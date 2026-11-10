"""
同级素材发现、语言推断与字幕编码探测。

MkvToolkit 的“自动发现”只做文件名前缀匹配：只有与视频主文件名共享前缀的字幕/音频
才会被默认勾选，避免把相邻剧集的素材误挂到当前文件上。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Optional

from .fssvc import AUDIO_EXT, FONT_EXT, SUBTITLE_EXT


def _normalized_stem(name: str) -> str:
    """把文件名主干转成用于比较的小写形式（忽略常见分隔符差异）。"""
    text = name.lower()
    for token in (" ", ".", "_", "-", "[", "]", "(", ")", "【", "】"):
        text = text.replace(token, "")
    return text


def _matches_prefix(file_stem: str, video_stem: str) -> bool:
    """判断素材文件名主干是否与视频文件名前缀匹配。"""
    left = _normalized_stem(file_stem)
    right = _normalized_stem(video_stem)
    if not left or not right:
        return False
    return left == right or left.startswith(right) or right.startswith(left)


def infer_language(name: str, language_map: dict[str, str]) -> str:
    """
    从文件名片段推断语言码。

    :param name: 文件名（含扩展名可）
    :param language_map: 标记到语言码的映射
    :return: 语言码，识别失败返回 ``und``
    """
    lowered = name.lower()
    tokens = sorted(language_map.items(), key=lambda item: len(item[0]), reverse=True)
    for token, code in tokens:
        if token and token in lowered:
            return code
    return "und"


def detect_text_encoding(path: Path, max_bytes: int = 512 * 1024) -> str:
    """
    探测文本字幕编码，返回 mkvmerge 可识别的字符集名称。

    优先 UTF-8（含 BOM），其次 GB18030（兼容 GBK/GB2312），最后 BIG5。

    :param path: 字幕文件
    :param max_bytes: 最多读取的字节数
    :return: ``UTF-8`` / ``GB18030`` / ``BIG5``
    """
    try:
        data = path.read_bytes()[:max_bytes]
    except OSError:
        return "UTF-8"
    for encoding in ("utf-8-sig", "utf-8"):
        try:
            data.decode(encoding)
            return "UTF-8"
        except UnicodeDecodeError:
            continue
    for encoding, label in (("gb18030", "GB18030"), ("big5", "BIG5")):
        try:
            data.decode(encoding)
            return label
        except UnicodeDecodeError:
            continue
    return "UTF-8"


def _entry(path: Path, language_map: dict[str, str], matched: bool) -> dict[str, Any]:
    """构造一个同级素材条目。"""
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    return {
        "name": path.name,
        "path": str(path),
        "size": size,
        "ext": path.suffix.lower(),
        "language": infer_language(path.name, language_map),
        "matched": matched,
    }


def discover_siblings(
    video_path: Path,
    language_map: dict[str, str],
    include_fonts: bool = True,
) -> dict[str, list[dict[str, Any]]]:
    """
    扫描视频同目录（字体额外扫描 ``fonts`` 子目录）的素材候选。

    :param video_path: 视频文件路径
    :param language_map: 语言标记映射
    :param include_fonts: 是否扫描字体
    :return: ``subtitles`` / ``audios`` / ``fonts`` 三个列表
    """
    parent = video_path.parent
    video_stem = video_path.stem
    result: dict[str, list[dict[str, Any]]] = {"subtitles": [], "audios": [], "fonts": []}
    try:
        entries = sorted(parent.iterdir(), key=lambda item: item.name.lower())
    except OSError:
        return result
    for entry in entries:
        if entry.is_dir() or entry.name.startswith("."):
            continue
        suffix = entry.suffix.lower()
        stem = entry.stem
        matched = _matches_prefix(stem, video_stem)
        if suffix in SUBTITLE_EXT:
            if matched or _is_same_episode(stem, video_stem):
                result["subtitles"].append(_entry(entry, language_map, matched))
        elif suffix in AUDIO_EXT:
            if matched:
                result["audios"].append(_entry(entry, language_map, matched))
        elif include_fonts and suffix in FONT_EXT:
            result["fonts"].append(_entry(entry, language_map, matched))

    if include_fonts:
        fonts_dir = parent / "fonts"
        if fonts_dir.is_dir():
            try:
                for entry in sorted(fonts_dir.iterdir(), key=lambda item: item.name.lower()):
                    if entry.is_file() and entry.suffix.lower() in FONT_EXT:
                        item = _entry(entry, language_map, False)
                        item["matched"] = False
                        result["fonts"].append(item)
            except OSError:
                pass
    return result


def _is_same_episode(stem: str, video_stem: str) -> bool:
    """宽松匹配：字幕名以视频名开头时也认为是同集素材（如 ``E01.cht.srt``）。"""
    left = _normalized_stem(stem)
    right = _normalized_stem(video_stem)
    return bool(left and right and left.startswith(right))
