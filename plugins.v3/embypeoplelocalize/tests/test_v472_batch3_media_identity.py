# -*- coding: utf-8 -*-
"""v4.6.72 批次 3 回归测试：洗版稳定身份（报告第八~十节 / 十九节测试 8）。

运行：python tests/test_v472_batch3_media_identity.py

真实 db.py（schema v12：person 稳定身份列 + media_identity_alias 表）
+ 从 __init__.py 提取的真实方法体（_remove_missing_event）。
覆盖：
  T1 split_media_id：tmdb/tvdb/imdb/nfo/空 解析
  T2 upsert 落 provider 身份列；集记录 series_media_id = 剧身份
  T3 洗版恢复：路径/标题/Emby ItemId 全变、provider 相同 → 命中并解除观察期
  T4 候选冲突保护：弱匹配（剧名+季集）候选 >1 → 不自动恢复
  T5 Webhook 事件 provider 归一匹配（"1177096" ≡ "tmdb:1177096"）
  T6 历史身份别名：alias_put / alias_resolve
  T7 洗版去重：provider 稳定时旧路径残留行被清理（不留重复）
  T8 恢复只让新增/变化词条进 pending（旧译文继承，原文未变不重翻）
  T9 源码级：_ingest_nfo_pending 用 deleted_weak_candidates 且要求唯一候选
"""
import sys
import os
import re
import types
import tempfile
import importlib.util
from pathlib import Path
from typing import Any, List, Optional, Dict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl72b3_"))
S1 = "___1_192_168_2_15_8096"
S2 = "___2_192_168_2_16_8096"

class _Logger:
    def debug(self, msg, *a, **k):
        if os.environ.get("EPL_DBG"):
            print(f"    [dbg] {msg}")
    def info(self, *a, **k): pass
    def warning(self, msg, *a, **k):
        if os.environ.get("EPL_DBG"):
            print(f"    [warn] {msg}")
    def error(self, *a, **k): pass
    def log(self, *a, **k): pass

logger = _Logger()
_mod_app = types.ModuleType("app")
_mod_sdk = types.ModuleType("app.sdk")
_mod_log = types.ModuleType("app.sdk.logging")
_mod_log.logger = logger
_mod_cfg = types.ModuleType("app.sdk.config")
class _Settings:
    CONFIG_PATH = str(TMP)
_mod_cfg.settings = _Settings()
sys.modules.update({"app": _mod_app, "app.sdk": _mod_sdk,
                    "app.sdk.logging": _mod_log, "app.sdk.config": _mod_cfg})

_spec = importlib.util.spec_from_file_location("epl_db72", PLUGIN_DIR / "db.py")
dbm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dbm)

_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")

def _grab(name: str) -> str:
    m = re.search(rf"^    def {re.escape(name)}\(", _SRC, re.M)
    assert m, f"未找到方法 {name}"
    lines = _SRC[m.start():].splitlines()
    out = [lines[0]]
    for ln in lines[1:]:
        if ln.strip() == "":
            out.append(ln); continue
        if re.match(r"^    \S", ln):
            break
        out.append(ln)
    pre = []
    _head = _SRC[:m.start()].rstrip("\n").splitlines()
    while _head and re.match(r"^    @", _head[-1]):
        pre.insert(0, _head.pop())
    return "\n".join(pre + out)

class _DummyErr(Exception):
    pass

def _mk_cls(cls_name, methods, extra=None):
    ns = {
        "logger": logger, "re": re, "os": os, "Any": Any, "List": List,
        "Optional": Optional, "Dict": Dict, "tuple": tuple, "set": set,
        "int": int, "str": str, "bool": bool, "len": len, "max": max, "min": min,
        "sorted": sorted, "list": list, "dict": dict,
        "split_media_id": dbm.split_media_id,
        "Exception": Exception,
    }
    if extra:
        ns.update(extra)
    src = (f"class {cls_name}:\n" + "\n".join(_grab(n) for n in methods))
    exec(compile(src, "<extract:__init__.py>", "exec"), ns)
    return ns[cls_name]

_N = [0, 0]
def check(cond, msg):
    _N[0] += 1
    if cond:
        print(f"  [PASS] {msg}")
    else:
        _N[1] += 1
        print(f"  [FAIL] {msg}")

pdb = dbm.PeopleDb()
pdb.ensure_table()
PID = "EPL72B3"

print("=" * 72)
print("v4.6.72 批次3 回归测试（洗版稳定身份）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] split_media_id 解析")
# ─────────────────────────────────────────────
check(dbm.split_media_id("1177096") == ("tmdb", "1177096"), "纯数字 → tmdb")
check(dbm.split_media_id("tvdb:123") == ("tvdb", "123"), "tvdb: 前缀")
check(dbm.split_media_id("imdb:tt12345") == ("imdb", "tt12345"), "imdb: 前缀")
check(dbm.split_media_id("nfo:abcdef") == ("nfo", "abcdef"), "nfo: 前缀")
check(dbm.split_media_id("") == ("", ""), "空 → 空")

# ─────────────────────────────────────────────
print("\n[T2] upsert 落稳定身份列；集记录 series_media_id = 剧身份")
# ─────────────────────────────────────────────
pdb.upsert_people(plugin_id=PID, server_id=S1, item_id="tmdb:1177096", item_type="Series",
                  title="大室家", series_name="大室家", season_num=None, episode_num=None,
                  nfo_path="X:/new/tvshow.nfo", emby_item_id="A1",
                  series_media_id="tmdb:1177096",
                  people=[{"before_name": "Sister", "Name": "姐妹", "before_role": "", "Role": ""}])
pdb.upsert_people(plugin_id=PID, server_id=S1, item_id="tmdb:1177096", item_type="Episode",
                  title="大室家", series_name="大室家", season_num=1, episode_num=1,
                  nfo_path="X:/new/S01E01.nfo", emby_item_id="A2",
                  series_media_id="tmdb:1177096",
                  people=[{"before_name": "Sister", "Name": "姐妹", "before_role": "", "Role": ""}])
_r = dbm._q1("SELECT media_provider, media_id, series_media_id FROM person "
             "WHERE plugin_id=? AND item_type='Episode' AND item_id='tmdb:1177096'", (PID,))
check(_r and _r["media_provider"] == "tmdb" and _r["media_id"] == "1177096"
      and _r["series_media_id"] == "tmdb:1177096",
      f"集记录落了 provider/series_media_id：{dict(_r) if _r else None}")

# ─────────────────────────────────────────────
print("\n[T3] 洗版恢复：路径/标题/Emby ItemId 全变，provider 相同 → 命中")
# ─────────────────────────────────────────────
# 旧记录（旧路径 / 旧标题 / 旧 Emby ItemId）→ 标记观察期
pdb.upsert_people(plugin_id=PID, server_id=S1, item_id="tmdb:999888", item_type="Episode",
                  title="旧标题", series_name="旧标题", season_num=2, episode_num=5,
                  nfo_path="X:/old/OLD_RELEASE/S02E05.nfo", emby_item_id="EMBY_OLD",
                  series_media_id="tmdb:999888",
                  people=[{"before_name": "Hero", "Name": "英雄", "before_role": "", "Role": ""}])
pdb.mark_deleted_by_nfo_path(plugin_id=PID, nfo_path="X:/old/OLD_RELEASE/S02E05.nfo", server_id=S1)
# 新记录：同 provider、不同路径/标题/Emby ItemId
_hit = pdb.is_deleted_by_media(plugin_id=PID, item_id="tmdb:999888",
                               media_provider="tmdb", media_id="999888",
                               series_media_id="tmdb:999888", emby_item_id="EMBY_NEW",
                               season_num=2, episode_num=5, server_id=S1)
check(_hit > 0, f"洗版后按 provider 命中观察期行（命中 {_hit}）")
_n = pdb.clear_deleted_by_media(plugin_id=PID, item_id="tmdb:999888", media_provider="tmdb",
                                media_id="999888", series_media_id="tmdb:999888",
                                season_num=2, episode_num=5, server_id=S1)
check(_n > 0 and pdb.is_deleted_by_media(plugin_id=PID, item_id="tmdb:999888",
                                          media_id="999888", server_id=S1) == 0,
      f"解除观察期（清 {_n} 行）→ 恢复成功")
# 只给 provider 归一形式也应命中（新文件无 item_id、旧库有）
pdb.upsert_people(plugin_id=PID, server_id=S1, item_id="tvdb:555", item_type="Movie",
                  title="电影", season_num=None, episode_num=None,
                  nfo_path="X:/old/M/movie.nfo", emby_item_id="MOLD",
                  people=[{"before_name": "A", "Name": "甲"}])
pdb.mark_deleted_by_nfo_path(plugin_id=PID, nfo_path="X:/old/M/movie.nfo", server_id=S1)
check(pdb.is_deleted_by_media(plugin_id=PID, media_provider="tvdb", media_id="555",
                              server_id=S1) > 0, "仅凭 (provider,media_id) 命中电影观察期行")

# ─────────────────────────────────────────────
print("\n[T4] 候选冲突保护：弱匹配候选 >1 → 不自动恢复")
# ─────────────────────────────────────────────
pdb.upsert_people(plugin_id=PID, server_id=S1, item_id="nfo:aaa", item_type="Episode",
                  title="冲突剧", series_name="冲突剧", season_num=3, episode_num=1,
                  nfo_path="X:/c1/S03E01.nfo",
                  people=[{"before_name": "A", "Name": "甲"}])
pdb.mark_deleted_by_nfo_path(plugin_id=PID, nfo_path="X:/c1/S03E01.nfo", server_id=S1)
pdb.upsert_people(plugin_id=PID, server_id=S1, item_id="nfo:bbb", item_type="Episode",
                  title="冲突剧", series_name="冲突剧", season_num=3, episode_num=1,
                  nfo_path="X:/c2/S03E01.nfo",
                  people=[{"before_name": "A", "Name": "甲"}])
pdb.mark_deleted_by_nfo_path(plugin_id=PID, nfo_path="X:/c2/S03E01.nfo", server_id=S1)
_wc = pdb.deleted_weak_candidates(plugin_id=PID, series_name="冲突剧",
                                  season_num=3, episode_num=1, server_id=S1)
check(_wc == 2, f"同名+同季集有 2 个候选 → 不自动恢复（candidates={_wc}）")
# 唯一候选场景
pdb.upsert_people(plugin_id=PID, server_id=S1, item_id="nfo:ccc", item_type="Episode",
                  title="唯一剧", series_name="唯一剧", season_num=1, episode_num=2,
                  nfo_path="X:/u/S01E02.nfo",
                  people=[{"before_name": "B", "Name": "乙"}])
pdb.mark_deleted_by_nfo_path(plugin_id=PID, nfo_path="X:/u/S01E02.nfo", server_id=S1)
_wc2 = pdb.deleted_weak_candidates(plugin_id=PID, series_name="唯一剧",
                                   season_num=1, episode_num=2, server_id=S1)
check(_wc2 == 1, f"唯一候选 → 允许自动恢复（candidates={_wc2}）")

# ─────────────────────────────────────────────
print("\n[T5] Webhook 事件 provider 归一匹配")
# ─────────────────────────────────────────────
EP = _mk_cls("EPL72B3EP", ["_remove_missing_event"])
ep = EP()
ep._webhook_events = [
    {"status": "missing", "item_id": "31840", "media_item_id": "1177096",
     "series_name": "大室家", "name": "大室家", "season": None, "episode": None,
     "server_id": S1},
]
ep._people_db = None
ep._save_state = lambda: None
# 恢复事件：Emby ItemId 变了，但 provider 相同（tmdb:1177096 ≡ 1177096）
_n = ep._remove_missing_event(series_name="大室家", season=None, episode=None,
                              title="大室家", server_id=S1,
                              item_id="31997", media_item_id="tmdb:1177096")
check(_n == 1 and not ep._webhook_events,
      f"洗版后 Emby ItemId 变化 → 按 provider 归一命中并清除事件（清 {_n} 行）")

# ─────────────────────────────────────────────
print("\n[T6] 历史身份别名")
# ─────────────────────────────────────────────
pdb.alias_put(plugin_id=PID, server_id=S1, provider="tmdb", provider_id="1177096",
              old_media_id="nfo:OLDHASH", old_emby_item_id="31840",
              old_nfo_path="X:/old/大室家/S01E01.nfo", old_title="大室家",
              new_media_id="tmdb:1177096")
_ids = pdb.alias_resolve(plugin_id=PID, server_id=S1, provider="tmdb",
                         provider_id="1177096", item_id="tmdb:1177096")
check("nfo:OLDHASH" in _ids and "tmdb:1177096" in _ids,
      f"别名把洗版前后身份归一：{_ids}")
_rows = pdb.alias_rows(plugin_id=PID, server_id=S1, provider="tmdb", provider_id="1177096")
check(len(_rows) == 1 and _rows[0]["old_emby_item_id"] == "31840",
      "别名明细可查（含旧 Emby ItemId / 旧路径）")

# ─────────────────────────────────────────────
print("\n[T7] 洗版去重：provider 稳定时旧路径残留行被清理")
# ─────────────────────────────────────────────
pdb.upsert_people(plugin_id=PID, server_id=S1, item_id="tmdb:777", item_type="Episode",
                  title="洗版剧", series_name="洗版剧", season_num=1, episode_num=1,
                  nfo_path="X:/oldsite/S01E01.nfo", emby_item_id="E1",
                  series_media_id="tmdb:777",
                  people=[{"before_name": "X", "Name": "旧译"}])
# 洗版：同 provider、新路径重新入库
pdb.upsert_people(plugin_id=PID, server_id=S1, item_id="tmdb:777", item_type="Episode",
                  title="洗版剧", series_name="洗版剧", season_num=1, episode_num=1,
                  nfo_path="X:/newsite/S01E01.nfo", emby_item_id="E2",
                  series_media_id="tmdb:777",
                  people=[{"before_name": "X", "Name": "旧译"}])
_rows = dbm._q("SELECT nfo_path FROM person WHERE plugin_id=? AND item_id='tmdb:777'", (PID,))
check(len(_rows) == 1 and _rows[0]["nfo_path"] == "X:/newsite/S01E01.nfo",
      f"旧路径残留行被清理，只剩新路径 1 行：{[r['nfo_path'] for r in _rows]}")

# ─────────────────────────────────────────────
print("\n[T8] 恢复只让新增/变化词条进 pending（原文未变继承旧译文）")
# ─────────────────────────────────────────────
pdb.upsert_people(plugin_id=PID, server_id=S1, item_id="tmdb:555", item_type="Movie",
                  title="继承片", season_num=None, episode_num=None,
                  nfo_path="X:/old/i.nfo", emby_item_id="I1",
                  people=[{"before_name": "Keep", "Name": "保留", "before_role": "", "Role": ""},
                          {"before_name": "Chg", "Name": "旧译", "before_role": "", "Role": ""}])
pdb.mark_deleted_by_nfo_path(plugin_id=PID, nfo_path="X:/old/i.nfo", server_id=S1)
pdb.clear_deleted_by_media(plugin_id=PID, item_id="tmdb:555", server_id=S1)
# 重新入库：Keep 原样、Chg 原文未变、New 新增
pdb.upsert_people(plugin_id=PID, server_id=S1, item_id="tmdb:555", item_type="Movie",
                  title="继承片", season_num=None, episode_num=None,
                  nfo_path="X:/old/i.nfo", emby_item_id="I1",
                  people=[{"before_name": "Keep", "Name": "Keep", "before_role": "", "Role": ""},
                          {"before_name": "Chg", "Name": "Chg", "before_role": "", "Role": ""},
                          {"before_name": "New", "Name": "New", "before_role": "", "Role": ""}])
_rows = dbm._q("SELECT name_before, name_after FROM person WHERE plugin_id=? "
               "AND item_id='tmdb:555' ORDER BY name_before", (PID,))
_d = {r["name_before"]: r["name_after"] for r in _rows}
check(_d.get("Keep") == "保留", f"原文未变 + 旧译文存在 → 继承（Keep={_d.get('Keep')}）")
check(_d.get("Chg") == "旧译", f"原文未变 → 继承旧译文（Chg={_d.get('Chg')}）")
check(_d.get("New") == "New", f"新增词条 → 以原文占位（New={_d.get('New')}）")

# ─────────────────────────────────────────────
print("\n[T9] 源码级：_ingest_nfo_pending 用 deleted_weak_candidates 且要求唯一候选")
# ─────────────────────────────────────────────
_body = _grab("_ingest_nfo_pending")
check("is_deleted_by_media" in _body, "恢复判定用强身份 is_deleted_by_media")
check("deleted_weak_candidates" in _body and "_wc == 1" in _body,
      "弱匹配要求候选唯一（_wc == 1）才自动恢复")
check("sample_deleted_identities" in _body and "alias_put" in _body,
      "恢复时登记洗版历史别名")

# ─────────────────────────────────────────────
print("\n[T10] schema 迁移：旧库 v11 → v12 无损补列（必须放最后，会切换连接）")
# ─────────────────────────────────────────────
import sqlite3
_mdir = Path(tempfile.mkdtemp(prefix="epl72mig_"))
_mpath = _mdir / "data.db"
_c = sqlite3.connect(str(_mpath))
_c.executescript(
    "CREATE TABLE person (id INTEGER PRIMARY KEY AUTOINCREMENT, plugin_id TEXT DEFAULT '', "
    "server_id TEXT DEFAULT '', item_id TEXT DEFAULT '', item_type TEXT DEFAULT '', title TEXT DEFAULT '', "
    "series_name TEXT DEFAULT '', season_num INTEGER, episode_num INTEGER, library_name TEXT DEFAULT '', "
    "person_index INTEGER DEFAULT 0, person_type TEXT DEFAULT 'Actor', name_before TEXT DEFAULT '', "
    "name_after TEXT DEFAULT '', role_before TEXT DEFAULT '', role_after TEXT DEFAULT '', "
    "translated_at TEXT DEFAULT '', nfo_path TEXT DEFAULT '', deleted_at TEXT DEFAULT '', "
    "emby_item_id TEXT DEFAULT '');"
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT DEFAULT '');"
    "INSERT INTO meta (key, value) VALUES ('schema_version','11');"
    "INSERT INTO person (plugin_id, item_id, name_before, name_after) VALUES ('OLD','123','Old','旧');"
)
_c.commit()
_c.close()

_orig_datadir = dbm._data_dir
dbm._data_dir = lambda: _mdir
dbm._drop_conn()
try:
    dbm.PeopleDb.ensure_table()
    _ver = dbm.get_meta("schema_version", "0")
    check(str(_ver) == str(dbm.SCHEMA_VERSION),
          f"迁移后 schema_version={dbm.SCHEMA_VERSION}（实际 {_ver}）")
    _cols = [r["name"] for r in dbm._q("PRAGMA table_info(person)")]
    check(all(c in _cols for c in ["media_provider", "media_id", "series_media_id", "file_fingerprint"]),
          "person 已补 4 个稳定身份列")
    _idx = [r["name"] for r in dbm._q("PRAGMA index_list(person)")]
    check("idx_person_media" in _idx and "idx_person_series_media" in _idx, "稳定媒体身份索引已建")
    _tbl = [r["name"] for r in dbm._q("SELECT name FROM sqlite_master WHERE type='table'")]
    check("media_identity_alias" in _tbl, "历史身份别名表已建")
    _old = dbm._q1("SELECT name_after FROM person WHERE plugin_id='OLD'")
    check(_old and _old["name_after"] == "旧", "旧数据无损保留（迁移不删数据）")
finally:
    dbm._drop_conn()
    dbm._data_dir = _orig_datadir

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
