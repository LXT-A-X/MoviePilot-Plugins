# -*- coding: utf-8 -*-
"""P0 回归测试：写回状态机（WB-002 失败重试不再饿死 / WB-003 writing 租约自愈）。

运行：python tests/test_p0_writeback_state.py
"""
import os
import sys
from datetime import datetime, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import test_p0_nfo_checkpoint as base   # noqa: E402  （安装宿主桩件）

_Cls = base._Cls
check = base.check

_WB_ROOT = os.path.join(base._TMP, "wbstate")
os.makedirs(_WB_ROOT, exist_ok=True)
import app.sdk.config as _hcfg  # noqa: E402
_hcfg.settings.CONFIG_PATH = _WB_ROOT

from embypeoplelocalize.db import PeopleDb, WritebackDb, _x, _q  # noqa: E402

PID = "EmbyPeopleLocalize"

# 建表 + 跑版本化迁移（writeback_state 的 (plugin_id, server_id, item_id) 唯一索引
# 由 migrate() v7 创建 —— 插件启动时会跑，测试里需显式初始化，否则 ON CONFLICT 不可用）
PeopleDb.ensure_table()


def _iso(minutes_ago):
    return (datetime.now() - timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")


def _row(item_id):
    return WritebackDb().get(plugin_id=PID, server_id="", item_id=item_id)


def _force_last_attempt(item_id, iso_text):
    _x("UPDATE writeback_state SET last_attempt_at=? WHERE plugin_id=? AND item_id=?",
       (iso_text, PID, item_id))


def test_stale_writing_recovery():
    print("A) WB-003：超时 writing 行复位为 pending")
    wdb = WritebackDb()
    wdb.ensure_table()
    wdb.set_status(plugin_id=PID, server_id="", item_id="W-OLD", status="writing")
    _force_last_attempt("W-OLD", _iso(60))          # 1 小时前开始写 → 陈旧
    wdb.set_status(plugin_id=PID, server_id="", item_id="W-FRESH", status="writing")
    _force_last_attempt("W-FRESH", _iso(0))         # 刚开始写 → 不能误伤
    wdb.set_status(plugin_id=PID, server_id="", item_id="W-NOTS", status="writing")
    _force_last_attempt("W-NOTS", "")               # 无时间戳（旧数据）→ 视为陈旧
    n = wdb.reset_stale_writing(plugin_id=PID, stale_sec=900)
    check("陈旧 writing 行被复位（2 行）", n == 2, f"n={n}")
    check("陈旧行 → pending", str((_row("W-OLD") or {}).get("status")) == "pending")
    check("无时间戳行 → pending", str((_row("W-NOTS") or {}).get("status")) == "pending")
    check("新鲜 writing 行未被误伤", str((_row("W-FRESH") or {}).get("status")) == "writing")
    check("复位行给出错误说明",
          "自动恢复" in str((_row("W-OLD") or {}).get("error") or ""),
          str((_row("W-OLD") or {}).get("error")))


class _WBCls(_Cls):
    pass


def _wb_plugin(processed):
    """只挂写回轮所需桩件的实例（类属性游标隔离在子类上）。"""
    obj = object.__new__(_WBCls)
    obj._wb_stop_requested = lambda: False
    obj._wb_writeback_enabled = lambda: True
    obj._task_running = lambda task: False

    def _proc(pi_d, rec):
        processed.append(str(rec.get("item_id") or ""))
        return {"written": 1, "current": rec.get("item_id")}

    obj._wb_process_item = _proc
    return obj


def test_failed_not_starved():
    print("B) WB-002：pending 未清空时，到期的 failed 同样获得本轮试跑")
    wdb = WritebackDb()
    wdb.set_status(plugin_id=PID, server_id="", item_id="P-1", status="pending")
    wdb.set_status(plugin_id=PID, server_id="", item_id="F-1", status="failed", attempts=1)
    _force_last_attempt("F-1", _iso(20))            # 20 分钟前失败 → 已过退避（600s）
    processed = []
    obj = _wb_plugin(processed)
    _WBCls._wb_cursor = 0
    st = obj._writeback_pending_round(PID)
    check("同一轮同时处理 pending 与 failed 重试",
          ("P-1" in processed) and ("F-1" in processed), f"processed={processed}")
    check("本轮统计记为已处理", bool(st and st.get("did")), str(st))


def test_stale_writing_selfheal_in_round():
    print("C) WB-003：worker 卡死留下的 writing 行由本轮自愈并重跑")
    wdb = WritebackDb()
    wdb.set_status(plugin_id=PID, server_id="", item_id="W-CRASH", status="writing")
    _force_last_attempt("W-CRASH", _iso(30))
    processed = []
    obj = _wb_plugin(processed)
    _WBCls._wb_cursor = 0
    obj._writeback_pending_round(PID)
    check("卡死条目在同一轮被恢复并处理", "W-CRASH" in processed, f"processed={processed}")


if __name__ == "__main__":
    print(f"wb 目录: {_WB_ROOT}")
    test_stale_writing_recovery()
    test_failed_not_starved()
    test_stale_writing_selfheal_in_round()
    print(f"\n结果: {base._PASS} 通过 / {base._FAIL} 失败")
    sys.exit(1 if base._FAIL else 0)