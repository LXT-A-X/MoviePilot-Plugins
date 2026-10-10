# -*- coding: utf-8 -*-
"""v4.6.82 回归测试：库页左栏一律用图标（不再逐行加载海报）。

运行：python tests/test_v482_list_icon_only.py

背景：v4.6.81 曾把左栏海报改用 emby_item_id 拼 Emby 图 URL；用户反馈——
    列表一行一张海报 = 无限滚动 / 翻页时对服务器发起大量图片请求（「一拉就疯狂请求」）。
本版据此改为：左栏**一律显示图标**，后端**不再为列表条目生成 poster_url**。
    右侧详情海报仍走 GET /poster（单张、按需），不受影响。
v4.6.83 追加：左栏图标**按类型区分** —— 电影 `mdi-movie-outline` / 剧集 `mdi-television-classic`。

覆盖：
  T1 _annotate_db_items（真实方法体）：不再产出 poster_url
  T2 源码级：列表补字段里不再出现 poster_url / Images/Primary
  T3 源码级：_group_person_rows 已回退 emby_item_id
  T4 真 SQLite：library_items 分组结果不含 emby_item_id
  T5 前端：左栏 prepend 无 <v-img>，用 itemIcon() 取图标
  T6 前端：右侧详情海报（/poster）保留
  T7 前端行为级（Node）：itemIcon 按类型返回 电影 / 剧集 图标
"""
import sys
import re
import types
import textwrap
import subprocess
import tempfile
import importlib.util
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl82_"))
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
_DB = (PLUGIN_DIR / "db.py").read_text(encoding="utf-8")
_VUE = (PLUGIN_DIR / "src/views/LibraryView.vue").read_text(encoding="utf-8")


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

_spec = importlib.util.spec_from_file_location("epl_db82", PLUGIN_DIR / "db.py")
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


def _grab_vue(decl):
    mm = re.search(rf"^(?:async\s+)?function\s+{re.escape(decl)}\s*\(", _VUE, re.M)
    assert mm, f"未找到 {decl}"
    lines = _VUE[mm.start():].splitlines()
    out, depth = [], 0
    for ln in lines:
        out.append(ln)
        depth += ln.count("{") - ln.count("}")
        if depth == 0:
            break
    return "\n".join(out)


def _row(**kw):
    base = {"plugin_id": "", "server_id": "", "item_id": "", "item_type": "Movie",
            "title": "", "series_name": "", "season_num": None, "episode_num": None,
            "library_name": "", "person_index": 0, "person_type": "Actor",
            "name_before": "N", "name_after": "", "role_before": "", "role_after": "",
            "translated_at": "", "nfo_path": "", "deleted_at": "", "emby_item_id": ""}
    base.update(kw)
    return base


print("=" * 72)
print("v4.6.82 回归测试（库页左栏一律用图标，不再逐行加载海报）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] _annotate_db_items（真实方法体）：不再产出 poster_url")
# ─────────────────────────────────────────────
_ns = {}
exec(_grab_method(_SRC, "_annotate_db_items"), _ns)
_annotate = _ns["_annotate_db_items"]


class _FakeDb:
    def episode_counts(self, **kw): return {}
    def expired_item_ids(self, **kw): return []
    def purge_expired(self, **kw): return 0


class _FakeSelf:
    _enabled = False
    _nfo_dead_grace_hours = 24
    def _all_nfo_roots(self): return []
    def _library_name_for_path(self, p): return "电影"
    def _push_log(self, *a, **k): pass


_its = [
    {"item_id": "296101", "server_id": "S1", "emby_item_id": "31715", "item_type": "Series",
     "nfo_dir": "X:/lib/Grow Up Show", "title": "Grow Up Show", "poster_url": "STALE"},
    {"item_id": "4242", "server_id": "S1", "emby_item_id": "88888", "item_type": "Movie",
     "nfo_dir": "X:/lib/Some Movie", "title": "Some Movie"},
]
_out = _annotate(_FakeSelf(), _FakeDb(), [dict(x) for x in _its], "nfo")
check(len(_out) == 2, f"条目正常返回，实际 {len(_out)}")
check(all(not it.get("poster_url") for it in _out),
      "列表条目不再带 poster_url（即使传入旧值也被清掉/不生成）")
check(not any("Images/Primary" in str(it.get("poster_url") or "") for it in _out),
      "列表条目不含 Images/Primary 图片 URL")

# ─────────────────────────────────────────────
print("\n[T2] 源码级：列表补字段里不再出现 poster_url / Images/Primary")
# ─────────────────────────────────────────────
_seg = _grab_method(_SRC, "_annotate_db_items")
check('it["poster_url"]' not in _seg, "`_annotate_db_items` 中已无 poster_url 赋值")
check("Images/Primary" not in _seg, "`_annotate_db_items` 中已无 Emby 图片 URL 拼接")
check("_proxy_poster" not in _seg, "`_annotate_db_items` 不再签名图片代理 URL")
check('it.pop("poster_url", None)' in _seg, "对列表条目做防御性 `pop(\"poster_url\")`（绝不外泄海报）")
check("v4.6.82" in _seg, "留有 v4.6.82 变更说明（便于日后追溯）")

# ─────────────────────────────────────────────
print("\n[T3] 源码级：_group_person_rows 已回退 emby_item_id")
# ─────────────────────────────────────────────
_gseg = _grab_method(_DB, "_group_person_rows")
check("emby_item_id" not in _gseg, "`_group_person_rows` 不再带出 emby_item_id（海报已不用）")

# ─────────────────────────────────────────────
print("\n[T4] 真 SQLite：library_items 分组结果不含 emby_item_id")
# ─────────────────────────────────────────────
dbm.PeopleDb.ensure_table()
PID = "EPL82"
_rows = [
    {"item_id": "296101", "item_type": "Series", "title": "Grow Up Show",
     "nfo_path": "X:/lib/Grow Up Show/tvshow.nfo", "emby_item_id": "31715", "translated_at": "2026-01-01"},
    {"item_id": "296101", "item_type": "Episode", "title": "Grow Up Show", "season_num": 1, "episode_num": 1,
     "nfo_path": "X:/lib/Grow Up Show/Season 1/S01E01.nfo", "emby_item_id": "55501", "translated_at": "2026-01-02"},
]
for _r in _rows:
    dbm._x("INSERT INTO person (plugin_id, server_id, item_id, item_type, title, season_num, episode_num, "
           "nfo_path, library_name, emby_item_id, person_index, translated_at, person_type, name_before) "
           "VALUES (?,?,?,?,?,?,?,?,'',?,?,?,'Actor','N')",
           (PID, "S1", _r["item_id"], _r["item_type"], _r["title"],
            _r.get("season_num"), _r.get("episode_num"), _r["nfo_path"],
            _r["emby_item_id"], 0, _r["translated_at"]))
_items = dbm.PeopleDb().library_items(plugin_id=PID, scan_mode=None)
check(len(_items) == 1, f"聚为 1 个条目，实际 {len(_items)}")
check(_items and "emby_item_id" not in _items[0],
      "分组条目不含 emby_item_id 字段（已回退，避免无用的载荷字段）")
check(_items and str(_items[0].get("item_id")) == "296101", "基本字段（item_id）仍正常")

# ─────────────────────────────────────────────
print("\n[T5] 前端：左栏 prepend 无 <v-img>，固定灰色图标")
# ─────────────────────────────────────────────
_m = re.search(r"<v-list-item v-else[^>]*>(.*?)</v-list-item>", _VUE, re.S)
_block = _m.group(1) if _m else ""
_pre = re.search(r"<template #prepend>(.*?)</template>", _block, re.S)
_pretxt = _pre.group(1) if _pre else ""
check(bool(_m), "找到左栏「条目行」节点（v-list-item v-else）")
check(bool(_pre), "找到条目行的 prepend 插槽")
check("<v-img" not in _pretxt, "左栏 prepend 不再包含 <v-img>（不加载任何图片）")
check("{{ itemIcon(node.item) }}" in _pretxt, "左栏 prepend 用 itemIcon(node.item) 按类型取图标")
check("poster_url" not in _pretxt, "左栏 prepend 不再引用 poster_url")
check("failedPosters" not in _VUE and "thumbOk" not in _VUE and "onThumbError" not in _VUE,
      "v4.6.81 的海报失败回退逻辑已移除（列表已无图片）")
check("node.item.poster_url" not in _VUE, "列表相关代码不再消费 node.item.poster_url")

# ─────────────────────────────────────────────
print("\n[T6] 前端：右侧详情海报（/poster，单张按需）保留")
# ─────────────────────────────────────────────
check("'/poster'" in _VUE or '"/poster"' in _VUE, "详情仍调用 GET /poster（按需单张）")
check("posterData" in _VUE, "详情海报状态 posterData 保留")
_dm = re.search(r'<v-img v-if="posterData.*?</v-img>', _VUE, re.S)
check(bool(_dm), "详情头部海报 <v-img> 仍保留")

# ─────────────────────────────────────────────
print("\n[T7] 前端行为级：itemIcon 按类型区分（Node 跑真实提取函数）")
# ─────────────────────────────────────────────
_js = _grab_vue("itemIcon") + """
let n=0,f=0; function chk(c,m){n++; if(c) console.log('PASS '+m); else {f++; console.log('FAIL '+m);}}
chk(itemIcon({item_type:'Movie'})==='mdi-movie-outline','Movie → 电影图标');
chk(itemIcon({item_type:'Series'})==='mdi-television-classic','Series → 剧集图标');
chk(itemIcon({item_type:'series'})==='mdi-television-classic','小写 series → 剧集图标');
chk(itemIcon({item_type:'电视剧'})==='mdi-television-classic','中文「电视剧」→ 剧集图标');
chk(itemIcon({item_type:'Movie'})!==itemIcon({item_type:'Series'}),'电影与剧集图标不同');
chk(itemIcon({})==='mdi-movie-outline','无类型 → 默认电影图标');
chk(itemIcon(null)==='mdi-movie-outline','null 安全 → 默认电影图标');
console.log('JS_TOTAL='+n); console.log('JS_FAIL='+f);
"""
node = None
for _cand in (r"C:\node-v22.14.0-win-x64\node.exe", "node"):
    try:
        subprocess.run([_cand, "-v"], capture_output=True, timeout=15)
        node = _cand
        break
    except Exception:
        continue
if node:
    _t = Path(tempfile.mkdtemp(prefix="epl82n_")) / "t.mjs"
    _t.write_text(_js, encoding="utf-8")
    r = subprocess.run([node, str(_t)], capture_output=True, timeout=60)
    out = (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")
    for _ln in out.splitlines():
        if _ln.startswith("PASS "):
            check(True, _ln[5:])
        elif _ln.startswith("FAIL "):
            check(False, _ln[5:])
    _jf = re.search(r"JS_FAIL=(\d+)", out)
    check(bool(_jf) and int(_jf.group(1)) == 0, "itemIcon 行为级全部通过")
else:
    print("  [SKIP] 未找到 node")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
