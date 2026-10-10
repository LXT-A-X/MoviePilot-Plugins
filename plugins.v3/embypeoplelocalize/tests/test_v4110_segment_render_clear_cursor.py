r"""
v4.6.110 回归测试（①展开分库分段渲染 ②清空翻译记录后「续跑」仍在 ③TMDB 空结果日志带条目/文件）

① 用户担心：左栏点开「动漫番剧 ▾」往下拉会列出剧名，若一次把该分库**全部**条目渲染出来，
   几千行时会不会卡（Vuetify 的 v-list 默认不虚拟滚动）。
   现状：`visibleNodes` 里展开分库是 `for (const it of list) out.push(...)` —— 有多少推多少。
   修复（LIB-018）：**只限制「渲染多少行」**（每页 300，滚到「还有 N 条」提示行再补一页），
   **数据仍全量加载**（items.value 不动）→ 分库分组与条数完全不受影响，
   也不会退回「第 1 页之外的分库整组消失」的老问题。

② 用户实测：扫描到一半点「暂停」→ 清空数据库 → 仪表盘**仍显示「续跑」**可用。
   根因（LIB-019）：`_api_db_clear` 清了记录 / 写回队列 / 文件签名，但**没清扫描断点**
   （`_scan_cursor["nfo"]`），而 `_nfo_resume_state()` 只看断点 → 「续跑」依旧可用，
   可记录与译文都删了，续跑只会跳过全部已处理文件、空转。
   修复：清空翻译记录时**一并清掉扫描断点**（并在日志/返回里说明）。

③ 宿主 `tmdbapi.py` 的 404 日志不含 ID、无法定位；v4.6.109 已补 ID，
   这一版再把**条目名 + NFO 文件名**带进日志，直接定位到具体文件。

覆盖：
  T1 行为级（Node 跑真实 visibleNodes）：分段渲染上限 / 「还有 N 条」/ 分组与条数不受影响
  T2 源码级：只限制渲染、不动数据；模板与滚动接线
  T3 行为级 + 源码级：清断点后「续跑」自动不可用
  T4 源码级：TMDB 日志带条目/文件
"""
import sys
import re
import types
import tempfile
import subprocess
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
_VUE = (PLUGIN_DIR / "src/views/LibraryView.vue").read_text(encoding="utf-8")

_N = [0, 0]


def check(cond, msg):
    _N[0] += 1
    if cond:
        print(f"  [PASS] {msg}")
    else:
        _N[1] += 1
        print(f"  [FAIL] {msg}")


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
    _tf = Path(tempfile.mkdtemp(prefix="epl110n_")) / "t.mjs"
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


def _grab_method(src, name, indent=4):
    lines = src.splitlines()
    i0 = next(i for i, ln in enumerate(lines) if ln.startswith(" " * indent + f"def {name}("))
    i1 = len(lines)
    for i in range(i0 + 1, len(lines)):
        if lines[i].startswith(" " * indent + "def ") or lines[i].startswith(" " * indent + "async def "):
            i1 = i
            break
    return "\n".join(ln[indent:] if len(ln) >= indent else ln for ln in lines[i0:i1])


print("=" * 72)
print("v4.6.110 回归测试（分库分段渲染 / 清库清断点 / TMDB 日志带文件）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] 行为级（Node 跑真实 visibleNodes）：分段渲染")
# ─────────────────────────────────────────────
_i = _VUE.index("const visibleNodes = computed(() => {")
_j = _VUE.index("\n})", _i) + 3
_txt = _VUE[_i:_j]
check(_txt.endswith("\n})"), "已定位 visibleNodes computed 区块")
_fn = _txt.replace("const visibleNodes = computed(() => {", "function visibleNodesFn() {", 1)
_fn = _fn[: -len("\n})")] + "\n}"
check("function visibleNodesFn() {" in _fn and "type: 'more'" in _fn,
      "已把 computed 包装换成可执行函数（含 more 节点逻辑）")

_js = """
const BIG = []
for (let i = 0; i < 485; i++) BIG.push({ server_id: 's', item_id: 'i' + i, title: 'T' + i })
const groups = { value: { '动漫番剧': BIG, '电影': [{ server_id: 's', item_id: 'm1', title: 'M1' }] } }
const expandedLibs = { value: new Set(['动漫番剧']) }
const search = { value: '' }
const libRenderCap = { value: {} }
const RENDER_PAGE = 300
""" + _fn + """
let n = 0, f = 0
function chk (c, m) { n++; if (c) console.log('PASS ' + m); else { f++; console.log('FAIL ' + m) } }

let v = visibleNodesFn()
chk(v.filter(x => x.type === 'item').length === 300,
    '展开分库首批只渲染 300 行，实际 ' + v.filter(x => x.type === 'item').length)
chk(v.filter(x => x.type === 'group').length === 2,
    '两个分库分组节点都在（不受渲染上限影响）')
chk(v.find(x => x.type === 'group' && x.lib === '动漫番剧').count === 485,
    '分库条数仍是全量 485（数据没被裁剪）')
const more = v.find(x => x.type === 'more')
chk(!!more && more.remain === 185 && more.shown === 300 && more.total === 485,
    '末尾有「还有 N 条」提示行（remain=185）')
chk(v.filter(x => x.type === 'item' || x.type === 'more').length === 301,
    '渲染行数 = 300 + 1 提示行（有上限）')

libRenderCap.value = { '动漫番剧': 600 }
v = visibleNodesFn()
chk(v.filter(x => x.type === 'item').length === 485, '补一页后 485 条全部渲染')
chk(!v.some(x => x.type === 'more'), '全部渲染后不再显示「还有 N 条」')

expandedLibs.value = new Set()
v = visibleNodesFn()
chk(v.filter(x => x.type === 'item').length === 0 && v.filter(x => x.type === 'group').length === 2,
    '分库未展开时只渲染分组行（不渲染条目）')
console.log('JS_TOTAL=' + n); console.log('JS_FAIL=' + f)
"""
_report(_node_run(_js), "T1")

# ─────────────────────────────────────────────
print("\n[T2] 源码级：只限制渲染、不动数据；模板与滚动接线")
# ─────────────────────────────────────────────
check("const RENDER_PAGE = 300" in _VUE, "新增 RENDER_PAGE（每页渲染 300 行）")
check("const _shown = list.slice(0, _cap)" in _VUE, "展开分库只渲染前 N 条")
check("items.value =" not in _fn, "visibleNodes 里没有改写 items（数据仍全量，分库/条数不受影响）")
check('class="epl-more-sentinel"' in _VUE and ':data-more-lib="node.lib"' in _VUE,
      "模板里有「还有 N 条」提示行（带分库名）")
check('v-else-if="node.type === \'item\'"' in _VUE, "条目节点改为 v-else-if（给提示行让出 v-else）")
check('ref="listBody" class="pa-0 epl-col-body" @scroll="onListScroll"' in _VUE,
      "左栏滚动容器接了 onListScroll（滚到提示行附近补渲染）")
check("function onListScroll()" in _VUE and "function growLib(lib)" in _VUE,
      "onListScroll / growLib 已实现（点击提示行也能加载）")
check(".epl-more-sentinel { cursor: pointer" in _VUE, "提示行有可点样式")

# ─────────────────────────────────────────────
print("\n[T3] 清空翻译记录 → 「续跑」不再可用")
# ─────────────────────────────────────────────
check('_cur.pop("nfo", None)' in _SRC, "清空翻译记录时一并清掉扫描断点（_scan_cursor.nfo）")
check("扫描断点 {_cur_n} 条已一并清空" in _SRC, "日志/提示里说明断点已清")
check('"cursor_cleared": _cur_n' in _SRC, "返回体带上清掉的断点条数")

_ns = {}
exec(_grab_method(_SRC, "_nfo_resume_state"), _ns)


class _Stub:
    _nfo_recursive = True
    _nfo_include_episodes = False

    def __init__(self, cur):
        self._scan_cursor = cur

    def _nfo_scan_sig(self, *a, **k):
        return "SIG"

    def _all_nfo_roots(self):
        return []


_resume = _ns["_nfo_resume_state"]
_full = _resume(_Stub({"nfo": {"sig": "SIG", "done": {"a.nfo": "x", "b.nfo": "y"}}}))
check(_full["ok"] is True and _full["done"] == 2, "有断点时「续跑」可用（复现用户看到的现象）")
_cur = {"nfo": {"sig": "SIG", "done": {"a.nfo": "x", "b.nfo": "y"}}}
_cur.pop("nfo", None)   # 复刻 _api_db_clear 里的清理
_cleared = _resume(_Stub(_cur))
check(_cleared["ok"] is False and _cleared["done"] == 0,
      "断点被清后「续跑」自动不可用（不再误导）")

# ─────────────────────────────────────────────
print("\n[T4] 源码级：TMDB 空结果日志带条目/文件")
# ─────────────────────────────────────────────
check("def _tmdb_credits_role_map(self, item_id: str, item_type: str, hint: str = \"\") -> dict:"
      in _SRC, "接口新增 hint 参数（仅用于日志）")
check("{('｜' + hint) if hint else ''}" in _SRC, "日志把 hint 拼在 id/类型后面")
check('hint=f"条目={title or os.path.basename(doc.path)}"' in _SRC
      and 'f"｜文件={os.path.basename(doc.path)}"' in _SRC,
      "调用点传入「条目名 + NFO 文件名」（可直接定位到文件）")

print("\n" + "=" * 72)
print(f"结果：PASS {_N[0] - _N[1]} / {_N[0]}，FAIL {_N[1]}")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
