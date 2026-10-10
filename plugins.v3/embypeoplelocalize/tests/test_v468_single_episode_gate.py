# -*- coding: utf-8 -*-
"""v4.6.68 回归测试：「处理单集」在全部翻译入口的一致性门禁 + 来源判定口径。

运行：python tests/test_v468_single_episode_gate.py

真实 db.py + 从 __init__.py 提取的真实方法体 + 真 SQLite。
对应复查报告 P0：
  「处理单集」=关：Episode 可以入库，但不能进入翻译 pending / 不能进入 AI；
  =开：Episode 正常进入 pending 与 Worker。手动扫描 / 定时扫描 / 探测库 /
  Webhook / Series 展开 / 删除恢复 必须完全一致。
覆盖：
  T1 待翻查询（pending_terms_full / force_item_occurrences）门禁
  T2 单条目门禁（force_item_terms / pending_terms_of_item / find_pending_items）
  T3 库页条目统计（pending_items_count / pending_items_list）门禁
  T4 插件层 _tx_occurrences（翻译词条唯一来源）门禁 —— 等于「不进入 AI」
  T5 入库不受门禁影响（Episode 行照常入库，供库页查看）
  T6 scan_mode 来源判定改用 nfo_path（P0-1 后 Webhook 行带真实 server_id 不再被误排除）
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
TMP = Path(tempfile.mkdtemp(prefix="epl68_"))
S1 = "___1_192_168_2_15_8096"

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

_spec = importlib.util.spec_from_file_location("epl_db", PLUGIN_DIR / "db.py")
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
    "_tx_limits_by_level", "_tx_exclude_episodes",
    "_tx_occ_id", "_tx_occurrences",
]

class NotificationType:
    Manual = "Manual"

def _mk_cls(cls_name):
    ns = {"logger": logger, "time": time, "datetime": datetime, "threading": threading,
          "List": List, "Optional": Optional, "Dict": Dict, "Any": Any,
          "NotificationType": NotificationType, "HAS_ZHCONV": False,
          "re": re, "os": os}
    src = (f"class {cls_name}:\n"
           "    TX_TYPE_SWITCH = {'Actor': 'actor', 'VoiceActor': 'actor', "
           "'GuestStar': 'guest', 'Director': 'director', 'Writer': 'writer', 'Producer': 'producer'}\n"
           + "\n".join(_grab(n) for n in _METHODS))
    exec(compile(src, "<extract:__init__.py>", "exec"), ns)
    return ns[cls_name]

def make_plugin(pdb, cls_name="EPL68"):
    p = _mk_cls(cls_name)()
    p._people_db = pdb
    p._tx_target_scope = "both"
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
    return p

def people_row(before, after="", rbefore="", rafter="", ptype="Actor"):
    return {"before_name": before, "Name": after or before,
            "before_role": rbefore, "Role": rafter or rbefore, "Type": ptype}

_N = [0, 0]
def check(cond, msg):
    _N[0] += 1
    if cond:
        print(f"  [PASS] {msg}")
    else:
        _N[1] += 1
        print(f"  [FAIL] {msg}")

PID = "EPL68Gate"
SERIES = "tvdb:41072"
pdb = dbm.PeopleDb()
pdb.ensure_table()

# 播种：剧级 1 条 + 3 集（均属同一 series item_id，Episode 层级行共享 item_id）
TV = "X:/media/tv/Show/tvshow.nfo"
pdb.upsert_people(plugin_id=PID, server_id=S1, item_id=SERIES, item_type="Series",
                  title="门禁剧", series_name="门禁剧", nfo_path=TV, emby_item_id="100",
                  people=[people_row("Kana Hanazawa"), people_row("Ayane Sakura")])
EPS = {}
for _ep in (1, 2, 3):
    _p = f"X:/media/tv/Show/Season 1/S01E0{_ep}.nfo"
    EPS[_ep] = _p
    pdb.upsert_people(plugin_id=PID, server_id=S1, item_id=SERIES, item_type="Episode",
                      title="门禁剧", series_name="门禁剧", season_num=1, episode_num=_ep,
                      nfo_path=_p, emby_item_id=f"10{_ep}",
                      people=[people_row("Kana Hanazawa"), people_row("Guest One", ptype="GuestStar")])

print("=" * 72)
print("v4.6.68「处理单集」门禁回归测试（真库真码）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] 待翻查询门禁（pending_terms_full / force_item_occurrences）")
# ─────────────────────────────────────────────
_on = pdb.pending_terms_full(plugin_id=PID, limits=None, only_pending=True, exclude_episodes=False)
_off = pdb.pending_terms_full(plugin_id=PID, limits=None, only_pending=True, exclude_episodes=True)
check(len(_on["names"]) == 8, f"处理单集=开：8 条人名（剧 2 + 3 集 × 2）：{len(_on['names'])}")
check(len(_off["names"]) == 2
      and all(r["episode_num"] is None for r in _off["names"]),
      f"处理单集=关：只剩剧级 2 条（Episode 被排除）：{len(_off['names'])}")
_occ_on = pdb.force_item_occurrences(plugin_id=PID, item_id=SERIES, server_id=S1,
                                    limits=None, only_pending=True, exclude_episodes=False)
_occ_off = pdb.force_item_occurrences(plugin_id=PID, item_id=SERIES, server_id=S1,
                                     limits=None, only_pending=True, exclude_episodes=True)
check(len(_occ_on["names"]) == 8, f"开：单条目 occurrence 含各集 8 条：{len(_occ_on['names'])}")
check(len(_occ_off["names"]) == 2 and all(o["episode_num"] is None for o in _occ_off["names"]),
      f"关：单条目 occurrence 只剩剧级 2 条：{len(_occ_off['names'])}")
check(len(_occ_on["roles"]) == 0, "（播种无角色名，role 恒 0）")

# ─────────────────────────────────────────────
print("\n[T2] 单条目 / 写回就绪 门禁")
# ─────────────────────────────────────────────
_t_on = pdb.force_item_terms(plugin_id=PID, item_id=SERIES, server_id=S1,
                             limits=None, only_pending=True, exclude_episodes=False)
_t_off = pdb.force_item_terms(plugin_id=PID, item_id=SERIES, server_id=S1,
                              limits=None, only_pending=True, exclude_episodes=True)
check(len(_t_on["names"]) > len(_t_off["names"]) and len(_t_off["names"]) == 2,
      f"force_item_terms：开 {len(_t_on['names'])} > 关 {len(_t_off['names'])}")
_pt_on = pdb.pending_terms_of_item(plugin_id=PID, item_id=SERIES, server_id=S1, exclude_episodes=False)
_pt_off = pdb.pending_terms_of_item(plugin_id=PID, item_id=SERIES, server_id=S1, exclude_episodes=True)
check(not any(x["kind"] == "name" and x["term"] == "Guest One" for x in _pt_off),
      "写回就绪：关时集级客串「Guest One」不算待翻（否则写回永不就绪）")
check(any(x["term"] == "Guest One" for x in _pt_on), "开时该客串计入待翻")
_fp_on = pdb.find_pending_items(plugin_id=PID, exclude_episodes=False)
_fp_off = pdb.find_pending_items(plugin_id=PID, exclude_episodes=True)
check(len(_fp_on) == 1 and len(_fp_off) == 1, "同 item_id 去重后均为 1 个条目（剧=集共享 item_id）")
check(_fp_off and _fp_off[0]["item_type"] == "Series",
      f"关时条目级类型取值为 Series（非 Episode）：{_fp_off[0]['item_type'] if _fp_off else '-'}")

# ─────────────────────────────────────────────
print("\n[T3] 库页条目统计门禁（pending_items_count / pending_items_list）")
# ─────────────────────────────────────────────
_c_on = pdb.pending_items_count(plugin_id=PID, exclude_episodes=False)
_c_off = pdb.pending_items_count(plugin_id=PID, exclude_episodes=True)
check(_c_on == 1 and _c_off == 1, f"条目维度（同 item_id）开关均 1：开 {_c_on} / 关 {_c_off}")
_l_off = pdb.pending_items_list(plugin_id=PID, exclude_episodes=True)
check(len(_l_off) == 1, f"详情列表关时 1 条：{len(_l_off)}")

# ─────────────────────────────────────────────
print("\n[T4] 插件层 _tx_occurrences（翻译词条唯一来源）门禁")
# ─────────────────────────────────────────────
p = make_plugin(pdb)
p._nfo_include_episodes = True
_oc_on = p._tx_occurrences(PID, item_id=SERIES, server_id=S1)
p._nfo_include_episodes = False
_oc_off = p._tx_occurrences(PID, item_id=SERIES, server_id=S1)
check(len(_oc_on) == 8, f"处理单集=开：worker 收到 8 条词条：{len(_oc_on)}")
check(len(_oc_off) == 2 and all(o["episode_num"] is None for o in _oc_off),
      f"处理单集=关：worker 只收到剧级 2 条（不进入 AI）：{len(_oc_off)}")
check(p._tx_exclude_episodes() is True and _mk_cls("EPL68X")()._tx_exclude_episodes() is True,
      "_tx_exclude_episodes()：未设 flag 默认 True（关）")

# ─────────────────────────────────────────────
print("\n[T5] 入库不受门禁影响（Episode 行照常入库）")
# ─────────────────────────────────────────────
_r = dbm._q1("SELECT COUNT(*) c FROM person WHERE plugin_id=? AND item_type='Episode'", (PID,))
check(int((_r or {}).get("c") or 0) == 6, f"Episode 行仍在库中（3 集 × 2 人 = 6）：{(_r or {}).get('c')}")
check(pdb.library_items_page(plugin_id=PID, scan_mode="nfo")[1] == 1,
      "库页仍能看到该剧（剧级行存在，Episode 行只作明细展示）")

# ─────────────────────────────────────────────
print("\n[T6] scan_mode 来源判定改用 nfo_path（Webhook 行带真实 server_id 不再被误排除）")
# ─────────────────────────────────────────────
# 剧级行与集行都带真实 server_id + nfo_path（P0-1 后 Webhook 就是这样入库的）
_pend_nfo = pdb.pending_terms(plugin_id=PID, scan_mode="nfo", exclude_episodes=True)
check(len(_pend_nfo["names"]) > 0,
      f"scan_mode=nfo 仍能取到带真实 server_id 的本地 nfo 条目：{len(_pend_nfo['names'])}")
_pend_api = pdb.pending_terms(plugin_id=PID, scan_mode="api", exclude_episodes=True)
check(len(_pend_api["names"]) == 0, "scan_mode=api 不含本地 nfo 条目（0）")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
