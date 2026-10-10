# -*- coding: utf-8 -*-
"""v4.6.94 回归测试：译名列「改过才显示」+ 状态文案「无需操作」。

运行：python tests/test_v494_zh_display_and_wording.py

用户口径（2026-10-09）：
① 人名池两列不再重复显示同一个名字 —— 原文名列只显示「我们拉进来的原名」；
   译名列只在「第一排改过」时显示最终译名（AI 翻译 / 人工修改），
   这样即使人工改错，也还能对照原文名进行修正。
② 如果原文本来就是中文 → 译名列不用显示（只显示一处）；状态不叫「无需翻译」，
   改「无需操作」（这类行不翻也不同步，什么都不用做）。
③ 只要第一排改过，状态就与没改过的行不一样（待同步 / 已同步）。

覆盖：
  T1 derive_pool_status：no_change → 「无需操作」；改过 → 待同步/已同步（状态区分）
  T2 「第一排改过」语义矩阵（含中文原件被改：去空格 / 加译名）
  T3 源码级：db.py / PeoplePoolView.vue 无「无需翻译」残留 + 模板接线 zhText
  T4 前端 Node：zhText / statusChip / recomputeRowStatus 行为级
  T5 真实 SQLite：计数口径不变 + 状态输出为「无需操作」
"""
import sys
import re
import types
import subprocess
import tempfile
import importlib.util
from pathlib import Path
from typing import Any, Optional, Dict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl94_"))
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
_DB = (PLUGIN_DIR / "db.py").read_text(encoding="utf-8")
_VUE = (PLUGIN_DIR / "src/views/PeoplePoolView.vue").read_text(encoding="utf-8")


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


_c.settings = _S()
sys.modules.update({"app": _m, "app.sdk": _s, "app.sdk.logging": _l, "app.sdk.config": _c})

_spec = importlib.util.spec_from_file_location("epl_db94", PLUGIN_DIR / "db.py")
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
print("v4.6.94 回归测试（译名列改过才显示 / 状态改「无需操作」）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] derive_pool_status：no_change → 无需操作（不再是 无需翻译）")
# ─────────────────────────────────────────────
_d = dbm.derive_pool_status
_r = _d({"name_original": "阿澄 佳奈", "name_zh": "阿澄 佳奈", "name_current": ""})
check(_r["ui"] == "无需操作", f"已中文（zh==原文，当前名未知）→ 无需操作（实际 {_r['ui']}）")
_r = _d({"name_original": "角田 雄二郎", "name_zh": "", "name_current": ""})
check(_r["ui"] == "无需操作", f"已中文（zh 为空）→ 无需操作（实际 {_r['ui']}）")
_r = _d({"name_original": "上坂堇", "name_zh": "上坂堇", "name_current": "上坂堇"})
check(_r["ui"] == "无需操作" and _r["sync"] == "synced",
      f"已中文 + 当前名==原名 → 无需操作（实际 {_r['ui']}）")
_r = _d({"name_original": "水桥 かおり", "name_zh": "", "name_current": ""})
check(_r["ui"] == "待翻译", f"含假名未翻 → 待翻译（实际 {_r['ui']}）")
check(all(_d({"name_original": o, "name_zh": z, "name_current": c})["ui"] != "无需翻译"
          for o, z, c in [("阿澄 佳奈", "阿澄 佳奈", ""), ("角田 雄二郎", "", ""),
                          ("上坂堇", "上坂堇", "上坂堇")]),
      "不再有任何行输出旧文案「无需翻译」")

# ─────────────────────────────────────────────
print("\n[T2] 「第一排改过」语义矩阵：改过 → 状态与没改过的不同")
# ─────────────────────────────────────────────
_r = _d({"name_original": "阿澄 佳奈", "name_zh": "阿澄佳奈", "name_current": ""})
check(_r["translation"] == "translated" and _r["ui"] == "待同步",
      f"中文原件被改（去空格：阿澄 佳奈→阿澄佳奈）→ 待同步（实际 {_r['ui']}）")
_r = _d({"name_original": "阿澄 佳奈", "name_zh": "阿澄佳奈", "name_current": "阿澄佳奈"})
check(_r["ui"] == "已同步", f"改过 + 当前名==译名 → 已同步（实际 {_r['ui']}）")
_r = _d({"name_original": "佐仓绫音", "name_zh": "佐仓绫音", "name_current": ""})
check(_r["ui"] == "无需操作",
      f"AI 原样返回（zh==原文）不算改过 → 仍无需操作（实际 {_r['ui']}）")
_r = _d({"name_original": "田中 あいみ", "name_zh": "田中爱美", "name_current": ""})
check(_r["ui"] == "待同步", f"日文译成中文（改过）→ 待同步（实际 {_r['ui']}）")
_r = _d({"name_original": "Tom Hanks", "name_zh": "汤姆汉克斯", "name_current": "汤姆汉克斯"})
check(_r["ui"] == "已同步", f"译过并已同步 → 已同步（实际 {_r['ui']}）")

# ─────────────────────────────────────────────
print("\n[T3] 源码级：无「无需翻译」残留 + 前端 zhText 接线")
# ─────────────────────────────────────────────
check("无需翻译" not in _DB, "db.py 无「无需翻译」字面量（文案已全部改「无需操作」）")
check('ui = "无需操作"' in _DB, "derive_pool_status 输出「无需操作」")
check('no_change 无需操作' in _DB and 'no_change=无需操作' in _DB, "两处状态说明文档同步更新")
check("无需翻译" not in _VUE, "PeoplePoolView.vue 无「无需翻译」残留（筛选/徽标/明细/弹窗）")
check("{ value: 'no_change', title: '无需操作' }" in _VUE, "状态筛选 chip 改「无需操作」")
check("if (r.status === '无需操作') return { text: '无需操作', color: 'success', dot: '🟩' }" in _VUE,
      "状态徽标映射改「无需操作」（绿🟩）")
check("function zhText(r)" in _VUE, "新增 zhText() —— 译名列「改过才显示」的单点判定")
check("{{ zhText(r) || '—' }}" in _VUE, "桌面表格译名列接入 zhText（没改过显示 —）")
check("{{ zhText(r) || (isChineseText(r.name_original) ? '—' : '— 未译') }}" in _VUE,
      "移动卡片译名列接入 zhText（已中文 → —；未译 → — 未译）")
check(':title="r.name_zh"' in _VUE, "译名列悬停提示保留（可 peek 池里存的 zh）")

# ─────────────────────────────────────────────
print("\n[T4] 前端 Node：zhText / statusChip / recomputeRowStatus 行为级")
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


_js = (_grab_vue("isChineseText") + "\n" + _grab_vue("poolTargetName") + "\n"
       + _grab_vue("zhText") + "\n" + _grab_vue("recomputeRowStatus") + "\n"
       + _grab_vue("statusChip") + """
let n=0,f=0; function chk(c,m){n++; if(c) console.log('PASS '+m); else {f++; console.log('FAIL '+m);}}
// zhText：改过才显示
chk(zhText({name_original:'阿澄 佳奈',name_zh:'阿澄 佳奈'})==='', '原文已是中文未改过 → 译名列空（不重复显示）');
chk(zhText({name_original:'佐仓绫音',name_zh:'佐仓绫音'})==='', '佐仓绫音未改过 → 译名列空');
chk(zhText({name_original:'角田 雄二郎',name_zh:''})==='', 'zh 为空 → 译名列空');
chk(zhText({name_original:'Tom Hanks',name_zh:''})==='', '未翻 → 译名列空');
chk(zhText({name_original:'Tom Hanks',name_zh:'汤姆汉克斯'})==='汤姆汉克斯', 'AI 译过 → 显示译名');
chk(zhText({name_original:'阿澄 佳奈',name_zh:'阿澄佳奈'})==='阿澄佳奈', '人工改过（去空格）→ 显示改后的名字');
// 状态徽标
let c1=statusChip({status:'无需操作'});
chk(c1.text==='无需操作' && c1.dot==='🟩', '徽标：无需操作 → 绿🟩');
chk(statusChip({status:'无需翻译'}).text!=='无需翻译', '旧文案不再有专属徽标（落到默认）');
// 状态与「改没改过」联动
let r1={name_original:'阿澄 佳奈',name_zh:'阿澄 佳奈',name_current:'',sync_status:''};
recomputeRowStatus(r1); chk(r1.status==='无需操作', '未改过（已中文）→ 无需操作，实际 '+r1.status);
let r2={name_original:'阿澄 佳奈',name_zh:'阿澄佳奈',name_current:'',sync_status:''};
recomputeRowStatus(r2); chk(r2.status==='待同步', '改过（未同步）→ 待同步，实际 '+r2.status);
let r3={name_original:'Tom Hanks',name_zh:'汤姆汉克斯',name_current:'汤姆汉克斯',sync_status:''};
recomputeRowStatus(r3); chk(r3.status==='已同步', '改过且已同步 → 已同步，实际 '+r3.status);
let r4={name_original:'水桥 かおり',name_zh:'',name_current:'',sync_status:''};
recomputeRowStatus(r4); chk(r4.status==='待翻译', '未改过（非中文）→ 待翻译，实际 '+r4.status);
console.log('JS_TOTAL='+n); console.log('JS_FAIL='+f);
""")
node = None
for _cand in (r"C:\node-v22.14.0-win-x64\node.exe", "node"):
    try:
        subprocess.run([_cand, "-v"], capture_output=True, timeout=15)
        node = _cand
        break
    except Exception:
        continue
if node:
    _t = Path(tempfile.mkdtemp(prefix="epl94n_")) / "t.mjs"
    _t.write_text(_js, encoding="utf-8")
    _r = subprocess.run([node, str(_t)], capture_output=True, timeout=60)
    out = (_r.stdout or b"").decode("utf-8", "replace") + (_r.stderr or b"").decode("utf-8", "replace")
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
print("\n[T5] 真实 SQLite：计数口径不变 + 状态输出「无需操作」")
# ─────────────────────────────────────────────
pdb = dbm.NameMapDb()
pdb.ensure_table()
PID = "EPL94"
_rows = [
    ("阿澄 佳奈", "阿澄 佳奈", "", "", "无需操作"),      # 未改过（已中文）
    ("佐仓绫音", "佐仓绫音", "", "", "无需操作"),        # 未改过（已中文）
    ("村川 梨衣", "村川梨衣", "", "", "待同步"),        # 改过（去空格）未同步
    ("田中 あいみ", "", "", "", "待翻译"),              # 未改过（含假名）
    ("Tom Hanks", "汤姆汉克斯", "汤姆汉克斯", "synced", "已同步"),
]
for _o, _z, _c, _ss, _exp in _rows:
    pdb.upsert_pool_person(plugin_id=PID, server_id=("S1" if _ss else ""),
                           emby_person_id=("p1" if _ss else ""),
                           name_original=_o, name_current=_c, name_zh=_z,
                           person_type="Actor", person_types=["Actor"], source="scan",
                           sync_status=_ss)
_lp = pdb.list_pool(plugin_id=PID, size=50)
_by = {str(x.get("name_original")): x for x in (_lp.get("items") or [])}
_ok = all(_by.get(_o, {}).get("status") == _exp for _o, _z, _c, _ss, _exp in _rows)
check(_ok, "list_pool 状态全部为：「无需操作/待同步/待翻译/已同步」")
check(all(str(x.get("status")) != "无需翻译" for x in (_lp.get("items") or [])),
      "列表不再出现旧文案「无需翻译」")
_st = pdb.count_pool_status(plugin_id=PID)
check(_st["no_change"] == 2, f"无需操作计数 = 2（阿澄 佳奈 / 佐仓绫音），实际 {_st['no_change']}")
check(_st["translated"] == 1 and _st["pending"] == 1 and _st["synced"] == 1,
      f"待同步/待翻译/已同步 = 1/1/1，实际 {_st['translated']}/{_st['pending']}/{_st['synced']}")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)