"""常驻子集化工作进程客户端。

- 帧协议：每行一个 JSON（请求带自增 id，响应回传同 id），无需长度前缀
- 单进程复用：省掉每条字幕的进程启动 + uharfbuzz/fontTools 导入开销
- 崩溃/超时：杀掉当前进程并清空管道，下一次请求自动重启
- 空闲回收：超过 IDLE_TTL_SECONDS 没有请求就主动退出进程，释放 uharfbuzz/fontTools 内存
- stderr 由独立线程持续排空（防管道写满阻塞子进程），只保留末尾诊断信息
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional


class SubsetWorkerStartError(RuntimeError):
    """工作进程无法启动（解释器/路径/权限），调用方可回退进程内执行。"""


class SubsetWorkerTimeout(TimeoutError):
    """单次请求超时（工作进程已被终止）。"""


class SubsetWorkerCrashed(RuntimeError):
    """工作进程退出或协议异常（已隔离，可自动重启）。"""


class SubsetWorkerClient:
    # 常驻进程每处理 N 条任务回收一次，避免 Python/fontTools 长期累积的内存碎片
    MAX_REQUESTS_PER_PROCESS = 100
    # 空闲超过该秒数就回收工作进程（长时间没有字幕任务时释放内存）；下次请求再按需重启
    IDLE_TTL_SECONDS = 300.0
    # 空闲巡检间隔上限（实际取 min(此值, TTL/2)）
    IDLE_CHECK_INTERVAL = 30.0

    def __init__(self, worker_path: str | Path) -> None:
        self._worker = Path(worker_path)
        self._lock = threading.RLock()
        self._proc: Optional[subprocess.Popen] = None
        self._lines: "queue.Queue[Optional[str]]" = queue.Queue()
        self._seq = 0
        self._served = 0
        self._stderr_tail = ""
        self._last_used = time.monotonic()
        self._reaper: Optional[threading.Thread] = None
        self._reaper_stop = threading.Event()

    # ── 进程管理 ──────────────────────────────────────────

    def _start_locked(self) -> None:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        creationflags = 0
        if os.name == "nt":
            creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            proc = subprocess.Popen(
                [sys.executable, str(self._worker), "--server"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=str(self._worker.parent),
                env=env,
                creationflags=creationflags,
            )
        except Exception as err:
            raise SubsetWorkerStartError(str(err)) from err
        self._proc = proc
        self._lines = queue.Queue()
        self._served = 0
        self._stderr_tail = ""
        self._last_used = time.monotonic()
        threading.Thread(target=self._pump_stdout, args=(proc, self._lines), daemon=True).start()
        threading.Thread(target=self._pump_stderr, args=(proc,), daemon=True).start()
        self._start_reaper_locked()

    def _start_reaper_locked(self) -> None:
        if self._reaper is not None and self._reaper.is_alive():
            return
        self._reaper_stop.clear()
        self._reaper = threading.Thread(
            target=self._reap_idle, name="ziti-subset-reaper", daemon=True
        )
        self._reaper.start()

    def _reap_idle(self) -> None:
        """空闲回收：超过 TTL 没有请求就杀掉工作进程，下次请求再按需重启。

        只在拿到锁（= 没有在途请求）后才判断，不会打断正在执行的任务。
        """
        interval = max(0.01, min(self.IDLE_CHECK_INTERVAL, self.IDLE_TTL_SECONDS / 2.0))
        while not self._reaper_stop.wait(interval):
            with self._lock:
                if self._proc is None:
                    continue  # 进程已被其他路径回收（条数回收/崩溃/超时），等下次启动
                if time.monotonic() - self._last_used < self.IDLE_TTL_SECONDS:
                    continue
                self._discard_locked()

    @staticmethod
    def _pump_stdout(proc: subprocess.Popen, lines: "queue.Queue[Optional[str]]") -> None:
        try:
            for line in proc.stdout:
                lines.put(line)
        except Exception:
            pass
        finally:
            lines.put(None)  # EOF 哨兵：让等待方立刻知道进程已结束

    def _pump_stderr(self, proc: subprocess.Popen) -> None:
        try:
            for line in proc.stderr:
                self._stderr_tail = (self._stderr_tail + line)[-2000:]
        except Exception:
            pass

    def _ensure_started_locked(self) -> None:
        proc = self._proc
        if proc is not None and proc.poll() is None:
            return
        self._discard_locked()
        self._start_locked()

    def _discard_locked(self) -> Optional[int]:
        """终止并清理当前进程（若仍存活），返回退出码。"""
        proc = self._proc
        self._proc = None
        self._lines = queue.Queue()
        if proc is None:
            return None
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass
        return proc.returncode

    # ── 请求 ──────────────────────────────────────────────

    def request(self, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        """发一条任务并等待同 id 的响应。

        异常：SubsetWorkerStartError（启动失败）/ SubsetWorkerTimeout（超时，进程已杀）
        / SubsetWorkerCrashed（进程退出或协议异常，已隔离）。
        """
        with self._lock:
            self._ensure_started_locked()
            self._seq += 1
            req = dict(payload)
            req["id"] = self._seq
            proc = self._proc
            lines = self._lines
            try:
                if proc is None or proc.stdin is None:
                    raise RuntimeError("stdin 不可用")
                proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
                proc.stdin.flush()
            except Exception as err:
                code = self._discard_locked()
                raise SubsetWorkerCrashed(f"写入工作进程失败（exit={code}）") from err
            deadline = time.time() + max(1.0, float(timeout))
            while True:
                remain = deadline - time.time()
                if remain <= 0:
                    self._discard_locked()
                    raise SubsetWorkerTimeout(
                        f"请求超时（{int(timeout)} 秒），工作进程已终止"
                    )
                try:
                    line = lines.get(timeout=min(remain, 1.0))
                except queue.Empty:
                    continue
                if line is None:
                    code = self._discard_locked()
                    tail = self._stderr_tail.strip()[-600:]
                    raise SubsetWorkerCrashed(
                        f"工作进程已退出（exit={code}）" + (f": {tail}" if tail else "")
                    )
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                if not isinstance(data, dict):
                    continue
                if data.get("id") not in (None, self._seq):
                    # 历史残留/不属于本次请求的响应，丢弃
                    continue
                self._served += 1
                self._last_used = time.monotonic()
                if self._served >= self.MAX_REQUESTS_PER_PROCESS:
                    # 空闲态回收：响应已送达，直接杀进程，下一次请求重新启动
                    self._discard_locked()
                return data

    def abort(self) -> None:
        """立即终止（停服/重载配置）：不等待在途请求，用 EOF 哨兵让其快速失败。"""
        proc = self._proc
        lines = self._lines
        self._proc = None
        self._lines = queue.Queue()
        self._reaper_stop.set()
        try:
            lines.put_nowait(None)  # 唤醒正在等待响应的线程
        except Exception:
            pass
        if proc is None:
            return
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass

    def close(self) -> None:
        """优雅关闭：发 shutdown 帧，超时则强杀。"""
        with self._lock:
            self._reaper_stop.set()
            proc = self._proc
            if proc is None:
                return
            try:
                if proc.poll() is None and proc.stdin is not None:
                    proc.stdin.write(json.dumps({"id": 0, "task": "shutdown"}) + "\n")
                    proc.stdin.flush()
                    proc.wait(timeout=3)
            except Exception:
                pass
            self._discard_locked()

    @property
    def pid(self) -> Optional[int]:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return None
        return proc.pid

    @property
    def alive(self) -> bool:
        proc = self._proc
        return proc is not None and proc.poll() is None
