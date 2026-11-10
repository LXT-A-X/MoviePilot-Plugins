"""
媒体信息探测：优先 ``mkvmerge -J``，缺失时退回 ``ffprobe``。

输出统一成前端与 planner 共用的 MediaInfo 字典，轨道 ``id`` 使用 mkvmerge 的
0 基轨道序号（同一文件内所有轨道按顺序编号，附件使用独立编号）。
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from .chapters import parse_chapter_file
from .siblings import detect_text_encoding, discover_siblings

_CODEC_NAMES = {
    "AVC": "H.264",
    "HEVC": "HEVC",
    "VP9": "VP9",
    "AV1": "AV1",
    "MPEG-4p10": "H.265",
    "AAC": "AAC",
    "AC-3": "AC-3",
    "E-AC-3": "E-AC-3",
    "DTS": "DTS",
    "TrueHD": "TrueHD",
    "FLAC": "FLAC",
    "MP3": "MP3",
    "Opus": "Opus",
    "Vorbis": "Vorbis",
    "PCM": "PCM",
    "SubRip/SRT": "SRT",
    "SubStationAlpha": "ASS",
    "SSA/ASS": "ASS",
    "HDMV PGS": "PGS",
    "VobSub": "VobSub",
    "WebVTT": "WebVTT",
}

_TYPE_MAP = {
    "video": "video",
    "audio": "audio",
    "subtitles": "subtitle",
    "subtitle": "subtitle",
    "attachment": "attachment",
}

_HDR_TRANSFERS = {"smpte2084": "HDR10", "arib-std-b67": "HLG"}


class ProbeError(RuntimeError):
    """探测失败时抛出。"""


def _run_json(args: list[str], timeout: int = 60) -> dict[str, Any]:
    """执行命令并解析 JSON 输出。"""
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as error:
        raise ProbeError(f"命令执行失败：{error}") from error
    raw = result.stdout.strip()
    if not raw:
        raise ProbeError(result.stderr.strip() or "命令没有输出")
    try:
        data = json.loads(raw)
    except ValueError as error:
        raise ProbeError(f"JSON 解析失败：{error}") from error
    if isinstance(data, dict) and data.get("errors"):
        raise ProbeError("; ".join(str(item) for item in data["errors"]))
    return data


def _ns_to_seconds(value: Any) -> Optional[float]:
    """把纳秒整数转换为秒。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    return number / 1_000_000_000


def _friendly_codec(codec: str) -> str:
    """把 mkvmerge/ffprobe 的编码名映射成更常见的形式。"""
    return _CODEC_NAMES.get(codec, codec or "未知")


def probe_media(
    path: Path,
    engine: dict[str, Any],
    language_map: dict[str, str],
    extract_chapters: bool = True,
) -> dict[str, Any]:
    """
    探测一个视频文件的容器、轨道、章节、附件与同级素材。

    :param path: 视频文件
    :param engine: ``EngineManager.detect()`` 的结果（用于取工具路径）
    :param language_map: 语言标记映射
    :param extract_chapters: 是否尝试解析完整章节列表
    :return: MediaInfo 字典
    """
    mkvmerge = _tool_path(engine, "mkvmerge")
    ffprobe = _tool_path(engine, "ffprobe")
    warnings: list[str] = []
    info: dict[str, Any]
    if mkvmerge:
        info = _probe_with_mkvmerge(path, mkvmerge)
    elif ffprobe:
        info = _probe_with_ffprobe(path, ffprobe)
        warnings.append("当前使用 ffprobe 探测，部分轨道细节可能缺失")
    else:
        raise ProbeError("未检测到 mkvmerge 或 ffprobe，无法读取媒体信息")

    if ffprobe:
        try:
            _enrich_video(path, ffprobe, info)
        except ProbeError:
            pass
    _estimate_video_bitrate(path, info)
    if mkvmerge and extract_chapters and path.suffix.lower() == ".mkv":
        mkvextract = _tool_path(engine, "mkvextract")
        if mkvextract:
            chapters = _extract_chapters(path, mkvextract)
            if chapters:
                info["chapters"] = chapters
    siblings = discover_siblings(path, language_map)
    for item in siblings.get("subtitles", []):
        if item.get("matched"):
            item["encoding"] = detect_text_encoding(Path(item["path"]))
    info["siblings"] = siblings
    info["warnings"] = warnings
    return info


def _tool_path(engine: dict[str, Any], tool: str) -> Optional[str]:
    """从引擎探测结果里取工具路径。"""
    state = engine.get(tool) or {}
    return str(state.get("path") or "") or None


def _probe_with_mkvmerge(path: Path, mkvmerge: str) -> dict[str, Any]:
    """使用 ``mkvmerge -J`` 解析容器信息。"""
    data = _run_json([mkvmerge, "-J", str(path)])
    container = data.get("container") or {}
    properties = container.get("properties") or {}
    duration = _ns_to_seconds(properties.get("duration"))
    tracks: list[dict[str, Any]] = []
    for track in data.get("tracks") or []:
        props = track.get("properties") or {}
        track_type = _TYPE_MAP.get(str(track.get("type")), str(track.get("type")))
        track_id = int(track.get("id", len(tracks)))
        default_duration = props.get("default_duration")
        fps = None
        try:
            if default_duration:
                fps = round(1_000_000_000 / float(default_duration), 3)
        except (TypeError, ValueError, ZeroDivisionError):
            fps = None
        # 优先使用 BCP47 标签：简体/繁体等细分信息只存在 language_ietf 里
        ietf_language = str(props.get("language_ietf") or "").strip()
        tracks.append({
            "id": track_id,
            "type": track_type,
            "ff_index": None,
            "codec": _friendly_codec(str(track.get("codec") or "")),
            "codec_raw": str(track.get("codec") or ""),
            "codec_detail": "",
            "language": ietf_language or str(props.get("language") or "und"),
            "name": str(props.get("track_name") or ""),
            "default": bool(props.get("default_track")),
            "forced": bool(props.get("forced_track")),
            "width": _int_or_none(str(props.get("pixel_dimensions") or "").split("x")[0]),
            "height": _int_or_none(str(props.get("pixel_dimensions") or "").split("x")[-1]),
            "fps": fps,
            "hdr": "",
            "bitrate": None,
            "channels": _int_or_none(props.get("audio_channels")),
            "sample_rate": _int_or_none(props.get("audio_sampling_frequency")),
            "duration": _ns_to_seconds(props.get("tag_duration")) or duration,
        })
    attachments: list[dict[str, Any]] = []
    for attachment in data.get("attachments") or []:
        attachments.append({
            "id": int(attachment.get("id", len(attachments))),
            "name": str(attachment.get("file_name") or ""),
            "mime": str(attachment.get("content_type") or ""),
            "size": int(attachment.get("size") or 0),
        })
    chapter_count = data.get("chapters")
    try:
        chapter_count = int(chapter_count or 0)
    except (TypeError, ValueError):
        chapter_count = 0
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    return {
        "path": str(path),
        "name": path.name,
        "size": size,
        "container": {
            "format": str(container.get("type") or "Matroska"),
            "duration": duration,
            "title": str(properties.get("title") or ""),
            "muxing_app": str(properties.get("muxing_application") or ""),
            "writing_app": str(properties.get("writing_application") or ""),
            "tags": properties.get("tags") or {},
        },
        "tracks": tracks,
        "attachments": attachments,
        "chapters": [],
        "chapter_count": chapter_count,
        "warnings": [],
    }


def _probe_with_ffprobe(path: Path, ffprobe: str) -> dict[str, Any]:
    """使用 ffprobe 解析容器信息（降级路径）。"""
    data = _run_json([
        ffprobe, "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", "-show_chapters", f"file:{path}",
    ], timeout=90)
    fmt = data.get("format") or {}
    duration = _float_or_none(fmt.get("duration"))
    tracks: list[dict[str, Any]] = []
    attachments: list[dict[str, Any]] = []
    for index, stream in enumerate(data.get("streams") or []):
        codec_type = str(stream.get("codec_type") or "")
        tags = stream.get("tags") or {}
        disposition = stream.get("disposition") or {}
        if codec_type == "attachment":
            attachments.append({
                "id": len(attachments),
                "name": str(tags.get("filename") or f"attachment-{index}"),
                "mime": str(tags.get("mimetype") or ""),
                "size": _int_or_none(stream.get("size")) or 0,
            })
            continue
        track_type = _TYPE_MAP.get(codec_type, codec_type)
        if track_type not in {"video", "audio", "subtitle"}:
            continue
        tracks.append({
            "id": len(tracks),
            "type": track_type,
            "ff_index": index,
            "codec": _friendly_codec(str(stream.get("codec_name") or "")),
            "codec_raw": str(stream.get("codec_name") or ""),
            "codec_detail": str(stream.get("profile") or ""),
            "language": str(tags.get("language") or "und"),
            "name": str(tags.get("title") or ""),
            "default": bool(disposition.get("default")),
            "forced": bool(disposition.get("forced")),
            "width": _int_or_none(stream.get("width")),
            "height": _int_or_none(stream.get("height")),
            "fps": _parse_fps(stream.get("r_frame_rate")),
            "hdr": _HDR_TRANSFERS.get(str(stream.get("color_transfer") or ""), ""),
            "bitrate": _int_or_none(stream.get("bit_rate")),
            "channels": _int_or_none(stream.get("channels")),
            "sample_rate": _int_or_none(stream.get("sample_rate")),
            "duration": _float_or_none(stream.get("duration")) or duration,
        })
    chapters = []
    for item in data.get("chapters") or []:
        chapters.append({
            "start": _float_or_none(item.get("start_time")) or 0.0,
            "end": _float_or_none(item.get("end_time")) or 0.0,
            "title": str((item.get("tags") or {}).get("title") or ""),
        })
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    return {
        "path": str(path),
        "name": path.name,
        "size": size,
        "container": {
            "format": str(fmt.get("format_name") or "matroska"),
            "duration": duration,
            "title": str((fmt.get("tags") or {}).get("title") or ""),
            "muxing_app": "",
            "writing_app": "",
            "tags": {},
        },
        "tracks": tracks,
        "attachments": attachments,
        "chapters": chapters,
        "chapter_count": len(chapters),
        "warnings": [],
    }


def _enrich_video(path: Path, ffprobe: str, info: dict[str, Any]) -> None:
    """用 ffprobe 补充 HDR / 码率等 mkvmerge 不提供的信息。"""
    data = _run_json([
        ffprobe, "-v", "error", "-print_format", "json",
        "-select_streams", "v", "-show_streams", f"file:{path}",
    ], timeout=60)
    videos = [track for track in info.get("tracks", []) if track.get("type") == "video"]
    for track, stream in zip(videos, data.get("streams") or []):
        if not track.get("hdr"):
            track["hdr"] = _HDR_TRANSFERS.get(str(stream.get("color_transfer") or ""), "")
        if not track.get("bitrate"):
            track["bitrate"] = _int_or_none(stream.get("bit_rate"))
        for side in stream.get("side_data_list") or []:
            if "dovi" in str(side.get("side_data_type") or "").lower():
                track["hdr"] = "Dolby Vision"
        if not track.get("codec_detail"):
            track["codec_detail"] = str(stream.get("profile") or "")


def _estimate_video_bitrate(path: Path, info: dict[str, Any]) -> None:
    """视频轨没有码率时，用文件大小/时长估算整片平均码率并标记为估算值。"""
    videos = [track for track in info.get("tracks", []) if track.get("type") == "video"]
    if not videos or videos[0].get("bitrate"):
        return
    duration = _float_or_none((info.get("container") or {}).get("duration"))
    try:
        size = path.stat().st_size
    except OSError:
        return
    if not duration or duration <= 0 or size <= 0:
        return
    videos[0]["bitrate"] = int(size * 8 / duration)
    videos[0]["bitrate_estimated"] = True


def _extract_chapters(path: Path, mkvextract: str) -> list[dict[str, Any]]:
    """用 mkvextract 读取章节 XML 并解析成列表（临时文件放系统临时目录）。"""
    try:
        result = subprocess.run(
            [mkvextract, "chapters", str(path)],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []
    temp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".xml", delete=False, encoding="utf-8",
        ) as handle:
            handle.write(result.stdout)
            temp_path = Path(handle.name)
        return parse_chapter_file(temp_path)
    except (OSError, ValueError):
        return []
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except OSError:
                pass


def probe_extra_file(path: Path, engine: dict[str, Any]) -> dict[str, Any]:
    """
    探测一个外部素材文件（音频/字幕）的时长与轨道数量。

    :param path: 素材文件
    :param engine: 引擎探测结果
    :return: ``{"duration": 秒或 None, "track_count": 轨道数}``
    """
    ffprobe = _tool_path(engine, "ffprobe")
    if not ffprobe:
        return {"duration": None, "track_count": 1}
    try:
        data = _run_json([
            ffprobe, "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", f"file:{path}",
        ], timeout=60)
    except ProbeError:
        return {"duration": None, "track_count": 1}
    fmt = data.get("format") or {}
    streams = [
        stream for stream in data.get("streams") or []
        if str(stream.get("codec_type") or "") in {"audio", "video", "subtitle"}
    ]
    return {
        "duration": _float_or_none(fmt.get("duration")),
        "track_count": max(1, len(streams)),
    }


def _int_or_none(value: Any) -> Optional[int]:
    """尽力把值转换为 int，失败返回 None。"""
    try:
        if value in (None, ""):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> Optional[float]:
    """尽力把值转换为 float，失败返回 None。"""
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_fps(value: Any) -> Optional[float]:
    """解析 ``30000/1001`` 形式的帧率。"""
    text = str(value or "")
    if "/" in text:
        numerator, _, denominator = text.partition("/")
        try:
            return round(float(numerator) / float(denominator), 3)
        except (ValueError, ZeroDivisionError):
            return None
    return _float_or_none(text)
