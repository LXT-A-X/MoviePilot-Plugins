"""
压缩包字体提取：从 zip / tar / 7z / rar 中解出字体文件。

- zip / tar（含 .tar.gz/.tar.bz2/.tar.xz）：Python 标准库直接解，不依赖外部程序；
- 7z / rar：调用系统已安装的 ``7z``（或 ``7zz``/``7za``）与 ``unrar``；
- 所有解压都做路径穿越防护、文件数/大小限制，只保留 .ttf/.otf/.ttc。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Iterable, Optional

FONT_EXT = {".ttf", ".otf", ".ttc"}
ARCHIVE_EXT = {
    ".zip", ".7z", ".rar", ".tar", ".tgz", ".tbz2", ".txz",
    ".tar.gz", ".tar.bz2", ".tar.xz",
}
MAX_FONT_FILES = 500
MAX_FONT_BYTES = 512 * 1024 * 1024


def archive_extension(name: str | Path) -> str:
    """返回压缩包扩展名（支持 .tar.gz 这类双后缀，统一小写）。"""
    text = str(name).lower()
    for suffix in (".tar.gz", ".tar.bz2", ".tar.xz"):
        if text.endswith(suffix):
            return suffix
    path = Path(text)
    return path.suffix.lower()


def is_archive(path: str | Path) -> bool:
    """判断路径扩展名是否为支持的压缩包。"""
    return archive_extension(path) in ARCHIVE_EXT


def _which(*names: str) -> str:
    """在 PATH 中查找可执行文件。"""
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return ""


def available_tools() -> dict[str, str]:
    """返回可用的外部解压程序。"""
    return {
        "7z": _which("7z", "7zz", "7za"),
        "unrar": _which("unrar", "unrar-free"),
    }


def supported_extensions() -> list[str]:
    """前端展示用的支持扩展名。"""
    tools = available_tools()
    result = [".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz"]
    if tools["7z"]:
        result.append(".7z")
        result.append(".rar")
    elif tools["unrar"]:
        result.append(".rar")
    return result


def _safe_member(dest: Path, member_name: str) -> Optional[Path]:
    """把压缩包内路径转成目标路径，拒绝绝对路径/.. 逃逸。"""
    name = str(member_name).replace("\\", "/").lstrip("/")
    if not name or name.endswith("/"):
        return None
    relative = Path(name)
    if any(part in {"", ".", ".."} for part in relative.parts):
        return None
    target = (dest / relative).resolve()
    try:
        if not target.is_relative_to(dest.resolve()):
            return None
    except (OSError, ValueError):
        return None
    return target


def _collect_fonts(dest: Path) -> list[Path]:
    """收集目录下的字体文件（解压后调用）。"""
    result: list[Path] = []
    for path in sorted(dest.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in FONT_EXT:
            continue
        result.append(path)
        if len(result) >= MAX_FONT_FILES:
            break
    return result


def _extract_zip(archive: Path, dest: Path) -> list[Path]:
    """解压 zip 中的字体文件。"""
    result: list[Path] = []
    total = 0
    with zipfile.ZipFile(archive) as handle:
        for info in handle.infolist():
            if info.is_dir() or Path(info.filename).suffix.lower() not in FONT_EXT:
                continue
            target = _safe_member(dest, info.filename)
            if target is None:
                continue
            if len(result) >= MAX_FONT_FILES or total + info.file_size > MAX_FONT_BYTES:
                break
            target.parent.mkdir(parents=True, exist_ok=True)
            with handle.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            total += info.file_size
            result.append(target)
    return result


def _extract_tar(archive: Path, dest: Path) -> list[Path]:
    """解压 tar 系列中的字体文件。"""
    result: list[Path] = []
    total = 0
    with tarfile.open(archive, mode="r:*") as handle:
        for member in handle.getmembers():
            if not member.isfile() or Path(member.name).suffix.lower() not in FONT_EXT:
                continue
            target = _safe_member(dest, member.name)
            if target is None:
                continue
            if len(result) >= MAX_FONT_FILES or total + member.size > MAX_FONT_BYTES:
                break
            source = handle.extractfile(member)
            if source is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            total += member.size
            result.append(target)
    return result


def _extract_external(archive: Path, dest: Path) -> list[Path]:
    """用 7z / unrar 解压到临时目录，再把字体移动到目标目录。"""
    tools = available_tools()
    suffix = archive_extension(archive)
    temp = Path(tempfile.mkdtemp(prefix="mkvfont-"))
    try:
        commands: list[list[str]] = []
        if tools["7z"]:
            commands.append([tools["7z"], "x", "-y", f"-o{temp}", str(archive)])
        if suffix == ".rar" and tools["unrar"]:
            commands.append([tools["unrar"], "x", "-o+", str(archive), str(temp) + os.sep])
        if not commands:
            raise RuntimeError(
                "解压 7z/rar 需要系统安装 7z 或 unrar；zip/tar 不需要额外程序"
            )
        last_error = ""
        for command in commands:
            completed = subprocess.run(
                command, capture_output=True, text=True, timeout=600,
                encoding="utf-8", errors="replace",
            )
            if completed.returncode in (0, 1):
                break
            last_error = (completed.stderr or completed.stdout or "").strip()[-500:]
        else:
            raise RuntimeError(f"解压失败：{last_error or '解压程序返回错误'}")
        result: list[Path] = []
        total = 0
        for source in _collect_fonts(temp):
            target = dest / source.name
            if target.exists():
                target = dest / f"{source.stem}-{source.stat().st_size}{source.suffix}"
            target.parent.mkdir(parents=True, exist_ok=True)
            size = source.stat().st_size
            if len(result) >= MAX_FONT_FILES or total + size > MAX_FONT_BYTES:
                break
            shutil.move(str(source), str(target))
            total += size
            result.append(target)
        return result
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def extract_fonts(archive: Path, dest: Path) -> list[Path]:
    """
    从压缩包提取字体文件到目标目录。

    :param archive: 压缩包路径
    :param dest: 目标目录
    :return: 提取出的字体文件列表
    :raises RuntimeError: 不支持或解压失败
    """
    archive = Path(archive)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    suffix = archive_extension(archive)
    if suffix == ".zip":
        return _extract_zip(archive, dest)
    if suffix in {".tar", ".tgz", ".tbz2", ".txz", ".tar.gz", ".tar.bz2", ".tar.xz"}:
        return _extract_tar(archive, dest)
    if suffix in {".7z", ".rar"}:
        return _extract_external(archive, dest)
    raise RuntimeError(f"不支持的压缩包格式：{suffix or archive.name}")


def scan_archives(directory: Path, recursive: bool = False) -> list[Path]:
    """扫描目录（或递归）下的压缩包，最多返回 50 个。"""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    iterator: Iterable[Path] = directory.rglob("*") if recursive else directory.iterdir()
    found: list[Path] = []
    try:
        for path in sorted(iterator):
            if path.is_file() and is_archive(path):
                found.append(path)
                if len(found) >= 50:
                    break
    except OSError:
        return found
    return found
