# -*- coding: utf-8 -*-
"""v4.6.98 回归测试：审查报告（v4.6.97）P1-01 ~ P1-04 修复。

运行：python tests/test_v498_delete_safety.py

覆盖报告「八、必须新增的回归测试」关键项：
  A 空库 / 未管理媒体删除 → 完全静默（无 missing、无观察期、无通知、无写库）
  B 已管理媒体删除：容器明确不存在（NOT_FOUND）→ 进入观察期；
    容器仍在（FOUND，只少了几集）→ 只标真正消失的集；
    容器状态未知（UNAVAILABLE）→ 不批量标记、不发普通删除通知
  C 多服务器：缺 server_id 且多台 / 无服务 → 不修改任何记录
  D 数据库错误：media_probe 查询失败 → status=error（≠未管理）；清理遇 error 保留事件；
    count_missing() 返回 -1 → 取消清理

所有断言都跑**真实代码**：emby_client 三态用假 session；
删除链路用真实 SQLite + 真实提取的 _handle_webhook_delete / _reconcile_missing_episodes /
_resolve_unique_server_id / _cleanup_dirty_webhook_events。
"""
import os
import re
import sys
import time
import types
import textwrap
import tempfile
import importlib.util
from pathlib import Path
from typing import Any, List, Optional, Dict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl98_"))
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
_d = types.ModuleType("app.sdk.db")
_sch = types.ModuleType("app.schemas")
_sch.ServiceInfo = object
sys.modules.update({"app": _m, "app.sdk": _s, "app.sdk.logging": _l, "app.sdk.config": _c,
                    "app.sdk.db": _d, "app.schemas": _sch})

# requests 打桩（本地环境可能未安装；只用到 Session() 的 headers/close）
_req = types.ModuleType("requests")


class _ReqSession:
    def __init__(self):
        self.headers = {}

    def close(self):
        pass


_req.Session = _ReqSession
sys.modules["requests"] = _req

_spec = importlib.util.spec_from_file_location("epl_db98", PLUGIN_DIR / "db.py")
dbm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dbm)

_cli_spec = importlib.util.spec_from_file_location("epl_cli98", PLUGIN_DIR / "emby_client.py")
clim = importlib.util.module_from_spec(_cli_spec)
_cli_spec.loader.exec_module(clim)


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


# 提取真实方法到一个共享命名空间（提供它们引用的模块级名字）
_NS = {"logger": logger, "os": os, "time": time, "re": re, "Any": Any, "Optional": Optional,
       "List": List, "Dict": Dict, "split_media_id": lambda x: ("", ""),
       "ITEM_FOUND": clim.ITEM_FOUND, "ITEM_NOT_FOUND": clim.ITEM_NOT_FOUND,
       "ITEM_UNAVAILABLE": clim.ITEM_UNAVAILABLE}
for _n in ("_resolve_unique_server_id", "_reconcile_missing_episodes",
           "_handle_webhook_delete", "_cleanup_dirty_webhook_events",
           "_configured_server_keys"):
    exec(_grab_method(_SRC, _n), _NS)

print("=" * 72)
print("v4.6.98 回归测试（删除安全：P1-01 ~ P1-04）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] emby_client 三态（FOUND / NOT_FOUND / UNAVAILABLE）")
# ─────────────────────────────────────────────


class _Resp:
    def __init__(self, code, payload=None, bad_json=False):
        self.status_code = code
        self._payload = payload
        self._bad = bad_json

    def json(self):
        if self._bad:
            raise ValueError("not json")
        return self._payload


class _Sess:
    def __init__(self, resp=None, exc=None):
        self.resp, self.exc = resp, exc

    def get(self, *a, **k):
        if self.exc:
            raise self.exc
        return self.resp

    def close(self):
        pass


def _mk_client(resp=None, exc=None, user="u1"):
    c = clim.EmbyClient("http://emby.test:8096", "k")
    c.session = _Sess(resp, exc)
    c._get_user_id = lambda: user
    return c


_c = _mk_client(_Resp(200, {"Id": "32027", "Type": "Series"}))
_st, _data = _c._get_status("/x")
check(_st == clim.ITEM_FOUND and (_data or {}).get("Id") == "32027", "HTTP 200 + JSON → FOUND")
check(_mk_client(_Resp(404))._get_status("/x")[0] == clim.ITEM_NOT_FOUND,
      "HTTP 404 → NOT_FOUND（明确不存在）")
for _code in (400, 401, 403, 500, 502, 503):
    _st, _dd = _mk_client(_Resp(_code))._get_status("/x")
    check(_st == clim.ITEM_UNAVAILABLE and _dd is None, f"HTTP {_code} → UNAVAILABLE（不是「不存在」）")
check(_mk_client(exc=TimeoutError("timeout"))._get_status("/x")[0] == clim.ITEM_UNAVAILABLE,
      "超时/连接失败 → UNAVAILABLE")
check(_mk_client(_Resp(200, None, bad_json=True))._get_status("/x")[0] == clim.ITEM_UNAVAILABLE,
      "响应非法 JSON → UNAVAILABLE")
check(_mk_client(_Resp(404)).fetch_item_status("32027")[0] == clim.ITEM_NOT_FOUND,
      "fetch_item_status：404 → NOT_FOUND")
check(_mk_client(_Resp(200, {"Id": "1"}), user=None).fetch_item_status("1")[0] == clim.ITEM_UNAVAILABLE,
      "fetch_item_status：无 user_id → UNAVAILABLE")
check(_mk_client(_Resp(200, {"Id": "1"})).fetch_item_status("")[0] == clim.ITEM_UNAVAILABLE,
      "fetch_item_status：空 item_id → UNAVAILABLE")
check(_mk_client(_Resp(200, {"Id": "1"})).fetch_item("1") == {"Id": "1"}, "fetch_item 兼容：FOUND → dict")
check(_mk_client(_Resp(404)).fetch_item("1") is None, "fetch_item 兼容：NOT_FOUND → None")
check(_mk_client(_Resp(500)).fetch_item("1") is None, "fetch_item 兼容：UNAVAILABLE → None")

# ─────────────────────────────────────────────
print("\n[T2] _resolve_unique_server_id（缺 server_id 时不得跨服务器）")
# ─────────────────────────────────────────────


class _Svc:
    def __init__(self, n):
        self.name = n


class _RF:
    _resolve_unique_server_id = _NS["_resolve_unique_server_id"]
    _configured_server_keys = _NS["_configured_server_keys"]

    def __init__(self, svcs):
        self._svcs = svcs

    def _get_all_emby_services(self):
        return self._svcs

    def _get_server_identifier(self, svc):
        return f"{svc.name}_192_168_2_15_8096"


# v4.6.99（报告 P1-02 B）：**非空 ≠ 有效** —— ServerId 必须在已配置服务白名单内
check(_RF([_Svc("Emby")])._resolve_unique_server_id("Emby_192_168_2_15_8096") == ("Emby_192_168_2_15_8096", ""),
      "事件带 ServerId 且能映射到已配置服务 → 采用")
check(_RF([])._resolve_unique_server_id("S1")[0] == "", "0 台 Emby + 非空 ServerId → 未知（拒绝写库）")
_sid, _err = _RF([_Svc("A"), _Svc("B")])._resolve_unique_server_id("某未知GUID")
check(_sid == "" and "无法映射" in _err, f"2 台 Emby + 未知 GUID → 拒绝（{_err}）")
check(_RF([_Svc("Emby")])._resolve_unique_server_id("")[0] == "Emby_192_168_2_15_8096",
      "只 1 台 Emby + 无 ServerId → 唯一可确定")
_sid, _err = _RF([_Svc("A"), _Svc("B")])._resolve_unique_server_id("")
check(_sid == "" and "2 台" in _err, f"2 台 Emby + 无 ServerId → 拒绝（{_err}）")

# ─────────────────────────────────────────────
print("\n[T3] db 写入/删除函数：强制 server scope（P1-02 E）")
# ─────────────────────────────────────────────
pdb = dbm.PeopleDb()
pdb.ensure_table()
PID = "EPL98"
_PREF = "/Media/悠哉日常大王"


def _ins(sid, iid, s, e):
    pdb.upsert_people(plugin_id=PID, server_id=sid, item_id=iid, item_type="Episode",
                      title="E", series_name="悠哉日常大王", season_num=s, episode_num=e,
                      library_name="L", nfo_path=f"{_PREF}/S0{s}/E0{e}.nfo",
                      people=[{"Type": "Actor", "before_name": "小岩井琴里", "Name": "小岩井琴里",
                               "before_role": "r", "Role": "r"}])


def _reset():
    dbm._x("UPDATE person SET deleted_at='' WHERE plugin_id=?", (PID,))


def _miss():
    return pdb.count_missing(plugin_id=PID)


dbm._x("DELETE FROM person WHERE plugin_id=?", (PID,))
_ins("A", "aa", 1, 1)
_ins("A", "aa", 1, 2)
_ins("B", "bb", 1, 1)
_ins("", "cc", 1, 1)
check(pdb.mark_deleted_by_nfo_path_prefix(plugin_id=PID, path_prefix=_PREF) == 0,
      "server_id=None 默认被拒（不写库）")
check(_miss() == 0, "被拒后无任何行进入观察期")
check(pdb.mark_deleted_by_nfo_path_prefix(plugin_id=PID, path_prefix=_PREF, server_id="A") == 3,
      "server_id='A' → 只标 A 的 2 行 + legacy 空来源 1 行 = 3")
_b = dbm._q("SELECT COUNT(*) c FROM person WHERE plugin_id=? AND server_id='B' "
            "AND deleted_at!='' AND deleted_at IS NOT NULL", (PID,))
check(int(_b[0]["c"]) == 0, "B 服记录未被 A 服删除波及（跨服务器隔离）")
_reset()
check(pdb.mark_deleted_by_nfo_path_prefix(plugin_id=PID, path_prefix=_PREF,
                                          server_id=None, allow_unscoped=True) == 4,
      "显式 allow_unscoped=True → 全来源 4 行")
_reset()
check(pdb.mark_deleted_by_media(plugin_id=PID, item_id="aa") == 0,
      "mark_deleted_by_media：server_id=None 默认被拒")
check(pdb.mark_deleted_by_media(plugin_id=PID, item_id="aa", server_id="A") == 2,
      "mark_deleted_by_media：带 server_id 正常")
_reset()
check(pdb.mark_deleted_episodes_by_prefix(plugin_id=PID, path_prefix=_PREF, pairs=[(1, 1)]) == 0,
      "mark_deleted_episodes_by_prefix：server_id=None 默认被拒")
check(pdb.mark_deleted_by_nfo_path(plugin_id=PID, nfo_path=f"{_PREF}/S01/E01.nfo") == 0,
      "mark_deleted_by_nfo_path：server_id=None 默认被拒")
_reset()

# ─────────────────────────────────────────────
print("\n[T4] media_probe：数据库查询失败 → status=error（≠ 未管理，P1-04）")
# ─────────────────────────────────────────────
_p1 = pdb.media_probe(plugin_id=PID, server_id="A", item_id="aa")
check(_p1.get("status") == "ok" and _p1.get("managed") is True, "正常探测 → status=ok / managed=True")
_p2 = pdb.media_probe(plugin_id=PID, server_id="A", item_id="nope")
check(_p2.get("status") == "ok" and _p2.get("managed") is False, "正常未命中 → status=ok / managed=False")
_orig_q1 = dbm._q1


def _boom(*a, **k):
    raise RuntimeError("db down")


dbm._q1 = _boom
try:
    _p3 = pdb.media_probe(plugin_id=PID, server_id="A", emby_item_id="aa")
finally:
    dbm._q1 = _orig_q1
check(_p3.get("status") == "error" and _p3.get("managed") is False,
      f"数据库异常 → status=error（不得伪装成未管理），实际 {_p3}")
dbm._q1 = _boom
try:
    _cm = pdb.count_missing(plugin_id=PID)
finally:
    dbm._q1 = _orig_q1
check(_cm == -1, f"count_missing 查询失败 → -1，实际 {_cm}")

# ─────────────────────────────────────────────
print("\n[T5] _cleanup_dirty_webhook_events：探测 error 时保留事件（P1-04 D）")
# ─────────────────────────────────────────────


class _ProbeDb:
    def __init__(self, res):
        self._res = res

    def media_probe(self, **kw):
        return self._res


class _CleanF:
    _cleanup_dirty_webhook_events = _NS["_cleanup_dirty_webhook_events"]

    def __init__(self, res):
        self._people_db = _ProbeDb(res)
        self._webhook_events = [{"status": "missing", "item_id": "9", "name": "某剧",
                                 "series_name": "某剧", "server_id": "A"}]

    def _save_state(self):
        pass


_o = _CleanF({"managed": False, "match_type": "error", "status": "error"})
_r5 = _o._cleanup_dirty_webhook_events()
check(_r5.get("removed_count") == 0 and _r5.get("kept_error_count") == 1
      and bool(_r5.get("success")) and len(_o._webhook_events) == 1,
      f"探测 error → 保留事件并计数 kept_error_count（实际 {_r5}）")
_o = _CleanF({"managed": True, "match_type": "emby_item_id", "status": "ok"})
_r5 = _o._cleanup_dirty_webhook_events()
check(_r5.get("removed_count") == 0 and len(_o._webhook_events) == 1, "探测 managed → 保留")
_o = _CleanF({"managed": False, "match_type": "none", "status": "ok"})
_r5 = _o._cleanup_dirty_webhook_events()
check(_r5.get("removed_count") == 1 and bool(_r5.get("success")) and len(_o._webhook_events) == 0,
      "探测成功且未管理 → 清掉脏事件（原行为保留）")
# v4.6.99（报告 §七）：整体失败必须**明确**返回 success=False（不得显示清理成功）
_o = _CleanF({"managed": False, "match_type": "none", "status": "ok"})
_o._people_db = None
_r5 = _o._cleanup_dirty_webhook_events()
check(_r5.get("success") is False and _r5.get("error_message"), f"数据库不可用 → success=False {_r5}")
check(len(_o._webhook_events) == 1, "失败时不动事件列表")

# ─────────────────────────────────────────────
print("\n[T6] 删除链路端到端（真实 SQLite + 真实 handler）")
# ─────────────────────────────────────────────


class _FakeClient:
    def __init__(self, status, data=None, episodes=None):
        self.status, self.data, self.episodes = status, data, episodes

    def fetch_item_status(self, iid):
        return self.status, self.data

    def get_series_episodes_status(self, iid, limit=200):
        return "found", list(self.episodes or []), ""

    def get_series_episodes(self, iid):
        return self.episodes or []


class _DelPlugin:
    _resolve_unique_server_id = _NS["_resolve_unique_server_id"]
    _configured_server_keys = _NS["_configured_server_keys"]
    _reconcile_missing_episodes = _NS["_reconcile_missing_episodes"]
    _handle_webhook_delete = _NS["_handle_webhook_delete"]

    def __init__(self, db, svcs, client):
        self._people_db = db
        self._svcs = svcs
        self._client = client
        self.events = []
        self.notifies = []

    def _get_all_emby_services(self):
        return self._svcs

    def _get_server_identifier(self, svc):
        return f"{svc.name}_skey"

    def _normalize_webhook_path(self, sid, p):
        return p

    def _in_selected_library(self, p):
        return True

    def _delete_nfo_path_guess(self, p, sid):
        # 模拟真实推导：剧目录 → tvshow.nfo（供 media_probe 按 nfo_path 精确命中）
        return (str(p or "").rstrip("/") + "/tvshow.nfo") if p else ""

    def _all_nfo_roots(self):
        return []

    def _item_id_from_dir_name(self, p):
        return ""

    def _nfo_episode_meta(self, p):
        return "", "", None, None

    def _emby_client_for_server(self, sid, allow_legacy_fallback=True):
        if self._client is None:
            return None, "no-client"
        return self._client, ""

    def _push_webhook_event(self, item_id, name, status, msg, **kw):
        self.events.append({"item_id": item_id, "status": status, "msg": msg,
                            "series_name": kw.get("series_name")})

    def _enqueue_delete_notification(self, head, ep_txt="", n=0):
        self.notifies.append({"head": head, "ep_txt": ep_txt, "n": n})


def _mk_raw(path="/Media/悠哉日常大王", itype="Series", iid="32027"):
    return {"json_object": {"Event": "library.deleted",
                            "Item": {"Id": iid, "Type": itype, "Name": "悠哉日常大王",
                                     "Path": path, "IsFolder": True,
                                     "ProviderIds": {"Tmdb": "216182"}}}}


def _rows_deleted():
    _r = dbm._q("SELECT COUNT(*) c FROM person WHERE plugin_id=? "
                "AND deleted_at!='' AND deleted_at IS NOT NULL", (PID,))
    return int(_r[0]["c"])


# handler 内部用 self.__class__.__name__ 作为 plugin_id → T6 的行必须写同一个 id
PID = _DelPlugin.__name__
dbm._x("DELETE FROM person WHERE plugin_id=?", (PID,))

# A) 空库 + Series 删除 + 单台 Emby（无 ServerId）→ 完全静默
_p = _DelPlugin(pdb, [_Svc("Emby")], _FakeClient(clim.ITEM_FOUND, {"Id": "32027"}))
_p._handle_webhook_delete(_mk_raw(), "32027", "library.deleted", "")
check(len(_p.events) == 0 and len(_p.notifies) == 0, "A：空库删除陌生 Series → 无事件、无通知（完全静默）")
check(dbm._q("SELECT COUNT(*) c FROM person WHERE plugin_id=?", (PID,))[0]["c"] == 0, "A：未写库")

# A-2) v4.6.99（P1-05）：空库 + 多服务器 + 无 ServerId → 只读探测无任何候选 → 静默
_p = _DelPlugin(pdb, [_Svc("A"), _Svc("B")], _FakeClient(clim.ITEM_NOT_FOUND, None))
_p._handle_webhook_delete(_mk_raw(), "32027", "library.deleted", "")
check(len(_p.events) == 0 and len(_p.notifies) == 0,
      "A-2：空库 + 服务器未知 → 完全静默（不产生无意义的「待确认」事件）")
check(dbm._q("SELECT COUNT(*) c FROM person WHERE plugin_id=?", (PID,))[0]["c"] == 0, "A-2：未写库")

# 已管理：剧级行 + 2 集
pdb.upsert_people(plugin_id=PID, server_id="Emby_skey", item_id="32027", item_type="Series",
                  title="悠哉日常大王", series_name="", season_num=None, episode_num=None,
                  library_name="L", nfo_path=f"{_PREF}/tvshow.nfo",
                  people=[{"Type": "Actor", "before_name": "小岩井琴里", "Name": "小岩井琴里",
                           "before_role": "r", "Role": "r"}])
_ins("Emby_skey", "32027", 1, 1)
_ins("Emby_skey", "32027", 1, 2)

# B-1) 容器状态未知（超时/500）→ 不标记、不发普通删除通知
_reset()
_p = _DelPlugin(pdb, [_Svc("Emby")], _FakeClient(clim.ITEM_UNAVAILABLE, None))
_p._handle_webhook_delete(_mk_raw(), "32027", "library.deleted", "")
check(_rows_deleted() == 0, "B：Emby 状态未知 → 一行都不标记（不批量误删）")
check(len(_p.notifies) == 0, "B：状态未知 → 不发普通删除通知")
check(len(_p.events) == 1 and _p.events[0]["status"] == "ambiguous" and "无法确认" in _p.events[0]["msg"],
      "B：登记「待确认」事件（文案=删除状态无法确认）")

# B-2) 容器明确不存在（404）→ 进入观察期
_reset()
_p = _DelPlugin(pdb, [_Svc("Emby")], _FakeClient(clim.ITEM_NOT_FOUND, None))
_p._handle_webhook_delete(_mk_raw(), "32027", "library.deleted", "")
check(_rows_deleted() == 3, f"B：明确不存在 → 进入观察期（剧级+2集=3 行），实际 {_rows_deleted()}")
check(len(_p.events) == 1 and _p.events[0]["status"] == "missing", "B：登记 missing 事件")
check(len(_p.notifies) == 1 and _p.notifies[0]["n"] == 3, "B：发出删除通知且行数与实际一致")

# B-3) 容器仍在（只少了 1 集）→ 只标消失的那一集
_reset()
_p = _DelPlugin(pdb, [_Svc("Emby")],
                _FakeClient(clim.ITEM_FOUND, {"Id": "32027"},
                            episodes=[{"ParentIndexNumber": 1, "IndexNumber": 1}]))
_p._handle_webhook_delete(_mk_raw(), "32027", "library.deleted", "")
check(_rows_deleted() == 1, f"B：容器仍在 → 只标真消失的 1 集，实际 {_rows_deleted()}")
_ep2 = dbm._q("SELECT deleted_at FROM person WHERE plugin_id=? AND server_id='Emby_skey' "
              "AND season_num=1 AND episode_num=2", (PID,))
check(str(_ep2[0]["deleted_at"] or "") != "", "B：确实是「E2」被标（差集正确）")

# C) 多服务器 + 无 ServerId → 不写库
_reset()
_p = _DelPlugin(pdb, [_Svc("A"), _Svc("B")], _FakeClient(clim.ITEM_NOT_FOUND, None))
_p._handle_webhook_delete(_mk_raw(), "32027", "library.deleted", "")
check(_rows_deleted() == 0, "C：多台 Emby 缺 ServerId → 不修改任何记录")
check(len(_p.notifies) == 0, "C：不跨服务器、不发普通删除通知")
check(len(_p.events) == 1 and _p.events[0]["status"] == "ambiguous", "C：登记待确认事件")

# D) media_probe 报错 → 不改记录、不发普通删除通知
_reset()
dbm._q1 = _boom
try:
    _p = _DelPlugin(pdb, [_Svc("Emby")], _FakeClient(clim.ITEM_NOT_FOUND, None))
    _p._handle_webhook_delete(_mk_raw(), "32027", "library.deleted", "")
finally:
    dbm._q1 = _orig_q1
check(_rows_deleted() == 0, "D：探测报错 → 一行都不标记")
check(len(_p.notifies) == 0, "D：探测报错 → 不发普通删除通知")
check(len(_p.events) == 1 and _p.events[0]["status"] == "ambiguous", "D：登记待确认事件")
_reset()

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)