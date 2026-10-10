# -*- coding: utf-8 -*-
"""v4.6.73 批次 4 回归测试：文件锁 + 原子写回复读校验 + 条目级互斥 + 统一任务状态机。
（报告第十二 / 十五 / 十六节 + 十九节测试 10）

运行：python tests/test_v473_batch4_filelock_taskstate.py

覆盖：
  T1 nfo.file_lock：同路径同一把锁（大小写/分隔符归一）、不同路径不同锁、可重入
  T2 条目级互斥：_item_enter/_item_busy/_item_leave 语义（忙/闲、其它条目不受影响）
  T3 _wb_process_item 用条目锁包装（忙则跳过）
  T4 _task_state 统一状态机（优先级） + data_mutation_locked
  T5 _restore_nfo_from_db 文件锁包装（真实现 _restore_nfo_from_db_locked）
  T6 写回后复读校验（verified）
  T7 /translate/jobs/create 条目级互斥门禁
  T8 /pool/status 与仪表盘状态含 task_state
  T9 前端 TaskGuard 消费 task_state（useTaskGuard / TaskGuardDlg / 两视图）
  T10 真实原子写回：tmp + os.replace 后文件内容正确（nfo.save 集成）
"""
import sys
import os
import re
import types
import tempfile
import importlib.util
from pathlib import Path
from typing import Any, List, Optional, Dict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent

class _Logger:
    def debug(self, msg, *a, **k):
        if os.environ.get("EPL_DBG"):
            print(f"    [dbg] {msg}")
    def info(self, *a, **k): pass
    def warning(self, msg, *a, **k):
        if os.environ.get("EPL_DBG"):
            print(f"    [warn] {msg}")
    def error(self, *a, **k): pass
    def log(self, *a, **k): pass

logger = _Logger()
_mod_app = types.ModuleType("app")
_mod_sdk = types.ModuleType("app.sdk")
_mod_log = types.ModuleType("app.sdk.logging")
_mod_log.logger = logger
sys.modules.update({"app": _mod_app, "app.sdk": _mod_sdk, "app.sdk.logging": _mod_log})

_spec = importlib.util.spec_from_file_location("epl_nfo73", PLUGIN_DIR / "nfo.py")
nfo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nfo)

_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")

def _grab(name: str) -> str:
    m = re.search(rf"^    def {re.escape(name)}\(", _SRC, re.M)
    assert m, f"未找到方法 {name}"
    lines = _SRC[m.start():].splitlines()
    out = [lines[0]]
    for ln in lines[1:]:
        if ln.strip() == "":
            out.append(ln); continue
        if re.match(r"^    \S", ln):
            break
        out.append(ln)
    pre = []
    _head = _SRC[:m.start()].rstrip("\n").splitlines()
    while _head and re.match(r"^    @", _head[-1]):
        pre.insert(0, _head.pop())
    return "\n".join(pre + out)

def _mk_cls(cls_name, methods):
    import threading
    ns = {
        "logger": logger, "re": re, "os": os, "Any": Any, "List": List,
        "Optional": Optional, "Dict": Dict, "tuple": tuple, "set": set,
        "threading": threading, "Exception": Exception,
        "int": int, "str": str, "bool": bool, "len": len,
    }
    src = f"class {cls_name}:\n" + "\n".join(_grab(n) for n in methods)
    exec(compile(src, "<extract:__init__.py>", "exec"), ns)
    return ns[cls_name]

_N = [0, 0]
def check(cond, msg):
    _N[0] += 1
    if cond:
        print(f"  [PASS] {msg}")
    else:
        _N[1] += 1
        print(f"  [FAIL] {msg}")

print("=" * 72)
print("v4.6.73 批次4 回归测试（文件锁 / 条目互斥 / 任务状态机）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] nfo.file_lock：同路径同一把锁、不同路径不同锁、可重入")
# ─────────────────────────────────────────────
_a = nfo.file_lock("X:/Dir/A.nfo")
_b = nfo.file_lock("x:\\dir\\a.nfo")     # 大小写/分隔符归一 → 同一把
_c = nfo.file_lock("X:/Dir/B.nfo")
check(_a is _b, "同路径（大小写/分隔符归一）返回同一把锁")
check(_a is not _c, "不同路径返回不同锁")
check(hasattr(_a, "acquire") and hasattr(_a, "release"), "返回可 with 的锁对象")
_re = _a.acquire(blocking=False); _a.acquire(blocking=False); _a.release(); _a.release()
check(_re is True, "可重入（同线程多次 acquire 不阻塞）")

# ─────────────────────────────────────────────
print("\n[T2] 条目级互斥：enter/busy/leave")
# ─────────────────────────────────────────────
CLS = _mk_cls("EPL73I", ["_item_lock", "_item_enter", "_item_leave", "_item_busy"])
p = CLS()
check(p._item_busy("S1", "100") is False, "初始不忙")
p._item_enter("S1", "100")
check(p._item_busy("S1", "100") is True, "enter 后条目忙")
check(p._item_busy("S1", "200") is False, "同服务器其它条目不受影响")
check(p._item_busy("S2", "100") is False, "其它服务器同 item 不受影响")
p._item_leave("S1", "100")
check(p._item_busy("S1", "100") is False, "leave 后恢复空闲")

# ─────────────────────────────────────────────
print("\n[T3] _wb_process_item 用条目锁包装")
# ─────────────────────────────────────────────
_body = _grab("_wb_process_item")
check("_item_busy" in _body and "_item_enter" in _body and "_item_leave" in _body,
      "写回单条目先查忙、进入/退出条目锁")
check("_wb_process_item_locked" in _body, "真实现拆到 _wb_process_item_locked")
check("_item_leave" in _body and "finally" in _body, "finally 中释放条目锁（异常也释放）")

# ─────────────────────────────────────────────
print("\n[T4] _task_state 统一状态机（优先级）")
# ─────────────────────────────────────────────
ST = _mk_cls("EPL73S", ["_task_state", "_clear_transient_stop_bits"])   # v4.6.108：停止位自愈依赖它
s = ST()
s._task_running = lambda k: {"scan": True, "translate": True, "writeback": True}.get(k, False)
s._stop_requested = False
s._wb_stop = False
s._pool_pulling = False
check(s._task_state()["state"] == "WRITING", "写回中优先于翻译/扫描 → WRITING")
s._task_running = lambda k: {"scan": True, "translate": True}.get(k, False)
check(s._task_state()["state"] == "TRANSLATING", "翻译中优先于扫描 → TRANSLATING")
s._task_running = lambda k: (k == "scan")
check(s._task_state()["state"] == "SCANNING", "仅扫描 → SCANNING")
s._task_running = lambda k: (k == "probe")
check(s._task_state()["state"] == "PROBING", "仅探测库 → PROBING")
s._task_running = lambda k: False
s._pool_pulling = True
check(s._task_state()["state"] == "POOL_FETCHING", "拉取人名中 → POOL_FETCHING")
s._pool_pulling = False
s._task_running = lambda k: (k == "pool")
check(s._task_state()["state"] == "POOL_SYNCING", "人名池同步中 → POOL_SYNCING")
s._task_running = lambda k: False
_st = s._task_state()
check(_st["state"] == "IDLE" and _st["data_mutation_locked"] is False,
      "空闲 → IDLE 且不锁数据变更")
# v4.6.108（LIB-015）：停止位只表示「请当前这轮停下来」——
# **仍在跑 / 翻译许可未归还**时才是 STOPPING；已全部停完则自愈回 IDLE
# （此前会永久卡在 STOPPING → data_mutation_locked 恒为 True → 所有启动/改数据操作被锁死，
#   只有重启插件才能恢复；用户实测 17:03:03 终止 → 17:03:29 保存仍判「任务运行中」）。
s._task_running = lambda k: (k == "pool")
s._stop_requested = True
check(s._task_state()["state"] == "STOPPING", "停止位 + 仍有任务在跑 → STOPPING（优先）")
s._task_running = lambda k: False
s._tx_requested = True
check(s._task_state()["state"] == "STOPPING", "停止位 + 翻译许可未归还 → 仍 STOPPING（不丢停止请求）")
s._tx_requested = False
check(s._task_state()["state"] == "IDLE",
      "已全部停完 → 自愈回 IDLE（不再永久卡 STOPPING，无需重启插件）")
s._stop_requested = False
s._task_running = lambda k: (k == "writeback")
check(s._task_state()["data_mutation_locked"] is True, "非 IDLE → data_mutation_locked=True")

# ─────────────────────────────────────────────
print("\n[T5] _restore_nfo_from_db 文件锁包装")
# ─────────────────────────────────────────────
_w = _grab("_restore_nfo_from_db")
check("file_lock(nfo_path)" in _w and "_restore_nfo_from_db_locked" in _w,
      "落盘入口用 file_lock 包裹真实现（同文件读改写串行）")
check(re.search(r"^    def _restore_nfo_from_db_locked\(", _SRC, re.M) is not None,
      "真实现 _restore_nfo_from_db_locked 存在")

# ─────────────────────────────────────────────
print("\n[T6] 写回后复读校验（verified）")
# ─────────────────────────────────────────────
_lk = _grab("_restore_nfo_from_db_locked")
check("复读校验" in _lk and "parse_nfo(nfo_path) is not None" in _lk,
      "写回后重新 parse 校验文件可读")
check('"verified": _verified' in _lk, "结果 data 带 verified 字段")

# ─────────────────────────────────────────────
print("\n[T7] /translate/jobs/create 条目级互斥门禁")
# ─────────────────────────────────────────────
_jc = _grab("_api_translate_job_create")
check("_item_busy" in _jc and "同一条目互斥" in _jc, "条目忙 → 拒绝创建重翻 Job")

# ─────────────────────────────────────────────
print("\n[T8] 状态端点含 task_state")
# ─────────────────────────────────────────────
check('"task_state": self._task_state()' in _SRC
      and _SRC.count('"task_state": self._task_state()') >= 2,
      "/pool/status 与仪表盘状态都附 task_state")

# ─────────────────────────────────────────────
print("\n[T9] 前端 TaskGuard 消费 task_state")
# ─────────────────────────────────────────────
_js = (PLUGIN_DIR / "src/components/useTaskGuard.js").read_text(encoding="utf-8")
check("STATE_LABEL" in _js and "task_state" in _js and "data_mutation_locked" in _js,
      "useTaskGuard 读 task_state / data_mutation_locked 并映射中文状态")
check("stateLabel" in _js, "暴露 stateLabel")
_vue = (PLUGIN_DIR / "src/components/TaskGuardDlg.vue").read_text(encoding="utf-8")
check("state:" in _vue and "props.state" in _vue, "TaskGuardDlg 有 state 属性并展示")
for _f in ("src/views/LibraryView.vue", "src/views/PeoplePoolView.vue"):
    _t = (PLUGIN_DIR / _f).read_text(encoding="utf-8")
    check(':state="guard.stateLabel.value"' in _t, f"{_f} 传入 :state")

# ─────────────────────────────────────────────
print("\n[T10] 真实原子写回：apply → save → 文件内容正确")
# ─────────────────────────────────────────────
_td = Path(tempfile.mkdtemp(prefix="epl73nfo_"))
_nf = _td / "movie.nfo"
_nf.write_text(
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<movie><title>T</title>'
    '<actor><name>Tom Hanks</name><role>Forrest</role></actor></movie>',
    encoding="utf-8")
doc = nfo.parse_nfo(str(_nf))
check(doc is not None, "解析测试 nfo")
_ok = doc.save(backup=False, dry_run=False)
check(_ok is True, "save 返回成功")
_txt = _nf.read_text(encoding="utf-8")
check("汤姆·汉克斯" not in _txt, "写入前无译文（基线）")
doc.apply({"Tom Hanks": "汤姆·汉克斯"}, {"Forrest": "阿甘"})
_ok2 = doc.save(backup=False, dry_run=False)
_txt2 = _nf.read_text(encoding="utf-8")
check(_ok2 and "汤姆·汉克斯" in _txt2 and "阿甘" in _txt2,
      "apply + save 后译文写入文件（tmp + os.replace 原子落盘）")
check(not os.path.exists(str(_nf) + ".tmp"), "临时文件已被 os.replace 清理")
check(nfo.parse_nfo(str(_nf)) is not None, "写回后文件仍可正常解析（复读校验通过）")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
