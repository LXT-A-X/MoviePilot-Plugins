# -*- coding: utf-8 -*-
"""v4.6.104 回归测试：库页左侧「每次刷新都拉一下 / 分库刷新了又退、又没有」+ 有更新才刷新。

运行：python tests/test_v4104_library_poll_merge.py

用户实测（库内 360 条目，4 个分库）：
  ①每次刷新「页面会拉一下、会加载一下」；
  ②「刷新完就一直停到第一个库，另外几个刷新了又退，刷新了又没有」；
  ③诉求：「如果有数据更新的话再刷新，没数据更新的话干嘛要刷新？」

根因：loadItems 固定 limit=100/offset=0 且无条件 items.value = list ——
  分页窗口被丢弃、列表塌回第 1 页；而分库分组按条数排序，落在第 1 页之外的分库
  （服务器1·电视剧 / 服务器1·电影 等）在每轮刷新后整组消失，下一轮哨兵补页又出现。
现修法：①按当前窗口请求 ②按 key 原地合并（保留对象引用与顺序）③内容等价则跳过赋值
        ④列表改为事件驱动：/status 带回 items_rev，只有版本号变化才重拉。

覆盖：
  T1 行为级（Node）：_mergeItems 保留对象引用 / 原地改字段 / 追加 / 移除
  T2 行为级（Node）：内容等价 → 完全不赋值（不触发渲染）
  T3 行为级（Node）：窗口保持 300 条不再塌回第一页（分库不再消失）
  T4 源码级：列表事件驱动（无 listTimer，轮询体不直接拉列表，后台不轮询）
  T5 行为级（Node）：loadStatus 按 items_rev 变化才触发 loadItems
  T6 行为级（真 SQLite）：db_rev 只在 person 表写入时自增
  T7 源码级：/status 下发 items_rev
"""
import re
import sys
import time
import types
import tempfile
import subprocess
import importlib.util
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl104_"))
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
_VUE = (PLUGIN_DIR / "src/views/LibraryView.vue").read_text(encoding="utf-8")
_DB = (PLUGIN_DIR / "db.py").read_text(encoding="utf-8")

_N = [0, 0]


def check(cond, msg):
    _N[0] += 1
    if cond:
        print(f"  [PASS] {msg}")
    else:
        _N[1] += 1
        print(f"  [FAIL] {msg}")


class _Logger:
    def debug(self, *a, **k): pass
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass
    def log(self, *a, **k): pass


logger = _Logger()

# ── 桩：宿主 app.* 模块 ──
_m = types.ModuleType("app")
_sdk = types.ModuleType("app.sdk")
_lg = types.ModuleType("app.sdk.logging"); _lg.logger = logger
_cfg = types.ModuleType("app.sdk.config")
class _Settings:
    CONFIG_PATH = str(TMP)
    TMDB_LOCALE = "zh-CN"
_cfg.settings = _Settings()
_chain = types.ModuleType("app.chain")
_tmdbmod = types.ModuleType("app.chain.tmdb")
class _FakeChain:
    def person_detail(self, pid): return None
_tmdbmod.TmdbChain = _FakeChain
_tmw = types.ModuleType("app.modules")
_tmwdb = types.ModuleType("app.modules.themoviedb")
_tmwapi = types.ModuleType("app.modules.themoviedb.tmdbapi")
class _FakeTmdbApi:
    def __init__(self, **k): pass
    def get_person_detail(self, tid): return {}
_tmwapi.TmdbApi = _FakeTmdbApi
sys.modules.update({
    "app": _m, "app.sdk": _sdk, "app.sdk.logging": _lg, "app.sdk.config": _cfg,
    "app.chain": _chain, "app.chain.tmdb": _tmdbmod,
    "app.modules": _tmw, "app.modules.themoviedb": _tmwdb,
    "app.modules.themoviedb.tmdbapi": _tmwapi,
})

# ── 真 db.py ──
_spec = importlib.util.spec_from_file_location("epl104_db", PLUGIN_DIR / "db.py")
dbm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dbm)


def _grab_method(src, name):
    mm = re.search(rf"^([ \t]*)def {re.escape(name)}\(", src, re.M)
    assert mm, f"未找到 {name}"
    indent = len(mm.group(1))
    lines = src[mm.start():].splitlines()
    out = [lines[0]]
    for ln in lines[1:]:
        if ln.strip() == "":
            out.append(ln)
            continue
        if re.match(rf"^ {{{indent}}}\S", ln):
            break
        out.append(ln)
    _head = src[:mm.start()].rstrip("\n").splitlines()
    pre = []
    while _head and re.match(r"^[ \t]*@", _head[-1]):
        pre.insert(0, _head.pop())
    return "\n".join(pre + out)


def _node_run(js):
    _node = None
    for _cand in (r"C:\node-v22.14.0-win-x64\node.exe", "node"):
        try:
            subprocess.run([_cand, "-v"], capture_output=True, timeout=15)
            _node = _cand
            break
        except Exception:
            continue
    if not _node:
        print("  [SKIP] 未找到 node")
        return None
    _tf = Path(tempfile.mkdtemp(prefix="epl104n_")) / "t.mjs"
    _tf.write_text(js, encoding="utf-8")
    _r = subprocess.run([_node, str(_tf)], capture_output=True, timeout=60)
    return (_r.stdout or b"").decode("utf-8", "replace") + (_r.stderr or b"").decode("utf-8", "replace")


def _report(out, tag):
    if out is None:
        return
    for _ln in out.splitlines():
        if _ln.startswith("PASS "):
            check(True, _ln[5:])
        elif _ln.startswith("FAIL "):
            check(False, _ln[5:])
    _jf = re.search(r"JS_FAIL=(\d+)", out)
    check(bool(_jf) and int(_jf.group(1)) == 0,
          f"{tag} 行为级全部通过" + ("" if (_jf and int(_jf.group(1)) == 0) else "\n" + out))


print("=" * 72)
print("v4.6.104 回归测试（左侧列表 原地合并 / 有更新才刷新）")
print("=" * 72)

# ── 提取前端 loadItems 区块（含 _itemSig/_itemsSame/_mergeItems）──
_i = _VUE.index("function _normItems(resp)")
_j = _VUE.index("\n// 滚动到底部自动追加下一页", _i)
_js_block = _VUE[_i:_j]
check("_mergeItems" in _js_block and "_itemsSame" in _js_block, "已提取到 原地合并 / 等价判定 辅助函数")

_HARNESS = """
const loadingList = { value: false }
const items = { value: [] }
const itemHasMore = { value: false }
const props = { api: {} }
const ITEM_PAGE_SIZE = 100
const itemKey = (it) => (it ? `${it.server_id || ''}:${it.item_id || ''}` : '')
let itemsSeq = 0
let LIMITS = []
let NEXT = { items: [], total: 0, has_more: false }
const api = { get: async (a, url, params) => { LIMITS.push(params.limit); return NEXT } }
function notify() {}
let n = 0, f = 0
function chk (c, m) { n++; if (c) console.log('PASS ' + m); else { f++; console.log('FAIL ' + m) } }
function mk (id, pc) { return { server_id: 's', item_id: id, title: 'T' + id, item_type: 'Movie', person_count: pc || 1 } }
"""

# ─────────────────────────────────────────────
print("\n[T1] 行为级（Node）：_mergeItems —— 保留引用 / 原地改字段 / 追加 / 移除")
# ─────────────────────────────────────────────
_t1 = _js_block + _HARNESS + """
const o1 = mk('a', 1), o2 = mk('b', 2), o3 = mk('c', 3)
items.value = [o1, o2, o3]
NEXT = { items: [mk('a', 1), mk('b', 9), mk('c', 3), mk('d', 4)], total: 4, has_more: false }
await loadItems(true)
chk(items.value.length === 4, '合并后长度 4，实际 ' + items.value.length)
chk(items.value[0] === o1, '未变化的条目保留原对象引用（该行不重建）')
chk(items.value[1] === o2 && o2.person_count === 9, '变化的条目原地更新字段、引用不变')
chk(items.value[2] === o3, '第三条引用不变')
chk(items.value[3] && items.value[3].item_id === 'd', '新条目追加到末尾（顺序不重排）')
NEXT = { items: [mk('a', 1)], total: 1, has_more: false }
await loadItems(true)
chk(items.value.length === 1 && items.value[0] === o1, '服务端已消失的条目被移除，其余引用保留')
console.log('JS_TOTAL=' + n); console.log('JS_FAIL=' + f)
"""
_report(_node_run(_t1), "T1")

# ─────────────────────────────────────────────
print("\n[T2] 行为级（Node）：内容等价 → 完全不赋值（不触发渲染）")
# ─────────────────────────────────────────────
_t2 = _js_block + _HARNESS + """
const o1 = mk('a', 1), o2 = mk('b', 2)
items.value = [o1, o2]
const arrBefore = items.value
NEXT = { items: [mk('a', 1), mk('b', 2)], total: 2, has_more: false }   // 新对象、内容等价
await loadItems(true)
chk(items.value === arrBefore, '内容等价 → 数组引用不变（连 computed 都不触发）')
chk(items.value[0] === o1 && items.value[1] === o2, '条目对象引用也不变')
NEXT = { items: [mk('a', 1), mk('b', 2)], total: 2, has_more: true }
await loadItems(true)
chk(itemHasMore.value === true, '等价跳过时仍同步 hasMore（不丢状态）')
console.log('JS_TOTAL=' + n); console.log('JS_FAIL=' + f)
"""
_report(_node_run(_t2), "T2")

# ─────────────────────────────────────────────
print("\n[T3] 行为级（Node）：窗口保持 300 条，不再塌回第一页（分库不再消失）")
# ─────────────────────────────────────────────
_t3 = _js_block + _HARNESS + """
const ALL = []
for (let i = 0; i < 300; i++) ALL.push(mk('i' + i, 1))
items.value = ALL.slice()          // 模拟用户已滚动加载 3 页
const arrBefore = items.value
LIMITS = []
NEXT = { items: ALL.map((x) => ({ ...x })), total: 300, has_more: false }
await loadItems(true)
chk(LIMITS[0] === 300, '按当前窗口大小请求（300），不再固定拉第 1 页 100 条，实际 ' + LIMITS[0])
chk(items.value.length === 300, '列表不再塌回 100 条，实际 ' + items.value.length)
chk(items.value === arrBefore, '内容等价 → 连赋值都跳过')
// 真有变化时同样不许塌陷
LIMITS = []
NEXT = { items: ALL.map((x) => ({ ...x })), total: 300, has_more: false }
NEXT.items[0] = mk('i0', 99)
await loadItems(true)
chk(LIMITS[0] === 300, '有变化时仍按 300 请求，实际 ' + LIMITS[0])
chk(items.value.length === 300, '有变化时列表仍是 300 条（不塌回第一页）')
// v4.6.104（LIB-010）：窗口不完整（本次只取回一部分、total 仍更大）→ 已加载条目一个都不能丢。
// 这是「分库刷新了又退、又没有」的最后一道防线：列表按 translated_at 倒序，翻译一发生顺序就变，
// 上一窗口里的条目会落到新窗口之外，若无条件按 next 裁剪就会把它们删掉。
items.value = ALL.slice()          // 用户已滚动加载 300 条
NEXT = { items: ALL.slice(0, 100).map((x) => ({ ...x })), total: 300, has_more: true }
await loadItems(true)
chk(items.value.length === 300, '窗口不完整 → 不删已加载条目（分库不会整组消失），实际 ' + items.value.length)
chk(items.value.some((x) => x.item_id === 'i299'), '原本在末尾的条目仍在（没被窗口裁掉）')
console.log('JS_TOTAL=' + n); console.log('JS_FAIL=' + f)
"""
_report(_node_run(_t3), "T3")

# ─────────────────────────────────────────────
print("\n[T4] 源码级：列表事件驱动（无 listTimer、轮询体不直接拉列表、后台不轮询）")
# ─────────────────────────────────────────────
check("listTimer" not in _VUE, "已删除按固定周期拉列表的 listTimer（改为 items_rev 事件驱动）")
check("_lastItemsRev" in _VUE, "有 _lastItemsRev 版本号记忆变量")
_poll_body = _VUE[_VUE.index("pollTimer = setInterval("):]
_poll_body = _poll_body[:_poll_body.index("}, FAST_POLL_MS)")]
check("loadItems" not in _poll_body, "8s 轮询体内不再直接拉列表（改由 items_rev 变更触发）")
check("if (document.hidden) return" in _VUE, "页面在后台不轮询")
check("document.addEventListener('visibilitychange', _onDocVisible)" in _VUE,
      "切回前台立即补一次（visibilitychange）")
check("document.removeEventListener('visibilitychange', _onDocVisible)" in _VUE,
      "卸载时移除 visibilitychange 监听（不泄漏）")
# v4.6.104（LIB-010）：窗口不完整时不允许删除已加载条目
check("const _complete = list.length >= total" in _VUE,
      "以「本次是否拉全」判定能否安全删除（list.length >= total）")
check("_mergeItems(items.value, list, _complete)" in _VUE,
      "把「是否拉全」传给 _mergeItems（不完整窗口只增改不删）")

# ─────────────────────────────────────────────
print("\n[T5] 行为级（Node）：loadStatus 按 items_rev 变化才触发 loadItems")
# ─────────────────────────────────────────────
_k = _VUE.index("async function loadStatus() {")
_e = _VUE.index("\n}\n", _k) + 3
_ls_block = _VUE[_k:_e]
_t5 = _ls_block + """
let _lastItemsRev = null
let _wasTaskRunning = false
const autoWriteback = { value: false }
const pendingDlg = { value: false }
const props = { api: {} }
let REV = '1'
let LIST_CALLS = 0
const api = { get: async () => ({ items_rev: REV, auto_writeback: false, tasks: {} }) }
const guard = { loadStatus: () => {} }
function refreshDetailSoft () {}
function loadTxPreview () {}
function loadItems () { LIST_CALLS++ }
function loadPendingDetail () {}
let n = 0, f = 0
function chk (c, m) { n++; if (c) console.log('PASS ' + m); else { f++; console.log('FAIL ' + m) } }
await loadStatus()
chk(LIST_CALLS === 0, '首帧只记版本号，不重复拉列表（startPoll 已拉过），实际 ' + LIST_CALLS)
await loadStatus()
chk(LIST_CALLS === 0, '版本号没变 → 一个字节都不重拉，实际 ' + LIST_CALLS)
REV = '2'
await loadStatus()
chk(LIST_CALLS === 1, '版本号变了 → 立刻拉一次列表，实际 ' + LIST_CALLS)
await loadStatus()
chk(LIST_CALLS === 1, '版本号没变 → 不再拉，实际 ' + LIST_CALLS)
REV = '3'
await loadStatus()
chk(LIST_CALLS === 2, '再次变化 → 再拉一次，实际 ' + LIST_CALLS)
console.log('JS_TOTAL=' + n); console.log('JS_FAIL=' + f)
"""
_report(_node_run(_t5), "T5")

# ─────────────────────────────────────────────
print("\n[T6] 行为级（真 SQLite）：db_rev 只在 person 表写入时自增")
# ─────────────────────────────────────────────
pdb = dbm.PeopleDb()
pdb.ensure_table()
_pid = "EmbyPeopleLocalize"
_r0 = dbm.db_rev()
pdb.upsert_people(plugin_id=_pid, server_id="s1", item_id="tvdb:1", item_type="Series",
                  title="剧", series_name="剧", season_num=None, episode_num=None,
                  nfo_path="/x/tvshow.nfo", emby_item_id="1",
                  people=[{"before_name": "Kana Hanazawa", "Name": "花泽香菜",
                           "before_role": "Actor", "Role": "Actor", "Type": "Actor"}])
_r1 = dbm.db_rev()
check(_r1 > _r0, f"upsert_people（批量写 person）→ 版本号自增（{_r0} → {_r1}）")
_r1b = _r1
dbm.set_meta("epl104_probe", "1")
_r2 = dbm.db_rev()
check(_r2 == _r1b, f"meta 写入不碰 person → 版本号不动（{_r1b} → {_r2}）")
pdb.mark_deleted(plugin_id=_pid, item_ids=["tvdb:1"], server_id="s1")
_r3 = dbm.db_rev()
check(_r3 > _r2, f"mark_deleted（UPDATE person）→ 版本号自增（{_r2} → {_r3}）")
n_del = dbm._x("DELETE FROM person WHERE plugin_id=? AND item_id=?", (_pid, "tvdb:1"))
_r4 = dbm.db_rev()
check(n_del > 0 and _r4 > _r3, f"DELETE person → 版本号自增（{_r3} → {_r4}）")
check(isinstance(dbm.db_rev(), int), "db_rev() 返回整数（前端只做「不等即变化」比较）")

# ─────────────────────────────────────────────
print("\n[T7] 源码级：/status 下发 items_rev")
# ─────────────────────────────────────────────
_st = _grab_method(_SRC, "_api_status")
check('"items_rev": db_rev(),' in _st, "/status 返回体含 items_rev（db_rev()）")
check("from .db import (PeopleDb, NameMapDb, WritebackDb, TranslateJobDb, pool_target_name," in _SRC
      and "db_rev" in _SRC.split("from .db import (")[1].split(")")[0],
      "__init__.py 已导入 db_rev（v4.6.111 起同一行还带 get_meta/set_meta）")
check("def db_rev() -> int:" in _DB, "db.py 定义 db_rev()")
check('if "person" in sql.lower():' in _DB, "_x 只对 person 表写入自增版本号（任务簿记不误触发）")

print("\n" + "=" * 72)
print(f"结果：PASS {_N[0] - _N[1]} / {_N[0]}，FAIL {_N[1]}")
print("=" * 72)
sys.exit(1 if _N[1] else 0)