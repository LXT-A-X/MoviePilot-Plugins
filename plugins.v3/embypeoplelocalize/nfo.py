# -*- coding: utf-8 -*-
"""
nfo.py - NFO 文件引擎（v4.0 第二期）
职责（只做文件层，翻译交给上层）：
  - classify     按文件名判定层级 movie/tvshow/season/episode
  - find_nfo_files 遍历根目录收集 nfo（排除 bak/tmp，可选排除目录）
  - parse/load   解析 NFO，保留元素结构与子元素
  - collect_names 采集人名/角色名池（人名双键：tmdbid + 原文）
  - apply        只替换命中的 name/role 文本，其余元素原样保留
  - save         原子写回（临时文件 + os.replace）+ .nfo.bak 备份 + BOM 保留
"""
import os
import re
import stat
import logging
import threading
import time
from typing import Dict, List, Optional, Tuple

from xml.etree import ElementTree as ET

_logger = logging.getLogger("embypeoplelocalize.nfo")

_last_save_error: str = ""

_XML_ILLEGAL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")

# ── 文件级锁（v4.6.73 · 报告第十二节）──
# 进程内「按 nfo 路径」互斥：同一文件的「重新读取磁盘 → apply → 原子写回」全过程串行，
# 防止两个线程（写回 worker / 手动全部写回 / 单条写入）同时写同一个 NFO 互相覆盖。
_file_locks: Dict[str, threading.RLock] = {}
_file_locks_guard = threading.RLock()


def _lock_key(path: str) -> str:
    return str(path or "").replace("\\", "/").strip().lower()


def file_lock(path: str) -> threading.RLock:
    """返回某 nfo 路径对应的进程内可重入锁（with file_lock(p): ...）。
    同一路径恒返回同一把锁；路径大小写/分隔符归一，Windows/SMB 不漏配。"""
    _k = _lock_key(path)
    with _file_locks_guard:
        _lk = _file_locks.get(_k)
        if _lk is None:
            _lk = threading.RLock()
            _file_locks[_k] = _lk
        return _lk


def strip_illegal_xml_chars(text: str) -> str:
    """过滤 XML 1.0 非法控制字符（保留 \\t \\n \\r）。"""
    try:
        return _XML_ILLEGAL_RE.sub("", str(text or ""))
    except Exception:
        return str(text or "")


def get_last_save_error() -> str:
    """最近一次 save 失败的原始原因 —— 上层据此显式上报（避免写盘失败被静默）"""
    return str(_last_save_error or "")

# ---------------- 层级判定 ----------------

def classify(path: str) -> str:
    """按文件名/目录判定层级"""
    p = path.replace("\\", "/")
    fn = os.path.basename(p).lower()
    if fn == "tvshow.nfo":
        return "tvshow"
    if fn == "movie.nfo" or fn == "video.nfo":
        return "movie"
    if fn == "season.nfo":
        return "season"
    # 含 SxxExx → 单集
    if re.search(r"s\d{1,2}e\d{1,3}", fn, re.IGNORECASE):
        return "episode"
    return "movie"


# XML 根节点 → 语义层级（NFO-008）。文件名猜不出层级时以根节点为准；
# 音乐/图片/书籍等明确非影视的 sidecar 直接判为 unsupported（不解析、不入库），
# 避免把第三方 .nfo 当电影采集进库。
_ROOT_LEVEL = {
    "movie": "movie",
    "tvshow": "tvshow",
    "episodedetails": "episode",
    "season": "season",
    "musicvideo": "unsupported",
    "album": "unsupported",
    "artist": "unsupported",
    "audio": "unsupported",
    "picture": "unsupported",
    "photoset": "unsupported",
    "playlist": "unsupported",
    "book": "unsupported",
}


def root_level(root_tag: str) -> str:
    """XML 根节点对应的语义层级。
    "unsupported" = 明确的非影视 NFO；"" = 未知标签（不表态，沿用文件名判定，保持旧行为）。"""
    return _ROOT_LEVEL.get(str(root_tag or "").strip().lower(), "")

# ---------------- 采集 nfo 文件 ----------------

def find_nfo_files(roots: List[str], recursive: bool = True,
                   include_episodes: bool = False,
                   exclude_dirs: Tuple[str, ...] = ()) -> List[str]:
    """遍历目录收集 nfo 文件
    排除项支持两种写法：
      - 完整路径（以 / 或 \\ 开头，如 /media/示例库/排除目录）→ 精确剪枝该目录
      - 目录名（如 排除目录）→ 任意位置同名目录均排除（兼容旧行为）
    """
    found: List[str] = []
    names: set = set()     # 目录名排除（basename）
    paths: List[str] = []  # 路径排除（前缀匹配）
    for d in (x.strip() for x in exclude_dirs if x and x.strip()):
        _d = d.replace("\\", "/")
        if _d.startswith("/"):
            paths.append(_d.rstrip("/"))
        else:
            names.add(d.lower())
    paths = [p for p in paths if p]
    for root in roots:
        root = str(root or "").strip()
        if not root or not os.path.isdir(root):
            continue
        if recursive:
            for dirpath, dirnames, files in os.walk(root):
                # 目录名排除（沿用旧逻辑）
                dirnames[:] = [d for d in dirnames if d.lower() not in names]
                # 路径排除：完整路径前缀命中 → 剪枝
                if paths:
                    _cur = dirpath.replace("\\", "/").rstrip("/")
                    for _p in paths:
                        if _p == _cur or _cur.startswith(_p + "/"):
                            dirnames[:] = []
                            break
                for f in files:
                    if not f.lower().endswith(".nfo"):
                        continue
                    if f.lower().endswith((".bak", ".tmp", "~")):
                        continue
                    fp = os.path.join(dirpath, f)
                    c = classify(fp)
                    if c == "season" or (c == "episode" and not include_episodes):
                        continue
                    found.append(fp)
        else:
            for f in os.listdir(root):
                if not f.lower().endswith(".nfo"):
                    continue
                fp = os.path.join(root, f)
                try:
                    if os.path.isfile(fp) and classify(fp) in ("movie", "tvshow"):
                        found.append(fp)
                except Exception:
                    pass
    return sorted(found)

# ---------------- 解析 ----------------

class NfoDoc:
    """单个 NFO 的封装：保留原始字节决定是否重写"""
    def __init__(self, path: str):
        self.path = path
        self.has_bom = False
        self.raw: Optional[bytes] = None
        self.root: Optional[ET.Element] = None
        self.parse_error: str = ""
        self.filename = os.path.basename(path)
        self.level = classify(path)
        # 原始编码（NFO-009）：UTF-16 文件读得进，写回也保持原编码，不把用户文件转成 UTF-8
        self.encoding: str = "utf-8"
        # 明确的非影视 NFO（NFO-008）：扫描流程跳过，不入库
        self.unsupported: bool = False
        self.unsupported_reason: str = ""

    def load(self) -> bool:
        try:
            with open(self.path, "rb") as f:
                data = f.read()
            self.raw = data
            self.has_bom = data.startswith(b"\xef\xbb\xbf")
            if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
                # UTF-16（带 BOM）—— NFO-009：历史库/第三方工具常见，原先整批被跳过
                self.encoding = "utf-16-le" if data.startswith(b"\xff\xfe") else "utf-16-be"
                text = data.decode("utf-16")
            else:
                self.encoding = "utf-8"
                text = data.decode("utf-8-sig")
            if text and text[0] == "\ufeff":
                text = text[1:]
            self.root = ET.fromstring(text)
            _rl = root_level(getattr(self.root, "tag", ""))
            if _rl == "unsupported":
                self.unsupported = True
                self.unsupported_reason = f"XML 根节点 <{self.root.tag}> 不是影视 NFO"
                _logger.info(f"[NFO] 跳过非影视 NFO（根节点 <{self.root.tag}>）: {self.path}")
            return True
        except UnicodeDecodeError as e:
            self.parse_error = f"编码非 UTF-8/UTF-16，已跳过（未改写）: {e}"
            _logger.warning(f"[NFO] 跳过非 UTF-8/UTF-16 文件（避免乱码写回，可手动转码后重扫）: {self.path} :: {e}")
            return False
        except Exception as e:
            self.parse_error = str(e)
            return False

    # ----- 采集 -----
    def collect(self, translate_types: Dict[str, bool] = None,
                guest_limit: int = 0,
                limits: Dict[str, int] = None) -> Tuple[List[Tuple[str, str, Optional[str]]], List[Tuple[str, str, Optional[str]]]]:
        """采集 (原文, tmdbid) 人名对 和 (角色原文, None) 角色对
        返回 (names, roles)
        guest_limit>0 时，本文件内主角（type=Actor）全收，
        配角（type=GuestStar 等非 Actor）只收前 guest_limit 个 —— NFO「每集配角上限」
        translate_types 支持类型开关过滤（缺陷 H）—— 键：actor / guest /
        director / writer / producer / role；缺省或为 None 时该类型全收（兼容旧行为）。
        limits 每类型人数上限 —— {"actor": N, "guest": N, "director": N, "writer": N}，
        填 N=该文件内该类型只收前 N 个（actor/guest 按 <actor> 节点顺序；director/writer
        按节点顺序）；未列出的类型不限。
        v4.6.67（P1-F）：**N<=0 / 留空 = 不限（该类型全收）** —— 与 DB 层
        （pending 查询里 0=不限）统一口径；此前本层把 0 当「该类型不采集」，
        导致扫描健康检查/收集统计与库内待翻数字对不上。是否翻某类型由类型开关决定，
        不由数字决定。guest_limit 参数保留兼容（等价 limits["guest"]）。
        """
        if self.root is None:
            return [], []
        names: List[Tuple[str, str, Optional[str]]] = []
        roles: List[Tuple[str, str, Optional[str]]] = []
        tt = translate_types or {}
        want_actor = tt.get("actor", True)
        want_guest = tt.get("guest", True)
        want_director = tt.get("director", True)
        want_writer = tt.get("writer", True)
        want_producer = tt.get("producer", True)
        want_role = tt.get("role", True)
        has_limits = limits is not None
        lim_actor = int(limits.get("actor") or 0) if has_limits else 0
        lim_guest = int(limits.get("guest") or 0) if has_limits else max(0, int(guest_limit or 0))
        lim_director = int(limits.get("director") or 0) if has_limits else 0
        lim_writer = int(limits.get("writer") or 0) if has_limits else 0
        guest_count = 0
        actor_count = 0

        # <actor> 复杂节点
        for actor in self.root.findall("actor"):
            name_el = actor.find("name")
            role_el = actor.find("role")
            id_el = actor.find("tmdbid")
            type_el = actor.find("type")
            a_type = (type_el.text or "").strip() if type_el is not None and type_el.text else "Actor"
            is_guest = a_type.lower() not in ("actor", "voiceactor", "star")
            if is_guest:
                if not want_guest:
                    continue
            else:
                if not want_actor:
                    continue
            if is_guest:
                # v4.6.67：0/留空 = 不限（不再整类跳过）
                if lim_guest > 0 and guest_count >= lim_guest:
                    continue  # 客串超上限：整条跳过（人名+角色名都不收）
                guest_count += 1
            else:
                if lim_actor > 0 and actor_count >= lim_actor:
                    continue  # 主演超上限：整条跳过
                actor_count += 1
            n = (name_el.text or "").strip() if name_el is not None and name_el.text else ""
            r = (role_el.text or "").strip() if role_el is not None and role_el.text else ""
            if n:
                names.append((n, self._extract_tmdb(id_el), ""))
            if r and want_role:
                roles.append((r, None, ""))
        # 简单节点：director / writer / credits / producer —— 各看自己开关（credits 归 producer）
        simple_tags = ("director", "writer", "credits", "producer")
        want_simple = {"director": want_director, "writer": want_writer,
                       "credits": want_producer, "producer": want_producer}
        for tag in simple_tags:
            if not want_simple.get(tag, True):
                continue
            _lim = lim_director if tag == "director" else lim_writer
            # v4.6.67：0/留空 = 不限（不再整类跳过）
            _el_count = 0
            for el in self.root.findall(tag):
                if _lim > 0 and _el_count >= _lim:
                    continue  # 超上限：跳过
                _el_count += 1
                t = (el.text or "").strip() if el.text else ""
                if not t:
                    continue
                tmdb = el.get("tmdbid") or ""
                names.append((t, tmdb, ""))
        return names, roles

    @staticmethod
    def _extract_tmdb(id_el) -> str:
        if id_el is None:
            return ""
        return (id_el.text or "").strip()

    # ----- 应用 -----
    def apply(self, person_map: Dict[str, str], role_map: Dict[str, str]) -> int:
        """只替换命中的 name/role 文本，返回改动次数"""
        if self.root is None:
            return 0
        changed = 0
        for actor in self.root.findall("actor"):
            name_el = actor.find("name")
            role_el = actor.find("role")
            if name_el is not None and name_el.text:
                orig = name_el.text.strip()
                if orig and orig in person_map and person_map[orig] != orig:
                    name_el.text = person_map[orig]
                    changed += 1
            if role_el is not None and role_el.text:
                orig = role_el.text.strip()
                if orig and orig in role_map and role_map[orig] != orig:
                    role_el.text = role_map[orig]
                    changed += 1
        for tag in ("director", "writer", "credits", "producer"):
            for el in self.root.findall(tag):
                if el.text:
                    orig = el.text.strip()
                    if orig and orig in person_map and person_map[orig] != orig:
                        el.text = person_map[orig]
                        changed += 1
        return changed

    def absorb_actors_from(self, tv_doc, person_map: Optional[Dict[str, str]] = None,
                           role_map: Optional[Dict[str, str]] = None,
                           overwrite_all: bool = False) -> int:
        """把剧集主演出场的演员/角色翻译写进单集 nfo。

        修正：每集演员可能不同（主演不一定出场），默认不整份覆盖——
        只对单集里「已存在」的演员做原文→译文替换（person_map/role_map 命中才写），
        集内其他陌生人/非剧集演员一律保留。overwrite_all=True 时才整份同步剧集名单。

        :return: 改动条数
        """
        if self.root is None or tv_doc is None or getattr(tv_doc, "root", None) is None:
            return 0
        person_map = person_map or {}
        role_map = role_map or {}
        tv_actors = tv_doc.root.findall("actor")
        if not tv_actors:
            return 0
        import copy

        enough = bool(person_map or role_map)
        if overwrite_all or not enough:
            # 整份覆盖模式：替换为剧集已翻译名单（旧地兜底）
            old_actors = self.root.findall("actor")
            old_xml = [ET.tostring(a, encoding="unicode") for a in old_actors]
            new_xml = [ET.tostring(a, encoding="unicode") for a in tv_actors]
            if old_xml == new_xml:
                return 0
            for a in old_actors:
                self.root.remove(a)
            for a in tv_actors:
                self.root.append(copy.deepcopy(a))
            return len(tv_actors)

        # 智能匹配模式：只替换集内已存在且命中的 actor（name 原文匹配）
        changed = 0
        for actor in self.root.findall("actor"):
            name_el = actor.find("name")
            role_el = actor.find("role")
            if name_el is not None and name_el.text:
                orig = name_el.text.strip()
                if orig and orig in person_map and person_map[orig] != orig:
                    # 记录原文角色（有则改），无 role 保持原样
                    name_el.text = person_map[orig]
                    changed += 1
            if role_el is not None and role_el.text:
                orig = role_el.text.strip()
                if orig and orig in role_map and role_map[orig] != orig:
                    role_el.text = role_map[orig]
                    changed += 1
        return changed

    def merge_actors_from(self, ep_doc: "NfoDoc") -> int:
        """把单集 nfo 的演员合并进剧（self）的 <actor> 列表。

        - 只合并「剧里还没有」的演员，按 name 原文文本去重（剧已有的不动）
        - 合并的是原文副本（不带翻译），随主流水线的 apply(person_map) 统一翻译，
          从而实现「集演员按开关过滤后放进 tvshow」且翻译一致
        - 单集的 <actor> 通常没有或很少（Emby 对集写客串），有则全量吸收
        :return: 新增演员条数
        """
        if self.root is None or ep_doc is None or getattr(ep_doc, "root", None) is None:
            return 0
        try:
            ep_actors = ep_doc.root.findall("actor")
            if not ep_actors:
                return 0
            # 剧里已有的 name（原文文本）集合 —— 去重键
            existing = set()
            for a in self.root.findall("actor"):
                ne = a.find("name")
                if ne is not None and ne.text:
                    existing.add(ne.text.strip())
            import copy
            added = 0
            for a in ep_actors:
                ne = a.find("name")
                _n = ne.text.strip() if (ne is not None and ne.text) else ""
                if not _n or _n in existing:
                    continue
                self.root.append(copy.deepcopy(a))
                existing.add(_n)
                added += 1
            return added
        except Exception:
            return 0

    def set_lock(self, lock: bool = True) -> bool:
        """字段级锁定：在 <lockedfields> 中追加 Cast（演员），让 Emby/Jellyfin
        重新刮削/刷新元数据时不覆盖已翻译的中文演员名单，但剧情/简介/海报等
        其他字段照常可更新（新番简介过几天出中文也不受影响）。
        改为大写「Cast」（Emby 原生 nfo 写法；实测小写 cast 不被
        Emby 识别、会被刮削重写清除）—— 已有任何大小写形态的 cast 时保持原样，
        不再覆写大小写。
        :return: 是否发生 XML 变更（触发保存判定）
        """
        if self.root is None:
            return False
        if not lock:
            return False  # 关闭时不动文件（已锁的保留，需要手动/后续解锁）
        lf = self.root.find("lockedfields")
        want = "Cast"
        if lf is None:
            lf = ET.Element("lockedfields")
            lf.text = want
            self.root.insert(0, lf)
            return True
        cur = (lf.text or "").strip()
        names = [x.strip() for x in cur.replace(";", ",").split(",") if x.strip()]
        if any(n.lower() == "cast" for n in names):
            return False  # 已有锁（任意大小写），保持原样
        names.append(want)
        newv = ",".join(names)
        if newv != cur:
            lf.text = newv
            return True
        return False

    def is_cast_locked(self) -> bool:
        try:
            if self.root is None:
                return False
            lf = self.root.find("lockedfields")
            if lf is None:
                return False
            cur = (lf.text or "").strip()
            names = [x.strip() for x in cur.replace(";", ",").split(",") if x.strip()]
            return any(n.lower() == "cast" for n in names)
        except Exception:
            return False

    def save(self, backup: bool = True, dry_run: bool = False, lock_cast: bool = False) -> bool:
        global _last_save_error
        if self.root is None or dry_run:
            return dry_run
        if lock_cast:
            try:
                self.set_lock(True)
            except Exception:
                pass
        try:
            body = ET.tostring(self.root, encoding="unicode", short_empty_elements=True)
            body = strip_illegal_xml_chars(body)
            _enc = str(getattr(self, "encoding", "") or "utf-8")
            if _enc in ("utf-16-le", "utf-16-be"):
                # 保留原 UTF-16 编码与字节序（NFO-009）—— 转成 UTF-8 会改动用户文件编码
                body = '<?xml version="1.0" encoding="UTF-16" standalone="yes"?>\n' + body + "\n"
                payload = ("\ufeff" + body).encode(_enc)
            else:
                body = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + body + "\n"
                data = ("\ufeff" if self.has_bom else "") + body
                payload = data.encode("utf-8")
            if backup and os.path.exists(self.path):
                bak = self.path + ".bak"
                if not os.path.exists(bak):
                    with open(bak, "wb") as f:
                        f.write(self.raw or b"")
            tmp = self.path + ".tmp"
            _prev_mode = None
            _prev_uid = None
            _prev_gid = None
            try:
                _pst = os.stat(self.path)
                _prev_mode = stat.S_IMODE(_pst.st_mode)
                _prev_uid = getattr(_pst, "st_uid", None)
                _prev_gid = getattr(_pst, "st_gid", None)
            except Exception:
                _prev_mode = None
            last_err: Optional[BaseException] = None
            for _delay in (0.3, 1.0, 2.0, 3.0, 5.0):
                try:
                    with open(tmp, "wb") as f:
                        f.write(payload)
                        try:
                            f.flush()
                            os.fsync(f.fileno())
                        except Exception:
                            pass
                    os.replace(tmp, self.path)
                    if _prev_mode is not None:
                        try:
                            os.chmod(self.path, _prev_mode)
                        except Exception:
                            pass
                    if _prev_uid is not None and _prev_gid is not None and hasattr(os, "chown"):
                        try:
                            os.chown(self.path, _prev_uid, _prev_gid)
                        except Exception:
                            pass
                    return True
                except Exception as _e:  # noqa: BLE001
                    last_err = _e
                    time.sleep(_delay)
            _last_save_error = str(last_err)
            _logger.warning(f"[NFO] 写回失败（5 次重试后，间隔 0.3/1/2/3/5s）: {self.path} :: {last_err}")
            return False
        except Exception as e:
            _last_save_error = str(e)
            _logger.warning(f"[NFO] save 失败: {self.path} :: {e}")
            try:
                if os.path.exists(self.path + ".tmp"):
                    os.remove(self.path + ".tmp")
            except Exception:
                pass
            return False

# ---------------- 映射构造 ----------------

def build_map_from_source(pairs: List[Tuple[str, str]]) -> Dict[str, str]:
    """由 (原文, 译文) 配对构造人名角色映射（key=原文）"""
    out: Dict[str, str] = {}
    for orig, trans in pairs:
        orig = (orig or "").strip()
        trans = (trans or "").strip()
        if orig and trans:
            out[orig] = trans
    return out


def parse_nfo(path: str) -> Optional[NfoDoc]:
    doc = NfoDoc(path)
    return doc if doc.load() else None