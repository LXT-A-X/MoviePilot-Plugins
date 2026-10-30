# -*- coding: utf-8 -*-
"""OpenClash / OpenWrt LuCI HTTP 客户端。

- 通过 LuCI 登录（POST /cgi-bin/luci，username/password）拿 sysauth cookie；
- 登录后调用 OpenClash 的 LuCI 接口（/cgi-bin/luci/admin/services/openclash/...）；
- 仅在插件设置里启用「OpenWrt 管理」并填写密码后使用；
- 密码只用于登录，不写日志。
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional
from urllib.parse import urlsplit

import httpx


class LuCiError(RuntimeError):
    """LuCI 调用失败（登录失败 / session 过期 / 接口报错）。"""


class LuCiClient:
    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        scheme: str = "http",
        timeout: float = 12.0,
    ) -> None:
        text = (host or "").strip()
        if "://" in text:
            parsed = urlsplit(text)
            scheme = parsed.scheme or scheme
            host = parsed.netloc or parsed.path
        self.scheme = (scheme or "http").strip().lower() or "http"
        self.host = (host or "").strip().strip("/")
        self.username = (username or "").strip()
        self.password = password or ""
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._stok: Optional[str] = None

    @property
    def base_url(self) -> str:
        return f"{self.scheme}://{self.host}"

    def _url(self, path: str) -> str:
        if self._stok and path.startswith("/cgi-bin/luci/"):
            suffix = path[len("/cgi-bin/luci"):]
            return f"{self.base_url}/cgi-bin/luci/;stok={self._stok}{suffix}"
        return self.base_url + path

    async def _ensure(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                trust_env=False,
                follow_redirects=False,
            )
            await self._login()
        return self._client

    async def _login(self) -> None:
        assert self._client is not None
        try:
            resp = await self._client.post(
                f"{self.base_url}/cgi-bin/luci",
                data={"luci_username": self.username, "luci_password": self.password},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            # 兼容部分固件使用 username/password 字段
            if resp.status_code not in (200, 302) or "sysauth" not in ";".join(resp.headers.get_list("set-cookie")).lower():
                retry = await self._client.post(
                    f"{self.base_url}/cgi-bin/luci",
                    data={"username": self.username, "password": self.password},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                if retry.status_code in (200, 302) or "sysauth" in ";".join(retry.headers.get_list("set-cookie")).lower():
                    resp = retry
        except Exception as exc:  # noqa: BLE001
            raise LuCiError(f"无法连接 OpenWrt：{exc}") from exc
        cookie_text = ";".join(resp.headers.get_list("set-cookie")).lower()
        if resp.status_code not in (200, 302) or "sysauth" not in cookie_text:
            raise LuCiError("OpenWrt 登录失败（用户名或密码错误）")
        location = resp.headers.get("location") or ""
        match = re.search(r";stok=([^/;]+)", location)
        self._stok = match.group(1) if match else None
        # 某些版本 stok 在 200 页面里
        if not self._stok:
            found = re.search(r";stok=([A-Za-z0-9]+)", resp.text or "")
            self._stok = found.group(1) if found else None

    async def _request(self, method: str, path: str, data: Optional[Dict[str, Any]] = None) -> httpx.Response:
        client = await self._ensure()
        last_exc: Optional[Exception] = None
        for attempt in (1, 2):
            try:
                if method == "GET":
                    resp = await client.get(self._url(path))
                else:
                    resp = await client.post(self._url(path), data=data or {})
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt == 1:
                    await self._login()
                    continue
                raise LuCiError(f"请求 OpenWrt 失败：{exc}") from exc
            if resp.status_code in (401, 403):
                if attempt == 1:
                    await self._login()
                    continue
                raise LuCiError("OpenWrt 鉴权失败（session 已过期，请检查密码）")
            if resp.status_code >= 400:
                raise LuCiError(f"OpenClash 接口返回 {resp.status_code}：{resp.text[:120]}")
            return resp
        raise LuCiError(f"请求 OpenWrt 失败：{last_exc}")

    async def get(self, path: str) -> httpx.Response:
        return await self._request("GET", path)

    async def post(self, path: str, data: Optional[Dict[str, Any]] = None) -> httpx.Response:
        return await self._request("POST", path, data)

    async def get_json(self, path: str) -> Any:
        resp = await self.get(path)
        try:
            return resp.json()
        except ValueError as exc:  # noqa: BLE001
            raise LuCiError(f"接口返回非 JSON：{resp.text[:120]}") from exc

    async def post_json(self, path: str, data: Optional[Dict[str, Any]] = None) -> Any:
        resp = await self.post(path, data)
        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError:
            return {"raw": resp.text[:200]}

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:  # noqa: BLE001
                pass
            self._client = None


OC = "/cgi-bin/luci/admin/services/openclash"
