"""
MkvToolkit / MKV 工具箱：MoviePilot V3 插件入口。

本插件只做 MKV 容器层编辑：字幕内封、音轨管理、字体附件、章节与标题。
所有写操作都要先经过 ``/plan`` 预览确认，再由 ``/jobs`` 入队执行。
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # FastAPI 在宿主与本地测试环境都可能存在
    from fastapi import File, Request, UploadFile
except ImportError:  # 最小环境下的占位实现

    def File(*_args: Any, **_kwargs: Any) -> None:  # type: ignore[misc]
        """占位的 FastAPI File。"""
        return None

    class Request:  # type: ignore[no-redef]
        """占位的 FastAPI Request。"""

        async def json(self) -> dict[str, Any]:
            """读取 JSON 请求体。"""
            return {}

    class UploadFile:  # type: ignore[no-redef]
        """占位的 FastAPI UploadFile。"""

        filename: str = ""

        async def read(self, _size: int = -1) -> bytes:
            """读取上传内容。"""
            return b""

        async def close(self) -> None:
            """关闭上传文件。"""
            return None

try:  # MoviePilot 宿主环境
    from app.sdk.logging import logger
    from app.sdk.plugin import _PluginBase
except ImportError:  # 本地静态检查 / 单元测试环境
    import logging

    logger = logging.getLogger("mkvtoolkit")

    class _PluginBase:  # type: ignore[no-redef]
        """占位的插件基类，仅用于脱离宿主运行测试。"""

        def __init__(self) -> None:
            """占位初始化。"""

        def get_data_path(self, plugin_id: Optional[str] = None) -> Path:
            """返回临时数据目录。"""
            path = Path.cwd() / ".mkvtoolkit-data"
            path.mkdir(parents=True, exist_ok=True)
            return path

        def get_config(self, plugin_id: Optional[str] = None) -> Any:
            """占位配置读取。"""
            return {}

        def update_config(self, config: dict[str, Any], plugin_id: Optional[str] = None) -> bool:
            """占位配置保存。"""
            return True

from .archive import (
    available_tools,
    extract_fonts,
    is_archive,
    scan_archives,
    supported_extensions,
)
from .chapters import parse_chapter_file
from .engine import EngineManager
from .fssvc import KIND_EXT, FileSystemService, HistoryMatchError
from .offset import estimate_audio_offset, estimate_subtitle_offset
from .planner import build_plan
from .probe import ProbeError, probe_extra_file, probe_media
from .runner import JobRunner
from .store import DataStore, normalize_config

VERSION = "0.1.50"
_CHAPTER_EXT = {".xml", ".txt", ".chap", ".ffmeta"}

# 插件管理卡片图标：宿主只对 http(s) 地址走图片代理，需使用公网图片地址。
# 如需换成自己的图床/GitHub 仓库，改这里并把 package.v3.json 的 icon 同步即可。
PLUGIN_ICON = "https://raw.githubusercontent.com/LXT-A-X/MoviePilot-Plugins/main/icons/mkvtoolkit.png"


class MkvToolkit(_PluginBase):
    """MKV 工具箱插件主类。"""

    plugin_icon = PLUGIN_ICON

    plugin_name = "MKV 工具箱"
    plugin_desc = (
        "MKV 容器层编辑：字幕内封、音轨增删/排序/标签、字体附件、章节与标题，"
        "基于 mkvmerge + mkvpropedit，支持预览确认、队列执行、历史回滚与手机端操作。"
    )
    plugin_version = VERSION
    plugin_author = "LXT-A-X"
    author_url = "https://github.com/LXT-A-X"
    plugin_config_prefix = "mkvtoolkit_"
    plugin_order = 120
    auth_level = 2

    def __init__(self) -> None:
        """初始化插件状态与线程安全容器。"""
        super().__init__()
        self._enabled = False
        self._config: dict[str, Any] = {}
        self._data: Optional[DataStore] = None
        self._engine: Optional[EngineManager] = None
        self._fs: Optional[FileSystemService] = None
        self._jobs: Optional[JobRunner] = None
        self._lock = threading.RLock()
        self._logs: deque[str] = deque(maxlen=500)

    # ------------------------------------------------------------------ 生命周期
    def init_plugin(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        读取配置并建立运行期资源，可重复调用。

        :param config: 宿主传入的插件配置
        """
        self.stop_service()
        cfg = normalize_config(config)
        with self._lock:
            self._config = cfg
            self._enabled = bool(cfg.get("enabled", True))
        if not self._enabled:
            self._log("插件已停用")
            return
        self._build_runtime(cfg)
        roots = self._fs.root_texts() if self._fs else []
        self._log(f"MKV 工具箱 v{VERSION} 已启动，媒体根目录：{roots}")

    def _build_runtime(self, cfg: dict[str, Any]) -> None:
        """创建数据目录、引擎、文件服务与任务队列。"""
        data_dir = Path(self.get_data_path())
        log_dir = self._resolve_plugin_log_dir(data_dir)
        store = DataStore(data_dir, history_keep=int(cfg.get("history_keep") or 200))
        engine = EngineManager(data_dir, log=self._log)
        fs = FileSystemService(cfg.get("roots") or [], uploads_dir=store.uploads_dir)
        jobs = JobRunner(
            data_dir=data_dir,
            store=store,
            config_getter=self._effective_config,
            engine_getter=lambda: self._engine.detect(self._effective_config()) if self._engine else {},
            probe_getter=self._probe_for,
            log=self._log,
        )
        with self._lock:
            self._data = store
            self._engine = engine
            self._fs = fs
            self._jobs = jobs
            self._log_dir = log_dir
        engine.detect(cfg)
        jobs.start()

    @staticmethod
    def _resolve_plugin_log_dir(data_dir: Path) -> Path:
        """
        解析 MoviePilot 插件日志目录（``<LOG_PATH>/plugins``）。

        与其它插件一致：优先宿主运行配置里的 ``LOG_PATH``，容器默认 ``/config/logs/plugins``；
        都不可用时才回退到插件数据目录下的 ``logs``。
        """
        candidates: List[Path] = []
        try:
            from app.runtime.config import get_runtime_setting  # type: ignore

            value = get_runtime_setting("LOG_PATH")
            if value:
                candidates.append(Path(value) / "plugins")
        except Exception:  # noqa: BLE001 - 不同宿主版本接口位置不同
            pass
        try:
            from app.core.config import settings  # type: ignore

            value = getattr(settings, "LOG_PATH", None)
            if value:
                candidates.append(Path(value) / "plugins")
        except Exception:  # noqa: BLE001
            pass
        env_value = os.environ.get("LOG_PATH")
        if env_value:
            candidates.append(Path(env_value) / "plugins")
        # 容器默认路径：只在 /config 已挂载时使用，避免在开发机创建 C:\config
        if Path("/config").is_dir():
            candidates.append(Path("/config/logs/plugins"))

        for directory in candidates:
            try:
                if not directory.is_dir():
                    if not directory.parent.is_dir():
                        continue
                    directory.mkdir(parents=True, exist_ok=True)
                return directory
            except OSError:
                continue
        fallback = Path(data_dir) / "logs"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

    def _apply_config(self, cfg: dict[str, Any]) -> None:
        """保存并热应用配置：保留正在等待/运行的任务。"""
        if not cfg.get("enabled", True):
            self.update_config(cfg)
            self.stop_service()
            with self._lock:
                self._config = cfg
                self._enabled = False
            return
        self.update_config(cfg)
        with self._lock:
            old_jobs = self._jobs
        if old_jobs is None:
            with self._lock:
                self._config = cfg
                self._enabled = True
            self._build_runtime(cfg)
            return
        with self._lock:
            self._config = cfg
            self._enabled = True
            data_dir = Path(self.get_data_path())
            self._data = DataStore(data_dir, history_keep=int(cfg.get("history_keep") or 200))
            self._engine = EngineManager(data_dir, log=self._log)
            self._fs = FileSystemService(cfg.get("roots") or [], uploads_dir=self._data.uploads_dir)
        old_jobs.set_concurrency(int(cfg.get("concurrency") or 1))
        self._engine.detect(cfg)

    def get_state(self) -> bool:
        """返回插件是否启用。"""
        return self._enabled

    def stop_service(self) -> None:
        """停止任务队列并释放运行期资源。"""
        with self._lock:
            jobs = self._jobs
            self._jobs = None
            self._engine = None
            self._fs = None
            self._data = None
        if jobs is None:
            # 宿主可能重复调用 stop：没有运行期实例时不再重复写“已停止”
            return
        try:
            jobs.stop()
        except Exception as error:  # noqa: BLE001 - 停止失败不影响停用
            logger.warning(f"MkvToolkit 停止任务队列失败：{error}")
        self._log("MKV 工具箱已停止")

    # ------------------------------------------------------------------ 渲染与导航
    @staticmethod
    def get_render_mode() -> tuple[str, Optional[str]]:
        """声明 Vue 联邦渲染模式与构建产物目录。"""
        return "vue", "dist/assets"

    def get_form(self) -> tuple[Optional[List[dict]], Dict[str, Any]]:
        """Vue 模式下配置页由前端组件渲染。"""
        return [], self._public_config()

    def get_page(self) -> Optional[List[dict]]:
        """Vue 模式下详情页由前端组件渲染。"""
        return []

    @staticmethod
    def get_sidebar_nav() -> List[Dict[str, Any]]:
        """注册侧栏全页入口。"""
        return [
            {
                "nav_key": "main",
                "title": "MKV 工具箱",
                "icon": "mdi-video-box",
                "section": "system",
                "permission": "admin",
                "order": 120,
            }
        ]

    # ------------------------------------------------------------------ API 注册
    def get_api(self) -> List[Dict[str, Any]]:
        """注册插件后端接口。"""
        return [
            {"path": "/status", "endpoint": self.api_status, "methods": ["GET"], "auth": "bear", "summary": "运行状态"},
            {"path": "/config", "endpoint": self.api_get_config, "methods": ["GET"], "auth": "bear", "summary": "读取配置"},
            {"path": "/config", "endpoint": self.api_save_config, "methods": ["POST"], "auth": "bear", "summary": "保存配置"},
            {"path": "/engine/check", "endpoint": self.api_engine_check, "methods": ["POST"], "auth": "bear", "summary": "重新检测引擎"},
            {"path": "/engine/install", "endpoint": self.api_engine_install, "methods": ["POST"], "auth": "bear", "summary": "安装引擎"},
            {"path": "/diagnose", "endpoint": self.api_diagnose, "methods": ["POST"], "auth": "bear", "summary": "一键诊断"},
            {"path": "/fs/list", "endpoint": self.api_fs_list, "methods": ["POST"], "auth": "bear", "summary": "浏览目录"},
            {"path": "/probe", "endpoint": self.api_probe, "methods": ["POST"], "auth": "bear", "summary": "探测媒体信息"},
            {"path": "/plan", "endpoint": self.api_plan, "methods": ["POST"], "auth": "bear", "summary": "预览执行计划"},
            {"path": "/analyze/offset", "endpoint": self.api_analyze_offset, "methods": ["POST"], "auth": "bear", "summary": "估计音轨/字幕偏移"},
            {"path": "/jobs", "endpoint": self.api_job_create, "methods": ["POST"], "auth": "bear", "summary": "创建任务"},
            {"path": "/jobs", "endpoint": self.api_jobs, "methods": ["GET"], "auth": "bear", "summary": "任务列表"},
            {"path": "/jobs/start", "endpoint": self.api_jobs_start, "methods": ["POST"], "auth": "bear", "summary": "统一开始队列"},
            {"path": "/jobs/pause", "endpoint": self.api_job_pause, "methods": ["POST"], "auth": "bear", "summary": "暂停队列"},
            {"path": "/jobs/clear", "endpoint": self.api_job_clear, "methods": ["POST"], "auth": "bear", "summary": "清空等待"},
            {"path": "/jobs/{job_id}", "endpoint": self.api_job_detail, "methods": ["GET"], "auth": "bear", "summary": "任务详情"},
            {"path": "/jobs/{job_id}/cancel", "endpoint": self.api_job_cancel, "methods": ["POST"], "auth": "bear", "summary": "取消任务"},
            {"path": "/jobs/{job_id}/start", "endpoint": self.api_job_start, "methods": ["POST"], "auth": "bear", "summary": "启动单个任务"},
            {"path": "/jobs/{job_id}/update", "endpoint": self.api_job_update, "methods": ["POST"], "auth": "bear", "summary": "修改排队任务"},
            {"path": "/jobs/{job_id}/move", "endpoint": self.api_job_move, "methods": ["POST"], "auth": "bear", "summary": "调整队列顺序"},
            {"path": "/history", "endpoint": self.api_history, "methods": ["GET"], "auth": "bear", "summary": "历史记录"},
            {"path": "/history/clear", "endpoint": self.api_history_clear, "methods": ["POST"], "auth": "bear", "summary": "清空历史"},
            {"path": "/history/{history_id}/rollback", "endpoint": self.api_rollback, "methods": ["POST"], "auth": "bear", "summary": "回滚历史"},
            {"path": "/history/{history_id}/delete", "endpoint": self.api_history_delete, "methods": ["POST"], "auth": "bear", "summary": "删除历史"},
            {"path": "/file-statuses", "endpoint": self.api_file_statuses, "methods": ["GET"], "auth": "bear", "summary": "文件任务状态"},
            {"path": "/upload", "endpoint": self.api_upload, "methods": ["POST"], "auth": "bear", "summary": "上传素材"},
            {"path": "/archive/tools", "endpoint": self.api_archive_tools, "methods": ["GET"], "auth": "bear", "summary": "压缩包解压能力"},
            {"path": "/archive/extract", "endpoint": self.api_archive_extract, "methods": ["POST"], "auth": "bear", "summary": "从目录/压缩包提取字体"},
            {"path": "/archive/upload", "endpoint": self.api_archive_upload, "methods": ["POST"], "auth": "bear", "summary": "上传压缩包并提取字体"},
            {"path": "/logs", "endpoint": self.api_logs, "methods": ["GET"], "auth": "bear", "summary": "插件日志"},
        ]

    # ------------------------------------------------------------------ 状态/配置
    def api_status(self) -> Dict[str, Any]:
        """运行状态总览。"""
        engine = self._engine.detect(self._effective_config()) if self._engine else {"mode": "none"}
        return self._ok({
            "enabled": self._enabled,
            "version": VERSION,
            "engine": engine,
            "engine_install": self._engine.install_state if self._engine else {"running": False, "ok": False},
            "archive": {"tools": available_tools(), "extensions": supported_extensions()},
            "queue": self._jobs.counts() if self._jobs else {"running": 0, "pending": 0, "paused": False},
            "config": self._public_config(),
            "roots": self._fs.root_texts() if self._fs else [],
        })

    def api_get_config(self) -> Dict[str, Any]:
        """读取当前配置。"""
        return self._ok(self._public_config())

    async def api_save_config(self, request: Request) -> Dict[str, Any]:
        """保存配置并热应用。"""
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 - 非法 JSON 按空对象处理
            body = {}
        if not isinstance(body, dict):
            return self._err("配置格式不正确")
        cfg = normalize_config(body)
        try:
            self._apply_config(cfg)
        except Exception as error:  # noqa: BLE001 - 配置错误要回传前端
            return self._err(f"保存配置失败：{error}")
        return self._ok(self._public_config())

    # ------------------------------------------------------------------ 引擎
    def api_engine_check(self) -> Dict[str, Any]:
        """重新检测引擎。"""
        if not self._engine:
            return self._err("插件未启用")
        return self._ok(self._engine.refresh(self._effective_config()))

    async def api_engine_install(self, request: Request) -> Dict[str, Any]:
        """触发后台安装。"""
        if not self._engine:
            return self._err("插件未启用")
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        method = str((body or {}).get("method") or "apt")
        path = str((body or {}).get("path") or "")
        target = str((body or {}).get("target") or "all")
        try:
            result = self._engine.start_install(method, path, target)
        except RuntimeError as error:
            return self._err(str(error))
        return self._ok(result)

    # ------------------------------------------------------------------ 目录/探测
    def api_diagnose(self) -> Dict[str, Any]:
        """一键诊断：引擎、权限、根目录与磁盘空间。"""
        if not self._engine:
            return self._err("插件未启用")
        cfg = self._effective_config()
        engine = self._engine.detect(cfg)
        roots: list[dict[str, Any]] = []
        for root in (self._fs.root_texts() if self._fs else []):
            path = Path(root)
            try:
                free = int(shutil.disk_usage(path).free)
            except OSError:
                free = 0
            roots.append({
                "path": root,
                "exists": path.is_dir(),
                "writable": os.access(path, os.W_OK),
                "free": free,
            })
        data_dir = Path(self.get_data_path())
        geteuid = getattr(os, "geteuid", None)
        return self._ok({
            "engine": engine,
            "mode": engine.get("mode"),
            "is_root": bool(geteuid and geteuid() == 0),
            "data_dir": str(data_dir),
            "data_writable": os.access(data_dir, os.W_OK),
            "roots": roots,
            "upload_max_mb": cfg.get("upload_max_mb"),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        })

    async def api_fs_list(self, request: Request) -> Dict[str, Any]:
        """浏览目录。"""
        if not self._fs:
            return self._err("插件未启用")
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        body = body or {}
        try:
            result = self._fs.list_dir(
                root=str(body.get("root") or "") or None,
                path=str(body.get("path") or "") or None,
                kind=str(body.get("kind") or "video"),
            )
        except HistoryMatchError as error:
            return self._err(str(error))
        return self._ok(result)

    async def api_probe(self, request: Request) -> Dict[str, Any]:
        """探测单个 MKV 的轨道、章节、附件与同级素材。"""
        if not self._fs:
            return self._err("插件未启用")
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        path = str((body or {}).get("path") or "")
        try:
            resolved = self._fs.resolve_video(path)
            info = self._probe_for(resolved)
        except (HistoryMatchError, ProbeError) as error:
            return self._err(str(error))
        return self._ok(info)

    # ------------------------------------------------------------------ 计划/任务
    async def api_plan(self, request: Request) -> Dict[str, Any]:
        """生成执行计划（dry-run）。"""
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        if not isinstance(body, dict):
            return self._err("请求格式不正确")
        try:
            preview = self._build_plan(body)
        except (HistoryMatchError, ProbeError, ValueError) as error:
            return self._err(str(error))
        return self._ok(preview)

    async def api_analyze_offset(self, request: Request) -> Dict[str, Any]:
        """实验能力：估计新增音轨/字幕相对视频的延迟（结果需用户确认后使用）。"""
        if not self._fs or not self._engine:
            return self._err("插件未启用")
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        body = body or {}
        kind = str(body.get("kind") or "audio")
        if kind not in {"audio", "subtitle"}:
            return self._err("kind 只支持 audio / subtitle")
        try:
            video = self._fs.resolve_video(str(body.get("path") or ""))
            source = self._fs.resolve_source(str(body.get("file") or ""), kind)
        except HistoryMatchError as error:
            return self._err(str(error))
        engine = self._engine.detect(self._effective_config())
        ffmpeg = str((engine.get("ffmpeg") or {}).get("path") or "")
        if not ffmpeg:
            return self._err("偏移估计需要 ffmpeg，但当前未检测到 ffmpeg")
        try:
            max_seconds = int(body.get("max_seconds") or 900)
        except (TypeError, ValueError):
            max_seconds = 900
        try:
            range_ms = int(body.get("range_ms") or (8000 if kind == "audio" else 15000))
        except (TypeError, ValueError):
            range_ms = 8000 if kind == "audio" else 15000
        max_seconds = max(60, min(3600, max_seconds))
        range_ms = max(500, min(30000, range_ms))
        try:
            if kind == "audio":
                result = estimate_audio_offset(video, source, ffmpeg, max_seconds, range_ms)
            else:
                result = estimate_subtitle_offset(video, source, ffmpeg, max_seconds, range_ms)
        except Exception as error:  # noqa: BLE001 - ffmpeg 异常要回传前端
            return self._err(f"偏移估计失败：{error}")
        result["path"] = str(video)
        result["file"] = str(source)
        return self._ok(result)

    async def api_job_create(self, request: Request) -> Dict[str, Any]:
        """校验计划并入队。"""
        if not self._jobs:
            return self._err("插件未启用")
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        plan_payload = (body or {}).get("plan") if isinstance(body, dict) else None
        hold = bool((body or {}).get("hold")) if isinstance(body, dict) else False
        if not isinstance(plan_payload, dict):
            return self._err("缺少执行计划")
        try:
            preview = self._build_plan(plan_payload)
        except (HistoryMatchError, ProbeError, ValueError) as error:
            return self._err(str(error))
        if preview.get("blockers"):
            return self._err(
                str(preview["blockers"][0].get("message") or "计划存在阻塞项"),
                data={"blockers": preview.get("blockers")},
            )
        job = self._jobs.submit(plan_payload, preview, hold=hold)
        return self._ok(job)

    def api_jobs_start(self) -> Dict[str, Any]:
        """统一开始队列：解除所有待启动任务并恢复执行。"""
        if not self._jobs:
            return self._err("插件未启用")
        return self._ok(self._jobs.start_all())

    def api_job_start(self, job_id: str) -> Dict[str, Any]:
        """启动单个待启动任务。"""
        if not self._jobs:
            return self._err("插件未启用")
        try:
            return self._ok(self._jobs.start_job(job_id))
        except KeyError as error:
            return self._err(str(error))

    async def api_job_update(self, job_id: str, request: Request) -> Dict[str, Any]:
        """修改排队中的任务配置（重新生成计划后覆盖）。"""
        if not self._jobs:
            return self._err("插件未启用")
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        plan_payload = (body or {}).get("plan") if isinstance(body, dict) else None
        if not isinstance(plan_payload, dict):
            return self._err("缺少执行计划")
        try:
            preview = self._build_plan(plan_payload)
        except (HistoryMatchError, ProbeError, ValueError) as error:
            return self._err(str(error))
        if preview.get("blockers"):
            return self._err(
                str(preview["blockers"][0].get("message") or "计划存在阻塞项"),
                data={"blockers": preview.get("blockers")},
            )
        try:
            return self._ok(self._jobs.update(job_id, plan_payload, preview))
        except KeyError as error:
            return self._err(str(error))

    def api_jobs(self, status: str = "all") -> Dict[str, Any]:
        """任务列表。"""
        if not self._jobs:
            return self._ok({"jobs": [], "paused": False})
        return self._ok({
            "jobs": self._jobs.list_jobs(status),
            "paused": self._jobs.counts().get("paused", False),
        })

    def api_job_detail(self, job_id: str) -> Dict[str, Any]:
        """任务详情（含日志尾部）；已结束的任务回退到历史查询。"""
        if not self._jobs:
            return self._err("插件未启用")
        job = self._jobs.get(job_id)
        if job:
            job["log_tail"] = self._jobs.log_tail(job_id)
            return self._ok(job)
        for item in self._jobs.history():
            if item.get("id") == job_id:
                return self._ok(item)
        return self._err("任务不存在或已结束，请到历史中查看")

    def api_job_cancel(self, job_id: str) -> Dict[str, Any]:
        """取消任务。"""
        if not self._jobs:
            return self._err("插件未启用")
        try:
            return self._ok(self._jobs.cancel(job_id))
        except KeyError as error:
            return self._err(str(error))

    async def api_job_pause(self, request: Request) -> Dict[str, Any]:
        """暂停/继续队列。"""
        if not self._jobs:
            return self._err("插件未启用")
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        return self._ok(self._jobs.set_paused(bool((body or {}).get("paused", True))))

    def api_job_clear(self) -> Dict[str, Any]:
        """清空等待队列。"""
        if not self._jobs:
            return self._err("插件未启用")
        return self._ok({"cancelled": self._jobs.clear_pending()})

    async def api_job_move(self, job_id: str, request: Request) -> Dict[str, Any]:
        """调整等待任务顺序。"""
        if not self._jobs:
            return self._err("插件未启用")
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        try:
            return self._ok(self._jobs.move(job_id, str((body or {}).get("to") or "top")))
        except KeyError as error:
            return self._err(str(error))

    # ------------------------------------------------------------------ 历史/回滚
    def api_history(self, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """历史记录（新的在前）。"""
        if not self._jobs:
            return self._ok({"items": [], "total": 0})
        items = self._jobs.history()
        try:
            start = max(0, int(offset))
            size = max(1, min(500, int(limit)))
        except (TypeError, ValueError):
            start, size = 0, 50
        return self._ok({"items": items[start:start + size], "total": len(items)})

    def api_file_statuses(self) -> Dict[str, Any]:
        """文件树状态：队列待开始/运行中 + 历史已完成/失败/已取消（按源文件路径去重）。"""
        if not self._jobs:
            return self._ok({"items": []})
        states: Dict[str, Dict[str, Any]] = {}
        for item in self._jobs.history():
            path = str(item.get("path") or "")
            status = str(item.get("status") or "")
            if not path or path in states or status not in {"success", "failed", "cancelled"}:
                continue
            states[path] = {
                "path": path,
                "name": item.get("name") or Path(path).name,
                "state": status,
                "job_id": item.get("id"),
                "updated_at": item.get("finished_at") or item.get("created_at"),
            }
        for job in self._jobs.list_jobs("all"):
            path = str(job.get("path") or "")
            status = str(job.get("status") or "")
            if not path or status not in {"pending", "running"}:
                continue
            states[path] = {
                "path": path,
                "name": job.get("name") or Path(path).name,
                "state": status,
                "stage": job.get("stage"),
                "job_id": job.get("id"),
                "updated_at": job.get("updated_at") or job.get("created_at"),
            }
        return self._ok({"items": list(states.values())})

    def api_rollback(self, history_id: str) -> Dict[str, Any]:
        """从备份回滚一次替换操作。"""
        if not self._jobs:
            return self._err("插件未启用")
        try:
            return self._ok(self._jobs.rollback(history_id))
        except KeyError as error:
            return self._err(str(error))
        except OSError as error:
            return self._err(f"回滚失败：{error}")

    def api_history_delete(self, history_id: str) -> Dict[str, Any]:
        """删除一条历史记录。"""
        if not self._jobs:
            return self._err("插件未启用")
        return self._ok({"deleted": self._jobs.delete_history(history_id)})

    def api_history_clear(self) -> Dict[str, Any]:
        """清空历史记录。"""
        if not self._jobs:
            return self._err("插件未启用")
        return self._ok({"deleted": self._jobs.clear_history()})

    # ------------------------------------------------------------------ 上传
    async def api_upload(
        self,
        file: UploadFile = File(...),
        kind: str = "subtitle",
    ) -> Dict[str, Any]:
        """上传字幕/音频/字体文件（超过上限直接拒绝）。"""
        if not self._data:
            return self._err("插件未启用")
        if file is None:
            return self._err("缺少上传文件")
        allowed = KIND_EXT.get(kind)
        if not allowed:
            return self._err(f"未知上传类型：{kind}")
        limit_mb = int(self._effective_config().get("upload_max_mb") or 50)
        limit_bytes = limit_mb * 1024 * 1024
        filename = str(getattr(file, "filename", "") or "upload.bin")
        suffix = Path(filename).suffix.lower()
        if suffix not in allowed:
            return self._err(f"不支持的文件类型：{suffix}")
        chunks: list[bytes] = []
        total = 0
        try:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit_bytes:
                    return self._err(
                        f"文件超过 {limit_mb}MB 上传上限，请改用「从目录选择」",
                        data={"size": total, "limit": limit_bytes},
                    )
                chunks.append(chunk)
        finally:
            try:
                await file.close()
            except Exception:  # noqa: BLE001
                pass
        if not total:
            return self._err("上传文件为空")
        target = self._data.save_upload(filename, b"".join(chunks))
        self._log(f"已上传素材：{target.name}（{total} 字节）")
        return self._ok({
            "path": str(target),
            "name": target.name,
            "size": total,
            "kind": kind,
        })

    # ------------------------------------------------------------------ 压缩包字体
    def api_archive_tools(self) -> Dict[str, Any]:
        """返回压缩包解压能力（7z/unrar 是否可用）与支持的扩展名。"""
        return self._ok({
            "tools": available_tools(),
            "extensions": supported_extensions(),
        })

    def _resolve_archive_path(self, path_text: str) -> Path:
        """校验路径在媒体根目录或上传目录内。"""
        if not self._fs:
            raise HistoryMatchError("插件未启用")
        candidate = Path(str(path_text or "")).expanduser()
        if not candidate.is_absolute():
            candidate = Path("/") / candidate
        try:
            resolved = candidate.resolve(strict=False)
        except OSError as error:
            raise HistoryMatchError(f"路径不可用：{error}") from error
        if not (self._fs.is_within_roots(resolved) or self._fs.is_upload(resolved)):
            raise HistoryMatchError("路径不在已配置的媒体根目录或上传目录内")
        if not resolved.exists():
            raise HistoryMatchError(f"路径不存在：{resolved}")
        return resolved

    def _extract_archives(self, archives: List[Path]) -> Dict[str, Any]:
        """把压缩包里的字体提取到上传目录，返回可加入附件的字体列表。"""
        if not self._data:
            raise HistoryMatchError("插件未启用")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest_root = self._data.uploads_dir / "fonts"
        items: List[Dict[str, Any]] = []
        results: List[Dict[str, Any]] = []
        for archive in archives[:50]:
            sub = dest_root / f"{archive.stem}-{stamp}"
            if sub.exists():
                sub = dest_root / f"{archive.stem}-{stamp}-{len(results) + 1}"
            try:
                fonts = extract_fonts(archive, sub)
            except Exception as error:  # noqa: BLE001 - 单个压缩包失败不影响其它
                results.append({"path": str(archive), "fonts": 0, "error": str(error)})
                continue
            results.append({"path": str(archive), "fonts": len(fonts), "target": str(sub)})
            self._log(f"已从压缩包提取字体：{archive.name} → {len(fonts)} 个")
            for font in fonts:
                try:
                    size = font.stat().st_size
                except OSError:
                    size = 0
                items.append({
                    "path": str(font),
                    "name": font.name,
                    "size": size,
                    "ext": font.suffix.lower(),
                    "archive": str(archive),
                })
        return {
            "items": items,
            "archives": results,
            "tools": available_tools(),
            "extensions": supported_extensions(),
        }

    async def api_archive_extract(self, request: Request) -> Dict[str, Any]:
        """从指定目录（可递归）或单个压缩包中提取字体。"""
        if not self._fs or not self._data:
            return self._err("插件未启用")
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        body = body or {}
        try:
            target = self._resolve_archive_path(str(body.get("path") or ""))
        except HistoryMatchError as error:
            return self._err(str(error))
        recursive = bool(body.get("recursive"))
        if target.is_file():
            if not is_archive(target):
                return self._err("不是支持的压缩包（zip / 7z / rar / tar）")
            archives = [target]
        elif target.is_dir():
            archives = scan_archives(target, recursive=recursive)
            if not archives:
                return self._err("目录下没有找到 zip / 7z / rar / tar 压缩包")
        else:
            return self._err("目标既不是压缩包也不是目录")
        try:
            return self._ok(self._extract_archives(archives))
        except HistoryMatchError as error:
            return self._err(str(error))

    async def api_archive_upload(self, file: UploadFile = File(...)) -> Dict[str, Any]:
        """上传压缩包并直接提取其中的字体。"""
        if not self._data:
            return self._err("插件未启用")
        if file is None:
            return self._err("缺少上传文件")
        filename = str(getattr(file, "filename", "") or "upload.zip")
        if not is_archive(filename):
            return self._err("只支持 zip / 7z / rar / tar 压缩包")
        limit_bytes = 512 * 1024 * 1024
        chunks: List[bytes] = []
        total = 0
        try:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit_bytes:
                    return self._err("压缩包超过 512MB 上限", data={"size": total, "limit": limit_bytes})
                chunks.append(chunk)
        finally:
            try:
                await file.close()
            except Exception:  # noqa: BLE001
                pass
        if not total:
            return self._err("上传文件为空")
        archive = self._data.save_upload(filename, b"".join(chunks))
        self._log(f"已上传压缩包：{archive.name}（{total} 字节）")
        try:
            data = self._extract_archives([archive])
        except HistoryMatchError as error:
            return self._err(str(error))
        data["uploaded"] = str(archive)
        return self._ok(data)

    # ------------------------------------------------------------------ 日志
    def api_logs(self, lines: int = 200) -> Dict[str, Any]:
        """返回插件最近日志（优先读 MoviePilot 的 <LOG_PATH>/plugins 日志文件）。"""
        try:
            count = max(1, min(500, int(lines)))
        except (TypeError, ValueError):
            count = 200
        log_dir = getattr(self, "_log_dir", None)
        if log_dir:
            log_name = Path(__file__).parent.name or "mkvtoolkit"
            log_path = Path(log_dir) / f"{log_name}.log"
            if log_path.is_file():
                try:
                    content = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                    return self._ok({"lines": content[-count:], "path": str(log_path)})
                except OSError:
                    pass
        with self._lock:
            return self._ok({"lines": list(self._logs)[-count:]})

    # ------------------------------------------------------------------ 内部
    def _build_plan(self, plan_payload: dict[str, Any]) -> dict[str, Any]:
        """
        校验输入并生成执行计划。

        :param plan_payload: 前端 plan
        :return: ``build_plan()`` 结果
        """
        if not self._fs or not self._engine:
            raise HistoryMatchError("插件未启用")
        cfg = self._effective_config()
        source = self._fs.resolve_video(str(plan_payload.get("path") or ""))
        info = self._probe_for(source)
        payload = dict(plan_payload)
        payload["path"] = str(source)
        tracks = dict(payload.get("tracks") or {})
        additions_raw = tracks.get("add") or []
        additions: list[dict[str, Any]] = []
        for item in additions_raw:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "")
            try:
                media = self._fs.resolve_source(str(item.get("file") or ""), kind)
            except HistoryMatchError as error:
                raise HistoryMatchError(f"{item.get('file')}: {error}") from error
            enriched = dict(item)
            enriched["file"] = str(media)
            enriched["size"] = media.stat().st_size
            extra = probe_extra_file(media, self._engine.detect(cfg))
            enriched["duration"] = extra.get("duration")
            enriched["track_count"] = extra.get("track_count") or 1
            if kind != "audio":
                enriched.setdefault("encoding", "auto")
            additions.append(enriched)
        tracks["add"] = additions
        payload["tracks"] = tracks

        chapters_data: Optional[list[dict[str, Any]]] = None
        chapter_cfg = dict(payload.get("chapters") or {})
        if str(chapter_cfg.get("mode")) == "import":
            chapter_path = str(chapter_cfg.get("file") or "")
            resolved_chapter = self._resolve_chapter_file(chapter_path)
            try:
                chapters_data = parse_chapter_file(resolved_chapter)
            except ValueError as error:
                raise ValueError(f"章节解析失败：{error}") from error
            chapter_cfg["file"] = str(resolved_chapter)
            payload["chapters"] = chapter_cfg
        output_cfg = dict(payload.get("output") or {})
        if str(output_cfg.get("mode") or cfg.get("output_mode")) == "dir":
            output_dir = Path(str(cfg.get("output_dir") or ""))
            if output_dir:
                self._fs.ensure_dir(output_dir)
        return build_plan(
            plan=payload,
            info=info,
            engine=self._engine.detect(cfg),
            config=cfg,
            data_dir=Path(self.get_data_path()),
            chapters=chapters_data,
        )

    def _resolve_chapter_file(self, path_text: str) -> Path:
        """章节文件允许位于媒体根目录或上传目录。"""
        if not self._fs:
            raise HistoryMatchError("插件未启用")
        candidate = Path(path_text).expanduser()
        if not candidate.is_absolute():
            candidate = Path("/") / candidate
        resolved = candidate.resolve(strict=False)
        if not (self._fs.is_within_roots(resolved) or self._fs.is_upload(resolved)):
            raise HistoryMatchError("章节文件必须位于媒体根目录或插件上传目录内")
        if not resolved.is_file():
            raise HistoryMatchError(f"章节文件不存在：{resolved}")
        if resolved.suffix.lower() not in _CHAPTER_EXT:
            raise HistoryMatchError("章节文件只支持 .xml / .txt（OGM 或 ffmetadata）")
        return resolved

    def _probe_for(self, path: Path) -> dict[str, Any]:
        """用当前引擎探测文件。"""
        if not self._engine:
            raise ProbeError("插件未启用")
        cfg = self._effective_config()
        return probe_media(
            path,
            engine=self._engine.detect(cfg),
            language_map=dict(cfg.get("language_map") or {}),
        )

    def _effective_config(self) -> dict[str, Any]:
        """补齐输出/备份默认目录后的配置。"""
        cfg = dict(self._config)
        if self._data:
            if not cfg.get("output_dir"):
                cfg["output_dir"] = str(self._data.output_dir)
            if not cfg.get("backup_dir"):
                cfg["backup_dir"] = str(self._data.backup_dir)
        return cfg

    def _public_config(self) -> dict[str, Any]:
        """返回给前端的配置（补默认目录）。"""
        return self._effective_config()

    def _log(self, message: str) -> None:
        """写插件日志：自己直接追加到 <LOG_PATH>/plugins/mkvtoolkit.log，并缓存到内存。"""
        text = str(message)
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} [MkvToolkit] {text}"
        with self._lock:
            self._logs.append(line)
        path = self._plugin_log_path()
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", errors="replace") as handle:
                handle.write(line + "\n")
        except OSError:
            pass

    def _plugin_log_path(self) -> Optional[Path]:
        """返回插件日志文件路径（懒解析日志目录，确保文件一定生成）。"""
        log_dir = getattr(self, "_log_dir", None)
        if not log_dir:
            try:
                log_dir = self._resolve_plugin_log_dir(Path(self.get_data_path()))
            except Exception:  # noqa: BLE001 - 日志失败不影响插件
                return None
            self._log_dir = log_dir
        name = Path(__file__).parent.name or "mkvtoolkit"
        return Path(log_dir) / f"{name}.log"

    # ------------------------------------------------------------------ 响应封装
    @staticmethod
    def _ok(data: Any = None, message: str = "success") -> Dict[str, Any]:
        """成功响应。"""
        return {"success": True, "message": message, "data": data}

    @staticmethod
    def _err(message: str = "error", data: Any = None) -> Dict[str, Any]:
        """失败响应。"""
        return {"success": False, "message": message, "data": data}
