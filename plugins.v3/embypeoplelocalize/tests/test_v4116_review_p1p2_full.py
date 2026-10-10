# -*- coding: utf-8 -*-
"""v4.6.116 回归测试：第三方审查报告（v4.6.115）P1-01 ~ P1-08 + P2-10/11。

运行：python tests/test_v4116_review_p1p2_full.py

覆盖（对齐报告第十四节验收清单）：
  A 剧集列表完整性（P1-02）：分页总数固定 / 跨页变化 → 不可信；页数上限用尽 → 不可信
  B 人名池生命周期（P1-04）：list_all_persons_status 三态；_pool_collect_persons 显式完成态；
                         仅完整拉取才允许 sweep
  C 多服务器与探测（P1-05）：probe_keys 按 server_id 分组；reverse mark 逐服务器 +
                         清单不完整的服务器跳过
  D 路径级映射（P1-06）：Webhook 归一化按原始 Emby 路径唯一反推 (lib_id, idx)；歧义不任取
  E 任务隔离（P1-08）：运行中到达的新请求独立入队（不改当前 Job 的 source/scope/items/快照）
  F 强制任务复合键（P2-10）：_tx_force_jobs 按 (job_id, item_id) 保存
  G Person 元数据安全（P2-11）：改名后复读校验，元数据变化 → 按失败处理
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
TMP = Path(tempfile.mkdtemp(prefix="epl116_"))
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
_DB = (PLUGIN_DIR / "db.py").read_text(encoding="utf-8")
_CLI = (PLUGIN_DIR / "emby_client.py").read_text(encoding="utf-8")

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
_req = types.ModuleType("requests")


class _RS:
    def __init__(self): self.headers = {}

    def close(self): pass


_req.Session = _RS
_sch = types.ModuleType("app.schemas"); _sch.ServiceInfo = object
sys.modules.update({"app": _m, "app.sdk": _s, "app.sdk.logging": _l, "app.sdk.config": _c,
                    "requests": _req, "app.schemas": _sch})

_spec = importlib.util.spec_from_file_location("epl_db116", PLUGIN_DIR / "db.py")
dbm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dbm)
_cs = importlib.util.spec_from_file_location("epl_cli116", PLUGIN_DIR / "emby_client.py")
clim = importlib.util.module_from_spec(_cs)
_cs.loader.exec_module(clim)


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
print("v4.6.116 回归测试（审查报告 P1-01~08 + P2-10/11 全量）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[A] 剧集列表完整性（P1-02：总数固定 + 跨页一致 + 页数上限）")
# ─────────────────────────────────────────────


class _Resp:
    def __init__(self, code, payload=None):
        self.status_code, self._p = code, payload

    def json(self):
        return self._p


class _Sess:
    def __init__(self, seq):
        self.seq = list(seq)
        self.n = 0

    def get(self, *a, **k):
        _r = self.seq[min(self.n, len(self.seq) - 1)]
        self.n += 1
        if isinstance(_r, Exception):
            raise _r
        return _r

    def close(self):
        pass


def _mk(seq, user="u1"):
    c = clim.EmbyClient("http://emby.test:8096", "k")
    c.session = _Sess(seq)
    c._get_user_id = lambda: user
    return c


def _eps(_from, _to):
    return [{"Id": str(i), "ParentIndexNumber": 1, "IndexNumber": i} for i in range(_from, _to + 1)]


# A-4：第一页 total=1000，第二页 total=500 → 不得视为完整
_st, _out, _why = _mk([_Resp(200, {"Items": _eps(1, 2), "TotalRecordCount": 1000}),
                       _Resp(200, {"Items": _eps(3, 4), "TotalRecordCount": 500})]
                      ).get_series_episodes_status("9", limit=2)
check(_st == clim.ITEM_UNAVAILABLE and _why.startswith("pagination_total_changed_"),
      f"剧集分页：总数中途变化 → UNAVAILABLE（不计算缺集），实际 {_st}/{_why}")

# A-1：HTTP 200 + {} → UNAVAILABLE
check(_mk([_Resp(200, {})]).get_series_episodes_status("9")[0] == clim.ITEM_UNAVAILABLE,
      "剧集分页：200 + {}（结构非法）→ UNAVAILABLE")

# A-4（query_items_paged_status）：跨页总数变化 → complete=False
_st, _d, _why = _mk([_Resp(200, {"Items": _eps(1, 2), "TotalRecordCount": 10}),
                     _Resp(200, {"Items": _eps(3, 4), "TotalRecordCount": 6})]
                    ).query_items_paged_status({"ParentId": "L"}, page_size=2, max_pages=5)
check(_st == clim.ITEM_UNAVAILABLE and (_d or {}).get("complete") is False
      and _why.startswith("pagination_total_changed_"),
      f"分页查询：总数变化 → 不完整（complete=False），实际 {_st}/{_why}")

# A-6：max_pages 用尽仍未读完 → 不可信
_st, _d, _why = _mk([_Resp(200, {"Items": _eps(1, 2), "TotalRecordCount": 10})]
                    ).query_items_paged_status({"ParentId": "L"}, page_size=2, max_pages=2)
check(_st == clim.ITEM_UNAVAILABLE and (_d or {}).get("complete") is False
      and _why.startswith("max_pages_"),
      f"分页查询：页数上限用尽未读完 → 不完整，实际 {_st}/{_why}")

# 正常：总数一致且读完 → FOUND
_st, _d, _why = _mk([_Resp(200, {"Items": _eps(1, 2), "TotalRecordCount": 2})]
                    ).query_items_paged_status({"ParentId": "L"}, page_size=2, max_pages=5)
check(_st == clim.ITEM_FOUND and (_d or {}).get("complete") is True and _why == "",
      "分页查询：总数一致且读完 → FOUND + complete=True")

# 分页中途超时 → 不完整
_st, _d, _why = _mk([_Resp(200, {"Items": _eps(1, 2), "TotalRecordCount": 10}),
                     TimeoutError("boom")]
                    ).query_items_paged_status({"ParentId": "L"}, page_size=2, max_pages=5)
check(_st == clim.ITEM_UNAVAILABLE and (_d or {}).get("complete") is False,
      "分页查询：中途超时 → 不完整（部分清单绝不当作完整）")

# ─────────────────────────────────────────────
print("\n[B] 人名池生命周期（P1-04：显式完成态 + sweep 门控）")
# ─────────────────────────────────────────────
check(_mk([_Resp(404, {})]).list_all_persons_status()[0] == clim.ITEM_NOT_FOUND,
      "list_all_persons_status：404 → NOT_FOUND")
check(_mk([_Resp(500, {})]).list_all_persons_status()[0] == clim.ITEM_UNAVAILABLE,
      "list_all_persons_status：500 → UNAVAILABLE（不再伪装空列表）")
check(_mk([_Resp(200, {"Items": [], "TotalRecordCount": 0})]).list_all_persons_status()[0]
      == clim.ITEM_FOUND, "list_all_persons_status：合法空 → FOUND（真空）")
check(_mk([_Resp(200, {})]).list_all_persons_status()[0] == clim.ITEM_UNAVAILABLE,
      "list_all_persons_status：200 + {} → UNAVAILABLE")

_pl = _grab_method(_SRC, "_pool_collect_persons")
check("return list(out.values()), complete, errors" in _pl
      and "list_all_persons_status" in _pl and 'complete = False' in _pl,
      "_pool_collect_persons 返回三元组 (persons, complete, errors)（严格状态接口）")
_pfw = _grab_method(_SRC, "_pool_fetch_worker")
check("_pcomplete" in _pfw and "_persons, _pcomplete, _perrs" in _pfw,
      "_pool_fetch_worker 解包完成态")
check("if not _pcomplete:" in _pfw,
      "sweep 仅在完整拉取时执行（部分拉取跳过生命周期刷新）")

_nsPC = {"logger": logger, "ITEM_FOUND": clim.ITEM_FOUND, "ITEM_NOT_FOUND": clim.ITEM_NOT_FOUND,
         "ITEM_UNAVAILABLE": clim.ITEM_UNAVAILABLE, "Dict": Dict, "List": List}
exec(_grab_method(_SRC, "_pool_collect_persons"), _nsPC)


class _PoolCli:
    def __init__(self, pages):
        self.pages = pages
        self.i = 0

    def query_items_status(self, params=None):
        return clim.ITEM_FOUND, {"Items": [], "TotalRecordCount": 0}, ""

    def list_all_persons_status(self, limit=500, start_index=0):
        _r = self.pages[min(self.i, len(self.pages) - 1)]
        self.i += 1
        return _r


class _PoolSelf:
    _pool_collect_persons = _nsPC["_pool_collect_persons"]
    POOL_PAGE = 500

    def __init__(self, cli):
        self._cli = cli
        self._libraries = []
        self._pool_stop = False
        self._pool_status = {}
        self.logs = []

    def _get_emby_libraries(self):
        return []

    def _push_log(self, lvl, msg):
        self.logs.append((lvl, msg))


_FULL = (clim.ITEM_FOUND, {"Items": [{"Id": f"P{i}", "Name": f"N{i}"} for i in range(500)],
                           "TotalRecordCount": 500}, "")
_FULL_P1 = (clim.ITEM_FOUND, {"Items": [{"Id": f"P{i}", "Name": f"N{i}"} for i in range(500)],
                              "TotalRecordCount": 1000}, "")
_FAIL2 = (clim.ITEM_UNAVAILABLE, {"Items": [], "TotalRecordCount": 0}, "http_error")
_pc1 = _PoolCli([_FULL])
_persons, _complete, _errs = _PoolSelf(_pc1)._pool_collect_persons(_pc1, "all")
check(len(_persons) == 500 and _complete is True and _errs == [],
      f"整页拉取成功 → complete=True（{len(_persons)} 人）")
_pc2 = _PoolCli([_FULL_P1, _FAIL2])
_persons, _complete, _errs = _PoolSelf(_pc2)._pool_collect_persons(_pc2, "all")
check(_complete is False and any("persons" in e for e in _errs),
      f"第二页失败 → complete=False（已入池的人保留，但不得 sweep），errors={_errs}")

# ─────────────────────────────────────────────
print("\n[C] 多服务器与探测（P1-05：按 server_id 隔离）")
# ─────────────────────────────────────────────
pdb = dbm.PeopleDb()
pdb.ensure_table()
PID = "EPL116"
dbm._x("DELETE FROM person WHERE plugin_id=?", (PID,))
pdb.upsert_people(plugin_id=PID, server_id="A", item_id="tv:1", item_type="Series",
                  title="S", series_name="S", nfo_path="X:/a/tv.nfo",
                  people=[{"before_name": "A", "Name": "A"}])
pdb.upsert_people(plugin_id=PID, server_id="A", item_id="tv:1", item_type="Episode",
                  title="S", series_name="S", season_num=1, episode_num=1,
                  nfo_path="X:/a/S01E01.nfo", people=[{"before_name": "A", "Name": "A"}])
pdb.upsert_people(plugin_id=PID, server_id="B", item_id="tv:1", item_type="Series",
                  title="S", series_name="S", nfo_path="Y:/b/tv.nfo",
                  people=[{"before_name": "A", "Name": "A"}])
pdb.upsert_people(plugin_id=PID, server_id="B", item_id="tv:1", item_type="Episode",
                  title="S", series_name="S", season_num=1, episode_num=1,
                  nfo_path="Y:/b/S01E01.nfo", people=[{"before_name": "A", "Name": "A"}])
pdb.upsert_people(plugin_id=PID, server_id="B", item_id="tv:1", item_type="Episode",
                  title="S", series_name="S", season_num=1, episode_num=9,
                  nfo_path="Y:/b/S01E09.nfo", people=[{"before_name": "A", "Name": "A"}])
_keys = pdb.probe_keys(plugin_id=PID)
check(set((_keys.get("items") or {}).keys()) == {"A", "B"},
      f"probe_keys：items 按 server_id 分组（{sorted((_keys.get('items') or {}).keys())}）")
check((_keys.get("episodes") or {}).get("A", {}).get("tv:1") == {(1, 1)}
      and (_keys.get("episodes") or {}).get("B", {}).get("tv:1") == {(1, 1), (1, 9)},
      "probe_keys：集号按服务器分组，绝不跨服务器并集"
      f"（A={(_keys.get('episodes') or {}).get('A', {}).get('tv:1')}）")

_pdc = _grab_method(_SRC, "_probe_deep_collect")
check("(skey, _ck)" in _pdc and "complete_servers" in _pdc and "query_items_paged_status" in _pdc,
      "_probe_deep_collect 主键含 server_id（(skey, ckey)）并返回 complete_servers")

_nsRM = {"logger": logger, "time": __import__("time"), "List": List}
exec(_grab_method(_SRC, "_probe_reverse_mark"), _nsRM)


class _RevDb:
    def __init__(self):
        self.calls = []

    def mark_deleted_by_episode(self, **kw):
        self.calls.append(kw)
        return 1


class _RevSelf:
    _probe_reverse_mark = _nsRM["_probe_reverse_mark"]
    PROBE_REVERSE_MAX = 100

    def __init__(self, db, servers, complete):
        self._people_db = db
        self._servers = servers
        self._complete = complete
        self._nfo_dead_grace_hours = 24
        self.events = []
        self.logs = []

    def _configured_server_keys(self):
        return set(self._servers)

    def _push_webhook_event(self, *a, **k):
        self.events.append((a, k))

    def _push_log(self, lvl, msg):
        self.logs.append((lvl, msg))


def _rec(skey):
    return {"key": "tmdb:1", "keys": ["tmdb:1"], "name": "S",
            "path": f"{skey}:/tv", "emby_id": f"e{skey}", "skey": skey}


# A 缺 E09、B 有 E09 → 只标 A 的 E09
_inv = {"series": {("A", "tmdb:1"): _rec("A"), ("B", "tmdb:1"): _rec("B")},
        "eps": {("A", "tmdb:1"): {(1, 1): {}}, ("B", "tmdb:1"): {(1, 1): {}, (1, 9): {}}},
        "complete_servers": {"A": True, "B": True}}
_db = {"items": {"A": {"tmdb:1"}, "B": {"tmdb:1"}},
       "episodes": {"A": {"tmdb:1": {(1, 1), (1, 9)}}, "B": {"tmdb:1": {(1, 1), (1, 9)}}}}
_rd = _RevDb()
_r = _RevSelf(_rd, ("A", "B"), None)._probe_reverse_mark(_inv, _db, {})
_sk = sorted({(c["server_id"], c["season_num"], c["episode_num"]) for c in _rd.calls})
check(_sk == [("A", 1, 9)],
      f"A 缺 E09、B 有 E09 → 只标 A 的 E09（不得用 B 的并集掩盖），实际 {_sk}")

# A 的清单不完整 → A 一律跳过
_inv2 = dict(_inv); _inv2["complete_servers"] = {"A": False, "B": True}
_rd2 = _RevDb()
_RevSelf(_rd2, ("A", "B"), None)._probe_reverse_mark(_inv2, _db, {})
check(_rd2.calls == [],
      f"A 清单不完整 → 跳过其反向标记（绝不把「没读到」当「已删除」），实际 {_rd2.calls}")

# A 有 E09、B 缺 E09 → 只标 B 的 E09
_inv3 = {"series": {("A", "tmdb:1"): _rec("A"), ("B", "tmdb:1"): _rec("B")},
         "eps": {("A", "tmdb:1"): {(1, 1): {}, (1, 9): {}}, ("B", "tmdb:1"): {(1, 1): {}}},
         "complete_servers": {"A": True, "B": True}}
_rd3 = _RevDb()
_RevSelf(_rd3, ("A", "B"), None)._probe_reverse_mark(_inv3, _db, {})
_sk3 = sorted({(c["server_id"], c["episode_num"]) for c in _rd3.calls})
check(_sk3 == [("B", 9)], f"仅 B 缺 E09 → 只标 B（{_sk3}）")

# ─────────────────────────────────────────────
print("\n[D] 路径级映射（P1-06：Webhook 按原始 Emby 路径唯一反推 lib/idx）")
# ─────────────────────────────────────────────
_nsCTX = {"logger": logger}
exec(_grab_method(_SRC, "_resolve_lib_ctx_for_emby_path"), _nsCTX)


class _CtxSelf:
    _resolve_lib_ctx_for_emby_path = _nsCTX["_resolve_lib_ctx_for_emby_path"]

    def __init__(self, libs):
        self._libs = libs
        self.warns = []

    def _get_emby_libraries(self):
        return self._libs

    def _warn_once(self, key, msg):
        self.warns.append(key)


_LIBS = [
    {"skey": "A", "lib_id": "L1",
     "paths": [{"idx": 0, "emby_path": "/mnt/movie"}, {"idx": 1, "emby_path": "/mnt/movie2"}]},
    {"skey": "B", "lib_id": "L9",
     "paths": [{"idx": 0, "emby_path": "/mnt/movie"}]},
]
_o = _CtxSelf(_LIBS)
check(_o._resolve_lib_ctx_for_emby_path("A", "/mnt/movie2/S01/x.mkv") == ("L1", 1),
      "最长前缀：/mnt/movie2 命中库 L1 的第 2 条 Locations")
check(_o._resolve_lib_ctx_for_emby_path("A", "/mnt/movie/x.mkv") == ("L1", 0),
      "第 1 条 Locations 命中 idx=0")
check(_o._resolve_lib_ctx_for_emby_path("A", "/other/x.mkv") == (None, None),
      "无命中 → (None, None)（退回服务器级映射）")
check(_o._resolve_lib_ctx_for_emby_path("B", "/mnt/movie/x.mkv") == ("L9", 0),
      "只在该服务器内匹配（B 的路径不套用 A 的库）")

_o2 = _CtxSelf([{"skey": "A", "lib_id": "L1",
                 "paths": [{"idx": 0, "emby_path": "/mnt/a"}, {"idx": 1, "emby_path": "/mnt/a"}]}])
check(_o2._resolve_lib_ctx_for_emby_path("A", "/mnt/a/x") == (None, None) and bool(_o2.warns),
      "多条同长 Locations 前缀重叠 → 歧义 (None, None) + 告警（不任取第一条）")

check("_resolve_lib_ctx_for_emby_path(_sid, p)" in _grab_method(_SRC, "_normalize_webhook_path"),
      "_normalize_webhook_path 已接入路径级上下文反推再调统一 resolver")

# ─────────────────────────────────────────────
print("\n[E] 任务隔离（P1-08：运行中新请求独立入队，不改当前 Job）")
# ─────────────────────────────────────────────
_nsIso = {"logger": logger, "time": __import__("time"), "json": __import__("json"),
          "List": List, "Optional": Optional, "Dict": Dict, "Any": Any}
exec(_grab_method(_SRC, "_tx_build_cfg_snapshot"), _nsIso)
exec(_grab_method(_SRC, "_tx_enqueue_request"), _nsIso)
exec(_grab_method(_SRC, "_tx_request_consume"), _nsIso)
exec(_grab_method(_SRC, "_tx_pump_wait_jobs"), _nsIso)


class _JobDbQ:
    def __init__(self):
        self.created = []

    def create(self, **kw):
        self.created.append(kw)
        return True


class _IsoSelf:
    _tx_build_cfg_snapshot = _nsIso["_tx_build_cfg_snapshot"]
    _tx_enqueue_request = _nsIso["_tx_enqueue_request"]
    _tx_request_consume = _nsIso["_tx_request_consume"]
    _tx_pump_wait_jobs = _nsIso["_tx_pump_wait_jobs"]

    def __init__(self, requested=False, job_id="", snap=None):
        self._tx_requested = requested
        self._tx_job_id = job_id
        self._tx_source = ""
        self._tx_target_scope = "both"
        self._tx_scope_items = set()
        self._tx_only_terms = set()
        self._tx_cfg_snapshot = snap
        self._tx_stop = False
        self._tx_wait_jobs = None
        self._tx_batch = 0
        self._translate_batching = "per_title"
        self._jdb = _JobDbQ()

    def _collect_trans_types(self):
        return {"translate": {"person": True, "role": True}, "limits": {"actor": 5}}

    def _configured_server_keys(self):
        return set()

    def _tx_scope(self):
        return "both"

    def _tx_job_set(self, *a, **k):
        pass

    def _tx_wake(self):
        pass

    def _push_log(self, *a, **k):
        pass

    def _tx_job_db(self):
        return self._jdb


# 全库任务运行中 → 单条重翻请求独立入队，不改当前 Job
_o = _IsoSelf(requested=True, job_id="JBIG", snap={"scope": "both", "version": 2})
_o._tx_request_consume(source="library", items=["ItemX"], scope="person")
check(_o._tx_source == "" and _o._tx_target_scope == "both" and not _o._tx_scope_items,
      "运行中新请求**不改**当前 Job 的 source/scope/items（开始后不可变）")
check(_o._tx_cfg_snapshot == {"scope": "both", "version": 2},
      "运行中新请求**不覆盖**当前 Job 快照")
check(len(_o._tx_wait_jobs or []) == 1 and _o._tx_wait_jobs[0]["items"] == ["ItemX"]
      and _o._tx_wait_jobs[0]["scope"] == "person",
      "新请求独立入队（各自 items/scope）")
check(_o._tx_wait_jobs[0]["job_id"] and bool(_o._jdb.created),
      "排队任务有自己的 job_id 与持久化记录")
check(_o._tx_job_id == "JBIG", "当前 Job 的 job_id 不被改写")

# 当前任务结束 → 出队启动排队请求
_o._tx_requested = False
_started = _o._tx_pump_wait_jobs()
check(_started is True and _o._tx_requested is True,
      "任务结束后出队启动排队请求（回到请求态）")
check(_o._tx_source == "library" and list(_o._tx_scope_items) == ["ItemX"]
      and _o._tx_target_scope == "person",
      "出队启动后当前 Job 为排队请求的 source/items/scope")
check(not (_o._tx_wait_jobs or []), "出队后等待队列清空")

# 排队请求去重：等价请求只保留一条
_o2 = _IsoSelf(requested=True, job_id="J1", snap={"scope": "both"})
_o2._tx_request_consume(source="pool")
_o2._tx_request_consume(source="pool")
check(len(_o2._tx_wait_jobs or []) == 1,
      "等价排队请求去重（同一 source/scope/items/terms 只入队一次）")

# ─────────────────────────────────────────────
print("\n[F] 强制任务复合键（P2-10：_tx_force_jobs 按 (job_id, item_id)）")
# ─────────────────────────────────────────────
_nsFE = {"logger": logger}
exec(_grab_method(_SRC, "_tx_force_enqueue"), _nsFE)


class _FESelf:
    _tx_force_enqueue = _nsFE["_tx_force_enqueue"]

    def __init__(self):
        self._tx_force_jobs = None
        self._tx_job_id = ""


_f = _FESelf()
_f._tx_force_enqueue("I1", {"title": "a"}, job_id="J1")
_f._tx_force_enqueue("I1", {"title": "b"}, job_id="J2")
check(len(_f._tx_force_jobs) == 2 and _f._tx_force_jobs[("J1", "I1")]["title"] == "a"
      and _f._tx_force_jobs[("J2", "I1")]["title"] == "b",
      "同一 item_id 属于两个任务 → 各自保留自己的 payload（不互相覆盖）")

_fr = _grab_method(_SRC, "_tx_force_round")
check("_orig_key" in _fr and "_ekey != _cur_jid" in _fr and "_jobs.pop(_orig_key, None)" in _fr,
      "_tx_force_round 只处理当前 job_id 的条目（复合键，pop 本任务项）")

# ─────────────────────────────────────────────
print("\n[G] Person 元数据安全（P2-11：改名后复读校验）")
# ─────────────────────────────────────────────
_FULL_DTO = {"Id": "P1", "Name": "Old", "Overview": "简介",
             "LockedFields": ["Name"], "ProviderIds": {"Tmdb": "1"}, "ImageTags": {"Primary": "x"}}


def _mk_ren(seq_details, post_ok=True):
    c = clim.EmbyClient("http://x", "k")
    _it = iter(seq_details)
    c.get_person_detail = lambda pid: next(_it, None)
    c._post = lambda path, data=None: post_ok
    return c


check(_mk_ren([dict(_FULL_DTO), dict(_FULL_DTO, Name="New")]).rename_person("P1", "New") is True,
      "改名成功且其它元数据逐项不变 → True")
check(_mk_ren([None]).rename_person("P1", "New") is False,
      "完整 DTO 取不到 → False（不提交稀疏对象）")

_broken = dict(_FULL_DTO, Name="New")
_broken["Overview"] = None   # 回写后 Overview 被清空
check(_mk_ren([dict(_FULL_DTO), _broken]).rename_person("P1", "New") is False,
      "回写后 Overview 变化 → 复读校验失败 → False（不静默接受数据损坏）")


def _raise_after(pid):
    raise RuntimeError("boom")


_c = clim.EmbyClient("http://x", "k")
_n = [0]


def _detail_then_raise(pid):
    _n[0] += 1
    if _n[0] == 1:
        return dict(_FULL_DTO)
    raise RuntimeError("after read boom")


_c.get_person_detail = _detail_then_raise
_c._post = lambda path, data=None: True
check(_c.rename_person("P1", "New") is True,
      "复读本身失败（非致命）→ 不阻断改名成功")

check('_PERSON_KEEP_FIELDS' in _CLI and '"ImageTags"' in _CLI,
      "保留字段含 ImageTags/Overview/LockedFields/ProviderIds")
check('ChannelMappingInfo,ProviderIds,Overview,LockedFields,ImageTags' in _CLI,
      "get_person_detail 字段集补齐（能校验的字段先取全）")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
