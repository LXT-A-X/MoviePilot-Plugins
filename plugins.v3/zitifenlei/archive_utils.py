"""
压缩包安全解包（.zip 用标准库；.7z/.rar 依赖系统解压工具，探测不到则明确拒绝）。

约束（后端强校验，不依赖前端提示）：
- 只解一层：嵌套压缩包不解，按不支持扩展名跳过
- 防 Zip Slip：拒绝绝对路径、盘符、`..` 越界成员
- 拒绝加密成员、目录项、系统/隐藏垃圾文件（__MACOSX、.DS_Store 等）
- 单成员大小、总大小、成员数量上限，防止 zip bomb / 磁盘打满
- 按扩展名白名单只取需要处理的文件（字体 / .ass）
- .7z/.rar：先解到隔离临时目录，再逐个校验（路径/后缀/体积）后复制到目标，
  7z 可用时还会先 `l -slt` 预检成员数与总大小，避免解压后才发现超限
"""

from __future__ import annotations

import re
import shutil
import subprocess
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

ZIP_EXTENSIONS = (".zip",)
EXTERNAL_ARCHIVE_EXTENSIONS = (".7z", ".rar")

# 外部解压工具探测顺序：7z 同时能读 7z/rar（p7zip 自带 Rar 解码），优先
_TOOL_NAMES = ("7z", "7za", "unar", "unrar", "bsdtar")
_TOOL_CACHE: Optional[Dict[str, str]] = None

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


def detect_extract_tools(refresh: bool = False) -> Dict[str, str]:
    """探测系统可用的解压工具，返回 {工具名: 可执行文件路径}。

    结果缓存，避免每次上传都扫 PATH；传 refresh=True 强制重扫（依赖检测接口用）。
    """
    global _TOOL_CACHE
    if _TOOL_CACHE is not None and not refresh:
        return dict(_TOOL_CACHE)
    found: Dict[str, str] = {}
    for name in _TOOL_NAMES:
        exe = shutil.which(name)
        if exe:
            found[name] = exe
    _TOOL_CACHE = found
    return dict(found)


def external_archive_extensions() -> Tuple[str, ...]:
    """当前环境实际可解的外部压缩包后缀（工具缺失时返回空）。"""
    tools = detect_extract_tools()
    exts: List[str] = []
    # 7z/7za 与 unar 都能读 .7z
    if tools.get("7z") or tools.get("7za") or tools.get("unar"):
        exts.append(".7z")
    # .rar 需要 7z/7za、unar、unrar 或 bsdtar（libarchive）
    if any(tools.get(k) for k in ("7z", "7za", "unar", "unrar", "bsdtar")):
        exts.append(".rar")
    return tuple(exts)


def archive_extensions() -> Tuple[str, ...]:
    """当前环境支持的压缩包后缀：zip 永远支持，其余按工具探测结果。"""
    return ZIP_EXTENSIONS + external_archive_extensions()


def is_archive(name: str) -> bool:
    """是否为本环境支持的压缩包（zip 恒支持，7z/rar 取决于解压工具）。"""
    return Path(name or "").suffix.lower() in archive_extensions()


def is_any_archive(name: str) -> bool:
    """是否压缩包后缀（不管当前环境能否解），用于生成「未装工具」的明确提示。"""
    return Path(name or "").suffix.lower() in (ZIP_EXTENSIONS + EXTERNAL_ARCHIVE_EXTENSIONS)


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
                    if suffix in (ZIP_EXTENSIONS + EXTERNAL_ARCHIVE_EXTENSIONS):
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


def _pick_external_tool(suffix: str) -> Tuple[str, str]:
    """按后缀选一个可用的外部解压工具，返回 (工具名, 可执行路径)；没有则返回 ("", "")。"""
    tools = detect_extract_tools()
    order = ("7z", "7za", "unar") if suffix == ".7z" else ("7z", "7za", "unar", "unrar", "bsdtar")
    for name in order:
        exe = tools.get(name)
        if exe:
            return name, exe
    return "", ""


def _tool_cmd(tool: str, exe: str, archive: Path, outdir: Path) -> List[str]:
    """不同解压工具的命令行（统一解到 outdir，不保留压缩包内顶层目录限制由调用方处理）。"""
    if tool in ("7z", "7za"):
        return [exe, "x", "-y", "-bd", f"-o{outdir.as_posix()}", archive.as_posix()]
    if tool == "unar":
        return [exe, "-q", "-f", "-o", outdir.as_posix(), "-D", archive.as_posix()]
    if tool == "unrar":
        return [exe, "x", "-o+", "-y", archive.as_posix(), outdir.as_posix() + "/"]
    if tool == "bsdtar":
        return [exe, "-xf", archive.as_posix(), "-C", outdir.as_posix()]
    return []


def _precheck_with_7z(
    exe: str,
    archive: Path,
    max_members: int,
    max_total_bytes: int,
) -> Optional[str]:
    """用 7z l -slt 预检成员数与解压后总大小；超限返回原因，正常返回 None。

    预检失败（工具不支持该格式/输出不可解析）时返回 None，交给解压后的二次校验兜底。
    """
    try:
        proc = subprocess.run(
            [exe, "l", "-slt", archive.as_posix()],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    members: List[Tuple[str, int]] = []
    name = ""
    size = 0
    is_dir = False
    kind = ""

    def _flush() -> None:
        nonlocal name, size, is_dir, kind
        if name and not is_dir and kind.lower() not in ("7z", "rar", "zip", "cab", "tar", "gzip"):
            members.append((name, size))
        name, size, is_dir, kind = "", 0, False, ""

    for raw_line in proc.stdout.splitlines():
        line = raw_line.strip()
        if line.startswith("Path = "):
            _flush()
            name = line[7:].strip()
        elif line.startswith("Size = "):
            try:
                size = int(line[7:].strip())
            except Exception:
                size = 0
        elif line.startswith("Attributes = "):
            attr = line[13:].strip()
            if attr.startswith("D"):
                is_dir = True
        elif line.startswith("Type = "):
            kind = line[7:].strip()
    _flush()
    if not members:
        return None
    if len(members) > max_members:
        return f"压缩包成员过多（{len(members)} > {max_members}），已拒绝解压"
    total = sum(size for _, size in members)
    if total > max_total_bytes:
        return f"解压后总大小超过上限（{total} > {max_total_bytes} 字节），已拒绝解压"
    return None


def extract_external(
    archive_path: str | Path,
    dest_dir: str | Path,
    allowed_exts: Sequence[str],
    max_members: int = DEFAULT_MAX_MEMBERS,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_member_bytes: int = DEFAULT_MAX_MEMBER_BYTES,
) -> ExtractResult:
    """用系统解压工具解 .7z/.rar：先解到隔离临时目录，再校验后复制到目标目录。"""
    result = ExtractResult()
    archive = Path(archive_path)
    root = Path(dest_dir)
    exts = tuple(ext.lower() for ext in allowed_exts)
    suffix = archive.suffix.lower()
    tool, exe = _pick_external_tool(suffix)
    if not tool:
        result.errors.append(
            (archive.name, f"未检测到可解 {suffix} 的解压工具（需 7z/7za/unar/unrar/bsdtar）")
        )
        return result
    if tool in ("7z", "7za"):
        precheck = _precheck_with_7z(exe, archive, max_members, max_total_bytes)
        if precheck:
            result.errors.append((archive.name, precheck))
            return result
    try:
        root.mkdir(parents=True, exist_ok=True)
    except Exception as err:
        result.errors.append((archive.name, f"创建解压目录失败: {err}"))
        return result
    staging = root / f".extract_{uuid.uuid4().hex}"
    try:
        staging.mkdir(parents=True, exist_ok=True)
    except Exception as err:
        result.errors.append((archive.name, f"创建临时解压目录失败: {err}"))
        return result
    try:
        try:
            proc = subprocess.run(
                _tool_cmd(tool, exe, archive, staging),
                capture_output=True,
                text=True,
                timeout=600,
            )
        except Exception as err:
            result.errors.append((archive.name, f"调用 {tool} 解压失败: {err}"))
            return result
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip().splitlines()
            reason = detail[-1] if detail else f"退出码 {proc.returncode}"
            result.errors.append((archive.name, f"{tool} 解压失败（加密或损坏？）: {reason[:200]}"))
            return result

        staged = [p for p in sorted(staging.rglob("*")) if p.is_file()]
        if len(staged) > max_members:
            result.errors.append((archive.name, f"压缩包成员过多（{len(staged)} > {max_members}），已拒绝"))
            return result
        for src_file in staged:
            member = src_file.relative_to(staging).as_posix()
            if _is_junk_member(member):
                result.skipped.append((member, "系统/隐藏垃圾文件"))
                continue
            member_suffix = Path(member).suffix.lower()
            if member_suffix not in exts:
                if member_suffix in (ZIP_EXTENSIONS + EXTERNAL_ARCHIVE_EXTENSIONS):
                    result.skipped.append((member, "嵌套压缩包不解（只解一层）"))
                else:
                    result.skipped.append((member, "不在允许的扩展名内"))
                continue
            try:
                size = src_file.stat().st_size
            except Exception:
                size = 0
            if size > max_member_bytes:
                result.skipped.append((member, f"单文件超过上限 {max_member_bytes} 字节"))
                continue
            if result.total_bytes + size > max_total_bytes:
                result.errors.append((archive.name, f"解压后总大小超过上限 {max_total_bytes} 字节，已停止"))
                break
            target = _safe_member_path(root, member)
            if target is None:
                result.errors.append((member, "非法路径（疑似越界），已拒绝"))
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src_file, target)
                result.total_bytes += size
                result.files.append(ExtractedFile(path=target, member=member, size=size))
            except Exception as err:
                result.errors.append((member, f"复制失败: {err}"))
        return result
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def extract_archive(
    archive_path: str | Path,
    dest_dir: str | Path,
    allowed_exts: Sequence[str],
    max_members: int = DEFAULT_MAX_MEMBERS,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_member_bytes: int = DEFAULT_MAX_MEMBER_BYTES,
) -> ExtractResult:
    """按后缀分派解压：.zip 走标准库，.7z/.rar 走系统工具（缺工具时明确报错）。"""
    suffix = Path(archive_path).suffix.lower()
    if suffix in ZIP_EXTENSIONS:
        return extract_zip(
            archive_path,
            dest_dir,
            allowed_exts,
            max_members=max_members,
            max_total_bytes=max_total_bytes,
            max_member_bytes=max_member_bytes,
        )
    if suffix in EXTERNAL_ARCHIVE_EXTENSIONS:
        return extract_external(
            archive_path,
            dest_dir,
            allowed_exts,
            max_members=max_members,
            max_total_bytes=max_total_bytes,
            max_member_bytes=max_member_bytes,
        )
    result = ExtractResult()
    result.errors.append((Path(archive_path).name, f"不支持的压缩包格式：{suffix or '（无后缀）'}"))
    return result

