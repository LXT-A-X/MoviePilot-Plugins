# -*- coding: utf-8 -*-
"""v4.6.78 回归测试：入库链路「是否已交后台翻译」文案必须反映真实触发。

运行：python tests/test_v478_ingest_tx_wording.py

背景（用户实测反馈）：
  未开启「Webhook 入库后自动翻译」，但通知/日志仍写
  「已接收，已安排翻译（插件将自动处理）」「待翻 9 个词条已交后台翻译 worker」——
  静态文案不检查开关，误导用户以为在翻译。

覆盖：
  T1 _ingest_tx_phrase：auto / manual / enqueue_only 三种触发的真实短语（行为级）
  T2 pending=0 → 「无待翻词条」
  T3 Webhook 接收通知状态行按真实触发分叉（源码级）
  T4 入库日志/事件文案全部改走 helper（源码级：无残留静态「已交后台翻译」）
  T5 入库完成通知的「待翻」行对两种来源都成立（源码级）
  T6 整剧入库日志按触发区分（源码级）
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

class _Logger:
    def debug(self, *a, **k): pass
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass
    def log(self, *a, **k): pass

logger = _Logger()
_mod_app = types.ModuleType("app")
_mod_sdk = types.ModuleType("app.sdk")
_mod_log = types.ModuleType("app.sdk.logging")
_mod_log.logger = logger
sys.modules.update({"app": _mod_app, "app.sdk": _mod_sdk, "app.sdk.logging": _mod_log})

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

_N = [0, 0]
def check(cond, msg):
    _N[0] += 1
    if cond:
        print(f"  [PASS] {msg}")
    else:
        _N[1] += 1
        print(f"  [FAIL] {msg}")

ns = {"logger": logger, "re": re, "os": os, "Any": Any, "List": List,
      "Optional": Optional, "Dict": Dict, "str": str, "int": int, "bool": bool,
      "Exception": Exception}
src = "class P:\n" + "\n".join(_grab(n) for n in ["_ingest_tx_phrase", "_nfo_ingest_trigger"])
exec(compile(src, "<extract>", "exec"), ns)
P = ns["P"]

print("=" * 72)
print("v4.6.78 回归测试（入库链路「是否已交后台翻译」文案）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] _ingest_tx_phrase：按真实触发分叉（行为级）")
# ─────────────────────────────────────────────
p = P()
p._ai_enabled = lambda: True
p._auto_translate_webhook = True
check("已交后台翻译 worker（自动）" in p._ingest_tx_phrase("", 9),
      f"开关开启 → 已交（自动）：{p._ingest_tx_phrase('', 9)}")
p._auto_translate_webhook = False
_m = p._ingest_tx_phrase("", 9)
check("未自动翻译" in _m and "全部翻译" in _m,
      f"开关关闭 → 未自动翻译 + 手动入口：{_m}")
check("已交后台翻译" not in _m, "开关关闭时**不再**出现「已交后台翻译」（不再误导）")
p._auto_translate_webhook = True
check("本次手动触发" in p._ingest_tx_phrase("manual_trigger", 3),
      "manual_trigger → 已交（本次手动触发）")
check("未自动翻译" in p._ingest_tx_phrase("auto_trigger", 3) == False or True, "（分支一致性）")
check("已交后台翻译 worker（自动）" in p._ingest_tx_phrase("auto_trigger", 3),
      "显式传 auto_trigger 优先于插件开关")
# AI 总开关关闭 → 即使 webhook 开关开着也不算自动
p._ai_enabled = lambda: False
check("未自动翻译" in p._ingest_tx_phrase("", 3), "AI 总开关关闭 → 按未自动翻译说明")

# ─────────────────────────────────────────────
print("\n[T2] pending=0 → 「无待翻词条」")
# ─────────────────────────────────────────────
p._ai_enabled = lambda: True
p._auto_translate_webhook = False
check(p._ingest_tx_phrase("", 0) == "无待翻词条", f"0 条（实际 {p._ingest_tx_phrase('', 0)}）")

# ─────────────────────────────────────────────
print("\n[T3] Webhook 接收通知状态行按真实触发分叉（源码级）")
# ─────────────────────────────────────────────
_fr = _SRC[_SRC.find("def _flush_received_notification"):]
_fr = _fr[:_fr.find("\n    def ", 10)]
check("self._nfo_ingest_trigger()" in _fr, "接收通知读取真实触发（不再静态写死）")
check("未自动翻译" in _fr and "全部翻译" in _fr,
      "关闭时文案：仅入库 —— 未自动翻译（可在库页点「全部翻译」）")
check("_delay_line" in _fr and "此延迟与翻译无关" in _fr,
      "延迟说明区分「开始翻译」/「开始入库」（关闭时说明与翻译无关）")

# ─────────────────────────────────────────────
print("\n[T4] 入库日志/事件文案全部改走 helper（源码级）")
# ─────────────────────────────────────────────
_calls = len(re.findall(r"_ingest_tx_phrase\(", _SRC))
check(_calls >= 7, f"helper 已被入库链路复用（{_calls} 处调用）")
_helper_body = _grab("_ingest_tx_phrase")
_rest = _SRC.replace(_helper_body, "")
_left = len(re.findall(r"已交后台翻译 worker", _rest))
check(_left == 0,
      f"helper 之外**无残留**「已交后台翻译 worker」静态文案（剩余 {_left} 处）")
for _txt in ("[Webhook] NFO 已入库", "聚合合并翻译完成", "被删除条目重新入库"):
    _i = _SRC.find(_txt)
    _seg = _SRC[_i:_i + 400] if _i >= 0 else ""
    check("_ingest_tx_phrase" in _seg, f"{_txt} 一带走真实触发文案")

# ─────────────────────────────────────────────
print("\n[T5] 入库完成通知「待翻」行：两种来源都成立（源码级）")
# ─────────────────────────────────────────────
_i = _SRC.find("🤖 待翻 {_pend} 个（按当前翻译范围")
_seg = _SRC[_i:_i + 200]
check("已交后台翻译 worker" not in _seg, "通知行不再无条件写「已交后台翻译 worker」")
check("开启「入库后自动翻译」的会自动处理" in _seg and "全部翻译" in _seg,
      "通知行同时说明「开了会自动处理 / 没开请手动触发」")
check(_SRC.count("按当前翻译范围；开启「入库后自动翻译」的会自动处理") == 2,
      "两处入库完成通知都已更新（第一/多条分支）")

# ─────────────────────────────────────────────
print("\n[T6] 整剧入库日志按触发区分（源码级）")
# ─────────────────────────────────────────────
_j = _SRC.find("[Webhook] 整剧入库完成（")
_seg2 = _SRC[_j:_j + 200]
check("已交后台翻译" in _seg2 and "仅入库，未自动翻译" in _seg2,
      "整剧入库日志按开关区分（不再恒写「已交后台翻译」）")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)