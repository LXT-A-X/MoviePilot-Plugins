"""
字体元数据统一解析（fontTools 唯一权威）。

- TTF/OTF/WOFF 单 face；TTC/OTC 按 face 逐个解析（一个文件 ≠ 一个字体面）
- 名称/别名（含本地化名称）、厂商、设计者、版本、格式、cmap 字符覆盖
- 文件指纹：size + mtime_ns + SHA-256（读取前后 stat 校验，避免上传未完成时抢读）
- 解析失败明确记为 invalid/error 并保留原因，不伪装成「零字形正常字体」

不依赖 assfonts，也不读写 fonts.json。
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

try:
    from fontTools.ttLib import TTCollection, TTFont, TTLibError
except Exception:  # pragma: no cover - 宿主未装 fontTools 时只做降级提示
    TTCollection = None
    TTFont = None
    TTLibError = Exception

from .font_utils import map_vendor, max_font_file_bytes, normalize_font_key

# 参与别名匹配的 name 记录 ID：家族 / 子家族 / 全名 / PostScript 名 / 排版家族 / 排版子家族
_NAME_IDS = (1, 2, 4, 6, 16, 17)
# 用于展示的主名称优先级：全名 > PostScript 名 > 家族 + 子家族 > 家族
_DISPLAY_ORDER = (4, 6, 1)


@dataclass
class FontFaceMeta:
    """单个字体面的元数据（TTC/OTC 按 face_index 区分）。"""

    file_path: str
    face_index: int
    family: str = ""
    subfamily: str = ""
    full_name: str = ""
    postscript_name: str = ""
    typographic_family: str = ""
    typographic_subfamily: str = ""
    aliases: List[str] = field(default_factory=list)
    vendor: str = "未知厂商"
    designer: str = ""
    version: str = ""
    format: str = ""
    codepoints: Set[int] = field(default_factory=set)
    char_count: int = 0
    is_variable: bool = False
    status: str = "ok"
    error: str = ""

    def display_name(self) -> str:
        for value in (self.full_name, self.postscript_name, self.family):
            if value:
                return value
        return Path(self.file_path).stem

    def alias_keys(self) -> List[str]:
        """归一化后的匹配键（字体名大小写/空格/@竖排前缀等差异归一到同一键）。"""
        keys: List[str] = []
        seen = set()
        for name in self.aliases:
            key = normalize_font_key(name)
            if key and key not in seen:
                seen.add(key)
                keys.append(key)
        return keys

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "face_index": self.face_index,
            "family": self.family,
            "subfamily": self.subfamily,
            "full_name": self.full_name,
            "postscript_name": self.postscript_name,
            "typographic_family": self.typographic_family,
            "typographic_subfamily": self.typographic_subfamily,
            "aliases": list(self.aliases),
            "vendor": self.vendor,
            "designer": self.designer,
            "version": self.version,
            "format": self.format,
            "char_count": self.char_count,
            "is_variable": self.is_variable,
            "status": self.status,
            "error": self.error,
        }


@dataclass
class FontInspection:
    """一个字体文件的解析结果（可能包含多个 face）。"""

    path: str
    file_size: int = 0
    mtime_ns: int = 0
    sha256: str = ""
    format: str = ""
    face_count: int = 0
    valid_face_count: int = 0
    faces: List[FontFaceMeta] = field(default_factory=list)
    status: str = "ok"  # ok / invalid / partial
    error: str = ""

    def to_dict(self, include_codepoints: bool = False) -> Dict[str, Any]:
        data = {
            "path": self.path,
            "file_size": self.file_size,
            "mtime_ns": self.mtime_ns,
            "sha256": self.sha256,
            "format": self.format,
            "face_count": self.face_count,
            "valid_face_count": self.valid_face_count,
            "status": self.status,
            "error": self.error,
            "faces": [],
        }
        for face in self.faces:
            item = face.to_dict()
            if include_codepoints:
                item["codepoints"] = sorted(face.codepoints)
            data["faces"].append(item)
        return data


def compute_fingerprint(path: str | Path, with_hash: bool = True) -> Dict[str, Any]:
    """计算文件指纹。带稳定性校验：读取期间文件变化（上传未完成）直接报错。"""
    p = Path(path)
    st = p.stat()
    limit = max_font_file_bytes()
    if st.st_size > limit:
        raise RuntimeError(
            f"字体文件超过解析上限（{st.st_size // (1024 * 1024)}MB > "
            f"{limit // (1024 * 1024)}MB，可在设置中调整），拒绝哈希/解析"
        )
    digest = ""
    if with_hash:
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        digest = h.hexdigest()
    after = p.stat()
    if (st.st_size, st.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError("字体文件在计算指纹期间仍在变化（可能仍在上传）")
    return {"size": after.st_size, "mtime_ns": after.st_mtime_ns, "sha256": digest}


def encode_codepoints(codepoints: Iterable[int]) -> bytes:
    """字符覆盖集合 → 压缩二进制（排序 + varint 增量 + zlib）。

    中日文字体常见 2 万+ 码点，直接按行存 SQLite 会膨胀；这里压缩后通常几 KB。
    """
    out = bytearray()
    prev = 0
    for cp in sorted({int(c) for c in codepoints if 0 <= int(c) <= 0x10FFFF}):
        delta = cp - prev
        prev = cp
        while delta >= 0x80:
            out.append((delta & 0x7F) | 0x80)
            delta >>= 7
        out.append(delta)
    return zlib.compress(bytes(out), 9)


def decode_codepoints(blob: bytes) -> Set[int]:
    """压缩字符覆盖 → 码点集合（与 encode_codepoints 互逆）。"""
    if not blob:
        return set()
    raw = zlib.decompress(blob)
    result: Set[int] = set()
    prev = 0
    value = 0
    shift = 0
    for byte in raw:
        value |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
            continue
        prev += value
        result.add(prev)
        value = 0
        shift = 0
    return result


def _name_score(platform_id: int, lang_id: int) -> int:
    """名称记录优先级：Windows 英文 > Windows 中文 > Unicode > 其他。"""
    score = 0
    if platform_id == 3:
        score += 100
        if lang_id == 0x409:
            score += 50
        elif lang_id in (0x804, 0x404, 0x411, 0x412):
            score += 20
    elif platform_id == 0:
        score += 10
    return score


def _collect_names(font: Any) -> Dict[int, List[tuple]]:
    """收集 name 表：nameID -> [(score, 字符串)]。"""
    names: Dict[int, List[tuple]] = {}
    try:
        table = font["name"]
    except Exception:
        return names
    for record in table.names:
        try:
            text = record.toUnicode()
        except Exception:
            continue
        text = (text or "").strip()
        if not text or len(text) > 200:
            continue
        if any(ord(ch) < 0x20 for ch in text):
            continue
        names.setdefault(int(record.nameID), []).append(
            (_name_score(int(record.platformID), int(record.langID)), text)
        )
    return names


def _best_name(names: Dict[int, List[tuple]], name_id: int) -> str:
    items = names.get(name_id) or []
    if not items:
        return ""
    items = sorted(items, key=lambda item: item[0], reverse=True)
    return items[0][1]


def _cmap4_codepoints(data: bytes, off: int) -> Set[int]:
    """宽松解析 format 4：idRangeOffset 越界的个别条目直接跳过，不整体判失败。"""
    if off + 14 > len(data):
        return set()
    length = struct.unpack(">H", data[off + 2:off + 4])[0]
    seg = struct.unpack(">H", data[off + 6:off + 8])[0] // 2
    if seg <= 0:
        return set()
    pos = off + 14
    need = seg * 2
    if pos + need * 4 + 2 > len(data):
        return set()
    ends = struct.unpack(">%dH" % seg, data[pos:pos + need])
    starts = struct.unpack(">%dH" % seg, data[pos + need + 2:pos + need * 2 + 2])
    deltas = struct.unpack(">%dh" % seg, data[pos + need * 2 + 2:pos + need * 3 + 2])
    range_offset_pos = pos + need * 3 + 2
    offsets = struct.unpack(">%dH" % seg, data[range_offset_pos:range_offset_pos + need])
    limit = min(len(data), off + length) if length else len(data)
    result: Set[int] = set()
    for i in range(seg):
        start, end = starts[i], ends[i]
        if start > end or start == 0xFFFF:
            continue
        if offsets[i] == 0:
            for cp in range(start, end + 1):
                if cp == 0xFFFF:
                    continue
                if ((cp + deltas[i]) & 0xFFFF) != 0:
                    result.add(cp)
            continue
        base = range_offset_pos + 2 * i + offsets[i]
        for cp in range(start, end + 1):
            if cp == 0xFFFF:
                continue
            idx = base + 2 * (cp - start)
            if idx + 2 > limit:
                continue
            gid = struct.unpack(">H", data[idx:idx + 2])[0]
            if gid and ((gid + deltas[i]) & 0xFFFF) != 0:
                result.add(cp)
    return result


def _cmap6_codepoints(data: bytes, off: int) -> Set[int]:
    if off + 10 > len(data):
        return set()
    first, count = struct.unpack(">HH", data[off + 6:off + 10])
    result: Set[int] = set()
    for i in range(count):
        pos = off + 10 + 2 * i
        if pos + 2 > len(data):
            break
        if struct.unpack(">H", data[pos:pos + 2])[0]:
            result.add(first + i)
    return result


def _cmap12_codepoints(data: bytes, off: int) -> Set[int]:
    if off + 16 > len(data):
        return set()
    groups = struct.unpack(">I", data[off + 12:off + 16])[0]
    result: Set[int] = set()
    for i in range(min(groups, 0x10000)):
        rec = off + 16 + i * 12
        if rec + 12 > len(data):
            break
        start, end, glyph = struct.unpack(">III", data[rec:rec + 12])
        if end < start or end - start > 0x110000:
            continue
        for cp in range(start, end + 1):
            if glyph + (cp - start):
                result.add(cp)
    return result


def _codepoints_from_raw_cmap(font: Any) -> Set[int]:
    """兜底：fontTools 的 cmap 严格解析失败时，直接按字节解析 Unicode cmap。

    个别老字体（如华康 DFPop 系列 TTC）format 4 的 idRangeOffset 会指向
    glyphIdArray 末尾之外一个元素，fontTools 直接断言失败，导致整个字体被判
    「无 cmap」。这类文件实际只有一两个条目越界，跳过坏条目即可正常取码点。
    """
    try:
        # 必须读原始字节：cmap 一旦被 fontTools 部分加载，getTableData 会尝试重新编译并再次抛错
        data = font.reader["cmap"] if getattr(font, "reader", None) is not None else b""
    except Exception:
        data = b""
    if not data:
        try:
            data = font.getTableData("cmap")
        except Exception:
            return set()
    if not data or len(data) < 4:
        return set()
    try:
        count = struct.unpack(">H", data[2:4])[0]
    except Exception:
        return set()
    result: Set[int] = set()
    for i in range(min(count, 64)):
        rec = 4 + i * 8
        if rec + 8 > len(data):
            break
        pid, eid, offset = struct.unpack(">HHI", data[rec:rec + 8])
        if not (pid == 0 or (pid == 3 and eid in (1, 10))):
            continue
        if offset + 2 > len(data):
            continue
        fmt = struct.unpack(">H", data[offset:offset + 2])[0]
        try:
            if fmt == 4:
                result.update(_cmap4_codepoints(data, offset))
            elif fmt == 6:
                result.update(_cmap6_codepoints(data, offset))
            elif fmt == 12:
                result.update(_cmap12_codepoints(data, offset))
        except Exception:
            continue
    return result


def _font_codepoints(font: Any) -> Set[int]:
    """读取 cmap 覆盖的 Unicode 码点；best cmap 失败时按字节宽松解析，最后才合并全部子表。"""
    try:
        best = font.getBestCmap()
        if best:
            return {int(cp) for cp in best.keys()}
    except Exception:
        pass
    # 严格解析失败：先按字节宽松解析 Unicode 子表（跳过越界条目）。
    # 这一步必须优先于「合并全部 cmap 子表」——后者会把 Mac Roman 等非 Unicode
    # 子表的字节码（0x00-0xFF）当成码点，既不对又让兜底逻辑失效。
    raw = _codepoints_from_raw_cmap(font)
    if raw:
        return raw
    codepoints: Set[int] = set()
    try:
        for table in font["cmap"].tables:
            try:
                if int(table.platformID) == 1:  # Mac 编码，不是 Unicode
                    continue
                codepoints.update(int(cp) for cp in table.cmap.keys())
            except Exception:
                continue
    except Exception:
        pass
    return codepoints


def _sfnt_format(font: Any, suffix: str) -> str:
    ext = (suffix or "").lower().lstrip(".")
    if ext in ("ttc", "otc"):
        return ext
    version = getattr(font, "sfntVersion", "") or ""
    if version == "OTTO":
        return "otf"
    if version in ("\x00\x01\x00\x00", "\x00\x00\x01\x00", "true"):
        return "ttf"
    return ext or "font"


def _iter_fonts(path: Path):
    """打开字体文件并逐个 yield (face_index, TTFont)；集合格式按 TTCollection 展开。"""
    suffix = path.suffix.lower()
    if suffix in (".ttc", ".otc") and TTCollection is not None:
        collection = TTCollection(str(path), lazy=True)
        try:
            for index, font in enumerate(collection.fonts):
                yield index, font
        finally:
            try:
                collection.close()
            except Exception:
                pass
    else:
        if TTFont is None:
            raise RuntimeError("未安装 fontTools，无法解析字体")
        font = TTFont(str(path), fontNumber=0, lazy=True)
        try:
            yield 0, font
        finally:
            try:
                font.close()
            except Exception:
                pass


def _inspect_face(path: Path, index: int, font: Any) -> FontFaceMeta:
    names = _collect_names(font)
    family = _best_name(names, 1)
    subfamily = _best_name(names, 2)
    full_name = _best_name(names, 4)
    postscript_name = _best_name(names, 6)
    typographic_family = _best_name(names, 16)
    typographic_subfamily = _best_name(names, 17)
    raw_vendor = _best_name(names, 8)
    designer = _best_name(names, 9)
    version = _best_name(names, 5)

    # 别名：所有本地化名称 + 家族/子家族组合，覆盖 ASS 里五花八门的写法
    aliases: List[str] = []
    seen = set()

    def add(value: str) -> None:
        value = (value or "").strip()
        if not value:
            return
        key = value.casefold()
        if key in seen:
            return
        seen.add(key)
        aliases.append(value)

    for name_id in _NAME_IDS:
        for _score, text in names.get(name_id) or []:
            add(text)
    primary_family = typographic_family or family
    primary_subfamily = typographic_subfamily or subfamily
    if primary_family and primary_subfamily:
        add(f"{primary_family} {primary_subfamily}")
    if family and subfamily:
        add(f"{family} {subfamily}")

    codepoints = _font_codepoints(font)
    status = "ok"
    error = ""
    if not codepoints:
        # 没有 cmap 不代表文件损坏（少数纯符号/位图字体），但无法做字符覆盖判定
        status = "no_cmap"
        error = "字体没有可用的 cmap 字符表"

    face = FontFaceMeta(
        file_path=str(path),
        face_index=index,
        family=family or full_name or path.stem,
        subfamily=subfamily,
        full_name=full_name or family or path.stem,
        postscript_name=postscript_name,
        typographic_family=typographic_family,
        typographic_subfamily=typographic_subfamily,
        aliases=aliases,
        designer=designer,
        version=version,
        format=_sfnt_format(font, path.suffix),
        codepoints=codepoints,
        char_count=len(codepoints),
        is_variable=("fvar" in font),
        status=status,
        error=error,
    )
    face.vendor = map_vendor(
        raw_vendor,
        parent_dir=str(path.parent),
        file_name=path.name,
        hint=face.family,
    )
    return face


def inspect_font(path: str | Path, with_hash: bool = True) -> FontInspection:
    """解析一个字体文件的全部 face；任何层面失败都记录原因，不静默吞掉。"""
    p = Path(path)
    inspection = FontInspection(path=str(p))
    try:
        fingerprint = compute_fingerprint(p, with_hash=with_hash)
        inspection.file_size = int(fingerprint["size"])
        inspection.mtime_ns = int(fingerprint["mtime_ns"])
        inspection.sha256 = str(fingerprint["sha256"] or "")
    except Exception as err:
        inspection.status = "invalid"
        inspection.error = f"读取文件失败: {err}"
        return inspection

    inspection.format = p.suffix.lower().lstrip(".") or "font"
    faces: List[FontFaceMeta] = []
    try:
        for index, font in _iter_fonts(p):
            try:
                faces.append(_inspect_face(p, index, font))
            except Exception as err:
                faces.append(
                    FontFaceMeta(
                        file_path=str(p),
                        face_index=index,
                        format=inspection.format,
                        status="invalid",
                        error=f"face {index} 解析失败: {err}",
                    )
                )
    except Exception as err:
        inspection.status = "invalid"
        inspection.error = f"字体解析失败: {err}"
        inspection.faces = faces
        inspection.face_count = len(faces)
        inspection.valid_face_count = sum(1 for f in faces if f.status == "ok")
        return inspection

    inspection.faces = faces
    inspection.face_count = len(faces)
    inspection.valid_face_count = sum(1 for f in faces if f.status == "ok")
    if not faces:
        inspection.status = "invalid"
        inspection.error = "未解析到任何字体面"
    elif inspection.valid_face_count == 0:
        inspection.status = "invalid"
        inspection.error = "所有字体面均解析失败"
    elif inspection.valid_face_count < len(faces):
        inspection.status = "partial"
        inspection.error = "部分字体面解析失败"
    return inspection


def lookup_keys_for_inspection(inspection: FontInspection) -> Dict[str, List[int]]:
    """别名 → face_index 列表（写入索引时用）。"""
    result: Dict[str, List[int]] = {}
    for face in inspection.faces:
        if face.status != "ok":
            continue
        for key in face.alias_keys():
            result.setdefault(key, []).append(face.face_index)
    return result
