# -*- coding: utf-8 -*-
"""v4.6.102 回归测试：翻译吞吐三缺陷（缩批钉死批大小 / 重试机会全局共享 / 译名==原名毒丸）。

运行：python tests/test_v4102_batch_retry_noop.py

背景（线上日志实测 944 行 / 781 次请求）：
  批大小分布 returned=X/Y 的 Y：1 条 516 次、2 条 191 次、3 条 48 次、30 条 11 次
  06 个 job「完成 0（写库 0 行）/ AI 请求 2 次 / 剩余 6351 纹丝不动」
  08:50:34,558 llm_client returned=1/1  ←→  08:50:34,562 插件「本批仅返回 0/1」（隔 4ms 自相矛盾）
  吞吐 0.143 条/秒（1 条批）vs 1.97 条/秒（30 条批）→ 13.8 倍差，14936 条要 29 小时。

覆盖：
  T1 源码级：旧缩批语句/旧恢复条件已删除；_partial_round 在 while 内；noop 桶已接通
  T2 行为级：真缺失 → 只重试缺失项，**批大小保持 30**（旧逻辑会钉死为 1）
  T3 行为级：缺失项排到队尾（毒丸不再堵队首）
  T4 行为级：每批独立享有 1 次缩批重试（旧逻辑整个 job 只 1 次）
  T5 行为级：译名==原名 → noop（计入完成、不记失败、不重试、登记本会话无需翻译）
  T6 行为级：单字母 / 纯符号 → _tx_untranslatable 预判
"""
import re
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")

_N = [0, 0]


def check(cond, msg):
    _N[0] += 1
    if cond:
        print(f"  [PASS] {msg}")
    else:
        _N[1] += 1
        print(f"  [FAIL] {msg}")


class _Cap:
    """捕获 WARNING 文案（用于数「缩批重试」次数）。"""

    def __init__(self):
        self.warns = []
        self.infos = []

    def debug(self, *a, **k): pass

    def info(self, *a, **k):
        self.infos.append(" ".join(str(x) for x in a))

    def warning(self, *a, **k):
        self.warns.append(" ".join(str(x) for x in a))

    def error(self, *a, **k): pass

    def log(self, *a, **k): pass


CAP = _Cap()


def _grab(name: str) -> str:
    """提取方法源码（含紧邻装饰器），保留 def 行的类的缩进，便于 dedent 后重新缩进。"""
    m = re.search(rf"^([ \t]*)def {re.escape(name)}\(", _SRC, re.M)
    assert m, f"未找到方法 {name}"
    indent = len(m.group(1))
    start = _SRC.rfind("\n", 0, m.start()) + 1
    while start > 0:
        _ps = _SRC.rfind("\n", 0, start - 1) + 1
        _line = _SRC[_ps:start].rstrip("\r\n")
        if _line.strip().startswith("@") and (len(_line) - len(_line.lstrip())) == indent:
            start = _ps
        else:
            break
    out = []
    _seen_def = False
    for ln in _SRC[start:].splitlines():
        _st = ln.lstrip()
        _ind = len(ln) - len(_st)
        if _seen_def and ln.strip() and _ind <= indent and (_st.startswith("def ") or _st.startswith("@")):
            break
        if _ind == indent and _st.startswith("def "):
            _seen_def = True
        out.append(ln)
    return textwrap.dedent("\n".join(out))


class _DummyErr(Exception):
    pass


def _mk_cls(cls_name):
    ns = {
        "logger": CAP, "re": re, "Any": Any, "List": List, "Optional": Optional, "Dict": Dict,
        # 供 except 子句使用（无异常时不触发）
        "InterruptedError": InterruptedError,
        "ContextLengthExceeded": _DummyErr, "RateLimited": _DummyErr,
        "QuotaExceeded": _DummyErr, "AuthenticationError": _DummyErr,
        "LLMError": _DummyErr, "Exception": Exception,
    }
    src = (f"class {cls_name}:\n"
           "    TX_BATCH = 30\n"
           "    TX_BATCH_MIN = 1\n"
           + "\n".join(textwrap.indent(_grab(n), "    ")
                       for n in ("_tx_llm_chunks", "_tx_noop_terms_set", "_tx_untranslatable")))
    exec(compile(src, "<extract:__init__.py>", "exec"), ns)
    return ns[cls_name]


class _FakeLLM:
    """可编排的假 LLM：记录每次批大小，按 need 决定返回哪些 id / 是否原样返回。"""

    def __init__(self, fn):
        self._fn = fn
        self.sizes = []
        self.idss = []
        self.n = 0

    def translate_items(self, items, **k):
        self.sizes.append(len(items))
        self.idss.append([it["id"] for it in items])
        self.n += 1
        return dict(self._fn(self.n, list(items)))


def _mk_occ(i, text=None):
    return {"occ_id": f"o{i}", "text": text if text is not None else f"Name{i}",
            "kind": "person", "item_id": "", "title": "", "year": ""}


def _base(fn):
    p = _mk_cls("EPL102")()
    p._llm = _FakeLLM(fn)
    p._tx_batch = 30
    p._tx_batch_max = 30
    p._tx_job_id = ""
    p._failed_terms = set()
    p._failed_terms_detail = {}
    p._rl_ok = lambda: None
    p._tx_stop_requested = lambda: False
    p._ai_enabled = lambda: True
    p._zhconv_convert = lambda s: s
    return p


print("=" * 72)
print("v4.6.102 回归测试（批大小不再被缩批钉死 / 重试每批独立 / 译名==原名=无需翻译）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] 源码级：三缺陷补丁均已落地")
# ─────────────────────────────────────────────
_body = _grab("_tx_llm_chunks")
check("_size = max(self.TX_BATCH_MIN, min(_size, len(_missing)))" not in _body,
      "旧缩批语句已删除（批大小不再由『缺了几条』决定）")
check("_pending = _rest + _miss_occs" in _body, "缺失项改为排到队尾 _pending = _rest + _miss_occs")
check("if _size < _cap and not _missing:" in _body, "恢复条件改为『本批无缺失即爬升』")
check("and len(_pending) >= _size" not in _body, "旧的恢复条件 len(_pending) >= _size 已移除")
_w = _body.index("while _pending:")
check(_body.index("_partial_round = 0") > _w,
      "_partial_round = 0 已移入 while 循环（每批独立）")
check(_body.count("_partial_round = 0") == 1, f"_partial_round 只有一处初始化（{_body.count('_partial_round = 0')}）")
_seg = _body[_body.index("if _missing and _partial_round < 1:"):_body.index("if _missing:\n")]
check("self._tx_batch = _size" not in _seg, "缩批重试路径不再改写实例属性 self._tx_batch")
check('"noop": out_noop' in _body and "_v == _src_text" in _body,
      "译名==原名 走 noop 桶（不再判为未返回）")
_b2 = _grab("_translate_pending_round")
check("_tx_noop_terms_set()" in _b2, "收词阶段拦下本会话已确认『无需翻译』的词条")
check("_tx_untranslatable(_t)" in _b2, "『无任何可译内容』词条直接登记，不占批名额")
check('_bk2.get("noop")' in _b2, "noop 计入完成（_done_ids）")

# ─────────────────────────────────────────────
print("\n[T2] 行为级：真缺失只重试缺失项，批大小保持 30（旧逻辑会钉死为 1）")
# ─────────────────────────────────────────────


def _fn_missing_first(n, items):
    out = {}
    for it in items:
        if n == 1 and it["id"] == "o0":
            continue          # 首次调用故意漏掉 o0（真缺失）
        out[it["id"]] = "译-" + it["text"]
    return out


CAP.warns.clear()
p = _base(_fn_missing_first)
occs = [_mk_occ(i) for i in range(60)]
r = p._tx_llm_chunks(occs)
check(p._llm.sizes[0] == 30, f"首批 30 条（实际 {p._llm.sizes[0]}）")
check(p._llm.sizes[1] == 30,
      f"缩批重试仍发 30 条（旧逻辑会缩成 1 条，实际 {p._llm.sizes[1]}）")
check(p._tx_batch == 30, f"实例批大小保持 30（旧逻辑会被钉成 1，实际 {p._tx_batch}）")
check(any("仅重试缺失项" in w for w in CAP.warns), "日志口径为『仅重试缺失项（批大小保持 N 不变）』")
check(len(r["failed"]) == 0, f"缺失项在重试后被补齐 → 无失败（实际 {r['failed']}）")
check(len(r["llm"]) == 60, f"60 条全部拿到译文（实际 {len(r['llm'])}）")

# ─────────────────────────────────────────────
print("\n[T3] 行为级：缺失项排到队尾（毒丸不再堵队首）")
# ─────────────────────────────────────────────


def _fn_missing_second(n, items):
    out = {}
    for it in items:
        if n == 1 and it["id"] == "o0":
            continue
        out[it["id"]] = "译-" + it["text"]
    return out


p = _base(_fn_missing_second)
p._tx_llm_chunks([_mk_occ(i) for i in range(60)])
check(p._llm.sizes == [30, 30, 1], f"批大小序列 [30, 30, 1]（实际 {p._llm.sizes}）")
check(p._llm.idss[1][0] == "o30",
      f"重试批队首是新词条 o30 —— 毒丸 o0 已排到队尾（实际队首 {p._llm.idss[1][0]}）")
check(p._llm.idss[2] == ["o0"], f"缺失项最后单独补（实际 {p._llm.idss[2]}）")

# ─────────────────────────────────────────────
print("\n[T4] 行为级：每批独立享有 1 次缩批重试（旧逻辑整个 job 只 1 次）")
# ─────────────────────────────────────────────


def _fn_missing_each_batch(n, items):
    out = {}
    for it in items:
        if it["id"] == f"o{(n - 1) * 30}":   # 每个新批次的第一条都缺失
            continue
        out[it["id"]] = "译-" + it["text"]
    return out


CAP.warns.clear()
p = _base(_fn_missing_each_batch)
p._tx_llm_chunks([_mk_occ(i) for i in range(60)])
_retries = sum(1 for w in CAP.warns if "仅重试缺失项" in w)
check(_retries >= 2, f"两个批次各自都触发了一次缩批重试（实际 {_retries} 次，旧逻辑只有 1 次）")

# ─────────────────────────────────────────────
print("\n[T5] 行为级：译名==原名 → noop（不失败 / 不重试 / 登记本会话无需翻译）")
# ─────────────────────────────────────────────


def _fn_echo(n, items):
    return {it["id"]: it["text"] for it in items}      # 全部如实返回原文


CAP.warns.clear()
p = _base(_fn_echo)
occs = [_mk_occ(0, "M"), _mk_occ(1, "Blofeld"), _mk_occ(2, "James Bond")]
r = p._tx_llm_chunks(occs)
check(p._llm.sizes == [3], f"只发 1 次请求、不再缩批重试（实际 {p._llm.sizes}）")
check(r["failed"] == [], f"不再记失败（实际 {r['failed']}）")
check(set(r["noop"].keys()) == {"o0", "o1", "o2"}, f"三条全部归入 noop（实际 {sorted(r['noop'])}）")
check(r["llm"] == {}, "noop 不进 llm 桶（不污染『LLM 翻译条数』统计）")
check(p._tx_noop_terms_set() == {"M", "Blofeld", "James Bond"},
      f"登记进本会话『无需翻译』集合（实际 {sorted(p._tx_noop_terms_set())}）")
check(not any("仅重试缺失项" in w for w in CAP.warns), "毒丸不再触发缩批重试")

# 混合：一条如实返回 + 一条真译文
def _fn_mixed(n, items):
    out = {}
    for it in items:
        out[it["id"]] = it["text"] if it["id"] == "o0" else "译-" + it["text"]
    return out


p = _base(_fn_mixed)
r = p._tx_llm_chunks([_mk_occ(0, "M"), _mk_occ(1, "Guardian")])
check(set(r["noop"].keys()) == {"o0"} and r["llm"].get("o1") == "译-Guardian",
      f"混合批：noop 与 llm 各归其位（noop={sorted(r['noop'])} llm={r['llm']}）")
check(p._llm.sizes == [2], "混合批同样只发 1 次请求")

# ─────────────────────────────────────────────
print("\n[T6] 行为级：_tx_untranslatable 预判（单字符 / 纯符号不送 LLM）")
# ─────────────────────────────────────────────
_h = _mk_cls("EPL102b")()
_f = _h._tx_untranslatable
check(_f("M") is True, "单字母 'M' → 无需翻译")
check(_f("--") is True, "纯符号 '--' → 无需翻译")
check(_f("A.") is False, "'A.' 含字母 → 交给模型判定（不预判）")
check(_f("  ") is True, "纯空白 → 无需翻译")
check(_f("123") is True, "纯数字 → 无需翻译")
check(_f("James Bond") is False, "'James Bond' 是可译词条（交给模型判定）")
check(_f("Blofeld") is False, "'Blofeld' 是可译词条（交给模型判定）")

print("\n" + "=" * 72)
print(f"结果：PASS {_N[0] - _N[1]} / {_N[0]}，FAIL {_N[1]}")
print("=" * 72)
sys.exit(1 if _N[1] else 0)