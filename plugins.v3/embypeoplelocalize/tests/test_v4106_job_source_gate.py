r"""
v4.6.106 回归测试（作业进度「分母」按来源门控 —— 人名池任务的进度不再算库内人头）

用户实测：
    AI 翻译  40 / 1883 · 紗倉のり子
    job=... source=pool scope=both items=303 terms=1883 收到翻译许可，开始消费待翻词条
    （目标 = 人名池 · 第一排人名；人名 59 / 角色 1812 / 池 12）
用户疑问：「明明（池）剩 12 个了，为什么显示 1883？计算又不对。」

根因（LIB-013）：worker 开始/结束用的是
    self._tx_pending_snapshot(pool_gate=True, ...)
—— `pool_gate` 只门控**池**统计，库内 person/role 一律计入 → `total = 59 + 1812 + 12 = 1883`。
于是「人名池 · 批量翻译」的进度分母包含了它**永远不会消费**的库内词条：
进度永远到不了 100%、收尾永远是 PARTIAL、日志里的「剩余」也把库内人头算进去。

修复：新增 `source_gate` 参数 —— 与 `pool_gate` 同理，把**库内**统计也按本次作业来源门控；
仅 worker 开始 / 收尾两处传 True，徽章 / 明细 / 预估不传（库页照常显示「全部待翻」）。

覆盖：
  T1 行为级（真 SQLite + 逐字执行 _tx_pending_snapshot）：三种来源各自的分母
  T2 源码级：source_gate 参数与门控表达式；只有 worker 两处传 True
"""
import sys
import types
import tempfile
import importlib.util
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl106g_"))
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

_spec = importlib.util.spec_from_file_location("epl106g_db", PLUGIN_DIR / "db.py")
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
print("v4.6.106 回归测试（作业进度分母按来源门控）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] 行为级（真 SQLite + 逐字执行 _tx_pending_snapshot）")
# ─────────────────────────────────────────────
PID = "Stub"   # = self.__class__.__name__（快照按类名当 plugin_id 查库）

# 库内：1 个电影条目，3 个待翻人名
_pdb = dbm.PeopleDb()
_pdb.ensure_table()
_pdb.upsert_people(plugin_id=PID, server_id="", item_id="A1", item_type="Movie", title="剧A",
                   people=[{"Type": "Actor", "before_name": n} for n in ("AAA", "BBB", "CCC")])
# 池：3 个待翻人名
_nmdb = dbm.NameMapDb()
_nmdb.ensure_table()
for _i, _n in enumerate(("Water Bridge", "Tom Hanks", "Meryl Streep")):   # 非中文 → 计「待翻译」
    _nmdb.upsert_pool_person(plugin_id=PID, server_id="S1", emby_person_id=f"E{_i}",
                             name_original=_n, name_current=_n, name_zh="",
                             person_type="Actor", person_types=["Actor"],
                             source="", translation_status="pending")


# 逐字执行真实的 _tx_pending_snapshot（去缩进后绑到最小 self 桩上）
def _grab_method_dedent(name):
    lines = _SRC.splitlines()
    i0 = next(i for i, ln in enumerate(lines) if ln.startswith(f"    def {name}("))
    i1 = len(lines)
    for i in range(i0 + 1, len(lines)):
        if lines[i].startswith("    def ") or lines[i].startswith("    async def "):
            i1 = i
            break
    return "\n".join(ln[4:] if len(ln) >= 4 else ln for ln in lines[i0:i1])


_ns = {"NameMapDb": dbm.NameMapDb, "logger": logger, "Dict": dict, "List": list}
exec(_grab_method_dedent("_tx_pending_snapshot"), _ns)   # noqa: S102 - 测试：逐字执行生产代码
_snapshot_fn = _ns.get("_tx_pending_snapshot")
check(callable(_snapshot_fn), "已逐字提取并编译真实的 _tx_pending_snapshot")


class Stub:
    TX_TYPE_SWITCH = {"Actor": "actor", "VoiceActor": "actor", "GuestStar": "guest",
                      "Director": "director", "Writer": "writer", "Producer": "producer"}
    _tx_pending_snapshot = _snapshot_fn

    def __init__(self, source):
        self._source = source
        self._people_db = _pdb
        self._name_map_db = _nmdb

    # ── 下面是 _tx_pending_snapshot 依赖的最小桩 ──
    def _tx_source_allows(self, kind):
        return self._source in ("", "both") or str(kind) == self._source

    def _tx_scope(self):
        return "both"

    def _collect_trans_types(self):
        return {"translate": {"person": True, "role": True, "actor": True,
                              "guest": False, "director": False, "writer": False,
                              "producer": False}}

    def _tx_limits_by_level(self):
        return {}

    def _tx_exclude_episodes(self):
        return False

    def _tx_type_enabled(self, person_type, scope=""):
        return True

    def _tx_role_type_enabled(self, person_type, scope=""):
        return True

    def _skip_no_translate(self, text):
        return False


_snap_lib = Stub("library")._tx_pending_snapshot(pool_gate=True, source_gate=True)
_snap_pool = Stub("pool")._tx_pending_snapshot(pool_gate=True, source_gate=True)
_snap_both = Stub("both")._tx_pending_snapshot(pool_gate=True, source_gate=True)
_snap_old = Stub("pool")._tx_pending_snapshot(pool_gate=True)   # 旧口径（不带 source_gate）

check(_snap_lib["person"] == 3, f"【库内作业】分母含库内 3 个人名，实际 {_snap_lib['person']}")
check(_snap_lib["pool"] == 0, f"【库内作业】分母不含池（pool_gate），实际 {_snap_lib['pool']}")
check(_snap_pool["person"] == 0 and _snap_pool["role"] == 0,
      f"【人名池作业】分母不含库内人名/角色（实际 person={_snap_pool['person']} role={_snap_pool['role']}）")
check(_snap_pool["pool"] == 3, f"【人名池作业】分母 = 池 3，实际 {_snap_pool['pool']}")
check(_snap_pool["total"] == 3,
      f"【人名池作业】total = 3（不再是「库内 + 池」的虚高值），实际 {_snap_pool['total']}")
check(_snap_both["person"] == 3 and _snap_both["pool"] == 3 and _snap_both["total"] == 6,
      f"【both】两来源都算：{_snap_both['person']} + {_snap_both['pool']} = {_snap_both['total']}")
check(_snap_old["person"] == 3 and _snap_old["total"] > _snap_pool["total"],
      "不带 source_gate（徽章/预估口径）→ 仍把库内算进来（源码保持独立，这是旧口径复现）")

# ─────────────────────────────────────────────
print("\n[T2] 源码级：门控表达式 + 只有 worker 两处启用")
# ─────────────────────────────────────────────
check("source_gate: bool = False" in _SRC, "新增 source_gate 参数（默认 False，向后兼容）")
check('_src_lib = (not source_gate) or self._tx_source_allows("library")' in _SRC,
      "库内统计按来源门控（与 pool_gate 同一套 source_allows）")
check('_with_person = _sc in ("person", "both") and _src_lib' in _SRC
      and '_with_role = _sc in ("role", "both") and _src_lib' in _SRC,
      "person/role 两个「待翻」集合都受 _src_lib 约束")
check("_snap0 = self._tx_pending_snapshot(pool_gate=True, source_gate=True," in _SRC,
      "worker 开始时按来源门控（进度分母 = 本作业真正要翻的量）")
check("_snap2 = self._tx_pending_snapshot(_job_scope, pool_gate=True," in _SRC
      and "source_gate=True, with_detail=True)" in _SRC,
      "worker 收尾时同样按来源门控（剩余/完成判定不再虚高）")
check(_SRC.count("pool_gate=True, source_gate=True") == 1
      and _SRC.count("source_gate=True, with_detail=True)") == 1,
      "启用点只有 worker 开始 + 收尾两处（其余调用不带该参数）")
check("_s = self._tx_pending_snapshot(with_detail=True)" in _SRC
      and "_s = snap if isinstance(snap, dict) else self._tx_pending_snapshot()" in _SRC,
      "徽章 / 明细口径不变（不带 source_gate）")

print("\n" + "=" * 72)
print(f"结果：PASS {_N[0] - _N[1]} / {_N[0]}，FAIL {_N[1]}")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
