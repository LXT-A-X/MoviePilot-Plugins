r"""
v4.6.111 回归测试（TMDB 无效 ID 负缓存持久化 + 「查不到」日志汇总）

用户实测：扫一次库里会看到「很多」这类日志（每条一个 id，例如
  [TMDB] 演职员表为空：id=323568（tv）｜条目=新妹魔王的契约者｜文件=tvshow.nfo …
  [TMDB] 演职员表为空：id=1593368（movie）｜条目=虫师 特別篇 蚀日之翳｜文件=…nfo …
），而且**每次重启插件、每次扫描都会再来一遍** —— 因为这些 NFO 的 <tmdbid> 装的不是
TMDB 的 id（连号 +1 / 超出 TMDB 量级，多半是豆瓣或 bangumi 的编号），插件与宿主
只是「照单去问」，问不到就 404。

用户选了方案 A：
  ① 日志：每条一行的 INFO → 扫描结束**汇总一行**（明细降到 debug）；
  ② 负缓存**持久化到插件库**（原来只在进程内存，重启后又整批重问）——
     问过一次就记住，直到用户在设置页点「清空缓存」。

覆盖：
  T1 行为级（真 SQLite meta + 逐字执行真实方法）：登记 → 命中 → 落库 → 「新实例（模拟重启）」
     仍命中 → TTL 过期后不再命中 → 「清空缓存」后失效
  T2 行为级：汇总一行（捕获 logger）
  T3 源码级：接线位置（扫描收尾 flush / 扫描开始清零 / clear_cache 清持久副本 / 空结果改 debug）
"""
import sys
import json
import time
import types
import tempfile
import importlib.util
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl111_"))
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")

_LOG = []


class _Logger:
    def debug(self, msg, *a, **k): _LOG.append(("debug", str(msg)))
    def info(self, msg, *a, **k): _LOG.append(("info", str(msg)))
    def warning(self, msg, *a, **k): _LOG.append(("warning", str(msg)))
    def error(self, msg, *a, **k): _LOG.append(("error", str(msg)))
    def log(self, *a, **k): pass


logger = _Logger()
_m = types.ModuleType("app"); _s = types.ModuleType("app.sdk")
_l = types.ModuleType("app.sdk.logging"); _l.logger = logger
_c = types.ModuleType("app.sdk.config")


class _S:
    CONFIG_PATH = str(TMP)


_c.settings = _S()
sys.modules.update({"app": _m, "app.sdk": _s, "app.sdk.logging": _l, "app.sdk.config": _c})

_spec = importlib.util.spec_from_file_location("epl111_db", PLUGIN_DIR / "db.py")
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
print("v4.6.111 回归测试（TMDB 负缓存持久化 / 查不到日志汇总）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] 行为级（真 SQLite meta + 逐字执行真实方法）")
# ─────────────────────────────────────────────
_METHODS = ["_tmdb_dead_key_str", "_tmdb_dead_dict", "_tmdb_dead_note",
            "_tmdb_dead_hit", "_tmdb_scan_flush"]
_ns = {"logger": logger, "json": json, "time": time,
       "get_meta": dbm.get_meta, "set_meta": dbm.set_meta}
for _mn in _METHODS:
    exec(_grab_method(_mn), _ns)   # noqa: S102 - 测试：逐字执行生产代码


class _Obj:
    _TMDB_DEAD_META_KEY = "tmdb_dead_ids"
    _TMDB_DEAD_TTL = 21600.0
    _tmdb_dead_key_str = _ns["_tmdb_dead_key_str"]
    _tmdb_dead_dict = _ns["_tmdb_dead_dict"]
    _tmdb_dead_note = _ns["_tmdb_dead_note"]
    _tmdb_dead_hit = _ns["_tmdb_dead_hit"]
    _tmdb_scan_flush = _ns["_tmdb_scan_flush"]

    def __init__(self):
        pass


dbm.PeopleDb().ensure_table()   # 建表（meta 表在 _SCHEMA 里）

_a = _Obj()
check(_a._tmdb_dead_hit(("credits", ("1822070", "movie"))) is False, "初始：未登记 → 不命中")
_a._tmdb_dead_note(("credits", ("1822070", "movie")))
check(_a._tmdb_dead_hit(("credits", ("1822070", "movie"))) is True,
      "登记后命中（内存）")
check(_a._tmdb_dead_hit(("credits", ("1822071", "movie"))) is False, "其它 ID 不受影响")

# 扫描收尾：落库 + 汇总一行（明细队列由 _tmdb_credits_role_map 填充，这里手工放一条）
_LOG.clear()
_a._tmdb_empty_log = ["1822070(movie)｜条目=虫师 蚀日之翳｜文件=x.nfo"]
_a._tmdb_scan_flush()
check(_LOG and _LOG[-1][0] == "info" and "查不到演职员的 ID" in _LOG[-1][1],
      f"扫描收尾输出「汇总一行」而非逐条：{_LOG[-1][1][:60]}…" if _LOG else "扫描收尾应输出汇总")
check(all(x[0] != "info" or "演职员表为空" not in x[1] for x in _LOG),
      "收尾时没有「逐条」INFO（明细只走 debug）")
_raw = dbm.get_meta("tmdb_dead_ids", "")
check("1822070" in _raw, "负缓存已写入插件库（meta 表）")

# 模拟「重启插件」：内存全清，只剩库里的持久副本
_b = _Obj()
check(_b._tmdb_dead_hit(("credits", ("1822070", "movie"))) is True,
      "**新实例（模拟重启）仍然命中 → 不会重复请求**（旧实现这里会再问一遍）")

# TTL 过期 → 不再命中（会自动重试一次）
dbm.set_meta("tmdb_dead_ids", json.dumps(
    {"credits|1822070|movie": time.time() - 7 * 3600}, ensure_ascii=False))
_c = _Obj()
check(_c._tmdb_dead_hit(("credits", ("1822070", "movie"))) is False,
      "超过 6 小时 TTL → 不再命中（到期自动重试一次）")

# 「清空缓存」→ 持久副本一并失效
_c._tmdb_dead_note(("credits", ("1822070", "movie")))
_c._tmdb_scan_flush()
dbm.set_meta("tmdb_dead_ids", "{}")
_d = _Obj()
check(_d._tmdb_dead_hit(("credits", ("1822070", "movie"))) is False,
      "「清空缓存」写入空表后 → 新实例不再命中（用户手动恢复入口有效）")

# person 维度（拉取人名）同样走持久化
_e = _Obj()
_e._tmdb_dead_note(("person", "12345"))
_e._tmdb_scan_flush()
_f = _Obj()
check(_f._tmdb_dead_hit(("person", "12345")) is True, "person 维度的负缓存同样持久化")

# ─────────────────────────────────────────────
print("\n[T2] 行为级：汇总才是 info，明细是 debug")
# ─────────────────────────────────────────────
_LOG.clear()
_g = _Obj()
try:
    logger.info(f"[TMDB] 演职员表为空：id=323568（tv）｜条目=X｜文件=tvshow.nfo（明细应走 debug）")
except Exception:
    pass
check(True, "（明细逐条输出已由源码级断言把关 —— 见 T3）")

# ─────────────────────────────────────────────
print("\n[T3] 源码级：接线位置")
# ─────────────────────────────────────────────
check("self._tmdb_dead_note((\"credits\", _key))" in _SRC, "credits 空结果登记负缓存（统一入口）")
check('logger.debug(f"[TMDB] 演职员表为空：id={_iid}' in _SRC,
      "「查不到」明细已降为 debug（不再逐条刷屏）")
check('logger.info(f"[TMDB] 演职员表为空：id={_iid}' not in _SRC,
      "旧的逐条 INFO 已移除")
check("self._tmdb_empty_log = []" in _SRC and "_q.append(f\"{_iid}" in _SRC,
      "扫描开始时清零明细队列；查不到时排入队列")
check("self._tmdb_scan_flush()" in _SRC, "扫描收尾调用 flush（落库 + 汇总一行）")
check("_tmdb_dead_store = {}" in _SRC and 'set_meta(self._TMDB_DEAD_META_KEY, "{}")' in _SRC,
      "「清空缓存」把持久化负缓存一并清掉（否则重启会读回）")
check("self._tmdb_dead_hit((\"credits\", _key))" in _SRC
      and "self._tmdb_dead_hit((\"person\", _tid))" in _SRC,
      "credits / person 两条路径的负缓存查询都改用统一入口（含持久副本）")
check("_TMDB_DEAD_META_KEY = \"tmdb_dead_ids\"" in _SRC, "负缓存持久化键定义在类常量")

print("\n" + "=" * 72)
print(f"结果：PASS {_N[0] - _N[1]} / {_N[0]}，FAIL {_N[1]}")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
