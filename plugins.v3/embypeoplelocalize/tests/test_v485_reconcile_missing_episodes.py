# -*- coding: utf-8 -*-
"""v4.6.85 回归测试：容器仍在 Emby 时「只标真正消失的那几集」。

运行：python tests/test_v485_reconcile_missing_episodes.py

背景：v4.6.84 起，Emby 发容器级删除（Type=Series）但容器**仍在**时不再整树标记 ——
      这修好了「只动几集却标整部剧」，但也导致「用户真删掉的那几集在失效列表里查不到」。
本版补上：容器仍在时，把**库里登记的集**与**Emby 实际的集**做差集，
      只把真正消失的集标记观察期（同剧其它集一律不碰），并登记「失效 / 待恢复」事件。

覆盖：
  T1 episode_pairs_under_prefix：只返回前缀内、带季集的行（去重升序）
  T2 mark_deleted_episodes_by_prefix：只标指定集，其它集/剧级行不动
  T3 _reconcile_missing_episodes：差集正确；任一侧数据缺失时保守返回 []
  T4 源码级：容器仍在分支接入「比对 + 精确标记 + 事件/通知」
"""
import sys
import re
import types
import textwrap
import tempfile
import importlib.util
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl85_"))
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

_spec = importlib.util.spec_from_file_location("epl_db85", PLUGIN_DIR / "db.py")
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
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent and ln.lstrip().startswith("def "):
            break
        out.append(ln)
    return textwrap.dedent("\n".join(out))


print("=" * 72)
print("v4.6.85 回归测试（容器仍在 → 只标真正消失的集）")
print("=" * 72)

PID = "EPL85"
SHOW = "X:/lib/Show"
dbm.PeopleDb.ensure_table()
_seed = [
    ("X:/lib/Show/Season 1/S01E01.nfo", 1, 1, "Episode"),
    ("X:/lib/Show/Season 1/S01E02.nfo", 1, 2, "Episode"),
    ("X:/lib/Show/Season 1/S01E03.nfo", 1, 3, "Episode"),
    ("X:/lib/Show/Season 2/S02E01.nfo", 2, 1, "Episode"),
    ("X:/lib/Show/tvshow.nfo", None, None, "Series"),
    ("X:/other/Other/movie.nfo", None, None, "Movie"),
]
for _np, _s, _e, _ty in _seed:
    dbm._x("INSERT INTO person (plugin_id, server_id, item_id, item_type, title, nfo_path, "
           "season_num, episode_num, person_type, name_before) VALUES (?,?,?,?,?,?,?,?,'Actor','N')",
           (PID, "S1", "224207" if "Show" in _np else "999", _ty, "迷途之子!!!!!", _np, _s, _e))

# ─────────────────────────────────────────────
print("\n[T1] episode_pairs_under_prefix：前缀内、带季集的行（去重升序）")
# ─────────────────────────────────────────────
_pairs = dbm.PeopleDb().episode_pairs_under_prefix(plugin_id=PID, path_prefix=SHOW, server_id="S1")
check(_pairs == [(1, 1), (1, 2), (1, 3), (2, 1)],
      f"只返回该剧目录下带季集的 4 集（剧级行/别的目录不算），实际 {_pairs}")
check(dbm.PeopleDb().episode_pairs_under_prefix(plugin_id=PID, path_prefix="X:/none", server_id="S1") == [],
      "前缀不命中 → 空")
check(dbm.PeopleDb().episode_pairs_under_prefix(plugin_id=PID, path_prefix="", server_id="S1") == [],
      "空前缀 → 空（不误查全库）")

# ─────────────────────────────────────────────
print("\n[T2] mark_deleted_episodes_by_prefix：只标指定集")
# ─────────────────────────────────────────────
_n = dbm.PeopleDb().mark_deleted_episodes_by_prefix(plugin_id=PID, path_prefix=SHOW,
                                                    pairs=[(1, 2), (1, 3)], server_id="S1")
check(_n == 2, f"标记 2 行（S01E02 / S01E03），实际 {_n}")


def _is_dead(_np):
    r = dbm._q1("SELECT COUNT(*) c FROM person WHERE plugin_id=? AND nfo_path=? "
                "AND deleted_at IS NOT NULL AND deleted_at<>''", (PID, _np))
    return bool(r and int(r.get("c") or 0) > 0)


check(not _is_dead("X:/lib/Show/Season 1/S01E01.nfo"), "S01E01 未被标记（同剧其它集不动）")
check(_is_dead("X:/lib/Show/Season 1/S01E02.nfo"), "S01E02 已进入观察期")
check(_is_dead("X:/lib/Show/Season 1/S01E03.nfo"), "S01E03 已进入观察期")
check(not _is_dead("X:/lib/Show/Season 2/S02E01.nfo"), "S02E01 未被标记")
check(not _is_dead("X:/lib/Show/tvshow.nfo"), "剧级行未被标记（容器仍在，不整树标记）")
check(not _is_dead("X:/other/Other/movie.nfo"), "别的目录完全不受影响")
_n2 = dbm.PeopleDb().mark_deleted_episodes_by_prefix(plugin_id=PID, path_prefix=SHOW,
                                                     pairs=[(1, 2)], server_id="S1")
check(_n2 == 0, f"重复标记同一集 → 0（不会重复计数），实际 {_n2}")

# ─────────────────────────────────────────────
print("\n[T3] _reconcile_missing_episodes：差集正确 / 数据缺失时保守不标")
# ─────────────────────────────────────────────
_ns = {"logger": logger,
       # v4.6.99：枚举三态常量（与 emby_client 同名同值）
       "ITEM_FOUND": "found", "ITEM_NOT_FOUND": "not_found", "ITEM_UNAVAILABLE": "unavailable"}
exec(_grab_method(_SRC, "_reconcile_missing_episodes"), _ns)


class _FakeClient:
    """v4.6.99：提供「枚举完整性三态」接口（get_series_episodes_status / query_items_status）。"""

    def __init__(self, eps=None, boom=False, season_eps=None,
                 series_status=None, season_status=None):
        self._eps = eps if eps is not None else []
        self._boom = boom
        self._season_eps = season_eps
        self._series_status = series_status
        self._season_status = season_status

    def get_series_episodes_status(self, series_id, limit=200):
        if self._boom:
            return "unavailable", [], "exception"
        if self._series_status:
            return self._series_status, [], "forced"
        return "found", list(self._eps), ""

    def query_items_status(self, params=None):
        if self._boom:
            return "unavailable", {"Items": [], "TotalRecordCount": 0}, "exception"
        if self._season_status:
            return self._season_status, {"Items": [], "TotalRecordCount": 0}, "forced"
        if self._season_eps is None:
            return "found", {"Items": [], "TotalRecordCount": 0}, ""
        return "found", {"Items": list(self._season_eps),
                         "TotalRecordCount": len(self._season_eps)}, ""


_K = type(PID, (object,), {})
_K._reconcile_missing_episodes = _ns["_reconcile_missing_episodes"]


def _mk_self():
    o = _K()
    o._people_db = dbm.PeopleDb()
    return o


# 剧容器：库里有 S1E01~03 + S2E01；Emby 只剩 S1E01 + S2E01 → 少了 S1E02/S1E03
_cli = _FakeClient([{"ParentIndexNumber": 1, "IndexNumber": 1},
                    {"ParentIndexNumber": 2, "IndexNumber": 1}])
_miss, _ok, _why = _mk_self()._reconcile_missing_episodes(_cli, "32027", SHOW, "S1", "series")
check(_miss == [(1, 2), (1, 3)] and _ok is True,
      f"剧容器差集 = 真正消失的 2 集（且枚举可信），实际 {_miss} / {_ok}")

# Emby 侧一集不缺 → 枚举成功、差集为空（不标记）
_cli2 = _FakeClient([{"ParentIndexNumber": s, "IndexNumber": e}
                     for (s, e) in [(1, 1), (1, 2), (1, 3), (2, 1)]])
check(_mk_self()._reconcile_missing_episodes(_cli2, "32027", SHOW, "S1", "series") == ([], True, ""),
      "Emby 一集不缺 → ([], 可信)（不标记）")
# v4.6.99：查询失败/异常 → 枚举**不可信**（旧版这里是「(空, False) 由调用方退化为整季标记」，
# 现在调用方一律不标记，避免把仍存在的整季误标）
_r = _mk_self()._reconcile_missing_episodes(_FakeClient(boom=True), "32027", SHOW, "S1", "series")
check(_r[0] == [] and _r[1] is False and "exception" in _r[2], f"Emby 调用异常 → 不可信 {_r}")
_r = _mk_self()._reconcile_missing_episodes(
    _FakeClient(series_status="unavailable"), "32027", SHOW, "S1", "series")
check(_r[0] == [] and _r[1] is False and "unavailable" in _r[2], f"剧集枚举 HTTP 失败 → 不可信 {_r}")
check(_mk_self()._reconcile_missing_episodes(_cli, "32027", "X:/none", "S1", "series") == ([], True, "no_db_rows"),
      "库里前缀下无记录 → (可信、无差异)（无东西可标）")
o = _K(); o._people_db = None
check(o._reconcile_missing_episodes(_cli, "32027", SHOW, "S1", "series")[1] is False, "无数据库 → 不可信")
check(_mk_self()._reconcile_missing_episodes(None, "32027", SHOW, "S1", "series")[1] is False,
      "无 Emby 客户端 → 不可信")

# ── 季容器（删第一季）：只比对该季，第二/三季天然不受影响 ──
S1DIR = "X:/lib/Show/Season 1"
_cli_s = _FakeClient(season_eps=[{"ParentIndexNumber": 1, "IndexNumber": 1}])
_miss_s, _ok_s, _why_s = _mk_self()._reconcile_missing_episodes(_cli_s, "55001", S1DIR, "S1", "season")
check(_miss_s == [(1, 2), (1, 3)] and _ok_s is True,
      f"季容器：该季只剩 S01E01 → 少了 S01E02/S01E03，实际 {_miss_s} / {_ok_s}")
# v4.6.99：查询失败 → **不可信**（不再退化为整季前缀标记）
_r = _mk_self()._reconcile_missing_episodes(
    _FakeClient(season_status="unavailable"), "55001", S1DIR, "S1", "season")
check(_r[0] == [] and _r[1] is False, f"季容器查询失败 → 不可信、不标记（不再退化为整季）{_r}")
# 成功但总数 > 实际返回 = 分页不完整 → 不可信
check(_mk_self()._reconcile_missing_episodes(_FakeClient(season_eps=[{"ParentIndexNumber": 1,
                                                                     "IndexNumber": 1}]),
                                             "55001", S1DIR, "S1", "season")[1] is True,
      "季容器成功且总数一致 → 可信")
check(_mk_self()._reconcile_missing_episodes(_FakeClient(season_eps=[{"IndexNumber": 1}]), "55001",
                                             S1DIR, "S1", "season")[1] is False,
      "季容器返回的集缺季号（脏数据/结构异常）→ 不可信（不乱标）")

# ─────────────────────────────────────────────
print("\n[T4] 源码级：容器仍在分支接入「比对 + 精确标记 + 事件/通知」")
# ─────────────────────────────────────────────
_del = _grab_method(_SRC, "_handle_webhook_delete")
# v4.6.98：容器存在性改为三态 —— 「容器仍在」分支的入口由 `if _still:` 变为
# `if _cst == ITEM_FOUND:`（UNAVAILABLE 走「状态未知 → 不按真删除处理」另一分支）。
_i = _del.find("if _cst == ITEM_FOUND:")
check(_i > 0, "容器分支改用三态判定（if _cst == ITEM_FOUND:）")
_seg = _del[_i:_i + 3600]
check("_reconcile_missing_episodes" in _seg, "容器仍在 → 调用缺失集比对")
check("mark_deleted_episodes_by_prefix" in _seg, "只按季集精确标记（不再整树标记）")
check("_miss_pairs, _ok, _reason = self._reconcile_missing_episodes(" in _seg,
      "接收 (缺失集, 枚举是否可信, 原因) 三个返回值（区分「可信的空」与「枚举不可信」）")
check('(not _enumerable) and _ct == "season"' not in _seg,
      "v4.6.99：已移除「季容器枚举不到 → 整季标记」退化（枚举不可信一律不标记）")
check("if not _ok:" in _seg and "无法确认" in _seg,
      "枚举不可信 → 登记待确认、不标记（安全退出）")
check('"missing"' in _seg and "已不存在" in _seg, "登记「失效 / 待恢复」事件并写明少了几集")
check("_enqueue_delete_notification" in _seg, "发删除通知（含集数）")
check("if _mk > 0:" in _seg and "return" in _seg, "分支内有标记判定并以 return 收束")
# v4.6.98：状态未知（查询失败 / 401 / 500 / 无 user_id）→ 绝不按真删除处理
_iu = _del.find("if _cst == ITEM_UNAVAILABLE:")
check(_iu > 0, "新增「容器状态未知」分支（if _cst == ITEM_UNAVAILABLE:）")
_useg = _del[_iu:_iu + 1200]
check("无法确认" in _useg, "状态未知文案：删除状态无法确认（不写「已进入观察期」）")
check("if _mk" not in _useg and "mark_deleted" not in _useg, "状态未知分支内不做任何标记写库")
check("return" in _useg, "状态未知分支以 return 收束（不落入真删除标记）")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
