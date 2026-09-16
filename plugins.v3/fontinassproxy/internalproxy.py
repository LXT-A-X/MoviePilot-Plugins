# -*- coding: utf-8 -*-
"""字幕字体代理 — 内置反代服务（可选，替代外部 nginx）。

在不依赖 nginx 的场景下，由插件在独立端口上直接反向代理 Emby：
- 字幕路径（/Videos/.../Subtitles/.../Stream.*）交给插件处理链路；
- 其余请求全部透传 Emby。

形态参考 mediawarp（插件内起独立端口 + 后台线程启动），但为纯 Python 实现，
复用 MoviePilot 自带的 uvicorn/starlette，无需外部二进制。
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Awaitable, Callable, Dict, Tuple

from starlette.responses import Response
from fastapi import FastAPI, Request

logger = logging.getLogger("FontInAssProxy")

# handler(original_uri, headers, method, body) -> (status, body, resp_headers)
ProxyHandler = Callable[[str, Dict[str, str], str, bytes],
                        Awaitable[Tuple[int, bytes, Dict[str, str]]]]

# subtitle_check(original_uri) -> bool：判断字幕路径
SubtitleCheck = Callable[[str], bool]
# stream_check(original_uri, method) -> bool：判断是否流式透传（视频/音频大头）
StreamCheck = Callable[[str, str], bool]


class InternalProxy:
    """独立端口反向代理服务。启动/停止与插件生命周期绑定。

    分发规则：
    - 字幕路径 -> handler（插件处理链路，缓冲返回）；
    - 视频/音频流路径 -> 流式透传 Emby（边收边发，不阻塞起播）；
    - 其余（Web/登录/API）-> 缓冲处理链路（原样转发方法+请求体）。
    """

    def __init__(self, port: int, handler: ProxyHandler,
                 subtitle_check: Optional[SubtitleCheck] = None,
                 stream_check: Optional[StreamCheck] = None,
                 streamer: Optional[Any] = None):
        self.port = int(port)
        self._handler = handler
        self._subtitle_check = subtitle_check
        self._stream_check = stream_check
        self._streamer = streamer
        self._server = None
        self._thread: threading.Thread | None = None
        self._app = self._build_app()

    def _build_app(self) -> FastAPI:
        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

        @app.api_route("/{path:path}",
                       methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "DELETE", "PATCH"])
        async def _gateway(request: Request, path: str):
            query = request.url.query
            original_uri = request.url.path + (f"?{query}" if query else "")
            headers = {k: v for k, v in request.headers.items()}
            method = request.method

            # 字幕路径：走插件处理链路
            if self._subtitle_check and self._subtitle_check(original_uri):
                body = await request.body()
                try:
                    status, resp_body, resp_headers = await self._handler(
                        original_uri, headers, method, body)
                except Exception as e:
                    logger.exception(f"内置反代处理异常: {e}")
                    return Response(content=b"", status_code=500,
                                    media_type="text/plain")
                return Response(content=resp_body, status_code=status, headers=resp_headers)

            # 视频/音频流：流式透传，边收边发
            if self._stream_check and self._stream_check(original_uri, method) \
                    and self._streamer:
                return await self._stream_passthrough(original_uri, headers, method)

            # 其余（Web/登录/API）：缓冲处理链路（POST 登录等必须原样转发方法+请求体）
            body = await request.body()
            try:
                status, resp_body, resp_headers = await self._handler(
                    original_uri, headers, method, body)
            except Exception as e:
                logger.exception(f"内置反代处理异常: {e}")
                return Response(content=b"", status_code=500,
                                media_type="text/plain")
            return Response(content=resp_body, status_code=status, headers=resp_headers)

        return app

    async def _stream_passthrough(self, original_uri: str,
                                  headers: Dict[str, str],
                                  method: str):
        """流式转发上游（视频 Range 大头不缓冲）。"""
        import httpx
        from starlette.responses import StreamingResponse
        try:
            upstream_resp = await self._streamer.open_stream(original_uri, headers, method)
        except Exception as e:
            logger.exception(f"流式回源失败 {original_uri}: {e}")
            return Response(content=b"", status_code=502, media_type="text/plain")
        # 透传响应头（保留 Range/长度等信息，供播放器断点续播）
        resp_headers: Dict[str, str] = {}
        for k, v in upstream_resp.headers.items():
            lk = k.lower()
            if lk in ("content-encoding", "transfer-encoding", "connection",
                      "content-length"):
                continue
            resp_headers[k] = v
        status = upstream_resp.status_code
        if status >= 400:
            data = b""
            try:
                data = await upstream_resp.aread()
            except Exception:
                pass
            try:
                await upstream_resp.aclose()
            except Exception:
                pass
            return Response(content=data, status_code=status, headers=resp_headers)

        async def gen():
            try:
                async for chunk in upstream_resp.aiter_bytes():
                    yield chunk
            except Exception as e:
                logger.warning(f"流式转发中断: {e}")
            finally:
                try:
                    await upstream_resp.aclose()
                except Exception:
                    pass

        return StreamingResponse(gen(), status_code=status, headers=resp_headers)

    def start(self) -> bool:
        """后台线程启动 uvicorn（在独立线程内跑自己的事件循环，与 MP 主循环隔离）。"""
        if self._thread and self._thread.is_alive():
            return True
        try:
            import uvicorn
        except Exception as e:
            logger.error(f"内置反代无法启动（uvicorn 不可用）: {e}")
            return False
        config = uvicorn.Config(
            self._app,
            host="0.0.0.0",
            port=self.port,
            log_level="warning",
            access_log=False,
            lifespan="off",
        )
        server = uvicorn.Server(config)
        self._server = server
        self._thread = threading.Thread(target=server.run, daemon=True,
                                        name="FontInAssProxy-internal-proxy")
        self._thread.start()
        # 等待端口就绪（最多 5 秒）
        import time
        deadline = time.time() + 5
        while time.time() < deadline:
            if server.started:
                break
            time.sleep(0.05)
        if not server.started and not server.should_exit:
            logger.error(f"内置反代端口 {self.port} 启动超时")
            return False
        logger.info(f"内置反代已监听 0.0.0.0:{self.port}")
        return True

    def stop(self) -> None:
        try:
            if self._server:
                self._server.should_exit = True
                if self._thread and self._thread.is_alive():
                    self._thread.join(timeout=3)
        except Exception:
            pass
        self._server = None
        self._thread = None