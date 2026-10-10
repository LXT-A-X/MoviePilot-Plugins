r"""
v4.6.106 回归测试（库页右侧人物搜索「串其他剧」→ 增加搜索范围：本条目 / 全库）

用户实测：库页右侧的人物搜索框本意是「在当前这部剧里筛人」，实际会把其他剧的同名人一起列出来。
根因（LIB-012）：前端搜索只发 keyword、**不带条目身份**：
    api.get(props.api, '/db/people', { keyword: kw })
后端 _api_db_people 判 `if not item_id:` → 落到「全库搜索」分支（search_people 扫整库）。
修复：搜索框加范围下拉 —— 默认「本条目」（带 item_id/server_id，后端在该条目名单内按关键词过滤），
可选「全库」（旧行为，结果区标注「含其他作品」）；两种范围返回同构的「汇总行」；
「N 处」展开的出现清单也跟随范围（本条目范围内只数本条目）。
前端搜索框只在本条目名单里筛，出现清单同口径。

覆盖：
  T1 行为级（真 SQLite）：全库能找到两个剧的同名，条目内只找到本剧那一条 + 逐字执行源码过滤片段
  T2 源码级：_api_db_people 条目分支按 keyword 过滤并返回 search/scoped 标记
  T3 源码级：_aggregate_people_rows 抽出，全库/条目两分支共用同一汇总口径
  T4 源码级：_api_person_occurrences 支持 item_id 并按 item_id 限定
  T5 前端源码级：范围 ref 默认 item、下拉两项、切范围重搜、请求带/不带条目身份、结果区标注
  T6 行为级（Node 跑真实 searchPeople）：两种范围各自的请求参数 + 未选中条目不发请求
"""
import sys
import re
import types
import tempfile
import subprocess
import importlib.util
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl106_"))
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
_VUE = (PLUGIN_DIR / "src/views/LibraryView.vue").read_text(encoding="utf-8")


class _Logger:
    def debug(self, *a, **k): pass
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass
    def log(self, *a, **k): pass


logger = _Logger()
_m = types.ModuleType("app"); _s = types.ModuleType("app.sdk")
_l = types.ModuleType("app.sdk.logging"); _l.logger = logger
_c = types.ModuleType("app.sdk.config")


class _S:
    CONFIG_PATH = str(TMP)
    TMDB_LOCALE = "zh-CN"


_c.settings = _S()
sys.modules.update({"app": _m, "app.sdk": _s, "app.sdk.logging": _l, "app.sdk.config": _c})

_spec = importlib.util.spec_from_file_location("epl106_db", PLUGIN_DIR / "db.py")
dbm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dbm)

_N = [0, 0]


def check(cond, msg):
    _N[0] += 1
    if cond:
        print(f"  [PASS] {msg}")
    else:
        _N[1] += 1
        print(f"  [FAIL] {msg}")


def _grab_method(name):
    """类方法全文：从「    def name(」到下一个同级「    def 」。"""
    mm = re.search(rf"^    def\s+{re.escape(name)}\s*\(", _SRC, re.M)
    assert mm, f"未找到 {name}"
    _nxt = _SRC.find("\n    def ", mm.start() + 1)
    return _SRC[mm.start():(_nxt if _nxt > 0 else len(_SRC))]


def _grab_js(name):
    """取 <script setup> 里的 async function（按大括号配平）。"""
    mm = re.search(rf"^(?:async\s+)?function\s+{re.escape(name)}\s*\(", _VUE, re.M)
    assert mm, f"未找到前端函数 {name}"
    lines = _VUE[mm.start():].splitlines()
    out, depth = [], 0
    for ln in lines:
        out.append(ln)
        depth += ln.count("{") - ln.count("}")
        if depth == 0 and len(out) > 1:
            break
    return "\n".join(out)


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
    _tf = Path(tempfile.mkdtemp(prefix="epl106n_")) / "t.mjs"
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
print("v4.6.106 回归测试（库页人物搜索范围：本条目 / 全库）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] 行为级（真 SQLite）：全库串剧 vs 条目内只找本剧")
# ─────────────────────────────────────────────
pdb = dbm.PeopleDb()
pdb.ensure_table()
PID = "EPL106"


def _seed(item_id, title, rows):
    pdb.upsert_people(plugin_id=PID, server_id="", item_id=item_id, item_type="Movie",
                      title=title, people=rows)


_seed("A1", "剧A", [
    {"Type": "Actor", "before_name": "水桥 かおり", "Name": "水桥香织", "role_after": "角色甲"},
    {"Type": "Actor", "before_name": "Tom Hanks", "Name": "汤姆·汉克斯"},
    {"Type": "Actor", "before_name": "上坂堇", "Name": "上坂堇"},
])
_seed("B1", "剧B", [
    {"Type": "Actor", "before_name": "水桥 かおり", "Name": "水桥香织", "role_after": "角色乙"},
])

_glob = pdb.search_people(plugin_id=PID, keyword="水桥", limit=200)
check(len(_glob) == 2, f"全库搜索「水桥」命中 2 条（剧A + 剧B，这就是「串其他剧」）：{len(_glob)}")
_pa = pdb.people_of_item(plugin_id=PID, item_id="A1", server_id="")
check(len(_pa) == 3, f"剧A 条目内共 3 位人物，实际 {len(_pa)}")

# 逐字执行源码里的「_kw = … / if _kw: people = [...]」过滤片段
# （用朴素字符串定位，避免正则回溯；片段自带缩进，dedent 后 exec）
_lines = _SRC.splitlines()
try:
    _i0 = next(i for i, ln in enumerate(_lines)
               if ln.strip().startswith('_kw = (keyword or "").strip().lower()'))
    _i1 = next(i for i in range(_i0, len(_lines))
               if 'for _f in ("name_before", "name_after", "role_before", "role_after")' in _lines[i])
    _ind = len(_lines[_i0]) - len(_lines[_i0].lstrip())
    _ablock = "\n".join(ln[_ind:] if len(ln) >= _ind else ln for ln in _lines[_i0:_i1 + 1])
except StopIteration:
    _ablock = ""
check('if _kw:' in _ablock and 'people = [p for p in people' in _ablock,
      "已定位到 _api_db_people 里的条目内关键词过滤片段（逐字执行用）")

if _ablock:
    def _run_filter(kw):
        _ns = {"people": pdb.people_of_item(plugin_id=PID, item_id="A1", server_id=""),
               "keyword": kw}
        exec(_ablock, _ns)   # noqa: S102 - 测试：逐字执行生产代码片段
        return _ns.get("people") or []

    _hit = _run_filter("水桥")
    check(len(_hit) == 1 and _hit[0].get("name_before") == "水桥 かおり",
          f"剧A 内按「水桥」过滤 → 只剩本剧那 1 条，实际 {[x.get('name_before') for x in _hit]}")
    check(len(_run_filter("水桥香织")) == 1, "条目内过滤也能按译文命中")
    check(len(_run_filter("TOm HANKS")) == 1, "不区分大小写（tom hanks 命中 Tom Hanks）")
    check(len(_run_filter("角色乙")) == 0, "剧A 内搜「角色乙」（属剧B）→ 0 条（不再串到别的剧）")
    check(len(_run_filter("")) == 3, "空关键词 → 条目内全量（不误杀）")

# ─────────────────────────────────────────────
print("\n[T2] 源码级：_api_db_people 条目分支按 keyword 过滤 + 标记 scoped")
# ─────────────────────────────────────────────
_api = _grab_method("_api_db_people")
check('"search": bool(_kw)' in _api and '"scoped": bool(_kw)' in _api,
      "条目内搜索时返回 search/scoped 标记（前端可据此提示范围）")
check('"people": (self._aggregate_people_rows(people) if _kw else people)' in _api,
      "条目内搜索返回「汇总行」（与全库搜索同构，前端不用改渲染）")
check('_kw = (keyword or "").strip().lower()' in _api, "关键词做 strip+lower（大小写不敏感）")

# ─────────────────────────────────────────────
print("\n[T3] 源码级：汇总口径抽出为 _aggregate_people_rows，两分支共用")
# ─────────────────────────────────────────────
_agg = _grab_method("_aggregate_people_rows")
check("def _aggregate_people_rows" in _agg, "已抽出 _aggregate_people_rows")
check('r["count"] += 1' in _agg and 'r["series"].add' in _agg,
      "汇总行仍带 count / series / item_ids（前端「N 处 ▾」照常可用）")
check(_api.count("self._aggregate_people_rows(") == 2,
      f"全库分支与条目分支都走同一汇总（实际 {_api.count('self._aggregate_people_rows(')} 处）")
check("rows = []\n                idx = {}" not in _api, "旧的内联聚合循环已从 _api_db_people 移除")

# ─────────────────────────────────────────────
print("\n[T4] 源码级：出现清单支持 item_id（跟随搜索范围）")
# ─────────────────────────────────────────────
_occ = _grab_method("_api_person_occurrences")
check("item_id: str = \"\"" in _occ, "接口新增 item_id 参数")
check('_iid = str(item_id or "").strip()' in _occ, "读取并归一 item_id")
check('rows = [r for r in rows if str(r.get("item_id") or "") == _iid]' in _occ,
      "按 item_id 过滤出现清单（本条目范围下不再列其他作品）")

# ─────────────────────────────────────────────
print("\n[T5] 前端源码级：范围下拉 + 默认本条目 + 标注")
# ─────────────────────────────────────────────
check("const personSearchScope = ref('item')" in _VUE, "搜索范围 ref 默认 'item'（本条目，安全默认）")
check("{ title: '本条目', value: 'item' }" in _VUE and "{ title: '全库', value: 'all' }" in _VUE,
      "下拉两项：本条目 / 全库")
check('@update:model-value="onSearchScopeChange"' in _VUE, "下拉切换即重搜")
check("personSearchScope.value !== 'all' && !selected.value" in _VUE,
      "本条目范围但未选中条目 → 不发请求")
check("全库 · 含其他作品" in _VUE, "全库结果区明确标注「含其他作品」")
check("仅本条目" in _VUE and "本条目未找到匹配人物" in _VUE,
      "本条目结果区标注范围 + 空结果给出切换范围的指引")
check("const _p = (personSearchScope.value === 'all')" in _VUE,
      "toggleOcc 的出现清单也跟随范围（口径一致）")

# ─────────────────────────────────────────────
print("\n[T6] 行为级（Node）：真实 searchPeople 的请求参数")
# ─────────────────────────────────────────────
_js = _grab_js("searchPeople") + """
const personSearch = { value: '水桥' }
const personSearchScope = { value: 'item' }
const selected = { value: { item_id: 'A1', server_id: 'S1' } }
const searchResults = { value: [] }
const searchingPeople = { value: false }
const props = { api: {} }
let searchSeq = 0
let CALLS = 0, LAST = null
const api = { get: async (a, url, p) => { CALLS++; LAST = { url, p }; return { people: [{ name_before: 'x' }] } } }
let n = 0, f = 0
function chk (c, m) { n++; if (c) console.log('PASS ' + m); else { f++; console.log('FAIL ' + m) } }
""" + """
await searchPeople()
chk(LAST.url === '/db/people', '仍走 /db/people')
chk(LAST.p.keyword === '水桥', '始终带 keyword')
chk(LAST.p.item_id === 'A1' && LAST.p.server_id === 'S1',
    '【本条目】范围：请求带 item_id + server_id（后端只在该条目名单里筛）')
chk(searchResults.value.length === 1, '结果取自 data.people')
personSearchScope.value = 'all'
await searchPeople()
chk(!('item_id' in LAST.p) && !('server_id' in LAST.p),
    '【全库】范围：不带条目身份（保持旧行为，扫码跨作品）')
selected.value = null
personSearchScope.value = 'item'
CALLS = 0
searchResults.value = [{ name_before: 'stale' }]
await searchPeople()
chk(CALLS === 0, '本条目范围但未选中条目 → 一个请求都不发，实际 ' + CALLS)
chk(searchResults.value.length === 0, '并把残留结果清空')
console.log('JS_TOTAL=' + n); console.log('JS_FAIL=' + f)
"""
_report(_node_run(_js), "T6")

print("\n" + "=" * 72)
print(f"结果：PASS {_N[0] - _N[1]} / {_N[0]}，FAIL {_N[1]}")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
