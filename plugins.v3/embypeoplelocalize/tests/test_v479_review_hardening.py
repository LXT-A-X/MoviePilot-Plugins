# -*- coding: utf-8 -*-
"""v4.7.9 回归：第三方深度审查（基于 v4.7.8 的报告）中**本轮已修**的条目。

覆盖：
  T1  P0-01    根目录健康闸：挂载断开 / 权限 / 未选库 → **不标 missing、不物理清理**
  T2  P0-01-8  维护：标记「实际更新 0 行」时不得产生失效事件 / 通知（源码级）
  T3  P2-04    purge_expired 返回**实际删除行数**；SQL 失败 → -1（不再谎报「已清理成功」）
  T4  P2-01    观察期解析**尊重显式 0**（插件 `_nfo_grace_hours` + db `_grace_secs`）
  T5  P1-05    探测本轮不完整（有剩余 / 清单不完整）→ 不更新 `_probe_last_deep`
  T6  P1-08    定时扫描：**先确认 worker 启动成功**再写 `_last_full_scan_ts`
  T7  P1-07    任务状态读取异常 → **fail-closed**（按忙碌拦截）
  T8  P1-04    Webhook 延迟队列持久化 `added_count`（重启后处理范围不变）
"""
import sys
import os
import re
import types
import time
import textwrap
import tempfile
import threading
import importlib.util
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl479hard_"))
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
_N = [0, 0]


def check(cond, msg):
    if cond:
        _N[0] += 1
        print(f"[PASS] {msg}")
    else:
        _N[1] += 1
        print(f"[FAIL] {msg}")


class _Logger:
    def __init__(self):
        self.infos, self.warnings, self.debugs, self.errors = [], [], [], []

    def debug(self, m, *a, **k):
        self.debugs.append(str(m))

    def info(self, m, *a, **k):
        self.infos.append(str(m))

    def warning(self, m, *a, **k):
        self.warnings.append(str(m))

    def error(self, m, *a, **k):
        self.errors.append(str(m))

    def log(self, *a, **k):
        pass


logger = _Logger()
_m = types.ModuleType("app"); _s = types.ModuleType("app.sdk")
_l = types.ModuleType("app.sdk.logging"); _l.logger = logger
_c = types.ModuleType("app.sdk.config")
_c.settings = type("S", (), {"CONFIG_PATH": str(TMP)})()
sys.modules.update({"app": _m, "app.sdk": _s, "app.sdk.logging": _l, "app.sdk.config": _c})


def _grab_method(src, name):
    mm = re.search(rf"^([ \t]*)def {re.escape(name)}\(", src, re.M)
    assert mm, f"未找到 {name}"
    indent = len(mm.group(1))
    lines = src[mm.start():].splitlines()
    out = [lines[0]]
    for ln in lines[1:]:
        _st = ln.lstrip()
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent and (_st.startswith("def ") or _st.startswith("@")):
            break
        out.append(ln)
    return textwrap.dedent("\n".join(out))


print("=" * 72)
print("v4.7.9 回归：第三方深度审查（v4.7.8）本轮修复项")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] P0-01 根目录健康闸")
# ─────────────────────────────────────────────
_nsH = {"logger": logger, "os": os}
exec(_grab_method(_SRC, "_nfo_roots_health"), _nsH)


class _RootsSelf:
    _nfo_roots_health = _nsH["_nfo_roots_health"]
    _nfo_dead_grace_hours = 24

    def __init__(self, roots):
        self._roots = roots

    def _all_nfo_roots(self):
        return self._roots

    def _warn_once(self, *a, **k):
        pass


_good = tempfile.mkdtemp(prefix="epl479root_")
_h1 = _RootsSelf([_good])._nfo_roots_health()
check(_h1.get("ok") is True, f"根目录可读可枚举 → ok=True（{_h1.get('reason')}）")
_gone = tempfile.mkdtemp(prefix="epl479mnt_")
os.rmdir(_gone)
_h2 = _RootsSelf([_good, _gone])._nfo_roots_health()
check(_h2.get("ok") is False and list(_h2.get("bad") or []) == [_gone],
      f"多个根之一不可访问（挂载点消失）→ ok=False，bad={_h2.get('bad')}")
_h3 = _RootsSelf([])._nfo_roots_health()
check(_h3.get("ok") is False, "未选择任何媒体库 → ok=False（不允许据此判「缺失」）")

_mp = _grab_method(_SRC, "_maintenance_pass")
check("self._nfo_roots_health()" in _mp, "维护前做根目录健康检查")
check(_mp.index("_nfo_roots_health()") < _mp.index("mark_deleted("),
      "健康闸在「标记观察期」之前（不健康时绝不标 missing）")
_seg = _mp[_mp.index('if not _hh.get("ok"):'):]
check("return" in _seg[:500], "不健康 → 直接跳过本轮（既不标 missing、也不 purge）")

# ─────────────────────────────────────────────
print("\n[T2] P0-01-8：标记 0 行不产生失效事件/通知（源码级）")
# ─────────────────────────────────────────────
check("_marked_items" in _mp and "if _n > 0:" in _mp,
      "只把「mark_deleted 实际更新 >0 行」的条目纳入通知/事件")
check("if not _marked_items:" in _mp, "全部 0 行 → 走告警分支（不产生失效事件）")
_i_push = _mp[_mp.index("if not _marked_items:"):_mp.index("else:", _mp.index("if not _marked_items:"))]
check("_push_webhook_event" not in _i_push,
      "0 行分支内不 push 失效事件")

# ─────────────────────────────────────────────
print("\n[T3] P2-04：清理返回实际行数；SQL 失败 → -1")
# ─────────────────────────────────────────────
_spec = importlib.util.spec_from_file_location("epl_dbh479", str(PLUGIN_DIR / "db.py"))
_db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_db)
_db.PeopleDb.ensure_table()
_pdb = _db.PeopleDb()
PID = "EmbyPeopleLocalizeProbe479H"
_pdb.delete_item(plugin_id=PID, item_id="X1", server_id=None)
_now = time.time()
for _i in range(3):
    _db._x("INSERT INTO person (plugin_id, server_id, item_id, item_type, season_num, episode_num, "
           "person_index, name_before, name_after, deleted_at) VALUES (?,?,?,?,1,1,?,?,?,?)",
           (PID, "srv", "X1", "Episode", _i, f"n{_i}", f"n{_i}", str(_now - 7200.0)))
check(int(_pdb.purge_expired(plugin_id=PID, grace_hours=1) or 0) == 3,
      "purge_expired 返回**实际删除行数**")
_orig_x = _db._x
_db._x = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
try:
    _r = _pdb.purge_expired(plugin_id=PID, grace_hours=1)
finally:
    _db._x = _orig_x
check(_r == -1, f"purge_expired SQL 失败 → -1（不再返回 0 谎报成功），实际 {_r}")
_orig_q = _db._q
_db._q = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
try:
    _r2 = _pdb.expired_item_ids(plugin_id=PID, grace_hours=1)
finally:
    _db._q = _orig_q
check(_r2 is None, f"expired_item_ids SQL 失败 → None（区别于「没有过期条目」），实际 {_r2!r}")
check("_purged < 0" in _mp and "_purged == 0" in _mp,
      "维护：失败(负)/0 行 与 成功 分别处理（不谎报已清理）")
check("_purged2 < 0" in _SRC and "本次不隐藏记录" in _SRC,
      "洗版清理：失败时不隐藏记录、不报成功（验收 G）")

# ─────────────────────────────────────────────
print("\n[T4] P2-01：观察期解析尊重显式 0")
# ─────────────────────────────────────────────
_nsG = {"logger": logger}
exec(_grab_method(_SRC, "_nfo_grace_hours"), _nsG)


class _GH:
    _nfo_grace_hours = _nsG["_nfo_grace_hours"]

    def __init__(self, v):
        self._nfo_dead_grace_hours = v


check(_GH(0)._nfo_grace_hours() == 0.0, "配置 0 → 0.0（此前被 `or 24` 偷偷换成 24）")
check(_GH(24)._nfo_grace_hours() == 24.0, "配置 24 → 24.0")
check(_GH(None)._nfo_grace_hours() == 24.0, "None（非法值）→ 回退 24")
check(_GH("")._nfo_grace_hours() == 24.0, "空串（非法值）→ 回退 24")
check(_db._grace_secs(0) == 0.0 and _db._grace_secs(None) == 24 * 3600.0,
      "db._grace_secs：0 → 0s；None → 24h")
check('or 24)' not in _SRC.split("def _nfo_grace_hours")[0].split("def _all_nfo_roots")[-1],
      "_all_nfo_roots 之后不再残留 `... or 24` 的观察期写法")

# ─────────────────────────────────────────────
print("\n[T5] P1-05：探测未完整不更新 last_deep（源码级）")
# ─────────────────────────────────────────────
_pr = _grab_method(_SRC, "_run_probe_round")
check("_probe_complete" in _pr, "探测：先算「本轮是否完整」再决定是否刷新 last_deep")
_pc = _pr[_pr.index("_probe_complete = ("):_pr.index("_probe_complete = (") + 400]
check('res.get("rest")' in _pc, "完整性判定含「剩余目标 = 0」")
check('inventory.get("incomplete")' in _pc, "完整性判定含「清单完整」")
check("if _probe_complete:" in _pr and "_probe_last_deep = time.time()" in _pr
      and _pr.index("if _probe_complete:") < _pr.index("_probe_last_deep = time.time()"),
      "只有完整轮才刷新 `_probe_last_deep`")

# ─────────────────────────────────────────────
print("\n[T6] P1-08：定时扫描先启动成功再写时间戳")
# ─────────────────────────────────────────────
_nsS = {"logger": logger, "time": time, "threading": threading}
exec(_grab_method(_SRC, "_run_scheduled_scan"), _nsS)


class _SchedSelf:
    _run_scheduled_scan = _nsS["_run_scheduled_scan"]

    def __init__(self, launch=None):
        self._schedule_interval_hours = 24
        self._last_full_scan_ts = 0.0
        self._scan_lock = threading.RLock()
        self._is_running = False
        self._launch = launch
        self.saved = 0
        self.logs = []

    def _all_nfo_roots(self):
        return ["X:/lib"]

    def _launch_nfo_worker(self, body):
        if isinstance(self._launch, Exception):
            raise self._launch
        return self._launch

    def _save_state(self):
        self.saved += 1

    def _push_log(self, lvl, msg):
        self.logs.append((lvl, msg))


_s1 = _SchedSelf(launch=RuntimeError("thread start failed"))
_s1._run_scheduled_scan()
check(_s1._last_full_scan_ts == 0.0, "启动抛异常 → 不写「上次执行」（下一轮重试）")
_s2 = _SchedSelf(launch={"success": False, "message": "已有任务正在运行"})
_s2._run_scheduled_scan()
check(_s2._last_full_scan_ts == 0.0, "被互斥挡住（返回错误）→ 不写「上次执行」")
_s3 = _SchedSelf(launch=None)
_s3._run_scheduled_scan()
check(_s3._last_full_scan_ts > 0 and _s3.saved == 1, "启动成功 → 才写「上次执行」并落盘")

# ─────────────────────────────────────────────
print("\n[T7] P1-07：任务状态读取异常 → fail-closed")
# ─────────────────────────────────────────────
_nsB = {"logger": logger, "threading": threading, "Optional": __import__("typing").Optional}
exec(_grab_method(_SRC, "_task_busy_msg"), _nsB)


class _BusySelf:
    _task_busy_msg = _nsB["_task_busy_msg"]

    def __init__(self, boom=False, state=None):
        self._scan_lock = threading.RLock()
        self._is_running = False
        self._tx_requested = False
        self._boom = boom
        self._state = state

    def _task_state(self):
        if self._boom:
            raise RuntimeError("boom")
        return self._state


check(_BusySelf(boom=True)._task_busy_msg() is not None,
      "状态查询抛异常 → 拒绝（fail-closed），不再放行冲突写操作")
check("状态读取异常" in str((_BusySelf(boom=True)._task_busy_msg() or {}).get("message") or ""),
      "异常时给出明确文案（提示稍后重试/重启）")
check(_BusySelf(state={"state": "UNKNOWN", "data_mutation_locked": True})._task_busy_msg() is not None,
      "state=UNKNOWN → 同样按忙碌拦截")
check(_BusySelf(state={"state": "IDLE", "data_mutation_locked": False})._task_busy_msg() is None,
      "正常空闲 → 放行（不误伤）")
check('"state": "UNKNOWN"' in _grab_method(_SRC, "_task_state"),
      "_task_state 异常时返回 state=UNKNOWN（不再伪装 IDLE）")

# ─────────────────────────────────────────────
print("\n[T8] P1-04：延迟队列持久化 added_count")
# ─────────────────────────────────────────────
_ser = _grab_method(_SRC, "_serialize_webhook_schedule")
check('"added_count"' in _ser, "序列化时带上 added_count")
_ls = _grab_method(_SRC, "_load_state")
check('"added_count": int(_v.get("added_count") or 0)' in _ls,
      "载入 state 时还原 added_count（重启后「整剧新增」判定不变）")

# ─────────────────────────────────────────────
print("\n[T9] P1-02：写回进行中来的登记不再被丢弃（写回代数）")
# ─────────────────────────────────────────────
_reg = _grab_method(_SRC, "_wb_register_item")
check('== "writing"' not in _reg,
      "不再有「status==writing → skip」早退（恢复登记不再被静默丢弃）")
check('reason=str(reason or "")' in _reg, "登记照常落到 db.register（由其累积新一代）")
_wpr = _grab_method(_SRC, "_wb_process_item_locked")
check('_claimed_gen = int(rec.get("gen") or 0)' in _wpr, "写回轮认领时记下代数 gen")
check("claimed_gen=_claimed_gen" in _wpr and "wdb.finish(" in _wpr, "收尾走 finish(claimed_gen=...)")
_dbw = (PLUGIN_DIR / "db.py").read_text(encoding="utf-8")
check("def finish(" in _dbw and "gen=writeback_state.gen+1" in _dbw,
      "db.finish + register 递增代数")
check("def clear_restore(" not in _dbw, "已移除 clear_restore（清回由 finish 原子完成）")
check("_WRITEBACK_V17_COLUMNS" in _dbw and _db.SCHEMA_VERSION >= 17,
      f"schema v17 迁移补 gen（实际 {_db.SCHEMA_VERSION}）")

# ─────────────────────────────────────────────
print("\n[T10] P1-03：Webhook 事件按 (server_id, item_id) 定位")
# ─────────────────────────────────────────────
_nsU = {"logger": logger, "Optional": __import__("typing").Optional}
exec(_grab_method(_SRC, "_update_or_push_webhook_event"), _nsU)


class _EvSelf:
    _update_or_push_webhook_event = _nsU["_update_or_push_webhook_event"]

    def __init__(self, events):
        self._webhook_events = events
        self.saved = 0
        self.pushed = []

    def _save_state(self):
        self.saved += 1

    def _push_webhook_event(self, item_id, name, status, msg, series_name="", season=None,
                            episode=None, server_id=""):
        self.pushed.append({"item_id": item_id, "status": status, "server_id": server_id})


_evs = [{"item_id": "100", "status": "received", "server_id": "A", "msg": "x"},
        {"item_id": "100", "status": "received", "server_id": "B", "msg": "x"}]
_sA = _EvSelf([dict(e) for e in _evs])
_sA._update_or_push_webhook_event("100", "n", "done", "ok", server_id="A")
check(str(_sA._webhook_events[0]["status"]) == "done"
      and str(_sA._webhook_events[1]["status"]) == "received",
      "只更新 A 服务器的行，不动 B 服务器（此前只比 item_id 会串台）")
check(_sA.pushed == [], "命中已有行 → 不另起新行")
_sC = _EvSelf([dict(e) for e in _evs])
_sC._update_or_push_webhook_event("100", "n", "done", "ok", server_id="C")
check(bool(_sC.pushed) and str(_sC.pushed[0]["server_id"]) == "C",
      "没有该服务器的事件行 → 新起一行且带 server_id")
_evh = {"item_id": "9", "status": "received", "server_id": "", "msg": "x"}
_sD = _EvSelf([_evh])
_sD._update_or_push_webhook_event("9", "n", "done", "ok", server_id="A")
check(str(_sD._webhook_events[0].get("server_id") or "") == "A",
      "历史行（无 server_id）被命中时补齐 server_id（向后兼容）")
check('server_id=str(_mm.get("server_id") or "")' in _grab_method(_SRC, "_webhook_worker"),
      "worker 更新事件时带 server_id")
check('server_id=str(server_id or "")' in _grab_method(_SRC, "handle_webhook"),
      "「已接收」事件带 server_id")
check('schedule_key = f"{server_id}:{item_id}"' in _grab_method(_SRC, "handle_webhook"),
      "延迟队列键按 server:item 隔离（不跨服务器串队）")

# ─────────────────────────────────────────────
print("\n[T11] P1-04：插件未启用时保留队列（pause 语义）")
# ─────────────────────────────────────────────
_wk = _grab_method(_SRC, "_webhook_worker")
check("_webhook_schedule.clear()" not in _wk, "不再静默丢弃未处理事件")
check("暂存" in _wk and "_save_state()" in _wk, "改为暂存 + 落盘（重新启用后续跑）")
check("_resume_webhook_queue" in _SRC and "保留内存" in _SRC,
      "与 _resume_webhook_queue 的「保留不消费」语义一致")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
