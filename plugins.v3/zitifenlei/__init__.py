"""
字体分类管家 (Font Manager)
MoviePilot V2 插件 - 字体归档整理 + ASS 字幕字体检查
"""

from __future__ import annotations

import base64
import asyncio
import hashlib
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
from typing import Any, Dict, Iterable, List, Optional, Tuple

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
    from app.sdk.config import settings as _settings
except Exception:
    _settings = None

try:
    from app.sdk.logging import logger as _logger
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
    from app.sdk.events import eventmanager
    from app.schemas.types import EventType
except Exception:
    class _DummyEventManager:
        """本地/测试环境桩：无宿主 SDK 时让事件装饰器原样返回函数。"""

        def register(self, _event: Any):
            def _decorator(func: Any) -> Any:
                return func

            return _decorator

    eventmanager = _DummyEventManager()

    class EventType:  # 兜底：仅避免在无宿主环境导入时崩溃
        TransferComplete = "transfer.complete"
        SubtitleTransferComplete = "transfer.subtitle.complete"
        WebhookMessage = "webhook.message"

from .db import FontDB
from .font_utils import (
    ASS_EXTENSIONS,
    FONT_EXTENSIONS,
    MAX_ASS_FILE_BYTES,
    MAX_UPLOAD_FILES,
    MAX_UPLOAD_TOTAL_BYTES,
    TTFont,
    is_font_file,
    is_ass_file,
    max_font_file_bytes,
    parse_font_metadata,
    get_font_psname,
    parse_ass_fonts,
    normalize_font_key,
    safe_filename_component,
    has_embedded_fonts,
    set_max_font_mb,
)
from . import archive_utils as arch
from . import torrent_utils as tq
from .hdr_utils import apply_hdr_brightness
from .font_metadata import FontInspection, inspect_font
from .glyph_checker import FaceCoverage, evaluate_usage, parse_ass_usage
from .harfbuzz_engine import (
    FaceRef,
    SubsetEmbed,
    SubsetResult,
    _choose_face as hb_choose_face,
    default_output_path as hb_output_path,
    hb_available,
    refresh_backend as hb_refresh_backend,
    subset_ass_file as hb_subset_ass_file,
)
from .subset_worker_client import (
    SubsetWorkerClient,
    SubsetWorkerCrashed,
    SubsetWorkerStartError,
    SubsetWorkerTimeout,
)

_DEFAULT_CONFIG = {
    "enabled": True,
    "input_dir": "",
    "lib_dir": "",
    "ass_dir": "",
    "subset_dir": "",
    # 缺失字体专用接收目录（独立于字体库/监控目录）：放入的字体先等写入稳定，
    # 再逐 face 严格校验是否命中当前缺失目标并真实覆盖至少一个缺失字符；
    # 通过 → 直接归档入字体库；未通过 → 移入该目录下 rejected/ 留档，不入库不索引
    "missing_font_dir": "",
    # 字体元数据统一由 fontTools 解析（font_metadata.inspect_font），不再提供「文件名解析」模式，
    # 老配置里的 scan_mode 键不再读取
    "archive_mode": "copy",
    "font_name_internal": False,  # 利用字体内部名称（PostScript 名 nameID 6）命名归档：开用内部名，关保持原名
    # 单字体文件大小上限（MB）：超过该值的字体不做哈希/解析、不接受上传、不能预览。
    # 默认 128；超大 TTC（如 785MB 的 Sarasa-SuperTTC 含 480 个 face）逐 face 读 cmap
    # 会长时间占内存，确有需要可调大后重建索引
    "max_font_mb": 128,
    # 移动归档时删除判重跳过的残留源文件：只作用于「移动原文件」模式——
    # move 归档判重跳过（字体库已存在同名同后缀）时，监控目录的源文件会残留，
    # 开关开=删除残留；关=保留（复制模式不受影响，源文件本就保留）
    "move_delete_duplicate": True,
    "monitor_enabled": False,  # 是否启用监控（总开关）：统一控制字体监控目录 / ASS字幕目录监控 / ASS目录监控子集的启停
    # 老版本监控开关（auto_monitor/auto_check）已合并进 monitor_enabled，不再作为配置项暴露；
    # init_plugin 迁移时仍从宿主旧配置读取一次
    "auto_inbound": True,
    "auto_collect": True,
    "notify_enabled": False,
    # 索引维护：启动轻检（stat 级校验 + 磁盘清单对比补发现新字体）+ 每周差异核对
    # （cron 定时增量比对 + 哈希抽检）。按既定策略默认开启，可在设置中关闭
    "startup_light_check": True,
    "weekly_reconcile": True,
    # 子集化设置
    "auto_subset": False,
    # 子集化在独立工作进程中执行（uharfbuzz 段错误/病态字体只影响当前字幕，
    # 不拖垮 MoviePilot 主进程）；工作进程无法启动时自动回退进程内执行
    "subset_process_isolation": True,
    # MP 入库成品是否直接替换媒体库原字幕（独立开关：不影响目录监控与手动上传）
    "inbound_subset_overwrite": False,
    "subset_out_dir": "",
    # 监控目录输出方式：目录监控唯一的成品/源字幕去向开关
    #   copy = 成品进输出目录、源字幕保留；未配输出目录时另生成 xx.ziti.ass 并保留源字幕
    #   move = 成品进输出目录、成功后删除源字幕；未配输出目录时成品就地替换源字幕
    "subset_out_mode": "copy",
    # HDR 字幕亮度（子集化/上传字幕处理后按档位压暗主色/描边/阴影，避免 HDR 下刺眼）
    "hdr_brightness": False,
    "hdr_brightness_level": "",
    # ── 种子字体收集（只读下载器，按种子文件清单截取，不扫目录）──
    # 总开关：开启后自动包含「字幕入库前收集闸门 + 整理完成兜底 + 定时兜底」
    "torrent_enabled": False,
    # 整理完成兜底入口的启动延迟（秒）：等 MP 搬完文件；字幕事件触发的收集不吃这个延迟
    "torrent_delay_sec": 60,
    # 字幕入库子集化前的最长等待（秒）：超时照常子集，缺字记入结果可重试
    "torrent_wait_sec": 300,
    # 压缩包/路径关键词（逗号分隔）：只对压缩包生效，裸字体文件不看关键词
    "torrent_keywords": "font,fonts,字体",
    # 单文件上限（MB）与单种子最多截取文件数
    "torrent_max_file_mb": 2048,
    "torrent_max_files": 500,
    # 收集去向：False=直接入库；True=进「待整理」等确认
    "torrent_to_pending": False,
    # 基线时间戳（Unix 秒）：只处理基线之后完成的种子，历史不碰；由后端维护，前端可重置
    "torrent_baseline_ts": 0,
}

# _archive_font_file 返回码：>0=归档成功（返回字体 ID），None=处理失败。
# 负数区分「跳过」的各种原因，供通知统计「库中已存在跳过 / 删除重复源文件」等分项。
_ARCH_PENDING = -1        # 目录自动收集关闭：已进「待确认」，未归档
_ARCH_DUP = -2            # 字体库已存在（或源文件已收录）：跳过
_ARCH_DUP_DELETED = -3    # 同上跳过，且已删除监控目录残留的重复源文件
_ARCH_DUP_DEL_FAILED = -4  # 同上跳过，但删除重复源文件失败


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


_ADMIN_WRITE_DEPENDENCIES: Optional[List[Any]] = None


def _admin_write_dependencies() -> List[Any]:
    """高危写接口的管理员依赖。

    宿主插件路由只按声明里的 auth 做「是否已登录」校验，不会自动加管理员校验；
    清库/删文件/装依赖/改配置等写接口必须显式挂 get_current_active_superuser。
    宿主不提供该依赖时返回空列表（退回原行为，不影响插件加载）。
    """
    global _ADMIN_WRITE_DEPENDENCIES
    if _ADMIN_WRITE_DEPENDENCIES is None:
        try:
            from fastapi import Depends
            from app.api.dependencies.auth import get_current_active_superuser

            _ADMIN_WRITE_DEPENDENCIES = [Depends(get_current_active_superuser)]
        except Exception:
            _ADMIN_WRITE_DEPENDENCIES = []
    return list(_ADMIN_WRITE_DEPENDENCIES)



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


def _wait_file_stable(
    path: Path, timeout: float = 10.0, interval: float = 0.25, settle: float = 0.5
) -> bool:
    """等待文件写入完成：连续两次 stat 的 size 与 mtime_ns 一致才视为稳定。

    网络盘（PollingObserver 轮询/大字体跨盘复制）下 2 秒防抖不足以保证写完，
    半截文件入库后会被名称判重永久跳过，因此归档前必须显式探测。
    已静置超过 settle 秒的文件直接判定稳定，批量扫描存量字体不额外等待。
    """
    try:
        prev = Path(path).stat()
    except OSError:
        return False
    if time.time() - prev.st_mtime >= max(0.0, float(settle)):
        return True
    deadline = time.time() + max(0.0, float(timeout))
    while time.time() < deadline:
        time.sleep(max(0.05, float(interval)))
        try:
            cur = Path(path).stat()
        except OSError:
            return False
        if cur.st_size == prev.st_size and cur.st_mtime_ns == prev.st_mtime_ns:
            return True
        prev = cur
    return False


def _files_identical(a: Path, b: Path) -> bool:
    """两份字体是否完全相同：先比 size，再比 SHA-256（分块读取，避免大文件占内存）。

    任何读取/校验异常一律返回 False（宁可多存一份，也不误删用户源文件）。
    """
    try:
        sa = Path(a).stat()
        sb = Path(b).stat()
        if sa.st_size != sb.st_size:
            return False

        def _sha(p: Path) -> str:
            h = hashlib.sha256()
            with Path(p).open("rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    h.update(chunk)
            return h.hexdigest()

        return _sha(Path(a)) == _sha(Path(b))
    except Exception:
        return False


def _unique_archive_base(name_index: Dict[Tuple[str, str], str], base: str, suffix: str) -> str:
    """同名但内容不同时，生成 -2/-3… 的可用基础名（不覆盖、不跳过、不删源文件）。"""
    suffix_key = suffix.lower()
    candidate = base
    n = 1
    while (candidate.lower(), suffix_key) in name_index:
        n += 1
        candidate = f"{base}-{n}"
        if n > 999:
            return f"{base}-{uuid.uuid4().hex[:6]}"
    return candidate


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
    plugin_version = "3.1.3"
    plugin_author = "LXT-A-X"
    author_url = "https://github.com/LXT-A-X"
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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._config = dict(_DEFAULT_CONFIG)
        # watchdog 观察者列表：事件驱动 Observer + 兼容轮询 PollingObserver（双保险）
        self._watcher_observers: List[Any] = []
        # 检查页「缺失字体修复」暂存的上传：tmp_path -> {path, file_name, name, family, vendor, matched}
        # 进程内缓冲需加锁（上传/列表/归类多线程并发）+ TTL 清理；_cleanup_tmp 会引用这些路径
        self._missing_uploads: Dict[str, Any] = {}
        self._missing_uploads_lock = threading.RLock()
        self._missing_uploads_ttl = 6 * 3600  # 6 小时未归类视为过期
        # 常驻子集化工作进程客户端（懒启动；停插件/重载配置时关闭）
        self._subset_worker: Optional[SubsetWorkerClient] = None
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
        # 监控事件重试计数：失败一次不算「已处理」，清标记后有限重试（防复制半截文件永久丢事件）
        self._watch_retries: Dict[str, int] = {}
        # 维护期间被推迟处理的监控事件路径（维护结束立即补处理）
        self._deferred_watch: set = set()
        # 全量检查/扫描互斥锁：前端按钮在运行中禁用之外，后端再兜底挡住并发触发，
        # 避免两个请求同时 copy/写库产生竞态（重复触发直接返回「正在运行」）
        self._scan_lock = threading.RLock()
        # 破坏性维护门闩（数据库恢复/清库/字体删除/全量重建/清空检查记录）：
        # 与 watcher、字体归档、字幕检查、子集化互斥，避免「刚删又写」「恢复中仍在索引」
        self._maintenance_lock = threading.RLock()
        # 运行中的轻量任务计数（归档/单文件事件等不持有 _scan_lock 的线程）：
        # 停服排空必须等它归零，避免「文件已进库、数据库记录没写进」的半截态
        self._active_jobs = 0
        # 优雅停止标志：stop_service 先置位，运行中的扫描/检查/子集化把「当前条目」完整
        # 处理完（copy+写库）再退出，剩余的条目不再处理，避免「文件在库、记录缺失」半截态
        self._stopping = False
        # ── 种子字体收集运行态 ──
        # hash -> {event, state, stats, record_id}：同一 hash 只收集一次，闸门靠 event 等待
        self._torrent_jobs: Dict[str, Dict[str, Any]] = {}
        self._torrent_jobs_lock = threading.RLock()
        # 收集并发上限：本地复制+解压以 IO 为主，限 2 个避免多剧同时下时互相排队拖垮闸门
        self._torrent_sem = threading.BoundedSemaphore(2)
        # 定时兜底扫描互斥：上一轮没跑完不叠加
        self._torrent_poll_lock = threading.Lock()
        # 整理完成兜底的延迟 Timer：hash -> Timer（同 hash 重复事件重置倒计时）
        self._torrent_delay_timers: Dict[str, threading.Timer] = {}
        # 实时监控通知聚合缓冲：连续放入的字体/字幕在 short 窗口内合并成一条归类通知，
        # 避免「放 5 个字体发 5 条通知」的刷屏。窗口内有新事件则滑动重置，到期统一发送。
        self._notify_agg: Dict[str, Any] = {
            "fonts": [],  # 已自动归档的文件名
            "fonts_skipped": [],  # 字体库已存在而跳过归档的文件名
            "fonts_dup_deleted": 0,  # 移动模式删除的重复源文件数
            "fonts_delete_failed": 0,  # 删除重复源文件失败数
            "font_failed": 0,  # 归档处理失败数
            "archive_mode": "",  # 本批字体事件首次到达时的归档模式快照（copy/move）
            "fonts_pending": [],  # 目录自动收集关闭时进入「待确认」的字体名（未归档）
            "subs_missing": [],  # {"name", "count", "fonts": 前几个缺失字体名}
            "subs_subset": [],  # 已子集化字幕文件名
            "subs_ok": [],  # 字体齐全（已完成字形级验证）字幕文件名
            "subs_unverified": [],  # 仅名称匹配、未完成字形级验证的字幕文件名
            "timer": None,
        }
        self._notify_agg_delay = 6  # 聚合窗口（秒）
        # 自动归档后的字体索引重建：脏标记 + 延迟聚合定时器（防批量归档反复重建）
        self._index_dirty = False
        self._index_rebuild_timer: Optional[threading.Timer] = None
        # ── 轮询接口瘦身缓存（Q2/Q3/Q4/Q5 修复）─────────────────
        # subsetted 判定缓存：file_path -> (mtime_ns, size, 是否内嵌)。
        # 检查列表/缺失聚合按文件 mtime+size 签名命中直接复用，不再每次读整个文件；
        # size 上限 500 条，超出清空重建（低频接口，重建一次不贵）
        self._ass_subset_cache: Dict[str, Tuple] = {}
        self._ass_subset_cache_limit = 500
        # /missing/summary 聚合 TTL 缓存：cache_key -> (计算时间戳, 结果)，
        # 60 秒内直接返回上次结果；字体库/字幕记录变更时由 _prune_stale_records/
        # 检查写入路径主动失效（见 _invalidate_missing_agg）
        self._missing_agg_cache: Optional[Tuple[str, float, Any]] = None
        self._missing_agg_ttl = 60
        # /stats 待整理计数缓存：input_dir -> (目录签名, 上次统计时间, 结果)，
        # 目录 mtime 未变且 30 秒内直接复用，避免每 30 秒全量 rglob
        self._pending_income_cache: Optional[Tuple[str, float, int]] = None
        # 批量归档判重索引：dest_dir -> {(base_lower, suffix_lower)} 已存在集合。
        # 首次归档某厂商目录时一次 rglob 建集合，批内后续归档 O(1) 判重，
        # 消除 O(N²)：万级字体库批量投 1000 个字体不再每次全目录遍历
        self._dest_name_index: Dict[str, set] = {}
        self._dest_name_index_limit = 64  # 厂商目录数上限，超出清空重建
        # _prune_stale_records 低频化闸门：记录上次执行时间，5 分钟内不重复全表 stat
        self._last_prune_ts = 0.0
        # ── fontTools 增量索引（v2）──
        # 全量重建/懒建索引互斥锁：与扫描锁分离，避免检查时等子集化任务
        self._index_build_lock = threading.RLock()
        self._index_last_build_ts = 0.0
        # 全量重建进行中：其他调用方（检查/子集化）直接跳过，宁可不动也不要按旧/空索引误判缺失
        self._index_rebuilding = False
        # 重建进度（供 UI 显示「正在重建：已处理 N/M」）：重建结束后清零
        self._index_progress: Dict[str, Any] = {"done": 0, "total": 0}
        # HarfBuzz 探测缓存（签名环境不变不重复 import）
        self._hb_probe: Optional[Tuple[bool, str]] = None

    def _ass_is_subsetted(self, fp: str) -> bool:
        """判定 ASS 是否已内嵌字体，带 (mtime_ns, size) 签名缓存（Q2/Q3 修复）。

        检查页列表 / 缺失聚合都按文件实时判定 subsetted（与字体库删减即时同步），
        但轮询路径每次 read_bytes 读整个字幕文件成本过高。这里用 stat 签名缓存：
        文件未变化直接复用上次判定结果，只读一次 stat；文件变化才重新读字节判定。
        """
        try:
            if not fp:
                return False
            p = Path(fp)
            st = p.stat()
            sig = (st.st_mtime_ns, st.st_size)
            entry = self._ass_subset_cache.get(fp)
            if entry and entry[0] == sig:
                return entry[1]
            subsetted = has_embedded_fonts(p.read_bytes())
            if self._ass_subset_cache_limit and len(self._ass_subset_cache) >= self._ass_subset_cache_limit:
                self._ass_subset_cache.clear()
            self._ass_subset_cache[fp] = (sig, subsetted)
            return subsetted
        except Exception:
            return False

    def _invalidate_missing_agg(self) -> None:
        """字体库/字幕记录变更后失效缺失聚合缓存（Q3 修复配合）"""
        self._missing_agg_cache = None

    def _ass_missing_agg_cached(self) -> Dict[str, Dict[str, Any]]:
        """_ass_missing_agg 的 TTL 缓存包装：60 秒内直接返回上次聚合结果，
        记录变更（检查写入/清理失效记录）时由 _invalidate_missing_agg 主动失效。（Q3 修复）
        """
        if self._db is None:
            return {}
        cache = self._missing_agg_cache
        if cache and (time.time() - cache[1]) < self._missing_agg_ttl:
            return cache[2]
        result = self._ass_missing_agg()
        self._missing_agg_cache = (None, time.time(), result)
        return result

    def _dest_names_for(self, dest_dir: Path) -> Dict[Tuple[str, str], str]:
        """目标厂商目录"已存在文件名"索引（Q5 修复）：首次访问该目录时一次 rglob
        建立 {(base_lower, suffix_lower): 文件路径} 映射，批内后续判重 O(1)；
        同时覆盖旧平铺布局（厂商/基础名.后缀）与新格式子目录（厂商/格式/基础名.后缀）。
        容量上限 64 个目录，超出清空重建（缓存容量策略）。
        """
        key = str(dest_dir)
        index = self._dest_name_index.get(key)
        if index is None:
            index = {}
            try:
                for c in dest_dir.rglob(f"*"):
                    try:
                        if c.is_file():
                            index[(c.stem.lower(), c.suffix.lower())] = str(c)
                    except Exception:
                        continue
            except Exception:
                pass
            if self._dest_name_index_limit and len(self._dest_name_index) >= self._dest_name_index_limit:
                self._dest_name_index.clear()
            self._dest_name_index[key] = index
        return index

    # ─── 生命周期 ────────────────────────────────────────
    def get_state(self) -> bool:
        """获取插件启用状态。"""
        return self._enabled

    def _apply_font_limits(self) -> None:
        """把配置的「字体文件大小上限」同步到解析/上传/预览的统一口径。

        上限只在运行时生效，不需要重启插件；调大后原有超限文件需重建索引才会纳入。
        """
        try:
            set_max_font_mb(self._config.get("max_font_mb"))
        except Exception:
            pass

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
        # 重载配置可能创建新 DB/临时目录：先关掉上一轮常驻工作进程，避免僵尸进程
        self._close_subset_worker()
        try:
            data_path = self.get_data_path()
            Path(data_path).mkdir(parents=True, exist_ok=True)
            self._db_path = Path(data_path) / "fonts.db"
            self._tmp_dir = Path(data_path) / "tmp"
            Path(self._tmp_dir).mkdir(parents=True, exist_ok=True)
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

            # 字体大小上限：无论配置来自宿主还是本地镜像，都按最终生效配置同步一次
            self._apply_font_limits()
            # 种子收集基线：首次启用（或旧配置无值）时写入当前时间，从此只处理之后完成的种子
            try:
                if bool(self._config.get("torrent_enabled")):
                    self._torrent_ensure_baseline()
            except Exception:
                pass

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
                self._stopping = False
                self._start_watcher()
                # 恢复检查页「缺失字体修复」上传缓冲（持久化），再清理孤儿临时文件
                self._load_missing_uploads()
                # 清理临时目录中的孤儿文件（未被待确认/字幕记录引用的上传缓存）
                self._cleanup_tmp()
                # 启动轻检：索引为空时从磁盘重建字体库，失效/变更文件增量修正（后台线程，不阻塞启动）
                self._schedule_startup_light_check()
            except Exception as err:
                _logger.error("字体分类管家初始化失败: %s", err)
                self._enabled = False

    def stop_service(self) -> None:
        """停止后台服务：停监控、清理孤儿临时文件、关闭数据库"""
        # 优雅停止：先关启用开关（新事件/新通知/新重建一律拒绝），再立停止标志
        self._enabled = False
        self._stopping = True
        self._stop_watcher()
        self._stop_polling()
        # 等待运行中的全量扫描/检查/子集化把当前条目完整写完（copy+写库完成才放锁），
        # 期间不关数据库，保证「文件入库 + 记录落库」原子成立；超时兜底强制继续
        self._wait_scan_drain(60)
        # 排空后关闭常驻子集化工作进程（正常 shutdown，超时强杀）
        self._close_subset_worker()
        # 取消未到期的入库扫描聚合计时器
        with self._lock:
            for t in self._show_timers.values():
                try:
                    t.cancel()
                except Exception:
                    pass
            self._show_timers.clear()
            self._pending_shows.clear()
            # 取消未到期的种子收集延迟计时器，并放行正在等待收集的字幕闸门
            try:
                with self._torrent_jobs_lock:
                    for t in self._torrent_delay_timers.values():
                        try:
                            t.cancel()
                        except Exception:
                            pass
                    self._torrent_delay_timers.clear()
                    for job in self._torrent_jobs.values():
                        ev = job.get("event")
                        if ev is not None:
                            try:
                                ev.set()
                            except Exception:
                                pass
            except Exception:
                pass
            # 取消未发送的通知聚合计时器并清空缓冲，避免旧实例残留发通知
            try:
                agg_timer = self._notify_agg.get("timer")
                if agg_timer:
                    agg_timer.cancel()
            except Exception:
                pass
            self._notify_agg["timer"] = None
            self._notify_agg["fonts"] = []
            self._notify_agg["fonts_skipped"] = []
            self._notify_agg["fonts_dup_deleted"] = 0
            self._notify_agg["fonts_delete_failed"] = 0
            self._notify_agg["font_failed"] = 0
            self._notify_agg["archive_mode"] = ""
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

    def _job_begin(self) -> None:
        """登记一个运行中的轻量任务（归档/单文件事件线程）。"""
        with self._lock:
            self._active_jobs += 1

    def _maintenance_begin(self, label: str) -> bool:
        """获取破坏性维护权（非阻塞）：同一时刻只允许一个维护动作。

        维护期间 watcher / 自动扫描 / 索引重建 / 子集化一律让步，
        避免「恢复或清库过程中后台仍在写库/索引」造成状态错位。
        """
        if self._maintenance_lock.acquire(blocking=False):
            try:
                self._db.add_log(f"维护开始：{label}（监控与后台任务暂停）", "warning")
            except Exception:
                pass
            return True
        return False

    def _maintenance_end(self, label: str = "") -> None:
        """释放维护权，并立刻补处理维护期间被推迟的监控事件。"""
        try:
            if label:
                self._db.add_log(f"维护结束：{label}", "info")
        except Exception:
            pass
        pending: List[str] = []
        with self._lock:
            pending = list(self._deferred_watch)
            self._deferred_watch.clear()
        for path in pending:
            try:
                self._schedule_watch_handle(path)
            except Exception:
                continue
        try:
            self._maintenance_lock.release()
        except Exception:
            pass

    def _maintenance_active(self) -> bool:
        """是否正处于破坏性维护中（非阻塞探测，不改变锁状态）。"""
        if self._maintenance_lock.acquire(blocking=False):
            self._maintenance_lock.release()
            return False
        return True

    def _job_end(self) -> None:
        """结束一个轻量任务；计数只减不增，异常路径也不会把计数拖成负数。"""
        with self._lock:
            if self._active_jobs > 0:
                self._active_jobs -= 1

    def _wait_scan_drain(self, timeout: float = 60.0) -> None:
        """等待运行中的扫描/检查/子集化/归档排空。

        停插件时调用：_stopping 已置位 → 运行线程处理完当前条即退出并释放 _scan_lock；
        归档/单文件事件不持有 _scan_lock，靠 _active_jobs 计数判断。这里等到
        「扫描锁空闲 且 任务计数为 0」才视为排空完成，随后才关库，杜绝
        「文件进了库、记录没写进」半截态。
        """
        try:
            import time as _time

            deadline = _time.time() + timeout
            while _time.time() < deadline:
                with self._lock:
                    jobs_idle = self._active_jobs == 0
                if jobs_idle and self._scan_lock.acquire(blocking=False):
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
                    # 子集化待处理（含压缩包展开的 .ass）在重启后仍需可处理
                    for r in self._db.query("SELECT file_path FROM subset_pending WHERE file_path != ''"):
                        if r.get("file_path"):
                            referenced.add(str(Path(r["file_path"]).resolve()))
                    # 缺失字体修复已上传待归类（持久化表 + 内存缓冲）：不能当孤儿删
                    for r in self._db.query("SELECT path FROM missing_uploads WHERE path != ''"):
                        if r.get("path"):
                            referenced.add(str(Path(r["path"]).resolve()))
                    with self._missing_uploads_lock:
                        for p in self._missing_uploads.keys():
                            referenced.add(str(Path(p).resolve()))
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
            # （字体已内嵌进成品字幕，夹子仅是备份，默认不同步输出目录）
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
            # 压缩包解压目录：清掉未被记录引用的解压文件，目录（含子目录）清空后删除
            for d in Path(self._tmp_dir).iterdir():
                if not d.is_dir() or not d.name.startswith("_unzip_"):
                    continue
                for f in list(d.rglob("*")):
                    if not f.is_file():
                        continue
                    if str(f.resolve()) in referenced:
                        continue
                    try:
                        f.unlink()
                        removed += 1
                    except Exception:
                        pass
                try:
                    for sub in sorted(
                        [p for p in d.rglob("*") if p.is_dir()],
                        key=lambda p: len(p.parts),
                        reverse=True,
                    ):
                        if not any(sub.iterdir()):
                            sub.rmdir()
                    if not any(d.iterdir()):
                        d.rmdir()
                except Exception:
                    pass
            # 种子收集暂存目录：只清 6 小时前的残留（运行中的任务自己会在 finally 清理）
            try:
                cutoff = time.time() - 6 * 3600
                for d in Path(self._tmp_dir).iterdir():
                    if not d.is_dir() or not d.name.startswith("torrent_"):
                        continue
                    try:
                        if d.stat().st_mtime < cutoff:
                            shutil.rmtree(d, ignore_errors=True)
                            removed += 1
                    except Exception:
                        pass
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
        if not bool(self.get_resource_or_config("weekly_reconcile")):
            jobs: List[Dict[str, Any]] = []
        else:
            # 每周差异核对：只按 size+mtime 比对并重解析差异文件（未变文件零解析），
            # 与「启动轻检」互补；关闭配置后不再注册该定时任务
            jobs = [
                {
                    "id": "ZitifenleiWeeklyReconcile",
                    "name": "字体索引每周差异核对",
                    "trigger": "cron",
                    "func": self._weekly_reconcile_task,
                    "kwargs": {"day_of_week": "sun", "hour": 4, "minute": 30},
                }
            ]
        # 种子字体收集兜底：总开关开启才注册，每 30 分钟扫一次「基线之后完成」的种子
        try:
            if self._torrent_enabled():
                jobs.append(
                    {
                        "id": "ZitifenleiTorrentCollect",
                        "name": "种子字体收集兜底扫描",
                        "trigger": "cron",
                        "func": self._torrent_poll_task,
                        "kwargs": {"minute": "*/30"},
                    }
                )
        except Exception:
            pass
        return jobs

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
        # 缺失字体专用目录兜底扫描（事件漏发/网络盘无事件时也能严格校验收录）：
        # 独立于「目录自动收集」开关——它是单独的严格接收通道，不放宽为普通归档
        try:
            missing_dir = self.get_resource_or_config("missing_font_dir") or ""
            if missing_dir and Path(missing_dir).is_dir():
                for f in list(Path(missing_dir).iterdir()):
                    if self._stopping:
                        break
                    if f.is_file() and is_font_file(f.name):
                        self._handle_missing_dir_font(f)
        except Exception as err:
            try:
                if self._db is not None:
                    self._db.add_log(f"缺失字体目录扫描失败: {err}", "warning")
            except Exception:
                pass
        # 「是否自动执行监控结果」关闭：监控字体改走「待确认」，由实时监控逐文件登记，
        # 轮询兜底不再整体重扫监控目录（避免每 60s rglob 整目录 + 「归档 N 个」计数虚高）
        if self.get_resource_or_config("auto_collect") is False:
            return
        stats: Optional[Dict[str, Any]] = None
        with self._lock:
            try:
                input_dir = self.get_resource_or_config("input_dir") or ""
                if not input_dir or not Path(input_dir).is_dir():
                    return
                stats = self._archive_from_dir(Path(input_dir), source="auto")
                added = len(stats["added"])
                if added:
                    self._db.add_log(f"自动监控：归档 {added} 个字体", "info")
                    # 轮询兜底归档后同样自动重建字体索引
                    self._schedule_index_rebuild()
                elif stats["skipped"] or stats["failed"]:
                    self._db.add_log(
                        f"自动监控：跳过已存在 {len(stats['skipped'])} 个，失败 {stats['failed']} 个",
                        "info" if not stats["failed"] else "warning",
                    )
            except Exception as err:
                self._db.add_log(f"自动监控失败: {err}", "error")
                stats = None
        # 通知放到锁外发送（post_message 为外部 IO，不占用监控线程持锁时间）。
        # 轮询兜底不做「只有跳过」的通知：复制模式下源文件常驻监控目录，
        # 每次轮询都会全量跳过，通知会周期性刷屏；真正代表有动静的是新增/失败/删除重复源文件。
        if stats and (
            stats["added"] or stats["failed"] or stats["dup_deleted"] or stats["delete_failed"]
        ):
            self._archive_notify(stats, source_label="监控", title_prefix="自动归档")

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

    def _schedule_watch_handle(self, path: str, delay: float = 2.0) -> None:
        """watchdog 事件统一防抖：同一路径 2 秒内重复事件重置计时器，
        文件写入/改名完成后才真正处理，避免读到半文件或漏掉改名后的正名文件。

        失败重试路径可用更大的 delay 再入队（不占用户操作）。
        """
        if self._stopping or not self._enabled or self._db is None:
            return
        with self._lock:
            timer = self._watch_timers.get(path)
            if timer:
                timer.cancel()
            timer = threading.Timer(max(0.1, float(delay)), self._on_watch_event, args=(path,))
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
        missing_dir_cfg = self.get_resource_or_config("missing_font_dir") or ""
        if missing_dir_cfg and not Path(missing_dir_cfg).is_dir():
            self._db.add_log(
                f"已配置「缺失字体接收目录」但目录不可达（{missing_dir_cfg}）：放入的字体无法严格校验", "warning"
            )
        paths: List[Path] = []
        if input_dir and Path(input_dir).is_dir():
            paths.append(Path(input_dir))
        if ass_dir and Path(ass_dir).is_dir():
            paths.append(Path(ass_dir))
        if subset_dir_cfg and Path(subset_dir_cfg).is_dir():
            paths.append(Path(subset_dir_cfg))
        if missing_dir_cfg and Path(missing_dir_cfg).is_dir():
            paths.append(Path(missing_dir_cfg))
        # 字体库目录也纳入监控：外部直接放入/替换的字体事件级发现（只增量索引，不归档）
        if lib_dir_cfg and Path(lib_dir_cfg).is_dir():
            paths.append(Path(lib_dir_cfg))
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
        """单文件事件包装：计入 _active_jobs，停服排空时不会在写库中途被掐断。"""
        self._job_begin()
        try:
            self._on_watch_event_impl(path)
        finally:
            self._job_end()

    def _on_watch_event_impl(self, path: str) -> None:
        """单文件事件：字体 → 自动归档；字幕 → 自动检查

        Q6 修复：锁内只做「去重表检查 + 标记」，磁盘 IO（字体复制/移动、字幕
        全文件读取）全部移到锁外——批量投递时 watchdog 事件线程不再为等锁排队，
        2 秒防抖窗口恢复意义；共享缓冲（_processed_recent/_notify_agg）访问仍各自加锁。
        """
        if self._stopping or not self._enabled or self._db is None:
            return
        # 破坏性维护中（数据库恢复/清库/字体删除/全量重建）：不处理本次事件，
        # 登记为待处理路径，维护结束立即补处理（不丢事件、不与维护并发写库）
        if self._maintenance_active():
            with self._lock:
                if len(self._deferred_watch) < 2000:
                    self._deferred_watch.add(str(path))
            return
        # 过滤 NAS 系统目录与回收站（参考实时软连接插件）：@eaDir / #recycle / 隐藏文件等
        if self._is_system_hidden_path(Path(path)):
            return
        success = False
        try:
            p = Path(path)
            if not p.is_file():
                return
            # 双观察者（Observer + PollingObserver）会对同一文件各触发一次：
            # 同一源文件 60 秒内已处理过则跳过，避免重复归档 / 生成重复检查记录
            key = str(p.resolve())
            now = time.time()
            with self._lock:
                last = self._processed_recent.get(key)
                if last is not None and now - last < 60.0:
                    return
                # 先标记再处理：后续同一文件的重复事件直接跳过（双观察者并发安全）
                self._processed_recent[key] = now
            try:
                # 缺失字体专用目录：先稳定等待，再逐 face 严格校验（不与普通归档重复处理）
                missing_dir_cfg = self.get_resource_or_config("missing_font_dir") or ""
                if (
                    missing_dir_cfg
                    and is_font_file(p.name)
                    and _path_within(p, Path(missing_dir_cfg))
                ):
                    success = self._handle_missing_dir_font(p)
                    return
                # 字体库目录内直接放入/替换的字体（用户手动放/外部工具同步）：
                # 只做增量索引，不归档、不移动、不删源文件（同一目录不被两套流程重复处理）
                lib_dir_cfg = self.get_resource_or_config("lib_dir") or ""
                if lib_dir_cfg and is_font_file(p.name) and _path_within(p, Path(lib_dir_cfg)):
                    if self._index_font_path(p):
                        self._db.add_log(f"字体库变更已增量索引: {p.name}", "info")
                    success = True
                    return
                if is_font_file(p.name):
                    # 归档函数内部自带成功/失败日志，此处不再重复记录；
                    # 返回值：>0=已归档，_ARCH_PENDING=进入待确认（目录自动收集关闭），
                    # _ARCH_DUP*=库中已存在跳过，None=处理失败
                    ret = self._archive_font_file(p, source="auto")
                    with self._lock:
                        if ret is not None and ret > 0:
                            # 归档结果进通知聚合缓冲：同一批连续放入的文件合并成一条归类通知
                            self._notify_agg["fonts"].append(p.name)
                            # 归档成功自动重建字体索引（延迟聚合，防批量归档反复重建）
                            self._schedule_index_rebuild()
                            success = True
                        elif ret == _ARCH_PENDING:
                            # 只进待确认（未归档）：走独立「待确认」通知，不再误报「已自动归档」
                            self._notify_agg["fonts_pending"].append(p.name)
                            success = True
                        elif ret in (_ARCH_DUP, _ARCH_DUP_DELETED, _ARCH_DUP_DEL_FAILED):
                            # 库中已有该字体：同样进通知（用户放了文件却「没归档」需要有交代）
                            self._notify_agg["fonts_skipped"].append(p.name)
                            success = True
                            if ret == _ARCH_DUP_DELETED:
                                self._notify_agg["fonts_dup_deleted"] = int(
                                    self._notify_agg.get("fonts_dup_deleted") or 0
                                ) + 1
                            elif ret == _ARCH_DUP_DEL_FAILED:
                                self._notify_agg["fonts_delete_failed"] = int(
                                    self._notify_agg.get("fonts_delete_failed") or 0
                                ) + 1
                        else:
                            # None：未配置库目录 / 复制 / 写库异常等失败
                            self._notify_agg["font_failed"] = int(
                                self._notify_agg.get("font_failed") or 0
                            ) + 1
                        # 本批字体事件首次到达时快照归档模式，通知标题/正文标明复制还是移动
                        if not self._notify_agg.get("archive_mode"):
                            self._notify_agg["archive_mode"] = (
                                self.get_resource_or_config("archive_mode") or "copy"
                            )
                    self._queue_agg_notify()
                elif is_ass_file(p.name):
                    subset_dir_cfg = self.get_resource_or_config("subset_dir") or ""
                    if subset_dir_cfg and _path_within(p, Path(subset_dir_cfg)):
                        # 「ASS目录监控子集」：放入即进入子集化流程——
                        # 「目录自动收集」开 → 立即后台自动子集化；关 → 进子集化页「待处理」等手动
                        self._schedule_subset_watch(p)
                        success = True
                        self._db.add_log(f"子集监控: {p.name} → 已进入子集化流程", "info")
                        return
                    result = self._check_ass_file(p, source="auto")
                    if result:
                        success = True
                        self._db.add_log(
                            f"实时检查字幕: {p.name} → {result['status_text']}",
                            "warning" if result["missing_count"] else "info",
                        )
                        missing = result.get("missing_fonts") or []
                        with self._lock:
                            if missing:
                                self._notify_agg["subs_missing"].append(
                                    {
                                        "name": p.name,
                                        "count": int(result.get("missing_count") or len(missing)),
                                        "fonts": missing,
                                    }
                                )
                            elif result.get("subsetted"):
                                # 已内嵌（子集化）字幕自带字体，不依赖字体库
                                self._notify_agg["subs_subset"].append(p.name)
                            elif result.get("status") == "partial_check":
                                # 仅名称匹配、未完成字形级验证：不能报「字体齐全」
                                self._notify_agg["subs_unverified"].append(p.name)
                            elif result.get("status") != "pending":
                                # 待检查状态（目录自动收集关闭时的登记）不通知「字体齐全」，避免误导
                                self._notify_agg["subs_ok"].append(p.name)
                        self._queue_agg_notify()
                        # 子集化自动处理（设置 auto_subset 开启时）：跟随「目录自动收集」开关——
                        # 开 → 立即后台自动子集化；关 → 进子集化页「待处理」等手动
                        if self.get_resource_or_config("auto_subset"):
                            self._schedule_subset_watch(p)
            except Exception as err:
                self._db.add_log(f"监控处理失败 {path}: {err}", "error")
            finally:
                # 本次处理结束，移除防抖条目（RLock 可重入）
                with self._lock:
                    self._watch_timers.pop(path, None)
                    # 归档/检查超时判定的时机：只有确实处理成功才保留 60s 去重窗口；
                    # 失败（半截文件/IO 抖动/库目录未配置）必须清除标记并安排有限重试，
                    # 否则后续 modify 事件会被去重吞掉，文件要等下一次人工扫描才被处理。
                    if not success and not self._stopping:
                        key_retry = str(p.resolve())
                        self._processed_recent.pop(key_retry, None)
                        tries = int(self._watch_retries.get(key_retry, 0))
                        if tries < 3:
                            self._watch_retries[key_retry] = tries + 1
                            try:
                                self._schedule_watch_handle(str(p), delay=5.0 * (tries + 1))
                                self._db.add_log(
                                    f"监控处理未完成，已安排第 {tries + 1} 次重试：{p.name}", "warning"
                                )
                            except Exception:
                                pass
                        else:
                            self._watch_retries.pop(key_retry, None)
                    elif success:
                        self._watch_retries.pop(str(p.resolve()), None)
                    # 限制增长：超过阈值时清理 5 分钟前的旧条目
                    if len(self._processed_recent) > 2000:
                        expire = now - 300.0
                        for k in [kk for kk, tt in self._processed_recent.items() if tt < expire]:
                            self._processed_recent.pop(k, None)
                    if len(self._watch_retries) > 2000:
                        self._watch_retries.clear()
        except Exception:
            # 文件在 stat/resolve 阶段消失（瞬时文件/系统临时文件）——静默忽略
            return

    def _queue_auto_pending(self, file_path: Path, source: str) -> Optional[int]:
        """监控到的字体进「待确认」列表（目录自动收集关闭时的行为，与手动上传一致）"""
        if self._db is None:
            return None
        # 稳定性探测：写入中的半截字体不进待确认
        if not _wait_file_stable(file_path):
            try:
                self._db.add_log(f"跳过 {file_path.name}：文件仍在写入，稍后重试", "warning")
            except Exception:
                pass
            return None
        try:
            if self._db.query_one(
                "SELECT id FROM pending_fonts WHERE file_path = ?", (str(file_path),)
            ):
                return None
            if self._db.count_fonts_by_path(str(file_path)):
                return None
            scan_mode = "internal"  # fontTools 为唯一权威解析口径
            try:
                meta = parse_font_metadata(
                    file_path, scan_mode=scan_mode, filename_hint=file_path.stem
                )
            except Exception:
                meta = {"name": file_path.stem, "family": file_path.stem, "vendor": "未知厂商", "designer": ""}
            if not meta.get("internal_ok", True):
                # 无法解析的字体不进待确认，避免用户一键整理时把坏文件归档入库
                self._db.add_log(
                    f"跳过 {file_path.name}：字体无法解析（可能损坏或仍在写入）", "warning"
                )
                return None
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

    def _handle_missing_dir_font(self, file_path: Path) -> bool:
        """缺失字体专用目录：等稳定 → 逐 face 严格校验 → 收录或拒绝。

        与普通字体库目录的区别（两套策略互不重复处理，靠目录归属路由）：
        - 普通库/监控目录：常规归档，只校验指纹与元数据；
        - 缺失专用目录：必须命中当前缺失目标，且同一 face 真实覆盖至少一个缺失字符；
          无关/损坏/未覆盖任何缺字的字体拒绝入库，移入同目录 rejected/ 留档（不删用户文件）。
        返回 True=已处理完毕（收录/拒绝），False=本次未完成（外层安排有限重试）。
        """
        if self._db is None:
            return False
        # 稳定性探测：写入中的半截字体不校验（半文件必然解析失败，白等一次重试）
        if not _wait_file_stable(file_path):
            return False
        try:
            targets = self._missing_glyph_targets()
        except Exception as err:
            self._db.add_log(f"缺失字体目录校验失败（读取缺失目标异常）: {err}", "warning")
            return False
        verdict = self._evaluate_font_for_targets(file_path, targets) if targets else {
            "ok": False,
            "reason": "当前没有缺失字体目标（缺失列表为空）",
            "name": "",
        }
        if not verdict.get("ok"):
            reason = str(verdict.get("reason") or "未覆盖任何缺字")
            missing_dir = Path(self.get_resource_or_config("missing_font_dir") or "")
            try:
                rejected_dir = missing_dir / "rejected"
                rejected_dir.mkdir(parents=True, exist_ok=True)
                dest = rejected_dir / file_path.name
                if dest.exists():
                    dest = rejected_dir / f"{file_path.stem}-{int(time.time())}{file_path.suffix}"
                shutil.move(str(file_path), str(dest))
                self._db.add_log(
                    f"缺失字体目录拒绝 {file_path.name}：{reason}（已移至 rejected/ 留档）", "warning"
                )
            except Exception as err:
                self._db.add_log(
                    f"缺失字体目录拒绝 {file_path.name}：{reason}（留档移动失败: {err}）", "warning"
                )
            return True
        ret = self._archive_font_file(file_path, source="missing")
        if ret is not None and ret > 0:
            self._schedule_index_rebuild()
            self._db.add_log(
                f"缺失字体目录收录 {file_path.name} → 解决「{verdict.get('matched')}」"
                f"（覆盖 {verdict.get('covered_chars') or '缺失字符'}）",
                "info",
            )
            return True
        if ret in (_ARCH_PENDING, _ARCH_DUP, _ARCH_DUP_DELETED, _ARCH_DUP_DEL_FAILED):
            if ret == _ARCH_PENDING:
                self._db.add_log(
                    f"缺失字体目录收录 {file_path.name} → 已加入「待确认」（目录自动收集关闭）", "info"
                )
            return True
        return False

    def _archive_font_file(
        self, file_path: Path, source: str = "auto", force_pending: bool = False
    ) -> Optional[int]:
        """归档入口包装：计入 _active_jobs，停服排空时等本次 copy+写库完整结束。"""
        self._job_begin()
        try:
            return self._archive_font_file_impl(file_path, source, force_pending=force_pending)
        finally:
            self._job_end()

    def _archive_font_file_impl(
        self, file_path: Path, source: str = "auto", force_pending: bool = False
    ) -> Optional[int]:
        """自动归档单个字体（监控发现）：直接写入字体库（不经待确认）。

        「目录自动收集」关闭时：监控到的字体改进「待确认」，等待一键整理。
        未配置「字体库目录」时不静默：写明确警示日志。

        返回值：>0=归档成功（字体 ID）；_ARCH_PENDING=进待确认；
        _ARCH_DUP / _ARCH_DUP_DELETED / _ARCH_DUP_DEL_FAILED=库中已存在跳过；
        None=处理失败。调用方据此区分「跳过」与「失败」分别统计。
        """
        # 收集开关：关闭 → 只收下待确认，不自动归档。
        # 种子来源以「收集后进待整理」为准：关=直接入库，不再受「自动执行监控结果」总开关影响，
        # 否则会与设置页「关：直接归档进字体库」的说明不一致。
        if force_pending:
            return self._queue_auto_pending(file_path, source)
        if source != "torrent" and self.get_resource_or_config("auto_collect") is False:
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
                return _ARCH_DUP
            if self._db.count_fonts_by_path(str(file_path)):
                # 记录源文件已处理（仪表盘「待整理」排除该文件）
                self._db.mark_font_processed(str(file_path))
                return _ARCH_DUP
        except Exception:
            pass
        scan_mode = "internal"  # fontTools 为唯一权威解析口径
        # 稳定性探测：写入未完成的半截文件不入库（否则名称判重会让完整文件永远被跳过）
        if not _wait_file_stable(file_path):
            self._db.add_log(
                f"跳过 {file_path.name}：文件仍在写入（等待稳定超时），稍后重试", "warning"
            )
            return None
        try:
            meta = parse_font_metadata(file_path, scan_mode=scan_mode, filename_hint=file_path.stem)
        except Exception:
            meta = {"name": file_path.stem, "family": file_path.stem, "vendor": "未知厂商", "designer": ""}
        # 解析失败（fontTools 打不开）不入库：损坏/半截字体进库后难以清理，明确记警告并等待人工确认
        if not meta.get("internal_ok", True):
            self._db.add_log(
                f"跳过 {file_path.name}：字体无法解析（可能损坏或仍在写入），请确认后手动整理",
                "warning",
            )
            return None
        archive_mode = self.get_resource_or_config("archive_mode") or "copy"
        try:
            dest_dir = Path(lib_dir) / safe_filename_component(
                str(meta.get("vendor") or "未知厂商"), "未知厂商"
            )
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
            # 内部名来自不可信字体文件：清洗后方可拼路径（防 ../、盘符、分隔符越界）
            base = safe_filename_component(base)
            # 按格式分子文件夹归档：字体库/厂商/格式/基础名.后缀（同字体不同格式共存，目录清晰）
            fmt_dir = dest_dir / _font_subdir_name(file_path.suffix)
            # Q5 修复：判重走"目标厂商目录已存在文件名"索引（_dest_names_for 首次
            # 一次 rglob 建表，批内后续 O(1)），去除批量归档的 O(N²) 递归 rglob；
            # 索引 key 同时覆盖旧平铺布局与新格式子目录（rglob 全目录收集）
            name_index = self._dest_names_for(dest_dir)
            try:
                existing = name_index.get((base.lower(), file_path.suffix.lower()), None)
            except Exception:
                existing = None
            if existing is not None:
                existing = Path(existing)
            if existing and _files_identical(file_path, existing):
                # 字体库已存在「内容完全相同」的同名同后缀字体（含旧平铺布局与格式子文件夹）：
                # 跳过本次归档，保证轮询/兜底全量扫描存量文件时幂等
                self._db.add_log(f"跳过 {file_path.name}：字体库已存在 {existing.name}", "info")
                skip_ret = _ARCH_DUP
                # 「移动原文件」模式 + 开关开启：删除监控目录残留的重复源文件，
                # 避免 move 模式下判重跳过导致源文件一直堆在监控目录；复制模式不受影响
                if archive_mode == "move" and self.get_resource_or_config("move_delete_duplicate"):
                    try:
                        if file_path.is_file():
                            file_path.unlink()
                            skip_ret = _ARCH_DUP_DELETED
                            self._db.add_log(
                                f"已删除监控目录残留的重复源文件 {file_path.name}（字体库已有 {existing.name}）",
                                "info",
                            )
                    except Exception as err:
                        skip_ret = _ARCH_DUP_DEL_FAILED
                        self._db.add_log(f"删除重复源文件失败 {file_path.name}: {err}", "warning")
                # 源文件虽然同源已入库（仅更名），同样算已处理，「待整理」不再计入
                self._db.mark_font_processed(str(file_path))
                return skip_ret
            if existing:
                # 同名但内容不同（升级版/同 family 不同字重被解析成同名）：
                # 绝不能按名称判重删源文件，改名 -2/-3 另存，旧版与新版本都保留
                base = _unique_archive_base(name_index, base, file_path.suffix)
                self._db.add_log(
                    f"{file_path.name} 与库内 {existing.name} 同名但内容不同，另存为 {base}{file_path.suffix}",
                    "warning",
                )
            try:
                fmt_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            dest = fmt_dir / f"{base}{file_path.suffix}"
            # 第二道防线：即使清洗规则被绕过，目标也必须仍在字体库内
            if not _path_within(dest, Path(lib_dir)):
                self._db.add_log(f"拒绝归档：目标越界 {dest}", "error")
                return None
            # 原子落盘：先写隐藏临时名，校验大小与源一致后再 os.replace 换正名。
            # 半截/复制失败只会留下临时文件（随即清理），不会出现「正名文件内容不完整」。
            src_size = file_path.stat().st_size
            tmp_dest = fmt_dir / f".{dest.name}.tmp-{uuid.uuid4().hex[:8]}"
            try:
                shutil.copy2(str(file_path), str(tmp_dest))
                written = tmp_dest.stat().st_size
                if written != src_size:
                    raise RuntimeError(f"写入大小不一致（源 {src_size}，目标 {written}）")
                os.replace(str(tmp_dest), str(dest))
            except Exception:
                try:
                    tmp_dest.unlink(missing_ok=True)
                except Exception:
                    pass
                raise
            # move 模式：正名落位且校验通过后才删源文件（跨盘 move 也不会有半截丢失）
            if archive_mode == "move":
                try:
                    file_path.unlink()
                except Exception as err:
                    self._db.add_log(
                        f"已归档 {dest.name}，但删除源文件 {file_path.name} 失败: {err}", "warning"
                    )
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
        except Exception as err:
            # 写库失败：回滚刚归档的文件，不留「文件进库、记录缺失」的孤儿
            # （copy 模式删掉副本；move 模式源已被删且未恢复时搬回原位）
            try:
                if dest.exists():
                    if archive_mode == "move" and not Path(str(file_path)).exists():
                        shutil.move(str(dest), str(file_path))
                        self._db.add_log(f"自动归档回滚: {dest.name} 已移回 {file_path.name}", "warning")
                    else:
                        dest.unlink(missing_ok=True)
                        self._db.add_log(f"自动归档回滚: 已删除副本 {dest.name}", "warning")
            except Exception:
                pass
            try:
                self._db.add_log(f"写库失败 {dest.name}: {err}", "error")
            except Exception:
                pass
            return None
        # 记录已落库：后续标记/索引失败只记日志，绝不能再回滚文件（否则记录指向不存在的文件）
        try:
            # 记录源文件已处理（复制模式下源文件留存字体监控目录，「待整理」不再计入）
            self._db.mark_font_processed(str(file_path))
            self._db.add_log(f"自动归档: {dest.name}", "info")
            # 同步写入 fontTools 增量索引（face/cmap/别名），字形级检测与子集化立即可用
            self._index_font_path(dest)
            # 归档成功：同步更新目录文件名索引，批内后续同名字体可直接判重命中
            dkey = str(dest_dir)
            if dkey in self._dest_name_index:
                self._dest_name_index[dkey][(dest.stem.lower(), dest.suffix.lower())] = str(dest)
            # 归档成功：标记字体索引需要重建（由调用方调度延迟聚合重建）
            self._index_dirty = True
        except Exception as err:
            try:
                self._db.add_log(f"归档后置处理失败 {dest.name}: {err}", "warning")
            except Exception:
                pass
        return font_id

    def _archive_from_dir(
        self, directory: Path, source: str = "auto", force_pending: bool = False
    ) -> Dict[str, Any]:
        """批量自动归档目录内字体（定时兜底）：直接写入字体库，不经过待确认。

        返回统计字典（供通知按「新增 / 跳过 / 失败 / 删除重复源文件」分项展示）：
          added: [归档成功的源文件名]
          skipped: [字体库已存在而跳过的源文件名]
          failed: 处理失败数量
          dup_deleted: 移动模式下实际删除的重复源文件数
          delete_failed: 删除重复源文件失败数
          pending: 进入「待确认」的数量（目录自动收集关闭）
        """
        stats: Dict[str, Any] = {
            "added": [],
            "skipped": [],
            "failed": 0,
            "dup_deleted": 0,
            "delete_failed": 0,
            "pending": 0,
        }
        if not directory.is_dir():
            return stats
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
            ret = self._archive_font_file(f, source=source, force_pending=force_pending)
            if ret is not None and ret > 0:
                stats["added"].append(f.name)
            elif ret == _ARCH_PENDING:
                stats["pending"] += 1
            elif ret == _ARCH_DUP:
                stats["skipped"].append(f.name)
            elif ret == _ARCH_DUP_DELETED:
                stats["skipped"].append(f.name)
                stats["dup_deleted"] += 1
            elif ret == _ARCH_DUP_DEL_FAILED:
                stats["skipped"].append(f.name)
                stats["delete_failed"] += 1
            else:
                # None=未配置库目录/复制/写库异常等失败
                stats["failed"] += 1
        return stats

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
        if self._stopping or not self._enabled:
            return
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

    @staticmethod
    def _short_names(names: List[str], limit: int) -> str:
        """通知里的字体名截断：最多展示 limit 个，超出补「…」"""
        shown = list(names)[: max(0, int(limit))]
        text = "、".join(str(n) for n in shown)
        return text + ("…" if len(names) > len(shown) else "")

    def _archive_notify(
        self,
        stats: Dict[str, Any],
        mode: Optional[str] = None,
        source_label: str = "监控",
        title_prefix: str = "自动归档",
        extra: str = "",
    ) -> None:
        """字体归档类通知统一模板（实时监控 / 全量检查 / 全量扫描共用）。

        标题与正文首行都标明复制/移动模式；新增名最多 10 个、跳过名最多 3 个；
        末尾「已删除监控目录中的重复源文件」仅在移动模式 + 删除开关开 + 实际删除时出现。
        """
        added = list(stats.get("added") or [])
        skipped = list(stats.get("skipped") or [])
        failed = int(stats.get("failed") or 0)
        dup_deleted = int(stats.get("dup_deleted") or 0)
        delete_failed = int(stats.get("delete_failed") or 0)
        total = len(added) + len(skipped) + failed
        if not total:
            return
        if not self.get_resource_or_config("notify_enabled"):
            return
        mode = mode or (self.get_resource_or_config("archive_mode") or "copy")
        is_move = mode == "move"
        mode_name = "移动模式" if is_move else "复制模式"
        mode_desc = "移动模式：源文件已移入字体库" if is_move else "复制模式：源文件保留在监控目录"
        lines = [f"📥 本次{source_label}到 {total} 个字体（{mode_desc}）", ""]
        if added:
            lines.append(f"✅ 新增归档 {len(added)} 个：{self._short_names(added, 10)}")
        if skipped:
            lines.append(f"⏭ 库中已存在跳过 {len(skipped)} 个：{self._short_names(skipped, 3)}")
        if failed:
            lines.append(f"⚠ 处理失败 {failed} 个（详见插件日志）")
        if delete_failed:
            lines.append(f"⚠ 删除重复源文件失败 {delete_failed} 个（详见插件日志）")
        if extra:
            lines.append(extra)
        if dup_deleted and is_move:
            lines += ["", f"🗑 已删除监控目录中的重复源文件 {dup_deleted} 个"]
        self._notify(f"字体分类管家：{title_prefix}（{mode_name}）", "\n".join(lines))

    def _flush_agg_notify(self) -> None:
        """聚合窗口到期：把缓冲内的归档/字幕检查结果归类成一条通知发送。

        字体归档走统一模板 _archive_notify（区分复制/移动、新增/跳过/失败分项）；
        字幕按缺失/子集化/齐全分类。数量大时折叠显示（前几个 + …），避免消息过长。
        """
        with self._lock:
            buf = self._notify_agg
            fonts = list(buf.get("fonts") or [])
            fonts_skipped = list(buf.get("fonts_skipped") or [])
            fonts_dup_deleted = int(buf.get("fonts_dup_deleted") or 0)
            fonts_delete_failed = int(buf.get("fonts_delete_failed") or 0)
            font_failed = int(buf.get("font_failed") or 0)
            archive_mode = str(buf.get("archive_mode") or "")
            fonts_pending = list(buf.get("fonts_pending") or [])
            subs_missing = list(buf.get("subs_missing") or [])
            subs_subset = list(buf.get("subs_subset") or [])
            subs_ok = list(buf.get("subs_ok") or [])
            subs_unverified = list(buf.get("subs_unverified") or [])
            buf["fonts"] = []
            buf["fonts_skipped"] = []
            buf["fonts_dup_deleted"] = 0
            buf["fonts_delete_failed"] = 0
            buf["font_failed"] = 0
            buf["archive_mode"] = ""
            buf["fonts_pending"] = []
            buf["subs_missing"] = []
            buf["subs_subset"] = []
            buf["subs_ok"] = []
            buf["subs_unverified"] = []
            buf["timer"] = None
        if not (
            fonts
            or fonts_skipped
            or font_failed
            or fonts_dup_deleted
            or fonts_delete_failed
            or fonts_pending
            or subs_missing
            or subs_subset
            or subs_ok
            or subs_unverified
        ):
            return
        if not self.get_resource_or_config("notify_enabled"):
            return
        # 字体与字幕分开通知：字体一条、字幕一条，不混在同一消息里
        if fonts or fonts_skipped or font_failed or fonts_dup_deleted or fonts_delete_failed:
            # 字体归档通知（仅字体）：新增/跳过/失败分项，只有跳过时也发（用户需要知道去向）
            self._archive_notify(
                {
                    "added": fonts,
                    "skipped": fonts_skipped,
                    "failed": font_failed,
                    "dup_deleted": fonts_dup_deleted,
                    "delete_failed": fonts_delete_failed,
                },
                mode=archive_mode or None,
                source_label="监控",
                title_prefix="自动归档",
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
        if subs_missing or subs_subset or subs_ok or subs_unverified:
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
                    f"✅ 字体齐全（已逐字符验证）{len(subs_ok)} 个：{'、'.join(shown)}"
                    + (f" 等 {more} 个" if more > 0 else "")
                )
            if subs_unverified:
                shown = subs_unverified[:10]
                more = len(subs_unverified) - len(shown)
                lines.append(
                    f"⚠️ 未验证字形（仅名称匹配）{len(subs_unverified)} 个：{'、'.join(shown)}"
                    + (f" 等 {more} 个" if more > 0 else "")
                )
            if subs_missing:
                lines.append("可在「检查页」上传缺失字体入库消除标记")
            self._notify("字体分类管家：字幕检查", "\n".join(lines))

    # ─── 子集化引擎 ──────────────────────────────────────
    def _subset_engine_ready(self) -> Tuple[bool, str]:
        """子集化引擎就绪判断（内置 HarfBuzz / uharfbuzz）。

        返回 (ok, 说明)。上传/全量/重试/自动子集化入口统一用它。
        """
        hb_ok, hb_info = self._hb_status()
        if hb_ok:
            return True, "harfbuzz"
        return False, f"子集化引擎不可用：{hb_info}"

    # ─── fontTools 增量索引（v2，字形级检测/子集化的权威口径） ───

    def _index_font_path(self, path: str | Path) -> bool:
        """单个字体文件 → 解析全部 face 并事务性写入索引。

        归档/入库路径调用；失败只记日志，不回滚已完成的归档（索引可重建修复）。
        """
        if self._db is None:
            return False
        try:
            resolved = Path(path).resolve()
            inspection = inspect_font(resolved)
            result = self._db.upsert_font_file(inspection)
            if inspection.status == "invalid":
                self._db.add_log(
                    f"字体索引: {resolved.name} 解析失败（{inspection.error}）",
                    "warning",
                )
            if result.get("changed"):
                self._index_dirty = True
                # 字体库新增/更新字体后，缺失聚合缓存立即失效（按新覆盖重算）
                self._invalidate_missing_agg()
            return True
        except Exception as err:
            if self._db is not None:
                try:
                    self._db.add_log(f"字体索引写入失败 {Path(path).name}: {err}", "warning")
                except Exception:
                    pass
            return False

    def _remove_font_from_index(self, path: str | Path) -> bool:
        """删除字体文件记录（磁盘删除/记录清理时同步撤销索引贡献）。"""
        if self._db is None or not path:
            return False
        candidates = [str(path)]
        try:
            candidates.insert(0, str(Path(path).resolve()))
        except Exception:
            pass
        for candidate in candidates:
            try:
                if self._db.remove_font_file(candidate).get("removed"):
                    return True
            except Exception:
                continue
        return False

    def _rebuild_font_index(
        self, force_hash: bool = False, full: bool = False, hash_sample: int = 0
    ) -> Dict[str, Any]:
        """扫描字体库目录提交索引；删除磁盘上已不存在的索引记录。

        默认增量（日常归档/入库）：size+mtime_ns 未变的文件直接跳过解析。
        full=True（子集化页「全部重建」）：解析结果先写暂存表，全部完成后单事务
        原子切换到正式索引；中途停止/异常则丢弃暂存、保留旧索引（不再清空后裸奔）。

        完整性门槛（P0）：`inspect_font` 返回 status=invalid 属于「确认损坏」，可安全
        重写；但文件读取/权限/IO/解析抛异常属于「结果不确定」——不能静默丢弃其旧索引
        贡献。全量模式下出现任何不确定失败一律不提交暂存（保留旧索引），除非显式
        allow_incomplete。增量模式无法确定时同样不写该文件（旧记录保持不动）。

        hash_sample>0 时对「stat 未变」的文件额外抽检 N 个重算 SHA-256（周核对用）：
        size+mtime 相同但内容被替换（复制工具/恢复备份/touch 保时间戳）也能被发现。
        """
        stats: Dict[str, Any] = {
            "ok": False,
            "scanned": 0,
            "indexed": 0,
            "unchanged": 0,
            "invalid": 0,
            "failed": 0,
            "failed_paths": [],
            "removed": 0,
            "hash_checked": 0,
            "hash_mismatch": 0,
            "error": "",
        }
        if self._db is None:
            stats["error"] = "数据库未初始化"
            return stats
        # 破坏性维护（数据库恢复/清库/删除字体）进行中：本轮不重建，避免与恢复交叉写索引
        if not self._maintenance_lock.acquire(blocking=False):
            stats["error"] = "维护任务执行中，索引重建已跳过"
            return stats
        try:
            return self._rebuild_font_index_impl(
                stats, force_hash=force_hash, full=full, hash_sample=hash_sample
            )
        finally:
            try:
                self._maintenance_lock.release()
            except Exception:
                pass

    def _rebuild_font_index_impl(
        self,
        stats: Dict[str, Any],
        force_hash: bool = False,
        full: bool = False,
        hash_sample: int = 0,
        allow_incomplete: bool = False,
    ) -> Dict[str, Any]:
        lib_dir = self.get_resource_or_config("lib_dir") or ""
        if not lib_dir or not Path(lib_dir).is_dir():
            stats["error"] = "字体库目录未配置或不存在"
            return stats
        root = Path(lib_dir).resolve()
        with self._index_build_lock:
            self._index_rebuilding = True
            try:
                if full:
                    try:
                        self._db.stage_font_index_begin()
                    except Exception as err:
                        stats["error"] = f"初始化重建暂存区失败: {err}"
                        return stats
                seen: set = set()
                try:
                    candidates = [
                        item
                        for item in root.rglob("*")
                        if item.is_file() and is_font_file(item.name) and not self._is_system_hidden_path(item)
                    ]
                except Exception as err:
                    stats["error"] = f"扫描字体库失败: {err}"
                    if full:
                        try:
                            self._db.stage_font_index_discard()
                        except Exception:
                            pass
                    return stats
                # 进度基准：UI 用「已处理 / 候选总数」展示重建进度（结束后清零）
                self._index_progress = {"done": 0, "total": len(candidates)}
                aborted = False

                def _record_uncertain(item_name: str, why: str) -> None:
                    """记录「结果不确定」的文件：不静默漏过，全量模式下阻止提交。"""
                    stats["failed"] += 1
                    if len(stats["failed_paths"]) < 20:
                        stats["failed_paths"].append(item_name)
                    try:
                        self._db.add_log(f"字体索引结果不确定 {item_name}: {why}", "warning")
                    except Exception:
                        pass

                hash_budget = max(0, int(hash_sample))

                def _hash_mismatch(resolved: Path, existing: Dict[str, Any]) -> bool:
                    """抽检：重算 SHA-256 与索引记录比对（发现同大小同时间戳的内容替换）。

                    hash_budget 用尽后不再计算，直接按 stat 判定未变。
                    """
                    nonlocal hash_budget
                    if hash_budget <= 0:
                        return False
                    old_sha = str(existing.get("sha256") or "")
                    if not old_sha:
                        return False
                    hash_budget -= 1
                    try:
                        h = hashlib.sha256()
                        with resolved.open("rb") as fh:
                            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                                h.update(chunk)
                        stats["hash_checked"] += 1
                        if h.hexdigest() != old_sha:
                            stats["hash_mismatch"] += 1
                            return True
                    except Exception as err:
                        _record_uncertain(resolved.name, f"哈希抽检失败: {err}")
                    return False

                for item in sorted(candidates):
                    if self._stopping:
                        aborted = True
                        break
                    try:
                        resolved = item.resolve()
                    except Exception as err:
                        _record_uncertain(item.name, f"解析真实路径失败: {err}")
                        continue
                    key = str(resolved)
                    seen.add(key)
                    stats["scanned"] += 1
                    self._index_progress["done"] = stats["scanned"]
                    try:
                        st = resolved.stat()
                    except Exception as err:
                        _record_uncertain(item.name, f"读取文件属性失败: {err}")
                        continue
                    try:
                        existing = self._db.get_font_file(key)
                        if (
                            not full
                            and not force_hash
                            and existing
                            and int(existing.get("size") or 0) == st.st_size
                            and int(existing.get("mtime_ns") or 0) == st.st_mtime_ns
                            and str(existing.get("status") or "ok") in ("ok", "partial")
                        ):
                            if not _hash_mismatch(resolved, existing):
                                stats["unchanged"] += 1
                                continue
                        inspection = inspect_font(resolved)
                        if full:
                            self._db.stage_font_index_add(inspection)
                        else:
                            self._db.upsert_font_file(inspection)
                        stats["indexed"] += 1
                        if inspection.status == "invalid":
                            stats["invalid"] += 1
                    except Exception as err:
                        # 解析/写索引抛异常 = 结果不确定（权限/IO/解析器异常）：
                        # 不能当作「确认损坏」丢弃旧索引贡献，也不能静默漏过
                        _record_uncertain(item.name, str(err))
                if aborted:
                    # 停服/中途中断：全量重建丢弃暂存，正式索引保持上一次的可用状态
                    if full:
                        try:
                            self._db.stage_font_index_discard()
                        except Exception:
                            pass
                    stats["error"] = "重建已中止（旧索引保留）"
                    return stats
                if full:
                    # 提交前完整性门槛：候选必须全部有明确结果（有效/确认损坏），
                    # 出现任何「结果不确定」的文件一律不切换，保留旧索引（默认拒绝不完整索引）
                    accounted = stats["indexed"] + stats["unchanged"] + stats["failed"]
                    if not allow_incomplete and (
                        stats["failed"] or accounted != len(candidates)
                    ):
                        try:
                            self._db.stage_font_index_discard()
                        except Exception:
                            pass
                        detail = "、".join(stats["failed_paths"][:5])
                        stats["error"] = (
                            f"全量重建未提交：{stats['failed']} 个文件结果不确定"
                            + (f"（{detail}）" if detail else "")
                            + "，已保留旧索引。请检查文件权限/网络盘后重试"
                        )
                        try:
                            self._db.add_log(stats["error"], "warning")
                        except Exception:
                            pass
                        return stats
                    try:
                        self._db.stage_font_index_commit(lib_dir=str(root), engine="fontTools")
                    except Exception as err:
                        try:
                            self._db.stage_font_index_discard()
                        except Exception:
                            pass
                        stats["error"] = f"切换索引失败（旧索引保留）: {err}"
                        return stats
                else:
                    # 增量模式：清理磁盘上已不存在的（只处理字体库根目录下的记录，外部路径不动）
                    try:
                        rows = self._db.query("SELECT id, path FROM font_files")
                        for row in rows:
                            path_text = str(row.get("path") or "")
                            if not path_text or path_text in seen:
                                continue
                            try:
                                if _path_within(Path(path_text), root):
                                    removed = self._db.remove_font_file(path_text)
                                    if removed.get("removed"):
                                        stats["removed"] += 1
                            except Exception:
                                continue
                    except Exception:
                        pass
                    try:
                        self._db.index_set("last_rebuild", self._db.now())
                        self._db.index_set("engine", "fontTools")
                        self._db.index_set("lib_dir", str(root))
                    except Exception:
                        pass
                self._index_last_build_ts = time.time()
                stats["ok"] = True
                if stats["indexed"] or stats["removed"] or full:
                    # 索引内容变化（新增/更新/删除）→ 缺失聚合按新库重算
                    self._invalidate_missing_agg()
                return stats
            finally:
                self._index_rebuilding = False
                self._index_progress = {"done": 0, "total": 0}

    def _ensure_font_index(self, force: bool = False) -> bool:
        """索引可用性保障：库目录变更/索引为空时懒做一次全量扫描（带节流）。

        有重建进行中时直接返回 False：让检查/子集化本轮跳过，宁可不动，
        也不要在旧索引或空索引上批量误报缺字体。
        """
        if self._db is None or self._index_rebuilding:
            return False
        lib_dir = self.get_resource_or_config("lib_dir") or ""
        if not lib_dir or not Path(lib_dir).is_dir():
            return False
        resolved_lib = str(Path(lib_dir).resolve())
        try:
            summary = self._db.index_stats()
        except Exception:
            summary = {"faces": 0}
        indexed_lib = str(self._db.index_get("lib_dir", "") or "")
        if not force and summary.get("faces") and indexed_lib == resolved_lib:
            return True
        now = time.time()
        if not force and (now - self._index_last_build_ts) < 300 and summary.get("faces"):
            return True
        if not self._index_build_lock.acquire(blocking=False):
            # 另一个线程正在重建：本轮不要用抢锁前读到的旧状态给出结论
            return False
        try:
            # 抢到锁后重新读：避免把重建前的空/旧 summary 当成当前状态
            try:
                summary2 = self._db.index_stats()
            except Exception:
                summary2 = {"faces": 0}
            indexed_lib2 = str(self._db.index_get("lib_dir", "") or "")
            if not force and summary2.get("faces") and indexed_lib2 == resolved_lib:
                return True
            if force or (time.time() - self._index_last_build_ts) >= 1.0:
                result = self._rebuild_font_index()
                if result.get("ok"):
                    self._db.add_log(
                        f"字体索引已重建：扫描 {result['scanned']}、更新 {result['indexed']}、"
                        f"未变 {result['unchanged']}、清理 {result['removed']}",
                        "info",
                    )
                elif result.get("error"):
                    self._db.add_log(f"字体索引重建失败：{result['error']}", "warning")
            try:
                return bool(self._db.index_stats().get("faces"))
            except Exception:
                return False
        finally:
            self._index_build_lock.release()

    def _startup_light_check(self) -> None:
        """启动轻检包装：持索引构建锁，避免与全量重建/其他轻检并发互删索引行。"""
        with self._index_build_lock:
            self._startup_light_check_impl()

    def _startup_light_check_impl(self) -> None:
        """启动轻检（后台线程）：stat 比对磁盘与索引，不做全量解析。

        - 索引为空（新装/换库/升级后重建）→ 从磁盘重建字体库；
        - 已索引文件磁盘不存在 → 撤销其索引贡献；
        - size/mtime 变化 → 只重解析这几个文件；
        - 磁盘上存在但索引里没有的新字体（watchdog 漏事件/外部直接放入/迁移丢记录）
          → 一并增量补索引：轻检不能只看数据库记录，否则永远发现不了「未入索引的新文件」；
        - 未变化文件零解析开销，万级字体库也不拖慢启动。
        """
        if self._db is None:
            return
        try:
            lib_dir = self.get_resource_or_config("lib_dir") or ""
            if not lib_dir or not Path(lib_dir).is_dir():
                return
            root = Path(lib_dir)
            rows = self._db.query("SELECT path, size, mtime_ns FROM font_files")
            if not rows:
                stats = self._rebuild_font_index()
                if stats.get("ok"):
                    self._db.add_log(
                        f"启动轻检：索引为空，已从磁盘重建字体库"
                        f"（更新 {stats.get('indexed', 0)}、清理 {stats.get('removed', 0)}）",
                        "info",
                    )
                elif stats.get("error"):
                    self._db.add_log(f"启动轻检：字体库重建失败（{stats['error']}）", "warning")
                return
            missing = changed = 0
            indexed_paths: set = set()
            for row in rows:
                if self._stopping:
                    return
                path_text = str(row.get("path") or "")
                if not path_text:
                    continue
                indexed_paths.add(path_text)
                try:
                    p = Path(path_text)
                    if not p.is_file():
                        if self._remove_font_from_index(path_text):
                            missing += 1
                        continue
                    st = p.stat()
                    if (
                        int(row.get("size") or 0) == st.st_size
                        and int(row.get("mtime_ns") or 0) == st.st_mtime_ns
                    ):
                        continue
                    if self._index_font_path(p):
                        changed += 1
                except Exception:
                    continue
            # 磁盘清单对比：补发现「磁盘存在、索引没有」的新字体（轻量 stat，不解析全部）
            discovered = 0
            try:
                for item in root.rglob("*"):
                    if self._stopping:
                        break
                    if not item.is_file() or not is_font_file(item.name):
                        continue
                    if self._is_system_hidden_path(item):
                        continue
                    try:
                        resolved_key = str(item.resolve())
                    except Exception:
                        continue
                    if resolved_key in indexed_paths:
                        continue
                    if self._index_font_path(item):
                        discovered += 1
                        indexed_paths.add(resolved_key)
            except Exception as err:
                self._db.add_log(f"启动轻检：磁盘清单对比失败（{err}）", "warning")
            if missing or changed or discovered:
                self._invalidate_missing_agg()
                self._db.add_log(
                    f"启动轻检完成：撤销失效 {missing} 个、增量更新 {changed} 个、"
                    f"新发现补索引 {discovered} 个（共 {len(rows)} 个已索引文件）",
                    "info" if not missing else "warning",
                )
        except Exception as err:
            try:
                if self._db is not None:
                    self._db.add_log(f"启动轻检失败: {err}", "warning")
            except Exception:
                pass

    def _schedule_startup_light_check(self) -> None:
        """按配置在后台线程执行启动轻检（不阻塞插件初始化）。"""
        if not bool(self.get_resource_or_config("startup_light_check")):
            return
        if not self._enabled or self._db is None:
            return
        t = threading.Thread(target=self._startup_light_check, name="zt-light-check", daemon=True)
        t.start()

    def _weekly_reconcile_task(self) -> None:
        """每周差异核对（cron）：size+mtime 指纹比对磁盘与索引，只重解析差异文件。

        stat 指纹相同不代表内容相同（复制工具/NAS/恢复备份可能保留 mtime），
        因此每周额外抽检 _WEEKLY_HASH_SAMPLE 个「未变」文件重算 SHA-256：
        抽检不一致 → 视为已变更，重解析并刷新索引贡献。
        """
        if not self._enabled or self._db is None:
            return
        if not bool(self.get_resource_or_config("weekly_reconcile")):
            return
        result = self._rebuild_font_index(hash_sample=self._WEEKLY_HASH_SAMPLE)
        if not result.get("ok"):
            self._db.add_log(f"每周差异核对失败：{result.get('error') or '未知错误'}", "warning")
            return
        self._db.add_log(
            f"每周差异核对完成：扫描 {result.get('scanned', 0)}、更新 {result.get('indexed', 0)}、"
            f"未变 {result.get('unchanged', 0)}、清理 {result.get('removed', 0)}、"
            f"哈希抽检 {result.get('hash_checked', 0)}（命中内容替换 {result.get('hash_mismatch', 0)}）",
            "info",
        )
        if int(result.get("indexed") or 0) or int(result.get("removed") or 0):
            self._recheck_missing_after_library_change("每周差异核对")

    def _glyph_check(self, raw: bytes) -> Optional[Any]:
        """字形级检测：ASS 用到的每个字体名 → 索引 face → 逐字符缺失。索引不可用返回 None。"""
        if self._db is None or not self._ensure_font_index():
            return None
        try:
            usage, warnings = parse_ass_usage(raw)
        except Exception as err:
            self._db.add_log(f"ASS 字形解析失败: {err}", "warning")
            return None
        if not usage:
            return None

        def _lookup(name: str) -> List[FaceCoverage]:
            rows = self._db.lookup_faces(name) or []
            return [
                FaceCoverage(
                    face_id=int(row.get("face_id") or 0),
                    file_path=str(row.get("file_path") or ""),
                    face_index=int(row.get("face_index") or 0),
                    names=list(row.get("names") or []),
                    codepoints=set(row.get("codepoints") or set()),
                )
                for row in rows
            ]

        result = evaluate_usage(usage.values(), _lookup)
        for warning in warnings:
            try:
                self._db.add_log(f"ASS 解析提示: {warning}", "info")
            except Exception:
                pass
        return result

    def _lookup_face_refs(self, name: str) -> List[FaceRef]:
        """子集化用：字体名 → FaceRef（过滤已不存在的文件）。"""
        if self._db is None:
            return []
        refs: List[FaceRef] = []
        for row in self._db.lookup_faces(name) or []:
            path = str(row.get("file_path") or "")
            if not path or not Path(path).is_file():
                continue
            refs.append(
                FaceRef(
                    file_path=path,
                    face_index=int(row.get("face_index") or 0),
                    codepoints=set(row.get("codepoints") or set()),
                    names=list(row.get("names") or []),
                )
            )
        return refs

    def _hb_status(self) -> Tuple[bool, str]:
        if self._hb_probe is None:
            self._hb_probe = hb_available()
        return self._hb_probe

    def _snapshot_remaining(
        self, row: Dict[str, Any], coverage_cache: Optional[Dict[str, set]] = None
    ) -> Tuple[set, set, str]:
        """字形快照行 → (全部缺失码点, 仍缺码点, 仍缺字符)。

        按「当前字体库」该字体名（含别名/TTC 各 face）的字符覆盖实时扣除：
        从字体库上传/归档补齐字体后，已覆盖的缺失字符自动消失，无需重新检查字幕。
        """
        raw_cps = row.get("missing_codepoints")
        try:
            if isinstance(raw_cps, (list, tuple, set)):
                cps = {int(v) for v in raw_cps}  # latest_missing_glyphs 已解析成列表
            else:
                cps = {int(v) for v in json.loads(raw_cps or "[]")}
        except Exception:
            cps = set()
        name = str(row.get("font_name") or "")
        key = normalize_font_key(name)
        if coverage_cache is not None and key in coverage_cache:
            covered = coverage_cache[key]
        else:
            covered = set()
            try:
                if self._db is not None:
                    for face in self._db.lookup_faces(name) or []:
                        covered |= set(face.get("codepoints") or set())
            except Exception:
                pass
            if coverage_cache is not None:
                coverage_cache[key] = covered
        remain = cps - covered
        chars = "".join(chr(cp) for cp in sorted(remain) if 0 < cp <= 0x10FFFF)
        return cps, remain, chars

    def _lib_font_keys(self) -> Tuple[set, str]:
        """检查侧「字体库有哪些字体」统一口径：返回 (归一化键集, 匹配来源)。

        优先级：fontTools 增量索引 font_aliases（权威，含 family/全名/PS/排版名别名）
        → 字体库记录 family（"db"，索引不可用时的兜底）。
        """
        if self._db is None:
            return set(), "db"
        try:
            # fontTools 增量索引（权威口径）：font_aliases 已是归一化键
            if self._ensure_font_index():
                rows = self._db.query("SELECT alias FROM font_aliases")
                keys = {str(r.get("alias") or "") for r in rows}
                keys.discard("")
                if keys:
                    return keys, "index"
        except Exception:
            pass
        try:
            fams = {normalize_font_key(x) for x in self._db.all_font_families()}
        except Exception:
            fams = set()
        return fams, "db"

    def _schedule_index_rebuild(self, delay: float = 5.0) -> None:
        """自动归档后延迟聚合重建索引：一次拖入多个字体时 5 秒窗口内合并为一次重建，
        避免逐文件重建拖慢监控；同时跳过已重建的重复调度。"""
        try:
            if self._stopping or not self._enabled or not self._index_dirty:
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
                    self._db.add_log("字体索引已自动重建（自动归档后）", "info")
                    # 自动归档补齐字体后，立即重检受影响字幕（字体已在索引里，重建不会重复计入新增）
                    self._recheck_missing_after_library_change("自动归档")
                else:
                    self._db.add_log(f"字体索引自动重建失败: {msg}", "warning")
            finally:
                self._scan_lock.release()
        except Exception as err:
            try:
                if self._db is not None:
                    self._db.add_log(f"字体索引自动重建异常: {err}", "warning")
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

    def _sync_subset_output(self, out: Path, show: str = "") -> Tuple[Optional[Path], str]:
        """子集化成品同步到「子集化输出目录」（subset_out_dir）。

        未配置输出目录 → 返回 (None, "")（保持原目录产物，不影响调用方）；
        配置了 → 按 subset_out_mode 复制(copy)/移动(move) 成品 ass 到输出目录，
        show（剧名）非空时输出到 输出目录/<剧名>/ 子文件夹（监控来源按剧分类，多剧不混在一起），
        返回 (同步后成品路径, 说明)。失败/无需同步时返回 (None, 说明)。

        字体已内嵌进 .ziti.ass，不再产生 *_subsetted 字体夹，因此这里只同步字幕成品。
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
            # 子集字体已内嵌进 .ziti.ass，不再随成品同步字体夹（旧版 *_subsetted 仅备份，已移除）
            if self._db is not None:
                self._db.add_log(f"子集化成品{'移动' if mode == 'move' else '已输出'}: {dst}", "info")
            return dst, f"输出目录：{dst}"
        except Exception as err:
            if self._db is not None:
                self._db.add_log(f"子集化成品同步输出目录失败: {err}", "warning")
            return None, f"同步失败: {err}"

    # 子集化工作进程超时：60 秒基础 + 每字体 10 秒，上限 300 秒
    _SUBSET_WORKER_TIMEOUT_BASE = 60.0
    _SUBSET_WORKER_TIMEOUT_PER_FONT = 10.0
    _SUBSET_WORKER_TIMEOUT_MAX = 300.0
    # 每周差异核对时对「stat 未变」文件额外做哈希抽检的条数（发现同大小同时间戳的内容替换）
    _WEEKLY_HASH_SAMPLE = 50

    def _subset_with_hb(self, src: Path, out_path: Path) -> Dict[str, Any]:
        """用 HarfBuzz 引擎子集化一份字幕，返回与其他子集化引擎同构的字典。

        任一字体完全缺失 → status=missing（不产出半成品）；仅部分字符未覆盖 →
        success + warning（已覆盖字符正常内嵌）。默认在独立工作进程中执行，
        uharfbuzz 段错误/病态字体只影响当前字幕；隔离开启时工作进程无法启动直接
        报错（不允许回退主进程执行），只有显式关闭隔离开关才走进程内模式
        （两条路径共用 subset_ass_with_plan，结果口径一致）。
        """
        try:
            raw = src.read_bytes()
            usage, _warnings = parse_ass_usage(raw)
            usage_map = {item.name: set(item.codepoints) for item in usage.values()}
            # 预检整字体缺失：引擎在"部分字体缺失"时仍会写出只含其余字体的半成品，
            # 直接调用会覆盖上一版可用成品。这里先按 @合并口径解析字体，
            # 只要任一字体完全无法覆盖 → 不调用引擎，旧成品保持不动。
            merged: Dict[str, set] = {}
            for raw_name, chars in usage_map.items():
                name = raw_name[1:] if raw_name.startswith("@") else raw_name
                merged.setdefault(name, set()).update(chars)
            missing_pre: List[str] = []
            plan: List[Dict[str, Any]] = []
            plan_warnings: List[str] = []
            for name, chars in merged.items():
                if not chars:
                    continue
                try:
                    refs = self._lookup_face_refs(name) or []
                except Exception:
                    refs = []
                ref = hb_choose_face(refs, chars) if refs else None
                covered = (chars & set(ref.codepoints)) if ref is not None else set()
                if not covered:
                    missing_pre.append(name)
                    continue
                if len(covered) < len(chars):
                    plan_warnings.append(
                        f"字体「{name}」只覆盖 {len(covered)}/{len(chars)} 个字符，缺失字符沿用播放器回退"
                    )
                plan.append(
                    {
                        "font_name": name,
                        "file_path": ref.file_path,
                        "face_index": ref.face_index,
                        "codepoints": sorted(covered),
                    }
                )
            if missing_pre:
                return {
                    "status": "missing",
                    "out": "",
                    "reason": "缺字体: " + "、".join(missing_pre),
                    "missing_fonts": missing_pre,
                }
            result: Optional[SubsetResult] = None
            if self.get_resource_or_config("subset_process_isolation"):
                result = self._subset_via_worker(src, out_path, plan, plan_warnings)
                if result is None:
                    # P2-15：隔离开启时禁止回退主进程执行——最需要隔离的正是
                    # worker 起不来的环境（依赖/路径问题），此时回到主进程跑
                    # uharfbuzz 等于把段错误风险重新引回 MoviePilot 宿主。
                    return {
                        "status": "error",
                        "out": "",
                        "reason": "子集化进程隔离已开启，但工作进程无法启动"
                        "（请检查插件目录下的 subset_worker.py 与 Python 解释器/uharfbuzz 依赖）；"
                        "已拒绝在主进程内执行。如需进程内模式请在设置中关闭「子集化进程隔离」",
                        "missing_fonts": [],
                    }
            else:
                # 用户显式关闭隔离：进程内执行（与旧版本行为一致）
                result = hb_subset_ass_file(src, out_path, usage_map, self._lookup_face_refs)
        except Exception as err:
            return {"status": "error", "out": "", "reason": f"HarfBuzz 子集化异常: {err}", "missing_fonts": []}
        if result.missing_fonts:
            # 缺字体时引擎在写盘前就返回，本轮没有产出任何文件；
            # 不要删 out_path —— 那可能是上一轮成功生成、播放器正在用的成品。
            return {
                "status": "missing",
                "out": "",
                "reason": "缺字体: " + "、".join(result.missing_fonts),
                "missing_fonts": list(result.missing_fonts),
            }
        if not result.success:
            return {
                "status": "error",
                "out": "",
                "reason": "；".join(result.errors)[:300] or "子集化失败",
                "missing_fonts": [],
            }
        notes = list(result.warnings)
        if self._db is not None and result.embedded:
            try:
                self._db.add_log(
                    f"HarfBuzz 子集化: {src.name} 内嵌 {len(result.embedded)} 个字体、"
                    f"{sum(item.encoded_size for item in result.embedded)} 字节",
                    "info",
                )
            except Exception:
                pass
        return {
            "status": "success",
            "out": result.out_path,
            "reason": "；".join(notes),
            "missing_fonts": [],
        }

    def _subset_via_worker(
        self,
        src: Path,
        out_path: Path,
        plan: List[Dict[str, Any]],
        warnings: Optional[List[str]] = None,
    ) -> Optional[SubsetResult]:
        """在常驻工作进程中执行子集化。

        返回 None 表示工作进程无法启动（脚本缺失/解释器不可用），调用方回退进程内；
        崩溃、超时、协议异常返回带 errors 的 SubsetResult（已隔离，不影响宿主进程）。
        进程崩溃/超时后客户端会杀掉当前进程，下一次请求自动重启。
        """
        client = self._get_subset_worker()
        if client is None:
            return None
        payload = {
            "v": 1,
            "task": "subset_ass",
            "ass_path": str(src),
            "out_path": str(out_path),
            "plan": plan,
            "warnings": list(warnings or []),
        }
        timeout = min(
            self._SUBSET_WORKER_TIMEOUT_MAX,
            self._SUBSET_WORKER_TIMEOUT_BASE
            + self._SUBSET_WORKER_TIMEOUT_PER_FONT * max(1, len(plan)),
        )
        started = time.time()
        try:
            data = client.request(payload, timeout=timeout)
        except SubsetWorkerTimeout:
            self._cleanup_subset_temp(out_path, since=started)
            return SubsetResult(
                errors=[f"子集化超时（{int(timeout)} 秒），工作进程已终止（已隔离）"]
            )
        except SubsetWorkerStartError as err:
            # 启动失败：交给调用方回退进程内，避免插件功能不可用
            _logger.warning("子集化工作进程启动失败，回退进程内执行: %s", err)
            return None
        except SubsetWorkerCrashed as err:
            self._cleanup_subset_temp(out_path, since=started)
            return SubsetResult(errors=[f"子集化引擎崩溃（{err}，已隔离）"])
        except Exception as err:
            self._cleanup_subset_temp(out_path, since=started)
            return SubsetResult(errors=[f"子集化引擎异常（{err}，已隔离）"])
        result = self._subset_result_from_worker(data)
        if not result.warnings and warnings:
            result.warnings = list(warnings)
        if result.success and (not result.out_path or not Path(result.out_path).is_file()):
            result.success = False
            result.errors.append("工作进程报告成功，但产物文件不存在")
        return result

    def _get_subset_worker(self) -> Optional[SubsetWorkerClient]:
        """懒启动常驻工作进程；脚本缺失返回 None（调用方回退进程内执行）。"""
        worker = Path(__file__).resolve().parent / "subset_worker.py"
        if not worker.is_file():
            _logger.warning("子集化工作进程不存在，回退进程内执行: %s", worker)
            return None
        client = self._subset_worker
        if client is None:
            client = SubsetWorkerClient(worker)
            self._subset_worker = client
        return client

    def _close_subset_worker(self) -> None:
        """关闭常驻工作进程（停插件/重载配置/进程退出前）：立即中止，不等在途请求。"""
        client = self._subset_worker
        self._subset_worker = None
        if client is not None:
            try:
                client.abort()
            except Exception:
                pass

    @staticmethod
    def _subset_result_from_worker(data: Dict[str, Any]) -> SubsetResult:
        """工作进程 JSON → SubsetResult（字段缺失时按失败/空值处理）。"""
        result = SubsetResult()
        result.success = bool(data.get("success"))
        result.out_path = str(data.get("out_path") or "")
        result.missing_fonts = [str(item) for item in (data.get("missing_fonts") or [])]
        result.errors = [str(item) for item in (data.get("errors") or [])]
        result.warnings = [str(item) for item in (data.get("warnings") or [])]
        for item in data.get("embedded") or []:
            if not isinstance(item, dict):
                continue
            try:
                result.embedded.append(
                    SubsetEmbed(
                        font_name=str(item.get("font_name") or ""),
                        file_path=str(item.get("file_path") or ""),
                        face_index=int(item.get("face_index") or 0),
                        required=int(item.get("required") or 0),
                        encoded_size=int(item.get("encoded_size") or 0),
                    )
                )
            except Exception:
                continue
        return result

    @staticmethod
    def _cleanup_subset_temp(out_path: Path, since: float = 0.0) -> None:
        """清理被杀工作进程留下的临时文件（引擎用 .<out.name>.xxxx.tmp 落盘）。"""
        try:
            parent = Path(out_path).parent
            if not parent.is_dir():
                return
            prefix = f".{Path(out_path).name}."
            for item in parent.iterdir():
                try:
                    # 只认引擎本轮的临时命名，避免误删同目录其他文件
                    if not item.name.startswith(prefix) or not item.name.endswith(".tmp"):
                        continue
                    if item.is_file() and item.stat().st_mtime >= since - 1:
                        item.unlink(missing_ok=True)
                except Exception:
                    continue
        except Exception:
            pass

    def _subset_source_kind(self, f: Path, source: str) -> str:
        """判定字幕的子集化来源身份：manual（上传临时目录）/ watch（字幕监控目录）/ inbound（媒体库）。

        retry 无独立身份，按源字幕实际所在区域继承；判定失败按 inbound 处理。
        """
        if source != "retry":
            return source
        try:
            if self._tmp_dir and _path_within(f, Path(self._tmp_dir)):
                return "manual"
            if any(
                w and _path_within(f, Path(w))
                for w in (
                    str(self.get_resource_or_config("ass_dir") or ""),
                    str(self.get_resource_or_config("subset_dir") or ""),
                )
            ):
                return "watch"
        except Exception:
            pass
        return "inbound"

    def _run_subset_batch(self, files: List[Path], source: str = "manual") -> Dict[str, Any]:
        """对一批 ass 字幕执行子集化：跳过已子集化/缺字体的记录原因，写 subset_records。

        调用方需已持有 _scan_lock（入库自动与页面全量互斥）。
        """
        stats: Dict[str, Any] = {"success": 0, "skipped": 0, "missing": 0, "error": 0, "missing_fonts": [], "file_status": {}, "out_files": []}
        if not files:
            return stats
        if self._db is None:
            return stats
        # 引擎：内置 HarfBuzz（fontTools 增量索引 + uharfbuzz 子集化）
        hb_ok, hb_info = self._hb_status()
        if not hb_ok:
            self._db.add_log(f"子集化未执行：{hb_info}", "warning")
            return stats
        if not self._ensure_font_index():
            self._db.add_log("子集化未执行：字体索引不可用（请确认字体库目录已配置并完成重建）", "warning")
            return stats
        inbound_overwrite = bool(self.get_resource_or_config("inbound_subset_overwrite"))
        out_dir_cfg = str(self.get_resource_or_config("subset_out_dir") or "")
        # 「监控目录输出方式」是目录监控唯一的成品/源字幕去向开关：
        #   copy = 成品进输出目录、源字幕保留（未配输出目录：另生成 xx.ziti.ass 并保留源）
        #   move = 成品进输出目录、成功后删除源字幕（未配输出目录：成品就地替换源字幕）
        watch_move = str(self.get_resource_or_config("subset_out_mode") or "copy") == "move"
        for f in files:
            try:
                # 优雅停止：停插件时当前条子集化处理完（含写结果记录）就不再继续
                if self._stopping:
                    break
                f = Path(f)
                if not f.is_file() or not is_ass_file(f.name):
                    continue
                src_kind = self._subset_source_kind(f, source)
                # 监控目录：move=删源（有输出目录时）/就地替换（无输出目录）；copy=保留源
                # 上传临时目录（manual）与其他来源：永远不覆盖源文件
                overwrite = False
                if src_kind == "inbound":
                    # 媒体库（inbound）：独立开关控制，默认 off 保留原字幕
                    overwrite = inbound_overwrite
                elif src_kind == "watch":
                    overwrite = watch_move
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
                                "source": src_kind,
                            }
                        )
                        stats["skipped"] += 1
                        continue
                except Exception:
                    pass
                hb_out = hb_output_path(f)
                res = self._subset_with_hb(f, hb_out)
                # 失败/缺字体时不要删除 hb_out：引擎只在成功后原子替换目标，
                # 失败时本轮没有写文件，路径上的内容是上一轮可用成品，必须保留。
                status = res.get("status", "error")
                if status == "success":
                    out = Path(res.get("out") or "")
                    # 成品输出名：以「原始字幕名」为准（去掉上传临时目录的 uuid 前缀），
                    # 后缀固定 .ziti.ass；未配输出目录且为 move 时直接替换原字幕
                    orig = self._original_subset_name(f)
                    base = orig[:-4] if orig.lower().endswith(".ass") else orig
                    # 配了输出目录的目录监控：成品统一先落成 .ziti.ass 再同步到输出目录，
                    # 不再就地改写监控目录的源字幕（成品去向由「监控目录输出方式」决定）。
                    watch_with_out = src_kind == "watch" and bool(out_dir_cfg)
                    if overwrite and not watch_with_out:
                        # 覆盖模式：子集化结果直接替换原字幕文件（原名不变）。
                        # 上传临时缓存文件名带 subset_<uuid>_ 前缀，同名覆盖会让成品带前缀，
                        # 这里先把成品落到「原始名」路径，再清理带前缀的临时缓存副本
                        try:
                            if f.name != orig:
                                target_f = Path(f.parent) / orig
                                if target_f.exists():
                                    target_f.unlink(missing_ok=True)
                                out.replace(target_f)
                                final_out = target_f
                                f.unlink(missing_ok=True)
                            else:
                                out.replace(f)
                                final_out = f
                        except Exception:
                            final_out = out
                    else:
                        final_out = out
                        try:
                            # 成品固定后缀 .ziti.ass（原字幕保留不动）
                            target = Path(f.parent) / f"{base}.ziti.ass"
                            if str(target.resolve()).lower() != str(out.resolve()).lower():
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
                    # 后端同时判断开关：只配档位（配置/API 直写）不应绕过 UI 的关闭语义
                    if (
                        final_out.is_file()
                        and self.get_resource_or_config("hdr_brightness")
                        and hdr_level
                    ):
                        hdr_msg = apply_hdr_brightness(final_out, str(hdr_level)) or ""
                        if hdr_msg:
                            self._db.add_log(f"HDR 亮度应用: {final_out.name}（{hdr_msg}）", "info")
                    # ── 成品落位判定（来源身份，循环开头已算好 src_kind）：
                    #   inbound（MP入库）：成品只落媒体库，不同步输出目录
                    #   watch（目录监控）：成品按「监控目录输出方式」同步到输出目录并按剧名分子文件夹
                    #   manual（手动上传）：成品只留上传临时目录，不同步输出目录
                    if src_kind != "watch":
                        synced, sync_msg = "", ""
                    else:
                        synced, sync_msg = self._sync_subset_output(
                            final_out, self._extract_show_name(str(final_out))
                        )
                        # 成品已进输出目录：监控目录不再留 .ziti.ass 副本，
                        # 否则 copy 模式下会同时出现「源字幕 + 成品副本」两份，也容易被下一轮扫描重复收录
                        if synced:
                            try:
                                if Path(final_out).resolve() != Path(synced).resolve():
                                    Path(final_out).unlink(missing_ok=True)
                            except Exception as err:
                                sync_msg = f"{sync_msg}；监控目录成品清理失败: {err}"
                        # move 模式：成品落地输出目录后删除源字幕（copy 模式保留源字幕）
                        if synced and overwrite and watch_with_out:
                            try:
                                if Path(f).resolve() != Path(final_out).resolve():
                                    Path(f).unlink(missing_ok=True)
                                    sync_msg = f"{sync_msg}；已删除源字幕"
                            except Exception as err:
                                sync_msg = f"{sync_msg}；源字幕删除失败: {err}"
                    record_out = str(synced) if synced else (str(final_out) if final_out.is_file() else "")
                    self._db.add_subset_record(
                        {
                            "file_name": orig,
                            "file_path": str(f),
                            "status": "success",
                            "reason": "；".join(
                                [m for m in (sync_msg, hdr_msg, str(res.get("reason") or "")) if m]
                            ) or "",
                            "out_file": record_out,
                            "source": src_kind,
                        }
                    )
                    stats["success"] += 1
                    # 记录成功成品路径：清理待处理临时源文件时排除它（覆盖模式成品替换了源文件，误删会丢下载结果）
                    try:
                        if record_out:
                            stats["out_files"].append(str(Path(record_out).resolve()))
                    except Exception:
                        pass
                    self._db.add_log(f"子集化成功: {f.name} → {Path(record_out or final_out).name}", "info")
                elif status == "missing":
                    reason = str(res.get("reason") or "")
                    # 结构化缺失清单（引擎输出解析所得），不再对 reason 字符串做往返拆分
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
                            "source": src_kind,
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
                            "source": src_kind,
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
                            "source": src_kind if 'src_kind' in locals() else "",
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
                    + "（可先上传缺失字体入库后重试）"
                )
            if stats["error"]:
                lines.append(f"⚠ 失败 {stats['error']} 个（见子集化记录）")
            if lines:
                self._notify(title, "\n".join(lines))
        except Exception:
            pass

    def _run_show_subset(self, files: List[Path], show: str = "", source: str = "inbound") -> None:
        """后台自动子集化（入库监控共用，后台线程）：与页面全量互斥，引擎/索引不可用时仅写日志。

        source 决定成品落位身份：
        - inbound（MP 入库）→ 成品只落媒体库，不同步输出目录；
        - watch（目录监控）→ 按「监控目录输出方式」同步到输出目录并按剧名分子文件夹。
        """
        if self._db is None:
            return
        ready, why = self._subset_engine_ready()
        if not ready:
            self._db.add_log(f"自动子集化跳过：{why}（设置 → 子集化）", "warning")
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

    # ─── 种子字体收集（只读下载器，按种子文件清单截取，不扫目录）────────────
    def _torrent_enabled(self) -> bool:
        """总开关：插件启用 + 种子收集开关。"""
        try:
            return bool(self._enabled) and bool(self.get_resource_or_config("torrent_enabled"))
        except Exception:
            return False

    def _torrent_baseline_ts(self) -> int:
        try:
            if self._db is None:
                return 0
            return int(self._db.get_setting("torrent_baseline_ts", 0) or 0)
        except Exception:
            return 0

    def _torrent_set_baseline(self, ts: int = 0) -> int:
        ts = int(ts or time.time())
        try:
            if self._db is not None:
                self._db.set_setting("torrent_baseline_ts", ts)
        except Exception:
            pass
        return ts

    def _torrent_ensure_baseline(self) -> int:
        """取基线；没有就写入当前时间（只处理基线之后完成的种子，历史不碰）。"""
        ts = self._torrent_baseline_ts()
        if ts <= 0:
            ts = self._torrent_set_baseline(int(time.time()))
        return ts

    def _torrent_cfg_int(self, key: str, default: int) -> int:
        """读取数值型种子收集配置：0 是合法值，不能被 `or default` 吞掉。"""
        try:
            raw = self.get_resource_or_config(key)
        except Exception:
            raw = None
        if raw is None or raw == "":
            return int(default)
        try:
            return int(raw)
        except Exception:
            return int(default)

    def _torrent_plan(self, torrent_hash: str, downloader: str) -> Tuple[bool, str, Dict[str, Any]]:
        """只读探测：拿种子文件清单并挑出字体候选（不复制、不改下载器）。"""
        if not torrent_hash:
            return False, "缺少种子 hash", {}
        service = tq.get_downloader_service(downloader)
        instance = tq.service_instance(service)
        if instance is None:
            return False, f"下载器不可用：{downloader or '（未指定）'}", {}
        meta = tq.torrent_meta(instance, torrent_hash)
        root = tq.map_download_path(str(meta.get("save_path") or ""), service, downloader)
        if not root:
            return False, "下载器未返回保存路径（save_path 为空）", {}
        if not Path(root).is_dir():
            return False, f"下载路径在插件侧不可访问：{root}（请检查下载器路径映射）", {}
        files = tq.list_files(instance, torrent_hash)
        if not files:
            return False, "读取种子文件清单失败或种子已被删除", {}
        keywords = str(self.get_resource_or_config("torrent_keywords") or "font,fonts,字体")
        max_mb = self._torrent_cfg_int("torrent_max_file_mb", 2048)
        max_files = self._torrent_cfg_int("torrent_max_files", 500)
        candidates, stats = tq.pick_candidates(files, root, keywords, max_mb, max_files)
        alive: List[Dict[str, Any]] = []
        for item in candidates:
            try:
                if Path(item.get("abs_path") or "").is_file():
                    alive.append(item)
            except Exception:
                continue
        stats["missing_files"] = len(candidates) - len(alive)
        return True, "", {
            "hash": torrent_hash,
            "name": str(meta.get("name") or ""),
            "root": root,
            "candidates": alive,
            "stats": stats,
        }

    def _ensure_torrent_collect(
        self,
        torrent_hash: str,
        downloader: str,
        source: str = "inbound",
        wait: bool = False,
    ) -> Dict[str, Any]:
        """确保该种子的字体收集已入队/完成；wait=True 时最多等 torrent_wait_sec 秒。

        返回 {state, added, skipped, failed, picked, name, reason}：
          state: skipped（未开启/无 hash）/ cached（已收集过）/ queued|running（不等待时）
                 / done|empty|failed / timeout
        """
        empty = {
            "state": "skipped", "added": 0, "pending": 0, "skipped": 0,
            "failed": 0, "picked": 0, "name": "", "reason": "",
        }
        if not self._torrent_enabled() or not torrent_hash:
            return empty
        job: Optional[Dict[str, Any]] = None
        with self._torrent_jobs_lock:
            job = self._torrent_jobs.get(torrent_hash)
            if job is None:
                # 幂等：该 hash 已成功收集过（含「种子内无字体」）就不再重复截取
                try:
                    done = self._db.get_torrent_ingest_by_hash(torrent_hash) if self._db else None
                except Exception:
                    done = None
                if done is not None:
                    return {
                        "state": "cached",
                        "added": int(done.get("added") or 0),
                        "pending": 0,
                        "skipped": int(done.get("skipped") or 0),
                        "failed": int(done.get("failed") or 0),
                        "picked": int(done.get("picked") or 0),
                        "name": str(done.get("torrent_name") or ""),
                        "reason": "",
                    }
                job = {"event": threading.Event(), "state": "queued", "stats": {}}
                self._torrent_jobs[torrent_hash] = job
                try:
                    threading.Thread(
                        target=self._torrent_job_run,
                        args=(torrent_hash, downloader, source),
                        name="zt-torrent",
                        daemon=True,
                    ).start()
                except Exception as err:
                    job["state"] = "failed"
                    job["stats"] = {"reason": f"线程启动失败: {err}"}
                    job["event"].set()
        if not wait:
            return {**empty, "state": str(job.get("state") or "queued")}
        timeout = max(0, self._torrent_cfg_int("torrent_wait_sec", 300))
        finished = job["event"].wait(timeout)
        stats = dict(job.get("stats") or {})
        if not finished:
            return {
                "state": "timeout",
                "added": int(stats.get("added") or 0),
                "pending": int(stats.get("pending") or 0),
                "skipped": int(stats.get("skipped") or 0),
                "failed": int(stats.get("failed") or 0),
                "picked": int(stats.get("picked") or 0),
                "name": str(stats.get("name") or ""),
                "reason": f"等待 {timeout} 秒超时",
            }
        return {
            "state": str(job.get("state") or "done"),
            "added": int(stats.get("added") or 0),
            "pending": int(stats.get("pending") or 0),
            "skipped": int(stats.get("skipped") or 0),
            "failed": int(stats.get("failed") or 0),
            "picked": int(stats.get("picked") or 0),
            "name": str(stats.get("name") or ""),
            "reason": str(stats.get("reason") or ""),
        }

    def _torrent_job_run(self, torrent_hash: str, downloader: str, source: str) -> None:
        """执行一次种子字体截取：暂存复制 → 解压 → 归档入库 → 重建索引 → 写记录。"""
        job = self._torrent_jobs.get(torrent_hash) or {}
        stats: Dict[str, Any] = {
            "picked": 0, "added": 0, "pending": 0, "skipped": 0, "failed": 0, "name": ""
        }
        staging: Optional[Path] = None
        record_id = 0
        state = "failed"
        detail = ""
        try:
            with self._torrent_sem:
                if self._stopping:
                    state = "failed"
                    stats["reason"] = "插件正在停止"
                    return
                job["state"] = "running"
                ok, err, plan = self._torrent_plan(torrent_hash, downloader)
                plan_stats = (plan or {}).get("stats") or {}
                stats["name"] = str((plan or {}).get("name") or "")
                if not ok:
                    stats["reason"] = err
                    detail = err
                    self._db.add_log(f"种子字体收集跳过：{err}", "warning")
                    record_id = self._db.add_torrent_ingest(
                        torrent_hash, downloader, "", source, "failed", 0, 0, 0, 1, err
                    )
                    return
                candidates = plan.get("candidates") or []
                stats["picked"] = len(candidates)
                if not candidates:
                    state = "empty"
                    detail = (
                        f"扫描 {plan_stats.get('scanned', 0)} 个文件，无已下载的字体/字体包"
                        + (f"（{plan_stats.get('pending', 0)} 个未下完）" if plan_stats.get("pending") else "")
                    )
                    self._db.add_log(f"种子字体收集：{stats['name'] or torrent_hash[:8]} {detail}", "info")
                    record_id = self._db.add_torrent_ingest(
                        torrent_hash, downloader, stats["name"], source, "empty", 0, 0, 0, 0, detail
                    )
                    return
                if not self._tmp_dir:
                    stats["reason"] = "临时目录未初始化"
                    detail = stats["reason"]
                    return
                staging = Path(self._tmp_dir) / f"torrent_{torrent_hash[:12]}_{uuid.uuid4().hex[:6]}"
                raw_dir = staging / "raw"
                extract_dir = staging / "extract"
                raw_dir.mkdir(parents=True, exist_ok=True)
                extract_dir.mkdir(parents=True, exist_ok=True)
                max_mb = self._torrent_cfg_int("torrent_max_file_mb", 2048)
                max_files = self._torrent_cfg_int("torrent_max_files", 500)
                skipped_notes: List[str] = []
                empty_archives = 0
                for item in candidates:
                    if self._stopping:
                        break
                    src = Path(str(item.get("abs_path") or ""))
                    base_name = Path(str(item.get("name") or "")).name or "font"
                    try:
                        dst = raw_dir / base_name
                        if dst.exists():
                            dst = raw_dir / f"{uuid.uuid4().hex[:6]}_{base_name}"
                        shutil.copy2(src, dst)
                    except Exception as err:
                        stats["failed"] += 1
                        skipped_notes.append(f"{base_name}: 复制失败 {err}")
                        continue
                    if item.get("kind") != "archive":
                        continue
                    try:
                        result = arch.extract_archive(
                            dst,
                            extract_dir,
                            FONT_EXTENSIONS,
                            max_members=max(1, max_files),
                            max_total_bytes=max(1, max_mb) * 1024 * 1024,
                            max_member_bytes=max_font_file_bytes(),
                        )
                        if result.files:
                            for member, reason in (result.skipped + result.errors)[:10]:
                                skipped_notes.append(f"{base_name}/{member}: {reason}")
                        elif result.errors:
                            stats["failed"] += 1
                            for member, reason in result.errors[:5]:
                                skipped_notes.append(f"{base_name}/{member}: {reason}")
                        else:
                            # 压缩包能正常解开但里面没有任何字体：不算失败，
                            # 记一笔空包后直接放行（字幕照常走检查/子集）
                            empty_archives += 1
                            skipped_notes.append(f"{base_name}: 压缩包内无字体，已丢弃")
                    except Exception as err:
                        stats["failed"] += 1
                        skipped_notes.append(f"{base_name}: 解压失败 {err}")
                    finally:
                        try:
                            dst.unlink(missing_ok=True)
                        except Exception:
                            pass
                force_pending = bool(self.get_resource_or_config("torrent_to_pending"))
                merged: Dict[str, Any] = {
                    "added": [],
                    "skipped": [],
                    "failed": 0,
                    "dup_deleted": 0,
                    "delete_failed": 0,
                    "pending": 0,
                }
                for folder in (raw_dir, extract_dir):
                    try:
                        if self._stopping:
                            break
                        sub = self._archive_from_dir(folder, source="torrent", force_pending=force_pending)
                        merged["added"].extend(sub.get("added") or [])
                        merged["skipped"].extend(sub.get("skipped") or [])
                        merged["failed"] += int(sub.get("failed") or 0)
                        merged["pending"] += int(sub.get("pending") or 0)
                    except Exception as err:
                        merged["failed"] += 1
                        skipped_notes.append(f"归档失败: {err}")
                stats["added"] = len(merged["added"])
                stats["pending"] = int(merged["pending"] or 0)
                stats["skipped"] = len(merged["skipped"])
                stats["failed"] += int(merged["failed"] or 0)
                state = "done" if (stats["added"] or merged["pending"]) else ("failed" if stats["failed"] else "empty")
                bits = [f"候选 {stats['picked']} 个", f"新增 {stats['added']}", f"跳过 {stats['skipped']}"]
                if merged["pending"]:
                    bits.append(f"待确认 {merged['pending']}")
                if empty_archives:
                    bits.append(f"空包 {empty_archives} 个")
                if stats["failed"]:
                    bits.append(f"失败 {stats['failed']}")
                if plan_stats.get("pending"):
                    bits.append(f"未下完 {plan_stats['pending']}")
                detail = "，".join(bits)
                if skipped_notes:
                    detail += "；" + "；".join(skipped_notes[:5])
                try:
                    self._db.add_log(
                        f"种子字体收集（{stats['name'] or torrent_hash[:8]}，{source}）：{detail}",
                        "info" if state in ("done", "empty") else "warning",
                    )
                except Exception:
                    pass
                record_id = self._db.add_torrent_ingest(
                    torrent_hash,
                    downloader,
                    stats["name"],
                    source,
                    state,
                    stats["picked"],
                    stats["added"],
                    stats["skipped"],
                    stats["failed"],
                    detail,
                )
                if stats["added"] or merged["pending"]:
                    idx_ok, idx_msg = self._rebuild_subset_index_silent()
                    if idx_ok:
                        self._db.add_log("字体索引已自动重建（种子字体收集后）", "info")
                    else:
                        self._db.add_log(f"字体索引自动重建失败: {idx_msg}", "warning")
                    if stats["added"]:
                        try:
                            self._recheck_missing_after_library_change("种子字体收集")
                        except Exception:
                            pass
                # 字幕入库触发时由「入库检查通知」统一说明，这里不重复推送
                if source != "inbound":
                    self._torrent_notify_result(stats, merged, source)
        except Exception as err:
            state = "failed"
            stats["reason"] = str(err)
            try:
                self._db.add_log(f"种子字体收集异常: {err}", "error")
            except Exception:
                pass
            try:
                record_id = self._db.add_torrent_ingest(
                    torrent_hash, downloader, stats.get("name", ""), source, "failed",
                    stats.get("picked", 0), stats.get("added", 0), stats.get("skipped", 0),
                    stats.get("failed", 0), f"异常: {err}",
                )
            except Exception:
                pass
        finally:
            if staging is not None:
                try:
                    shutil.rmtree(staging, ignore_errors=True)
                except Exception:
                    pass
            stats["record_id"] = record_id
            job["stats"] = stats
            job["state"] = state
            try:
                job["event"].set()
            except Exception:
                pass

    def _torrent_notify_result(
        self, stats: Dict[str, Any], merged: Dict[str, Any], source: str
    ) -> None:
        """非字幕入库来源（整理兜底/手动/定时）的收集结果通知。"""
        try:
            if not self.get_resource_or_config("notify_enabled"):
                return
            added = list(merged.get("added") or [])
            pending = int(merged.get("pending") or 0)
            failed = int(stats.get("failed") or 0)
            if not added and not pending and not failed:
                return
            label = {"transfer": "整理完成兜底", "manual": "手动检查", "poll": "定时检查"}.get(source, source)
            lines = [f"📥 种子字体收集（{label}）：{stats.get('name') or '未知种子'}"]
            if added:
                lines.append(f"✅ 新增 {len(added)} 个：{self._short_names(added, 10)}")
            if pending:
                lines.append(f"📝 已加入待整理 {pending} 个（等待一键整理）")
            if failed:
                lines.append(f"⚠ 处理失败 {failed} 个（详见插件日志）")
            self._notify("字体分类管家：种子字体收集", "\n".join(lines))
        except Exception:
            pass

    def _torrent_queue_delay(self, torrent_hash: str, downloader: str, source: str = "transfer") -> None:
        """整理完成兜底：延迟 torrent_delay_sec 秒再收集（等 MP 搬完文件）。"""
        if not self._torrent_enabled() or not torrent_hash:
            return
        delay = max(0, self._torrent_cfg_int("torrent_delay_sec", 60))
        with self._torrent_jobs_lock:
            timer = self._torrent_delay_timers.get(torrent_hash)
            if timer:
                try:
                    timer.cancel()
                except Exception:
                    pass
            timer = threading.Timer(
                delay,
                self._torrent_delay_timer_fire,
                args=(torrent_hash, downloader, source),
            )
            timer.daemon = True
            timer.start()
            self._torrent_delay_timers[torrent_hash] = timer

    def _torrent_delay_timer_fire(self, torrent_hash: str, downloader: str, source: str) -> None:
        with self._torrent_jobs_lock:
            self._torrent_delay_timers.pop(torrent_hash, None)
        try:
            self._ensure_torrent_collect(torrent_hash, downloader, source=source, wait=False)
        except Exception as err:
            _logger.debug("种子字体收集入队失败: %s", err)

    def _torrent_scan(self, downloader: str = "", hours: int = 0) -> Dict[str, Any]:
        """手动/定时扫描已完成种子：只处理基线之后完成的，逐个入队收集。"""
        if not self._torrent_enabled():
            return {"queued": 0, "scanned": 0, "skipped": 0, "reason": "种子字体收集未启用"}
        baseline = int(time.time()) - int(hours) * 3600 if int(hours or 0) > 0 else self._torrent_ensure_baseline()
        names = [downloader] if downloader else [d["name"] for d in tq.list_downloaders()]
        queued = 0
        scanned = 0
        skipped = 0
        errors: List[str] = []
        if not names:
            errors.append("未发现已启用的下载器")
        for name in names:
            service = tq.get_downloader_service(name)
            instance = tq.service_instance(service)
            if instance is None:
                errors.append(f"{name} 不可用")
                continue
            for item in tq.list_completed(instance):
                scanned += 1
                if int(item.get("completion_on") or 0) < baseline:
                    skipped += 1
                    continue
                res = self._ensure_torrent_collect(item.get("hash") or "", name, source="manual", wait=False)
                if res.get("state") not in ("skipped", "cached"):
                    queued += 1
        return {
            "queued": queued,
            "scanned": scanned,
            "skipped": skipped,
            "baseline": baseline,
            "errors": errors,
        }

    def _torrent_poll_task(self) -> None:
        """定时兜底：扫描下载器已完成种子（只处理基线之后的）。"""
        if not self._torrent_enabled():
            return
        if not self._torrent_poll_lock.acquire(blocking=False):
            return
        try:
            res = self._torrent_scan("", 0)
            if res.get("queued"):
                try:
                    self._db.add_log(
                        f"种子字体收集定时扫描：发现 {res.get('queued')} 个新种子入队（跳过历史 {res.get('skipped')} 个）",
                        "info",
                    )
                except Exception:
                    pass
        except Exception as err:
            _logger.debug("种子字体收集定时扫描失败: %s", err)
        finally:
            try:
                self._torrent_poll_lock.release()
            except Exception:
                pass

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

    def _notify_show_scan(
        self,
        show: str,
        total: int,
        embedded: int,
        missing_map: Dict[str, str],
        extra_lines: Optional[List[str]] = None,
    ) -> None:
        """汇总通知：missing_map = {归一化key: 展示名}（缺 N 种已按 key 去重）

        格式对齐单字幕通知：状态符号 + 结果行 + 明细换行。剧级聚合字体可能较多，
        缺失列表保持「最多 5 个 + 等 N 种」折叠，避免消息过长。
        extra_lines：种子字体收集的补充说明（只在真有收集动作时传入）
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
                    f"❌ 共 {total} 个字幕" + (f"，其中 {embedded} 个已内嵌字体" if embedded else ""),
                    f"缺失 {len(missing_map)} 种字体：{text}",
                    "可在检查页上传缺失字体入库消除标记",
                ]
            else:
                # 全部字幕已内嵌（子集化）：不再说「字体齐全」（观众根本看不出有没有子集化），明确告知
                all_embedded = embedded > 0 and embedded == total
                lines = [
                    f"✅ 共 {total} 个字幕" + (f"，其中 {embedded} 个已内嵌字体" if embedded else ""),
                    "全部字幕已子集化（自带内嵌字体）" if all_embedded else "字幕字体齐全",
                ]
            for extra in extra_lines or []:
                if extra:
                    lines.append(extra)
            self._notify(f"《{show}》字幕检查完成", "\n".join(lines))
        except Exception:
            pass

    def _run_show_scan(
        self,
        key: str,
        tmdbid: str,
        title: str,
        file_list: List[str],
        hashes: Optional[Dict[str, str]] = None,
    ) -> None:
        """聚合到期：处理本次新增的 ASS 字幕列表（由 on_transfer_complete 汇总传入）。

        「入库自动检查字幕」（auto_inbound）开 → 写检查记录并汇总通知；
        「入库后自动子集化」（auto_subset）开 → 对这批字幕做字体子集化并内嵌。
        两者相互独立：只开子集化时不产生检查记录/检查通知，只开检查时不做子集化。

        hashes：本批字幕对应的下载种子（hash -> 下载器名）。种子收集开启时，
        先等这些种子的字体截取完成（最多 torrent_wait_sec 秒），再检查/子集，
        避免「字幕先到、字体还没入库」导致误判缺字。超时也继续，缺字记入结果可重试。
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
            # ── 种子字体收集闸门：先补字体，再检查/子集 ──
            torrent_notes: List[str] = []
            if self._torrent_enabled() and hashes:
                for h, dl in list(hashes.items()):
                    if self._stopping:
                        break
                    res = self._ensure_torrent_collect(str(h), str(dl or ""), source="inbound", wait=True)
                    state = str(res.get("state") or "")
                    if state == "timeout":
                        torrent_notes.append(
                            f"⚠ 种子字体收集超时（{res.get('reason') or '等待上限'}），"
                            "收集仍在后台继续，缺字可稍后重试"
                        )
                    elif state == "failed" and res.get("reason"):
                        torrent_notes.append(f"⚠ 种子字体收集失败：{res.get('reason')}")
                    elif int(res.get("added") or 0) > 0 or int(res.get("pending") or 0) > 0:
                        bits: List[str] = []
                        if int(res.get("added") or 0) > 0:
                            bits.append(f"补充 {int(res.get('added') or 0)} 个字体")
                        if int(res.get("pending") or 0) > 0:
                            bits.append(
                                f"{int(res.get('pending') or 0)} 个已进待整理（确认后重试）"
                            )
                        torrent_notes.append(
                            f"种子收集：{'，'.join(bits)}"
                            f"（来自 {res.get('name') or str(h)[:8]}）"
                        )
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
                self._notify_show_scan(title or key, total, embedded, missing_map, extra_lines=torrent_notes)
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
        - 「入库后自动子集化」（auto_subset）开 → 对新增字幕做子集化；
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
            # 本次整理对应的种子：种子收集开启时，字幕一到就按 hash 截取字体（异步），
            # 聚合到期再等它完成，保证子集化时字体已入库（不依赖视频/字幕事件先后顺序）
            download_hash = str(data.get("download_hash") or "")
            downloader = str(data.get("downloader") or "")
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
            # 字幕一到就先入队种子字体收集（不等视频整理事件，避免事件顺序不可控）
            if download_hash and self._torrent_enabled():
                try:
                    self._ensure_torrent_collect(download_hash, downloader, source="inbound", wait=False)
                except Exception as err:
                    _logger.debug("种子字体收集入队失败: %s", err)
            with self._lock:
                ctx = self._pending_shows.get(key)
                if not isinstance(ctx, dict):
                    ctx = {"files": [], "hashes": {}}
                    self._pending_shows[key] = ctx
                cur = ctx["files"]
                for p in ass_paths:
                    if p not in cur:
                        cur.append(p)
                if download_hash:
                    ctx["hashes"][download_hash] = downloader
                timer = self._show_timers.get(key)
                if timer:
                    timer.cancel()
                timer = threading.Timer(
                    self._ass_finalize_delay,
                    self._run_show_scan,
                    args=(key, tmdbid, title, list(cur), dict(ctx["hashes"])),
                )
                timer.daemon = True
                timer.start()
                self._show_timers[key] = timer
            self._db.add_log(
                f"入库字幕已排队（{title or key}）：{len(cur)} 个，{self._ass_finalize_delay} 秒聚合后统一处理，"
                + ("种子字体收集已先行入队；" if (download_hash and self._torrent_enabled()) else "")
                + "正在等待整部入库完毕…",
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

    @eventmanager.register(EventType.TransferComplete)
    def on_torrent_transfer_complete(self, event) -> None:
        """整理完成兜底：纯字体包种子（没有字幕）不会触发字幕事件，靠这里延迟截取。

        只入队、不阻塞事件总线；延迟 torrent_delay_sec 秒是为了避开 MP 正在搬文件的时刻。
        """
        try:
            if not self._torrent_enabled():
                return
            data = getattr(event, "event_data", None) or {}
            if not isinstance(data, dict):
                return
            torrent_hash = str(data.get("download_hash") or "")
            downloader = str(data.get("downloader") or "")
            if not torrent_hash:
                return
            self._torrent_queue_delay(torrent_hash, downloader, source="transfer")
        except Exception as err:
            _logger.debug("整理完成种子收集入队失败: %s", err)

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
        # uharfbuzz：子集化引擎（逐字符子集化 + [Fonts] 内嵌）
        hb_ok, hb_info = self._hb_status()
        items.append(
            {
                "key": "uharfbuzz",
                "name": "uharfbuzz（子集化引擎）",
                "ok": hb_ok,
                "detail": f"HarfBuzz 子集化引擎（{hb_info}）",
                "impact": "未安装时无法执行子集化（可点「重新安装」并用 pip 安装）",
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
        # 解压工具：zip 内置恒可用；7z/rar 需要系统工具（p7zip / unar / unrar / bsdtar）
        try:
            tools = tq.describe_extract_tools(refresh=True)
        except Exception:
            tools = {"seven_zip": False, "rar": False, "tools": []}
        _tool_names = "、".join(tools.get("tools") or []) or "未检测到"
        items.append(
            {
                "key": "extract_tools",
                "name": "解压工具（7z / rar）",
                "ok": bool(tools.get("seven_zip") or tools.get("rar")),
                "detail": f"zip 内置；已检测到：{_tool_names}",
                "impact": "未安装时只能解 .zip，.7z/.rar 的上传与种子字体收集会被跳过（容器内装 p7zip 后重启插件）",
            }
        )
        ok_count = sum(1 for i in items if i["ok"])
        return self._ok(
            {"items": items, "ok_count": ok_count, "total": len(items)},
            "依赖检测完成",
        )

    async def api_deps_install(self, request: Request) -> Dict[str, Any]:
        """重新安装白名单运行依赖（pip 安装到当前运行环境，成功后热刷新探测）。"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        package = ""
        try:
            package = str(request.query_params.get("package") or "")
        except Exception:
            pass
        if not package:
            try:
                body = await request.json() if hasattr(request, "json") else {}
                if isinstance(body, dict):
                    package = str(body.get("package") or "")
            except Exception:
                pass
        allow = {
            "uharfbuzz": "uharfbuzz",
            "fonttools": "fonttools",
            "watchdog": "watchdog",
        }
        key = str(package or "").strip().lower()
        if key not in allow:
            return self._err(f"不支持的依赖：{package or '（空）'}")
        pkg = allow[key]
        try:
            import sys

            # 异步子进程 + 超时：pip 安装最长 5 分钟，绝不能用同步 subprocess.run
            # 占住事件循环（否则安装期间整个 MoviePilot 的 HTTP 请求全部挂起）
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-cache-dir",
                "--upgrade",
                pkg,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                out_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=300)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                try:
                    await proc.wait()
                except Exception:
                    pass
                return self._err(f"安装 {pkg} 超时（300 秒），已终止")
        except Exception as err:
            return self._err(f"安装 {pkg} 失败: {err}")
        returncode = int(proc.returncode or 0)
        ok = returncode == 0
        output = (out_bytes or b"").decode("utf-8", errors="replace").strip()[-1500:]
        # 热刷新探测缓存：uharfbuzz 安装后无需重启进程即可用于子集化
        self._hb_probe = None
        try:
            if pkg == "uharfbuzz":
                hb_refresh_backend()
        except Exception:
            pass
        try:
            self._db.add_log(
                f"依赖重装 {pkg}: {'成功' if ok else '失败'}（exit={proc.returncode}）",
                "info" if ok else "error",
            )
        except Exception:
            pass
        if not ok:
            return self._err(f"安装 {pkg} 失败（exit={proc.returncode}）：{output[-400:]}")
        note = "；需重启插件/容器后生效" if pkg != "uharfbuzz" else "（已热加载）"
        return self._ok({"package": pkg, "output": output}, f"{pkg} 安装完成{note}")

    # ─── API：统计 ──────────────────────────────────────
    def _input_dir_signature(self, input_dir: Path) -> str:
        """监控目录内容签名：目录 mtime + 首层文件数——目录 mtime 变化通常意味着
        有新文件写入/删除；对深层子目录变化不敏感（可接受），避免每次 stat 整个树。（Q4 修复）
        """
        try:
            st = input_dir.stat()
            sig = f"{st.st_mtime_ns}:{st.st_size}"
            try:
                with os.scandir(input_dir) as it:
                    n = sum(1 for _ in it)
                sig += f":{n}"
            except Exception:
                pass
            return sig
        except Exception:
            return ""

    def _count_pending_incoming(self) -> int:
        """字体监控目录中尚未被收集的字体文件数（仪表盘「待整理」口径）

        实时递归扫描输入目录的字体文件，排除：
        - 位于字体库目录内的（归档落点与输入目录重叠的场景，文件本身就在库里）；
        - 已在「待确认」列表挂档的；
        - 已被监控/全量检查处理过的源文件（_archive_font_file 归档或同名跳过时标记）。

        用户往监控目录放 N 个字体 → 未入库前显示 N，监控自动归档/全量检查处理后归零。

        Q4 修复：加目录内容签名 + 30 秒 TTL 缓存——目录签名未变（无新写入）
        且在 TTL 内直接复用上次计数，避免 30 秒轮询每次都全量 rglob。
        """
        try:
            input_dir = self.get_resource_or_config("input_dir") or ""
            if not input_dir or not Path(input_dir).is_dir():
                return 0
            lib_dir = self.get_resource_or_config("lib_dir") or ""
            # 目录签名缓存：签名相同且在 30 秒内直接返回缓存结果
            sig = self._input_dir_signature(Path(input_dir))
            cache = self._pending_income_cache
            if cache and cache[0] == sig and (time.time() - cache[1]) < 30:
                return cache[2]
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
            self._pending_income_cache = (sig, time.time(), count)
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
            {"label": "ASS 字幕检查目录", "path": cfg.get("ass_dir", ""), "exists": bool(cfg.get("ass_dir")) and Path(cfg["ass_dir"]).is_dir()},
            {"label": "ASS 自动子集化目录", "path": cfg.get("subset_dir", ""), "exists": bool(cfg.get("subset_dir")) and Path(cfg["subset_dir"]).is_dir()},
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
        persisted = True
        persist_error = ""
        # 1) 写入宿主原生配置（与宿主 PUT /plugin 同等的持久化路径，重启保留）
        try:
            self.update_config(new_cfg)
        except Exception as err:
            persisted = False
            persist_error = str(err)
            _logger.warning("宿主配置写入失败: %s", err)
        # 2) 更新运行时并热生效
        self._config = new_cfg
        self._apply_font_limits()
        if self._db:
            try:
                self._db.save_full_config(new_cfg)
            except Exception as err:
                _logger.warning("配置镜像写入数据库失败: %s", err)
        if isinstance(new_cfg.get("enabled"), bool):
            self._enabled = new_cfg["enabled"]
        else:
            try:
                self._enabled = bool(new_cfg.get("enabled", self._enabled))
            except Exception:
                pass
        try:
            # Q18 修复：补 self._db 判空，与其他调用点防御风格一致
            if self._db is not None:
                self._db.set_setting("enabled", self._enabled)
            self._db.add_log("插件配置已更新", "info")
            self._start_watcher()
        except Exception as err:
            _logger.warning("配置生效失败: %s", err)
        if not persisted:
            # P2-16：宿主持久化失败不能报「保存成功」——本地运行时已生效，
            # 但重启后可能回退，必须如实告知（否则用户以为已永久保存）
            try:
                if self._db is not None:
                    self._db.add_log(
                        f"配置仅运行时生效：宿主持久化失败（{persist_error[:120]}）", "error"
                    )
            except Exception:
                pass
            result = self._err(
                "配置已在当前会话生效，但宿主持久化失败（重启后可能丢失）："
                f"{persist_error[:160]}"
            )
            result["data"] = {"persisted": False, "config": new_cfg}
            return result
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
        """从 JSON 备份恢复数据库（单事务替换业务表 + 作废字体索引，随后重建）

        恢复期间持维护权：watcher / 自动扫描 / 索引重建 / 子集化全部让步，
        避免「恢复中后台仍在写库」；恢复成功后字体索引已在事务内清空并递增
        index_version，由下一次检查/子集化的懒加载重建（或手动「全部重建」）。
        """
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
        if not self._maintenance_begin("数据库恢复"):
            return self._err("正在执行其他维护任务（恢复/清库/删除/重建），请稍后重试")
        try:
            counts = self._db.import_all(body)
            # 恢复后的索引已作废：立刻在此刻把运行时缓存清掉，避免旧聚合结果短暂命中
            self._invalidate_missing_agg()
            self._db.add_log(
                "数据库恢复完成：字体索引已作废，将在下次检查/子集化时自动重建"
                f"（恢复 {len(counts)} 张表）",
                "warning",
            )
            return self._ok(
                counts,
                "数据库恢复成功（字体索引将自动重建），请刷新页面",
            )
        except Exception as err:
            return self._err(f"导入数据库失败（已回滚，原数据未变）: {err}")
        finally:
            self._maintenance_end("数据库恢复")

    def api_db_clear(self) -> Dict[str, Any]:
        """清空数据库业务表（字体库、待确认、ASS 检查记录）；保留插件设置与镜像"""
        if not self._db_ok():
            return self._err("数据库未初始化")
        if not self._maintenance_begin("清空数据库"):
            return self._err("正在执行其他维护任务（恢复/清库/删除/重建），请稍后重试")
        try:
            counts = self._db.clear_all()
            # 索引状态已在 clear_all 内复位（last_rebuild/engine/lib_dir 清空 + index_version 递增）
            self._invalidate_missing_agg()
            self._db.add_log("数据库已清空：字体索引状态同步复位", "warning")
            return self._ok(counts, "数据库已清空")
        except Exception as err:
            return self._err(f"清空数据库失败: {err}")
        finally:
            self._maintenance_end("清空数据库")

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

    def api_font_tree_meta(self) -> Dict[str, Any]:
        """字体库变更签名（Q15 修复）：轮询路径的轻量"有没有变化"检查——
        只跑两次聚合 SQL（count + max(id)/max(updated_at)），避免轮询每次
        全量返回上万条字体 JSON。前端轮询比对签名，无变化不重拉 /fonts/tree。
        """
        if not self._db_ok():
            return self._ok({"total": 0, "signature": ""})
        try:
            row = self._db.query_one(
                "SELECT COUNT(*) AS c, COALESCE(MAX(id),0) AS m, "
                "COALESCE(MAX(updated_at),'') AS u FROM fonts"
            )
            c = row["c"] if row else 0
            m = row["m"] if row else 0
            u = row["u"] if row else ""
            return self._ok({"total": c, "signature": f"{c}:{m}:{u}"})
        except Exception as err:
            return self._err(f"读取字体库签名失败: {err}")

    def api_font_delete(self, id: int = 0) -> Dict[str, Any]:
        """删除字体：删除数据库记录 + 磁盘上的字体文件（含清理空目录）

        级联（P1-7）：删除前收集该文件贡献的字体名/别名，删除成功并提交索引后
        统一失效缺失聚合缓存，并重检受影响的字幕——只由这份字体覆盖的字符会
        立刻回到 missing/partial，不再等到 TTL 到期或手动重检。
        """
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        if not id:
            return self._err("缺少字体ID")
        if not self._maintenance_begin("删除字体"):
            return self._err("正在执行其他维护任务（恢复/清库/删除），请稍后重试")
        try:
            row = self._db.get_font(id)
            if not row:
                return self._err("字体不存在")
            file_path = row.get("file_path", "") or ""
            # 删除前收集索引贡献的别名（face/alias）：删除后 alias 行会一并消失，必须先取
            affected_keys: List[str] = []
            if file_path:
                try:
                    for r in self._db.query(
                        "SELECT DISTINCT a.alias AS alias FROM font_aliases a "
                        "JOIN font_faces fa ON fa.id = a.face_id "
                        "JOIN font_files ff ON ff.id = fa.file_id WHERE ff.path = ?",
                        (str(file_path),),
                    ):
                        alias = str(r.get("alias") or "")
                        if alias:
                            affected_keys.append(alias)
                except Exception:
                    affected_keys = []
            file_deleted = False
            lib_dir = self.get_resource_or_config("lib_dir") or ""
            if file_path:
                p = Path(file_path)
                if p.is_file():
                    # 删除边界：只允许删字体库目录内的字体文件；越界（db 导入注入/改配置后的旧记录）拒绝
                    if not arch.safe_unlink(p, lib_dir, exts=FONT_EXTENSIONS):
                        return self._err("拒绝删除：文件不在字体库目录内或不是字体文件")
                    file_deleted = True
                # 若父目录位于字体库内且已为空，则一并清理
                if lib_dir and _path_within(p.parent, Path(lib_dir)):
                    try:
                        p.parent.rmdir()
                    except Exception:
                        pass
            self._db.delete_font(id)
            self._remove_font_from_index(file_path)
            self._db.add_log(
                f"删除字体: {row.get('file_name', '')} ({'已删除文件' if file_deleted else '文件不存在，仅删记录'})",
                "warning",
            )
            # 级联失效：缺失聚合按新库重算，受影响字幕（源文件仍在时）安全重检
            try:
                self._invalidate_missing_agg()
            except Exception:
                pass
            recheck = {"checked": 0, "ok": 0, "missing": 0, "failed": 0}
            if affected_keys:
                try:
                    recheck = self._recheck_affected_ass(affected_keys, reason="字体删除")
                except Exception as err:
                    _logger.warning("字体删除后重检受影响字幕失败: %s", err)
            return self._ok(
                {"id": id, "file_deleted": file_deleted, "recheck": recheck},
                "字体已删除" + (f"，已重检 {recheck['checked']} 个字幕" if recheck["checked"] else ""),
            )
        except Exception as err:
            return self._err(f"删除失败: {err}")
        finally:
            self._maintenance_end("删除字体")

    def api_recalc_vendor(self, id: int = 0) -> Dict[str, Any]:
        """重新识别厂商：按新规则（内部制造商名/目录名/文件名）重新解析字体库内字体的厂商。
        不传 id 时全量重算；传 id 时仅重算单个字体。返回变更数量。
        文件已不存在（外部删除/移动）的记录会一并清除，保证厂商分布/字体库统计与磁盘一致。"""
        if not self._db_ok():
            return self._err("数据库未初始化")
        scan_mode = "internal"  # fontTools 为唯一权威解析口径
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
                    self._remove_font_from_index(file_path)
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
                    # 防御畸形 TTC：numFonts 最大 42 亿，必须封顶，否则逐 face 解析会长时间卡死线程
                    num = min(struct.unpack(">I", raw[8:12])[0], 64)
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
                    num = min(struct.unpack(">I", raw[8:12])[0], 64)
                    if 12 + 4 * num > len(raw):
                        return raw  # 头部 offset 表不完整：畸形文件，别按越界数据切片
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
            try:
                font_size = Path(file_path).stat().st_size
            except OSError as err:
                return self._err(f"读取字体文件失败: {err}")
            if font_size > max_font_file_bytes():
                return self._err(
                    f"字体文件过大（{font_size // (1024 * 1024)}MB），超过预览上限 "
                    f"{max_font_file_bytes() // (1024 * 1024)}MB"
                )
            raw = Path(file_path).read_bytes()
            # TTC（TrueType Collection）拆单 face 再预览：浏览器 FontFace 不认 ttcf 容器
            # （会抛 Invalid font data in ArrayBuffer）。_split_ttc_face 逐 face 用 fontTools
            # 解析重存（可正确处理表数据交错排布的非标准 TTC），并对结果再解析校验；
            # 全部失败才回退整文件交给浏览器报错。
            if raw[:4] == b"ttcf":
                raw = self._split_ttc_face(raw, file_path)
            data = base64.b64encode(raw).decode("ascii")
            # 字体信息（字符数 / face 数 / 名称兜底）：fontTools 权威口径
            char_count = 0
            face_count = 0
            try:
                inspection = inspect_font(file_path, with_hash=False)
                face_count = inspection.face_count or len(inspection.faces)
                valid = [f for f in inspection.faces if f.status in ("ok", "no_cmap")]
                char_count = max((f.char_count for f in valid), default=0)
                first = valid[0] if valid else None
                if first is not None:
                    name = name or first.display_name()
                    family = family or first.family
            except Exception:
                pass
            return self._ok(
                {
                    "id": 0,
                    "name": name,
                    "family": family,
                    "data": data,
                    "char_count": char_count,
                    "face_count": face_count,
                }
            )
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

    async def _write_upload_limited(self, upload: Any, dest: Path, max_bytes: int) -> Tuple[int, bool]:
        """分块流式写盘（不把整文件读入内存），超过上限立即中止并删除半成品。

        返回 (写入字节数, 是否超限)。读取异常会清理半成品后向上抛出。
        """
        written = 0
        too_large = False
        try:
            with dest.open("wb") as fh:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_bytes:
                        too_large = True
                        break
                    fh.write(chunk)
        except Exception:
            try:
                dest.unlink(missing_ok=True)
            except Exception:
                pass
            raise
        if too_large or written <= 0:
            try:
                dest.unlink(missing_ok=True)
            except Exception:
                pass
        return written, too_large

    async def _receive_uploads(
        self,
        upload_files: List[Any],
        allowed_exts: Tuple[str, ...],
        prefix: str = "up",
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """把上传文件（含 .zip 压缩包）落到临时目录，返回可处理的文件清单。

        - 普通文件：后缀在 allowed_exts 内才接收，写 tmp/<prefix>_<uuid>_<name>
        - .zip：安全解压到 tmp/_unzip_<uuid>/，只取 allowed_exts 内的文件（只解一层）
        - 安全上限：单请求文件数、单文件字节数、总字节数，流式写盘不在内存里囤整包
        - 返回 (files, notes)：files 每项 file_name/path/size/from_archive；
          notes 为压缩包跳过/拒绝的说明，供接口回显
        """
        files: List[Dict[str, Any]] = []
        notes: List[str] = []
        if not self._tmp_dir:
            return files, ["临时目录未初始化"]
        base = Path(self._tmp_dir)
        try:
            base.mkdir(parents=True, exist_ok=True)
        except Exception as err:
            return files, [f"临时目录不可用: {err}"]
        exts = tuple(str(e).lower() for e in allowed_exts)
        # 单文件上限按用途区分：字体走可配置上限（默认 128MB）/ 字幕 16MB
        extset = set(exts)
        is_font_upload = bool(extset & {e.lower() for e in FONT_EXTENSIONS})
        member_limit = max_font_file_bytes() if is_font_upload else MAX_ASS_FILE_BYTES
        uploads = list(upload_files)
        if len(uploads) > MAX_UPLOAD_FILES:
            notes.append(
                f"一次最多上传 {MAX_UPLOAD_FILES} 个文件，已忽略多余的 {len(uploads) - MAX_UPLOAD_FILES} 个"
            )
            uploads = uploads[:MAX_UPLOAD_FILES]
        total_bytes = 0
        for upload in uploads:
            file_name = getattr(upload, "filename", "") or ""
            safe_name = Path(file_name).name
            if not safe_name:
                continue
            if arch.is_any_archive(safe_name):
                if not arch.is_archive(safe_name):
                    notes.append(
                        f"{safe_name}: 未检测到 {Path(safe_name).suffix or '该格式'} 的解压工具，"
                        "暂不支持该压缩包（.zip 可直接上传）"
                    )
                    continue
                zip_path = base / f"{prefix}_{uuid.uuid4().hex}_{safe_name}"
                try:
                    written, too_large = await self._write_upload_limited(
                        upload, zip_path, MAX_UPLOAD_TOTAL_BYTES
                    )
                except Exception as err:
                    notes.append(f"{safe_name}: 读取失败 {err}")
                    continue
                if too_large:
                    notes.append(
                        f"{safe_name}: 压缩包超过单次上传总量上限（{MAX_UPLOAD_TOTAL_BYTES // (1024 * 1024)}MB）"
                    )
                    continue
                if not written:
                    continue
                dest = base / f"_unzip_{uuid.uuid4().hex}"
                result = arch.extract_archive(
                    zip_path,
                    dest,
                    exts,
                    max_members=500,
                    max_total_bytes=MAX_UPLOAD_TOTAL_BYTES,
                    max_member_bytes=member_limit,
                )
                try:
                    zip_path.unlink(missing_ok=True)
                except Exception:
                    pass
                for item in result.files:
                    if len(files) >= MAX_UPLOAD_FILES:
                        notes.append(f"{safe_name}: 单次最多处理 {MAX_UPLOAD_FILES} 个文件，其余已忽略")
                        break
                    if total_bytes + item.size > MAX_UPLOAD_TOTAL_BYTES:
                        notes.append(f"{safe_name}: 解压后总大小超过单次上传上限，其余已忽略")
                        break
                    total_bytes += item.size
                    files.append(
                        {
                            "file_name": Path(item.path).name,
                            "path": str(item.path),
                            "size": item.size,
                            "from_archive": safe_name,
                        }
                    )
                for member, reason in (result.skipped + result.errors)[:20]:
                    notes.append(f"{safe_name}/{member}: {reason}")
                if not result.files and not result.skipped and not result.errors:
                    notes.append(f"{safe_name}: 压缩包内没有可处理的文件")
                continue
            if Path(safe_name).suffix.lower() not in exts:
                continue
            if len(files) >= MAX_UPLOAD_FILES:
                notes.append(f"单次最多处理 {MAX_UPLOAD_FILES} 个文件，其余已忽略")
                break
            tmp_path = base / f"{prefix}_{uuid.uuid4().hex}_{safe_name}"
            try:
                written, too_large = await self._write_upload_limited(upload, tmp_path, member_limit)
            except Exception as err:
                notes.append(f"{safe_name}: 读取失败 {err}")
                continue
            if too_large:
                notes.append(
                    f"{safe_name}: 超过单文件上限（{member_limit // (1024 * 1024)}MB）"
                )
                continue
            if not written:
                continue
            if total_bytes + written > MAX_UPLOAD_TOTAL_BYTES:
                arch.safe_unlink(tmp_path, base, exts=exts)
                notes.append(f"{safe_name}: 超过单次上传总量上限，其余已忽略")
                break
            total_bytes += written
            files.append(
                {"file_name": safe_name, "path": str(tmp_path), "size": written, "from_archive": ""}
            )
        return files, notes

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
        scan_mode = "internal"  # fontTools 为唯一权威解析口径
        files, notes = await self._receive_uploads(upload_files, FONT_EXTENSIONS, prefix="up")

        def _preview_sync() -> List[Dict[str, Any]]:
            """fontTools 解析是同步重活：放到线程池，避免阻塞事件循环拖住全站请求。"""
            done: List[Dict[str, Any]] = []
            for entry in files:
                safe_name = entry["file_name"]
                tmp_path = Path(entry["path"])
                if not tmp_path.is_file():
                    continue
                meta = parse_font_metadata(
                    tmp_path, scan_mode=scan_mode, filename_hint=Path(safe_name).stem
                )
                item: Dict[str, Any] = {
                    "file_name": safe_name,
                    "file_path": str(tmp_path),
                    "name": meta["name"],
                    "family": meta["family"],
                    "vendor": meta["vendor"],
                    "designer": meta["designer"],
                    "file_size": entry.get("size", 0),
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
            return done

        done = await asyncio.to_thread(_preview_sync)
        if not done:
            msg = "没有可上传的有效字体文件（需字体后缀或 .zip 压缩包，且内容非空）"
            if notes:
                msg += "；" + "；".join(notes[:3])
            return self._err(msg)
        tail = f"，压缩包内 {len(done)} 个文件已展开" if any(e.get("from_archive") for e in files) else ""
        return self._ok(
            {"count": len(done), "items": done, "notes": notes},
            f"已加入待确认列表 {len(done)} 个字体{tail}" + (f"（{len(notes)} 条跳过提示）" if notes else ""),
        )

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
                # 只删插件临时目录内的上传缓存；监控目录里用户自己的源文件绝不动
                arch.safe_unlink(row["file_path"], self._tmp_dir, exts=FONT_EXTENSIONS)
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
                dest_dir = Path(lib_dir) / safe_filename_component(
                    str(item.get("vendor") or "未知厂商"), "未知厂商"
                )
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
                # 内部名不可信：清洗后方可拼路径
                base_name = safe_filename_component(base_name)
                # 按格式分子文件夹归档：字体库/厂商/格式/基础名.后缀
                fmt_dir = dest_dir / _font_subdir_name(src.suffix)
                existing = _dest_exists_recursive(dest_dir, base_name, src.suffix)
                if existing and _files_identical(src, existing):
                    # 字体库已存在「内容完全相同」的同名同后缀字体：跳过
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
                if existing:
                    # 同名但内容不同：改名 -2/-3 另存，不覆盖旧版，更不能删源文件
                    index = self._dest_names_for(dest_dir)
                    base_name = _unique_archive_base(index, base_name, src.suffix)
                    self._db.add_log(
                        f"{src.name} 与库内 {existing.name} 同名但内容不同，另存为 {base_name}{src.suffix}",
                        "warning",
                    )
                try:
                    fmt_dir.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
                dest = fmt_dir / f"{base_name}{src.suffix}"
                if not _path_within(dest, Path(lib_dir)):
                    raise ValueError(f"目标越界，拒绝归档: {dest}")
                # 原子落盘 + 大小校验：失败只留临时文件，不会出现半截正名文件
                src_size = src.stat().st_size
                tmp_dest = fmt_dir / f".{dest.name}.tmp-{uuid.uuid4().hex[:8]}"
                try:
                    shutil.copy2(str(src), str(tmp_dest))
                    written = tmp_dest.stat().st_size
                    if written != src_size:
                        raise RuntimeError(f"写入大小不一致（源 {src_size}，目标 {written}）")
                    os.replace(str(tmp_dest), str(dest))
                except Exception:
                    try:
                        tmp_dest.unlink(missing_ok=True)
                    except Exception:
                        pass
                    raise
                if archive_mode == "move":
                    try:
                        src.unlink()
                    except Exception as err:
                        self._db.add_log(f"已归档 {dest.name}，但删除源文件失败: {err}", "warning")
                else:
                    # 复制模式：只清理上传临时目录里的缓存，监控目录源文件保持不动
                    if self._tmp_dir and _path_within(src, Path(self._tmp_dir)):
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
                self._index_font_path(dest)
                self._db.delete_pending(item["id"])
                processed += 1
            except Exception as err:
                failed.append({"name": item.get("file_name", ""), "reason": str(err)})
        self._db.add_log(f"一键整理：归档 {processed} 个字体", "info")
        idx_ok, idx_msg = ("", "")
        recheck = {"checked": 0, "ok": 0, "missing": 0, "failed": 0}
        if processed:
            try:
                idx_ok, idx_msg = self._rebuild_subset_index_silent()
            except Exception:
                idx_ok, idx_msg = False, "索引重建异常"
            if idx_ok:
                self._db.add_log("字体索引已自动重建（一键整理后）", "info")
            else:
                self._db.add_log(f"字体索引自动重建失败: {idx_msg}", "warning")
            # 字体库这边归档补齐后：重检受影响字幕，缺失页/检查页立即消除已解决项
            recheck = self._recheck_missing_after_library_change("字体库归档")
        if failed:
            self._db.add_log(f"整理失败 {len(failed)} 个", "error")
        # 一键整理为同页面手动操作，结果直接反映在前端提示，不再额外发送通知
        return self._ok(
            {"processed": processed, "failed": failed, "index_ok": idx_ok, "recheck": recheck},
            f"已归档 {processed} 个字体" + ("" if not idx_ok else "，字体索引已自动重建"),
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
                if item.get("file_path"):
                    # 只清上传缓存；监控目录用户源文件保留
                    arch.safe_unlink(item["file_path"], self._tmp_dir, exts=FONT_EXTENSIONS)
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
                stats = self._archive_from_dir(Path(input_dir), source="scan")
                added = len(stats["added"])
                idx_ok, idx_msg = self._rebuild_subset_index_silent()
                self._db.add_log(
                    f"检查归档：归档 {added} 个字体，跳过已存在 {len(stats['skipped'])} 个",
                    "info",
                )
                if idx_ok:
                    self._db.add_log("字体索引已自动重建（全量检查归档后）", "info")
                elif added:
                    # 归档成功但索引重建失败：提示但不阻塞归档结果
                    self._db.add_log(f"字体索引自动重建失败: {idx_msg}", "warning")
                if added:
                    # 归档补齐字体后重检受影响字幕，缺失页/检查页立即消除已解决项
                    self._recheck_missing_after_library_change("全量检查归档")
                self._db.set_last_scan_time()  # 记录「上次全量检查」时间（仪表盘展示）
                # 全量检查通知：与自动归档统一模板（新增/跳过/失败分项 + 明确模式）
                self._archive_notify(
                    stats,
                    source_label="扫描",
                    title_prefix="全量检查完成",
                    extra=("⚠ 字体索引重建失败（详见插件日志）" if (added and not idx_ok) else ""),
                )
                return self._ok(
                    {"added": added, "index_ok": idx_ok},
                    f"已归档 {added} 个字体" + ("，字体索引已自动重建" if idx_ok else ""),
                )
            # 「目录自动收集」关闭：加入待确认列表等待一键整理
            scan_mode = "internal"  # fontTools 为唯一权威解析口径
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
                if self.get_resource_or_config("notify_enabled"):
                    self._notify(
                        "字体分类管家：全量检查完成",
                        f"✅ 全量检查完成\n新增 {added} 个待确认字体"
                        + (f"，已跳过 {skipped} 个已在待确认中的文件" if skipped else ""),
                    )
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
            stats = self._archive_from_dir(Path(input_dir), source="scan")
            added = len(stats["added"])
            self._db.add_log(
                f"全量扫描：归档 {added} 个字体，跳过已存在 {len(stats['skipped'])} 个，失败 {stats['failed']} 个",
                "info",
            )
            if added:
                # 补齐字体后重建/增量更新索引，并重检受影响字幕（缺失页/检查页即时消除）
                self._rebuild_subset_index_silent()
                self._recheck_missing_after_library_change("全量扫描归档")
            # 全量扫描通知：与自动归档统一模板（新增/跳过/失败分项 + 明确模式）
            self._archive_notify(stats, source_label="扫描", title_prefix="全量扫描完成")
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
        # Q2 修复：_prune_stale_records 不再挂在每次列表请求上（全表 stat 昂贵），
        # 改为 5 分钟上限的低频清理——下个周期前拉到被删除字幕的记录最多 5 分钟延迟，
        # 对比原先每次轮询全表 stat 的代价可忽略
        try:
            now_ts = time.time()
            if now_ts - self._last_prune_ts > 300:
                self._prune_stale_records()
                self._last_prune_ts = now_ts
        except Exception:
            pass
        try:
            data = self._db.query_ass(keyword=(search or "").strip(), page=page, limit=limit)
            families, match_source = self._lib_font_keys()
            # 字形快照按 ass_id 分组（一次查询），列表状态与缺失页同口径：按当前字体库实时扣除
            snap_by_ass: Dict[Any, Dict[str, Dict[str, Any]]] = {}
            try:
                for snap in self._latest_missing_snapshots():
                    snap_by_ass.setdefault(snap.get("ass_id"), {})[
                        normalize_font_key(snap.get("font_name") or "")
                    ] = snap
            except Exception:
                snap_by_ass = {}
            coverage: Dict[str, set] = {}
            # 匹配来源提升到顶层：列表为空（无记录）时前端也能显示「匹配基准」提示
            data["match_source"] = match_source
            for r in data.get("list", []):
                # 匹配来源透传（index=fontTools 字体索引 / db=字体库记录，索引未构建时回退）
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
                    # Q2 修复：subsetted 判定走 (mtime_ns, size) 签名缓存，
                    # 文件未变化仅 stat 一次，不再每行 read_bytes 整个 ASS 文件
                    subsetted = self._ass_is_subsetted(fp)
                    snaps = snap_by_ass.get(r["id"]) or {}
                    missing_live: List[str] = []
                    seen_k: set = set()
                    for f in all_fonts:
                        k = normalize_font_key(f)
                        if not k or k in seen_k:
                            continue
                        seen_k.add(k)
                        snap = snaps.get(k)
                        if snap is not None:
                            # 字形级：字符已被当前字体库覆盖则不再算缺失
                            cps, remain, _chars = self._snapshot_remaining(snap, coverage)
                            if cps and not remain:
                                continue
                            missing_live.append(f)
                        elif k not in families:
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
        files, notes = await self._receive_uploads(upload_files, ASS_EXTENSIONS, prefix="ass")
        done: List[Dict[str, Any]] = []
        for entry in files:
            safe_name = entry["file_name"]
            tmp_path = Path(entry["path"])
            if not tmp_path.is_file():
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
            msg = "没有可上传的有效 ASS 文件（需 .ass 后缀或 .zip 压缩包，且内容非空）"
            if notes:
                msg += "；" + "；".join(notes[:3])
            return self._err(msg)
        return self._ok(
            {"count": len(done), "items": done, "notes": notes},
            f"已上传 {len(done)} 个字幕，请在列表中手动检查",
        )

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
            # 读盘 + 字形解析 + 索引比对都是同步重活：放线程池，别占住事件循环
            raw = await asyncio.to_thread(Path(src_path).read_bytes)
            # 走统一检查口径（字形级优先，索引不可用时回退名称级）
            result = await asyncio.to_thread(
                self._check_ass_content,
                row.get("file_name") or Path(src_path).name,
                raw,
                row.get("source") or "manual",
                src_path,
            )
            # 记录 id 可能因并发新增而变化，以本次检查结果为准
            ass_id = result.get("id") or int(ass_id)
            self._db.add_log(
                f"手动检查: {row['file_name']} → {result.get('status_text')}",
                "warning" if result.get("missing_count") else "info",
            )
            self._invalidate_missing_agg()
            families, _fmatch = await asyncio.to_thread(self._lib_font_keys)
            return self._ok(
                {
                    "id": ass_id,
                    "file_name": row["file_name"],
                    "status": result.get("status"),
                    "status_text": result.get("status_text"),
                    "missing_count": result.get("missing_count", 0),
                    "all_fonts": [
                        {"name": f, "in_lib": normalize_font_key(f) in families}
                        for f in (result.get("all_fonts") or [])
                    ],
                    "missing_fonts": result.get("missing_fonts") or [],
                    "missing_details": result.get("missing_details") or [],
                    "total_missing_chars": result.get("total_missing_chars", 0),
                    "subsetted": result.get("subsetted", False),
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
            snapshots: Dict[str, Dict[str, Any]] = {}
            try:
                for snap in self._db.latest_missing_glyphs(int(id)):
                    key = normalize_font_key(snap.get("font_name") or "")
                    if key:
                        snapshots[key] = snap
            except Exception:
                snapshots = {}
            if stored_all:
                # 缺失清单按归一化 key 去重（@竖排变体与本体同 key 只算一次）
                seen_k: set = set()
                missing_live: List[str] = []
                details: List[Dict[str, Any]] = []
                coverage: Dict[str, set] = {}
                for f in stored_all:
                    k = normalize_font_key(f)
                    if not k or k in seen_k:
                        continue
                    seen_k.add(k)
                    snap = snapshots.get(k)
                    if snap is not None:
                        # 字形级口径 + 实时扣除：按当前字体库字符覆盖重算剩余缺失，
                        # 字体库那边补齐字体后，本页的红色缺失标记自动消失
                        cps_all, remain, remain_chars = self._snapshot_remaining(snap, coverage)
                        status = snap.get("status") or "ok"
                        if cps_all and not remain:
                            status = "ok"
                        elif status == "missing" and cps_all and remain != cps_all:
                            status = "partial"
                        faces: List[Any] = []
                        try:
                            faces = json.loads(snap.get("faces") or "[]")
                        except Exception:
                            pass
                        detail = {
                            "name": f,
                            "status": status,
                            "used_count": int(snap.get("used_count") or 0),
                            "missing_count": len(remain) if cps_all else int(snap.get("missing_count") or 0),
                            "missing_codepoints": sorted(remain) if cps_all else [],
                            "missing_chars": remain_chars if cps_all else (snap.get("missing_chars") or ""),
                            "faces": faces,
                        }
                        if status in ("missing", "partial"):
                            missing_live.append(f)
                    else:
                        # 无字形快照（历史记录）：回退名称级判定
                        in_lib = k in families
                        if not in_lib:
                            missing_live.append(f)
                        detail = {
                            "name": f,
                            "status": "ok" if in_lib else "missing",
                            "used_count": 0,
                            "missing_count": 0,
                            "missing_codepoints": [],
                            "missing_chars": "",
                            "faces": [],
                        }
                    details.append(detail)
                # 已内嵌（子集化）字幕：即使字体库删减也不报缺失
                if subsetted:
                    missing_live = []
                    details = []
                    row["status"] = "ok"
                elif missing_live:
                    row["status"] = "missing"
                elif row.get("status") == "partial_check":
                    # 原检查未完成字形级验证（名称存在但未验证字符覆盖）：
                    # 详情页不能因为「当前库里名字都在」就改口显示「字体完整」
                    row["status"] = "partial_check"
                else:
                    row["status"] = "ok"
                row["all_fonts"] = [{"name": f, "in_lib": normalize_font_key(f) in families} for f in stored_all]
                row["missing_fonts"] = missing_live
                row["missing_count"] = len(missing_live)
                row["missing_details"] = details
            else:
                row["all_fonts"] = []
                row["missing_fonts"] = []
                row["missing_count"] = 0
                row["missing_details"] = []
            row["match_source"] = match_source
            row["subsetted"] = subsetted
            return self._ok(row)
        except Exception as err:
            return self._err(f"读取详情失败: {err}")

    def _owns_ass_copy(self, file_path: str) -> bool:
        """插件拥有该字幕副本：真实路径位于插件临时目录内且后缀为 ASS。

        P0 数据安全：删除检查记录只允许清理插件自己落盘的临时副本；
        监控目录/媒体库里的原始字幕（source=auto/manual/inbound 等）一律
        只删记录、绝不按 source 字符串推断磁盘文件可删。
        """
        if not file_path or self._tmp_dir is None:
            return False
        try:
            if Path(file_path).suffix.lower() not in {s.lower() for s in ASS_EXTENSIONS}:
                return False
        except Exception:
            return False
        return _path_within(Path(file_path), Path(self._tmp_dir))

    def api_ass_delete(self, id: int = 0) -> Dict[str, Any]:
        """删除单条检查记录（仅清理插件临时目录内的副本，不动原始字幕）"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        if not id:
            return self._err("缺少记录ID")
        try:
            row = self._db.get_ass(id)
            self._db.delete_ass(id)
            # 只清理插件临时目录内的字幕副本（手动上传落盘的临时文件）；
            # 监控目录/媒体库的原始字幕只删记录，避免误删用户原件
            file_removed = False
            if row and self._owns_ass_copy(row.get("file_path") or ""):
                file_removed = arch.safe_unlink(row["file_path"], self._tmp_dir, exts=ASS_EXTENSIONS)
            return self._ok({"file_removed": file_removed}, "已删除")
        except Exception as err:
            return self._err(f"删除失败: {err}")

    def api_ass_clear(self) -> Dict[str, Any]:
        """清空全部检查记录（仅清理插件临时目录内的副本，不动原始字幕）"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        if not self._maintenance_begin("清空检查记录"):
            return self._err("正在执行其他维护任务（恢复/清库/删除/重建），请稍后重试")
        try:
            removed = 0
            external = 0
            for r in self._db.query("SELECT file_path FROM ass_files"):
                fp = r.get("file_path") or ""
                if not fp:
                    continue
                if self._owns_ass_copy(fp):
                    if arch.safe_unlink(fp, self._tmp_dir, exts=ASS_EXTENSIONS):
                        removed += 1
                else:
                    # 监控目录/媒体库里的原件：只删记录，不删文件
                    external += 1
            self._db.clear_ass()
            if external:
                detail = f"清理上传临时副本 {removed} 个；其余 {external} 条只删记录，监控目录/媒体库原字幕未动"
            else:
                detail = f"清理上传临时副本 {removed} 个"
            self._db.add_log(f"清空全部ASS检查记录（{detail}）", "warning")
            self._invalidate_missing_agg()
            return self._ok({"file_removed": removed}, "已清空")
        except Exception as err:
            return self._err(f"清空失败: {err}")
        finally:
            self._maintenance_end("清空检查记录")

    # ─── API：子集化 ─────────────────────────────────────
    def api_subset_index(self) -> Dict[str, Any]:
        """子集化状态：HarfBuzz 引擎 + fontTools 字体索引统计"""
        if not self._db_ok():
            return self._err("数据库未初始化")
        lib_dir_cfg = self.get_resource_or_config("lib_dir") or ""
        hb_ok, hb_info = self._hb_status()
        engine_ready, engine_name = self._subset_engine_ready()
        try:
            font_index = self._db.index_stats()
        except Exception:
            font_index = {}
        return self._ok(
            {
                "engine": engine_name,
                "engine_ready": engine_ready,
                "hb_ok": hb_ok,
                "hb_info": hb_info,
                "font_index": font_index,
                # 重建状态：UI 据此显示「正在重建（已处理 N/M）」，避免只看到「—」以为索引坏了
                "rebuilding": bool(self._index_rebuilding),
                "rebuild_progress": dict(self._index_progress) if self._index_rebuilding else {},
                "lib_dir": lib_dir_cfg,
            },
            "子集化状态",
        )

    def api_subset_rebuild_index(self, allow_incomplete: bool = False) -> Dict[str, Any]:
        """全部重建字体库索引：暂存表原子切换（非增量，日常入库仍走增量/减量）

        allow_incomplete=False（默认）：出现任何「结果不确定」的文件（权限/IO/解析
        异常）时不提交暂存，保留旧索引并返回原因；allow_incomplete=True 才允许
        在明确知晓的前提下提交不完整索引。
        """
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        lib_dir = self.get_resource_or_config("lib_dir") or ""
        if not lib_dir:
            return self._err("请先在设置中配置字体库目录（子集化字体来源）")
        if not self._scan_lock.acquire(blocking=False):
            return self._err("正在处理中，请等待当前任务完成")
        if not self._maintenance_begin("全部重建索引"):
            self._scan_lock.release()
            return self._err("正在执行其他维护任务（恢复/清库/删除/重建），请稍后重试")
        try:
            result = self._rebuild_font_index_impl(
                stats={
                    "ok": False,
                    "scanned": 0,
                    "indexed": 0,
                    "unchanged": 0,
                    "invalid": 0,
                    "failed": 0,
                    "failed_paths": [],
                    "removed": 0,
                    "hash_checked": 0,
                    "hash_mismatch": 0,
                    "error": "",
                },
                full=True,
                allow_incomplete=bool(allow_incomplete),
            )
            if not result.get("ok"):
                return self._err(f"重建索引失败: {result.get('error') or '未知错误'}")
            self._db.add_log(
                f"字体库已全部重建：重解析 {result['indexed']} 个文件、"
                f"跳过 {result['unchanged']}、清理 {result['removed']}（{lib_dir}）",
                "info",
            )
            return self._ok(
                {"engine": "harfbuzz", "font_index": self._db.index_stats()},
                "字体库已全部重建（逐文件重新解析）",
            )
        finally:
            self._maintenance_end("全部重建索引")
            self._scan_lock.release()

    def _rebuild_subset_index_silent(self) -> Tuple[bool, str]:
        """重建 fontTools 增量字体索引（尽力而为，不抛异常，失败仅返回错误信息）。

        字体归档/全量检查后调用，让新入库字体立即可被子集化引用；
        返回 (ok, msg)。调用方需自行持有 _scan_lock（或确认无并发冲突）。
        """
        try:
            hb_ok, hb_info = self._hb_status()
            if not hb_ok:
                return False, hb_info
            result = self._rebuild_font_index()
            if not result.get("ok"):
                return False, str(result.get("error") or "字体索引重建失败")
            if int(result.get("indexed") or 0) > 0:
                # 字体库新增/更新字体后：重检受影响的字幕，让已解决的缺失即时消失
                self._recheck_missing_after_library_change("字体库更新")
            return True, ""
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
        ready, why = self._subset_engine_ready()
        if not ready:
            return self._err(why)
        if not self._scan_lock.acquire(blocking=False):
            return self._err("全量子集化正在运行中，请等待本次完成后再试")
        if self._maintenance_active():
            self._scan_lock.release()
            return self._err("正在执行维护任务（恢复/清库/删除/重建），请稍后重试")
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
            stats: Dict[str, Any] = {"success": 0, "skipped": 0, "missing": 0, "error": 0, "missing_fonts": [], "file_status": {}, "out_files": []}
            watch_stats: Optional[Dict[str, Any]] = None
            for batch, src in ((manual_files, "manual"), (watch_files, "watch")):
                if not batch:
                    continue
                sub = self._run_subset_batch(batch, source=src)
                for k in ("success", "skipped", "missing", "error"):
                    stats[k] += sub.get(k, 0)
                stats["missing_fonts"].extend(sub.get("missing_fonts") or [])
                stats["file_status"].update(sub.get("file_status") or {})
                stats["out_files"].extend(sub.get("out_files") or [])
                if src == "watch":
                    watch_stats = sub
            # 处理完成：移除待处理记录；上传到临时目录的缓存源文件仅成功/跳过才清理，
            # 缺字体/失败（file_status=keep）保留供「重试失败」补字后再次处理
            keep_map = stats.get("file_status") or {}
            out_set = set(stats["out_files"] or [])
            for r in pending:
                try:
                    self._db.delete_subset_pending(r["id"])
                except Exception:
                    pass
                fp = Path(r.get("file_path") or "")
                if self._tmp_dir and _path_within(fp, Path(self._tmp_dir)):
                    # 覆盖模式成品==源文件路径：成品不可当临时源删（下载依赖它）
                    if keep_map.get(str(fp.resolve())) != "keep" and str(fp.resolve()) not in out_set:
                        arch.safe_unlink(fp, self._tmp_dir, exts=ASS_EXTENSIONS)
            self._db.add_log(
                f"全量子集化: 成功 {stats['success']}, 跳过 {stats['skipped']}, "
                f"缺字体 {stats['missing']}, 失败 {stats['error']}",
                "info",
            )
            # 手动上传是页面内的主动操作，不发系统通知；只有目录监控收集的字幕才推送
            # （后台监控/MP 入库走 _run_show_subset，仍照常通知）
            if watch_stats:
                self._notify_subset_result(watch_stats)
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
            # 与检查侧同一基准（fontTools 索引优先，回退字体库记录）
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
        files, notes = await self._receive_uploads(upload_files, ASS_EXTENSIONS, prefix="subset")
        done = []
        for entry in files:
            safe_name = entry["file_name"]
            tmp_path = Path(entry["path"])
            if not tmp_path.is_file():
                continue
            pid = self._db.add_subset_pending(safe_name, str(tmp_path), source="upload")
            done.append({"id": pid, "file_name": safe_name})
        if not done:
            msg = "没有可上传的字幕文件（需 .ass 后缀或 .zip 压缩包，且内容非空）"
            if notes:
                msg += "；" + "；".join(notes[:3])
            return self._err(msg)
        return self._ok(
            {"count": len(done), "items": done, "notes": notes},
            f"已加入待处理 {len(done)} 个字幕",
        )

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
                if self._tmp_dir and _path_within(fp, Path(self._tmp_dir)):
                    arch.safe_unlink(fp, self._tmp_dir, exts=ASS_EXTENSIONS)
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
                    if self._tmp_dir and _path_within(fp, Path(self._tmp_dir)):
                        arch.safe_unlink(fp, self._tmp_dir, exts=ASS_EXTENSIONS)
            self._db.clear_subset_pending()
            return self._ok({}, "已清空待处理")
        except Exception as err:
            return self._err(f"清空失败: {err}")

    def _subset_delete_roots(self, source: str = "") -> List[Path]:
        """可随记录删除产物的目录白名单。

        - inbound（MP 入库）：一律不允许删除（媒体库成品属于用户资产）
        - manual（上传）：临时目录
        - watch（监控）：临时/输出/ASS监控/子集监控目录
        - 旧记录无 source：只认插件自有的临时/输出目录（不按监控目录猜，避免
          用户把 subset_dir 配成媒体库根时误删媒体库字幕）
        """
        source = str(source or "")
        if source == "inbound":
            return []
        roots: List[Path] = []
        for value in (self._tmp_dir, self.get_resource_or_config("subset_out_dir") or ""):
            if value:
                roots.append(Path(value))
        if source == "watch":
            for key in ("ass_dir", "subset_dir"):
                value = self.get_resource_or_config(key) or ""
                if value:
                    roots.append(Path(value))
        return roots

    def _subset_out_deletable(self, out_path: str, source: str = "") -> bool:
        """子集化成成品文件是否可随记录删除：按记录来源身份判定，而不是按目录猜。

        inbound（媒体库）记录即使 out_file 恰好落在监控/输出目录，也一律不删；
        只有 manual/watch 来源（或旧记录且位于插件自有临时/输出目录）才允许删除。
        """
        if not out_path:
            return False
        try:
            p = Path(out_path)
            return any(_path_within(p, root) for root in self._subset_delete_roots(source))
        except Exception:
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
        source = str(row.get("source") or "")
        if not out or not self._subset_out_deletable(out, source):
            return
        roots = self._subset_delete_roots(source)
        arch.safe_unlink(out, *roots, exts=(".ass",))
        # 同行 <stem>_subsetted 备份夹：仅当夹子也在可删区域时删除，
        # 子集化在源目录生成该夹只是备份，随记录删除产物时一并清掉
        stem = out[:-4] if out.lower().endswith(".ass") else out
        sub = Path(stem + "_subsetted")
        if sub.is_dir() and self._subset_out_deletable(str(sub), source):
            try:
                shutil.rmtree(sub, ignore_errors=True)
            except Exception:
                pass
        # 输出目录/<剧名>/ 空文件夹清理
        self._prune_empty_show_dir(Path(out))

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
        ready, why = self._subset_engine_ready()
        if not ready:
            return self._err(why)
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
            st: Dict[str, Any] = {"success": 0, "skipped": 0, "missing": 0, "error": 0, "missing_fonts": [], "file_status": {}, "out_files": []}
            # 按来源拆两批：手动上传的重试不发系统通知，监控/入库来源仍推送
            manual_files: List[Path] = []
            monitor_files: List[Path] = []
            for p in files:
                if self._subset_source_kind(p, "retry") == "manual":
                    manual_files.append(p)
                else:
                    monitor_files.append(p)
            notify_st: Optional[Dict[str, Any]] = None
            for batch, is_manual in ((manual_files, True), (monitor_files, False)):
                if not batch:
                    continue
                sub = self._run_subset_batch(batch, source="retry")
                for k in ("success", "skipped", "missing", "error"):
                    st[k] += sub.get(k, 0)
                st["missing_fonts"].extend(sub.get("missing_fonts") or [])
                st["file_status"].update(sub.get("file_status") or {})
                st["out_files"].extend(sub.get("out_files") or [])
                if not is_manual:
                    notify_st = sub
            self._db.add_log(
                f"重试失败子集化: 重试 {len(files)} 个，成功 {st['success']}，缺字体 {st['missing']}，失败 {st['error']}",
                "info",
            )
            if notify_st:
                self._notify_subset_result(notify_st, scope="重试")
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
            # 与检查侧同一基准（fontTools 索引优先，回退字体库记录）：
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

    def _latest_missing_snapshots(self) -> List[Dict[str, Any]]:
        """每个字幕「最近一次检查批次」里仍缺失（missing/partial）的字形快照行。

        同一批检查的行共享 check_time；按批次取最新可避免字体已从字幕移除后
        旧快照仍被当作缺失。
        """
        try:
            rows = self._db.query(
                "SELECT g.ass_id, g.file_path, g.font_name, g.missing_codepoints, g.missing_chars, "
                "g.status, g.check_time FROM ass_missing_glyphs g "
                "JOIN ass_files a ON a.id = g.ass_id ORDER BY g.id"
            )
        except Exception:
            return []
        latest_time: Dict[Any, str] = {}
        for row in rows:
            latest_time[row.get("ass_id")] = row.get("check_time") or ""
        latest: Dict[Tuple[Any, str], Dict[str, Any]] = {}
        for row in rows:
            if (row.get("check_time") or "") != latest_time.get(row.get("ass_id")):
                continue
            key = normalize_font_key(row.get("font_name") or "")
            if key:
                latest[(row.get("ass_id"), key)] = row
        return [
            r for r in latest.values() if (r.get("status") or "") in ("missing", "partial")
        ]

    def _missing_glyph_targets(self) -> Dict[str, Dict[str, Any]]:
        """归一化字体名 → 缺失目标（字形级最新快照 + 旧口径名称兜底）。

        返回 {key: {"name": 展示名, "count": 受影响字幕数,
                    "codepoints": set[int], "chars": 缺失字符（去重截断）, "glyph": bool}}
        """
        targets: Dict[str, Dict[str, Any]] = {}
        coverage: Dict[str, set] = {}
        for row in self._latest_missing_snapshots():
            key = normalize_font_key(row.get("font_name") or "")
            if not key:
                continue
            cps, remain, remain_chars = self._snapshot_remaining(row, coverage)
            if cps and not remain:
                continue  # 字体库已覆盖全部缺失字符 → 不再是上传目标
            item = targets.get(key)
            if not item:
                item = {
                    "name": row.get("font_name") or key,
                    "count": 0,
                    "codepoints": set(),
                    "chars": "",
                    "glyph": True,
                }
                targets[key] = item
            item["count"] += 1
            item["codepoints"] |= remain if cps else cps
            item["chars"] += remain_chars if cps else (row.get("missing_chars") or "")
        # 旧口径兜底：没有字形快照的历史记录只按名称匹配（无字符约束）
        for key, value in self._ass_missing_agg_cached().items():
            if key in targets:
                continue
            targets[key] = {
                "name": value.get("name") or key,
                "count": int(value.get("count") or 0),
                "codepoints": set(),
                "chars": "",
                "glyph": False,
            }
        for item in targets.values():
            item["chars"] = "".join(dict.fromkeys(item["chars"]))[:80]
        return targets

    def _evaluate_font_for_targets(
        self,
        path: Path,
        targets: Dict[str, Dict[str, Any]],
        target_hint: str = "",
    ) -> Dict[str, Any]:
        """严格校验上传字体：同一 face 必须同时「名称命中缺失目标」且「真实覆盖缺失字符」。

        P1-4：逐 face 独立评估，绝不做「face 名称 + 另一 face 的 cmap」跨 face 拼接——
        TTC/OTC 里 face 0 名称匹配但缺字、face 1 有字符但名称不匹配时，文件整体必须被拒绝。
        历史记录缺少缺失码点明细（旧口径记录）时不能只凭名称放行：要求先重新检查字幕。

        返回 {"ok": bool, "reason": str, "matched": 展示名, "match_kind": name|manual,
              "matched_keys": [...], "affected_keys": [...], "covered_chars": str,
              "required_chars": str, "glyph": bool, "name": 字体内部名, "family": "",
              "sha256": str, "face_count": int, "face_index": int}
        """
        if not targets:
            return {"ok": False, "reason": "当前没有缺失字体，请先在「检查」页生成缺失列表"}
        try:
            inspection = inspect_font(path)
        except Exception as err:
            return {"ok": False, "reason": f"字体解析失败: {err}"}
        if not inspection.faces:
            return {"ok": False, "reason": inspection.error or "字体文件无法解析"}
        faces: List[Any] = []
        display = ""
        family = ""
        for face in inspection.faces:
            if face.status not in ("ok", "no_cmap"):
                continue
            try:
                keys = set(face.alias_keys())
            except Exception:
                keys = set()
            if not keys:
                continue
            faces.append((face, keys))
            if not display:
                display = face.display_name()
            if not family:
                family = face.family
        if not faces:
            return {"ok": False, "reason": "字体缺少可用的名称信息（name 表为空）"}
        hint_key = normalize_font_key(target_hint) if target_hint else ""
        if hint_key and hint_key not in targets:
            return {"ok": False, "reason": f"人工指定的目标「{target_hint}」不在当前缺失列表中"}
        match_kind = "manual" if hint_key else "name"

        best: Optional[Tuple[Tuple[int, int], str, set, Any]] = None
        matched_keys: List[str] = []       # 名称/别名命中的目标 key（不论是否覆盖字符）
        uncovered_keys: List[str] = []     # 名称命中但该 face 不覆盖任何缺失字符
        name_only_keys: List[str] = []     # 名称命中但目标无码点明细（未验证覆盖）
        if hint_key:
            # 人工指定目标：用户显式声明「这份字体用于补 X」，不再要求字体内部名等于 X；
            # 但覆盖验证不放松——仍要某个单一 face 真实覆盖该目标的缺失字符，
            # 且历史记录缺少码点明细时同样必须先重检（不能只凭人工指定放行）。
            matched_keys.append(hint_key)
            target = targets[hint_key]
            required = set(target.get("codepoints") or set())
            if not required:
                name_only_keys.append(hint_key)
            else:
                for face, _keys in faces:
                    covered = required & set(face.codepoints)
                    if not covered:
                        continue
                    score = (len(covered), int(target.get("count") or 0))
                    if best is None or score > best[0]:
                        best = (score, hint_key, covered, face)
                if best is None:
                    uncovered_keys.append(hint_key)
        else:
            for face, keys in faces:
                for key in keys:
                    if key not in targets:
                        continue
                    if key not in matched_keys:
                        matched_keys.append(key)
                    target = targets[key]
                    required = set(target.get("codepoints") or set())
                    if not required:
                        # 旧口径历史记录：没有缺失码点明细 → 不能视为已解决（要求先重检）
                        if key not in name_only_keys:
                            name_only_keys.append(key)
                        continue
                    covered = required & set(face.codepoints)
                    if not covered:
                        if key not in uncovered_keys:
                            uncovered_keys.append(key)
                        continue
                    score = (len(covered), int(target.get("count") or 0))
                    if best is None or score > best[0]:
                        best = (score, key, covered, face)
        if best is None:
            if name_only_keys:
                names = "、".join(
                    str(targets[k].get("name") or k) for k in name_only_keys[:3]
                )
                return {
                    "ok": False,
                    "reason": f"名称命中「{names}」但历史记录缺少缺失字符明细，无法验证字形覆盖，"
                    "请先在「检查」页重新检查相关字幕后再上传",
                    "name": display,
                    "family": family,
                    "matched_keys": matched_keys,
                }
            if uncovered_keys:
                key = uncovered_keys[0]
                required_chars = targets[key].get("chars") or ""
                return {
                    "ok": False,
                    "reason": "名称匹配但未覆盖任何缺失字符"
                    + (f"（缺失字符: {required_chars}）" if required_chars else ""),
                    "name": display,
                    "family": family,
                    "matched_keys": matched_keys,
                }
            return {
                "ok": False,
                "reason": "与当前缺失字体不匹配（可在页面选择目标字体后重试）",
                "name": display,
                "family": family,
            }
        _score, chosen, covered, chosen_face = best
        target = targets[chosen]
        covered_chars = "".join(
            chr(cp) for cp in sorted(covered) if cp >= 0x20 and not 0x7F <= cp <= 0x9F
        )
        # affected_keys：所有名称命中同一目标的 key（别名口径），供归档后统一失效/重检
        affected = set(matched_keys) | set(name_only_keys) | set(uncovered_keys)
        return {
            "ok": True,
            "matched": target.get("name") or target_hint or chosen,
            "match_kind": match_kind,
            "matched_keys": [chosen],
            "affected_keys": sorted(affected),
            "covered": sorted(covered),
            "covered_chars": covered_chars[:80],
            "required_chars": target.get("chars") or "",
            "glyph": bool(target.get("codepoints")),
            "name": display,
            "family": family,
            "sha256": inspection.sha256,
            "face_count": len(inspection.faces),
            # 通过的单一 face：归档/子集化必须沿用同一 face，禁止跨 face 拼接
            "face_index": int(getattr(chosen_face, "face_index", 0) or 0),
        }

    def _recheck_affected_ass(self, keys: Iterable[str], reason: str = "") -> Dict[str, int]:
        """重检受某字体影响的 ASS 记录（逐字形快照 + 名称缺失 + 引用清单），返回统计。

        三条来源缺一不可：
        - 逐字形快照（ass_missing_glyphs）中 key 仍为 missing/partial；
        - ass_files.missing_fonts 里的旧口径名称缺失；
        - ass_files.all_fonts 里「引用过该字体」的记录——字体被删除时，之前已解决的
          记录不会再出现在任何缺失清单里，只能靠引用清单找回来重检。
        """
        normalized = {normalize_font_key(k) for k in keys if k}
        result = {"checked": 0, "ok": 0, "missing": 0, "failed": 0}
        if not normalized:
            return result
        paths: set = set()
        try:
            latest: Dict[Tuple[Any, str], Dict[str, Any]] = {}
            for row in self._db.query(
                "SELECT ass_id, file_path, font_name, status FROM ass_missing_glyphs ORDER BY id"
            ):
                key = normalize_font_key(row.get("font_name") or "")
                if key in normalized:
                    latest[(row.get("ass_id"), key)] = row
            for row in latest.values():
                if row.get("file_path"):
                    paths.add(str(row["file_path"]))
            for row in self._db.query(
                "SELECT file_path, missing_fonts, all_fonts FROM ass_files"
            ):
                file_path = str(row.get("file_path") or "")
                if not file_path:
                    continue
                matched = False
                for field in ("missing_fonts", "all_fonts"):
                    try:
                        names = json.loads(row.get(field) or "[]")
                    except Exception:
                        names = []
                    if any(normalize_font_key(str(n)) in normalized for n in names or []):
                        matched = True
                        break
                if matched:
                    paths.add(file_path)
        except Exception:
            pass
        for path in paths:
            p = Path(path)
            if not p.is_file():
                continue
            out = self._check_ass_file(p, source="manual")
            result["checked"] += 1
            if not out:
                result["failed"] += 1
            elif out.get("status") == "ok":
                result["ok"] += 1
            else:
                result["missing"] += 1
        if result["checked"]:
            self._invalidate_missing_agg()
            if reason:
                self._db.add_log(
                    f"已重检 {result['checked']} 个字幕（{reason}）：完整 {result['ok']}，仍缺 {result['missing']}",
                    "info",
                )
        return result

    def _recheck_missing_after_library_change(self, reason: str = "字体库新增字体") -> Dict[str, int]:
        """字体库新增/更新字体后，重检所有仍被标记缺失的字幕（源文件存在时）。

        与缺失字体页的归类流程同口径：补齐字体后字幕状态/逐字符快照即时更新，
        不再需要手动重新检查。源文件已不存在的上传记录由聚合侧的实时扣除兜底。
        """
        try:
            names = self._db.all_missing_font_names()
        except Exception:
            names = []
        if not names:
            self._invalidate_missing_agg()
            return {"checked": 0, "ok": 0, "missing": 0, "failed": 0}
        return self._recheck_affected_ass(names, reason=reason)

    def api_missing_summary(self) -> Dict[str, Any]:
        """缺失字体汇总：check=检查页检测的缺失（含逐字符明细），subset=子集化因缺字体跳过的"""
        if not self._db_ok():
            return self._err("数据库未初始化")
        try:
            targets = self._missing_glyph_targets()
            agg = self._ass_missing_agg_cached()
            check = []
            for key, value in agg.items():
                target = targets.get(key) or {}
                check.append(
                    {
                        "name": value["name"],
                        "count": value["count"],
                        "key": key,
                        "chars": target.get("chars", ""),
                        "glyph": bool(target.get("glyph")),
                        "codepoints_count": len(target.get("codepoints") or ()),
                    }
                )
            check.sort(key=lambda x: (-x["count"], x["name"]))
            subset = self._subset_missing_agg()
            hb_ok, hb_info = self._hb_status()
            try:
                index_faces = int(self._db.index_stats().get("faces") or 0)
            except Exception:
                index_faces = 0
            return self._ok(
                {
                    "check": check,
                    "subset": subset,
                    "lib_dir": self.get_resource_or_config("lib_dir") or "",
                    "hb_ok": hb_ok,
                    "hb_info": hb_info,
                    "engine": "harfbuzz",
                    "index_faces": index_faces,
                },
                "缺失字体汇总",
            )
        except Exception as err:
            return self._err(f"获取缺失字体汇总失败: {err}")

    def api_missing_uploads(self) -> Dict[str, Any]:
        """已上传待归类的字体列表（顺带清理超时未归类项）"""
        self._prune_missing_uploads()
        lst = []
        with self._missing_uploads_lock:
            items = list(self._missing_uploads.items())
        for path, item in items:
            lst.append(
                {
                    "path": path,
                    "file_name": item.get("file_name", ""),
                    "name": item.get("name", ""),
                    "family": item.get("family", ""),
                    "vendor": item.get("vendor", "未知厂商"),
                    "file_size": item.get("file_size", 0),
                    "matched": item.get("matched", ""),
                    "match_kind": item.get("match_kind", ""),
                    "covered_chars": item.get("covered_chars", ""),
                    "required_chars": item.get("required_chars", ""),
                }
            )
        return self._ok(lst)

    async def api_missing_upload(self, request: Request) -> Dict[str, Any]:
        """缺失字体页上传字体：严格校验（名称/别名命中缺失目标且覆盖缺失字符）"""
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
        scan_mode = "internal"  # fontTools 为唯一权威解析口径
        target_hint = ""
        try:
            raw_target = form.get("target")
            if isinstance(raw_target, str):
                target_hint = raw_target.strip()
        except Exception:
            pass
        targets = self._missing_glyph_targets()
        files, notes = await self._receive_uploads(upload_files, FONT_EXTENSIONS, prefix="missing")
        done: List[Dict[str, Any]] = []
        rejected: List[Dict[str, str]] = []

        def _missing_upload_sync() -> None:
            """校验/解析字体是同步重活：放线程池，避免阻塞事件循环。"""
            for entry in files:
                safe_name = entry["file_name"]
                tmp_path = Path(entry["path"])
                if not tmp_path.is_file():
                    continue
                verdict = self._evaluate_font_for_targets(tmp_path, targets, target_hint)
                if not verdict.get("ok"):
                    arch.safe_unlink(tmp_path, self._tmp_dir, exts=FONT_EXTENSIONS)
                    rejected.append(
                        {"file_name": safe_name, "reason": str(verdict.get("reason") or "不匹配")}
                    )
                    continue
                try:
                    meta = parse_font_metadata(tmp_path, scan_mode=scan_mode, filename_hint=Path(safe_name).stem)
                except Exception:
                    meta = {
                        "name": verdict.get("name") or Path(safe_name).stem,
                        "family": verdict.get("family") or Path(safe_name).stem,
                        "vendor": "未知厂商",
                        "designer": "",
                    }
                item = {
                    "path": str(tmp_path),
                    "file_name": safe_name,
                    "name": meta.get("name", "") or verdict.get("name") or Path(safe_name).stem,
                    "family": meta.get("family", "") or verdict.get("family") or Path(safe_name).stem,
                    "vendor": meta.get("vendor", "未知厂商"),
                    "designer": meta.get("designer", ""),
                    "file_size": entry.get("size", 0),
                    "matched": verdict.get("matched", ""),
                    "match_kind": verdict.get("match_kind", "name"),
                    "matched_keys": verdict.get("affected_keys") or verdict.get("matched_keys") or [],
                    "covered_chars": verdict.get("covered_chars", ""),
                    "required_chars": verdict.get("required_chars", ""),
                    "sha256": verdict.get("sha256", ""),
                    # 严格校验通过的单一 face（P1-4）：归档/子集化沿用，不允许跨 face 拼接
                    "face_index": int(verdict.get("face_index") or 0),
                }
                if item["match_kind"] == "manual":
                    try:
                        self._db.set_manual_font_mapping(
                            item["name"],
                            item["matched"],
                            file_sha256=item["sha256"],
                            note="上传时人工指定目标",
                        )
                    except Exception:
                        pass
                    self._db.add_log(
                        f"人工映射: {safe_name}（{item['name']}）→ 缺失字体「{item['matched']}」",
                        "warning",
                    )
                item["created_at"] = time.time()
                with self._missing_uploads_lock:
                    self._missing_uploads[str(tmp_path)] = item
                try:
                    self._db.add_missing_upload(item)
                except Exception:
                    pass
                done.append(item)

        await asyncio.to_thread(_missing_upload_sync)
        if not done:
            if rejected:
                detail = "；".join(f"{r['file_name']}: {r['reason']}" for r in rejected[:3])
                return self._err(f"没有字体通过缺失校验（{detail}）")
            if not targets:
                return self._err("当前没有缺失字体，请先在「检查」页检查字幕生成缺失列表")
            return self._err("没有可上传的字体文件（需字体后缀或 .zip 压缩包，且内容非空）")
        message = f"已上传 {len(done)} 个字体（已通过缺失匹配校验），可点击「归类」入库"
        if rejected:
            message += f"；{len(rejected)} 个未通过校验"
        return self._ok(
            {"count": len(done), "items": done, "rejected": rejected, "notes": notes},
            message,
        )

    def _load_missing_uploads(self) -> int:
        """启动/重载时恢复缺失字体上传缓冲（持久化在 missing_uploads 表）。

        文件已不存在（临时目录被清/用户手动删）的记录一并清理，避免幽灵条目。
        """
        if self._db is None:
            return 0
        try:
            rows = self._db.list_missing_uploads()
        except Exception:
            return 0
        loaded = 0
        for row in rows:
            path = str(row.get("path") or "")
            if not path:
                continue
            if not Path(path).is_file():
                try:
                    self._db.delete_missing_upload(path)
                except Exception:
                    pass
                continue
            try:
                matched_keys = json.loads(row.get("matched_keys") or "[]")
            except Exception:
                matched_keys = []
            item = {
                "path": path,
                "file_name": row.get("file_name", ""),
                "name": row.get("name", ""),
                "family": row.get("family", ""),
                "vendor": row.get("vendor", "") or "未知厂商",
                "designer": row.get("designer", ""),
                "file_size": int(row.get("file_size") or 0),
                "matched": row.get("matched", ""),
                "match_kind": row.get("match_kind", ""),
                "matched_keys": matched_keys if isinstance(matched_keys, list) else [],
                "covered_chars": row.get("covered_chars", ""),
                "required_chars": row.get("required_chars", ""),
                "sha256": row.get("sha256", ""),
                "created_at": float(row.get("created_at") or 0),
                "face_index": int(row.get("face_index") or 0),
            }
            with self._missing_uploads_lock:
                self._missing_uploads[path] = item
            loaded += 1
        return loaded

    def _prune_missing_uploads(self) -> int:
        """清理超时未归类的上传缓冲（文件 + 持久化记录），避免无限堆积。"""
        now = time.time()
        expired: List[str] = []
        with self._missing_uploads_lock:
            for path, item in list(self._missing_uploads.items()):
                born = float(item.get("created_at") or 0)
                if not born or now - born > float(self._missing_uploads_ttl):
                    expired.append(path)
        for path in expired:
            self._drop_missing_upload(path)
        return len(expired)

    def _drop_missing_upload(self, path: str) -> Optional[Dict[str, Any]]:
        """移除一条未入库上传：清缓冲、持久化记录、临时文件与对应人工映射审计记录。"""
        with self._missing_uploads_lock:
            item = self._missing_uploads.pop(path, None)
        try:
            self._db.delete_missing_upload(str(path))
        except Exception:
            pass
        if item:
            arch.safe_unlink(item.get("path") or path, self._tmp_dir, exts=FONT_EXTENSIONS)
            if item.get("match_kind") == "manual":
                try:
                    self._db.delete_manual_font_mapping_pair(
                        item.get("name", ""), item.get("matched", "")
                    )
                except Exception:
                    pass
        return item

    def api_missing_uploads_clear(self) -> Dict[str, Any]:
        """清除已上传未归类的字体（删除临时文件）"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        with self._missing_uploads_lock:
            paths = list(self._missing_uploads.keys())
        for path in paths:
            self._drop_missing_upload(path)
        return self._ok({}, "已清除上传的字体")

    def api_missing_upload_remove(self, path: str = "") -> Dict[str, Any]:
        """删除单条已上传待归类的字体（仅删除临时文件和内存记录，不影响字体库）"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not path:
            return self._err("参数错误")
        with self._missing_uploads_lock:
            exists = path in self._missing_uploads
        if not exists:
            return self._err("未找到该字体记录")
        self._drop_missing_upload(path)
        return self._ok({}, "已移除")

    async def api_missing_remap(self, request: Request) -> Dict[str, Any]:
        """已上传字体人工映射到指定缺失目标，并复核字符覆盖（审计入库）。"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        try:
            body = await request.json() if hasattr(request, "json") else {}
        except Exception:
            body = {}
        path = body.get("path") or ""
        target = str(body.get("target") or "").strip()
        item = self._missing_uploads.get(path)
        if not item:
            return self._err("上传记录不存在或已失效，请重新上传")
        if not target:
            return self._err("请选择要映射的缺失目标字体")
        src = Path(path)
        if not src.is_file():
            return self._err("临时字体文件不存在，请重新上传")
        targets = self._missing_glyph_targets()
        verdict = await asyncio.to_thread(self._evaluate_font_for_targets, src, targets, target)
        if not verdict.get("ok"):
            return self._err(str(verdict.get("reason") or "映射校验失败"))
        old_matched = str(item.get("matched") or "")
        item.update(
            {
                "matched": verdict.get("matched", target),
                "match_kind": "manual",
                "matched_keys": verdict.get("affected_keys") or [normalize_font_key(target)],
                "covered_chars": verdict.get("covered_chars", ""),
                "required_chars": verdict.get("required_chars", ""),
                "sha256": verdict.get("sha256", item.get("sha256", "")),
            }
        )
        try:
            if old_matched and old_matched != item["matched"]:
                self._db.delete_manual_font_mapping_pair(item.get("name", ""), old_matched)
            self._db.set_manual_font_mapping(
                item.get("name", "") or verdict.get("name", ""),
                item["matched"],
                file_sha256=item.get("sha256", ""),
                note="手动改派缺失目标",
            )
            self._db.add_missing_upload(item)
        except Exception:
            pass
        self._db.add_log(
            f"人工映射: {item.get('file_name', '')}（{item.get('name', '')}）→ 缺失字体「{item['matched']}」",
            "warning",
        )
        return self._ok(item, f"已映射到「{item['matched']}」，覆盖字符：{item.get('covered_chars') or '（名称级）'}")

    def api_missing_mappings(self) -> Dict[str, Any]:
        """人工映射审计列表"""
        if not self._db_ok():
            return self._ok([])
        try:
            return self._ok(self._db.list_manual_font_mappings())
        except Exception as err:
            return self._err(f"读取人工映射失败: {err}")

    def api_missing_mapping_delete(self, id: int = 0) -> Dict[str, Any]:
        """删除一条人工映射审计记录"""
        if not self._db_ok():
            return self._err("数据库未初始化")
        if not id:
            return self._err("缺少映射ID")
        try:
            self._db.delete_manual_font_mapping(int(id))
            return self._ok({}, "已删除")
        except Exception as err:
            return self._err(f"删除失败: {err}")

    def api_missing_classify(self) -> Dict[str, Any]:
        """归类：把已上传的字体全部归档入库（同名跳过不覆盖）→ 刷新字体索引 → 通知"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._db_ok():
            return self._err("数据库未初始化")
        lib_dir = self.get_resource_or_config("lib_dir") or ""
        if not lib_dir:
            return self._err("请先在设置中配置字体库目录（归档落点）")
        with self._missing_uploads_lock:
            items = list(self._missing_uploads.items())
        if not items:
            return self._err("还没有上传的字体，请先上传")
        if not self._scan_lock.acquire(blocking=False):
            return self._err("正在处理中，请等待当前任务完成")
        try:
            ok_count = 0
            failed: List[str] = []
            index_failed: List[str] = []
            affected: set = set()
            targets = self._missing_glyph_targets()
            for tmp_path, item in items:
                try:
                    src = Path(tmp_path)
                    if not src.is_file():
                        continue
                    # 入库前复核：仍须命中缺失目标且覆盖缺失字符（人工映射按其目标复核）
                    hint = item.get("matched", "") if item.get("match_kind") == "manual" else ""
                    verdict = self._evaluate_font_for_targets(src, targets, hint)
                    if not verdict.get("ok"):
                        failed.append(f"{item.get('file_name', '')}（{verdict.get('reason') or '未通过缺失校验'}）")
                        continue
                    affected.update(verdict.get("affected_keys") or [])
                    vendor = safe_filename_component(
                        str(item.get("vendor") or "未知厂商"), "未知厂商"
                    )
                    dest_dir = Path(lib_dir) / vendor
                    base = safe_filename_component(
                        str(item.get("name") or Path(item.get("file_name", "font")).stem)
                    )
                    # 按格式分子文件夹归档：字体库/厂商/格式/基础名.后缀
                    fmt_dir = dest_dir / _font_subdir_name(src.suffix)
                    existing = _dest_exists_recursive(dest_dir, base, src.suffix)
                    if existing and _files_identical(src, existing):
                        # 库内已有完全相同的文件：清理上传缓冲（含持久化记录），避免条目永久卡在列表
                        failed.append(f"{item.get('file_name', '')}（字体库已存在相同文件 {existing.name}）")
                        with self._missing_uploads_lock:
                            self._missing_uploads.pop(tmp_path, None)
                        try:
                            self._db.delete_missing_upload(tmp_path)
                        except Exception:
                            pass
                        arch.safe_unlink(tmp_path, self._tmp_dir, exts=FONT_EXTENSIONS)
                        continue
                    if existing:
                        # 同名但内容不同：另存 -2/-3，不覆盖旧版也不卡住条目
                        base = _unique_archive_base(self._dest_names_for(dest_dir), base, src.suffix)
                        self._db.add_log(
                            f"缺失字体 {item.get('file_name', '')} 与库内 {existing.name} 同名但内容不同，另存为 {base}{src.suffix}",
                            "warning",
                        )
                    try:
                        fmt_dir.mkdir(parents=True, exist_ok=True)
                    except Exception:
                        pass
                    dest = fmt_dir / f"{base}{src.suffix}"
                    if not _path_within(dest, Path(lib_dir)):
                        failed.append(f"{item.get('file_name', '')}（目标越界，拒绝归档）")
                        continue
                    src_size = src.stat().st_size
                    tmp_dest = fmt_dir / f".{dest.name}.tmp-{uuid.uuid4().hex[:8]}"
                    try:
                        shutil.copy2(str(src), str(tmp_dest))
                        written = tmp_dest.stat().st_size
                        if written != src_size:
                            raise RuntimeError(f"写入大小不一致（源 {src_size}，目标 {written}）")
                        os.replace(str(tmp_dest), str(dest))
                    except Exception:
                        try:
                            tmp_dest.unlink(missing_ok=True)
                        except Exception:
                            pass
                        raise
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
                    if not self._index_font_path(dest):
                        index_failed.append(dest.name)
                    with self._missing_uploads_lock:
                        self._missing_uploads.pop(tmp_path, None)
                    try:
                        self._db.delete_missing_upload(tmp_path)
                    except Exception:
                        pass
                    arch.safe_unlink(tmp_path, self._tmp_dir, exts=FONT_EXTENSIONS)
                    ok_count += 1
                except Exception as err:
                    failed.append(f"{item.get('file_name', '')}（{err}）")
            # 入库时已按文件写入 fontTools 增量索引；逐文件检查结果，索引失败要在通知里如实提示
            idx_ok = not index_failed
            idx_msg = self._short_names(index_failed, 5) if index_failed else ""
            # 逐字符解决复核：重检受本次入库影响的字幕，缺失标记随之消除
            recheck = self._recheck_affected_ass(affected, reason="缺失字体入库") if ok_count else {
                "checked": 0,
                "ok": 0,
                "missing": 0,
                "failed": 0,
            }
            self._db.add_log(
                f"缺失字体归类: 入库 {ok_count} 个, 跳过/失败 {len(failed)} 个", "info"
            )
            # 通知：入库结果 + 复核结果
            if ok_count and self.get_resource_or_config("notify_enabled"):
                lines = [f"✅ 缺失字体已入库 {ok_count} 个"]
                if recheck["checked"]:
                    lines.append(
                        f"已重检受影响字幕 {recheck['checked']} 个：完整 {recheck['ok']}，仍缺 {recheck['missing']}"
                    )
                if idx_ok:
                    lines.append("索引已自动刷新，请回到「子集化」页重新运行")
                elif idx_msg:
                    lines.append(f"⚠ 索引刷新失败：{idx_msg[:100]}")
                self._notify("字体分类管家：缺失字体入库", "\n".join(lines))
            return self._ok(
                {
                    "classified": ok_count,
                    "failed": failed,
                    "index_ok": idx_ok,
                    "recheck": recheck,
                },
                f"已入库 {ok_count} 个字体"
                + (
                    f"，已重检 {recheck['checked']} 个字幕（完整 {recheck['ok']}，仍缺 {recheck['missing']}）"
                    if recheck["checked"]
                    else ""
                )
                + ("，索引已刷新，可回到「子集化」页重新运行" if idx_ok else ""),
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
        Q3 修复：subsetted 判定走 (mtime_ns, size) 签名缓存（_ass_is_subsetted），
        不再对每条字幕 read_bytes 整个文件；调用方走 _ass_missing_agg_cached TTL 缓存。
        """
        agg: Dict[str, Dict[str, Any]] = {}
        glyph_paths: set = set()
        coverage: Dict[str, set] = {}
        # 字形级快照优先：名称在库但字符未覆盖同样计入缺失；
        # 按当前字体库字符覆盖实时扣除——字体库那边补齐字体后，这里立即不再显示
        for row in self._latest_missing_snapshots():
            key = normalize_font_key(row.get("font_name") or "")
            if not key:
                continue
            fp = row.get("file_path") or ""
            if fp:
                glyph_paths.add(fp)
                try:
                    if self._ass_is_subsetted(fp):
                        continue
                except Exception:
                    pass
            cps, remain, _chars = self._snapshot_remaining(row, coverage)
            if cps and not remain:
                continue  # 当前字体库已覆盖全部缺失字符 → 已解决
            if key in agg:
                agg[key]["count"] += 1
            else:
                agg[key] = {"name": row.get("font_name") or key, "count": 1}
        try:
            families, _fmatch = self._lib_font_keys()  # 与检查列表同口径（索引优先，回退字体库记录）
            for r in self._db.query("SELECT all_fonts, file_path FROM ass_files WHERE all_fonts != '[]'"):
                # 已内嵌（子集化）字幕自带字体，不参与缺失修复聚合
                fp = r.get("file_path") or ""
                if fp and fp in glyph_paths:
                    continue  # 该字幕已按字形级口径统计
                try:
                    if fp and self._ass_is_subsetted(fp):
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
        agg = self._ass_missing_agg_cached()
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
        target_hint = ""
        try:
            raw_target = form.get("target")
            if isinstance(raw_target, str):
                target_hint = raw_target.strip()
        except Exception:
            pass
        targets = self._missing_glyph_targets()
        files, notes = await self._receive_uploads(upload_files, FONT_EXTENSIONS, prefix="missingfix")
        scan_mode = "internal"  # fontTools 为唯一权威解析口径
        accepted: List[Dict[str, Any]] = []
        rejected: List[Dict[str, str]] = []

        def _verify_sync() -> None:
            """校验/解析字体是同步重活：放线程池，避免阻塞事件循环。"""
            for entry in files:
                safe_name = entry["file_name"]
                tmp_path = Path(entry["path"])
                if not tmp_path.is_file():
                    continue
                verdict = self._evaluate_font_for_targets(tmp_path, targets, target_hint)
                if not verdict.get("ok"):
                    arch.safe_unlink(tmp_path, self._tmp_dir, exts=FONT_EXTENSIONS)
                    rejected.append(
                        {"file_name": safe_name, "reason": str(verdict.get("reason") or "不匹配")}
                    )
                    continue
                try:
                    meta = parse_font_metadata(tmp_path, scan_mode=scan_mode, filename_hint=Path(safe_name).stem)
                except Exception:
                    meta = {
                        "name": verdict.get("name") or Path(safe_name).stem,
                        "family": verdict.get("family") or Path(safe_name).stem,
                        "vendor": "未知厂商",
                        "designer": "",
                    }
                item = {
                    "path": str(tmp_path),
                    "file_name": safe_name,
                    "name": meta.get("name", "") or verdict.get("name") or Path(safe_name).stem,
                    "family": meta.get("family", "") or verdict.get("family") or Path(safe_name).stem,
                    "vendor": meta.get("vendor", "未知厂商"),
                    "designer": meta.get("designer", ""),
                    "file_size": entry.get("size", 0),
                    "matched": verdict.get("matched", ""),
                    "match_kind": verdict.get("match_kind", "name"),
                    "matched_keys": verdict.get("affected_keys") or verdict.get("matched_keys") or [],
                    "covered_chars": verdict.get("covered_chars", ""),
                    "required_chars": verdict.get("required_chars", ""),
                    "sha256": verdict.get("sha256", ""),
                    # 严格校验通过的单一 face（P1-4）：归档/子集化沿用，不允许跨 face 拼接
                    "face_index": int(verdict.get("face_index") or 0),
                }
                if item["match_kind"] == "manual":
                    try:
                        self._db.set_manual_font_mapping(
                            item["name"], item["matched"], file_sha256=item["sha256"], note="检查页人工指定目标"
                        )
                    except Exception:
                        pass
                item["created_at"] = time.time()
                with self._missing_uploads_lock:
                    self._missing_uploads[str(tmp_path)] = item
                try:
                    self._db.add_missing_upload(item)
                except Exception:
                    pass
                accepted.append(item)
                self._db.add_log(
                    f"缺失字体上传待入库: {safe_name} → {item['matched']}"
                    + (f"（覆盖 {item['covered_chars']}）" if item["covered_chars"] else ""),
                    "info",
                )

        await asyncio.to_thread(_verify_sync)
        if not accepted:
            if rejected:
                detail = "；".join(f"{r['file_name']}: {r['reason']}" for r in rejected[:3])
                return self._err(f"字体未通过缺失校验（{detail}）")
            if not targets:
                return self._err("当前没有缺失字体，请先对字幕执行「检查」生成缺失列表")
            return self._err("没有可上传的字体文件（需字体后缀或 .zip 压缩包，且内容非空）")
        first = dict(accepted[0])
        first.update(
            {"count": len(accepted), "items": accepted, "rejected": rejected, "notes": notes}
        )
        message = f"已识别 {len(accepted)} 个缺失字体，点击「入库」加入字体库"
        if rejected:
            message += f"；{len(rejected)} 个未通过校验"
        return self._ok(first, message)

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
        with self._missing_uploads_lock:
            item = self._missing_uploads.get(path)
        if not item:
            return self._err("上传记录不存在或已失效，请重新上传")
        lib_dir = self.get_resource_or_config("lib_dir") or ""
        if not lib_dir:
            return self._err("请先在设置中配置字体库目录")
        src = Path(path)
        if not src.is_file():
            self._drop_missing_upload(path)
            return self._err("临时字体文件不存在，请重新上传")
        # 复核：该字体仍处于缺失名单，且覆盖至少一个缺失字符
        targets = self._missing_glyph_targets()
        hint = item.get("matched", "") if item.get("match_kind") == "manual" else ""
        verdict = await asyncio.to_thread(self._evaluate_font_for_targets, src, targets, hint)
        if not verdict.get("ok"):
            # 校验失败不销毁用户上传：保留缓冲与临时文件，用户可改派目标或手动取消
            return self._err(f"该字体已不再缺失或未通过校验：{verdict.get('reason') or '无法重复入库'}")
        matched = verdict.get("matched") or item.get("matched", "")
        affected = verdict.get("affected_keys") or item.get("matched_keys") or []
        try:
            dest_dir = Path(lib_dir) / safe_filename_component(
                str(item.get("vendor") or "未知厂商"), "未知厂商"
            )
            base = safe_filename_component(
                str(item.get("name") or Path(item.get("file_name", "font")).stem)
            )
            # 按格式分子文件夹归档：字体库/厂商/格式/基础名.后缀
            fmt_dir = dest_dir / _font_subdir_name(src.suffix)
            existing = _dest_exists_recursive(dest_dir, base, src.suffix)
            if existing and _files_identical(src, existing):
                # 库内已有完全相同的字体：清理上传缓冲（含持久化记录），避免条目永久卡在列表
                with self._missing_uploads_lock:
                    self._missing_uploads.pop(path, None)
                try:
                    self._db.delete_missing_upload(path)
                except Exception:
                    pass
                arch.safe_unlink(src, self._tmp_dir, exts=FONT_EXTENSIONS)
                return self._err(f"字体库已存在相同字体 {existing.name}，无需重复入库（已清理上传缓存）")
            if existing:
                # 同名但内容不同：另存 -2/-3，不覆盖旧版
                base = _unique_archive_base(self._dest_names_for(dest_dir), base, src.suffix)
                self._db.add_log(
                    f"缺失字体 {item.get('file_name', '')} 与库内 {existing.name} 同名但内容不同，另存为 {base}{src.suffix}",
                    "warning",
                )
            try:
                fmt_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            dest = fmt_dir / f"{base}{src.suffix}"
            if not _path_within(dest, Path(lib_dir)):
                return self._err("目标路径越界，拒绝归档")

            def _land() -> str:
                """原子落盘 + 大小校验；同步磁盘 IO 放线程池，别占住事件循环。"""
                src_size = src.stat().st_size
                tmp_dest = fmt_dir / f".{dest.name}.tmp-{uuid.uuid4().hex[:8]}"
                try:
                    shutil.copy2(str(src), str(tmp_dest))
                    written = tmp_dest.stat().st_size
                    if written != src_size:
                        raise RuntimeError(f"写入大小不一致（源 {src_size}，目标 {written}）")
                    os.replace(str(tmp_dest), str(dest))
                except Exception:
                    try:
                        tmp_dest.unlink(missing_ok=True)
                    except Exception:
                        pass
                    raise
                return str(dest)

            await asyncio.to_thread(_land)
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
            # 写库失败：回滚刚写入的字体文件，保留上传缓存供重试
            try:
                dest.unlink(missing_ok=True)
            except Exception:
                pass
            return self._err(f"写库失败: {err}")
        await asyncio.to_thread(self._index_font_path, dest)
        with self._missing_uploads_lock:
            self._missing_uploads.pop(path, None)
        try:
            self._db.delete_missing_upload(path)
        except Exception:
            pass
        arch.safe_unlink(src, self._tmp_dir, exts=FONT_EXTENSIONS)
        recheck = await asyncio.to_thread(self._recheck_affected_ass, affected, f"入库 {matched}")
        self._invalidate_missing_agg()
        self._db.add_log(f"缺失字体入库: {dest.name}（匹配缺失 {matched}）", "info")
        return self._ok(
            {"path": path, "name": dest.name, "matched": matched, "recheck": recheck},
            f"「{matched}」已入库，缺失标记自动消除"
            + (
                f"；已重检 {recheck['checked']} 个字幕（完整 {recheck['ok']}，仍缺 {recheck['missing']}）"
                if recheck["checked"]
                else ""
            ),
        )

    async def api_ass_missing_cancel(self, request: Request) -> Dict[str, Any]:
        """取消缺失字体上传（删除暂存文件）"""
        try:
            body = await request.json() if hasattr(request, "json") else {}
        except Exception:
            body = {}
        path = body.get("path") or ""
        self._drop_missing_upload(path)
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
        missing_details: List[Dict[str, Any]] = []
        glyph_result = None
        check_engine = "fonttools"
        unverified: List[str] = []
        # 字形级检测优先：字体名存在但 cmap 不覆盖实际字符也算缺失；
        # 已内嵌字体的字幕自带字体，跳过检测（与旧口径一致）
        if subsetted:
            check_engine = "embedded"
        else:
            glyph_result = self._glyph_check(raw)
        if glyph_result is not None:
            missing = list(glyph_result.missing_names)
            missing_details = [item.to_dict() for item in glyph_result.fonts]
            unverified = list(glyph_result.unverified_names)
            # 字体引用清单以字形解析为准：旧名称解析对复杂 ASS（\fn/\r/绘图/逗号文本）会切出垃圾名
            all_fonts = [item.name for item in glyph_result.fonts]
        else:
            # 索引不可用（库目录未配置/字体库为空/解析异常）时回退旧口径：只判字体名是否存在。
            # P1-6：名称存在 ≠ 字形完整，此路径的结果只能标为「未验证」（partial_check），
            # 不能把「名字在库里」当成「字体完整」展示。
            check_engine = "name-only"
            fam_keys, _fmatch = self._lib_font_keys()
            # 缺失清单按归一化 key 去重（@竖排变体与本体同 key，只算一次），保留首个原始名
            seen: set = set()
            missing = []
            for f in all_fonts:
                k = normalize_font_key(f)
                if not k or k in seen:
                    continue
                seen.add(k)
                if k not in fam_keys:
                    missing.append(f)
            if not missing and all_fonts:
                unverified = list(all_fonts)
        # 已内嵌（子集化）字幕自带字体：播放不依赖字体库，不再报缺失
        if subsetted and missing:
            missing = []
        if missing:
            status = "missing"
        elif subsetted:
            status = "ok"
        elif glyph_result is not None and not unverified:
            status = "ok"  # 真正完成字形级覆盖验证
        else:
            # 名称存在但未做字形级验证（或无有效用字/解析失败）：不得显示「字体完整」
            status = "partial_check"
        try:
            import hashlib

            sha256 = hashlib.sha256(raw).hexdigest()
        except Exception:
            sha256 = ""
        try:
            index_version = self._db.index_version()
        except Exception:
            index_version = 0
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
        if ass_id:
            try:
                self._db.set_ass_check_detail(
                    ass_id,
                    missing_details,
                    file_sha256=sha256,
                    index_version=index_version,
                    check_engine=check_engine,
                )
                self._db.replace_missing_glyphs(ass_id, file_path, missing_details)
            except Exception as err:
                if self._db is not None:
                    try:
                        self._db.add_log(f"写入字形检测明细失败: {err}", "warning")
                    except Exception:
                        pass
        total_missing_chars = sum(int(item.get("missing_count") or 0) for item in missing_details)
        if missing:
            status_text = "缺 " + str(len(missing)) + " 个字体" + (
                f"（{total_missing_chars} 个字符）" if total_missing_chars else ""
            )
        elif status == "partial_check":
            status_text = (
                f"未验证字形（{len(unverified)} 个字体仅按名称匹配）"
                if unverified
                else "未验证字形（无有效用字或解析失败）"
            )
        else:
            status_text = "字体完整"
        return {
            "id": ass_id,
            "status": status,
            "status_text": status_text,
            "check_engine": check_engine,
            "unverified_fonts": unverified[:20],
            "missing_count": len(missing),
            "all_fonts": all_fonts,
            "missing_fonts": missing,
            "missing_details": missing_details,
            "total_missing_chars": total_missing_chars,
            "subsetted": subsetted,
            "index_version": index_version,
        }

    # ─── API 注册 ───────────────────────────────────────
    # ─── API：种子字体收集 ──────────────────────────────
    def api_torrent_status(self) -> Dict[str, Any]:
        """种子收集状态：开关、基线、下载器可用性、解压能力、运行中任务数。"""
        try:
            tools = tq.describe_extract_tools(refresh=True)
        except Exception:
            tools = {"zip": True, "seven_zip": False, "rar": False, "tools": [], "extensions": [".zip"]}
        downloaders: List[Dict[str, Any]] = []
        for item in tq.list_downloaders():
            inst = tq.service_instance(tq.get_downloader_service(item["name"]))
            downloaders.append({**item, "available": inst is not None})
        baseline = self._torrent_baseline_ts()
        try:
            baseline_text = (
                datetime.fromtimestamp(baseline).strftime("%Y-%m-%d %H:%M:%S") if baseline > 0 else ""
            )
        except Exception:
            baseline_text = ""
        running = 0
        with self._torrent_jobs_lock:
            for job in self._torrent_jobs.values():
                if job.get("state") in ("queued", "running"):
                    running += 1
        return self._ok(
            {
                "enabled": self._torrent_enabled(),
                "baseline_ts": baseline,
                "baseline_text": baseline_text,
                "downloaders": downloaders,
                "tools": tools,
                "running": running,
            }
        )

    async def api_torrent_scan(self, request: Request = None) -> Dict[str, Any]:
        """手动检查下载器已完成种子（只处理基线之后完成的，不改下载器任何状态）。"""
        if not self._enabled:
            return self._err("插件已停用，请先在设置中启用")
        if not self._torrent_enabled():
            return self._err("请先在设置中开启「种子字体收集」")
        body: Dict[str, Any] = {}
        try:
            if request is not None:
                data = await request.json()
                if isinstance(data, dict):
                    body = data
        except Exception:
            body = {}
        downloader = str(body.get("downloader") or "")
        try:
            hours = int(body.get("hours") or 0)
        except Exception:
            hours = 0
        res = self._torrent_scan(downloader, hours)
        msg = (
            f"扫描 {res.get('scanned', 0)} 个已完成种子，入队 {res.get('queued', 0)} 个"
            f"（跳过历史 {res.get('skipped', 0)} 个）"
        )
        if res.get("errors"):
            msg += "；" + "；".join(res["errors"][:3])
        try:
            self._db.add_log(msg, "info")
        except Exception:
            pass
        return self._ok(res, msg)

    def api_torrent_records(self, limit: int = 20) -> Dict[str, Any]:
        """最近种子截取记录（只读展示，不影响任何文件）。"""
        try:
            rows = self._db.list_torrent_ingest(max(1, min(int(limit or 20), 200)))
        except Exception:
            rows = []
        return self._ok({"items": rows})

    def api_torrent_records_clear(self) -> Dict[str, Any]:
        """清空种子截取记录（只删记录，不动字体库与下载目录）。"""
        try:
            count = self._db.clear_torrent_ingest()
        except Exception:
            count = 0
        try:
            self._db.add_log(f"清空种子字体收集记录 {count} 条", "warning")
        except Exception:
            pass
        return self._ok({"removed": count}, f"已清空 {count} 条记录")

    def api_torrent_baseline_reset(self) -> Dict[str, Any]:
        """把基线重置为当前时间：从此只处理之后完成的种子。"""
        ts = self._torrent_set_baseline(int(time.time()))
        try:
            self._db.add_log("种子字体收集基线已重置为当前时间", "info")
        except Exception:
            pass
        return self._ok({"baseline_ts": ts}, "基线已重置")

    def get_api(self) -> List[Dict[str, Any]]:
        apis = [
            {"path": "/deps/check", "endpoint": self.api_deps_check, "methods": ["GET"], "auth": "bear", "summary": "检测运行依赖是否安装"},
            {"path": "/deps/install", "endpoint": self.api_deps_install, "methods": ["POST"], "auth": "bear", "summary": "重新安装运行依赖（pip）"},
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
            {"path": "/fonts/tree_meta", "endpoint": self.api_font_tree_meta, "methods": ["GET"], "auth": "bear", "summary": "字体库变更签名（轮询轻量检查用）"},
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
            {"path": "/subset/index", "endpoint": self.api_subset_index, "methods": ["GET"], "auth": "bear", "summary": "子集化引擎状态与字体索引"},
            {"path": "/subset/rebuild_index", "endpoint": self.api_subset_rebuild_index, "methods": ["POST"], "auth": "bear", "summary": "全部重建字体库索引（逐文件重新解析）"},
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
            {"path": "/missing/upload", "endpoint": self.api_missing_upload, "methods": ["POST"], "auth": "bear", "summary": "缺失字体上传（严格校验）"},
            {"path": "/missing/remap", "endpoint": self.api_missing_remap, "methods": ["POST"], "auth": "bear", "summary": "人工映射已上传字体到缺失目标"},
            {"path": "/missing/mappings", "endpoint": self.api_missing_mappings, "methods": ["GET"], "auth": "bear", "summary": "人工映射审计列表"},
            {"path": "/missing/mappings/remove", "endpoint": self.api_missing_mapping_delete, "methods": ["DELETE"], "auth": "bear", "summary": "删除人工映射记录"},
            {"path": "/missing/classify", "endpoint": self.api_missing_classify, "methods": ["POST"], "auth": "bear", "summary": "归类入库并重建索引"},
            {"path": "/missing/uploads/clear", "endpoint": self.api_missing_uploads_clear, "methods": ["DELETE"], "auth": "bear", "summary": "清除已上传字体"},
            {"path": "/missing/uploads/remove", "endpoint": self.api_missing_upload_remove, "methods": ["DELETE"], "auth": "bear", "summary": "删除单条已上传字体"},
            {"path": "/torrent/status", "endpoint": self.api_torrent_status, "methods": ["GET"], "auth": "bear", "summary": "种子字体收集状态（下载器/解压工具/基线）"},
            {"path": "/torrent/scan", "endpoint": self.api_torrent_scan, "methods": ["POST"], "auth": "bear", "summary": "立即检查下载器已完成种子"},
            {"path": "/torrent/records", "endpoint": self.api_torrent_records, "methods": ["GET"], "auth": "bear", "summary": "种子字体收集记录"},
            {"path": "/torrent/records", "endpoint": self.api_torrent_records_clear, "methods": ["DELETE"], "auth": "bear", "summary": "清空种子字体收集记录"},
            {"path": "/torrent/baseline", "endpoint": self.api_torrent_baseline_reset, "methods": ["POST"], "auth": "bear", "summary": "重置种子收集基线为当前时间"},
        ]
        # 写接口（POST/PUT/PATCH/DELETE）统一追加管理员依赖：宿主只按 auth 校验登录，
        # 不追加这一步的话，任意登录用户都能清库/删文件/装依赖/改配置。
        admin = _admin_write_dependencies()
        if admin:
            for api in apis:
                if any(str(m).upper() in ("POST", "PUT", "PATCH", "DELETE") for m in api.get("methods") or []):
                    api["dependencies"] = list(admin)
        return apis