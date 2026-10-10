# -*- coding: utf-8 -*-
"""v4.6.80 回归测试：「中文里带空格」的名字不再被判成待翻译（口径修正）。

运行：python tests/test_v480_chinese_with_space.py

用户实测：「角田 雄二郎」明明就是中文里多了个空格，却被判「待翻译」，
且繁简转换是空操作、AI 也多半原样返回 → 永远停在待翻译并每轮重复调 AI。
修正：含汉字且**无假名**即视为「已是中文」（空格不再作为排除条件）。

覆盖：
  T1 Python 口径：_is_chinese_text（含空格→中文；含假名→非中文；英文→非中文）
  T2 SQL 口径（真实 SQLite）：count_pool_status / list_pool 对三类名字的归类
  T3 pool_target_name：空格名 → 目标名 = 原文
  T4 前端口径对齐（Node 跑真实提取的 isChineseText）
  T5 「本轮无可消费词条」可见原因日志（源码级）
"""
import sys
import os
import re
import types
import subprocess
import tempfile
import importlib.util
from pathlib import Path
from typing import Any, Optional, Dict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl80_"))
_VUE = (PLUGIN_DIR / "src/views/PeoplePoolView.vue").read_text(encoding="utf-8")
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")

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
class _S: CONFIG_PATH = str(TMP)
_c.settings = _S()
sys.modules.update({"app": _m, "app.sdk": _s, "app.sdk.logging": _l, "app.sdk.config": _c})

_spec = importlib.util.spec_from_file_location("epl_db80", PLUGIN_DIR / "db.py")
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

print("=" * 72)
print("v4.6.80 回归测试（中文带空格的名字不再判待翻译）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] Python 口径：_is_chinese_text")
# ─────────────────────────────────────────────
check(dbm._is_chinese_text("角田 雄二郎") is True, "「角田 雄二郎」（中文带空格）→ 是中文")
check(dbm._is_chinese_text("角田雄二郎") is True, "「角田雄二郎」（无空格）→ 是中文")
check(dbm._is_chinese_text("上坂堇") is True, "「上坂堇」→ 是中文")
check(dbm._is_chinese_text("水桥 かおり") is False, "「水桥 かおり」（含假名）→ 不是中文（仍需翻译）")
check(dbm._is_chinese_text("かおり") is False, "纯假名 → 不是中文")
check(dbm._is_chinese_text("Tom Hanks") is False, "英文 → 不是中文")
check(dbm._is_chinese_text("") is False, "空 → 不是中文")

# ─────────────────────────────────────────────
print("\n[T2] SQL 口径（真实 SQLite）：池状态归类")
# ─────────────────────────────────────────────
pdb = dbm.NameMapDb()
pdb.ensure_table()
PID = "EPL80"
_rows = [
    ("角田 雄二郎", "person"),   # 中文带空格 → 无需操作
    ("上坂堇", "person"),        # 中文         → 无需操作
    ("水桥 かおり", "person"),   # 含假名       → 待翻译
    ("Tom Hanks", "person"),     # 英文         → 待翻译
]
for _nm, _ty in _rows:
    pdb.upsert_pool_person(plugin_id=PID, server_id="S1", emby_person_id="",
                           name_original=_nm, name_current=_nm, name_zh="",
                           person_type="Actor", person_types=["Actor"], source="", translation_status="pending")
_st = pdb.count_pool_status(plugin_id=PID)
check(_st["no_change"] == 2, f"「无需操作」= 2（角田 雄二郎 / 上坂堇），实际 {_st['no_change']}")
check(_st["pending"] == 2, f"「待翻译」= 2（水桥 かおり / Tom Hanks），实际 {_st['pending']}")
_lp = pdb.list_pool(plugin_id=PID, status="pending", size=50)
_names = sorted(str(x.get("name_original")) for x in (_lp.get("items") or []))
check(_names == ["Tom Hanks", "水桥 かおり"], f"待翻清单只含真正需翻译的：{_names}")
_lp2 = pdb.list_pool(plugin_id=PID, status="", size=50)
_by = {str(x.get("name_original")): x for x in (_lp2.get("items") or [])}
check("角田 雄二郎" in _by, "「角田 雄二郎」仍列在池里（只是不再算待翻译）")

# ─────────────────────────────────────────────
print("\n[T3] pool_target_name：空格名的目标名 = 原文")
# ─────────────────────────────────────────────
check(dbm.pool_target_name({"name_original": "角田 雄二郎", "name_zh": ""}) == "角田 雄二郎",
      "目标名 = 原名（池里不再是「--- 待翻译」）")
check(dbm.pool_target_name({"name_original": "Tom Hanks", "name_zh": ""}) == "",
      "英文无译文 → 目标名为空（仍需翻译）")

# ─────────────────────────────────────────────
print("\n[T4] 前端口径对齐（Node 跑真实提取的 isChineseText）")
# ─────────────────────────────────────────────
def _grab_vue(decl: str) -> str:
    mm = re.search(rf"^(?:async\s+)?function\s+{re.escape(decl)}\s*\(", _VUE, re.M)
    assert mm, f"未找到 {decl}"
    lines = _VUE[mm.start():].splitlines()
    out, depth = [], 0
    for ln in lines:
        out.append(ln)
        depth += ln.count("{") - ln.count("}")
        if depth == 0 and len(out) > 1:
            break
    return "\n".join(out)

check("空格" not in _grab_vue("isChineseText") or "空格不再" in _grab_vue("isChineseText"),
      "前端 isChineseText 已去掉「空格即非中文」的逻辑")
_js = _grab_vue("isChineseText") + """
let n=0,f=0; function chk(c,m){n++; if(c) console.log('PASS '+m); else {f++; console.log('FAIL '+m);}}
chk(isChineseText('角田 雄二郎')===true, '角田 雄二郎 → 中文');
chk(isChineseText('水桥 かおり')===false, '水桥 かおり → 非中文（含假名）');
chk(isChineseText('Tom Hanks')===false, '英文 → 非中文');
chk(isChineseText('')===false, '空 → 非中文');
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
    _t = Path(tempfile.mkdtemp(prefix="epl80n_")) / "t.mjs"
    _t.write_text(_js, encoding="utf-8")
    r = subprocess.run([node, str(_t)], capture_output=True, timeout=60)
    out = (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")
    for _ln in out.splitlines():
        if _ln.startswith("PASS "):
            check(True, _ln[5:])
        elif _ln.startswith("FAIL "):
            check(False, _ln[5:])
    _jf = re.search(r"JS_FAIL=(\d+)", out)
    check(bool(_jf) and int(_jf.group(1)) == 0, "前端行为级全部通过")
else:
    print("  [SKIP] 未找到 node")

# ─────────────────────────────────────────────
print("\n[T5] 「本轮无可消费词条」可见原因日志（源码级）")
# ─────────────────────────────────────────────
_i = _SRC.find("本轮无可消费词条")
_seg = _SRC[_i - 300:_i + 500] if _i >= 0 else ""
check(_i > 0, "已新增「本轮无可消费词条」诊断日志（不再静默 did=False）")
check("第一排={_take_person}" in _seg and "池={bool(pool_rows)}" in _seg,
      "诊断输出：来源 / 范围 / 两排开关 / 池是否收到（定位「为什么 0」）")
check("_SQL_IS_ZH" in (PLUGIN_DIR / "db.py").read_text(encoding="utf-8")
      and "_SQL_HAS_NAME_SPACE" not in re.search(r"_SQL_IS_ZH = .*", (PLUGIN_DIR / "db.py").read_text(encoding="utf-8"), re.M).group(0),
      "SQL 口径 _SQL_IS_ZH 不再排除空格")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)