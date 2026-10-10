# -*- coding: utf-8 -*-
"""v4.6.96 回归测试：同一人重复 credit（<writer> + <credits>）去重。

运行：python tests/test_v496_duplicate_credit.py

背景（用户实测，2026-10-09）：库页右侧「分集演员」里 E01 出现两个「吉田玲子」（无角色），
但 Emby 只显示一个。根因：源 nfo 把同一个人同时写了两个 credit 标签
（`<writer>吉田玲子</writer>` + `<credits>吉田玲子</credits>`，实测
`Z:\\影视资源\\测试\\悠哉日常大王\\Season 01\\悠哉日常大王S01E01.nfo` 第 46/47 行），
插件按标签各采集一条 → 库里两行；Emby 按「人物」展示，所以只有一个。

修正（两层）：
  采集层 `_dedup_credit_people`：同一 nfo 内「原文名 + 角色」完全相同只保留先出现的一条
    （`_record_nfo_library` 落库前调用）→ 从源头不再产生重复行，重扫即清理历史重复。
  展示层 `_dedup_credit_rows`：`_api_db_people` 对「剧级名单 + 各集名单」按
    「name_before + role_before」去重 → 历史重复行无需重扫也立刻只显示一个。

覆盖：
  T1 _dedup_credit_people（采集层）：同人同角色去重 / 不同角色保留 / 保序 / 空值
  T2 _dedup_credit_rows（展示层）：同口径
  T3 源码级：两处接线位置
  T4 集成（真实 SQLite）：模拟真实重复行 → 剧级/分集都只显示一个；不同角色不被误合
"""
import sys
import re
import types
import textwrap
import tempfile
import importlib.util
from pathlib import Path
from typing import Any, List, Optional, Dict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl96_"))
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


class _S:
    CONFIG_PATH = str(TMP)


_c.settings = _S()
sys.modules.update({"app": _m, "app.sdk": _s, "app.sdk.logging": _l, "app.sdk.config": _c})

_spec = importlib.util.spec_from_file_location("epl_db96", PLUGIN_DIR / "db.py")
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
print("v4.6.96 回归测试（重复 credit 去重：<writer> + <credits> 同人）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] _dedup_credit_people（采集层）")
# ─────────────────────────────────────────────
_ns = {"logger": logger, "Any": Any, "Optional": Optional, "List": List, "Dict": Dict}
exec(_grab_method(_SRC, "_dedup_credit_people"), _ns)
exec(_grab_method(_SRC, "_dedup_credit_rows"), _ns)
_dp = _ns["_dedup_credit_people"]
_dr = _ns["_dedup_credit_rows"]


def _P(name, role, typ="Writer"):
    return {"Type": typ, "before_name": name, "Name": name, "before_role": role, "Role": role}


_src_people = [
    _P("小岩井琴里", "Renge (voice)", "Actor"),
    _P("吉田玲子", "", "Writer"),
    _P("吉田玲子", "", "Producer"),          # 同一人同角色（不同标签）→ 应去重
    _P("川面真也", "", "Director"),
    _P("声优A", "角色A", "Actor"),
    _P("声优A", "角色B", "Actor"),            # 同名不同角色 → 两条都应保留
]
_out = _dp(_src_people)
_names = [p["before_name"] for p in _out]
check(len(_out) == 5, f"6 条 → 5 条（吉田玲子×2 合 1），实际 {len(_out)}")
check(_names.count("吉田玲子") == 1, "「吉田玲子」只剩 1 条")
check(_names.count("声优A") == 2, "「声优A」两条（不同角色）都保留")
check(_names[0] == "小岩井琴里" and _names[1] == "吉田玲子", "保序（保留先出现者）")
check(_out[1]["Type"] == "Writer", "保留先出现的类型（Writer，先于 credits/Producer）")
check(_dp([]) == [] and _dp(None) == [], "空 / None → 空列表")
check(_dp([_P("角田 雄二郎", "")]) == [_P("角田 雄二郎", "")], "单条原样返回")
_pad = _dp([_P("吉田玲子", " "), _P("吉田玲子", "")])
check(len(_pad) == 1, "角色空白差异（'' vs ' '）按 strip 后视为同一条 → 去重")

# ─────────────────────────────────────────────
print("\n[T2] _dedup_credit_rows（展示层）")
# ─────────────────────────────────────────────


def _R(name, role):
    return {"name_before": name, "role_before": role, "name_after": name, "index": 0}


_rows = [_R("吉田玲子", ""), _R("吉田玲子", ""), _R("川面真也", ""), _R("声优A", "角色A"),
         _R("声优A", "角色B")]
_out2 = _dr(_rows)
check(len(_out2) == 4, f"5 行 → 4 行，实际 {len(_out2)}")
check([r["name_before"] for r in _out2].count("吉田玲子") == 1, "「吉田玲子」只留一条")
check([r["name_before"] for r in _out2].count("声优A") == 2, "不同角色的同名保留两条")
check(_dr([]) == [] and _dr(None) == [], "空 / None → 空列表")

# ─────────────────────────────────────────────
print("\n[T3] 源码级：两处接线")
# ─────────────────────────────────────────────
_rec = _grab_method(_SRC, "_record_nfo_library")
check("people = self._dedup_credit_people(people)" in _rec,
      "采集层：_record_nfo_library 落库前调用 _dedup_credit_people")
check(_rec.index("_dedup_credit_people(people)") < _rec.index("if not people:"),
      "去重发生在「空名单早退」之前")
_pd = _grab_method(_SRC, "_api_db_people")
check("_main_cast = self._dedup_credit_rows(_main_cast)" in _pd, "展示层：剧级名单去重")
check('_ep["people"] = self._dedup_credit_rows(_ep.get("people") or [])' in _pd, "展示层：各集名单去重")

# ─────────────────────────────────────────────
print("\n[T4] 集成（真实 SQLite）：模拟真实重复行 → 只显示一个")
# ─────────────────────────────────────────────
pdb = dbm.PeopleDb()
pdb.ensure_table()


class _Fake96:
    """承载真实提取的 _api_db_people；plugin_id = 类名。"""
    _people_db = pdb
    _dedup_credit_rows = staticmethod(_dr)


PID = _Fake96.__name__
_TV = [
    {"Type": "Writer", "before_name": "吉田玲子", "Name": "吉田玲子", "before_role": "", "Role": ""},
    {"Type": "Producer", "before_name": "吉田玲子", "Name": "吉田玲子", "before_role": "", "Role": ""},
    {"Type": "Actor", "before_name": "小岩井琴里", "Name": "小岩井琴里",
     "before_role": "Renge (voice)", "Role": "Renge (voice)"},
]
pdb.upsert_people(plugin_id=PID, server_id="S1", item_id="66875", item_type="Series",
                  title="悠哉日常大王", series_name="", season_num=None, episode_num=None,
                  library_name="测试", people=_TV, nfo_path=r"X:\悠哉日常大王\tvshow.nfo")
_E1 = [
    {"Type": "Actor", "before_name": "小岩井琴里", "Name": "小岩井琴里",
     "before_role": "Renge (voice)", "Role": "Renge (voice)"},
    {"Type": "Writer", "before_name": "吉田玲子", "Name": "吉田玲子", "before_role": "", "Role": ""},
    {"Type": "Producer", "before_name": "吉田玲子", "Name": "吉田玲子", "before_role": "", "Role": ""},
    {"Type": "Director", "before_name": "川面真也", "Name": "川面真也", "before_role": "", "Role": ""},
    {"Type": "Actor", "before_name": "声优A", "Name": "声优A", "before_role": "角色A", "Role": "角色A"},
    {"Type": "Actor", "before_name": "声优A", "Name": "声优A", "before_role": "角色B", "Role": "角色B"},
]
pdb.upsert_people(plugin_id=PID, server_id="S1", item_id="66875", item_type="Episode",
                  title="转学生来了", series_name="悠哉日常大王", season_num=1, episode_num=1,
                  library_name="测试", people=_E1, nfo_path=r"X:\悠哉日常大王\Season 01\E01.nfo")

_api = _grab_method(_SRC, "_api_db_people")
_ns2 = {"logger": logger, "Any": Any, "Optional": Optional, "List": List, "Dict": Dict}
exec(_api, _ns2)
_obj = _Fake96()
_obj._api_db_people = types.MethodType(_ns2["_api_db_people"], _obj)
_res = _obj._api_db_people(item_id="66875", server_id="S1")
check(_res.get("success") is True, f"接口调用成功（{_res.get('message', '')}）")
_data = _res.get("data") or {}
_flat = _data.get("people") or []
_mc = _data.get("main_cast") or []
_eps = _data.get("episodes") or []
check(len(_flat) == 9, f"扁平 people 保持原样（不去重，9 行），实际 {len(_flat)}")
check(len(_mc) == 2, f"剧级名单：3 行 → 2 行（吉田玲子合 1），实际 {len(_mc)}")
check([p["name_before"] for p in _mc].count("吉田玲子") == 1, "剧级名单里吉田玲子只 1 个")
check(len(_eps) == 1, f"分集列表 1 集，实际 {len(_eps)}")
_ep_people = (_eps[0].get("people") or []) if _eps else []
check(len(_ep_people) == 5, f"分集名单：6 行 → 5 行，实际 {len(_ep_people)}")
check([p["name_before"] for p in _ep_people].count("吉田玲子") == 1,
      "分集名单里「吉田玲子」只显示 1 个（用户实测的重复已消除）")
check([p["name_before"] for p in _ep_people].count("声优A") == 2, "同名不同角色仍保留 2 个（不误合）")
check("小岩井琴里" in [p["name_before"] for p in _ep_people], "正常演员不受影响")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)