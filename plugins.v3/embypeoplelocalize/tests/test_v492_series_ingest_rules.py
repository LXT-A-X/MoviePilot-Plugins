# -*- coding: utf-8 -*-
"""v4.6.92 回归测试：整剧入库「三条规则」（通知数量全链路 + 兜底全收）。

运行：python tests/test_v492_series_ingest_rules.py

背景（用户实测）：Emby 发剧级通知只给「已添加了 N 项」，不说哪几集。用户拍板三条规则：
  ① 开了「整剧全收」→ 全收；
  ② 没开：通知数量 N ≥ 集总数 → 整剧都是新加的 → 全收；
  ③ 否则按 Emby 加入时间只收新增；④ 一个都挑不出来 → **兜底全收**（宁可多收，绝不漏收）。
触发场景：悠哉日常大王 4 季一次性入库（通知 4 项 = 剧中 4 集），因资源包自带旧时间戳
被 v4.6.90 判成全旧集 → 全跳过（一个分集都没入库）→ 本版修复。

覆盖：
  T1 _parse_added_count：中英文标题 / dict / 裸字符串 / 剧名带数字 / 无效输入
  T2 _decide_series_ingest 行为：三条规则 + 兜底（真实提取方法体 + 真实 _filter_new_episodes）
  T3 源码级：通知数量全链路（handle_webhook → schedule → worker → translate_worker → submit → expanded）
  T4 用户场景对照：悠哉日常大王 / 迷途之子 / 时间全失灵
"""
import sys
import re
import types
import textwrap
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")


class _Logger:
    def debug(self, *a, **k): pass
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass
    def log(self, *a, **k): pass


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
        _st = ln.lstrip()
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent and (_st.startswith("def ") or _st.startswith("@")):
            break
        out.append(ln)
    return textwrap.dedent("\n".join(out))


logger = _Logger()
_const_stub = types.SimpleNamespace(SERIES_NEW_ONLY_LOOKBACK_HOURS=168)

print("=" * 72)
print("v4.6.92 回归测试（整剧入库三条规则）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] _parse_added_count：解析通知里的新增数量")
# ─────────────────────────────────────────────
_ns = {"logger": logger, "re": re, "time": __import__("time"), "constants": _const_stub,
       "Optional": Optional, "types": types, "textwrap": textwrap}
exec(_grab_method(_SRC, "_parse_added_count"), _ns)
_parse = _ns["_parse_added_count"]

check(_parse("A-X 上已添加了 3 项到 迷途之子!!!!!") == 3, "用户日志原文（迷途之子）→ 3")
check(_parse("A-X 上已添加了 4 项到 悠哉日常大王") == 4, "用户场景（悠哉日常大王）→ 4")
check(_parse("已添加了3项到 某剧") == 3, "无空格「已添加了3项」→ 3")
check(_parse("4 items added to Show") == 4, "英文「N items added」→ 4")
check(_parse("Added 4 items to Show") == 4, "英文「Added N items」→ 4（大小写不敏感）")
check(_parse("86 -不存在的战区- 上已添加了 2 项到 86") == 2, "剧名带数字 → 仍取「已添加了 N 项」的 N")
check(_parse("A-X 上已移除 迷途之子!!!!! 中的 3 项") == 0,
      "删除通知措辞（上已移除…中的 N 项）→ 0（不误匹配，删除链路不用它）")
check(_parse("hello world") == 0, "无关文本 → 0")
check(_parse("") == 0, "空串 → 0")
check(_parse(None) == 0, "None → 0")
check(_parse({"json_object": {"Title": "A-X 上已添加了 4 项到 悠哉日常大王"}}) == 4,
      "webhook 报文 dict（json_object.Title）→ 4")
check(_parse({"title": "A-X 上已添加了 5 项到 某剧"}) == 5, "dict（title 字段）→ 5")
check(_parse({"json_object": {}}) == 0, "空 json_object → 0")

# ─────────────────────────────────────────────
print("\n[T2] _decide_series_ingest：三条规则 + 兜底（真实方法体）")
# ─────────────────────────────────────────────
exec(_grab_method(_SRC, "_emby_date_ts"), _ns)
exec(_grab_method(_SRC, "_filter_new_episodes"), _ns)
exec(_grab_method(_SRC, "_decide_series_ingest"), _ns)


class _Fake:
    def __init__(self, ingest_all=False):
        self._series_ingest_all = ingest_all


_Fake._emby_date_ts = staticmethod(_ns["_emby_date_ts"])
_Fake._filter_new_episodes = _ns["_filter_new_episodes"]
_Fake._decide_series_ingest = _ns["_decide_series_ingest"]


def _iso(hours_ago: float) -> str:
    _dt = datetime.now(timezone.utc) + timedelta(hours=hours_ago)
    return _dt.strftime("%Y-%m-%dT%H:%M:%S") + ".5607219Z"


_E4_NEW = [{"Id": f"n{i}", "DateCreated": _iso(-0.5)} for i in (1, 2, 3, 4)]
_E13 = ([{"Id": f"old{i}", "DateCreated": "2023-09-16T23:04:59.0000000Z"} for i in range(1, 11)]
        + [{"Id": f"new{i}", "DateCreated": _iso(-0.5)} for i in (11, 12, 13)])
_E13_OLD = [{"Id": f"old{i}", "DateCreated": "2023-09-16T23:04:59.0000000Z"} for i in range(1, 14)]

_fk = _Fake(ingest_all=False)

_keep, _old, _note = _fk._decide_series_ingest(_E4_NEW, 4)
check(len(_keep) == 4 and _old == 0 and "整剧新入库" in _note,
      f"规则②：4 集全新 + 通知 4 项 = 集数 → 全收（{_note}）")

_keep, _old, _note = _fk._decide_series_ingest(_E4_NEW, 5)
check(len(_keep) == 4 and "整剧新入库" in _note, "规则②：通知 5 项 > 4 集 → 全收（≥ 判定）")

_keep, _old, _note = _fk._decide_series_ingest(_E4_NEW, 0)
check(len(_keep) == 4 and _old == 0 and _note == "",
      "通知解析不到（0）+ 时间全命中 → 收 4 集（时间路径，无特别说明）")

_keep, _old, _note = _fk._decide_series_ingest(_E13, 3)
check([e["Id"] for e in _keep] == ["new11", "new12", "new13"] and _old == 10 and "只收新增" in _note,
      f"规则③：13 集里 3 新 + 通知 3 项 < 13 → 只收 3 集、跳过 10（{_note}）")

_keep, _old, _note = _fk._decide_series_ingest(_E13_OLD, 0)
check(len(_keep) == 13 and _old == 0 and "兜底全收" in _note,
      f"规则④：13 集全为旧时间 + 无数量信号 → 兜底全收（{_note}）")

_keep, _old, _note = _fk._decide_series_ingest(_E13_OLD, 3)
check(len(_keep) == 13 and "兜底全收" in _note,
      "规则④：通知 3 项 < 13 但时间全旧（挑不出）→ 仍兜底全收（宁可多收，绝不漏收）")

_keep, _old, _note = _fk._decide_series_ingest(_E13, 0)
check([e["Id"] for e in _keep] == ["new11", "new12", "new13"] and _old == 10,
      "13 集里 3 新 + 无数量信号 → 时间路径只收 3 集")

_keep, _old, _note = _fk._decide_series_ingest(_E13, 13)
check(len(_keep) == 13 and "整剧新入库" in _note, "规则②：通知 13 项 = 13 集 → 全收")

_fk_all = _Fake(ingest_all=True)
_keep, _old, _note = _fk_all._decide_series_ingest(_E13_OLD, 0)
check(len(_keep) == 13 and _old == 0 and _note == "", "规则①：开「整剧全收」→ 全收（无特别说明）")
_keep, _old, _note = _fk_all._decide_series_ingest(_E4_NEW, 4)
check(len(_keep) == 4 and _note == "", "规则①优先：开关开着时不走数量/时间判定")

_keep, _old, _note = _fk._decide_series_ingest([], 4)
check(_keep == [] and _old == 0 and _note == "", "空列表 → 空、无说明（不抛）")
_keep, _old, _note = _fk._decide_series_ingest(None, 4)
check(_keep == [] and _note == "", "None → 空、无说明（不抛）")

check(len(_fk._decide_series_ingest(_E4_NEW, "abc")[0]) == 4, "非法数量串 → 当 0 处理（退回时间路径，不抛）")

# ─────────────────────────────────────────────
print("\n[T3] 源码级：通知数量全链路")
# ─────────────────────────────────────────────
_hook = _grab_method(_SRC, "handle_webhook")
check("_added_n = self._parse_added_count(raw_data)" in _hook, "handle_webhook 解析通知数量")
check('"added_count": _added_n,' in _hook, "存入调度队列（新事件）")
check('self._webhook_schedule[schedule_key]["added_count"] = _added_n' in _hook,
      "重复事件时刷新数量（不覆盖为 0）")

_wk = _grab_method(_SRC, "_webhook_worker")
check('_added_n = int(pending_info.get("added_count") or 0)' in _wk, "worker 取出数量")
check("self._webhook_translate_worker(item_id, server_id, delay, _added_n)" in _wk,
      "单条路径透传（第 4 参）")
check('"added_count": _added_n})' in _wk, "同剧聚合成员带上数量")
check("self._webhook_group_translate(_grp)" in _wk, "聚合组交给 _webhook_group_translate 处理")
_gt = _grab_method(_SRC, "_webhook_group_translate")
check('_m_added = int(_m.get("added_count") or 0)' in _gt, "聚合组取成员数量（容错 int）")
check("added_count=_m_added" in _gt, "聚合组 Series 成员提交时透传")

_tw = _grab_method(_SRC, "_webhook_translate_worker")
check("added_count: int = 0" in _tw, "_webhook_translate_worker 签名带 added_count")
check("added_count=added_count" in _tw, "单集路径 Series 分支透传给 _submit_series_expand")

_se = _grab_method(_SRC, "_submit_series_expand")
check("added_count: int = 0" in _se, "_submit_series_expand 签名带 added_count")
check("server_id, display_title, added_count)" in _se, "线程池提交透传")
check("args=(client, item, item_id, server_id, display_title, added_count)" in _se, "独立线程透传")
check("self._translate_series_expanded(client, item, item_id, server_id, display_title, added_count)" in _se,
      "同步兜底透传")

_open = _grab_method(_SRC, "_translate_series_expanded")
check("added_count: int = 0" in _open, "_translate_series_expanded 签名带 added_count")
check("self._decide_series_ingest(pending, added_count)" in _open, "展开里调用三条规则决策")
check("跳过旧集 {_skipped_old} 个" in _open, "完成日志/事件仍写明跳过数")

_decide = _grab_method(_SRC, "_decide_series_ingest")
check("self._filter_new_episodes(_eps)" in _decide, "决策内部接入时间过滤")
check("_n and _n >= _total" in _decide, "规则②条件：数量 ≥ 集总数")
check("not _keep" in _decide, "规则④条件：时间挑不出任何新增")
check("兜底全收" in _decide, "规则④文案：兜底全收")

# ─────────────────────────────────────────────
print("\n[T4] 用户场景对照")
# ─────────────────────────────────────────────
_keep, _old, _note = _fk._decide_series_ingest(_E4_NEW, _parse("A-X 上已添加了 4 项到 悠哉日常大王"))
check(len(_keep) == 4, "悠哉日常大王（4 季 4 集全新增、通知 4 项）→ 全收 4 集（修复「一个没收」）")

_keep, _old, _note = _fk._decide_series_ingest(_E13, _parse("A-X 上已添加了 3 项到 迷途之子!!!!!"))
check([e["Id"] for e in _keep] == ["new11", "new12", "new13"],
      "迷途之子（13 集里新加 3 集、通知 3 项）→ 只收 3 集（保持精准）")

_keep, _old, _note = _fk._decide_series_ingest(_E13_OLD, _parse("无法解析的标题"))
check(len(_keep) == 13 and "兜底全收" in _note,
      "时间全失灵 + 数量解析不到 → 兜底全收（不再全跳过）")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)