# -*- coding: utf-8 -*-
"""P2 回归测试：UI-006 出现清单来源隔离 + UI-007 池导入上限。

对应整改文档：
  UI-006：PeoplePool occurrence/detail key 缺 server_id → 两服务器同名 Person 时
          UI 状态互相串。修复：key/查询都带 server_id（occurrence 支持 source scope）。
          回归：A/B 相同 person id/name，A 的查询不影响 B。
  UI-007：导入一次性读整个 JSON，无大小/行数上限 → 大文件冻结浏览器。
          修复：前端限制文件大小/记录数；后端兜底限制单次导入记录数。
          回归：超限必须快速拒绝并给出原因。

运行：python tests/test_p2_ui006_007_pool.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import test_p0_nfo_checkpoint as base   # noqa: E402  （安装宿主桩件 + 导入插件类）

_Cls = base._Cls
check = base.check

_ROOT = os.path.join(base._TMP, "ui006007")
os.makedirs(_ROOT, exist_ok=True)
import app.sdk.config as _hcfg  # noqa: E402
_hcfg.settings.CONFIG_PATH = _ROOT

from embypeoplelocalize.db import PeopleDb  # noqa: E402

PID = "EmbyPeopleLocalize"
SRV_A = "SRV-A"
SRV_B = "SRV-B"
SAME_NAME = "同名演员"   # 两个服务器共用的原文名（模拟相同 name / person）


def _p(name):
    return [{"Type": "Actor", "before_name": name, "Name": f"{name}-中"}]


def test_occurrence_source_scope():
    """UI-006：rows_by_name 按 server_id 隔离，两服务器同名不混入。"""
    print("A) UI-006 出现清单来源隔离")
    db = PeopleDb()
    db.ensure_table()
    db.upsert_people(plugin_id=PID, server_id=SRV_A, item_id="7007", item_type="Movie",
                     title="Server A", people=_p(SAME_NAME))
    db.upsert_people(plugin_id=PID, server_id=SRV_B, item_id="7008", item_type="Movie",
                     title="Server B", people=_p(SAME_NAME))

    a_rows = db.rows_by_name(plugin_id=PID, name_before=SAME_NAME, server_id=SRV_A)
    b_rows = db.rows_by_name(plugin_id=PID, name_before=SAME_NAME, server_id=SRV_B)
    all_rows = db.rows_by_name(plugin_id=PID, name_before=SAME_NAME)
    check("SRV-A 只返回 A 的来源行",
          len(a_rows) == 1 and a_rows[0].get("server_id") == SRV_A and a_rows[0].get("item_id") == "7007",
          str([(r.get("server_id"), r.get("item_id")) for r in a_rows]))
    check("SRV-B 只返回 B 的来源行",
          len(b_rows) == 1 and b_rows[0].get("server_id") == SRV_B and b_rows[0].get("item_id") == "7008",
          str([(r.get("server_id"), r.get("item_id")) for r in b_rows]))
    check("A 的查询看不到 B 的行", all(r.get("server_id") == SRV_A for r in a_rows), str(a_rows))
    check("不传 server_id → 保留旧「跨来源」语义（两行）", len(all_rows) == 2, str(len(all_rows)))

    # UI-006 key 结构（与前端 personKey 约定一致）：server_id + ':' + person 标识
    def _key(r):
        return f"{r.get('server_id') or ''}:{r.get('emby_person_id') or r.get('name_before') or ''}"
    check("A/B 两行的 key 不同（不会互相串展开态）",
          _key(a_rows[0]) != _key(b_rows[0]), f"{_key(a_rows[0])} vs {_key(b_rows[0])}")


def _import_obj():
    from embypeoplelocalize.db import NameMapDb
    obj = object.__new__(_Cls)
    obj._api_gate = lambda: None
    obj._task_busy_msg = lambda: None
    obj._push_log = lambda *a, **k: None
    obj._name_map_db = NameMapDb()
    return obj


def test_import_row_limit():
    """UI-007：后端兜底限制单次导入记录数；超限快速拒绝并给出原因。"""
    print("B) UI-007 池导入记录数上限（后端兜底）")
    obj = _import_obj()
    over = [{"original": "x", "zh": "y"}] * 50001
    r1 = obj._api_pool_import({"rows": over})
    check("超限导入被拒绝", r1.get("success") is False, str(r1))
    check("拒绝原因包含「记录数过多」", "记录数过多" in str(r1.get("message") or ""), str(r1))

    r2 = obj._api_pool_import({"rows": "not-a-list"})
    check("非数组导入被拒绝", r2.get("success") is False and "格式" in str(r2.get("message") or ""),
          str(r2))

    r3 = obj._api_pool_import({"rows": []})
    check("空数据被拒绝", r3.get("success") is False, str(r3))

    r4 = obj._api_pool_import({})
    check("缺字段被拒绝", r4.get("success") is False, str(r4))


if __name__ == "__main__":
    test_occurrence_source_scope()
    test_import_row_limit()
    print(f"\n结果: {base._PASS} 通过 / {base._FAIL} 失败")
    sys.exit(1 if base._FAIL else 0)
