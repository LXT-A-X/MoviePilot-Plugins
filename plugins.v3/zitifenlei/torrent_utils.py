"""种子字体截取的下载器适配层。

原则：
- 只读下载器：只调用 get_torrents / get_files / get_completed_torrents，
  不改优先级、不暂停、不删种、不移动文件
- 不遍历下载目录：只用「种子文件清单 + save_path」定位具体文件
- 下载器登录/重连/超时全部交给 MoviePilot 的下载器模块，插件不保存任何下载器凭据
- 各下载器字段口径不同（qBittorrent progress 0~1、rTorrent 0~100、
  Transmission bytesCompleted/size），统一归一成 0~1

本模块保持纯函数风格，方便单测在无 MoviePilot 宿主的环境下直接调用。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import archive_utils as arch
from font_utils import FONT_EXTENSIONS

# 进度视为「已下完」的阈值：qB 返回 1.0，rTorrent 按分块计算可能有 99.9%
PROGRESS_DONE = 0.99


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """兼容 dict 与对象属性的读取。"""
    if isinstance(obj, dict):
        return obj.get(key, default)
    try:
        return getattr(obj, key, default)
    except Exception:
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def get_downloader_service(name: str) -> Optional[Any]:
    """按名称取得 MoviePilot 的下载器服务（ServiceInfo）。

    V3 路径 app.application.downloader；V2 兼容 app.helper.downloader。
    宿主不可用或名称不存在时返回 None，调用方负责降级。
    """
    if not name:
        return None
    helper_cls = _downloader_helper_cls()
    if helper_cls is None:
        return None
    try:
        return helper_cls().get_service(name=name)
    except Exception:
        return None


def _downloader_helper_cls() -> Optional[Any]:
    """懒加载 MP 的 DownloaderHelper 类（宿主不存在时返回 None，便于纯单测环境）。"""
    try:
        from app.application.downloader import DownloaderHelper  # MoviePilot V3

        return DownloaderHelper
    except Exception:
        try:
            from app.helper.downloader import DownloaderHelper  # MoviePilot V2 兼容

            return DownloaderHelper
        except Exception:
            return None


def list_downloaders() -> List[Dict[str, str]]:
    """列出已配置并启用的下载器： [{name, type}]。"""
    helper_cls = _downloader_helper_cls()
    if helper_cls is None:
        return []
    try:
        configs = helper_cls().get_configs() or {}
    except Exception:
        return []
    result: List[Dict[str, str]] = []
    for name, conf in (configs or {}).items():
        try:
            enabled = getattr(conf, "enabled", True)
            if enabled is False:
                continue
            result.append({"name": str(name), "type": str(getattr(conf, "type", "") or "")})
        except Exception:
            continue
    return result



def service_instance(service: Any) -> Optional[Any]:
    """取 ServiceInfo 里的下载器实例（已登录的客户端封装）。"""
    return getattr(service, "instance", None) if service else None


def service_type(service: Any) -> str:
    return str(getattr(service, "type", "") or "")


def normalize_progress(file_obj: Any) -> float:
    """把各下载器的进度口径统一成 0~1。"""
    raw = _get(file_obj, "progress", None)
    if raw is not None:
        p = _as_float(raw, -1.0)
        if p >= 0:
            return p / 100.0 if p > 1.0 else p
    size = _as_int(_get(file_obj, "size", 0), 0)
    done = _get(file_obj, "bytesCompleted", None)
    if done is None:
        done = _get(file_obj, "completed", None)
    if size > 0 and done is not None:
        return _as_float(done, 0.0) / float(size)
    if bool(_get(file_obj, "is_seed", False)):
        return 1.0
    return 0.0


def normalize_file(file_obj: Any) -> Dict[str, Any]:
    """种子内单个文件 → {name, size, progress, index}。"""
    name = str(_get(file_obj, "name", "") or _get(file_obj, "path", "") or "")
    index = _get(file_obj, "index", None)
    if index is None:
        index = _get(file_obj, "id", 0)
    return {
        "name": name.replace("\\", "/").lstrip("/"),
        "size": _as_int(_get(file_obj, "size", 0), 0),
        "progress": normalize_progress(file_obj),
        "index": _as_int(index, 0),
    }


def list_files(instance: Any, torrent_hash: str) -> List[Dict[str, Any]]:
    """读取种子文件清单并归一；下载器不可用/查询失败返回空列表。"""
    if instance is None or not torrent_hash:
        return []
    try:
        files = instance.get_files(torrent_hash)
    except Exception:
        return []
    return [normalize_file(f) for f in (files or [])]


def _torrent_items(raw: Any) -> List[Any]:
    """get_torrents 的返回兼容：qBittorrent 模块返回 (list, error) 元组，其它返回列表。"""
    if isinstance(raw, tuple) and len(raw) == 2:
        items, _err = raw
        return list(items or [])
    return list(raw or [])


def torrent_meta(instance: Any, torrent_hash: str) -> Dict[str, Any]:
    """读取种子基础信息：保存路径、名称、完成时间。"""
    if instance is None or not torrent_hash:
        return {}
    try:
        items = _torrent_items(instance.get_torrents(ids=torrent_hash))
    except Exception:
        return {}
    if not items:
        return {}
    info = items[0]
    save_path = str(_get(info, "save_path", "") or _get(info, "download_path", "") or "")
    return {
        "hash": str(_get(info, "hash", "") or torrent_hash),
        "name": str(_get(info, "name", "") or ""),
        "save_path": save_path,
        "completion_on": _as_int(_get(info, "completion_on", 0), 0),
        "added_on": _as_int(_get(info, "added_on", 0), 0),
    }


def list_completed(instance: Any) -> List[Dict[str, Any]]:
    """列出已完成种子（兜底扫描用）；失败返回空列表。"""
    if instance is None:
        return []
    try:
        items = instance.get_completed_torrents()
    except Exception:
        items = None
    if items is None:
        try:
            items = _torrent_items(instance.get_torrents(status=["seeding", "completed"]))
        except Exception:
            return []
    result: List[Dict[str, Any]] = []
    for info in items or []:
        h = str(_get(info, "hash", "") or "")
        if not h:
            continue
        result.append(
            {
                "hash": h,
                "name": str(_get(info, "name", "") or ""),
                "save_path": str(_get(info, "save_path", "") or _get(info, "download_path", "") or ""),
                "completion_on": _as_int(_get(info, "completion_on", 0), 0),
            }
        )
    return result


def map_download_path(save_path: str, service: Any, downloader_name: str) -> str:
    """把下载器端路径映射成本地可访问路径（复用 MP 下载器模块的 path_mapping）。"""
    if not save_path:
        return ""
    mapped = save_path
    module = getattr(service, "module", None) if service else None
    if module is not None and hasattr(module, "normalize_return_path"):
        try:
            mapped = str(module.normalize_return_path(Path(save_path), downloader_name) or save_path)
        except Exception:
            mapped = save_path
    return mapped.removeprefix("local:")


def match_keywords(rel_path: str, keywords: str) -> bool:
    """压缩包是否命中关键词（不分大小写，逗号/顿号/空格分隔）。"""
    text = (rel_path or "").casefold()
    for word in str(keywords or "").replace("，", ",").replace("、", ",").split(","):
        w = word.strip().casefold()
        if w and w in text:
            return True
    return False


def pick_candidates(
    files: Sequence[Dict[str, Any]],
    root: str,
    keywords: str,
    max_file_mb: int,
    max_files: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """从文件清单里挑出可直接复制的字体文件与字体压缩包。

    返回 (候选列表, 统计)。候选每项：
      {name, abs_path, size, kind: font|archive, member: 压缩包后缀}
    只挑 progress≈1 的文件——没下完的文件不碰。
    """
    stats = {"scanned": 0, "pending": 0, "too_large": 0, "not_match": 0}
    candidates: List[Dict[str, Any]] = []
    supported_archives = set(arch.archive_extensions())
    limit_bytes = max(1, int(max_file_mb)) * 1024 * 1024
    for item in files:
        stats["scanned"] += 1
        name = str(item.get("name") or "")
        if not name:
            continue
        if item.get("progress", 0) < PROGRESS_DONE:
            stats["pending"] += 1
            continue
        size = _as_int(item.get("size", 0), 0)
        if size > limit_bytes:
            stats["too_large"] += 1
            continue
        suffix = Path(name).suffix.lower()
        kind = ""
        if suffix in set(FONT_EXTENSIONS):
            kind = "font"
        elif suffix in supported_archives and match_keywords(name, keywords):
            kind = "archive"
        if not kind:
            stats["not_match"] += 1
            continue
        abs_path = str((Path(root) / name)) if root else ""
        candidates.append(
            {"name": name, "abs_path": abs_path, "size": size, "kind": kind}
        )
        if len(candidates) >= max(1, int(max_files)):
            break
    return candidates, stats


def describe_extract_tools(refresh: bool = False) -> Dict[str, Any]:
    """当前环境解压能力摘要（设置页状态行 / 依赖检测共用）。"""
    tools = arch.detect_extract_tools(refresh=refresh)
    return {
        "zip": True,
        "seven_zip": bool(tools.get("7z") or tools.get("7za") or tools.get("unar")),
        "rar": any(tools.get(k) for k in ("7z", "7za", "unar", "unrar", "bsdtar")),
        "tools": sorted(tools.keys()),
        "extensions": list(arch.archive_extensions()),
    }
