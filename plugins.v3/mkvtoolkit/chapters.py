"""
章节文件解析与转换：OGM XML（mkvmerge/mkvpropedit 原生）与 ffmetadata（ffmpeg）。

用户导入章节时两种格式都接受，内部统一成
``[{"start": 秒, "end": 秒, "title": 文本}]``；需要喂给 ffmpeg 时再转回 ffmetadata。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Optional

_TIME_RE = re.compile(r"^(\d+):(\d{2}):(\d{2})(?:[.,](\d+))?$")


def ogm_time(seconds: float) -> str:
    """把秒格式化成 OGM 章节时间（纳秒精度）。"""
    if seconds < 0:
        seconds = 0.0
    total_ns = int(round(seconds * 1_000_000_000))
    hours, remainder = divmod(total_ns, 3_600_000_000_000)
    minutes, remainder = divmod(remainder, 60_000_000_000)
    secs, nanos = divmod(remainder, 1_000_000_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{nanos:09d}"


def parse_ogm_time(text: str) -> float:
    """解析 OGM 章节时间文本。"""
    match = _TIME_RE.match(text.strip())
    if not match:
        raise ValueError(f"无法解析章节时间：{text}")
    hours, minutes, secs, fraction = match.groups()
    value = int(hours) * 3600 + int(minutes) * 60 + int(secs)
    if fraction:
        value += int(fraction) / (10 ** len(fraction))
    return float(value)


def _parse_ogm(path: Path) -> list[dict[str, Any]]:
    """解析 OGM XML 章节。"""
    root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
    chapters: list[dict[str, Any]] = []
    for atom in root.iter("ChapterAtom"):
        start_text = atom.findtext("ChapterTimeStart")
        if not start_text:
            continue
        end_text = atom.findtext("ChapterTimeEnd")
        title = atom.findtext("ChapterDisplay/ChapterString") or ""
        start = parse_ogm_time(start_text)
        end = parse_ogm_time(end_text) if end_text else start
        chapters.append({"start": start, "end": max(end, start), "title": title.strip()})
    return chapters


def _parse_ffmetadata(path: Path) -> list[dict[str, Any]]:
    """解析 ffmetadata 章节。"""
    chapters: list[dict[str, Any]] = []
    current: Optional[dict[str, Any]] = None
    timebase = 1000.0
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line == "[CHAPTER]":
            if current:
                chapters.append(current)
            current = {"timebase": timebase, "start": 0.0, "end": 0.0, "title": ""}
            continue
        if current is None or not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().lower()
        value = value.strip()
        if key == "timebase":
            try:
                current["timebase"] = _parse_timebase(value)
            except ValueError:
                current["timebase"] = 1000.0
        elif key == "start":
            current["start"] = _scale(value, current["timebase"])
        elif key == "end":
            current["end"] = _scale(value, current["timebase"])
        elif key in {"title", "name"}:
            current["title"] = value
    if current:
        chapters.append(current)
    result: list[dict[str, Any]] = []
    for item in chapters:
        result.append({
            "start": float(item["start"]),
            "end": float(item["end"]),
            "title": str(item["title"]),
        })
    return result


def _parse_timebase(text: str) -> float:
    """解析 ``1/1000`` 形式的时间基。"""
    if "/" in text:
        numerator, _, denominator = text.partition("/")
        return float(denominator) / float(numerator or 1)
    return float(text or 1)


def _scale(value: str, timebase: float) -> float:
    """把时间基单位换算成秒。"""
    try:
        return float(value) / timebase
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def parse_chapter_file(path: Path) -> list[dict[str, Any]]:
    """
    自动识别并解析章节文件。

    :param path: 章节文件（OGM XML 或 ffmetadata）
    :return: 章节列表
    :raises ValueError: 两种格式都无法解析
    """
    text = path.read_text(encoding="utf-8", errors="replace")[:200].lstrip()
    if text.startswith("<"):
        return _parse_ogm(path)
    if text.startswith(";"):
        return _parse_ffmetadata(path)
    raise ValueError("无法识别章节文件格式（支持 OGM XML 与 ffmetadata）")


def chapters_to_ogm(chapters: list[dict[str, Any]]) -> str:
    """把章节列表序列化成 OGM XML。"""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<!DOCTYPE Chapters SYSTEM \"matroskachapters.dtd\">",
        "<Chapters>",
        "  <EditionEntry>",
    ]
    for item in chapters:
        lines.extend([
            "    <ChapterAtom>",
            f"      <ChapterTimeStart>{ogm_time(float(item.get('start', 0)))}</ChapterTimeStart>",
            "      <ChapterTimeEnd>"
            f"{ogm_time(float(item.get('end', item.get('start', 0))))}</ChapterTimeEnd>",
            "      <ChapterDisplay>",
            f"        <ChapterString>{_xml_escape(str(item.get('title', '')))}</ChapterString>",
            "      </ChapterDisplay>",
            "    </ChapterAtom>",
        ])
    lines.extend(["  </EditionEntry>", "</Chapters>", ""])
    return "\n".join(lines)


def chapters_to_ffmetadata(chapters: list[dict[str, Any]]) -> str:
    """把章节列表序列化成 ffmpeg 的 ffmetadata。"""
    lines = [";FFMETADATA1"]
    for item in chapters:
        lines.extend([
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={int(round(float(item.get('start', 0)) * 1000))}",
            f"END={int(round(float(item.get('end', item.get('start', 0))) * 1000))}",
            f"title={str(item.get('title', '')).replace('=', '_')}",
        ])
    return "\n".join(lines) + "\n"


def _xml_escape(text: str) -> str:
    """转义 XML 文本节点。"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
