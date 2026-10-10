# -*- coding: utf-8 -*-
"""v4.6.87 回归测试：整剧入库文案加上「季数描述」。

运行：python tests/test_v487_season_range_txt.py

背景：多季剧入库时，「入库事件」/日志/通知里只写总量（N 个 nfo），看不出覆盖了哪几季。
本版新增 `_seasons_range_txt()`（连续段用「–」、不连续用「、」），并把它接进
`_translate_series_expanded` 的运行中事件、完成事件、日志与完成通知标题。

覆盖：
  T1 _seasons_range_txt 行为级：连续/不连续/单个/空/脏值
  T2 源码级：整剧入库四处文案都带季描述，且无季时不显示空括号
"""
import sys
import re
import types
import textwrap
import tempfile
import importlib.util
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl87_"))
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")

EN = "\u2013"   # en dash「–」，测试里显式构造，避免与源码字符不一致误判


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

_spec = importlib.util.spec_from_file_location("epl_db87", PLUGIN_DIR / "db.py")
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
print("v4.6.87 回归测试（整剧入库文案 + 季数描述）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] _seasons_range_txt 行为级")
# ─────────────────────────────────────────────
_ns = {"logger": logger}
exec(_grab_method(_SRC, "_seasons_range_txt"), _ns)
_srt = _ns["_seasons_range_txt"]

check(_srt([1, 2, 3, 4]) == f"S01{EN}S04", f"连续 1~4 → S01{EN}S04，实际 {_srt([1,2,3,4])!r}")
check(_srt([1, 2]) == f"S01{EN}S02", "连续两季 → S01–S02")
check(_srt([1]) == "S01", "单季 → S01")
check(_srt([1, 3]) == "S01、S03", f"不连续 → S01、S03，实际 {_srt([1,3])!r}")
check(_srt([1, 2, 4, 5, 6]) == f"S01{EN}S02、S04{EN}S06",
      f"两段连续 → S01{EN}S02、S04{EN}S06，实际 {_srt([1,2,4,5,6])!r}")
check(_srt([3, 1, 2, 2]) == f"S01{EN}S03", "乱序+重复 → 去重排序后 S01–S03")
check(_srt([10, 11, 12]) == f"S10{EN}S12", "两位数季号 → S10–S12")
check(_srt([]) == "", "空列表 → 空串")
check(_srt(None) == "", "None → 空串")
check(_srt([None, 2, "3"]) == f"S02{EN}S03", "含 None/字符串数字 → 过滤并转换 → S02–S03")
check(_srt(["abc"]) == "", "非法季号 → 空串（不抛异常）")
check(_srt({1, 2}) == f"S01{EN}S02", "集合入参也支持")

# ─────────────────────────────────────────────
print("\n[T2] 源码级：整剧入库四处文案都带季描述")
# ─────────────────────────────────────────────
_open = _grab_method(_SRC, "_translate_series_expanded")
check("_s_txt = self._seasons_range_txt(" in _open, "由 Emby 的实际集列表算出季集合")
check('e.get("ParentIndexNumber") for e in eps if isinstance(e, dict)' in _open,
      "只统计 dict 且带季号的集（脏数据不参与）")
check('_s_show = f"【{_s_txt}】" if _s_txt else ""' in _open,
      "_s_show 无季时为空串（不会出现空括号）")
check("展开为 {len(eps)} 个单集任务{_s_show}" in _open, "运行中事件文案带季描述")
check("个 nfo{_s_show}" in _open, "完成事件 / 日志文案带季描述")
check('f"{display_title}{_s_show}"' in _open, "完成通知标题带季描述")
check("Series 展开为 {len(eps)} 个单集任务（合并翻译）{_s_show}" in _open, "日志（展开行）带季描述")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
