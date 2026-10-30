# -*- coding: utf-8 -*-
"""访问检查：站点连通性与延迟（直连 / MP 代理 / OpenClash 代理）。

设计：
- 站点配置支持 list[dict] 或多行文本（名称|URL|direct/proxy）；
- via=direct 的站点永远直连；
- via=proxy 的站点按调用方传入的代理 URL 走（MP 代理或 OpenClash mixed 端口）；
- 不依赖 MoviePilot 宿主，方便单测。
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

import httpx

DEFAULT_SITES: List[Dict[str, str]] = [
    {"name": "百度搜索", "url": "https://www.baidu.com/", "via": "direct"},
    {"name": "网易云音乐", "url": "https://music.163.com/", "via": "direct"},
    {"name": "GitHub", "url": "https://github.com/", "via": "proxy"},
    {"name": "YouTube", "url": "https://www.youtube.com/", "via": "proxy"},
]

DEFAULT_TIMEOUT = 6.0


def parse_sites(raw: Any) -> List[Dict[str, str]]:
    """把配置里的站点定义解析成 [{name,url,via}]（兼容 list 与多行文本）。"""
    items: List[Any]
    if isinstance(raw, list) and raw:
        items = raw
    elif isinstance(raw, str) and raw.strip():
        items = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [part.strip() for part in line.split("|")]
            if len(parts) < 2:
                continue
            via = parts[2].lower() if len(parts) > 2 else "direct"
            items.append({"name": parts[0], "url": parts[1], "via": via})
        if not items:
            items = list(DEFAULT_SITES)
    else:
        items = list(DEFAULT_SITES)

    result: List[Dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        url = str(item.get("url") or "").strip()
        if not name or not url:
            continue
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        via = "proxy" if str(item.get("via") or "").lower() == "proxy" else "direct"
        result.append({"name": name, "url": url, "via": via})
    return result or [dict(site) for site in DEFAULT_SITES]


async def _probe(url: str, proxy_url: Optional[str], timeout: float) -> Dict[str, Any]:
    """请求一个 URL，返回 {delay: ms|None, error: str|None}。"""
    started = time.perf_counter()
    try:
        kwargs: Dict[str, Any] = {
            "timeout": timeout,
            "follow_redirects": True,
            "trust_env": False,
        }
        if proxy_url:
            kwargs["proxy"] = proxy_url
        async with httpx.AsyncClient(**kwargs) as client:
            await client.get(url)
        return {"delay": int((time.perf_counter() - started) * 1000), "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"delay": None, "error": str(exc)[:160]}


async def run_netcheck(
    sites: List[Dict[str, str]],
    proxy_url: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
    concurrency: int = 4,
) -> List[Dict[str, Any]]:
    """并发检查站点，返回 [{name,url,via,delay,error}]。"""
    semaphore = asyncio.Semaphore(max(1, int(concurrency or 4)))

    async def one(site: Dict[str, str]) -> Dict[str, Any]:
        async with semaphore:
            use_proxy = proxy_url if site.get("via") == "proxy" else None
            result = await _probe(str(site.get("url") or ""), use_proxy, float(timeout or DEFAULT_TIMEOUT))
            return {**site, **result}

    return list(await asyncio.gather(*(one(site) for site in (sites or []))))


def mask_proxy(proxy_url: Optional[str]) -> str:
    """展示用：隐藏代理 URL 里的账号密码。"""
    if not proxy_url:
        return ""
    text = str(proxy_url)
    if "@" in text and "://" in text:
        head, tail = text.split("://", 1)
        if "@" in tail:
            _, host = tail.rsplit("@", 1)
            return f"{head}://***@{host}"
    return text
