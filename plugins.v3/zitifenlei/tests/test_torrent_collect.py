"""种子字体收集：文件清单归一、候选筛选、解压分派、执行器、闸门与手动扫描。

全部用假下载器实例，不依赖 MoviePilot 宿主；不访问网络。
"""

import importlib
import threading
import time
import zipfile
from pathlib import Path

import pytest

from ziti_under_test import archive_utils as au
from ziti_under_test import torrent_utils as tq
from ziti_under_test.db import FontDB


# ─── 假下载器 ────────────────────────────────────────────────────────────


class _FakeModule:
    def __init__(self, mapping=None):
        self._mapping = mapping or {}

    def normalize_return_path(self, path, downloader):
        p = Path(path).as_posix()
        for src, dst in self._mapping.items():
            if p == src or p.startswith(src.rstrip("/") + "/"):
                return dst + p[len(src):]
        return p


class _FakeService:
    def __init__(self, instance, mapping=None, stype="qbittorrent"):
        self.instance = instance
        self.module = _FakeModule(mapping)
        self.type = stype


class _FakeInstance:
    def __init__(self, files=None, meta=None, completed=None):
        self._files = files or []
        self._meta = meta or {}
        self._completed = completed or []

    def get_files(self, _tid):
        return self._files

    def get_torrents(self, ids=None, status=None, tags=None):
        return [self._meta], False

    def get_completed_torrents(self, ids=None, tags=None):
        return self._completed


def _plugin(tmp_path: Path):
    plugin_mod = importlib.import_module("ziti_under_test.__init__")
    plugin = plugin_mod.Zitifenlei()
    plugin._db = FontDB(tmp_path / "ziti.db")
    plugin._enabled = True
    plugin._tmp_dir = tmp_path / "tmp"
    plugin._tmp_dir.mkdir(parents=True, exist_ok=True)
    lib = tmp_path / "lib"
    lib.mkdir(parents=True, exist_ok=True)
    plugin._config.update(
        {
            "lib_dir": str(lib),
            "torrent_enabled": True,
            "torrent_wait_sec": 5,
            "torrent_delay_sec": 0,
            "torrent_max_file_mb": 64,
            "torrent_max_files": 50,
        }
    )
    return plugin, lib


# ─── 纯函数：进度归一 / 候选筛选 ──────────────────────────────────────────


def test_normalize_file_progress_across_downloaders():
    qb = tq.normalize_file({"name": "Fonts/a.ttf", "size": 100, "progress": 1, "index": 0})
    assert qb["progress"] == 1.0
    rt = tq.normalize_file({"name": "Fonts/b.ttf", "size": 100, "progress": 100, "id": 1})
    assert rt["progress"] == 1.0
    tr = tq.normalize_file({"name": "Fonts/c.ttf", "size": 200, "bytesCompleted": 50, "index": 2})
    assert tr["progress"] == 0.25


def test_pick_candidates_filters(tmp_path):
    root = tmp_path / "dl"
    (root / "Fonts").mkdir(parents=True)
    files = [
        {"name": "Fonts/a.ttf", "size": 10, "progress": 1.0, "index": 0},
        {"name": "Fonts/b.otf", "size": 10, "progress": 0.5, "index": 1},  # 未下完
        {"name": "Fonts/pack.zip", "size": 10, "progress": 1.0, "index": 2},  # 命中关键词
        {"name": "video/other.zip", "size": 10, "progress": 1.0, "index": 3},  # 无关键词
        {"name": "Fonts/huge.ttf", "size": 500 * 1024 * 1024, "progress": 1.0, "index": 4},
        {"name": "Fonts/sub.ass", "size": 10, "progress": 1.0, "index": 5},
    ]
    cands, stats = tq.pick_candidates(files, str(root), "font,字体", 64, 50)
    kinds = {(c["name"], c["kind"]) for c in cands}
    assert ("Fonts/a.ttf", "font") in kinds
    assert ("Fonts/pack.zip", "archive") in kinds
    assert all("b.otf" not in c["name"] for c in cands)
    assert all("huge.ttf" not in c["name"] for c in cands)
    assert stats["pending"] == 1
    assert stats["too_large"] == 1


def test_pick_candidates_respects_max_files(tmp_path):
    root = tmp_path / "dl"
    root.mkdir()
    files = [
        {"name": f"Fonts/{i}.ttf", "size": 1, "progress": 1.0, "index": i} for i in range(10)
    ]
    cands, _ = tq.pick_candidates(files, str(root), "font", 64, 3)
    assert len(cands) == 3


def test_map_download_path_uses_module_mapping():
    service = _FakeService(_FakeInstance(), {"/downloads": "/volume1/downloads"})
    assert tq.map_download_path("/downloads/a", service, "q") == "/volume1/downloads/a"
    assert tq.map_download_path("/other/a", service, "q") == "/other/a"


# ─── 解压分派：zip 恒支持，7z/rar 取决于工具 ─────────────────────────────


def test_archive_extensions_depend_on_tools(monkeypatch):
    monkeypatch.setattr(au, "detect_extract_tools", lambda refresh=False: {})
    assert au.archive_extensions() == (".zip",)
    assert not au.is_archive("a.7z")
    assert au.is_any_archive("a.7z")

    monkeypatch.setattr(au, "detect_extract_tools", lambda refresh=False: {"7z": "7z"})
    assert ".7z" in au.archive_extensions()
    assert ".rar" in au.archive_extensions()
    assert au.is_archive("a.7z") and au.is_archive("a.rar")


def test_extract_archive_without_tool_reports_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(au, "detect_extract_tools", lambda refresh=False: {})
    src = tmp_path / "a.7z"
    src.write_bytes(b"not-real")
    result = au.extract_archive(src, tmp_path / "out", (".ttf",))
    assert not result.files
    assert result.errors and "未检测到" in result.errors[0][1]


def test_extract_external_copies_allowed_files(tmp_path, monkeypatch):
    src = tmp_path / "fonts.7z"
    src.write_bytes(b"fake")
    monkeypatch.setattr(au, "detect_extract_tools", lambda refresh=False: {"7z": "7z"})
    monkeypatch.setattr(au, "_precheck_with_7z", lambda *a, **k: None)

    def _fake_run(cmd, **kwargs):
        outdir = Path(str(cmd[4])[2:] if str(cmd[4]).startswith("-o") else str(cmd[4]))
        (outdir / "Fonts").mkdir(parents=True, exist_ok=True)
        (outdir / "Fonts" / "a.ttf").write_bytes(b"AAAA")
        (outdir / "Fonts" / "skip.ass").write_bytes(b"x")
        (outdir / "Fonts" / "nested.zip").write_bytes(b"x")

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""

        return _R()

    monkeypatch.setattr(au.subprocess, "run", _fake_run)
    result = au.extract_external(src, tmp_path / "out", (".ttf",))
    names = [Path(f.path).name for f in result.files]
    assert names == ["a.ttf"]
    assert (tmp_path / "out" / "Fonts" / "a.ttf").is_file()
    reasons = {m: r for m, r in result.skipped}
    assert any("嵌套压缩包" in r for r in reasons.values())
    # 隔离临时目录必须清理干净
    assert not list((tmp_path / "out").glob(".extract_*"))


# ─── 执行器：载入 → 暂存 → 归档 → 记录 → 清理 ────────────────────────────


def test_torrent_job_records_and_cleans_staging(tmp_path, monkeypatch):
    plugin, lib = _plugin(tmp_path)
    dl = tmp_path / "dl" / "Fonts"
    dl.mkdir(parents=True)
    font = dl / "a.ttf"
    font.write_bytes(b"fake-font")

    instance = _FakeInstance(
        files=[{"name": "Fonts/a.ttf", "size": 9, "progress": 1.0, "index": 0}],
        meta={"hash": "h" * 40, "name": "测试种子", "save_path": str(tmp_path / "dl"), "completion_on": 1},
    )
    monkeypatch.setattr(tq, "get_downloader_service", lambda name: _FakeService(instance))

    def _fake_archive(folder, *a, **k):
        names = [p.name for p in Path(folder).rglob("*") if p.is_file()]
        return {
            "added": names, "skipped": [], "failed": 0, "pending": 0,
            "dup_deleted": 0, "delete_failed": 0,
        }

    monkeypatch.setattr(plugin, "_archive_from_dir", _fake_archive)
    monkeypatch.setattr(plugin, "_rebuild_subset_index_silent", lambda: (True, ""))
    monkeypatch.setattr(plugin, "_recheck_missing_after_library_change", lambda *a, **k: None)

    res = plugin._ensure_torrent_collect("h" * 40, "下载器1", source="manual", wait=True)
    assert res["state"] == "done"
    assert res["added"] == 1
    rows = plugin._db.list_torrent_ingest()
    assert rows and rows[0]["status"] == "done" and rows[0]["added"] == 1
    assert not list((tmp_path / "tmp").glob("torrent_*"))
    # 源文件绝不能被删/移
    assert font.is_file()


def test_torrent_job_empty_when_no_font_candidate(tmp_path, monkeypatch):
    plugin, _lib = _plugin(tmp_path)
    dl = tmp_path / "dl"
    dl.mkdir()
    instance = _FakeInstance(
        files=[{"name": "a.mkv", "size": 10, "progress": 1.0, "index": 0}],
        meta={"hash": "e" * 40, "name": "无字体种子", "save_path": str(dl), "completion_on": 1},
    )
    monkeypatch.setattr(tq, "get_downloader_service", lambda name: _FakeService(instance))

    res = plugin._ensure_torrent_collect("e" * 40, "下载器1", source="manual", wait=True)
    assert res["state"] == "empty"
    rows = plugin._db.list_torrent_ingest()
    assert rows and rows[0]["status"] == "empty"
    assert not list((tmp_path / "tmp").glob("torrent_*"))


def test_torrent_job_empty_archive_is_not_failure(tmp_path, monkeypatch):
    """压缩包能解开但里面没有字体：不算失败，状态 empty，下一步（检查/子集）照常走。"""
    plugin, _lib = _plugin(tmp_path)
    dl = tmp_path / "dl" / "Fonts"
    dl.mkdir(parents=True)
    pack = dl / "Fonts.zip"
    with zipfile.ZipFile(pack, "w") as zf:
        zf.writestr("readme.txt", "no font here")
        zf.writestr("cover.png", b"\x89PNG\r\n")

    instance = _FakeInstance(
        files=[
            {
                "name": "Fonts/Fonts.zip",
                "size": pack.stat().st_size,
                "progress": 1.0,
                "index": 0,
            }
        ],
        meta={
            "hash": "f" * 40,
            "name": "空字体包",
            "save_path": str(tmp_path / "dl"),
            "completion_on": 1,
        },
    )
    monkeypatch.setattr(tq, "get_downloader_service", lambda name: _FakeService(instance))
    monkeypatch.setattr(
        plugin,
        "_archive_from_dir",
        lambda folder, *a, **k: {
            "added": [], "skipped": [], "failed": 0, "pending": 0,
            "dup_deleted": 0, "delete_failed": 0,
        },
    )

    res = plugin._ensure_torrent_collect("f" * 40, "下载器1", source="manual", wait=True)
    assert res["state"] == "empty"
    assert res["failed"] == 0
    rows = plugin._db.list_torrent_ingest()
    assert rows and rows[0]["status"] == "empty"
    assert "空包 1 个" in (rows[0]["detail"] or "")
    assert not list((tmp_path / "tmp").glob("torrent_*"))
    # 源压缩包绝不能被动到
    assert pack.is_file()


def test_torrent_collect_disabled_does_nothing(tmp_path, monkeypatch):
    plugin, _lib = _plugin(tmp_path)
    plugin._config["torrent_enabled"] = False
    called = []
    monkeypatch.setattr(tq, "get_downloader_service", lambda name: called.append(name) or None)
    res = plugin._ensure_torrent_collect("x" * 40, "q", source="inbound", wait=True)
    assert res["state"] == "skipped"
    assert not called


def test_gate_timeout_returns_timeout(tmp_path):
    plugin, _lib = _plugin(tmp_path)
    plugin._config["torrent_wait_sec"] = 0
    job = {"event": threading.Event(), "state": "running", "stats": {"added": 0}}
    with plugin._torrent_jobs_lock:
        plugin._torrent_jobs["t" * 40] = job
    res = plugin._ensure_torrent_collect("t" * 40, "q", source="inbound", wait=True)
    assert res["state"] == "timeout"


# ─── 手动扫描：基线之前的历史种子一律跳过 ────────────────────────────────


def test_manual_scan_skips_history(tmp_path, monkeypatch):
    plugin, _lib = _plugin(tmp_path)
    now = int(time.time())
    plugin._db.set_setting("torrent_baseline_ts", now - 10)
    completed = [
        {"hash": "old" * 10, "name": "历史", "save_path": "/dl", "completion_on": now - 1000},
        {"hash": "new" * 10, "name": "新种子", "save_path": "/dl", "completion_on": now},
    ]
    instance = _FakeInstance(completed=completed)
    monkeypatch.setattr(tq, "list_downloaders", lambda: [{"name": "q", "type": "qbittorrent"}])
    monkeypatch.setattr(tq, "get_downloader_service", lambda name: _FakeService(instance))
    queued = []
    monkeypatch.setattr(
        plugin, "_ensure_torrent_collect",
        lambda h, d, source="inbound", wait=False: queued.append(h) or {"state": "queued"},
    )
    res = plugin._torrent_scan("", 0)
    assert res["scanned"] == 2
    assert res["skipped"] == 1
    assert res["queued"] == 1
    assert queued == ["new" * 10]


# ─── 检查通知：种子收集补充说明只写在检查通知里 ──────────────────────────


def test_notify_show_scan_includes_torrent_note(tmp_path, monkeypatch):
    plugin, _lib = _plugin(tmp_path)
    plugin._config["notify_enabled"] = True
    sent = []
    monkeypatch.setattr(plugin, "post_message", lambda **kw: sent.append(kw) or True)
    plugin._notify_show_scan(
        "某剧", 2, 0, {"missing": "某字体"}, extra_lines=["种子收集：补充 3 个字体（来自 某种子）"]
    )
    assert sent and "种子收集：补充 3 个字体" in sent[0]["text"]


# ─── DB：记录写入 / 幂等查询 / 清空 ──────────────────────────────────────


def test_db_torrent_ingest_crud(tmp_path):
    db = FontDB(tmp_path / "ziti.db")
    rid = db.add_torrent_ingest("h" * 40, "q", "种子", "manual", "done", 2, 1, 1, 0, "ok")
    assert rid > 0
    assert db.get_torrent_ingest_by_hash("h" * 40)
    assert len(db.list_torrent_ingest()) == 1
    db.update_torrent_ingest(rid, status="empty", added=0)
    assert db.list_torrent_ingest()[0]["status"] == "empty"
    assert db.clear_torrent_ingest() == 1
    assert not db.list_torrent_ingest()
    db.close()
