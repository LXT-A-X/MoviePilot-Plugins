# -*- coding: utf-8 -*-
"""MoviePilot V3 插件：字幕字体代理（FontInAssProxy）。

反代 Emby/Jellyfin 字幕流，实时对字幕用到的字体做子集化并以 ``[Fonts]`` 段
嵌入 ASS 返回，使未安装对应字体的设备也能正确显示特效字幕。

部署拓扑（nginx）：
    location ~* /videos/(.*)/Subtitles/(.*)/(Stream[.]ass|Stream[.]ssa|Stream[.]srt|Stream[.])$ {
        proxy_set_header X-Original-URI $request_uri;
        proxy_pass http://moviepilot:3000/api/v1/plugin/FontInAssProxy/subtitle;
    }

实现要点：
- 插件 API 匿名访问：``"allow_anonymous": True``，字幕端点免鉴权由 nginx 直转。
- 直接返回 ``starlette.Response`` 即原样透传（``/api/v1/...`` 绕开统一响应包装）。
- 子集化走线程池 + 全局信号量（Semaphore 4），并优先使用 uharfbuzz（C）加速，
  失败自动回退 fontTools。
- 宿主导入使用稳定 SDK（``app.sdk.logging`` / ``app.sdk.config``），适配 MoviePilot V3。
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import re
import subprocess
import sys
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from starlette.responses import Response
from fastapi import Request

from .assparser import clip_dialogues_by_ticks, parse_ass
from .cache import SingleFlight, SubtitleCache
from .fontindex import FontIndex
from .internalproxy import InternalProxy
from .srt2ass import is_srt, srt_to_ass
from .subsetter import build_one_entry, inject_fonts
from .upstream import UpstreamClient, rewrite_location, to_full_uri, try_decode

try:
    from app.sdk.logging import logger as _app_logger
except Exception:
    _app_logger = logging.getLogger("FontInAssProxy")

try:
    from app.plugins import _PluginBase
except Exception:
    class _PluginBase:  # type: ignore
        """无宿主环境兜底（仅为模块可导入/可做语法与静态检查）。"""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._config: Dict[str, Any] = kwargs.get("config", {})
            self._data: Dict[str, Any] = {}

        def get_config(self) -> Dict[str, Any]:
            return self._config

        def get_data_path(self) -> str:
            return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".data")

        def save_data(self, key: str, value: Any) -> None:
            self._data[key] = value

        def get_data(self, key: str, default: Any = None) -> Any:
            return self._data.get(key, default)

        def post_message(self, channel: Any = None, title: str = "", text: str = "",
                         image: str = False, userid: Optional[Any] = None, link: str = "") -> bool:
            _app_logger.info(f"[消息] {title}: {text}")
            return True


_DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "emby_url": "",
    "emby_api_key": "",
    "font_dirs": "",
    "srt_default_font": "思源黑体 CN",
    "srt_font_size": 20,
    "srt_primary_colour": "&H00FFFFFF",
    "cache_enabled": True,
    "cache_ttl_hours": 24,
    "max_concurrent_subset": 4,
    "passthrough_on_error": True,
    "internal_proxy_enabled": False,
    "internal_proxy_port": 8097,
    "notify_enabled": True,
}

# 匹配 /Videos/{Id}/{MediaSourceId}/Subtitles/{Index}/{StartPositionTicks}/Stream.ass
_SUB_URI_RE = re.compile(
    r"^/?(?:[^/]+/)?Videos/(?P<item>[^/]+)/(?P<msid>[^/]+)/Subtitles/"
    r"(?P<idx>[^/]+)(?:/(?P<ticks>[^/]+))?/Stream(?P<fmt>\.(ass|ssa|srt|subrip))?$",
    re.IGNORECASE,
)

_PASS_HEADER_BLOCK = {"content-encoding", "transfer-encoding", "content-length", "connection"}

# 日志行：【INFO】2026-09-13 00:48:03,465 - fontinassproxy - 消息
_LOG_LINE_RE = re.compile(
    r"【(?P<level>\w+)】(?P<time>20\d{2}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[^:]* - [^\s]+ - (?P<msg>.*)"
)
# 兜底：任意前缀（可能缺级别标签）也剥离「模块名」段，只留消息
_LOG_FALLBACK_RE = re.compile(
    r"^(?:【\w+】)?(?P<time>20\d{2}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[^:]* - [^\s]+ - (?P<msg>.*)$"
)


def _tail_log(path: str, n_lines: int = 300) -> List[str]:
    """从文件尾部读最后 n_lines 行（避免整文件加载）。"""
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        block = 8192
        chunks: List[bytes] = []
        remaining = size
        while remaining > 0 and len(b"".join(chunks).splitlines()) < n_lines * 3:
            read = min(block, remaining)
            f.seek(remaining - read)
            chunks.append(f.read(read))
            remaining -= read
        content = b"".join(reversed(chunks)).decode("utf-8", errors="ignore")
    return content.splitlines()[-n_lines:]


def _pass_headers(src: Dict[str, str]) -> Dict[str, str]:
    return {k: v for k, v in src.items() if k.lower() not in _PASS_HEADER_BLOCK}


class FontInAssProxy(_PluginBase):
    """字幕字体代理主插件。"""

    plugin_name = "字幕字体代理"
    plugin_desc = "反代 Emby/Jellyfin 字幕流，实时子集化并嵌入字体（[Fonts] 段），未装字体的设备也能正常显示特效字幕"
    plugin_icon = "https://raw.githubusercontent.com/LXT-A-X/MoviePilot-Plugins/main/icons/fontinassproxy.jpg"
    plugin_version = "3.0.0"
    plugin_author = "LXT-A-X"
    author_url = "https://github.com/LXT-A-X/MoviePilot-Plugins"
    plugin_config_prefix = "fontinassproxy_"
    plugin_order = 100
    auth_level = 2

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._enabled = False
        self._index: Optional[FontIndex] = None
        self._cache: Optional[SubtitleCache] = None
        self._upstream: Optional[UpstreamClient] = None
        self._flight = SingleFlight()
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._executor: Optional[ThreadPoolExecutor] = None
        self._internal_proxy: Optional[InternalProxy] = None
        self._font_cache: "OrderedDict[Tuple[str, int], bytes]" = OrderedDict()
        self._font_cache_lock = threading.Lock()
        self._missing: Dict[str, Dict[str, Any]] = {}
        self._missing_lock = threading.Lock()
        self._base_data_dir = ""

    # ------------------------------------------------------------------ 生命周期
    def init_plugin(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.stop_service()
        self._enabled = False
        self._config = {}
        if not config:
            return
        cfg = {**_DEFAULT_CONFIG, **config}
        self._config = cfg
        if not bool(cfg.get("enabled", True)):
            _app_logger.info("字幕字体代理插件已禁用")
            return
        self._enabled = True
        try:
            self._ensure_deps()
            self._apply_runtime(cfg)
            _app_logger.info("字幕字体代理插件初始化完成")
        except Exception as e:
            _app_logger.exception(f"插件初始化失败: {e}")
            self._enabled = False

    def _ensure_deps(self) -> None:
        """后台检查/自动安装 Python 依赖（fontTools 等）。

        MP 的 requirements.txt 安装可能失败或装到旧版，这里兜底：
        缺失的包补装；fontTools 版本过低（<4.55，CFF/大字体子集化有 bug）自动升级。
        检查放后台线程，不阻塞插件启动。
        """
        def _run():
            try:
                # 1) 缺失/过旧 -> 收集要装的
                need: List[str] = []
                try:
                    ft = importlib.import_module("fontTools")
                    ver = tuple(int(x) for x in (getattr(ft, "version", "0") or "0").split(".")[:2])
                    if ver < (4, 55):
                        need.append("fonttools>=4.55.0")
                except Exception:
                    need.append("fonttools>=4.55.0")
                for mod in ("watchdog", "cachetools", "httpx", "charset_normalizer"):
                    try:
                        importlib.import_module(mod)
                    except Exception:
                        need.append(mod)
                if not need:
                    return
                _app_logger.info(f"依赖检查：需要安装/升级 {need}")
                cmd = [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check"]
                cmd += need
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if proc.returncode == 0:
                    _app_logger.info(f"依赖安装完成: {', '.join(need)}")
                else:
                    _app_logger.warning(f"依赖安装失败: {proc.stderr[-500:]}")
            except Exception as e:
                _app_logger.warning(f"依赖自动安装异常: {e}")

        threading.Thread(target=_run, daemon=True,
                         name="FontInAssProxy-deps").start()

    def _apply_runtime(self, cfg: Dict[str, Any]) -> None:
        """按最新配置重建运行时资源（启动与配置热生效共用）。"""
        self._base_data_dir = self._data_dir()
        # 并发闸门与线程池
        try:
            max_con = max(1, int(cfg.get("max_concurrent_subset") or 2))
        except (TypeError, ValueError):
            max_con = 2
        self._semaphore = asyncio.Semaphore(max_con)
        self._executor = ThreadPoolExecutor(
            max_workers=max_con * 2, thread_name_prefix="fiasub")

        # 字体索引（后台线程扫描，不阻塞启动）
        font_dirs = [d.strip() for d in str(cfg.get("font_dirs") or "").split(";") if d.strip()]
        if font_dirs:
            db_path = os.path.join(self._base_data_dir, "fontindex.db")
            self._index = FontIndex(db_path, font_dirs,
                                    report=lambda msg: _app_logger.info(msg))
            self._index.start()
            _app_logger.info(f"字体索引启动，目录: {font_dirs}")

        # 缓存
        if cfg.get("cache_enabled"):
            cache_dir = str(cfg.get("cache_dir") or "") or os.path.join(self._base_data_dir, "cache")
            self._cache = SubtitleCache(
                cache_dir,
                mem_size=256,
                ttl_hours=float(cfg.get("cache_ttl_hours") or 720),
            )
            _app_logger.info(f"字幕缓存目录: {self._cache.cache_dir}")

        # 回源客户端
        emby_url = str(cfg.get("emby_url") or "").rstrip("/")
        if emby_url:
            self._upstream = UpstreamClient(emby_url, cfg.get("emby_api_key") or None)
        else:
            _app_logger.warning("未配置 Emby 地址，处理将无法回源")

        # 内置反代（可选，替代外部 nginx）
        if cfg.get("internal_proxy_enabled"):
            try:
                port = int(cfg.get("internal_proxy_port") or 8097)
            except (TypeError, ValueError):
                port = 8097
            self._internal_proxy = InternalProxy(
                port, self._serve_uri,
                subtitle_check=self._is_subtitle_uri,
                stream_check=self._is_stream_uri,
                streamer=self._upstream,
            )
            if not self._internal_proxy.start():
                _app_logger.warning(f"内置反代启动失败（端口 {port} 可能被占用）")

    @staticmethod
    def _is_subtitle_uri(original_uri: str) -> bool:
        """内置反代分流：字幕路径走处理链路。"""
        try:
            return bool(_SUB_URI_RE.match(urlsplit(original_uri).path))
        except Exception:
            return False

    @staticmethod
    def _is_stream_uri(original_uri: str, method: str = "GET") -> bool:
        """内置反代分流：视频/音频流路径（大头流量）走流式透传。"""
        if method not in ("GET", "HEAD"):
            return False
        path = urlsplit(original_uri).path.lower()
        # Emby/Jellyfin 媒体流端点（videos 播放流 / 音频 / 字幕预览不在此列）
        if "/videos/" in path and ("/stream." in path or path.rstrip("/").endswith("/stream")):
            return True
        if "/audios/" in path and "/stream." in path:
            return True
        if path.endswith((".mp4", ".mkv", ".ts", ".m2ts", ".mp3", ".flac", ".m4a",
                          ".opus", ".ogg", ".aac", ".webm", ".mov", ".wav")):
            return True
        return False

    def _data_dir(self) -> str:
        try:
            p = self.get_data_path()
            if p:
                os.makedirs(p, exist_ok=True)
                return str(p)
        except Exception:
            pass
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".data")
        os.makedirs(p, exist_ok=True)
        return p

    def get_state(self) -> bool:
        return self._enabled

    def stop_service(self) -> None:
        """停止内置反代、watchdog、线程池与回源客户端，避免插件重载线程泄漏。"""
        try:
            if self._internal_proxy:
                self._internal_proxy.stop()
                self._internal_proxy = None
        except Exception as e:
            _app_logger.warning(f"停内置反代失败: {e}")
        try:
            if self._index:
                self._index.close()
                self._index = None
        except Exception as e:
            _app_logger.warning(f"停字体索引失败: {e}")
        try:
            if self._executor:
                self._executor.shutdown(wait=False, cancel_futures=True)
                self._executor = None
        except Exception:
            pass
        try:
            if self._upstream:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(self._upstream.aclose())
                    else:
                        loop.run_until_complete(self._upstream.aclose())
                except Exception:
                    pass
                self._upstream = None
        except Exception:
            self._upstream = None

    # ------------------------------------------------------------------ 渲染模式（Vue 联邦）
    @staticmethod
    def get_render_mode() -> Tuple[str, Optional[str]]:
        return "vue", "dist/assets"

    # ------------------------------------------------------------------ 配置
    def _current_config(self) -> Dict[str, Any]:
        return {**_DEFAULT_CONFIG, **(self._config or {})}

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        # vue 模式：配置 UI 由联邦 Config 组件渲染，这里只提供默认配置模型
        return [], self._current_config()

    def get_page(self) -> Optional[List[dict]]:
        # vue 模式：详情页由联邦 Page 组件渲染
        return []

    # ------------------------------------------------------------------ 命令与服务
    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return [
            {"cmd": "/重建字体索引", "event": "plugin.action", "desc": "字幕字体代理：重建字体索引", "data": {"action": "rebuild_index"}, "category": "字幕字体代理"},
            {"cmd": "/清理字幕缓存", "event": "plugin.action", "desc": "字幕字体代理：清空处理结果缓存", "data": {"action": "clear_cache"}, "category": "字幕字体代理"},
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "font_change_notify",
                "name": "FFA 字体变更通知",
                "trigger": "interval",
                "func": self._font_change_task,
                "kwargs": {"seconds": 60},
                "func_kwargs": {},
            },
            {
                "id": "cache_clean",
                "name": "FFA 缓存清理",
                "trigger": "interval",
                "func": self._clean_cache_task,
                "kwargs": {"seconds": 14400},
                "func_kwargs": {},
            },
        ]

    def _font_change_task(self) -> None:
        """定时消费索引变更：新字体放入目录后提示（对齐 zitifenlei 的监控通知）。"""
        index = self._index
        if not index:
            return
        try:
            added, removed = index.drain_changes()
        except Exception as e:
            _app_logger.warning(f"字体变更统计失败: {e}")
            return
        if added or removed:
            _app_logger.info(f"字体目录变更：新增 {added} 个，删除 {removed} 个")
            if not bool((self._config or {}).get("notify_enabled", True)):
                return
            try:
                self.post_message(
                    title="字幕字体代理：字体索引更新",
                    text=f"检测到字体目录变化：新增 {added} 个字体，删除 {removed} 个。已自动更新索引并生效。",
                )
            except Exception:
                pass

    def _clean_cache_task(self) -> None:
        """定时清理过期磁盘缓存。"""
        if not self._cache:
            return
        try:
            self._cache.clear_expired()
        except Exception as e:
            _app_logger.warning(f"缓存清理失败: {e}")

    # ------------------------------------------------------------------ API
    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {
                "path": "/subtitle",
                "endpoint": self.handle_subtitle,
                "methods": ["GET"],
                "allow_anonymous": True,   # auth: None 会被强制改成 apikey，匿名开关是它
                "summary": "字幕字体代理流端点",
                "description": "由 nginx 拦截字幕路径后反代到此，处理并返回嵌入字体的 ASS",
            },
            {"path": "/config", "endpoint": self.api_get_config, "methods": ["GET"], "auth": "bear", "summary": "获取插件配置"},
            {"path": "/config", "endpoint": self.api_save_config, "methods": ["POST"], "auth": "bear", "summary": "保存插件配置"},
            {"path": "/status", "endpoint": self.api_status, "methods": ["GET"], "auth": "bear", "summary": "运行状态"},
            {"path": "/logs", "endpoint": self.api_logs, "methods": ["GET"], "auth": "bear", "summary": "插件日志"},
            {"path": "/logs/clear", "endpoint": self.api_logs_clear, "methods": ["POST"], "auth": "bear", "summary": "清除插件日志"},
            {"path": "/missing", "endpoint": self.api_missing, "methods": ["GET"], "auth": "bear", "summary": "缺失字体列表"},
            {"path": "/missing/clear", "endpoint": self.api_missing_clear, "methods": ["POST"], "auth": "bear", "summary": "清除缺失字体记录"},
            {"path": "/rebuild", "endpoint": self.api_rebuild, "methods": ["POST"], "auth": "bear", "summary": "重建字体索引"},
            {"path": "/clear_cache", "endpoint": self.api_clear_cache, "methods": ["POST"], "auth": "bear", "summary": "清空字幕缓存"},
        ]

    # ------------------------------------------------------------------ 管理 API
    @staticmethod
    def _ok(data: Any = None, message: str = "success") -> Dict[str, Any]:
        return {"success": True, "message": message, "data": data}

    @staticmethod
    def _err(message: str = "error", code: int = 500) -> Dict[str, Any]:
        return {"success": False, "message": message, "code": code}

    def api_get_config(self) -> Dict[str, Any]:
        return self._ok(self._current_config())

    async def api_save_config(self, request: Request) -> Dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict) or not body:
            return self._err("无效的配置数据", 400)
        new_cfg = {**self._current_config(), **{k: v for k, v in body.items()}}
        # 1) 写入宿主原生配置（与宿主 PUT 等效，重启保留）
        try:
            self.update_config(new_cfg)
        except Exception as e:
            _app_logger.warning(f"宿主配置写入失败: {e}")
        # 2) 更新运行时并热生效（_apply_runtime 已在后台线程启动全量扫描，不阻塞）
        self._config = new_cfg
        self.stop_service()  # 释放旧资源（watchdog/线程池/回源）
        if bool(new_cfg.get("enabled", True)):
            self._enabled = True
            try:
                self._apply_runtime(new_cfg)
                return self._ok(None, "配置已保存并生效（字体索引后台扫描中…）")
            except Exception as e:
                self._enabled = False
                _app_logger.exception(f"配置热生效失败: {e}")
                return self._err(f"配置已保存，但运行时启动失败: {e}")
        else:
            self._enabled = False
            self._semaphore = None
            self._executor = None
            return self._ok(None, "配置已保存（插件已禁用）")

    def api_status(self) -> Dict[str, Any]:
        index = self._index
        cache = self._cache.stats() if self._cache else {}
        missing_total = 0
        miss_count = 0
        with self._missing_lock:
            missing_total = len(self._missing)
            miss_count = sum(r["count"] for r in self._missing.values())
        scanning = False
        if index:
            try:
                scanning = bool(index._thread and index._thread.is_alive())
            except Exception:
                scanning = False
        # fontTools 版本（依赖自检用）
        ft_ver = "?"
        try:
            import fontTools
            ft_ver = getattr(fontTools, "version", "?")
        except Exception:
            pass
        # uharfbuzz 版本（子集化主引擎；未安装则为 "?"，走 fontTools 兜底）
        hb_ver = "?"
        try:
            import uharfbuzz as _hb
            hb_ver = getattr(_hb, "__version__", "?")
        except Exception:
            pass
        index_obj = {
            "ready": bool(index and index.ready()),
            "scanning": scanning,
            "faces": index.db.font_count() if index else 0,
            "version": index.db.index_version() if index else 0,
            "dirs": index.font_dirs if index else [],
        } if index else {"ready": False, "scanning": False, "faces": 0,
                         "version": 0, "dirs": []}
        return self._ok({
            "enabled": self._enabled,
            "emby_url": str(self._config.get("emby_url") or "") if self._config else "",
            "index": index_obj,
            "fonttools_version": ft_ver,
            "uharfbuzz_version": hb_ver,
            "cache": cache,
            "missing": missing_total,
            "miss_count": miss_count,
            "internal_proxy": {
                "enabled": bool(self._internal_proxy),
                "port": int(self._config.get("internal_proxy_port") or 8097) if self._config else 0,
            },
        })

    def api_missing(self) -> Dict[str, Any]:
        with self._missing_lock:
            items = [
                {"font_name": k, "count": v["count"], "last_seen": v["last_seen"]}
                for k, v in sorted(self._missing.items(), key=lambda kv: -kv[1]["count"])
            ][:200]
        return self._ok(items)

    def api_logs(self, lines: int = 300) -> Dict[str, Any]:
        """读取本插件日志并结构化（对齐 zitifenlei：id/time/level/message）。

        插件日志独立存放于 LOG_PATH/plugins/fontinassproxy.log；
        优先读独立插件日志，不存在时兜底读 moviepilot.log 过滤。
        """
        n = int(lines) if lines else 300
        candidates: List[str] = []
        try:
            from app.sdk.config import settings
            if settings and settings.LOG_PATH:
                candidates.append(str(settings.LOG_PATH / "plugins" / "fontinassproxy.log"))
                candidates.append(str(settings.LOG_PATH / "moviepilot.log"))
        except Exception:
            pass
        candidates += ["/config/logs/plugins/fontinassproxy.log", "/config/logs/moviepilot.log"]
        raw_rows: List[str] = []
        seen: Optional[str] = None
        for path in candidates:
            if not os.path.exists(path):
                continue
            if seen == path:
                continue
            seen = path
            try:
                rows = _tail_log(path, n)
            except OSError:
                continue
            if "fontinassproxy" in os.path.basename(path).lower():
                raw_rows = rows
                break
            raw_rows = [r for r in rows if "fontinassproxy" in r.lower()]
            if raw_rows:
                break
        out = []
        for i, line in enumerate(raw_rows):
            m = _LOG_LINE_RE.match(line)
            if m:
                lv = m.group("level").lower()
                level = "error" if lv in ("error", "critical") else "warning" if lv == "warning" else "info"
                out.append({"id": i, "time": m.group("time"),
                            "level": level, "message": m.group("msg").strip()})
            else:
                fb = _LOG_FALLBACK_RE.match(line)
                if fb:
                    out.append({"id": i, "time": fb.group("time"),
                                "level": "info", "message": fb.group("msg").strip()})
                else:
                    out.append({"id": i, "time": "", "level": "info", "message": line})
        return self._ok(out)

    async def api_logs_clear(self) -> Dict[str, Any]:
        """截断插件日志文件（清空内容，文件保留）。"""
        path = self._plugin_log_path()
        if not path:
            return self._ok({"cleared": 0}, "插件日志文件不存在")
        try:
            with open(path, "w", encoding="utf-8"):
                pass
        except OSError as e:
            return self._err(f"清除日志失败: {e}")
        return self._ok({"cleared": 1}, "插件日志已清除")

    def _plugin_log_path(self) -> Optional[str]:
        """定位本插件日志文件路径（存在才返回）。"""
        candidates: List[str] = []
        try:
            from app.sdk.config import settings
            if settings and settings.LOG_PATH:
                candidates.append(str(settings.LOG_PATH / "plugins" / "fontinassproxy.log"))
        except Exception:
            pass
        candidates.append("/config/logs/plugins/fontinassproxy.log")
        for p in candidates:
            if os.path.exists(p):
                return p
        return None

    async def api_missing_clear(self) -> Dict[str, Any]:
        """清除缺失字体记录（仅清内存统计，不影响字体索引）。"""
        with self._missing_lock:
            n = len(self._missing)
            self._missing.clear()
        self._missing_notified = False  # 允许再次触发缺失通知
        return self._ok({"cleared": n}, f"已清除 {n} 条缺失字体记录")

    async def api_rebuild(self) -> Dict[str, Any]:
        """重建字体索引（to_thread 后台执行，1.7 万字体需较长时间，不阻塞请求线程）。"""
        if not self._index:
            return self._err("未配置字体目录，无法重建索引", 400)
        try:
            faces = await asyncio.to_thread(self._index.rebuild)
            return self._ok({"faces": faces}, f"字体索引已重建（{faces} face）")
        except Exception as e:
            _app_logger.exception(f"重建索引失败: {e}")
            return self._err(f"重建索引失败: {e}")

    async def api_clear_cache(self) -> Dict[str, Any]:
        if not self._cache:
            return self._ok({"removed": 0}, "缓存未启用")
        removed = await self._cache.clear()
        return self._ok({"removed": removed}, f"已清空缓存（{removed} 个文件）")

    # ------------------------------------------------------------------ 主链路
    async def handle_subtitle(self, request: Request) -> Response:
        """插件 API 端点（/api/v1/plugin/FontInAssProxy/subtitle）。"""
        try:
            original_uri = request.headers.get("X-Original-URI") or str(request.url)
            status, body, headers = await self._serve_uri(
                original_uri, dict(request.headers), request.method)
            return Response(content=body, status_code=status, headers=headers)
        except Exception as e:
            _app_logger.exception(f"字幕处理异常: {e}")
            return Response(content=b"", status_code=500, media_type="text/plain")

    async def _serve_uri(self, original_uri: str,
                         headers: Dict[str, str], method: str = "GET",
                         body: bytes = b"") -> Tuple[int, bytes, Dict[str, str]]:
        """统一字幕代理链路（web 框架无关，插件 API 与内置反代共用）。

        返回 (status, body, resp_headers)。
        """
        parsed = urlsplit(original_uri)
        m = _SUB_URI_RE.match(parsed.path)
        # 非字幕路径 / 无法解析 -> 原样透传
        if not m:
            return await self._passthrough_uri(original_uri, headers, method, body)

        fmt = (m.group("fmt") or "").lower()
        is_ass = fmt in (".ass", ".ssa")
        is_srt = fmt in (".srt", ".subrip")
        if (not is_ass and not is_srt) or not self._enabled:
            return await self._passthrough_uri(original_uri, headers, method, body)

        ticks = 0
        try:
            ticks = int(m.group("ticks") or 0)
        except ValueError:
            ticks = 0

        # 回源完整字幕（忽略 StartPositionTicks，字形覆盖按完整字幕算）
        full_uri = to_full_uri(original_uri) if ticks else original_uri

        # 缓存（未裁剪内容；裁剪属于展示层，逐请求做）
        key: Optional[str] = None
        if self._cache:
            key = self._cache.make_key(
                m.group("item"), m.group("msid"), m.group("idx"), fmt,
                self._index.db.index_version() if self._index else 0,
                self._srt_cfg_ver(),
            )
            cached = await self._cache.get(key)
            if cached is not None:
                _app_logger.info(f"字幕缓存命中（{len(cached) / 1024:.1f}KB，直接返回，跳过子集化）")
                return 200, self._clip_ass(cached, ticks), self._ass_headers()

        # 全局并发闸门：加速后单请求 ~1s，等待 3s 内腾不出许可才降级透传
        # （字幕晚 3 秒出来，远比完全没有字体好）
        if self._semaphore:
            try:
                await asyncio.wait_for(self._semaphore.acquire(), timeout=3.0)
            except asyncio.TimeoutError:
                _app_logger.warning("子集化并发已满，请求降级透传")
                return await self._passthrough_uri(original_uri, headers, method, body)
            try:
                return await self._process_locked(key, original_uri, full_uri,
                                                  is_srt, ticks, headers,
                                                  method, body)
            finally:
                self._semaphore.release()
        return await self._process_locked(key, original_uri, full_uri,
                                          is_srt, ticks, headers, method, body)

    async def _process_locked(self, key: Optional[str], original_uri: str,
                              full_uri: str, is_srt_fmt: bool, ticks: int,
                              headers: Dict[str, str], method: str = "GET",
                              req_body: bytes = b"") -> Tuple[int, bytes, Dict[str, str]]:
        """已获得并发许可：并发去重 + 处理（字体索引版本已在 key 中体现）。"""
        async def do_process():
            return await self._build_ass(headers, original_uri, full_uri, is_srt_fmt)

        if key:
            body = await self._flight.run(key, do_process)
        else:
            body = await do_process()

        if body is None:
            return await self._passthrough_uri(original_uri, headers, method, req_body)

        if key and self._cache:
            await self._cache.set(key, body)

        return 200, self._clip_ass(body, ticks), self._ass_headers()

    @staticmethod
    def _ass_headers() -> Dict[str, str]:
        return {
            "content-type": "text/x-ssa; charset=utf-8",
            "X-FontInAss": "1",
            "Cache-Control": "no-cache",
        }

    def _clip_ass(self, body: bytes, ticks: int) -> bytes:
        """对完整 ASS 按请求时间窗裁剪（12 步：字形覆盖仍按全量）。"""
        if ticks <= 0:
            return body
        try:
            text = body.decode("utf-8-sig", errors="ignore")
            return ("\ufeff" + clip_dialogues_by_ticks(text, ticks)).encode("utf-8")
        except Exception:
            return body

    def _srt_cfg_ver(self) -> str:
        cfg = self._config or {}
        return f"{cfg.get('srt_default_font')}|{cfg.get('srt_font_size')}|{cfg.get('srt_primary_colour')}"

    async def _build_ass(self, headers: Dict[str, str], original_uri: str,
                         full_uri: str, is_srt_fmt: bool) -> Optional[bytes]:
        """回源 -> 转换 -> 解析 -> 子集化 -> 注入 [Fonts]。返回完整 ASS bytes。

        返回 None 表示无需处理（透传由调用方决定），并记录原因日志。
        """
        t0 = time.perf_counter()

        _app_logger.info(f"字幕URL: `{full_uri}`")

        if not self._upstream:
            _app_logger.warning(f"字幕处理跳过(未配置回源地址): {original_uri}")
            return None
        # 剥离客户端 Range/If-Range：字幕必须取完整内容，否则 Emby 返回 206 片段
        up_headers = {k: v for k, v in headers.items()
                      if k.lower() not in ("range", "if-range")}
        status, raw, _ = await self._upstream.fetch(full_uri, up_headers)
        if status != 200 or not raw:
            _app_logger.warning(f"字幕回源失败 status={status}（透传原始）: {original_uri}")
            return None

        text = try_decode(raw)
        if text is None:
            _app_logger.warning("字幕编码无法识别（透传原始）")
            return None

        # 原字幕已内嵌字体子集（[Fonts] 段 + fontname 条目）-> 跳过处理，原样透传，
        # 避免对已子集化的字幕重复注入产生冗余/报错。
        if re.search(r"(?im)^\[Fonts\]\s*$", text) and re.search(r"(?im)^\s*fontname\s*:", text):
            _app_logger.info("字幕已含 [Fonts] 内嵌字体，跳过处理（原样透传）")
            return None

        if is_srt_fmt or is_srt(text):
            cfg = self._config or {}
            try:
                fsize = int(cfg.get("srt_font_size") or 20)
            except (TypeError, ValueError):
                fsize = 20
            text = srt_to_ass(
                text,
                font_name=str(cfg.get("srt_default_font") or "思源黑体 CN"),
                font_size=fsize,
                primary_colour=str(cfg.get("srt_primary_colour") or "&H00FFFFFF"),
            )

        if not self._index or not self._index.ready():
            _app_logger.warning("字体索引未就绪，本请求透传")
            return None

        t_parse = time.perf_counter()
        try:
            parsed = parse_ass(text)
        except Exception as e:
            _app_logger.warning(f"ASS 解析失败: {e}（透传原始）")
            return None
        _app_logger.info(f"ass分析      {(time.perf_counter() - t_parse) * 1000:.2f}ms")
        if not parsed.char_map:
            _app_logger.warning("字幕未解析出可用字体（透传原始）")
            return None

        items = [(name, w, it, chars) for (name, w, it), chars in parsed.char_map.items() if chars]
        if not items:
            _app_logger.warning("字幕字符集为空（透传原始）")
            return None

        loop = asyncio.get_running_loop()
        executor = self._executor

        def worker(item) -> Tuple[str, str, str]:
            name, w, it, charset = item
            try:
                t_load = time.perf_counter()
                resolved = self._resolve_font(name, w, it)
                load_ms = (time.perf_counter() - t_load) * 1000
                if resolved is None:
                    return name, "miss", ""
                path, face, fb = resolved
                _app_logger.info(
                    f"从本地加载字体 {len(fb) / 1024 / 1024:.2f}MB {load_ms:.2f}ms"
                    f"      [('{name}', {w}, {it}) <== {path}]"
                )
                t_sub = time.perf_counter()
                miss, entry = build_one_entry(fb, face, name, w, it, set(charset))
                sub_ms = (time.perf_counter() - t_sub) * 1000
                _app_logger.info(
                    f"子集化 {len(set(charset))} 个字符 {sub_ms:.2f}ms            [{name}]"
                )
                return name, miss, entry
            except Exception as e:
                # 临时诊断：打印完整堆栈定位真实错误源（bad parameter 等）
                import traceback
                _app_logger.error(f"子集化 worker 异常 [{name}] chars={len(set(charset))} "
                                  f"face={face if 'face' in dir() else '?'} path={path if 'path' in dir() else '?'}\n"
                                  f"{traceback.format_exc()}")
                return name, f"error:{e}", ""

        tasks = [loop.run_in_executor(executor, worker, it) for it in items]
        results = await asyncio.gather(*tasks)

        entries: List[str] = []
        errors: List[str] = []
        for name, status2, entry in results:
            if status2 == "miss":
                errors.append(f"字体缺失[{name}]")
                self._record_missing(name)
            elif status2.startswith("error"):
                errors.append(f"子集化失败[{name}] {status2}")
            elif status2 == "busy":
                errors.append(f"并发占用[{name}]")
            elif status2:
                errors.append(f"缺字形[{name}]({status2})")
            if entry:
                entries.append(entry)

        if not entries:
            _app_logger.warning(
                f"无可用字体子集，本请求透传；请求字体 {len(items)} 个全部未匹配（{len(errors)} 项）：{'; '.join(errors)}")
            self._notify_missing()
            return None

        t_ass = time.perf_counter()
        try:
            ass_out_raw = inject_fonts(text, entries)
        except Exception as e:
            _app_logger.warning(f"注入 [Fonts] 失败: {e}")
            return None
        ass_out = ass_out_raw.encode("utf-8-sig")
        ass_ms = (time.perf_counter() - t_ass) * 1000
        _app_logger.info(f"子集化嵌入  {ass_ms:.2f}ms")

        if errors:
            _app_logger.warning(f"子集化告警({len(errors)}): {'; '.join(errors)}")
        dur_ms = (time.perf_counter() - t0) * 1000
        _app_logger.info(
            f"字幕处理完成: {len(raw) / 1024 / 1024:.2f}MB ==> {len(ass_out) / 1024 / 1024:.2f}MB  （总 {dur_ms:.0f}ms，注入 {len(entries)} 个字体）"
        )
        _app_logger.info("---------------- 打印 字幕处理完成 分隔线 ----------------")
        return ass_out

    def _resolve_font(self, name: str, weight: int, italic: bool) -> Optional[Tuple[str, int, bytes]]:
        """匹配字体文件并读取（LRU 缓存字节）。"""
        index = self._index
        if not index:
            return None
        hit = index.match(name, weight, italic)
        if hit is None:
            def_font = str((self._config or {}).get("srt_default_font") or "思源黑体 CN")
            if name != def_font:
                hit = index.match(def_font, 400, False)
        if hit is None:
            return None
        path, face = hit
        lock_key = (path, face)
        with self._font_cache_lock:
            bits = self._font_cache.get(lock_key)
        if bits is None:
            try:
                with open(path, "rb") as f:
                    bits = f.read()
            except OSError:
                _app_logger.warning(f"读取字体失败: {path}")
                return None
            with self._font_cache_lock:
                self._font_cache[lock_key] = bits
                while len(self._font_cache) > 32:
                    self._font_cache.popitem(last=False)
        return path, face, bits

    def _record_missing(self, name: str) -> None:
        with self._missing_lock:
            rec = self._missing.setdefault(name, {"count": 0, "last_seen": 0.0})
            rec["count"] += 1
            rec["last_seen"] = time.time()

    def _notify_missing(self) -> None:
        with self._missing_lock:
            if not self._missing:
                return
            top = sorted(self._missing.items(), key=lambda kv: -kv[1]["count"])[:5]
        # 仅在首次集中出现时通知一次（避免刷屏）
        if getattr(self, "_missing_notified", False):
            return
        self._missing_notified = True
        if not bool((self._config or {}).get("notify_enabled", True)):
            return
        text = "\n".join(f"  {k} ×{v['count']}" for k, v in top)
        try:
            self.post_message(title="字幕字体代理：缺失字体", text=f"字体索引未匹配到：\n{text}")
        except Exception:
            pass

    # ------------------------------------------------------------------ 透传
    async def _passthrough_uri(self, original_uri: str,
                               headers: Dict[str, str], method: str = "GET",
                               req_body: bytes = b"") -> Tuple[int, bytes, Dict[str, str]]:
        """回源原始请求原样返回（不处理）。方法/请求体原样转发；重定向不跟随并改写成相对路径。"""
        if not self._upstream:
            return 502, b"", {"content-type": "text/plain; charset=utf-8"}
        status, raw, resp_headers = await self._upstream.fetch(
            original_uri, headers, follow=False, method=method, content=req_body or None)
        out = _pass_headers(resp_headers)
        # 3xx：Location 里的绝对地址改写成相对路径，避免浏览器跳出反代直连 Emby
        if 300 <= status < 400:
            loc = None
            for k in ("location", "Location"):
                v = out.pop(k, None)
                if v:
                    loc = v
                    break
            if loc:
                out["location"] = rewrite_location(loc)
        out.setdefault("content-type", "text/plain; charset=utf-8")
        return status, raw, out