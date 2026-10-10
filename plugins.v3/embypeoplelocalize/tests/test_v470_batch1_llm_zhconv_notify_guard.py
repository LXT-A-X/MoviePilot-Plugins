# -*- coding: utf-8 -*-
"""v4.6.70 批次 1 回归测试：LLM 输出强制简体化 / 通知分排拆分 / 任务锁。

运行：python tests/test_v470_batch1_llm_zhconv_notify_guard.py

真实 __init__.py 方法体 + 注入假 zhconv（测试环境未装 zhconv，需确定性映射）。
覆盖审查报告 P0/P1：
  T1 LLM 输出被 zhconv 强制简体化 + llm_zhc 独立计数
  T2 该计数按第一/二排（bucket）正确归属
  T3 Job 统计拆分字段复位
  T4 完成通知：第一排/第二排分开、池命中/繁转简分开（不再「池/繁简命中」）
  T5 /translate/jobs/create 具备统一任务忙碌门禁
  T6 /pool/status 附统一任务快照（供人名池页同一把锁）
"""
import sys
import os
import re
import types
import importlib.util
from pathlib import Path
from typing import Any, List, Optional, Dict, Callable

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent

# ── 注入假 zhconv（确定性 繁→简 映射；测试环境未安装 zhconv） ──
_FAKE_MAP = {"臺": "台", "灣": "湾", "劇": "剧", "場": "场", "衛": "卫",
             "護": "护", "門": "门", "員": "员", "點": "点", "靈": "灵"}
_fake_zhconv = types.ModuleType("zhconv")
def _fake_convert(text, locale="zh-cn"):
    return "".join(_FAKE_MAP.get(ch, ch) for ch in str(text or ""))
_fake_zhconv.convert = _fake_convert
sys.modules["zhconv"] = _fake_zhconv

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
_mod_cfg = types.ModuleType("app.sdk.config")
class _Settings:
    CONFIG_PATH = str(PLUGIN_DIR)
_mod_cfg.settings = _Settings()
sys.modules.update({"app": _mod_app, "app.sdk": _mod_sdk,
                    "app.sdk.logging": _mod_log, "app.sdk.config": _mod_cfg})

_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")

def _grab(name: str) -> str:
    m = re.search(rf"^    def {re.escape(name)}\(", _SRC, re.M)
    assert m, f"未找到方法 {name}"
    lines = _SRC[m.start():].splitlines()
    out = [lines[0]]
    for ln in lines[1:]:
        if ln.strip() == "":
            out.append(ln)
            continue
        if re.match(r"^    \S", ln):
            break
        out.append(ln)
    pre = []
    _head = _SRC[:m.start()].rstrip("\n").splitlines()
    while _head and re.match(r"^    @", _head[-1]):
        pre.insert(0, _head.pop())
    return "\n".join(pre + out)

_METHODS = [
    "_tx_occ_id", "_tx_work_id", "_tx_llm_chunks", "_tx_translate_mixed", "_zhconv_convert",
    # v4.6.107：繁转简命中新增「有效译文」关口（残留假名不放行），一并提取真实实现
    "_zhconv_final_ok",
    "_tx_job_reset_stats",
]


def _is_kana_text(s: str) -> bool:
    """与 db._is_kana_text 同口径的假名检测（平假名 / 片假名）。"""
    return any(("\u3041" <= ch <= "\u309f") or ("\u30a0" <= ch <= "\u30ff")
               for ch in str(s or ""))

class _DummyErr(Exception):
    pass

def _mk_cls(cls_name):
    ns = {
        "logger": logger, "re": re, "os": os, "Any": Any, "List": List,
        "Optional": Optional, "Dict": Dict, "Callable": Callable,
        "HAS_ZHCONV": True,          # 已注入假 zhconv
        "zhconv": _fake_zhconv,
        "_is_kana_text": _is_kana_text,   # v4.6.107：_zhconv_final_ok 依赖
        # 供 except 子句使用的异常类型（无异常时不触发）
        "InterruptedError": InterruptedError,
        "ContextLengthExceeded": _DummyErr, "RateLimited": _DummyErr,
        "QuotaExceeded": _DummyErr, "AuthenticationError": _DummyErr,
        "LLMError": _DummyErr, "Exception": Exception,
        "int": int, "str": str, "bool": bool, "len": len, "max": max, "min": min,
        "set": set, "list": list, "dict": dict, "sorted": sorted,
    }
    src = (f"class {cls_name}:\n"
           "    TX_BATCH = 30\n"
           "    TX_BATCH_MIN = 1\n"
           + "\n".join(_grab(n) for n in _METHODS))
    exec(compile(src, "<extract:__init__.py>", "exec"), ns)
    return ns[cls_name]

_N = [0, 0]
def check(cond, msg):
    _N[0] += 1
    if cond:
        print(f"  [PASS] {msg}")
    else:
        _N[1] += 1
        print(f"  [FAIL] {msg}")

class _FakeLLM:
    def __init__(self, resp):
        self._resp = resp
    def translate_items(self, items, **k):
        return dict(self._resp)

def _base_plugin():
    p = _mk_cls("EPL70")()
    p._llm = None
    p._tx_batch = 30
    p._tx_batch_max = 30
    p._tx_job_id = ""
    p._failed_terms = set()
    p._failed_terms_detail = {}
    p._rl_ok = lambda: None
    p._tx_stop_requested = lambda: False
    p._ai_enabled = lambda: True
    return p

print("=" * 72)
print("v4.6.70 批次1 回归测试（LLM 简体化 / 通知拆分 / 任务锁）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] LLM 输出强制简体化 + llm_zhc 计数")
# ─────────────────────────────────────────────
p = _base_plugin()
p._llm = _FakeLLM({"o1": "台灣劇場", "o2": "守卫者"})   # o1 繁体、o2 已是简体
occs = [{"occ_id": "o1", "text": "Kana", "kind": "person"},
        {"occ_id": "o2", "text": "Guardian", "kind": "role"}]
_r = p._tx_llm_chunks(occs)
check(_r["llm"].get("o1") == "台湾剧场", f"LLM 返回繁体被纠正为简体：{_r['llm'].get('o1')}")
check(_r["llm"].get("o2") == "守卫者", "已是简体的保持不变")
check(_r.get("llm_zhc") == ["o1"], f"llm_zhc 只含被纠正的 o1：{_r.get('llm_zhc')}")

# ─────────────────────────────────────────────
print("\n[T2] llm_zhc 按第一/二排（bucket）归属")
# ─────────────────────────────────────────────
p = _base_plugin()
p._tx_llm_chunks = lambda *a, **k: {"llm": {"o1": "守卫者", "o2": "黑暗骑士"},
                                   "failed": [], "deferred": [], "llm_zhc": ["o1"]}
occs = [{"occ_id": "o1", "text": "Guardian", "kind": "role"},
        {"occ_id": "o2", "text": "Dark Knight", "kind": "person"}]
_mx = p._tx_translate_mixed(occs, {})
check("o1" in (_mx["role"].get("llm_zhc") or set()), "角色桶记录 o1 的简体化")
check("o1" not in (_mx["person"].get("llm_zhc") or set()), "人名桶不含 o1")
check(_mx["role"]["llm"].get("o1") == "守卫者" and _mx["person"]["llm"].get("o2") == "黑暗骑士",
      "两桶 llm 译文各自正确")

# ─────────────────────────────────────────────
print("\n[T3] Job 统计拆分字段复位")
# ─────────────────────────────────────────────
p = _base_plugin()
p._tx_job_pool = 3
p._tx_job_zhconv = 3
p._tx_job_llm_zhc = 2
p._tx_job_by_kind = {"person": {"done": 1}, "role": {"done": 22}}
p._tx_job_reset_stats()
check(p._tx_job_pool == 0 and p._tx_job_zhconv == 0 and p._tx_job_llm_zhc == 0
      and p._tx_job_by_kind is None and p._tx_job_hits == 0 and p._tx_job_done == 0,
      "拆分字段（pool/zhconv/llm_zhc/by_kind）与通用字段均已复位")

# ─────────────────────────────────────────────
print("\n[T4] 完成通知：第一排/第二排分开 + 池命中/繁转简分开")
# ─────────────────────────────────────────────
# 去掉注释行后再查（注释里会引用旧口径「池/繁简命中」作对照说明）
_CODE_ONLY = "\n".join(ln for ln in _SRC.splitlines() if not ln.lstrip().startswith("#"))
check("池/繁简命中" not in _CODE_ONLY, "代码（非注释）不再出现合并口径「池/繁简命中」")
check("_line_of('第一排'" in _SRC and "_line_of('第二排'" in _SRC,
      "通知按 第一排 / 第二排 分开输出")
check("人名池：" in _SRC and "繁转简：" in _SRC and "角色 Memory：" in _SRC,
      "池命中 / 角色记忆 / 繁转简 分开输出（v4.6.74 起每项一行）")
check("LLM 输出简体化" in _SRC, "通知含「LLM 输出简体化」独立行")
check("scope={_job_scope} person_terms=" in _SRC and "role_terms=" in _SRC,
      "日志打印 scope / person_terms / role_terms")

# ─────────────────────────────────────────────
print("\n[T5] /translate/jobs/create 任务忙碌门禁")
# ─────────────────────────────────────────────
_cre = _grab("_api_translate_job_create")
check("_task_busy_msg()" in _cre, "创建 Job 前调用 _task_busy_msg()")
check(_cre.index("_task_busy_msg()") < _cre.index("_tx_request_consume"),
      "门禁在 _tx_request_consume 之前（拒绝优先于入队）")

# ─────────────────────────────────────────────
print("\n[T6] /pool/status 附统一任务快照")
# ─────────────────────────────────────────────
_ps = _grab("_api_pool_status")
check('"is_running"' in _ps and '"tasks"' in _ps and '"scan"' in _ps,
      "/pool/status 返回 is_running + tasks（scan/translate/writeback/pool/probe）")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
