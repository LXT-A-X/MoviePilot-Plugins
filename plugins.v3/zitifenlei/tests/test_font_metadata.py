from pathlib import Path

import pytest

from ziti_under_test import font_metadata as fm
from ziti_under_test import font_utils as fu

FONT_DIR = Path(r"C:\Windows\Fonts")
ARIAL = FONT_DIR / "arial.ttf"
MSYH = FONT_DIR / "msyh.ttc"

pytestmark = pytest.mark.skipif(not ARIAL.exists(), reason="需要 Windows 系统字体目录")


def test_inspect_ttf_metadata_and_cmap():
    result = fm.inspect_font(ARIAL)
    assert result.status == "ok"
    assert result.face_count == 1
    assert result.valid_face_count == 1
    assert len(result.sha256) == 64
    face = result.faces[0]
    assert face.family == "Arial"
    assert face.char_count > 1000
    assert ord("A") in face.codepoints
    assert face.status == "ok"
    assert face.vendor != ""


@pytest.mark.skipif(not MSYH.exists(), reason="需要微软雅黑 TTC 字体")
def test_inspect_ttc_all_faces_and_localized_alias():
    result = fm.inspect_font(MSYH)
    assert result.status == "ok"
    assert result.face_count >= 2
    assert result.valid_face_count == result.face_count
    assert len({face.face_index for face in result.faces}) == result.face_count
    all_aliases = {alias for face in result.faces for alias in face.aliases}
    assert "微软雅黑" in all_aliases
    assert all(face.char_count > 10000 for face in result.faces)


def test_codepoint_codec_roundtrip():
    codepoints = {0x20, 0x41, 0x4E2D, 0x6587, 0x1F600, 0x10FFFF}
    blob = fm.encode_codepoints(codepoints)
    assert isinstance(blob, bytes) and blob
    assert fm.decode_codepoints(blob) == codepoints
    assert fm.decode_codepoints(b"") == set()


def test_invalid_font_is_reported_not_swallowed(tmp_path):
    broken = tmp_path / "broken.ttf"
    broken.write_bytes(b"this is not a font")
    result = fm.inspect_font(broken)
    assert result.status == "invalid"
    assert result.error
    assert result.valid_face_count == 0


def test_empty_file_is_invalid(tmp_path):
    empty = tmp_path / "empty.otf"
    empty.write_bytes(b"")
    result = fm.inspect_font(empty)
    assert result.status == "invalid"
    assert result.error


def test_fingerprint_changes_with_content(tmp_path):
    first = tmp_path / "a.ttf"
    first.write_bytes(b"x" * 100)
    fp1 = fm.compute_fingerprint(first)
    first.write_bytes(b"y" * 100)
    fp2 = fm.compute_fingerprint(first)
    assert fp1["sha256"] != fp2["sha256"]
    assert fp1["size"] == fp2["size"] == 100


def test_safe_filename_component_blocks_traversal():
    """字体内部名不可信：清洗后不得含路径分隔符、不得以点开头、不得为空。"""
    for raw in ("../../escape", "a/b", r"C:\Windows\Temp\x", "..", ".hidden", "", "x" * 300):
        name = fu.safe_filename_component(raw)
        assert name
        assert not any(ch in name for ch in '\\/:*?"<>|')
        assert not name.startswith(".")
        assert len(name) <= 120
    assert fu.safe_filename_component("../../escape").endswith("escape")
    assert fu.safe_filename_component("..", "font") == "font"
    assert fu.safe_filename_component("微软雅黑", "font") == "微软雅黑"
