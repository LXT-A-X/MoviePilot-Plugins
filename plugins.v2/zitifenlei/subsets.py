"""
assfonts 子集化封装：建字体索引 + 对 ASS 字幕做字体子集化并内嵌。

依赖：插件目录 bin/assfonts 可执行文件（Linux x86_64 ELF，随插件分发）。
assfonts 用法（见上游 wyzdwdz/assfonts README）：
  assfonts -b -f <fontpath> -d <dbpath>     建/更新字体索引（fonts.json 存于 dbpath）
  assfonts -i xxx.ass -d <dbpath> [-r]      子集化并内嵌字体 → 输出 xxx[.rename].assfonts.ass
                                             子集字体输出到输入同目录 <stem>_subsetted/
  stdout 含 [ERROR] 表示失败；'Missing the font: "xxx"' 表示缺字体
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SUBSET_DIR_SUFFIX = "_subsetted"
_OUT_SUFFIX = ".assfonts.ass"


class AssfontsMissingError(Exception):
    """字体缺失（Missing the font）"""

    def __init__(self, missing: List[str]) -> None:
        super().__init__("缺字体: " + "、".join(missing))
        self.missing = missing or []


def get_binary(plugin_root: Path) -> Optional[Path]:
    """插件根目录下的 bin/assfonts 可执行文件。

    Windows 推送/市场克隆常丢失 Unix 可执行位（git 存成 100644），
    容器内以 root（PUID=0）运行时检测到无可执行权限即自动 chmod +x 兜底。
    """
    p = Path(plugin_root) / "bin" / "assfonts"
    if not p.is_file():
        return None
    try:
        if not os.access(str(p), os.X_OK):
            os.chmod(str(p), 0o755)
    except Exception:
        pass
    return p if os.access(str(p), os.X_OK) else None


def build_index(binary: Path, font_dirs: List[str], db_path: Path) -> Tuple[bool, str]:
    """构建/更新字体索引：assfonts -b -f <font_dirs> -d <db_path>

    :return: (是否成功, 日志文本)
    """
    try:
        db_path = Path(db_path)
        db_path.mkdir(parents=True, exist_ok=True)
        cmd = [str(binary), "-b"]
        for d in font_dirs:
            if d:
                cmd += ["-f", str(d)]
        cmd += ["-d", str(db_path)]
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=600,
        )
        text = (result.stdout or "") + (result.stderr or "")
        if "[error]" in text.lower():
            errs = [ln for ln in text.splitlines() if "[error]" in ln.lower()]
            return False, "；".join(errs) or "构建索引失败"
        # 防假成功：输出无 [error] 但 fonts.json 没生成（如被中断/写权限缺失）也算失败
        if not (Path(db_path) / "fonts.json").is_file():
            return False, "索引构建未生成 fonts.json（可能被中断或目录不可写，请查看日志）"
        return True, text.strip()[:300]
    except Exception as err:
        return False, str(err)


def _entry_under(entry: Dict[str, Any], lib_dir: str) -> bool:
    """条目 path 是否位于字体库目录内（组件级判断，排除 assfonts 自带扫描进的系统字体如 /usr/share/fonts）"""
    p = entry.get("path") or ""
    if not p or not lib_dir:
        return True
    try:
        base = Path(lib_dir)
        return Path(p).is_relative_to(base)
    except Exception:
        try:
            return str(Path(p).resolve()).startswith(str(Path(lib_dir).resolve()) + "/")
        except Exception:
            return True


def index_font_count(db_path: Path, lib_dir: str = "") -> int:
    """读取索引 fonts.json 中的字体文件数（按 path 去重，一个 TTC 多 face 只算 1 个）。

    assfonts 构建索引时会同时扫描系统字体目录（/usr/share/fonts 等），
    传入 lib_dir 后可只统计字体库目录内的字体（失败返回 -1）。
    按 path 去重后再计数，口径与磁盘实际文件数（rglob 诊断）、字体库字体总数一致，
    避免「一个 TTC 含 2-3 个 face → 索引显示多出 2-3 个字体」的虚高。
    """
    try:
        fp = Path(db_path) / "fonts.json"
        if not fp.is_file():
            return -1
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not lib_dir:
            if not isinstance(data, (dict, list)):
                return -1
        if isinstance(data, dict):
            items = [{"path": k} for k in data.keys()]
            if not lib_dir:
                return len(items)
        elif isinstance(data, list):
            items = data
        else:
            return -1
        paths = {
            str(e.get("path") or "")
            for e in items
            if isinstance(e, dict) and _entry_under(e, lib_dir)
        }
        return len(paths)
    except Exception:
        return -1


def index_face_count(db_path: Path, lib_dir: str = "") -> int:
    """索引 face 条数（一个 TTC 含多个 face 就多条，供诊断/提示区分文件数）。"""
    try:
        fp = Path(db_path) / "fonts.json"
        if not fp.is_file():
            return -1
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            items = [{"path": k} for k in data.keys()] if lib_dir else data
        elif isinstance(data, list):
            items = data
        else:
            return -1
        if not lib_dir:
            return len(items)
        return sum(1 for e in items if isinstance(e, dict) and _entry_under(e, lib_dir))
    except Exception:
        return -1


def index_info(db_path: Path, lib_dir: str = "") -> Dict[str, Any]:
    """索引状态：是否存在 / 字体数（默认仅数字体库目录内）/ 最后构建时间 / 大小"""
    try:
        fp = Path(db_path) / "fonts.json"
        if not fp.is_file():
            return {"exists": False, "count": 0, "mtime": "", "size": 0}
        st = fp.stat()
        count = index_font_count(db_path, lib_dir)
        return {
            "exists": True,
            "count": int(count) if count > 0 else 0,
            "mtime": st.st_mtime,
            "size": st.st_size,
        }
    except Exception:
        return {"exists": False, "count": 0, "mtime": "", "size": 0}


def load_index(db_path: Path) -> Optional[Any]:
    """读取 assfonts 索引 fonts.json → dict（顶层为 字体路径->face数组）或 list（条目列表），
    不存在 / 解析失败返回 None。"""
    try:
        fp = Path(db_path) / "fonts.json"
        if not fp.is_file():
            return None
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, (dict, list)) else None
    except Exception:
        return None


def index_font_keys(data: Any, lib_dir: str) -> List[str]:
    """收集索引中「字体库目录内」所有可用字体名。

    assfonts 建索引时用 FontParser 递归扫描 fontpath（含系统字体目录
    /usr/share/fonts、C:\\Windows\\Fonts 等），必须按 lib_dir 过滤，
    否则检查语义会变成「本机有没有」而非「字体库有没有」。

    兼容三种结构（以 assfonts 实际输出为准）：
    - list：每条目为 flat face —— 顶层直接含 families/fullnames/psnames/path/index
      （assfonts ≥ 某版本实际输出格式，实测 C:\\plugins.v2\\fonts.json 即此结构）；
      兼容旧格式：条目含 path 与 faces（face 数组）
    - dict：key=字体文件路径，value=face 数组（或含 faces 的条目 dict）

    每个 face 收集 family/full/ps 三套名字（兼容 flat 顶层字段与 name 子表写法），
    检查侧与子集化侧共用同一份口径。
    """
    keys: List[str] = []
    seen: set = set()
    pairs: List[Tuple[str, Any]] = []
    if isinstance(data, dict):
        for path_key, val in data.items():
            if isinstance(val, list):
                faces = val
            elif isinstance(val, dict) and isinstance(val.get("faces"), list):
                faces = val["faces"]
            else:
                faces = [val]
            pairs.append((path_key, faces))
    elif isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            src_path = item.get("path") or ""
            # flat face 结构：条目自身即一个 face（含 families/fullnames/psnames 任一项）
            if any(k in item for k in ("families", "fullnames", "psnames")):
                pairs.append((src_path, [item]))
                continue
            if isinstance(item.get("faces"), list):
                pairs.append((src_path, item["faces"]))
            else:
                pairs.append((src_path, [item]))
    for path_key, faces in pairs:
        try:
            if not isinstance(faces, list):
                faces = [faces]
            for face in faces:
                if not isinstance(face, dict):
                    continue
                # 条目真实路径：face.path / face.source.path 优先，兜底顶层 key
                entry_path = ""
                for cand in (face.get("path"), (face.get("source") or {}).get("path") if isinstance(face.get("source"), dict) else None):
                    if cand:
                        entry_path = str(cand)
                        break
                if not entry_path:
                    entry_path = str(path_key or "")
                if not _entry_under({"path": entry_path}, lib_dir):
                    continue
                # 名字收集：flat 顶层字段 + name 子表双通道
                sections: List[Dict[str, Any]] = []
                flat = {k: face.get(k) for k in ("families", "fullnames", "psnames") if face.get(k) is not None}
                if flat:
                    sections.append(flat)
                name_sub = face.get("name")
                if isinstance(name_sub, dict):
                    sections.append(name_sub)
                for section in sections:
                    if not isinstance(section, dict):
                        continue
                    for field in (
                        "families", "fullnames", "psnames",
                        "family_names", "full_names", "ps_names",
                        "family_name", "full_name", "ps_name",
                    ):
                        v = section.get(field)
                        vals = v if isinstance(v, list) else ([v] if isinstance(v, str) and v else [])
                        for s in vals:
                            if isinstance(s, str) and s and s not in seen:
                                seen.add(s)
                                keys.append(s)
        except Exception:
            continue
    return keys


def output_paths(ass_file: Path, rename: bool) -> Tuple[Path, Path]:
    """按 assfonts 输出规则计算产出文件路径：(输出ass, 子集字体夹)"""
    suffix = ".rename" if rename else ""
    out = ass_file.with_name(f"{ass_file.stem}{suffix}{_OUT_SUFFIX}")
    subdir = ass_file.parent / f"{ass_file.stem}{_SUBSET_DIR_SUFFIX}"
    return out, subdir


def _parse_errors(text: str) -> Tuple[List[str], List[str]]:
    """解析 assfonts 输出：返回 (错误行列表, 缺失字体列表)"""
    errors: List[str] = []
    missing: List[str] = []
    for line in text.splitlines():
        low = line.lower()
        if "[error]" in low:
            errors.append(line.strip())
        if "missing the font:" in low:
            for m in re.finditer(r'Missing the font:\s*"?([^"?]+)"?', line, re.I):
                name = m.group(1).strip()
                if name and name not in missing:
                    missing.append(name)
    return errors, missing


def subset_ass_file(
    binary: Path,
    ass_file: Path,
    db_path: Path,
    rename: bool = True,
) -> Dict[str, Any]:
    """对单个 ASS 字幕执行 assfonts 子集化并内嵌字体。

    :return: {"status": success/skipped/missing/error,
              "reason": 说明, "out": 输出ass路径, "subdir": 子集字体夹路径,
              "missing_fonts": 缺失字体列表（结构化，缺字体时为实际缺失清单）}
    """
    result: Dict[str, Any] = {"status": "error", "reason": "", "out": "", "subdir": "", "missing_fonts": []}
    out, subdir = output_paths(ass_file, rename)
    result["out"] = str(out)
    result["subdir"] = str(subdir)
    try:
        cmd = [str(binary), "-i", str(ass_file), "-d", str(db_path)]
        if rename:
            cmd.append("-r")
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=600,
            cwd=str(ass_file.parent),
        )
        text = (proc.stdout or "") + (proc.stderr or "")
        errors, missing = _parse_errors(text)
        result["missing_fonts"] = missing
        # 缺字体优先判定：直接以解析出的 missing 列表为准（可行动项），
        # 不再因为输出里混着其它 error 就把实际错误吞成一条 missing
        if missing:
            result["status"] = "missing"
            result["reason"] = "缺字体: " + "、".join(missing)
            return result
        if errors:
            result["status"] = "error"
            result["reason"] = "；".join(errors[:3])
            return result
        if not out.exists():
            result["status"] = "error"
            result["reason"] = "处理完成但未找到输出文件"
            return result
        result["status"] = "success"
        result["reason"] = ""
        return result
    except subprocess.TimeoutExpired:
        result["status"] = "error"
        result["reason"] = "处理超时（600s）"
        return result
    except FileNotFoundError:
        result["status"] = "error"
        result["reason"] = "assfonts 二进制不存在或不可执行"
        return result
    except Exception as err:
        result["status"] = "error"
        result["reason"] = str(err)
        return result


# HDR 亮度档位 → 主色 ASS 色码（&HAABBGGRR；档位为纯白亮度的百分比）
HDR_LEVEL_COLOUR = {
    "100": "&H00FFFFFF",
    "85": "&H00D9D9D9",
    "80": "&H00CCCCCC",
    "75": "&H00BFBFBF",
    "70": "&H00B2B2B2",
    "63": "&H00A1A1A1",
    "50": "&H00808080",
}


def _decode_bytes_text(raw: bytes) -> Tuple[str, str]:
    """自适应解码 ass 文本并返回 (text, encoding)。UTF-16 BOM/前 1KB 含 NUL → utf-16，否则 utf-8。"""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace"), "utf-16"
    if b"\x00" in raw[:1024]:
        return raw.decode("utf-16", errors="replace"), "utf-16"
    return raw.decode("utf-8", errors="replace"), "utf-8"


def _scale_colour_token(col: str, percent: int) -> str:
    """把 ASS 色码 &H[AA]BBGGRR 按亮档压暗（RGB 各通道 × percent/100，保留 alpha）。"""
    m = re.fullmatch(r"&h([0-9a-fA-F]{6,8})", col.strip(), re.I)
    if not m:
        return col
    hexv = m.group(1)
    if len(hexv) == 8:
        a = hexv[:2]
        hexrgb = hexv[2:]
    else:
        a = "00"
        hexrgb = hexv
    try:
        rr = int(hexrgb[2:4], 16) * percent // 100
        gg = int(hexrgb[0:2], 16) * percent // 100
        bb = int(hexrgb[4:6], 16) * percent // 100
        return f"&H{a}{gg:02X}{bb:02X}{rr:02X}"
    except Exception:
        return col


def apply_hdr_brightness(ass_path: Path, level: str) -> Optional[str]:
    """对 ass 文件应用 HDR 亮度压暗：改动 Style 主色/描边/阴影与行内颜色标签。

    :param ass_path: 目标 .ass 文件（就地改写）
    :param level: 档位（100/85/80/75/70/63/50）
    :return: 成功返回说明；禁用/失败返回 None
    """
    percent = int(level) if str(level) in HDR_LEVEL_COLOUR else 0
    if not percent:
        return None
    try:
        raw = Path(ass_path).read_bytes()
        text, encoding = _decode_bytes_text(raw)
        changed = 0
        lines = text.split("\n")
        out_lines: List[str] = []
        for line in lines:
            if line.startswith("Style:"):
                parts = line.split(",")
                # Style: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour,
                #        OutlineColour, BackColour, Bold, ...
                # 压暗：PrimaryColour(3) / OutlineColour(5) / BackColour(6)
                if len(parts) >= 9:
                    for idx in (3, 5, 6):
                        new = _scale_colour_token(parts[idx], percent)
                        if new != parts[idx].strip():
                            parts[idx] = new
                            changed += 1
                out_lines.append(",".join(parts))
                continue
            if "\\c" in line or "\\1c" in line or "\\3c" in line or "\\4c" in line:
                def _repl(m: "re.Match[str]") -> str:
                    return _scale_colour_token(m.group(0), percent)
                new_line = re.sub(
                    r"\\[134]?c&H[0-9a-fA-F]{6,8}&",
                    _repl,
                    line,
                    flags=re.I,
                )
                if new_line != line:
                    changed += 1
                out_lines.append(new_line)
                continue
            out_lines.append(line)
        if not changed:
            return None
        new_raw = "\n".join(out_lines).encode("utf-16" if encoding == "utf-16" else "utf-8", errors="replace")
        Path(ass_path).write_bytes(new_raw)
        return f"HDR 亮度已应用（{percent}%，主色/描边/阴影）"
    except Exception:
        return None