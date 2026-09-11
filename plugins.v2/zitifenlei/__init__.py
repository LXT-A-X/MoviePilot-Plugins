"""
字体分类管家 (Font Manager)
MoviePilot V2 插件 - 字体归档整理 + ASS 字幕字体检查
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from fastapi import Body, Request, HTTPException
except Exception:
    class HTTPException(Exception):
        def __init__(self, *_, status_code: int = 500, detail: str = "") -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    def Body(default: Any = None, **_: Any) -> Any:
        return default

try:
    from app.core.config import settings as _settings
except Exception:
    _settings = None

try:
    from app.log import logger as _logger
except Exception:
    import logging
    _logger = logging.getLogger("Zitifenlei")

try:
    from app.plugins import _PluginBase
except Exception:
    class _PluginBase:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._config: Dict[str, Any] = kwargs.get("config", {})
            self._data: Dict[str, Any] = {}

        def get_config(self) -> Dict[str, Any]:
            return self._config

        def get_data_path(self) -> Path:
            return Path(__file__).resolve().parent / ".data"

        def get_data(self, key: str, default: Any = None) -> Any:
            return self._data.get(key, default)

        def save_data(self, key: str, value: Any) -> None:
            if value is None:
                self._data.pop(key, None)
            else:
                self._data[key] = value

        def update_config(self, config: Dict[str, Any]) -> bool:
            self._config.update(config)
            return True

        def get_state(self) -> bool:
            return True

        def get_service(self) -> List[Dict[str, Any]]:
            return []

        def stop_service(self) -> None:
            pass

        def post_message(self, *_: Any, **__: Any) -> bool:
            return True

try:
    from watchdog.observers import Observer
    from watchdog.observers.polling import PollingObserver
    from watchdog.events import FileSystemEventHandler
    _HAS_WATCHDOG = True
except Exception:
    _HAS_WATCHDOG = False
    Observer = None
    PollingObserver = None
    FileSystemEventHandler = object

try:
    from app.core.event import eventmanager
    from app.schemas.types import EventType
except Exception:
    eventmanager = None

    class EventType:  # 兜底：仅避免在无宿主环境导入时崩溃
        TransferComplete = "transfer.complete"
        WebhookMessage = "webhook.message"

from .db import FontDB
from .font_utils import (
    FONT_EXTENSIONS,
    TTFont,
    is_font_file,
    is_ass_file,
    parse_font_metadata,
    get_font_psname,
    parse_ass_fonts,
    normalize_font_key,
    has_embedded_fonts,
)
from . import subsets as af

_DEFAULT_CONFIG = {
    "enabled": True,
    "input_dir": "",
    "lib_dir": "",
    "ass_dir": "",
    "subset_dir": "",
    "scan_mode": "internal",
    "archive_mode": "copy",
    "font_name_internal": False,  # 利用字体内部名称（PostScript 名 nameID 6）命名归档：开用内部名，关保持原名
    # 移动归档时删除判重跳过的残留源文件：只作用于「移动原文件」模式——
    # move 归档判重跳过（字体库已存在同名同后缀）时，监控目录的源文件会残留，
    # 开关开=删除残留；关=保留（复制模式不受影响，源文件本就保留）
    "move_delete_duplicate": True,
    "monitor_enabled": False,  # 是否启用监控（总开关）：统一控制字体监控目录 / ASS字幕目录监控 / ASS目录监控子集的启停
    # 老版本监控开关（auto_monitor/auto_check）已被 monitor_enabled 合并，保留键仅用于旧配置迁移读取
    "auto_monitor": False,
    "auto_check": False,
    "auto_inbound": True,
    "auto_collect": True,
    "notify_enabled": False,
    # 子集化（assfonts）设置
    "auto_subset": False,
    "subset_overwrite": False,
    "subset_rename": True,
    "subset_out_dir": "",
    "subset_out_mode": "copy",
    "subset_sync_subdir": False,  # 同步子集字体夹（*_subsetted）：默认不同步（字体已内嵌进字幕，夹子仅供备份）
    # HDR 字幕亮度（子集化/上传字幕处理后按档位压暗主色/描边/阴影，避免 HDR 下刺眼）
    "hdr_brightness": "",
    "hdr_brightness_level": "80",
}


def _path_within(path: Path, base: Path) -> bool:
    """路径组件级判断 path 是否位于 base 目录内。

    不能用字符串 startswith：`/video/测试` 是 `/video/测试2` 的字符串前缀，
    会把平级目录误判成子目录，导致字体被当成「已在字体库内」而跳过。
    """
    try:
        return Path(path).resolve().is_relative_to(Path(base).resolve())
    except AttributeError:  # 旧版 Python 回退
        p = Path(path).resolve()
        b = Path(base).resolve()
        return str(p) == str(b) or b in p.parents


def _font_subdir_name(suffix: str) -> str:
    """归档的格式子文件夹名：取扩展名小写去点（ttf / otf / ttc / woff / woff2），
    无后缀时兜底 font。按格式分子文件夹后同字体不同格式互不冲突、目录清晰。"""
    return (suffix or "").lower().lstrip(".") or "font"


def _dest_exists_recursive(dir_: Path, base: str, suffix: str) -> Optional[Path]:
    """判重：在目标目录 dir_（含平铺旧布局与格式子文件夹/子目录递归）内查找
    同基础名 + 同扩展名的已存在文件，命中返回该文件路径（供跳过/去重），未命中返回 None。

    兼容布局切换过渡期——旧文件平铺在 厂商/ 下、新文件将进厂商/<格式>/，跨布局同名同后缀
    也应判为重复，避免「同字体同格式」被重复归档成两份。
    """
    target = _font_subdir_name(suffix)
    cands = list(dir_.rglob(f"*{suffix.lower()}")) + list(dir_.rglob(f"*{suffix.upper()}"))
    seen: set = set()
    for c in cands:
        try:
            if not c.is_file():
                continue
            rp = str(c.resolve())
            if rp in seen:
                continue
            seen.add(rp)
            if c.stem.lower() == base.lower():
                return c
        except Exception:
            continue
    # 兜底：直接拼目标路径（同库当前布局可直接命中；子目录里同后缀同名已在上方 rglob 覆盖）
    plain = dir_ / f"{base}{suffix}"
    if plain.exists() or (dir_ / target / f"{base}{suffix}").exists():
        return plain if plain.exists() else (dir_ / target / f"{base}{suffix}")
    return None


def _ensure_plugin_logfile() -> str:
    """让插件日志落到 <logs根>/plugins/zitifenlei.log（MoviePilot /api/v1/system/logging 约定路径），
    便于在系统「日志」页直接查看插件日志。幂等：只挂一次 FileHandler。

    使用独立 logger「ZitifenleiFile」（db.add_log 镜像到同一实例），
    不占用 MP 全局 logger 的输出级别，插件自己的文件日志完全独立可控。
    """
    try:
        if getattr(_logger, "_zt_logfile_ok", False):
            return getattr(_logger, "_zt_logfile_path", "") or ""
        root: Optional[Path] = None
        try:
            for attr in ("get_log_path", "LOG_PATH"):
                v = getattr(_settings, attr, None)
                if callable(v):
                    v = v()
                if v:
                    root = Path(str(v))
                    break
        except Exception:
            pass
        if root is None:
            cand = Path("/config/logs")
            if cand.is_dir():
                root = cand
        if root is None:
            root = Path(__file__).resolve().parent / ".data"
        try:
            plugins_dir = root / "plugins"
            plugins_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        file = str((root / "plugins" / "zitifenlei.log"))
        handler = logging.FileHandler(file, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
        )
        handler.setLevel(logging.DEBUG)
        _zt_logger = logging.getLogger("ZitifenleiFile")
        _zt_logger.setLevel(logging.DEBUG)
        # 防止热加载/重复 init 时累积多个 FileHandler 写同一文件
        for h in list(_zt_logger.handlers):
            try:
                if isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", "") == file:
                    _zt_logger.removeHandler(h)
                    h.close()
            except Exception:
                pass
        _zt_logger.addHandler(handler)
        # 幂等标志挂在插件模块 logger 上（_settings 属性被宿主冻结的风险小，见下）
        setattr(_logger, "_zt_logfile_ok", True)
        setattr(_logger, "_zt_logfile_path", file)
        return file
    except Exception:
        return ""


class Zitifenlei(_PluginBase):
    # ─── 插件元信息 ───────────────────────────────────────
    plugin_name = "字体分类管家"
    plugin_desc = "字体归档整理与 ASS 字幕字体检查插件：扫描/上传字体到字体库，检查字幕缺失字体。"
    plugin_icon = "https://raw.githubusercontent.com/LXT-A-X/MoviePilot-Plugins/main/icons/zitifenlei.png"
    plugin_version = "1.2.19"
    plugin_author = "LXT-A-X"
    author_url = "https://github.com/LXT-A-X/MoviePilot-Plugins"
    plugin_config_prefix = "zitifenlei_"
    plugin_order = 30
    auth_level = 1

    # ─── 运行时状态 ───────────────────────────────────────
    _enabled = False
    _config: Dict[str, Any] = {}
    _db: Optional[FontDB] = None
    _db_path: Optional[Path] = None
    _tmp_dir: Optional[Path] = None
    _watcher_observers: Optional[List[Any]] = None
    _lock = threading.RLock()
    # assfonts 索引（fonts.json）键集缓存签名：(mtime_ns, size, lib_dir) -> 归一化键集
    _index_font_cache: Optional[Tuple[tuple, set]] = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._config = dict(_DEFAULT_CONFIG)
        # watchdog 观察者列表：事件驱动 Observer + 兼容轮询 PollingObserver（双保险）
        self._watcher_observers: List[Any] = []
        # 检查页「缺失字体修复」暂存的上传：tmp_path -> {path, file_name, name, family, vendor, matched}
        # 重启后这些文件由 _cleanup_tmp 视为孤儿清理，无需持久化
        self._missing_uploads: Dict[str, Any] = {}
        # 入库（TransferComplete）字幕扫描：剧根 key -> 本次新增字幕绝对路径列表；
        # 计时器聚合「等入库完毕再扫」，多次事件按 key 合并去重
        # key 优先用 tmdbid，缺失时退化为 title/目录串
        self._pending_shows: Dict[str, List[str]] = {}
        self._show_timers: Dict[str, threading.Timer] = {}
        # 秒：聚合窗口——连续 30s 无该剧新入库事件后才视为整部入库完毕，再统一扫描（滑动重置：有新事件就重新倒计时）
        self._ass_finalize_delay = 30
        # 目录轮询兜底：watchdog 缺失或事件漏发时，定时扫描目录保证「放进去能处理」
        self._poll_thread: Optional[threading.Thread] = None
        self._poll_stop: Optional[threading.Event] = None
        # watchdog 正常时 10 分钟兜底；未安装/失败时 60 秒近实时轮询
        self._poll_interval = 600 if _HAS_WATCHDOG else 60
        # watchdog 事件防抖：path -> Timer（同一路径 2s 内合并，待文件写入完成再处理）
        self._watch_timers: Dict[str, threading.Timer] = {}
        # 已处理源文件防抖：resolved path -> 处理时间戳。事件驱动 Observer 与轮询 PollingObserver
        # 会对同一文件各触发一次，靠这里在 60s 窗口内去重，避免「一份文件归档两份/建两条记录」
        self._processed_recent: Dict[str, float] = {}
        # 全量检查/扫描互斥锁：前端按钮在运行中禁用之外，后端再兜底挡住并发触发，
        # 避免两个请求同时 copy/写库产生竞态（重复触发直接返回「正在运行」）
        self._scan_lock = threading.RLock()
        # 优雅停止标志：stop_service 先置位，运行中的扫描/检查/子集化把「当前条目」完整
        # 处理完（copy+写库）再退出，剩余的条目不再处理，避免「文件在库、记录缺失」半截态
        self._stopping = False
        # 实时监控通知聚合缓冲：连续放入的字体/字幕在 short 窗口内合并成一条归类通知，
        # 避免「放 5 个字体发 5 条通知」的刷屏。窗口内有新事件则滑动重置，到期统一发送。
        self._notify_agg: Dict[str, Any] = {
            "fonts": [],  # 已自动归档的文件名
            "fonts_pending": [],  # 目录自动收集关闭时进入「待确认」的字体名（未归档）
            "subs_missing": [],  # {"name", "count", "fonts": 前几个缺失字体名}
            "subs_subset": [],  # 已子集化字幕文件名
            "subs_ok": [],  # 字体齐全字幕文件名
            "timer": None,
        }
        self._notify_agg_delay = 6  # 聚合窗口（秒）
        # 自动归档后的 assfonts 索引重建：脏标记 + 延迟聚合定时器（防批量归档反复重建）
        self._index_dirty = False
        self._index_rebuild_timer: Optional[threading.Timer] = None

    # ─── 生命周期 ────────────────────────────────────────
    def get_state(self) -> bool:
        """获取插件启用状态。"""
        return self._enabled

    def init_plugin(self, config: Optional[Dict[str, Any]] = None) -> None:
        """插件初始化：读取配置、初始化数据库与临时目录。

        对齐 subscribeassistantenhanced 范式：
        - 宿主传入完整配置时，宿主配置为权威，同时同步写入 SQLite 镜像（兜底恢复用）；
        - 宿主未传配置（异常/旧版本场景）时，用 SQLite 镜像兜底恢复。
        """
        try:
            _ensure_plugin_logfile()
        except Exception:
            pass
        try:
            data_path = self.get_data_path()
            Path(data_path).mkdir(parents=True, exist_ok=True)
            self._db_path = Path(data_path) / "fonts.db"
            self._tmp_dir = Path(data_path) / "tmp"
            Path(self._tmp_dir).mkdir(parents=True, exist_ok=True)
            # assfonts 字体索引目录（fonts.json 落在这里，不污染字体库目录）
            self._assfonts_idx = Path(data_path) / "assfonts_idx"
            Path(self._assfonts_idx).mkdir(parents=True, exist_ok=True)
            self._db = FontDB(self._db_path)
        except Exception as err:
            _logger.error("字体分类管家数据库初始化失败: %s", err)

        with self._lock:
            if config:
                # 宿主配置为权威（原生保存协议 PUT 后宿主会带上完整配置重新 init_plugin）
                merged = {**dict(_DEFAULT_CONFIG), **dict(config)}
                # 老配置迁移：宿主没有「是否启用监控」总开关时，用旧的 auto_monitor/auto_check 合并推导
                if "monitor_enabled" not in (config or {}):
                    merged["monitor_enabled"] = bool(merged.get("auto_monitor")) or bool(merged.get("auto_check"))
                self._config = merged
                # 同步镜像：镜像始终等于最近一次宿主传进来的完整配置，重启/重载兜底恢复
                if self._db:
                    try:
                        self._db.save_full_config(self._config)
                    except Exception:
                        pass
            else:
                # 宿主未传配置：用 SQLite 镜像兜底恢复，避免目录等设置丢失
                saved_cfg = self._db.get_full_config() if self._db else None
                if saved_cfg:
                    merged = {**dict(_DEFAULT_CONFIG), **saved_cfg}
                    if "monitor_enabled" not in (saved_cfg or {}):
                        merged["monitor_enabled"] = bool(merged.get("auto_monitor")) or bool(merged.get("auto_check"))
                    self._config = merged

            try:
                if not self._db:
                    data_path = self.get_data_path()
                    Path(data_path).mkdir(parents=True, exist_ok=True)
                    self._db = FontDB(Path(data_path) / "fonts.db")
                # 插件总开关：以宿主传入配置为准（原生保存协议下 enabled 就是普通配置项）
                cfg_enabled = self._config.get("enabled")
                if cfg_enabled is None:
                    try:
                        cfg_enabled = bool(self._db.get_setting("enabled", True))
                    except Exception:
                        cfg_enabled = True
                self._enabled = bool(cfg_enabled)
                try:
                    self._db.set_setting("enabled", self._enabled)
                except Exception:
                    pass
                self._db.add_log("插件已初始化", "info")
                # 记录插件日志文件位置（系统日志页选择 zitifenlei 即可查看）
                try:
                    _logf = _ensure_plugin_logfile()
                    if _logf:
                        self._db.add_log(f"插件日志文件: {_logf}", "info")
                except Exception:
                    pass
                self._start_watcher()
                # 清理临时目录中的孤儿文件（未被待确认/字幕记录引用的上传缓存）
                self._cleanup_tmp()
            except Exception as err:
                _logger.error("字体分类管家初始化失败: %s", err)
                self._enabled = False

    def stop_service(self) -> None:
        """停止后台服务：停监控、清理孤儿临时文件、关闭数据库"""
        # 优雅停止：先立档，运行中的扫描/子集化把当前条写完、剩余不再处理
        self._stopping = True
        self._stop_watcher()
        self._stop_polling()
        # 等待运行中的全量扫描/检查/子集化把当前条目完整写完（copy+写库完成才放锁），
        # 期间不关数据库，保证「文件入库 + 记录落库」原子成立；超时兜底强制继续
        self._wait_scan_drain(60)
        # 取消未到期的入库扫描聚合计时器
        with self._lock:
            for t in self._show_timers.values():
                try:
                    t.cancel()
                except Exception:
                    pass
            self._show_timers.clear()
            self._pending_shows.clear()
            # 取消未发送的通知聚合计时器并清空缓冲，避免旧实例残留发通知
            try:
                agg_timer = self._notify_agg.get("timer")
                if agg_timer:
                    agg_timer.cancel()
            except Exception:
                pass
            self._notify_agg["timer"] = None
            self._notify_agg["fonts"] = []
            self._notify_agg["fonts_pending"] = []
            self._notify_agg["subs_missing"] = []
            self._notify_agg["subs_subset"] = []
            self._notify_agg["subs_ok"] = []
        # 取消未到期的自动归档索引重建定时器
        try:
            if self._index_rebuild_timer:
                self._index_rebuild_timer.cancel()
                self._index_rebuild_timer = None
        except Exception:
            pass
        self._index_dirty = False
        self._enabled = False
        # 清理未被记录引用的临时文件（已入库/已提交的残留上传缓存及时释放磁盘）
        self._cleanup_tmp()
        if self._db:
            try:
                self._db.add_log("插件已停止", "info")
                self._db.close()
            except Exception:
                pass
            self._db = None

    def _wait_scan_drain(self, timeout: float = 60.0) -> None:
        """等待运行中的扫描/检查/子集化排空（当前条目已完整处理、释放互斥锁）。

        停插件时调用：_stopping 已置位 → 运行线程处理完当前条即退出并释放 _scan_lock，
        这里等到锁可获取即视为排空完成，随后才关库，杜绝「文件进了库、记录没写进」。
        """
        try:
            import time as _time

            deadline = _time.time() + timeout
            while _time.time() < deadline:
                if self._scan_lock.acquire(blocking=False):
                    self._scan_lock.release()
                    return
                _time.sleep(0.2)
            _logger.warning("插件停止等待扫描排空超时（%ss），强制继续关闭", int(timeout))
        except Exception:
            pass

    def _cleanup_tmp(self) -> None:
        """清理临时目录中未被任何记录引用的孤儿文件。

        被 pending_fonts / ass_files 的 file_path 引用的文件必须保留
        （已入库排队或字幕待检查会继续使用），其余视为残留上传，直接删除。
        """
        try:
            if not self._tmp_dir or not Path(self._tmp_dir).exists():
                return
            referenced = set()
            try:
                if self._db:
                    for r in self._db.query("SELECT file_path FROM pending_fonts WHERE file_path != ''"):
                        if r.get("file_path"):
                            referenced.add(str(Path(r["file_path"]).resolve()))
                    for r in self._db.query("SELECT file_path FROM ass_files WHERE file_path != ''"):
                        if r.get("file_path"):
                            referenced.add(str(Path(r["file_path"]).resolve()))
                    # 子集化重试保留的源文件（缺字体/失败，status=missing/error）不能被当孤儿清理
                    for r in self._db.query(
                        "SELECT file_path FROM subset_records WHERE status IN ('missing', 'error') AND file_path != ''"
                    ):
                        if r.get("file_path"):
                            referenced.add(str(Path(r["file_path"]).resolve()))
            except Exception:
                pass
            removed = 0
            for f in Path(self._tmp_dir).iterdir():
                if not f.is_file():
                    continue
                if str(f.resolve()) not in referenced:
                    try:
                        f.unlink()
                        removed += 1
                    except Exception:
                        pass
            # 子集字体夹（<stem>_subsetted）孤儿目录清理：对应源字幕已不存在时删除
            # （字体已内嵌进成品字幕，夹子仅是 assfonts 的备份，默认不同步输出目录）
            for d in Path(self._tmp_dir).iterdir():
                if not d.is_dir() or not d.name.endswith("_subsetted"):
                    continue
                src = d.parent / (d.name[: -len("_subsetted")] + ".ass")
                if str(src.resolve()) not in referenced:
                    try:
                        shutil.rmtree(d, ignore_errors=True)
                        removed += 1
                    except Exception:
                        pass
            if removed:
                _logger.debug("字体分类管家清理 %d 个临时文件", removed)
        except Exception as err:
            _logger.debug("临时目录清理跳过: %s", err)

    # ─── 渲染模式：Vue 联邦 ──────────────────────────────
    @staticmethod
    def get_render_mode() -> Tuple[str, str]:
        return "vue", "dist/assets"

    @staticmethod
    def get_page() -> Optional[List[dict]]:
        return None

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        """返回宿主配置接口的 model：默认值合并当前运行时配置（对齐 subscribeplus 范式）。"""
        return None, {**dict(_DEFAULT_CONFIG), **dict(self._config)}

    # ─── 定时服务 ────────────────────────────────────────
    def get_service(self) -> List[Dict[str, Any]]:
        # 只做增量监控：watchdog 双观察者（事件驱动 Observer + 兼容轮询 PollingObserver）
        # 实时处理新增/变动文件，不注册定时全量扫描——6 小时兜底会把监控目录存量文件整体重扫，
        # 复制模式下同名字体反复归档出 xxx-2/xxx-3 副本堆积（已由 _archive_font_file 同名去重兜住）。
        # watchdog 完全缺失时的 60 秒轮询兜底（_start_polling）同样幂等，不会重复归档/重复建记录。
        return []

    def get_resource_or_config(self, key: str) -> Any:
        """读取配置（兼容运行时更新）：宿主配置有该键才用宿主值，
        缺失时回退运行时 _config（已按默认值合并），避免旧配置缺键时把默认值吞成 None。"""
        try:
            cfg = self.get_config()
            if isinstance(cfg, dict) and key in cfg:
                return cfg.get(key)
        except Exception:
            pass
        return self._config.get(key)

    def __auto_monitor_scan(self) -> None:
        """自动监控：扫描输入目录中的字体并自动归档"""
        # 「是否自动执行监控结果」关闭：监控字体改走「待确认」，由实时监控逐文件登记，
        # 轮询兜底不再整体重扫监控目录（避免每 60s rglob 整目录 + 「归档 N 个」计数虚高）
        if self.get_resource_or_config("auto_collect") is False:
            return
        with self._lock:
            try:
                input_dir = self.get_resource_or_config("input_dir") or ""
                if not input_dir or not Path(input_dir).is_dir():
                    return
                added = self._archive_from_dir(Path(input_dir), source="auto")
                if added:
                    self._db.add_log(f"自动监控：归档 {added} 个字体", "info")
                    # 轮询兜底归档后同样自动重建 assfonts 索引
                    self._schedule_index_rebuild()
                    if self.get_resource_or_config("notify_enabled"):
                        self._notify("字体分类管家：自动归档完成", f"✅ 自动归档完成\n已归档 {added} 个字体")
            except Exception as err:
                self._db.add_log(f"自动监控失败: {err}", "error")

    def __auto_ass_check(self) -> None:
        """自动检查：扫描字幕目录中的 ASS 文件"""
        with self._lock:
            try:
                ass_dir = self.get_resource_or_config("ass_dir") or ""
                if not ass_dir or not Path(ass_dir).is_dir():
                    return
                count = 0
                for f in Path(ass_dir).iterdir():
                    if f.is_file() and is_ass_file(f.name):
                        self._check_ass_file(f, source="auto")
                        count += 1
                if count:
                    self._db.add_log(f"自动ASS检查：检查 {count} 个字幕文件", "info")
                    if self.get_resource_or_config("notify_enabled"):
                        self._notify("字体分类管家：自动ASS检查完成", f"✅ 自动ASS检查完成\n已检查 {count} 个字幕文件")
            except Exception as err:
                self._db.add_log(f"自动ASS检查失败: {err}", "error")

    # ─── 目录实时监控（watchdog）────────────────────────
    class _FontWatchHandler(FileSystemEventHandler):
        """watchdog 事件处理器：新文件 → 字体自动归档 / 字幕自动检查

        同时监听 created / modified / moved：
        - created：文件首次出现（复制/上传的第一次事件）；
        - modified：写入过程（大文件可能多次触发，配合防抖等写完后处理）；
        - moved：覆盖 created+改名，兼容 .part / 临时名改回正名的复制管线。
        """

        def __init__(self, plugin: "Zitifenlei") -> None:
            self._plugin = plugin

        def on_created(self, event: Any) -> None:
            if event.is_directory:
                return
            self._plugin._schedule_watch_handle(str(event.src_path))

        def on_modified(self, event: Any) -> None:
            if event.is_directory:
                return
            self._plugin._schedule_watch_handle(str(event.src_path))

        def on_moved(self, event: Any) -> None:
            dest = getattr(event, "dest_path", None)
            if not dest or event.is_directory:
                return
            self._plugin._schedule_watch_handle(str(dest))

    def _schedule_watch_handle(self, path: str) -> None:
        """watchdog 事件统一防抖：同一路径 2 秒内重复事件重置计时器，
        文件写入/改名完成后才真正处理，避免读到半文件或漏掉改名后的正名文件。
        """
        if not self._enabled or self._db is None:
            return
        with self._lock:
            timer = self._watch_timers.get(path)
            if timer:
                timer.cancel()
            timer = threading.Timer(2.0, self._on_watch_event, args=(path,))
            timer.daemon = True
            timer.start()
            self._watch_timers[path] = timer

    def _cancel_watch_timers(self) -> None:
        with self._lock:
            for t in self._watch_timers.values():
                try:
                    t.cancel()
                except Exception:
                    pass
            self._watch_timers.clear()

    def _start_watcher(self) -> None:
        """启动实时监控：三级降级——Observer（事件驱动）→ PollingObserver（watchdog 内置轮询，兼容
        SMB/远程共享目录）→ 自写目录轮询（watchdog 包不可用时的最后兜底），保证任何环境都不漏事件。

        参考短剧监控插件的做法：Observer 启动失败（inotify 限额等）或目录为挂载共享时，
        使用 PollingObserver(timeout=10) 以轮询驱动同样的事件回调，事件接口完全一致。
        启动状态一律写入仪表盘日志，便于排查「放文件没反应」。
        """
        self._stop_watcher()
        # 先停掉旧轮询：配置更新（目录/开关变化）后按新配置重建
        self._stop_polling()
        if not self._enabled or self._db is None:
            return
        monitor_enabled = bool(self.get_resource_or_config("monitor_enabled"))
        if not monitor_enabled:
            self._db.add_log(
                "目录监控未启动：「是否启用监控」未开启（总开关，统一控制字体监控目录 / ASS字幕目录监控 / ASS目录监控子集）",
                "info",
            )
            return
        # 配置预检：开关开了但对应目标目录缺失 → 放文件也不会真正处理，提前暴露
        lib_dir_cfg = self.get_resource_or_config("lib_dir") or ""
        ass_dir_cfg = self.get_resource_or_config("ass_dir") or ""
        subset_dir_cfg = self.get_resource_or_config("subset_dir") or ""
        if monitor_enabled and not lib_dir_cfg:
            self._db.add_log(
                "「是否启用监控」已开启但未配置「字体库目录」：监控到的字体将无法直接归档，请到设置 → 目录配置补上字体库目录",
                "warning",
            )
        if monitor_enabled and not ass_dir_cfg:
            self._db.add_log(
                "「是否启用监控」已开启，但「ASS字幕目录监控」未配置：字幕放入后无法自动检查", "warning"
            )
        if subset_dir_cfg and not Path(subset_dir_cfg).is_dir():
            self._db.add_log(
                f"已配置「ASS目录监控子集」但目录不可达（{subset_dir_cfg}）：放入的字幕无法自动子集化", "warning"
            )
        input_dir = self.get_resource_or_config("input_dir") or ""
        ass_dir = self.get_resource_or_config("ass_dir") or ""
        paths: List[Path] = []
        if input_dir and Path(input_dir).is_dir():
            paths.append(Path(input_dir))
        if ass_dir and Path(ass_dir).is_dir():
            paths.append(Path(ass_dir))
        if subset_dir_cfg and Path(subset_dir_cfg).is_dir():
            paths.append(Path(subset_dir_cfg))
        if not paths:
            self._db.add_log(
                f"目录监控未启动：监控目录不可达（input_dir={input_dir or '(空)'}，ass_dir={ass_dir or '(空)'}）",
                "warning",
            )
            return
        if _HAS_WATCHDOG:
            handler = self._FontWatchHandler(self)
            # 1) 事件驱动模式（本地目录秒级）
            try:
                obs_evt = Observer(timeout=10)
                for p in paths:
                    obs_evt.schedule(handler, str(p), recursive=True)
                obs_evt.daemon = True
                obs_evt.start()
                self._watcher_observers.append(obs_evt)
                self._db.add_log(f"实时监控已启动: {', '.join(str(p) for p in paths)}", "info")
            except Exception as err:
                _logger.warning("watchdog Observer 启动失败，仍由兼容轮询兜底: %s", err)
                if "inotify" in str(err).lower() or "watch" in str(err).lower():
                    self._db.add_log(
                        "实时监控 inotify 限额不足：请在宿主机执行 "
                        "echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.conf && sudo sysctl -p 后重启。",
                        "warning",
                    )
            # 2) 兼容轮询观察者（watchdog 内置 PollingObserver）：始终启用。
            # inotify 对 SMB/网络挂载/部分 NAS 文件系统事件不可靠（启动成功但无事件），
            # PollingObserver 按目录变化发事件（空闲零开销），双保险保证任何环境都能收到
            if PollingObserver is not None:
                try:
                    obs_poll = PollingObserver(timeout=5)
                    for p in paths:
                        obs_poll.schedule(handler, str(p), recursive=True)
                    obs_poll.daemon = True
                    obs_poll.start()
                    self._watcher_observers.append(obs_poll)
                    self._db.add_log(
                        "已启用兼容轮询兜底（约 5 秒，覆盖网络挂载/事件失效场景）", "info"
                    )
                except Exception as err:
                    _logger.warning("PollingObserver 启动失败，由自写轮询兜底: %s", err)
        else:
            # watchdog 包缺失（requirements.txt 未自动安装）：事件驱动不可用，只靠自写轮询（高频）
            self._db.add_log("watchdog 未安装（requirements.txt 未自动安装）：实时监控改为 60 秒轮询兜底", "warning")
        # 仅有当 watchdog 观察者全部启动失败/缺失时才用自写 60 秒轮询兜底；
        # 正常时 PollingObserver 已覆盖（变化驱动，无「扫完又扫」）
        if not self._watcher_observers:
            self._poll_interval = 60
            self._start_polling()

    def _stop_watcher(self) -> None:
        for obs in (self._watcher_observers or []):
            try:
                obs.stop()
            except Exception:
                pass
            try:
                obs.join(1)
            except Exception:
                pass
        self._watcher_observers = []
        self._cancel_watch_timers()

    # ─── 目录轮询兜底（不依赖 watchdog）──────────────────
    def _start_polling(self) -> None:
        """启动目录轮询线程：watchdog 未装/启动失败时每 60s 扫描一次，保证「放进去能处理」。"""
        self._stop_polling()
        if not (
            self._enabled and self.get_resource_or_config("monitor_enabled")
        ):
            return
        self._poll_stop = threading.Event()
        t = threading.Thread(target=self._poll_loop, name="zt-poll", daemon=True)
        t.start()
        self._poll_thread = t
        if self._db is not None:
            try:
                self._db.add_log(
                    f"目录轮询兜底已启动：每 {self._poll_interval} 秒扫描一次监控目录", "info"
                )
            except Exception:
                pass

    def _stop_polling(self) -> None:
        t = self._poll_thread
        self._poll_thread = None
        if t is not None:
            try:
                if self._poll_stop is not None:
                    self._poll_stop.set()
            except Exception:
                pass
            try:
                t.join(2)
            except Exception:
                pass
        self._poll_stop = None

    def _poll_loop(self) -> None:
        while True:
            try:
                if self._poll_stop is None:
                    return
                if self._poll_stop.wait(self._poll_interval):
                    return  # 停止信号
                if not self._enabled or self._db is None:
                    return
                if self.get_resource_or_config("monitor_enabled"):
                    self.__auto_monitor_scan()
                    self.__auto_ass_check()
            except Exception:
                _logger.debug("目录轮询异常跳过", exc_info=True)

    def _on_watch_event(self, path: str) -> None:
        """单文件事件：字体 → 自动归档；字幕 → 自动检查"""
        if not self._enabled or self._db is None:
            return
        # 过滤 NAS 系统目录与回收站（参考实时软连接插件）：@eaDir / #recycle / 隐藏文件等
        if self._is_system_hidden_path(Path(path)):
            return
        with self._lock:
            try:
                p = Path(path)
                if not p.is_file():
                    return
                # 双观察者（Observer + PollingObserver）会对同一文件各触发一次：
                # 同一源文件 60 秒内已处理过则跳过，避免重复归档 / 生成重复检查记录
                key = str(p.resolve())
                now = time.time()
                last = self._processed_recent.get(key)
                if last is not None and now - last < 60.0:
                    return
                if is_font_file(p.name):
                    # 归档函数内部自带成功/失败日志，此处不再重复记录；
                    # 返回值：>0=已归档，-1=进入待确认（目录自动收集关闭），None=跳过
                    font_id = self._archive_font_file(p, source="auto")
                    if font_id and font_id > 0:
                        # 归档结果进通知聚合缓冲：同一批连续放入的文件合并成一条归类通知
                        with self._lock:
                            self._notify_agg["fonts"].append(p.name)
                        self._queue_agg_notify()
                        # 归档成功自动重建 assfonts 索引（延迟聚合，防批量归档反复重建）
                        self._schedule_index_rebuild()
                    elif font_id == -1:
                        # 只进待确认（未归档）：走独立「待确认」通知，不再误报「已自动归档」
                        with self._lock:
                            self._notify_agg["fonts_pending"].append(p.name)
                        self._queue_agg_notify()
                elif is_ass_file(p.name):
                    subset_dir_cfg = self.get_resource_or_config("subset_dir") or ""
                    if subset_dir_cfg and _path_within(p, Path(subset_dir_cfg)):
                        # 「ASS目录监控子集」：放入即进入子集化流程——
                        # 「目录自动收集」开 → 立即后台自动子集化；关 → 进子集化页「待处理」等手动
                        self._schedule_subset_watch(p)
                        self._db.add_log(f"子集监控: {p.name} → 已进入子集化流程", "info")
                        self._processed_recent[key] = now
                        return
                    result = self._check_ass_file(p, source="auto")
                    if result:
                        self._db.add_log(
                            f"实时检查字幕: {p.name} → {result['status_text']}",
                            "warning" if result["missing_count"] else "info",
                        )
                        missing = result.get("missing_fonts") or []
                        if missing:
                            with self._lock:
                                self._notify_agg["subs_missing"].append(
                                    {
                                        "name": p.name,
                                        "count": int(result.get("missing_count") or len(missing)),
                                        "fonts": missing,
                                    }
                                )
                            self._queue_agg_notify()
                        elif result.get("subsetted"):
                            # 已内嵌（子集化）字幕自带字体，不依赖字体库
                            with self._lock:
                                self._notify_agg["subs_subset"].append(p.name)
                            self._queue_agg_notify()
                        elif result.get("status") != "pending":
                            # 待检查状态（目录自动收集关闭时的登记）不通知「字体齐全」，避免误导
                            with self._lock:
                                self._notify_agg["subs_ok"].append(p.name)
                            self._queue_agg_notify()
                        # 子集化自动处理（设置 auto_subset 开启时）：跟随「目录自动收集」开关——
                        # 开 → 立即后台自动子集化；关 → 进子集化页「待处理」等手动
                        if self.get_resource_or_config("auto_subset"):
                            self._schedule_subset_watch(p)
                # 标记已处理（含非字体/字幕文件，避免后续事件空转）
                self._processed_recent[key] = now
                # 限制增长：超过阈值时清理 5 分钟前的旧条目
                if len(self._processed_recent) > 2000:
                    expire = now - 300.0
                    for k in [kk for kk, tt in self._processed_recent.items() if tt < expire]:
                        self._processed_recent.pop(k, None)
            except Exception as err:
                self._db.add_log(f"监控处理失败 {path}: {err}", "error")
            finally:
                # 本次处理结束，移除防抖条目（RLock 可重入）
                self._watch_timers.pop(path, None)

    def _queue_auto_pending(self, file_path: Path, source: str) -> Optional[int]:
        """监控到的字体进「待确认」列表（目录自动收集关闭时的行为，与手动上传一致）"""
        if self._db is None:
            return None
        try:
            if self._db.query_one(
                "SELECT id FROM pending_fonts WHERE file_path = ?", (str(file_path),)
            ):
                return None
            if self._db.count_fonts_by_path(str(file_path)):
                return None
            scan_mode = self.get_resource_or_config("scan_mode") or "internal"
            try:
                meta = parse_font_metadata(
                    file_path, scan_mode=scan_mode, filename_hint=file_path.stem
                )
            except Exception:
                meta = {"name": file_path.stem, "family": file_path.stem, "vendor": "未知厂商", "designer": ""}
            self._db.add_pending(
                {
                    "file_name": file_path.name,
                    "file_path": str(file_path),
                    "name": meta.get("name", "") or file_path.stem,
                    "family": meta.get("family", "") or file_path.stem,
                    "vendor": meta.get("vendor", "未知厂商"),
                    "designer": meta.get("designer", ""),
                    "file_size": int(file_path.stat().st_size) if file_path.exists() else 0,
                }
            )
            self._db.add_log(
                f"监控到新字体 {file_path.name}，已加入「待确认」（目录自动收集已关闭，等待一键整理）",
                "info",
            )
            return -1  # 注意：-1 仅表示「已进待确认、未归档」，不是归档成功 ID；调用方必须按 >0 判断真正归档
        except Exception as err:
            if self._db is not None:
                try:
                    self._db.add_log(f"监控字体 {file_path.name} 加入待确认失败: {err}", "error")
                except Exception:
                    pass
            return None

    def _archive_font_file(self, file_path: Path, source: str = "auto") -> Optional[int]:
        """自动归档单个字体（监控发现）：直接写入字体库（不经待确认）。

        「目录自动收集」关闭时：监控到的字体改进「待确认」，等待一键整理。
        未配置「字体库目录」时不静默：写明确警示日志。
        """
        # 收集开关：关闭 → 只收下待确认，不自动归档
        if self.get_resource_or_config("auto_collect") is False:
            return self._queue_auto_pending(file_path, source)
        lib_dir = self.get_resource_or_config("lib_dir") or ""
        if not lib_dir:
            if self._db is not None:
                try:
                    self._db.add_log(
                        f"自动归档跳过 {file_path.name}：未配置「字体库目录」（设置 → 目录配置），"
                        "监控到的字体将直接归档进字体库，请先配置库目录",
                        "warning",
                    )
                except Exception:
                    pass
            return None
        # 已在字体库目录内/已收录过的文件直接跳过，避免重复归档
        try:
            if _path_within(file_path, Path(lib_dir)):
                return None
            if self._db.count_fonts_by_path(str(file_path)):
                # 记录源文件已处理（仪表盘「待整理」排除该文件）
                self._db.mark_font_processed(str(file_path))
                return None
        except Exception:
            pass
        scan_mode = self.get_resource_or_config("scan_mode") or "internal"
        try:
            meta = parse_font_metadata(file_path, scan_mode=scan_mode, filename_hint=file_path.stem)
        except Exception:
            meta = {"name": file_path.stem, "family": file_path.stem, "vendor": "未知厂商", "designer": ""}
        archive_mode = self.get_resource_or_config("archive_mode") or "copy"
        try:
            dest_dir = Path(lib_dir) / str(meta.get("vendor", "未知厂商"))
            dest_dir.mkdir(parents=True, exist_ok=True)
            base = str(meta.get("name") or file_path.stem)
            # 「利用字体内部名称命名」开启时：用字体内部 PostScript 名（nameID 6），
            # 读不到则回退文件名（避免循环嵌套 TTFont 开销，仅命名用，元数据仍走 parse_font_metadata）
            if self.get_resource_or_config("font_name_internal"):
                try:
                    internal_name = get_font_psname(file_path)
                    if internal_name:
                        base = internal_name
                except Exception:
                    pass
            # 按格式分子文件夹归档：字体库/厂商/格式/基础名.后缀（同字体不同格式共存，目录清晰）
            fmt_dir = dest_dir / _font_subdir_name(file_path.suffix)
            existing = _dest_exists_recursive(dest_dir, base, file_path.suffix)
            if existing:
                # 字体库已存在同名同后缀字体（含旧平铺布局与格式子文件夹）：
                # 跳过本次归档（不再生成 -2/-3 副本，保证轮询/兜底全量扫描存量文件时幂等）
                self._db.add_log(f"跳过 {file_path.name}：字体库已存在 {existing.name}", "info")
                # 「移动原文件」模式 + 开关开启：删除监控目录残留的重复源文件，
                # 避免 move 模式下判重跳过导致源文件一直堆在监控目录；复制模式不受影响
                if archive_mode == "move" and self.get_resource_or_config("move_delete_duplicate"):
                    try:
                        if file_path.is_file():
                            file_path.unlink()
                            self._db.add_log(
                                f"已删除监控目录残留的重复源文件 {file_path.name}（字体库已有 {existing.name}）",
                                "info",
                            )
                    except Exception as err:
                        self._db.add_log(f"删除重复源文件失败 {file_path.name}: {err}", "warning")
                # 源文件虽然同源已入库（仅更名），同样算已处理，「待整理」不再计入
                self._db.mark_font_processed(str(file_path))
                return None
            try:
                fmt_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            dest = fmt_dir / f"{base}{file_path.suffix}"
            if archive_mode == "move":
                shutil.move(str(file_path), str(dest))
            else:
                shutil.copy2(str(file_path), str(dest))
        except Exception as err:
            self._db.add_log(f"自动归档失败 {file_path.name}: {err}", "error")
            return None
        try:
            font_id = self._db.add_font(
                {
                    "name": meta.get("name", ""),
                    "family": meta.get("family", ""),
                    "vendor": meta.get("vendor", "未知厂商"),
                    "designer": meta.get("designer", ""),
                    "file_name": dest.name,
                    "file_size": dest.stat().st_size if dest.exists() else 0,
                    "status": "已归档",
                    "source": source,
                    "file_path": str(dest),
                }
            )
            # 记录源文件已处理（复制模式下源文件留存字体监控目录，「待整理」不再计入）
            self._db.mark_font_processed(str(file_path))
            self._db.add_log(f"自动归档: {dest.name}", "info")
            # 归档成功：标记 assfonts 索引需要重建（由调用方调度延迟聚合重建）
            self._index_dirty = True
            return font_id
        except Exception as err:
            # 写库失败：回滚刚归档的文件，不留「文件进库、记录缺失」的孤儿
            # （copy 模式删掉副本；move 模式源已被移走，搬回原位）
            try:
                if dest.exists():
                    if archive_mode == "move" and Path(str(file_path)).resolve() != dest.resolve():
                        shutil.move(str(dest), str(file_path))
                        self._db.add_log(f"自动归档回滚: {dest.name} 已移回 {file_path.name}", "warning")
                    else:
                        dest.unlink(missing_ok=True)
                        self._db.add_log(f"自动归档回滚: 已删除副本 {dest.name}", "warning")
            except Exception:
                pass
            self._db.add_log(f"写库失败 {dest.name}: {err}", "error")
            return None

    def _archive_from_dir(self, directory: Path, source: str = "auto") -> int:
        """批量自动归档目录内字体（定时兜底）：直接写入字体库，不经过待确认"""
        added = 0
        if not directory.is_dir():
            return added
        for f in sorted(directory.rglob("*")):
            # 优雅停止：停插件时当前条处理完就不再继续（_stopping 被 stop_service 置位）
            try:
                if self._stopping or not self._enabled:
                    break
            except Exception:
                pass
            if self._is_system_hidden_path(f):
                continue
            if not f.is_file() or not is_font_file(f.name):
                continue
            # 只统计真正归档成功的（返回值 >0）；-1=进待确认、None=跳过，均不计入「归档 N 个」
            if (self._archive_font_file(f, source=source) or 0) > 0:
                added += 1
        return added

    # ─── 内部工具 ────────────────────────────────────────
    @staticmethod
    def _is_system_hidden_path(p: Path) -> bool:
        """路径是否命中 NAS 系统目录/回收站/隐藏段（群晖 @eaDir/@PleaseReadMe、威联通 @eaDir、#recycle）"""
        try:
            for part in p.parts:
                low = part.lower()
                if low in ("@eadir", "@justabit", "@pleasereadme", "#recycle", "@tmphds", "@sharebin"):
                    return True
                if part.startswith(".") and part not in (".", ".."):
                    return True
        except Exception:
            pass
        return False

    def _notify(self, title: str, text: str = "") -> bool:
        try:
            return self.post_message(title=title, text=text)
        except Exception:
            try:
                return self.post_message(title=title, text=text, mtype=None)
            except Exception:
                return False

    def _queue_agg_notify(self) -> None:
        """滑动重置通知聚合计时器：窗口内继续有新事件则推迟发送，

        连续放入的一批文件（如一次拖 5 个字体 + 几部字幕）合并成一条归类通知。
        """
        with self._lock:
            t = self._notify_agg.get("timer")
            if t:
                try:
                    t.cancel()
                except Exception:
                    pass
            t = threading.Timer(self._notify_agg_delay, self._flush_agg_notify)
            t.daemon = True
            t.start()
            self._notify_agg["timer"] = t

    def _flush_agg_notify(self) -> None:
        """聚合窗口到期：把缓冲内的归档/字幕检查结果归类成一条通知发送。

        分类：✅ 已自动归档 N 个字体 / ❌ 缺失字体的字幕（带缺的字体明细） /
        ✅ 已子集化字幕 / ✅ 字体齐全字幕。数量大时折叠显示（前几个 + 等 N 个），
        避免消息过长。
        """
        with self._lock:
            buf = self._notify_agg
            fonts = list(buf.get("fonts") or [])
            fonts_pending = list(buf.get("fonts_pending") or [])
            subs_missing = list(buf.get("subs_missing") or [])
            subs_subset = list(buf.get("subs_subset") or [])
            subs_ok = list(buf.get("subs_ok") or [])
            buf["fonts"] = []
            buf["fonts_pending"] = []
            buf["subs_missing"] = []
            buf["subs_subset"] = []
            buf["subs_ok"] = []
            buf["timer"] = None
        if not (fonts or fonts_pending or subs_missing or subs_subset or subs_ok):
            return
        if not self.get_resource_or_config("notify_enabled"):
            return
        # 字体与字幕分开通知：字体一条、字幕一条，不混在同一消息里
        if fonts:
            # 字体归档通知（仅字体）
            shown = fonts[:10]
            more = len(fonts) - len(shown)
            self._notify(
                "字体分类管家：自动归档",
                f"✅ 已自动归档 {len(fonts)} 个字体：{'、'.join(shown)}"
                + (f" 等 {more} 个" if more > 0 else ""),
            )
        # 目录自动收集关闭：监控到的字体只进「待确认」未归档，独立成条提示
        if fonts_pending:
            shown = fonts_pending[:10]
            more = len(fonts_pending) - len(shown)
            self._notify(
                "字体分类管家：新字体待确认",
                f"⏳ 已加入待确认 {len(fonts_pending)} 个字体，等待一键整理：{'、'.join(shown)}"
                + (f" 等 {more} 个" if more > 0 else ""),
            )
        if subs_missing or subs_subset or subs_ok:
            # 字幕检查通知（仅字幕，按缺失/子集化/齐全分类）
            lines: List[str] = []
            for m in subs_missing:
                first = m.get("fonts") or []
                detail = "、".join(first[:3])
                more = len(first) - 3
                lines.append(
                    f"❌ {m['name']} → 缺 {m['count']} 个字体"
                    + (f"（{detail}" + (f" 等 {more} 种" if more > 0 else "") + "）" if detail else "")
                )
            if subs_subset:
                shown = subs_subset[:10]
                more = len(subs_subset) - len(shown)
                lines.append(
                    f"✅ 已子集化（自带内嵌字体）{len(subs_subset)} 个：{'、'.join(shown)}"
                    + (f" 等 {more} 个" if more > 0 else "")
                )
            if subs_ok:
                shown = subs_ok[:10]
                more = len(subs_ok) - len(shown)
                lines.append(
                    f"✅ 字体齐全 {len(subs_ok)} 个：{'、'.join(shown)}"
                    + (f" 等 {more} 个" if more > 0 else "")
                )
            if subs_missing:
                lines.append("可在「检查页」上传缺失字体入库消除标记")
            self._notify("字体分类管家：字幕检查", "\n".join(lines))

    # ─── 子集化（assfonts）───────────────────────────────
    def _subset_binary(self) -> Optional[Path]:
        """插件自带 bin/assfonts 可执行文件路径（不存在返回 None）"""
        return af.get_binary(Path(__file__).resolve().parent)

    def _ensure_subset_index(self) -> bool:
        """确保 assfonts 字体索引存在（懒构建）。返回索引是否可用。"""
        try:
            if self._assfonts_idx is None:
                return False
            if (self._assfonts_idx / "fonts.json").is_file():
                return True
            binary = self._subset_binary()
            if not binary:
                return False
            lib_dir = self.get_resource_or_config("lib_dir") or ""
            if not lib_dir or not Path(lib_dir).is_dir():
                return False
            ok, msg = af.build_index(binary, [lib_dir], self._assfonts_idx)
            # 索引（重）构建完成后清键集缓存，新归档字体立即可被检查侧命中
            self._index_font_cache = None
            if ok:
                self._db.add_log(f"assfonts 字体索引已构建（{lib_dir}）", "info")
            else:
                self._db.add_log(f"assfonts 索引构建失败: {msg}", "error")
            return ok
        except Exception as err:
            if self._db is not None:
                try:
                    self._db.add_log(f"assfonts 索引检查失败: {err}", "error")
                except Exception:
                    pass
            return False

    def _index_font_keys(self) -> Optional[set]:
        """从 assfonts 索引（fonts.json）收集「字体库目录内」全部可用名字 → 归一化键集合。

        assfonts 索引保存 family / full name / PostScript name 三套名字（多键匹配），
        检查侧改用它能消除「full name / PS 名误报缺失」与 TTC 匹配问题；
        必须按 lib_dir 过滤（索引同时被 assfonts 灌入系统字体目录）。

        索引不可用（未构建 / 解析失败 / 未配置字体库目录）返回 None，
        调用方回退字体库记录（见 _lib_font_keys），并写一条诊断日志指明原因。
        （mtime_ns, size, lib_dir）签名缓存：索引文件未变不重读；个别网络挂载
        stat 失败时跳过缓存直接读文件，不退出。
        """
        lib_dir = self.get_resource_or_config("lib_dir") or ""
        if not lib_dir or not Path(lib_dir).is_dir() or self._assfonts_idx is None:
            self._diag_index_unavailable("lib_dir 未配置或目录不可达")
            return None
        try:
            fp = Path(self._assfonts_idx) / "fonts.json"
            if not fp.is_file():
                self._diag_index_unavailable("fonts.json 不存在（索引未构建）")
                return None
            sig = None
            cache = self._index_font_cache
            try:
                st = fp.stat()
                sig = (st.st_mtime_ns, st.st_size, lib_dir)
                if cache and cache[0] == sig:
                    return cache[1]
            except Exception:
                sig = None  # 无法 stat：跳过缓存，直接读文件
            data = af.load_index(self._assfonts_idx)
            if data is None:
                self._diag_index_unavailable("fonts.json 读取/解析失败")
                return None
            keys = {k for k in (normalize_font_key(x) for x in af.index_font_keys(data, lib_dir)) if k}
            if sig is not None:
                self._index_font_cache = (sig, keys)
            return keys
        except Exception as err:
            self._diag_index_unavailable(f"索引读取异常: {err}")
            return None

    def _diag_index_unavailable(self, reason: str) -> None:
        """索引不可用时落一条诊断日志（同一原因只记一次，避免列表接口每 30 秒轮询刷屏）"""
        try:
            key = "idx_unusable:" + reason
            if getattr(self, "_index_diag_last", None) == key:
                return
            self._index_diag_last = key
            if self._db is not None:
                self._db.add_log(
                    f"检查匹配基准回退字体库记录：{reason}（可在「子集化」页点「重建索引」）",
                    "warning",
                )
        except Exception:
            pass

    def _lib_font_keys(self) -> Tuple[set, str]:
        """检查侧「字体库有哪些字体」统一口径：返回 (归一化键集, 匹配来源)。

        索引可用 → (索引键集, "index")：与子集化共用同一份 assfonts fonts.json；
        索引不可用（未构建/读不到/库目录未配置）→ 回退字体库记录 family，
        (DB键集, "db")，保证旧环境检查功能不整体失效。
        """
        if self._db is None:
            return set(), "db"
        try:
            idx = self._index_font_keys()
            if idx is not None:
                return idx, "index"
        except Exception:
            pass
        try:
            fams = {normalize_font_key(x) for x in self._db.all_font_families()}
        except Exception:
            fams = set()
        return fams, "db"

    def _schedule_index_rebuild(self, delay: float = 5.0) -> None:
        """自动归档后延迟聚合重建 assfonts 索引：一次拖入多个字体时 5 秒窗口内合并为一次重建，
        避免逐文件重建拖慢监控；同时跳过已重建的重复调度。"""
        try:
            if not self._index_dirty:
                return
            timer = self._index_rebuild_timer
            if timer:
                try:
                    timer.cancel()
                except Exception:
                    pass
            timer = threading.Timer(delay, self._do_rebuild_index_async)
            timer.daemon = True
            timer.start()
            self._index_rebuild_timer = timer
        except Exception:
            pass

    def _do_rebuild_index_async(self) -> None:
        """索引延迟重建的后台执行：全量子集化运行中（_scan_lock 被占）则放弃本次，
        等下一批归档/轮询再触发；重建成功/失败都记日志，静默不打扰前台。"""
        try:
            self._index_rebuild_timer = None
            if not self._index_dirty:
                return
            if not self._scan_lock.acquire(blocking=False):
                return  # 全量子集化运行中：暂不重建，后续归档/轮询会再次触发
            try:
                self._index_dirty = False
                ok, msg = self._rebuild_subset_index_silent()
                if ok:
                    self._db.add_log("assfonts 字体索引已自动重建（自动归档后）", "info")
                else:
                    self._db.add_log(f"assfonts 索引自动重建失败: {msg}", "warning")
            finally:
                self._scan_lock.release()
        except Exception as err:
            try:
                if self._db is not None:
                    self._db.add_log(f"assfonts 索引自动重建异常: {err}", "warning")
            except Exception:
                pass

    @staticmethod
    def _extract_show_name(fname: str) -> str:
        """从字幕文件名提取「剧名」用于输出端子文件夹：取第一个分隔符（空格/-/·/_/括号等）
        之前的非空段；无分隔符时取去扩展名后的全名。
        如「葬送的芙莉莲 - S01E30 · WEB-DL · 1080p…」→「葬送的芙莉莲」，「你的名字.ass」→「你的名字」。"""
        stem = Path(str(fname or "")).stem
        parts = [p for p in re.split(r"[\s\-·_（）()\[\]]+", stem) if p.strip()]
        return parts[0].strip() if parts else stem.strip()

    def _original_subset_name(self, f: Path) -> str:
        """还原字幕「原始文件名」：上传临时目录里的文件名是 subset_<uuid>_<原名>（或 c6ASSsubset_<原名>），
        直接用作子集化输出名会带一堆无关前缀。

        优先按文件名模式剥离前缀（重试时 pending 已删、records 表名可能是旧 uuid 名，靠表名不可靠）；
        剥离不了再按 file_path 反向查 pending/records 的 file_name 兜底。
        """
        name = f.name
        if not name.startswith("subset_") and not name.startswith("c6ASSsubset_"):
            return name
        # subset_<32hex>_<原名> → 去掉 subset_ 与 uuid，保留原名
        m = re.match(r"^subset_[0-9a-f]{32}_(.+)$", name, re.I)
        if m:
            return m.group(1)
        # c6ASSsubset_<原名>
        m = re.match(r"^c6ASSsubset_(.+)$", name, re.I)
        if m:
            return m.group(1)
        try:
            row = self._db.query_one(
                "SELECT file_name FROM subset_pending WHERE file_path = ? ORDER BY id DESC LIMIT 1",
                (str(f),),
            )
            if row and row.get("file_name"):
                return row["file_name"]
            row = self._db.query_one(
                "SELECT file_name FROM subset_records WHERE file_path = ? ORDER BY id DESC LIMIT 1",
                (str(f),),
            )
            if row and row.get("file_name"):
                return row["file_name"]
        except Exception:
            pass
        return name

    def _sync_subset_output(self, out: Path, subdir: Path, show: str = "") -> Tuple[Optional[Path], str]:
        """子集化成品同步到「子集化输出目录」（subset_out_dir）。

        未配置输出目录 → 返回 (None, "")（保持原目录产物，不影响调用方）；
        配置了 → 按 subset_out_mode 复制(copy)/移动(move) 成品 ass 与子集字体夹到输出目录，
        show（剧名）非空时输出到 输出目录/<剧名>/ 子文件夹（监控来源按剧分类，多剧不混在一起），
        返回 (同步后成品路径, 说明)。失败/无需同步时返回 (None, 说明)。
        """
        out_dir = self.get_resource_or_config("subset_out_dir") or ""
        if not out_dir:
            return None, ""
        mode = self.get_resource_or_config("subset_out_mode") or "copy"
        try:
            d = Path(out_dir)
            if show:
                d = d / show
            d.mkdir(parents=True, exist_ok=True)
            if not out.is_file():
                return None, "输出文件不存在，未同步"
            # 输出目录与成品同目录：无需搬移
            if str(out.parent.resolve()).lower() == str(d.resolve()).lower():
                return None, ""
            dst = d / out.name
            if mode == "move":
                if dst.exists():
                    dst.unlink(missing_ok=True)
                shutil.move(str(out), str(dst))
            else:
                shutil.copy2(str(out), str(dst))
            # 子集字体夹（<stem>_subsetted）：仅当「是否在输出端保留子集化字体文件夹」开启时才随成品同步。
            # 子集字体已内嵌进 .assfonts.ass，该夹子仅是 assfonts 顺手的备份，不同步不影响播放。
            if subdir and subdir.is_dir() and bool(self.get_resource_or_config("subset_sync_subdir")):
                dst_sub = d / subdir.name
                if mode == "move":
                    if dst_sub.exists():
                        shutil.rmtree(dst_sub, ignore_errors=True)
                    shutil.move(str(subdir), str(dst_sub))
                elif not dst_sub.exists():
                    shutil.copytree(str(subdir), str(dst_sub))
            if self._db is not None:
                self._db.add_log(f"子集化成品{'移动' if mode == 'move' else '已输出'}: {dst}", "info")
            return dst, f"输出目录：{dst}"
        except Exception as err:
            if self._db is not None:
                self._db.add_log(f"子集化成品同步输出目录失败: {err}", "warning")
            return None, f"同步失败: {err}"

    def _run_subset_batch(self, files: List[Path], source: str = "manual") -> Dict[str, Any]:
        """对一批 ass 字幕执行子集化：跳过已子集化/缺字体的记录原因，写 subset_records。

        调用方需已持有 _scan_lock（入库自动与页面全量互斥）。
        """
        stats: Dict[str, Any] = {"success": 0, "skipped": 0, "missing": 0, "error": 0, "missing_fonts": [], "file_status": {}}
        if not files:
            return stats
        if self._db is None or self._assfonts_idx is None:
            return stats
        binary = self._subset_binary()
        if not binary:
            self._db.add_log("子集化未执行：bin/assfonts 不存在或不可执行", "warning")
            return stats
        if not self._ensure_subset_index():
            self._db.add_log("子集化未执行：字体索引不可用（请确认字体库目录已配置）", "warning")
            return stats
        rename = self.get_resource_or_config("subset_rename") is not False
        overwrite = bool(self.get_resource_or_config("subset_overwrite"))
        for f in files:
            try:
                # 优雅停止：停插件时当前条子集化处理完（含写结果记录）就不再继续
                if self._stopping:
                    break
                f = Path(f)
                if not f.is_file() or not is_ass_file(f.name):
                    continue
                # 原始字幕名（去掉上传临时目录的 subset_<uuid> 前缀），全部状态记录统一用它
                orig = self._original_subset_name(f)
                # 已内嵌（子集化）字幕跳过，不重复处理
                try:
                    if has_embedded_fonts(f.read_bytes()):
                        self._db.add_subset_record(
                            {
                                "file_name": orig,
                                "file_path": str(f),
                                "status": "skipped",
                                "reason": "已子集化（自带内嵌字体）",
                                "out_file": "",
                            }
                        )
                        stats["skipped"] += 1
                        continue
                except Exception:
                    pass
                res = af.subset_ass_file(binary, f, self._assfonts_idx, rename=rename)
                status = res.get("status", "error")
                if status == "success":
                    out = Path(res.get("out") or "")
                    # 成品输出名：以「原始字幕名」为准（去掉上传临时目录的 uuid 前缀），
                    # 后缀（assfonts 的 -r 重命名）默认开启（subset_rename 缺省 True），
                    # 控制成品是否保留 .assfonts 后缀；「输出覆盖原文件」开启时后缀被覆盖逻辑吞掉
                    orig = self._original_subset_name(f)
                    base = orig[:-4] if orig.lower().endswith(".ass") else orig
                    if overwrite:
                        # 覆盖模式：子集化结果直接替换原字幕文件（原名不变）
                        try:
                            out.replace(f)
                            final_out = f
                        except Exception:
                            final_out = out
                    else:
                        final_out = out
                        try:
                            target = Path(f.parent) / (f"{base}.assfonts.ass" if rename else f"{base}.ass")
                            if str(target.resolve()).lower() == str(f.resolve()).lower():
                                # 不加后缀时目标即原字幕文件 → 等同覆盖原文件，直接替换避免误删源
                                try:
                                    out.replace(f)
                                    final_out = f
                                except Exception:
                                    final_out = out
                            elif str(target.resolve()).lower() != str(out.resolve()).lower():
                                if target.exists():
                                    try:
                                        target.unlink()
                                    except Exception:
                                        pass
                                try:
                                    shutil.move(str(out), str(target))
                                    final_out = target
                                except Exception:
                                    final_out = out
                        except Exception:
                            final_out = out
                    # HDR 字幕亮度：完成子集化后按档位压暗主色/描边/阴影（就地改写成品）
                    hdr_msg = ""
                    hdr_level = self.get_resource_or_config("hdr_brightness_level") or ""
                    if final_out.is_file() and hdr_level:
                        hdr_msg = af.apply_hdr_brightness(final_out, str(hdr_level)) or ""
                        if hdr_msg:
                            self._db.add_log(f"HDR 亮度应用: {final_out.name}（{hdr_msg}）", "info")
                    # ── 成品落位判定（来源身份）：
                    #   inbound（MP入库）：成品只落媒体库，不同步输出目录；_subsetted 受开关控制
                    #   watch（目录监控）：成品按「监控目录输出方式」同步到输出目录并按剧名分子文件夹；
                    #                     _subsetted 受开关控制
                    #   manual（手动上传）：成品只留上传临时目录，不同步输出目录；_subsetted 始终不保留
                    #   retry：按源字幕所在区域继承身份——上传临时目录→manual；ASS/子集监控目录→watch；
                    #          媒体库→inbound
                    src_kind = source
                    if source == "retry":
                        try:
                            p_f = Path(f)
                            if _path_within(p_f, Path(self._tmp_dir)):
                                src_kind = "manual"
                            elif any(
                                w and _path_within(p_f, Path(w))
                                for w in (
                                    str(self.get_resource_or_config("ass_dir") or ""),
                                    str(self.get_resource_or_config("subset_dir") or ""),
                                )
                            ):
                                src_kind = "watch"
                            else:
                                src_kind = "inbound"
                        except Exception:
                            src_kind = "inbound"
                    keep_subdir = bool(self.get_resource_or_config("subset_sync_subdir"))
                    sync_output = False
                    show_folder = ""
                    if src_kind == "watch":
                        sync_output = True
                        show_folder = self._extract_show_name(str(final_out))
                    elif src_kind == "manual":
                        keep_subdir = False  # 手动上传始终不保留子集字体夹
                    if not sync_output:
                        synced, sync_msg = "", ""
                    else:
                        synced, sync_msg = self._sync_subset_output(
                            final_out, Path(res.get("subdir") or ""), show_folder
                        )
                    # 「是否在输出端保留子集化字体文件夹」关闭时，自动清理源字幕目录里的 *_subsetted
                    # 备份夹（手动上传一律清理；入库/监控受开关控制。move 同步已把夹子移走时自然跳过）
                    if not keep_subdir:
                        try:
                            sub = Path(res.get("subdir") or "")
                            if sub.is_dir():
                                shutil.rmtree(sub, ignore_errors=True)
                        except Exception:
                            pass
                    # assfonts「-r」机制遗留的中间副本清理：它先复制输入为 <stem>.rename.ass 再内嵌，
                    # 处理完不删；该副本与源字幕内容相同，纯属冗余，入库/监控/上传三条来源统一在此清除
                    if rename:
                        try:
                            _junk = f.with_name(f"{f.stem}.rename{f.suffix}")
                            if (
                                _junk.is_file()
                                and _junk.resolve() != f.resolve()
                                and _junk.resolve() != final_out.resolve()
                            ):
                                _junk.unlink(missing_ok=True)
                        except Exception:
                            pass
                    record_out = str(synced) if synced else (str(final_out) if final_out.is_file() else "")
                    self._db.add_subset_record(
                        {
                            "file_name": orig,
                            "file_path": str(f),
                            "status": "success",
                            "reason": "；".join([m for m in (sync_msg, hdr_msg) if m]) or "",
                            "out_file": record_out,
                        }
                    )
                    stats["success"] += 1
                    self._db.add_log(f"子集化成功: {f.name} → {Path(record_out or final_out).name}", "info")
                elif status == "missing":
                    reason = str(res.get("reason") or "")
                    # 结构化缺失清单（assfonts 输出解析所得），不再对 reason 字符串做往返拆分
                    fonts = [x.strip() for x in (res.get("missing_fonts") or []) if str(x or "").strip()]
                    for x in fonts:
                        if x and x not in stats["missing_fonts"]:
                            stats["missing_fonts"].append(x)
                    self._db.add_subset_record(
                        {
                            "file_name": orig,
                            "file_path": str(f),
                            "status": "missing",
                            "reason": reason,
                            "out_file": "",
                        }
                    )
                    stats["missing"] += 1
                    stats["file_status"][str(f.resolve())] = "keep"  # 缺字体：临时源保留待补字重试
                    self._db.add_log(f"子集化跳过(缺字体): {orig}（{reason}）", "warning")
                else:
                    self._db.add_subset_record(
                        {
                            "file_name": orig,
                            "file_path": str(f),
                            "status": "error",
                            "reason": str(res.get("reason") or "")[:300],
                            "out_file": "",
                        }
                    )
                    stats["error"] += 1
                    stats["file_status"][str(f.resolve())] = "keep"  # 失败：临时源保留待重试
                    self._db.add_log(f"子集化失败: {orig}（{res.get('reason', '')}）", "error")
            except Exception as err:
                stats["error"] += 1
                try:
                    self._db.add_subset_record(
                        {
                            "file_name": orig if 'orig' in locals() else Path(f).name,
                            "file_path": str(f),
                            "status": "error",
                            "reason": str(err)[:300],
                            "out_file": "",
                        }
                    )
                    stats["file_status"][str(Path(f).resolve() if f else "")] = "keep"
                    self._db.add_log(f"子集化失败: {Path(f).name}（{err}）", "error")
                except Exception:
                    pass
        return stats

    def _notify_subset_result(self, stats: Dict[str, Any], scope: str = "") -> None:
        """子集化批量完成通知（单条汇总）"""
        try:
            if not self.get_resource_or_config("notify_enabled"):
                return
            lines: List[str] = []
            title = f"字体分类管家：子集化完成{('（' + scope + '）') if scope else ''}"
            if stats["success"]:
                lines.append(f"✅ 已子集化 {stats['success']} 个字幕")
            if stats["skipped"]:
                lines.append(f"⏭ 跳过 {stats['skipped']} 个（已子集化）")
            if stats["missing"]:
                fonts = stats.get("missing_fonts") or []
                shown = "、".join(fonts[:5])
                more = len(fonts) - 5
                lines.append(
                    f"❌ 缺字体 {stats['missing']} 个字幕：{shown}"
                    + (f" 等 {more} 种" if more > 0 else "")
                    + "（可先上传缺失字体入库、重建索引后重试）"
                )
            if stats["error"]:
                lines.append(f"⚠ 失败 {stats['error']} 个（见子集化记录）")
            if lines:
                self._notify(title, "\n".join(lines))
        except Exception:
            pass

    def _run_show_subset(self, files: List[Path], show: str = "", source: str = "inbound") -> None:
        """后台自动子集化（入库监控共用，后台线程）：与页面全量互斥，缺二进制/索引时仅写日志。

        source 决定成品落位身份：
        - inbound（MP 入库）→ 成品只落媒体库，不同步输出目录，_subsetted 受开关控制；
        - watch（目录监控）→ 按「监控目录输出方式」同步到输出目录并按剧名分子文件夹。
        """
        if self._db is None:
            return
        if not self._subset_binary():
            self._db.add_log("自动子集化跳过：bin/assfonts 未就绪（设置 → 子集化）", "warning")
            return
        if not self._scan_lock.acquire(blocking=False):
            self._db.add_log(f"自动子集化（{show or '字幕'}）跳过：全量子集化正在运行", "warning")
            return
        try:
            stats = self._run_subset_batch(list(files), source=source)
            total_done = stats["success"] + stats["missing"] + stats["error"]
            if total_done:
                self._db.add_log(
                    f"自动子集化 {show or ''}: 成功 {stats['success']}, 跳过 {stats['skipped']}, "
                    f"缺字体 {stats['missing']}, 失败 {stats['error']}",
                    "info",
                )
                self._notify_subset_result(stats, scope=show or "")
        finally:
            self._scan_lock.release()

    def _schedule_subset_watch(self, p: Path) -> None:
        """目录监控到新字幕（auto_subset 开启时）：
        「目录自动收集」开 → 立即后台自动子集化；
        关 → 进子集化页左栏「待处理」等待手动「全量子集化」。
        """
        try:
            if self.get_resource_or_config("auto_collect") is False:
                if self._db is not None:
                    self._db.add_subset_pending(p.name, str(p), source="watch")
                return
            threading.Thread(
                target=self._run_show_subset,
                args=([p], "", "watch"),
                daemon=True,
            ).start()
        except Exception as err:
            _logger.debug("目录子集化调度失败: %s", err)

    # ─── 入库字幕扫描（TransferComplete / SubtitleTransferComplete 聚合）────────
    @staticmethod
    def _safe_get(obj, key, default=None):
        """兼容 dict 与 pydantic 对象的字段读取（MP 事件 payload 中 meta/mediainfo/transferinfo/fileitem 均为对象）"""
        if isinstance(obj, dict):
            return obj.get(key, default)
        try:
            return getattr(obj, key, default)
        except Exception:
            return default

    def _resolve_movie_pilot_path(self, raw: str) -> str:
        """解析 MP 事件路径：兼容存储视图前缀（如"本地/xxx"）与真实挂载路径两种形态"""
        if not raw:
            return ""
        p = str(raw)
        if Path(p).exists():
            return p
        # 首段可能是存储别名（本地/xxx 等）：剥掉首段再试
        try:
            parts = p.replace("\\", "/").split("/")
            if len(parts) > 1:
                joined = "/".join(parts[1:])
                if joined and Path(joined).exists():
                    return joined
        except Exception:
            pass
        return p

    def _upsert_ass_by_path(self, f: Path, raw: bytes, source: str = "auto") -> bool:
        """按 file_path 去重：已存在记录则覆盖更新检查结果，否则新增"""
        try:
            all_fonts = parse_ass_fonts(raw)
            subsetted = has_embedded_fonts(raw)
            fam_keys, _fmatch = self._lib_font_keys()
            # 缺失清单按归一化 key 去重（@竖排变体与本体同 key 只算一次），保留首个原始名
            seen: set = set()
            missing: List[str] = []
            for fo in all_fonts:
                k = normalize_font_key(fo)
                if not k or k in seen:
                    continue
                seen.add(k)
                if k not in fam_keys:
                    missing.append(fo)
            # 已内嵌（子集化）字幕自带字体：不报缺失
            if subsetted and missing:
                missing = []
            status = "ok" if not missing else "missing"
            row = self._db.query_one("SELECT id FROM ass_files WHERE file_path = ?", (str(f),))
            if row:
                self._db.update_ass(row["id"], status, missing, all_fonts)
            else:
                self._db.add_ass(
                    file_name=f.name,
                    source=source,
                    status=status,
                    missing_fonts=missing,
                    all_fonts=all_fonts,
                    file_path=str(f),
                )
            return True
        except Exception:
            return False

    def _notify_show_scan(self, show: str, total: int, embedded: int, missing_map: Dict[str, str]) -> None:
        """汇总通知：missing_map = {归一化key: 展示名}（缺 N 种已按 key 去重）

        格式对齐单字幕通知：状态符号 + 结果行 + 明细换行。剧级聚合字体可能较多，
        缺失列表保持「最多 5 个 + 等 N 种」折叠，避免消息过长。
        """
        try:
            if not self.get_resource_or_config("notify_enabled"):
                return
            if total <= 0:
                return  # 无 ASS 不通知
            if missing_map:
                names = list(missing_map.values())[:5]
                more = len(missing_map) - 5
                text = "、".join(names) + (f" 等 {more} 种" if more > 0 else "")
                lines = [
                    f"❌ 《{show}》字幕检查完成",
                    f"共 {total} 个字幕" + (f"，其中 {embedded} 个已内嵌字体" if embedded else ""),
                    f"缺失 {len(missing_map)} 种字体：{text}",
                    "可在检查页上传缺失字体入库消除标记",
                ]
            else:
                # 全部字幕已内嵌（子集化）：不再说「字体齐全」（观众根本看不出有没有子集化），明确告知
                all_embedded = embedded > 0 and embedded == total
                lines = [
                    f"✅ 《{show}》字幕检查完成",
                    f"共 {total} 个字幕" + (f"，其中 {embedded} 个已内嵌字体" if embedded else ""),
                    "全部字幕已子集化（自带内嵌字体）" if all_embedded else "字幕字体齐全",
                ]
            self._notify(f"《{show}》字幕检查完成", "\n".join(lines))
        except Exception:
            pass

    def _run_show_scan(self, key: str, tmdbid: str, title: str, file_list: List[str]) -> None:
        """聚合到期：处理本次新增的 ASS 字幕列表（由 on_transfer_complete 汇总传入）。

        「入库自动检查字幕」（auto_inbound）开 → 写检查记录并汇总通知；
        「入库后自动子集化」（auto_subset）开 → 对这批字幕做字体子集化并内嵌。
        两者相互独立：只开子集化时不产生检查记录/检查通知，只开检查时不做子集化。
        """
        with self._lock:
            self._show_timers.pop(key, None)
            self._pending_shows.pop(key, None)
        try:
            self._db.add_log(
                f"入库字幕聚合到期，开始处理（{title or key}）：本次 {len(file_list or [])} 个字幕",
                "info",
            )
            ass_files = [
                Path(f)
                for f in (file_list or [])
                if f and Path(f).is_file() and is_ass_file(Path(f).name)
            ]
            if not ass_files:
                self._db.add_log(f"入库扫描 {title or key}: 新增字幕文件均已失效，跳过", "info")
                return
            do_check = self.get_resource_or_config("auto_inbound") is not False
            do_subset = bool(self.get_resource_or_config("auto_subset"))
            if not (do_check or do_subset):
                return
            if do_check:
                total = 0
                embedded = 0
                # key(归一化字体) -> 展示名；缺 N 种按 key 去重统计（@竖排变体与本体算一种）
                missing_map: Dict[str, str] = {}
                fams, _fmatch = self._lib_font_keys()
                for f in ass_files:
                    try:
                        raw = f.read_bytes()
                    except Exception:
                        continue
                    if not self._upsert_ass_by_path(f, raw, source="inbound"):
                        continue
                    total += 1
                    if has_embedded_fonts(raw):
                        embedded += 1
                    else:
                        for fo in parse_ass_fonts(raw):
                            k = normalize_font_key(fo)
                            if k and k not in fams and k not in missing_map:
                                missing_map[k] = fo
                self._db.add_log(
                    f"入库扫描 {title or key}: {total} 个字幕, {embedded} 个已内嵌, 缺 {len(missing_map)} 种字体",
                    "warning" if missing_map else "info",
                )
                self._notify_show_scan(title or key, total, embedded, missing_map)
            # 入库自动子集化（设置开关 auto_subset 开启时）：独立于「入库自动检查字幕」，
            # 关闭检查开关不阻断子集化——对这批字幕做字体子集化并内嵌
            if do_subset:
                try:
                    threading.Thread(
                        target=self._run_show_subset,
                        args=(ass_files, title or key),
                        daemon=True,
                    ).start()
                except Exception as err:
                    _logger.debug("入库自动子集化启动失败: %s", err)
        except Exception as err:
            _logger.debug("入库字幕扫描失败: %s", err)

    @eventmanager.register(EventType.SubtitleTransferComplete)
    def on_transfer_complete(self, event) -> None:
        """MP 字幕入库（转移完成）事件：滑动聚合后处理该剧本次新增字幕（检查/子集化）

        MoviePilot V2 按文件类型分发转移完成事件（见 app/chain/transfer.py）：
        - 字幕文件整理完成 → SubtitleTransferComplete（transfer.subtitle.complete），
          transferinfo.target_item.path 是转移后字幕路径（媒体库内入库文件）；
          fileitem.path 是源字幕路径（link 模式下源文件仍在原目录，不计入）
        - 视频/音频整理完成 → TransferComplete / AudioTransferComplete，与字幕无关不监听
        （.ass 扩展名必被 MP 判定为字幕文件，字幕事件可靠且必然触发）
        tmdbid/title 位于 mediainfo（tmdb_id / title），meta 只是文件名解析元数据（无 tmdbid）；
        两个开关相互独立：
        - 「入库自动检查字幕」（auto_inbound）开 → 写 ass_files 记录并发检查通知；
        - 「入库后自动子集化」（auto_subset）开 → 对新增字幕做 assfonts 子集化；
        两者都关时才完全不处理。
        """
        try:
            if not self._enabled or not self._db_ok():
                return
            # 独立开关：检查与子集化解耦——只要任一开启就继续处理事件；
            # 注意用 is False 判断：老版本宿主配置无该字段（None）时应视为开启，不拦截
            if (
                self.get_resource_or_config("auto_inbound") is False
                and not bool(self.get_resource_or_config("auto_subset"))
            ):
                return
            data = getattr(event, "event_data", None) or {}
            if not isinstance(data, dict):
                data = {}
            # ── 媒体信息：V2 中 tmdbid/title 在 mediainfo；meta 只是解析元数据 ──
            mediainfo = data.get("mediainfo") or {}
            meta = data.get("meta") or {}
            tmdbid = (
                str(self._safe_get(mediainfo, "tmdb_id") or "")
                or str(self._safe_get(meta, "tmdbid") or "")
            )
            title = (
                str(self._safe_get(mediainfo, "title") or "")
                or str(self._safe_get(meta, "title") or "")
                or str(self._safe_get(meta, "cn_name") or "")
                or str(self._safe_get(meta, "en_name") or "")
            )
            transferinfo = data.get("transferinfo") or {}
            # ── 收集本次新增的 ASS 字幕路径（只算转移后入库文件） ──
            # transferinfo.target_item 是转移后的字幕（媒体库内入库文件）；
            # fileitem / transferinfo.fileitem 是源字幕路径——link 模式下源文件仍
            # 保留在原目录，不属于媒体库，不应计入检查/子集化（避免同一字幕双份）
            ass_paths: List[str] = []
            seen: set = set()

            def _collect(p):
                p = str(p or "")
                if not p or p in seen:
                    return
                seen.add(p)
                resolved = self._resolve_movie_pilot_path(p)
                if resolved and Path(resolved).is_file() and is_ass_file(Path(resolved).name):
                    ass_paths.append(resolved)

            _collect(self._safe_get(self._safe_get(transferinfo, "target_item") or {}, "path"))
            self._db.add_log(
                f"收到 MP 字幕入库事件：title={title or '未知'}, tmdbid={tmdbid or '未知'}, "
                f"本次携带字幕 {len(ass_paths)} 个",
                "info",
            )
            if not ass_paths:
                self._db.add_log("字幕事件未解析到可用 ASS 字幕路径，跳过", "warning")
                return
            key = tmdbid or title or str(Path(ass_paths[0]).parent)
            with self._lock:
                cur = self._pending_shows.get(key)
                if cur is None:
                    cur = []
                    self._pending_shows[key] = cur
                for p in ass_paths:
                    if p not in cur:
                        cur.append(p)
                timer = self._show_timers.get(key)
                if timer:
                    timer.cancel()
                timer = threading.Timer(
                    self._ass_finalize_delay,
                    self._run_show_scan,
                    args=(key, tmdbid, title, list(cur)),
                )
                timer.daemon = True
                timer.start()
                self._show_timers[key] = timer
            self._db.add_log(
                f"入库字幕已排队（{title or key}）：{len(cur)} 个，{self._ass_finalize_delay} 秒聚合后统一处理，"
                "正在等待整部入库完毕…",
                "info",
            )
            _logger.info("入库扫描已排队: %s (%d 个字幕)，%ds 后统一处理", title or key, len(cur), self._ass_finalize_delay)
        except Exception as err:
            _logger.debug("入库字幕扫描事件处理失败: %s", err)
            try:
                if self._db is not None:
                    self._db.add_log(f"入库事件处理异常: {err}", "error")
            except Exception:
                pass

    def _db_ok(self) -> bool:
        if self._db is None:
            try:
                self.init_plugin(self._config)
            except Exception:
                return False
        return self._db is not None

    def _ok(self, data: Any, message: str = "success") -> Dict[str, Any]:
        return {"success": True, "message": message, "data": data}

    def _err(self, message: str = "error", code: int = 500) -> Dict[str, Any]:
        return {"success": False, "message": message, "code": code}

    # ─── API：依赖检测 ──────────────────────────────────
    def api_deps_check(self) -> Dict[str, Any]:
        """检测插件运行依赖是否安装（fontTools/watchdog/sqlite），供仪表盘顶部展示"""
        items: List[Dict[str, Any]] = []
        # fontTools：字体元数据/厂商识别
        items.append(
            {
                "key": "fonttools",
                "name": "fontTools",
                "ok": TTFont is not None,
                "detail": "读取字体元数据 / 厂商识别",
                "impact": "未安装时厂商识别退化为文件名方式，无法读真实字体名",
            }
        )
        # watchdog：目录实时监控（字体归档 / 字幕自动检查）
        items.append(
            {
                "key": "watchdog",
                "name": "watchdog",
                "ok": _HAS_WATCHDOG,
                "detail": "目录实时监控（字体自动归档 / 字幕自动检查）",
                "impact": "未安装时仅靠 6 小时定时任务兜底，实时性下降",
            }
        )
        # sqlite3：宿主 Python 自带
        try:
            import sqlite3  # noqa: F401

            _sqlite_ok = True
        except Exception:
            _sqlite_ok = False
        items.append(
            {
                "key": "sqlite",
                "name": "SQLite",
                "ok": _sqlite_ok,
                "detail": "插件本地数据库（字体库 / 检查记录）",
                "impact": "依赖宿主运行环境",
            }
        )
        ok_count = sum(1 for i in items if i["ok"])
        return self._ok(
            {"items": items, "ok_count": ok_count, "total": len(items)},
            "依赖检测完成",
        )

    # ─── API：统计 ──────────────────────────────────────
    def _count_pending_incoming(self) -> int:
        """字体监控目录中尚未被收集的字体文件数（仪表盘「待整理」口径）

        实时递归扫描输入目录的字体文件，排除：
        - 位于字体库目录内的（归档落点与输入目录重叠的场景，文件本身就在库里）；
        - 已在「待确认」列表挂档的；
        - 已被监控/全量检查处理过的源文件（_archive_font_file 归档或同名跳过时标记）。

        用户往监控目录放 N 个字体 → 未入库前显示 N，监控自动归档/全量检查处理后归零。
        """
        try:
            input_dir = self.get_resource_or_config("input_dir") or ""
            if not input_dir or not Path(input_dir).is_dir():
                return 0
            lib_dir = self.get_resource_or_config("lib_dir") or ""
            pending_paths: set = set()
            try:
                for r in self._db.query(
                    "SELECT file_path FROM pending_fonts WHERE file_path != ''"
                ):
                    if r.get("file_path"):
                        pending_paths.add(str(Path(r["file_path"]).resolve()))
            except Exception:
                pass
            processed = self._db.processed_font_paths()
            count = 0
            for f in Path(input_dir).rglob("*"):
                if self._is_system_hidden_path(f):
                    continue
                if not f.is_file() or not is_font_file(f.name):
                    continue
                if lib_dir and _path_within(f, Path(lib_dir)):
                    continue
                resolved = str(f.resolve())
                if resolved in processed or resolved in pending_paths:
                    continue
                count += 1
            return count
        except Exception:
            return 0

    def api_stats(self) -> Dict[str, Any]:
        """仪表盘统计"""
        if not self._db_ok():
            return self._err("数据库未初始化")
        try:
            stats = self._db.stats()
            stats["db_ok"] = True
            stats["last_scan"] = self._db.get_last_scan_time()
            # 「待整理」= 字体监控目录中尚未被收集的字体文件数（实时扫描口径）
            stats["pending"] = self._count_pending_incoming()
            # 「最近子集化数量」= 子集化处理记录总条数
            try:
                stats["subset"] = self._db.count_subset_records()
            except Exception:
                stats["subset"] = 0
            # 「缺失字体」= 检查缺失 + 子集化因缺字体跳过的条数，合并展示
            try:
                stats["error"] += self._db.count_subset_missing()
            except Exception:
                pass
            return self._ok(stats)
        except Exception as err:
            return self._ok({"total": 0, "pending": 0, "archived": 0, "error": 0, "subset": 0, "db_ok": False, "last_scan": ""})

    def api_vendors(self) -> Dict[str, Any]:
        """厂商分布 TOP5"""
        if not self._db_ok():
            return self._err("数据库未初始化")
        try:
            return self._ok(self._db.vendors())
        except Exception as err:
            return self._err(f"获取厂商分布失败: {err}")

    def api_logs(self, limit: int = 10) -> Dict[str, Any]:
        """最近操作日志"""
        if not self._db_ok():
            return self._ok([])
        try:
            return self._ok(self._db.get_logs(limit))
        except Exception as err:
            return self._ok([])

    # ─── API：配置 ──────────────────────────────────────
    def api_task_status(self) -> Dict[str, Any]:
        """后台任务状态（供前端拦截「插件总开关」关闭操作）：
        busy=True 表示有全量检查/全量扫描/子集化在运行，此时不应允许停用插件。"""
        try:
            busy = bool(self._scan_lock.locked())
        except Exception:
            busy = False
        return self._ok({"busy": busy})

    def api_get_config(self) -> Dict[str, Any]:
        """获取配置 + 目录健康度"""
        cfg = {}
        try:
            cfg = dict(self.get_config() or {})
        except Exception:
            pass
        # 运行时 _config 已含默认值合并与老开关迁移推导（monitor_enabled），优先于宿主原始配置兜底，
        # 避免宿主旧保存缺总开关键时 UI 误显示「关闭」
        cfg = {**dict(_DEFAULT_CONFIG), **dict(self._config), **cfg}
        # 总开关以运行时状态为准（与宿主原生保存联动，init_plugin 时已同步）
        cfg["enabled"] = self._enabled
        dirs = [
            {"label": "字体监控目录", "path": cfg.get("input_dir", ""), "exists": bool(cfg.get("input_dir")) and Path(cfg["input_dir"]).is_dir()},
            {"label": "字体库目录", "path": cfg.get("lib_dir", ""), "exists": bool(cfg.get("lib_dir")) and Path(cfg["lib_dir"]).is_dir()},
            {"label": "ASS字幕目录监控", "path": cfg.get("ass_dir", ""), "exists": bool(cfg.get("ass_dir")) and Path(cfg["ass_dir"]).is_dir()},
            {"label": "ASS目录监控子集", "path": cfg.get("subset_dir", ""), "exists": bool(cfg.get("subset_dir")) and Path(cfg["subset_dir"]).is_dir()},
            {"label": "子集化输出目录", "path": cfg.get("subset_out_dir", ""), "exists": bool(cfg.get("subset_out_dir")) and Path(cfg["subset_out_dir"]).is_dir()},
        ]
        result = {**cfg, "dirs": dirs}
        return self._ok(result)

    async def api_save_config(self, request: Request = None) -> Dict[str, Any]:
        """保存配置：合并默认值 → 写入宿主原生配置（update_config）→ 更新运行时并热生效。

        对齐 subscribeplus_v0.23 范式（自建接口落盘宿主配置 + 前端 emit('save') 兜底）：
        - 配置设置页嵌于详情页导航内，宿主对 Page 组件的 save 事件不负责落盘，
          因此必须通过本接口调用 update_config 走宿主原生保存路径，重启/重载不丢；
        - update_config 写入宿主系统配置（plugin 前缀 key），与宿主原生 PUT 等效。
        """
        try:
            if request is None:
                return self._err("缺少请求")
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict) or not body:
            return self._err("无效的配置数据")
        new_cfg = {
            **dict(_DEFAULT_CONFIG),
            **dict(self._config),
            **{k: v for k, v in body.items()},
        }
        # 1) 写入宿主原生配置（与宿主 PUT /plugin 同等的持久化路径，重启保留）
        try:
            self.update_config(new_cfg)
        except Exception as err:
            _logger.warning("宿主配置写入失败: %s", err)
        # 2) 更新运行时并热生效
        self._config = new_cfg
        if self._db:
            try:
                self._db.save_full_config(new_cfg)
            except Exception:
                pass
        if isinstance(new_cfg.get("enabled"), bool):
            self._enabled = new_cfg["enabled"]
        else:
            try:
                self._enabled = bool(new_cfg.get("enabled", self._enabled))
            except Exception:
                pass
        try:
            self._db.set_setting("enabled", self._enabled)
            self._db.add_log("插件配置已更新", "info")
            self._start_watcher()
        except Exception as err:
            _logger.warning("配置生效失败: %s", err)
        return self._ok(new_cfg, "配置已保存")

    # ─── API：数据库备份与恢复 ────────────────────────────
    def api_db_export(self) -> Dict[str, Any]:
        """导出整个数据库为 JSON 备份（含字体库、待确认、ASS 检查记录、配置镜像）"""
        if not self._db_ok():
            return self._err("数据库未初始化")
        try:
            data = self._db.export_all()
            return self._ok(data, "数据库导出成功")
        except Exception as err:
            return self._err(f"导出数据库失败: {err}")

    async def api_db_import(self, request: Request = None) -> Dict[str, Any]:
        """从 JSON 备份恢复数据库（先清空业务表，再写回数据；保留日志，重载后生效）"""
        if not self._db_ok():
            return self._err("数据库未初始化")
        body: Dict[str, Any] = {}
        if request is not None:
            try:
                body = await request.json()
            except Exception:
                body = {}
        if not isinstance(body, dict) or not body:
            return self._err("无效的备份数据")
        try:
            counts = self._db.import_all(body)
            return self._ok(counts, "数据库恢复成功，请刷新页面")
        except Exception as err:
            return self._err(f"导入数据库失败: {err}")

    def api_db_clear(self) -> Dict[str, Any]:
        """清空数据库业务表（字体库、待确认、ASS 检查记录）；保留插件设置与镜像"""
        if not self._db_ok():
            return self._err("数据库未初始化")
        try:
            counts = self._db.clear_all()
            return self._ok(counts, "数据库已清空")
        except Exception as err:
            return self._err(f"清空数据库失败: {err}")

    # ─── API：字体库 ────────────────────────────────────
    def api_fonts(self, page: int = 1, limit: int = 50, search: str = "", vendor: str = "") -> Dict[str, Any]:
        """字体分页列表"""
        if not self._db_ok():
            return self._err("数据库未初始化")
        try:
            data = self._db.query_fonts(
                keyword=(search or "").strip(),
                vendor=(vendor or "").strip(),
                page=page,
                limit=limit,
            )
            return self._ok(data)
        except Exception as err:
            return self._err(f"查询字体列表失败: {err}")

    def api_font_tree(self) -> Dict[str, Any]:
        """全部已归档字体 + 字体库目录（前端本地构建目录树，忽略分页）"""
        if not self._db_ok():
            return self._err("数据库未初始化")
        try:
            fonts = self._db.list_all_fonts()
            return self._ok({
                "list": fonts,
                "lib_dir": self.get_resource_or_config("lib_dir") or "",
            })
        except Exception as err:
            return self._err(f"读取字体目录数据失败: {err}")

    def api_font_delete(self, id: int = 0) -> Dict[str, Any]:
        """删除字体：删除数据库记录 + 磁盘上的字体文件（含清理空目录）"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        if not id:
            return self._err("缺少字体ID")
        try:
            row = self._db.get_font(id)
            if not row:
                return self._err("字体不存在")
            file_path = row.get("file_path", "") or ""
            file_deleted = False
            if file_path:
                p = Path(file_path)
                try:
                    if p.is_file():
                        p.unlink()
                        file_deleted = True
                    # 若父目录位于字体库内且已为空，则一并清理
                    lib_dir = self.get_resource_or_config("lib_dir") or ""
                    if lib_dir and _path_within(p.parent, Path(lib_dir)):
                        try:
                            p.parent.rmdir()
                        except Exception:
                            pass
                except Exception as err:
                    return self._err(f"删除字体文件失败: {err}")
            self._db.delete_font(id)
            self._db.add_log(
                f"删除字体: {row.get('file_name', '')} ({'已删除文件' if file_deleted else '文件不存在，仅删记录'})",
                "warning",
            )
            return self._ok({"id": id, "file_deleted": file_deleted}, "字体已删除")
        except Exception as err:
            return self._err(f"删除失败: {err}")

    def api_recalc_vendor(self, id: int = 0) -> Dict[str, Any]:
        """重新识别厂商：按新规则（内部制造商名/目录名/文件名）重新解析字体库内字体的厂商。
        不传 id 时全量重算；传 id 时仅重算单个字体。返回变更数量。
        文件已不存在（外部删除/移动）的记录会一并清除，保证厂商分布/字体库统计与磁盘一致。"""
        if not self._db_ok():
            return self._err("数据库未初始化")
        scan_mode = self.get_resource_or_config("scan_mode") or "internal"
        changed = 0
        scanned = 0
        removed = 0
        try:
            if id:
                single = self._db.get_font(int(id)) or {}
                targets = [single] if single.get("id") else []
            else:
                targets = self._db.list_all_fonts()
            for row in targets:
                if not row:
                    continue
                file_path = row.get("file_path") or ""
                if not file_path or not Path(file_path).is_file():
                    # 文件已不存在：清除数据库记录，避免厂商分布/字体库统计残留
                    self._db.delete_font(row["id"])
                    removed += 1
                    continue
                scanned += 1
                try:
                    meta = parse_font_metadata(file_path, scan_mode=scan_mode, filename_hint=Path(file_path).stem)
                except Exception:
                    continue
                new_vendor = meta.get("vendor", "未知厂商")
                if new_vendor != row.get("vendor") or meta.get("designer") != row.get("designer"):
                    self._db.update_font_vendor(row["id"], new_vendor, meta.get("designer", ""))
                    changed += 1
            msg = f"重新识别厂商：扫描 {scanned} 个字体，更新 {changed} 个，清理失效记录 {removed} 条"
            self._db.add_log(msg, "info" if (changed or removed) else "success")
            return self._ok(
                {"scanned": scanned, "changed": changed, "removed": removed},
                f"已重新识别 {scanned} 个字体，更新 {changed} 个厂商，清理失效记录 {removed} 条",
            )
        except Exception as err:
            self._db.add_log(f"重新识别厂商失败: {err}", "error")
            return self._err(f"重新识别厂商失败: {err}")

    async def api_toggle_favorite(self, request: Request) -> Dict[str, Any]:
        """切换收藏"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        try:
            body = await request.json()
        except Exception:
            body = {}
        font_id = body.get("id")
        if not font_id:
            return self._err("缺少字体ID")
        try:
            new_val = self._db.toggle_favorite(font_id)
            return self._ok({"id": font_id, "favorite": new_val}, "收藏状态已更新")
        except Exception as err:
            return self._err(f"收藏操作失败: {err}")

    def api_font_preview(self, id: int = 0) -> Dict[str, Any]:
        """字体预览：返回字体文件 base64 + 元数据"""
        if not self._db_ok():
            return self._err("数据库未初始化")
        if not id:
            return self._err("缺少字体ID")
        try:
            font = self._db.get_font(id)
            if not font:
                return self._err("字体不存在")
            return self._font_preview_from_path(
                font.get("file_path", ""),
                name=font.get("name", ""),
                family=font.get("family", ""),
            )
        except Exception as err:
            return self._err(f"预览失败: {err}")

    @staticmethod
    def _split_ttc_face(raw: bytes, file_path: str) -> bytes:
        """把 TTC（ttcf 容器）拆出「第一个可被浏览器解析」的单 face 数据。

        逐 face 尝试：① fontTools 按 fontNumber 加载并重存（可正确处理表数据交错
        排布的非标准 TTC，DFP 等变体单个 face 不完整时也不会整卷废弃）；② 全部失败
        再按 TTC 头部 offset 表切片、仍经 fontTools 解析重存。每步都对重存结果做
        再解析校验，返回的都是可被重新解析的单字体数据；全部失败返回原数据。
        """
        try:
            import io as _io
            import struct

            from fontTools.ttLib import TTFont

            def _fmt4_subtable_bad(raw: bytes, off: int) -> bool:
                """format 4 子表结构性校验：segCount 各 idRangeOffset 指向的 glyphIdArray
                索引越界即判坏（老式工具常见：索引 == 数组长度 导致浏览器一票否决）。"""
                try:
                    if off + 16 > len(raw):
                        return True
                    seg_x2 = int.from_bytes(raw[off + 6:off + 8], "big")
                    seg = seg_x2 // 2
                    if seg <= 0 or seg_x2 & 1:
                        return True
                    base = off + 16 + 8 * seg  # endCount+pad+startCount+idDelta+idRangeOffset 之后 = glyphIdArray
                    # glyphIdArray 边界以子表自身 length 字段为准（整表边界会放大数组长度漏判）
                    length = int.from_bytes(raw[off + 2:off + 4], "big")
                    sub_end = (off + length) if (length and off + length <= len(raw)) else len(raw)
                    if base > sub_end:
                        return True
                    array_len = (sub_end - base) // 2
                    for i in range(seg):
                        ro = int.from_bytes(raw[off + 16 + 6 * seg + 2 * i:off + 16 + 6 * seg + 2 * i + 2], "big")
                        if ro == 0:
                            continue
                        lo = int.from_bytes(raw[off + 14 + 2 * i:off + 14 + 2 * i + 2], "big")  # endCount[i]
                        st = int.from_bytes(raw[off + 16 + 2 * seg + 2 * i:off + 16 + 2 * seg + 2 * i + 2], "big")
                        # 与 fontTools 相同的索引算式，取首尾两个极端 charCode 校验
                        idx_min = ro // 2 + i - seg  # charCode = startCount[i]
                        idx_max = idx_min + (lo - st)  # charCode = endCount[i]
                        if idx_min < 0 or idx_max >= array_len:
                            return True
                    return False
                except Exception:
                    return False

            def _fmt4_char_map(raw: bytes, off: int) -> Optional[Dict[int, int]]:
                """从原始字节直接解 format 4 子表为 char→gid 映射（不触发 fontTools
                反解，坏表已在 _fmt4_subtable_bad 剔除）。span 过大的子表返回 None。"""
                try:
                    seg = int.from_bytes(raw[off + 6:off + 8], "big") // 2
                    length = int.from_bytes(raw[off + 2:off + 4], "big")
                    sub_end = (off + length) if (length and off + length <= len(raw)) else len(raw)
                    base = off + 16 + 8 * seg
                    if base > sub_end:
                        return None
                    m = {}
                    total = 0
                    for i in range(seg):
                        lo = int.from_bytes(raw[off + 14 + 2 * i:off + 14 + 2 * i + 2], "big")
                        st = int.from_bytes(raw[off + 16 + 2 * seg + 2 * i:off + 16 + 2 * seg + 2 * i + 2], "big")
                        de = int.from_bytes(raw[off + 16 + 4 * seg + 2 * i:off + 16 + 4 * seg + 2 * i + 2], "big")
                        ro = int.from_bytes(raw[off + 16 + 6 * seg + 2 * i:off + 16 + 6 * seg + 2 * i + 2], "big")
                        span = lo - st + 1
                        total += span
                        if total > 70000:
                            return None
                        for code in range(st, lo + 1):
                            if ro != 0:
                                idx = ro // 2 + (code - st) + i - seg
                                if idx < 0:
                                    continue
                                p = base + 2 * idx
                                if p + 2 > sub_end:
                                    continue
                                gid = int.from_bytes(raw[p:p + 2], "big")
                            else:
                                gid = (code + de) & 0xFFFF
                            m[code] = gid
                    return m
                except Exception:
                    return None

            def _repair_broken_cmap(font, source_bytes: bytes) -> bool:
                """重建损坏的 cmap（浏览器一票否决：format 4 glyph 索引越界即拒载，
                fontTools 反解会在纯表阶段断言，无法借力，只能全原始字节处理）：
                ① 按 sfnt 目录切出 cmap 原始数据；② 结构校验判出坏子表，同时从
                完好的 fmt6/fmt4 子表直接解出 char→gid 映射；③ 有坏子表且有好映射
                时，重建一张干净的 format 4 (3,1) 替换。返回是否发生重建。"""
                try:
                    if "cmap" not in font:
                        return False
                    ng = font["maxp"].numGlyphs
                    # 单字体 sfnt 目录：0-3 version，4-5 numTables，记录从 12 开始
                    raw = b""
                    n = int.from_bytes(source_bytes[4:6], "big")
                    for i in range(n):
                        r = 12 + 16 * i
                        if r + 16 > len(source_bytes):
                            break
                        if source_bytes[r:r + 4] == b"cmap":
                            off = int.from_bytes(source_bytes[r + 8:r + 12], "big")
                            ln = int.from_bytes(source_bytes[r + 12:r + 16], "big")
                            raw = source_bytes[off:off + ln]
                            break
                    if len(raw) < 6:
                        return False
                    n = int.from_bytes(raw[2:4], "big")
                    merged: Dict[int, int] = {}
                    broken = False
                    for i in range(n):
                        r = 4 + 8 * i
                        if r + 8 > len(raw):
                            break
                        off = int.from_bytes(raw[r + 4:r + 8], "big")
                        if off < 0 or off + 6 > len(raw):
                            broken = True
                            continue
                        fmt = int.from_bytes(raw[off:off + 2], "big")
                        if fmt == 4:
                            # 结构校验判坏（浏览器一票否决项，触发整体重建）
                            if _fmt4_subtable_bad(raw, off):
                                broken = True
                            # 宽容解析取映射：坏表也尝试逐段恢复（越界段跳过，CJK 段照常）
                            m = _fmt4_char_map(raw, off)
                            if m:
                                merged.update(m)
                            else:
                                broken = True
                        elif fmt == 6:
                            length = int.from_bytes(raw[off + 2:off + 4], "big")
                            entry_count = int.from_bytes(raw[off + 8:off + 10], "big")
                            sub_end = (off + length) if (length and off + length <= len(raw)) else len(raw)
                            if off + 10 + 2 * entry_count > sub_end:
                                broken = True
                                continue
                            first = int.from_bytes(raw[off + 6:off + 8], "big")
                            for k in range(entry_count):
                                gid = int.from_bytes(raw[off + 10 + 2 * k:off + 10 + 2 * k + 2], "big")
                                merged[first + k] = gid
                        else:
                            # 其它格式（12 等）：不判坏、不参与（预览用不到）
                            continue
                    if not broken:
                        return False
                    if not merged:
                        return False
                    merged = {cp: g for cp, g in merged.items() if 0 <= g < ng}
                    if not merged:
                        return False
                    # 登记合成字形序：重建子表的字形名可解析回 id
                    try:
                        font.setGlyphOrder(["glyph%05d" % i for i in range(max(ng, 1))])
                    except Exception:
                        pass
                    from fontTools.ttLib.tables._c_m_a_p import CmapSubtable, table__c_m_a_p

                    try:
                        sub = CmapSubtable.newSubtable(4)  # fontTools 4.6x+
                    except AttributeError:
                        sub = CmapSubtable.newSubtableClass(4)  # 旧版 fontTools
                    sub.platformID, sub.platEncID, sub.format, sub.language = 3, 1, 4, 0
                    sub.cmap = {cp: "glyph%05d" % gid for cp, gid in merged.items()}
                    ncmap = table__c_m_a_p()
                    ncmap.tableVersion = 0
                    ncmap.tables = [sub]
                    font["cmap"] = ncmap
                    return True
                except Exception:
                    return False

            def _save_face(face) -> bytes:
                buf = _io.BytesIO()
                face.save(buf)
                data = buf.getvalue()
                probe = TTFont(_io.BytesIO(data), lazy=False)
                try:
                    # 校验 cmap 子表可展开（浏览器一票否决项），损坏则重建
                    _repair_broken_cmap(probe, data)
                    buf2 = _io.BytesIO()
                    probe.save(buf2)
                    data = buf2.getvalue()
                finally:
                    try:
                        probe.close()
                    except Exception:
                        pass
                # 最终校验：可解析且 cmap 全部可展开
                chk = TTFont(_io.BytesIO(data), lazy=False)
                try:
                    if "cmap" in chk:
                        for t in chk["cmap"].tables:
                            t.cmap
                finally:
                    try:
                        chk.close()
                    except Exception:
                        pass
                return data

            # ① fontTools 逐 face 加载重存（face 0 损坏时跳到下一个）
            try:
                num = 0
                if raw[:4] == b"ttcf" and len(raw) >= 16:
                    num = struct.unpack(">I", raw[8:12])[0]
                for idx in range(max(num, 1)):
                    try:
                        face = TTFont(file_path, fontNumber=idx, lazy=False)
                        try:
                            return _save_face(face)
                        finally:
                            try:
                                face.close()
                            except Exception:
                                pass
                    except Exception:
                        continue
            except Exception:
                pass
            # ② 回退：按 TTC 头部 offset 表切片后，再经 fontTools 解析重存校验
            try:
                if raw[:4] == b"ttcf" and len(raw) >= 16:
                    num = struct.unpack(">I", raw[8:12])[0]
                    offs = struct.unpack(f">{num}I", raw[12:12 + 4 * num])
                    for i in range(num):
                        start, end = offs[i], (offs[i + 1] if i + 1 < num else len(raw))
                        if end <= start or end - start < 64:
                            continue
                        try:
                            face = TTFont(_io.BytesIO(raw[start:end]), fontNumber=0, lazy=False)
                        except Exception:
                            continue
                        try:
                            return _save_face(face)
                        finally:
                            try:
                                face.close()
                            except Exception:
                                pass
            except Exception:
                pass
        except Exception:
            pass
        return raw

    def _font_preview_from_path(self, file_path: str, name: str = "", family: str = "") -> Dict[str, Any]:
        try:
            if not file_path or not Path(file_path).is_file():
                return self._err("字体文件不存在或无法读取")
            raw = Path(file_path).read_bytes()
            # TTC（TrueType Collection）拆单 face 再预览：浏览器 FontFace 不认 ttcf 容器
            # （会抛 Invalid font data in ArrayBuffer）。_split_ttc_face 逐 face 用 fontTools
            # 解析重存（可正确处理表数据交错排布的非标准 TTC），并对结果再解析校验；
            # 全部失败才回退整文件交给浏览器报错。
            if raw[:4] == b"ttcf":
                raw = self._split_ttc_face(raw, file_path)
            data = base64.b64encode(raw).decode("ascii")
            return self._ok({"id": 0, "name": name, "family": family, "data": data})
        except Exception as err:
            return self._err(f"读取字体文件失败: {err}")

    # ─── API：待确认上传（pending）──────────────────────
    def _prune_stale_records(self) -> None:
        """源文件被移走/删除后，自动移除对应记录，让列表与文件系统保持一致：

        - ass_files：仅清理非入库（source != 'inbound'）记录——目录监控/手动上传的字幕
          被拉走/删除后记录即失效，随列表查询自动清除；MP 入库记录对应媒体库内字幕文件，
          不自动删（避免存储路径解析差异误删，删除仍由用户主动控制）；
        - pending_fonts：待确认条目的源文件不存在即删（文件已移走/被清理）。
        前端 30 秒轮询/任意列表刷新都会行到本方法，拉走文件后 UI 自动消失。
        """
        if self._db is None:
            return
        try:
            removed_ass = 0
            for r in self._db.query(
                "SELECT id FROM ass_files WHERE file_path != '' AND source != 'inbound'"
            ):
                fp = r.get("file_path") or ""
                if fp and not Path(fp).exists():
                    self._db.delete_ass(r["id"])
                    removed_ass += 1
            removed_pending = 0
            for r in self._db.query("SELECT id FROM pending_fonts WHERE file_path != ''"):
                fp = r.get("file_path") or ""
                if fp and not Path(fp).exists():
                    self._db.delete_pending(r["id"])
                    removed_pending += 1
            if removed_ass or removed_pending:
                self._db.add_log(
                    f"自动移除失效记录（源文件已不存在）：字幕 {removed_ass} 条、待确认 {removed_pending} 条",
                    "info",
                )
        except Exception:
            pass

    def api_pending_list(self) -> Dict[str, Any]:
        """待确认上传列表"""
        if not self._db_ok():
            return self._ok([])
        self._prune_stale_records()
        try:
            return self._ok(self._db.list_pending())
        except Exception as err:
            return self._ok([])

    async def api_upload_preview(self, request: Request) -> Dict[str, Any]:
        """上传字体文件（不写库）：解析元数据后加入待确认列表"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        try:
            form = await request.form()
        except Exception as err:
            return self._err(f"读取上传表单失败: {err}")
        upload_files = []
        try:
            files = form.getlist("file")
            if files:
                upload_files = files
        except Exception:
            pass
        if not upload_files:
            return self._err("请选择要上传的字体文件")
        scan_mode = self.get_resource_or_config("scan_mode") or "internal"
        done: List[Dict[str, Any]] = []
        for upload in upload_files:
            file_name = getattr(upload, "filename", "") or ""
            if not is_font_file(file_name):
                continue
            try:
                raw = await upload.read()
            except Exception:
                continue
            if not raw:
                continue
            safe_name = Path(file_name).name
            tmp_path = Path(self._tmp_dir) / f"{uuid.uuid4().hex}_{safe_name}"
            try:
                tmp_path.write_bytes(raw)
            except Exception:
                continue
            meta = parse_font_metadata(tmp_path, scan_mode=scan_mode, filename_hint=Path(file_name).stem)
            item: Dict[str, Any] = {
                "file_name": safe_name,
                "file_path": str(tmp_path),
                "name": meta["name"],
                "family": meta["family"],
                "vendor": meta["vendor"],
                "designer": meta["designer"],
                "file_size": len(raw),
            }
            try:
                self._db.add_pending(item)
                row = self._db.query_one(
                    "SELECT * FROM pending_fonts WHERE file_path = ? ORDER BY id DESC LIMIT 1",
                    (str(tmp_path),),
                )
                item["id"] = row["id"] if row else 0
                self._db.add_log(f"上传字体: {safe_name}", "info")
            except Exception:
                continue
            done.append(item)
        if not done:
            return self._err("没有可上传的有效字体文件（需字体后缀且内容非空）")
        return self._ok({"count": len(done), "items": done}, f"已加入待确认列表 {len(done)} 个字体")

    def api_pending_delete(self, id: int = 0) -> Dict[str, Any]:
        """删除单个待确认项"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        if not id:
            return self._err("缺少待确认ID")
        try:
            row = self._db.query_one("SELECT * FROM pending_fonts WHERE id = ?", (id,))
            if row and row.get("file_path"):
                try:
                    Path(row["file_path"]).unlink(missing_ok=True)
                except Exception:
                    pass
            self._db.delete_pending(id)
            return self._ok({}, "已删除")
        except Exception as err:
            return self._err(f"删除失败: {err}")

    def api_confirm_upload(self) -> Dict[str, Any]:
        """一键整理：把所有待确认字体归档到字体库目录并写库"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        lib_dir = self.get_resource_or_config("lib_dir") or ""
        if not lib_dir:
            return self._err("请先在设置中配置字体库目录")
        try:
            Path(lib_dir).mkdir(parents=True, exist_ok=True)
        except Exception as err:
            return self._err(f"字体库目录不可用: {err}")
        pending = self._db.list_pending()
        if not pending:
            return self._err("没有待确认的字体")
        archive_mode = self.get_resource_or_config("archive_mode") or "copy"
        processed = 0
        failed = []
        for item in pending:
            try:
                src = Path(item.get("file_path", ""))
                if not src.is_file():
                    self._db.delete_pending(item["id"])
                    continue
                dest_dir = Path(lib_dir) / item.get("vendor", "未知厂商")
                dest_dir.mkdir(parents=True, exist_ok=True)
                base_name = str(item.get("name", item.get("file_name", "font")))
                # 「利用字体内部名称命名」开启时：用字体内部 PostScript 名，读不到回退原名
                if self.get_resource_or_config("font_name_internal"):
                    try:
                        internal_name = get_font_psname(src)
                        if internal_name:
                            base_name = internal_name
                    except Exception:
                        pass
                # 按格式分子文件夹归档：字体库/厂商/格式/基础名.后缀
                fmt_dir = dest_dir / _font_subdir_name(src.suffix)
                existing = _dest_exists_recursive(dest_dir, base_name, src.suffix)
                if existing:
                    # 字体库已存在同名同后缀字体（含旧平铺布局与格式子文件夹）：跳过
                    self._db.add_log(f"整理跳过 {src.name}：字体库已存在 {existing.name}", "info")
                    # 「移动原文件」模式 + 开关开启：删除判重跳过的残留源文件，不留重复
                    if archive_mode == "move" and self.get_resource_or_config("move_delete_duplicate"):
                        try:
                            if src.is_file():
                                src.unlink(missing_ok=True)
                                self._db.add_log(
                                    f"已删除残留的重复源文件 {src.name}（字体库已有 {existing.name}）",
                                    "info",
                                )
                        except Exception as err:
                            self._db.add_log(f"删除重复源文件失败 {src.name}: {err}", "warning")
                    self._db.delete_pending(item["id"])
                    continue
                try:
                    fmt_dir.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
                dest = fmt_dir / f"{base_name}{src.suffix}"
                if archive_mode == "move":
                    shutil.move(str(src), str(dest))
                else:
                    shutil.copy2(str(src), str(dest))
                    # 复制模式：临时目录里的上传源文件不再被 task 引用，立即删除避免残留
                    if self._tmp_dir and str(src.resolve()).startswith(str(Path(self._tmp_dir).resolve())):
                        try:
                            src.unlink(missing_ok=True)
                        except Exception:
                            pass
                self._db.add_font(
                    {
                        "name": item.get("name", ""),
                        "family": item.get("family", ""),
                        "vendor": item.get("vendor", "未知厂商"),
                        "designer": item.get("designer", ""),
                        "file_name": dest.name,
                        "file_size": item.get("file_size", 0),
                        "status": "已归档",
                        "source": "manual",
                        "file_path": str(dest),
                    }
                )
                self._db.delete_pending(item["id"])
                processed += 1
            except Exception as err:
                failed.append({"name": item.get("file_name", ""), "reason": str(err)})
        self._db.add_log(f"一键整理：归档 {processed} 个字体", "info")
        idx_ok, idx_msg = ("", "")
        if processed:
            try:
                idx_ok, idx_msg = self._rebuild_subset_index_silent()
            except Exception:
                idx_ok, idx_msg = False, "索引重建异常"
            if idx_ok:
                self._db.add_log("assfonts 字体索引已自动重建（一键整理后）", "info")
            else:
                self._db.add_log(f"assfonts 索引自动重建失败: {idx_msg}", "warning")
        if failed:
            self._db.add_log(f"整理失败 {len(failed)} 个", "error")
        if self.get_resource_or_config("notify_enabled"):
            self._notify(
                "字体分类管家：整理完成",
                f"✅ 整理完成\n已归档 {processed} 个字体" + ("" if idx_ok else f"\n⚠ assfonts 索引重建失败: {idx_msg}"),
            )
        return self._ok(
            {"processed": processed, "failed": failed, "index_ok": idx_ok},
            f"已归档 {processed} 个字体" + ("" if not idx_ok else "，assfonts 索引已自动重建"),
        )

    def api_discard_upload(self) -> Dict[str, Any]:
        """全部丢弃待确认"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        try:
            pending = self._db.list_pending()
            for item in pending:
                try:
                    if item.get("file_path"):
                        Path(item["file_path"]).unlink(missing_ok=True)
                except Exception:
                    pass
                self._db.delete_pending(item["id"])
            self._db.add_log(f"丢弃 {len(pending)} 个待确认字体", "warning")
            return self._ok({}, f"已丢弃 {len(pending)} 个待确认字体")
        except Exception as err:
            return self._err(f"丢弃失败: {err}")

    def api_scan_archive(self) -> Dict[str, Any]:
        """全量检查（检查归档）：扫描字体监控目录中的字体文件。

        「目录自动收集」开启（默认）→ 直接归档进字体库（幂等：同名/同路径跳过）；
        关闭 → 与手动上传一致，加入待确认列表等待一键整理。
        运行期间互斥：重复触发直接返回「正在运行」，不并发处理（防重复 copy/写库竞态）。
        """
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        input_dir = self.get_resource_or_config("input_dir") or ""
        if not input_dir:
            return self._err("请先在设置中配置字体监控目录")
        if not Path(input_dir).is_dir():
            return self._err("字体监控目录不存在")
        if not self._scan_lock.acquire(blocking=False):
            return self._err("全量检查正在运行中，请等待本次完成后再试")
        try:
            # 「目录自动收集」开启：直接归档入库，不再进待确认
            if self.get_resource_or_config("auto_collect") is not False:
                lib_dir = self.get_resource_or_config("lib_dir") or ""
                if not lib_dir:
                    return self._err("请先在设置中配置字体库目录（归档落点）")
                try:
                    # 诊断日志：打印实际扫描路径与目录项数量，便于定位「配置了目录却扫不到文件」
                    try:
                        entries = list(Path(input_dir).iterdir())
                        self._db.add_log(
                            f"检查归档诊断: 扫描 {input_dir}，目录共 {len(entries)} 项："
                            + (", ".join(e.name for e in entries[:20]) if entries else "(目录为空)"),
                            "info",
                        )
                    except Exception as err:
                        self._db.add_log(f"检查归档诊断: 读取 {input_dir} 失败: {err}", "error")
                except Exception:
                    pass
                added = self._archive_from_dir(Path(input_dir), source="scan")
                idx_ok, idx_msg = self._rebuild_subset_index_silent()
                self._db.add_log(f"检查归档：归档 {added} 个字体", "info")
                if idx_ok:
                    self._db.add_log("assfonts 字体索引已自动重建（全量检查归档后）", "info")
                elif added:
                    # 归档成功但索引重建失败：提示但不阻塞归档结果
                    self._db.add_log(f"assfonts 索引自动重建失败: {idx_msg}", "warning")
                self._db.set_last_scan_time()  # 记录「上次全量检查」时间（仪表盘展示）
                return self._ok(
                    {"added": added, "index_ok": idx_ok},
                    f"已归档 {added} 个字体" + ("，assfonts 索引已自动重建" if idx_ok else ""),
                )
            # 「目录自动收集」关闭：加入待确认列表等待一键整理
            scan_mode = self.get_resource_or_config("scan_mode") or "internal"
            lib_dir = self.get_resource_or_config("lib_dir") or ""
            added = 0
            skipped = 0
            try:
                # 诊断日志：打印实际扫描路径与目录内容，便于定位「配置了目录却扫不到文件」
                try:
                    all_entries = list(Path(input_dir).iterdir())
                    self._db.add_log(
                        f"检查归档诊断: 扫描 {input_dir}，目录共 {len(all_entries)} 项："
                        + (", ".join(e.name for e in all_entries[:20]) if all_entries else "(目录为空)"),
                        "info",
                    )
                except Exception as err:
                    self._db.add_log(f"检查归档诊断: 读取 {input_dir} 失败: {err}", "error")
                    all_entries = []
                for f in all_entries:
                    # 优雅停止：当前条放入待确认后就不再继续
                    try:
                        if self._stopping or not self._enabled:
                            break
                    except Exception:
                        pass
                    if not f.is_file() or not is_font_file(f.name):
                        continue
                    # 跳过已归档到字体库的文件
                    if lib_dir and _path_within(f, Path(lib_dir)):
                        continue
                    # 已在待确认列表中的同一文件不重复加入（重复点击/双观察者幂等）
                    try:
                        if self._db.query_one(
                            "SELECT id FROM pending_fonts WHERE file_path = ?", (str(f),)
                        ):
                            skipped += 1
                            continue
                    except Exception:
                        pass
                    try:
                        meta = parse_font_metadata(f, scan_mode=scan_mode, filename_hint=f.stem)
                    except Exception:
                        meta = {"name": f.stem, "family": f.stem, "vendor": "未知厂商", "designer": ""}
                    self._db.add_pending(
                        {
                            "file_name": f.name,
                            "file_path": str(f),
                            "name": meta["name"],
                            "family": meta["family"],
                            "vendor": meta["vendor"],
                            "designer": meta["designer"],
                            "file_size": f.stat().st_size,
                        }
                    )
                    added += 1
                self._db.add_log(f"检查归档：发现 {added} 个新字体（已加入待确认，目录自动收集已关闭）", "info")
                return self._ok({"added": added, "skipped": skipped}, f"发现 {added} 个新字体")
            except Exception as err:
                self._db.add_log(f"检查归档失败: {err}", "error")
                return self._err(f"检查归档失败: {err}")
        finally:
            self._scan_lock.release()

    def api_scan_archive_all(self) -> Dict[str, Any]:
        """全量扫描：递归扫描字体监控目录中的全部字体，已入库同名/同路径跳过，未入库直接归档进字体库。

        供检查页「全量扫描」按钮手动触发，弥补「监控只处理新增」后存量字体无入口的问题。
        复用 _archive_from_dir → _archive_font_file（含 v1.0.50 同名去重），幂等不生成副本。
        运行期间互斥：重复触发直接返回「正在运行」，不并发处理。
        """
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        input_dir = self.get_resource_or_config("input_dir") or ""
        if not input_dir:
            return self._err("请先在设置中配置字体监控目录")
        if not Path(input_dir).is_dir():
            return self._err("字体监控目录不存在")
        lib_dir = self.get_resource_or_config("lib_dir") or ""
        if not lib_dir:
            return self._err("请先在设置中配置字体库目录（归档落点）")
        if not self._scan_lock.acquire(blocking=False):
            return self._err("全量扫描正在运行中，请等待本次完成后再试")
        try:
            added = self._archive_from_dir(Path(input_dir), source="scan")
            self._db.add_log(f"全量扫描：处理 {added} 个字体", "info")
            if self.get_resource_or_config("notify_enabled"):
                self._notify("字体分类管家：全量扫描完成", f"✅ 全量扫描完成\n已处理 {added} 个字体（已入库同名跳过）")
            return self._ok({"added": added}, f"全量扫描完成，已处理 {added} 个字体")
        except Exception as err:
            self._db.add_log(f"全量扫描失败: {err}", "error")
            return self._err(f"全量扫描失败: {err}")
        finally:
            self._scan_lock.release()

    def api_ass_scan_all(self) -> Dict[str, Any]:
        """全量扫描：递归扫描 ASS 字幕目录中的全部 .ass 并检查（按 file_path upsert 幂等，不会新增重复记录）。

        供检查页「全量扫描」按钮手动触发，弥补存量字幕无检查入口的问题。
        """
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        ass_dir = self.get_resource_or_config("ass_dir") or ""
        if not ass_dir:
            return self._err("请先在设置中配置ASS字幕目录监控")
        if not Path(ass_dir).is_dir():
            return self._err("ASS字幕目录监控不存在")
        try:
            files = [
                f
                for f in Path(ass_dir).rglob("*.ass")
                if f.is_file() and not self._is_system_hidden_path(f)
            ]
            if not files:
                self._db.add_log(f"全量扫描字幕：{ass_dir} 下无 ASS 文件", "info")
                self._db.set_last_scan_time()  # 无条件算一次全量检查
                return self._ok({"checked": 0}, "字幕目录无 ASS 文件")
            checked = 0
            missing_total = 0
            for f in files:
                result = self._check_ass_file(f, source="scan")
                if result:
                    checked += 1
                    missing_total += int(result.get("missing_count") or 0)
            self._db.add_log(
                f"全量扫描字幕：检查 {checked} 个，共缺 {missing_total} 种字体",
                "warning" if missing_total else "info",
            )
            if self.get_resource_or_config("notify_enabled"):
                self._notify(
                    "字体分类管家：全量扫描完成",
                    f"✅ 字幕全量扫描完成\n已检查 {checked} 个字幕，缺失 {missing_total} 种字体",
                )
            self._db.set_last_scan_time()  # 记录「上次全量检查」时间（仪表盘展示）
            return self._ok({"checked": checked, "missing_total": missing_total}, f"已检查 {checked} 个字幕")
        except Exception as err:
            self._db.add_log(f"全量扫描字幕失败: {err}", "error")
            return self._err(f"全量扫描字幕失败: {err}")

    # ─── API：ASS 字幕检查 ─────────────────────────────
    def api_ass_list(self, page: int = 1, limit: int = 20, search: str = "") -> Dict[str, Any]:
        """ASS 检查记录列表（实时重算缺失/子集化，与字体库删减即时同步）"""
        if not self._db_ok():
            return self._ok({"list": [], "total": 0})
        self._prune_stale_records()
        try:
            data = self._db.query_ass(keyword=(search or "").strip(), page=page, limit=limit)
            families, match_source = self._lib_font_keys()
            # 匹配来源提升到顶层：列表为空（无记录）时前端也能显示「匹配基准」提示
            data["match_source"] = match_source
            for r in data.get("list", []):
                # 匹配来源透传（index=assfonts 子集索引 / db=字体库记录，索引未构建时回退）
                r["match_source"] = match_source
                # 子集化/缺失结果以「检查」为准：待检查（pending）状态不预判，
                # 只有手动点检查或开启自动监控（auto_check）检查后才展示
                if r.get("status") == "pending":
                    r["subsetted"] = False
                    continue
                try:
                    row = self._db.get_ass(r["id"])
                    if not row:
                        continue
                    all_fonts = row.get("all_fonts") or []
                    fp = row.get("file_path") or ""
                    subsetted = bool(
                        fp and Path(fp).is_file() and has_embedded_fonts(Path(fp).read_bytes())
                    )
                    missing_live: List[str] = []
                    seen_k: set = set()
                    for f in all_fonts:
                        k = normalize_font_key(f)
                        if not k or k in seen_k:
                            continue
                        seen_k.add(k)
                        if k not in families:
                            missing_live.append(f)
                    # 已内嵌（子集化）字幕：即使字体库删减也不报缺失
                    if subsetted:
                        missing_live = []
                    r["missing_count"] = len(missing_live)
                    r["status"] = "missing" if missing_live else "ok"
                    r["subsetted"] = subsetted
                except Exception:
                    r["subsetted"] = False
            return self._ok(data)
        except Exception as err:
            return self._err(f"查询检查记录失败: {err}")

    async def api_ass_upload(self, request: Request) -> Dict[str, Any]:
        """上传 ASS 字幕：仅保存字幕内容到临时目录并创建记录（不检查），需手动点“检查”"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        try:
            form = await request.form()
        except Exception as err:
            return self._err(f"读取上传表单失败: {err}")
        upload_files = []
        try:
            files = form.getlist("file")
            if files:
                upload_files = files
        except Exception:
            pass
        if not upload_files:
            return self._err("请选择要上传的 ASS 文件")
        done: List[Dict[str, Any]] = []
        for upload in upload_files:
            file_name = getattr(upload, "filename", "") or ""
            if not is_ass_file(file_name):
                continue
            try:
                raw = await upload.read()
            except Exception:
                continue
            if not raw:
                continue
            # 保存字幕内容到临时目录，供后续手动检查
            safe_name = Path(file_name).name
            tmp_path = Path(self._tmp_dir) / f"{uuid.uuid4().hex}_{safe_name}"
            try:
                tmp_path.write_bytes(raw)
            except Exception:
                continue
            # 双轨制：手动上传不自动检查，仅登记待检查记录
            self._db.add_ass(
                file_name=safe_name,
                source="manual",
                status="pending",
                missing_fonts=[],
                all_fonts=[],
                file_path=str(tmp_path),
            )
            row = self._db.query_one(
                "SELECT id FROM ass_files WHERE file_path = ? ORDER BY id DESC LIMIT 1",
                (str(tmp_path),),
            )
            self._db.add_log(f"字幕已上传待检查: {safe_name}", "info")
            done.append(
                {
                    "id": row["id"] if row else 0,
                    "file_name": safe_name,
                    "status": "pending",
                    "missing_count": 0,
                }
            )
        if not done:
            return self._err("没有可上传的有效 ASS 文件（需 .ass 后缀且内容非空）")
        return self._ok({"count": len(done), "items": done}, f"已上传 {len(done)} 个字幕，请在列表中手动检查")

    async def api_ass_check(self, request: Request) -> Dict[str, Any]:
        """手动检查：按记录 id 重新解析字幕文件并与字体库对比"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        try:
            body = await request.json() if hasattr(request, "json") else {}
        except Exception:
            body = {}
        ass_id = body.get("id")
        if not ass_id:
            return self._err("缺少记录ID")
        try:
            row = self._db.get_ass(int(ass_id))
            if not row:
                return self._err("记录不存在")
            src_path = row.get("file_path") or ""
            if not src_path or not Path(src_path).is_file():
                return self._err("字幕文件不存在，可能已被清理，请重新上传")
            raw = Path(src_path).read_bytes()
            all_fonts = parse_ass_fonts(raw)
            subsetted = has_embedded_fonts(raw)
            families, match_source = self._lib_font_keys()
            missing = [f for f in all_fonts if normalize_font_key(f) not in families]
            # 已内嵌（子集化）字幕自带字体：播放不依赖字体库，不再报缺失
            if subsetted and missing:
                missing = []
            status = "ok" if not missing else "missing"
            self._db.update_ass(int(ass_id), status, missing, all_fonts)
            text = "缺 " + str(len(missing)) + " 个字体" if missing else "字体完整"
            self._db.add_log(f"手动检查: {row['file_name']} → {text}", "warning" if missing else "info")
            return self._ok(
                {
                    "id": int(ass_id),
                    "file_name": row["file_name"],
                    "status": status,
                    "status_text": text,
                    "missing_count": len(missing),
                    "all_fonts": [{"name": f, "in_lib": normalize_font_key(f) in families} for f in all_fonts],
                    "missing_fonts": missing,
                    "subsetted": subsetted,
                    "match_source": match_source,
                },
                "检查完成",
            )
        except Exception as err:
            return self._err(f"检查失败: {err}")

    def api_ass_detail(self, id: int = 0) -> Dict[str, Any]:
        """ASS 检查详情"""
        if not self._db_ok():
            return self._err("数据库未初始化")
        if not id:
            return self._err("缺少记录ID")
        try:
            row = self._db.get_ass(id)
            if not row:
                return self._err("记录不存在")
            # 实时重算：以当前字体库为准，缺失字体/命中标记/子集化随库内变化即时更新
            # （用户从检查页上传缺失字体入库后，红色缺失标记直接消除，无需重新检查）
            stored_all = row.get("all_fonts") or []
            # 子集化/缺失结果以「检查」为准：待检查状态不做预判
            subsetted = False
            if row.get("status") != "pending":
                fp = row.get("file_path") or ""
                if fp and Path(fp).is_file():
                    try:
                        subsetted = has_embedded_fonts(Path(fp).read_bytes())
                    except Exception:
                        pass
            families, match_source = self._lib_font_keys()
            if stored_all:
                # 缺失清单按归一化 key 去重（@竖排变体与本体同 key 只算一次）
                seen_k: set = set()
                missing_live: List[str] = []
                for f in stored_all:
                    k = normalize_font_key(f)
                    if not k or k in seen_k:
                        continue
                    seen_k.add(k)
                    if k not in families:
                        missing_live.append(f)
                # 已内嵌（子集化）字幕：即使字体库删减也不报缺失
                if subsetted:
                    missing_live = []
                    row["status"] = "ok"
                else:
                    row["status"] = "missing" if missing_live else "ok"
                row["all_fonts"] = [{"name": f, "in_lib": normalize_font_key(f) in families} for f in stored_all]
                row["missing_fonts"] = missing_live
                row["missing_count"] = len(missing_live)
            else:
                row["all_fonts"] = []
                row["missing_fonts"] = []
                row["missing_count"] = 0
            row["match_source"] = match_source
            row["subsetted"] = subsetted
            return self._ok(row)
        except Exception as err:
            return self._err(f"读取详情失败: {err}")

    def api_ass_delete(self, id: int = 0) -> Dict[str, Any]:
        """删除单条检查记录"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        if not id:
            return self._err("缺少记录ID")
        try:
            row = self._db.get_ass(id)
            self._db.delete_ass(id)
            # MP 入库（inbound）记录的 ass 属于媒体库文件：只删记录不删文件；
            # 目录监控/手动上传的记录连同文件一起删
            if row and row.get("file_path") and row.get("source") != "inbound":
                try:
                    Path(row["file_path"]).unlink(missing_ok=True)
                except Exception:
                    pass
            return self._ok({}, "已删除")
        except Exception as err:
            return self._err(f"删除失败: {err}")

    def api_ass_clear(self) -> Dict[str, Any]:
        """清空全部检查记录（同时删除记录对应的临时字幕文件）"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        try:
            for r in self._db.query(
                "SELECT file_path FROM ass_files WHERE file_path != '' AND source != 'inbound'"
            ):
                if r.get("file_path"):
                    try:
                        Path(r["file_path"]).unlink(missing_ok=True)
                    except Exception:
                        pass
            self._db.clear_ass()
            self._db.add_log("清空全部ASS检查记录", "warning")
            return self._ok({}, "已清空")
        except Exception as err:
            return self._err(f"清空失败: {err}")

    # ─── API：子集化（assfonts）─────────────────────────
    def api_subset_index(self) -> Dict[str, Any]:
        """assfonts 状态：二进制是否存在 + 字体索引状态"""
        if not self._db_ok():
            return self._err("数据库未初始化")
        binary = self._subset_binary()
        lib_dir_cfg = self.get_resource_or_config("lib_dir") or ""
        index = af.index_info(self._assfonts_idx, lib_dir_cfg) if self._assfonts_idx else {"exists": False, "count": 0, "mtime": "", "size": 0}
        return self._ok(
            {
                "binary_ok": binary is not None,
                "binary_path": str(binary) if binary else "",
                "index": index,
                "lib_dir": lib_dir_cfg,
            },
            "assfonts 状态",
        )

    def api_subset_rebuild_index(self) -> Dict[str, Any]:
        """重建 assfonts 字体索引（-b）：扫描字体库目录生成 fonts.json"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        binary = self._subset_binary()
        if not binary:
            return self._err("bin/assfonts 不存在或不可执行（assfonts 随插件分发，请重新部署）")
        lib_dir = self.get_resource_or_config("lib_dir") or ""
        if not lib_dir:
            return self._err("请先在设置中配置字体库目录（子集化字体来源）")
        if self._assfonts_idx is None:
            self._assfonts_idx = Path(self.get_data_path()) / "assfonts_idx"
            Path(self._assfonts_idx).mkdir(parents=True, exist_ok=True)
        if not self._scan_lock.acquire(blocking=False):
            return self._err("正在处理中，请等待当前任务完成")
        try:
            ok, msg = self._rebuild_subset_index_silent()
            if not ok:
                return self._err(f"重建索引失败: {msg}")
            self._db.add_log(f"assfonts 索引已重建（{lib_dir}）", "info")
            if self.get_resource_or_config("notify_enabled"):
                self._notify("字体分类管家：索引重建完成", "✅ assfonts 字体索引已重建，缺失字体可重新子集化")
            return self._ok(af.index_info(self._assfonts_idx, lib_dir), "索引已重建")
        finally:
            self._scan_lock.release()

    def _rebuild_subset_index_silent(self) -> Tuple[bool, str]:
        """重建 assfonts 索引（尽力而为，不抛异常，失败仅返回错误信息）。

        字体归档/全量检查后调用，让新入库字体立即可被子集化引用；
        返回 (ok, msg)。调用方需自行持有 _scan_lock（或确认无并发冲突）。
        """
        try:
            binary = self._subset_binary()
            if not binary:
                return False, "bin/assfonts 不存在或不可执行"
            lib_dir = self.get_resource_or_config("lib_dir") or ""
            if not lib_dir or not Path(lib_dir).is_dir():
                return False, "字体库目录未配置或不可达"
            if self._assfonts_idx is None:
                self._assfonts_idx = Path(self.get_data_path()) / "assfonts_idx"
                Path(self._assfonts_idx).mkdir(parents=True, exist_ok=True)
            try:
                found = [
                    f
                    for f in Path(lib_dir).rglob("*")
                    if f.is_file() and f.suffix.lower() in (".ttf", ".otf", ".ttc", ".woff", ".woff2")
                ]
                # 只报数量，不列举文件名——字体库上千个文件时逐名列出会刷屏
                self._db.add_log(
                    f"索引构建诊断: 字体库目录 {lib_dir} 共发现 {len(found)} 个字体文件"
                    + ("（目录内无字体文件）" if not found else ""),
                    "info",
                )
            except Exception:
                pass
            result = af.build_index(binary, [lib_dir], self._assfonts_idx)
            # 索引（重）构建完成后清键集缓存，检查侧立即命中新归档字体
            self._index_font_cache = None
            return result
        except Exception as err:
            return False, str(err)

    def api_subset_all(self) -> Dict[str, Any]:
        """全量子集化：处理「待处理」列表中的全部字幕（上传的 + 目录监控收进来的），
        跳过已子集化的，逐条子集化并内嵌字体；完成后清空待处理、结果进记录列表。"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        if self._tmp_dir is None:
            return self._err("插件临时目录未初始化")
        binary = self._subset_binary()
        if not binary:
            return self._err("bin/assfonts 不存在或不可执行（assfonts 随插件分发，请重新部署）")
        if not self._scan_lock.acquire(blocking=False):
            return self._err("全量子集化正在运行中，请等待本次完成后再试")
        try:
            pending = self._db.list_subset_pending()

            def _collect(rows):
                out = []
                for r in rows:
                    p = Path(r.get("file_path") or "")
                    if p.is_file() and is_ass_file(p.name):
                        out.append(p)
                return out

            # 待处理区分来源身份：上传（manual）→ 成品留临时目录、始终不保留子集字体夹；
            # 目录监控收集（watch）→ 按「监控目录输出方式」同步到输出目录并按剧名分子文件夹
            watch_files = _collect([r for r in pending if r.get("source") == "watch"])
            manual_files = _collect([r for r in pending if r.get("source") != "watch"])
            if not (watch_files or manual_files):
                return self._ok({"success": 0, "skipped": 0, "missing": 0, "error": 0}, "待处理列表为空（可上传字幕，或开启「目录监控」自动收集）")
            stats: Dict[str, Any] = {"success": 0, "skipped": 0, "missing": 0, "error": 0, "missing_fonts": [], "file_status": {}}
            for batch, src in ((manual_files, "manual"), (watch_files, "watch")):
                if not batch:
                    continue
                sub = self._run_subset_batch(batch, source=src)
                for k in ("success", "skipped", "missing", "error"):
                    stats[k] += sub.get(k, 0)
                stats["missing_fonts"].extend(sub.get("missing_fonts") or [])
                stats["file_status"].update(sub.get("file_status") or {})
            # 处理完成：移除待处理记录；上传到临时目录的缓存源文件仅成功/跳过才清理，
            # 缺字体/失败（file_status=keep）保留供「重试失败」补字后再次处理
            keep_map = stats.get("file_status") or {}
            for r in pending:
                try:
                    self._db.delete_subset_pending(r["id"])
                except Exception:
                    pass
                fp = Path(r.get("file_path") or "")
                if self._tmp_dir and str(fp.resolve()).startswith(str(Path(self._tmp_dir).resolve())):
                    try:
                        if keep_map.get(str(fp.resolve())) != "keep":
                            fp.unlink(missing_ok=True)
                    except Exception:
                        pass
            self._db.add_log(
                f"全量子集化: 成功 {stats['success']}, 跳过 {stats['skipped']}, "
                f"缺字体 {stats['missing']}, 失败 {stats['error']}",
                "info",
            )
            self._notify_subset_result(stats)
            return self._ok(stats, f"全量子集化完成，成功 {stats['success']} 个")
        except Exception as err:
            self._db.add_log(f"全量子集化失败: {err}", "error")
            return self._err(f"全量子集化失败: {err}")
        finally:
            self._scan_lock.release()

    def _subset_record_missing_names(self, reason: str) -> List[str]:
        """从缺字体 reason（如「缺字体: 方正准圆_GBK、華康粗黑體」）解析字体名列表"""
        text = (reason or "").replace("缺字体:", "")
        names: List[str] = []
        for part in re.split(r"[、,，]", text):
            part = part.strip()
            if part:
                names.append(part)
        return names

    def _subset_record_retryable(self, reason: str) -> bool:
        """缺字体的字幕是否已可重试：reason 中所有字体都已被字体库收录（含刚归类的）"""
        names = self._subset_record_missing_names(reason)
        if not names:
            return False
        try:
            # 与检查侧同一基准（assfonts 索引优先，回退字体库记录）
            families, _src = self._lib_font_keys()
            return all(normalize_font_key(n) in families for n in names)
        except Exception:
            return False

    def api_subset_records(self, status: str = "", search: str = "", page: int = 1, limit: int = 20) -> Dict[str, Any]:
        """子集化处理记录列表（status 过滤 + 文件名搜索 + 分页）

        - status=missing：缺的字体未全部入库（仍缺，标签「缺字体」）
        - status=retryable：缺的字体已全部入库（标签「可重试」）
        - 两者互斥不重叠；其余记录附加 retryable 标记供前端显示
        """
        if not self._db_ok():
            return self._ok({"list": [], "total": 0})
        try:
            page = max(int(page), 1)
            raw_limit = int(limit)
            # limit<=0 表示拉取当前筛选下的全部记录（「全部下载」用），不限页
            limit = 100000 if raw_limit <= 0 else max(raw_limit, 1)
            if status in ("missing", "retryable"):
                # 拉取全部 missing → 按是否已补齐分流 → 手动分页
                raw = self._db.list_subset_records(status="missing", keyword=search, page=1, limit=100000)
                items = []
                for r in raw.get("list") or []:
                    ok = self._subset_record_retryable(r.get("reason") or "")
                    r["retryable"] = ok
                    if (status == "retryable") == ok:
                        items.append(r)
                total = len(items)
                offset = (page - 1) * limit
                return self._ok({"list": items[offset:offset + limit], "total": total, "retriable": raw.get("retriable", 0)})
            data = self._db.list_subset_records(status=status, keyword=search, page=page, limit=limit)
            for r in data.get("list") or []:
                r["retryable"] = bool(r.get("status") == "missing") and self._subset_record_retryable(r.get("reason") or "")
            return self._ok(data)
        except Exception:
            return self._ok({"list": [], "total": 0})

    def api_subset_download(self, id: int = 0) -> Dict[str, Any]:
        """下载子集化结果文件（base64，前端转 Blob 下载）"""
        if not id:
            return self._err("缺少记录ID")
        try:
            row = self._db.query_one("SELECT * FROM subset_records WHERE id = ?", (int(id),))
            if not row:
                return self._err("记录不存在")
            out = row.get("out_file") or ""
            if not out or not Path(out).is_file():
                return self._err("结果文件不存在或已被清理")
            data = base64.b64encode(Path(out).read_bytes()).decode("ascii")
            return self._ok(
                {"name": Path(out).name, "data": data, "size": Path(out).stat().st_size},
                "下载成功",
            )
        except Exception as err:
            return self._err(f"下载失败: {err}")

    def api_subset_pending_list(self) -> Dict[str, Any]:
        """子集化待处理列表"""
        if not self._db_ok():
            return self._ok([])
        try:
            return self._ok(self._db.list_subset_pending())
        except Exception:
            return self._ok([])

    async def api_subset_pending_upload(self, request: Request) -> Dict[str, Any]:
        """上传字幕到子集化待处理（支持多选，存临时目录）"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        try:
            form = await request.form()
        except Exception as err:
            return self._err(f"读取上传表单失败: {err}")
        upload_files = []
        try:
            files = form.getlist("file")
            if files:
                upload_files = files
        except Exception:
            pass
        if not upload_files:
            return self._err("请选择要上传的字幕文件")
        done = []
        for upload in upload_files:
            file_name = getattr(upload, "filename", "") or ""
            if not is_ass_file(file_name):
                continue
            try:
                raw = await upload.read()
            except Exception:
                continue
            if not raw:
                continue
            safe_name = Path(file_name).name
            tmp_path = Path(self._tmp_dir) / f"subset_{uuid.uuid4().hex}_{safe_name}"
            try:
                tmp_path.write_bytes(raw)
            except Exception:
                continue
            pid = self._db.add_subset_pending(safe_name, str(tmp_path), source="upload")
            done.append({"id": pid, "file_name": safe_name})
        if not done:
            return self._err("没有可上传的字幕文件（需 .ass 后缀且内容非空）")
        return self._ok({"count": len(done), "items": done}, f"已加入待处理 {len(done)} 个字幕")

    def api_subset_pending_remove(self, id: int = 0) -> Dict[str, Any]:
        """移除单条待处理（x 按钮）；临时目录的上传文件一并删除"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not id:
            return self._err("缺少记录ID")
        try:
            row = self._db.query_one("SELECT * FROM subset_pending WHERE id = ?", (int(id),))
            if row and row.get("file_path"):
                fp = Path(row["file_path"])
                # 仅删除插件临时目录内的上传缓存，监控目录里的原字幕不动
                if self._tmp_dir and str(fp.resolve()).startswith(str(Path(self._tmp_dir).resolve())):
                    try:
                        fp.unlink(missing_ok=True)
                    except Exception:
                        pass
            self._db.delete_subset_pending(int(id))
            return self._ok({}, "已移除")
        except Exception as err:
            return self._err(f"移除失败: {err}")

    def api_subset_pending_clear(self) -> Dict[str, Any]:
        """清空待处理（临时目录上传文件一并清理）"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        try:
            for row in self._db.list_subset_pending():
                if row.get("file_path"):
                    fp = Path(row["file_path"])
                    if self._tmp_dir and str(fp.resolve()).startswith(str(Path(self._tmp_dir).resolve())):
                        try:
                            fp.unlink(missing_ok=True)
                        except Exception:
                            pass
            self._db.clear_subset_pending()
            return self._ok({}, "已清空待处理")
        except Exception as err:
            return self._err(f"清空失败: {err}")

    def _subset_out_deletable(self, out_path: str) -> bool:
        """子集化成成品文件是否可随记录删除（删除记录时同步删输出产物）：
        输出目录 / 上传临时目录 / ASS字幕目录监控 / 子集目录监控 内的产物可删
        ——这些是「监控/上传」来源，源字幕在监控目录或临时目录不受影响；
        媒体库等其他外部路径是「MP 入库」来源，入库字幕已落地媒体库，即使删记录也
        不能动媒体库里的成品文件（用户声明：入库的删记录不影响已入库字幕）。"""
        if not out_path:
            return False
        try:
            p = Path(out_path)
            for b in (
                self._tmp_dir,
                self.get_resource_or_config("subset_out_dir") or "",
                self.get_resource_or_config("ass_dir") or "",
                self.get_resource_or_config("subset_dir") or "",
            ):
                if b and _path_within(p, Path(b)):
                    return True
        except Exception:
            pass
        return False

    def _prune_empty_show_dir(self, out_path: Path) -> None:
        """输出目录按剧名单生成的子文件夹清空后删除（监控输出方式=移动、删记录清产物后常见）。"""
        try:
            base = self.get_resource_or_config("subset_out_dir") or ""
            if not base:
                return
            base_p = Path(base)
            parent = out_path.parent
            # 只在「输出目录的子文件夹」层面清理（剧名层/更深），不动输出目录本身
            if parent != base_p and _path_within(parent, base_p):
                if not any(parent.iterdir()):
                    parent.rmdir()
        except Exception:
            pass

    def _remove_subset_output_files(self, row: Dict[str, Any]) -> None:
        """删除一条子集化记录对应的输出产物（仅限可删区域，媒体库成品不动）。
        补删同名 <stem>_subsetted 备份夹（也在可删区域时），避免只删成品留夹子；
        输出目录按剧名的子文件夹清空后一并删除（移动模式下不留空夹）。"""
        out = str(row.get("out_file") or "")
        if not out or not self._subset_out_deletable(out):
            return
        try:
            Path(out).unlink(missing_ok=True)
            # 同行 <stem>_subsetted 备份夹：仅当夹子也在可删区域（输出/临时/监控目录）时删除，
            # assfonts 在源目录生成该夹只是备份，随记录删除产物时一并清掉
            stem = out[:-4] if out.lower().endswith(".ass") else out
            sub = Path(stem + "_subsetted")
            if sub.is_dir() and self._subset_out_deletable(str(sub)):
                shutil.rmtree(sub, ignore_errors=True)
            # 输出目录/<剧名>/ 空文件夹清理
            self._prune_empty_show_dir(Path(out))
        except Exception:
            pass

    def api_subset_record_delete(self, id: int = 0) -> Dict[str, Any]:
        """删除单条子集化记录（监控/上传来历的记录同步删除输出产物；入库记录只删记录不动媒体库文件）"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        if not id:
            return self._err("缺少记录ID")
        try:
            row = self._db.query_one("SELECT * FROM subset_records WHERE id = ?", (int(id),))
            if row:
                self._remove_subset_output_files(row)
            self._db.delete_subset_record(int(id))
            return self._ok({}, "已删除")
        except Exception as err:
            return self._err(f"删除失败: {err}")

    def api_subset_records_clear(self) -> Dict[str, Any]:
        """清空子集化记录（监控/上传来历的记录同步删除输出产物；入库记录只删记录不动媒体库文件）"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        try:
            for r in self._db.query("SELECT * FROM subset_records"):
                self._remove_subset_output_files(r)
            self._db.clear_subset_records()
            return self._ok({}, "已清空")
        except Exception as err:
            return self._err(f"清空失败: {err}")

    def api_subset_retry(self) -> Dict[str, Any]:
        """重试失败/缺字体的子集化：收集 subset_records 中 missing/error 且源字幕仍存在的文件，重新子集化。

        补好缺失字体后可一键重跑——MP 入库缺字体 / 手动全量子集化失败的字幕不再需要重新上传。
        与页面全量子集化互斥（_scan_lock）。
        """
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        binary = self._subset_binary()
        if not binary:
            return self._err("bin/assfonts 不存在或不可执行（assfonts 随插件分发，请重新部署）")
        if not self._scan_lock.acquire(blocking=False):
            return self._err("正在处理中，请等待当前任务完成")
        try:
            rows = self._db.query(
                "SELECT * FROM subset_records WHERE status IN ('missing', 'error') ORDER BY id DESC"
            )
            files: List[Path] = []
            seen = set()
            for r in rows:
                fp = r.get("file_path") or ""
                if not fp or fp in seen:
                    continue
                p = Path(fp)
                if p.is_file() and is_ass_file(p.name):
                    seen.add(fp)
                    files.append(p)
            if not files:
                return self._ok(
                    {"success": 0, "skipped": 0, "missing": 0, "error": 0, "retried": 0},
                    "没有可重试的字幕（失败/缺字体记录的源文件不存在或已处理）",
                )
            st = self._run_subset_batch(files, source="retry")
            self._db.add_log(
                f"重试失败子集化: 重试 {len(files)} 个，成功 {st['success']}，缺字体 {st['missing']}，失败 {st['error']}",
                "info",
            )
            self._notify_subset_result(st, scope="重试")
            return self._ok({**st, "retried": len(files)}, f"重试完成：成功 {st['success']} 个")
        except Exception as err:
            self._db.add_log(f"重试失败子集化出错: {err}", "error")
            return self._err(f"重试失败: {err}")
        finally:
            self._scan_lock.release()

    # ─── API：缺失字体（统一管理页：检查缺失 + 子集化缺失）────────
    def _subset_missing_agg(self) -> List[Dict[str, Any]]:
        """聚合子集化因缺字体跳过的字体：{name: 出现次数}，按下限排序。

        实时按当前字体库重算——已上传归类（字体入库）的字体自动从缺失中消失，
        无需等到重试子集化才更新；@竖排前缀等归一化 key 与检查侧一致。
        """
        agg: Dict[str, int] = {}
        shown: Dict[str, str] = {}
        try:
            # 与检查侧同一基准（assfonts 索引优先，回退字体库记录）：
            # 索引可用时字体在库即命中，避免「入库了索引没重建」被误列为缺失
            families, _src = self._lib_font_keys()
            rows = self._db.query(
                "SELECT reason FROM subset_records WHERE status = 'missing' AND reason != ''"
            )
            for r in rows:
                text = (r.get("reason") or "").replace("缺字体:", "")
                for name in re.split(r"[、,，]", text):
                    name = name.strip()
                    if not name:
                        continue
                    key = normalize_font_key(name)
                    if not key or key in families:
                        continue
                    agg[key] = agg.get(key, 0) + 1
                    if key not in shown:
                        shown[key] = name
        except Exception:
            pass
        return [
            {"name": shown.get(k, k), "count": v}
            for k, v in sorted(agg.items(), key=lambda kv: (-kv[1], kv[0]))
        ]

    def api_missing_summary(self) -> Dict[str, Any]:
        """缺失字体汇总：check=检查页检测的缺失，subset=子集化因缺字体跳过的"""
        if not self._db_ok():
            return self._err("数据库未初始化")
        try:
            check = [
                {"name": v["name"], "count": v["count"]}
                for v in sorted(self._ass_missing_agg().values(), key=lambda x: -x["count"])
            ]
            subset = self._subset_missing_agg()
            return self._ok(
                {
                    "check": check,
                    "subset": subset,
                    "lib_dir": self.get_resource_or_config("lib_dir") or "",
                    "binary_ok": self._subset_binary() is not None,
                },
                "缺失字体汇总",
            )
        except Exception as err:
            return self._err(f"获取缺失字体汇总失败: {err}")

    def api_missing_uploads(self) -> Dict[str, Any]:
        """已上传待归类的字体列表"""
        lst = []
        for path, item in (self._missing_uploads or {}).items():
            lst.append(
                {
                    "path": path,
                    "file_name": item.get("file_name", ""),
                    "name": item.get("name", ""),
                    "family": item.get("family", ""),
                    "vendor": item.get("vendor", "未知厂商"),
                    "file_size": item.get("file_size", 0),
                }
            )
        return self._ok(lst)

    async def api_missing_upload(self, request: Request) -> Dict[str, Any]:
        """缺失字体页上传字体（不校验匹配，归类时统一入库）"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        try:
            form = await request.form()
        except Exception as err:
            return self._err(f"读取上传表单失败: {err}")
        upload_files = []
        try:
            files = form.getlist("file")
            if files:
                upload_files = files
        except Exception:
            pass
        if not upload_files:
            return self._err("请选择要上传的字体文件")
        scan_mode = self.get_resource_or_config("scan_mode") or "internal"
        done = []
        for upload in upload_files:
            file_name = getattr(upload, "filename", "") or ""
            if not is_font_file(file_name):
                continue
            try:
                raw = await upload.read()
            except Exception:
                continue
            if not raw:
                continue
            safe_name = Path(file_name).name
            tmp_path = Path(self._tmp_dir) / f"missing_{uuid.uuid4().hex}_{safe_name}"
            try:
                tmp_path.write_bytes(raw)
            except Exception:
                continue
            try:
                meta = parse_font_metadata(tmp_path, scan_mode=scan_mode, filename_hint=Path(file_name).stem)
            except Exception:
                meta = {"name": Path(file_name).stem, "family": Path(file_name).stem, "vendor": "未知厂商", "designer": ""}
            item = {
                "path": str(tmp_path),
                "file_name": safe_name,
                "name": meta.get("name", "") or Path(file_name).stem,
                "family": meta.get("family", "") or Path(file_name).stem,
                "vendor": meta.get("vendor", "未知厂商"),
                "designer": meta.get("designer", ""),
                "file_size": len(raw),
            }
            self._missing_uploads[str(tmp_path)] = item
            done.append(item)
        if not done:
            return self._err("没有可上传的字体文件（需字体后缀且内容非空）")
        return self._ok({"count": len(done), "items": done}, f"已上传 {len(done)} 个字体，可点击「归类」入库")

    def api_missing_uploads_clear(self) -> Dict[str, Any]:
        """清除已上传未归类的字体（删除临时文件）"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        for path in list(self._missing_uploads.keys()):
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass
        self._missing_uploads.clear()
        return self._ok({}, "已清除上传的字体")

    def api_missing_upload_remove(self, path: str = "") -> Dict[str, Any]:
        """删除单条已上传待归类的字体（仅删除临时文件和内存记录，不影响字体库）"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not path:
            return self._err("参数错误")
        if path in self._missing_uploads:
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass
            del self._missing_uploads[path]
            return self._ok({}, "已移除")
        return self._err("未找到该字体记录")

    def api_missing_classify(self) -> Dict[str, Any]:
        """归类：把已上传的字体全部归档入库（同名跳过不覆盖）→ 重建 assfonts 索引 → 通知"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        lib_dir = self.get_resource_or_config("lib_dir") or ""
        if not lib_dir:
            return self._err("请先在设置中配置字体库目录（归档落点）")
        items = list(self._missing_uploads.items())
        if not items:
            return self._err("还没有上传的字体，请先上传")
        if not self._scan_lock.acquire(blocking=False):
            return self._err("正在处理中，请等待当前任务完成")
        try:
            ok_count = 0
            failed: List[str] = []
            for tmp_path, item in items:
                try:
                    src = Path(tmp_path)
                    if not src.is_file():
                        continue
                    vendor = str(item.get("vendor") or "未知厂商")
                    dest_dir = Path(lib_dir) / vendor
                    base = str(item.get("name") or Path(item.get("file_name", "font")).stem)
                    # 按格式分子文件夹归档：字体库/厂商/格式/基础名.后缀
                    fmt_dir = dest_dir / _font_subdir_name(src.suffix)
                    existing = _dest_exists_recursive(dest_dir, base, src.suffix)
                    if existing:
                        # 已存在同名文件（含旧平铺布局与格式子文件夹）：跳过，不覆盖
                        failed.append(f"{item.get('file_name', '')}（字体库已存在 {existing.name}）")
                        self._missing_uploads.pop(tmp_path, None)
                        try:
                            src.unlink(missing_ok=True)
                        except Exception:
                            pass
                        continue
                    try:
                        fmt_dir.mkdir(parents=True, exist_ok=True)
                    except Exception:
                        pass
                    dest = fmt_dir / f"{base}{src.suffix}"
                    shutil.copy2(str(src), str(dest))
                    self._db.add_font(
                        {
                            "name": item.get("name", ""),
                            "family": item.get("family", ""),
                            "vendor": vendor,
                            "designer": item.get("designer", ""),
                            "file_name": dest.name,
                            "file_size": dest.stat().st_size if dest.exists() else 0,
                            "status": "已归档",
                            "source": "manual",
                            "file_path": str(dest),
                        }
                    )
                    self._missing_uploads.pop(tmp_path, None)
                    try:
                        src.unlink(missing_ok=True)
                    except Exception:
                        pass
                    ok_count += 1
                except Exception as err:
                    failed.append(f"{item.get('file_name', '')}（{err}）")
            # 归类后刷新 assfonts 索引，缺失字体即可被子集化使用
            idx_ok = False
            idx_msg = ""
            binary = self._subset_binary()
            if binary and ok_count:
                idx_ok, idx_msg = af.build_index(binary, [lib_dir], self._assfonts_idx)
            self._db.add_log(
                f"缺失字体归类: 入库 {ok_count} 个, 跳过/失败 {len(failed)} 个"
                + (f"，索引{'已刷新' if idx_ok else '刷新失败: ' + idx_msg[:100]}" if ok_count else ""),
                "info" if idx_ok or not ok_count else "warning",
            )
            # 通知：入库结果 + 索引刷新
            if ok_count and self.get_resource_or_config("notify_enabled"):
                lines = [f"✅ 缺失字体已入库 {ok_count} 个"]
                if idx_ok:
                    lines.append("assfonts 索引已自动刷新，请回到「子集化」页重新运行")
                else:
                    lines.append(f"⚠ 索引刷新失败：{idx_msg[:100]}")
                self._notify("字体分类管家：缺失字体入库", "\n".join(lines))
            return self._ok(
                {"classified": ok_count, "failed": failed, "index_ok": idx_ok},
                f"已入库 {ok_count} 个字体" + ("，索引已刷新，可回到「子集化」页重新运行" if idx_ok else ""),
            )
        except Exception as err:
            self._db.add_log(f"缺失字体归类失败: {err}", "error")
            return self._err(f"归类失败: {err}")
        finally:
            self._scan_lock.release()

    # ─── API：缺失字体修复（检查页底部窗口）────────────────
    def _ass_missing_agg(self) -> Dict[str, Dict[str, Any]]:
        """聚合全部已检查记录的缺失字体（实时按当前字体库重算）。

        返回 {归一化key: {"name": 展示名, "count": 出现次数}}；已被当前字体库收录的不计入。
        """
        agg: Dict[str, Dict[str, Any]] = {}
        try:
            families, _fmatch = self._lib_font_keys()  # 与检查列表同口径（索引优先，回退字体库记录）
            for r in self._db.query("SELECT all_fonts, file_path FROM ass_files WHERE all_fonts != '[]'"):
                # 已内嵌（子集化）字幕自带字体，不参与缺失修复聚合
                fp = r.get("file_path") or ""
                try:
                    if fp and Path(fp).is_file() and has_embedded_fonts(Path(fp).read_bytes()):
                        continue
                except Exception:
                    pass
                try:
                    all_fonts = json.loads(r["all_fonts"] or "[]")
                except Exception:
                    continue
                for f in all_fonts or []:
                    k = normalize_font_key(f)
                    if not k or k in families:
                        continue
                    if k in agg:
                        agg[k]["count"] += 1
                    else:
                        agg[k] = {"name": f, "count": 1}
        except Exception:
            pass
        return agg

    def api_ass_missing_list(self) -> Dict[str, Any]:
        """聚合缺失字体列表（自动检查 / 手动检查 / 历史记录汇总）"""
        if not self._db_ok():
            return self._ok({"list": [], "total": 0})
        agg = self._ass_missing_agg()
        lst = [
            {"name": v["name"], "key": k, "count": v["count"]}
            for k, v in sorted(agg.items(), key=lambda kv: -kv[1]["count"])
        ]
        return self._ok({"list": lst, "total": len(lst)})

    async def api_ass_missing_upload(self, request: Request) -> Dict[str, Any]:
        """缺失字体上传：解析元数据并校验与当前缺失名单匹配，匹配才允许入库"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        try:
            form = await request.form()
        except Exception as err:
            return self._err(f"读取上传表单失败: {err}")
        upload_files = []
        try:
            files = form.getlist("file")
            if files:
                upload_files = files
        except Exception:
            pass
        if not upload_files:
            return self._err("请选择要上传的字体文件")
        upload = upload_files[0]
        file_name = getattr(upload, "filename", "") or ""
        if not is_font_file(file_name):
            return self._err(f"不支持的字体文件格式（支持: {', '.join(FONT_EXTENSIONS)}）")
        try:
            raw = await upload.read()
        except Exception as err:
            return self._err(f"读取上传文件失败: {err}")
        if not raw:
            return self._err("上传文件为空")
        safe_name = Path(file_name).name
        tmp_path = Path(self._tmp_dir) / f"{uuid.uuid4().hex}_{safe_name}"
        try:
            tmp_path.write_bytes(raw)
        except Exception as err:
            return self._err(f"保存临时文件失败: {err}")
        scan_mode = self.get_resource_or_config("scan_mode") or "internal"
        try:
            meta = parse_font_metadata(tmp_path, scan_mode=scan_mode, filename_hint=Path(file_name).stem)
        except Exception:
            meta = {"name": Path(file_name).stem, "family": Path(file_name).stem, "vendor": "未知厂商", "designer": ""}
        agg = self._ass_missing_agg()
        matched = ""
        for c in (normalize_font_key(meta.get("name", "")), normalize_font_key(meta.get("family", ""))):
            if c and c in agg:
                matched = agg[c]["name"]
                break
        if not matched:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            return self._err("上传的字体与缺失字体不匹配，无法入库（请先对字幕执行「检查」生成缺失列表）")
        item = {
            "path": str(tmp_path),
            "file_name": safe_name,
            "name": meta.get("name", ""),
            "family": meta.get("family", ""),
            "vendor": meta.get("vendor", "未知厂商"),
            "file_size": len(raw),
            "matched": matched,
        }
        self._missing_uploads[str(tmp_path)] = item
        self._db.add_log(f"缺失字体上传待入库: {safe_name} → {matched}", "info")
        return self._ok(item, f"已识别为缺失字体「{matched}」，点击「入库」加入字体库")

    async def api_ass_missing_confirm(self, request: Request) -> Dict[str, Any]:
        """缺失字体入库：复核匹配后归档进字体库并写库，缺失标记随之消除"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        try:
            body = await request.json() if hasattr(request, "json") else {}
        except Exception:
            body = {}
        path = body.get("path") or ""
        item = self._missing_uploads.get(path)
        if not item:
            return self._err("上传记录不存在或已失效，请重新上传")
        lib_dir = self.get_resource_or_config("lib_dir") or ""
        if not lib_dir:
            return self._err("请先在设置中配置字体库目录")
        src = Path(path)
        if not src.is_file():
            self._missing_uploads.pop(path, None)
            return self._err("临时字体文件不存在，请重新上传")
        # 复核：该字体仍处于缺失名单才允许入库（防止重复入库/不复核误入）
        agg = self._ass_missing_agg()
        matched = item.get("matched", "")
        ok = False
        for c in (normalize_font_key(item.get("name", "")), normalize_font_key(item.get("family", ""))):
            if c and c in agg:
                ok = True
                matched = agg[c]["name"]
                break
        if not ok:
            self._missing_uploads.pop(path, None)
            try:
                src.unlink(missing_ok=True)
            except Exception:
                pass
            return self._err("该字体已不再缺失，无法重复入库")
        try:
            dest_dir = Path(lib_dir) / item.get("vendor", "未知厂商")
            base = str(item.get("name") or Path(item.get("file_name", "font")).stem)
            # 按格式分子文件夹归档：字体库/厂商/格式/基础名.后缀
            fmt_dir = dest_dir / _font_subdir_name(src.suffix)
            existing = _dest_exists_recursive(dest_dir, base, src.suffix)
            if existing:
                return self._err(f"字体库已存在同名字体 {existing.name}，无需重复入库")
            try:
                fmt_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            dest = fmt_dir / f"{base}{src.suffix}"
            archive_mode = self.get_resource_or_config("archive_mode") or "copy"
            if archive_mode == "move":
                shutil.move(str(src), str(dest))
            else:
                shutil.copy2(str(src), str(dest))
                try:
                    src.unlink(missing_ok=True)
                except Exception:
                    pass
        except Exception as err:
            return self._err(f"归档字体失败: {err}")
        try:
            self._db.add_font(
                {
                    "name": item.get("name", ""),
                    "family": item.get("family", ""),
                    "vendor": item.get("vendor", "未知厂商"),
                    "designer": item.get("designer", ""),
                    "file_name": dest.name,
                    "file_size": dest.stat().st_size if dest.exists() else 0,
                    "status": "已归档",
                    "source": "manual",
                    "file_path": str(dest),
                }
            )
        except Exception as err:
            return self._err(f"写库失败: {err}")
        self._missing_uploads.pop(path, None)
        self._db.add_log(f"缺失字体入库: {dest.name}（匹配缺失 {matched}）", "info")
        return self._ok({"path": path, "name": dest.name, "matched": matched}, f"「{matched}」已入库，缺失标记自动消除")

    async def api_ass_missing_cancel(self, request: Request) -> Dict[str, Any]:
        """取消缺失字体上传（删除暂存文件）"""
        try:
            body = await request.json() if hasattr(request, "json") else {}
        except Exception:
            body = {}
        path = body.get("path") or ""
        item = self._missing_uploads.pop(path, None)
        if item and item.get("path"):
            try:
                Path(item["path"]).unlink(missing_ok=True)
            except Exception:
                pass
        return self._ok({}, "已取消")

    def _check_ass_file(self, file_path: Path, source: str = "manual") -> Optional[Dict[str, Any]]:
        try:
            raw = file_path.read_bytes()
            return self._check_ass_content(file_path.name, raw, source=source, file_path=str(file_path))
        except Exception as err:
            self._db.add_log(f"ASS检查失败 {file_path.name}: {err}", "error")
            return None

    def _check_ass_content(self, file_name: str, raw: bytes, source: str = "manual", file_path: str = "") -> Dict[str, Any]:
        """解析 ASS 中引用的字体，与字体库对比，写入记录（按 file_path 幂等，双观察者重复事件不产生重复记录）。"""
        try:
            exist = self._db.query_one(
                "SELECT id FROM ass_files WHERE file_path = ? ORDER BY id DESC LIMIT 1",
                (file_path,),
            )
        except Exception:
            exist = None
        # 「目录自动收集」关闭：目录监控（source=auto）只登记待检查，不自动检查
        if source == "auto" and self.get_resource_or_config("auto_collect") is False:
            if not exist:
                self._db.add_ass(
                    file_name=file_name,
                    source=source,
                    status="pending",
                    missing_fonts=[],
                    all_fonts=[],
                    file_path=file_path,
                )
            return {
                "id": exist["id"] if exist else 0,
                "status": "pending",
                "status_text": "待检查",
                "missing_count": 0,
                "all_fonts": [],
                "missing_fonts": [],
                "subsetted": False,
            }
        all_fonts = parse_ass_fonts(raw)
        subsetted = has_embedded_fonts(raw)
        fam_keys, _fmatch = self._lib_font_keys()
        # 缺失清单按归一化 key 去重（@竖排变体与本体同 key，只算一次），保留首个原始名
        seen: set = set()
        missing: List[str] = []
        for f in all_fonts:
            k = normalize_font_key(f)
            if not k or k in seen:
                continue
            seen.add(k)
            if k not in fam_keys:
                missing.append(f)
        # 已内嵌（子集化）字幕自带字体：播放不依赖字体库，不再报缺失
        if subsetted and missing:
            missing = []
        status = "ok" if not missing else "missing"
        if exist:
            self._db.update_ass(exist["id"], status, missing, all_fonts)
            ass_id = exist["id"]
        else:
            self._db.add_ass(
                file_name=file_name,
                source=source,
                status=status,
                missing_fonts=missing,
                all_fonts=all_fonts,
                file_path=file_path,
            )
            row = self._db.query_one(
                "SELECT id FROM ass_files WHERE file_path = ? ORDER BY id DESC LIMIT 1",
                (file_path,),
            )
            ass_id = row["id"] if row else 0
        return {
            "id": ass_id,
            "status": status,
            "status_text": "缺 " + str(len(missing)) + " 个字体" if missing else "字体完整",
            "missing_count": len(missing),
            "all_fonts": all_fonts,
            "missing_fonts": missing,
            "subsetted": subsetted,
        }

    # ─── API 注册 ───────────────────────────────────────
    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {"path": "/deps/check", "endpoint": self.api_deps_check, "methods": ["GET"], "auth": "bear", "summary": "检测运行依赖是否安装"},
            {"path": "/task/status", "endpoint": self.api_task_status, "methods": ["GET"], "auth": "bear", "summary": "后台任务状态（供前端拦截停用插件）"},
            {"path": "/stats", "endpoint": self.api_stats, "methods": ["GET"], "auth": "bear", "summary": "仪表盘统计"},
            {"path": "/vendors", "endpoint": self.api_vendors, "methods": ["GET"], "auth": "bear", "summary": "厂商分布"},
            {"path": "/logs", "endpoint": self.api_logs, "methods": ["GET"], "auth": "bear", "summary": "最近操作日志"},
            {"path": "/config", "endpoint": self.api_get_config, "methods": ["GET"], "auth": "bear", "summary": "获取插件配置"},
            {"path": "/config", "endpoint": self.api_save_config, "methods": ["POST"], "auth": "bear", "summary": "保存插件配置"},
            {"path": "/db/export", "endpoint": self.api_db_export, "methods": ["GET"], "auth": "bear", "summary": "导出数据库备份"},
            {"path": "/db/import", "endpoint": self.api_db_import, "methods": ["POST"], "auth": "bear", "summary": "导入数据库备份"},
            {"path": "/db/clear", "endpoint": self.api_db_clear, "methods": ["DELETE"], "auth": "bear", "summary": "清空数据库"},
            {"path": "/fonts", "endpoint": self.api_fonts, "methods": ["GET"], "auth": "bear", "summary": "字体库列表"},
            {"path": "/fonts/tree", "endpoint": self.api_font_tree, "methods": ["GET"], "auth": "bear", "summary": "字体目录数据（前端构建目录树）"},
            {"path": "/fonts/delete", "endpoint": self.api_font_delete, "methods": ["DELETE"], "auth": "bear", "summary": "删除字体（记录+文件）"},
            {"path": "/fonts/recalc_vendor", "endpoint": self.api_recalc_vendor, "methods": ["POST"], "auth": "bear", "summary": "重新识别厂商（可不传 id 全量重算）"},
            {"path": "/fonts/pending", "endpoint": self.api_pending_list, "methods": ["GET"], "auth": "bear", "summary": "待确认字体列表"},
            {"path": "/fonts/toggle_favorite", "endpoint": self.api_toggle_favorite, "methods": ["POST"], "auth": "bear", "summary": "切换字体收藏"},
            {"path": "/fonts/upload_preview", "endpoint": self.api_upload_preview, "methods": ["POST"], "auth": "bear", "summary": "上传字体预览"},
            {"path": "/fonts/confirm_upload", "endpoint": self.api_confirm_upload, "methods": ["POST"], "auth": "bear", "summary": "确认上传字体"},
            {"path": "/fonts/discard_upload", "endpoint": self.api_discard_upload, "methods": ["POST"], "auth": "bear", "summary": "放弃上传字体"},
            {"path": "/fonts/pending_delete/{id}", "endpoint": self.api_pending_delete, "methods": ["POST"], "auth": "bear", "summary": "删除待确认字体"},
            {"path": "/fonts/scan", "endpoint": self.api_scan_archive, "methods": ["POST"], "auth": "bear", "summary": "扫描并归档字体"},
            {"path": "/fonts/scan_all", "endpoint": self.api_scan_archive_all, "methods": ["POST"], "auth": "bear", "summary": "全量扫描输入目录字体并直接归档"},
            {"path": "/fonts/preview", "endpoint": self.api_font_preview, "methods": ["GET"], "auth": "bear", "summary": "字体预览"},
            {"path": "/ass/list", "endpoint": self.api_ass_list, "methods": ["GET"], "auth": "bear", "summary": "ASS 检查记录列表"},
            {"path": "/ass/detail", "endpoint": self.api_ass_detail, "methods": ["GET"], "auth": "bear", "summary": "ASS 检查详情"},
            {"path": "/ass/delete", "endpoint": self.api_ass_delete, "methods": ["DELETE"], "auth": "bear", "summary": "删除 ASS 检查记录"},
            {"path": "/ass/clear_all", "endpoint": self.api_ass_clear, "methods": ["DELETE"], "auth": "bear", "summary": "清空 ASS 检查记录"},
            {"path": "/ass/upload", "endpoint": self.api_ass_upload, "methods": ["POST"], "auth": "bear", "summary": "上传 ASS 字幕（仅登记，不检查）"},
            {"path": "/ass/check", "endpoint": self.api_ass_check, "methods": ["POST"], "auth": "bear", "summary": "手动检查 ASS 字幕字体"},
            {"path": "/ass/scan_all", "endpoint": self.api_ass_scan_all, "methods": ["POST"], "auth": "bear", "summary": "全量扫描字幕目录 ASS 并检查"},
            {"path": "/ass/missing/list", "endpoint": self.api_ass_missing_list, "methods": ["GET"], "auth": "bear", "summary": "聚合缺失字体列表"},
            {"path": "/ass/missing/upload", "endpoint": self.api_ass_missing_upload, "methods": ["POST"], "auth": "bear", "summary": "上传缺失字体（校验匹配）"},
            {"path": "/ass/missing/confirm", "endpoint": self.api_ass_missing_confirm, "methods": ["POST"], "auth": "bear", "summary": "缺失字体入库"},
            {"path": "/ass/missing/cancel", "endpoint": self.api_ass_missing_cancel, "methods": ["POST"], "auth": "bear", "summary": "取消缺失字体上传"},
            {"path": "/subset/index", "endpoint": self.api_subset_index, "methods": ["GET"], "auth": "bear", "summary": "assfonts 状态与字体索引"},
            {"path": "/subset/rebuild_index", "endpoint": self.api_subset_rebuild_index, "methods": ["POST"], "auth": "bear", "summary": "重建 assfonts 字体索引"},
            {"path": "/subset/all", "endpoint": self.api_subset_all, "methods": ["POST"], "auth": "bear", "summary": "全量子集化（递归扫字幕目录）"},
            {"path": "/subset/records", "endpoint": self.api_subset_records, "methods": ["GET"], "auth": "bear", "summary": "子集化记录列表"},
            {"path": "/subset/download", "endpoint": self.api_subset_download, "methods": ["GET"], "auth": "bear", "summary": "下载子集化结果文件"},
            {"path": "/subset/pending", "endpoint": self.api_subset_pending_list, "methods": ["GET"], "auth": "bear", "summary": "子集化待处理列表"},
            {"path": "/subset/pending/upload", "endpoint": self.api_subset_pending_upload, "methods": ["POST"], "auth": "bear", "summary": "上传字幕到子集化待处理"},
            {"path": "/subset/pending/remove/{id}", "endpoint": self.api_subset_pending_remove, "methods": ["POST"], "auth": "bear", "summary": "移除待处理字幕"},
            {"path": "/subset/pending/clear", "endpoint": self.api_subset_pending_clear, "methods": ["DELETE"], "auth": "bear", "summary": "清空待处理字幕"},
            {"path": "/subset/delete/{id}", "endpoint": self.api_subset_record_delete, "methods": ["POST"], "auth": "bear", "summary": "删除子集化记录"},
            {"path": "/subset/clear", "endpoint": self.api_subset_records_clear, "methods": ["DELETE"], "auth": "bear", "summary": "清空子集化记录"},
            {"path": "/subset/retry", "endpoint": self.api_subset_retry, "methods": ["POST"], "auth": "bear", "summary": "重试失败/缺字体的子集化"},
            {"path": "/missing/summary", "endpoint": self.api_missing_summary, "methods": ["GET"], "auth": "bear", "summary": "缺失字体汇总（检查+子集化）"},
            {"path": "/missing/uploads", "endpoint": self.api_missing_uploads, "methods": ["GET"], "auth": "bear", "summary": "已上传待归类字体列表"},
            {"path": "/missing/upload", "endpoint": self.api_missing_upload, "methods": ["POST"], "auth": "bear", "summary": "缺失字体上传"},
            {"path": "/missing/classify", "endpoint": self.api_missing_classify, "methods": ["POST"], "auth": "bear", "summary": "归类入库并重建索引"},
            {"path": "/missing/uploads/clear", "endpoint": self.api_missing_uploads_clear, "methods": ["DELETE"], "auth": "bear", "summary": "清除已上传字体"},
            {"path": "/missing/uploads/remove", "endpoint": self.api_missing_upload_remove, "methods": ["DELETE"], "auth": "bear", "summary": "删除单条已上传字体"},
        ] 