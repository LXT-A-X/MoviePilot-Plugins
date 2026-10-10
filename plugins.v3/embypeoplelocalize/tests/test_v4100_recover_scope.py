# -*- coding: utf-8 -*-
"""v4.6.100 回归测试：恢复判定越界修复（剧级 tvshow.nfo 不得清扫整剧观察期）。

运行：python tests/test_v499_enum_lock_snapshot.py 之后
     python tests/test_v4100_recover_scope.py

背景（线上实测）：悠哉日常大王 删 S02E01/S03E01（标记 19 行）→ 放回 2 集 → 整剧入库时
  nfo_items 的首项是**剧级 tvshow.nfo**，它没有季集上下文，
  is_deleted_by_media(item_id=..., 季集=None) 会退化成「匹配该剧所有观察期行」，
  于是 tvshow NFO 一次性把 19 行全清了（recovered 只记 1），随后 4 个单集 NFO 判定为空。
  结果碰巧正确（两集都回来了），但**只删 1 集**时，任何整剧入库都会误清该集观察期。

覆盖：
  T1 源码级：_sweep_ok 门槛（电影/带季集的单集才做身份清扫；剧级只认 nfo_path）
  T2 行为级：剧级身份谓词确实“能命中整剧”（危险），但门禁后剧级判定为 False
  T3 行为级：单集精确恢复（只清自己那集；同剧其它集保持观察期）→ 计数为 NFO 文件数
  T4 行为级：只删 1 集，整剧入库（tvshow 先跑）不再误清该集观察期
  T5 行为级：恢复别名去重键含 old_nfo_path → 同剧多集各留一条旧身份
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
TMP = Path(tempfile.mkdtemp(prefix="epl100_"))
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")

_N = [0, 0]


def check(cond, msg):
    _N[0] += 1
    if cond:
        print(f"  [PASS] {msg}")
    else:
        _N[1] += 1
        print(f"  [FAIL] {msg}")


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

_spec = importlib.util.spec_from_file_location("epl_db100", PLUGIN_DIR / "db.py")
dbm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dbm)


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
print("v4.6.100 回归测试（恢复判定越界修复）")
print("=" * 72)

PID = "EmbyPeopleLocalize"
SID = "___1_192_168_2_15_8096"
SERIES = "悠哉日常大王"
PREFIX = "/video/影视资源/测试/悠哉日常大王"

# ─────────────────────────────────────────────
print("\n[T1] 源码级：_sweep_ok 门槛")
# ─────────────────────────────────────────────
_body = _grab_method(_SRC, "_ingest_nfo_pending")
check('_sweep_ok = (_lv == "movie") or (_lv == "episode" and (_ssn is not None or _epn is not None))' in _body,
      "_sweep_ok 定义为「电影 或 带季集的单集」")
check(_body.count("_sweep_ok") >= 4,
      f"_sweep_ok 在判定/清除两处均被引用（出现 {_body.count('_sweep_ok')} 次）")
check(_body.index("if _sweep_ok:") < _body.index("_db.is_deleted_by_media("),
      "强身份判定 is_deleted_by_media 被 if _sweep_ok 守卫")
check(_body.index("elif _sweep_ok:") < _body.index("deleted_weak_candidates("),
      "弱匹配 deleted_weak_candidates 被 elif _sweep_ok 守卫")
_tail = _body[_body.index("if recovered:"):]
check("if _sweep_ok:" in _tail and _tail.index("if _sweep_ok:") < _tail.index("clear_deleted_by_media("),
      "清除 clear_deleted_by_media 被 if _sweep_ok 守卫")
check("_db.clear_deleted(plugin_id=_pid, nfo_path=nfo_path" in _tail,
      "行级 clear_deleted 不受 _sweep_ok 限制（剧级 NFO 仍可解除剧级行）")

# ─────────────────────────────────────────────
print("\n[T2] 行为级：剧级身份谓词「越界」能力 + 门禁后剧级判定为 False")
# ─────────────────────────────────────────────
dbm.PeopleDb.ensure_table()
_ins = ("INSERT INTO person (plugin_id, server_id, item_id, item_type, title, series_name, "
        "season_num, episode_num, person_index, person_type, name_before, name_after, "
        "role_before, role_after, nfo_path, deleted_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'')")
_rows = []
for _i in range(10):
    _rows.append((PID, SID, "66875", "Episode", "上一年级了", SERIES, 2, 1, _i, "Actor",
                  f"S2-{_i}", f"S2-{_i}", "role", "role",
                  f"{PREFIX}/Season 02/悠哉日常大王S02E01.nfo"))
for _i in range(9):
    _rows.append((PID, SID, "66875", "Episode", "吹一曲青蛙的歌", SERIES, 3, 1, _i, "Actor",
                  f"S3-{_i}", f"S3-{_i}", "role", "role",
                  f"{PREFIX}/Season 03/悠哉日常大王S03E01.nfo"))
for _i in range(4):
    _rows.append((PID, SID, "66875", "Series", SERIES, SERIES, None, None, _i, "Actor",
                  f"SER-{_i}", f"SER-{_i}", "role", "role", f"{PREFIX}/tvshow.nfo"))
for _r in _rows:
    dbm._x(_ins, _r)
check(len(dbm._q("SELECT id FROM person WHERE plugin_id=?", (PID,))) == 23, "已插入 23 行（S2E1:10 / S3E1:9 / 剧级:4）")

_n_mark = dbm.PeopleDb().mark_deleted_episodes_by_prefix(
    plugin_id=PID, path_prefix=PREFIX, pairs=[(2, 1), (3, 1)], server_id=SID)
check(_n_mark == 19, f"标记 S2E1+S3E1 共 19 行（实际 {_n_mark}）")

_pdb = dbm.PeopleDb()
_dangerous = _pdb.is_deleted_by_media(
    plugin_id=PID, item_id="66875", media_provider="tmdb", media_id="66875",
    series_media_id="66875", emby_item_id="32063",
    season_num=None, episode_num=None, server_id=SID)
check(_dangerous == 19,
      f"剧级身份（季集=None）谓词仍会命中整剧 19 行 —— 这正是必须门禁的原因（实际 {_dangerous}）")

_tv_path_ok = _pdb.is_deleted_by_nfo_path(
    plugin_id=PID, nfo_path=f"{PREFIX}/tvshow.nfo", server_id=SID)
check(_tv_path_ok is False,
      "剧级 NFO 走 nfo_path 精确判定 → False（剧级行未被标记，不误报恢复）")

_ep2 = _pdb.is_deleted_by_media(
    plugin_id=PID, item_id="66875", media_provider="tmdb", media_id="66875",
    series_media_id="66875", emby_item_id="32083",
    season_num=2, episode_num=1, server_id=SID)
check(_ep2 == 10, f"单集 S2E1 判定命中 10 行（实际 {_ep2}）")

# ─────────────────────────────────────────────
print("\n[T3] 行为级：单集精确恢复 + 计数 = NFO 文件数")
# ─────────────────────────────────────────────
_cl2 = _pdb.clear_deleted_by_media(
    plugin_id=PID, item_id="66875", media_provider="tmdb", media_id="66875",
    series_media_id="66875", emby_item_id="32083",
    season_num=2, episode_num=1, server_id=SID)
check(_cl2 == 10, f"清 S2E1 只清 10 行（实际 {_cl2}）")
_left = dbm._q("SELECT COALESCE(season_num,-1) s, COALESCE(episode_num,-1) e, COUNT(*) n FROM person "
               "WHERE plugin_id=? AND deleted_at IS NOT NULL AND deleted_at<>'' GROUP BY s, e", (PID,))
check([(int(r["s"]), int(r["e"]), int(r["n"])) for r in _left] == [(3, 1, 9)],
      f"同剧 S3E1 的 9 行仍保持观察期（实际 {[(int(r['s']), int(r['e']), int(r['n'])) for r in _left]}）")

_ep3 = _pdb.is_deleted_by_media(
    plugin_id=PID, item_id="66875", media_provider="tmdb", media_id="66875",
    series_media_id="66875", emby_item_id="32084",
    season_num=3, episode_num=1, server_id=SID)
check(_ep3 == 9, f"单集 S3E1 判定命中 9 行（实际 {_ep3}）")
_cl3 = _pdb.clear_deleted_by_media(
    plugin_id=PID, item_id="66875", media_provider="tmdb", media_id="66875",
    series_media_id="66875", emby_item_id="32084",
    season_num=3, episode_num=1, server_id=SID)
check(_cl3 == 9, f"清 S3E1 只清 9 行（实际 {_cl3}）")
check(int(dbm._q1("SELECT COUNT(*) c FROM person WHERE plugin_id=? AND deleted_at IS NOT NULL "
                  "AND deleted_at<>''", (PID,))["c"]) == 0, "两集恢复后无残留观察期行")

_recovered = (1 if _ep2 > 0 else 0) + (1 if _ep3 > 0 else 0)
check(_recovered == 2, f"恢复计数按 NFO 文件数 = 2（旧行为会被剧级 NFO 抢跑记成 1；实际 {_recovered}）")

# ─────────────────────────────────────────────
print("\n[T4] 行为级：只删 1 集 → 整剧入库（tvshow 先跑）不再误清")
# ─────────────────────────────────────────────
dbm._x("UPDATE person SET deleted_at='' WHERE plugin_id=?", (PID,))
_n1 = _pdb.mark_deleted_episodes_by_prefix(
    plugin_id=PID, path_prefix=PREFIX, pairs=[(2, 1)], server_id=SID)
check(_n1 == 10, f"只标 S2E1 → 10 行（实际 {_n1}）")

# 旧路径（无门禁）：剧级身份判定会命中 10 行 → 误判「已恢复」
_d_old = _pdb.is_deleted_by_media(
    plugin_id=PID, item_id="66875", media_provider="tmdb", media_id="66875",
    series_media_id="66875", emby_item_id="32063",
    season_num=None, episode_num=None, server_id=SID)
check(_d_old == 10, f"（对照）剧级身份判定本会命中 {_d_old} 行 → 即旧的越界清除")

# 新逻辑：剧级只走 nfo_path 精确判定 → False，不触发任何清除
_tv_ok2 = _pdb.is_deleted_by_nfo_path(
    plugin_id=PID, nfo_path=f"{PREFIX}/tvshow.nfo", server_id=SID)
check(_tv_ok2 is False, "剧级 NFO 精确判定仍为 False → 不会清 S2E1 的观察期")
check(int(dbm._q1("SELECT COUNT(*) c FROM person WHERE plugin_id=? AND deleted_at IS NOT NULL "
                  "AND deleted_at<>''", (PID,))["c"]) == 10,
      "整剧入库后 S2E1 仍完整保持观察期（10 行未被误清）")

# ─────────────────────────────────────────────
print("\n[T5] 行为级：恢复别名去重键含 old_nfo_path")
# ─────────────────────────────────────────────
dbm._x("DELETE FROM media_identity_alias WHERE plugin_id=?", (PID,))
dbm._x("UPDATE person SET deleted_at='' WHERE plugin_id=?", (PID,))
_pdb.mark_deleted_episodes_by_prefix(plugin_id=PID, path_prefix=PREFIX, pairs=[(2, 1), (3, 1)], server_id=SID)
for _s in _pdb.sample_deleted_identities(
        plugin_id=PID, item_id="66875", media_provider="tmdb", media_id="66875",
        series_media_id="66875", emby_item_id="32063",
        season_num=None, episode_num=None, server_id=SID) or []:
    _pdb.alias_put(plugin_id=PID, server_id=str(_s.get("server_id") or ""),
                   provider="tmdb", provider_id="66875",
                   old_media_id=str(_s.get("item_id") or ""),
                   old_emby_item_id=str(_s.get("emby_item_id") or ""),
                   old_nfo_path=str(_s.get("nfo_path") or ""),
                   old_title=str(_s.get("title") or ""), new_media_id="66875")
_ali = dbm._q("SELECT old_nfo_path FROM media_identity_alias WHERE plugin_id=?", (PID,))
_paths = sorted(str(r["old_nfo_path"]) for r in _ali)
check(len(_ali) == 2, f"同剧两集各留一条旧身份别名（实际 {len(_ali)} 条）")
check(any("S02E01" in p for p in _paths) and any("S03E01" in p for p in _paths),
      f"两条别名分别对应 S02E01 / S03E01：{_paths}")

print("\n" + "=" * 72)
print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败（共 {_N[0]} 项）")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
