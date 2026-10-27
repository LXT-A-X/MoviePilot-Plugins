import zipfile
from pathlib import Path

import pytest

from ziti_under_test import archive_utils as au

FONT_DIR = Path(r"C:\Windows\Fonts")
ARIAL = FONT_DIR / "arial.ttf"
ASS_FIXTURE = Path(__file__).parent / "fixtures" / "complex.ass"


def _make_zip(path: Path):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("fonts/sub/ok.ttf", ARIAL.read_bytes() if ARIAL.exists() else b"font-bytes")
        zf.writestr("subs/demo.ass", ASS_FIXTURE.read_bytes())
        zf.writestr("readme.txt", b"ignore me")
        zf.writestr("nested.zip", b"PK\x03\x04fake")
        zf.writestr("__MACOSX/._junk.ttf", b"junk")
        zf.writestr("中文字体/测试.ass", ASS_FIXTURE.read_bytes())
        # 手工构造越界成员（zipfile 允许写入该名字）
        zf.writestr("../evil.ttf", b"evil")


def test_extract_zip_filters_and_blocks_traversal(tmp_path):
    archive = tmp_path / "bundle.zip"
    _make_zip(archive)
    dest = tmp_path / "out"
    result = au.extract_zip(archive, dest, (".ttf", ".ass"))

    names = {item.member for item in result.files}
    assert "fonts/sub/ok.ttf" in names
    assert "subs/demo.ass" in names
    assert "中文字体/测试.ass" in names
    assert len(result.files) == 3
    assert all(Path(item.path).is_file() for item in result.files)
    assert all(dest.resolve() in Path(item.path).resolve().parents for item in result.files)
    assert result.total_bytes > 0

    skipped_names = {name for name, _ in result.skipped}
    assert "readme.txt" in skipped_names
    assert "nested.zip" in skipped_names
    assert "__MACOSX/._junk.ttf" in skipped_names
    error_names = {name for name, _ in result.errors}
    assert "../evil.ttf" in error_names
    assert not (tmp_path / "evil.ttf").exists()


def test_extract_invalid_zip_reports_error(tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    result = au.extract_zip(bad, tmp_path / "out", (".ttf",))
    assert result.files == []
    assert result.errors


def test_extract_member_limit(tmp_path):
    archive = tmp_path / "many.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for i in range(5):
            zf.writestr(f"f{i}.ttf", b"x")
    result = au.extract_zip(archive, tmp_path / "out", (".ttf",), max_members=2)
    assert result.files == []
    assert any("成员过多" in reason for _, reason in result.errors)


def test_extract_single_member_size_limit(tmp_path):
    archive = tmp_path / "big.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("big.ttf", b"x" * 2048)
    result = au.extract_zip(archive, tmp_path / "out", (".ttf",), max_member_bytes=1024)
    assert result.files == []
    assert any("超过上限" in reason for _, reason in result.skipped)


def test_is_archive():
    assert au.is_archive("a.ZIP")
    assert not au.is_archive("a.rar")
    assert not au.is_archive("a.7z")
