# -*- coding: utf-8 -*-
"""P0 回归测试：UI-004 探测任务使用独立 probe_status，不再写 _scan_status。

对应整改文档 UI-004：
  探测任务复用 _scan_status.running，可能被 UI 误显示为「扫描进行中」。
  修复：probe 使用独立 probe_status，不得写 _scan_status。
  回归：只执行 probe，scan_status.running 必须保持 false。

运行：python tests/test_p0_ui004_probe_status.py
"""
import os
import sys
import threading

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import test_p0_nfo_checkpoint as base   # noqa: E402  （安装宿主桩件 + 导入插件类）

_Cls = base._Cls
check = base.check


def _new_obj():
    """不带宿主 __init__ 的实例，只挂扫描/探测状态与真实任务位逻辑。"""
    obj = object.__new__(_Cls)
    obj._scan_lock = threading.RLock()
    obj._state_lock = threading.RLock()
    obj._scan_status = {"running": False, "current_title": "", "total": 0, "done": 0}
    obj._probe_status = {"running": False, "current_title": "", "total": 0, "done": 0}
    obj._progress_step_start_time = 0.0
    obj._last_run_time = ""
    # 各任务位（初始全部空闲）
    obj._scan_running = False
    obj._translate_running = False
    obj._writeback_running = False
    obj._pool_running = False
    obj._probe_running = False
    obj._is_running = False
    obj._probe_stop = False
    return obj


def test_build_scan_status_excludes_probe():
    """只跑探测时，_build_scan_status().running 必须为 false。"""
    print("A) 只跑 probe → scan_status.running 保持 false")
    obj = _new_obj()
    # 模拟：仅 probe 任务在跑（聚合位 True，scan 位 False）
    obj._set_task_running("probe", True)
    st = obj._build_scan_status()
    check("probe 运行中，聚合 _is_running 为 True", obj._is_running is True, str(obj._is_running))
    check("只跑 probe：scan_status.running == False", st.get("running") is False, str(st.get("running")))
    check("scan_status.tasks.probe 反映真实运行位", st.get("tasks", {}).get("probe") is True,
          str(st.get("tasks")))
    obj._set_task_running("probe", False)

    # 对照：真正扫描时 running 必须为 True（避免修复误伤扫描显示）
    obj._set_task_running("scan", True)
    st2 = obj._build_scan_status()
    check("只跑 scan：scan_status.running == True", st2.get("running") is True, str(st2.get("running")))
    obj._set_task_running("scan", False)


def test_probe_execute_isolated_status():
    """_probe_execute 只写 _probe_status，绝不触碰 _scan_status。"""
    print("B) _probe_execute 隔离状态：不污染 _scan_status")
    obj = _new_obj()
    seen = {}

    def _fake_round(*a, **k):
        # 轮次执行期间：探测位已置起、扫描位不动
        seen["probe_running"] = obj._probe_running
        seen["probe_title"] = obj._probe_status.get("current_title")
        seen["scan_running"] = obj._scan_running
        seen["scan_status_snapshot"] = dict(obj._scan_status)

    obj._run_probe_round = _fake_round
    ret = obj._probe_execute(force_deep=True)

    check("probe 执行期间 probe 运行位为 True", seen.get("probe_running") is True,
          str(seen.get("probe_running")))
    check("probe 执行期间写入 probe_status.current_title",
          seen.get("probe_title") == "探测库中...", str(seen.get("probe_title")))
    check("probe 执行期间 scan 运行位保持 False", seen.get("scan_running") is False,
          str(seen.get("scan_running")))
    check("probe 执行期间未改动 _scan_status",
          seen.get("scan_status_snapshot") == {"running": False, "current_title": "",
                                               "total": 0, "done": 0},
          str(seen.get("scan_status_snapshot")))
    check("probe 正常结束返回 None", ret is None, str(ret))
    check("结束后 probe_status.running 复位", obj._probe_status.get("running") is False,
          str(obj._probe_status.get("running")))
    check("结束后 probe_status.current_title 清空", obj._probe_status.get("current_title") == "",
          str(obj._probe_status.get("current_title")))
    check("结束后 probe 运行位复位", obj._probe_running is False, str(obj._probe_running))
    check("结束后聚合位复位", obj._is_running is False, str(obj._is_running))


def test_scan_status_intact_after_probe():
    """probe 全程结束后 _scan_status 与初始完全一致（键值零污染）。"""
    print("C) probe 结束后 _scan_status 键值零污染")
    obj = _new_obj()
    before = dict(obj._scan_status)
    obj._run_probe_round = lambda *a, **k: None
    obj._probe_execute(force_deep=False)
    check("_scan_status 与初始一致", obj._scan_status == before,
          f"before={before} after={obj._scan_status}")


if __name__ == "__main__":
    test_build_scan_status_excludes_probe()
    test_probe_execute_isolated_status()
    test_scan_status_intact_after_probe()
    print(f"\n结果: {base._PASS} 通过 / {base._FAIL} 失败")
    sys.exit(1 if base._FAIL else 0)
