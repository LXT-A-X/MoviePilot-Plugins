# -*- coding: utf-8 -*-
"""v4.7.9 诊断探针（只读，不改生产代码）：复现两个疑点，把结果打印出来。

  A) 人名「无需操作」判定表 —— 哪些名字会被判「无需翻译」（= 永不翻译）
  B) 「📥 采集 N 词条 ｜ ✅ 已有译文 0 条（未重翻）」口径 —— 真 SQLite 复现
     （模拟 Grow Up Show：E01/E02 已翻译 → E02 删除进观察期 → E02 改名重新入库恢复）

运行：python tests/probe_v479_ingest_counts.py
（文件名不是 test_*.py，故意不进回归套件）
"""
import sys
import os
import re
import types
import textwrap
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl479probe_"))
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")


# ─────────────── 宿主桩件（与其它测试同款） ───────────────
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
_req = types.ModuleType("requests")


class _RS:
    def __init__(self): self.headers = {}

    def close(self): pass


_req.Session = _RS
_sch = types.ModuleType("app.schemas"); _sch.ServiceInfo = object
sys.modules.update({"app": _m, "app.sdk": _s, "app.sdk.logging": _l, "app.sdk.config": _c,
                    "requests": _req, "app.schemas": _sch})


def _grab_method(src, name):
    mm = re.search(rf"^([ \t]*)def {re.escape(name)}\(", src, re.M)
    assert mm, f"未找到 {name}"
    indent = len(mm.group(1))
    lines = src[mm.start():].splitlines()
    out = [lines[0]]
    for ln in lines[1:]:
        _st = ln.lstrip()
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent and (_st.startswith("def ") or _st.startswith("@")):
            break
        out.append(ln)
    return textwrap.dedent("\n".join(out))


# ═══════════════ A) 「无需操作」判定表 ═══════════════
print("=" * 78)
print("A) 人名「无需操作」判定表（真函数；命中 = 永不送翻译）")
print("=" * 78)
try:
    import zhconv  # noqa: F401
    _HAS_ZHCONV = True
except Exception:
    _HAS_ZHCONV = False
print(f"zhconv 可用 = {_HAS_ZHCONV}（不可用则「繁简不变」这一层的判定会失真）\n")

_nsA = {"logger": logger, "HAS_ZHCONV": _HAS_ZHCONV, "re": re, "os": os}
for _fn in ("_looks_like_japanese", "_looks_like_chinese", "_name_is_zh",
            "_skip_no_translate", "_tx_untranslatable", "_tx_noop_placeholder",
            "_zhconv_convert"):
    exec(_grab_method(_SRC, _fn), _nsA)


class _T:
    _looks_like_japanese = staticmethod(_nsA["_looks_like_japanese"])
    _looks_like_chinese = staticmethod(_nsA["_looks_like_chinese"])
    _name_is_zh = _nsA["_name_is_zh"]
    _skip_no_translate = _nsA["_skip_no_translate"]
    _tx_untranslatable = staticmethod(_nsA["_tx_untranslatable"])
    _zhconv_convert = _nsA["_zhconv_convert"]
    # 类属性：占位符正则（照抄源码 _NOOP_PLACEHOLDER_RE）
    _NOOP_PLACEHOLDER_RE = re.compile(
        r"^[（(【\[『「]?\s*(?:voice|voices|cv|vo|配音|旁白|待补充|待定|无|n/?a|unknown)\s*[)）】\]』」]?$",
        re.IGNORECASE)


_t = _T()
_ph = _nsA["_tx_noop_placeholder"]

_NAMES = [
    ("纯汉字日文名", "越谷夏海"), ("纯汉字日文名", "宫内莲华"), ("纯汉字日文名", "一条蛍"),
    ("纯汉字日文名", "富士宫木实"), ("纯汉字日文名", "名冢 佳织"),
    ("汉字+假名", "小岩井ことり"), ("汉字+假名", "雛坂ひかる"),
    ("汉字+假名", "紗倉のり子"), ("汉字+假名", "廣原ふう"),
    ("纯假名", "こまどり"), ("纯假名", "ゆかな"),
    ("罗马音/拉丁", "Erino Matsumoto"), ("罗马音/拉丁", "Suzuki"),
    ("罗马音/拉丁", "Lia"), ("罗马音/拉丁", "SOUNGDOK"),
    ("韩文", "김하늘"),
    ("真中文", "刘德华"), ("真中文", "周星驰"),
    ("占位符", "(voice)"), ("占位符", "(CV)"), ("占位符", "待补充"), ("占位符", "M"),
]

print(f"{'类别':<12} {'名字':<20} {'已是中文':<8} {'无内容':<8} {'占位符':<8} 判定")
print("-" * 78)
_verdict = {}
for _cat, _n in _NAMES:
    _zh = bool(_t._skip_no_translate(_n))
    _un = bool(_t._tx_untranslatable(_n))
    _plh = bool(_ph(_T, _n))
    if _zh:
        _v = "❌ 无需操作（已是中文）"
    elif _un:
        _v = "❌ 无需操作（无内容）"
    elif _plh:
        _v = "❌ 无需操作（占位符）"
    else:
        _v = "✅ 送翻译"
    _verdict[_n] = _v
    print(f"{_cat:<12} {_n:<20} {str(_zh):<8} {str(_un):<8} {str(_plh):<8} {_v}")

_noop_names = [_n for _n in _verdict if _verdict[_n].startswith("❌")]
print(f"\n小结：{len(_NAMES)} 个名字里 {len(_noop_names)} 个被判「无需操作」→ 永不送翻译：")
print("      " + "、".join(_noop_names))

# ═══════════════ B) 「已有译文」口径复现 ═══════════════
print("\n" + "=" * 78)
print("B) 恢复场景「已有译文」口径 —— 真 SQLite 复现（Grow Up Show 剧本）")
print("=" * 78)
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("epl_db_probe479", str(PLUGIN_DIR / "db.py"))
_db = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_db)
_db.PeopleDb.ensure_table()

PID = "EmbyPeopleLocalizeProbe479"
SRV = "___1_192_168_2_15_8096"
ITEM = "296101"          # 剧（集与剧共用这个 item_id）
NFO1 = "/v/Grow Up Show/S01E01.nfo"
NFO2_OLD = "/v/Grow Up Show/S01E02 @ADWeb.nfo"
NFO2_NEW = "/v/Grow Up Show/S01E02 @ADWebm.nfo"   # 本次实际是改名后重新入库
_pdb = _db.PeopleDb()
_pdb.clear_all(plugin_id=PID)
_pdb.delete_item(plugin_id=PID, item_id=ITEM, server_id=None)


def _ins(ep, nfo, name, zh, emby_id):
    return _pdb.upsert_people(
        plugin_id=PID, server_id=SRV, item_id=ITEM, item_type="Episode",
        title=f"S01E0{ep}", series_name="Grow Up Show", season_num=1, episode_num=ep,
        people=[{"before_name": name, "Name": zh, "before_role": f"r{ep}", "Role": f"角{ep}"}],
        nfo_path=nfo, emby_item_id=emby_id)


def _counts(tag):
    _c = _pdb.item_translation_counts(plugin_id=PID, pairs=[(SRV, ITEM)]) or {}
    _v = _c.get((SRV, ITEM)) or {"total": 0, "translated": 0}
    print(f"  [{tag}] item_translation_counts((SRV,296101)) → total={_v['total']} translated={_v['translated']}")
    return _v


def _rows():
    _r = _db._q("SELECT season_num, episode_num, name_before, name_after, nfo_path, "
                "emby_item_id, COALESCE(deleted_at,'') dz FROM person WHERE plugin_id=? "
                "AND item_id=? ORDER BY episode_num", (PID, ITEM))
    for _x in _r:
        print(f"      S{_x['season_num']}E{_x['episode_num']} {_x['name_before']}→{_x['name_after']!r} "
              f"nfo={os.path.basename(str(_x['nfo_path']))} emby={_x['emby_item_id']} "
              f"观察期={bool(str(_x['dz']).strip())}")


print("① 初次入库：E01/E02 都已翻译（name_after = 中文）")
_ins(1, NFO1, "A", "甲", "32085")
_ins(2, NFO2_OLD, "B", "乙", "32046")
_counts("初次入库")
_rows()

print("\n② 删除 E02 → 进入观察期")
_pdb.mark_deleted_by_nfo_path(plugin_id=PID, nfo_path=NFO2_OLD, server_id=SRV)
_counts("E02 观察期中")
_rows()

print("\n③ E02 改名重新入库（Emby Id 32087、nfo 改成 @ADWebm.nfo）→ 恢复继承")
_ins(2, NFO2_NEW, "B", "B", "32087")          # 新 nfo 里 Name 仍是英文 B（等插件翻译）
_counts("E02 恢复后")
_rows()

print("\n③b 再入库一集：**人名未译（纯汉字日文名 → 判『已是中文』）但第二排已译** —— Grow Up Show 的真实情况")
_ins(3, "/v/Grow Up Show/S01E03 @ADWeb.nfo", "C", "C", "32088")   # Name == before_name → 人名无译文
_counts("E03（仅第二排有译文）")
_rows()

print("\n④ 口径陷阱对照")
_c2 = _pdb.item_translation_counts(plugin_id=PID, pairs=[("", ITEM)]) or {}
print(f"  pairs=[('', 296101)]（server 传空）        → {_c2.get(('', ITEM)) or {'total':0,'translated':0}}")
_c3 = _pdb.item_translation_counts(plugin_id=PID, pairs=[(SRV, "")]) or {}
print(f"  pairs=[(SRV, '')]（item 传空 → 被跳过）    → {_c3 or {}}")
_c4 = _pdb.item_translation_counts(plugin_id=PID, pairs=[(SRV, "999999")]) or {}
print(f"  pairs=[(SRV, '999999')]（item 不存在）     → {_c4.get((SRV,'999999')) or {'total':0,'translated':0}}")

print("\n⑤ item_identity(296101)（剧/集共用 item_id → 只返回一行，①根因）")
print("  " + repr(_pdb.item_identity(plugin_id=PID, item_id=ITEM, server_id=SRV)))

print("\n⑥ emby_item_id_by_nfo_path（v4.7.9 新增的文件级定位）")
for _p in (NFO1, NFO2_NEW, NFO2_OLD):
    print(f"  {os.path.basename(_p):<45} → {_pdb.emby_item_id_by_nfo_path(plugin_id=PID, nfo_path=_p, server_id=SRV)!r}")

_pdb.clear_all(plugin_id=PID)
_pdb.delete_item(plugin_id=PID, item_id=ITEM, server_id=None)
print("\n完成（诊断脚本，不改任何生产代码）")
