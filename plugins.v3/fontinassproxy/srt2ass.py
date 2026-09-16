# -*- coding: utf-8 -*-
"""字幕字体代理 — SRT → ASS 模板转换。

行为对齐 fontInAss（utils.srt_to_ass）：
- 时间行（``hh:mm:ss,mmm --> hh:mm:ss,mmm``）转成 ASS 的 h:mm:ss.cc。
- 文本内换行转 ``\\N``；``<i>`` ``<b>`` ``<u>`` 转 override 开关；
  ``<font color="#RRGGBB">`` 转 ``{\\c&HBBGGRR&}``（ASS 为 BGR 反序）。
- 样式（字体/字号/颜色）由插件配置注入，避免依赖 Emby 转出来的 ASS 样式。
"""

from __future__ import annotations

import re
from typing import List

_TIME_DETECT = re.compile(r"-?\d\d:\d\d:\d\d")
_TIME_CAPTURE = re.compile(r"\d(\d:\d{2}:\d{2}),(\d{2})\d")
_TIME_ARROW = re.compile(r"\s+-->\s+")
_HTML_START = re.compile(r"<([ubi])>")
_HTML_END = re.compile(r"</([ubi])>")
_FONT_COLOR_START = re.compile(r'<font\s+color="?#(\w{2})(\w{2})(\w{2})"?>')
_FONT_COLOR_END = re.compile(r"</font>")


def _style_block(font_name: str, font_size: int, primary_colour: str) -> str:
    """生成 [V4+ Styles] 段。primary_colour 形如 &H00FFFFFF（BGR）。"""
    if not primary_colour.startswith("&H"):
        primary_colour = f"&H00{primary_colour.lstrip('#') or 'FFFFFF'}" if primary_colour else "&H00FFFFFF"
    return (
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},{font_size},{primary_colour},"
        "&H00FFFFFF,&H00000000,&H02000000,0,0,0,0,100,100,0,0,1,2,0,2,"
        "10,10,10,1\n"
    )


def srt_to_ass(srt_text: str, font_name: str = "思源黑体 CN",
               font_size: int = 20, primary_colour: str = "&H00FFFFFF") -> str:
    """SRT 文本 -> ASS 文本（含 V4+ Styles 头）。"""
    srt_text = srt_text.replace("\r", "")
    lines = [x.strip() for x in srt_text.split("\n") if x.strip()]

    sub_lines = ""
    tmp_lines = ""
    line_count = 0
    ln = 0
    while ln < len(lines):
        line = lines[ln]
        if line.isdigit() and ln + 1 < len(lines) and _TIME_DETECT.match(lines[ln + 1]):
            # 新字幕块开始
            if tmp_lines:
                sub_lines += tmp_lines.replace("\n", "\\n") + "\n"
            tmp_lines = ""
            line_count = 0
        else:
            if _TIME_DETECT.match(line):
                line = line.replace("-0", "0")
                tmp_lines += "Dialogue: 0," + line + ",Default,,0,0,0,,"
            else:
                tmp_lines += line if line_count < 2 else "\n" + line
            line_count += 1
        ln += 1

    sub_lines += tmp_lines.replace("\n", "\\n") + "\n"

    sub_lines = _TIME_CAPTURE.sub(r"\1.\2", sub_lines)
    sub_lines = _TIME_ARROW.sub(",", sub_lines)
    sub_lines = _HTML_START.sub(lambda m: f"{{\\{m.group(1).lower()}1}}", sub_lines)
    sub_lines = _HTML_END.sub(lambda m: f"{{\\{m.group(1).lower()}0}}", sub_lines)
    sub_lines = _FONT_COLOR_START.sub(r"{\\c&H\3\2\1&}", sub_lines)
    sub_lines = _FONT_COLOR_END.sub("", sub_lines)

    head = (
        "[Script Info]\n"
        "; This is an Advanced Sub Station Alpha v4+ script.\n"
        "Title:\n"
        "ScriptType: v4.00+\n"
        "Collisions: Normal\n"
        "PlayDepth: 0\n"
        "\n"
    )
    return head + _style_block(font_name, font_size, primary_colour) + "\n[Events]\n" \
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n\n" \
        + sub_lines


def is_srt(text: str) -> bool:
    """粗略判断文本是否为 SRT（不包含 ASS 段标记）。"""
    if "[Events]" in text or "[V4+ Styles]" in text:
        return False
    if _TIME_DETECT.search(text) and "-->" in text:
        return True
    return False