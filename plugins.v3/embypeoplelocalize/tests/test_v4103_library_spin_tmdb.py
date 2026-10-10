# -*- coding: utf-8 -*-
"""v4.6.103 回归测试：库页左栏转圈不停 / 「任务统计」迟迟不出来 + TMDB 404 刷屏。

运行：python tests/test_v4103_library_spin_tmdb.py

背景（用户实测，库内 360 条目）：
  1) 「左侧都会转半天」——条目早已渲染出来，进度条却一直转、停不下来：
     loadItems 有「请求代次」但没有单飞守卫，轮询每 8s 一次；/db/items 慢于 8s 时
     老请求被新请求顶掉（seq 不匹配 → early return，finally 不清 loadingList），
     新请求又被下一轮顶掉 —— 永远没有「最新一代」请求，loadingList 永远 true。
  2) 「任务统计加载完又不见，又加载」——/db/translate_preview 每轮把同一份重快照
     （pending_terms_full × 4 + count_pool_status）算两遍；且 /db/items 每次轮询都跑
     全表 CAST 扫描的 expired_item_ids + purge_expired。
  3) TMDB 日志 1 秒 1 条 "The resource you requested could not be found." ——
     单集记录没有剧级 id 时，退回用「单集 tmdbid」当剧 id 请求 /tv/{id}/credits 必然 404；
     且宿主 TmdbApi 对 404/异常一律吞掉返回空，插件无负缓存 → 每轮重打同一个坏 ID。

覆盖：
  T1 前端行为级（Node）：loadItems 单飞 —— 叠加调用只发 1 个请求，且 loadingList 必被清掉
  T2 前端源码级：单飞守卫 + 计时器轮询仍只调 loadItems
  T3 源码级 + 行为级：translate_preview 只算一次快照，_pending_stats(复用)
  T4 行为级：_annotate_db_items 洗版清理限频 120s
  T5 源码级：单集无剧级 id 时不再发 get_tv_credits（TMDB-4）
  T6 行为级：_tmdb_credits_role_map 负缓存（TMDB-1）
  T7 行为级：_pool_tmdb_fill_one 负缓存（TMDB-2）
  T8 源码级：_tmdb_poster_url 空结果也落缓存（TMDB-3）
"""
import re
import sys
import time
import types
import textwrap
import tempfile
import subprocess
import importlib.util
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl103_"))
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
_VUE = (PLUGIN_DIR / "src/views/LibraryView.vue").read_text(encoding="utf-8")

_N = [0, 0]


def check(cond, msg):
    _N[0] += 1
    if cond:
        print(f"  [PASS] {msg}")
    else:
        _N[1] += 1
        print(f"  [FAIL] {msg}")


class _Logger:
    def debug(self, *a, **k): pass
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass
    def log(self, *a, **k): pass


logger = _Logger()

# ── 桩：宿主 app.* 模块 ──
_m = types.ModuleType("app")
_sdk = types.ModuleType("app.sdk")
_lg = types.ModuleType("app.sdk.logging"); _lg.logger = logger
_cfg = types.ModuleType("app.sdk.config")
class _Settings:
    CONFIG_PATH = str(TMP)
    TMDB_LOCALE = "zh-CN"
    TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w500"
_cfg.settings = _Settings()
_chain = types.ModuleType("app.chain")
_tmdbmod = types.ModuleType("app.chain.tmdb")
_TMDB_CALLS = [0]
_tmdb_holder = {"person_detail": None}
class _FakeChain:
    def person_detail(self, pid):
        _TMDB_CALLS[0] += 1
        return _tmdb_holder["person_detail"]
    def recognize_media(self, **kw):
        return None
_tmdbmod.TmdbChain = _FakeChain
_tmw = types.ModuleType("app.modules")
_tmwdb = types.ModuleType("app.modules.themoviedb")
_tmwapi = types.ModuleType("app.modules.themoviedb.tmdbapi")
_CREDITS_CALLS = [0]
_credits_holder = {"cast": [], "raise": False}
class _FakeTmdbApi:
    def __init__(self, language=None):
        pass
    def _fetch(self, *a, **k):
        _CREDITS_CALLS[0] += 1
        if _credits_holder["raise"]:
            raise RuntimeError("boom")
        return list(_credits_holder["cast"])
    def get_tv_credits(self, *a, **k):
        return self._fetch()
    def get_movie_credits(self, *a, **k):
        return self._fetch()
_tmwapi.TmdbApi = _FakeTmdbApi
sys.modules.update({
    "app": _m, "app.sdk": _sdk, "app.sdk.logging": _lg, "app.sdk.config": _cfg,
    "app.chain": _chain, "app.chain.tmdb": _tmdbmod,
    "app.modules": _tmw, "app.modules.themoviedb": _tmwdb,
    "app.modules.themoviedb.tmdbapi": _tmwapi,
})


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


def _ns_for(*names):
    return {"logger": logger, "time": time, "settings": _cfg.settings, "re": re,
            "Any": Any, "Dict": Dict, "List": List, "Optional": Optional,
            "getattr": getattr, "str": str, "int": int, "bool": bool, "float": float,
            "list": list, "dict": dict, "set": set, "len": len, "sum": sum,
            "min": min, "max": max, "sorted": sorted, "Exception": Exception,
            "hashlib": __import__("hashlib")}


print("=" * 72)
print("v4.6.103 回归测试（库页转圈 / 任务统计 / TMDB 404）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] 前端行为级（Node）：loadItems 单飞 —— 叠加只发 1 个请求且 loadingList 必被清")
# ─────────────────────────────────────────────
_i = _VUE.index("function _normItems(resp)")
_j = _VUE.index("\n// 滚动到底部自动追加下一页", _i)   # v4.6.104：helpers 已插入 loadItems 之前，改按后续锚点截取
_js_block = _VUE[_i:_j]
_js = _js_block + """
const loadingList = { value: true }
const items = { value: [] }
const itemHasMore = { value: false }
const props = { api: {} }
const ITEM_PAGE_SIZE = 100
const itemKey = (it) => (it ? `${it.server_id || ''}:${it.item_id || ''}` : '')
let itemsSeq = 0
let calls = 0
const api = { get: async () => { calls++; await new Promise((r) => setTimeout(r, 60)); return { items: [{ item_id: 'a' }], total: 1, has_more: false } } }
function notify() {}
let n = 0, f = 0
function chk (c, m) { n++; if (c) console.log('PASS ' + m); else { f++; console.log('FAIL ' + m) } }
const p1 = loadItems(true)
const p2 = loadItems(false)
const p3 = loadItems(true)
chk(loadingList.value === true, '在飞期间手动刷新立即给出 loading 反馈')
await Promise.all([p1, p2, p3])
chk(calls === 1, '三轮叠加只发 1 个请求（单飞守卫生效），实际 ' + calls)
chk(loadingList.value === false, '响应到达后 loadingList 被清掉（不再永久转圈）')
await loadItems(true)
chk(calls === 2, '收尾后可正常发起下一轮，实际 ' + calls)
chk(loadingList.value === false, '下一轮结束同样收尾干净')
console.log('JS_TOTAL=' + n)
console.log('JS_FAIL=' + f)
"""
_node = None
for _cand in (r"C:\node-v22.14.0-win-x64\node.exe", "node"):
    try:
        subprocess.run([_cand, "-v"], capture_output=True, timeout=15)
        _node = _cand
        break
    except Exception:
        continue
if _node:
    _tf = Path(tempfile.mkdtemp(prefix="epl103n_")) / "t.mjs"
    _tf.write_text(_js, encoding="utf-8")
    _r = subprocess.run([_node, str(_tf)], capture_output=True, timeout=60)
    _out = (_r.stdout or b"").decode("utf-8", "replace") + (_r.stderr or b"").decode("utf-8", "replace")
    for _ln in _out.splitlines():
        if _ln.startswith("PASS "):
            check(True, _ln[5:])
        elif _ln.startswith("FAIL "):
            check(False, _ln[5:])
    _jf = re.search(r"JS_FAIL=(\d+)", _out)
    check(bool(_jf) and int(_jf.group(1)) == 0,
          "loadItems 行为级全部通过" + ("" if (_jf and int(_jf.group(1)) == 0) else "\n" + _out))
else:
    print("  [SKIP] 未找到 node")

# ─────────────────────────────────────────────
print("\n[T2] 前端源码级：单飞守卫落地，轮询仍只调 loadItems")
# ─────────────────────────────────────────────
check("if (_itemsInflight) {" in _js_block, "loadItems 开头有单飞守卫 `if (_itemsInflight)`")
check("_itemsInflight = true" in _js_block, "发请求前置位 _itemsInflight")
check("_itemsInflight = false" in _js_block, "finally 里复位 _itemsInflight（异常路径也复位）")
check("if (seq === itemsSeq) loadingList.value = false" in _js_block,
      "loadingList 仍由「最新一代」请求收尾")
check("v4.6.103" in _js_block, "留有 v4.6.103 变更说明")
check("loadItems(true); loadStatus(); loadTxPreview(true)" in _VUE, "切回前台仍同时刷新列表/状态/统计")
# v4.6.104：列表已改为事件驱动（items_rev 变更才拉）→ 计时器仍是 2 个（状态轮询 + 详情）
check(_VUE.count("setInterval") == 2, f"仍只有 2 个计时器（状态轮询 + 详情），实际 {_VUE.count('setInterval')}")
check("if (document.hidden) return" in _VUE, "v4.6.104：页面在后台不轮询")

# ─────────────────────────────────────────────
print("\n[T3] 源码级 + 行为级：translate_preview 只算一次快照")
# ─────────────────────────────────────────────
_prev = _grab_method(_SRC, "_api_db_translate_preview")
check(_prev.count("self._tx_pending_snapshot(") == 1,
      f"全库口径只调一次 _tx_pending_snapshot（实际 {_prev.count('self._tx_pending_snapshot(')} 次）")
check("_snap = self._tx_pending_snapshot(with_detail=True)" in _prev, "一次取「带明细」快照")
check("self._pending_stats(_snap)" in _prev, "徽章数复用同一份快照（不再算第二遍）")
check("self._pending_stats()" not in _prev, "旧的「另算一遍 _pending_stats()」调用已删除")
check("_detail = _snap.get(\"items_list\")" in _prev, "悬浮列表也取同一份快照的明细")

_ps = _ns_for()
exec(compile(_grab_method(_SRC, "_pending_stats"), "<t3>", "exec"), _ps)
_pending_stats = _ps["_pending_stats"]


class _PSSelf:
    def _tx_pending_snapshot(self, *a, **k):
        raise AssertionError("传入快照后不得再算一遍快照")


_snap = {"person": 7, "role": 3, "items": 4, "person_scope": 9, "role_scope": 5,
         "items_scope": 6, "person_on": True, "role_on": False, "disabled": ["Director"],
         "pool": 2, "total": 11}
_d = _pending_stats(_PSSelf(), _snap)
check(_d["names"] == 7 and _d["roles"] == 3 and _d["items"] == 4,
      f"复用快照得出徽章数（{_d['names']}/{_d['roles']}/{_d['items']}）")
check(_d["pool"] == 2 and _d["total"] == 11 and _d["role_on"] is False, "池 / 合计 / 开关原样透出")

# ─────────────────────────────────────────────
print("\n[T4] 行为级：_annotate_db_items 洗版清理限频 120s")
# ─────────────────────────────────────────────
_an = _ns_for()
exec(compile(_grab_method(_SRC, "_annotate_db_items"), "<t4>", "exec"), _an)
_annotate = _an["_annotate_db_items"]


class _CountDb:
    def __init__(self):
        self.expired = 0

    def episode_counts(self, **kw):
        return {}

    def expired_item_ids(self, **kw):
        self.expired += 1
        return []

    def purge_expired(self, **kw):
        return 0


class _AnSelf:
    _enabled = True
    _nfo_dead_grace_hours = 24

    def _all_nfo_roots(self):
        return []

    def _library_name_for_path(self, p):
        return "电影"

    def _push_log(self, *a, **k):
        pass


_db = _CountDb()
_self = _AnSelf()
_rows = [{"item_id": "1", "server_id": "S", "item_type": "Movie", "nfo_dir": "X:/m/1", "title": "M1"}]
_annotate(_self, _db, [dict(x) for x in _rows], "nfo")
check(_db.expired == 1, f"首次调用跑一次清理扫描（实际 {_db.expired}）")
for _ in range(5):
    _annotate(_self, _db, [dict(x) for x in _rows], "nfo")
check(_db.expired == 1, f"120s 内的后续调用不再重复扫描（实际 {_db.expired} 次）")
_self._purge_scan_ts = time.time() - 121.0
_annotate(_self, _db, [dict(x) for x in _rows], "nfo")
check(_db.expired == 2, f"超过 120s 后重新扫描一次（实际 {_db.expired} 次）")
check("v4.6.103" in _grab_method(_SRC, "_annotate_db_items"), "留有 v4.6.103 变更说明")

# ─────────────────────────────────────────────
print("\n[T5] 源码级：单集无剧级 id 时不再发 get_tv_credits（TMDB-4）")
# ─────────────────────────────────────────────
_rec = _grab_method(_SRC, "_record_nfo_library")
check('if item_type == "Episode" and not series_id:' in _rec,
      "单集且无 series_id → 直接不补角色（不再拿单集 id 当剧 id）")
check("_cid = series_id if item_type == \"Episode\" else item_id" in _rec,
      "其余情形才构造 _cid（Episode 走 series_id / 其它走 item_id）")
check("_cid = series_id if (item_type == \"Episode\" and series_id) else item_id" not in _rec,
      "旧的「无 series_id 时退回 item_id」已删除")
check('if getattr(self, "_pool_tmdb_credits", False) and bool(_tr.get("role", True)):' in _rec,
      "credits 触发条件仍用 effective role（v4.6.67 语义不回退）")

# ─────────────────────────────────────────────
print("\n[T6] 行为级：_tmdb_credits_role_map 负缓存（TMDB-1）")
# ─────────────────────────────────────────────
_cr = _ns_for()
exec(compile(_grab_method(_SRC, "_tmdb_credits_role_map"), "<t6>", "exec"), _cr)
_credits = _cr["_tmdb_credits_role_map"]


class _CrSelf:
    _TMDB_DEAD_TTL = 21600.0

    # v4.6.111：负缓存的「查询 / 登记」抽成了统一入口（真实现 = __init__._tmdb_dead_hit /
    # _tmdb_dead_note，含持久化；行为覆盖见 test_v4111）。这里按同语义提供最小桩，
    # 让本用例继续聚焦「TTL 内不重打 / 过期重试」这一段行为。
    def _tmdb_dead_hit(self, key):
        _d = getattr(self, "_tmdb_dead", None) or {}
        _ts = _d.get(key)
        return bool(_ts and (time.time() - float(_ts)) < self._TMDB_DEAD_TTL)

    def _tmdb_dead_note(self, key):
        _d = getattr(self, "_tmdb_dead", None)
        if _d is None:
            _d = self._tmdb_dead = {}
        _d[key] = time.time()


_CREDITS_CALLS[0] = 0
_credits_holder["cast"] = []
_s = _CrSelf()
check(_credits(_s, "111", "Series") == {}, "坏 ID（返回空）→ 空表")
check(_CREDITS_CALLS[0] == 1, f"首次真的发了一次请求（实际 {_CREDITS_CALLS[0]}）")
_s._tmdb_credits_cache = {}          # 模拟「下一轮扫描」清空 per-scan 缓存
check(_credits(_s, "111", "Series") == {}, "再次查询仍为空表")
check(_CREDITS_CALLS[0] == 1, f"负缓存命中 → 下一轮扫描不再请求 TMDB（实际 {_CREDITS_CALLS[0]}）")
# 有效 ID（有 cast）不得被负缓存吞掉
_credits_holder["cast"] = [{"id": 900, "character": "Bond"}]
check(_credits(_s, "222", "Series") == {"900": "Bond"}, "有效 ID 正常返回角色映射")
_s._tmdb_credits_cache = {}
_credits(_s, "222", "Series")
check(_CREDITS_CALLS[0] == 3, f"有效 ID 不受负缓存影响，照常请求（实际 {_CREDITS_CALLS[0]}）")
# TTL 过期后可重试
_s._tmdb_dead[("credits", ("111", "tv"))] = time.time() - 21601.0
_credits(_s, "111", "Series")
check(_CREDITS_CALLS[0] == 4, f"TTL 过期后自动重试一次（实际 {_CREDITS_CALLS[0]}）")
check(str(_s._tmdb_dead.get(("credits", ("111", "tv"))) or "") != "",
      "重试后重新登记负结果（时间戳已刷新）")

# ─────────────────────────────────────────────
print("\n[T7] 行为级：_pool_tmdb_fill_one 负缓存（TMDB-2）")
# ─────────────────────────────────────────────
_pf = _ns_for()
exec(compile(_grab_method(_SRC, "_pool_tmdb_fill_one"), "<t7>", "exec"), _pf)
_fill = _pf["_pool_tmdb_fill_one"]


class _FillSelf:
    _TMDB_DEAD_TTL = 21600.0

    # v4.6.111：负缓存查询/登记抽成统一入口（真实现见 __init__ / 覆盖见 test_v4111）—— 同语义最小桩
    def _tmdb_dead_hit(self, key):
        _d = getattr(self, "_tmdb_dead", None) or {}
        _ts = _d.get(key)
        return bool(_ts and (time.time() - float(_ts)) < self._TMDB_DEAD_TTL)

    def _tmdb_dead_note(self, key):
        _d = getattr(self, "_tmdb_dead", None)
        if _d is None:
            _d = self._tmdb_dead = {}
        _d[key] = time.time()

    def _name_is_zh(self, s):
        return any("\u4e00" <= c <= "\u9fff" for c in str(s or ""))

    def _zhconv_convert(self, s):
        return s

    def _tmdb_download_image(self, p):
        return b""


class _Cli:
    def __init__(self, tid):
        self._tid = tid
        self.updated = []

    def get_person_detail(self, pid):
        return {"Id": pid, "ProviderIds": {"Tmdb": self._tid}, "LockedFields": []}

    def update_person_info(self, pid, info):
        self.updated.append(info)
        return True

    def set_person_primary_image(self, pid, img):
        return True


_TMDB_CALLS[0] = 0
_tmdb_holder["person_detail"] = None
_fs = _FillSelf()
_fs._tmdb_person_cache = {}
_o1 = _fill(_fs, _Cli("333"), server_id="S", person_id="p1", name_cur="Nobody")
check(_o1["err"] == "TMDB 无人物详情", f"首次拉不到详情（err={_o1['err']}）")
check(_TMDB_CALLS[0] == 1, f"首次真的请求了一次（实际 {_TMDB_CALLS[0]}）")
_fs._tmdb_person_cache = {}          # 模拟「下一次拉池」清空 per-run 缓存
_o2 = _fill(_fs, _Cli("333"), server_id="S", person_id="p1", name_cur="Nobody")
check(_TMDB_CALLS[0] == 1, f"负缓存命中 → 下次拉池不再请求 TMDB（实际 {_TMDB_CALLS[0]}）")
check("负缓存" in str(_o2["err"] or ""), f"命中时给出明确原因（err={_o2['err']}）")
# 有效人物不受影响
_tmdb_holder["person_detail"] = types.SimpleNamespace(
    name="水桥香织", also_known_as=[], biography="", profile_path="")
_o3 = _fill(_fs, _Cli("444"), server_id="S", person_id="p2", name_cur="Kana")
check(_o3["cn_name"] == "水桥香织", f"有效 TmdbId 正常拿到中文名（{_o3['cn_name']}）")
check(_TMDB_CALLS[0] == 2, f"有效 ID 照常请求（实际 {_TMDB_CALLS[0]}）")

# ─────────────────────────────────────────────
print("\n[T8] 源码级：_tmdb_poster_url 空结果也落缓存（TMDB-3）")
# ─────────────────────────────────────────────
_poster = _grab_method(_SRC, "_tmdb_poster_url")
check('cache[_tid] = poster or ""' in _poster, "无图也写缓存（空串），不再每次都重打 TMDB")
check("_c[_tid2] = \"\"" in _poster, "异常路径同样登记负结果")
check("v4.6.103" in _poster, "留有 v4.6.103 变更说明")

print("\n" + "=" * 72)
print(f"结果：PASS {_N[0] - _N[1]} / {_N[0]}，FAIL {_N[1]}")
print("=" * 72)
sys.exit(1 if _N[1] else 0)