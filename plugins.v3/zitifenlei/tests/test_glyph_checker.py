from pathlib import Path

import pytest

from ziti_under_test import font_metadata as fm
from ziti_under_test import glyph_checker as gc

FIXTURE = Path(__file__).parent / "fixtures" / "complex.ass"
FONT_DIR = Path(r"C:\Windows\Fonts")


def _load_usage():
    data = FIXTURE.read_bytes()
    usage, warnings = gc.parse_ass_usage(data)
    return usage, warnings


def _charset(text: str) -> set:
    return {ord(ch) for ch in text}


def test_parse_ass_usage_fonts_and_control_codes():
    usage, _warnings = _load_usage()
    assert set(usage) == {"Arial", "Microsoft YaHei", "微软雅黑", "NoSuchFont"}

    msyh = usage["Microsoft YaHei"].codepoints
    # \h → 空格；\N/\n 换行不计入；绘图模式里的矢量指令不计入
    assert 0x20 in msyh
    assert ord("m") not in msyh
    assert ord("0") not in msyh
    # 注释行不参与统计
    assert ord("注") not in msyh

    arial = usage["Arial"].codepoints
    # {\t(0,500,\fnArial)} 嵌套标签仍能识别为 Arial
    assert _charset("动画里切字体") <= arial
    assert _charset("Hello, world! 123") <= arial
    assert _charset("卡拉OK") <= arial

    assert _charset("中文测试") <= usage["微软雅黑"].codepoints
    assert _charset("缺字体内容") <= usage["NoSuchFont"].codepoints


def test_utf16_subtitle_is_decoded(tmp_path):
    text = FIXTURE.read_text(encoding="utf-8")
    utf16 = tmp_path / "utf16.ass"
    utf16.write_bytes(b"\xff\xfe" + text.encode("utf-16-le"))
    usage, _ = gc.parse_ass_usage(utf16.read_bytes())
    assert "Arial" in usage
    assert "微软雅黑" in usage


def _coverage_lookup():
    """用系统字体构建真实覆盖，别名按归一化键匹配。"""
    if not (FONT_DIR / "arial.ttf").exists():
        pytest.skip("需要 Windows 系统字体目录")
    faces = []
    for path in (FONT_DIR / "arial.ttf", FONT_DIR / "msyh.ttc"):
        if not path.exists():
            continue
        inspection = fm.inspect_font(path)
        for face in inspection.faces:
            if face.status != "ok":
                continue
            faces.append(
                gc.FaceCoverage(
                    face_id=len(faces) + 1,
                    file_path=face.file_path,
                    face_index=face.face_index,
                    names=[face.family, face.full_name, *face.aliases],
                    codepoints=face.codepoints,
                )
            )

    alias_index = {}
    for face in faces:
        for name in face.names:
            key = fm.normalize_font_key(name)
            if key:
                alias_index.setdefault(key, []).append(face)

    def lookup(name: str):
        return alias_index.get(fm.normalize_font_key(name), [])

    return lookup


def test_v4pp_styles_are_parsed():
    """V4++ 样式段必须识别，否则整段 Style 被跳过、检查结论假“完整”。"""
    raw = (
        "[Script Info]\nScriptType: v4.00++\n\n"
        "[V4++ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
        "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,V4PPFont,52,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,2,1,2,30,30,30,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,测试\n"
    ).encode("utf-8")
    usage, _ = gc.parse_ass_usage(raw)
    assert "V4PPFont" in usage
    assert _charset("测试") <= usage["V4PPFont"].codepoints


def test_undefined_style_chars_go_to_unknown_bucket():
    """对白引用未定义样式时字符不能丢，归入 __unknown__ 暴露为缺失。"""
    raw = (
        "[Script Info]\nScriptType: v4.00+\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
        "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,52,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,2,1,2,30,30,30,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:02.00,NoSuchStyle,,0,0,0,,未知样式\n"
    ).encode("utf-8")
    usage, warnings = gc.parse_ass_usage(raw)
    assert usage["__unknown__"].codepoints == _charset("未知样式")
    assert any("未定义的样式" in w for w in warnings)


def test_gbk_ass_decodes_without_replacement():
    """GBK 老字幕不能按 UTF-8 解成 U+FFFD，否则字体名/字符全部误报缺失。"""
    from ziti_under_test import font_utils as fu

    text = (
        "[Script Info]\nScriptType: v4.00+\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
        "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,微软雅黑,52,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,2,1,2,30,30,30,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,中文字幕\n"
    )
    raw = text.encode("gb18030")
    decoded = fu._decode_ass_text(raw)
    assert "\ufffd" not in decoded
    assert "微软雅黑" in decoded
    usage, _ = gc.parse_ass_usage(raw)
    assert "微软雅黑" in usage
    assert _charset("中文字幕") <= usage["微软雅黑"].codepoints


def test_evaluate_usage_partial_and_alias_resolution():
    usage, _ = _load_usage()
    result = gc.evaluate_usage(usage.values(), _coverage_lookup())
    by_name = {item.name: item for item in result.fonts}

    # 别名：ASS 里写「微软雅黑」也能解析到 Microsoft YaHei 的 face
    assert by_name["微软雅黑"].status == "ok"
    assert by_name["Microsoft YaHei"].status == "ok"
    # 名称存在但 Arial 不覆盖中文 → 部分缺失，而不是「字体齐全」
    arial = by_name["Arial"]
    assert arial.status == "partial"
    assert arial.missing_count > 0
    assert "卡" in arial.missing_chars or "动" in arial.missing_chars
    # 完全不存在的字体 → missing
    missing = by_name["NoSuchFont"]
    assert missing.status == "missing"
    assert missing.missing_count == missing.used_count > 0
    assert "NoSuchFont" in result.missing_names
    assert result.total_missing_chars == sum(item.missing_count for item in result.fonts)
