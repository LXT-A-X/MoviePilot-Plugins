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

from .ui_forms import build_form, build_page
from .emby_client import EmbyClient
from .llm_client import LLMClient
from .translator import PeopleTranslator
from . import constants


class EmbyPeopleLocalize(_PluginBase):
    plugin_name = "Emby 演职人员中文化"
    plugin_desc = "利用大模型把 Emby 英文/罗马音/日文人名翻译为简体中文并写回"
    plugin_icon = "embypeoplelocalize.jpg"
    plugin_version = "1.2.2"
    plugin_author = "LXT-A-X"
    plugin_config_prefix = "embypeoplelocalize_"
    plugin_order = 27
    auth_level = 1
    v2 = True

    # ────────── 配置项 ──────────
    _enabled: bool = False
    _onlyonce: bool = False
    _libraries: List[str] = []
    _prompt_template: str = ""
    _translate_actor: bool = True
    _translate_director: bool = False
    _translate_writer: bool = False
    _translate_producer: bool = False
    _translate_all: bool = False
    _translate_role: bool = True
    _max_people_per_title: int = 10
    _max_people_per_batch: int = 5
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

    # ────────── 运行时状态 ──────────
    _ms_helper: Optional[MediaServerHelper] = None
    _emby: Optional[EmbyClient] = None
    _llm: Optional[LLMClient] = None
    _translator: Optional[PeopleTranslator] = None
    _stop_requested: bool = False
    _name_cache: Dict[str, Dict[str, str]] = {}
    _role_cache: Dict[str, Dict[str, str]] = {}
    _processed: Dict[str, str] = {}
    _history: List[Dict[str, Any]] = []
    _is_running: bool = False
    _is_paused: bool = False
    _last_run_time: Optional[float] = None
    _state_lock = threading.Lock()

    # 进度追踪
    _progress_total: int = 0
    _progress_done: int = 0
    _progress_current_title: str = ""
    _progress_current_library: str = ""
    _progress_servers_done: int = 0
    _progress_servers_total: int = 0

    # 缓存命中率统计
    _cache_hits: int = 0
    _cache_misses: int = 0

    # Webhook 状态追踪
    _webhook_received: int = 0
    _webhook_processed: int = 0
    _webhook_failed: int = 0
    _webhook_last_time: Optional[float] = None
    _webhook_last_event: str = ""
    _webhook_error: str = ""

    # 状态持久化路径
    _state_file: str = ""

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
            "_is_running", "_is_paused", "_last_run_time",
            "_name_cache", "_role_cache", "_processed", "_history",
            "_progress_total", "_progress_done", "_progress_current_title",
            "_progress_current_library", "_progress_servers_done", "_progress_servers_total",
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
            }
            state_file = self._get_state_file()
            tmp_file = state_file + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, state_file)
        except Exception as e:
            logger.warning(f"保存状态失败: {e}")

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
            self._processed = state.get("processed", {}) or {}
            self._history = state.get("history", []) or []
            self._last_run_time = state.get("last_run_time")
            self._cache_hits = state.get("cache_hits", 0) or 0
            self._cache_misses = state.get("cache_misses", 0) or 0
            total = sum(len(v) for v in self._name_cache.values()) + sum(len(v) for v in self._role_cache.values())
            logger.info(f"加载持久化状态: {len(self._processed)} 条已处理, {len(self._history)} 条历史, {total} 条缓存")
        except Exception as e:
            logger.warning(f"加载状态失败: {e}")
            self._name_cache = {}
            self._role_cache = {}
            self._processed = {}
            self._history = []

    def _auto_save(self):
        if self._progress_done % 10 == 0:
            self._save_state()

    # ============================================================
    # V2 API 注册
    # ============================================================
    def get_api(self) -> List[dict]:
        return [
            {"path": "/clear_cache", "endpoint": self._api_clear_cache, "methods": ["GET"], "auth": None},
            {"path": "/scan", "endpoint": self._api_scan, "methods": ["GET", "POST"], "auth": None},
            {"path": "/stop", "endpoint": self._api_stop, "methods": ["GET", "POST"], "auth": None},
            {"path": "/status", "endpoint": self._api_status, "methods": ["GET", "POST"], "auth": None},
            {"path": "/lock_cast", "endpoint": self._api_lock_cast, "methods": ["POST"], "auth": None},
            {"path": "/save_config", "endpoint": self._api_save_config, "methods": ["POST"], "auth": None},
            {"path": "/refresh_llm", "endpoint": self._api_refresh_llm, "methods": ["POST"], "auth": None},
            {"path": "/retranslate", "endpoint": self._api_retranslate, "methods": ["GET", "POST"], "auth": None},
            {"path": "/set_search", "endpoint": self._api_set_search, "methods": ["GET", "POST"], "auth": None},
            {"path": "/webhook_status", "endpoint": self._api_webhook_status, "methods": ["GET"], "auth": None},
            {"path": "/test_webhook", "endpoint": self._api_test_webhook, "methods": ["GET", "POST"], "auth": None},
        ]

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

            form, config = build_form(lib_options, self, invalid_libraries=invalid_libs)
            current = self._dump_config()
            config.update(current)
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

    def _api_scan(self):
        if self._is_running:
            return {"success": False, "message": "扫描任务正在运行中"}
        self._stop_requested = False
        threading.Thread(target=self._scan_worker, kwargs={"force": True}, daemon=True).start()
        return {"success": True, "message": "扫描任务已启动"}

    def _api_stop(self):
        if not self._is_running:
            return {"success": False, "message": "没有正在运行的扫描任务"}
        self._stop_requested = True
        self._is_paused = True
        return {"success": True, "message": "已请求停止扫描"}

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
                "progress": {
                    "total": self._progress_total,
                    "done": self._progress_done,
                    "current_title": self._progress_current_title,
                    "current_library": self._progress_current_library,
                },
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
                    client = EmbyClient(url, api_key, svc, user_id=user_id)
                    if client.lock_cast_for_item(item_id):
                        locked += 1
                        with self._state_lock:
                            for h in self._history:
                                if h.get("time") == processed.get(key):
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

    def _api_save_config(self, **kwargs):
        try:
            data = kwargs.get("data") or kwargs.get("form") or kwargs
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except Exception:
                    data = {}
            if isinstance(data, dict) and data:
                self._load_config(data)
                self.update_config(self._dump_config())
                logger.info("配置已保存")
                return {"success": True, "message": "配置已保存"}
            return {"success": False, "message": "未收到配置数据"}
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
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
        self._load_state()

        if config:
            self._load_config(config)

        # 检查插件是否被禁用，如果是则停止正在运行的扫描
        if not self._enabled and self._is_running:
            logger.info("插件已禁用，正在停止扫描...")
            self._stop_requested = True
            self._is_paused = True

        if self._is_running:
            logger.info("扫描正在运行，配置将在下次扫描时生效")

        if self._enabled:
            self._startup()

        if self._run_clear_cache:
            logger.info("检测到「清除缓存并重扫」开关")
            self._run_clear_cache = False
            self.update_config(self._dump_config())
            self.clear_cache()
            self._scan_worker(force=True)

        if self._run_scan:
            logger.info("检测到「立即扫描」开关")
            self._run_scan = False
            self.update_config(self._dump_config())
            self._scan_worker(force=True)

        if self._run_lock_cast:
            logger.info("检测到「批量补锁定」开关")
            self._run_lock_cast = False
            self.update_config(self._dump_config())
            threading.Thread(target=self._api_lock_cast, daemon=True).start()

        if self._onlyonce:
            self._onlyonce = False
            self._force_refresh = False
            self.update_config(self._dump_config())
            self._scan_worker(force=True)

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
        self._overwrite_chinese = bool(config.get(constants.CFG_OVERWRITE_CHINESE, False))
        self._delay = int(config.get(constants.CFG_DELAY, constants.DEFAULT_DELAY))
        self._lock_cast = bool(config.get(constants.CFG_LOCK_CAST, False))
        self._run_scan = bool(config.get(constants.CFG_RUN_SCAN, False))
        self._run_lock_cast = bool(config.get(constants.CFG_RUN_LOCK_CAST, False))
        self._run_clear_cache = bool(config.get(constants.CFG_RUN_CLEAR_CACHE, False))
        self._llm_base_url = str(config.get(constants.CFG_LLM_BASE_URL, ""))
        self._llm_api_key = str(config.get(constants.CFG_LLM_API_KEY, ""))
        self._llm_model = str(config.get(constants.CFG_LLM_MODEL, ""))
        self._llm_timeout = int(config.get(constants.CFG_LLM_TIMEOUT, constants.DEFAULT_LLM_TIMEOUT))
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
            constants.CFG_OVERWRITE_CHINESE: self._overwrite_chinese,
            constants.CFG_DELAY: self._delay,
            constants.CFG_LOCK_CAST: self._lock_cast,
            constants.CFG_RUN_SCAN: self._run_scan,
            constants.CFG_RUN_LOCK_CAST: self._run_lock_cast,
            constants.CFG_RUN_CLEAR_CACHE: self._run_clear_cache,
            constants.CFG_LLM_BASE_URL: self._llm_base_url,
            constants.CFG_LLM_API_KEY: self._llm_api_key,
            constants.CFG_LLM_MODEL: self._llm_model,
            constants.CFG_LLM_TIMEOUT: self._llm_timeout,
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
                                        user_id=self._get_service_user_id(svc))
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
                                    user_id=self._get_service_user_id(svc))
            self._init_llm()
            self._translator = PeopleTranslator(
                llm_client=self._llm,
                name_cache=self._name_cache,
                role_cache=self._role_cache,
                state_lock=self._state_lock,
                plugin=self,
            )
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
        if not force and self._is_running:
            logger.info("扫描已在运行中")
            return
        self._is_running = True
        self._is_paused = False
        self._stop_requested = False
        self._last_run_time = time.time()
        self._progress_done = 0
        self._progress_total = 0
        self._progress_servers_done = 0
        self._cache_hits = 0
        self._cache_misses = 0
        total_translated = total_failed = 0

        try:
            logger.info("=" * 50)
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
                                    user_id=self._get_service_user_id(svc))
                libs = client.get_libraries()
                for lib in libs:
                    lib_id = str(lib.get("Id", ""))
                    full_key = f"{skey}:{lib_id}"
                    if target_libs and full_key not in target_libs:
                        continue
                    all_tasks.append((svc, skey, client, lib_id, lib.get("Name", "?")))

            self._progress_total = len(all_tasks)
            logger.info(f"共 {len(all_tasks)} 个媒体库待扫描")

            for svc, skey, client, lib_id, lib_name in all_tasks:
                if self._stop_requested:
                    logger.info("扫描已请求停止")
                    break
                self._progress_current_library = f"[{getattr(svc,'name','?')}] {lib_name}"
                logger.info(f"📂 扫描媒体库: {self._progress_current_library}")
                t, f = self._scan_library(client, svc, skey, lib_id, lib_name)
                total_translated += t
                total_failed += f
                self._progress_done += 1
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
            self._is_running = False
            self._is_paused = False
            self._stop_requested = False
            self._progress_current_title = ""
            self._progress_current_library = ""
            self._save_state()

    def _scan_library(self, client: EmbyClient, svc: ServiceInfo, skey: str,
                      lib_id: str, lib_name: str) -> Tuple[int, int]:
        translated = failed = 0
        start = 0
        page_size = 50

        while True:
            if self._stop_requested:
                break
            try:
                data = client.fetch_items_page(lib_id, limit=page_size, start_index=start)
                items = (data or {}).get("Items", []) or []
                if not items:
                    break

                for item in items:
                    if self._stop_requested:
                        break
                    try:
                        t, f = self._process_item(client, svc, skey, item, lib_name)
                        translated += t
                        failed += f
                    except Exception as e:
                        logger.error(f"处理条目异常: {e}")
                        failed += 1
                    time.sleep(self._delay)

                if len(items) < page_size:
                    break
                start += page_size
            except Exception as e:
                logger.error(f"分页获取失败: {e}")
                break

        logger.info(f"媒体库 [{lib_name}] 扫描完成: 翻译 {translated}, 失败 {failed}")
        return translated, failed

    def _process_item(self, client: EmbyClient, svc: ServiceInfo, skey: str,
                      item: dict, lib_name: str = "") -> Tuple[int, int]:
        if self._stop_requested:
            return 0, 0

        item_id = str(item.get("Id", ""))
        title = item.get("Name", "")
        year = item.get("ProductionYear") or (item.get("PremiereDate", "")[:4] if item.get("PremiereDate") else "")
        item_type = item.get("Type", "")

        display_title = title
        series_name = ""
        season_num = None
        episode_num = None

        if item_type == "Episode":
            series_name = item.get("SeriesName", "") or title
            season_num = item.get("SeasonNumber")
            episode_num = item.get("EpisodeNumber")
            if season_num is not None and episode_num is not None:
                display_title = f"{series_name} S{season_num:02d}E{episode_num:02d}"
            elif series_name:
                display_title = series_name
        elif item_type == "Series":
            series_name = title

        key = f"{skey}:{item_id}"
        self._progress_current_title = display_title

        if not self._force_refresh and key in self._processed:
            logger.debug(f"[{item_id}] {display_title} ({year}) — 已处理，跳过")
            return 0, 0

        people = item.get("People", []) or []
        if not people:
            return 0, 0

        # 收集待翻译的人名和角色名
        name_terms = []
        role_terms = []
        skip_reasons = []

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
                if self._looks_like_chinese(name):
                    skip_reasons.append(f"{name}(已是中文)")
                else:
                    name_terms.append(name)

            if role and (self._translate_role or self._translate_all):
                if self._looks_like_chinese(role):
                    skip_reasons.append(f"{role}(角色已是中文)")
                else:
                    role_terms.append(role)

        if not name_terms and not role_terms:
            logger.info(f"[{item_id}] {display_title} ({year}) — 无需翻译")
            self._post_translate_hook(key, display_title, year, item_id, {}, self._lock_cast, lib_name, skipped=True,
                                  series_name=series_name, season_num=season_num, episode_num=episode_num, item_type=item_type)
            return 0, 0

        # 去重并限制数量
        name_terms = list(dict.fromkeys(name_terms))[:self._max_people_per_title]
        role_terms = list(dict.fromkeys(role_terms))[:self._max_people_per_title - len(name_terms)]

        logger.info(f"[{item_id}] {display_title} ({year}) — 待翻译 {len(name_terms) + len(role_terms)} 条")

        # 使用 Translator 处理
        if not self._translator or not self._llm:
            logger.warning("翻译器或 LLM 未初始化")
            return 0, 1

        batch_size = self._max_people_per_batch
        name_translations, role_translations = self._translator.translate_batch(
            title, year, name_terms, role_terms, batch_size
        )

        # 更新缓存命中率
        for name in name_terms:
            if name in name_translations:
                self._cache_hits += 1
            else:
                self._cache_misses += 1
        for role in role_terms:
            if role in role_translations:
                self._cache_hits += 1
            else:
                self._cache_misses += 1

        all_translations = {}
        all_translations.update(name_translations)
        all_translations.update(role_translations)

        if not all_translations:
            logger.info(f"[{item_id}] {display_title} ({year}) — 无有效翻译结果")
            return 0, 0

        new_people = self._translator.apply_translations(people, name_translations, role_translations)

        if self._stop_requested:
            logger.info("已请求停止，跳过写入")
            return 0, 0

        lock = self._lock_cast
        logger.info(f"正在写入 Emby ({len(all_translations)} 条翻译)...")
        updated = client.update_people(item_id, new_people, lock_cast=lock)

        if updated > 0:
            self._post_translate_hook(key, display_title, year, item_id, all_translations, lock, lib_name,
                                      series_name=series_name, season_num=season_num, episode_num=episode_num, item_type=item_type)
            return len(all_translations), 0
        else:
            logger.warning(f"[{item_id}] {display_title} ({year}) — 写回失败")
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
            self._cache_hits = 0
            self._cache_misses = 0
        self._save_state()
        logger.info("所有缓存已清空")

    def stop_service(self):
        self._stop_requested = True
        self._save_state()

    # ============================================================
    # Webhook 入库自动翻译（v1.0.0 完全重构）
    # ============================================================
    
    # Webhook 事件类型映射（Emby → MoviePilot 翻译触发）
    _WEBHOOK_ITEM_EVENT_TYPES = [
        "itemadded", "item.added", "library.new", "added", "newcontent",
        "itemupdated", "item.updated", "library.update",
    ]

    @eventmanager.register(EventType.WebhookMessage)
    def handle_webhook(self, event: Event):
        """
        监听 Emby Webhook 入库事件
        v1.0.0: 完全重写，支持多种事件格式，增强可靠性
        """
        try:
            # 记录收到事件
            self._webhook_received += 1
            self._webhook_last_time = time.time()
            
            # 解析事件数据
            raw_data = event.event_data or {}
            if isinstance(raw_data, str):
                try:
                    raw_data = json.loads(raw_data)
                except Exception:
                    pass
            
            logger.info(f"[Webhook] ===== 收到事件 #{self._webhook_received} =====")
            logger.info(f"[Webhook] event_type={event.event_type}")
            
            # 提取关键信息
            item_id = self._extract_item_id(raw_data)
            server_id = self._extract_server_id(raw_data)
            event_type_str = self._extract_event_type_str(raw_data)
            source = self._extract_source(raw_data)
            
            logger.info(f"[Webhook] 解析结果: item_id={item_id}, server_id={server_id}, type={event_type_str}, source={source}")
            
            # 更新状态
            self._webhook_last_event = f"{event_type_str} | ItemId={item_id}"
            
            # 检查是否为 Emby 事件
            if source and "emby" not in source.lower():
                logger.info(f"[Webhook] 来源不是 Emby，跳过: source={source}")
                return
            
            # 检查事件类型是否与媒体项相关
            if not self._is_item_event(event_type_str, raw_data):
                logger.info(f"[Webhook] 非媒体项事件，跳过: type={event_type_str}")
                return
            
            if not item_id:
                logger.warning("[Webhook] 未能提取到 ItemId，跳过")
                self._webhook_failed += 1
                return
            
            # 记录原始数据摘要
            self._webhook_error = ""
            
            # 发送通知
            delay = self._webhook_delay
            self._notify_webhook_received(item_id, delay)
            
            # 启动延迟翻译线程
            logger.info(f"[Webhook] 将在 {delay} 秒后翻译 ItemId={item_id}")
            threading.Thread(
                target=self._webhook_translate_worker,
                args=(item_id, server_id, delay),
                daemon=True,
                name=f"webhook-translate-{item_id}"
            ).start()
            
            self._webhook_processed += 1
            logger.info(f"[Webhook] 事件处理完成: ItemId={item_id}")
            
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
        
        for key in ["NotificationType", "notification_type", "Type", "type", "EventType", "event_type"]:
            val = data.get(key, "")
            if val:
                return str(val).lower()
        
        nested = data.get("data") or data.get("Data")
        if nested and isinstance(nested, dict):
            for key in ["NotificationType", "notification_type", "Type", "type"]:
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
            # 有 ItemId 就认为是有效事件
            return bool(self._extract_item_id(data))
        
        event_type_lower = event_type.lower()
        
        # 检查是否为已知的 Item 事件类型
        for keyword in self._WEBHOOK_ITEM_EVENT_TYPES:
            if keyword in event_type_lower:
                return True
        
        # 如果包含 ItemId 且事件名包含 item 或 library，也认为是相关事件
        if "item" in event_type_lower or "library" in event_type_lower or "media" in event_type_lower:
            return True
        
        # 检查数据中是否有 ItemId
        if self._extract_item_id(data):
            logger.info(f"[Webhook] 虽然事件类型不明确，但检测到 ItemId，视为有效事件")
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

    def _webhook_translate_worker(self, item_id: str, server_id: str, delay: int):
        """
        Webhook 翻译工作线程
        v1.0.0: 重写，增加重试和错误恢复
        """
        max_retries = 2  # 重试次数
        current_retry = 0
        
        while current_retry <= max_retries:
            try:
                if current_retry > 0:
                    logger.warning(f"[Webhook] 第 {current_retry} 次重试翻译 ItemId={item_id}")
                    time.sleep(2)  # 重试前等待
                
                # 延迟等待元数据刮削完成
                if current_retry == 0:
                    logger.info(f"[Webhook] 等待 {delay} 秒让 Emby 完成元数据刮削...")
                    time.sleep(delay)
                else:
                    time.sleep(1)
                
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
                client = EmbyClient(url, api_key, svc, user_id=user_id)
                
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
                self._notify_webhook_completed(item_id, display_title, translated, failed)
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

    def _notify_webhook_completed(self, item_id: str, title: str, translated: int, failed: int):
        """发送 Webhook 翻译完成通知"""
        try:
            if self._notify_on_complete and (translated > 0 or failed > 0):
                self.post_message(
                    mtype=NotificationType.Manual,
                    title=self.plugin_name,
                    text=f"翻译完成：{title} - 翻译 {translated} 条, 失败 {failed} 条"
                )
        except Exception as e:
            logger.debug(f"[Webhook] 发送完成通知失败（非致命）: {e}")

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
            client = EmbyClient(url, api_key, svc, user_id=user_id)
            
            item = client.fetch_item(item_id)
            if not item:
                self._webhook_failed += 1
                return {"success": False, "message": f"无法获取条目详情: {item_id}"}
            
            skey = self._get_server_identifier(svc)
            title = item.get("Name") or f"Item_{item_id}"
            
            self._force_refresh = True
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
