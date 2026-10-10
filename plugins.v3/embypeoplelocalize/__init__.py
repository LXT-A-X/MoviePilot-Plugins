"""
EmbyPeopleLocalize - Emby 演职人员中文化
利用大模型把 Emby 英文/罗马音/日文人名翻译为简体中文并写回
支持多服务器分库、入库/Webhook触发、Cast 锁定防覆盖、繁简直转省 LLM
"""
import json
import os
import random
import re
import threading
import time
import traceback
import hashlib
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

try:
    import openai as _openai_mod
    import httpx as _httpx_mod
    _HAS_OPENAI_SDK = True
except Exception:
    _HAS_OPENAI_SDK = False
    _openai_mod = None
    _httpx_mod = None

try:
    from urllib3 import disable_warnings
    from urllib3.exceptions import InsecureRequestWarning
    disable_warnings(InsecureRequestWarning)
except Exception:
    try:
        import warnings, urllib3
        warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        pass

from app.sdk.config import settings
from app.sdk.events import eventmanager, Event
from app.sdk.services import MediaServerHelper
from app.sdk.logging import logger
from app.plugins import _PluginBase
from app.schemas import ServiceInfo, NotificationType
from app.schemas.types import EventType

from .emby_client import EmbyClient, ITEM_FOUND, ITEM_NOT_FOUND, ITEM_UNAVAILABLE
from .llm_client import (LLMClient, LLMError, RateLimited, QuotaExceeded,
                         AuthenticationError, ContextLengthExceeded)
from .db import (PeopleDb, NameMapDb, WritebackDb, TranslateJobDb, pool_target_name,
                 _is_kana_text, split_media_id, db_rev, get_meta, set_meta)
from . import constants
from .task_manager import TaskStateMixin
from .path_utils import PathUtilsMixin

try:
    import zhconv
    HAS_ZHCONV = True
except ImportError:
    HAS_ZHCONV = False


_STATE_FILE_LOCK = threading.RLock()


def _mask_secret(_s: str) -> str:
    """密钥掩码（SEC-001）：只保留首尾少量字符，中间固定星号。
    用于下发前端展示「已配置」，绝不下发原值。"""
    _v = str(_s or "")
    if not _v:
        return ""
    if len(_v) <= 8:
        return "****"
    return f"{_v[:4]}****{_v[-4:]}"


class _TxJob:
    """翻译任务对象（v4.6.62 · 第 26 节第 2 步）—— 作为运行期**单一数据源**，
    取代散落的 _tx_requested / _tx_source / _tx_target_scope / _tx_scope_items / _tx_only_terms
    五个全局字段（这些名称保留为对象视图，兼容既有调用点，写入即合并进当前 Job）。"""
    __slots__ = ("requested", "source", "scope", "items", "terms")

    def __init__(self):
        self.requested = False
        self.source = ""
        self.scope = "both"
        self.items: set = set()
        self.terms: set = set()

    def reset(self):
        self.requested = False
        self.source = ""
        self.scope = "both"
        self.items = set()
        self.terms = set()


class EmbyPeopleLocalize(TaskStateMixin, PathUtilsMixin, _PluginBase):
    plugin_name = "Emby 演职人员中文化"
    plugin_desc = "利用大模型把 Emby 英文/罗马音/日文人名翻译为简体中文并写回；拉取人名时可用 TMDB 刮削补中文名/简介/头像"
    plugin_icon = "https://raw.githubusercontent.com/LXT-A-X/MoviePilot-Plugins/main/icons/embypeoplelocalize.png"
    plugin_version = "4.6.113"
    plugin_author = "LXT-A-X"
    author_url = "https://github.com/LXT-A-X"
    plugin_config_prefix = "embypeoplelocalize_"
    plugin_order = 27
    auth_level = 1
    v2 = True

    # ────────── 配置项 ──────────
    _enabled: bool = False
    _prompt_template: str = ""
    _translate_actor: bool = True
    _translate_director: bool = False
    _translate_writer: bool = False
    _translate_producer: bool = False
    _translate_guest_star: bool = False
    _actor_limit: int = 10
    _guest_limit: int = 10
    _director_limit: int = 3
    _writer_limit: int = 3
    _enable_ai: bool = True
    _movie_actor_limit: int = 10
    _movie_guest_limit: int = 10
    _movie_director_limit: int = 3
    _movie_writer_limit: int = 3
    _tv_actor_limit: int = 10
    _ep_actor_limit: int = 10
    _tv_guest_limit: int = 10
    _tv_director_limit: int = 3
    _tv_writer_limit: int = 3
    _schedule_enabled: bool = False
    _schedule_interval_hours: int = 24
    _ja_name_policy: str = "convert"
    _use_proxy: bool = constants.DEFAULT_USE_PROXY  # 必须在类属性声明，避免 API 访问时 AttributeError
    _scan_mode: str = "nfo"
    _libraries: list = []
    _nfo_roots: list = []
    _nfo_recursive: bool = True
    _nfo_include_episodes: bool = False
    _nfo_backup: bool = False
    _nfo_dry_run: bool = False
    _nfo_episode_sync: bool = True
    _nfo_episode_overwrite: bool = False
    _sync_direction: str = "s2e"
    _nfo_preview: bool = False
    _nfo_dead_grace_hours: int = 24
    _translate_all: bool = False
    _translate_role: bool = True
    _max_people_per_batch: int = 30
    _max_guest_per_episode: int = 5
    _overwrite_chinese: bool = False
    _lock_cast: bool = False
    _webhook_delay: int = 60
    _notify_on_complete: bool = False
    _sync_series_people: bool = True
    _people_db: Optional[PeopleDb] = None
    _history_search_keyword: str = ""

    # 运行时触发开关
    _run_clear_cache: bool = False

    # LLM 独立配置
    _llm_base_url: str = ""
    _llm_api_key: str = ""
    _llm_model: str = ""
    _llm_timeout: int = 120
    _llm_mode: str = "system"
    _llm_verify_ssl: bool = constants.DEFAULT_LLM_VERIFY_SSL
    _translate_batching: str = "per_title"
    _llm_min_interval: float = constants.DEFAULT_LLM_MIN_INTERVAL
    _llm_tpm_budget: int = constants.DEFAULT_LLM_TPM_BUDGET   # v4.6.61：TPM 令牌预算（0=不限）
    _llm_max_rpm: int = 0
    _llm_thinking_off: bool = constants.DEFAULT_LLM_THINKING_OFF
    _llm_thinking_params: str = constants.DEFAULT_LLM_THINKING_PARAMS
    _probe_enabled: bool = False
    _probe_interval_min: int = 60
    _pool_fetch_scope: str = ""                 # "" → dump 按 constants.DEFAULT_POOL_FETCH_SCOPE 兜底
    _pool_keep_unknown: bool = constants.DEFAULT_POOL_KEEP_UNKNOWN
    _pool_fetch_types: list = []                # 人名池「拉取类型」独立配置；空 → 默认演员 + 声优
    _limits_unified: bool = False               # v4.6.48：人数上限三套合并为一套的迁移标记
    _auto_writeback: bool = True

    # ────────── 运行时状态（仅类型注解占位，实际值在 init_plugin 中实例化）──────────
    _ms_helper: Optional[MediaServerHelper] = None
    _llm: Optional[LLMClient] = None
    _stop_requested: bool = False
    _scan_stop: bool = False
    _pool_stop: bool = False
    _probe_stop: bool = False
    _probe_daemon_stop: object = None
    _scan_paused: bool = False
    _pool_paused: bool = False
    _live_log: List[Dict[str, Any]] = []
    _is_running: bool = False
    _scan_running: bool = False
    _translate_running: bool = False
    _writeback_running: bool = False
    _pool_running: bool = False
    _probe_running: bool = False
    _tx_thread: object = None
    _tx_event: object = None
    _tx_stop: bool = False
    _tx_hard_until: float = 0.0        # 配额/认证类硬停（重试无意义；到点前不发请求）
    _tx_hard_kind: str = ""
    _tx_job_total: int = 0
    _tx_job_done: int = 0
    _tx_job_failed: int = 0
    _tx_job_llm: int = 0
    _tx_job_hits: int = 0
    # v4.6.70（P0-1/P0-2）：拆分统计 —— 池命中 / 繁转简（AI 前）/ LLM 输出被简体化 / 按第一·二排明细
    _tx_job_pool: int = 0
    _tx_job_zhconv: int = 0
    _tx_job_llm_zhc: int = 0
    # v4.6.75（规范 §四-3）：本 Job 累计「送 LLM 输入条数 / 去重后唯一条数」
    _tx_job_dedup_in: int = 0
    _tx_job_dedup_uniq: int = 0
    # v4.6.76（规范 §十三）：Job Snapshot —— 任务创建时冻结的翻译配置（运行中改设置不影响当前任务）
    _tx_cfg_snapshot: object = None
    # v4.6.99（报告 P1-03 D）：快照版本 —— 旧任务恢复时据此按明确规则迁移，缺字段不静默套用新配置
    TX_SNAPSHOT_VERSION: int = 2
    # v4.6.113（P2）：重启恢复队列 —— 多个未完成强制重翻任务**逐个**恢复（各保留自己的 job/范围/条目）
    _tx_recover_queue: object = None
    # v4.6.103（TMDB-1/2）：TMDB 无效 ID 负缓存 TTL（秒）。宿主 TmdbApi 对 404/异常一律
    # 吞掉返回空，插件无法区分「确实没有」与「请求失败」；负结果在 TTL 内跳过重试，避免
    # 每轮扫描/每次拉池都重打同一个坏 ID。TTL 过期自动重试 —— 网络抖动不会永久毒化。
    _TMDB_DEAD_TTL: float = 6 * 3600.0
    _tx_job_by_kind: object = None
    _tx_job_started: float = 0.0
    _tx_autosync_res: object = None
    _tx_batch: int = 30                # 当前批大小（context_length 超限自动折半，成功后再放大）
    _tx_batch_max: int = 30
    # v4.6.112（GH#3-6）：本会话「已验证不超长」的批大小上限 —— 上下文超长折半后记录，
    # 之后放大不超过它，避免「折半 → 放大 → 又超长」来回抖动（每次抖动白烧一个请求）。
    _tx_batch_safe: int = 30
    # v4.6.112（GH#3-7）：待翻候选队列缓存（每 Job 跑一次全表 SQL + 游标向前推进）。
    # 此前**每一轮**都要重跑全表聚合再过滤上万条，只为挑 30 条 —— 报告者 1.4 万待翻时
    # 「两次请求之间隔 10~55 秒」主要就是这个。
    TX_OCC_CACHE_TTL: float = 30.0
    _tx_occ_cache: object = None
    _rate_limited_until: float = 0.0   # 429 熔断窗口（窗口内暂停消费，词条留 DB）
    _rl_strikes: int = 0               # 连续限流次数（60→120→240→600 指数退避）
    _pool_lu_cache: object = None      # 人名池查表缓存（60s 或写池后失效）—— 全局翻译记忆
    _pool_lu_ts: float = 0.0
    _pool_lu_id: object = {}
    _pool_lu_idname: object = {}
    _llm_reload_pending: bool = False
    _tx_active: object = None          # 类级：当前活跃翻译 worker 实例（热加载防双份，文档 §41）
    _tx_skip_clear: bool = False
    _wb_thread: object = None
    _wb_event: object = None
    _wb_stop: bool = False
    _wb_cursor: int = 0
    _wb_active: object = None
    _writeback_db: object = None
    _pool_thread: object = None
    _pool_pulling: bool = False
    _pool_status: Dict[str, Any] = {}
    _pool_sync_after_translate: bool = False
    _pool_auto_sync: bool = False
    _auto_translate_webhook: bool = False
    _auto_translate_scan: bool = False
    _webhook_enabled: bool = False
    _translate_person: bool = True
    _nfo_path_mappings: list = []
    # ── v4.6.62（第 26 节第 2 步）：翻译任务状态统一收敛到 _TxJob 对象 ──
    # 以下 5 个名称保留为 Job 对象视图（单一数据源），旧的散落字段已淘汰；
    # 写入即合并进当前 Job，读取永远取 Job 的当前值，id 由 _tx_job_id 单独持有。
    @property
    def _tx_active_job(self):
        _j = self.__dict__.get("_tx_active_job_obj")
        if _j is None:
            _j = _TxJob()
            self.__dict__["_tx_active_job_obj"] = _j
        return _j

    @property
    def _tx_requested(self):
        return bool(self._tx_active_job.requested)

    @_tx_requested.setter
    def _tx_requested(self, v):
        self._tx_active_job.requested = bool(v)

    @property
    def _tx_source(self):
        return self._tx_active_job.source

    @_tx_source.setter
    def _tx_source(self, v):
        self._tx_active_job.source = str(v or "")

    @property
    def _tx_target_scope(self):
        return self._tx_active_job.scope

    @_tx_target_scope.setter
    def _tx_target_scope(self, v):
        self._tx_active_job.scope = str(v or "both")

    @property
    def _tx_scope_items(self):
        return self._tx_active_job.items

    @_tx_scope_items.setter
    def _tx_scope_items(self, v):
        self._tx_active_job.items = set(v or ())

    @property
    def _tx_only_terms(self):
        return self._tx_active_job.terms

    @_tx_only_terms.setter
    def _tx_only_terms(self, v):
        self._tx_active_job.terms = set(v or ())

    _tx_paused: bool = False
    _tx_pause_logged: bool = False
    _legacy_mapping: tuple = ("", "")
    _last_run_time: Optional[float] = None
    _state_lock: threading.Lock = None
    _scan_lock: threading.Lock = None
    _scan_cursor: Optional[Dict[str, Any]] = None

    # 进度追踪（v1.3.0 统一为 _scan_status dict）
    _scan_status: Dict[str, Any] = {}
    _translate_status: Dict[str, Any] = {}
    _writeback_status: Dict[str, Any] = {}
    _probe_status: Dict[str, Any] = {}
    _progress_step_start_time: float = 0.0  # 当前条目计时起点（_elapsed_seconds 用）

    # Webhook 状态追踪
    _webhook_received: int = 0
    _webhook_processed: int = 0
    _webhook_failed: int = 0
    _webhook_skipped: int = 0
    _webhook_last_time: Optional[float] = None
    _webhook_last_event: str = ""
    _webhook_error: str = ""
    _pool_hits: int = 0
    _llm_terms: int = 0

    # 状态持久化路径
    _state_file: str = ""

    _lib_cache: list = []
    _lib_cache_ts: float = 0.0

    _db_items_cache: object = None       # {"ts": float, "data": list}

    _failed_terms: set = set()
    _failed_terms_detail: dict = {}   # {词条: 失败原因}

    # ────────── V2 私有属性 ──────────
    _last_save_time: float = 0.0
    _notification_flush_timer: object = None
    _notification_lock: object = None
    _scan_thread: object = None
    _task_threads: dict = {}
    _wb_job_thread: object = None   # 「全部写回」作业线程（区别于常驻 _wb_thread）
    _tx_job_thread: object = None   # 库内批量翻译作业线程（区别于常驻 _tx_thread）
    _startup_background_started: bool = False
    _stop_event: object = None
    _webhook_lock: object = None
    _webhook_worker_event: object = None
    _webhook_worker_thread: object = None
    _series_executor: object = None
    _series_executor_workers: int = 0
    _series_max_workers: int = constants.DEFAULT_SERIES_MAX_WORKERS
    _series_ingest_all: bool = constants.DEFAULT_SERIES_INGEST_ALL

    @property
    def private_attrs(self) -> List[str]:
        return [
            "_enabled", "_prompt_template",
            "_translate_actor", "_translate_director", "_translate_writer",
            "_translate_producer", "_translate_all", "_translate_role",
            "_translate_person",
            "_translate_guest_star", "_ja_name_policy",
            "_actor_limit", "_guest_limit", "_director_limit", "_writer_limit",
            "_scan_mode", "_libraries", "_nfo_roots",
            "_nfo_recursive", "_nfo_include_episodes",
            "_nfo_backup", "_nfo_dry_run", "_nfo_episode_sync",
            "_nfo_episode_overwrite", "_nfo_preview", "_nfo_dead_grace_hours",
            "_max_people_per_batch", "_max_guest_per_episode", "_overwrite_chinese",
            "_lock_cast", "_webhook_delay", "_notify_on_complete",
            "_run_clear_cache",
            "_llm_base_url", "_llm_api_key", "_llm_model", "_llm_timeout",
            "_is_running", "_last_run_time", "_last_save_time",
            "_scan_status",
            "_webhook_received", "_webhook_processed", "_webhook_failed",
            "_webhook_skipped", "_webhook_last_time", "_webhook_last_event", "_webhook_error",
        ]

    # ============================================================
    # 状态持久化
    # ============================================================
    def _get_state_file(self) -> str:
        if not self._state_file:
            try:
                from app.sdk.config import settings
                _base = str(settings.CONFIG_PATH)
            except Exception:
                _base = "config"
            cache_dir = os.path.join(_base, "plugins", "embypeoplelocalize")
            os.makedirs(cache_dir, exist_ok=True)
            self._state_file = os.path.join(cache_dir, "state.json")
        return self._state_file

    def _get_sigs_file(self) -> str:
        try:
            _sf = self._get_state_file()
            return os.path.join(os.path.dirname(_sf), "file_sigs.json")
        except Exception:
            return ""

    def _save_file_sigs(self) -> None:
        """持久化文件签名表（扫库轻量化）—— 独立小文件，避免随断点高频重写 state.json。"""
        try:
            p = self._get_sigs_file()
            if not p:
                return
            _data = {"sig_cfg": getattr(self, "_nfo_sigs_cfg", "") or "",
                     "sigs": getattr(self, "_nfo_file_sigs", None) or {}}
            with _STATE_FILE_LOCK:
                tmp = f"{p}.{os.getpid()}.{threading.get_ident()}.tmp"
                try:
                    with open(tmp, "w", encoding="utf-8") as f:
                        json.dump(_data, f, ensure_ascii=False)
                    os.replace(tmp, p)
                finally:
                    try:
                        if os.path.exists(tmp):
                            os.remove(tmp)
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"保存文件签名表失败（非致命）: {e}")

    def _load_file_sigs(self) -> None:
        """载入文件签名表（不存在/损坏则忽略，下次扫描自动重建）。"""
        try:
            p = self._get_sigs_file()
            if not p or not os.path.exists(p):
                return
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            _sigs = data.get("sigs")
            self._nfo_file_sigs = dict(_sigs) if isinstance(_sigs, dict) else {}
            self._nfo_sigs_cfg = str(data.get("sig_cfg") or "")
            if self._nfo_file_sigs:
                logger.info(f"[NFO] 文件签名表已载入 {len(self._nfo_file_sigs)} 条（扫库将跳过未变化文件）")
        except Exception as e:
            logger.debug(f"载入文件签名表失败（非致命）: {e}")

    def _serialize_webhook_schedule(self) -> dict:
        """把 _webhook_schedule 转成 JSON 安全结构（供 state.json 持久化）。
        仅保留结构合法的条目，字段做类型归一，避免脏数据带入落盘。"""
        try:
            out = {}
            for _k, _v in (getattr(self, "_webhook_schedule", None) or {}).items():
                if not isinstance(_v, dict):
                    continue
                out[str(_k)] = {
                    "execute_at": float(_v.get("execute_at") or 0),
                    "server_id": str(_v.get("server_id") or ""),
                    "item_id": str(_v.get("item_id") or ""),
                    "delay": int(_v.get("delay") or 0),
                    "brief": _v.get("brief") if isinstance(_v.get("brief"), dict) else {},
                }
            return out
        except Exception:
            return {}

    def _resume_webhook_queue(self):
        """重启/重载后把 state.json 恢复的延迟队列真正拉起来消费。
        仅在「插件启用 且 Webhook 总开关开启」且队列非空时启动 Worker；否则保留内存
        队列不消费（待用户重新开启 Webhook —— 下次事件入队即拉起 Worker 续跑），
        避免在未启用状态下被 Worker 误判「已关闭」而清空恢复的事件。"""
        try:
            if not (getattr(self, "_enabled", False) and getattr(self, "_webhook_enabled", False)):
                return
            with self._webhook_lock:
                if not self._webhook_schedule:
                    return
                if self._webhook_worker_thread is not None and self._webhook_worker_thread.is_alive():
                    return
                self._webhook_worker_event.clear()
                self._webhook_worker_thread = threading.Thread(
                    target=self._webhook_worker, daemon=True, name="webhook-worker")
                self._webhook_worker_thread.start()
                _n = len(self._webhook_schedule)
            logger.info(f"[Webhook] 重启续跑：将延迟队列 {_n} 个未处理事件交给 Worker 消费")
        except Exception as e:
            logger.warning(f"[Webhook] 恢复延迟队列续跑失败: {e}")

    def _save_state(self):
        try:
            state = {
                "version": self.plugin_version,
                "last_run_time": self._last_run_time,
                "scan_cursor": self._scan_cursor if hasattr(self, "_scan_cursor") else None,
                "webhook_received": self._webhook_received if hasattr(self, "_webhook_received") else 0,
                "webhook_processed": self._webhook_processed if hasattr(self, "_webhook_processed") else 0,
                "webhook_failed": self._webhook_failed if hasattr(self, "_webhook_failed") else 0,
                "webhook_last_time": self._webhook_last_time if hasattr(self, "_webhook_last_time") else None,
                "webhook_last_event": self._webhook_last_event if hasattr(self, "_webhook_last_event") else "",
                "webhook_error": self._webhook_error if hasattr(self, "_webhook_error") else "",
                "webhook_pending_config": getattr(self, "_webhook_pending_config", None) or {},
                "failed_terms": sorted(getattr(self, "_failed_terms", None) or ()),
                "failed_terms_detail": getattr(self, "_failed_terms_detail", None) or {},
                "pool_hits": int(getattr(self, "_pool_hits", 0) or 0),
                "llm_terms": int(getattr(self, "_llm_terms", 0) or 0),
                "last_full_scan_ts": getattr(self, "_last_full_scan_ts", 0) or 0,
                "probe_counts": getattr(self, "_probe_counts", None) or {},
                "probe_last_run": float(getattr(self, "_probe_last_run", 0) or 0),
                "probe_last_deep": float(getattr(self, "_probe_last_deep", 0) or 0),
                "probe_seen": getattr(self, "_probe_seen", None) or {},
                "webhook_events": [e for e in (getattr(self, "_webhook_events", None) or []) if isinstance(e, dict)][:100],
                "maint_cursor": dict(getattr(self, "_maint_cursor", None) or {}),
                "webhook_schedule": self._serialize_webhook_schedule(),
                # 注：文件签名表（nfo_file_sigs）不写这里 —— 它随断点每 15 个文件被高频保存，
                # 单独落 file_sigs.json（_save_file_sigs），避免把 state.json 撑大
            }
            state_file = self._get_state_file()
            with _STATE_FILE_LOCK:
                tmp_file = f"{state_file}.{os.getpid()}.{threading.get_ident()}.tmp"
                try:
                    with open(tmp_file, "w", encoding="utf-8") as f:
                        json.dump(state, f, ensure_ascii=False, indent=2)
                    os.replace(tmp_file, state_file)
                finally:
                    try:
                        if os.path.exists(tmp_file):
                            os.remove(tmp_file)
                    except Exception:
                        pass
            logger.debug(f"状态已保存到: {state_file}")
        except Exception as e:
            logger.error(f"保存状态失败: {e}\n{traceback.format_exc()}")

    def _load_state(self):
        """兼容读 —— 旧版 state.json 中的 name_cache/role_cache/processed/
        history/failed/cache_hits/cache_misses 一律忽略（不写入内存）；
        scan_cursor/Webhook 统计等仍正常载入。"""
        try:
            state_file = self._get_state_file()
            if not os.path.exists(state_file):
                logger.info("无持久化状态文件，使用空状态")
                return
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            self._last_run_time = state.get("last_run_time")
            if hasattr(self, "_scan_cursor"):
                cursor = state.get("scan_cursor")
                if cursor:
                    self._scan_cursor = cursor
                    logger.info(f"检测到未完成的扫描: {cursor}")
            if hasattr(self, "_webhook_received"):
                self._webhook_received = state.get("webhook_received", 0) or 0
                self._webhook_processed = state.get("webhook_processed", 0) or 0
                self._webhook_failed = state.get("webhook_failed", 0) or 0
                self._webhook_last_time = state.get("webhook_last_time")
                self._webhook_last_event = state.get("webhook_last_event", "") or ""
                self._webhook_error = state.get("webhook_error", "") or ""
            self._pool_hits = int(state.get("pool_hits", 0) or 0)
            self._llm_terms = int(state.get("llm_terms", 0) or 0)
            self._last_full_scan_ts = float(state.get("last_full_scan_ts", 0) or 0)
            _pc = state.get("probe_counts")
            self._probe_counts = dict(_pc) if isinstance(_pc, dict) else {}
            self._probe_last_run = float(state.get("probe_last_run", 0) or 0)
            self._probe_last_deep = float(state.get("probe_last_deep", 0) or 0)
            _ps = state.get("probe_seen")
            self._probe_seen = dict(_ps) if isinstance(_ps, dict) else {}
            _ft = state.get("failed_terms")
            if hasattr(self, "_failed_terms") and isinstance(_ft, list):
                self._failed_terms = set(str(x) for x in _ft if str(x or "").strip())
            _ftd = state.get("failed_terms_detail")
            if hasattr(self, "_failed_terms_detail") and isinstance(_ftd, dict):
                self._failed_terms_detail = {str(k): str(v) for k, v in _ftd.items()}
            if getattr(self, "_failed_terms", None):
                logger.info(f"[Translate] 已恢复失败词条清单 {len(self._failed_terms)} 条（重启不丢，可手动重试）")
            self._load_file_sigs()
            _we = state.get("webhook_events")
            if isinstance(_we, list):
                self._webhook_events = [e for e in _we if isinstance(e, dict)][:100]
                if self._webhook_events:
                    logger.info(f"[Webhook] 已恢复事件明细 {len(self._webhook_events)} 条（含失效/待恢复）")
            if hasattr(self, "_webhook_pending_config"):
                self._webhook_pending_config = state.get("webhook_pending_config", None) or {}
            _mc = state.get("maint_cursor")
            if isinstance(_mc, dict):
                self._maint_cursor = {"item_id": int(_mc.get("item_id") or 0),
                                      "ep_id": int(_mc.get("ep_id") or 0)}
            _ws = state.get("webhook_schedule")
            if hasattr(self, "_webhook_schedule") and isinstance(_ws, dict) and _ws:
                _restored = {}
                for _k, _v in _ws.items():
                    if not isinstance(_v, dict):
                        continue
                    _sk = str(_k)
                    if not _sk:
                        continue
                    _restored[_sk] = {
                        "execute_at": float(_v.get("execute_at") or 0),
                        "server_id": str(_v.get("server_id") or ""),
                        "item_id": str(_v.get("item_id") or ""),
                        "delay": int(_v.get("delay") or getattr(self, "_webhook_delay", 60) or 60),
                        "brief": _v.get("brief") if isinstance(_v.get("brief"), dict) else {},
                    }
                if _restored:
                    with self._webhook_lock:
                        for _sk, _info in _restored.items():
                            self._webhook_schedule.setdefault(_sk, _info)
                    logger.info(f"[Webhook] 已从 state.json 恢复延迟队列 {len(_restored)} 个未处理事件（待续跑）")
        except Exception as e:
            logger.warning(f"加载状态失败: {e}")

    def _auto_save(self):
        self._save_state()

    # ============================================================
    # V2 API 注册
    # ============================================================
    def get_api(self) -> List[dict]:
        return [
            {"path": "/clear_cache", "endpoint": self._api_clear_cache, "methods": ["GET", "POST"], "auth": "bear"},
            {"path": "/scan", "endpoint": self._api_scan, "methods": ["GET", "POST"], "auth": "bear"},
            {"path": "/stop", "endpoint": self._api_stop, "methods": ["GET", "POST"], "auth": "bear"},
            {"path": "/task/pause", "endpoint": self._api_task_pause, "methods": ["GET", "POST"], "auth": "bear"},
            {"path": "/task/resume", "endpoint": self._api_task_resume, "methods": ["GET", "POST"], "auth": "bear"},
            {"path": "/status", "endpoint": self._api_status, "methods": ["GET", "POST"], "auth": "bear"},
            {"path": "/webhook_status", "endpoint": self._api_webhook_status, "methods": ["GET"], "auth": "bear"},
            {"path": "/webhook_events", "endpoint": self._api_webhook_events, "methods": ["GET"], "auth": "bear"},
            {"path": "/webhook_events/clear", "endpoint": self._api_webhook_events_clear, "methods": ["POST"], "auth": "bear"},
            {"path": "/webhook/pending", "endpoint": self._api_webhook_pending, "methods": ["GET"], "auth": "bear"},
            {"path": "/webhook/pending_continue", "endpoint": self._api_webhook_pending_continue, "methods": ["POST"], "auth": "bear"},
            {"path": "/webhook/pending_clear", "endpoint": self._api_webhook_pending_clear, "methods": ["POST"], "auth": "bear"},
            {"path": "/db/purge_missing", "endpoint": self._api_db_purge_missing, "methods": ["POST"], "auth": "bear"},
            {"path": "/live_log", "endpoint": self._api_live_log, "methods": ["GET"], "auth": "bear"},
            {"path": "/llm/test", "endpoint": self._api_llm_test, "methods": ["POST"], "auth": "bear"},
            {"path": "/clear_logs", "endpoint": self._api_clear_logs, "methods": ["POST"], "auth": "bear"},
            {"path": "/deps/check", "endpoint": self._api_deps_check, "methods": ["GET"], "auth": "bear"},
            {"path": "/emby_libraries", "endpoint": self._api_emby_libraries, "methods": ["GET"], "auth": "bear"},
            {"path": "/nfo/path/check", "endpoint": self._api_nfo_path_check, "methods": ["POST"], "auth": "bear"},
            {"path": "/nfo/path/check_all", "endpoint": self._api_nfo_path_check_all, "methods": ["POST"], "auth": "bear"},
            {"path": "/nfo/path/browse", "endpoint": self._api_nfo_path_browse, "methods": ["GET"], "auth": "bear"},
            {"path": "/poster", "endpoint": self._api_poster, "methods": ["GET"], "auth": "bear"},
            {"path": "/db/items", "endpoint": self._api_db_items, "methods": ["GET"], "auth": "bear"},
            {"path": "/db/people", "endpoint": self._api_db_people, "methods": ["GET"], "auth": "bear"},
            {"path": "/db/person_occurrences", "endpoint": self._api_person_occurrences, "methods": ["GET"], "auth": "bear"},
            {"path": "/db/sync_emby_names", "endpoint": self._api_sync_emby_names, "methods": ["POST"], "auth": "bear"},
            {"path": "/probe/run", "endpoint": self._api_probe_run, "methods": ["POST"], "auth": "bear"},
            {"path": "/db/stats", "endpoint": self._api_db_stats, "methods": ["GET"], "auth": "bear"},
            {"path": "/db/restore", "endpoint": self._api_db_restore, "methods": ["POST"], "auth": "bear"},
            {"path": "/db/delete", "endpoint": self._api_db_delete, "methods": ["POST"], "auth": "bear"},
            {"path": "/db/clear", "endpoint": self._api_db_clear, "methods": ["POST"], "auth": "bear"},
            {"path": "/db/clear_other", "endpoint": self._api_db_clear_other, "methods": ["POST"], "auth": "bear"},
            {"path": "/db/export", "endpoint": self._api_db_export, "methods": ["GET"], "auth": "bear"},
            {"path": "/db/import", "endpoint": self._api_db_import, "methods": ["POST"], "auth": "bear"},
            {"path": "/db/retranslate", "endpoint": self._api_db_retranslate, "methods": ["POST"], "auth": "bear"},
            {"path": "/db/rescan_item", "endpoint": self._api_db_rescan_item, "methods": ["POST"], "auth": "bear"},
            {"path": "/db/role_memory", "endpoint": self._api_db_role_memory, "methods": ["GET"], "auth": "bear"},
            {"path": "/db/role_memory/clear", "endpoint": self._api_db_role_memory_clear, "methods": ["POST"], "auth": "bear"},
            {"path": "/db/translate_preview", "endpoint": self._api_db_translate_preview, "methods": ["GET"], "auth": "bear"},
            {"path": "/db/pending_detail", "endpoint": self._api_db_pending_detail, "methods": ["GET"], "auth": "bear"},
            {"path": "/db/pending_snapshot", "endpoint": self._api_db_pending_snapshot, "methods": ["GET"], "auth": "bear"},
            {"path": "/translate/jobs", "endpoint": self._api_translate_jobs, "methods": ["GET"], "auth": "bear"},
            {"path": "/translate/jobs/create", "endpoint": self._api_translate_job_create, "methods": ["POST"], "auth": "bear"},
            {"path": "/translate/jobs/cancel", "endpoint": self._api_translate_job_cancel, "methods": ["POST"], "auth": "bear"},
            {"path": "/translate/jobs/resume", "endpoint": self._api_translate_job_resume, "methods": ["POST"], "auth": "bear"},
            {"path": "/db/translate_library", "endpoint": self._api_db_translate_library, "methods": ["POST"], "auth": "bear"},
            {"path": "/db/writeback_all", "endpoint": self._api_db_writeback_all, "methods": ["POST"], "auth": "bear"},
            {"path": "/translate/retry_failed", "endpoint": self._api_translate_retry_failed, "methods": ["POST"], "auth": "bear"},
            {"path": "/translate/clear_failed", "endpoint": self._api_translate_clear_failed, "methods": ["POST"], "auth": "bear"},
            {"path": "/db/update_person", "endpoint": self._api_db_update_person, "methods": ["POST"], "auth": "bear"},
            {"path": "/db/update_person_scope", "endpoint": self._api_db_update_person_scope, "methods": ["POST"], "auth": "bear"},
            {"path": "/db/update_person_global", "endpoint": self._api_db_update_person_global, "methods": ["POST"], "auth": "bear"},
            {"path": "/config", "endpoint": self._api_get_config, "methods": ["GET"], "auth": "bear"},
            {"path": "/nfo/test", "endpoint": self._api_nfo_test, "methods": ["POST"], "auth": "bear"},
            {"path": "/nfo/sync", "endpoint": self._api_nfo_sync, "methods": ["POST"], "auth": "bear"},
            {"path": "/translate_all", "endpoint": self._api_translate_all, "methods": ["POST"], "auth": "bear"},
            {"path": "/name_map", "endpoint": self._api_name_map_list, "methods": ["GET"], "auth": "bear"},
            {"path": "/name_map/update", "endpoint": self._api_name_map_update, "methods": ["POST"], "auth": "bear"},
            {"path": "/name_map/delete", "endpoint": self._api_name_map_delete, "methods": ["POST"], "auth": "bear"},
            {"path": "/pool/list", "endpoint": self._api_pool_list, "methods": ["GET"], "auth": "bear"},
            {"path": "/pool/fetch", "endpoint": self._api_pool_fetch, "methods": ["POST"], "auth": "bear"},
            {"path": "/pool/rescreen", "endpoint": self._api_pool_rescreen, "methods": ["POST"], "auth": "bear"},
            {"path": "/pool/update", "endpoint": self._api_pool_update, "methods": ["POST"], "auth": "bear"},
            {"path": "/pool/translate", "endpoint": self._api_pool_translate, "methods": ["POST"], "auth": "bear"},
            {"path": "/pool/sync", "endpoint": self._api_pool_sync, "methods": ["POST"], "auth": "bear"},
            {"path": "/pool/status", "endpoint": self._api_pool_status, "methods": ["GET"], "auth": "bear"},
            # 出现清单（只展示不编辑）：与库页共用同一实现
            {"path": "/pool/occurrences", "endpoint": self._api_person_occurrences, "methods": ["GET"], "auth": "bear"},
            {"path": "/pool/sync_one", "endpoint": self._api_pool_sync_one, "methods": ["POST"], "auth": "bear"},
            {"path": "/pool/refetch_one", "endpoint": self._api_pool_refetch_one, "methods": ["POST"], "auth": "bear"},
            {"path": "/pool/export", "endpoint": self._api_pool_export, "methods": ["GET"], "auth": "bear"},
            {"path": "/pool/import", "endpoint": self._api_pool_import, "methods": ["POST"], "auth": "bear"},
            {"path": "/pool/clear", "endpoint": self._api_pool_clear, "methods": ["POST"], "auth": "bear"},
            {"path": "/config", "endpoint": self._api_save_config, "methods": ["POST"], "auth": "bear"},
        ]

    def _api_llm_test(self):
        """LLM 测试连接 —— 真实调用一次 1 词翻译，把成功/具体错误回显给设置页。"""
        try:
            llm = getattr(self, "_llm", None)
            if llm is None:
                try:
                    self._init_llm()
                except Exception as _e:
                    return {"success": False, "message": f"初始化 LLM 失败: {_e}"}
                llm = getattr(self, "_llm", None)
            if llm is None:
                return {"success": False, "message": "LLM 未初始化：请检查插件的 LLM 配置（地址/密钥/模型）"}
            try:
                r = llm.translate_terms("测试", 2026, ["Tom Hanks"], raise_typed=True)
            except Exception as _e:
                _k = str(getattr(_e, "kind", "") or "").strip()
                _label = {
                    "rate_limited": "触发服务商限流（429）",
                    "quota_exceeded": "余额/配额不足",
                    "authentication_failed": "认证失败（API Key 无效或无权限）",
                    "context_length_exceeded": "上下文过长",
                    "server_error": "服务端异常（5xx）",
                    "network_error": "网络异常（连接/超时/代理）",
                    "empty_response": "模型返回空内容",
                }.get(_k, "")
                _msg = f"调用失败：{_label or _e}"
                if _label:
                    _msg += f"（{_e}）"
                return {"success": False, "message": _msg, "error_kind": _k}
            if r:
                _sample = next(iter(r.items()), None)
                _txt = f"→ {_sample[0]} = {_sample[1]}" if _sample else ""
                return {"success": True, "message": f"连接正常（模型 {getattr(llm, 'model', '-')} 返回 {len(r)} 条{_txt}）"}
            _err = str(getattr(llm, "last_error", "") or "").strip()
            return {"success": False,
                    "message": f"连接成功但无翻译产出：{_err or '模型返回空内容（可能是思考型模型或提示词未被接受）'}"}
        except Exception as e:
            return {"success": False, "message": f"测试连接异常: {e}"}

    def _api_clear_logs(self):
        try:
            with self._state_lock:
                self._live_log = []
            self._push_log("INFO", "实时日志已清空")
            return {"success": True, "message": "日志已清空"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_deps_check(self):
        try:
            items = []
            # 繁简转换
            items.append({
                "key": "zhconv",
                "name": "繁简转换 (zhconv)",
                "ok": bool(HAS_ZHCONV),
                "detail": "繁体人名/角色名自动转简体" if HAS_ZHCONV else "未安装 zhconv，繁体将直接走 LLM 处理",
                "impact": "繁转简降级",
            })
            # HTTP 客户端（LLM 调用基础）
            try:
                import httpx  # noqa: F401
                httpx_ok = True
            except Exception:
                httpx_ok = False
            items.append({
                "key": "httpx",
                "name": "HTTP 客户端 (httpx)",
                "ok": httpx_ok,
                "detail": "LLM 请求使用的 HTTP 客户端" if httpx_ok else "未安装 httpx，LLM 调用降级为 requests",
                "impact": "LLM 兼容性下降",
            })
            try:
                import openai  # noqa: F401
                openai_ok = True
            except Exception:
                openai_ok = False
            items.append({
                "key": "openai",
                "name": "LLM SDK (openai)",
                "ok": openai_ok,
                "detail": "LLM 走 openai SDK（连接复用/代理支持更好）" if openai_ok
                          else "未安装 openai SDK，已自动降级为 requests（功能可用；重装插件或 pip install openai 后恢复）",
                "impact": "LLM 兼容性下降",
            })
            # LLM AI 服务（按来源模式判断）
            _mode = getattr(self, "_llm_mode", "system")
            if not self._ai_enabled():
                items.append({
                    "key": "llm",
                    "name": "LLM / AI 服务（已关闭）",
                    "ok": True,
                    "detail": "AI 翻译开关已关闭 —— 当前仅使用人名池 / 繁转简 / 人工修正；需要 AI 翻译时请在设置页开启",
                    "impact": "无需 AI",
                })
            elif _mode == "plugin":
                _llm_cfg_ok = bool(self._llm_base_url and self._llm_api_key)
                _llm_detail = "插件 LLM：地址与密钥已填写" if _llm_cfg_ok else "已选择插件 LLM，但未填写地址/密钥"
                items.append({
                    "key": "llm",
                    "name": "LLM / AI 服务（插件）",
                    "ok": _llm_cfg_ok,
                    "detail": _llm_detail,
                    "impact": "无法翻译",
                })
            else:
                _llm_cfg_ok = bool(getattr(settings, 'LLM_BASE_URL', '') and getattr(settings, 'LLM_API_KEY', ''))
                _llm_detail = "使用 MoviePilot 系统 LLM 配置" if _llm_cfg_ok else "系统未配置 LLM（LLM_BASE_URL / LLM_API_KEY），请切换为「插件配置」或到系统设置配置"
                items.append({
                    "key": "llm",
                    "name": "LLM / AI 服务（系统）",
                    "ok": _llm_cfg_ok,
                    "detail": _llm_detail,
                    "impact": "无法翻译",
                })
            # 翻译记录数据库
            db_ok = getattr(self, "_people_db", None) is not None
            items.append({
                "key": "db",
                "name": "翻译记录库",
                "ok": db_ok,
                "detail": "翻译记录先入库再同步 Emby，可恢复" if db_ok else "翻译记录数据库未初始化",
                "impact": "无法恢复翻译",
            })
            ok_count = sum(1 for i in items if i["ok"])
            return {"success": True, "data": {"items": items, "ok_count": ok_count, "total": len(items)}}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_name_map_list(self, keyword: str = "", page: int = 1, size: int = 50):
        try:
            from .db import NameMapDb
            dbm = getattr(self, "_name_map_db", None) or NameMapDb()
            res = dbm.list_map(plugin_id=self.__class__.__name__, keyword=keyword,
                               page=int(page or 1), size=int(size or 50))
            return {"success": True, "data": res}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_name_map_update(self, data: Optional[dict] = None):
        _g = self._api_gate()
        if _g:
            return _g
        # v4.6.76（规范 §十一）：统一任务忙碌门禁 —— 本接口会改 name_map / 人物池 / 起池翻译，
        # 与翻译 worker / 池 worker 并发会互相覆盖。
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            if not isinstance(data, dict) or not data.get("original") or not data.get("zh"):
                return {"success": False, "message": "缺少 original/zh 参数"}
            from .db import NameMapDb
            dbm = getattr(self, "_name_map_db", None) or NameMapDb()
            ok = dbm.upsert_manual(plugin_id=self.__class__.__name__,
                                   name_type=str(data.get("type") or "person"),
                                   original=str(data.get("original")),
                                   zh=str(data.get("zh")))
            self._push_log("INFO", f"人名池人工录入: {data.get('original')} → {data.get('zh')}" if ok else "人名池录入失败")
            return {"success": ok, "message": "已保存（优先级：人工最高）" if ok else "保存失败"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_name_map_delete(self, data: Optional[dict] = None):
        _g = self._api_gate()
        if _g:
            return _g
        # v4.6.76（规范 §十一）：统一任务忙碌门禁 —— 本接口会改 name_map / 人物池 / 起池翻译，
        # 与翻译 worker / 池 worker 并发会互相覆盖。
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            if not isinstance(data, dict) or not data.get("original"):
                return {"success": False, "message": "缺少 original 参数"}
            from .db import NameMapDb
            dbm = getattr(self, "_name_map_db", None) or NameMapDb()
            ok = dbm.delete_entry(plugin_id=self.__class__.__name__,
                                  name_type=str(data.get("type") or "person"),
                                  original=str(data.get("original")))
            return {"success": ok, "message": "已删除" if ok else "删除失败"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ============================================================
    # ============================================================
    POOL_PAGE = 500          # /Persons 与库条目分页大小

    def _emby_clients(self) -> dict:
        """全部 Emby 服务的客户端（skey → EmbyClient）—— 多服务器人名同步用（文档 §2.5）。"""
        out: Dict[str, Any] = {}
        try:
            for svc in (self._get_all_emby_services() or []):
                url = self._get_service_url(svc)
                key = self._get_service_api_key(svc)
                if url and key:
                    out[self._get_server_identifier(svc)] = EmbyClient(
                        url, key, svc, user_id=self._get_service_user_id(svc), use_proxy=self._use_proxy)
        except Exception as e:
            logger.warning(f"[Emby] 取多服务客户端失败: {e}")
        return out

    def _pool_collect_persons(self, cli, scope: str) -> list:
        """收集一个 Emby 服务上的 Person 列表（按 Id 去重，文档 §2.3）。
        同时保留 Emby People 关系中的 Type，并合并多类型（文档 §八/§九/§十三）。
        scope=all → /Persons 分页取实体，再用已选媒体库 People 关系按 ID 补类型；
        scope=libraries → 直接遍历已选媒体库条目的 People（含 Type）。"""
        out: Dict[str, dict] = {}

        def _add(_id: str, _nm: str, _types):
            _rec = out.get(_id)
            if _rec is None:
                out[_id] = {"id": _id, "name": _nm, "types": []}
                _rec = out[_id]
            elif _nm and not _rec.get("name"):
                _rec["name"] = _nm
            _ts = _rec.setdefault("types", [])
            for _t in (_types or []):
                if _t and _t not in _ts:
                    _ts.append(_t)

        def _iter_library_people():
            """遍历已选媒体库条目的 People 关系，产出 (id, name, [types])。"""
            _want = set(str(x) for x in (self._libraries or []) if str(x).strip())
            for lib in (self._get_emby_libraries() or []):
                if self._pool_stop:
                    break
                if _want and lib.get("full_key") not in _want and lib.get("lib_id") not in _want:
                    continue
                _lib_id = str(lib.get("lib_id") or "")
                if not _lib_id:
                    continue
                _start = 0
                while not self._pool_stop:
                    r = cli.query_items({"ParentId": _lib_id, "Recursive": "true",
                                         "IncludeItemTypes": "Movie,Series",
                                         "Fields": "People",
                                         "StartIndex": _start, "Limit": self.POOL_PAGE})
                    items = r.get("Items") or []
                    for it in items:
                        for p in (it.get("People") or []):
                            _id = str(p.get("Id") or "").strip()
                            _nm = str(p.get("Name") or "").strip()
                            if not _id:
                                continue
                            _ty = str(p.get("Type") or "").strip()
                            yield _id, _nm, ([_ty] if _ty else [])
                    self._pool_status["collect_done"] = len(out)
                    _start += len(items)
                    if not items or len(items) < self.POOL_PAGE:
                        break

        if scope == "all":
            # 1) 先用已选媒体库 People 关系建立 person_id → 类型 索引（文档 §十一/§十三：ID 优先，不靠 name 反查）
            _type_idx: Dict[str, list] = {}
            for _id, _nm, _ts in _iter_library_people():
                if self._pool_stop:
                    break
                _cur = _type_idx.setdefault(_id, [])
                for _t in _ts:
                    if _t and _t not in _cur:
                        _cur.append(_t)
            # 2) /Persons 分页取全部 Person 实体，按 ID 合并类型
            _start = 0
            while not self._pool_stop:
                r = cli.list_all_persons(limit=self.POOL_PAGE, start_index=_start) or {}
                items = r.get("Items") or []
                _total = int(r.get("TotalRecordCount") or 0)
                if _total:
                    self._pool_status["collect_total"] = _total
                for it in items:
                    _id = str(it.get("Id") or "").strip()
                    _nm = str(it.get("Name") or "").strip()
                    if _id and _nm:
                        _add(_id, _nm, _type_idx.get(_id, []))
                self._pool_status["collect_done"] = len(out)
                _start += len(items)
                if not items or len(items) < self.POOL_PAGE or (_total and _start >= _total):
                    break
            return list(out.values())
        # scope=libraries：遍历已选库的条目（电影/剧）取 People（含 Type）
        for _id, _nm, _ts in _iter_library_people():
            if self._pool_stop:
                break
            if _id and _nm:
                _add(_id, _nm, _ts)
        return list(out.values())

    def _tmdb_download_image(self, profile_path: str) -> Optional[bytes]:
        """下载 TMDB 人物头像原图（/t/p/original）—— 对齐 personmeta set_item_image 的下载分支。
        走 settings.PROXY（容器内需科学访问 TMDB 图片域时生效）。失败返回 None。"""
        try:
            _domain = str(getattr(settings, "TMDB_IMAGE_DOMAIN", "") or "").strip() or "image.tmdb.org"
            _url = f"https://{_domain}/t/p/original{profile_path}"
            import requests
            _proxy = getattr(settings, "PROXY", None)
            _proxies = None
            if isinstance(_proxy, str) and _proxy.strip():
                _proxies = {"http": _proxy, "https": _proxy}
            elif isinstance(_proxy, dict) and _proxy:
                _proxies = _proxy
            _r = requests.get(_url, timeout=(10, 60), proxies=_proxies)
            if _r.status_code == 200 and _r.content:
                return _r.content
            logger.debug(f"[Pool][TMDB] 头像下载失败 {_url} 返回 {_r.status_code}")
        except Exception as e:
            logger.debug(f"[Pool][TMDB] 头像下载异常 {profile_path}: {e}")
        return None

    def _pool_tmdb_fill_one(self, cli, *, server_id: str, person_id: str, name_cur: str) -> dict:
        """拉取人名时的 TMDB 刮削补译（缝合官方 personmeta「演职人员刮削」）——
        只由调用方对「Emby 当前名非中文」的 Person 调用，流程与 personmeta 一致：
        1) 取 Person 完整详情拿 TmdbId（本轮 tmdbid → MediaPerson 详情缓存，避免重复请求）
        2) TmdbChain.person_detail → also_known_as 中第一个中文别名（繁转简）作中文名；
           biography 本身为中文时作简介（v4.6.67：简介与中文名解耦，各自独立写回）
        3) v4.6.20(P1-方案A)：不再把 TMDB 中文名直接写回 Emby —— 只把「繁转简后」的中文名
           作为池译文返回，由翻译/同步流程统一写回；繁体在「拉取环节」即本地繁转简（一律简体），
           不再留到入库后再慢慢翻。Overview(中文简介) + LockedFields(Overview) 与 Primary 头像
           仍即时写回（池不承载简介，与译名流程无关；头像同 personmeta）。
        头像与是否拿到中文名无关（有 profile 就更新）；
        失败一律静默返回 err —— 绝不因此把 Person 踢出池或中断本轮拉取。
        返回 {"cn_name", "cn_raw", "avatar", "wrote", "err"}：cn_name = 繁转简后的中文名（供入池，
        据此记 source='tmdb'）；cn_raw = TMDB 原始中文名（可能繁体，仅用于日志/区分）。"""
        out = {"cn_name": "", "cn_raw": "", "avatar": False, "wrote": False, "err": ""}
        try:
            _det = cli.get_person_detail(person_id) or {}
        except Exception as e:
            out["err"] = f"取详情失败: {e}"
            return out
        if not _det:
            out["err"] = "取详情为空"
            return out
        _prov = _det.get("ProviderIds") or {}
        _tid = str(_prov.get("Tmdb") or _prov.get("tmdb") or "").strip()
        if not _tid.isdigit():
            out["err"] = "无 TMDB ID"
            return out
        # v4.6.103（TMDB-2）：进程级负缓存 —— 同一 TmdbId 已在本进程确认「TMDB 无人物详情」时，
        # TTL 内直接跳过（此前每次拉池都重打一遍坏 ID，宿主 tmdbapi 每次 logger.error 一行
        # "The resource you requested could not be found."，用户日志被刷屏）。
        # v4.6.111（LIB-020）：负缓存同时看内存与持久化副本（重启也生效）
        if self._tmdb_dead_hit(("person", _tid)):
            out["err"] = "TMDB 无人物详情（负缓存命中，跳过请求）"
            return out
        _cache = getattr(self, "_tmdb_person_cache", None)
        if _cache is None:
            _cache = self._tmdb_person_cache = {}
        if _tid in _cache:
            _pd = _cache[_tid]
        else:
            try:
                from app.chain.tmdb import TmdbChain
                _pd = TmdbChain().person_detail(int(_tid))
            except Exception as e:
                logger.debug(f"[Pool][TMDB] person_detail 失败 {name_cur}({_tid}): {e}")
                _pd = None
            _cache[_tid] = _pd
        if not _pd:
            # v4.6.103（TMDB-2）登记负结果；v4.6.111（LIB-020）同时落持久化副本（重启也生效）
            self._tmdb_dead_note(("person", _tid))
            out["err"] = "TMDB 无人物详情"
            return out
        # 中文名来源（v4.6.11 修正）：
        # 1) also_known_as 里第一个「含汉字且不含假名」的别名（对齐 personmeta __get_chinese_name）
        # 2) 若没有 —— 再取 person_detail.name：TmdbChain 按 TMDB_LOCALE（通常 zh-CN）本地化，
        #    TMDB 有中文翻译时该字段本身就是中文名。例：person/1239110 的 zh-CN name =「水桥香织」，
        #    但它并不出现在 also_known_as（「又名」）里 —— 这正是此前「TMDB 明明有中文名却刮不到」的原因。
        #    无中文翻译时该字段回退为原始名（含假名/无汉字），会被下面的检查挡掉，不会误写。
        _cn_raw = ""
        for _alias in (getattr(_pd, "also_known_as", None) or []):
            _a = str(_alias or "").strip()
            if _a and self._name_is_zh(_a):
                _cn_raw = _a
                break
        if not _cn_raw:
            _nm = str(getattr(_pd, "name", "") or "").strip()
            if _nm and self._name_is_zh(_nm):
                _cn_raw = _nm
        if not _cn_raw:
            # 兜底（v4.6.11）: 宿主 TMDB_LOCALE 非中文时，TmdbChain 返回的 name 也不是中文，
            # 显式按 zh-CN 再查一次人物详情取本地化名；失败静默不影响其它流程
            try:
                _loc = str(getattr(settings, "TMDB_LOCALE", "") or "").lower()
            except Exception:
                _loc = ""
            if not _loc.startswith("zh"):
                try:
                    from app.modules.themoviedb.tmdbapi import TmdbApi
                    _d2 = TmdbApi(language="zh-CN").get_person_detail(int(_tid)) or {}
                    _n2 = str(_d2.get("name") or "").strip()
                    if _n2 and self._name_is_zh(_n2):
                        _cn_raw = _n2
                except Exception as _e2:
                    logger.debug(f"[Pool][TMDB] zh-CN 兜底查询失败 {name_cur}: {_e2}")
        _cn = ""
        if _cn_raw:
            try:
                _cn = str(self._zhconv_convert(_cn_raw) or "").strip()
            except Exception:
                _cn = _cn_raw
        # 中文简介（v4.6.11 改为「汉字占比」判定）：中文简介常引用日文原名（含假名，如
        # 「水桥香织（日语：水橋 かおり…）」），用「不含假名」一刀切会误杀；用「含汉字即收」
        # 又会把纯日文简介写进去。故要求汉字为主（假名不超过汉字的 40%）。
        _bio = str(getattr(_pd, "biography", "") or "").strip()
        if _bio:
            _han = sum(1 for _c in _bio if 0x4E00 <= ord(_c) <= 0x9FFF)
            _kana = sum(1 for _c in _bio
                        if 0x3041 <= ord(_c) <= 0x309F or 0x30A0 <= ord(_c) <= 0x30FF)
            if not (_han > 0 and _kana <= _han * 0.4):
                _bio = ""
        _pp = str(getattr(_pd, "profile_path", "") or "").strip()
        # v4.6.67（P1-E）：中文简介写回与「是否有中文名」解耦 ——
        # 此前要求 _cn and _bio 同时成立，导致「TMDB 有中文简介但无中文名」时简介不写回，
        # 与 UI「中文简介即时写回」不一致；现在只要拿到合格中文简介就写（Overview + 锁定）。
        if _bio:
            try:
                _iteminfo = dict(_det)
                _lf = list(_iteminfo.get("LockedFields") or [])
                _iteminfo["Overview"] = str(self._zhconv_convert(_bio) or _bio)
                if "Overview" not in _lf:
                    _lf.append("Overview")
                _iteminfo["LockedFields"] = _lf
                cli.update_person_info(person_id, _iteminfo)
            except Exception as _e3:
                logger.debug(f"[Pool][TMDB] 简介写回失败 {name_cur}: {_e3}")
        out["cn_name"] = _cn
        out["cn_raw"] = _cn_raw
        # 头像更新（有 profile 就写；v4.6.8 优化：Emby 已有 Primary 图则跳过，避免每次拉取重复下载上传）
        _has_primary = bool((_det.get("ImageTags") or {}).get("Primary"))
        if _pp and not _has_primary:
            _img = self._tmdb_download_image(_pp)
            if _img:
                out["avatar"] = bool(cli.set_person_primary_image(person_id, _img))
        return out

    # ── v4.6.111（LIB-020）：TMDB 无效 ID 负缓存的**持久化** + 「查不到」日志汇总 ──
    _TMDB_DEAD_META_KEY = "tmdb_dead_ids"

    def _tmdb_dead_key_str(self, key) -> str:
        """把内存里的负缓存元组键转成可持久化的字符串键（credits|1822070|movie / person|12345）。"""
        try:
            _k, _v = (key or ("", ""))
            if isinstance(_v, (list, tuple)):
                return f"{_k}|" + "|".join(str(x) for x in _v)
            return f"{_k}|{_v}"
        except Exception:
            return str(key)

    def _tmdb_dead_dict(self) -> dict:
        """负缓存的持久化副本（跨重启有效）—— 只存 {键: 时间戳}，读取时按 TTL 过滤。

        v4.6.111（LIB-020）：此前负缓存只在进程内存里，**重启插件后同一批坏 id 会再问一遍**
        （用户实测：每次扫描日志里都有「很多 404」）。落进插件库后，问过一次就记住，
        直到用户在设置页点「清空缓存」。
        """
        _m = getattr(self, "_tmdb_dead_store", None)
        if isinstance(_m, dict):
            return _m
        _m = {}
        try:
            _raw = str(get_meta(self._TMDB_DEAD_META_KEY, "") or "")
            if _raw:
                _d = json.loads(_raw)
                if isinstance(_d, dict):
                    _now = time.time()
                    _ttl = float(getattr(self, "_TMDB_DEAD_TTL", 21600.0) or 21600.0)
                    _m = {str(k): float(v) for k, v in _d.items()
                          if isinstance(v, (int, float)) and (_now - float(v)) < _ttl}
        except Exception:
            _m = {}
        self._tmdb_dead_store = _m
        return _m

    def _tmdb_dead_note(self, key) -> None:
        """登记一条负结果：内存 + 持久化副本（打脏标记，扫描收尾时统一落库，避免频繁写盘）。"""
        _now = time.time()
        try:
            _dead = getattr(self, "_tmdb_dead", None)
            if _dead is None:
                _dead = self._tmdb_dead = {}
            _dead[key] = _now
        except Exception:
            pass
        try:
            self._tmdb_dead_dict()[self._tmdb_dead_key_str(key)] = _now
            self._tmdb_dead_dirty = True
        except Exception:
            pass

    def _tmdb_dead_hit(self, key) -> bool:
        """该键是否在 TTL 内已被判定为「无效」（内存或持久化副本命中）。"""
        _ttl = float(getattr(self, "_TMDB_DEAD_TTL", 21600.0) or 21600.0)
        _now = time.time()
        try:
            _dead = getattr(self, "_tmdb_dead", None) or {}
            _ts = _dead.get(key)
            if _ts and (_now - float(_ts)) < _ttl:
                return True
        except Exception:
            pass
        try:
            _ts2 = self._tmdb_dead_dict().get(self._tmdb_dead_key_str(key))
            return bool(_ts2 and (_now - float(_ts2)) < _ttl)
        except Exception:
            return False

    def _tmdb_scan_flush(self) -> None:
        """扫描收尾：负缓存落库 + 把「查不到」的逐条日志**汇总成一行**。

        v4.6.111（LIB-020）：此前每个查不到的 id 都打一条 INFO，用户日志被刷屏
        （「还有很多，我就不一一复制了」）；现在明细降到 debug，结束时只报一条汇总。
        """
        try:
            if getattr(self, "_tmdb_dead_dirty", False):
                _st = getattr(self, "_tmdb_dead_store", None)
                if isinstance(_st, dict):
                    _now = time.time()
                    _ttl = float(getattr(self, "_TMDB_DEAD_TTL", 21600.0) or 21600.0)
                    _st = {k: v for k, v in _st.items() if (_now - float(v)) < _ttl}
                    self._tmdb_dead_store = _st
                    set_meta(self._TMDB_DEAD_META_KEY, json.dumps(_st, ensure_ascii=False))
                self._tmdb_dead_dirty = False
        except Exception:
            pass
        try:
            _q = getattr(self, "_tmdb_empty_log", None) or []
            if _q:
                _uniq = sorted({str(x) for x in _q})
                _preview = "、".join(_uniq[:6])
                logger.info(f"[TMDB] 本次查不到演职员的 ID 共 {len(_q)} 个（已跳过并登记负缓存，"
                            f"重启也不会重复请求；「清空缓存」可重置；明细见 debug 日志）"
                            f"｜示例：{_preview}" + ("…" if len(_uniq) > 6 else ""))
            self._tmdb_empty_log = []
        except Exception:
            pass

    def _tmdb_credits_role_map(self, item_id: str, item_type: str, hint: str = "") -> dict:
        """取条目的 TMDB 演职人员表，构建 {人物 TmdbId(str): 英文角色名}。

        用途：回填「第二排角色名」——豆瓣等来源的 NFO 第二排常缺英文角色名，翻译链无原文可翻。
        仅接受纯数字（真实 TMDB ID）的条目；结果按 (id, movie/tv) 缓存，一轮扫描内不重复请求；
        失败一律静默返回空表（不影响入库，也不中断扫描）。
        """
        _iid = str(item_id or "").strip()
        if not _iid.isdigit():
            return {}
        _is_tv = str(item_type or "").lower() in ("series", "tvshow", "tv", "episode")
        _key = (_iid, "tv" if _is_tv else "movie")
        _cache = getattr(self, "_tmdb_credits_cache", None)
        if _cache is None:
            _cache = self._tmdb_credits_cache = {}
        if _key in _cache:
            return _cache[_key]
        # v4.6.103（TMDB-1）：进程级负缓存 —— 宿主 TmdbApi.get_tv_credits/get_movie_credits 对
        # 404/异常一律吞掉返回 []，插件无法区分「确实没有演职员」与「ID 无效/请求失败」；此前
        # _tmdb_credits_cache 每轮扫描清空，同一个坏 ID 会被反复重打（日志 1 秒 1 条 404）。
        # 命中即跳过；TTL 过期自动重试。
        # v4.6.111（LIB-020）：负缓存查询同时看内存与**持久化副本**（重启也生效）
        if self._tmdb_dead_hit(("credits", _key)):
            _cache[_key] = {}
            return {}
        _map = {}
        try:
            from app.modules.themoviedb.tmdbapi import TmdbApi
            # 固定 en-US：拿 TMDB 的英文角色名（character）作为「可被翻译的原文」
            _api = TmdbApi(language="en-US")
            _fetch = _api.get_tv_credits if _is_tv else _api.get_movie_credits
            _page = 1
            while _page <= 10:
                _cast = _fetch(int(_iid), page=_page, count=100) or []
                if not _cast:
                    break
                for _c in _cast:
                    _pid = str((_c or {}).get("id") or "").strip()
                    _ch = str((_c or {}).get("character") or "").strip()
                    if _pid and _ch and _pid not in _map:
                        _map[_pid] = _ch
                if len(_cast) < 100:
                    break
                _page += 1
        except Exception as e:
            logger.debug(f"[Pool][TMDB] credits 拉取失败 {_iid}({'tv' if _is_tv else 'movie'}): {e}")
        _cache[_key] = _map
        if not _map:
            # v4.6.103（TMDB-1）：空结果登记负缓存（TTL 内不再重打 —— 404 的 ID 与「确实无演职员」
            # 在宿主侧无法区分，两者都不值得每轮重试；TTL 到期会自动再试一次）。
            # v4.6.111（LIB-020）：登记负缓存（内存 + 待落库），并把明细排进扫描汇总队列 ——
            # 逐条 info 会刷屏（用户实测「还有很多」），现在只 debug 留明细、扫描结束汇总一行。
            self._tmdb_dead_note(("credits", _key))
            try:
                _q = getattr(self, "_tmdb_empty_log", None)
                if _q is None:
                    _q = self._tmdb_empty_log = []
                if len(_q) < 200:
                    _q.append(f"{_iid}({'tv' if _is_tv else 'movie'})"
                              f"{('｜' + hint) if hint else ''}")
            except Exception:
                pass
            logger.debug(f"[TMDB] 演职员表为空：id={_iid}（{'tv' if _is_tv else 'movie'}）"
                         f"{('｜' + hint) if hint else ''}"
                         f" —— 该 ID 无效（TMDB 返回 404）或该条目确实没有演职员")
        return _map

    def _pool_fetch_worker(self, data: Optional[dict] = None):
        """人名池拉取主体（文档 §2.3）：Emby Person → 类型过滤 → 入池。
        body: {scope: libraries|all, server_id: str}
        拉取类型按人名池「独立设置」（_pool_fetch_trans_types / pool_fetch_types），
        不跟随设置页「翻译范围」。"""
        _pid = self.__class__.__name__
        data = data or {}
        _scope = str(data.get("scope") or getattr(self, "_pool_fetch_scope", "libraries") or "libraries").strip().lower()
        _types_in = data.get("types")
        if isinstance(_types_in, list) and _types_in:
            _types = [str(t).strip() for t in _types_in if str(t).strip()]
        else:
            _types = self._pool_fetch_trans_types()
        _only_server = str(data.get("server_id") or "").strip()
        _t0 = time.time()
        self._pool_pulling = True
        self._pool_status = {"running": True, "phase": "pool", "total": 0, "done": 0,
                             "current": "", "current_server": "", "current_person": "",
                             "server_total": 0, "server_done": 0, "servers": [],
                             "collect_total": 0, "collect_done": 0,
                             "added": 0, "updated": 0, "unchanged": 0,
                             "filtered": 0, "failed": 0}
        self._tmdb_person_cache = {}
        _added = _updated = _unchanged = _filtered = _failed = 0
        _added_pending = 0
        _tmdb_name_ok = 0
        _tmdb_avatar_ok = 0
        try:
            _dbm = getattr(self, "_name_map_db", None) or NameMapDb()
            self._name_map_db = _dbm
            services = self._get_all_emby_services() or []
            if _only_server:
                services = [s for s in services if self._get_server_identifier(s) == _only_server]
            if not services:
                self._push_log("ERROR", "[Pool] 拉取人名失败：未配置可用的 Emby 服务（请到设置页确认 Emby 服务）")
                return
            self._push_log("INFO", f"[Pool] 拉取人名开始：来源={'全库 Person' if _scope == 'all' else '已选媒体库'}，"
                                   f"类型={'、'.join(_types) or '（未勾选任何拉取类型，将不入池）'}（按人名池独立设置），{len(services)} 个 Emby 服务")
            for svc in services:
                if self._pool_stop:
                    break
                if not self._pause_gate("pool"):
                    break
                _skey = self._get_server_identifier(svc)
                _sname = getattr(svc, "name", "") or "Emby"
                try:
                    cli = EmbyClient(self._get_service_url(svc), self._get_service_api_key(svc), svc,
                                     user_id=self._get_service_user_id(svc), use_proxy=self._use_proxy)
                except Exception as e:
                    logger.warning(f"[Pool] 取客户端失败 {_skey}: {e}")
                    continue
                self._pool_status["current_server"] = _sname
                self._pool_status["current"] = f"读取 {_sname} 的人员清单…"
                self._push_log("INFO", f"[Pool] Emby {_sname}：开始拉取人员清单（scope={_scope}）")
                _persons = self._pool_collect_persons(cli, _scope)
                if not _persons:
                    self._push_log("WARNING", f"[Pool] {_sname} 未读到任何 Person（接口不可用或该库无条目）")
                    continue
                _srv_total = len(_persons)
                _srv_done_base = int(self._pool_status.get("done") or 0)
                _svc_entry = {"server": _sname, "total": _srv_total, "done": 0}
                self._pool_status["server_total"] = _srv_total
                self._pool_status["server_done"] = 0
                self._pool_status["total"] = int(self._pool_status.get("total") or 0) + _srv_total
                self._pool_status.setdefault("servers", []).append(_svc_entry)
                _svc_added = 0
                _svc_updated = 0
                for _i, p in enumerate(_persons):
                    if self._pool_stop:
                        break
                    if not self._pause_gate("pool"):
                        break
                    if _i % 20 == 0 or _i == len(_persons) - 1:
                        self._pool_status["server_done"] = _i + 1
                        _svc_entry["done"] = _i + 1
                        self._pool_status["done"] = _srv_done_base + _i + 1
                        self._pool_status["current_person"] = str(p.get("name") or "")
                        self._pool_status["current"] = str(p.get("name") or "")
                    _ptypes = [str(t).strip() for t in (p.get("types") or []) if str(t).strip()]
                    if _ptypes and not (_types and any(t in _types for t in _ptypes)):
                        # 类型已知但不在「翻译范围」类型开关内 → 过滤（文档 §十二 步骤 2）
                        _filtered += 1
                        continue
                    # 类型未知（scope=all 未补到关系类型）→ 保留为「未确定类型」，不参与按类型筛选（文档 §十一/§十二 步骤 3）
                    _cur = str(p.get("name") or "").strip()
                    _is_zh = self._name_is_zh(_cur)
                    _tmdb_cn = ""
                    if (not _is_zh) and bool(getattr(self, "_pool_tmdb_fill", True)):
                        _ex = None
                        try:
                            _ex = _dbm.find_pool_person(plugin_id=_pid, server_id=_skey,
                                                        emby_person_id=p["id"])
                        except Exception:
                            _ex = None
                        _ex_zh = str((_ex or {}).get("name_zh") or "").strip()
                        _ex_orig = str((_ex or {}).get("name_original") or "").strip()
                        if (_ex is not None and _ex_zh and _ex_zh != _ex_orig
                                and not self._looks_like_japanese(_ex_zh)):
                            pass  # 池内已有有效译文（人工/AI/TMDB）→ 不动 Emby，交给同步流程
                        else:
                            self._pool_status["current"] = f"TMDB 刮削 {_cur}…"
                            _tr = self._pool_tmdb_fill_one(cli, server_id=_skey,
                                                           person_id=p["id"], name_cur=_cur)
                            _tmdb_cn = str(_tr.get("cn_name") or "")
                            if _tmdb_cn:
                                _tmdb_name_ok += 1
                                self._pool_lu_cache = None
                                _trad = "（繁体→简体）" if str(_tr.get("cn_raw") or "") not in ("", _tmdb_cn) else ""
                                logger.debug(f"[Pool][TMDB] {_cur} → {_tmdb_cn}{_trad}（已入池，待同步写回）")
                            if _tr.get("avatar"):
                                _tmdb_avatar_ok += 1
                    _cur_after = _cur
                    _zh_fill = _tmdb_cn or (_cur if _is_zh else "")
                    try:
                        _st = _dbm.upsert_pool_person(
                            plugin_id=_pid, server_id=_skey, emby_person_id=p["id"],
                            name_original=_cur, name_current=_cur_after,
                            name_zh=_zh_fill,
                            person_type=(_ptypes[0] if _ptypes else ""), person_types=_ptypes,
                            source=("emby" if _is_zh else ("tmdb" if _tmdb_cn else "")),
                            translation_status=("translated" if (_is_zh or _tmdb_cn) else "pending"),
                            sync_status="")
                    except Exception as _e:
                        logger.debug(f"[Pool] 入池失败 {_cur}: {_e}")
                        _st = "failed"
                    if _st == "added":
                        _added += 1
                        _svc_added += 1
                        if not _is_zh and not _tmdb_cn:
                            _added_pending += 1
                    elif _st == "updated":
                        _updated += 1
                        _svc_updated += 1
                    elif _st == "unchanged":
                        _unchanged += 1
                    else:
                        _failed += 1
                _svc_entry["done"] = _srv_total
                self._pool_status["server_done"] = _srv_total
                self._pool_status["done"] = _srv_done_base + _srv_total
                if str(_scope or "").strip().lower() == "all":
                    try:
                        _seen = {str(p.get("id") or "").strip() for p in _persons if str(p.get("id") or "").strip()}
                        _lc = _dbm.sweep_pool_lifecycle(plugin_id=_pid, server_id=_skey, seen_ids=_seen) or {}
                        if _lc:
                            self._push_log("INFO", f"[Pool] {_sname} 生命周期刷新：在线 {_lc.get('active', 0)} / "
                                                  f"暂缺 {_lc.get('stale', 0)} / 已消失 {_lc.get('missing', 0)}")
                    except Exception as _e:
                        logger.debug(f"[Pool] 生命周期刷新失败: {_e}")
                else:
                    self._push_log("INFO", f"[Pool] {_sname} 为「仅已选媒体库」拉取，跳过全服务器生命周期判定"
                                           f"（未覆盖的 Person 不算消失）")
                self._push_log("INFO", f"[Pool] Emby {_sname} 入池完成：新增 {_svc_added} 个，更新 {_svc_updated} 个")
            self._pool_status.update({"added": _added, "updated": _updated, "unchanged": _unchanged,
                                      "skipped": _unchanged, "filtered": _filtered, "failed": _failed,
                                      "done": self._pool_status.get("total") or 0,
                                      "phase": "done", "current": "", "current_person": ""})
            _cnt = {}
            try:
                _cnt = _dbm.count_pool_status(plugin_id=_pid) or {}
            except Exception:
                _cnt = {}
            _tmdb_txt = ""
            if bool(getattr(self, "_pool_tmdb_fill", True)):
                _tmdb_txt = f"TMDB 刮削：{_tmdb_name_ok} 人入池中文名（待同步） / {_tmdb_avatar_ok} 人更新头像，"
            self._push_log("INFO", f"[Pool] 拉取人名完成：新增 {_added} / 更新 {_updated} / 无变化 {_unchanged} / 类型过滤 {_filtered} / 失败 {_failed}，"
                                   f"{_tmdb_txt}池共 {_cnt.get('total', 0)} 人（待翻 {_cnt.get('pending', 0)} / 待同步 {_cnt.get('translated', 0)}），"
                                   f"耗时 {int(time.time() - _t0)} 秒"
                                   + ("；已按开关自动开始翻译新人物" if (getattr(self, "_pool_auto_translate", False) and _added_pending > 0) else ""))
            if (_added or _updated) and self._notify_guard("人名池拉取完成"):
                try:
                    self.post_message(mtype=NotificationType.Manual, title=self.plugin_name,
                                      text=(f"👥 人名池拉取完成\n"
                                            f"📥 新增 {_added} · 更新 {_updated} · 无变化 {_unchanged} · 过滤 {_filtered} · 失败 {_failed}\n"
                                            + (f"🌐 TMDB 刮削：{_tmdb_name_ok} 人入池中文名 · {_tmdb_avatar_ok} 人更新头像\n"
                                               if bool(getattr(self, "_pool_tmdb_fill", True)) else "")
                                            + f"📊 池共 {_cnt.get('total', 0)} 人：待翻 {_cnt.get('pending', 0)} · "
                                              f"待同步 {_cnt.get('translated', 0)} · 已同步 {_cnt.get('synced', 0)}"))
                except Exception as _ne:
                    logger.warning(f"[Notify] 人名池拉取完成通知发送失败: {_ne}")
        except Exception as e:
            logger.error(f"[Pool] 拉取失败: {e}\n{traceback.format_exc()}")
            self._push_log("ERROR", f"[Pool] 拉取人名失败：{e}")
        finally:
            self._pool_pulling = False
            self._pool_status["running"] = False
            self._pool_status["paused"] = False
            self._pool_paused = False
            self._set_task_running("pool", False)
            # 拉取结束 → 唤醒 Webhook worker 续跑拉取期间积压的事件（文档 §2.4）
            try:
                if getattr(self, "_webhook_worker_event", None) is not None:
                    self._webhook_worker_event.set()
            except Exception:
                pass
            try:
                if (getattr(self, "_pool_translation_enabled", True)
                        and getattr(self, "_pool_auto_translate", False) and _added_pending > 0
                        and self._ai_enabled()):   # v4.6.61（P1-SET-04）：AI 关闭时不自动消费
                    self._tx_request_consume(source="pool")
            except Exception:
                pass
            try:
                self._save_state()
            except Exception:
                pass

    def _warn_once(self, key: str, msg: str) -> None:
        """同一 key 每次进程内只告警一次（文档 §十 §二十五）——
        批量同步/多服务器/legacy 数据场景下避免同一条 WARNING 日志刷屏。"""
        try:
            _seen = getattr(self, "_warn_once_seen", None)
            if _seen is None:
                _seen = set()
                self._warn_once_seen = _seen
            if key in _seen:
                return
            _seen.add(key)
        except Exception:
            pass
        logger.warning(msg)

    @staticmethod
    def _provider_sig(person: dict) -> str:
        """Person 的 ProviderIds 指纹 —— 判断多个同名 Person 是否为同一人（重复实体）。"""
        _prov = (person or {}).get("ProviderIds") or {}
        if not isinstance(_prov, dict):
            return ""
        _items = sorted(f"{str(k).lower()}={str(v).strip()}"
                        for k, v in _prov.items() if str(v).strip())
        return "|".join(_items)

    def _resolve_rename_by_name(self, cli, *, name_original: str, target: str, tag: str) -> dict:
        """无 ID / ID 已失效时按名字定位 Person 并改名（文档 §十 §二十五 兜底规则）。
        - 同名候选唯一 → 直接改名；
        - 多候选：若全部候选 ProviderIds 指纹一致 → 判定为「同一人的重复 Person 实体」，全部改名；
          指纹不一致（真同名不同人）→ 身份无法确认 → 失败，绝不自动猜。
        - 原文名与目标名都搜不到 → 失败。
        返回 {ok, reason, skipped?, person_id?, ambiguous?}。"""
        _orig = str(name_original or "").strip()
        _cands = []
        try:
            _cands = cli.find_persons_by_name(_orig) or []
        except Exception:
            _cands = []
        if len(_cands) > 1:
            _sig = self._provider_sig(_cands[0])
            _same = bool(_sig) and all(self._provider_sig(_c) == _sig for _c in _cands)
            if not _same:
                self._warn_once(f"{tag}:ambiguous:{_orig}",
                                f"[{tag}] 原名「{_orig}」在 Emby 有 {len(_cands)} 个同名 Person → 阻止自动改名")
                return {"ok": False, "ambiguous": True,
                        "reason": f"Emby 中存在 {len(_cands)} 个同名人物「{_orig}」，无法确认身份，"
                                  f"已阻止自动改名（请人工确认或先补齐 Person ID）"}
            _done = 0
            for _c in _cands:
                try:
                    if cli.rename_person(str(_c.get("Id")), target, _c.get("ProviderIds")):
                        _done += 1
                except Exception:
                    pass
            if _done:
                return {"ok": True, "reason": f"已同步（同名同一人 {_done} 个 Person 实体）",
                        "person_id": str(_cands[0].get("Id") or "")}
            return {"ok": False, "reason": "Emby 改名接口失败（同名同一人多实体）"}
        person = _cands[0] if _cands else None
        if not person or not person.get("Id"):
            _p2 = cli.find_person_by_name(target)
            if _p2 and _p2.get("Id"):
                return {"ok": True, "skipped": True, "reason": "已是目标名",
                        "person_id": str(_p2.get("Id") or "")}
            return {"ok": False, "reason": "Emby 中未找到该人物（原文名与目标名都搜不到）"}
        if str(person.get("Name") or "").strip() == target:
            return {"ok": True, "skipped": True, "reason": "已是目标名",
                    "person_id": str(person.get("Id") or "")}
        if cli.rename_person(str(person.get("Id")), target, person.get("ProviderIds")):
            return {"ok": True, "reason": "已同步", "person_id": str(person.get("Id") or "")}
        return {"ok": False, "reason": "Emby 改名接口失败"}

    def _pool_sync_one_row(self, cli, *, person_id: str, name_original: str, name_zh: str,
                           name_current: str = "") -> dict:
        """单条同步 —— 优先 emby_person_id 直接改名（文档 §1.2-6：不能优先靠名字猜）；
        ID 缺失/失效才回退按名字找（唯一候选才允许，见 _resolve_rename_by_name）。
        返回 {ok, reason, skipped?, person_id?}（person_id=本次确认/可回写的身份，供 legacy 行补齐）。
        目标名统一用 pool_target_name 推导 —— 有效译文优先，
        原文已是中文时目标名=原文（no_change 行也需同步到 Emby 当前名）。"""
        _orig = str(name_original or "").strip()
        _cur = str(name_current or "").strip()
        _pid = str(person_id or "").strip()
        _target = pool_target_name({"name_original": _orig, "name_zh": name_zh})
        if not _target:
            return {"ok": True, "skipped": True, "reason": "无需同步（无有效目标名）"}
        if _cur and _cur == _target:
            return {"ok": True, "skipped": True, "reason": "已是目标名"}
        if _pid:
            if cli.rename_person(_pid, _target):
                return {"ok": True, "reason": "已同步", "person_id": _pid}
            # v4.6.113（P1-03）：ID 状态**三态**判定 —— 只有 Emby 明确回答「不存在」
            # 才允许按名字回退；「查询失败 / 服务器不可用」一律按「状态未知」处理：
            # 停止自动改名、不按名字回退，等待重试（避免把「暂时查不到」误当成「已删除」
            # 而按名字匹配到同名他人）。
            _pst, _pinfo, _preason = ITEM_UNAVAILABLE, None, "query_failed"
            try:
                _pst, _pinfo, _preason = cli.get_person_status(_pid)
            except Exception as _pe:
                _pst, _pinfo, _preason = ITEM_UNAVAILABLE, None, f"exception:{_pe}"
            if _pst == ITEM_FOUND:
                self._warn_once(f"pool:id-rename-fail:{_pid}",
                                f"[Pool] PersonId {_pid}（{_orig}）改名失败但 ID 仍有效 → 记失败，不按名字回退")
                return {"ok": False, "reason": "Emby 改名接口失败（Person ID 仍有效，已阻止按名字回退以免误改同名人物）"}
            if _pst == ITEM_UNAVAILABLE:
                self._warn_once(f"pool:id-unknown:{_pid}",
                                f"[Pool] PersonId {_pid}（{_orig}）状态无法确认（{_preason}）"
                                f"→ 停止自动改名、不按名字回退，等待重试")
                return {"ok": False,
                        "reason": f"无法确认 Person ID 是否仍有效（{_preason}）：已停止自动改名、"
                                  f"未按名字回退，请稍后重试"}
            # ITEM_NOT_FOUND：ID 确实已不存在 → 才允许按名字回退（仅唯一候选）
            self._warn_once(f"pool:id-stale:{_pid}",
                            f"[Pool] PersonId {_pid}（{_orig}）已失效 → 允许按名字回退（仅唯一候选）")
        return self._resolve_rename_by_name(cli, name_original=_orig, target=_target, tag="Pool")

    def _pool_sync_all(self, *, server_id: str = "", ctx: str = "") -> dict:
        """批量同步池中「待同步」条目到 Emby（文档 §2.5）—— 逐条按 server_id 选对应客户端。"""
        _pid = self.__class__.__name__
        _dbm = getattr(self, "_name_map_db", None) or NameMapDb()
        self._name_map_db = _dbm
        try:
            rows = _dbm.list_translated_pending_sync(plugin_id=_pid, server_id=server_id) or []
        except Exception:
            rows = []
        _res = {"total": len(rows), "renamed": 0, "skipped": 0, "failed": 0, "fails": [], "message": ""}
        if not rows:
            _res["message"] = "没有待同步的人名"
            return _res
        _clients = self._emby_clients()
        if not _clients:
            _res["failed"] = len(rows)
            _res["message"] = "Emby 未配置或不可用"
            self._push_log("WARNING", "人名池同步：Emby 未配置或不可用")
            return _res
        _now = datetime.now().isoformat(timespec="seconds")
        try:
            for r in rows:
                if self._pool_stop:
                    break
                _skey = str(r.get("server_id") or "")
                if _skey:
                    cli = _clients.get(_skey)
                    if cli is None:
                        self._warn_once(f"pool:server-missing:{_skey}",
                                        f"[Emby] 找不到 server_id={_skey} 对应的 Emby 服务 —— 已跳过，避免改名到错误的服务器")
                        _cerr = f"找不到 server_id={_skey} 对应的 Emby 服务（已跳过，避免改名到错误服务器）"
                    else:
                        _cerr = ""
                else:
                    self._warn_once("pool:legacy-no-server-id",
                                    "[Emby] legacy/no-server-id 记录：按第一台 Emby 兼容同步（多服务器环境下建议补齐 server_id）")
                    cli, _cerr = next(iter(_clients.values())), ""
                _orig = str(r.get("name_original") or "").strip()
                _zh = str(r.get("name_zh") or "").strip()
                _cur = str(r.get("name_current") or "").strip()
                _person_id = str(r.get("emby_person_id") or "").strip()
                _target = pool_target_name(r)
                if cli is None:
                    _res["failed"] += 1
                    if len(_res["fails"]) < 8:
                        _res["fails"].append(f"{_orig} → {_target}（{_cerr}）")
                    try:
                        _dbm.update_pool_status(plugin_id=_pid, server_id=_skey, emby_person_id=_person_id,
                                                name_original=_orig, sync_status="failed",
                                                sync_error=str(_cerr or ""))
                    except Exception:
                        pass
                    continue
                _sr = self._pool_sync_one_row(cli, person_id=_person_id, name_original=_orig,
                                              name_zh=_zh, name_current=_cur)
                if _sr.get("ok"):
                    if _sr.get("skipped"):
                        _res["skipped"] += 1
                    else:
                        _res["renamed"] += 1
                    _resp_id = str(_sr.get("person_id") or "").strip()
                    if not _person_id and _resp_id:
                        try:
                            _dbm.bind_pool_person_id(plugin_id=_pid, server_id=_skey,
                                                     name_original=_orig, emby_person_id=_resp_id)
                            _person_id = _resp_id
                        except Exception:
                            pass
                    try:
                        _dbm.update_pool_status(plugin_id=_pid, server_id=_skey, emby_person_id=_person_id,
                                                name_original=_orig,
                                                translation_status=("translated" if (_target and _target != _orig) else "no_change"),
                                                sync_status="synced", sync_error="", last_sync_at=_now,
                                                name_current=_target)
                    except Exception:
                        pass
                else:
                    _res["failed"] += 1
                    if len(_res["fails"]) < 8:
                        _res["fails"].append(f"{_orig} → {_target}（{_sr.get('reason')}）")
                    try:
                        # 同步失败只记原因，绝不改译文/状态为成功（文档 §46）
                        _dbm.update_pool_status(plugin_id=_pid, server_id=_skey, emby_person_id=_person_id,
                                                name_original=_orig, sync_status="failed",
                                                sync_error=str(_sr.get("reason") or ""))
                    except Exception:
                        pass
        finally:
            try:
                for _c in _clients.values():
                    try:
                        _c.close()
                    except Exception:
                        pass
            except Exception:
                pass
        try:
            _pc3 = _dbm.count_pool_status(plugin_id=_pid) or {}
            _left_sync = int(_pc3.get("translated") or 0)
        except Exception:
            _left_sync = 0
        _res["left_sync"] = _left_sync
        _res["message"] = (f"改名 {_res['renamed']} 个 · 已是译文 {_res['skipped']} 个 · "
                           f"未找到/失败 {_res['failed']} 个（本轮处理 {_res['total']} 个"
                           f"{('，' + ctx) if ctx else ''}）· 剩余待同步 {_left_sync}")
        self._push_log("INFO", f"🔄 人名池同步：{_res['message']}")
        for _f in _res["fails"]:
            self._push_log("WARNING", f"⚠️ 人名池同步失败：{_f}")
        return _res

    def _notify_skipped_hint(self, what: str) -> None:
        """通知被跳过时的可见提示 —— 便于排查「为什么没收到通知」。
        此前开关关闭导致静默跳过（日志无痕），用户无法判断是「没发」还是「发失败」。"""
        try:
            self._push_log("INFO", f"{what}：未发送通知（设置页「完成时通知」开关未开启；开启后即可收到）")
        except Exception:
            pass

    def _notify_guard(self, what: str) -> bool:
        """通知开关检查 —— 关闭时打一条可见日志（避免"为什么没通知"无迹可查）。"""
        if bool(getattr(self, "_notify_on_complete", False)):
            return True
        self._notify_skipped_hint(what)
        return False

    def _pool_sync_worker(self, data: Optional[dict] = None):
        """批量同步（后台线程）—— 人名池页「批量同步」按钮。"""
        try:
            data = data or {}
            _res = self._pool_sync_all(server_id=str(data.get("server_id") or ""), ctx="批量同步")
            if _res.get("total") and self._notify_guard("人名池批量同步完成"):
                try:
                    self.post_message(mtype=NotificationType.Manual, title=self.plugin_name,
                                      text=(f"🔄 人名池同步完成\n"
                                            f"✏️ 改名：{_res.get('renamed', 0)} 个\n"
                                            f"♻️ 已是译文：{_res.get('skipped', 0)} 个\n"
                                            f"❌ 未找到/失败：{_res.get('failed', 0)} 个\n"
                                            f"⏳ 剩余待同步：{_res.get('left_sync', 0)} 个"))
                except Exception as _ne:
                    logger.warning(f"[Notify] 人名池同步完成通知发送失败: {_ne}")
        except Exception as e:
            logger.error(f"[Pool] 批量同步失败: {e}\n{traceback.format_exc()}")
            self._push_log("ERROR", f"人名池批量同步失败：{e}")
        finally:
            self._set_task_running("pool", False)

    # ── 人名池 API（文档 §47）──

    def _api_pool_list(self, keyword: str = "", status: str = "", type: str = "",
                       server_id: str = "", page: int = 1, size: int = 50):
        try:
            dbm = getattr(self, "_name_map_db", None) or NameMapDb()
            res = dbm.list_pool(plugin_id=self.__class__.__name__, keyword=str(keyword or ""),
                                status=str(status or ""), ptype=str(type or ""),
                                server_id=str(server_id or ""),
                                page=int(page or 1), size=int(size or 50))
            return {"success": True, "data": res}
        except Exception as e:
            logger.error(f"[Pool] 列表读取失败: {e}")
            return {"success": False, "message": str(e)}

    def _api_pool_status(self):
        try:
            dbm = getattr(self, "_name_map_db", None) or NameMapDb()
            _cnt = dbm.count_pool_status(plugin_id=self.__class__.__name__) or {}
            _tx = self._tx_state_snapshot(_cnt)
            _ts = dict(getattr(self, "_translate_status", None) or {})
            _tx["running"] = bool(_ts.get("running"))
            _tx["total"] = int(_ts.get("total") or 0)
            _tx["done"] = int(_ts.get("done") or 0)
            _tx["current"] = str(_ts.get("current") or "")
            return {"success": True, "data": {
                "counts": _cnt,
                "pulling": bool(getattr(self, "_pool_pulling", False)),
                "fetch": dict(getattr(self, "_pool_status", None) or {}),
                "running": self._task_running("pool"),
                "tx": _tx,
                "scope": str(getattr(self, "_pool_fetch_scope", constants.DEFAULT_POOL_FETCH_SCOPE) or ""),
                "types": self._pool_fetch_trans_types(),
                "servers": [{"skey": k} for k in (self._emby_clients() or {}).keys()],
                # v4.6.70：附统一任务快照，供前端 TaskGuard（人名池页也需与库页同一把锁）
                "is_running": self._is_running,
                "tasks": {
                    "scan": self._task_running("scan"),
                    "translate": self._task_running("translate"),
                    "writeback": self._task_running("writeback"),
                    "pool": self._task_running("pool"),
                    "probe": self._task_running("probe"),
                },
                # v4.6.73：统一任务状态机（报告第十五节）
                "task_state": self._task_state(),
            }}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_pool_export(self):
        """导出人名池全部 Person（JSON；备份 / 迁移用）。"""
        try:
            dbm = getattr(self, "_name_map_db", None) or NameMapDb()
            rows = dbm.export_pool(plugin_id=self.__class__.__name__)
            return {"success": True, "data": rows, "count": len(rows)}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_pool_import(self, data: Optional[dict] = None):
        """导入 Person 到人名池（JSON 数组；带译文的以 manual 覆盖）。"""
        _g = self._api_gate()
        if _g:
            return _g
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            data = data or {}
            rows = data.get("rows") or data.get("records") or []
            if isinstance(rows, dict):
                rows = rows.get("rows") or rows.get("records") or []
            if not rows:
                return {"success": False, "message": "没有可导入的人名池数据"}
            # UI-007：后端兜底限制单次导入记录数（前端已限制文件大小/行数，
            # 此处防止绕过 UI 的超大请求体打爆内存）
            _max_rows = 50000
            if not isinstance(rows, (list, tuple)):
                return {"success": False, "message": "导入数据格式不正确（应为数组）"}
            if len(rows) > _max_rows:
                return {"success": False,
                        "message": f"记录数过多（{len(rows)} 条，上限 {_max_rows} 条）：请拆分后再导入"}
            dbm = getattr(self, "_name_map_db", None) or NameMapDb()
            n = dbm.import_pool(plugin_id=self.__class__.__name__, rows=rows)
            self._push_log("INFO", f"已导入人名池 {n} 人")
            return {"success": True, "message": f"已导入 {n} 人", "data": {"imported": n}}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_pool_clear(self):
        """清空人名池全部条目（含人工修正）—— 前端「清除人名池」双确认后调用。"""
        _g = self._api_gate()
        if _g:
            return _g
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            dbm = getattr(self, "_name_map_db", None) or NameMapDb()
            n = dbm.clear_all(plugin_id=self.__class__.__name__)
            _note = ""
            if bool(getattr(self, "_tx_requested", False)):
                _note = ("；翻译作业进行中：取不到待翻会自动回「待命」；"
                         "若刚有一批在请求中，其译文可能稍后写回池（少量残留，可再清一次）")
                self._push_log("WARNING", "清除人名池：翻译作业进行中 —— 当前批次若在请求中，其译文可能稍后写回池（少量残留）")
            self._push_log("INFO", f"已清除人名池：删除 {n} 人（含人工修正；第二排角色译文缓存保留）")
            return {"success": True, "message": f"已清除人名池（{n} 人）{_note}", "data": {"cleared": n}}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_pool_fetch(self, data: Optional[dict] = None):
        """拉取 Emby Person 入池（后台线程；进度见 /pool/status）。"""
        _g = self._api_gate()
        if _g:
            return _g
        _err = self._launch_bg(self._pool_fetch_worker, dict(data or {}), task="pool")
        if _err:
            return _err
        self._push_log("INFO", "已触发拉取人名（Emby Person → 人名池，后台执行；期间入库事件自动排队）")
        return {"success": True, "message": "拉取人名已启动（进度见本页顶部）"}

    def _api_pool_rescreen(self, data: Optional[dict] = None):
        """按当前「翻译范围」重筛池 —— 删除类型不在翻译范围内的池管理条目（文档 §2.3）。"""
        _g = self._api_gate()
        if _g:
            return _g
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            data = data or {}
            _types = data.get("types")
            if not isinstance(_types, list) or not _types:
                # v4.6.108（LIB-016）：白名单取**「翻译范围」的类型开关**（与接口语义 / 按钮文案一致）。
                # 此前取的是「拉取类型」（_pool_fetch_trans_types，默认只有 演员+声优）——
                # 两个口径不同：用户开着「客串」时，客串行会被误判成「类型不符」。
                _tr_now = self._collect_trans_types().get("translate", {}) or {}
                _types = [t for t, k in self.TX_TYPE_SWITCH.items() if bool(_tr_now.get(k))]
            _types = [str(t).strip() for t in _types if str(t).strip()]
            if not _types:
                # 白名单为空 = 一个类型开关都没开：此时「全都类型不符」会把池清空，
                # 明确拒绝而不是静默删库。
                return {"success": False,
                        "message": "当前「翻译范围」一个类型开关都没开 —— 重筛会把池清空，已拒绝。请先勾选要保留的类型"}
            _keep_unknown = data.get("keep_unknown")
            if _keep_unknown is None:
                _keep_unknown = bool(getattr(self, "_pool_keep_unknown", True))
            else:
                _keep_unknown = bool(_keep_unknown)
            dbm = getattr(self, "_name_map_db", None) or NameMapDb()
            # v4.6.108（LIB-016）：include_no_id=True —— 扫描入库的「无 Emby Person ID 缓存行」
            # 此前**不参与**重筛（旧实现只清带 ID 的池管理条目），于是从「客串」门禁漏进来的
            # 导演/编剧/制片缓存行点多少次重筛都清不掉；现在一并按类型白名单清理。
            _n = dbm.remove_non_matching_types(plugin_id=self.__class__.__name__, allowed_types=_types,
                                               keep_unknown=_keep_unknown, include_no_id=True)
            self._push_log("INFO", f"人名池重筛完成：按「翻译范围」类型（{'、'.join(_types)}）不匹配的 {_n} 个条目已移出池")
            return {"success": True, "message": f"已按当前设置重筛：移除 {_n} 个类型不符的人名", "data": {"removed": _n}}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_pool_update(self, data: Optional[dict] = None):
        """单条池编辑（改池 + **同步回写「库」第一排全库同名**；同步 Emby 走 /pool/sync_one）。"""
        _g = self._api_gate()
        if _g:
            return _g
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            data = data or {}
            _orig = str(data.get("name_original") or "").strip()
            _zh = str(data.get("name_zh") or "").strip()
            if not _orig:
                return {"success": False, "message": "缺少 name_original（原文名）"}
            dbm = getattr(self, "_name_map_db", None) or NameMapDb()
            ok = dbm.set_pool_zh(plugin_id=self.__class__.__name__,
                                 server_id=str(data.get("server_id") or ""),
                                 emby_person_id=str(data.get("emby_person_id") or ""),
                                 name_original=_orig, name_zh=_zh, source="manual")
            if not ok:
                return {"success": False, "message": "池中未找到该条目（可先拉取人名）"}
            self._pool_lu_cache = None  # 池已变 → 查表缓存作废
            # v4.6.58：池里改了译名 → 同步回写「库」的第一排（person 表，全库同名），
            # 否则库页第一排还停在旧译名，两边不一致。留空 = 恢复原文（写回原文名）。
            _n_lib = 0
            try:
                _pdb = getattr(self, "_people_db", None)
                if _pdb is not None:
                    _target = _zh or _orig
                    _n_lib = int(_pdb.update_by_name(plugin_id=self.__class__.__name__,
                                                     name_before=_orig, name_after=_target) or 0)
            except Exception as _e:
                logger.debug(f"[Pool] 库第一排同步失败（非致命）: {_e}")
            try:
                self._db_items_cache = None      # 库列表缓存作废 → 库页立即看到新译名
            except Exception:
                pass
            self._push_log("INFO", f"人名池人工修正：{_orig} → {_zh or '（清空/恢复原文）'}"
                                   f"（manual 最高优先级，AI 不覆盖；已同步库第一排 {_n_lib} 处）")
            return {"success": True,
                    "message": f"已保存池译文：{_orig} → {_zh or '（清空/恢复原文）'}"
                               f"；库第一排同步 {_n_lib} 处",
                    "data": {"updated_db": _n_lib}}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_pool_translate(self, data: Optional[dict] = None):
        """批量翻译池中待翻人名 —— 交常驻翻译 worker（不新建 LLM 路径）；
        翻译后是否同步 Emby 由本次 data.sync_after 决定，**默认关闭**（文档 §四）。
        常驻偏好见 pool_auto_sync；二者不混用（一次性 sync_after ≠ 长期 pool_auto_sync）。"""
        _g = self._api_gate()
        if _g:
            return _g
        # v4.6.76（规范 §十一）：统一任务忙碌门禁 —— 本接口会改 name_map / 人物池 / 起池翻译，
        # 与翻译 worker / 池 worker 并发会互相覆盖。
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            data = data or {}
            dbm = getattr(self, "_name_map_db", None) or NameMapDb()
            _cnt = dbm.count_pool_status(plugin_id=self.__class__.__name__) or {}
            _pending = int(_cnt.get("pending") or 0)
            if _pending <= 0:
                return {"success": True, "message": "人名池没有待翻译的条目", "data": {"pending": 0}}
            # v4.6.61（P1-SET-04）：后端执行门控 —— AI 总开关关闭时拒绝池批量翻译（不依赖前端置灰）
            if not self._ai_enabled():
                return {"success": False,
                        "message": "AI 翻译总开关已关闭（设置页「启用 AI 翻译」）—— 人名池批量翻译依赖 AI，请先开启"}
            # v4.6.75（规范 §三-1/2）：人名池 = 第一排 —— 目标范围不含第一排 / 第一排总开关关闭
            # 时明确拒绝（此前会静默启动但 worker 跳过，池一直停在「待翻译」）。
            _tr_now = self._collect_trans_types().get("translate", {})
            if not (self._tx_scope_allows("person") and bool(_tr_now.get("person", True))):
                return {"success": False,
                        "message": "当前翻译范围不含第一排人名（如「仅第二排角色」或第一排总开关关闭）—— "
                                   "人名池翻译已跳过；如需翻译人名，请在设置页开启第一排（或把目标范围改为含第一排）"}
            _sync_after = bool(data.get("sync_after", False))
            self._pool_sync_after_translate = _sync_after
            self._tx_request_consume(source="pool")
            self._push_log("INFO", f"人名池批量翻译已启动：{_pending} 个待翻人名（后台翻译 worker 自动消费"
                                   f"{('，完成后自动同步 Emby' if _sync_after else '')}）")
            return {"success": True, "message": f"已交后台翻译（{_pending} 个待翻人名）",
                    "data": {"pending": _pending, "sync_after": _sync_after}}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_pool_sync(self, data: Optional[dict] = None):
        """批量同步池中「待同步」条目到 Emby（后台线程）。"""
        _g = self._api_gate()
        if _g:
            return _g
        # v4.6.76（规范 §十一）：统一任务忙碌门禁 —— 本接口会改 name_map / 人物池 / 起池翻译，
        # 与翻译 worker / 池 worker 并发会互相覆盖。
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            dbm = getattr(self, "_name_map_db", None) or NameMapDb()
            _cnt = dbm.count_pool_status(plugin_id=self.__class__.__name__) or {}
            _n = int(_cnt.get("translated") or 0)
            if _n <= 0:
                return {"success": True, "message": "没有待同步的人名（池里没有「已翻译未同步」的条目）"}
            _err = self._launch_bg(self._pool_sync_worker, dict(data or {}), task="pool")
            if _err:
                return _err
            self._push_log("INFO", f"人名池批量同步已启动：{_n} 个待同步人名（Emby Person 改名，后台执行）")
            return {"success": True, "message": f"批量同步已启动（{_n} 个待同步）", "data": {"pending": _n}}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_pool_sync_one(self, data: Optional[dict] = None):
        """单条同步到 Emby（池编辑弹窗的「同步到 Emby」按钮）。"""
        _g = self._api_gate()
        if _g:
            return _g
        # v4.6.76（规范 §十一）：统一任务忙碌门禁 —— 本接口会改 name_map / 人物池 / 起池翻译，
        # 与翻译 worker / 池 worker 并发会互相覆盖。
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            data = data or {}
            _orig = str(data.get("name_original") or "").strip()
            _zh = str(data.get("name_zh") or "").strip()
            if not _orig:
                return {"success": False, "message": "缺少 name_original（原文名）"}
            _target = pool_target_name({"name_original": _orig, "name_zh": _zh})
            if not _target:
                return {"success": False, "message": "无有效目标名（原文非中文且无译文）"}
            _skey = str(data.get("server_id") or "")
            cli, _cerr = self._emby_client_for_server(_skey)
            if cli is None:
                return {"success": False, "message": _cerr or "Emby 未配置或不可用"}
            _sr = self._pool_sync_one_row(cli, person_id=str(data.get("emby_person_id") or ""),
                                          name_original=_orig, name_zh=_zh,
                                          name_current=str(data.get("name_current") or ""))
            dbm = getattr(self, "_name_map_db", None) or NameMapDb()
            _now = datetime.now().isoformat(timespec="seconds")
            _disp = _target if _target != _orig else f"{_orig}（已是目标名）"
            if _sr.get("ok"):
                dbm.update_pool_status(plugin_id=self.__class__.__name__, server_id=_skey,
                                       emby_person_id=str(data.get("emby_person_id") or ""),
                                       name_original=_orig,
                                       translation_status=("translated" if _target != _orig else "no_change"),
                                       sync_status="synced", sync_error="", last_sync_at=_now,
                                       name_current=_target)
                self._push_log("INFO", f"人名池同步：{_orig} → {_target} · {_sr.get('reason')}")
                return {"success": True, "message": f"{_sr.get('reason')}：{_disp}", "data": _sr}
            dbm.update_pool_status(plugin_id=self.__class__.__name__, server_id=_skey,
                                   emby_person_id=str(data.get("emby_person_id") or ""),
                                   name_original=_orig, sync_status="failed",
                                   sync_error=str(_sr.get("reason") or ""))
            self._push_log("WARNING", f"人名池同步失败：{_orig} → {_target}（{_sr.get('reason')}）")
            return {"success": False, "message": f"同步失败：{_sr.get('reason')}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_pool_refetch_one(self, data: Optional[dict] = None):
        """单条「重新拉取」——按身份（server_id + emby_person_id / 原名）从 Emby 重取该人事实，
        刷新池行的「Emby 当前名 / 类型」，并给 legacy 无 ID 行补上 Person ID。
        不覆盖已有译文、不动同步状态（只刷新 Emby 事实）。"""
        _g = self._api_gate()
        if _g:
            return _g
        # v4.6.99（P1-04）：本接口会查询 Emby Person 并**更新/补全人名池记录**（数据修改），
        # 必须与其它数据变更操作共用统一任务忙碌门禁 —— 不能只靠前端禁用按钮保护。
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            data = data or {}
            _orig = str(data.get("name_original") or "").strip()
            _pid_in = str(data.get("emby_person_id") or "").strip()
            _skey = str(data.get("server_id") or "").strip()
            if not _orig and not _pid_in:
                return {"success": False, "message": "缺少 name_original / emby_person_id"}
            cli, _cerr = self._emby_client_for_server(_skey)
            if cli is None:
                return {"success": False, "message": _cerr or "Emby 未配置或不可用"}
            p = None
            if _pid_in:
                try:
                    p = cli.get_person_by_id(_pid_in)
                except Exception:
                    p = None
            if not (p and str(p.get("Id") or "").strip()):
                _cands = []
                try:
                    _cands = cli.find_persons_by_name(_orig) or []
                except Exception:
                    _cands = []
                if len(_cands) == 1:
                    p = _cands[0]
                elif len(_cands) > 1:
                    return {"success": False,
                            "message": f"Emby 有 {len(_cands)} 个同名「{_orig}」，无法确定要重拉哪一个"
                                       f"（建议先「拉取人名」补齐 Person ID 再点重拉）"}
            if not (p and str(p.get("Id") or "").strip()):
                return {"success": False, "message": f"Emby 未找到该人物「{_orig or _pid_in}」"}
            _pid = str(p.get("Id") or "").strip()
            _cur = str(p.get("Name") or "").strip() or _orig
            _pid_name = self.__class__.__name__
            dbm = getattr(self, "_name_map_db", None) or NameMapDb()
            self._name_map_db = dbm
            # 定位现有池行：先按 ID → 再按原名（含跨服务器，覆盖 legacy 无 ID 行）
            _ex = None
            try:
                _ex = dbm.find_pool_person(plugin_id=_pid_name, server_id=_skey, emby_person_id=_pid)
            except Exception:
                _ex = None
            if _ex is None:
                try:
                    _lst = dbm.find_pool_persons_by_name(plugin_id=_pid_name,
                                                         name_original=_orig, server_id=_skey) or []
                    if not _lst:
                        _lst = dbm.find_pool_persons_by_name(plugin_id=_pid_name,
                                                             name_original=_orig, server_id="") or []
                    _ex = _lst[0] if _lst else None
                except Exception:
                    _ex = None
            _orig_keep = str((_ex or {}).get("name_original") or "").strip() or _orig or _cur
            _pt = str((_ex or {}).get("person_type") or "").strip()
            _pts: list = []
            try:
                _pts = json.loads(str((_ex or {}).get("person_types") or "") or "[]")
            except Exception:
                _pts = []
            _pts = [str(x) for x in _pts if str(x).strip()]
            if _ex is not None:
                _ex_sid = str(_ex.get("server_id") or "").strip()
                _ex_pid = str(_ex.get("emby_person_id") or "").strip()
                if _ex_pid:
                    dbm.upsert_pool_person(plugin_id=_pid_name, server_id=_ex_sid, emby_person_id=_ex_pid,
                                           name_original=_orig_keep, name_current=_cur,
                                           person_type=_pt, person_types=(_pts or ([_pt] if _pt else [])))
                else:
                    # legacy 无 ID 行：就地补 ID（不新增重复行），再刷新 Emby 当前名
                    dbm.bind_pool_person_id(plugin_id=_pid_name, server_id=_ex_sid,
                                            name_original=_orig_keep, emby_person_id=_pid)
                    dbm.update_pool_status(plugin_id=_pid_name, server_id=_ex_sid,
                                           emby_person_id="", name_original=_orig_keep,
                                           name_current=_cur)
            else:
                dbm.upsert_pool_person(plugin_id=_pid_name, server_id=_skey, emby_person_id=_pid,
                                       name_original=_orig_keep, name_current=_cur,
                                       person_type=_pt, person_types=(_pts or ([_pt] if _pt else [])))
            self._push_log("INFO", f"人名池重新拉取：{_orig_keep} → Emby 当前名「{_cur}」"
                                   f"（PersonId {_pid}）")
            return {"success": True,
                    "message": f"已重新拉取「{_orig_keep}」：Emby 当前名 {_cur}",
                    "data": {"emby_person_id": _pid, "name_current": _cur}}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _get_series_executor(self):
        """获取/懒创建 Series 展开有界线程池（单例）。

        并发上限 = _series_max_workers（配置项 series_max_workers，默认 3，夹 1~4）。
        若用户改过配置导致并发数变化，则重建池（旧池 shutdown(wait=False) 归还线程）。
        池不可用（创建失败）时返回 None，调用方退化为原「一事件一线程（daemon）」。
        """
        try:
            _mw = int(getattr(self, "_series_max_workers", constants.DEFAULT_SERIES_MAX_WORKERS)
                      or constants.DEFAULT_SERIES_MAX_WORKERS)
        except Exception:
            _mw = constants.DEFAULT_SERIES_MAX_WORKERS
        _mw = max(1, min(4, _mw))
        _ex = getattr(self, "_series_executor", None)
        if _ex is not None and int(getattr(self, "_series_executor_workers", 0) or 0) == _mw:
            return _ex
        # 并发数变化 / 首次：重建（旧池异步回收）
        if _ex is not None:
            try:
                _ex.shutdown(wait=False)
            except Exception:
                pass
        try:
            _ex = ThreadPoolExecutor(max_workers=_mw, thread_name_prefix="epl-series")
            self._series_executor = _ex
            self._series_executor_workers = _mw
            logger.info(f"[Webhook] Series 展开线程池已就绪（max_workers={_mw}）")
            return _ex
        except Exception as e:
            logger.warning(f"[Webhook] Series 展开线程池创建失败，退化为独立线程: {e}")
            self._series_executor = None
            self._series_executor_workers = 0
            return None

    def _submit_series_expand(self, client, item: dict, item_id: str,
                              server_id: str, display_title: str,
                              added_count: int = 0) -> None:
        """把 Series/Season 展开翻译提交到有界线程池。

        原实现每遇到一个 Series 事件就 new 一个 Thread —— 大批剧集入库时线程数无上限。
        这里统一入池（并发 ≤ _series_max_workers）；池满时任务在池内排队，不新开线程。
        提交失败 → 同步执行兜底（保持旧行为，绝不丢任务）。注意：LLM 仍走统一 limiter，
        并发数不会绕过限速（翻译本身在 _translate_worker / 池命中链内串行收口）。
        v4.6.92：`added_count` = 通知里的「本次新增条目数」（整剧入库判定用），原样透传。
        """
        try:
            _ex = self._get_series_executor()
            if _ex is not None:
                _ex.submit(self._translate_series_expanded, client, item, item_id,
                           server_id, display_title, added_count)
                return
        except Exception as e:
            logger.warning(f"[Webhook] Series 展开入池失败，退化为独立线程: {e}")
        try:
            threading.Thread(target=self._translate_series_expanded,
                             args=(client, item, item_id, server_id, display_title, added_count),
                             daemon=True, name=f"epl-series-{item_id}").start()
        except Exception:
            # 线程创建失败：退化为同步执行（保持旧行为，不丢任务）
            self._translate_series_expanded(client, item, item_id, server_id, display_title, added_count)

    # ============================================================
    # ============================================================
    TX_BATCH = 30          # 单批词条数（context_length 超限自动折半，成功后再放大）
    TX_BATCH_MIN = 1
    TX_SKIP_AFTER = 3      # 同一词条连续失败 N 次 → 本会话跳过（留 DB + 进失败清单，可手动重试）
    TX_TYPE_SWITCH = {"Actor": "actor", "VoiceActor": "actor", "GuestStar": "guest",
                      "Director": "director", "Writer": "writer", "Producer": "producer"}
    POOL_FETCH_TYPE_DEFAULT = ("Actor", "VoiceActor")   # 人名池「拉取类型」默认（演员 + 声优）

    def _tx_wake(self) -> None:
        """唤醒翻译 worker（扫描/库内翻译收尾、Webhook 入队等有新 pending 时调用）。"""
        try:
            _ev = getattr(self, "_tx_event", None)
            if _ev is None:
                self._tx_event = _ev = threading.Event()
            _ev.set()
        except Exception:
            pass

    def _tx_stop_requested(self) -> bool:
        """翻译 worker 只读自己的停止位 —— 停扫描/停写回不会误停翻译。"""
        if not getattr(self, "_enabled", False):
            return True
        return bool(getattr(self, "_tx_stop", False))

    def _tx_state_snapshot(self, pool_counts=None) -> dict:
        """翻译 Worker 状态快照 —— 统一「在线/待命/翻译中/限流暂停/认证暂停/配额暂停」语义。
        online 仅表示常驻线程存活；requested 仅在获得消费许可时为真；paused 表示当前因 LLM 原因暂停：
          - rate_limited：429 熔断窗口内（窗口过后自动续翻）
          - quota_exceeded / authentication_failed：硬停 30 分钟（需人工介入）
        前端据此渲染，绝不能把 online=true 显示成「翻译中」。
        """
        _now = time.time()
        _hard_until = float(getattr(self, "_tx_hard_until", 0) or 0)
        _rl_until = float(getattr(self, "_rate_limited_until", 0) or 0)
        _paused, _left = "", 0.0
        if _now < _hard_until:
            _paused = str(getattr(self, "_tx_hard_kind", "") or "quota_exceeded")
            _left = max(0.0, _hard_until - _now)
        elif _now < _rl_until:
            _paused = "rate_limited"
            _left = max(0.0, _rl_until - _now)
        return {
            "online": bool(getattr(getattr(self, "_tx_thread", None), "is_alive", lambda: False)()),
            "requested": bool(getattr(self, "_tx_requested", False)),
            "pending": int((pool_counts or {}).get("pending") or 0),
            "paused": _paused,
            "pause_left": int(_left),
            "user_paused": bool(getattr(self, "_tx_paused", False)),
            "scope": self._tx_scope_label(),
        }

    def _start_translate_worker(self) -> None:
        """启动常驻翻译 worker（单例防重：热加载/重复 init 不产生第二份，文档 §41）。"""
        try:
            _t = getattr(self, "_tx_thread", None)
            if _t is not None and _t.is_alive():
                return
            # 类级「当前活跃 worker 实例」——热加载后旧实例的 worker 检测到被接管会自行退出
            self.__class__._tx_active = self
            self._tx_stop = False
            self._tx_event = getattr(self, "_tx_event", None) or threading.Event()
            # v4.6.61（P1-6）：重启恢复 —— 未完成 Job 标记 interrupted；force 任务重新入队
            self._tx_job_recover()
            self._tx_thread = threading.Thread(target=self._translate_worker,
                                               daemon=True, name="epl-translate")
            self._tx_thread.start()
            logger.info("[Translate] 翻译 worker 已启动（常驻：消费人物库/人名池待翻词条；限流自动熔断）")
        except Exception as e:
            logger.warning(f"[Translate] worker 启动失败: {e}")

    def _rl_enter(self, retry_after=None) -> float:
        """进入限流熔断 —— 优先用 Retry-After，否则指数退避 60→120→240→600（带抖动）。"""
        _s = int(getattr(self, "_rl_strikes", 0) or 0)
        _base = min(600.0, 60.0 * (2 ** min(_s, 3)))
        try:
            _w = float(retry_after) if retry_after else _base
        except Exception:
            _w = _base
        _w = max(1.0, _w * (0.8 + 0.4 * random.random()))
        self._rl_strikes = _s + 1
        self._rate_limited_until = time.time() + _w
        if self._llm is not None:
            try:
                self._llm.rate_limited_until = self._rate_limited_until
            except Exception:
                pass
        return _w

    def _rl_ok(self) -> None:
        """翻译成功后恢复（半开 → 关闭）：清退避计数与窗口。"""
        self._rl_strikes = 0
        self._rate_limited_until = 0.0
        if self._llm is not None:
            try:
                self._llm.rate_limited_until = 0.0
            except Exception:
                pass

    def _pool_lookup_cached(self) -> dict:
        """人名池查表缓存（60s TTL；翻译 worker 每轮都要用，避免反复整表加载）。
        返回值是【全局翻译记忆】(键 = (term_type, 原文)，跨服务器聚合)，
        只能当「词条 → 译文」的记忆命中用；Person 主数据请走身份维度 _pool_identity_zh()
        （优先 server_id + emby_person_id，再 fallback 本全局 TM），以免跨服务器互相污染。
        本方法同时刷新身份视图缓存（_pool_lu_id / _pool_lu_idname）。"""
        now = time.time()
        if (getattr(self, "_pool_lu_cache", None) is not None
                and (now - float(getattr(self, "_pool_lu_ts", 0) or 0)) < 60):
            return self._pool_lu_cache or {}
        try:
            _dbm = getattr(self, "_name_map_db", None) or NameMapDb()
            self._name_map_db = _dbm
            _pid = self.__class__.__name__
            self._pool_lu_cache = _dbm.load_map(plugin_id=_pid)
            try:
                _idmap = _dbm.load_pool_identity_map(plugin_id=_pid) or {}
            except Exception:
                _idmap = {}
            self._pool_lu_id = _idmap.get("by_id") or {}
            self._pool_lu_idname = _idmap.get("by_name") or {}
        except Exception:
            self._pool_lu_cache = {}
            self._pool_lu_id = {}
            self._pool_lu_idname = {}
        self._pool_lu_ts = now
        return self._pool_lu_cache or {}

    def _pool_identity_zh(self, server_id: str, emby_person_id: str = "",
                          name_original: str = "") -> Optional[tuple]:
        """按 Person 身份读取当前译名（人工优先的读原语）。
        顺序：① server_id + emby_person_id 精确身份 → ② server_id + 原文名 就地兜底。
        命中返回 (name_zh, source)，否则 None。同名跨服务器不会互相串用。"""
        self._pool_lookup_cached()  # 确保身份视图已加载（60s TTL）
        _sid = str(server_id or "")
        _pid = str(emby_person_id or "").strip()
        _nm = str(name_original or "").strip()
        _by_id = getattr(self, "_pool_lu_id", None) or {}
        _by_nm = getattr(self, "_pool_lu_idname", None) or {}
        if _pid:
            _hit = _by_id.get((_sid, _pid))
            if _hit and str(_hit[0] or "").strip():
                return tuple(_hit)
        if _nm:
            _hit = _by_nm.get((_sid, _nm))
            if _hit and str(_hit[0] or "").strip():
                return tuple(_hit)
        return None

    def _translate_worker(self) -> None:
        """常驻翻译 worker 主体（文档 §38：循环取 pending → 翻译 → 写 DB；空闲退避轮询）。"""
        _pid = self.__class__.__name__
        _skip: Dict[str, int] = {}
        _idle = 0
        _last_log = 0.0
        while True:
            try:
                # 热加载防重：已被新实例的 worker 接管 → 本线程退出（防双份消费，文档 §41）
                _act = getattr(self.__class__, "_tx_active", None)
                if _act is not None and _act is not self:
                    logger.info("[Translate] 检测到新实例接管，旧翻译 worker 退出")
                    return
                _ev = getattr(self, "_tx_event", None)
                if _ev is None:
                    self._tx_event = _ev = threading.Event()
                # 终止（独立停止位 / 全局停止位 / 插件禁用）
                if self._tx_stop_requested():
                    if bool(getattr(self, "_tx_requested", False)):
                        # v4.6.62（第 22 节）：终止落 Job 状态 —— 显式用户终止 = cancelled；
                        # 插件禁用/被动停止 = interrupted。pending 一律保留（取消 ≠ 删除数据）。
                        _jid_stop = str(getattr(self, "_tx_job_id", "") or "")
                        if _jid_stop:
                            try:
                                self._tx_job_set(
                                    "cancelled" if bool(getattr(self, "_tx_stop", False)) else "interrupted",
                                    finished_at=datetime.now().isoformat(timespec="seconds"),
                                    error_message="用户终止（未完成词条保留待翻）"
                                    if bool(getattr(self, "_tx_stop", False)) else "插件停止/禁用导致中断")
                            except Exception:
                                pass
                        self._tx_requested = False
                        self._tx_permit_logged = False
                        self._tx_target_scope = "both"
                        self._tx_source = ""
                        self._tx_scope_items = set()
                        self._tx_only_terms = set()
                        # v4.6.76（规范 §十三）：任务结束 → 释放 Job Snapshot（下个任务用最新设置）
                        self._tx_cfg_snapshot = None
                        self._tx_job_reset_stats()
                        self._tx_job_started = 0.0
                        try:
                            self._translate_status["running"] = False
                        except Exception:
                            pass
                        logger.info("[Translate] 已终止：归还消费许可，回到待命（pending/断点保留，可随时继续）")
                    _ev.wait(1.0); _ev.clear(); continue
                self._llm_reload_if_idle()
                if bool(getattr(self, "_tx_skip_clear", False)):
                    _skip.clear()
                    self._tx_noop_terms = set()   # v4.6.102：与失败跳过同生命周期（改设置/终止即清）
                    self._tx_skip_clear = False
                # 库内全部翻译（手动）进行中 → 让位（避免同一批词条两条 LLM 路径重复翻）
                if self._task_running("translate"):
                    _ev.wait(1.0); _ev.clear(); continue
                _until = float(getattr(self, "_rate_limited_until", 0) or 0)
                if time.time() < _until:
                    _ev.wait(min(1.0, max(0.2, _until - time.time()))); _ev.clear(); continue
                # 配额/认证硬停（重试无意义，等用户充值/修 Key）
                if time.time() < float(getattr(self, "_tx_hard_until", 0) or 0):
                    _ev.wait(1.0); _ev.clear(); continue
                if self._task_paused("translate"):
                    try:
                        if self._translate_status.get("running"):
                            self._translate_status["running"] = False
                    except Exception:
                        pass
                    if not bool(getattr(self, "_tx_pause_logged", False)):
                        self._tx_pause_logged = True
                        logger.info("[Translate] 翻译已暂停（手动）：不再发起新请求，词条保留待续")
                        try:
                            self._push_log("INFO", "翻译已暂停（手动）：当前批次完成后不再发起新请求，点「继续」恢复")
                        except Exception:
                            pass
                    _ev.wait(1.0); _ev.clear(); continue
                if bool(getattr(self, "_tx_pause_logged", False)):
                    self._tx_pause_logged = False
                    logger.info("[Translate] 翻译已继续：恢复消费待翻词条")
                    try:
                        self._push_log("INFO", "翻译已继续：恢复消费待翻词条")
                    except Exception:
                        pass
                if not bool(getattr(self, "_tx_requested", False)):
                    # v4.6.113（P2）：空闲时启动下一个待恢复的强制重翻任务（逐个恢复，
                    # 每个任务保留自己的 job_id / 范围 / 条目）
                    if getattr(self, "_tx_recover_queue", None):
                        self._tx_recover_pump()
                        if bool(getattr(self, "_tx_requested", False)):
                            continue
                    _ev.wait(2.0); _ev.clear(); continue
                if not bool(getattr(self, "_tx_permit_logged", False)):
                    self._tx_permit_logged = True
                    try:
                        # v4.6.61：统一快照（唯一口径）—— 徽章 / 明细 / 日志完全同源；
                        # pool_gate=True：池按本次作业来源门控（与 worker 实际消费一致）
                        # v4.6.106（LIB-013）：source_gate=True —— 库内同样按来源门控，
                        # 否则「人名池 · 批量翻译」的进度分母会把库内人名/角色也算进来（数字对不上）。
                        _snap0 = self._tx_pending_snapshot(pool_gate=True, source_gate=True,
                                                           with_detail=True)
                        _pend = int(_snap0.get("total") or 0)
                        _job_id0 = str(getattr(self, "_tx_job_id", "") or "")
                        _scope0 = self._tx_scope()
                        _src0 = str(getattr(self, "_tx_source", "") or "both")
                        _mode0 = str(getattr(self, "_translate_batching", "per_title") or "per_title")
                        _items0 = len(set(getattr(self, "_tx_scope_items", None) or ())) or int(_snap0.get("items") or 0)
                        logger.info(f"[TranslateJob] job={_job_id0} source={_src0} scope={_scope0} "
                                    f"items={_items0} terms={_pend} mode={_mode0} 收到翻译许可，开始消费待翻词条"
                                    f"（目标 = {self._tx_scope_label()}；人名 {_snap0.get('person', 0)} / "
                                    f"角色 {_snap0.get('role', 0)} / 池 {_snap0.get('pool', 0)}）")
                        self._tx_job_reset_stats()
                        self._tx_job_total = max(0, int(_pend or 0))
                        self._tx_job_started = time.time()
                        self._tx_autosync_res = None
                        # v4.6.61（P1-6）：Job 转 running（SQLite 持久化，UI/重启可查）
                        self._tx_job_set("running",
                                         started_at=datetime.now().isoformat(timespec="seconds"),
                                         item_count=int(_items0 or 0), term_count=int(_pend or 0),
                                         batch_mode=_mode0, batch_size=int(getattr(self, "_tx_batch", 0) or 0),
                                         remaining_count=int(_pend or 0))
                        # v4.6.64（第 24 节）：登记本 Job 的 occurrences（term_id = occ_id，
                        # 带 season/episode/person_index —— 同名分属不同作品不会互相扩散）
                        try:
                            _trows = [{"term_id": o["occ_id"], "original_text": o["text"],
                                       "item_id": o["item_id"], "server_id": o["server_id"],
                                       "season_num": o.get("season_num"),
                                       "episode_num": o.get("episode_num"),
                                       "person_index": o.get("person_index") or 0,
                                       "kind": ("role" if o["kind"] == "role" else "person"),
                                       "person_type": o.get("person_type")}
                                      # v4.6.112（GH#3-7）：复用候选队列（同一份全表结果），
                                      # 不再为「登记 Job 词条」多跑一次全表聚合
                                      for o in (self._tx_occ_queue(pid).get("occs") or [])]
                            self._tx_register_job_terms(_trows)
                        except Exception:
                            pass
                        # v4.6.60（P1-3）+ v4.6.61（P2-2）：记录本轮 LLM 计数基线（结束取差值）
                        try:
                            _l0 = getattr(self, "_llm", None)
                            self._tx_req0 = ({k: int(getattr(_l0, k, 0) or 0)
                                              for k in ("stat_requests", "stat_success", "stat_failed",
                                                        "stat_rate_limited", "stat_quota",
                                                        "stat_tokens_in", "stat_tokens_out",
                                                        "stat_latency_ms")}
                                             if _l0 is not None else {})
                        except Exception:
                            self._tx_req0 = {}
                    except Exception:
                        pass
                _scope_items = set(getattr(self, "_tx_scope_items", None) or ())
                # 条目级重翻（「重新翻译」单条）→ 跳过全库待翻扫描，仅由 _tx_force_round 重翻指定条目
                _st = None if _scope_items else self._translate_pending_round(_pid, _skip)
                _fst = self._tx_force_round(_pid, _skip) if self._tx_source_allows("library") else None
                if _fst:
                    if not _st:
                        _st = {"did": True, "done": 0, "llm": 0, "hits": 0, "failed": 0,
                               "deferred": 0, "left": 0, "current": ""}
                    _st["did"] = True
                    for _k in ("done", "llm", "hits", "failed"):
                        _st[_k] = int(_st.get(_k) or 0) + int(_fst.get(_k) or 0)
                    # v4.6.74：强制重翻（条目级重翻）同样产出分排统计 —— 合并进本轮 by_kind，
                    # 否则通知里「第一排/第二排」恒显示 0（重翻明明翻了词条）。
                    if isinstance(_fst.get("by_kind"), dict):
                        _bk1 = _st.get("by_kind")
                        if not isinstance(_bk1, dict):
                            _bk1 = _st["by_kind"] = {
                                "person": {"done": 0, "llm": 0, "pool": 0, "role_mem": 0,
                                           "tmdb": 0, "zhconv": 0, "llm_zhc": 0, "failed": 0},
                                "role": {"done": 0, "llm": 0, "pool": 0, "role_mem": 0,
                                         "tmdb": 0, "zhconv": 0, "llm_zhc": 0, "failed": 0}}
                        for _k2, _v2 in _fst["by_kind"].items():
                            if _k2 in _bk1 and isinstance(_v2, dict):
                                for _f2 in ("done", "llm", "pool", "role_mem", "tmdb",
                                            "zhconv", "llm_zhc", "failed"):
                                    _bk1[_k2][_f2] = int(_bk1[_k2].get(_f2) or 0) + int(_v2.get(_f2) or 0)
                    if _fst.get("current"):
                        _st["current"] = _fst["current"]
                if not _st or not _st.get("did"):
                    # 条目级重翻任务尚未翻完（限流/延时/缩批）→ 保留消费许可，稍后续翻，不归还任务字段
                    if bool(getattr(self, "_tx_force_jobs", None)) and not self._tx_stop_requested():
                        _idle += 1
                        _wait = 1.0 if _idle < 3 else (2.0 if _idle < 10 else 5.0)
                        if self._translate_status.get("running"):
                            self._translate_status["running"] = False
                        _ev.wait(_wait); _ev.clear(); continue
                    if getattr(self, "_pool_sync_after_translate", False) or getattr(self, "_pool_auto_sync", False):
                        try:
                            _pc = (getattr(self, "_name_map_db", None) or NameMapDb()).count_pool_status(plugin_id=_pid) or {}
                            if int(_pc.get("pending") or 0) <= 0:
                                self._pool_sync_after_translate = False
                                _sr = self._pool_sync_all(ctx="翻译完成自动同步")
                                if _sr.get("total"):
                                    self._push_log("INFO", f"人名池翻译完成 → 自动同步 Emby：{_sr.get('message')}")
                                    self._tx_autosync_res = dict(_sr)
                        except Exception as _pe:
                            self._pool_sync_after_translate = False
                            logger.debug(f"[Translate] 池翻译后自动同步失败（非致命）: {_pe}")
                    if bool(getattr(self, "_tx_requested", False)):
                        _scope_lbl = self._tx_scope_label()   # 复位前先取标签，供结束日志正确显示
                        _job_done = int(getattr(self, "_tx_job_done", 0) or 0)
                        _job_failed = int(getattr(self, "_tx_job_failed", 0) or 0)
                        _job_llm = int(getattr(self, "_tx_job_llm", 0) or 0)
                        _job_hits = int(getattr(self, "_tx_job_hits", 0) or 0)
                        # v4.6.70（P0-1/P0-2）：复位前捕获拆分统计（池命中 / 繁转简 / LLM 输出简体化 / 分排）
                        _job_pool = int(getattr(self, "_tx_job_pool", 0) or 0)
                        _job_zhconv = int(getattr(self, "_tx_job_zhconv", 0) or 0)
                        _job_llm_zhc = int(getattr(self, "_tx_job_llm_zhc", 0) or 0)
                        # v4.6.75（规范 §四-3/§十-3）：输入条数 → 去重后唯一条数（复位前捕获）
                        _job_dedup_in = int(getattr(self, "_tx_job_dedup_in", 0) or 0)
                        _job_dedup_uniq = int(getattr(self, "_tx_job_dedup_uniq", 0) or 0)
                        _job_bk = getattr(self, "_tx_job_by_kind", None)
                        _job_started = float(getattr(self, "_tx_job_started", 0) or 0)
                        # v4.6.61：结束统计必须**含库内人名 + 角色 + 池**（复位前按本轮范围取快照，
                        # 池按本次来源门控）—— 唯一口径，与徽章/明细完全同源
                        _job_scope = self._tx_scope()
                        # v4.6.106（LIB-013）：收尾统计同样按来源门控（池作业不该把库内人头算进「剩余」）
                        _snap2 = self._tx_pending_snapshot(_job_scope, pool_gate=True,
                                                           source_gate=True, with_detail=True)
                        _job_id_txt = str(getattr(self, "_tx_job_id", "") or "")
                        # v4.6.61（P1-7）：写回状态独立统计 —— 翻译完成 ≠ 写回完成
                        _wb_st: dict = {}
                        try:
                            _wb_st = self._wb_db().stats(plugin_id=_pid)
                        except Exception:
                            _wb_st = {}
                        _wb_pend = int(_wb_st.get("writeback_pending") or 0)
                        self._tx_requested = False
                        self._tx_permit_logged = False
                        self._tx_target_scope = "both"
                        self._tx_source = ""
                        self._tx_scope_items = set()
                        self._tx_only_terms = set()
                        # v4.6.76（规范 §十三）：任务结束 → 释放 Job Snapshot（下个任务用最新设置）
                        self._tx_cfg_snapshot = None
                        _left_pool = int(_snap2.get("total") or 0)
                        _elapsed = int(time.time() - _job_started) if _job_started > 0 else 0
                        # v4.6.60（P1-3）+ v4.6.61（P2-2）：本轮真实 AI 请求 / 令牌 / 延迟（差值）
                        _rq: dict = {}
                        try:
                            if getattr(self, "_llm", None) is not None:
                                _r0 = getattr(self, "_tx_req0", {}) or {}
                                _rq = {k: int(getattr(self._llm, k, 0) or 0) - int(_r0.get(k, 0))
                                       for k in ("stat_requests", "stat_success", "stat_failed",
                                                 "stat_rate_limited", "stat_quota",
                                                 "stat_tokens_in", "stat_tokens_out", "stat_latency_ms")}
                        except Exception:
                            _rq = {}
                        self._tx_req0 = {}
                        # v4.6.61（P1-6）：Job 收尾（SQLite）—— 剩余 >0 只标 partial，绝不谎报 DONE
                        _job_done_status = "done" if _left_pool <= 0 else "partial"
                        self._tx_job_set(_job_done_status,
                                         finished_at=datetime.now().isoformat(timespec="seconds"),
                                         translated_count=int(_job_done or 0),
                                         failed_count=int(_job_failed or 0),
                                         llm_request_count=int(_rq.get("stat_requests", 0) or 0),
                                         rate_limit_count=int(_rq.get("stat_rate_limited", 0) or 0),
                                         quota_error_count=int(_rq.get("stat_quota", 0) or 0),
                                         remaining_count=int(_left_pool or 0),
                                         writeback_pending_count=int(_wb_pend or 0))
                        # v4.6.62（第 24 节）：Job 明细保留策略 —— 只留最近 30 个已完成 Job，防表膨胀
                        try:
                            self._tx_job_flush_attempts()   # v4.6.64：收尾时补落剩余 attempt（如 429 中断）
                        except Exception:
                            pass
                        try:
                            self._tx_job_db().prune(plugin_id=_pid, keep=30)
                        except Exception:
                            pass
                        self._tx_job_id = ""
                        self._tx_job_status = ""
                        self._tx_job_total = 0
                        self._tx_job_done = 0
                        self._tx_job_failed = 0
                        self._tx_job_llm = 0
                        self._tx_job_hits = 0
                        # v4.6.70：拆分项一并复位（_tx_job_applied 保留至下方 _job_applied 读取之后再清）
                        self._tx_job_pool = 0
                        self._tx_job_zhconv = 0
                        self._tx_job_llm_zhc = 0
                        self._tx_job_by_kind = None
                        self._tx_job_started = 0.0
                        _tok_in = int(_rq.get("stat_tokens_in", 0) or 0)
                        _tok_out = int(_rq.get("stat_tokens_out", 0) or 0)
                        _lat_s = round(int(_rq.get("stat_latency_ms", 0) or 0) / 1000.0, 1)
                        _job_applied = int(getattr(self, "_tx_job_applied", 0) or 0)
                        self._tx_job_applied = 0   # v4.6.70：读取后再清（下次 Job 从 0 开始）
                        # v4.6.63：剩余词条明细（前 5 条）—— 让日志自证「到底剩哪些」
                        _rems: list = []
                        for _rit in (_snap2.get("items_list") or []):
                            for _rt in (_rit.get("roles") or []) + (_rit.get("names") or []):
                                if _rt and _rt not in _rems:
                                    _rems.append(_rt)
                        _rem_txt = ("，剩余词条：" + "、".join(_rems[:5])
                                    + (f" 等共 {len(_rems)} 条" if len(_rems) > 5 else "")) if _rems else ""
                        # v4.6.70（P0-2）：按第一/二排拆分统计（供日志与通知）
                        _bk = _job_bk if isinstance(_job_bk, dict) else {}
                        _pbk = _bk.get("person") or {}
                        _rbk = _bk.get("role") or {}
                        logger.info(f"[TranslateJob] job={_job_id_txt} {_job_done_status.upper()} "
                                    f"scope={_job_scope} person_terms={int(_pbk.get('done', 0) or 0)} "
                                    f"role_terms={int(_rbk.get('done', 0) or 0)} "
                                    f"完成 {_job_done}（写库 {_job_applied} 行）/ 失败 {_job_failed} / 剩余 {_left_pool}"
                                    f"（人名 {_snap2.get('person', 0)} / 角色 {_snap2.get('role', 0)} / "
                                    f"池 {_snap2.get('pool', 0)}）"
                                    # v4.6.75（规范 §四-3/§十-3）：输入 → 去重 → 记忆命中 → AI 请求 全链路自证
                                    + (f" · 输入 {_job_dedup_in} → 去重后 {_job_dedup_uniq} 条"
                                       f"（省 {_job_dedup_in - _job_dedup_uniq} 条）"
                                       if _job_dedup_in else "")
                                    + f" · 角色记忆 {int(_rbk.get('role_mem', 0) or 0)}"
                                    f" · 池命中 {_job_pool} / 繁转简 {_job_zhconv} / LLM输出简体化 {_job_llm_zhc}"
                                    f" · AI 请求 {int(_rq.get('stat_requests', 0) or 0)} 次"
                                    f"（成功 {int(_rq.get('stat_success', 0) or 0)} / 限流 {int(_rq.get('stat_rate_limited', 0) or 0)}"
                                    f" / 配额 {int(_rq.get('stat_quota', 0) or 0)}）"
                                    + (f" · 令牌 输入≈{_tok_in} / 输出≈{_tok_out}" if (_tok_in or _tok_out) else "")
                                    + (f" · API 延迟合计 {_lat_s}s" if _lat_s else "")
                                    + f" · 待写回 {_wb_pend}"
                                    + (f" · 耗时 {_elapsed} 秒" if _elapsed else "")
                                    + _rem_txt)
                        _as = getattr(self, "_tx_autosync_res", None) or {}
                        if ((_job_done or _job_failed or _as) and self._notify_guard("翻译完成")):
                            try:
                                # v4.6.70（P0-2）：第一排 / 第二排分开报；池命中与繁转简分开报（不再「池/繁简命中」）
                                # v4.6.74（报告第六 / 二十三节）：每一项单独列一行 ——
                                # LLM / 角色 Memory / 人名池 / TMDB / 繁转简 / LLM 输出简体化，
                                # 用户能明确知道每个数字是什么（不再有「池/繁简 3 条」这种口径）。
                                def _line_of(_lbl: str, _k: dict) -> str:
                                    _d = int(_k.get("done", 0) or 0)
                                    if not _d:
                                        return f"📝 {_lbl}：本次处理 0 条"
                                    _sub = [f"LLM：{int(_k.get('llm', 0) or 0)} 条"]
                                    _mem = int(_k.get("role_mem", 0) or 0)
                                    if _mem:
                                        _sub.append(f"角色 Memory：{_mem} 条")
                                    _pl = int(_k.get("pool", 0) or 0)
                                    if _pl:
                                        _sub.append(f"人名池：{_pl} 条")
                                    _tm = int(_k.get("tmdb", 0) or 0)
                                    if _tm:
                                        _sub.append(f"TMDB：{_tm} 条")
                                    _zc = int(_k.get("zhconv", 0) or 0)
                                    if _zc:
                                        _sub.append(f"繁转简：{_zc} 条")
                                    _lz = int(_k.get("llm_zhc", 0) or 0)
                                    if _lz:
                                        _sub.append(f"LLM 输出简体化：{_lz} 条")
                                    _fl = int(_k.get("failed", 0) or 0)
                                    if _fl:
                                        _sub.append(f"失败：{_fl} 条")
                                    return (f"📝 {_lbl}：完成 {_d} 条\n"
                                            + "\n".join(f"　　• {_x}" for _x in _sub))
                                self.post_message(
                                    mtype=NotificationType.Manual, title=self.plugin_name,
                                    text=(f"✅ 翻译完成（目标 = {_scope_lbl}）\n"
                                          f"{_line_of('第一排', _pbk)}\n"
                                          f"{_line_of('第二排', _rbk)}\n"
                                          + (f"🤖 AI 请求 {int(_rq.get('stat_requests', 0) or 0)} 次"
                                             f"（成功 {int(_rq.get('stat_success', 0) or 0)}"
                                             + (f" · 失败 {int(_rq.get('stat_failed', 0) or 0)}"
                                                if int(_rq.get('stat_failed', 0) or 0) else "")
                                             + (f" · 限流 {int(_rq.get('stat_rate_limited', 0) or 0)}"
                                                if int(_rq.get('stat_rate_limited', 0) or 0) else "")
                                             + (f" · 配额 {int(_rq.get('stat_quota', 0) or 0)}"
                                                if int(_rq.get('stat_quota', 0) or 0) else "")
                                             + "）\n"
                                             if int(_rq.get('stat_requests', 0) or 0) else "")
                                          # v4.6.70（P0-1）：LLM 返回繁体被系统纠正为简体的条数（独立于「繁转简」）
                                          + (f"🔤 LLM 输出简体化 {_job_llm_zhc} 条（模型返回繁体，已自动纠正）\n"
                                             if _job_llm_zhc else "")
                                          # v4.6.75（规范 §四-3/§十-3）：AI 聚合自证（输入 → 去重后唯一）
                                          + (f"🧮 AI 聚合：输入 {_job_dedup_in} 条 → 去重后 {_job_dedup_uniq} 条"
                                             f"（省 {_job_dedup_in - _job_dedup_uniq} 条重复请求）\n"
                                             if _job_dedup_in and _job_dedup_in > _job_dedup_uniq else "")
                                          + (f"❌ 失败 {_job_failed} 条（可在仪表盘失败清单重试）\n" if _job_failed else "")
                                          + f"⏳ 剩余待翻 {_left_pool} 条\n"
                                          + (f"🚚 待写回 {_wb_pend} 个条目（翻译完成 ≠ 写回完成，自动写回开启时自动落盘）\n"
                                             if _wb_pend else "")
                                          + (f"🔄 已自动同步 Emby：改名 {_as.get('renamed', 0)} · "
                                             f"已是译文 {_as.get('skipped', 0)} · 失败 {_as.get('failed', 0)} · "
                                             f"剩余待同步 {_as.get('left_sync', 0)}\n" if _as else "")
                                          + (f"⏱ 耗时 {_elapsed} 秒" if _elapsed else "")).rstrip())
                            except Exception as _ne:
                                logger.warning(f"[Notify] 翻译完成通知发送失败: {_ne}")
                            finally:
                                self._tx_autosync_res = None
                    # 空闲：渐进退避（1s → 2s → 5s），_tx_event 仍可随时唤醒
                    _idle += 1
                    _wait = 1.0 if _idle < 3 else (2.0 if _idle < 10 else 5.0)
                    if self._translate_status.get("running"):
                        self._translate_status["running"] = False
                    _ev.wait(_wait); _ev.clear(); continue
                _idle = 0
                # v4.6.61（P1-6）：有实际轮次产出 → Job 从 rate_limited/quota_paused 恢复为 running
                if str(getattr(self, "_tx_job_status", "") or "") != "running":
                    self._tx_job_set("running")
                if len(_skip) > 5000:
                    _skip.clear()
                self._tx_job_done = int(getattr(self, "_tx_job_done", 0) or 0) + int(_st.get("done") or 0)
                self._tx_job_applied = int(getattr(self, "_tx_job_applied", 0) or 0) + int(_st.get("applied") or 0)
                self._tx_job_failed = int(getattr(self, "_tx_job_failed", 0) or 0) + int(_st.get("failed") or 0)
                self._tx_job_llm = int(getattr(self, "_tx_job_llm", 0) or 0) + int(_st.get("llm") or 0)
                self._tx_job_hits = int(getattr(self, "_tx_job_hits", 0) or 0) + int(_st.get("hits") or 0)
                # v4.6.70（P0-1/P0-2）：拆分统计累加（池命中 / 繁转简 / LLM 输出简体化 / 按第一·二排）
                self._tx_job_pool = int(getattr(self, "_tx_job_pool", 0) or 0) + int(_st.get("pool") or 0)
                self._tx_job_zhconv = int(getattr(self, "_tx_job_zhconv", 0) or 0) + int(_st.get("zhconv") or 0)
                self._tx_job_llm_zhc = int(getattr(self, "_tx_job_llm_zhc", 0) or 0) + int(_st.get("llm_zhc") or 0)
                # v4.6.75（规范 §四-3）：输入条数 → 去重后唯一条数（AI 聚合自证）
                self._tx_job_dedup_in = int(getattr(self, "_tx_job_dedup_in", 0) or 0) + int(_st.get("dedup_in") or 0)
                self._tx_job_dedup_uniq = int(getattr(self, "_tx_job_dedup_uniq", 0) or 0) + int(_st.get("dedup_uniq") or 0)
                try:
                    _bk0 = getattr(self, "_tx_job_by_kind", None)
                    if not isinstance(_bk0, dict):
                        _bk0 = {"person": {"done": 0, "llm": 0, "pool": 0, "role_mem": 0, "tmdb": 0,
                                           "zhconv": 0, "llm_zhc": 0, "failed": 0},
                                "role": {"done": 0, "llm": 0, "pool": 0, "role_mem": 0, "tmdb": 0,
                                         "zhconv": 0, "llm_zhc": 0, "failed": 0}}
                    for _kk, _vv in (_st.get("by_kind") or {}).items():
                        if _kk in _bk0 and isinstance(_vv, dict):
                            for _f in ("done", "llm", "pool", "role_mem", "tmdb",
                                       "zhconv", "llm_zhc", "failed"):
                                _bk0[_kk][_f] = int(_bk0[_kk].get(_f) or 0) + int(_vv.get(_f) or 0)
                    self._tx_job_by_kind = _bk0
                except Exception:
                    pass
                _jt = int(getattr(self, "_tx_job_total", 0) or 0)
                _jd = int(getattr(self, "_tx_job_done", 0) or 0)
                self._translate_status.update({
                    "running": True, "phase": "translate",
                    "job": str(getattr(self, "_tx_job_id", "") or ""),
                    "status": str(getattr(self, "_tx_job_status", "") or ""),
                    "total": _jt if _jt > 0 else (int(_st.get("done") or 0) + int(_st.get("left") or 0)),
                    "done": min(_jd, _jt) if _jt > 0 else _jd,
                    "failed": int(getattr(self, "_tx_job_failed", 0) or 0), "current": str(_st.get("current") or ""),
                })
                if int(_st.get("failed") or 0) > 0:
                    self._save_state()
                # 轮次日志节流（≥15s 一条，避免刷屏）
                if time.time() - _last_log >= 15:
                    _last_log = time.time()
                    # v4.6.70（P0-2）：池命中 / 繁转简 分开报（此前合并成「池/繁简」）
                    self._push_log("INFO", f"翻译 worker：本轮 {_st.get('done', 0)} 条（LLM {_st.get('llm', 0)} 条 · "
                                           f"池命中 {_st.get('pool', 0)} 条 · 繁转简 {_st.get('zhconv', 0)} 条 · "
                                           f"LLM输出简体化 {_st.get('llm_zhc', 0)} 条 · "
                                           f"未决 {_st.get('deferred', 0)} · 失败 {_st.get('failed', 0)}），"
                                           f"剩余待翻约 {_st.get('left', 0)} 条")
            except Exception as e:
                logger.warning(f"[Translate] worker 轮次异常: {e}")
                try:
                    time.sleep(2)
                except Exception:
                    pass

    def _tx_force_round(self, pid: str, skip: Dict[str, int]) -> Optional[dict]:
        """强制重翻任务轮 —— 「重新翻译」按钮只做「入队」，
        真正重翻由本方法在常驻翻译 worker 内执行（统一限流/熔断/错误链路，无第二套翻译系统）：
          - 不复用池命中/已有译文（池查表传空 → 直接 LLM；繁转简仍可用）
          - 重翻结果覆盖该条目译文（update_by_name / update_role_by_before），并回写人名池（llm 源）
          - 不删任何已有译文（失败也不动旧值）；全部成功后把条目登记给 Writeback Worker 统一落盘
          - preview / auto_writeback 只影响「是否自动落盘」，不影响本流程（清单 §八）
        任务存内存队列 _tx_force_jobs（入队即唤醒；重启丢弃 → 再点一次「重新翻译」即可）。"""
        _jobs = getattr(self, "_tx_force_jobs", None)
        if not _jobs:
            return None
        db = getattr(self, "_people_db", None)
        dbm = getattr(self, "_name_map_db", None) or NameMapDb()
        done = llm_n = hits_n = failed = 0
        _cur = ""
        # v4.6.74（报告第六 / 二十一节）：强制重翻也要产出「分排统计」与更新「角色记忆」——
        # 此前重翻结束后角色记忆仍是旧译文（下一集又复用旧的），且通知里分排数字恒为 0。
        _bk_f = {"person": {"done": 0, "llm": 0, "pool": 0, "role_mem": 0, "tmdb": 0,
                            "zhconv": 0, "llm_zhc": 0, "failed": 0},
                 "role": {"done": 0, "llm": 0, "pool": 0, "role_mem": 0, "tmdb": 0,
                          "zhconv": 0, "llm_zhc": 0, "failed": 0}}
        for _item in list(_jobs.keys()):
            if self._tx_stop_requested():
                break
            _job = _jobs.get(_item) or {}
            _cur = str(_job.get("title") or _item)
            try:
                _scope_f = self._tx_scope()
                # v4.6.64：强制重翻也从 DB 取 occurrence（带 season/episode/person_index），
                # only_pending=False → 含已翻词条；写库用 override 覆盖。
                _occs = [o for o in self._tx_occurrences(
                    pid, item_id=_item, server_id=str(_job.get("server_id") or ""), force=True)
                    if int(skip.get(o["text"], 0) or 0) < self.TX_SKIP_AFTER
                    # v4.6.95：已是中文（含「汉字夹空格」）的词条不参与强制重翻 ——
                    # 与「重新翻译」弹窗预估（同一 _skip_no_translate 口径）保持一致，
                    # 避免「预估显示不用翻、实际却送 LLM」（用户实测：名冢 佳织 等已中文仍被翻）。
                    and not self._skip_no_translate(o["text"])
                    and ((o["kind"] == "role" and self._tx_role_type_enabled(o.get("person_type"), _scope_f))
                         or (o["kind"] != "role" and self._tx_type_enabled(o.get("person_type"), _scope_f)))]
                if not _occs:
                    _jobs.pop(_item, None)
                    continue
                _fresh: List[dict] = []
                _ok_all = True
                _res_m = self._tx_translate_mixed(_occs, {},
                                                  title=str(_job.get("title") or ""),
                                                  year=str(_job.get("year") or ""))
                _by = {str(o.get("occ_id")): o for o in _occs}
                _rows: List[dict] = []
                for _bk_key, _is_role in (("person", False), ("role", True)):
                    _bk = (_res_m or {}).get(_bk_key) or {}
                    _llm_k = _bk.get("llm") or {}
                    llm_n += len(_llm_k)
                    hits_n += len(_bk.get("hits") or {})
                    failed += len(_bk.get("failed") or [])
                    _bad = "role" if _is_role else "person"
                    _bk_f[_bad]["llm"] += len(_llm_k)
                    _bk_f[_bad]["failed"] += len(_bk.get("failed") or [])
                    for _hv in (_bk.get("hits") or {}).values():
                        _hs = str(_hv[1] or "") if isinstance(_hv, tuple) else ""
                        if _hs == "zhconv":
                            _bk_f[_bad]["zhconv"] += 1
                        elif _hs == "series":
                            _bk_f[_bad]["role_mem"] += 1
                        elif _hs == "tmdb":
                            _bk_f[_bad]["tmdb"] += 1
                        else:
                            _bk_f[_bad]["pool"] += 1
                    _bk_f[_bad]["llm_zhc"] += len(_bk.get("llm_zhc") or set())
                    _m: Dict[str, str] = {}
                    for _i, _v in (_bk.get("hits") or {}).items():
                        _m[str(_i)] = str(_v[0] if isinstance(_v, tuple) else _v)
                    for _i, _v in _llm_k.items():
                        _m[str(_i)] = str(_v)
                    if (_bk.get("failed") or _bk.get("deferred")) and not _m:
                        _ok_all = False
                    for _i, _z in _m.items():
                        _o = _by.get(str(_i))
                        if not _o:
                            continue
                        _zz = str(_z or "").strip()
                        if _is_role:
                            _zz = self._normalize_role_zh(_o["text"], _zz)
                        if not _zz or _zz == _o["text"]:
                            continue
                        _rows.append({"kind": ("role" if _is_role else "name"),
                                      "original_text": _o["text"], "translation": _zz,
                                      "item_id": _o["item_id"], "server_id": _o.get("server_id") or "",
                                      "season_num": _o.get("season_num"),
                                      "episode_num": _o.get("episode_num"),
                                      "person_index": _o.get("person_index") or 0})
                        _fresh.append({"type": ("role" if _is_role else "person"),
                                       "original": _o["text"], "zh": _zz,
                                       "source": ("llm" if str(_i) in _llm_k else "zhconv")})
                        _bk_f[_bad]["done"] += 1
                        done += 1
                if _rows and db is not None:
                    try:
                        # 强制重翻必须覆盖旧译文 → occurrence 精确 + override
                        db.apply_translations_occurrence(plugin_id=pid, rows=_rows, override=True)
                    except Exception as _e:
                        logger.debug(f"[Translate] 强制重翻写库失败: {_e}")
                # v4.6.74（报告第二十一 / 二十九节）：强制重翻的**角色**新译文刷新「同剧角色记忆」——
                # 否则重翻后记忆仍是旧译文，下一集命中旧值（用户明确要求重翻后更新 Memory）。
                try:
                    if db is not None:
                        _mem_f = []
                        for _r in _rows:
                            if str(_r.get("kind")) != "role" or not _r.get("item_id"):
                                continue
                            _mem_f.append({"server_id": str(_r.get("server_id") or ""),
                                           "series_id": str(_r.get("item_id") or ""),
                                           "series_name": str(_job.get("title") or ""),
                                           "role_original": str(_r.get("original_text") or ""),
                                           "role_translated": str(_r.get("translation") or ""),
                                           "source": "llm"})
                        if _mem_f:
                            db.role_memory_put(plugin_id=pid, rows=_mem_f)
                except Exception as _me:
                    logger.debug(f"[Translate] 强制重翻刷新角色记忆失败（非致命）: {_me}")
                if _fresh:
                    try:
                        dbm.set_map_many(plugin_id=pid, entries=_fresh)
                    except Exception:
                        pass
                if _ok_all:
                    _jobs.pop(_item, None)
                    # 重翻完成 → 登记写回候选（由 Writeback Worker 按门控统一落盘，save 成功才标 done）
                    try:
                        self._wb_register_item(_item, str(_job.get("server_id") or ""), _scope_f)
                    except Exception:
                        pass
                elif _fresh:
                    _jobs.pop(_item, None)   # 有产出但部分失败：本轮已尽力，失败词条留给失败清单重试
            except Exception as _e:
                logger.warning(f"[Translate] 强制重翻任务异常 {_item}: {_e}")
                failed += 1
                _jobs.pop(_item, None)
        if not (done or llm_n or hits_n or failed):
            return None
        return {"done": done, "llm": llm_n, "hits": hits_n, "failed": failed, "current": _cur,
                "by_kind": _bk_f}

    def _tx_llm_chunks(self, occs: list, title: str = "", year: str = "") -> dict:
        """对「需要 LLM 翻译」的 occurrence 做分块调用（v4.6.64 · occurrence 化）。

        **始终结构化输入**：每条 occurrence 携带 occ_id / kind / title / item_id，模型按 id
        一一对应返回，同名原文分属不同作品不会串译（不再以原文字符串为键，报告 P0/P1-AGG-02）。
        返回 {"llm": {occ_id: zh}, "failed": [occ_id], "deferred": [occ_id]}。
        """
        out_llm: Dict[str, str] = {}
        out_llm_zhc: set = set()   # v4.6.70（P0-1）：LLM 返回被 zhconv 纠正为简体的 occ_id
        out_noop: Dict[str, str] = {}   # v4.6.102（P0·缺陷3）：模型如实返回原文 = 无需翻译
        failed: List[str] = []
        deferred: List[str] = []
        _dedup = {"in": 0, "uniq": 0}   # v4.6.75（规范 §四-3/§十-3）：输入条数 → 去重后唯一条数

        def _ret() -> dict:
            """统一收口返回（v4.6.70）—— 附带 llm_zhc（LLM 输出被简体化的 occ_id）。
            v4.6.75：附带 dedup（本批「输入 N 条 → 去重后唯一 M 条」，供日志/通知自证聚合）。"""
            return {"llm": out_llm, "failed": failed, "deferred": deferred,
                    "llm_zhc": sorted(out_llm_zhc), "noop": out_noop,
                    "dedup_in": int(_dedup["in"]), "dedup_uniq": int(_dedup["uniq"])}

        _pending: List[dict] = list(occs or [])
        if not _pending:
            return _ret()
        _txt: Dict[str, str] = {str(o.get("occ_id")): str(o.get("text") or "") for o in _pending}
        # v4.6.70（报告第二十三节）：**批内去重** —— 同一 (kind, 原文) 只发一次 AI，
        # 结果扇出到全部 occurrence。一部剧 12 集里同一角色反复出现时，此前会把
        # 「Dark Knight」重复发送 N 次（AI 请求 / Token / 429 概率被成倍放大）。
        # v4.6.74（P0 · 报告第二 / 六 / 二十四节）：**第二排角色去重必须带作品身份** ——
        # 全局聚合模式下 A 剧 Guard 与 B 剧 Guard 此前共用 (role, 原文) 键被压成一条，
        # 结果互相扇出（不同作品同名角色串译）。现在：
        #   角色 → (role, server_id, 作品身份 series_media_id/item_id, 原文)
        #          A 剧 E01/E02/E03 Guard 仍合并为一条（同作品跨集合并可聚合）；
        #          B 剧 Guard 独立成条（可与 A 剧得到不同译文，互不串译）。
        #   人名 → (person, 原文)（第一排本就是全局人名池设计，跨作品共用同一译名）。
        _alias: Dict[str, List[str]] = {}      # 代表 occ_id -> 同键的其它 occ_id
        _uniq_pending: List[dict] = []
        _seen_key: Dict[tuple, str] = {}
        for _o in _pending:
            _kind = "role" if str(_o.get("kind")) == "role" else "person"
            if _kind == "role":
                _k = (_kind, str(_o.get("server_id") or ""),
                      self._tx_work_id(_o), str(_o.get("text") or ""))
            else:
                _k = (_kind, str(_o.get("text") or ""))
            _rid = _seen_key.get(_k)
            if _rid:
                _alias.setdefault(_rid, []).append(str(_o.get("occ_id")))
                continue
            _seen_key[_k] = str(_o.get("occ_id"))
            _uniq_pending.append(_o)
        # 去重只用于「送 LLM 的批次」：_txt 仍保留全部 occ_id（扇出写回要用）
        _dedup["in"] = len(_txt)
        _dedup["uniq"] = len(_uniq_pending)
        _pending = _uniq_pending
        if not self._ai_enabled():
            deferred.extend(_txt.keys())
            return _ret()
        _llm = self._llm
        if _llm is None:
            try:
                self._init_llm()
            except Exception:
                pass
            _llm = getattr(self, "_llm", None)
        if _llm is None:
            deferred.extend(_txt.keys())
            return _ret()
        _size = min(max(1, int(getattr(self, "_tx_batch", 0) or self.TX_BATCH)), max(1, len(_pending)))
        # v4.6.102（P0·缺陷2）：缩批重试计数改为**每批独立**（在 while 内重置）——
        # 此前定义在此处（while 之外），整个 job 只共享 1 次重试机会：第一批用掉后
        # 其余批次的缺失项全部直接记失败（实测 14936 条的 job 因此大面积假失败、
        # 失败词条又回队首 → 毒丸闭环）。
        _batch_no = 0
        _batch_total = max(1, (len(_pending) + max(1, _size) - 1) // max(1, _size))
        _job_id_txt = str(getattr(self, "_tx_job_id", "") or "")
        while _pending:
            _partial_round = 0   # v4.6.102：每批独立（见上）
            _chunk = _pending[:_size]
            _batch_no += 1
            _ids = [str(o.get("occ_id")) for o in _chunk]
            try:
                _items = [{"id": str(o.get("occ_id")), "text": str(o.get("text") or ""),
                           "kind": ("role" if o.get("kind") == "role" else "person"),
                           "title": str(o.get("title") or title or ""),
                           "year": str(year or ""),
                           "item_id": str(o.get("item_id") or "")} for o in _chunk]
                _raw = _llm.translate_items(_items, stop_check=self._tx_stop_requested,
                                            raise_typed=True, job_id=_job_id_txt,
                                            batch_no=_batch_no, batch_total=_batch_total)
                self._rl_ok()  # 成功一次 → 熔断恢复
                _got: set = set()
                for _id, _zh in (_raw or {}).items():
                    _id = str(_id)
                    _v = str(_zh or "").strip()
                    # v4.6.70（P0-1）：LLM 输出**强制简体化** —— 提示词要求「翻译成简体中文」
                    # 不等于模型一定给简体（实测会返回 台灣/劇場/角色… 等繁体）；
                    # 这里统一 zhconv 纠正后再入库，保证 DB / NFO / 角色记忆一律简体，
                    # 避免繁体结果被后续集继续复用。被纠正的计入 llm_zhc 独立统计。
                    if _v:
                        try:
                            _v2 = self._zhconv_convert(_v)
                        except Exception:
                            _v2 = _v
                        if _v2 and _v2 != _v:
                            _v = _v2
                            out_llm_zhc.add(_id)
                    if _id in _txt and _v:
                        _src_text = str(_txt.get(_id) or "")
                        if _v == _src_text:
                            # v4.6.102（P0·缺陷3）：**模型如实返回原文 = 无需翻译**（"M"、"Blofeld"
                            # 这类单字母名 / 专有名词）。此前被 `_v != _txt[_id]` 判为「未返回」→
                            # 触发缩批重试 → 二次仍缺 → 记失败 → 回队首 → 每轮开局就撞（毒丸）。
                            # 现在计入「已返回」并单独归入 noop 桶：不再缩批、不再记失败，
                            # 同时登记进本会话「无需翻译」集合，后续轮次不再重复送 LLM。
                            out_noop[_id] = _v
                            _got.add(_id)
                            try:
                                self._tx_noop_terms_set().add(_src_text)
                                self._failed_terms.discard(_src_text)
                                self._failed_terms_detail.pop(_src_text, None)
                            except Exception:
                                pass
                            for _al in (_alias.get(_id) or []):
                                if _al in _txt:
                                    out_noop[_al] = _v
                                    _got.add(_al)
                            continue
                        out_llm[_id] = _v
                        _got.add(_id)
                        # v4.6.70：扇出到「同文本的其它 occurrence」（批内去重后的补齐）
                        for _al in (_alias.get(_id) or []):
                            if _al in _txt and _v != _txt.get(_al):
                                out_llm[_al] = _v
                                _got.add(_al)
                                if _id in out_llm_zhc:
                                    out_llm_zhc.add(_al)
                        self._failed_terms.discard(_txt.get(_id))
                        self._failed_terms_detail.pop(str(_txt.get(_id)), None)
                # 批次 / 词条状态留痕（按 occurrence，不再按 original_text 扩散）
                if _job_id_txt:
                    try:
                        self._tx_job_note_batch(_batch_no, _ids, set(_got), _chunk)
                    except Exception:
                        pass
                # v4.6.102（P0·缺陷1）：部分返回**只重试缺失项，绝不改动批大小**。
                # 旧逻辑 `_size = min(_size, len(_missing))` + `self._tx_batch = _size`
                # 会在「29/30 部分返回」时把批大小钉死为 1（min(30,1)=1），且 _tx_batch 是
                # 实例属性、job 之间从不重置 → 直到下次插件重启才恢复。实测 781 次请求里
                # 66% 的批大小是 1（吞吐 0.143 条/秒 vs 30 条的 1.97 条/秒，差 13.8 倍）。
                _rest = _pending[_size:]
                _missing = [_i for _i in _ids if _i not in _got]
                if _missing and _partial_round < 1:
                    _partial_round += 1
                    _miss_occs = [o for o in _chunk if str(o.get("occ_id")) in _missing]
                    logger.warning(f"[LLM] 本批仅返回 {len(_got)}/{len(_chunk)} 条，"
                                   f"缺失 {len(_missing)} 条 → 仅重试缺失项（批大小保持 {_size} 不变）")
                    # 关键修复：缺失项排到队尾（毒丸不再永远堵在队首），_size/self._tx_batch 均不动
                    _pending = _rest + _miss_occs
                    continue
                if _missing:
                    for _i in _missing:
                        failed.append(_i)
                        _t0 = _txt.get(_i) or ""
                        if _t0:
                            self._failed_terms.add(_t0)
                            self._failed_terms_detail[str(_t0)] = "模型返回缺项（缩批重试后仍未返回）"
                    logger.warning(f"[LLM] 本批缺失 {len(_missing)} 条，已记失败待重试（词条仍留在库中）")
                _pending = _rest
                # 批大小恢复：本批「无缺失」即向上爬升（上限 = 设置页「单批最多翻译条数」）。
                # v4.6.102：去掉旧的 `len(_pending) >= _size` 条件 —— 缩批路径下 _pending 已被
                # 改写，该条件在最后一批恒为假，导致批大小永远爬不回去。
                _cap = max(1, int(getattr(self, "_tx_batch_max", 0) or self.TX_BATCH))
                # v4.6.112（GH#3-6）：放大不超过「本会话已验证不超长的上限」，避免
                # 「折半 → 放大 → 又超长」来回抖动（每次抖动白烧一个请求）。
                try:
                    _cap = max(self.TX_BATCH_MIN, min(_cap, int(getattr(self, "_tx_batch_safe", 0) or _cap)))
                except Exception:
                    pass
                if _size < _cap and not _missing:
                    _size = min(_cap, max(_size + 1, _size * 2))
                    self._tx_batch = _size
            except InterruptedError:
                deferred.extend(_ids)
                break
            except ContextLengthExceeded:
                if _size > self.TX_BATCH_MIN:
                    _size = max(self.TX_BATCH_MIN, _size // 2)
                    self._tx_batch = _size
                    # v4.6.112（GH#3-6）：记下本会话「已验证不超长」的上限（取更保守者），
                    # 放大时不越过它 —— 否则会「折半 → 放大 → 又超长」来回抖动白烧请求。
                    try:
                        self._tx_batch_safe = max(
                            self.TX_BATCH_MIN,
                            min(int(getattr(self, "_tx_batch_safe", 0) or _size), _size))
                    except Exception:
                        pass
                    logger.warning(f"[Translate] 上下文超长 → 批次折半为 {_size} 条重试（本会话沿用该批大小）")
                    continue
                _bad = _chunk[0]
                _bid = str(_bad.get("occ_id"))
                _bt = str(_bad.get("text") or "")
                failed.append(_bid)
                if _bt:
                    self._failed_terms.add(_bt)
                    self._failed_terms_detail[_bt] = "上下文超长（单词条仍超限，减小单批条数或换模型）"
                _pending = _pending[1:]
                logger.warning(f"[Translate] 单词条上下文超长，记失败: {_bt[:60]}")
            except RateLimited as _re:
                _w = self._rl_enter(getattr(_re, "retry_after", None))
                logger.warning(f"[Translate] 触发限流 → 熔断 {_w:.0f}s（{len(_pending)} 条词条留在 DB，窗口过后自动续翻）")
                self._push_log("WARNING", f"LLM 限流熔断 {_w:.0f} 秒：词条不丢，窗口过后自动续翻")
                self._tx_job_set("rate_limited",
                                 next_retry_at=datetime.fromtimestamp(time.time() + _w).isoformat(timespec="seconds"),
                                 error_message=f"限流（429 / tpm-rpm），{int(_w)} 秒后自动续跑")
                deferred.extend([str(o.get("occ_id")) for o in _pending])
                break
            except QuotaExceeded as _qe:
                self._tx_hard_until = time.time() + 1800
                self._tx_hard_kind = "quota_exceeded"
                logger.warning(f"[Translate] LLM 余额/配额不足 → 暂停 30 分钟不做无意义重试: {str(_qe)[:120]}")
                self._push_log("WARNING", "LLM 余额/配额不足：已暂停 AI 翻译 30 分钟（词条留在库中，充值后自动续翻）")
                self._tx_job_set("quota_paused",
                                 next_retry_at=datetime.fromtimestamp(time.time() + 1800).isoformat(timespec="seconds"),
                                 error_message=str(_qe)[:200])
                deferred.extend([str(o.get("occ_id")) for o in _pending])
                break
            except AuthenticationError as _ae:
                self._tx_hard_until = time.time() + 1800
                self._tx_hard_kind = "authentication_failed"
                logger.warning(f"[Translate] LLM 认证失败 → 暂停 30 分钟: {str(_ae)[:120]}")
                self._push_log("WARNING", "LLM 认证失败（请检查 API Key）：已暂停 AI 翻译 30 分钟")
                self._tx_job_set("failed", error_message=f"认证失败：{str(_ae)[:160]}")
                deferred.extend([str(o.get("occ_id")) for o in _pending])
                break
            except LLMError as _le:
                logger.warning(f"[Translate] LLM 错误（{getattr(_le, 'kind', 'error')}），本轮放弃该批（词条留 DB）: {str(_le)[:120]}")
                deferred.extend([str(o.get("occ_id")) for o in _pending])
                break
            except Exception as _e:
                logger.warning(f"[Translate] 翻译异常，本轮放弃该批（词条留 DB）: {str(_e)[:120]}")
                deferred.extend([str(o.get("occ_id")) for o in _pending])
                break
        return _ret()

    def _tx_translate_mixed(self, occs: list, pool_lu: dict,
                            title: str = "", year: str = "") -> dict:
        """occurrence 统一批队列（v4.6.64）—— 人名 + 角色合成一次请求，键为 **occ_id**。
        occs: [occurrence dict...]（已按预算裁剪；含 occ_id/kind/text）。
        池命中 / 繁简转换按各自通道先行，剩下的一起送 LLM。
        返回 {"person": {hits,llm,failed,deferred}, "role": {...}}（各字典键 = occ_id）。"""
        def _mk():
            # v4.6.70（P0-1）：llm_zhc = 本桶里「LLM 输出被强制简体化」的 occ_id（独立统计）
            # v4.6.102（P0·缺陷3）：noop = 模型如实返回原文（无需翻译）的 occ_id
            return {"hits": {}, "llm": {}, "llm_zhc": set(), "noop": {}, "failed": [], "deferred": []}
        _out = {"person": _mk(), "role": _mk(), "dedup_in": 0, "dedup_uniq": 0}
        _llm_occs: List[dict] = []
        for o in (occs or []):
            _t = str((o or {}).get("text") or "").strip()
            if not _t:
                continue
            _k = "role" if str(o.get("kind")) == "role" else "person"
            _oid = str(o.get("occ_id") or "")
            _bucket = _out[_k]
            # v4.6.74（P0 · 报告第三 / 二十节）：**第二排角色不得跨作品复用全局记忆** ——
            # 全局池（name_map）是跨作品聚合的，A 剧「Guardian → 守护者」会污染 B 剧
            # （B 应得到「守门人」）。角色只认「同剧角色记忆」（role_memory，已在上一阶段
            # 命中并从 _occs 中移除）；这里不读全局池 → 不同作品同名角色绝不可能串译。
            _hit = None if _k == "role" else (pool_lu or {}).get((_k, _t))
            # v4.6.107（LIB-014）：池命中也要过「有效译文」关 —— 历史脏数据里可能有含假名的
            # name_zh（早期把 TMDB 日文别名当中文名写入），直接当命中会永远清不掉「待翻译」。
            if _hit and self._zhconv_final_ok(_t, _hit[0]):
                _bucket["hits"][_oid] = (str(_hit[0]).strip(), str(_hit[1] or "pool"))
                continue
            try:
                _z = self._zhconv_convert(_t)
            except Exception:
                _z = _t
            # v4.6.107（LIB-014）：繁转简必须产出**有效中文名**才算命中，否则放行给 LLM。
            # 「雛坂ひかる」这类汉字 + 假名的名字，zhconv 只把汉字换掉（→「雏坂ひかる」），
            # 假名还在 → 池/库的「有效译文」判定（db._SQL_ZH_VALID，排除含假名）不认，
            # 行永远停在「待翻译」→ 每轮重复繁转简、永远收敛不了（用户实测 9 条池待翻
            # 卡在「繁转简 2 条 / 剩余 4 条」死循环，且这些词条**从未被送去 LLM**）。
            if self._zhconv_final_ok(_t, _z):
                _bucket["hits"][_oid] = (_z, "zhconv")
                continue
            _llm_occs.append(o)
        # 统一一次 LLM 调用（含分块/缩批/熔断/类型化异常）
        _r = self._tx_llm_chunks(_llm_occs, title, year)
        # v4.6.75（规范 §四-3/§十-3）：把「送 LLM 的输入条数 → 去重后唯一条数」带上，
        # 供轮次日志 / Job 结束日志自证「几条词条 = 几次请求」。
        _out["dedup_in"] = int(_r.get("dedup_in") or 0)
        _out["dedup_uniq"] = int(_r.get("dedup_uniq") or 0)
        _by = {str(o.get("occ_id")): o for o in _llm_occs}

        def _bk(_i):
            _o = _by.get(str(_i))
            return _out["role" if (_o and str(_o.get("kind")) == "role") else "person"] if _o else None

        for _i, _z in (_r.get("llm") or {}).items():
            _b = _bk(_i)
            if _b is not None:
                _b["llm"][str(_i)] = _z
        # v4.6.102（P0·缺陷3）：模型如实返回原文（无需翻译）→ 归入所属桶的 noop
        for _i, _z in (_r.get("noop") or {}).items():
            _b = _bk(_i)
            if _b is not None:
                _b["noop"][str(_i)] = _z
        # v4.6.70（P0-1）：LLM 输出被简体化的 occ_id 记进所属桶（独立统计，不影响 llm 计数）
        for _i in (_r.get("llm_zhc") or []):
            _b = _bk(_i)
            if _b is not None:
                _b["llm_zhc"].add(str(_i))
        for _i in (_r.get("failed") or []):
            _b = _bk(_i)
            if _b is not None:
                _b["failed"].append(str(_i))
        for _i in (_r.get("deferred") or []):
            _b = _bk(_i)
            if _b is not None:
                _b["deferred"].append(str(_i))
        return _out

    def _tx_scope(self) -> str:
        """本次翻译/写回目标范围 —— person / role / both。

        临时任务字段（self._tx_target_scope），默认 both；「批量翻译」可临时覆盖，
        不改动全局配置（§三十）。

        v4.6.113（P1-04）：**任务运行期间优先读任务快照的 scope** —— 任务一旦启动，
        其范围即冻结；运行中新的自动触发 / 并发请求不得改变当前任务的范围
        （`self._tx_target_scope` 仅在无快照时才作为实时值使用）。
        """
        _snap = getattr(self, "_tx_cfg_snapshot", None)
        if isinstance(_snap, dict):
            _ss = str(_snap.get("scope") or "").strip().lower()
            if _ss in ("person", "role", "both"):
                return _ss
        _s = str(getattr(self, "_tx_target_scope", "both") or "both").strip().lower()
        return _s if _s in ("person", "role", "both") else "both"

    def _tx_batching_mode(self) -> str:
        """分批模式（per_title / global）—— 任务运行期间取 Job Snapshot（v4.6.113 · P1-04）：
        运行中改「分批方式」不影响当前任务（新设置从下一个任务生效）。"""
        _snap = getattr(self, "_tx_cfg_snapshot", None)
        if isinstance(_snap, dict) and _snap.get("batching"):
            _b = str(_snap.get("batching")).strip().lower()
            if _b:
                return _b
        return str(getattr(self, "_translate_batching", "per_title") or "per_title").strip().lower()

    def _tx_scope_allows(self, kind: str, scope: str = "") -> bool:
        """当前目标范围是否包含某排 —— person=第一排人名 / role=第二排角色。
        可显式传入任务范围（写回就绪判定按候选记录里的范围判，不依赖瞬时状态）。"""
        _s = str(scope or "").strip().lower()
        if _s not in ("person", "role", "both"):
            _s = self._tx_scope()
        if kind == "person":
            return _s in ("person", "both")
        if kind == "role":
            return _s in ("role", "both")
        return True

    def _tx_source_allows(self, kind: str) -> bool:
        """本次作业来源是否包含某来源 —— library（库内词条）/ pool（人名池）。
        空串（未声明来源，兜底）/ both → 都允许。"""
        _s = str(getattr(self, "_tx_source", "") or "").strip().lower()
        if _s in ("", "both"):
            return True
        return _s == str(kind or "").strip().lower()

    def _tx_job_db(self):
        """翻译任务持久化库（惰性单例，v4.6.61 · P1-6）。"""
        _d = getattr(self, "_tx_job_db_obj", None)
        if _d is None:
            _d = TranslateJobDb()
            self._tx_job_db_obj = _d
        return _d

    def _tx_register_job_terms(self, rows: list) -> int:
        """把本 Job 的待翻词条写入 translate_job_terms（幂等；无 job 时静默）。"""
        _jid = str(getattr(self, "_tx_job_id", "") or "")
        if not _jid or not rows:
            return 0
        try:
            return int(self._tx_job_db().save_terms(plugin_id=self.__class__.__name__,
                                                    job_id=_jid, rows=rows) or 0)
        except Exception:
            return 0

    @staticmethod
    def _tx_occ_id(o: dict) -> str:
        """occurrence 稳定键（v4.6.64）—— 同名原文分属不同作品/季/集/序号不串：
        "server|item|season|episode|index|kind|text"。人名池（无 item）退化为 "pool|kind|text"。"""
        _i = str(o.get("item_id") or "").strip()
        _snn = "" if o.get("season_num") is None else str(o.get("season_num"))
        _enn = "" if o.get("episode_num") is None else str(o.get("episode_num"))
        _idx = str(int(o.get("person_index") or 0))
        _kind = str(o.get("kind") or "")
        _txt = str(o.get("text") or "")
        if not _i:
            return f"pool|{_kind}|{_txt}"
        return "|".join([str(o.get("server_id") or ""), _i, _snn, _enn, _idx, _kind, _txt])

    @staticmethod
    def _tx_work_id(o: dict) -> str:
        """occurrence 的「作品身份」（v4.6.74）—— 第二排角色翻译的隔离作用域。

        series_media_id（批次3 稳定媒体身份）优先，退化为 item_id（集记录本就复用剧 id，
        两者是同一个剧级身份）；人名池无条目上下文时为空串（池内为全局人名）。
        """
        return str((o or {}).get("series_media_id") or (o or {}).get("item_id") or "")

    def _tx_noop_terms_set(self) -> set:
        """本会话「确认无需翻译」的词条集合（v4.6.102·P0 缺陷3）——
        模型如实返回原文（"M"、"Blofeld" 这类单字母名 / 专有名词）者在此登记，
        后续轮次不再重复送 LLM。生命周期与「失败跳过」一致：终止任务/改设置时清空。"""
        _s = getattr(self, "_tx_noop_terms", None)
        if _s is None:
            _s = set()
            self._tx_noop_terms = _s
        return _s

    @staticmethod
    def _tx_untranslatable(text: str) -> bool:
        """是否「无任何可译内容」（单字符 / 纯数字符号，如 "M"）——
        送 LLM 必然原样返回（实测毒丸之一），直接登记为无需翻译：
        省掉一次 AI 请求 + 一次缩批重试，也不占单批名额。"""
        _t = str(text or "").strip()
        if len(_t) <= 1:
            return True
        return not any(_ch.isalpha() for _ch in _t)

    @staticmethod
    def _tx_pick_batch(occs: list, n: int) -> list:
        """从 occurrence 列表里按「人名/角色轮流取」裁剪出不超过 n 条的一批
        （v4.6.64）—— 保证第一排 + 第二排能同批聚合（3+3 → 一次请求），而非各发一次。"""
        _p = [o for o in (occs or []) if str(o.get("kind")) != "role"]
        _r = [o for o in (occs or []) if str(o.get("kind")) == "role"]
        out: list = []
        _i = _j = 0
        _n = max(1, int(n or 1))
        while len(out) < _n and (_i < len(_p) or _j < len(_r)):
            if _i < len(_p):
                out.append(_p[_i]); _i += 1
            if len(out) < _n and _j < len(_r):
                out.append(_r[_j]); _j += 1
        return out

    def _tx_occurrences(self, pid: str, item_id: str = "", server_id: str = "",
                        force: bool = False, disabled: Optional[list] = None) -> List[dict]:
        """本轮流内待翻（或强制重翻）的 occurrence 明细 —— **唯一来源，不按原文字符串去重**
        （v4.6.64 · occurrence 化）。每项：occ_id/kind/text/item_id/server_id/season_num/
        episode_num/person_index/person_type/title。
        """
        _out: List[dict] = []
        # v4.6.113（P2）：数据库读取错误标记 —— 供候选队列 / 翻译轮次区分
        # 「查询失败」与「确实没有待翻」，绝不把前者伪装成「本轮没有工作」。
        self._tx_occ_err = ""
        try:
            _db = getattr(self, "_people_db", None)
            if _db is None:
                return _out
            _lim = self._tx_limits_by_level()
            # v4.6.68：翻译词条唯一来源统一带「处理单集」门禁 —— 关时 Episode 行不产出 occurrence
            _ex_ep = self._tx_exclude_episodes()
            if str(item_id or "").strip():
                _raw = _db.force_item_occurrences(
                    plugin_id=pid, item_id=item_id, server_id=server_id, limits=_lim,
                    disabled_types=disabled, only_pending=not force,
                    exclude_episodes=_ex_ep) or {}
            else:
                _raw = _db.pending_terms_full(plugin_id=pid, limits=_lim,
                                              disabled_types=disabled, only_pending=True,
                                              exclude_episodes=_ex_ep) or {}
            if isinstance(_raw, dict) and _raw.get("error"):
                self._tx_occ_err = str(_raw.get("error"))
                logger.warning(f"[Translate] 待翻词条读取失败（数据库错误，非「无可翻条目」）: {self._tx_occ_err}")
                return _out
            for _kind, _key in (("person", "names"), ("role", "roles")):
                for r in (_raw.get(_key) or []):
                    _t = str((r or {}).get("term") or "").strip()
                    if not _t:
                        continue
                    _o = {"kind": _kind, "text": _t,
                          "item_id": str(r.get("item_id") or ""),
                          "server_id": str(r.get("server_id") or ""),
                          "season_num": r.get("season_num"),
                          "episode_num": r.get("episode_num"),
                          "person_index": int(r.get("person_index") or 0),
                          "person_type": str(r.get("type") or "Actor"),
                          "title": str(r.get("title") or "")}
                    _o["occ_id"] = self._tx_occ_id(_o)
                    _out.append(_o)
        except Exception as _e:
            # v4.6.113（P2）：异常同样登记为错误标记（≠ 空的「无可翻条目」）
            self._tx_occ_err = str(_e)
            logger.warning(f"[Translate] 取 occurrence 失败（数据库/查询错误，非「无可翻条目」）: {_e}")
        return _out

    def _tx_occ_queue(self, pid: str, force: bool = False) -> dict:
        """本 Job 的待翻候选队列（v4.6.112 · GH#3-7）—— 缓存全表 SQL 结果 + 游标。

        GH#3-7：此前 `_translate_pending_round` **每一轮**都调 `_tx_occurrences()` ——
        对整张 person 表跑两次（name / role 各一次）窗口聚合，再在 Python 里把上万条
        逐条过滤，最后只挑「单批最多翻译条数」（默认 30）条。1.4 万待翻时等于
        「每翻 30 条就全表扫两遍」，报告者实测两次请求之间要等 10~55 秒，主要就是这个。

        现在：全表 SQL 每 Job 只跑一次（TTL 到期 / 队列走完时再刷新），轮次只在一个
        游标上向前推进 —— 每轮真正过滤的条目数从 O(全部待翻) 降到 O(本轮要的条数)。

        缓存失效条件：Job 变化、pid 变化、TTL(30s) 到期、游标走完（force 重建）。
        刷新是安全的：已翻的词条 SQL 不会再返回；失败待重试的会再次出现（正好重试）。
        """
        _now = time.time()
        _c = getattr(self, "_tx_occ_cache", None)
        _jid = str(getattr(self, "_tx_job_id", "") or "")
        _ok = (isinstance(_c, dict)
               and str(_c.get("pid") or "") == str(pid)
               and str(_c.get("jid") or "") == _jid
               and (_now - float(_c.get("ts") or 0.0)) < float(self.TX_OCC_CACHE_TTL))
        if force or not _ok:
            # v4.6.113（P2）：一并带上数据库读取错误标记（供轮次区分「查询失败」与「确无待翻」）
            _occs = self._tx_occurrences(pid)
            _c = {"pid": str(pid), "jid": _jid, "ts": _now,
                  "occs": _occs, "i": 0,
                  "error": str(getattr(self, "_tx_occ_err", "") or "")}
            self._tx_occ_cache = _c
            if force:
                logger.debug(f"[Translate] 待翻候选队列重建：{len(_c.get('occs') or [])} 条")
                if _c.get("error"):
                    logger.warning(f"[Translate] 候选队列重建时数据库读取失败（非「无待翻」）：{_c['error']}")
        return _c

    def _tx_job_flush_attempts(self) -> int:
        """把 LLM 层的每次 HTTP attempt 落进 translate_job_batches（v4.6.64 · P1-5/P1-6）——
        429/5xx/401 与失败重试都留痕，Job 批次历史才能完整回答「发了几次、哪次 429」。"""
        _jid = str(getattr(self, "_tx_job_id", "") or "")
        _llm = getattr(self, "_llm", None)
        if not _jid or _llm is None or not hasattr(_llm, "drain_attempts"):
            return 0
        try:
            _atts = _llm.drain_attempts() or []
        except Exception:
            return 0
        _n = 0
        try:
            _jdb = self._tx_job_db()
            _pid = self.__class__.__name__
            for _a in _atts:
                _n += int(_jdb.add_batch(
                    plugin_id=_pid, job_id=_jid, batch_id=int(_a.get("batch_no") or 0),
                    status=("ok" if _a.get("ok") else "failed"),
                    request_no=int(_a.get("request_no") or 0),
                    term_count=int(_a.get("term_count") or 0), returned_count=0,
                    attempt_count=int(_a.get("attempt") or 0),
                    http_status=int(_a.get("http_status") or 0),
                    error_kind=str(_a.get("error_kind") or ""),
                    started_at=str(_a.get("started_at") or ""),
                    finished_at=str(_a.get("finished_at") or "")) or 0)
        except Exception:
            pass
        return _n

    def _tx_job_note_batch(self, batch_no: int, ids: list, got: set,
                           occs: Optional[list] = None) -> None:
        """批次留痕 + 词条状态回写（v4.6.64 · 按 occurrence_id，不按 original_text 扩散）。
        ids 为本批 occurrence id；got 为真正拿到译文的 id 集合；未拿到的记 failed（等待重试）。"""
        _jid = str(getattr(self, "_tx_job_id", "") or "")
        if not _jid:
            return
        _ids = [str(x) for x in (ids or []) if str(x or "").strip()]
        try:
            _jdb = self._tx_job_db()
            _pid = self.__class__.__name__
            _llm = getattr(self, "_llm", None)
            _jdb.add_batch(plugin_id=_pid, job_id=_jid,
                           batch_id=int(batch_no or 0),
                           status=("ok" if len(got) >= len(_ids) else ("partial" if got else "failed")),
                           request_no=int(getattr(_llm, "stat_requests", 0) or 0),
                           term_count=len(_ids), returned_count=len(got),
                           input_tokens=int(getattr(_llm, "stat_tokens_in", 0) or 0),
                           output_tokens=int(getattr(_llm, "stat_tokens_out", 0) or 0),
                           finished_at=datetime.now().isoformat(timespec="seconds"))
            # v4.6.64：按 occurrence_id 精确置状态（term_id 即 occ_id），不再用 original_text 反查扩散
            _ok_ids = [str(_i) for _i in _ids if str(_i) in set(got)]
            _bad_ids = [str(_i) for _i in _ids if str(_i) not in set(got)]
            if _ok_ids:
                _jdb.set_terms_status(plugin_id=_pid, job_id=_jid, term_ids=_ok_ids, status="translated")
            if _bad_ids:
                _jdb.set_terms_status(plugin_id=_pid, job_id=_jid, term_ids=_bad_ids,
                                      status="failed", error="本批未返回，等待重试", bump_retry=True)
            # v4.6.64：把本次 HTTP attempt（含 429/5xx/401）落进批次历史
            self._tx_job_flush_attempts()
        except Exception:
            pass

    def _tx_job_reset_stats(self) -> None:
        """重置本轮 Job 统计（v4.6.70：含拆分项）—— 周期开始 / 终止 / 收尾 / 全量复位统一调用。

        _tx_job_by_kind 结构：{"person": {done,llm,pool,zhconv,llm_zhc,failed},
                              "role":   {同}}。
        """
        self._tx_job_total = 0
        self._tx_job_done = 0
        self._tx_job_applied = 0
        self._tx_job_failed = 0
        self._tx_job_llm = 0
        self._tx_job_hits = 0
        self._tx_job_pool = 0
        self._tx_job_zhconv = 0
        self._tx_job_llm_zhc = 0
        self._tx_job_dedup_in = 0
        self._tx_job_dedup_uniq = 0
        self._tx_job_by_kind = None
        # v4.6.112（GH#3-5）：每个 Job 开始消费时把批大小复位到配置上限 ——
        # 否则上一个任务因上下文超长折半后的批大小会被新任务继承
        # （报告者实测：「重载插件或重新保存设置后短暂回到 30，很快又掉回去」）。
        try:
            _m = max(1, int(getattr(self, "_tx_batch_max", 0) or self.TX_BATCH))
            self._tx_batch = _m
            self._tx_batch_safe = _m
        except Exception:
            pass

    def _tx_job_set(self, status: str, **fields) -> None:
        """更新当前 Job 状态（内存 + SQLite 双写，v4.6.61）—— 无 job / 异常时静默。"""
        if not str(getattr(self, "_tx_job_id", "") or ""):
            return
        try:
            self._tx_job_status = str(status or "")
            _f = dict(fields or {})
            if str(status or "") and "status" not in _f:
                _f["status"] = str(status)
            self._tx_job_db().update(plugin_id=self.__class__.__name__,
                                     job_id=str(self._tx_job_id), **_f)
        except Exception:
            pass

    def _tx_recover_pump(self) -> None:
        """重启恢复队列泵（v4.6.113 · P2）—— **一次只恢复一个**未完成强制重翻任务：
        仅当当前没有正在运行的任务时才启动下一个，保证每个任务保留**自己的**
        job_id / 目标范围 / 条目 / 配置快照（不再把多个旧任务汇总并归到第一个任务）。"""
        try:
            _q = getattr(self, "_tx_recover_queue", None) or []
            if not _q:
                return
            if bool(getattr(self, "_tx_requested", False)):
                return   # 当前任务仍在跑 → 等它结束后由 worker 再泵
            _it = _q.pop(0)
            self._tx_recover_queue = _q
            _snap = _it.get("snapshot")
            if isinstance(_snap, dict) and _snap:
                self._tx_cfg_snapshot = _snap
            self._tx_request_consume(source="library", items=list(_it.get("items") or []),
                                     scope=str(_it.get("scope") or "both"),
                                     resume_job_id=str(_it.get("job_id") or ""))
            logger.info(f"[TranslateJob] 重启恢复：重新入队 job={_it.get('job_id')} "
                        f"scope={_it.get('scope')} items={len(_it.get('items') or [])}"
                        f"（剩余待恢复 {len(_q)} 个）")
        except Exception as _e:
            logger.debug(f"[TranslateJob] 重启恢复泵失败（非致命）: {_e}")

    def _tx_job_recover(self) -> None:
        """进程重启恢复（v4.6.61 · P1-6）—— 未完成的 Job 标记 interrupted；
        「重新翻译」（force）的 payload 重新入队并唤醒 worker（不再静默丢任务）。

        v4.6.113（P2 · P1-04）：**逐个恢复**多个未完成的强制重翻任务 ——
        每个任务保留自己的 job_id / 范围 / 条目 / 配置快照，放入恢复队列，由
        `_tx_recover_pump()` 一次启动一个（不再把多个任务汇总成第一个的任务）。
        """
        try:
            _pid = self.__class__.__name__
            _stale = self._tx_job_db().mark_stale(plugin_id=_pid) or []
            if not _stale:
                return
            _jobs = getattr(self, "_tx_force_jobs", None)
            if _jobs is None:
                _jobs = {}
                self._tx_force_jobs = _jobs
            _queue = list(getattr(self, "_tx_recover_queue", None) or [])
            _n_force = 0
            for _row in _stale:
                if str(_row.get("job_type") or "") != "force":
                    continue
                try:
                    _payload = json.loads(str(_row.get("payload") or "{}") or "{}")
                except Exception:
                    _payload = {}
                if not isinstance(_payload, dict) or not _payload:
                    continue
                _items: List[str] = []
                for _iid, _job in _payload.items():
                    _iid = str(_iid or "").strip()
                    if _iid and isinstance(_job, dict):
                        _jobs.setdefault(_iid, _job)
                        _items.append(_iid)
                if not _items:
                    continue
                try:
                    _snap = json.loads(str(_row.get("cfg_snapshot") or "") or "{}")
                except Exception:
                    _snap = {}
                _queue.append({"job_id": str(_row.get("id") or ""),
                               "scope": str(_row.get("scope") or "both"),
                               "items": _items,
                               "snapshot": (_snap if isinstance(_snap, dict) else {})})
                _n_force += 1
            self._tx_recover_queue = _queue
            logger.info(f"[TranslateJob] 重启恢复：{len(_stale)} 个未完成任务已标记 interrupted"
                        + (f"，其中 {_n_force} 个强制重翻任务已分别入队待恢复"
                           if _n_force else "（常规任务：待翻词条仍在库中，下一次许可自动续翻）"))
            self._push_log("INFO", f"翻译任务重启恢复：{len(_stale)} 个中断任务已登记"
                                   + (f"，{_n_force} 个重新翻译任务已分别恢复入队" if _n_force else ""))
            self._tx_recover_pump()
        except Exception as _e:
            logger.debug(f"[TranslateJob] 重启恢复失败（非致命）: {_e}")

    def _tx_request_consume(self, *, source: str = "both", scope: str = "",
                            items: Optional[list] = None, terms: Optional[list] = None,
                            payload: str = "", resume_job_id: str = "") -> None:
        """授予翻译消费许可 —— 显式声明本次作业来源与目标范围（任务字段）。

        source: library=库内词条；pool=人名池；both=都消费。
        scope:  person/role/both；空 = 不改当前范围（沿用现有/配置默认）。
        items:  条目级限定（如「重新翻译」某条）—— 非空时翻译 worker 只重翻这些条目，
                不再扫全库（避免「点单条重翻 → 整库重翻」）。
        terms:  词条级限定（如「重试失败」）—— 非空时只翻这些词条。
        并发合并：已有不同来源的作业在跑 → 并入为 both（互不覆盖、不串任务）；许可归还时由 worker 复位。
        """
        _src = str(source or "both").strip().lower()
        if _src not in ("pool", "library", "both"):
            _src = "both"
        _cur = str(getattr(self, "_tx_source", "") or "").strip().lower()
        self._tx_source = _src if (not _cur or _cur == _src) else "both"
        if scope in ("person", "role", "both"):
            self._tx_target_scope = scope
        if items is not None:
            _new_i = {str(x).strip() for x in items if str(x or "").strip()}
            _cur_i = set(getattr(self, "_tx_scope_items", None) or ())
            self._tx_scope_items = (_cur_i | _new_i) if _cur_i else _new_i
        if terms is not None:
            _new_t = {str(x).strip() for x in terms if str(x or "").strip()}
            _cur_t = set(getattr(self, "_tx_only_terms", None) or ())
            self._tx_only_terms = (_cur_t | _new_t) if _cur_t else _new_t
        # v4.6.113（P1-04）：判定「已有正在运行 / 已冻结快照的任务」—— 此时本次（并发 /
        # 自动触发）请求**不得覆盖**当前任务的配置快照（范围 / 人数上限 / 写回策略 / 分批模式
        # 一律保持创建时冻结）；恢复既有 Job（resume_job_id 非空）时沿用调用方已设置的快照。
        _running_snap = (isinstance(getattr(self, "_tx_cfg_snapshot", None), dict)
                         and (bool(getattr(self, "_tx_requested", False))
                              or bool(str(resume_job_id or "").strip())))
        self._tx_requested = True
        self._tx_stop = False
        # v4.6.76（规范 §十三 · Job Snapshot）：任务创建时**冻结**翻译相关配置 ——
        # 运行中用户改设置（第一排/第二排开关、类型开关、处理单集、TMDB 补译…）
        # 不得影响正在跑的任务；新设置从下一个任务生效。
        if _running_snap:
            logger.debug("[Translate] 并发/恢复请求：沿用当前任务配置快照"
                         "（不覆盖运行中任务的冻结配置，新设置下一个任务生效）")
        else:
            try:
                # v4.6.99（报告 P1-03 A）：快照覆盖本任务**真正依赖**的设置，而不只是类型开关；
                # 并带上 version，供旧任务恢复时按明确规则迁移（缺字段不静默套用新配置）。
                # 注意：这里**直接读实时配置**（不经 _tx_limits_by_level / _tx_exclude_episodes），
                # 避免赋值前拿到「上一个任务的旧快照」造成跨任务串味。
                _ctt = self._collect_trans_types() or {}
                _tt = dict(_ctt.get("translate", {}) or {})
                _one = dict(_ctt.get("limits", {}) or {})
                self._tx_cfg_snapshot = {
                    "version": int(getattr(self, "TX_SNAPSHOT_VERSION", 2) or 2),
                    "person": bool(_tt.get("person", True)),
                    "role": bool(_tt.get("role", True)),
                    "types": _tt,
                    "exclude_episodes": (not bool(getattr(self, "_nfo_include_episodes", False))),
                    "scope": str(getattr(self, "_tx_target_scope", "both") or "both"),
                    # 人数上限（每文件每类型前 N）—— 运行中改设置不得影响本任务
                    "limits": {"movie": dict(_one), "tvshow": dict(_one), "episode": dict(_one)},
                    "tmdb_credits": bool(getattr(self, "_pool_tmdb_credits", False)),
                    "tmdb_fill": bool(getattr(self, "_pool_tmdb_fill", True)),
                    "auto_writeback": bool(getattr(self, "_auto_writeback", True)),
                    "nfo_preview": bool(getattr(self, "_nfo_preview", False)),
                    "batching": str(getattr(self, "_translate_batching", "per_title") or "per_title"),
                    "batch_size": int(getattr(self, "_tx_batch", 0) or 0),
                    "libraries": [str(x) for x in (getattr(self, "_libraries", None) or [])],
                    "servers": sorted(self._configured_server_keys()),
                    "llm_model": str(getattr(self, "_llm_model", "") or ""),
                }
            except Exception:
                self._tx_cfg_snapshot = None
        # v4.6.61（P0-4 → P1-6 · Job 持久化）：每轮任务一个 job_id；
        # 常规许可 = auto、带 items/terms = force（重新翻译）—— 均落 SQLite（translate_jobs），
        # force 的 payload 供重启恢复；resume_job_id 非空 = 恢复既有 Job（不新建行）。
        # v4.6.62：恢复分支不再要求「当前无 job」—— 取消后 _tx_job_id 可能仍在，
        # 只要当前任务未在跑（或就是它自己），即复用并回 queued（否则 resume 永远停在 cancelled）。
        _resume = str(resume_job_id or "").strip()
        _cur_job = str(getattr(self, "_tx_job_id", "") or "")
        if _resume and (_resume == _cur_job or not _cur_job
                        or not bool(getattr(self, "_tx_requested", False))):
            self._tx_job_id = _resume
            self._tx_job_set("queued", started_at="", finished_at="", error_message="")
        elif not _cur_job:
            try:
                _ms = int((time.time() % 1) * 1000)
                self._tx_job_id = time.strftime("%Y%m%d%H%M%S") + f"-{_ms:03d}"
            except Exception:
                self._tx_job_id = str(int(time.time() * 1000))
            _jt = "force" if (items is not None or terms is not None) else "auto"
            try:
                self._tx_job_db().create(
                    plugin_id=self.__class__.__name__, job_id=self._tx_job_id,
                    job_type=_jt, source=self._tx_source or "both", scope=self._tx_scope(),
                    batch_mode=str(getattr(self, "_translate_batching", "") or ""),
                    batch_size=int(getattr(self, "_tx_batch", 0) or 0),
                    item_count=len(set(self._tx_scope_items or ())),
                    term_count=len(set(self._tx_only_terms or ())),
                    payload=str(payload or ""),
                    # v4.6.113（P1-04）：把创建时的完整配置快照持久化进任务库 ——
                    # 重启恢复时据此沿用原任务的翻译范围 / 人数上限 / 写回策略。
                    cfg_snapshot=(json.dumps(self._tx_cfg_snapshot, ensure_ascii=False)
                                  if isinstance(getattr(self, "_tx_cfg_snapshot", None), dict) else ""))
            except Exception:
                pass
        self._tx_wake()

    def _tx_scope_label(self) -> str:
        """目标范围的可读标签 —— 用于日志 / 运行状态展示。
        人名池作业单独标注来源（池只含第一排人名）。"""
        if str(getattr(self, "_tx_source", "") or "").strip().lower() == "pool":
            return "人名池 · 第一排人名"
        return {"person": "仅第一排人名", "role": "仅第二排角色",
                "both": "第一排人名 + 第二排角色"}.get(self._tx_scope(), "第一排人名 + 第二排角色")

    def _tx_pending_snapshot(self, scope: str = "", item_id: str = "",
                             server_id: str = "", with_detail: bool = False,
                             pool_gate: bool = False, source_gate: bool = False) -> dict:
        """唯一「待翻」快照（v4.6.61 · P1-2 统一口径）—— 徽章 / 明细 / 预估 /
        worker 日志 / 完成通知全部只读这一份，杜绝「日志剩 0 / 库页还有 3」的分裂。

        口径 = 「当前翻译范围 + 类型开关 + 人数上限 + 已是中文跳过 + 未翻译判定」，
        与翻译 worker 收词条完全同一套 SQL（db.pending_terms_full，词条 × 条目明细），
        条目数由明细对的 item 去重得出 —— 不再另维护第二套 SQL 统计。

        :param scope: person/role/both；空 = 当前任务范围（_tx_scope）
        :param item_id/server_id: 非空 = 单条目口径（「重新翻译」预估）
        :param with_detail: 附带 items_list（按条目分组的待翻明细）
        :param pool_gate: True = 按本次作业来源门控池统计（worker 开始/结束用）；
                          False = 池始终计数（徽章/明细/预估用，与作业无关）
        :param source_gate: True = 同样按本次作业来源门控**库内**统计（worker 开始/结束用）。
                          v4.6.106（LIB-013）：此前只门控了池，库内 person/role 一律计入 →
                          「人名池 · 批量翻译」（source=pool）的进度分母把库内 59 人名 + 1812 角色
                          也算进去（用户实测「AI 翻译 4 / 1883，可池里明明只剩 12 个」），
                          且作业永远无法翻完 → 收尾永远是 PARTIAL、数字对不上。
                          徽章 / 明细 / 预估不传此参数（保持「无论什么作业、库页照常显示全部待翻」）。
        :return {"person","role","pool","items","total","person_scope","role_scope",
                 "items_scope","terms_scope","person_on","role_on","disabled",[items_list]}
        """
        _pid = self.__class__.__name__
        _sc = str(scope or "").strip().lower()
        if _sc not in ("person", "role", "both"):
            _sc = self._tx_scope()
        # v4.6.106（LIB-013）：按本次作业来源门控库内统计（与 worker 收词口径一致）
        _src_lib = (not source_gate) or self._tx_source_allows("library")
        _with_person = _sc in ("person", "both") and _src_lib
        _with_role = _sc in ("role", "both") and _src_lib
        _out = {"person": 0, "role": 0, "pool": 0, "items": 0, "total": 0,
                "person_scope": 0, "role_scope": 0, "items_scope": 0, "terms_scope": 0,
                "person_on": True, "role_on": True, "disabled": []}
        if with_detail:
            _out["items_list"] = []
        _tr: dict = {}
        _disabled: list = []
        try:
            _tr = self._collect_trans_types().get("translate", {})
            _out["person_on"] = bool(_tr.get("person", True))
            _out["role_on"] = bool(_tr.get("role", True))
            _disabled = [str(_t) for _t, _k in self.TX_TYPE_SWITCH.items()
                         if _k and not bool(_tr.get(_k, False))]
            _out["disabled"] = _disabled
            _pdb = getattr(self, "_people_db", None)
            if _pdb is not None:
                _limits = self._tx_limits_by_level()
                _iid = str(item_id or "").strip()
                _sid = str(server_id or "").strip()

                def _norm(_raw):
                    """统一成 dict 行：pending_terms_full 已是 dict；force_item_terms 是 (term,type) 元组。"""
                    _o = {"names": [], "roles": []}
                    for _k in ("names", "roles"):
                        for _it in ((_raw or {}).get(_k) or []):
                            if isinstance(_it, dict):
                                _o[_k].append(_it)
                            else:
                                _o[_k].append({"term": str(_it[0] if len(_it) > 0 else ""),
                                               "type": str(_it[1] if len(_it) > 1 else ""),
                                               "item_id": _iid, "server_id": _sid, "title": ""})
                    return _o

                _ex_ep = self._tx_exclude_episodes()
                if _iid:
                    # 单条目口径（「重新翻译」弹窗预估）—— 与全库同规则（人数上限 / 类型 / 中文跳过）
                    _np = _norm(_pdb.force_item_terms(plugin_id=_pid, item_id=_iid, server_id=_sid,
                                                      limits=_limits, only_pending=True,
                                                      exclude_episodes=_ex_ep))
                    _ap = _norm(_pdb.force_item_terms(plugin_id=_pid, item_id=_iid, server_id=_sid,
                                                      limits=_limits, only_pending=False,
                                                      exclude_episodes=_ex_ep))
                else:
                    _np = _pdb.pending_terms_full(plugin_id=_pid, limits=_limits,
                                                  disabled_types=_disabled, only_pending=True,
                                                  exclude_episodes=_ex_ep) or {}
                    _ap = _pdb.pending_terms_full(plugin_id=_pid, limits=_limits,
                                                  disabled_types=_disabled, only_pending=False,
                                                  exclude_episodes=_ex_ep) or {}
                # v4.6.113（P2）：数据库读取失败 ≠ 「无待翻」—— 上报错误供 UI/日志显示，
                # 绝不静默把「查询失败」当成「剩余 0 / 本轮没有工作」。
                _db_err = ""
                for _rr in (_np, _ap):
                    if isinstance(_rr, dict) and _rr.get("error"):
                        _db_err = str(_rr.get("error"))
                        break
                if _db_err:
                    _out["error"] = _db_err
                    logger.warning(f"[Translate] 待翻快照读取失败（数据库错误，非「无待翻」）: {_db_err}")

                def _collect(_pairs, _is_role: bool, _skip_zh: bool, _use_scope: bool):
                    """扫一遍「词条 × 条目」对 → (词条集合, 条目集合, {条目键: 明细})"""
                    _terms, _items, _detail = set(), set(), {}
                    for _row in (_pairs or []):
                        _t = str(_row.get("term") or "").strip()
                        if not _t:
                            continue
                        _pt = str(_row.get("type") or "")
                        if _use_scope:
                            if _is_role:
                                if not _with_role or not self._tx_role_type_enabled(_pt, "both"):
                                    continue
                            else:
                                if not _with_person or not self._tx_type_enabled(_pt, "both"):
                                    continue
                        else:
                            # 「范围内」只看类型开关（与旧口径一致）
                            _sw = self.TX_TYPE_SWITCH.get(_pt.strip(), "")
                            if _sw and not bool(_tr.get(_sw, False)):
                                continue
                            if _is_role and not _out["role_on"]:
                                continue
                            if (not _is_role) and not _out["person_on"]:
                                continue
                        if _skip_zh and self._skip_no_translate(_t):
                            continue
                        _terms.add(_t)
                        _key = (str(_row.get("item_id") or ""), str(_row.get("server_id") or ""))
                        _items.add(_key)
                        if with_detail and not _iid:
                            _d = _detail.setdefault(_key, {"item_id": _key[0], "server_id": _key[1],
                                                           "title": str(_row.get("title") or ""),
                                                           "names": [], "roles": []})
                            _lst = _d["roles"] if _is_role else _d["names"]
                            if _t not in _lst:
                                _lst.append(_t)
                    return _terms, _items, _detail

                _pt, _pi, _pd = _collect(_np.get("names"), False, True, True)
                _rt, _ri, _rd = _collect(_np.get("roles"), True, True, True)
                _out["person"] = len(_pt)
                _out["role"] = len(_rt)
                _out["items"] = len(_pi | _ri)
                _pst, _psi, _ = _collect(_ap.get("names"), False, False, False)
                _rst, _rsi, _ = _collect(_ap.get("roles"), True, False, False)
                _out["person_scope"] = len(_pst)
                _out["role_scope"] = len(_rst)
                _out["items_scope"] = len(_psi | _rsi)
                _out["terms_scope"] = _out["person_scope"] + _out["role_scope"]
                if with_detail and not _iid:
                    _merged: dict = {}
                    for _d in list(_pd.values()) + list(_rd.values()):
                        _m = _merged.setdefault((_d["item_id"], _d["server_id"]),
                                                {"item_id": _d["item_id"], "server_id": _d["server_id"],
                                                 "title": _d["title"], "names": [], "roles": []})
                        if _d["title"] and not _m["title"]:
                            _m["title"] = _d["title"]
                        for _x in _d["names"]:
                            if _x not in _m["names"]:
                                _m["names"].append(_x)
                        for _x in _d["roles"]:
                            if _x not in _m["roles"]:
                                _m["roles"].append(_x)
                    _out["items_list"] = sorted(_merged.values(),
                                                key=lambda x: (str(x.get("title") or ""),
                                                               str(x.get("item_id") or "")))
        except Exception as _e:
            logger.debug(f"[Translate] 待翻快照失败（按 0 兜底）: {_e}")
        try:
            _allow_pool = (not pool_gate) or (self._tx_source_allows("pool")
                                              and bool(getattr(self, "_pool_translation_enabled", True)))
            if _allow_pool:
                _nmx = getattr(self, "_name_map_db", None) or NameMapDb()
                _out["pool"] = int((_nmx.count_pool_status(plugin_id=_pid) or {}).get("pending") or 0)
        except Exception:
            _out["pool"] = 0
        _out["total"] = int(_out["person"] + _out["role"] + _out["pool"])
        return _out

    def _tx_eff_types(self) -> dict:
        """任务期间的**生效**翻译开关（v4.6.76 · 规范 §十三 Job Snapshot）——
        有任务快照时用创建任务那一刻的配置（运行中改设置不影响当前任务）；
        无任务（纯 UI 预估/统计）时用实时配置。"""
        _snap = getattr(self, "_tx_cfg_snapshot", None)
        if isinstance(_snap, dict) and isinstance(_snap.get("types"), dict):
            return dict(_snap["types"])
        try:
            return dict(self._collect_trans_types().get("translate", {}) or {})
        except Exception:
            return {}

    def _tx_switch_key(self, person_type: str) -> str:
        """Emby 原始职位 → 翻译类型开关键（actor/guest/director/writer/producer）。
        大小写不敏感（NFO 里可能写 "actor" / "Actor"）；未知职位返回 ""（由调用方兜底）。
        v4.6.108（LIB-016）：扫描入池的门禁要用**真实职位**去查开关，故单独抽出，
        避免各处各写一套映射导致「门禁用 A、落库用 B」的不一致。"""
        _t = str(person_type or "").strip()
        if not _t:
            return ""
        _k = self.TX_TYPE_SWITCH.get(_t)
        if _k:
            return _k
        _tl = _t.lower()
        for _kk, _vv in self.TX_TYPE_SWITCH.items():
            if _kk.lower() == _tl:
                return _vv
        return ""

    def _tx_type_enabled(self, person_type: str, scope: str = "") -> bool:
        """该人物类型是否在翻译范围内（翻译 worker 收词条 / 写回就绪判定共用同一口径）。
        需同时满足 —— 目标范围含第一排(person)、
        第一排人名总开关 translate.person、该人物类型翻译开关 translate[type]。
        scope 可显式传入（写回按候选记录的任务范围判定）。"""
        _tr = self._tx_eff_types()   # v4.6.76：任务期间用 Job Snapshot（运行中改设置不影响当前任务）
        if not self._tx_scope_allows("person", scope):
            return False
        if not bool(_tr.get("person", True)):
            return False
        _sw_key = self.TX_TYPE_SWITCH.get(str(person_type or "").strip(), "")
        if not _sw_key:
            return True   # 未分类：总开关（person）已在上方通过
        return bool(_tr.get(_sw_key, False))

    def _tx_role_type_enabled(self, person_type: str, scope: str = "") -> bool:
        """角色名（第二排）是否在翻译范围内 —— 复用同一套「类型开关」，但
        **不要求目标范围含第一排**（与 _tx_type_enabled 的唯一区别）。
        v4.6.59 修：此前角色词条也走 _tx_type_enabled，它内部要求 _tx_scope_allows("person")，
        于是用户选「只翻第二排角色」时所有角色词条被整体判为 False → 统计 0/0、
        结果提示「当前翻译目标下没有待翻译词条」（明明预估显示待翻 3 个）。
        scope 传 "both" 表示只看类型开关、不受目标范围影响（明细 / 预估用）。"""
        if not self._tx_scope_allows("role", scope):
            return False
        _tr = self._tx_eff_types()   # v4.6.76：任务期间用 Job Snapshot（运行中改设置不影响当前任务）
        if not bool(_tr.get("role", True)):
            return False
        _sw_key = self.TX_TYPE_SWITCH.get(str(person_type or "").strip(), "")
        if not _sw_key:
            return True
        return bool(_tr.get(_sw_key, False))

    def _trans_types_for_collect(self, level: str = "") -> dict:
        """供「翻译」用途调用 doc.collect() 时使用的类型过滤表。

        与「采集」区分：采集用 _collect_trans_types()["collect"]（与翻译开关无关，见 §二十二/§五十三）；
        翻译用途需同时叠加 —— 目标范围(_tx_scope_allows) + 第一排人名总开关 + 类型翻译开关；
        第二排角色由 translate.role + 目标范围含 role 决定。
        """
        _tr = self._collect_trans_types(level).get("translate", {})
        _person = bool(_tr.get("person", True)) and self._tx_scope_allows("person")
        _role = bool(_tr.get("role", True)) and self._tx_scope_allows("role")
        return {
            "actor": _person and bool(_tr.get("actor", True)),
            "guest": _person and bool(_tr.get("guest", False)),
            "director": _person and bool(_tr.get("director", False)),
            "writer": _person and bool(_tr.get("writer", False)),
            "producer": _person and bool(_tr.get("producer", False)),
            "role": _role,
        }

    def _pool_fetch_trans_types(self, level: str = "") -> List[str]:
        """人名池拉取的 Person 类型 —— **独立配置**（v4.6.48：不再跟随「翻译范围」）。

        由设置页「人名池 → 拉取类型」的独立开关决定（pool_fetch_types）。
        返回 Emby Person 类型名列表（如 ["Actor", "VoiceActor"]）；未配置时用默认（演员 + 声优）。
        只看拉取类型开关，不受「翻译范围」的类型/人数约束。
        """
        _raw = getattr(self, "_pool_fetch_types", None)
        if isinstance(_raw, str):
            _raw = [x.strip() for x in _raw.replace("，", ",").split(",")]
        if not isinstance(_raw, (list, tuple)):
            _raw = list(self.POOL_FETCH_TYPE_DEFAULT)
        out = [str(x).strip() for x in _raw if str(x).strip()]
        # 「演员」勾选即含声优：Actor 自动展开为 Actor + VoiceActor（Emby 把声优单列）
        if "Actor" in out and "VoiceActor" not in out:
            out.append("VoiceActor")
        return out

    def _tx_existing_translations(self, names=None, roles=None) -> dict:
        """统一通道 —— 自动流水线（扫描/Webhook/探测）的「现成译文」来源（库里已有译文，不调 LLM）。

        文档 §3：扫描只采集入库、§5：翻译统一交给常驻翻译 worker。流水线只写「现在就确定」的
        译文（池命中 / 库中已有 / 繁转简），剩下的词条留在 DB，由翻译 worker 翻好后由写回 worker 落盘。
        """
        try:
            db = getattr(self, "_people_db", None)
            if db is None:
                return {"names": {}, "roles": {}}
            return db.translated_map(plugin_id=self.__class__.__name__,
                                     names=list(names or []), roles=list(roles or []))
        except Exception:
            return {"names": {}, "roles": {}}

    def _translate_pending_round(self, pid: str, skip: Dict[str, int]) -> Optional[dict]:
        """翻译一轮（人物库待翻 + 人名池待翻）→ 写回对应表。无待翻返回 {"did": False}。"""
        db = getattr(self, "_people_db", None)
        nm = getattr(self, "_name_map_db", None)
        if nm is None:
            # v4.6.105（LIB-011）：兜底 —— 池句柄未初始化时就地补建（并告警一次）。
            # 此前这里没有兜底，插件重启后直接点「人名池 · 批量翻译」会静默一轮 0 条（见 init_plugin 注释）。
            try:
                nm = NameMapDb()
                self._name_map_db = nm
                self._warn_once("name_map_db_lazy",
                                "[Translate] 人名池句柄未初始化，已就地补建（正常不应发生，请检查 init_plugin）")
            except Exception as _e:
                logger.warning(f"[Translate] 人名池句柄补建失败: {_e}")
                nm = None
        _tr = self._tx_eff_types()   # v4.6.76：任务期间用 Job Snapshot（运行中改设置不影响当前任务）
        _take_library = self._tx_source_allows("library")
        _take_person = _take_library and bool(_tr.get("person", True)) and self._tx_scope_allows("person")
        _take_role = _take_library and bool(_tr.get("role", True)) and self._tx_scope_allows("role")
        _occs: List[dict] = []
        _scope_items = set(getattr(self, "_tx_scope_items", None) or ())
        if _scope_items:
            # 条目级重翻（「重新翻译」单条）：仅交给 _tx_force_round 逐条重翻，本轮不扫全库，
            # 避免「点单条重翻」把整库待翻词条一起翻掉（i1 修复）。
            return {"did": False}
        _only_terms = set(getattr(self, "_tx_only_terms", None) or ())
        # v4.6.112（GH#3-1/GH#3-7）：先算出「本轮要收多少条」= 设置页「单批最多翻译条数」，
        # 再按需从候选队列取够即止 —— 不再「把上万条全过滤一遍，最后只挑 30 条」。
        _batch = max(1, int(getattr(self, "_tx_batch_max", 0) or self.TX_BATCH))

        def _accept(_o: dict) -> bool:
            """逐条过滤（与原先 for 循环里的条件逐字一致，只是改成「取够即停」时按需调用）。"""
            _t = str(_o.get("text") or "")
            if _only_terms and _t not in _only_terms:
                return False
            if int(skip.get(_t, 0) or 0) >= self.TX_SKIP_AFTER:
                return False
            if self._skip_no_translate(_t):
                return False
            if not _only_terms:
                # v4.6.102（P0·缺陷3）：本会话已确认「无需翻译」→ 不再重发（省一次请求）；
                # 「无任何可译内容」（如 "M"）直接登记，不占单批名额、不触缩批重试。
                # 手动单选重翻（_only_terms 非空）时放行，保证人工重翻不被拦。
                if _t in self._tx_noop_terms_set():
                    return False
                if self._tx_untranslatable(_t):
                    self._tx_noop_terms_set().add(_t)
                    return False
            if _o.get("kind") == "role":
                return bool(_take_role and self._tx_role_type_enabled(_o.get("person_type")))
            return bool(_take_person and self._tx_type_enabled(_o.get("person_type")))

        try:
            # v4.6.112（GH#3-7）：候选队列 + 游标 —— 全表 SQL 每 Job 跑一次即可（见 _tx_occ_queue），
            # 每轮只沿游标向后过滤到「取够本轮条数」为止（原先每轮过滤全部待翻词条）。
            # 本次来源不含库内（如「人名池 · 批量翻译」）时**整段跳过** —— 那些行本就会
            # 被 _accept 全判否，跳过可省掉每轮一次无用的全量遍历。
            if _take_person or _take_role:
                def _fill_from(_q: dict) -> None:
                    _lst = _q.get("occs") or []
                    _i = int(_q.get("i") or 0)
                    while _i < len(_lst) and len(_occs) < _batch:
                        if _accept(_lst[_i]):
                            _occs.append(_lst[_i])
                        _i += 1
                    _q["i"] = _i

                _q = self._tx_occ_queue(pid)
                if _q.get("error"):
                    # v4.6.113（P2）：数据库读取失败 → **不得当作「真的没有可翻条目」**；
                    # 记错误标记、本轮跳过库内收词（等待重试），避免 UI / 日志误报「空轮」。
                    self._tx_occ_err = str(_q.get("error"))
                    logger.warning(f"[Translate] 本轮跳过库内收词：待翻读取数据库错误"
                                   f"（非「无可翻条目」）：{_q['error']}")
                else:
                    _fill_from(_q)
                    if not _occs and int(_q.get("i") or 0) >= len(_q.get("occs") or []):
                        # 队列走完仍取不到 → 重建一次（新入库 / 失败待重试的词条会重新出现）；
                        # 重建后还是空，才认为「真的没有可翻条目」。
                        _fill_from(self._tx_occ_queue(pid, force=True))
        except Exception as e:
            self._tx_occ_err = str(e)
            logger.warning(f"[Translate] 读取人物库待翻失败: {e}")
        # 人名池待翻（池管理条目：有原文无译文）
        pool_rows: List[dict] = []
        _person_in_scope = False   # v4.6.105：提前声明，供末尾诊断日志判定「池为什么没收」
        try:
            # v4.6.75（规范 §三-1/2）：**人名池 = 第一排** —— 目标范围不含第一排
            # （如「仅第二排角色」）或第一排人名总开关关闭时，池内人名一律不翻译。
            # 此前池行作为 kind=person 直接入列，未过目标范围门禁（未分类旧行会漏翻第一排）。
            _person_in_scope = (self._tx_scope_allows("person")
                                and bool(_tr.get("person", True)))
            if (nm is not None and self._tx_source_allows("pool")
                    and bool(getattr(self, "_pool_translation_enabled", True))
                    and _person_in_scope):
                def _pool_type_ok(_x: dict) -> bool:
                    """池行人物类型是否在翻译范围内（v4.6.44）——
                    人名池入池已按「类型开关」筛过，此处再校验一次，保证用户改开关后
                    既有池行也即时遵循「翻译受类型约束」；类型为空（旧行/未分类）视为放行。"""
                    _ts: List[str] = []
                    _pt = str(_x.get("person_type") or "").strip()
                    if _pt:
                        _ts.append(_pt)
                    try:
                        _arr = json.loads(str(_x.get("person_types") or "") or "[]")
                        if isinstance(_arr, list):
                            _ts.extend(str(_t) for _t in _arr if str(_t).strip())
                    except Exception:
                        pass
                    if not _ts:
                        return True
                    # 类型开关（v4.6.48：人数上限 0/留空 = 不限，故不再参与"翻不翻"判定）
                    return any(self._tx_type_enabled(_t) for _t in _ts)
                _pl = nm.list_pool(plugin_id=pid, status="pending", size=200) or {}
                _noop_now = self._tx_noop_terms_set()
                pool_rows = [x for x in (_pl.get("items") or [])
                             if str(x.get("name_original") or "").strip()
                             and (not _only_terms or str(x.get("name_original") or "").strip() in _only_terms)
                             and _pool_type_ok(x)
                             # v4.6.102（P0·缺陷3）：本会话已确认「无需翻译」的池行不再重发
                             and (bool(_only_terms)
                                  or str(x.get("name_original") or "").strip() not in _noop_now)
                             and int(skip.get(str(x.get("name_original") or ""), 0) or 0) < self.TX_SKIP_AFTER]
        except Exception as e:
            logger.warning(f"[Translate] 读取人名池待翻失败: {e}")
        # 池行 → occurrence（无条目上下文：item_id 空、occ_id = pool|person|text）
        _seen_occ = {str(o.get("occ_id")) for o in _occs}
        for x in pool_rows:
            _t = str(x.get("name_original") or "").strip()
            if not _t:
                continue
            _po = {"kind": "person", "text": _t, "item_id": "",
                   "server_id": str(x.get("server_id") or ""), "season_num": None,
                   "episode_num": None, "person_index": 0,
                   "person_type": str(x.get("person_type") or "Actor"), "title": ""}
            _po["occ_id"] = self._tx_occ_id(_po)
            if _po["occ_id"] not in _seen_occ:
                _seen_occ.add(_po["occ_id"])
                _occs.append(_po)
        if not _occs:
            # v4.6.80（用户实测反馈「点了批量翻译就没有然后了」）：一轮无待翻时给出**可见原因**，
            # 不再静默返回（此前只有一句 did=False，界面/日志看不出为什么什么都没发生）。
            # v4.6.105：把「池未收」的原因拆分到**具体一条** —— 此前只并列三种可能，
            # 用户实测「待翻译 89 个」却一轮 0 条时，日志看不出到底是哪一条拦的。
            _pool_why: List[str] = []
            if not self._tx_source_allows("pool"):
                _pool_why.append("本次来源不含 pool")
            if not bool(getattr(self, "_pool_translation_enabled", True)):
                _pool_why.append("「人名池翻译总开关」已关（设置页 · 人名池）")
            if not _person_in_scope:
                _pool_why.append("目标范围不含第一排 / 「第一排人名」总开关关闭")
            if nm is None:
                _pool_why.append("人名池句柄未初始化")
            _pool_hint = ("；".join(_pool_why) if _pool_why
                          else "池行被类型开关 / 已跳过项过滤（检查「翻译范围」类型开关，或用「重试失败」）")
            logger.info(f"[Translate] 本轮无可消费词条：来源={str(getattr(self, '_tx_source', '') or 'both')} "
                        f"范围={self._tx_scope()}｜库内 第一排={_take_person} 第二排={_take_role}"
                        f"（来源含 library={_take_library}）｜池={bool(pool_rows)}（{_pool_hint}）")
            return {"did": False}
        # v4.6.70（报告第二十~三十四节）：**第二排角色跨集复用** —— 同剧（server_id + item_id）
        # 同角色名已翻过的，直接复用记忆，不再调 AI；洗版重建 / 删除后恢复后同样命中。
        # 记忆与 person 表解耦：删除/恢复/清库都不清它。人工修正（source=manual）优先级最高。
        _role_mem_hits: Dict[str, tuple] = {}
        _mem_occs: Dict[str, dict] = {}
        try:
            if db is not None:
                _mkeys = [(str(o.get("server_id") or ""), str(o.get("item_id") or ""),
                           str(o.get("text") or ""))
                          for o in _occs if str(o.get("kind")) == "role"]
                _mem = db.role_memory_get(plugin_id=pid, keys=_mkeys) if _mkeys else {}
                if _mem:
                    _kept: List[dict] = []
                    for o in _occs:
                        if str(o.get("kind")) != "role":
                            _kept.append(o)
                            continue
                        _mk = (str(o.get("server_id") or ""), str(o.get("item_id") or ""),
                               str(o.get("text") or ""))
                        _hit = _mem.get(_mk)
                        if _hit and str(_hit[0]).strip():
                            _oid = str(o.get("occ_id"))
                            _role_mem_hits[_oid] = (str(_hit[0]).strip(), "series")
                            _mem_occs[_oid] = o
                            continue
                        _kept.append(o)
                    if _role_mem_hits:
                        _occs = _kept
                        logger.debug(f"[Translate] 角色记忆命中 {len(_role_mem_hits)} 条（同剧复用，未调 AI）")
        except Exception as _rme:
            logger.debug(f"[Translate] 角色记忆命中失败（非致命）: {_rme}")
        if not _occs and not _role_mem_hits:
            return {"did": False}
        # _batch 已在收词前算好（= 设置页「单批最多翻译条数」，与分块大小 _tx_batch 解耦）
        _combined = self._tx_pick_batch(_occs, _batch)
        _pool_lu = self._pool_lookup_cached()
        # 分批模式：per_title（同作品分组，各组带作品名）/ global（一次聚合；因已 occurrence 化，
        # 每条自带 title/item_id，跨作品同名也不会串译）
        # v4.6.113（P1-04）：任务期间取 Job Snapshot 的分批模式（运行中改设置不影响当前任务）
        _batching = self._tx_batching_mode()
        _nr = {"hits": {}, "llm": {}, "llm_zhc": set(), "noop": {}, "failed": [], "deferred": []}
        _rr = {"hits": {}, "llm": {}, "llm_zhc": set(), "noop": {}, "failed": [], "deferred": []}
        # v4.6.75（规范 §四-3/§十-3）：本轮「送 LLM 输入 → 去重后唯一」累计（按作品分组时累加）
        _dedup_agg = {"in": 0, "uniq": 0}

        def _merge(_dst, _src):
            _dst["hits"].update(_src.get("hits") or {})
            _dst["llm"].update(_src.get("llm") or {})
            _dst["noop"].update(_src.get("noop") or {})   # v4.6.102（P0·缺陷3）
            try:
                _dst["llm_zhc"] |= set(_src.get("llm_zhc") or ())
            except Exception:
                pass
            _dst["failed"] += list(_src.get("failed") or [])
            _dst["deferred"] += list(_src.get("deferred") or [])

        if _batching == "per_title":
            _groups: Dict[str, List[dict]] = {}
            for _o in _combined:
                _groups.setdefault(str(_o.get("title") or ""), []).append(_o)
            for _ti, _g in _groups.items():
                _mx = self._tx_translate_mixed(_g, _pool_lu, title=_ti)
                _merge(_nr, _mx["person"])
                _merge(_rr, _mx["role"])
                _dedup_agg["in"] += int(_mx.get("dedup_in") or 0)
                _dedup_agg["uniq"] += int(_mx.get("dedup_uniq") or 0)
        else:
            _mx = self._tx_translate_mixed(_combined, _pool_lu)
            _nr = _mx["person"]
            _rr = _mx["role"]
            _dedup_agg["in"] += int(_mx.get("dedup_in") or 0)
            _dedup_agg["uniq"] += int(_mx.get("dedup_uniq") or 0)
        # v4.6.70：角色记忆命中并入「角色 hits」（同样要写库 / 计数，只是没调 AI）
        if _role_mem_hits:
            _rr["hits"].update(dict(_role_mem_hits))
        _occ_by_id: Dict[str, dict] = {str(o.get("occ_id")): o for o in _combined}
        _occ_by_id.update(_mem_occs)   # 记忆命中的 occurrence 也要参与写库
        # 真失败：计入会话跳过（避免死循环重试）
        for _i in (_nr.get("failed") or []) + (_rr.get("failed") or []):
            _of = _occ_by_id.get(str(_i))
            if _of:
                skip[_of["text"]] = int(skip.get(_of["text"], 0) or 0) + 1
        # 组装译文（键 = occ_id）→ 库内 occurrence 精确写库 / 池字典写回
        _rows: List[dict] = []
        _p_zh: Dict[str, tuple] = {}
        _done_ids: set = set()
        _done_kind = {"person": 0, "role": 0}   # v4.6.70（P0-2）：完成数按第一/二排拆分
        # v4.6.102（P0·缺陷3）：「模型如实返回原文 = 无需翻译」——计入完成（不写库：
        # 译文 == 原文，写库会被「已翻译 = 译文≠原文」口径判为未翻，纯属污染），
        # 词条已由 _tx_llm_chunks 登记进本会话「无需翻译」集合，后续轮次不再重发。
        _noop_n = 0
        _noop_pool: List[tuple] = []   # v4.6.109（LIB-017）：池行里被判定「无需翻译」的 (server_id, 原文名)
        for _bk2, _is_role2 in ((_nr, False), (_rr, True)):
            for _i in (_bk2.get("noop") or {}):
                _o2 = _occ_by_id.get(str(_i))
                if _o2 is None:
                    continue
                _done_ids.add(str(_i))
                _done_kind["role" if _is_role2 else "person"] += 1
                _noop_n += 1
                if not _is_role2 and not _o2.get("item_id"):
                    # 池行（无条目身份）—— 需要把「无需翻译」这个结论**持久化到池里**
                    _noop_pool.append((str(_o2.get("server_id") or ""), str(_o2.get("text") or "")))
        if _noop_n:
            logger.info(f"[Translate] 本轮 {_noop_n} 条判定「无需翻译」（模型如实返回原文）；"
                        f"池行将标记为「无需操作」，不再重复发给模型")
        for _bk, _is_role in ((_nr, False), (_rr, True)):
            _zh_map: Dict[str, str] = {}
            _src_map: Dict[str, str] = {}
            for _i, _v in (_bk.get("hits") or {}).items():
                _zh_map[str(_i)] = str(_v[0] if isinstance(_v, tuple) else _v)
                _src_map[str(_i)] = str(_v[1] or "") if isinstance(_v, tuple) else ""
            for _i, _v in (_bk.get("llm") or {}).items():
                _zh_map[str(_i)] = str(_v)
                _src_map[str(_i)] = "llm"
            for _i, _zh in _zh_map.items():
                _o = _occ_by_id.get(_i)
                if not _o:
                    continue
                _z = str(_zh or "").strip()
                if _is_role:
                    _z = self._normalize_role_zh(_o["text"], _z)
                if not _z or _z == _o["text"]:
                    continue
                _done_ids.add(_i)
                _done_kind["role" if _is_role else "person"] += 1
                _src = _src_map.get(_i) or "llm"
                if not _is_role and not _is_kana_text(_z):
                    _p_zh.setdefault(_o["text"], (_z, _src if _src in ("llm", "zhconv") else "reused"))
                if _o.get("item_id"):
                    _rows.append({"kind": ("role" if _is_role else "name"),
                                  "original_text": _o["text"], "translation": _z,
                                  "item_id": _o["item_id"], "server_id": _o.get("server_id") or "",
                                  "season_num": _o.get("season_num"),
                                  "episode_num": _o.get("episode_num"),
                                  "person_index": _o.get("person_index") or 0})
        _n_applied = 0
        try:
            if db is not None and _rows:
                # v4.6.64（P0）：occurrence 精确写库 —— 不再用 name_before/role_before 全局 UPDATE，
                # 不同作品的同名人物/角色不会被互相污染。
                _n_applied = int(db.apply_translations_occurrence(plugin_id=pid, rows=_rows) or 0)
                _wb_seen: set = set()
                for _r in _rows:
                    _k = (str(_r.get("server_id") or ""), str(_r.get("item_id") or ""))
                    if _k in _wb_seen:
                        continue
                    _wb_seen.add(_k)
                    try:
                        self._wb_register_item(_k[1], _k[0], self._tx_scope())
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"[Translate] occurrence 写库失败: {e}")
        # 写回人名池（人名统一字典：池命中 / LLM 命中都真实回写到「当前 pending 池行本身」）
        try:
            if nm is not None:
                entries = [{"type": "person", "original": _t, "zh": _v, "source": _s}
                           for _t, (_v, _s) in _p_zh.items()]
                for _i, _v in (_rr.get("llm") or {}).items():
                    _o = _occ_by_id.get(str(_i))
                    if _o:
                        entries.append({"type": "role", "original": _o["text"],
                                        "zh": _v, "source": "llm"})
                if entries:
                    nm.set_map_many(plugin_id=pid, entries=entries)
                    self._pool_lu_cache = None  # 池已变 → 缓存作废
                for x in (pool_rows or []):
                    _t = str(x.get("name_original") or "").strip()
                    if not _t:
                        continue
                    _sid = str(x.get("server_id") or "")
                    _pid_x = str(x.get("emby_person_id") or "")
                    _idz = self._pool_identity_zh(_sid, _pid_x, _t)
                    # v4.6.107（LIB-014）：只回写**有效译文**（≠ 原文且不含假名），否则
                    # 写进去也没用（池仍判「待翻译」，下一轮照旧），优先用本轮新译文。
                    _hit = None
                    for _cand in (_p_zh.get(_t), _idz):
                        if _cand and self._zhconv_final_ok(_t, _cand[0]):
                            _hit = _cand
                            break
                    if not _hit:
                        continue
                    nm.set_pool_zh(plugin_id=pid,
                                   server_id=_sid,
                                   emby_person_id=_pid_x,
                                   name_original=_t, name_zh=_hit[0], source=_hit[1])
                # v4.6.109（LIB-017）：模型判定「无需翻译」（如实返回原文）的池行 → 落持久标记。
                # 这样它们不再计入「待翻译」（显示「无需操作」），也不会在下一个任务/重启后
                # 被重新发给模型（此前每重启一次就白烧一批 token，还永远报「剩余 N 条」）。
                # set_pool_noop 内部带 `WHERE name_zh=''` —— 绝不覆盖已有译文。
                for _sid_n, _t_n in _noop_pool:
                    if not _t_n:
                        continue
                    nm.set_pool_noop(plugin_id=pid, server_id=_sid_n,
                                     emby_person_id="", name_original=_t_n)
        except Exception as e:
            logger.warning(f"[Translate] 写回人名池失败: {e}")
        # v4.6.70（报告第二十四/二十六/二十七节）：写「同剧角色翻译记忆」——
        # 本轮的 LLM / 繁转简 / 复用结果落进记忆，后续集（含下一轮 / 洗版重建）直接命中。
        # 源优先级 manual > llm > tmdb > zhconv > reused（人工修正不会被 AI 覆盖）。
        try:
            if db is not None:
                _mem_rows: List[dict] = []
                for _i, _v in (_rr.get("llm") or {}).items():
                    _o = _occ_by_id.get(str(_i))
                    if _o:
                        _mem_rows.append({"server_id": str(_o.get("server_id") or ""),
                                          "series_id": str(_o.get("item_id") or ""),
                                          "series_name": str(_o.get("title") or ""),
                                          "role_original": str(_o.get("text") or ""),
                                          "role_translated": str(_v), "source": "llm"})
                for _i, _vv in (_rr.get("hits") or {}).items():
                    _o = _occ_by_id.get(str(_i))
                    if not _o:
                        continue
                    _s = str(_vv[1] or "") if isinstance(_vv, tuple) else ""
                    _src = {"zhconv": "zhconv", "pool": "reused", "series": "reused"}.get(_s, "reused")
                    _zh = str(_vv[0] if isinstance(_vv, tuple) else _vv)
                    _mem_rows.append({"server_id": str(_o.get("server_id") or ""),
                                      "series_id": str(_o.get("item_id") or ""),
                                      "series_name": str(_o.get("title") or ""),
                                      "role_original": str(_o.get("text") or ""),
                                      "role_translated": _zh, "source": _src})
                if _mem_rows:
                    db.role_memory_put(plugin_id=pid, rows=_mem_rows)
        except Exception as e:
            logger.debug(f"[Translate] 写角色记忆失败（非致命）: {e}")
        # 统计
        _hits = len(_nr.get("hits") or {}) + len(_rr.get("hits") or {})
        _llm_n = len(_nr.get("llm") or {}) + len(_rr.get("llm") or {})
        try:
            self._pool_hits += _hits
            self._llm_terms += _llm_n
        except Exception:
            pass
        _done = len(_done_ids)
        _deferred = len(_nr.get("deferred") or []) + len(_rr.get("deferred") or [])
        if not _done and not _deferred:
            return {"did": False}

        # v4.6.70（P0-2）：按第一/二排拆分 + 把「池命中 / 繁转简 / LLM 输出简体化」分成三项 ——
        # 此前只报一个「池/繁简命中」，用户无法判断命中来自哪一排、是哪一类。
        # v4.6.74（报告第六 / 二十三节）：再拆出「角色 Memory（同剧记忆）」与「TMDB」——
        # 用户要求的最终口径：LLM / 角色 Memory / 人名池 / TMDB / 繁转简 / LLM 输出简体化。
        def _kind_stat(_b: dict, _kind: str) -> dict:
            _pool = _zhc = _mem = _tmdb = 0
            for _v in (_b.get("hits") or {}).values():
                _s = str(_v[1] or "") if isinstance(_v, tuple) else ""
                if _s == "zhconv":
                    _zhc += 1
                elif _s == "series":
                    _mem += 1           # 同剧角色翻译记忆命中（不调 AI）
                elif _s == "tmdb":
                    _tmdb += 1          # TMDB 刮削命中（人名池里的 tmdb 源）
                else:
                    _pool += 1          # 人名池命中 / 库已有译文 / 复用
            return {"done": int(_done_kind.get(_kind, 0)),
                    "llm": len(_b.get("llm") or {}),
                    "pool": _pool, "role_mem": _mem, "tmdb": _tmdb, "zhconv": _zhc,
                    "llm_zhc": len(_b.get("llm_zhc") or set()),
                    "failed": len(_b.get("failed") or [])}
        _by_kind = {"person": _kind_stat(_nr, "person"), "role": _kind_stat(_rr, "role")}
        _pool_n = _by_kind["person"]["pool"] + _by_kind["role"]["pool"]
        _zhc_n = _by_kind["person"]["zhconv"] + _by_kind["role"]["zhconv"]
        _llm_zhc_n = _by_kind["person"]["llm_zhc"] + _by_kind["role"]["llm_zhc"]

        # v4.6.63：译文条数与真实写库行数不一致时告警（occurrence 不匹配 / 译文等于原文）
        if _rows and _n_applied == 0:
            logger.warning(f"[Translate] 本轮解析出 {len(_rows)} 条库内译文但写库 0 行"
                           f"（occurrence 不匹配或译文等于原文）—— 词条仍留待翻列表")
        return {
            "did": True,
            "done": _done, "llm": _llm_n, "hits": _hits, "applied": _n_applied,
            "failed": len(_nr.get("failed") or []) + len(_rr.get("failed") or []),
            "deferred": _deferred,
            "left": max(0, len(_occs) - len(_combined)),
            "current": (str(_combined[0].get("text") or "") if _combined else ""),
            # v4.6.70（P0-2）：拆分统计
            "pool": _pool_n, "zhconv": _zhc_n, "llm_zhc": _llm_zhc_n,
            # v4.6.75（规范 §四-3/§十-3）：输入条数 → 去重后唯一条数（AI 聚合自证）
            "dedup_in": int(_dedup_agg["in"]), "dedup_uniq": int(_dedup_agg["uniq"]),
            "by_kind": _by_kind,
        }

    # ============================================================
    # ============================================================
    WB_BATCH = 8            # 每轮处理条目数（写回是文件 IO，一批不宜过大）
    WB_MAX_ATTEMPTS = 3     # 失败自动重试上限（超过后等新译文重新登记 / 手动「全部写回」）
    WB_RETRY_AFTER = 600.0  # 失败条目自动重试最小间隔（秒）

    def _wb_writeback_enabled(self) -> bool:
        """自动写回门控（文档 §3.8/§3.12）—— auto_writeback 关或旧预览模式开 → 不自动写回。
        （预览模式旧语义本阶段保持：预览开 = 翻译完不自动写回。）
        v4.6.99（报告 P1-03 A）：任务运行期间取 Job Snapshot 的写回策略 ——
        运行中改「自动写回 / 预览模式」不影响当前 Job（新设置从下一个任务生效）。"""
        try:
            _snap = getattr(self, "_tx_cfg_snapshot", None)
            if isinstance(_snap, dict) and "auto_writeback" in _snap:
                return (bool(_snap.get("auto_writeback"))
                        and not bool(_snap.get("nfo_preview")))
            return (bool(getattr(self, "_auto_writeback", True))
                    and not bool(getattr(self, "_nfo_preview", False)))
        except Exception:
            return False

    def _wb_wake(self) -> None:
        """唤醒写回 worker（翻译 worker 登记新候选后调用）。"""
        try:
            _ev = getattr(self, "_wb_event", None)
            if _ev is None:
                self._wb_event = _ev = threading.Event()
            _ev.set()
        except Exception:
            pass

    def _wb_stop_requested(self) -> bool:
        """写回 worker 只读自己的停止位（独立停止位 + 插件禁用）。"""
        if not getattr(self, "_enabled", False):
            return True
        return bool(getattr(self, "_wb_stop", False))

    def _wb_db(self):
        """写回状态库（惰性单例）。"""
        _d = getattr(self, "_writeback_db", None)
        if _d is None:
            _d = WritebackDb()
            self._writeback_db = _d
        return _d

    # ── 条目级互斥（v4.6.73 · 报告第十六节）──
    def _item_lock(self, server_id: str, item_id: str):
        """某条目（server_id + item_id）的进程内可重入锁 —— 同一条目同一时刻只允许
        一个写回/重翻在跑；其它条目不受影响（保守安全模式：不再全局串行）。"""
        try:
            _lk = getattr(self, "_item_locks", None)
            if _lk is None:
                _lk = self._item_locks = {}
            _gd = getattr(self, "_item_locks_guard", None)
            if _gd is None:
                _gd = self._item_locks_guard = threading.RLock()
            _k = (str(server_id or ""), str(item_id or ""))
            with _gd:
                _o = _lk.get(_k)
                if _o is None:
                    _o = _lk[_k] = threading.RLock()
                return _o
        except Exception:
            return threading.RLock()

    def _item_enter(self, server_id: str, item_id: str):
        """占用某条目（获取互斥锁 + 记 busy 标记）；必须与 _item_leave 成对。"""
        _k = (str(server_id or ""), str(item_id or ""))
        _lk = self._item_lock(*_k)
        _lk.acquire()
        try:
            _bs = getattr(self, "_item_busy_set", None)
            if _bs is None:
                _bs = self._item_busy_set = set()
            _bs.add(_k)
        except Exception:
            pass
        return _lk

    def _item_leave(self, server_id: str, item_id: str) -> None:
        """释放某条目（清 busy 标记 + 释放互斥锁）。"""
        _k = (str(server_id or ""), str(item_id or ""))
        try:
            _bs = getattr(self, "_item_busy_set", None)
            if _bs is not None:
                _bs.discard(_k)
        except Exception:
            pass
        try:
            self._item_lock(*_k).release()
        except Exception:
            pass

    def _item_busy(self, server_id: str, item_id: str) -> bool:
        """该条目当前是否有写回/重翻在进行（用于「同一条目互斥」门禁）。"""
        try:
            return (str(server_id or ""), str(item_id or "")) in (
                getattr(self, "_item_busy_set", None) or set())
        except Exception:
            return False

    def _start_writeback_worker(self) -> None:
        """启动常驻写回 worker（单例防重：热加载/重复 init 不产生第二份，文档 §41）。"""
        try:
            _t = getattr(self, "_wb_thread", None)
            if _t is not None and _t.is_alive():
                return
            self.__class__._wb_active = self
            self._wb_stop = False
            self._wb_event = getattr(self, "_wb_event", None) or threading.Event()
            self.__class__._wb_cursor = 0
            # 重启恢复（文档 §50）：进程/线程中断留下的 writing 行复位为 pending —— 写文件幂等，重跑安全
            try:
                _n = self._wb_db().reset_writing(plugin_id=self.__class__.__name__)
                if _n:
                    logger.info(f"[Writeback] 发现 {_n} 个中断的写回条目（writing），已复位为待写回并自动重试")
            except Exception:
                pass
            self._wb_thread = threading.Thread(target=self._writeback_worker,
                                               daemon=True, name="epl-writeback")
            self._wb_thread.start()
            logger.info("[Writeback] 写回 worker 已启动（常驻：条目翻完自动写回 nfo；幂等可重入）")
        except Exception as e:
            logger.warning(f"[Writeback] worker 启动失败: {e}")

    def _wb_item_fp(self, item_id: str, server_id: str = "") -> str:
        """条目写回指纹 = md5(译文行 + nfo 文件签名)，幂等判据（文档 §15/§16）。
        译文更新（含重新采集后重翻）或文件被外部替换/删除 → 指纹变化 → 允许再写回；
        与上次写回后的指纹一致 → 内容没变，不重复写。"""
        try:
            db = getattr(self, "_people_db", None)
            if db is None:
                return ""
            rows = db.people_of_item(plugin_id=self.__class__.__name__,
                                     item_id=str(item_id or ""),
                                     server_id=str(server_id or "")) or []
            parts = []
            for r in rows:
                parts.append("|".join(str(r.get(k) if r.get(k) is not None else "") for k in
                                      ("index", "type", "season_num", "episode_num",
                                       "name_before", "name_after", "role_before", "role_after", "nfo_path")))
            paths = sorted({str(r.get("nfo_path") or "").strip()
                            for r in rows if str(r.get("nfo_path") or "").strip()})
            for p in paths:
                parts.append(f"{p}={self._file_sig(p) or 'missing'}")
            if not parts:
                return ""
            return hashlib.md5("\n".join(parts).encode("utf-8")).hexdigest()[:12]
        except Exception:
            return ""

    def _wb_register_item(self, item_id: str, server_id: str = "", target_scope: str = "") -> str:
        """把「有新译文的条目」登记为写回候选（翻译 worker 每轮调用，文档 §3.4）。
        指纹只在需要做幂等比较时计算（状态 done/failed/missing）—— 省掉常规路径的文件 stat 开销。
        target_scope 随登记落库（person/role/both）—— 就绪判定按候选记录的任务范围，
        不再依赖瞬时 _tx_target_scope（防「只翻第二排」任务结束后第一排 pending 重新阻塞写回）。"""
        _item = str(item_id or "").strip()
        if not _item:
            return "skip"
        try:
            wdb = self._wb_db()
            _fp = ""
            rec = wdb.get(plugin_id=self.__class__.__name__,
                          server_id=str(server_id or ""), item_id=_item)
            if rec is not None and str(rec.get("status") or "") == "writing":
                return "skip"
            if rec is not None and str(rec.get("status") or "") in ("done", "failed", "missing"):
                _fp = self._wb_item_fp(_item, server_id)
            _r = wdb.register(plugin_id=self.__class__.__name__, server_id=str(server_id or ""),
                              item_id=_item, file_sig=_fp, target_scope=str(target_scope or ""))
            if _r in ("new", "pending"):
                self._wb_wake()
            return _r
        except Exception as e:
            logger.debug(f"[Writeback] 登记候选失败 {item_id}: {e}")
            return "skip"

    def translation_pending_for_item(self, *, item_id: str, server_id: str = "", scope: str = "") -> dict:
        """条目「翻译就绪」统一判定（文档 §1.2-8）—— 自动写回门槛的唯一入口。

        只有「仍会被翻译」的待翻词条才阻塞写回：
          - 类型开关关闭 / 角色开关关闭 → 不计（不翻的类型永远不会有译文）；
          - 已在翻译失败清单 → 不计（不让个别词条卡死整个条目；重试成功后会重新登记写回）；
          - 人名池已有译文（池命中）→ 不计（worker 消费即补上，写回池补充映射也会带上）；
          - AI 关闭 → LLM 类待翻词条无法解析 → 不计（先写已翻部分，开启 AI 后重新登记再补）。
        scope 为「该写回候选登记时的任务范围」—— 只按那个上下文判阻塞，
        不再读瞬时 _tx_target_scope（任务结束后不会被另一排的 pending 重新阻塞）。
        观察期/文件不存在不在本函数处理：写回时按「全部文件缺失 → missing」单计（不报普通失败）。
        :return: {"ready": bool, "pending": int, "blocked": [词条...]}
        """
        out = {"ready": True, "pending": 0, "blocked": []}
        try:
            db = getattr(self, "_people_db", None)
            if db is None:
                return out
            rows = db.pending_terms_of_item(plugin_id=self.__class__.__name__,
                                            item_id=str(item_id or ""), server_id=str(server_id or ""),
                                            exclude_episodes=self._tx_exclude_episodes())
            _tr = self._collect_trans_types().get("translate", {})
            _scope = str(scope or "").strip().lower()
            if _scope not in ("person", "role", "both"):
                _scope = self._tx_scope()
            _take_role = bool(_tr.get("role", True)) and self._tx_scope_allows("role", _scope)
            _ai = self._ai_enabled()
            _failed = getattr(self, "_failed_terms", None) or set()
            try:
                _pool = self._pool_lookup_cached() or {}
            except Exception:
                _pool = {}
            blocked = []
            for r in rows:
                _t = str(r.get("term") or "").strip()
                if not _t or _t in _failed:
                    continue
                _kind = "role" if str(r.get("kind")) == "role" else "name"
                _pool_kind = "role" if _kind == "role" else "person"
                if self._skip_no_translate(_t):
                    continue   # v4.6.54：原文已是简体中文 → 无需翻译，不阻塞写回
                if _kind == "role":
                    if not _take_role:
                        continue
                    # v4.6.59：与被关闭的类型成对 —— 关掉的类型不该阻塞写回（否则永远等不到 worker 消费）
                    if not self._tx_role_type_enabled(r.get("person_type"), _scope):
                        continue
                else:
                    if not self._tx_type_enabled(r.get("person_type"), _scope):
                        continue
                _hit = None
                if _pool_kind == "person" and str(server_id or "").strip():
                    _hit = self._pool_identity_zh(str(server_id), "", _t)
                if _hit is None:
                    _hit = _pool.get((_pool_kind, _t))
                if _hit and str(_hit[0] or "").strip() and str(_hit[0]).strip() != _t:
                    continue  # 池命中：worker 消费后即补上，不阻塞
                if not _ai:
                    continue  # AI 关闭：LLM 类词条无法解析，不阻塞（先写已翻部分）
                blocked.append(_t)
            out["blocked"] = blocked
            out["pending"] = len(blocked)
            out["ready"] = not blocked
        except Exception as e:
            logger.debug(f"[Writeback] 就绪判定异常 {item_id}: {e}")
        return out

    def _wb_process_item(self, pi_d: str, rec: dict) -> dict:
        """条目级互斥包装（v4.6.73 · 报告第十六节）—— 同一条目同一时刻只跑一个写回，
        条目忙则本轮跳过（下一轮重试），其它条目照常；真实现见 _wb_process_item_locked。"""
        _iid = str(rec.get("item_id") or "")
        _sid = str(rec.get("server_id") or "")
        if self._item_busy(_sid, _iid):
            return {"not_ready": 1, "current": _iid}
        self._item_enter(_sid, _iid)
        try:
            return self._wb_process_item_locked(pi_d, rec)
        finally:
            self._item_leave(_sid, _iid)

    def _wb_process_item_locked(self, pi_d: str, rec: dict) -> dict:
        """处理单个条目 —— 就绪判定 → 写文件 → 标状态（顺序纪律：先成功写文件再标 done）。
        落盘统一经 _write_nfo_once；只有它返回 success 才在本函数标 done。"""
        wdb = self._wb_db()
        item_id = str(rec.get("item_id") or "")
        server_id = str(rec.get("server_id") or "")
        title = item_id
        try:
            _db = getattr(self, "_people_db", None)
            _m = _db.item_meta(plugin_id=pi_d, item_id=item_id, server_id=server_id) if _db is not None else None
            if _m and str(_m.get("title") or "").strip():
                title = str(_m.get("title")).strip()
        except Exception:
            pass
        # 幂等 1：writing → 跳过（同一个条目只能有一个写回任务，文档 §15）
        if str(rec.get("status") or "") == "writing":
            return {"skip_writing": 1, "current": title}
        # 就绪判定：还有会被翻译的待翻词条 → 等下一轮（文档 §1.2-8 / §3.4）
        chk = self.translation_pending_for_item(item_id=item_id, server_id=server_id,
                                                scope=str(rec.get("target_scope") or ""))
        if not chk.get("ready"):
            return {"not_ready": 1, "current": title}
        # 先标 writing（防并发；失败/中断后由 reset/退避恢复），失败计数 +1
        wdb.set_status(plugin_id=pi_d, server_id=server_id, item_id=item_id,
                       nfo_path=str(rec.get("nfo_path") or ""), status="writing",
                       error="", bump_attempt=True)
        try:
            r = self._restore_item_to_nfo(item_id, server_id, auto=True)
        except Exception as e:
            r = {"success": False, "message": str(e)}
        d = r.get("data") or {}
        _recent = (str(r.get("message") or "")[:200] or "未知原因")
        if r.get("success"):
            # 顺序纪律：文件写成功 → 才标 done（写回失败不能标记成功，文档 §46）
            # 自动路径下「内容已是译文（apply 改动 0）」不落盘（noop），同样算成功
            _fp = self._wb_item_fp(item_id, server_id)
            wdb.set_status(plugin_id=pi_d, server_id=server_id, item_id=item_id,
                           status="done", error="", changed_count=int(d.get("changed") or 0),
                           file_sig=_fp)
            return {"written": 1, "changed": int(d.get("changed") or 0),
                    "noop": 1 if d.get("noop") else 0, "current": title}
        if d.get("missing") or d.get("skip"):
            # 文件全不存在（删除/观察期）或早期 API 在线记录（无本地 nfo）—— 不是普通失败，不再空转重试
            wdb.set_status(plugin_id=pi_d, server_id=server_id, item_id=item_id,
                           status="missing", error=_recent, file_sig=self._wb_item_fp(item_id, server_id))
            return {"missing": 1, "current": title}
        # 真失败（文件占用/只读/解析失败）→ failed，绝不标成功；靠退避重试或新译文重新登记
        wdb.set_status(plugin_id=pi_d, server_id=server_id, item_id=item_id,
                       status="failed", error=_recent)
        return {"failed": 1, "current": title, "error": _recent}

    def _wb_failed_retryable(self, rec: dict) -> bool:
        """失败条目是否可以自动重试（次数上限 + 最小间隔退避）。"""
        try:
            if int(rec.get("attempts") or 0) >= int(self.WB_MAX_ATTEMPTS):
                return False
            _last = str(rec.get("last_attempt_at") or "").strip()
            if not _last:
                return True
            try:
                _ts = datetime.strptime(_last, "%Y-%m-%dT%H:%M:%S").timestamp()
            except Exception:
                try:
                    _ts = datetime.fromisoformat(_last).timestamp()
                except Exception:
                    return True
            return (time.time() - _ts) >= float(self.WB_RETRY_AFTER)
        except Exception:
            return True

    def _writeback_pending_round(self, pi_d: str) -> Optional[dict]:
        """写回一轮 —— 取 pending（游标轮转，就绪未到的不饿死后面的）+ 到期的 failed 重试。"""
        wdb = self._wb_db()
        # WB-003 租约恢复：超时仍停留在 writing 的行复位为 pending（worker 崩溃/被强杀自愈）
        try:
            _stale = wdb.reset_stale_writing(plugin_id=pi_d)
            if _stale:
                logger.warning(f"[Writeback] {_stale} 个写回条目停留在 writing 超时，"
                               f"已复位为待写回并自动重试")
        except Exception:
            pass
        _cur = int(getattr(self.__class__, "_wb_cursor", 0) or 0)
        rows = wdb.list_by_status(plugin_id=pi_d, status="pending",
                                  limit=self.WB_BATCH, after_id=_cur)
        if rows:
            self.__class__._wb_cursor = int(rows[-1].get("id") or 0)
        else:
            # 本轮无 pending → 游标回到开头
            self.__class__._wb_cursor = 0
        # WB-002：失败重试不再等「pending 清空」才排队 —— 每轮都掺入到期的 failed，
        # 否则持续有新翻译时老失败条目可能长期得不到重试。
        # 注意：游标只按 pending 行推进（上面已完成），掺入的 failed 不影响轮转。
        try:
            _retry = [r for r in wdb.list_by_status(plugin_id=pi_d, status="failed", limit=50)
                      if self._wb_failed_retryable(r)]
        except Exception:
            _retry = []
        if _retry:
            _seen = {int(r.get("id") or 0) for r in rows}
            _slots = max(1, self.WB_BATCH - len(rows))
            rows = list(rows) + [r for r in _retry if int(r.get("id") or 0) not in _seen][:_slots]
        if not rows:
            return {"did": False}
        stats = {"did": False, "written": 0, "changed": 0, "noop": 0,
                 "failed": 0, "missing": 0, "not_ready": 0, "skip_writing": 0,
                 "current": "", "error": ""}
        for rec in rows:
            if self._wb_stop_requested() or not self._wb_writeback_enabled():
                break
            # 让位：手动「全部写回」在跑 / 扫描在跑（扫描当前仍内联写 nfo，避免同文件两个写者）
            if self._task_running("writeback") or self._task_running("scan"):
                break
            try:
                _r = self._wb_process_item(pi_d, rec)
            except Exception as e:
                _r = {"failed": 1}
                logger.warning(f"[Writeback] 处理条目异常 {rec.get('item_id')}: {e}")
            for _k in ("written", "changed", "noop", "failed", "missing",
                       "not_ready", "skip_writing"):
                stats[_k] = int(stats.get(_k) or 0) + int(_r.get(_k) or 0)
            if _r.get("current"):
                stats["current"] = str(_r.get("current"))
            if _r.get("error"):
                stats["error"] = str(_r.get("error"))
            if _r.get("written") or _r.get("failed") or _r.get("missing") or _r.get("skip_writing"):
                stats["did"] = True
        return stats

    def _writeback_worker(self) -> None:
        """常驻写回 worker 主体（文档 §3.10：常驻 + 空闲退避轮询）。"""
        _pid = self.__class__.__name__
        _idle = 0
        _last_log = 0.0
        while True:
            try:
                # 热加载防重：已被新实例的 worker 接管 → 本线程退出（防双份消费）
                _act = getattr(self.__class__, "_wb_active", None)
                if _act is not None and _act is not self:
                    logger.info("[Writeback] 检测到新实例接管，旧写回 worker 退出")
                    return
                _ev = getattr(self, "_wb_event", None)
                if _ev is None:
                    self._wb_event = _ev = threading.Event()
                if self._wb_stop_requested():
                    _ev.wait(1.0); _ev.clear(); continue
                # 让位（同 _writeback_pending_round 内判断，这里先睡再查，避免空转）
                if self._task_running("writeback") or self._task_running("scan"):
                    _ev.wait(1.0); _ev.clear(); continue
                if not self._wb_writeback_enabled():
                    # 自动写回关 / 预览模式开：待命（手动「全部写回」不受影响）
                    _ev.wait(1.0); _ev.clear(); continue
                _st = self._writeback_pending_round(_pid)
                if not _st or not _st.get("did"):
                    _idle += 1
                    _wait = 1.0 if _idle < 3 else (2.0 if _idle < 10 else 5.0)
                    if self._writeback_status.get("running"):
                        self._writeback_status["running"] = False
                    _ev.wait(_wait); _ev.clear(); continue
                _idle = 0
                self._writeback_status.update({
                    "running": True, "phase": "writeback",
                    "total": int(_st.get("written") or 0) + int(_st.get("failed") or 0)
                             + int(_st.get("missing") or 0),
                    "done": int(_st.get("written") or 0),
                    "failed": int(_st.get("failed") or 0),
                    "missing": int(_st.get("missing") or 0),
                    "current": str(_st.get("current") or ""),
                })
                if time.time() - _last_log >= 15:
                    _last_log = time.time()
                    self._push_log("INFO", f"自动写回：本轮完成 {_st.get('written', 0)} 个条目"
                                           f"（改动 {_st.get('changed', 0)} 条 · 已是译文 {_st.get('noop', 0)}）"
                                           f"，失败 {_st.get('failed', 0)}，文件缺失 {_st.get('missing', 0)}，"
                                           f"等待翻译 {_st.get('not_ready', 0)}")
            except Exception as e:
                logger.warning(f"[Writeback] worker 轮次异常: {e}")
                try:
                    time.sleep(2)
                except Exception:
                    pass

    def _api_nfo_sync(self, data: Optional[dict] = None):
        """后台线程执行 NFO 扫描，立即返回。
        锁内置位启动 —— 消除「检查 _is_running」与「线程置位」之间的竞态窗口，
        避免批量触发时双开两个同步线程并发写同一批 NFO。"""
        _g = self._api_gate()
        if _g:
            return _g
        data = data or {}
        _err = self._launch_nfo_worker(data)
        if _err:
            return _err
        self._push_log("INFO", "已触发 NFO 扫描（后台执行）")
        return {"success": True, "message": "NFO 扫描已启动，运行详情见仪表盘日志"}

    def _api_translate_all(self, data: Optional[dict] = None):
        """仪表盘「续跑」（原「全部翻译」，v4.2.1 改名）—— 续扫未完成：
        尊重断点（断点里已处理的文件跳过，只补未完成的）+ 跳过预览模式（真正翻译并写回文件）。
        「失效/待恢复」条目：文件回归时库记录自动恢复（upsert 清 deleted_at 标记），
        但断点内文件不重翻（除非改配置作废签名或强制重扫）—— 已如实标注，避免误导。
        force=False 保留断点跳过，preview=False 确保走完整翻译写回流水线而非预览只采集。
        语义严格化 —— 只有存在有效断点（上轮被停止/异常中断且配置未变）时才允许执行；
        无断点直接拒绝（防误点变成全量重扫；全量处理请走「NFO 扫描」）。
        """
        _g = self._api_gate()
        if _g:
            return _g
        _rs = self._nfo_resume_state()
        if not _rs.get("ok"):
            return {"success": False,
                    "message": "没有可续跑的断点（上轮扫描已正常跑完，或配置已变更使断点作废）。需要全量处理请点「NFO 扫描」"}
        body = dict(data or {})
        body["force_translate"] = False   # 不强制重翻已完成文件（续扫：断点里已处理的跳过）
        _pv = bool(getattr(self, "_nfo_preview", False))
        body["preview"] = _pv
        body["write_files"] = not _pv
        body["translate_all_mode"] = True
        _err = self._launch_nfo_worker(body)
        if _err:
            return _err
        if _pv:
            self._push_log("INFO", f"已触发续跑（已处理 {_rs.get('done', 0)} 个文件，预览模式已开：只采集入库，不写文件；确认后点「全部写回」落盘 nfo）")
        else:
            self._push_log("INFO", f"已触发续跑（已处理 {_rs.get('done', 0)} 个文件：跳过已处理的，采集入库并用现成译文写回；"
                                   f"剩余词条由后台翻译 worker 自动补全并写回；含失效/待恢复条目重新核对）")
        return {"success": True,
                "message": ("续跑已启动（续扫未完成，预览模式已开：只入库不写文件）" if _pv
                            else "续跑已启动（续扫未完成；已采集入库，剩余词条由后台自动翻译并写回）"),
                "data": {"preview": _pv, "done": _rs.get("done", 0)}}

    def _collect_trans_types(self, level: str = "") -> dict:
        """完整翻译类型开关字典（缺陷 H）—— 供三条流水线的 collect() 做类型过滤。
        增加 limits —— {"actor": N, ...}，0=不翻该类型（数量必填才翻），
        N>0=每文件前 N 个。返回 {"switches": {...}, "limits": {...}}。
        D —— limits 拆电影/剧两套（类型开关全局共用，数量独立）：
        level=movie → 电影套（movie.nfo）；level=tvshow → 剧套主演（tvshow.nfo 前 N）；
        level=episode → 单集套（episode.nfo 前 N + 剧套客串/导演/编剧）；
        level 空 → 返回电影套（兼容旧调用，库内翻译/记录按各自 doc 层级传参）。
        采集与翻译彻底解耦 —— 返回值扩展为
          collect   采集什么（与翻译开关无关；入库范围只受 limits 人数上限约束，
                    第一排 OFF 时仍照常采集入库，见 §五十三/§六十四）
          translate 翻译什么（person=第一排人名总开关；role=第二排角色总开关；
                    actor/guest/director/writer/producer=第一排人名翻译的类型范围）
          switches  旧调用兼容（= translate 的 actor..role 子集，不再含 person）
          limits    每类型「最多采集多少」（§二十五）
        """
        _all = bool(getattr(self, "_translate_all", False))
        # 采集：与翻译解耦 —— 采集范围不再受任何翻译开关影响（§二十二/§五十三）。
        collect = {
            "actor": True,
            "guest": True,
            "director": True,
            "writer": True,
            "producer": True,
            "role": True,
        }
        # 翻译：第一排人名总开关 + 第二排角色总开关 + 第一排人名类型范围（§二十四/§三十七）。
        translate = {
            "person": _all or bool(getattr(self, "_translate_person", True)),
            "role": _all or bool(getattr(self, "_translate_role", True)),
            "actor": _all or bool(getattr(self, "_translate_actor", True)),
            "guest": _all or bool(getattr(self, "_translate_guest_star", False)),
            "director": _all or bool(getattr(self, "_translate_director", False)),
            "writer": _all or bool(getattr(self, "_translate_writer", False)),
            "producer": _all or bool(getattr(self, "_translate_producer", False)),
        }
        switches = {
            "actor": translate["actor"],
            "guest": translate["guest"],
            "director": translate["director"],
            "writer": translate["writer"],
            "producer": translate["producer"],
            "role": translate["role"],
        }
        # 人数上限（v4.6.48 三段式最简）：**一套数字**（电影 / 剧 / 单集共用），
        # 数字 = 每文件每类型取前 N 个；0 / 留空 = 不限（翻该类型全部）。
        # 「翻不翻该类型」由上面的类型开关（translate）决定，与人数解耦。
        limits = {
            "actor": max(0, int(getattr(self, "_actor_limit", 0) or 0)),
            "guest": max(0, int(getattr(self, "_guest_limit", 0) or 0)),
            "director": max(0, int(getattr(self, "_director_limit", 0) or 0)),
            "writer": max(0, int(getattr(self, "_writer_limit", 0) or 0)),
        }
        return {"collect": collect, "translate": translate,
                "switches": switches, "limits": limits}

    def _tx_limits_by_level(self) -> dict:
        """人数上限（**一套**，两排 / 各 doc 层级共用）—— 结构兼容 db.pending_terms(limits=...)。
        v4.6.48 三段式最简：电影 / 剧 / 单集不再分开，三个层级返回同一份。
        v4.6.99（报告 P1-03 A）：任务运行期间取 Job Snapshot 的「人数上限」——
        运行中改「每文件前 N 个」不影响当前任务（新设置从下一个任务生效）。"""
        _snap = getattr(self, "_tx_cfg_snapshot", None)
        if isinstance(_snap, dict) and isinstance(_snap.get("limits"), dict) and _snap.get("limits"):
            try:
                _l = _snap["limits"]
                return {"movie": dict(_l.get("movie") or {}),
                        "tvshow": dict(_l.get("tvshow") or {}),
                        "episode": dict(_l.get("episode") or {})}
            except Exception:
                pass
        _one = self._collect_trans_types().get("limits", {}) or {}
        return {"movie": dict(_one), "tvshow": dict(_one), "episode": dict(_one)}

    def _tx_exclude_episodes(self) -> bool:
        """「处理单集」=关 → 待翻口径统一排除 Episode 层级行（v4.6.68）。

        单集仍会入库（供「库」页查看/编辑），但不进入：待翻统计 / 翻译预估 /
        worker 收词 / 写回就绪判定 / 重新翻译 —— 即「不参与翻译、不调 AI」。
        所有 db 待翻查询调用点都必须传本值，保证 扫描 / 定时扫描 / 探测库 /
        Webhook / Series 展开 / 删除恢复 各入口口径完全一致。
        v4.6.76（规范 §十三）：任务运行期间取 Job Snapshot 的值 —— 运行中改「处理单集」
        不影响当前任务（新设置从下一个任务生效）。
        """
        _snap = getattr(self, "_tx_cfg_snapshot", None)
        if isinstance(_snap, dict) and "exclude_episodes" in _snap:
            return bool(_snap.get("exclude_episodes"))
        return not bool(getattr(self, "_nfo_include_episodes", False))

    def _ai_enabled(self) -> bool:
        """C —— AI 翻译总开关。关闭后仅禁 LLM：池命中/繁转简/人工修正照常，
        采集原文照旧入库。"""
        return bool(getattr(self, "_enable_ai", True))

    @staticmethod
    def _normalize_role_zh(orig: str, zh: str) -> str:
        """角色名统一保留「配音」标记 —— LLM 对 "(voice)" 后缀的翻译时有时无
        （有的给「（配音）」、有的直接省略），导致同一部剧里有的角色带、有的不带。
        规则：原文含 (voice) /（voice） 等标记 → 译文统一补齐全角「配音」，去掉残留英文。
        原文无 voice 标记的角色名原样返回（如导演/编剧职能角色）。
        """
        z = (zh or "").strip()
        o = (orig or "").strip()
        if not z or not o:
            return z
        has_voice = bool(re.search(r"\(\s*voice\s*\)", o, re.IGNORECASE))
        if not has_voice:
            return z
        # 去掉译文里残留的 (voice)/（voice）与已存在的中文「（配音）」括注，避免双写
        z = re.sub(r"[（(]\s*voice\s*[)）]", "", z, flags=re.IGNORECASE).strip()
        z = re.sub(r"[（(]\s*配音\s*[)）]", "", z).strip()
        if z and "配音" not in z:
            z += "（配音）"
        return z


    def _nfo_sync_worker(self, data: Optional[dict] = None):
        """NFO 扫描线程体：采集→翻译→写回→人名池，完成后释放运行状态。
        运行位走 scan 位（translate/writeback/pool 位互不影响）。"""
        self._set_task_running("scan", True)
        self._scan_status["running"] = True
        self._scan_status["paused"] = False
        self._scan_status["current_title"] = "NFO 扫描中..."
        self._scan_status["total"] = 0
        self._scan_status["done"] = 0
        self._tmdb_credits_cache = {}
        # v4.6.111（LIB-020）：本轮扫描的「TMDB 查不到」明细队列清零（结束时会汇总成一行）
        self._tmdb_empty_log = []
        _sig: str = ""
        _done: Dict[str, str] = {}
        _sigs_new: Dict[str, str] = {}
        _write_sigs: bool = False
        _seen_sigs_files: set = set()
        try:
            from . import nfo as nfo_engine
            from .db import NameMapDb
            _pid = self.__class__.__name__
            self._name_map_db = getattr(self, "_name_map_db", None) or NameMapDb()
            data = data or {}
            roots = list(data.get("roots") or [])
            roots += [x.strip() for x in str(data.get("root_text") or "").splitlines() if x.strip()]
            if not roots:
                # 仪表盘触发（无 body）：回退到已选媒体库路径（v3.6.0: 库 Path 即根目录，无需手填）
                roots = self._all_nfo_roots()
            if not roots:
                self._push_log("ERROR", "NFO 扫描失败：未选择任何媒体库。请到设置页选择要处理的 Emby 媒体库（其目录将自动作为扫描根目录）")
                return
            recursive = bool(data.get("recursive", self._nfo_recursive))
            include_episodes = bool(data.get("include_episodes", self._nfo_include_episodes))
            do_dry = bool(data.get("dry_run", self._nfo_dry_run))
            preview = bool(data.get("preview", self._nfo_preview))
            force = bool(data.get("force_translate"))
            translate_all_mode = bool(data.get("translate_all_mode"))
            write_files = bool(data.get("write_files", not preview))


            _sig = self._nfo_scan_sig(roots, recursive, include_episodes, ())
            _done: Dict[str, str] = {}
            if not force:
                _ncur = (getattr(self, "_scan_cursor", None) or {}).get("nfo") or {}
                if _ncur.get("sig") == _sig:
                    _dc = _ncur.get("done")
                    if isinstance(_dc, dict):
                        # 新格式：{路径: 处理时文件签名}（NFO-001）
                        _done = {str(k): str(v or "") for k, v in _dc.items()}
                    else:
                        # 旧格式（纯路径列表）：无签名可比，维持原「跳过」语义
                        _done = {str(p): "" for p in (_dc or []) if str(p)}
            _sigs_ok = (not force) and bool(_sig) and (getattr(self, "_nfo_sigs_cfg", "") == _sig)
            _sigs_old: Dict[str, str] = dict(getattr(self, "_nfo_file_sigs", None) or {}) if _sigs_ok else {}
            _sigs_new: Dict[str, str] = dict(_sigs_old)
            _skipped_unchanged = 0
            _skipped_nonvideo = 0   # 明确的非影视 NFO（音乐/图片等 sidecar，NFO-008）
            _write_sigs = bool(write_files) and not do_dry   # 仅真正写文件的运行才更新签名表
            _seen_sigs_files: set = set()                    # 本轮见到的全部文件（收尾裁剪已删除项）

            self._push_log("INFO", f"NFO 扫描开始：{self._roots_pretty(roots)}（共 {len(roots)} 个目录）{('，断点续扫已处理 ' + str(len(_done)) + ' 个文件') if _done else ''}")
            files_all = nfo_engine.find_nfo_files(roots, recursive=recursive,
                                                  include_episodes=include_episodes)
            tier1 = [f for f in files_all if nfo_engine.classify(f) in ("movie", "tvshow")]
            tier2 = [f for f in files_all if nfo_engine.classify(f) == "episode"] if include_episodes else []
            _scan_prog_total = len(tier1) + len(tier2)
            _scan_prog_done = 0
            try:
                self._scan_status["total"] = _scan_prog_total
                self._scan_status["done"] = 0
            except Exception:
                pass
            _seen_sigs_files = set(tier1) | set(tier2)
            episode_map: Dict[str, List[str]] = {}
            episode_targets: List[str] = []
            _sdir = getattr(self, "_sync_direction", "s2e")
            _need_ep_map = (_sdir in ("s2e", "e2s")) or bool(preview and not force and not translate_all_mode)
            for fp in (tier1 if _need_ep_map else []):
                if nfo_engine.classify(fp) != "tvshow":
                    continue
                base_dir = os.path.dirname(fp)
                eps = []
                for dirpath, _, files in os.walk(base_dir):
                    for fn in files:
                        if not fn.lower().endswith(".nfo"):
                            continue
                        if fn.lower().endswith((".bak", ".tmp", "~")):
                            continue
                        ep = os.path.join(dirpath, fn)
                        if ep == fp:
                            continue
                        _c = nfo_engine.classify(ep)
                        if _c in ("tvshow", "movie", "season"):
                            continue
                        if ep not in eps:
                            eps.append(ep)
                if eps:
                    episode_map[fp] = eps
                    episode_targets.extend(eps)

            # 采集（第 1、2 轮共用池）
            name_orig, role_orig = set(), set()
            file_terms: Dict[str, dict] = {}
            guest_limit = 0
            tt_collect: Optional[dict] = None if (preview and not force) else self._collect_trans_types()
            _collect_sw = (tt_collect or {}).get("collect", {})

            def _lm_for(fp: str) -> dict:
                return self._collect_trans_types(nfo_engine.classify(fp)).get("limits", {})

            def _doc_meta(doc):
                """从 nfo 文档提取作品名/年份（供按作品分批翻译的 LLM 上下文）。"""
                _t = _y = ""
                try:
                    if doc is not None and getattr(doc, "root", None) is not None:
                        _te = doc.root.find("title")
                        if _te is not None and _te.text:
                            _t = _te.text.strip()
                        _ye = doc.root.find("year")
                        if _ye is not None and _ye.text:
                            _y = _ye.text.strip()
                except Exception:
                    pass
                return _t, _y

            # 两排体检（仅提示，不改数据）：第一排缺中文名 / 第二排缺英文角色名（拆可补·补不了）
            # 另统计：第二排无原文角色名（NFO 未提供角色名）—— v4.6.112 起再按「该演员有没有
            # <tmdbid>」拆两支：有的可开「TMDB 角色回填」补出英文角色名（不是「无法翻译」），
            # 没有的才是真的补不了。此前一律写成「无法翻译」，误导用户。
            _hc = {"row1": set(), "row2_ok": set(), "row2_miss": set(),
                   "row2_norole": set(), "row2_norole_ok": set()}

            def _mark_health(_doc, _ns, _rs):
                for _n in (_ns or ()):
                    _nm2 = str(_n[0] or "").strip()
                    if _nm2 and not any('\u4e00' <= _c <= '\u9fff' for _c in _nm2):
                        _hc["row1"].add(_nm2)
                try:
                    for _ac in _doc.root.findall("actor"):
                        _re = _ac.find("role")
                        _rv = (_re.text or "").strip() if _re is not None and _re.text else ""
                        _ne = _ac.find("name")
                        _nv = (_ne.text or "").strip() if _ne is not None and _ne.text else ""
                        _ae = _ac.find("tmdbid")
                        _av = (_ae.text or "").strip() if _ae is not None and _ae.text else ""
                        if not _rv:
                            if _nv:
                                # 有演员 tmdbid → 「TMDB 角色回填」可补；无 → 真补不了
                                (_hc["row2_norole_ok"] if _av else _hc["row2_norole"]).add(_nv)
                            continue
                        if any("a" <= _c.lower() <= "z" for _c in _rv):
                            continue
                        (_hc["row2_ok"] if _av else _hc["row2_miss"]).add((_nv, _rv))
                except Exception:
                    pass

            for fp in tier1:
                doc = nfo_engine.parse_nfo(fp)
                if doc is None or getattr(doc, "unsupported", False):
                    continue
                ns, rs = doc.collect(translate_types=_collect_sw or None, guest_limit=0, limits=_lm_for(fp) or None)
                name_orig.update(n[0] for n in ns)
                role_orig.update(r[0] for r in rs)
                _mark_health(doc, ns, rs)
                _t, _y = _doc_meta(doc)
                file_terms[fp] = {"title": _t, "year": _y,
                                  "names": {n[0] for n in ns}, "roles": {r[0] for r in rs}}
            _collect_eps = list(tier2)
            if getattr(self, "_sync_direction", "s2e") == "e2s":
                for _ep in episode_targets:
                    if _ep not in _collect_eps:
                        _collect_eps.append(_ep)
            for fp in _collect_eps:
                doc = nfo_engine.parse_nfo(fp)
                if doc is None or getattr(doc, "unsupported", False):
                    continue
                ns, rs = doc.collect(translate_types=_collect_sw or None, guest_limit=guest_limit, limits=_lm_for(fp) or None)
                name_orig.update(n[0] for n in ns)
                role_orig.update(r[0] for r in rs)
                _mark_health(doc, ns, rs)
                _t, _y = _doc_meta(doc)
                if nfo_engine.classify(fp) == "episode":
                    try:
                        _sid, _sname, _ssn, _epn = self._nfo_episode_meta(fp)
                        if _sname:
                            _t = _sname
                    except Exception:
                        pass
                file_terms[fp] = {"title": _t, "year": _y,
                                  "names": {n[0] for n in ns}, "roles": {r[0] for r in rs}}

            # 两排体检结论（只在对应开关未开且确有问题时提示）
            _health_lines: List[str] = []
            try:
                _r1 = set(_hc["row1"])
                if _r1:
                    _known = (self._tx_existing_translations(names=list(_r1)) or {}).get("names") or {}
                    _r1_missing = {n for n in _r1 if not str(_known.get(n) or "").strip()}
                else:
                    _r1_missing = set()
                if _r1_missing and not bool(getattr(self, "_pool_tmdb_fill", True)):
                    _health_lines.append(f"🩺 第一排：{len(_r1_missing)} 个人名无中文（TMDB 人名补译已关，开启可自动补）")
                _r2_ok = len(_hc["row2_ok"])
                _r2_miss = len(_hc["row2_miss"])
                if (_r2_ok or _r2_miss) and not bool(getattr(self, "_pool_tmdb_credits", False)):
                    _health_lines.append(f"🩺 第二排：{_r2_ok + _r2_miss} 个角色缺英文名"
                                         f"（可补 {_r2_ok} / 无 tmdbid 补不了 {_r2_miss}；TMDB 角色回填已关）")
                _r2_norole = len(_hc["row2_norole"])
                _r2_norole_ok = len(_hc["row2_norole_ok"])
                _want_role = bool(getattr(self, "_translate_role", True) or getattr(self, "_translate_all", False))
                if (_r2_norole or _r2_norole_ok) and _want_role:
                    # v4.6.112：不再笼统写「无法翻译」—— 拆成「可补 / 无可补」并带上开关状态，
                    # 与上一行「角色缺英文名（可补 X / 无 tmdbid 补不了 Y）」同口径。
                    _fill_on = bool(getattr(self, "_pool_tmdb_credits", False))
                    _health_lines.append(
                        f"🩺 第二排：{_r2_norole + _r2_norole_ok} 个角色 NFO 未提供角色名"
                        f"（可补 {_r2_norole_ok} / 无 tmdbid 补不了 {_r2_norole}；"
                        f"TMDB 角色回填{'已开' if _fill_on else '已关'}）")
            except Exception as _e:
                logger.debug(f"[NFO] 两排体检统计失败（非致命）: {_e}")
            _health_txt = ("；" + "；".join(_health_lines)) if _health_lines else ""

            if preview and not force and not translate_all_mode:
                lib_records = 0
                for fp in tier1 + tier2:
                    if self._scan_stop:
                        break
                    if not self._pause_gate("scan"):
                        break
                    _scan_prog_done += 1
                    self._scan_status["done"] = _scan_prog_done
                    if not force and fp in _done and self._nfo_done_skip(fp, _done):
                        continue
                    doc = nfo_engine.parse_nfo(fp)
                    if doc is None:
                        continue
                    if getattr(doc, "unsupported", False):
                        # 非影视 NFO：预览也不入库；计入断点避免每轮重复解析（NFO-008）
                        _skipped_nonvideo += 1
                        _done[fp] = self._file_sig(fp)
                        continue
                    try:
                        if nfo_engine.classify(fp) == "episode":
                            _sid, _sname, _ssn, _epn = self._nfo_episode_meta(fp)
                        else:
                            _sid = _sname = ""
                            _ssn = _epn = None
                        lib_records += self._record_nfo_library(doc, {}, {},
                                                                series_id=_sid, series_name=_sname,
                                                                season_num=_ssn, episode_num=_epn,
                                                                pool_ingest=True)
                    except Exception as e:
                        logger.warning(f"[NFO] 预览入库失败（未计入断点，下次扫描重试）{fp}: {e}")
                    else:
                        _done[fp] = self._file_sig(fp)
                # 处理单集关时集未在 tier2，也把各集原文入库（供库页查看/编辑）
                if not include_episodes:
                    for _tv_fp, eps in episode_map.items():
                        for ep in eps:
                            if self._scan_stop:
                                break
                            if not self._pause_gate("scan"):
                                break
                            if ep in _done and self._nfo_done_skip(ep, _done):
                                continue
                            edoc = nfo_engine.parse_nfo(ep)
                            if edoc is None:
                                continue
                            try:
                                _sid, _sname, _ssn, _epn = self._nfo_episode_meta(ep)
                                lib_records += self._record_nfo_library(edoc, {}, {},
                                                                        series_id=_sid, series_name=_sname,
                                                                        season_num=_ssn, episode_num=_epn,
                                                                        pool_ingest=True)
                            except Exception as e:
                                logger.warning(f"[NFO] 预览入库集失败（未计入断点，下次扫描重试）{ep}: {e}")
                            else:
                                _done[ep] = self._file_sig(ep)
                self._push_log("INFO", f"预览模式（{self._roots_pretty(roots)}）：已采集入库 {lib_records} 条原文（不写文件；翻译由后台 worker 自动进行，落盘需手动「全部写回」）"
                                       f"{('；跳过非影视 ' + str(_skipped_nonvideo) + ' 个') if _skipped_nonvideo else ''}{_health_txt}")
                if getattr(self, "_notify_on_complete", False) and not do_dry:
                    try:
                        _roots_txt = "、".join(os.path.basename(r or "") or r for r in (roots or []))
                        _lines = [
                            f"📁 库：{_roots_txt or len(files_all)}",
                            f"📄 文件：{len(files_all)} 个（预览扫描）",
                            f"📥 入库原文：{lib_records} 条",
                            "👀 预览模式：只入库未翻译（去「库」页点「全部翻译」）",
                        ]
                        _lines.extend(_health_lines)
                        if getattr(self, "_scan_stop", False):
                            _lines.append("⏹️ 已手动终止（断点已保存，下次扫描续）")
                        self.post_message(mtype=NotificationType.Manual, title="✅ NFO 扫描完成",
                                          text="\n".join(_lines))
                    except Exception as _e:
                        logger.debug(f"[NFO] 预览完成通知发送失败（非致命）: {_e}")
                return


            fail = 0
            lib_records = 0
            skipped = 0
            for fp in tier1 + tier2:
                if self._scan_stop:
                    break
                if not self._pause_gate("scan"):
                    break
                _scan_prog_done += 1
                self._scan_status["done"] = _scan_prog_done
                if not force and fp in _done and self._nfo_done_skip(fp, _done):
                    skipped += 1
                    continue
                _fp_sig = self._file_sig(fp)
                if _sigs_ok and _fp_sig:
                    _old_sig = _sigs_old.get(fp) or ""
                    if _old_sig == _fp_sig:
                        _skipped_unchanged += 1
                        continue
                    if _old_sig and self._sig_legacy_same(_old_sig, _fp_sig):
                        # 旧版秒级签名与新格式等价 → 视为未变化，顺手升级签名表（NFO-003）
                        _sigs_new[fp] = _fp_sig
                        _skipped_unchanged += 1
                        continue
                doc = nfo_engine.parse_nfo(fp)
                if doc is None:
                    fail += 1
                    continue
                if getattr(doc, "unsupported", False):
                    # 非影视 NFO（音乐/图片等第三方 sidecar）：不入库、不翻译；
                    # 计入断点与签名表，避免每轮扫描重复解析（NFO-008）
                    _skipped_nonvideo += 1
                    _done[fp] = _fp_sig
                    if _write_sigs and _fp_sig:
                        _sigs_new[fp] = _fp_sig
                    continue
                _e2s_added = 0
                if _sdir == "e2s" and nfo_engine.classify(fp) == "tvshow" and fp in episode_map:
                    for ep in episode_map[fp]:
                        try:
                            edoc = nfo_engine.parse_nfo(ep)
                            if edoc is not None:
                                _e2s_added += doc.merge_actors_from(edoc)
                        except Exception as e:
                            logger.debug(f"[NFO] 集→剧合并失败 {ep}: {e}")
                    if _e2s_added:
                        logger.info(f"[NFO] 集→剧合并：{os.path.basename(os.path.dirname(fp))} 新增 {_e2s_added} 位集演员（已入库，待写回 worker 落盘）")
                # 采集入库（空映射 = 只记原文；译文由翻译 worker 写入 name_after/role_after）
                # NFO-002：只有「解析成功 + 必需 DB 写入成功」才计入断点；
                # 失败不入 done 且从签名表移除 → 下次扫描必然重试，不再出现「假成功」。
                _db_ok = True
                if not do_dry and (include_episodes or fp not in episode_targets):
                    try:
                        if nfo_engine.classify(fp) == "episode":
                            _sid, _sname, _ssn, _epn = self._nfo_episode_meta(fp)
                        else:
                            _sid = _sname = ""
                            _ssn = _epn = None
                        lib_records += self._record_nfo_library(doc, {}, {},
                                                                series_id=_sid, series_name=_sname,
                                                                season_num=_ssn, episode_num=_epn,
                                                                pool_ingest=True)
                    except Exception as e:
                        _db_ok = False
                        logger.warning(f"[NFO] 写库页记录失败（未计入断点，下次扫描重试）{fp}: {e}")
                if _sdir == "s2e" and fp in episode_map:
                    for ep in episode_map[fp]:
                        try:
                            edoc = nfo_engine.parse_nfo(ep)
                            if edoc is None:
                                fail += 1
                                _db_ok = False   # 集解析失败 → 父级不入断点，下次扫描重试
                                continue
                            if getattr(edoc, "unsupported", False):
                                continue   # 非影视 NFO：不是这一集，跳过且不影响父级（NFO-008）
                            if not do_dry:
                                sid, sname, ssn, epn = self._nfo_episode_meta(ep)
                                _rec_src = doc if bool(getattr(self, "_nfo_episode_overwrite", False)) else edoc
                                lib_records += self._record_nfo_library(_rec_src, {}, {},
                                                                       series_id=sid, series_name=sname,
                                                                       season_num=ssn, episode_num=epn,
                                                                       pool_ingest=True)
                        except Exception as e:
                            _db_ok = False
                            logger.warning(f"[NFO] 剧→集集记录失败（未计入断点，下次扫描重试）{ep}: {e}")
                if _db_ok:
                    _done[fp] = _fp_sig
                    if _write_sigs and _fp_sig:
                        _sigs_new[fp] = _fp_sig
                elif _write_sigs:
                    # 本次处理失败：签名表也忘记它，避免被「未变化」跳过而永远不重试
                    _sigs_new.pop(fp, None)
                if not self._scan_stop and len(_done) % 15 == 0:
                    self._save_nfo_cursor(_sig, _done)
            _auto_triggered = self._scan_ingest_trigger() == "auto_trigger"
            if _auto_triggered:
                self._tx_request_consume(source="library")
            else:
                self._tx_wake()
            _pending_stats = self._pending_stats()
            _pending_terms = _pending_stats["names"] + _pending_stats["roles"]
            _pending_how = ("已交常驻翻译 worker，翻完由写回 worker 自动落盘" if _auto_triggered
                            else "已入库待翻，未开启自动翻译（去「库」页点「全部翻译」或开基础设置开关）")
            _fail_hint = ""
            _ftn = len(getattr(self, "_failed_terms", None) or ())
            if _ftn:
                _fail_hint = f"；翻译失败词条 {_ftn} 个（含其文件已计入断点），可用仪表盘「翻译失败词条」重试补齐"
            self._push_log("INFO", f"NFO 扫描完成（只采集入库，不写 NFO）：入库 {lib_records} 条原文，"
                                   f"待翻 {_pending_stats['items']} 个条目 / {_pending_terms} 个词条（{_pending_how}）"
                                   f"（解析失败 {fail}，跳过已处理 {skipped} 个"
                                   f"{('，跳过未变化 ' + str(_skipped_unchanged) + ' 个') if _skipped_unchanged else ''}"
                                   f"{('，跳过非影视 ' + str(_skipped_nonvideo) + ' 个') if _skipped_nonvideo else ''}"
                                   f"{_fail_hint}）{_health_txt}")
            if not force and (skipped or _skipped_unchanged) and lib_records == 0:
                self._push_log("INFO", f"与上次一致：{skipped + _skipped_unchanged} 个文件均已处理过（其中未变化 {_skipped_unchanged} 个按签名跳过），无新增或变化，无需重复翻译")
            if not do_dry:
                try:
                    _db0 = getattr(self, "_people_db", None)
                    if _db0 is not None:
                        _gh = float(getattr(self, "_nfo_dead_grace_hours", 24) or 24)
                        _purged = _db0.purge_expired(plugin_id=_pid, grace_hours=_gh)
                        if _purged:
                            # v4.6.77：记录真删除后同步清掉对应失效事件（不留「待恢复」假象）
                            try:
                                self._cleanup_dirty_webhook_events()
                            except Exception:
                                pass
                            self._push_log("INFO", f"已清理 {_purged} 个超过宽限期未恢复的条目（判定为真删除）")
                except Exception:
                    pass
            _emby_sync_line = ""
            if not preview and not do_dry:
                _esr = self._pool_sync_all(ctx="全库扫描") if getattr(self, "_emby_name_sync", True) else {}
                if _esr and _esr.get("total"):
                    _emby_sync_line = (f"🔄 Emby 人名：改名 {_esr.get('renamed', 0)} · "
                                       f"已是译文 {_esr.get('skipped', 0)} · 未找到/失败 {_esr.get('failed', 0)}")
            if getattr(self, "_notify_on_complete", False) and not do_dry:
                try:
                    _roots_txt = "、".join(os.path.basename(r or "") or r for r in (roots or []))
                    _lines = [
                        f"📁 库：{_roots_txt or len(files_all)}",
                        f"📄 文件：{len(files_all)} 个　📥 入库原文：{lib_records} 条",
                        "🔎 只负责发现：翻译交后台 worker，落盘由写回 worker 统一完成",
                        f"❌ 失败：{fail}",
                    ]
                    if _pending_stats["items"] or _pending_terms:
                        _lines.append(f"🤖 待翻：{_pending_stats['items']} 个条目"
                                      f"（第一排 {_pending_stats['names']} 词条 · 第二排 {_pending_stats['roles']} 词条）{_pending_how}")
                    if _emby_sync_line:
                        _lines.append(_emby_sync_line)
                    _lines.extend(_health_lines)
                    if preview:
                        _lines.append("👀 预览模式：只翻译写入库未写文件（去「库」页点「全部写回」落盘）")
                    if getattr(self, "_scan_stop", False):
                        _lines.append("⏹️ 已手动终止（断点已保存，下次扫描续）")
                    if bool(getattr(self, "_lock_cast", False)):
                        _lines.append("🔒 Cast 已锁定（lockedfields=Cast）")
                    else:
                        _lines.append("🔓 Cast 未锁定（设置未开启）")
                    self.post_message(
                        mtype=NotificationType.Manual,
                        title="✅ NFO 扫描完成",
                        text="\n".join(_lines),
                    )
                except Exception as _e:
                    logger.debug(f"[NFO] 完成通知发送失败（非致命）: {_e}")
        except Exception as e:
            self._push_log("ERROR", f"[NFO] 同步失败: {e}")
            logger.error(f"[NFO] 同步失败: {e}")
            if _sig:
                try:
                    self._save_nfo_cursor(_sig, _done)
                except Exception:
                    pass
        finally:
            # 释放运行状态（线程内收尾，等待的请求方已先行返回）
            self._set_task_running("scan", False)
            self._tx_wake()
            self._scan_status["running"] = False
            self._scan_status["paused"] = False
            self._scan_status["current_title"] = ""
            self._scan_status["total"] = 0
            self._scan_status["done"] = 0
            try:
                if getattr(self, "_scan_stop", False) and _sig:
                    self._save_nfo_cursor(_sig, _done)
                else:
                    cur = getattr(self, "_scan_cursor", None)
                    if isinstance(cur, dict):
                        cur.pop("nfo", None)
                        self._scan_cursor = cur
                if _write_sigs:
                    try:
                        _sigs_final = {k: v for k, v in _sigs_new.items() if k in _seen_sigs_files}
                        if len(_sigs_final) > 50000:
                            _sigs_final = dict(list(_sigs_final.items())[-50000:])
                        self._nfo_file_sigs = _sigs_final
                        self._nfo_sigs_cfg = _sig
                        self._save_file_sigs()   # 独立文件，不塞进 state.json（断点会高频重写它）
                    except Exception:
                        pass
                # v4.6.111（LIB-020）：收尾 —— 负缓存落库（跨重启有效）+ 「查不到」汇总一行
                try:
                    self._tmdb_scan_flush()
                except Exception:
                    pass
                self._save_state()
            except Exception:
                pass

    def _roots_pretty(self, roots) -> str:
        """把根目录数组转成可读描述 —— 库名（实际地址）多行以「、」连接。

        优先取每个根对应的媒体库名；匹配不到时回退为路径本身。
        """
        try:
            labels = []
            for r in roots or []:
                _r = str(r or "")
                _nm = self._library_name_for_path(_r)
                labels.append(f"{_nm}（{_r}）" if _nm else _r)
            return "、".join(x for x in labels if x) or "<空>"
        except Exception:
            return "、".join(str(r) for r in (roots or []))

    def _nfo_scan_sig(self, roots, recursive, include_episodes, ex_dirs) -> str:
        """NFO 扫描配置签名 —— 配置变化时旧断点作废。
        并入翻译开关 —— 「先只开演员、后加开角色」时改配置即全量重扫，新类型自然补译。
        缺陷 M —— 并入五类型开关 + 四数量上限，改开关/人数后断点作废触发补译。"""
        try:
            _ctt = self._collect_trans_types()
            _sw = _ctt.get("switches", {})
            _lm = _ctt.get("limits", {})
            _s = "|".join([
                ",".join(sorted(str(x) for x in (roots or []))),
                str(bool(recursive)), str(bool(include_episodes)),
                ",".join(sorted(str(x) for x in (ex_dirs or []))),
                str(int(getattr(self, "_max_guest_per_episode", 5) or 0)),
                str(bool(getattr(self, "_translate_role", True))),
                str(bool(getattr(self, "_translate_person", True))),
                str(bool(getattr(self, "_translate_all", False))),
                str(getattr(self, "_ja_name_policy", "convert") or "").strip(),
                str(bool(getattr(self, "_lock_cast", False))),
                str(bool(_sw.get("actor", True))), str(bool(_sw.get("guest", False))),
                str(bool(_sw.get("director", False))), str(bool(_sw.get("writer", False))),
                str(bool(_sw.get("producer", False))), str(bool(_sw.get("role", True))),
                str(int(_lm.get("actor", 0))), str(int(_lm.get("guest", 0))),
                str(int(_lm.get("director", 0))), str(int(_lm.get("writer", 0))),
                str(int(getattr(self, "_movie_actor_limit", 0) or 0)),
                str(int(getattr(self, "_movie_guest_limit", 0) or 0)),
                str(int(getattr(self, "_movie_director_limit", 0) or 0)),
                str(int(getattr(self, "_movie_writer_limit", 0) or 0)),
                str(int(getattr(self, "_tv_actor_limit", 0) or 0)),
                str(int(getattr(self, "_ep_actor_limit", 0) or 0)),
                str(int(getattr(self, "_tv_guest_limit", 0) or 0)),
                str(int(getattr(self, "_tv_director_limit", 0) or 0)),
                str(int(getattr(self, "_tv_writer_limit", 0) or 0)),
                str(getattr(self, "_sync_direction", "s2e") or "s2e"),
                str(bool(getattr(self, "_nfo_episode_overwrite", False))),
            ])
            return hashlib.md5(_s.encode("utf-8")).hexdigest()[:12]
        except Exception:
            return ""

    @staticmethod
    def _file_sig(path: str) -> str:
        """文件签名（mtime_ns|大小）—— 扫库轻量化跳过未变化文件的判据。
        NFO-003：秒级 mtime 在「同一秒内同长度重写」时无法分辨，改用纳秒。
        旧版秒级签名由 _sig_legacy_same 兼容（等价时顺手升级为新格式），
        不会因签名格式升级触发全库重扫。
        文件读不到（不存在/权限）返回空串（空串不参与跳过）。"""
        try:
            st = os.stat(str(path or ""))
            return f"{int(st.st_mtime_ns)}|{int(st.st_size)}"
        except Exception:
            return ""

    @staticmethod
    def _sig_legacy_same(old: str, cur: str) -> bool:
        """旧版秒级签名与新格式（纳秒|大小）是否代表同一状态（NFO-003 兼容层）。
        仅 old 是纯秒级、cur 是纳秒级时可能命中：大小一致且纳秒整除到秒后相等。"""
        try:
            _o, _os = str(old or "").split("|", 1)
            _c, _cs = str(cur or "").split("|", 1)
            return int(_os) == int(_cs) and int(_c) // 1000000000 == int(_o)
        except Exception:
            return False

    def _nfo_done_skip(self, fp: str, done: Dict[str, str]) -> bool:
        """断点命中判定（NFO-001）：done 记录「处理时的文件签名」，
        只有当前签名与记录一致（或记录为空 = 旧格式断点）才跳过；
        文件在断点保存后被改动 → 返回 False，重新解析入库。"""
        _rec = str(done.get(fp) or "")
        if not _rec:
            return True
        _cur = self._file_sig(fp)
        return (not _cur) or (_cur == _rec)

    def _nfo_resume_state(self) -> dict:
        """断点续跑状态 —— 是否存在「可续跑」的扫描断点。
        返回 {"ok": bool, "done": int}；仪表盘「续跑」按钮据此启用/灰置，/translate_all 据此兜底拒绝。

        断点只在「上轮被手动停止 / 异常中断」时保留（正常跑完会主动清除，见 _nfo_sync_worker finally）；
        配置签名变化后旧断点作废（不会再跳过已处理文件），因此同样视为「不可续跑」。
        """
        try:
            cur = (getattr(self, "_scan_cursor", None) or {}).get("nfo") or {}
            _dc = cur.get("done")
            _dn = len(_dc) if isinstance(_dc, (dict, list)) else 0
            if not _dn:
                return {"ok": False, "done": 0}
            try:
                _ex: tuple = ()
                _sig = self._nfo_scan_sig(self._all_nfo_roots(),
                                          bool(getattr(self, "_nfo_recursive", True)),
                                          bool(getattr(self, "_nfo_include_episodes", False)),
                                          _ex)
            except Exception:
                _sig = ""
            return {"ok": bool(_sig) and cur.get("sig") == _sig, "done": _dn}
        except Exception:
            return {"ok": False, "done": 0}

    def _save_nfo_cursor(self, sig: str, done: Dict[str, str]) -> None:
        """持久化 NFO 断点（上限 50000 文件，按真实处理顺序保留最近 N 条）。
        上限 5000→50000 —— 超大库超出部分原本每次续扫都要重新采集/翻译。
        done = {路径: 处理时文件签名}（NFO-001/004）：按处理顺序（dict 插入序）
        截断，而不是旧实现的 sorted 字典序 —— 保留的是真正最近处理的一批。"""
        try:
            cur = getattr(self, "_scan_cursor", None)
            if not isinstance(cur, dict):
                cur = {}
            _items = list(done.items())
            if len(_items) > 50000:
                logger.warning(f"[NFO] 断点已处理清单超 50000（共 {len(_items)}），仅保留最近 50000 条")
            cur["nfo"] = {"sig": sig, "done": dict(_items[-50000:])}
            self._scan_cursor = cur
            self._save_state()
        except Exception as e:
            logger.debug(f"保存 NFO 断点失败（非致命）: {e}")

    def _nfo_episode_meta(self, ep_path: str) -> tuple:
        """从单集 nfo 路径解析所属剧信息。
        向上找 tvshow.nfo → 读 tmdbid/title；文件名解析 SxxExx。
        :return: (series_id, series_name, season, episode)
        """
        from . import nfo as nfo_engine
        series_id = series_name = ""
        season = episode = None
        try:
            d = os.path.dirname(ep_path)
            # 向上最多 4 级找 tvshow.nfo
            for _ in range(4):
                if not d:
                    break
                t = os.path.join(d, "tvshow.nfo")
                if os.path.isfile(t):
                    tdoc = nfo_engine.parse_nfo(t)
                    if tdoc is not None and tdoc.root is not None:
                        _tm = tdoc.root.find("tmdbid")
                        if _tm is not None and _tm.text:
                            series_id = _tm.text.strip()
                        _t = tdoc.root.find("title")
                        if _t is not None and _t.text:
                            series_name = _t.text.strip()
                    break
                d = os.path.dirname(d)
            # 文件名解析 SxxExx（兼容 S01E01 / 1x01 等）
            fn = os.path.basename(ep_path).lower()
            m = re.search(r"s(\d{1,2})e(\d{1,3})", fn)
            if m:
                season = int(m.group(1))
                episode = int(m.group(2))
            elif re.search(r"(\d{1,2})x(\d{1,3})", fn):
                m2 = re.search(r"(\d{1,2})x(\d{1,3})", fn)
                season = int(m2.group(1))
                episode = int(m2.group(2))
        except Exception:
            pass
        return series_id, series_name, season, episode

    @staticmethod
    def _item_id_from_dir_name(path: str) -> str:
        """从 nfo 所在目录名解析合并 ID（{tmdb=302051} / {tvdb=123} / {imdb=ttxxx}）。
        用于 nfo 内缺 tmdbid 时兜底，让不同下载站命名不同的同一部剧仍能并成一部。
        tmdb 直接作为 item_id；tvdb/imdb 加前缀区分，避免不同类型 id 串味。"""
        try:
            _dir = os.path.basename(str(path or "").replace("\\", "/").rstrip("/"))
            _m = re.search(r"\{tmdb[=\s:]*(\d+)\}", _dir, re.I)
            if not _m:
                _m = re.search(r"\(tmdb[=\s:]*(\d+)\)", _dir, re.I)
            if _m:
                return _m.group(1)
            _m = re.search(r"\{tvdb[=\s:]*(\d+)\}", _dir, re.I)
            if _m:
                return "tvdb:" + _m.group(1)
            _m = re.search(r"\{imdb[=\s:]*([tT]{2}\d+)\}", _dir, re.I)
            if _m:
                return "imdb:" + _m.group(1).lower()
        except Exception:
            pass
        return ""

    @staticmethod
    def _nfo_file_fingerprint(path: str) -> str:
        """nfo 文件内容指纹（v4.6.72 · 洗版稳定身份辅助）——
        md5(文件字节)[:16]，文件缺失/读取失败返回 ""。仅作辅助参考，稳定恢复以 provider 为准。"""
        try:
            _p = str(path or "")
            if not _p or not os.path.isfile(_p):
                return ""
            with open(_p, "rb") as _f:
                _b = _f.read(262144)
            return hashlib.md5(_b).hexdigest()[:16]
        except Exception:
            return ""

    def _record_nfo_library(self, doc, person_map: dict, role_map: dict,
                            series_id: str = "", series_name: str = "",
                            season_num: int = None, episode_num: int = None,
                            pool_ingest: bool = False,
                            server_id: str = "", emby_item_id: str = "") -> int:
        """把单个 NFO 文件的演职人员写入 PeopleDb（库页数据源）。

        集（episode）记录复用剧的 item_id（剧 tmdbid），用 season/episode 区分层级，
        这样 `/db/people?item_id=剧` 一次查出剧+各集，库页按层级分组展示。

        v4.6.44 —— 库页「文件里有什么就全量入库」：本函数不再按采集开关 / 人数上限裁剪
        PeopleDb 写入；类型开关与人数上限只约束【翻译阶段】（见 _translate_pending_round）。
        pool_ingest=True（扫描 / Webhook / 探测库等所有入库路径）时，另按「翻译类型开关 +
        人数上限」把对应类型的人名写入【人名池】(NameMapDb，无 emby_person_id 的缓存行，待翻译)。
        v4.6.66（P0-1/P0-2）—— **来源与身份必须显式传入**：
          server_id     真实 Emby 服务器标识（Webhook/Series 展开全链路传递；扫描路径可为 ""）
          emby_item_id  Emby ItemId（Webhook 事件 ID），与媒体 item_id（tmdb/tvdb/nfo:hash）
                        分开保存，禁止混用（此前本函数把 server_id 写死为 ""，导致
                        Webhook 入库记录在按服务器查询的库页里整批找不到）。
        :return: 写入行数
        """
        if doc is None or getattr(doc, "root", None) is None:
            return 0
        # 标题
        title = ""
        _t = doc.root.find("title")
        if _t is not None and _t.text:
            title = _t.text.strip()
        if not title:
            title = os.path.splitext(doc.filename)[0]
        # item_id：优先 nfo tmdbid → v3.4.52 目录名 {tmdb=}/{tvdb=}/{imdb=} 兜底 → 路径哈希
        # 用途：不同下载站命名不同导致同一部剧拆成多个目录，只要目录名/nfo 带同一 id 就并成一部
        item_id = ""
        _tm = doc.root.find("tmdbid")
        if _tm is not None and _tm.text:
            item_id = _tm.text.strip()
        if not item_id:
            item_id = self._item_id_from_dir_name(doc.path)
        if not item_id:
            item_id = "nfo:" + hashlib.md5(doc.path.encode("utf-8")).hexdigest()[:16]
        # 类型映射：movie/tvshow/episode → Movie/Series/Episode
        _lv = (doc.level or "").lower()
        item_type = {"movie": "Movie", "tvshow": "Series", "episode": "Episode"}.get(_lv, "Movie")
        if item_type == "Episode" and series_id:
            item_id = series_id
        # v4.6.72（批次3）：稳定媒体身份 —— provider/id 显式落列；集记录记剧级 series_media_id。
        _mp, _mid = split_media_id(item_id)
        _smi = item_id if item_type in ("Series", "Episode") else ""
        # 组装 people：actor（name+role）与简单标签（director/writer/credits/producer）
        # 库页 = 全量入库（不受类型/人数约束）；人名池 = 按「翻译类型开关 + 人数上限」收词。
        _ct = self._collect_trans_types(_lv)
        _tr = _ct.get("translate", {})
        _pool_on = bool(pool_ingest) and bool(_tr.get("person", True))
        _pool_entries = []
        _credits_map = {}
        # v4.6.67（P0-D）：TMDB 第二排角色补译改用「有效角色开关」（= 全部类型 OR 角色总开关）
        # —— _tr['role'] 即 _collect_trans_types 计算出的有效值。此前用原始 _translate_role：
        # 用户开「全部类型」但历史 _translate_role=false 时，翻译会翻角色、这里却不补角色。
        if getattr(self, "_pool_tmdb_credits", False) and bool(_tr.get("role", True)):
            # v4.6.103（TMDB-4）：单集记录若拿不到剧级 id，**不得**退回用单集 id 当剧 id 去查
            # get_tv_credits —— 单集 nfo 的 <tmdbid> 是「集」的 ID，用它请求 /tv/{id}/credits
            # 必然 404，正是用户日志里刷屏的 "The resource you requested could not be found."
            # （每个单集文件 1 条）。此路径直接放弃补角色，不再发无效请求。
            if item_type == "Episode" and not series_id:
                _credits_map = {}
            else:
                _cid = series_id if item_type == "Episode" else item_id
                _cty = "Series" if item_type in ("Episode", "Series") else "Movie"
                # v4.6.110：把「哪个条目 / 哪个 NFO」带进日志 —— 宿主那条 404 只有一句
                # "The resource you requested could not be found."，看不出是谁在打；
                # 有了这个 hint 就能直接定位到具体条目与文件（排查 NFO 里的假 tmdbid）。
                _credits_map = self._tmdb_credits_role_map(
                    _cid, _cty, hint=f"条目={title or os.path.basename(doc.path)}"
                                     f"｜文件={os.path.basename(doc.path)}")
        people = []
        for actor in doc.root.findall("actor"):
            _n = actor.find("name")
            _r = actor.find("role")
            _ty = actor.find("type")
            n = (_n.text or "").strip() if _n is not None and _n.text else ""
            r = (_r.text or "").strip() if _r is not None and _r.text else ""
            a_type = (_ty.text or "").strip() if _ty is not None and _ty.text else "Actor"
            _is_guest = a_type.lower() not in ("actor", "voiceactor", "star")
            _kind = "guest" if _is_guest else "actor"
            # v4.6.108（LIB-016 · 入池门禁漏洞）：门禁必须按**这个人的真实职位**去查开关。
            # 此前一律用 _kind —— 只要不是演员类就算「客串」，于是 Emby 把导演/编剧/制片写成
            # `<actor><type>Director</type></actor>`（非常常见）时，**只要开着「客串」，
            # 导演/编剧/制片就会被一并收进人名池**，而落库的 person_type 仍是
            # Director/Writer/Producer → 池里显示「导演/编剧/制片」，翻译时又按类型开关
            # （这几个开关没开）被跳过、永远翻不掉（用户实测：只开「演员 + 客串」，
            # 池里却混进 制片/导演/编剧，并永久挂着「剩余 2 条」）。
            # 现在按真实职位取开关键（Actor→actor / Director→director / Producer→producer …），
            # 只有职位未知时才退回原来的「演员类=actor / 其它=guest」兜底。
            _sw_key = self._tx_switch_key(a_type) or _kind
            if not n and not r:
                continue
            if _credits_map and (not r or not any("a" <= _c.lower() <= "z" for _c in r)):
                _aid = actor.find("tmdbid")
                _apid = (_aid.text or "").strip() if _aid is not None and _aid.text else ""
                _cr = _credits_map.get(_apid, "") if _apid else ""
                if _cr:
                    r = _cr
            people.append({
                "Type": a_type,
                "before_name": n,
                "Name": person_map.get(n, n),
                "before_role": r,
                "Role": role_map.get(r, r),
            })
            # 入池只受「类型开关 + 第一排总开关」约束（v4.6.48）——
            # 「翻译人数上限」是「翻译阶段每文件前 N 个」的量，不决定「收不收进池」；
            # 上限填 0 只是不翻该类型，不应导致扫描后池空（用户实测困惑点）。
            if _pool_on and n and bool(_tr.get(_sw_key)):
                _pool_entries.append({"original": n, "zh": person_map.get(n, ""),
                                      "person_type": a_type, "source": "scan"})
        simple_type = {"director": "Director", "writer": "Writer", "credits": "Producer", "producer": "Producer"}
        # 人名池的类型开关：director/writer 各自独立；credits/producer 归入 producer 开关
        # （沿用 producer 翻译开关）。人数上限不参与入池判定（v4.6.48）。
        _simple_pool = {"director": "director", "writer": "writer",
                        "credits": "producer", "producer": "producer"}
        for tag in ("director", "writer", "credits", "producer"):
            _sw_key = _simple_pool[tag]
            for el in doc.root.findall(tag):
                t = (el.text or "").strip() if el.text else ""
                if not t:
                    continue
                people.append({
                    "Type": simple_type.get(tag, "Actor"),
                    "before_name": t,
                    "Name": person_map.get(t, t),
                    "before_role": "",
                    "Role": "",
                })
                if _pool_on and bool(_tr.get(_sw_key)):
                    _pool_entries.append({"original": t, "zh": person_map.get(t, ""),
                                          "person_type": simple_type.get(tag, "Actor"),
                                          "source": "scan"})
        # v4.6.96：同一人同时写在多个 credit 标签（如 <writer> + <credits>）→ 采集去重，
        # 避免库里同一人「原文名 + 角色」完全相同的重复行（与 Emby 按人物展示一致）。
        people = self._dedup_credit_people(people)
        if not people:
            return 0
        lib_name = self._library_name_for_path(doc.path)
        dbm = getattr(self, "_people_db", None) or PeopleDb()
        _pid = self.__class__.__name__
        if item_id and not str(item_id).startswith("nfo:") and not str(item_id).startswith("imdb:"):
            try:
                _old = dbm.item_id_by_nfo_path(plugin_id=_pid, nfo_path=doc.path)
                _osc = str(_old or "")
                if _old and _old != item_id and (_osc.startswith("nfo:") or _osc.isdigit()):
                    _n = dbm.migrate_item_id(plugin_id=_pid, old=_old, new=item_id)
                    if _n:
                        logger.info(f"[NFO] 合并重复条目 {_old} -> {item_id}（{os.path.basename(doc.path)}，{_n} 行）")
                        self._push_log("INFO", f"已合并重复条目：{os.path.basename(doc.path)}（{_n} 条记录并入 {item_id}）")
            except Exception:
                pass
        # 人名池入库（v4.6.44）：扫描/Webhook/探测库等入库路径按「翻译类型开关 + 人数上限」
        # 把对应类型人名写入人名池（无 emby_person_id 缓存行，待翻译；翻译阶段再翻、写回阶段再同步）。
        if _pool_on and _pool_entries:
            try:
                _nmm = getattr(self, "_name_map_db", None) or NameMapDb()
                self._name_map_db = _nmm
                _nmm.add_pool_candidates(plugin_id=_pid, entries=_pool_entries)
            except Exception as _e:
                logger.debug(f"[NFO] 写入人名池失败（非致命）: {_e}")
        # v4.6.88：扫描路径没有服务器上下文（调用方未传 server_id → 落库为 ""），而 Webhook 路径
        # 带真实 server_id；两者按 server_id 隔离 → 「先 Webhook 入库、后扫描」同一文件会出现
        # 两份记录（实测 6 行 / 库页 2 个条目）。这里在 server_id 为空时复用该文件已登记的
        # **唯一**真实来源 → upsert 命中同一组（覆盖而非新增），已有重复也会被顺带收编。
        _sid_final = str(server_id or "")
        if not _sid_final:
            try:
                _sid_final = dbm.server_id_by_nfo_path(plugin_id=_pid, nfo_path=doc.path) or ""
            except Exception:
                _sid_final = ""
        return dbm.upsert_people(
            plugin_id=_pid,
            server_id=_sid_final,
            item_id=item_id,
            item_type=item_type,
            title=title,
            series_name=series_name or "",
            season_num=season_num,
            episode_num=episode_num,
            library_name=lib_name,
            people=people,
            nfo_path=doc.path,
            emby_item_id=str(emby_item_id or ""),
            media_provider=_mp,
            media_id=_mid,
            series_media_id=_smi,
            file_fingerprint=self._nfo_file_fingerprint(doc.path),
        )

    # [LEGACY/manual compatibility — v5 收口 P0-2] 单文件「翻译 + 落盘」流水线。
    # 已从 Webhook / 探测库 / 整剧展开等所有自动路径移除调用；自动翻译改走常驻翻译
    # worker，自动落盘改走写回 worker 的落盘入口。保留仅供人工重新翻译等兼容场景，
    # 禁止在后台自动链路重新接线（否则会重新引入第二套翻译/写回链路）。
    def _translate_nfo_by_path(self, nfo_path: str, preview: Optional[bool] = None) -> dict:
        """单 NFO 文件完整翻译流水线（重新翻译 / Webhook 本地模式共用）。
        采集 → 按当前设置翻译（池优先→繁转简→LLM）→ apply → 原子写回文件 → 记录库+人名池。
        preview 参数 —— True=预览模式只更新库记录不写文件；None=跟随设置 _nfo_preview；
        返回增加 zhconv_count（繁体转简体条数）、preview。
        不再直接调 LLM（统一通道）—— 译文来源：人名池命中 → 库中已有译文 → 繁转简；
        剩余词条留在 DB，由常驻翻译 worker 翻译、写回 worker 落盘（返回 pending_left 供通知/事件展示）。
        :return: {changed, llm_calls, saved, records, zhconv_count, preview, pending_left, error}
        """
        from . import nfo as nfo_engine
        if preview is None:
            preview = bool(getattr(self, "_nfo_preview", False))
        res = {"changed": 0, "llm_calls": 0, "saved": False, "records": 0,
               "zhconv_count": 0, "pool_hit": 0, "preview": preview, "pending_left": 0, "error": ""}
        nfo_path = str(nfo_path or "").strip()
        if not nfo_path or not os.path.isfile(nfo_path):
            res["error"] = "nfo 文件不存在（目录可能已被删除或正在洗版观察期，恢复后重试）"
            return res
        doc = nfo_engine.parse_nfo(nfo_path)
        if doc is None:
            res["error"] = f"nfo 文件解析失败: {nfo_path}"
            return res
        _pid = self.__class__.__name__
        name_orig, role_orig = set(), set()
        gl = 0
        _ctt = self._collect_trans_types(nfo_engine.classify(nfo_path))
        ns, rs = doc.collect(translate_types=self._trans_types_for_collect(nfo_engine.classify(nfo_path)) or None,
                             guest_limit=gl if nfo_engine.classify(nfo_path) == "episode" else 0,
                             limits=_ctt.get("limits", {}) or None)
        name_orig.update(n[0] for n in ns)
        role_orig.update(r[0] for r in rs)
        if not name_orig and not role_orig:
            return res
        overwrite = bool(getattr(self, "_overwrite_chinese", False))
        dbm = getattr(self, "_name_map_db", None) or NameMapDb()
        _pool = dbm.load_map(plugin_id=_pid)
        _fresh = []
        llm_calls = 0
        zhconv_count = 0
        pool_hit = 0
        only_roles = bool(getattr(self, "_translate_role", True) or getattr(self, "_translate_all", False))
        _db_trans = self._tx_existing_translations(name_orig, role_orig)
        _db_names = (_db_trans or {}).get("names") or {}
        _db_roles = (_db_trans or {}).get("roles") or {}

        def _translate_set(terms, is_role):
            """不调 LLM —— 人名池命中 → 库中已有译文 → 繁转简。"""
            nonlocal zhconv_count, pool_hit
            out = {}
            _t = "role" if is_role else "person"
            _dbm = _db_roles if is_role else _db_names
            for t in sorted(terms):
                t = (t or "").strip()
                if not t:
                    continue
                hit = _pool.get((_t, t))
                if hit and hit[0]:
                    out[t] = hit[0]; self._pool_hits += 1; pool_hit += 1; continue
                _dbt = _dbm.get(t)
                if _dbt and _dbt != t:
                    out[t] = _dbt
                    continue
                if not overwrite and (self._looks_like_japanese(t) and self._ja_name_policy == 'keep'):
                    continue
                if not overwrite and self._ja_name_policy != 'translate' \
                        and not self._looks_like_japanese(t) and self._looks_like_chinese(t):
                    # 繁转简（v3.6.3/v3.6.5: 排除含假名的日文名，如 楠木ともり —— 三处流水线对齐）
                    z = self._zhconv_convert(t)
                    if z and z != t:
                        out[t] = z
                        zhconv_count += 1
                        _fresh.append({"type": _t, "original": t, "zh": z, "source": "zhconv"})
                        self._pool_hits += 1
                    continue
            return out

        person_pairs, role_pairs = [], []
        if name_orig:
            nm = _translate_set(name_orig, False)
            person_pairs = [(k, v) for k, v in nm.items()]
        if role_orig and only_roles:
            rm = _translate_set(role_orig, True)
            role_pairs = [(k, self._normalize_role_zh(k, v)) for k, v in rm.items()]
        person_map = nfo_engine.build_map_from_source(person_pairs)
        role_map = nfo_engine.build_map_from_source(role_pairs)
        _sid = _sname = ""
        _ssn = _epn = None
        if nfo_engine.classify(nfo_path) == "episode":
            try:
                _sid, _sname, _ssn, _epn = self._nfo_episode_meta(nfo_path)
            except Exception:
                pass
        if preview:
            records = self._record_nfo_library(doc, person_map, role_map,
                                               series_id=_sid, series_name=_sname,
                                               season_num=_ssn, episode_num=_epn,
                                               pool_ingest=True)
            changed = doc.apply(person_map, role_map)
            saved = False
        else:
            changed = doc.apply(person_map, role_map)
            saved = doc.save(backup=getattr(self, "_nfo_backup", False), dry_run=False,
                             lock_cast=bool(getattr(self, "_lock_cast", False)))
            if not saved:
                _se = ""
                try:
                    _se = str(getattr(nfo_engine, "get_last_save_error", lambda: "")() or "")
                except Exception:
                    _se = ""
                res["error"] = f"nfo 写回失败（文件被 Emby 占用/权限/只读）: {_se[:120] or '未知原因'}"
                logger.error(f"[NFO] 写回失败 {nfo_path}: {_se or '未知原因'}")
                self._push_log("ERROR", f"nfo 写回失败：{os.path.basename(nfo_path)}（{_se[:80] or '未知原因'}）")
            if saved:
                records = self._record_nfo_library(doc, person_map, role_map,
                                                   series_id=_sid, series_name=_sname,
                                                   season_num=_ssn, episode_num=_epn,
                                                   pool_ingest=True)
        if _fresh and dbm:
            try:
                dbm.set_map_many(plugin_id=_pid, entries=_fresh)
            except Exception:
                pass
        _pending_left = (sum(1 for _t0 in name_orig if str(_t0).strip() not in person_map)
                         + sum(1 for _t0 in role_orig if str(_t0).strip() not in role_map))
        if _pending_left:
            self._tx_wake()
        res.update({"changed": changed, "llm_calls": llm_calls, "saved": saved,
                    "records": records, "zhconv_count": zhconv_count, "pool_hit": pool_hit,
                    "pending_left": _pending_left})
        return res

    def _nfo_ingest_trigger(self) -> str:
        """Webhook/NFO 入库后的翻译触发语义（文档 §三）。
        默认 enqueue_only（只入队等人工触发）；仅当设置页开启「Webhook 自动翻译」才 auto_trigger。
        与 pool_auto_translate（人名池拉取后自动翻译）是两个不同概念（文档 §三 D）。
        v4.6.61（P1-SET-04）：AI 总开关关闭时按 off 处理（后端兜底，不依赖前端置灰）。"""
        return ("auto_trigger"
                if (bool(getattr(self, "_auto_translate_webhook", False)) and self._ai_enabled())
                else "enqueue_only")

    def _scan_ingest_trigger(self) -> str:
        """NFO 扫描 / 探测库入库后的翻译触发语义。
        默认 enqueue_only（只入库等人工触发）；仅当设置页开启「扫描/探测库入库后自动翻译」才 auto_trigger。
        与 _nfo_ingest_trigger（Webhook 入库）是两个独立开关。
        v4.6.61（P1-SET-04）：AI 总开关关闭时按 off 处理（后端兜底，不依赖前端置灰）。"""
        return ("auto_trigger"
                if (bool(getattr(self, "_auto_translate_scan", False)) and self._ai_enabled())
                else "enqueue_only")

    def _incoming_media_identity(self, doc, nfo_path: str, lv: str,
                                 item: Optional[dict] = None) -> tuple:
        """本次入库文件的**稳定媒体身份** (item_id, provider, media_id, series_media_id, title)。

        v4.6.72（批次3 · 洗版稳定身份）：与 _record_nfo_library 同一套推导 ——
        nfo tmdbid → 目录名 {tmdb=}/{tvdb=}/{imdb=} → nfo:hash 兜底；集记录取剧级 id
        （series_media_id）。用于洗版恢复判定与历史别名登记，洗版后只要 provider 未变即可识别。
        """
        _path = str(getattr(doc, "path", "") or nfo_path or "")
        _title = ""
        try:
            _t = doc.root.find("title")
            if _t is not None and (_t.text or "").strip():
                _title = _t.text.strip()
        except Exception:
            _title = ""
        if not _title:
            _title = os.path.splitext(str(getattr(doc, "filename", "") or ""))[0]
        _iid = ""
        try:
            _tm = doc.root.find("tmdbid")
            if _tm is not None and (_tm.text or "").strip():
                _iid = _tm.text.strip()
        except Exception:
            _iid = ""
        if not _iid:
            _iid = self._item_id_from_dir_name(_path)
        _smi = ""
        if str(lv or "").lower() == "episode":
            try:
                _sid, _sn2, _ss2, _ep2 = self._nfo_episode_meta(nfo_path)
                if _sid:
                    _iid = str(_sid)
                    _smi = str(_sid)
            except Exception:
                pass
        if not _iid:
            _iid = "nfo:" + hashlib.md5(_path.encode("utf-8")).hexdigest()[:16]
        if not _smi and str(lv or "").lower() == "tvshow":
            _smi = _iid
        _mp, _mid = split_media_id(_iid)
        return _iid, _mp, _mid, _smi, _title

    def _media_identity_from_path(self, nfo_path: str, lv: str = "") -> tuple:
        """按路径推导稳定媒体身份（整剧展开等无 doc 场景）—— 解析 nfo 取 tmdbid，失败按路径兜底。"""
        try:
            from . import nfo as nfo_engine
            _doc = nfo_engine.parse_nfo(nfo_path)
            if _doc is not None:
                return self._incoming_media_identity(_doc, nfo_path, lv, None)
        except Exception:
            pass
        _lv = str(lv or "").lower()
        _iid = ""
        if _lv == "episode":
            try:
                _sid, _sn, _ss, _ep = self._nfo_episode_meta(nfo_path)
                if _sid:
                    _iid = str(_sid)
            except Exception:
                pass
        if not _iid:
            _iid = self._item_id_from_dir_name(nfo_path)
        if not _iid:
            _iid = "nfo:" + hashlib.md5(str(nfo_path).encode("utf-8")).hexdigest()[:16]
        _p, _m = split_media_id(_iid)
        _smi = _iid if _lv in ("episode", "tvshow") else ""
        return _iid, _p, _m, _smi, ""

    def _ingest_tx_phrase(self, trigger: str = "", pending: int = 0) -> str:
        """入库链路的「待翻词条是否已交后台翻译」短语（v4.6.78）——

        必须按**真实触发**说：未开「Webhook / 扫描·探测库 入库后自动翻译」时，
        此前静态写「已交后台翻译 worker」会误导用户（实测反馈：没开自动翻译却提示已安排）。
        auto_trigger → 已交（自动）；manual_trigger → 已交（本次手动）；否则 → 未自动翻译 + 手动入口。
        pending<=0 时统一返回「无待翻词条」。
        """
        _n = int(pending or 0)
        if _n <= 0:
            return "无待翻词条"
        _t = str(trigger or "").strip().lower()
        if _t not in ("auto_trigger", "manual_trigger", "enqueue_only"):
            try:
                _t = str(self._nfo_ingest_trigger())
            except Exception:
                _t = "enqueue_only"
        if _t == "auto_trigger":
            return f"待翻 {_n} 个词条已交后台翻译 worker（自动）"
        if _t == "manual_trigger":
            return f"待翻 {_n} 个词条已交后台翻译 worker（本次手动触发）"
        return (f"待翻 {_n} 个词条未自动翻译"
                f"（设置页「入库后自动翻译」未开启，可在库页点「全部翻译」手动触发）")

    def _ingest_nfo_pending(self, nfo_path: str, item_id: str = "", server_id: str = "",
                            item: Optional[dict] = None,
                            recovered: Optional[bool] = None,
                            trigger: str = "enqueue_only") -> dict:
        """单 NFO 只做「解析 → 入库(pending)」，不翻译、不 apply、不写盘。
        译文由常驻翻译 worker 统一消费，写回 worker 唯一落盘（清单 §三/§七）。
        Webhook / 探测库 / 其他自动入库路径统一走这里，禁止再出现「Webhook → LLM → doc.save」。
        用可读的 trigger 语义替代含义不明的 grant（文档 §三 C）：
          - enqueue_only （默认）: 只入库，不开翻译消费许可（Webhook/扫描/探测默认行为）
          - manual_trigger        : 用户明确触发本次翻译 —— 授予消费许可
          - auto_trigger          : 「Webhook 自动翻译」开启时 —— 授予消费许可
        注：旧签名 grant=True 已弃用，新代码一律用 trigger。
        :return: {ok, records, names, roles, recovered, error, nfo_path}
        """
        from . import nfo as nfo_engine
        res = {"ok": False, "records": 0, "names": 0, "roles": 0,
               "recovered": 0, "error": "", "nfo_path": nfo_path}
        nfo_path = str(nfo_path or "").strip()
        if not nfo_path or not os.path.isfile(nfo_path):
            res["error"] = "nfo 文件不存在（目录可能已被删除或正在洗版观察期，恢复后重试）"
            return res
        doc = nfo_engine.parse_nfo(nfo_path)
        if doc is None:
            res["error"] = f"nfo 文件解析失败: {nfo_path}"
            return res
        _pid = self.__class__.__name__
        _lv = nfo_engine.classify(nfo_path)
        _it = item or {}
        _sname = str(_it.get("SeriesName") or "")
        _ssn = _it.get("ParentIndexNumber")
        _epn = _it.get("IndexNumber")
        if _lv == "episode" and not _sname:
            try:
                _x, _sname, _ssn, _epn = self._nfo_episode_meta(nfo_path)
            except Exception:
                pass
        # v4.6.72（批次3）：先算本次入库的稳定媒体身份（供洗版恢复判定 + 历史别名登记）。
        _in_iid, _in_mp, _in_mid, _in_smi, _in_title = self._incoming_media_identity(
            doc, nfo_path, _lv, _it)
        _sid_arg = str(server_id or "") or None
        _emby_in = str(_it.get("Id") or "")
        # 删除→恢复识别（必须在入库 upsert 之前 —— upsert 会清空 deleted_at）
        # v4.6.100（恢复越界修复）：稳定媒体身份（item_id / provider / series_media_id）在
        # **不给季集**时会退化成「匹配该剧全部观察期行」。剧级 tvshow.nfo 没有季集上下文，
        # 若照旧参与身份清扫，会把整剧（含**仍然缺失**的其它集）的观察期一次性清掉 ——
        # 实测：删 2 集再放回 2 集时 recovered 只记成 1；只删 1 集后任何整剧入库都会误清该集。
        # 现在只有「明确的单集上下文」或「电影单条目」才做身份恢复清扫；
        # 剧级 tvshow.nfo 只认 nfo_path 精确命中（剧级行），逐集恢复交回各自的单集 NFO。
        _sweep_ok = (_lv == "movie") or (_lv == "episode" and (_ssn is not None or _epn is not None))
        if recovered is None:
            recovered = False
            try:
                _db = getattr(self, "_people_db", None)
                if _db is not None:
                    # 1) 强身份（provider / item_id / series_media_id / Emby ItemId）——
                    #    洗版后路径/标题/Emby ItemId 变化但 provider 未变仍能命中（§八~十）。
                    _strong = 0
                    if _sweep_ok:
                        try:
                            _strong = int(_db.is_deleted_by_media(
                                plugin_id=_pid, item_id=_in_iid, media_provider=_in_mp,
                                media_id=_in_mid, series_media_id=_in_smi, emby_item_id=_emby_in,
                                season_num=_ssn, episode_num=_epn, server_id=_sid_arg) or 0)
                        except Exception:
                            _strong = 0
                    if _strong > 0:
                        recovered = True
                    elif bool(_db.is_deleted_by_nfo_path(plugin_id=_pid, nfo_path=nfo_path,
                                                         server_id=_sid_arg)):
                        # 2) 兼容旧路径：nfo_path 精确命中（行级精确，不会越界到同剧其它集）
                        recovered = True
                    elif _sweep_ok:
                        # 3) 弱匹配（剧名 + 季集 / 标题）—— **仅候选唯一**才允许自动恢复
                        #    （报告第九节 · 候选冲突保护：绝不「找到一个像的就自动恢复」）。
                        _wc = int(_db.deleted_weak_candidates(
                            plugin_id=_pid, series_name=_sname, title=_in_title,
                            season_num=_ssn, episode_num=_epn, server_id=_sid_arg) or 0)
                        if _wc == 1:
                            recovered = True
                        elif _wc > 1:
                            logger.warning(f"[恢复] 弱匹配存在多个候选（{_wc} 个），不自动恢复："
                                           f"{_sname or _in_title} S{_ssn}E{_epn}（{os.path.basename(nfo_path)}）")
                            self._push_log("WARN", f"存在多个候选，需人工确认："
                                                   f"{_sname or _in_title} S{_ssn}E{_epn}")
            except Exception:
                recovered = False
        if recovered:
            try:
                _db = getattr(self, "_people_db", None)
                if _db is not None:
                    # v4.6.100：身份清扫（含历史别名登记）只在 _sweep_ok 时进行 ——
                    # 剧级 tvshow.nfo 无季集上下文，绝不能按「整剧身份」清观察期。
                    if _sweep_ok:
                        # 登记洗版历史别名（旧身份 → 新身份）：供后续查询归一 / 日志排查。
                        try:
                            for _s in (_db.sample_deleted_identities(
                                    plugin_id=_pid, item_id=_in_iid, media_provider=_in_mp,
                                    media_id=_in_mid, series_media_id=_in_smi, emby_item_id=_emby_in,
                                    season_num=_ssn, episode_num=_epn, server_id=_sid_arg) or []):
                                _o_iid = str(_s.get("item_id") or "")
                                _o_eid = str(_s.get("emby_item_id") or "")
                                if _o_iid == _in_iid and _o_eid == _emby_in:
                                    continue
                                _db.alias_put(
                                    plugin_id=_pid, server_id=str(_s.get("server_id") or ""),
                                    provider=_in_mp, provider_id=_in_mid,
                                    old_media_id=_o_iid, old_emby_item_id=_o_eid,
                                    old_nfo_path=str(_s.get("nfo_path") or ""),
                                    old_title=str(_s.get("title") or ""), new_media_id=_in_iid)
                        except Exception:
                            pass
                        # 解除观察期（强身份 + nfo_path + 唯一候选弱匹配 —— 均带季集范围）
                        _db.clear_deleted_by_media(
                            plugin_id=_pid, item_id=_in_iid, media_provider=_in_mp, media_id=_in_mid,
                            series_media_id=_in_smi, emby_item_id=_emby_in,
                            season_num=_ssn, episode_num=_epn, server_id=_sid_arg)
                    # 行级精确解除（nfo_path 命中；剧级 NFO 只走这一条，不会越界到其它集）
                    _db.clear_deleted(plugin_id=_pid, nfo_path=nfo_path, series_name=_sname,
                                      season_num=_ssn, episode_num=_epn, server_id=_sid_arg)
            except Exception:
                pass
        # 采集词条（v4.4.7 P0-6/§二十二：采集与翻译开关解耦 —— 用 collect 表；仅按人数上限筛）
        try:
            _ctt = self._collect_trans_types(_lv)
            ns, rs = doc.collect(translate_types=_ctt.get("collect", {}) or None,
                                 guest_limit=0,
                                 limits=_ctt.get("limits", {}) or None)
            name_orig = {str(n[0]).strip() for n in ns if str(n[0]).strip()}
            role_orig = {str(r[0]).strip() for r in rs if str(r[0]).strip()}
        except Exception as _e:
            res["error"] = f"采集词条失败: {_e}"
            return res
        res["names"] = len(name_orig)
        res["roles"] = len(role_orig)
        if not name_orig and not role_orig:
            res["ok"] = True
            res["recovered"] = 1 if recovered else 0
            return res
        # 入库：person/role 以原文为 pending 占位（不写 NFO，不调 LLM）
        _sid = ""
        _ssn2 = _epn2 = None
        if _lv == "episode":
            try:
                _sid, _sname2, _ssn2, _epn2 = self._nfo_episode_meta(nfo_path)
                if not _sname:
                    _sname = _sname2
            except Exception:
                pass
        try:
            # v4.6.66（P0-1/P0-2）：真实 server_id + Emby ItemId 全链路写入 ——
            # server_id 从此不再写死为空（此前 Webhook 记录丢失来源，按服务器查库页找不到）。
            res["records"] = int(self._record_nfo_library(
                doc, {}, {}, series_id=_sid, series_name=_sname,
                season_num=_ssn2, episode_num=_epn2, pool_ingest=True,
                server_id=server_id,
                emby_item_id=str(_it.get("Id") or "")) or 0)
        except Exception as _e:
            res["error"] = f"入库记录失败: {_e}"
            logger.warning(f"[Webhook] 入库记录失败 {nfo_path}: {_e}")
            return res
        res["ok"] = True
        res["recovered"] = 1 if recovered else 0
        # v4.6.66（P0-6）：单集入库时确保「剧级行」存在 —— 库页隐藏「纯 Episode 组」，
        # 若 tvshow.nfo 未被单独入库（Emby 未就绪 / 路径映射差异），整部剧会从库页消失。
        if _lv == "episode" and _sid:
            try:
                _db2 = getattr(self, "_people_db", None)
                if _db2 is not None and not _db2.item_has_series_row(
                        plugin_id=self.__class__.__name__, item_id=_sid,
                        server_id=(server_id or None), exclude_deleted=True):
                    _tv = self._find_show_tvshow_nfo(nfo_path)
                    if _tv and os.path.isfile(_tv):
                        _tv_doc = nfo_engine.parse_nfo(_tv)
                        if _tv_doc is not None:
                            _n_tv = self._record_nfo_library(
                                _tv_doc, {}, {}, series_id=_sid, series_name=_sname,
                                season_num=None, episode_num=None, pool_ingest=True,
                                server_id=server_id,
                                emby_item_id=str(_it.get("SeriesId") or ""))
                            res["records"] = int(res["records"]) + int(_n_tv or 0)
                            logger.info(f"[Webhook] 已补写剧级记录（tvshow.nfo）：{os.path.basename(_tv)}"
                                        f"（{_n_tv} 条，防纯 Episode 组在库页被隐藏）")
            except Exception as _e:
                logger.debug(f"[Webhook] 补写剧级记录失败（非致命）: {_e}")
        res["media_item_id"] = str(_sid or "")
        res["server_id"] = str(server_id or "")
        # 唤醒常驻翻译 worker 消费 pending（翻译完成 → 写回 worker 自动落盘）
        try:
            _tw = str(trigger or "enqueue_only").strip().lower()
            if _tw in ("manual_trigger", "auto_trigger"):
                self._tx_request_consume(source="library")
            else:
                self._tx_wake()
        except Exception:
            pass
        return res

    def _ingest_scope_brief(self, pairs: list) -> dict:
        """入库通知口径（v4.6.66 · P1-1/P1-2）：按**当前翻译范围**统计这批条目的
        「当前范围待翻 / 已有译文」，与常驻 worker 收词同口径
        （目标范围 + 类型开关 + 人数上限 + 已是中文跳过）。
        不再把 NFO 全量采集词条直接叫「待翻」（此前 39 人名 + 30 角色 = 69 直接当待翻）。
        :param pairs: [(server_id, media_item_id), ...] 去重后的条目
        :return: {pending, pending_person, pending_role, translated, total}
        """
        _out = {"pending": 0, "pending_person": 0, "pending_role": 0, "translated": 0, "total": 0}
        _pid = self.__class__.__name__
        _seen: set = set()
        try:
            _db = getattr(self, "_people_db", None)
            for _sid, _iid in (pairs or []):
                _iid = str(_iid or "")
                _sk = (str(_sid or ""), _iid)
                if not _iid or _sk in _seen:
                    continue
                _seen.add(_sk)
                for _o in self._tx_occurrences(_pid, item_id=_iid, server_id=str(_sid or "")):
                    _t = str(_o.get("text") or "")
                    if not _t or self._skip_no_translate(_t):
                        continue
                    if _o.get("kind") == "role":
                        if self._tx_role_type_enabled(_o.get("person_type")):
                            _out["pending"] += 1
                            _out["pending_role"] += 1
                    else:
                        if self._tx_type_enabled(_o.get("person_type")):
                            _out["pending"] += 1
                            _out["pending_person"] += 1
            if _db is not None:
                _cnt = _db.item_translation_counts(plugin_id=_pid, pairs=list(_seen)) or {}
                for _c in _cnt.values():
                    _out["total"] += int(_c.get("total") or 0)
                    _out["translated"] += int(_c.get("translated") or 0)
        except Exception as _e:
            logger.debug(f"[Webhook] 入库口径统计失败（非致命）: {_e}")
        return _out

    def _ingest_nfo_batch(self, entries: list, trigger: str = "enqueue_only") -> dict:
        """批量「解析 NFO → 入库(pending)」，不翻译、不 apply、不写盘。
        entries: [(nfo_path, level, item_id, server_id, item)]
        返回结构与旧 _batch_translate_nfo_files 兼容（供 webhook 事件/通知复用），
        但 changed/llm_calls/zhconv/pool_new 恒 0（本层不再产生译文）。
        trigger 语义同 _ingest_nfo_pending（默认 enqueue_only，只入库不自动翻译）。
        v4.6.66：新增 brief（按当前翻译范围的待翻/已有译文）与身份字段（media_item_id/server_id），
        pending_left 改为 **brief.pending（当前范围口径）**，不再用采集词条数冒充待翻。
        """
        done = fail = records = recovered = 0
        names_total = roles_total = 0
        _pairs: list = []
        for nf, _lv, iid, sid, it in entries:
            if getattr(self, "_stop_requested", False) or not getattr(self, "_enabled", False):
                break
            try:
                r = self._ingest_nfo_pending(nf, item_id=iid, server_id=sid, item=it, trigger=trigger)
            except Exception as _e:
                fail += 1
                logger.warning(f"[Webhook] 入库异常 {nf}: {_e}")
                continue
            if r.get("ok"):
                done += 1
                records += int(r.get("records") or 0)
                recovered += int(r.get("recovered") or 0)
                names_total += int(r.get("names") or 0)
                roles_total += int(r.get("roles") or 0)
                if r.get("media_item_id"):
                    _pairs.append((str(r.get("server_id") or ""), str(r.get("media_item_id") or "")))
            else:
                fail += 1
                logger.warning(f"[Webhook] 入库失败 {nf}: {r.get('error')}")
        brief = self._ingest_scope_brief(_pairs) if _pairs else \
            {"pending": 0, "pending_person": 0, "pending_role": 0, "translated": 0, "total": 0}
        if names_total or roles_total:
            try:
                _tw = str(trigger or "enqueue_only").strip().lower()
                if _tw in ("manual_trigger", "auto_trigger"):
                    self._tx_request_consume(source="library")
                else:
                    self._tx_wake()
            except Exception:
                pass
        # v4.6.66（P1-4）：Webhook Job 身份日志 —— server_id / media_item_id / 采集 / 当前范围待翻 / 已有译文
        try:
            _id_txt = "、".join(f"{s or '(本地)'}:{i}" for s, i in list(_pairs)[:3])
            logger.info(f"[WebhookJob] event={trigger} nfo={done}（成功 {done}/失败 {fail}）"
                        f" identity=[{_id_txt or '-'}] records={records} recovered={recovered}"
                        f" collected=人名 {names_total}/角色 {roles_total}"
                        f" scoped_pending={brief.get('pending', 0)}"
                        f"（第一排 {brief.get('pending_person', 0)} / 第二排 {brief.get('pending_role', 0)}）"
                        f" translated={brief.get('translated', 0)}")
        except Exception:
            pass
        return {"done": done, "fail": fail, "changed": 0, "records": records,
                "llm_calls": 0, "zhconv": 0, "pool_new": 0, "pool_hit": 0,
                "recovered": recovered,
                # pending_left = 按当前翻译范围过滤后的真实待翻（不再用采集词条数冒充）
                "pending_left": int(brief.get("pending") or 0),
                "pending_person": int(brief.get("pending_person") or 0),
                "pending_role": int(brief.get("pending_role") or 0),
                "translated_existing": int(brief.get("translated") or 0),
                "records_total": int(brief.get("total") or 0),
                "names_count": names_total, "roles_count": roles_total,
                "brief": brief}

    def _find_show_tvshow_nfo(self, nfo_path: str) -> str:
        """从单集 nfo 向上找所属剧的 tvshow.nfo（最多 4 级）。
        与 _nfo_episode_meta 同口径，用于写回阶段的 s2e 分发（剧演员插入到集）。
        找不到返回空串。"""
        try:
            d = os.path.dirname(str(nfo_path or ""))
            for _ in range(4):
                if not d:
                    break
                t = os.path.join(d, "tvshow.nfo")
                if os.path.isfile(t):
                    return t
                nd = os.path.dirname(d)
                if nd == d:
                    break
                d = nd
        except Exception:
            pass
        return ""

    def _write_nfo_once(self, item_id: str, server_id: str, nfo_path: str,
                        people_records: Optional[list] = None, auto: bool = False) -> dict:
        """自动 / 手动写回的**唯一落盘入口**（清单 §七）。

        自动链路：_writeback_worker → _wb_process_item → _restore_item_to_nfo
                  → _write_nfo_once；手动链路：_api_db_restore / _writeback_all_worker
                  → _restore_item_to_nfo → _write_nfo_once。两条路径最终都只从这里落盘。

        本层职责：
        - 文件存在检查（缺失 → missing，交调用方标 missing，不算失败）
        - 获取最新 DB 译文（未显式传入时现取 people_of_item）
        - 重新 parse + apply + save（内部实现 _restore_nfo_from_db）
        - 每次落盘前重新读取磁盘最新内容再套用译文 → 避免覆盖外部改动

        顺序纪律：本函数返回 success 后调用方才允许标记 writeback_state=done；
        返回失败时调用方必须保留 pending/failed，绝不可先标 done 再 save。
        """
        try:
            nfo_path = str(nfo_path or "").strip()
            if not nfo_path or not os.path.isfile(nfo_path):
                # 文件已不存在（删除 / 洗版观察期）—— 交调用方标 missing，不空转重试
                return {"success": False,
                        "message": "该条目 nfo 文件已不存在（可能已删除或正在洗版观察期），无法写回",
                        "data": {"changed": 0, "saved": False, "missing": True, "nfo_path": nfo_path}}
            _pid = self.__class__.__name__
            if people_records is None:
                db = getattr(self, "_people_db", None)
                if db is None:
                    return {"success": False, "message": "翻译记录数据库未初始化"}
                people_records = db.people_of_item(plugin_id=_pid,
                                                   item_id=str(item_id or ""),
                                                   server_id=str(server_id or ""))
            if not people_records:
                return {"success": False, "message": "库中该条目无人物记录",
                        "data": {"skip": True}}
            # 落盘实现：内部重新 parse 磁盘内容 → 合并最新译文 → apply → save（含外部改动保护）
            return self._restore_nfo_from_db(item_id, nfo_path, people_records, auto=auto)
        except Exception as e:
            logger.error(f"[Writeback] 落盘失败 {nfo_path}: {e}\n{traceback.format_exc()}")
            return {"success": False, "message": str(e)}

    def _restore_nfo_from_db(self, item_id: str, nfo_path: str, people_records: list,
                             auto: bool = False) -> dict:
        """文件级锁包装（v4.6.73 · 报告第十二节）—— 同一 nfo 的
        「重新读取磁盘 → apply → 原子写回」全程串行，防止两个线程
        （写回 worker / 手动全部写回 / 单条写入）同时写同一文件互相覆盖。
        真正实现见 _restore_nfo_from_db_locked。"""
        from . import nfo as nfo_engine
        with nfo_engine.file_lock(nfo_path):
            return self._restore_nfo_from_db_locked(item_id, nfo_path, people_records, auto=auto)

    def _restore_nfo_from_db_locked(self, item_id: str, nfo_path: str, people_records: list,
                             auto: bool = False) -> dict:
        """把库中已翻译名单写回 nfo 文件（本地模式「写入 nfo」）。
        用库里的 name_before→name_after / role_before→role_after 构造映射，
        apply 覆盖 nfo 中对应文本，不调 LLM、不动人名池。
        本函数是唯一落盘入口 _write_nfo_once 的内部实现，
        不再被其它链路直接调用；调用方（_write_nfo_once）负责就绪/状态纪律。
        auto=True（自动写回 worker）—— apply 改动 0 条时直接返回成功且不落盘，
        文件 mtime 不变（幂等：已是译文不重复写，文档 §15）。
        """
        from . import nfo as nfo_engine
        try:
            if not os.path.isfile(nfo_path):
                return {"success": False,
                        "message": "该条目 nfo 目录已不存在（可能已删除或正在洗版观察期），无法写回；观察期内重新入库后将自动按媒体稳定身份恢复翻译名单",
                        "data": {"changed": 0, "saved": False, "missing": True, "nfo_path": nfo_path}}
            doc = nfo_engine.parse_nfo(nfo_path)
            if doc is None:
                return {"success": False, "message": f"nfo 解析失败: {nfo_path}"}
            person_map, role_map = {}, {}
            _recs_all = list(people_records or [])
            _recs_role = _recs_all
            try:
                _lv = nfo_engine.classify(nfo_path)
                if _lv == "episode":
                    _s = _n = None
                    try:
                        _sd, _sn, _s, _n = self._nfo_episode_meta(nfo_path)
                    except Exception:
                        pass
                    _hit = [r for r in _recs_all
                            if r.get("season_num") == _s and r.get("episode_num") == _n]
                    if _hit:
                        _recs_role = _hit
                elif _lv in ("tvshow", "movie", "season"):
                    _hit = [r for r in _recs_all
                            if r.get("season_num") is None and r.get("episode_num") is None]
                    if _hit:
                        _recs_role = _hit
            except Exception:
                pass
            for rec in _recs_all:
                nb = str(rec.get("name_before") or "").strip()
                na = str(rec.get("name_after") or "").strip()
                if nb and na and na != nb:
                    person_map[nb] = na
            for rec in _recs_role:
                rb = str(rec.get("role_before") or "").strip()
                ra = str(rec.get("role_after") or "").strip()
                if rb and ra and ra != rb:
                    role_map[rb] = ra
            if people_records:
                try:
                    _need_nb = any(
                        (str(_rec.get("name_before") or "").strip()
                         and str(_rec.get("name_before") or "").strip() not in person_map)
                        for _rec in people_records)
                    _need_rb = any(
                        (str(_rec.get("role_before") or "").strip()
                         and str(_rec.get("role_before") or "").strip() not in role_map)
                        for _rec in people_records)
                    if _need_nb or _need_rb:
                        _pool = (getattr(self, "_name_map_db", None) or NameMapDb()).load_map(
                            plugin_id=self.__class__.__name__)
                        _seen_nb = set(x.strip() for x in person_map.keys() if x)
                        for _rec in people_records:
                            _nb = str(_rec.get("name_before") or "").strip()
                            if not _nb or _nb in _seen_nb:
                                continue
                            _hit = _pool.get(("person", _nb))
                            if _hit and str(_hit[0] or "").strip() and str(_hit[0]).strip() != _nb:
                                person_map[_nb] = str(_hit[0]).strip()
                                _seen_nb.add(_nb)
                        # v4.6.74（P0 · 报告第三 / 二十节）：**角色不再回退全局池** ——
                        # 全局池是跨作品聚合的，A 剧「Guardian → 守护者」会让 B 剧写回时
                        # 用错译文。角色的权威来源 = 本条目自己的库记录（v4.6.64 起
                        # occurrence 精确写库，已含全部角色译文）+ 同剧角色记忆。
                        # （人名保持全局池回退 —— 第一排本就是全局人名设计。）
                except Exception:
                    pass
            try:
                if doc.root is not None:
                    _cur_role = {}
                    for _a in doc.root.findall("actor"):
                        _ne = _a.find("name")
                        _re = _a.find("role")
                        _nv = (_ne.text or "").strip() if _ne is not None and _ne.text else ""
                        _rv = (_re.text or "").strip() if _re is not None and _re.text else ""
                        if _nv and _rv:
                            _cur_role[_nv] = _rv
                    for _rec in _recs_role:
                        _ra = str(_rec.get("role_after") or "").strip()
                        if not _ra:
                            continue
                        for _key in (str(_rec.get("name_after") or "").strip(),
                                     str(_rec.get("name_before") or "").strip()):
                            _cv = _cur_role.get(_key)
                            if _cv and _cv != _ra:
                                role_map.setdefault(_cv, _ra)
            except Exception:
                pass
            _dist_added = 0
            try:
                _sdir2 = str(getattr(self, "_sync_direction", "s2e") or "s2e")
                _lv2 = nfo_engine.classify(nfo_path)
                if _sdir2 == "s2e" and _lv2 == "episode":
                    _tv_fp = self._find_show_tvshow_nfo(nfo_path)
                    _tdoc = nfo_engine.parse_nfo(_tv_fp) if _tv_fp else None
                    if _tdoc is not None:
                        _dist_added += doc.absorb_actors_from(
                            _tdoc, person_map, role_map,
                            overwrite_all=bool(getattr(self, "_nfo_episode_overwrite", False)))
                        if _dist_added:
                            self._push_log("INFO", f"剧→集分发：{os.path.basename(nfo_path)} 写入 {_dist_added} 位剧演员（写回阶段）")
                elif _sdir2 == "e2s" and _lv2 == "tvshow":
                    for _ep2 in nfo_engine.find_nfo_files([os.path.dirname(nfo_path)], recursive=True,
                                                          include_episodes=True):
                        if _ep2 == nfo_path:
                            continue
                        try:
                            _edoc2 = nfo_engine.parse_nfo(_ep2)
                            if _edoc2 is not None:
                                _dist_added += doc.merge_actors_from(_edoc2)
                        except Exception:
                            pass
                    if _dist_added:
                        self._push_log("INFO", f"集→剧合并：{os.path.basename(nfo_path)} 合并 {_dist_added} 位集演员（写回阶段）")
            except Exception as _de:
                logger.debug(f"[Writeback] 分发合并失败 {nfo_path}: {_de}")
            changed = doc.apply(person_map, role_map)
            changed += int(_dist_added or 0)   # 仅分发插入也算改动 → 触发落盘/计数
            if auto and changed == 0 and (person_map or role_map):
                self._push_log("INFO", f"自动写回跳过：{os.path.basename(nfo_path)} 已是译文（无改动）")
                return {"success": True, "message": f"已是译文，无需写回：{os.path.basename(nfo_path)}",
                        "data": {"changed": 0, "saved": True, "noop": True, "nfo_path": nfo_path}}
            if changed == 0 and not person_map and not role_map:
                if bool(getattr(self, "_lock_cast", False)) and not doc.is_cast_locked():
                    _locked = doc.save(backup=getattr(self, "_nfo_backup", False), dry_run=False,
                                       lock_cast=True)
                    if _locked:
                        self._push_log("INFO", f"无译文可写，已补锁 Cast：{os.path.basename(nfo_path)}")
                        return {"success": True, "message": f"无译文可写，已补锁 Cast：{os.path.basename(nfo_path)}",
                                "data": {"changed": 0, "saved": True, "locked": True, "nfo_path": nfo_path}}
                    _serr = str(getattr(nfo_engine, "_last_save_error", "") or (""))
                    logger.error(f"[DB] 补锁失败: {nfo_path} :: {_serr or '未知原因'}")
                    return {"success": False,
                            "message": f"补锁 Cast 失败：{os.path.basename(nfo_path)}（{_serr[:160] or '文件可能被 Emby/SMB 占用或目录只读'}）",
                            "data": {"changed": 0, "saved": False, "locked": False, "nfo_path": nfo_path}}
                return {"success": False, "message": "库中该条目无已翻译名单可写回"}
            saved = doc.save(backup=getattr(self, "_nfo_backup", False), dry_run=False,
                         lock_cast=bool(getattr(self, "_lock_cast", False)))
            # v4.6.73（报告第十二节）：写回后**复读校验** —— 重新解析确认文件可读且格式正常。
            _verified = None
            if saved:
                try:
                    _verified = nfo_engine.parse_nfo(nfo_path) is not None
                    if not _verified:
                        logger.warning(f"[Writeback] 写回后复读校验失败（文件可能损坏）: {nfo_path}")
                        self._push_log("WARN", f"写回后复读校验失败：{os.path.basename(nfo_path)}")
                except Exception:
                    _verified = None
            _lkd = ""
            if bool(getattr(self, "_lock_cast", False)):
                _lkd = "，Cast 已锁定" if doc.is_cast_locked() else "，Cast 未锁定（lockedfields 未写入成功）"
            else:
                _lkd = "，Cast 未锁定（设置未开启）"
            _bk_txt = "，.bak 已开启" if bool(getattr(self, "_nfo_backup", False)) else "，.bak 未开启"
            _why = ""
            if changed == 0:
                _where = f"{os.path.basename(os.path.dirname(nfo_path))}/{os.path.basename(nfo_path)}"
                _why = (f"  ← 原因：库中 {len(person_map)} 个人名 / {len(role_map)} 个角色译文，"
                        f"在 {_where} 里都没找到匹配文本。通常是该文件已是译文，"
                        f"或它是同一部剧/片的另一份副本、且其路径不在已勾选媒体库内")
            self._push_log("INFO", f"写入 nfo 完成：{os.path.basename(nfo_path)} 改动 {changed} 条{_lkd}（写回 {'成功' if saved else '失败'}{_bk_txt}）{_why}")
            if not saved:
                _serr = str(getattr(nfo_engine, "_last_save_error", "") or (""))
                logger.error(f"[DB] 写入 nfo 失败: {nfo_path} :: {_serr or '未知原因'}")
                self._push_log("ERROR", f"写入 nfo 失败：{os.path.basename(nfo_path)}（{_serr[:160] or '文件占用或只读'}）")
                return {"success": False, "message": f"写入 nfo 失败：{os.path.basename(nfo_path)}（{_serr[:160] or '文件可能被 Emby/SMB 占用或目录只读'}）",
                        "data": {"changed": changed, "saved": False, "nfo_path": nfo_path}}
            return {"success": True, "message": f"已写入 nfo：改动 {changed} 条{_bk_txt}{_lkd}", "data": {"changed": changed, "saved": True, "verified": _verified, "nfo_path": nfo_path}}
        except Exception as e:
            logger.error(f"[DB] 写回 nfo 失败: {e}\n{traceback.format_exc()}")
            return {"success": False, "message": str(e)}

    def _locate_nfo_from_item(self, item: dict) -> str:
        """根据 Emby 条目详情（含 Path）定位本地 nfo 文件。
        - 剧集 tvshow → 同目录 tvshow.nfo
        - 电影 → 同目录 movie.nfo / video.nfo / 与媒体同名的 nfo
        - 单集 → 同目录同名 nfo；没有则按 SxxExx 特征在当前目录与父目录找
        返回找到的 nfo 路径，找不到返回空串。
        """
        try:
            path = str((item or {}).get("Path") or "").strip()
            if not path:
                return ""
            p = path.replace("\\", "/")
            fn = os.path.basename(p).lower()
            itype = str((item or {}).get("Type") or "").lower()
            # v4.6.84（用户实测）：容器条目（Series/Season/Folder）的 Path 就是**目录本身** ——
            # 旧代码无条件 dirname(Path) 会退到「上一级目录」，导致 series 的 tvshow.nfo
            # 永远定位不到（后果：剧级行从不重新入库 → 剧级观察期永不解除、剧名一直「待恢复」）。
            # 对容器条目同时尝试「Path 本身」与「上一级」，既兼容 Emby 的目录式 Path，
            # 也兼容个别把 Path 写成文件路径的实现。
            if itype in ("series", "tvshow", "season", "folder"):
                _dirs = [p, os.path.dirname(p)]
            else:
                _dirs = [os.path.dirname(p)]
            d = _dirs[0]
            # 剧集容器条目：同目录（或上一级）的 tvshow.nfo
            if itype in ("series", "tvshow", "season", "folder"):
                for _d0 in _dirs:
                    t = os.path.join(_d0, "tvshow.nfo")
                    if os.path.isfile(t):
                        return t
            if itype in ("movie",):
                for cand in ("movie.nfo", "video.nfo"):
                    t = os.path.join(d, cand)
                    if os.path.isfile(t):
                        return t
            # 统一：先试同名 nfo（集文件 xxx.mkv → xxx.nfo）
            stem = os.path.splitext(fn)[0]
            for _d0 in _dirs:
                cand = os.path.join(_d0, stem + ".nfo")
                if os.path.isfile(cand):
                    return cand
            try:
                _target = stem + ".nfo"
                for _fn in os.listdir(d):
                    if _fn.lower() == _target:
                        _c2 = os.path.join(d, _fn)
                        if os.path.isfile(_c2):
                            return _c2
            except Exception:
                pass
            return ""
        except Exception as e:
            logger.warning(f"[NFO] 定位 nfo 失败: {e}")
            return ""

    def _tmdb_poster_url(self, item_id: str, item_type: str = "") -> str:
        """按 tmdbid 拉取 TMDB 海报完整 URL（参考 getmissingepisodes 的 TmdbChain 用法）。
        失败返回空串，前端显示占位图。带进程内缓存避免重复请求。
        """
        try:
            _tid = str(item_id or "").strip()
            if not _tid.isdigit():
                return ""
            cache = getattr(self, "_tmdb_poster_cache", None)
            if cache is None:
                cache = self._tmdb_poster_cache = {}
            if _tid in cache:
                return cache[_tid]
            from app.chain.tmdb import TmdbChain
            from app.schemas.types import MediaType, MediaSource
            chain = TmdbChain()
            mtype = MediaType.TV if str(item_type).lower() in ("series", "tvshow", "tv") else MediaType.MOVIE
            info = chain.recognize_media(
                mtype=mtype,
                media_source=MediaSource.TMDB,
                media_id=_tid,
            )
            poster = ""
            if info:
                poster = str(getattr(info, "poster_path", "") or "").strip()
            if not poster.startswith("http"):
                _base = str(getattr(settings, "TMDB_IMAGE_URL", "") or "https://image.tmdb.org/t/p/w500")
                _p = poster.lstrip("/")
                poster = f"{_base.rstrip('/')}/{_p}" if _p else ""
            # v4.6.103（TMDB-3）：无图/失败同样落缓存（空串）—— 此前只在拿到图时才写缓存，
            # 「ID 无效 / TMDB 无图」的条目每次打开详情都会重新请求一遍（同一条目反复打 TMDB）。
            cache[_tid] = poster or ""
            return poster
        except Exception as e:
            logger.debug(f"[TMDB] 拉取海报失败 {item_id}: {e}")
            try:
                _tid2 = str(item_id or "").strip()
                if _tid2.isdigit():
                    _c = getattr(self, "_tmdb_poster_cache", None)
                    if isinstance(_c, dict):
                        _c[_tid2] = ""   # v4.6.103（TMDB-3）：异常路径也记负结果，避免重复请求
            except Exception:
                pass
            return ""

    def _proxy_poster(self, url: str) -> str:
        """转成宿主图片代理签名 URL（<img> 直接可显示，绕过防盗链/域名白名单）。
        宿主端点 GET /api/v1/system/img/{proxy}?imgurl=<签名URL>，资源 token 走同源 cookie。
        """
        if not url:
            return ""
        try:
            from urllib.parse import quote
            from app.application.security.url import SecurityUtils
            signed = SecurityUtils.sign_url(url)  # fragment 追加 mp_sig 签名
            return "/api/v1/system/img/0?imgurl=" + quote(signed, safe="")
        except Exception:
            return url

    def _canonical_server_id(self, server_id: str) -> str:
        """把「任意来源的 server_id」归一为服务器级 mapping 使用的 skey。

        Webhook 报文里 Emby 携带的是 ServerId（GUID），或宿主的 server_name，与
        _nfo_path_mappings 的键 skey（name_host_port）命名空间不同；不归一 →
        _server_mapping(server_id) 匹配不到 → 路径映射整体不生效（映射用户的
        Webhook 会因未映射路径被判「未选择该媒体库」而丢弃）。此处在 Webhook 路径
        解析入口统一归一（文档 §三十一 规则 12：任何 Webhook path 必须检查 server_id）。

        优先级：已是 skey > 服务器名匹配 > Emby GUID 反查；都匹配不到则原样返回
        （交由上层按「未匹配」处理，绝不静默套用其它服务器的 mapping）。
        """
        sid = str(server_id or "").strip()
        if not sid:
            return ""
        services = []
        try:
            services = self._get_all_emby_services() or []
        except Exception:
            services = []
        # 1) 已经是某台服务器的 skey（未配置 mapping 的服务器同样命中，保持原值）
        for svc in services:
            try:
                if self._get_server_identifier(svc) == sid:
                    return sid
            except Exception:
                continue
        # 2) 服务器名匹配（宿主广播的 server_name）
        _low = sid.lower()
        for svc in services:
            try:
                if (getattr(svc, 'name', '') or '').strip().lower() == _low:
                    return self._get_server_identifier(svc)
            except Exception:
                continue
        # 3) Emby GUID 反查（skey -> GUID，见 _load_emby_server_ids；探测带 5 分钟节流）
        try:
            if not getattr(self, "_emby_server_ids", None):
                _ts = float(getattr(self, "_emby_server_ids_ts", 0) or 0)
                if time.time() - _ts > 300:
                    self._load_emby_server_ids()
            for _skey, _guid in (self._emby_server_ids or {}).items():
                if str(_guid) == sid:
                    return str(_skey)
        except Exception:
            pass
        # 4) 实在无法归一 → 原样返回（上层按未匹配处理，不猜第一台）
        return sid

    def _server_mapping(self, server_id: str) -> Tuple[str, str]:
        """取指定服务器的路径映射 (from, to) —— 仅服务器级 mapping（全局旧映射已移除）。
        未配置的服务器返回 ("", "")，即直接使用 Emby 原路径。"""
        sid = str(server_id or "").strip()
        if sid:
            for m in (getattr(self, "_nfo_path_mappings", None) or []):
                if not isinstance(m, dict):
                    continue
                if str(m.get("server_id") or "").strip() == sid:
                    _f = str(m.get("from") or "").strip()
                    if _f:
                        return _f, str(m.get("to") or "").strip()
        return ("", "")

    def _resolve_library_path(self, server_id: str, raw_path: str) -> str:
        """统一路径 resolver —— 唯一路径映射入口。

        Emby 原始 Path →（服务器级 mapping > 原始）→ MP 本地路径。
        扫描 / Webhook / 预检 / 文件浏览全部走本函数，禁止第二套替换逻辑。
        """
        _f, _t = self._server_mapping(server_id)
        return self._apply_root_replace(raw_path, _f, _t)

    def _migrate_legacy_mapping_for(self, server_id: str, server_name: str = "") -> bool:
        """旧版全局 nfo_replace_from/to → 服务器级 nfo_path_mappings 一次性迁移。

        只对「尚无 mapping 的服务器」各补一条（老用户升级不丢旧替换规则；之后可在设置页逐服务器修改）。
        返回是否新增。"""
        _lf, _lt = getattr(self, "_legacy_mapping", ("", "")) or ("", "")
        sid = str(server_id or "").strip()
        if not _lf or not sid:
            return False
        _maps = list(getattr(self, "_nfo_path_mappings", None) or [])
        for m in _maps:
            if isinstance(m, dict) and str(m.get("server_id") or "").strip() == sid:
                return False
        _maps.append({"server_id": sid, "server_name": str(server_name or ""), "from": _lf, "to": _lt})
        self._nfo_path_mappings = _maps
        logger.info(f"[Config] 旧版全局映射已迁移到服务器「{server_name or sid}」：{_lf} → {_lt}（设置页可按服务器修改）")
        return True

    def _normalize_webhook_item(self, item: dict, server_id: str = "") -> dict:
        """Webhook 条目路径归一化（缺陷 A）—— Emby 推送的 item.Path 是
        挂载原始路径，而库路径（_get_emby_libraries）与门禁白名单都是
        mapping 之后的路径。这里对 item.Path 做同样的前缀替换并写回，
        此后 `_in_selected_library` / `_dir_in_nfo_roots` / `_locate_*` 全部基于
        同一套替换后口径，避免配置了 replace 的用户 Webhook 整批失效。
        严格按 server_id 路由 —— 调统一 resolver（不用别的服务器的 mapping 猜）。
        """
        try:
            if item and item.get("Path"):
                _p = str(item.get("Path") or "").strip()
                _sid = str(server_id or item.get("ServerId") or "").strip()
                _np = self._normalize_webhook_path(_sid, _p)
                if _np and _np != _p:
                    item["Path"] = _np
        except Exception:
            pass
        return item or {}

    def _normalize_webhook_path(self, server_id: str, path: str) -> str:
        """Webhook 条目路径归一化 —— 复用统一 resolver，不得另起替换逻辑。
        server_id 已知 → 只应用该服务器自己的 mapping（绝不套用其它服务器的规则）；
        server_id 缺失（旧事件）→ 逐条尝试能命中的 mapping 兜底（与旧行为一致）。
        server_id 先归一为 skey —— Webhook 报文多为 Emby GUID / 服务器名，
        与 mapping 键 skey 命名空间不同；不归一则 mapping 永远匹配不到（映射用户 Webhook 路径
        替换失效）。归一后仍只应用「该服务器自己的」mapping。"""
        p = self._norm_seg_path(path)
        if not p:
            return str(path or "").strip()
        _sid = str(server_id or "").strip()
        if _sid:
            _sid = self._canonical_server_id(_sid)
            return self._resolve_library_path(_sid, p)
        for m in (getattr(self, "_nfo_path_mappings", None) or []):
            if not isinstance(m, dict):
                continue
            _f = str(m.get("from") or "").strip()
            if not _f:
                continue
            _r = self._apply_root_replace(p, _f, str(m.get("to") or ""))
            if _r != p:
                return _r
        return p

    def _get_emby_libraries(self) -> List[dict]:
        """探测所有 Emby 服务下的媒体库列表（只读，含 Id/Name/Path）。

        Path 已做前缀替换。失败返回 []（不影响既有流程）。
        带 60s 内存缓存 —— Webhook 每事件、库页渲染都会用到，
        避免每次触发对 Emby 的探测往返。
        """
        try:
            if self._lib_cache and (time.time() - self._lib_cache_ts) < 60:
                return self._lib_cache
        except Exception:
            pass
        result = []
        try:
            for svc in self._get_all_emby_services():
                skey = self._get_server_identifier(svc)
                sname = (getattr(svc, 'name', '') or '').strip() or "Emby"
                try:
                    self._migrate_legacy_mapping_for(skey, sname)
                except Exception:
                    pass
                client = EmbyClient(self._get_service_url(svc), self._get_service_api_key(svc), svc,
                                    user_id=self._get_service_user_id(svc),
                                    use_proxy=self._use_proxy)
                try:
                    libs = client.get_libraries() or []
                except Exception as e:
                    logger.warning(f"[Libraries] 获取服务库失败: {e}")
                    continue
                for lib in libs:
                    lib_id = str(lib.get("Id", ""))
                    if not lib_id:
                        continue
                    _raw = str(lib.get("Path") or "")
                    _mapped = self._resolve_library_path(skey, _raw)
                    _mf, _mt = self._server_mapping(skey)
                    _rec = {
                        "skey": skey,
                        "server_id": skey,
                        "lib_id": lib_id,
                        "server_name": sname,
                        "lib_name": str(lib.get("Name") or "?"),
                        "lib_type": str(lib.get("Type") or ""),
                        "emby_path": _raw,
                        "path": _mapped,
                        "mapping_from": _mf,
                        "mapping_to": _mt,
                        "full_key": f"{skey}:{lib_id}",
                    }
                    try:
                        _rec["path_exists"] = bool(_mapped) and os.path.exists(_mapped)
                        _rec["path_readable"] = bool(_mapped) and os.access(_mapped, os.R_OK) if _rec["path_exists"] else False
                        _rec["path_is_dir"] = bool(_mapped) and os.path.isdir(_mapped)
                    except Exception:
                        _rec["path_exists"] = False
                        _rec["path_readable"] = False
                        _rec["path_is_dir"] = False
                    result.append(_rec)
        except Exception as e:
            logger.error(f"[Libraries] 媒体库列表失败: {e}")
        if result:
            self._legacy_mapping = ("", "")
        try:
            self._lib_cache = result
            self._lib_cache_ts = time.time()
        except Exception:
            pass
        return result

    def _selected_library_paths(self) -> List[str]:
        """已选中库的自动根目录（库 Path，经前缀替换）。

        - 选中的库以 full_key（skey:lib_id）或裸 lib_id 匹配
        - 命中且 Path 非空 → 作为扫描根目录
        - 一个库都没选 → 返回 []（表示不启用库过滤/自动根目录）
        """
        libs = self._libraries or []
        if not libs:
            return []
        want = set(libs)
        paths = []
        for lib in self._get_emby_libraries():
            if lib["full_key"] in want or lib["lib_id"] in want:
                if lib["path"]:
                    paths.append(lib["path"])
        return list(dict.fromkeys(paths))

    def _all_nfo_roots(self) -> List[str]:
        """扫描根目录 = 已选中的媒体库路径（经前缀替换）。

        手动 nfo_roots 已废弃（库 Path 自动映射，无需手填；前缀不一致用 replace）。
        未选任何库 → 返回 []：扫描明确拒绝、Webhook 一律屏蔽。
        缺陷 F —— 兼容回退：v3.5 老用户只填过 nfo_roots、没选过媒体库时，
        仍沿用旧 nfo_roots 并打 WARNING 引导迁移到媒体库选择，避免升级后直接拒绝扫描。
        """
        paths = self._selected_library_paths()
        if paths:
            return paths
        legacy = []
        try:
            raw = self._nfo_roots
            if isinstance(raw, str):
                legacy = [x.strip() for x in raw.splitlines() if x.strip()]
            elif isinstance(raw, (list, tuple)):
                legacy = [str(x).strip() for x in raw if str(x).strip()]
        except Exception:
            legacy = []
        if legacy:
            # 只提示一次（内存标志），避免每次调用刷屏
            if not getattr(self, "_nfo_root_warned", False):
                self._nfo_root_warned = True
                logger.warning("[NFO] 检测到旧版手动 NFO 目录配置（nfo_roots）。该配置已废弃，"
                               "建议前往设置页选择 Emby 媒体库（其目录自动作为扫描根目录，可跨容器用「路径前缀替换」映射）")
                self._push_log("WARNING", "沿用旧版手动 NFO 目录（已废弃）—— 建议改用「选择 Emby 媒体库」自动映射，或配置「路径前缀替换」应对容器挂载差异")
            return legacy
        return []

    def _in_selected_library(self, path: str) -> bool:
        """库白名单判断 —— 条目的 Path 是否落在已选中的库目录下。

        - 未选择任何库 → False（入库一律屏蔽、不处理不提醒）
        - 选了库 → 命中任一选中库的 Path 前缀才算
        """
        paths = self._selected_library_paths()
        if not paths:
            return False
        p = str(path or "").replace("\\", "/").strip("/")
        if not p:
            return False
        for root in paths:
            r = str(root).replace("\\", "/").strip("/")
            if r and (p == r or p.startswith(r + "/")):
                return True
        return False

    def _library_name_for_path(self, path: str) -> str:
        """从 nfo 路径推导所属媒体库名（库页左侧分组用）。

        遍历全部 Emby 服务的库，匹配路径前缀；匹配不到返回 ""（前端归「未分类」）。
        仅使用缓存中的库列表（60s），不额外探测。
        """
        try:
            p = str(path or "").replace("\\", "/").strip("/")
            if not p:
                return ""
            for lib in self._get_emby_libraries():
                r = str(lib.get("path") or "").replace("\\", "/").strip("/")
                if r and (p == r or p.startswith(r + "/")):
                    # 多服务器同名库 → 带服务器名前缀区分
                    _srv = str(lib.get("server_name") or "").strip()
                    _nm = str(lib.get("lib_name") or "").strip()
                    return f"{_srv} · {_nm}" if _srv and _nm else (_nm or _srv or "")
            return ""
        except Exception:
            return ""

    def _api_emby_libraries(self):
        try:
            return {"success": True, "data": self._get_emby_libraries()}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ============================================================
    # ============================================================
    def _check_one_path(self, server_id: str, lib_id: str, raw_path: str = "") -> dict:
        """单条路径预检（只读、不递归）。

        返回：映射前后的路径、映射是否命中、是否存在/可读/是目录、顶层 nfo 计数、明确提示。
        """
        server_id = str(server_id or "").strip()
        lib_id = str(lib_id or "").strip()
        emby_path = str(raw_path or "").strip()
        resolved = ""
        # 1) 优先按媒体库定位（含 server_id 精确匹配）
        if lib_id:
            for lib in self._get_emby_libraries():
                if lib.get("lib_id") != lib_id:
                    continue
                if server_id and lib.get("skey") != server_id:
                    continue
                emby_path = str(lib.get("emby_path") or "")
                resolved = str(lib.get("path") or "")
                break
        # 2) 未命中媒体库 → 用传入 raw_path 走统一 resolver
        if not resolved and emby_path:
            resolved = self._resolve_library_path(server_id, emby_path)
        mf, mt = self._server_mapping(server_id)
        info = {
            "server_id": server_id,
            "lib_id": lib_id,
            "emby_path": emby_path,
            "path": resolved,
            "mapping_from": mf,
            "mapping_to": mt,
            "exists": False,
            "readable": False,
            "is_dir": False,
            "nfo_count": 0,
            "message": "",
        }
        # 映射命中状态：无替换配置=None / 命中=True / 未命中=False（§四十三 未命中明确提示）
        if not mf:
            info["mapping_hit"] = None
        else:
            info["mapping_hit"] = self._seg_prefix_match(emby_path, mf)
        if not resolved:
            info["message"] = "路径为空：未配置映射或该媒体库无 Path"
            return info
        try:
            info["exists"] = os.path.exists(resolved)
            info["is_dir"] = os.path.isdir(resolved)
            info["readable"] = info["exists"] and os.access(resolved, os.R_OK)
        except Exception as e:
            info["message"] = f"路径检查异常：{e}"
            return info
        if info["exists"] and info["is_dir"]:
            try:
                with os.scandir(resolved) as it:
                    info["nfo_count"] = sum(1 for e in it
                                            if e.is_file() and e.name.lower().endswith(".nfo"))
            except Exception:
                pass
        if not info["exists"]:
            info["message"] = f"路径不存在：{resolved}"
        elif not info["is_dir"]:
            info["message"] = f"路径存在但不是目录：{resolved}"
        elif not info["readable"]:
            info["message"] = f"路径无读取权限：{resolved}"
        else:
            info["message"] = "路径可访问"
        return info

    def _api_nfo_path_check(self, data: Optional[dict] = None):
        """扫描前路径预检 API。
        入参：{"server_id","lib_id"} 或 {"server_id","path"}。"""
        try:
            data = data or {}
            info = self._check_one_path(str(data.get("server_id") or ""),
                                        str(data.get("lib_id") or ""),
                                        str(data.get("path") or ""))
            return {"success": True, "data": info}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_nfo_path_check_all(self, data: Optional[dict] = None):
        """「测试全部路径」—— 对所有已选媒体库批量预检。"""
        try:
            want = set(self._libraries or [])
            libs = self._get_emby_libraries()
            targets = [l for l in libs
                       if (not want) or (l.get("full_key") in want or l.get("lib_id") in want)]
            rows = [self._check_one_path(str(l.get("skey") or ""),
                                         str(l.get("lib_id") or ""),
                                         str(l.get("emby_path") or ""))
                    for l in targets]
            ok = sum(1 for r in rows if r.get("exists") and r.get("is_dir") and r.get("readable"))
            return {"success": True, "data": {"total": len(rows), "ok": ok, "rows": rows}}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_nfo_path_browse(self, server_id: str = "", lib_id: str = "", path: str = ""):
        """文件浏览（只读，限定媒体库根目录）。

        入参（GET query）：server_id / lib_id / path（path 可空=列根目录，可为根内子路径）。
        修复：GET 端点必须用命名参数接收 query（宿主按函数签名绑定；同 /live_log、/pool/list）。
        此前用 POST 风格 data 字典签名 → 参数全部丢失（server_id/lib_id 恒为空）→ 恒报「未找到该媒体库」。
        安全：根目录只能来自已探测媒体库的映射后路径；禁止越界 / ../ / 任意绝对路径；不提供删除/改名。
        """
        try:
            server_id = str(server_id or "").strip()
            lib_id = str(lib_id or "").strip()
            sub = str(path or "").strip()
            root = ""
            emby_path = ""
            for lib in self._get_emby_libraries():
                if lib_id and lib.get("lib_id") != lib_id:
                    continue
                if server_id and lib.get("skey") != server_id:
                    continue
                if not (lib_id or server_id):
                    continue
                emby_path = str(lib.get("emby_path") or "")
                root = str(lib.get("path") or "")
                break
            if not root and emby_path:
                root = self._resolve_library_path(server_id, emby_path)
            if not root:
                return {"success": False, "message": "未找到该媒体库或库无有效本地路径（请先配置路径映射）"}
            root = os.path.abspath(root)
            if sub:
                target = os.path.abspath(sub) if os.path.isabs(sub) else os.path.abspath(os.path.join(root, sub))
            else:
                target = root
            # 越界校验（realdir 前缀必须落在 root 内）
            try:
                if os.path.commonpath([root, target]) != root:
                    return {"success": False, "message": "越界访问被拒绝：仅允许浏览媒体库根目录内"}
            except Exception:
                if not (target == root or target.startswith(root + os.sep)):
                    return {"success": False, "message": "越界访问被拒绝：仅允许浏览媒体库根目录内"}
            try:
                _rroot = os.path.realpath(root)
                _rtarget = os.path.realpath(target)
                if os.path.commonpath([_rroot, _rtarget]) != _rroot:
                    return {"success": False,
                            "message": "越界访问被拒绝：目标经软链接解析后落在媒体库根目录之外"}
            except Exception:
                pass
            if not os.path.isdir(target):
                return {"success": False, "message": f"目录不存在或不是目录：{target}"}
            if not os.access(target, os.R_OK):
                return {"success": False, "message": f"目录无读取权限：{target}"}
            entries = []
            try:
                with os.scandir(target) as it:
                    for e in it:
                        try:
                            is_dir = e.is_dir()
                            entries.append({
                                "name": e.name,
                                "is_dir": is_dir,
                                "size": 0 if is_dir else int((e.stat().st_size) or 0),
                            })
                        except Exception:
                            continue
            except Exception as e:
                return {"success": False, "message": f"读取目录失败：{e}"}
            entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
            try:
                rel = os.path.relpath(target, root)
            except Exception:
                rel = ""
            return {"success": True, "data": {
                "root": root,
                "path": target,
                "relative": "" if rel in (".", "") else rel.replace("\\", "/"),
                "entries": entries,
            }}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _zhconv_convert(self, text: str) -> str:
        """繁转简（无依赖时原样返回）"""
        try:
            if not HAS_ZHCONV:
                return text
            import zhconv
            r = zhconv.convert(text, "zh-cn")
            return r if r != text else text
        except Exception:
            return text

    def _zhconv_final_ok(self, text: str, conv: str) -> bool:
        """繁转简 / 池命中的结果能否**直接当作最终译文**（v4.6.107 · LIB-014）。

        与库/池自己的「有效译文」判定（`db._SQL_ZH_VALID`）保持**同一口径**：
        译文必须 ≠ 原文，**且不得残留假名**。

        为什么必须卡这一道：像「雛坂ひかる」「紗倉のり子」「廣原ふう」这类
        **汉字 + 假名**的日文名，`zhconv` 只会把汉字部分转掉
        （→「雏坂ひかる」/「纱仓のり子」/「广原ふう」），假名原封不动。
        此前只要 `zhconv(t) != t` 就当命中并计入完成，于是：
          · 词条被标成「已处理」，**永远不会送去 LLM**（所以日志里 LLM 恒为 0 条）；
          · 而池/库的「有效译文」判定排除含假名的 name_zh → 行永远停在「🔴 待翻译」；
          · 下一轮又被收进来，再次「繁转简命中」……
        用户实测正是：9 条池待翻卡在「本轮 2 条 · 繁转简 2 条 · 剩余 4 条」死循环，
        永远收敛不了。现在这类词条一律放行给 LLM，由模型给出真正的中文名
        （如「雏坂光」），写回后池行才真正脱离「待翻译」。
        """
        _t = str(text or "").strip()
        _z = str(conv or "").strip()
        if not _t or not _z or _z == _t:
            return False
        try:
            return not _is_kana_text(_z)
        except Exception:
            return False

    def _api_nfo_test(self, data: Optional[dict] = None):
        try:
            from . import nfo as nfo_engine
            data = data or {}
            roots = list(data.get("roots") or [])
            roots += [x.strip() for x in str(data.get("root_text") or "").splitlines() if x.strip()]
            if not roots:
                roots = self._all_nfo_roots()
            if not roots:
                return {"success": False, "message": "未选择任何媒体库，无法测试扫描。请先在设置页选择要处理的 Emby 媒体库"}
            recursive = bool(data.get("recursive", True))
            include_episodes = bool(data.get("include_episodes", False))
            files = nfo_engine.find_nfo_files(roots, recursive=recursive,
                                              include_episodes=include_episodes)
            stat = {"movie": 0, "tvshow": 0, "season": 0, "episode": 0, "fail": 0}
            name_total = role_total = 0
            for fp in files:
                doc = nfo_engine.parse_nfo(fp)
                if doc is None:
                    stat["fail"] += 1
                    continue
                stat[doc.level] = stat.get(doc.level, 0) + 1
                names, roles = doc.collect()
                name_total += len(names)
                role_total += len(roles)
            self._push_log("INFO", f"NFO 测试扫描: 共 {len(files)} 个文件（电影{stat['movie']} 剧集{stat['tvshow']} 单集{stat['episode']} 解析失败{stat['fail']}），人名 {name_total} 条/角色 {role_total} 条")
            return {"success": True, "data": {"files": len(files), "stat": stat,
                                              "names": name_total, "roles": role_total}}
        except Exception as e:
            logger.error(f"[NFO] 测试扫描失败: {e}")
            return {"success": False, "message": str(e)}


    def _api_live_log(self, limit: int = 100):
        try:
            limit = int(limit) if limit else 100
            with self._state_lock:
                logs = list(self._live_log[-limit:])
            return {"success": True, "data": logs}
        except Exception as e:
            return {"success": False, "message": str(e)}


    def _push_log(self, level: str, msg: str):
        try:
            with self._state_lock:
                self._live_log.append({
                    "time": time.time(),
                    "level": level,
                    "msg": msg,
                })
                # 只保留最近 500 条
                if len(self._live_log) > 500:
                    self._live_log = self._live_log[-500:]
        except Exception:
            pass


    def _build_scan_status(self) -> Dict[str, Any]:
        """直接返回 _scan_status dict 引用 - 单一数据源
        不再从多个 _progress_* 属性聚合，杜绝读写不同步问题
        UI 读取时建议 dict(self._scan_status) 浅拷贝避免外部篡改
        """
        with self._state_lock:
            status = dict(self._scan_status)
            # UI-004：running 只代表「扫描」本身，不再用聚合 _is_running
            # （否则只跑探测/翻译/写回时扫描进度会被误判为「扫描中」）
            status["running"] = self._task_running("scan")
            status["tasks"] = {t: self._task_running(t) for t in ("scan", "translate", "writeback", "pool", "probe")}
            total = status.get("total", 0) or 0
            done = status.get("done", 0) or 0
            status["percent"] = round(done / max(total, 1) * 100, 1) if total > 0 else 0.0
            status["elapsed_seconds"] = self._elapsed_seconds()
            status["last_run_time"] = self._last_run_time
            return status



    def _elapsed_seconds(self) -> int:
        """当前条目处理耗时（秒）"""
        try:
            return int(time.time() - getattr(self, "_progress_step_start_time", time.time()))
        except Exception:
            return 0


    def log(self, level: str, msg: str):
        """统一日志入口，所有模块应该使用此方法
        而非直接 logger.info()，确保 UI 实时日志可以完整显示
        """
        if level == "INFO":
            logger.info(msg)
        elif level == "WARNING":
            logger.warning(msg)
        elif level == "ERROR":
            logger.error(msg)
        elif level == "DEBUG":
            logger.debug(msg)
        else:
            logger.info(msg)
        self._push_log(level, msg)

    _log_bridge_installed: bool = False
    def _install_log_bridge(self):
        if self._log_bridge_installed:
            return
        try:
            import logging
            # MoviePilot 主 logger 名称为 "moviepilot"，插件 logger 通过
            # 继承的子 logger 名为 "moviepilot.plugins.embypeoplelocalize" 等
            # 我们需要拦截带有 [EmbyClient]/[LLM] 前缀的日志
            class _LogBridgeHandler(logging.Handler):
                def emit(_h, record):
                    try:
                        msg = _h.format(record)
                        # 只接管底层模块的日志
                        if any(tag in msg for tag in ("[EmbyClient]", "[LLM]")):
                            _inst = getattr(EmbyPeopleLocalize, "_active_instance", None)
                            if _inst is None:
                                return
                            level = record.levelname or "INFO"
                            if level not in ("WARNING", "ERROR", "DEBUG"):
                                level = "INFO"
                            _inst._push_log(level, msg)
                    except Exception:
                        pass
            # 找到 moviepilot 的根 logger：先移除本插件安装过的旧 bridge
            # （用标记属性识别 —— 每次热重载类对象都是新类，isinstance 判定不可靠且会
            # 挡住新装；同时兼容清理旧版本无标记、带 .outer 的 handler）
            root_logger = logging.getLogger("moviepilot")
            for _h in list(root_logger.handlers):
                if getattr(_h, "_epl_bridge", False) or (
                        _h.__class__.__name__ == "_LogBridgeHandler" and hasattr(_h, "outer")):
                    try:
                        root_logger.removeHandler(_h)
                    except Exception:
                        pass
            if root_logger:
                bridge = _LogBridgeHandler()
                bridge._epl_bridge = True
                bridge.setLevel(logging.INFO)
                bridge.setFormatter(logging.Formatter("%(message)s"))
                root_logger.addHandler(bridge)
                EmbyPeopleLocalize._active_instance = self
                self._log_bridge_installed = True
                logger.info("[EmbyPeopleLocalize] 日志桥接已安装")
                self._ensure_plugin_logfile()
        except Exception as e:
            logger.warning(f"安装日志桥接失败: {e}")

    def _ensure_plugin_logfile(self):
        """路径改用宿主 CONFIG_PATH 推导（不再依赖进程 cwd）；
        换 RotatingFileHandler（5MB × 3）防长期运行日志无限增长。"""
        try:
            import logging
            from logging.handlers import RotatingFileHandler
            if getattr(self, "_logfile_ok", False):
                return
            log_root = ""
            try:
                from app.sdk.config import settings as _st
                _cfg = getattr(_st, "CONFIG_PATH", None)
                if _cfg:
                    log_root = os.path.join(str(_cfg), "logs", "plugins")
            except Exception:
                log_root = ""
            if not log_root:
                log_root = os.path.join("config", "logs", "plugins")
            os.makedirs(log_root, exist_ok=True)
            path = os.path.join(log_root, "embypeoplelocalize.log")
            fh = RotatingFileHandler(path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [EmbyPeopleLocalize] %(message)s"))
            # 挂到插件自身子 logger（moviepilot.plugins.embypeoplelocalize 的后代），不影响他人
            lg = logging.getLogger("moviepilot.plugins.embypeoplelocalize")
            for _lh in list(lg.handlers):
                if getattr(_lh, "_epl_logfile", False):
                    try:
                        lg.removeHandler(_lh)
                    except Exception:
                        pass
            fh._epl_logfile = True
            lg.addHandler(fh)
            self._logfile_ok = True
            logger.info(f"插件文件日志已启用: {path}")
        except Exception as e:
            logger.warning(f"启用插件文件日志失败: {e}")


    @staticmethod
    def get_render_mode() -> Tuple[str, str]:
        return "vue", "dist/assets"

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        """Vue 模式下返回 (None, 合并模型)；配置页由 Config.vue 渲染。"""
        try:
            config = self._dump_config()
            if not config.get("prompt_template"):
                config["prompt_template"] = constants.DEFAULT_PROMPT
            return None, config
        except Exception as e:
            logger.error(f"构建配置模型失败: {e}\n{traceback.format_exc()}")
            return None, {}

    @staticmethod
    def get_page() -> Optional[List[dict]]:
        return None

    def get_sidebar_nav(self) -> Optional[List[dict]]:
        """不注册宿主侧栏全页入口：插件仅在宿主「弹窗」内渲染。

        弹窗内部即左侧导航（仪表盘/库/设置）+ 右侧内容，默认落在仪表盘。
        """
        return []

    def get_state(self) -> bool:
        return self._enabled

    def _api_gate(self) -> Optional[dict]:
        """门禁口径统一（全插件唯一规则）——
        需要 gate：任何「会修改插件数据（DB / 人名池 / 事件 / 持久化状态）或发起任务」的接口；
        不 gate：① 只读查询/统计/导出（含路径预检与文件浏览——只读不递归）；
                 ② 安全控制（停止/暂停/继续：任何状态下都必须可用）；
                 ③ 配置读写与 LLM 测试、清空实时日志（内存诊断）、依赖检查
                    （插件未启用时也要能配置与排障 —— 文档 §P2-3「插件未启用可以配置」）。
        """
        if not getattr(self, "_enabled", False):
            return {"success": False, "message": "插件未启用：请先在设置页打开「启用插件」"}
        return None

    def _task_busy_msg(self) -> Optional[dict]:
        """任务运行中拒绝数据操作（清缓存/清记录/导入/重翻译/写回），
        避免与后台 worker 并发读写同一批数据产生不可预期结果。
        翻译 worker 是常驻线程、不置 _translate_running 位，「翻译中」只体现为消费许可
        _tx_requested；此前翻译期间清人名池/清库不会被拦截（用户：这边在翻译，那边给它删了）。
        此处把「已下发翻译许可」也视为运行中一并拒绝，直到任务结束或终止。"""
        with self._scan_lock:
            _busy = bool(self._is_running) or bool(getattr(self, "_tx_requested", False))
        if not _busy:
            # v4.6.76（规范 §十一）：统一「数据变更锁」口径 —— 扫描/翻译/写回/人名池/探测库
            # 任一在跑（或池正在拉取）都视为忙碌；此前只看 _is_running + 翻译许可，
            # 导致写回/池/探测运行中仍可改 name_map / 人物池 / 起池翻译。
            try:
                _busy = bool(self._task_state().get("data_mutation_locked"))
            except Exception:
                _busy = False
        if _busy:
            return {"success": False,
                    "message": "任务正在运行中，请先「终止」或等待完成后，再进行此操作"}
        return None

    def _clear_transient_stop_bits(self) -> None:
        """停止位自愈复位（v4.6.108 · LIB-015）。

        「终止」(`_api_stop` → `_request_task_stop`) 会置 `_stop_requested` 与各任务的
        停止位（`_scan_stop` / `_tx_stop` / `_wb_stop` / `_pool_stop` / `_probe_stop`）——
        这些位只表示「请当前这轮停下来」，**但没有任何地方在停完之后把它们复位**。
        而 `_task_state()` 把 `_stop_requested` / `_wb_stop` 当作 STOPPING，于是：

            终止 → STOPPING → data_mutation_locked 恒为 True
                 → 所有「开始新任务 / 改数据」都被 `_task_busy_msg()` 拦住
                   （连保存配置都会提示「任务运行中」）
                 → 而能复位停止位的 `_launch_*` 又被这个门拦着 → 死锁，只能重启插件。

        用户实测日志正是：17:03:03 已「归还消费许可」→ 26 秒后 17:03:29 保存配置仍判
        「任务运行中，下个任务生效」。

        现在由 `_task_state()` 在「确认没有任何任务在跑、也没有未归还的翻译许可」时调用本方法，
        把这些**请求位**复位回待命态（不清 `_tx_requested` —— 它由翻译线程自己归还）。
        """
        try:
            self._stop_requested = False
            self._scan_stop = False
            self._tx_stop = False
            self._wb_stop = False
            self._pool_stop = False
            self._probe_stop = False
        except Exception:
            pass

    def _task_state(self) -> dict:
        """统一任务状态（v4.6.73 · 报告第十五节）—— 单一状态 + 是否锁数据变更。

        状态：IDLE / SCANNING / PROBING / TRANSLATING / WRITING / POOL_FETCHING /
        POOL_SYNCING / STOPPING。任一非 IDLE 状态都视为「数据变更已锁」（前端据此统一拦截）。
        优先级：STOPPING > WRITING > TRANSLATING > SCANNING > PROBING > POOL_FETCHING > POOL_SYNCING。
        """
        try:
            _scan = self._task_running("scan")
            _tx = self._task_running("translate")
            _wb = self._task_running("writeback")
            _pool = self._task_running("pool")
            _probe = self._task_running("probe")
            # v4.6.108（LIB-015）：停止位自愈 —— 确认「没有任何任务在跑、也没有未归还的翻译许可」
            # （= 各 worker 都已收到并消化了停止请求）就把停止位复位，状态回到 IDLE，
            # 否则会永久卡在 STOPPING、把后续所有启动/改数据操作都锁死（详见本方法上方说明）。
            if not (_scan or _tx or _wb or _pool or _probe
                    or bool(getattr(self, "_tx_requested", False))
                    or bool(getattr(self, "_pool_pulling", False))):
                self._clear_transient_stop_bits()
            _stopping = bool(getattr(self, "_stop_requested", False) or getattr(self, "_wb_stop", False))
            if _stopping:
                _state = "STOPPING"
            elif _wb:
                _state = "WRITING"
            elif _tx:
                _state = "TRANSLATING"
            elif _scan:
                _state = "SCANNING"
            elif _probe:
                _state = "PROBING"
            elif bool(getattr(self, "_pool_pulling", False)):
                _state = "POOL_FETCHING"
            elif _pool:
                _state = "POOL_SYNCING"
            else:
                _state = "IDLE"
            return {"state": _state, "data_mutation_locked": _state != "IDLE",
                    "tasks": {"scan": _scan, "translate": _tx, "writeback": _wb,
                              "pool": _pool, "probe": _probe}}
        except Exception:
            return {"state": "IDLE", "data_mutation_locked": False,
                    "tasks": {"scan": False, "translate": False, "writeback": False,
                              "pool": False, "probe": False}}

    # ============================================================
    # API 处理
    # ============================================================
    def _api_clear_cache(self):
        try:
            _g = self._api_gate()
            if _g:
                return _g
            _tb = self._task_busy_msg()
            if _tb:
                return _tb
            self.clear_cache()
            self._push_log("INFO", "手动清空人名池自动翻译条目（人工修正保留）")
            return {"success": True, "message": "已清空"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_scan(self):
        _g = self._api_gate()
        if _g:
            return _g
        return self._api_nfo_sync(None)

    def _api_stop(self, data: Optional[dict] = None):
        """请求停止当前任务（NFO 扫描/Webhook 批量），保存断点可续扫
        缺陷 I —— 除置位外，强制关闭 LLM HTTP 连接，让飞行中的请求立即抛异常、
        停止秒级生效（否则要等当前批次最多 120s 读超时 + 429 重试 5s+10s+20s ≈ 2.5 分钟）。
        close 后置 None + 复位背景初始化，worker 开工时会惰性重建客户端（见 _nfo_sync_worker）。
        停止位彻底拆开 —— scan/translate/writeback/pool/probe 各自独立
        （_request_task_stop），停止扫描不会停掉翻译 worker；target 缺省 = all（全部停）。
        停止不是删除：pending / 断点 / 写回待办全部保留，恢复后可继续消费。
        """
        try:
            _target = str((data or {}).get("target") or "all").strip().lower()
        except Exception:
            _target = "all"
        _set = self._request_task_stop(_target)
        if _target in ("translate", "all", "", "*") and "translate" in _set:
            # 关断 LLM 连接 —— in-flight 请求立即抛错（仅停翻译/全部停时做；停扫描不再误伤翻译）
            try:
                if self._llm is not None and hasattr(self._llm, "close"):
                    self._llm.close()
                    logger.info("已强制关闭 LLM HTTP 连接，翻译停止立即生效")
            except Exception as _e:
                logger.debug(f"停止时关闭 LLM 连接异常: {_e}")
            finally:
                self._llm = None
                self._startup_background_started = False
        if "scan" in _set:
            self._scan_status["paused"] = False
            try:
                self._save_state()   # 立即保存当前 cursor，下次启动可续扫
            except Exception:
                pass
        _names = "、".join(_set) or "（无匹配目标）"
        self._push_log("INFO", f"已请求终止：{_names}（各自的 pending/断点/待写回全部保留，可随时继续）")
        return {"success": True,
                "message": f"已请求终止：{_names}（互不影响其它任务；pending 与断点保留，可随时继续）"}

    def _request_task_stop(self, task: str = "all") -> list:
        """按任务设置独立停止位 —— scan / translate / writeback / pool / probe / all。
        Worker 只读自己的停止位，互不污染；「all」额外置全局位（Webhook 事件管线沿用旧的全局位）。
        :return: 实际置位的任务名列表"""
        _t = str(task or "all").strip().lower()
        _flags = {"scan": "_scan_stop", "translate": "_tx_stop", "writeback": "_wb_stop",
                  "pool": "_pool_stop", "probe": "_probe_stop"}
        _targets = list(_flags) if _t in ("all", "", "*", "stop") else ([_t] if _t in _flags else [])
        _set = []
        for _k in _targets:
            try:
                setattr(self, _flags[_k], True)
                _set.append(_k)
            except Exception:
                pass
        if _t in ("all", "", "*", "stop"):
            self._stop_requested = True   # 旧全局位：仅 Webhook 事件管线还在用（「停止」= 全部停）
        try:
            self._tx_wake()
            self._wb_wake()
        except Exception:
            pass
        try:
            self._set_task_paused(_t, False)
        except Exception:
            pass
        return _set

    def _api_task_pause(self, data: Optional[dict] = None):
        """暂停任务（target=scan/pool/translate/all，缺省 all）。进度保留，可随时「继续」。
        纳入 AI 翻译 —— 「暂停」= 不再发起新的 LLM 请求（当前一批跑完即停，词条留在库中）。"""
        _t = self._set_task_paused(str((data or {}).get("target") or "all"), True)
        if not _t:
            return {"success": False, "message": "无可暂停的任务（target=scan/pool/translate/all）"}
        _name_map = {"scan": "NFO 扫描", "pool": "拉取人名", "translate": "AI 翻译"}
        _names = "、".join(_name_map.get(x, x) for x in _t)
        _note = "（当前一批完成后生效，词条保留可续）" if "translate" in _t else "（进度保留，点「继续」从断点接着跑）"
        self._push_log("INFO", f"已请求暂停：{_names}{_note}")
        return {"success": True, "message": f"已暂停：{_names}{_note}"}

    def _api_task_resume(self, data: Optional[dict] = None):
        """继续任务（target=scan/pool/translate/all，缺省 all）。"""
        _t = self._set_task_paused(str((data or {}).get("target") or "all"), False)
        if not _t:
            return {"success": False, "message": "无可恢复的任务（target=scan/pool/translate/all）"}
        if "translate" in _t:
            try:
                self._tx_wake()   # 立即唤醒翻译 worker 恢复消费（否则最多等 1 秒轮询）
            except Exception:
                pass
        _name_map = {"scan": "NFO 扫描", "pool": "拉取人名", "translate": "AI 翻译"}
        _names = "、".join(_name_map.get(x, x) for x in _t)
        self._push_log("INFO", f"已继续：{_names}")
        return {"success": True, "message": f"已继续：{_names}"}


    def _api_status(self):
        wh_total = self._webhook_received
        wh_processed = self._webhook_processed
        wh_failed = self._webhook_failed
        wh_success_rate = round(wh_processed / max(wh_total, 1) * 100, 1) if wh_total > 0 else 0.0

        wh_last_time = None
        if self._webhook_last_time:
            wh_last_time = datetime.fromtimestamp(self._webhook_last_time).strftime("%Y-%m-%d %H:%M:%S")

        scan_status = self._build_scan_status()
        # 人名池统计（替代原 cache_hit_rate —— 该字段恒为 0 已无意义）
        try:
            _nowts = time.time()
            _pc = getattr(self, "_pool_total_cache", None)
            if _pc and _nowts - float(_pc[0]) < 60:
                pool_total = int(_pc[1])
            else:
                dbm = getattr(self, "_name_map_db", None) or NameMapDb()
                pool_total = int(dbm.count_map(plugin_id=self.__class__.__name__) or 0)
                self._pool_total_cache = (_nowts, pool_total)
        except Exception:
            pool_total = 0
        try:
            _pcs = getattr(self, "_pool_counts_cache", None)
            if _pcs and time.time() - float(_pcs[0]) < 20:
                pool_counts = dict(_pcs[1])
            else:
                dbm2 = getattr(self, "_name_map_db", None) or NameMapDb()
                pool_counts = dbm2.count_pool_status(plugin_id=self.__class__.__name__) or {}
                self._pool_counts_cache = (time.time(), dict(pool_counts))
        except Exception:
            pool_counts = {"total": 0, "pending": 0, "translated": 0, "synced": 0, "failed": 0}
        _pool_hits = int(getattr(self, "_pool_hits", 0) or 0)
        _llm_terms = int(getattr(self, "_llm_terms", 0) or 0)
        _hit_total = _pool_hits + _llm_terms
        pool_hit_rate = round(_pool_hits / _hit_total * 100, 1) if _hit_total > 0 else 0.0

        try:
            _svcs = self._get_all_emby_services()
            _svc_count = len(_svcs)
            _selected = [str(x).strip() for x in (self._libraries or []) if str(x).strip()]
            _sel_count = len(_selected)
            if _svc_count:
                if _sel_count:
                    _emby_ok = True
                    _emby_hint = f"正常 · 已选 {_sel_count} 个分库"
                else:
                    _emby_ok = False
                    _emby_hint = "服务在线，未选择分库"
            else:
                _sel_count = 0
                _emby_ok = False
                _emby_hint = "未配置 Emby 服务"
        except Exception:
            _svc_count = 0
            _sel_count = 0
            _emby_ok = False
            _emby_hint = "异常"

        return {
            "success": True,
            "data": {
                "enabled": self._enabled,
                "is_running": self._is_running,
                "tasks": {
                    "scan": self._task_running("scan"),
                    "translate": self._task_running("translate"),
                    "writeback": self._task_running("writeback"),
                    "pool": self._task_running("pool"),
                    "probe": self._task_running("probe"),
                },
                "task_state": self._task_state(),
                "translate_status": dict(getattr(self, "_translate_status", None) or {}),
                "writeback_status": dict(getattr(self, "_writeback_status", None) or {}),
                "probe_status": dict(getattr(self, "_probe_status", None) or {}),
                "auto_writeback": self._wb_writeback_enabled(),
                "pool_status": dict(getattr(self, "_pool_status", None) or {}),
                "pool_counts": pool_counts,
                "tx": self._tx_state_snapshot(pool_counts),
                "llm_gate": {
                    "min_interval": float(getattr(self, "_llm_min_interval", 0) or 0),
                    "error_kind": str(getattr(self._llm, "last_error_kind", "") or "") if self._llm is not None else "",
                    "limited_until": float(getattr(self._llm, "rate_limited_until", 0) or 0) if self._llm is not None else 0.0,
                },
                "nfo_preview": bool(getattr(self, "_nfo_preview", False)),
                "nfo_resume": self._nfo_resume_state(),
                "scan_mode": self._scan_mode,
                "scan_status": scan_status,
                "pool_total": pool_total,
                # v4.6.104（LIB-009）：库数据版本号 —— 前端据此决定「有更新才重拉左侧列表」，
                # 没写库就完全不拉（用户诉求：没数据更新干嘛要刷新）。
                "items_rev": db_rev(),
                "pool_hit_rate": pool_hit_rate,
                "failed_translations": {
                    "terms": sorted(getattr(self, "_failed_terms", None) or ()),
                    "detail": dict(getattr(self, "_failed_terms_detail", None) or {}),
                },
                "emby": {
                    "ok": _emby_ok,
                    "hint": _emby_hint,
                    "server_count": _svc_count,
                    "selected_count": _sel_count,   # 已勾选的分库数（用户所见即所配）
                },
                "webhook": {
                    "enabled": bool(getattr(self, "_webhook_enabled", False)),
                    # pending_count = 待配置（需用户处理）事件数，与 /webhook/pending 口径一致
                    "pending_count": len(getattr(self, "_webhook_pending_config", None) or {}),
                    # held_count = 挂起事件总数（含等待/重试调度队列），关闭 Webhook 时冻结队列展示用
                    "held_count": (len(getattr(self, "_webhook_schedule", None) or {})
                                   + len(getattr(self, "_webhook_pending_config", None) or {})),
                    "scheduled_count": len(getattr(self, "_webhook_schedule", None) or {}),
                    "total_received": wh_total,
                    "processed": wh_processed,
                    "failed": wh_failed,
                    "success_rate": wh_success_rate,
                    "last_time": wh_last_time,
                    "last_event": self._webhook_last_event,
                    "last_error": self._webhook_error,
                },
                "deps": {
                    "llm_ready": self._llm is not None,
                    "zhconv_ready": bool(HAS_ZHCONV),
                    "db_ready": getattr(self, "_people_db", None) is not None,
                }
            }
        }



    @staticmethod
    def _extract_param(kwargs: dict, *keys) -> str:
        """从多种参数格式中提取值"""
        for key in keys:
            if key in kwargs:
                return str(kwargs[key] or "")
        if kwargs.get("data"):
            data = kwargs["data"]
            if isinstance(data, dict):
                for key in keys:
                    if key in data:
                        return str(data[key] or "")
            elif isinstance(data, str):
                return data
        if kwargs.get("form"):
            form = kwargs["form"]
            if isinstance(form, dict):
                for key in keys:
                    if key in form:
                        return str(form[key] or "")
        return ""

    # ============================================================
    # 初始化 / 配置加载
    # ============================================================
    def init_plugin(self, config: dict = None):
        is_first_init = not getattr(self, "_runtime_initialized", False)
        if is_first_init:
            self._ms_helper = None
            self._llm = None
            self._startup_background_started = False
            self._stop_requested = False
            self._scan_stop = False
            self._tx_stop = False
            self._wb_stop = False
            self._pool_stop = False
            self._probe_stop = False
            self._scan_paused = False
            self._pool_paused = False
            self._live_log = []
            self._is_running = False
            self._scan_running = False
            self._translate_running = False
            self._writeback_running = False
            self._pool_running = False
            self._probe_running = False
            self._tx_thread = None
            self._tx_event = threading.Event()
            self._tx_stop = False
            self._tx_hard_until = 0.0
            self._tx_hard_kind = ""
            self._tx_job_reset_stats()
            self._tx_job_started = 0.0
            self._tx_autosync_res = None
            self._tx_batch = 30
            self._rate_limited_until = 0.0
            self._rl_strikes = 0
            self._tx_requested = False
            self._tx_batch = 30
            self._tx_batch_max = 30
            self._llm_max_rpm = 0
            self._llm_thinking_off = True
            self._llm_thinking_params = ""
            self._pool_lu_cache = None
            self._pool_lu_ts = 0.0
            self._wb_thread = None
            self._wb_event = threading.Event()
            self._wb_stop = False
            self.__class__._wb_cursor = 0
            self._writeback_db = None
            self._pool_thread = None
            self._pool_pulling = False
            self._pool_status = {"running": False, "total": 0, "done": 0, "current": "",
                                 "current_server": "", "current_person": "", "server_total": 0,
                                 "server_done": 0, "servers": [], "collect_total": 0, "collect_done": 0}
            self._pool_sync_after_translate = False
            self._pool_auto_sync = False
            self._pool_auto_translate = False
            self._pool_translation_enabled = True
            self._pool_tmdb_fill = True
            self._pool_tmdb_credits = False
            self._auto_translate_webhook = False
            self._auto_translate_scan = False
            self._webhook_enabled = False
            self._translate_person = True
            self._nfo_path_mappings = []
            self._tx_target_scope = "both"
            self._tx_source = ""
            self._tx_scope_items = set()
            self._tx_only_terms = set()
            self._enabled = False
            self._prompt_template = ""
            self._translate_all = False
            self._translate_role = True
            self._translate_actor = True
            self._translate_director = False
            self._translate_writer = False
            self._translate_producer = False
            self._translate_guest_star = False
            self._ja_name_policy = "convert"
            self._scan_mode = "nfo"
            self._libraries = []
            self._nfo_roots = []
            self._nfo_recursive = True
            self._nfo_include_episodes = False
            self._nfo_backup = False   # 类默认口径：兜底绝不默认写 .bak（真正取值来自已保存配置）
            self._nfo_dry_run = False
            self._nfo_episode_sync = True
            self._nfo_episode_overwrite = False
            self._nfo_preview = False
            self._nfo_dead_grace_hours = 24
            self._max_people_per_batch = 30
            self._max_guest_per_episode = 5
            self._actor_limit = 10
            self._guest_limit = 10
            self._director_limit = 3
            self._writer_limit = 3
            self._movie_actor_limit = 10
            self._movie_guest_limit = 10
            self._movie_director_limit = 3
            self._movie_writer_limit = 3
            self._tv_actor_limit = 10
            self._ep_actor_limit = 10
            self._tv_guest_limit = 10
            self._tv_director_limit = 3
            self._tv_writer_limit = 3
            self._overwrite_chinese = False
            self._lock_cast = False
            self._emby_name_sync = True
            self._run_clear_cache = False
            self._llm_base_url = ""
            self._llm_api_key = ""
            self._llm_model = ""
            self._llm_timeout = 120
            self._llm_mode = "system"
            self._use_proxy = constants.DEFAULT_USE_PROXY
            self._llm_verify_ssl = constants.DEFAULT_LLM_VERIFY_SSL
            self._translate_batching = "per_title"
            self._llm_min_interval = constants.DEFAULT_LLM_MIN_INTERVAL
            self._webhook_delay = 60
            self._notify_on_complete = False
            self._series_max_workers = constants.DEFAULT_SERIES_MAX_WORKERS
            self._series_ingest_all = constants.DEFAULT_SERIES_INGEST_ALL
            self._series_executor = None
            self._series_executor_workers = 0
            self._enable_ai = True
            self._schedule_enabled = False
            self._schedule_interval_hours = 24
            self._probe_enabled = False
            self._probe_interval_min = 60
            self._sync_direction = "s2e"
            self._pool_fetch_scope = ""         # "" → dump 按 constants.DEFAULT_POOL_FETCH_SCOPE 兜底
            self._pool_keep_unknown = constants.DEFAULT_POOL_KEEP_UNKNOWN
            self._auto_writeback = True
            self._tx_paused = False
            self._tx_pause_logged = False
            self._legacy_mapping = ("", "")
            self._last_run_time = None
            self._last_save_time = None
            self._scan_thread = None
            self._task_threads = {}
            self._wb_job_thread = None
            self._tx_job_thread = None
            self._stop_event = threading.Event()
            # 线程锁也必须实例化（否则多实例共享同一把锁）
            self._state_lock = threading.Lock()
            self._scan_lock = threading.Lock()
            self._scan_cursor = None
            self._nfo_file_sigs: Dict[str, str] = {}
            self._nfo_sigs_cfg: str = ""
            self._probe_thread = None
            self._probe_stop = False
            self._probe_daemon_stop = None
            self._probe_last_run = 0.0      # 上次探测轮时间戳（daemon 间隔判断）
            self._probe_last_deep = 0.0     # 上次深查时间戳（≥24h 强制再来一次深查）
            self._probe_counts: Dict[str, int] = {}   # 上次轻查计数 {skey:lib_id:type → n}
            self._probe_seen: Dict[str, float] = {}   # 已探测尝试的 nfo 路径 → 时间戳（防重复触发）

            # 进度追踪
            self._scan_status = {
                "running": False,
                "paused": False,
                "total": 0,
                "done": 0,
                "current_title": "",
                "current_library": "",
                "servers_total": 0,
                "servers_done": 0,
            }
            self._progress_step_start_time = time.time()
            self._translate_status = {"running": False, "total": 0, "done": 0,
                                      "failed": 0, "current": "", "phase": "translate"}
            self._writeback_status = {"running": False, "total": 0, "done": 0,
                                      "failed": 0, "current": "", "phase": "writeback"}
            # 探测库独立状态（UI-004）：不再复用 _scan_status，避免「扫描中」假状态
            self._probe_status = {"running": False, "current_title": "", "total": 0, "done": 0}

            self._runtime_initialized = True

            self._webhook_received = 0
            self._webhook_processed = 0
            self._webhook_failed = 0
            self._webhook_last_time = None
            self._webhook_last_event = ""
            self._webhook_error = ""
            self._webhook_schedule: Dict[str, Dict[str, Any]] = {}
            self._webhook_worker_thread: Optional[threading.Thread] = None
            self._webhook_worker_event = threading.Event()
            self._webhook_lock = threading.Lock()
            self._failed_terms = set(getattr(self, "_failed_terms", None) or ())
            self._failed_terms_detail = dict(getattr(self, "_failed_terms_detail", None) or {})
            self._pool_hits = int(getattr(self, "_pool_hits", 0) or 0)
            self._llm_terms = int(getattr(self, "_llm_terms", 0) or 0)
            self._webhook_events: List[dict] = list(getattr(self, "_webhook_events", None) or [])
            self._webhook_received_batch: Dict[str, List[dict]] = {}
            self._webhook_received_order: List[str] = []
            self._webhook_received_timer: Optional[threading.Timer] = None
            self._webhook_retry_map: Dict[str, int] = {}
            self._webhook_retry_first: Dict[str, float] = {}
            self._emby_itemid_cache: Dict[str, str] = {}
            self._webhook_pending_config: Dict[str, dict] = {}
            self._webhook_pending_notify_count: int = 0
            self._webhook_pending_timer: Optional[threading.Timer] = None
            self._notification_queue: Dict[str, List[Dict[str, Any]]] = {}
            self._notification_flush_timer: Optional[threading.Timer] = None
            self._notification_lock = threading.Lock()

            # 状态持久化路径
            self._state_file = ""

            self._install_log_bridge()

            self._people_db = PeopleDb()
            try:
                PeopleDb.ensure_table()
            except Exception as e:
                logger.warning(f"初始化翻译记录数据库失败: {e}")

            try:
                NameMapDb.ensure_table()
            except Exception as e:
                logger.warning(f"初始化人名池数据库失败: {e}")
            # v4.6.105（LIB-011 · 人名池「批量翻译」一轮 0 条的根因）：启动即建人名池句柄。
            # 此前这里只建了 _people_db，_name_map_db 一直是 None，要等「扫描 / 拉取人名 / 重拉」
            # 等路径惰性赋值（各处都写 `getattr(self, "_name_map_db", None) or NameMapDb()`）。
            # 于是插件重启/重载后，若用户**直接**去「人名池」点「批量翻译」：
            #   池页/统计走 `or NameMapDb()` 正常显示「待翻译 89」，
            #   但翻译 worker 收词时 `nm = getattr(self, "_name_map_db", None)` 拿到 None →
            #   池收集门 `nm is not None` 直接失败 → 本轮 0 条、池 pending 一直不动
            #   （日志：「池=False（池未收：源不含 pool / 未开池翻译 / 范围不含第一排）」）。
            self._name_map_db = NameMapDb()

            self._load_state()
            try:
                _rn = self._rebuild_missing_events_from_db()
                if _rn:
                    logger.info(f"[Webhook] 已从库记录重建 {_rn} 条「失效/待恢复」事件行")
            except Exception:
                pass
            try:
                self._start_maintenance()
            except Exception:
                pass
            try:
                self._start_schedule_daemon()
            except Exception:
                pass
            try:
                self._start_probe_daemon()
            except Exception:
                pass
            try:
                self._start_translate_worker()
            except Exception:
                pass
            try:
                self._start_writeback_worker()
            except Exception:
                pass

        if config:
            self._load_config(config)

        try:
            self._resume_webhook_queue()
        except Exception:
            pass

        # ============================================================
        # ============================================================
        if not self._enabled and self._is_running:
            logger.info("插件已禁用，正在停止扫描...")
            # 调用 stop_service 强制停止扫描线程（包括关闭 LLM 连接）
            self.stop_service()

        # ============================================================
        # 阶段 3: 扫描运行中时直接 return（不重建运行时状态，配置下次生效）
        # ============================================================
        if self._is_running:
            logger.info("扫描正在运行，配置将在下次扫描时生效")
            return


        # ============================================================
        # 阶段 4: 扫描未运行时才能执行的操作
        # ============================================================
        if self._run_clear_cache:
            logger.info("检测到「清空缓存」开关")
            self._run_clear_cache = False
            self.update_config(self._dump_config())
            self.clear_cache()

        # ============================================================
        # ============================================================
        if self._enabled and not self._startup_background_started:
            self._startup_background_started = True
            threading.Thread(target=self._startup, daemon=True).start()

    def _load_config(self, config: dict):
        self._enabled = constants.safe_bool(config.get(constants.CFG_ENABLED), False)
        # v4.6.109（LIB-017）：旧版默认提示词写着「无法确认或无需翻译时保留原文」——
        # 模型据此把纯假名/罗马音人名**原样返回**，池里永远停在「待翻译」。
        # 若用户**从未改过**（与旧默认逐字相同）就自动升到新版；用户自己写过的模板一律不动。
        _pt = str(config.get(constants.CFG_PROMPT_TEMPLATE) or "").strip()
        if (not _pt) or _pt == constants.DEFAULT_PROMPT_LEGACY.strip():
            _pt = constants.DEFAULT_PROMPT
        self._prompt_template = _pt
        self._translate_all = constants.safe_bool(config.get(constants.CFG_TRANSLATE_ALL), False)
        self._translate_role = constants.safe_bool(config.get(constants.CFG_TRANSLATE_ROLE), True)
        self._translate_actor = constants.safe_bool(config.get(constants.CFG_TRANSLATE_ACTOR), True)
        self._translate_director = constants.safe_bool(config.get(constants.CFG_TRANSLATE_DIRECTOR), False)
        self._translate_writer = constants.safe_bool(config.get(constants.CFG_TRANSLATE_WRITER), False)
        self._translate_producer = constants.safe_bool(config.get(constants.CFG_TRANSLATE_PRODUCER), False)
        self._translate_guest_star = constants.safe_bool(config.get(constants.CFG_TRANSLATE_GUEST_STAR), False)
        _jp = str(config.get(constants.CFG_JA_NAME_POLICY, "convert")).strip() or "convert"
        if _jp != "convert":
            self._ja_name_policy = "convert"
            logger.warning("[NFO] ja_name_policy 旧值 '%s' 已迁移为 convert（自动判断：纯汉字繁转简、含假名送 LLM）——该开关已并入「翻译演员」自动判断", _jp)
        else:
            self._ja_name_policy = "convert"
        self._scan_mode = str(config.get(constants.CFG_SCAN_MODE, "nfo")).strip() or "nfo"
        if self._scan_mode not in ("api", "nfo"):
            self._scan_mode = "nfo"
        self._scan_mode = "nfo"
        self._libraries = [str(x).strip() for x in (config.get(constants.CFG_LIBRARIES, []) or []) if str(x).strip()]
        self._nfo_roots = self._norm_nfo_roots(config.get(constants.CFG_NFO_ROOTS, []))
        self._lib_cache = []
        self._lib_cache_ts = 0.0
        self._nfo_recursive = constants.safe_bool(config.get(constants.CFG_NFO_RECURSIVE), True)
        self._nfo_include_episodes = constants.safe_bool(config.get(constants.CFG_NFO_INCLUDE_EPISODES), False)
        self._nfo_backup = constants.safe_bool(config.get(constants.CFG_NFO_BACKUP),
                                              constants.DEFAULT_NFO_BACKUP)
        self._nfo_dry_run = constants.safe_bool(config.get(constants.CFG_NFO_DRY_RUN), False)
        self._nfo_episode_sync = constants.safe_bool(config.get(constants.CFG_NFO_EPISODE_SYNC), True)
        self._nfo_episode_overwrite = constants.safe_bool(config.get(constants.CFG_NFO_EPISODE_OVERWRITE), False)
        self._nfo_preview = constants.safe_bool(config.get(constants.CFG_NFO_PREVIEW), False)
        self._nfo_dead_grace_hours = constants.safe_int(
            config.get(constants.CFG_NFO_DEAD_GRACE_HOURS), constants.DEFAULT_NFO_DEAD_GRACE_HOURS,
            min_value=0, max_value=720)   # v4.6.64：与 UI 边界统一（0~720）

        # v4.6.61（P1-SET-03）：「全部类型」= 运行期覆盖，**不再回写子开关** ——
        # 此前加载/保存时把 role/actor/director/... 全部强制置 True，用户关掉「全部类型」后
        # 原选择已被永久改写、无法恢复；现覆盖只在 _collect_trans_types 运行期生效，
        # 子开关保持用户原值，关闭「全部类型」即恢复原选择（UI 上同步显示覆盖提示）。
        self._max_people_per_batch = constants.safe_int(
            config.get(constants.CFG_MAX_PEOPLE_PER_BATCH), constants.DEFAULT_BATCH_SIZE,
            min_value=1, max_value=200)   # v4.6.64：与批次上限一致 1~200
        self._tx_batch_max = constants.safe_int(
            self._max_people_per_batch or constants.DEFAULT_BATCH_SIZE, constants.DEFAULT_BATCH_SIZE,
            min_value=1, max_value=200)
        self._tx_batch = self._tx_batch_max
        self._tx_batch_safe = self._tx_batch_max   # v4.6.112（GH#3-6）
        self._max_guest_per_episode = constants.safe_int(
            config.get(constants.CFG_MAX_GUEST_PER_EPISODE), 5, min_value=0)
        if constants.CFG_ACTOR_LIMIT in config:
            self._actor_limit = constants.safe_int(config.get(constants.CFG_ACTOR_LIMIT), 0, min_value=0)
        else:
            self._actor_limit = 10
        if constants.CFG_GUEST_LIMIT in config:
            self._guest_limit = constants.safe_int(config.get(constants.CFG_GUEST_LIMIT), 0, min_value=0)
        else:
            self._guest_limit = 10
        if constants.CFG_DIRECTOR_LIMIT in config:
            self._director_limit = constants.safe_int(config.get(constants.CFG_DIRECTOR_LIMIT), 0, min_value=0)
        else:
            self._director_limit = 3
        if constants.CFG_WRITER_LIMIT in config:
            self._writer_limit = constants.safe_int(config.get(constants.CFG_WRITER_LIMIT), 0, min_value=0)
        else:
            self._writer_limit = 3


        def _lim_or_default(cfg_key: str, default: int) -> int:
            if cfg_key in config:
                return constants.safe_int(config.get(cfg_key), 0, min_value=0)
            return int(default)

        _old_actor = self._actor_limit if self._actor_limit else 10
        _old_guest = self._guest_limit if self._guest_limit else 10
        _old_director = self._director_limit if self._director_limit else 3
        _old_writer = self._writer_limit if self._writer_limit else 3
        self._movie_actor_limit = _lim_or_default(constants.CFG_MOVIE_ACTOR_LIMIT, _old_actor)
        self._ep_actor_limit = _lim_or_default(constants.CFG_EP_ACTOR_LIMIT, _old_actor)
        self._tv_actor_limit = _lim_or_default(constants.CFG_TV_ACTOR_LIMIT, 10)
        self._movie_guest_limit = _lim_or_default(constants.CFG_MOVIE_GUEST_LIMIT, _old_guest)
        self._tv_guest_limit = _lim_or_default(constants.CFG_TV_GUEST_LIMIT, _old_guest)
        self._movie_director_limit = _lim_or_default(constants.CFG_MOVIE_DIRECTOR_LIMIT, _old_director)
        self._tv_director_limit = _lim_or_default(constants.CFG_TV_DIRECTOR_LIMIT, _old_director)
        self._movie_writer_limit = _lim_or_default(constants.CFG_MOVIE_WRITER_LIMIT, _old_writer)
        self._tv_writer_limit = _lim_or_default(constants.CFG_TV_WRITER_LIMIT, _old_writer)

        # v4.6.48 三段式最简：人数上限合并为「一套」。
        # 首次升级（无迁移标记）→ 取原「电影/剧/单集」三套的最大值回写全局键，并打标记；
        # 此后以全局键（actor_limit 等）为准，旧三套键统一为同一值、仅作兼容不再参与判定。
        self._limits_unified = constants.safe_bool(config.get(constants.CFG_LIMITS_UNIFIED), False)
        if not self._limits_unified:
            self._actor_limit = max(self._actor_limit, self._movie_actor_limit,
                                    self._tv_actor_limit, self._ep_actor_limit)
            self._guest_limit = max(self._guest_limit, self._movie_guest_limit, self._tv_guest_limit)
            self._director_limit = max(self._director_limit, self._movie_director_limit,
                                       self._tv_director_limit)
            self._writer_limit = max(self._writer_limit, self._movie_writer_limit,
                                     self._tv_writer_limit)
            self._limits_unified = True
        self._movie_actor_limit = self._ep_actor_limit = self._tv_actor_limit = self._actor_limit
        self._movie_guest_limit = self._tv_guest_limit = self._guest_limit
        self._movie_director_limit = self._tv_director_limit = self._director_limit
        self._movie_writer_limit = self._tv_writer_limit = self._writer_limit

        self._enable_ai = constants.safe_bool(config.get(constants.CFG_ENABLE_AI), True)
        self._schedule_enabled = constants.safe_bool(config.get(constants.CFG_SCHEDULE_ENABLED), False)
        self._schedule_interval_hours = constants.safe_int(
            config.get(constants.CFG_SCHEDULE_INTERVAL_HOURS), 24, min_value=1, max_value=720)
        self._probe_enabled = constants.safe_bool(config.get(constants.CFG_PROBE_ENABLED), False)
        self._probe_interval_min = constants.safe_int(
            config.get(constants.CFG_PROBE_INTERVAL_MINUTES), 60, min_value=10, max_value=1440)
        _sd = str(config.get(constants.CFG_SYNC_DIRECTION, "") or "").strip().lower()
        self._sync_direction = _sd if _sd in constants.SYNC_DIRECTIONS else "s2e"
        self._overwrite_chinese = constants.safe_bool(config.get(constants.CFG_OVERWRITE_CHINESE), False)
        self._lock_cast = constants.safe_bool(config.get(constants.CFG_LOCK_CAST), False)
        self._emby_name_sync = True
        self._run_clear_cache = constants.safe_bool(config.get(constants.CFG_RUN_CLEAR_CACHE), False)
        self._llm_base_url = str(config.get(constants.CFG_LLM_BASE_URL, ""))
        self._llm_api_key = str(config.get(constants.CFG_LLM_API_KEY, ""))
        self._llm_model = str(config.get(constants.CFG_LLM_MODEL, ""))
        self._llm_timeout = constants.safe_int(
            config.get(constants.CFG_LLM_TIMEOUT), constants.DEFAULT_LLM_TIMEOUT, min_value=1, max_value=3600)
        self._llm_mode = str(config.get(constants.CFG_LLM_MODE, "system")).strip() or "system"
        self._llm_verify_ssl = constants.safe_bool(config.get(constants.CFG_LLM_VERIFY_SSL),
                                                   constants.DEFAULT_LLM_VERIFY_SSL)
        self._translate_batching = str(config.get(constants.CFG_TRANSLATE_BATCHING, "per_title") or "per_title").strip() or "per_title"
        self._use_proxy = constants.safe_bool(config.get(constants.CFG_USE_PROXY), constants.DEFAULT_USE_PROXY)
        self._webhook_delay = constants.safe_int(
            config.get(constants.CFG_WEBHOOK_DELAY), constants.DEFAULT_WEBHOOK_DELAY, min_value=0, max_value=3600)
        self._notify_on_complete = constants.safe_bool(config.get(constants.CFG_NOTIFY_ON_COMPLETE), False)
        self._series_max_workers = constants.safe_int(
            config.get(constants.CFG_SERIES_MAX_WORKERS), constants.DEFAULT_SERIES_MAX_WORKERS,
            min_value=1, max_value=4)
        self._series_ingest_all = constants.safe_bool(config.get(constants.CFG_SERIES_INGEST_ALL),
                                                      constants.DEFAULT_SERIES_INGEST_ALL)
        self._pool_fetch_scope = str(config.get(constants.CFG_POOL_FETCH_SCOPE, "") or "").strip() \
            or constants.DEFAULT_POOL_FETCH_SCOPE
        self._pool_auto_translate = constants.safe_bool(config.get(constants.CFG_POOL_AUTO_TRANSLATE),
                                                        constants.DEFAULT_POOL_AUTO_TRANSLATE)
        self._pool_auto_sync = constants.safe_bool(config.get(constants.CFG_POOL_AUTO_SYNC),
                                                   constants.DEFAULT_POOL_AUTO_SYNC)
        self._pool_keep_unknown = constants.safe_bool(config.get(constants.CFG_POOL_KEEP_UNKNOWN),
                                                      constants.DEFAULT_POOL_KEEP_UNKNOWN)
        # 人名池「拉取类型」独立配置（v4.6.48）；缺省 → 默认「演员」
        # 「演员」勾选即含声优 → 存储里不再保留 VoiceActor（由 _pool_fetch_trans_types 展开）
        _pft = config.get(constants.CFG_POOL_FETCH_TYPES, None)
        if isinstance(_pft, str):
            _pft = [x.strip() for x in _pft.replace("，", ",").split(",") if x.strip()]
        elif not isinstance(_pft, (list, tuple)):
            _pft = []
        self._pool_fetch_types = [str(x).strip() for x in _pft
                                  if str(x).strip() and str(x).strip() != "VoiceActor"] \
            or list(constants.DEFAULT_POOL_FETCH_TYPES)
        self._pool_translation_enabled = constants.safe_bool(config.get(constants.CFG_POOL_TRANSLATE_ENABLED),
                                                             constants.DEFAULT_POOL_TRANSLATE_ENABLED)
        self._pool_tmdb_fill = constants.safe_bool(config.get(constants.CFG_POOL_TMDB_FILL),
                                                   constants.DEFAULT_POOL_TMDB_FILL)
        self._pool_tmdb_credits = constants.safe_bool(config.get(constants.CFG_POOL_TMDB_CREDITS),
                                                      constants.DEFAULT_POOL_TMDB_CREDITS)
        self._auto_translate_webhook = constants.safe_bool(config.get(constants.CFG_AUTO_TRANSLATE_WEBHOOK),
                                                           constants.DEFAULT_AUTO_TRANSLATE_WEBHOOK)
        self._auto_translate_scan = constants.safe_bool(config.get(constants.CFG_AUTO_TRANSLATE_SCAN),
                                                        constants.DEFAULT_AUTO_TRANSLATE_SCAN)
        if constants.CFG_WEBHOOK_ENABLED in config:
            self._webhook_enabled = constants.safe_bool(config.get(constants.CFG_WEBHOOK_ENABLED), False)
        else:
            _legacy_cfg = bool(config) and (constants.CFG_ENABLED in config
                                            or constants.CFG_PROMPT_TEMPLATE in config
                                            or constants.CFG_SCAN_MODE in config
                                            or bool(config.get(constants.CFG_LIBRARIES, []))
                                            or bool(config.get(constants.CFG_AUTO_TRANSLATE_WEBHOOK, False)))
            self._webhook_enabled = bool(_legacy_cfg)
        self._translate_person = constants.safe_bool(config.get(constants.CFG_TRANSLATE_PERSON),
                                                     constants.DEFAULT_TRANSLATE_PERSON)
        self._nfo_path_mappings = [m for m in
                                   constants.safe_json_list(config.get(constants.CFG_NFO_PATH_MAPPINGS), [])
                                   if isinstance(m, dict)]
        _lf = str(config.get("nfo_replace_from") or "").strip()
        _lt = str(config.get("nfo_replace_to") or "").strip()
        if _lf and not self._nfo_path_mappings:
            self._legacy_mapping = (_lf, _lt)
            if not getattr(self, "_legacy_mapping_logged", False):
                self._legacy_mapping_logged = True
                logger.info(f"[Config] 检测到旧版全局路径映射（{_lf} → {_lt}），将在探测到 Emby 服务器后迁移为服务器级 mapping")
        else:
            self._legacy_mapping = ("", "")
        self._llm_min_interval = constants.safe_float(
            config.get(constants.CFG_LLM_MIN_INTERVAL), constants.DEFAULT_LLM_MIN_INTERVAL,
            min_value=0.0, max_value=600.0)   # v4.6.64：与 UI 边界统一（0~600）
        # v4.6.61（P2-3）：TPM 令牌预算（每分钟估算令牌，0 = 不限制）
        self._llm_tpm_budget = constants.safe_int(
            config.get(constants.CFG_LLM_TPM_BUDGET), constants.DEFAULT_LLM_TPM_BUDGET, min_value=0)
        # v4.6.64（P2-11）：`llm_max_rpm` 为**历史兼容字段** —— 限速已统一为「请求间隔
        # (llm_min_interval) + TPM 预算 (llm_tpm_budget)」两个概念，RPM 恒为 0（不启用），
        # 避免同时存在两套容易误解的限速概念。
        self._llm_max_rpm = 0
        self._llm_thinking_off = constants.safe_bool(config.get(constants.CFG_LLM_THINKING_OFF),
                                                     constants.DEFAULT_LLM_THINKING_OFF)
        self._llm_thinking_params = str(config.get(constants.CFG_LLM_THINKING_PARAMS,
                                                   constants.DEFAULT_LLM_THINKING_PARAMS) or "").strip()
        if constants.CFG_AUTO_WRITEBACK in config:
            self._auto_writeback = constants.safe_bool(config.get(constants.CFG_AUTO_WRITEBACK), True)
        else:
            self._auto_writeback = not bool(getattr(self, "_nfo_preview", False))

    def _dump_config(self) -> dict:
        # v4.6.61（P1-SET-03）：不再把「全部类型」强制回写进子开关（见 _load_config 注释）——
        # 子开关按用户原值落盘，运行期由 _collect_trans_types 用 _translate_all 覆盖。
        return {
            constants.CFG_ENABLED: self._enabled,
            constants.CFG_PROMPT_TEMPLATE: self._prompt_template or constants.DEFAULT_PROMPT,
            "prompt_default": constants.DEFAULT_PROMPT,
            constants.CFG_TRANSLATE_ACTOR: self._translate_actor,
            constants.CFG_TRANSLATE_DIRECTOR: self._translate_director,
            constants.CFG_TRANSLATE_WRITER: self._translate_writer,
            constants.CFG_TRANSLATE_PRODUCER: self._translate_producer,
            constants.CFG_TRANSLATE_GUEST_STAR: self._translate_guest_star,
            constants.CFG_JA_NAME_POLICY: self._ja_name_policy,
            constants.CFG_SCAN_MODE: self._scan_mode,
            constants.CFG_LIBRARIES: self._libraries,
            constants.CFG_NFO_ROOTS: "\n".join(self._nfo_roots),
            constants.CFG_NFO_RECURSIVE: self._nfo_recursive,
            constants.CFG_NFO_INCLUDE_EPISODES: self._nfo_include_episodes,
            constants.CFG_NFO_BACKUP: self._nfo_backup,
            constants.CFG_NFO_DRY_RUN: self._nfo_dry_run,
            constants.CFG_NFO_EPISODE_SYNC: self._nfo_episode_sync,
            constants.CFG_NFO_EPISODE_OVERWRITE: self._nfo_episode_overwrite,
            constants.CFG_NFO_PREVIEW: self._nfo_preview,
            constants.CFG_NFO_DEAD_GRACE_HOURS: self._nfo_dead_grace_hours,
            constants.CFG_TRANSLATE_ALL: self._translate_all,
            constants.CFG_TRANSLATE_ROLE: self._translate_role,
            constants.CFG_MAX_PEOPLE_PER_BATCH: self._max_people_per_batch,
            constants.CFG_MAX_GUEST_PER_EPISODE: self._max_guest_per_episode,
            constants.CFG_ACTOR_LIMIT: self._actor_limit,
            constants.CFG_GUEST_LIMIT: self._guest_limit,
            constants.CFG_DIRECTOR_LIMIT: self._director_limit,
            constants.CFG_WRITER_LIMIT: self._writer_limit,
            constants.CFG_OVERWRITE_CHINESE: self._overwrite_chinese,
            constants.CFG_LOCK_CAST: self._lock_cast,
            constants.CFG_EMBY_NAME_SYNC: getattr(self, "_emby_name_sync", True),
            constants.CFG_POOL_FETCH_SCOPE: (getattr(self, "_pool_fetch_scope", "") or constants.DEFAULT_POOL_FETCH_SCOPE),
            constants.CFG_POOL_AUTO_TRANSLATE: getattr(self, "_pool_auto_translate", constants.DEFAULT_POOL_AUTO_TRANSLATE),
            constants.CFG_POOL_AUTO_SYNC: getattr(self, "_pool_auto_sync", constants.DEFAULT_POOL_AUTO_SYNC),
            constants.CFG_POOL_KEEP_UNKNOWN: getattr(self, "_pool_keep_unknown", constants.DEFAULT_POOL_KEEP_UNKNOWN),
            constants.CFG_POOL_FETCH_TYPES: list(getattr(self, "_pool_fetch_types", None)
                                                 or constants.DEFAULT_POOL_FETCH_TYPES),
            constants.CFG_LIMITS_UNIFIED: bool(getattr(self, "_limits_unified", False)),
            constants.CFG_POOL_TRANSLATE_ENABLED: getattr(self, "_pool_translation_enabled", constants.DEFAULT_POOL_TRANSLATE_ENABLED),
            constants.CFG_POOL_TMDB_FILL: getattr(self, "_pool_tmdb_fill", constants.DEFAULT_POOL_TMDB_FILL),
            constants.CFG_POOL_TMDB_CREDITS: getattr(self, "_pool_tmdb_credits", constants.DEFAULT_POOL_TMDB_CREDITS),
            constants.CFG_AUTO_TRANSLATE_WEBHOOK: getattr(self, "_auto_translate_webhook", constants.DEFAULT_AUTO_TRANSLATE_WEBHOOK),
            constants.CFG_AUTO_TRANSLATE_SCAN: getattr(self, "_auto_translate_scan", constants.DEFAULT_AUTO_TRANSLATE_SCAN),
            constants.CFG_WEBHOOK_ENABLED: getattr(self, "_webhook_enabled", constants.DEFAULT_WEBHOOK_ENABLED),
            constants.CFG_TRANSLATE_PERSON: getattr(self, "_translate_person", constants.DEFAULT_TRANSLATE_PERSON),
            constants.CFG_NFO_PATH_MAPPINGS: getattr(self, "_nfo_path_mappings", constants.DEFAULT_NFO_PATH_MAPPINGS),
            constants.CFG_LLM_MIN_INTERVAL: getattr(self, "_llm_min_interval", constants.DEFAULT_LLM_MIN_INTERVAL),
            constants.CFG_LLM_TPM_BUDGET: getattr(self, "_llm_tpm_budget", constants.DEFAULT_LLM_TPM_BUDGET),
            constants.CFG_LLM_MAX_RPM: getattr(self, "_llm_max_rpm", constants.DEFAULT_LLM_MAX_RPM),
            constants.CFG_LLM_THINKING_OFF: getattr(self, "_llm_thinking_off", constants.DEFAULT_LLM_THINKING_OFF),
            constants.CFG_LLM_THINKING_PARAMS: getattr(self, "_llm_thinking_params", constants.DEFAULT_LLM_THINKING_PARAMS),
            constants.CFG_AUTO_WRITEBACK: getattr(self, "_auto_writeback", True),
            constants.CFG_RUN_CLEAR_CACHE: self._run_clear_cache,
            constants.CFG_LLM_BASE_URL: self._llm_base_url,
            constants.CFG_LLM_API_KEY: self._llm_api_key,
            constants.CFG_LLM_MODEL: self._llm_model,
            constants.CFG_LLM_TIMEOUT: self._llm_timeout,
            constants.CFG_LLM_MODE: self._llm_mode,
            constants.CFG_USE_PROXY: self._use_proxy,
            constants.CFG_LLM_VERIFY_SSL: self._llm_verify_ssl,
            constants.CFG_TRANSLATE_BATCHING: self._translate_batching,
            constants.CFG_WEBHOOK_DELAY: self._webhook_delay,
            constants.CFG_NOTIFY_ON_COMPLETE: self._notify_on_complete,
            constants.CFG_SERIES_MAX_WORKERS: getattr(self, "_series_max_workers", constants.DEFAULT_SERIES_MAX_WORKERS),
            constants.CFG_SERIES_INGEST_ALL: getattr(self, "_series_ingest_all", constants.DEFAULT_SERIES_INGEST_ALL),
            constants.CFG_ENABLE_AI: self._enable_ai,
            constants.CFG_MOVIE_ACTOR_LIMIT: self._movie_actor_limit,
            constants.CFG_EP_ACTOR_LIMIT: self._ep_actor_limit,
            constants.CFG_TV_ACTOR_LIMIT: self._tv_actor_limit,
            constants.CFG_MOVIE_GUEST_LIMIT: self._movie_guest_limit,
            constants.CFG_TV_GUEST_LIMIT: self._tv_guest_limit,
            constants.CFG_MOVIE_DIRECTOR_LIMIT: self._movie_director_limit,
            constants.CFG_TV_DIRECTOR_LIMIT: self._tv_director_limit,
            constants.CFG_MOVIE_WRITER_LIMIT: self._movie_writer_limit,
            constants.CFG_TV_WRITER_LIMIT: self._tv_writer_limit,
            constants.CFG_SCHEDULE_ENABLED: self._schedule_enabled,
            constants.CFG_SCHEDULE_INTERVAL_HOURS: self._schedule_interval_hours,
            constants.CFG_PROBE_ENABLED: self._probe_enabled,
            constants.CFG_PROBE_INTERVAL_MINUTES: self._probe_interval_min,
            constants.CFG_SYNC_DIRECTION: self._sync_direction,
        }

    # ============================================================
    # 媒体服务器 / 媒体库
    # ============================================================
    @staticmethod
    def _get_service_url(service: ServiceInfo) -> str:
        inst = service.instance
        if not inst:
            return ''
        host = getattr(inst, '_host', None) or getattr(service, 'url', '') or ''
        if isinstance(host, str):
            host = host.strip('`').rstrip('/')
        return host

    @staticmethod
    def _get_service_api_key(service: ServiceInfo) -> str:
        inst = service.instance
        if not inst:
            return ''
        return getattr(inst, '_apikey', None) or getattr(service, 'api_key', '') or getattr(service, 'apikey', '') or ''

    @staticmethod
    def _get_service_user_id(service: ServiceInfo) -> Optional[str]:
        inst = service.instance
        if not inst:
            return None
        return getattr(inst, 'user', None)

    def _get_all_emby_services(self) -> List[ServiceInfo]:
        try:
            if self._ms_helper is None:
                self._ms_helper = MediaServerHelper()
            services = self._ms_helper.get_services()
            if isinstance(services, dict):
                services = list(services.values())
            emby_services = [s for s in services if getattr(s, 'type', '').lower() == 'emby']
            return emby_services
        except Exception as e:
            logger.error(f"获取 Emby 服务列表失败: {e}")
            return []

    def _get_server_identifier(self, service: ServiceInfo) -> str:
        name = getattr(service, 'name', '') or ''
        url = self._get_service_url(service)
        host = port = ''
        if url:
            parsed = urlparse(url)
            host = parsed.hostname or ''
            port = str(parsed.port or (8096 if parsed.scheme == 'http' else 8920))
        base = f"{name}_{host}_{port}".strip('_')
        return re.sub(r'[^a-zA-Z0-9_-]', '_', base) or "default"

    def _probe_emby_services(self):
        """启动时轻量 Emby 健康检查 —— 只读探测、不阻塞启动。

        仅做服务列举（不逐个请求库），给出 Webhook 链路可用性提示。
        """
        try:
            svcs = self._get_all_emby_services()
            if not svcs:
                logger.warning("⚠️ 未检测到 Emby 服务 —— 本地 NFO 扫描/翻译可用，但「Emby 入库自动翻译（Webhook）」不可用；请到 MP 设置接入 Emby 后再启用")
                return
            lines = []
            for s in svcs:
                _n = (getattr(s, 'name', '') or '').strip() or "Emby"
                _u = (self._get_service_url(s) or "?").strip('`')
                lines.append(f"{_n}（{_u}）")
            logger.info(f"✅ Emby 服务健康检查：检测到 {len(svcs)} 个 —— " + "；".join(lines))
        except Exception as e:
            logger.error(f"Emby 服务健康检查失败（非阻断）: {e}")


    # ============================================================
    # 启动 / LLM 初始化
    # ============================================================
    def _startup(self):
        self._stop_requested = False
        self._scan_stop = False
        self._tx_stop = False
        self._wb_stop = False
        self._pool_stop = False
        self._probe_stop = False
        self._scan_paused = False
        self._pool_paused = False
        self._tx_paused = False
        self._tx_pause_logged = False
        self._probe_emby_services()
        # v4.6.76（规范 §二十三）：一次性清理旧版产生的「未管理脏事件」——
        # P0 修复前，未管理媒体的删除也会登记 missing 事件；升级后按数据库真实记录核对，
        # 数据库里连对应媒体都没有的 missing 事件直接移除（不再挂在界面上误导用户）。
        try:
            _cl = self._cleanup_dirty_webhook_events() or {}
            _n_dirty = int(_cl.get("removed_count") or 0)
            if _n_dirty:
                logger.info(f"[Webhook] 已清理 {_n_dirty} 条旧版残留的失效事件"
                            f"（插件未管理该媒体，数据库无对应记录）")
        except Exception as _de:
            logger.debug(f"[Webhook] 脏事件清理失败（非致命）: {_de}")
        try:
            self._init_llm()
            if self._llm is not None:
                logger.info(f"✅ LLM 初始化成功: model={self._llm.model}")
            elif self._ai_enabled():
                logger.warning("⚠️ LLM 客户端初始化失败，扫描时无法翻译")
            logger.info(f"EmbyPeopleLocalize v{self.plugin_version} 启动完成")
            try:
                logger.info(f"检测到 {len(self._get_all_emby_services())} 个 Emby 服务")
            except Exception:
                pass
            try:
                self._push_log("INFO", f"插件已启动 v{self.plugin_version}（模式={self._scan_mode}）")
            except Exception:
                pass
        except Exception as e:
            logger.error(f"插件启动失败: {e}\n{traceback.format_exc()}")

    def _init_llm(self):
        if not self._ai_enabled():
            logger.info("AI 翻译开关已关闭（仅使用人名池/繁转简/人工修正），LLM 不启用")
            self._llm = None
            return
        try:
            _mode = getattr(self, "_llm_mode", "system")
            if _mode == "plugin":
                # 插件自填：用户单独配置模型
                base_url = self._llm_base_url
                api_key = self._llm_api_key
                model = self._llm_model
            else:
                # 系统配置：使用 MoviePilot 全局 LLM
                base_url = getattr(settings, 'LLM_BASE_URL', '')
                api_key = getattr(settings, 'LLM_API_KEY', '')
                model = getattr(settings, 'LLM_MODEL', '')
            timeout = self._llm_timeout or constants.DEFAULT_LLM_TIMEOUT
            if not base_url or not api_key:
                logger.warning(f"[LLM] 未配置（mode={_mode}），翻译将不可用")
                self._llm = None
                return
            self._llm = LLMClient(
                base_url=base_url,
                api_key=api_key,
                model=model,
                prompt_template=self._prompt_template or constants.DEFAULT_PROMPT,
                timeout=timeout,
                verify_ssl=self._llm_verify_ssl,
                use_proxy=bool(getattr(self, "_use_proxy", False)),
                min_interval=float(getattr(self, "_llm_min_interval", 0) or constants.DEFAULT_LLM_MIN_INTERVAL),
                max_rpm=int(getattr(self, "_llm_max_rpm", 0) or 0),
                tpm_budget=int(getattr(self, "_llm_tpm_budget", 0) or 0),
                thinking_off=bool(getattr(self, "_llm_thinking_off", True)),
                thinking_params=str(getattr(self, "_llm_thinking_params", "") or ""),
            )
            logger.info(f"[LLM] 客户端预热完成：仅初始化 LLM 通道，不拉取人物（模型 {self._llm.model}）")
        except Exception as e:
            logger.error(f"[LLM] 初始化失败: {e}")
            self._llm = None

    def _llm_workers_busy(self) -> bool:
        """是否有会用到 LLM 的作业正在跑（翻译/写回/拉取）。
        用于「LLM 配置延迟热重载」判定 —— 运行中不热替换 LLM 核心对象（文档 P1-C）：
        避免请求参数前后混合、限速状态/429 熔断窗口被重置、API key/base_url 中途切换。"""
        try:
            if self._task_busy_for_pause("translate"):
                return True
            if self._task_running("writeback"):
                return True
            if self._task_running("pool"):
                return True
        except Exception:
            return False
        return False

    def _llm_reload_if_idle(self) -> None:
        """延迟 LLM 配置重载 —— 有「待重载」标记且此刻无任何
        LLM 作业在跑时，统一重建 LLM 客户端并清标记。由翻译 worker 轮询调用
        （其空闲 = 翻译链路空闲），确保新配置只在整个链路空档期生效，不做中途热替换。"""
        if not bool(getattr(self, "_llm_reload_pending", False)):
            return
        if self._llm_workers_busy():
            return
        self._llm_reload_pending = False
        logger.info("[LLM] 翻译链路已空闲，应用延迟的 LLM 配置变更（重建客户端）")
        self._init_llm()
        try:
            self._push_log("INFO", "LLM 配置已生效（客户端已重建）")
        except Exception:
            pass

    # ============================================================
    # NFO 文本判定辅助（_looks_like_* 供 NFO 流水线共用）
    # ============================================================

    @staticmethod
    def _looks_like_japanese(text: str) -> bool:
        """假名检测 - 含平/片假名判定为日文（动漫声优名）"""
        for c in text:
            cp = ord(c)
            if 0x3040 <= cp <= 0x309F or 0x30A0 <= cp <= 0x30FF:
                return True
        return False

    @staticmethod
    def _looks_like_chinese(text: str) -> bool:
        for c in text:
            cp = ord(c)
            if (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF
                    or 0xF900 <= cp <= 0xFAFF or 0x20000 <= cp <= 0x2FFFF):
                return True
        return False

    @staticmethod
    def _looks_like_spaced_cjk_name(text: str) -> bool:
        """汉字名夹空格（「日高 里菜」= 日文「姓 名」写法）。
        v4.6.95：**不再**作为「需翻译」的判据（与 db.py v4.6.80 口径对齐）——
        这类汉字名本身就是可用中文，此前被判待翻译 → 白占人数上限、白调 LLM，
        且与人名池「无需操作」矛盾（用户实测：「名冢 佳织」「村川 梨衣」等已中文却仍进待翻）。
        保留本方法仅供需要「识别空格写法」的场景参考，翻译判定不再调用。"""
        _t = str(text or "").strip()
        if not _t:
            return False
        if not any("\u4e00" <= ch <= "\u9fff" for ch in _t):
            return False
        return len(_t.split()) > 1

    def _name_is_zh(self, text: str) -> bool:
        """名字是否「已是中文」—— 含汉字 且 不含假名。
        v4.6.95：空格不再是排除条件（对齐 db.py v4.6.80）——
        「名冢 佳织」「村川 梨衣」这类汉字夹空格的名字本身就是可用中文，不再当待翻译。"""
        return (self._looks_like_chinese(text)
                and not self._looks_like_japanese(text))

    def _skip_no_translate(self, term: str) -> bool:
        """「已是简体中文」= 无需翻译（v4.6.54）—— 从待翻口径里排除：
        含汉字且无假名（v4.6.95：空格不再是排除条件，与 db.py v4.6.80 对齐），
        且繁转简后不变（繁体名仍会保留待翻，不破坏繁→简）。
        这样中文名不再一直显示「待翻译」、不再白占人数上限额度、不再白调 LLM / 阻塞写回。"""
        _t = str(term or "").strip()
        if not _t or not self._name_is_zh(_t):
            return False
        try:
            return self._zhconv_convert(_t) == _t
        except Exception:
            return False

    # ============================================================
    # 演职人员「重复 credit」去重（v4.6.96）
    # ============================================================
    @staticmethod
    def _dedup_credit_people(people: list) -> list:
        """采集层去重：同一 nfo 内「原文名 + 角色」完全相同的 credit 只保留先出现的一条。
        v4.6.96（用户实测）：nfo 有时把同一个人同时写在 <writer> 与 <credits>
        （实测《某剧》S01E01：「吉田玲子」两行），采集会落两行；
        Emby 按「人物」展示只显示一个 —— 这里同口径去重，从源头不再产生重复行。"""
        _seen, _out = set(), []
        for _p in (people or []):
            _k = (str(_p.get("before_name") or "").strip(), str(_p.get("before_role") or "").strip())
            if _k in _seen:
                continue
            _seen.add(_k)
            _out.append(_p)
        return _out

    @staticmethod
    def _dedup_credit_rows(rows: list) -> list:
        """展示层去重（people_of_item 行）：同一「name_before + role_before」只留一条。
        v4.6.96：库里若已存在历史重复行（旧版本采集写入），展示时同样只显示一个（与 Emby 一致），
        无需等到重扫；不影响库中数据与翻译流程。"""
        _seen, _out = set(), []
        for _r in (rows or []):
            _k = (str(_r.get("name_before") or "").strip(), str(_r.get("role_before") or "").strip())
            if _k in _seen:
                continue
            _seen.add(_k)
            _out.append(_r)
        return _out

    # ============================================================
    # 缓存管理
    # ============================================================
    def clear_cache(self):
        self._pool_hits = 0
        self._llm_terms = 0
        try:
            self._failed_terms = set()
            self._failed_terms_detail = {}
        except Exception:
            pass
        try:
            # v4.6.103（TMDB-1/2）：清缓存时一并重置 TMDB 无效 ID 负缓存 ——
            # 「清空缓存」是用户唯一的手动恢复入口，避免坏 ID 在 TTL 内被一直跳过。
            self._tmdb_dead = {}
            self._tmdb_poster_cache = {}
            self._tmdb_credits_cache = {}
            self._tmdb_person_cache = {}
            # v4.6.111（LIB-020）：**持久化的负缓存副本也一并清掉**（否则清完缓存，
            # 重启后又从库里读回那批坏 id，用户点「清空缓存」将失去意义）。
            self._tmdb_dead_store = {}
            self._tmdb_dead_dirty = False
            self._tmdb_empty_log = []
            try:
                set_meta(self._TMDB_DEAD_META_KEY, "{}")
            except Exception:
                pass
        except Exception:
            pass
        self._save_state()
        try:
            from .db import NameMapDb
            dbm = getattr(self, "_name_map_db", None) or NameMapDb()
            _n = dbm.clear_auto(plugin_id=self.__class__.__name__)
            if _n:
                self._push_log("INFO", f"已清空人名池自动条目 {_n} 条（人工修正保留）")
        except Exception as e:
            logger.debug(f"清空人名池自动条目失败（非致命）: {e}")
        logger.info("人名池自动条目已清空")

    def _stop_join_worker(self, kind: str, thread_attr: str, event_attr: str,
                          timeout: float = 2.0) -> bool:
        """统一停止并等待一个常驻后台 Worker。

        文档 P1-G：所有后台任务须拥有 thread ref / Event / stop flag；停止流程 =
        set stop flag（由 _request_task_stop 置）→ set wake event → join(timeout) →
        记录是否退出。原 stop_service 只对 Webhook Worker / 扫描线程做了 join，
        翻译（_tx_thread）与写回（_wb_thread）只置停止位、从不等待 —— 关闭/热重载时
        它们可能仍在跑 LLM 调用或文件写回，无收口。

        返回 True 表示已退出（或本就未在运行）；False 表示超时未退出（daemon 兜底）。
        """
        try:
            _ev = getattr(self, event_attr, None)
            if isinstance(_ev, threading.Event):
                _ev.set()
            _th = getattr(self, thread_attr, None)
            if _th is not None and _th.is_alive():
                logger.info(f"等待 {kind} Worker 退出 (timeout={timeout}s)...")
                _th.join(timeout=timeout)
                if _th.is_alive():
                    logger.warning(f"{kind} Worker {timeout}s 内未退出，daemon 兜底")
                    return False
                logger.info(f"{kind} Worker 已退出")
            try:
                setattr(self, thread_attr, None)
            except Exception:
                pass
            return True
        except Exception as e:
            logger.warning(f"停止 {kind} Worker 异常: {e}")
            return False

    def stop_service(self):
        """关闭插件时安全停止后台线程
        加强 - 1) 等待时间 10s → 30s，给 LLM 调用留出响应时间
                     2) 让 LLM 客户端置 None 强制让卡住的 LLM 调用快速抛错
                     3) daemon=True 兜底，MP 进程退出时线程会被强制结束
        有任务运行中时提示用户（后台有任务，请勿关闭），并保存断点
        """
        logger.info("收到插件停止信号，开始安全退出...")
        try:
            if getattr(self, "_is_running", False):
                self._push_log("WARNING", "后台有任务正在执行（扫描/翻译）。已保存断点，请在下次扫描时继续；强制关闭可能中断当前 AI 翻译批次。")
                logger.warning("后台有任务正在执行（扫描/翻译）——如有 LLM 调用正在等待响应，本次可能中断")
        except Exception:
            pass
        try:
            # 1. 触发停止事件（v5 收口 P0-5: 走统一接口 → 各任务独立停止位全置）
            self._request_task_stop("all")
            if hasattr(self, "_stop_event") and self._stop_event is not None:
                self._stop_event.set()
            # 2. 保存当前状态（含 cursor，NFO 断点可续扫）
            self._save_state()
            # 3. v1.3.6: 强制关闭 LLM HTTP 连接 - 让卡住的 LLM 调用立即抛异常退出
            try:
                if self._llm is not None and hasattr(self._llm, "close"):
                    self._llm.close()
                    logger.info("已强制关闭 LLM HTTP 连接，停止中的 LLM 调用将立即失败")
            except Exception as e:
                logger.debug(f"关闭 LLM 连接时异常: {e}")
            finally:
                self._llm = None
                self._startup_background_started = False
            # 4. 停止 Webhook Worker 线程（v1.3.9）
            if hasattr(self, "_webhook_worker_event") and self._webhook_worker_event is not None:
                self._webhook_worker_event.set()
            wh_thread = getattr(self, "_webhook_worker_thread", None)
            if wh_thread and wh_thread.is_alive():
                logger.info("等待 Webhook Worker 退出 (timeout=1.5s)...")
                wh_thread.join(timeout=1.5)
                if wh_thread.is_alive():
                    logger.warning("Webhook Worker 1.5s 内未退出，daemon 兜底")
                else:
                    logger.info("Webhook Worker 已退出")
            self._webhook_worker_thread = None

            # 4.5 v4.6.21(P1-G/§30-15): 停止常驻翻译/写回 Worker 并等待退出。
            # 原实现只经 _request_task_stop("all") 置了 _tx_stop/_wb_stop（停止位），
            # 却不 join —— 关闭/「保存配置」触发的热重载时，二者可能仍在跑 LLM 调用
            # 或文件写回，MP 进程/旧实例销毁前无收口。此处对齐 Webhook Worker：
            # set 停止位（已置）→ set 唤醒 Event → join(timeout) → 记录是否退出。
            # 位置在 LLM close（步骤 3）之后：LLM 已置 None，卡住的调用会立即抛错退出。
            # 翻译 Worker 稍长（2.5s，给 LLM 反压收尾）；写回 Worker 1.5s（本地文件写）。
            self._stop_join_worker("翻译", "_tx_thread", "_tx_event", timeout=2.5)
            self._stop_join_worker("写回", "_wb_thread", "_wb_event", timeout=1.5)

            # 5. 停止后台维护线程（v3.4.58/v3.5.1）—— set 事件让 worker 退出本轮等待；
            # 不置 None（_start_maintenance 重启用时会重建新 Event）
            if hasattr(self, "_maintenance_stop") and self._maintenance_stop is not None:
                self._maintenance_stop.set()

            if hasattr(self, "_schedule_stop") and self._schedule_stop is not None:
                self._schedule_stop.set()
            _pds = getattr(self, "_probe_daemon_stop", None)
            if isinstance(_pds, threading.Event):
                _pds.set()
            # 兼容旧实例：万一 _probe_stop 曾被历史代码写成 Event，也一并 set
            if isinstance(getattr(self, "_probe_stop", None), threading.Event):
                self._probe_stop.set()
            self._probe_stop = True   # 通知正在跑的探测轮退出（bool 停止位）

            # 6. 等待 NFO 扫描/扫描线程退出（v3.5.1: 1.5s，原 3s —— LLM 已 close，
            # _stop_requested 已置，worker 内 LLM 调用立即抛错、批间检查快速退出；
            # 短等避免「保存配置」接口被拖慢，daemon 兜底）
            _joined = set()
            _treg = dict(getattr(self, "_task_threads", None) or {})
            if getattr(self, "_scan_thread", None) is not None:
                _treg.setdefault("scan", self._scan_thread)
            for _tname, thread in _treg.items():
                if thread is None or id(thread) in _joined or not thread.is_alive():
                    continue
                _joined.add(id(thread))
                logger.info(f"等待 {_tname} 任务线程退出 (timeout=1.5s)...")
                thread.join(timeout=1.5)
                if thread.is_alive():
                    logger.warning(f"{_tname} 任务线程 1.5s 内未退出，daemon 兜底（MP 进程结束时会被强制结束）")
                else:
                    logger.info(f"{_tname} 任务线程已退出")
            self._scan_thread = None
            self._pool_thread = None
            self._wb_job_thread = None
            self._tx_job_thread = None
            self._task_threads = {}

            # 6.5 v4.6.21(P1-H/§30-16): 关闭 Series 展开有界线程池 —— 不再处理新事件，
            # wait=False（不等在跑任务），正在展开的 Series 由其自身停止位/LLM 关闭快速收敛。
            _sex = getattr(self, "_series_executor", None)
            if _sex is not None:
                try:
                    _sex.shutdown(wait=False)
                except Exception:
                    pass
                self._series_executor = None
                self._series_executor_workers = 0
            try:
                self._flush_received_notification()
            except Exception:
                pass
            try:
                self._flush_delete_notification()
            except Exception:
                pass
            try:
                self._flush_notification_queue()
            except Exception:
                pass
            logger.info("插件停止完成")
        except Exception as e:
            logger.error(f"停止服务异常: {e}\n{traceback.format_exc()}")

    # ============================================================
    # Webhook 入库自动翻译（v1.0.0 完全重构）
    # ============================================================
    
    # Webhook 事件类型映射（Emby → MoviePilot 翻译触发）
    _WEBHOOK_ITEM_EVENT_TYPES = (
        "itemadded", "item.added", "library.new", "added", "newcontent",
        "itemupdated", "item.updated", "library.update",
    )
    _WEBHOOK_EXCLUDE_EVENT_TYPES = (
        "playback", "playstate", "session", "user", "notification",
        "playbackstart", "playbackprogress", "playbackstopped",
        "sessionstarted", "sessionended",
        "delete", "deleted", "remove", "removed",
    )
    _WEBHOOK_ITEM_EVENT_TYPES_EXT = (
        "itemadded", "item.added", "library.new", "librarynew", "added", "newcontent",
        "itemupdated", "item.updated", "library.update", "libraryupdated",
        "item.refresh", "itemrefresh", "item.created", "system.update",
    )

    @eventmanager.register(EventType.WebhookMessage)
    def handle_webhook(self, event: Event):
        """
        监听 Emby Webhook 入库事件
        简化 Pydantic v2 解析（MoviePilot 仅支持 v2），移除冗余字段映射
        插件关闭时不再调度翻译
        """
        # 插件未启用：静默丢弃，不调度、不计数
        if not getattr(self, "_enabled", False):
            return
        if not getattr(self, "_webhook_enabled", False):
            return
        try:
            event_data_obj = event.event_data
            if event_data_obj is None:
                return

            if hasattr(event_data_obj, 'model_dump'):
                try:
                    raw_data = event_data_obj.model_dump() or {}
                except Exception as e:
                    logger.debug(f"[Webhook] model_dump() 失败: {e}")
                    return
            elif isinstance(event_data_obj, dict):
                raw_data = event_data_obj
            elif isinstance(event_data_obj, str):
                try:
                    raw_data = json.loads(event_data_obj)
                except Exception:
                    return
            else:
                return

            if not isinstance(raw_data, dict) or not raw_data:
                return

            if isinstance(raw_data.get('json_object'), dict) and raw_data['json_object']:
                raw_json = raw_data['json_object']
                _item = raw_json.get('Item') or {}
                if _item:
                    if _item.get('Id') and not raw_data.get('ItemId'):
                        raw_data['ItemId'] = str(_item.get('Id'))
                    if _item.get('Id') and not raw_data.get('Id'):
                        raw_data['Id'] = str(_item.get('Id'))
                    if _item.get('ServerId'):
                        raw_data['ServerId'] = str(_item.get('ServerId'))
                    if _item.get('Type'):
                        raw_data['media_type'] = _item.get('Type')
                if raw_json.get('Event') and not raw_data.get('Event'):
                    raw_data['Event'] = raw_json.get('Event')
                if raw_json.get('Server') and isinstance(raw_json.get('Server'), dict):
                    raw_data['Server'] = raw_json.get('Server')
                    if raw_json.get('Server').get('Name'):
                        raw_data['server_name'] = raw_json.get('Server').get('Name')
            # 宿主来源识别：WebhookEventInfo.channel == 'emby'
            if raw_data.get('channel') and not raw_data.get('source'):
                raw_data['source'] = raw_data.get('channel')


            # 早期提取 ItemId，没有 ItemId 直接跳过（减少噪音日志）
            item_id = self._extract_item_id(raw_data)
            if not item_id:
                return  # 无 ItemId 的事件直接跳过，不记录日志

            server_id = self._extract_server_id(raw_data)
            try:
                server_id = self._canonical_server_id(server_id)
            except Exception:
                pass
            event_type_str = self._extract_event_type_str(raw_data)
            source = self._extract_source(raw_data)

            # 检查是否为 Emby 事件
            if source and "emby" not in source.lower():
                return  # 非 Emby 来源静默丢弃

            # 检查事件类型是否与媒体项相关
            try:
                _rj_d = raw_data.get("json_object") or {}
                _it_d = (_rj_d.get("Item") or {}) if isinstance(_rj_d, dict) else {}
                if not _it_d and isinstance(raw_data.get("Item"), dict):
                    _it_d = raw_data["Item"]
                logger.info(
                    "[Webhook] 收到事件 Event=%r Type=%r IsFolder=%r Id=%r Path=%r "
                    "SeriesName=%r SeasonName=%r IndexNumber=%r ParentIndexNumber=%r",
                    event_type_str, _it_d.get("Type"), _it_d.get("IsFolder"), item_id,
                    _it_d.get("Path"), _it_d.get("SeriesName"), _it_d.get("SeasonName"),
                    _it_d.get("IndexNumber"), _it_d.get("ParentIndexNumber"),
                )
            except Exception:
                pass
            if not self._is_item_event(event_type_str, raw_data):
                if self._is_delete_event(event_type_str):
                    self._handle_webhook_delete(raw_data, item_id, event_type_str, server_id)
                return  # 非入库事件静默丢弃（playback/playstate 等播放事件）

            try:
                _rj = raw_data.get("json_object") or {}
                _item0 = (_rj.get("Item") or {}) if isinstance(_rj, dict) else {}
                if not _item0 and isinstance(raw_data.get("Item"), dict):
                    _item0 = raw_data["Item"]
                _pre_path = self._normalize_webhook_path(server_id, str(_item0.get("Path") or ""))
                if _pre_path and not self._in_selected_library(_pre_path):
                    logger.debug(f"[Webhook] 预检过滤（未选择该媒体库）: {item_id} Path={_pre_path}")
                    return
            except Exception:
                pass  # 预检失败 → 交给 worker 阶段兜底

            now = time.time()
            delay = self._webhook_delay
            execute_at = now + delay
            schedule_key = f"{server_id}:{item_id}" if server_id else item_id
            _brief = self._webhook_item_brief(raw_data)
            # v4.6.92：解析通知里的「本次新增条目数」（如「Emby 上已添加了 4 项到 剧名」）——
            # 整剧入库判定「整剧都是新加的」用它（数量 ≥ 集总数 → 全收）；解析不到为 0（退回其它判定）。
            _added_n = self._parse_added_count(raw_data)
            with self._webhook_lock:
                if schedule_key in self._webhook_schedule:
                    # 重复事件：重置 execute_at
                    self._webhook_schedule[schedule_key]["execute_at"] = execute_at
                    if _brief:
                        self._webhook_schedule[schedule_key]["brief"] = _brief
                    if _added_n:
                        self._webhook_schedule[schedule_key]["added_count"] = _added_n
                    return
                self._webhook_schedule[schedule_key] = {
                    "execute_at": execute_at,
                    "server_id": server_id,
                    "item_id": item_id,
                    "delay": delay,
                    "brief": _brief,
                    "added_count": _added_n,
                }
                # 确保单 Worker 线程在运行
                if self._webhook_worker_thread is None or not self._webhook_worker_thread.is_alive():
                    self._webhook_worker_event.clear()
                    self._webhook_worker_thread = threading.Thread(
                        target=self._webhook_worker,
                        daemon=True,
                        name="webhook-worker"
                    )
                    self._webhook_worker_thread.start()

            self._webhook_received += 1
            self._webhook_last_time = now
            self._webhook_last_event = f"{event_type_str} | ItemId={item_id}"
            self._webhook_error = ""
            self._push_webhook_event(item_id, _brief.get("name") or _brief.get("series_name") or item_id,
                                     "received", f"已接收入库事件，{delay} 秒后处理",
                                     series_name=_brief.get("series_name") or "",
                                     season=_brief.get("season"), episode=_brief.get("episode"))
            self._enqueue_received_notification(_brief, item_id)
            logger.info(f"[Webhook] 已调度: ItemId={item_id}, 将在 {delay} 秒后执行")

        except Exception as e:
            logger.error(f"[Webhook] 处理异常: {e}\n{traceback.format_exc()}")
            self._webhook_failed += 1
            self._webhook_error = str(e)

    def _webhook_item_brief(self, raw_data: dict) -> dict:
        """从 Webhook 原始报文提取条目简要信息（剧名/单集号/类型）。"""
        try:
            _item = {}
            _rj = raw_data.get("json_object") or {}
            if isinstance(_rj, dict):
                _item = _rj.get("Item") or {}
            if not _item and isinstance(raw_data.get("Item"), dict):
                _item = raw_data["Item"]

            def _g(*names, default=None):
                for n in names:
                    v = _item.get(n)
                    if v not in (None, ""):
                        return v
                return default

            return {
                "name": str(_g("Name", default="") or ""),
                "series_name": str(_g("SeriesName", "ParentName", "Series", default="") or ""),
                "season": _g("ParentIndexNumber", "SeasonNumber", "Season"),
                "episode": _g("IndexNumber", "EpisodeNumber", "Episode"),
                "type": str(_g("Type", default="") or ""),
            }
        except Exception:
            return {}

    @staticmethod
    def _parse_added_count(source) -> int:
        """解析 Emby 通知里的「本次新增条目数」（v4.6.92）。

        中文（Emby 中文界面）：「Emby 上已添加了 4 项到 某剧」→ 4；
        英文：「4 items added to ...」/「Added 4 items to ...」→ 4。
        `source` 可传 webhook 原始报文（dict，读 json_object.Title / title）或直接传标题字符串。

        解析失败返回 0 —— 表示「无此信号」，调用方退回其它判定（**绝不**当成「新增 0 项」处理）。
        剧名里带数字不受影响（按「已添加了 N 项」这类完整措辞匹配，不裸取数字）。
        """
        _t = ""
        try:
            if isinstance(source, dict):
                _rj = source.get("json_object") or {}
                if isinstance(_rj, dict):
                    _t = str(_rj.get("Title") or _rj.get("title") or "")
                if not _t:
                    _t = str(source.get("title") or source.get("Title") or "")
            else:
                _t = str(source or "")
        except Exception:
            return 0
        if not _t:
            return 0
        for _pat in (r"已添加了\s*(\d+)\s*项", r"已新增了?\s*(\d+)\s*项",
                     r"(\d+)\s*items?\s+added", r"added\s+(\d+)\s+items?"):
            try:
                _m = re.search(_pat, _t, re.I)
            except Exception:
                continue
            if _m:
                try:
                    return int(_m.group(1))
                except Exception:
                    return 0
        return 0

    def _push_webhook_event(self, item_id: str, name: str, status: str, msg: str,
                            series_name: str = "", season=None, episode=None,
                            server_id: str = "", media_item_id: str = "") -> None:
        """记录一条 Webhook 事件明细（最新在前，上限 100）。
        v4.6.66（P0-5）：事件带 server_id / media_item_id —— 恢复清除时用完整身份匹配，
        不再只靠 title/series_name。"""
        try:
            events = getattr(self, "_webhook_events", None)
            if events is None:
                events = self._webhook_events = []
            from datetime import datetime as _dt
            events.insert(0, {
                "time": _dt.now().strftime("%Y-%m-%d %H:%M:%S"),
                "item_id": str(item_id or ""),
                "name": name or "",
                "series_name": series_name or "",
                "season": season,
                "episode": episode,
                "status": status,
                "msg": msg or "",
                "server_id": str(server_id or ""),
                "media_item_id": str(media_item_id or ""),
            })
            del events[100:]
            try:
                self._save_state()
            except Exception:
                pass
        except Exception:
            pass

    def _update_or_push_webhook_event(self, item_id: str, name: str, status: str, msg: str,
                                      series_name: str = "", season=None, episode=None) -> None:
        """把该条目最近的**非终态**事件行（已接收 / 处理中 / 等待）原地更新为最新状态，
        找不到才插入新行 —— 让「入库事件」列表**一个事件只占一行、状态原地流转**：
        已接收 → 处理中 → 完成/失败。

        v4.6.66：避免同一集出现两行（已接收 + 完成）。
        v4.6.84（用户实测）：此前只匹配 status=='received'，一旦中间态（running/waiting）
        用 _push_webhook_event 另起一行，后续就不再命中 → 列表里一个事件仍显示两行
        （「已接收/处理中」+「完成」）。现改为匹配全部非终态，串起整条状态链。"""
        try:
            events = getattr(self, "_webhook_events", None) or []
            _iid = str(item_id or "")
            if _iid:
                for e in events:
                    if str(e.get("item_id") or "") == _iid \
                            and str(e.get("status")) in ("received", "running", "waiting"):
                        e["status"] = status
                        e["msg"] = msg or ""
                        from datetime import datetime as _dt
                        e["time"] = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
                        if name:
                            e["name"] = name
                        if series_name:
                            e["series_name"] = series_name
                        if season is not None:
                            e["season"] = season
                        if episode is not None:
                            e["episode"] = episode
                        try:
                            self._save_state()
                        except Exception:
                            pass
                        return
        except Exception:
            pass
        self._push_webhook_event(item_id, name, status, msg,
                                 series_name=series_name, season=season, episode=episode)

    def _rebuild_missing_events_from_db(self) -> int:
        """从库中「观察期」记录重建「失效/待恢复」事件行 ——
        state.json 里没有事件明细时（老版本升级/首次持久化前），重启后也能看到哪些还在观察期。"""
        try:
            db = getattr(self, "_people_db", None)
            if db is None:
                return 0
            rows = db.missing_events(plugin_id=self.__class__.__name__)
            if not rows:
                return 0
            events = getattr(self, "_webhook_events", None)
            if events is None:
                events = self._webhook_events = []
            _exist = {(str(e.get("item_id") or ""), e.get("season"), e.get("episode"))
                      for e in events if str(e.get("status")) == "missing"}
            _gh = float(getattr(self, "_nfo_dead_grace_hours", 24) or 24)
            _n = 0
            for r in rows:
                _k = (r.get("item_id"), r.get("season_num"), r.get("episode_num"))
                if _k in _exist:
                    continue
                _ts = 0.0
                try:
                    _ts = float(r.get("deleted_at") or 0)
                except Exception:
                    pass
                _t = (datetime.fromtimestamp(_ts).strftime("%Y-%m-%d %H:%M:%S") if _ts
                      else datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                _sn = str(r.get("series_name") or "")
                _ep = r.get("episode_num")
                events.append({
                    "time": _t, "item_id": str(r.get("item_id") or ""),
                    "name": str(r.get("title") or _sn), "series_name": _sn,
                    "season": r.get("season_num"), "episode": _ep,
                    "status": "missing",
                    "msg": f"Emby 已删除该单集，进入观察期（{_gh:.0f} 小时）（重启后由库记录恢复显示）",
                })
                _n += 1
            if _n:
                events.sort(key=lambda e: str(e.get("time") or ""), reverse=True)
                del events[100:]
            return _n
        except Exception:
            return 0

    def _remove_missing_event(self, series_name: str = "", season=None, episode=None,
                              title: str = "", server_id: str = "", item_id: str = "",
                              media_item_id: str = "") -> int:
        """条目恢复（被删除后重新入库）时清掉事件列表里对应的
        「失效/待恢复」（missing）行 —— 恢复后不该再挂着一行待恢复。

        v4.6.66（P0-5）：改用**完整身份**匹配（Emby ItemId / 媒体 id / server_id + 剧名 + 季集 + 标题），
        修「整剧删除事件恢复后永远挂着」—— 整剧删除事件常无 SeriesName（Name 即剧名），
        恢复时按剧名也匹配得到；同剧不同服务器互不误清。

        极端情况（删 1 集 → 删 2 集 → 整部删 → 陆续恢复）语义：
        - 单集恢复只清该集自己的「失效」事件；
        - 剧/季级事件（无集号）只有在**该剧被删记录全部恢复**（不再有观察期行）后才清 ——
          恢复 1 集不会误清「整部删除」事件；全部恢复后由最后一条恢复自动清掉。
        :return: 清除行数
        """
        try:
            events = getattr(self, "_webhook_events", None)
            if not events:
                return 0
            _sn = str(series_name or "").strip()
            _ti = str(title or "").strip()
            _sid = str(server_id or "").strip()
            _iid = str(item_id or "").strip()
            _mid = str(media_item_id or "").strip()
            _all_restored = [None]   # 惰性：该剧是否已无观察期记录

            def _series_gone() -> bool:
                if _all_restored[0] is None:
                    _v = True
                    try:
                        _db = getattr(self, "_people_db", None)
                        if _db is not None and _sn:
                            _v = not _db.has_deleted_for_series(
                                plugin_id=self.__class__.__name__, series_name=_sn,
                                server_id=(_sid or None))
                    except Exception:
                        _v = False   # 查询失败 → 保守：保持事件
                    _all_restored[0] = _v
                return bool(_all_restored[0])

            def _match(e: dict) -> bool:
                if str(e.get("status")) != "missing":
                    return False
                # (a) Emby ItemId / 媒体 id 精确命中（同一条目的直接恢复，身份可辨）
                _e_iid = str(e.get("item_id") or "").strip()
                _e_mid = str(e.get("media_item_id") or "").strip()
                if _iid and _e_iid and _iid == _e_iid:
                    return True
                if _mid and _e_mid and _mid == _e_mid:
                    return True
                # (a2) v4.6.72：provider 身份归一比较 —— "1177096" 与 "tmdb:1177096"
                # 视为同一媒体（洗版后 Emby ItemId 变化时按 provider 命中，报告第九节）。
                if _mid and _e_mid:
                    try:
                        if split_media_id(_mid) == split_media_id(_e_mid):
                            return True
                    except Exception:
                        pass
                if _iid and _e_iid:
                    try:
                        _a = split_media_id(_iid)
                        _b = split_media_id(_e_iid)
                        if _a[0] and _a == _b:
                            return True
                    except Exception:
                        pass
                # 同服务器优先（任一方无值视为可匹配 —— 兼容老事件无 server_id）
                _e_sid = str(e.get("server_id") or "").strip()
                if _sid and _e_sid and _sid != _e_sid:
                    return False
                _e_sn = str(e.get("series_name") or "").strip()
                _e_nm = str(e.get("name") or "").strip()
                _e_ep = e.get("episode")
                # (b) 剧名匹配：事件剧名 或 事件名（整剧删除时 Name 即剧名）
                if _sn and (_e_sn == _sn or _e_nm == _sn):
                    if _e_ep is None:
                        # 剧/季级事件（无集号）：该剧被删记录全部恢复才清
                        return _series_gone()
                    # 集级事件：必须集号吻合（剧级入库不误清单集事件）
                    if episode is None:
                        return False
                    if e.get("season") is not None and season is not None \
                            and e.get("season") != season:
                        return False
                    return _e_ep == episode
                # (c) 标题匹配（电影 / 单集）
                if _ti and _e_nm == _ti:
                    return True
                return False

            _n = sum(1 for e in events if _match(e))
            if _n:
                events[:] = [e for e in events if not _match(e)]
                self._save_state()
            return _n
        except Exception:
            return 0

    def _cleanup_dirty_webhook_events(self) -> dict:
        """清理旧版残留的「未管理脏事件」（v4.6.76 · 规范 §二十三）。

        仅针对 **missing**（失效/待恢复）事件：用数据库真实记录核对 ——
        若该事件的身份（server_id + Emby ItemId / 媒体 id / nfo_path / 剧名+季集）
        在 person 表里连一条记录都没有（观察期行也没有），说明这是 P0 修复前
        「未管理媒体删除」误登记的脏事件，直接移除。

        v4.6.99（报告 §七）：改为**结构化返回**，明确区分「清理成功 / 无需清理 / 清理失败」，
        探测 error 的事件**必须保留**并单独计数：
          `{"success": bool, "removed_count": int, "kept_error_count": int, "error_message": str}`
        """
        out = {"success": True, "removed_count": 0, "kept_error_count": 0, "error_message": ""}
        try:
            events = getattr(self, "_webhook_events", None)
            if not events:
                return out
            db = getattr(self, "_people_db", None)
            if db is None:
                out["success"] = False
                out["error_message"] = "翻译记录数据库未初始化"
                return out
            _pid = self.__class__.__name__
            _keep, _drop, _kept_err = [], 0, 0
            for e in list(events):
                if str(e.get("status")) != "missing":
                    _keep.append(e)
                    continue
                try:
                    _p = db.media_probe(
                        plugin_id=_pid,
                        server_id=(str(e.get("server_id") or "") or None),
                        emby_item_id=str(e.get("item_id") or ""),
                        item_id=str(e.get("media_item_id") or ""),
                        media_id=str(e.get("media_item_id") or ""),
                        nfo_path="",
                        season_num=e.get("season"), episode_num=e.get("episode"),
                        series_name=str(e.get("series_name") or ""),
                        title=str(e.get("name") or "")) or {}
                except Exception as _pe:
                    _p = {"managed": True, "status": "error"}   # 探测异常 → 保守保留
                    logger.warning(f"[Webhook] 脏失效事件核对异常（保留）：{_pe}")
                # v4.6.98（P1-04 D）/ v4.6.99：只有「成功查询且确认无对应记录」才可移除；
                # status=error 必须**保留原事件**并计数（此前会误删）。
                if _p.get("status") == "error" or str(_p.get("match_type") or "") == "error":
                    _keep.append(e)
                    _kept_err += 1
                    logger.warning(f"[Webhook] 脏失效事件核对失败（媒体身份探测 error）→ 保留事件："
                                   f"ItemId={e.get('item_id')} {e.get('series_name') or e.get('name')}")
                elif _p.get("managed"):
                    _keep.append(e)
                else:
                    _drop += 1
                    logger.debug(f"[Webhook] 清理脏失效事件：ItemId={e.get('item_id')} "
                                 f"{e.get('series_name') or e.get('name')}（数据库无对应记录）")
            if _drop:
                self._webhook_events = _keep
                self._save_state()
            out["removed_count"] = int(_drop)
            out["kept_error_count"] = int(_kept_err)
            return out
        except Exception as _e:
            logger.warning(f"[Webhook] 清理脏失效事件失败: {_e}")
            return {"success": False, "removed_count": 0, "kept_error_count": 0,
                    "error_message": str(_e)}

    @staticmethod
    def _extract_item_id(data: Any) -> str:
        """从各种格式中提取 ItemId"""
        if not isinstance(data, dict):
            return ""

        # 直接字段
        for key in ["ItemId", "item_id", "Id", "id", "itemId", "itemid"]:
            val = data.get(key, "")
            if val:
                return str(val)

        # 嵌套在 data 字段中
        nested = data.get("data") or data.get("Data") or data.get("payload")
        if nested and isinstance(nested, dict):
            for key in ["ItemId", "item_id", "Id", "id"]:
                val = nested.get(key, "")
                if val:
                    return str(val)

        return ""

    @staticmethod
    def _extract_server_id(data: Any) -> str:
        """从各种格式中提取 ServerId"""
        if not isinstance(data, dict):
            return ""
        
        for key in ["ServerId", "server_id", "Serverid", "serverId"]:
            val = data.get(key, "")
            if val:
                return str(val)
        val = data.get("server_name", "") or data.get("ServerName", "")
        if val:
            return str(val)
        # 兼容嵌套的 data / payload 中的 server 名或 id
        nested = data.get("data") or data.get("Data") or data.get("payload")
        if nested and isinstance(nested, dict):
            for key in ["ServerId", "server_id"]:
                val = nested.get(key, "")
                if val:
                    return str(val)
        
        return ""

    @staticmethod
    def _extract_event_type_str(data: Any) -> str:
        """提取事件类型字符串"""
        if not isinstance(data, dict):
            return ""
        
        for key in ["NotificationType", "notification_type", "Type", "type", "EventType", "event_type", "Event", "event"]:
            val = data.get(key, "")
            if val:
                return str(val).lower()
        
        nested = data.get("data") or data.get("Data")
        if nested and isinstance(nested, dict):
            for key in ["NotificationType", "notification_type", "Type", "type", "Event"]:
                val = nested.get(key, "")
                if val:
                    return str(val).lower()
        
        return ""

    @staticmethod
    def _extract_source(data: Any) -> str:
        """提取事件来源"""
        if not isinstance(data, dict):
            return ""
        
        for key in ["source", "Source", "Server", "server", "System", "system"]:
            val = data.get(key, "")
            if val:
                return str(val)
        
        return ""

    def _is_item_event(self, event_type: str, data: Any) -> bool:
        """判断是否为媒体项相关事件"""
        if not event_type:
            return False
        
        event_type_lower = event_type.lower()
        
        for exclude_keyword in self._WEBHOOK_EXCLUDE_EVENT_TYPES:
            if exclude_keyword in event_type_lower:
                logger.debug(f"[Webhook] 排除非入库事件: {event_type}")
                return False
        
        # 检查是否为已知的 Item 事件类型
        for keyword in self._WEBHOOK_ITEM_EVENT_TYPES:
            if keyword in event_type_lower:
                return True
        
        if any(k in event_type_lower for k in ("delete", "deleted", "remove", "removed")):
            logger.debug(f"[Webhook] 排除删除事件: {event_type}")
            return False
        
        try:
            _et_clean = re.sub(r"[^a-z.]", "", event_type_lower)
        except Exception:
            _et_clean = event_type_lower
        if _et_clean in self._WEBHOOK_ITEM_EVENT_TYPES_EXT:
            return True
        logger.debug(f"[Webhook] 事件类型未命中入库白名单，忽略: {event_type}")
        return False

    @staticmethod
    def _is_delete_event(event_type: str) -> bool:
        """是否为 Emby 删除事件（library.deleted / ItemRemoved / LibraryDeleted 等）。
        与 _is_item_event 的兜底拦截共用同一组关键词，保证删除事件绝不会被当入库。"""
        et = (event_type or "").lower()
        return any(k in et for k in ("delete", "deleted", "remove", "removed"))

    def _delete_nfo_path_guess(self, path: str, server_id: str = "") -> str:
        """删除事件 Path → 库记录 nfo_path 猜测。
        - 已是 .nfo → 原样
        - 带扩展名（视频文件，含单集 mkv）→ 同目录同名 .nfo
        - 无扩展名（目录，整部删除）→ 目录下 tvshow.nfo / movie.nfo / 目录名.nfo
        归一化按 server_id 路由映射。
        """
        try:
            p = self._normalize_webhook_path(server_id, str(path or "").strip())
            if not p:
                return ""
            p = p.replace("\\", "/")
            if p.lower().endswith(".nfo"):
                return p
            base, ext = os.path.splitext(p)
            if ext and ext.lower() != ".nfo":
                return base + ".nfo"
            # 目录：整部删除（剧/电影目录）
            dname = base.rsplit("/", 1)[-1]
            for cand in (f"{p}/tvshow.nfo", f"{p}/movie.nfo", f"{p}/{dname}.nfo"):
                if os.path.isfile(cand):
                    return cand
            return f"{p}/tvshow.nfo"  # 兜底：都不存在时仍给 tvshow（交由落库匹配）
        except Exception:
            pass
        return ""

    def _reconcile_missing_episodes(self, client, container_item_id: str,
                                    path_prefix: str, server_id: str = "",
                                    itype: str = "series",
                                    include_legacy: bool = True) -> tuple:
        """容器级删除事件但容器**仍在 Emby** → 比对「库里登记的集」与「Emby 实际的集」。

        返回 `(真正消失的 [(season, episode), ...], 枚举是否可信, 原因)`：
          · `(diff, True, "")`      查询成功且**分页/总数完整** → diff 可信（可能为空 = 一集不缺）
          · `([], False, reason)`   查询失败 / 分页不完整 / 无 user_id / 客户端或库不可用
                                    → **不可信：调用方不得据此标记任何东西**

        v4.6.99（P1-01）：此前「枚举不到」时调用方会退化为「整季前缀标记」——
        而「枚举不到」的真实原因往往是**请求失败**（超时 / 401 / 403 / 500 / 无 user_id /
        响应非法 / 分页中断），会把仍然存在的整季记录误标进观察期。
        现在改为：只有「成功且完整」的枚举才能产出可信差集；其余一律不可信 → 不标记。

        - Series 容器：`client.get_series_episodes_status(剧 Id)` 拿全剧集（含分页完整性）；
        - Season 容器：`client.query_items_status(ParentId=季 Id, IncludeItemTypes=Episode)`，
          **循环翻页**直到取满总数 —— 任一页结构非法 / 分页中断 / 总数变化 → 不可信。

        v4.6.113（P1-01 / P2）：
        · Season 查询补齐**分页循环**（此前固定单页 Limit=500，>500 集的季会被判「不完整」）；
        · `episode_pairs_under_prefix` 返回 None（数据库查询失败）时按**不可信**处理，
          不再落入 no_db_rows（否则真实缺失集不会被处理）；
        · 读取范围与写入一致：`include_legacy` 透传给 db 层（多服务器环境只命中本服）。
        """
        try:
            db = getattr(self, "_people_db", None)
            if db is None or client is None:
                return [], False, "no_client_or_db"
            _sid = str(server_id or "")
            db_pairs = db.episode_pairs_under_prefix(
                plugin_id=self.__class__.__name__, path_prefix=path_prefix,
                server_id=_sid, include_legacy=include_legacy)
            if db_pairs is None:
                # v4.6.113（P2）：数据库查询失败 ≠ 「库里没有记录」—— 不得返回 no_db_rows
                return [], False, "db_error"
            db_pairs = set(db_pairs)
            if not db_pairs:
                # 库里本就没有「带季集」的记录可比 → 无可标记（可信的「无差异」）
                return [], True, "no_db_rows"
            _itype = str(itype or "series").lower()
            _items: List[dict] = []
            if _itype == "season":
                _total = None
                _start = 0
                _limit = 500
                while True:
                    _st, _r, _reason = client.query_items_status({
                        "ParentId": str(container_item_id or ""),
                        "IncludeItemTypes": "Episode",
                        "Recursive": "false",
                        "Fields": "ParentIndexNumber,IndexNumber",
                        "StartIndex": _start,
                        "Limit": _limit,
                    })
                    if _st != ITEM_FOUND:
                        return [], False, f"season_query_{_st}:{_reason}"
                    _r = _r if isinstance(_r, dict) else {}
                    _page = _r.get("Items")
                    if not isinstance(_page, list):
                        return [], False, "season_items_not_list"
                    try:
                        _t = int(_r.get("TotalRecordCount"))
                    except Exception:
                        return [], False, "season_total_invalid"
                    if _t < 0:
                        return [], False, "season_total_negative"
                    if _total is None:
                        _total = _t
                    elif _t != _total:
                        return [], False, f"season_total_changed_{_total}->{_t}"
                    if not _page:
                        if _start >= _total:
                            break
                        return [], False, f"season_empty_page_but_total_{_total}_at_{_start}"
                    if _total == 0:
                        return [], False, f"season_total_zero_but_items_at_{_start}"
                    _items.extend(_page)
                    _start += len(_page)
                    if _start >= _total:
                        break
                    if len(_page) < _limit:
                        return [], False, f"season_short_page_{_start}/{_total}"
            else:
                _st, _items, _reason = client.get_series_episodes_status(str(container_item_id or ""))
                if _st != ITEM_FOUND:
                    return [], False, f"series_query_{_st}:{_reason}"
            emby_pairs = set()
            for _ep in (_items or []):
                _s = _ep.get("ParentIndexNumber")
                _e = _ep.get("IndexNumber")
                if _s is None or _e is None:
                    continue
                try:
                    emby_pairs.add((int(_s), int(_e)))
                except Exception:
                    pass
            if _items and not emby_pairs:
                # v4.6.99（报告 §2.2 B）：服务器返回了条目，但**没有一条**能解析出季/集号
                #（响应结构异常 / 脏数据）→ 枚举不可信，不得据此判定「整季都消失了」。
                return [], False, "items_without_season_episode"
            return sorted(db_pairs - emby_pairs), True, ""
        except Exception as _e:
            logger.warning(f"[Webhook] 缺失集比对异常（按不可信处理，不标记）: {_e}")
            return [], False, f"exception:{_e}"

    def _configured_server_keys(self) -> set:
        """已配置 Emby 服务的 skey 集合（服务器身份校验白名单）。异常 → 空集。"""
        try:
            return {str(self._get_server_identifier(s) or "")
                    for s in (self._get_all_emby_services() or [])} - {""}
        except Exception:
            return set()

    def _resolve_unique_server_id(self, server_id: str) -> tuple:
        """删除处理**必须落在唯一且已确认的服务器**上（v4.6.98 P1-02 / v4.6.99 收紧）。
        返回 `(skey, error)`；error 非空表示「不得写库」。

        v4.6.99（报告 P1-02 B/C）：**非空 ≠ 有效** —— 事件带来的 ServerId 必须能映射到
        已配置的 Emby 服务（skey 白名单），否则一律判「服务器未知」并拒绝写库。
        此前 `_canonical_server_id` 解析不了时原样返回字符串，未知 GUID 会被当成有效服务器，
        再叠加软范围（`server_id=''` 也命中）就会误改 legacy 空来源行。

        - 事件带 ServerId 且在白名单 → 采用；
        - 未带且只配置 1 台 → 用该台（归属唯一可确定）；
        - 未带且多台 / 无服务 / 带了但不认识 → `("", 原因)`。
        """
        _sid = str(server_id or "").strip()
        _keys = self._configured_server_keys()
        if _sid:
            if _sid in _keys:
                return _sid, ""
            return "", f"事件携带的 ServerId 无法映射到任何已配置的 Emby 服务（{_sid}）"
        if len(_keys) == 1:
            return next(iter(_keys)), ""
        if not _keys:
            return "", "未配置 Emby 服务（无法确定删除事件归属哪台服务器）"
        return "", f"配置了 {len(_keys)} 台 Emby 但事件未携带 ServerId（无法唯一确定归属）"

    def _handle_webhook_delete(self, raw_data: dict, item_id: str, event_type: str = "", server_id: str = ""):
        """Emby 删除事件（单集/整部）处理（v4.6.76 · 规范 §一/§二：**先探测插件是否管理过**）：
        Webhook 删除事件 ≠ 插件管理记录 —— 只有命中插件管理过的媒体（person 记录 /
        稳定媒体身份 / 历史别名 / 唯一弱匹配）才进入 missing 观察期；
        未管理媒体（含普通 Folder）删除完全静默：不建事件、不通知、不写库。
        managed 的删除复用 missing 机制 —— 观察期内重新入库时按稳定媒体身份自动恢复、
        超期由维护线程清理，并在 Webhook 事件列表「失效/待恢复」栏登记。"""
        try:
            _rj = raw_data.get("json_object") or {}
            _item = (_rj.get("Item") or {}) if isinstance(_rj, dict) else {}
            if not _item and isinstance(raw_data.get("Item"), dict):
                _item = raw_data["Item"]
            title = str(_item.get("Name") or _item.get("Title") or item_id)
            series_name = str(_item.get("SeriesName") or "")
            itype = str(_item.get("Type") or "")
            path_raw = str(_item.get("Path") or "")
            # 门禁：仅处理属于已选库的删除（与入库预检口径一致，未选库静默）
            pre = self._normalize_webhook_path(server_id, path_raw)
            if pre and not self._in_selected_library(pre):
                logger.debug(f"[Webhook] 删除事件跳过（未选择该媒体库）: ItemId={item_id}")
                return
            nfo_path = self._delete_nfo_path_guess(path_raw, server_id)
            _VIDEO_EXTS = (".mkv", ".mp4", ".avi", ".ts", ".m2ts", ".iso", ".mov", ".wmv",
                           ".flv", ".rmvb", ".strm", ".mpg", ".mpeg", ".m4v", ".webm", ".vob")
            _norm_pre = str(pre or "").replace("\\", "/")
            _is_dir_del = bool(_norm_pre) and not _norm_pre.lower().endswith(".nfo") \
                and os.path.splitext(_norm_pre)[1].lower() not in _VIDEO_EXTS
            n = 0
            db = getattr(self, "_people_db", None)
            _pid = self.__class__.__name__
            _pre_key = _norm_pre.strip("/").lower()
            _roots_key = [str(x).replace("\\", "/").strip("/").lower()
                          for x in (self._all_nfo_roots() or [])]
            _prefix_ok = bool(_pre_key) and _pre_key not in _roots_key
            _season = _item.get("ParentIndexNumber")
            _episode = _item.get("IndexNumber")
            # ── v4.6.98（P1-02）：删除处理必须落在**唯一**服务器上 ──
            # 此前 `_sid_arg = str(server_id or "") or None` → 缺 ServerId 时退化为 None =
            # 「不限定来源」（全表范围）：多台 Emby 同路径 / 同 ItemId / 同 ProviderId 时，
            # A 服的删除可能命中并标记 B 服的记录（违反多服务器隔离）。
            _sid_arg, _sid_err = self._resolve_unique_server_id(server_id)
            if not _sid_arg:
                # v4.6.99（P1-05）：服务器未知时**先做只读候选探测** ——
                #  · 探测成功且全库无任何候选管理记录 → 完全静默（不产生与插件无关的 UI 事件）；
                #  · 存在候选（插件以前可能管理过）→ 才登记 ambiguous 待确认（仍不写库）；
                #  · 探测失败 → 不当作 0 命中，登记 error 待确认。
                _probe_ok, _cand, _camb = True, 0, False
                if db is not None:
                    try:
                        _pr = db.media_probe(
                            plugin_id=_pid, server_id=None,          # 只读：跨来源候选探测
                            emby_item_id=str(item_id or ""), item_id="",
                            media_provider="", media_id="", nfo_path="",
                            season_num=_item.get("ParentIndexNumber"),
                            episode_num=_item.get("IndexNumber"),
                            series_name=str(_item.get("SeriesName") or _item.get("Name") or ""),
                            title=str(_item.get("Name") or ""),
                            # v4.6.113（P2）：Folder 候选探测同样禁止仅凭标题弱匹配
                            is_folder=(str(itype or "").lower() == "folder")) or {}
                        if (str(_pr.get("status") or "ok") == "error"
                                or str(_pr.get("match_type") or "") == "error"):
                            _probe_ok = False
                        elif _pr.get("managed"):
                            _cand = int(_pr.get("matched_rows") or 0)
                            _camb = bool(_pr.get("ambiguous"))
                    except Exception:
                        _probe_ok = False
                if _probe_ok and not _cand:
                    logger.debug(f"[Webhook] DELETE server-unknown 且无任何候选管理记录 → 静默："
                                 f"{_sid_err} item_id={item_id} path={_norm_pre}")
                    return
                _umsg = ((f"删除状态无法确认（{_sid_err}，且候选探测失败）" if not _probe_ok
                          else f"存在 {_cand} 条可能相关的管理记录，但服务器归属无法唯一确定")
                         + "：本次未修改任何翻译记录、未进入观察期；请检查 Webhook / Emby 配置，"
                           "或在库页手动确认")
                self._push_webhook_event(str(item_id or ""), title, "ambiguous", _umsg,
                                         series_name=series_name, season=_season, episode=_episode,
                                         server_id=str(server_id or ""), media_item_id="")
                logger.warning(f"[Webhook] DELETE server-unknown（不写库、不通知）: {_sid_err} "
                               f"probe_ok={_probe_ok} candidates={_cand} ambiguous={_camb} "
                               f"item_id={item_id} path={_norm_pre}")
                return
            # v4.6.99（P1-02 D）：多服务器环境下 legacy 空来源（server_id=''）行
            # 「原归属不明」→ 不能被本台服务器的事件自动认领/修改，只走人工确认；
            # 单服务器环境归属唯一可确定 → 允许连同 legacy 行一起处理。
            _include_legacy = len(self._configured_server_keys()) <= 1
            # ── 删除事件的稳定身份（v4.6.76 · 规范 §二：先探测「插件是否管理过」）──
            _title0 = str(_item.get("Name") or _item.get("Title") or item_id)
            _series0 = str(_item.get("SeriesName") or "")
            _ev_sn = _series0 or (_title0 if itype.lower() in ("series", "season") else "")
            _mp, _mid = "", ""
            try:
                _prov = _item.get("ProviderIds")
                if isinstance(_prov, dict):
                    _tmdb = str(_prov.get("Tmdb") or _prov.get("TmdbId") or "").strip()
                    _tvdb = str(_prov.get("Tvdb") or _prov.get("TvdbId") or "").strip()
                    _imdb = str(_prov.get("Imdb") or _prov.get("ImdbId") or "").strip()
                    if _tmdb.isdigit():
                        _mp, _mid = "tmdb", _tmdb
                    elif _tvdb:
                        _mp, _mid = "tvdb", _tvdb
                    elif _imdb:
                        _mp, _mid = "imdb", _imdb.lower()
            except Exception:
                _mp, _mid = "", ""
            _ev_media = _mid if _mp == "tmdb" else (f"{_mp}:{_mid}" if _mp else "")
            # 目录名兜底（{tmdb=123}）—— 与入库同一套推导
            _dir_iid = self._item_id_from_dir_name(_norm_pre or path_raw)
            _dir_mp, _dir_mid = split_media_id(_dir_iid) if _dir_iid else ("", "")
            _probe_mp = _mp or (_dir_mp if _dir_mp != "nfo" else "")
            _probe_mid = _mid or (_dir_mid if _dir_mp != "nfo" else "")
            _probe_iid = ""
            if itype.lower() in ("episode",) and path_raw:
                try:
                    _sid3, _sn3, _ss3, _ep3 = self._nfo_episode_meta(nfo_path or path_raw)
                    _probe_iid = str(_sid3 or "")
                except Exception:
                    _probe_iid = ""
            if not _probe_iid and itype.lower() in ("series", "season", "movie", "folder"):
                _probe_iid = _dir_iid if not str(_dir_iid).startswith("nfo:") else ""
            _series_media = _probe_iid if itype.lower() in ("series", "season", "episode") else ""
            _probe = {"managed": False, "match_type": "none", "matched_rows": 0,
                      "ambiguous": False, "status": "ok"}
            if db is not None:
                try:
                    _probe = db.media_probe(
                        plugin_id=_pid, server_id=_sid_arg,
                        emby_item_id=str(item_id or ""), item_id=_probe_iid,
                        media_provider=_probe_mp, media_id=_probe_mid,
                        series_media_id=(_series_media or _probe_iid) if itype.lower() != "movie" else "",
                        nfo_path=(nfo_path or _norm_pre or ""),
                        season_num=_season, episode_num=_episode,
                        series_name=_ev_sn, title=_title0,
                        # v4.6.113（P2）：探测范围与写入一致（多服务器不认领 legacy）；
                        # Folder 禁止仅凭标题弱匹配认领（避免陌生文件夹撞名产生噪声事件）。
                        is_folder=(itype.lower() == "folder"),
                        include_legacy=_include_legacy) or _probe
                except Exception as _pe:
                    logger.warning(f"[Webhook] 删除事件身份探测异常（按 error 处理，不当作未管理）: {_pe}")
                    _probe = {"managed": False, "match_type": "error",
                              "matched_rows": 0, "ambiguous": False, "status": "error"}
            # v4.6.98（P1-04）：探测出错 ≠ 未管理 —— 既不得静默丢弃（漏标真删除），
            # 也不得当作真删除（误标）。登记待确认事件、不写库、不发普通删除通知。
            if _probe.get("status") == "error" or str(_probe.get("match_type") or "") == "error":
                self._push_webhook_event(
                    str(item_id or ""), _title0, "ambiguous",
                    "删除状态无法确认（媒体身份探测失败）：本次未修改翻译记录、未进入观察期；"
                    "请检查数据库后重试或到库页手动确认",
                    series_name=_ev_sn, season=_season, episode=_episode,
                    server_id=str(server_id or ""), media_item_id=_ev_media)
                logger.warning(f"[Webhook] DELETE probe-error（不改记录、不发普通删除通知）: "
                               f"server={server_id} item_id={item_id}")
                return
            if not _probe.get("managed"):
                # v4.6.76（P0 · 规范 §一/§三-A）：插件从未管理过该媒体 → **完全静默**：
                # 不建 missing 事件、不进入观察期、不发通知、不写数据库。
                logger.debug(f"[Webhook] DELETE ignored: plugin has no managed record "
                             f"server={server_id} item_id={item_id} path={_norm_pre}（命中=0）")
                return
            if _probe.get("ambiguous"):
                # 规范 §三-B：多候选（弱匹配）→ 不自动观察期、不发普通删除通知，登记待人工确认
                self._push_webhook_event(
                    str(item_id), _title0, "ambiguous",
                    f"Emby 已删除该条目，但插件存在多个可能匹配的历史记录"
                    f"（候选 {_probe.get('matched_rows')} 个）—— 请人工确认后再处理；"
                    f"本次未自动进入观察期、未改动任何翻译记录",
                    series_name=_ev_sn, season=_season, episode=_episode,
                    server_id=str(server_id or ""), media_item_id=_ev_media)
                logger.warning(f"[Webhook] DELETE ambiguous: candidates={_probe.get('matched_rows')} "
                               f"server={server_id} item_id={item_id}（需人工确认）")
                return
            # v4.6.84（用户实测）：Emby 对「容器内容变动」也会发**容器级**删除 ——
            # 实测：只把 3 集（视频+nfo）移走，事件却是 Type=Series / IsFolder=True 的整部剧
            # （Emby 自己的通知标题写「移除了 X 中的 3 项」，但 Item 给的是 Series）。
            # 若照着 Item 整树标记，就会把整部剧误标进观察期（用户实测 86 条）。
            # 标记前先问 Emby：该容器条目现在是**存在 / 明确不存在 / 状态未知**。
            # v4.6.98（P1-01）改为**三态**判定，不再用「fetch_item 非空」——
            # 因为「查询失败」与「条目不存在」都返回 None，会把 Emby 超时/401/500
            # 误判成「容器已删除」→ 整剧批量误标：
            #   FOUND        容器仍在 → 内容变动：只标真正消失的集（不整树标记）
            #   NOT_FOUND    明确不存在 → 真删除：继续走后续标记
            #   UNAVAILABLE  查询失败 / 客户端不可用 / 无 user_id → **状态未知**：
            #                绝不按真删除处理（不整树标记、不发普通删除通知），登记待确认
            if itype.lower() in ("series", "season", "folder"):
                _cst, _cli, _still = ITEM_UNAVAILABLE, None, None
                try:
                    _cli, _cerr = self._emby_client_for_server(_sid_arg, allow_legacy_fallback=False)
                except Exception:
                    _cli, _cerr = None, "client-error"
                if _cli is not None:
                    try:
                        _cst, _still = _cli.fetch_item_status(str(item_id or ""))
                    except Exception as _fe:
                        _cst, _still = ITEM_UNAVAILABLE, None
                        _cerr = f"fetch-error: {_fe}"
                if _cst == ITEM_UNAVAILABLE:
                    _kmsg = (f"删除状态无法确认（{_cerr or '查询 Emby 失败 / 服务器不可用'}）："
                             f"本次未修改翻译记录、未进入观察期；稍后可重试或到库页手动确认")
                    self._push_webhook_event(str(item_id or ""), _title0, "ambiguous", _kmsg,
                                             series_name=_ev_sn, season=_season, episode=_episode,
                                             server_id=str(server_id or ""), media_item_id=_ev_media)
                    logger.warning(f"[Webhook] DELETE container-state-unknown（不按真删除处理）: "
                                   f"type={itype} server={_sid_arg} item_id={item_id} err={_cerr}")
                    return
                if _cst == ITEM_FOUND:
                    # 容器仍在 Emby → 是**内容变动**（少了几集），不是整树删除。
                    # v4.6.85：此前直接 return（一集都不标）→ 用户真删掉的几集就查不到；
                    # 现在改为**比对差集、只标真正消失的那几集**（同剧其它集一律不碰）。
                    _miss_pairs, _mk = [], 0
                    _ct = itype.lower()
                    if _ct in ("series", "season") and _is_dir_del and _prefix_ok:
                        # v4.6.99（P1-01）：枚举结果必须**可信**才允许标记 ——
                        # 「查询失败 / 分页不完整」不再退化为「整季前缀标记」
                        #（那会把仍然存在的整季记录误标观察期）。
                        _ok, _reason = True, ""
                        try:
                            _miss_pairs, _ok, _reason = self._reconcile_missing_episodes(
                                _cli, str(item_id or ""), _norm_pre, _sid_arg, _ct,
                                include_legacy=_include_legacy)
                        except Exception as _re:
                            _miss_pairs, _ok, _reason = [], False, f"exception:{_re}"
                        if not _ok:
                            _emsg = (f"删除状态无法确认（该容器仍在 Emby，但剧集枚举不可信：{_reason}）"
                                     f"—— 本次未修改翻译记录、未进入观察期；稍后可重试或到库页手动确认")
                            self._push_webhook_event(str(item_id or ""), _title0, "ambiguous", _emsg,
                                                     series_name=_ev_sn, season=None, episode=None,
                                                     server_id=str(server_id or ""),
                                                     media_item_id=_ev_media)
                            logger.warning(f"[Webhook] DELETE 容器仍在但枚举不可信（不标记）: "
                                           f"type={itype} server={_sid_arg} item_id={item_id} "
                                           f"reason={_reason}")
                            return
                        try:
                            if _miss_pairs:
                                _mk = int(db.mark_deleted_episodes_by_prefix(
                                    plugin_id=_pid, path_prefix=_norm_pre,
                                    pairs=_miss_pairs, server_id=_sid_arg,
                                    include_legacy=_include_legacy) or 0)
                        except Exception:
                            _mk = 0
                    if _mk > 0:
                        _mgh = float(getattr(self, "_nfo_dead_grace_hours", 24) or 24)
                        _mdead = time.strftime("%Y-%m-%d %H:%M",
                                               time.localtime(time.time() + _mgh * 3600))
                        _eps_txt = "、".join(f"S{_s:02d}E{_e:02d}" for _s, _e in _miss_pairs[:12])
                        if len(_miss_pairs) > 12:
                            _eps_txt += f" 等 {len(_miss_pairs)} 集"
                        _msg = (f"Emby 该容器仍在、检测到内容变动：已不存在 {len(_miss_pairs)} 集"
                                f"（{_eps_txt}）；{_mdead} 到期自动检查，"
                                f"观察期内重新入库时将自动尝试按媒体稳定身份恢复。"
                                f"本次只标记这几集，同剧其它集未受影响")
                        self._push_webhook_event(str(item_id or ""), _title0, "missing", _msg,
                                                 series_name=_ev_sn, season=None, episode=None,
                                                 server_id=str(server_id or ""),
                                                 media_item_id=_ev_media)
                        logger.info(f"[Webhook] DELETE 容器仍在 Emby → 只标缺失的 {len(_miss_pairs)} 集"
                                    f"（{_eps_txt}），标记 {_mk} 行：server={server_id} item_id={item_id}")
                        self._enqueue_delete_notification(head=_series0 or _title0,
                                                          ep_txt=f"{len(_miss_pairs)} 集",
                                                          n=_mk)
                    else:
                        logger.info(f"[Webhook] DELETE 容器仍在 Emby（无缺失集，判定为无关变动）→ 不标记："
                                    f"type={itype} server={server_id} item_id={item_id} path={_norm_pre}")
                    return
            if db is not None:
                try:
                    # v4.6.67（P0 删除隔离）：删除事件一律带来源服务器 ——
                    # 两台 Emby 映射到同一 nfo 路径时，A 服删除不得标记 B 服记录。
                    if itype.lower() in ("series", "movie", "season") and _is_dir_del and _prefix_ok:
                        n = int(db.mark_deleted_by_nfo_path_prefix(
                            plugin_id=_pid, path_prefix=_norm_pre, server_id=_sid_arg,
                            include_legacy=_include_legacy) or 0)
                        if not n and nfo_path:
                            n = int(db.mark_deleted_by_nfo_path(plugin_id=_pid, nfo_path=nfo_path,
                                                                server_id=_sid_arg,
                                                                include_legacy=_include_legacy) or 0)
                    elif nfo_path:
                        n = int(db.mark_deleted_by_nfo_path(plugin_id=_pid, nfo_path=nfo_path,
                                                            server_id=_sid_arg,
                                                            include_legacy=_include_legacy) or 0)
                        # 电影文件路径：Emby 刮削常写 movie.nfo（与视频文件不同名）——补查一次
                        if not n and itype.lower() == "movie" and "/" in _norm_pre:
                            _d = _norm_pre.rsplit("/", 1)[0]
                            n = int(db.mark_deleted_by_nfo_path(
                                plugin_id=_pid, nfo_path=_d + "/movie.nfo",
                                server_id=_sid_arg, include_legacy=_include_legacy) or 0)
                    if not n:
                        # v4.6.76（规范 §二/§九-42~44）：路径/命名不一致（洗版、Remux、nfo 改名）
                        # → 用探测到的稳定身份兜底标记观察期（整剧删除标全层级；单集只标本集）。
                        _m_season, _m_episode = (_season, _episode) if itype.lower() == "episode" else (None, None)
                        n = int(db.mark_deleted_by_media(
                            plugin_id=_pid, item_id=_probe_iid,
                            media_provider=_probe_mp, media_id=_probe_mid,
                            series_media_id=(_series_media or _probe_iid) if itype.lower() != "movie" else "",
                            emby_item_id=str(item_id or ""),
                            season_num=_m_season, episode_num=_m_episode,
                            server_id=_sid_arg, include_legacy=_include_legacy) or 0)
                except Exception:
                    n = 0
            _gh = float(getattr(self, "_nfo_dead_grace_hours", 24) or 24)
            _dead_text = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() + _gh * 3600))
            if itype.lower() == "episode":
                _tag = "单集"
            elif itype.lower() == "series":
                _tag = "整部剧集"
            elif itype.lower() == "movie":
                _tag = "整部电影"
            else:
                _tag = itype or "条目"
            if n <= 0:
                # v4.6.76（规范 §四）：managed=True 但行级标记 0（竞态 / 命名差异）→ 异常保护：
                # 不发送普通删除通知（避免误报），登记待确认事件并留 WARNING 日志。
                self._push_webhook_event(
                    str(item_id), _title0, "ambiguous",
                    f"Emby 已删除该{_tag}，插件确认管理过该媒体（match={_probe.get('match_type')}）"
                    f"但未能定位到具体记录行 —— 未标记观察期、未改动翻译记录，请到库页手动确认",
                    series_name=_ev_sn, season=_season, episode=_episode,
                    server_id=str(server_id or ""), media_item_id=_ev_media)
                logger.warning(f"[Webhook] DELETE managed-but-unmarked: match={_probe.get('match_type')} "
                               f"server={server_id} item_id={item_id} matched_rows=0")
                return
            msg = (f"Emby 已删除该{_tag}，进入观察期（{int(_gh)} 小时）；{_dead_text} 到期自动检查，"
                   f"观察期内重新入库时将自动尝试按媒体稳定身份恢复（Emby ID / TMDB / TVDB / IMDb）"
                   f"；已标记翻译记录 {n} 条待清理")
            # v4.6.66（P0-5）：整剧删除事件补 series_name（删除事件常无 SeriesName，Name 即剧名）——
            # 否则恢复时按剧名匹配不到，事件永远挂着「失效/待恢复」。
            self._push_webhook_event(str(item_id), _title0, "missing", msg, series_name=_ev_sn,
                                     season=_season, episode=_episode,
                                     server_id=str(server_id or ""), media_item_id=_ev_media)
            logger.info(f"[Webhook] DELETE managed: match={_probe.get('match_type')} "
                        f"server={server_id} item_id={item_id} matched_rows={n}")
            _ep_txt = ""
            if _season is not None and _episode is not None:
                _ep_txt = f"第{_season}季 第{_episode}集"
            elif _episode is not None:
                _ep_txt = f"第{_episode}集"
            self._enqueue_delete_notification(head=_series0 or _title0, ep_txt=_ep_txt, n=n)
        except Exception as e:
            logger.debug(f"[Webhook] 删除事件处理失败: {e}")

    def _enqueue_received_notification(self, brief: dict, item_id: str):
        """Webhook 接收通知批量聚合 —— 15 秒静默窗口内把多条入库事件合并成
        一条通知（显示剧名/集数，不再逐条带 ItemId 刷屏）。"""
        if not getattr(self, "_notify_on_complete", False):
            return
        try:
            bq = getattr(self, "_webhook_received_batch", None)
            if bq is None:
                self._webhook_received_batch = bq = {}
                self._webhook_received_order = []
            sn = str(brief.get("series_name") or "").strip()
            nm = str(brief.get("name") or "").strip()
            key = sn or nm or f"#item:{item_id}"
            rec = {"series_name": sn, "name": nm,
                   "season": brief.get("season"), "episode": brief.get("episode"),
                   "type": str(brief.get("type") or "")}
            with self._webhook_lock:
                _seen_set = getattr(self, "_webhook_recv_notified", None)
                if _seen_set is None:
                    _seen_set = self._webhook_recv_notified = set()
                _first = key not in _seen_set
                if _first:
                    _seen_set.add(key)
                if key not in bq:
                    bq[key] = []
                    self._webhook_received_order.append(key)
                bq[key].append(rec)
                if not _first:
                    self._webhook_received_reset = True
                if getattr(self, "_webhook_received_timer", None):
                    try:
                        self._webhook_received_timer.cancel()
                    except Exception:
                        pass
                self._webhook_received_timer = threading.Timer(
                    0.1 if _first else 10.0,
                    self._flush_received_notification)
                self._webhook_received_timer.daemon = True
                self._webhook_received_timer.start()
                # 等待期结束后解除「已通知」标记 —— 下一轮新集可再次即时通知
                if _first:
                    try:
                        _clr = getattr(self, "_webhook_recv_clr_timer", None)
                        if _clr:
                            _clr.cancel()
                    except Exception:
                        pass
                    self._webhook_recv_clr_timer = threading.Timer(
                        max(15.0, float(getattr(self, "_webhook_delay", 60) or 60)) + 5.0,
                        self._clear_recv_notified)
                    self._webhook_recv_clr_timer.daemon = True
                    self._webhook_recv_clr_timer.start()
        except Exception as e:
            logger.debug(f"[Webhook] 接收通知聚合入队失败（非致命）: {e}")

    def _enqueue_delete_notification(self, head: str, ep_txt: str, n: int):
        """删除通知聚合 —— 5 秒静默窗口内把批量删除合并成一条通知
        （原逐条推送：Emby 批量删 100 集 = 100 条推送刷屏）。"""
        if not getattr(self, "_notify_on_complete", False):
            return
        try:
            with self._webhook_lock:
                bq = getattr(self, "_webhook_delete_batch", None)
                if bq is None:
                    self._webhook_delete_batch = bq = []
                bq.append({"head": str(head or ""), "ep": str(ep_txt or ""), "n": int(n or 0)})
                _t = getattr(self, "_webhook_delete_timer", None)
                if _t:
                    try:
                        _t.cancel()
                    except Exception:
                        pass
                self._webhook_delete_timer = threading.Timer(5.0, self._flush_delete_notification)
                self._webhook_delete_timer.daemon = True
                self._webhook_delete_timer.start()
        except Exception as e:
            logger.debug(f"[Webhook] 删除通知聚合入队失败（非致命）: {e}")

    def _flush_delete_notification(self):
        """发送聚合后的删除通知（v4.6.76 · 规范 §二十：只聚合**插件已管理**的删除 ——
        未管理媒体的删除在 _handle_webhook_delete 已静默忽略，不会进本队列）。"""
        try:
            with self._webhook_lock:
                bq = list(getattr(self, "_webhook_delete_batch", None) or [])
                self._webhook_delete_batch = []
                self._webhook_delete_timer = None
            if not bq:
                return
            _gh = float(getattr(self, "_nfo_dead_grace_hours", 24) or 24)
            _dead_text = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() + _gh * 3600))
            _names, _marked = [], 0
            for r in bq:
                _lb = (r.get("head") or "") + (f" {r['ep']}" if r.get("ep") else "")
                if _lb and _lb not in _names:
                    _names.append(_lb)
                _marked += int(r.get("n") or 0)
            _head_txt = "、".join(_names[:5]) + (f" 等 {len(bq)} 条" if len(bq) > 5 else "")
            _lines = [
                f"🗑️ Emby 已删除 {len(bq)} 个**已管理**条目：{_head_txt}",
                f"📌 状态：进入观察期（{int(_gh)} 小时），到期自动检查；"
                f"观察期内重新入库时将自动尝试按媒体稳定身份恢复（Emby ID / TMDB / TVDB / IMDb）",
                f"📊 实际进入观察期：{_marked} 条翻译记录",
                f"⏰ 到期时间：{_dead_text}",
            ]
            self.post_message(mtype=NotificationType.Manual, title=self.plugin_name,
                              text="\n".join(_lines))
        except Exception as e:
            logger.debug(f"[Webhook] 删除通知发送失败（非致命）: {e}")

    def _clear_recv_notified(self):
        """等待期结束后解除「已发即时接收通知」标记 —— 下一轮新集可再次即时通知。"""
        try:
            with self._webhook_lock:
                self._webhook_recv_notified = set()
        except Exception:
            pass

    def _flush_received_notification(self):
        """发送聚合后的接收通知。
        电影专版文案 —— 电影没有「同剧合并」概念，去掉剧集口径的说明；条目带「（电影）」标识"""
        def _is_movie_rec(x: dict) -> bool:
            _t = str(x.get("type") or "").strip().lower()
            if _t:
                return _t == "movie"
            # 缺 Type 报文兜底：无剧名且无季集号 → 视为电影
            return (not x.get("series_name")) and x.get("season") is None and x.get("episode") is None
        try:
            with self._webhook_lock:
                bq = dict(getattr(self, "_webhook_received_batch", None) or {})
                order = list(getattr(self, "_webhook_received_order", None) or [])
                self._webhook_received_batch = {}
                self._webhook_received_order = []
                self._webhook_received_timer = None
                _is_reset = bool(getattr(self, "_webhook_received_reset", False))
                self._webhook_received_reset = False
            if not bq:
                return
            total = sum(len(v) for v in bq.values())
            parts = []
            for key in order:
                recs = bq.get(key) or []
                if not recs:
                    continue
                if recs[0].get("series_name"):
                    sn = recs[0]["series_name"]
                    eps = sorted(set(int(x["episode"]) for x in recs if x.get("episode") is not None))
                    seas = sorted(set(int(x["season"]) for x in recs if x.get("season") is not None))
                    if len(eps) > 1:
                        _txt = f"第{eps[0]}-{eps[-1]}集"
                    elif eps:
                        _txt = f"第{eps[0]}集"
                    else:
                        _txt = f"{len(recs)} 条"
                    parts.append(f"{sn} 第{seas[0]}季 {_txt}" if seas else f"{sn} {_txt}")
                else:
                    names = []
                    for x in recs:
                        _nm = x.get("name") or ""
                        if _nm and _nm not in names:
                            names.append(_nm)
                    _line = "、".join(names[:3]) + (f" 等 {len(recs)} 条" if len(names) > 3 else "")
                    parts.append(f"{_line}（电影）" if _is_movie_rec(recs[0]) else _line)
            _all_recs = [x for _k in order for x in (bq.get(_k) or [])]
            _all_movies = bool(_all_recs) and all(_is_movie_rec(x) for x in _all_recs)
            _items_txt = "\n".join(f"  • {p}" for p in parts[:8])
            if len(parts) > 8:
                _items_txt += f"\n  • …等 {len(parts)} 组"
            _delay = max(1, int(getattr(self, "_webhook_delay", 60) or 60))
            # v4.6.78：状态行与「延迟」说明必须反映**真实触发** —— 此前静态写「已安排翻译」，
            # 未开「Webhook 入库后自动翻译」时也照报，误导用户（实测反馈）。
            try:
                _auto = (str(self._nfo_ingest_trigger()) == "auto_trigger")
            except Exception:
                _auto = False
            if _auto:
                _st_line = "⏳ 状态：已接收，已安排翻译（插件将自动处理）"
                _delay_line = (f"🕒 延迟：约 {_delay} 秒后开始（等待 Emby 刮削/文件落位）")
                _st_merge = "⏳ 状态：已合并"
            else:
                _st_line = ("⏳ 状态：已接收，仅入库 —— 未自动翻译"
                            "（设置页「Webhook 入库后自动翻译」未开启；可在库页点「全部翻译」手动触发）")
                _delay_line = (f"🕒 延迟：约 {_delay} 秒后开始入库（等待 Emby 刮削/文件落位；此延迟与翻译无关）")
                _st_merge = "⏳ 状态：已合并（仅入库，未自动翻译）"
            if _all_movies:
                if _is_reset:
                    text = (f"📥 又有 {total} 条入库事件（已并入本轮）\n"
                            f"{_items_txt}\n"
                            f"{_st_merge}\n"
                            f"🔄 计时重置：重新等待约 {_delay} 秒后开始")
                else:
                    text = (f"📥 收到 {total} 条入库事件\n"
                            f"{_items_txt}\n"
                            f"{_st_line}\n"
                            f"{_delay_line}")
            elif _is_reset:
                text = (f"📥 又有 {total} 条入库事件（已并入本轮）\n"
                        f"{_items_txt}\n"
                        f"{_st_merge}，同剧会统一处理\n"
                        f"🔄 计时重置：重新等待约 {_delay} 秒后开始（避免边下边翻）")
            else:
                text = (f"📥 收到 {total} 条入库事件\n"
                        f"{_items_txt}\n"
                        f"{_st_line}\n"
                        f"{_delay_line}（期间同剧新集自动合并并重置计时）")
            self.post_message(mtype=NotificationType.Manual, title=self.plugin_name, text=text)
        except Exception as e:
            logger.debug(f"[Webhook] 接收通知聚合发送失败（非致命）: {e}")

    @staticmethod
    def _emby_date_ts(s) -> Optional[float]:
        """Emby 时间戳（如 `2026-10-08T16:24:48.5607219Z`）→ epoch 秒（UTC）；解析失败返回 None。

        v4.6.89：整剧入库「只收新增」用它判断集的加入时间。手写正则解析（只取到秒），
        兼容 3.10 的 `fromisoformat` 不认 `Z` 与 7 位小数秒的情况。"""
        _t = str(s or "").strip()
        if not _t:
            return None
        try:
            from datetime import datetime, timezone
            _m = re.match(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})", _t)
            if not _m:
                return None
            return datetime(int(_m.group(1)), int(_m.group(2)), int(_m.group(3)),
                            int(_m.group(4)), int(_m.group(5)), int(_m.group(6)),
                            tzinfo=timezone.utc).timestamp()
        except Exception:
            return None

    def _filter_new_episodes(self, eps: list) -> tuple:
        """整剧入库「只收新增」（v4.6.89）：按 Emby `DateCreated` 过滤出**最近加入**的集。

        :return: (保留的集, 跳过的旧集数)
        - 有日期且早于阈值 → 旧集，跳过；
        - 无日期字段 / 解析失败 → 视为新集（宁可多收，也不漏掉用户刚加的）；
        - 整批一个可用日期都没有 → 退回整剧入库（原样返回，跳过数 0），行为不劣于旧版。
        """
        try:
            _look = float(getattr(constants, "SERIES_NEW_ONLY_LOOKBACK_HOURS", 168) or 168)
        except Exception:
            _look = 168.0
        _cut = time.time() - _look * 3600.0
        _keep, _old, _dated = [], 0, 0
        for _e in (eps or []):
            _ts = self._emby_date_ts((_e or {}).get("DateCreated")) if isinstance(_e, dict) else None
            if _ts is None:
                _keep.append(_e)
                continue
            _dated += 1
            if _ts >= _cut:
                _keep.append(_e)
            else:
                _old += 1
        if not _dated:
            return list(eps or []), 0
        return _keep, _old

    def _decide_series_ingest(self, eps: list, added_count: int = 0) -> tuple:
        """Webhook「整剧入库」收词决策 —— 三条规则（v4.6.92，用户拍板）。

        ① 开了「整剧全收」→ 全收（开关语义）；
        ② 没开：通知数量 N ≥ 集总数 → **整剧都是新加的** → 全收
           （用户实测：资源包自带旧时间戳会让「刚入库的整剧」被判成全旧集，v4.6.90
            因此把一整部新剧（某剧）全跳过 —— 数量对得上时直接全收，最稳）；
        ③ 否则按 Emby 加入时间挑新增（挑到几个收几个）；
        ④ 一个都挑不出来（全为旧时间 / 时间不可靠）→ **兜底全收** ——
           宁可多收，绝不出现「新加了东西却一个没收」。

        :return: (要入库的集, 跳过的旧集数, 判定说明) —— 说明为空时不追加日志。
        """
        _eps = list(eps or [])
        if not _eps:
            return _eps, 0, ""
        if bool(getattr(self, "_series_ingest_all", False)):
            return _eps, 0, ""
        _total = len(_eps)
        try:
            _n = int(added_count or 0)
        except Exception:
            _n = 0
        if _n and _n >= _total:
            return _eps, 0, f"判定整剧新入库：通知 {_n} 项 ≥ 本剧 {_total} 集 → 全收"
        try:
            _keep, _old = self._filter_new_episodes(_eps)
        except Exception:
            _keep, _old = list(_eps), 0
        if not _keep:
            return _eps, 0, f"时间认不出新增（{_total} 集全为旧时间）→ 兜底全收"
        if _old:
            try:
                _look = int(getattr(constants, "SERIES_NEW_ONLY_LOOKBACK_HOURS", 168) or 168)
            except Exception:
                _look = 168
            return _keep, _old, (f"只收新增：保留 {len(_keep)} 集 / 跳过 {_old} 个旧集"
                                 f"（Emby 加入时间早于 {_look} 小时前）")
        return _keep, 0, ""

    @staticmethod
    def _seasons_range_txt(seasons) -> str:
        """把季号集合压成紧凑描述（v4.6.87）。

        连续段用「–」连写、不连续用「、」分隔：
          [1,2,3,4] → "S01–S04"；[1,3] → "S01、S03"；[1] → "S01"；空/脏值 → ""。
        用于「整剧入库」事件/日志/通知里标明覆盖了哪几季（多季时尤其直观）。"""
        try:
            _ss = sorted({int(x) for x in (seasons or []) if x is not None})
        except Exception:
            return ""
        if not _ss:
            return ""
        _parts, _start, _prev = [], _ss[0], _ss[0]
        for _x in _ss[1:]:
            if _x == _prev + 1:
                _prev = _x
                continue
            _parts.append((_start, _prev))
            _start = _prev = _x
        _parts.append((_start, _prev))
        _out = []
        for _a, _b in _parts:
            _out.append(f"S{_a:02d}" if _a == _b else f"S{_a:02d}–S{_b:02d}")
        return "、".join(_out)

    def _describe_group_eps(self, members: list) -> str:
        try:
            eps = []
            seasons = set()
            for m in members or []:
                _b = m.get("brief") or {}
                _s = _b.get("season")
                _e = _b.get("episode")
                if _s is not None:
                    try:
                        seasons.add(int(_s))
                    except Exception:
                        pass
                if _e is not None:
                    try:
                        eps.append(int(_e))
                    except Exception:
                        pass
            if not eps:
                return f"{len(members)} 集"
            eps_sorted = sorted(set(eps))
            s_txt = ""
            if len(seasons) == 1:
                s_txt = f"S{list(seasons)[0]}"
            elif len(seasons) > 1:
                s_txt = f"S{min(seasons)}-S{max(seasons)}"
            if len(eps_sorted) == 1:
                e_txt = f"E{eps_sorted[0]}"
            elif eps_sorted == list(range(eps_sorted[0], eps_sorted[-1] + 1)):
                e_txt = f"E{eps_sorted[0]}-{eps_sorted[-1]}"
            else:
                e_txt = "E" + ",E".join(str(x) for x in eps_sorted[:8])
            return f"{s_txt}{e_txt}"
        except Exception:
            return f"{len(members)} 集"

    def _webhook_worker(self):
        """
        Webhook 单 Worker 线程 - 消费延迟调度队列
        避免一事件一线程导致的线程爆炸
        """
        logger.info("[Webhook] Worker 线程已启动")
        while not self._webhook_worker_event.is_set():
            if not getattr(self, "_enabled", False):
                with self._webhook_lock:
                    if self._webhook_schedule:
                        logger.info(f"[Webhook] 插件已关闭，丢弃 {len(self._webhook_schedule)} 个未处理任务")
                    self._webhook_schedule.clear()
                logger.info("[Webhook] 插件已关闭，Worker 停止消费（不再监测入库事件）")
                break
            if not getattr(self, "_webhook_enabled", False):
                self._webhook_worker_event.wait(1.0)
                continue
            now = time.time()
            if getattr(self, "_pool_pulling", False):
                self._webhook_worker_event.wait(1.0)
                continue
            due: List[Tuple[str, Dict]] = []
            with self._webhook_lock:
                for item_id, info in list(self._webhook_schedule.items()):
                    if info["execute_at"] <= now:
                        due.append((item_id, info))
                for item_id, info in due:
                    self._webhook_schedule.pop(item_id, None)
            if not due:
                if self._stop_requested and not self._is_running:
                    self._stop_requested = False
                # 没有到时间的任务，sleep 1秒
                self._webhook_worker_event.wait(1.0)
                continue

            merged: Dict[str, dict] = {}
            for pending_item, pending_info in due:
                item_id = pending_info.get("item_id", pending_item)
                server_id = pending_info.get("server_id") or ""
                delay = pending_info.get("delay") or self._webhook_delay
                _brief = pending_info.get("brief") or {}
                # v4.6.92：通知里的新增数量随事件带给「整剧展开」（整剧入库判定用）
                try:
                    _added_n = int(pending_info.get("added_count") or 0)
                except Exception:
                    _added_n = 0
                _sname = str(_brief.get("series_name") or "").strip()
                _mkey = f"{server_id}:{_sname}" if _sname else ""
                logger.info(f"[Webhook] 开始执行: ItemId={item_id}, Server={server_id}")
                if _mkey:
                    # 同剧聚合：收拢到一组（组内每事件各自精确处理对应集的 nfo 文件）
                    if _mkey not in merged:
                        merged[_mkey] = {"series_name": _sname, "server_id": server_id, "members": []}
                    merged[_mkey]["members"].append({"item_id": item_id, "server_id": server_id,
                                                     "delay": delay, "brief": dict(_brief),
                                                     "added_count": _added_n})
                    continue
                try:
                    self._webhook_translate_worker(item_id, server_id, delay, _added_n)
                except Exception as e:
                    logger.error(f"[Webhook] Worker 执行异常: {e}\n{traceback.format_exc()}")
                    self._webhook_failed += 1
            for _mkey, _grp in merged.items():
                try:
                    _members = list(_grp.get("members") or [])
                    _sname = str(_grp.get("series_name") or "")
                    if len(_members) > 1:
                        _eps_txt = self._describe_group_eps(_members)
                        logger.info(f"[Webhook] 启动整合翻译：{_sname}（{len(_members)} 集 {_eps_txt}）")
                        # v4.6.84（用户实测）：整合只把**各成员已接收的那一行**原地改为「处理中」，
                        # 不再用合成键 `_mkey` 另起一行（否则会多出一条永远停在「处理中」的事件行）。
                        for _mm in _members:
                            self._update_or_push_webhook_event(
                                str(_mm.get("item_id") or ""), _sname, "running",
                                f"整合翻译启动：{len(_members)} 集合并收集词条（{_eps_txt}）",
                                series_name=_sname)
                        if getattr(self, "_notify_on_complete", False):
                            try:
                                self.post_message(
                                    mtype=NotificationType.Manual,
                                    title=self.plugin_name,
                                    text=(f"🔗 启动整合翻译：{_sname}\n"
                                          f"📥 本批聚合：{len(_members)} 个入库事件（{_eps_txt}）\n"
                                          f"⏳ 状态：正在合并收集全部集词条，随后统一翻译"
                                          f"（避免逐集多次调用 AI）")
                                )
                            except Exception:
                                pass
                    self._webhook_group_translate(_grp)
                except Exception as e:
                    logger.error(f"[Webhook] 剧聚合处理异常: {e}\n{traceback.format_exc()}")
                    self._webhook_failed += 1

        logger.info("[Webhook] Worker 线程已退出")

    def _webhook_group_translate(self, group: dict) -> None:
        """同剧聚合处理（零散多集入库）—— webhook_delay 窗口内陆续到达的
        3-4 集归到同一组 → 逐个 fetch + 定位 nfo，收集全部集词条合并翻译一次
        （与整季展开共用 _batch_translate_nfo_files，不再逐集调用 LLM）。"""
        try:
            _sname = str(group.get("series_name") or "")
            _members = list(group.get("members") or [])
            if not _members:
                return
            logger.info(f"[Webhook] 同剧聚合处理：{_sname}（{len(_members)} 个成员，合并翻译模式）")

            nfo_items = []
            _first_item = None
            _pending_eps = []
            _missing_cnt = 0
            for _m in _members:
                if getattr(self, "_stop_requested", False):
                    return
                item_id = str(_m.get("item_id") or "")
                server_id = str(_m.get("server_id") or "")
                services = self._get_all_emby_services()
                if not services:
                    self._webhook_failed += 1
                    continue
                svc = self._find_target_server(services, server_id)
                if svc is None:
                    self._webhook_skipped += 1
                    self._push_webhook_event(item_id, f"Item_{item_id}", "skipped",
                                             f"未匹配到 server_id={server_id} 的 Emby 服务器，已跳过（不改名到错误服务器）")
                    continue
                client = EmbyClient(self._get_service_url(svc), self._get_service_api_key(svc), svc,
                                    user_id=self._get_service_user_id(svc), use_proxy=self._use_proxy)
                item = client.fetch_item(item_id)
                if not item:
                    if self._schedule_webhook_retry(item_id, server_id, 60,
                                                    f"Item_{item_id}", "item"):
                        continue
                    self._webhook_failed += 1
                    self._push_webhook_event(item_id, f"Item_{item_id}", "failed",
                                             "条目未就绪（重试 2 次后放弃），跳过")
                    continue
                item = self._normalize_webhook_item(item, server_id)
                if not self._in_selected_library(str(item.get("Path") or "")):
                    self._webhook_skipped += 1
                    self._push_webhook_event(item_id, str(item.get("Name") or item_id), "skipped",
                                             "未选择该媒体库，已忽略",
                                             series_name=str(item.get("SeriesName") or ""),
                                             season=item.get("ParentIndexNumber"),
                                             episode=item.get("IndexNumber"))
                    continue
                if _first_item is None:
                    _first_item = item
                itype = str(item.get("Type") or "").lower()
                if itype in ("series", "tvshow", "season") or itype.startswith("season"):
                    # Series 级成员 → 单独走展开（合并翻译；有界线程池不独占 worker）
                    _m_added = 0
                    try:
                        _m_added = int(_m.get("added_count") or 0)
                    except Exception:
                        _m_added = 0
                    self._submit_series_expand(client, item, item_id, server_id,
                                               item.get("Name") or item_id, added_count=_m_added)
                    continue
                nf = self._locate_nfo_from_item(item)
                if not nf:
                    _dt = item.get("Name") or item_id
                    if self._schedule_webhook_retry(item_id, server_id, 60, _dt, "nfo", item):
                        continue
                    _expect = os.path.splitext(str(item.get("Path") or "").replace("\\", "/"))[0] + ".nfo"
                    _missing_cnt += 1
                    self._webhook_failed += 1
                    logger.warning(f"[Webhook] 未找到本地 nfo（重试 2 次后放弃）: {_expect}")
                    self._push_webhook_event(item_id, _dt, "failed",
                                             f"未找到 nfo（重试 2 次后放弃），预期路径：{_expect}",
                                             series_name=str(item.get("SeriesName") or ""),
                                             season=item.get("ParentIndexNumber"),
                                             episode=item.get("IndexNumber"))
                    if getattr(self, "_notify_on_complete", False):
                        try:
                            self.post_message(mtype=NotificationType.Manual, title=self.plugin_name,
                                              text=f"❌ 翻译失败：{_dt}\n"
                                                   f"• 类型：{str(item.get('Type') or 'Episode')}\n"
                                                   f"• 未找到 nfo（已重试 2 次）：{_expect}\n"
                                                   f"• 请确认 Emby 已刮削完成、该文件确实存在")
                        except Exception:
                            pass
                    continue
                from . import nfo as nfo_engine
                lv = nfo_engine.classify(nf)
                nfo_items.append((nf, lv))
                _pending_eps.append((item_id, server_id, item))

            if not nfo_items:
                return
            _entries = []
            for _idx, (_nf2, _lvn2) in enumerate(nfo_items):
                if _idx < len(_pending_eps):
                    _iid2, _sid2, _it2 = _pending_eps[_idx]
                else:
                    _iid2, _sid2, _it2 = "", "", _first_item
                _entries.append((_nf2, _lvn2, _iid2, _sid2, _it2))
            res = self._ingest_nfo_batch(_entries, trigger=self._nfo_ingest_trigger())
            _pl = int(res.get("pending_left") or 0)
            logger.info(f"[Webhook] 同剧聚合入库完成：{_sname}（{len(nfo_items)} 个 nfo，"
                        f"{res['done']} 入库成功/{res['fail']} 失败，{self._ingest_tx_phrase(self._nfo_ingest_trigger(), _pl)}）")
            with self._webhook_lock:
                for _item_id, _sid2, _ in _pending_eps:
                    _rk = self._wh_retry_key(_sid2, _item_id)
                    self._webhook_retry_map.pop(_rk, None)
                    self._webhook_retry_first.pop(_rk, None)
            if res['done']:
                self._webhook_processed += 1
            if res['fail']:
                self._webhook_failed += 1
            self._push_log("INFO", f"Webhook 聚合合并翻译完成：{_sname}（{len(nfo_items)} 个 nfo，"
                                   f"成功 {res['done']} 失败 {res['fail']}，"
                                   f"{self._ingest_tx_phrase(self._nfo_ingest_trigger(), _pl)}）")
            for _iid, _sid, _it in _pending_eps:
                try:
                    self._remove_missing_event(series_name=str(_it.get("SeriesName") or ""),
                                               season=_it.get("ParentIndexNumber"),
                                               episode=_it.get("IndexNumber"),
                                               title=str(_it.get("Name") or ""),
                                               server_id=str(_sid or ""), item_id=str(_iid or ""))
                    self._update_or_push_webhook_event(
                        _iid, str(_it.get("Name") or _iid),
                        "done" if res['done'] else "failed",
                        ((f"聚合翻译完成，改动 {res['changed']} 条" +
                          (f"，{self._ingest_tx_phrase(self._nfo_ingest_trigger(), _pl)}" if _pl else "")) if res['done'] else "聚合翻译失败，见日志"),
                        series_name=str(_it.get("SeriesName") or ""),
                        season=_it.get("ParentIndexNumber"), episode=_it.get("IndexNumber"))
                except Exception:
                    pass
            # v4.6.67（P0-C）：入库阶段没有「翻译词条数」—— translated 恒 0，
            # 入库文件数走 ingested；真正的翻译统计由常驻 worker 完成后单独推送。
            self._notify_webhook_completed(
                str(_first_item.get("Id") or "group") if _first_item else "group",
                _sname or "聚合任务", 0, res['fail'] + _missing_cnt, _first_item,
                recovered=int(res.get("recovered", 0) or 0),
                llm_calls=res['llm_calls'], zhconv=res['zhconv'], batch=True,
                pool=res.get('pool_hit', 0), pending_left=_pl,
                existing=res.get('translated_existing', 0),
                collected=int(res.get('names_count', 0)) + int(res.get('roles_count', 0)),
                ingested=int(res.get('done') or 0))
        except Exception as e:
            logger.error(f"[Webhook] 剧聚合处理失败: {e}\n{traceback.format_exc()}")
            self._webhook_failed += 1

    def _dir_in_nfo_roots(self, path: str) -> bool:
        """目录是否在有效 NFO 根目录下（前缀匹配，分隔符归一）。
        有效根目录 = 选中库的自动路径 ∪ 手动 nfo_roots ——
        选了库之后，库 Path 自动成为门禁白名单，无需再手填。
        作为 Webhook 门禁：先确认目录已配置，再决定要不要处理该入库事件。
        P0 修复 —— 原实现 roots 只 rstrip（保留前导 /），而调用方传入的
        路径已 strip("/")（丢了前导 /），前缀比较恒失败 → 所有 Webhook 入库被误判
        「库路径映射不命中」挂起「待配置」，且「继续处理」同样失效。现两边统一
        strip("/")（与 _in_selected_library 同口径），彻底消除不对称。"""
        try:
            roots = [str(x).replace("\\", "/").strip("/")
                     for x in self._all_nfo_roots() if str(x or "").strip()]
            if not roots:
                return False
            p = str(path or "").replace("\\", "/").strip("/")
            if not p:
                return False
            for r in roots:
                if r and (p == r or p.startswith(r + "/")):
                    return True
            return False
        except Exception:
            return False

    @staticmethod
    def _wh_retry_key(server_id: str, item_id: str) -> str:
        """Webhook 重试计数键 —— 与调度表同用复合键（WH-001）：
        多服务器出现同 item_id 时各自独立重试预算，互不消耗/互不清零。"""
        _i = str(item_id or "")
        _s = str(server_id or "")
        return f"{_s}:{_i}" if _s else _i

    def _schedule_webhook_retry(self, item_id: str, server_id: str, delay: int,
                                display_title: str, kind: str,
                                item: Optional[dict] = None) -> bool:
        """Webhook 条目/nfo/写盘延迟重试。
        重试收敛为最多 2 次（60s/120s）—— 用户实测「60/120/240/480/600 共约
        25 分钟空转」不可接受；超过 2 次直接返回 False，由调用方发❌失败通知（带
        完整 nfo 路径与 Item 类型）并结束，不再占用 worker 线程。
        :param kind: "item"=条目尚未就绪 / "nfo"=未找到 nfo / "write"=写盘失败
        """
        try:
            _MAX = 2
            _rk = self._wh_retry_key(server_id, item_id)
            with self._webhook_lock:
                n = self._webhook_retry_map.get(_rk, 0) + 1
                if n > _MAX:
                    self._webhook_retry_map.pop(_rk, None)
                    self._webhook_retry_first.pop(_rk, None)
                    return False
                self._webhook_retry_map[_rk] = n
                nd = 60 if n == 1 else 120  # 60/120，不再指数放大到 240/480/600
                skey = _rk
                self._webhook_schedule[skey] = {
                    "execute_at": time.time() + nd,
                    "server_id": server_id,
                    "item_id": item_id,
                    "delay": nd,
                    "brief": {},  # 重放任务走单条路径
                }
            if kind == "item":
                _msg = f"条目尚未就绪（Emby 刮削/文件未落位），{nd} 秒后重试（第 {n} 次）"
            elif kind == "write":
                _msg = f"nfo 写盘失败（文件可能被 Emby 占用），{nd} 秒后重试（第 {n} 次）"
            else:
                _msg = f"未找到集 nfo 文件，等待 Emby 刮削完成后自动处理（{nd} 秒后重试，第 {n} 次）"
            self._update_or_push_webhook_event(item_id, display_title, "waiting", _msg,
                                               series_name=str((item or {}).get("SeriesName") or ""),
                                               season=(item or {}).get("ParentIndexNumber"),
                                               episode=(item or {}).get("IndexNumber"))
            logger.info(f"[Webhook] {display_title}: {_msg}")
            return True
        except Exception:
            return False

    def _hold_pending_config(self, item_id: str, server_id: str, item: dict, display_title: str):
        """目录未配置 → 挂起等配置（不丢弃）；持久化到 state.json。
        只存不发重试，同时归并一条通知提醒用户去配置，配置后由用户在 UI 点「继续处理」。"""
        try:
            _p = str(item.get("Path") or "")
            key = f"{server_id}:{item_id}" if server_id else item_id
            with self._webhook_lock:
                self._webhook_pending_config[key] = {
                    "item_id": item_id,
                    "server_id": server_id,
                    "time": time.time(),
                    "path": _p,
                    "name": str(item.get("Name") or display_title or ""),
                    "series_name": str(item.get("SeriesName") or ""),
                    "season": item.get("ParentIndexNumber"),
                    "episode": item.get("IndexNumber"),
                }
                self._webhook_pending_notify_count = getattr(self, "_webhook_pending_notify_count", 0) + 1
                if getattr(self, "_webhook_pending_timer", None):
                    try:
                        self._webhook_pending_timer.cancel()
                    except Exception:
                        pass
                self._webhook_pending_timer = threading.Timer(5.0, self._notify_pending_config)
                self._webhook_pending_timer.daemon = True
                self._webhook_pending_timer.start()
            self._update_or_push_webhook_event(item_id, display_title, "waiting",
                                               "该目录不在已选媒体库的映射路径内（可能容器挂载不一致），已挂起等待：调整「路径前缀替换」后到本页点「继续处理」",
                                               series_name=str(item.get("SeriesName") or ""),
                                               season=item.get("ParentIndexNumber"), episode=item.get("IndexNumber"))
            self._push_log("WARNING", f"Webhook 挂起（库路径映射不命中）：{display_title}（{_p}）—— 请到设置页检查「路径前缀替换」")
            logger.warning(f"[Webhook] 库路径映射不命中，事件挂起等待: {display_title}（{_p}）")
            self._save_state()
        except Exception as e:
            logger.warning(f"[Webhook] 挂起事件失败（非致命）: {e}")

    def _notify_pending_config(self):
        """发送挂起提醒通知（批量子里合并一条，避免逐条刷屏）。"""
        try:
            with self._webhook_lock:
                _n = getattr(self, "_webhook_pending_notify_count", 0) or 0
                self._webhook_pending_notify_count = 0
                self._webhook_pending_timer = None
            if _n and getattr(self, "_notify_on_complete", False):
                self.post_message(
                    mtype=NotificationType.Manual,
                    title=self.plugin_name,
                    text=f"⚠️ 有 {_n} 个 Emby 入库事件因目录映射不命中而挂起。\n"
                         f"请到设置页确认已选择该媒体库，必要时调整「路径前缀替换」；\n"
                         f"然后到「仪表盘 → Webhook 最近事件」点「继续处理」开始自动翻译。\n"
                         f"（不想处理可点「放弃全部」清除挂起）"
                )
        except Exception:
            pass

    def _api_webhook_pending(self):
        """挂起的「未配置目录」事件列表（供 UI 提示条/继续按钮）。"""
        try:
            items = []
            with self._webhook_lock:
                for _k, _i in (getattr(self, "_webhook_pending_config", None) or {}).items():
                    items.append({"name": _i.get("name") or "", "series_name": _i.get("series_name") or "",
                                  "path": _i.get("path") or "", "time": _i.get("time")})
            return {"success": True, "data": {"count": len(items), "items": items[:50]}}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_webhook_pending_continue(self, data: Optional[dict] = None):
        """用户配置完根目录后，手动「继续处理」挂起事件。"""
        _g = self._api_gate()
        if _g:
            return _g
        try:
            n = self._reprocess_pending_config()
            with self._webhook_lock:
                left = len(getattr(self, "_webhook_pending_config", None) or {})
            if n:
                msg = f"已恢复 {n} 个挂起事件，开始自动处理"
                if left:
                    msg += f"，另 {left} 个仍不在已配置根目录内（请确认目录已加入后再次点击）"
            else:
                msg = "当前没有可恢复的挂起事件" if not left else f"挂起事件仍不在已选媒体库的映射路径内（共 {left} 个），请检查「路径前缀替换」或直接点「放弃全部」"
            return {"success": True, "message": msg, "data": {"restored": n, "left": left}}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_webhook_pending_clear(self, data: Optional[dict] = None):
        """放弃全部挂起的「待配置」事件 —— 清空 pending 列表并移除事件列表中
        对应的 waiting 行（用户明确不要这些事件继续处理；此前只能等「继续处理」，
        路径映射有问题时点继续无效果，待配置徽标永远挂着删不掉）。"""
        _g = self._api_gate()
        if _g:
            return _g
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            with self._webhook_lock:
                _pcfg = dict(getattr(self, "_webhook_pending_config", None) or {})
                n = len(_pcfg)
                _hold_item_ids = set()
                for _k, _v in _pcfg.items():
                    _hold_item_ids.add(str((_v or {}).get("item_id") or str(_k).split(":")[-1]))
                self._webhook_pending_config = {}
            # 事件列表：移除「挂起」waiting 行（重试中的 waiting 行保留），其余保留
            try:
                events = getattr(self, "_webhook_events", None)
                if events is not None:
                    events[:] = [e for e in events
                                 if not (str(e.get("status")) == "waiting"
                                         and str(e.get("item_id")) in _hold_item_ids)]
            except Exception:
                pass
            try:
                self._save_state()
            except Exception:
                pass
            self._push_log("INFO", f"已放弃 {n} 个挂起的入库事件（待配置列表已清空）")
            return {"success": True, "message": f"已放弃 {n} 个挂起事件（如需重新处理，再次入库触发即可）",
                    "data": {"cleared": n}}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _reprocess_pending_config(self) -> int:
        """根目录配置变化后调用 —— 把挂起的「未配置目录」事件放回调度自动续跑。"""
        try:
            if not getattr(self, "_webhook_pending_config", None):
                return 0
            due_keys = []
            with self._webhook_lock:
                for key, info in list(self._webhook_pending_config.items()):
                    _p = str(info.get("path") or "").replace("\\", "/").strip("/")
                    _dir = _p.rsplit("/", 1)[0] if "/" in _p else _p
                    if not self._dir_in_nfo_roots(_dir):
                        continue
                    item_id = str(info.get("item_id") or "")
                    server_id = str(info.get("server_id") or "")
                    skey = f"{server_id}:{item_id}" if server_id else item_id
                    if skey not in self._webhook_schedule:
                        _d = max(10, int(getattr(self, "_webhook_delay", 60) or 60))
                        self._webhook_schedule[skey] = {
                            "execute_at": time.time() + _d,
                            "server_id": server_id,
                            "item_id": item_id,
                            "delay": _d,
                            "brief": {},
                        }
                    due_keys.append(key)
                for k in due_keys:
                    self._webhook_pending_config.pop(k, None)
                if due_keys and (self._webhook_worker_thread is None
                                 or not self._webhook_worker_thread.is_alive()):
                    self._webhook_worker_event.clear()
                    self._webhook_worker_thread = threading.Thread(target=self._webhook_worker,
                                                                   daemon=True, name="webhook-worker")
                    self._webhook_worker_thread.start()
            if due_keys:
                self._save_state()
                logger.info(f"[Webhook] 根目录已配置，恢复 {len(due_keys)} 个挂起事件")
                self._push_log("INFO", f"配置完成，已恢复 {len(due_keys)} 个挂起的入库事件，将自动继续处理")
            return len(due_keys)
        except Exception as e:
            logger.warning(f"[Webhook] 恢复挂起事件失败: {e}")
            return 0

    def _start_maintenance(self):
        try:
            if getattr(self, "_maintenance_thread", None) and self._maintenance_thread.is_alive():
                return
            self._maintenance_stop = threading.Event()
            self._maintenance_thread = threading.Thread(target=self._maintenance_worker,
                                                        daemon=True, name="epl-maintenance")
            self._maintenance_thread.start()
        except Exception as e:
            logger.warning(f"[NFO] 后台维护线程启动失败: {e}")

    def _maintenance_worker(self):
        while not getattr(self, "_maintenance_stop", threading.Event()).is_set():
            try:
                if getattr(self, "_enabled", False):
                    self._maintenance_pass()
            except Exception:
                pass
            self._maintenance_stop.wait(3600)

    def _start_schedule_daemon(self):
        try:
            if getattr(self, "_schedule_thread", None) and self._schedule_thread.is_alive():
                return
            self._schedule_stop = threading.Event()
            self._schedule_thread = threading.Thread(target=self._schedule_worker,
                                                     daemon=True, name="epl-schedule")
            self._schedule_thread.start()
        except Exception as e:
            logger.warning(f"[NFO] 定时扫库线程启动失败: {e}")

    def _schedule_worker(self):
        while not getattr(self, "_schedule_stop", threading.Event()).is_set():
            try:
                if getattr(self, "_enabled", False) and getattr(self, "_schedule_enabled", False):
                    self._run_scheduled_scan()
            except Exception:
                pass
            self._schedule_stop.wait(60)

    def _run_scheduled_scan(self):
        """单轮定时扫库判定：到点且空闲才触发，忙则跳过本轮（下周期再试）。

        v4.6.67（P0-B）：一律按「上次执行时刻 + 设置间隔」判定。
        此前对 interval>=24h 走「每天 04:00 后未跑过则触发」的日历逻辑 ——
        用户把「间隔小时」设成 48 / 72 时并不会真的等 48/72 小时，而是被改成每天一次，
        设置语义与用户预期不符。_last_full_scan_ts 已持久化到 state（重启不重新计时），
        因此无需再用凌晨锚点绕过「MP 重启即重新计时」的问题。"""
        try:
            now = time.time()
            interval = max(1, int(getattr(self, "_schedule_interval_hours", 24) or 24)) * 3600
            last = float(getattr(self, "_last_full_scan_ts", 0) or 0)
            if now - last < interval:
                return   # 未到「上次执行 + 间隔」
            # 未选任何媒体库：无可扫范围，跳过（避免空转）
            if not self._all_nfo_roots():
                return
            # 互斥：后台已有任务（扫描/翻译/写回）则跳过本轮，下次周期再试
            with self._scan_lock:
                if self._is_running:
                    return
            self._last_full_scan_ts = now
            self._save_state()
            _h = int(interval // 3600)
            logger.info(f"[NFO] 定时全量扫库已触发（间隔 {_h} 小时，断点续扫增量，兜底漏入库条目）")
            self._push_log("INFO", f"定时全量扫库已触发（间隔 {_h} 小时，断点续扫增量，兜底关插件/漏接 webhook 期间的漏入库条目）")
            self._launch_nfo_worker({})
        except Exception as e:
            logger.warning(f"[NFO] 定时扫库失败: {e}")

    # ============================================================
    # ============================================================
    PROBE_MAX_FILES_PER_ROUND = 200   # 每轮补翻文件上限（超出的下轮继续）
    PROBE_REVERSE_MAX = 50
    PROBE_DEEP_MAX_AGE = 24 * 3600    # 深查最大间隔（防止「同数替换」永远漏检）

    def _start_probe_daemon(self):
        try:
            if getattr(self, "_probe_thread", None) and self._probe_thread.is_alive():
                return
            self._probe_stop = False          # 任务停止位（bool）
            self._probe_daemon_stop = threading.Event()   # daemon 专属退出事件
            self._probe_thread = threading.Thread(target=self._probe_worker,
                                                  daemon=True, name="epl-probe")
            self._probe_thread.start()
        except Exception as e:
            logger.warning(f"[Probe] 探测线程启动失败: {e}")

    def _probe_worker(self):
        """探测 daemon：每 60s 检查一次；到点且插件启用+开关打开才跑一轮。"""
        _stop_ev = getattr(self, "_probe_daemon_stop", None)
        if not isinstance(_stop_ev, threading.Event):
            _stop_ev = threading.Event()
            self._probe_daemon_stop = _stop_ev
        while not _stop_ev.is_set():
            try:
                if getattr(self, "_enabled", False) and getattr(self, "_probe_enabled", False):
                    now = time.time()
                    _iv = max(10, int(getattr(self, "_probe_interval_min", 60) or 60)) * 60
                    if now - float(getattr(self, "_probe_last_run", 0) or 0) >= _iv:
                        self._probe_execute(force_deep=False)
            except Exception:
                pass
            _stop_ev.wait(60)

    def _probe_execute(self, force_deep: bool = False) -> Optional[dict]:
        """占用运行位并同步执行一轮探测（daemon 与手动按钮共用；调用方决定线程）。"""
        with self._scan_lock:
            # 探测会补翻/写盘，与任何任务都冲突 → 仍按聚合位判断（v5：置位走独立 probe 位）
            if self._is_running:
                return {"success": False, "message": "已有任务正在运行（扫描/翻译/写回），本轮探测已跳过"}
            self._set_task_running("probe", True)
            self._probe_stop = False
        try:
            self._probe_status["running"] = True
            self._probe_status["current_title"] = "探测库中..."
            self._run_probe_round(force_deep=force_deep)
        except Exception as e:
            logger.warning(f"[Probe] 探测轮失败: {e}")
            return {"success": False, "message": str(e)}
        finally:
            with self._scan_lock:
                self._set_task_running("probe", False)
            self._probe_status["running"] = False
            self._probe_status["current_title"] = ""
        return None

    def _api_probe_run(self, data: Optional[dict] = None):
        """设置页「立即探测」—— 手动跑一轮（强制深查；后台线程执行，立即返回）。"""
        _g = self._api_gate()
        if _g:
            return _g
        with self._scan_lock:
            if self._is_running:
                return {"success": False, "message": "已有任务正在运行（扫描/翻译/写回），稍后再试"}
        try:
            threading.Thread(target=lambda: self._probe_execute(force_deep=True),
                             daemon=True, name="epl-probe-run").start()
        except Exception as e:
            return {"success": False, "message": str(e)}
        return {"success": True, "message": "探测已启动（后台执行；完成后见仪表盘日志与通知）"}

    def _probe_selected_libs(self) -> list:
        """已选中的媒体库（含 skey/lib_id/path，供探测按库查询）。"""
        try:
            want = set(str(x).strip() for x in (self._libraries or []) if str(x).strip())
            out = []
            for lib in (self._get_emby_libraries() or []):
                if lib.get("full_key") in want or lib.get("lib_id") in want:
                    out.append(lib)
            return out
        except Exception:
            return []

    def _probe_clients(self) -> Dict[str, Any]:
        """可用 Emby 客户端 {skey: EmbyClient}（多服务器并集）。"""
        out: Dict[str, Any] = {}
        try:
            for svc in (self._get_all_emby_services() or []):
                _u = self._get_service_url(svc)
                _k = self._get_service_api_key(svc)
                if _u and _k:
                    out[self._get_server_identifier(svc)] = EmbyClient(
                        _u, _k, svc, user_id=self._get_service_user_id(svc), use_proxy=self._use_proxy)
        except Exception:
            pass
        return out

    def _probe_light_counts(self, clients: Dict[str, Any], libs: list) -> Dict[str, int]:
        """轻查：选中库内 剧/电影/单集 总数（每库每类型 1 个小请求，Limit=1 只取总数）。"""
        counts: Dict[str, int] = {}
        for lib in libs:
            cli = clients.get(str(lib.get("skey") or ""))
            if cli is None:
                continue
            for _t in ("Series", "Movie", "Episode"):
                r = cli.query_items({"ParentId": lib.get("lib_id"), "Recursive": "true",
                                     "IncludeItemTypes": _t, "Limit": 1, "EnableImages": "false"})
                counts[f"{lib.get('skey')}:{lib.get('lib_id')}:{_t}"] = int(r.get("TotalRecordCount") or 0)
        return counts

    @staticmethod
    def _probe_item_keys(provider_ids: dict) -> List[str]:
        """Emby ProviderIds → 与插件库 item_id 同形的候选键（tmdb 裸数字 / tvdb: / imdb:）。"""
        out: List[str] = []
        try:
            p = provider_ids or {}
            _tm = str(p.get("Tmdb") or p.get("TMDB") or "").strip()
            if _tm:
                out.append(_tm)
            _tv = str(p.get("Tvdb") or p.get("TvDB") or "").strip()
            if _tv:
                out.append("tvdb:" + _tv)
            _im = str(p.get("Imdb") or p.get("IMDB") or "").strip().lower()
            if _im:
                out.append("imdb:" + _im)
        except Exception:
            pass
        return out

    def _probe_deep_collect(self, clients: Dict[str, Any], libs: list,
                            max_pages: int = 80) -> dict:
        """深查：分页拉选中库清单 —— 剧/电影（ProviderIds + Path）+ 单集（Path/SeriesId/季/集号）。
        返回 {"series": {canonical_key: rec}, "movies": {...}, "eps": {canonical_key: {(s,e): {...}}}}"""
        series: Dict[str, dict] = {}
        movies: Dict[str, dict] = {}
        eps: Dict[str, dict] = {}
        emby_id2key: Dict[tuple, str] = {}
        for lib in libs:
            skey = str(lib.get("skey") or "")
            cli = clients.get(skey)
            if cli is None:
                continue
            lib_id = str(lib.get("lib_id") or "")
            # 1) 剧 + 电影
            start = 0
            for _ in range(max_pages):
                if self._probe_stop:
                    break
                r = cli.query_items({"ParentId": lib_id, "Recursive": "true",
                                     "IncludeItemTypes": "Series,Movie",
                                     "Fields": "ProviderIds,Path", "StartIndex": start,
                                     "Limit": 500, "EnableImages": "false"})
                items = r.get("Items") or []
                total = int(r.get("TotalRecordCount") or 0)
                for it in items:
                    _keys = self._probe_item_keys(it.get("ProviderIds") or {})
                    if not _keys:
                        continue
                    _ck = _keys[0]
                    _is_series = str(it.get("Type") or "").lower() in ("series", "tvshow")
                    _rec = {"key": _ck, "keys": _keys,
                            "name": str(it.get("Name") or ""),
                            "path": self._normalize_webhook_path(skey, str(it.get("Path") or "")),
                            "emby_id": str(it.get("Id") or ""), "skey": skey}
                    _dst = series if _is_series else movies
                    if _ck not in _dst:
                        _dst[_ck] = _rec
                    else:
                        # 多服务器并集：候选键合并、路径取先有的非空
                        for _k in _keys:
                            if _k not in _dst[_ck]["keys"]:
                                _dst[_ck]["keys"].append(_k)
                        if not _dst[_ck].get("path") and _rec.get("path"):
                            _dst[_ck].update(_rec)
                    if _is_series and _rec["emby_id"]:
                        emby_id2key[(skey, _rec["emby_id"])] = _ck
                start += len(items)
                if not items or start >= total:
                    break
            # 2) 单集
            start = 0
            for _ in range(max_pages):
                if self._probe_stop:
                    break
                r = cli.query_items({"ParentId": lib_id, "Recursive": "true",
                                     "IncludeItemTypes": "Episode",
                                     "Fields": "Path,SeriesId,ParentIndexNumber,IndexNumber",
                                     "StartIndex": start, "Limit": 1000, "EnableImages": "false"})
                items = r.get("Items") or []
                total = int(r.get("TotalRecordCount") or 0)
                for it in items:
                    _k = emby_id2key.get((skey, str(it.get("SeriesId") or "")))
                    if not _k:
                        continue
                    try:
                        _s = int(it.get("ParentIndexNumber"))
                        _e = int(it.get("IndexNumber"))
                    except Exception:
                        continue
                    if _s == 0:
                        continue   # 特别篇（S0）默认忽略，避免误报缺口
                    eps.setdefault(_k, {})
                    if (_s, _e) not in eps[_k]:
                        eps[_k][(_s, _e)] = {
                            "path": self._normalize_webhook_path(skey, str(it.get("Path") or "")),
                            "emby_id": str(it.get("Id") or ""), "skey": skey}
                start += len(items)
                if not items or start >= total:
                    break
        return {"series": series, "movies": movies, "eps": eps}

    def _probe_make_ep_target(self, rec: dict, ep: dict, s: int, e: int) -> Optional[dict]:
        """把一个 Emby 单集转成补翻目标（路径归一化 + 库白名单 + nfo 定位 + 防重复）。"""
        path = str(ep.get("path") or "")
        if not path or not self._in_selected_library(path):
            return None
        nfo = self._locate_nfo_from_item({"Path": path, "Type": "Episode"})
        if not nfo or nfo in (self._probe_seen or {}):
            return None
        return {"kind": "ep", "path": nfo, "title": rec.get("name") or "",
                "series": rec.get("name") or "", "s": s, "e": e,
                "emby_id": ep.get("emby_id") or "", "skey": ep.get("skey") or "",
                "group": "series:" + str(rec.get("key") or "")}

    def _probe_diff(self, inventory: dict, dbkeys: dict) -> list:
        """对差：库里已有的剧比 (季,集) 集合补缺集；Emby 有库里没有的整条补（新剧含各集/新电影）。
        返回去重后的待补翻目标列表（按 nfo 路径去重）。"""
        db_items = set(dbkeys.get("items") or ())
        db_eps = dict(dbkeys.get("episodes") or {})
        targets: Dict[str, dict] = {}
        _series = inventory.get("series") or {}
        _eps_map = inventory.get("eps") or {}
        # 1) 已有剧：缺集
        for ckey, rec in _series.items():
            if not any(k in db_items for k in (rec.get("keys") or [])):
                continue
            _db_key = next((k for k in (rec.get("keys") or []) if k in db_eps), None)
            _have = (db_eps.get(_db_key) or set()) if _db_key else set()
            for (s, e), ep in sorted((_eps_map.get(ckey) or {}).items()):
                if (s, e) in _have:
                    continue
                _t = self._probe_make_ep_target(rec, ep, s, e)
                if _t:
                    targets.setdefault(_t["path"], _t)
        # 2) 全新剧：整部补（tvshow.nfo + 各集）
        for ckey, rec in _series.items():
            if any(k in db_items for k in (rec.get("keys") or [])):
                continue
            _tv = self._locate_nfo_from_item({"Path": rec.get("path") or "", "Type": "Series"})
            if _tv and _tv not in (self._probe_seen or {}):
                targets.setdefault(_tv, {
                    "kind": "item", "path": _tv, "title": rec.get("name") or "",
                    "series": rec.get("name") or "", "s": None, "e": None,
                    "emby_id": rec.get("emby_id") or "", "skey": rec.get("skey") or "",
                    "group": "new:" + ckey})
            for (s, e), ep in sorted((_eps_map.get(ckey) or {}).items()):
                _t = self._probe_make_ep_target(rec, ep, s, e)
                if _t:
                    _t["kind"] = "item"
                    _t["group"] = "new:" + ckey
                    targets.setdefault(_t["path"], _t)
        # 3) 全新电影
        for ckey, rec in (inventory.get("movies") or {}).items():
            if any(k in db_items for k in (rec.get("keys") or [])):
                continue
            _mv = self._locate_nfo_from_item({"Path": rec.get("path") or "", "Type": "Movie"})
            if _mv and _mv not in (self._probe_seen or {}):
                targets.setdefault(_mv, {
                    "kind": "item", "path": _mv, "title": rec.get("name") or "",
                    "series": "", "s": None, "e": None,
                    "emby_id": rec.get("emby_id") or "", "skey": rec.get("skey") or "",
                    "group": "new:" + ckey})
        return list(targets.values())

    def _run_probe_round(self, force_deep: bool = False) -> dict:
        """一轮探测：轻查 → （按需）深查 → 对差 → 补翻（≤200 文件）→ 通知/事件登记。"""
        _pid = self.__class__.__name__
        now = time.time()
        res: Dict[str, Any] = {"found": 0, "done": 0, "failed": 0, "rest": 0, "deep": False, "fails": []}
        self._probe_last_run = now
        try:
            db = getattr(self, "_people_db", None)
            if db is None:
                return res
            # 安全阀：插件库为空不探测（防清库/刚装后把整个 Emby 库当「缺的」全翻一遍）
            try:
                _has_items = bool(db.library_items(plugin_id=_pid) or [])
            except Exception:
                _has_items = False
            if not _has_items:
                self._push_log("WARNING", "探测库已跳过：插件库为空 —— 请先执行一次「NFO 扫描」初始化采集（防止整库被当漏收录重翻）")
                self._save_state()
                return res
            libs = self._probe_selected_libs()
            clients = self._probe_clients()
            if not libs or not clients:
                return res
            # 1) 轻查：计数没变且 24h 内深查过 → 结束（稳态零开销）
            _before = dict(getattr(self, "_probe_counts", None) or {})
            counts = self._probe_light_counts(clients, libs)
            _changed = bool(counts) and bool(_before) and (counts != _before)
            if counts:
                self._probe_counts = counts
            _deep_due = (force_deep or (not _before) or _changed
                         or (now - float(getattr(self, "_probe_last_deep", 0) or 0) >= self.PROBE_DEEP_MAX_AGE))
            if not _deep_due:
                self._save_state()
                return res
            # 2) 深查 + 对差
            res["deep"] = True
            self._push_log("INFO", f"探测库：开始深查（{'手动触发' if force_deep else ('计数变化' if _changed else '距上次深查≥24h')}）")
            inventory = self._probe_deep_collect(clients, libs)
            keys = db.probe_keys(plugin_id=_pid)
            targets = self._probe_diff(inventory, keys)
            res["found"] = len(targets)
            try:
                _inv_s = len(inventory.get("series") or {})
                _inv_m = len(inventory.get("movies") or {})
                _inv_e = sum(len(v) for v in (inventory.get("eps") or {}).values())
                _db_i = len(keys.get("items") or ())
                _db_e = sum(len(v) for v in (keys.get("episodes") or {}).values())
                self._push_log("INFO",
                               f"探测库：Emby 清单 剧 {_inv_s} / 电影 {_inv_m} / 单集 {_inv_e}；"
                               f"插件库 条目 {_db_i} / 已收录集 {_db_e}；比对后待补 {res['found']} 个"
                               f"（探测只补「Emby 有、插件库没有」的缺口）")
            except Exception:
                pass
            # 惰性初始化 LLM（探测线程此前可能未初始化；「AI 翻译」关闭时仅池/繁转简，不中止）
            try:
                if self._ai_enabled() and self._llm is None:
                    self._init_llm()
            except Exception:
                pass
            # 3) 补翻（上限 200/轮，超额下轮继续）
            batch = targets[:self.PROBE_MAX_FILES_PER_ROUND]
            res["rest"] = max(0, len(targets) - len(batch))
            if not self._probe_stop:
                self._probe_reverse_mark(inventory, keys, res)
            self._probe_process(batch, res)
            self._probe_last_deep = time.time()
            self._save_state()
        except Exception as e:
            logger.warning(f"[Probe] 探测轮异常: {e}")
        return res

    def _probe_reverse_mark(self, inventory: dict, dbkeys: dict, res: dict) -> int:
        """反向检查 —— 剧在 Emby 存在且**能拉到集**，但某集插件库有、Emby 没有：
        说明服务器已删除该集（可能漏接 library.deleted）→ 标记观察期 + 登记「失效/待恢复」行。
        安全阀：①拉不到集（0 集）的剧一律不判（避免未刮削/接口异常误判成删除）；
        ②每轮最多标 PROBE_REVERSE_MAX 集；③已标记过的（deleted_at 非空）不重复计数。"""
        try:
            db = getattr(self, "_people_db", None)
            if db is None:
                return 0
            _pid = self.__class__.__name__
            _series = inventory.get("series") or {}
            _eps_map = inventory.get("eps") or {}
            db_items = set(dbkeys.get("items") or ())
            db_eps = dict(dbkeys.get("episodes") or {})
            _gh = float(getattr(self, "_nfo_dead_grace_hours", 24) or 24)
            _now = time.time()
            _marked = 0
            _names: List[str] = []
            for ckey, rec in _series.items():
                _hit = [k for k in (rec.get("keys") or []) if k in db_items]
                if not _hit:
                    continue
                _emby_eps = _eps_map.get(ckey) or {}
                if not _emby_eps:
                    continue   # 该剧在 Emby 一集都没拉到 → 不判，避免误标
                _sn = str(rec.get("name") or "")
                for _dbk in _hit:
                    for (_s, _e) in sorted(db_eps.get(_dbk) or set()):
                        if _marked >= self.PROBE_REVERSE_MAX:
                            break
                        if _s == 0 or (_s, _e) in _emby_eps:
                            continue
                        _n = db.mark_deleted_by_episode(plugin_id=_pid, item_id=_dbk,
                                                        season_num=_s, episode_num=_e,
                                                        deleted_ts=_now,
                                                        server_id=str(rec.get("skey") or ""))
                        if _n > 0:
                            _marked += 1
                            self._push_webhook_event(
                                str(rec.get("emby_id") or ""), _sn or str(_dbk), "missing",
                                f"探测发现 Emby 已无该集（S{_s}E{_e}），标记观察期（{_gh:.0f} 小时）；"
                                f"期间重新入库会自动恢复，到期未恢复则清理",
                                series_name=_sn, season=_s, episode=_e,
                                server_id=str(rec.get("skey") or ""))
                            if _sn and _sn not in _names:
                                _names.append(_sn)
            if _marked:
                res["reverse_marked"] = _marked
                res["reverse_names"] = _names
                self._push_log("WARNING",
                               f"探测库反向检查：Emby 已无 {_marked} 个集"
                               f"（{('、'.join(_names[:5])) if _names else '-'}），已标记观察期（{_gh:.0f} 小时）")
            return _marked
        except Exception as e:
            logger.debug(f"[Probe] 反向检查失败: {e}")
            return 0

    def _probe_process(self, batch: list, res: dict) -> None:
        """补翻一批目标（单文件入库流水线）+ 事件登记 + 聚合通知。"""
        _rev = int(res.get("reverse_marked") or 0)
        if not batch:
            if _rev:
                self._push_log("WARNING",
                               f"探测库：未发现需补翻的缺口；但发现 {_rev} 个集 Emby 已无（已标记观察期，"
                               f"见仪表盘「失效/待恢复」）")
            else:
                self._push_log("INFO", "探测库：深查完成，未发现缺集/新条目")
            return
        preview = bool(getattr(self, "_nfo_preview", False))
        _now = time.time()
        groups: Dict[str, dict] = {}
        for t in batch:
            if self._probe_stop:
                break
            try:
                r = self._ingest_nfo_pending(t["path"], trigger=self._scan_ingest_trigger())
            except Exception as e:
                r = {"ok": False, "error": str(e)}
            _err = str((r or {}).get("error") or "")
            g = groups.setdefault(str(t.get("group") or t["path"]),
                                  {"name": t.get("series") or t.get("title") or "",
                                   "done": 0, "failed": 0, "eps": [],
                                   "skey": t.get("skey") or "", "emby_id": t.get("emby_id") or ""})
            if _err:
                res["failed"] = int(res.get("failed") or 0) + 1
                g["failed"] += 1
                if len(res["fails"]) < 8:
                    res["fails"].append(f"{os.path.basename(str(t.get('path') or ''))}：{_err}")
                continue
            # 成功 → 登记「已探测尝试」（防止每轮重复触发；预览模式也登记，
            # 文件落盘留给「全部写回」或后续扫描，避免每小时空转）
            self._probe_seen[t["path"]] = _now
            res["done"] = int(res.get("done") or 0) + 1
            g["done"] += 1
            if t.get("s") is not None:
                g["eps"].append(f"E{t.get('e')}")
        if not preview and res.get("done"):
            try:
                if getattr(self, "_emby_name_sync", True):
                    self._pool_sync_all(ctx="探测库")
            except Exception:
                pass
        # 登记裁剪（上限 20000、保留 30 天）
        try:
            _seen = self._probe_seen or {}
            if len(_seen) > 20000:
                self._probe_seen = dict(sorted(_seen.items(), key=lambda kv: kv[1])[-20000:])
            _cut = _now - 30 * 24 * 3600
            self._probe_seen = {k: v for k, v in (self._probe_seen or {}).items()
                                if float(v or 0) >= _cut}
        except Exception:
            pass
        _groups = [(k, v) for k, v in groups.items() if v.get("done")]
        # 仪表盘事件列表登记（带「探测」标记，与 Webhook 入库区分；每次最多 20 行）
        for _k, g in _groups[:20]:
            _nm = g.get("name") or "条目"
            if str(_k).startswith("new:"):
                _msg = f"🔎 探测库：全新条目已入库 {g['done']} 个文件（待后台翻译）"
            else:
                _eps = "、".join(g["eps"][:12]) or f"{g['done']} 个文件"
                _msg = f"🔎 探测库：缺集已入库 {g['done']} 个（{_eps}）（待后台翻译）"
            self._push_webhook_event(str(g.get("emby_id") or ""), _nm, "done", _msg, series_name=_nm)
        _sum = (f"🔎 探测库：发现 {res.get('found', 0)} 个待补（{len(_groups)} 处），"
                f"已入库 {res.get('done', 0)} 个，失败 {res.get('failed', 0)} 个"
                f"{('，其余 ' + str(res.get('rest')) + ' 个下轮继续') if res.get('rest') else ''}")
        self._push_log("WARNING" if res.get("failed") else "INFO", _sum)
        # MP 通知（有补翻 或 有反向标记 就发；遵循「完成时发送通知」总开关）
        if (_groups or _rev) and getattr(self, "_notify_on_complete", False):
            try:
                if _groups:
                    _lines = [f"🔎 探测库：补翻 {res.get('done', 0)} 个文件（{len(_groups)} 处缺口）"
                              f"{'（预览模式：只写库未写文件）' if preview else ''}"]
                else:
                    _lines = ["🔎 探测库：未发现需要补翻的缺口"]
                for _k, g in _groups[:10]:
                    _nm = g.get("name") or "条目"
                    if str(_k).startswith("new:"):
                        _lines.append(f"• 《{_nm}》：全新条目 · {g['done']} 个文件")
                    else:
                        _lines.append(f"• 《{_nm}》：缺 {g['done']} 集（{'、'.join(g['eps'][:12]) or '-'}）")
                if len(_groups) > 10:
                    _lines.append(f"… 其余 {len(_groups) - 10} 处见仪表盘事件列表")
                if res.get("rest"):
                    _lines.append(f"⏭️ 其余 {res.get('rest')} 个文件下一轮继续（每轮上限 {self.PROBE_MAX_FILES_PER_ROUND}）")
                if res.get("failed"):
                    _lines.append(f"❌ 失败 {res.get('failed')} 个（见日志）")
                if _rev:
                    _lines.append(f"🗑️ 反向检查：发现 {_rev} 个集 Emby 已无"
                                  f"（{('、'.join((res.get('reverse_names') or [])[:5])) if res.get('reverse_names') else '-'}），"
                                  f"已标记观察期，见仪表盘「失效/待恢复」")
                self.post_message(mtype=NotificationType.Manual, title="🔎 探测库",
                                  text="\n".join(_lines))
            except Exception as _e:
                logger.debug(f"[Probe] 探测通知发送失败（非致命）: {_e}")

    def _maintenance_pass(self):
        """单轮维护：标记消失 → 超期清理（真删除）+ 通知。
        P4: 改用轻量 GROUP BY 查询（不再全表行加载）；
        X3: 增加行级检查 —— 整季删除（剧根仍在）也能进观察期；
        建议5: 每日一次 WAL checkpoint + VACUUM。
        维护轮转游标 —— 按 id waterline 分页循环覆盖整个数据库
        （此前每轮永远只检查最新 800 条 / 最新 1500 个 nfo_path，更早的条目
        和文件永不检查）。每轮推进游标，翻到末尾后回到起点重新覆盖。"""
        try:
            db = getattr(self, "_people_db", None)
            if db is None:
                return
            _pid = self.__class__.__name__
            _gh = float(getattr(self, "_nfo_dead_grace_hours", 24) or 24)
            _mcur = getattr(self, "_maint_cursor", None)
            if not isinstance(_mcur, dict):
                _mcur = {"item_id": 0, "ep_id": 0}
                self._maint_cursor = _mcur
            _page = 800
            _after = int(_mcur.get("item_id") or 0)
            items = db.library_items_lite(plugin_id=_pid, limit=_page, after_id=_after)
            # 推进条目轮转游标：满页 → 继续向后；不满页/空 → 本轮到底，下轮回到起点
            if items and len(items) >= _page:
                _mcur["item_id"] = max(int(it.get("id") or 0) for it in items)
            else:
                _mcur["item_id"] = 0
            missing = [it for it in items
                       if it.get("nfo_dir") and not os.path.isdir(str(it["nfo_dir"]))
                       and not str(it.get("deleted_at") or "")]
            if missing:
                # v4.6.66（P0-1 联动）：按条目各自来源标记（Webhook 行带真实 server_id，
                # 旧代码只看 '' 来源 → P0-1 后这些行漏标、观察期机制失效）。
                for it in missing:
                    try:
                        db.mark_deleted(plugin_id=_pid, item_ids=[str(it["item_id"])],
                                        server_id=str(it.get("server_id") or ""))
                    except Exception:
                        pass
                _dead_text = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() + _gh * 3600))
                for it in missing:
                    self._push_webhook_event(str(it["item_id"]), str(it.get("title") or ""),
                                             "missing",
                                             f"检测到 nfo 目录消失，已进入观察期（{int(_gh)} 小时）；{_dead_text} 到期自动检查，"
                                             f"观察期内重新入库时将自动尝试按媒体稳定身份恢复（Emby ID / TMDB / TVDB / IMDb）",
                                             series_name=str(it.get("series_name") or ""),
                                             server_id=str(it.get("server_id") or ""))
                logger.info(f"[NFO] 维护：{len(missing)} 个条目 nfo 目录消失，进入观察期（{int(_gh)} 小时）")
            try:
                _ep_page = 1500
                _ep_after = int(_mcur.get("ep_id") or 0)
                _ep_rows = db.episode_nfo_paths(plugin_id=_pid, limit=_ep_page, after_id=_ep_after)
                # 推进 nfo_path 轮转游标：满页 → 继续向后；不满页/空 → 下轮回到起点
                if _ep_rows and len(_ep_rows) >= _ep_page:
                    _mcur["ep_id"] = max(int(r.get("id") or 0) for r in _ep_rows)
                else:
                    _mcur["ep_id"] = 0
                _dirs = {}
                for _row in _ep_rows:
                    _p0 = str(_row.get("nfo_path") or "")
                    _d0 = _p0.replace("\\", "/").rsplit("/", 1)[0] if "/" in _p0 else ""
                    if _d0 and _d0 not in _dirs:
                        _dirs[_d0] = 0
                _ep_marked = 0
                for _d0 in list(_dirs.keys())[:400]:
                    self._maintenance_stop.wait(0.15)  # 网盘场景节流
                    if os.path.isdir(_d0):
                        continue
                    # v4.6.67：本地维护按「目录在本地文件系统消失」判定 ——
                    # 显式 server_id=None（不限定来源）：同一路径对所有来源都已不存在。
                    # v4.6.98（P1-02 E）：跨来源写入必须显式声明 allow_unscoped=True 才放行。
                    _ep_marked += int(db.mark_deleted_by_nfo_path_prefix(
                        plugin_id=_pid, path_prefix=_d0, server_id=None,
                        allow_unscoped=True) or 0)
                if _ep_marked:
                    logger.info(f"[NFO] 维护：{_ep_marked} 条记录所在目录消失（整季删除），已进入观察期")
                    self._push_log("INFO", f"维护：{_ep_marked} 条记录（整季/目录被删）已进入观察期，"
                                           f"{int(_gh)} 小时后自动清理")
            except Exception as _e:
                logger.debug(f"[NFO] 行级失效检查失败（非致命）: {_e}")
            exp = db.expired_item_ids(plugin_id=_pid, grace_hours=_gh)
            if exp:
                db.purge_expired(plugin_id=_pid, grace_hours=_gh)
                # v4.6.77（规范 §二十三闭环）：观察期到点未恢复 → 记录已真删除，
                # 同步清掉对应的「失效/待恢复」事件（数据库已无对应记录），不留假象。
                try:
                    _cl = self._cleanup_dirty_webhook_events() or {}
                    _n_ev = int(_cl.get("removed_count") or 0)
                    if _n_ev:
                        logger.info(f"[NFO] 维护：同步清理 {_n_ev} 条已过观察期条目的失效事件")
                except Exception:
                    pass
                logger.info(f"[NFO] 维护：清理 {len(exp)} 个超过宽限期条目（判定为真删除）")
                self._push_log("INFO", f"已自动清理 {len(exp)} 个超过宽限期未恢复的条目（判定为真删除）")
                if getattr(self, "_notify_on_complete", False):
                    self.post_message(mtype=NotificationType.Manual, title=self.plugin_name,
                                      text=f"已自动清理 {len(exp)} 个超过宽限期（{int(_gh)} 小时）未恢复的条目（判定为真删除）。若属误判，该剧重新入库即可恢复翻译名单。")
            try:
                _day = time.strftime("%Y-%m-%d")
                if str(getattr(self, "_last_vacuum_day", "")) != _day:
                    self._last_vacuum_day = _day
                    _vac = getattr(db, "vacuum", None)
                    if callable(_vac):
                        _vac()
                    self._save_state()
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"[NFO] 维护检查失败: {e}")


    def _webhook_translate_worker(self, item_id: str, server_id: str, delay: int,
                                  added_count: int = 0):
        """
        Webhook 翻译执行器（v1.3.9: 延迟由 _webhook_worker 调度，此处不再 sleep）
        """
        max_retries = 2  # 重试次数
        current_retry = 0

        while current_retry <= max_retries:
            if not getattr(self, "_enabled", False):
                logger.info(f"[Webhook] 插件已关闭，取消处理 ItemId={item_id}")
                return
            try:
                if current_retry > 0:
                    logger.warning(f"[Webhook] 第 {current_retry} 次重试翻译 ItemId={item_id}")
                    time.sleep(2)  # 重试前等待
                else:
                    time.sleep(1)  # 给 Emby 一点缓冲时间
                
                if self._stop_requested:
                    logger.info(f"[Webhook] 已请求停止，取消翻译 ItemId={item_id}")
                    return
                
                # 获取服务列表
                services = self._get_all_emby_services()
                if not services:
                    logger.error("[Webhook] 无可用 Emby 服务器")
                    self._webhook_failed += 1
                    return
                
                # 查找目标服务器
                svc = self._find_target_server(services, server_id)
                if svc is None:
                    self._webhook_failed += 1
                    self._push_webhook_event(item_id, f"Item_{item_id}", "failed",
                                             f"未匹配到 server_id={server_id} 的 Emby 服务器，已跳过")
                    return
                url = self._get_service_url(svc)
                api_key = self._get_service_api_key(svc)
                user_id = self._get_service_user_id(svc)
                client = EmbyClient(url, api_key, svc, user_id=user_id, use_proxy=self._use_proxy)
                
                # 获取条目详情
                logger.info(f"[Webhook] 正在获取条目详情: ItemId={item_id}")
                item = client.fetch_item(item_id)
                if not item:
                    if self._schedule_webhook_retry(item_id, server_id, 60, f"Item_{item_id}", "item"):
                        return
                    logger.error(f"[Webhook] 无法获取条目详情: {item_id}（2h 窗口内未就绪），跳过")
                    self._webhook_failed += 1
                    self._webhook_error = "获取条目详情失败"
                    return
                
                display_title = item.get("Name") or f"Item_{item_id}"

                item = self._normalize_webhook_item(item, server_id)

                if not self._in_selected_library(str(item.get("Path") or "")):
                    _p_skip = str(item.get("Path") or "")
                    logger.debug(f"[Webhook] 已过滤（未选择该媒体库）: {display_title} Path={_p_skip}")
                    try:
                        _warned = getattr(self, "_lib_skip_warned", None)
                        if _warned is None:
                            _warned = self._lib_skip_warned = set()
                        _libnm = self._library_name_for_path(_p_skip) or "（未识别库）"
                        if _libnm not in _warned:
                            _warned.add(_libnm)
                            self._push_log("WARNING",
                                           f"⚠️ 入库条目「{display_title}」属于未勾选的媒体库 {_libnm}，已跳过翻译；"
                                           f"如需处理请在设置页勾选该媒体库（示例路径：{_p_skip}）")
                    except Exception:
                        pass
                    self._webhook_skipped += 1
                    self._push_webhook_event(item_id, display_title, "skipped",
                                             "未选择该媒体库，已忽略",
                                             series_name=str(item.get("SeriesName") or ""),
                                             season=item.get("ParentIndexNumber"), episode=item.get("IndexNumber"))
                    return

                _itype2 = str(item.get("Type") or "").lower()
                if _itype2 in ("series", "tvshow", "season") or _itype2.startswith("season"):
                    self._submit_series_expand(client, item, item_id, server_id, display_title,
                                               added_count=added_count)
                    return

                if getattr(self, "_scan_mode", "nfo") == "nfo":
                    _ip = str(item.get("Path") or "").replace("\\", "/").strip("/")
                    _item_dir = _ip.rsplit("/", 1)[0] if "/" in _ip else _ip
                    if not self._dir_in_nfo_roots(_item_dir):
                        self._hold_pending_config(item_id, server_id, item, display_title)
                        return
                    nfo_path = self._locate_nfo_from_item(item)
                    if not nfo_path:
                        if self._schedule_webhook_retry(item_id, server_id, 60, display_title, "nfo", item):
                            return
                        _expect = os.path.splitext(str(item.get("Path") or "").replace("\\", "/"))[0] + ".nfo"
                        _itype_txt = str(item.get("Type") or "Episode")
                        logger.warning(f"[Webhook] 未找到本地 nfo（重试 2 次后放弃）: {_expect}")
                        self._webhook_skipped += 1
                        self._push_webhook_event(item_id, display_title, "failed",
                                                 f"未找到 nfo（重试 2 次后放弃），预期路径：{_expect}",
                                                 series_name=str(item.get("SeriesName") or ""),
                                                 season=item.get("ParentIndexNumber"), episode=item.get("IndexNumber"))
                        if getattr(self, "_notify_on_complete", False):
                            try:
                                self.post_message(mtype=NotificationType.Manual, title=self.plugin_name,
                                                  text=f"❌ 翻译失败：{display_title}\n• 类型：{_itype_txt}\n"
                                                       f"• 未找到 nfo（已重试 2 次）：{_expect}\n"
                                                       f"• 请确认 Emby 已刮削完成、该文件确实存在")
                            except Exception:
                                pass
                        return
                    res = self._ingest_nfo_pending(nfo_path, item_id=item_id,
                                                   server_id=server_id, item=item,
                                                   trigger=self._nfo_ingest_trigger())
                    self._save_state()
                    _recovered = int(res.get("recovered") or 0)
                    # v4.6.66（P1-1/P1-2）：待翻按「当前翻译范围」统计（采集数不再冒充待翻）
                    _brief1 = self._ingest_scope_brief(
                        [(res.get("server_id") or server_id, res.get("media_item_id") or "")])
                    _pl = int(_brief1.get("pending") or 0)
                    _coll1 = int(res.get("names") or 0) + int(res.get("roles") or 0)
                    _exist1 = int(_brief1.get("translated") or 0)
                    if not res.get("ok"):
                        _err = str(res.get("error") or "入库失败")
                        logger.warning(f"[Webhook] NFO 入库未完成: {_err}")
                        self._webhook_failed += 1
                        self._webhook_error = _err
                        self._push_webhook_event(item_id, display_title, "failed",
                                                 f"入库失败: {_err[:60]}",
                                                 series_name=str(item.get("SeriesName") or ""),
                                                 season=item.get("ParentIndexNumber"),
                                                 episode=item.get("IndexNumber"))
                        with self._webhook_lock:
                            _rk = self._wh_retry_key(server_id, item_id)
                            self._webhook_retry_map.pop(_rk, None)
                            self._webhook_retry_first.pop(_rk, None)
                        return
                    else:
                        logger.info(f"[Webhook] NFO 已入库{'(恢复)' if _recovered else ''}: {display_title} - "
                                    f"记录 {res.get('records', 0)} 条, {self._ingest_tx_phrase(self._nfo_ingest_trigger(), _pl)}")
                        self._webhook_error = ""
                        if _recovered:
                            # 清掉事件列表里对应的旧「失效/待恢复」行（该条目已重新入库恢复）
                            self._remove_missing_event(series_name=str(item.get("SeriesName") or ""),
                                                       season=item.get("ParentIndexNumber"),
                                                       episode=item.get("IndexNumber"),
                                                       title=display_title,
                                                       server_id=str(server_id or ""),
                                                       item_id=str(item_id or ""),
                                                       media_item_id=str(res.get("media_item_id") or ""))
                            self._update_or_push_webhook_event(item_id, display_title, "done",
                                                               f"已恢复：被删除条目重新入库，{self._ingest_tx_phrase(self._nfo_ingest_trigger(), _pl)}"
                                                               if _pl else "已恢复：被删除条目重新入库",
                                                               series_name=str(item.get("SeriesName") or ""),
                                                               season=item.get("ParentIndexNumber"),
                                                               episode=item.get("IndexNumber"))
                        else:
                            self._update_or_push_webhook_event(item_id, display_title, "done",
                                                               f"已入库，{self._ingest_tx_phrase(self._nfo_ingest_trigger(), _pl)}" if _pl else "已入库（无需翻译）",
                                                               series_name=str(item.get("SeriesName") or ""),
                                                               season=item.get("ParentIndexNumber"),
                                                               episode=item.get("IndexNumber"))
                    with self._webhook_lock:
                        _rk = self._wh_retry_key(server_id, item_id)
                        self._webhook_retry_map.pop(_rk, None)
                        self._webhook_retry_first.pop(_rk, None)
                    self._webhook_processed += 1
                    self._notify_webhook_completed(item_id, display_title, 0, 0, item,
                                                   recovered=_recovered,
                                                   llm_calls=0, zhconv=0, pool=0,
                                                   pending_left=_pl,
                                                   existing=_exist1, collected=_coll1,
                                                   ingested=1)
                    return
                
            except Exception as e:
                logger.error(f"[Webhook] 翻译异常 (尝试 {current_retry + 1}/{max_retries + 1}): {e}")
                self._webhook_error = str(e)
                current_retry += 1
                if current_retry > max_retries:
                    self._webhook_failed += 1
                    logger.error(f"[Webhook] 翻译彻底失败: ItemId={item_id}")
                    try:
                        self._push_webhook_event(item_id, f"Item_{item_id}", "failed",
                                                 f"翻译异常: {str(e)[:80]}")
                    except Exception:
                        pass
                    with self._webhook_lock:
                        _rk = self._wh_retry_key(server_id, item_id)
                        self._webhook_retry_map.pop(_rk, None)
                        self._webhook_retry_first.pop(_rk, None)

    def _batch_translate_nfo_files(self, nfo_items: list, title_ctx: str = "",
                                   year_ctx: str = "", item_meta: dict = None) -> dict:
        """批量翻译一组 nfo 文件。
        不再直接调 LLM（统一通道）—— 译文来源：人名池命中 → 库中已有译文 → 繁转简；
        剩余词条留在 DB，由常驻翻译 worker 翻译、写回 worker 落盘。
        :param nfo_items: [(nfo_path, level)]，level ∈ tvshow/episode/movie
        :return: {done, fail, changed, records, llm_calls, zhconv, pool_new,
                  names_count, roles_count, recovered, pending_left}
        """
        from . import nfo as nfo_engine
        _pid = self.__class__.__name__
        dbm = getattr(self, "_name_map_db", None) or NameMapDb()
        _pool = dbm.load_map(plugin_id=_pid)
        _fresh = []
        overwrite = bool(getattr(self, "_overwrite_chinese", False))
        only_roles = bool(getattr(self, "_translate_role", True) or getattr(self, "_translate_all", False))
        preview = bool(getattr(self, "_nfo_preview", False))
        llm_calls = 0
        zhconv_count = 0
        pool_hit = 0

        # 阶段 1：解析所有 nfo + 收集词条
        name_orig: set = set()
        role_orig: set = set()
        _doc_cache = {}
        for nf, lv in nfo_items:
            if getattr(self, "_stop_requested", False):
                break
            doc = nfo_engine.parse_nfo(nf)
            if doc is None:
                continue
            _doc_cache[nf] = doc
            _ctt = self._collect_trans_types(lv)
            ns, rs = doc.collect(
                translate_types=self._trans_types_for_collect(lv) or None,
                guest_limit=0,
                limits=_ctt.get("limits", {}) or None,
            )
            name_orig.update(n[0] for n in ns)
            role_orig.update(r[0] for r in rs)

        # 阶段 1.5（v4.0 适配·不可倒退）: 删除→恢复识别 —— 必须在入库 upsert 之前
        # （逐文件按 nfo_path 精确查观察期；集文件再按 剧名+季集 兜底），命中即解除
        recovered = 0
        try:
            _db = getattr(self, "_people_db", None)
            if _db is not None:
                _sid_arg = str(server_id or "") or None
                for nf, lv in nfo_items:
                    try:
                        _sname = ""
                        _ssn = _epn = None
                        if lv == "episode":
                            try:
                                _sid2, _sname, _ssn, _epn = self._nfo_episode_meta(nf)
                            except Exception:
                                pass
                        _i_iid, _i_mp, _i_mid, _i_smi, _i_title = self._media_identity_from_path(nf, lv)
                        # v4.6.72（批次3）：强身份（provider / item_id / series_media_id / Emby）
                        # 优先；洗版后路径/标题变化但 provider 未变仍能识别为恢复。
                        _was = False
                        try:
                            if int(_db.is_deleted_by_media(
                                    plugin_id=_pid, item_id=_i_iid, media_provider=_i_mp,
                                    media_id=_i_mid, series_media_id=_i_smi,
                                    season_num=_ssn, episode_num=_epn,
                                    server_id=_sid_arg) or 0) > 0:
                                _was = True
                        except Exception:
                            _was = False
                        if not _was:
                            _was = bool(_db.is_deleted_by_nfo_path(plugin_id=_pid, nfo_path=nf,
                                                                   server_id=_sid_arg))
                        if not _was and lv == "episode" and _sname:
                            # 弱匹配（剧名+季集）—— 仅候选唯一才允许自动恢复
                            _wc = int(_db.deleted_weak_candidates(
                                plugin_id=_pid, series_name=_sname, title=_i_title,
                                season_num=_ssn, episode_num=_epn, server_id=_sid_arg) or 0)
                            _was = (_wc == 1)
                        if _was:
                            _db.clear_deleted_by_media(
                                plugin_id=_pid, item_id=_i_iid, media_provider=_i_mp,
                                media_id=_i_mid, series_media_id=_i_smi,
                                season_num=_ssn, episode_num=_epn, server_id=_sid_arg)
                            _db.clear_deleted(plugin_id=_pid, nfo_path=nf, series_name=_sname,
                                              season_num=_ssn, episode_num=_epn, server_id=_sid_arg)
                            recovered += 1
                    except Exception:
                        pass
        except Exception:
            pass

        # 阶段 2：合并去重（池命中 → 库中已有译文 → 繁转简；不调 LLM —— 剩余交常驻翻译 worker）
        _db_trans = self._tx_existing_translations(name_orig, role_orig)
        _db_names = (_db_trans or {}).get("names") or {}
        _db_roles = (_db_trans or {}).get("roles") or {}

        def _translate_merged(terms, is_role):
            """不调 LLM —— 人名池命中 → 库中已有译文 → 繁转简。"""
            nonlocal zhconv_count, pool_hit
            out = {}
            _t = "role" if is_role else "person"
            _dbm = _db_roles if is_role else _db_names
            for t in sorted(terms):
                t = (t or "").strip()
                if not t:
                    continue
                hit = _pool.get((_t, t))
                if hit and hit[0]:
                    out[t] = hit[0]; self._pool_hits += 1; pool_hit += 1
                    continue
                _dbt = _dbm.get(t)
                if _dbt and _dbt != t:
                    out[t] = _dbt
                    continue
                if not overwrite and (self._looks_like_japanese(t) and self._ja_name_policy == 'keep'):
                    continue
                if not overwrite and self._ja_name_policy != 'translate' \
                        and not self._looks_like_japanese(t) and self._looks_like_chinese(t):
                    z = self._zhconv_convert(t)
                    if z and z != t:
                        out[t] = z
                        zhconv_count += 1
                        _fresh.append({"type": _t, "original": t, "zh": z, "source": "zhconv"})
                        self._pool_hits += 1
                        _pool[(_t, t)] = (z, "zhconv")
                    continue
            return out

        name_map = _translate_merged(name_orig, False) if name_orig else {}
        role_map = {k: self._normalize_role_zh(k, v)
                    for k, v in (_translate_merged(role_orig, True) if (role_orig and only_roles) else {}).items()}
        person_map = nfo_engine.build_map_from_source(list(name_map.items()))
        role_map_final = nfo_engine.build_map_from_source(list(role_map.items()))

        # 阶段 3：逐文件 apply + save + 入库
        done = fail = changed_total = records = 0
        for nf, lv in nfo_items:
            if getattr(self, "_stop_requested", False):
                break
            doc = _doc_cache.get(nf)
            if doc is None:
                fail += 1
                continue
            try:
                _sid2 = _sname = ""
                _ssn = _epn = None
                if lv == "episode":
                    try:
                        _sid2, _sname, _ssn, _epn = self._nfo_episode_meta(nf)
                    except Exception:
                        pass
                if preview:
                    try:
                        records += self._record_nfo_library(doc, person_map, role_map_final,
                                                            series_id=_sid2, series_name=_sname,
                                                            season_num=_ssn, episode_num=_epn,
                                                            pool_ingest=True)
                    except Exception as _e:
                        logger.warning(f"[Webhook] 批量入库记录失败 {nf}: {_e}")
                    changed_total += doc.apply(person_map, role_map_final)
                    done += 1
                else:
                    c = doc.apply(person_map, role_map_final)
                    changed_total += c
                    saved = doc.save(backup=getattr(self, "_nfo_backup", False),
                                     dry_run=False,
                                     lock_cast=bool(getattr(self, "_lock_cast", False)))
                    if saved:
                        try:
                            records += self._record_nfo_library(doc, person_map, role_map_final,
                                                                series_id=_sid2, series_name=_sname,
                                                                season_num=_ssn, episode_num=_epn,
                                                                pool_ingest=True)
                        except Exception as _e:
                            logger.warning(f"[Webhook] 批量入库记录失败 {nf}: {_e}")
                        done += 1
                    else:
                        fail += 1
                        logger.warning(f"[Webhook] 批量入库写回失败: {nf}")
            except Exception as _e:
                fail += 1
                logger.warning(f"[Webhook] 批量入库异常 {nf}: {_e}")

        if _fresh:
            try:
                dbm.set_map_many(plugin_id=_pid, entries=_fresh)
            except Exception as _e:
                logger.warning(f"[Webhook] 批量入库回写人名池失败: {_e}")

        _pending_left = (sum(1 for _t0 in name_orig if str(_t0).strip() not in person_map)
                         + sum(1 for _t0 in role_orig if str(_t0).strip() not in role_map_final))
        if _pending_left:
            self._tx_wake()
        return {
            "done": done, "fail": fail, "changed": changed_total, "records": records,
            "llm_calls": llm_calls, "zhconv": zhconv_count, "pool_new": len(_fresh),
            "pool_hit": pool_hit,
            "names_count": len(name_orig), "roles_count": len(role_orig),
            "recovered": recovered, "pending_left": _pending_left,
        }

    def _translate_series_expanded(self, client, item: dict, item_id: str,
                                   server_id: str, display_title: str,
                                   added_count: int = 0):
        """Series/Season 级入库展开 —— 拉出全部单集 + tvshow.nfo，
        合并词条一次性翻译（与零散多集入库共用 _batch_translate_nfo_files）。
        nfo 未就绪的集重试 2 次后仍缺 → ❌ 失败通知（带完整路径+类型），不退化为静默跳过。"""
        try:
            _sid = str(item.get("Id") or item_id)
            eps = client.get_series_episodes(_sid, limit=200)
            if not eps:
                logger.warning(f"[Webhook] Series 展开：未拉到任何单集（ItemId={item_id}），跳过")
                self._update_or_push_webhook_event(item_id, display_title, "skipped",
                                                   "整剧入库：未拉到单集（Emby 尚未就绪），跳过")
                return
            # v4.6.87：标明本次覆盖了哪几季（多季入库时尤其直观）
            _s_txt = self._seasons_range_txt(
                [e.get("ParentIndexNumber") for e in eps if isinstance(e, dict)])
            _s_show = f"【{_s_txt}】" if _s_txt else ""
            logger.info(f"[Webhook] Series 展开为 {len(eps)} 个单集任务（合并翻译）{_s_show}: {display_title}")
            self._update_or_push_webhook_event(item_id, display_title, "running",
                                               f"整剧入库：展开为 {len(eps)} 个单集任务{_s_show}，收集全部集词条合并翻译")
            # 预过滤：Path 有效 + 属已选库 + 目录过根目录门禁（与单集链同口径）
            pending = []
            for ep in eps:
                if not isinstance(ep, dict):
                    continue
                try:
                    _ep = self._normalize_webhook_item(ep, server_id)
                except Exception:
                    _ep = ep
                _p = str(_ep.get("Path") or "").replace("\\", "/")
                if not _p or not self._in_selected_library(_p):
                    continue
                _dir = _p.rsplit("/", 1)[0] if "/" in _p else _p
                if not self._dir_in_nfo_roots(_dir.strip("/")):
                    continue
                pending.append(_ep)
            if not pending:
                logger.info("[Webhook] 整剧入库：过滤后无可处理单集")
                return

            # v4.6.92：整剧入库收词决策 —— 三条规则（用户拍板；完整口径见 _decide_series_ingest）：
            #   ① 开了「整剧全收」→ 全收；
            #   ② 通知数量 N ≥ 集总数 → 整剧都是新加的 → 全收；
            #   ③ 否则按 Emby 加入时间只收新增；④ 一个都挑不出来 → 兜底全收（宁可多收，绝不漏收）。
            # 补齐旧集的入口（不走本判定、不受影响）：「扫描」/「探测库」/ 对该剧「重新拉取」。
            # 即使全被跳过也不早退 —— tvshow 仍会入库（保证该剧在库页可见）。
            _skipped_old = 0
            if pending:
                _decide_note = ""
                try:
                    pending, _skipped_old, _decide_note = self._decide_series_ingest(pending, added_count)
                except Exception as _de:
                    logger.debug(f"[Webhook] 整剧入库决策失败（按整剧继续）: {_de}")
                if _decide_note:
                    logger.info(f"[Webhook] {_decide_note}{_s_show}: {display_title}")

            still = pending
            _nfo_map = {}
            for i, wait in enumerate((0, 60, 120)):  # 首查 + 2 次重试（超过 2 次直接报错）
                if i and still:
                    time.sleep(wait)
                nxt = []
                for ep in still:
                    if not getattr(self, "_enabled", False) or self._stop_requested:
                        return
                    nf = self._locate_nfo_from_item(ep)
                    if nf:
                        _nfo_map[str(ep.get("Id") or id(ep))] = nf
                    else:
                        nxt.append(ep)
                still = nxt
                if not still:
                    break

            if still:
                _missing = [os.path.splitext(str(_e.get("Path") or "").replace("\\", "/"))[0] + ".nfo"
                            for _e in still[:5]]
                logger.warning(f"[Webhook] 整剧入库展开：{len(still)} 个单集 nfo 未就绪（重试 2 次后放弃）")
                if getattr(self, "_notify_on_complete", False):
                    try:
                        self.post_message(mtype=NotificationType.Manual, title=self.plugin_name,
                                          text=f"❌ 整剧入库处理未完成：{display_title}\n"
                                               f"• 类型：Series/Season（ItemId={item_id}）\n"
                                               f"• 未找到 nfo 的集：{len(still)} 个（已重试 2 次）\n"
                                               f"• 示例路径：\n  " + "\n  ".join(_missing))
                    except Exception:
                        pass

            nfo_items = []
            _tv_nfo = self._locate_nfo_from_item(item)
            if _tv_nfo:
                nfo_items.append((_tv_nfo, "tvshow"))
            for ep in pending:
                nf = _nfo_map.get(str(ep.get("Id") or id(ep)))
                if nf:
                    nfo_items.append((nf, "episode"))
            if not nfo_items:
                logger.warning("[Webhook] 整剧入库：所有 nfo 均未就绪（重试 2 次后放弃）")
                self._update_or_push_webhook_event(item_id, display_title, "failed",
                                                   "整剧入库：所有集未找到 nfo（重试 2 次后放弃）")
                self._webhook_failed += 1
                return

            _entries = []
            for _nf3, _lvn3 in nfo_items:
                _it3, _iid3 = item, item_id
                if _lvn3 == "episode":
                    for _ep3 in pending:
                        if _nfo_map.get(str(_ep3.get("Id") or id(_ep3))) == _nf3:
                            _it3 = _ep3
                            _iid3 = str(_ep3.get("Id") or item_id)
                            break
                _entries.append((_nf3, _lvn3, _iid3, server_id, _it3))
            res = self._ingest_nfo_batch(_entries, trigger=self._nfo_ingest_trigger())
            _fail_total = res["fail"] + len(still)
            _fail_n = len(getattr(self, "_failed_terms", None) or ())
            _pl = int(res.get("pending_left") or 0)
            # v4.6.66（P1-1/P1-2）：日志拆分「采集 / 当前范围待翻 / 已有译文」，不再把采集数当待翻
            logger.info(f"[Webhook] 整剧入库完成（"
                        f"{'已交后台翻译' if str(self._nfo_ingest_trigger()) == 'auto_trigger' else '仅入库，未自动翻译'}）"
                        f"：{len(nfo_items)} 个 nfo{_s_show}"
                        f"（{res['done']} 入库成功/{res['fail']} 失败），"
                        f"采集 人名 {res['names_count']}/角色 {res['roles_count']}，"
                        f"当前范围待翻 {_pl} 个（第一排 {res.get('pending_person', 0)} / "
                        f"第二排 {res.get('pending_role', 0)}），已有译文 {res.get('translated_existing', 0)} 条"
                        + (f"，跳过旧集 {_skipped_old} 个（只收新增）" if _skipped_old else "")
                        + (f"，失败清单 {_fail_n} 个" if _fail_n else ""))
            self._update_or_push_webhook_event(
                item_id, display_title,
                "failed" if still else "done",
                f"整剧入库：{len(nfo_items)} 个 nfo{_s_show}"
                f"（成功 {res['done']}，失败 {_fail_total}）"
                f"｜采集 人名 {res['names_count']}/角色 {res['roles_count']}"
                f"｜当前范围待翻 {_pl} 个"
                + (f"｜跳过旧集 {_skipped_old} 个（只收新增）" if _skipped_old else "")
                + (f"｜已有译文 {res.get('translated_existing', 0)} 条" if res.get('translated_existing') else ""))
            for _ep in pending:
                try:
                    self._remove_missing_event(series_name=str(_ep.get("SeriesName") or ""),
                                               season=_ep.get("ParentIndexNumber"),
                                               episode=_ep.get("IndexNumber"),
                                               title=str(_ep.get("Name") or ""),
                                               server_id=str(server_id or ""),
                                               item_id=str(_ep.get("Id") or ""))
                except Exception:
                    pass
            if res['done']:
                self._webhook_processed += 1
            else:
                self._webhook_failed += 1
            # v4.6.67（P0-C）：入库阶段 translated 恒 0（res['done'] 是 NFO 文件数），
            # 文件数走 ingested —— 修「3 个 NFO 入库显示成『翻译 3 条』」。
            self._notify_webhook_completed(item_id, f"{display_title}{_s_show}", 0, _fail_total, item,
                                           recovered=int(res.get("recovered", 0) or 0),
                                           llm_calls=res['llm_calls'], zhconv=res['zhconv'],
                                           batch=True, pool=res.get('pool_hit', 0),
                                           pending_left=_pl,
                                           existing=res.get('translated_existing', 0),
                                           collected=int(res.get('names_count', 0)) + int(res.get('roles_count', 0)),
                                           ingested=int(res.get('done') or 0))
        except Exception as e:
            logger.error(f"[Webhook] Series 展开处理失败: {e}\n{traceback.format_exc()}")
            self._webhook_failed += 1
            self._webhook_error = str(e)

    def _load_emby_server_ids(self):
        """缺陷 Q —— 缓存「服务 skey → Emby 真实 ServerId（GUID）」映射。
        Webhook 报文的 ServerId 是 Emby 的 GUID，与 skey（服务名_主机_端口）不同
        命名空间；有该映射后多 Emby 用户的事件能精确路由到对应服务器。
        探测节流 —— 全部失败（Emby 暂不可达）时记时间戳，5 分钟内不重复探测。"""
        try:
            ids = {}
            for svc in self._get_all_emby_services():
                skey = self._get_server_identifier(svc)
                try:
                    client = EmbyClient(self._get_service_url(svc), self._get_service_api_key(svc), svc,
                                        user_id=self._get_service_user_id(svc), use_proxy=self._use_proxy)
                    _sid = client.get_server_id()
                except Exception as e:
                    logger.warning(f"[Webhook] 获取服务 ServerId 失败 {skey}: {e}")
                    continue
                if _sid:
                    ids[skey] = str(_sid)
            self._emby_server_ids = ids
            self._emby_server_ids_ts = time.time()
        except Exception:
            self._emby_server_ids = {}
            self._emby_server_ids_ts = time.time()

    def _find_target_server(self, services: list, server_id: str):
        """查找目标 Emby 服务器。
        调用方明确给了 server_id 但匹配不到 → 返回 None（**禁止**静默退回第一台，
        由上层记 sync_error / 跳过）；只有 server_id 为空（legacy/no-server-id）才允许兼容取第一台（记日志）。"""
        if not server_id:
            # 没有指定服务器（legacy/无 server_id 数据）→ 兼容取第一台，但显式记日志
            self._warn_once("emby:event-no-server-id",
                            "[Emby] 事件未携带 server_id：按第一台 Emby 兼容路由（多服务器环境下请确认）")
            return services[0] if services else None
        
        # 尝试精确匹配
        for svc in services:
            skey = self._get_server_identifier(svc)
            if skey == server_id:
                return svc

        try:
            if not getattr(self, "_emby_server_ids", None):
                _ts = float(getattr(self, "_emby_server_ids_ts", 0) or 0)
                if time.time() - _ts > 300:
                    self._load_emby_server_ids()
            for svc in services:
                skey = self._get_server_identifier(svc)
                if self._emby_server_ids.get(skey) == server_id:
                    return svc
        except Exception:
            pass
        
        # 尝试通过服务器名匹配
        for svc in services:
            name = getattr(svc, 'name', '') or ''
            if name.lower() == server_id.lower():
                return svc
        
        # 尝试通过 URL 匹配
        for svc in services:
            url = self._get_service_url(svc)
            if url and server_id in url:
                return svc
        
        logger.warning(f"[Emby] 未按 ServerId 匹配到服务器（server_id={server_id}）—— 放弃本次路由（不改名到错误服务器）")
        return None

    def _notify_webhook_completed(self, item_id: str, title: str, translated: int, failed: int, item: dict = None,
                                  recovered: int = 0, llm_calls: int = 0, zhconv: int = 0,
                                  batch: bool = False, pool: int = 0, pending_left: int = 0,
                                  existing: int = 0, collected: int = 0, ingested: int = 0):
        """发送 Webhook 入库/翻译完成通知（v1.3.8: 支持聚合；v3.9.0: recovered=被删条目恢复）
        A-2: 带上 llm_calls/zhconv —— 通知里显示 AI 调用与繁转简次数
        batch=合并翻译批次（通知加「（整合）」标记）；
             剧级事件（series_name 有、集号为空）也归剧队列，不再误入电影队列
        pool=本批「跳过已有译文」条数（池命中，未调 AI）
        pending_left=按当前翻译范围统计的「真正待翻」词条数（已交常驻翻译 worker）
        v4.6.66（P1-1/P1-2）：existing=入库时已有译文条数（恢复继承，未重翻）；
             collected=本批 NFO 采集词条总数 —— 通知拆分「采集数量」与「真正待翻数量」，
             不再把 NFO 全量词条冒充待翻（用户翻译筛选外的词条不计入 pending）。
        v4.6.67（P0-C）：ingested=本批**入库 NFO 文件数** —— 与 translated（真正翻译的词条数）
             严格分开。此前 Webhook/Series 路径把 NFO 文件数当 translated 传入，
             通知里显示成「✅ 翻译：3 条」（实际是 3 个 NFO），是明确的统计口径错误；
             现在入库阶段 translated 恒为 0，通知走「📥 入库完成」并显示 NFO 文件数，
             真正的「翻译完成」由常驻 worker 在处理完后单独推送。
        v4.6.84：recovered 由布尔改为**本批恢复的被删条目（NFO 文件）数** —— 此前通知里
             「已恢复被删条目 1 条」数的是「通知批次条目」（一次整剧入库恒为 1），
             与日志的 recovered=13（13 个文件）对不上。"""
        if not self._notify_on_complete:
            return
        try:
            # 提取剧集信息用于聚合
            series_name = ""
            episode_num = None
            season_num = None
            if item and isinstance(item, dict):
                series_name = item.get("SeriesName") or item.get("series_name") or ""
                episode_num = item.get("IndexNumber") or item.get("index_number")
                season_num = item.get("ParentIndexNumber") or item.get("parent_index_number")

            if translated == 0 and failed == 0 and not recovered and not pending_left and not ingested:
                return  # S3: 无需翻译且无入库量，静默
            if series_name:
                # 剧集模式（含整季批量：集号可能为空）：加入剧聚合队列
                self._add_notification_to_queue(
                    series_name=series_name,
                    title=title,
                    season_num=season_num,
                    episode_num=episode_num,
                    translated=translated,
                    failed=failed,
                    recovered=recovered,
                    llm_calls=llm_calls,
                    zhconv=zhconv,
                    batch=batch,
                    pool=pool,
                    pending=pending_left,
                    existing=existing,
                    collected=collected,
                    ingested=ingested,
                )
            else:
                # 电影/非剧集：并入聚合队列（key=__movies__，flush 时按电影名汇总）
                self._add_notification_to_queue(
                    series_name="__movies__",
                    title=title,
                    season_num=season_num,
                    episode_num=None,
                    translated=translated,
                    failed=failed,
                    recovered=recovered,
                    llm_calls=llm_calls,
                    zhconv=zhconv,
                    batch=batch,
                    pool=pool,
                    pending=pending_left,
                    existing=existing,
                    collected=collected,
                    ingested=ingested,
                )
        except Exception as e:
            logger.debug(f"[Webhook] 发送完成通知失败（非致命）: {e}")

    def _add_notification_to_queue(self, series_name: str, title: str, season_num, episode_num, translated: int, failed: int,
                                   recovered: int = 0, llm_calls: int = 0, zhconv: int = 0,
                                   batch: bool = False, pool: int = 0, pending: int = 0,
                                   existing: int = 0, collected: int = 0, ingested: int = 0):
        """将剧集通知加入聚合队列（v3.9.0: recovered 标记恢复条目）
        A-3: 一并入队 llm_calls/zhconv/batch（聚合通知显示 AI 次数与「整合」标记）
        pool=池命中跳过条数（通知显示「跳过已有译文」）
        pending=交后台翻译的剩余词条数
        v4.6.66（P1-1/P1-2）：existing=已有译文条数（恢复继承）；collected=本批采集词条总数
        v4.6.67（P0-C）：ingested=本批入库 NFO 文件数（与 translated 词条数分开）
        v4.6.84：recovered 由布尔改为**本批恢复的被删条目（NFO 文件）数** —— 此前数的是
             「通知批次条目」，一次整剧入库恒为 1，与实际恢复的 13 个文件对不上。"""
        info = {
            "title": title,
            "season_num": season_num,
            "episode_num": episode_num,
            "translated": translated,
            "failed": failed,
            "recovered": int(recovered or 0),
            "llm_calls": int(llm_calls or 0),
            "zhconv": int(zhconv or 0),
            "batch": bool(batch),
            "pool": int(pool or 0),
            "pending": int(pending or 0),
            "existing": int(existing or 0),
            "collected": int(collected or 0),
            "ingested": int(ingested or 0),
        }
        with self._notification_lock:
            if series_name not in self._notification_queue:
                self._notification_queue[series_name] = []
            self._notification_queue[series_name].append(info)
            # 重置定时器：v3.4.49 窗口 5 秒 → 30 秒（批量入库几百集时更长缓冲，尽量汇成一条）
            if self._notification_flush_timer:
                self._notification_flush_timer.cancel()
            self._notification_flush_timer = threading.Timer(30.0, self._flush_notification_queue)
            self._notification_flush_timer.daemon = True
            self._notification_flush_timer.start()
            logger.info(f"[Webhook] 通知已入队: {series_name} 第{episode_num}集（等待聚合）")

    def _flush_notification_queue(self):
        """聚合发送通知队列
        汇总显示 LLM 调用 / 繁转简次数；批量（多条入队）加「（整合）」标记"""
        with self._notification_lock:
            queue = dict(self._notification_queue)
            self._notification_queue.clear()
            self._notification_flush_timer = None

        for series_name, items in queue.items():
            try:
                if series_name == "__movies__":
                    if not items:
                        continue
                    total_translated = sum(i["translated"] for i in items)
                    total_failed = sum(i["failed"] for i in items)
                    _rec = sum(int(i.get("recovered") or 0) for i in items)
                    _llm = sum(i.get("llm_calls", 0) for i in items)
                    _zhc = sum(i.get("zhconv", 0) for i in items)
                    _pool_skip = sum(i.get("pool", 0) for i in items)
                    _pend = sum(i.get("pending", 0) for i in items)
                    _exist = sum(i.get("existing", 0) for i in items)
                    _coll = sum(i.get("collected", 0) for i in items)
                    _ing = sum(i.get("ingested", 0) for i in items)
                    names = []
                    for i in items:
                        _nm = str(i.get("title") or "").strip()
                        if _nm and _nm not in names:
                            names.append(_nm)
                    _head = "、".join(names[:5]) + (f" 等 {len(names)} 部" if len(names) > 5 else "")
                    if total_translated > 0 or total_failed > 0 or _rec > 0 or _pend > 0 or _ing > 0:
                        _batch_tag = "（整合）" if (len(items) > 1 or any(i.get("batch") for i in items)) else ""
                        # v4.6.67（P0-C）：入库批次（ingested>0）一律「入库完成」，失败归入库；
                        # 只有真正翻译过的批次才叫「翻译完成」。不再把 NFO 文件数写成「翻译 N 条」。
                        if _ing > 0:
                            _hd, _icon = "入库完成", "📥"
                        elif total_translated > 0 or total_failed > 0:
                            _hd, _icon = "翻译完成", "🎬"
                        else:
                            _hd, _icon = "恢复完成", "🔄"
                        _lines = [f"{_icon} {_hd}{_batch_tag}：{_head}"]
                        if _ing > 0:
                            _lines.append(f"📥 入库 NFO {_ing} 个"
                                          + (f" ｜ ❌ 失败 {total_failed} 个" if total_failed else ""))
                        elif total_translated > 0 or total_failed > 0:
                            _lines.append(f"✅ 翻译：{total_translated} 条 ｜ ❌ 失败：{total_failed} 条")
                        if _llm > 0 or _zhc > 0:
                            _lines.append(f"🤖 LLM：{_llm} 次 ｜ 🔄 繁转简：{_zhc} 条")
                        if _pool_skip:
                            _lines.append(f"♻️ 跳过已有译文：{_pool_skip} 条（池命中，未调 AI）")
                        if _coll or _exist:
                            _lines.append(f"📥 采集 {_coll} 词条 ｜ ✅ 已有译文 {_exist} 条（未重翻）")
                        if _pend:
                            _lines.append(f"🤖 待翻 {_pend} 个（按当前翻译范围；开启「入库后自动翻译」的会自动处理，否则请在库页点「全部翻译」）")
                        if _rec:
                            _lines.append(f"🔄 其中已恢复被删条目 {_rec} 个（重新入库）")
                        text = "\n".join(_lines)
                    else:
                        continue  # S3: 全部无需翻译，静默
                    self.post_message(mtype=NotificationType.Manual, title=self.plugin_name, text=text)
                    continue
                episodes = sorted(set(i["episode_num"] for i in items if i["episode_num"] is not None))
                seasons = sorted(set(i["season_num"] for i in items if i["season_num"] is not None))
                total_translated = sum(i["translated"] for i in items)
                total_failed = sum(i["failed"] for i in items)
                _rec = sum(int(i.get("recovered") or 0) for i in items)
                _llm = sum(i.get("llm_calls", 0) for i in items)
                _zhc = sum(i.get("zhconv", 0) for i in items)
                _pool_skip = sum(i.get("pool", 0) for i in items)
                _pend = sum(i.get("pending", 0) for i in items)
                _exist = sum(i.get("existing", 0) for i in items)
                _coll = sum(i.get("collected", 0) for i in items)
                _ing = sum(i.get("ingested", 0) for i in items)

                # 构建集数显示
                if len(episodes) == 1:
                    ep_text = f"第{episodes[0]}集"
                elif episodes:
                    ep_text = f"第{episodes[0]}-{episodes[-1]}集"
                else:
                    ep_text = ""

                season_text = ""
                if len(seasons) == 1:
                    season_text = f"第{seasons[0]}季 "
                elif len(seasons) > 1:
                    season_text = f"第{seasons[0]}-{seasons[-1]}季 "

                if total_translated > 0 or total_failed > 0 or _rec > 0 or _pend > 0 or _ing > 0:
                    _batch_tag = "（整合）" if (len(items) > 1 or any(i.get("batch") for i in items)) else ""
                    # v4.6.67（P0-C）：见电影分支 —— 按实际动作命名，NFO 数不再冒充翻译数。
                    if _ing > 0:
                        _hd, _icon = "入库完成", "📥"
                    elif total_translated > 0 or total_failed > 0:
                        _hd, _icon = "翻译完成", "📺"
                    else:
                        _hd, _icon = "恢复完成", "🔄"
                    _lines = [f"{_icon} {_hd}{_batch_tag}：{series_name} {season_text}{ep_text}".rstrip()]
                    if _ing > 0:
                        _lines.append(f"📥 入库 NFO {_ing} 个"
                                      + (f" ｜ ❌ 失败 {total_failed} 个" if total_failed else ""))
                    elif total_translated > 0 or total_failed > 0:
                        _lines.append(f"✅ 翻译：{total_translated} 条 ｜ ❌ 失败：{total_failed} 条")
                    if _llm > 0 or _zhc > 0:
                        _lines.append(f"🤖 LLM：{_llm} 次 ｜ 🔄 繁转简：{_zhc} 条")
                    if _pool_skip:
                        _lines.append(f"♻️ 跳过已有译文：{_pool_skip} 条（池命中，未调 AI）")
                    if _coll or _exist:
                        _lines.append(f"📥 采集 {_coll} 词条 ｜ ✅ 已有译文 {_exist} 条（未重翻）")
                    if _pend:
                        _lines.append(f"🤖 待翻 {_pend} 个（按当前翻译范围；开启「入库后自动翻译」的会自动处理，否则请在库页点「全部翻译」）")
                    if _rec:
                        _lines.append(f"🔄 其中已恢复被删条目 {_rec} 个（重新入库）")
                    text = "\n".join(_lines)
                else:
                    continue

                self.post_message(
                    mtype=NotificationType.Manual,
                    title=self.plugin_name,
                    text=text,
                )
            except Exception as e:
                logger.debug(f"[Webhook] 聚合通知发送失败: {e}")

    # ─────────────────────────────────────────────
    # Webhook 状态 API
    # ─────────────────────────────────────────────
    def _api_webhook_events(self, limit: int = 50):
        try:
            events = list(getattr(self, "_webhook_events", None) or [])
            return {"success": True, "data": events[:max(1, min(200, int(limit or 50)))]}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_webhook_events_clear(self):
        _g = self._api_gate()
        if _g:
            return _g
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            events = getattr(self, "_webhook_events", None)
            if events is not None:
                events[:] = [e for e in events if str(e.get("status")) == "missing"]
            self._webhook_received = 0
            self._webhook_processed = 0
            self._webhook_failed = 0
            self._webhook_error = ""
            self._webhook_last_event = ""
            try:
                self._save_state()
            except Exception:
                pass
            return {"success": True, "message": "Webhook 入库事件已清空（失效/待恢复保留）"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_db_purge_missing(self, data: Optional[dict] = None):
        _g = self._api_gate()
        if _g:
            return _g
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            db = getattr(self, "_people_db", None)
            if db is None:
                return {"success": False, "message": "翻译记录数据库未初始化"}
            _pid = self.__class__.__name__
            # v4.6.76（规范 §七/§二十二）：先查当前失效记录数 —— 0 条时明确「无需清理」，
            # 不做成「像发生了清理」的动作反馈。
            _miss = int(db.count_missing(plugin_id=_pid) if hasattr(db, "count_missing") else -1)
            if _miss < 0:
                # v4.6.98（P1-03）：计数查询失败（-1）**绝不能**当成 0 继续清理 ——
                # 不删任何数据库记录、不动事件列表，明确返回失败（此前会照常 purge，与注释要求相悖）。
                _m = "读取失效记录数量失败，已取消清理；请检查数据库后重试。"
                self._push_log("WARNING", _m)
                return {"success": False, "message": _m,
                        "data": {"purged": 0, "aborted": True, "reason": "count_error"}}
            if _miss == 0:
                # v4.6.84（用户实测）：数据库里已无观察期行，但事件列表里可能还残留
                # 「失效 / 待恢复」行 —— 例：先「清空翻译记录」把观察期行清掉了，
                # 事件却还挂着（用户点「清除」看到「无需清理」，事件其实并没删）。
                # 这里同步按数据库真实记录核对，清掉这些**无对应记录**的脏事件。
                _dirty, _kept_err, _cl_ok = 0, 0, True
                try:
                    _cl = self._cleanup_dirty_webhook_events() or {}
                    _dirty = int(_cl.get("removed_count") or 0)
                    _kept_err = int(_cl.get("kept_error_count") or 0)
                    _cl_ok = bool(_cl.get("success", True))
                except Exception:
                    _cl_ok = False
                if not _cl_ok:
                    # v4.6.99（报告 §七）：事件清理失败 → **不得显示清理成功**
                    _msg = "失效记录数量为 0，但部分事件状态无法确认，未执行强制清理。"
                    self._push_log("WARNING", _msg)
                    return {"success": False, "message": _msg,
                            "data": {"purged": 0, "none": True, "events_cleared": _dirty,
                                     "events_unconfirmed": _kept_err,
                                     "reason": "event_cleanup_error"}}
                if _dirty:
                    _msg = f"数据库已无失效记录；已同步清掉 {_dirty} 条残留的「失效 / 待恢复」事件"
                elif _kept_err:
                    _msg = (f"失效记录数量为 0，但 {_kept_err} 条事件状态无法确认，"
                            f"未执行强制清理。")
                else:
                    _msg = "当前没有插件管理的失效记录，无需清理"
                self._push_log("INFO", _msg)
                return {"success": True, "message": _msg,
                        "data": {"purged": 0, "none": True, "events_cleared": _dirty,
                                 "events_unconfirmed": _kept_err}}
            n = db.purge_all_missing(plugin_id=_pid) if hasattr(db, "purge_all_missing") else 0
            if int(n or 0) <= 0:
                # v4.6.98（P1-03 D/E）：实际删除 0 行（查询/写入失败或竞态）→ **不报告成功、不清事件**，
                # 避免「一半成功一半失败」（记录没删掉、事件却先没了）；删除行数必须与文案一致。
                _m2 = (f"清理失败：预期清理 {_miss} 条，实际未删除任何记录；"
                       f"事件列表已保留，请检查数据库后重试。")
                self._push_log("WARNING", _m2)
                return {"success": False, "message": _m2,
                        "data": {"purged": 0, "expected": _miss, "aborted": True}}
            # 事件列表同步清掉失效记录（只清 missing 事件；role_memory / 媒体身份历史不动）
            try:
                events = getattr(self, "_webhook_events", None)
                if events is not None:
                    self._webhook_events = [e for e in events if str(e.get("status")) != "missing"]
                    self._save_state()
            except Exception:
                pass
            self._push_log("INFO", f"已永久清除 {n} 条插件管理的失效记录"
                                   f"（观察期条目直接清理，不再等待；角色记忆与媒体身份历史保留）")
            self._db_items_cache = None
            return {"success": True,
                    "message": f"已永久清除 {n} 条插件管理的失效记录（判定为真删除，不再等待宽限期）",
                    "data": {"purged": n}}
        except Exception as e:
            logger.error(f"[DB] 清除失效记录失败: {e}")
            return {"success": False, "message": str(e)}

    def _api_webhook_status(self):
        """获取 Webhook 处理状态"""
        total = self._webhook_received
        processed = self._webhook_processed
        failed = self._webhook_failed
        success_rate = round(processed / max(total, 1) * 100, 1) if total > 0 else 0.0
        
        last_time = None
        if self._webhook_last_time:
            last_time = datetime.fromtimestamp(self._webhook_last_time).strftime("%Y-%m-%d %H:%M:%S")
        
        return {
            "success": True,
            "data": {
                "total_received": total,
                "processed": processed,
                "failed": failed,
                "success_rate": success_rate,
                "last_time": last_time,
                "last_event": self._webhook_last_event,
                "last_error": self._webhook_error,
                "server_count": len(self._get_all_emby_services()),
                "webhook_enabled": bool(getattr(self, "_webhook_enabled", False)),
                "pending_count": len(getattr(self, "_webhook_pending_config", {}) or {}),
                "held_count": (len(getattr(self, "_webhook_schedule", {}) or {})
                               + len(getattr(self, "_webhook_pending_config", {}) or {})),
                "scheduled_count": len(getattr(self, "_webhook_schedule", {}) or {}),
            }
        }

    def _api_poster(self, item_id: str = "", server_id: str = "", kind: str = ""):
        """NFO 条目只有 tmdbid（item_id 即 tmdbid）→ 先按 AnyProviderIdEquals=tmdb.{id}
        反查 Emby itemId（内存缓存 _emby_itemid_cache），再拉 Images/Primary（海报）或
        Images/Logo。只做右侧选中条目，失败返回 message（前端隐藏对应图位）。"""
        try:
            item_id = str(item_id or "").strip()
            kind = str(kind or "poster").strip().lower() or "poster"
            if not item_id:
                return {"success": False, "message": "缺少 item_id"}
            if not item_id.isdigit():
                # 非纯数字 item_id（旧 API 在线记录）不适用 tmdb 反查
                return {"success": False, "message": "该条目无 tmdbid，无法拉取海报"}
            services = self._get_all_emby_services()
            if not services:
                return {"success": False, "message": "无可用 Emby 服务器"}
            if str(server_id or "").strip():
                svc = self._find_target_server(services, str(server_id or ""))
            else:
                svc = services[0]
            if svc is None:
                return {"success": False, "message": "未匹配到 Emby 服务器"}
            url = self._get_service_url(svc)
            api_key = self._get_service_api_key(svc)
            if not url or not api_key:
                return {"success": False, "message": "Emby 服务器未配置完整"}
            skey = self._get_server_identifier(svc)
            ck = f"{skey}:{item_id}"
            cache = getattr(self, "_emby_itemid_cache", None)
            if cache is None:
                cache = {}
                self._emby_itemid_cache = cache
            eid = cache.get(ck)
            if eid:
                try:
                    cache.pop(ck, None)
                    cache[ck] = eid
                except Exception:
                    pass
            if not eid:
                client = EmbyClient(url, api_key, svc, user_id=self._get_service_user_id(svc),
                                    use_proxy=self._use_proxy)
                eid = client.search_item_by_provider("tmdb", item_id, ["Series", "Movie"])
                if eid:
                    cache[ck] = eid
                    try:
                        while len(cache) > 2000:
                            cache.pop(next(iter(cache)))
                    except Exception:
                        pass
            if not eid:
                return {"success": False, "message": "Emby 中未找到该 tmdbid 条目"}
            img_kind = "Logo" if kind in ("logo",) else "Primary"
            client = EmbyClient(url, api_key, svc, user_id=self._get_service_user_id(svc),
                                use_proxy=self._use_proxy)
            raw = client.get_image_bytes(f"/emby/Items/{eid}/Images/{img_kind}",
                                         params={"maxHeight": 480, "quality": 90})
            if not raw:
                if img_kind == "Primary":
                    return {"success": False, "message": "海报拉取失败"}
                return {"success": False, "message": "LOGO 不存在"}
            _mime = "image/png" if raw[:4] == b"\x89PNG" else "image/jpeg"
            return {"success": True,
                    "data": f"data:{_mime};base64,{base64.b64encode(raw).decode('ascii')}",
                    "kind": img_kind}
        except Exception as e:
            logger.debug(f"[Poster] 拉取失败: {e}")
            return {"success": False, "message": str(e)}

    # ============================================================
    # ============================================================
    def _db_items_page(self, items: list, limit: int = 0, offset: int = 0) -> dict:
        """库列表分页（UI-PAGE）：默认 limit=0 返回旧结构（data 为数组，向后兼容）；
        limit>0 时按 offset 切片，data 变为 {items,total,offset,limit,has_more}。"""
        try:
            _lim = int(limit or 0)
            _off = int(offset or 0)
        except Exception:
            _lim, _off = 0, 0
        if _lim > 0:
            _off = max(0, _off)
            _total = len(items)
            _page = items[_off:_off + _lim]
            return {"success": True, "data": {"items": _page, "total": _total,
                                              "offset": _off, "limit": _lim,
                                              "has_more": (_off + _lim) < _total}}
        return {"success": True, "data": items}

    def _annotate_db_items(self, db, items: list, mode: str) -> list:
        """库列表条目补充展示字段（source/poster_url/subdir/library_name/episode_count），
        并做洗版宽限期清理。抽取自 _api_db_items（保守移动，语义与顺序不变）。

        v4.6.66（P0-6）：来源判定由「server_id 是否为空」改为「是否有本地 nfo 目录」——
        Webhook 入库现在带真实 server_id（P0-1），旧判定会让 nfo 模式把新入库条目全部丢弃
        （用户实测：日志 3 个 NFO 入库成功、库页找不到）。NFO 记录必有 nfo_dir；纯 API 老记录没有。"""
        if mode == "nfo":
            items = [it for it in items if str(it.get("nfo_dir") or "")]
            for it in items:
                it["source"] = "nfo"
        else:
            items = [it for it in items if not str(it.get("nfo_dir") or "")]
            for it in items:
                it["source"] = "api"
        # v4.6.82：库页左栏一律用图标，不再为每个条目生成 / 保留海报 URL。
        # 原逐行海报会让无限滚动 / 翻页时对服务器发起大量图片请求（用户实测：一拉就疯狂请求）；
        # 且 v4.6.66 起 item_id 是媒体身份（tmdb/…）而非 Emby 条目 ID，拼出的图 URL 本就无效。
        # 右侧详情海报仍走 GET /poster（单张、按需），不受影响。
        for it in items:
            it.pop("poster_url", None)
        items = [it for it in items if str(it.get("item_type") or "") != "Episode"]
        _roots = self._all_nfo_roots()
        for it in items:
            _nd = str(it.get("nfo_dir") or "").replace("\\", "/")
            _sd = ""
            if _nd:
                if _roots:
                    for _r in _roots:
                        _rr = str(_r).replace("\\", "/").rstrip("/")
                        if _rr and (_nd == _rr or _nd.startswith(_rr + "/")):
                            _rel = _nd[len(_rr):].strip("/")
                            if _rel:
                                _sd = _rel.split("/")[0]
                            break
                if not _sd:
                    _seg = [x for x in _nd.split("/") if x]
                    _sd = _seg[-1] if len(_seg) > 1 else (_seg[0] if _seg else "")
            it["subdir"] = _sd
        for it in items:
            if not str(it.get("library_name") or "").strip():
                it["library_name"] = self._library_name_for_path(str(it.get("nfo_dir") or ""))
        try:
            # v4.6.66：跨来源统计集数（实现带真实 server_id，不能再按「本地来源」过滤）
            _epmap = db.episode_counts(plugin_id=self.__class__.__name__,
                                       item_ids=[str(it.get("item_id")) for it in items],
                                       server_id=None)
            for it in items:
                it["episode_count"] = _epmap.get(str(it.get("item_id")), 0)
        except Exception:
            pass
        if getattr(self, "_enabled", False):
            # v4.6.103（LIB-005）：洗版宽限期清理**限频 120s** —— expired_item_ids（全表
            # CAST(deleted_at AS REAL) 扫描）与 purge_expired（全表 DELETE）此前每调用一次
            # /db/items 就跑一遍，而库页轮询每 8s 一次、条目 360 个时直接拖慢整页。
            # 宽限期以「小时」计，120s 粒度完全够用；内存时间戳，不落盘。
            _now = time.time()
            if _now - float(getattr(self, "_purge_scan_ts", 0.0) or 0.0) >= 120.0:
                self._purge_scan_ts = _now
                try:
                    _gh = float(getattr(self, "_nfo_dead_grace_hours", 24) or 24)
                    _pid2 = self.__class__.__name__
                    _expired = db.expired_item_ids(plugin_id=_pid2, grace_hours=_gh)
                    if _expired:
                        db.purge_expired(plugin_id=_pid2, grace_hours=_gh)
                        _sexp = set(str(x) for x in _expired)
                        items = [it for it in items if str(it.get("item_id")) not in _sexp]
                        self._push_log("INFO", f"已清理 {len(_expired)} 个超过宽限期未恢复的条目（判定为真删除）")
                except Exception as _e:
                    logger.warning(f"[DB] 洗版宽限期处理失败: {_e}")
        return items

    def _api_db_items(self, server_id: str = "", limit: int = 0, offset: int = 0):
        """库页左侧：条目列表（来自本插件数据库；v3.4.16 按模式过滤；UI-PAGE 支持分页）。
        v4.6.33：limit>0 走 SQL 层分页（db.library_items_page），不再整表 SELECT * 落 Python。"""
        try:
            db = getattr(self, "_people_db", None)
            if db is None:
                return {"success": False, "message": "翻译记录数据库未初始化"}
            try:
                _lim = int(limit or 0)
                _off = max(0, int(offset or 0))
            except Exception:
                _lim, _off = 0, 0
            _now_ts = time.time()
            mode = str(getattr(self, "_scan_mode", "nfo") or "nfo")
            try:
                _busy = any(self._task_running(_t) for _t in ("scan", "translate", "writeback", "pool", "probe"))
            except Exception:
                _busy = True
            # ── 分页路径（UI-PAGE）：SQL 层聚合，只把当前页条目加载进内存 ──
            if _lim > 0:
                _items, _total = db.library_items_page(
                    plugin_id=self.__class__.__name__, scan_mode=mode,
                    limit=_lim, offset=_off)
                _items = self._annotate_db_items(db, list(_items or []), mode)
                _total = int(_total or 0)
                return {"success": True, "data": {"items": _items, "total": _total,
                                                  "offset": _off, "limit": _lim,
                                                  "has_more": (_off + _lim) < _total}}
            # ── 旧路径：整表 + 10s 缓存 + 数组（向后兼容） ──
            _cache = getattr(self, "_db_items_cache", None)
            if not _busy and isinstance(_cache, dict) and (_now_ts - float(_cache.get("ts") or 0)) < 10.0:
                return self._db_items_page(list(_cache.get("data") or []), 0, 0)
            items = db.library_items(plugin_id=self.__class__.__name__) or []
            items = self._annotate_db_items(db, items, mode)
            if not _busy:
                try:
                    self._db_items_cache = {"ts": _now_ts, "data": list(items)}
                except Exception:
                    pass
            return self._db_items_page(items, 0, 0)
        except Exception as e:
            logger.error(f"[DB] 读取库列表失败: {e}")
            return {"success": False, "message": str(e)}

    def _aggregate_people_rows(self, people: List[dict]) -> List[dict]:
        """把人物行按「原文名 + 类型 + 译文 + 角色译文」汇总 —— 库页右栏搜索结果用。
        带出现次数（count）、剧名集合（series）、条目集合（item_ids）。
        v4.6.106（LIB-012）：从 _api_db_people 抽出，供「全库搜索」与「条目内搜索」共用同一口径，
        保证切范围只改「搜哪些行」，结果的呈现（N 处 / 剧名标签 / 逐处清单）完全一致。"""
        rows: List[dict] = []
        idx: Dict[str, int] = {}
        for p in people or []:
            k = f"{p.get('name_before')}|{p.get('type')}|{p.get('name_after')}|{p.get('role_after')}"
            if k not in idx:
                idx[k] = len(rows)
                rows.append({"name_before": p.get("name_before"), "name_after": p.get("name_after"),
                             "type": p.get("type"), "role_after": p.get("role_after"),
                             "role_before": p.get("role_before"), "count": 0,
                             "series": set(), "item_ids": set()})
            r = rows[idx[k]]
            r["count"] += 1
            if p.get("series_name"):
                r["series"].add(p["series_name"])
            r["item_ids"].add(str(p.get("item_id") or ""))
        for r in rows:
            r["series"] = sorted(r["series"])[:5]
            r["item_ids"] = sorted(x for x in r["item_ids"] if x)
        return rows

    def _api_db_people(self, item_id: str = "", server_id: str = "", keyword: str = ""):
        """库页右侧：某条目全部人物（翻译前/后）。
        v3.4.49：无 item_id 且带 keyword → 全库搜索人物。
        v4.6.106（LIB-012）：带 item_id 且带 keyword → **只在该条目内**搜索（此前不识别 keyword，
        前端搜索框又只发 keyword 不发 item_id，于是「在本条目的名单里筛人」实际扫了全库、串到别的剧）。"""
        try:
            db = getattr(self, "_people_db", None)
            if db is None:
                return {"success": False, "message": "翻译记录数据库未初始化"}
            if not item_id:
                kw = (keyword or "").strip()
                if not kw:
                    return {"success": True, "data": {"search": True, "item": None, "people": []}}
                people = db.search_people(plugin_id=self.__class__.__name__, keyword=kw, limit=200)
                return {"success": True, "data": {"search": True, "scoped": False, "item": None,
                                                  "people": self._aggregate_people_rows(people)}}
            people = db.people_of_item(plugin_id=self.__class__.__name__,
                                       item_id=item_id, server_id=server_id)
            # v4.6.106（LIB-012）：条目内搜索 —— 按关键词过滤（原文名 / 译文 / 角色 / 角色译文，不区分大小写）
            _kw = (keyword or "").strip().lower()
            if _kw:
                people = [p for p in people
                          if any(_kw in str(p.get(_f) or "").lower()
                                 for _f in ("name_before", "name_after", "role_before", "role_after"))]
            meta = db.item_meta(plugin_id=self.__class__.__name__,
                                item_id=item_id, server_id=server_id)
            poster_url = ""
            if meta and not str(meta.get("server_id") or ""):
                try:
                    poster_url = self._proxy_poster(self._tmdb_poster_url(item_id, meta.get("item_type") or ""))
                except Exception:
                    poster_url = ""
            if meta:
                meta = dict(meta)
                meta["poster_url"] = poster_url
            _main_cast = []
            _ep_map = {}
            for p in people:
                _s = p.get("season_num")
                _e = p.get("episode_num")
                if _s is None and _e is None:
                    _main_cast.append(p)
                else:
                    _key = (_s, _e)
                    if _key not in _ep_map:
                        _ep_map[_key] = {
                            "season": _s, "episode": _e,
                            "nfo_path": p.get("nfo_path") or "",
                            "title": str(p.get("title") or "").strip(),
                            "people": [],
                        }
                    elif not _ep_map[_key].get("title"):
                        _ep_map[_key]["title"] = str(p.get("title") or "").strip()
                    _ep_map[_key]["people"].append(p)
            _episodes = sorted(_ep_map.values(),
                               key=lambda x: (x.get("season") or 0, x.get("episode") or 0))
            # v4.6.96：同一「原文名 + 角色」的重复 credit（历史数据）→ 展示去重（与 Emby 按人物展示一致），
            # 剧级名单与各集名单都去重；库中数据与翻译流程不受影响。
            _main_cast = self._dedup_credit_rows(_main_cast)
            for _ep in _episodes:
                _ep["people"] = self._dedup_credit_rows(_ep.get("people") or [])
            return {"success": True, "data": {
                "item": meta,
                # v4.6.106（LIB-012）：条目内搜索时同样返回「汇总行」（N 处 / 剧名 / 条目集合），
                # 与全库搜索完全同构 —— 前端只需切范围、不用改渲染。
                "search": bool(_kw),
                "scoped": bool(_kw),
                "people": (self._aggregate_people_rows(people) if _kw else people),
                "main_cast": _main_cast,
                "episodes": _episodes,
            }}
        except Exception as e:
            logger.error(f"[DB] 读取条目人物失败: {e}")
            return {"success": False, "message": str(e)}

    def _api_db_stats(self):
        """仪表盘：翻译记录统计"""
        try:
            db = getattr(self, "_people_db", None)
            if db is None:
                return {"success": False, "message": "翻译记录数据库未初始化"}
            stats = db.stats(plugin_id=self.__class__.__name__)
            return {"success": True, "data": stats}
        except Exception as e:
            logger.error(f"[DB] 读取统计失败: {e}")
            return {"success": False, "message": str(e)}

    def _api_db_role_memory(self, item_id: str = "", server_id: str = ""):
        """第二排角色翻译记忆（v4.6.70）：整体统计 / 某剧的记忆明细。

        记忆与 person 表解耦 —— 删除/恢复/清库都不会清它，只有「清除该剧翻译记忆」会。
        """
        try:
            db = getattr(self, "_people_db", None)
            if db is None:
                return {"success": False, "message": "翻译记录数据库未初始化"}
            _pid = self.__class__.__name__
            _data = {"stats": db.role_memory_stats(plugin_id=_pid)}
            _iid = str(item_id or "").strip()
            if _iid:
                _data["items"] = db.role_memory_of_item(
                    plugin_id=_pid, item_id=_iid, server_id=str(server_id or ""))
            return {"success": True, "data": _data}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_db_role_memory_clear(self, data: Optional[dict] = None):
        """「清除该剧角色翻译记忆」—— 记忆的**唯一**清除入口（v4.6.70）。

        删除某集 / 整剧删除 / 恢复 / 清空翻译记录都不清记忆（洗版重建仍可复用旧译文）；
        只有用户显式点这里才清。
        """
        _g = self._api_gate()
        if _g:
            return _g
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            d = data or {}
            db = getattr(self, "_people_db", None)
            if db is None:
                return {"success": False, "message": "翻译记录数据库未初始化"}
            _sid = str(d.get("server_id") or "")
            _ser = str(d.get("item_id") or d.get("series_id") or "")
            _sn = str(d.get("series_name") or "")
            if not _ser and not _sn:
                return {"success": False, "message": "缺少 item_id / series_name（无法定位该剧）"}
            _n = db.role_memory_delete_series(plugin_id=self.__class__.__name__,
                                              server_id=_sid, series_id=_ser, series_name=_sn)
            return {"success": True, "message": f"已清除该剧角色翻译记忆 {_n} 条",
                    "data": {"deleted": _n}}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _pending_stats(self, snap: Optional[dict] = None) -> dict:
        """库内待翻统计（唯一口径 v4.6.61 · P1-2）—— 直接取统一快照：
        徽章 / 明细 / 预估 / worker 日志 / 通知全部同源（旧实现另维护一套 SQL 口径，已废）。
        条目 = 词条 × 条目明细对按 item 去重（含人数上限 / 类型开关 / 已是中文跳过）。

        :param snap: v4.6.103 —— 调用方已经算过的同一份快照（_tx_pending_snapshot 结果）。
                     传入即直接复用，不再重复跑一遍重 SQL（「任务统计」徽章每次轮询曾算两遍）。"""
        try:
            _s = snap if isinstance(snap, dict) else self._tx_pending_snapshot()
        except Exception:
            return {"names": 0, "roles": 0, "items": 0, "names_scope": 0, "roles_scope": 0,
                    "person_on": True, "role_on": True, "disabled": [],
                    "items_scope": 0, "pool": 0, "total": 0}
        return {"names": int(_s.get("person") or 0), "roles": int(_s.get("role") or 0),
                "items": int(_s.get("items") or 0),
                "names_scope": int(_s.get("person_scope") or 0),
                "roles_scope": int(_s.get("role_scope") or 0),
                "items_scope": int(_s.get("items_scope") or 0),
                "person_on": bool(_s.get("person_on", True)),
                "role_on": bool(_s.get("role_on", True)),
                "disabled": list(_s.get("disabled") or []),
                "pool": int(_s.get("pool") or 0), "total": int(_s.get("total") or 0)}

    def _api_db_pending_detail(self, limit_items: int = 30, terms_per_item: int = 12):
        """「有任务 · 待翻译」明细 —— 与徽章/合计完全同源（v4.6.61 · P1-2）：
        直接取统一快照的 items_list（同一 SQL 口径），不再按每一条目单独查一遍
        （旧实现逐条目跑 force_item_terms，列表与合计各自维护、口径易漂移）。"""
        try:
            _db = getattr(self, "_people_db", None)
            if _db is None:
                return {"success": False, "message": "翻译记录数据库未初始化"}
            _s = self._tx_pending_snapshot(with_detail=True)
            _lim = max(1, min(100, int(limit_items or 30)))
            _tpi = max(1, min(50, int(terms_per_item or 12)))
            out = []
            for it in list(_s.get("items_list") or [])[:_lim]:
                _nm = list(it.get("names") or [])
                _rl = list(it.get("roles") or [])
                out.append({"item_id": str(it.get("item_id") or ""),
                            "server_id": str(it.get("server_id") or ""),
                            "title": str(it.get("title") or it.get("item_id") or ""),
                            "names": _nm[:_tpi], "roles": _rl[:_tpi],
                            "names_total": len(_nm), "roles_total": len(_rl)})
            return {"success": True, "data": {
                "items": out, "items_total": int(_s.get("items") or 0),
                "names_pending": int(_s.get("person") or 0), "roles_pending": int(_s.get("role") or 0),
                "names_scope": int(_s.get("person_scope") or 0), "roles_scope": int(_s.get("role_scope") or 0),
                "person_on": bool(_s.get("person_on", True)), "role_on": bool(_s.get("role_on", True)),
            }}
        except Exception as e:
            logger.error(f"[DB] 待翻译明细失败: {e}")
            return {"success": False, "message": str(e)}

    def _api_db_pending_snapshot(self):
        """唯一待翻统计接口（v4.6.61 · P1-2）—— 徽章 / 明细 / 预估 / 日志全部同源；
        附带 items_list（按条目分组的待翻明细）。"""
        try:
            _s = self._tx_pending_snapshot(with_detail=True)
            return {"success": True, "data": _s}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_translate_jobs(self, limit: int = 20, job_id: str = ""):
        """翻译任务列表 / 详情（v4.6.61 · P1-6 SQLite 持久化；v4.6.62 详情附词条与批次明细）。"""
        try:
            _jdb = self._tx_job_db()
            _jid = str(job_id or "").strip()
            if _jid:
                _row = _jdb.get(plugin_id=self.__class__.__name__, job_id=_jid)
                if not _row:
                    return {"success": False, "message": "未找到该任务"}
                _terms = _jdb.terms_summary(plugin_id=self.__class__.__name__, job_id=_jid)
                _batches = _jdb.list_batches(plugin_id=self.__class__.__name__, job_id=_jid, limit=100)
                return {"success": True, "data": {"job": _row, "terms": _terms, "batches": _batches}}
            _rows = _jdb.list_recent(plugin_id=self.__class__.__name__,
                                     limit=max(1, min(200, int(limit or 20))))
            return {"success": True, "data": {"jobs": _rows, "current": str(getattr(self, "_tx_job_id", "") or "")}}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_translate_job_create(self, data: Optional[dict] = None):
        """创建并触发一个翻译任务（第 25 节 POST /translate/jobs）—— 等价于手动授予一次翻译许可。
        body: source(library/pool/both)、scope(person/role/both)、item_id/server_id（可选，条目级）、
              terms（可选，词条级）。"""
        _g = self._api_gate()
        if _g:
            return _g
        # v4.6.70（P0-3）：与其它数据操作一致的任务忙碌门禁 —— 此前本接口只查 _api_gate()，
        # 可在已有翻译任务运行中重复创建 Job；多个 Job 会共享同一套消费许可字段
        # （_tx_source / _tx_target_scope / _tx_scope_items / _tx_only_terms）→ 被隐式合并成一个许可。
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        if not self._ai_enabled():
            return {"success": False, "message": "AI 翻译总开关已关闭（设置页「启用 AI 翻译」）"}
        try:
            data = data or {}
            _src = str(data.get("source") or "library").strip().lower()
            if _src not in ("library", "pool", "both"):
                _src = "library"
            _scope = str(data.get("scope") or "both").strip().lower()
            if _scope not in ("person", "role", "both"):
                _scope = "both"
            _iid = str(data.get("item_id") or "").strip()
            _terms = data.get("terms") if isinstance(data.get("terms"), (list, tuple)) else None
            # v4.6.73（报告第十六节）：同一条目互斥 —— 该条目正在写回/重翻时拒绝，避免写回与重翻打架；
            # 其它条目不受影响（与全局任务锁不同，这里只锁「同一条目」）。
            if _iid and self._item_busy(str(data.get("server_id") or ""), _iid):
                return {"success": False,
                        "message": "该条目正在写回/重翻中，请等完成后再操作（同一条目互斥）"}
            _payload = ""
            if _iid:
                try:
                    _job = {"server_id": str(data.get("server_id") or ""),
                            "title": str(data.get("title") or ""),
                            "year": str(data.get("year") or ""),
                            "names": [], "roles": [], "ts": time.time()}
                    _payload = json.dumps({_iid: _job}, ensure_ascii=False)
                except Exception:
                    _payload = ""
            self._tx_request_consume(source=_src, scope=_scope,
                                     items=([_iid] if _iid else None), terms=_terms,
                                     payload=_payload)
            _jid = str(getattr(self, "_tx_job_id", "") or "")
            self._push_log("INFO", f"翻译任务已创建：job={_jid}（来源 {_src} / 范围 {_scope}"
                                   + (f" / 条目 {_iid}" if _iid else "") + "）")
            return {"success": True, "job_id": _jid,
                    "message": f"翻译任务已创建并交后台执行（job={_jid}）"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_translate_job_cancel(self, data: Optional[dict] = None):
        """取消任务（第 22 节）—— Job=cancelled，**不删除 pending**（未翻成功的词条留在库中，
        下次再翻会生成新 Job）。若取消的是当前在跑的任务，同时请求 worker 归还消费许可。"""
        _g = self._api_gate()
        if _g:
            return _g
        try:
            data = data or {}
            _jid = str(data.get("job_id") or "").strip()
            if not _jid:
                return {"success": False, "message": "缺少 job_id"}
            _jdb = self._tx_job_db()
            _row = _jdb.get(plugin_id=self.__class__.__name__, job_id=_jid)
            if not _row:
                return {"success": False, "message": "未找到该任务"}
            _st = str(_row.get("status") or "")
            if _st in ("done", "cancelled"):
                return {"success": True, "message": f"任务已是 {_st}，无需取消"}
            _jdb.update(plugin_id=self.__class__.__name__, job_id=_jid, status="cancelled",
                        finished_at=datetime.now().isoformat(timespec="seconds"),
                        error_message="用户取消（pending 已保留，可再次翻译）")
            _is_cur = (_jid == str(getattr(self, "_tx_job_id", "") or ""))
            if _is_cur:
                # 请求 worker 归还消费许可（下一次循环开头处理终止分支）；pending 不动
                self._tx_stop = True
                self._tx_wake()
            self._push_log("INFO", f"翻译任务已取消：job={_jid}（未完成词条保留为待翻，可再次发起）")
            return {"success": True, "job_id": _jid,
                    "message": "任务已取消；未完成的词条仍保留在待翻列表，可随时重新翻译"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_translate_job_resume(self, data: Optional[dict] = None):
        """恢复任务（第 22 节）—— cancelled/interrupted 重新入队：force 任务按 payload 恢复条目，
        其它按原 source/scope 重新授予消费许可（Job 复用同一 id，状态回 queued）。"""
        _g = self._api_gate()
        if _g:
            return _g
        if not self._ai_enabled():
            return {"success": False, "message": "AI 翻译总开关已关闭（设置页「启用 AI 翻译」）"}
        try:
            data = data or {}
            _jid = str(data.get("job_id") or "").strip()
            if not _jid:
                return {"success": False, "message": "缺少 job_id"}
            _jdb = self._tx_job_db()
            _row = _jdb.get(plugin_id=self.__class__.__name__, job_id=_jid)
            if not _row:
                return {"success": False, "message": "未找到该任务"}
            if str(_row.get("status") or "") in ("queued", "running"):
                return {"success": True, "message": "任务已在运行，无需恢复"}
            _payload = {}
            try:
                _payload = json.loads(str(_row.get("payload") or "{}") or "{}")
            except Exception:
                _payload = {}
            _scope = str(_row.get("scope") or "both") or "both"
            _src = str(_row.get("source") or "library") or "library"
            if isinstance(_payload, dict) and _payload:
                _jobs = getattr(self, "_tx_force_jobs", None)
                if _jobs is None:
                    _jobs = {}
                    self._tx_force_jobs = _jobs
                for _iid, _job in _payload.items():
                    if str(_iid or "").strip() and isinstance(_job, dict):
                        _jobs.setdefault(str(_iid), _job)
                self._tx_request_consume(source="library", items=list(_payload.keys()),
                                         scope=_scope, resume_job_id=_jid)
            else:
                self._tx_request_consume(source=_src, scope=_scope, resume_job_id=_jid)
            self._push_log("INFO", f"翻译任务已恢复：job={_jid}（来源 {_src} / 范围 {_scope}）")
            return {"success": True, "job_id": _jid, "message": f"任务已恢复（job={_jid}）"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_db_translate_preview(self, item_id: str = "", server_id: str = ""):
        """翻译预估。无参数 = 全库口径（库页角标 / 全部翻译弹窗）；
        传 item_id = 单条目口径（「重新翻译」弹窗），按「类型开关 + 人数上限」统计可翻词条。"""
        try:
            db = getattr(self, "_people_db", None)
            if db is None:
                return {"success": False, "message": "翻译记录数据库未初始化"}
            _mode = str(getattr(self, "_scan_mode", "nfo") or "nfo")
            _iid = str(item_id or "").strip()
            if _iid:
                _tr = self._collect_trans_types().get("translate", {})
                _person_on = bool(_tr.get("person", True))
                _role_on = bool(_tr.get("role", True))
                _limits = self._tx_limits_by_level()
                _sid = str(server_id or "").strip()
                _ex_ep = self._tx_exclude_episodes()
                _in_scope = db.force_item_terms(plugin_id=self.__class__.__name__, item_id=_iid,
                                                server_id=_sid, limits=_limits,
                                                exclude_episodes=_ex_ep) \
                    or {"names": [], "roles": []}
                _pend = db.force_item_terms(plugin_id=self.__class__.__name__, item_id=_iid,
                                            server_id=_sid, limits=_limits, only_pending=True,
                                            exclude_episodes=_ex_ep) \
                    or {"names": [], "roles": []}

                def _cnt(_terms, _key, _on, _skip=False, _role=False):
                    return len({str(t).strip() for t, pt in (_terms.get(_key) or [])
                                if str(t or "").strip()
                                and (self._tx_role_type_enabled(pt, "both") if _role
                                     else self._tx_type_enabled(pt, "both"))
                                and not (_skip and self._skip_no_translate(t))}) if _on else 0

                _n = _cnt(_pend, "names", _person_on, True)
                _r = _cnt(_pend, "roles", _role_on, True, True)
                _n_all = _cnt(_in_scope, "names", _person_on)
                _r_all = _cnt(_in_scope, "roles", _role_on, False, True)
                return {"success": True, "data": {
                    "names_pending": int(_n), "roles_pending": int(_r),
                    "names_scope": int(_n_all), "roles_scope": int(_r_all),
                    "items_pending": 1 if (_n or _r) else 0,
                    "person_enabled": _person_on, "role_enabled": _role_on,
                    "pending_items": [], "scope": "item",
                }}
            # v4.6.103（LIB-005）：徽章数与明细**共用同一份快照** —— 此前 _pending_stats() 与
            # _tx_pending_snapshot(with_detail=True) 各算一遍（同一轮跑两遍重 SQL：pending_terms_full
            # × 4 + count_pool_status），而前端每 8s 轮询一次，是「任务统计」迟迟转不出来的主因之一。
            _snap = self._tx_pending_snapshot(with_detail=True)
            _s = self._pending_stats(_snap)
            _pend_items = []
            try:
                # v4.6.61：徽章悬浮列表直接取统一快照明细（与合计完全同口径）
                _detail = _snap.get("items_list") or []
                _pend_items = [{"item_id": str(x.get("item_id") or ""),
                                "server_id": str(x.get("server_id") or ""),
                                "title": str(x.get("title") or x.get("item_id") or "")}
                               for x in _detail[:10]]
            except Exception:
                _pend_items = []
            # v4.6.61（P1-7）：写回状态独立统计 —— 「翻译完成 ≠ 写回完成」
            _wb = {}
            try:
                _wb = self._wb_db().stats(plugin_id=self.__class__.__name__)
            except Exception:
                _wb = {}
            return {"success": True, "data": {
                "names_pending": _s["names"], "roles_pending": _s["roles"],
                "names_scope": _s.get("names_scope", 0), "roles_scope": _s.get("roles_scope", 0),
                "items_pending": _s["items"],
                "person_enabled": _s["person_on"], "role_enabled": _s["role_on"],
                "pending_items": _pend_items,
                "writeback_pending": int(_wb.get("writeback_pending") or 0),
                "writeback_failed": int(_wb.get("failed") or 0),
                "writeback_writing": int(_wb.get("writing") or 0),
                "writeback_missing": int(_wb.get("missing") or 0),
                "pool_pending": int(_s.get("pool") or 0),
            }}
        except Exception as e:
            logger.error(f"[DB] 翻译预估失败: {e}")
            return {"success": False, "message": str(e)}

    def _api_db_restore(self, data: Optional[dict] = None):
        _g = self._api_gate()
        if _g:
            return _g
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            data = data or {}
            item_id = str(data.get("item_id") or "").strip()
            server_id = str(data.get("server_id") or "").strip()
            if not item_id:
                return {"success": False, "message": "缺少 item_id 参数"}
            _r = self._restore_item_to_nfo(item_id, server_id)
            self._db_items_cache = None
            # v4.6.63（关键修复）：手动「写入」必须同步写回状态 —— 此前只写文件、从不更新
            # writeback_state，于是「待写回」徽章永远挂着（用户：点了「写入」待写回也没消失，
            # 难道必须点「全部写回」？）。现在写入成功即标 done、文件不存在标 missing。
            try:
                _wdb = self._wb_db()
                _wd = _r.get("data") or {}
                if _r.get("success") and not _wd.get("missing"):
                    _wdb.set_status(plugin_id=self.__class__.__name__, server_id=server_id,
                                    item_id=item_id, status="done", error="",
                                    changed_count=int(_wd.get("changed") or 0),
                                    file_sig=self._wb_item_fp(item_id, server_id))
                elif _wd.get("missing"):
                    _wdb.set_status(plugin_id=self.__class__.__name__, server_id=server_id,
                                    item_id=item_id, status="missing",
                                    error=str(_r.get("message") or "")[:200],
                                    file_sig=self._wb_item_fp(item_id, server_id))
            except Exception as _we:
                logger.debug(f"[Writeback] 手动写入状态同步失败（非致命）: {_we}")
            if _r.get("success"):
                # 第一排（人名）再额外同步 Emby（Person 实体改名，全局生效）
                try:
                    if getattr(self, "_emby_name_sync", True) and not bool(getattr(self, "_nfo_preview", False)):
                        _db = getattr(self, "_people_db", None)
                        _recs = _db.people_of_item(plugin_id=self.__class__.__name__,
                                                   item_id=item_id, server_id=server_id) if _db else []
                        _pairs: Dict[str, str] = {}
                        for _rec in (_recs or []):
                            _nb = str(_rec.get("name_before") or "").strip()
                            _na = str(_rec.get("name_after") or "").strip()
                            if _nb and _na and _na != _nb:
                                _pairs[_nb] = _na
                        _ok = _skip = _fail = 0
                        for _nb, _na in _pairs.items():
                            _sr = self._emby_sync_manual_rename(_nb, _na, server_id=server_id)
                            if _sr.get("ok"):
                                if _sr.get("skipped"):
                                    _skip += 1
                                else:
                                    _ok += 1
                            else:
                                _fail += 1
                        if _ok or _skip or _fail:
                            _line = f"；Emby 人名：改名 {_ok} · 已是译文 {_skip} · 失败 {_fail}"
                            _r["message"] = str(_r.get("message") or "") + _line
                            if isinstance(_r.get("data"), dict):
                                _r["data"]["emby"] = {"renamed": _ok, "skipped": _skip, "failed": _fail}
                            self._push_log("INFO", f"写入后同步 Emby 人名：改名 {_ok} · 已是译文 {_skip} · 失败 {_fail}")
                except Exception as _e:
                    logger.debug(f"[DB] 写入后同步 Emby 人名失败（非致命）: {_e}")
            return _r
        except Exception as e:
            logger.error(f"[DB] 恢复失败: {e}\n{traceback.format_exc()}")
            return {"success": False, "message": str(e)}

    def _restore_item_to_nfo(self, item_id: str, server_id: str = "", auto: bool = False) -> dict:
        """把某条目库中已翻译名单写回本地 nfo 文件（不调 LLM）—— 单条版与「全部写回」共用。

        仅支持 NFO 条目（库中带 nfo_path 的记录）。旧版 API 在线记录
        （server_id 非空、无 nfo_path）已不再支持写回 Emby ——
        如需清理请使用库页「清空异模式数据」（/db/clear_other）。
        auto=True 供自动写回 worker 使用 —— 内容已是译文（apply 改动 0）时不落盘，
        避免无谓改动文件 mtime（手动路径保持旧行为：无改动也保存以便补锁 Cast）。
        :return: {"success", "message", "data": {...} | "skip": True}
        """
        try:
            item_id = str(item_id or "").strip()
            if not item_id:
                return {"success": False, "message": "缺少 item_id 参数"}
            db = getattr(self, "_people_db", None)
            if db is None:
                return {"success": False, "message": "翻译记录数据库未初始化"}
            _pid = self.__class__.__name__
            meta = db.item_meta(plugin_id=_pid, item_id=item_id, server_id=server_id)
            if not meta:
                return {"success": False, "message": f"库中无此条目记录: {item_id}", "data": {"skip": True}}
            people_records = db.people_of_item(plugin_id=_pid, item_id=item_id, server_id=server_id)
            if not people_records:
                return {"success": False, "message": "库中该条目无人物记录", "data": {"skip": True}}

            path_groups: Dict[str, list] = {}
            _n_with_path = 0
            for rec in people_records or []:
                _p = str(rec.get("nfo_path") or "").strip()
                if not _p:
                    continue
                _n_with_path += 1
                if os.path.isfile(_p):
                    path_groups.setdefault(_p, []).append(rec)
            if path_groups:
                done = changed_total = failed = skipped = noop = 0
                for _p, recs in path_groups.items():
                    try:
                        r = self._write_nfo_once(item_id, server_id, _p, people_records=recs, auto=auto)
                        if r.get("success"):
                            done += 1
                            changed_total += int((r.get("data") or {}).get("changed", 0))
                            if (r.get("data") or {}).get("noop"):
                                noop += 1
                        elif "无已翻译名单" in str(r.get("message") or ""):
                            skipped += 1
                        else:
                            failed += 1
                    except Exception as _e:
                        failed += 1
                        logger.warning(f"[DB] 写回 nfo 失败 {_p}: {_e}")
                msg = f"已写回 {done} 个 nfo 文件，改动 {changed_total} 条"
                if noop:
                    msg += f"，{noop} 个已是译文（未重复写）"
                if skipped:
                    msg += f"，{skipped} 个无译文可写（已跳过）"
                if failed:
                    msg += f"，失败 {failed}"
                _miss = _n_with_path - sum(len(v) for v in path_groups.values())
                if _miss > 0:
                    msg += f"，跳过 {_miss} 条（nfo 已不存在，可能已删除或正在观察期）"
                return {"success": failed == 0, "message": msg,
                        "data": {"files": done, "changed": changed_total, "failed": failed,
                                 "skipped": skipped, "noop": noop, "skipped_missing": max(0, _miss)}}

            if _n_with_path:
                _recs_wp = [r for r in (people_records or []) if str(r.get("nfo_path") or "").strip()]
                _rest = ""
                try:
                    _gh = float(getattr(self, "_nfo_dead_grace_hours", 24) or 24)
                    _ts = []
                    for _r in _recs_wp:
                        _d = str(_r.get("deleted_at") or "").strip()
                        if _d:
                            try:
                                _ts.append(float(_d))
                            except Exception:
                                pass
                    if _ts:
                        _left = max(0.0, _gh - (time.time() - max(_ts)) / 3600.0)
                        _rest = (f"，观察期约剩 {_left:.1f} 小时" if _left > 0
                                 else "，观察期已过（下次维护会自动清理这些记录）")
                except Exception:
                    _rest = ""
                _m = (f"该条目的 nfo 文件已不存在（服务器已删除或正在洗版观察期{_rest}）："
                      f"库中 {_n_with_path} 条记录的目标文件都找不到，本次未写入任何内容。"
                      f"等它重新入库后会自动恢复翻译名单并写回，现在无需手动操作")
                self._push_log("INFO", f"写入 nfo 已跳过：该条目 {_n_with_path} 条记录的目标文件都不存在{_rest}")
                return {"success": False, "message": _m,
                        "data": {"changed": 0, "saved": False, "missing": True, "skipped": _n_with_path}}

            return {"success": False,
                    "message": "该条目为早期 API 在线记录（Emby 写回已下线，v3.5.0）。如需保留请导出备份，清理请用库页「清空异模式数据」",
                    "data": {"skip": True}}
        except Exception as e:
            logger.error(f"[DB] 恢复失败: {e}\n{traceback.format_exc()}")
            return {"success": False, "message": str(e)}

    def _api_db_translate_library(self, data: Optional[dict] = None):
        _g = self._api_gate()
        if _g:
            return _g
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            db = getattr(self, "_people_db", None)
            if db is None:
                return {"success": False, "message": "翻译记录数据库未初始化"}
            # v4.6.61（P1-SET-04）：后端执行门控 —— 不依赖前端置灰：
            # AI 总开关关闭时拒绝「全部翻译」（与设置页该按钮的禁用语义一致）
            if not self._ai_enabled():
                return {"success": False,
                        "message": "AI 翻译总开关已关闭（设置页「启用 AI 翻译」）—— 如需翻译请先开启；"
                                   "池命中 / 繁转简 / 人工修正仍随扫描自动生效"}
            _mode = str(getattr(self, "_scan_mode", "nfo") or "nfo")
            _tr = self._collect_trans_types().get("translate", {})
            _disabled = [str(_t) for _t, _k in self.TX_TYPE_SWITCH.items()
                         if _k and not bool(_tr.get(_k, False))]
            _ex_ep = self._tx_exclude_episodes()
            _pending = db.pending_terms(plugin_id=self.__class__.__name__,
                                        scan_mode=_mode,
                                        limits=self._tx_limits_by_level(),
                                        disabled_types=_disabled,
                                        exclude_episodes=_ex_ep) if db else {"names": [], "roles": []}
            _scope = str((data or {}).get("target_scope") or "both").strip().lower()
            if _scope not in ("person", "role", "both"):
                _scope = "both"
            # 计数期临时生效；若最终未授予许可，必须在返回前复位，避免任务字段泄漏到后续自动翻译（§三十）
            self._tx_target_scope = _scope
            if not _pending["names"] and not _pending["roles"]:
                _items = db.library_items(plugin_id=self.__class__.__name__, scan_mode=_mode) if db else []
                self._tx_target_scope = "both"
                if not _items:
                    return {"success": True, "target_scope": _scope,
                            "message": "库中暂无记录 —— 请先执行「NFO 扫描」采集原文入库后再点「全部翻译」"}
                # 区分「确实全翻完」/「被人数上限挡下」/「被类型开关关闭」（v4.6.55：分开判定，别把关掉的类型算进来）
                try:
                    _all = db.pending_terms(plugin_id=self.__class__.__name__, scan_mode=_mode,
                                            exclude_episodes=_ex_ep) or {}
                    _all_on = db.pending_terms(plugin_id=self.__class__.__name__, scan_mode=_mode,
                                               disabled_types=_disabled,
                                               exclude_episodes=_ex_ep) or {}
                except Exception:
                    _all = {}
                    _all_on = {}

                def _cnt(_d, _k):
                    return len({str(_t).strip() for _t, _pt in (_d.get(_k) or []) if str(_t or "").strip()
                                and not self._skip_no_translate(_t)})

                _on_n, _on_r = _cnt(_all_on, "names"), _cnt(_all_on, "roles")
                if _on_n or _on_r:
                    # 开着类型的词条确实还有未翻的 → 真·被人数上限挡下
                    _lim = self._collect_trans_types().get("limits", {}) or {}
                    return {"success": True, "target_scope": _scope,
                            "message": f"库中还有未翻译词条（人名 {_on_n} / 角色 {_on_r}），但都被「每文件前 N 个」"
                                       f"的人数上限挡下了（当前 演员 {_lim.get('actor', 0)} / 客串 {_lim.get('guest', 0)} / "
                                       f"导演 {_lim.get('director', 0)} / 编剧·制片 {_lim.get('writer', 0)}；0=不限）"
                                       f"—— 请调大人数上限，或点库页「有任务 · 待翻译」看具体是哪些"}
                if _cnt(_all, "names") or _cnt(_all, "roles"):
                    _off = "、".join(str(t) for t in (_disabled or [])) or "（无）"
                    return {"success": True, "target_scope": _scope,
                            "message": f"库中还有未翻译词条，但它们的类型开关是关的（已关：{_off}）"
                                       f"—— 到设置页「翻译范围」把对应类型开关打开后重试"}
                return {"success": True, "target_scope": _scope,
                        "message": "库中已全部翻译完成，无需再处理（去「全部写回」落盘即可）"}
            # 按「目标范围 + 类型开关 + 角色开关」口径统计待翻数（与常驻 worker 收词条同口径）
            _n = len([1 for _t, _pt in (_pending.get("names") or [])
                      if str(_t or "").strip() and self._tx_type_enabled(_pt)
                      and not self._skip_no_translate(_t)])
            # v4.6.48：角色名与第一排共用同一套类型开关（v4.6.59：改用角色版判定，不要求含第一排）
            _r = len([1 for _t, _pt in (_pending.get("roles") or [])
                      if str(_t or "").strip() and self._tx_role_type_enabled(_pt)
                      and not self._skip_no_translate(_t)])
            if _n == 0 and _r == 0:
                # 该范围内无待翻（例如「只翻第二排」但库里只有人名 pending）—— 不改许可，复位后直接返回
                # v4.6.59：label 必须用**本次** _scope —— 此前先复位成 both 再取 label，
                # 导致选了「只翻第二排」却提示「（第一排人名 + 第二排角色）下没有待翻译词条」
                _lbl = {"person": "仅第一排人名", "role": "仅第二排角色",
                        "both": "第一排人名 + 第二排角色"}.get(_scope, "第一排人名 + 第二排角色")
                self._tx_target_scope = "both"
                return {"success": True, "target_scope": _scope, "names_pending": 0, "roles_pending": 0,
                        "message": f"当前翻译目标（{_lbl}）下没有待翻译词条"}
            self._tx_skip_clear = True   # 清会话跳过计数（曾失败的词条借这次机会重试）
            self._tx_request_consume(source="library", scope=_scope)
            _wb_txt = "翻译完成后按「自动写回」设置自动落盘 nfo" if self._wb_writeback_enabled() \
                else "当前未开自动写回：翻译只写库，确认后点「全部写回」落盘 nfo"
            self._push_log("INFO", f"库内翻译已交后台翻译队列（目标 = {self._tx_scope_label()}）："
                                   f"人名 {_n} / 角色 {_r}（常驻 worker 自动消费；{_wb_txt}）")
            return {"success": True, "target_scope": _scope, "names_pending": _n, "roles_pending": _r,
                    "message": f"已交后台翻译（目标 = {self._tx_scope_label()}；人名 {_n} / 角色 {_r}；{_wb_txt}）"}
        except Exception as e:
            logger.error(f"[DB] 库内翻译启动失败: {e}\n{traceback.format_exc()}")
            return {"success": False, "message": str(e)}

    def _api_db_writeback_all(self, data: Optional[dict] = None):
        _g = self._api_gate()
        if _g:
            return _g
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            db = getattr(self, "_people_db", None)
            if db is None:
                return {"success": False, "message": "翻译记录数据库未初始化"}
            items = db.library_items(plugin_id=self.__class__.__name__,
                                     scan_mode=str(getattr(self, "_scan_mode", "nfo") or "nfo"))
            if not items:
                return {"success": False, "message": "库中暂无记录"}
            _err = self._launch_bg(self._writeback_all_worker, {}, task="writeback")
            if _err:
                return _err
            self._push_log("INFO", f"全部写回已启动：将把库中 {len(items)} 个条目的已翻译名单批量写回 nfo 文件（不重新翻译）")
            return {"success": True, "message": f"全部写回已启动（{len(items)} 个条目，后台执行）"}
        except Exception as e:
            logger.error(f"[DB] 全部写回启动失败: {e}\n{traceback.format_exc()}")
            return {"success": False, "message": str(e)}

    def _writeback_all_worker(self, data: Optional[dict] = None):
        """遍历库中全部条目，逐条把已翻译名单写回 nfo 文件（复用单条写回逻辑）。"""
        try:
            _pid = self.__class__.__name__
            db = getattr(self, "_people_db", None)
            items = db.library_items(plugin_id=_pid) if db else []
            done = changed_total = failed = skipped = skipped_na = skipped_missing = 0
            # UI-004 同类修复：「全部写回」是写回任务，进度写入独立 _writeback_status，
            # 不再借用 _scan_status（否则会覆盖正在进行的扫描进度显示）
            self._writeback_status["running"] = True
            self._writeback_status["phase"] = "writeback_all"
            self._writeback_status["current"] = "全部写回 nfo 中..."
            self._writeback_status["total"] = len(items)
            self._writeback_status["done"] = 0
            for i, it in enumerate(items):
                if getattr(self, "_wb_stop", False):
                    break
                self._writeback_status["done"] = i + 1
                try:
                    _iid = str(it.get("item_id") or "")
                    _sid = str(it.get("server_id") or "")
                    r = self._restore_item_to_nfo(_iid, _sid)
                    d = r.get("data") or {}
                    # v4.6.63：「全部写回」同样同步 writeback_state —— 否则「待写回」徽章会一直挂着
                    try:
                        _wdb = self._wb_db()
                        if r.get("success") and not d.get("missing"):
                            _wdb.set_status(plugin_id=_pid, server_id=_sid, item_id=_iid,
                                            status="done", error="",
                                            changed_count=int(d.get("changed") or 0),
                                            file_sig=self._wb_item_fp(_iid, _sid))
                        elif d.get("missing"):
                            _wdb.set_status(plugin_id=_pid, server_id=_sid, item_id=_iid,
                                            status="missing", error=str(r.get("message") or "")[:200],
                                            file_sig=self._wb_item_fp(_iid, _sid))
                    except Exception:
                        pass
                    if r.get("success"):
                        done += 1
                        changed_total += int(d.get("changed") or 0)
                    elif d.get("skip"):
                        skipped_na += 1
                    elif d.get("missing"):
                        skipped_missing += 1
                    elif "无已翻译名单" in str(r.get("message") or ""):
                        skipped += 1
                    else:
                        failed += 1
                except Exception as _e:
                    failed += 1
                    logger.warning(f"[DB] 全部写回条目失败 {it.get('item_id')}: {_e}")
            _miss_txt = f"，文件已不存在跳过 {skipped_missing}（删除/观察期）" if skipped_missing else ""
            self._push_log("INFO", f"全部写回完成：写回 {done} 个条目，改动 {changed_total} 条（无译文跳过 {skipped}，无 nfo 记录跳过 {skipped_na}{_miss_txt}，失败 {failed}）")
            _emby_sync_line = ""
            if not bool(getattr(self, "_nfo_preview", False)):
                _esr = self._pool_sync_all(ctx="全部写回") if getattr(self, "_emby_name_sync", True) else {}
                if _esr and _esr.get("total"):
                    _emby_sync_line = (f"🔄 Emby 人名：改名 {_esr.get('renamed', 0)} · "
                                       f"已是译文 {_esr.get('skipped', 0)} · 未找到/失败 {_esr.get('failed', 0)}")
            if getattr(self, "_notify_on_complete", False):
                try:
                    _backup_txt = ".bak 已开启" if bool(getattr(self, "_nfo_backup", False)) else ".bak 未开启"
                    _lock_txt = "Cast 已锁定" if bool(getattr(self, "_lock_cast", False)) else "Cast 未锁定（设置未开启）"
                    _lines = [
                        f"📄 写回文件：{done} 个条目　🎬 改动：{changed_total} 条",
                        f"⏭️ 跳过：{skipped + skipped_na + skipped_missing}"
                        f"{f'（其中文件已不存在 {skipped_missing} 个：删除/观察期）' if skipped_missing else ''}"
                        f"　❌ 失败：{failed}　💾 备份：{_backup_txt}",
                        f"🔐 锁定：{_lock_txt}",
                        "不重新翻译 · 使用库中已翻译名单落盘",
                    ]
                    if _emby_sync_line:
                        _lines.append(_emby_sync_line)
                    self.post_message(
                        mtype=NotificationType.Manual,
                        title="✅ 全部写回完成",
                        text="\n".join(_lines),
                    )
                except Exception as _e:
                    logger.debug(f"[DB] 全部写回完成通知发送失败（非致命）: {_e}")
        except Exception as e:
            logger.error(f"[DB] 全部写回失败: {e}\n{traceback.format_exc()}")
            self._push_log("ERROR", f"全部写回失败：{e}")
        finally:
            self._set_task_running("writeback", False)
            self._writeback_status["running"] = False
            self._writeback_status["current"] = ""
            self._writeback_status["total"] = 0
            self._writeback_status["done"] = 0
            try:
                self._save_state()
            except Exception:
                pass

    def _api_translate_retry_failed(self, data: Optional[dict] = None):
        _g = self._api_gate()
        if _g:
            return _g
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            terms = sorted(set(str(x).strip() for x in (getattr(self, "_failed_terms", None) or ()) if str(x).strip()))
            if not terms:
                return {"success": True, "message": "失败清单为空，无需重试"}
            if not self._ai_enabled():
                return {"success": False, "message": "AI 翻译已关闭，无法重试"}
            if self._llm is None:
                self._init_llm()
            if self._llm is None:
                return {"success": False, "message": "LLM 未配置（请在设置页配置，或点「测试连接」排查）"}
            self._tx_skip_clear = True
            # 词条级许可：只重试这些失败词条（worker 收到 terms 后不扫全库，避免「重试失败」顺带翻全库）
            self._tx_request_consume(source="library", terms=terms)
            self._push_log("INFO", f"失败词条重试已交后台翻译队列：{len(terms)} 个（成功后自动移出清单）")
            return {"success": True, "message": f"已交后台重试（{len(terms)} 个失败词条，成功后自动移出清单）"}
        except Exception as e:
            logger.error(f"[DB] 失败词条重试启动失败: {e}\n{traceback.format_exc()}")
            return {"success": False, "message": str(e)}

    def _api_translate_clear_failed(self, data: Optional[dict] = None):
        _g = self._api_gate()
        if _g:
            return _g
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            n = len(getattr(self, "_failed_terms", None) or ())
            self._failed_terms = set()
            self._failed_terms_detail = {}
            self._save_state()
            self._push_log("INFO", f"已清空翻译失败清单（{n} 个词条）")
            return {"success": True, "message": f"已清空失败清单（{n} 个词条）"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_db_delete(self, data: Optional[dict] = None):
        _g = self._api_gate()
        if _g:
            return _g
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            data = data or {}
            item_id = str(data.get("item_id") or "").strip()
            server_id = str(data.get("server_id") or "")
            if not item_id:
                return {"success": False, "message": "缺少 item_id"}
            db = getattr(self, "_people_db", None)
            if db is None:
                return {"success": False, "message": "翻译记录数据库未初始化"}
            n = db.delete_item(plugin_id=self.__class__.__name__, item_id=item_id, server_id=server_id)
            self._db_items_cache = None
            return {"success": True, "message": f"已删除 {n} 条记录", "data": {"deleted": n}}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_db_clear(self):
        _g = self._api_gate()
        if _g:
            return _g
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            db = getattr(self, "_people_db", None)
            if db is None:
                return {"success": False, "message": "翻译记录数据库未初始化"}
            n = db.clear_all(plugin_id=self.__class__.__name__)
            # 写回队列一并清空（记录已删，残留候选只会空转；避免「待写回」数字虚高）
            _wn = 0
            try:
                _wn = self._wb_db().clear_all(plugin_id=self.__class__.__name__)
            except Exception:
                _wn = 0
            self._pool_hits = 0
            self._llm_terms = 0
            _sig_n = 0
            try:
                _sig_n = len(getattr(self, "_nfo_file_sigs", None) or {})
                self._nfo_file_sigs = {}
                self._save_file_sigs()
            except Exception:
                _sig_n = 0
            # v4.6.110（LIB-019）：**扫描断点一并清空** —— 否则「清空翻译记录」之后
            # 仪表盘仍显示「续跑」可用：`_nfo_resume_state()` 只看断点（_scan_cursor.nfo.done）,
            # 记录/译文都删了，续跑只会跳过全部已处理文件、空转（用户实测：扫到一半暂停 →
            # 清库 → 仪表盘还提示续跑）。清掉后「续跑」自动灰置，下次扫描按全量重来（符合预期）。
            _cur_n = 0
            try:
                _cur = getattr(self, "_scan_cursor", None)
                if isinstance(_cur, dict):
                    _cur_n = len((_cur.get("nfo") or {}).get("done") or {})
                    _cur.pop("nfo", None)
                    self._scan_cursor = _cur
            except Exception:
                _cur_n = 0
            self._db_items_cache = None
            try:
                self._save_state()
            except Exception:
                pass
            self._push_log("INFO", f"已清空翻译记录：{n} 条（写回队列 {_wn} 条、文件签名 {_sig_n} 条、"
                                   f"扫描断点 {_cur_n} 条已一并清空）—— 人名池保留（含人工修正，未受影响），"
                                   f"下次扫描将按全量重来并用池内译文快速重建记录")
            return {"success": True,
                    "message": f"已清空翻译记录（{n} 条；断点已清，「续跑」不再可用；人名池未受影响，含人工修正保留）",
                    "data": {"cleared": n, "writeback_cleared": _wn, "cursor_cleared": _cur_n}}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_db_clear_other(self):
        _g = self._api_gate()
        if _g:
            return _g
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            db = getattr(self, "_people_db", None)
            if db is None:
                return {"success": False, "message": "翻译记录数据库未初始化"}
            mode = str(getattr(self, "_scan_mode", "nfo") or "nfo")
            # 删除的是「异模式」记录：当前 NFO 模式 → 删 API（nfo_only=False）；当前 API 模式 → 删 NFO（nfo_only=True）
            target_nfo_only = mode != "nfo"
            label = "NFO 本地记录" if target_nfo_only else "API 在线记录"
            n = db.clear_by_source(plugin_id=self.__class__.__name__, nfo_only=target_nfo_only)
            self._db_items_cache = None
            self._push_log("INFO", f"已清空异模式数据（{label}，{n} 条）")
            return {"success": True, "message": f"已清空{label} {n} 条", "data": {"cleared": n}}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_db_export(self):
        try:
            db = getattr(self, "_people_db", None)
            if db is None:
                return {"success": False, "message": "翻译记录数据库未初始化"}
            rows = db.export_all(plugin_id=self.__class__.__name__)
            return {"success": True, "data": rows, "count": len(rows)}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_db_import(self, data: Optional[dict] = None):
        _g = self._api_gate()
        if _g:
            return _g
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            data = data or {}
            rows = data.get("rows") or data.get("records") or []
            if isinstance(rows, dict):
                rows = rows.get("records") or rows.get("rows") or []
            if not rows:
                return {"success": False, "message": "没有可导入的数据"}
            db = getattr(self, "_people_db", None)
            if db is None:
                return {"success": False, "message": "翻译记录数据库未初始化"}
            n = db.import_rows(plugin_id=self.__class__.__name__, rows=rows)
            self._db_items_cache = None
            self._push_log("INFO", f"已导入翻译记录 {n} 条")
            return {"success": True, "message": f"已导入 {n} 条记录", "data": {"imported": n}}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_db_rescan_item(self, data: Optional[dict] = None):
        """重新拉取（重扫这一条）—— 只重采集当前这一个条目，按本地 NFO 更新入库：
        - 范围 = 该条目 nfo 文件（剧：tvshow.nfo + 其下全部单集 nfo；电影/单集：单文件），
          与「重新翻译」同口径；不动全库、不触发仪表盘整库扫描。
        - 只重采集名单（刷新原文/层级/标题/数量），不翻译：新出现的原文留在库中由常驻翻译 worker 处理。
        - 保留已有译文：把库中该条目现存的 name_after/role_after 作为映射回填，
          避免重采集把已翻好的中文冲掉（原文本身有变则视为新词条）。
        """
        _g = self._api_gate()
        if _g:
            return _g
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            data = data or {}
            item_id = str(data.get("item_id") or "").strip()
            server_id = str(data.get("server_id") or "").strip()
            if not item_id:
                return {"success": False, "message": "缺少 item_id"}
            db = getattr(self, "_people_db", None)
            if db is None:
                return {"success": False, "message": "翻译记录数据库未初始化"}
            _pid = self.__class__.__name__
            meta = db.item_meta(plugin_id=_pid, item_id=item_id, server_id=server_id) or {}
            people = db.people_of_item(plugin_id=_pid, item_id=item_id, server_id=server_id)
            nfo_path = str(meta.get("nfo_path") or "").strip()
            if (not nfo_path) or not os.path.isfile(nfo_path):
                return {"success": False,
                        "message": "该条目 nfo 文件不存在（可能已删除，或为纯 API 条目，无法从本地重扫）"}
            from . import nfo as nfo_engine
            _title = str(meta.get("title") or meta.get("series_name") or "").strip()
            _disp = f"《{_title}》({item_id})" if _title else item_id
            lv = nfo_engine.classify(nfo_path)
            if lv == "tvshow":
                files = nfo_engine.find_nfo_files([os.path.dirname(nfo_path)], recursive=True,
                                                  include_episodes=True)
            else:
                files = [nfo_path]  # 电影/单集：单文件
            if not files:
                return {"success": False, "message": "未找到可重新拉取的 nfo 文件"}
            # 保留该条目已有译文（原文→译文），重采集时回填，避免冲掉已翻好的中文
            person_map, role_map = {}, {}
            for p in (people or []):
                _nb = str(p.get("name_before") or "").strip()
                _na = str(p.get("name_after") or "").strip()
                if _nb and _na and _na != _nb:
                    person_map[_nb] = _na
                _rb = str(p.get("role_before") or "").strip()
                _ra = str(p.get("role_after") or "").strip()
                if _rb and _ra and _ra != _rb:
                    role_map[_rb] = _ra
            _rows = 0
            _files_ok = 0
            _files_bad = 0
            for fp in files:
                try:
                    doc = nfo_engine.parse_nfo(fp)
                    if doc is None or getattr(doc, "unsupported", False):
                        _files_bad += 1
                        continue
                    if nfo_engine.classify(fp) == "episode":
                        _sid, _sname, _ssn, _epn = self._nfo_episode_meta(fp)
                    else:
                        _sid = _sname = ""
                        _ssn = _epn = None
                    _rows += self._record_nfo_library(doc, person_map, role_map,
                                                      series_id=_sid, series_name=_sname,
                                                      season_num=_ssn, episode_num=_epn,
                                                      pool_ingest=True)
                    _files_ok += 1
                except Exception as e:
                    _files_bad += 1
                    logger.warning(f"[DB] 重新拉取单文件失败 {fp}: {e}")
            self._db_items_cache = None
            _bad_txt = f"，失败 {_files_bad} 个" if _files_bad else ""
            self._push_log("INFO", f"重新拉取完成（重扫这一条）：{_disp} —— 重扫 {_files_ok} 个 NFO / 更新 {_rows} 条"
                                   f"{_bad_txt}（只重采集名单，不翻译；新词条由翻译 worker 处理）")
            return {"success": True,
                    "message": f"已重新拉取 {_disp}：重扫 {_files_ok} 个 NFO，更新 {_rows} 条{_bad_txt}"
                               f"（只重采集名单，不翻译）",
                    "data": {"files": _files_ok, "failed": _files_bad, "rows": _rows}}
        except Exception as e:
            logger.error(f"[DB] 重新拉取失败: {e}\n{traceback.format_exc()}")
            return {"success": False, "message": str(e)}

    def _api_db_retranslate(self, data: Optional[dict] = None):
        """重新翻译 —— worker 化：
        - 后台执行（与 NFO 扫描/库内翻译共用 _is_running 锁，仪表盘「运行操作」同步显示+锁定）
        - 范围 = 该条目 nfo 文件（剧：tvshow.nfo + 其下全部单集 nfo，尊重排除目录；
          电影/单集：单文件）—— 修复此前只翻剧文件、客串（在集文件里）翻不到的缺陷
        - 预览模式开 → 只写库不写文件；关 → 写文件+库（与库内「全部翻译」语义一致）"""
        _g = self._api_gate()
        if _g:
            return _g
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            data = data or {}
            item_id = str(data.get("item_id") or "").strip()
            server_id = str(data.get("server_id") or "").strip()
            _scope = str(data.get("target_scope") or "both").strip().lower()
            if _scope not in ("person", "role", "both"):
                _scope = "both"
            _scope_lbl = {"person": "仅第一排人名", "role": "仅第二排角色",
                          "both": "第一排人名 + 第二排角色"}.get(_scope, _scope)
            if not item_id:
                return {"success": False, "message": "缺少 item_id"}
            db = getattr(self, "_people_db", None)
            if db is None:
                return {"success": False, "message": "翻译记录数据库未初始化"}
            _pid = self.__class__.__name__
            meta = db.item_meta(plugin_id=_pid, item_id=item_id, server_id=server_id) or {}
            people = db.people_of_item(plugin_id=_pid, item_id=item_id, server_id=server_id)
            if not people:
                return {"success": False, "message": "库中该条目无人物记录"}
            if not self._ai_enabled():
                return {"success": False, "message": "AI 翻译已关闭，无法重新翻译"}
            if self._llm is None:
                self._init_llm()
            if self._llm is None:
                return {"success": False, "message": "LLM 未配置（请在设置页配置，或点「测试连接」排查）"}
            from . import nfo as nfo_engine

            _title = str(meta.get("title") or meta.get("series_name") or "").strip()
            _disp = f"《{_title}》({item_id})" if _title else item_id

            nfo_path = str(meta.get("nfo_path") or "").strip()
            if (not nfo_path) or not os.path.isfile(nfo_path):
                return {"success": False,
                        "message": "该条目 nfo 文件不存在（可能已删除或正在洗版观察期，恢复后重试）"}
            lv = nfo_engine.classify(nfo_path)
            files = []
            if lv == "tvshow":
                files = nfo_engine.find_nfo_files([os.path.dirname(nfo_path)], recursive=True,
                                                  include_episodes=True)
            else:
                files = [nfo_path]  # 电影/单集：单文件
            if not files:
                return {"success": False, "message": "未找到可重新翻译的 nfo 文件"}
            # 按「翻译范围 + 类型开关 + 人数上限」口径取应重翻的词条（i2/v4.6.48）——
            # 与「全部翻译」同一套约束；此前重翻无视这些约束，会把该条目全部人名/角色都翻一遍。
            _tr = self._collect_trans_types().get("translate", {})
            _take_person = self._tx_scope_allows("person", _scope) and bool(_tr.get("person", True))
            _take_role = self._tx_scope_allows("role", _scope) and bool(_tr.get("role", True))
            _terms = db.force_item_terms(plugin_id=_pid, item_id=item_id, server_id=server_id,
                                         limits=self._tx_limits_by_level(),
                                         exclude_episodes=self._tx_exclude_episodes()) or {"names": [], "roles": []}
            if _take_person:
                _names = sorted({(str(t).strip(), str(pt or "Actor").strip() or "Actor")
                                 for t, pt in (_terms.get("names") or [])
                                 if str(t or "").strip() and self._tx_type_enabled(pt, _scope)})
            else:
                _names = []
            # v4.6.48：角色名与第一排共用同一套「类型开关 + 人数上限」（v4.6.59：角色版判定）
            _roles = sorted({(str(t).strip(), str(pt or "Actor").strip() or "Actor")
                             for t, pt in (_terms.get("roles") or [])
                             if str(t or "").strip() and self._tx_role_type_enabled(pt, _scope)}) if _take_role else []
            if not _names and not _roles:
                return {"success": True, "target_scope": _scope, "names_pending": 0, "roles_pending": 0,
                        "message": f"该条目在「{_scope_lbl}」下没有可重翻的词条"
                                   f"（可能对应类型开关关闭 / 人数上限为 0，或本就是空记录）"}
            _jobs = getattr(self, "_tx_force_jobs", None)
            if _jobs is None:
                _jobs = {}
                self._tx_force_jobs = _jobs
            _jobs[item_id] = {"server_id": server_id, "title": _title,
                              "year": str(meta.get("year") or ""),
                              "names": [list(x) for x in _names], "roles": [list(x) for x in _roles],
                              "ts": time.time()}
            # 条目级许可：只重翻这一条（worker 收到 items 后不再扫全库，i1）+ 本次范围
            # v4.6.61（P1-6）：payload 落 SQLite —— 插件重启后自动恢复入队，不再「重启即丢」
            try:
                _pl = json.dumps({item_id: _jobs[item_id]}, ensure_ascii=False)
            except Exception:
                _pl = ""
            self._tx_request_consume(source="library", items=[item_id], scope=_scope, payload=_pl)
            # v4.6.64（第 24 节）：登记本次重翻的 occurrences（term_id = occ_id，含季/集/序号）
            try:
                _fraw = db.force_item_occurrences(plugin_id=_pid, item_id=item_id, server_id=server_id,
                                                  limits=self._tx_limits_by_level(), only_pending=False,
                                                  exclude_episodes=self._tx_exclude_episodes()) or {}
                _orows = []
                for _kk, _kkey in (("person", "names"), ("role", "roles")):
                    for r in (_fraw.get(_kkey) or []):
                        _oo = {"kind": _kk, "text": str(r.get("term") or ""),
                               "item_id": str(r.get("item_id") or item_id),
                               "server_id": str(r.get("server_id") or server_id),
                               "season_num": r.get("season_num"), "episode_num": r.get("episode_num"),
                               "person_index": int(r.get("person_index") or 0)}
                        _orows.append({"term_id": self._tx_occ_id(_oo),
                                       "original_text": _oo["text"], "item_id": _oo["item_id"],
                                       "server_id": _oo["server_id"], "season_num": _oo["season_num"],
                                       "episode_num": _oo["episode_num"],
                                       "person_index": _oo["person_index"], "kind": _kk,
                                       "person_type": str(r.get("type") or "Actor")})
                self._tx_register_job_terms(_orows)
            except Exception:
                pass
            _wb_txt = "重翻完成后按「自动写回」设置自动落盘" if self._wb_writeback_enabled() \
                else "当前未开自动写回：重翻只写库，确认后点「全部写回」落盘"
            self._push_log("INFO", f"重新翻译已入队：{_disp}（范围 = {_scope_lbl}；"
                                   f"人名 {len(_names)} / 角色 {len(_roles)}）"
                                   f"—— 由常驻翻译 worker 统一重翻（不删旧译文，翻好即覆盖）；{_wb_txt}")
            return {"success": True, "target_scope": _scope,
                    "names_pending": len(_names), "roles_pending": len(_roles),
                    "message": f"已交后台重新翻译（范围 = {_scope_lbl}；人名 {len(_names)} / 角色 {len(_roles)}；{_wb_txt}）"}
        except Exception as e:
            logger.error(f"[DB] 重新翻译启动失败: {e}\n{traceback.format_exc()}")
            return {"success": False, "message": str(e)}


    def _api_db_update_person(self, data: Optional[dict] = None):
        _g = self._api_gate()
        if _g:
            return _g
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            data = data or {}
            item_id = str(data.get("item_id") or "").strip()
            name_before = str(data.get("name_before") or "").strip()
            if not item_id:
                return {"success": False, "message": "缺少 item_id"}
            if not name_before:
                return {"success": False, "message": "缺少 name_before（原文名）"}
            server_id = str(data.get("server_id") or "")
            name_after = str(data.get("name_after") or "").strip()
            role_before = str(data.get("role_before") or "").strip()
            role_after = str(data.get("role_after") or "").strip()
            _raw_variants = data.get("name_befores") or []
            if isinstance(_raw_variants, str):
                _raw_variants = [x.strip() for x in _raw_variants.replace("，", ",").split(",")]
            _variants = [str(x).strip() for x in _raw_variants if str(x or "").strip()]
            if name_before not in _variants:
                _variants.insert(0, name_before)
            _vset = set(_variants)
            db = getattr(self, "_people_db", None)
            if db is None:
                return {"success": False, "message": "翻译记录数据库未初始化"}
            _pid = self.__class__.__name__
            rows = db.people_of_item(plugin_id=_pid, item_id=item_id, server_id=server_id)
            matched = [p for p in rows if (p.get("name_before") or "").strip() in _vset]
            if not matched:
                return {"success": False, "message": f"库中无「{name_before}」的记录"}
            _role_keys = set()
            if role_after:
                _role_rows = [p for p in matched
                              if role_before and (str(p.get("role_before") or "").strip() == role_before)]
                if not _role_rows:
                    # 前端给了 role_before 但没有匹配行 → 明确报错而不是假报成功
                    return {"success": False,
                            "message": f"库中无「{name_before}」饰「{role_before}」的角色记录（刷新后重试或直接改人名）"}
                _role_keys = {(p.get("season_num"), p.get("episode_num"), p.get("index"))
                              for p in _role_rows}
            targets = matched
            updated = 0
            role_updated = 0
            for p in targets:
                rb = str(p.get("role_before") or "").strip()
                _is_role_hit = (p.get("season_num"), p.get("episode_num"), p.get("index")) in _role_keys
                n = db.update_person(plugin_id=_pid, item_id=item_id, server_id=server_id,
                                     season_num=p.get("season_num"), episode_num=p.get("episode_num"),
                                     index=p.get("index"), name_after=name_after or name_before,
                                     role_after=(role_after if _is_role_hit else (p.get("role_after") or "")))
                if n > 0:
                    updated += 1
                    if _is_role_hit and role_after != rb:
                        role_updated += 1
            # 人工修正同步写入人名池缓存（manual 最高优先级，重跑扫描不会被 AI 覆盖）
            dbm = getattr(self, "_name_map_db", None) or NameMapDb()
            if name_after:
                for _v in _variants:
                    if _v and name_after != _v:
                        try:
                            dbm.upsert_manual(plugin_id=_pid, name_type="person", original=_v, zh=name_after)
                        except Exception:
                            pass
            if role_after and role_before and role_after != role_before:
                dbm.upsert_manual(plugin_id=_pid, name_type="role", original=role_before, zh=role_after)
            self._push_log("INFO", f"人工修正译文: {name_before} → {name_after or '（清理）'}（{updated} 处）")
            return {"success": True, "message": f"已更新 {updated} 处记录（重跑扫描不会被 AI 覆盖）",
                    "data": {"updated": updated, "role_updated": role_updated}}
        except Exception as e:
            logger.error(f"[DB] 更新人物失败: {e}\n{traceback.format_exc()}")
            return {"success": False, "message": str(e)}

    def _first_emby_client(self):
        """取第一个可用 Emby 服务器的客户端（兼容入口：仅限「无 server_id 的历史数据」场景）。
        业务层新代码请用 _emby_client_for_server(server_id)（server_id 感知）。
        legacy: 本方法为「第一台服务器」旧路径，当前已无任何调用者。
        新流程一律走 _emby_client_for_server(server_id) / _pool_sync_all，禁止再依赖第一台。"""
        try:
            for svc in (self._get_all_emby_services() or []):
                url = self._get_service_url(svc)
                key = self._get_service_api_key(svc)
                if url and key:
                    return EmbyClient(url, key, svc, user_id=self._get_service_user_id(svc),
                                      use_proxy=self._use_proxy)
        except Exception as e:
            logger.warning(f"[Emby] 取客户端失败: {e}")
        return None

    def _emby_client_for_server(self, server_id: str = "", allow_legacy_fallback: bool = True):
        """按 server_id 取对应 Emby 客户端（Person 改名唯一路由入口）。
        :return: (client, error) —— 二者必有一空。
        - server_id 命中 → (client, "")
        - 明确给了 server_id 却匹配不到 → (None, 明确错误)：禁止静默 fallback 第一台（多服务器改名正确性）
        - server_id 为空（legacy/no-server-id 历史数据）→ 显式记日志后兼容取第一台（allow_legacy_fallback=False 则报错）
        """
        _skey = str(server_id or "").strip()
        _clients = self._emby_clients()
        if not _clients:
            return None, "Emby 未配置或不可用"
        if _skey:
            if _skey in _clients:
                return _clients[_skey], ""
            self._warn_once(f"emby:server-missing:{_skey}",
                            f"[Emby] 找不到 server_id={_skey} 对应的 Emby 服务 —— 已跳过，避免改名到错误的服务器")
            return None, f"找不到 server_id={_skey} 对应的 Emby 服务（已跳过，避免改名到错误服务器）"
        if not allow_legacy_fallback:
            return None, "记录缺少 server_id（无服务器信息，无法确定同步目标）"
        self._warn_once("emby:legacy-no-server-id",
                        "[Emby] legacy/no-server-id 记录：按第一台 Emby 兼容同步（多服务器环境下建议补齐 server_id）")
        return next(iter(_clients.values())), ""

    def _sync_emby_person_name(self, name_before: str, name_after: str,
                               client: Optional[Any] = None, server_id: str = "") -> dict:
        """把一个人名译文同步到 Emby（重命名 Person 实体）。返回 {ok, reason, skipped?}
        client 未显式给出时按 server_id 取（找不到目标服务器 → 明确失败，不 fallback 第一台）。
        无 ID / ID 失效时的名字兜底统一走 _resolve_rename_by_name（文档 §十 §二十五：
        同名候选唯一才改名；多候选中「同一人的重复实体」才批量改名；真同名 → 失败不猜）。"""
        nb = str(name_before or "").strip()
        na = str(name_after or "").strip()
        if not nb or not na or nb == na:
            return {"ok": False, "reason": "无需同步（译文与原文相同）"}
        if client is None:
            _cli, _err = self._emby_client_for_server(server_id)
            if _cli is None:
                return {"ok": False, "reason": _err}
            client = _cli
        return self._resolve_rename_by_name(client, name_original=nb, target=na, tag="Emby")

    def _emby_sync_manual_rename(self, name_before: str, name_after: str,
                                 server_id: str = "") -> dict:
        """库页人工改人名 → 同步 Emby（严格 server_id + Person ID 优先）。
        优先级（文档 §七 A）：emby_person_id → server_id → legacy 名字兜底。
        - 先在人名池按 name_original 定位身份行：命中则按各自 server_id 精确改名
          （ID 优先，多服务器各改各的，绝不静默改到第一台）；
        - 池内未命中再按 server_id 路由做名字兜底（server_id 为空只作 legacy 兼容并记日志）。
        返回 _sync_emby_person_name 同构结果 {ok, reason, skipped?}。
        """
        nb = str(name_before or "").strip()
        na = str(name_after or "").strip()
        if not nb or not na or nb == na:
            return {"ok": False, "reason": "无需同步（译文与原文相同）"}
        _dbm = getattr(self, "_name_map_db", None) or NameMapDb()
        _pid = self.__class__.__name__
        try:
            _rows = _dbm.find_pool_persons_by_name(plugin_id=_pid, name_original=nb,
                                                   server_id=server_id) or []
        except Exception:
            _rows = []
        if _rows:
            _ok = False
            _reasons: List[str] = []
            for _r in _rows:
                _skey = str(_r.get("server_id") or "")
                _rid = str(_r.get("emby_person_id") or "").strip()
                cli, _cerr = self._emby_client_for_server(_skey)
                if cli is None:
                    _reasons.append(f"{_skey or '默认'}:{_cerr or 'Emby 不可用'}")
                    try:
                        _dbm.update_pool_status(plugin_id=_pid, server_id=_skey, emby_person_id=_rid,
                                                name_original=nb, sync_status="failed",
                                                sync_error=str(_cerr or ""))
                    except Exception:
                        pass
                    continue
                _sr = self._pool_sync_one_row(cli, person_id=_rid, name_original=nb, name_zh=na,
                                              name_current=str(_r.get("name_current") or ""))
                if _sr.get("ok"):
                    _ok = True
                    _reasons.append(f"{_skey or '默认'}:{_sr.get('reason')}")
                    _resp_id = str(_sr.get("person_id") or "").strip()
                    if not _rid and _resp_id:
                        try:
                            _dbm.bind_pool_person_id(plugin_id=_pid, server_id=_skey,
                                                     name_original=nb, emby_person_id=_resp_id)
                            _rid = _resp_id
                        except Exception:
                            pass
                    try:
                        _dbm.update_pool_status(
                            plugin_id=_pid, server_id=_skey, emby_person_id=_rid, name_original=nb,
                            translation_status="translated", sync_status="synced", sync_error="",
                            last_sync_at=datetime.now().isoformat(timespec="seconds"), name_current=na)
                    except Exception:
                        pass
                else:
                    _reasons.append(f"{_skey or '默认'}:{_sr.get('reason')}")
                    try:
                        _dbm.update_pool_status(plugin_id=_pid, server_id=_skey, emby_person_id=_rid,
                                                name_original=nb, sync_status="failed",
                                                sync_error=str(_sr.get("reason") or ""))
                    except Exception:
                        pass
            if _ok:
                return {"ok": True, "reason": "；".join(_reasons) or "已同步"}
            return {"ok": False, "reason": "；".join(_reasons) or "池内 Person 同步失败"}
        # 池内未命中 → 按 server_id 路由做名字兜底（server_id 为空=legacy，路由会显式记日志）
        return self._sync_emby_person_name(nb, na, server_id=server_id)

    def _run_emby_name_sync(self, pairs: dict, ctx: str = "", server_id: str = "") -> dict:
        """执行一批人名同步（pairs: {原文名: 译文}）—— 只对"确实需要改"的发请求，
        Emby 那边已经是译文的直接跳过（不发）。
        按 server_id 路由（server_id 为空=legacy/no-server-id → 兼容第一台并记日志；
        明确给了却匹配不到 → 整批失败并给出原因，绝不改名到错误服务器）。
        legacy: name-only 批量改名执行器，保留给 _api_sync_emby_names（旧入口）。
        新流程不再调用；收尾同步改由 _pool_sync_all（池内 Person ID 优先）完成。"""
        if not pairs:
            return {"renamed": 0, "skipped": 0, "failed": 0, "total": 0, "fails": []}
        cli, _err = self._emby_client_for_server(server_id)
        if cli is None:
            return {"renamed": 0, "skipped": 0, "failed": 0, "total": len(pairs),
                    "fails": [_err or "Emby 未配置或不可用"]}
        renamed = skipped = failed = 0
        fails: List[str] = []
        for nb, na in pairs.items():
            res = self._sync_emby_person_name(nb, na, client=cli)
            if res.get("ok"):
                skipped += 1 if res.get("skipped") else 0
                renamed += 0 if res.get("skipped") else 1
            else:
                failed += 1
                if len(fails) < 8:
                    fails.append(f"{nb} → {na}（{res.get('reason')}）")
        _msg = (f"改名 {renamed} 个 · 已是译文跳过 {skipped} 个 · 未找到/失败 {failed} 个"
                f"（本批 {len(pairs)} 个译名{('，' + ctx) if ctx else ''}）")
        self._push_log("INFO", f"🔄 Emby 人名同步：{_msg}")
        for _f in fails:
            self._push_log("WARNING", f"⚠️ Emby 人名同步失败：{_f}")
        return {"renamed": renamed, "skipped": skipped, "failed": failed,
                "total": len(pairs), "fails": fails, "message": _msg}

    def _mark_emby_name_dirty(self, pairs_or_names) -> None:
        """记录本批需要同步到 Emby 的人名（收尾一次性同步，不逐集发请求）
        legacy: 本批脏名字集合仅供 _flush_emby_name_sync 消费；因收尾同步已改走
        _pool_sync_all（以池内事实为准，不再依赖待发集合），该集合当前无任何消费者，保留仅为兼容。"""
        try:
            s = getattr(self, "_emby_sync_pending", None)
            if s is None:
                s = set()
                self._emby_sync_pending = s
            if isinstance(pairs_or_names, dict):
                for k in pairs_or_names.keys():
                    _k = str(k or "").strip()
                    if _k:
                        s.add(_k)
            else:
                for n in (pairs_or_names or []):
                    _n = str(n or "").strip()
                    if _n:
                        s.add(_n)
        except Exception:
            pass

    def _flush_emby_name_sync(self, full: bool = False, ctx: str = "") -> dict:
        """收尾同步 Emby 人名。
        full=True → 全量对齐（库里所有已译人名 vs Emby；用于全库扫描 / 全部写回）；
        full=False → 只同步本批脏名字（增量：Webhook 单集 / 单条重新翻译）。
        legacy: name-only 收尾路径，当前已无任何调用者（全库扫描 / 全部写回 /
        探测库三处收尾均改走 _pool_sync_all）。保留仅为兼容，新代码禁止调用。"""
        if not getattr(self, "_emby_name_sync", True):
            return {}
        try:
            db = getattr(self, "_people_db", None)
            if db is None:
                return {}
            _pid = self.__class__.__name__
            pairs: Dict[str, str] = {}
            if full:
                # 全量对齐已覆盖本批全部人名 → 清空增量待发集合（避免下次增量重复查一遍）
                self._emby_sync_pending = set()
                for r in (db.distinct_name_pairs(plugin_id=_pid) or []):
                    pairs[r["name_before"]] = r["name_after"]
            else:
                pending = set(getattr(self, "_emby_sync_pending", None) or [])
                self._emby_sync_pending = set()
                if not pending:
                    return {}
                for r in (db.pairs_for_names(plugin_id=_pid, names=sorted(pending)) or []):
                    pairs[r["name_before"]] = r["name_after"]
            if not pairs:
                return {}
            return self._run_emby_name_sync(pairs, ctx=ctx)
        except Exception as e:
            logger.warning(f"[Emby] 收尾人名同步失败: {e}")
            return {}

    def _api_sync_emby_names(self, data: Optional[dict] = None):
        """批量把所有已翻译人名（库 + 人名池）同步到 Emby Person 实体。
        设置页「同步人名到 Emby」按钮调用（全量对齐）。
        legacy: name-only 批量改名旧 API（/db/sync_emby_names），前端入口已删。
        保留仅为兼容历史调用；新流程请走 /pool/sync（server_id + Person ID 感知）。"""
        _g = self._api_gate()
        if _g:
            return _g
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            db = getattr(self, "_people_db", None)
            if db is None:
                return {"success": False, "message": "翻译记录数据库未初始化"}
            _pid = self.__class__.__name__
            pairs: Dict[str, str] = {}
            for r in (db.distinct_name_pairs(plugin_id=_pid) or []):
                pairs[r["name_before"]] = r["name_after"]
            # 人名池（含人工修正）也并入 —— 覆盖"条目已删但池里仍有译名"的情况
            try:
                _pool = (getattr(self, "_name_map_db", None) or NameMapDb()).load_map(plugin_id=_pid)
                for k, v in (_pool or {}).items():
                    if not (isinstance(k, tuple) and len(k) == 2 and k[0] == "person"):
                        continue
                    _nb = str(k[1] or "").strip()
                    _zh = str((v or ("", ""))[0] or "").strip()
                    if _nb and _zh and _zh != _nb and _nb not in pairs:
                        pairs[_nb] = _zh
            except Exception:
                pass
            if not pairs:
                return {"success": True, "message": "库中暂无已翻译人名可同步"}
            res = self._run_emby_name_sync(pairs, ctx="全量对齐")
            if not res.get("total"):
                return {"success": False, "message": "Emby 未配置或不可用"}
            return {"success": True, "message": f"已同步 Emby 人名：{res.get('message')}",
                    "data": res}
        except Exception as e:
            logger.error(f"[Emby] 同步人名失败: {e}")
            return {"success": False, "message": str(e)}

    def _api_db_update_person_scope(self, data: Optional[dict] = None):
        _g = self._api_gate()
        if _g:
            return _g
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            data = data or {}
            item_id = str(data.get("item_id") or "").strip()
            server_id = str(data.get("server_id") or "")
            name_before = str(data.get("name_before") or "").strip()
            if not name_before:
                return {"success": False, "message": "缺少 name_before"}
            name_after = str(data.get("name_after") or "").strip() or name_before
            role_before = str(data.get("role_before") or "").strip()
            role_after = str(data.get("role_after") or "").strip()
            role_scope = str(data.get("role_scope") or data.get("scope") or "single").strip().lower()
            # v4.6.74（报告第十四节）：人名作用域 —— 默认「只改当前人物身份」，
            # 「全库同名修改」必须由用户主动选择（前端标红二次确认）才走全局 UPDATE。
            name_scope = str(data.get("name_scope") or "").strip().lower()
            if name_scope not in ("single", "series", "library"):
                name_scope = "single"
            season_num = data.get("season_num")
            episode_num = data.get("episode_num")
            index = data.get("index")
            db = getattr(self, "_people_db", None)
            if db is None:
                return {"success": False, "message": "翻译记录数据库未初始化"}
            _pid = self.__class__.__name__
            # v4.6.53：*_force = 用户在弹窗里确实改过该字段（即便改回与原文相同 / 清空）。
            # 「译名改回与原文一致」是合法操作（= 清除错译、恢复原文），此前被当成「没有变化」拒绝。
            _force_name = bool(data.get("name_force"))
            _force_role = bool(data.get("role_force"))
            _name_changed = bool(name_after) and (_force_name or name_after != name_before)
            _role_changed = bool(role_after) and (_force_role or role_after != role_before)
            if not _name_changed and not _role_changed:
                return {"success": False, "message": "没有需要更新的内容"}
            if _role_changed and not item_id:
                return {"success": False, "message": "缺少 item_id（角色更新需要条目定位）"}

            n_name = n_role = 0
            if _name_changed:
                # v4.6.74（报告第十四节）：默认**只改当前人物身份** —— 不再默认全库同名
                # （同名可能对应两个不同真人）；「全库同名修改」需用户主动选择 name_scope=library。
                n_name = int(db.update_name_by_scope(
                    plugin_id=_pid, name_before=name_before, name_after=name_after,
                    server_id=server_id, item_id=item_id,
                    season_num=season_num, episode_num=episode_num, index=index,
                    scope=name_scope) or 0)
                if n_name == 0:
                    _sc_lbl = {"single": "当前这一条", "series": "该作品内同名",
                               "library": "全库同名"}.get(name_scope, name_scope)
                    return {"success": False,
                            "message": f"库中无「{name_before}」的记录（范围：{_sc_lbl}）"}
            if _role_changed:
                n_role = int(db.update_role_by_scope(
                    plugin_id=_pid, item_id=item_id, server_id=server_id,
                    season_num=season_num, episode_num=episode_num, index=index,
                    role_before=role_before, role_after=role_after,
                    scope=role_scope) or 0)

            dbm = getattr(self, "_name_map_db", None) or NameMapDb()
            # v4.6.74（报告第十四节）：只有「全库同名修改」才写全局人名池（人工修正记忆）——
            # 局部修改（仅这一条 / 该作品内同名）不写全局池，否则另一部作品里的
            # 同名人物（可能是另一个真人）会命中文中译名被一起改掉。
            if _name_changed and name_scope == "library":
                try:
                    dbm.upsert_manual(plugin_id=_pid, name_type="person",
                                      original=name_before, zh=name_after)
                except Exception:
                    pass
            if _role_changed and role_before:
                try:
                    dbm.upsert_manual(plugin_id=_pid, name_type="role",
                                      original=role_before, zh=role_after)
                except Exception:
                    pass
            # v4.6.70（报告第二十八节）：人工修改角色 → 写入「同剧角色翻译记忆」(source=manual，
            # 优先级最高) —— 同剧后续集直接复用该译文、不再调 AI；AI 结果不得覆盖人工结果。
            if _role_changed and role_before and role_after:
                try:
                    _sn = ""
                    try:
                        _mt = db.item_meta(plugin_id=_pid, item_id=item_id,
                                           server_id=str(server_id or ""))
                        _sn = str((_mt or {}).get("title") or "")
                    except Exception:
                        _sn = ""
                    db.role_memory_put(plugin_id=_pid, rows=[{
                        "server_id": str(server_id or ""), "series_id": str(item_id or ""),
                        "series_name": _sn, "role_original": str(role_before),
                        "role_translated": str(role_after), "source": "manual"}])
                except Exception:
                    pass

            _scope_map = {"single": "仅这一集/这一条", "season": "这一季", "series": "这个剧",
                          "tv": "仅剧级名单", "library": "全库同名"}
            _scope_txt = _scope_map.get(role_scope, role_scope)
            _sync_emby = bool(data.get("sync_emby"))
            _is_restore = bool(_name_changed and name_after == name_before)
            _sync_txt = ""
            if _sync_emby and _name_changed and not _is_restore:
                _sr = self._emby_sync_manual_rename(name_before, name_after, server_id=server_id)
                if _sr.get("ok"):
                    _sync_txt = "；Emby 人名已同步" if not _sr.get("skipped") else "；Emby 人名已是译文"
                else:
                    _sync_txt = f"；Emby 人名未同步（{_sr.get('reason')}）"
                self._push_log("INFO", f"Emby 人名同步: {name_before} → {name_after} · {_sr.get('reason')}")
            elif _is_restore:
                _sync_txt = "；已恢复为原文（未改 Emby，如需把 Emby 的名字也改回去请自行处理）"
            elif _name_changed:
                _sync_txt = "；未同步 Emby（未勾选）"
            _msg_parts = []
            _name_sc_lbl = {"single": "仅当前这一条", "series": "该作品内同名",
                            "library": "全库同名"}.get(name_scope, name_scope)
            if _name_changed:
                _msg_parts.append(f"人名更新 {n_name} 处（{_name_sc_lbl}）"
                                  + ("（已恢复为原文/清除该人名的错译）" if _is_restore else ""))
            if _role_changed:
                _msg_parts.append(f"角色更新 {n_role} 处（{_scope_txt}）")
            self._push_log("INFO", f"人工修正译文: {name_before} → {name_after}（{'；'.join(_msg_parts)}；重跑扫描不会被 AI 覆盖）")
            return {"success": True,
                    "message": f"{'；'.join(_msg_parts)}（重跑扫描不会被 AI 覆盖）{_sync_txt}",
                    "data": {"updated_name": n_name, "updated_role": n_role,
                             "name_scope": name_scope, "role_scope": role_scope}}
        except Exception as e:
            logger.error(f"[DB] scope 更新失败: {e}\n{traceback.format_exc()}")
            return {"success": False, "message": str(e)}

    def _api_person_occurrences(self, name_before: str = "", limit: int = 1000,
                                server_id: str = "", item_id: str = ""):
        try:
            db = getattr(self, "_people_db", None)
            if db is None:
                return {"success": False, "message": "翻译记录数据库未初始化"}
            # UI-006：按来源服务器限定，避免不同服务器同名人物混入同一「出现清单」
            _nb = str(name_before or "").strip()
            _sid = str(server_id or "").strip()
            rows = db.rows_by_name(plugin_id=self.__class__.__name__,
                                   name_before=_nb, server_id=_sid,
                                   limit=int(limit or 1000))
            # 跨来源兜底（v4.6.48）：人名池行带 Emby 服务器标识，而「库」表里的人名记录
            # 是本地 NFO 来源（server_id 为空）—— 直接按服务器过滤会 0 条、显示「查不到」。
            # 故带 server_id 查不到时，退回不限来源再查一次（库表本就是本地单一来源，不会串数据）。
            if not rows and _sid:
                rows = db.rows_by_name(plugin_id=self.__class__.__name__,
                                       name_before=_nb, server_id="",
                                       limit=int(limit or 1000))
            # v4.6.106（LIB-012）：库页「本条目」搜索模式下展开「N 处」时，出现清单也限定在该条目内
            # （否则仍会把其他作品的同名出现列出来 —— 与搜索范围口径不一致）。
            # 人名池页（/pool/occurrences）不传 item_id → 行为不变。
            _iid = str(item_id or "").strip()
            if _iid:
                rows = [r for r in rows if str(r.get("item_id") or "") == _iid]
            return {"success": True, "data": rows, "count": len(rows)}
        except Exception as e:
            logger.error(f"[DB] 读取人物出现清单失败: {e}")
            return {"success": False, "message": str(e)}

    def _api_db_update_person_global(self, data: Optional[dict] = None):
        _g = self._api_gate()
        if _g:
            return _g
        _tb = self._task_busy_msg()
        if _tb:
            return _tb
        try:
            data = data or {}
            name_before = str(data.get("name_before") or "").strip()
            if not name_before:
                return {"success": False, "message": "缺少 name_before（原文名）"}
            name_after = str(data.get("name_after") or "").strip() or name_before
            role_after = str(data.get("role_after") or "").strip()
            role_before = str(data.get("role_before") or "").strip()
            server_id = str(data.get("server_id") or "")
            db = getattr(self, "_people_db", None)
            if db is None:
                return {"success": False, "message": "翻译记录数据库未初始化"}
            _pid = self.__class__.__name__
            n = db.update_by_name(plugin_id=_pid, name_before=name_before,
                                  name_after=name_after,
                                  role_after=(role_after if (role_after and not role_before) else ""))
            if role_after and role_before:
                try:
                    n += int(db.update_role_by_before(plugin_id=_pid, role_before=role_before,
                                                      role_after=role_after) or 0)
                except Exception:
                    pass
            # 人工修正同步写人名池（manual 最高优先级，重跑扫描不被 AI 覆盖）
            dbm = getattr(self, "_name_map_db", None) or NameMapDb()
            if name_after and name_after != name_before:
                dbm.upsert_manual(plugin_id=_pid, name_type="person", original=name_before, zh=name_after)
            if role_after:
                _rb_sync = role_before
                if not _rb_sync:
                    rows = db.search_people(plugin_id=_pid, keyword=name_before, limit=10)
                    for p in rows:
                        _rb0 = str(p.get("role_before") or "").strip()
                        if _rb0:
                            _rb_sync = _rb0
                            break
                if _rb_sync and role_after != _rb_sync:
                    dbm.upsert_manual(plugin_id=_pid, name_type="role", original=_rb_sync, zh=role_after)
            _sync_txt = ""
            if getattr(self, "_emby_name_sync", True) and name_after and name_after != name_before:
                _sr = self._emby_sync_manual_rename(name_before, name_after, server_id=server_id)
                if _sr.get("ok"):
                    _sync_txt = "；Emby 人名已同步" if not _sr.get("skipped") else "；Emby 人名已是译文"
                else:
                    _sync_txt = f"；Emby 人名未同步（{_sr.get('reason')}）"
                self._push_log("INFO", f"Emby 人名同步: {name_before} → {name_after} · {_sr.get('reason')}")
            self._push_log("INFO", f"人物全局修正: {name_before} → {name_after or '（清理）'}（全库 {n} 条，重跑扫描不被 AI 覆盖）")
            return {"success": True, "message": f"已更新全库 {n} 条「{name_before}」记录（重跑扫描不被 AI 覆盖）{_sync_txt}",
                    "data": {"updated": n}}
        except Exception as e:
            logger.error(f"[DB] 人物全局更新失败: {e}\n{traceback.format_exc()}")
            return {"success": False, "message": str(e)}

    def _api_config_view(self) -> dict:
        """下发给前端的配置视图（SEC-001）—— LLM API Key 只给掩码与「是否已配置」，
        原值绝不出后端（浏览器 DevTools / Network 看不到密钥）。
        保存沿用旧 Key：前端留空 + 后端按「空 = 保持原值」处理；显式清除走 clear_api_key。"""
        _cfg = self._dump_config()
        _k = str(_cfg.get(constants.CFG_LLM_API_KEY) or "")
        _cfg[constants.CFG_LLM_API_KEY] = ""
        _cfg["has_api_key"] = bool(_k)
        _cfg["llm_api_key_masked"] = _mask_secret(_k)
        return _cfg

    def _api_get_config(self):
        """Vue 设置页：读取当前配置（含默认值）"""
        try:
            return {"success": True, "data": self._api_config_view()}
        except Exception as e:
            logger.error(f"[Config] 读取配置失败: {e}")
            return {"success": False, "message": str(e)}

    def _api_save_config(self, data: Optional[dict] = None):
        """Vue 设置页：保存配置（经宿主 update_config 热生效）
        显式签名 - 宿主动态路由把 **kwargs 当 query 必填项导致 422
        """
        try:
            if not isinstance(data, dict):
                return {"success": False, "message": "参数格式错误，期望 JSON body"}
            data = dict(data)
            # SEC-001：Key 的空值语义 —— 前端只拿得到掩码，因此
            #   空 = 保持原 Key（不覆盖）；显式清除必须带 clear_api_key=true。
            if bool(data.pop("clear_api_key", False)):
                data[constants.CFG_LLM_API_KEY] = ""
            elif not str(data.get(constants.CFG_LLM_API_KEY) or "").strip():
                data.pop(constants.CFG_LLM_API_KEY, None)
            # 下行字段（前端展示用）不参与保存
            data.pop("has_api_key", None)
            data.pop("llm_api_key_masked", None)
            # 合并当前配置，仅存传入字段
            cur = self._dump_config()
            merged = {**cur, **data}
            self._load_config(merged)
            self.update_config(self._dump_config())
            # LLM 相关字段变化后热刷新客户端
            if any(str(k).startswith("llm_") for k in data.keys()) or "prompt_template" in data:
                if self._llm_workers_busy():
                    self._llm_reload_pending = True
                    logger.info("[LLM] 检测到 LLM 作业进行中，配置已保存；新 LLM 客户端将在翻译链路空闲后生效")
                    self._push_log("INFO", "LLM 配置已保存：当前有翻译/写回/拉取作业在跑，新的 LLM 客户端将在其空闲后自动生效")
                else:
                    self._init_llm()
                    self._llm_reload_pending = False
            # v4.6.99（报告 P1-03 B/C）：任务运行中**允许**保存配置，但必须明确告知
            # 「与任务语义相关的设置下一个任务才生效」—— 当前任务继续使用启动时的 Snapshot，
            # 不会因热修改而中途改变翻译范围 / 人数上限 / 写回策略。
            _busy = False
            try:
                _busy = bool(self._task_busy_msg())
            except Exception:
                _busy = False
            if _busy:
                _m = ("配置已保存。当前有任务正在运行 —— 与翻译范围 / 人数上限 / 写回策略"
                      "相关的设置将在**下一个任务**生效（本任务继续使用启动时的快照）。")
                logger.info(f"[Config] 保存（任务运行中，下个任务生效）")
                self._push_log("INFO", _m)
                return {"success": True, "message": _m, "data": {"applied_next_task": True}}
            self._push_log("INFO", f"配置已保存并生效（模式={self._scan_mode}）")
            return {"success": True, "message": "配置已保存并生效",
                    "data": {"applied_next_task": False}}
        except Exception as e:
            logger.error(f"[Config] 保存配置失败: {e}")
            return {"success": False, "message": str(e)}
