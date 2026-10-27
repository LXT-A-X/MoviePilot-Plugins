"""
ASS 字幕字形级缺失检测。

流程：ASS 指纹 → 解析 [V4+ Styles] / [Events] / 覆盖标签 → 每个字体实际用到的字符
→ 解析到字体 face → cmap 覆盖比对 → 按字符给出缺失清单。

与旧实现（只看字体名是否存在）的区别：
- 名称存在但 font face 不覆盖实际字符 → 仍判缺失（部分覆盖只报缺的那部分）
- 同一字体名多 face 按并集计算；TTC 不会只算第一个 face
- 不把覆盖标签、换行符、绘图指令当成显示字符
"""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from .font_utils import _decode_ass_text, ass_section_name, normalize_font_key

# ASS 覆盖标签名只含小写字母（\fn / \r / \p / \k…）；
# 不能用 [a-zA-Z]+，否则 \rCN 会被当成标签名 "rCN"、\fnArial 会变成 "fnArial"。
_OVERRIDE_TAG_RE = re.compile(r"\\([a-z]+)([^\\}]*)")
_STYLE_FONT_FALLBACK = ""
# 样式段：v4 / v4+ / v4++ 都要识别，否则 V4++ 字幕的 Style 行被整体跳过、检查结论假“完整”
_V4_STYLE_SECTIONS = ("[v4 styles]", "[v4+ styles]", "[v4++ styles]", "[v4 styles+]")
# 对白引用了未定义样式时的字符归属桶（不能静默丢弃，否则漏报缺字体）
_UNKNOWN_STYLE_FONT = "__unknown__"


@dataclass
class AssFontUse:
    """一个字幕中某个字体名实际用到的字符集合。"""

    name: str
    codepoints: Set[int] = field(default_factory=set)

    @property
    def char_count(self) -> int:
        return len(self.codepoints)


@dataclass
class FaceCoverage:
    """字体索引里一个 face 的覆盖信息（数据库查询结果的轻量载体）。"""

    face_id: int
    file_path: str
    face_index: int
    names: List[str] = field(default_factory=list)
    codepoints: Set[int] = field(default_factory=set)

    def to_evidence(self) -> Dict[str, Any]:
        return {
            "face_id": self.face_id,
            "file_path": self.file_path,
            "face_index": self.face_index,
            "names": list(self.names)[:6],
        }


@dataclass
class FontVerdict:
    """单个字体引用的检测结论。"""

    name: str
    status: str  # ok / partial / missing / unknown / unused
    used_count: int = 0
    missing_count: int = 0
    missing_codepoints: List[int] = field(default_factory=list)
    missing_chars: str = ""
    faces: List[Dict[str, Any]] = field(default_factory=list)
    # 判定所依据的单一 face（-1=未选出）——与子集化 _choose_face 同口径
    face_index: int = -1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "used_count": self.used_count,
            "missing_count": self.missing_count,
            "missing_codepoints": self.missing_codepoints[:200],
            "missing_chars": self.missing_chars,
            "faces": self.faces,
            "face_index": self.face_index,
        }


@dataclass
class AssCheckResult:
    fonts: List[FontVerdict] = field(default_factory=list)
    unused_fonts: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def missing_names(self) -> List[str]:
        """兼容旧字段 missing_fonts：未解析或仍有缺失字符的字体名。"""
        return [v.name for v in self.fonts if v.status in ("missing", "partial")]

    @property
    def unverified_names(self) -> List[str]:
        """无法给出确定结论的字体名（索引异常/无 cmap）——不能当成「完整」。"""
        return [v.name for v in self.fonts if v.status == "unknown"]

    @property
    def missing_count(self) -> int:
        """兼容旧字段 missing_count：缺失字体引用数量（不是缺失字符数）。"""
        return len(self.missing_names)

    @property
    def total_missing_chars(self) -> int:
        return sum(v.missing_count for v in self.fonts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fonts": [v.to_dict() for v in self.fonts],
            "unused_fonts": self.unused_fonts,
            "warnings": self.warnings,
            "missing_names": self.missing_names,
            "unverified_names": self.unverified_names,
            "missing_count": self.missing_count,
            "total_missing_chars": self.total_missing_chars,
        }


def _read_ass_text(ass_bytes: bytes) -> str:
    try:
        return _decode_ass_text(ass_bytes)
    except Exception:
        return ass_bytes.decode("utf-8", errors="replace")


def _apply_override_tags(
    block: str,
    current_font: str,
    base_font: str,
    in_drawing: bool,
    style_fonts: Dict[str, str],
) -> Tuple[str, bool]:
    """处理一个 {…} 覆盖块里的字体/对齐/绘图标签，返回 (当前字体, 是否绘图模式)。"""
    font = current_font
    drawing = in_drawing
    for match in _OVERRIDE_TAG_RE.finditer(block):
        tag = (match.group(1) or "").lower()
        value = (match.group(2) or "").strip()
        if tag == "fn":
            # 嵌套在 \t(…\fnX) / \clip(…) 里时，值末尾会带上 ")"
            value = value.rstrip(")").strip()
            # 空值 = 回到当前样式字体
            font = value if value else base_font
        elif tag == "r":
            value = value.rstrip(")").strip()
            # \r 回到本行样式；\rSomeStyle 切换回指定样式
            if value:
                font = style_fonts.get(value, base_font)
            else:
                font = base_font
        elif tag == "p":
            digits = re.sub(r"\D", "", value)
            drawing = bool(digits) and int(digits) > 0
    return font, drawing


def _text_chars_by_font(
    text: str,
    base_font: str,
    style_fonts: Dict[str, str],
) -> Dict[str, Set[int]]:
    """从一条对白的 Text 字段提取「每个字体实际使用的字符」。

    跳过覆盖标签块、\\N/\\n 换行、绘图模式（\\p1…\\p0）里的矢量指令字符。
    """
    result: Dict[str, Set[int]] = {}
    current = base_font or _STYLE_FONT_FALLBACK
    drawing = False
    i = 0
    length = len(text)
    while i < length:
        ch = text[i]
        if ch == "{":
            end = text.find("}", i + 1)
            if end < 0:
                block = text[i + 1 :]
                i = length
            else:
                block = text[i + 1 : end]
                i = end + 1
            current, drawing = _apply_override_tags(block, current, base_font, drawing, style_fonts)
            continue
        if ch == "\\":
            nxt = text[i + 1] if i + 1 < length else ""
            if nxt in ("N", "n"):
                i += 2
                continue
            if nxt == "h":
                if not drawing:
                    result.setdefault(current, set()).add(0x20)
                i += 2
                continue
            # 其余反斜杠转义：跳过反斜杠与后一个字符
            i += 2
            continue
        if not drawing:
            cp = ord(ch)
            if cp >= 0x20 and cp != 0x7F:
                result.setdefault(current, set()).add(cp)
        i += 1
    return result


def _split_fields(payload: str, fields: List[str]) -> List[str]:
    if fields:
        return payload.split(",", len(fields) - 1)
    return payload.split(",", 9)


def _merge_usage(target: Dict[str, Set[int]], source: Dict[str, Set[int]]) -> None:
    for name, chars in source.items():
        if not name:
            continue
        target.setdefault(name, set()).update(chars)


def parse_ass_usage(ass_bytes: bytes) -> Tuple[OrderedDict[str, AssFontUse], List[str]]:
    """解析 ASS，返回 (字体名 → 使用字符, 警告列表)。"""
    text = _read_ass_text(ass_bytes)
    warnings: List[str] = []
    section = ""
    style_fields: List[str] = []
    event_fields: List[str] = []
    style_fonts: Dict[str, str] = {}
    usage: Dict[str, Set[int]] = OrderedDict()

    for raw in text.splitlines():
        line = raw.strip().lstrip("\ufeff")
        if not line:
            continue
        section_name = ass_section_name(line)
        if section_name:
            section = section_name
            continue
        if section in _V4_STYLE_SECTIONS and line.lower().startswith("format:"):
            style_fields = [f.strip().lower() for f in line.split(":", 1)[1].split(",")]
            continue
        if section in _V4_STYLE_SECTIONS and line.lower().startswith("style:"):
            fields = _split_fields(line.split(":", 1)[1], style_fields)
            if len(fields) < 2:
                warnings.append(f"样式行字段不足，已跳过: {line[:80]}")
                continue
            style_name = fields[0].strip()
            font_name = fields[1].strip()
            if style_name:
                style_fonts[style_name] = font_name
            continue
        if section == "[events]" and line.lower().startswith("format:"):
            event_fields = [f.strip().lower() for f in line.split(":", 1)[1].split(",")]
            continue
        if section == "[events]":
            low = line.lower()
            if low.startswith("comment:") or low.startswith("picture:") or low.startswith("sound:") or low.startswith("movie:") or low.startswith("command:"):
                continue
            if not low.startswith("dialogue:"):
                continue
            fields = _split_fields(line.split(":", 1)[1], event_fields)
            if event_fields:
                try:
                    style_index = event_fields.index("style")
                    text_index = event_fields.index("text")
                except ValueError:
                    style_index, text_index = 3, 9
            else:
                style_index, text_index = 3, 9
            if len(fields) <= max(style_index, text_index):
                warnings.append(f"对白行字段不足，已跳过: {line[:80]}")
                continue
            style_name = fields[style_index].strip()
            payload = fields[text_index]
            base_font = style_fonts.get(style_name, "")
            if not base_font:
                warnings.append(f"对白引用了未定义的样式「{style_name}」")
                # 字符不能丢：归入未知桶，后续按“缺失字体”暴露出来（漏报比误报更危险）
                base_font = _UNKNOWN_STYLE_FONT
            _merge_usage(usage, _text_chars_by_font(payload, base_font, style_fonts))

    result: OrderedDict[str, AssFontUse] = OrderedDict()
    for name, chars in usage.items():
        result[name] = AssFontUse(name=name, codepoints=set(chars))
    return result, warnings


def evaluate_usage(
    usage: Iterable[AssFontUse],
    lookup: Callable[[str], List[FaceCoverage]],
) -> AssCheckResult:
    """按字符比对字体覆盖，生成逐字体结论。lookup 负责字体名/别名 → face 列表。

    单 face 口径（与子集化 subset 的 _choose_face 完全一致）：成品字幕只会嵌入
    「覆盖字符最多的那一个 face」，因此覆盖率按该 face 计算，而不是把所有同名 face
    的 cmap 并集。否则多个同名 face 覆盖互补字符时，检测会误报「完整」，而实际
    子集化只嵌入一个 face、成品依旧缺字。
    """
    result = AssCheckResult()
    for item in usage:
        chars = set(item.codepoints)
        if not chars:
            result.unused_fonts.append(item.name)
            continue
        lookup_failed = False
        try:
            faces = list(lookup(item.name) or [])
        except Exception as err:
            result.warnings.append(f"查询字体「{item.name}」索引失败: {err}")
            faces = []
            lookup_failed = True
        # 选 face：覆盖字符最多者优先，其次 face_index 小的（通常是 Regular），
        # 与 harfbuzz_engine._choose_face 的排序键一致
        chosen: Optional[FaceCoverage] = None
        best_key = (-1, 10**6)
        for face in faces:
            covered_count = len(chars & set(face.codepoints))
            key = (covered_count, -int(face.face_index or 0))
            if key > best_key:
                chosen = face
                best_key = key
        covered: Set[int] = set(chosen.codepoints) if chosen is not None else set()
        missing = sorted(chars - covered)
        union: Set[int] = set()
        for face in faces:
            union |= set(face.codepoints)
        if lookup_failed:
            status = "unknown"  # 索引查询异常：不能断言缺失，也不能说完整
        elif not faces:
            status = "missing"
        elif not covered:
            # 有 face 但 cmap 为空（no_cmap）：无法用码点验证覆盖
            status = "unknown"
        elif missing:
            status = "partial"
        else:
            status = "ok"
        if status in ("partial", "unknown") and chosen is not None:
            holes = chars & (union - covered)
            if holes and status == "partial":
                result.warnings.append(
                    f"字体「{item.name}」多个 face 覆盖互补：子集化只嵌入单个 face"
                    f"（face_index={chosen.face_index}），另有 {len(holes)} 个字符仅被其它 face 覆盖，"
                    "成品字幕里可能仍缺字"
                )
        missing_chars = "".join(_safe_char(cp) for cp in missing[:30])
        if len(missing) > 30:
            missing_chars += "…"
        faces_evidence = [face.to_evidence() for face in faces[:8]]
        if chosen is not None:
            # 实际生效的 face 排在最前，便于前端/日志直接判定「用哪个 face 判的」
            chosen_ev = chosen.to_evidence()
            faces_evidence = [chosen_ev] + [
                ev for ev in faces_evidence if ev.get("face_id") != chosen_ev.get("face_id")
            ]
        result.fonts.append(
            FontVerdict(
                name=item.name,
                status=status,
                used_count=len(chars),
                missing_count=len(missing),
                missing_codepoints=missing,
                missing_chars=missing_chars,
                faces=faces_evidence,
                face_index=int(chosen.face_index) if chosen is not None else -1,
            )
        )
    return result


def _safe_char(cp: int) -> str:
    try:
        ch = chr(cp)
    except Exception:
        return "�"
    if ch.isspace():
        return "␣"
    if cp < 0x20 or cp == 0x7F:
        return "�"
    return ch
