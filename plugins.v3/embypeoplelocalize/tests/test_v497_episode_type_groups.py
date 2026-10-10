# -*- coding: utf-8 -*-
"""v4.6.97 回归测试：分集 / 主演员名单「按类型分段」（与电影页同款）。

运行：python tests/test_v497_episode_type_groups.py

背景（用户实测，2026-10-09）：库页右侧「分集演员」里所有人物平铺成一个样
（只显示「名字 + 饰 角色」），看不出哪个是演员、哪个是导演/编剧：
实测 S01E01 里 川面真也（导演）、吉田玲子（编剧）与演员长得一模一样，只是没有「饰 …」。

用户口径：分集显示「像电影一样」按类型分段；类型判断「除非 nfo 明确写客串，否则都算演员」。
本就如此 —— 类型取自 nfo：<actor> 的 <type>（缺省/Actor=演员；显式 GuestStar=客串）、
<director>=导演、<writer>=编剧、<credits>=制片人。

修正（v4.6.97，纯前端）：新增 `groupByType()` —— 把名单按类型分组
（顺序：演员→声优→客串→导演→编剧→制片人→其他），主演员区与每个分集内部都按类型分段，
段标题显示「图标 + 类型名 + 数量」；**只有一种类型时不显示段标题**（避免「演员 12」这种冗余）。
数据/翻译/写回全部不动，无需重扫。

覆盖：
  T1 groupByType / typeLabel / typeIcon（Node 跑真实提取的函数）
  T2 源码级：主演员区与分集区都接线 + 旧平铺循环已移除 + CSS 段样式
  T3 用户场景：S01E01 名单 → 演员4 / 客串1 / 导演1 / 编剧1（顺序正确）
"""
import sys
import re
import subprocess
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
_VUE = (PLUGIN_DIR / "src/views/LibraryView.vue").read_text(encoding="utf-8")

_N = [0, 0]


def check(cond, msg):
    _N[0] += 1
    if cond:
        print(f"  [PASS] {msg}")
    else:
        _N[1] += 1
        print(f"  [FAIL] {msg}")


def _grab_fn(decl: str) -> str:
    mm = re.search(rf"^(?:async\s+)?function\s+{re.escape(decl)}\s*\(", _VUE, re.M)
    assert mm, f"未找到函数 {decl}"
    lines = _VUE[mm.start():].splitlines()
    out, depth = [], 0
    for ln in lines:
        out.append(ln)
        depth += ln.count("{") - ln.count("}")
        if depth == 0:
            break
    return "\n".join(out)


print("=" * 72)
print("v4.6.97 回归测试（分集/主演员按类型分段）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] groupByType / typeLabel / typeIcon（Node 行为级）")
# ─────────────────────────────────────────────
_m_lab = re.search(r"^const TYPE_LABEL = \{[^}]*\}", _VUE, re.M | re.S)
_m_ord = re.search(r"^const TYPE_ORDER = \[[^\]]*\]", _VUE, re.M | re.S)
check(_m_lab is not None, "找到 TYPE_LABEL")
check(_m_ord is not None, "找到 TYPE_ORDER")
_js = ((_m_lab.group(0) if _m_lab else "") + ";\n" + (_m_ord.group(0) if _m_ord else "") + ";\n"
       + _grab_fn("typeLabel") + "\n" + _grab_fn("typeIcon") + "\n" + _grab_fn("groupByType") + """
let n=0,f=0; function chk(c,m){n++; if(c) console.log('PASS '+m); else {f++; console.log('FAIL '+m);}}
const A=(name,type,role)=>({name_before:name, name_after:name, type:type, role_before:role||'', role_after:role||''});
// 用户实测 S01E01 名单
const e01=[A('小岩井琴里','Actor','Renge (voice)'),A('村川 梨衣','Actor','Hotaru (voice)'),
           A('佐仓绫音','Actor','Natsumi (voice)'),A('阿澄 佳奈','Actor','Komari (voice)'),
           A('名冢 佳织','GuestStar','Kazuho (voice)'),A('川面真也','Director',''),
           A('吉田玲子','Writer','')];
const g=groupByType(e01);
chk(g.length===4, '4 段，实际 '+g.length);
chk(g.map(x=>x.type).join(',')==='Actor,GuestStar,Director,Writer', '顺序 = 演员→客串→导演→编剧，实际 '+g.map(x=>x.type).join(','));
chk(g.map(x=>x.label).join(',')==='演员,客串,导演,编剧', '标签正确，实际 '+g.map(x=>x.label).join(','));
chk(g[0].list.length===4 && g[1].list.length===1 && g[2].list.length===1 && g[3].list.length===1, '各段数量 4/1/1/1');
chk(g[2].list[0].name_before==='川面真也', '导演段是 川面真也（能分清导演了）');
// 缺 type 一律算演员
chk(groupByType([A('无类型','','')])[0].type==='Actor', '缺 type → 归入演员');
// 未知类型按出现顺序追加在后
const g2=groupByType([A('某甲','Director',''),A('某乙','CustomType','')]);
chk(g2.map(x=>x.type).join(',')==='Director,CustomType', '未知类型追加在末尾');
chk(g2[1].label==='CustomType', '未知类型标签回落为原串');
// 空 / 单类型
chk(groupByType([]).length===0, '空名单 → 0 段');
chk(groupByType(null).length===0, 'null → 0 段');
chk(groupByType([A('a','Actor','')]).length===1, '单一类型 → 1 段（模板据此隐藏段标题）');
// 图标
chk(typeIcon('Director')==='mdi-video-outline' && typeIcon('Writer')==='mdi-pencil-outline'
    && typeIcon('Actor')==='mdi-account', '类型图标映射正确');
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
    _t = Path(tempfile.mkdtemp(prefix="epl97n_")) / "t.mjs"
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
print("\n[T2] 源码级：两处接线 + 旧平铺循环移除 + 段样式")
# ─────────────────────────────────────────────
check("const mainCastGroups = computed(() => groupByType(libMainCast.value))" in _VUE,
      "主演员分组（computed mainCastGroups）")
check('v-for="grp in mainCastGroups"' in _VUE, "主演员模板按分组渲染")
check("v-for=\"grp in groupByType(ep.people)\"" in _VUE, "分集模板按分组渲染")
check('v-for="(p, i) in libMainCast"' not in _VUE, "旧「主演员平铺循环」已移除")
check('v-for="(p, i) in ep.people"' not in _VUE, "旧「分集平铺循环」已移除")
check(_VUE.count('class="epl-type-sub"') == 2, f"段标题出现 2 处（主演员/分集），实际 {_VUE.count('class=\"epl-type-sub\"')}")
check(_VUE.count("> 1\" class=\"epl-type-sub\"") == 2 or _VUE.count('.length > 1" class="epl-type-sub"') == 2,
      "两处段标题都带「>1 种类型才显示」条件")
check(".epl-type-block { margin-top: 8px; }" in _VUE and ".epl-type-sub {" in _VUE, "新增段样式 CSS")
check("epl-actor-flow epl-actor-grid2" in _VUE, "两栏卡片布局保留（观感不变）")

# ─────────────────────────────────────────────
print("\n[T3] 用户场景：S01E01 → 演员4 / 客串1 / 导演1 / 编剧1")
# ─────────────────────────────────────────────
if node:
    _js2 = ((_m_lab.group(0) if _m_lab else "") + ";\n" + (_m_ord.group(0) if _m_ord else "") + ";\n"
            + _grab_fn("typeLabel") + "\n" + _grab_fn("groupByType") + """
const A=(name,type,role)=>({name_before:name, type:type, role_before:role||''});
const e01=[A('小岩井琴里','Actor','Renge (voice)'),A('村川 梨衣','Actor','Hotaru (voice)'),
           A('佐仓绫音','Actor','Natsumi (voice)'),A('阿澄 佳奈','Actor','Komari (voice)'),
           A('名冢 佳织','GuestStar','Kazuho (voice)'),A('川面真也','Director',''),A('吉田玲子','Writer','')];
const g=groupByType(e01);
console.log(g.map(x=>x.label+':'+x.list.length).join(' | '));
""")
    _t2 = Path(tempfile.mkdtemp(prefix="epl97b_")) / "t2.mjs"
    _t2.write_text(_js2, encoding="utf-8")
    _r2 = subprocess.run([node, str(_t2)], capture_output=True, timeout=60)
    _out2 = (_r2.stdout or b"").decode("utf-8", "replace").strip()
    check(_out2 == "演员:4 | 客串:1 | 导演:1 | 编剧:1", f"分段结果 = {_out2}")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)