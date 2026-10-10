# -*- coding: utf-8 -*-
"""P2/P3 回归测试：UI-008 复合键 / UI-009 汇总身份键 / 库列表分页 / 统一 TaskManager。

对应整改文档：
  UI-008：删除条目后清空选中态只比较 item_id，忽略来源 → 跨服务器同 item_id 误清选中。
          修复：以 itemKey（server_id:item_id）比较。
  UI-009：summaryGroups 以「译名」为身份键 → 两个不同原文被译成同字时被错误合并成一行。
          修复：以「原文 + 角色」为身份键（模板 :key 同步）。
  UI-PAGE：库列表一次性返回全部条目 → 大库卡顿、首屏慢。
          修复：/db/items 支持 limit/offset 分页（limit=0 保持旧数组结构向后兼容），
                前端 IntersectionObserver 滚动自加载并按复合键去重。
  TaskManager：把原散落在 __init__.py 的运行位/暂停位/启动器统一抽取到
               task_manager.TaskStateMixin（保守抽取，行为与原实现逐字一致）。

运行：python tests/test_p2_ui008_009_page_taskmgr.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import test_p0_nfo_checkpoint as base   # noqa: E402  （安装宿主桩件 + 导入插件类）

_Cls = base._Cls
check = base.check

from embypeoplelocalize.task_manager import TaskStateMixin  # noqa: E402

_VUE = os.path.join(os.path.dirname(_HERE), "src", "views", "LibraryView.vue")


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_ui008_composite_key():
    """UI-008：删除条目时按「来源 + item_id」复合键清选中态。"""
    print("A) UI-008 删除条目按复合键清选中态")
    src = _read(_VUE)
    check("delItem 使用 itemKey 复合键比较（含来源）",
          "itemKey(selected.value) === itemKey(node.item)" in src)
    check("未再回退到仅 item_id 比较",
          "selected.value?.item_id === node.item.item_id" not in src)


def test_ui009_identity_key():
    """UI-009：汇总行身份键 = 原文 + 角色（绝不以译名为键）。"""
    print("B) UI-009 汇总身份键 = 原文 + 角色")
    src = _read(_VUE)
    check("summaryGroups 以原文+角色构造 key",
          "${p.name_before || p.name_after || ''}\\u0001${p.role_before || p.role_after || ''}" in src)
    check("模板 :key 同步为 类型+原文+角色",
          "grp.type + '\\u0001' + row.name_before + '\\u0001' + row.role_before" in src)


def test_library_pagination():
    """UI-PAGE：/db/items 分页语义 + 前端滚动自加载接线。"""
    print("C) 库列表分页 /db/items")
    obj = base._fake_plugin()
    items = [{"server_id": "S1", "item_id": str(i)} for i in range(5)]

    r0 = obj._db_items_page(items, 0, 0)
    check("limit=0 → 旧结构（data 为数组，向后兼容）",
          r0.get("success") is True and isinstance(r0.get("data"), list) and len(r0["data"]) == 5,
          str(type(r0.get("data"))))

    d1 = obj._db_items_page(items, 2, 0).get("data") or {}
    check("首页 limit=2 返回前 2 条",
          isinstance(d1, dict) and [x["item_id"] for x in d1.get("items", [])] == ["0", "1"], str(d1))
    check("total=5 且 has_more=True（0+2<5）",
          d1.get("total") == 5 and d1.get("has_more") is True, str(d1))

    d2 = obj._db_items_page(items, 2, 4).get("data") or {}
    check("尾页 offset=4 limit=2 → 最后 1 条且 has_more=False",
          [x["item_id"] for x in d2.get("items", [])] == ["4"] and d2.get("has_more") is False, str(d2))

    d3 = obj._db_items_page(items, 2, 99).get("data") or {}
    check("越界 offset → 空页且 has_more=False",
          d3.get("items") == [] and d3.get("has_more") is False, str(d3))

    r4 = obj._db_items_page(items, "bad", -3)
    check("非法 limit → 回退旧结构（data 为数组）",
          isinstance(r4.get("data"), list), str(type(r4.get("data"))))

    src = _read(_VUE)
    # v4.6.104（LIB-006）：首页请求改为「按当前窗口大小」的 limit（Math.max(ITEM_PAGE_SIZE, 已加载数)）
    # 而非固定 limit=ITEM_PAGE_SIZE —— 否则静默轮询会把滚动加载出来的分页整段丢弃、塌回第 1 页。
    check("前端按 limit/offset 请求首页（按当前窗口大小，不塌回第 1 页）",
          "offset: 0" in src and "Math.max(ITEM_PAGE_SIZE, items.value.length)" in src)
    check("前端按已加载条数请求下一页",
          "offset: items.value.length" in src)
    check("前端挂载滚动哨兵", 'ref="itemSentinel"' in src)


def test_task_manager_unified():
    """统一 TaskManager：混入、运行位、聚合位、暂停位。"""
    print("D) 统一 TaskManager（TaskStateMixin）")
    check("插件类混入 TaskStateMixin", issubclass(_Cls, TaskStateMixin))
    check("运行位映射齐全",
          set(_Cls._TASK_FLAGS) == {"scan", "translate", "writeback", "pool", "probe"},
          str(_Cls._TASK_FLAGS))

    obj = base._fake_plugin()
    obj._scan_running = False
    obj._translate_running = False
    obj._writeback_running = False
    obj._pool_running = False
    obj._probe_running = False
    obj._is_running = False

    check("初始无任务在跑", obj._task_running("scan") is False)
    check("未知任务回退聚合位", obj._task_running("nope") is False)
    obj._set_task_running("scan", True)
    check("置位后 _task_running(scan) 为真", obj._task_running("scan") is True)
    check("聚合位 _is_running 被同步", obj._is_running is True)
    obj._set_task_running("scan", False)
    check("清位后聚合位归零", obj._is_running is False and obj._task_running("scan") is False)

    obj._scan_paused = False
    obj._scan_status = {"running": False}
    t = obj._set_task_paused("scan", True)
    check("暂停 scan 生效", t == ["scan"] and obj._task_paused("scan") is True, str(t))
    check("暂停位同步到 _scan_status", obj._scan_status.get("paused") is True)
    obj._set_task_paused("scan", False)
    check("继续 scan 清除暂停位", obj._task_paused("scan") is False)
    check("无效 target 不生效", obj._set_task_paused("bogus", True) == [])

    obj._tx_requested = True
    check("翻译忙碌判定以 _tx_requested 为准", obj._task_busy_for_pause("translate") is True)


def main():
    test_ui008_composite_key()
    test_ui009_identity_key()
    test_library_pagination()
    test_task_manager_unified()
    print(f"\n合计: PASS={base._PASS} FAIL={base._FAIL}")
    sys.exit(1 if base._FAIL else 0)


if __name__ == "__main__":
    main()
