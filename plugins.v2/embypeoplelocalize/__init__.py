"""
EmbyPeopleLocalize - Emby 演职人员中文化 v0.8.1
利用大模型把 Emby 英文/罗马音/日文人名翻译为简体中文并写回
支持多服务器分库、入库/Webhook触发、Cast 锁定防覆盖、繁简直转省 LLM
v0.8.1: 修复搜索筛选和重译按钮、搜索关键词可持久化配置
v0.8.0: 移除定时扫描、新增重新翻译功能、历史搜索筛选、通知始终发送
v0.7.0: Webhook 入库自动翻译、缓存持久化到 config/plugins/
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

# ========== openai SDK + httpx 代理初始化 ==========
try:
    import openai as _openai_mod
    import httpx as _httpx_mod
    _HAS_OPENAI_SDK = True
except Exception:
    _HAS_OPENAI_SDK = False
    _openai_mod = None
    _httpx_mod = None

# 屏蔽 InsecureRequestWarning
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

# 简繁转换
try:
    import zhconv
    HAS_ZHCONV = True
except ImportError:
    HAS_ZHCONV = False

# 本地模块
from .ui_forms import build_form, build_page
from .emby_client import EmbyClient
from .llm_client import LLMClient
from .translator import PeopleTranslator
from . import constants

# ========== 默认提示词 ==========
DEFAULT_PROMPT = """你是一位世界级的影视专家，扮演一个只返回 JSON 的 API。
任务：将外语/拼音/日文演员名和角色名翻译成简体中文。

输入格式：
context: {"title": 作品名, "year": 年份}
terms: 待翻译字符串列表

策略：
1. 利用 title + year 确定具体作品，找官方/最公认的中文译名
2. 拼音/英文/日文 → 汉字
3. 目标语言永远是简体中文
4. 无法翻译则保留原文

输出格式（强制 JSON，禁止 markdown）：
{"原文1": "译文1", "原文2": "译文2"}
"""


class EmbyPeopleLocalize(_PluginBase):
    plugin_name = "Emby 演职人员中文化"
    plugin_desc = "利用大模型把 Emby 英文/罗马音/日文人名翻译为简体中文并写回（可选库/全库）"
    plugin_icon = "embypeoplelocalize.jpg"
    plugin_version = "0.8.1"
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
    _translate_voice_actor: bool = True
    _translate_director: bool = False
    _translate_writer: bool = False
    _translate_producer: bool = False
    _translate_all: bool = False
    _translate_role: bool = True  # 是否翻译角色名（Role 字段）
    _max_people_per_title: int = 10
    _max_people_per_batch: int = 5
    _overwrite_chinese: bool = False
    _force_refresh: bool = False
    _delay: int = 2
    _lock_cast: bool = False
    _webhook_delay: int = 60

    # 手动操作触发开关（打开 → 保存 → 执行 → 自动复位）
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
    _MAX_HISTORY = 200
    _SAVE_INTERVAL = 10
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

    # 通知开关
    _notify_on_complete: bool = False

    # 状态持久化路径（延迟初始化）
    _state_file: str = ""

    # ────────── V2 私有属性声明 ──────────
    @property
    def private_attrs(self) -> List[str]:
        return [
            "_enabled", "_onlyonce", "_libraries", "_prompt_template",
            "_translate_actor", "_translate_voice_actor", "_translate_director",
            "_translate_writer", "_translate_producer", "_translate_all", "_translate_role",
            "_max_people_per_title", "_max_people_per_batch", "_overwrite_chinese",
            "_force_refresh", "_delay", "_lock_cast", "_webhook_delay",
            "_run_scan", "_run_lock_cast", "_run_clear_cache",
            "_llm_base_url", "_llm_api_key", "_llm_model", "_llm_timeout",
            "_is_running", "_is_paused", "_last_run_time",
            "_name_cache", "_role_cache", "_processed", "_history",
            "_progress_total", "_progress_done", "_progress_current_title",
            "_progress_current_library", "_progress_servers_done", "_progress_servers_total",
            "_cache_hits", "_cache_misses", "_notify_on_complete",
        ]

    # ============================================================
    # 状态持久化
    # ============================================================
    def _get_state_file(self) -> str:
        """获取状态文件路径（存放在 config/plugins/ 下，MP 重启不会清空）"""
        if not self._state_file:
            cache_dir = os.path.join("config", "plugins", "embypeoplelocalize")
            os.makedirs(cache_dir, exist_ok=True)
            self._state_file = os.path.join(cache_dir, "state.json")
        return self._state_file

    def _save_state(self):
        """持久化运行状态到文件"""
        try:
            state = {
                "version": self.plugin_version,
                "name_cache": self._name_cache,
                "role_cache": self._role_cache,
                "processed": self._processed,
                "history": self._history[-self._MAX_HISTORY:],
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
        """从文件加载持久化状态"""
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
            total_cache = sum(len(v) for v in self._name_cache.values()) + sum(len(v) for v in self._role_cache.values())
            logger.info(f"加载持久化状态: {len(self._processed)} 条已处理, {len(self._history)} 条历史, {total_cache} 条缓存 (命中率 {self._cache_hits}/{self._cache_hits + self._cache_misses})")
        except Exception as e:
            logger.warning(f"加载状态失败: {e}")
            self._name_cache = {}
            self._role_cache = {}
            self._processed = {}
            self._history = []

    def _auto_save(self):
        """自动保存（每次处理 N 个条目后调用）"""
        if self._progress_done % self._SAVE_INTERVAL == 0:
            self._save_state()

    # ============================================================
    # V2 插件必须：API 注册
    # ============================================================
    def get_api(self) -> List[dict]:
        return [
            {"path": "/clear_cache",     "endpoint": self._api_clear_cache,  "methods": ["GET"],       "auth": None, "summary": "清空缓存"},
            {"path": "/clear_and_rescan", "endpoint": self._api_clear_and_rescan, "methods": ["GET"], "auth": None, "summary": "清除缓存并重扫"},
            {"path": "/scan",           "endpoint": self._api_scan,          "methods": ["GET", "POST"], "auth": None, "summary": "立即扫描"},
            {"path": "/stop",           "endpoint": self._api_stop,          "methods": ["GET", "POST"], "auth": None, "summary": "停止扫描"},
            {"path": "/status",         "endpoint": self._api_status,        "methods": ["GET", "POST"], "auth": None, "summary": "获取状态"},
            {"path": "/lock_cast",      "endpoint": self._api_lock_cast,     "methods": ["POST"],       "auth": None, "summary": "锁定已翻译条目的Cast"},
            {"path": "/open_settings",  "endpoint": self._api_open_settings, "methods": ["GET"],       "auth": None, "summary": "打开设置页"},
            {"path": "/back_to_page",   "endpoint": self._api_back_to_page,  "methods": ["GET"],       "auth": None, "summary": "返回数据页"},
            {"path": "/save_config",    "endpoint": self._api_save_config,   "methods": ["POST"],      "auth": None, "summary": "保存配置"},
            {"path": "/refresh_llm",    "endpoint": self._api_refresh_llm,   "methods": ["POST"],      "auth": None, "summary": "刷新LLM配置"},
            {"path": "/retranslate", "endpoint": self._api_retranslate, "methods": ["GET", "POST"], "auth": None, "summary": "重新翻译历史条目"},
            {"path": "/apply_search", "endpoint": self._api_apply_search, "methods": ["GET", "POST"], "auth": None, "summary": "应用搜索筛选"},
            {"path": "/clear_search", "endpoint": self._api_clear_search, "methods": ["GET", "POST"], "auth": None, "summary": "清除搜索筛选"},
            {"path": "/search_history", "endpoint": self._api_search_history, "methods": ["GET", "POST"], "auth": None, "summary": "搜索翻译历史"},
            {"path": "/set_search", "endpoint": self._api_set_search, "methods": ["GET", "POST"], "auth": None, "summary": "设置搜索关键词"},
        ]

    # ============================================================
    # V2 插件必须：页面构建
    # ============================================================
    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """第二页（设置页）"""
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
                config["prompt_template"] = DEFAULT_PROMPT
            return form, config
        except Exception as e:
            logger.error(f"构建配置表单失败: {e}\n{traceback.format_exc()}")
            return [], {}

    def get_page(self) -> List[dict]:
        """第一页（数据面板）"""
        try:
            return build_page(self)
        except Exception as e:
            logger.error(f"构建数据面板失败: {e}\n{traceback.format_exc()}")
            return [{"component": "div", "props": {"class": "pa-4 text-error"},
                     "content": [{"component": "p", "text": f"页面渲染失败: {e}"}]}]

    def get_state(self) -> bool:
        return self._enabled

    # ============================================================
    # API 处理方法
    # ============================================================
    def _api_clear_cache(self):
        try:
            self.clear_cache()
            return {"success": True, "message": "缓存已清空"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_clear_and_rescan(self):
        """清除缓存并立即重新扫描"""
        if self._is_running:
            return {"success": False, "message": "扫描任务正在运行中，请先停止"}
        try:
            self.clear_cache()
            logger.info("缓存已清空，开始重新扫描...")
            self._stop_requested = False
            threading.Thread(target=self._scan_worker, kwargs={"force": True}, daemon=True).start()
            return {"success": True, "message": "缓存已清空，扫描任务已启动"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_scan(self):
        if self._is_running:
            return {"success": False, "message": "扫描任务正在运行中"}
        self._stop_requested = False
        threading.Thread(target=self._scan_worker, kwargs={"force": True}, daemon=True).start()
        return {"success": True, "message": "扫描任务已启动"}

    def _api_stop(self):
        """停止当前扫描"""
        if not self._is_running:
            return {"success": False, "message": "没有正在运行的扫描任务"}
        self._stop_requested = True
        self._is_paused = True
        return {"success": True, "message": "已请求停止扫描，正在安全退出..."}

    def _api_status(self):
        total_hits = self._cache_hits
        total_misses = self._cache_misses
        total_lookups = total_hits + total_misses
        hit_rate = round(total_hits / total_lookups * 100, 1) if total_lookups > 0 else 0.0
        return {
            "success": True,
            "data": {
                "is_running": self._is_running,
                "is_paused": self._is_paused,
                "stop_requested": self._stop_requested,
                "history_count": len(self._history),
                "name_cache_count": sum(len(v) for v in self._name_cache.values()),
                "role_cache_count": sum(len(v) for v in self._role_cache.values()),
                "cache_hits": total_hits,
                "cache_misses": total_misses,
                "cache_hit_rate": hit_rate,
                "processed_count": len(self._processed),
                "emby_connected": self._emby is not None,
                "llm_configured": self._llm is not None,
                "lock_cast": self._lock_cast,
                "progress": {
                    "total": self._progress_total,
                    "done": self._progress_done,
                    "current_title": self._progress_current_title,
                    "current_library": self._progress_current_library,
                    "servers_done": self._progress_servers_done,
                    "servers_total": self._progress_servers_total,
                },
            }
        }

    def _api_lock_cast(self):
        """遍历已处理条目，批量追加 Cast 到 LockedFields"""
        try:
            services = self._get_all_emby_services()
            if not services or not self._emby:
                return {"success": False, "message": "Emby 未连接"}
            processed = self._processed or {}
            if not processed:
                return {"success": True, "message": "没有已处理的条目", "data": {"locked": 0, "skipped": 0, "failed": 0}}
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
                    client = EmbyClient(self._get_service_url(svc), self._get_service_api_key(svc), svc,
                                    user_id=self._get_service_user_id(svc))
                    ok = client.lock_cast_for_item(svc, item_id)
                    if ok:
                        locked += 1
                        with self._state_lock:
                            for h in self._history:
                                if h.get("time") == processed.get(key):
                                    h["cast_locked"] = True
                    else:
                        skipped += 1
                except Exception:
                    failed += 1
            msg = f"锁定完成: 成功 {locked}, 跳过 {skipped}, 失败 {failed}"
            logger.info(msg)
            self._save_state()
            return {"success": True, "message": msg, "data": {"locked": locked, "skipped": skipped, "failed": failed}}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def _api_open_settings(self):
        return {"redirect": "/plugin/EmbyPeopleLocalize/config"}

    def _api_back_to_page(self):
        return {"redirect": "/plugin/EmbyPeopleLocalize"}

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
        """手动刷新 LLM 配置（从 MP 系统重新读取）"""
        try:
            old_model, new_model = self._refresh_llm()
            return {
                "success": True,
                "message": f"LLM 已刷新: {old_model} → {new_model}",
                "data": {"old_model": old_model, "new_model": new_model},
            }
        except Exception as e:
            logger.error(f"刷新 LLM 失败: {e}")
            return {"success": False, "message": str(e)}

    # ============================================================
    # 初始化 / 配置加载
    # ============================================================
    def init_plugin(self, config: dict = None):
        """初始化插件 — 不清除状态，只重载配置和连接"""
        # 先加载持久化状态（历史、缓存不丢失）
        self._load_state()
        # 保存配置时不中断正在运行的扫描，避免缓存丢失
        # 如果扫描正在运行，让它继续执行，配置更新在下次扫描时生效
        if self._is_running:
            logger.info("扫描正在运行，配置将在下次扫描时生效")

        if config:
            self._load_config(config)
        if self._enabled:
            self._startup()

        # ── 处理「清除缓存并重扫」触发开关 ──
        if self._run_clear_cache:
            logger.info("检测到「清除缓存并重扫」开关，开始执行...")
            self._run_clear_cache = False
            self.update_config(self._dump_config())
            self.clear_cache()
            self._scan_worker(force=True)

        # ── 处理手动操作触发开关 ──
        if self._run_scan:
            logger.info("检测到「立即扫描」开关，开始执行...")
            self._run_scan = False
            self.update_config(self._dump_config())
            self._scan_worker(force=True)

        if self._run_lock_cast:
            logger.info("检测到「批量补锁定」开关，开始执行...")
            self._run_lock_cast = False
            self.update_config(self._dump_config())
            threading.Thread(target=self._api_lock_cast, daemon=True).start()

        # 一次性运行（入库后自动扫描）
        if self._onlyonce:
            self._onlyonce = False
            self._force_refresh = False
            self.update_config(self._dump_config())
            self._scan_worker(force=True)

    def _load_config(self, config: dict):
        self._enabled = bool(config.get("enabled", False))
        self._onlyonce = bool(config.get("onlyonce", False))
        self._libraries = list(config.get("libraries", []))
        self._prompt_template = str(config.get("prompt_template") or DEFAULT_PROMPT)
        self._translate_all = bool(config.get("translate_all", False))
        self._translate_role = bool(config.get("translate_role", True))
        self._translate_actor = bool(config.get("translate_actor", True))
        self._translate_director = bool(config.get("translate_director", False))
        self._translate_writer = bool(config.get("translate_writer", False))
        self._translate_producer = bool(config.get("translate_producer", False))
        
        # 如果开启「全部翻译」，强制将所有翻译类型设为 True，UI 显示为开启状态
        if self._translate_all:
            self._translate_role = True
            self._translate_actor = True
            self._translate_director = True
            self._translate_writer = True
            self._translate_producer = True
        
        self._max_people_per_title = int(config.get("max_people_per_title", 10))
        self._max_people_per_batch = int(config.get("max_people_per_batch", 5))
        self._overwrite_chinese = bool(config.get("overwrite_chinese", False))
        self._force_refresh = bool(config.get("force_refresh", False))
        self._delay = int(config.get("delay", 2))
        self._lock_cast = bool(config.get("lock_cast", False))
        self._run_scan = bool(config.get("run_scan", False))
        self._run_lock_cast = bool(config.get("run_lock_cast", False))
        self._run_clear_cache = bool(config.get("run_clear_cache", False))
        self._llm_base_url = str(config.get("llm_base_url") or "")
        self._llm_api_key = str(config.get("llm_api_key") or "")
        self._llm_model = str(config.get("llm_model") or "")
        self._llm_timeout = int(config.get("llm_timeout", 120) or 120)
        self._webhook_delay = int(config.get("webhook_delay", 60) or 60)
        self._notify_on_complete = bool(config.get("notify_on_complete", False))
        self._history_search = str(config.get("history_search_keyword", "") or "")

    def _dump_config(self) -> dict:
        # 如果开启「全部翻译」，强制将所有翻译类型保存为 True
        if self._translate_all:
            self._translate_role = True
            self._translate_actor = True
            self._translate_director = True
            self._translate_writer = True
            self._translate_producer = True
        
        return {
            "enabled": self._enabled,
            "onlyonce": self._onlyonce,
            "libraries": self._libraries,
            "prompt_template": self._prompt_template or DEFAULT_PROMPT,
            "translate_actor": self._translate_actor,
            "translate_director": self._translate_director,
            "translate_writer": self._translate_writer,
            "translate_producer": self._translate_producer,
            "translate_all": self._translate_all,
            "translate_role": self._translate_role,
            "max_people_per_title": self._max_people_per_title,
            "max_people_per_batch": self._max_people_per_batch,
            "overwrite_chinese": self._overwrite_chinese,
            "force_refresh": self._force_refresh,
            "delay": self._delay,
            "lock_cast": self._lock_cast,
            "run_scan": self._run_scan,
            "run_lock_cast": self._run_lock_cast,
            "run_clear_cache": self._run_clear_cache,
            "llm_base_url": self._llm_base_url,
            "llm_api_key": self._llm_api_key,
            "llm_model": self._llm_model,
            "llm_timeout": self._llm_timeout,
            "webhook_delay": self._webhook_delay,
            "notify_on_complete": self._notify_on_complete,
            "history_search_keyword": self._history_search or "",
        }



    def _api_set_search(self, **kwargs):
        """设置搜索关键词 - 支持多种参数格式"""
        try:
            keyword = ""
            # update:modelValue 事件可能传递 value 参数
            if "value" in kwargs:
                keyword = str(kwargs["value"] or "")
            elif "keyword" in kwargs:
                keyword = str(kwargs["keyword"] or "")
            elif "q" in kwargs:
                keyword = str(kwargs["q"] or "")
            elif kwargs.get("data"):
                data = kwargs["data"]
                if isinstance(data, dict):
                    keyword = str(data.get("keyword", "") or data.get("value", "") or "")
                elif isinstance(data, str):
                    keyword = data
                else:
                    keyword = str(data or "")
            elif kwargs.get("form"):
                form = kwargs["form"]
                if isinstance(form, dict):
                    keyword = str(form.get("keyword", "") or form.get("value", "") or "")
            
            keyword = keyword.strip()
            self._history_search = keyword
            
            if keyword:
                kw = keyword.lower()
                filtered = [h for h in self._history if
                    kw in str(h.get("title", "")).lower() or
                    kw in str(h.get("library", "")).lower() or
                    kw in str(h.get("year", "")).lower() or
                    kw in str(h.get("item_id", "")).lower()
                ]
                return {
                    "success": True,
                    "message": f"搜索完成: 找到 {len(filtered)} 条匹配记录",
                    "data": {"keyword": keyword, "count": len(filtered)}
                }
            else:
                return {
                    "success": True,
                    "message": f"显示全部 {len(self._history)} 条历史记录",
                    "data": {"keyword": "", "count": len(self._history)}
                }
        except Exception as e:
            logger.error(f"搜索历史失败: {e}")
            return {"success": False, "message": str(e)}

    def _api_apply_search(self, **kwargs):
        """应用搜索筛选 - 从 VTextField 的 change 事件获取值或使用配置中的关键词"""
        try:
            keyword = ""
            if "value" in kwargs:
                keyword = str(kwargs["value"] or "")
            elif "keyword" in kwargs:
                keyword = str(kwargs["keyword"] or "")
            elif kwargs.get("data"):
                data = kwargs["data"]
                if isinstance(data, dict):
                    keyword = str(data.get("keyword", "") or data.get("value", "") or "")
                elif isinstance(data, str):
                    keyword = data
                else:
                    keyword = str(data or "")
            
            keyword = keyword.strip()
            self._history_search = keyword
            
            # 同步到配置
            config = self._dump_config()
            config["history_search_keyword"] = keyword
            self.update_config(config)
            
            if keyword:
                kw = keyword.lower()
                count = sum(1 for h in self._history if
                    kw in str(h.get("title", "")).lower() or
                    kw in str(h.get("library", "")).lower() or
                    kw in str(h.get("year", "")).lower() or
                    kw in str(h.get("item_id", "")).lower()
                )
                return {
                    "success": True,
                    "message": f"筛选完成: 找到 {count} 条匹配",
                    "data": {"keyword": keyword, "count": count}
                }
            else:
                return {
                    "success": True,
                    "message": f"显示全部 {len(self._history)} 条历史记录",
                    "data": {"keyword": "", "count": len(self._history)}
                }
        except Exception as e:
            logger.error(f"应用搜索筛选失败: {e}")
            return {"success": False, "message": str(e)}

    def _api_clear_search(self, **kwargs):
        """清除搜索筛选"""
        try:
            self._history_search = ""
            config = self._dump_config()
            config["history_search_keyword"] = ""
            self.update_config(config)
            return {
                "success": True,
                "message": f"已清除筛选，显示全部 {len(self._history)} 条历史记录",
                "data": {"keyword": "", "count": len(self._history)}
            }
        except Exception as e:
            logger.error(f"清除筛选失败: {e}")
            return {"success": False, "message": str(e)}

    def _api_retranslate(self, **kwargs):
        """重新翻译指定条目"""
        try:
            item_id = ""
            if "item_id" in kwargs:
                item_id = str(kwargs["item_id"])
            elif kwargs.get("data"):
                data = kwargs["data"]
                if isinstance(data, dict):
                    item_id = str(data.get("item_id", ""))
                else:
                    item_id = str(data)
            elif kwargs.get("form"):
                form = kwargs["form"]
                if isinstance(form, dict):
                    item_id = str(form.get("item_id", ""))
            elif kwargs.get("itemId"):
                item_id = str(kwargs["itemId"])
            
            if not item_id or item_id == "None":
                return {"success": False, "message": "缺少 item_id 参数"}
            
            # 从历史记录中查找条目信息
            history_item = None
            for h in reversed(self._history):
                if str(h.get("item_id", "")) == str(item_id):
                    history_item = h
                    break
            
            if not history_item:
                return {"success": False, "message": "未在历史记录中找到该条目"}
            
            # 获取条目详情并重新翻译
            services = self._get_all_emby_services()
            if not services:
                return {"success": False, "message": "无可用 Emby 服务器"}
            
            # 从 key 中解析服务器标识
            item_key = None
            for key in self._processed:
                if key.endswith(f":{item_id}"):
                    item_key = key
                    break
            
            if item_key:
                skey = item_key.split(":")[0]
                svc = next((s for s in services if self._get_server_identifier(s) == skey), services[0])
            else:
                svc = services[0]
            
            url = self._get_service_url(svc)
            api_key = self._get_service_api_key(svc)
            user_id = self._get_service_user_id(svc)
            client = EmbyClient(url, api_key, svc, user_id=user_id)
            
            # 获取条目详情
            item = client.fetch_item(svc, item_id)
            if not item:
                return {"success": False, "message": f"无法获取条目详情: {item_id}"}
            
            # 移除该条目的缓存，强制重新翻译
            key = f"{self._get_server_identifier(svc)}:{item_id}"
            with self._state_lock:
                if key in self._processed:
                    del self._processed[key]
            
            # 重新翻译
            self._force_refresh = True
            translated, failed = self._process_item(client, svc, self._get_server_identifier(svc), item, history_item.get("library", ""))
            
            return {
                "success": True, 
                "message": f"重新翻译完成: 翻译 {translated} 条, 失败 {failed} 条",
                "data": {"translated": translated, "failed": failed}
            }
        except Exception as e:
            logger.error(f"重新翻译失败: {e}")
            return {"success": False, "message": str(e)}

    def _api_search_history(self, **kwargs):
        """搜索翻译历史 - 存储关键词并过滤"""
        try:
            keyword = ""
            if "keyword" in kwargs:
                keyword = str(kwargs["keyword"])
            elif "q" in kwargs:
                keyword = str(kwargs["q"])
            elif kwargs.get("data"):
                data = kwargs["data"]
                if isinstance(data, dict):
                    keyword = str(data.get("keyword", "") or data.get("q", ""))
                else:
                    keyword = str(data)
            elif kwargs.get("form"):
                form = kwargs["form"]
                if isinstance(form, dict):
                    keyword = str(form.get("keyword", "") or form.get("q", ""))
            
            keyword = keyword.strip()
            self._history_search = keyword
            
            history = list(self._history)
            if keyword:
                kw = keyword.lower()
                history = [h for h in history if
                    kw in str(h.get("title", "")).lower() or
                    kw in str(h.get("library", "")).lower() or
                    kw in str(h.get("year", "")).lower() or
                    kw in str(h.get("item_id", "")).lower()
                ]
            
            # 返回最近的 limit 条
            history = history[-limit:]
            
            return {
                "success": True,
                "data": {
                    "total": len(history),
                    "history": history
                }
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

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
                emby_client=self._emby,
                name_cache=self._name_cache,
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
            timeout = self._llm_timeout or 120
            self._llm = LLMClient(
                base_url=base_url,
                api_key=api_key,
                model=model,
                prompt_template=self._prompt_template or DEFAULT_PROMPT,
                timeout=timeout,
            )
            logger.info(f"LLM 客户端初始化成功: {self._llm.model}")
        except Exception as e:
            logger.error(f"LLM 初始化失败: {e}")
            self._llm = None

    def _refresh_llm(self):
        """重新读取 MP 系统 LLM 配置并刷新客户端（不清除插件自定义配置）"""
        if self._llm is not None:
            old_model = getattr(self._llm, 'model', '')
        else:
            old_model = '未初始化'
        self._init_llm()
        if self._translator:
            self._translator._llm = self._llm
        new_model = getattr(self._llm, 'model', '') if self._llm else '未配置'
        logger.info(f"LLM 刷新完成: {old_model} → {new_model}")
        return old_model, new_model



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
        api_key = getattr(inst, '_apikey', None) or getattr(service, 'api_key', '') or getattr(service, 'apikey', '') or ''
        return api_key

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
            logger.info(f"MediaServerHelper 返回 {len(services)} 个服务，其中 Emby {len(emby_services)} 个")
            for s in emby_services:
                logger.info(f"  - {getattr(s, 'name', '?')}: {self._get_service_url(s)}")
            return emby_services
        except Exception as e:
            logger.error(f"获取 Emby 服务列表失败: {e}\n{traceback.format_exc()}")
            return []

    def _get_server_identifier(self, service: ServiceInfo) -> str:
        name = getattr(service, 'name', '') or ''
        url = self._get_service_url(service)
        if url:
            parsed = urlparse(url)
            host = parsed.hostname or ''
            port = parsed.port
            if not port:
                port = 8096 if parsed.scheme == 'http' else 8920
        else:
            host = ''
            port = ''
        base = f"{name}_{host}_{port}".strip('_')
        return re.sub(r'[^a-zA-Z0-9_-]', '_', base) or "default"

    def _get_library_options(self) -> List[Dict[str, str]]:
        options = []
        try:
            services = self._get_all_emby_services()
            logger.info(f"检测到 {len(services)} 个 Emby 服务")
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
            logger.error(f"获取媒体库列表失败: {e}\n{traceback.format_exc()}")
        return options

    # ============================================================
    # 扫描引擎
    # ============================================================
    def _scan_worker(self, force: bool = False):
        if not force and self._is_running:
            logger.info("扫描已在运行中，跳过")
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
        total_translated = 0
        total_failed = 0
        try:
            logger.info("=" * 50)
            logger.info("开始扫描 Emby 演职人员...")
            services = self._get_all_emby_services()
            if not services:
                logger.warning("无可用 Emby 服务器，扫描终止")
                self._is_running = False
                self._save_state()
                return

            self._progress_servers_total = len(services)
            target_libs = self._libraries or []
            grand_total_items = 0

            # 第一遍：计算总条目数用于进度
            all_tasks = []
            for svc in services:
                if self._stop_requested:
                    logger.info("扫描已请求停止（预扫描阶段）")
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
                    lib_name = lib.get("Name", "?")
                    grand_total_items += 1
                    all_tasks.append((svc, skey, client, lib_id, lib_name))

            self._progress_total = grand_total_items
            logger.info(f"共 {len(all_tasks)} 个媒体库待扫描")

            # 第二遍：实际扫描
            for svc, skey, client, lib_id, lib_name in all_tasks:
                if self._stop_requested:
                    logger.info("扫描已请求停止，保存进度后退出")
                    break
                self._progress_current_library = f"[{getattr(svc,'name','?')}] {lib_name}"
                logger.info(f"📂 扫描媒体库: {self._progress_current_library}")
                translated, failed = self._scan_library(client, svc, skey, lib_id, lib_name)
                total_translated += translated
                total_failed += failed
                self._progress_done += 1
                self._auto_save()

            self._progress_servers_done = self._progress_servers_total
            logger.info(f"扫描完成: 翻译 {total_translated} 条, 失败 {total_failed} 条")
            
            # 发送扫描完成通知
            if self._notify_on_complete:
                try:
                    hit_rate = round(self._cache_hits / max(self._cache_hits + self._cache_misses, 1) * 100, 1)
                    self.post_message(
                        mtype=NotificationType.Manual,
                        title=self.plugin_name,
                        text=f"扫描完成：翻译 {total_translated} 条，失败 {total_failed} 条，缓存命中率 {hit_rate}%"
                    )
                    logger.info("已发送扫描完成通知")
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
            logger.info(f"扫描线程结束，状态已保存")

    def _scan_library(self, client: EmbyClient, svc: ServiceInfo, skey: str, lib_id: str, lib_name: str) -> Tuple[int, int]:
        """分页扫描单个媒体库，返回 (翻译数, 失败数)"""
        translated = 0
        failed = 0
        skipped = 0
        start = 0
        page_size = 50
        page_num = 0
        while True:
            if self._stop_requested:
                logger.info("扫描已请求停止（分页循环中）")
                break
            try:
                page_num += 1
                data = client.fetch_items_page(svc, lib_id, limit=page_size, start_index=start)
                items = (data or {}).get("Items", []) or []
                if not items:
                    logger.info(f"  第 {page_num} 页: 无更多条目，扫描结束")
                    break
                logger.info(f"  第 {page_num} 页: 获取 {len(items)} 个条目 (start={start})")
                for item in items:
                    if self._stop_requested:
                        break
                    try:
                        t, f = self._process_item(client, svc, skey, item, lib_name)
                        translated += t
                        failed += f
                    except Exception as e:
                        logger.error(f"  处理条目异常: {e}\n{traceback.format_exc()}")
                        failed += 1
                    # 使用 sleep 等待
                    if self._stop_requested:
                        break
                    time.sleep(self._delay)
                if len(items) < page_size:
                    logger.info(f"  本页 {len(items)} 条已处理，无更多数据")
                    break
                start += page_size
            except Exception as e:
                logger.error(f"  分页获取失败 (start={start}): {e}\n{traceback.format_exc()}")
                break
        logger.info(f"  媒体库 [{lib_name}] 扫描完成: 翻译 {translated}, 失败 {failed}")
        return translated, failed

    def _process_item(self, client: EmbyClient, svc: ServiceInfo, skey: str, item: dict, lib_name: str = "") -> Tuple[int, int]:
        """处理单个条目，返回 (翻译数, 失败数)"""
        item_id = str(item.get("Id", ""))
        title = item.get("Name", "")
        year = item.get("ProductionYear") or (item.get("PremiereDate", "")[:4] if item.get("PremiereDate") else "")
        item_type = item.get("Type", "")
        # 显示用名称：Episode 取 SeriesName，Series/Movie 用 Name
        display_title = title
        if item_type == "Episode":
            series_name = item.get("SeriesName", "") or title
            season_num = item.get("SeasonNumber", "")
            episode_num = item.get("EpisodeNumber", "")
            if season_num and episode_num:
                display_title = f"{series_name} S{season_num:02d}E{episode_num:02d}"
            elif series_name:
                display_title = series_name
        key = f"{skey}:{item_id}"

        self._progress_current_title = display_title

        # 去重检查
        if not self._force_refresh and key in self._processed:
            logger.debug(f"  [{item_id}] {display_title} ({year}) — 已处理，跳过")
            return 0, 0

        people = item.get("People", []) or []
        if not people:
            logger.debug(f"  [{item_id}] {display_title} ({year}) — 无演职人员，跳过")
            return 0, 0

        # 筛选需要翻译的人名（Name）和角色名（Role）
        to_translate = []  # [(原文, 字段类型(Name/Role), 人员索引), ...]
        skip_reasons = []
        cached_translations = {}  # 从缓存中获取的翻译结果

        for idx, p in enumerate(people):
            ptype = p.get("Type", "Actor")
            name = p.get("Name", "").strip()
            role = p.get("Role", "").strip()

            # 类型过滤（仅在非「全部翻译」模式下生效）
            name_type_ok = True
            if not self._translate_all:
                name_type_ok = {
                    "Actor": self._translate_actor,
                    "Director": self._translate_director,
                    "Writer": self._translate_writer,
                    "Producer": self._translate_producer,
                    "VoiceActor": self._translate_actor,  # 声优归入演员类型
                }.get(ptype, False)

            # 第一行：人名（Name）—— 受类型过滤控制
            if name and (self._translate_all or name_type_ok):
                # 中文文本永远不发送给 LLM，直接跳过
                if self._looks_like_chinese(name):
                    skip_reasons.append(f"{name}(人名已是中文)")
                else:
                    # 查缓存
                    cached = self._get_cached_value(self._name_cache, name)
                    if cached:
                        cached_translations[name] = cached
                        self._cache_hits += 1
                        skip_reasons.append(f"{name}(缓存命中)")
                    else:
                        self._cache_misses += 1
                        to_translate.append((name, "Name", idx, ptype))
            elif name and not (self._translate_all or name_type_ok):
                skip_reasons.append(f"{name}({ptype}未启用)")

            # 第二行：角色名（Role）—— 独立于类型过滤
            if role and (self._translate_role or self._translate_all):
                # 中文文本永远不发送给 LLM，直接跳过
                if self._looks_like_chinese(role):
                    skip_reasons.append(f"{role}(角色已是中文)")
                else:
                    # 查角色缓存
                    cached = self._get_cached_value(self._role_cache, role)
                    if cached:
                        cached_translations[role] = cached
                        self._cache_hits += 1
                        skip_reasons.append(f"{role}(缓存命中)")
                    else:
                        self._cache_misses += 1
                        to_translate.append((role, "Role", idx, ptype))

        # 合并缓存翻译结果
        translations = dict(cached_translations)
        logger_hits = len(cached_translations)
        logger_misses = len(to_translate)

        if not to_translate:
            hit_info = f"缓存命中 {len(cached_translations)} 条" if cached_translations else "无缓存命中"
            logger.info(f"  [{item_id}] {display_title} ({year}) — 无需翻译 (共 {len(people)} 人，{hit_info}，跳过: {', '.join(skip_reasons[:3])}{'...' if len(skip_reasons) > 3 else ''})")
            if cached_translations:
                # 有缓存命中需要写回
                new_people = self._build_new_people(people, cached_translations)
                lock = self._lock_cast
                logger.info(f"    正在写入 Emby (缓存翻译 {len(cached_translations)} 条)...")
                updated = client.update_people(svc, item_id, new_people, item_data=item, lock_cast=lock)
                if updated > 0:
                    self._post_translate_hook(key, display_title, year, item_id, cached_translations, lock, lib_name)
                    return len(cached_translations), 0
            return 0, 0

        # 限制每部作品翻译条数（人名 + 角色名合计）
        to_translate = to_translate[:self._max_people_per_title]
        name_count = sum(1 for t in to_translate if t[1] == "Name")
        role_count = sum(1 for t in to_translate if t[1] == "Role")
        logger.info(f"  [{item_id}] {display_title} ({year}) [{item_type}] — 待翻译 {len(to_translate)} 条 (人名 {name_count}, 角色 {role_count}): {', '.join(f'{t[0]}({t[1]})' for t in to_translate[:5])}{'...' if len(to_translate) > 5 else ''}")

        # 繁简转换优先（同时处理人名和角色名）
        remaining = []
        seen_texts = set()
        for text, field, idx, ptype in to_translate:
            if text in seen_texts:
                continue
            seen_texts.add(text)
            if HAS_ZHCONV and any(0x4E00 <= ord(c) <= 0x9FFF for c in text):
                try:
                    simplified = zhconv.convert(text, 'zh-cn')
                    if simplified != text:
                        translations[text] = simplified
                        logger.debug(f"    繁简转换: {text} → {simplified}")
                        # 繁简转换结果也存入缓存
                        cache_store = self._name_cache if field == "Name" else self._role_cache
                        self._set_cached_value(cache_store, text, simplified)
                        continue
                except Exception:
                    pass
            remaining.append(text)

        # LLM 翻译剩余文本（去重后）
        if remaining and self._llm:
            # 停止检查：LLM 调用前
            if self._stop_requested:
                logger.info(f"    已请求停止，跳过 LLM 调用")
                return 0, 0
            try:
                logger.info(f"    调用 LLM 翻译 {len(remaining)} 条文本...")
                result = self._llm.translate_terms(title, year, remaining)
                if isinstance(result, dict):
                    translations.update(result)
                    # LLM 结果写入缓存
                    for orig, trans in result.items():
                        if trans and trans != orig:
                            for text, field, idx, ptype in to_translate:
                                if text == orig:
                                    cache_store = self._name_cache if field == "Name" else self._role_cache
                                    self._set_cached_value(cache_store, orig, trans)
                                    break
                    logger.info(f"    LLM 返回 {len(result)} 个翻译结果")
            except Exception as e:
                logger.error(f"    LLM 翻译失败 [{display_title}]: {e}")
                return 0, 1

        if not translations:
            logger.info(f"    无有效翻译结果")
            return 0, 0

        # 构建新 People 列表
        new_people = self._build_new_people(people, translations)

        # 停止检查：写回前
        if self._stop_requested:
            logger.info(f"    已请求停止，跳过 Emby 写入")
            return 0, 0

        # 写回 Emby
        lock = self._lock_cast
        logger.info(f"    正在写入 Emby ({len(translations)} 条翻译)...")
        updated = client.update_people(svc, item_id, new_people, item_data=item, lock_cast=lock)

        if updated > 0:
            self._post_translate_hook(key, display_title, year, item_id, translations, lock, lib_name)
            return len(translations), 0
        else:
            logger.warning(f"  ⚠️ [{item_id}] {display_title} ({year}) — 写回失败")
            return 0, 0

    def _build_new_people(self, people, translations):
        """构建新 People 列表 —— 同时更新 Name 和 Role"""
        new_people = []
        for p in people:
            np = dict(p)
            cur_name = np.get("Name", "")
            if cur_name in translations:
                np["Name"] = translations[cur_name]
            cur_role = np.get("Role", "")
            if cur_role and cur_role in translations:
                np["Role"] = translations[cur_role]
            new_people.append(np)
        return new_people

    def _get_cached_value(self, cache_store, key):
        """从缓存中获取翻译值"""
        with self._state_lock:
            for lang_cache in cache_store.values():
                if key in lang_cache:
                    return lang_cache[key]
        return None

    def _set_cached_value(self, cache_store, key, value, lang="default"):
        """将翻译值存入缓存"""
        with self._state_lock:
            if lang not in cache_store:
                cache_store[lang] = {}
            cache_store[lang][key] = value

    def _post_translate_hook(self, key, display_title, year, item_id, translations, lock, lib_name=""):
        """翻译成功后：更新状态、写日志"""
        with self._state_lock:
            self._processed[key] = datetime.now().isoformat()
            self._history.append({
                "time": datetime.now().isoformat(timespec='seconds'),
                "library": lib_name,
                "title": display_title,
                "year": year,
                "item_id": item_id,
                "n_trans": len(translations),
                "status": "ok",
                "cast_locked": lock,
            })
            if len(self._history) > self._MAX_HISTORY:
                self._history = self._history[-self._MAX_HISTORY:]
        logger.info(f"  ✅ [{item_id}] {display_title} ({year}) — 翻译 {len(translations)} 个, 锁定={lock}")
        for orig, trans in list(translations.items())[:3]:
            logger.info(f"      {orig} → {trans}")

    # ============================================================
    # 辅助
    # ============================================================
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
        """停止服务 — 请求扫描安全退出"""
        self._stop_requested = True
        if self._is_running:
            logger.info("正在请求扫描任务安全退出...")
        self._save_state()

    # ============================================================
    # Webhook 入库自动翻译
    # ============================================================
    @eventmanager.register(EventType.WebhookMessage)
    def handle_webhook(self, event: Event):
        """监听 Emby Webhook 入库事件，延迟后自动翻译单条目"""
        logger.info(f"[Webhook] 收到 Webhook 事件: event_type={event.event_type}, source={event.source}, raw_data={event.event_data}")
        data = event.event_data or {}
        if "emby" not in str(data.get("source", "")).lower():
            logger.info(f"[Webhook] 来源不匹配（非 Emby），跳过: source={data.get('source')}")
            return
        nt = str(data.get("NotificationType", "")).lower()
        et = str(data.get("Type", "")).lower()
        if not any(k in nt or k in et for k in ["itemadded", "item.added", "library.new", "added"]):
            logger.info(f"[Webhook] 事件类型不匹配，跳过: NotificationType={nt}, Type={et}")
            return
        item_id = data.get("ItemId") or data.get("item_id") or data.get("Id") or ""
        server_id = data.get("ServerId") or data.get("server_id") or ""
        if not item_id:
            logger.info("[Webhook] 收到入库事件但无 ItemId，跳过")
            return
        logger.info(f"[Webhook] 收到入库事件: ItemId={item_id}, ServerId={server_id}")
        try:
            self.post_message(
                mtype=NotificationType.Manual,
                title=self.plugin_name,
                text=f"收到 Emby 入库事件: ItemId={item_id}，{delay}秒后开始翻译"
            )
        except Exception:
            pass
        delay = getattr(self, '_webhook_delay', 60)
        threading.Thread(
            target=self._delayed_scan_item,
            kwargs={"item_id": item_id, "server_id": server_id, "delay": delay},
            daemon=True
        ).start()

    def _delayed_scan_item(self, item_id, server_id, delay):
        """延迟扫描单条目（等待 Emby 刮源完成）"""
        try:
            logger.info(f"[Webhook] 等待 {delay} 秒后扫描 ItemId={item_id}...")
            time.sleep(delay)
            if self._stop_requested:
                logger.info("[Webhook] 已请求停止，取消扫描")
                return
            services = self._get_all_emby_services()
            if not services:
                logger.warning("[Webhook] 无可用 Emby 服务器")
                return
            svc = next(
                (s for s in services if self._get_server_identifier(s) == server_id),
                services[0]
            )
            url = self._get_service_url(svc)
            api_key = self._get_service_api_key(svc)
            user_id = self._get_service_user_id(svc)
            client = EmbyClient(url, api_key, svc, user_id=user_id)
            item = client.fetch_item(svc, item_id)
            if not item:
                logger.warning(f"[Webhook] 无法获取条目详情: {item_id}")
                return
            self._translate_single_item(client, svc, item_id, item)
        except Exception as e:
            logger.error(f"[Webhook] 扫描异常: {e}\n{traceback.format_exc()}")

    def _translate_single_item(self, client, svc, item_id, item):
        """翻译单个条目（Webhook 触发）"""
        title = item.get("Name", "")
        year = item.get("ProductionYear") or (item.get("PremiereDate", "")[:4] if item.get("PremiereDate") else "")
        item_type = item.get("Type", "")
        display_title = title
        if item_type == "Episode":
            series_name = item.get("SeriesName", "") or title
            season_num = item.get("SeasonNumber", "")
            episode_num = item.get("EpisodeNumber", "")
            if season_num and episode_num:
                display_title = f"{series_name} S{season_num:02d}E{episode_num:02d}"
            elif series_name:
                display_title = series_name
        key = f"{self._get_server_identifier(svc)}:{item_id}"

        people = item.get("People", []) or []
        if not people:
            logger.info(f"[Webhook] [{item_id}] {display_title} ({year}) — 无演职人员，跳过")
            return

        to_translate = []
        skip_reasons = []
        cached_translations = {}

        for idx, p in enumerate(people):
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
                    skip_reasons.append(f"{name}(人名已是中文)")
                else:
                    cached = self._get_cached_value(self._name_cache, name)
                    if cached:
                        cached_translations[name] = cached
                        self._cache_hits += 1
                        skip_reasons.append(f"{name}(缓存命中)")
                    else:
                        self._cache_misses += 1
                        to_translate.append((name, "Name", idx, ptype))

            if role and (self._translate_role or self._translate_all):
                if self._looks_like_chinese(role):
                    skip_reasons.append(f"{role}(角色已是中文)")
                else:
                    cached = self._get_cached_value(self._role_cache, role)
                    if cached:
                        cached_translations[role] = cached
                        self._cache_hits += 1
                        skip_reasons.append(f"{role}(缓存命中)")
                    else:
                        self._cache_misses += 1
                        to_translate.append((role, "Role", idx, ptype))

        translations = dict(cached_translations)

        if not to_translate:
            if cached_translations:
                new_people = self._build_new_people(people, cached_translations)
                lock = self._lock_cast
                logger.info(f"[Webhook] [{item_id}] {display_title} ({year}) — 缓存命中 {len(cached_translations)} 条，写入 Emby...")
                updated = client.update_people(svc, item_id, new_people, item_data=item, lock_cast=lock)
                if updated > 0:
                    self._post_translate_hook(key, display_title, year, item_id, cached_translations, lock, "")
                    self._save_state()
            return

        to_translate = to_translate[:self._max_people_per_title]

        remaining = []
        seen_texts = set()
        for text, field, idx, ptype in to_translate:
            if text in seen_texts:
                continue
            seen_texts.add(text)
            if HAS_ZHCONV and any(0x4E00 <= ord(c) <= 0x9FFF for c in text):
                try:
                    simplified = zhconv.convert(text, 'zh-cn')
                    if simplified != text:
                        translations[text] = simplified
                        cache_store = self._name_cache if field == "Name" else self._role_cache
                        self._set_cached_value(cache_store, text, simplified)
                        continue
                except Exception:
                    pass
            remaining.append(text)

        if remaining and self._llm:
            try:
                logger.info(f"[Webhook] [{item_id}] {display_title} ({year}) — LLM 翻译 {len(remaining)} 条...")
                result = self._llm.translate_terms(title, year, remaining)
                if isinstance(result, dict):
                    translations.update(result)
                    for orig, trans in result.items():
                        if trans and trans != orig:
                            for text, field, idx, ptype in to_translate:
                                if text == orig:
                                    cache_store = self._name_cache if field == "Name" else self._role_cache
                                    self._set_cached_value(cache_store, orig, trans)
                                    break
            except Exception as e:
                logger.error(f"[Webhook] LLM 翻译失败 [{display_title}]: {e}")
                return

        if not translations:
            logger.info(f"[Webhook] [{item_id}] {display_title} ({year}) — 无有效翻译结果")
            return

        new_people = self._build_new_people(people, translations)
        lock = self._lock_cast
        logger.info(f"[Webhook] [{item_id}] {display_title} ({year}) — 写入 Emby ({len(translations)} 条翻译)...")
        updated = client.update_people(svc, item_id, new_people, item_data=item, lock_cast=lock)
        if updated > 0:
            self._post_translate_hook(key, display_title, year, item_id, translations, lock, "")
            self._save_state()
            logger.info(f"[Webhook] 翻译完成: {display_title} ({year}) — 翻译 {len(translations)} 条")