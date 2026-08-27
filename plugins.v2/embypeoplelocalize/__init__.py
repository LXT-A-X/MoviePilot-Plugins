"""
EmbyPeopleLocalize - Emby 演职人员中文化 v1.1.0
利用大模型把 Emby 英文/罗马音/日文人名翻译为简体中文并写回
支持多服务器分库、入库/Webhook触发、Cast 锁定防覆盖、繁简直转省 LLM

v1.1.0 更新:
- 移除搜索和重译功能
- 优化剧集显示格式（按季聚合显示，如"第一季 1-20集"）
- 修复 ui_forms.py 语法错误

v1.0.0 完全重构:
- Webhook 处理完全重写：支持多种事件格式、智能事件检测、自动重试
- 新增 Webhook 状态监控和手动测试功能
- 优化服务器匹配逻辑，支持多种 server_id 格式
- 增强日志记录，便于问题排查
- 统一翻译流程，增加错误恢复机制
"""
import json
import os
import re
import threading
import time
import traceback
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

from app.core.config import settings
from app.core.event import eventmanager, Event
from app.helper.mediaserver import MediaServerHelper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import ServiceInfo, NotificationType
from app.schemas.types import EventType

from .ui import build_form, build_page
from .emby_client import EmbyClient
from .llm_client import LLMClient
from .translator import PeopleTranslator
from . import constants


class EmbyPeopleLocalize(_PluginBase):
    plugin_name = "Emby 演职人员中文化"
    plugin_desc = "利用大模型把 Emby 英文/罗马音/日文人名翻译为简体中文并写回"
    plugin_icon = "embypeoplelocalize.jpg"
    plugin_version = "1.3.11"
    plugin_author = "LXT-A-X"
    plugin_config_prefix = "embypeoplelocalize_"
    plugin_order = 27
    auth_level = 1
    v2 = True

    # ────────── 配置项 ──────────
    _enabled: bool = False
    _onlyonce: bool = False
    # v1.3.0: 无默认值 - 避免类级可变对象在 MoviePilot 热加载时污染
    _libraries: List[str]
    _prompt_template: str = ""
    _translate_actor: bool = True
    _translate_director: bool = False
    _translate_writer: bool = False
    _translate_producer: bool = False
    _translate_all: bool = False
    _translate_role: bool = True
    _max_people_per_title: int = 10
    _max_people_per_batch: int = 5
    _batch_titles: int = 10
    _overwrite_chinese: bool = False
    _delay: int = 2
    _lock_cast: bool = False
    _webhook_delay: int = 60
    _notify_on_complete: bool = False
    _history_search_keyword: str = ""

    # 运行时触发开关
    _run_scan: bool = False
    _run_lock_cast: bool = False
    _run_clear_cache: bool = False

    # LLM 独立配置
    _llm_base_url: str = ""
    _llm_api_key: str = ""
    _llm_model: str = ""
    _llm_timeout: int = 120

    # ────────── 运行时状态（仅类型注解占位，实际值在 init_plugin 中实例化）──────────
    # v1.2.8: 所有可变类型运行时状态全部移到 init_plugin，避免 MoviePilot 热加载时
    # 类变量在多个实例/重载之间共享导致的污染问题
    _ms_helper: Optional[MediaServerHelper]
    _emby: Optional[EmbyClient]
    _llm: Optional[LLMClient]
    _translator: Optional[PeopleTranslator]
    _stop_requested: bool
    _force_refresh: bool
    _name_cache: Dict[str, Dict[str, str]]
    _role_cache: Dict[str, Dict[str, str]]
    _processed: Dict[str, str]
    _history: List[Dict[str, Any]]
    _failed: List[Dict[str, Any]]
    _live_log: List[Dict[str, Any]]
    _is_running: bool
    _is_paused: bool
    _last_run_time: Optional[float]
    _state_lock: threading.Lock
    _scan_lock: threading.Lock
    _scan_cursor: Optional[Dict[str, Any]]

    # 进度追踪（v1.3.0 统一为 _scan_status dict）
    _scan_status: Dict[str, Any]
    _progress_step_start_time: float  # 当前条目计时起点（_elapsed_seconds 用）

    # 缓存命中率统计
    _cache_hits: int
    _cache_misses: int

    # Webhook 状态追踪
    _webhook_received: int
    _webhook_processed: int
    _webhook_failed: int
    _webhook_last_time: Optional[float]
    _webhook_last_event: str
    _webhook_error: str

    # 状态持久化路径
    _state_file: str

    # ────────── V2 私有属性 ──────────
    @property
    def private_attrs(self) -> List[str]:
        return [
            "_enabled", "_onlyonce", "_libraries", "_prompt_template",
            "_translate_actor", "_translate_director", "_translate_writer",
            "_translate_producer", "_translate_all", "_translate_role",
            "_max_people_per_title", "_max_people_per_batch", "_overwrite_chinese",
            "_delay", "_lock_cast", "_webhook_delay", "_notify_on_complete",
            "_run_scan", "_run_lock_cast", "_run_clear_cache",
            "_llm_base_url", "_llm_api_key", "_llm_model", "_llm_timeout",
            "_is_running", "_is_paused", "_last_run_time", "_last_save_time",
            "_name_cache", "_role_cache", "_processed", "_history",
            "_scan_status",  # v1.3.0: 单一数据源，替代 _progress_*
            "_cache_hits", "_cache_misses",
            "_webhook_received", "_webhook_processed", "_webhook_failed",
            "_webhook_last_time", "_webhook_last_event", "_webhook_error",
        ]

    # ============================================================
    # 状态持久化
    # ============================================================
    def _get_state_file(self) -> str:
        if not self._state_file:
            cache_dir = os.path.join("config", "plugins", "embypeoplelocalize")
            os.makedirs(cache_dir, exist_ok=True)
            self._state_file = os.path.join(cache_dir, "state.json")
        return self._state_file

    def _save_state(self):
        try:
            state = {
                "version": self.plugin_version,
                "name_cache": self._name_cache,
                "role_cache": self._role_cache,
                "processed": self._processed,
                "history": self._history[-constants.MAX_HISTORY:],
                "last_run_time": self._last_run_time,
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
                # v1.2.6: 持久化失败队列
                "failed": self._failed[-2000:] if hasattr(self, "_failed") else [],
                # v1.2.7: 断点续扫 - 记录当前扫描位置
                "scan_cursor": self._scan_cursor if hasattr(self, "_scan_cursor") else None,
                # v1.2.8: Webhook 统计持久化（避免重启后清零）
                "webhook_received": self._webhook_received if hasattr(self, "_webhook_received") else 0,
                "webhook_processed": self._webhook_processed if hasattr(self, "_webhook_processed") else 0,
                "webhook_failed": self._webhook_failed if hasattr(self, "_webhook_failed") else 0,
                "webhook_last_time": self._webhook_last_time if hasattr(self, "_webhook_last_time") else None,
                "webhook_last_event": self._webhook_last_event if hasattr(self, "_webhook_last_event") else "",
                "webhook_error": self._webhook_error if hasattr(self, "_webhook_error") else "",
            }
            state_file = self._get_state_file()
            tmp_file = state_file + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, state_file)
            logger.debug(f"状态已保存到: {state_file}")
        except Exception as e:
            logger.error(f"保存状态失败: {e}\n{traceback.format_exc()}")

    def _load_state(self):
        try:
            state_file = self._get_state_file()
            if not os.path.exists(state_file):
                logger.info("无持久化状态文件，使用空状态")
                return
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            self._name_cache = state.get("name_cache", {}) or {}
            self._role_cache = state.get("role_cache", {}) or {}
            # v1.2.8: 兼容迁移 - 旧版 "default" 顶层缓存重命名为 "zh-cn"
            # 避免之前 v1.2.7 的缓存结构失效
            if isinstance(self._name_cache, dict) and "default" in self._name_cache:
                default_cache = self._name_cache.pop("default")
                if "zh-cn" not in self._name_cache and default_cache:
                    self._name_cache["zh-cn"] = default_cache
            if isinstance(self._role_cache, dict) and "default" in self._role_cache:
                default_cache = self._role_cache.pop("default")
                if "zh-cn" not in self._role_cache and default_cache:
                    self._role_cache["zh-cn"] = default_cache
            self._processed = state.get("processed", {}) or {}
            self._history = state.get("history", []) or []
            self._last_run_time = state.get("last_run_time")
            self._cache_hits = state.get("cache_hits", 0) or 0
            self._cache_misses = state.get("cache_misses", 0) or 0
            # v1.2.6: 加载失败队列
            if hasattr(self, "_failed"):
                self._failed = state.get("failed", []) or []
            # v1.2.7: 加载断点续扫状态
            if hasattr(self, "_scan_cursor"):
                cursor = state.get("scan_cursor")
                if cursor:
                    self._scan_cursor = cursor
                    logger.info(f"检测到未完成的扫描: {cursor}")
            # v1.2.8: 加载 Webhook 统计（避免重启清零）
            if hasattr(self, "_webhook_received"):
                self._webhook_received = state.get("webhook_received", 0) or 0
                self._webhook_processed = state.get("webhook_processed", 0) or 0
                self._webhook_failed = state.get("webhook_failed", 0) or 0
                self._webhook_last_time = state.get("webhook_last_time")
                self._webhook_last_event = state.get("webhook_last_event", "") or ""
                self._webhook_error = state.get("webhook_error", "") or ""
            total = sum(len(v) for v in self._name_cache.values()) + sum(len(v) for v in self._role_cache.values())
            logger.info(f"加载持久化状态: {len(self._processed)} 条已处理, {len(self._history)} 条历史, {total} 条缓存")
        except Exception as e:
            logger.warning(f"加载状态失败: {e}")
            self._name_cache = {}
            self._role_cache = {}
            self._processed = {}
            self._history = []

    def _auto_save(self):
        # v1.3.11: 每处理完一个条目立即保存，避免停止时进度丢失
        self._save_state()

    # ============================================================
    # V2 API 注册
    # ============================================================
    def get_api(self) -> List[dict]:
        return [
            # v1.3.0: 同时支持 GET/POST - 让 UI 弹窗确认后用 POST 触发
            {"path": "/clear_cache", "endpoint": self._api_clear_cache, "methods": ["GET", "POST"], "auth": None},
            {"path": "/scan", "endpoint": self._api_scan, "methods": ["GET", "POST"], "auth": None},
            {"path": "/stop", "endpoint": self._api_stop, "methods": ["GET", "POST"], "auth": None},
            # v1.3.2: 真正的暂停/恢复 - 保留线程和位置
            {"path": "/pause", "endpoint": self._api_pause, "methods": ["POST"], "auth": None},
            {"path": "/resume", "endpoint": self._api_resume, "methods": ["POST"], "auth": None},
            {"path": "/status", "endpoint": self._api_status, "methods": ["GET", "POST"], "auth": None},
            {"path": "/lock_cast", "endpoint": self._api_lock_cast, "methods": ["POST"], "auth": None},
            {"path": "/refresh_llm", "endpoint": self._api_refresh_llm, "methods": ["POST"], "auth": None},
            {"path": "/webhook_status", "endpoint": self._api_webhook_status, "methods": ["GET"], "auth": None},
            {"path": "/test_webhook", "endpoint": self._api_test_webhook, "methods": ["GET", "POST"], "auth": None},
            # v1.2.6 新增
            {"path": "/live_log", "endpoint": self._api_live_log, "methods": ["GET"], "auth": None},
            {"path": "/failed_list", "endpoint": self._api_failed_list, "methods": ["GET"], "auth": None},
            {"path": "/retry_failed", "endpoint": self._api_retry_failed, "methods": ["POST"], "auth": None},
            {"path": "/clear_failed", "endpoint": self._api_clear_failed, "methods": ["POST"], "auth": None},
        ]

    # v1.2.6: 实时日志 API
    def _api_live_log(self, limit: int = 100):
        try:
            limit = int(limit) if limit else 100
            with self._state_lock:
                logs = list(self._live_log[-limit:])
            return {"success": True, "data": logs}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # v1.2.6: 失败列表 API
    def _api_failed_list(self):
        try:
            with self._state_lock:
                failed = list(self._failed)
            return {"success": True, "data": failed, "count": len(failed)}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # v1.2.6: 重试失败项 API
    def _api_retry_failed(self):
        with self._scan_lock:
            if self._is_running:
                return {"success": False, "message": "当前有扫描任务运行中，无法重试"}
            self._is_running = True
            self._scan_status["running"] = True  # v1.3.0: 同步状态
            self._stop_requested = False
        def _retry_wrapper():
            try:
                self._retry_failed_worker()
            except Exception as e:
                logger.error(f"重试线程未捕获异常: {e}\n{traceback.format_exc()}")
                self._is_running = False
                self._scan_status["running"] = False  # v1.3.0: 同步状态
        threading.Thread(target=_retry_wrapper, daemon=True).start()
        return {"success": True, "message": "重试任务已启动"}

    def _retry_failed_worker(self):
        """v1.2.7: 真正实现失败重试
        - 重新构造 client
        - 调用 _process_item 完整流程（fetch_item -> 翻译 -> 写回）
        - 成功后从 _processed 中清除 key（避免误判为已处理）
        """
        with self._state_lock:
            pending = list(self._failed)
            self._failed.clear()
        self._save_state()
        logger.info(f"开始重试 {len(pending)} 个失败项")
        self._push_log("INFO", f"开始重试 {len(pending)} 个失败项")

        # 按 server 缓存 client，避免重复创建
        client_cache: Dict[str, EmbyClient] = {}
        service_cache: Dict[str, ServiceInfo] = {}

        retried_ok = 0
        retried_fail = 0

        for entry in pending:
            if self._stop_requested:
                logger.info("重试任务已被请求停止")
                break
            item_id = entry.get("item_id", "")
            skey = entry.get("skey", "")
            if not item_id or not skey:
                continue

            # 重建 client（如果未缓存）
            if skey not in client_cache:
                services = self._get_all_emby_services()
                svc = next((s for s in services if self._get_server_identifier(s) == skey), None)
                if not svc:
                    logger.warning(f"重试 [{item_id}] 找不到服务: skey={skey}")
                    # 仍记录为失败
                    self._record_failure(item_id, skey, entry.get("title", ""), "服务不可用")
                    retried_fail += 1
                    continue
                try:
                    client = EmbyClient(
                        self._get_service_url(svc),
                        self._get_service_api_key(svc),
                        svc,
                        user_id=self._get_service_user_id(svc),
                        use_proxy=self._use_proxy,
                    )
                    client_cache[skey] = client
                    service_cache[skey] = svc
                except Exception as e:
                    logger.error(f"重试 [{item_id}] 创建客户端失败: {e}")
                    self._record_failure(item_id, skey, entry.get("title", ""), f"客户端创建失败: {e}")
                    retried_fail += 1
                    continue

            client = client_cache[skey]
            svc = service_cache[skey]

            # 调用 _process_item 完整重试
            # 先构造 item 字典（只需要 Id）
            item_dict = {"Id": item_id, "Name": entry.get("title", ""), "Type": "Movie"}
            try:
                # 清除 _processed 中的记录，强制重新处理
                key = f"{skey}:{item_id}"
                with self._state_lock:
                    self._processed.pop(key, None)
                self._force_refresh = True
                with self._process_lock:
                    t, f = self._process_item(client, svc, skey, item_dict, "")
                self._force_refresh = False
                if t > 0:
                    retried_ok += 1
                    logger.info(f"重试成功 [{item_id}] {entry.get('title', '?')}")
                    self._push_log("INFO", f"重试成功: {entry.get('title', item_id)}")
                else:
                    retried_fail += 1
                    logger.warning(f"重试未成功 [{item_id}] {entry.get('title', '?')} t={t} f={f}")
                    # 重新记录失败
                    self._record_failure(item_id, skey, entry.get("title", ""), entry.get("reason", "重试失败"))
            except Exception as e:
                retried_fail += 1
                logger.error(f"重试异常 [{item_id}]: {e}\n{traceback.format_exc()}")
                self._record_failure(item_id, skey, entry.get("title", ""), f"重试异常: {e}")
            time.sleep(self._delay)

        self._force_refresh = False
        logger.info(f"重试完成: 成功 {retried_ok} 条, 失败 {retried_fail} 条")
        self._push_log("INFO", f"重试完成: 成功 {retried_ok}, 失败 {retried_fail}")
        self._is_running = False
        self._scan_status["running"] = False  # v1.3.0: 同步状态
        self._save_state()

    # v1.2.6: 清空失败列表 API
    def _api_clear_failed(self):
        try:
            with self._state_lock:
                self._failed.clear()
            self._save_state()
            return {"success": True, "message": "失败列表已清空"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # v1.2.6: 内部辅助 - 记录实时日志
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

    # v1.2.8: 内部辅助 - 设置扫描步骤状态
    # 用于 UI 扫描详情展示，4 个标准步骤
    STEP_NAMES = ("获取Emby", "提取演员", "AI翻译", "写回")
    STEP_DONE = "✓"
    STEP_ACTIVE = "●"
    STEP_PENDING = "○"
    STEP_SKIPPED = "—"

    def _build_scan_status(self) -> Dict[str, Any]:
        """v1.3.0: 直接返回 _scan_status dict 引用 - 单一数据源
        不再从多个 _progress_* 属性聚合，杜绝读写不同步问题
        UI 读取时建议 dict(self._scan_status) 浅拷贝避免外部篡改
        """
        with self._state_lock:
            status = dict(self._scan_status)
            total = status.get("total", 0) or 0
            done = status.get("done", 0) or 0
            status["percent"] = round(done / max(total, 1) * 100, 1) if total > 0 else 0.0
            status["elapsed_seconds"] = self._elapsed_seconds()
            status["last_run_time"] = self._last_run_time
            return status

    def _reset_steps(self):
        """v1.3.0: 重置 4 步骤状态 - 写入 _scan_status
        启动/切换条目时调用，UI 永远有稳定结构
        """
        try:
            with self._state_lock:
                self._scan_status["step_status"] = {
                    "获取Emby": self.STEP_PENDING,
                    "提取演员": self.STEP_PENDING,
                    "AI翻译": self.STEP_PENDING,
                    "写回": self.STEP_PENDING,
                }
                self._scan_status["current_step"] = ""
                self._progress_step_start_time = time.time()
        except Exception:
            pass

    def _set_step(self, name: str, status: str = None):
        """v1.3.0: 设置当前步骤 - 写入 _scan_status
        name: 步骤名（获取Emby/提取演员/AI翻译/写回）
        status: 状态符号（✓/●/○/—），传 None 表示设为进行中
        """
        try:
            with self._state_lock:
                step_status = self._scan_status.setdefault("step_status", {})
                if name not in step_status:
                    step_status[name] = self.STEP_PENDING
                if status is None:
                    step_status[name] = self.STEP_ACTIVE
                    self._scan_status["current_step"] = name
                else:
                    step_status[name] = status
                    if status == self.STEP_DONE:
                        try:
                            idx = self.STEP_NAMES.index(name)
                            if idx + 1 < len(self.STEP_NAMES):
                                next_step = self.STEP_NAMES[idx + 1]
                                if step_status.get(next_step) == self.STEP_PENDING:
                                    step_status[next_step] = self.STEP_ACTIVE
                                    self._scan_status["current_step"] = next_step
                        except ValueError:
                            pass
        except Exception:
            pass

    def _elapsed_seconds(self) -> int:
        """当前条目处理耗时（秒）"""
        try:
            return int(time.time() - getattr(self, "_progress_step_start_time", time.time()))
        except Exception:
            return 0

    def _finalize_steps(self, success: bool = True):
        """处理完一个条目后收尾 - 把最后一步也标为完成/失败"""
        try:
            with self._state_lock:
                step_status = self._scan_status.get("step_status", {})
                for k, v in list(step_status.items()):
                    if v == self.STEP_ACTIVE:
                        step_status[k] = self.STEP_DONE if success else self.STEP_SKIPPED
                self._scan_status["current_step"] = ""
        except Exception:
            pass

    # v1.2.7: 统一日志入口 - 同步到实时日志队列和标准 logger
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

    # v1.2.8: 接管底层 logger - 让 EmbyClient / LLMClient / Translator 的
    # logger.info(...) 也能进入 _live_log 队列
    _log_bridge_installed: bool = False
    def _install_log_bridge(self):
        if self._log_bridge_installed:
            return
        try:
            import logging
            from app.log import logger as mp_logger
            # MoviePilot 主 logger 名称为 "moviepilot"，插件 logger 通过
            # 继承的子 logger 名为 "moviepilot.plugins.embypeoplelocalize" 等
            # 我们需要拦截带有 [EmbyClient]/[LLMClient] 前缀的日志
            class _LogBridgeHandler(logging.Handler):
                def __init__(_h, outer):
                    super().__init__()
                    _h.outer = outer
                def emit(_h, record):
                    try:
                        msg = _h.format(record)
                        # 只接管底层模块的日志
                        if any(tag in msg for tag in ("[EmbyClient]", "[LLMClient]", "[PeopleTranslator]")):
                            level = record.levelname or "INFO"
                            if level == "WARNING":
                                level = "WARNING"
                            elif level == "ERROR":
                                level = "ERROR"
                            elif level == "DEBUG":
                                level = "DEBUG"
                            else:
                                level = "INFO"
                            _h.outer._push_log(level, msg)
                    except Exception:
                        pass
            # 找到 moviepilot 的根 logger，添加 handler
            root_logger = logging.getLogger("moviepilot")
            if root_logger and not any(isinstance(h, _LogBridgeHandler) for h in root_logger.handlers):
                bridge = _LogBridgeHandler(self)
                bridge.setLevel(logging.INFO)
                bridge.setFormatter(logging.Formatter("%(message)s"))
                root_logger.addHandler(bridge)
                self._log_bridge_installed = True
                logger.info("[EmbyPeopleLocalize] 日志桥接已安装")
        except Exception as e:
            logger.warning(f"安装日志桥接失败: {e}")

    # v1.2.6: 内部辅助 - 记录失败
    def _record_failure(self, item_id: str, skey: str, title: str, reason: str):
        try:
            with self._state_lock:
                self._failed.append({
                    "item_id": item_id,
                    "skey": skey,
                    "title": title,
                    "reason": reason,
                    "time": time.time(),
                })
                # 上限 2000
                if len(self._failed) > 2000:
                    self._failed = self._failed[-2000:]
        except Exception:
            pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        try:
            lib_options = self._get_library_options()
            valid_values = {opt["value"] for opt in lib_options}
            invalid_libs = []
            if valid_values:
                original = list(self._libraries or [])
                cleaned = [v for v in original if v in valid_values]
                invalid_libs = [v for v in original if v not in valid_values]
                if invalid_libs:
                    logger.warning(f"清理失效的媒体库配置: {invalid_libs}")
                    self._libraries = cleaned
                    self.update_config(self._dump_config())

            # v1.3.1: build_form 现在只返回 form 列表；config 单独从 self._dump_config() 取
            form = build_form(lib_options, self, invalid_libraries=invalid_libs)
            config = self._dump_config()
            if not config.get("prompt_template"):
                config["prompt_template"] = constants.DEFAULT_PROMPT
            return form, config
        except Exception as e:
            logger.error(f"构建配置表单失败: {e}\n{traceback.format_exc()}")
            return [], {}

    def get_page(self) -> List[dict]:
        try:
            return build_page(self)
        except Exception as e:
            logger.error(f"构建数据面板失败: {e}\n{traceback.format_exc()}")
            return [{"component": "div", "props": {"class": "pa-4 text-error"},
                     "content": [{"component": "p", "text": f"页面渲染失败: {e}"}]}]

    def get_state(self) -> bool:
        return self._enabled

    # ============================================================
    # API 处理
    # ============================================================
    def _api_clear_cache(self):
        try:
            self.clear_cache()
            return {"success": True, "message": "缓存已清空"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _start_scan_thread(self, force: bool = False) -> bool:
        """v1.3.12 (D方案): 后台线程启动扫描引擎，调用方立即返回。
        不阻塞 init_plugin 保存接口 —— LLM/Translator/Emby 的初始化延迟到
        扫描线程内部完成（见 _scan_worker 开头惰性初始化）。
        """
        with self._scan_lock:
            if self._is_running:
                logger.info("扫描已在运行中（_scan_lock 兜底）")
                return False
            # 运行状态（_is_running / _scan_status）交由 _scan_worker 内部设置，
            # 避免此处置位导致 _scan_worker 开头的 `if self._is_running: return` 误判。
            # 这里只做启动前的复位准备。
            self._stop_requested = False
            # v1.3.2: 重置 stop event - 上一次停止后必须 clear 才能再次启动
            if hasattr(self, "_stop_event") and self._stop_event is not None:
                self._stop_event.clear()

        # v1.2.6: 增加线程包装，确保异常时状态恢复
        def _scan_wrapper():
            try:
                self._scan_worker(force=force)
            except Exception as e:
                logger.error(f"扫描线程未捕获异常: {e}\n{traceback.format_exc()}")
                self._is_running = False
                self._is_paused = False
                # v1.3.0: 同步 _scan_status - 单一数据源
                self._scan_status["running"] = False
                self._scan_status["paused"] = False
                self._scan_status["current_title"] = ""
                self._scan_status["current_library"] = ""
                self._save_state()
                try:
                    self.post_message(
                        mtype=NotificationType.Manual,
                        title=self.plugin_name,
                        text=f"扫描异常中断: {str(e)[:100]}"
                    )
                except Exception:
                    pass

        # v1.3.2: 保存线程引用，stop_service 时可以 join
        self._scan_thread = threading.Thread(target=_scan_wrapper, daemon=True)
        self._scan_thread.start()
        return True

    def _api_scan(self):
        # v1.3.12 (D方案): 移除 LLM/Translator/Emby 前置检查。
        # 它们现在在线程内惰性初始化（见 _scan_worker 开头），配置未就绪时
        # 扫描线程会自动 _startup() 并给出明确错误日志，而非在此同步拦截。
        if self._start_scan_thread(True):
            return {"success": True, "message": "扫描任务已启动"}
        return {"success": False, "message": "扫描任务正在运行中"}

    def _api_stop(self):
        """v1.3.2: 真正停止扫描 - 区分暂停和停止
        - 停止：保存 cursor，下次可续扫
        - 暂停：保留线程和位置，循环 sleep 等待
        """
        if not self._is_running:
            return {"success": False, "message": "没有正在运行的扫描任务"}
        self._stop_requested = True
        self._is_paused = False  # 停止 ≠ 暂停
        # 同步 _scan_status - 单一数据源
        self._scan_status["paused"] = False
        # 立即保存当前 cursor，下次启动可续扫
        self._save_state()
        return {"success": True, "message": "已请求停止扫描（将保存断点）"}

    def _api_pause(self):
        """v1.3.2: 暂停扫描 - 保留线程和位置，扫描循环用 Event.wait 等待恢复"""
        if not self._is_running:
            return {"success": False, "message": "没有正在运行的扫描任务"}
        if self._is_paused:
            return {"success": False, "message": "扫描已处于暂停状态"}
        self._is_paused = True
        self._scan_status["paused"] = True
        # v1.3.2: 用 Event.set() 通知扫描循环 sleep
        if hasattr(self, "_pause_event") and self._pause_event is not None:
            self._pause_event.set()
        logger.info("⏸ 扫描已暂停")
        return {"success": True, "message": "⏸ 扫描已暂停"}

    def _api_resume(self):
        """v1.3.2: 恢复扫描 - Event.clear() 后扫描循环继续"""
        if not self._is_running:
            return {"success": False, "message": "没有正在运行的扫描任务"}
        if not self._is_paused:
            return {"success": False, "message": "扫描未处于暂停状态"}
        self._is_paused = False
        self._scan_status["paused"] = False
        # v1.3.2: clear 后扫描循环 Event.wait() 立刻返回
        if hasattr(self, "_pause_event") and self._pause_event is not None:
            self._pause_event.clear()
        logger.info("▶ 扫描已恢复")
        return {"success": True, "message": "▶ 扫描已恢复"}

    def _api_status(self):
        total_lookups = self._cache_hits + self._cache_misses
        hit_rate = round(self._cache_hits / total_lookups * 100, 1) if total_lookups > 0 else 0.0

        # Webhook 状态
        wh_total = self._webhook_received
        wh_processed = self._webhook_processed
        wh_failed = self._webhook_failed
        wh_success_rate = round(wh_processed / max(wh_total, 1) * 100, 1) if wh_total > 0 else 0.0

        wh_last_time = None
        if self._webhook_last_time:
            wh_last_time = datetime.fromtimestamp(self._webhook_last_time).strftime("%Y-%m-%d %H:%M:%S")

        # v1.2.9: 统一扫描状态对象
        scan_status = self._build_scan_status()
        # 失败中心
        with self._state_lock:
            failed_count = len(self._failed)
        # 最近活动
        with self._state_lock:
            recent_activity = list(self._history[-10:][::-1])

        return {
            "success": True,
            "data": {
                "is_running": self._is_running,
                "is_paused": self._is_paused,
                "history_count": len(self._history),
                "name_cache_count": sum(len(v) for v in self._name_cache.values()),
                "role_cache_count": sum(len(v) for v in self._role_cache.values()),
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
                "cache_hit_rate": hit_rate,
                "processed_count": len(self._processed),
                # v1.2.9: 改为统一 scan_status 对象
                "scan_status": scan_status,
                # v1.2.9: 失败中心 + 最近活动
                "failed_count": failed_count,
                "recent_activity": recent_activity,
                "webhook": {
                    "total_received": wh_total,
                    "processed": wh_processed,
                    "failed": wh_failed,
                    "success_rate": wh_success_rate,
                    "last_time": wh_last_time,
                    "last_event": self._webhook_last_event,
                    "last_error": self._webhook_error,
                }
            }
        }

    def _api_lock_cast(self):
        try:
            services = self._get_all_emby_services()
            if not services or not self._emby:
                return {"success": False, "message": "Emby 未连接"}
            processed = self._processed or {}
            if not processed:
                return {"success": True, "message": "没有已处理的条目"}
            locked = skipped = failed = 0
            for key in list(processed.keys()):
                parts = key.split(":", 1)
                if len(parts) != 2:
                    skipped += 1
                    continue
                skey, item_id = parts
                svc = next((s for s in services if self._get_server_identifier(s) == skey), None)
                if not svc:
                    skipped += 1
                    continue
                try:
                    url = self._get_service_url(svc)
                    api_key = self._get_service_api_key(svc)
                    user_id = self._get_service_user_id(svc)
                    client = EmbyClient(url, api_key, svc, user_id=user_id, use_proxy=self._use_proxy)
                    if client.lock_cast_for_item(item_id):
                        locked += 1
                        # v1.2.4: 修复锁定时间戳精度问题
                        # 原来用 processed.get(key) 的时间戳匹配历史记录，
                        # 但写入和锁定时生成的时间戳精度不同，永远匹配不上
                        # 改为直接用 item_id 匹配
                        with self._state_lock:
                            for h in self._history:
                                if h.get("item_id") == item_id:
                                    h["cast_locked"] = True
                    else:
                        failed += 1
                except Exception:
                    failed += 1
            msg = f"锁定完成: 成功 {locked}, 跳过 {skipped}, 失败 {failed}"
            logger.info(msg)
            self._save_state()
            return {"success": True, "message": msg}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_refresh_llm(self, **kwargs):
        try:
            old_model = getattr(self._llm, 'model', '未初始化') if self._llm else '未初始化'
            self._init_llm()
            if self._translator:
                self._translator.llm = self._llm
            new_model = getattr(self._llm, 'model', '未配置') if self._llm else '未配置'
            logger.info(f"LLM 刷新完成: {old_model} → {new_model}")
            return {"success": True, "message": f"LLM 已刷新: {old_model} → {new_model}"}
        except Exception as e:
            logger.error(f"刷新 LLM 失败: {e}")
            return {"success": False, "message": str(e)}

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
        # v1.3.11: 区分首次初始化 vs 配置热更新，避免运行时重置导致扫描崩溃/缓存丢失
        is_first_init = not hasattr(self, '_state_lock')
        if is_first_init:
            # v1.2.8: 所有可变运行时状态在实例化时初始化，彻底解决类变量污染问题
            # 之前使用类级别默认值在 MoviePilot 热加载时会导致多个实例共享同一份状态
            self._ms_helper = None
            self._emby = None
            self._llm = None
            self._translator = None
            # v1.3.13: D方案回归修复 - 防止重复启动后台初始化线程
            self._startup_background_started = False
            self._stop_requested = False
            self._force_refresh = False
            self._name_cache = {}
            self._role_cache = {}
            self._processed = {}
            self._history = []
            self._failed = []
            self._live_log = []
            self._is_running = False
            self._is_paused = False
            self._last_run_time = None
            self._last_save_time = None  # v1.3.2: 配置最后保存时间
            # v1.3.2: 线程生命周期 - 用 Event 安全通知 + 保存线程引用
            self._scan_thread = None
            self._stop_event = threading.Event()
            self._pause_event = threading.Event()  # 用 Event.wait() 实现真正暂停
            # 线程锁也必须实例化（否则多实例共享同一把锁）
            self._state_lock = threading.Lock()
            self._scan_lock = threading.Lock()
            # v1.3.11: 处理并发冲突锁（scan worker vs webhook worker）
            self._process_lock = threading.Lock()
            # v1.2.7: 断点续扫状态 - 完整结构
            # {"server_id": "...", "library_id": "...", "page": 0, "index": 0, "total": 0, "time": ts}
            self._scan_cursor = None

            # 进度追踪
            # v1.3.0: 统一扫描状态 - 单一数据源
            # 所有 set/get 都走 self._scan_status[key]
            # UI 端通过 _build_scan_status() 读取（带 percent/elapsed 计算）
            self._scan_status = {
                "running": False,
                "paused": False,
                "total": 0,
                "done": 0,
                "current_title": "",
                "current_library": "",
                "current_step": "",
                "step_status": {
                    "获取Emby": self.STEP_PENDING,
                    "提取演员": self.STEP_PENDING,
                    "AI翻译": self.STEP_PENDING,
                    "写回": self.STEP_PENDING,
                },
                "servers_total": 0,
                "servers_done": 0,
            }
            self._progress_step_start_time = time.time()

            # 缓存命中率统计
            self._cache_hits = 0
            self._cache_misses = 0

            # v1.2.8: Webhook 状态追踪 - 实例化
            self._webhook_received = 0
            self._webhook_processed = 0
            self._webhook_failed = 0
            self._webhook_last_time = None
            self._webhook_last_event = ""
            self._webhook_error = ""
            # v1.3.9: Webhook 延迟调度队列 - {item_id: {"execute_at": float, "server_id": str, "delay": int}}
            # 单 Worker 线程消费，重复事件 debounce（重置 execute_at）
            self._webhook_schedule: Dict[str, Dict[str, Any]] = {}
            self._webhook_worker_thread: Optional[threading.Thread] = None
            self._webhook_worker_event = threading.Event()
            self._webhook_lock = threading.Lock()
            # v1.3.8: 通知聚合队列 - {series_name: [item_info, ...]}
            self._notification_queue: Dict[str, List[Dict[str, Any]]] = {}
            self._notification_flush_timer: Optional[threading.Timer] = None
            self._notification_lock = threading.Lock()

            # 状态持久化路径
            self._state_file = ""

            # v1.2.8: 接管底层 logger - 把 EmbyClient/LLMClient/Translator 的日志也接入实时日志队列
            self._install_log_bridge()

            self._load_state()

        if config:
            self._load_config(config)

        # ============================================================
        # 阶段 1: 扫描生命周期操作（stop / pause / resume）
        # ============================================================
        # v1.3.11: 处理「停止扫描」开关 - 先写缓存再停止，避免进度丢失
        if getattr(self, '_run_stop_scan', False):
            logger.info("检测到「停止扫描」开关，先保存缓存再停止...")
            self._run_stop_scan = False
            self.update_config(self._dump_config())
            self._save_state()
            if self._is_running:
                self.stop_service()

        # v1.3.11: 处理「暂停任务」开关 - 扫描运行时可用
        if getattr(self, '_run_pause', False):
            self._run_pause = False
            self.update_config(self._dump_config())
            if self._is_running:
                if self._is_paused:
                    logger.info("检测到「恢复任务」开关")
                    self._is_paused = False
                    self._scan_status["paused"] = False
                    if hasattr(self, "_pause_event") and self._pause_event is not None:
                        self._pause_event.clear()
                    logger.info("▶ 扫描已恢复")
                else:
                    logger.info("检测到「暂停任务」开关")
                    self._is_paused = True
                    self._scan_status["paused"] = True
                    if hasattr(self, "_pause_event") and self._pause_event is not None:
                        self._pause_event.set()
                    logger.info("⏸ 扫描已暂停")

        # v1.3.6: 检查插件是否被禁用，如果是则停止正在运行的扫描
        if not self._enabled and self._is_running:
            logger.info("插件已禁用，正在停止扫描...")
            # 调用 stop_service 强制停止扫描线程（包括关闭 LLM 连接）
            self.stop_service()

        # ============================================================
        # 阶段 2: 扫描运行时也能执行的操作（不重建 translator）
        # ============================================================
        if getattr(self, '_run_refresh_llm', False):
            logger.info("检测到「刷新 LLM 客户端」开关")
            self._run_refresh_llm = False
            self.update_config(self._dump_config())
            self._api_refresh_llm()

        # ============================================================
        # 阶段 3: 扫描运行中时直接 return，防止重建 translator 导致崩溃
        # ============================================================
        if self._is_running:
            logger.info("扫描正在运行，配置将在下次扫描时生效")
            # v1.3.11: 扫描运行时保留现有翻译器和 LLM，不重建
            return

        # v1.3.12 (D方案): 不再在 init_plugin 里同步初始化 LLM/Translator/Emby
        # 这些耗时操作全部推迟到扫描线程内部（见 _scan_worker 开头）。
        # 这样保存接口只负责"点火"，立即返回，前端弹窗不会长时间卡住。
        # 需要注意：webhook 翻译需要 LLM，因此仅在 webhook 事件到达且未就绪时，
        # 才在 webhook worker 内做一次惰性初始化（见 handle_webhook / _process_item）。

        # ============================================================
        # 阶段 4: 扫描未运行时才能执行的操作
        # ============================================================
        if self._run_clear_cache:
            # v1.3.3: 改为「单独清空缓存」- 只清缓存+已处理记录，不再自动重扫
            logger.info("检测到「清空缓存」开关")
            self._run_clear_cache = False
            self.update_config(self._dump_config())
            self.clear_cache()

        if self._run_scan:
            logger.info("检测到「立即扫描」开关")
            self._run_scan = False
            self.update_config(self._dump_config())
            # v1.3.12 (D方案): 后台线程启动，保存接口立即返回不阻塞
            self._start_scan_thread(True)

        if self._run_lock_cast:
            logger.info("检测到「批量补锁定」开关")
            self._run_lock_cast = False
            self.update_config(self._dump_config())
            threading.Thread(target=self._api_lock_cast, daemon=True).start()

        if getattr(self, '_run_retry_failed', False):
            logger.info("检测到「重试失败任务」开关")
            self._run_retry_failed = False
            self.update_config(self._dump_config())
            threading.Thread(target=self._api_retry_failed, daemon=True).start()

        if self._onlyonce:
            self._onlyonce = False
            self._force_refresh = False
            self.update_config(self._dump_config())
            # v1.3.12 (D方案): 后台线程启动，避免阻塞配置保存
            self._start_scan_thread(True)

        # ============================================================
        # v1.3.13 (D方案回归修复): 后台线程尽早初始化 Emby/LLM
        # 启用插件但尚未开始扫描时，_emby/_llm 都是 None，
        # 仪表盘会误报"未启动/Emby 未连接/LLM 未配置"。
        # 这里用一个后台守护线程（非阻塞）尽早填充，让 UI 正确显示，
        # 同时不阻塞保存接口。扫描线程内的惰性初始化仍保留作为兜底。
        # ============================================================
        if self._enabled and not self._startup_background_started:
            self._startup_background_started = True
            threading.Thread(target=self._startup, daemon=True).start()

    def _load_config(self, config: dict):
        self._enabled = bool(config.get(constants.CFG_ENABLED, False))
        self._onlyonce = bool(config.get(constants.CFG_ONCE, False))
        self._force_refresh = False
        self._libraries = list(config.get(constants.CFG_LIBRARIES, []))
        self._prompt_template = str(config.get(constants.CFG_PROMPT_TEMPLATE) or constants.DEFAULT_PROMPT)
        self._translate_all = bool(config.get(constants.CFG_TRANSLATE_ALL, False))
        self._translate_role = bool(config.get(constants.CFG_TRANSLATE_ROLE, True))
        self._translate_actor = bool(config.get(constants.CFG_TRANSLATE_ACTOR, True))
        self._translate_director = bool(config.get(constants.CFG_TRANSLATE_DIRECTOR, False))
        self._translate_writer = bool(config.get(constants.CFG_TRANSLATE_WRITER, False))
        self._translate_producer = bool(config.get(constants.CFG_TRANSLATE_PRODUCER, False))

        if self._translate_all:
            self._translate_role = True
            self._translate_actor = True
            self._translate_director = True
            self._translate_writer = True
            self._translate_producer = True

        self._max_people_per_title = int(config.get(constants.CFG_MAX_PEOPLE_PER_TITLE, constants.DEFAULT_MAX_PEOPLE))
        self._max_people_per_batch = int(config.get(constants.CFG_MAX_PEOPLE_PER_BATCH, constants.DEFAULT_BATCH_SIZE))
        self._batch_titles = int(config.get(constants.CFG_BATCH_TITLES, constants.DEFAULT_BATCH_TITLES))
        self._overwrite_chinese = bool(config.get(constants.CFG_OVERWRITE_CHINESE, False))
        self._delay = int(config.get(constants.CFG_DELAY, constants.DEFAULT_DELAY))
        self._lock_cast = bool(config.get(constants.CFG_LOCK_CAST, False))
        self._run_scan = bool(config.get(constants.CFG_RUN_SCAN, False))
        self._run_lock_cast = bool(config.get(constants.CFG_RUN_LOCK_CAST, False))
        self._run_clear_cache = bool(config.get(constants.CFG_RUN_CLEAR_CACHE, False))
        self._run_stop_scan = bool(config.get(constants.CFG_RUN_STOP_SCAN, False))
        self._run_retry_failed = bool(config.get(constants.CFG_RUN_RETRY_FAILED, False))
        self._run_refresh_llm = bool(config.get(constants.CFG_RUN_REFRESH_LLM, False))
        self._run_pause = bool(config.get(constants.CFG_RUN_PAUSE, False))
        self._llm_base_url = str(config.get(constants.CFG_LLM_BASE_URL, ""))
        self._llm_api_key = str(config.get(constants.CFG_LLM_API_KEY, ""))
        self._llm_model = str(config.get(constants.CFG_LLM_MODEL, ""))
        self._llm_timeout = int(config.get(constants.CFG_LLM_TIMEOUT, constants.DEFAULT_LLM_TIMEOUT))
        # v1.3.1: 代理可配置 - 默认 False
        self._use_proxy = bool(config.get(constants.CFG_USE_PROXY, constants.DEFAULT_USE_PROXY))
        self._webhook_delay = int(config.get(constants.CFG_WEBHOOK_DELAY, constants.DEFAULT_WEBHOOK_DELAY))
        self._notify_on_complete = bool(config.get(constants.CFG_NOTIFY_ON_COMPLETE, False))

    def _dump_config(self) -> dict:
        if self._translate_all:
            self._translate_role = True
            self._translate_actor = True
            self._translate_director = True
            self._translate_writer = True
            self._translate_producer = True

        return {
            constants.CFG_ENABLED: self._enabled,
            constants.CFG_ONCE: self._onlyonce,
            constants.CFG_LIBRARIES: self._libraries,
            constants.CFG_PROMPT_TEMPLATE: self._prompt_template or constants.DEFAULT_PROMPT,
            constants.CFG_TRANSLATE_ACTOR: self._translate_actor,
            constants.CFG_TRANSLATE_DIRECTOR: self._translate_director,
            constants.CFG_TRANSLATE_WRITER: self._translate_writer,
            constants.CFG_TRANSLATE_PRODUCER: self._translate_producer,
            constants.CFG_TRANSLATE_ALL: self._translate_all,
            constants.CFG_TRANSLATE_ROLE: self._translate_role,
            constants.CFG_MAX_PEOPLE_PER_TITLE: self._max_people_per_title,
            constants.CFG_MAX_PEOPLE_PER_BATCH: self._max_people_per_batch,
            constants.CFG_BATCH_TITLES: self._batch_titles,
            constants.CFG_OVERWRITE_CHINESE: self._overwrite_chinese,
            constants.CFG_DELAY: self._delay,
            constants.CFG_LOCK_CAST: self._lock_cast,
            constants.CFG_RUN_SCAN: self._run_scan,
            constants.CFG_RUN_LOCK_CAST: self._run_lock_cast,
            constants.CFG_RUN_CLEAR_CACHE: self._run_clear_cache,
            constants.CFG_RUN_STOP_SCAN: self._run_stop_scan,
            constants.CFG_RUN_RETRY_FAILED: self._run_retry_failed,
            constants.CFG_RUN_REFRESH_LLM: self._run_refresh_llm,
            constants.CFG_RUN_PAUSE: self._run_pause,
            constants.CFG_LLM_BASE_URL: self._llm_base_url,
            constants.CFG_LLM_API_KEY: self._llm_api_key,
            constants.CFG_LLM_MODEL: self._llm_model,
            constants.CFG_LLM_TIMEOUT: self._llm_timeout,
            constants.CFG_USE_PROXY: self._use_proxy,
            constants.CFG_WEBHOOK_DELAY: self._webhook_delay,
            constants.CFG_NOTIFY_ON_COMPLETE: self._notify_on_complete,
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
            logger.info(f"检测到 {len(emby_services)} 个 Emby 服务")
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

    def _get_library_options(self) -> List[Dict[str, str]]:
        options = []
        try:
            services = self._get_all_emby_services()
            for svc in services:
                sname = getattr(svc, 'name', '服务器')
                surl = self._get_service_url(svc)
                try:
                    client = EmbyClient(surl, self._get_service_api_key(svc), svc,
                                        user_id=self._get_service_user_id(svc),
                                        use_proxy=self._use_proxy)
                    libs = client.get_libraries()
                    for lib in libs:
                        options.append({
                            "title": f"【{sname}】{lib.get('Name')} ({lib.get('Type')})",
                            "value": f"{self._get_server_identifier(svc)}:{lib.get('Id')}"
                        })
                except Exception as e:
                    logger.warning(f"获取服务器 {sname} 媒体库失败: {e}")
        except Exception as e:
            logger.error(f"获取媒体库列表失败: {e}")
        return options

    # ============================================================
    # 启动 / LLM 初始化
    # ============================================================
    def _startup(self):
        try:
            self._ms_helper = MediaServerHelper()
            services = self._get_all_emby_services()
            if not services:
                logger.warning("未检测到可用的 Emby 服务器")
                return
            svc = services[0]
            self._emby = EmbyClient(self._get_service_url(svc), self._get_service_api_key(svc), svc,
                                    user_id=self._get_service_user_id(svc),
                                    use_proxy=self._use_proxy)
            self._init_llm()
            # v1.3.2: 明确打印 LLM/Translator 初始化状态 - 扫描前就能看到
            if self._llm is None:
                logger.warning("⚠️ LLM 客户端初始化失败，扫描时无法翻译")
            else:
                logger.info(f"✅ LLM 初始化成功: model={self._llm.model}")
            self._translator = PeopleTranslator(
                llm_client=self._llm,
                name_cache=self._name_cache,
                role_cache=self._role_cache,
                state_lock=self._state_lock,
                plugin=self,
            )
            if self._translator is None:
                logger.error("❌ Translator 初始化失败")
            else:
                logger.info("✅ Translator 初始化成功")
            logger.info(f"EmbyPeopleLocalize v{self.plugin_version} 启动完成")
        except Exception as e:
            logger.error(f"插件启动失败: {e}\n{traceback.format_exc()}")

    def _init_llm(self):
        try:
            base_url = self._llm_base_url or getattr(settings, 'LLM_BASE_URL', '')
            api_key = self._llm_api_key or getattr(settings, 'LLM_API_KEY', '')
            model = self._llm_model or getattr(settings, 'LLM_MODEL', '')
            timeout = self._llm_timeout or constants.DEFAULT_LLM_TIMEOUT
            self._llm = LLMClient(
                base_url=base_url,
                api_key=api_key,
                model=model,
                prompt_template=self._prompt_template or constants.DEFAULT_PROMPT,
                timeout=timeout,
            )
            logger.info(f"LLM 客户端初始化成功: {self._llm.model}")
        except Exception as e:
            logger.error(f"LLM 初始化失败: {e}")
            self._llm = None

    # ============================================================
    # 扫描引擎
    # ============================================================
    def _scan_worker(self, force: bool = False):
        # v1.2.5: 防止 _is_running 重复启动
        # 调用方（_api_scan / init_plugin）已加锁并设置 _is_running=True
        # 这里只在 init_plugin 直接调用时做兜底检查
        if not force and self._is_running:
            logger.info("扫描已在运行中")
            return

        # 如果 init_plugin 直接调用（未通过 _api_scan），需要在这里设置状态
        with self._scan_lock:
            if self._is_running:
                logger.info("扫描已在运行中（_scan_lock 兜底）")
                return
            self._is_running = True
            self._scan_status["running"] = True  # v1.3.0: 同步状态
            self._stop_requested = False

        self._is_paused = False
        self._last_run_time = time.time()
        # v1.3.0: 同步 _scan_status - 单一数据源
        self._scan_status["running"] = True
        self._scan_status["paused"] = False
        self._cache_hits = 0
        self._cache_misses = 0
        total_translated = total_failed = 0

        try:
            logger.info("=" * 50)
            # v1.3.12 (D方案): LLM/Translator 初始化从 init_plugin 挪到扫描线程内
            # 让保存接口只负责"点火"，初始化 LLM（可能慢）放到后台线程。
            if not self._llm or not self._translator:
                self._startup()
                if not self._llm or not self._translator:
                    logger.error("LLM 或 Translator 初始化失败，无法开始扫描")
                    self._is_running = False
                    self._scan_status["running"] = False
                    self._save_state()
                    return
            logger.info("开始扫描 Emby 演职人员...")
            services = self._get_all_emby_services()
            if not services:
                logger.warning("无可用 Emby 服务器")
                self._is_running = False
                self._save_state()
                return

            target_libs = self._libraries or []
            all_tasks = []

            for svc in services:
                if self._stop_requested:
                    break
                skey = self._get_server_identifier(svc)
                client = EmbyClient(self._get_service_url(svc), self._get_service_api_key(svc), svc,
                                    user_id=self._get_service_user_id(svc),
                                    use_proxy=self._use_proxy)
                libs = client.get_libraries()
                for lib in libs:
                    lib_id = str(lib.get("Id", ""))
                    full_key = f"{skey}:{lib_id}"
                    if target_libs and full_key not in target_libs:
                        continue
                    lib_type = (lib.get("Type", "") or "").lower()
                    all_tasks.append((svc, skey, client, lib_id, lib.get("Name", "?"), lib_type))

            self._scan_status["total"] = len(all_tasks)
            logger.info(f"共 {len(all_tasks)} 个媒体库待扫描")

            for svc, skey, client, lib_id, lib_name, lib_type in all_tasks:
                if self._stop_requested:
                    logger.info("扫描已请求停止")
                    break
                self._scan_status["current_library"] = f"[{getattr(svc,'name','?')}] {lib_name}"
                logger.info(f"📂 扫描媒体库: {self._scan_status['current_library']}")
                t, f = self._scan_library(client, svc, skey, lib_id, lib_name, lib_type)
                total_translated += t
                total_failed += f
                self._scan_status["done"] = self._scan_status.get("done", 0) + 1
                self._auto_save()

            logger.info(f"扫描完成: 翻译 {total_translated} 条, 失败 {total_failed} 条")

            if self._notify_on_complete:
                try:
                    hit_rate = round(self._cache_hits / max(self._cache_hits + self._cache_misses, 1) * 100, 1)
                    self.post_message(
                        mtype=NotificationType.Manual,
                        title=self.plugin_name,
                        text=f"扫描完成：翻译 {total_translated} 条，失败 {total_failed} 条，缓存命中率 {hit_rate}%"
                    )
                except Exception as e:
                    logger.warning(f"发送通知失败: {e}")
        except Exception as e:
            logger.error(f"扫描异常: {e}\n{traceback.format_exc()}")
        finally:
            # v1.3.2: 区分正常完成 vs 停止
            # - 正常完成：清空 cursor
            # - 停止：保留 cursor，可续扫
            was_stopped = self._stop_requested
            self._is_running = False
            self._is_paused = False
            self._stop_requested = False
            # v1.3.0: 同步 _scan_status - 单一数据源
            self._scan_status["running"] = False
            self._scan_status["paused"] = False
            self._scan_status["current_title"] = ""
            self._scan_status["current_library"] = ""
            if not was_stopped:
                # 正常完成才清空 cursor；停止时 cursor 已在外层 break 时保存
                self._scan_cursor = None
            self._save_state()

    def _scan_library(self, client: EmbyClient, svc: ServiceInfo, skey: str,
                      lib_id: str, lib_name: str, lib_type: str = "") -> Tuple[int, int]:
        translated = failed = 0
        skipped = 0
        page_size = 50
        total_estimated = 0
        page_index = 0
        item_index = 0

        # v1.2.5: 根据媒体库类型决定是否递归
        lib_type_lower = (lib_type or "").lower()
        recursive = lib_type_lower in ("tvshows", "mixed", "tv")

        # v1.2.8: 断点续扫 - 从 cursor 恢复 server_id/library_id/page/index/total
        if self._scan_cursor and self._scan_cursor.get("library_id") == lib_id and \
                self._scan_cursor.get("server_id") == skey:
            page_index = int(self._scan_cursor.get("page", 0) or 0)
            item_index = int(self._scan_cursor.get("index", 0) or 0)
            total_estimated = int(self._scan_cursor.get("total", 0) or 0)
            logger.info(f"从断点继续扫描 [{lib_name}]: 第{page_index}页 第{item_index}项")
            self._push_log("INFO", f"断点续扫: {lib_name} 从第{page_index}页第{item_index}项继续")
        start = page_index * page_size

        # 先获取总数
        try:
            first_data = client.fetch_items_page(lib_id, limit=1, start_index=0, recursive=recursive)
            total_estimated = int((first_data or {}).get("TotalRecordCount", 0) or 0)
        except Exception:
            pass

        self._scan_status["total"] = total_estimated
        self._scan_status["current_library"] = lib_name

        page_counter = page_index
        while True:
            # v1.3.2: 暂停等待 - 用 Event.wait 替代 sleep 轮询
            # Event 被 set 后 wait() 立即返回
            if self._is_paused and not self._stop_requested:
                logger.info("⏸ 扫描已暂停，等待恢复...")
                self._push_log("INFO", "扫描已暂停")
                # wait 直到 resume 时 clear() 返回
                if hasattr(self, "_pause_event") and self._pause_event is not None:
                    self._pause_event.wait(timeout=0.5)
                else:
                    time.sleep(0.5)
                # 检查是否在暂停期间被停止
                if self._stop_requested:
                    break
                # 退出暂停 - 双重检查 _is_paused（resume 时已清）
                if not self._is_paused:
                    logger.info("▶ 扫描已恢复")
                    self._push_log("INFO", "扫描已恢复")
            if self._stop_requested:
                break
            try:
                data = client.fetch_items_page(lib_id, limit=page_size, start_index=start, recursive=recursive)
                items = (data or {}).get("Items", []) or []
                if not items:
                    break

                # 更新总数
                if not total_estimated:
                    total_estimated = int((data or {}).get("TotalRecordCount", 0) or 0)
                    self._scan_status["total"] = total_estimated

                start_idx_in_page = item_index if page_counter == page_index else 0
                # v1.3.11: 跨剧集批处理 - 每 _batch_titles 个剧集打包一次发给 AI
                batch_size = max(1, int(getattr(self, "_batch_titles", 10)))
                pending: List[dict] = []
                pending_indices: List[int] = []
                for i in range(start_idx_in_page, len(items)):
                    if self._stop_requested:
                        # v1.3.2: 停止时保存 cursor 包含当前 item 位置
                        self._scan_cursor = {
                            "server_id": skey,
                            "library_id": lib_id,
                            "library_name": lib_name,
                            "page": page_counter,
                            "index": i,
                            "total": total_estimated,
                            "time": time.time(),
                        }
                        self._save_state()
                        logger.info(f"⏹ 已保存断点: [{lib_name}] 第{page_counter}页第{i}项")
                        break
                    item = items[i]
                    self._scan_status["done"] = start + i + 1
                    self._scan_status["current_title"] = item.get("Name", "?")
                    pending.append(item)
                    pending_indices.append(i)
                    # 攒够 batch_size 个就批量处理
                    if len(pending) >= batch_size:
                        try:
                            with self._process_lock:
                                t, f, _sk = self._process_items_batch(client, svc, skey, pending, lib_name)
                            translated += t
                            failed += f
                            if t == 0 and f == 0:
                                skipped += len(pending)
                        except Exception as e:
                            logger.error(f"批量处理异常: {e}")
                            failed += len(pending)
                            for it in pending:
                                item_id = str(it.get("Id", ""))
                                title = it.get("Name", "?")
                                self._record_failure(item_id, skey, title, f"批量处理异常: {e}")
                        # 批量后实时保存状态（_auto_save 也会兜底）
                        self._auto_save()
                        pending = []
                        pending_indices = []

                # 处理本页不足 batch_size 的剩余剧集
                if pending:
                    try:
                        with self._process_lock:
                            t, f, _sk = self._process_items_batch(client, svc, skey, pending, lib_name)
                        translated += t
                        failed += f
                        if t == 0 and f == 0:
                            skipped += len(pending)
                    except Exception as e:
                        logger.error(f"批量处理异常: {e}")
                        failed += len(pending)
                        for it in pending:
                            item_id = str(it.get("Id", ""))
                            title = it.get("Name", "?")
                            self._record_failure(item_id, skey, title, f"批量处理异常: {e}")
                    self._auto_save()

                # v1.2.8: 每页处理完后保存完整 cursor
                start += page_size
                page_counter += 1
                item_index = 0
                self._scan_cursor = {
                    "server_id": skey,
                    "library_id": lib_id,
                    "library_name": lib_name,
                    "page": page_counter,
                    "index": item_index,
                    "total": total_estimated,
                    "time": time.time(),
                }
                self._save_state()

                if len(items) < page_size:
                    break
            except Exception as e:
                logger.error(f"分页获取失败: {e}")
                break

        if translated == 0 and failed == 0:
            logger.info(f"媒体库 [{lib_name}] 扫描完成：共 {skipped} 条，均无需翻译")
        else:
            logger.info(f"媒体库 [{lib_name}] 扫描完成: 翻译 {translated}, 失败 {failed}, 跳过 {skipped}")
        return translated, failed

    def _fetch_full_item(self, client: EmbyClient, item: dict) -> Optional[dict]:
        """v1.3.11: 提取单条目 - 优先使用 list 接口返回的 People，没有则按需补全详情

        返回完整的 People 列表（不修改原 item）。
        """
        item_id = str(item.get("Id", ""))
        people = item.get("People")
        if people:
            return people
        full_item = client.fetch_item(item_id)
        if not full_item:
            return None
        return full_item.get("People", []) or []

    def _build_display_title(self, item: dict, full_item: Optional[dict] = None) -> Tuple[str, str, Any, Any, Any, str]:
        """v1.3.11: 从 item 构造展示标题/剧名/季/集 - 集中逻辑便于复用

        返回: (display_title, series_name, season_num, episode_num, year, item_type)
        """
        title = item.get("Name", "")
        year = item.get("ProductionYear") or (item.get("PremiereDate", "")[:4] if item.get("PremiereDate") else "")
        item_type = item.get("Type", "")
        display_title = title
        series_name = ""
        season_num = None
        episode_num = None
        src = full_item if full_item else item
        if item_type == "Episode":
            series_name = src.get("SeriesName", "") or series_name
            season_num = src.get("ParentIndexNumber", season_num)
            if season_num is None:
                season_num = src.get("SeasonNumber")
            episode_num = src.get("IndexNumber", episode_num)
            if episode_num is None:
                episode_num = src.get("EpisodeNumber")
            if season_num is not None and episode_num is not None:
                display_title = f"{series_name} 第{season_num}季 第{episode_num}集"
            elif series_name:
                display_title = series_name
        elif item_type == "Series":
            series_name = title
            season_num = src.get("ChildCount") or src.get("SeasonCount")
        return display_title, series_name, season_num, episode_num, year, item_type

    def _extract_translatable_terms(self, people: List[dict]) -> Tuple[List[str], List[str]]:
        """v1.3.11: 纯函数 - 从 People 列表中按翻译配置筛出待翻译的人名/角色名

        已应用繁简过滤、类型过滤、限制数量。供 _process_item 和跨剧集批处理共用。
        返回: (name_terms, role_terms)
        """
        name_terms = []
        role_terms = []
        for p in people:
            ptype = p.get("Type", "Actor")
            name = p.get("Name", "").strip()
            role = p.get("Role", "").strip()

            name_type_ok = True
            if not self._translate_all:
                name_type_ok = {
                    "Actor": self._translate_actor,
                    "Director": self._translate_director,
                    "Writer": self._translate_writer,
                    "Producer": self._translate_producer,
                    "VoiceActor": self._translate_actor,
                }.get(ptype, False)

            if name and (self._translate_all or name_type_ok):
                if self._looks_like_chinese(name) and not self._overwrite_chinese:
                    continue
                name_terms.append(name)

            if role and (self._translate_role or self._translate_all):
                if self._looks_like_chinese(role) and not self._overwrite_chinese:
                    continue
                role_terms.append(role)

        # 去重并限制数量
        name_terms = list(dict.fromkeys(name_terms))[:self._max_people_per_title]
        role_terms = list(dict.fromkeys(role_terms))[:self._max_people_per_title - len(name_terms)]
        return name_terms, role_terms

    def _process_item(self, client: EmbyClient, svc: ServiceInfo, skey: str,
                      item: dict, lib_name: str = "",
                      pre_extracted: Optional[Dict[str, Any]] = None) -> Tuple[int, int]:
        """v1.3.11: 处理单个条目。

        pre_extracted (跨剧集批处理传入):
          {
            "name_translations": {...}, "role_translations": {...},
            "people": [...],   # 已 fetch 完整的 People
            "display_title": str, "year": Any, "item_type": str,
            "series_name": str, "season_num": Any, "episode_num": Any,
          }
        不传时按单剧集模式：自己 fetch / 调 LLM。
        """
        # v1.3.11-fix: 单剧集模式才因 stop 跳过；pre_extracted 模式表示翻译已完成，应直接写回
        if not pre_extracted and self._stop_requested:
            return 0, 0

        # v1.2.8: 初始化步骤状态（用于 UI 扫描详情）
        self._reset_steps()
        self._set_step("获取Emby")  # 标记"获取Emby"为进行中

        item_id = str(item.get("Id", ""))
        title = item.get("Name", "")
        item_type = item.get("Type", "")

        # v1.3.11: 跨剧集批处理时复用预提取的数据，避免重复 LLM 调用
        if pre_extracted:
            display_title = pre_extracted["display_title"]
            year = pre_extracted["year"]
            series_name = pre_extracted["series_name"]
            season_num = pre_extracted["season_num"]
            episode_num = pre_extracted["episode_num"]
            people = pre_extracted["people"]
            name_translations = pre_extracted["name_translations"]
            role_translations = pre_extracted["role_translations"]
            all_translations = {}
            all_translations.update(name_translations)
            all_translations.update(role_translations)
            self._scan_status["current_title"] = display_title
            self._set_step("获取Emby", self.STEP_DONE)
            self._set_step("提取演员", self.STEP_DONE)
            self._set_step("AI翻译", self.STEP_DONE)
            self._set_step("写回")

            if not all_translations:
                logger.info(f"[{item_id}] {display_title} ({year}) — 批次翻译未命中，跳过")
                self._set_step("写回", self.STEP_SKIPPED)
                return 0, 0

            new_people = self._translator.apply_translations(people, name_translations, role_translations)
            lock = self._lock_cast
            logger.info(f"正在写入 Emby ({len(all_translations)} 条翻译)...")
            updated = client.update_people(item_id, new_people, lock_cast=lock)
            key = f"{skey}:{item_id}"
            if updated > 0:
                self._post_translate_hook(key, display_title, year, item_id, all_translations, lock, lib_name,
                                          series_name=series_name, season_num=season_num, episode_num=episode_num, item_type=item_type)
                self._set_step("写回", self.STEP_DONE)
                return len(all_translations), 0
            else:
                logger.warning(f"[{item_id}] {display_title} ({year}) — 写回失败")
                self._set_step("写回", self.STEP_SKIPPED)
                return 0, 1

        key = f"{skey}:{item_id}"
        display_title, series_name, season_num, episode_num, year, _ = self._build_display_title(item)
        self._scan_status["current_title"] = display_title

        # v1.3.2: 提前检查停止 - 让用户点停止后能更快响应
        # 同时检查 _stop_requested 标志 + stop_event（双重保险）
        if self._stop_requested or (
            hasattr(self, "_stop_event") and self._stop_event is not None
            and self._stop_event.is_set()
        ):
            logger.info(f"[{item_id}] {display_title} — 已请求停止，跳过")
            self._finalize_steps(success=False)
            return 0, 0

        if not self._force_refresh and key in self._processed:
            logger.debug(f"[{item_id}] {display_title} ({year}) — 已处理，跳过")
            self._finalize_steps(success=True)
            return 0, 0

        # 优先使用列表中已含的 People，若无则按需获取详情
        people = item.get("People")
        if not people:
            full_item = client.fetch_item(item_id)
            if not full_item:
                logger.warning(f"[{item_id}] {display_title} — 无法获取完整条目")
                self._finalize_steps(success=False)
                return 0, 0
            title = full_item.get("Name", title)
            year = full_item.get("ProductionYear") or (full_item.get("PremiereDate", "")[:4] if full_item.get("PremiereDate") else year)
            people = full_item.get("People", []) or []
            # 重新读取季集信息（使用 Emby 实际字段）
            display_title, series_name, season_num, episode_num, year, _ = self._build_display_title(item, full_item)
            self._scan_status["current_title"] = display_title
        # v1.2.8: "获取Emby"步骤完成，进入"提取演员"
        self._set_step("获取Emby", self.STEP_DONE)
        self._set_step("提取演员")

        if not people:
            self._finalize_steps(success=True)
            return 0, 0

        # v1.3.11: 用纯函数提取待翻译词条
        name_terms, role_terms = self._extract_translatable_terms(people)

        if not name_terms and not role_terms:
            logger.info(f"[{item_id}] {display_title} ({year}) — 无需翻译")
            self._post_translate_hook(key, display_title, year, item_id, {}, self._lock_cast, lib_name, skipped=True,
                                  series_name=series_name, season_num=season_num, episode_num=episode_num, item_type=item_type)
            # v1.2.8: 步骤收尾（提取演员后无需翻译）
            self._set_step("提取演员", self.STEP_DONE)
            self._set_step("AI翻译", self.STEP_SKIPPED)
            self._set_step("写回", self.STEP_SKIPPED)
            return 0, 0

        logger.info(f"[{item_id}] {display_title} ({year}) — 待翻译 {len(name_terms) + len(role_terms)} 条")

        # v1.2.8: "提取演员"步骤完成，进入"AI翻译"
        self._set_step("提取演员", self.STEP_DONE)
        self._set_step("AI翻译")

        # 使用 Translator 处理
        if not self._translator or not self._llm:
            logger.warning("翻译器或 LLM 未初始化")
            self._finalize_steps(success=False)
            return 0, 1

        batch_size = self._max_people_per_batch
        # v1.3.3: 传 stop_check 回调 - 让 translator 在 LLM 调用之间检查停止信号
        # 不传则 translator 用自己的 stop_event（兜底）
        def _stop_check() -> bool:
            return self._stop_requested
        name_translations, role_translations = self._translator.translate_batch(
            title, year, name_terms, role_terms, batch_size,
            stop_check=_stop_check,
        )

        # v1.3.2: LLM 调用是最慢的环节，调用后立即检查停止 - 避免用户等很久
        if self._stop_requested:
            logger.info(f"[{item_id}] {display_title} — LLM 翻译完成但已请求停止，跳过写回")
            self._finalize_steps(success=False)
            return 0, 0

        # v1.2.4: 修复缓存命中率统计
        # 区分"真正命中缓存"vs"繁简转换命中"vs"LLM 新翻译命中"
        # 只有真正命中（字典中存在）才计为 cache_hits
        # v1.3.3: 防御 - 扫描中若 self._translator 被外部置 None（如 reload 插件/重新 init_plugin）
        # 立即停止扫描，避免后续访问 NoneType 抛错
        if self._translator is None:
            logger.warning(f"[{item_id}] {display_title} — 翻译器已失效（可能被重载），停止扫描")
            self._finalize_steps(success=False)
            return 0, 1
        for name in name_terms:
            if name in name_translations:
                # v1.3.4: 防御 - 同上，translator 失效立即停止
                if self._translator is None:
                    logger.warning(f"[{item_id}] {display_title} — 翻译器已失效，跳过缓存命中统计")
                    self._finalize_steps(success=False)
                    return 0, 1
                if self._translator.get_cached_name(name):
                    self._cache_hits += 1
                else:
                    # 是繁简转换或 LLM 新翻译的结果
                    self._cache_misses += 1
        for role in role_terms:
            if role in role_translations:
                # v1.3.4: 防御 - 重试时若 self._translator 被外部置 None，立即停止
                if self._translator is None:
                    logger.warning(f"[{item_id}] {display_title} — 翻译器已失效，跳过缓存命中统计")
                    self._finalize_steps(success=False)
                    return 0, 1
                if self._translator.get_cached_role(role):
                    self._cache_hits += 1
                else:
                    self._cache_misses += 1

        all_translations = {}
        all_translations.update(name_translations)
        all_translations.update(role_translations)

        # v1.2.8: "AI翻译"步骤完成，进入"写回"
        self._set_step("AI翻译", self.STEP_DONE)
        self._set_step("写回")

        if not all_translations:
            logger.info(f"[{item_id}] {display_title} ({year}) — 无有效翻译结果")
            self._set_step("写回", self.STEP_SKIPPED)
            return 0, 0

        new_people = self._translator.apply_translations(people, name_translations, role_translations)

        if self._stop_requested:
            logger.info("已请求停止，跳过写入")
            self._set_step("写回", self.STEP_SKIPPED)
            return 0, 0

        lock = self._lock_cast
        logger.info(f"正在写入 Emby ({len(all_translations)} 条翻译)...")
        updated = client.update_people(item_id, new_people, lock_cast=lock)

        if updated > 0:
            self._post_translate_hook(key, display_title, year, item_id, all_translations, lock, lib_name,
                                      series_name=series_name, season_num=season_num, episode_num=episode_num, item_type=item_type)
            self._set_step("写回", self.STEP_DONE)
            return len(all_translations), 0
        else:
            logger.warning(f"[{item_id}] {display_title} ({year}) — 写回失败")
            self._set_step("写回", self.STEP_SKIPPED)
            return 0, 1

    def _post_translate_hook(self, key, display_title, year, item_id, translations, lock, lib_name="",
                             skipped=False, series_name="", season_num=None, episode_num=None, item_type=""):
        with self._state_lock:
            self._processed[key] = datetime.now().isoformat()
            history_entry = {
                "time": datetime.now().isoformat(timespec='seconds'),
                "library": lib_name,
                "title": display_title,
                "year": year,
                "item_id": item_id,
                "n_trans": len(translations),
                "status": "跳过" if skipped else "成功",
                "cast_locked": lock,
                "item_type": item_type,
            }
            if series_name:
                history_entry["series_name"] = series_name
            if season_num is not None:
                history_entry["season_num"] = season_num
            if episode_num is not None:
                history_entry["episode_num"] = episode_num
            self._history.append(history_entry)
            if len(self._history) > constants.MAX_HISTORY:
                self._history = self._history[-constants.MAX_HISTORY:]
        if not skipped:
            logger.info(f"✅ [{item_id}] {display_title} ({year}) — 翻译 {len(translations)} 个, 锁定={lock}")
            for orig, trans in list(translations.items())[:3]:
                logger.info(f"    {orig} → {trans}")

    def _process_items_batch(self, client: EmbyClient, svc: ServiceInfo, skey: str,
                             items: List[dict], lib_name: str = "") -> Tuple[int, int, int]:
        """v1.3.11: 跨剧集批处理 - 把 N 个剧集的所有 People 打包发给 AI，失败自动降级为单剧集调用

        返回: (translated, failed, skipped)
        """
        if self._stop_requested or not items:
            return 0, 0, 0

        if not self._translator or not self._llm:
            logger.warning("翻译器或 LLM 未初始化")
            return 0, len(items), 0

        # v1.3.11-fix: 内部辅助函数 - 把已能完整翻译的剧集立即写回 Emby
        def _try_flush(collected_inner: Dict[str, Dict[str, Any]]) -> Tuple[int, int, List[str]]:
            """尝试写回已拿到完整翻译的剧集，返回 (translated, failed, removed_ids)"""
            t_flush = 0
            f_flush = 0
            removed: List[str] = []
            for item_id, info in list(collected_inner.items()):
                if self._stop_requested:
                    break
                name_terms = info["name_terms"]
                role_terms = info["role_terms"]
                name_translations: Dict[str, str] = {}
                role_translations: Dict[str, str] = {}
                complete = True
                for n in name_terms:
                    if n in cached_names:
                        name_translations[n] = cached_names[n]
                    elif n in zhconv_names:
                        name_translations[n] = zhconv_names[n]
                    elif n in llm_combined:
                        name_translations[n] = llm_combined[n]
                    else:
                        complete = False
                        break
                if complete:
                    for r in role_terms:
                        if r in cached_roles:
                            role_translations[r] = cached_roles[r]
                        elif r in zhconv_roles:
                            role_translations[r] = zhconv_roles[r]
                        elif r in llm_combined:
                            role_translations[r] = llm_combined[r]
                        else:
                            complete = False
                            break
                if not complete:
                    continue
                pre_extracted = {
                    "name_translations": name_translations,
                    "role_translations": role_translations,
                    "people": info["people"],
                    "display_title": info["display_title"],
                    "year": info["year"],
                    "item_type": info["item_type"],
                    "series_name": info["series_name"],
                    "season_num": info["season_num"],
                    "episode_num": info["episode_num"],
                }
                try:
                    t, f = self._process_item(client, svc, skey, info["item"], lib_name, pre_extracted=pre_extracted)
                    t_flush += t
                    f_flush += f
                    if f == 0:
                        removed.append(item_id)
                except Exception as e:
                    logger.error(f"批量即时写回失败 [{item_id}]: {e}")
                    f_flush += 1
            for item_id in removed:
                collected_inner.pop(item_id, None)
            return t_flush, f_flush, removed

        # ───── 阶段 1: 收集每个剧集的 people + 待翻译 terms ─────
        # structure: {item_id: {"item": item, "people": [...], "name_terms": [], "role_terms": [],
        #                       "display_title": str, "year": ..., "item_type": str,
        #                       "series_name": str, "season_num": ..., "episode_num": ...}}
        collected: Dict[str, Dict[str, Any]] = {}
        for item in items:
            item_id = str(item.get("Id", ""))
            key = f"{skey}:{item_id}"
            if not self._force_refresh and key in self._processed:
                continue

            # 优先 list 接口返回的 People，否则按需补全
            people = item.get("People")
            if not people:
                full_item = client.fetch_item(item_id)
                if not full_item:
                    continue
                people = full_item.get("People", []) or []
            if not people:
                continue

            name_terms, role_terms = self._extract_translatable_terms(people)
            if not name_terms and not role_terms:
                # 全部是中文或已缓存，无需翻译 - 直接 post_hook 标记跳过
                display_title, series_name, season_num, episode_num, year, item_type = self._build_display_title(item)
                self._post_translate_hook(key, display_title, year, item_id, {}, self._lock_cast, lib_name, skipped=True,
                                          series_name=series_name, season_num=season_num, episode_num=episode_num, item_type=item_type)
                continue

            display_title, series_name, season_num, episode_num, year, item_type = self._build_display_title(item)
            collected[item_id] = {
                "item": item,
                "people": people,
                "name_terms": name_terms,
                "role_terms": role_terms,
                "display_title": display_title,
                "year": year,
                "item_type": item_type,
                "series_name": series_name,
                "season_num": season_num,
                "episode_num": episode_num,
            }

        if not collected:
            return 0, 0, 0

        # ───── 阶段 2: 合并所有 terms（去重）一次性发 AI ─────
        # 跨剧集的特性：terms 来自不同 title，传统 translator 是单 title 接口
        # 这里直接调 llm.translate_terms 拿 dict（不依赖单 title 上下文）
        all_remaining_names: List[str] = []
        all_remaining_roles: List[str] = []
        for info in collected.values():
            all_remaining_names.extend(info["name_terms"])
            all_remaining_roles.extend(info["role_terms"])
        all_remaining_names = list(dict.fromkeys(all_remaining_names))
        all_remaining_roles = list(dict.fromkeys(all_remaining_roles))

        # v1.3.11: 先用 cache + 繁简转换预过滤，避免无意义的 LLM 调用
        cached_names: Dict[str, str] = {}
        cached_roles: Dict[str, str] = {}
        zhconv_names: Dict[str, str] = {}
        zhconv_roles: Dict[str, str] = {}
        for n in all_remaining_names:
            c = self._translator.get_cached_name(n)
            if c:
                cached_names[n] = c
                continue
            z = self._translator.try_zhconv(n)
            if z:
                zhconv_names[n] = z
        for r in all_remaining_roles:
            c = self._translator.get_cached_role(r)
            if c:
                cached_roles[r] = c
                continue
            z = self._translator.try_zhconv(r)
            if z:
                zhconv_roles[r] = z

        need_llm_names = [n for n in all_remaining_names if n not in cached_names and n not in zhconv_names]
        need_llm_roles = [r for r in all_remaining_roles if r not in cached_roles and r not in zhconv_roles]

        # v1.3.11: 跨剧集批调用 - title 用 "batch" 占位（AI 会根据 terms 自识别）
        llm_combined: Dict[str, str] = {}
        partial_failure = False
        translated = 0
        failed = 0
        if need_llm_names or need_llm_roles:
            all_to_translate = list(dict.fromkeys(need_llm_names + need_llm_roles))
            batch_size = self._max_people_per_batch
            logger.info(f"📦 跨剧集批翻译: {len(collected)} 个剧集, "
                        f"{len(all_to_translate)} 条待翻译（缓存命中 {len(cached_names) + len(cached_roles)}, "
                        f"繁简转换 {len(zhconv_names) + len(zhconv_roles)}）")
            try:
                # v1.3.11: 跨剧集场景无单一 title，使用 None 让 translator 走通用 prompt
                # 失败则记录 partial_failure，阶段 3 对缺失项单独降级
                for i in range(0, len(all_to_translate), batch_size):
                    if self._stop_requested:
                        logger.info("[批量] 扫描停止中，保留已完成的翻译结果")
                        break
                    batch = all_to_translate[i:i + batch_size]
                    # 合并人名+角色，用 batch 作为 title（会传给 prompt 上下文）
                    result = self._llm.translate_terms("batch", "", batch)
                    if isinstance(result, dict) and result:
                        llm_combined.update(result)
                        # 写入缓存（本批结果立即落盘）
                        for orig, trans in result.items():
                            if not trans or trans == orig:
                                continue
                            if orig in need_llm_names:
                                self._translator.set_cached_name(orig, trans)
                            if orig in need_llm_roles:
                                self._translator.set_cached_role(orig, trans)
                        # v1.3.11-fix: 每批 LLM 成功后，立即写回已经能完整翻译的剧集
                        t_flush, f_flush, flushed_ids = _try_flush(collected)
                        translated += t_flush
                        failed += f_flush
                        if flushed_ids:
                            logger.info(f"📝 本批后立即写回 {len(flushed_ids)} 个剧集（累计翻译 {translated} 条）")
                    elif not result:
                        # v1.3.11-fix: 部分失败，保留已拿到结果，后续对缺失项单独降级
                        logger.warning(f"[批量] 第{i // batch_size + 1}批返回空，标记为部分失败")
                        partial_failure = True
                        break
            except Exception as e:
                logger.error(f"[批量] 跨剧集翻译异常，标记为部分失败: {e}")
                partial_failure = True

        # ───── 阶段 3: 把翻译结果按剧集分发、写回 Emby ─────
        for item_id, info in collected.items():
            item = info["item"]
            key = f"{skey}:{item_id}"
            name_terms = info["name_terms"]
            role_terms = info["role_terms"]
            people = info["people"]

            # 合并缓存/繁简/LLM 三路结果
            name_translations: Dict[str, str] = {}
            role_translations: Dict[str, str] = {}
            for n in name_terms:
                if n in cached_names:
                    name_translations[n] = cached_names[n]
                elif n in zhconv_names:
                    name_translations[n] = zhconv_names[n]
                elif n in llm_combined:
                    name_translations[n] = llm_combined[n]
            for r in role_terms:
                if r in cached_roles:
                    role_translations[r] = cached_roles[r]
                elif r in zhconv_roles:
                    role_translations[r] = zhconv_roles[r]
                elif r in llm_combined:
                    role_translations[r] = llm_combined[r]

            # v1.3.11-fix: 优先使用已拿到的翻译结果直接写回（避免停止时丢弃已翻译内容）
            if name_translations or role_translations:
                pre_extracted = {
                    "name_translations": name_translations,
                    "role_translations": role_translations,
                    "people": people,
                    "display_title": info["display_title"],
                    "year": info["year"],
                    "item_type": info["item_type"],
                    "series_name": info["series_name"],
                    "season_num": info["season_num"],
                    "episode_num": info["episode_num"],
                }
                try:
                    t, f = self._process_item(client, svc, skey, item, lib_name, pre_extracted=pre_extracted)
                    translated += t
                    failed += f
                except Exception as e:
                    logger.error(f"批量写回失败 [{item_id}]: {e}")
                    failed += 1
                continue

            # 完全没有翻译结果：部分失败时降级单剧集；停止中则跳过
            if partial_failure and not self._stop_requested:
                try:
                    t, f = self._process_item(client, svc, skey, item, lib_name)
                    translated += t
                    failed += f
                except Exception as e:
                    logger.error(f"降级单剧集翻译失败 [{item_id}]: {e}")
                    failed += 1
                continue

            if self._stop_requested:
                logger.info(f"[{item_id}] {info['display_title']} — 扫描已停止，跳过未翻译条目")
                continue

            # 全部未命中（极端情况）
            logger.info(f"[{item_id}] {info['display_title']} — 批量未命中，写回跳过")
            self._post_translate_hook(key, info["display_title"], info["year"], item_id, {},
                                      self._lock_cast, lib_name, skipped=True,
                                      series_name=info["series_name"], season_num=info["season_num"],
                                      episode_num=info["episode_num"], item_type=info["item_type"])

        return translated, failed, 0

    @staticmethod
    def _looks_like_chinese(text: str) -> bool:
        for c in text:
            cp = ord(c)
            if 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF:
                return True
        return False

    # ============================================================
    # 缓存管理
    # ============================================================
    def clear_cache(self):
        with self._state_lock:
            self._name_cache.clear()
            self._role_cache.clear()
            self._processed.clear()
            self._history.clear()
            # v1.3.4: 同时清空失败任务 - 缓存清空后旧失败记录已无意义
            # 避免用户看到一堆 stale 的"get_cached_role"等已不相关的错误
            self._failed.clear()
            self._cache_hits = 0
            self._cache_misses = 0
        self._save_state()
        logger.info("所有缓存及失败任务已清空")

    def stop_service(self):
        """v1.3.2: 关闭插件时安全停止后台线程
        v1.3.3: 加强 - 1) 等待时间 10s → 30s，给 LLM 调用留出响应时间
                     2) 让 LLM 客户端置 None 强制让卡住的 LLM 调用快速抛错
                     3) daemon=True 兜底，MP 进程退出时线程会被强制结束
        """
        logger.info("收到插件停止信号，开始安全退出...")
        try:
            # 1. 触发停止事件
            self._stop_requested = True
            if hasattr(self, "_stop_event") and self._stop_event is not None:
                self._stop_event.set()
            # 2. 取消暂停（如果有）
            self._is_paused = False
            # 3. 保存当前状态（含 cursor）
            self._save_state()
            # 4. v1.3.6: 强制关闭 LLM HTTP 连接 - 让卡住的 LLM 调用立即抛异常退出
            try:
                if self._llm is not None and hasattr(self._llm, "close"):
                    self._llm.close()
                    logger.info("已强制关闭 LLM HTTP 连接，停止中的 LLM 调用将立即失败")
            except Exception as e:
                logger.debug(f"关闭 LLM 连接时异常: {e}")
            # 5. 停止 Webhook Worker 线程（v1.3.9）
            if hasattr(self, "_webhook_worker_event") and self._webhook_worker_event is not None:
                self._webhook_worker_event.set()
            wh_thread = getattr(self, "_webhook_worker_thread", None)
            if wh_thread and wh_thread.is_alive():
                logger.info("等待 Webhook Worker 退出 (timeout=5s)...")
                wh_thread.join(timeout=5.0)
                if wh_thread.is_alive():
                    logger.warning("Webhook Worker 5s 内未退出，daemon 兜底")
                else:
                    logger.info("Webhook Worker 已退出")
            self._webhook_worker_thread = None

            # 6. 等待扫描线程退出（3s - 避免阻塞 MP 主线程导致保存配置 504）
            thread = getattr(self, "_scan_thread", None)
            if thread and thread.is_alive():
                logger.info(f"等待扫描线程退出 (timeout=3s)...")
                thread.join(timeout=3.0)
                if thread.is_alive():
                    logger.warning("扫描线程 3s 内未退出，daemon 兜底（MP 进程结束时会被强制结束）")
                else:
                    logger.info("扫描线程已退出")
            self._scan_thread = None
            logger.info("插件停止完成")
        except Exception as e:
            logger.error(f"停止服务异常: {e}\n{traceback.format_exc()}")

    # ============================================================
    # Webhook 入库自动翻译（v1.0.0 完全重构）
    # ============================================================
    
    # Webhook 事件类型映射（Emby → MoviePilot 翻译触发）
    # v1.3.0: 改为不可变 tuple - 避免类级可变对象污染
    _WEBHOOK_ITEM_EVENT_TYPES = (
        "itemadded", "item.added", "library.new", "added", "newcontent",
        "itemupdated", "item.updated", "library.update",
    )
    # v1.3.7: 排除播放相关事件，避免播放时触发翻译
    # Emby Webhook 事件类型：PlaybackStart, PlaybackProgress, PlaybackStopped, SessionStarted 等
    _WEBHOOK_EXCLUDE_EVENT_TYPES = (
        "playback", "playstate", "session", "user", "notification",
        "playbackstart", "playbackprogress", "playbackstopped",
        "sessionstarted", "sessionended",
    )

    @eventmanager.register(EventType.WebhookMessage)
    def handle_webhook(self, event: Event):
        """
        监听 Emby Webhook 入库事件
        v1.2.5: 简化 Pydantic v2 解析（MoviePilot 仅支持 v2），移除冗余字段映射
        """
        try:
            event_data_obj = event.event_data
            if event_data_obj is None:
                return

            # v1.2.5: MoviePilot 仅使用 Pydantic v2，统一用 model_dump()
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

            # v1.2.5: 提取辅助方法已支持多种字段名（ItemId/item_id/Id），
            # 移除 v1.2.4 的字段重映射（属于冗余代码）

            # 早期提取 ItemId，没有 ItemId 直接跳过（减少噪音日志）
            item_id = self._extract_item_id(raw_data)
            if not item_id:
                return  # 无 ItemId 的事件直接跳过，不记录日志

            server_id = self._extract_server_id(raw_data)
            event_type_str = self._extract_event_type_str(raw_data)
            source = self._extract_source(raw_data)

            # 检查是否为 Emby 事件
            if source and "emby" not in source.lower():
                return  # 非 Emby 来源静默丢弃

            # 检查事件类型是否与媒体项相关
            if not self._is_item_event(event_type_str, raw_data):
                return  # 非入库事件静默丢弃（playback/playstate 等播放事件）

            # v1.3.9: debounce 延迟调度 - 重复事件重置计时器
            # v1.3.10-fix: key 改为 server_id:item_id，避免多服务器相同 ItemId 冲突
            now = time.time()
            delay = self._webhook_delay
            execute_at = now + delay
            schedule_key = f"{server_id}:{item_id}" if server_id else item_id
            with self._webhook_lock:
                if schedule_key in self._webhook_schedule:
                    # 重复事件：重置 execute_at，静默更新
                    self._webhook_schedule[schedule_key]["execute_at"] = execute_at
                    return
                self._webhook_schedule[schedule_key] = {
                    "execute_at": execute_at,
                    "server_id": server_id,
                    "item_id": item_id,
                    "delay": delay,
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
            self._notify_webhook_received(item_id, delay)
            logger.info(f"[Webhook] 已调度: ItemId={item_id}, 将在 {delay} 秒后执行")

        except Exception as e:
            logger.error(f"[Webhook] 处理异常: {e}\n{traceback.format_exc()}")
            self._webhook_failed += 1
            self._webhook_error = str(e)

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
        
        # v1.3.7: 增加 Event 字段支持（Emby 播放事件使用此字段）
        for key in ["NotificationType", "notification_type", "Type", "type", "EventType", "event_type", "Event"]:
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
        # v1.3.7: 如果事件类型为空，不认为是入库事件（避免播放事件误触发）
        if not event_type:
            return False
        
        event_type_lower = event_type.lower()
        
        # v1.3.7: 先排除播放、会话等非入库事件
        for exclude_keyword in self._WEBHOOK_EXCLUDE_EVENT_TYPES:
            if exclude_keyword in event_type_lower:
                logger.debug(f"[Webhook] 排除非入库事件: {event_type}")
                return False
        
        # 检查是否为已知的 Item 事件类型
        for keyword in self._WEBHOOK_ITEM_EVENT_TYPES:
            if keyword in event_type_lower:
                return True
        
        # 如果包含 ItemId 且事件名包含 item 或 library，也认为是相关事件
        if "item" in event_type_lower or "library" in event_type_lower or "media" in event_type_lower:
            return True
        
        return False

    def _notify_webhook_received(self, item_id: str, delay: int):
        """发送 Webhook 接收通知"""
        try:
            if self._notify_on_complete:
                self.post_message(
                    mtype=NotificationType.Manual,
                    title=self.plugin_name,
                    text=f"收到 Emby 入库事件：ItemId={item_id}，{delay}秒后开始翻译"
                )
        except Exception as e:
            logger.debug(f"[Webhook] 发送通知失败（非致命）: {e}")

    def _webhook_worker(self):
        """
        v1.3.9: Webhook 单 Worker 线程 - 消费延迟调度队列
        避免一事件一线程导致的线程爆炸
        """
        logger.info("[Webhook] Worker 线程已启动")
        while not self._webhook_worker_event.is_set():
            now = time.time()
            pending_item = None
            pending_info = None

            with self._webhook_lock:
                # 查找已到执行时间的任务
                for item_id, info in list(self._webhook_schedule.items()):
                    if info["execute_at"] <= now:
                        pending_item = item_id
                        pending_info = info
                        break

            if pending_item:
                with self._webhook_lock:
                    self._webhook_schedule.pop(pending_item, None)
                self._webhook_processed += 1
                item_id = pending_info.get("item_id", pending_item)
                server_id = pending_info["server_id"]
                logger.info(f"[Webhook] 开始执行: ItemId={item_id}, Server={server_id}")
                try:
                    self._webhook_translate_worker(
                        item_id,
                        server_id,
                        pending_info["delay"]
                    )
                except Exception as e:
                    logger.error(f"[Webhook] Worker 执行异常: {e}\n{traceback.format_exc()}")
                    self._webhook_failed += 1
                continue  # 立即检查下一个

            # 没有到时间的任务，sleep 1秒
            self._webhook_worker_event.wait(1.0)

        logger.info("[Webhook] Worker 线程已退出")

    def _webhook_translate_worker(self, item_id: str, server_id: str, delay: int):
        """
        Webhook 翻译执行器（v1.3.9: 延迟由 _webhook_worker 调度，此处不再 sleep）
        """
        max_retries = 2  # 重试次数
        current_retry = 0

        while current_retry <= max_retries:
            try:
                if current_retry > 0:
                    logger.warning(f"[Webhook] 第 {current_retry} 次重试翻译 ItemId={item_id}")
                    time.sleep(2)  # 重试前等待
                else:
                    # v1.3.9: 首次执行不再等待 delay，因为 _webhook_worker 已经调度延迟
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
                url = self._get_service_url(svc)
                api_key = self._get_service_api_key(svc)
                user_id = self._get_service_user_id(svc)
                client = EmbyClient(url, api_key, svc, user_id=user_id, use_proxy=self._use_proxy)
                
                # 获取条目详情
                logger.info(f"[Webhook] 正在获取条目详情: ItemId={item_id}")
                item = client.fetch_item(item_id)
                if not item:
                    current_retry += 1
                    if current_retry <= max_retries:
                        logger.warning(f"[Webhook] 无法获取条目详情，将重试...")
                        continue
                    else:
                        logger.error(f"[Webhook] 无法获取条目详情: {item_id}（已重试 {max_retries} 次）")
                        self._webhook_failed += 1
                        self._webhook_error = "获取条目详情失败"
                        return
                
                skey = self._get_server_identifier(svc)
                display_title = item.get("Name") or f"Item_{item_id}"
                
                # 执行翻译
                logger.info(f"[Webhook] 开始翻译: {display_title} (ItemId={item_id})")
                with self._process_lock:
                    translated, failed = self._process_item(client, svc, skey, item, "")
                
                # 保存状态
                self._save_state()
                
                if failed > 0 and translated == 0:
                    logger.warning(f"[Webhook] 翻译完成但全部失败: {display_title}")
                    self._webhook_failed += 1
                    self._webhook_error = f"翻译失败: {failed} 条"
                else:
                    logger.info(f"[Webhook] 翻译完成: {display_title} - 翻译 {translated} 条, 失败 {failed} 条")
                    self._webhook_error = ""
                
                # 发送完成通知
                self._notify_webhook_completed(item_id, display_title, translated, failed, item)
                return  # 成功，退出重试循环
                
            except Exception as e:
                logger.error(f"[Webhook] 翻译异常 (尝试 {current_retry + 1}/{max_retries + 1}): {e}")
                self._webhook_error = str(e)
                current_retry += 1
                if current_retry > max_retries:
                    self._webhook_failed += 1
                    logger.error(f"[Webhook] 翻译彻底失败: ItemId={item_id}")

    def _find_target_server(self, services: list, server_id: str):
        """查找目标 Emby 服务器"""
        if not server_id:
            # 没有指定服务器，使用第一个
            logger.info(f"[Webhook] 未指定服务器，使用第一个可用服务器")
            return services[0]
        
        # 尝试精确匹配
        for svc in services:
            skey = self._get_server_identifier(svc)
            if skey == server_id:
                return svc
        
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
        
        # 找不到匹配，使用第一个
        logger.warning(f"[Webhook] 未找到匹配的服务器 (server_id={server_id})，使用第一个")
        return services[0]

    def _notify_webhook_completed(self, item_id: str, title: str, translated: int, failed: int, item: dict = None):
        """发送 Webhook 翻译完成通知（v1.3.8: 支持聚合）"""
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
            
            if series_name and episode_num is not None:
                # 剧集模式：加入聚合队列
                self._add_notification_to_queue(
                    series_name=series_name,
                    title=title,
                    season_num=season_num,
                    episode_num=episode_num,
                    translated=translated,
                    failed=failed,
                )
            else:
                # 电影/非剧集：直接发送
                if translated > 0 or failed > 0:
                    self.post_message(
                        mtype=NotificationType.Manual,
                        title=self.plugin_name,
                        text=f"翻译完成：{title} - 翻译 {translated} 条, 失败 {failed} 条"
                    )
                else:
                    self.post_message(
                        mtype=NotificationType.Manual,
                        title=self.plugin_name,
                        text=f"{title} - 无需翻译"
                    )
        except Exception as e:
            logger.debug(f"[Webhook] 发送完成通知失败（非致命）: {e}")

    def _add_notification_to_queue(self, series_name: str, title: str, season_num, episode_num, translated: int, failed: int):
        """v1.3.8: 将剧集通知加入聚合队列"""
        info = {
            "title": title,
            "season_num": season_num,
            "episode_num": episode_num,
            "translated": translated,
            "failed": failed,
        }
        with self._notification_lock:
            if series_name not in self._notification_queue:
                self._notification_queue[series_name] = []
            self._notification_queue[series_name].append(info)
            # 重置定时器：5 秒后聚合发送
            if self._notification_flush_timer:
                self._notification_flush_timer.cancel()
            self._notification_flush_timer = threading.Timer(5.0, self._flush_notification_queue)
            self._notification_flush_timer.daemon = True
            self._notification_flush_timer.start()
            logger.info(f"[Webhook] 通知已入队: {series_name} 第{episode_num}集（等待聚合）")

    def _flush_notification_queue(self):
        """v1.3.8: 聚合发送通知队列"""
        with self._notification_lock:
            queue = dict(self._notification_queue)
            self._notification_queue.clear()
            self._notification_flush_timer = None

        for series_name, items in queue.items():
            try:
                episodes = sorted(set(i["episode_num"] for i in items if i["episode_num"] is not None))
                seasons = sorted(set(i["season_num"] for i in items if i["season_num"] is not None))
                total_translated = sum(i["translated"] for i in items)
                total_failed = sum(i["failed"] for i in items)

                # 构建集数显示
                if len(episodes) == 1:
                    ep_text = f"第{episodes[0]}集"
                else:
                    ep_text = f"第{episodes[0]}-{episodes[-1]}集"

                season_text = ""
                if len(seasons) == 1:
                    season_text = f"第{seasons[0]}季 "
                elif len(seasons) > 1:
                    season_text = f"第{seasons[0]}-{seasons[-1]}季 "

                if total_translated > 0 or total_failed > 0:
                    text = f"翻译完成：{series_name} {season_text}{ep_text} - 翻译 {total_translated} 条, 失败 {total_failed} 条"
                else:
                    text = f"{series_name} {season_text}{ep_text} - 无需翻译"

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
            }
        }

    def _api_test_webhook(self, **kwargs):
        """
        测试 Webhook 处理
        可以手动触发一个模拟的 Webhook 事件来验证处理逻辑是否正常
        """
        try:
            item_id = self._extract_param(kwargs, "item_id")
            
            if not item_id:
                return {
                    "success": False,
                    "message": "请提供 item_id 参数",
                    "example": "plugin/EmbyPeopleLocalize/test_webhook?item_id=12345"
                }
            
            # 模拟 Webhook 数据
            test_data = {
                "ItemId": item_id,
                "ServerId": "",
                "NotificationType": "ItemAdded",
                "source": "emby",
            }
            
            # 直接调用处理逻辑
            logger.info(f"[Webhook-Test] 开始测试: item_id={item_id}")
            
            self._webhook_received += 1
            self._webhook_last_time = time.time()
            self._webhook_last_event = f"Test | ItemId={item_id}"
            
            # 获取服务
            services = self._get_all_emby_services()
            if not services:
                self._webhook_failed += 1
                return {"success": False, "message": "无可用 Emby 服务器"}
            
            svc = services[0]
            url = self._get_service_url(svc)
            api_key = self._get_service_api_key(svc)
            user_id = self._get_service_user_id(svc)
            client = EmbyClient(url, api_key, svc, user_id=user_id, use_proxy=self._use_proxy)
            
            item = client.fetch_item(item_id)
            if not item:
                self._webhook_failed += 1
                return {"success": False, "message": f"无法获取条目详情: {item_id}"}
            
            skey = self._get_server_identifier(svc)
            title = item.get("Name") or f"Item_{item_id}"
            
            self._force_refresh = True
            with self._process_lock:
                translated, failed = self._process_item(client, svc, skey, item, "")
            
            self._webhook_processed += 1
            self._save_state()
            
            return {
                "success": True,
                "message": f"测试完成: {title} - 翻译 {translated} 条, 失败 {failed} 条",
                "data": {"item_id": item_id, "title": title, "translated": translated, "failed": failed}
            }
            
        except Exception as e:
            logger.error(f"[Webhook-Test] 测试失败: {e}\n{traceback.format_exc()}")
            self._webhook_failed += 1
            return {"success": False, "message": f"测试失败: {e}"}

# v1.3.10 - local dev trigger
