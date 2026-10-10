# -*- coding: utf-8 -*-
"""v4.6.74 回归测试：P0 角色跨作品隔离 + 人名改名作用域 + 统计拆分。

运行：python tests/test_v474_role_isolation_name_scope.py

对应复查报告：
  测试 4：全局聚合下 A 剧 Guard / B 剧 Guard 必须是两个独立翻译项（去重键含作品身份）
  测试 3：不同作品同名角色两个译文可并存（互不串译）
  测试 1/2：同剧跨集仍可合并（E01/E02/E03 Guard → 1 条）；同批次去重仍生效
  测试 12：两个同名真人 —— 修改其中一个，默认不得把另一个一起改
  第六 / 二十三节：统计拆分（角色 Memory / 人名池 / TMDB / 繁转简 / LLM / LLM 输出简体化）
  第二十一节：强制重翻必须绕过记忆，且重翻后刷新角色记忆

覆盖：
  T1 _tx_work_id：series_media_id 优先 / 退化 item_id
  T2 角色批内去重按作品隔离（A 剧 + B 剧 → 2 条；同剧 3 集 → 1 条）
  T3 结果扇出只在同作品内（A 得守护者 / B 得守门人，不互串）
  T4 人名（第一排）保持全局合并（跨作品同名 → 1 条）
  T5 角色不读全局池 + 写回不回退角色全局池（源码级）
  T6 统计拆分：_kind_stat 产出 role_mem / tmdb；通知每项一行
  T7 强制重翻刷新角色记忆 + 返回 by_kind（源码级）
  T8 人名改名作用域（真实 SQLite）：single 只改一条 / series 只改该作品 / library 全库
  T9 源码级：局部改名不写全局人名池（防跨作品误改）
  T10 已交付项核验：删除不清角色记忆 / 人工(memory) 优先 / 强制重翻在记忆查询前返回
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
TMP = Path(tempfile.mkdtemp(prefix="epl74_"))
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

_spec = importlib.util.spec_from_file_location("epl_db74", PLUGIN_DIR / "db.py")
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

def _mk_cls(cls_name, methods, extra=None):
    ns = {
        "logger": logger, "re": re, "os": os, "Any": Any, "List": List,
        "Optional": Optional, "Dict": Dict, "tuple": tuple, "set": set,
        "int": int, "str": str, "bool": bool, "len": len, "max": max, "min": min,
        "sorted": sorted, "list": list, "dict": dict, "Exception": Exception,
    }
    if extra:
        ns.update(extra)
    src = f"class {cls_name}:\n    TX_BATCH = 30\n    TX_BATCH_MIN = 1\n" + "\n".join(_grab(n) for n in methods)
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
PID = "EPL74"

class _CountLLM:
    def __init__(self, resp_fn):
        self.calls = []
        self._fn = resp_fn
    def translate_items(self, items, **k):
        self.calls.append([(it["id"], it["text"]) for it in items])
        return self._fn(items)

def _plugin(resp_fn):
    p = _mk_cls("EPL74P", ["_tx_occ_id", "_tx_work_id", "_tx_llm_chunks"])()
    p._llm = _CountLLM(resp_fn)
    p._tx_batch = 30
    p._tx_batch_max = 30
    p._tx_job_id = ""
    p._failed_terms = set()
    p._failed_terms_detail = {}
    p._rl_ok = lambda: None
    p._tx_stop_requested = lambda: False
    p._ai_enabled = lambda: True
    p._zhconv_convert = lambda t: t     # 本测试不涉繁简，恒等即可
    return p

def _occ(oid, text, kind, item_id, server_id=S1, title="", smid=None):
    o = {"occ_id": oid, "text": text, "kind": kind, "item_id": item_id,
         "server_id": server_id, "title": title, "person_index": 0}
    if smid is not None:
        o["series_media_id"] = smid
    return o

print("=" * 72)
print("v4.6.74 回归测试（角色跨作品隔离 / 人名改名作用域 / 统计拆分）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] _tx_work_id：series_media_id 优先 / 退化 item_id")
# ─────────────────────────────────────────────
W = _mk_cls("EPL74W", ["_tx_work_id"])
check(W._tx_work_id({"series_media_id": "tmdb:111", "item_id": "tmdb:111"}) == "tmdb:111",
      "series_media_id 优先（与 item_id 同值时一致）")
check(W._tx_work_id({"item_id": "tvdb:9"}) == "tvdb:9", "无 series_media_id → 用 item_id")
check(W._tx_work_id({}) == "", "两者皆空 → 空串")

# ─────────────────────────────────────────────
print("\n[T2] 角色批内去重按「作品」隔离（测试 4）")
# ─────────────────────────────────────────────
p = _plugin(lambda items: {it["id"]: f"译[{it['text']}]" for it in items})
occs = [
    # A 剧（item=tvdb:A）三集同一角色 → 应合并成 1 条
    _occ("a1", "Guard", "role", "tvdb:A", title="A剧"),
    _occ("a2", "Guard", "role", "tvdb:A", title="A剧"),
    _occ("a3", "Guard", "role", "tvdb:A", title="A剧"),
    # B 剧（item=tvdb:B）同角色原文 → 必须独立成条
    _occ("b1", "Guard", "role", "tvdb:B", title="B剧"),
]
_r = p._tx_llm_chunks(occs)
_sent = p._llm.calls[0]
check(len(_sent) == 2, f"全局聚合：A 剧 3 条合并 + B 剧独立 = 送 LLM 2 条（实际 {len(_sent)}）")
check(sorted(x[0] for x in _sent) == ["a1", "b1"],
      f"送 LLM 的代表 occurrence = a1 + b1（实际 {[x[0] for x in _sent]}）")
check(len(_r["llm"]) == 4, f"结果扇出到全部 4 个 occurrence（实际 {len(_r['llm'])}）")
check(_r["llm"].get("a2") == _r["llm"].get("a3") == _r["llm"].get("a1"),
      "A 剧三集得到同一译文（同作品跨集合并）")

# ─────────────────────────────────────────────
print("\n[T3] 不同作品同名角色可并存、绝不互相扇出（测试 3）")
# ─────────────────────────────────────────────
def _resp(items):
    # 故意让 A 剧与 B 剧得到不同译文（模拟不同作品不同角色语义）
    return {it["id"]: ("守护者" if it["id"] == "a1" else "守门人") for it in items}
p2 = _plugin(_resp)
_r2 = p2._tx_llm_chunks([
    _occ("a1", "Guardian", "role", "tvdb:A", title="A剧"),
    _occ("b1", "Guardian", "role", "tvdb:B", title="B剧"),
])
check(_r2["llm"].get("a1") == "守护者" and _r2["llm"].get("b1") == "守门人",
      f"A=守护者 / B=守门人 并存（实际 {_r2['llm']}）")
check(_r2["llm"].get("a1") != _r2["llm"].get("b1"),
      "A 剧结果没有被扇出覆盖 B 剧（此前 P0：两者会变成同一译文）")

# 同剧同角色不同集 + 不同季/序号：仍合并
p3 = _plugin(lambda items: {it["id"]: "黑暗骑士" for it in items})
_o1 = _occ("e1", "Dark Knight", "role", "tmdb:100", title="剧")
_o1["season_num"], _o1["episode_num"] = 1, 1
_o2 = _occ("e2", "Dark Knight", "role", "tmdb:100", title="剧")
_o2["season_num"], _o2["episode_num"] = 1, 5
_r3 = p3._tx_llm_chunks([_o1, _o2])
check(len(p3._llm.calls[0]) == 1 and _r3["llm"].get("e2") == "黑暗骑士",
      "同一部剧 E01/E05 同一角色 → 只发 1 条并扇出（跨集复用）")

# ─────────────────────────────────────────────
print("\n[T4] 人名（第一排）保持全局合并")
# ─────────────────────────────────────────────
p4 = _plugin(lambda items: {it["id"]: "汤姆·汉克斯" for it in items})
_r4 = p4._tx_llm_chunks([
    _occ("n1", "Tom Hanks", "person", "tvdb:A", title="A剧"),
    _occ("n2", "Tom Hanks", "person", "tvdb:B", title="B剧"),
])
check(len(p4._llm.calls[0]) == 1 and _r4["llm"].get("n2") == "汤姆·汉克斯",
      "人名跨作品同一原文仍合并为 1 条（第一排全局人名设计不变）")

# ─────────────────────────────────────────────
print("\n[T5] 角色不读全局池 / 写回不回退角色全局池（源码级）")
# ─────────────────────────────────────────────
_mx = _grab("_tx_translate_mixed")
check('_hit = None if _k == "role" else (pool_lu or {}).get((_k, _t))' in _mx,
      "翻译阶段：角色不查全局池（只认同剧记忆 / LLM）")
_lk = _grab("_restore_nfo_from_db_locked")
check('_pool.get(("role"' not in _lk, "写回阶段：角色不再回退全局池（防写错另一部作品的译文）")
check('_pool.get(("person"' in _lk, "写回阶段：人名仍保留全局池回退（第一排设计）")

# ─────────────────────────────────────────────
print("\n[T6] 统计拆分（角色 Memory / 人名池 / TMDB / 繁转简）")
# ─────────────────────────────────────────────
_tpr = _grab("_translate_pending_round")
check('_s == "series"' in _tpr and '_mem += 1' in _tpr,
      "_kind_stat：同剧角色记忆（source=series）独立计数")
check('"_tmdb"' in _tpr or "_tmdb += 1" in _tpr, "_kind_stat：TMDB 命中独立计数")
check('"role_mem": _mem, "tmdb": _tmdb' in _tpr, "by_kind 输出 role_mem / tmdb 字段")
check("角色 Memory：" in _SRC and "人名池：" in _SRC and "TMDB：" in _SRC
      and "繁转简：" in _SRC and "LLM 输出简体化：" in _SRC,
      "完成通知每项一行（LLM / 角色 Memory / 人名池 / TMDB / 繁转简 / LLM 输出简体化）")

# ─────────────────────────────────────────────
print("\n[T7] 强制重翻：绕过记忆 + 重翻后刷新角色记忆 + 分排统计（源码级）")
# ─────────────────────────────────────────────
_round = _grab("_translate_pending_round")
check(_round.find("if _scope_items:") < _round.find("role_memory_get"),
      "条目级重翻（force）在记忆查询之前提前返回 → 强制重翻必然绕过旧记忆（测试 6）")
_fr = _grab("_tx_force_round")
check("role_memory_put" in _fr, "强制重翻后刷新「同剧角色记忆」（重翻结果覆盖旧记忆）")
check('"by_kind": _bk_f' in _fr, "强制重翻返回分排统计（通知不再恒显示 0）")
check("_tx_translate_mixed(_occs, {}" in _fr, "强制重翻池查表传空 → 不复用池命中")

# ─────────────────────────────────────────────
print("\n[T8] 人名改名作用域（真实 SQLite · 测试 12）")
# ─────────────────────────────────────────────
# A 作品：John Smith（E01 + E02 两条）；B 作品：John Smith（另一部作品/另一个真人）
pdb.upsert_people(plugin_id=PID, server_id=S1, item_id="tmdb:A", item_type="Episode",
                  title="A作品", series_name="A作品", season_num=1, episode_num=1,
                  nfo_path="X:/a/S01E01.nfo",
                  people=[{"before_name": "John Smith", "Name": "John Smith",
                           "before_role": "", "Role": ""}])
pdb.upsert_people(plugin_id=PID, server_id=S1, item_id="tmdb:A", item_type="Episode",
                  title="A作品", series_name="A作品", season_num=1, episode_num=2,
                  nfo_path="X:/a/S01E02.nfo",
                  people=[{"before_name": "John Smith", "Name": "John Smith",
                           "before_role": "", "Role": ""}])
pdb.upsert_people(plugin_id=PID, server_id=S1, item_id="tmdb:B", item_type="Movie",
                  title="B作品", season_num=None, episode_num=None,
                  nfo_path="X:/b/movie.nfo",
                  people=[{"before_name": "John Smith", "Name": "John Smith",
                           "before_role": "", "Role": ""}])

def _name_of(item, s, e):
    r = dbm._q1("SELECT name_after FROM person WHERE plugin_id=? AND item_id=? "
                "AND season_num IS ? AND episode_num IS ? AND name_before='John Smith'",
                (PID, item, s, e))
    return str((r or {}).get("name_after") or "")

# ① 默认 single：只改 A 作品 E01 那一条
_n = pdb.update_name_by_scope(plugin_id=PID, name_before="John Smith", name_after="约翰·史密斯",
                              server_id=S1, item_id="tmdb:A", season_num=1, episode_num=1,
                              index=0, scope="single")
check(_n == 1 and _name_of("tmdb:A", 1, 1) == "约翰·史密斯",
      f"single：只改当前这一条（改动 {_n} 行）")
check(_name_of("tmdb:A", 1, 2) == "John Smith", "single：同作品另一集未被改动")
check(_name_of("tmdb:B", None, None) == "John Smith",
      "single：另一部作品的同名人物未被改动（测试 12 核心）")

# ② series：改该作品全部集
_n2 = pdb.update_name_by_scope(plugin_id=PID, name_before="John Smith", name_after="约翰",
                               server_id=S1, item_id="tmdb:A", scope="series")
check(_n2 == 2 and _name_of("tmdb:A", 1, 1) == "约翰" and _name_of("tmdb:A", 1, 2) == "约翰",
      f"series：该作品内全部集一起改（改动 {_n2} 行）")
check(_name_of("tmdb:B", None, None) == "John Smith", "series：不影响其它作品")

# ③ library：用户主动选择才全库（name_before 是原文，A 的两条 + B 一条都命中）
_n3 = pdb.update_name_by_scope(plugin_id=PID, name_before="John Smith", name_after="约翰·史密",
                               scope="library")
check(_n3 == 3 and _name_of("tmdb:B", None, None) == "约翰·史密",
      f"library：显式全库同名覆盖全部同名行（改动 {_n3} 行，含另一部作品）")

# ─────────────────────────────────────────────
print("\n[T9] 局部改名不写全局人名池（源码级 · 防跨作品误改）")
# ─────────────────────────────────────────────
_ups = _grab("_api_db_update_person_scope")
check('if _name_changed and name_scope == "library":' in _ups,
      "只有 name_scope=library 才写全局人名池（single/series 不写）")
check("update_name_by_scope(" in _ups, "人名改走 update_name_by_scope（按范围）")
check('name_scope = str(data.get("name_scope")' in _ups and 'name_scope = "single"' in _ups,
      "name_scope 默认 single（后端兜底，不依赖前端）")

# ─────────────────────────────────────────────
print("\n[T10] 已交付项核验（记忆不因删除而清 / 人工优先 / 记忆隔离）")
# ─────────────────────────────────────────────
pdb.role_memory_put(plugin_id=PID, rows=[
    {"server_id": S1, "series_id": "tmdb:A", "series_name": "A作品",
     "role_original": "Guard", "role_translated": "守护者", "source": "llm"},
    {"server_id": S1, "series_id": "tmdb:B", "series_name": "B作品",
     "role_original": "Guard", "role_translated": "守门人", "source": "llm"}])
_m = pdb.role_memory_get(plugin_id=PID, keys=[(S1, "tmdb:A", "Guard"),
                                             (S1, "tmdb:B", "Guard")])
check(_m.get((S1, "tmdb:A", "Guard"))[0] == "守护者"
      and _m.get((S1, "tmdb:B", "Guard"))[0] == "守门人",
      "同角色原文在两部作品各自有译文（记忆按作品隔离）")
_before = pdb.role_memory_stats(plugin_id=PID)["total"]
pdb.upsert_people(plugin_id=PID, server_id=S1, item_id="tmdb:A", item_type="Episode",
                  title="A作品", series_name="A作品", season_num=9, episode_num=9,
                  nfo_path="X:/a/S09E09.nfo",
                  people=[{"before_name": "X", "Name": "X"}])
pdb.mark_deleted_by_nfo_path(plugin_id=PID, nfo_path="X:/a/S09E09.nfo", server_id=S1)
pdb.delete_item(plugin_id=PID, item_id="tmdb:A", server_id=S1)
check(pdb.role_memory_stats(plugin_id=PID)["total"] == _before,
      "删除集 / 删除条目都不清角色记忆（洗版重建仍可复用）")
pdb.role_memory_put(plugin_id=PID, rows=[
    {"server_id": S1, "series_id": "tmdb:A", "series_name": "A作品",
     "role_original": "Guard", "role_translated": "守卫者", "source": "manual"}])
_mm = pdb.role_memory_get(plugin_id=PID, keys=[(S1, "tmdb:A", "Guard")]).get((S1, "tmdb:A", "Guard"))
check(_mm is not None and _mm[0] == "守卫者",
      f"人工（manual）可覆盖 AI 结果（实际 {_mm}）")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)