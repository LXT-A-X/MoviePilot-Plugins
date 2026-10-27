import os
from pathlib import Path

import pytest

from ziti_under_test import font_metadata as fm
from ziti_under_test import glyph_checker as gc
from ziti_under_test import harfbuzz_engine as he

FIXTURE = Path(__file__).parent / "fixtures" / "complex.ass"
FONT_DIR = Path(r"C:\Windows\Fonts")
ARIAL = FONT_DIR / "arial.ttf"
MSYH = FONT_DIR / "msyh.ttc"


def _hb_ready():
    ok, _ = he.hb_available()
    return ok


pytestmark = pytest.mark.skipif(not _hb_ready(), reason="需要 uharfbuzz")


def test_encode_decode_font_data_roundtrip():
    for size in (1, 2, 3, 4, 5, 44, 45, 46, 90, 1024):
        data = bytes((i * 37 + 11) & 0xFF for i in range(size))
        encoded = he.encode_font_data(data)
        decoded = he.decode_font_data("".join(encoded))
        assert decoded == data, f"size={size}"


def _bracketed_data_line() -> str:
    """构造一行形如 "[...]" 的合法字体编码数据（60 个编码字符 = 45 字节）。"""
    groups = [58] + [0] * 58 + [60]  # 首字符 '['（33+58），末字符 ']'（33+60）
    line = "".join(chr(value + 33) for value in groups)
    assert line.startswith("[") and line.endswith("]")
    return line


def test_fonts_data_line_looking_like_section_is_kept():
    """字体内嵌数据行恰好 "[...]" 时不得当成段标题：后续字体与段落都要保留。"""
    fake = _bracketed_data_line()
    text = (
        "[Script Info]\nTitle: x\n\n"
        "[V4+ Styles]\n"
        "Style: Default,Arial,52,&H00FFFFFF,&H000000FF,&H00202020,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,40,40,60,1\n\n"
        "[Fonts]\n"
        "fontname: Foo\n" + fake + "\n"
        "fontname: Bar\n" + "A" * 60 + "\n"
        "\n"
        "[Events]\n"
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,你好\n"
    )

    embedded = he.extract_embedded_fonts(text.encode("utf-8"))
    assert [name for name, _ in embedded] == ["Foo", "Bar"]
    assert len(embedded[0][1]) == 45

    stripped = he.strip_fonts_section(text)
    assert "[Fonts]" not in stripped
    assert "fontname:" not in stripped
    assert "[Events]" in stripped and "你好" in stripped

    # 字形检测同样不能被这行带偏，Events 段仍需正常解析
    usage, warnings = gc.parse_ass_usage(text.encode("utf-8"))
    assert not warnings, warnings
    assert ord("你") in usage["Arial"].codepoints


@pytest.mark.skipif(not ARIAL.exists(), reason="需要 Windows 系统字体")
def test_subset_font_bytes_covers_requested_chars():
    data = he.subset_font_bytes(ARIAL, {ord("A"), ord("B"), ord("C")}, rename_to="测试字体ABC")
    assert data
    from fontTools.ttLib import TTFont
    from io import BytesIO

    font = TTFont(BytesIO(data))
    try:
        cmap = font.getBestCmap()
        assert {ord("A"), ord("B"), ord("C")} <= set(cmap)
        assert font["name"].getDebugName(1) == "测试字体ABC"
    finally:
        font.close()


@pytest.mark.skipif(not ARIAL.exists(), reason="需要 Windows 系统字体")
def test_subset_ass_embeds_and_validates(tmp_path):
    if not MSYH.exists():
        pytest.skip("需要微软雅黑 TTC 字体")
    usage, _ = gc.parse_ass_usage(FIXTURE.read_bytes())
    faces = {}
    for path in (ARIAL, MSYH):
        inspection = fm.inspect_font(path)
        for face in inspection.faces:
            if face.status != "ok":
                continue
            for name in {face.family, face.full_name, *face.aliases}:
                faces.setdefault(name, []).append(
                    he.FaceRef(
                        file_path=face.file_path,
                        face_index=face.face_index,
                        codepoints=face.codepoints,
                        names=list(face.aliases),
                    )
                )

    def resolve(name):
        return faces.get(name, [])

    source = tmp_path / "complex.ass"
    source.write_bytes(FIXTURE.read_bytes())
    out = tmp_path / "complex.ziti.ass"
    result = he.subset_ass_file(source, out, {k: v.codepoints for k, v in usage.items()}, resolve)
    assert result.success, result.errors
    assert out.is_file()
    assert source.read_bytes() == FIXTURE.read_bytes()  # 原字幕不变
    assert "NoSuchFont" in result.missing_fonts

    embedded = he.extract_embedded_fonts(out.read_bytes())
    names = {name for name, _ in embedded}
    assert {"Arial", "Microsoft YaHei", "微软雅黑"} <= names
    assert "NoSuchFont" not in names

    # 内嵌字体能解析，且确实包含所需字符
    from fontTools.ttLib import TTFont
    from io import BytesIO

    by_name = dict(embedded)
    font = TTFont(BytesIO(by_name["微软雅黑"]))
    try:
        cmap = font.getBestCmap()
        assert {ord(c) for c in "中文测试"} <= set(cmap)
        assert font["name"].getDebugName(1) == "微软雅黑"
    finally:
        font.close()


@pytest.mark.skipif(not ARIAL.exists(), reason="需要 Windows 系统字体")
def test_existing_fonts_section_is_replaced(tmp_path):
    source = tmp_path / "with_fonts.ass"
    text = FIXTURE.read_text(encoding="utf-8")
    source.write_text(text, encoding="utf-8")
    out = tmp_path / "out.ass"

    def resolve(_name):
        return [he.FaceRef(file_path=str(ARIAL), face_index=0, codepoints=fm.inspect_font(ARIAL).faces[0].codepoints)]

    result = he.subset_ass_file(source, out, {"Arial": {ord("A"), ord("B")}}, resolve)
    assert result.success, result.errors
    encoded = out.read_text(encoding="utf-8")
    assert encoded.count("[Fonts]") == 1
    assert encoded.count("fontname: Arial") == 1
