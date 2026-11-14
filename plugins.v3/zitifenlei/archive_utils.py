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

多工具容错（.rar 尤其重要）：
- 解 .7z/.rar 时按候选工具顺序逐个尝试，某个工具缺失/不支持该格式/解压报错就自动换下一个，
  最后再尝试复用 MoviePilot 宿主自带的解压实现（app.adapters.system.host.SystemUtils）；
- 7za/7zr 是 7-Zip 精简版（只支持 7z，不支持 rar），因此不会作为 .rar 候选；
- 7-Zip 退出码 1 表示"有警告但已解出文件"，按成功处理（否则一个乱码文件名就会判整包失败）；
- 容器内没有解压工具时，插件设置/依赖页可调用 install_extract_tools() 一键 apt/apk 安装 unar。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ZIP_EXTENSIONS = (".zip",)
EXTERNAL_ARCHIVE_EXTENSIONS = (".7z", ".rar")

# 外部解压工具探测清单（按优先级）。7z/7zz 是否带 Rar 解码器取决于构建，
# 真正解包时按候选顺序逐个尝试，任何工具失败都会自动换下一个，避免只挑到一个
# 不顶用的工具就整个失败。7za/7zr 是 7-Zip 精简版，只支持 7z，不能解 rar。
_TOOL_NAMES = ("7z", "7zz", "7za", "7zr", "unar", "unrar", "unrar-free", "bsdtar")
_TOOL_CACHE: Optional[Dict[str, str]] = None
# 可执行性探测缓存：shutil.which 只能证明"路径存在"，Windows 的 0 字节应用别名、
# 或装了但立即崩溃的工具都会被误判成"可用"。真正执行一次（无参打印 usage）才算数。
_PROBE_CACHE: Dict[str, bool] = {}

# 各后缀的候选工具（元组顺序即尝试顺序）
_SEVEN_ZIP_CANDIDATES = ("7z", "7zz", "7za", "7zr", "unar", "bsdtar")
_RAR_CANDIDATES = ("7z", "7zz", "unar", "unrar", "unrar-free", "bsdtar")

# 默认上限：单包 2GB、单成员 1GB、最多 5000 个成员（字体库/字幕包足够）
DEFAULT_MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_MAX_MEMBER_BYTES = 1 * 1024 * 1024 * 1024
DEFAULT_MAX_MEMBERS = 5000

_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_JUNK_PARTS = {"__MACOSX", "__MACOSX".lower(), ".DS_Store".lower(), "Thumbs.db".lower()}
_CJK_RE = re.compile(r"[\u3400-\u9fff\uf900-\ufaff]")


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


def _tool_launchable(exe: str) -> bool:
    """真正执行一次工具（无参一般打印 usage 后退出），排除 0 字节别名/启动即崩的假工具。"""
    cached = _PROBE_CACHE.get(exe)
    if cached is not None:
        return cached
    ok = False
    try:
        subprocess.run(
            [exe],
            capture_output=True,
            text=True,
            timeout=15,
            stdin=subprocess.DEVNULL,
        )
        ok = True
    except Exception:
        ok = False
    _PROBE_CACHE[exe] = ok
    return ok


def detect_extract_tools(refresh: bool = False) -> Dict[str, str]:
    """探测系统可用的解压工具，返回 {工具名: 可执行文件路径}。

    结果缓存，避免每次上传都扫 PATH；传 refresh=True 强制重扫（依赖检测接口用）。
    除 shutil.which 外还会真正执行一次（_tool_launchable），避免把 Windows 应用别名
    这类 0 字节 exe / 一启动就崩的工具当成"已安装"。
    """
    global _TOOL_CACHE
    if _TOOL_CACHE is not None and not refresh:
        return dict(_TOOL_CACHE)
    found: Dict[str, str] = {}
    for name in _TOOL_NAMES:
        exe = shutil.which(name)
        if exe and _tool_launchable(exe):
            found[name] = exe
    _TOOL_CACHE = found
    return dict(found)


def _tool_candidates(names: Sequence[str]) -> List[Tuple[str, str]]:
    """按给定顺序返回当前环境可用的 (工具名, 可执行路径) 列表。"""
    tools = detect_extract_tools()
    return [(name, tools[name]) for name in names if tools.get(name)]


def seven_zip_candidates() -> List[Tuple[str, str]]:
    """可解 .7z 的工具候选（按优先级，含 unar/bsdtar 兜底）。"""
    return _tool_candidates(_SEVEN_ZIP_CANDIDATES)


def rar_candidates() -> List[Tuple[str, str]]:
    """可解 .rar 的工具候选（按优先级）。

    `7za`/`7zr` 是精简版 7-Zip，没有 Rar 解码器，不能列入，否则会把「装了 7za」
    误判成「支持 rar」。真正的能力以逐个工具实际解包结果为准。
    """
    return _tool_candidates(_RAR_CANDIDATES)


def external_archive_extensions() -> Tuple[str, ...]:
    """当前环境实际可解的外部压缩包后缀（工具缺失时返回空）。"""
    exts: List[str] = []
    if seven_zip_candidates():
        exts.append(".7z")
    if rar_candidates():
        exts.append(".rar")
    return tuple(exts)


def describe_extract_state(refresh: bool = False) -> Dict[str, Any]:
    """当前环境解压能力摘要（设置页状态行 / 依赖检测 / 上传提示共用）。"""
    tools = detect_extract_tools(refresh=refresh)
    details = [
        {"name": name, "path": tools[name]}
        for name in _TOOL_NAMES
        if tools.get(name)
    ]
    can_install = bool(shutil.which("apt-get") or shutil.which("apk"))
    has_rar = bool(rar_candidates())
    has_seven = bool(seven_zip_candidates())
    names = "、".join(sorted(tools.keys())) or "未检测到"
    hint = ""
    if not has_rar:
        hint = (
            "未检测到可解 .rar 的工具（需 unar/unrar/带 Rar 解码器的 7z）："
            + ("可点「安装解压工具」在容器内自动安装 unar。" if can_install else "请在镜像内安装 unar 后重启容器。")
        )
    elif not has_seven:
        hint = "未检测到可解 .7z 的工具，可点「安装解压工具」自动安装 unar。"
    return {
        "zip": True,
        "seven_zip": has_seven,
        "rar": has_rar,
        "tools": sorted(tools.keys()),
        "details": details,
        "extensions": list(archive_extensions()),
        "can_install": can_install,
        "platform": sys.platform,
        "hint": hint,
        "summary": f"zip 内置；7z：{'可用' if has_seven else '未安装'}；rar：{'可用' if has_rar else '未安装'}（已检测到：{names}）",
    }


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


def _zip_member_name(info: zipfile.ZipInfo) -> str:
    """还原「未设 UTF-8 标志」的 zip 成员名（cp437 乱码 → 尝试 UTF-8/GB18030/BIG5）。

    中文压缩软件（Windows/安卓）常把中文名按 GBK 写进 zip 却不设 UTF-8 标志，
    zipfile 会按 cp437 解码成乱码；乱码里还可能夹带 0x5C（解码成反斜杠），
    后续按反斜杠切路径时后缀会变空，导致字体被误判为「不在允许的扩展名内」。
    这里用原始字节重新猜编码，解出明显 CJK 才采用，避免误伤正常英文名。
    """
    name = info.filename or ""
    try:
        if int(info.flag_bits) & 0x800:
            return name
    except Exception:
        pass
    try:
        raw = name.encode("cp437")
    except Exception:
        return name
    for encoding in ("utf-8", "gb18030", "big5"):
        try:
            guess = raw.decode(encoding)
        except Exception:
            continue
        if guess and guess != name and _CJK_RE.search(guess):
            return guess
    return name


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
                member = _zip_member_name(info)
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


def _host_unpack(archive: Path, outdir: Path) -> Optional[str]:
    """复用 MoviePilot 宿主自带的解压实现（V3/V2 路径都试）。

    成功返回 None；失败/宿主不可用返回错误描述。作为最后一个兜底：宿主的
    SystemUtils 自己会按 unar/unrar/7z/bsdtar 依次尝试（见 MP 源码）。
    """
    unpack = None
    for module_path in ("app.adapters.system.host", "app.utils.system"):
        try:
            module = __import__(module_path, fromlist=["SystemUtils"])
            candidate = getattr(module, "SystemUtils", None)
            if candidate is not None and hasattr(candidate, "unpack_archive"):
                unpack = candidate
                break
        except Exception:
            continue
    if unpack is None:
        return "宿主未提供解压能力"
    try:
        outdir.mkdir(parents=True, exist_ok=True)
        fmt = "rar" if archive.suffix.lower() == ".rar" else None
        unpack.unpack_archive(Path(archive), Path(outdir), fmt)
        return None
    except Exception as err:
        return str(err)


def _tool_cmd(tool: str, exe: str, archive: Path, outdir: Path) -> List[str]:
    """不同解压工具的命令行（统一解到 outdir，不保留压缩包内顶层目录限制由调用方处理）。"""
    if tool in ("7z", "7zz", "7za", "7zr"):
        return [exe, "x", "-y", "-bd", f"-o{outdir.as_posix()}", archive.as_posix()]
    if tool == "unar":
        return [exe, "-q", "-f", "-o", outdir.as_posix(), "-D", archive.as_posix()]
    if tool in ("unrar", "unrar-free"):
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
    """用系统解压工具解 .7z/.rar：先解到隔离临时目录，再校验后复制到目标目录。

    候选工具按优先级逐个尝试：某个工具缺失、不支持该格式或解压报错时自动换下一个
    （典型场景：容器里只有 7za 时它解不了 rar，但机器上同时装了 unar）；
    全部工具都失败后，再兜底调用 MoviePilot 宿主自带的解压实现。
    """
    result = ExtractResult()
    archive = Path(archive_path)
    root = Path(dest_dir)
    exts = tuple(ext.lower() for ext in allowed_exts)
    suffix = archive.suffix.lower()
    candidates = rar_candidates() if suffix == ".rar" else seven_zip_candidates()
    if not candidates:
        result.errors.append(
            (
                archive.name,
                f"未检测到可解 {suffix} 的解压工具（需 7z/7zz/unar/unrar/bsdtar；"
                "可在「仪表盘 → 依赖 → 解压工具」点「安装解压工具」自动安装）",
            )
        )
        return result
    try:
        root.mkdir(parents=True, exist_ok=True)
    except Exception as err:
        result.errors.append((archive.name, f"创建解压目录失败: {err}"))
        return result

    attempts: List[str] = []
    staging: Optional[Path] = None
    staged: List[Path] = []
    for tool, exe in candidates:
        if tool in ("7z", "7zz", "7za", "7zr"):
            precheck = _precheck_with_7z(exe, archive, max_members, max_total_bytes)
            if precheck:
                # 预检已确认成员数/总大小超限：换工具也一样超限，直接判失败，避免白解一遍
                result.errors.append((archive.name, precheck))
                return result
        attempt_dir = root / f".extract_{uuid.uuid4().hex}"
        try:
            attempt_dir.mkdir(parents=True, exist_ok=True)
            try:
                proc = subprocess.run(
                    _tool_cmd(tool, exe, archive, attempt_dir),
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
            except Exception as err:
                attempts.append(f"{tool}: 调用失败 {err}")
                continue
            found = [p for p in sorted(attempt_dir.rglob("*")) if p.is_file()]
            # 7-Zip 退出码 1 = 部分成员有警告但已解出可用文件（乱码名/链接/不支持项等），
            # 只要解出了文件就继续走后缀白名单过滤，不能因此判整包失败。
            ok = proc.returncode == 0
            if not ok and tool in ("7z", "7zz", "7za", "7zr") and proc.returncode == 1 and found:
                ok = True
            if ok and found:
                staging, staged = attempt_dir, found
                break
            detail = ((proc.stderr or proc.stdout or "").strip().splitlines() or [""])[-1]
            attempts.append(f"{tool}: {detail[:160] or f'退出码 {proc.returncode}'}")
        finally:
            if attempt_dir is not staging:
                shutil.rmtree(attempt_dir, ignore_errors=True)

    # 最后一个兜底：MoviePilot 宿主自己的解压实现（对 rar 才有补充意义）
    if staging is None and suffix == ".rar":
        host_dir = root / f".extract_{uuid.uuid4().hex}"
        try:
            host_err = _host_unpack(archive, host_dir)
            if host_err is None:
                found = [p for p in sorted(host_dir.rglob("*")) if p.is_file()]
                if found:
                    staging, staged = host_dir, found
                else:
                    attempts.append("宿主解压: 未解出任何文件")
            else:
                attempts.append(f"宿主解压: {host_err[:160]}")
        finally:
            if host_dir is not staging:
                shutil.rmtree(host_dir, ignore_errors=True)

    if staging is None:
        detail = "；".join(attempts[:4]) or "所有工具都未解出文件"
        result.errors.append(
            (archive.name, f"{suffix} 解压失败（已尝试 {len(candidates)} 个工具）：{detail}")
        )
        return result

    try:
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


def list_archive_entries(
    archive_path: str | Path,
    max_entries: int = 500,
) -> Dict[str, Any]:
    """列出压缩包内容（不落盘、不解压，仅供管理页在线查看）。

    返回 {"entries": [{"name","size","is_dir"}], "total", "truncated", "tool"}。
    zip 用标准库；7z/rar 优先 7z l -slt，其次 lsar -j，最后 bsdtar -tf。
    工具缺失/格式不支持时返回 {"error": "..."}。
    """
    archive = Path(archive_path)
    if not archive.is_file():
        return {"error": "压缩包文件不存在"}

    def _collect(entries: List[Dict[str, Any]], tool: str) -> Dict[str, Any]:
        total = len(entries)
        shown = entries[: max(1, int(max_entries))]
        return {
            "entries": shown,
            "total": total,
            "truncated": total > len(shown),
            "tool": tool,
        }

    if zipfile.is_zipfile(archive):
        try:
            entries: List[Dict[str, Any]] = []
            with zipfile.ZipFile(archive) as zf:
                for info in zf.infolist():
                    name = _zip_member_name(info)
                    if not name:
                        continue
                    entries.append(
                        {
                            "name": name,
                            "size": 0 if info.is_dir() else int(info.file_size or 0),
                            "is_dir": info.is_dir(),
                        }
                    )
            return _collect(entries, "zip")
        except Exception as err:
            return {"error": f"读取 zip 目录失败: {err}"}

    suffix = archive.suffix.lower()
    candidates = rar_candidates() if suffix == ".rar" else seven_zip_candidates()
    for tool, exe in candidates:
        entries: List[Dict[str, Any]] = []
        try:
            if tool in ("7z", "7zz", "7za", "7zr"):
                proc = subprocess.run(
                    [exe, "l", "-slt", archive.as_posix()],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=120,
                )
                if proc.returncode != 0:
                    continue
                name, size, is_dir, kind = "", 0, False, ""
                def _flush() -> None:
                    nonlocal name, size, is_dir, kind
                    if name and kind.lower() not in ("7z", "rar", "zip", "cab", "tar", "gzip"):
                        entries.append(
                            {
                                "name": name,
                                "size": 0 if is_dir else int(size or 0),
                                "is_dir": bool(is_dir),
                            }
                        )
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
                        is_dir = line[13:].strip().startswith("D")
                    elif line.startswith("Type = "):
                        kind = line[7:].strip()
                _flush()
                if entries:
                    return _collect(entries, tool)
            elif tool == "bsdtar":
                proc = subprocess.run(
                    [exe, "-tf", archive.as_posix()],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=120,
                )
                if proc.returncode != 0:
                    continue
                for raw_line in proc.stdout.splitlines():
                    name = raw_line.strip()
                    if name:
                        entries.append({"name": name, "size": 0, "is_dir": name.endswith("/")})
                if entries:
                    return _collect(entries, tool)
        except Exception:
            continue

    lsar = shutil.which("lsar")
    if lsar:
        try:
            proc = subprocess.run(
                [lsar, "-j", archive.as_posix()],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
            if proc.returncode == 0:
                data = json.loads(proc.stdout or "{}")
                entries = []
                for item in data.get("lsarContents") or []:
                    name = str(item.get("XADFileName") or "")
                    if not name:
                        continue
                    entries.append(
                        {
                            "name": name,
                            "size": int(item.get("XADFileSize") or 0),
                            "is_dir": bool(item.get("XADIsDirectory")),
                        }
                    )
                if entries:
                    return _collect(entries, "lsar")
        except Exception:
            pass

    return {
        "error": (
            "当前环境没有可列出该格式的解压工具（需 7z/unar/lsar）；"
            "可到「仪表盘 → 依赖 → 解压工具」安装/修复。"
        )
    }

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


def _run_install_command(
    cmd: Sequence[str], timeout: int = 900, env: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """执行一条安装命令并收集输出（供 install_extract_tools 汇总，不抛异常）。"""
    try:
        proc = subprocess.run(
            [str(c) for c in cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        output = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return {
            "cmd": " ".join(str(c) for c in cmd),
            "ok": proc.returncode == 0,
            "output": output[-2000:],
        }
    except Exception as err:
        return {"cmd": " ".join(str(c) for c in cmd), "ok": False, "output": str(err)[-2000:]}


def install_extract_tools() -> Dict[str, Any]:
    """在容器内尝试安装解压工具（apt/apk），供「一键安装解压工具」使用。

    - 需要容器内 root、可用的 apt-get/apk 与网络；每一步命令与输出都会回传；
    - 只装能同时覆盖 .7z / .rar 的工具：优先 unar（Debian 自带，rar4/rar5 都能解），
      再试 7zip、p7zip-full，最后 unrar-free；
    - 装完重新探测工具缓存；容器重建/镜像更新后需要重新安装。
    """
    steps: List[Dict[str, Any]] = []
    if not (shutil.which("apt-get") or shutil.which("apk")):
        return {
            "ok": False,
            "steps": steps,
            "state": describe_extract_state(refresh=True),
            "message": "容器内没有 apt-get/apk，无法自动安装；请在镜像里安装 unar（或 7z）后重启容器",
        }
    # 只有确实探测到 unar（rar/7z 都能解）才直接跳过安装；
    # 光有 7z 不够——精简版/缺 Rar 解码器的 7z 会被 which 误判成"有工具"。
    if shutil.which("unar"):
        return {
            "ok": True,
            "steps": steps,
            "state": describe_extract_state(),
            "message": "已检测到 unar（可解 .7z/.rar），无需安装",
        }

    if shutil.which("apt-get"):
        env = dict(os.environ)
        env["DEBIAN_FRONTEND"] = "noninteractive"
        steps.append(_run_install_command(["apt-get", "update", "-qq"], timeout=300, env=env))
        for pkg in ("unar", "7zip", "p7zip-full", "unrar-free"):
            if rar_candidates() and seven_zip_candidates():
                break
            steps.append(
                _run_install_command(
                    ["apt-get", "install", "-y", "--no-install-recommends", pkg],
                    timeout=900,
                    env=env,
                )
            )
            detect_extract_tools(refresh=True)

    if not (rar_candidates() and seven_zip_candidates()) and shutil.which("apk"):
        for pkg in ("unar", "p7zip"):
            if rar_candidates() and seven_zip_candidates():
                break
            steps.append(_run_install_command(["apk", "add", "--no-cache", pkg], timeout=600))
            detect_extract_tools(refresh=True)

    detect_extract_tools(refresh=True)
    state = describe_extract_state()
    ok = bool(state.get("rar") and state.get("seven_zip"))
    if ok:
        return {
            "ok": True,
            "steps": steps,
            "state": state,
            "message": "解压工具安装完成：现在支持 .7z/.rar（容器重建或更新镜像后需要重新安装）",
        }
    failed = [step for step in steps if not step.get("ok")]
    lines: List[str] = []
    for step in failed[-3:]:
        output = (step.get("output") or "").strip().splitlines()
        lines.append(f"{step.get('cmd')}: {output[-1] if output else '失败'}")
    detail = "；".join(lines) or "所有安装命令均失败"
    return {
        "ok": False,
        "steps": steps,
        "state": state,
        "message": (
            f"安装未成功（{detail}）。"
            "若容器没有 root 权限或无法联网，请在镜像内安装 unar（或 7z）后重启容器；"
            "也可以直接把字体从压缩包解出来再上传。"
        ),
    }

