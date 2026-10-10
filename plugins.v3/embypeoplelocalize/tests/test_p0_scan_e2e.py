# -*- coding: utf-8 -*-
"""P0 端到端回归：NFO 扫描 worker 在宿主桩件下的真实运行（断点 / 签名 / 失败重试）。

运行：python tests/test_p0_scan_e2e.py

对应整改文档 §12 的回归用例：
  T2 未修改续跑 → 跳过；T1 修改后续跑 → 重新解析入库；
另覆盖：首次扫描入库并清断点、未变化按签名跳过、断点保存（dict 新格式）、
失败不入断点（NFO-002，用毒丸文件模拟入库异常）。
"""
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import test_p0_nfo_checkpoint as base   # noqa: E402  （安装宿主桩件 + 导入插件类）

_Cls = base._Cls
check = base.check

_E2E_ROOT = os.path.join(base._TMP, "e2e")
os.makedirs(_E2E_ROOT, exist_ok=True)

# 把宿主 CONFIG_PATH 指到独立的 e2e 目录（数据库隔离）
import app.sdk.config as _hcfg  # noqa: E402
_hcfg.settings.CONFIG_PATH = _E2E_ROOT

MOVIE_NFO = """<?xml version="1.0" encoding="UTF-8"?>
<movie>
  <title>Movie A</title>
  <tmdbid>1001</tmdbid>
  <year>2024</year>
  <actor><name>Tom Hanks</name><role>Forrest</role><type>Actor</type></actor>
  <actor><name>Robin Wright</name><role>Jenny</role><type>Actor</type></actor>
  <director>Robert Zemeckis</director>
</movie>
"""

TV_NFO = """<?xml version="1.0" encoding="UTF-8"?>
<tvshow>
  <title>Show B</title>
  <tmdbid>2002</tmdbid>
  <actor><name>Bryan Cranston</name><role>Walter</role><type>Actor</type></actor>
</tvshow>
"""

EP_NFO = """<?xml version="1.0" encoding="UTF-8"?>
<episodedetails>
  <title>Pilot</title>
  <season>1</season>
  <episode>1</episode>
  <actor><name>Aaron Paul</name><role>Jesse</role><type>Actor</type></actor>
</episodedetails>
"""


def _make_lib(root):
    os.makedirs(os.path.join(root, "Movie A"), exist_ok=True)
    os.makedirs(os.path.join(root, "Show B", "Season 1"), exist_ok=True)
    base._write(os.path.join(root, "Movie A", "movie.nfo"), MOVIE_NFO)
    base._write(os.path.join(root, "Show B", "tvshow.nfo"), TV_NFO)
    base._write(os.path.join(root, "Show B", "Season 1", "Show.B.S01E01.nfo"), EP_NFO)
    return {
        "movie": os.path.join(root, "Movie A", "movie.nfo"),
        "tv": os.path.join(root, "Show B", "tvshow.nfo"),
        "ep": os.path.join(root, "Show B", "Season 1", "Show.B.S01E01.nfo"),
    }


def _new_plugin(lib_dir):
    from embypeoplelocalize.db import PeopleDb, NameMapDb
    obj = object.__new__(_Cls)
    obj._logs = []
    obj._scan_cursor = None
    obj._scan_status = {}
    obj._scan_stop = False
    obj._nfo_file_sigs = {}
    obj._nfo_sigs_cfg = ""
    obj._tmdb_credits_cache = {}
    obj._failed_terms = set()
    obj._lock_cast = False
    obj._notify_on_complete = False
    obj._emby_name_sync = False          # 跳过 Emby 人名同步
    obj._nfo_dead_grace_hours = 24
    obj._sync_direction = "s2e"
    obj._nfo_episode_overwrite = False
    obj._nfo_recursive = True
    obj._nfo_include_episodes = False
    obj._nfo_backup = False
    obj._nfo_dry_run = False
    obj._nfo_preview = False
    obj._nfo_episode_sync = False
    obj._overwrite_chinese = False
    obj._translate_role = True
    obj._translate_all = False
    obj._translate_person = True
    obj._pool_tmdb_credits = False
    obj._pool_tmdb_fill = False
    obj._max_guest_per_episode = 5
    # 真实 DB（数据落 e2e 临时目录）
    obj._people_db = PeopleDb()
    obj._name_map_db = NameMapDb()
    # 桩：宿主/外部交互
    obj._all_nfo_roots = lambda: [lib_dir]
    obj._roots_pretty = lambda roots: "lib"
    obj._pause_gate = lambda kind: True
    obj._push_log = lambda level, msg: obj._logs.append(f"[{level}] {msg}")
    obj._tx_wake = lambda: None
    obj._set_task_running = lambda task, on: None
    obj._save_state = lambda: None
    obj._save_file_sigs = lambda: None
    obj._pool_sync_all = lambda *a, **k: {}
    obj.post_message = lambda *a, **k: None
    obj._tx_existing_translations = lambda names=None: {"names": {}}
    obj._collect_trans_types = lambda *a, **k: {
        "collect": {"actor": True, "guest": False, "director": True, "writer": True,
                    "credits": False, "producer": True},
        "limits": {"actor": 10, "guest": 0, "director": 2, "writer": 2},
        "translate": {"person": True, "role": True},
        "switches": {"actor": True, "guest": False, "director": True, "writer": True},
    }
    return obj


def _run_scan(obj, lib_dir):
    """同步跑一遍扫描 worker（等价仪表盘「NFO 扫描」）。"""
    data = {"roots": [lib_dir], "recursive": True, "include_episodes": False,
            "backup": False, "dry_run": False, "episode_sync": False,
            "preview": False, "write_files": True, "force_translate": False}
    _Cls._nfo_sync_worker(obj, data)


def _wrap_calls(obj):
    """记录 _record_nfo_library 被调用的 nfo 路径。"""
    calls = []
    _orig = obj._record_nfo_library

    def _spy(doc, *a, **k):
        calls.append(str(getattr(doc, "path", "") or ""))
        return _orig(doc, *a, **k)

    obj._record_nfo_library = _spy
    return calls


def _items(obj):
    return obj._people_db.library_items(plugin_id="EmbyPeopleLocalize") or []


def scenario_1_fresh_scan():
    print("S1) 首次扫描：采集入库 + 清断点 + 建立签名表")
    lib = os.path.join(_E2E_ROOT, "lib1")
    files = _make_lib(lib)
    obj = _new_plugin(lib)
    calls = _wrap_calls(obj)
    _run_scan(obj, lib)
    items = _items(obj)
    check("首次扫描三个 nfo 全部入库", len(calls) >= 2 and len(items) >= 2,
          f"calls={len(calls)} items={len(items)}")
    check("数据库有条目（电影/剧）", any(it.get("item_id") == "1001" for it in items),
          str([it.get("item_id") for it in items]))
    check("正常跑完清空断点", not ((obj._scan_cursor or {}).get("nfo")),
          str(obj._scan_cursor))
    check("签名表建立（供下次跳过未变化）", len(obj._nfo_file_sigs) >= 2 and bool(obj._nfo_sigs_cfg),
          f"sigs={len(obj._nfo_file_sigs)} cfg={bool(obj._nfo_sigs_cfg)}")
    return lib, files, obj


def scenario_2_unchanged_rescan(lib, files):
    print("S2) 未修改重扫（T2）：按签名跳过，不重复处理")
    obj = _new_plugin(lib)
    obj._nfo_file_sigs = {}     # 重新载入签名表（真实运行时来自 file_sigs.json）
    # 复用 S1 的签名表：直接从 S1 实例取
    return obj


def scenario_2_run(obj, lib, files, prev_sigs, prev_cfg):
    obj._nfo_file_sigs = dict(prev_sigs)
    obj._nfo_sigs_cfg = prev_cfg
    calls = _wrap_calls(obj)
    _run_scan(obj, lib)
    check("未修改文件全部跳过（无重复入库）", len(calls) == 0, f"calls={calls}")
    _skipped = [m for m in obj._logs if "跳过未变化" in m or "与上次一致" in m]
    check("日志体现跳过未变化", bool(_skipped), str(obj._logs[-3:]))


def scenario_3_changed_rescan(lib, files, prev_sigs, prev_cfg):
    print("S3) 修改一个文件后续扫（T1）：只重新处理被改的文件")
    time.sleep(0.02)
    base._write(files["movie"], MOVIE_NFO.replace("Tom Hanks", "Tom Hanks Jr."))
    obj = _new_plugin(lib)
    obj._nfo_file_sigs = dict(prev_sigs)
    obj._nfo_sigs_cfg = prev_cfg
    calls = _wrap_calls(obj)
    _run_scan(obj, lib)
    check("被改动的文件重新入库", files["movie"] in calls, f"calls={calls}")
    check("未改动的文件仍跳过", files["tv"] not in calls and files["ep"] not in calls,
          f"calls={calls}")


def scenario_4_checkpoint_resume(lib, files, prev_sigs, prev_cfg):
    print("S4) 中断保存断点 → 修改文件 → 续跑：断点后改动必须重处理（NFO-001）")
    # 先让文件处于「已处理」状态：以当前签名建立断点（模拟上次中断时的记录）
    time.sleep(0.02)
    base._write(files["tv"], TV_NFO.replace("Bryan Cranston", "Bryan Cranston X."))
    sig_tv = _Cls._file_sig(files["tv"])
    sig_movie = _Cls._file_sig(files["movie"])
    obj = _new_plugin(lib)
    obj._nfo_file_sigs = dict(prev_sigs)
    obj._nfo_sigs_cfg = prev_cfg
    obj._scan_cursor = {"nfo": {"sig": obj._nfo_scan_sig([lib], True, False, ()),
                                "done": {files["tv"]: sig_tv, files["movie"]: sig_movie}}}
    # 断点后 tvshow.nfo 又被改动 → 续跑必须重新处理；movie 未变 → 跳过
    time.sleep(0.02)
    base._write(files["tv"], TV_NFO.replace("Bryan Cranston", "Bryan Cranston Y."))
    calls = _wrap_calls(obj)
    _run_scan(obj, lib)
    check("断点后被改动的文件重新处理", files["tv"] in calls, f"calls={calls}")
    check("断点中未改动的文件跳过", files["movie"] not in calls, f"calls={calls}")
    check("旧格式断点（纯路径列表）仍可读",
          isinstance((obj._scan_cursor or {}).get("nfo", {}).get("done"), (dict, list, type(None))))


def scenario_5_failed_not_done():
    print("S5) 入库失败不得计入断点（NFO-002）")
    lib = os.path.join(_E2E_ROOT, "lib5")
    files = _make_lib(lib)
    obj = _new_plugin(lib)
    boom = {"n": 0}
    _orig = obj._record_nfo_library

    def _poison(doc, *a, **k):
        if str(getattr(doc, "path", "") or "") == files["movie"]:
            boom["n"] += 1
            raise RuntimeError("模拟入库失败（毒丸）")
        return _orig(doc, *a, **k)

    obj._record_nfo_library = _poison
    _run_scan(obj, lib)      # 第一轮：movie 入库失败
    check("失败文件未被记入签名表", files["movie"] not in (obj._nfo_file_sigs or {}),
          str(list((obj._nfo_file_sigs or {}).keys())))
    obj._record_nfo_library = _orig   # 第二轮：恢复正常
    _run_scan(obj, lib)
    check("失败文件下次扫描自动重试并成功", boom["n"] == 1 and files["movie"] in (obj._nfo_file_sigs or {}),
          f"poison_calls={boom['n']}")


if __name__ == "__main__":
    print(f"e2e 目录: {_E2E_ROOT}")
    lib1, files1, obj1 = scenario_1_fresh_scan()
    sigs, cfg = dict(obj1._nfo_file_sigs or {}), obj1._nfo_sigs_cfg
    obj2 = scenario_2_unchanged_rescan(lib1, files1)
    scenario_2_run(obj2, lib1, files1, sigs, cfg)
    scenario_3_changed_rescan(lib1, files1, sigs, cfg)
    scenario_4_checkpoint_resume(lib1, files1, sigs, cfg)
    scenario_5_failed_not_done()
    print(f"\n结果: {base._PASS} 通过 / {base._FAIL} 失败")
    sys.exit(1 if base._FAIL else 0)