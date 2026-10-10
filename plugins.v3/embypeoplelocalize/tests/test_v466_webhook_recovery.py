# -*- coding: utf-8 -*-
"""v4.6.66 回归测试：Webhook 删除→恢复 + 库页可见性 + 通知口径。

运行：python tests/test_v466_webhook_recovery.py

真实 db.py + 从 __init__.py 提取的真实方法体 + 真 SQLite 库（临时目录）。
覆盖用户实测场景：
  T1 新入库：server_id + emby_item_id 落库、nfo 模式库页可见、api 模式不可见
  T2 纯 Episode 组被库页隐藏 → 补写剧级行后可见（P0-6 根因链）
  T3 删除 → 恢复：译文继承（不重翻、不丢译文）；原文变化 → 才进 pending
  T4 极端情况：删 1 集 → 删 2 集 → 整部删 → 逐集恢复（计数/事件清除时机）
  T5 事件匹配边界：集号不吻合不误清 / Emby ItemId 精确命中
  T6 多服务器同名剧隔离（B 服恢复不清 A 服事件、不动 A 服观察期行）
  T7 入库通知口径：按当前翻译范围统计待翻（类型开关 + 已是中文过滤）
  T8 通知文案（真实 _notify_webhook_completed → _flush_notification_queue）
  T9 维护/探测标记的来源隔离（P0-1 联动）
"""
import sys
import os
import re
import time
import types
import tempfile
import threading
import importlib.util
from pathlib import Path
from typing import Any, List, Optional, Dict
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl66_"))
PID = "EmbyPeopleLocalize"
S1 = "___1_192_168_2_15_8096"
S2 = "___2_192_168_2_16_8096"

# ── stub app.sdk（db.py 顶部 import） ──
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

# ── 真 db.py ──
_spec = importlib.util.spec_from_file_location("epl_db", PLUGIN_DIR / "db.py")
dbm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dbm)

# ── 从 __init__.py 提取真实方法体 ──
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")

def _grab(name: str) -> str:
    m = re.search(rf"^    def {re.escape(name)}\(", _SRC, re.M)
    assert m, f"未找到方法 {name}"
    lines = _SRC[m.start():].splitlines()
    out = [lines[0]]
    for ln in lines[1:]:
        if ln.strip() == "":
            out.append(ln)
            continue
        if re.match(r"^    \S", ln):   # 恰好 4 空格 + 非空格 = 下一个成员
            break
        out.append(ln)
    # 前置装饰器（@staticmethod 等）—— 与 def 同缩进且紧邻
    pre = []
    _head = _SRC[:m.start()].rstrip("\n").splitlines()
    while _head and re.match(r"^    @", _head[-1]):
        pre.insert(0, _head.pop())
    return "\n".join(pre + out)

_METHODS = [
    "_tx_scope", "_tx_scope_allows", "_collect_trans_types", "_tx_eff_types",
    "_tx_type_enabled", "_tx_role_type_enabled",
    "_tx_occ_id", "_tx_limits_by_level", "_tx_occurrences",
    "_tx_exclude_episodes",
    "_looks_like_chinese", "_looks_like_japanese", "_looks_like_spaced_cjk_name",
    "_name_is_zh", "_skip_no_translate", "_zhconv_convert",
    "_ingest_scope_brief",
    "_push_webhook_event", "_remove_missing_event",
    "_notify_webhook_completed", "_add_notification_to_queue", "_flush_notification_queue",
]

class NotificationType:
    Manual = "Manual"

_NS = {"logger": logger, "time": time, "datetime": datetime, "threading": threading,
       "List": List, "Optional": Optional, "Dict": Dict,
       "NotificationType": NotificationType, "HAS_ZHCONV": False}
_CLS_CACHE = {}

def _cls_for(pid: str):
    """按 plugin_id 生成独立的提取类（self.__class__.__name__ == pid，与库中数据同命名空间）"""
    if pid not in _CLS_CACHE:
        ns = dict(_NS)
        src = (f"class {pid}:\n"
               "    TX_TYPE_SWITCH = {'Actor': 'actor', 'VoiceActor': 'actor', "
               "'GuestStar': 'guest', 'Director': 'director', 'Writer': 'writer', 'Producer': 'producer'}\n"
               + "\n".join(_grab(n) for n in _METHODS))
        exec(compile(src, "<extract:__init__.py>", "exec"), ns)
        _CLS_CACHE[pid] = ns[pid]
    return _CLS_CACHE[pid]

def make_plugin(pdb, pid):
    p = _cls_for(pid)()
    p.plugin_name = pid
    p._people_db = pdb
    p._webhook_events = []
    p._save_state = lambda: None
    p._nfo_dead_grace_hours = 24
    p._tx_target_scope = "both"
    p._tx_source = ""
    p._translate_all = False
    p._translate_person = True
    p._translate_role = True
    p._translate_actor = True
    p._translate_guest_star = False
    p._translate_director = False
    p._translate_writer = False
    p._translate_producer = False
    p._actor_limit = 10
    p._guest_limit = 10
    p._director_limit = 3
    p._writer_limit = 3
    p._notify_on_complete = True
    p._notification_lock = threading.RLock()
    p._notification_queue = {}
    p._notification_flush_timer = None
    return p

def people_row(before, after="", rbefore="", rafter="", ptype="Actor"):
    """人物 dict：Name=译文（空则原文占位=待翻）"""
    return {"before_name": before, "Name": after or before,
            "before_role": rbefore, "Role": rafter or rbefore, "Type": ptype}

_N = [0, 0]   # 断言计数
def check(cond, msg):
    _N[0] += 1
    if cond:
        print(f"  [PASS] {msg}")
    else:
        _N[1] += 1
        print(f"  [FAIL] {msg}")

def deleted_rows(pdb, pid):
    r = dbm._q1("SELECT COUNT(*) c FROM person WHERE plugin_id=? AND deleted_at IS NOT NULL AND deleted_at<>''", (pid,))
    return int((r or {}).get("c") or 0)

print("=" * 72)
print("v4.6.66 回归测试（真库真码）")
print("=" * 72)

pdb = dbm.PeopleDb()
pdb.ensure_table()

# ─────────────────────────────────────────────
print("\n[T1] 新入库：server_id/emby_item_id 落库 + 库页可见性")
# ─────────────────────────────────────────────
T1 = "T1"
n = pdb.upsert_people(plugin_id=T1, server_id=S1, item_id="tvdb:41072", item_type="Series",
                      title="我的剧", series_name="我的剧",
                      nfo_path="X:/media/tv/MyShow/tvshow.nfo", emby_item_id="31998",
                      people=[people_row("Kana Hanazawa", "花泽香菜", "(voice)", "（配音）")])
check(n == 1, "剧级 1 行写入")
r = dbm._q1("SELECT server_id, emby_item_id, nfo_path FROM person WHERE plugin_id=?", (T1,))
check(r["server_id"] == S1, f"server_id 落真实来源（P0-1）：{r['server_id']}")
check(r["emby_item_id"] == "31998", f"emby_item_id 单存 Emby ItemId（P0-2）：{r['emby_item_id']}")
items, total = pdb.library_items_page(plugin_id=T1, scan_mode="nfo")
check(total == 1 and items and items[0]["item_id"] == "tvdb:41072",
      f"nfo 模式库页可见（ScanScope 改为按 nfo_path 判定）：total={total}")
items2, total2 = pdb.library_items_page(plugin_id=T1, scan_mode="api")
check(total2 == 0, f"api 模式不含本地来源：total={total2}")

# ─────────────────────────────────────────────
print("\n[T2] 纯 Episode 组隐藏 → 补写剧级行后可见（P0-6）")
# ─────────────────────────────────────────────
T2 = "T2"
pdb.upsert_people(plugin_id=T2, server_id=S1, item_id="tvdb:999", item_type="Episode",
                  title="我的剧", series_name="我的剧", season_num=1, episode_num=1,
                  nfo_path="X:/media/tv/S2/Season 1/S01E01.nfo", emby_item_id="55001",
                  people=[people_row("Kana Hanazawa")])
check(pdb.item_has_series_row(plugin_id=T2, item_id="tvdb:999", server_id=None) is False,
      "单集入库后无剧级行（item_has_series_row=False）")
items, total = pdb.library_items_page(plugin_id=T2, scan_mode="nfo")
check(total == 0, f"纯 Episode 组被库页隐藏（复现「库里显示不出来」）：total={total}")
pdb.upsert_people(plugin_id=T2, server_id=S1, item_id="tvdb:999", item_type="Series",
                  title="我的剧", series_name="我的剧",
                  nfo_path="X:/media/tv/S2/tvshow.nfo", emby_item_id="55000",
                  people=[people_row("Kana Hanazawa")])
check(pdb.item_has_series_row(plugin_id=T2, item_id="tvdb:999", server_id=None) is True,
      "补写剧级行后 item_has_series_row=True")
items, total = pdb.library_items_page(plugin_id=T2, scan_mode="nfo")
check(total == 1, f"补写剧级行后库页可见：total={total}")

# ─────────────────────────────────────────────
print("\n[T3] 删除→恢复：译文继承（核心）")
# ─────────────────────────────────────────────
T3 = "T3"
E1 = "X:/media/tv/S3/Season 1/S01E01.nfo"
pdb.upsert_people(plugin_id=T3, server_id=S1, item_id="tvdb:1", item_type="Episode",
                  title="我的剧", series_name="我的剧", season_num=1, episode_num=1,
                  nfo_path=E1, emby_item_id="70001",
                  people=[people_row("Kana Hanazawa", "花泽香菜", "(voice)", "（配音）"),
                          people_row("Ayane Sakura", "佐仓绫音", "Mirai", "未来")])
r = dbm._q1("SELECT translated_at, name_after FROM person WHERE plugin_id=? AND nfo_path=? AND name_before='Kana Hanazawa'", (T3, E1))
_t0 = str(r["translated_at"])
check(r["name_after"] == "花泽香菜" and _t0, "初始译文已入库（花泽香菜）")
# 删除（v4.6.98：写入/删除类必须显式限定 server scope）
n = pdb.mark_deleted_by_nfo_path(plugin_id=T3, nfo_path=E1, server_id=S1)
check(n == 2, f"删除标记 2 行：n={n}")
check(pdb.is_deleted_by_nfo_path(plugin_id=T3, nfo_path=E1) is True, "恢复识别命中（is_deleted_by_nfo_path）")
n2 = pdb.mark_deleted_by_nfo_path(plugin_id=T3, nfo_path=E1, server_id=S1)
check(n2 == 0, f"重复标记不重复计数：n={n2}")
# 恢复：清观察期 + 重写（person_map={} 情形 —— 只给原文）
pdb.clear_deleted(plugin_id=T3, nfo_path=E1, series_name="我的剧", season_num=1, episode_num=1)
pdb.upsert_people(plugin_id=T3, server_id=S1, item_id="tvdb:1", item_type="Episode",
                  title="我的剧", series_name="我的剧", season_num=1, episode_num=1,
                  nfo_path=E1, emby_item_id="70002",
                  people=[people_row("Kana Hanazawa", "", "(voice)", ""),
                          people_row("Ayane Sakura", "", "Mirai", ""),
                          people_row("Saori Hayami", "", "(voice)", "")])
rows = {(x["name_before"]): x for x in pdb.people_of_item(plugin_id=T3, item_id="tvdb:1", server_id=S1)}
check(rows["Kana Hanazawa"]["name_after"] == "花泽香菜",
      f"恢复继承译文（原文未变）：{rows['Kana Hanazawa']['name_after']}")
check(str(rows["Kana Hanazawa"].get("role_after") or "") == "（配音）",
      f"恢复继承角色译文：{rows['Kana Hanazawa'].get('role_after')}")
check(str(rows["Kana Hanazawa"].get("translated_at") or "") == _t0, "translated_at 保留原值（未重翻）")
check(str(rows["Saori Hayami"]["name_after"] or "") == "Saori Hayami",
      f"新增词条仍为待翻（进 pending）：{rows['Saori Hayami']['name_after']}")
# 已恢复：观察期应为空
check(deleted_rows(pdb, T3) == 0, "恢复后观察期行清零")

# ─────────────────────────────────────────────
print("\n[T4] 极端情况：删 1 集 → 删 2 集 → 整部删 → 逐集恢复")
# ─────────────────────────────────────────────
T4 = "T4"
DIR = "X:/media/tv/S4"
EPS = {1: f"{DIR}/Season 1/S01E01.nfo", 2: f"{DIR}/Season 1/S01E02.nfo", 3: f"{DIR}/Season 1/S01E03.nfo"}
TV = f"{DIR}/tvshow.nfo"
for ep, path in EPS.items():
    pdb.upsert_people(plugin_id=T4, server_id=S1, item_id="tvdb:4", item_type="Episode",
                      title="我的剧", series_name="我的剧", season_num=1, episode_num=ep,
                      nfo_path=path, emby_item_id=f"9{ep:04d}",
                      people=[people_row("Kana Hanazawa", "花泽香菜"),
                              people_row("Ayane Sakura", "佐仓绫音")])
pdb.upsert_people(plugin_id=T4, server_id=S1, item_id="tvdb:4", item_type="Series",
                  title="我的剧", series_name="我的剧", nfo_path=TV, emby_item_id="90000",
                  people=[people_row("Kana Hanazawa", "花泽香菜")])
p = make_plugin(pdb, T4)
# 事件：3 条单集 + 1 条整剧（整剧事件模拟真实：无 SeriesName、Name=剧名、旧 Emby ItemId）
p._push_webhook_event("90001", "第 1 集", "missing", "已删除", series_name="我的剧", season=1, episode=1, server_id=S1)
p._push_webhook_event("90002", "第 2 集", "missing", "已删除", series_name="我的剧", season=1, episode=2, server_id=S1)
p._push_webhook_event("90003", "第 3 集", "missing", "已删除", series_name="我的剧", season=1, episode=3, server_id=S1)
p._push_webhook_event("90000", "我的剧", "missing", "整部删除", series_name="", season=None, episode=None, server_id=S1)
check(len(p._webhook_events) == 4, "4 条失效事件已登记（3 单集 + 1 整剧）")
# 删除 1 集（v4.6.98：显式 server scope）
n = pdb.mark_deleted_by_nfo_path(plugin_id=T4, nfo_path=EPS[1], server_id=S1)
check(n == 2, f"删第 1 集：标记 2 行（n={n}）")
# 再删 2 集（两条事件）
n = (pdb.mark_deleted_by_nfo_path(plugin_id=T4, nfo_path=EPS[2], server_id=S1)
     + pdb.mark_deleted_by_nfo_path(plugin_id=T4, nfo_path=EPS[3], server_id=S1))
check(n == 4, f"再删第 2/3 集：标记 4 行（n={n}）")
# 整部删（目录前缀）
n = pdb.mark_deleted_by_nfo_path_prefix(plugin_id=T4, path_prefix=DIR, server_id=S1)
check(n == 1, f"整部删除：只标记未标过的剩余 1 行（剧级行，n={n}）")
check(deleted_rows(pdb, T4) == 7, f"全库观察期 = 7 行（全集计一次，不重复）：{deleted_rows(pdb, T4)}")
# 恢复第 1 集
pdb.clear_deleted(plugin_id=T4, nfo_path=EPS[1], series_name="我的剧", season_num=1, episode_num=1,
                  server_id=S1)
pdb.upsert_people(plugin_id=T4, server_id=S1, item_id="tvdb:4", item_type="Episode",
                  title="我的剧", series_name="我的剧", season_num=1, episode_num=1,
                  nfo_path=EPS[1], emby_item_id="91001",
                  people=[people_row("Kana Hanazawa", ""), people_row("Ayane Sakura", "")])
_c = p._remove_missing_event(series_name="我的剧", season=1, episode=1, title="第 1 集",
                             server_id=S1, item_id="91001")
_miss = [e for e in p._webhook_events if e.get("status") == "missing"]
check(_c == 1 and len(_miss) == 3, f"恢复 1 集 → 只清该集事件（清除 {_c}，剩 {len(_miss)}）")
check(any(e.get("episode") is None for e in _miss), "整剧事件保留（其余集仍在观察期，未误清）")
rows = {(x["name_before"]): x for x in pdb.people_of_item(plugin_id=T4, item_id="tvdb:4", server_id=S1)}
check(rows["Kana Hanazawa"]["name_after"] == "花泽香菜", "恢复的集继承译文")
# 恢复第 2 集
pdb.clear_deleted(plugin_id=T4, nfo_path=EPS[2], series_name="我的剧", season_num=1, episode_num=2,
                  server_id=S1)
pdb.upsert_people(plugin_id=T4, server_id=S1, item_id="tvdb:4", item_type="Episode",
                  title="我的剧", series_name="我的剧", season_num=1, episode_num=2,
                  nfo_path=EPS[2], emby_item_id="91002",
                  people=[people_row("Kana Hanazawa", ""), people_row("Ayane Sakura", "")])
_c = p._remove_missing_event(series_name="我的剧", season=1, episode=2, title="第 2 集",
                             server_id=S1, item_id="91002")
_miss = [e for e in p._webhook_events if e.get("status") == "missing"]
check(_c == 1 and len(_miss) == 2, f"恢复第 2 集 → 剩 2 条（第 3 集 + 整剧，清除 {_c}）")
# 恢复第 3 集（最后一条：整剧事件应一并清除）
pdb.clear_deleted(plugin_id=T4, nfo_path=EPS[3], series_name="我的剧", season_num=1, episode_num=3,
                  server_id=S1)
pdb.upsert_people(plugin_id=T4, server_id=S1, item_id="tvdb:4", item_type="Episode",
                  title="我的剧", series_name="我的剧", season_num=1, episode_num=3,
                  nfo_path=EPS[3], emby_item_id="91003",
                  people=[people_row("Kana Hanazawa", ""), people_row("Ayane Sakura", "")])
pdb.clear_deleted(plugin_id=T4, nfo_path=TV)
pdb.upsert_people(plugin_id=T4, server_id=S1, item_id="tvdb:4", item_type="Series",
                  title="我的剧", series_name="我的剧", nfo_path=TV, emby_item_id="91000",
                  people=[people_row("Kana Hanazawa", "")])
_c = p._remove_missing_event(series_name="我的剧", season=1, episode=3, title="第 3 集",
                             server_id=S1, item_id="91003")
_miss = [e for e in p._webhook_events if e.get("status") == "missing"]
check(_c == 2 and len(_miss) == 0, f"最后恢复 → 清第 3 集 + 整剧事件（清除 {_c}，剩 {len(_miss)}）")
check(deleted_rows(pdb, T4) == 0, "全部恢复后观察期清零")
rows = {(x["name_before"]): x for x in pdb.people_of_item(plugin_id=T4, item_id="tvdb:4", server_id=S1)}
check(rows["Kana Hanazawa"]["name_after"] == "花泽香菜", "整剧恢复后译文全部保留（未重翻为英文）")

# ─────────────────────────────────────────────
print("\n[T5] 事件匹配边界：集号不吻合 / 身份精确命中")
# ─────────────────────────────────────────────
T5 = "T5"
p = make_plugin(pdb, T5)
p._push_webhook_event("A-EP1", "第 1 集", "missing", "已删除", series_name="边界剧", season=1, episode=1, server_id=S1)
_c = p._remove_missing_event(series_name="边界剧", season=1, episode=2, title="第 2 集", server_id=S1, item_id="B-EP2")
check(_c == 0 and len(p._webhook_events) == 1, "恢复第 2 集不清第 1 集事件（集号校验）")
p._push_webhook_event("OLD-ID", "整部剧", "missing", "整部删除", series_name="", season=None, episode=None, server_id=S1)
_c = p._remove_missing_event(series_name="边界剧", season=None, episode=None, title="整部剧",
                             server_id=S1, item_id="OLD-ID")
check(_c == 1 and len(p._webhook_events) == 1, "Emby ItemId 精确命中 → 直接清（同 ID 恢复）")

# ─────────────────────────────────────────────
print("\n[T6] 多服务器同名剧隔离")
# ─────────────────────────────────────────────
T6 = "T6"
EA = "X:/media/a/同名剧/Season 1/S01E01.nfo"
EB = "Y:/media/b/同名剧/Season 1/S01E01.nfo"
for sid, path in ((S1, EA), (S2, EB)):
    pdb.upsert_people(plugin_id=T6, server_id=sid, item_id=f"tvdb:{sid[-4:]}", item_type="Episode",
                      title="同名剧", series_name="同名剧", season_num=1, episode_num=1,
                      nfo_path=path, emby_item_id="1",
                      people=[people_row("Kana Hanazawa", "花泽香菜")])
p = make_plugin(pdb, T6)
n = pdb.mark_deleted_by_nfo_path(plugin_id=T6, nfo_path=EA, server_id=S1)
p._push_webhook_event("X1", "第 1 集", "missing", "已删除", series_name="同名剧", season=1, episode=1, server_id=S1)
check(deleted_rows(pdb, T6) == 1, "A 服标记 1 行")
# B 服恢复（同名同集，不同服 —— 与产品同路径：带 server_id 收窄）
pdb.clear_deleted(plugin_id=T6, nfo_path=EB, series_name="同名剧", season_num=1, episode_num=1,
                  server_id=S2)
_c = p._remove_missing_event(series_name="同名剧", season=1, episode=1, title="第 1 集", server_id=S2, item_id="Z9")
check(_c == 0 and len(p._webhook_events) == 1, "B 服恢复不清 A 服事件（server_id 隔离）")
check(deleted_rows(pdb, T6) == 1, "B 服恢复不动 A 服观察期行（路径 + server_id 隔离）")
# A 服恢复
pdb.clear_deleted(plugin_id=T6, nfo_path=EA, series_name="同名剧", season_num=1, episode_num=1,
                  server_id=S1)
_c = p._remove_missing_event(series_name="同名剧", season=1, episode=1, title="第 1 集", server_id=S1, item_id="Z1")
check(_c == 1 and len(p._webhook_events) == 0, "A 服恢复清 A 服事件")
check(deleted_rows(pdb, T6) == 0, "A 服观察期清零")

# ─────────────────────────────────────────────
print("\n[T7] 入库通知口径：按当前翻译范围统计待翻（P1-1/P1-2）")
# ─────────────────────────────────────────────
T7 = "T7"
p = make_plugin(pdb, T7)
kana = people_row("Kana Hanazawa")                       # 日文名 Actor → 待翻
ayane = people_row("Ayane Sakura")                       # 日文名 Actor → 待翻
zh = people_row("花泽香菜")                               # 已是中文 → 跳过
nolan = people_row("Christopher Nolan", ptype="Director")  # Director 开关 OFF → 不计
kana["before_role"] = "(voice)"; kana["Role"] = "(voice)"        # 角色待翻
zh["before_role"] = "（配音）"; zh["Role"] = "（配音）"            # 角色已是中文 → 跳过
pdb.upsert_people(plugin_id=T7, server_id=S1, item_id="tvdb:7", item_type="Series",
                  title="口径剧", series_name="口径剧", nfo_path="X:/media/tv/S7/tvshow.nfo",
                  emby_item_id="77", people=[kana, ayane, zh, nolan])
brief = p._ingest_scope_brief([(S1, "tvdb:7")])
check(brief["pending_person"] == 2, f"第一排待翻 = 2（日文 Actor；中文/导演不计）：{brief['pending_person']}")
check(brief["pending_role"] == 1, f"第二排待翻 = 1（中文角色不计）：{brief['pending_role']}")
check(brief["pending"] == 3, f"合计待翻 = 3（不再拿采集数冒充）：{brief['pending']}")
check(brief["total"] == 4, f"采集总量 = 4：{brief['total']}")
check(brief["translated"] == 0, f"已有译文 = 0：{brief['translated']}")
# 追加一条已翻译 → translated+1，且不计入 pending
pdb.upsert_people(plugin_id=T7, server_id=S1, item_id="tvdb:7", item_type="Series",
                  title="口径剧", series_name="口径剧", nfo_path="X:/media/tv/S7/tvshow.nfo",
                  emby_item_id="77", people=[kana, ayane, zh, nolan, people_row("Saori Hayami", "早见沙织")])
brief = p._ingest_scope_brief([(S1, "tvdb:7")])
check(brief["pending"] == 3 and brief["translated"] == 1,
      f"已翻不影响待翻：pending={brief['pending']} translated={brief['translated']}")
# 关掉「角色」总开关 → 角色不计、人名不变（口径随筛选实时变化）
p._translate_role = False
brief = p._ingest_scope_brief([(S1, "tvdb:7")])
check(brief["pending_person"] == 2 and brief["pending_role"] == 0,
      f"关闭角色开关 → 角色 0、人名仍 2：pending={brief['pending']}")
p._translate_role = True
# 打开「导演」类型 → 导演人名计入
p._translate_director = True
brief = p._ingest_scope_brief([(S1, "tvdb:7")])
check(brief["pending_person"] == 3, f"打开导演类型 → 人名 3：{brief['pending_person']}")
p._translate_director = False

# ─────────────────────────────────────────────
print("\n[T8] 通知文案（恢复 + 采集/已有译文/待翻拆分）")
# ─────────────────────────────────────────────
T8 = "T8"
p = make_plugin(pdb, T8)
CAP = []
p.post_message = lambda mtype=None, title="", text="": CAP.append(text)
p._notify_webhook_completed("80001", "我的剧", 0, 0,
                            {"SeriesName": "我的剧", "IndexNumber": 1, "ParentIndexNumber": 1},
                            recovered=13, llm_calls=2, zhconv=1, batch=True,
                            pool=0, pending_left=3, existing=5, collected=9)
p._flush_notification_queue()
_txt = CAP[0] if CAP else ""
check("待翻 3 个（按当前翻译范围" in _txt, "文案：待翻按当前翻译范围口径")
check("📥 采集 9 词条 ｜ ✅ 已有译文 5 条（未重翻）" in _txt, "文案：采集/已有译文分列")
check("🔄 其中已恢复被删条目 13 个（重新入库）" in _txt, "文案：恢复标记（v4.6.84 改为恢复文件数）")
check("🤖 LLM：2 次" in _txt, "文案：AI 调用次数保留")

# ─────────────────────────────────────────────
print("\n[T9] 维护/探测标记的来源隔离（P0-1 联动）")
# ─────────────────────────────────────────────
T9 = "T9"
pdb.upsert_people(plugin_id=T9, server_id=S1, item_id="tvdb:9", item_type="Series", title="标记剧",
                  series_name="标记剧", nfo_path="X:/media/tv/S9/tvshow.nfo", emby_item_id="99",
                  people=[people_row("Kana Hanazawa", "花泽香菜")])
pdb.upsert_people(plugin_id=T9, server_id="", item_id="tvdb:9", item_type="Series", title="标记剧",
                  series_name="标记剧", nfo_path="Y:/media/tv/S9/tvshow.nfo", emby_item_id="",
                  people=[people_row("Kana Hanazawa", "花泽香菜")])
lite = pdb.library_items_lite(plugin_id=T9)
check(len(lite) == 2 and {x["server_id"] for x in lite} == {S1, ""},
      f"维护列表按来源分组并带出 server_id：{[x['server_id'] for x in lite]}")
n = pdb.mark_deleted(plugin_id=T9, item_ids=["tvdb:9"], server_id=S1)
check(n == 1 and deleted_rows(pdb, T9) == 1, f"按来源标记只影响该来源（n={n}）")
pdb.upsert_people(plugin_id=T9, server_id=S2, item_id="tvdb:9b", item_type="Episode", title="标记剧",
                  series_name="标记剧", season_num=1, episode_num=1,
                  nfo_path="Z:/media/tv/S9/S01E01.nfo", emby_item_id="991",
                  people=[people_row("Ayane Sakura", "佐仓绫音")])
n = pdb.mark_deleted_by_episode(plugin_id=T9, item_id="tvdb:9b", season_num=1, episode_num=1, server_id=S2)
check(n == 1, f"探测反向标记按 skey 命中（n={n}）")
n2 = pdb.mark_deleted_by_episode(plugin_id=T9, item_id="tvdb:9b", season_num=1, episode_num=1, server_id=S1)
check(n2 == 0 and deleted_rows(pdb, T9) == 2, f"其他服务器标记不到（来源隔离）：n={n2}")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)