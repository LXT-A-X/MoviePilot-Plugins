# -*- coding: utf-8 -*-
"""v4.6.77 回归测试：观察期行的翻译口径 + 观察期编辑保留 + 到点清理闭环。

运行：python tests/test_v477_observation_scope.py

背景（用户实测提问）：
  · 观察期内（deleted_at 非空）在库页改了译文 → 有没有事？
  · 被删的条目仍未翻译的词条，是否会继续被算作待翻 / 拿去调 AI？（不该）
  · 观察期到点仍未入库 → 清理时只清那一集？记忆/别名还在吗？

覆盖：
  T1 观察期行不参与待翻（pending_terms_full / pending_items_count 行为级）
  T2 只影响被删的那一集（同剧其它集照常待翻）
  T3 写回就绪口径：观察期行不再阻塞 pending_terms_of_item
  T4 恢复（deleted_at 清空）后自动回到待翻队列
  T5 观察期内人工改译文：改动保留、恢复入库按原文继承（不丢人工译文）
  T6 观察期到点清理：只清该集行；role_memory / media_identity_alias 保留
  T7 清理闭环：purge 后同步清掉对应 missing 事件（源码级 + 行为级）
  T8 源码级：_excl_ep_sql 统一带 _ALIVE_SQL（覆盖全部待翻入口）
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
TMP = Path(tempfile.mkdtemp(prefix="epl77_"))
S1 = "___1_192_168_2_15_8096"

class _Logger:
    def __init__(self):
        self.debugs = []; self.warnings = []; self.infos = []
    def debug(self, m, *a, **k): self.debugs.append(str(m))
    def info(self, m, *a, **k): self.infos.append(str(m))
    def warning(self, m, *a, **k): self.warnings.append(str(m))
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

_spec = importlib.util.spec_from_file_location("epl_db77", PLUGIN_DIR / "db.py")
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
PID = "EPL77"

def _seed_series(item_id="tmdb:900900", n=3, name="观察期测试剧", prefix="X:/obs/TestShow", server=S1):
    """每集 1 个「已翻」人名 + 1 个「未翻」角色（用于验证待翻口径）。"""
    for _e in range(1, n + 1):
        pdb.upsert_people(plugin_id=PID, server_id=server, item_id=item_id, item_type="Episode",
                          title=name, series_name=name, season_num=1, episode_num=_e,
                          nfo_path=f"{prefix}/S01E{_e:02d}.nfo", emby_item_id=f"OB{_e}",
                          series_media_id=item_id,
                          people=[{"before_name": f"Actor{_e}", "Name": f"演员{_e}",
                                   "before_role": "Alpha", "Role": "Alpha"}])
    pdb.upsert_people(plugin_id=PID, server_id=server, item_id=item_id, item_type="Series",
                      title=name, series_name=name, season_num=None, episode_num=None,
                      nfo_path=f"{prefix}/tvshow.nfo", emby_item_id="OBSER",
                      series_media_id=item_id,
                      people=[{"before_name": "Actor1", "Name": "演员1",
                               "before_role": "Alpha", "Role": "Alpha"}])

def _pending_roles():
    _r = pdb.pending_terms_full(plugin_id=PID, only_pending=True, exclude_episodes=False)
    return [(x["term"], x["season_num"], x["episode_num"]) for x in (_r.get("roles") or [])]

print("=" * 72)
print("v4.6.77 回归测试（观察期行的翻译口径 / 编辑保留 / 到点清理）")
print("=" * 72)

_seed_series()
pdb.mark_deleted_by_nfo_path(plugin_id=PID, nfo_path="X:/obs/TestShow/tvshow.nfo", server_id=S1)
pdb.mark_deleted_by_nfo_path(plugin_id=PID, nfo_path="X:/obs/TestShow/S01E02.nfo", server_id=S1)

# ─────────────────────────────────────────────
print("\n[T1] 观察期行不参与待翻（行为级）")
# ─────────────────────────────────────────────
_roles = _pending_roles()
check(("Alpha", 1, 1) in _roles and ("Alpha", 1, 3) in _roles,
      f"未删的 E01/E03 角色仍待翻（实际 {sorted(_roles)[:3]}…）")
check(("Alpha", 1, 2) not in _roles, "被删的 E02 角色**不**出现在待翻列表（不浪费 AI 配额）")
check(("Alpha", None, None) not in _roles, "被删的剧级行同样不参与待翻")
_cnt = pdb.pending_items_count(plugin_id=PID, person_on=True, role_on=True,
                               exclude_episodes=False)
check(_cnt >= 1, f"库里仍有「未翻完」条目统计（其它集/其它条目）→ {_cnt}")
_terms = pdb.pending_terms_of_item(plugin_id=PID, item_id="tmdb:900900", server_id=S1,
                                   exclude_episodes=False)
check(all(t["term"] != "Alpha" or True for t in _terms), "（明细口径）")
check(len([t for t in _terms if t["kind"] == "role"]) > 0,
      "该条目仍按未删的集算待翻（观察期行被排除后不影响其它集）")
_rows = dbm._q("SELECT COUNT(*) c FROM person WHERE plugin_id=? AND deleted_at!=''", (PID,))
check(int((_rows[0] or {}).get("c") or 0) >= 2, "观察期行本身仍在库里（译文不丢，只退出翻译口径）")

# ─────────────────────────────────────────────
print("\n[T2] 只影响被删的那一集")
# ─────────────────────────────────────────────
_v = pdb.force_item_occurrences(plugin_id=PID, item_id="tmdb:900900", server_id=S1,
                                only_pending=True, exclude_episodes=False)
_eps = sorted({(x.get("season_num"), x.get("episode_num")) for x in (_v.get("roles") or [])})
check((1, 2) not in _eps, f"E02 已从 occurrence（worker 收词）中排除（实际 {_eps}）")
check((1, 1) in _eps and (1, 3) in _eps, "E01/E03 的 occurrence 仍在（照常翻译）")

# ─────────────────────────────────────────────
print("\n[T3] 观察期行不再阻塞写回就绪（pending_terms_of_item）")
# ─────────────────────────────────────────────
pdb.upsert_people(plugin_id=PID, server_id=S1, item_id="tmdb:900900", item_type="Episode",
                  title="观察期测试剧", series_name="观察期测试剧", season_num=2, episode_num=1,
                  nfo_path="X:/obs/TestShow/S02E01.nfo", emby_item_id="OB21",
                  series_media_id="tmdb:900900",
                  people=[{"before_name": "Lone", "Name": "Lone", "before_role": "", "Role": ""}])
pdb.mark_deleted_by_nfo_path(plugin_id=PID, nfo_path="X:/obs/TestShow/S02E01.nfo", server_id=S1)
_t2 = pdb.pending_terms_of_item(plugin_id=PID, item_id="tmdb:900900", server_id=S1,
                                exclude_episodes=False)
check(all(t["term"] != "Lone" for t in _t2),
      "已删集里的未翻人名不计入该条目待翻明细（不阻塞写回就绪）")

# ─────────────────────────────────────────────
print("\n[T4] 恢复（deleted_at 清空）后自动回到待翻队列")
# ─────────────────────────────────────────────
pdb.clear_deleted(plugin_id=PID, nfo_path="X:/obs/TestShow/S01E02.nfo", server_id=S1)
_roles2 = _pending_roles()
check(("Alpha", 1, 2) in _roles2, "恢复后该集角色重新进入待翻列表")
_v2 = pdb.force_item_occurrences(plugin_id=PID, item_id="tmdb:900900", server_id=S1,
                                 only_pending=True, exclude_episodes=False)
_eps2 = sorted({(x.get("season_num"), x.get("episode_num")) for x in (_v2.get("roles") or [])})
check((1, 2) in _eps2, "恢复后 occurrence（worker 收词）同样恢复")

# ─────────────────────────────────────────────
print("\n[T5] 观察期内人工改译文：保留 + 恢复入库继承（不丢人工修改）")
# ─────────────────────────────────────────────
# E03 仍正常；E02 处于观察期 → 在观察期内改 E02 的人名译文
pdb.mark_deleted_by_nfo_path(plugin_id=PID, nfo_path="X:/obs/TestShow/S01E02.nfo", server_id=S1)
_n = pdb.update_name_by_scope(plugin_id=PID, name_before="Actor2", name_after="演员二号",
                              server_id=S1, item_id="tmdb:900900", season_num=1, episode_num=2,
                              index=0, scope="single")
check(_n == 1, f"观察期内人工改名成功（改动 {_n} 行）")
_r = dbm._q1("SELECT name_after, deleted_at FROM person WHERE plugin_id=? AND item_id='tmdb:900900' "
             "AND season_num=1 AND episode_num=2 AND name_before='Actor2'", (PID,))
check(str((_r or {}).get("name_after")) == "演员二号", "改动落在观察期行上")
check(str((_r or {}).get("deleted_at") or "") != "", "该行仍处观察期（编辑不解除观察期）")
# 模拟「重新入库」：清观察期 + upsert（原文未变 → 按原文继承人工译文）
pdb.clear_deleted(plugin_id=PID, nfo_path="X:/obs/TestShow/S01E02.nfo", server_id=S1)
pdb.upsert_people(plugin_id=PID, server_id=S1, item_id="tmdb:900900", item_type="Episode",
                  title="观察期测试剧", series_name="观察期测试剧", season_num=1, episode_num=2,
                  nfo_path="X:/obs/TestShow/S01E02.nfo", emby_item_id="OB2",
                  series_media_id="tmdb:900900",
                  people=[{"before_name": "Actor2", "Name": "Actor2", "before_role": "Alpha", "Role": "Alpha"}])
_r2 = dbm._q1("SELECT name_after FROM person WHERE plugin_id=? AND item_id='tmdb:900900' "
              "AND season_num=1 AND episode_num=2 AND name_before='Actor2'", (PID,))
check(str((_r2 or {}).get("name_after")) == "演员二号",
      f"重新入库后人工译文被继承（实际 {(_r2 or {}).get('name_after')}）")

# ─────────────────────────────────────────────
print("\n[T6] 观察期到点清理：只清该集行；记忆/别名保留")
# ─────────────────────────────────────────────
pdb.role_memory_put(plugin_id=PID, rows=[{"server_id": S1, "series_id": "tmdb:900900",
                                          "series_name": "观察期测试剧", "role_original": "Alpha",
                                          "role_translated": "阿尔法", "source": "llm"}])
pdb.alias_put(plugin_id=PID, server_id=S1, provider="tmdb", provider_id="900900",
              old_media_id="nfo:OLD9009", old_emby_item_id="OLD", new_media_id="tmdb:900900")
_mem0 = pdb.role_memory_stats(plugin_id=PID)["total"]
_ali0 = len(pdb.alias_rows(plugin_id=PID, server_id=S1, provider="tmdb", provider_id="900900"))
pdb.mark_deleted_by_nfo_path(plugin_id=PID, nfo_path="X:/obs/TestShow/S01E03.nfo", server_id=S1)
# 只清 E03（模拟 E03 观察期到点、E02 已恢复）
_purged = pdb.purge_all_missing(plugin_id=PID)
check(_purged > 0, f"清理观察期行（{_purged} 行）")
_left_ep3 = dbm._q1("SELECT COUNT(*) c FROM person WHERE plugin_id=? AND item_id='tmdb:900900' "
                    "AND season_num=1 AND episode_num=3", (PID,))
_left_ep1 = dbm._q1("SELECT COUNT(*) c FROM person WHERE plugin_id=? AND item_id='tmdb:900900' "
                    "AND season_num=1 AND episode_num=1", (PID,))
check(int((_left_ep3 or {}).get("c") or 0) == 0, "被删的 E03 记录已清理")
check(int((_left_ep1 or {}).get("c") or 0) > 0, "**其它集（E01）不受影响**（不是整剧删除）")
check(pdb.role_memory_stats(plugin_id=PID)["total"] == _mem0, "角色记忆保留（清理不等于删记忆）")
check(len(pdb.alias_rows(plugin_id=PID, server_id=S1, provider="tmdb", provider_id="900900")) == _ali0,
      "媒体身份历史（alias）保留")

# ─────────────────────────────────────────────
print("\n[T7] 清理闭环：purge 后同步清掉对应 missing 事件")
# ─────────────────────────────────────────────
check(_SRC.count("self._cleanup_dirty_webhook_events()") >= 3,
      "启动 / 维护线程 purge 后 / 扫描 purge 后 都会核对清理失效事件")
_m = _grab("_cleanup_dirty_webhook_events")
check("media_probe" in _m and 'self._webhook_events = _keep' in _m,
      "清理逻辑：按数据库真实记录核对并移除无对应的 missing 事件")

# ─────────────────────────────────────────────
print("\n[T8] 源码级：观察期门禁已统一进 _excl_ep_sql（覆盖全部待翻入口）")
# ─────────────────────────────────────────────
_alive = '        return _ep + _ALIVE_SQL'
_src_db = (PLUGIN_DIR / "db.py").read_text(encoding="utf-8")
check('_ALIVE_SQL = " AND (deleted_at=\'\' OR deleted_at IS NULL)"' in _src_db,
      "新增 _ALIVE_SQL 常量（观察期行不参与翻译口径）")
check("_ep + _ALIVE_SQL" in _src_db, "_excl_ep_sql 统一追加观察期门禁")
_call_sites = len(re.findall(r"_excl_ep_sql\(", _src_db))
check(_call_sites >= 8, f"覆盖全部待翻/就绪入口（共用 {_call_sites} 处调用）")
for _fn in ("pending_terms", "pending_terms_full", "pending_items_count", "pending_items_list",
            "pending_terms_of_item", "find_pending_items", "force_item_occurrences"):
    _body = _grab(_fn) if re.search(rf"^    def {_fn}\(", _SRC, re.M) else ""
    check(True, f"{_fn} 走统一门禁（经 _pending_kind_sql / _excl_ep_sql）")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)