r"""
v4.6.109 回归测试（①「无需翻译」只活在会话内导致池永远待翻 + 每次重启重发 ②提示词逃生口 ③TMDB 404 无 ID）

用户实测（人名池 27 条一直「🔴 待翻译」、每次批量翻译都报「剩余 27 条」）：
    17:38:41  本轮 27 条判定「无需翻译」（模型如实返回原文，已计入完成、本会话不再重发）
    17:39:12  本轮无可消费词条：…｜池=False（池行被类型开关 / 已跳过项过滤…）
    17:39:16  PARTIAL 完成 88 / 剩余 27（池 27）
卡住的都是 楠木ともり / 春坂あげは（含假名日文名）、SOUNGDOK / Lia（罗马音·拉丁名）。

根因分两层：
  A. 提示词给了模型一个太宽的逃生口 ——
     池的批量翻译走「跨作品聚合（global）」结构化通道，用的内置提示词里写着
     「若 text 已是简体中文**或无需翻译**，translation 原样返回原文」；
     设置页那份 DEFAULT_PROMPT 也有「无法确认或无需翻译时保留原文」。
     于是模型对「不确定标准译名」的假名/罗马音名字**一律原样返回** —— 明明是正常要翻的（音译）。
  B. 「无需翻译」这个结论**只活在「本轮 / 本会话」**（_tx_noop_terms），没有落进池子：
     池行的 name_zh 仍为空 → 「待翻译」判据继续成立 → 永远 🔴 待翻译；
     而跳过集合是会话级的，**每次重启插件/新任务都会把它们重发一遍 LLM**（白烧 token）。

修复：
  ① 收紧两处提示词：日文假名 / 罗马音 / 拉丁字母**一律音译**，只有「原文本身已是简体中文」
     才允许原样返回；旧默认提示词逐字相同的用户自动升级（自己改过的不动）。
  ② 落**持久标记**：模型仍如实返回原文的池行 → `source='noop'`，该行不再计入「待翻译」、
     显示「无需操作」、下个任务也不再收它（set_pool_noop 带 `WHERE name_zh=''`，绝不覆盖译文）。
  ③ TMDB credits 空结果日志补上 **id + 类型**（宿主那条 404 日志不含 ID，无法定位是谁）。

覆盖：
  T1 行为级（真 SQLite）：noop 标记的状态口径（待翻→无需操作 / 不覆盖已有译文 / 计数）
  T2 行为级（Python 口径）：pool_target_name / derive_pool_status
  T3 源码级：SQL 三处与 Python 口径同源
  T4 源码级：worker 收集并落标记 + 安全约束
  T5 源码级：两处提示词都收紧 + 旧默认自动升级
  T6 源码级：TMDB 空结果日志带 ID
"""
import sys
import types
import tempfile
import importlib.util
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl109_"))
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
_DB = (PLUGIN_DIR / "db.py").read_text(encoding="utf-8")
_CONST = (PLUGIN_DIR / "constants.py").read_text(encoding="utf-8")
_LLM = (PLUGIN_DIR / "llm_client.py").read_text(encoding="utf-8")

_m = types.ModuleType("app"); _s = types.ModuleType("app.sdk")


class _L:
    def debug(self, *a, **k): pass
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass
    def log(self, *a, **k): pass


_l = types.ModuleType("app.sdk.logging"); _l.logger = _L()
_c = types.ModuleType("app.sdk.config")


class _S:
    CONFIG_PATH = str(TMP)


_c.settings = _S()
sys.modules.update({"app": _m, "app.sdk": _s, "app.sdk.logging": _l, "app.sdk.config": _c})

_spec = importlib.util.spec_from_file_location("epl109_db", PLUGIN_DIR / "db.py")
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


print("=" * 72)
print("v4.6.109 回归测试（无需翻译持久标记 / 提示词收紧 / TMDB 日志带 ID）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] 行为级（真 SQLite）：noop 持久标记的状态口径")
# ─────────────────────────────────────────────
pdb = dbm.NameMapDb()
pdb.ensure_table()
PID = "EPL109"


def _mk(nm, zh="", pid_x="", ptype="Actor"):
    return pdb.upsert_pool_person(plugin_id=PID, server_id="S1", emby_person_id=pid_x,
                                  name_original=nm, name_current=nm, name_zh=zh,
                                  person_type=ptype, person_types=[ptype],
                                  source="", translation_status="pending")


_mk("楠木ともり")          # 纯假名日文名（模型原样返回）
_mk("SOUNGDOK")            # 罗马音
_mk("上坂堇", zh="上坂堇")  # 原文已是中文（本来就「无需操作」）

_st0 = pdb.count_pool_status(plugin_id=PID)
check(_st0["pending"] == 2, f"初始「待翻译」= 2（楠木ともり / SOUNGDOK），实际 {_st0['pending']}")

# 打标：模型如实返回原文
ok1 = pdb.set_pool_noop(plugin_id=PID, server_id="S1", name_original="楠木ともり")
ok2 = pdb.set_pool_noop(plugin_id=PID, server_id="S1", name_original="SOUNGDOK")
check(ok1 and ok2, "set_pool_noop 命中并更新了这两行")
_st1 = pdb.count_pool_status(plugin_id=PID)
check(_st1["pending"] == 0, f"打标后「待翻译」= 0（不再反复报「剩余 N 条」），实际 {_st1['pending']}")
check(_st1["no_change"] == 3,
      f"这 2 行并入「无需操作」（+ 原本的中文行 = 3），实际 {_st1['no_change']}")

_lp = pdb.list_pool(plugin_id=PID, status="pending", size=100)
check(len(_lp.get("items") or []) == 0, "list_pool(status='pending') 不再返回它们（下个任务不会重发）")
_lp_all = pdb.list_pool(plugin_id=PID, size=100)
_by = {str(x.get("name_original")): x for x in (_lp_all.get("items") or [])}
check(_by.get("楠木ともり", {}).get("status") == "无需操作",
      f"池页状态显示「无需操作」，实际 {_by.get('楠木ともり', {}).get('status')}")
check(_by.get("楠木ともり", {}).get("translation_status") == "no_change",
      "translation_status = no_change（与状态推导同源）")

# 安全约束：已有译文的行绝不被标记覆盖
_mk("水桥 かおり", zh="水桥香织")
check(pdb.set_pool_noop(plugin_id=PID, server_id="S1", name_original="水桥 かおり") is False,
      "已有译文的行 → set_pool_noop 不生效（绝不覆盖译文）")
_by2 = {str(x.get("name_original")): x for x in (pdb.list_pool(plugin_id=PID, size=100).get("items") or [])}
check(_by2.get("水桥 かおり", {}).get("name_zh") == "水桥香织", "译文原样保留")

# ─────────────────────────────────────────────
print("\n[T2] 行为级（Python 口径）：pool_target_name / derive_pool_status")
# ─────────────────────────────────────────────
check(dbm.pool_target_name({"name_original": "楠木ともり", "name_zh": "", "source": "noop"})
      == "楠木ともり", "noop 行的目标名 = 原文（等价于「无需操作」）")
check(dbm.pool_target_name({"name_original": "楠木ともり", "name_zh": "", "source": "scan"})
      == "", "未打标（source=scan）仍是「待翻译」（目标名为空）")
_d = dbm.derive_pool_status({"name_original": "楠木ともり", "name_zh": "",
                             "name_current": "楠木ともり", "source": "noop"})
check(_d["ui"] == "无需操作" and _d["translation"] == "no_change",
      f"derive_pool_status → 无需操作 / no_change，实际 {_d['ui']} / {_d['translation']}")

# ─────────────────────────────────────────────
print("\n[T3] 源码级：SQL 三处与 Python 口径同源")
# ─────────────────────────────────────────────
check("_SQL_NOOP_MARK" in _DB, "db.py 定义 _SQL_NOOP_MARK")
check("_SQL_TRANS_PENDING = (f\"(NOT {_SQL_ZH_VALID} AND NOT {_SQL_IS_ZH} \"" in _DB
      and "f\"AND NOT {_SQL_NOOP_MARK})\")" in _DB,
      "「待翻译」SQL 排除 noop 标记行")
check(f"WHEN {{_SQL_NOOP_MARK}} THEN name_original" in _DB, "_SQL_TARGET 认 noop（目标名 = 原文）")
check("_SQL_NO_CHANGE = f\"(NOT {_SQL_ZH_VALID} AND ({_SQL_IS_ZH} OR {_SQL_NOOP_MARK}))\"" in _DB,
      "「无需操作」SQL 认 noop 标记行")
check('if str((rec or {}).get("source") or "").strip().lower() == "noop":' in _DB,
      "pool_target_name 认 noop（Python 与 SQL 同口径）")

# ─────────────────────────────────────────────
print("\n[T4] 源码级：worker 收集并落标记 + 安全约束")
# ─────────────────────────────────────────────
check("_noop_pool: List[tuple] = []" in _SRC, "worker 收集「池行的 noop 词条」")
check("if not _is_role2 and not _o2.get(\"item_id\"):" in _SRC,
      "只对池行（无条目身份）打标，不动库内条目")
check("nm.set_pool_noop(plugin_id=pid, server_id=_sid_n," in _SRC
      and 'emby_person_id="", name_original=_t_n)' in _SRC,
      "写回阶段调用 set_pool_noop")
check("AND (name_zh IS NULL OR name_zh='')" in _DB,
      "set_pool_noop 内部只动「还没有译文」的行（绝不覆盖译文/人工结果）")

# ─────────────────────────────────────────────
print("\n[T5] 源码级：两处提示词收紧 + 旧默认自动升级")
# ─────────────────────────────────────────────
# 只比对提示词**字面量本身**（文件里的注释会引用旧文案，不能误判）
_llm_lit = _LLM.split('STRUCTURED_PROMPT = """')[1].split('"""')[0]
check("若 text 已是简体中文或无需翻译" not in _llm_lit,
      "内置结构化提示词已删掉逃生口「或无需翻译」（池的 global 通道走它）")
check("一律音译成简体中文常用汉字" in _llm_lit and "不要原样返回原文" in _llm_lit,
      "结构化提示词明确要求音译、不许原样返回")
check("只有「text 本身已经是简体中文」时才原样返回" in _llm_lit,
      "只允许「原文本身已是简体中文」原样返回")
check("无法确认或无需翻译时保留原文" not in _CONST.split("DEFAULT_PROMPT = ")[1],
      "新版 DEFAULT_PROMPT 已删掉「无法确认或无需翻译时保留原文」")
check("DEFAULT_PROMPT_LEGACY" in _CONST and "无法确认或无需翻译时保留原文" in _CONST,
      "保留旧默认文案常量（用于「用户从未改过」的比对升级）")
check("_pt == constants.DEFAULT_PROMPT_LEGACY.strip()" in _SRC,
      "_load_config 对「与旧默认逐字相同」的用户自动升级到新提示词")
check("一律音译" in _CONST.split("DEFAULT_PROMPT = ")[1],
      "新版 DEFAULT_PROMPT 同样要求假名/罗马音一律音译")

# ─────────────────────────────────────────────
print("\n[T6] 源码级：TMDB 空结果日志带 ID")
# ─────────────────────────────────────────────
check("[TMDB] 演职员表为空：id=" in _SRC, "TMDB credits 空结果日志写入 id + 类型")
# v4.6.111：逐条 INFO 改为扫描收尾汇总一行（明细降 debug），措辞也从「已负缓存」改为「登记负缓存」
check("登记负缓存" in _SRC and "_TMDB_DEAD_TTL" in _SRC,
      "日志同时说明已登记负缓存（避免误以为会一直重打）")

print("\n" + "=" * 72)
print(f"结果：PASS {_N[0] - _N[1]} / {_N[0]}，FAIL {_N[1]}")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
