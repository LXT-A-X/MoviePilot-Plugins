# -*- coding: utf-8 -*-
"""P0 回归测试：媒体身份 source scope（DB-001）。

运行：python tests/test_p0_db_scope.py

覆盖：同一 item_id 在「本地 NFO（server_id 空）+ 多个 Emby 服务器」并存时，
读取 / 标记观察期 / 删除 / 集数统计 / 库列表分组必须只作用于目标来源；
显式传 None 时保留旧「不限来源」语义。
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import test_p0_nfo_checkpoint as base   # noqa: E402  （安装宿主桩件）

check = base.check

_DB_ROOT = os.path.join(base._TMP, "dbscope")
os.makedirs(_DB_ROOT, exist_ok=True)
import app.sdk.config as _hcfg  # noqa: E402
_hcfg.settings.CONFIG_PATH = _DB_ROOT

from embypeoplelocalize.db import PeopleDb  # noqa: E402

PID = "EmbyPeopleLocalize"
LOCAL = ""
SRV_A = "SRV-A"
SRV_B = "SRV-B"


def _p(name):
    return [{"Type": "Actor", "before_name": name, "Name": f"{name}-中"}]


def _seed():
    db = PeopleDb()
    db.ensure_table()
    # 同 item_id 三个来源（读取作用域用）
    db.upsert_people(plugin_id=PID, server_id=LOCAL, item_id="1001", item_type="Movie",
                     title="Local A", people=_p("Tom"),
                     nfo_path="D:/lib/Movie A/movie.nfo")
    db.upsert_people(plugin_id=PID, server_id=SRV_A, item_id="1001", item_type="Movie",
                     title="Server A", people=_p("Bob"))
    db.upsert_people(plugin_id=PID, server_id=SRV_B, item_id="1001", item_type="Movie",
                     title="Server B", people=_p("Cat"))
    # 观察期标记用
    db.upsert_people(plugin_id=PID, server_id=LOCAL, item_id="3003", item_type="Movie",
                     title="Local D", people=_p("Dan"), nfo_path="D:/lib/D/movie.nfo")
    db.upsert_people(plugin_id=PID, server_id=SRV_A, item_id="3003", item_type="Movie",
                     title="Server D", people=_p("Eve"))
    # 删除用
    db.upsert_people(plugin_id=PID, server_id=LOCAL, item_id="4004", item_type="Movie",
                     title="Local F", people=_p("Fay"), nfo_path="D:/lib/F/movie.nfo")
    db.upsert_people(plugin_id=PID, server_id=SRV_A, item_id="4004", item_type="Movie",
                     title="Server F", people=_p("Gil"))
    # 集数统计用（同剧两个来源各有不同集）
    db.upsert_people(plugin_id=PID, server_id=LOCAL, item_id="5005", item_type="Series",
                     title="Show L", season_num=1, episode_num=1, people=_p("Hal"),
                     nfo_path="D:/lib/Show/S01E01.nfo")
    db.upsert_people(plugin_id=PID, server_id=SRV_A, item_id="5005", item_type="Series",
                     title="Show A", season_num=1, episode_num=2, people=_p("Ida"))
    return db


def _names(rows):
    return sorted(str(r.get("name_before") or "") for r in rows)


def _deleted_names(rows):
    return sorted(str(r.get("name_before") or "") for r in rows if str(r.get("deleted_at") or ""))


def test_read_scope(db):
    print("A) 读取：people_of_item / item_meta 按来源隔离")
    check("server_id=SRV-A → 只返回 A 来源",
          _names(db.people_of_item(plugin_id=PID, item_id="1001", server_id=SRV_A)) == ["Bob"],
          str(_names(db.people_of_item(plugin_id=PID, item_id="1001", server_id=SRV_A))))
    check("server_id='' → 只返回本地来源（不再跨来源）",
          _names(db.people_of_item(plugin_id=PID, item_id="1001", server_id=LOCAL)) == ["Tom"])
    check("server_id=None → 保留旧「不限来源」语义",
          _names(db.people_of_item(plugin_id=PID, item_id="1001", server_id=None)) == ["Bob", "Cat", "Tom"])
    check("item_meta 本地来源标题正确",
          (db.item_meta(plugin_id=PID, item_id="1001", server_id=LOCAL) or {}).get("title") == "Local A")
    check("item_meta 指定服务器标题正确",
          (db.item_meta(plugin_id=PID, item_id="1001", server_id=SRV_B) or {}).get("title") == "Server B")
    check("item_meta 不存在的来源 → None",
          db.item_meta(plugin_id=PID, item_id="1001", server_id="SRV-X") is None)


def test_library_items_group(db):
    print("B) 库列表：同 item_id 不同来源不再并成一格")
    items = db.library_items(plugin_id=PID) or []
    g = [it for it in items if str(it.get("item_id")) == "1001"]
    check("三个来源各自成组", len(g) == 3, f"groups={len(g)}")
    check("分组带来源标识", sorted(str(it.get("server_id") or "") for it in g) == ["", SRV_A, SRV_B],
          str(sorted(str(it.get("server_id") or "") for it in g)))
    g_nfo = db.library_items(plugin_id=PID, scan_mode="nfo") or []
    check("scan_mode=nfo 只留本地来源", len([it for it in g_nfo if str(it.get("item_id")) == "1001"]) == 1)
    g_api = db.library_items(plugin_id=PID, scan_mode="api") or []
    check("scan_mode=api 只留在线来源", len([it for it in g_api if str(it.get("item_id")) == "1001"]) == 2)


def test_mark_deleted_scope(db):
    print("C) 观察期标记：只标记目标来源")
    n = db.mark_deleted(plugin_id=PID, item_ids=["3003"], server_id=LOCAL)
    rows = db.people_of_item(plugin_id=PID, item_id="3003", server_id=None)
    check("本地来源被标记（1 行）", n == 1 and _deleted_names(rows) == ["Dan"], f"n={n} {_deleted_names(rows)}")
    check("其它来源未被误标", "Eve" not in _deleted_names(rows))
    n2 = db.mark_deleted(plugin_id=PID, item_ids=["3003"], server_id=None)
    check("None 语义：其余来源一并标记（旧行为）", n2 == 1, f"n2={n2}")


def test_mark_deleted_by_episode_scope(db):
    print("D) 集级观察期标记：只标记目标来源")
    db.upsert_people(plugin_id=PID, server_id=LOCAL, item_id="6006", item_type="Series",
                     title="Show M", season_num=1, episode_num=3, people=_p("Joy"),
                     nfo_path="D:/lib/M/S01E03.nfo")
    db.upsert_people(plugin_id=PID, server_id=SRV_A, item_id="6006", item_type="Series",
                     title="Show M", season_num=1, episode_num=3, people=_p("Kim"))
    n = db.mark_deleted_by_episode(plugin_id=PID, item_id="6006", season_num=1, episode_num=3,
                                   server_id=LOCAL)
    rows = db.people_of_item(plugin_id=PID, item_id="6006", server_id=None)
    check("只标记本地集的记录", n == 1 and _deleted_names(rows) == ["Joy"], f"n={n} {_deleted_names(rows)}")


def test_delete_scope(db):
    print("E) 删除：只删目标来源")
    n = db.delete_item(plugin_id=PID, item_id="4004", server_id=SRV_A)
    left = db.people_of_item(plugin_id=PID, item_id="4004", server_id=None)
    check("只删掉 SRV-A 的记录", n == 1 and _names(left) == ["Fay"], f"n={n} {_names(left)}")


def test_episode_counts_scope(db):
    print("F) 集数统计：按来源统计")
    check("本地来源只算本地集",
          db.episode_counts(plugin_id=PID, item_ids=["5005"], server_id=LOCAL).get("5005") == 1)
    check("指定服务器只算该服集",
          db.episode_counts(plugin_id=PID, item_ids=["5005"], server_id=SRV_A).get("5005") == 1)
    check("None 语义：跨来源合计",
          db.episode_counts(plugin_id=PID, item_ids=["5005"], server_id=None).get("5005") == 2)


def _pend(name, *, name_after="", ptype="Actor", before_role="", role_after=""):
    return [{"Type": ptype, "before_name": name, "Name": name_after,
             "before_role": before_role, "Role": role_after}]


def test_pending_items_count(db):
    print("G) 待翻译条目统计：pending_items_count（库页顶部常驻统计口径）")
    # 7001 本地：仅第一排人名未翻（Actor）
    db.upsert_people(plugin_id=PID, server_id=LOCAL, item_id="7001", item_type="Movie",
                     title="Pend A", people=_pend("Zed"), nfo_path="D:/lib/PendA/movie.nfo")
    # 7002 在线：仅第二排角色未翻（人名已译）
    db.upsert_people(plugin_id=PID, server_id=SRV_A, item_id="7002", item_type="Movie",
                     title="Pend B", people=_pend("Yan", name_after="Yan-中",
                                                  before_role="侦探", role_after=""))
    # 7003 在线：已全翻，不计入
    db.upsert_people(plugin_id=PID, server_id=SRV_A, item_id="7003", item_type="Movie",
                     title="Done C", people=_p("Xena"))
    check("不限来源：7001 + 7002 两条条目 pending",
          db.pending_items_count(plugin_id=PID) == 2, f"got={db.pending_items_count(plugin_id=PID)}")
    check("scan_mode=nfo 只剩本地 7001",
          db.pending_items_count(plugin_id=PID, scan_mode="nfo") == 1)
    check("scan_mode=api 只剩在线 7002",
          db.pending_items_count(plugin_id=PID, scan_mode="api") == 1)
    check("关第一排 person_on=False → 只剩角色 pending 7002",
          db.pending_items_count(plugin_id=PID, person_on=False) == 1)
    check("关第二排 role_on=False → 只剩人名 pending 7001",
          db.pending_items_count(plugin_id=PID, role_on=False) == 1)
    check("类型过滤：禁用 Actor 后本地 7001 不计入（台词角色不受影响）",
          db.pending_items_count(plugin_id=PID, scan_mode="nfo", disabled_types=["Actor"]) == 0)
    check("全部关闭 person/role → 0",
          db.pending_items_count(plugin_id=PID, person_on=False, role_on=False) == 0)


if __name__ == "__main__":
    print(f"db 目录: {_DB_ROOT}")
    _db = _seed()
    test_read_scope(_db)
    test_library_items_group(_db)
    test_mark_deleted_scope(_db)
    test_mark_deleted_by_episode_scope(_db)
    test_delete_scope(_db)
    test_episode_counts_scope(_db)
    test_pending_items_count(_db)
    print(f"\n结果: {base._PASS} 通过 / {base._FAIL} 失败")
    sys.exit(1 if base._FAIL else 0)