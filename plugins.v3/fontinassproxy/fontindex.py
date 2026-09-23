# -*- coding: utf-8 -*-
"""字幕字体代理 — 字体索引层。

背景：字体整合包动辄几千个文件，绝不能在请求路径上遍历目录或逐个打开文件。
方案：
- 后台线程全量扫描字体目录，元数据落 SQLite（schema 见规格书第 5 节）。
- watchdog 监听目录增量更新（按 mtime 判断是否重解析）。
- 匹配打分（规格书第 6 节）：精确 > 归一化相等 > 前缀/包含 > 分词近似 > 属性修正。
- 索引未就绪时请求透传，不阻塞 MoviePilot 启动。
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from fontTools.ttLib import TTFont, TTCollection

logger = logging.getLogger("FontInAssProxy")

FONT_EXTENSIONS = (".ttf", ".otf", ".ttc", ".otc")
SCHEMA_VERSION = 3   # 索引结构变更（MS 平台过滤 + 中文名修正），启动自动重建
MATCH_THRESHOLD = 0.6

# ---------------------------------------------------------------------------
# 容器格式优先级（对齐 assfonts 的 ttf/otf 分轮，但细化为四级递减）
#   ASS 规范只允许内嵌 TrueType，故 ttf 最高；ttc 是 ttf 集合，次之；
#   otf/otc 部分播放器仍支持，保底保留。
# 加成幅度刻意很小（<=0.03，远小于名字档位差 0.05+）：
#   格式只在「名字打平」时起作用，永远不能让一个名字更差的 otf 越过 ttf。
# ---------------------------------------------------------------------------
FMT_PRIORITY = {".ttf": 3, ".ttc": 2, ".otf": 1, ".otc": 0}
FMT_BONUS = {".ttf": 0.030, ".ttc": 0.020, ".otf": 0.010, ".otc": 0.0}

# nameID -> 别名种类
_NAME_KIND = {1: "family", 4: "fullname", 6: "psname", 16: "family"}

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS fonts (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    face_index INTEGER DEFAULT 0,
    family TEXT,
    subfamily TEXT,
    fullname TEXT,
    psname TEXT,
    weight INTEGER DEFAULT 400,
    italic INTEGER DEFAULT 0,
    mtime REAL,
    size INTEGER,
    indexed_at REAL,
    UNIQUE(path, face_index)
);
CREATE TABLE IF NOT EXISTS font_aliases (
    font_id INTEGER NOT NULL,
    alias TEXT NOT NULL,
    alias_norm TEXT NOT NULL,
    kind TEXT,
    lang TEXT
);
CREATE INDEX IF NOT EXISTS idx_alias ON font_aliases(alias);
CREATE INDEX IF NOT EXISTS idx_alias_norm
    ON font_aliases(alias_norm COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_font_id
    ON font_aliases(font_id);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


# --------------------------------------------------------------------------
# 字体元数据解析
# --------------------------------------------------------------------------

def _fmt_of(path: Optional[str]) -> str:
    """取字体容器格式后缀（小写，含点）。"""
    return os.path.splitext(path or "")[1].lower()


def _fmt_priority(path: Optional[str]) -> int:
    """容器格式优先级：ttf(3) > ttc(2) > otf(1) > otc(0)。未知返回 -1。"""
    return FMT_PRIORITY.get(_fmt_of(path), -1)


def _fmt_bonus(path: Optional[str]) -> float:
    """容器格式加成：ttf 0.030 > ttc 0.020 > otf 0.010 > otc 0。"""
    return FMT_BONUS.get(_fmt_of(path), 0.0)


def _subfamily_weight(header: Optional[str]) -> Optional[int]:
    """从 subfamily 名推断字重。"""
    if not header:
        return None
    low = header.lower()
    if "black" in low:
        return 900
    if "heavy" in low or "extrabold" in low:
        return 800
    if "bold" in low:
        return 700
    if "semibold" in low or "demibold" in low:
        return 600
    if "medium" in low:
        return 500
    if "light" in low:
        return 300
    if "thin" in low:
        return 100
    return None


def _decode_name(rec) -> str:
    """解码单条 name 记录（中文名正确性的关键）。

    实测（本机 1.86 万条 name 记录扫库）MS 平台 enc=2/3 记录存在多种真实存储：
      - UTF-16BE（HG 平成明朝体：\\x00H\\x00G...）
      - UTF-16BE 纯中文（思源黑体：高字节是汉字码位，无 0x00）
      - GB2312/BIG5（汉鼎繁新艺体：\\xba\\xba\\xb6\\xa6...）
      - 纯 ASCII（'HanDing-CS-Fonts'）
    fontTools 的 toUnicode() 对部分 enc=2/3 会用 shift_jis 解出乱码（如把 GBK
    中文解成韩文），但不能一概按 UTF-16BE（会把 GBK 解成韩文）。故采用
    「多路解码 + 内容评分择优」：

      对每条记录用 utf-16-be / utf-16-le / gbk / gb18030 / big5 全部尝试，
      对每个成功解码结果按内容质量打分：
        控制字符         -10
        U+FFFD/U+FFFE    -5
        韩文音节         -2（中/日文字体里大量韩文基本可判定为错解）
        汉字(4E00-9FFF)   +3
        日文假名          +2
        ASCII 字母数字    +1
      取最高分；全部 <=0 或全失败时保底 rec.toUnicode()。
    """
    raw = getattr(rec, "string", None)
    if not isinstance(raw, (bytes, bytearray)):
        try:
            t = rec.toUnicode()
            return t.replace("\n", " ").strip() if t else ""
        except Exception:
            return ""
    b = bytes(raw).rstrip(b"\x00")

    def _score(t: str) -> int:
        s = 0
        for ch in t:
            o = ord(ch)
            if o < 0x20 or o == 0x7F:
                s -= 10
            elif o in (0xFFFD, 0xFFFE):
                s -= 5
            elif 0xAC00 <= o <= 0xD7A3:        # 韩文音节
                s -= 2
            elif 0x4E00 <= o <= 0x9FFF:        # CJK 汉字
                s += 3
            elif 0x3040 <= o <= 0x30FF:        # 日文假名
                s += 2
            elif (0x30 <= o <= 0x39 or 0x41 <= o <= 0x5A or 0x61 <= o <= 0x7A):
                s += 1
        return s

    best, best_score = "", float("-inf")
    for codec, weight in (("utf-16-be", 0), ("utf-16-le", 0), ("gbk", 0), ("gb18030", 0), ("big5", 0)):
        try:
            t = b.decode(codec)
        except Exception:
            continue
        if not t or not t.strip():
            continue
        t = t.replace("\x00", "").strip()
        sc = _score(t)
        if sc > best_score:
            best, best_score = t, sc
    if best_score > 0:
        return best.replace("\n", " ").strip()
    try:
        t = rec.toUnicode()
        if t and t.strip():
            return t.replace("\n", " ").strip()
    except Exception:
        pass
    return ""


def _name_records(font: TTFont) -> List[Tuple[int, int, str]]:
    """返回 (kind, 语言标记, 名称)。

    对齐 assfonts（font_parser.cc::ParseFontName）：只采集 Microsoft 平台
    (platformID=3) 的名字。字幕里写的名字就是 Windows 下看到的那个，Mac 平台名
    往往不同，收进来只会污染候选池、制造误匹配。
    少数字体只带 Mac 名字，此时回退全平台，避免整份字体无别名可用。
    """
    records: List[Tuple[int, int, str]] = []
    try:
        name_table = font["name"]
    except KeyError:
        return records

    def _collect(ms_only: bool) -> List[Tuple[int, int, str]]:
        out: List[Tuple[int, int, str]] = []
        for rec in name_table.names:
            if rec.nameID not in _NAME_KIND:
                continue
            if ms_only and getattr(rec, "platformID", None) != 3:
                continue
            text = _decode_name(rec)
            if not text or not text.strip():
                continue
            kind = _NAME_KIND[rec.nameID]
            if rec.platformID == 3:  # windows
                lang = "zh" if rec.langID in (0x0804, 0x0404) else \
                    "ja" if rec.langID == 0x0411 else \
                    "en" if rec.langID == 0x0409 else \
                    "zh" if rec.nameID == 1 else "en"
                # encodingID 2=PRC(GB2312) 3=BIG5：声明为中文，强制标 zh
                if getattr(rec, "platEncID", None) in (2, 3):
                    lang = "zh"
            else:
                lang = "en"
            out.append((kind, lang, text.replace("\n", " ").strip()))
        return out

    records = _collect(ms_only=True)
    if not records:          # 仅 Mac 名字的字体：回退全平台，避免索引空别名
        records = _collect(ms_only=False)
    return records


def parse_font_file(path: str) -> List[Dict]:
    """解析单个字体文件（含 TTC 多 face），返回 face 元数据列表。"""
    results: List[Dict] = []
    try:
        with open(path, "rb") as f:
            head = f.read(4)
        is_collection = head == b"ttcf"
    except OSError:
        return results

    fonts: Sequence[TTFont] = []
    try:
        if is_collection:
            coll = TTCollection(path, lazy=True)
            fonts = coll.fonts
        else:
            fonts = [TTFont(path, lazy=True, fontNumber=0)]
    except Exception as exc:
        logger.warning(f"无法打开字体文件: {path}: {exc}")
        return results

    for face_index, font in enumerate(fonts):
        try:
            info = _extract_face(font, path, face_index)
            if info:
                results.append(info)
        except Exception as exc:
            logger.warning(f"解析字体异常 {path}(face {face_index}): {exc}")
        finally:
            try:
                font.close()
            except Exception:
                pass
    return results


def _extract_face(font: TTFont, path: str, face_index: int) -> Optional[Dict]:
    """提取单个 face 的身家信息。"""
    family = subfamily = fullname = psname = ""
    # 优先 windows 平台英文名，其次任何平台
    best = {k: "" for k in ("family", "fullname", "psname")}
    sub_names: List[str] = []
    try:
        name_table = font["name"]
        for rec in name_table.names:
            try:
                text = rec.toUnicode()
            except Exception:
                continue
            if not text or not text.strip():
                continue
            if rec.nameID == 1 and (rec.platformID == 3 or not best["family"]):
                family = family or text
                if rec.platformID == 3:
                    best["family"] = best["family"] or text
                    family = best["family"]
            elif rec.nameID == 2:
                sub_names.append(text)
            elif rec.nameID == 4 and (rec.platformID == 3 or not best["fullname"]):
                fullname = fullname or text
                if rec.platformID == 3:
                    best["fullname"] = best["fullname"] or text
                    fullname = best["fullname"]
            elif rec.nameID == 6 and not psname:
                psname = text
        subfamily = sub_names[0] if sub_names else family
    except (KeyError, Exception):
        pass

    # 字重/斜体
    weight = 400
    italic = False
    try:
        if "OS/2" in font:
            os2 = font["OS/2"]
            weight = int(getattr(os2, "usWeightClass", 400) or 400)
            italic = bool(getattr(os2, "fsSelection", 0) & 0x01)
    except Exception:
        pass
    if not italic:
        try:
            if "head" in font:
                italic = bool(getattr(font["head"], "macStyle", 0) & 0x02)
        except Exception:
            pass
    if weight == 400 or not weight:
        sub_w = _subfamily_weight(subfamily)
        if sub_w is not None:
            weight = sub_w
    if not italic:
        low_sub = (subfamily or "").lower()
        italic = "italic" in low_sub or "oblique" in low_sub

    if not family and not fullname and not psname:
        return None

    return {
        "path": path,
        "face_index": face_index,
        "family": family,
        "subfamily": subfamily,
        "fullname": fullname,
        "psname": psname,
        "weight": weight or 400,
        "italic": 1 if italic else 0,
        "size": os.path.getsize(path),
        "mtime": os.path.getmtime(path),
        "names": _name_records(font),
    }


# --------------------------------------------------------------------------
# 归一化与打分（规格书第 6 节）
# --------------------------------------------------------------------------

_RE_NONWORD = re.compile(r"[\s_\-]+")


def normalize_name(name: str) -> str:
    """去空格/下划线/连字符并转小写。"""
    return _RE_NONWORD.sub("", name).lower()


def _tokenize(name: str) -> Set[str]:
    """按空格与 camelCase 边界切词。"""
    words = set()
    for part in name.split():
        # camelCase 切分
        parts = re.split(r"(?<=[a-z0-9])(?=[A-Z])", part)
        for p in parts:
            p = p.strip()
            if p:
                words.add(p.lower())
    return words


def _expand_grams(name: str) -> List[str]:
    """把查询名扩展为匹配用的 gram 集合。

    - 英文/日文/空格分段直接保留；
    - 连续中文段按长度 2/3 滑窗切成 gram（如 方正筑紫明朝宋 -> 方正/筑紫/明朝/方正筑/筑紫明...），
      使「字幕写 方正筑紫明朝宋 简繁、字库是 方正FW筑紫明朝 简 D」这类仅局部重合的能命中。
    返回按长度降序、去重的 gram 列表（长 gram 更具体，优先用）。
    """
    grams: "Set[str]" = set()
    for seg in re.split(r"[\s_\-]+", name):
        if not seg:
            continue
        # 含中文的段：滑窗切 gram
        cjk_run = re.sub(r"[^\u4e00-\u9fff]+", "", seg)
        if cjk_run and len(cjk_run) >= 2:
            for n in (2, 3):
                for i in range(0, len(cjk_run) - n + 1):
                    grams.add(cjk_run[i:i + n])
        # 纯字母/数字段（非中文主体）保留原词
        if not seg or not re.search(r"[\u4e00-\u9fff]", seg):
            grams.add(seg.lower())
    return sorted(grams, key=len, reverse=True)


def _alias_exact(q_norm: str, cand: Dict) -> bool:
    """候选是否含「归一化后与查询全等」的名字（对齐 assfonts 的 std::find 全等）。

    与 LIKE 包含不同：全等不会让「微软雅黑」吃掉「微软雅黑 UI」的查询。
    检查范围：内部名(family/subfamily/fullname/psname) + 全部别名 + 文件名字干。
    """
    norms = [
        normalize_name(cand.get("family") or ""),
        normalize_name(cand.get("subfamily") or ""),
        normalize_name(cand.get("fullname") or ""),
        normalize_name(cand.get("psname") or ""),
    ]
    norms += [an for _k, _l, _t, an in (cand.get("names") or []) if an]
    norms.append(normalize_name(
        os.path.splitext(os.path.basename(cand.get("path") or ""))[0]))
    return q_norm in norms


def _cjk_grams(name: str) -> Set[str]:
    """取名称中全部中文的 2 字滑窗 gram（只取中文，跨非中文字符不中断）。"""
    chars = re.findall(r"[\u4e00-\u9fff]", name or "")
    if len(chars) < 2:
        return set()
    return {chars[i] + chars[i + 1] for i in range(len(chars) - 1)}


def score_font(query_name: str, query_weight: int, query_italic: bool,
               font: Dict) -> float:
    """对单个字体记录打分，返回 [0,1]，越高越匹配。

    匹配策略（对齐 assfonts：内部名 > 文件名）：
      1. 内部名（family/full/psname + 全部别名）精确 -> 0.95（最高）
      2. 文件名精确                          -> 0.90（字幕组常按文件名写字幕名）
      3. 内部名包含 / 互为前缀               -> 0.75
      4. 文件名包含                          -> 0.72
      5. 分词集合重叠（英文/日文有效）        -> 0.4 + 0.5 * 重叠率
      6. 中文 gram 覆盖兜底（宽松候选）      -> 0.45 + 0.4 * 覆盖度
    最后叠加格式加成（ttf>ttc>otf>otc，幅度 < 档位差）与属性修正（字重/斜体惩罚）。
    """
    query_norm = normalize_name(query_name)
    if not query_norm:
        return 0.0
    query_tokens = _tokenize(query_name)

    stem = os.path.splitext(os.path.basename(font.get("path") or ""))[0]
    stem_norm = normalize_name(stem)

    aliases = [
        font.get("family") or "", font.get("subfamily") or "",
        font.get("fullname") or "", font.get("psname") or "",
    ]
    # 性能-2：aliases_norm 直接用库里现成的 alias_norm（文件名字干也已在
    # replace_path 时作为 kind=filename 别名入库），不再每候选跑正则归一化。
    aliases_norm = [normalize_name(a) for a in aliases]
    for kind, lang, text, anorm in font.get("names") or []:
        aliases.append(text)
        aliases_norm.append(anorm or normalize_name(text))

    base = 0.0
    # 1) 内部名（最高优先级；先测内部名，避免「微软雅黑.ttf」顶掉内部名更精确的
    #    「Microsoft YaHei UI」——精确匹配不能输给部分匹配）
    for alias_norm in aliases_norm:
        if not alias_norm:
            continue
        if alias_norm == query_norm:
            base = max(base, 0.95)
        elif alias_norm in query_norm or query_norm in alias_norm:
            base = max(base, 0.75)

    # 2) 文件名（降为兜底：仅当内部名未命中时才可能主导）
    if stem_norm and stem_norm == query_norm:
        base = max(base, 0.90)
    elif stem_norm and (stem_norm in query_norm or query_norm in stem_norm):
        base = max(base, 0.72)

    # 3) 分词集合重叠（英文/日文有效；纯中文无空格分词，此路径对中文失效）
    if base < 0.75:
        for alias in aliases:
            if not alias:
                continue
            alias_tokens = _tokenize(alias)
            if query_tokens and alias_tokens and query_tokens & alias_tokens:
                overlap = len(query_tokens & alias_tokens) / len(query_tokens | alias_tokens)
                base = max(base, 0.4 + 0.5 * overlap)
    if base <= 0:
        # 4) gram 级兜底（宽松候选专用）：中文 2 字滑窗覆盖度
        #    「方正筑紫明朝宋 简繁」→「方正FW筑紫明朝 简 D」这类仅中文字符局部重合
        query_grams = _cjk_grams(query_name)
        if len(query_grams) >= 2:
            for t in [stem] + [a for a in aliases if a]:
                cand_grams = _cjk_grams(t)
                if not cand_grams:
                    continue
                inter = len(query_grams & cand_grams)
                if inter >= 2:
                    cover = inter / len(query_grams)
                    base = max(base, 0.45 + 0.4 * cover)
    if base <= 0:
        return 0.0

    # 属性修正（仅对候选有效，小幅惩罚）
    penalty = 0.0
    font_weight = int(font.get("weight") or 400)
    font_italic = bool(font.get("italic"))
    if query_weight and font_weight:
        diff_weight = abs(font_weight - query_weight)
        if diff_weight > 150:
            penalty += 0.25
        elif diff_weight > 50:
            penalty += 0.10
    if query_italic != font_italic:
        penalty += 0.15
    score = max(0.0, base - penalty)

    # 格式加成：ttf 0.030 > ttc 0.020 > otf 0.010 > otc 0
    # 幅度(<=0.03) 小于相邻名字档位差(>=0.05)，保证格式只在同档内打破平局，
    # 绝不会让一个名字更差的 otf 越过名字更好的 ttf。
    if score > 0:
        score = min(1.0, score + _fmt_bonus(font.get("path") or ""))
    return round(score, 3)


# --------------------------------------------------------------------------
# SQLite 存储
# --------------------------------------------------------------------------

class _FontDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        # RLock：可重入，串行化所有 conn 访问（worker 并发 + watchdog 写共用同一连接，
        # 不加锁并发 execute 会抛 sqlite3.InterfaceError: bad parameter or other API misuse）
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self._create_tables()

    def _create_tables(self):
        with self._lock:
            cur = self.conn.cursor()
            cur.executescript(_SCHEMA_SQL)
            v = self.meta_get("schema_version")
            if v != str(SCHEMA_VERSION):
                self._drop_all()
                cur.executescript(_SCHEMA_SQL)
                self.meta_set("schema_version", str(SCHEMA_VERSION))
                self.meta_set("index_version", "0")
            self.conn.commit()

    def _drop_all(self):
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("DROP TABLE IF EXISTS fonts")
            cur.execute("DROP TABLE IF EXISTS font_aliases")

    # -- meta --
    def meta_get(self, key: str, default: str = "") -> str:
        with self._lock:
            cur = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,))
            row = cur.fetchone()
            return row[0] if row else default

    def meta_set(self, key: str, value: str):
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO meta(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            self.conn.commit()

    def index_version(self) -> int:
        try:
            return int(self.meta_get("index_version", "0") or 0)
        except ValueError:
            return 0

    def bump_version(self):
        self.meta_set("index_version", str(self.index_version() + 1))

    # -- 数据 --
    def known_paths(self) -> Set[str]:
        with self._lock:
            rows = self.conn.execute("SELECT DISTINCT path FROM fonts").fetchall()
            return {r[0] for r in rows}

    def font_meta(self, path: str):
        """取单字体文件 mtime/size（增量更新判断，加锁防并发）。"""
        with self._lock:
            return self.conn.execute(
                "SELECT mtime, size FROM fonts WHERE path=? LIMIT 1", (path,)
            ).fetchone()

    @staticmethod
    def _replace_one(cur, path: str, faces: List[Dict]) -> None:
        """替换单个 path 的全部 face（调用方持锁/事务内执行）。

        性能-3：先按 path 取旧 id 列表，按 id 删别名，再删 fonts 行——
        避免 NOT IN (SELECT id FROM fonts) 的全表孤儿清理。
        """
        old_ids = [r[0] for r in cur.execute(
            "SELECT id FROM fonts WHERE path=?", (path,)).fetchall()]
        for oid in old_ids:
            cur.execute("DELETE FROM font_aliases WHERE font_id=?", (oid,))
        cur.execute("DELETE FROM fonts WHERE path=?", (path,))
        for face in faces:
            cur.execute(
                "INSERT INTO fonts(path, face_index, family, subfamily, fullname, "
                "psname, weight, italic, mtime, size, indexed_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (face["path"], face["face_index"], face["family"],
                 face["subfamily"], face["fullname"], face["psname"],
                 face["weight"], face["italic"], face["mtime"], face["size"],
                 time.time()),
            )
            font_id = cur.lastrowid
            seen = set()
            for kind, lang, text in face.get("names") or []:
                t = text.strip()
                if not t or (kind, lang, t) in seen:
                    continue
                seen.add((kind, lang, t))
                cur.execute(
                    "INSERT INTO font_aliases(font_id, alias, alias_norm, kind, lang) "
                    "VALUES(?,?,?,?,?)",
                    (font_id, t, normalize_name(t), kind, lang),
                )
            # 基础别名：family/fullname/psname + 文件名字干（kind=filename，优先级最高）
            for alias, kind in ((face["family"], "family"),
                                (face["fullname"], "fullname"),
                                (face["psname"], "psname"),
                                (os.path.splitext(os.path.basename(face["path"]))[0],
                                 "filename")):
                if alias:
                    cur.execute(
                        "INSERT INTO font_aliases(font_id, alias, alias_norm, kind, lang) "
                        "VALUES(?,?,?,?,?)",
                        (font_id, alias, normalize_name(alias), kind, "en"),
                    )

    def replace_path(self, path: str, faces: List[Dict]):
        """删除 path 全部 face 并重新插入（增量更新单文件）。"""
        with self._lock:
            cur = self.conn.cursor()
            self._replace_one(cur, path, faces)
            self.conn.commit()

    def replace_paths_batch(self, items: List[Tuple[str, List[Dict]]]) -> None:
        """批量替换（性能-4）：一批文件共享一个事务提交。items=[(path, faces), ...]"""
        with self._lock:
            cur = self.conn.cursor()
            for path, faces in items:
                self._replace_one(cur, path, faces)
            self.conn.commit()

    def remove_path(self, path: str):
        with self._lock:
            cur = self.conn.cursor()
            old_ids = [r[0] for r in cur.execute(
                "SELECT id FROM fonts WHERE path=?", (path,)).fetchall()]
            for oid in old_ids:
                cur.execute("DELETE FROM font_aliases WHERE font_id=?", (oid,))
            cur.execute("DELETE FROM fonts WHERE path=?", (path,))
            self.conn.commit()

    def font_count(self) -> int:
        with self._lock:
            row = self.conn.execute("SELECT COUNT(*) FROM fonts").fetchone()
            return row[0] if row else 0

    def query_candidates(self, query_norm: str) -> List[Dict]:
        """取可能的匹配候选（归一化别名 LIKE + NOCASE，按长度排序）。

        关键：fonts 表的 family/fullname/psname 常只存英文/拼音记录，
        真正的名称（如中文「方正筑紫明朝宋 简繁」）在 font_aliases 表里。
        这里把该字体全部别名原文用 GROUP_CONCAT 带回，供 score_font 用真实名打分。
        """
        like = f"%{query_norm}%"
        with self._lock:
            rows = self.conn.execute(
                "SELECT f.id, f.path, f.face_index, f.family, f.subfamily, "
                "f.fullname, f.psname, f.weight, f.italic, "
                "GROUP_CONCAT(a.alias, char(1)), "
                "GROUP_CONCAT(a.alias_norm, char(1)) "
                "FROM fonts f JOIN font_aliases a ON a.font_id = f.id "
                "WHERE a.alias_norm LIKE ? COLLATE NOCASE "
                "GROUP BY f.id "
                "ORDER BY MIN(length(a.alias_norm)) LIMIT 200",
                (like,),
            ).fetchall()
        return [self._row_to_cand(r) for r in rows]

    def query_candidates_loose(self, query_name: str, limit: int = 300) -> List[Dict]:
        """分词/gram 级宽松候选：连续 LIKE 查不到时，按 gram 交集查询。

        处理「字幕写 方正筑紫明朝宋 简繁、字库是 方正FW筑紫明朝 简 D」这类
        仅局部重合的场景。gram 为中文滑窗 2/3 字 + 非中文原词。

        排序关键：通用 gram（方正/明朝）会命中数千候选，若按别名长度排，
        长别名的高契合字体反而被挤出候选池。改为按「命中 gram 数」降序，
        重合越多排名越靠前，保证高契合字体进入打分环节。
        """
        grams = _expand_grams(query_name)
        if not grams:
            return []
        likes = [f"%{g}%" for g in grams[:30]]
        n = len(likes)
        # 每个 LIKE 命中计 1 分，求和得 hits = 命中 gram 数
        hits_expr = " + ".join(["(CASE WHEN a.alias_norm LIKE ? COLLATE NOCASE THEN 1 ELSE 0 END)"] * n)
        where_or = " OR ".join(["a.alias_norm LIKE ? COLLATE NOCASE"] * n)
        sql = (
            "SELECT f.id, f.path, f.face_index, f.family, f.subfamily, "
            "f.fullname, f.psname, f.weight, f.italic, "
            "GROUP_CONCAT(a.alias, char(1)), "
            "GROUP_CONCAT(a.alias_norm, char(1)), (" + hits_expr + ") AS hits "
            "FROM fonts f JOIN font_aliases a ON a.font_id = f.id "
            f"WHERE {where_or} "
            "GROUP BY f.id "
            "ORDER BY hits DESC, MIN(length(a.alias_norm)) LIMIT ?"
        )
        params = likes + likes + [limit]
        with self._lock:
            rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_cand(r) for r in rows]

    @staticmethod
    def _row_to_cand(r) -> Dict:
        # r: 前 9 列同 fonts 表；r[9] 全部别名原文、r[10] 对应 alias_norm（\x01 分隔）；
        # r[11] 为 hits（仅宽松查询有）
        names = []
        norm_parts = str(r[10]).split("\x01") if len(r) > 10 and r[10] else []
        if len(r) > 9 and r[9]:
            for i, t in enumerate(str(r[9]).split("\x01")):
                if not t:
                    continue
                an = norm_parts[i] if i < len(norm_parts) else ""
                names.append(("", "", t, an))
        return {
            "id": r[0], "path": r[1], "face_index": r[2], "family": r[3],
            "subfamily": r[4], "fullname": r[5], "psname": r[6],
            "weight": r[7], "italic": r[8], "names": names,
        }

    def close(self):
        with self._lock:
            self.conn.close()


# --------------------------------------------------------------------------
# 目录监听（watchdog；缺失时降级轮询）
# --------------------------------------------------------------------------

class FontIndex:
    """字体索引：后台扫描 + watchdog 增量 + 匹配查询。"""

    def __init__(self, db_path: str, font_dirs: List[str],
                 report: Optional["Callable[[str], None]"] = None):
        self.db = _FontDB(db_path)
        self.font_dirs = [d for d in font_dirs if d and os.path.isdir(d)]
        self._ready = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._observer = None
        self._poll_timer: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        # 变更报告回调（插件主类传入 MP logger，让索引日志进入插件日志文件）
        self._report = report
        # 目录变更统计（供插件定时消费通知用户）
        self._changes = {"added": 0, "removed": 0, "modified": 0}
        self._changes_lock = threading.Lock()
        # 性能-2：match 结果进程内 LRU（字幕字体名重复率极高），随 index_version 失效
        self._match_cache: "OrderedDict" = OrderedDict()
        self._match_cache_lock = threading.Lock()
        self._match_vsn = -1
        _MATCH_CACHE_MAX = 1024
        self._match_cache_max = _MATCH_CACHE_MAX

    def _log(self, msg: str) -> None:
        if self._report:
            try:
                self._report(msg)
                return
            except Exception:
                pass
        logger.info(msg)

    # -- 变更统计（供 UI/通知消费） --
    def note_changes(self, added: int = 0, removed: int = 0,
                     modified: int = 0) -> None:
        if added or removed or modified:
            with self._changes_lock:
                self._changes["added"] += added
                self._changes["removed"] += removed
                self._changes["modified"] += modified

    def drain_changes(self) -> Tuple[int, int, int]:
        """取出并清零累计变更数，返回 (added, removed, modified)。"""
        with self._changes_lock:
            added = self._changes["added"]
            removed = self._changes["removed"]
            modified = self._changes["modified"]
            self._changes["added"] = 0
            self._changes["removed"] = 0
            self._changes["modified"] = 0
        return added, removed, modified

    # -- 生命周期 --
    def start(self):
        """启动后台全量扫描（不阻塞调用方）。"""
        if not self.font_dirs:
            logger.warning("未配置字体目录，索引为空")
            return
        self._thread = threading.Thread(target=self._run_scan_loop, daemon=True)
        self._thread.start()
        self._start_watchdog()

    def _start_watchdog(self):
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
            from watchdog.observers.polling import PollingObserver

            class _Handler(FileSystemEventHandler):
                def __init__(self, owner):
                    self.owner = owner

                def on_created(self, event):
                    self.owner._handle_event_path(event.src_path, "added")

                def on_deleted(self, event):
                    self.owner._handle_event_path(event.src_path, "removed")

                def on_modified(self, event):
                    self.owner._handle_event_path(event.src_path, "modified")

                def on_moved(self, event):
                    self.owner._handle_event_path(event.dest_path, "added")

            handler = _Handler(self)
            try:
                observer = Observer()
            except Exception:
                observer = PollingObserver()
            for d in self.font_dirs:
                observer.schedule(handler, d, recursive=True)
            observer.daemon = True
            observer.start()
            self._observer = observer
            logger.info("字体目录 watchdog 已启动")
        except Exception as exc:
            logger.warning(f"watchdog 不可用，降级为 60s 轮询: {exc}")
            self._start_polling()

    def _start_polling(self):
        def loop():
            while not self._stop.is_set():
                try:
                    self._poll_diff()
                except Exception as exc:
                    logger.warning(f"轮询扫描异常: {exc}")
                self._stop.wait(60)

        t = threading.Thread(target=loop, daemon=True)
        t.start()
        self._poll_timer = t

    # -- 扫描 --
    def _run_scan_loop(self):
        try:
            self._full_scan()
            # 防御：库里有字体但版本仍是 0（如 schema 升级重建后漏 bump），强制 bump 一次
            try:
                if self.db.font_count() > 0 and self.db.index_version() == 0:
                    self.db.bump_version()
                    self._log("字体索引版本重置为 1（防御性 bump）")
            except Exception:
                pass
        except Exception as exc:
            logger.exception(f"全量扫描失败: {exc}")
        finally:
            self._ready = True
            logger.info(f"字体索引就绪: {self.db.font_count()} 个 face")

    def _full_scan(self) -> int:
        changed = 0
        added = 0
        removed = 0
        modified = 0
        known = self.db.known_paths()
        current: Set[str] = set()
        for d in self.font_dirs:
            for root, _, files in os.walk(d):
                for fn in files:
                    if not fn.lower().endswith(FONT_EXTENSIONS):
                        continue
                    current.add(os.path.join(root, fn))
        # 删除的
        for path in known - current:
            self.db.remove_path(path)
            changed += 1
            removed += 1
        # 新增/变更：解析放线程池（性能-4），SQLite 写入仍单线程但攒批提交
        need = [p for p in current if self._needs_reindex(p, known)]
        if need:
            workers = min(8, max(4, os.cpu_count() or 4))
            batch: List[Tuple[str, List[Dict]]] = []
            with ThreadPoolExecutor(max_workers=workers,
                                    thread_name_prefix="fias-scan") as pool:
                for path, faces in zip(need, pool.map(parse_font_file, need)):
                    if not faces:
                        continue
                    batch.append((path, faces))
                    changed += 1
                    if path not in known:
                        added += 1
                    else:
                        modified += 1
                    if len(batch) >= 300:      # 攒批提交（性能-4）
                        self.db.replace_paths_batch(batch)
                        batch = []
            if batch:
                self.db.replace_paths_batch(batch)
        if changed:
            self.db.bump_version()
        self.note_changes(added=added, removed=removed, modified=modified)
        self._log(f"字体索引全量扫描完成：新增 {added} 个，修改 {modified} 个，删除 {removed} 个，"
                  f"当前 {self.db.font_count()} face")
        return changed

    def _needs_reindex(self, path: str, known: Set[str]) -> bool:
        if path not in known:
            return True
        try:
            mtime = os.path.getmtime(path)
            size = os.path.getsize(path)
        except OSError:
            return False
        row = self.db.font_meta(path)
        return not row or abs((row[0] or 0) - mtime) > 1e-6 or row[1] != size

    def _poll_diff(self):
        """轮询兜底：对比 mtime 增量更新。"""
        known = self.db.known_paths()
        current: Set[str] = set()
        for d in self.font_dirs:
            for root, _, files in os.walk(d):
                for fn in files:
                    if fn.lower().endswith(FONT_EXTENSIONS):
                        current.add(os.path.join(root, fn))
        changed = 0
        added = 0
        removed = 0
        modified = 0
        for path in known - current:
            self.db.remove_path(path)
            changed += 1
            removed += 1
        need = [p for p in current if self._needs_reindex(p, known)]
        batch: List[Tuple[str, List[Dict]]] = []
        for path in need:
            faces = parse_font_file(path)
            if not faces:
                continue
            batch.append((path, faces))
            changed += 1
            if path not in known:
                added += 1
            else:
                modified += 1
            if len(batch) >= 300:
                self.db.replace_paths_batch(batch)
                batch = []
        if batch:
            self.db.replace_paths_batch(batch)
        if changed:
            self.db.bump_version()
        self.note_changes(added=added, removed=removed, modified=modified)
        if changed:
            self._log(f"字体目录增量扫描：新增 {added} 个，修改 {modified} 个，删除 {removed} 个，"
                      f"当前 {self.db.font_count()} face")

    def _handle_event_path(self, src_path: str, event_type: str = "added"):
        """watchdog 事件：单个文件增量处理（在 Observer 线程执行）。

        轻微-6：modified 事件计入「修改」而非「新增」，统计口径不失真。
        """
        if not src_path or not src_path.lower().endswith(FONT_EXTENSIONS):
            return
        try:
            if os.path.exists(src_path):
                # 目录事件忽略
                if os.path.isdir(src_path):
                    return
                self.db.replace_path(src_path, parse_font_file(src_path))
                if event_type == "modified":
                    self.note_changes(modified=1)
                    self._log(f"字体目录变更：修改 {os.path.basename(src_path)}")
                else:
                    self.note_changes(added=1)
                    self._log(f"字体目录变更：新增 {os.path.basename(src_path)}")
            else:
                self.db.remove_path(src_path)
                self.note_changes(removed=1)
                self._log(f"字体目录变更：删除 {os.path.basename(src_path)}")
            self.db.bump_version()
        except Exception as exc:
            logger.warning(f"watchdog 增量更新失败 {src_path}: {exc}")

    # -- 查询 --
    def ready(self) -> bool:
        return self._ready

    def match(self, font_name: str, weight: int = 400,
              italic: bool = False) -> Optional[Tuple[str, int]]:
        """按字体名 + 属性匹配，返回 (path, face_index) 或 None。

        分层匹配（对齐 assfonts FontSubsetter::FindFont 的语义，但保留模糊兜底）：

          第 1 层 严格全等 —— 归一化后与内部名/别名/文件名字干完全相等。
                 命中则在层内按「容器格式优先级 ttf>ttc>otf>otc」降序、
                 同格式按属性距离升序挑一个。找不到 ttf 就顺位用 otf。
          第 2 层 模糊打分 —— 仅当第 1 层全军覆没时启用（score_font，含格式加成）。

        这样做的原因：assfonts 之所以配得准，不是打分聪明，而是它根本不打分——
        先严格全等，名字对不上直接不算候选。模糊只作兜底，避免它越级压过精确。
        """
        q = normalize_name(font_name or "")
        if not q:
            return None

        # 性能-2：进程内 LRU——字幕字体名重复率极高，命中直接返回
        cache_key = (q, weight, italic)
        with self._match_cache_lock:
            vsn = self.db.index_version()
            if vsn != self._match_vsn:
                self._match_cache.clear()
                self._match_vsn = vsn
            hit = self._match_cache.get(cache_key)
            if hit is not None:
                self._match_cache.move_to_end(cache_key)
                return hit[0] if hit[0] is not None else None

        # 候选池：连续 LIKE + 宽松 gram 候选合并去重（原来是互斥的，会漏召回）
        # 中等-4：重建(drop)瞬间缺表会抛 OperationalError，防御性返回 None（走透传）
        try:
            cands = self.db.query_candidates(q)
            loose = self.db.query_candidates_loose(font_name)
        except sqlite3.OperationalError:
            return None
        if loose:
            seen = {c["id"] for c in cands}
            cands = cands + [c for c in loose if c["id"] not in seen]

        # 第 1 层：严格全等
        exact = [c for c in cands if _alias_exact(q, c)]
        if exact:
            def _key(c):
                # 格式优先级降序 -> 属性距离升序 -> 路径稳定序
                dist = abs(int(c.get("weight") or 400) - weight) \
                    + (110 if bool(c.get("italic")) != bool(italic) else 0)
                return (-_fmt_priority(c["path"]), dist, c["path"])
            best = min(exact, key=_key)
            return best["path"], best["face_index"]

        # 第 2 层：模糊打分（score_font 内已叠加格式加成）
        best = None
        best_score = 0.0
        for row in cands:
            sc = score_font(font_name, weight, italic, row)
            if sc > best_score:
                best_score = sc
                best = row
        result: Optional[Tuple[str, int]] = None
        if best is not None and best_score >= MATCH_THRESHOLD:
            result = (best["path"], best["face_index"])
        with self._match_cache_lock:
            self._match_cache[cache_key] = (result,)
            self._match_cache.move_to_end(cache_key)
            if len(self._match_cache) > self._match_cache_max:
                self._match_cache.popitem(last=False)
        return result

    def rebuild(self) -> int:
        """显式重建（同步，供命令调用）。

        中等-4：重建期间把 _ready 置 False，让并发请求直接走透传，避免
        查到正在重插的残缺数据；drop 与 recreate 之间的缺表窗口也有防御。
        """
        self._ready = False
        try:
            self.db._drop_all()
            self.db._create_tables()
            n = self._full_scan()
        finally:
            self._ready = True
        return n

    def close(self):
        self._stop.set()
        if self._observer:
            try:
                self._observer.stop()
            except Exception:
                pass
            try:
                self._observer.join(timeout=3)
            except Exception:
                pass
        self.db.close()