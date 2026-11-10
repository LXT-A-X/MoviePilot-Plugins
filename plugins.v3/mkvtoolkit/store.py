"""
MkvToolkit 的配置默认值、数据目录以及队列/历史的 JSON 持久化。

插件只使用 ``get_data_path()`` 返回的目录保存运行数据，不写插件源码目录；
队列与历史都保持为可序列化字典，避免依赖宿主 ORM。
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

# 文件名里的语言标记到 Matroska/ISO-639-2 语言码的默认映射
DEFAULT_LANGUAGE_MAP: dict[str, str] = {
    "zh": "chi",
    "chs": "chi",
    "cht": "chi",
    "sc": "chi",
    "tc": "chi",
    "简": "chi",
    "繁": "chi",
    "中文": "chi",
    "国语": "chi",
    "国配": "chi",
    "普通话": "chi",
    "mandarin": "chi",
    "jpn": "jpn",
    "jp": "jpn",
    "日语": "jpn",
    "japanese": "jpn",
    "eng": "eng",
    "en": "eng",
    "英语": "eng",
    "english": "eng",
    "yue": "yue",
    "粤": "yue",
    "粤语": "yue",
    "cantonese": "yue",
    "kor": "kor",
    "ko": "kor",
    "韩语": "kor",
    "korean": "kor",
}

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "roots": [],
    "engine_mode": "auto",
    "mkvmerge_path": "",
    "mkvpropedit_path": "",
    "mkvextract_path": "",
    "ffmpeg_path": "",
    "output_mode": "dir",
    "output_dir": "",
    "output_suffix": "",
    "backup_dir": "",
    "backup_keep": 3,
    "subtitle_after": "keep",
    "subtitle_encoding": "auto",
    "language_map": dict(DEFAULT_LANGUAGE_MAP),
    "concurrency": 1,
    "validation_tolerance": 2.0,
    "strict_duration_check": False,
    "history_keep": 200,
    "upload_max_mb": 50,
    "allow_ffmpeg_fallback": False,
    "auto_subtitle": False,
    "auto_audio": False,
    "auto_fonts": False,
}

# 允许的取值，非法值回退默认
_ENUMS: dict[str, set[str]] = {
    "engine_mode": {"auto", "mkvmerge", "ffmpeg"},
    "output_mode": {"dir", "replace"},
    "subtitle_after": {"keep", "archive", "delete"},
    "subtitle_encoding": {"auto", "utf-8", "gbk", "big5"},
}

_INT_LIMITS: dict[str, tuple[int, int]] = {
    "backup_keep": (0, 20),
    "concurrency": (1, 3),
    "history_keep": (10, 1000),
    "upload_max_mb": (1, 10240),
}


def _as_bool(value: Any, default: bool) -> bool:
    """把配置里的真假值转换成 bool。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "是"}
    return default


def _as_list(value: Any) -> list[str]:
    """把字符串或列表统一成去空的字符串列表。"""
    if isinstance(value, str):
        items = value.replace("\n", ";").split(";")
    elif isinstance(value, (list, tuple)):
        items = [str(item) for item in value]
    else:
        items = []
    result: list[str] = []
    for item in items:
        text = item.strip()
        if text and text not in result:
            result.append(text)
    return result


def normalize_config(raw: Optional[dict[str, Any]]) -> dict[str, Any]:
    """
    合并默认值并做类型与范围校验，保证运行期配置始终可用。

    :param raw: 宿主保存的原始配置字典
    :return: 规范化后的完整配置
    """
    cfg = dict(DEFAULT_CONFIG)
    if isinstance(raw, dict):
        cfg.update({key: value for key, value in raw.items() if key in DEFAULT_CONFIG})
    cfg["enabled"] = _as_bool(cfg.get("enabled"), True)
    cfg["roots"] = _as_list(cfg.get("roots"))
    for key in ("mkvmerge_path", "mkvpropedit_path", "mkvextract_path",
                "ffmpeg_path", "output_dir", "backup_dir", "output_suffix"):
        cfg[key] = str(cfg.get(key) or "").strip()
    for key, allowed in _ENUMS.items():
        if cfg.get(key) not in allowed:
            cfg[key] = DEFAULT_CONFIG[key]
    for key, (low, high) in _INT_LIMITS.items():
        try:
            value = int(cfg.get(key, DEFAULT_CONFIG[key]))
        except (TypeError, ValueError):
            value = int(DEFAULT_CONFIG[key])
        cfg[key] = max(low, min(high, value))
    try:
        tolerance = float(cfg.get("validation_tolerance", 2.0))
    except (TypeError, ValueError):
        tolerance = 2.0
    cfg["validation_tolerance"] = max(0.5, min(60.0, tolerance))
    cfg["allow_ffmpeg_fallback"] = _as_bool(cfg.get("allow_ffmpeg_fallback"), False)
    cfg["strict_duration_check"] = _as_bool(cfg.get("strict_duration_check"), False)
    cfg["auto_subtitle"] = _as_bool(cfg.get("auto_subtitle"), False)
    cfg["auto_audio"] = _as_bool(cfg.get("auto_audio"), False)
    cfg["auto_fonts"] = _as_bool(cfg.get("auto_fonts"), False)

    language_map: dict[str, str] = dict(DEFAULT_LANGUAGE_MAP)
    incoming = cfg.get("language_map")
    if isinstance(incoming, dict):
        for token, code in incoming.items():
            token_text = str(token).strip().lower()
            code_text = str(code).strip().lower()
            if token_text and code_text:
                language_map[token_text] = code_text
    cfg["language_map"] = language_map
    return cfg


def new_id(prefix: str = "") -> str:
    """
    生成稳定可读的短 ID（时间 + 随机），用于任务与历史记录。

    :param prefix: 可选前缀
    :return: 形如 ``20261101-233000-ab12cd`` 的字符串
    """
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return f"{prefix}{stamp}-{uuid.uuid4().hex[:6]}"


def _atomic_write_json(path: Path, data: Any) -> None:
    """
    原子写入 JSON 文件，避免进程中断留下半截内容。

    :param path: 目标文件
    :param data: 可序列化对象
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path, default: Any) -> Any:
    """
    读取 JSON 文件，不存在或损坏时返回默认值。

    :param path: 源文件
    :param default: 兜底值
    :return: 解析结果
    """
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


class DataStore:
    """
    插件数据目录访问入口：队列、历史、上传文件、引擎二进制。

    :param data_dir: ``get_data_path()`` 返回的插件数据目录
    :param history_keep: 历史保留条数
    """

    def __init__(self, data_dir: Path, history_keep: int = 200) -> None:
        self.data_dir = Path(data_dir)
        self.history_keep = max(10, int(history_keep))
        self.uploads_dir = self.data_dir / "uploads"
        self.bin_dir = self.data_dir / "bin"
        self.backup_dir = self.data_dir / "backup"
        self.output_dir = self.data_dir / "output"
        self.work_dir = self.data_dir / "work"
        for directory in (self.uploads_dir, self.bin_dir, self.backup_dir,
                          self.output_dir, self.work_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ 队列
    @property
    def queue_file(self) -> Path:
        """队列持久化文件。"""
        return self.data_dir / "queue.json"

    def load_queue(self) -> dict[str, Any]:
        """读取持久化的等待队列与暂停状态。"""
        with self._lock:
            data = _read_json(self.queue_file, {})
        if not isinstance(data, dict):
            data = {}
        jobs = data.get("jobs")
        return {
            "paused": bool(data.get("paused")),
            "jobs": jobs if isinstance(jobs, list) else [],
        }

    def save_queue(self, paused: bool, jobs: list[dict[str, Any]]) -> None:
        """保存等待队列与暂停状态。"""
        with self._lock:
            _atomic_write_json(self.queue_file, {"paused": paused, "jobs": jobs})

    # ------------------------------------------------------------------ 历史
    @property
    def history_file(self) -> Path:
        """历史持久化文件。"""
        return self.data_dir / "history.json"

    def load_history(self) -> list[dict[str, Any]]:
        """读取历史记录（新的在前）。"""
        with self._lock:
            data = _read_json(self.history_file, [])
        return data if isinstance(data, list) else []

    def append_history(self, item: dict[str, Any]) -> None:
        """追加一条历史并裁剪到配置上限。"""
        with self._lock:
            items = self.load_history()
            items.insert(0, item)
            if len(items) > self.history_keep:
                items = items[: self.history_keep]
            _atomic_write_json(self.history_file, items)

    def update_history(self, item_id: str, patch: dict[str, Any]) -> bool:
        """按 ID 更新历史记录，返回是否命中。"""
        with self._lock:
            items = self.load_history()
            for item in items:
                if item.get("id") == item_id:
                    item.update(patch)
                    _atomic_write_json(self.history_file, items)
                    return True
        return False

    def delete_history(self, item_id: str) -> bool:
        """删除一条历史记录，返回是否命中。"""
        with self._lock:
            items = self.load_history()
            kept = [item for item in items if item.get("id") != item_id]
            if len(kept) == len(items):
                return False
            _atomic_write_json(self.history_file, kept)
            return True

    def clear_history(self) -> int:
        """清空历史记录，返回删除条数。"""
        with self._lock:
            items = self.load_history()
            _atomic_write_json(self.history_file, [])
            return len(items)

    # ------------------------------------------------------------------ 文件
    def clear_uploads(self) -> None:
        """清空上传目录里的旧素材。"""
        for path in self.uploads_dir.glob("*"):
            try:
                if path.is_file():
                    path.unlink()
            except OSError:
                continue

    def save_upload(self, filename: str, data: bytes) -> Path:
        """
        把上传内容写入上传目录，文件名做安全处理并加随机前缀防冲突。

        :param filename: 原始文件名
        :param data: 文件内容
        :return: 落盘路径
        """
        safe = "".join(ch for ch in Path(filename).name if ch not in '\\/:*?"<>|').strip()
        safe = safe or "upload.bin"
        target = self.uploads_dir / f"{uuid.uuid4().hex[:8]}_{safe}"
        target.write_bytes(data)
        return target
