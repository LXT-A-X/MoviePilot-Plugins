# -*- coding: utf-8 -*-
"""v4.6.90 回归测试：整剧入库口径 —— 默认「只收新增」，可开「整剧全收」。

运行：python tests/test_v490_series_ingest_all.py

背景：Emby 在「只加了 3 集」时发的是**剧级**事件（Item=Series），v4.6.89 之前插件按「整剧展开」
把该剧 Emby 里**现有的全部集**入库（实测日志 nfo=14 = 13 集 + tvshow）→ 用户从没入库过的旧集也进来了。
v4.6.89 加了开关但**默认关**（默认整剧全收）；用户明确要：**默认只收本次新增的那几集**
（「我入库如果那个没开，只收我们那三个，10~13 集」），想整剧补齐时点「扫描」。
故 v4.6.90 把开关反过来表达为「整剧全收」，**默认关 = 只收新增**。

覆盖：
  T1 _emby_date_ts：Emby 时间戳解析（含 7 位小数秒 / Z / 无时间戳 / 乱码）
  T2 _filter_new_episodes：新集保留、旧集跳过、缺日期算新集、整批无日期退回整剧
  T3 源码级：常量 / 类属性 / 读取 / 导出 / **默认只收新增的接入方式** / 文案 / Emby 字段
  T4 前端：默认值 + v-switch（「整剧全收」默认关）
  T5 用户场景：10 旧 + 3 新 → 默认只收 3 集；开「整剧全收」→ 13 集全收
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
_CLI = (PLUGIN_DIR / "emby_client.py").read_text(encoding="utf-8")
_CONST = (PLUGIN_DIR / "constants.py").read_text(encoding="utf-8")
_VUE = (PLUGIN_DIR / "src" / "views" / "SettingsView.vue").read_text(encoding="utf-8")


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
print("v4.6.90 回归测试（整剧入库：默认只收新增 / 可开整剧全收）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] _emby_date_ts：Emby 时间戳解析")
# ─────────────────────────────────────────────
_ns = {"logger": logger, "re": re, "time": __import__("time"), "constants": _const_stub,
       "Optional": Optional, "types": types, "textwrap": textwrap}
exec(_grab_method(_SRC, "_emby_date_ts"), _ns)
exec(_grab_method(_SRC, "_filter_new_episodes"), _ns)


class _S:
    pass


_s = _S()
_s._emby_date_ts = _ns["_emby_date_ts"]
_s._filter_new_episodes = types.MethodType(_ns["_filter_new_episodes"], _s)

_ts = _s._emby_date_ts("2026-10-08T16:24:48.5607219Z")
check(_ts is not None and _ts > 0, f"Emby 风格（7 位小数秒 + Z）解析成功 → {_ts}")
_expect = datetime(2026, 10, 8, 16, 24, 48, tzinfo=timezone.utc).timestamp()
check(_ts is not None and abs(_ts - _expect) < 1, "解析值 = 该 UTC 时刻的 epoch 秒")
check(_s._emby_date_ts("") is None, "空串 → None")
check(_s._emby_date_ts(None) is None, "None → None")
check(_s._emby_date_ts("not-a-date") is None, "乱码 → None")
check(_s._emby_date_ts("2023-09-16T23:04:59.0000000Z") is not None, "无小数秒/0 小数秒也能解析")


def _iso(hours_ago: float) -> str:
    _dt = datetime.now(timezone.utc) + timedelta(hours=hours_ago)
    return _dt.strftime("%Y-%m-%dT%H:%M:%S") + ".5607219Z"


# ─────────────────────────────────────────────
print("\n[T2] _filter_new_episodes：只保留最近加入的集")
# ─────────────────────────────────────────────
_EPS = [
    {"Id": "e1", "IndexNumber": 1, "DateCreated": _iso(-30 * 24)},    # 30 天前 → 旧
    {"Id": "e10", "IndexNumber": 10, "DateCreated": _iso(-31 * 24)},  # 31 天前 → 旧
    {"Id": "e11", "IndexNumber": 11, "DateCreated": _iso(-1)},        # 1 小时前 → 新
    {"Id": "e12", "IndexNumber": 12, "DateCreated": _iso(-2)},        # 2 小时前 → 新
    {"Id": "e13", "IndexNumber": 13, "DateCreated": _iso(-72)},       # 3 天前 → 新（<7 天）
]
_keep, _old = _s._filter_new_episodes(_EPS)
check([e["Id"] for e in _keep] == ["e11", "e12", "e13"],
      f"只保留最近 7 天加入的集（11/12/13），实际 {[e['Id'] for e in _keep]}")
check(_old == 2, f"跳过 2 个旧集，实际 {_old}")

_keep2, _old2 = _s._filter_new_episodes([{"Id": "a"}, {"Id": "b"}])
check(len(_keep2) == 2 and _old2 == 0, "整批都没有 DateCreated → 退回整剧（原样保留、跳过 0）")

_keep3, _old3 = _s._filter_new_episodes(
    [{"Id": "x", "DateCreated": _iso(-1)}, {"Id": "y"}, {"Id": "z", "DateCreated": "bad"}])
check([e["Id"] for e in _keep3] == ["x", "y", "z"] and _old3 == 0,
      "有日期的算新集；缺日期/解析失败的也保留（宁可多收，不漏掉刚加的）")

_keep4, _old4 = _s._filter_new_episodes(
    [{"Id": "n", "DateCreated": _iso(-1)}, {"Id": "o", "DateCreated": _iso(-30 * 24)}])
check([e["Id"] for e in _keep4] == ["n"] and _old4 == 1, "新+旧混合：新集保留、旧集跳过")

check(_s._filter_new_episodes([]) == ([], 0), "空列表 → ([], 0)")
check(_s._filter_new_episodes(None) == ([], 0), "None → ([], 0)")

_keep5, _old5 = _s._filter_new_episodes(
    [{"Id": "p", "DateCreated": _iso(-100)}, {"Id": "q", "DateCreated": _iso(-200)}])
check([e["Id"] for e in _keep5] == ["p"] and _old5 == 1,
      "阈值 7 天：100 小时前保留 / 200 小时前跳过")

# ─────────────────────────────────────────────
print("\n[T3] 源码级：常量 / 配置 / 默认只收新增 / Emby 字段")
# ─────────────────────────────────────────────
check('CFG_SERIES_INGEST_ALL = "series_ingest_all"' in _CONST, "constants.py 定义 CFG_SERIES_INGEST_ALL")
check("DEFAULT_SERIES_INGEST_ALL = False" in _CONST, "「整剧全收」默认**关**（即默认只收新增）")
check("SERIES_NEW_ONLY_LOOKBACK_HOURS = 168" in _CONST, "回看窗口 168 小时 = 7 天")
check("_series_ingest_all: bool = constants.DEFAULT_SERIES_INGEST_ALL" in _SRC,
      "类属性声明（避免 AttributeError）")
check("self._series_ingest_all = constants.safe_bool(config.get(constants.CFG_SERIES_INGEST_ALL)" in _SRC,
      "_load_config 读取该配置")
check("constants.CFG_SERIES_INGEST_ALL: getattr(self, \"_series_ingest_all\"" in _SRC, "_dump_config 导出给前端")
check("Type,DateCreated" in _CLI, "emby_client：Series 集列表已带 DateCreated 字段")

_open = _grab_method(_SRC, "_translate_series_expanded")
_decide = _grab_method(_SRC, "_decide_series_ingest")
check("self._decide_series_ingest(pending, added_count)" in _open, "整剧展开接入三条规则决策（v4.6.92）")
check("self._filter_new_episodes(_eps)" in _decide, "决策里接入「按加入时间挑新增」")
check('if bool(getattr(self, "_series_ingest_all", False)):' in _decide,
      "「整剧全收」开着 → 决策直接全收（默认 = 只收新增）")
check("_skipped_old" in _open, "记录跳过数量")
check("跳过旧集 {_skipped_old} 个" in _open, "完成日志/事件写明跳过数")
check("if not pending:" in _open and _open.index("_decide_series_ingest") < _open.index("still = pending"),
      "决策发生在「定位 nfo」之前（不会为旧集浪费定位/重试）")

# ─────────────────────────────────────────────
print("\n[T4] 前端开关：「整剧全收」默认关")
# ─────────────────────────────────────────────
check("series_ingest_all: false" in _VUE, "SettingsView 默认值 series_ingest_all=false（默认只收新增）")
check('v-model="config.series_ingest_all"' in _VUE, "有 v-switch 开关")
check("整剧全收（包含旧集）" in _VUE, "开关标题 = 整剧全收（包含旧集）")
check("只入库本次新增的集" in _VUE, "说明写明默认行为 = 只收本次新增")
check("要补收旧集都可用" in _VUE and "「扫描」" in _VUE and "「探测库」" in _VUE and "「重新拉取」" in _VUE,
      "说明写明三个补旧集入口：扫描 / 探测库 / 重新拉取")
check('v-if="config.webhook_enabled"' in _VUE, "开关位于 Webhook 设置区（随启用状态显示）")
check("series_new_only" not in _VUE and "CFG_SERIES_NEW_ONLY" not in _CONST and "CFG_SERIES_NEW_ONLY" not in _SRC,
      "旧键 series_new_only 已彻底移除（不留双开关）")
# 作用域护栏：开关只作用于「整剧入库决策」这一条路径，扫描 / 探测库 / 重新拉取必须不受影响
_usages = re.findall(r"_series_ingest_all", _SRC)
check(len(_usages) == 5,
      f"开关作用域受限：全插件仅 5 处（类属性/默认值/读配置/导配置/决策方法），实际 {len(_usages)}")
check(_decide.count("_series_ingest_all") == 1 and "_series_ingest_all" not in _open,
      "决策方法里只用一次（展开方法不再直接感知该开关）")
check("_series_ingest_all" not in _grab_method(_SRC, "_run_probe_round"),
      "探测库（_run_probe_round）不读取该开关 → 补齐时仍全收")
check("_series_ingest_all" not in _grab_method(_SRC, "_api_db_rescan_item"),
      "重新拉取（_api_db_rescan_item）不读取该开关 → 按本地 nfo 全量重采集")
check("_series_ingest_all" not in _grab_method(_SRC, "_record_nfo_library"),
      "扫描入库（_record_nfo_library）不读取该开关 → 扫描仍全收")

# ─────────────────────────────────────────────
print("\n[T5] 用户场景：13 集里只加 3 集（旧集 10 个）")
# ─────────────────────────────────────────────
_E13 = (
    [{"Id": f"old{i}", "IndexNumber": i, "DateCreated": "2023-09-16T23:04:59.0000000Z"} for i in range(1, 11)]
    + [{"Id": f"new{i}", "IndexNumber": i, "DateCreated": _iso(-0.5)} for i in (11, 12, 13)]
)


def _expand(eps, ingest_all: bool):
    """复刻 _translate_series_expanded 的口径：整剧全收关闭 → 走只收新增过滤。"""
    if (not ingest_all) and eps:
        return _s._filter_new_episodes(eps)
    return list(eps), 0


_keep_def, _skip_def = _expand(_E13, ingest_all=False)
check([e["IndexNumber"] for e in _keep_def] == [11, 12, 13],
      f"默认（整剧全收关）→ 只收新增的 3 集，实际 {[e['IndexNumber'] for e in _keep_def]}")
check(_skip_def == 10, f"跳过 10 个旧集，实际 {_skip_def}")

_keep_all, _skip_all = _expand(_E13, ingest_all=True)
check(len(_keep_all) == 13 and _skip_all == 0, "打开「整剧全收」→ 13 集全收（补齐整部剧）")

check(_s._emby_date_ts("2023-09-16T23:04:59.0000000Z") < (datetime.now(timezone.utc).timestamp() - 168 * 3600),
      "2023 年的旧集确实早于 7 天阈值（一定被跳过，与'几天'无关）")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
