# -*- coding: utf-8 -*-
"""v4.6.93 回归测试：人名池「原文已是中文 + Emby 当前名未知」不再报「待同步」。

运行：python tests/test_v493_pool_sync_chinese_cache.py

背景（用户实测，2026-10-09）：人名池里「阿澄 佳奈 / 佐仓绫音」等行明明已是中文，
却挂🟡待同步；用户怀疑是「空格惹的祸」（带空格与不带空格的都中招，排除空格假设）。
真实数据核对（运行库副本）：这些行全部是**扫描缓存行** —— source=scan、
server_id/emby_person_id 为空（本地 NFO 扫描拿不到 Emby Person 身份）、
name_current 为空（不知道 Emby 里现在叫什么）。旧口径把「当前名未知」一律判待同步，
于是 11 行已中文缓存行常驻「待同步」，还会进「批量同步」队列白跑改名。

修正（v4.6.93）：同步维度只在「有东西可同步」时算待同步 ——
  ① Emby 当前名已知且 ≠ 目标名 → 待同步（含「原文已是中文 + 当前名不同」，语义保留）；
  ② Emby 当前名未知（空）→ 只有「有真译文」才待同步（等待写回 Emby）；
     原文已是中文（目标名 = 原文）→ 无可同步之物 → 不报待同步，显示「无需操作」。

覆盖：
  T1 derive_pool_status（Python 口径）：九种组合
  T2 真实 SQLite：count_pool_status / list_pool / list_translated_pending_sync 归类
  T3 源码级：SQL 常量结构 + derive 分支 + 旧口径残留检查
  T4 前端镜像：Node 跑真实提取的 recomputeRowStatus / canSync
  T5 用户场景：悠哉日常大王扫描的 12 行（11 中文 + 1 假名）→ 待同步 = 0
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
TMP = Path(tempfile.mkdtemp(prefix="epl93_"))
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

_spec = importlib.util.spec_from_file_location("epl_db93", PLUGIN_DIR / "db.py")
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
print("v4.6.93 回归测试（已中文 + 当前名未知 → 不再报待同步）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] derive_pool_status：九种组合")
# ─────────────────────────────────────────────
_d = dbm.derive_pool_status
_r = _d({"name_original": "阿澄 佳奈", "name_zh": "阿澄 佳奈", "name_current": ""})
check(_r["translation"] == "no_change" and _r["sync"] == "unknown" and _r["ui"] == "无需操作",
      f"阿澄 佳奈 + 当前名未知 → 无需操作（实际 {_r['ui']}/{_r['sync']}）")
_r = _d({"name_original": "佐仓绫音", "name_zh": "佐仓绫音", "name_current": ""})
check(_r["ui"] == "无需操作", f"佐仓绫音 + 当前名未知 → 无需操作（实际 {_r['ui']}）")
_r = _d({"name_original": "角田 雄二郎", "name_zh": "", "name_current": ""})
check(_r["ui"] == "无需操作", f"中文原文无译文 + 当前名未知 → 无需操作（实际 {_r['ui']}）")
_r = _d({"name_original": "上坂堇", "name_zh": "上坂堇", "name_current": "上坂堇"})
check(_r["sync"] == "synced" and _r["ui"] == "无需操作",
      f"已中文 + 当前名==原名 → synced / 无需操作（实际 {_r['sync']}/{_r['ui']}）")
_r = _d({"name_original": "佐仓绫音", "name_zh": "佐仓绫音", "name_current": "佐倉綾音"})
check(_r["sync"] == "pending" and _r["ui"] == "待同步",
      f"已中文 + 当前名已知且不同（繁体）→ 仍待同步（实际 {_r['ui']}）")
_r = _d({"name_original": "田中 あいみ", "name_zh": "田中爱美", "name_current": ""})
check(_r["translation"] == "translated" and _r["sync"] == "pending" and _r["ui"] == "待同步",
      f"有真译文 + 当前名未知 → 待同步（等待写回 Emby）（实际 {_r['ui']}）")
_r = _d({"name_original": "Tom Hanks", "name_zh": "汤姆汉克斯", "name_current": "汤姆汉克斯"})
check(_r["ui"] == "已同步", f"真译文 + 当前名==译文 → 已同步（实际 {_r['ui']}）")
_r = _d({"name_original": "楠木ともり", "name_zh": "楠木灯", "name_current": "楠木ともり"})
check(_r["ui"] == "待同步", f"真译文 + 当前名不同 → 待同步（实际 {_r['ui']}）")
_r = _d({"name_original": "水桥 かおり", "name_zh": "", "name_current": ""})
check(_r["ui"] == "待翻译", f"含假名无译文 → 待翻译（实际 {_r['ui']}）")
_r = _d({"name_original": "阿澄 佳奈", "name_zh": "阿澄 佳奈", "name_current": "",
         "sync_status": "failed"})
check(_r["ui"] == "同步失败", f"已中文 + 当前名未知 + 历史 failed → 仍如实显示同步失败（实际 {_r['ui']}）")

# ─────────────────────────────────────────────
print("\n[T2] 真实 SQLite：池统计 / 筛选 / 待同步清单")
# ─────────────────────────────────────────────
pdb = dbm.NameMapDb()
pdb.ensure_table()
PID = "EPL93"
_rows = [
    # (orig, zh, cur, pid, sst, 期望 ui)
    ("阿澄 佳奈", "阿澄 佳奈", "", "", "", "无需操作"),
    ("佐仓绫音", "佐仓绫音", "", "", "", "无需操作"),
    ("角田 雄二郎", "", "", "", "", "无需操作"),
    ("上坂堇", "上坂堇", "上坂堇", "p1", "synced", "无需操作"),
    ("田中 あいみ", "田中爱美", "", "", "", "待同步"),
    ("楠木ともり", "楠木灯", "楠木ともり", "p2", "", "待同步"),
    ("水桥 かおり", "", "", "", "", "待翻译"),
    ("Tom Hanks", "汤姆汉克斯", "汤姆汉克斯", "p3", "synced", "已同步"),
]
for _o, _z, _c, _p, _ss, _exp in _rows:
    pdb.upsert_pool_person(plugin_id=PID, server_id=("S1" if _p else ""), emby_person_id=_p,
                           name_original=_o, name_current=_c, name_zh=_z,
                           person_type="Actor", person_types=["Actor"], source="scan",
                           sync_status=_ss)
_lp = pdb.list_pool(plugin_id=PID, size=50)
_by = {str(x.get("name_original")): x for x in (_lp.get("items") or [])}
_ok = all(_by.get(_o, {}).get("status") == _exp for _o, _z, _c, _p, _ss, _exp in _rows)
check(_ok, "list_pool 每行状态符合预期：" + " / ".join(f"{r[0]}→{_by.get(r[0], {}).get('status')}" for r in _rows))

_st = pdb.count_pool_status(plugin_id=PID)
check(_st["translated"] == 2, f"待同步计数 = 2（田中 あいみ / 楠木ともり），实际 {_st['translated']}")
check(_st["no_change"] == 4, f"原文已是中文 = 4，实际 {_st['no_change']}")
check(_st["pending"] == 1, f"待翻译 = 1（水桥 かおり），实际 {_st['pending']}")
check(_st["synced"] == 2, f"已同步 = 2（上坂堇 / Tom Hanks，当前名==目标名），实际 {_st['synced']}")

_ls = pdb.list_translated_pending_sync(plugin_id=PID)
_names = sorted(str(x.get("name_original")) for x in _ls)
check(_names == ["楠木ともり", "田中 あいみ"],
      f"批量同步清单只含真有活干的 2 条，实际 {_names}")
check("阿澄 佳奈" not in _names and "佐仓绫音" not in _names and "角田 雄二郎" not in _names,
      "已中文 + 当前名未知的 3 行都不再进批量同步队列（旧口径会白跑改名）")

_lp2 = pdb.list_pool(plugin_id=PID, status="translated", size=50)
_n2 = sorted(str(x.get("name_original")) for x in (_lp2.get("items") or []))
check(_n2 == ["楠木ともり", "田中 あいみ"], f"「待同步」筛选只剩 2 条，实际 {_n2}")
_lp3 = pdb.list_pool(plugin_id=PID, status="no_change", size=50)
_n3 = sorted(str(x.get("name_original")) for x in (_lp3.get("items") or []))
check("阿澄 佳奈" in _n3 and "角田 雄二郎" in _n3,
      f"「无需操作」筛选包含已中文缓存行，实际 {_n3}")

# ─────────────────────────────────────────────
print("\n[T3] 源码级：SQL 常量结构 + derive 分支 + 旧口径残留")
# ─────────────────────────────────────────────
check('_SQL_CUR_UNKNOWN = "(name_current IS NULL OR name_current=\'\')"' in _DB,
      "新增 _SQL_CUR_UNKNOWN（当前名未知）单点定义")
_pend = _DB[_DB.index("_SQL_SYNC_PENDING = ("):_DB.index("_SQL_SYNC_FAILED = (")]
check("({_SQL_CUR_UNKNOWN} AND {_SQL_ZH_VALID})" in _pend,
      "待同步 = 当前名未知时仅「有真译文(_SQL_ZH_VALID)」才算")
check("NOT {_SQL_CUR_UNKNOWN} AND name_current<>{_SQL_TARGET}" in _pend,
      "当前名已知且不同 → 仍待同步（旧语义保留）")
check("OR name_current<>{_SQL_TARGET}) AND COALESCE(sync_status" not in _DB,
      "旧「cur 为空一律待同步」写法已移除（不留双口径）")
_synced_blk = re.search(r"_SQL_SYNCED = .*\n", _DB)
check(_synced_blk is not None and "name_current<>''" in _synced_blk.group(0),
      "_SQL_SYNCED 不变（当前名已知且==目标 → 已同步）")
check('elif not cur and translation == "no_change":' in _DB,
      "derive_pool_status 增加「已中文 + 当前名未知 → unknown」分支")
check(_DB.index('_SQL_CUR_UNKNOWN = ') < _DB.index('_SQL_SYNC_PENDING = ('),
      "_SQL_CUR_UNKNOWN 定义在 _SQL_SYNC_PENDING 之前")

# ─────────────────────────────────────────────
print("\n[T4] 前端镜像：Node 跑真实提取的 recomputeRowStatus / canSync")
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
       + _grab_vue("recomputeRowStatus") + "\n" + _grab_vue("canSync") + """
let n=0,f=0; function chk(c,m){n++; if(c) console.log('PASS '+m); else {f++; console.log('FAIL '+m);}}
let r1={name_original:'阿澄 佳奈',name_zh:'阿澄 佳奈',name_current:'',sync_status:''};
recomputeRowStatus(r1); chk(r1.status==='无需操作', '阿澄 佳奈（当前名未知）→ 无需操作，实际 '+r1.status);
chk(r1.sync_status==='unknown', 'sync 维度 = unknown，实际 '+r1.sync_status);
let r2={name_original:'田中 あいみ',name_zh:'田中爱美',name_current:'',sync_status:''};
recomputeRowStatus(r2); chk(r2.status==='待同步', '有真译文（当前名未知）→ 待同步，实际 '+r2.status);
let r3={name_original:'佐仓绫音',name_zh:'佐仓绫音',name_current:'佐倉綾音',sync_status:''};
recomputeRowStatus(r3); chk(r3.status==='待同步', '当前名已知且不同 → 待同步，实际 '+r3.status);
let r4={name_original:'Tom Hanks',name_zh:'汤姆汉克斯',name_current:'汤姆汉克斯',sync_status:''};
recomputeRowStatus(r4); chk(r4.status==='已同步', '真译文 + 当前名==译文 → 已同步，实际 '+r4.status);
chk(canSync({name_original:'阿澄 佳奈',name_zh:'阿澄 佳奈',name_current:''})===false,
    '已中文 + 当前名未知 → 行内「同步」按钮隐藏');
chk(canSync({name_original:'田中 あいみ',name_zh:'田中爱美',name_current:''})===true,
    '有真译文 + 当前名未知 → 「同步」按钮保留');
chk(canSync({name_original:'佐仓绫音',name_zh:'佐仓绫音',name_current:'佐倉綾音'})===true,
    '当前名已知且不同 → 「同步」按钮保留');
chk(canSync({name_original:'上坂堇',name_zh:'上坂堇',name_current:'上坂堇'})===false,
    '当前名==目标 → 「同步」按钮隐藏');
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
    _t = Path(tempfile.mkdtemp(prefix="epl93n_")) / "t.mjs"
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
check('v-if="canSync(r)"' in _VUE, "桌面表格「同步」按钮改用 canSync（与移动端同一口径）")

# ─────────────────────────────────────────────
print("\n[T5] 用户场景：悠哉日常大王扫描 12 行（11 中文 + 1 假名）")
# ─────────────────────────────────────────────
PID2 = "EPL93B"
_scene = ["小岩井琴里", "村川 梨衣", "佐仓绫音", "阿澄 佳奈", "佐藤利奈", "永岛由子",
          "平松 晶子", "名冢 佳织", "福圆 美里", "蟹江 裕介", "新谷 良子"]
for _nm in _scene:
    pdb.add_pool_candidates(plugin_id=PID2, entries=[
        {"original": _nm, "zh": "", "person_type": "Actor", "source": "scan"}])
pdb.add_pool_candidates(plugin_id=PID2, entries=[
    {"original": "田中 あいみ", "zh": "", "person_type": "Actor", "source": "scan"}])
_st2 = pdb.count_pool_status(plugin_id=PID2)
check(_st2["total"] == 12, f"场景共 12 行，实际 {_st2['total']}")
check(_st2["translated"] == 0, f"待同步 = 0（旧口径为 11 —— 本次修复的核心），实际 {_st2['translated']}")
check(_st2["pending"] == 1, f"待翻译 = 1（田中 あいみ，含假名），实际 {_st2['pending']}")
check(_st2["no_change"] == 11, f"原文已是中文 = 11，实际 {_st2['no_change']}")
_lq = pdb.list_translated_pending_sync(plugin_id=PID2)
check(len(_lq) == 0, f"批量同步队列为空（不再白跑 11 条改名），实际 {len(_lq)} 条")
_lp4 = pdb.list_pool(plugin_id=PID2, size=50)
_u = sorted({str(x.get("status")) for x in (_lp4.get("items") or [])})
check(_u == sorted(["无需操作", "待翻译"]), f"页面只见「无需操作/待翻译」两种状态，实际 {_u}")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)