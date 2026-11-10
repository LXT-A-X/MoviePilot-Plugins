"""
任务队列与执行器：串行/多 worker、进度解析、取消、原子替换、校验与历史。

执行流程：
1. 把计划里的命令参数替换成「临时输出路径」与「工作目录」；
2. 依次执行（复制 / mkvmerge / mkvpropedit / ffmpeg），实时记录日志与进度；
3. 用探测结果校验轨道数量与时长；
4. 通过后再落盘：输出模式直接原子替换，替换模式先备份原文件再替换；
5. 写历史、按配置处理已内封的外挂字幕。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from .store import DataStore, new_id

_PERCENT_RE = re.compile(r"#GUI#progress\s+(\d+)%")
_FFMPEG_TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
_CANCEL_WAIT = 5

# mkvmerge/mkvpropedit 的退出码语义：0 成功、1 完成但有警告、2 失败
_WARN_EXIT_TOOLS = {"mkvmerge", "mkvpropedit"}


def _exit_ok(tool: str, code: int) -> bool:
    """
    判断外部命令退出码是否视为成功。

    :param tool: 工具名
    :param code: 进程退出码
    :return: 是否成功
    """
    if code == 0:
        return True
    return code == 1 and tool in _WARN_EXIT_TOOLS


class JobCancelled(RuntimeError):
    """任务被用户取消。"""


class JobRunner:
    """
    插件内的任务队列与执行器。

    :param data_dir: 插件数据目录
    :param store: 数据持久化
    :param config_getter: 返回当前配置的回调
    :param engine_getter: 返回引擎探测结果的回调
    :param probe_getter: 返回 ``probe_media`` 可调用对象的回调
    :param log: 日志回调
    """

    def __init__(
        self,
        data_dir: Path,
        store: DataStore,
        config_getter: Callable[[], dict[str, Any]],
        engine_getter: Callable[[], dict[str, Any]],
        probe_getter: Callable[[Path], dict[str, Any]],
        log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.store = store
        self._config = config_getter
        self._engine = engine_getter
        self._probe = probe_getter
        self._log = log or (lambda _message: None)
        self.running_file = self.data_dir / "running.json"
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._jobs: dict[str, dict[str, Any]] = {}
        self._pending: list[str] = []
        self._paused = False
        self._shutdown = False
        self._workers: list[threading.Thread] = []
        self._live_workers = 0
        self._concurrency = max(1, int(self._config().get("concurrency") or 1))
        self._load_persisted()

    # ------------------------------------------------------------------ 生命周期
    def start(self) -> None:
        """启动 worker 线程（幂等，可重复调用）。"""
        with self._lock:
            self._shutdown = False
            while self._live_workers < self._concurrency:
                self._spawn_worker()

    def _spawn_worker(self) -> None:
        """在持锁状态下创建并启动一个 worker 线程。"""
        index = self._live_workers
        self._live_workers += 1
        thread = threading.Thread(
            target=self._worker_loop, args=(index,),
            name=f"MkvToolkit-job-{index}", daemon=True,
        )
        thread.start()
        self._workers.append(thread)

    def stop(self) -> None:
        """停止 worker、终止运行中的任务并持久化等待队列。"""
        with self._lock:
            self._shutdown = True
            self._cond.notify_all()
            for job in self._jobs.values():
                if job.get("status") == "running":
                    job["cancel_requested"] = True
                    process = job.get("_proc")
                    if process and process.poll() is None:
                        try:
                            process.terminate()
                        except OSError:
                            pass
        for thread in list(self._workers):
            thread.join(timeout=10)
        with self._lock:
            self._workers.clear()
            self._live_workers = 0
            self._persist_queue()

    def set_concurrency(self, value: int) -> None:
        """
        调整并发数：只增删空闲 worker，不打断正在执行的任务。

        :param value: 新的并发数（1~3）
        """
        value = max(1, min(3, int(value)))
        with self._lock:
            if value == self._concurrency:
                return
            self._concurrency = value
            self._cond.notify_all()
            while self._live_workers < value:
                self._spawn_worker()

    # ------------------------------------------------------------------ 提交/查询
    def submit(
        self,
        plan_payload: dict[str, Any],
        preview: dict[str, Any],
        hold: bool = False,
    ) -> dict[str, Any]:
        """
        提交一个计划到等待队列。

        :param plan_payload: 前端原始 plan
        :param preview: ``build_plan()`` 结果
        :param hold: 为 True 时任务只进队列不自动开始，等用户统一启动
        :return: 任务摘要
        """
        job = {
            "id": new_id(),
            "created_at": _now_text(),
            "updated_at": _now_text(),
            "status": "pending",
            "progress": 0,
            "stage": "待启动" if hold else "等待中",
            "hold": bool(hold),
            "plan": plan_payload,
            "preview": preview,
            "path": str(plan_payload.get("path") or ""),
            "name": Path(str(plan_payload.get("path") or "")).name,
            "engine": preview.get("engine"),
            "summary": _summary(preview),
            "output_path": preview.get("output_path"),
            "backup_path": preview.get("backup_path"),
            "backup_deleted": False,
            "no_backup": bool(preview.get("no_backup")),
            "output_mode": preview.get("output_mode"),
            "error": None,
            "warnings": preview.get("warnings") or [],
            "log_lines": [],
            "cancel_requested": False,
            "source_size": _safe_size(Path(str(plan_payload.get("path") or ""))),
        }
        with self._lock:
            self._jobs[job["id"]] = job
            self._pending.append(job["id"])
            self._cond.notify_all()
            self._persist_queue()
        self._log(f"任务已入队：{job['name']}（{job['id']}）")
        return _public_job(job)

    def get(self, job_id: str) -> Optional[dict[str, Any]]:
        """按 ID 取任务。"""
        with self._lock:
            job = self._jobs.get(job_id)
            return _public_job(job) if job else None

    def list_jobs(self, status: str = "all") -> list[dict[str, Any]]:
        """列出内存中的任务（等待 + 运行 + 最近完成）。"""
        with self._lock:
            jobs = list(self._jobs.values())
        result = []
        for job in jobs:
            if status == "pending" and job.get("status") != "pending":
                continue
            if status == "running" and job.get("status") != "running":
                continue
            if status == "finished" and job.get("status") in {"pending", "running"}:
                continue
            result.append(_public_job(job))
        result.sort(key=lambda item: item.get("created_at") or "")
        return result

    def counts(self) -> dict[str, Any]:
        """等待/运行数量与暂停状态。"""
        with self._lock:
            running = sum(1 for job in self._jobs.values() if job.get("status") == "running")
            pending = sum(1 for job in self._jobs.values() if job.get("status") == "pending")
            held = sum(
                1 for job in self._jobs.values()
                if job.get("status") == "pending" and job.get("hold")
            )
            return {"running": running, "pending": pending, "held": held, "paused": self._paused}

    def cancel(self, job_id: str) -> dict[str, Any]:
        """取消等待或运行中的任务。"""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError("任务不存在")
            status = job.get("status")
            if status == "pending":
                if job_id in self._pending:
                    self._pending.remove(job_id)
                job["status"] = "cancelled"
                job["stage"] = "已取消"
                self._jobs.pop(job_id, None)
                self._cond.notify_all()
                self._persist_queue()
                self._append_history(job, "cancelled")
                self._cleanup_uploads(job)
                return _public_job(job)
            if status == "running":
                job["cancel_requested"] = True
                process = job.get("_proc")
                if process and process.poll() is None:
                    try:
                        process.terminate()
                    except OSError:
                        pass
                return _public_job(job)
            raise KeyError("任务已结束")

    def move(self, job_id: str, target: str) -> dict[str, Any]:
        """在等待队列里置顶/上移/下移。"""
        with self._lock:
            if job_id not in self._pending:
                raise KeyError("任务不在等待队列中")
            index = self._pending.index(job_id)
            if target == "top":
                self._pending.insert(0, self._pending.pop(index))
            elif target == "up" and index > 0:
                self._pending[index - 1], self._pending[index] = self._pending[index], self._pending[index - 1]
            elif target == "down" and index < len(self._pending) - 1:
                self._pending[index + 1], self._pending[index] = self._pending[index], self._pending[index + 1]
            self._persist_queue()
            return self.get(job_id) or {}

    def clear_pending(self) -> int:
        """清空等待队列，返回取消数量。"""
        with self._lock:
            pending_ids = list(self._pending)
            self._pending.clear()
            for job_id in pending_ids:
                job = self._jobs.pop(job_id, None)
                if job:
                    job["status"] = "cancelled"
                    self._append_history(job, "cancelled")
                    self._cleanup_uploads(job)
            self._persist_queue()
            self._cond.notify_all()
            return len(pending_ids)

    def set_paused(self, paused: bool) -> dict[str, Any]:
        """暂停/继续队列。"""
        with self._lock:
            self._paused = bool(paused)
            self._persist_queue()
            self._cond.notify_all()
            return self.counts()

    def start_all(self) -> dict[str, Any]:
        """统一启动：解除所有待启动任务的 hold，并恢复队列。"""
        with self._lock:
            started = 0
            for job_id in list(self._pending):
                job = self._jobs.get(job_id)
                if job and job.get("hold"):
                    job["hold"] = False
                    job["stage"] = "等待中"
                    started += 1
            self._paused = False
            self._persist_queue()
            self._cond.notify_all()
            return {"started": started, **self.counts()}

    def start_job(self, job_id: str) -> dict[str, Any]:
        """启动单个待启动任务。"""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError("任务不存在或已结束")
            if job.get("status") != "pending":
                raise KeyError("任务已开始或已结束")
            job["hold"] = False
            job["stage"] = "等待中"
            self._persist_queue()
            self._cond.notify_all()
            return _public_job(job)

    def update(self, job_id: str, plan_payload: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
        """
        修改排队中的任务配置（重新生成计划后覆盖）。

        :param job_id: 任务 ID
        :param plan_payload: 新的原始 plan
        :param preview: 新 plan 的 ``build_plan()`` 结果
        :return: 更新后的任务摘要
        :raises KeyError: 任务不存在或已开始
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                raise KeyError("任务不存在或已结束")
            if job.get("status") != "pending":
                raise KeyError("只有排队中的任务可以修改")
            job["plan"] = plan_payload
            job["preview"] = preview
            job["engine"] = preview.get("engine")
            job["summary"] = _summary(preview)
            job["output_path"] = preview.get("output_path")
            job["backup_path"] = preview.get("backup_path")
            job["output_mode"] = preview.get("output_mode")
            job["warnings"] = preview.get("warnings") or []
            job["source_size"] = _safe_size(Path(str(plan_payload.get("path") or "")))
            job["updated_at"] = _now_text()
            job["stage"] = "待启动" if job.get("hold") else "等待中"
            self._persist_queue()
            return _public_job(job)

    # ------------------------------------------------------------------ 历史/回滚
    def history(self) -> list[dict[str, Any]]:
        """读取历史记录。"""
        return self.store.load_history()

    def delete_history(self, history_id: str) -> bool:
        """删除一条历史记录，并清理只被它引用的临时上传文件。"""
        items = self.store.load_history()
        target = next((item for item in items if item.get("id") == history_id), None)
        removed = self.store.delete_history(history_id)
        if removed and target:
            self._cleanup_uploads({"id": history_id, "plan": target.get("plan")})
        return removed

    def clear_history(self) -> int:
        """清空历史记录，返回删除条数，并清理不再被引用的临时上传文件。"""
        items = self.store.load_history()
        count = self.store.clear_history()
        for item in items:
            self._cleanup_uploads({"id": item.get("id"), "plan": item.get("plan")})
        return count

    def rollback(self, history_id: str) -> dict[str, Any]:
        """
        用备份还原一次“原地替换”操作。

        :param history_id: 历史记录 ID
        :return: 回滚结果
        :raises KeyError: 记录不存在或不可回滚
        """
        items = self.store.load_history()
        target = next((item for item in items if item.get("id") == history_id), None)
        if not target:
            raise KeyError("历史记录不存在")
        backup = Path(str(target.get("backup_path") or ""))
        output = Path(str(target.get("output_path") or target.get("path") or ""))
        if not backup.is_file():
            raise KeyError("备份文件不存在，无法回滚")
        temp = output.with_name(f".{output.stem}.rollback{output.suffix}")
        shutil.copy2(backup, temp)
        os.replace(temp, output)
        self._log(f"已回滚：{output}")
        return {"path": str(output), "backup": str(backup)}

    # ------------------------------------------------------------------ worker
    def _has_takeable(self) -> bool:
        """当前是否有可执行（未被 hold）的等待任务。"""
        for job_id in self._pending:
            job = self._jobs.get(job_id)
            if job and not job.get("hold"):
                return True
        return False

    def _take_next(self) -> Optional[dict[str, Any]]:
        """取出第一个未被 hold 的等待任务。"""
        for index, job_id in enumerate(self._pending):
            job = self._jobs.get(job_id)
            if job and not job.get("hold"):
                self._pending.pop(index)
                return job
        return None

    def _worker_loop(self, index: int) -> None:
        """worker 主循环：取任务 → 执行；并发数降低时主动退出。"""
        try:
            while True:
                with self._lock:
                    while not self._shutdown and (
                        self._paused
                        or not self._has_takeable()
                        or index >= self._concurrency
                    ):
                        if self._shutdown or index >= self._concurrency:
                            return
                        self._cond.wait(timeout=1.0)
                    if self._shutdown:
                        return
                    job = self._take_next()
                    if job is None:
                        continue
                    job["status"] = "running"
                    job["started_at"] = _now_text()
                    job["stage"] = "准备中"
                    self._mark_running(job)
                    self._persist_queue()
                try:
                    self._execute(job)
                except JobCancelled:
                    self._finish(job, "cancelled", "已取消")
                except Exception as error:  # noqa: BLE001 - 执行失败必须记录原因
                    self._finish(job, "failed", str(error))
                    self._log(f"任务失败：{job.get('name')} - {error}")
                finally:
                    with self._lock:
                        self._cond.notify_all()
        finally:
            with self._lock:
                self._live_workers = max(0, self._live_workers - 1)

    def _execute(self, job: dict[str, Any]) -> None:
        """执行单个任务。"""
        preview = job["preview"]
        plan_payload = job["plan"]
        source = Path(str(plan_payload.get("path") or ""))
        output_path = Path(str(preview.get("output_path") or ""))
        if not source.is_file():
            raise RuntimeError(f"源文件不存在：{source}")
        current_size = _safe_size(source)
        if job.get("source_size") and current_size != job["source_size"]:
            raise RuntimeError("源文件在入队后发生变化，请重新预览再提交")

        workdir = self.data_dir / "work" / job["id"]
        workdir.mkdir(parents=True, exist_ok=True)
        temp = output_path.with_name(f".{output_path.stem}.{job['id']}.tmp{output_path.suffix or '.mkv'}")
        self._write_prepares(preview.get("prepares") or [], workdir)
        commands = preview.get("commands") or []
        if not commands:
            raise RuntimeError("计划为空，无法执行")
        total_weight = sum(float(command.get("weight") or 1.0) for command in commands) or 1.0
        done_weight = 0.0
        job["stage"] = "执行中"
        try:
            for command in commands:
                self._check_cancel(job)
                weight = float(command.get("weight") or 1.0)
                self._run_command(job, command, temp, workdir, done_weight / total_weight, weight / total_weight)
                done_weight += weight
                job["progress"] = min(99, int(done_weight / total_weight * 100))
            job["stage"] = "校验中"
            self._verify(job, source, temp, preview)
            self._finish_output(job, source, temp, output_path, preview)
            job["progress"] = 100
            self._finish(job, "success", "完成")
        finally:
            self._cleanup_temp(temp)
            shutil.rmtree(workdir, ignore_errors=True)

    def _run_command(
        self,
        job: dict[str, Any],
        command: dict[str, Any],
        temp: Path,
        workdir: Path,
        base_fraction: float,
        weight_fraction: float,
    ) -> None:
        """执行一条命令并更新进度。"""
        args = [
            str(token)
            .replace("{output}", str(temp))
            .replace("{work}", str(workdir))
            for token in command.get("args") or []
        ]
        tool = str(command.get("tool") or "")
        command_line = " ".join(args)
        self._append_log(job, f"\n$ {command_line}")
        # 命令本身也记录到插件日志（与启动/关闭/任务记录同一个 mkvtoolkit.log）
        self._log(f"[{job.get('id')}] 执行 {tool}: {command_line[:800]}")
        job["command"] = command_line
        if tool == "copy":
            self._copy_with_progress(job, Path(args[0]), Path(args[1]), base_fraction, weight_fraction)
            return
        duration = _float_or_none((job["preview"].get("expected") or {}).get("duration"))
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=dict(os.environ, LC_ALL="C.UTF-8"),
        )
        job["_proc"] = process
        try:
            self._pump_output(job, process, tool, duration, base_fraction, weight_fraction)
        finally:
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            job["_proc"] = None
        if not _exit_ok(tool, process.returncode):
            tail = "\n".join((job.get("log_lines") or [])[-20:])
            raise RuntimeError(
                f"命令执行失败（退出码 {process.returncode}）：{tool}\n{tail}"
            )
        if process.returncode == 1:
            note = f"{tool} 完成但有警告（退出码 1）"
            self._append_log(job, f"（{note}，继续校验输出）")
            with self._lock:
                job.setdefault("runtime_warnings", []).append(note)

    def _pump_output(
        self,
        job: dict[str, Any],
        process: subprocess.Popen[str],
        tool: str,
        duration: Optional[float],
        base_fraction: float,
        weight_fraction: float,
    ) -> None:
        """读取子进程输出、写内存日志并解析进度。"""
        stream = process.stdout
        assert stream is not None
        for line in stream:
            self._check_cancel(job)
            text = line.rstrip()
            if text:
                self._append_log(job, text)
            if text.startswith("Warning:"):
                with self._lock:
                    notes = job.setdefault("runtime_warnings", [])
                    if len(notes) < 8 and text not in notes:
                        notes.append(text)
            if tool == "mkvmerge":
                match = _PERCENT_RE.search(text)
                if match:
                    self._set_progress(job, base_fraction, weight_fraction, int(match.group(1)) / 100.0)
            elif tool == "ffmpeg" and duration:
                match = _FFMPEG_TIME_RE.search(text)
                if match:
                    hours, minutes, seconds = match.groups()
                    current = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                    self._set_progress(job, base_fraction, weight_fraction, min(1.0, current / duration))
        if tool == "mkvpropedit":
            self._set_progress(job, base_fraction, weight_fraction, 1.0)

    def _copy_with_progress(
        self, job: dict[str, Any], source: Path, target: Path, base: float, weight: float,
    ) -> None:
        """带进度的大文件复制（用于 mkvpropedit 前的临时副本）。"""
        try:
            total = source.stat().st_size or 1
        except OSError:
            total = 1
        written = 0
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as src, target.open("wb") as dst:
            while True:
                self._check_cancel(job)
                chunk = src.read(1024 * 1024 * 4)
                if not chunk:
                    break
                dst.write(chunk)
                written += len(chunk)
                self._set_progress(job, base, weight, min(1.0, written / total))
        shutil.copystat(source, target, follow_symlinks=False)

    def _set_progress(self, job: dict[str, Any], base: float, weight: float, fraction: float) -> None:
        """按命令权重换算总进度百分比。"""
        value = (base + weight * max(0.0, min(1.0, fraction))) * 100
        job["progress"] = min(99, int(value))

    def _check_cancel(self, job: dict[str, Any]) -> None:
        """检查取消标记，必要时终止子进程。"""
        if job.get("cancel_requested") or self._shutdown:
            process = job.get("_proc")
            if process and process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=_CANCEL_WAIT)
                except (OSError, subprocess.TimeoutExpired):
                    try:
                        process.kill()
                    except OSError:
                        pass
            raise JobCancelled()

    def _write_prepares(self, prepares: list[dict[str, Any]], workdir: Path) -> None:
        """把计划里预生成的章节等文本写入工作目录。"""
        for item in prepares:
            name = Path(str(item.get("name") or "")).name
            if not name:
                continue
            (workdir / name).write_text(str(item.get("content") or ""), encoding="utf-8")

    def _verify(self, job: dict[str, Any], source: Path, temp: Path, preview: dict[str, Any]) -> None:
        """校验输出文件的轨道数量；时长偏差默认只告警，可在设置里改为严格失败。"""
        if not temp.is_file() or temp.stat().st_size == 0:
            raise RuntimeError("输出文件为空，执行失败")
        expected = preview.get("expected") or {}
        if not expected:
            return
        info = self._probe(temp)
        tracks = [track for track in info.get("tracks") or [] if track.get("type") in {"video", "audio", "subtitle"}]
        counts = {
            "video": sum(1 for track in tracks if track.get("type") == "video"),
            "audio": sum(1 for track in tracks if track.get("type") == "audio"),
            "subtitle": sum(1 for track in tracks if track.get("type") == "subtitle"),
        }
        for kind, expected_count in expected.items():
            if kind in counts and counts[kind] != int(expected_count):
                raise RuntimeError(
                    f"校验失败：{kind} 轨道数量应为 {expected_count}，实际 {counts[kind]}"
                )
        expected_duration = _float_or_none(expected.get("duration"))
        actual_duration = _float_or_none((info.get("container") or {}).get("duration"))
        tolerance = float(self._config().get("validation_tolerance") or 2.0)
        if expected_duration and actual_duration and abs(actual_duration - expected_duration) > tolerance:
            note = (
                f"时长与源视频相差 {actual_duration - expected_duration:+.1f}s"
                f"（超过阈值 {tolerance:.1f}s），通常是新增音轨/字幕来自其它版本"
            )
            if self._config().get("strict_duration_check"):
                raise RuntimeError(f"校验失败：{note}；已开启严格时长校验")
            with self._lock:
                job.setdefault("runtime_warnings", []).append(note)
            self._log(f"警告：{note}")

    def _finish_output(
        self,
        job: dict[str, Any],
        source: Path,
        temp: Path,
        output_path: Path,
        preview: dict[str, Any],
    ) -> None:
        """把临时文件落盘：直接输出、临时备份后替换，或不备份直接替换。"""
        mode = str(preview.get("output_mode") or "dir")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if mode == "replace":
            backup_text = str(preview.get("backup_path") or "")
            if backup_text:
                backup_path = Path(backup_text)
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                if backup_path.exists():
                    backup_path = backup_path.with_name(
                        f"{backup_path.stem}.{int(time.time())}{backup_path.suffix}"
                    )
                # 临时备份：先移走源文件，替换失败时复制回来并保留备份
                shutil.move(str(source), str(backup_path))
                job["backup_path"] = str(backup_path)
                job["backup_deleted"] = False
                try:
                    os.replace(temp, source)
                except OSError as error:
                    try:
                        shutil.copy2(str(backup_path), str(source))
                    except OSError:
                        pass
                    raise RuntimeError(f"写入源文件失败，已尝试从备份恢复：{error}") from error
                job["output_path"] = str(source)
                # 成功：删除临时备份（失败时才保留）
                try:
                    backup_path.unlink()
                except OSError as error:
                    self._log(f"备份删除失败，已保留：{backup_path}（{error}）")
                else:
                    job["backup_deleted"] = True
                    job["backup_path"] = None
                self._prune_backups(backup_path.parent)
            else:
                # 用户选择“不保存备份”：直接原地替换，失败时没有恢复副本
                job["backup_path"] = None
                job["backup_deleted"] = False
                os.replace(temp, source)
                job["output_path"] = str(source)
                self._log(f"已按“不保存备份”原地替换：{source}")
        else:
            if output_path.exists():
                raise RuntimeError(f"输出文件已存在：{output_path}")
            os.replace(temp, output_path)
            job["output_path"] = str(output_path)
        self._handle_subtitles(job, preview)

    def _prune_backups(self, backup_dir: Path) -> None:
        """按配置保留最近 N 份备份。"""
        keep = int(self._config().get("backup_keep") or 0)
        if keep <= 0:
            return
        try:
            files = sorted(
                [item for item in backup_dir.iterdir() if item.is_file() and item.name.endswith(".bak")],
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return
        for item in files[keep:]:
            try:
                item.unlink()
            except OSError:
                continue

    def _handle_subtitles(self, job: dict[str, Any], preview: dict[str, Any]) -> None:
        """
        按配置处理已内封的外挂字幕文件。

        只对“原地替换”生效：输出到新目录时源视频未改动，外挂字幕不应被移走/删除。
        """
        if str(preview.get("output_mode") or "dir") != "replace":
            return
        config = self._config()
        action = str(config.get("subtitle_after") or "keep")
        if action == "keep":
            return
        additions = (job.get("plan") or {}).get("tracks", {}).get("add") or []
        for addition in additions:
            if str(addition.get("kind")) != "subtitle":
                continue
            path = Path(str(addition.get("file") or ""))
            if not path.is_file():
                continue
            if action == "delete":
                try:
                    path.unlink()
                except OSError:
                    continue
            elif action == "archive":
                archive_dir = path.parent / "subs_done"
                try:
                    archive_dir.mkdir(exist_ok=True)
                    target = archive_dir / path.name
                    if target.exists():
                        target = archive_dir / f"{path.stem}.{int(time.time())}{path.suffix}"
                    shutil.move(str(path), str(target))
                except OSError:
                    continue

    def _finish(self, job: dict[str, Any], status: str, message: str) -> None:
        """结束任务：更新状态、写历史、清理内存记录。"""
        with self._lock:
            job["status"] = status
            job["stage"] = {"success": "完成", "failed": "失败", "cancelled": "已取消"}.get(status, message)
            job["finished_at"] = _now_text()
            job["error"] = None if status == "success" else (message if status == "failed" else None)
            if job.get("started_at"):
                job["duration"] = _duration(job["started_at"])
            # 合并预检警告与执行期警告（mkvmerge 退出码 1 / Warning 行）
            merged = list(job.get("warnings") or [])
            for note in job.get("runtime_warnings") or []:
                if note not in merged:
                    merged.append(note)
            job["warnings"] = merged
            self._append_history(job, status)
            self._clear_running(job)
        self._log(f"任务{job['stage']}：{job.get('name')}" + (f" - {message}" if status == "failed" else ""))
        with self._lock:
            # 完成后移出内存队列，历史里可查
            if status != "running":
                self._jobs.pop(job["id"], None)
        try:
            self._cleanup_uploads(job)
        except OSError:
            pass

    def _append_history(self, job: dict[str, Any], status: str) -> None:
        """写入一条历史记录。"""
        item = {
            "id": job["id"],
            "created_at": job.get("created_at"),
            "finished_at": job.get("finished_at") or _now_text(),
            "name": job.get("name"),
            "path": job.get("path"),
            "status": status,
            "summary": job.get("summary"),
            "engine": job.get("engine"),
            "output_path": job.get("output_path"),
            "backup_path": job.get("backup_path"),
            "backup_deleted": bool(job.get("backup_deleted")),
            "no_backup": bool(job.get("no_backup")),
            "output_mode": job.get("output_mode"),
            "duration": job.get("duration"),
            "error": job.get("error"),
            "command": job.get("command"),
            "warnings": job.get("warnings") or [],
            "log_tail": list(job.get("log_lines") or [])[-200:],
            "plan": job.get("plan"),
        }
        self.store.append_history(item)

    # ------------------------------------------------------------------ 临时上传清理
    @staticmethod
    def _job_upload_paths(job: dict[str, Any]) -> set[Path]:
        """从任务/历史计划里收集可能位于上传目录的临时文件路径。"""
        plan = job.get("plan") or {}
        if not isinstance(plan, dict):
            return set()
        result: set[Path] = set()

        def add(value: Any) -> None:
            text = str(value or "").strip()
            if not text:
                return
            try:
                result.add(Path(text).resolve())
            except OSError:
                pass

        attachments = plan.get("attachments")
        if isinstance(attachments, list):
            for item in attachments:
                if isinstance(item, dict):
                    add(item.get("file"))
        tracks = plan.get("tracks")
        if isinstance(tracks, dict):
            for item in tracks.get("add") or []:
                if isinstance(item, dict):
                    add(item.get("file"))
            for item in tracks.get("attachments_add") or []:
                add(item)
        chapters = plan.get("chapters")
        if isinstance(chapters, dict):
            add(chapters.get("file"))
        return result

    def _referenced_uploads(self, exclude_job_id: Optional[str] = None) -> set[Path]:
        """收集仍被内存中的队列/运行任务引用的上传文件（历史记录不保留引用）。"""
        references: set[Path] = set()
        with self._lock:
            jobs = list(self._jobs.values())
        for job in jobs:
            if job.get("id") == exclude_job_id:
                continue
            references |= self._job_upload_paths(job)
        return references

    def _cleanup_uploads(self, job: dict[str, Any]) -> int:
        """
        清理任务引用的临时上传文件（解压出的字体、上传字幕/音频等）。

        - 只删除插件上传目录内的文件；
        - 仍被其它队列任务或历史记录引用的文件不删；
        - 删除后顺带移除空的字体子目录。
        """
        uploads = Path(self.store.uploads_dir).resolve()
        candidates = self._job_upload_paths(job)
        if not candidates:
            return 0
        references = self._referenced_uploads(job.get("id"))
        removed = 0
        for path in sorted(candidates):
            if path in references:
                continue
            try:
                if not path.is_relative_to(uploads):
                    continue
            except (OSError, ValueError):
                continue
            try:
                if path.is_file():
                    path.unlink()
                    removed += 1
            except OSError:
                continue
            parent = path.parent
            while parent != uploads and parent.is_relative_to(uploads):
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
        if removed:
            self._log(f"已清理任务临时文件：{removed} 个")
        return removed

    # ------------------------------------------------------------------ 工具
    def _mark_running(self, job: dict[str, Any]) -> None:
        """标记当前正在执行的任务，供重启后识别“中断”。"""
        try:
            payload = {
                "id": job.get("id"),
                "name": job.get("name"),
                "path": job.get("path"),
                "started_at": job.get("started_at"),
            }
            temp = self.running_file.with_suffix(".tmp")
            temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(temp, self.running_file)
        except OSError:
            pass

    def _clear_running(self, job: dict[str, Any]) -> None:
        """任务结束后清除运行标记。"""
        try:
            if not self.running_file.exists():
                return
            data = json.loads(self.running_file.read_text(encoding="utf-8"))
            if str(data.get("id")) == str(job.get("id")):
                self.running_file.unlink()
        except (OSError, ValueError):
            pass

    def _recover_interrupted(self) -> None:
        """把上次进程中断时正在运行的任务记为“已中断”。"""
        if not self.running_file.exists():
            return
        try:
            data = json.loads(self.running_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        try:
            self.running_file.unlink()
        except OSError:
            pass
        if not isinstance(data, dict) or not data.get("id"):
            return
        self.store.append_history({
            "id": data.get("id"),
            "created_at": data.get("started_at") or _now_text(),
            "finished_at": _now_text(),
            "name": data.get("name"),
            "path": data.get("path"),
            "status": "interrupted",
            "summary": "插件重启时中断",
            "engine": None,
            "output_path": None,
            "backup_path": None,
            "output_mode": None,
            "duration": None,
            "error": "插件重启导致任务中断，临时文件已清理，请重新提交",
            "command": None,
            "warnings": [],
            "plan": None,
        })
        self._log(f"检测到上次运行中断的任务：{data.get('name')}")

    def _load_persisted(self) -> None:
        """恢复上次未完成的等待任务；运行中的任务标记为中断。"""
        self._recover_interrupted()
        data = self.store.load_queue()
        self._paused = bool(data.get("paused"))
        for item in data.get("jobs") or []:
            plan = item.get("plan")
            preview = item.get("preview")
            if not isinstance(plan, dict) or not isinstance(preview, dict):
                continue
            job_id = str(item.get("id") or new_id())
            hold = bool(item.get("hold"))
            job = {
                "id": job_id,
                "created_at": item.get("created_at") or _now_text(),
                "updated_at": _now_text(),
                "status": "pending",
                "progress": 0,
                "stage": "待启动（已恢复）" if hold else "等待中（已恢复）",
                "hold": hold,
                "plan": plan,
                "preview": preview,
                "path": str(plan.get("path") or ""),
                "name": Path(str(plan.get("path") or "")).name,
                "engine": preview.get("engine"),
                "summary": _summary(preview),
                "output_path": preview.get("output_path"),
                "backup_path": preview.get("backup_path"),
                "output_mode": preview.get("output_mode"),
                "error": None,
                "warnings": preview.get("warnings") or [],
                "log_lines": [],
                "cancel_requested": False,
                "source_size": _safe_size(Path(str(plan.get("path") or ""))),
            }
            self._jobs[job_id] = job
            self._pending.append(job_id)
        if self._pending:
            self._log(f"已恢复 {len(self._pending)} 个等待任务")

    def _persist_queue(self) -> None:
        """把等待队列写入磁盘。"""
        with self._lock:
            jobs = []
            for job_id in self._pending:
                job = self._jobs.get(job_id)
                if not job:
                    continue
                jobs.append({
                    "id": job["id"],
                    "created_at": job.get("created_at"),
                    "hold": bool(job.get("hold")),
                    "plan": job.get("plan"),
                    "preview": job.get("preview"),
                })
            try:
                self.store.save_queue(self._paused, jobs)
            except OSError as error:
                self._log(f"保存队列失败：{error}")

    def _cleanup_temp(self, temp: Path) -> None:
        """删除遗留的临时输出文件。"""
        try:
            if temp.exists():
                temp.unlink()
        except OSError:
            pass

    def _append_log(self, job: dict[str, Any], text: str) -> None:
        """把一行输出追加到任务内存日志（最多保留最近 3000 行）。"""
        with self._lock:
            lines = job.setdefault("log_lines", [])
            lines.append(text)
            if len(lines) > 3000:
                del lines[:len(lines) - 3000]

    def log_tail(self, job_id: str, lines: int = 100) -> list[str]:
        """读取某任务内存日志末尾。"""
        with self._lock:
            job = self._jobs.get(job_id)
            history = list((job or {}).get("log_lines") or [])
        try:
            count = max(1, min(1000, int(lines)))
        except (TypeError, ValueError):
            count = 100
        return history[-count:]


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    """剥掉内部字段后的任务视图。"""
    return {
        "id": job.get("id"),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "status": job.get("status"),
        "progress": job.get("progress"),
        "stage": job.get("stage"),
        "hold": bool(job.get("hold")),
        "path": job.get("path"),
        "name": job.get("name"),
        "engine": job.get("engine"),
        "summary": job.get("summary"),
        "output_path": job.get("output_path"),
        "backup_path": job.get("backup_path"),
        "output_mode": job.get("output_mode"),
        "duration": job.get("duration"),
        "error": job.get("error"),
        "warnings": job.get("warnings") or [],
        "command": job.get("command"),
        "plan": job.get("plan"),
    }


def _summary(preview: dict[str, Any]) -> str:
    """生成一行中文操作摘要。"""
    changes = preview.get("changes") or {}
    parts: list[str] = []
    if changes.get("add"):
        parts.append(f"+{len(changes['add'])} 素材")
    if changes.get("drop"):
        parts.append(f"-{len(changes['drop'])} 轨道")
    if changes.get("edit"):
        parts.append(f"改 {len(changes['edit'])} 项属性")
    if changes.get("attachments_add"):
        parts.append(f"+{len(changes['attachments_add'])} 附件")
    if changes.get("attachments_drop"):
        parts.append(f"-{len(changes['attachments_drop'])} 附件")
    if changes.get("chapters") in {"clear", "import"}:
        parts.append("章节" + ("清空" if changes["chapters"] == "clear" else "导入"))
    if changes.get("title"):
        parts.append("改标题")
    return " · ".join(parts) if parts else "无变更"


def _now_text() -> str:
    """当前时间文本。"""
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _duration(started_at: str) -> Optional[float]:
    """计算从开始到现在的耗时（秒）。"""
    try:
        start = time.mktime(time.strptime(started_at, "%Y-%m-%d %H:%M:%S"))
        return round(time.time() - start, 1)
    except (ValueError, OverflowError):
        return None


def _safe_size(path: Path) -> int:
    """读取文件大小，失败返回 0。"""
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _float_or_none(value: Any) -> Optional[float]:
    """转 float，失败返回 None。"""
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
