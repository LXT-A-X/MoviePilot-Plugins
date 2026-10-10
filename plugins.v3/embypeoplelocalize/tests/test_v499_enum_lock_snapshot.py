# -*- coding: utf-8 -*-
"""v4.6.99 回归测试：审查报告（v4.6.98）P1-01 ~ P1-05 + P2。

运行：python tests/test_v499_enum_lock_snapshot.py

覆盖：
  T1 Emby 季集枚举三态：get_series_episodes_status（分页完整性）/ query_items_status
  T2 _reconcile_missing_episodes：可信差集 vs 不可信（查询失败 / 分页不完整 / 结构异常）
  T3 include_legacy：多服务器不认领 legacy 空来源行（单服务器可）
  T4 P1-04 _api_pool_refetch_one 补齐统一任务锁（源码级）
  T5 P1-03 Job Snapshot 扩充 + 版本 + 运行中配置「下个任务生效」提示（源码级 + 行为级）
  T6 P2 清理接口结构化返回 + 文案（源码级）
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
TMP = Path(tempfile.mkdtemp(prefix="epl99_"))
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
_DB = (PLUGIN_DIR / "db.py").read_text(encoding="utf-8")

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

_spec = importlib.util.spec_from_file_location("epl_db99", PLUGIN_DIR / "db.py")
dbm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dbm)
_cs = importlib.util.spec_from_file_location("epl_cli99", PLUGIN_DIR / "emby_client.py")
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
print("v4.6.99 回归测试（枚举完整性 / 服务器白名单 / 任务锁 / Snapshot / 清理）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] Emby 季集枚举三态（get_series_episodes_status / query_items_status）")
# ─────────────────────────────────────────────


class _Resp:
    def __init__(self, code, payload=None, bad=False):
        self.status_code, self._p, self._bad = code, payload, bad

    def json(self):
        if self._bad:
            raise ValueError("not json")
        return self._p


class _Sess:
    """按调用序号依次返回给定响应；用完后一直返回最后一个。"""

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


# 成功且完整：一页足量 + 末页不满
_c = _mk([_Resp(200, {"Items": [{"IndexNumber": i} for i in range(3)], "TotalRecordCount": 3})])
check(_c.get_series_episodes_status("1")[0] == clim.ITEM_FOUND, "成功且完整 → FOUND")
# 分页：第一页满、第二页失败 → 不完整 → UNAVAILABLE
_c = _mk([_Resp(200, {"Items": [{"IndexNumber": i} for i in range(200)], "TotalRecordCount": 300}),
          _Resp(500, {})])
_st, _items, _why = _c.get_series_episodes_status("1", limit=200)
check(_st == clim.ITEM_UNAVAILABLE and "http_error" in _why,
      f"分页中途 500 → UNAVAILABLE（不把未返回的集当成已删除），实际 {_st}/{_why}")
check(len(_items) == 200, "已取到的 200 集仍返回（但标记为不可信）")
# 空页但服务器声称还有 → 不完整
_c = _mk([_Resp(200, {"Items": [], "TotalRecordCount": 300})])
_st, _items, _why = _c.get_series_episodes_status("1")
check(_st == clim.ITEM_UNAVAILABLE and "empty_page_but_total" in _why,
      f"空页但总数>已取 → UNAVAILABLE，实际 {_st}/{_why}")
# 总数一致的空页 → 完整（真空剧集）
_c = _mk([_Resp(200, {"Items": [], "TotalRecordCount": 0})])
check(_c.get_series_episodes_status("1") == (clim.ITEM_FOUND, [], ""), "总数一致的空结果 → FOUND（真空）")
# 404 → NOT_FOUND；401/超时 → UNAVAILABLE；无 user_id → UNAVAILABLE
check(_mk([_Resp(404, {})]).get_series_episodes_status("1")[0] == clim.ITEM_NOT_FOUND, "404 → NOT_FOUND")
check(_mk([_Resp(401, {})]).get_series_episodes_status("1")[0] == clim.ITEM_UNAVAILABLE, "401 → UNAVAILABLE")
check(_mk([TimeoutError("t")]).get_series_episodes_status("1")[0] == clim.ITEM_UNAVAILABLE, "超时 → UNAVAILABLE")
check(_mk([_Resp(200, None, bad=True)]).get_series_episodes_status("1")[0] == clim.ITEM_UNAVAILABLE,
      "响应非法 JSON → UNAVAILABLE")
check(_mk([_Resp(200, {"Items": []})], user=None).get_series_episodes_status("1")[0] == clim.ITEM_UNAVAILABLE,
      "无 user_id → UNAVAILABLE（不当作空剧）")
check(_mk([_Resp(200, {"Items": []})]).get_series_episodes_status("")[0] == clim.ITEM_UNAVAILABLE,
      "空 series_id → UNAVAILABLE")
# 兼容包装
check(_mk([_Resp(200, {"Items": [{"IndexNumber": 1}], "TotalRecordCount": 1})]).get_series_episodes("1")
      == [{"IndexNumber": 1}], "get_series_episodes 兼容：FOUND → items")
check(_mk([_Resp(500, {})]).get_series_episodes("1") == [], "get_series_episodes 兼容：UNAVAILABLE → []")
# query_items_status
check(_mk([_Resp(200, {"Items": [{"Id": "1"}], "TotalRecordCount": 1})]).query_items_status({})[0]
      == clim.ITEM_FOUND, "query_items_status：200 → FOUND")
check(_mk([_Resp(404, {})]).query_items_status({})[0] == clim.ITEM_NOT_FOUND, "query_items_status：404 → NOT_FOUND")
check(_mk([_Resp(500, {})]).query_items_status({})[0] == clim.ITEM_UNAVAILABLE, "query_items_status：500 → UNAVAILABLE")
check(_mk([_Resp(200, {})], user=None).query_items_status({})[0] == clim.ITEM_UNAVAILABLE,
      "query_items_status：无 user_id → UNAVAILABLE（不当作空列表）")

# ─────────────────────────────────────────────
print("\n[T2] _reconcile_missing_episodes：可信差集 vs 不可信")
# ─────────────────────────────────────────────
_NS2 = {"logger": logger,
        "ITEM_FOUND": clim.ITEM_FOUND, "ITEM_NOT_FOUND": clim.ITEM_NOT_FOUND,
        "ITEM_UNAVAILABLE": clim.ITEM_UNAVAILABLE, "List": List}
exec(_grab_method(_SRC, "_reconcile_missing_episodes"), _NS2)

pdb = dbm.PeopleDb()
pdb.ensure_table()
PID = "EPL99"
PREF = "X:/lib/Show"


def _seed():
    dbm._x("DELETE FROM person WHERE plugin_id=?", (PID,))
    for _e in (1, 2, 3):
        pdb.upsert_people(plugin_id=PID, server_id="S1", item_id="tvdb:9", item_type="Episode",
                          title="T", series_name="T", season_num=1, episode_num=_e,
                          nfo_path=f"{PREF}/S01E{_e:02d}.nfo",
                          people=[{"before_name": "A", "Name": "A"}])


class _RC:
    _reconcile_missing_episodes = _NS2["_reconcile_missing_episodes"]

    def __init__(self, st, items, total=None):
        self._st, self._items, self._total = st, items, total

    def _get_series_episodes_status(self, iid, limit=200):
        return self._st, self._items, "x"


class _RR:
    _reconcile_missing_episodes = _NS2["_reconcile_missing_episodes"]

    def __init__(self, cli):
        self._people_db = pdb
        self._cli = cli

    def _rc(self):
        return self._reconcile_missing_episodes(self._cli, "9", PREF, "S1", "series")


class _Cli:
    def __init__(self, st, items):
        self.st, self.items = st, items

    def get_series_episodes_status(self, iid, limit=200):
        return self.st, list(self.items), "why"

    def query_items_status(self, params=None):
        return self.st, {"Items": list(self.items), "TotalRecordCount": len(self.items)}, "why"

    def get_series_episodes(self, iid):
        return list(self.items)


# handler/方法内部用 self.__class__.__name__ 作为 plugin_id → 行必须写同一个 id
PID = _RR.__name__
PREF = "X:/lib/Show"
dbm._x("DELETE FROM person WHERE plugin_id=?", (PID,))
for _e in (1, 2, 3):
    pdb.upsert_people(plugin_id=PID, server_id="S1", item_id="tvdb:9", item_type="Episode",
                      title="T", series_name="T", season_num=1, episode_num=_e,
                      nfo_path=f"{PREF}/S01E{_e:02d}.nfo",
                      people=[{"before_name": "A", "Name": "A"}])


_r = _RR(None)._rc()
check(_r[0] == [] and _r[1] is False, f"无客户端 → 不可信 {_r}")
_r = _RR(_Cli(clim.ITEM_UNAVAILABLE, []))._rc()
check(_r[0] == [] and _r[1] is False, f"查询失败 → 不可信、不标记 {_r}")
_r = _RR(_Cli(clim.ITEM_FOUND, [{"ParentIndexNumber": 1, "IndexNumber": 1}]))._rc()
check(_r[0] == [(1, 2), (1, 3)] and _r[1] is True, f"可信差集 = 真消失的 2 集 {_r}")
_r = _RR(_Cli(clim.ITEM_FOUND, [{"ParentIndexNumber": 1, "IndexNumber": 1},
                                {"ParentIndexNumber": 1, "IndexNumber": 2},
                                {"ParentIndexNumber": 1, "IndexNumber": 3}]))._rc()
check(_r[0] == [] and _r[1] is True, f"一集不缺 → 可信空差集（不标记）{_r}")
_r = _RR(_Cli(clim.ITEM_FOUND, [{"Name": "无季集号"}]))._rc()
check(_r[1] is False, f"返回条目但无季/集号（结构异常）→ 不可信 {_r}")
_r = _RR(_Cli(clim.ITEM_FOUND, []))._rc()
check(_r[1] is True and _r[0] == [(1, 1), (1, 2), (1, 3)],
      f"成功枚举为空 → 差集=全季（真删除）{_r}")
check(_RR(_Cli(clim.ITEM_FOUND, []))._reconcile_missing_episodes(_Cli(clim.ITEM_FOUND, []),
                                                                  "9", "X:/none", "S1", "series")[2]
      == "no_db_rows", "库中无该前缀记录 → 记 no_db_rows（可信、无差异）")

# ─────────────────────────────────────────────
print("\n[T3] include_legacy：多服务器不认领 legacy 空来源行")
# ─────────────────────────────────────────────
dbm._x("DELETE FROM person WHERE plugin_id=?", (PID,))
for _sid, _iid, _e in (("A", "a1", 1), ("", "c1", 2)):
    pdb.upsert_people(plugin_id=PID, server_id=_sid, item_id=_iid, item_type="Episode",
                      title="T", series_name="T", season_num=1, episode_num=_e,
                      nfo_path=f"{PREF}/S01E{_e:02d}.nfo", people=[{"before_name": "A", "Name": "A"}])
_n = pdb.mark_deleted_by_nfo_path_prefix(plugin_id=PID, path_prefix=PREF, server_id="A",
                                         include_legacy=False)
check(_n == 1, f"多服务器（include_legacy=False）→ 只标 A 的 1 行（不认领 legacy），实际 {_n}")
dbm._x("UPDATE person SET deleted_at='' WHERE plugin_id=?", (PID,))
_n = pdb.mark_deleted_by_nfo_path_prefix(plugin_id=PID, path_prefix=PREF, server_id="A",
                                        include_legacy=True)
check(_n == 2, f"单服务器（include_legacy=True）→ 连 legacy 一起 2 行，实际 {_n}")
dbm._x("UPDATE person SET deleted_at='' WHERE plugin_id=?", (PID,))
check("def _scope_sql_soft(server_id: Optional[str], include_legacy: bool = True)" in _DB,
      "db.py `_scope_sql_soft` 支持 include_legacy")

# ─────────────────────────────────────────────
print("\n[T4] P1-04：_api_pool_refetch_one 补齐统一任务锁")
# ─────────────────────────────────────────────
_rf = _grab_method(_SRC, "_api_pool_refetch_one")
check("_task_busy_msg()" in _rf, "_api_pool_refetch_one 已接入 _task_busy_msg（后端拦截，不靠前端禁用）")
check(_rf.index("_task_busy_msg()") < _rf.index("_emby_client_for_server"), "任务锁判定在「查 Emby」之前")

# ─────────────────────────────────────────────
print("\n[T5] P1-03：Job Snapshot 扩充 + 版本 + 运行中配置下个任务生效")
# ─────────────────────────────────────────────
_rc = _grab_method(_SRC, "_tx_request_consume")
# v4.6.116（P1-08）：快照构建已抽成 _tx_build_cfg_snapshot（任务启动/入队共用），字段在其体内
_snaprc = _grab_method(_SRC, "_tx_build_cfg_snapshot")
for _f in ('"version"', '"limits"', '"tmdb_credits"', '"tmdb_fill"', '"auto_writeback"',
           '"nfo_preview"', '"batching"', '"batch_size"', '"libraries"', '"servers"', '"llm_model"'):
    check(_f in _snaprc, f"快照覆盖 {_f}")
check("TX_SNAPSHOT_VERSION: int = 2" in _SRC, "快照版本常量 TX_SNAPSHOT_VERSION = 2")
_lim = _grab_method(_SRC, "_tx_limits_by_level")
check('_snap.get("limits")' in _lim, "_tx_limits_by_level 任务期间取快照（人数上限冻结）")
_wb = _grab_method(_SRC, "_wb_writeback_enabled")
check('_snap.get("auto_writeback")' in _wb, "_wb_writeback_enabled 任务期间取快照（写回策略冻结）")
_sv = _grab_method(_SRC, "_api_save_config")
check("applied_next_task" in _sv and "下一个任务" in _sv, "运行中保存配置 → 明确提示「下一个任务生效」")

# 行为级：快照存在时优先取快照
_ns3 = {"logger": logger}
exec(_grab_method(_SRC, "_tx_limits_by_level"), _ns3)
exec(_grab_method(_SRC, "_wb_writeback_enabled"), _ns3)


class _SnapF:
    _tx_limits_by_level = _ns3["_tx_limits_by_level"]
    _wb_writeback_enabled = _ns3["_wb_writeback_enabled"]

    def __init__(self, snap, live_limits, auto=True, preview=False):
        self._tx_cfg_snapshot = snap
        self._live = live_limits
        self._auto_writeback = auto
        self._nfo_preview = preview

    def _collect_trans_types(self):
        return {"limits": dict(self._live)}


_o = _SnapF({"limits": {"movie": {"actor": 3}, "tvshow": {"actor": 3}, "episode": {"actor": 3}},
             "auto_writeback": False, "nfo_preview": False}, {"actor": 99})
check(_o._tx_limits_by_level()["tvshow"] == {"actor": 3}, "有快照 → 用快照人数上限（忽略实时 99）")
check(_o._wb_writeback_enabled() is False, "有快照 → 用快照写回策略（实时 True 被冻结忽略）")
_o = _SnapF(None, {"actor": 99}, auto=True, preview=False)
check(_o._tx_limits_by_level()["tvshow"] == {"actor": 99}, "无快照 → 用实时配置")
check(_o._wb_writeback_enabled() is True, "无快照 → 用实时写回策略")

# ─────────────────────────────────────────────
print("\n[T6] P2：清理接口结构化返回 + 文案")
# ─────────────────────────────────────────────
_cf = _grab_method(_SRC, "_cleanup_dirty_webhook_events")
for _f in ('"success"', '"removed_count"', '"kept_error_count"', '"error_message"'):
    check(_f in _cf, f"清理返回含 {_f}")
_pm = _grab_method(_SRC, "_api_db_purge_missing")
check("events_unconfirmed" in _pm, "清理接口回报「状态无法确认」的事件数")
check("当前没有插件管理的失效记录，无需清理" in _pm, "0 条文案保留")
check("读取失效记录数量失败，已取消清理" in _pm, "计数失败文案保留")
check("失效记录数量为 0，但部分事件状态无法确认，未执行强制清理" in _pm,
      "事件清理失败文案：不显示清理成功")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)