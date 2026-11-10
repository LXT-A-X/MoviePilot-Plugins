"""
偏移估计（实验功能）：用 ffmpeg 静音检测与字幕时间轴做粗对齐。

- 音频：比较「视频首音轨」与「新增音轨」的静音段边界序列，找最佳平移量。
- 字幕：解析字幕 cue 时间，统计平移后 cue 起点/终点落在语音区间内的比例，取最佳平移量。

不引入 numpy 等新依赖；精度在百毫秒级，只适合“同一内容、不同延迟”的素材。
置信度低时会明确返回 ``reliable=False``，由前端提示用户不要直接采用。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Optional

from .siblings import detect_text_encoding

_SILENCE_START_RE = re.compile(r"silence_start:\s*(-?\d+(?:\.\d+)?)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*(-?\d+(?:\.\d+)?)")
_SRT_TIME_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})"
)
_ASS_TIME_RE = re.compile(r"(\d+):(\d{2}):(\d{2})[.,](\d{1,2})")
_VTT_TIME_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[.](\d{1,3})"
)
_DIALOGUE_PREFIX = "Dialogue:"


def _ffmpeg_output(args: list[str], timeout: int = 300) -> str:
    """执行 ffmpeg 并返回合并后的输出文本。"""
    process = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    return f"{process.stdout or ''}\n{process.stderr or ''}"


def silence_events(
    media: Path,
    ffmpeg: str,
    max_seconds: int = 900,
    noise_db: int = -30,
    min_duration: float = 0.25,
) -> dict[str, list[float]]:
    """
    用 ffmpeg ``silencedetect`` 提取语音/静音边界。

    :param media: 媒体文件
    :param ffmpeg: ffmpeg 路径
    :param max_seconds: 只分析开头多少秒
    :param noise_db: 静音阈值（dB）
    :param min_duration: 最短静音时长（秒）
    :return: ``{"speech_starts": [...], "speech_ends": [...]}``
    """
    output = _ffmpeg_output([
        ffmpeg, "-hide_banner", "-nostats",
        "-t", str(max(30, int(max_seconds))),
        "-i", str(media),
        "-map", "0:a:0",
        "-af", f"silencedetect=noise={noise_db}dB:d={min_duration}",
        "-f", "null", "-",
    ])
    starts = [float(match.group(1)) for match in _SILENCE_START_RE.finditer(output)]
    ends = [float(match.group(1)) for match in _SILENCE_END_RE.finditer(output)]
    speech_starts: list[float] = []
    speech_ends: list[float] = []
    if starts and starts[0] > 0.2:
        speech_starts.append(0.0)
    speech_starts.extend(ends)
    speech_ends.extend(starts)
    return {
        "speech_starts": sorted(round(value, 3) for value in speech_starts),
        "speech_ends": sorted(round(value, 3) for value in speech_ends),
    }


def _score_events(
    reference: list[float],
    candidate: list[float],
    shift: float,
    tolerance: float = 0.45,
) -> int:
    """统计平移后 candidate 与 reference 的匹配事件数。"""
    if not reference or not candidate:
        return 0
    matched = 0
    pointer = 0
    for value in candidate:
        target = value + shift
        while pointer < len(reference) and reference[pointer] < target - tolerance:
            pointer += 1
        if pointer < len(reference) and abs(reference[pointer] - target) <= tolerance:
            matched += 1
    return matched


def _best_shift(
    reference: list[float],
    candidate: list[float],
    search_ms: int,
    step_ms: int,
    tolerance: float = 0.45,
) -> tuple[float, int, int]:
    """
    在 ±search 范围内搜索最佳平移量。

    :return: ``(shift_seconds, matched, total)``
    """
    total = min(len(reference), len(candidate)) or 1
    best_shift, best_score = 0.0, 0
    second_best = 0
    search = max(500, int(search_ms))
    step = max(20, int(step_ms))
    for offset in range(-search, search + 1, step):
        shift = offset / 1000.0
        score = _score_events(reference, candidate, shift, tolerance)
        if score > best_score:
            second_best = best_score
            best_score = score
            best_shift = shift
        elif score > second_best:
            second_best = score
    margin = (best_score - second_best) / total if total else 0.0
    confidence = round(best_score / total, 3) if total else 0.0
    return best_shift, int(confidence * 100), int(margin * 100)


def estimate_audio_offset(
    video: Path,
    audio: Path,
    ffmpeg: str,
    max_seconds: int = 900,
    search_ms: int = 8000,
) -> dict[str, Any]:
    """
    估计新增音轨相对视频音轨需要施加的 ``--sync`` 延迟。

    :param video: 源视频
    :param audio: 新增音频文件
    :param ffmpeg: ffmpeg 路径
    :param max_seconds: 分析时长
    :param search_ms: 搜索范围（毫秒）
    :return: 估计结果
    """
    reference = silence_events(video, ffmpeg, max_seconds)
    candidate = silence_events(audio, ffmpeg, max_seconds)
    ref_points = sorted(reference["speech_starts"] + reference["speech_ends"])
    cand_points = sorted(candidate["speech_starts"] + candidate["speech_ends"])
    shift, confidence, margin = _best_shift(ref_points, cand_points, search_ms, 50)
    reliable = confidence >= 45 and margin >= 10
    return {
        "kind": "audio",
        "offset_ms": int(round(shift * 1000)),
        "confidence": confidence,
        "margin": margin,
        "reliable": reliable,
        "method": "silence-events",
        "detail": {
            "reference_events": len(ref_points),
            "candidate_events": len(cand_points),
            "analyzed_seconds": max_seconds,
        },
        "hint": (
            f"建议 --sync {int(round(shift * 1000))}"
            if reliable else "静音边界匹配度低，可能是不同剪辑/版本，不建议直接采用"
        ),
    }


def _decode_subtitle_text(path: Path) -> str:
    """按探测到的编码读取字幕文本。"""
    encoding = detect_text_encoding(path)
    codec = {"UTF-8": "utf-8", "GB18030": "gb18030", "BIG5": "big5"}.get(encoding, "utf-8")
    try:
        return path.read_text(encoding=codec, errors="replace")
    except (OSError, LookupError):
        return path.read_text(encoding="utf-8", errors="replace")


def parse_subtitle_times(path: Path) -> list[tuple[float, float]]:
    """
    解析 srt / ass / ssa / vtt 的 cue 时间。

    :param path: 字幕文件
    :return: ``[(start, end), ...]``
    """
    text = _decode_subtitle_text(path)
    suffix = path.suffix.lower()
    cues: list[tuple[float, float]] = []
    if suffix in {".ass", ".ssa"}:
        for line in text.splitlines():
            if not line.strip().startswith(_DIALOGUE_PREFIX):
                continue
            parts = line.split(",", 9)
            if len(parts) < 3:
                continue
            start = _ass_seconds(parts[1])
            end = _ass_seconds(parts[2])
            if start is not None and end is not None and end >= start:
                cues.append((start, end))
        return cues
    pattern = _SRT_TIME_RE if suffix == ".srt" else _VTT_TIME_RE
    for match in pattern.finditer(text):
        start = _hms_seconds(*match.groups()[:4])
        end = _hms_seconds(*match.groups()[4:])
        if end >= start:
            cues.append((start, end))
    return cues


def _ass_seconds(text: str) -> Optional[float]:
    """解析 ASS 时间 ``H:MM:SS.cc``。"""
    match = _ASS_TIME_RE.search(text.strip())
    if not match:
        return None
    hours, minutes, seconds, fraction = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(fraction) / 100


def _hms_seconds(hours: str, minutes: str, seconds: str, fraction: str) -> float:
    """解析 HH:MM:SS.fff。"""
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(fraction) / (10 ** len(fraction))
    )


def _speech_ratio(cues: list[tuple[float, float]], intervals: list[tuple[float, float]], shift: float) -> float:
    """统计平移后 cue 起点落在语音区间内的比例。"""
    if not cues or not intervals:
        return 0.0
    hits = 0
    index = 0
    for start, _end in cues:
        target = start + shift
        while index < len(intervals) and intervals[index][1] < target:
            index += 1
        if index < len(intervals) and intervals[index][0] <= target <= intervals[index][1]:
            hits += 1
    return hits / len(cues)


def _speech_intervals(events: dict[str, list[float]]) -> list[tuple[float, float]]:
    """把语音起点/终点配对成区间。"""
    starts = events.get("speech_starts") or []
    ends = events.get("speech_ends") or []
    intervals: list[tuple[float, float]] = []
    for start in starts:
        later = [end for end in ends if end > start]
        if later:
            intervals.append((start, min(later)))
    return intervals


def estimate_subtitle_offset(
    video: Path,
    subtitle: Path,
    ffmpeg: str,
    max_seconds: int = 900,
    search_ms: int = 15000,
) -> dict[str, Any]:
    """
    估计字幕相对视频需要施加的 ``--sync`` 延迟。

    :param video: 源视频
    :param subtitle: 字幕文件
    :param ffmpeg: ffmpeg 路径
    :param max_seconds: 分析时长
    :param search_ms: 搜索范围（毫秒）
    :return: 估计结果
    """
    cues = parse_subtitle_times(subtitle)
    if not cues:
        return {
            "kind": "subtitle",
            "offset_ms": 0,
            "confidence": 0,
            "reliable": False,
            "method": "speech-ratio",
            "hint": "字幕时间轴解析失败（支持 srt/ass/ssa/vtt）",
            "detail": {"cues": 0},
        }
    events = silence_events(video, ffmpeg, max_seconds)
    intervals = _speech_intervals(events)
    if not intervals:
        return {
            "kind": "subtitle",
            "offset_ms": 0,
            "confidence": 0,
            "reliable": False,
            "method": "speech-ratio",
            "hint": "视频音轨未检测到可用语音区间，无法估计",
            "detail": {"cues": len(cues), "speech_intervals": 0},
        }
    search = max(1000, int(search_ms))
    best_shift, best_score = 0.0, 0.0
    for offset in range(-search, search + 1, 250):
        shift = offset / 1000.0
        score = _speech_ratio(cues, intervals, shift)
        if score > best_score:
            best_score, best_shift = score, shift
    baseline = _speech_ratio(cues, intervals, 0.0)
    improvement = max(0.0, best_score - baseline)
    confidence = max(0, min(100, int(round(baseline * 100))))
    margin = max(0, min(100, int(round(improvement * 100))))
    offset_ms = int(round(best_shift * 1000))
    detail = {
        "cues": len(cues),
        "speech_intervals": len(intervals),
        "baseline_score": round(baseline, 3),
        "analyzed_seconds": max_seconds,
    }
    # 保守策略：原本就对齐（或只有微小偏移）时，不要给出 200~300ms 的“假偏移”
    if baseline >= 0.6 and improvement < 0.12:
        return {
            "kind": "subtitle",
            "offset_ms": 0,
            "confidence": confidence,
            "margin": margin,
            "reliable": True,
            "method": "speech-ratio",
            "detail": detail,
            "hint": "字幕时间轴已对齐，无需 --sync",
        }
    if abs(offset_ms) < 400:
        offset_ms = 0
    reliable = best_score >= 0.65 and improvement >= 0.12 and abs(offset_ms) >= 400
    return {
        "kind": "subtitle",
        "offset_ms": offset_ms,
        "confidence": confidence,
        "margin": margin,
        "reliable": reliable,
        "method": "speech-ratio",
        "detail": detail,
        "hint": (
            f"建议 --sync {offset_ms}" if reliable else "匹配度低，字幕可能不是同一版本或时间轴正常，不建议直接采用"
        ),
    }
