"""第三批（P1-4 ~ P1-11）安全/边界回归测试。

覆盖：优雅停止排空、归档完整性辅助函数、全量索引原子重建中断、删库后拒绝重连、
删除边界（safe_unlink / inbound 产物不删）、缺失字体上传缓冲持久化与 TTL、
上传数量/大小上限（含半成品清理）、畸形 TTC 防炸、依赖安装异步化。
"""

import asyncio
import importlib
import os
import shutil
import struct
import threading
import time
from pathlib import Path

import pytest

from ziti_under_test import archive_utils as au
from ziti_under_test import font_metadata as fm
from ziti_under_test.db import FontDB

FONT_DIR = Path(r"C:\Windows\Fonts")
ARIAL = FONT_DIR / "arial.ttf"
MSYH = FONT_DIR / "msyh.ttc"

needs_fonts = pytest.mark.skipif(
    not (ARIAL.is_file() and MSYH.is_file()), reason="需要 Windows 系统字体"
)

plugin_mod = importlib.import_module("ziti_under_test.__init__")


# ─── 脚手架 ──────────────────────────────────────────────────────────────


class _Upload:
    def __init__(self, filename: str, data: bytes) -> None:
        self.filename = filename
        self._data = data

    async def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            data, self._data = self._data, b""
            return data
        chunk, self._data = self._data[:size], self._data[size:]
        return chunk


def _make_lib(tmp_path: Path) -> Path:
    lib = tmp_path / "lib"
    lib.mkdir(parents=True, exist_ok=True)
    for src in (ARIAL, MSYH):
        dst = lib / src.name
        if dst.exists():
            continue
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)
    return lib


def _plugin(tmp_path: Path, db: FontDB, lib: Path):
    plugin = plugin_mod.Zitifenlei()
    plugin._db = db
    plugin._enabled = True
    plugin._config.update({"lib_dir": str(lib)})
    plugin._tmp_dir = tmp_path / "tmp"
    plugin._tmp_dir.mkdir(parents=True, exist_ok=True)
    return plugin


# ─── P1-8 删除边界 ───────────────────────────────────────────────────────


def test_safe_unlink_boundaries(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    inside = root / "a.ttf"
    inside.write_bytes(b"x")
    outside = tmp_path / "outside.ttf"
    outside.write_bytes(b"y")

    # 越界 / 无允许根 / 目标等于根 / 后缀不符：一律拒绝
    assert au.safe_unlink(outside, root, exts=(".ttf",)) is False
    assert outside.exists()
    assert au.safe_unlink(inside) is False
    assert inside.exists()
    assert au.safe_unlink(root, root) is False
    assert au.safe_unlink(inside, root, exts=(".ass",)) is False
    assert inside.exists()
    # 目录本身不允许删
    sub = root / "sub"
    sub.mkdir()
    assert au.safe_unlink(sub, root) is False
    assert sub.exists()
    # 根内正常文件：删除；不存在视为成功（幂等）
    assert au.safe_unlink(inside, root, exts=(".ttf",)) is True
    assert not inside.exists()
    assert au.safe_unlink(inside, root, exts=(".ttf",)) is True


def test_subset_out_deletable_by_source(tmp_path):
    lib = _make_lib(tmp_path)
    db = FontDB(tmp_path / "ziti.db")
    try:
        plugin = _plugin(tmp_path, db, lib)
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        plugin._config.update({"subset_out_dir": str(out_dir), "ass_dir": str(tmp_path / "watch")})
        media_out = out_dir / "episode.ziti.ass"
        media_out.write_text("x", encoding="utf-8")

        # inbound（媒体库）产物即使落在输出目录也绝不删
        assert plugin._subset_out_deletable(str(media_out), "inbound") is False
        # 插件自有输出目录 + manual/watch 来源可删
        assert plugin._subset_out_deletable(str(media_out), "manual") is True
        assert plugin._subset_out_deletable(str(media_out), "watch") is True
        # 监控目录只在 watch 来源下算可删区域
        watch = tmp_path / "watch"
        watch.mkdir()
        watched = watch / "ep.ziti.ass"
        watched.write_text("x", encoding="utf-8")
        assert plugin._subset_out_deletable(str(watched), "manual") is False
        assert plugin._subset_out_deletable(str(watched), "watch") is True
        # 无 source 的旧记录：只认临时/输出目录
        assert plugin._subset_out_deletable(str(media_out), "") is True
        assert plugin._subset_out_deletable(str(watched), "") is False
    finally:
        db.close()


def test_path_within_is_component_wise(tmp_path):
    base = tmp_path / "测试"
    sibling = tmp_path / "测试2"
    base.mkdir()
    sibling.mkdir()
    inner = base / "sub"
    inner.mkdir()
    assert plugin_mod._path_within(inner, base) is True
    # 字符串前缀相同的平级目录不能被当成子目录
    assert plugin_mod._path_within(sibling, base) is False


# ─── P1-5 归档完整性辅助函数 ──────────────────────────────────────────────


def test_wait_file_stable_and_identical(tmp_path):
    old = tmp_path / "old.ttf"
    old.write_bytes(b"old")
    past = time.time() - 60
    os.utime(old, (past, past))
    assert plugin_mod._wait_file_stable(old) is True  # 已静置 → 直接判稳定
    assert plugin_mod._wait_file_stable(tmp_path / "missing.ttf") is False

    growing = tmp_path / "growing.ttf"
    growing.write_bytes(b"1")
    stop = threading.Event()

    def _writer():
        # 显式推进 mtime（步长 10ms，避开文件系统时间戳精度），稳定可判定为「仍在写入」
        base = time.time_ns()
        i = 0
        while not stop.is_set():
            i += 1
            stamp = base + i * 10_000_000
            try:
                os.utime(growing, ns=(stamp, stamp))
            except OSError:
                return
            time.sleep(0.02)

    t = threading.Thread(target=_writer, daemon=True)
    t.start()
    try:
        assert (
            plugin_mod._wait_file_stable(growing, timeout=0.3, interval=0.05, settle=100) is False
        )
    finally:
        stop.set()
        t.join(2)
    # 写完后连续两次 stat 一致 → 稳定
    assert plugin_mod._wait_file_stable(growing, timeout=3, interval=0.05, settle=0.05) is True

    twin = tmp_path / "twin.ttf"
    twin.write_bytes(growing.read_bytes())
    assert plugin_mod._files_identical(growing, twin) is True
    twin.write_bytes(growing.read_bytes() + b"extra")
    assert plugin_mod._files_identical(growing, twin) is False
    assert plugin_mod._files_identical(growing, tmp_path / "none.ttf") is False


def test_unique_archive_base(tmp_path):
    index = {("arial", ".ttf"): "x"}
    assert plugin_mod._unique_archive_base(index, "Arial", ".TTF") == "Arial-2"
    index[("arial-2", ".ttf")] = "y"
    assert plugin_mod._unique_archive_base(index, "Arial", ".TTF") == "Arial-3"


# ─── P1-4 优雅停止排空 ───────────────────────────────────────────────────


def test_wait_scan_drain_waits_active_jobs():
    plugin = plugin_mod.Zitifenlei()
    started = threading.Event()
    release = threading.Event()

    def _worker():
        plugin._job_begin()
        started.set()
        release.wait(3)
        plugin._job_end()

    worker = threading.Thread(target=_worker, daemon=True)
    worker.start()
    assert started.wait(2)

    drained = threading.Event()

    def _drain():
        plugin._wait_scan_drain(timeout=5)
        drained.set()

    drainer = threading.Thread(target=_drain, daemon=True)
    drainer.start()
    time.sleep(0.3)
    assert not drained.is_set()  # 归档任务未结束 → 不能提前排空关库
    release.set()
    worker.join(2)
    assert drained.wait(3)
    assert plugin._active_jobs == 0


# ─── P1-7 索引原子重建 ───────────────────────────────────────────────────


@needs_fonts
def test_full_rebuild_abort_keeps_old_index(tmp_path, monkeypatch):
    lib = _make_lib(tmp_path)
    db = FontDB(tmp_path / "ziti.db")
    try:
        for item in sorted(lib.iterdir()):
            if item.is_file():
                db.upsert_font_file(fm.inspect_font(item))
        before = db.index_stats()
        assert before["files"] == 2
        last_rebuild_before = db.index_get("last_rebuild", "")

        plugin = _plugin(tmp_path, db, lib)
        real = fm.inspect_font

        def _abort_on_first(path):
            plugin._stopping = True
            return real(path)

        monkeypatch.setattr(plugin_mod, "inspect_font", _abort_on_first)
        stats = plugin._rebuild_font_index(full=True)
        assert stats["ok"] is False
        assert "中止" in stats["error"]
        # 旧索引必须原样保留（不能出现「清空后裸奔」）
        after = db.index_stats()
        assert after["files"] == before["files"]
        assert after["faces"] == before["faces"]
        assert plugin._index_rebuilding is False
        assert db.index_get("last_rebuild", "") == last_rebuild_before  # 未写入新时间戳
    finally:
        db.close()


def test_db_close_refuses_reconnect(tmp_path):
    db = FontDB(tmp_path / "ziti.db")
    db.index_stats()
    db.close()
    with pytest.raises(RuntimeError):
        db.query_one("SELECT 1 AS v")


# ─── P1-10 缺失字体上传缓冲持久化 ────────────────────────────────────────


def test_missing_uploads_persist_prune_and_mapping_cleanup(tmp_path):
    db = FontDB(tmp_path / "ziti.db")
    try:
        plugin = _plugin(tmp_path, db, tmp_path / "lib")
        font = plugin._tmp_dir / "missing_a.ttf"
        font.write_bytes(b"font")
        item = {
            "path": str(font),
            "file_name": font.name,
            "name": "MyFont.ttf",
            "family": "MyFont",
            "vendor": "未知厂商",
            "file_size": 4,
            "matched": "Target",
            "match_kind": "manual",
            "matched_keys": ["target"],
            "covered_chars": "ab",
            "required_chars": "ab",
            "sha256": "x",
            "created_at": time.time(),
        }
        db.add_missing_upload(item)
        db.set_manual_font_mapping("MyFont.ttf", "Target", file_sha256="x", note="test")

        # 新进程/重载后从库恢复
        restored = _plugin(tmp_path, db, tmp_path / "lib")
        restored._missing_uploads = {}
        assert restored._load_missing_uploads() == 1
        assert str(font) in restored._missing_uploads

        # 指向已不存在文件的记录：加载时清掉幽灵条目
        db.add_missing_upload(dict(item, path=str(plugin._tmp_dir / "gone.ttf")))
        restored._missing_uploads = {}
        assert restored._load_missing_uploads() == 1
        assert {row["path"] for row in db.list_missing_uploads()} == {str(font)}

        # TTL 过期：文件、库记录、人工映射审计一并清理
        restored._missing_uploads[str(font)]["created_at"] = time.time() - 100
        db.add_missing_upload(dict(item, created_at=time.time() - 100))
        restored._missing_uploads_ttl = 10
        assert restored._prune_missing_uploads() == 1
        assert not font.exists()
        assert db.list_missing_uploads() == []
        assert db.list_manual_font_mappings() == []
    finally:
        db.close()


# ─── P1-11 上传数量/大小上限 ─────────────────────────────────────────────


def test_receive_uploads_limits_files_and_cleans_partials(tmp_path, monkeypatch):
    plugin = plugin_mod.Zitifenlei()
    plugin._tmp_dir = tmp_path / "tmp"
    plugin._tmp_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(plugin_mod, "MAX_UPLOAD_FILES", 2)
    files, notes = asyncio.run(
        plugin._receive_uploads(
            [_Upload(f"f{i}.ttf", b"1234") for i in range(3)],
            (".ttf",),
            prefix="up",
        )
    )
    assert len(files) == 2
    assert any("一次最多上传 2 个文件" in n for n in notes)

    # 单文件超限：拒收且不留下半成品
    for leftover in plugin._tmp_dir.iterdir():
        leftover.unlink()
    monkeypatch.setattr(plugin_mod, "MAX_ASS_FILE_BYTES", 8)
    files, notes = asyncio.run(
        plugin._receive_uploads([_Upload("big.ass", b"x" * 64)], (".ass",), prefix="up")
    )
    assert files == []
    assert any("超过单文件上限" in n for n in notes)
    assert list(plugin._tmp_dir.iterdir()) == []

    # 总量超限：后续文件拒收，已接收的保留，被拒的半成品清理
    for leftover in plugin._tmp_dir.iterdir():
        leftover.unlink()
    monkeypatch.setattr(plugin_mod, "MAX_UPLOAD_TOTAL_BYTES", 10)
    files, notes = asyncio.run(
        plugin._receive_uploads(
            [_Upload("a.ttf", b"12345678"), _Upload("b.ttf", b"12345678")], (".ttf",), prefix="up"
        )
    )
    assert [item["file_name"] for item in files] == ["a.ttf"]
    assert any("总量上限" in n for n in notes)
    assert len(list(plugin._tmp_dir.iterdir())) == 1


def test_split_ttc_malformed_numfonts_returns_fast(tmp_path):
    plugin = plugin_mod.Zitifenlei()
    # 畸形 TTC：numFonts = 42 亿且 offset 表缺失
    raw = b"ttcf" + b"\x00\x01\x00\x00" + struct.pack(">I", 0xFFFFFFFF) + b"\x00" * 4
    path = tmp_path / "bad.ttc"
    path.write_bytes(raw)
    started = time.time()
    out = plugin._split_ttc_face(raw, str(path))
    assert time.time() - started < 10
    assert out == raw


# ─── P1-6 依赖安装异步化 ─────────────────────────────────────────────────


def test_deps_install_uses_async_subprocess(tmp_path, monkeypatch):
    db = FontDB(tmp_path / "ziti.db")
    try:
        plugin = _plugin(tmp_path, db, tmp_path / "lib")
        called = {}

        class _Proc:
            returncode = 0

            async def communicate(self):
                return b"Successfully installed uharfbuzz", None

        async def _fake_exec(*args, **kwargs):
            called["args"] = args
            return _Proc()

        class _Req:
            def __init__(self) -> None:
                self.query_params = {"package": "uharfbuzz"}

        monkeypatch.setattr(plugin_mod.asyncio, "create_subprocess_exec", _fake_exec)
        result = asyncio.run(plugin.api_deps_install(_Req()))
        assert result["success"] is True, result
        assert "-m" in called["args"] and "pip" in called["args"]
        logs = db.get_logs(limit=5)
        if logs:
            assert any("依赖重装 uharfbuzz" in row["message"] for row in logs)
    finally:
        db.close()
