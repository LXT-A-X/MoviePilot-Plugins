# -*- coding: utf-8 -*-
"""v4.7.13 回归：GitHub issue #14 + #15（no_entity 终态「只进不出」+ 「无此人物」标签缺样式）。

覆盖：
  T1 issue #15 后端：`_api_pool_refetch_one` 重拉拿到 Person 后**撤销 no_entity 终态**
     （逐字执行真实方法：有 ID 行 / legacy 无 ID 行两条分支都覆盖；failed 保持不变）
  T2 issue #15 前端：`canSync()` 与批量同步（`_SQL_SYNC_PENDING`）同口径 —— no_entity 不给「同步」按钮
     （Node 跑真实 canSync 函数的行为矩阵）
  T3 issue #14：补齐 `.epl-badge.st-info` —— statusChip() 可能返回的四种 color 在 CSS 里都有类
  T4 口径一致性：前端按钮门禁 / 批量同步 SQL / 数据库终态三者互不矛盾
"""
import sys
import re
import json
import types
import textwrap
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
_DB = (PLUGIN_DIR / "db.py").read_text(encoding="utf-8")
_VUE = (PLUGIN_DIR / "src" / "views" / "PeoplePoolView.vue").read_text(encoding="utf-8")
NODE = r"C:\node-v22.14.0-win-x64\node.exe"
_N = [0, 0]


def check(cond, msg):
    if cond:
        _N[0] += 1
        print(f"[PASS] {msg}")
    else:
        _N[1] += 1
        print(f"[FAIL] {msg}")


class _Logger:
    def __init__(self):
        self.infos, self.warnings, self.debugs, self.errors = [], [], [], []

    def debug(self, m, *a, **k):
        self.debugs.append(str(m))

    def info(self, m, *a, **k):
        self.infos.append(str(m))

    def warning(self, m, *a, **k):
        self.warnings.append(str(m))

    def error(self, m, *a, **k):
        self.errors.append(str(m))

    def log(self, *a, **k):
        pass


logger = _Logger()

_m = types.ModuleType("app"); _s = types.ModuleType("app.sdk")
_l = types.ModuleType("app.sdk.logging"); _l.logger = logger
sys.modules.update({"app": _m, "app.sdk": _s, "app.sdk.logging": _l})


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


def _grab_js_fn(src, name):
    """从 .vue 里按大括号配平提取一个 JS 函数体。"""
    mm = re.search(rf"^function {re.escape(name)}\([^\n]*\) \{{", src, re.M)
    assert mm, f"未找到 JS 函数 {name}"
    start = mm.start()
    i = src.index("{", mm.start() + len("function ") + len(name))
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
    raise AssertionError(name)


print("=" * 72)
print("v4.7.13 回归：issue #14（标签缺样式）+ #15（no_entity 终态只进不出）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] 后端：重拉拿到 Person → 撤销 no_entity 终态")
# ─────────────────────────────────────────────
_ns = {"logger": logger, "json": json, "str": str, "int": int, "bool": bool, "len": len,
       "Optional": Optional, "Dict": Dict, "NameMapDb": object}
exec(_grab_method(_SRC, "_api_pool_refetch_one"), _ns)


class _CliStub:
    def __init__(self, person):
        self.person = person

    def get_person_by_id(self, pid):
        return dict(self.person) if self.person else None

    def find_persons_by_name(self, name):
        return [dict(self.person)] if self.person else []


class _DbStub:
    def __init__(self, row):
        self.row = row
        self.calls = []

    def find_pool_person(self, **kw):
        return dict(self.row) if self.row else None

    def find_pool_persons_by_name(self, **kw):
        return [dict(self.row)] if self.row else []

    def upsert_pool_person(self, **kw):
        self.calls.append(("upsert", dict(kw)))
        return "updated"

    def bind_pool_person_id(self, **kw):
        self.calls.append(("bind", dict(kw)))
        return 1

    def update_pool_status(self, **kw):
        self.calls.append(("status", dict(kw)))
        return 1


class _RefSelf:
    _api_pool_refetch_one = _ns["_api_pool_refetch_one"]

    def __init__(self, row, person):
        self._name_map_db = _DbStub(row)
        self._cli = _CliStub(person)
        self.logs = []

    def _api_gate(self):
        return None

    def _task_busy_msg(self):
        return None

    def _emby_client_for_server(self, sid, allow_legacy_fallback=True):
        return (self._cli, "")

    def _push_log(self, level, msg):
        self.logs.append(f"{level} {msg}")


_PERSON = {"Id": "P1", "Name": "Joe Murphy"}
_ROW_BASE = {"name_original": "Joe Murphy", "server_id": "S1", "person_type": "Actor",
             "person_types": "[]"}

# ① 有 ID 的 no_entity 行（issue #15 实况：emby_person_id='' 由 legacy 分支覆盖在 ③）
_row_ne = dict(_ROW_BASE, emby_person_id="P1", sync_status="no_entity",
               sync_error="Emby 中未找到该人物（原文名与目标名都搜不到）—— 该 Person 实体不存在，无需同步")
_s1 = _RefSelf(_row_ne, _PERSON)
_r1 = _s1._api_pool_refetch_one({"name_original": "Joe Murphy", "server_id": "S1"})
_clr = [c for c in _s1._name_map_db.calls
        if c[0] == "status" and c[1].get("sync_status") == "" and c[1].get("sync_error") == ""]
check(_r1.get("success") is True, f"重拉成功（Emby 已存在该 Person），实际 {_r1.get('message')}")
check(len(_clr) == 1, f"重拉成功后清 no_entity 终态（sync_status='' / sync_error=''），实际 {len(_clr)} 次清空")
check(_clr and _clr[0][1].get("emby_person_id") == "P1", "清终态按身份（Person ID）定位，不误伤同名行")
check(any("已清除「无此人物」终态" in m for m in _s1.logs),
      f"清终态落一条 INFO（用户可见「这行为什么能出来了」），实际 {_s1.logs}")
check(any(c[0] == "upsert" for c in _s1._name_map_db.calls), "Emby 事实照旧刷新（upsert 当前名）")

# ② failed 行：真失败（实体存在但改不动）→ **不得**清
_row_f = dict(_ROW_BASE, emby_person_id="P1", sync_status="failed", sync_error="改名失败：403")
_s2 = _RefSelf(_row_f, _PERSON)
_s2._api_pool_refetch_one({"name_original": "Joe Murphy", "server_id": "S1"})
_clr2 = [c for c in _s2._name_map_db.calls if c[0] == "status" and c[1].get("sync_status") == ""]
check(_clr2 == [], f"failed 行不清终态（保留计数与原因），实际 {_clr2}")
check(not any("已清除" in m for m in _s2.logs), "failed 行不打「已清除」日志")

# ③ legacy 无 ID 行 + no_entity（issue #15 报告者的实况：emby_person_id=''）→ 补 ID 后同样清
_row_legacy = dict(_ROW_BASE, emby_person_id="", sync_status="no_entity", sync_error="Emby 中未找到该人物")
_s3 = _RefSelf(_row_legacy, _PERSON)
_r3 = _s3._api_pool_refetch_one({"name_original": "Joe Murphy"})
_calls3 = _s3._name_map_db.calls
_clr3 = [c for c in _calls3 if c[0] == "status" and c[1].get("sync_status") == ""]
check(any(c[0] == "bind" for c in _calls3), "legacy 无 ID 行：先就地补 Person ID")
check(len(_clr3) == 1, f"legacy 行同样清终态，实际 {len(_clr3)}")
check(any(c[0] == "status" and c[1].get("name_current") == "Joe Murphy" for c in _calls3),
      "legacy 行照旧刷新 Emby 当前名")
check(_r3.get("success") is True, "legacy 重拉成功返回")

# ④ 池里没有该行 → 新建，不涉及清理
_s4 = _RefSelf(None, _PERSON)
_s4._api_pool_refetch_one({"name_original": "Joe Murphy", "server_id": "S1"})
check(any(c[0] == "upsert" for c in _s4._name_map_db.calls), "池中无该行 → 新建池行")
check(not any(c[0] == "status" for c in _s4._name_map_db.calls), "新建路径不做终态清理")

# ⑤ Emby 仍无此人 → 保持原行为（返回失败、不动状态）
_s5 = _RefSelf(_row_ne, None)
_r5 = _s5._api_pool_refetch_one({"name_original": "Joe Murphy", "server_id": "S1"})
check(_r5.get("success") is False and "未找到该人物" in str(_r5.get("message") or ""),
      f"Emby 仍无此人 → 明确失败（行为不变），实际 {_r5.get('message')}")
check(not any(c[0] == "status" and c[1].get("sync_status") == "" for c in _s5._name_map_db.calls),
      "Emby 仍无此人时不误清终态")

# ─────────────────────────────────────────────
print("\n[T2] 前端 canSync()：no_entity 不给「同步」按钮（Node 跑真实函数）")
# ─────────────────────────────────────────────
_js = "\n".join([_grab_js_fn(_VUE, "isChineseText"), _grab_js_fn(_VUE, "poolTargetName"),
                 _grab_js_fn(_VUE, "canSync")])
_tmp_js = Path(tempfile.mkdtemp(prefix="epl4713_")) / "cansync.js"
_tmp_js.write_text(_js + """
const cases = [
  [{name_original:'Joe Murphy',name_zh:'乔·墨菲',name_current:'Joe Murphy',sync_status:'no_entity'},
   false, 'no_entity（确实有差异）→ 不给按钮'],
  [{name_original:'Joe Murphy',name_zh:'乔·墨菲',name_current:'乔·墨菲',sync_status:'no_entity'},
   false, 'no_entity（目标名==当前名）→ 不给按钮'],
  [{name_original:'Joe Murphy',name_zh:'乔·墨菲',name_current:'Joe Murphy',status:'无此人物'},
   false, 'status 口径「无此人物」→ 不给按钮'],
  [{name_original:'Joe Murphy',name_zh:'乔·墨菲',name_current:'Joe Murphy',sync_status:''},
   true, '普通「待同步」→ 仍给按钮（未被误伤）'],
  [{name_original:'Joe Murphy',name_zh:'乔·墨菲',name_current:'Joe Murphy',sync_status:'failed'},
   true, 'failed（真失败）→ 仍给按钮（可重试）'],
  [{name_original:'Tom Hanks',name_zh:'汤姆·汉克斯',name_current:'Tom Hanks'},
   true, '无 sync_status 的老行 → 仍给按钮'],
  [{name_original:'阿澄 佳奈',name_zh:'',name_current:''},
   false, 'v4.6.93 原口径不变（原文已是中文 + 无当前名）'],
  [{name_original:'Tom Hanks',name_zh:'',name_current:''},
   false, '无目标名 → 不给按钮（原口径）'],
];
const out = cases.map(([r, exp, msg]) => ({ok: canSync(r) === exp, msg: msg + '（实际 ' + canSync(r) + '）'}));
console.log(JSON.stringify(out));
""", encoding="utf-8")
_js_out = subprocess.run([NODE, str(_tmp_js)], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
try:
    _cases = json.loads((_js_out.stdout or "").strip().splitlines()[-1])
    for _c in _cases:
        check(bool(_c.get("ok")), _c.get("msg"))
except Exception as e:
    check(False, f"Node 跑 canSync 失败：{e} / stdout={_js_out.stdout!r} stderr={_js_out.stderr!r}")

_can_src = _grab_js_fn(_VUE, "canSync")
check("=== 'no_entity'" in _can_src and "'无此人物'" in _can_src,
      "源码级：canSync 同时排除 sync_status=no_entity 与 status=无此人物（双口径）")
check(_VUE.count('v-if="canSync(r)"') == 2, f"行内与卡片两处按钮都走同一门禁，实际 {_VUE.count('v-if=\"canSync(r)\"')} 处")
check("v4.7.13（GitHub issue #15）" in _can_src, "改动带 issue 出处注释（可追溯）")

# ─────────────────────────────────────────────
print("\n[T3] issue #14：补齐 .epl-badge.st-info（不再有「映射到未定义类」）")
# ─────────────────────────────────────────────
check(".epl-badge.st-info" in _VUE, "新增 .st-info 样式类")
check("rgba(33,150,243,.16)" in _VUE and "rgba(33,150,243,.42)" in _VUE,
      "沿用同一透明度公式（Material Blue 500：底色 .16 / 描边 .42）")
_sc_src = _VUE[_VUE.index("function statusChip"):]
_sc_src = _sc_src[:_sc_src.index("\n}")]
for _color in ("error", "warning", "success", "info"):
    check(f"color: '{_color}'" in _sc_src and f".epl-badge.st-{_color}" in _VUE,
          f"statusChip 的 color='{_color}' 在 CSS 里有对应类（无缺口）")
check(_VUE.count("class=\"epl-badge\"") == 2, "行内与卡片两处徽章都用同一手写类拼接（同一处修复即全覆盖）")

# ─────────────────────────────────────────────
print("\n[T4] 三处口径一致性（前端按钮 / 批量 SQL / 终态语义）")
# ─────────────────────────────────────────────
check("NOT IN ('failed','no_entity')" in _DB, "批量同步 SQL 依旧排除 no_entity（^口径不变）")
check("COALESCE(sync_status,'') NOT IN ('failed','no_entity')" in _DB, "「待同步」计数同口径")
check("no_entity" in _DB and "不计失败" in _DB, "no_entity 语义：不计同步失败（保持 v4.7.11 设计）")
_pend = _DB[_DB.index("_SQL_SYNC_PENDING"):]
_pend = _pend[:_pend.index("\n")]
check("no_entity" in _pend, "前端隐藏按钮的集合与 SQL 排除的集合一致（都是 no_entity）")
_initsrc = _grab_method(_SRC, "_api_pool_refetch_one")
check(_initsrc.index("no_entity") < _initsrc.index("return {\"success\": True"),
      "清终态发生在「重拉成功返回」之前（同一次请求内完成）")
check("sync_error=\"\"" in _initsrc, "清终态同时清 sync_error（不留旧原因）")

print("\n" + "=" * 72)
print(f"结果: {_N[0]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
