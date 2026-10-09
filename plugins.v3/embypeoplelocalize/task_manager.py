"""
统一任务状态机（TaskManager）
============================
把原先散落在 `__init__.py` 各处的「运行位 / 暂停位 / 停止位 / 启动器」收拢到一处，
形成单一可信来源（Single Source of Truth），便于审计与单测。

设计原则（保守抽取，行为与原实现逐字一致）：
- 只做「移动」，不改语义；方法名、签名、返回值全部保持原样。
- 通过 mixin 混入插件主类，`self._TASK_FLAGS` / `self._task_running(...)` 等
  调用点无需改动，测试对 `_set_task_running` / `_task_running` 的实例级 monkeypatch
  亦不受影响（实例属性优先于继承来的方法）。

任务运行位（_TASK_FLAGS）映射到实例上的布尔属性：
    scan → _scan_running / translate → _translate_running / writeback → _writeback_running
    pool → _pool_running / probe → _probe_running
聚合位 `_is_running`（旧代码/UI 读取）由各运行位推导，保持向后兼容。
"""
import threading
import time
from typing import Optional


class TaskStateMixin:
    """任务状态机：运行位、暂停位、停止门与统一启动器。"""

    _TASK_FLAGS = {
        "scan": "_scan_running",
        "translate": "_translate_running",
        "writeback": "_writeback_running",
        "pool": "_pool_running",
        "probe": "_probe_running",
    }

    # ──────────────────────────── 运行位 ────────────────────────────
    def _task_running(self, task: str) -> bool:
        """某任务是否在跑（未知任务回退到聚合位）。"""
        _a = self._TASK_FLAGS.get(str(task or ""))
        return bool(getattr(self, _a, False)) if _a else bool(getattr(self, "_is_running", False))

    def _recompute_running(self) -> None:
        """由各任务位聚合推导 _is_running（旧代码/UI 读取它做「运行中」判断）。"""
        self._is_running = any(bool(getattr(self, _a, False)) for _a in self._TASK_FLAGS.values())

    def _set_task_running(self, task: str, on: bool) -> None:
        """置/清某任务运行位（调用方负责持 _scan_lock），并同步聚合镜像。"""
        _a = self._TASK_FLAGS.get(str(task or ""))
        if _a:
            setattr(self, _a, bool(on))
        self._recompute_running()

    # ──────────────────────────── 启动器 ────────────────────────────
    def _launch_nfo_worker(self, body: dict) -> Optional[dict]:
        """统一 NFO worker 启动 —— 锁内置位 _is_running 后启动线程，
        若线程创建/启动期间抛异常则回滚运行状态（否则 _is_running 卡 True，
        所有任务被拒直到重启）。返回启动失败时的错误响应，成功返回 None。
        只按 scan 位互斥（扫描×扫描互斥；与翻译/写回可并行 —— 文档 §3.9）。"""
        with self._scan_lock:
            if self._task_running("scan"):
                return {"success": False, "message": "已有任务正在运行（Emby 扫描或 NFO 扫描）"}
            self._set_task_running("scan", True)
            self._scan_stop = False
            self._stop_requested = False  # 旧全局位（Webhook 事件管线沿用）保持原语义
            self._set_task_paused("scan", False)
        try:
            self._scan_thread = threading.Thread(target=self._nfo_sync_worker, args=(body,), daemon=True)
            self._scan_thread.start()
            self._task_threads["scan"] = self._scan_thread
        except Exception:
            with self._scan_lock:
                self._set_task_running("scan", False)
                self._scan_status["running"] = False
            raise
        return None

    def _launch_bg(self, target, body: Optional[dict] = None,
                   task: str = "translate") -> Optional[dict]:
        _task = str(task or "translate")
        _conflicts = {"translate": ("translate", "writeback"),
                      "writeback": ("writeback", "translate"),
                      "pool": ("pool", "scan", "translate", "writeback", "probe")}.get(_task, (_task,))
        with self._scan_lock:
            if any(self._task_running(_t) for _t in _conflicts):
                return {"success": False, "message": "已有任务正在运行，请先「终止」或等待完成后再试"}
            self._set_task_running(_task, True)
            _own_flag = {"scan": "_scan_stop", "translate": "_tx_stop", "writeback": "_wb_stop",
                         "pool": "_pool_stop", "probe": "_probe_stop"}.get(_task)
            if _own_flag:
                setattr(self, _own_flag, False)
            self._stop_requested = False  # 旧全局位（Webhook 事件管线沿用）保持原语义
            if _task in ("scan", "pool"):
                self._set_task_paused(_task, False)
        try:
            _th = threading.Thread(target=target, args=(body,), daemon=True)
            _th.start()
            if _task == "pool":
                self._pool_thread = _th
            elif _task == "writeback":
                self._wb_job_thread = _th
            elif _task == "translate":
                self._tx_job_thread = _th
            else:
                self._scan_thread = _th
            self._task_threads[_task] = _th
        except Exception:
            with self._scan_lock:
                self._set_task_running(_task, False)
                self._scan_status["running"] = False
            raise
        return None

    # ──────────────────────────── 暂停位 ────────────────────────────
    def _task_paused(self, kind: str) -> bool:
        """任务是否处于「暂停」状态（scan/pool/translate）。
        纳入 translate —— 翻译暂停=不发起新的 LLM 请求（当前一批跑完即停，词条留 DB）。"""
        if kind == "scan":
            return bool(getattr(self, "_scan_paused", False))
        if kind == "pool":
            return bool(getattr(self, "_pool_paused", False))
        if kind == "translate":
            return bool(getattr(self, "_tx_paused", False))
        return False

    def _task_busy_for_pause(self, kind: str) -> bool:
        """该任务此刻是否「真正在跑」—— 决定全局「暂停」是否作用于它。
        翻译 worker 是常驻线程（线程存活 ≠ 在翻译），故以「已获消费许可」为准。"""
        if kind in ("scan", "pool", "writeback", "probe"):
            return self._task_running(kind)
        if kind == "translate":
            return bool(getattr(self, "_tx_requested", False))
        return False

    def _set_task_paused(self, kind: str, paused: bool) -> list:
        """置/清任务的暂停位。kind: scan/pool/translate/all（''/'*'/'stop' 视为 all）。
        返回实际生效的任务名列表。

        全局「暂停」（kind=all）只作用于「当前真正在跑」的任务 —— 修复幽灵暂停：
        此前只跑拉取人名时点一次「暂停」，会把空闲的扫描/翻译也标成暂停位；
        之后即便只点拉取区的「继续」，仪表盘「AI 翻译 Worker」仍显示「已暂停（手动）」、
        运行操作一直停在「继续」清不掉（一份暂停留了多个位，局部入口只清得掉一个）。
        显式 target（scan/pool/translate）时按用户意图照设；
        「继续」（paused=False）按 target 范围清除（all → 清全部，单个 → 只清该任务）。"""
        _k = str(kind or "all").strip().lower()
        _valid = ("scan", "pool", "translate")
        if _k in ("all", "", "*", "stop"):
            _targets = ([t for t in _valid if self._task_busy_for_pause(t)]
                        if paused else list(_valid))
        else:
            _targets = [_k] if _k in _valid else []
        for _t in _targets:
            if _t == "scan":
                self._scan_paused = bool(paused)
                try:
                    self._scan_status["paused"] = bool(paused)
                except Exception:
                    pass
            elif _t == "pool":
                self._pool_paused = bool(paused)
                if isinstance(getattr(self, "_pool_status", None), dict):
                    self._pool_status["paused"] = bool(paused)
            elif _t == "translate":
                self._tx_paused = bool(paused)
        return _targets

    def _pause_gate(self, kind: str) -> bool:
        """暂停门：任务被暂停时在此阻塞等待「继续」（每 0.3s 轮询，兼顾停止）。
        :return: True=可继续执行；False=等待期间收到停止请求，调用方应 break 退出。"""
        if not self._task_paused(kind):
            return True
        _flag = {"scan": "_scan_stop", "pool": "_pool_stop", "translate": "_tx_stop"}.get(kind, "_scan_stop")
        _logged = False
        while self._task_paused(kind):
            if getattr(self, _flag, False):
                return False
            if not _logged:
                _logged = True
                try:
                    self._push_log("INFO", f"[{ {'scan': '扫描', 'pool': '拉取', 'translate': '翻译'}.get(kind, kind) }] 已暂停：等待「继续」…（进度保留）")
                except Exception:
                    pass
            time.sleep(0.3)
        return True
