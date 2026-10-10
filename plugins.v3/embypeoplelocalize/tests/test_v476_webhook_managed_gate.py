# -*- coding: utf-8 -*-
"""v4.6.76 回归测试：Webhook 删除事件「插件管理身份」门禁（规范 §一~§四 / §二十三 / §26 A~E）。

运行：python tests/test_v476_webhook_managed_gate.py

核心原则：**Webhook 删除事件 ≠ 插件管理记录** —— 只有插件真正管理过的媒体，
删除时才进入 managed → missing → observation 生命周期；未管理媒体完全静默。

覆盖：
  T1 测试 A：空库 + 删除未知 Series → 静默（不建事件 / 不通知 / 不写库）
  T2 测试 B：库有 12 集记录 + 整剧删除 → 命中 12 条 + 1 条 missing 事件 + 1 条聚合通知
  T3 测试 C：空库 + 删除普通 Folder → 完全静默
  T4 测试 D：有记录但删除路径不同 → 用 provider / item 稳定身份兜底标记观察期
  T5 测试 E：多候选（弱匹配）→ ambiguous，不自动观察期、不发普通删除通知
  T6 多服务器：A 服删除不标 B 服记录
  T7 手动清理 0 条 → 「无需清理」，且不清 role_memory / 媒体别名
  T8 通知文案：不再出现「同 ID 新版本」（改为稳定身份恢复说明）
  T9 任务锁补齐：5 个高风险 API 均过 _task_busy_msg；忙碌口径含统一数据变更锁
  T10 Job Snapshot：任务创建时冻结配置；运行中改设置不影响当前任务
  T11 脏事件清理：数据库无对应记录的 missing 事件被移除，有记录的保留
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
TMP = Path(tempfile.mkdtemp(prefix="epl76_"))
S1 = "___1_192_168_2_15_8096"
S2 = "___2_192_168_2_16_8096"

class _Logger:
    def __init__(self):
        self.debugs = []
        self.warnings = []
        self.infos = []
    def debug(self, msg, *a, **k):
        self.debugs.append(str(msg))
    def info(self, msg, *a, **k):
        self.infos.append(str(msg))
    def warning(self, msg, *a, **k):
        self.warnings.append(str(msg))
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

_spec = importlib.util.spec_from_file_location("epl_db76", PLUGIN_DIR / "db.py")
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

pdb = dbm.PeopleDb()
pdb.ensure_table()
PID = "EPL76P"   # = 合成类名（_pid 取 self.__class__.__name__）

def _mk_plugin_cls(extra_methods):
    ns = {
        "logger": logger, "re": re, "os": os, "time": __import__("time"),
        "Any": Any, "List": List, "Optional": Optional, "Dict": Dict,
        "tuple": tuple, "set": set, "int": int, "str": str, "bool": bool,
        "len": len, "max": max, "min": min, "sorted": sorted,
        "list": list, "dict": dict, "Exception": Exception,
        "split_media_id": dbm.split_media_id,
        "NotificationType": type("NT", (), {"Manual": "Manual"}),
        # v4.6.98：删除链路新增「条目存在性三态」常量（与 emby_client 同名同值）
        "ITEM_FOUND": "found", "ITEM_NOT_FOUND": "not_found", "ITEM_UNAVAILABLE": "unavailable",
    }
    methods = ["_handle_webhook_delete", "_push_webhook_event",
               "_cleanup_dirty_webhook_events",
               # v4.6.98：删除处理现在会先做「唯一服务器归属」判定与容器差集比对
               "_resolve_unique_server_id", "_reconcile_missing_episodes",
               # v4.6.99：服务器身份改为「白名单校验」——需要 _configured_server_keys
               "_configured_server_keys"] + extra_methods
    src = "class EPL76P:\n" + "\n".join(_grab(n) for n in methods)
    exec(compile(src, "<extract:__init__.py>", "exec"), ns)
    return ns["EPL76P"]

EP = _mk_plugin_cls([])

def _mk_plugin(del_paths=None, roots=None, container_status="not_found", episodes=None):
    """构造一个可跑 _handle_webhook_delete 的插件实例（真实删除处理逻辑 + 桩掉外围）。

    v4.6.98：容器存在性改为**三态**（fetch_item_status）——
    container_status 默认 "not_found"（Emby 明确回答不存在）→ 与旧用例「整剧删除」语义一致；
    传 "unavailable" 可验证「查询失败绝不按真删除处理」。
    """
    p = EP()
    p._people_db = pdb
    p._webhook_events = []
    p._nfo_dead_grace_hours = 24
    p._notify_on_complete = True
    p._deleted_notifies = []
    p._saved = {"n": 0}

    class _Cli:
        def fetch_item_status(self, iid):
            return container_status, ({"Id": iid} if container_status == "found" else None)

        def get_series_episodes_status(self, iid, limit=200):
            return "found", list(episodes or []), ""

        def get_series_episodes(self, iid):
            return episodes or []

    p._emby_client_for_server = lambda sid, allow_legacy_fallback=True: (_Cli(), "")
    # v4.6.99（P1-02）：服务器身份白名单 —— 本用例事件带 S1，故 S1 必须是「已配置」的 skey
    p._get_all_emby_services = lambda: [type("S", (), {"name": "Emby"})()]
    p._get_server_identifier = lambda svc: S1
    # 外围桩：路径归一 / 选库判定 / nfo 路径推断 / 剧集元数据 / 根目录 / 通知聚合
    p._normalize_webhook_path = lambda sid, raw: str(raw or "").replace("\\", "/")
    p._in_selected_library = lambda pre: bool(del_paths is None or (del_paths and pre and pre.startswith(del_paths)))
    p._all_nfo_roots = lambda: (roots or [])
    p._delete_nfo_path_guess = lambda raw, sid: (str(raw or "").rstrip("/") + "/tvshow.nfo") if raw else ""
    p._nfo_episode_meta = lambda nf: ("", "", None, None)
    p._item_id_from_dir_name = lambda path: ""
    p._save_state = lambda: p._saved.__setitem__("n", p._saved["n"] + 1)
    p._enqueue_delete_notification = lambda head, ep_txt, n: p._deleted_notifies.append(
        {"head": head, "ep": ep_txt, "n": n})
    return p

def _del_event(item_id, name, itype, path, providers=None, series=None, season=None, episode=None):
    item = {"Name": name, "Type": itype, "Path": path}
    if series:
        item["SeriesName"] = series
    if season is not None:
        item["ParentIndexNumber"] = season
    if episode is not None:
        item["IndexNumber"] = episode
    if providers:
        item["ProviderIds"] = providers
    return {"json_object": {"Item": item}}

def _seed_series(item_id="tmdb:296101", server=S1, n=12, name="Grow Up Show", prefix="X:/video/测试/GrowUp"):
    for _e in range(1, n + 1):
        pdb.upsert_people(plugin_id=PID, server_id=server, item_id=item_id, item_type="Episode",
                          title=name, series_name=name, season_num=1, episode_num=_e,
                          nfo_path=f"{prefix}/S01E{_e:02d}.nfo", emby_item_id=f"E{_e}",
                          series_media_id=item_id,
                          people=[{"before_name": "Actor A", "Name": "演员A", "before_role": "Alpha", "Role": "阿尔法"}])
    pdb.upsert_people(plugin_id=PID, server_id=server, item_id=item_id, item_type="Series",
                      title=name, series_name=name, season_num=None, episode_num=None,
                      nfo_path=f"{prefix}/tvshow.nfo", emby_item_id="SER1", series_media_id=item_id,
                      people=[{"before_name": "Actor A", "Name": "演员A", "before_role": "Alpha", "Role": "阿尔法"}])

_N = [0, 0]
def check(cond, msg):
    _N[0] += 1
    if cond:
        print(f"  [PASS] {msg}")
    else:
        _N[1] += 1
        print(f"  [FAIL] {msg}")

print("=" * 72)
print("v4.6.76 回归测试（Webhook 删除事件「插件管理身份」门禁）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] 测试 A：空库 + 删除未知 Series → 完全静默（P0）")
# ─────────────────────────────────────────────
p = _mk_plugin(del_paths="/video/影视资源/测试")
p._handle_webhook_delete(
    _del_event("31998", "Grow Up Show ～向日葵马戏团～ (2026)", "Series",
               "/video/影视资源/测试/Grow Up Show ～向日葵马戏团～ (2026) {tmdb=296101}",
               providers={"Tmdb": "296101"}),
    "31998", server_id=S1)
check(p._webhook_events == [], "不创建 missing 事件（事件列表为空）")
check(p._deleted_notifies == [], "不进入删除通知聚合队列（不发 QQ）")
check(p._saved["n"] == 0, "不写数据库 / 不保存状态")
check(any("DELETE ignored" in d for d in logger.debugs), "仅 DEBUG 日志：plugin has no managed record")
check("已删除" not in " ".join(logger.infos), "无任何「已删除/观察期」INFO 日志")

# ─────────────────────────────────────────────
print("\n[T2] 测试 B：库有 12 集记录 + 整剧删除 → 观察期 + 1 条事件 + 1 条通知")
# ─────────────────────────────────────────────
_seed_series()
p2 = _mk_plugin(del_paths="X:/video/测试")
p2._handle_webhook_delete(
    _del_event("31998", "Grow Up Show", "Series",
               "X:/video/测试/GrowUp", providers={"Tmdb": "296101"}),
    "31998", server_id=S1)
check(len(p2._webhook_events) == 1 and p2._webhook_events[0]["status"] == "missing",
      f"登记 1 条 missing 事件（实际 {len(p2._webhook_events)}）")
check(len(p2._deleted_notifies) == 1, "聚合通知入队 1 条")
_m = dbm._q1("SELECT COUNT(*) c FROM person WHERE plugin_id=? AND item_id='tmdb:296101' "
             "AND deleted_at!='' AND deleted_at IS NOT NULL", (PID,))
check(int((_m or {}).get("c") or 0) == 13, f"13 行（12 集 + 剧级）全部进入观察期（实际 {(_m or {}).get('c')}）")
check(any("DELETE managed" in i for i in logger.infos), "INFO 日志：DELETE managed: match=... matched_rows=13")
check(p2._deleted_notifies[0]["n"] == 13, "通知记录实际进入观察期 13 条")

# ─────────────────────────────────────────────
print("\n[T2b] v4.6.98：容器状态未知（查询失败/超时/500）→ 绝不按真删除处理")
# ─────────────────────────────────────────────
# 先解除 T2 标记的 13 行，确保断言「一行都没标」
dbm._x("UPDATE person SET deleted_at='' WHERE plugin_id=? AND item_id='tmdb:296101'", (PID,))
p_unk = _mk_plugin(del_paths="X:/video/测试", container_status="unavailable")
p_unk._handle_webhook_delete(
    _del_event("31998", "Grow Up Show", "Series",
               "X:/video/测试/GrowUp", providers={"Tmdb": "296101"}),
    "31998", server_id=S1)
_m_unk = dbm._q1("SELECT COUNT(*) c FROM person WHERE plugin_id=? AND item_id='tmdb:296101' "
                 "AND deleted_at!='' AND deleted_at IS NOT NULL", (PID,))
check(int((_m_unk or {}).get("c") or 0) == 0,
      f"Emby 查询失败 → 一行都不标记（不批量误删），实际 {(_m_unk or {}).get('c')}")
check(p_unk._deleted_notifies == [], "不发送普通删除通知")
check(len(p_unk._webhook_events) == 1 and p_unk._webhook_events[0]["status"] == "ambiguous"
      and "无法确认" in p_unk._webhook_events[0]["msg"],
      "登记「删除状态无法确认」待确认事件（不写「已进入观察期」）")


p3 = _mk_plugin(del_paths="/video/影视资源")
p3._handle_webhook_delete(
    _del_event("77881", "大室家", "Folder", "/video/影视资源/测试/大室家"),
    "77881", server_id=S1)
check(p3._webhook_events == [] and p3._deleted_notifies == [] and p3._saved["n"] == 0,
      "普通文件夹（未管理）删除：不建事件 / 不通知 / 不写库")

# ─────────────────────────────────────────────
print("\n[T4] 测试 D：有记录但删除路径不同 → 稳定身份兜底进入观察期")
# ─────────────────────────────────────────────
# 先种入一个「旧路径」的作品（新删除事件路径完全不同 → 只能靠 provider 命中）
for _e in (1, 2):
    pdb.upsert_people(plugin_id=PID, server_id=S1, item_id="tmdb:555001", item_type="Episode",
                      title="Remux 剧", series_name="Remux 剧", season_num=1, episode_num=_e,
                      nfo_path=f"X:/old/OLDNAME/S01E{_e:02d}.nfo", emby_item_id=f"OLDE{_e}",
                      series_media_id="tmdb:555001",
                      people=[{"before_name": "Actor B", "Name": "演员B"}])
p4 = _mk_plugin(del_paths="X:/video/new")
p4._handle_webhook_delete(
    _del_event("EMBYNEW", "Grow Up Show", "Series",
               "X:/video/new/OHMURO", providers={"Tmdb": "555001"}),
    "EMBYNEW", server_id=S1)
check(len(p4._webhook_events) == 1 and p4._webhook_events[0]["status"] == "missing",
      "路径变了但 provider 命中 → 仍进入观察期（洗版/Remux 场景）")
check(p4._deleted_notifies and p4._deleted_notifies[0]["n"] > 0,
      f"命中行数 > 0（实际 {p4._deleted_notifies and p4._deleted_notifies[0]['n']}）")

# ─────────────────────────────────────────────
print("\n[T5] 测试 E：多候选（弱匹配）→ ambiguous，不自动观察期")
# ─────────────────────────────────────────────
for _i, _name in enumerate(["同名剧", "同名剧"]):
    pdb.upsert_people(plugin_id=PID, server_id=S1, item_id=f"nfo:dup{_i}", item_type="Episode",
                      title=_name, series_name=_name, season_num=3, episode_num=1,
                      nfo_path=f"X:/dup{_i}/S03E01.nfo", emby_item_id=f"DUP{_i}",
                      people=[{"before_name": "A", "Name": "甲"}])
pdb.mark_deleted_by_nfo_path(plugin_id=PID, nfo_path="X:/dup0/S03E01.nfo", server_id=S1)
pdb.mark_deleted_by_nfo_path(plugin_id=PID, nfo_path="X:/dup1/S03E01.nfo", server_id=S1)
p5 = _mk_plugin(del_paths="X:/video/dup")
p5._handle_webhook_delete(
    _del_event("DUPX", "同名剧", "Episode", "X:/video/dup/S03E01.mkv", series="同名剧",
               season=3, episode=1),
    "DUPX", server_id=S1)
check(len(p5._webhook_events) == 1 and p5._webhook_events[0]["status"] == "ambiguous",
      f"登记「需人工确认」事件（实际 {[e.get('status') for e in p5._webhook_events]}）")
check(p5._deleted_notifies == [], "不发送普通删除通知")
check(not p5._webhook_events[0].get("seq_unused"), "")

# ─────────────────────────────────────────────
print("\n[T6] 多服务器隔离：A 服删除不标 B 服")
# ─────────────────────────────────────────────
pdb.upsert_people(plugin_id=PID, server_id=S2, item_id="tmdb:777", item_type="Series",
                  title="B剧", series_name="B剧", season_num=None, episode_num=None,
                  nfo_path="X:/b/tvshow.nfo", series_media_id="tmdb:777",
                  people=[{"before_name": "B", "Name": "乙"}])
pdb.upsert_people(plugin_id=PID, server_id=S1, item_id="tmdb:777", item_type="Series",
                  title="A剧", series_name="A剧", season_num=None, episode_num=None,
                  nfo_path="X:/a/tvshow.nfo", series_media_id="tmdb:777",
                  people=[{"before_name": "A", "Name": "甲"}])
p6 = _mk_plugin(del_paths="X:/a")
p6._handle_webhook_delete(
    _del_event("A1", "A剧", "Series", "X:/a", providers={"Tmdb": "777"}),
    "A1", server_id=S1)
_r_a = dbm._q1("SELECT deleted_at FROM person WHERE plugin_id=? AND server_id=? AND item_id='tmdb:777'",
               (PID, S1))
_r_b = dbm._q1("SELECT deleted_at FROM person WHERE plugin_id=? AND server_id=? AND item_id='tmdb:777'",
               (PID, S2))
check(str((_r_a or {}).get("deleted_at") or "") != "", "A 服记录被标记观察期")
check(str((_r_b or {}).get("deleted_at") or "") == "", "B 服同 TMDB 记录未被标记（多服务器隔离）")

# ─────────────────────────────────────────────
print("\n[T7] 手动清理：0 条 → 「无需清理」；清理不动 role_memory / 媒体别名")
# ─────────────────────────────────────────────
pdb.role_memory_put(plugin_id=PID, rows=[{"server_id": S1, "series_id": "tmdb:296101",
                                          "series_name": "Grow Up Show",
                                          "role_original": "Alpha", "role_translated": "阿尔法",
                                          "source": "llm"}])
pdb.alias_put(plugin_id=PID, server_id=S1, provider="tmdb", provider_id="296101",
              old_media_id="nfo:OLD", old_emby_item_id="OLD1", new_media_id="tmdb:296101")
_mem_before = pdb.role_memory_stats(plugin_id=PID)["total"]
_ali_before = len(pdb.alias_rows(plugin_id=PID, server_id=S1, provider="tmdb", provider_id="296101"))
_n_purged = pdb.purge_all_missing(plugin_id=PID)
check(_n_purged > 0, f"清理观察期行（{_n_purged} 行）")
check(pdb.role_memory_stats(plugin_id=PID)["total"] == _mem_before,
      "清理不删除 Role Memory（角色记忆保留）")
check(len(pdb.alias_rows(plugin_id=PID, server_id=S1, provider="tmdb", provider_id="296101")) == _ali_before,
      "清理不删除媒体身份历史（alias 保留）")
check(pdb.count_missing(plugin_id=PID) == 0, "清理后观察期计数 = 0")
check('"当前没有插件管理的失效记录，无需清理"' in _SRC,
      "0 条时返回「当前没有插件管理的失效记录，无需清理」")

# ─────────────────────────────────────────────
print("\n[T8] 通知文案：不再出现「同 ID 新版本」（改为稳定身份恢复）")
# ─────────────────────────────────────────────
check("同 ID 新版本入库自动恢复" not in _SRC,
      "代码中已无「同 ID 新版本入库自动恢复」旧文案")
check("观察期内重新入库时将自动尝试按媒体稳定身份恢复（Emby ID / TMDB / TVDB / IMDb）" in _SRC,
      "新文案：按媒体稳定身份恢复（Emby ID / TMDB / TVDB / IMDb）")
check("个**已管理**条目" in _SRC, "聚合通知标注「已管理条目」（不再把未知删除算进去）")

# ─────────────────────────────────────────────
print("\n[T9] 任务锁补齐（规范 §十一）")
# ─────────────────────────────────────────────
for _api in ["_api_name_map_update", "_api_name_map_delete", "_api_pool_translate",
             "_api_pool_sync", "_api_pool_sync_one"]:
    _b = _grab(_api)
    check("_task_busy_msg()" in _b, f"{_api} 已接入统一任务忙碌门禁")
check("_task_state().get(\"data_mutation_locked\")" in _grab("_task_busy_msg"),
      "忙碌口径扩为统一数据变更锁（扫描/翻译/写回/池/探测任一在跑即拒绝）")

# ─────────────────────────────────────────────
print("\n[T10] Job Snapshot：运行中改设置不影响当前任务（规范 §十二/§十三）")
# ─────────────────────────────────────────────
_rc = _grab("_tx_request_consume")
# v4.6.116（P1-08）：快照构建抽为 _tx_build_cfg_snapshot，_tx_request_consume 调用它
check('self._tx_cfg_snapshot = self._tx_build_cfg_snapshot()' in _rc,
      "创建任务时冻结配置快照（person/role/types/处理单集/scope）")
check('"person"' in _grab("_tx_build_cfg_snapshot") and '"role"' in _grab("_tx_build_cfg_snapshot")
      and '"exclude_episodes"' in _grab("_tx_build_cfg_snapshot"),
      "快照字段完整（person/role/处理单集）")
check('"_tx_cfg_snapshot", None)' in _grab("_tx_eff_types") and "_tx_eff_types" in _grab("_tx_type_enabled"),
      "类型判定任务期间改用快照（_tx_eff_types）")
check('isinstance(_snap, dict) and "exclude_episodes" in _snap' in _grab("_tx_exclude_episodes"),
      "「处理单集」任务期间改用快照")
check(_SRC.count("self._tx_cfg_snapshot = None") >= 2,
      "任务结束/复位时释放快照（下个任务用最新设置）")

# ─────────────────────────────────────────────
print("\n[T11] 脏事件清理（规范 §二十三）")
# ─────────────────────────────────────────────
p7 = _mk_plugin()
p7._webhook_events = [
    # 有 DB 记录的真实失效事件（应保留）
    {"status": "missing", "item_id": "E5", "media_item_id": "tmdb:296101",
     "series_name": "Grow Up Show", "name": "Grow Up Show", "season": 1, "episode": 5,
     "server_id": S1},
    # 旧版误登记的脏事件（数据库里没有该媒体 → 应移除）
    {"status": "missing", "item_id": "99999", "media_item_id": "",
     "series_name": "从未管理的剧", "name": "从未管理的剧", "season": None, "episode": None,
     "server_id": S1},
    {"status": "done", "item_id": "1", "name": "正常入库事件"},
]
# 先恢复被清掉的记录（T7 清理过）→ 重新入库 1 集，保证 probe 能命中
pdb.upsert_people(plugin_id=PID, server_id=S1, item_id="tmdb:296101", item_type="Episode",
                  title="Grow Up Show", series_name="Grow Up Show", season_num=1, episode_num=5,
                  nfo_path="X:/video/测试/GrowUp/S01E05.nfo", emby_item_id="E5",
                  series_media_id="tmdb:296101",
                  people=[{"before_name": "Actor A", "Name": "演员A"}])
# v4.6.99：清理接口改为结构化返回 → 取 removed_count
_cl = p7._cleanup_dirty_webhook_events() or {}
_n_dirty = int(_cl.get("removed_count") or 0)
check(_n_dirty == 1 and bool(_cl.get("success", True)), f"清理 1 条脏事件（实际 {_n_dirty}）")
_left = [e.get("status") for e in p7._webhook_events]
check("missing" in _left and len(p7._webhook_events) == 2,
      f"数据库有记录的 missing 事件保留、done 事件不动（实际 {_left}）")
check(all(e.get("series_name") != "从未管理的剧" for e in p7._webhook_events),
      "未管理媒体的脏失效事件已移除")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)