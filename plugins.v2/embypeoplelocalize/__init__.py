"""
EmbyPeopleLocalize - Emby 演职人员中文化

利用大模型（HTTP直连）把 Emby 中英文/罗马音/日文人名翻译为正式中文名并写回。
用户选择媒体库则只扫描选中的，未选择则扫描全部（所有服务器所有库）。
支持扫描电影、剧集、季、单集，自带人名缓存和条目级缓存。
支持分页获取、People专用端点更新（自动fallback整条更新）。
"""

import json
import os
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import requests as _requests
import random

# ========== 字幕插件同款：openai SDK + httpx 代理 初始化（失败则降级为纯requests）==========
try:
    import openai as _openai_mod  # noqa: F401
    import httpx as _httpx_mod  # noqa: F401
    _HAS_OPENAI_SDK = True
except Exception:
    _HAS_OPENAI_SDK = False
    _openai_mod = None
    _httpx_mod = None

# 屏蔽 verify=False 时的 InsecureRequestWarning，日志里不会堆满无关告警
try:
    from urllib3 import disable_warnings as _urllib3_disable_warnings
    from urllib3.exceptions import InsecureRequestWarning as _InsecureRequestWarning
    _urllib3_disable_warnings(_InsecureRequestWarning)
except Exception:
    try:
        import warnings as _warnings
        import urllib3 as _urllib3
        _warnings.filterwarnings("ignore", category=_urllib3.exceptions.InsecureRequestWarning)
    except Exception:
        pass

from app.core.config import settings
from app.core.event import eventmanager, Event
from app.chain.mediaserver import MediaServerChain
from app.helper.mediaserver import MediaServerHelper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import ServiceInfo
from app.schemas.types import EventType
from app.utils.http import RequestUtils
from app.utils.string import StringUtils

# 尝试导入简繁转换库（可选）
try:
    import zhconv
    HAS_ZHCONV = True
except ImportError:
    HAS_ZHCONV = False


# ========== 默认提示词 ==========
DEFAULT_PROMPT = """你是一位世界级的影视专家，扮演一个只返回 JSON 的 API。
你的任务是利用提供的影视上下文，准确地将外语或拼音的演员名和角色名翻译成 **简体中文**。

**输入格式：**
你将收到一个包含 `context`（含 `title` 和 `year`）和 `terms`（待翻译字符串列表）的 JSON 对象。

**你的策略：**
1. **利用上下文：** 使用 `title` 和 `year` 来确定具体的剧集/电影。在该特定作品的背景下，找到 `terms` 的官方或最受认可的中文译名。
2. **翻译拼音/英文/日文：** 将非中文的读音翻译成汉字。
3. **【核心指令】目标语言永远是简体中文。**
4. **兜底：** 如果无法翻译，使用原始字符串。

**输出格式（强制）：**
你 **必须** 返回一个有效的 JSON 对象，将每个原始词条映射到其中文翻译。严禁包含其他文本或 markdown 标记。

【本次实际输入】
context:
{{
  "title": {title_json},
  "year": {year_json}
}}
terms: {terms_json}
"""


class EmbyPeopleLocalize(_PluginBase):
    plugin_name = "Emby 演职人员中文化"
    plugin_desc = "利用大模型把Emby里英文/罗马音/日文人名翻译为正式中文名并写回（可选库/全库）"
    plugin_icon = "embypeoplelocalize.jpg"
    plugin_version = "0.3.0"
    plugin_author = "local"
    plugin_config_prefix = "embypeoplelocalize_"
    plugin_order = 27
    auth_level = 1

    # 配置项
    _enabled: bool = False
    _onlyonce: bool = False
    _cron: str = "0 4 * * *"
    _libraries: List[str] = []
    _prompt_template: str = ""
    _translate_actor: bool = True
    _translate_voice_actor: bool = True
    _translate_director: bool = False
    _translate_writer: bool = False
    _translate_producer: bool = False
    _translate_all: bool = False
    _max_people_per_title: int = 15
    _max_people_per_batch: int = 5
    _overwrite_chinese: bool = False
    _force_refresh: bool = False
    _delay: int = 2

    # 运行时
    _scheduler = None
    _ms_helper: Optional[MediaServerHelper] = None
    _event = threading.Event()
    _name_cache: Dict[str, Dict[str, str]] = {}
    _processed: Dict[str, str] = {}
    _history: List[Dict[str, Any]] = []
    _MAX_HISTORY = 200
    _SAVE_INTERVAL = 50  # 每处理多少个条目保存一次缓存
    # LLM 客户端（openai SDK，同 AI 字幕插件实现）
    _llm_client = None
    _llm_model: str = ""
    _llm_last_error: str = ""

    @property
    def private_attrs(self) -> List[str]:
        return []

    # ==================== 与 AI 字幕插件同款的 LLM 客户端构建 ====================
    def _get_proxy_for_llm(self) -> Optional[Dict[str, str]]:
        """解析 settings.PROXY（兼容 dict/list/str），返回 requests/openai 通用格式或 None"""
        proxies: Optional[Dict[str, str]] = None
        try:
            raw_proxy = getattr(settings, 'PROXY', None)
            if not raw_proxy:
                return None
            if isinstance(raw_proxy, dict):
                http_proxy = str(raw_proxy.get("http") or raw_proxy.get("https") or "").strip()
                https_proxy = str(raw_proxy.get("https") or raw_proxy.get("http") or "").strip()
                if http_proxy or https_proxy:
                    proxies = {}
                    if http_proxy:
                        proxies["http"] = http_proxy
                    if https_proxy:
                        proxies["https"] = https_proxy
            elif isinstance(raw_proxy, (list, tuple)):
                for item in raw_proxy:
                    s = str(item or "").strip()
                    if s and s.lower().startswith(("http://", "https://", "socks5://")):
                        proxies = {"http": s, "https": s}
                        break
            else:
                s = str(raw_proxy).strip()
                if s and s.lower().startswith(("http://", "https://", "socks5://")):
                    proxies = {"http": s, "https": s}
        except Exception as e:
            logger.debug(f"解析 settings.PROXY 失败，忽略: {e}")
            return None
        return proxies

    def _build_llm_client(self):
        """按 AI 字幕生成(联动版) 方式构建 openai SDK 客户端，失败则留空（降级requests）"""
        base_url = str(getattr(settings, 'LLM_BASE_URL', '') or '').rstrip('/')
        api_key = str(getattr(settings, 'LLM_API_KEY', '') or '')
        model = str(getattr(settings, 'LLM_MODEL', '') or '')
        if not base_url or not api_key:
            self._llm_client = None
            self._llm_model = model
            return
        # 兼容：若 base_url 不以 /v1 结尾，则 SDK 自动补 /v1（同字幕插件compatible=False分支）
        if base_url.endswith("/v1"):
            sdk_base = base_url[:-3].rstrip('/')
            compatible = False
        elif "/v1" in base_url:
            sdk_base = base_url
            compatible = True
        else:
            sdk_base = base_url
            compatible = False
        proxy_cfg = self._get_proxy_for_llm()
        try:
            if _HAS_OPENAI_SDK:
                http_client = None
                if _httpx_mod and proxy_cfg and proxy_cfg.get("https"):
                    # httpx 代理可传单个 https URL（同字幕插件写法）
                    try:
                        transport = _httpx_mod.HTTPTransport(retries=1)
                        http_client = _httpx_mod.Client(
                            proxies=proxy_cfg.get("https") or proxy_cfg.get("http"),
                            timeout=_httpx_mod.Timeout(connect=10.0, read=60.0, write=15.0, pool=10.0),
                            transport=transport,
                            verify=False,
                        )
                    except Exception as e:
                        logger.debug(f"构建 httpx 代理客户端失败，走默认: {e}")
                        http_client = None
                base_url_final = sdk_base if compatible else f"{sdk_base}/v1"
                self._llm_client = _openai_mod.OpenAI(
                    api_key=api_key,
                    base_url=base_url_final,
                    http_client=http_client,
                    timeout=(10.0, 60.0),
                    max_retries=0,
                )
                self._llm_model = model
                self._llm_last_error = ""
            else:
                self._llm_client = None
                self._llm_model = model
        except Exception as e:
            logger.warning(f"构建 openai SDK LLM 客户端失败，后续降级 requests: {e}")
            self._llm_client = None
            self._llm_model = model

    def init_plugin(self, config: dict = None):
        self.stop_service()
        self._event.set()
        if config:
            self._enabled = bool(config.get("enabled", False))
            self._onlyonce = bool(config.get("onlyonce", False))
            self._cron = str(config.get("cron", "0 4 * * *"))
            self._libraries = list(config.get("libraries", []) or [])
            self._prompt_template = str(config.get("prompt_template") or DEFAULT_PROMPT)
            self._translate_actor = bool(config.get("translate_actor", True))
            self._translate_voice_actor = bool(config.get("translate_voice_actor", True))
            self._translate_director = bool(config.get("translate_director", False))
            self._translate_writer = bool(config.get("translate_writer", False))
            self._translate_producer = bool(config.get("translate_producer", False))
            self._translate_all = bool(config.get("translate_all", False))
            self._max_people_per_title = int(config.get("max_people_per_title", 15))
            self._max_people_per_batch = int(config.get("max_people_per_batch", 5))
            self._overwrite_chinese = bool(config.get("overwrite_chinese", False))
            self._force_refresh = bool(config.get("force_refresh", False))
            self._delay = int(config.get("delay", 2))

        if self._enabled:
            self._ms_helper = MediaServerHelper()
            # 构建 openai SDK LLM 客户端（同 AI 字幕插件），失败再降级 requests
            self._build_llm_client()
            logger.info(f"{self.plugin_name}: LLM 模式={'openai SDK' if self._llm_client else 'requests 兜底'}"
                        + (f"，model={self._llm_model}" if self._llm_model else ""))
            data = self.get_data("cache") or {}
            if self._force_refresh:
                logger.info(f"{self.plugin_name}: 强制刷新，清空所有缓存")
                self._name_cache = {}
                self._processed = {}
            else:
                self._name_cache = data.get("name_cache", {}) or {}
                self._processed = data.get("processed", {}) or {}
            self._history = list(data.get("history", []) or [])[:self._MAX_HISTORY]
            logger.info(f"{self.plugin_name} v{self.plugin_version} 初始化成功 "
                        f"(缓存 {len(self._name_cache)} 条, 历史 {len(self._history)} 条)")

        if self._onlyonce:
            self._onlyonce = False
            self._force_refresh = False
            self.update_config({
                "enabled": self._enabled,
                "onlyonce": self._onlyonce,
                "cron": self._cron,
                "libraries": self._libraries,
                "prompt_template": self._prompt_template,
                "translate_actor": self._translate_actor,
                "translate_voice_actor": self._translate_voice_actor,
                "translate_director": self._translate_director,
                "translate_writer": self._translate_writer,
                "translate_producer": self._translate_producer,
                "translate_all": self._translate_all,
                "max_people_per_title": self._max_people_per_title,
                "max_people_per_batch": self._max_people_per_batch,
                "overwrite_chinese": self._overwrite_chinese,
                "force_refresh": self._force_refresh,
                "delay": self._delay,
            })
            if not self._scheduler:
                self._scheduler = BackgroundScheduler(timezone=settings.TZ)
                self._scheduler.add_job(
                    func=self.sync_library,
                    trigger="date",
                    run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3)
                )
                self._scheduler.start()
            logger.info(f"{self.plugin_name}：立即运行一次")

    def _save_cache(self):
        """保存缓存（全部）——任何异常都吞掉，绝对不能崩主线程"""
        try:
            self.save_data("cache", {
                "name_cache": dict(self._name_cache or {}),
                "processed": dict(self._processed or {}),
                "history": list(self._history or [])[:self._MAX_HISTORY],
            })
        except Exception as e:
            logger.warning(f"保存缓存失败（不影响继续运行）: {type(e).__name__}: {e}")

    def _add_history(self, key: str, title: str, server: str, lib: str, n_trans: int, item_id: str = ""):
        """添加历史记录——任何异常吞掉，不能崩主线程"""
        try:
            if not key or n_trans <= 0:
                return
            now = datetime.now().isoformat(timespec='seconds')
            new_item = {
                "key": str(key or ""),
                "title": str(title or "")[:120],
                "server": str(server or "")[:60],
                "lib": str(lib or "")[:60],
                "n_trans": int(n_trans or 0),
                "time": now,
                "item_id": str(item_id or ""),
            }
            new_hist = [h for h in (self._history or []) if str(h.get("key") or "") != str(key)]
            new_hist.insert(0, new_item)
            self._history = new_hist[:self._MAX_HISTORY]
        except Exception as e:
            logger.warning(f"添加历史记录失败（不影响继续运行）: {type(e).__name__}: {e}")

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        return [{
            "cmd": "/people_localize",
            "desc": "Emby演职人员中文化 - 立即扫描",
            "target": "sync_library",
        }]

    def get_api(self) -> List[Dict[str, Any]]:
        return []

    def get_service(self) -> List[Dict[str, Any]]:
        if self._enabled and self._cron:
            return [{
                "id": "EmbyPeopleLocalize",
                "name": f"{self.plugin_name} 定时扫描",
                "trigger": CronTrigger.from_crontab(self._cron, timezone=settings.TZ),
                "func": self.sync_library,
                "kwargs": {}
            }]
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        servers, lib_opts = self._get_server_lib_options()
        form = [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {'component': 'VCol', 'props': {'cols': 12},
                             'content': [{'component': 'VSwitch', 'props': {'prop': 'enabled', 'model': 'enabled', 'label': '启用插件'}}]},
                        ],
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {'component': 'VCol', 'props': {'cols': 6},
                             'content': [{'component': 'VSwitch', 'props': {'prop': 'onlyonce', 'model': 'onlyonce', 'label': '立即运行一次'}}]},
                            {'component': 'VCol', 'props': {'cols': 6},
                             'content': [{'component': 'VTextField', 'props': {'prop': 'cron', 'model': 'cron', 'label': '定时扫描cron表达式', 'placeholder': '0 4 * * *'}}]},
                        ],
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {'component': 'VCol', 'props': {'cols': 12},
                             'content': [{'component': 'VSelect', 'props': {'prop': 'libraries', 'model': 'libraries', 'chips': True, 'multiple': True, 'clearable': True, 'label': '选择要扫描的媒体库（格式 服务器名:库ID，留空=全库扫描）', 'items': lib_opts}}]},
                        ],
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {'component': 'VCol', 'props': {'cols': 12},
                             'content': [{'component': 'VTextarea', 'props': {'prop': 'prompt_template', 'model': 'prompt_template', 'label': '自定义大模型提示词（占位符：{title_json} {year_json} {terms_json}）', 'rows': 10, 'placeholder': DEFAULT_PROMPT}}]},
                        ],
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {'component': 'VCol', 'props': {'cols': 4}, 'content': [{'component': 'VSwitch', 'props': {'prop': 'translate_actor', 'model': 'translate_actor', 'label': '翻译 Actor'}}]},
                            {'component': 'VCol', 'props': {'cols': 4}, 'content': [{'component': 'VSwitch', 'props': {'prop': 'translate_voice_actor', 'model': 'translate_voice_actor', 'label': '翻译 VoiceActor'}}]},
                            {'component': 'VCol', 'props': {'cols': 4}, 'content': [{'component': 'VSwitch', 'props': {'prop': 'translate_director', 'model': 'translate_director', 'label': '翻译 Director'}}]},
                        ],
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {'component': 'VCol', 'props': {'cols': 4}, 'content': [{'component': 'VSwitch', 'props': {'prop': 'translate_writer', 'model': 'translate_writer', 'label': '翻译 Writer'}}]},
                            {'component': 'VCol', 'props': {'cols': 4}, 'content': [{'component': 'VSwitch', 'props': {'prop': 'translate_producer', 'model': 'translate_producer', 'label': '翻译 Producer'}}]},
                            {'component': 'VCol', 'props': {'cols': 4}, 'content': [{'component': 'VSwitch', 'props': {'prop': 'translate_all', 'model': 'translate_all', 'label': '翻译所有类型'}}]},
                        ],
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {'component': 'VCol', 'props': {'cols': 3},
                             'content': [{'component': 'VTextField', 'props': {'prop': 'max_people_per_title', 'model': 'max_people_per_title', 'label': '每条目最多翻译人数', 'type': 'number', 'placeholder': '15'}}]},
                            {'component': 'VCol', 'props': {'cols': 3},
                             'content': [{'component': 'VTextField', 'props': {'prop': 'max_people_per_batch', 'model': 'max_people_per_batch', 'label': '单批送大模型人数', 'type': 'number', 'placeholder': '20'}}]},
                            {'component': 'VCol', 'props': {'cols': 3},
                             'content': [{'component': 'VSwitch', 'props': {'prop': 'overwrite_chinese', 'model': 'overwrite_chinese', 'label': '覆盖已有中文'}}]},
                            {'component': 'VCol', 'props': {'cols': 3},
                             'content': [{'component': 'VSwitch', 'props': {'prop': 'force_refresh', 'model': 'force_refresh', 'label': '强制刷新(清缓存)'}}]},
                        ],
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {'component': 'VCol', 'props': {'cols': 4},
                             'content': [{'component': 'VTextField', 'props': {'prop': 'delay', 'model': 'delay', 'label': '条目间延迟(秒)', 'type': 'number', 'placeholder': '2'}}]},
                        ],
                    },
                ]
            }
        ]
        defaults = {
            "enabled": self._enabled,
            "onlyonce": self._onlyonce,
            "cron": self._cron,
            "libraries": self._libraries,
            "prompt_template": self._prompt_template or DEFAULT_PROMPT,
            "translate_actor": self._translate_actor,
            "translate_voice_actor": self._translate_voice_actor,
            "translate_director": self._translate_director,
            "translate_writer": self._translate_writer,
            "translate_producer": self._translate_producer,
            "translate_all": self._translate_all,
            "max_people_per_title": self._max_people_per_title,
            "max_people_per_batch": self._max_people_per_batch,
            "overwrite_chinese": self._overwrite_chinese,
            "force_refresh": self._force_refresh,
            "delay": self._delay,
        }
        return form, defaults

    def get_page(self) -> List[dict]:
        """Vue 自定义前端接管，不再使用 VPage"""
        return []

    @staticmethod
    def get_render_mode() -> Tuple[str, str]:
        """使用自定义 Vue 前端（Module Federation）"""
        return "vue", "dist/assets"

    def get_sidebar_nav(self) -> List[Dict[str, Any]]:
        """侧边栏导航入口"""
        if not self._enabled:
            return []
        return [{
            "nav_key": "main",
            "title": "Emby 演职人员中文化",
            "icon": "mdi-translate",
            "section": "organize",
            "permission": "manage",
            "order": 27,
        }]

    def get_api(self) -> List[Dict[str, Any]]:
        """注册自定义 API 路由给 Vue 前端调用"""
        from .api import build_api_routes
        return build_api_routes(self)

    def stop_service(self):
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._event.set()
                    self._scheduler.shutdown(wait=False)
                self._scheduler = None
        except Exception as e:
            logger.debug(f"停止定时器失败: {e}")

    # ==================== 工具函数 ====================
    @staticmethod
    def _norm_name_key(name: str) -> str:
        if not name:
            return ""
        s = re.sub(r"[\s　・・\.．\-－_,，、。()（）\[\]【】\[\]【】\#'\"`~]", "", str(name))
        return s.strip().lower()

    def _get_server_lib_options(self) -> Tuple[List[str], List[dict]]:
        servers: List[str] = []
        items: List[dict] = []
        try:
            helper = MediaServerHelper()
            msc = MediaServerChain()
            emby_configs = {name: cfg for name, cfg in (helper.get_configs() or {}).items()
                            if str(getattr(cfg, "type", "") or "").lower() == "emby"}
            for server_name in emby_configs.keys():
                servers.append(server_name)
                try:
                    for lib in (msc.librarys(server_name) or []):
                        lid = str(getattr(lib, "id", "") or "")
                        lname = str(getattr(lib, "name", "") or "")
                        if lid:
                            items.append({"title": f"{server_name} - {lname}", "value": f"{server_name}:{lid}"})
                except Exception as e:
                    logger.warning(f"获取服务器 {server_name} 媒体库失败: {e}")
        except Exception as e:
            logger.warning(f"获取媒体库列表失败: {e}")
        return servers, items

    def _get_emby_info(self, service: ServiceInfo) -> Tuple[Optional[str], Optional[str]]:
        instance = getattr(service, 'instance', None)
        host = None
        apikey = None
        if instance is not None:
            host = getattr(instance, '_host', None) or getattr(instance, 'host', None)
            apikey = getattr(instance, '_apikey', None) or getattr(instance, 'apikey', None)
            if not host:
                try:
                    cfg = getattr(instance, 'config', None) or {}
                    host = cfg.get("host") or host
                    apikey = cfg.get("api_key") or apikey
                except Exception:
                    pass
        if not host:
            logger.error(f"无法获取服务 {getattr(service, 'name', '?')} 的 host")
        return (str(host).rstrip('/') if host else None), str(apikey) if apikey else None

    def _emby_get(self, service: ServiceInfo, path: str, timeout: int = 30) -> Optional[Any]:
        """对齐 EmbyBangumi声优本地化 写法：只取 instance.user 作为 UserId（GUID），其他字段全是用户名会导致404"""
        host, api_key = self._get_emby_info(service)
        if not host:
            return None
        user_id = getattr(service.instance, 'user', None) if getattr(service, 'instance', None) else None
        sep = '&' if '?' in path else '?'
        url = f"{host}{path}{sep}api_key={api_key or ''}"
        if user_id and 'UserId=' not in path and 'userid=' not in path.lower():
            url += f"&UserId={user_id}"
        try:
            resp = RequestUtils(timeout=timeout).get_res(url)
        except Exception as e:
            logger.warning(f"Emby GET 异常: {e}, url={url.split('?')[0]}")
            return None
        if resp is None:
            logger.warning(f"Emby GET 无响应: {url.split('?')[0]}")
            return None
        if resp.status_code not in (200, 201, 204):
            logger.warning(f"Emby GET {resp.status_code}: {url.split('?')[0]}")
            try:
                if resp.content:
                    body_raw = resp.content or b""
                    try:
                        body_txt = body_raw.decode("utf-8", errors="replace")
                    except Exception:
                        body_txt = str(body_raw)
                    logger.warning(f"  body: {body_txt[:300]}")
            except Exception:
                pass
            return None
        try:
            return resp.json()
        except Exception:
            return None

    def _emby_post(self, service: ServiceInfo, path: str, json: Any = None,
                   data: Any = None, headers: Optional[Dict[str, str]] = None,
                   timeout: int = 30) -> bool:
        """对齐 EmbyBangumi声优本地化 写法：只取 instance.user 作为 UserId（GUID），避免404"""
        host, api_key = self._get_emby_info(service)
        if not host:
            return False
        user_id = getattr(service.instance, 'user', None) if getattr(service, 'instance', None) else None
        sep = '&' if '?' in path else '?'
        url = f"{host}{path}{sep}api_key={api_key or ''}"
        if user_id and 'UserId=' not in path and 'userid=' not in path.lower():
            url += f"&UserId={user_id}"
        h = dict(headers or {})
        if json is not None and data is None and "Content-Type" not in h:
            h["Content-Type"] = "application/json"
        try:
            if json is not None:
                resp = RequestUtils(headers=h, timeout=timeout).post_res(url=url, json=json)
            else:
                resp = RequestUtils(headers=h, timeout=timeout).post_res(url=url, data=data)
        except Exception as e:
            logger.warning(f"Emby POST 异常: {e}, url={url.split('?')[0]}")
            return False
        if resp is None:
            logger.warning(f"Emby POST 无响应: {url.split('?')[0]}")
            return False
        if resp.status_code in (200, 201, 204):
            return True
        logger.warning(f"Emby POST {resp.status_code}: {url.split('?')[0]}")
        try:
            body_raw = resp.content or b""
            try:
                body_txt = body_raw.decode("utf-8", errors="replace")
            except Exception:
                body_txt = str(body_raw)
            logger.warning(f"  body: {body_txt[:300]}")
        except Exception:
            pass
        return False

    def _get_emby_libraries(self, service: ServiceInfo) -> List[dict]:
        user_id = None
        try:
            user_id = getattr(service.instance, 'user', None)
        except Exception:
            user_id = None
        data = None
        if user_id:
            data = self._emby_get(service, f"/Users/{user_id}/Items?Recursive=true&IncludeItemTypes=CollectionFolder&Fields=Name")
        if not data or "Items" not in data:
            vf_data = self._emby_get(service, "/Library/VirtualFolders")
            if isinstance(vf_data, list):
                return [{"id": str(vf.get("ItemId") or vf.get("Id") or vf.get("Guid") or ""),
                         "name": vf.get("Name") or ""}
                        for vf in vf_data if
                        str(vf.get("ItemId") or vf.get("Id") or vf.get("Guid") or "")]
            return []
        libraries = []
        for it in data.get("Items", []) or []:
            lid = str(it.get("Id") or it.get("Guid") or "")
            lname = it.get("Name") or ""
            if lid:
                libraries.append({"id": lid, "name": lname})
        return libraries

    # ==================== 大模型翻译（AI字幕插件同款 openai SDK + 指数退避 + requests 兜底） ====================
    def _call_llm_translate(self, title: str, names: List[str], year: Optional[str] = None) -> Dict[str, str]:
        """外层异常墙：任何异常返回空字典，不崩主线程"""
        try:
            if not names:
                return {}
            try:
                title_json = json.dumps(title, ensure_ascii=False)
                year_json = json.dumps(year if year else "", ensure_ascii=False)
                terms_json = json.dumps(names, ensure_ascii=False)
                prompt = (self._prompt_template or DEFAULT_PROMPT).format(
                    title_json=title_json, year_json=year_json, terms_json=terms_json,
                    title=title, count=len(names)
                )
            except Exception:
                fallback_payload = json.dumps({"context": {"title": title, "year": year if year else ""}, "terms": names},
                                              ensure_ascii=False)
                prompt = f"{self._prompt_template or DEFAULT_PROMPT}\n\n实际输入:\n{fallback_payload}"

            # LLM 客户端若被重建（settings 变更），则每次尝试调用时再懒构建
            if not self._llm_client and _HAS_OPENAI_SDK:
                try:
                    self._build_llm_client()
                except Exception as e:
                    logger.debug(f"懒构建LLM客户端失败，走requests: {e}")

            # 1) 优先 openai SDK（同 AI 字幕生成插件）
            raw = ""
            used_sdk = False
            if self._llm_client:
                try:
                    raw = self._try_llm_via_sdk(prompt)
                    used_sdk = bool(raw)
                except Exception as e:
                    logger.warning(f"SDK调用异常（转requests）: {type(e).__name__}: {e}")
                    raw = ""
            # 2) SDK 失败或不可用 -> requests 原生兜底（保留之前修复好的代理+头+超时）
            if not raw:
                try:
                    raw = self._try_llm_via_requests(prompt)
                except Exception as e:
                    logger.warning(f"requests调用异常: {type(e).__name__}: {e}")
                    raw = ""
            # 调试：记录到底哪种方式成功/失败
            if not raw:
                logger.debug("LLM 两种调用方式均返回空")
            else:
                logger.debug(f"LLM 返回方式={'sdk' if used_sdk else 'requests'}，长度={len(raw)}")
            return self._parse_llm_json(raw, names)
        except Exception as e:
            logger.warning(f"_call_llm_translate 总异常（返回空）: {type(e).__name__}: {e}")
            return {}

    def _try_llm_via_sdk(self, prompt: str) -> str:
        """AI 字幕插件同款：client.chat.completions.create + 遇Timeout直接跳requests不硬等。
        【优化】单条SDK只试1次，60s不回立即跳requests，绝不卡主线程。
        外层异常墙：任何异常返回空字符串，不崩主线程"""
        try:
            if not self._llm_client:
                return ""
            model = self._llm_model or "gpt-4o-mini"
            messages = [
                {"role": "system", "content": "你是一个影视人名翻译专家，只输出 JSON 对象，不要解释。"},
                {"role": "user", "content": prompt},
            ]
            last_err = ""
            # 只试1次！60s不回直接跳，绝不做第二次硬等
            try:
                completion = self._llm_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.0,
                    top_p=1.0,
                    response_format={"type": "json_object"},
                    timeout=(10.0, 60.0),
                )
                try:
                    choices = getattr(completion, "choices", None) or []
                    if choices:
                        msg0 = choices[0]
                        message = getattr(msg0, "message", None)
                        content = getattr(message, "content", None) if message is not None else None
                        if content:
                            self._llm_last_error = ""
                            return str(content)
                except Exception as e:
                    logger.warning(f"LLM SDK 解析 completion 失败: {e}")
                    return ""
                last_err = "choices 为空或 content 为空"
                logger.warning(f"LLM SDK 返回空")
            except Exception as e:
                err_name = type(e).__name__
                detail = str(e)
                last_err = f"{err_name}: {detail}"
                safe_err = last_err if len(last_err) <= 220 else last_err[:220] + "..."
                logger.warning(f"LLM SDK {err_name}: {safe_err}（不重试，立即转requests）")
                self._llm_last_error = last_err
            logger.warning(f"LLM SDK 失败: {last_err or '未知'}（转 requests 兜底）")
            return ""
        except Exception as e:
            logger.warning(f"_try_llm_via_sdk 总异常（返回空）: {type(e).__name__}: {e}")
            return ""

    def _try_llm_via_requests(self, prompt: str) -> str:
        """requests 原生兜底（保留 Chrome 头、分离超时、代理自动降级，失败裸连）。
        外层异常墙：任何异常返回空字符串，不崩主线程"""
        try:
            base_url = str(getattr(settings, 'LLM_BASE_URL', '') or '').rstrip('/')
            api_key = str(getattr(settings, 'LLM_API_KEY', '') or '')
            model = str(getattr(settings, 'LLM_MODEL', '') or '')
            if not base_url or not api_key:
                logger.warning("MoviePilot未配置LLM，请在系统设置中配置 LLM_BASE_URL 和 LLM_API_KEY")
                return ""
            if "/v1" not in base_url:
                base_url = f"{base_url}/v1"
            url = f"{base_url}/chat/completions"
            payload = {
                "model": model or "gpt-4o-mini",
                "temperature": 0.0,
                "messages": [
                    {"role": "system", "content": "You are a Japanese name translator. Output JSON only."},
                    {"role": "user", "content": prompt}
                ],
                "response_format": {"type": "json_object"},
            }
            # 模拟 Chrome 完整请求头（绕过 403 / 无响应 / timeout）
            chrome_headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,ja;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Origin": base_url.rsplit("/", 2)[0] if base_url.startswith("http") else "",
                "Referer": (base_url.rsplit("/", 2)[0] + "/") if base_url.startswith("http") else "",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "Connection": "keep-alive",
                "sec-ch-ua": '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-site",
            }
            chrome_headers = {k: v for k, v in chrome_headers.items() if v is not None and v != ""}

            proxies_setting = self._get_proxy_for_llm()
            timeout_tuple = (10, 60)  # 【优化】读超时60s，不回直接下一条；下次cron再试，绝不卡主线程
            max_attempts = 2  # 2次：先走代理（有则），再裸连（各60s）；最坏120s不成就放弃
            last_err = ""
            for attempt in range(max_attempts):
                # 第一次走代理（有配置），最后一次强制裸连
                use_proxies = proxies_setting if attempt == 0 else None
                try:
                    resp = _requests.post(
                        url=url,
                        json=payload,
                        headers=chrome_headers,
                        timeout=timeout_tuple,
                        proxies=use_proxies,
                        verify=False,
                        allow_redirects=True,
                        stream=False,
                    )
                    if resp.status_code == 200:
                        try:
                            data = resp.json()
                            choices = data.get("choices") or []
                            if choices:
                                msg = choices[0].get("message") or {}
                                return str(msg.get("content") or "")
                        except Exception as e:
                            logger.warning(f"解析LLM返回JSON失败: {e}")
                        return ""
                    status = resp.status_code
                    last_err = f"HTTP {status}"
                    body_preview = ""
                    try:
                        if resp.content:
                            body_preview = resp.text[:200]
                    except Exception:
                        pass
                    hint = f"，body: {body_preview}" if body_preview else ""
                    logger.warning(
                        f"LLM HTTP (第{attempt+1}次) {status}: {url[:90]}"
                        f"{' (via proxy)' if use_proxies else ''}{hint}"
                    )
                except _requests.exceptions.ProxyError as e:
                    last_err = f"ProxyError: {e}"
                    logger.warning(f"LLM HTTP (第{attempt+1}次) 代理错误: {last_err[:120]}")
                except _requests.exceptions.ConnectTimeout as e:
                    last_err = f"ConnectTimeout: {e}"
                    logger.warning(f"LLM HTTP (第{attempt+1}次) 连接超时: {last_err[:120]}{' (via proxy)' if use_proxies else ''}")
                except _requests.exceptions.ReadTimeout as e:
                    last_err = f"ReadTimeout: {e}"
                    logger.warning(f"LLM HTTP (第{attempt+1}次) 读超时: {last_err[:120]}{' (via proxy)' if use_proxies else ''}")
                except _requests.exceptions.ConnectionError as e:
                    last_err = f"ConnectionError: {e}"
                    logger.warning(f"LLM HTTP (第{attempt+1}次) 连接失败: {last_err[:140]}{' (via proxy)' if use_proxies else ''}")
                except Exception as e:
                    last_err = f"{type(e).__name__}: {e}"
                    logger.warning(f"LLM HTTP (第{attempt+1}次) 异常: {last_err[:140]}{' (via proxy)' if use_proxies else ''}")
                if attempt < max_attempts - 1:
                    # 指数退避（对齐 autosubv3）
                    try:
                        sleep_time = (2 ** attempt) + random.uniform(0.1, 0.9)
                        time.sleep(sleep_time)
                    except Exception:
                        break
            logger.warning(f"LLM HTTP 最终失败: {last_err or '未知'}")
            return ""
        except Exception as e:
            logger.warning(f"_try_llm_via_requests 总异常（返回空）: {type(e).__name__}: {e}")
            return ""

    def _parse_llm_json(self, raw: Any, names: List[str]) -> Dict[str, str]:
        """外层异常墙：任何异常返回空字典，不崩主线程"""
        result: Dict[str, str] = {}
        text = ""
        try:
            if raw is None:
                return {}
            text = raw if isinstance(raw, str) else (
                raw.get("content") if isinstance(raw, dict) else json.dumps(raw, ensure_ascii=False)
            )
            text = str(text or "").strip()
            if not text:
                return {}
            m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.I)
            if m:
                text = m.group(1).strip()
            try:
                data = json.loads(text)
                translations = None
                if isinstance(data, list):
                    translations = data
                elif isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, list):
                            translations = v
                            break
                    if translations is None and "translations" not in data:
                        return {k: str(v) for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}
                if isinstance(translations, list):
                    for t in translations:
                        if isinstance(t, dict):
                            orig = str(t.get("original") or t.get("name") or t.get("jp") or t.get("en") or "").strip()
                            cn = str(t.get("chinese") or t.get("cn") or t.get("zh") or t.get("name_cn") or t.get("translated") or "").strip()
                            if orig and cn:
                                result[orig] = cn
            except Exception as e:
                logger.warning(f"解析翻译结果 JSON 失败: {e}, 原文前200字: {text[:200]}")
            if not result:
                for m in re.finditer(r"""(?P<q>["'])(?P<orig>[^"']{1,40})(?P=q)\s*:\s*(?P<q2>["'])(?P<cn>[^"']{1,20})(?P=q2)""", text):
                    orig = m.group("orig").strip()
                    cn = m.group("cn").strip()
                    if orig and cn and self._norm_name_key(orig) in {self._norm_name_key(n) for n in names}:
                        result[orig] = cn
            return result
        except Exception as e:
            logger.warning(f"_parse_llm_json 总异常（返回空）: {type(e).__name__}: {e}")
            return {}

    # ==================== 过滤/匹配/翻译应用 ====================
    def _should_translate_type(self, person: dict) -> bool:
        if self._translate_all:
            return True
        ptype = str(person.get("Type") or "").strip()
        role = str(person.get("Role") or "").strip()
        ptype_l = ptype.lower()
        role_l = role.lower()
        if self._translate_voice_actor:
            if "voice" in ptype_l or "配音" in role or "声" in role or "cv" in role_l or "(voice)" in role_l:
                return True
        if self._translate_actor and ("actor" in ptype_l or ptype_l == "" or "演" in ptype_l):
            return True
        if self._translate_director and "director" in ptype_l:
            return True
        if self._translate_writer and "writer" in ptype_l:
            return True
        if self._translate_producer and "producer" in ptype_l:
            return True
        return False

    _HIRAGANA_RE = re.compile(r"[\u3040-\u309F]")
    _KATAKANA_RE = re.compile(r"[\u30A0-\u30FF\u31F0-\u31FF]")
    _JAPANESE_SYMBOL_RE = re.compile(r"[\u30FB\u30FC]")

    @classmethod
    def _contains_japanese(cls, s: str) -> bool:
        if not s:
            return False
        return bool(cls._HIRAGANA_RE.search(s) or cls._KATAKANA_RE.search(s) or cls._JAPANESE_SYMBOL_RE.search(s))

    def _is_pure_chinese(self, s: str) -> bool:
        if not s:
            return False
        cleaned = re.sub(r"[\s　\.．\-－_,，、。()（）\[\]【】\[\]【】\#'\"`~]", "", s)
        if not cleaned:
            return False
        if re.fullmatch(r"[\u4e00-\u9fff]+", cleaned):
            return True
        return False

    def _name_needs_translate(self, name: str) -> bool:
        if not name:
            return False
        s = str(name).strip()
        if re.fullmatch(r"[\W\d_]+", s):
            return False
        # 纯中文处理：简体跳过，繁体转简体（如果安装了zhconv）
        if self._is_pure_chinese(s):
            if HAS_ZHCONV:
                simplified = zhconv.convert(s, 'zh-hans')
                if simplified != s:
                    return True  # 繁体需要翻译
                else:
                    return False  # 简体不翻译
            else:
                return False  # 未安装zhconv，跳过所有纯中文
        # 含英文或假名 -> 翻译
        if re.search(r"[A-Za-z]", s) or self._contains_japanese(s):
            return True
        return False

    def _role_needs_translate(self, role: str) -> bool:
        return self._name_needs_translate(role)

    def _apply_translation_to_people(self, title: str, people: List[dict], year: Optional[str] = None) -> Tuple[List[dict], int]:
        """外层异常墙：任何异常返回(people,0)原样返回，绝对不崩主线程"""
        try:
            return self._apply_translation_to_people_inner(title, people, year=year)
        except Exception as e:
            logger.warning(f"【{title}】_apply_translation_to_people 总异常（原样返回）: {type(e).__name__}: {e}", exc_info=True)
            return list(people or []), 0

    def _apply_translation_to_people_inner(self, title: str, people: List[dict], year: Optional[str] = None) -> Tuple[List[dict], int]:
        _start_ts = time.time()
        _MAX_WALL_SEC = 200  # 【关键】单条目翻译最坏200s就停，绝不卡整条扫描线
        name_candidates: List[Tuple[int, str]] = []
        role_candidates: List[Tuple[int, str]] = []
        for idx, p in enumerate(people or []):
            if not self._should_translate_type(p):
                continue
            if (len(name_candidates) + len(role_candidates)) >= (self._max_people_per_title * 2):
                break
            name = str(p.get("Name") or "").strip()
            role = str(p.get("Role") or "").strip()
            if self._name_needs_translate(name):
                name_candidates.append((idx, name))
            if self._role_needs_translate(role):
                role_candidates.append((idx, role))

        terms_to_translate = []
        for _, nm in name_candidates:
            terms_to_translate.append(nm)
        for _, rl in role_candidates:
            terms_to_translate.append(rl)

        if not terms_to_translate:
            return people, 0

        logger.debug(f"【{title}】准备翻译 {len(terms_to_translate)} 条")

        mapping: Dict[str, str] = {}
        remaining: List[str] = []
        for t in terms_to_translate:
            key = self._norm_name_key(t)
            # zhconv 快速繁简映射（省LLM token）：纯中文走这里直接搞定
            if HAS_ZHCONV and self._is_pure_chinese(t):
                simplified = zhconv.convert(t, 'zh-hans')
                if simplified and simplified != t:
                    mapping[t] = simplified
                    if key:
                        self._name_cache[key] = {
                            "chinese": simplified,
                            "source": "zhconv",
                            "time": datetime.now().isoformat(timespec='seconds'),
                        }
                    continue
            cached = self._name_cache.get(key, {}).get("chinese") if key else None
            if cached and str(cached).strip() and (not self._overwrite_chinese or str(cached) != t):
                mapping[t] = str(cached)
            else:
                remaining.append(t)

        if remaining:
            uniq = list(dict.fromkeys(remaining))
            logger.debug(f"【{title}】实际送LLM: {len(uniq)} 条(缓存命中 {len(mapping)})")
            translated_from_llm: Dict[str, str] = {}
            BATCH = max(1, self._max_people_per_batch)
            for i in range(0, len(uniq), BATCH):
                # 【关键】wall-clock 超时：单条已处理超过 _MAX_WALL_SEC 秒直接跳出
                _elapsed = time.time() - _start_ts
                if _elapsed > _MAX_WALL_SEC:
                    logger.warning(
                        f"【{title}】单条已用时 {int(_elapsed)}s 超过上限 {_MAX_WALL_SEC}s，"
                        f"剩余{len(uniq) - i}条不再送LLM，等下次cron再补。"
                    )
                    break
                batch = uniq[i:i + BATCH]
                try:
                    r = self._call_llm_translate(title, batch, year=year)
                    if r:
                        translated_from_llm.update(r)
                    else:
                        logger.warning(f"【{title}】第{i//BATCH+1}批LLM返回空")
                except Exception as e:
                    logger.warning(f"【{title}】第{i//BATCH+1}批失败: {e}")
                if self._delay > 0 and (i + BATCH) < len(uniq):
                    time.sleep(min(self._delay, 2))
            if translated_from_llm:
                logger.debug(f"【{title}】LLM结果: {dict(list(translated_from_llm.items())[:5])}")
            for orig, cn in translated_from_llm.items():
                if not cn or not str(cn).strip():
                    continue
                mapping[orig] = str(cn).strip()
                key = self._norm_name_key(orig)
                if key:
                    self._name_cache[key] = {
                        "chinese": str(cn).strip(),
                        "source": "llm",
                        "time": datetime.now().isoformat(timespec='seconds'),
                    }
        else:
            logger.debug(f"【{title}】全部命中缓存(含zhconv)")

        update_count = 0
        for pi, orig_name in name_candidates:
            cn = mapping.get(orig_name)
            if not cn or cn == orig_name:
                continue
            p = dict(people[pi])
            p["Name"] = cn
            people[pi] = p
            update_count += 1
        for pi, orig_role in role_candidates:
            cn = mapping.get(orig_role)
            if not cn or cn == orig_role:
                continue
            p = dict(people[pi])
            p["Role"] = cn
            people[pi] = p
            update_count += 1

        logger.debug(f"【{title}】实际更新 {update_count} 个字段")
        return people, update_count

    # ==================== 主流程 ====================
    def _parse_selected_libraries(self) -> Dict[str, Dict[str, str]]:
        result: Dict[str, Dict[str, str]] = {}
        for sel in (self._libraries or []):
            s = str(sel or "").strip()
            if not s or ":" not in s:
                continue
            sname, _, lid = s.partition(":")
            sname = sname.strip()
            lid = lid.strip()
            if not sname or not lid:
                continue
            result.setdefault(sname, {})[lid] = lid
        return result

    def _emby_libraries_via_chain(self, service: ServiceInfo, server_name: str,
                                  msc: Optional[MediaServerChain] = None) -> List[dict]:
        result: List[dict] = []
        if msc is None:
            try:
                msc = MediaServerChain()
            except Exception:
                msc = None
        if msc:
            try:
                for lib in (msc.librarys(server_name) or []):
                    lid = str(getattr(lib, "id", "") or "")
                    lname = str(getattr(lib, "name", "") or "")
                    if lid:
                        result.append({"id": lid, "name": lname})
            except Exception as e:
                logger.debug(f"MediaServerChain.librarys({server_name}) 失败: {e}")
        if not result:
            try:
                result = list(self._get_emby_libraries(service) or [])
            except Exception as e:
                logger.warning(f"Emby API 兜底拉库失败: {e}")
        return result

    def _update_people_with_fallback(self, service: ServiceInfo, item_id: str, new_people: List[dict],
                                      item_data: Optional[dict] = None) -> bool:
        """外层异常墙：任何异常返回False，不崩主线程。
        对齐 EmbyBangumi声优本地化：优先使用扫描时已拿到的完整item_data，**绝不二次查Emby**（查/Items/{id}带错UserId直接404）
        只有传入的item_data为空/无People时，才用兜底路径 /Users/{UserId}/Items/{id} 查询（对UserId更友好）"""
        try:
            return self._update_people_with_fallback_inner(service, item_id, new_people, item_data=item_data)
        except Exception as e:
            logger.error(f"_update_people_with_fallback 总异常（返回False，不挂线程）: {type(e).__name__}: {e}", exc_info=True)
            return False

    def _update_people_with_fallback_inner(self, service: ServiceInfo, item_id: str, new_people: List[dict],
                                            item_data: Optional[dict] = None) -> bool:
        # 优先用扫描时传入的完整item_data（扫库URL /Items?ParentId=xxx 已经带 Fields=People,Genres,...，拿到的绝对不会404）
        data = item_data
        if not data or not isinstance(data, dict) or "People" not in data:
            logger.debug(f"_update_people_with_fallback: 传入item_data无People，用兜底Users路径查{item_id}")
            user_id = getattr(service.instance, 'user', None) if getattr(service, 'instance', None) else None
            fallback_path = f"/Users/{user_id}/Items/{item_id}?Fields=People,Genres,Tags,ProviderIds,OriginalTitle,PremiereDate,ProductionYear" if user_id \
                else f"/Items/{item_id}?Fields=People,Genres,Tags,ProviderIds,OriginalTitle,PremiereDate,ProductionYear"
            data = self._emby_get(service, fallback_path)
            if not data:
                # 最后兜底：不加UserId，直接查/Items/{id}（API key权限足够时能过）
                logger.debug(f"兜底Users路径仍失败，尝试无UserId纯/Items查{item_id}")
                host, api_key = self._get_emby_info(service)
                if host and api_key:
                    try:
                        raw_resp = _requests.get(
                            f"{host}/Items/{item_id}?api_key={api_key}&Fields=People,Genres,Tags,ProviderIds,OriginalTitle,PremiereDate,ProductionYear",
                            timeout=30, verify=False
                        )
                        if raw_resp.status_code == 200:
                            data = raw_resp.json()
                    except Exception as e:
                        logger.debug(f"纯Items无UserId查也失败: {e}")
            if not data:
                logger.error(f"获取Item {item_id} 完整数据失败（3种路径均失败），无法更新演职人员")
                return False
        data["People"] = new_people or []
        # 移除只读/容易冲突字段（Emby校验严格，整条更新时必须剔除）
        for fld in ("ImageTags", "BackdropImageTags", "ParentLogoItemId",
                    "ParentBackdropItemId", "ParentThumbItemId",
                    "DateCreated", "DateModified", "DateLastRefreshed",
                    "DateLastSaved", "RunTimeTicks", "Size", "ChannelId",
                    "ForcedSortName", "SortName"):
            data.pop(fld, None)
        ok = self._emby_post(service, f"/Items/{item_id}", json=data)
        if not ok:
            # 再兜底：在现有data里多移除一些字段（不同Emby版本对字段容忍度不一致）
            for extra in ("MediaType", "MediaTypeExtra", "Container", "Path", "PlaylistItemId",
                          "PremiereDate", "ExternalUrls", "MediaSources", "MediaStreams",
                          "SeriesId", "SeasonId", "ParentId", "AlbumId", "Album",
                          "PreferredMetadataLanguage", "PreferredMetadataCountryCode",
                          "LockData", "LockedFields", "ProviderIds", "Overview",
                          "CommunityRating", "CriticRating", "OfficialRating",
                          "ProductionLocations", "Taglines", "Studios",
                          "LocalTrailerCount", "SpecialFeatureCount"):
                data.pop(extra, None)
            ok = self._emby_post(service, f"/Items/{item_id}", json=data)
        return ok

    # ==================== 事件监听（入库自动处理） ====================
    @eventmanager.register(EventType.TransferComplete)
    @eventmanager.register(EventType.MetadataScrape)
    def _on_media_event(self, event: Event):
        """入库/刮削完成：从_processed中移除对应条目，下一次cron/立即运行时会重新处理（自动触发翻译）"""
        if not self._enabled:
            return
        try:
            data = event.event_data or {}
            # 兼容不同MP版本的字段命名
            meta = (data.get("meta") if isinstance(data, dict) else None) or {}
            if not isinstance(meta, dict):
                meta = {}
            # 拿媒体服务器 + item_id
            server = (meta.get("mediaserver")
                      or meta.get("media_server")
                      or meta.get("server_name")
                      or getattr(data, "mediaserver", None)
                      or getattr(data, "server_name", None))
            item_id = (meta.get("mediaitem_id")
                       or meta.get("item_id")
                       or meta.get("id")
                       or getattr(meta, "id", None))
            if not server or not item_id:
                return
            key = f"{str(server)}:{str(item_id)}"
            if self._processed and key in self._processed:
                self._processed.pop(key, None)
                logger.info(f"入库事件{event.event_type or ''}触发：已清缓存 {key}，下次扫描会自动翻译")
        except Exception as e:
            logger.debug(f"事件处理失败: {e}")

    def sync_library(self):
        if not self._enabled:
            return
        self._event.clear()
        total = processed_count = skipped = failed = translated_total = 0
        selected_libs = self._parse_selected_libraries()
        target_servers = list(selected_libs.keys()) or None  # None 表示所有服务器

        msc: Optional[MediaServerChain] = None
        try:
            msc = MediaServerChain()
        except Exception:
            msc = None
        # ========== 最外层异常墙：无论什么崩，最后一定save_cache ==========
        try:
            try:
                services: Dict[str, ServiceInfo] = MediaServerHelper().get_services(
                    type_filter="emby", name_filters=target_servers,
                ) or {}
                services = {k: v for k, v in services.items()
                            if not getattr(getattr(v, "instance", None), "is_inactive", lambda: True)()}
                if not services:
                    logger.warning("未找到可用的 Emby 服务")
                    return

                for sname, service in services.items():
                    if self._event.is_set() or not self._enabled:
                        break
                    # ========== 每个服务器一层异常墙 ==========
                    try:
                        logger.info(f"开始扫描服务器 {sname}...")
                        # 获取该服务器下用户选中的库ID集合（如果用户没选任何库，则 target_lib_ids 为空集合）
                        target_lib_ids = set(selected_libs.get(sname, {}).keys()) if selected_libs else set()

                        # 获取所有媒体库
                        libraries = self._emby_libraries_via_chain(service, sname, msc=msc)
                        logger.info(f"服务器 {sname} 共有 {len(libraries)} 个媒体库")

                        for library in libraries:
                            if self._event.is_set() or not self._enabled:
                                break
                            # ========== 每个媒体库一层异常墙 ==========
                            try:
                                lid = str(library.get("id") or "")
                                lname = str(library.get("name") or "")
                                if not lid:
                                    continue

                                # 如果用户选择了库（selected_libs不为空）且当前库不在选中列表中，则跳过
                                if selected_libs and lid not in target_lib_ids:
                                    logger.info(f"跳过媒体库: {lname}（未选择）")
                                    continue

                                logger.info(f"扫描媒体库: {lname} (id={lid})")
                                fields = "Genres,Tags,ProviderIds,OriginalTitle,PremiereDate,ProductionYear,People,Path"

                                offset = 0
                                limit = 200
                                total_count = None
                                lib_processed = 0
                                while total_count is None or offset < total_count:
                                    if self._event.is_set() or not self._enabled:
                                        break
                                    # ========== 分页拉取一层异常墙 ==========
                                    try:
                                        items_url = (f"/Items?ParentId={lid}&Recursive=true&Fields={fields}"
                                                     f"&IncludeItemTypes=Movie,Series,Season,Episode"
                                                     f"&Limit={limit}&StartIndex={offset}")
                                        items_data = self._emby_get(service, items_url)
                                        if not items_data or "Items" not in items_data:
                                            logger.error(f"获取媒体库 {lname} 条目失败，跳过该页")
                                            break
                                        items = items_data.get("Items", []) or []
                                        total_count = items_data.get("TotalRecordCount", len(items))
                                        logger.debug(f"获取到 {len(items)} 条，总 {total_count} 条")
                                        total += len(items)

                                        for it in items:
                                            if self._event.is_set() or not self._enabled:
                                                break
                                            # ========== 单条条目最内层异常墙：绝对不能崩整个线程 ==========
                                            try:
                                                item_id = str(it.get("Id") or "")
                                                title = it.get("Name") or it.get("OriginalTitle") or "未知标题"
                                                label = f"{title} ({lname})"
                                                if not item_id:
                                                    continue
                                                item_key = f"{sname}:{item_id}"
                                                if item_key in self._processed:
                                                    skipped += 1
                                                    continue
                                                logger.info(f"处理: {label}")
                                                people = it.get("People") or [] or []
                                                if people:
                                                    logger.debug(f"{label}: People数量 {len(people)}")
                                                year = it.get("ProductionYear") or it.get("Year") or None
                                                if year:
                                                    try:
                                                        year = str(int(year))
                                                    except Exception:
                                                        year = str(year)[:4] if len(str(year)) >= 4 else None
                                                new_people, n_translated = self._apply_translation_to_people(
                                                    str(title), [dict(p) for p in people], year=year,
                                                )
                                                if n_translated > 0:
                                                    # 【关键】直接把扫描时拿到的完整 it（含People等字段）传进去，
                                                    # 对齐Bangumi声优插件，**绝不二次查 /Items/{id}（带错UserId直接404）**
                                                    if self._update_people_with_fallback(service, item_id, new_people, item_data=it):
                                                        translated_total += n_translated
                                                        processed_count += 1
                                                        lib_processed += 1
                                                        self._add_history(key=item_key, title=str(title), server=str(sname),
                                                                          lib=str(lname), n_trans=n_translated, item_id=item_id)
                                                        logger.info(f"{label}: Emby 更新成功，翻译 {n_translated} 个字段")
                                                    else:
                                                        failed += 1
                                                        logger.error(f"{label}: Emby 更新失败")
                                                        # 失败也算已处理，避免下次重复卡在这里
                                                        self._processed[item_key] = datetime.now().isoformat(timespec='seconds')
                                                        continue
                                                else:
                                                    processed_count += 1
                                                    lib_processed += 1
                                                    logger.debug(f"{label}: 无需翻译")
                                                self._processed[item_key] = datetime.now().isoformat(timespec='seconds')
                                                if lib_processed % self._SAVE_INTERVAL == 0:
                                                    self._save_cache()
                                            except Exception as e:
                                                failed += 1
                                                logger.error(f"单条目处理失败（已隔离，继续下一条）: {type(e).__name__}: {e}", exc_info=True)
                                                # 标记已处理，避免下次卡住
                                                try:
                                                    if it is not None:
                                                        item_id2 = str(it.get("Id") or "")
                                                        if item_id2:
                                                            k2 = f"{sname}:{item_id2}"
                                                            self._processed[k2] = datetime.now().isoformat(timespec='seconds')
                                                except Exception:
                                                    pass
                                            if self._delay > 0:
                                                try:
                                                    time.sleep(min(self._delay, 2))
                                                except Exception:
                                                    pass
                                        offset += limit
                                    except Exception as e:
                                        logger.error(f"分页 {lid}@{offset} 处理异常（已隔离，跳该页）: {type(e).__name__}: {e}", exc_info=True)
                                        try:
                                            offset += limit
                                        except Exception:
                                            break
                                self._save_cache()
                            except Exception as e:
                                logger.error(f"媒体库 {library} 处理异常（已隔离，继续下一个库）: {type(e).__name__}: {e}", exc_info=True)
                                self._save_cache()
                    except Exception as e:
                        logger.error(f"服务器 {sname} 处理异常（已隔离，继续下一个服务器）: {type(e).__name__}: {e}", exc_info=True)
                        self._save_cache()
                self._save_cache()
                logger.info(f"扫描完成 - 总计: {total}, 成功: {processed_count}, 翻译字段数: {translated_total}, 跳过: {skipped}, 失败: {failed}")
            except Exception as e:
                logger.error(f"扫描过程总异常: {type(e).__name__}: {e}", exc_info=True)
        finally:
            # ========== 终极保障：不管怎么崩，最后一定save_cache并清理event ==========
            try:
                self._save_cache()
            except Exception as e:
                logger.warning(f"finally save_cache 再失败: {e}")
            try:
                self._event.set()
            except Exception:
                pass


# 兼容
PluginClass = EmbyPeopleLocalize
__all__ = ["EmbyPeopleLocalize", "PluginClass", "DEFAULT_PROMPT"]
