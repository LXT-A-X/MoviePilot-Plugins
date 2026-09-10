"""
字体分类管家 - 字体/字幕解析工具
- 字体元数据解析：fontTools（内部扫描）或文件名（文件名解析）
- ASS 字幕字体引用提取
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from fontTools.ttLib import TTFont, TTLibError
except Exception:
    TTFont = None
    TTLibError = Exception

# 字体文件扩展名
FONT_EXTENSIONS = (".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2")
ASS_EXTENSIONS = (".ass",)

# ── 厂商识别规则（优先级：内部元数据制造商名 > 目录名映射 > 文件名规则 > 未知）──

# 1) 内部制造商名（nameID 8）→ 中文厂商映射：把 fontTools 读出的英文字符串归一到中文
_VENDOR_NAME_MAP = [
    (re.compile(r"morisawa", re.I), "森泽"),
    (re.compile(r"founder", re.I), "方正"),
    (re.compile(r"hanyi", re.I), "汉仪"),
    (re.compile(r"arphic", re.I), "文鼎"),
    (re.compile(r"dynacomware|dynafont|dyna", re.I), "华康"),
    (re.compile(r"sinotype|founder arphic", re.I), "华文"),
    (re.compile(r"monotype", re.I), "Monotype"),
    (re.compile(r"fontworks", re.I), "Fontworks"),
    (re.compile(r"microsoft|ms corp", re.I), "Microsoft"),
    (re.compile(r"adobe", re.I), "Adobe"),
    (re.compile(r"source han|思源", re.I), "Adobe"),
    (re.compile(r"noto|google", re.I), "Google"),
    (re.compile(r"wenquanyi|wen quan", re.I), "文泉驿"),
    (re.compile(r"tensentype|tengxiang", re.I), "腾祥"),
    (re.compile(r"ricoh", re.I), "理光"),
    (re.compile(r"ipa", re.I), "IPA"),
    (re.compile(r"zcool", re.I), "站酷"),
    (re.compile(r"huawei|harmonyos", re.I), "华为"),
    (re.compile(r"xiaomi|miui", re.I), "小米"),
    (re.compile(r"oppo", re.I), "OPPO"),
    (re.compile(r"vivo", re.I), "vivo"),
    (re.compile(r"alibaba", re.I), "阿里巴巴"),
]

# 2) 目录名映射：字体库目录结构自带厂商标识（如 "Arphic（文鼎）"、"DynaFont（华康）"）
_DIR_VENDOR_HINTS = [
    (re.compile(r"arphic|文鼎", re.I), "文鼎"),
    (re.compile(r"dynafont|dynacomware|华康", re.I), "华康"),
    (re.compile(r"sinotype|华文", re.I), "华文"),
    (re.compile(r"fontworks", re.I), "Fontworks"),
    (re.compile(r"adobe", re.I), "Adobe"),
    (re.compile(r"ricoh|理光", re.I), "理光"),
    (re.compile(r"microsoft|微软", re.I), "Microsoft"),
    (re.compile(r"founder|方正", re.I), "方正"),
    (re.compile(r"hanyi|汉仪", re.I), "汉仪"),
    (re.compile(r"monotype|蒙纳", re.I), "Monotype"),
    (re.compile(r"腾祥", re.I), "腾祥"),
    (re.compile(r"文泉|wqy|wenquanyi", re.I), "文泉驿"),
    (re.compile(r"zcool|站酷", re.I), "站酷"),
    (re.compile(r"汉鼎", re.I), "汉鼎"),
    (re.compile(r"书体坊", re.I), "书体坊"),
    (re.compile(r"叶根友", re.I), "叶根友"),
    (re.compile(r"义启", re.I), "义启"),
    (re.compile(r"理杏", re.I), "理杏"),
    (re.compile(r"张海山", re.I), "张海山"),
    (re.compile(r"苏新诗", re.I), "苏新诗"),
    (re.compile(r"钟齐", re.I), "钟齐"),
    (re.compile(r"霞鹜|lxgw", re.I), "霞鹜"),
    (re.compile(r"更纱|sarasa", re.I), "更纱黑体"),
    (re.compile(r"zpix|点阵", re.I), "点阵"),
    (re.compile(r"ipa", re.I), "IPA"),
]

# 3) 文件名规则兜底：常见中文字体厂商文件名/前缀模式
_VENDOR_HINTS = [
    # 得意黑优先于通用规则，避免 "Smiley Sans" 被误判
    (re.compile(r"smiley sans|smileysans|得意黑", re.I), "得意黑"),
    # MORISAWA（森泽）：内部名同一映射；文件名 MO 前缀（MOKei/MOStd/MOJR…，MO 后须跟字母，避免误伤 moons/modern 等）
    (re.compile(r"morisawa", re.I), "森泽"),
    (re.compile(r"(^|[_.\- ])mo(?=[a-z])", re.I), "森泽"),
    # 中文厂商名 → 中文
    (re.compile(r"方正", re.I), "方正"),
    (re.compile(r"汉仪", re.I), "汉仪"),
    (re.compile(r"华康|華康", re.I), "华康"),
    (re.compile(r"华文", re.I), "华文"),
    (re.compile(r"文鼎", re.I), "文鼎"),
    (re.compile(r"蒙纳", re.I), "Monotype"),
    (re.compile(r"腾祥", re.I), "腾祥"),
    (re.compile(r"文泉驿|文泉", re.I), "文泉驿"),
    (re.compile(r"站酷", re.I), "站酷"),
    (re.compile(r"汉鼎", re.I), "汉鼎"),
    (re.compile(r"书体坊", re.I), "书体坊"),
    (re.compile(r"叶根友", re.I), "叶根友"),
    (re.compile(r"义启", re.I), "义启"),
    (re.compile(r"思源|sourcehan|Source Han", re.I), "Adobe"),
    (re.compile(r"noto", re.I), "Google"),
    # 前缀模式（FZ=方正, HY=汉仪, DF=华康, ST=华文, FOT=Fontworks, LXGW=霞鹜）
    (re.compile(r"(^|[_.\- ])(fz|fzst|fzxk)", re.I), "方正"),
    (re.compile(r"(^|[_.\- ])hy(?!brid|per)", re.I), "汉仪"),
    (re.compile(r"(^|[_.\- ])df", re.I), "华康"),
    # ST 华文：排除 -Style/-STYLE 等修饰后缀（如 MOKei-StyleA-D 的 -Style 不得判为华文）
    (re.compile(r"(^|[_.\- ])st(?!yle)(?=[a-z0-9])", re.I), "华文"),
    (re.compile(r"fot-", re.I), "Fontworks"),
    (re.compile(r"lxgw", re.I), "霞鹜"),
    (re.compile(r"sarasa", re.I), "更纱黑体"),
    (re.compile(r"zpix|unifont", re.I), "点阵"),
    (re.compile(r"ipaex|ipag|ipam|ipaf", re.I), "IPA"),
    # Microsoft 系统字体（精确，避免裸 "ms" 误伤）
    (re.compile(r"msyh[bl]?d?|msyh[lt]?|msyh_", re.I), "Microsoft"),
    (re.compile(r"simhei|simsun|simfang|simkai|simyou|simeng|simli", re.I), "Microsoft"),
    (re.compile(r"ms gothic|ms mincho|ms pgothic|ms ui gothic|meiryo|yu gothic|malgun", re.I), "Microsoft"),
    (re.compile(r"微软雅黑|微软|新宋体|宋体|黑体|仿宋|幼圆|楷体_GB2312", re.I), "Microsoft"),
    # 其他品牌
    (re.compile(r"harmonyos|huawei", re.I), "华为"),
    (re.compile(r"xiaomi|miui", re.I), "小米"),
    (re.compile(r"^oppo", re.I), "OPPO"),
    (re.compile(r"^vivo", re.I), "vivo"),
    (re.compile(r"alibaba", re.I), "阿里巴巴"),
    (re.compile(r"zcool", re.I), "站酷"),
    (re.compile(r"文泉|wqy", re.I), "文泉驿"),
]


def is_font_file(name: str) -> bool:
    return name.lower().endswith(FONT_EXTENSIONS)


def is_ass_file(name: str) -> bool:
    return name.lower().endswith(ASS_EXTENSIONS)


def _decode_ass_text(ass_bytes: bytes) -> str:
    """ASS 文本编码自适应解码：UTF-16 BOM / 前 1KB 含 NUL → UTF-16；否则 UTF-8。

    部分字幕站/压制工具输出 UTF-16 编码的 ass（BOM FF FE / FE FF），若一律按 UTF-8 解码，
    ASCII 字符之间会残留 NUL 字节，导致 Style 行 / {\fn} 标签 / 区段标题全部匹配失败。
    """
    if not ass_bytes:
        return ""
    if ass_bytes.startswith(b"\xff\xfe") or ass_bytes.startswith(b"\xfe\xff"):
        try:
            return ass_bytes.decode("utf-16")
        except Exception:
            return ""
    if b"\x00" in ass_bytes[:1024]:
        try:
            return ass_bytes.decode("utf-16", errors="replace")
        except Exception:
            return ""
    return ass_bytes.decode("utf-8", errors="replace")


def has_embedded_fonts(ass_bytes: bytes) -> bool:
    """判断 ASS 字幕是否内嵌（子集化）了字体。

    libass / 压制工具标准做法是在 [Fonts] / [Glyphs] 区段内嵌字体：
      [Fonts]
      fontname: <字体名> ...
      <base64 字体数据>
      [Glyphs]
      <base64 字形数据>
    存在上述区段标题（或独立小写 fontname: 行）即判定「已内嵌字体」。
    编码自适应（UTF-16 / UTF-8），避免漏判老工具产出的字幕。
    """
    text = _decode_ass_text(ass_bytes)
    for line in text.splitlines():
        s = line.strip().lstrip("\ufeff").lower()
        if s.startswith("[fonts]") or s.startswith("[glyphs]") or s.startswith("[font]"):
            return True
        # 旁证：独立小写 fontname: 行（样式行的 Fontname 是 Style: 行内字段，不会单独成行）
        if s.startswith("fontname:"):
            return True
    return False


def _get_name_record(ttfont: Any, name_id: int) -> str:
    """从 fontTools name 表读取指定记录（优先英文，其次任意）"""
    if ttfont is None or not hasattr(ttfont, "name"):
        return ""
    try:
        for record in ttfont["name"].names:
            if record.nameID == name_id:
                try:
                    value = record.toUnicode().strip()
                except Exception:
                    continue
                if value:
                    return value
    except Exception:
        pass
    return ""


def get_font_psname(file_path: str | Path) -> str:
    """读取字体内部 PostScript 名（nameID 6），用于「是否利用字体内部名称命名」；
    读取失败或为空返回空串（调用方回退原文件名）。"""
    file_path = Path(file_path)
    if TTFont is None:
        return ""
    try:
        ttfont = TTFont(str(file_path), fontNumber=0, lazy=True)
        try:
            return _get_name_record(ttfont, 6)
        finally:
            try:
                ttfont.close()
            except Exception:
                pass
    except Exception:
        return ""


def parse_font_metadata(
    file_path: str | Path,
    scan_mode: str = "internal",
    filename_hint: str = "",
) -> Dict[str, Any]:
    """
    解析字体文件的元数据
    :param file_path: 字体文件路径
    :param scan_mode: internal=用fontTools读内部元数据; filename=仅从文件名解析
    :param filename_hint: 作为 fallback 的显示名（没有内部信息时用）
    :return: {name, family, vendor, designer}
    """
    file_path = Path(file_path)
    file_name = file_path.name
    base_name = Path(file_name).stem
    hint = filename_hint or base_name

    name = ""
    family = ""
    vendor = ""
    designer = ""

    if scan_mode == "internal" and TTFont is not None:
        try:
            ttfont = TTFont(str(file_path), fontNumber=0, lazy=True)
            try:
                name = _get_name_record(ttfont, 4) or _get_name_record(ttfont, 1)
                family = _get_name_record(ttfont, 1) or _get_name_record(ttfont, 16)
                designer = _get_name_record(ttfont, 9)
                vendor = _get_name_record(ttfont, 8)
            finally:
                try:
                    ttfont.close()
                except Exception:
                    pass
        except Exception:
            name = ""
            family = ""
            vendor = ""
            designer = ""

    # 文件名模式解析（作为 vendor 兜底 / filename 模式主解析）
    if not name:
        name = hint
    if not family:
        family = hint

    # ── 厂商识别：内部制造商名 → 目录名 → 文件名 → 内部原文兜底 ──
    raw_vendor = vendor  # nameID 8 读出的原始制造商名
    vendor = ""
    if raw_vendor:
        # 1) 内部制造商名映射（Arphic → 文鼎、Founder → 方正、DynaComware → 华康…）
        for pattern, mapped in _VENDOR_NAME_MAP:
            if pattern.search(raw_vendor):
                vendor = mapped
                break
    if not vendor:
        # 2) 目录名映射：字体库目录结构自带厂商标识（与扫描/归档目录名对应）
        dir_text = str(file_path.parent)
        for pattern, mapped in _DIR_VENDOR_HINTS:
            if pattern.search(dir_text):
                vendor = mapped
                break
    if not vendor:
        # 3) 文件名规则兜底
        for pattern, mapped in _VENDOR_HINTS:
            if pattern.search(Path(file_name).stem) or pattern.search(hint):
                vendor = mapped
                break
    if not vendor and raw_vendor:
        # 4) 内部制造商名有值但未命中映射表：保留原文（如 "Microsoft Corp."）
        vendor = raw_vendor
    if not vendor:
        vendor = "未知厂商"
    # 厂商值落地硬约束：不允许出现路径分隔符，防止归档时建出嵌套目录（如历史上的 "Adobe/Google"）
    vendor = re.sub(r"[\\/]+", "", vendor).strip() or "未知厂商"

    return {
        "name": name,
        "family": family,
        "vendor": vendor,
        "designer": designer,
    }


def parse_ass_fonts(ass_bytes: bytes) -> List[str]:
    """
    从 ASS 字幕内容中提取所有引用的字体名
    - Style 行的 Fontname 字段
    - Dialogue/Movie/Comment 内 {\fnXXX} 覆盖标签
    编码自适应（UTF-16 / UTF-8），避免 UTF-16 字幕解析出 0 个字体误报「字体完整」。
    """
    text = _decode_ass_text(ass_bytes)
    fonts: List[str] = []
    seen = set()

    def _add(f: str) -> None:
        f = f.strip()
        if f and f not in seen:
            seen.add(f)
            fonts.append(f)

    # {\fnXXXX} 标签
    for m in re.finditer(r"\\fn([^\\}]+)", text):
        _add(m.group(1))

    # Style: Name, Fontname, Fontsize, ...
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("style:") and "," in line:
            parts = [p.strip() for p in line.split(",", 7)]
            if len(parts) >= 2:
                fontname = parts[1]
                if fontname:
                    _add(fontname)

    return fonts


def normalize_font_key(name: str) -> str:
    """字体名归一化，用于模糊匹配（去 @竖排前缀/空格、大小写统一）"""
    import unicodedata

    if not name:
        return ""
    name = name.strip()
    # ASS 竖排变体前缀 @xxx → 与 xxx 合并匹配：字体库有同名字体即算命中
    if name.startswith("@"):
        name = name[1:]
    name = unicodedata.normalize("NFKC", name)
    name = name.replace(" ", "").replace("　", "")
    return name.lower()