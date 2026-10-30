# -*- coding: utf-8 -*-
"""MoviePilot V3 插件：OpenClash 控制面板（OpenClashPanel）。

能力：
- 状态总览（含全部策略组）、策略组/节点切换、批量/单项测速、规则模式切换、刷新订阅；
- Smart 智能组支持（OpenClash smart 内核的 type=smart）；
- 访问检查（MP 网络 / OpenClash 代理两套通道，后台采集 + 缓存）；
- 日志（插件日志 + 内核日志）；
- 远程命令（英文命令 + 中文说明）：/oc_status、/oc_check、/oc_node、/oc_mode、/oc_refresh、/oc_help；
  TG 支持按钮选择组/节点/模式，微信等渠道自动降级为纯文本查询；
- 仪表盘注册（全宽小组件：状态 / 访问检查 / 策略组与节点）。

数据面：
- OpenClash external-controller（默认 http://<路由器>:9090，Bearer secret）；
- secret 即 OpenClash 的 Dashboard 密码。
"""
from __future__ import annotations

import asyncio
import collections
import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple
from urllib.parse import quote, urlsplit

from fastapi import Request

from app.sdk.logging import logger
from app.sdk.plugin import _PluginBase

from .clash_client import (
    DEFAULT_DELAY_TIMEOUT,
    DEFAULT_DELAY_URL,
    ClashApiError,
    ClashClient,
    build_groups,
    build_providers,
    build_status,
    GROUP_TYPES,
    test_delays,
)
from .netcheck import (
    DEFAULT_SITES,
    DEFAULT_TIMEOUT as NETCHECK_TIMEOUT,
    mask_proxy,
    parse_sites,
    run_netcheck,
)
from .luci_client import OC, LuCiClient, LuCiError

try:
    from app.schemas.types import EventType
    from app.sdk.events import Event, eventmanager
except Exception:  # noqa: BLE001
    EventType = None  # type: ignore
    eventmanager = None  # type: ignore

__all__ = ["OpenClashPanel"]

_DEFAULT_CONFIG: Dict[str, Any] = {
    "enabled": True,
    "api_url": "http://192.168.1.1:9090",
    "secret": "",
    "timeout": 8,
    "delay_test_url": DEFAULT_DELAY_URL,
    "delay_test_timeout": DEFAULT_DELAY_TIMEOUT,
    "auto_refresh": 10,
    "max_delay_concurrency": 8,
    "show_dashboard": True,
    "dashboard_url": "http://192.168.1.1:9090/ui/zashboard/",
    "log_level": "info",
    "netcheck_mode": "kernel",
    "netcheck_interval": 30,
    "netcheck_timeout": 6,
    "netcheck_sites": [dict(site) for site in DEFAULT_SITES],
    "allow_commands": True,
    "openwrt_enabled": False,
    "openwrt_scheme": "http",
    "openwrt_host": "192.168.1.1",
    "openwrt_username": "root",
    "openwrt_password": "",
}

_VALID_MODES = ("rule", "global", "direct")
_LOG_BUFFER_SIZE = 500

_PM_LOG_RE = re.compile(
    r"^【(?P<level>[A-Za-z]+)】\s*"
    r"(?P<dt>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})(?:[,.]\d+)?\s*"
    r"(?:\[[^\]]*\]\s*)?-\s*(?P<module>\S+)\s*-\s*(?P<msg>.*)$"
)


def normalize_api_url(value: str) -> str:
    """把用户可能填错的地址纠正成 external-controller 根地址。"""
    text = (value or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = "http://" + text
    try:
        parts = urlsplit(text)
    except ValueError:
        return text
    if not parts.hostname:
        return text
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{parts.hostname}{port}"


def _tail_lines(path: Path, limit: int) -> List[str]:
    """从文件尾部读最后 limit 行（避免整文件加载）。"""
    if limit <= 0 or not path.is_file():
        return []
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            block = 64 * 1024
            data = b""
            while size > 0 and data.count(b"\n") <= limit:
                step = min(block, size)
                size -= step
                handle.seek(size)
                data = handle.read(step) + data
        lines = data.splitlines()[-limit:]
        return [line.decode("utf-8", "replace") for line in lines]
    except OSError:
        return []


def parse_plugin_log_lines(lines: List[str]) -> List[Dict[str, str]]:
    """把 MP 插件日志文本行解析成前端用的 {time, level, text}。"""
    items: List[Dict[str, str]] = []
    for raw in lines:
        text = (raw or "").rstrip()
        if not text:
            continue
        match = _PM_LOG_RE.match(text)
        if not match:
            items.append({"time": "", "level": "info", "text": text})
            continue
        stamp = match.group("dt")
        items.append(
            {
                "time": stamp.split(" ")[-1],
                "level": match.group("level").lower(),
                "text": match.group("msg"),
            }
        )
    return items


def _fmt_bytes(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    while number >= 1024 and index < len(units) - 1:
        number /= 1024
        index += 1
    return f"{number:.1f} {units[index]}" if index else f"{int(number)} {units[index]}"


class OpenClashPanel(_PluginBase):
    """OpenClash 控制面板插件。"""

    plugin_name = "OpenClash 控制面板"
    plugin_desc = (
        "在 MoviePilot 里查看 OpenClash/Mihomo 状态与全部策略组、切换节点/规则模式、"
        "批量/单项测速、刷新订阅、访问检查（MP/OpenClash 双通道）、查看日志；"
        "支持 Smart 智能组、TG 按钮命令、仪表盘全宽组件。"
    )
    plugin_icon = "https://raw.githubusercontent.com/LXT-A-X/MoviePilot-Plugins/main/icons/openclashpanel.png"
    plugin_version = "1.12.0"
    plugin_author = "LXT-A-X"
    plugin_config_prefix = "openclashpanel_"
    plugin_order = 110
    auth_level = 2

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self._config: Dict[str, Any] = dict(_DEFAULT_CONFIG)
        self._enabled = False
        self._log_buffer: Deque[Dict[str, str]] = collections.deque(maxlen=_LOG_BUFFER_SIZE)
        self._log_stop = threading.Event()
        self._log_thread: Optional[threading.Thread] = None
        self._api_ok: Optional[bool] = None
        # 访问检查后台采集
        self._net_cache: Dict[str, Dict[str, Any]] = {}
        self._net_stop = threading.Event()
        self._net_thread: Optional[threading.Thread] = None
        self._net_event = threading.Event()
        self._net_target: Optional[str] = None
        self._net_progress: Dict[str, Dict[str, Any]] = {}
        # 命令交互缓存（TG 按钮用索引，避免 callback_data 超长）
        self._cmd_groups: List[Dict[str, Any]] = []
        self._cmd_nodes: Dict[str, List[Dict[str, Any]]] = {}
        self._cmd_current_group = ""
        self._cmd_ts = 0.0
        self._cmd_page = 0
        self._cmd_node_page = 0
        self._cmd_current_group_index = -1

    # ------------------------------------------------------------------ 生命周期
    def init_plugin(self, config: Optional[Dict[str, Any]] = None) -> None:
        merged = dict(_DEFAULT_CONFIG)
        if config:
            merged.update({k: v for k, v in config.items() if v is not None})
        merged["api_url"] = normalize_api_url(str(merged.get("api_url") or ""))
        self._config = merged
        self._enabled = bool(merged.get("enabled"))
        self._api_ok = None
        try:
            logger.info(
                f"插件初始化：enabled={self._enabled}，API={self._config.get('api_url') or '未配置'}，"
                f"命令={'开' if self._config.get('allow_commands') else '关'}"
            )
        except Exception:  # noqa: BLE001
            pass
        self._restart_log_worker()
        self._restart_net_worker()

    def get_state(self) -> bool:
        return self._enabled

    def stop_service(self) -> None:
        self._stop_log_worker()
        self._stop_net_worker()
        self._enabled = False
        try:
            logger.info("插件已停用")
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ 访问检查后台采集
    def _restart_net_worker(self) -> None:
        self._stop_net_worker()
        cfg = self._current_config()
        if not self._enabled or not cfg.get("api_url") or not cfg.get("secret"):
            return
        self._net_stop = threading.Event()
        self._net_event = threading.Event()
        self._net_thread = threading.Thread(
            target=self._net_worker, name="OpenClashPanel-Netcheck", daemon=True
        )
        self._net_thread.start()
        try:
            logger.info("访问检查采集线程已启动")
        except Exception:  # noqa: BLE001
            pass

    def _stop_net_worker(self) -> None:
        had_thread = bool(self._net_thread and self._net_thread.is_alive())
        try:
            self._net_stop.set()
            self._net_event.set()
        except Exception:  # noqa: BLE001
            pass
        thread = self._net_thread
        self._net_thread = None
        if thread and thread.is_alive():
            thread.join(timeout=3)
        if had_thread:
            try:
                logger.info("访问检查采集线程已停止")
            except Exception:  # noqa: BLE001
                pass

    def _net_worker(self) -> None:
        try:
            asyncio.run(self._net_loop())
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"访问检查采集线程退出：{exc}")

    async def _net_loop(self) -> None:
        stop = self._net_stop
        while not stop.is_set():
            cfg = self._current_config()
            interval = max(10, int(cfg.get("netcheck_interval") or 30))
            target = self._net_target or str(cfg.get("netcheck_mode") or "kernel")
            self._net_target = None
            try:
                data = await self._run_netcheck_once(target)
                self._net_cache[data["mode"]] = {**data, "ts": time.time()}
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"访问检查失败：{exc}")
            self._net_event.wait(interval)
            self._net_event.clear()

    def _cached_netcheck(self, mode: str) -> Optional[Dict[str, Any]]:
        data = self._net_cache.get(mode)
        if not data:
            return None
        interval = max(10, int(self._current_config().get("netcheck_interval") or 30))
        if time.time() - float(data.get("ts") or 0) > interval + 5:
            return None
        return {**data, "checking": False, "updated_at": float(data.get("ts") or 0)}

    # ------------------------------------------------------------------ 插件日志文件
    def _plugin_log_file(self) -> Optional[Path]:
        """返回 MP 为本插件写的日志文件（config/logs/plugins/openclashpanel.log）。"""
        try:
            from app.sdk.config import settings

            log_path = Path(settings.LOG_PATH)
        except Exception:  # noqa: BLE001
            try:
                from app.runtime.settings import get_runtime_setting

                log_path = Path(get_runtime_setting("LOG_PATH"))
            except Exception:  # noqa: BLE001
                return None
        plugin_dir_name = Path(__file__).resolve().parent.name
        return log_path / "plugins" / f"{plugin_dir_name}.log"

    # ------------------------------------------------------------------ 内核日志采集
    def _restart_log_worker(self) -> None:
        self._stop_log_worker()
        cfg = self._current_config()
        if not self._enabled or not cfg.get("api_url") or not cfg.get("secret"):
            return
        self._log_stop = threading.Event()
        self._log_thread = threading.Thread(
            target=self._log_worker, name="OpenClashPanel-Logs", daemon=True
        )
        self._log_thread.start()
        try:
            logger.info("内核日志采集线程已启动")
        except Exception:  # noqa: BLE001
            pass

    def _stop_log_worker(self) -> None:
        had_thread = bool(self._log_thread and self._log_thread.is_alive())
        try:
            self._log_stop.set()
        except Exception:  # noqa: BLE001
            pass
        thread = self._log_thread
        self._log_thread = None
        if thread and thread.is_alive():
            thread.join(timeout=3)
        if had_thread:
            try:
                logger.info("内核日志采集线程已停止")
            except Exception:  # noqa: BLE001
                pass

    def _log_worker(self) -> None:
        try:
            asyncio.run(self._log_loop())
        except Exception as exc:  # noqa: BLE001
            try:
                logger.warning(f"内核日志线程退出：{exc}")
            except Exception:  # noqa: BLE001
                pass

    async def _log_loop(self) -> None:
        import httpx

        stop = self._log_stop
        while not stop.is_set():
            cfg = self._current_config()
            api_url = normalize_api_url(str(cfg.get("api_url") or ""))
            secret = str(cfg.get("secret") or "")
            level = str(cfg.get("log_level") or "info")
            if not api_url or not secret:
                stop.wait(5)
                continue
            headers = {"Authorization": f"Bearer {secret}"} if secret else {}
            connected = False
            try:
                async with httpx.AsyncClient(
                    base_url=api_url,
                    headers=headers,
                    timeout=httpx.Timeout(connect=5, read=None, write=5, pool=5),
                    trust_env=False,
                ) as client:
                    async with client.stream("GET", "/logs", params={"level": level}) as response:
                        if response.status_code >= 400:
                            stop.wait(5)
                            continue
                        connected = True
                        try:
                            logger.info(f"内核日志已连接：{api_url}（level={level}）")
                        except Exception:  # noqa: BLE001
                            pass
                        async for line in response.aiter_lines():
                            if stop.is_set():
                                return
                            line = (line or "").strip()
                            if not line:
                                continue
                            try:
                                item = json.loads(line)
                            except ValueError:
                                item = {"type": "info", "payload": line}
                            self._log_buffer.append(
                                {
                                    "time": datetime.now().strftime("%H:%M:%S"),
                                    "level": str(item.get("type") or "info").lower(),
                                    "text": str(item.get("payload") or ""),
                                }
                            )
            except Exception as exc:  # noqa: BLE001
                if not connected:
                    try:
                        logger.warning(f"内核日志连接失败，3 秒后重试：{exc}")
                    except Exception:  # noqa: BLE001
                        pass
                stop.wait(3)

    # ------------------------------------------------------------------ 渲染模式 / 页面
    @staticmethod
    def get_render_mode() -> Tuple[str, Optional[str]]:
        return "vue", "dist/assets"

    def _current_config(self) -> Dict[str, Any]:
        cfg = {**_DEFAULT_CONFIG, **(self._config or {})}
        cfg["api_url"] = normalize_api_url(str(cfg.get("api_url") or ""))
        return cfg

    def get_form(self) -> Tuple[Optional[List[dict]], Dict[str, Any]]:
        return [], self._current_config()

    def get_page(self) -> Optional[List[dict]]:
        return []

    @staticmethod
    def get_sidebar_nav() -> List[Dict[str, Any]]:
        return [
            {
                "nav_key": "main",
                "title": "OpenClash",
                "icon": "mdi-shield-network",
                "section": "system",
                "permission": "admin",
                "order": 55,
            }
        ]

    # ------------------------------------------------------------------ 仪表盘注册（全宽）
    def get_dashboard_meta(self) -> Optional[List[Dict[str, str]]]:
        return [{"key": "main", "name": "OpenClash 状态"}]

    def get_dashboard(self, key: str = "", **kwargs: Any) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], None]]:
        if key not in ("", "main"):
            return None
        return (
            {"cols": 12},
            {"refresh": 30, "border": True, "title": "OpenClash", "subtitle": "状态 · 访问检查 · 策略组"},
            None,
        )

    # ------------------------------------------------------------------ 远程命令
    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        if EventType is None:
            return []
        return [
            {"cmd": "/oc_status", "event": EventType.PluginAction, "desc": "查看 OpenClash 状态与全部策略组", "category": "工具", "data": {"action": "oc_status"}},
            {"cmd": "/oc_check", "event": EventType.PluginAction, "desc": "OpenClash 访问检查", "category": "工具", "data": {"action": "oc_check"}},
            {"cmd": "/oc_node", "event": EventType.PluginAction, "desc": "切换策略组节点（无参数会列出组）", "category": "工具", "data": {"action": "oc_node"}},
            {"cmd": "/oc_mode", "event": EventType.PluginAction, "desc": "切换规则模式（无参数会列出模式）", "category": "工具", "data": {"action": "oc_mode"}},
            {"cmd": "/oc_refresh", "event": EventType.PluginAction, "desc": "刷新订阅节点", "category": "工具", "data": {"action": "oc_refresh"}},
            {"cmd": "/oc_help", "event": EventType.PluginAction, "desc": "OpenClash 命令帮助", "category": "工具", "data": {"action": "oc_help"}},
        ]

    @staticmethod
    def _run_async(coro: Any) -> Any:
        """在独立线程里跑协程，避免事件处理线程已有事件循环时冲突。"""
        box: Dict[str, Any] = {}

        def worker() -> None:
            try:
                box["value"] = asyncio.run(coro)
            except Exception as exc:  # noqa: BLE001
                box["error"] = exc

        thread = threading.Thread(target=worker, daemon=True, name="OpenClashPanel-Cmd")
        thread.start()
        thread.join(timeout=40)
        if "error" in box:
            raise box["error"]
        return box.get("value")

    @staticmethod
    def _is_telegram(channel: Any) -> bool:
        value = getattr(channel, "value", channel)
        return "telegram" in str(value or "").lower()

    def _send_reply(
        self,
        channel: Any,
        title: str,
        text: str,
        buttons: Optional[List[List[dict]]] = None,
        original_message_id: Any = None,
        original_chat_id: Any = None,
    ) -> None:
        base: Dict[str, Any] = {"title": title, "text": text}
        if buttons:
            base["buttons"] = buttons
        if original_message_id:
            edit_kwargs: Dict[str, Any] = {**base, "original_message_id": original_message_id}
            if original_chat_id:
                edit_kwargs["original_chat_id"] = original_chat_id
            try:
                self.post_message(channel=channel, **edit_kwargs)
                return
            except Exception:  # noqa: BLE001
                pass
        try:
            self.post_message(channel=channel, **base)
            return
        except Exception:  # noqa: BLE001
            pass
        try:
            self.post_message(**base)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"命令回复发送失败：{exc}")

    def _handle_plugin_action(self, event: Any) -> None:
        try:
            data = getattr(event, "event_data", None) or {}
            action = str(data.get("action") or "")
            if not action.startswith("oc_"):
                return
            arg = str(data.get("arg_str") or "").strip()
            channel = data.get("channel")
            cfg = self._current_config()
            if action in ("oc_node", "oc_mode", "oc_refresh") and not cfg.get("allow_commands", True):
                self._send_reply(channel, "OpenClash", "操作命令已在插件设置中关闭（allow_commands=false）")
                return
            if action == "oc_status":
                self._send_reply(channel, "OpenClash 状态", self._run_async(self._build_status_text()))
            elif action == "oc_check":
                self._send_reply(channel, "OpenClash 访问检查", self._run_async(self._build_netcheck_text()))
            elif action == "oc_node":
                if arg:
                    if len(arg.split()) == 1:
                        self._send_reply(channel, "OpenClash 节点", self._run_async(self._build_group_nodes_text(arg)))
                    else:
                        self._send_reply(channel, "OpenClash 切换节点", self._run_async(self._build_node_text(arg)))
                else:
                    groups = self._run_async(build_groups(self._client()))
                    self._cmd_groups = groups
                    self._cmd_ts = time.time()
                    text, buttons = self._group_list_page(0, channel)
                    self._send_reply(channel, "OpenClash 策略组", text, buttons)
            elif action == "oc_mode":
                if arg:
                    self._send_reply(channel, "OpenClash 规则模式", self._run_async(self._build_mode_text(arg)))
                else:
                    text, buttons = self._mode_menu(channel)
                    self._send_reply(channel, "OpenClash 规则模式", text, buttons)
            elif action == "oc_refresh":
                self._send_reply(channel, "OpenClash 刷新订阅", self._run_async(self._build_refresh_text()))
            elif action == "oc_help":
                self._send_reply(channel, "OpenClash 命令帮助", self._help_text())
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"处理 OpenClash 命令失败：{exc}")
            self._send_reply(None, "OpenClash", f"命令执行失败：{exc}")

    def _handle_message_action(self, event: Any) -> None:
        """处理 TG 按钮回调（[PLUGIN]OpenClashPanel|oc:...），尽量编辑原消息。"""
        try:
            data = getattr(event, "event_data", None) or {}
            if str(data.get("plugin_id") or "") != self.__class__.__name__:
                return
            content = str(data.get("text") or "")
            channel = data.get("channel")
            original_message_id = data.get("original_message_id")
            original_chat_id = data.get("original_chat_id")
            if not content.startswith("oc:"):
                return

            def reply(title: str, text: str, buttons: Optional[List[List[dict]]] = None) -> None:
                self._send_reply(
                    channel, title, text, buttons,
                    original_message_id=original_message_id,
                    original_chat_id=original_chat_id,
                )

            parts = content.split(":")
            if len(parts) == 3 and parts[1] == "gp":
                text, buttons = self._group_list_page(int(parts[2]), channel)
                reply("OpenClash 策略组", text, buttons)
            elif len(parts) == 3 and parts[1] == "ng":
                text, buttons = self._group_nodes_page(int(parts[2]), 0, channel)
                reply("OpenClash 节点", text, buttons)
            elif len(parts) == 3 and parts[1] == "np":
                text, buttons = self._group_nodes_page(self._cmd_current_group_index, int(parts[2]), channel)
                reply("OpenClash 节点", text, buttons)
            elif len(parts) == 3 and parts[1] == "nn":
                text = self._run_async(self._switch_by_index(int(parts[2])))
                reply("OpenClash 切换节点", text, self._result_buttons())
            elif len(parts) == 2 and parts[1] == "back":
                text, buttons = self._group_list_page(self._cmd_page, channel)
                reply("OpenClash 策略组", text, buttons)
            elif len(parts) == 2 and parts[1] == "close":
                reply("OpenClash", "已退出。发送 /oc_node 可再次打开。", None)
            elif len(parts) == 3 and parts[1] == "m":
                text = self._run_async(self._build_mode_text(parts[2]))
                self._send_reply(channel, "OpenClash 规则模式", text)
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"处理 OpenClash 按钮回调失败：{exc}")
            self._send_reply(None, "OpenClash", f"操作失败：{exc}")

    if eventmanager is not None:
        _handle_plugin_action = eventmanager.register(EventType.PluginAction)(_handle_plugin_action)
        _handle_message_action = eventmanager.register(EventType.MessageAction)(_handle_message_action)

    @staticmethod
    def _help_text() -> str:
        return "\n".join(
            [
                "【OpenClash 命令帮助】",
                "/oc_status - 查看状态与全部策略组",
                "/oc_check - 访问检查（按插件设置里的通道）",
                "/oc_node - 列出策略组；/oc_node 组名 节点名 切换",
                "/oc_mode - 列出规则模式；/oc_mode rule|global|direct 切换",
                "/oc_refresh - 刷新订阅节点",
                "/oc_help - 显示本帮助",
                "",
                "TG 里可直接点按钮选组/节点/模式；微信等渠道用文本命令。",
            ]
        )

    # ------------------------------------------------------------------ 命令内容构建
    async def _build_status_text(self) -> str:
        client = self._client()
        status = await build_status(client)
        groups = await build_groups(client)
        self._cmd_groups = groups
        self._cmd_ts = time.time()
        default_group = next((g for g in groups if "默认代理" in str(g.get("name"))), groups[0] if groups else None)
        lines = [
            "【OpenClash 状态】",
            f"内核：{status.get('version')}（{'Mihomo' if status.get('meta') else 'Clash'}）",
            f"模式：{status.get('mode')}",
        ]
        if default_group:
            now = default_group.get("now")
            if default_group.get("type") == "Smart":
                now = "智能自动选路"
            lines.append(f"默认组：{default_group.get('name')} → {now}")
        lines.extend(
            [
                f"连接：{status.get('active_connections')}",
                f"流量：{_fmt_bytes(status.get('download_total'))} ↓ / {_fmt_bytes(status.get('upload_total'))} ↑",
                "",
                f"策略组（{len(groups)}）：",
            ]
        )
        for group in groups:
            now = group.get("now") or ""
            if group.get("type") == "Smart":
                now = "智能自动选路"
            lines.append(f"· {group.get('name')} [{group.get('type')}] → {now}")
        return "\n".join(lines)

    async def _build_netcheck_text(self) -> str:
        data = await self._run_netcheck_once(self._current_config().get("netcheck_mode") or "mp")
        mode_label = "MP 网络" if data.get("mode") == "mp" else "OpenClash 代理"
        lines = [f"【OpenClash 访问检查 · {mode_label}】"]
        for item in data.get("results") or []:
            if item.get("delay") is None:
                lines.append(f"{item.get('name')}：失败")
            else:
                lines.append(f"{item.get('name')}：{item.get('delay')}ms")
        if data.get("note"):
            lines.append(f"（{data['note']}）")
        return "\n".join(lines)

    _GROUPS_PER_PAGE = 10
    _NODES_PER_PAGE = 8

    @staticmethod
    def _nav_buttons(prefix: str, page: int, total_pages: int, rows: Optional[List[List[dict]]] = None) -> List[List[dict]]:
        result: List[List[dict]] = list(rows or [])
        nav: List[dict] = []
        if page > 0:
            nav.append({"text": "◀ 上一页", "callback_data": f"[PLUGIN]OpenClashPanel|oc:{prefix}:{page - 1}"})
        if page + 1 < total_pages:
            nav.append({"text": "下一页 ▶", "callback_data": f"[PLUGIN]OpenClashPanel|oc:{prefix}:{page + 1}"})
        if nav:
            result.append(nav)
        return result

    def _group_list_page(self, page: int, channel: Any) -> Tuple[str, Optional[List[List[dict]]]]:
        groups = self._cmd_groups
        total_pages = max(1, (len(groups) + self._GROUPS_PER_PAGE - 1) // self._GROUPS_PER_PAGE)
        page = max(0, min(int(page), total_pages - 1))
        self._cmd_page = page
        lines = [f"【OpenClash 策略组】第 {page + 1}/{total_pages} 页"]
        start = page * self._GROUPS_PER_PAGE
        end = min(len(groups), start + self._GROUPS_PER_PAGE)
        for index in range(start, end):
            group = groups[index]
            now = "智能自动选路" if group.get("type") == "Smart" else (group.get("now") or "—")
            lines.append(f"{index + 1}. {group.get('name')}（{group.get('type')}，{group.get('count')} 项）→ {now}")
        lines.append("点组名展开节点；微信请用 /oc_node 组序号 节点序号")
        if not self._is_telegram(channel):
            return "\n".join(lines), None
        buttons = [
            [{"text": f"{index + 1}. {groups[index].get('name')}"[:60],
              "callback_data": f"[PLUGIN]{self.__class__.__name__}|oc:ng:{index}"}]
            for index in range(start, end)
        ]
        buttons = self._nav_buttons("gp", page, total_pages, buttons)
        buttons.append([{"text": "✖ 退出", "callback_data": f"[PLUGIN]{self.__class__.__name__}|oc:close"}])
        return "\n".join(lines), buttons

    def _group_nodes_page(self, group_index: int, page: int, channel: Any) -> Tuple[str, Optional[List[List[dict]]]]:
        if time.time() - self._cmd_ts > 300 or not (0 <= group_index < len(self._cmd_groups)):
            return "列表已过期，请重新发送 /oc_node", None
        group = self._cmd_groups[group_index]
        members = group.get("members") or []
        self._cmd_nodes = {str(group.get("name")): members}
        self._cmd_current_group = str(group.get("name"))
        self._cmd_current_group_index = group_index
        total_pages = max(1, (len(members) + self._NODES_PER_PAGE - 1) // self._NODES_PER_PAGE)
        page = max(0, min(int(page), total_pages - 1))
        self._cmd_node_page = page
        lines = [f"【{group.get('name')}】当前：{group.get('now') or '—'}（第 {page + 1}/{total_pages} 页）"]
        start = page * self._NODES_PER_PAGE
        end = min(len(members), start + self._NODES_PER_PAGE)
        for index in range(start, end):
            member = members[index]
            flags = []
            if member.get("is_group"):
                flags.append("组")
            if member.get("provider"):
                flags.append(str(member.get("provider")))
            suffix = f"（{'/'.join(flags)}）" if flags else ""
            mark = "✅ " if member.get("selected") else ""
            lines.append(f"{mark}{index + 1}. {member.get('name')}{suffix}")
        lines.append(f"微信切换：/oc_node {group.get('name')} 节点名")
        if not self._is_telegram(channel):
            return "\n".join(lines), None
        buttons = [
            [{"text": f"{'✅ ' if members[index].get('selected') else ''}{index + 1}. {members[index].get('name')[:40]}",
              "callback_data": f"[PLUGIN]{self.__class__.__name__}|oc:nn:{index}"}]
            for index in range(start, end)
        ]
        buttons = self._nav_buttons("np", page, total_pages, buttons)
        buttons.append([
            {"text": "↩ 返回组列表", "callback_data": f"[PLUGIN]{self.__class__.__name__}|oc:back"},
            {"text": "✖ 退出", "callback_data": f"[PLUGIN]{self.__class__.__name__}|oc:close"},
        ])
        return "\n".join(lines), buttons

    def _result_buttons(self) -> List[List[dict]]:
        return [[
            {"text": "↩ 返回组列表", "callback_data": f"[PLUGIN]{self.__class__.__name__}|oc:back"},
            {"text": "✖ 退出", "callback_data": f"[PLUGIN]{self.__class__.__name__}|oc:close"},
        ]]

    def _build_group_nodes_text(self, group_token: str) -> str:
        groups = self._cmd_groups
        if group_token.isdigit():
            index = int(group_token) - 1
        else:
            index = next((i for i, g in enumerate(groups) if str(g.get("name")) == group_token), -1)
        if time.time() - self._cmd_ts > 300 or not (0 <= index < len(groups)):
            return "组未找到或列表已过期，请先发送 /oc_node（或 /oc_status）刷新组列表"
        group = groups[index]
        members = group.get("members") or []
        lines = [f"【{group.get('name')}】当前：{group.get('now') or '—'}（{len(members)} 项）"]
        for i, member in enumerate(members):
            mark = "✅ " if member.get("selected") else ""
            lines.append(f"{mark}{i + 1}. {member.get('name')}")
        lines.append(f"切换：/oc_node {group.get('name')} 节点名（或 /oc_node {index + 1} 节点序号）")
        return "\n".join(lines)

    def _mode_menu(self, channel: Any) -> Tuple[str, Optional[List[List[dict]]]]:
        current = self._run_async(build_status(self._client())).get("mode") or "—"
        lines = [
            "【OpenClash 规则模式】",
            f"当前：{current}",
            "1. rule - 规则",
            "2. global - 全局",
            "3. direct - 直连",
            "用法：/oc_mode rule|global|direct",
        ]
        buttons = None
        if self._is_telegram(channel):
            buttons = [
                [{"text": "规则 rule", "callback_data": f"[PLUGIN]{self.__class__.__name__}|oc:m:rule"}],
                [{"text": "全局 global", "callback_data": f"[PLUGIN]{self.__class__.__name__}|oc:m:global"}],
                [{"text": "直连 direct", "callback_data": f"[PLUGIN]{self.__class__.__name__}|oc:m:direct"}],
            ]
        return "\n".join(lines), buttons

    async def _build_node_text(self, arg: str) -> str:
        parts = arg.split(None, 1)
        if len(parts) < 2:
            return "用法：/oc_node 组名 节点名（或 /oc_node 组序号 节点序号）"
        group_token, node_token = parts[0], parts[1].strip()
        client = self._client()
        proxies = await client.proxies()
        group = group_token
        if group_token.isdigit():
            index = int(group_token) - 1
            if time.time() - self._cmd_ts > 300 or not (0 <= index < len(self._cmd_groups)):
                return "组序号无效或列表已过期，请先发送 /oc_node 查看列表"
            group = str(self._cmd_groups[index].get("name"))
        group_type = (proxies.get(group) or {}).get("type")
        if group_type == "Smart":
            return f"「{group}」是智能组（Smart），由内核自动选路，不能手动指定节点。"
        if node_token.isdigit() and group_token.isdigit():
            members = [str(m.get("name")) for m in (self._cmd_groups[int(group_token) - 1].get("members") or [])]
            index = int(node_token) - 1
            if not (0 <= index < len(members)):
                return f"节点序号无效（{group} 共 {len(members)} 项）"
            node_token = members[index]
        await client.switch(group, node_token)
        logger.info(f"命令切换节点：{group} -> {node_token}")
        return f"已切换：{group} → {node_token}"

    async def _switch_by_index(self, node_index: int) -> str:
        group = self._cmd_current_group
        members = self._cmd_nodes.get(group) or []
        if not group or time.time() - self._cmd_ts > 300 or not (0 <= node_index < len(members)):
            return "列表已过期，请重新发送 /oc_node"
        name = str(members[node_index].get("name"))
        client = self._client()
        proxies = await client.proxies()
        if (proxies.get(group) or {}).get("type") == "Smart":
            return "智能组由内核自动选路，不能手动指定节点。"
        await client.switch(group, name)
        logger.info(f"按钮切换节点：{group} -> {name}")
        return f"已切换：{group} → {name}"

    async def _build_mode_text(self, arg: str) -> str:
        mode = arg.strip().lower()
        if mode not in _VALID_MODES:
            return "用法：/oc_mode rule|global|direct"
        await self._client().set_mode(mode)
        logger.info(f"命令切换规则模式：{mode}")
        return f"规则模式已切换为 {mode}"

    async def _build_refresh_text(self) -> str:
        client = self._client()
        providers = await build_providers(client)
        if not providers:
            return "没有可刷新的订阅源"
        names = []
        for provider in providers:
            await client.refresh_provider(str(provider.get("name")))
            names.append(str(provider.get("name")))
        logger.info(f"命令刷新订阅：{names}")
        return "已触发订阅更新：" + "、".join(names)

    # ------------------------------------------------------------------ 内部工具
    def _client(self) -> ClashClient:
        cfg = self._current_config()
        return ClashClient(
            api_url=str(cfg.get("api_url") or ""),
            secret=str(cfg.get("secret") or ""),
            timeout=float(cfg.get("timeout") or 8),
        )

    def _luci(self) -> Optional[LuCiClient]:
        """OpenWrt 管理客户端（仅在启用并填写密码时可用）。"""
        cfg = self._current_config()
        if not cfg.get("openwrt_enabled"):
            return None
        host = str(cfg.get("openwrt_host") or "").strip()
        password = str(cfg.get("openwrt_password") or "")
        if not host or not password:
            return None
        return LuCiClient(
            host=host,
            username=str(cfg.get("openwrt_username") or "root"),
            password=password,
            scheme=str(cfg.get("openwrt_scheme") or "http"),
            timeout=float(cfg.get("timeout") or 8),
        )

    @staticmethod
    def _ok(data: Any = None, message: str = "success") -> Dict[str, Any]:
        return {"success": True, "message": message, "data": data}

    @staticmethod
    def _err(message: str = "error", code: int = 500) -> Dict[str, Any]:
        return {"success": False, "message": message, "code": code}

    @staticmethod
    async def _json_body(request: Request) -> Dict[str, Any]:
        try:
            body = await request.json()
        except Exception:
            return {}
        return body if isinstance(body, dict) else {}

    # ------------------------------------------------------------------ 访问检查
    @staticmethod
    def _mp_proxy_url() -> Optional[str]:
        """读取 MoviePilot 自己配置的代理。"""
        try:
            from app.sdk.config import settings

            proxies = getattr(settings, "PROXY", None)
            if isinstance(proxies, dict):
                return proxies.get("https") or proxies.get("http")
            host = getattr(settings, "PROXY_HOST", None)
            if host and str(host).strip():
                return str(host).strip()
        except Exception:  # noqa: BLE001
            return None
        return None

    async def _clash_proxy_url(self) -> Optional[str]:
        cfg = self._current_config()
        api_url = normalize_api_url(str(cfg.get("api_url") or ""))
        if not api_url:
            return None
        parts = urlsplit(api_url)
        if not parts.hostname:
            return None
        try:
            configs = await self._client().configs()
        except Exception:  # noqa: BLE001
            return None
        port = configs.get("mixed-port") or configs.get("port")
        if not port:
            return None
        try:
            return f"http://{parts.hostname}:{int(port)}"
        except (TypeError, ValueError):
            return None

    async def _kernel_export(self) -> str:
        """内核视角的国外站点出口：默认代理组当前选中的节点/组。"""
        try:
            proxies = await self._client().proxies()
        except Exception:  # noqa: BLE001
            return "DIRECT"
        group = proxies.get("🚀 默认代理")
        if not group:
            group = next((value for key, value in proxies.items() if "默认代理" in key), None)
        if isinstance(group, dict) and group.get("now"):
            return str(group.get("now"))
        return "DIRECT"

    async def _kernel_probe(self, target: str, url: str, timeout: float) -> Dict[str, Any]:
        """用 Clash 内核测速（/proxies/{name}/delay 或 /group/{name}/delay）。"""
        try:
            proxies = await self._client().proxies()
        except Exception:  # noqa: BLE001
            proxies = {}
        target_type = (proxies.get(target) or {}).get("type")
        is_group = target_type in GROUP_TYPES
        result = await self._client().delay(
            target,
            url=url,
            timeout=int(max(timeout, 3) * 1000),
            is_group=is_group,
        )
        if result.get("delay") is None:
            await asyncio.sleep(0.4)
            result = await self._client().delay(
                target,
                url=url,
                timeout=int(max(timeout, 3) * 1000),
                is_group=is_group,
            )
        return result

    async def _run_kernel_netcheck(self, sites: List[Dict[str, str]], timeout: float) -> List[Dict[str, Any]]:
        export = await self._kernel_export()
        semaphore = asyncio.Semaphore(4)

        async def one(site: Dict[str, str]) -> Dict[str, Any]:
            async with semaphore:
                target = "DIRECT" if site.get("via") != "proxy" else export
                result = await self._kernel_probe(target, str(site.get("url") or ""), timeout)
                return {
                    **site,
                    "target": target,
                    "delay": result.get("delay"),
                    "error": result.get("error"),
                }

        return list(await asyncio.gather(*(one(site) for site in sites)))

    async def _run_netcheck_once(self, mode: str = "") -> Dict[str, Any]:
        cfg = self._current_config()
        mode = (mode or cfg.get("netcheck_mode") or "kernel").strip().lower()
        if mode not in ("kernel", "mp", "clash"):
            mode = "kernel"
        sites = parse_sites(cfg.get("netcheck_sites"))
        timeout = float(cfg.get("netcheck_timeout") or NETCHECK_TIMEOUT)
        progress: Dict[str, Any] = {
            "mode": mode,
            "proxy": "",
            "note": "",
            "results": [],
            "done": 0,
            "total": len(sites),
            "checking": True,
            "ts": time.time(),
        }
        self._net_progress[mode] = progress
        try:
            tasks: List[Any] = []
            if mode == "kernel":
                export = await self._kernel_export()
                progress["proxy"] = f"内核出口：{export}"
                progress["note"] = "经 OpenClash 内核测速（与官方访问检查一致）"

                async def one(site: Dict[str, str]) -> Dict[str, Any]:
                    target = "DIRECT" if site.get("via") != "proxy" else export
                    result = await self._kernel_probe(target, str(site.get("url") or ""), timeout)
                    return {**site, "target": target, "delay": result.get("delay"), "error": result.get("error")}

                tasks = [one(site) for site in sites]
            else:
                proxy_url: Optional[str] = None
                if mode == "mp":
                    proxy_url = self._mp_proxy_url()
                    if not proxy_url:
                        progress["note"] = "MP 未配置代理，国外站点将直连"
                else:
                    proxy_url = await self._clash_proxy_url()
                    if not proxy_url:
                        proxy_url = self._mp_proxy_url()
                        progress["note"] = (
                            "OpenClash 代理端口不可用，已回退 MP 代理"
                            if proxy_url
                            else "OpenClash 代理端口不可用，国外站点将直连"
                        )
                progress["proxy"] = mask_proxy(proxy_url)

                async def one(site: Dict[str, str]) -> Dict[str, Any]:
                    use_proxy = proxy_url if site.get("via") == "proxy" else None
                    result = await run_netcheck([site], use_proxy, timeout=timeout, concurrency=1)
                    return result[0] if result else {**site, "delay": None, "error": "no result"}

                tasks = [one(site) for site in sites]
            for coro in asyncio.as_completed(tasks):
                item = await coro
                progress["results"].append(item)
                progress["done"] = len(progress["results"])
        finally:
            self._net_progress.pop(mode, None)
        return {
            "mode": mode,
            "proxy": progress.get("proxy") or "",
            "note": progress.get("note") or "",
            "results": progress["results"],
        }

    # ------------------------------------------------------------------ API 注册
    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {"path": "/config", "endpoint": self.api_get_config, "methods": ["GET"], "auth": "bear", "summary": "读取插件配置"},
            {"path": "/config", "endpoint": self.api_save_config, "methods": ["POST"], "auth": "bear", "summary": "保存插件配置"},
            {"path": "/status", "endpoint": self.api_status, "methods": ["GET"], "auth": "bear", "summary": "OpenClash 运行状态"},
            {"path": "/groups", "endpoint": self.api_groups, "methods": ["GET"], "auth": "bear", "summary": "策略组与节点"},
            {"path": "/providers", "endpoint": self.api_providers, "methods": ["GET"], "auth": "bear", "summary": "订阅源列表"},
            {"path": "/switch", "endpoint": self.api_switch, "methods": ["POST"], "auth": "bear", "summary": "切换策略组节点"},
            {"path": "/mode", "endpoint": self.api_mode, "methods": ["POST"], "auth": "bear", "summary": "切换规则模式"},
            {"path": "/delay", "endpoint": self.api_delay, "methods": ["POST"], "auth": "bear", "summary": "批量/单项测速"},
            {"path": "/providers/refresh", "endpoint": self.api_refresh_provider, "methods": ["POST"], "auth": "bear", "summary": "刷新订阅节点"},
            {"path": "/logs", "endpoint": self.api_logs, "methods": ["GET"], "auth": "bear", "summary": "插件日志 / 内核日志"},
            {"path": "/netcheck", "endpoint": self.api_netcheck, "methods": ["GET"], "auth": "bear", "summary": "站点访问检查"},
            {"path": "/ocweb/status", "endpoint": self.api_ocweb_status, "methods": ["GET"], "auth": "bear", "summary": "OpenWrt 管理状态（运行模式/配置/快捷设置）"},
            {"path": "/ocweb/manage", "endpoint": self.api_ocweb_manage, "methods": ["POST"], "auth": "bear", "summary": "OpenWrt 管理操作（启停/重启/运行模式/切换配置/更新订阅/清缓存/快捷设置）"},
            {"path": "/ocweb/info", "endpoint": self.api_ocweb_info, "methods": ["GET"], "auth": "bear", "summary": "OpenClash 资源占用与订阅流量信息"},
        ]

    # ------------------------------------------------------------------ 配置接口
    def api_get_config(self) -> Dict[str, Any]:
        return self._ok(self._current_config())

    async def api_save_config(self, request: Request) -> Dict[str, Any]:
        body = await self._json_body(request)
        if not body:
            return self._err("无效的配置数据", 400)
        new_cfg = {**self._current_config(), **body}
        new_cfg["api_url"] = normalize_api_url(str(new_cfg.get("api_url") or ""))
        try:
            self.update_config(new_cfg)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"写回宿主配置失败：{exc}")
        self._config = new_cfg
        self._enabled = bool(new_cfg.get("enabled"))
        self._restart_log_worker()
        self._restart_net_worker()
        logger.info(f"配置已保存：enabled={self._enabled}，API={new_cfg.get('api_url') or '未配置'}")
        return self._ok(None, "配置已保存并生效")

    # ------------------------------------------------------------------ 业务接口
    async def api_status(self) -> Dict[str, Any]:
        try:
            data = await build_status(self._client())
            if self._api_ok is False:
                logger.info("OpenClash API 已恢复")
            self._api_ok = True
            return self._ok(data)
        except ClashApiError as exc:
            if self._api_ok is not False:
                logger.warning(f"OpenClash API 不可用：{exc.message}")
            self._api_ok = False
            return self._err(exc.message, exc.status or 500)
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"读取状态失败：{exc}")
            self._api_ok = False
            return self._err(f"读取状态失败：{exc}")

    async def api_groups(self) -> Dict[str, Any]:
        try:
            return self._ok({"groups": await build_groups(self._client())})
        except ClashApiError as exc:
            logger.warning(f"读取策略组失败：{exc.message}")
            return self._err(exc.message, exc.status or 500)
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"读取策略组失败：{exc}")
            return self._err(f"读取策略组失败：{exc}")

    async def api_providers(self) -> Dict[str, Any]:
        try:
            return self._ok({"providers": await build_providers(self._client())})
        except ClashApiError as exc:
            logger.warning(f"读取订阅源失败：{exc.message}")
            return self._err(exc.message, exc.status or 500)
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"读取订阅源失败：{exc}")
            return self._err(f"读取订阅源失败：{exc}")

    async def api_netcheck(self, mode: str = "", refresh: int = 0) -> Dict[str, Any]:
        """访问检查：优先返回后台采集的缓存；refresh=1 或缓存过期时触发后台立刻重测。"""
        try:
            cfg = self._current_config()
            mode = (mode or cfg.get("netcheck_mode") or "kernel").strip().lower()
            if mode not in ("kernel", "mp", "clash"):
                mode = "kernel"
            progress = self._net_progress.get(mode)
            if progress and progress.get("checking"):
                return self._ok({
                    "mode": mode,
                    "proxy": progress.get("proxy") or "",
                    "note": progress.get("note") or "",
                    "results": list(progress.get("results") or []),
                    "checking": True,
                    "done": progress.get("done"),
                    "total": progress.get("total"),
                })
            if refresh:
                self._net_target = mode
                self._net_event.set()
                return self._ok(
                    {"mode": mode, "proxy": "", "note": "", "results": [], "checking": True}
                )
            # 已触发但后台还没建进度时，继续返回 checking（轮询不会重复触发）
            if self._net_target == mode:
                return self._ok(
                    {"mode": mode, "proxy": "", "note": "", "results": [], "checking": True}
                )
            cached = self._cached_netcheck(mode)
            if cached:
                return self._ok(cached)
            return self._ok({"mode": mode, "proxy": "", "note": "", "results": [], "checking": True})
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"访问检查失败：{exc}")
            return self._err(f"访问检查失败：{exc}")

    # ------------------------------------------------------------------ OpenWrt 管理（LuCI）
    async def _ocweb(self, op: str, body: Dict[str, Any], client: LuCiClient) -> Dict[str, Any]:
        try:
            if op == "status":
                status = await client.get_json(f"{OC}/status")
                run_mode = await client.get_json(f"{OC}/get_run_mode")
                config = await client.get_json(f"{OC}/config_name")
                settings = await client.get_json(f"{OC}/oc_settings")
                files = await client.get_json(f"{OC}/config_file_list")
                config_name = (config or {}).get("config_path")
                if not config_name:
                    items = (config or {}).get("config_name")
                    if isinstance(items, str):
                        config_name = items
                    elif isinstance(items, list) and items:
                        first = items[0]
                        config_name = first.get("name") if isinstance(first, dict) else str(first)
                return self._ok(
                    {
                        "status": status or {},
                        "run_mode": (run_mode or {}).get("mode"),
                        "config_name": config_name,
                        "settings": settings or {},
                        "config_files": (files or {}).get("config_files") or [],
                    }
                )
            if op == "action":
                action = str(body.get("action") or "").strip().lower()
                if action not in ("start", "stop", "restart"):
                    return self._err("action 必须是 start/stop/restart", 400)
                await client.post(f"{OC}/action", {"action": action})
                logger.info(f"OpenWrt 操作：{action} OpenClash 服务")
                label = {"start": "启动", "stop": "停止", "restart": "重启"}[action]
                return self._ok({"action": action}, f"已{label} OpenClash")
            if op == "run_mode":
                run_mode = str(body.get("run_mode") or "")
                if run_mode not in ("", "-tun", "-mix"):
                    return self._err("run_mode 必须是空字符串 / -tun / -mix", 400)
                await client.post(f"{OC}/switch_run_mode", {"run_mode": run_mode})
                label = {"": "基础", "-tun": "增强(TUN)", "-mix": "混合"}[run_mode]
                logger.info(f"OpenWrt 操作：运行模式 {label}（会重启 OpenClash）")
                return self._ok({"run_mode": run_mode}, f"已切换运行模式为 {label}（正在重启 OpenClash）")
            if op == "switch_config":
                config_name = str(body.get("config_name") or "").strip()
                if not config_name:
                    return self._err("缺少 config_name", 400)
                await client.post(f"{OC}/switch_config", {"config_name": config_name})
                logger.info(f"OpenWrt 操作：切换配置 {config_name}")
                return self._ok({"config_name": config_name}, f"已切换配置 {config_name}（正在重启 OpenClash）")
            if op == "update_config":
                filename = str(body.get("filename") or "").strip()
                if not filename:
                    return self._err("缺少 filename（当前配置名）", 400)
                await client.post(f"{OC}/update_config", {"filename": filename})
                logger.info(f"OpenWrt 操作：更新订阅 {filename}")
                return self._ok({"filename": filename}, f"已触发订阅更新：{filename}")
            if op == "close_connections":
                await self._client().close_connections()
                logger.info("OpenWrt 操作：断开全部连接")
                return self._ok(None, "已断开全部代理连接")
            if op == "reload_firewall":
                await client.post(f"{OC}/reload_firewall")
                logger.info("OpenWrt 操作：重载防火墙")
                return self._ok(None, "已重载防火墙规则")
            if op == "flush":
                target = str(body.get("target") or "dns").strip().lower()
                if target not in ("dns", "smart"):
                    return self._err("target 必须是 dns 或 smart", 400)
                path = f"{OC}/flush_dns_cache" if target == "dns" else f"{OC}/flush_smart_cache"
                await client.post(path)
                logger.info(f"OpenWrt 操作：清理 {target} 缓存")
                return self._ok({"target": target}, f"已清理 {target} 缓存")
            if op == "setting":
                setting = str(body.get("setting") or "").strip()
                value = str(body.get("value") or "").strip()
                if setting not in ("meta_sniffer", "respect_rules", "oversea", "stream_unlock"):
                    return self._err("不支持的 setting（meta_sniffer/respect_rules/oversea/stream_unlock）", 400)
                await client.post(f"{OC}/switch_oc_setting", {"setting": setting, "value": value})
                logger.info(f"OpenWrt 操作：设置 {setting}={value}")
                return self._ok({"setting": setting, "value": value}, "设置已更新")
            return self._err(f"未知操作：{op}", 400)
        except LuCiError as exc:
            logger.warning(f"OpenWrt 管理失败：{op} {exc}")
            return self._err(str(exc), 502)

    async def api_ocweb_status(self) -> Dict[str, Any]:
        client = self._luci()
        if client is None:
            return self._err("未启用 OpenWrt 管理或未填写密码（请在插件设置里配置）", 400)
        try:
            return await self._ocweb("status", {}, client)
        finally:
            await client.close()

    async def api_ocweb_info(self) -> Dict[str, Any]:
        """资源占用（toolbar_show）与订阅流量/到期（sub_info_get）。"""
        client = self._luci()
        if client is None:
            return self._err("未启用 OpenWrt 管理或未填写密码（请在插件设置里配置）", 400)
        try:
            info: Dict[str, Any] = {"toolbar": {}, "subinfo": {}}
            try:
                first = await client.get_json(f"{OC}/toolbar_show")
                info["toolbar"] = first or {}
                # OpenClash 的 CPU 是后台瞬时采样，空闲时常为 0；再采一次取较大值
                try:
                    second = await client.get_json(f"{OC}/toolbar_show")
                    try:
                        a = int(str(first.get("cpu") or "0")) if isinstance(first, dict) else 0
                    except (TypeError, ValueError):
                        a = 0
                    try:
                        b = int(str(second.get("cpu") or "0")) if isinstance(second, dict) else 0
                    except (TypeError, ValueError):
                        b = 0
                    if isinstance(info["toolbar"], dict) and b > a:
                        info["toolbar"]["cpu"] = str(b)
                except LuCiError:
                    pass
            except LuCiError:
                info["toolbar"] = {}
            try:
                cfg = await client.get_json(f"{OC}/config_name")
                filename = str((cfg or {}).get("config_path") or "")
                if filename:
                    info["subinfo"] = await client.get_json(
                        f"{OC}/sub_info_get?filename={quote(filename)}"
                    )
            except LuCiError:
                info["subinfo"] = {}
            return self._ok(info)
        finally:
            await client.close()

    async def api_ocweb_manage(self, request: Request) -> Dict[str, Any]:
        body = await self._json_body(request)
        op = str(body.get("op") or "").strip()
        client = self._luci()
        if client is None:
            return self._err("未启用 OpenWrt 管理或未填写密码（请在插件设置里配置）", 400)
        try:
            return await self._ocweb(op, body, client)
        finally:
            await client.close()

    async def api_logs(self, lines: int = 200, level: str = "", source: str = "plugin") -> Dict[str, Any]:
        try:
            size = max(1, min(int(lines or 200), _LOG_BUFFER_SIZE))
        except (TypeError, ValueError):
            size = 200
        src = (source or "plugin").strip().lower()
        wanted = {part.strip().lower() for part in str(level or "").split(",") if part.strip()}

        if src == "kernel":
            items = list(self._log_buffer)
            if wanted:
                items = [item for item in items if item.get("level") in wanted]
            items = items[-size:]
            return self._ok(
                {
                    "logs": items,
                    "source": "kernel",
                    "exists": True,
                    "path": "",
                    "running": bool(self._log_thread and self._log_thread.is_alive()),
                    "level": self._current_config().get("log_level"),
                }
            )

        path = self._plugin_log_file()
        exists = bool(path and path.is_file())
        items: List[Dict[str, str]] = []
        if exists and path is not None:
            raw_lines = _tail_lines(path, max(size * 4, size))
            items = parse_plugin_log_lines(raw_lines)
        if wanted:
            items = [item for item in items if item.get("level") in wanted]
        items = items[-size:]
        return self._ok(
            {
                "logs": items,
                "source": "plugin",
                "exists": exists,
                "path": str(path) if path else "",
                "running": bool(self._log_thread and self._log_thread.is_alive()),
            }
        )

    async def api_switch(self, request: Request) -> Dict[str, Any]:
        body = await self._json_body(request)
        group = str(body.get("group") or "").strip()
        name = str(body.get("name") or "").strip()
        if not group or not name:
            return self._err("缺少 group 或 name 参数", 400)
        try:
            client = self._client()
            proxies = await client.proxies()
            group_type = (proxies.get(group) or {}).get("type")
            if group_type == "Smart":
                return self._err(
                    f"「{group}」是智能组（Smart），由内核自动选路，不能手动指定节点；"
                    "请选择上层策略组或普通节点组",
                    400,
                )
            await client.switch(group, name)
            logger.info(f"切换节点：{group} -> {name}")
            return self._ok({"group": group, "name": name}, f"已切换到 {name}")
        except ClashApiError as exc:
            logger.warning(f"切换节点失败：{group} -> {name}：{exc.message}")
            return self._err(exc.message, exc.status or 500)
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"切换节点失败：{exc}")
            return self._err(f"切换节点失败：{exc}")

    async def api_mode(self, request: Request) -> Dict[str, Any]:
        body = await self._json_body(request)
        mode = str(body.get("mode") or "").strip().lower()
        if mode not in _VALID_MODES:
            return self._err("mode 必须是 rule / global / direct 之一", 400)
        try:
            await self._client().set_mode(mode)
            logger.info(f"规则模式切换：{mode}")
            return self._ok({"mode": mode}, f"规则模式已切换为 {mode}")
        except ClashApiError as exc:
            logger.warning(f"规则模式切换失败：{mode}：{exc.message}")
            return self._err(exc.message, exc.status or 500)
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"切换规则模式失败：{exc}")
            return self._err(f"切换规则模式失败：{exc}")

    async def api_delay(self, request: Request) -> Dict[str, Any]:
        body = await self._json_body(request)
        names = body.get("names") or []
        if not isinstance(names, list) or not names:
            return self._err("缺少 names 参数（节点名数组）", 400)
        cfg = self._current_config()
        try:
            results = await test_delays(
                self._client(),
                [str(item) for item in names],
                url=str(body.get("url") or cfg.get("delay_test_url") or DEFAULT_DELAY_URL),
                timeout=int(body.get("timeout") or cfg.get("delay_test_timeout") or DEFAULT_DELAY_TIMEOUT),
                concurrency=int(cfg.get("max_delay_concurrency") or 8) if len(names) > 1 else 1,
            )
            ok = sum(1 for item in results.values() if item.get("delay") is not None)
            if len(names) > 1:
                logger.info(f"批量测速完成：{len(names)} 项，成功 {ok} 项")
            return self._ok({"results": results})
        except ClashApiError as exc:
            logger.warning(f"测速失败：{exc.message}")
            return self._err(exc.message, exc.status or 500)
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"测速失败：{exc}")
            return self._err(f"测速失败：{exc}")

    async def api_refresh_provider(self, request: Request) -> Dict[str, Any]:
        body = await self._json_body(request)
        name = str(body.get("name") or "").strip()
        if not name:
            return self._err("缺少 name 参数（订阅源名称）", 400)
        try:
            await self._client().refresh_provider(name)
            logger.info(f"刷新订阅：{name}")
            return self._ok({"name": name}, f"已触发 {name} 订阅更新，节点稍后刷新")
        except ClashApiError as exc:
            logger.warning(f"刷新订阅失败：{name}：{exc.message}")
            return self._err(exc.message, exc.status or 500)
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"刷新订阅失败：{exc}")
            return self._err(f"刷新订阅失败：{exc}")
