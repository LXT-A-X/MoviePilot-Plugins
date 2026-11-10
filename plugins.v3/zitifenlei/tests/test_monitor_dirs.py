# -*- coding: utf-8 -*-
"""v3.2.3 回归：监控目录类型判定 + 字体监控目录压缩包处理（不依赖宿主）。"""
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


def test_watch_dir_kind_priority(tmp_path):
    dirs = {
        "input_dir": str(tmp_path / "fonts"),
        "ass_dir": str(tmp_path / "subs"),
        "subset_dir": str(tmp_path / "subs" / "subset"),
        "lib_dir": str(tmp_path / "lib"),
        "missing_font_dir": str(tmp_path / "miss"),
    }
    plugin = _plugin()
    plugin.get_resource_or_config = lambda key: dirs.get(key, "")

    assert plugin._watch_dir_kind(tmp_path / "fonts" / "a.ttf") == "input"
    assert plugin._watch_dir_kind(tmp_path / "fonts" / "pack.7z") == "input"
    assert plugin._watch_dir_kind(tmp_path / "subs" / "a.ass") == "ass"
    # 子目录更具体：subset 优先于 ass
    assert plugin._watch_dir_kind(tmp_path / "subs" / "subset" / "a.ass") == "subset"
    assert plugin._watch_dir_kind(tmp_path / "subs" / "font.ttf") == "ass"
    assert plugin._watch_dir_kind(tmp_path / "lib" / "f.ttf") == "lib"
    assert plugin._watch_dir_kind(tmp_path / "miss" / "m.ttf") == "missing"
    assert plugin._watch_dir_kind(tmp_path / "other" / "z.ttf") == ""


def test_handle_font_archive_extracts_once(tmp_path):
    plugin = _plugin()
    plugin._db = _FakeDB()
    plugin._tmp_dir = str(tmp_path / "tmp")
    plugin._notify_agg = {"fonts": []}
    plugin._lock = threading.RLock()
    plugin._schedule_index_rebuild = lambda: None
    plugin._queue_agg_notify = lambda: None
    plugin.get_resource_or_config = lambda key: {"lib_dir": str(tmp_path / "lib"), "archive_mode": "copy"}.get(key, "")

    archive = tmp_path / "fonts.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("a.ttf", b"\x00" * 256)
        zf.writestr("readme.txt", b"ignore me")

    handled = []
    plugin._archive_font_file = lambda f, source="auto", **kw: (handled.append(Path(f).name) or 1)

    assert plugin._handle_font_archive(archive) is True
    assert handled == ["a.ttf"]
    # 同一包（路径+大小+mtime 指纹）第二次应直接跳过，不重复解压
    assert plugin._handle_font_archive(archive) is True
    assert handled == ["a.ttf"]
    assert any("监控压缩包" in msg for _, msg in plugin._db.logs)


def test_handle_font_archive_7z_uses_archive_utils(tmp_path, monkeypatch):
    plugin = _plugin()
    plugin._db = _FakeDB()
    plugin._tmp_dir = str(tmp_path / "tmp")
    plugin._notify_agg = {"fonts": []}
    plugin._lock = threading.RLock()
    plugin._schedule_index_rebuild = lambda: None
    plugin._queue_agg_notify = lambda: None
    plugin.get_resource_or_config = lambda key: {"lib_dir": str(tmp_path / "lib")}.get(key, "")

    archive = tmp_path / "fonts.7z"
    archive.write_bytes(b"fake-7z")

    def _fake_extract(archive_path, dest_dir, exts, **kwargs):
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        font = dest / "b.ttf"
        font.write_bytes(b"\x01" * 128)
        result = au.ExtractResult()
        result.files.append(au.ExtractedFile(path=font, member="b.ttf", size=128))
        return result

    monkeypatch.setattr(au, "is_any_archive", lambda name: True)
    monkeypatch.setattr(au, "is_archive", lambda name: True)
    monkeypatch.setattr(au, "extract_archive", _fake_extract)

    handled = []
    plugin._archive_font_file = lambda f, source="auto", **kw: (handled.append(Path(f).name) or 1)
    assert plugin._handle_font_archive(archive) is True
    assert handled == ["b.ttf"]
