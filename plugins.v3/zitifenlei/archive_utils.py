"""
上传压缩包安全解包（仅 .zip，标准库 zipfile，不引入额外依赖）。

约束（后端强校验，不依赖前端提示）：
- 只解一层：嵌套压缩包不解，按不支持扩展名跳过
- 防 Zip Slip：拒绝绝对路径、盘符、`..` 越界成员
- 拒绝加密成员、目录项、系统/隐藏垃圾文件（__MACOSX、.DS_Store 等）
- 单成员大小、总大小、成员数量上限，防止 zip bomb / 磁盘打满
- 按扩展名白名单只取需要处理的文件（字体 / .ass）
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterable, List, Optional, Sequence, Tuple

ZIP_EXTENSIONS = (".zip",)

# 默认上限：单包 2GB、单成员 1GB、最多 5000 个成员（字体库/字幕包足够）
DEFAULT_MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_MAX_MEMBER_BYTES = 1 * 1024 * 1024 * 1024
DEFAULT_MAX_MEMBERS = 5000

_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_JUNK_PARTS = {"__MACOSX", "__MACOSX".lower(), ".DS_Store".lower(), "Thumbs.db".lower()}


@dataclass
class ExtractedFile:
    path: Path
    member: str
    size: int


@dataclass
class ExtractResult:
    files: List[ExtractedFile] = field(default_factory=list)
    skipped: List[Tuple[str, str]] = field(default_factory=list)
    errors: List[Tuple[str, str]] = field(default_factory=list)
    total_bytes: int = 0

    @property
    def ok(self) -> bool:
        return bool(self.files)

    def summary(self) -> dict:
        return {
            "files": [{"path": str(item.path), "member": item.member, "size": item.size} for item in self.files],
            "skipped": [{"member": name, "reason": reason} for name, reason in self.skipped],
            "errors": [{"member": name, "reason": reason} for name, reason in self.errors],
            "total_bytes": self.total_bytes,
        }


def is_archive(name: str) -> bool:
    return Path(name or "").suffix.lower() in ZIP_EXTENSIONS


def safe_unlink(
    path: str | Path,
    *allowed_roots: str | Path,
    exts: Sequence[str] | None = None,
) -> bool:
    """边界安全删除：仅当目标位于允许根目录内且后缀在白名单内才删除。

    - 必须传入至少一个允许根；无根一律拒绝（防止调用方漏传参数时误删任意文件）
    - 目标等于允许根本身也拒绝（只删根内的子文件）
    - 文件本就不存在视为成功（幂等）
    返回 True=已删除/本就不存在，False=越界/后缀不符/删除失败。
    """
    if not allowed_roots:
        return False
    try:
        target = Path(path).resolve()
    except Exception:
        return False
    if exts:
        suffixes = {str(e).lower() for e in exts}
        if target.suffix.lower() not in suffixes:
            return False
    within = False
    for root in allowed_roots:
        if root is None or str(root) == "":
            continue
        try:
            root_path = Path(root).resolve()
        except Exception:
            continue
        if target == root_path:
            continue
        try:
            if target.is_relative_to(root_path):
                within = True
                break
        except AttributeError:  # 旧版 Python 回退
            if root_path in target.parents:
                within = True
                break
    if not within:
        return False
    try:
        if not target.exists():
            return True
        if target.is_dir():
            return False
        target.unlink()
        return True
    except Exception:
        return False


def _is_junk_member(member: str) -> bool:
    name = (member or "").replace("\\", "/").strip()
    return any(part.casefold() in _JUNK_PARTS for part in PurePosixPath(name).parts)


def _safe_member_path(root: Path, member: str) -> Optional[Path]:
    """成员路径 → 解压目标路径；越界/非法返回 None。"""
    name = (member or "").replace("\\", "/").strip()
    if not name:
        return None
    if name.startswith("/") or _DRIVE_RE.match(name):
        return None
    parts = PurePosixPath(name).parts
    if ".." in parts:
        return None
    target = (root / name).resolve()
    try:
        if not target.is_relative_to(root.resolve()):
            return None
    except AttributeError:  # 旧版 Python 回退
        if str(target) != str(root.resolve()) and str(root.resolve()) not in str(target):
            return None
    return target


def extract_zip(
    zip_path: str | Path,
    dest_dir: str | Path,
    allowed_exts: Sequence[str],
    max_members: int = DEFAULT_MAX_MEMBERS,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_member_bytes: int = DEFAULT_MAX_MEMBER_BYTES,
) -> ExtractResult:
    """安全解压 zip，只保留扩展名白名单内的文件。"""
    result = ExtractResult()
    zip_file = Path(zip_path)
    root = Path(dest_dir)
    exts = tuple(ext.lower() for ext in allowed_exts)

    try:
        if not zipfile.is_zipfile(zip_file):
            result.errors.append((zip_file.name, "不是有效的 zip 压缩包"))
            return result
    except Exception as err:
        result.errors.append((zip_file.name, f"读取压缩包失败: {err}"))
        return result

    try:
        root.mkdir(parents=True, exist_ok=True)
    except Exception as err:
        result.errors.append((zip_file.name, f"创建解压目录失败: {err}"))
        return result

    try:
        with zipfile.ZipFile(zip_file) as zf:
            infos = zf.infolist()
            if len(infos) > max_members:
                result.errors.append((zip_file.name, f"压缩包成员过多（{len(infos)} > {max_members}），已拒绝解压"))
                return result
            for info in infos:
                member = info.filename
                if info.is_dir():
                    continue
                if info.flag_bits & 0x1:
                    result.skipped.append((member, "加密的压缩包成员（不支持密码）"))
                    continue
                suffix = Path(member.replace("\\", "/")).suffix.lower()
                if _is_junk_member(member):
                    result.skipped.append((member, "系统/隐藏垃圾文件"))
                    continue
                if suffix not in exts:
                    if suffix in ZIP_EXTENSIONS:
                        result.skipped.append((member, "嵌套压缩包不解（只解一层）"))
                    else:
                        result.skipped.append((member, "不在允许的扩展名内"))
                    continue
                if info.file_size > max_member_bytes:
                    result.skipped.append((member, f"单文件超过上限 {max_member_bytes} 字节"))
                    continue
                if result.total_bytes + info.file_size > max_total_bytes:
                    result.errors.append((zip_file.name, f"解压后总大小超过上限 {max_total_bytes} 字节，已停止"))
                    break
                target = _safe_member_path(root, member)
                if target is None:
                    result.errors.append((member, "非法路径（疑似 Zip Slip），已拒绝"))
                    continue
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    written = 0
                    with zf.open(info) as src, target.open("wb") as dst:
                        while True:
                            chunk = src.read(1024 * 1024)
                            if not chunk:
                                break
                            written += len(chunk)
                            if written > max_member_bytes or result.total_bytes + written > max_total_bytes:
                                raise RuntimeError("实际写出大小超过上限")
                            dst.write(chunk)
                    result.total_bytes += written
                    result.files.append(ExtractedFile(path=target, member=member, size=written))
                except Exception as err:
                    result.errors.append((member, f"解压失败: {err}"))
                    try:
                        target.unlink(missing_ok=True)
                    except Exception:
                        pass
    except Exception as err:
        result.errors.append((zip_file.name, f"解压异常: {err}"))
    return result
