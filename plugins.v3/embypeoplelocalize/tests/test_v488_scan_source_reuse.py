# -*- coding: utf-8 -*-
"""v4.6.88 回归测试：扫描路径复用已有 server_id —— 修「先 Webhook 入库、后扫描」重复。

运行：python tests/test_v488_scan_source_reuse.py

背景（真实 DB 实测复现）：Webhook 入库的行带真实 server_id，而扫描路径写库时 server_id 传空
（`_record_nfo_library` 调用方没传）→ upsert 的删旧行/清观察期都按 server_id 隔离 → 同一文件
出现两份记录（6 行 / 库页 2 个条目）。反向顺序（先扫描 → 再 Webhook）因「遗留行来源迁移」
（''→真实）不会重复 —— 只有「先入库后扫描」会中招。

修法：扫描写库前，若 server_id 为空 → `db.server_id_by_nfo_path()` 复用该文件**唯一**的真实来源
（无记录 / 多个不同来源 → 仍用 ''），于是 upsert 命中同一组（覆盖而非新增），已有重复也顺带收编。

覆盖：
  T1 server_id_by_nfo_path：无记录 / 唯一来源 / 多来源 / 只有空来源 / 空路径
  T2 端到端：先 Webhook 再「复用来源的扫描」→ 仍 1 组；不传来源 → 2 组（复现旧 bug 作为护栏）
  T3 已重复状态 → 用复用来源再写一次 → 收编回 1 组
  T4 反向顺序（先扫描 → 再 Webhook）仍不重复
  T5 源码级：_record_nfo_library 接入复用，且 upsert 用 _sid_final
"""
import sys
import re
import types
import textwrap
import tempfile
import importlib.util
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl88_"))
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")


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
class _S: CONFIG_PATH = str(TMP)
_c.settings = _S()
sys.modules.update({"app": _m, "app.sdk": _s, "app.sdk.logging": _l, "app.sdk.config": _c})

_spec = importlib.util.spec_from_file_location("epl_db88", PLUGIN_DIR / "db.py")
dbm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dbm)

_N = [0, 0]
def check(cond, msg):
    _N[0] += 1
    if cond:
        print(f"  [PASS] {msg}")
    else:
        _N[1] += 1
        print(f"  [FAIL] {msg}")


def _grab_method(src, name):
    mm = re.search(rf"^([ \t]*)def {re.escape(name)}\(", src, re.M)
    assert mm, f"未找到 {name}"
    indent = len(mm.group(1))
    lines = src[mm.start():].splitlines()
    out = [lines[0]]
    for ln in lines[1:]:
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent and ln.lstrip().startswith("def "):
            break
        out.append(ln)
    return textwrap.dedent("\n".join(out))


print("=" * 72)
print("v4.6.88 回归测试（扫描复用已有 server_id — 修先入库后扫描重复）")
print("=" * 72)

S_REAL = "___1_192_168_2_15_8096"
NFO = "X:/lib/Show/Season 1/S01E01.nfo"
PEOPLE = [{"Type": "Actor", "Name": "Tom Hanks", "Role": "Hero"},
          {"Type": "Actor", "Name": "Bob", "Role": "Villain"},
          {"Type": "Director", "Name": "Alice", "Role": ""}]
dbm.PeopleDb.ensure_table()


def _up(pid, sid):
    return dbm.PeopleDb().upsert_people(
        plugin_id=pid, server_id=sid, item_id="224207", item_type="Episode",
        title="Show", series_name="Show", season_num=1, episode_num=1,
        library_name="TV", people=PEOPLE, nfo_path=NFO, emby_item_id="55501",
        media_provider="tmdb", media_id="224207", series_media_id="224207", file_fingerprint="")


def _scan_sid(pid, nfo=NFO):
    """模拟修好后的扫描：server_id 为空 → 复用已有真实来源。"""
    return dbm.PeopleDb().server_id_by_nfo_path(plugin_id=pid, nfo_path=nfo) or ""


def _groups(pid):
    rows = dbm._q("SELECT COALESCE(server_id,'') sid, COUNT(*) n FROM person WHERE plugin_id=? "
                  "GROUP BY COALESCE(server_id,'') ORDER BY sid", (pid,))
    return [(str(r["sid"]), int(r["n"])) for r in rows]


def _total(pid):
    return int((dbm._q1("SELECT COUNT(*) c FROM person WHERE plugin_id=?", (pid,)) or {}).get("c") or 0)


# ─────────────────────────────────────────────
print("\n[T1] server_id_by_nfo_path：只认「唯一的非空来源」")
# ─────────────────────────────────────────────
P1 = "EPL88A"
check(dbm.PeopleDb().server_id_by_nfo_path(plugin_id=P1, nfo_path=NFO) == "", "无记录 → 空串")
check(dbm.PeopleDb().server_id_by_nfo_path(plugin_id=P1, nfo_path="") == "", "空路径 → 空串")
_up(P1, "")
check(dbm.PeopleDb().server_id_by_nfo_path(plugin_id=P1, nfo_path=NFO) == "",
      "只有空来源（''）→ 空串（不把 '' 当来源）")
_up(P1, S_REAL)
check(dbm.PeopleDb().server_id_by_nfo_path(plugin_id=P1, nfo_path=NFO) == S_REAL,
      f"唯一真实来源 → 返回 {S_REAL}")

P1B = "EPL88B"
_up(P1B, "S_A")
_up(P1B, "S_B")
check(dbm.PeopleDb().server_id_by_nfo_path(plugin_id=P1B, nfo_path=NFO) == "",
      "同一路径有多个不同来源 → 空串（多服务器不误归属）")

# ─────────────────────────────────────────────
print("\n[T2] 端到端：先 Webhook 再扫描 —— 复用来源后不再重复")
# ─────────────────────────────────────────────
P2 = "EPL88C"
_up(P2, S_REAL)                       # Webhook 入库
check(_groups(P2) == [(S_REAL, 3)] and _total(P2) == 3, "Webhook 后：1 组 3 行")
_scan_sid_fixed = _scan_sid(P2)       # 修好后的扫描会复用真实来源
check(_scan_sid_fixed == S_REAL, "扫描复用到的来源 = 真实来源")
_up(P2, _scan_sid_fixed)              # 扫描写库（复用来源）
check(_groups(P2) == [(S_REAL, 3)] and _total(P2) == 3,
      f"扫描后仍 1 组 3 行（无重复），实际 {_groups(P2)}")

P2B = "EPL88D"
_up(P2B, S_REAL)
_up(P2B, "")                          # 旧行为（不复用）：回归护栏
check(_groups(P2B) == [("", 3), (S_REAL, 3)] and _total(P2B) == 6,
      f"不复用来源 → 复现旧 bug：2 组 6 行 / 库页 2 条目，实际 {_groups(P2B)}")

# ─────────────────────────────────────────────
print("\n[T3] 已有重复的状态 → 用复用来源再写一次即可收编")
# ─────────────────────────────────────────────
_up(P2B, _scan_sid(P2B) or S_REAL)    # 修复后再来一次（扫描复用真实来源）
check(_groups(P2B) == [(S_REAL, 3)] and _total(P2B) == 3,
      f"收编后：1 组 3 行（重复被合并），实际 {_groups(P2B)}")

# ─────────────────────────────────────────────
print("\n[T4] 反向顺序（先扫描 → 再 Webhook）仍不重复（既有行为不回退）")
# ─────────────────────────────────────────────
P4 = "EPL88E"
_up(P4, "")
_up(P4, S_REAL)
check(_groups(P4) == [(S_REAL, 3)] and _total(P4) == 3,
      f"先扫描后 Webhook：仍 1 组 3 行（''→真实 收编），实际 {_groups(P4)}")

# ─────────────────────────────────────────────
print("\n[T5] 源码级：_record_nfo_library 接入复用")
# ─────────────────────────────────────────────
_rec = _grab_method(_SRC, "_record_nfo_library")
check("_sid_final = str(server_id or \"\")" in _rec, "引入 _sid_final（默认原 server_id）")
check("if not _sid_final:" in _rec, "仅在 server_id 为空时才去复用")
check("dbm.server_id_by_nfo_path(plugin_id=_pid, nfo_path=doc.path)" in _rec,
      "按该文件的 nfo_path 查已有来源")
check("server_id=_sid_final," in _rec, "upsert 用复用后的来源写库")
check("server_id=str(server_id or \"\")," not in _rec, "旧的写死写法已移除")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
