# -*- coding: utf-8 -*-
"""P1 回归测试：库列表分页内存修复（library_items_page）。

背景：旧实现 `_api_db_items` 每次都把整张 person 表 SELECT * 拉进 Python 再分组，
分页只在内存里切片 —— 大库下单次请求内存随库规模线性增长。
修复：`PeopleDb.library_items_page` 在 SQL 层 GROUP BY (server_id, item_id) 聚合出
「当前页」的分组键（按 updated_at=MAX(translated_at) 倒序，集类型组剔除），
再只取该页条目对应的行做分组；字段/排序与整表 `library_items` 完全一致。

本测试用「分页结果 == 整表结果按同一规则切片」的强等价断言守住语义：
  * 逐页拼接 == 整表过滤后的完整序列（顺序、字段值全等）
  * total 与 has_more 正确
  * scan_mode 来源作用域生效
  * 仅 Episode 行构成的组被剔除；含非 Episode 行的混合组保留且类型取剧/电影

运行：python tests/test_p1_library_page.py
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import test_p0_nfo_checkpoint as base   # noqa: E402  （安装宿主桩件）

check = base.check

_DB_ROOT = os.path.join(base._TMP, "libpage")
os.makedirs(_DB_ROOT, exist_ok=True)
import app.sdk.config as _hcfg  # noqa: E402
_hcfg.settings.CONFIG_PATH = _DB_ROOT

import embypeoplelocalize.db as dbmod  # noqa: E402
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

    def _one(iid, srv, itype, title, ts, nfo_path, name, season=None, episode=None):
        db.upsert_people(plugin_id=PID, server_id=srv, item_id=iid, item_type=itype,
                         title=title, season_num=season, episode_num=episode,
                         people=_p(name), nfo_path=nfo_path)
        dbmod._x("UPDATE person SET translated_at=? WHERE plugin_id=? AND item_id=?",
                 (ts, PID, iid))

    _one("1001", LOCAL, "Movie", "Local A", "2024-01-01", "D:/lib/A/movie.nfo", "Tom")
    _one("1002", SRV_A, "Movie", "Server B", "2024-01-05", "", "Bob")
    _one("1003", LOCAL, "Series", "Local C", "2024-01-03", "D:/lib/C/S01E01.nfo", "Cat")
    _one("1004", SRV_A, "Movie", "Server D", "2024-01-02", "", "Dan")
    _one("1005", LOCAL, "Movie", "Local E", "2024-01-06", "D:/lib/E/movie.nfo", "Eve")
    _one("1006", SRV_B, "Movie", "Server F", "2024-01-04", "", "Fay")
    # 混合组：先落一条 Episode（id 较小），再落一条 Movie —— 组类型应取 Movie 并保留
    _one("MIX", LOCAL, "Episode", "Mixed", "2024-01-07", "D:/lib/MIX/S01E01.nfo", "Gil",
         season=1, episode=1)
    _one("MIX", LOCAL, "Movie", "Mixed", "2024-01-07", "D:/lib/MIX/movie.nfo", "Gil")
    # 纯 Episode 组：应被剔除
    _one("EP", LOCAL, "Episode", "EpOnly", "2024-01-08", "D:/lib/EP/S01E01.nfo", "Hal",
         season=1, episode=1)
    _one("EP", LOCAL, "Episode", "EpOnly", "2024-01-08", "D:/lib/EP/S01E02.nfo", "Hal",
         season=1, episode=2)
    return db


def _sig(items):
    return json.dumps([{k: it.get(k) for k in sorted(it)} for it in items],
                      sort_keys=True, ensure_ascii=False)


def _expected(db, scan_mode=None):
    """整表结果按 _api_db_items 的规则过滤（剔除 Episode 组）后的参照序列。"""
    rows = db.library_items(plugin_id=PID, scan_mode=scan_mode) or []
    return [it for it in rows if str(it.get("item_type") or "") != "Episode"]


def test_equivalence_full(db):
    print("A) 逐页拼接 == 整表过滤后的完整序列（全来源）")
    exp = _expected(db)
    check("参照序列 7 条（EP 纯集组被剔除）", len(exp) == 7, f"n={len(exp)}")
    check("排序按 updated_at 倒序且混合组类型为 Movie",
          [it.get("item_id") for it in exp] == ["MIX", "1005", "1002", "1006", "1003", "1004", "1001"],
          str([it.get("item_id") for it in exp]))
    check("混合组取非 Episode 类型",
          next(it for it in exp if it.get("item_id") == "MIX").get("item_type") == "Movie")

    got = []
    total = None
    off = 0
    limit = 3
    while True:
        page, total = db.library_items_page(plugin_id=PID, limit=limit, offset=off)
        got.extend(page)
        if not page or off + limit >= total:
            break
        off += limit
    check("分页 total == 参照总数", total == len(exp), f"total={total} exp={len(exp)}")
    check("逐页拼接顺序与字段与参照完全一致", _sig(got) == _sig(exp),
          f"got={[i.get('item_id') for i in got]}")


def test_page_fields(db):
    print("B) 单页字段与整表切片逐字一致（person_count/nfo_dir/title）")
    exp = _expected(db)
    page, total = db.library_items_page(plugin_id=PID, limit=2, offset=2)
    check("offset=2 limit=2 切到参照第 3、4 条",
          _sig(page) == _sig(exp[2:4]), f"got={[i.get('item_id') for i in page]}")
    check("total 仍为全量", total == len(exp), f"total={total}")
    _mix = next(it for it in page if it.get("item_id") == "MIX") if any(
        it.get("item_id") == "MIX" for it in page) else None
    check("混合组 person_count=2", _mix is None or _mix.get("person_count") == 2,
          str(_mix.get("person_count")) if _mix else "not-on-page")


def test_tail_and_oob(db):
    print("C) 尾页 / 越界页")
    exp = _expected(db)
    page, total = db.library_items_page(plugin_id=PID, limit=10, offset=5)
    check("末页返回剩余 2 条", _sig(page) == _sig(exp[5:]), str(len(page)))
    page2, total2 = db.library_items_page(plugin_id=PID, limit=10, offset=99)
    check("越界 offset → 空页但 total 不变", page2 == [] and total2 == len(exp), str(len(page2)))


def test_scan_mode_scope(db):
    print("D) scan_mode 来源作用域")
    exp_nfo = _expected(db, scan_mode="nfo")
    exp_api = _expected(db, scan_mode="api")
    check("nfo 模式 4 条（本地 + 混合组）", len(exp_nfo) == 4, str(len(exp_nfo)))
    check("api 模式 3 条（仅在线来源）", len(exp_api) == 3, str(len(exp_api)))
    p_nfo, t_nfo = db.library_items_page(plugin_id=PID, scan_mode="nfo", limit=10, offset=0)
    p_api, t_api = db.library_items_page(plugin_id=PID, scan_mode="api", limit=10, offset=0)
    check("nfo 分页 == nfo 参照", _sig(p_nfo) == _sig(exp_nfo) and t_nfo == len(exp_nfo),
          str([i.get("item_id") for i in p_nfo]))
    check("api 分页 == api 参照", _sig(p_api) == _sig(exp_api) and t_api == len(exp_api),
          str([i.get("item_id") for i in p_api]))


def test_limit_fallback(db):
    print("E) limit<=0 退化路径仍与整表一致")
    exp = _expected(db)
    page, total = db.library_items_page(plugin_id=PID, limit=0, offset=0)
    check("limit=0 返回全量且 total 一致", _sig(page) == _sig(exp) and total == len(exp),
          str(len(page)))


_COLS = ("plugin_id, server_id, item_id, item_type, title, series_name, season_num, "
         "episode_num, person_index, person_type, name_before, name_after, role_before, "
         "role_after, translated_at, nfo_path")


def test_null_server_group(db):
    print("F) server_id NULL / 空串 归一化：同一逻辑条目不得重复、total 不虚高")
    # 同一 item_id「NULLG」既有一行 server_id=NULL、又有一行 server_id=''。
    # SQL 若按裸 server_id 分组会把它们拆成两组，归一化后却是同一 key →
    # 页内重复 + total 虚高。修复后应合并为一组。
    dbmod._x("INSERT INTO person (" + _COLS + ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
             (PID, None, "NULLG", "Movie", "Null Group", "", None, None, 0, "Actor",
              "Zed", "Zed-中", "Zed", "Zed-中", "2024-01-09", "D:/lib/NULLG/movie.nfo"))
    dbmod._x("INSERT INTO person (" + _COLS + ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
             (PID, "", "NULLG", "Movie", "Null Group", "", None, None, 1, "Actor",
              "Zed", "Zed-中", "Zed", "Zed-中", "2024-01-09", "D:/lib/NULLG/movie.nfo"))
    exp = _expected(db)
    n_null = sum(1 for it in exp if it.get("item_id") == "NULLG")
    check("整表把 NULL/空串 归为同一组（1 条）", n_null == 1, f"n={n_null}")
    check("整表该组 person_count=2",
          next((it.get("person_count") for it in exp if it.get("item_id") == "NULLG"), None) == 2,
          str(next((it.get("person_count") for it in exp if it.get("item_id") == "NULLG"), None)))
    page, total = db.library_items_page(plugin_id=PID, limit=100, offset=0)
    ids = [it.get("item_id") for it in page]
    check("分页无重复条目（NULLG 仅出现一次）", ids.count("NULLG") == 1, f"n={ids.count('NULLG')}")
    check("total == 参照总数（未虚高）", total == len(exp), f"total={total} exp={len(exp)}")
    check("分页拼接与参照整体一致", _sig(page) == _sig(exp), f"n={len(page)}")


def test_large_library(db):
    print("G) 大库：数千行下分页遍历与整表一致 + 聚合索引就绪")
    n = 2000
    conn = dbmod._get_conn()
    rows = []
    for i in range(n):
        iid = f"BIG{i:05d}"
        rows.append((PID, LOCAL, iid, "Series", f"Big {i}", "Big Series", None, None, 0,
                     "Actor", "A", "A-中", "A", "A-中", "2024-02-01", f"D:/big/{iid}/tvshow.nfo"))
        rows.append((PID, LOCAL, iid, "Episode", f"Big {i}", "Big Series", 1, 1, 0,
                     "Actor", "B", "B-中", "B", "B-中", "2024-02-01", f"D:/big/{iid}/S01E01.nfo"))
    conn.executemany("INSERT INTO person (" + _COLS + ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    names = {str(r.get("name")) for r in dbmod._q("PRAGMA index_list(person)")}
    check("idx_person_page 表达式索引已建立", "idx_person_page" in names, str(sorted(names)))

    exp = _expected(db)
    got = []
    off = 0
    limit = 100
    total = None
    while True:
        page, total = db.library_items_page(plugin_id=PID, limit=limit, offset=off)
        got.extend(page)
        if not page or off + limit >= total:
            break
        off += limit
    check("大库 total == 参照总数", total == len(exp), f"total={total} exp={len(exp)}")
    check("大库逐页拼接 == 参照整表（顺序与字段全等）", _sig(got) == _sig(exp),
          f"got={len(got)} exp={len(exp)}")


if __name__ == "__main__":
    print(f"db 目录: {_DB_ROOT}")
    _db = _seed()
    test_equivalence_full(_db)
    test_page_fields(_db)
    test_tail_and_oob(_db)
    test_scan_mode_scope(_db)
    test_limit_fallback(_db)
    test_null_server_group(_db)
    test_large_library(_db)
    print(f"\n结果: {base._PASS} 通过 / {base._FAIL} 失败")
    sys.exit(1 if base._FAIL else 0)
