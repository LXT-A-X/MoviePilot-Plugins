r"""
v4.6.105 回归测试（人名池「批量翻译」一轮 0 条 —— 池句柄未初始化）

用户实测：人名池卡片「待翻译 89 个 / 无需操作 3668 个」，点「批量翻译」后
  [TranslateJob] job=... source=pool scope=both ... 收到翻译许可，开始消费待翻词条
  [Translate] 本轮无可消费词条：来源=pool 范围=both｜库内 第一排=False 第二排=False
             （来源含 library=False）｜池=False（池未收：源不含 pool / 未开池翻译 / 范围不含第一排）
  [TranslateJob] ... PARTIAL ... 完成 0 / 剩余 1960（人名 59 / 角色 1812 / 池 89）

根因（LIB-011）：init_plugin 只建了 _people_db，**没有建 _name_map_db** ——
该属性一直为 None，要等「扫描 / 拉取人名 / 重拉 / 同步」等路径惰性赋值
（那些地方都写 `getattr(self, "_name_map_db", None) or NameMapDb()`）。
而翻译 worker 收池词条时用的是 `nm = getattr(self, "_name_map_db", None)`（无兜底），
池收集门 `nm is not None` 直接失败 → 池行一条都收不到。
池页/统计之所以正常，是因为它们走的是 `or NameMapDb()`。

覆盖：
  T1 源码级：init_plugin 启动即建人名池句柄（且在 NameMapDb.ensure_table() 之后）
  T2 源码级：worker 收词前有兜底（nm is None → 就地补建 + 只告警一次）
  T3 源码级：兜底位于池收集门之前（保证门一定能拿到句柄）
  T4 行为级（真 SQLite）：池数据侧正常 + 逐字执行源码里的兜底片段能拿到同一个池
  T5 源码级：「本轮无可消费词条」诊断按**具体一条**原因输出（不再并列三种可能）
"""
import sys
import os
import re
import types
import tempfile
import importlib.util
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl105_"))
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

_spec = importlib.util.spec_from_file_location("epl_db105", PLUGIN_DIR / "db.py")
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


def _grab_func(name: str) -> str:
    """取类方法完整方法体：从「    def name(」到下一个同级「    def 」（含缩进 4 空格）。"""
    mm = re.search(rf"^    def\s+{re.escape(name)}\s*\(", _SRC, re.M)
    assert mm, f"未找到 {name}"
    _start = mm.start()
    _nxt = _SRC.find("\n    def ", _start + 1)
    return _SRC[_start:(_nxt if _nxt > 0 else len(_SRC))]


print("=" * 72)
print("v4.6.105 回归测试（人名池「批量翻译」一轮 0 条：池句柄未初始化）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] 源码级：init_plugin 启动即建人名池句柄")
# ─────────────────────────────────────────────
_init = _grab_func("init_plugin")
_i_tbl = _init.find("NameMapDb.ensure_table()")
_i_hnd = _init.find("self._name_map_db = NameMapDb()")
check(_i_hnd > 0, "init_plugin 里有 self._name_map_db = NameMapDb()（启动即建，不再等惰性赋值）")
check(_i_tbl > 0 and _i_hnd > _i_tbl,
      "该赋值位于 NameMapDb.ensure_table() 之后（表先建好，句柄再挂上）")
check("self._people_db = PeopleDb()" in _init,
      "原有 _people_db 初始化保持不变（两库同点初始化）")

# ─────────────────────────────────────────────
print("\n[T2] 源码级：worker 收池词条前有兜底（句柄为空就地补建）")
# ─────────────────────────────────────────────
_rd = _grab_func("_translate_pending_round")
_i_anchor = _rd.find('nm = getattr(self, "_name_map_db", None)')
check(_i_anchor > 0, "worker 仍先取 self._name_map_db（保持原语义）")
_i_fb = _rd.find("if nm is None:", _i_anchor)
check(_i_fb > 0, "紧跟「if nm is None:」兜底分支（此前缺失 → 池静默 0 条）")
_fb_seg = _rd[_i_fb:_i_fb + 700]
check("nm = NameMapDb()" in _fb_seg, "兜底里就地补建 NameMapDb()")
check("self._name_map_db = nm" in _fb_seg, "兜底把句柄挂回 self（后续不再重复补建）")
check('_warn_once("name_map_db_lazy"' in _fb_seg, "兜底只告警一次（不刷屏）")

# ─────────────────────────────────────────────
print("\n[T3] 源码级：兜底位于池收集门之前")
# ─────────────────────────────────────────────
_i_gate = _rd.find('if (nm is not None and self._tx_source_allows("pool")')
check(_i_gate > 0, "池收集门仍是 `nm is not None and 来源含 pool ...`")
check(_i_fb < _i_gate, "兜底在池收集门**之前** —— 门一定能拿到已建好的句柄")
check("_person_in_scope = False   # v4.6.105" in _rd,
      "报告原因用的 _person_in_scope 已提前声明（异常路径也有定义）")

# ─────────────────────────────────────────────
print("\n[T4] 行为级（真 SQLite）：池数据侧正常 + 逐字执行源码里的兜底片段")
# ─────────────────────────────────────────────
_pdb = dbm.NameMapDb()
_pdb.ensure_table()
PID = "EPL105"
for _nm, _zh, _stt in (("水桥 かおり", "", "pending"),
                       ("春坂あげは", "", "pending"),
                       ("上坂堇", "上坂堇", "done")):
    _pdb.upsert_pool_person(plugin_id=PID, server_id="S1", emby_person_id="",
                            name_original=_nm, name_current=_nm, name_zh=_zh,
                            person_type="Actor", person_types=["Actor"],
                            source="", translation_status=_stt)
_lp = _pdb.list_pool(plugin_id=PID, status="pending", size=200)
_names = sorted(str(x.get("name_original")) for x in (_lp.get("items") or []))
check(_names == ["春坂あげは", "水桥 かおり"],
      f"池里 2 条待翻可被读出（数据侧没问题）：{_names}")

# 逐字执行源码里的兜底片段（去缩进后 exec），验证「句柄为空 → 补建 → 能读到同一个池」
_i_s = _rd.index("if nm is None:", _i_anchor)
_i_e = _rd.index("nm = None\n", _i_s) + len("nm = None\n")
_fb_block = _rd[_i_s:_i_e]
_fb_dedented = "\n".join(ln[8:] if ln.startswith("        ") else ln
                         for ln in _fb_block.splitlines())


class _Stub:
    """最小 self 桩：只放兜底片段真正用到的属性。"""
    def __init__(self):
        self._name_map_db = None
        self._warned = []

    def _warn_once(self, key, msg):
        self._warned.append((key, msg))


_stub = _Stub()
_ns = {"self": _stub, "NameMapDb": dbm.NameMapDb, "logger": logger, "nm": None}
exec(_fb_dedented, _ns)   # noqa: S102 - 测试：逐字执行生产代码片段
check(_stub._name_map_db is not None, "兜底执行后句柄已补建（self._name_map_db 不再为 None）")
check(_ns.get("nm") is not None, "兜底执行后局部 nm 可用（池收集门能通过）")
check(len(_stub._warned) == 1 and _stub._warned[0][0] == "name_map_db_lazy",
      "补建时只告警一次（key=name_map_db_lazy）")
_lp2 = _ns["nm"].list_pool(plugin_id=PID, status="pending", size=200)
_names2 = sorted(str(x.get("name_original")) for x in (_lp2.get("items") or []))
check(_names2 == _names, f"补建出的句柄读到的是同一个池：{_names2}")

# ─────────────────────────────────────────────
print("\n[T5] 源码级：诊断日志按具体一条原因输出")
# ─────────────────────────────────────────────
check("_pool_why" in _rd and "_pool_hint" in _rd, "新增 _pool_why / _pool_hint（原因拆分）")
for _cond in ("本次来源不含 pool",
              "「人名池翻译总开关」已关（设置页 · 人名池）",
              "目标范围不含第一排 / 「第一排人名」总开关关闭",
              "人名池句柄未初始化"):
    check(_cond in _rd, f"诊断覆盖原因：{_cond}")
check('f"（池未收：源不含 pool / 未开池翻译 / 范围不含第一排）"' not in _SRC,
      "旧的「并列三种可能」日志片段已删除（不再含糊）")
check("池={bool(pool_rows)}（{_pool_hint}）" in _rd, "日志把具体原因拼进「池=」后面")

print("\n" + "=" * 72)
print(f"结果：PASS {_N[0] - _N[1]} / {_N[0]}，FAIL {_N[1]}")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
