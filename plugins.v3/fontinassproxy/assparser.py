# -*- coding: utf-8 -*-
"""字幕字体代理 — ASS 解析层。

输入原始 ASS 文本，输出 ``{（字体名, 字重, 斜体）: 字符集}`` 映射，用于子集化。

行为对齐 fontInAss 的 C++ 分析器（src/py2cy/cpp_utils*.cpp）：
- ``[V4+ Styles]`` / ``[V4 Styles]``：按 ``Format:`` 行定位列，**不硬编码列号**；
  收集 style 名 -> (Fontname, Bold->700/400, Italic)。第一个 style 作为默认样式。
- ``[Events]`` 的 ``Dialogue:``：按 ``Format:`` 定位 Style / Text 列。
- 文本清洗：剥离 ``{...}`` override 块；``\\N`` ``\\n`` ``\\h`` 及转义的
  ``\\{`` ``\\}`` 不入字符集；``\\p`` 绘图模式内的坐标代码跳过；普通转义
  ``\\x`` 会把 ``x`` 计入字符集。
- 内联切换：``\\fn<字体名>`` 后续文本归该字体；``\\fn`` 空恢复默认样式字体；
  ``\\r`` / ``\\r<style>`` 重置/切换到指定样式；``\\b`` ``\\i`` 切字重/斜体。
- 字体名前缀 ``@``（竖排）在匹配前剥离。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

FontKey = Tuple[str, int, bool]  # (font_name, weight, italic)


def strip_name(name: str, ch: str) -> str:
    """对齐 C++ ``trimLC_strip``：首部剥除指定字符与空白，尾部剥除空白。"""
    start = 0
    end = len(name)
    while start < end and (name[start] == ch or name[start].isspace()):
        start += 1
    while end > start and name[end - 1].isspace():
        end -= 1
    return name[start:end]


# --------------------------------------------------------------------------
# 时间戳（h:mm:ss.cc，1 tick = 100ns）
# --------------------------------------------------------------------------

_TIME_RE = re.compile(r"(\d+):(\d+):([\d.]+)")


def ass_time_to_ticks(timestr: str) -> int:
    """ASS 时间 h:mm:ss.cc -> 100ns ticks。解析失败返回 -1。"""
    m = _TIME_RE.search(timestr)
    if not m:
        return -1
    h, mi, sec = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return int((h * 3600 + mi * 60 + sec) * 1_0000_000.0)


def _is_dialogue(line: str) -> bool:
    return line.startswith("Dialogue:")


@dataclass
class AssParseResult:
    """一次 ASS 解析的结果。"""

    styles: Dict[str, Tuple[str, int, bool]] = field(default_factory=dict)
    default_style: str = ""
    char_map: Dict[FontKey, Set[int]] = field(default_factory=dict)
    # history 模式（旧 assfonts 用随机 ID 做字体名）的还原映射：replaced -> origin
    rename_map: Dict[str, str] = field(default_factory=dict)
    # 每个 Dialogue 的 (style, start_ticks, end_ticks)，供时间窗裁剪
    dialogues: List[Tuple[int, int]] = field(default_factory=list)

    def get_font_key(self, style_name: str) -> Optional[FontKey]:
        key = style_name
        if key in self.styles:
            return self.styles[key]
        if self.default_style and self.default_style in self.styles:
            return self.styles[self.default_style]
        # 未知 style 且无默认样式
        for k in self.styles.values():
            return k
        return None

    def merge_style_key(self, key: FontKey, text: str, styles: Dict[str, Tuple[str, int, bool]],
                        default: Tuple[str, int, bool]):
        """解析一行文本，把归属字符并入 char_map。key 为行内当前字体（可能被 \fn 等切换）。"""
        self._analyse_text(key, text, styles, default)


# --------------------------------------------------------------------------
# 文本收集（对齐 C++ 状态机）
# --------------------------------------------------------------------------

_SPECIAL_ESCAPES = frozenset("{}\nNnh")


def _next_char(text: str, idx: int):
    """返回 (char, 新下标)。处理多字符？Python str 已经是字符序列，直接取一个字符。"""
    if idx >= len(text):
        return "", idx
    return text[idx], idx + 1


def analyse_text(font_key: FontKey, text: str,
                 styles: Dict[str, Tuple[str, int, bool]],
                 default: FontKey,
                 char_map: Dict[FontKey, Set[int]]):
    """解析一行文本（C++ analyssLine 的 text 处理部分）。

    状态机：textState 0 = 普通文本；1 = override 块内（读取 tag）。
    字体键随 \\fn / \\r / \\b / \\i 切换，切换后新键自动建字符集。
    ``default`` 为**当前行所用样式**的字体键（\\r 空 / \\fn 空时恢复到此）。
    """
    if font_key not in char_map:
        char_map[font_key] = set()
    current = font_key
    current_chars = char_map[current]
    line_default = default or font_key

    text_state = 0
    draw_mod = False
    i = 0
    n = len(text)

    while i < n:
        add_char = False
        font_key_changed = False
        ch = text[i]

        if text_state == 0:
            if ch == "{":
                # 跳过块内容，直到 '}'、'\\' 或行尾
                while i < n and text[i] not in ("}", "\\"):
                    i += 1
                if i < n and text[i] == "\\":
                    text_state = 1
                elif i < n and text[i] == "}":
                    i += 1   # 中等-3：无反转义的 {注释} 块，'}' 同样不入字符集
                # 若抵到行尾则循环自然结束
                continue
            elif draw_mod:
                # 绘图模式：普通字符与转义都不入集
                i += 1
                continue
            elif ch == "\\":
                if i + 1 >= n:
                    break
                nxt = text[i + 1]
                i += 2
                if nxt not in _SPECIAL_ESCAPES:
                    # 普通转义字符（如 \- \~）作为可见字符计入
                    add_char = True
                    if add_char:
                        glyph = nxt if nxt != "\r" else ""
                        if glyph:
                            current_chars.add(ord(glyph))
                continue
            else:
                add_char = True
        elif text_state == 1:
            # override 块内：读取 tag 直到 '}' 或 '\\'
            code_start = i
            while i < n and text[i] not in ("}", "\\"):
                i += 1
            if i < n and text[i] == "}":
                text_state = 0
            # 若遇 '\\' 则保持块内继续读下一个 tag
            code = text[code_start:i]
            code = code.rstrip()

            if code.startswith("p") and len(code) > 1 and code[1:].isdigit():
                draw_mod = code[1] != "0"
            elif code.startswith("fn") or code.startswith("FN") or code.startswith("Fn") or code.startswith("fN"):
                font_key_changed = True
                if len(code) == 2:
                    # 恢复当前行样式的字体名（保留已切过的字重/斜体）
                    current = (line_default[0], current[1], current[2])
                else:
                    fname = strip_name(code[2:], "@")
                    pre, _, _ = fname.partition("\x00")
                    fname = pre or "Unknown"
                    current = (fname, current[1], current[2])
            elif code.startswith("r") or code.startswith("R"):
                font_key_changed = True
                rstyle = strip_name(code[1:], "*")
                if not rstyle:
                    # \r 空：恢复当前行样式的完整字体键
                    current = line_default
                else:
                    current = styles.get(rstyle, line_default)
            elif code.startswith("b") or code.startswith("B"):
                if len(code) == 1:
                    current = (current[0], default[1], current[2])
                    font_key_changed = True
                elif code[1:].isdigit():
                    weight = int(code[1:])
                    if weight == 0:
                        weight = 400
                    elif weight == 1:
                        weight = 700
                    current = (current[0], weight, current[2])
                    font_key_changed = True
            elif code.startswith("i") or code.startswith("I"):
                if len(code) == 1:
                    current = (current[0], current[1], default[2])
                    font_key_changed = True
                elif code[1:].isdigit():
                    # 对齐 C++：0 -> 否，其它值 -> 是
                    current = (current[0], current[1], code[1] != "0")
                    font_key_changed = True

            if font_key_changed:
                if current not in char_map:
                    char_map[current] = set()
                current_chars = char_map[current]
            # 推进过分隔符（'}') 或新的 '\'，避免块内连续 tag 死循环
            if i < n:
                i += 1
            continue

        if add_char:
            if ch != "\r":
                current_chars.add(ord(ch))
            i += 1
        else:
            i += 1


# --------------------------------------------------------------------------
# 主解析
# --------------------------------------------------------------------------

def parse_ass(ass_text: str, collect_dialogues: bool = False) -> AssParseResult:
    """解析整个 ASS 文本，返回样式表与字符集映射。"""
    result = AssParseResult()
    state = 0  # 0=头部 1=等待 Styles Format 2=Style 行 3=等待 Events Format 4=Dialogue
    style_cols: Dict[str, int] = {}
    event_cols: Dict[str, int] = {}
    styles = result.styles
    default_style = ""
    default_key: Tuple[str, int, bool] = ("", 400, False)

    for line in ass_text.split("\n"):
        if not line:
            continue
        ls = line.lstrip()

        if state == 0:
            if ls.startswith("[V4+ Styles]") or ls.startswith("[V4 Styles]"):
                state = 1
                continue
            if ls.startswith("; Font Subset:"):
                # replaced = 随机 8 字符 ID，还原原字体名
                rest = ls[len("; Font Subset:"):].strip()
                # 形如 "59W6OVGX - OriginalName"
                if " - " in rest:
                    replaced, origin = rest.split(" - ", 1)
                    result.rename_map[replaced.strip()] = origin.strip()
                continue
        elif state == 1:
            if ls.startswith("Format:"):
                cols = _parse_cols(ls[len("Format:"):])
                style_cols = {
                    name: idx for idx, name in enumerate(cols)
                    if name in ("Name", "Fontname", "Bold", "Italic")
                }
                state = 2
            else:
                # 没有 Format: 的非法文件
                state = 2
            continue
        elif state == 2:
            if ls.startswith("[Events]"):
                state = 3
                continue
            if ls.startswith("Style:"):
                _parse_style_line(ls, style_cols, styles)
                if not default_style and styles:
                    # 第一个 style 即默认（对齐 C++ defaultStyleName）
                    default_style = next(iter(styles))
                    default_key = styles[default_style]
            continue
        elif state == 3:
            if ls.startswith("Format:"):
                cols = _parse_cols(ls[len("Format:"):])
                event_cols = {
                    name: idx for idx, name in enumerate(cols)
                    if name in ("Style", "Text")
                }
                state = 4
            else:
                state = 4
            continue
        elif state == 4:
            if ls.startswith("[") and "]" in ls:
                break  # 后续其他段忽略
            if _is_dialogue(ls):
                style_name, text_part = _parse_dialogue(ls, event_cols)
                if collect_dialogues:
                    start_t = ass_time_to_ticks(_dialogue_field(ls, event_cols, "Start"))
                    end_t = ass_time_to_ticks(_dialogue_field(ls, event_cols, "End"))
                    result.dialogues.append((start_t, end_t))

                if style_name not in styles:
                    style_name = default_style
                key = styles.get(style_name, default_key)
                # default 传当前行样式键：\r/\fn 空恢复的应是行样式而非全局默认
                analyse_text(key, text_part, styles, key or default_key, result.char_map)
            continue

    result.default_style = default_style
    return result


def _parse_cols(text: str) -> List[str]:
    return [token.strip() for token in text.split(",") if token.strip()]


def _parse_style_line(line: str, cols: Dict[str, int],
                      styles: Dict[str, Tuple[str, int, bool]]):
    body = line[len("Style:"):]
    parts = body.split(",")
    name_idx = cols.get("Name")
    font_idx = cols.get("Fontname")
    bold_idx = cols.get("Bold")
    italic_idx = cols.get("Italic")
    if name_idx is None or name_idx >= len(parts):
        return
    name = strip_name(parts[name_idx].strip(), "*")
    if not name:
        return
    font_name = strip_name(parts[font_idx].strip(), "@") if font_idx is not None and font_idx < len(parts) else ""
    weight = 700 if (bold_idx is not None and bold_idx < len(parts)
                     and not _is_zero(parts[bold_idx])) else 400
    italic = bool(italic_idx is not None and italic_idx < len(parts)
                  and not _is_zero(parts[italic_idx]))
    styles[name] = (font_name, weight, italic)


def _is_zero(token: str) -> bool:
    t = token.strip()
    if not t:
        return True
    try:
        return float(t) == 0
    except ValueError:
        return False


def _parse_dialogue(line: str, cols: Dict[str, int]) -> Tuple[str, str]:
    """返回 (style名, 文本)。事件行标准 10 列，Text 之后含逗号。"""
    body = line[len("Dialogue:"):]
    text_idx = cols.get("Text", 9)
    style_idx = cols.get("Style", 3)
    parts = body.split(",", text_idx)
    if len(parts) < text_idx + 1:
        style = ""
        text = ""
    else:
        style = parts[style_idx].strip() if style_idx < len(parts) else ""
        text = ",".join(parts[text_idx:])
    return style, text


def _dialogue_field(line: str, cols: Dict[str, int], field_name: str) -> str:
    """取 Dialogue 行的指定列（按完整列索引，Event 标准字段顺序已知）。"""
    # Event 字段标准顺序: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
    order = ["Layer", "Start", "End", "Style", "Name", "MarginL", "MarginR", "MarginV", "Effect", "Text"]
    idx = order.index(field_name) if field_name in order else -1
    body = line[len("Dialogue:"):]
    if idx == -1:
        return ""
    parts = body.split(",", 10)
    if idx < len(parts):
        return parts[idx].strip()
    return ""


# --------------------------------------------------------------------------
# 时间窗裁剪（对齐规格书第 7 节第 12 步）
# --------------------------------------------------------------------------

def clip_dialogues_by_ticks(ass_text: str, start_ticks: int) -> str:
    """若 start_ticks > 0，丢弃 [Events] 中 End <= start_ticks 的 Dialogue 行。

    保留 [Script Info] / [V4+ Styles] / [Fonts] 段与行结构；时间不做偏移，
    保持字幕自身时间轴（播放器按自身播放位置渲染，不受影响）。
    返回裁剪后的 ASS 文本。
    """
    if start_ticks <= 0:
        return ass_text
    out_lines: List[str] = []
    in_events = False
    for line in ass_text.split("\n"):
        if line.startswith("[Events]"):
            in_events = True
        elif in_events and line.startswith("[") and "]" in line:
            in_events = False
        if in_events and _is_dialogue(line):
            body = line[len("Dialogue:"):]
            parts = body.split(",", 10)
            # Event 标准列：Layer,Start,End,...
            if len(parts) >= 3:
                end = ass_time_to_ticks(parts[2].strip())
                if end != -1 and end <= start_ticks:
                    continue  # 丢弃
        out_lines.append(line)
    return "\n".join(out_lines).rstrip("\n") + "\n"