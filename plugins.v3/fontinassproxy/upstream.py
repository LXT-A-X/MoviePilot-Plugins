# -*- coding: utf-8 -*-
"""字幕字体代理 — Emby 回源层。

- 从请求头 ``X-Original-URI``（若客户端提供）或原始 URL 重建上游地址（保留全部 query 参数）。
- ``Accept-Encoding: identity``，避免拿到 gzip 再解压。
- 编码识别：BOM -> 声明/探测 -> UTF-8 兜底。
- 提供 ``to_full_uri``：把 ``/Subtitles/{index}/{StartPositionTicks}/Stream.*``
  中的 ticks 归零以取完整字幕（字形覆盖必须按完整字幕计算）。
"""

from __future__ import annotations

import re
import logging
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

logger = logging.getLogger("FontInAssProxy")

_TICKS_RE = re.compile(r"(/Subtitles/\d+/)\d+(/Stream[^?]*)", re.IGNORECASE)


def to_full_uri(original_uri: str) -> str:
    """把 StartPositionTicks 归零，请求完整字幕。"""
    return _TICKS_RE.sub(r"\g<1>0\g<2>", original_uri)


def rebuild_url(base_url: str, original_uri: str, api_key: Optional[str] = None) -> str:
    """base_url + original_uri；若显式配置 api_key 则覆盖 query 中的 api_key。"""
    if not original_uri.startswith("/"):
        original_uri = "/" + original_uri
    url = base_url.rstrip("/") + original_uri
    if not api_key:
        return url
    parts = urlsplit(url)
    qs = dict(parse_qsl(parts.query, keep_blank_values=True))
    qs["api_key"] = api_key
    qs["X-Emby-Token"] = api_key
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(qs), parts.fragment))


def rewrite_location(location: str) -> str:
    """把重定向 Location 里的绝对 URL 转成相对路径，让浏览器在当前反代下继续。

    场景：客户端经内置反代（8097）访问 Emby 根路径，Emby 302 指向自己的绝对地址
    （http://192.168.2.15:8096/web/index.html）。若原样透传，浏览器会跳出反代直连
    8096，产生混合域黑屏。转成相对 /web/index.html 后一切资源都走当前反代。
    """
    if not location:
        return location
    if location.startswith("http://") or location.startswith("https://"):
        parts = urlsplit(location)
        new = parts.path
        if parts.query:
            new += "?" + parts.query
        return new
    return location


def try_decode(raw: bytes) -> Optional[str]:
    """按 BOM -> 探测 -> UTF-8/GBK 兜底识别字幕文本。失败返回 None。"""
    if raw.startswith(b"\xff\xfe\x00\x00") or raw.startswith(b"\x00\x00\xfe\xff"):
        try:
            return raw.decode("utf-32")
        except UnicodeDecodeError:
            pass
    if raw.startswith(b"\xef\xbb\xbf"):
        try:
            return raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            pass
    if raw.startswith(b"\xff\xfe"):
        try:
            return raw.decode("utf-16")
        except UnicodeDecodeError:
            pass
    if raw.startswith(b"\xfe\xff"):
        try:
            return raw.decode("utf-16-be")
        except UnicodeDecodeError:
            pass
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    # 最后探测
    try:
        from charset_normalizer import from_bytes
        best = from_bytes(raw).best()
        if best and best.encoding:
            return str(best)
    except Exception:
        pass
    return None


class UpstreamClient:
    """Emby/Jellyfin 回源客户端。"""

    def __init__(self, base_url: str, api_key: Optional[str] = None,
                 timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout,
            headers={"Accept-Encoding": "identity", "User-Agent": "FontInAssProxy/1.0"},
        )

    async def fetch(self, original_uri: str,
                    client_headers: Optional[Dict[str, str]] = None,
                    follow: bool = True, method: str = "GET",
                    content: Optional[bytes] = None) -> Tuple[int, bytes, Dict[str, str]]:
        """回源请求，返回 (status, body, 响应头子集)。

        - follow=True：跟随重定向取最终内容（字幕处理链路用）。
        - follow=False：保留重定向原始响应（透传链路用，配合 rewrite_location
          让浏览器在反代域内继续，避免 Emby 绝对地址跳出反代）。
        - method/content：透传链路原样转发方法（如 POST 登录）与请求体。
        """
        url = rebuild_url(self.base_url, original_uri, self.api_key)
        headers = self._filter_headers(client_headers)
        try:
            resp = await self._client.request(
                method, url, headers=headers, content=content,
                follow_redirects=follow)
        except httpx.HTTPError as exc:
            logger.warning(f"回源失败 {url}: {exc}")
            return 502, b"", {}
        resp_headers = {k: v for k, v in resp.headers.items()
                        if k.lower() in ("content-type", "content-disposition",
                                         "cache-control", "location", "set-cookie")}
        return resp.status_code, resp.content, resp_headers

    @staticmethod
    def _filter_headers(client_headers: Optional[Dict[str, str]]) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if client_headers:
            for k, v in client_headers.items():
                name = k.lower()
                if name in ("host", "accept-encoding", "content-length", "connection"):
                    continue
                headers[k] = v
        return headers

    async def open_stream(self, original_uri: str,
                          client_headers: Optional[Dict[str, str]] = None,
                          method: str = "GET") -> httpx.Response:
        """流式打开上游响应（视频等大流量透传：边收边发，不在内存缓冲全文）。

        返回 httpx.Response（stream=True），调用方负责 aiter_bytes 与 aclose。
        """
        url = rebuild_url(self.base_url, original_uri, self.api_key)
        headers = self._filter_headers(client_headers)
        req = self._client.build_request(method, url, headers=headers)
        return await self._client.send(req, stream=True, follow_redirects=False)

    async def aclose(self):
        try:
            await self._client.aclose()
        except Exception:
            pass