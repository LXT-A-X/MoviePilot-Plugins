"""
EmbyPeopleLocalize - Emby 演职人员中文化
利用大模型（HTTP直连）把 Emby 中英文/罗马音/日文人名翻译为正式中文名并写回。
用户选择媒体库则只扫描选中的，未选择则扫描全部（所有服务器所有库）。
支持扫描电影、剧集，自带人名缓存和条目级缓存。
三阶段按库处理架构：收集 → 翻译 → 写入。
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

try:
    import openai as _openai_mod  # noqa: F401
    import httpx as _httpx_mod  # noqa: F401
    _HAS_OPENAI_SDK = True
except Exception:
    _HAS_OPENAI_SDK = False
    _openai_mod = None
    _httpx_mod = None

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
from app.schemas.types import EventType, NotificationType
from app.utils.http import RequestUtils
from app.utils.string import StringUtils

try:
    import zhconv
    HAS_ZHCONV = True
except ImportError:
    HAS_ZHCONV = False

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

_EMBY_STRIP_FIELDS = frozenset([
    "Id", "Key", "Guid", "ExternalUrls", "MediaStreams", "MediaSources",
    "PlaylistItemId", "PlaylistIndex", "PlaylistLength", "LockedFields",
    "ImageTags", "BackdropImageTags", "ScreenshotImageTags", "ParentId",
    "Type", "MediaType", "People",
    "Path", "OriginalTitle", "PremiereDate", "CriticRating",
    "CommunityRating", "RunTimeTicks", "PlayAccess", "ProductionYear",
])


class EmbyPeopleLocalize(_PluginBase):
    plugin_name = "Emby 演职人员中文化"
    plugin_desc = "利用大模型把Emby里英文/罗马音/日文人名翻译为正式中文名并写回（可选库/全库）"
    plugin_icon = "embypeoplelocalize_icon.jpg"
    plugin_version = "0.3.1"
    plugin_author = "LXT-A-X"
    plugin_config_prefix = "embypeoplelocalize_"
    plugin_order = 27
    auth_level = 1

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

    _scheduler = None
    _ms_helper: Optional[MediaServerHelper] = None
    _event = threading.Event()
    _rt_lock = threading.Lock()
    _rt_recent_keys: Dict[str, float] = {}
    _name_cache: Dict[str, Dict[str, str]] = {}
    _processed: Dict[str, str] = {}
    _history: List[Dict[str, Any]] = []
    _MAX_HISTORY = 200
    _SAVE_INTERVAL = 50
    _RT_WINDOW = 300

    _llm_client = None
    _llm_model: str = ""
    _llm_last_error: str = ""

    _LLM_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Origin": "https://api.siliconflow.cn",
        "Referer": "https://api.siliconflow.cn/",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "sec-ch-ua": '"Chromium";v="127", "Not)A;Brand";v="99", "Google Chrome";v="127"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }

    @property
    def private_attrs(self) -> List[str]:
        return []

    def _get_proxy_for_llm(self) -> Optional[Dict[str, str]]:
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
        base_url = str(getattr(settings, 'LLM_BASE_URL', '') or '').rstrip('/')
        api_key = str(getattr(settings, 'LLM_API_KEY', '') or '')
        model = str(getattr(settings, 'LLM_MODEL', '') or '')
        if not base_url or not api_key:
            self._llm_client = None
            self._llm_model = model
            return
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

    @eventmanager.register(EventType.TransferComplete)
    @eventmanager.register(EventType.MetadataScrape)
    def _on_event(self, event: Event):
        try:
            if not self._enabled:
                return
            event_data = event.event_data or {}
            item_info = (
                event_data.get("iteminfo")
                or event_data.get("meta_info")
                or event_data.get("media_info")
                or event_data.get("item_info")
                or {}
            )
            if not isinstance(item_info, dict):
                return
            item_id = str(
                item_info.get("item_id")
                or item_info.get("id")
                or item_info.get("Id")
                or ""
            )
            if not item_id:
                return
            title = str(
                item_info.get("title")
                or item_info.get("name")
                or item_info.get("Name")
                or "未知作品"
            )
            server_name = str(
                item_info.get("server_name")
                or item_info.get("server")
                or item_info.get("mediaserver")
                or getattr(item_info.get("mediaserver") or "", "name", "")
                or ""
            )
            library = str(
                item_info.get("library")
                or item_info.get("library_name")
                or item_info.get("Library")
                or ""
            )
            media_type = str(item_info.get("type") or item_info.get("mtype") or item_info.get("Type") or "")
            if media_type and media_type.lower() not in ("movie", "series", "tv", "动漫电影", "番剧", ""):
                return
            key = f"{server_name}:{item_id}:rt"
            if not self.__try_lock_rt_item(key, title):
                return
            threading.Thread(
                target=self.__rt_worker,
                args=(key, server_name, item_id, title, library),
                daemon=True,
            ).start()
        except Exception as e:
            logger.debug(f"事件响应失败（不影响主流程）: {e}")

    def __try_lock_rt_item(self, key: str, title: str = "") -> bool:
        now = time.time()
        with self._rt_lock:
            for k, ts in list(self._rt_recent_keys.items()):
                if now - ts > self._RT_WINDOW:
                    self._rt_recent_keys.pop(k, None)
            if key in self._rt_recent_keys:
                return False
            self._rt_recent_keys[key] = now
            return True

    def __unlock_rt_item(self, key: str, completed: bool):
        try:
            with self._rt_lock:
                if not completed:
                    self._rt_recent_keys.pop(key, None)
        except Exception:
            pass

    def __rt_worker(self, key: str, server_name: str, item_id: str, title: str, library_name: str):
        completed = False
        try:
            time.sleep(min(int(self._delay or 2), 30))
            if not self._enabled:
                return
            selected_libs = self._parse_selected_libraries()
            if selected_libs:
                hit = False
                for srv, ids in selected_libs.items():
                    if srv == server_name:
                        if library_name or ids:
                            hit = True
                            break
                if not hit and library_name:
                    try:
                        _srv, _lib_opts = self._get_server_lib_options()
                        for lo in _lib_opts:
                            v = str(lo.get("value") or "")
                            t = str(lo.get("title") or "")
                            for srv, ids in selected_libs.items():
                                for lid in ids:
                                    if v == f"{srv}:{lid}" and library_name in t:
                                        hit = True
                                        break
                            if hit:
                                break
                    except Exception:
                        pass
                if not hit:
                    logger.debug(f"实时跳过 {title}：库 '{library_name}' 未在选择列表中")
                    return
            services = self.service_infos()
            service = None
            if server_name and server_name in services:
                service = services[server_name]
            elif len(services) == 1:
                service = next(iter(services.values()))
            if not service:
                logger.warning(f"实时处理 {title}: 找不到匹配的 Emby 服务器")
                return
            user_id = getattr(service.instance, 'user', None)
            query_path = f"/Items/{item_id}?Fields=People,Genres,Tags,ProviderIds,OriginalTitle,PremiereDate,ProductionYear"
            if user_id:
                it = self._emby_get(service, f"/Users/{user_id}{query_path}")
                if not it:
                    it = self._emby_get(service, query_path)
            else:
                it = self._emby_get(service, query_path)
            if not it or not isinstance(it, dict):
                logger.warning(f"实时处理 {title}: 拿不到完整 item_data")
                return
            mtype_str = (it.get("Type") or "").lower()
            media_type = "TV" if "series" in mtype_str or mtype_str == "tv" else "MOVIE"
            n_trans = self._apply_translation_to_people_inner(
                server_name, service, item_id, title,
                str(it.get("OriginalTitle") or title),
                str(it.get("ProductionYear") or (it.get("PremiereDate") or "")[:4]),
                media_type, item_data=it,
            )
            if n_trans > 0:
                self._add_history(f"{server_name}:{item_id}", title, server_name, library_name or "实时入库", n_trans, item_id)
                self._save_cache()
            completed = True
        except Exception as e:
            logger.error(f"实时处理 {title} 失败: {e}", exc_info=True)
        finally:
            self.__unlock_rt_item(key, completed)

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
            self._build_llm_client()
            logger.info(
                f"{self.plugin_name}: LLM 模式={'openai SDK' if self._llm_client else 'requests 兜底'}"
                + (f"，model={self._llm_model}" if self._llm_model else "")
            )
            data = self.get_data("cache") or {}
            if self._force_refresh:
                logger.info(f"{self.plugin_name}: 强制刷新，清空所有缓存")
                self._name_cache = {}
                self._processed = {}
            else:
                self._name_cache = data.get("name_cache", {}) or {}
                self._processed = data.get("processed", {}) or {}
            self._history = list(data.get("history", []) or [])[:self._MAX_HISTORY]
            logger.info(
                f"{self.plugin_name} v{self.plugin_version} 初始化成功 "
                f"(缓存 {len(self._name_cache)} 条, 历史 {len(self._history)} 条)"
            )
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
                    run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                )
                self._scheduler.start()
            logger.info(f"{self.plugin_name}：立即运行一次")

    def stop_service(self):
        try:
            self._event.set()
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown(wait=False)
                self._scheduler = None
        except Exception as e:
            logger.debug(f"停止服务时出错: {e}")

    def _save_cache(self):
        try:
            self.save_data("cache", {
                "name_cache": dict(self._name_cache or {}),
                "processed": dict(self._processed or {}),
                "history": list(self._history or [])[:self._MAX_HISTORY],
            })
        except Exception as e:
            logger.warning(f"保存缓存失败（不影响继续运行）: {type(e).__name__}: {e}")

    def _add_history(self, key: str, title: str, server: str, lib: str, n_trans: int, item_id: str = ""):
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

    @staticmethod
    def get_render_mode() -> Tuple[str, str]:
        """默认 VPage 模式"""
        return "page", ""

    def get_sidebar_nav(self) -> List[Dict[str, Any]]:
        return []

    def get_page(self) -> List[dict]:
        try:
            history = list(self._history or [])
        except Exception:
            history = []
        cache_count = len(self._name_cache or {})
        history_count = len(history)
        processed_count = len(self._processed or {})
        total_fields = sum(int(h.get("n_trans") or 0) for h in history)

        stat_cards = {
            "component": "VRow",
            "props": {"dense": True, "class": "mb-4"},
            "content": [
                {"component": "VCol", "props": {"cols": "6", "sm": "3"}, "content": [
                    {"component": "VCard", "props": {"color": "primary", "variant": "tonal", "flat": True}, "content": [
                        {"component": "VCardText", "props": {"class": "text-center py-2"}, "content": [
                            {"component": "div", "props": {"class": "text-headline font-bold text-primary"}, "content": [history_count]},
                            {"component": "div", "props": {"class": "text-caption text-medium-emphasis mt-1"}, "content": ["处理作品"]},
                        ]}
                    ]}
                ]},
                {"component": "VCol", "props": {"cols": "6", "sm": "3"}, "content": [
                    {"component": "VCard", "props": {"color": "success", "variant": "tonal", "flat": True}, "content": [
                        {"component": "VCardText", "props": {"class": "text-center py-2"}, "content": [
                            {"component": "div", "props": {"class": "text-headline font-bold text-success"}, "content": [total_fields]},
                            {"component": "div", "props": {"class": "text-caption text-medium-emphasis mt-1"}, "content": ["翻译字段"]},
                        ]}
                    ]}
                ]},
                {"component": "VCol", "props": {"cols": "6", "sm": "3"}, "content": [
                    {"component": "VCard", "props": {"color": "info", "variant": "tonal", "flat": True}, "content": [
                        {"component": "VCardText", "props": {"class": "text-center py-2"}, "content": [
                            {"component": "div", "props": {"class": "text-headline font-bold text-info"}, "content": [cache_count]},
                            {"component": "div", "props": {"class": "text-caption text-medium-emphasis mt-1"}, "content": ["人名缓存"]},
                        ]}
                    ]}
                ]},
                {"component": "VCol", "props": {"cols": "6", "sm": "3"}, "content": [
                    {"component": "VCard", "props": {"color": "warning", "variant": "tonal", "flat": True}, "content": [
                        {"component": "VCardText", "props": {"class": "text-center py-2"}, "content": [
                            {"component": "div", "props": {"class": "text-headline font-bold text-warning"}, "content": [processed_count]},
                            {"component": "div", "props": {"class": "text-caption text-medium-emphasis mt-1"}, "content": ["已处理条目"]},
                        ]}
                    ]}
                ]},
            ],
        }

        by_lib: Dict[str, List[Dict[str, Any]]] = {}
        for h in history:
            lib = str(h.get("lib") or "未知")
            by_lib.setdefault(lib, []).append(h)
        sorted_libs = sorted(by_lib.keys(), key=lambda k: -len(by_lib[k]))

        panels_children = []
        for lib in sorted_libs:
            items = by_lib[lib]
            summary = f"{lib}  共 {len(items)} 个作品"
            rows = []
            for it in items[:80]:
                title = str(it.get("title") or "")
                n_trans = int(it.get("n_trans") or 0)
                t = str(it.get("time") or "")[:19]
                rows.append({
                    "component": "VRow",
                    "props": {"dense": True, "class": "py-1 border-b border-opacity-25 border-outline-variant"},
                    "content": [
                        {"component": "VCol", "props": {"cols": "8"}, "content": [
                            {"component": "div", "props": {"class": "text-body-2 text-nowrap text-truncate"}, "content": [title]},
                        ]},
                        {"component": "VCol", "props": {"cols": "2"}, "content": [
                            {"component": "VChip",
                             "props": {"color": "success" if n_trans > 0 else "grey", "size": "x-small", "variant": "tonal"},
                             "content": [f"{n_trans}"]},
                        ]},
                        {"component": "VCol", "props": {"cols": "2"}, "content": [
                            {"component": "div", "props": {"class": "text-caption text-medium-emphasis text-right"}, "content": [t]},
                        ]},
                    ],
                })
            if len(items) > 80:
                rows.append({
                    "component": "div",
                    "props": {"class": "text-caption text-medium-emphasis text-center py-2"},
                    "content": [f"…仅显示最近 80 条，共 {len(items)} 条"],
                })
            panels_children.append({
                "component": "VExpansionPanel",
                "content": [
                    {"component": "VExpansionPanelTitle", "content": [summary]},
                    {"component": "VExpansionPanelText", "props": {"class": "px-0"}, "content": rows or [
                        {"component": "div", "props": {"class": "text-body-2 text-medium-emphasis text-center py-4"}, "content": ["暂无记录"]}
                    ]},
                ]
            })

        if not panels_children:
            panels_children = [{
                "component": "VCard",
                "props": {"variant": "tonal", "flat": True},
                "content": [{
                    "component": "VCardText",
                    "props": {"class": "text-center text-medium-emphasis py-8"},
                    "content": ["暂无翻译记录。启用插件后，选择媒体库并点击「立即运行一次」即可开始扫描。"],
                }]
            }]

        data_tab_items = [
            stat_cards,
            {
                "component": "VExpansionPanels",
                "props": {"variant": "accordion", "flat": True, "class": "mt-2"},
                "content": panels_children,
            },
        ]

        return [
            {
                "component": "VCard",
                "props": {"flat": True},
                "content": [
                    {
                        "component": "VTabs",
                        "props": {"color": "primary"},
                        "content": [
                            {"component": "VTab", "props": {"value": "data"}, "content": ["📊 数据面板"]},
                            {"component": "VTab", "props": {"value": "config"}, "content": ["⚙️ 插件设置"]},
                            {"component": "VWindow", "content": [
                                {"component": "VWindowItem", "props": {"value": "data"}, "content": [
                                    {"component": "VCardText", "content": data_tab_items},
                                ]},
                                {"component": "VWindowItem", "props": {"value": "config"}, "content": [
                                    {"component": "VCardText", "content": [
                                        {"component": "div", "props": {"class": "text-caption text-medium-emphasis mb-4"},
                                         "content": ["修改配置后点击底部「保存」生效。需要立即扫描时，勾选「立即运行一次」再保存。"]},
                                    ]},
                                ]},
                            ]},
                        ],
                    },
                ],
            },
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        if self._enabled and self._cron:
            return [{
                "id": "EmbyPeopleLocalize",
                "name": f"{self.plugin_name} 定时扫描",
                "trigger": CronTrigger.from_crontab(self._cron, timezone=settings.TZ),
                "func": self.sync_library,
                "kwargs": {},
            }]
        return []

    def _get_server_lib_options(self) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        library_options: List[Dict[str, Any]] = []
        services: Dict[str, Any] = {}
        try:
            helper = MediaServerHelper()
            msc = MediaServerChain()
            all_services = helper.get_services(type_filter="emby") or {}
            services = {k: v for k, v in all_services.items() if not getattr(v.instance, "is_inactive", lambda: False)()}
            for server_name in services.keys():
                try:
                    for lib in msc.librarys(server_name):
                        lib_value = f"{server_name}:{lib.id}"
                        lib_title = f"{server_name} - {lib.name}"
                        library_options.append({"title": lib_title, "value": lib_value})
                except Exception as e:
                    logger.warning(f"获取服务器 {server_name} 媒体库失败: {e}")
        except Exception as e:
            logger.warning(f"获取媒体库列表失败: {e}")
        return services, library_options

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        _servers, lib_opts = self._get_server_lib_options()
        return [
            {
                "component": "VForm",
                "content": [
                    {"component": "VRow", "content": [
                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                            {"component": "VSwitch", "props": {"prop": "enabled", "model": "enabled", "label": "启用插件"}}
                        ]},
                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                            {"component": "VSwitch", "props": {"prop": "onlyonce", "model": "onlyonce", "label": "立即运行一次"}}
                        ]},
                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                            {"component": "VSwitch", "props": {"prop": "force_refresh", "model": "force_refresh", "label": "强制刷新（清空缓存）"}}
                        ]},
                    ]},
                    {"component": "VRow", "content": [
                        {"component": "VCol", "props": {"cols": 12, "md": 6}, "content": [
                            {"component": "VTextField", "props": {"prop": "cron", "model": "cron", "label": "定时扫描 cron 表达式", "placeholder": "0 4 * * *"}}
                        ]},
                        {"component": "VCol", "props": {"cols": 12, "md": 6}, "content": [
                            {"component": "VTextField", "props": {"prop": "delay", "model": "delay", "label": "批间/入库延迟（秒）", "type": "number"}}
                        ]},
                    ]},
                    {"component": "VRow", "content": [
                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                            {"component": "VTextField", "props": {"prop": "max_people_per_title", "model": "max_people_per_title", "label": "单作品最多处理前N人", "type": "number"}}
                        ]},
                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                            {"component": "VTextField", "props": {"prop": "max_people_per_batch", "model": "max_people_per_batch", "label": "单次 LLM 批大小", "type": "number", "hint": "数越小LLM响应越快"}}
                        ]},
                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                            {"component": "VSwitch", "props": {"prop": "overwrite_chinese", "model": "overwrite_chinese", "label": "覆盖已有的中文名"}}
                        ]},
                    ]},
                    {"component": "VRow", "content": [
                        {"component": "VCol", "props": {"cols": 12}, "content": [
                            {"component": "VSelect", "props": {"prop": "libraries", "model": "libraries", "multiple": True, "chips": True, "clearable": True, "label": "选择媒体库（多选，留空=全服务器扫描）", "items": lib_opts}}
                        ]},
                    ]},
                    {"component": "VRow", "content": [
                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                            {"component": "VSwitch", "props": {"prop": "translate_actor", "model": "translate_actor", "label": "翻译 Actor（演员）"}}
                        ]},
                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                            {"component": "VSwitch", "props": {"prop": "translate_voice_actor", "model": "translate_voice_actor", "label": "翻译 VoiceActor（声优）"}}
                        ]},
                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                            {"component": "VSwitch", "props": {"prop": "translate_director", "model": "translate_director", "label": "翻译导演"}}
                        ]},
                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                            {"component": "VSwitch", "props": {"prop": "translate_writer", "model": "translate_writer", "label": "翻译编剧"}}
                        ]},
                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                            {"component": "VSwitch", "props": {"prop": "translate_producer", "model": "translate_producer", "label": "翻译制作人"}}
                        ]},
                        {"component": "VCol", "props": {"cols": 12, "md": 4}, "content": [
                            {"component": "VSwitch", "props": {"prop": "translate_all", "model": "translate_all", "label": "翻译全部类型（忽略以上开关）"}}
                        ]},
                    ]},
                    {"component": "VRow", "content": [
                        {"component": "VCol", "props": {"cols": 12}, "content": [
                            {"component": "VTextarea", "props": {"prop": "prompt_template", "model": "prompt_template", "label": "自定义大模型提示词（含 {title_json} {year_json} {terms_json} 占位符）", "rows": 10, "auto-grow": True}}
                        ]},
                    ]},
                ],
            },
        ], {
            "enabled": False,
            "onlyonce": False,
            "force_refresh": False,
            "cron": "0 4 * * *",
            "delay": 2,
            "max_people_per_title": 15,
            "max_people_per_batch": 5,
            "overwrite_chinese": False,
            "libraries": [],
            "translate_actor": True,
            "translate_voice_actor": True,
            "translate_director": False,
            "translate_writer": False,
            "translate_producer": False,
            "translate_all": False,
            "prompt_template": DEFAULT_PROMPT,
        }

    @staticmethod
    def _get_emby_info(service: ServiceInfo) -> Tuple[Optional[str], Optional[str]]:
        inst = service.instance
        host = getattr(inst, '_host', None)
        api_key = getattr(inst, '_apikey', None)
        if host and isinstance(host, str):
            host = host.strip('`').rstrip('/').strip()
        return host, api_key

    def _emby_get(self, service: ServiceInfo, path: str, **kwargs) -> Optional[dict]:
        host, api_key = self._get_emby_info(service)
        if not host or not api_key:
            logger.error(f"无法获取 Emby 连接信息")
            return None
        user_id = getattr(service.instance, 'user', None)
        sep = '&' if '?' in path else '?'
        url = f"{host}{path}{sep}api_key={api_key}"
        if user_id and 'UserId=' not in path and 'userid=' not in path.lower():
            url += f"&UserId={user_id}"
        try:
            safe_url = url.split('?')[0]
            qs = '&'.join([p for p in url.split('?')[1].split('&') if 'api_key' not in p.lower()]) if '?' in url else ''
            logger.debug(f"Emby GET -> {safe_url}?{qs[:160]}")
            resp = RequestUtils().get_res(url, **kwargs)
            if resp and resp.status_code == 200:
                return resp.json()
            body = ""
            try:
                body = (resp.content.decode("utf-8", "replace") if resp else "")[:400]
            except Exception:
                pass
            logger.warning(f"Emby GET {path[:80]} 失败: status={resp.status_code if resp else '无响应'}, body={body}")
        except Exception as e:
            logger.error(f"Emby GET {path[:80]} 异常: {type(e).__name__}: {e}")
        return None

    def _emby_post(self, service: ServiceInfo, path: str, **kwargs) -> bool:
        host, api_key = self._get_emby_info(service)
        if not host or not api_key:
            logger.error(f"无法获取 Emby 连接信息")
            return False
        user_id = getattr(service.instance, 'user', None)
        sep = '&' if '?' in path else '?'
        url = f"{host}{path}{sep}api_key={api_key}"
        if user_id and 'UserId=' not in path and 'userid=' not in path.lower():
            url += f"&UserId={user_id}"
        try:
            headers = kwargs.pop('headers', {})
            if 'json' in kwargs:
                headers.setdefault("Content-Type", "application/json")
            resp = RequestUtils(headers=headers).post_res(url, **kwargs)
            if resp and resp.status_code in (200, 204):
                return True
            body = ""
            try:
                body = (resp.content.decode("utf-8", "replace") if resp else "")[:400]
            except Exception:
                pass
            logger.warning(f"Emby POST {path[:80]} 失败: status={resp.status_code if resp else '无响应'}, body={body}")
            return False
        except Exception as e:
            logger.error(f"Emby POST {path[:80]} 异常: {type(e).__name__}: {e}")
            return False

    def _parse_selected_libraries(self) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {}
        for lib_value in (self._libraries or []):
            if isinstance(lib_value, str) and ":" in lib_value:
                server, lib_id = lib_value.split(":", 1)
                result.setdefault(server, []).append(lib_id)
        return result

    def service_infos(self) -> Dict[str, ServiceInfo]:
        selected_libs = self._parse_selected_libraries()
        target_servers = list(selected_libs.keys()) if selected_libs else None
        try:
            services = MediaServerHelper().get_services(type_filter="emby", name_filters=target_servers) or {}
        except Exception as e:
            logger.warning(f"获取媒体服务列表失败: {e}")
            services = {}
        return {k: v for k, v in services.items() if not getattr(v.instance, "is_inactive", lambda: False)()}

    def _person_type_allowed(self, p_type: str, role: str = "") -> bool:
        if self._translate_all:
            return True
        p_type_l = (p_type or "").lower()
        role_l = (role or "").lower()
        if self._translate_actor and ("actor" in p_type_l or p_type_l == ""):
            return True
        if self._translate_voice_actor and ("voice" in p_type_l or "配音" in (role or "")):
            return True
        if self._translate_director and "director" in p_type_l:
            return True
        if self._translate_writer and "writer" in p_type_l:
            return True
        if self._translate_producer and "producer" in p_type_l:
            return True
        return False

    @staticmethod
    def _is_all_chinese(text: str) -> bool:
        if not text:
            return False
        stripped = re.sub(r"[\s·・・\(\)（）\[\]【】,，.。:：\-—/\\0-9a-zA-Z]", "", text)
        if not stripped:
            return False
        return all("\u4e00" <= c <= "\u9fff" for c in stripped)

    def _zhconv_or_skip(self, text: str) -> Optional[str]:
        if not HAS_ZHCONV:
            return None
        try:
            if self._is_all_chinese(text):
                simplified = zhconv.convert(text, "zh-cn")
                if simplified and simplified != text:
                    return simplified
        except Exception:
            return None
        return None

    def _try_llm_via_sdk(self, prompt: str, timeout_read: float = 60.0) -> Optional[str]:
        if not self._llm_client:
            return None
        try:
            resp = self._llm_client.chat.completions.create(
                model=self._llm_model or "deepseek-ai/DeepSeek-V4-Flash",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                timeout=(10.0, timeout_read),
            )
            if resp and resp.choices and len(resp.choices) > 0:
                content = resp.choices[0].message.content or ""
                if content.strip():
                    return content
            logger.warning("LLM SDK 返回空内容")
            return None
        except _openai_mod.APITimeoutError if _openai_mod else Exception as e:
            logger.warning(f"LLM SDK APITimeoutError: {e}（不重试，立即转requests）")
            return None
        except Exception as e:
            logger.warning(f"LLM SDK 失败: {type(e).__name__}: {e}（转 requests 兜底）")
            return None

    def _try_llm_via_requests(self, prompt: str) -> Optional[str]:
        base_url = str(getattr(settings, 'LLM_BASE_URL', '') or '').rstrip('/')
        api_key = str(getattr(settings, 'LLM_API_KEY', '') or '')
        model = str(getattr(settings, 'LLM_MODEL', '') or self._llm_model or '')
        if not base_url or not api_key or not model:
            return None
        if base_url.endswith("/v1"):
            chat_url = f"{base_url}/chat/completions"
        elif "/v1" in base_url:
            chat_url = f"{base_url.rstrip('/')}/chat/completions"
        else:
            chat_url = f"{base_url}/v1/chat/completions"
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "stream": False,
        }
        proxy_cfg = self._get_proxy_for_llm()
        attempts = [
            ("via proxy", 60, (proxy_cfg.get("https") or proxy_cfg.get("http")) if proxy_cfg else None),
            ("裸连", 60, None),
        ]
        last_err = ""
        for label, tmo, proxy_url in attempts:
            try:
                proxies_for_req = None
                if proxy_url:
                    proxies_for_req = {"http": proxy_url, "https": proxy_url}
                logger.debug(f"LLM HTTP ({label}) 调用: model={model}")
                headers = dict(self._LLM_HEADERS)
                headers["Authorization"] = f"Bearer {api_key}"
                resp = _requests.post(
                    chat_url,
                    json=body,
                    headers=headers,
                    timeout=(10.0, tmo),
                    verify=False,
                    allow_redirects=True,
                    proxies=proxies_for_req,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices") or []
                    if choices:
                        content = (choices[0].get("message") or {}).get("content") or ""
                        if content.strip():
                            return content
                    last_err = f"HTTP {label} 返回空 choices"
                    logger.warning(f"LLM HTTP ({label}): {last_err}")
                else:
                    last_err = f"HTTP {label} status={resp.status_code}, body={resp.text[:300]}"
                    logger.warning(f"LLM HTTP ({label}) 失败: {last_err}")
            except _requests.exceptions.ReadTimeout as e:
                last_err = f"读超时: {e}"
                logger.warning(f"LLM HTTP ({label}) 读超时: {e}{(' (via proxy)' if proxy_url else '')}")
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                logger.warning(f"LLM HTTP ({label}) 异常: {last_err}{(' (via proxy)' if proxy_url else '')}")
        self._llm_last_error = last_err or "未知"
        return None

    @staticmethod
    def _parse_llm_json(content: str) -> Dict[str, str]:
        if not content:
            return {}
        try:
            s = content.strip()
            if s.startswith("```"):
                s = re.sub(r"^```(?:json)?\s*", "", s)
                s = re.sub(r"\s*```$", "", s)
            first = s.find("{")
            last = s.rfind("}")
            if first >= 0 and last > first:
                s = s[first:last + 1]
            result = json.loads(s)
            if isinstance(result, dict):
                return {str(k): str(v) for k, v in result.items()}
        except Exception as e:
            logger.warning(f"解析 LLM JSON 失败: {type(e).__name__}: {e}; 原始内容前200字符: {content[:200]}")
        return {}

    def _call_llm_translate(self, title: str, year: str, terms: List[str]) -> Dict[str, str]:
        if not terms:
            return {}
        cache_key = f"{title}|||{year}"
        cache_for_title = self._name_cache.get(cache_key) or {}
        uncached = [t for t in terms if t not in cache_for_title]
        if not uncached:
            return {t: cache_for_title[t] for t in terms if t in cache_for_title}
        try:
            title_json = json.dumps(title, ensure_ascii=False)
            year_json = json.dumps(year, ensure_ascii=False)
            terms_json = json.dumps(uncached, ensure_ascii=False)
        except Exception:
            title_json = f'"{title}"'
            year_json = f'"{year}"'
            terms_json = json.dumps(uncached, ensure_ascii=False)
        tmpl = self._prompt_template or DEFAULT_PROMPT
        try:
            prompt = tmpl.replace("{title_json}", title_json).replace("{year_json}", year_json).replace("{terms_json}", terms_json)
        except Exception:
            prompt = DEFAULT_PROMPT.replace("{title_json}", title_json).replace("{year_json}", year_json).replace("{terms_json}", terms_json)

        result: Dict[str, str] = {}
        sdk_out = self._try_llm_via_sdk(prompt, timeout_read=60.0)
        if sdk_out:
            result = self._parse_llm_json(sdk_out)
        if not result:
            req_out = self._try_llm_via_requests(prompt)
            if req_out:
                result = self._parse_llm_json(req_out)
        for orig, trans in result.items():
            if trans:
                cache_for_title[orig] = trans
        final: Dict[str, str] = {}
        for t in terms:
            if t in cache_for_title and cache_for_title[t]:
                final[t] = cache_for_title[t]
            else:
                simp = self._zhconv_or_skip(t)
                if simp:
                    final[t] = simp
                    cache_for_title[t] = simp
        self._name_cache[cache_key] = cache_for_title
        return final

    def _update_people_with_fallback(self, service: ServiceInfo, item_id: str, new_people: List[dict],
                                     item_data: Optional[dict] = None) -> int:
        if not new_people:
            return 0
        changes = 0
        try:
            payload_people = {"Id": item_id, "People": new_people}
            ok1 = self._emby_post(service, f"/Items/{item_id}", json=payload_people)
            if ok1:
                changes = sum(1 for p in new_people if p.get("Name"))
                logger.debug(f"Emby 更新成功（方法1，直接 POST People）: item={item_id}, people={changes}")
                return changes
        except Exception as e:
            logger.debug(f"方法1 POST People 失败: {e}")
        if item_data and isinstance(item_data, dict):
            try:
                payload_full: Dict[str, Any] = {}
                for k, v in item_data.items():
                    if k in _EMBY_STRIP_FIELDS and k != "People":
                        continue
                    payload_full[k] = v
                payload_full["Id"] = item_id
                payload_full["People"] = new_people
                ok2 = self._emby_post(service, f"/Items/{item_id}", json=payload_full)
                if ok2:
                    changes = sum(1 for p in new_people if p.get("Name"))
                    logger.debug(f"Emby 更新成功（方法2，整条POST剔除只读字段）: item={item_id}, people={changes}")
                    return changes
            except Exception as e:
                logger.debug(f"方法2 整条 POST 失败: {e}")
        logger.warning(f"Emby 更新失败（两种方法均失败）: item={item_id}")
        return 0

    def _apply_translation_to_people_inner(self, server_name: str, service: ServiceInfo, item_id: str,
                                           title: str, original_title: str, year_str: str,
                                           media_type: str,
                                           item_data: Optional[dict] = None) -> int:
        t_start = time.time()
        WALL_TIME_LIMIT = 240.0
        try:
            people_raw = []
            if item_data and isinstance(item_data, dict):
                people_raw = item_data.get("People") or []
            if not people_raw:
                logger.debug(f"{title}: 没有 People 字段，跳过")
                return 0
            max_n = max(1, int(self._max_people_per_title or 15))
            candidates: List[dict] = []
            for p in people_raw:
                if len(candidates) >= max_n:
                    break
                p_type = str(p.get("Type") or "")
                p_role = str(p.get("Role") or "")
                if not self._person_type_allowed(p_type, p_role):
                    continue
                raw_name = str(p.get("Name") or "").strip()
                if not raw_name:
                    continue
                if not self._overwrite_chinese and self._is_all_chinese(raw_name):
                    continue
                candidates.append(dict(p))
            if not candidates:
                return 0
            pending_candidates: List[dict] = []
            for c in candidates:
                raw = str(c.get("Name") or "").strip()
                simp = self._zhconv_or_skip(raw)
                if simp and raw != simp:
                    c["Name"] = simp
                    cache_key = f"{title}|||{year_str}"
                    d = self._name_cache.setdefault(cache_key, {})
                    d[raw] = simp
                    self._name_cache[cache_key] = d
                pending_candidates.append(c)
            batch_size = max(1, int(self._max_people_per_batch or 5))
            all_names: List[str] = []
            for c in pending_candidates:
                raw = str(c.get("Name") or "")
                if raw and raw not in all_names:
                    all_names.append(raw)
            applied: Dict[str, str] = {}
            for i in range(0, len(all_names), batch_size):
                if time.time() - t_start > WALL_TIME_LIMIT:
                    logger.warning(f"【{title}】单条目 wall-clock 超时 {WALL_TIME_LIMIT}s，剩余批次跳过，下次 cron 再补")
                    break
                batch = all_names[i:i + batch_size]
                try:
                    batch_map = self._call_llm_translate(title, year_str, batch)
                    for k, v in batch_map.items():
                        if v and k != v:
                            applied[k] = v
                except Exception as e:
                    logger.warning(f"【{title}】第{i // batch_size + 1}批LLM异常: {type(e).__name__}: {e}")
                finally:
                    try:
                        time.sleep(min(int(self._delay or 2), 2))
                    except Exception:
                        pass
            new_people = [dict(p) for p in people_raw]
            n_changes = 0
            for idx, p in enumerate(new_people):
                raw = str(p.get("Name") or "").strip()
                if not raw:
                    continue
                if raw in applied:
                    new_name = applied[raw].strip()
                    if new_name and new_name != raw:
                        new_people[idx]["Name"] = new_name
                        n_changes += 1
                raw_role = str(p.get("Role") or "").strip()
                if raw_role and not self._is_all_chinese(raw_role):
                    role_trans = applied.get(raw_role)
                    if role_trans and role_trans != raw_role:
                        new_people[idx]["Role"] = role_trans
                        n_changes += 1
                    else:
                        simp_role = self._zhconv_or_skip(raw_role)
                        if simp_role and simp_role != raw_role:
                            new_people[idx]["Role"] = simp_role
                            n_changes += 1
            if n_changes <= 0:
                self._processed[f"{server_name}:{item_id}"] = datetime.now().isoformat(timespec='seconds')
                return 0
            updated = self._update_people_with_fallback(service, item_id, new_people, item_data)
            if updated > 0:
                self._processed[f"{server_name}:{item_id}"] = datetime.now().isoformat(timespec='seconds')
                return updated
            return 0
        except Exception as e:
            logger.error(f"【{title}】翻译+写回 异常: {type(e).__name__}: {e}", exc_info=True)
            return 0

    def sync_library(self):
        if not self._enabled:
            return
        self._event.clear()
        service_infos = self.service_infos()
        if not service_infos:
            logger.warning("没有可用的 Emby 服务器（请先选择服务器或媒体库）")
            self._event.set()
            return
        selected_libs = self._parse_selected_libraries()
        total_titles = success = skipped = failed = 0
        total_fields_all = 0
        try:
            for server, service in service_infos.items():
                try:
                    if self._event.is_set() or not self._enabled:
                        logger.info("收到停止信号，中断扫描")
                        break
                    logger.info(f"开始扫描服务器 {server}...")
                    target_lib_ids = set(selected_libs.get(server, []))
                    host, api_key = self._get_emby_info(service)
                    if not host or not api_key:
                        logger.error(f"{server}: 无法获取 Emby 连接信息，跳过此服务器")
                        continue
                    user_id = getattr(service.instance, 'user', None)
                    vf_data = self._emby_get(service, "/Library/VirtualFolders")
                    if not vf_data or not isinstance(vf_data, list):
                        try:
                            vf2 = self._emby_get(service, f"/Users/{user_id}/Views" if user_id else "/Library/SelectableMediaFolders")
                            if isinstance(vf2, dict):
                                vf_data = vf2.get("Items") or []
                            elif isinstance(vf2, list):
                                vf_data = vf2
                        except Exception:
                            pass
                    if not vf_data or not isinstance(vf_data, list):
                        logger.error(f"{server}: 拿不到媒体库列表，跳过此服务器")
                        continue
                    libraries = []
                    for vf in vf_data:
                        lib_id = str(vf.get("Id") or vf.get("ItemId") or vf.get("Guid") or "")
                        lib_name = str(vf.get("Name") or vf.get("DisplayName") or "")
                        if lib_id:
                            libraries.append({"id": lib_id, "name": lib_name})
                    logger.info(f"服务器 {server} 共有 {len(libraries)} 个媒体库")
                    for library in libraries:
                        try:
                            if self._event.is_set() or not self._enabled:
                                break
                            lid = library["id"]
                            lname = library["name"]
                            is_selected = bool(target_lib_ids) and lid in target_lib_ids
                            if target_lib_ids and not is_selected:
                                logger.info(f"跳过媒体库: {lname}（未选择）")
                                continue
                            logger.info(f"扫描媒体库: {lname} (id={lid})")
                            fields = "People,Genres,Tags,ProviderIds,OriginalTitle,PremiereDate,ProductionYear"
                            page_size = 200
                            start_index = 0
                            page_counter = 0
                            while True:
                                if self._event.is_set() or not self._enabled:
                                    break
                                page_counter += 1
                                items_url = (
                                    f"/Items?ParentId={lid}&Recursive=true"
                                    f"&Fields={fields}&IncludeItemTypes=Movie,Series"
                                    f"&StartIndex={start_index}&Limit={page_size}"
                                )
                                try:
                                    items_data = self._emby_get(service, items_url)
                                except Exception as e:
                                    logger.error(f"分页获取 {lname} 失败 page={page_counter}: {e}")
                                    break
                                if not items_data or not isinstance(items_data, dict):
                                    logger.warning(f"获取 {lname} 条目失败，停止此库分页")
                                    break
                                items = items_data.get("Items") or []
                                total_record_count = int(items_data.get("TotalRecordCount") or len(items))
                                if not items:
                                    break
                                logger.info(f"  [{lname}] page={page_counter} 条目数={len(items)}，总={total_record_count}")
                                per_page_processed = per_page_success = per_page_fail = per_page_skip = 0
                                per_page_fields = 0
                                for it in items:
                                    if self._event.is_set() or not self._enabled:
                                        break
                                    if not it or not isinstance(it, dict):
                                        continue
                                    item_id = str(it.get("Id") or "")
                                    if not item_id:
                                        continue
                                    item_type = str(it.get("Type") or "")
                                    is_series = "Series" in item_type
                                    is_movie = "Movie" in item_type
                                    if not is_series and not is_movie:
                                        continue
                                    total_titles += 1
                                    per_page_processed += 1
                                    item_key = f"{server}:{item_id}"
                                    if not self._force_refresh and item_key in self._processed:
                                        skipped += 1
                                        per_page_skip += 1
                                        continue
                                    t_title = str(it.get("Name") or "未知")
                                    t_orig = str(it.get("OriginalTitle") or t_title)
                                    prod_year = it.get("ProductionYear")
                                    premier = str(it.get("PremiereDate") or "")
                                    t_year = str(prod_year if prod_year else (premier[:4] if premier else ""))
                                    mtype = "TV" if is_series else "MOVIE"
                                    try:
                                        logger.info(f"处理: {t_title} ({'番剧' if is_series else '动漫电影'})")
                                        n_trans = self._apply_translation_to_people_inner(
                                            server, service, item_id, t_title, t_orig, t_year, mtype, item_data=it,
                                        )
                                        if n_trans > 0:
                                            logger.info(f"{t_title} ({'番剧' if is_series else '动漫电影'}): Emby 更新成功，翻译 {n_trans} 个字段")
                                            self._add_history(item_key, t_title, server, lname, n_trans, item_id)
                                            total_fields_all += n_trans
                                            per_page_fields += n_trans
                                            success += 1
                                            per_page_success += 1
                                        else:
                                            skipped += 1
                                            per_page_skip += 1
                                    except Exception as e:
                                        failed += 1
                                        per_page_fail += 1
                                        logger.error(f"处理 {t_title or '未知'} 失败: {type(e).__name__}: {e}", exc_info=True)
                                    finally:
                                        if per_page_processed % self._SAVE_INTERVAL == 0:
                                            self._save_cache()
                                        try:
                                            time.sleep(min(int(self._delay or 2), 2))
                                        except Exception:
                                            pass
                                logger.info(
                                    f"  [{lname}] 页{page_counter}统计：处理{per_page_processed}，"
                                    f"成功翻译{per_page_success}({per_page_fields}字段)，跳过{per_page_skip}，失败{per_page_fail}"
                                )
                                self._save_cache()
                                start_index += len(items)
                                if start_index >= total_record_count or len(items) < page_size:
                                    break
                        except Exception as e:
                            logger.error(f"处理库 {library.get('name')} 时发生异常: {type(e).__name__}: {e}", exc_info=True)
                        finally:
                            self._save_cache()
                except Exception as e:
                    logger.error(f"处理服务器 {server} 异常: {type(e).__name__}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"扫描全局异常: {type(e).__name__}: {e}", exc_info=True)
        finally:
            self._save_cache()
            self._event.set()
        summary = (
            f"扫描完成\n总计: {total_titles}\n成功(翻译作品): {success}\n"
            f"翻译字段: {total_fields_all}\n跳过: {skipped}\n失败: {failed}"
        )
        logger.info(
            f"扫描完成 - 总计: {total_titles}, 成功: {success}, 翻译字段数: {total_fields_all}, "
            f"跳过: {skipped}, 失败: {failed}"
        )
        try:
            self.post_message(
                mtype=NotificationType.Plugin,
                title="Emby 演职人员中文化",
                text=summary,
            )
        except Exception:
            pass
