# -*- coding: utf-8 -*-
"""v4.6.113 回归测试：第三方审查报告（v4.6.112）P1-01 ~ P1-04 + P2 五项。

运行：python tests/test_v4113_review_p1_p2.py

覆盖（对齐报告第六节 6 条验收标准）：
  1 Emby HTTP 200 + {} → 查询不可信（不误标整季）
  2 人物重命名：读取/完整保存失败 → 不回退稀疏 DTO；ID 三态判定
  3 任务配置快照：运行中不被覆盖 + 持久化 + 重启恢复逐个任务
  4 多服务器 legacy 空来源记录隔离（探测/读取范围与写入一致）
  5 数据库读取失败不得伪装成「无待翻」（错误标记 + 上报）
  6 多个强制重翻任务重启恢复：各自 job_id / 范围 / 条目
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
TMP = Path(tempfile.mkdtemp(prefix="epl113_"))
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

_spec = importlib.util.spec_from_file_location("epl_db113", PLUGIN_DIR / "db.py")
dbm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dbm)
_cs = importlib.util.spec_from_file_location("epl_cli113", PLUGIN_DIR / "emby_client.py")
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


def _code(text):
    """去掉整行注释（避免说明性注释里的旧写法被误判）。"""
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))


print("=" * 72)
print("v4.6.113 回归测试（审查报告 P1-01~04 + P2：响应校验 / 改名安全 / 快照 / DB 错误态 / legacy / Folder）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] Emby 响应严格校验：HTTP 200 + {} 不当作可信空结果")
# ─────────────────────────────────────────────


class _Resp:
    def __init__(self, code, payload=None, bad=False):
        self.status_code, self._p, self._bad = code, payload, bad

    def json(self):
        if self._bad:
            raise ValueError("not json")
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


_ok, _items, _total, _why = clim.EmbyClient._parse_items_page({})
check(_ok is False and _why == "items_missing_or_not_list",
      "{} → 结构非法（Items 缺失）")
_ok, _items, _total, _why = clim.EmbyClient._parse_items_page({"Items": []})
check(_ok is False and _why == "total_missing", "缺 TotalRecordCount → 结构非法")
_ok, _items, _total, _why = clim.EmbyClient._parse_items_page({"Items": [], "TotalRecordCount": "x"})
check(_ok is False and _why == "total_not_number", "TotalRecordCount 非数值 → 结构非法")
_ok, _items, _total, _why = clim.EmbyClient._parse_items_page({"Items": [1], "TotalRecordCount": 1})
check(_ok is True and _total == 1, "合法响应 → ok")

# 剧集枚举：HTTP 200 + {}
check(_mk([_Resp(200, {})]).get_series_episodes_status("1")[0] == clim.ITEM_UNAVAILABLE,
      "get_series_episodes_status：200 + {} → UNAVAILABLE（不当作空剧集）")
# 通用查询：HTTP 200 + {}
check(_mk([_Resp(200, {})]).query_items_status({})[0] == clim.ITEM_UNAVAILABLE,
      "query_items_status：200 + {} → UNAVAILABLE（不当作空列表）")
# 总数=0 却有条目（自相矛盾）
check(_mk([_Resp(200, {"Items": [{"Id": "1"}], "TotalRecordCount": 0})]).get_series_episodes_status("1")[0]
      == clim.ITEM_UNAVAILABLE, "总数=0 却有 Items → UNAVAILABLE（自相矛盾）")
# 合法空
check(_mk([_Resp(200, {"Items": [], "TotalRecordCount": 0})]).get_series_episodes_status("1")
      == (clim.ITEM_FOUND, [], ""), "总数一致的空结果 → FOUND（真空）")

# ─────────────────────────────────────────────
print("\n[T2] 人物重命名：不回退稀疏 DTO；人物 ID 三态")
# ─────────────────────────────────────────────
_rp = _grab_method(_CLI, "rename_person")
_rpc = _code(_rp)
check('"Type": "Person"' not in _rpc and '"Id": pid, "Name": nn' not in _rpc,
      "rename_person 不再构造稀疏 DTO（Id/Name/Type/ProviderIds）")
check(_rpc.count("self._post(") == 1, "rename_person 只有一次完整对象回写（无二次兜底提交）")
check('未取得完整 DTO' in _rp, "读取完整 DTO 失败 → 明确中止并记日志")

# 行为级：完整详情取不到 → False 且不提交任何 POST
_c = clim.EmbyClient("http://x", "k")
_c.get_person_detail = lambda pid: None
_posts = []
_c._post = lambda path, data=None: (_posts.append((path, data)), True)[1]
check(_c.rename_person("P1", "新名") is False and _posts == [],
      "完整 DTO 取不到 → 返回 False 且不提交稀疏对象")
# 行为级：完整详情可用 → 整份回写并保留其它字段
_detail = {"Id": "P1", "Name": "旧名", "Overview": "简介", "LockedFields": ["Name"]}
_c2 = clim.EmbyClient("http://x", "k")
_c2.get_person_detail = lambda pid: dict(_detail)
_posts2 = []
_c2._post = lambda path, data=None: (_posts2.append((path, data)), True)[1]
check(_c2.rename_person("P1", "新名") is True, "完整 DTO 可用 → 改名成功")
check(bool(_posts2) and _posts2[0][1].get("Name") == "新名"
      and _posts2[0][1].get("Overview") == "简介",
      "整份回写：Name 覆盖，其它元数据保留")

# 三态
check(_mk([_Resp(404, {})]).get_person_status("P1")[0] == clim.ITEM_NOT_FOUND, "get_person_status：404 → NOT_FOUND")
check(_mk([_Resp(500, {})]).get_person_status("P1")[0] == clim.ITEM_UNAVAILABLE, "get_person_status：500 → UNAVAILABLE")
check(_mk([_Resp(200, {"Id": "P1", "Name": "n"})]).get_person_status("P1")[0] == clim.ITEM_FOUND,
      "get_person_status：200 + Id → FOUND")
check(_mk([_Resp(200, {"Name": "n"})]).get_person_status("P1")[0] == clim.ITEM_UNAVAILABLE,
      "get_person_status：200 但无有效 Id → UNAVAILABLE（不当作已删除）")

# _pool_sync_one_row 只在 NOT_FOUND 才按名字回退
_nsP = {"logger": logger,
        "ITEM_FOUND": clim.ITEM_FOUND, "ITEM_NOT_FOUND": clim.ITEM_NOT_FOUND,
        "ITEM_UNAVAILABLE": clim.ITEM_UNAVAILABLE,
        "pool_target_name": lambda r: str(r.get("name_zh") or "")}
exec(_grab_method(_SRC, "_pool_sync_one_row"), _nsP)


class _CliP:
    def __init__(self, status):
        self.status = status
        self.fallback_called = False

    def rename_person(self, pid, target, provider_ids=None):
        return False

    def get_person_status(self, pid):
        return self.status, None, "why"


class _PoolSelf:
    _pool_sync_one_row = _nsP["_pool_sync_one_row"]

    def __init__(self):
        self.logged = []

    def _warn_once(self, key, msg):
        self.logged.append((key, msg))

    def _resolve_rename_by_name(self, cli, *, name_original, target, tag):
        return {"ok": True, "reason": "fallback", "person_id": "F1"}


_o = _PoolSelf()
_r = _o._pool_sync_one_row(_CliP(clim.ITEM_FOUND), person_id="P1",
                           name_original="A", name_zh="甲")
check(_r.get("ok") is False and "仍有效" in str(_r.get("reason")),
      f"ID 仍有效（FOUND）→ 记失败、不按名字回退：{_r.get('reason')}")
_o = _PoolSelf()
_r = _o._pool_sync_one_row(_CliP(clim.ITEM_UNAVAILABLE), person_id="P1",
                           name_original="A", name_zh="甲")
check(_r.get("ok") is False and "无法确认" in str(_r.get("reason")),
      f"查询失败（UNAVAILABLE）→ 停止自动改名、不按名字回退：{_r.get('reason')}")
_r = _PoolSelf()._pool_sync_one_row(_CliP(clim.ITEM_NOT_FOUND), person_id="P1",
                                    name_original="A", name_zh="甲")
check(_r.get("reason") == "fallback", "明确不存在（NOT_FOUND）→ 才允许按名字回退")

# ─────────────────────────────────────────────
print("\n[T3] 任务配置快照：运行中不覆盖 + 持久化 + 恢复逐个任务")
# ─────────────────────────────────────────────
_scope_fn = _grab_method(_SRC, "_tx_scope")
_scope_ns = {"logger": logger}
exec(_scope_fn, _scope_ns)
_batch_ns = {"logger": logger}
exec(_grab_method(_SRC, "_tx_batching_mode"), _batch_ns)


class _SnapSelf:
    _tx_scope = _scope_ns["_tx_scope"]
    _tx_batching_mode = _batch_ns["_tx_batching_mode"]

    def __init__(self, snap, live_scope="both", live_batch="per_title"):
        self._tx_cfg_snapshot = snap
        self._tx_target_scope = live_scope
        self._translate_batching = live_batch


check(_SnapSelf({"scope": "person"}, live_scope="both")._tx_scope() == "person",
      "_tx_scope：有快照 → 用快照范围（忽略实时）")
check(_SnapSelf(None, live_scope="role")._tx_scope() == "role", "_tx_scope：无快照 → 用实时范围")
check(_SnapSelf({"batching": "global"}, live_batch="per_title")._tx_batching_mode() == "global",
      "_tx_batching_mode：有快照 → 用快照分批模式")
check("_batching = self._tx_batching_mode()" in _SRC, "翻译轮次分批模式改读快照（_tx_batching_mode）")

# _tx_request_consume：运行中不覆盖快照
_nsRC = {"logger": logger, "time": __import__("time"), "json": __import__("json"),
         "List": List, "Optional": Optional, "Dict": Dict, "Any": Any}
exec(_grab_method(_SRC, "_tx_build_cfg_snapshot"), _nsRC)
exec(_grab_method(_SRC, "_tx_enqueue_request"), _nsRC)
exec(_grab_method(_SRC, "_tx_request_consume"), _nsRC)


class _JobDbF:
    def __init__(self):
        self.created = []

    def create(self, **kw):
        self.created.append(kw)
        return True


class _RCSelf:
    _tx_build_cfg_snapshot = _nsRC["_tx_build_cfg_snapshot"]
    _tx_enqueue_request = _nsRC["_tx_enqueue_request"]
    _tx_request_consume = _nsRC["_tx_request_consume"]

    def __init__(self, snap, requested, job_id=""):
        self._tx_cfg_snapshot = snap
        self._tx_requested = requested
        self._tx_source = ""
        self._tx_target_scope = "both"
        self._tx_scope_items = set()
        self._tx_only_terms = set()
        self._tx_job_id = job_id
        self._tx_job_db_obj = _JobDbF()
        self._tx_wait_jobs = None
        self._tx_batch = 0
        self._translate_batching = "per_title"

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
        return self._tx_job_db_obj


_snap_old = {"version": 2, "scope": "person", "batching": "global", "limits": {"actor": 3}}
_s = _RCSelf(_snap_old, requested=True, job_id="J-OLD")
_s._tx_request_consume(source="library", scope="role")
check(_s._tx_cfg_snapshot is _snap_old and _s._tx_cfg_snapshot.get("scope") == "person",
      "运行中并发请求**不覆盖**当前任务快照（范围仍冻结为 person）")
# v4.6.116（P1-08）：运行中到达的新请求不再合并进当前 Job 的全局字段，而是独立入队
check(_s._tx_target_scope == "both" and not _s._tx_scope_items,
      "运行中并发请求**不改**当前 Job 的实时范围/条目（开始后不可变）")
check(len(_s._tx_wait_jobs or []) == 1 and _s._tx_wait_jobs[0]["scope"] == "role"
      and _s._tx_wait_jobs[0]["source"] == "library",
      "新请求独立入队（各自 source/scope，待当前任务结束后启动）")
check(_s._tx_wait_jobs[0]["job_id"] and bool(_s._tx_job_db_obj.created),
      "排队任务有自己的 job_id 与持久化记录（status=queued）")
_s2 = _RCSelf(None, requested=False)
_s2._tx_request_consume(source="library", scope="role")
check(isinstance(_s2._tx_cfg_snapshot, dict) and _s2._tx_cfg_snapshot.get("scope") == "role",
      "新任务（无快照）→ 重建快照（scope=role）")
check(bool(_s2._tx_job_db_obj.created)
      and bool(_s2._tx_job_db_obj.created[0].get("cfg_snapshot")),
      "新建 Job 时把完整配置快照写入 translate_jobs.cfg_snapshot")

# 行为级：TranslateJobDb 持久化 cfg_snapshot
_jdb = dbm.TranslateJobDb()
_jdb.create(plugin_id="EPL113", job_id="J-PERSIST", job_type="force", scope="person",
            payload='{"i1":{}}', cfg_snapshot='{"scope":"person","batching":"global"}')
_row = _jdb.get(plugin_id="EPL113", job_id="J-PERSIST")
check(bool(_row) and 'global' in str(_row.get("cfg_snapshot") or ""),
      "cfg_snapshot 列已持久化并可读回（重启恢复用）")
check("cfg_snapshot" in _DB and '("cfg_snapshot", "TEXT DEFAULT \'\'")' in _DB,
      "db.py 迁移补 cfg_snapshot 列（v13）")

# 行为级：_tx_job_recover 逐个恢复
_nsPump = {"logger": logger, "List": List}
exec(_grab_method(_SRC, "_tx_recover_pump"), _nsPump)
_nsRec = {"logger": logger, "json": __import__("json"), "List": List}
# v4.6.116（P2-10）：恢复入队改用 _tx_force_enqueue（复合键 job_id+item_id）
exec(_grab_method(_SRC, "_tx_force_enqueue"), _nsRec)
exec(_grab_method(_SRC, "_tx_job_recover"), _nsRec)


class _StaleDb:
    def __init__(self, rows):
        self.rows = rows

    def mark_stale(self, plugin_id=None):
        return self.rows


class _RecSelf:
    _tx_job_recover = _nsRec["_tx_job_recover"]
    _tx_force_enqueue = _nsRec["_tx_force_enqueue"]
    _tx_recover_pump = _nsPump["_tx_recover_pump"]

    def __init__(self, rows):
        self._jdb = _StaleDb(rows)
        self._tx_force_jobs = {}
        self._tx_recover_queue = None
        self._tx_requested = False
        self._tx_cfg_snapshot = None
        self.calls = []

    def _tx_job_db(self):
        return self._jdb

    def _push_log(self, *a, **k):
        pass

    def _tx_request_consume(self, **kw):
        self.calls.append(kw)


_rows = [
    {"id": "J-A", "job_type": "force", "scope": "person",
     "payload": '{"itemA": {}}', "cfg_snapshot": '{"scope":"person"}'},
    {"id": "J-B", "job_type": "force", "scope": "role",
     "payload": '{"itemB": {}}', "cfg_snapshot": '{"scope":"role"}'},
    {"id": "J-C", "job_type": "auto", "scope": "both", "payload": "{}", "cfg_snapshot": ""},
]
_rr = _RecSelf(_rows)
_rr._tx_job_recover()
check(len(_rr.calls) == 1 and _rr.calls[0]["resume_job_id"] == "J-A"
      and _rr.calls[0]["scope"] == "person" and _rr.calls[0]["items"] == ["itemA"],
      f"重启恢复：先恢复第 1 个强制任务（J-A/person/itemA），实际 {_rr.calls}")
check(len(_rr._tx_recover_queue or []) == 1, "其余强制任务留在恢复队列（未合并进第 1 个）")
_rr._tx_requested = False   # 模拟第 1 个任务结束
_rr._tx_recover_pump()
check(len(_rr.calls) == 2 and _rr.calls[1]["resume_job_id"] == "J-B"
      and _rr.calls[1]["scope"] == "role" and _rr.calls[1]["items"] == ["itemB"],
      f"第 1 个结束后恢复第 2 个强制任务（J-B/role/itemB），实际 {_rr.calls}")
check(len(_rr._tx_recover_queue or []) == 0, "全部恢复完成 → 队列清空")
check(_rr._tx_cfg_snapshot == {"scope": "role"}, "恢复第 2 个任务时沿用其配置快照")
check("_tx_recover_queue" in _SRC and "_tx_recover_pump" in _SRC,
      "恢复队列 / 泵已接入（逐个恢复，不合并任务）")

# ─────────────────────────────────────────────
print("\n[T4] 多服务器 legacy 隔离 + Folder 禁止标题弱匹配")
# ─────────────────────────────────────────────
pdb = dbm.PeopleDb()
pdb.ensure_table()
PID = "EPL113"
dbm._x("DELETE FROM person WHERE plugin_id=?", (PID,))
_pdb = pdb
_PREF = "X:/lib/Show"
# 一条属于 A 服、一条 legacy 空来源
_pdb.upsert_people(plugin_id=PID, server_id="A", item_id="xA", item_type="Episode",
                   title="T", series_name="T", season_num=1, episode_num=1,
                   nfo_path=f"{_PREF}/S01E01.nfo", people=[{"before_name": "A", "Name": "A"}])
_pdb.upsert_people(plugin_id=PID, server_id="", item_id="xL", item_type="Episode",
                   title="T", series_name="T", season_num=1, episode_num=2,
                   nfo_path=f"{_PREF}/S01E02.nfo", people=[{"before_name": "A", "Name": "A"}])

_pairs_strict = _pdb.episode_pairs_under_prefix(plugin_id=PID, path_prefix=_PREF,
                                                server_id="A", include_legacy=False)
_pairs_soft = _pdb.episode_pairs_under_prefix(plugin_id=PID, path_prefix=_PREF,
                                              server_id="A", include_legacy=True)
check(_pairs_strict == [(1, 1)] and _pairs_soft == [(1, 1), (1, 2)],
      f"episode_pairs_under_prefix：多服务器(include_legacy=False) 只含本服 {_pairs_strict}；含 legacy {_pairs_soft}")

_p_strict = _pdb.media_probe(plugin_id=PID, server_id="A", item_id="xL", include_legacy=False)
_p_soft = _pdb.media_probe(plugin_id=PID, server_id="A", item_id="xL", include_legacy=True)
check(_p_strict.get("managed") is False, "media_probe：多服务器不认领 legacy 空来源行")
check(_p_soft.get("managed") is True and _p_soft.get("match_type") == "item_id",
      "media_probe：单服务器（include_legacy=True）可命中 legacy")

# Folder：禁止仅凭标题弱匹配
_pdb.upsert_people(plugin_id=PID, server_id="A", item_id="fold1", item_type="Folder",
                   title="我的文件夹", series_name="",
                   nfo_path="X:/lib/我的文件夹/folder.nfo",
                   people=[{"before_name": "A", "Name": "A"}])
_wc_off, _wa_off = dbm._weak_sql(title="我的文件夹", allow_title_only=False)
check(_wc_off == "" and _wa_off == [], "_weak_sql：allow_title_only=False 时不产生纯标题条件")
check(_pdb.media_probe(plugin_id=PID, server_id="A", title="我的文件夹",
                       is_folder=False).get("managed") is True,
      "（对照）非 Folder：标题弱匹配可命中（managed=True）")
_pf = _pdb.media_probe(plugin_id=PID, server_id="A", title="我的文件夹", is_folder=True)
check(_pf.get("managed") is False, "media_probe：Folder 仅标题命中 → 不认领（managed=False）")

# DB 错误态：episode_pairs_under_prefix 查询失败 → None（≠ 空列表）
_orig_q = dbm._q


def _boom_q(*a, **k):
    raise RuntimeError("db boom")


dbm._q = _boom_q
try:
    _none = _pdb.episode_pairs_under_prefix(plugin_id=PID, path_prefix=_PREF, server_id="A")
finally:
    dbm._q = _orig_q
check(_none is None, "episode_pairs_under_prefix：DB 查询失败返回 None（调用方可区分「出错」与「无记录」）")
check("include_legacy: bool = True" in _DB.split("def episode_pairs_under_prefix")[1][:400],
      "episode_pairs_under_prefix 支持 include_legacy")

# _reconcile_missing_episodes：DB 错误 → 不可信（db_error，绝不 no_db_rows）
_nsRR = {"logger": logger, "ITEM_FOUND": clim.ITEM_FOUND, "ITEM_NOT_FOUND": clim.ITEM_NOT_FOUND,
         "ITEM_UNAVAILABLE": clim.ITEM_UNAVAILABLE, "List": List}
exec(_grab_method(_SRC, "_reconcile_missing_episodes"), _nsRR)


class _DbErrPairs:
    def episode_pairs_under_prefix(self, **kw):
        return None


class _RR:
    _reconcile_missing_episodes = _nsRR["_reconcile_missing_episodes"]

    def __init__(self, db):
        self._people_db = db


class _CliAny:
    def get_series_episodes_status(self, iid, limit=200):
        return "found", [], ""

    def query_items_status(self, params=None):
        return "found", {"Items": [], "TotalRecordCount": 0}, ""


_r = _RR(_DbErrPairs())._reconcile_missing_episodes(_CliAny(), "9", _PREF, "A", "series")
check(_r == ([], False, "db_error"), f"DB 读取失败 → 不可信 db_error（不当作 no_db_rows），实际 {_r}")

# Season 分页：>500 集也要翻页取全（单页实现会误判不完整）
class _PageCli:
    def __init__(self, total):
        self.total = total

    def query_items_status(self, params=None):
        _s = int((params or {}).get("StartIndex") or 0)
        _l = int((params or {}).get("Limit") or 500)
        _n = max(0, min(_l, self.total - _s))
        return "found", {"Items": [{"ParentIndexNumber": 1, "IndexNumber": _s + i + 1}
                                   for i in range(_n)],
                         "TotalRecordCount": self.total}, ""


_RID = _RR.__name__   # _reconcile 内部用 self.__class__.__name__ 作为 plugin_id
dbm._x("DELETE FROM person WHERE plugin_id=?", (_RID,))
_PS = "X:/lib/Big/Season 1"
for _e in (1, 2, 3):
    _pdb.upsert_people(plugin_id=_RID, server_id="A", item_id="tv:99", item_type="Episode",
                       title="B", series_name="B", season_num=1, episode_num=_e,
                       nfo_path=f"{_PS}/S01E{_e:02d}.nfo", people=[{"before_name": "A", "Name": "A"}])
_miss, _ok, _why = _RR(_pdb)._reconcile_missing_episodes(_PageCli(1200), "99", _PS, "A", "season")
check(_ok is True and _why == "" and _miss == [],
      f"Season 分页取全 1200 集 → 可信空差集（单页实现会误判），实际 ok={_ok} miss={_miss} why={_why}")

# ─────────────────────────────────────────────
print("\n[T5] 数据库读取失败不得伪装成「无待翻」")
# ─────────────────────────────────────────────
check('"error": str(e)' in _DB, "pending_terms_full / force_item_occurrences 失败返回 error 标记")
check("pending_terms_full 查询失败" in _DB and "不当作无待翻" in _DB, "DB 层明确日志：查询失败 ≠ 无待翻")
check('_out["error"] = _db_err' in _SRC, "_tx_pending_snapshot：DB 错误上报 error（供 UI/日志显示）")

_nsOcc = {"logger": logger, "List": List, "Optional": Optional, "Dict": Dict, "Any": Any}
exec(_grab_method(_SRC, "_tx_occurrences"), _nsOcc)


class _DbErrOcc:
    def pending_terms_full(self, **kw):
        return {"names": [], "roles": [], "error": "boom"}


class _OccSelf:
    _tx_occurrences = _nsOcc["_tx_occurrences"]

    def __init__(self, db):
        self._people_db = db

    def _tx_limits_by_level(self):
        return {"movie": {}, "tvshow": {}, "episode": {}}

    def _tx_exclude_episodes(self):
        return False

    @staticmethod
    def _tx_occ_id(o):
        return "x"


_os = _OccSelf(_DbErrOcc())
_occ = _os._tx_occurrences("P")
check(_occ == [] and getattr(_os, "_tx_occ_err", "") == "boom",
      "DB 错误 → _tx_occurrences 返回空但登记错误标记（非「无可翻条目」）")
check('"error": str(getattr(self, "_tx_occ_err", "") or "")' in _SRC
      and 'if _q.get("error")' in _grab_method(_SRC, "_translate_pending_round"),
      "候选队列携带 error 标记；翻译轮次遇错跳过收词（不误报空轮）")

# ─────────────────────────────────────────────
print("\n[T6] 源码级守护：三态常量 / 旧退化写法已移除")
# ─────────────────────────────────────────────
_rr_body = _code(_grab_method(_SRC, "_reconcile_missing_episodes"))
check("season_incomplete_" not in _rr_body, "Season 单页「总数>返回即不完整」旧写法已移除（改分页循环）")
check("while True:" in _rr_body and '"StartIndex": _start' in _rr_body, "Season 查询已补分页循环")
check("if db_pairs is None:" in _rr_body, "DB 查询失败（None）单独处理，不落入 no_db_rows")
_rp_body = _code(_grab_method(_CLI, "rename_person"))
check("body = {" not in _rp_body and 'ProviderIds": provider_ids' not in _rp_body,
      "rename_person 不再有稀疏 DTO 回退分支")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
