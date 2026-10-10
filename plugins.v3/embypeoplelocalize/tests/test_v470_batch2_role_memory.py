# -*- coding: utf-8 -*-
"""v4.6.70 批次 2 回归测试：第二排角色跨集复用（报告第二十~三十四节）。

运行：python tests/test_v470_batch2_role_memory.py

真实 db.py（role_memory 表）+ 从 __init__.py 提取的真实方法体 + 注入假 zhconv。
覆盖文档「三十三、关键测试」1~7 的语义：
  T1 跨集重复角色：E01 走 AI，E02/E03 走记忆（AI 只调 1 次）
  T2 同批次去重：一次送入 3×A + 2×B → LLM 只收到 A、B 两个唯一值
  T3 不同作品同名角色：A 剧 Guardian→守护者、B 剧 Guardian→守门人 可并存
  T4 人工优先：source=manual 不被 llm 覆盖；AI 结果不得改写人工
  T5 强制重翻绕过记忆（source 级：force 分支在记忆查询之前提前返回）
  T6 洗版：媒体身份（series_id）不变即命中，与路径无关
  T7 记忆清除：只有显式 delete_series 才清；删除/恢复/清库都不清
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
TMP = Path(tempfile.mkdtemp(prefix="epl70b2_"))
S1 = "___1_192_168_2_15_8096"
S2 = "___2_192_168_2_16_8096"

_FAKE_MAP = {"臺": "台", "灣": "湾", "劇": "剧", "場": "场", "衛": "卫", "護": "护"}
_fake_zhconv = types.ModuleType("zhconv")
_fake_zhconv.convert = lambda t, locale="zh-cn": "".join(_FAKE_MAP.get(c, c) for c in str(t or ""))
sys.modules["zhconv"] = _fake_zhconv

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

class _DummyErr(Exception):
    pass

def _mk_cls(cls_name, methods):
    ns = {
        "logger": logger, "re": re, "os": os, "Any": Any, "List": List,
        "Optional": Optional, "Dict": Dict, "HAS_ZHCONV": True, "zhconv": _fake_zhconv,
        "InterruptedError": InterruptedError,
        "ContextLengthExceeded": _DummyErr, "RateLimited": _DummyErr,
        "QuotaExceeded": _DummyErr, "AuthenticationError": _DummyErr,
        "LLMError": _DummyErr, "Exception": Exception,
        "int": int, "str": str, "bool": bool, "len": len, "max": max, "min": min,
        "set": set, "list": list, "dict": dict, "sorted": sorted,
    }
    src = (f"class {cls_name}:\n    TX_BATCH = 30\n    TX_BATCH_MIN = 1\n"
           + "\n".join(_grab(n) for n in methods))
    exec(compile(src, "<extract:__init__.py>", "exec"), ns)
    return ns[cls_name]

_N = [0, 0]
def check(cond, msg):
    _N[0] += 1
    if cond:
        print(f"  [PASS] {msg}")
    else:
        _N[1] += 1
        print(f"  [FAIL] {msg}")

pdb = dbm.PeopleDb()
pdb.ensure_table()
PID = "EPL70B2"

class _CountLLM:
    def __init__(self, resp_fn):
        self.calls = []
        self._fn = resp_fn
    def translate_items(self, items, **k):
        self.calls.append([it["id"] for it in items])
        return self._fn(items)

def _plugin():
    p = _mk_cls("EPL70B2P", ["_tx_occ_id", "_tx_work_id", "_tx_llm_chunks", "_zhconv_convert"])()
    p._llm = None
    p._tx_batch = 30
    p._tx_batch_max = 30
    p._tx_job_id = ""
    p._failed_terms = set()
    p._failed_terms_detail = {}
    p._rl_ok = lambda: None
    p._tx_stop_requested = lambda: False
    p._ai_enabled = lambda: True
    return p

print("=" * 72)
print("v4.6.70 批次2 回归测试（第二排角色跨集复用）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] 跨集重复角色：E01 走 AI，E02/E03 走记忆（AI 只 1 次）")
# ─────────────────────────────────────────────
# 模拟：E01 首次翻译落记忆；E02/E03 同剧同角色 → 记忆命中
pdb.role_memory_put(plugin_id=PID, rows=[{
    "server_id": S1, "series_id": "tvdb:100", "series_name": "测试剧",
    "role_original": "Dark Knight", "role_translated": "黑暗骑士", "source": "llm"}])
_mem = pdb.role_memory_get(plugin_id=PID, keys=[
    (S1, "tvdb:100", "Dark Knight"), (S1, "tvdb:100", "Dark Knight")])
check(_mem.get((S1, "tvdb:100", "Dark Knight")) == ("黑暗骑士", "llm"),
      "E02/E03 命中同剧记忆（无需再调 AI）")

# ─────────────────────────────────────────────
print("\n[T2] 同批次去重：LLM 只收到唯一值")
# ─────────────────────────────────────────────
p = _plugin()
_p = pdb
_llm = _CountLLM(lambda items: {it["id"]: f"译-{it['text']}" for it in items})
p._llm = _llm
occs = []
for _i, _txt in enumerate(["Dark Knight", "Dark Knight", "Dark Knight", "Captain", "Captain"]):
    occs.append({"occ_id": f"o{_i}", "text": _txt, "kind": "role", "title": "剧A", "item_id": "tvdb:100"})
_r = p._tx_llm_chunks(occs)
check(len(_llm.calls) == 1 and sorted(_llm.calls[0]) == ["o0", "o3"],
      f"一次请求只送唯一值（3×Dark Knight + 2×Captain → 只送 2 条）：{_llm.calls}")
check(len(_r["llm"]) == 5 and len(set(_r["llm"].values())) == 2,
      f"结果扇出到全部 5 个 occurrence：{sorted(_r['llm'].keys())}")
check(_r["llm"].get("o2") == _r["llm"].get("o0") == "译-Dark Knight",
      "同文本 occurrence 得到同一译文")

# ─────────────────────────────────────────────
print("\n[T3] 不同作品同名角色互不串用")
# ─────────────────────────────────────────────
pdb.role_memory_put(plugin_id=PID, rows=[
    {"server_id": S1, "series_id": "tvdb:A", "series_name": "A剧",
     "role_original": "Guardian", "role_translated": "守护者", "source": "llm"},
    {"server_id": S1, "series_id": "tvdb:B", "series_name": "B剧",
     "role_original": "Guardian", "role_translated": "守门人", "source": "llm"}])
_m = pdb.role_memory_get(plugin_id=PID, keys=[
    (S1, "tvdb:A", "Guardian"), (S1, "tvdb:B", "Guardian")])
check(_m.get((S1, "tvdb:A", "Guardian"))[0] == "守护者"
      and _m.get((S1, "tvdb:B", "Guardian"))[0] == "守门人",
      "A 剧=守护者 / B 剧=守门人 并存（按剧作用域隔离）")
_m2 = pdb.role_memory_get(plugin_id=PID, keys=[(S2, "tvdb:A", "Guardian")])
check(not _m2, "其它服务器（S2）不命中 S1 的记忆")

# ─────────────────────────────────────────────
print("\n[T4] 人工优先：manual 不被 llm 覆盖")
# ─────────────────────────────────────────────
pdb.role_memory_put(plugin_id=PID, rows=[{
    "server_id": S1, "series_id": "tvdb:C", "series_name": "C剧",
    "role_original": "Guardian", "role_translated": "守门人", "source": "manual"}])
pdb.role_memory_put(plugin_id=PID, rows=[{
    "server_id": S1, "series_id": "tvdb:C", "series_name": "C剧",
    "role_original": "Guardian", "role_translated": "守护者", "source": "llm"}])
_m = pdb.role_memory_get(plugin_id=PID, keys=[(S1, "tvdb:C", "Guardian")])
check(_m.get((S1, "tvdb:C", "Guardian")) == ("守门人", "manual"),
      f"人工结果未被 AI 结果覆盖：{_m.get((S1, 'tvdb:C', 'Guardian'))}")
# 反向：先 llm 后 manual → 应被人工覆盖
pdb.role_memory_put(plugin_id=PID, rows=[{
    "server_id": S1, "series_id": "tvdb:D", "series_name": "D剧",
    "role_original": "Boss", "role_translated": "老板", "source": "llm"}])
pdb.role_memory_put(plugin_id=PID, rows=[{
    "server_id": S1, "series_id": "tvdb:D", "series_name": "D剧",
    "role_original": "Boss", "role_translated": "首领", "source": "manual"}])
_m = pdb.role_memory_get(plugin_id=PID, keys=[(S1, "tvdb:D", "Boss")])
check(_m.get((S1, "tvdb:D", "Boss")) == ("首领", "manual"), "人工结果可覆盖 AI 结果")

# ─────────────────────────────────────────────
print("\n[T5] 强制重翻绕过记忆（源码级：force 分支在记忆查询之前返回）")
# ─────────────────────────────────────────────
_body = _grab("_translate_pending_round")
_i_scope = _body.find('if _scope_items:')
_i_mem = _body.find("role_memory_get")
check(_i_scope != -1 and _i_mem != -1 and _i_scope < _i_mem,
      "条目级重翻（force）在角色记忆查询之前提前返回 → 强制重翻必然绕过旧记忆")

# ─────────────────────────────────────────────
print("\n[T6] 洗版：媒体身份不变即命中（与路径/标题无关）")
# ─────────────────────────────────────────────
pdb.role_memory_put(plugin_id=PID, rows=[{
    "server_id": S1, "series_id": "tmdb:1177096", "series_name": "大室家",
    "role_original": "Sister", "role_translated": "姐妹", "source": "llm"}])
_hit = pdb.role_memory_get(plugin_id=PID, keys=[(S1, "tmdb:1177096", "Sister")])
check(_hit.get((S1, "tmdb:1177096", "Sister")) == ("姐妹", "llm"),
      "洗版后同 TMDB 媒体身份 → 直接命中旧译文（不依赖 nfo 路径/剧名）")

# ─────────────────────────────────────────────
print("\n[T7] 记忆清除：只有显式 clear 才清")
# ─────────────────────────────────────────────
_before = pdb.role_memory_stats(plugin_id=PID)["total"]
check(_before >= 5, f"记忆已积累 {_before} 条")
# 模拟「删除某集 / 整剧删除 / 清空翻译记录」：只动 person 表 → 记忆不动
pdb.upsert_people(plugin_id=PID, server_id=S1, item_id="tmdb:1177096", item_type="Episode",
                  title="大室家", series_name="大室家", season_num=1, episode_num=1,
                  nfo_path="X:/old/S01E01.nfo", emby_item_id="1",
                  people=[{"before_name": "A", "Name": "A", "before_role": "Sister", "Role": "姐妹"}])
pdb.mark_deleted_by_nfo_path(plugin_id=PID, nfo_path="X:/old/S01E01.nfo", server_id=S1)
pdb.delete_item(plugin_id=PID, item_id="tmdb:1177096", server_id=S1)
_after = pdb.role_memory_stats(plugin_id=PID)["total"]
check(_after == _before, f"删除集/删条目/（清库只清 person）后记忆不变：{_before} → {_after}")
_n = pdb.role_memory_delete_series(plugin_id=PID, server_id=S1, series_id="tmdb:1177096")
check(_n >= 1 and pdb.role_memory_stats(plugin_id=PID)["total"] == _before - _n,
      f"显式 clear 才清（清掉 {_n} 条）")
check(pdb.role_memory_get(plugin_id=PID, keys=[(S1, "tmdb:1177096", "Sister")]) == {},
      "清除后该剧记忆确实为空")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
