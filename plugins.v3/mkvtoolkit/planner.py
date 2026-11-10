"""
编辑计划生成器（dry-run 核心）。

把前端提交的“期望状态”与探测结果做 diff，决定使用 mkvpropedit（只改属性，不重封装）、
mkvmerge（增删轨道/重排/附件，copy 编码）还是 ffmpeg（降级），并生成可预览的命令。

本模块保持纯函数：不启动子进程、不写文件，便于单元测试。
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any, Optional

from .chapters import chapters_to_ffmetadata, chapters_to_ogm

_FONT_MIME = {
    ".ttf": "application/x-truetype-font",
    ".otf": "application/vnd.ms-opentype",
    ".ttc": "application/x-truetype-font",
}

# mkvmerge / mkvpropedit 都不允许用户覆盖输出路径
_FORBIDDEN_ARGS = {"-o", "--output"}


def _attachment_mime(path: Path) -> str:
    """按扩展名给出字体附件的 MIME 类型。"""
    return _FONT_MIME.get(path.suffix.lower(), "application/octet-stream")


def _now_backup_name(source: Path, backup_dir: Path) -> Path:
    """生成不会互相覆盖的备份文件名。"""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return backup_dir / f"{source.stem}.{stamp}{source.suffix}.bak"


def _track_brief(track: dict[str, Any]) -> dict[str, Any]:
    """轨道摘要，用于变更列表展示。"""
    return {
        "id": track.get("id"),
        "type": track.get("type"),
        "codec": track.get("codec"),
        "language": track.get("language"),
        "name": track.get("name"),
    }


def _drop_warning(message: str, code: str = "warn") -> dict[str, Any]:
    """构造一条警告。"""
    return {"level": "warn", "code": code, "message": message}


def _blocker(code: str, message: str) -> dict[str, Any]:
    """构造一条阻塞项。"""
    return {"level": "error", "code": code, "message": message}


def validate_extra_args(extra_args: list[str], source: Path) -> Optional[str]:
    """
    校验用户手写的附加参数，禁止覆盖输出路径或引入输入文件。

    :param extra_args: 附加参数列表
    :param source: 源视频路径（用于拒绝重复输入）
    :return: 出错时返回中文原因，否则 None
    """
    for token in extra_args:
        text = str(token)
        if text in _FORBIDDEN_ARGS or text.startswith("--output="):
            return f"附加参数不允许包含 {text}（输出路径由插件控制）"
        try:
            candidate = Path(text)
            if candidate.is_absolute() and candidate.exists():
                return f"附加参数不允许引用已存在的文件：{text}"
        except OSError:
            continue
        if text == str(source):
            return "附加参数不允许再次引用源文件"
    return None


def _resolve_output(
    source: Path,
    plan: dict[str, Any],
    config: dict[str, Any],
    data_dir: Path,
) -> tuple[Optional[Path], Optional[Path], list[dict[str, Any]]]:
    """
    计算输出路径与备份路径。

    :return: ``(输出路径, 备份路径, 阻塞项)``
    """
    blockers: list[dict[str, Any]] = []
    output_cfg = plan.get("output") or {}
    mode = str(output_cfg.get("mode") or config.get("output_mode") or "dir")
    if mode not in {"dir", "replace"}:
        mode = "dir"
    suffix = str(config.get("output_suffix") or "")
    source_is_mkv = source.suffix.lower() == ".mkv"
    if mode == "replace":
        if not source_is_mkv:
            blockers.append(_blocker(
                "container_replace_unsupported",
                "m2ts/ts 需要重封装为 MKV，不能原地替换，请把输出模式改为「输出到目录」",
            ))
            return None, None, blockers
        if bool(output_cfg.get("no_backup")):
            # 用户显式选择“不保存备份”：直接原地替换，失败/误操作无法回滚
            return source, None, blockers
        backup_dir = Path(str(config.get("backup_dir") or data_dir / "backup")).expanduser()
        backup_path = _now_backup_name(source, backup_dir)
        return source, backup_path, blockers
    output_dir_text = str(output_cfg.get("dir") or config.get("output_dir") or data_dir / "output")
    output_dir = Path(output_dir_text).expanduser()
    # 非 MKV 源（m2ts/ts）输出统一为 .mkv
    target_suffix = source.suffix.lower() if source_is_mkv else ".mkv"
    target = output_dir / f"{source.stem}{suffix}{target_suffix}"
    if target == source:
        blockers.append(_blocker("output_conflict", "输出文件不能与源文件相同，请改用原地替换模式"))
    elif target.exists():
        blockers.append(_blocker("output_exists", f"输出文件已存在：{target}"))
    return target, None, blockers


def _natural_kept(track_ids: list[int], drop: set[int]) -> list[int]:
    """未显式排序时的保留顺序（按文件内原始顺序）。"""
    return [track_id for track_id in track_ids if track_id not in drop]


def build_plan(
    plan: dict[str, Any],
    info: dict[str, Any],
    engine: dict[str, Any],
    config: dict[str, Any],
    data_dir: Path,
    chapters: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """
    生成执行计划。

    :param plan: 前端提交的期望状态
    :param info: ``probe_media()`` 结果
    :param engine: ``EngineManager.detect()`` 结果
    :param config: 插件配置
    :param data_dir: 插件数据目录
    :param chapters: 已解析的导入章节（``mode=import`` 时必填）
    :return: 含 commands/prepares/changes/warnings/blockers 的计划字典
    """
    warnings: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    commands: list[dict[str, Any]] = []
    prepares: list[dict[str, Any]] = []

    source = Path(str(plan.get("path") or ""))
    source_is_mkv = source.suffix.lower() == ".mkv"
    container_remux = not source_is_mkv
    tracks_info = [track for track in info.get("tracks") or [] if track.get("type") in {"video", "audio", "subtitle"}]
    by_id = {int(track["id"]): track for track in tracks_info}
    all_ids = [int(track["id"]) for track in tracks_info]
    video_ids = [int(track["id"]) for track in tracks_info if track["type"] == "video"]

    track_plan = plan.get("tracks") or {}
    drop_raw = track_plan.get("drop") or []
    drop: set[int] = {int(item) for item in drop_raw if _is_int(item)}
    order_raw = track_plan.get("order") or []
    order = [int(item) for item in order_raw if _is_int(item)] if order_raw else _natural_kept(all_ids, drop)
    for track_id in order:
        if track_id not in by_id:
            blockers.append(_blocker("unknown_track", f"轨道 {track_id} 不存在"))
    kept = [track_id for track_id in order if track_id in by_id and track_id not in drop]
    if not kept:
        blockers.append(_blocker("no_tracks", "至少需要保留一条轨道"))
    kept_video = [track_id for track_id in kept if by_id[track_id]["type"] == "video"]
    if not kept_video:
        blockers.append(_blocker("no_video", "至少需要保留一条视频轨"))
    natural = _natural_kept(all_ids, drop)
    reordered = kept != natural

    edits = track_plan.get("edits") or {}
    edit_changes: list[dict[str, Any]] = []
    for key, patch in edits.items():
        try:
            track_id = int(key)
        except (TypeError, ValueError):
            continue
        if track_id not in by_id or track_id in drop:
            continue
        track = by_id[track_id]
        if not isinstance(patch, dict):
            continue
        for field, target_value in patch.items():
            if field not in {"language", "name", "default", "forced"}:
                continue
            old_value = track.get(field)
            if field in {"default", "forced"}:
                new_value = bool(target_value)
            else:
                new_value = str(target_value or "").strip()
            if old_value == new_value:
                continue
            edit_changes.append({
                "id": track_id,
                "field": field,
                "from": old_value,
                "to": new_value,
                "type": track["type"],
            })

    additions_raw = track_plan.get("add") or []
    additions: list[dict[str, Any]] = []
    add_changes: list[dict[str, Any]] = []
    for item in additions_raw:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        file_text = str(item.get("file") or "")
        if kind not in {"subtitle", "audio"} or not file_text:
            continue
        media_path = Path(file_text)
        if not media_path.is_file():
            blockers.append(_blocker("missing_source", f"素材文件不存在：{media_path}"))
            continue
        if media_path.suffix.lower() == ".mkv":
            blockers.append(_blocker("nested_mkv", "新增素材暂不支持其它 MKV 容器，请提供音频或字幕文件"))
            continue
        addition = {
            "kind": kind,
            "file": str(media_path),
            "name": media_path.name,
            "language": str(item.get("language") or "und"),
            "track_name": str(item.get("name") or ""),
            "default": bool(item.get("default")),
            "forced": bool(item.get("forced")),
            "encoding": str(item.get("encoding") or "auto"),
            "sync_ms": int(item.get("sync_ms") or 0) if _is_int(item.get("sync_ms")) else 0,
            "duration": _float_or_none(item.get("duration")),
            "size": _int_or_none(item.get("size")) or media_path.stat().st_size,
        }
        additions.append(addition)
        add_changes.append({
            "kind": kind,
            "file": media_path.name,
            "name": addition["track_name"] or media_path.stem,
            "language": addition["language"],
        })

    attachments_add_raw = track_plan.get("attachments_add") or []
    attachments_add: list[dict[str, Any]] = []
    for item in attachments_add_raw:
        media_path = Path(str(item or ""))
        if not media_path.is_file():
            blockers.append(_blocker("missing_attachment", f"附件不存在：{media_path}"))
            continue
        if media_path.suffix.lower() not in _FONT_MIME:
            blockers.append(_blocker("bad_attachment", "附件只允许字体文件（ttf/otf/ttc）"))
            continue
        attachments_add.append({"file": str(media_path), "mime": _attachment_mime(media_path), "size": media_path.stat().st_size})
    attachments_drop_names = [str(item) for item in (track_plan.get("attachments_drop") or []) if str(item)]
    attachments_drop = [
        attachment for attachment in info.get("attachments") or []
        if str(attachment.get("name")) in attachments_drop_names
    ]

    chapters_cfg = plan.get("chapters") or {}
    chapter_mode = str(chapters_cfg.get("mode") or "keep")
    if chapter_mode not in {"keep", "clear", "import"}:
        chapter_mode = "keep"
    if chapter_mode == "import":
        if not chapters:
            blockers.append(_blocker("chapters_missing", "未提供或无法解析章节文件"))
        else:
            prepares.append({
                "name": "chapters-ogm.xml",
                "content": chapters_to_ogm(chapters),
            })
            prepares.append({
                "name": "chapters-ffmetadata.txt",
                "content": chapters_to_ffmetadata(chapters),
            })
    title = str(plan.get("title") or "").strip()

    output_path, backup_path, output_blockers = _resolve_output(source, plan, config, data_dir)
    blockers.extend(output_blockers)
    if output_path is None:
        return _empty_result(blockers)

    output_cfg = plan.get("output") or {}
    requested_mode = str(output_cfg.get("mode") or config.get("output_mode") or "dir")
    no_backup = requested_mode == "replace" and bool(output_cfg.get("no_backup"))
    if no_backup:
        warnings.append(_drop_warning(
            "已关闭临时备份：原地替换失败时无法从备份恢复源文件",
            code="no_backup",
        ))

    mode = str(engine.get("mode") or "none")
    mkvmerge_ok = bool((engine.get("mkvmerge") or {}).get("ok"))
    propedit_ok = bool((engine.get("mkvpropedit") or {}).get("ok"))
    ffmpeg_ok = bool((engine.get("ffmpeg") or {}).get("ok")) and bool((engine.get("ffprobe") or {}).get("ok"))
    allow_fallback = bool(config.get("allow_ffmpeg_fallback"))

    extra_args = [str(item) for item in (plan.get("extra_args") or []) if str(item).strip()]
    has_extra_args = bool(extra_args)

    structural = bool(drop) or bool(additions) or reordered or container_remux or has_extra_args
    if not any([
        structural, edit_changes, attachments_add, attachments_drop,
        chapter_mode != "keep", title,
    ]):
        blockers.append(_blocker("nothing_to_do", "没有任何修改，请先调整轨道、字幕、附件或章节"))

    if container_remux:
        # m2ts/ts 必须先重封装成 MKV，mkvpropedit 无法处理
        if mkvmerge_ok:
            chosen = "mkvmerge"
        elif ffmpeg_ok and allow_fallback:
            chosen = "ffmpeg"
        else:
            chosen = "none"
    elif structural and mkvmerge_ok:
        chosen = "mkvmerge"
    elif not structural and propedit_ok:
        chosen = "mkvpropedit"
    elif mkvmerge_ok:
        chosen = "mkvmerge"
    elif propedit_ok and not structural:
        chosen = "mkvpropedit"
    elif ffmpeg_ok and allow_fallback:
        chosen = "ffmpeg"
    else:
        chosen = "none"
    if container_remux:
        warnings.append(_drop_warning(
            f"源文件为 {source.suffix or '非 MKV'}，将重封装为 MKV 输出（视频/音频不重编码）"
        ))
    if chosen == "none":
        if mode == "none":
            blockers.append(_blocker("engine_missing", "未安装 MKVToolNix，请先在设置里安装或指定 mkvmerge 路径"))
        elif not allow_fallback:
            blockers.append(_blocker(
                "engine_missing",
                "当前只有 ffmpeg，未开启“降级执行”；请安装 MKVToolNix 或到设置里开启降级",
            ))
        else:
            blockers.append(_blocker("engine_missing", "没有可用的执行引擎"))
    if attachments_drop and chosen in {"ffmpeg"}:
        blockers.append(_blocker("attachment_drop_unsupported", "降级模式不支持删除附件，请安装 MKVToolNix"))
    if has_extra_args and chosen != "mkvmerge":
        blockers.append(_blocker(
            "extra_args_engine",
            "附加参数只能用于 mkvmerge，请先在设置里安装或指定 mkvmerge 路径",
        ))
    elif has_extra_args:
        warnings.append(_drop_warning("附加参数将追加到 mkvmerge 命令行（按填写顺序）"))
    if chosen == "ffmpeg":
        warnings.append(_drop_warning("当前为 ffmpeg 降级模式：附件/tags/轨道 UID 细节可能丢失"))

    if reordered:
        warnings.append(_drop_warning("轨道顺序将被重排，播放器默认选轨可能变化"))
    if drop:
        warnings.append(_drop_warning(f"将删除 {len(drop)} 条轨道，该操作不可撤销（请确认输出文件无误）"))
    if chapter_mode == "clear":
        warnings.append(_drop_warning("章节将被清空"))
    for addition in additions:
        if addition["kind"] == "subtitle":
            encoding = addition["encoding"]
            if encoding in {"auto", "utf-8"}:
                source_encoding = str(
                    next(
                        (item.get("encoding") for item in (info.get("siblings") or {}).get("subtitles") or []
                         if item.get("path") == addition["file"]),
                        "UTF-8",
                    )
                )
                if source_encoding not in {"UTF-8"}:
                    warnings.append(_drop_warning(f"字幕 {addition['name']} 为 {source_encoding}，将转换为 UTF-8"))
        if addition["kind"] in {"audio", "subtitle"}:
            duration = _float_or_none((info.get("container") or {}).get("duration"))
            add_duration = addition.get("duration")
            tolerance = float(config.get("validation_tolerance") or 2)
            if duration and add_duration and abs(float(add_duration) - float(duration)) > tolerance:
                diff = float(add_duration) - float(duration)
                if addition["kind"] == "audio":
                    warnings.append(_drop_warning(
                        f"音轨 {addition['name']} 与视频时长相差 {diff:+.1f}s，"
                        f"可能不是同一版本；可用 --sync 校正或换文件",
                        code="duration_mismatch",
                    ))
                else:
                    warnings.append(_drop_warning(
                        f"字幕 {addition['name']} 与视频时长相差 {diff:+.1f}s，"
                        f"可能不是同一版本，内封后时间轴会对不上",
                        code="duration_mismatch",
                    ))
    if attachments_drop:
        warnings.append(_drop_warning(f"将删除 {len(attachments_drop)} 个附件（执行时会追加一次 mkvpropedit）"))
    if str(config.get("subtitle_after")) == "delete":
        warnings.append(_drop_warning("内封成功后将删除源外挂字幕文件"))

    extra_error = validate_extra_args(extra_args, source)
    if extra_error:
        blockers.append(_blocker("extra_args", extra_error))

    need_bytes = int(info.get("size") or 0)
    need_bytes += sum(int(item.get("size") or 0) for item in additions)
    need_bytes = int(need_bytes * 1.02)
    free_bytes = _free_space(output_path)
    if output_path != source and free_bytes and free_bytes < need_bytes:
        blockers.append(_blocker(
            "disk_space",
            f"输出目录剩余空间不足：需要约 {_human(need_bytes)}，可用 {_human(free_bytes)}",
        ))

    expected = {
        "video": len(kept_video),
        "audio": len([track_id for track_id in kept if by_id[track_id]["type"] == "audio"])
        + len([item for item in additions if item["kind"] == "audio"]),
        "subtitle": len([track_id for track_id in kept if by_id[track_id]["type"] == "subtitle"])
        + len([item for item in additions if item["kind"] == "subtitle"]),
        "duration": (info.get("container") or {}).get("duration"),
    }

    engine_paths = {
        "mkvmerge": str((engine.get("mkvmerge") or {}).get("path") or ""),
        "mkvpropedit": str((engine.get("mkvpropedit") or {}).get("path") or ""),
        "mkvextract": str((engine.get("mkvextract") or {}).get("path") or ""),
        "ffmpeg": str((engine.get("ffmpeg") or {}).get("path") or ""),
    }
    commands, prepare_more = _build_commands(
        chosen=chosen,
        source=source,
        output_path=output_path,
        info=info,
        by_id=by_id,
        kept=kept,
        drop=drop,
        edit_changes=edit_changes,
        additions=additions,
        attachments_add=attachments_add,
        attachments_drop=attachments_drop,
        chapter_mode=chapter_mode,
        title=title,
        extra_args=extra_args,
        engine_paths=engine_paths,
        config=config,
        plan_order=order_raw,
    )
    prepares.extend(prepare_more)

    changes = {
        "keep": len(kept),
        "drop": [_track_brief(by_id[track_id]) for track_id in sorted(drop) if track_id in by_id],
        "add": add_changes,
        "edit": edit_changes,
        "attachments_add": [Path(item["file"]).name for item in attachments_add],
        "attachments_drop": [item.get("name") for item in attachments_drop],
        "chapters": chapter_mode,
        "title": title,
        "reordered": reordered,
    }
    return {
        "engine": chosen,
        "commands": commands,
        "prepares": prepares,
        "changes": changes,
        "output_path": str(output_path),
        "backup_path": str(backup_path) if backup_path else None,
        "output_mode": "replace" if requested_mode == "replace" else "dir",
        "no_backup": no_backup,
        "warnings": warnings,
        "blockers": blockers,
        "space": {"need": need_bytes, "free": free_bytes},
        "expected": expected,
        "extra_args": extra_args,
    }


def _empty_result(blockers: list[dict[str, Any]]) -> dict[str, Any]:
    """无法生成输出路径时的空结果。"""
    return {
        "engine": "none",
        "commands": [],
        "prepares": [],
        "changes": {},
        "output_path": "",
        "backup_path": None,
        "output_mode": "dir",
        "no_backup": False,
        "warnings": [],
        "blockers": blockers,
        "space": {"need": 0, "free": 0},
        "expected": {},
        "extra_args": [],
    }


def _build_commands(
    *,
    chosen: str,
    source: Path,
    output_path: Path,
    info: dict[str, Any],
    by_id: dict[int, dict[str, Any]],
    kept: list[int],
    drop: set[int],
    edit_changes: list[dict[str, Any]],
    additions: list[dict[str, Any]],
    attachments_add: list[dict[str, Any]],
    attachments_drop: list[dict[str, Any]],
    chapter_mode: str,
    title: str,
    extra_args: list[str],
    engine_paths: dict[str, str],
    config: dict[str, Any],
    plan_order: Optional[list[Any]] = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """按引擎生成命令列表与需要预写的临时文件。"""
    prepares: list[dict[str, Any]] = []
    if chosen == "mkvmerge":
        return _mkvmerge_commands(
            source, output_path, info, by_id, kept, drop, edit_changes, additions,
            attachments_add, attachments_drop, chapter_mode, title, extra_args, engine_paths,
            plan_order=plan_order,
        ), prepares
    if chosen == "mkvpropedit":
        return _propedit_commands(
            source, output_path, by_id, kept, edit_changes, additions,
            attachments_add, attachments_drop, chapter_mode, title, engine_paths,
        ), prepares
    if chosen == "ffmpeg":
        return _ffmpeg_commands(
            source, output_path, info, by_id, kept, drop, edit_changes, additions,
            attachments_add, chapter_mode, title, engine_paths,
        ), prepares
    return [], prepares


def _mkvmerge_commands(
    source: Path, output_path: Path, info: dict[str, Any],
    by_id: dict[int, dict[str, Any]], kept: list[int], drop: set[int],
    edit_changes: list[dict[str, Any]], additions: list[dict[str, Any]],
    attachments_add: list[dict[str, Any]], attachments_drop: list[dict[str, Any]],
    chapter_mode: str, title: str, extra_args: list[str], engine_paths: dict[str, str],
    plan_order: Optional[list[Any]] = None,
) -> list[dict[str, Any]]:
    """生成 mkvmerge 命令（必要时追加 mkvpropedit 删除附件）。"""
    tool = engine_paths["mkvmerge"]
    base_count = len(info.get("tracks") or [])
    video_ids = [track_id for track_id in kept if by_id[track_id]["type"] == "video"]
    audio_ids = [track_id for track_id in kept if by_id[track_id]["type"] == "audio"]
    subtitle_ids = [track_id for track_id in kept if by_id[track_id]["type"] == "subtitle"]
    audio_all = [int(track["id"]) for track in info.get("tracks") or [] if track["type"] == "audio"]
    subtitle_all = [int(track["id"]) for track in info.get("tracks") or [] if track["type"] == "subtitle"]
    video_all = [int(track["id"]) for track in info.get("tracks") or [] if track["type"] == "video"]

    args: list[str] = [tool, "--gui-mode", "-o", "{output}"]
    # 新增素材在全局轨道 ID 中的起始位置（每个输入文件贡献自己的轨道数，仅用于 --track-order）
    new_ids: list[tuple[dict[str, Any], int]] = []
    next_id = base_count
    for addition in additions:
        new_ids.append((addition, next_id))
        next_id += int(addition.get("track_count") or 1)
    new_audio_ids = [new_id for addition, new_id in new_ids if addition["kind"] == "audio"]
    new_subtitle_ids = [new_id for addition, new_id in new_ids if addition["kind"] == "subtitle"]

    # ---- 全局选项（与具体输入文件无关）----
    # 混合顺序：plan_order 里数字表示源轨道，`add:<文件路径>` 表示新增文件；
    # 未列出的源轨道/新增文件按原顺序补到末尾（兼容旧计划）。
    add_index_by_path = {str(addition["file"]): index for index, addition in enumerate(additions)}
    kept_set = set(kept)
    order_tokens: list[str] = []
    seen_orig: set[int] = set()
    seen_add: set[int] = set()
    for token in plan_order or []:
        if isinstance(token, str) and token.startswith("add:"):
            add_index = add_index_by_path.get(token[4:])
            if add_index is None or add_index in seen_add:
                continue
            seen_add.add(add_index)
            order_tokens.append(f"{add_index + 1}:0")
            continue
        if not _is_int(token):
            continue
        track_id = int(token)
        if track_id not in kept_set or track_id in seen_orig:
            continue
        seen_orig.add(track_id)
        order_tokens.append(f"0:{track_id}")
    for track_id in kept:
        if track_id not in seen_orig:
            order_tokens.append(f"0:{track_id}")
    for index in range(len(additions)):
        if index not in seen_add:
            order_tokens.append(f"{index + 1}:0")
    args += ["--track-order", ",".join(order_tokens)]
    for attachment in attachments_add:
        args += ["--attach-file", str(attachment["file"])]
        args += ["--attachment-mime-type", str(attachment["mime"])]
    if chapter_mode == "clear":
        args += ["--no-chapters"]
    elif chapter_mode == "import":
        args += ["--chapters", "{work}/chapters-ogm.xml"]
    if title:
        args += ["--title", title]
    args += extra_args

    # ---- 源文件专属选项：必须紧贴源文件，轨道 ID 为源文件内的 local ID ----
    if not video_ids and video_all:
        args += ["--no-video"]
    elif len(video_ids) < len(video_all):
        args += ["--video-tracks", ",".join(str(item) for item in video_ids)]
    if not audio_ids and audio_all:
        args += ["--no-audio"]
    elif len(audio_ids) < len(audio_all):
        args += ["--audio-tracks", ",".join(str(item) for item in audio_ids)]
    if not subtitle_ids and subtitle_all:
        # 只丢弃源文件里的字幕；新增字幕来自其它输入文件，不受影响
        args += ["--no-subtitles"]
    elif len(subtitle_ids) < len(subtitle_all):
        args += ["--subtitle-tracks", ",".join(str(item) for item in subtitle_ids)]

    # 已有轨道的属性（源文件内 local ID）
    for change in edit_changes:
        track_id = int(change["id"])
        field = change["field"]
        value = change["to"]
        if field == "language":
            args += ["--language", f"{track_id}:{value}"]
        elif field == "name":
            args += ["--track-name", f"{track_id}:{value}"]
        elif field == "default":
            args += ["--default-track-flag", f"{track_id}:{1 if value else 0}"]
        elif field == "forced":
            args += ["--forced-display-flag", f"{track_id}:{1 if value else 0}"]
    args.append(str(source))

    # ---- 新增文件专属选项：放在各自的输入文件之前，ID 用该文件内的 local ID（从 0 开始）----
    for addition in additions:
        local_id = 0
        if addition["kind"] == "subtitle" and addition["encoding"] not in {"auto", "utf-8"}:
            args += ["--sub-charset", f"{local_id}:{addition['encoding']}"]
        args += ["--language", f"{local_id}:{addition['language']}"]
        if addition["track_name"]:
            args += ["--track-name", f"{local_id}:{addition['track_name']}"]
        args += ["--default-track-flag", f"{local_id}:{1 if addition['default'] else 0}"]
        args += ["--forced-display-flag", f"{local_id}:{1 if addition['forced'] else 0}"]
        if addition["sync_ms"]:
            args += ["--sync", f"{local_id}:{addition['sync_ms']}"]
        args.append(str(addition["file"]))

    commands = [_command("mkvmerge", args, output_path)]
    if attachments_drop:
        propedit = engine_paths.get("mkvpropedit") or "mkvpropedit"
        remove_args = [propedit, "{output}"]
        for attachment in attachments_drop:
            # mkvpropedit 的选择器直接使用 mkvmerge -J 输出的附件 ID
            remove_args += ["--delete-attachment", str(int(attachment.get("id", 0)))]
        commands.append(_command("mkvpropedit", remove_args, output_path, weight=0.15))
    return commands


def _propedit_commands(
    source: Path, output_path: Path, by_id: dict[int, dict[str, Any]], kept: list[int],
    edit_changes: list[dict[str, Any]], additions: list[dict[str, Any]],
    attachments_add: list[dict[str, Any]], attachments_drop: list[dict[str, Any]],
    chapter_mode: str, title: str, engine_paths: dict[str, str],
) -> list[dict[str, Any]]:
    """生成“复制 + mkvpropedit”命令（不重封装）。"""
    tool = engine_paths.get("mkvpropedit") or "mkvpropedit"
    commands: list[dict[str, Any]] = [
        {"tool": "copy", "args": [str(source), "{output}"], "display": f"复制 {source.name} 到临时文件", "weight": 1.0},
    ]
    args: list[str] = [tool, "{output}"]
    for change in edit_changes:
        track_no = int(change["id"]) + 1
        field = change["field"]
        value = change["to"]
        if field == "language":
            args += ["--edit", f"track:{track_no}", "--set", f"language={value}"]
        elif field == "name":
            args += ["--edit", f"track:{track_no}", "--set", f"name={value}"]
        elif field == "default":
            args += ["--edit", f"track:{track_no}", "--set", f"flag-default={1 if value else 0}"]
        elif field == "forced":
            args += ["--edit", f"track:{track_no}", "--set", f"flag-forced={1 if value else 0}"]
    if title:
        args += ["--edit", "info", "--set", f"title={title}"]
    if chapter_mode == "clear":
        args += ["--chapters", ""]
    elif chapter_mode == "import":
        args += ["--chapters", "{work}/chapters-ogm.xml"]
    for attachment in attachments_add:
        args += [
            "--attachment-name", Path(attachment["file"]).name,
            "--attachment-mime-type", str(attachment["mime"]),
            "--add-attachment", str(attachment["file"]),
        ]
    for attachment in attachments_drop:
        # mkvpropedit 的选择器直接使用 mkvmerge -J 输出的附件 ID
        args += ["--delete-attachment", str(int(attachment.get("id", 0)))]
    # mkvpropedit 不能新增轨道；上游已保证此路径没有 additions
    commands.append(_command("mkvpropedit", args, output_path, weight=1.0))
    return commands


def _ffmpeg_commands(
    source: Path, output_path: Path, info: dict[str, Any],
    by_id: dict[int, dict[str, Any]], kept: list[int], drop: set[int],
    edit_changes: list[dict[str, Any]], additions: list[dict[str, Any]],
    attachments_add: list[dict[str, Any]], chapter_mode: str, title: str,
    engine_paths: dict[str, str],
) -> list[dict[str, Any]]:
    """生成 ffmpeg 降级命令。"""
    tool = engine_paths.get("ffmpeg") or "ffmpeg"
    args: list[str] = [tool, "-y", "-hide_banner"]
    args += ["-i", str(source)]
    input_index = 1
    for addition in additions:
        if addition["kind"] == "subtitle" and addition["encoding"] not in {"auto", "utf-8"}:
            args += ["-sub_charenc", addition["encoding"]]
        if addition["sync_ms"]:
            args += ["-itsoffset", f"{addition['sync_ms'] / 1000:.3f}"]
        args += ["-i", str(addition["file"])]
        addition["input_index"] = input_index
        input_index += 1
    chapter_input = None
    if chapter_mode == "import":
        args += ["-i", "{work}/chapters-ffmetadata.txt"]
        chapter_input = input_index
        input_index += 1

    output_ordinals = {"video": 0, "audio": 0, "subtitle": 0}
    for track_id in kept:
        track = by_id[track_id]
        local_index = track.get("ff_index")
        if local_index is None:
            local_index = track_id
        args += ["-map", f"0:{local_index}"]
        _append_stream_metadata(args, track, track["type"], output_ordinals[track["type"]])
        output_ordinals[track["type"]] += 1
    for addition in additions:
        stream_type = "a" if addition["kind"] == "audio" else "s"
        args += ["-map", f"{addition['input_index']}:{stream_type}:0"]
        if addition["kind"] == "audio":
            ordinal = output_ordinals["audio"]
            output_ordinals["audio"] += 1
            args += ["-metadata:s:a:" + str(ordinal), f"language={addition['language']}"]
            if addition["track_name"]:
                args += ["-metadata:s:a:" + str(ordinal), f"title={addition['track_name']}"]
            if addition["default"]:
                args += ["-disposition:a:" + str(ordinal), "default"]
        else:
            ordinal = output_ordinals["subtitle"]
            output_ordinals["subtitle"] += 1
            args += ["-metadata:s:s:" + str(ordinal), f"language={addition['language']}"]
            if addition["track_name"]:
                args += ["-metadata:s:s:" + str(ordinal), f"title={addition['track_name']}"]
            if addition["default"]:
                args += ["-disposition:s:" + str(ordinal), "default"]
            if addition["forced"]:
                args += ["-disposition:s:" + str(ordinal), "forced"]
    if chapter_mode == "clear":
        args += ["-map_chapters", "-1"]
    elif chapter_input is not None:
        args += ["-map_chapters", str(chapter_input)]
    if title:
        args += ["-metadata", f"title={title}"]
    for index, attachment in enumerate(attachments_add):
        args += ["-attach", str(attachment["file"])]
        args += [f"-metadata:s:t:{index}", f"mimetype={attachment['mime']}"]
    args += ["-c", "copy"]
    args.append("{output}")
    return [_command("ffmpeg", args, output_path)]


def _append_stream_metadata(args: list[str], track: dict[str, Any], stream_type: str, ordinal: int) -> None:
    """给 ffmpeg 输出流追加语言、名称与 disposition。"""
    short = {"video": "v", "audio": "a", "subtitle": "s"}[stream_type]
    if track.get("language"):
        args += [f"-metadata:s:{short}:{ordinal}", f"language={track['language']}"]
    if track.get("name"):
        args += [f"-metadata:s:{short}:{ordinal}", f"title={track['name']}"]
    if stream_type != "video":
        disposition = []
        if track.get("default"):
            disposition.append("default")
        if track.get("forced"):
            disposition.append("forced")
        if disposition:
            args += [f"-disposition:{short}:{ordinal}", "+".join(disposition)]


def _command(tool: str, args: list[str], output_path: Path, weight: float = 1.0) -> dict[str, Any]:
    """构造一条命令记录（含可展示的命令行）。"""
    display = " ".join(_quote(token) for token in args)
    return {
        "tool": tool,
        "args": args,
        "display": display,
        "weight": weight,
        "output_path": str(output_path),
    }


def _quote(token: str) -> str:
    """需要时给命令行参数加引号，仅用于展示。"""
    if any(ch in token for ch in " \t\"'") and not (token.startswith('"') and token.endswith('"')):
        return '"' + token.replace('"', '\\"') + '"'
    return token


def _free_space(path: Path) -> int:
    """输出路径所在磁盘的可用空间。"""
    try:
        return int(shutil.disk_usage(path.parent if path.parent.exists() else Path("/")).free)
    except OSError:
        return 0


def _human(size: int) -> str:
    """人类可读的字节数。"""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def _is_int(value: Any) -> bool:
    """判断值能否安全转 int。"""
    try:
        int(value)
        return True
    except (TypeError, ValueError):
        return False


def _int_or_none(value: Any) -> Optional[int]:
    """转 int，失败返回 None。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> Optional[float]:
    """转 float，失败返回 None。"""
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
