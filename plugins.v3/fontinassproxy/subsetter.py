# -*- coding: utf-8 -*-
"""字幕字体代理 — 子集化与 [Fonts] 编码层。

复刻 fontInAss（https://github.com/RiderLty/fontInAss）的编码细节：

- UUEncode 变体（授权来源 src/py2cy/c_utils.pyx）：行宽 80 字符（60 字节数据）、
  字符偏移 33（``!`` 起）、无行首长度字节、无 ``end`` 标记、尾部不足 3 字节不填充、
  数据长度恰为 60 字节倍数时末尾的 ``\\n`` 会被去掉。
- ``[Fonts]`` 段格式（授权来源 src/subsetter.py）：
  ``fontname:{字体名}_{'B' if weight>400}{'I' if italic}0.ttf`` + 编码数据 + 空行。
  插入位置在 ``[Events]`` 之前。
- 代理链路输出编码 UTF-8-sig（带 BOM）。

子集化用 fontTools（而不是 subprocess 调 pyftsubset），便于嵌入错误处理与线程池调用。
"""

from __future__ import annotations

import io
import logging
from typing import Iterable, List, Optional, Set, Tuple

from fontTools import subset
from fontTools.ttLib import TTFont

try:
    import uharfbuzz as hb
except ImportError:      # 未安装则自动回退到 fontTools（见 _subset_impl）
    hb = None

logger = logging.getLogger("FontInAssProxy")

# name 表 tag 的整数值（utils.tag_to_integer("name")），传给 NO_SUBSET_TABLE_TAG
# 以保留 name 表——播放器靠它按字体名匹配内嵌字体，丢了就白嵌。
_NAME_TABLE_TAG = 1851878757

# -- UUEncode 变体参数（对应 c_utils.pyx 的 CHUNK_SIZE / OFFSET）----------------
CHUNK_SIZE = 80   # 每行最多 80 个 ASCII 字符
OFFSET = 33       # 6-bit 值 + 33（'!')，与 ASS 规范一致

_CH_MAP = [chr(i + OFFSET) for i in range(64)]


def uuencode(data: bytes) -> str:
    """对字体二进制做 UUEncode 变体编码，产出为纯 ASCII 字符串，末尾无换行。

    逐行对应 fontInAss c_utils.pyx 的 ``uuencode``：
    - 每 3 字节 -> 4 字符（6-bit 值 + 33）
    - 每累计 80 字符插入一个 ``\\n``
    - 尾部 remainder == 1 -> 2 字符，remainder == 2 -> 3 字符，不填充
    - 若最后恰好是刚插入的换行（数据长度为 60 的倍数）则去掉该换行
    """
    if not data:
        return ""
    out: List[str] = []
    chars_in_line = 0
    n = len(data)
    i = 0
    limit = n - (n % 3)
    while i < limit:
        b0, b1, b2 = data[i], data[i + 1], data[i + 2]
        packed = (b0 << 16) | (b1 << 8) | b2
        out.append(_CH_MAP[(packed >> 18) & 0x3F])
        out.append(_CH_MAP[(packed >> 12) & 0x3F])
        out.append(_CH_MAP[(packed >> 6) & 0x3F])
        out.append(_CH_MAP[packed & 0x3F])
        chars_in_line += 4
        if chars_in_line == CHUNK_SIZE:
            out.append("\n")
            chars_in_line = 0
        i += 3
    rem = n - limit
    if rem == 1:
        packed = data[i] << 16
        out.append(_CH_MAP[(packed >> 18) & 0x3F])
        out.append(_CH_MAP[(packed >> 12) & 0x3F])
    elif rem == 2:
        packed = (data[i] << 16) | (data[i + 1] << 8)
        out.append(_CH_MAP[(packed >> 18) & 0x3F])
        out.append(_CH_MAP[(packed >> 12) & 0x3F])
        out.append(_CH_MAP[(packed >> 6) & 0x3F])
    # 尾部恰好满一行时去掉刚插入的换行
    if chars_in_line == 0 and out and out[-1] == "\n":
        out.pop()
    return "".join(out)


def _sanitize_file_stem(name: str) -> str:
    """字体文件名里不能出现路径分隔 / 控制字符，避免生成出问题文件名。"""
    stem = "".join(ch for ch in name if ch not in ('/', '\\', ':', '*', '?', '"', '<', '>', '|', '\x00'))
    return stem or "Unknown"


def make_font_entry(font_name: str, weight: int, italic: bool, encoded: str) -> str:
    """生成单条 [Fonts] 条目文本。文件名规则同 fontInAss：

    ``{font_name}_{'B' if weight > 400 else ''}{'I' if italic else ''}0.ttf``
    """
    flag_b = "B" if (weight or 0) > 400 else ""
    flag_i = "I" if italic else ""
    filename = f"{_sanitize_file_stem(font_name)}_{flag_b}{flag_i}0.ttf"
    return f"fontname:{filename}\n{encoded}\n"


def inject_fonts(ass_text: str, entries: Iterable[str]) -> str:
    """把 [Fonts] 段插到 ``[Events]`` 之前（与 fontInAss 相同）。"""
    block = "[Fonts]\n" + "".join(entries)
    head, sep, tail = ass_text.partition("[Events]")
    if not sep:
        raise ValueError("字幕中未找到 [Events] 段，无法注入字体")
    return head + block + "\n" + sep + tail


def subset_font_bytes(
    font_bytes: bytes,
    face_index: int,
    unicode_set: Set[int],
    name_id_keep: bool = True,
) -> bytes:
    """对单个字体文件（或 TTC face）做 fontTools 子集化，返回 TTF/OTF 字节。

    - 必须保留 name 表（``opts.name_IDs = ['*']``），否则播放器按字体名匹配不到
      内嵌字体（fontInAss 里对应 NO_SUBSET_TABLE_TAG 保留 name 表）。
    - 不转 woff（flavor=None）。
    - 全字重/斜体等由调用方决定，这里只负责按字形集合子集化。
    """
    try:
        return _subset_impl(font_bytes, face_index, unicode_set, name_id_keep)
    except Exception:
        # 防御：旧版 fontTools 对部分字体（尤其 CFF/大 GBK 集）子集化有 bug，
        # 失败时用最保守的选项重试一次（不再强制保留 name 表全部 ID）
        return _subset_impl(font_bytes, face_index, unicode_set, name_id_keep,
                            conservative=True)


def _subset_impl(font_bytes: bytes, face_index: int, unicode_set: Set[int],
                 name_id_keep: bool = True, conservative: bool = False) -> bytes:
    """子集化：优先 uharfbuzz（C），失败则回退 fontTools（纯 Python）。

    性能差异（15.8MB 思源黑体 / 800 字实测）：
        uharfbuzz    9.6 ms
        fontTools 1320 ms   （约 137 倍差距）
    FontInAss 快就快在这里——它用 uharfbuzz，从不走 fontTools 的子集化。

    额外收益：uharfbuzz 默认做完整布局闭包（GSUB/GPOS/composite 引用字形），
    修复了 fontTools 关掉 layout_features 后复杂文字（阿拉伯/缅甸/天城等）漏
    17%~79% 布局闭包字形的问题。

    回退路径保留原 conservative 语义：旧版 fontTools 对部分字体（尤其 CFF /
    大 GBK 集）子集化有 bug，失败时再用最保守选项重试一次。
    """
    if hb is not None:
        try:
            face = hb.Face(font_bytes, face_index)
            inp = hb.SubsetInput()
            inp.sets(hb.SubsetInputSets.UNICODE).set(unicode_set)
            if name_id_keep:
                inp.sets(hb.SubsetInputSets.NO_SUBSET_TABLE_TAG).set({_NAME_TABLE_TAG})
            out = hb.subset(face, inp)
            return out.blob.data
        except Exception as e:
            logger.warning(f"uharfbuzz 子集化失败，回退 fontTools: {e}")

    opts = subset.Options()
    if not conservative:
        opts.layout_features = []            # 关闭不用的布局特性以缩体积
    opts.notdef_outline = True
    opts.recommended_glyphs = True
    opts.drop_tables += ["DSIG"]
    if name_id_keep:
        opts.name_IDs = ["*"]
        opts.name_legacy = True
    opts.notdef_glyph = True

    font = TTFont(io.BytesIO(font_bytes), fontNumber=face_index, lazy=True)
    sub = subset.Subsetter(options=opts)
    sub.populate(unicodes=unicode_set)
    sub.subset(font)

    buf = io.BytesIO()
    font.save(buf, reorderTables=False)
    font.close()
    return buf.getvalue()


def build_one_entry(
    font_bytes: bytes,
    face_index: int,
    font_name: str,
    weight: int,
    italic: bool,
    unicode_set: Set[int],
) -> Tuple[str, str]:
    """子集化 -> UUEncode -> 组装单条 [Fonts] 条目。

    返回 ``(miss_glyphs: str, entry_text: str)``；miss_glyphs 为空串表示无缺字形。

    两条优化（均对齐 FontInAss）：
      1. 走 uharfbuzz 时顺带从已子集化的 face 上取 unicodes 做差集，缺字检查
         接近零成本；不再调用 _missing_glyphs（它会把完整字体再打开一遍，
         15.8MB 字体实测 78ms/个，12 个字体白烧 0.94 秒）。
      2. 只有回退到 fontTools 时才走老的 _missing_glyphs 路径。
    """
    missed: Set[int] = set()
    if hb is not None:
        try:
            face = hb.Face(font_bytes, face_index)
            inp = hb.SubsetInput()
            inp.sets(hb.SubsetInputSets.UNICODE).set(unicode_set)
            inp.sets(hb.SubsetInputSets.NO_SUBSET_TABLE_TAG).set({_NAME_TABLE_TAG})
            out = hb.subset(face, inp)
            subsetted = out.blob.data
            # 零成本缺字检查：直接用子集化产物的 unicodes 做差集
            if unicode_set:
                missed = set(unicode_set).difference(set(out.unicodes))
            encoded = uuencode(subsetted)
            entry = make_font_entry(font_name, weight, italic, encoded)
            return ("".join(chr(cp) for cp in sorted(missed)) if missed else ""), entry
        except Exception as e:
            logger.warning(f"uharfbuzz 子集化失败，回退 fontTools: {e}")

    subsetted = subset_font_bytes(font_bytes, face_index, unicode_set)
    encoded = uuencode(subsetted)
    entry = make_font_entry(font_name, weight, italic, encoded)
    miss = _missing_glyphs(font_bytes, face_index, unicode_set)
    return miss, entry


def _missing_glyphs(font_bytes: bytes, face_index: int, unicode_set: Set[int]) -> str:
    """返回字体中『确实没有』的字符（用于日志/缺失记录，不阻塞处理）。"""
    if not unicode_set:
        return ""
    try:
        font = TTFont(io.BytesIO(font_bytes), fontNumber=face_index, lazy=True)
        cmap = set()
        for table in font["cmap"].tables:
            cmap.update(table.cmap.keys())
        font.close()
        missing = "".join(chr(cp) for cp in sorted(unicode_set) if cp not in cmap)
        return missing
    except Exception:
        return ""