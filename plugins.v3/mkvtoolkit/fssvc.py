"""
文件系统访问：根目录白名单、目录浏览、素材路径校验与上传落盘。

所有对外暴露的路径都必须落在配置的媒体根目录内；唯一的例外是插件自己的
上传目录与输出/备份目录，它们由插件管理并显式放行。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Iterable, Optional

VIDEO_EXT = {".mkv", ".m2ts"}
SUBTITLE_EXT = {".srt", ".ass", ".ssa", ".vtt"}
AUDIO_EXT = {".aac", ".flac", ".mka", ".ac3", ".eac3", ".dts", ".mp3", ".m4a", ".opus", ".wav"}
FONT_EXT = {".ttf", ".otf", ".ttc"}
ARCHIVE_EXT = {".zip", ".7z", ".rar", ".tar", ".tgz", ".tbz2", ".txz",
               ".tar.gz", ".tar.bz2", ".tar.xz"}

KIND_EXT: dict[str, set[str]] = {
    "video": VIDEO_EXT,
    "subtitle": SUBTITLE_EXT,
    "audio": AUDIO_EXT,
    "font": FONT_EXT,
    "archive": ARCHIVE_EXT,
    "all": VIDEO_EXT | SUBTITLE_EXT | AUDIO_EXT | FONT_EXT | ARCHIVE_EXT,
}


class HistoryMatchError(ValueError):
    """路径不满足安全约束时抛出的业务异常。"""


class FileSystemService:
    """
    受根目录约束的文件浏览与素材校验。

    :param roots: 配置里的媒体根目录列表
    :param uploads_dir: 插件上传目录（允许作为素材来源）
    """

    def __init__(self, roots: Iterable[str], uploads_dir: Optional[Path] = None) -> None:
        self.roots = self._normalize_roots(roots)
        self.uploads_dir = Path(uploads_dir).resolve() if uploads_dir else None

    @staticmethod
    def _normalize_roots(roots: Iterable[str]) -> list[Path]:
        """解析并去重根目录，丢弃不存在或不是目录的项。"""
        result: list[Path] = []
        seen: set[str] = set()
        for item in roots or []:
            text = str(item or "").strip()
            if not text:
                continue
            try:
                path = Path(text).expanduser().resolve()
            except OSError:
                continue
            if not path.is_dir():
                continue
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            result.append(path)
        return result

    def root_texts(self) -> list[str]:
        """返回根目录的字符串形式，供前端展示。"""
        return [str(root) for root in self.roots]

    def _inside(self, path: Path, base: Path) -> bool:
        """判断路径是否在 base 之内（已 resolve）。"""
        try:
            return path == base or path.is_relative_to(base)
        except (OSError, ValueError):
            return False

    def is_within_roots(self, path: Path) -> bool:
        """判断路径是否落在任一媒体根目录内。"""
        candidate = Path(path).resolve()
        return any(self._inside(candidate, root) for root in self.roots)

    def is_upload(self, path: Path) -> bool:
        """判断路径是否在插件上传目录内。"""
        if self.uploads_dir is None:
            return False
        return self._inside(Path(path).resolve(), self.uploads_dir)

    def resolve_inside(self, path: str | Path) -> Path:
        """
        校验并解析一个媒体根目录内的路径。

        :param path: 用户提供的路径
        :return: 解析后的绝对路径
        :raises HistoryMatchError: 路径不存在、越界或不是目录
        """
        candidate = Path(str(path)).expanduser()
        if not candidate.is_absolute():
            candidate = Path("/") / candidate
        try:
            resolved = candidate.resolve(strict=False)
        except OSError as error:
            raise HistoryMatchError(f"路径不可用：{error}") from error
        if not self.is_within_roots(resolved):
            raise HistoryMatchError("路径不在已配置的媒体根目录内")
        if not resolved.exists():
            raise HistoryMatchError(f"路径不存在：{resolved}")
        return resolved

    def resolve_video(self, path: str | Path) -> Path:
        """
        校验一个视频文件路径（仅 .mkv 且位于根目录内）。

        :param path: 视频路径
        :return: 解析后的绝对路径
        :raises HistoryMatchError: 不满足约束
        """
        resolved = self.resolve_inside(path)
        if not resolved.is_file():
            raise HistoryMatchError(f"不是文件：{resolved}")
        if resolved.suffix.lower() not in VIDEO_EXT:
            raise HistoryMatchError("只支持 .mkv / .m2ts 文件")
        return resolved

    def resolve_source(self, path: str | Path, kind: str) -> Path:
        """
        校验一个素材文件路径（字幕/音频/字体），允许媒体根目录或上传目录。

        :param path: 素材路径
        :param kind: ``subtitle`` / ``audio`` / ``font``
        :return: 解析后的绝对路径
        :raises HistoryMatchError: 扩展名或位置不合法
        """
        allowed = KIND_EXT.get(kind)
        if not allowed:
            raise HistoryMatchError(f"未知素材类型：{kind}")
        candidate = Path(str(path)).expanduser()
        if not candidate.is_absolute():
            candidate = Path("/") / candidate
        try:
            resolved = candidate.resolve(strict=False)
        except OSError as error:
            raise HistoryMatchError(f"路径不可用：{error}") from error
        if not (self.is_within_roots(resolved) or self.is_upload(resolved)):
            raise HistoryMatchError("素材必须位于媒体根目录或插件上传目录内")
        if not resolved.is_file():
            raise HistoryMatchError(f"素材文件不存在：{resolved}")
        if resolved.suffix.lower() not in allowed:
            raise HistoryMatchError(f"不支持的素材扩展名：{resolved.suffix}")
        return resolved

    def ensure_dir(self, path: str | Path) -> Path:
        """
        创建并返回输出/备份等插件自管目录。

        :param path: 目标目录
        :return: 解析后的目录路径
        """
        target = Path(str(path)).expanduser().resolve()
        target.mkdir(parents=True, exist_ok=True)
        return target

    def list_dir(self, root: Optional[str], path: Optional[str], kind: str = "video") -> dict[str, Any]:
        """
        列出一个目录下的子目录和目标类型文件。

        :param root: 根目录（缺省用第一个配置根）
        :param path: 要列出的目录（缺省为根目录本身）
        :param kind: 文件类型过滤
        :return: 目录与文件列表
        :raises HistoryMatchError: 根目录未配置或路径越界
        """
        if not self.roots:
            raise HistoryMatchError("尚未配置媒体根目录，请先到设置里添加")
        if root:
            base = self.resolve_inside(root)
            if not base.is_dir():
                raise HistoryMatchError(f"根目录不可用：{base}")
        else:
            base = self.roots[0]
        current = self.resolve_inside(path) if path else base
        if not current.is_dir():
            raise HistoryMatchError(f"不是目录：{current}")
        allowed = KIND_EXT.get(kind, KIND_EXT["video"])

        dirs: list[dict[str, Any]] = []
        files: list[dict[str, Any]] = []
        try:
            entries = sorted(os.scandir(current), key=lambda item: (not item.is_dir(), item.name.lower()))
        except OSError as error:
            raise HistoryMatchError(f"目录读取失败：{error}") from error
        for entry in entries:
            if entry.name.startswith("."):
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    dirs.append({
                        "name": entry.name,
                        "path": str(current / entry.name),
                        "file_count": self._count_files(current / entry.name, allowed),
                    })
                elif entry.is_file(follow_symlinks=False):
                    suffix = Path(entry.name).suffix.lower()
                    if suffix not in allowed:
                        continue
                    stat = entry.stat(follow_symlinks=False)
                    files.append({
                        "name": entry.name,
                        "path": str(current / entry.name),
                        "size": stat.st_size,
                        "ext": suffix,
                    })
            except OSError:
                continue
        parent = str(current.parent) if current != base and self.is_within_roots(current.parent) else None
        return {
            "root": str(base),
            "path": str(current),
            "parent": parent,
            "dirs": dirs,
            "files": files,
        }

    @staticmethod
    def _count_files(directory: Path, allowed: set[str]) -> int:
        """统计目录下目标类型文件数量（不递归，失败返回 0）。"""
        try:
            count = 0
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.is_file(follow_symlinks=False) and Path(entry.name).suffix.lower() in allowed:
                        count += 1
                        if count >= 999:
                            break
            return count
        except OSError:
            return 0

    def free_space(self, directory: Path) -> int:
        """返回目录所在磁盘的可用字节数。"""
        try:
            return int(shutil.disk_usage(directory).free)
        except OSError:
            return 0
