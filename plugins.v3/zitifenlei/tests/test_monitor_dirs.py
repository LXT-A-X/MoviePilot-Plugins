# -*- coding: utf-8 -*-
"""v3.3.0 回归：监控目录类型 / 压缩包待确认稳定副本 / 清理策略 / 放错目录提醒。"""
import importlib
import threading
import zipfile
from pathlib import Path

import pytest

from ziti_under_test import archive_utils as au


def _plugin():
    mod = importlib.import_module("ziti_under_test.__init__")
    return object.__new__(mod.Zitifenlei)


class _FakeDB:
    def __init__(self):
        self.logs = []
        self.settings = {}

    def add_log(self, message, level="info"):
        self.logs.append((level, message))

    def get_setting(self, key, default=None):
        return self.settings.get(key, default)

    def set_setting(self, key, value):
        self.settings[key] = value


def _make_zip(path: Path, names=("a.ttf", "readme.txt")):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for name in names:
            zf.writestr(name, b"\x00" * 128)


def _page_plugin(tmp: Path, cfg=None, archive_ret=1):
    plugin = _plugin()
    plugin._db = _FakeDB()
    plugin._tmp_dir = str(tmp / "tmp")
    plugin._notify_agg = {"fonts": [], "archives": [], "archives_wrong_dir": []}
    plugin._lock = threading.RLock()
    plugin._stopping = False
    plugin._schedule_index_rebuild = lambda: None
    plugin._queue_agg_notify = lambda: None
    conf = {"lib_dir": str(tmp / "lib"), "input_dir": str(tmp / "input")}
    conf.update(cfg or {})
    plugin.get_resource_or_config = lambda key: conf.get(key, "")
    handled = []

    def _archive(f, source="auto", **kw):
        handled.append(Path(f))
        return archive_ret

    plugin._archive_font_file = _archive
    return plugin, handled


def test_watch_dir_kind_without_missing(tmp_path):
    dirs = {
        "input_dir": str(tmp_path / "fonts"),
        "ass_dir": str(tmp_path / "subs"),
        "subset_dir": str(tmp_path / "subs" / "subset"),
        "lib_dir": str(tmp_path / "lib"),
        # v3.3.0 起删除「缺失字体接收目录」，旧键即使存在也应被忽略
        "missing_font_dir": str(tmp_path / "miss"),
    }
    plugin = _plugin()
    plugin.get_resource_or_config = lambda key: dirs.get(key, "")

    assert plugin._watch_dir_kind(tmp_path / "fonts" / "a.ttf") == "input"
    assert plugin._watch_dir_kind(tmp_path / "fonts" / "pack.7z") == "input"
    assert plugin._watch_dir_kind(tmp_path / "subs" / "a.ass") == "ass"
    assert plugin._watch_dir_kind(tmp_path / "subs" / "subset" / "a.ass") == "subset"
    assert plugin._watch_dir_kind(tmp_path / "subs" / "font.ttf") == "ass"
    assert plugin._watch_dir_kind(tmp_path / "lib" / "f.ttf") == "lib"
    assert plugin._watch_dir_kind(tmp_path / "miss" / "m.ttf") == ""


def test_monitor_dirs_requires_configured_existing_dirs(tmp_path):
    plugin = _plugin()
    for name in ("fonts", "subs", "lib"):
        (tmp_path / name).mkdir()
    plugin.get_resource_or_config = lambda key: {
        "input_dir": str(tmp_path / "fonts"),
        "ass_dir": str(tmp_path / "subs"),
        "lib_dir": str(tmp_path / "lib"),
        "subset_dir": str(tmp_path / "missing-dir"),
    }.get(key, "")
    dirs = [str(p.resolve()) for p in plugin._monitor_dirs()]
    assert str((tmp_path / "fonts").resolve()) in dirs
    assert str((tmp_path / "subs").resolve()) in dirs
    assert str((tmp_path / "lib").resolve()) in dirs
    assert str((tmp_path / "missing-dir").resolve()) not in dirs


def test_archive_cleanup_off_keeps_package(tmp_path):
    plugin, handled = _page_plugin(tmp_path)
    archive = tmp_path / "input" / "pack.zip"
    _make_zip(archive)

    assert plugin._handle_font_archive(archive) is True
    assert archive.is_file()
    assert handled
    entry = plugin._notify_agg["archives"][-1]
    assert entry["added"] == 1
    assert entry["action"] == ""
    assert "未开启" in entry["keep_reason"]


def test_archive_cleanup_move_to_done_dir(tmp_path):
    plugin, _ = _page_plugin(tmp_path, {"archive_cleanup_enabled": True, "archive_cleanup_action": "move"})
    archive = tmp_path / "input" / "pack.zip"
    _make_zip(archive)

    assert plugin._handle_font_archive(archive) is True
    assert not archive.exists()
    assert (tmp_path / "input" / "已处理压缩包" / "pack.zip").is_file()
    assert plugin._notify_agg["archives"][-1]["action"] == "moved"


def test_archive_cleanup_delete(tmp_path):
    plugin, _ = _page_plugin(tmp_path, {"archive_cleanup_enabled": True, "archive_cleanup_action": "delete"})
    archive = tmp_path / "input" / "pack.zip"
    _make_zip(archive)

    assert plugin._handle_font_archive(archive) is True
    assert not archive.exists()
    assert plugin._notify_agg["archives"][-1]["action"] == "deleted"


def test_archive_pending_uses_stable_copy(tmp_path):
    plugin, handled = _page_plugin(tmp_path, {"auto_collect": False}, archive_ret=-1)
    archive = tmp_path / "input" / "pack.zip"
    _make_zip(archive)

    assert plugin._handle_font_archive(archive) is True
    # 待确认字体必须在解压目录被清理后仍然存在（稳定副本）
    assert handled and handled[0].is_file()
    assert handled[0].parent == Path(plugin._tmp_dir)
    assert archive.is_file()
    entry = plugin._notify_agg["archives"][-1]
    assert entry["pending"] == 1
    assert entry["action"] == ""
    assert "待确认" in entry["keep_reason"]


def test_archive_failure_keeps_package(tmp_path):
    plugin, _ = _page_plugin(tmp_path, {"archive_cleanup_enabled": True}, archive_ret=None)
    archive = tmp_path / "input" / "pack.zip"
    _make_zip(archive)

    assert plugin._handle_font_archive(archive) is True
    assert archive.is_file()
    entry = plugin._notify_agg["archives"][-1]
    assert entry["failed"] == 1
    assert entry["action"] == ""
    assert "失败" in entry["keep_reason"]


def test_font_dir_subtitle_archive_kept_with_upload_hint(tmp_path):
    plugin, handled = _page_plugin(tmp_path)
    archive = tmp_path / "input" / "subtitle.zip"
    _make_zip(archive, names=("ep.ass", "readme.txt"))

    assert plugin._handle_font_archive(archive) is True
    assert archive.is_file()
    assert not handled
    entry = plugin._notify_agg["archives"][-1]
    assert entry["total"] == 0
    assert entry["keep_reason"] and "字幕" in entry["keep_reason"]
    assert any("检查 / 子集化" in msg for _, msg in plugin._db.logs)


def test_archive_in_wrong_dir_notified_and_kept(tmp_path):
    plugin, _ = _page_plugin(tmp_path, {"ass_dir": str(tmp_path / "subs")})
    (tmp_path / "subs").mkdir()
    archive = tmp_path / "subs" / "fonts.zip"
    _make_zip(archive)

    plugin._log_dir_mismatch(archive, "ass", False, False, True)
    assert archive.is_file()
    assert plugin._notify_agg["archives_wrong_dir"][-1]["label"] == "ASS 字幕检查目录"
    assert any("放错目录" in msg for _, msg in plugin._db.logs)
    assert any("字幕压缩包" in msg for _, msg in plugin._db.logs)


def test_deprecated_config_keys_stripped():
    mod = importlib.import_module("ziti_under_test.__init__")
    plugin = object.__new__(mod.Zitifenlei)
    plugin._config = {
        "enabled": True,
        "input_dir": "/tmp/fonts",
        "monitor_enabled": True,
        "missing_font_dir": "/tmp/missing",
        "subset_process_isolation": False,
    }
    form = mod.Zitifenlei.get_form(plugin)[1]
    for key in ("monitor_enabled", "missing_font_dir", "subset_process_isolation"):
        assert key not in form
    assert form.get("input_dir") == "/tmp/fonts"
