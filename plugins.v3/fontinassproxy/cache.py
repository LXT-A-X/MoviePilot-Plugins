# -*- coding: utf-8 -*-
"""字幕字体代理 — 缓存与并发控制。

- 双层缓存：进程内 LRU + 磁盘（按 key 存处理后的 ASS 文件）。
- single-flight：同一 key 的并发请求合并成一个实际任务，避免并发首播拖垮 CPU。
- 全局并发闸门（asyncio.Semaphore）：在插件请求链路中使用，超限降级透传。

注意：实际子集化是同步 CPU 密集调用，必须走 ``run_in_executor``（由主处理链路负责）。
"""

from __future__ import annotations

import asyncio
import hashlib
import threading
import json
import logging
import os
import tempfile
import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Dict, Optional

logger = logging.getLogger("FontInAssProxy")

DEFAULT_KEY_PARTS = ("ItemId", "MediaSourceId", "SubtitleIndex", "Format")


class SubtitleCache:
    """处理结果缓存：内存 LRU + 磁盘。"""

    def __init__(self, cache_dir: str, mem_size: int = 256,
                 ttl_hours: float = 720.0):
        self.cache_dir = cache_dir
        self.ttl_seconds = ttl_hours * 3600
        try:
            os.makedirs(cache_dir, exist_ok=True)
        except OSError:
            cache_dir = os.path.join(os.path.dirname(__file__), ".cache")
            os.makedirs(cache_dir, exist_ok=True)
            self.cache_dir = cache_dir

        self._mem: "OrderedDict[str, bytes]" = OrderedDict()
        self._mem_size = mem_size          # 条数上限（保留兼容）
        self._mem_bytes = mem_size * 1024 * 1024  # 字节上限：默认 256MB 改为按条估算
        self._mem_bytes_now = 0
        self._lock = threading.Lock()      # 纯内存临界区：threading.Lock 跨事件循环安全

    # -- key ------------------------------------------------------------------
    @staticmethod
    def make_key(*parts: Any) -> str:
        """由请求/配置相关片段生成缓存 key（md5 hex）。"""
        raw = "|".join(str(p) for p in parts if p is not None)
        return hashlib.md5(raw.encode("utf-8", "ignore")).hexdigest()

    # -- 内存 -----------------------------------------------------------------
    def mem_get(self, key: str) -> Optional[bytes]:
        with self._lock:
            val = self._mem.get(key)
            if val is not None:
                self._mem.move_to_end(key)  # LRU 刷新
                return val
            if key in self._mem:
                self._mem_bytes_now -= len(self._mem[key])
                del self._mem[key]
            return None

    def mem_set(self, key: str, data: bytes):
        with self._lock:
            if key in self._mem:
                self._mem_bytes_now -= len(self._mem[key])
                self._mem.move_to_end(key)
            else:
                self._mem_bytes_now += len(data)
            self._mem[key] = data
            # LRU 淘汰：同时按条数与字节上限
            while (len(self._mem) > self._mem_size
                   or self._mem_bytes_now > self._mem_bytes):
                if not self._mem:
                    break
                _k, _v = self._mem.popitem(last=False)
                self._mem_bytes_now -= len(_v)

    # -- 磁盘 -----------------------------------------------------------------
    def _disk_path(self, key: str) -> str:
        return os.path.join(self.cache_dir, f"{key}.ass")

    def disk_get(self, key: str) -> Optional[bytes]:
        path = self._disk_path(key)
        try:
            if not os.path.exists(path):
                return None
            if self.ttl_seconds > 0:
                mtime = os.path.getmtime(path)
                if time.time() - mtime > self.ttl_seconds:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                    return None
            with open(path, "rb") as f:
                return f.read()
        except OSError:
            return None

    def disk_set(self, key: str, data: bytes):
        path = self._disk_path(key)
        try:
            fd, tmp = tempfile.mkstemp(dir=self.cache_dir, suffix=".tmp")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                os.replace(tmp, path)
            except OSError:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        except OSError:
            pass

    # -- 统一接口 -------------------------------------------------------------
    async def get(self, key: str) -> Optional[bytes]:
        data = self.mem_get(key)
        if data is not None:
            return data
        data = await asyncio.to_thread(self.disk_get, key)
        if data is not None:
            self.mem_set(key, data)
        return data

    async def set(self, key: str, data: bytes):
        self.mem_set(key, data)
        await asyncio.to_thread(self.disk_set, key, data)

    async def clear(self) -> int:
        """清空内存与磁盘缓存，返回删除的文件数。"""
        with self._lock:
            self._mem.clear()
            self._mem_bytes_now = 0
        removed = 0
        for fname in os.listdir(self.cache_dir):
            if fname.endswith(".ass"):
                try:
                    os.remove(os.path.join(self.cache_dir, fname))
                    removed += 1
                except OSError:
                    pass
        return removed

    def clear_expired(self) -> int:
        """删除超过 TTL 的磁盘缓存文件，返回删除数。"""
        if self.ttl_seconds <= 0:
            return 0
        removed = 0
        now = time.time()
        try:
            for fname in os.listdir(self.cache_dir):
                if not fname.endswith(".ass"):
                    continue
                try:
                    path = os.path.join(self.cache_dir, fname)
                    if now - os.path.getmtime(path) > self.ttl_seconds:
                        os.remove(path)
                        removed += 1
                except OSError:
                    continue
        except OSError:
            pass
        return removed

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            mem_bytes = sum(len(v) for v in list(self._mem.values()))
        try:
            disk_files = [f for f in os.listdir(self.cache_dir) if f.endswith(".ass")]
        except OSError:
            disk_files = []
        return {
            "mem_items": len(self._mem),
            "mem_bytes": mem_bytes,
            "disk_files": len(disk_files),
            "disk_dir": self.cache_dir,
        }


class SingleFlight:
    """同 key 并发去重：第一个调用执行，其余等待同一结果。"""

    def __init__(self):
        self._tasks: Dict[str, asyncio.Future] = {}
        self._mu = threading.Lock()   # 纯内存临界区：threading.Lock 跨事件循环安全

    async def run(self, key: str, func: Callable[[], Awaitable[Any]]) -> Tuple:
        """返回 ``(result, is_leader)``：is_leader 为 True 表示本次真正执行了 func
        （等待者拿到的 False），便于调用方只在 leader 侧写缓存（轻微-9）。"""
        with self._mu:
            fut = self._tasks.get(key)
            if fut is not None and not fut.done():
                # 已有在处理：等待该结果（非 leader）
                return await asyncio.shield(fut), False
            new_fut = asyncio.get_event_loop().create_future()
            self._tasks[key] = new_fut

        try:
            result = await func()
            if not new_fut.done():
                new_fut.set_result(result)
            return result, True
        except BaseException as exc:
            if not new_fut.done():
                new_fut.set_exception(exc)
            raise
        finally:
            with self._mu:
                if self._tasks.get(key) is new_fut:
                    self._tasks.pop(key, None)


def cache_key_payload(index_version: int, srt_version: int) -> str:
    """把字体索引版本与 SRT 样式配置版本序列化进 key 的一部分。"""
    return f"{index_version}|{srt_version}"