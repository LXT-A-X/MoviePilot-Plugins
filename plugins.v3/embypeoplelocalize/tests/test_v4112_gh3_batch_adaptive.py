r"""
v4.6.112 回归测试（GitHub issue #3：自适应批次「只降不升 → 永久退化成每轮 1 条」）

报告（v4.6.101）列了 6 点，其中 3 点已在 v4.6.102 修掉，本版补齐剩下 3 点：
  [已修 · v4.6.102] 2. 「译文 == 原文」（模型如实返回原文）被当成「未返回」→ 触发缩批
  [已修 · v4.6.102] 3. 缩批公式 min(_size, len(_missing)) 一缺就压成 1
  [已修 · v4.6.102] 4. 放大分支被 len(_pending) >= _size 门控 → 永远升不回去
  [本版 · GH#3-1]   1. 每轮**收词数量**用的是当前批大小 _tx_batch（应固定按设置上限）
  [本版 · GH#3-5]   5. _tx_job_reset_stats 不复位 _tx_batch → 上一个任务塌陷被新任务继承
  [本版 · GH#3-6]   6.（可选）上下文超长折半后记「本会话安全上限」，避免折半→放大→再超长抖动

本文件既守护「已修的 3 点不回退」，也验证本版新增的 3 点。
"""
import sys
import re
import types
from pathlib import Path

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


def _code(text: str) -> str:
    """去掉行注释 —— 代码里保留了「旧逻辑是 XXX」的说明注释，
    直接 in 判断会把注释里的旧写法当成"还在用"（本测试多处踩过）。"""
    _out = []
    for _ln in text.splitlines():
        _i = _ln.find("#")
        _out.append(_ln[:_i] if _i >= 0 else _ln)
    return "\n".join(_out)


def _grab_method(name, indent=4):
    lines = _SRC.splitlines()
    i0 = next(i for i, ln in enumerate(lines) if ln.startswith(" " * indent + f"def {name}("))
    i1 = len(lines)
    for i in range(i0 + 1, len(lines)):
        if lines[i].startswith(" " * indent + "def ") or lines[i].startswith(" " * indent + "async def "):
            i1 = i
            break
    return "\n".join(ln[indent:] if len(ln) >= indent else ln for ln in lines[i0:i1])


print("=" * 72)
print("v4.6.112 回归测试（GH#3 自适应批次）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] GH#3-1：每轮收词固定按设置上限（与分块大小解耦）")
# ─────────────────────────────────────────────
_i = _SRC.index("def _translate_pending_round")
_j = re.search(r"\n    def ", _SRC[_i + 10:])
_round = _SRC[_i:_i + 10 + _j.start()]   # 到下一个顶层方法为止
check('_batch = max(1, int(getattr(self, "_tx_batch_max", 0) or self.TX_BATCH))' in _round,
      "收词数量取 _tx_batch_max（设置页上限）")
check('_batch = max(1, int(getattr(self, "_tx_batch", 0) or self.TX_BATCH))' not in _round,
      "不再用被缩批压缩后的 _tx_batch 决定收词数量")
check("_tx_pick_batch(_occs, _batch)" in _round, "收词仍走 _tx_pick_batch(occs, n)")
# 分块那一侧仍应使用 _tx_batch（两者解耦：收多少 vs 一次请求多大）
_chunks = _grab_method("_tx_llm_chunks")
check('_size = min(max(1, int(getattr(self, "_tx_batch", 0) or self.TX_BATCH)), max(1, len(_pending)))'
      in _chunks, "单次请求分块仍按 _tx_batch（收词量 ≠ 分块大小）")

# ─────────────────────────────────────────────
print("\n[T2] GH#3-5：每个 Job 开始复位批大小（行为级，跑真实 _tx_job_reset_stats）")
# ─────────────────────────────────────────────
_ns = {"logger": types.SimpleNamespace(debug=lambda *a, **k: None,
                                       info=lambda *a, **k: None,
                                       warning=lambda *a, **k: None,
                                       error=lambda *a, **k: None)}
exec(compile(_grab_method("_tx_job_reset_stats"), "<t2>", "exec"), _ns)


class _J:
    TX_BATCH = 30
    _tx_batch = 1          # 上一个任务塌陷后残留
    _tx_batch_max = 30
    _tx_batch_safe = 1
    _tx_job_reset_stats = _ns["_tx_job_reset_stats"]


_j = _J()
_j._tx_job_reset_stats()
check(_j._tx_batch == 30, f"Job 开始 → _tx_batch 复位为配置上限（实际 {_j._tx_batch}）")
check(_j._tx_batch_safe == 30, f"Job 开始 → 会话安全上限一并复位（实际 {_j._tx_batch_safe}）")

_j2 = _J()
_j2._tx_batch_max = 12      # 用户把设置改成 12 → 新任务按 12 开始
_j2._tx_job_reset_stats()
check(_j2._tx_batch == 12, "复位跟随用户设置的当前值（不是写死 30）")

# ─────────────────────────────────────────────
print("\n[T3] GH#3-6：折半记「本会话安全上限」，放大不越过（不再来回抖动）")
# ─────────────────────────────────────────────
check("self._tx_batch_safe = max(" in _chunks, "上下文超长折半后记录本会话安全上限")
check('min(_cap, int(getattr(self, "_tx_batch_safe", 0) or _cap))' in _chunks,
      "放大分支的 cap 取「设置上限 ∩ 本会话安全上限」")
check("_tx_batch_safe: int = 30" in _SRC, "类属性 _tx_batch_safe 有默认值")
check("self._tx_batch_safe = self._tx_batch_max" in _SRC,
      "加载配置 / 新 Job 时安全上限复位到配置上限")

# ─────────────────────────────────────────────
print("\n[T4] 已修项不回退（GH#3-2/3/4，v4.6.102）")
# ─────────────────────────────────────────────
check("out_noop[_id] = _v" in _chunks and "_got.add(_id)" in _chunks,
      "GH#3-2：模型如实返回原文 → 计入「已返回」并归 noop 桶（不触发缩批）")
check("if _v != _txt.get(_id):" not in _chunks.split("out_noop")[0].split("if _id in _txt and _v:")[-1],
      "GH#3-2：不再用「译文 != 原文」当作「未返回」的判据")
check("_pending = _rest + _miss_occs" in _chunks,
      "GH#3-3：部分返回只重试缺失项并把它们排到队尾（不改批大小）")
_chunks_code = _code(_chunks)
check("min(_size, len(_missing))" not in _chunks_code,
      "GH#3-3：旧的「一缺就压成 len(_missing)」公式已删除（仅注释里留说明）")
check("_size = min(_cap, max(_size + 1, _size * 2))" in _chunks, "GH#3-4：成功后批大小向上爬升")
check("len(_pending) >= _size" not in _code(_SRC),
      "GH#3-4：放大不再被 len(_pending) >= _size 门控（单向棘轮已解除）")

# ─────────────────────────────────────────────
print("\n[T5] 回归：部分返回时批大小保持不动")
# ─────────────────────────────────────────────
_part = _code(_chunks.split("if _missing and _partial_round < 1:")[1].split("continue")[0])
check("self._tx_batch" not in _part, "部分返回分支里不出现 self._tx_batch（批大小不被压低）")
check("批大小保持" in _part, "日志明确说明「批大小保持不变」")

# ─────────────────────────────────────────────
print("\n[T6] GH#3-7：每轮不再重跑全表 SQL（候选队列 + 游标）")
# ─────────────────────────────────────────────
_qns = {"logger": types.SimpleNamespace(debug=lambda *a, **k: None,
                                        info=lambda *a, **k: None,
                                        warning=lambda *a, **k: None,
                                        error=lambda *a, **k: None),
        "time": __import__("time")}
exec(compile(_grab_method("_tx_occ_queue"), "<t6>", "exec"), _qns)


class _Q:
    TX_OCC_CACHE_TTL = 30.0
    _tx_occ_cache = None
    _tx_job_id = "J1"
    _tx_occ_queue = _qns["_tx_occ_queue"]

    def __init__(self):
        self.calls = 0

    def _tx_occurrences(self, pid):
        self.calls += 1
        return [{"occ_id": f"{pid}-{i}", "text": f"t{i}"} for i in range(5)]


_q = _Q()
_a1 = _q._tx_occ_queue("P")
check(_q.calls == 1 and len(_a1["occs"]) == 5, "首次访问 → 跑一次全表并缓存")
check(_a1.get("i") == 0, "游标从 0 开始")
_a1["i"] = 3                        # 模拟本轮已消费到第 3 条
_a2 = _q._tx_occ_queue("P")
check(_q.calls == 1, "TTL 内再次访问 → **不重跑 SQL**（原先每轮都重跑）")
check(_a2 is _a1 and _a2["i"] == 3, "同一份缓存、游标保留（轮次接着往后走）")
_q._tx_occ_queue("P", force=True)
check(_q.calls == 2, "游标走完 → force 重建一次（拿新入库 / 失败待重试）")
_q._tx_occ_cache["ts"] = 0.0        # 模拟 TTL 过期
_q._tx_occ_queue("P")
check(_q.calls == 3, "TTL(30s) 过期 → 刷新一次")
_q._tx_job_id = "J2"                # 新任务
_q._tx_occ_queue("P")
check(_q.calls == 4, "换 Job → 缓存失效重取（新任务不沿用上轮游标）")
_q._tx_occ_queue("OTHER")
check(_q.calls == 5, "换 pid → 缓存失效")

_round2 = _code(_round)
check("for _o in self._tx_occurrences(pid):" not in _round2,
      "收词不再「每轮直接遍历 _tx_occurrences(全部待翻)」")
check("if _take_person or _take_role:" in _round,
      "来源不含库内（如人名池批量翻译）时整段跳过库内遍历")
check("while _i < len(_lst) and len(_occs) < _batch:" in _round,
      "沿游标过滤到「取够本轮条数」即停（O(本轮条数) 而非 O(全部待翻)）")
check('_q["i"] = _i' in _round, "游标写回缓存（下轮从这里继续）")
check("self._tx_occ_queue(pid, force=True)" in _round,
      "队列走完 → 强制重建一次再判定「真的没有」")
check("self._tx_occ_queue(pid).get(\"occs\")" in _SRC,
      "Job 启动登记词条复用同一份队列（省掉一次全表聚合）")

# ─────────────────────────────────────────────
print("\n[T7] 两排体检：第二排「NFO 未提供角色名」区分「可补 / 补不了」")
# ─────────────────────────────────────────────
# 用户看到的原提示是「N 个角色 NFO 未提供角色名，无法翻译」—— 其实其中一部分
# 只要开着「TMDB 角色回填」就能补（该演员在 NFO 里带 <tmdbid>）。现在按有无 tmdbid 拆两支。
_hns = {"logger": types.SimpleNamespace(debug=lambda *a, **k: None,
                                        info=lambda *a, **k: None,
                                        warning=lambda *a, **k: None,
                                        error=lambda *a, **k: None)}
# _mark_health 是嵌套闭包（缩进 12），按「起始行 → 紧随其后的 for fp in tier1」精确截取
_i7 = _SRC.index("            def _mark_health(_doc, _ns, _rs):")
_j7 = _SRC.index("\n            for fp in tier1:", _i7)
_mh_src = "\n".join(_ln[12:] if _ln.startswith("            ") else _ln
                    for _ln in _SRC[_i7:_j7].splitlines())
exec(compile(_mh_src, "<t7>", "exec"), _hns)
_mark = _hns["_mark_health"]


class _El:
    def __init__(self, **kw):
        self._m = kw

    def find(self, tag):
        _v = self._m.get(tag)
        return None if _v is None else types.SimpleNamespace(text=_v)


class _Doc:
    def __init__(self, actors):
        self.root = types.SimpleNamespace(
            findall=lambda t: (actors if t == "actor" else []))


_hc = {"row1": set(), "row2_ok": set(), "row2_miss": set(),
       "row2_norole": set(), "row2_norole_ok": set()}
_hns["_hc"] = _hc
_mark(_Doc([
    _El(name="A", role="", tmdbid="101"),          # 无名角色 + 有 tmdbid → 可补
    _El(name="B", role=""),                        # 无名角色 + 无 tmdbid → 补不了
    _El(name="C", role="偵探", tmdbid="103"),       # 非英文角色名 + 有 tmdbid → 可补
    _El(name="D", role="偵探"),                     # 非英文角色名 + 无 tmdbid → 补不了
    _El(name="E", role="Detective", tmdbid="105"),  # 已是英文 → 忽略
]), [("Tom Hanks", "Actor"), ("梁朝伟", "Actor")], [("Detective", "Actor")])

check(_hc["row2_norole_ok"] == {"A"}, f"未提供角色名 + 有 tmdbid → 记入「可补」（实际 {_hc['row2_norole_ok']}）")
check(_hc["row2_norole"] == {"B"}, f"未提供角色名 + 无 tmdbid → 记入「补不了」（实际 {_hc['row2_norole']}）")
check(_hc["row2_ok"] == {("C", "偵探")}, "非英文角色名 + 有 tmdbid → 记入「可补」")
check(_hc["row2_miss"] == {("D", "偵探")}, "非英文角色名 + 无 tmdbid → 记入「补不了」")
check(_hc["row1"] == {"Tom Hanks"}, f"第一排缺中文名只记非中文（实际 {_hc['row1']}）")

check("row2_norole_ok" in _SRC, "体检统计新增 row2_norole_ok 分支")
check("（可补 {_r2_norole_ok} / 无 tmdbid 补不了 {_r2_norole}；" in _SRC,
      "提示拆成「可补 N / 无 tmdbid 补不了 M」")
check("TMDB 角色回填{'已开' if _fill_on else '已关'}" in _SRC, "提示带上回填开关状态")
check("个角色 NFO 未提供角色名，无法翻译" not in _SRC,
      "不再笼统写「无法翻译」（可补的那部分不再被误判为没救）")

print("\n" + "=" * 72)
print(f"结果：PASS {_N[0] - _N[1]} / {_N[0]}，FAIL {_N[1]}")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
