# -*- coding: utf-8 -*-
"""v4.6.67 回归测试：删除隔离 / 定时扫描间隔 / 通知口径 / TMDB 有效开关 / 0=不限 / 简介解耦。

运行：python tests/test_v467_webhook_notify_scan.py

真实 db.py + 真实 nfo.py + 从 __init__.py 提取的真实方法体 + 真 SQLite。
对应审查报告（4.6.66 测试报告 2026-10-05）P0/P1 项：
  T1 删除按 nfo_path 标记的 server_id 隔离（同路径双服务器）
  T2 is_deleted_by_nfo_path 的来源隔离
  T3 Series 入库通知不再把 NFO 文件数写成「翻译 N 条」
  T4 NFO 收集层人数上限 0=不限（与 DB 层统一）
  T5 TMDB 第二排角色补译改用 effective role（all OR role）
  T6 TMDB 中文简介与中文名解耦写回
  T7 定时扫描一律按「上次执行 + 间隔」（>=24h 不再被每日 04:00 改写）
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
TMP = Path(tempfile.mkdtemp(prefix="epl67_"))
PID = "EmbyPeopleLocalize"
S1 = "___1_192_168_2_15_8096"
S2 = "___2_192_168_2_16_8096"

# ── stub app.sdk ──
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
    TMDB_LOCALE = "zh-CN"
_mod_cfg.settings = _Settings()
# TMDB 依赖链（_pool_tmdb_fill_one 内部 import）—— 用可注入的假实现
_tmdb_holder = {"person_detail": None}
_mod_chain = types.ModuleType("app.chain")
_mod_chain_tmdb = types.ModuleType("app.chain.tmdb")
class _FakeTmdbChain:
    def person_detail(self, tid):
        return _tmdb_holder["person_detail"]
_mod_chain_tmdb.TmdbChain = _FakeTmdbChain
_mod_mw = types.ModuleType("app.modules")
_mod_mwt = types.ModuleType("app.modules.themoviedb")
_mod_mwtmdb = types.ModuleType("app.modules.themoviedb.tmdbapi")
class _FakeTmdbApi:
    def __init__(self, **k): pass
    def get_person_detail(self, tid): return {}
_mod_mwtmdb.TmdbApi = _FakeTmdbApi
sys.modules.update({
    "app": _mod_app, "app.sdk": _mod_sdk,
    "app.sdk.logging": _mod_log, "app.sdk.config": _mod_cfg,
    "app.chain": _mod_chain, "app.chain.tmdb": _mod_chain_tmdb,
    "app.modules": _mod_mw, "app.modules.themoviedb": _mod_mwt,
    "app.modules.themoviedb.tmdbapi": _mod_mwtmdb,
})

# ── 真 db.py ──
_spec = importlib.util.spec_from_file_location("epl_db", PLUGIN_DIR / "db.py")
dbm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dbm)

# ── 真 nfo.py ──
_spec2 = importlib.util.spec_from_file_location("epl_nfo", PLUGIN_DIR / "nfo.py")
nfo = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(nfo)

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
        if re.match(r"^    \S", ln):
            break
        out.append(ln)
    pre = []
    _head = _SRC[:m.start()].rstrip("\n").splitlines()
    while _head and re.match(r"^    @", _head[-1]):
        pre.insert(0, _head.pop())
    return "\n".join(pre + out)

_METHODS = [
    "_tx_scope", "_tx_scope_allows", "_collect_trans_types",
    "_tx_exclude_episodes",
    "_looks_like_chinese", "_looks_like_japanese", "_looks_like_spaced_cjk_name",
    "_name_is_zh", "_zhconv_convert",
    "_pool_tmdb_fill_one",
    "_notify_webhook_completed", "_add_notification_to_queue", "_flush_notification_queue",
    "_run_scheduled_scan",
]

class NotificationType:
    Manual = "Manual"

_CLS_CACHE = {}

def _cls_for(pid: str, cls_name: str = None):
    key = (pid, cls_name)
    if key not in _CLS_CACHE:
        ns = {"logger": logger, "time": time, "datetime": datetime, "threading": threading,
              "List": List, "Optional": Optional, "Dict": Dict, "Any": Any,
              "NotificationType": NotificationType, "HAS_ZHCONV": False,
              "settings": _mod_cfg.settings, "re": re, "os": os,
              "getattr": getattr, "int": int, "str": str, "bool": bool, "float": float,
              "max": max, "min": min, "sum": sum, "len": len, "Exception": Exception,
              "time_module": time}
        src = (f"class {cls_name or pid}:\n"
               "    TX_TYPE_SWITCH = {'Actor': 'actor', 'VoiceActor': 'actor', "
               "'GuestStar': 'guest', 'Director': 'director', 'Writer': 'writer', 'Producer': 'producer'}\n"
               + "\n".join(_grab(n) for n in _METHODS))
        exec(compile(src, "<extract:__init__.py>", "exec"), ns)
        _c = ns[cls_name or pid]
        # v4.6.111：TMDB 负缓存的「查询 / 登记」抽成统一入口（真实现 = __init__._tmdb_dead_hit /
        # _tmdb_dead_note，含持久化；行为覆盖见 test_v4111）。这里补同语义最小桩。
        _c._tmdb_dead_hit = _tmdb_dead_hit_stub
        _c._tmdb_dead_note = _tmdb_dead_note_stub
        _CLS_CACHE[key] = _c
    return _CLS_CACHE[key]


def _tmdb_dead_hit_stub(self, key):
    _d = getattr(self, "_tmdb_dead", None) or {}
    _ts = _d.get(key)
    return bool(_ts and (time.time() - float(_ts)) < 21600.0)


def _tmdb_dead_note_stub(self, key):
    _d = getattr(self, "_tmdb_dead", None)
    if _d is None:
        _d = self._tmdb_dead = {}
    _d[key] = time.time()

def _mk(pid, cls_name=None):
    p = _cls_for(pid, cls_name)()
    p.plugin_name = pid
    return p

_N = [0, 0]
def check(cond, msg):
    _N[0] += 1
    if cond:
        print(f"  [PASS] {msg}")
    else:
        _N[1] += 1
        print(f"  [FAIL] {msg}")

def people_row(before, after="", rbefore="", rafter="", ptype="Actor"):
    return {"before_name": before, "Name": after or before,
            "before_role": rbefore, "Role": rafter or rbefore, "Type": ptype}

pdb = dbm.PeopleDb()
pdb.ensure_table()

print("=" * 72)
print("v4.6.67 回归测试（真库真码）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] 删除按 nfo_path 标记的 server_id 隔离（同路径双服务器）")
# ─────────────────────────────────────────────
T1 = "T1"
SHARED = "Z:/share/tv/Show/Season 1/S01E01.nfo"
for sid in (S1, S2):
    pdb.upsert_people(plugin_id=T1, server_id=sid, item_id=f"tvdb:{sid[-4:]}", item_type="Episode",
                      title="共享剧", series_name="共享剧", season_num=1, episode_num=1,
                      nfo_path=SHARED, emby_item_id="1",
                      people=[people_row("Kana Hanazawa", "花泽香菜")])
n = pdb.mark_deleted_by_nfo_path(plugin_id=T1, nfo_path=SHARED, server_id=S1)
_del = dbm._q("SELECT server_id FROM person WHERE plugin_id=? AND deleted_at IS NOT NULL AND deleted_at<>''", (T1,))
check(n == 1 and [str(r["server_id"]) for r in _del] == [S1],
      f"A 服删除只标记 A 服同路径记录（n={n}）")
n = pdb.mark_deleted_by_nfo_path(plugin_id=T1, nfo_path=SHARED, server_id=S2)
check(n == 1 and len(_del) == 1, f"B 服删除标记 B 服（各标各的，n={n}）")
# 遗留空来源行：带 server_id 时也应能标记（不漏升级前数据）
pdb.upsert_people(plugin_id=T1, server_id="", item_id="legacy:1", item_type="Episode",
                  title="共享剧", series_name="共享剧", season_num=1, episode_num=1,
                  nfo_path="L:/legacy/S01E01.nfo", emby_item_id="",
                  people=[people_row("Ayane Sakura", "佐仓绫音")])
n = pdb.mark_deleted_by_nfo_path(plugin_id=T1, nfo_path="L:/legacy/S01E01.nfo", server_id=S1)
check(n == 1, f"带 server_id 也覆盖旧版空来源行（n={n}）")
# 目录前缀隔离
D_A, D_B = "P:/lib/A/Show", "P:/lib/B/Show"
for sid, d in ((S1, D_A), (S2, D_B)):
    pdb.upsert_people(plugin_id=T1 + "P", server_id=sid, item_id=f"tvdb:p{sid[-1]}", item_type="Series",
                      title="前缀剧", series_name="前缀剧", nfo_path=d + "/tvshow.nfo", emby_item_id="2",
                      people=[people_row("Kana Hanazawa")])
n = pdb.mark_deleted_by_nfo_path_prefix(plugin_id=T1 + "P", path_prefix=D_A, server_id=S1)
check(n == 1, f"整剧前缀删除只标记指定来源（n={n}）")

# ─────────────────────────────────────────────
print("\n[T2] is_deleted_by_nfo_path 的来源隔离")
# ─────────────────────────────────────────────
T2 = "T2"
PA, PB = "Q:/a/Ep.nfo", "Q:/b/Ep.nfo"
for sid, path in ((S1, PA), (S2, PB)):
    pdb.upsert_people(plugin_id=T2, server_id=sid, item_id=f"tvdb:i{sid[-1]}", item_type="Episode",
                      title="剧", series_name="剧", season_num=1, episode_num=1,
                      nfo_path=path, emby_item_id="3",
                      people=[people_row("Kana Hanazawa", "花泽香菜")])
pdb.mark_deleted_by_nfo_path(plugin_id=T2, nfo_path=PA, server_id=S1)
check(pdb.is_deleted_by_nfo_path(plugin_id=T2, nfo_path=PA, server_id=S1) is True,
      "A 服查 A 服路径 → 命中")
check(pdb.is_deleted_by_nfo_path(plugin_id=T2, nfo_path=PA, server_id=S2) is False,
      "B 服查同一路径 → 不命中（来源隔离）")
check(pdb.is_deleted_by_nfo_path(plugin_id=T2, nfo_path=PA) is True,
      "不传 server_id（None）→ 跨来源（旧行为）")

# ─────────────────────────────────────────────
print("\n[T3] Series 入库通知不再把 NFO 文件数写成「翻译 N 条」")
# ─────────────────────────────────────────────
T3 = "T3"
p = _mk(T3)
p._notify_on_complete = True
p._notification_lock = threading.RLock()
p._notification_queue = {}
p._notification_flush_timer = None
CAP = []
p.post_message = lambda mtype=None, title="", text="": CAP.append(text)
# 入库批次：3 个 NFO / 采集 69 / 待翻 69
p._notify_webhook_completed("i1", "我的剧", 0, 0,
                            {"SeriesName": "我的剧", "IndexNumber": 1, "ParentIndexNumber": 1},
                            recovered=False, batch=True, pending_left=69,
                            existing=0, collected=69, ingested=3)
p._flush_notification_queue()
_txt = CAP[0] if CAP else ""
check("入库完成" in _txt, f"标题为「入库完成」：{_txt.splitlines()[0] if _txt else '(空)'}")
check("📥 入库 NFO 3 个" in _txt, "显示入库 NFO 文件数")
check("待翻 69 个" in _txt, "显示按当前范围的待翻词条数")
check("翻译：3 条" not in _txt and "翻译完成" not in _txt,
      "不再出现「翻译：3 条」/「翻译完成」")
# 真正翻译批次：6 词条
CAP.clear()
p._notify_webhook_completed("i2", "我的剧", 6, 0,
                            {"SeriesName": "我的剧", "IndexNumber": 2, "ParentIndexNumber": 1},
                            llm_calls=1, batch=True, pending_left=0, ingested=0)
p._flush_notification_queue()
_txt2 = CAP[0] if CAP else ""
check("翻译完成" in _txt2 and "✅ 翻译：6 条" in _txt2,
      "真正翻译批次仍显示「翻译完成 / 翻译：6 条」")

# ─────────────────────────────────────────────
print("\n[T4] NFO 收集层人数上限 0=不限（与 DB 层统一）")
# ─────────────────────────────────────────────
_XML = """<movie><title>T</title>
<actor><name>A1</name><role>r1</role><type>Actor</type></actor>
<actor><name>A2</name><role>r2</role><type>Actor</type></actor>
<actor><name>A3</name><role>r3</role><type>Actor</type></actor>
<director>D1</director><director>D2</director>
</movie>"""
import xml.etree.ElementTree as ET
doc = nfo.NfoDoc("T:/x/movie.nfo")
doc.root = ET.fromstring(_XML)
ns0, _ = doc.collect(translate_types={"actor": True, "director": True}, limits={"actor": 0, "director": 0})
check([n[0] for n in ns0] == ["A1", "A2", "A3", "D1", "D2"],
      f"0 = 不限（收全：3 演员 + 2 导演）：{[n[0] for n in ns0]}")
ns1, _ = doc.collect(translate_types={"actor": True, "director": True}, limits={"actor": 2, "director": 1})
check([n[0] for n in ns1] == ["A1", "A2", "D1"],
      f"N>0 仍按前 N 个收：{[n[0] for n in ns1]}")

# ─────────────────────────────────────────────
print("\n[T5] TMDB 第二排角色补译改用 effective role")
# ─────────────────────────────────────────────
T5 = "T5"
p = _mk(T5)
p._translate_all = True
p._translate_role = False          # 历史子开关为 false，但「全部类型」已开
p._translate_person = True
p._translate_actor = True
p._translate_guest_star = False
p._translate_director = False
p._translate_writer = False
p._translate_producer = False
_eff = p._collect_trans_types().get("translate", {})
check(_eff.get("role") is True, f"effective role = all OR role = True（role={_eff.get('role')}）")
# 源码守卫：credits 触发条件必须读 effective（_tr['role']），不得再读原始 _translate_role
m = re.search(r'if getattr\(self, "_pool_tmdb_credits"[^\n]*', _SRC)
_line = m.group(0) if m else ""
check("_tr.get" in _line and '"_translate_role"' not in _line,
      f"credits 触发用 effective role：{_line.strip()}")

# ─────────────────────────────────────────────
print("\n[T6] TMDB 中文简介与中文名解耦写回")
# ─────────────────────────────────────────────
T6 = "T6"
class _FakeCli:
    def __init__(self, tid="12345"):
        self.updated = []
        self._tid = tid
    def get_person_detail(self, pid):
        return {"Id": pid, "ProviderIds": {"Tmdb": self._tid}, "LockedFields": []}
    def update_person_info(self, pid, info):
        self.updated.append(info); return True
    def set_person_primary_image(self, pid, img): return True
class _Pd:
    def __init__(self, name, aka, bio, prof=""):
        self.name = name; self.also_known_as = aka
        self.biography = bio; self.profile_path = prof

p = _mk(T6)
p._tmdb_person_cache = {}

# 场景 1：只有中文简介、没有中文名 → 仍应写回 Overview（旧代码要求 name+bio 同时存在 → 不写）
_tmdb_holder["person_detail"] = _Pd("水橋かおり", [], "日本女性声优，东京都出身。")
cli = _FakeCli(tid="20001")
out = p._pool_tmdb_fill_one(cli, server_id=S1, person_id="p1", name_cur="水橋かおり")
check(out["cn_name"] == "" and len(cli.updated) == 1
      and "Overview" in (cli.updated[0].get("LockedFields") or []),
      f"仅中文简介也写回（cn_name='{out['cn_name']}'，写回 {len(cli.updated)} 次）")
# 场景 2：有中文名 + 中文简介 → 仍写回
_tmdb_holder["person_detail"] = _Pd("Kana", ["花泽香菜"], "日本女性声优。")
cli2 = _FakeCli(tid="20002")
out2 = p._pool_tmdb_fill_one(cli2, server_id=S1, person_id="p2", name_cur="Kana")
check(out2["cn_name"] == "花泽香菜" and len(cli2.updated) == 1,
      f"中文名 + 简介正常（cn_name={out2['cn_name']}）")
check("Overview" in (cli2.updated[0].get("LockedFields") or []),
      "写回时锁定 Overview")
# 场景 3：简介非中文（纯英文）→ 不写回
_tmdb_holder["person_detail"] = _Pd("Kana", ["花泽香菜"], "Japanese voice actress.")
cli3 = _FakeCli(tid="20003")
p._pool_tmdb_fill_one(cli3, server_id=S1, person_id="p3", name_cur="Kana")
check(len(cli3.updated) == 0, "英文简介不写回")

# ─────────────────────────────────────────────
print("\n[T7] 定时扫描一律按「上次执行 + 间隔」（>=24h 不再被 04:00 改写）")
# ─────────────────────────────────────────────
T7 = "T7"
NOW = 1_800_000_000.0

class _FakeTime:
    @staticmethod
    def time(): return NOW
    def localtime(self, *a): return time.localtime(*a)
    def mktime(self, *a): return time.mktime(*a)
    def strftime(self, *a, **k): return time.strftime(*a, **k)

class _NullCtx:
    def __enter__(self): return self
    def __exit__(self, *a): return False

# 用假 time 替换提取命名空间里的 time（方法内部调用 time.time()）
def _run_sched(interval_h, last):
    ns = {"logger": logger, "time": _FakeTime(), "datetime": datetime, "threading": threading,
          "List": List, "Optional": Optional, "Dict": Dict, "Any": Any,
          "NotificationType": NotificationType, "HAS_ZHCONV": False,
          "settings": _mod_cfg.settings, "re": re, "os": os}
    src = ("class S:\n"
           "    TX_TYPE_SWITCH = {}\n" + _grab("_run_scheduled_scan"))
    exec(compile(src, "<extract:sched>", "exec"), ns)
    p = ns["S"]()
    p._schedule_interval_hours = interval_h
    p._last_full_scan_ts = last
    p._all_nfo_roots = lambda: ["X:/lib"]
    p._scan_lock = _NullCtx()
    p._is_running = False
    p._save_state = lambda: None
    p._push_log = lambda *a, **k: None
    p._launched = []
    p._launch_nfo_worker = lambda *a, **k: p._launched.append(1)
    p._run_scheduled_scan()
    return len(p._launched)

check(_run_sched(48, NOW - 47 * 3600) == 0, "48h 间隔、仅过 47h → 不触发")
check(_run_sched(48, NOW - 49 * 3600) == 1, "48h 间隔、已过 49h → 触发")
check(_run_sched(24, NOW - 1 * 3600) == 0, "24h 间隔、仅过 1h → 不触发")
check(_run_sched(24, NOW - 25 * 3600) == 1, "24h 间隔、已过 25h → 触发")
# 关键回归：720h 间隔、仅过 100h —— 旧「每日 04:00」逻辑会误触发，新逻辑必须不触发
check(_run_sched(720, NOW - 100 * 3600) == 0,
      "720h 间隔、仅过 100h → 不触发（旧 04:00 日历逻辑会误触发）")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
