# -*- coding: utf-8 -*-
"""v4.6.75 回归测试：最终发布规范（多季 UI / 任务锁与刷新 / 范围严格生效 / AI 聚合日志 / 配额与定时扫描）。

运行：python tests/test_v475_final_spec.py

对应规范：
  §二-1/2/3、§十一：多季选择器限高内部滚动、季序数字排序、切季重置懒加载 + 重建 Observer + 回 E01
  §五-1/5：任务「运行中 → 结束」立即刷新详情与统计（不再等 30s 定时器）
  §三-1/2：翻译范围严格生效（人名池 = 第一排，范围不含第一排时一律不翻）
  §四-3/§十-3：日志/通知自证「输入 N → 去重后 M → AI 请求 K」
  §四-5/6/7：429 指数退避 / 配额硬停真实阻止请求 / 重启策略明确（内存态 = 重启即恢复）
  §六-5/6：定时扫描开关与「上次执行 + 间隔」语义

覆盖：
  T1 季序数字排序 + 季内集号排序（源码级）
  T2 季选择器限高 + 内部滚动（CSS 源码级）
  T3 切季：重置计数 + 重建 Observer（先销毁）+ 滚回开头（源码级）
  T4 单季不显示季选择器（源码级）
  T5 任务结束跳变 → 立即刷新（源码级）
  T6 人名池第一排门禁（源码级：收词 + API 拒绝）
  T7 AI 聚合统计（行为级：dedup_in / dedup_uniq）
  T8 配额 / 429 策略（源码级：退避、硬停、请求前门禁、重启语义）
  T9 定时扫描：开关门禁 + last+interval 判定（源码级）
  T10 范围门禁贯穿（源码级：person/role 两排 switch 全覆盖）
"""
import sys
import os
import re
import types
import importlib.util
from pathlib import Path
from typing import Any, List, Optional, Dict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
_VUE = (PLUGIN_DIR / "src/views/LibraryView.vue").read_text(encoding="utf-8")

class _Logger:
    def debug(self, msg, *a, **k):
        if os.environ.get("EPL_DBG"):
            print(f"    [dbg] {msg}")
    def info(self, *a, **k): pass
    def warning(self, msg, *a, **k):
        if os.environ.get("EPL_DBG"):
            print(f"    [warn] {msg}")
    def error(self, *a, **k): pass
    def log(self, *a, **k): pass

logger = _Logger()
_mod_app = types.ModuleType("app")
_mod_sdk = types.ModuleType("app.sdk")
_mod_log = types.ModuleType("app.sdk.logging")
_mod_log.logger = logger
sys.modules.update({"app": _mod_app, "app.sdk": _mod_sdk, "app.sdk.logging": _mod_log})

if importlib.util.find_spec("zhconv") is None:
    _fz = types.ModuleType("zhconv")
    _fz.convert = lambda t, locale="zh-cn": str(t or "")
    sys.modules["zhconv"] = _fz

def _grab(name: str) -> str:
    m = re.search(rf"^    def {re.escape(name)}\(", _SRC, re.M)
    assert m, f"未找到方法 {name}"
    lines = _SRC[m.start():].splitlines()
    out = [lines[0]]
    for ln in lines[1:]:
        if ln.strip() == "":
            out.append(ln); continue
        if re.match(r"^    \S", ln):
            break
        out.append(ln)
    pre = []
    _head = _SRC[:m.start()].rstrip("\n").splitlines()
    while _head and re.match(r"^    @", _head[-1]):
        pre.insert(0, _head.pop())
    return "\n".join(pre + out)

def _mk_cls(cls_name, methods, extra=None):
    ns = {
        "logger": logger, "re": re, "os": os, "Any": Any, "List": List,
        "Optional": Optional, "Dict": Dict, "tuple": tuple, "set": set,
        "int": int, "str": str, "bool": bool, "len": len, "max": max, "min": min,
        "sorted": sorted, "list": list, "dict": dict, "Exception": Exception,
    }
    if extra:
        ns.update(extra)
    src = f"class {cls_name}:\n    TX_BATCH = 30\n    TX_BATCH_MIN = 1\n" + "\n".join(_grab(n) for n in methods)
    exec(compile(src, "<extract:__init__.py>", "exec"), ns)
    return ns[cls_name]

def _grab_vue(decl: str) -> str:
    """从 LibraryView.vue 提取一段 JS 函数体（decl 形如 "function selectSeason(s)"）。"""
    m = re.search(rf"^(?:async\s+)?function\s+{re.escape(decl)}\s*\(", _VUE, re.M)
    assert m, f"未找到 Vue 函数 {decl}"
    lines = _VUE[m.start():].splitlines()
    out, depth = [], 0
    for ln in lines:
        out.append(ln)
        depth += ln.count("{") - ln.count("}")
        if depth == 0 and len(out) > 1:
            break
    return "\n".join(out)

_N = [0, 0]
def check(cond, msg):
    _N[0] += 1
    if cond:
        print(f"  [PASS] {msg}")
    else:
        _N[1] += 1
        print(f"  [FAIL] {msg}")

print("=" * 72)
print("v4.6.75 回归测试（最终发布规范）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] 季序按数字排序 + 季内按集号排序（§二-2）")
# ─────────────────────────────────────────────
check(".sort((a, b) => a.season - b.season)" in _VUE,
      "季选择器按季号数字排序（S1/S2/S3/S10/S20，非字符串序）")
check("list.sort((a, b) => (a.episode ?? 0) - (b.episode ?? 0))" in _VUE,
      "季内剧集按集号数字排序（不依赖接口顺序）")

# ─────────────────────────────────────────────
print("\n[T2] 季选择器限高 + 内部滚动（§二-1 / §十一-3/4）")
# ─────────────────────────────────────────────
_m = re.search(r"\.epl-season-tabs\s*\{([^}]*)\}", _VUE)
_css = _m.group(1) if _m else ""
check(bool(_m) and "max-height" in _css, f"季选择器有限高（{_css.strip()[:60]}…）")
check("overflow-y: auto" in _css or "overflow-y:auto" in _css,
      "季选择器自身滚动（季数多时不把剧集列表顶出屏幕）")
check(re.search(r"max-height:\s*(8\d|9\d|100)px", _css) is not None,
      "限高在规范建议区间（80~100px）内")

# ─────────────────────────────────────────────
print("\n[T3] 切季：重置懒加载 + 重建 Observer + 回到本季开头（§二-3 / §十一-9）")
# ─────────────────────────────────────────────
_sel = _grab_vue("selectSeason")
check("epLoadedCount.value = Math.min(EP_PAGE_SIZE" in _sel, "切季重置该季懒加载计数")
check("setupEpObserver()" in _sel, "切季后重建观察器")
check("scrollIntoView" in _sel, "切季后滚回本季开头（E01）")
_setup = _grab_vue("setupEpObserver")
check("teardownEpObserver()" in _setup, "重建前先销毁旧 IntersectionObserver（不残留上一季观察）")
check("epAllLoaded.value" in _setup, "观察器回调按当前季的加载状态判定")

# ─────────────────────────────────────────────
print("\n[T4] 单季不显示季选择器（§十一-1）")
# ─────────────────────────────────────────────
check('v-if="epMultiSeason" class="epl-season-tabs"' in _VUE,
      "季选择器仅在多季时渲染（v-if=epMultiSeason）")
check("epMultiSeason = computed(() => epSeasons.value.length > 1)" in _VUE,
      "多季判定 = 季数 > 1")
check("{{ sg.count }}" in _VUE, "季标签显示该季集数")
check("is-active" in _VUE and "is-dead" in _VUE, "当前季高亮 + 观察期季警告样式")

# ─────────────────────────────────────────────
print("\n[T5] 任务结束 → 立即刷新详情与统计（§五-1/5）")
# ─────────────────────────────────────────────
check("_wasTaskRunning" in _VUE, "检测任务「运行中 → 结束」跳变")
_lt = _VUE[_VUE.find("async function loadStatus"):]
_lt = _lt[:_lt.find("\n}\n")]
check("refreshDetailSoft()" in _lt and "loadTxPreview(true)" in _lt and "loadItems(true)" in _lt,
      "结束瞬间立即重读详情 / 待翻统计 / 列表（不再等 30s 定时器）")

# ─────────────────────────────────────────────
print("\n[T6] 翻译范围严格生效：人名池 = 第一排（§三-1/2）")
# ─────────────────────────────────────────────
_tpr = _grab("_translate_pending_round")
check("_person_in_scope = (self._tx_scope_allows(\"person\")" in _tpr,
      "池行收词前检查目标范围含第一排")
check("and _person_in_scope):" in _tpr, "范围不含第一排 → 池行一律不收（含未分类旧行）")
check("bool(_tr.get(\"person\", True))" in _tpr, "第一排人名总开关关闭同样拦截")
_pt = _grab("_api_pool_translate")
check("当前翻译范围不含第一排人名" in _pt, "池翻译 API 明确拒绝（不再静默启动空转）")

# ─────────────────────────────────────────────
print("\n[T7] AI 聚合统计：输入 → 去重后唯一（行为级 + 源码级）")
# ─────────────────────────────────────────────
class _CountLLM:
    def __init__(self):
        self.calls = []
    def translate_items(self, items, **k):
        self.calls.append([it["id"] for it in items])
        return {it["id"]: f"译-{it['text']}" for it in items}

p = _mk_cls("EPL75P", ["_tx_occ_id", "_tx_work_id", "_tx_llm_chunks"])()
p._llm = _CountLLM()
p._tx_batch = 30
p._tx_batch_max = 30
p._tx_job_id = ""
p._failed_terms = set()
p._failed_terms_detail = {}
p._rl_ok = lambda: None
p._tx_stop_requested = lambda: False
p._ai_enabled = lambda: True
p._zhconv_convert = lambda t: t

def _occ(oid, text, kind, item_id):
    return {"occ_id": oid, "text": text, "kind": kind, "item_id": item_id,
            "server_id": "S1", "title": "剧", "person_index": 0}

_r = p._tx_llm_chunks([
    _occ("r1", "Guard", "role", "tvdb:A"), _occ("r2", "Guard", "role", "tvdb:A"),
    _occ("r3", "Guard", "role", "tvdb:A"),
    _occ("n1", "Tom", "person", "tvdb:A"), _occ("n2", "Tom", "person", "tvdb:B"),
])
check(_r.get("dedup_in") == 5, f"回报「输入条数」= 5（实际 {_r.get('dedup_in')}）")
check(_r.get("dedup_uniq") == 2, f"回报「去重后唯一条数」= 2（实际 {_r.get('dedup_uniq')}）")
check(len(p._llm.calls) == 1 and len(p._llm.calls[0]) == 2,
      f"一次请求只送唯一 2 条（实际 {p._llm.calls}）")
check("dedup_in" in _grab("_tx_translate_mixed") and 'dedup_agg["uniq"]' in _tpr,
      "轮次累计去重统计并返回")
check("输入 {_job_dedup_in} → 去重后 {_job_dedup_uniq} 条" in _SRC,
      "Job 结束日志自证「输入 → 去重后」（§十-3）")
check("🧮 AI 聚合：输入" in _SRC, "完成通知含 AI 聚合行（§四-3）")
check("_tx_job_dedup_in" in _SRC and "self._tx_job_dedup_in = 0" in _SRC,
      "Job 统计字段声明 + 复位")

# ─────────────────────────────────────────────
print("\n[T8] 429 / 配额策略（§四-5/6/7）")
# ─────────────────────────────────────────────
_rl = _grab("_rl_enter")
check("60.0 * (2 ** min(_s, 3))" in _rl and "min(600.0" in _rl,
      "429 指数退避 60→120→240→600（上限 10 分钟）")
check("random.random()" in _rl, "退避带抖动（防雪崩）")
check("300, 1800" not in _rl and "1800" in _SRC, "配额/认证类走 30 分钟硬停")
_ws = _grab("_tx_state_snapshot")
check('"paused"' in _ws and "pause_left" in _ws, "UI 可见暂停状态与剩余时间（不会显示成『翻译中』）")
check("self._tx_hard_until = time.time() + 1800" in _SRC, "硬停 1800 秒（quota / auth）")
# 请求前门禁：worker 在硬停/退避窗口内不发请求
_w = _SRC[_SRC.find("def _translate_worker"):]
_w = _w[:_w.find("\n    def ", 10)]
check("_tx_hard_until" in _w and "_rate_limited_until" in _w,
      "worker 在硬停 / 退避窗口内不发请求（§四-6）")
check("self._tx_hard_until = 0.0" in _SRC and "self._rate_limited_until = 0.0" in _SRC,
      "重启即恢复（暂停态为内存态，重启后从零开始 —— 策略明确：不持久化暂停）")
check("quota_paused" in _SRC, "Job 侧记录 quota_paused 状态（与 UI 一致）")

# ─────────────────────────────────────────────
print("\n[T9] 定时扫描开关与周期语义（§六-5/6）")
# ─────────────────────────────────────────────
_sw = _grab("_schedule_worker")
check('"_schedule_enabled"' in _sw and '"_enabled"' in _sw,
      "定时扫描线程仅在开关开启时触发（关闭后启动/刷新/Webhook 都不会触发）")
_sched = _grab("_run_scheduled_scan")
check("now - last < interval" in _sched, "按「上次执行 + 设置间隔」判定（不做日历改写）")
check("_last_full_scan_ts" in _sched, "记录上次执行时刻（已持久化，重启不重新计时）")
check("_scan_lock" in _sched and "self._is_running" in _sched, "与后台任务互斥（忙则跳本轮）")
check("self._all_nfo_roots()" in _sched, "未选媒体库时不空转（服务器/库范围真实生效）")

# ─────────────────────────────────────────────
print("\n[T10] 范围门禁贯穿两排（§三-2/3）")
# ─────────────────────────────────────────────
check("_take_person = _take_library and bool(_tr.get(\"person\", True)) and self._tx_scope_allows(\"person\")" in _tpr,
      "库内第一排：来源 + 总开关 + 目标范围三重门禁")
check("_take_role = _take_library and bool(_tr.get(\"role\", True)) and self._tx_scope_allows(\"role\")" in _tpr,
      "库内第二排：来源 + 总开关 + 目标范围三重门禁")
check("and self._tx_role_type_enabled(_o.get(\"person_type\"))" in _tpr
      and "and self._tx_type_enabled(_o.get(\"person_type\"))" in _tpr,
      "逐词条再过类型开关（范围外词条不进 LLM）")
check('if not self._tx_scope_allows("person", scope):' in _grab("_tx_type_enabled"),
      "类型判定内含目标范围检查（写回就绪判定共用同一口径）")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)