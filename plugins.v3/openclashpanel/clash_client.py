# -*- coding: utf-8 -*-
"""OpenClash / Mihomo external-controller 客户端与数据整形。

设计约束：
- 不依赖 MoviePilot 宿主，方便单独做只读冒烟测试；
- 只用 httpx（宿主已自带），不新增第三方依赖；
- trust_env=False：避免 MP 容器里的代理环境变量把局域网请求带走；
- 所有节点/组名一律 URL 编码（组名里有 emoji、空格、竖线）。
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

DEFAULT_DELAY_URL = "https://www.gstatic.com/generate_204"
DEFAULT_DELAY_TIMEOUT = 5000

GROUP_TYPES = {"Selector", "URLTest", "Fallback", "LoadBalance", "Relay", "Smart"}

_PRIORITY_KEYWORDS = ("默认代理", "全部节点")

_REGION_KEYWORDS = (
    "香港", "日本", "美国", "狮城", "新加坡", "台湾", "韩国", "英国", "德国",
    "法国", "俄罗斯", "印度", "澳大利亚", "加拿大", "荷兰", "土耳其", "阿根廷",
)


class ClashApiError(Exception):
    """OpenClash API 调用失败（带可展示的中文消息）。"""

    def __init__(self, message: str, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def _quote(text: Any) -> str:
    return quote(str(text), safe="")


class ClashClient:
    """极简的 Clash/Mihomo external-controller 客户端。"""

    def __init__(self, api_url: str, secret: str, timeout: float = 8.0) -> None:
        self.api_url = (api_url or "").strip().rstrip("/")
        self.secret = (secret or "").strip()
        self.timeout = max(1.0, float(timeout or 8.0))

    # ------------------------------------------------------------------ 基础请求
    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.secret:
            headers["Authorization"] = "Bearer " + self.secret
        return headers

    def _validate(self) -> None:
        if not self.api_url:
            raise ClashApiError("请先在插件设置里填写 OpenClash API 地址（如 http://你的路由器IP:9090）")
        if not self.secret:
            raise ClashApiError("请先在插件设置里填写 OpenClash Dashboard 密码")

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        """发一个请求并返回 JSON（空响应返回 None）。"""
        self._validate()
        try:
            async with httpx.AsyncClient(
                base_url=self.api_url,
                headers=self._headers(),
                timeout=self.timeout,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                response = await client.request(method, path, **kwargs)
        except httpx.ConnectError as exc:
            raise ClashApiError(f"无法连接 OpenClash API：{self.api_url}") from exc
        except httpx.TimeoutException as exc:
            raise ClashApiError(f"OpenClash API 请求超时（>{self.timeout:g}s）") from exc
        except httpx.HTTPError as exc:
            raise ClashApiError(f"OpenClash API 请求失败：{exc}") from exc

        if response.status_code == 401:
            raise ClashApiError("Dashboard 密码错误（401），请检查插件设置里的密码", 401)
        if response.status_code == 404:
            raise ClashApiError("OpenClash API 找不到该对象（404）", 404)
        if response.status_code >= 400:
            detail = (response.text or "")[:200]
            raise ClashApiError(f"OpenClash API 返回 {response.status_code}：{detail}", response.status_code)
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    # ------------------------------------------------------------------ 具体能力
    async def version(self) -> Dict[str, Any]:
        return await self.request("GET", "/version") or {}

    async def configs(self) -> Dict[str, Any]:
        return await self.request("GET", "/configs") or {}

    async def proxies(self) -> Dict[str, Any]:
        payload = await self.request("GET", "/proxies") or {}
        return payload.get("proxies") or {}

    async def providers(self) -> Dict[str, Any]:
        payload = await self.request("GET", "/providers/proxies") or {}
        return payload.get("providers") or {}

    async def connections(self) -> Dict[str, Any]:
        return await self.request("GET", "/connections") or {}

    async def switch(self, group: str, name: str) -> None:
        """切换策略组节点：PUT /proxies/{group} {"name": ...}。"""
        await self.request("PUT", f"/proxies/{_quote(group)}", json={"name": name})

    async def set_mode(self, mode: str) -> None:
        """切换规则模式（只改运行时；OpenClash 重启后会回到配置文件里的 mode）。"""
        await self.request("PATCH", "/configs", json={"mode": mode})

    async def refresh_provider(self, name: str) -> None:
        """刷新订阅 provider（重新拉取订阅并更新节点）。"""
        await self.request("PUT", f"/providers/proxies/{_quote(name)}")

    async def close_connections(self) -> None:
        """断开所有代理连接（DELETE /connections）。"""
        await self.request("DELETE", "/connections")

    async def delay(
        self,
        name: str,
        provider: Optional[str] = None,
        url: str = DEFAULT_DELAY_URL,
        timeout: int = DEFAULT_DELAY_TIMEOUT,
        is_group: bool = False,
    ) -> Dict[str, Any]:
        """单节点 / 单组测延迟。

        - 策略组：GET /group/{name}/delay
        - 订阅节点：GET /providers/proxies/{provider}/{name}/healthcheck
        - 配置内节点：GET /proxies/{name}/delay
        """
        if is_group:
            path = f"/group/{_quote(name)}/delay"
        elif provider:
            path = f"/providers/proxies/{_quote(provider)}/{_quote(name)}/healthcheck"
        else:
            path = f"/proxies/{_quote(name)}/delay"
        try:
            payload = await self.request("GET", path, params={"url": url, "timeout": int(timeout)})
        except ClashApiError as exc:
            return {"name": name, "delay": None, "error": exc.message}
        if not isinstance(payload, dict):
            return {"name": name, "delay": None}
        if "delay" in payload:
            return {"name": name, "delay": payload.get("delay")}
        # /group/{name}/delay 返回的是 {节点名: 延迟} 映射（Smart/Selector 组都是这种）
        children = {
            str(key): value
            for key, value in payload.items()
            if isinstance(value, (int, float))
        }
        values = [value for value in children.values() if isinstance(value, (int, float)) and value > 0]
        return {
            "name": name,
            "delay": min(values) if values else None,
            "children": children,
        }


# ---------------------------------------------------------------------- 数据整形

def _provider_node_index(providers: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for provider_name, provider in (providers or {}).items():
        # 配置内联的 Compatible 伪 provider 里装的是配置里的代理/策略组，不是订阅节点
        if (provider.get("vehicleType") or "Compatible") == "Compatible":
            continue
        for node in provider.get("proxies") or []:
            node_name = node.get("name")
            if node_name:
                index[node_name] = {"type": node.get("type"), "provider": provider_name}
    return index


def _node_entry(name: str, proxies: Dict[str, Any], node_index: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    direct = proxies.get(name) or {}
    meta = node_index.get(name) or {}
    node_type = direct.get("type") or meta.get("type")
    return {
        "name": name,
        "type": node_type,
        "is_group": node_type in GROUP_TYPES,
        "provider": meta.get("provider"),
    }


def _group_sort_key(group: Dict[str, Any]):
    name = str(group.get("name") or "")
    if name == "GLOBAL":
        return (9, 0, name)
    for i, keyword in enumerate(_PRIORITY_KEYWORDS):
        if keyword in name:
            return (0, i, name)
    for i, keyword in enumerate(_REGION_KEYWORDS):
        if keyword in name:
            return (1, i, name)
    return (2, 0, name)


async def build_status(client: ClashClient) -> Dict[str, Any]:
    version, configs, connections = await asyncio.gather(
        client.version(), client.configs(), client.connections()
    )
    active = len(connections.get("connections") or [])
    return {
        "version": version.get("version"),
        "meta": bool(version.get("meta")),
        "mode": configs.get("mode"),
        "ports": {
            "http": configs.get("port"),
            "socks": configs.get("socks-port"),
            "redir": configs.get("redir-port"),
            "tproxy": configs.get("tproxy-port"),
            "mixed": configs.get("mixed-port"),
            "tun": bool((configs.get("tun") or {}).get("enable")),
        },
        "allow_lan": bool(configs.get("allow-lan")),
        "active_connections": active,
        "download_total": connections.get("downloadTotal"),
        "upload_total": connections.get("uploadTotal"),
    }


async def build_groups(client: ClashClient) -> List[Dict[str, Any]]:
    proxies, providers = await asyncio.gather(client.proxies(), client.providers())
    node_index = _provider_node_index(providers)
    groups: List[Dict[str, Any]] = []
    for group_name, group in (proxies or {}).items():
        group_type = group.get("type")
        if group_type not in GROUP_TYPES:
            continue
        now = group.get("now")
        members = []
        for member_name in group.get("all") or []:
            entry = _node_entry(member_name, proxies, node_index)
            entry["selected"] = member_name == now
            members.append(entry)
        groups.append(
            {
                "name": group_name,
                "type": group_type,
                "now": now,
                "count": len(members),
                "members": members,
            }
        )
    # 策略组顺序：Clash 的 GLOBAL.all 保留了 proxy-groups 的配置顺序，
    # 优先按它排序（与 OpenClash 配置文件 / zashboard 显示一致）；拿不到时回退语义排序。
    global_all = (proxies.get("GLOBAL") or {}).get("all") or []
    if global_all:
        position = {name: index for index, name in enumerate(global_all)}
        groups.sort(key=lambda item: (position.get(item["name"], len(position)), _group_sort_key(item)))
    else:
        groups.sort(key=_group_sort_key)
    return groups


async def build_providers(client: ClashClient) -> List[Dict[str, Any]]:
    providers = await client.providers()
    result: List[Dict[str, Any]] = []
    for provider_name, provider in (providers or {}).items():
        vehicle = provider.get("vehicleType") or ""
        # 跳过配置内联的 Compatible 伪 provider，只保留真正的订阅源
        if vehicle == "Compatible":
            continue
        result.append(
            {
                "name": provider_name,
                "vehicle": vehicle,
                "type": provider.get("type"),
                "updated_at": provider.get("updatedAt"),
                "node_count": len(provider.get("proxies") or []),
            }
        )
    return result


async def test_delays(
    client: ClashClient,
    names: List[str],
    url: str = DEFAULT_DELAY_URL,
    timeout: int = DEFAULT_DELAY_TIMEOUT,
    concurrency: int = 8,
) -> Dict[str, Dict[str, Any]]:
    """并发测试一组节点/组的延迟，返回 {name: {delay, error, skipped}}。"""
    providers, proxies = await asyncio.gather(client.providers(), client.proxies())
    node_index = _provider_node_index(providers)
    semaphore = asyncio.Semaphore(max(1, int(concurrency or 8)))
    skip_types = {"Reject", "RejectDrop", "Pass", "Block", "Compatible"}

    async def run(node_name: str) -> Dict[str, Any]:
        direct = proxies.get(node_name) or {}
        meta = node_index.get(node_name) or {}
        node_type = direct.get("type") or meta.get("type")
        if node_type in skip_types:
            return {"name": node_name, "delay": None, "skipped": True}
        async with semaphore:
            result = await client.delay(
                node_name,
                meta.get("provider"),
                url=url,
                timeout=timeout,
                is_group=node_type in GROUP_TYPES,
            )
            result["skipped"] = False
            return result

    results = await asyncio.gather(*(run(name) for name in (names or [])[:300]))
    return {
        item["name"]: {
            "delay": item.get("delay"),
            "error": item.get("error"),
            "skipped": bool(item.get("skipped")),
            "children": item.get("children") or {},
        }
        for item in results
    }
