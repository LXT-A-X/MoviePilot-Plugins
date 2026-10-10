# -*- coding: utf-8 -*-
"""v4.6.84 回归测试：容器级删除先探测 + 剧级行恢复 + 清除失效同步清事件 +
入库事件列表「一个事件一行」+ 通知恢复条数口径。

运行：python tests/test_v484_event_row_and_delete_probe.py

用户实测背景：
  ① 只把 3 集（视频+nfo）移走，Emby 发来的却是 Type=Series/IsFolder=True 的**容器级**删除
     → 插件照着 Item 整树标记 86 条 → 整部剧被误标观察期；
  ② 重新入库只展开 13 个单集，tvshow.nfo 定位失败（Series 的 Path 是目录却被 dirname）
     → 剧级行永不恢复 → 剧名一直「待恢复」、失效事件/到期时间不清；
  ③ 通知「已恢复被删条目 1 条」数的是通知批次而非恢复文件数（日志是 13）；
  ④ 点「清除失效」说成功但事件列表里的「失效/待恢复」行还在；
  ⑤ 「入库事件」列表一个事件显示两行（已接收 + 完成）。

覆盖：
  T1 _update_or_push_webhook_event 行为级：状态原地流转、一个事件一行
  T2 _locate_nfo_from_item 行为级：Series 的目录式 Path 能定位 tvshow.nfo（旧代码退一级 → 找不到）
  T3 item_has_series_row(exclude_deleted=True)：观察期行不算「已有剧级行」
  T4 _handle_webhook_delete 源码级：容器级删除先向 Emby 探测容器是否仍在
  T5 _api_db_purge_missing 源码级：0 条时也清理残留的脏失效事件
  T6 通知口径源码级：recovered 为计数、文案「个（重新入库）」
"""
import sys
import os
import re
import types
import textwrap
import tempfile
import importlib.util
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl84_"))
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
_DB = (PLUGIN_DIR / "db.py").read_text(encoding="utf-8")


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

_spec = importlib.util.spec_from_file_location("epl_db84", PLUGIN_DIR / "db.py")
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
print("v4.6.84 回归测试（容器删除探测 / 剧级行恢复 / 事件一行 / 口径）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] _update_or_push_webhook_event：状态原地流转、一个事件一行")
# ─────────────────────────────────────────────
_ns = {}
exec(_grab_method(_SRC, "_push_webhook_event"), _ns)
exec(_grab_method(_SRC, "_update_or_push_webhook_event"), _ns)


class _FS:
    def __init__(self): self._webhook_events = []
    def _save_state(self): pass


_FS._push_webhook_event = _ns["_push_webhook_event"]
_FS._update_or_push_webhook_event = _ns["_update_or_push_webhook_event"]
fs = _FS()
_push = lambda *a, **k: fs._push_webhook_event(*a, **k)
_upd = lambda *a, **k: fs._update_or_push_webhook_event(*a, **k)
_push("32027", "迷途之子!!!!!", "received", "已接收入库事件，60 秒后处理")
check(len(fs._webhook_events) == 1, "已接收 → 1 行")
_upd("32027", "迷途之子!!!!!", "running", "整剧入库：展开为 13 个单集任务")
check(len(fs._webhook_events) == 1, "处理中 → 仍 1 行（不再另起一行）")
check(fs._webhook_events[0]["status"] == "running", "该行状态原地变为 running")
_upd("32027", "迷途之子!!!!!", "done", "整剧入库：13 个 nfo")
check(len(fs._webhook_events) == 1, "完成 → 仍 1 行（一个事件只占一行）")
check(fs._webhook_events[0]["status"] == "done", "该行状态原地变为 done")
check("13 个 nfo" in fs._webhook_events[0]["msg"], "消息已同步为终态内容")
# 新事件（另一个条目）另起一行
_upd("999", "别的剧", "running", "x")
check(len(fs._webhook_events) == 2, "另一个条目 → 另起一行")
# 终态行不被中间态误改
_upd("32027", "迷途之子!!!!!", "running", "二次处理")
_done_rows = [e for e in fs._webhook_events if e["item_id"] == "32027" and e["status"] == "done"]
check(len(_done_rows) == 1, "已终态的行不会再被中间态覆盖（终态保持）")

# ─────────────────────────────────────────────
print("\n[T2] _locate_nfo_from_item：Series 的目录式 Path 能定位 tvshow.nfo")
# ─────────────────────────────────────────────
_ns2 = {"os": os, "logger": logger}
exec(_grab_method(_SRC, "_locate_nfo_from_item"), _ns2)


class _Host:
    _locate_nfo_from_item = _ns2["_locate_nfo_from_item"]


_locate = _Host()._locate_nfo_from_item
_root = Path(tempfile.mkdtemp(prefix="epl84nfo_"))
_show = _root / "BanG Dream! It's MyGO!!!!! (2023)"
_show.mkdir(parents=True)
(_show / "tvshow.nfo").write_text("<tvshow/>", encoding="utf-8")
_s1 = _show / "Season 1"
_s1.mkdir()
(_s1 / "S01E01.nfo").write_text("<episode/>", encoding="utf-8")
(_s1 / "S01E01.mkv").write_bytes(b"x")
(_show / "movie.nfo").write_text("<movie/>", encoding="utf-8")
(_show / "The Movie.mkv").write_bytes(b"x")

_r_series = _locate({"Type": "Series", "Path": str(_show)})
check(str(_r_series).replace("\\", "/").endswith("/tvshow.nfo"),
      f"Series（Path=目录）→ 命中同级 tvshow.nfo，实际 {_r_series!r}")
check(Path(_r_series).parent == _show if _r_series else False,
      "定位到的是剧集目录内的 tvshow.nfo（不是上一级目录——旧代码会退一级）")
_r_ep = _locate({"Type": "Episode", "Path": str(_s1 / "S01E01.mkv")})
check(str(_r_ep).replace("\\", "/").lower().endswith("/s01e01.nfo"),
      f"Episode → 命中同名 nfo（大小写不敏感比较），实际 {_r_ep!r}")
_r_movie = _locate({"Type": "Movie", "Path": str(_show / "The Movie.mkv")})
check(bool(_r_movie), "Movie → 仍能命中同目录 movie.nfo")

# ─────────────────────────────────────────────
print("\n[T3] item_has_series_row(exclude_deleted=True)：观察期行不算「已有剧级行」")
# ─────────────────────────────────────────────
dbm.PeopleDb.ensure_table()
PID = "EPL84"
dbm._x("INSERT INTO person (plugin_id, server_id, item_id, item_type, title, nfo_path, "
       "deleted_at, person_type, name_before) VALUES (?,?,?,?,?,?,?,'Actor','N')",
       (PID, "S1", "224207", "Series", "迷途之子!!!!!", "X:/a/tvshow.nfo", "2026-10-08 23:23:00"))
check(dbm.PeopleDb().item_has_series_row(plugin_id=PID, item_id="224207", server_id="S1") is True,
      "默认口径：观察期行仍算「已有剧级行」（旧行为，补写会被跳过）")
check(dbm.PeopleDb().item_has_series_row(plugin_id=PID, item_id="224207", server_id="S1",
                                         exclude_deleted=True) is False,
      "exclude_deleted=True：观察期行不算 → 触发补写剧级行（剧级行得以恢复）")
dbm._x("UPDATE person SET deleted_at='' WHERE plugin_id=? AND item_id=?", (PID, "224207"))
check(dbm.PeopleDb().item_has_series_row(plugin_id=PID, item_id="224207", server_id="S1",
                                         exclude_deleted=True) is True,
      "解除观察期后 → 又算「已有剧级行」（正常）")

# ─────────────────────────────────────────────
print("\n[T4] _handle_webhook_delete：容器级删除先向 Emby 探测容器是否仍在")
# ─────────────────────────────────────────────
_del = _grab_method(_SRC, "_handle_webhook_delete")
check("fetch_item" in _del, "删除处理中调用 Emby fetch_item 探测")
check('itype.lower() in ("series", "season", "folder")' in _del,
      "仅对容器类型（series/season/folder）做探测")
check("_emby_client_for_server" in _del, "按 server_id 取对应 Emby 客户端")
# v4.6.98/99：容器存在性改三态；「容器仍在」分支入口 = if _cst == ITEM_FOUND:
_idx = _del.find("if _cst == ITEM_FOUND:")
check(_idx > 0, "容器分支改用三态判定（if _cst == ITEM_FOUND:）")
_seg = _del[max(0, _idx - 1600):_idx + 3000]
check("_reconcile_missing_episodes" in _seg and "mark_deleted_episodes_by_prefix" in _seg,
      "容器仍在 Emby → 只标真正消失的那几集（v4.6.85 起），不整树标记")
check('_ct == "season"' not in _seg,
      "v4.6.99：已移除「季容器枚举不到 → 整季标记」的危险退化（枚举不可信时一律不标记）")
check("_norm_pre" in _seg, "日志带路径便于排查")

# ─────────────────────────────────────────────
print("\n[T5] _api_db_purge_missing：0 条时也清掉残留的脏失效事件")
# ─────────────────────────────────────────────
_purge = _grab_method(_SRC, "_api_db_purge_missing")
check("_cleanup_dirty_webhook_events" in _purge, "「清除失效」里接入脏事件清理")
_i0 = _purge.find("_miss == 0")
_seg0 = _purge[_i0:_i0 + 2200]
check("_cleanup_dirty_webhook_events" in _seg0 and "events_cleared" in _purge,
      "0 条分支内也会清理并回报已清事件数")

# ─────────────────────────────────────────────
print("\n[T6] 通知口径：recovered 为计数、文案「个（重新入库）」")
# ─────────────────────────────────────────────
_note = _grab_method(_SRC, "_notify_webhook_completed")
check("recovered: int = 0" in _note, "_notify_webhook_completed 的 recovered 为计数（int）")
check("recovered: int = 0" in _grab_method(_SRC, "_add_notification_to_queue"),
      "_add_notification_to_queue 的 recovered 为计数（int）")
check('"recovered": int(recovered or 0)' in _grab_method(_SRC, "_add_notification_to_queue"),
      "入队时按计数保存（不再是布尔）")
check("sum(int(i.get(\"recovered\") or 0) for i in items)" in _SRC,
      "聚合时按计数求和（此前是「有几条带标记」= 恒 1）")
check("其中已恢复被删条目 {_rec} 个（重新入库）" in _SRC, "文案改为「已恢复被删条目 N 个（重新入库）」")
check('recovered=res.get("recovered", 0) > 0' not in _SRC, "调用点不再传布尔")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
