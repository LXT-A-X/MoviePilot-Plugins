# -*- coding: utf-8 -*-
"""v4.6.79 回归测试：人名池「类型」显示口径 —— 演员类合并为「演员」，特别身份不合并。

运行：python tests/test_v479_pool_type_display.py

需求（用户确认）：
  主演 Actor / 声优 VoiceActor / 客串 GuestStar 三者**都算演员** → 显示层合并为一枚「演员」；
  导演 / 编剧 / 制片 等「特别身份」**不合并**，各自单独显示。
  只改【人名池】显示；库页（LibraryView）不动。

覆盖：
  T1 源码级：PeoplePoolView 新增 ACTING_TYPES / ACTING_LABEL，typeList 走合并
  T2 行为级（Node 跑真实 extract 的函数）：13 个用例
  T3 库页未受影响（LibraryView 仍保留 客串/声优 标签，main_cast 显示不变）
  T4 只改显示：筛选选项 TYPE_FILTERS / 拉取类型 / 重筛 / 翻译开关均未被改动
"""
import sys
import os
import re
import subprocess
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
_VUE = (PLUGIN_DIR / "src/views/PeoplePoolView.vue").read_text(encoding="utf-8")
_LIB = (PLUGIN_DIR / "src/views/LibraryView.vue").read_text(encoding="utf-8")

_N = [0, 0]
def check(cond, msg):
    _N[0] += 1
    if cond:
        print(f"  [PASS] {msg}")
    else:
        _N[1] += 1
        print(f"  [FAIL] {msg}")

def _grab_vue(decl: str) -> str:
    """从 .vue 提取一段 JS 函数体（按花括号配对）。"""
    m = re.search(rf"^(?:async\s+)?function\s+{re.escape(decl)}\s*\(", _VUE, re.M)
    assert m, f"未找到 Vue 函数 {decl}"
    lines = _VUE[m.start():].splitlines()
    out, depth = [], 0
    for ln in lines:
        out.append(ln)
        depth += ln.count("{") - ln.count("}")
        if depth == 0 and len(out) > 1:
            break
    return "\n".join(out)

print("=" * 72)
print("v4.6.79 回归测试（人名池类型显示：演员类合并）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] 源码级：合并常量与 typeList 逻辑")
# ─────────────────────────────────────────────
check(re.search(r"^const ACTING_TYPES = \['Actor', 'VoiceActor', 'GuestStar'\]$", _VUE, re.M) is not None,
      "ACTING_TYPES = ['Actor','VoiceActor','GuestStar']（三者都算演员）")
check(re.search(r"^const ACTING_LABEL = '演员'$", _VUE, re.M) is not None,
      "ACTING_LABEL = '演员'")
_tl = _grab_vue("typeList")
check("ACTING_TYPES.includes(x)" in _tl and "hasActing = true" in _tl,
      "typeList：演员类被识别并跳过（不单独成标签）")
check("[ACTING_LABEL, ...out]" in _tl, "typeList：有演员类时「演员」排在最前，特别身份跟随")
check("TYPE_FILTERS" not in _tl, "typeList 未触碰筛选选项（只改显示）")

# ─────────────────────────────────────────────
print("\n[T2] 行为级：Node 跑真实提取的函数（13 用例）")
# ─────────────────────────────────────────────
def _first_line(pat: str) -> str:
    m = re.search(pat, _VUE, re.M)
    assert m, f"未找到 {pat}"
    return m.group(0)

_defs = "\n".join([
    _first_line(r"^const TYPE_LABELS = \{.*$"),
    _first_line(r"^const ACTING_TYPES = \[.*$"),
    _first_line(r"^const ACTING_LABEL = .*$"),
    _grab_vue("parseJsonArray"),
    _grab_vue("typeList"),
    _grab_vue("typeText"),
])

JS = _defs + """
let n=0, f=0;
function chk(c, m){ n++; if(c) console.log('PASS '+m); else { f++; console.log('FAIL '+m); } }
function T(row){ return typeText(row); }
chk(T({person_types:['Actor']}) === '演员', 'Actor → 演员');
chk(T({person_types:['GuestStar']}) === '演员', 'GuestStar（仅客串）→ 演员');
chk(T({person_types:['VoiceActor']}) === '演员', 'VoiceActor（仅声优）→ 演员');
chk(T({person_types:['Actor','GuestStar']}) === '演员', 'Actor+GuestStar → 只显示「演员」');
chk(T({person_types:['Actor','VoiceActor','GuestStar']}) === '演员', '三者齐全 → 只显示「演员」');
chk(T({person_types:['Actor','Director']}) === '演员 / 导演', 'Actor+Director → 演员 / 导演');
chk(T({person_types:['GuestStar','Director','Writer']}) === '演员 / 导演 / 编剧',
    'GuestStar+Director+Writer → 演员 / 导演 / 编剧');
chk(T({person_types:['Director']}) === '导演', 'Director → 导演（特别身份不合并）');
chk(T({person_types:['Director','Writer','Producer']}) === '导演 / 编剧 / 制片',
    '导演/编剧/制片 各自独立');
chk(T({person_types:['Director','GuestStar']}) === '演员 / 导演', '演员排在特别身份之前');
chk(!T({person_types:['Actor','GuestStar','Director']}).includes('客串'), '结果显示中不再出现「客串」');
chk(!T({person_types:['Actor','VoiceActor']}).includes('声优'), '结果显示中不再出现「声优」');
chk(T({person_type:'GuestStar'}) === '演员', '缺 person_types、只有 person_type=GuestStar → 演员');
chk(T({person_types:'["Actor","Producer"]'}) === '演员 / 制片', 'JSON 字符串输入同样生效');
chk(T({person_type:''}) === '未分类', '无类型 → 未分类');
chk(T({}) === '未分类', '空行 → 未分类');
console.log('JS_TOTAL='+n); console.log('JS_FAIL='+f);
"""

node = None
for _cand in (r"C:\node-v22.14.0-win-x64\node.exe", "node"):
    try:
        subprocess.run([_cand, "-v"], capture_output=True, timeout=15)
        node = _cand
        break
    except Exception:
        continue

if node:
    _tmpd = Path(tempfile.mkdtemp(prefix="epl79_"))
    _f = _tmpd / "t.mjs"
    _f.write_text(JS, encoding="utf-8")
    r = subprocess.run([node, str(_f)], capture_output=True, timeout=60)
    out = (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")
    for _l in out.splitlines():
        if _l.startswith("PASS "):
            check(True, _l[5:])
        elif _l.startswith("FAIL "):
            check(False, _l[5:])
    _tot = re.search(r"JS_TOTAL=(\d+)", out)
    _fail = re.search(r"JS_FAIL=(\d+)", out)
    check(bool(_tot) and bool(_fail) and int(_fail.group(1)) == 0,
          f"Node 行为级全部通过（{(_tot.group(1) if _tot else '?')} 用例 / 失败 {(_fail.group(1) if _fail else '?')}）")
else:
    print("  [SKIP] 未找到 node，跳过行为级用例（源码级断言已覆盖规则）")

# ─────────────────────────────────────────────
print("\n[T3] 库页（LibraryView）未受影响")
# ─────────────────────────────────────────────
check("GuestStar: '客串'" in _LIB and "VoiceActor: '声优'" in _LIB,
      "库页 TYPE_LABEL 仍是「客串 / 声优」（本轮明确不动库页）")
check("ACTING_TYPES" not in _LIB, "库页未引入合并常量（范围严格限定人名池）")

# ─────────────────────────────────────────────
print("\n[T4] 只改显示：筛选 / 拉取类型 / 重筛 / 翻译开关不受影响")
# ─────────────────────────────────────────────
check("{ value: 'GuestStar', title: '客串' }" in _VUE,
      "筛选下拉仍有「客串」选项（按原始 Emby 类型筛选，功能保留）")
check("TYPE_FILTERS = [" in _VUE and "STATUS_FILTERS = [" in _VUE,
      "筛选选项结构未变")
_src_py = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
check("_pool_fetch_trans_types" in _src_py and "remove_non_matching_types" in _src_py,
      "拉取类型 / 重筛逻辑仍按原始类型（后端未改动）")
check("TX_TYPE_SWITCH = {\"Actor\": \"actor\", \"VoiceActor\": \"actor\", \"GuestStar\": \"guest\""
      in _src_py or '"GuestStar": "guest"' in _src_py,
      "翻译类型开关仍区分 guest（后端未改动）")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)