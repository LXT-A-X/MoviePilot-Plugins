# -*- coding: utf-8 -*-
"""字幕字体代理 — Emby 回源层。

- 从内置反代收到的原始相对路径重建上游地址（保留全部 query 参数）。
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


def _printable_ratio(data: bytes) -> float:
    """可打印字节（含常见控制符）占比，用于过滤 gb18030 误解码的乱码内容。"""
    if not data:
        return 0.0
    n = ok = 0
    for b in data:
        n += 1
        if b in (9, 10, 13) or 0x20 <= b <= 0x7E:
            ok += 1
    return ok / n


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
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    # 轻微-2：gb18030 几乎能解任意字节序列，损坏/二进制内容也会"成功"解出乱码，
    # 先做可打印率校验，不达标再走 charset_normalizer。
    if _printable_ratio(raw) >= 0.9:
        try:
            return raw.decode("gb18030")
        except UnicodeDecodeError:
            pass
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
        # 严重-2：视频/音频长连接（暂停播放时客户端停止拉取）沿用 30s 读超时会被掐断。
        # 流式透传单独放宽读超时（read=None），连接/写入/池超时仍保留 10s 兜底。
        req = self._client.build_request(
            method, url, headers=headers,
            timeout=httpx.Timeout(10.0, read=None),
        )
        return await self._client.send(req, stream=True, follow_redirects=False)

    async def open_ws(self, original_uri: str,
                        client_headers: Optional[Dict[str, str]] = None):
        """打开上游 WebSocket 连接（Emby Web 会话同步/遥控透传，中等-7）。

        需要 websockets 库；宿主缺失时抛 ImportError，由调用方优雅降级。
        """
        import websockets
        url = rebuild_url(self.base_url, original_uri, self.api_key)
        url = url.replace("http://", "ws://", 1).replace("https://", "wss://", 1)
        headers = self._filter_headers(client_headers)
        for hop in ("connection", "upgrade", "sec-websocket-key",
                    "sec-websocket-version", "sec-websocket-extensions",
                    "sec-websocket-protocol", "accept-encoding"):
            headers.pop(hop, None)
        return await websockets.connect(url, extra_headers=headers,
                                        ping_interval=None)

    async def aclose(self):
        try:
            await self._client.aclose()
        except Exception:
            pass