# -*- coding: utf-8 -*-
"""v4.7.0 回归测试：GitHub issue #7（写回 NameError `_sc`）+ issue #6（noop 词条永久计入待翻）。

运行：python tests/test_v470_release_issues_6_7.py

覆盖：
  T1 issue #7 —— _norm_writeback_scope 归一化 + _restore_item_to_nfo 不再抛 NameError
                （范围文案 / Emby 条目角色门禁）；编程错误单独标 bug=True
  T2 issue #6 —— person 表 name_noop/role_noop 持久标记：schema/迁移/谓词/真实 SQLite
                标记后不再计入待翻；_translate_pending_round 接线
"""
import sys
import os
import re
import types
import time
import textwrap
import tempfile
import traceback
import importlib.util
from pathlib import Path
from typing import Any, List, Optional, Dict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl470_"))
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
_DB = (PLUGIN_DIR / "db.py").read_text(encoding="utf-8")

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

_spec = importlib.util.spec_from_file_location("epl_db470", PLUGIN_DIR / "db.py")
dbm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dbm)


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


print("=" * 72)
print("v4.7.0 回归测试（issue #7 写回 _sc / issue #6 noop 永久待翻）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] issue #7：_norm_writeback_scope + _restore_item_to_nfo 不再抛 NameError")
# ─────────────────────────────────────────────
check("def _norm_writeback_scope(scope, default: str = \"both\") -> str:" in _SRC,
      "新增 _norm_writeback_scope 统一归一化入口")
# 归一化语义（与生产实现逐字一致）
_nsNorm = {}
exec(_grab_method(_SRC, "_norm_writeback_scope"), _nsNorm)
_norm = _nsNorm["_norm_writeback_scope"].__func__ if hasattr(_nsNorm["_norm_writeback_scope"], "__func__") \
    else _nsNorm["_norm_writeback_scope"]
try:
    check(_norm("role") == "role" and _norm("PERSON") == "person" and _norm("both") == "both",
          "_norm_writeback_scope：合法值原样/小写归一")
    check(_norm("") == "both" and _norm(None) == "both" and _norm("xyz") == "both",
          "空/None/非法 → 默认 both")
    check(_norm("", "role") == "role", "默认值可指定（空 → 指定默认）")
except TypeError:
    _norm_fn = _nsNorm["_norm_writeback_scope"]
    check(_norm_fn(None, "role") == "role", "静态方法（带 self 占位）可调用")

# 源码级：_restore_item_to_nfo 已定义 _sc（不再裸用）
_rb = _grab_method(_SRC, "_restore_item_to_nfo")
check("_sc = self._norm_writeback_scope(scope)" in _rb,
      "_restore_item_to_nfo 使用统一归一化定义 _sc（修复 NameError）")

# 行为级：真实执行 _restore_item_to_nfo（真临时 nfo 文件 + 桩）
_nfo = TMP / "tvshow.nfo"
_nfo.write_text("<movie/>", encoding="utf-8")
_nsRS = {"logger": logger, "os": os, "time": time, "Dict": Dict, "traceback": traceback,
         "Optional": Optional, "Any": Any, "List": List}
exec(_grab_method(_SRC, "_restore_item_to_nfo"), _nsRS)


class _RSDb:
    def __init__(self, recs, boom=False):
        self._recs = recs
        self._boom = boom

    def item_meta(self, **kw):
        if self._boom:
            raise NameError("name 'foo' is not defined")
        return {"item_id": "1"}

    def people_of_item(self, **kw):
        if self._boom:
            raise NameError("name 'foo' is not defined")
        return list(self._recs)


class _RSSelf:
    _restore_item_to_nfo = _nsRS["_restore_item_to_nfo"]
    _norm_writeback_scope = staticmethod(_norm)

    def __init__(self, recs, boom=False):
        self._people_db = _RSDb(recs, boom=boom)
        self._nfo_preview = False
        self.emby_calls = []
        self.logs = []

    def _write_nfo_once(self, *a, **k):
        return {"success": True, "data": {"changed": 3, "noop": False}}

    def _emby_sync_item_roles(self, **k):
        self.emby_calls.append(k)
        return {"changed": 2}

    def _push_log(self, *a, **k):
        self.logs.append(a)


_RECS = [{"nfo_path": str(_nfo), "name_before": "A", "role_before": "B"}]

_o = _RSSelf(_RECS)
_r = _o._restore_item_to_nfo("1", "S1", auto=False, scope="role")
check(isinstance(_r, dict) and _r.get("success") is True and not _r.get("bug"),
      f"scope=role 写回不抛 NameError（issue #7 主症状），实际 {_r.get('message')!r}")
check("仅第二排角色" in str(_r.get("message")) and _r.get("data", {}).get("scope") == "role",
      "范围文案正确（仅第二排角色）+ data.scope 归一")
check(len(_o.emby_calls) == 1 and "Emby 角色同步 2 处" in str(_r.get("message")),
      "scope=role 时 Emby 条目级角色同步门禁可执行到（v4.6.114 能力复活）")

_o = _RSSelf(_RECS)
_r = _o._restore_item_to_nfo("1", "S1", scope="person")
check(not _o.emby_calls and "本次未包含第二排" in str(_r.get("message")),
      "scope=person → 不同步 Emby 角色且明确说明")

_o = _RSSelf(_RECS)
_r = _o._restore_item_to_nfo("1", "S1", scope="both")
check(len(_o.emby_calls) == 1 and "仅第一排人名" not in str(_r.get("message")),
      "scope=both → 两排都写（同步 Emby 角色、无范围后缀）")

# 编程错误单独标记 bug=True（不再只当普通写回失败）
_o = _RSSelf(_RECS, boom=True)
_r = _o._restore_item_to_nfo("1", "S1", scope="both")
check(_r.get("success") is False and _r.get("bug") is True and "内部错误" in str(_r.get("message")),
      f"编程错误 → bug=True（提示反馈作者），实际 {_r}")

# ─────────────────────────────────────────────
print("\n[T2] issue #6：person 持久 noop 标记 + 待翻口径一致")
# ─────────────────────────────────────────────
check(dbm.SCHEMA_VERSION >= 14, f"SCHEMA_VERSION 升到 14+（实际 {dbm.SCHEMA_VERSION}）")
check("name_noop INTEGER DEFAULT 0" in _DB and "role_noop INTEGER DEFAULT 0" in _DB,
      "person 建表含 name_noop / role_noop 列")
check('_ensure_columns("person", [("name_noop", "INTEGER DEFAULT 0"),' in _DB
      and '("role_noop", "INTEGER DEFAULT 0")' in _DB,
      "迁移 v14 幂等补列（旧库无损）")
check("def mark_person_noop" in _DB, "新增 PeopleDb.mark_person_noop")

_pk = _grab_method(_DB, "_pending_kind_sql")
check("COALESCE({'role_noop' if _col == 'role_before' else 'name_noop'},0)=0" in _pk,
      "_pending_kind_sql：only_pending 时排除 noop 标记行")
check('_noop_sql = ""' in _pk, "none-pending（force/范围内）不受 noop 标记影响（可重试）")

# 真实 SQLite 行为级
pdb = dbm.PeopleDb()
pdb.ensure_table()
PID = "EPL470"
dbm._x("DELETE FROM person WHERE plugin_id=?", (PID,))
pdb.upsert_people(plugin_id=PID, server_id="S1", item_id="tv:1", item_type="Series",
                  title="S", series_name="S",
                  people=[{"Type": "Actor", "before_name": "Bob", "before_role": "M"},
                          {"Type": "Actor", "before_name": "Alice", "before_role": "Done"}])


def _terms():
    _f = pdb.pending_terms_full(plugin_id=PID, only_pending=True)
    return {"names": sorted({r["term"] for r in (_f.get("names") or [])}),
            "roles": sorted({r["term"] for r in (_f.get("roles") or [])})}


_before = _terms()
check(_before["names"] == ["Alice", "Bob"] and _before["roles"] == ["Done", "M"],
      f"标记前：待翻 人名 {_before['names']} / 角色 {_before['roles']}")

_n = pdb.mark_person_noop(plugin_id=PID, role_terms=["M"])
check(_n > 0, f"mark_person_noop 标记角色成功（{_n} 行）")
_after = _terms()
check(_after["roles"] == ["Done"] and _after["names"] == ["Alice", "Bob"],
      f"标记「M」后角色待翻不再含 M（{_after['roles']}）；人名不受影响")

_n2 = pdb.mark_person_noop(plugin_id=PID, name_terms=["Bob"])
_after2 = _terms()
check(_after2["names"] == ["Alice"] and _after2["roles"] == ["Done"],
      f"标记「Bob」后人名待翻只剩 Alice（{_after2}），角色 noop 标记互不串")

# 已有译文的行绝不被标记（守卫 after='' OR NULL）
pdb.upsert_people(plugin_id=PID, server_id="S1", item_id="tv:2", item_type="Series",
                  title="S2", series_name="S2",
                  people=[{"Type": "Actor", "before_name": "Carol", "before_role": "R"}])


pdb.apply_translations_occurrence(plugin_id=PID, rows=[
    {"kind": "name", "original_text": "Carol", "translation": "卡罗尔",
     "item_id": "tv:2", "server_id": "S1", "person_index": 0}])
_marked = pdb.mark_person_noop(plugin_id=PID, name_terms=["Carol"])
_rows = dbm._q("SELECT name_after, name_noop FROM person WHERE plugin_id=? AND name_before='Carol'",
               (PID,))
check(_rows and int(_rows[0].get("name_noop") or 0) == 0 and str(_rows[0].get("name_after")) == "卡罗尔",
      "已翻译的行不被 noop 标记覆盖（守卫生效）")

# _translate_pending_round 接线
check("_noop_lib: Dict[str, set] = {\"name\": set(), \"role\": set()}" in _SRC,
      "轮次收集库内 noop 词条（人名/角色分开）")
check("_noop_lib[_k].add(_t)" in _SRC and _SRC.count("_noop_lib[_k].add(_t)") >= 3,
      "v4.7.2（issue #8）：三条 noop 过滤分支（已是中文/会话 noop/无内容）**都**落持久标记")
check('if _t in self._tx_noop_terms_set():' in _SRC
      and "内存知识必须持久化" in _SRC,
      "会话 noop 集合命中即持久化（此前只 return False → 永不落盘 = 角标永久挂着）")
check("_flush_noop_marks()" in _SRC and "db.mark_person_noop(plugin_id=pid" in _SRC,
      "轮末落 person 表持久标记（收词即生效，含提前 return 路径）")
check("def _flush_noop_marks()" in _SRC and _SRC.count("_flush_noop_marks()") >= 2,
      "_flush_noop_marks 定义 + 至少两处调用（收词后 / 模型 noop 后）")

# v4.7.2（issue #8）：空标记占位 + 读取处兜底 + 空转自证
check("def _tx_noop_placeholder" in _SRC and "_NOOP_PLACEHOLDER_RE" in _SRC,
      "新增空标记占位判定（(voice)/(CV)/待补充 …）—— 不被 _tx_untranslatable 覆盖")
check("兜底 noop 持久标记" in _SRC and "已从候选队列剔除" in _SRC,
      "全库轮在读取处兜底落标记并从候选剔除（不依赖某轮 _accept 是否被调用）")
check("自证：候选" in _SRC, "候选非空却 0 条可送翻时有 INFO 自证日志（空转可自查）")

_nsPh = {"re": re}
exec(_grab_method(_SRC, "_tx_noop_placeholder"), _nsPh)
_ph = _nsPh["_tx_noop_placeholder"]


class _PhNS:
    pass


_PhNS._NOOP_PLACEHOLDER_RE = re.compile(
    re.search(r'_NOOP_PLACEHOLDER_RE = re\.compile\(\s*r"([^"]+)"', _SRC).group(1), re.IGNORECASE)
check(_ph(_PhNS, "(voice)") is True and _ph(_PhNS, "（CV）") is True and _ph(_PhNS, "待补充") is True,
      "占位判定：voice / CV / 待补充 → noop")
check(_ph(_PhNS, "N8") is False and _ph(_PhNS, "sloppy") is False and _ph(_PhNS, "M") is False,
      "占位判定不误伤真实名字（N8 / sloppy / M 走 AI 或单字符判定）")

# 附带（同一排障诉求）：DEBUG 日志不再被桥接层写死 INFO 挡住 + 实例级别真正接通
check("bridge.setLevel(logging.NOTSET)" in _SRC and "bridge.setLevel(logging.INFO)" not in _SRC,
      "日志桥接不再写死 INFO（跟随 logger 有效级别）")
check("def _align_log_level" in _SRC and "moviepilot.plugins.embypeoplelocalize" in _SRC
      and "DEBUG 将落入日志文件" in _SRC,
      "新增 _align_log_level：把插件实例日志级别（DEBUG）真正接通到共享 logger + 文件 handler")
check("条「无需操作」词条已落持久标记" in _SRC,
      "noop 落标记有 INFO 自证日志（空转作业可自查，不再只有 debug 分支）")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
