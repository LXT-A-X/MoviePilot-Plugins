"""HDR 亮度回归：ASS 颜色是 &HAABBGGRR，R/G 通道不能互换，行内 \1c 也要生效。"""

from pathlib import Path

from ziti_under_test import hdr_utils as hu


def test_scale_colour_keeps_channel_order():
    assert hu._scale_colour_token("&H000000FF", 50) == "&H0000007F"  # 纯红只压 R
    assert hu._scale_colour_token("&H0000FF00", 50) == "&H00007F00"  # 纯绿只压 G
    assert hu._scale_colour_token("&H00FF0000", 50) == "&H007F0000"  # 纯蓝只压 B
    assert hu._scale_colour_token("&H00FFFFFF", 50) == "&H007F7F7F"
    assert hu._scale_colour_token("&H800000FF", 50) == "&H8000007F"  # alpha 保留
    assert hu._scale_colour_token("not-a-colour", 50) == "not-a-colour"


def test_apply_hdr_scales_style_and_inline_colours(tmp_path):
    ass = tmp_path / "hdr.ass"
    ass.write_text(
        "[Script Info]\nScriptType: v4.00+\n\n"
        "[V4+ Styles]\n"
        "Style: Default,Arial,52,&H00FFFFFF,&H000000FF,&H000000FF,"
        "&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,30,30,30,1\n\n"
        "[Events]\n"
        "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,{\\1c&H000000FF&}红\n",
        encoding="utf-8",
    )
    assert hu.apply_hdr_brightness(ass, "50")
    text = ass.read_text(encoding="utf-8")
    # Primary 白 → 灰；Outline 红 → 暗红（R 通道，不是绿色）
    assert "&H007F7F7F" in text
    assert "&H0000007F" in text
    assert "&H00007F00" not in text
    # 行内 \1c 同样被压暗且保留标签结构
    assert "{\\1c&H0000007F&}红" in text
