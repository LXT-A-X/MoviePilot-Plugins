"""检查页分组抽屉相关：ass_files.batch 落库/读取、上传批次归属、批量检查接口。

不依赖 MoviePilot 宿主；上传走假 Request/form，检查逻辑用假实现替换。
"""

import asyncio
import importlib
from pathlib import Path

from ziti_under_test.db import FontDB


class _FakeForm:
    def __init__(self, files, batch=""):
        self._files = list(files)
        self._batch = batch

    def getlist(self, key):
        return list(self._files) if key == "file" else []

    def get(self, key):
        return self._batch if key == "batch" else None


class _FakeUploadRequest:
    def __init__(self, form):
        self._form = form

    async def form(self):
        return self._form


class _FakeJsonRequest:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


class _FakeUploadFile:
    def __init__(self, filename):
        self.filename = filename


def _plugin(tmp_path: Path):
    plugin_mod = importlib.import_module("ziti_under_test.__init__")
    plugin = plugin_mod.Zitifenlei()
    plugin._db = FontDB(tmp_path / "ziti.db")
    plugin._enabled = True
    plugin._tmp_dir = tmp_path / "tmp"
    plugin._tmp_dir.mkdir(parents=True, exist_ok=True)
    plugin._config.update({"lib_dir": str(tmp_path / "lib")})
    return plugin


# ─── DB：batch 字段往返 ──────────────────────────────────────────────────


def test_ass_batch_roundtrip(tmp_path):
    db = FontDB(tmp_path / "ziti.db")
    db.add_ass("a.ass", "manual", "pending", [], [], file_path="/tmp/a.ass", batch="Pack.zip")
    db.add_ass("b.ass", "manual", "pending", [], [], file_path="/tmp/b.ass")

    rows = db.query_ass(limit=10)["list"]
    by_name = {r["file_name"]: r for r in rows}
    assert by_name["a.ass"]["batch"] == "Pack.zip"
    assert by_name["b.ass"]["batch"] == ""
    # 分组需要 file_path（监控/入库记录按目录归组）
    assert by_name["a.ass"]["file_path"] == "/tmp/a.ass"


# ─── 上传：压缩包用包名，散文件用本次上传批次 ────────────────────────────


def test_ass_upload_assigns_batch(tmp_path):
    plugin = _plugin(tmp_path)
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    a = src_dir / "a.ass"
    b = src_dir / "b.ass"
    a.write_text("[Script Info]", encoding="utf-8")
    b.write_text("[Script Info]", encoding="utf-8")

    async def _fake_receive(_uploads, _exts, prefix="ass"):
        return (
            [
                {"file_name": "a.ass", "path": str(a), "size": 13, "from_archive": "Pack.zip"},
                {"file_name": "b.ass", "path": str(b), "size": 13, "from_archive": ""},
            ],
            [],
        )

    plugin._receive_uploads = _fake_receive
    form = _FakeForm([_FakeUploadFile("Pack.zip"), _FakeUploadFile("b.ass")], batch="手动上传 10-27 12:30")
    res = asyncio.run(plugin.api_ass_upload(_FakeUploadRequest(form)))

    assert res["success"] is True
    assert res["data"]["count"] == 2
    rows = plugin._db.query_ass(limit=10)["list"]
    by_name = {r["file_name"]: r for r in rows}
    assert by_name["a.ass"]["batch"] == "Pack.zip"
    assert by_name["b.ass"]["batch"] == "手动上传 10-27 12:30"


# ─── 批量检查：统计成功/缺字体/失败 ──────────────────────────────────────


def test_ass_check_batch_stats(tmp_path):
    plugin = _plugin(tmp_path)

    async def _fake_check(ass_id, families=None):
        if ass_id == 2:
            raise RuntimeError("boom")
        return {"id": ass_id, "missing_count": 1 if ass_id == 1 else 0}

    plugin._check_ass_by_id = _fake_check
    res = asyncio.run(plugin.api_ass_check_batch(_FakeJsonRequest({"ids": [1, 2, 3]})))

    assert res["success"] is True
    assert res["data"] == {"total": 3, "ok": 2, "missing": 1, "failed": 1}
    assert "2/3" in res["message"]


def test_ass_check_batch_rejects_empty(tmp_path):
    plugin = _plugin(tmp_path)
    res = asyncio.run(plugin.api_ass_check_batch(_FakeJsonRequest({"ids": [0, "x"]})))
    assert res["success"] is False
