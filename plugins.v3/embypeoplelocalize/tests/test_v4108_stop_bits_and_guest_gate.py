r"""
v4.6.108 回归测试（①终止后状态永久卡 STOPPING ②「客串」门禁漏进导演/编剧/制片）

① 用户实测日志：
     17:03:03  [Translate] 已终止：归还消费许可，回到待命        ← 许可已正常归还
     17:03:29  [Config] 保存（任务运行中，下个任务生效）          ← 26 秒后仍判「有任务」
   现象：终止后界面一直「有任务」，所有「开始/改数据」都被拦（连保存配置都提示任务运行中），
   限流窗口早就过了也不能继续，**必须重启插件**。
   根因（LIB-015）：`_api_stop` 会置 `_stop_requested` / 各任务停止位（_scan_stop/_tx_stop/
   _wb_stop/_pool_stop/_probe_stop），而**没有任何地方在停完之后复位它们**；`_task_state()`
   又把这些位当作 STOPPING → `data_mutation_locked` 恒为 True → 所有启动型接口被拦；
   而唯一能复位它们的 `_launch_*` 又被这个门拦着 → 死锁，只能重启。
   修复：`_task_state()` 在「确认没有任何任务在跑、也没有未归还的翻译许可」时，
   调用 `_clear_transient_stop_bits()` 复位这些请求位，状态自愈回 IDLE。

② 用户实测：扫描/翻译/人名池都只开了「演员 + 客串」，池里却出现「导演 / 编剧 / 制片」
   （并永久挂着「剩余 2 条」翻译不掉）。
   根因（LIB-016）：扫描读 `<actor>` 时，入池门禁用 `_kind`（只要不是演员类就算「客串」），
   而落库的 `person_type` 是真实职位 —— Emby 常把导演/编剧/制片写成
   `<actor><type>Director</type></actor>`，于是**开着「客串」就把它们一并收进池**。
   修复：门禁按真实职位取开关键（`_tx_switch_key`），未知职位才退回原兜底；
   并让「按当前设置重筛池」按**翻译范围**取白名单 + 连无 ID 缓存行一起清理。

覆盖：
  T1 行为级（逐字执行真实 _task_state / _clear_transient_stop_bits / _task_running）
  T2 行为级（逐字执行 _tx_switch_key）+ 门禁矩阵
  T3 行为级（真 SQLite）：remove_non_matching_types 的 include_no_id 口径
  T4 源码级：门禁改用 _sw_key；重筛取翻译范围白名单 + include_no_id + 空白名单拒绝
"""
import sys
import types
import tempfile
import importlib.util
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl108_"))
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
_TM = (PLUGIN_DIR / "task_manager.py").read_text(encoding="utf-8")

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

_spec = importlib.util.spec_from_file_location("epl108_db", PLUGIN_DIR / "db.py")
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


def _grab(src_text, name, indent=4):
    """取类方法并去掉一级缩进 → 可直接 exec。"""
    lines = src_text.splitlines()
    i0 = next(i for i, ln in enumerate(lines) if ln.startswith(" " * indent + f"def {name}("))
    i1 = len(lines)
    for i in range(i0 + 1, len(lines)):
        if lines[i].startswith(" " * indent + "def ") or lines[i].startswith(" " * indent + "async def "):
            i1 = i
            break
        if indent == 4 and lines[i].startswith("    def "):
            i1 = i
            break
    return "\n".join(ln[indent:] if len(ln) >= indent else ln for ln in lines[i0:i1])


print("=" * 72)
print("v4.6.108 回归测试（停止位自愈 / 客串门禁）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] 行为级（逐字执行 _task_state / _clear_transient_stop_bits / _task_running）")
# ─────────────────────────────────────────────
_ns = {}
exec("class _Holder:\n"
     + "\n".join("    " + ln for ln in _grab(_TM, "_task_running").splitlines()) + "\n"
     + "    _TASK_FLAGS = " + str({"scan": "_scan_running", "translate": "_translate_running",
                                  "writeback": "_writeback_running", "pool": "_pool_running",
                                  "probe": "_probe_running"}) + "\n",
     _ns)
exec("class _Holder2:\n"
     + "\n".join("    " + ln for ln in _grab(_SRC, "_clear_transient_stop_bits").splitlines()) + "\n"
     + "\n".join("    " + ln for ln in _grab(_SRC, "_task_state").splitlines()) + "\n",
     _ns)


class Stub(_ns["_Holder"], _ns["_Holder2"]):
    _TASK_FLAGS = _ns["_Holder"]._TASK_FLAGS

    def __init__(self, **kw):
        self._scan_running = False
        self._translate_running = False
        self._writeback_running = False
        self._pool_running = False
        self._probe_running = False
        self._stop_requested = False
        self._wb_stop = False
        self._scan_stop = False
        self._tx_stop = False
        self._pool_stop = False
        self._probe_stop = False
        self._tx_requested = False
        self._pool_pulling = False
        for k, v in kw.items():
            setattr(self, k, v)


check(callable(getattr(Stub, "_task_state", None)), "已逐字提取并编译真实的 _task_state")

# 场景 A：用户点过「终止」，各停止位被置 True，但此刻已无任务在跑、许可也已归还
_p = Stub(_stop_requested=True, _wb_stop=True, _tx_stop=True, _scan_stop=True)
check(_p._task_state()["state"] == "IDLE", "终止且已停完 → 状态自愈回 IDLE（不再卡 STOPPING）")
check(_p._task_state()["data_mutation_locked"] is False, "不再锁数据变更（能开始新任务 / 保存配置）")
check(_p._stop_requested is False and _p._wb_stop is False
      and _p._tx_stop is False and _p._scan_stop is False,
      "停止位已被复位（下次任务不受影响）")

# 场景 B：翻译仍在跑（许可未归还）→ 绝不能复位，否则停止请求会丢
_q = Stub(_stop_requested=True, _tx_stop=True, _tx_requested=True)
_st = _q._task_state()
check(_st["state"] == "STOPPING", "许可未归还（停止还在生效中）→ 保持 STOPPING")
check(_q._tx_stop is True, "此时**不**复位停止位（停止请求不会丢）")
check(_st["data_mutation_locked"] is True, "停止中仍锁数据变更（符合预期）")

# 场景 C：有任务在跑（如拉取人名）→ 同样不复位
_r = Stub(_stop_requested=True, _pool_stop=True, _pool_running=True)
_r._task_state()
check(_r._stop_requested is True and _r._pool_stop is True, "有任务在跑 → 不复位（等它自己停完）")

# 场景 D：真的停完（无停止位）→ 状态 IDLE
_ok = Stub()
check(_ok._task_state()["state"] == "IDLE" and _ok._task_state()["data_mutation_locked"] is False,
      "正常待命 → IDLE 且不锁")

# ─────────────────────────────────────────────
print("\n[T2] 行为级（逐字执行 _tx_switch_key）+ 入池门禁矩阵")
# ─────────────────────────────────────────────
_sw = {}
exec(_grab(_SRC, "_tx_switch_key"), _sw)
SWITCH = {"Actor": "actor", "VoiceActor": "actor", "GuestStar": "guest",
          "Director": "director", "Writer": "writer", "Producer": "producer"}
_ns2 = dict(_sw, **{"self": type("S", (), {"TX_TYPE_SWITCH": SWITCH})()})
from types import MethodType
_key = MethodType(_sw["_tx_switch_key"], _ns2["self"])
check(callable(_key), "已逐字提取并编译真实的 _tx_switch_key")

check(_key("Actor") == "actor" and _key("VoiceActor") == "actor", "Actor / VoiceActor → actor")
check(_key("actor") == "actor" and _key("producer") == "producer", "小写职位同样识别（大小写不敏感）")
check(_key("Director") == "director" and _key("Writer") == "writer", "Director → director / Writer → writer")
check(_key("Producer") == "producer", "Producer → producer（不再被当成「客串」）")
check(_key("GuestStar") == "guest", "GuestStar → guest")
check(_key("Star") == "" and _key("Mystery") == "", "未知职位 → 空（由调用方兜底）")

# 用户实测配置：只开 演员 + 客串
_TR = {"person": True, "role": True, "actor": True, "guest": True,
       "director": False, "writer": False, "producer": False}


def _gate(a_type):
    """复刻扫描入池门禁：真实职位取开关键，未知才退回「演员类=actor / 其它=guest」"""
    _is_guest = a_type.lower() not in ("actor", "voiceactor", "star")
    _kind = "guest" if _is_guest else "actor"
    return bool(_TR.get(_key(a_type) or _kind))


check(_gate("Actor") is True, "「演员」职位 → 入池（演员开关开）")
check(_gate("GuestStar") is True, "「客串」职位 → 入池（客串开关开）")
check(_gate("Director") is False, "「导演」职位 → **不入池**（导演开关没开）—— 修好前会漏进来")
check(_gate("Writer") is False, "「编剧」职位 → 不入池（修好前会漏进来）")
check(_gate("Producer") is False, "「制片」职位 → 不入池（修好前会漏进来）")
check(_gate("Mystery") is True, "未知职位 → 仍按「客串」兜底（保留原语义）")

# ─────────────────────────────────────────────
print("\n[T3] 行为级（真 SQLite）：remove_non_matching_types 的 include_no_id 口径")
# ─────────────────────────────────────────────
pdb = dbm.NameMapDb()
pdb.ensure_table()
PID = "EPL108"
_rows = [
    ("无名演员", "Actor", ""),        # 扫描入库（无 Emby Person ID）
    ("无名制片", "Producer", ""),      # ← 从「客串」漏进来的那条
    ("无名未分类", "", ""),
    ("有名导演", "Director", "EM1"),   # 拉取入库（有 ID）
    ("有名演员", "Actor", "EM2"),
]
for _nm, _pt, _pid_x in _rows:
    pdb.upsert_pool_person(plugin_id=PID, server_id="S1", emby_person_id=_pid_x,
                           name_original=_nm, name_current=_nm, name_zh="",
                           person_type=_pt, person_types=([_pt] if _pt else []),
                           source="", translation_status="pending")


def _names():
    return sorted(str(r.get("name_original")) for r in
                  (pdb.list_pool(plugin_id=PID, size=200).get("items") or []))


_ALLOW = ["Actor", "VoiceActor", "GuestStar"]
_n1 = pdb.remove_non_matching_types(plugin_id=PID, allowed_types=_ALLOW, keep_unknown=True)
_left1 = _names()
check(_n1 == 1 and "有名导演" not in _left1, f"默认口径只清「有 ID」的类型不符行（实际清 {_n1} 条）")
check("无名制片" in _left1, "无 ID 缓存行默认不动（旧行为，保底不变）")

_n2 = pdb.remove_non_matching_types(plugin_id=PID, allowed_types=_ALLOW,
                                    keep_unknown=True, include_no_id=True)
_left2 = _names()
check(_n2 == 1 and "无名制片" not in _left2, f"include_no_id=True → 漏进来的无 ID 制片行被清掉（实际清 {_n2} 条）")
check("无名演员" in _left2, "无 ID 演员行保留（类型在白名单内）")
check("无名未分类" in _left2, "未分类行保留（keep_unknown=True）")
check("有名演员" in _left2, "有 ID 演员行保留")

# ─────────────────────────────────────────────
print("\n[T4] 源码级：门禁改用 _sw_key + 重筛取翻译范围白名单")
# ─────────────────────────────────────────────
check("if _pool_on and n and bool(_tr.get(_sw_key)):" in _SRC,
      "扫描入池门禁已按真实职位取开关键（_sw_key）")
check("if _pool_on and n and bool(_tr.get(_kind)):" not in _SRC,
      "旧的「一律按 _kind（客串）」门禁已移除")
check("_sw_key = self._tx_switch_key(a_type) or _kind" in _SRC,
      "未知职位仍退回原兜底（actor / guest）")
check("def _tx_switch_key(self, person_type: str) -> str:" in _SRC, "新增 _tx_switch_key 辅助")
check("_types = [t for t, k in self.TX_TYPE_SWITCH.items() if bool(_tr_now.get(k))]" in _SRC,
      "重筛白名单改取「翻译范围」的类型开关（与按钮文案一致）")
check("keep_unknown=_keep_unknown, include_no_id=True" in _SRC,
      "重筛连无 ID 缓存行一起清理")
check("重筛会把池清空，已拒绝" in _SRC, "白名单为空时明确拒绝（不静默清空池）")
check("include_no_id: bool = False" in (PLUGIN_DIR / "db.py").read_text(encoding="utf-8"),
      "db.remove_non_matching_types 新增 include_no_id（默认 False，向后兼容）")

print("\n" + "=" * 72)
print(f"结果：PASS {_N[0] - _N[1]} / {_N[0]}，FAIL {_N[1]}")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
