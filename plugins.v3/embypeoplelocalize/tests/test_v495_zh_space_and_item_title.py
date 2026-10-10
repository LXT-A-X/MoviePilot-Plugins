# -*- coding: utf-8 -*-
"""v4.6.95 回归测试：两处口径修正。

运行：python tests/test_v495_zh_space_and_item_title.py

背景（用户实测《悠哉日常大王》，2026-10-09）：
① 库页「待翻译明细」里，第一排出现「名冢 佳织 / 村川 梨衣 / 新谷 良子 / 福圆 美里」——
   明明已是中文却仍算待翻译。根因：**汉字夹空格**。db.py 早在 v4.6.80 就把
   「含汉字且无假名」判为「已是中文」（空格不再是排除条件），但 __init__.py 的
   `_name_is_zh` 仍把「汉字夹空格」当日文名要求翻译 → 两处口径打架。
   （反证：同一批里「佐仓绫音 / 阿澄 佳奈」无空格，被正确跳过了。）
   另：`_tx_force_round`（重新翻译）未过 `_skip_no_translate` → 实际重翻比弹窗预估多翻，
   所以「重新翻译」也会把已中文的词条送去 LLM。
② 「待翻译明细」标题显示成某一**分集名**（《转学生来了》）而非**剧名**（《悠哉日常大王》）。
   根因：同一 item_id 下剧级行 title=剧名、各集行 title=集名，SQL 用 `MAX(title)`
   按字符序取最大 → 恰好选中集名（「转」U+8F6C > 「悠」「第」「吹」「上」）。

修正：
  A 口径对齐：`_name_is_zh` = 含汉字 且 不含假名（空格不再排除）；`_tx_force_round` 补
    `_skip_no_translate` 过滤。
  B 标题口径：新增 `_SQL_ITEM_TITLE` = 剧级行 title → series_name → MAX(title)，
    接入 `_pending_kind_sql`（含人数上限两分支）/ `pending_items_list` / `find_pending_items`。

覆盖：
  T1 _name_is_zh / _skip_no_translate（Python 口径 + zhconv）
  T2 源码级：口径对齐 + 强制重翻过滤 + _SQL_ITEM_TITLE 接入点
  T3 真实 SQLite：条目显示名 = 剧名（无人数上限 / 有人数上限 两分支都验）
  T4 用户场景：悠哉日常大王（Series 行 + 各集行）→ 《悠哉日常大王》且不含集名
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
TMP = Path(tempfile.mkdtemp(prefix="epl95_"))
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
_DB = (PLUGIN_DIR / "db.py").read_text(encoding="utf-8")

try:
    import zhconv  # type: ignore
    _HAS_ZHCONV = True
except Exception:
    zhconv = None
    _HAS_ZHCONV = False


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

_spec = importlib.util.spec_from_file_location("epl_db95", PLUGIN_DIR / "db.py")
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
print("v4.6.95 回归测试（汉字夹空格=已中文 / 条目显示名=剧名）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] _name_is_zh / _skip_no_translate：空格不再排除")
# ─────────────────────────────────────────────
_ns = {"logger": logger, "re": re, "Any": Any, "Optional": Optional, "List": List, "Dict": Dict}
for _mth in ("_looks_like_japanese", "_looks_like_chinese", "_looks_like_spaced_cjk_name",
             "_name_is_zh", "_skip_no_translate"):
    exec(_grab_method(_SRC, _mth), _ns)


class _Fake:
    """承载真实提取的方法；_zhconv_convert 用真 zhconv（不可用则恒等）。"""
    _looks_like_japanese = staticmethod(_ns["_looks_like_japanese"])
    _looks_like_chinese = staticmethod(_ns["_looks_like_chinese"])
    _looks_like_spaced_cjk_name = staticmethod(_ns["_looks_like_spaced_cjk_name"])
    _name_is_zh = _ns["_name_is_zh"]
    _skip_no_translate = _ns["_skip_no_translate"]

    @staticmethod
    def _zhconv_convert(s):
        if not _HAS_ZHCONV:
            return s
        try:
            return zhconv.convert(str(s), "zh-cn")
        except Exception:
            return s


_fk = _Fake()
check(_fk._name_is_zh("名冢 佳织") is True, "「名冢 佳织」（汉字夹空格）→ 已是中文（v4.6.95 修正）")
check(_fk._name_is_zh("村川 梨衣") is True, "「村川 梨衣」→ 已是中文")
check(_fk._name_is_zh("新谷 良子") is True, "「新谷 良子」→ 已是中文")
check(_fk._name_is_zh("福圆 美里") is True, "「福圆 美里」→ 已是中文")
check(_fk._name_is_zh("佐仓绫音") is True, "「佐仓绫音」（无空格）→ 已是中文")
check(_fk._name_is_zh("阿澄 佳奈") is True, "「阿澄 佳奈」→ 已是中文")
check(_fk._name_is_zh("田中 あいみ") is False, "「田中 あいみ」（含假名）→ 仍需翻译")
check(_fk._name_is_zh("水桥 かおり") is False, "「水桥 かおり」（含假名）→ 仍需翻译")
check(_fk._name_is_zh("Tom Hanks") is False, "英文 → 仍需翻译")
check(_fk._name_is_zh("") is False, "空 → 不是中文")

check(_fk._skip_no_translate("名冢 佳织") is True, "→ 名冢 佳织 被跳过（不进待翻）")
check(_fk._skip_no_translate("村川 梨衣") is True, "→ 村川 梨衣 被跳过")
check(_fk._skip_no_translate("佐仓绫音") is True, "→ 佐仓绫音 被跳过")
check(_fk._skip_no_translate("田中 あいみ") is False, "含假名 → 不跳过（会送 LLM）")
check(_fk._skip_no_translate("Tom Hanks") is False, "英文 → 不跳过")
check(_fk._looks_like_spaced_cjk_name("名冢 佳织") is True, "保留「空格写法」识别方法（仅供参考）")
check(_fk._looks_like_spaced_cjk_name("佐仓绫音") is False, "无空格 → 非空格写法")
if _HAS_ZHCONV:
    check(_fk._skip_no_translate("名塚 佳織") is False,
          "繁体/日文汉字「名塚 佳織」→ 繁转简会变，仍需翻译（不误伤繁→简）")

# ─────────────────────────────────────────────
print("\n[T2] 源码级：口径对齐 + 强制重翻过滤 + 标题聚合接入点")
# ─────────────────────────────────────────────
_nz = _grab_method(_SRC, "_name_is_zh")
check("_looks_like_spaced_cjk_name" not in _nz, "_name_is_zh 不再引用「汉字夹空格」排除")
check("_looks_like_japanese" in _nz, "_name_is_zh 仍排除含假名的日文名")
_fr = _grab_method(_SRC, "_tx_force_round")
check('and not self._skip_no_translate(o["text"])' in _fr,
      "强制重翻（_tx_force_round）已过滤「已是中文」词条（与弹窗预估同口径）")
check("_SQL_ITEM_TITLE" in _DB, "db.py 新增 _SQL_ITEM_TITLE（条目显示名聚合口径）")
check("MAX(CASE WHEN COALESCE(item_type,'')<>'Episode' THEN title END)" in _DB,
      "显示名优先取「剧级行（非 Episode）标题」")
check("MAX(NULLIF(series_name,''))" in _DB, "显示名回退到剧名 series_name")
check("person_index, MAX(title) AS title" not in _DB, "_pending_kind_sql 无人数上限分支已改")
check("MAX(item_type) AS item_type, MAX(title) AS title" not in _DB, "find_pending_items 已改")
_pk = _grab_method(_DB, "_pending_kind_sql")
check(_pk.count("_SQL_ITEM_TITLE} AS title") == 2, "两处 with_items 分支（有人数上限/无）都接入 _SQL_ITEM_TITLE")
check("item_type, series_name" in _pk, "SQL 中间层透传 item_type/series_name（供外层聚合）")

# ─────────────────────────────────────────────
print("\n[T3] 真实 SQLite：条目显示名 = 剧名")
# ─────────────────────────────────────────────
pdb = dbm.PeopleDb()
pdb.ensure_table()
PID = "EPL95"
_people_zh = [
    {"Type": "Actor", "before_name": "名冢 佳织", "Name": "名冢 佳织",
     "before_role": "Akane Shinoda (voice)", "Role": "Akane Shinoda (voice)"},
    {"Type": "Actor", "before_name": "小岩井琴里", "Name": "小岩井琴里",
     "before_role": "Renge (voice)", "Role": "Renge (voice)"},
]
pdb.upsert_people(plugin_id=PID, server_id="S1", item_id="66875", item_type="Series",
                  title="悠哉日常大王", series_name="", season_num=None, episode_num=None,
                  library_name="测试", people=_people_zh,
                  nfo_path=r"X:\悠哉日常大王\tvshow.nfo")
pdb.upsert_people(plugin_id=PID, server_id="S1", item_id="66875", item_type="Episode",
                  title="转学生来了", series_name="悠哉日常大王", season_num=1, episode_num=1,
                  library_name="测试", people=_people_zh,
                  nfo_path=r"X:\悠哉日常大王\S01\E01.nfo")
pdb.upsert_people(plugin_id=PID, server_id="S1", item_id="66875", item_type="Episode",
                  title="上一年级了", series_name="悠哉日常大王", season_num=2, episode_num=1,
                  library_name="测试", people=_people_zh,
                  nfo_path=r"X:\悠哉日常大王\S02\E01.nfo")


def _titles(limits):
    _r = pdb.pending_terms_full(plugin_id=PID, limits=limits, only_pending=True,
                                exclude_episodes=False) or {}
    return sorted({str(x.get("title") or "") for x in (_r.get("names") or [])}), _r


_t_a, _r_a = _titles(None)
check(_t_a == ["悠哉日常大王"], f"无人数上限：所有行 title = 剧名，实际 {_t_a}")
check("转学生来了" not in _t_a and "上一年级了" not in _t_a, "不再出现分集名（旧 MAX(title) 的 bug）")
_t_b, _r_b = _titles({"movie": {"actor": 0}, "tvshow": {"actor": 10}, "episode": {"actor": 10}})
check(_t_b == ["悠哉日常大王"], f"有人数上限（复杂 SQL 分支）：title = 剧名，实际 {_t_b}")
check(len(_r_a.get("names") or []) > 0, "确实取到了人名词条（非空跑）")

# 只有集行、无剧级行 → 回退到 series_name
pdb.upsert_people(plugin_id=PID, server_id="S1", item_id="70001", item_type="Episode",
                  title="某集名", series_name="某剧名", season_num=1, episode_num=1,
                  library_name="测试", people=_people_zh,
                  nfo_path=r"X:\某剧名\S01\E01.nfo")
_r2 = pdb.pending_terms_full(plugin_id=PID, limits=None, only_pending=True,
                             exclude_episodes=False) or {}
_t2 = sorted({str(x.get("title") or "") for x in (_r2.get("names") or [])})
check(_t2 == ["悠哉日常大王", "某剧名"], f"纯集行条目回退到剧名，实际 {_t2}")
check("某集名" not in _t2, "纯集行也不显示集名（回退 series_name）")

# ─────────────────────────────────────────────
print("\n[T4] 用户场景：悠哉日常大王 → 《悠哉日常大王》")
# ─────────────────────────────────────────────
_r3 = pdb.pending_terms_full(plugin_id=PID, limits=None, only_pending=True,
                             exclude_episodes=False) or {}
_by_item = {}
for _k in ("names", "roles"):
    for _x in (_r3.get(_k) or []):
        if str(_x.get("item_id")) == "66875":
            _by_item[str(_x.get("term"))] = str(_x.get("title") or "")
check(set(_by_item.values()) == {"悠哉日常大王"}, f"该条目全部词条 title 均为剧名，实际 {set(_by_item.values())}")
check("名冢 佳织" in _by_item, "名冢 佳织 仍在库里（只是不再算待翻/不再重复显示）")
_pd = _grab_method(_SRC, "_api_db_pending_detail")
check('"title": str(it.get("title") or it.get("item_id") or "")' in _pd,
      "待翻译明细直接采用快照 title（修正后即显示剧名）")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)