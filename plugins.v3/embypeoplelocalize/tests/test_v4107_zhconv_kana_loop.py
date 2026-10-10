r"""
v4.6.107 回归测试（「繁转简」把汉字+假名的日文名改一半 → 池行永远待翻译、死循环）

用户实测（人名池 9 条一直不收敛）：
    人名池批量翻译已启动：9 个待翻人名
    翻译 worker：本轮 7 条（LLM 0 条 · 繁转简 6 条）剩余待翻约 0 条
    翻译 worker：本轮 2 条（LLM 0 条 · 繁转简 2 条）剩余待翻约 4 条
    翻译 worker：本轮 2 条（LLM 0 条 · 繁转简 2 条）剩余待翻约 4 条   ← 无限重复
卡住的名字：紗倉のり子 / 中島なつみ / 雛坂ひかる / 金庭こず恵 / 飯田ヒカル / 廣原ふう …

根因（LIB-014）：worker 收词前的「繁转简」预步骤只判 `zhconv(t) != t` 就当命中并计入完成：
    _z = self._zhconv_convert(_t)
    if _z and _z != _t:            # ← 只要变了就算翻完
        _bucket["hits"][_oid] = (_z, "zhconv")
        continue                   # ← 于是这些词条**永远不会送去 LLM**
而这些名字是「汉字 + 假名」，zhconv 只转汉字部分（雛坂ひかる → 雏坂ひかる），假名原样留着；
池/库的「有效译文」判定（db._SQL_ZH_VALID）**明确排除含假名的 name_zh** → 行永远停在
「🔴 待翻译」→ 下一轮又被收进来、再判一次繁转简命中 …… 死循环，且 LLM 恒为 0 条。

修复：新增 `_zhconv_final_ok(text, conv)`（与 db._SQL_ZH_VALID 同口径：译文 ≠ 原文
且不含假名），繁转简 / 池命中都必须过这一关；不合格就放行给 LLM，由模型给出真正的中文名。

覆盖：
  T1 行为级（真 SQLite）：含假名的译文不算「有效」→ 仍待翻译；换成真中文名 → 立刻脱离待翻译
  T2 行为级（逐字执行 _zhconv_final_ok）：用户实测那批名字的真实判定
  T3 源码级：worker 主路径（池命中 / 繁转简）都过这道关；池回写只写有效译文
"""
import sys
import types
import tempfile
import importlib.util
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl107_"))
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")


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


class _S:
    CONFIG_PATH = str(TMP)


_c.settings = _S()
sys.modules.update({"app": _m, "app.sdk": _s, "app.sdk.logging": _l, "app.sdk.config": _c})

_spec = importlib.util.spec_from_file_location("epl107_db", PLUGIN_DIR / "db.py")
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


def _grab_method_dedent(name):
    """取类方法并去掉一级缩进（4 空格）→ 可直接 exec 成模块级函数。"""
    lines = _SRC.splitlines()
    i0 = next(i for i, ln in enumerate(lines) if ln.startswith(f"    def {name}("))
    i1 = len(lines)
    for i in range(i0 + 1, len(lines)):
        if lines[i].startswith("    def ") or lines[i].startswith("    async def "):
            i1 = i
            break
    return "\n".join(ln[4:] if len(ln) >= 4 else ln for ln in lines[i0:i1])


print("=" * 72)
print("v4.6.107 回归测试（繁转简残留假名 → 池行死循环）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] 行为级（真 SQLite）：含假名的译文不算「有效译文」")
# ─────────────────────────────────────────────
pdb = dbm.NameMapDb()
pdb.ensure_table()
PID = "EPL107"
pdb.upsert_pool_person(plugin_id=PID, server_id="S1", emby_person_id="E1",
                       name_original="雛坂ひかる", name_current="雛坂ひかる", name_zh="",
                       person_type="Actor", person_types=["Actor"],
                       source="", translation_status="pending")
_st0 = pdb.count_pool_status(plugin_id=PID)
check(_st0["pending"] == 1, f"初始「待翻译」= 1，实际 {_st0['pending']}")

# 场景 A：写回「繁转简一半」的结果（假名残留）→ 池仍判待翻译（这就是死循环的由来）
pdb.set_pool_zh(plugin_id=PID, server_id="S1", emby_person_id="E1",
                name_original="雛坂ひかる", name_zh="雏坂ひかる", source="zhconv")
_st1 = pdb.count_pool_status(plugin_id=PID)
check(_st1["pending"] == 1,
      f"「雏坂ひかる」（假名残留）不算有效译文 → 仍是待翻译 {_st1['pending']}（死循环前提）")

# 场景 B：写回真正的中文名 → 立刻脱离待翻译
pdb.set_pool_zh(plugin_id=PID, server_id="S1", emby_person_id="E1",
                name_original="雛坂ひかる", name_zh="雏坂光", source="llm")
_st2 = pdb.count_pool_status(plugin_id=PID)
check(_st2["pending"] == 0, f"「雏坂光」（无假名）→ 脱离待翻译，实际 {_st2['pending']}")
check(_st2["translated"] + _st2["no_change"] + _st2["synced"] >= 1,
      "已计入其他状态（不再是 🔴 待翻译）")

# ─────────────────────────────────────────────
print("\n[T2] 行为级（逐字执行 _zhconv_final_ok）：判定口径")
# ─────────────────────────────────────────────
_ns = {"_is_kana_text": dbm._is_kana_text}
exec(_grab_method_dedent("_zhconv_final_ok"), _ns)   # noqa: S102 - 测试：逐字执行生产代码
_ok = types.MethodType(_ns.get("_zhconv_final_ok"), object())   # 绑一个空 self（方法体不用 self 状态）
check(callable(_ok), "已逐字提取并编译真实的 _zhconv_final_ok")

check(_ok("雛坂ひかる", "雏坂ひかる") is False, "雛坂ひかる → 雏坂ひかる（假名残留）不放过")
check(_ok("紗倉のり子", "纱仓のり子") is False, "紗倉のり子 → 纱仓のり子（假名残留）不放过")
check(_ok("廣原ふう", "广原ふう") is False, "廣原ふう → 广原ふう（假名残留）不放过")
check(_ok("雛坂ひかる", "雏坂光") is True, "雛坂ひかる → 雏坂光（真中文名）放过")
check(_ok("藤原啓治", "藤原启治") is True, "纯汉字繁转简（藤原啓治 → 藤原启治）放过")
check(_ok("Tom Hanks", "Tom Hanks") is False, "译名等于原文 → 不算命中（交给 LLM）")
check(_ok("", "任何") is False, "空原文 → 不放过")
check(_ok("水桥 かおり", "水橋 かおり") is False, "转完仍是假名 → 不放过")

try:
    import zhconv
    _conv = zhconv.convert("雛坂ひかる", "zh-cn")
    print(f"  [INFO] 真实 zhconv：雛坂ひかる → {_conv}")
    check(_ok("雛坂ひかる", _conv) is False,
          f"用真实 zhconv 结果（{_conv}）复验：不放过 → 会走 LLM")
except Exception as _e:
    print(f"  [SKIP] 未安装 zhconv（{_e}），跳过真实转换复验")

# ─────────────────────────────────────────────
print("\n[T3] 源码级：worker 主路径两道关 + 池回写只写有效译文")
# ─────────────────────────────────────────────
check("def _zhconv_final_ok(self, text: str, conv: str) -> bool:" in _SRC,
      "新增 _zhconv_final_ok 辅助")
check("if _hit and self._zhconv_final_ok(_t, _hit[0]):" in _SRC,
      "池命中也必须过「有效译文」关（防历史含假名脏数据当命中）")
check("if self._zhconv_final_ok(_t, _z):" in _SRC,
      "繁转简必须产出有效中文名才算命中，否则放行给 LLM")
check('if _z and _z != _t:\n                _bucket["hits"][_oid] = (_z, "zhconv")' not in _SRC,
      "旧的「只要 zhconv 变了就算命中」已移除")
check("for _cand in (_p_zh.get(_t), _idz):" in _SRC,
      "池回写优先用本轮新译文，且只回写有效译文（含假名的身份名不再回写）")
check('_is_kana_text' in _SRC.split("def _zhconv_final_ok")[1][:900],
      "_zhconv_final_ok 复用 db 的 _is_kana_text（与池/库判定同源）")

print("\n" + "=" * 72)
print(f"结果：PASS {_N[0] - _N[1]} / {_N[0]}，FAIL {_N[1]}")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
