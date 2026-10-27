"""
HDR 字幕亮度调整：子集化/上传字幕处理后按档位压暗主色、描边、阴影，避免 HDR 下刺眼。

仅做 ASS 文本改写，不依赖任何外部二进制。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 档位 → 目标主色（文档/前端展示用；实际压暗按 percent 等比缩放 RGB）
HDR_LEVEL_COLOUR: Dict[str, str] = {
    "100": "&H00FFFFFF",
    "85": "&H00D9D9D9",
    "80": "&H00CCCCCC",
    "75": "&H00BFBFBF",
    "70": "&H00B2B2B2",
    "63": "&H00A1A1A1",
    "50": "&H00808080",
}


def _decode_bytes_text(raw: bytes) -> Tuple[str, str]:
    """自适应解码 ass 文本并返回 (text, encoding)。UTF-16 BOM/前 1KB 含 NUL → utf-16，否则 utf-8。"""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace"), "utf-16"
    if b"\x00" in raw[:1024]:
        return raw.decode("utf-16", errors="replace"), "utf-16"
    return raw.decode("utf-8", errors="replace"), "utf-8"


def _scale_colour_token(col: str, percent: int) -> str:
    """把 ASS 色码 &H[AA]BBGGRR 按亮档压暗（RGB 各通道 × percent/100，保留 alpha）。"""
    m = re.fullmatch(r"&h([0-9a-fA-F]{6,8})", col.strip(), re.I)
    if not m:
        return col
    hexv = m.group(1)
    if len(hexv) == 8:
        a = hexv[:2]
        hexrgb = hexv[2:]
    else:
        a = "00"
        hexrgb = hexv
    try:
        # ASS 颜色是 &HAABBGGRR：hexrgb[0:2]=BB、[2:4]=GG、[4:6]=RR
        bb = int(hexrgb[0:2], 16) * percent // 100
        gg = int(hexrgb[2:4], 16) * percent // 100
        rr = int(hexrgb[4:6], 16) * percent // 100
        return f"&H{a}{bb:02X}{gg:02X}{rr:02X}"
    except Exception:
        return col


def apply_hdr_brightness(ass_path: Path, level: str) -> Optional[str]:
    """对 ass 文件应用 HDR 亮度压暗：改动 Style 主色/描边/阴影与行内颜色标签。

    :param ass_path: 目标 .ass 文件（就地改写）
    :param level: 档位（100/85/80/75/70/63/50）
    :return: 成功返回说明；禁用/失败返回 None
    """
    percent = int(level) if str(level) in HDR_LEVEL_COLOUR else 0
    if not percent:
        return None
    try:
        raw = Path(ass_path).read_bytes()
        text, encoding = _decode_bytes_text(raw)
        changed = 0
        lines = text.split("\n")
        out_lines: List[str] = []
        for line in lines:
            if line.startswith("Style:"):
                parts = line.split(",")
                # Style: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour,
                #        OutlineColour, BackColour, Bold, ...
                # 压暗：PrimaryColour(3) / OutlineColour(5) / BackColour(6)
                if len(parts) >= 9:
                    for idx in (3, 5, 6):
                        new = _scale_colour_token(parts[idx], percent)
                        if new != parts[idx].strip():
                            parts[idx] = new
                            changed += 1
                out_lines.append(",".join(parts))
                continue
            if "\\c" in line or "\\1c" in line or "\\3c" in line or "\\4c" in line:
                def _repl(m: "re.Match[str]") -> str:
                    token = m.group(0)
                    # 行内标签形如 \1c&H000000FF&：剥掉前缀与结尾 & 再缩放，原样拼回
                    pos = token.upper().find("&H")
                    if pos < 0:
                        return token
                    prefix = token[:pos]
                    color = token[pos:]
                    suffix = "&" if color.endswith("&") else ""
                    if suffix:
                        color = color[:-1]
                    return prefix + _scale_colour_token(color, percent) + suffix

                new_line = re.sub(
                    r"\\[134]?c&H[0-9a-fA-F]{6,8}&",
                    _repl,
                    line,
                    flags=re.I,
                )
                if new_line != line:
                    changed += 1
                out_lines.append(new_line)
                continue
            out_lines.append(line)
        if not changed:
            return None
        new_raw = "\n".join(out_lines).encode("utf-16" if encoding == "utf-16" else "utf-8", errors="replace")
        Path(ass_path).write_bytes(new_raw)
        return f"HDR 亮度已应用（{percent}%，主色/描边/阴影）"
    except Exception:
        return None
