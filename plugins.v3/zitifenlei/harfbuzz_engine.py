"""
HarfBuzz 子集化引擎 + ASS [Fonts] 内嵌写回。

- 子集化：uharfbuzz（hb_subset），只保留 ASS 实际用到的字符
- 内嵌：按 libass 的 [Fonts] 段格式写回（fontname: 名称 + 33 偏移的 6bit 编码数据）
- 名称：把子集字体内部 family/full/PS/typographic 名改成 ASS 里引用的字体名，
  保证 libass 按字幕里的名字能命中内嵌字体（libass 用字体内部元数据匹配，不看 fontname 标签）
- 写入：先写临时文件 → 回读验证（可解析、目标字符覆盖、字体数据可解码）→ 原子替换
- 失败不覆盖原字幕、不删除旧输出

不依赖 assfonts 二进制；缺 uharfbuzz 时明确报错，不静默回退。
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    import uharfbuzz as hb
except Exception as _hb_err:  # pragma: no cover - 运行环境缺依赖
    hb = None
    _HB_IMPORT_ERROR = str(_hb_err)
else:
    _HB_IMPORT_ERROR = ""

try:
    from fontTools.ttLib import TTFont
except Exception:  # pragma: no cover
    TTFont = None

from .font_utils import (
    MAX_ASS_FILE_BYTES,
    MAX_FONT_FILE_BYTES,
    _decode_ass_text,
    ass_section_name,
    is_ass_file,
)

FONT_EMBED_LINE_BYTES = 45  # 45 字节 → 60 个编码字符（4 的倍数）
DEFAULT_OUT_SUFFIX = ".ziti.ass"


class EngineError(RuntimeError):
    """子集化/内嵌失败（调用方转成任务失败状态，不静默）。"""


@dataclass
class FaceRef:
    """可用于子集化的字体 face。"""

    file_path: str
    face_index: int
    codepoints: Set[int] = field(default_factory=set)
    names: List[str] = field(default_factory=list)


@dataclass
class SubsetEmbed:
    font_name: str
    file_path: str
    face_index: int
    required: int
    encoded_size: int


@dataclass
class SubsetResult:
    success: bool = False
    out_path: str = ""
    embedded: List[SubsetEmbed] = field(default_factory=list)
    missing_fonts: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "out_path": self.out_path,
            "embedded": [
                {
                    "font_name": item.font_name,
                    "file_path": item.file_path,
                    "face_index": item.face_index,
                    "required": item.required,
                    "encoded_size": item.encoded_size,
                }
                for item in self.embedded
            ],
            "missing_fonts": self.missing_fonts,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def _hb_info() -> Tuple[bool, str]:
    if hb is None:
        return False, f"uharfbuzz 未安装或加载失败: {_HB_IMPORT_ERROR}"
    try:
        version = getattr(hb, "version_string", None) or getattr(hb, "__version__", "")
        return True, str(version or "unknown")
    except Exception as err:
        return False, str(err)


def refresh_backend() -> Tuple[bool, str]:
    """重新尝试加载 uharfbuzz（依赖重装后无需重启进程即可生效）。"""
    global hb, _HB_IMPORT_ERROR
    try:
        import importlib

        importlib.invalidate_caches()
        hb = importlib.import_module("uharfbuzz")
        _HB_IMPORT_ERROR = ""
    except Exception as err:
        hb = None
        _HB_IMPORT_ERROR = str(err)
    try:
        # 子集化依赖的字体解析库同步刷新（同一进程内 re-import）
        global TTFont
        if TTFont is None:
            from fontTools.ttLib import TTFont as _TTFont

            TTFont = _TTFont
    except Exception:
        pass
    return _hb_info()


def hb_available() -> Tuple[bool, str]:
    """启动自检：uharfbuzz 是否可用，返回 (可用, 版本或错误信息)。"""
    if hb is None:
        refresh_backend()
    return _hb_info()


def _subset_flags(input_obj: Any) -> None:
    # 默认保留 hinting/布局；显式声明便于后续调整
    try:
        flags = 0
        flags |= int(hb.SubsetFlags.PASSTHROUGH_UNRECOGNIZED)
        input_obj.flags = flags
    except Exception:
        pass


def subset_font_bytes(
    font_path: str | Path,
    codepoints: Iterable[int],
    face_index: int = 0,
    rename_to: str = "",
) -> bytes:
    """对单个 face 做 HarfBuzz 子集化，返回字体字节（可选重命名内部名称）。"""
    ok, info = hb_available()
    if not ok:
        raise EngineError(info)
    if TTFont is None:
        raise EngineError("fontTools 未安装，无法写入子集字体名称")
    chars = {int(cp) for cp in codepoints if 0 <= int(cp) <= 0x10FFFF}
    if not chars:
        raise EngineError("没有需要保留的字符，拒绝生成空子集")
    chars.add(0x20)  # 空格始终保留（字幕空白/间距）
    # 解析前先做体积上限检查：避免把超大字体整读进内存 / 长时间占用 C 扩展
    try:
        font_size = Path(font_path).stat().st_size
    except OSError as err:
        raise EngineError(f"读取字体文件失败（{Path(font_path).name}）: {err}")
    if font_size > MAX_FONT_FILE_BYTES:
        raise EngineError(
            f"字体文件超过解析上限（{font_size} > {MAX_FONT_FILE_BYTES} 字节），拒绝子集化"
        )
    raw = Path(font_path).read_bytes()
    try:
        face = hb.Face(raw, index=max(0, int(face_index)))
        inp = hb.SubsetInput()
        unicode_set = inp.sets(hb.SubsetInputSets.UNICODE)
        for cp in chars:
            unicode_set.add(cp)
        _subset_flags(inp)
        subset_face = hb.subset(face, inp)
        data = subset_face.blob.data
    except Exception as err:
        raise EngineError(f"HarfBuzz 子集化失败（{Path(font_path).name} face {face_index}）: {err}")
    if not data:
        raise EngineError("HarfBuzz 子集化输出为空")
    if rename_to:
        try:
            data = _rename_subset_names(data, rename_to)
        except Exception as err:
            raise EngineError(f"重写子集字体名称失败: {err}")
    return data


def _ps_name(name: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-")
    return text or "EmbeddedFont"


def _rename_subset_names(data: bytes, name: str) -> bytes:
    """把子集字体的 family/full/PS/typographic family 改成 ASS 引用的名称。

    ASS 的「@字体名」表示竖排：libass 匹配时会剥掉 @ 再查内部 family，
    所以内嵌字体的内部名必须用不带 @ 的原名，否则竖排样式找不到内嵌字体。
    """
    # [Fonts] 的 fontname 标签仍保留 ASS 原名（含 @），只改字体内部名称
    if name.startswith("@"):
        name = name[1:]
    font = TTFont(BytesIO(data))
    try:
        if "name" not in font:
            from fontTools.ttLib.tables._n_a_m_e import table__n_a_m_e

            font["name"] = table__n_a_m_e()
        name_table = font["name"]
        ps = _ps_name(name)
        for record in list(name_table.names):
            name_id = int(record.nameID)
            value = None
            if name_id in (1, 4, 16):
                value = name
            elif name_id == 6:
                value = ps
            if value is None:
                continue
            try:
                name_table.setName(
                    value,
                    name_id,
                    record.platformID,
                    record.platEncID,
                    record.langID,
                )
            except Exception:
                continue
        buffer = BytesIO()
        font.save(buffer)
        return buffer.getvalue()
    finally:
        try:
            font.close()
        except Exception:
            pass


def encode_font_data(data: bytes) -> List[str]:
    """按 libass 的 [Fonts] 解码规则编码字体数据（33 偏移，3 字节 → 4 字符）。"""
    lines: List[str] = []
    for offset in range(0, len(data), FONT_EMBED_LINE_BYTES):
        chunk = data[offset : offset + FONT_EMBED_LINE_BYTES]
        chars: List[str] = []
        for pos in range(0, len(chunk), 3):
            group = chunk[pos : pos + 3]
            padded = group + b"\x00" * (3 - len(group))
            value = (padded[0] << 16) | (padded[1] << 8) | padded[2]
            count = len(group) + 1
            encoded = [
                ((value >> 18) & 63) + 33,
                ((value >> 12) & 63) + 33,
                ((value >> 6) & 63) + 33,
                (value & 63) + 33,
            ]
            chars.extend(chr(code) for code in encoded[:count])
        lines.append("".join(chars))
    return lines


def decode_font_data(encoded: str) -> bytes:
    """反向解码 [Fonts] 数据（libass decode_chars 的 Python 实现，用于自检）。"""
    out = bytearray()
    text = "".join(ch for ch in encoded if ch not in "\r\n")
    index = 0
    length = len(text)
    while index < length:
        remain = length - index
        count = 4 if remain >= 4 else remain
        if count == 1:
            raise EngineError("字体内嵌数据长度非法（%4 == 1）")
        value = 0
        for i in range(count):
            value |= ((ord(text[index + i]) - 33) & 63) << (6 * (3 - i))
        out.append((value >> 16) & 0xFF)
        if count >= 3:
            out.append((value >> 8) & 0xFF)
        if count >= 4:
            out.append(value & 0xFF)
        index += count
    return bytes(out)


def build_fonts_section(entries: Sequence[Tuple[str, bytes]]) -> str:
    lines: List[str] = ["[Fonts]"]
    for name, data in entries:
        lines.append(f"fontname: {name}")
        lines.extend(encode_font_data(data))
        lines.append("")
    return "\n".join(lines) + "\n"


def strip_fonts_section(text: str) -> str:
    """移除已有的 [Fonts] 段（保留其余段落）。

    段边界只认标准 ASS 段名：字体数据行是 33 偏移编码文本，可能恰好
    以 "[" 开头、"]" 结尾，按通用方括号判断会被当成分段而提前截断。
    """
    kept: List[str] = []
    skipping = False
    for line in text.splitlines(keepends=True):
        section = ass_section_name(line)
        if section:
            skipping = section == "[fonts]"
            if skipping:
                continue
        if not skipping:
            kept.append(line)
    return "".join(kept).rstrip() + "\n"


def _read_ass_text(ass_bytes: bytes) -> str:
    try:
        return _decode_ass_text(ass_bytes)
    except Exception:
        return ass_bytes.decode("utf-8", errors="replace")


def _choose_face(refs: Sequence[FaceRef], chars: Set[int]) -> Optional[FaceRef]:
    """同一字体名多个 face：选覆盖字符最多者，其次优先 face_index 小的（通常是 Regular）。"""
    best: Optional[FaceRef] = None
    best_key = (-1, 10**6)
    for ref in refs:
        covered = len(chars & set(ref.codepoints))
        key = (covered, -int(ref.face_index))
        if key > best_key:
            best = ref
            best_key = key
    return best


def subset_ass_with_plan(
    ass_path: str | Path,
    out_path: str | Path,
    plan: Sequence[Dict[str, Any]],
    warnings: Optional[Sequence[str]] = None,
) -> SubsetResult:
    """按「已选定的 face + 覆盖字符」执行子集化并写回 [Fonts]。

    plan 每项：{"font_name", "file_path", "face_index", "codepoints"}，由调用方
    基于字体索引预先生成（进度隔离时由父进程生成、工作进程直接执行）。
    本函数不做字体名→face 解析，也不查数据库，便于在独立子进程中运行。
    """
    result = SubsetResult()
    if warnings:
        result.warnings.extend(str(item) for item in warnings)
    source = Path(ass_path)
    target = Path(out_path)
    if not source.is_file():
        result.errors.append(f"字幕不存在: {source}")
        return result
    ok, info = hb_available()
    if not ok:
        result.errors.append(info)
        return result

    entries: List[Tuple[str, bytes]] = []
    expected_embedded: Dict[str, Set[int]] = {}
    for item in plan:
        try:
            font_name = str(item.get("font_name") or "")
            file_path = str(item.get("file_path") or "")
            face_index = int(item.get("face_index") or 0)
            chars = {
                int(cp)
                for cp in (item.get("codepoints") or [])
                if 0 <= int(cp) <= 0x10FFFF
            }
        except Exception as err:
            result.errors.append(f"子集化计划条目非法: {err}")
            continue
        if not font_name or not file_path or not chars:
            continue
        try:
            data = subset_font_bytes(file_path, chars, face_index, rename_to=font_name)
        except EngineError as err:
            result.errors.append(f"字体「{font_name}」:{err}")
            continue
        entries.append((font_name, data))
        expected_embedded[font_name] = set(chars)
        result.embedded.append(
            SubsetEmbed(
                font_name=font_name,
                file_path=file_path,
                face_index=face_index,
                required=len(chars),
                encoded_size=len(data),
            )
        )

    if not entries:
        if not result.errors:
            result.errors.append("没有需要内嵌的字体")
        return result

    try:
        ass_size = source.stat().st_size
        if ass_size > MAX_ASS_FILE_BYTES:
            result.errors.append(
                f"字幕文件超过处理上限（{ass_size} > {MAX_ASS_FILE_BYTES} 字节）: {source}"
            )
            return result
        raw = source.read_bytes()
        had_bom = raw.startswith(b"\xef\xbb\xbf")
        text = _read_ass_text(raw)
        body = strip_fonts_section(text)
        fonts_section = build_fonts_section(entries)
        output_text = body + ("\n" if body and not body.endswith("\n") else "") + fonts_section
        # 自检：内嵌数据可解码、字体可解析、目标字符存在
        for name, data in entries:
            if not data:
                raise EngineError(f"字体「{name}」内嵌数据为空")
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            temp_path.write_text(output_text, encoding="utf-8-sig" if had_bom else "utf-8")
            _validate_output(temp_path, expected_embedded)
            os.replace(temp_path, target)
        finally:
            temp_path.unlink(missing_ok=True)
        result.out_path = str(target)
        result.success = True
        return result
    except Exception as err:
        result.errors.append(f"写入/验证输出失败: {err}")
        return result


def subset_ass_file(
    ass_path: str | Path,
    out_path: str | Path,
    usage: Dict[str, Set[int]],
    resolve_faces,
    embed_missing: bool = False,
) -> SubsetResult:
    """对 ASS 做子集化并写回 [Fonts]（进程内入口）。

    usage: 字体名 → 实际使用字符（glyph_checker.parse_ass_usage 的结果）
    resolve_faces: 字体名 → List[FaceRef]（由字体索引查询）
    embed_missing: 缺失字体是否仍写占位（默认否，缺失项只记录不内嵌）

    解析负责构建 plan，真正的子集化/写盘统一走 subset_ass_with_plan，
    保证进程内与子进程隔离两条路径行为一致。
    """
    source = Path(ass_path)
    target = Path(out_path)
    if not source.is_file():
        return SubsetResult(errors=[f"字幕不存在: {source}"])
    ok, info = hb_available()
    if not ok:
        return SubsetResult(errors=[info])

    plan: List[Dict[str, Any]] = []
    missing_fonts: List[str] = []
    pre_errors: List[str] = []
    warnings: List[str] = []
    # @竖排字体与同名常规字体是同一物理字体的两种写法：合并字符集只内嵌一份。
    # 否则内嵌两个同 family 子集时，libass 可能选到字符不全的那份，导致竖排缺字。
    merged: Dict[str, Set[int]] = {}
    for raw_name, codepoints in usage.items():
        # libass 查找字体会剥掉 @ 前缀，内嵌标签统一写不带 @ 的原名
        name = raw_name[1:] if raw_name.startswith("@") else raw_name
        merged.setdefault(name, set()).update(int(cp) for cp in codepoints)
    for font_name, chars in merged.items():
        if not chars:
            continue
        try:
            refs = list(resolve_faces(font_name) or [])
        except Exception as err:
            pre_errors.append(f"查询字体「{font_name}」失败: {err}")
            refs = []
        if not refs:
            missing_fonts.append(font_name)
            if not embed_missing:
                continue
        ref = _choose_face(refs, chars) if refs else None
        if ref is None:
            continue
        covered = chars & set(ref.codepoints)
        if not covered:
            missing_fonts.append(font_name)
            continue
        if len(covered) < len(chars):
            warnings.append(
                f"字体「{font_name}」只覆盖 {len(covered)}/{len(chars)} 个字符，缺失字符沿用播放器回退"
            )
        plan.append(
            {
                "font_name": font_name,
                "file_path": ref.file_path,
                "face_index": ref.face_index,
                "codepoints": sorted(covered),
            }
        )

    result = subset_ass_with_plan(source, target, plan, warnings=warnings)
    result.errors = pre_errors + result.errors
    result.missing_fonts = missing_fonts
    if missing_fonts and not result.success and not result.embedded:
        if "没有需要内嵌的字体" in result.errors:
            result.errors.remove("没有需要内嵌的字体")
        result.errors.append("没有可内嵌的字体（全部缺失或未被索引命中）")
    return result


def _validate_output(path: Path, expected_embedded: Dict[str, Set[int]]) -> None:
    """回读输出：能解析、[Fonts] 段可解码、每个内嵌字体覆盖其实需保留的字符。"""
    from .glyph_checker import parse_ass_usage

    data = path.read_bytes()
    usage_back, warnings = parse_ass_usage(data)
    if not usage_back:
        raise EngineError("输出字幕解析不到任何字体引用")
    embedded = extract_embedded_fonts(data)
    if not embedded:
        raise EngineError("输出字幕没有可解码的 [Fonts] 内嵌字体")
    by_name = {name: blob for name, blob in embedded}
    for font_name, chars in expected_embedded.items():
        blob = by_name.get(font_name)
        if blob is None:
            raise EngineError(f"输出字幕缺少字体「{font_name}」的内嵌数据")
        if TTFont is None:
            continue
        try:
            font = TTFont(BytesIO(blob), fontNumber=0, lazy=True)
            try:
                cmap = font.getBestCmap() or {}
            finally:
                font.close()
        except Exception as err:
            raise EngineError(f"内嵌字体「{font_name}」无法解析: {err}")
        missing = {cp for cp in chars if cp not in cmap}
        if missing:
            preview = "".join(chr(cp) for cp in sorted(missing)[:10])
            raise EngineError(f"内嵌字体「{font_name}」缺少目标字符: {preview}")


def extract_embedded_fonts(ass_bytes: bytes) -> List[Tuple[str, bytes]]:
    """解析 [Fonts] 段，返回 [(fontname 标签, 字体字节)]（用于自检/测试）。"""
    text = _read_ass_text(ass_bytes)
    result: List[Tuple[str, bytes]] = []
    in_fonts = False
    current_name = ""
    buffer: List[str] = []
    for line in text.splitlines():
        section = ass_section_name(line)
        if section:
            if in_fonts and current_name and buffer:
                try:
                    result.append((current_name, decode_font_data("".join(buffer))))
                except Exception:
                    pass
            in_fonts = section == "[fonts]"
            current_name = ""
            buffer = []
            continue
        if not in_fonts:
            continue
        stripped = line.strip()
        if stripped.lower().startswith("fontname:"):
            if current_name and buffer:
                try:
                    result.append((current_name, decode_font_data("".join(buffer))))
                except Exception:
                    pass
            current_name = stripped.split(":", 1)[1].strip()
            buffer = []
            continue
        if not stripped:
            continue
        if current_name:
            buffer.append(stripped)
    if in_fonts and current_name and buffer:
        try:
            result.append((current_name, decode_font_data("".join(buffer))))
        except Exception:
            pass
    return result


def default_output_path(ass_path: str | Path, suffix: str = DEFAULT_OUT_SUFFIX) -> Path:
    """默认输出：原目录/原基础名 + .ziti.ass（不再使用 .assfonts.ass）。"""
    source = Path(ass_path)
    return source.with_name(source.stem + suffix)
