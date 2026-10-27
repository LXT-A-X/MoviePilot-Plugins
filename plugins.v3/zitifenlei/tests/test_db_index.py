import shutil
from pathlib import Path

import pytest

from ziti_under_test import font_metadata as fm
from ziti_under_test.db import FontDB

FONT_DIR = Path(r"C:\Windows\Fonts")
ARIAL = FONT_DIR / "arial.ttf"
ARIAL_BOLD = FONT_DIR / "arialbd.ttf"
MSYH = FONT_DIR / "msyh.ttc"

pytestmark = pytest.mark.skipif(not ARIAL.exists(), reason="需要 Windows 系统字体")


def _db(tmp_path):
    return FontDB(tmp_path / "test.db")


def test_upsert_lookup_and_counts(tmp_path):
    db = _db(tmp_path)
    try:
        inspection = fm.inspect_font(ARIAL)
        result = db.upsert_font_file(inspection)
        assert result["changed"] is True
        assert result["index_version"] == 1

        stats = db.index_stats()
        assert stats["files"] == 1
        assert stats["faces"] == 1
        assert stats["chars"] > 1000

        faces = db.lookup_faces("arial")
        assert len(faces) == 1
        assert ord("A") in faces[0]["codepoints"]
        assert faces[0]["file_path"] == str(ARIAL.resolve())

        # 内容未变 → 不重复贡献、不涨版本
        again = db.upsert_font_file(inspection)
        assert again["changed"] is False
        assert again["index_version"] == 1
    finally:
        db.close()


def test_move_same_content_keeps_single_record(tmp_path):
    db = _db(tmp_path)
    try:
        source = tmp_path / "lib" / "arial.ttf"
        source.parent.mkdir()
        shutil.copy2(ARIAL, source)
        first = db.upsert_font_file(fm.inspect_font(source))
        assert first["changed"] is True

        moved = tmp_path / "lib2" / "arial-renamed.ttf"
        moved.parent.mkdir()
        shutil.move(str(source), str(moved))
        second = db.upsert_font_file(fm.inspect_font(moved))
        assert second["changed"] is False  # 同 SHA → 迁移路径，不算新字体
        assert db.index_stats()["files"] == 1
        assert db.lookup_faces("Arial")[0]["file_path"] == str(moved.resolve())
    finally:
        db.close()


def test_modified_font_replaces_old_contributions(tmp_path):
    if not ARIAL_BOLD.exists():
        pytest.skip("需要 arialbd.ttf")
    db = _db(tmp_path)
    try:
        target = tmp_path / "f.ttf"
        shutil.copy2(ARIAL, target)
        db.upsert_font_file(fm.inspect_font(target))
        assert db.lookup_faces("Arial")

        shutil.copy2(ARIAL_BOLD, target)  # 换内容（家族 Arial / 子家族 Bold）
        changed = db.upsert_font_file(fm.inspect_font(target))
        assert changed["changed"] is True
        assert db.index_stats()["files"] == 1
        # 旧 face 贡献已撤销：同路径只有一条 face，旧别名（Arial Regular）不残留
        faces = db.lookup_faces("Arial")
        assert len(faces) == 1
        assert "Bold" in faces[0]["full_name"]
        assert db.lookup_faces("Arial Regular") == []
        assert db.lookup_faces("Arial Bold")
    finally:
        db.close()


def test_ttc_faces_indexed_separately(tmp_path):
    if not MSYH.exists():
        pytest.skip("需要微软雅黑 TTC")
    db = _db(tmp_path)
    try:
        db.upsert_font_file(fm.inspect_font(MSYH))
        stats = db.index_stats()
        assert stats["files"] == 1
        assert stats["faces"] >= 2
        # 中文别名可命中
        faces = db.lookup_faces("微软雅黑")
        assert faces
        assert any(f["face_index"] == 0 for f in faces)
    finally:
        db.close()


def test_remove_font_file(tmp_path):
    db = _db(tmp_path)
    try:
        db.upsert_font_file(fm.inspect_font(ARIAL))
        removed = db.remove_font_file(str(ARIAL.resolve()))
        assert removed["removed"] is True
        assert db.index_stats()["files"] == 0
        assert db.lookup_faces("Arial") == []
    finally:
        db.close()


def test_missing_glyph_snapshots_and_manual_mapping(tmp_path):
    db = _db(tmp_path)
    try:
        # 真实流程一定先有 ass_files 记录（缺失聚合按 JOIN ass_files 统计，删字幕即不再计入）
        db.add_ass("a.ass", "manual", "missing", ["NoSuchFont"], ["NoSuchFont", "Arial"], "/tmp/a.ass")
        ass_id = int(db.query_one("SELECT id FROM ass_files ORDER BY id DESC LIMIT 1")["id"])
        db.replace_missing_glyphs(
            ass_id,
            "/tmp/a.ass",
            [
                {"name": "NoSuchFont", "used_count": 5, "missing_count": 5, "missing_codepoints": [1, 2], "missing_chars": "ab", "status": "missing"},
                {"name": "Arial", "used_count": 3, "missing_count": 0, "status": "ok"},
            ],
        )
        latest = db.latest_missing_glyphs(ass_id)
        assert {row["font_name"] for row in latest} == {"NoSuchFont", "Arial"}
        assert db.all_missing_font_names() == ["NoSuchFont"]
        # 删字幕记录必须级联清快照（否则已删字幕的字体永久留在缺失列表）
        db.delete_ass(ass_id)
        assert db.latest_missing_glyphs(ass_id) == []
        assert db.all_missing_font_names() == []

        db.set_manual_font_mapping("MyFont.ttf", "NoSuchFont", file_sha256="abc", note="test")
        mapping = db.get_manual_font_mapping("MyFont.ttf")
        assert mapping["target_name"] == "NoSuchFont"
        assert len(db.list_manual_font_mappings()) == 1
        db.delete_manual_font_mapping(mapping["id"])
        assert db.list_manual_font_mappings() == []
    finally:
        db.close()
