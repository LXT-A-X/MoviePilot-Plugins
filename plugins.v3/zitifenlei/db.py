"""
字体分类管家 - 数据库模块
独立 SQLite 数据库，存放于插件数据目录（get_data_path）
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 文件日志通道：插件在 init_plugin 时会给该 logger 挂上 plugins/zitifenlei.log 的
# FileHandler（见 __init__.py _ensure_plugin_logfile），此处共用同名字实例，
# 使仪表盘日志同步落盘到文件（独立 logger，不受 MP 全局日志级别影响）
_ztLogger = logging.getLogger("ZitifenleiFile")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS fonts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT DEFAULT '',
    family TEXT DEFAULT '',
    vendor TEXT DEFAULT '未知厂商',
    designer TEXT DEFAULT '',
    file_name TEXT DEFAULT '',
    file_size INTEGER DEFAULT 0,
    favorite INTEGER DEFAULT 0,
    status TEXT DEFAULT '已归档',
    source TEXT DEFAULT 'manual',
    file_path TEXT DEFAULT '',
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS pending_fonts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT DEFAULT '',
    file_path TEXT DEFAULT '',
    name TEXT DEFAULT '',
    family TEXT DEFAULT '',
    vendor TEXT DEFAULT '未知厂商',
    designer TEXT DEFAULT '',
    file_size INTEGER DEFAULT 0,
    created_at TEXT
);

-- missing_uploads：检查页「缺失字体修复」已上传待归类的字体（持久化，重启不丢）
CREATE TABLE IF NOT EXISTS missing_uploads (
    path TEXT PRIMARY KEY,
    file_name TEXT DEFAULT '',
    name TEXT DEFAULT '',
    family TEXT DEFAULT '',
    vendor TEXT DEFAULT '',
    designer TEXT DEFAULT '',
    file_size INTEGER DEFAULT 0,
    matched TEXT DEFAULT '',
    match_kind TEXT DEFAULT '',
    matched_keys TEXT DEFAULT '[]',
    covered_chars TEXT DEFAULT '',
    required_chars TEXT DEFAULT '',
    sha256 TEXT DEFAULT '',
    created_at REAL DEFAULT 0,
    face_index INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ass_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT DEFAULT '',
    source TEXT DEFAULT 'manual',
    status TEXT DEFAULT 'ok',
    check_time TEXT,
    missing_count INTEGER DEFAULT 0,
    missing_fonts TEXT DEFAULT '[]',
    all_fonts TEXT DEFAULT '[]',
    file_path TEXT DEFAULT '',
    batch TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time TEXT,
    level TEXT DEFAULT 'info',
    message TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS plugin_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS processed_fonts (
    source_path TEXT PRIMARY KEY,
    done_at TEXT
);

CREATE TABLE IF NOT EXISTS subset_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT DEFAULT '',
    file_path TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    reason TEXT DEFAULT '',
    out_file TEXT DEFAULT '',
    source TEXT DEFAULT '',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS subset_pending (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT DEFAULT '',
    file_path TEXT DEFAULT '',
    source TEXT DEFAULT 'upload',
    created_at TEXT
);

-- ── 增量字体索引（fontTools 权威口径，替代 assfonts fonts.json）──
-- font_files：每个真实字体文件一条；SHA-256 为身份，path 只是引用（移动/改名可迁移）
CREATE TABLE IF NOT EXISTS font_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE,
    sha256 TEXT DEFAULT '',
    size INTEGER DEFAULT 0,
    mtime_ns INTEGER DEFAULT 0,
    format TEXT DEFAULT '',
    face_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ok',
    error TEXT DEFAULT '',
    indexed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_font_files_sha ON font_files(sha256);
-- font_faces：TTC/OTC 一个文件多个 face，一个 face 一条
CREATE TABLE IF NOT EXISTS font_faces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER NOT NULL,
    face_index INTEGER DEFAULT 0,
    family TEXT DEFAULT '',
    subfamily TEXT DEFAULT '',
    full_name TEXT DEFAULT '',
    postscript_name TEXT DEFAULT '',
    aliases_json TEXT DEFAULT '[]',
    vendor TEXT DEFAULT '',
    designer TEXT DEFAULT '',
    version TEXT DEFAULT '',
    char_count INTEGER DEFAULT 0,
    coverage BLOB,
    status TEXT DEFAULT 'ok',
    error TEXT DEFAULT '',
    UNIQUE(file_id, face_index)
);
CREATE INDEX IF NOT EXISTS idx_font_faces_file ON font_faces(file_id);
-- font_aliases：归一化别名 → face 多对多（同名字体多来源可共存）
CREATE TABLE IF NOT EXISTS font_aliases (
    alias TEXT NOT NULL,
    face_id INTEGER NOT NULL,
    PRIMARY KEY(alias, face_id)
);
CREATE INDEX IF NOT EXISTS idx_font_aliases_alias ON font_aliases(alias);
-- index_state：索引版本/active/上一有效版本/统计
CREATE TABLE IF NOT EXISTS index_state (
    key TEXT PRIMARY KEY,
    value TEXT
);
-- ass_missing_glyphs：逐字符缺失明细（历史保留，重检后更新）
CREATE TABLE IF NOT EXISTS ass_missing_glyphs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ass_id INTEGER,
    file_path TEXT DEFAULT '',
    font_name TEXT DEFAULT '',
    used_count INTEGER DEFAULT 0,
    missing_count INTEGER DEFAULT 0,
    missing_codepoints TEXT DEFAULT '[]',
    missing_chars TEXT DEFAULT '',
    status TEXT DEFAULT '',
    faces_json TEXT DEFAULT '[]',
    check_time TEXT
);
CREATE INDEX IF NOT EXISTS idx_ass_missing_ass ON ass_missing_glyphs(ass_id);
-- manual_font_mappings：严格上传的人工放行（带审计）
CREATE TABLE IF NOT EXISTS manual_font_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    target_name TEXT NOT NULL,
    file_sha256 TEXT DEFAULT '',
    note TEXT DEFAULT '',
    created_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_manual_mapping ON manual_font_mappings(source_name, target_name);
-- torrent_ingest：种子字体截取的处理记录（幂等判断 / 页面展示 / 失败排查）
CREATE TABLE IF NOT EXISTS torrent_ingest (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hash TEXT DEFAULT '',
    downloader TEXT DEFAULT '',
    torrent_name TEXT DEFAULT '',
    source TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    picked INTEGER DEFAULT 0,
    added INTEGER DEFAULT 0,
    skipped INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    detail TEXT DEFAULT '',
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_torrent_ingest_hash ON torrent_ingest(hash);
"""


class FontDB:
    """SQLite 封装，线程安全"""

    def __init__(self, db_path: str | Path):
        self._path = str(db_path)
        self._lock = threading.RLock()
        self._conn = None
        self._ensure_connected()

    def _ensure_connected(self) -> None:
        if getattr(self, "_closed", False):
            # close() 后拒绝静默重连：停服后残留线程若继续写库，应明确失败并暴露，
            # 而不是悄悄重开一个无人关闭的连接（WAL 残留、日志丢失更难排查）
            raise RuntimeError("数据库已关闭，拒绝重连")
        if self._conn is None:
            # Q17 修复：统一显式隔离级别（isolation_level=None + 手动 BEGIN/COMMIT），
            # 避免 sqlite3 隐式事务与 import_all 手动 BEGIN 交错时报
            # "cannot start a transaction within a transaction"（低频但原理性隐患）
            self._conn = sqlite3.connect(self._path, check_same_thread=False, isolation_level=None)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            with self._lock:
                self._conn.executescript(_SCHEMA)
                self._conn.commit()
                # 兼容旧库：ass_files 补充 file_path 列（存储上传字幕的临时文件路径）
                try:
                    self._conn.execute("ALTER TABLE ass_files ADD COLUMN file_path TEXT DEFAULT ''")
                    self._conn.commit()
                except Exception:
                    pass
                # 兼容旧库：ass_files 补充 batch 列（检查页按压缩包/上传批次分组抽屉）
                try:
                    self._conn.execute("ALTER TABLE ass_files ADD COLUMN batch TEXT DEFAULT ''")
                    self._conn.commit()
                except Exception:
                    pass
                # 字形级检测/索引口径新增列（旧库就地补充，不重写已有数据）
                for column, ddl in (
                    ("missing_details", "TEXT DEFAULT '[]'"),
                    ("file_sha256", "TEXT DEFAULT ''"),
                    ("index_version", "INTEGER DEFAULT 0"),
                    ("check_engine", "TEXT DEFAULT ''"),
                    ("legacy", "INTEGER DEFAULT 0"),
                ):
                    try:
                        self._conn.execute(f"ALTER TABLE ass_files ADD COLUMN {column} {ddl}")
                        self._conn.commit()
                    except Exception:
                        pass
                # schema 版本标记（迁移记录，当前 v2：fontTools 增量索引 + 字形级检测）
                try:
                    self._conn.execute(
                        "INSERT INTO index_state(key, value) VALUES('schema_version', '2') "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
                    )
                    self._conn.commit()
                except Exception:
                    pass
                # 子集化记录补充来源列（P1-8）：inbound（媒体库）记录删记录时绝不能删媒体库成品
                try:
                    self._conn.execute("ALTER TABLE subset_records ADD COLUMN source TEXT DEFAULT ''")
                    self._conn.commit()
                except Exception:
                    pass
                # 缺失字体上传缓冲补充 face_index（P1-4）：严格校验按单一 face 通过，
                # 归档/子集化必须用同一个 face，不能在多 face 间错配
                try:
                    self._conn.execute(
                        "ALTER TABLE missing_uploads ADD COLUMN face_index INTEGER DEFAULT 0"
                    )
                    self._conn.commit()
                except Exception:
                    pass

    def close(self) -> None:
        with self._lock:
            self._closed = True
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

    def execute(self, sql: str, params: tuple = ()) -> None:
        with self._lock:
            self._ensure_connected()
            self._conn.execute(sql, params)
            self._conn.commit()

    def executemany(self, sql: str, seq: List[tuple]) -> None:
        with self._lock:
            self._ensure_connected()
            self._conn.executemany(sql, seq)
            self._conn.commit()

    def query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        with self._lock:
            self._ensure_connected()
            cur = self._conn.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    def query_one(self, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    # ============ 通用工具 ============

    @staticmethod
    def now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def __init__(self, db_path: str | Path):
        self._path = str(db_path)
        self._lock = threading.RLock()
        self._conn = None
        self._closed = False
        # Q12 修复：日志裁剪计数器——每写入 N 条日志才执行一次 DELETE 裁剪，
        # 避免每次 INSERT 都跟一条 NOT IN 子查询（日志密集场景 SQL 翻倍）
        self._log_trim_counter = 0
        self._log_trim_interval = 20  # 每 20 条裁剪一次（保留 200 条上限仍成立：峰值多 19 条）
        self._ensure_connected()

    def add_log(self, message: str, level: str = "info") -> None:
        try:
            self.execute(
                "INSERT INTO logs (time, level, message) VALUES (?, ?, ?)",
                (self.now(), level, message),
            )
            # Q12 修复：保留最近 200 条日志——裁剪低频化，每 _log_trim_interval 条
            # 才执行一次 DELETE（原实现每次 INSERT 都跟一条 NOT IN 子查询，SQL 翻倍）
            self._log_trim_counter += 1
            if self._log_trim_counter >= self._log_trim_interval:
                self._log_trim_counter = 0
                self.execute("DELETE FROM logs WHERE id NOT IN (SELECT id FROM logs ORDER BY id DESC LIMIT 200)")
        except Exception:
            pass
        # 镜像到插件文件日志（logs/plugins/zitifenlei.log），保证 API/系统日志页可读；
        # SQLite 日志级别 success 对应文件 INFO
        try:
            fn = getattr(_ztLogger, level if level != "success" else "info", _ztLogger.info)
            fn(f"字体分类管家: {message}")
        except Exception:
            pass

    def get_logs(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self.query("SELECT id, time, level, message FROM logs ORDER BY id DESC LIMIT ?", (int(limit),))

    # ============ 插件状态（键值存储，独立于 MP 配置） ============

    def get_setting(self, key: str, default: Any = None) -> Any:
        """读取插件内部状态（存储为字符串，带类型前缀标记还原）

        Q16 修复：set_setting 写入时带类型前缀（b:/i:/s:），get_setting 按前缀还原，
        解决老实现 isdigit() 把纯数字字符串（如档位 "80"）误转成 int 导致的类型不稳定；
        兼容老数据：前缀缺失时按布尔/字符串启发还原（True/False），纯数字按原字符串返回。
        """
        try:
            row = self.query_one("SELECT value FROM plugin_settings WHERE key = ?", (key,))
            if row is None:
                return default
            val = row["value"]
            if val.startswith("b:"):
                return val[2:] == "1"
            if val.startswith("i:"):
                try:
                    return int(val[2:])
                except Exception:
                    return val[2:]
            if val.startswith("s:"):
                return val[2:]
            # 兼容旧数据：无前缀的布尔字面量
            if val == "True":
                return True
            if val == "False":
                return False
            return val
        except Exception:
            return default

    def set_setting(self, key: str, value: Any) -> None:
        """保存插件内部状态（Q16 修复：写入时带类型前缀，get_setting 据此还原类型）"""
        try:
            if value is True or value is False:
                val = "b:1" if value else "b:0"
            elif value is None:
                val = "s:"
            elif isinstance(value, int):
                val = f"i:{value}"
            else:
                val = f"s:{value}"
            self.execute(
                "INSERT INTO plugin_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, val),
            )
        except Exception:
            pass

    # ============ 全配置镜像（所有配置字段，重启/重载兜底恢复） ============

    def save_full_config(self, cfg: Dict[str, Any]) -> None:
        """保存插件完整配置镜像到 SQLite（json 序列化），独立于宿主配置存储"""
        try:
            self.set_setting("full_config", json.dumps(cfg, ensure_ascii=False))
        except Exception:
            pass

    def get_full_config(self, default: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """读取完整配置镜像；无镜像或解析失败返回 default"""
        try:
            raw = self.get_setting("full_config", None)
            if raw:
                cfg = json.loads(raw)
                return cfg if isinstance(cfg, dict) else default
        except Exception:
            return default
        return default

    # ============ fonts ============

    def add_font(self, item: Dict[str, Any]) -> int:
        # Q13 修复：直接取 cursor.lastrowid 拿自增 id，省掉插入后的回查 SELECT
        with self._lock:
            self._ensure_connected()
            cur = self._conn.execute(
                """INSERT INTO fonts (name, family, vendor, designer, file_name, file_size,
                   favorite, status, source, file_path, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)""",
                (
                    item.get("name", ""),
                    item.get("family", ""),
                    item.get("vendor", "未知厂商"),
                    item.get("designer", ""),
                    item.get("file_name", ""),
                    item.get("file_size", 0),
                    item.get("status", "已归档"),
                    item.get("source", "manual"),
                    item.get("file_path", ""),
                    self.now(),
                    self.now(),
                ),
            )
            self._conn.commit()
            return cur.lastrowid or 0

    def count_fonts_by_path(self, file_path: str) -> int:
        row = self.query_one("SELECT COUNT(*) AS c FROM fonts WHERE file_path = ?", (file_path,))
        return row["c"] if row else 0

    def query_fonts(
        self,
        keyword: str = "",
        vendor: str = "",
        page: int = 1,
        limit: int = 50,
    ) -> Dict[str, Any]:
        where = []
        params: List[Any] = []
        if keyword:
            like = f"%{keyword}%"
            where.append("(name LIKE ? OR family LIKE ? OR vendor LIKE ? OR designer LIKE ? OR file_name LIKE ?)")
            params.extend([like, like, like, like, like])
        if vendor:
            where.append("vendor = ?")
            params.append(vendor)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        total = self.query_one(f"SELECT COUNT(*) AS c FROM fonts {where_sql}", tuple(params))["c"]
        offset = (max(int(page), 1) - 1) * int(limit)
        rows = self.query(
            f"SELECT * FROM fonts {where_sql} ORDER BY favorite DESC, id DESC LIMIT ? OFFSET ?",
            tuple(params) + (int(limit), offset),
        )
        return {"list": rows, "total": total}

    def get_font(self, font_id: int) -> Optional[Dict[str, Any]]:
        return self.query_one("SELECT * FROM fonts WHERE id = ?", (int(font_id),))

    def delete_font(self, font_id: int) -> None:
        """删除字体记录（文件删除由上层负责）"""
        self.execute("DELETE FROM fonts WHERE id = ?", (int(font_id),))

    def update_font_vendor(self, font_id: int, vendor: str, designer: str = "") -> None:
        """更新字体的厂商/设计师（重新识别时使用）"""
        self.execute(
            "UPDATE fonts SET vendor = ?, designer = ?, updated_at = ? WHERE id = ?",
            (vendor, designer, self.now(), int(font_id)),
        )

    def list_all_fonts(self) -> List[Dict[str, Any]]:
        """返回全部字体记录（用于前端本地构建目录树）"""
        return self.query("SELECT * FROM fonts ORDER BY favorite DESC, id DESC")

    def toggle_favorite(self, font_id: int) -> int:
        row = self.get_font(font_id)
        if not row:
            return 0
        new_val = 0 if row["favorite"] else 1
        self.execute("UPDATE fonts SET favorite = ? WHERE id = ?", (new_val, font_id))
        return new_val

    def stats(self) -> Dict[str, Any]:
        total = self.query_one("SELECT COUNT(*) AS c FROM fonts")["c"]
        pending = self.query_one("SELECT COUNT(*) AS c FROM fonts WHERE status = '待整理'")["c"]
        archived = self.query_one("SELECT COUNT(*) AS c FROM fonts WHERE status = '已归档'")["c"]
        missing = self.query_one("SELECT COALESCE(SUM(missing_count), 0) AS c FROM ass_files")["c"]
        # 字体索引口径的 face 数：TTC/OTC 一个文件含多个 face，与「字体总数（文件数）」
        # 天然不相等，并列展示避免被误当成统计错误
        try:
            faces = self.query_one("SELECT COUNT(*) AS c FROM font_faces WHERE status = 'ok'")["c"]
        except Exception:
            faces = 0
        return {
            "total": total,
            "pending": pending,
            "archived": archived,
            "error": missing,
            "faces": faces,
        }

    def vendors(self, top: int = 0) -> List[Dict[str, Any]]:
        """厂商分布：默认返回全量并按数量降序（top>0 时仅取前 N，兼容旧调用）"""
        total = self.query_one("SELECT COUNT(*) AS c FROM fonts")["c"] or 1
        limit = f" LIMIT {int(top)}" if int(top) > 0 else ""
        rows = self.query(f"SELECT vendor, COUNT(*) AS count FROM fonts GROUP BY vendor ORDER BY count DESC{limit}")
        return [
            {"vendor": r["vendor"], "count": r["count"], "percent": round(r["count"] * 100 / total, 1)}
            for r in rows
        ]

    # ============ pending_fonts ============

    def list_pending(self) -> List[Dict[str, Any]]:
        return self.query("SELECT * FROM pending_fonts ORDER BY id DESC")

    def add_pending(self, item: Dict[str, Any]) -> None:
        self.execute(
            """INSERT INTO pending_fonts (file_name, file_path, name, family, vendor, designer, file_size, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item.get("file_name", ""),
                item.get("file_path", ""),
                item.get("name", ""),
                item.get("family", ""),
                item.get("vendor", "未知厂商"),
                item.get("designer", ""),
                item.get("file_size", 0),
                self.now(),
            ),
        )

    def delete_pending(self, pending_id: int) -> None:
        self.execute("DELETE FROM pending_fonts WHERE id = ?", (int(pending_id),))

    def delete_pending_by_path(self, file_path: str) -> None:
        self.execute("DELETE FROM pending_fonts WHERE file_path = ?", (file_path,))

    # ============ missing_uploads（缺失字体修复上传缓冲，持久化） ============

    def list_missing_uploads(self) -> List[Dict[str, Any]]:
        return self.query("SELECT * FROM missing_uploads ORDER BY created_at")

    def add_missing_upload(self, item: Dict[str, Any]) -> None:
        self.execute(
            """INSERT INTO missing_uploads (path, file_name, name, family, vendor, designer, file_size,
                                             matched, match_kind, matched_keys, covered_chars, required_chars,
                                             sha256, created_at, face_index)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(path) DO UPDATE SET file_name = excluded.file_name, name = excluded.name,
                   family = excluded.family, vendor = excluded.vendor, designer = excluded.designer,
                   file_size = excluded.file_size, matched = excluded.matched,
                   match_kind = excluded.match_kind, matched_keys = excluded.matched_keys,
                   covered_chars = excluded.covered_chars, required_chars = excluded.required_chars,
                   sha256 = excluded.sha256, created_at = excluded.created_at,
                   face_index = excluded.face_index""",
            (
                item.get("path", ""),
                item.get("file_name", ""),
                item.get("name", ""),
                item.get("family", ""),
                item.get("vendor", ""),
                item.get("designer", ""),
                int(item.get("file_size") or 0),
                item.get("matched", ""),
                item.get("match_kind", ""),
                json.dumps(item.get("matched_keys") or [], ensure_ascii=False),
                item.get("covered_chars", ""),
                item.get("required_chars", ""),
                item.get("sha256", ""),
                float(item.get("created_at") or 0),
                int(item.get("face_index") or 0),
            ),
        )

    def delete_missing_upload(self, path: str) -> None:
        self.execute("DELETE FROM missing_uploads WHERE path = ?", (str(path),))

    def clear_missing_uploads(self) -> None:
        self.execute("DELETE FROM missing_uploads")

    # ============ 已处理源字体（仪表盘「待整理」统计口径） ============

    def mark_font_processed(self, source_path: str) -> None:
        """记录一个源字体文件已被系统处理过（监控/全量检查归档、同名跳过均算）。

        复制归档模式下源文件保留在字体监控目录，仅凭文件名无法判断是否处理过，
        靠该标记让「待整理」统计排除已处理的文件（入库完成数字归零）。
        """
        if not source_path:
            return
        try:
            self.execute(
                "INSERT INTO processed_fonts (source_path, done_at) VALUES (?, ?) "
                "ON CONFLICT(source_path) DO UPDATE SET done_at = excluded.done_at",
                (str(source_path), self.now()),
            )
        except Exception:
            pass

    def processed_font_paths(self) -> set:
        """返回全部已处理源字体文件的路径集合"""
        try:
            rows = self.query("SELECT source_path FROM processed_fonts")
            return {r["source_path"] for r in rows}
        except Exception:
            return set()

    # ============ 子集化记录（subset_records） ============

    def add_subset_record(self, item: Dict[str, Any]) -> None:
        # 同一字幕只保留最新一条处理记录：重试/重复处理时旧记录（缺字体/失败）被新结果替换，
        # 避免结果区新旧两条并存
        fp = item.get("file_path", "")
        if fp:
            try:
                self.execute("DELETE FROM subset_records WHERE file_path = ?", (str(fp),))
            except Exception:
                pass
        self.execute(
            """INSERT INTO subset_records (file_name, file_path, status, reason, out_file, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                item.get("file_name", ""),
                item.get("file_path", ""),
                item.get("status", "pending"),
                item.get("reason", ""),
                item.get("out_file", ""),
                item.get("source", ""),
                self.now(),
            ),
        )

    def list_subset_records(
        self,
        status: str = "",
        keyword: str = "",
        page: int = 1,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """子集化记录分页查询：status 过滤（空=全部）+ file_name 模糊搜索"""
        where = []
        params: List[Any] = []
        if status in ("success", "skipped", "missing", "error"):
            where.append("status = ?")
            params.append(status)
        if keyword:
            where.append("file_name LIKE ?")
            params.append(f"%{keyword}%")
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        total = self.query_one(
            f"SELECT COUNT(*) AS c FROM subset_records {where_sql}", tuple(params)
        )["c"]
        offset = (max(int(page), 1) - 1) * int(limit)
        rows = self.query(
            f"SELECT * FROM subset_records {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?",
            tuple(params) + (int(limit), offset),
        )
        # 可重试数（缺字体+失败，不分页不限筛选），供前端「重试失败」按钮判断
        retriable = self.query_one(
            "SELECT COUNT(*) AS c FROM subset_records WHERE status IN ('missing', 'error')"
        )["c"]
        return {"list": rows, "total": total, "retriable": retriable}

    def delete_subset_record(self, record_id: int) -> None:
        self.execute("DELETE FROM subset_records WHERE id = ?", (int(record_id),))

    def clear_subset_records(self) -> None:
        self.execute("DELETE FROM subset_records")

    def count_subset_records(self) -> int:
        row = self.query_one("SELECT COUNT(*) AS c FROM subset_records")
        return row["c"] if row else 0

    def count_subset_missing(self) -> int:
        """子集化因缺字体跳过的字幕条数"""
        row = self.query_one("SELECT COUNT(*) AS c FROM subset_records WHERE status = 'missing'")
        return row["c"] if row else 0

    # ============ 子集化待处理（subset_pending） ============

    def add_subset_pending(self, file_name: str, file_path: str, source: str = "upload") -> int:
        """加入待处理列表（去重：同 file_path 只保留一条）"""
        exist = self.query_one("SELECT id FROM subset_pending WHERE file_path = ?", (file_path,))
        if exist:
            return exist["id"]
        self.execute(
            "INSERT INTO subset_pending (file_name, file_path, source, created_at) VALUES (?, ?, ?, ?)",
            (file_name, file_path, source, self.now()),
        )
        row = self.query_one("SELECT id FROM subset_pending WHERE file_path = ?", (file_path,))
        return row["id"] if row else 0

    def list_subset_pending(self) -> List[Dict[str, Any]]:
        return self.query("SELECT * FROM subset_pending ORDER BY id DESC")

    def delete_subset_pending(self, pending_id: int) -> None:
        self.execute("DELETE FROM subset_pending WHERE id = ?", (int(pending_id),))

    def clear_subset_pending(self) -> None:
        self.execute("DELETE FROM subset_pending")

    # ============ ass_files ============

    def add_ass(
        self,
        file_name: str,
        source: str,
        status: str,
        missing_fonts: List[str],
        all_fonts: List[str],
        file_path: str = "",
        batch: str = "",
    ) -> None:
        self.execute(
            """INSERT INTO ass_files (file_name, source, status, check_time, missing_count, missing_fonts, all_fonts, file_path, batch)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                file_name,
                source,
                status,
                self.now(),
                len(missing_fonts),
                json.dumps(missing_fonts, ensure_ascii=False),
                json.dumps(all_fonts, ensure_ascii=False),
                file_path,
                batch,
            ),
        )

    def update_ass(
        self,
        ass_id: int,
        status: str,
        missing_fonts: List[str],
        all_fonts: List[str],
    ) -> None:
        """手动/再次检查后更新单条 ASS 记录的检查结果"""
        self.execute(
            """UPDATE ass_files SET status = ?, check_time = ?, missing_count = ?,
               missing_fonts = ?, all_fonts = ? WHERE id = ?""",
            (
                status,
                self.now(),
                len(missing_fonts),
                json.dumps(missing_fonts, ensure_ascii=False),
                json.dumps(all_fonts, ensure_ascii=False),
                int(ass_id),
            ),
        )

    def query_ass(
        self,
        keyword: str = "",
        page: int = 1,
        limit: int = 20,
    ) -> Dict[str, Any]:
        where = []
        params: List[Any] = []
        if keyword:
            where.append("file_name LIKE ?")
            params.append(f"%{keyword}%")
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        total = self.query_one(f"SELECT COUNT(*) AS c FROM ass_files {where_sql}", tuple(params))["c"]
        offset = (max(int(page), 1) - 1) * int(limit)
        rows = self.query(
            f"SELECT id, file_name, source, status, check_time, missing_count, file_path, batch FROM ass_files {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?",
            tuple(params) + (int(limit), offset),
        )
        return {"list": rows, "total": total}

    def get_ass(self, ass_id: int) -> Optional[Dict[str, Any]]:
        row = self.query_one("SELECT * FROM ass_files WHERE id = ?", (int(ass_id),))
        if row:
            row["missing_fonts"] = json.loads(row.get("missing_fonts") or "[]")
            row["all_fonts"] = json.loads(row.get("all_fonts") or "[]")
        return row

    def delete_ass(self, ass_id: int) -> None:
        """删除一个字幕记录：同事务清理其字形缺失快照，避免已删字幕的字体永久留在缺失列表。"""
        with self.transaction() as conn:
            conn.execute("DELETE FROM ass_missing_glyphs WHERE ass_id = ?", (int(ass_id),))
            conn.execute("DELETE FROM ass_files WHERE id = ?", (int(ass_id),))

    def clear_ass(self) -> None:
        """清空字幕记录：同事务清理字形缺失快照。"""
        with self.transaction() as conn:
            conn.execute("DELETE FROM ass_missing_glyphs")
            conn.execute("DELETE FROM ass_files")

    def all_font_families(self) -> List[str]:
        rows = self.query("SELECT DISTINCT family FROM fonts WHERE family != ''")
        names = [r["family"] for r in rows]
        names += [r["name"] for r in self.query("SELECT DISTINCT name FROM fonts WHERE name != ''")]
        return list(set(names))

    # ============ 增量字体索引（fontTools 权威口径） ============

    @contextmanager
    def transaction(self):
        """手动事务：索引提交要么全部成功、要么全部回滚。"""
        with self._lock:
            self._ensure_connected()
            self._conn.execute("BEGIN")
            try:
                yield self._conn
                self._conn.execute("COMMIT")
            except Exception:
                try:
                    self._conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise

    def index_get(self, key: str, default: Any = None) -> Any:
        row = self.query_one("SELECT value FROM index_state WHERE key = ?", (key,))
        return row["value"] if row else default

    def index_set(self, key: str, value: Any) -> None:
        self.execute(
            "INSERT INTO index_state(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )

    def index_version(self) -> int:
        try:
            return int(self.index_get("index_version", 0) or 0)
        except Exception:
            return 0

    def bump_index_version(self) -> int:
        with self.transaction() as conn:
            row = conn.execute("SELECT value FROM index_state WHERE key = 'index_version'").fetchone()
            try:
                current = int(row["value"]) if row else 0
            except Exception:
                current = 0
            new_value = current + 1
            conn.execute(
                "INSERT INTO index_state(key, value) VALUES('index_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(new_value),),
            )
        return new_value

    @staticmethod
    def _encode_coverage(codepoints) -> bytes:
        from .font_metadata import encode_codepoints

        return encode_codepoints(codepoints or ())

    @staticmethod
    def _decode_coverage(blob) -> set:
        from .font_metadata import decode_codepoints

        if not blob:
            return set()
        try:
            return decode_codepoints(bytes(blob))
        except Exception:
            return set()

    def get_font_file(self, path: str) -> Optional[Dict[str, Any]]:
        return self.query_one("SELECT * FROM font_files WHERE path = ?", (str(path),))

    def get_font_file_by_sha(self, sha256: str) -> Optional[Dict[str, Any]]:
        if not sha256:
            return None
        return self.query_one("SELECT * FROM font_files WHERE sha256 = ? ORDER BY id LIMIT 1", (sha256,))

    def upsert_font_file(self, inspection: Any, indexed_at: Optional[str] = None) -> Dict[str, Any]:
        """把一个字体文件（含全部 face/别名/覆盖）事务性写入索引。

        inspection: font_metadata.FontInspection
        返回 {"changed": bool, "file_id": int, "index_version": int}
        """
        path = str(getattr(inspection, "path", "") or "")
        sha256 = str(getattr(inspection, "sha256", "") or "")
        size = int(getattr(inspection, "file_size", 0) or 0)
        mtime_ns = int(getattr(inspection, "mtime_ns", 0) or 0)
        fmt = str(getattr(inspection, "format", "") or "")
        status = str(getattr(inspection, "status", "") or "ok")
        error = str(getattr(inspection, "error", "") or "")
        faces = list(getattr(inspection, "faces", []) or [])
        timestamp = indexed_at or self.now()

        with self.transaction() as conn:
            row = conn.execute("SELECT * FROM font_files WHERE path = ?", (path,)).fetchone()
            if row:
                file_id = int(row["id"])
                if (
                    sha256
                    and str(row["sha256"] or "") == sha256
                    and int(row["size"] or 0) == size
                    and int(row["mtime_ns"] or 0) == mtime_ns
                    and str(row["status"] or "") == status
                ):
                    return {"changed": False, "file_id": file_id, "index_version": self.index_version()}
            else:
                # 同内容文件的路径迁移：只有「原路径文件确实已不存在」才把记录迁到新路径
                # （移动/改名语义）。若旧路径文件仍在，说明这是两份独立的同内容字体，
                # 与全量重建（每个路径一条记录）口径保持一致，按新路径新建记录。
                same = None
                if sha256:
                    same = conn.execute(
                        "SELECT * FROM font_files WHERE sha256 = ? AND sha256 != '' ORDER BY id LIMIT 1",
                        (sha256,),
                    ).fetchone()
                old_path_exists = False
                if same:
                    old_path = str(same["path"] or "")
                    if old_path and old_path != path:
                        try:
                            old_path_exists = Path(old_path).is_file()
                        except Exception:
                            old_path_exists = True  # 判定不了就当仍在：宁可多一条记录
                if same and int(same["size"] or 0) == size and not old_path_exists:
                    file_id = int(same["id"])
                    conn.execute("UPDATE font_files SET path = ?, mtime_ns = ?, indexed_at = ? WHERE id = ?",
                                 (path, mtime_ns, timestamp, file_id))
                    return {"changed": False, "file_id": file_id, "index_version": self.index_version()}
                cur = conn.execute(
                    "INSERT INTO font_files(path, sha256, size, mtime_ns, format, face_count, status, error, indexed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (path, sha256, size, mtime_ns, fmt, len(faces), status, error, timestamp),
                )
                file_id = int(cur.lastrowid)

            # 修改文件：先撤销旧版本贡献，再写新版本（防止旧别名/cmap 残留）
            conn.execute(
                "DELETE FROM font_aliases WHERE face_id IN (SELECT id FROM font_faces WHERE file_id = ?)",
                (file_id,),
            )
            conn.execute("DELETE FROM font_faces WHERE file_id = ?", (file_id,))
            conn.execute(
                "UPDATE font_files SET sha256 = ?, size = ?, mtime_ns = ?, format = ?, face_count = ?, "
                "status = ?, error = ?, indexed_at = ? WHERE id = ?",
                (sha256, size, mtime_ns, fmt, len(faces), status, error, timestamp, file_id),
            )

            from .font_utils import normalize_font_key

            for face in faces:
                face_status = str(getattr(face, "status", "ok") or "ok")
                cur = conn.execute(
                    "INSERT INTO font_faces(file_id, face_index, family, subfamily, full_name, postscript_name, "
                    "aliases_json, vendor, designer, version, char_count, coverage, status, error) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        file_id,
                        int(getattr(face, "face_index", 0) or 0),
                        str(getattr(face, "family", "") or ""),
                        str(getattr(face, "subfamily", "") or ""),
                        str(getattr(face, "full_name", "") or ""),
                        str(getattr(face, "postscript_name", "") or ""),
                        json.dumps(list(getattr(face, "aliases", []) or []), ensure_ascii=False),
                        str(getattr(face, "vendor", "") or ""),
                        str(getattr(face, "designer", "") or ""),
                        str(getattr(face, "version", "") or ""),
                        int(getattr(face, "char_count", 0) or 0),
                        self._encode_coverage(getattr(face, "codepoints", set())),
                        face_status,
                        str(getattr(face, "error", "") or ""),
                    ),
                )
                face_id = int(cur.lastrowid)
                if face_status != "ok":
                    continue
                keys = set()
                try:
                    keys.update(face.alias_keys())
                except Exception:
                    pass
                for alias in getattr(face, "aliases", []) or []:
                    key = normalize_font_key(str(alias))
                    if key:
                        keys.add(key)
                for key in keys:
                    conn.execute(
                        "INSERT OR IGNORE INTO font_aliases(alias, face_id) VALUES(?, ?)",
                        (key, face_id),
                    )

            vrow = conn.execute("SELECT value FROM index_state WHERE key = 'index_version'").fetchone()
            try:
                version = int(vrow["value"]) if vrow else 0
            except Exception:
                version = 0
            version += 1
            conn.execute(
                "INSERT INTO index_state(key, value) VALUES('index_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(version),),
            )
        return {"changed": True, "file_id": file_id, "index_version": version}

    def remove_font_file(self, path: str) -> Dict[str, Any]:
        """删除字体文件及其 face/别名；返回是否删到、索引版本。"""
        with self.transaction() as conn:
            row = conn.execute("SELECT id FROM font_files WHERE path = ?", (str(path),)).fetchone()
            if not row:
                return {"removed": False, "index_version": self.index_version()}
            file_id = int(row["id"])
            conn.execute(
                "DELETE FROM font_aliases WHERE face_id IN (SELECT id FROM font_faces WHERE file_id = ?)",
                (file_id,),
            )
            conn.execute("DELETE FROM font_faces WHERE file_id = ?", (file_id,))
            conn.execute("DELETE FROM font_files WHERE id = ?", (file_id,))
            vrow = conn.execute("SELECT value FROM index_state WHERE key = 'index_version'").fetchone()
            try:
                version = int(vrow["value"]) if vrow else 0
            except Exception:
                version = 0
            version += 1
            conn.execute(
                "INSERT INTO index_state(key, value) VALUES('index_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(version),),
            )
        return {"removed": True, "index_version": version}

    def lookup_faces(self, name: str) -> List[Dict[str, Any]]:
        """字体名/别名 → face 列表（含 cmap 覆盖集合），供字形级检测与子集化使用。"""
        from .font_utils import normalize_font_key

        key = normalize_font_key(name or "")
        if not key:
            return []
        rows = self.query(
            "SELECT fa.id AS face_id, fa.face_index, fa.family, fa.full_name, fa.aliases_json, fa.coverage, "
            "ff.path, ff.status AS file_status "
            "FROM font_aliases a JOIN font_faces fa ON fa.id = a.face_id "
            "JOIN font_files ff ON ff.id = fa.file_id "
            "WHERE a.alias = ? AND fa.status = 'ok' AND ff.status IN ('ok', 'partial')",
            (key,),
        )
        if not rows:
            # 兜底：别名表为空（旧索引未迁移）时按 family/full_name 精确匹配
            rows = self.query(
                "SELECT fa.id AS face_id, fa.face_index, fa.family, fa.full_name, fa.aliases_json, fa.coverage, "
                "ff.path, ff.status AS file_status "
                "FROM font_faces fa JOIN font_files ff ON ff.id = fa.file_id "
                "WHERE LOWER(fa.family) = LOWER(?) OR LOWER(fa.full_name) = LOWER(?)",
                (name, name),
            )
        result: List[Dict[str, Any]] = []
        for row in rows:
            try:
                names = json.loads(row.get("aliases_json") or "[]")
            except Exception:
                names = []
            result.append(
                {
                    "face_id": int(row["face_id"]),
                    "file_path": row["path"],
                    "face_index": int(row["face_index"] or 0),
                    "family": row.get("family") or "",
                    "full_name": row.get("full_name") or "",
                    "names": names,
                    "codepoints": self._decode_coverage(row.get("coverage")),
                }
            )
        return result

    def index_stats(self) -> Dict[str, Any]:
        files = self.query_one(
            "SELECT COUNT(*) AS c, COALESCE(SUM(face_count),0) AS faces FROM font_files WHERE status IN ('ok','partial')"
        ) or {}
        valid_faces = self.query_one("SELECT COUNT(*) AS c, COALESCE(SUM(char_count),0) AS chars FROM font_faces WHERE status = 'ok'") or {}
        invalid = self.query_one("SELECT COUNT(*) AS c FROM font_faces WHERE status != 'ok'") or {}
        # 最近一次索引写入时间：索引可能由「逐文件增量入库」建立（从未跑过全量重建），
        # 此时 index_state 里没有 last_rebuild，用 font_files.indexed_at 兜底给 UI 显示
        # （只在缺构建时间时查，避免每次轮询都全表扫 indexed_at）
        last_rebuild = self.index_get("last_rebuild", "") or ""
        last_indexed_at = ""
        if not last_rebuild:
            try:
                last_indexed = self.query_one("SELECT MAX(indexed_at) AS t FROM font_files") or {}
                last_indexed_at = str(last_indexed.get("t") or "")
            except Exception:
                last_indexed_at = ""
        return {
            "files": int(files.get("c") or 0),
            "faces": int(valid_faces.get("c") or 0),
            "declared_faces": int(files.get("faces") or 0),
            "chars": int(valid_faces.get("chars") or 0),
            "invalid_faces": int(invalid.get("c") or 0),
            "index_version": self.index_version(),
            "last_rebuild": last_rebuild,
            "last_indexed_at": last_indexed_at,
            "engine": self.index_get("engine", "fontTools") or "fontTools",
        }

    def clear_font_index(self) -> None:
        """清空字体索引（文件/face/别名），用于「全部重建」：随后逐个文件重新解析。

        人工映射（manual_font_mappings）与字幕缺失快照不清理——它们是用户数据，
        不属于字体库索引本身。
        """
        with self.transaction() as conn:
            conn.execute("DELETE FROM font_aliases")
            conn.execute("DELETE FROM font_faces")
            conn.execute("DELETE FROM font_files")
            conn.execute("DELETE FROM index_state WHERE key IN ('last_rebuild', 'engine')")
        self.bump_index_version()

    # ============ 全量重建暂存区（原子切换，失败保留旧索引） ============

    def stage_font_index_begin(self) -> None:
        """建立全量重建暂存表：解析期间旧索引照常可读，最后一次性切换。"""
        with self._lock:
            self._ensure_connected()
            self._conn.executescript(
                "DROP TABLE IF EXISTS font_aliases_stage;"
                "DROP TABLE IF EXISTS font_faces_stage;"
                "DROP TABLE IF EXISTS font_files_stage;"
                "CREATE TABLE font_files_stage("
                "path TEXT, sha256 TEXT, size INTEGER, mtime_ns INTEGER, format TEXT, "
                "face_count INTEGER, status TEXT, error TEXT, indexed_at TEXT);"
                "CREATE TABLE font_faces_stage("
                "path TEXT, face_index INTEGER, family TEXT, subfamily TEXT, full_name TEXT, "
                "postscript_name TEXT, aliases_json TEXT, vendor TEXT, designer TEXT, version TEXT, "
                "char_count INTEGER, coverage BLOB, status TEXT, error TEXT);"
                "CREATE TABLE font_aliases_stage(alias TEXT, path TEXT, face_index INTEGER);"
            )
            self._conn.commit()

    def stage_font_index_add(self, inspection: Any, indexed_at: Optional[str] = None) -> None:
        """把一个字体的解析结果写入暂存表（不触碰正式索引）。"""
        from .font_utils import normalize_font_key

        path = str(getattr(inspection, "path", "") or "")
        timestamp = indexed_at or self.now()
        faces = list(getattr(inspection, "faces", []) or [])
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO font_files_stage(path, sha256, size, mtime_ns, format, face_count, status, error, indexed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    path,
                    str(getattr(inspection, "sha256", "") or ""),
                    int(getattr(inspection, "file_size", 0) or 0),
                    int(getattr(inspection, "mtime_ns", 0) or 0),
                    str(getattr(inspection, "format", "") or ""),
                    len(faces),
                    str(getattr(inspection, "status", "") or "ok"),
                    str(getattr(inspection, "error", "") or ""),
                    timestamp,
                ),
            )
            for face in faces:
                face_status = str(getattr(face, "status", "ok") or "ok")
                idx = int(getattr(face, "face_index", 0) or 0)
                conn.execute(
                    "INSERT INTO font_faces_stage(path, face_index, family, subfamily, full_name, "
                    "postscript_name, aliases_json, vendor, designer, version, char_count, coverage, status, error) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        path,
                        idx,
                        str(getattr(face, "family", "") or ""),
                        str(getattr(face, "subfamily", "") or ""),
                        str(getattr(face, "full_name", "") or ""),
                        str(getattr(face, "postscript_name", "") or ""),
                        json.dumps(list(getattr(face, "aliases", []) or []), ensure_ascii=False),
                        str(getattr(face, "vendor", "") or ""),
                        str(getattr(face, "designer", "") or ""),
                        str(getattr(face, "version", "") or ""),
                        int(getattr(face, "char_count", 0) or 0),
                        self._encode_coverage(getattr(face, "codepoints", set())),
                        face_status,
                        str(getattr(face, "error", "") or ""),
                    ),
                )
                if face_status != "ok":
                    continue
                keys = set()
                try:
                    keys.update(face.alias_keys())
                except Exception:
                    pass
                for alias in getattr(face, "aliases", []) or []:
                    key = normalize_font_key(str(alias))
                    if key:
                        keys.add(key)
                for key in keys:
                    conn.execute(
                        "INSERT OR IGNORE INTO font_aliases_stage(alias, path, face_index) VALUES(?, ?, ?)",
                        (key, path, idx),
                    )

    def stage_font_index_commit(self, lib_dir: str = "", engine: str = "fontTools") -> Dict[str, Any]:
        """暂存表 → 正式索引：单事务原子切换，成功后写 last_rebuild/engine/lib_dir。

        事务期间持有 DB 锁，其他线程的查询会被阻塞到提交完成，看不到「空索引」中间态。
        """
        with self.transaction() as conn:
            conn.execute("DELETE FROM font_aliases")
            conn.execute("DELETE FROM font_faces")
            conn.execute("DELETE FROM font_files")
            conn.execute(
                "INSERT INTO font_files(path, sha256, size, mtime_ns, format, face_count, status, error, indexed_at) "
                "SELECT path, sha256, size, mtime_ns, format, face_count, status, error, indexed_at "
                "FROM font_files_stage"
            )
            conn.execute(
                "INSERT INTO font_faces(file_id, face_index, family, subfamily, full_name, postscript_name, "
                "aliases_json, vendor, designer, version, char_count, coverage, status, error) "
                "SELECT ff.id, sf.face_index, sf.family, sf.subfamily, sf.full_name, sf.postscript_name, "
                "sf.aliases_json, sf.vendor, sf.designer, sf.version, sf.char_count, sf.coverage, sf.status, sf.error "
                "FROM font_faces_stage sf JOIN font_files ff ON ff.path = sf.path"
            )
            conn.execute(
                "INSERT INTO font_aliases(alias, face_id) "
                "SELECT sa.alias, fa.id FROM font_aliases_stage sa "
                "JOIN font_files ff ON ff.path = sa.path "
                "JOIN font_faces fa ON fa.file_id = ff.id AND fa.face_index = sa.face_index"
            )
            timestamp = self.now()
            for key, value in (
                ("last_rebuild", timestamp),
                ("engine", engine),
                ("lib_dir", str(lib_dir or "")),
            ):
                conn.execute(
                    "INSERT INTO index_state(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )
            vrow = conn.execute("SELECT value FROM index_state WHERE key = 'index_version'").fetchone()
            try:
                version = int(vrow["value"]) if vrow else 0
            except Exception:
                version = 0
            version += 1
            conn.execute(
                "INSERT INTO index_state(key, value) VALUES('index_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(version),),
            )
            conn.execute("DROP TABLE IF EXISTS font_aliases_stage")
            conn.execute("DROP TABLE IF EXISTS font_faces_stage")
            conn.execute("DROP TABLE IF EXISTS font_files_stage")
        return {"index_version": version, "last_rebuild": timestamp}

    def stage_font_index_discard(self) -> None:
        """放弃本轮重建：删除暂存表，正式索引保持原样。"""
        with self._lock:
            self._ensure_connected()
            self._conn.executescript(
                "DROP TABLE IF EXISTS font_aliases_stage;"
                "DROP TABLE IF EXISTS font_faces_stage;"
                "DROP TABLE IF EXISTS font_files_stage;"
            )
            self._conn.commit()

    def replace_missing_glyphs(self, ass_id: Optional[int], file_path: str, verdicts: List[Dict[str, Any]]) -> None:
        """写入一次字形级检测快照；每个 ass 仅保留最近 20 次，历史不删整条记录。"""
        timestamp = self.now()
        with self.transaction() as conn:
            for item in verdicts:
                conn.execute(
                    "INSERT INTO ass_missing_glyphs(ass_id, file_path, font_name, used_count, missing_count, "
                    "missing_codepoints, missing_chars, status, faces_json, check_time) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        int(ass_id) if ass_id is not None else None,
                        str(file_path or ""),
                        str(item.get("name") or ""),
                        int(item.get("used_count") or 0),
                        int(item.get("missing_count") or 0),
                        json.dumps(item.get("missing_codepoints") or [], ensure_ascii=False),
                        str(item.get("missing_chars") or ""),
                        str(item.get("status") or ""),
                        json.dumps(item.get("faces") or [], ensure_ascii=False),
                        timestamp,
                    ),
                )
            if ass_id is not None:
                conn.execute(
                    "DELETE FROM ass_missing_glyphs WHERE ass_id = ? AND id NOT IN "
                    "(SELECT id FROM ass_missing_glyphs WHERE ass_id = ? ORDER BY id DESC LIMIT 20)",
                    (int(ass_id), int(ass_id)),
                )

    def latest_missing_glyphs(self, ass_id: int) -> List[Dict[str, Any]]:
        rows = self.query(
            "SELECT * FROM ass_missing_glyphs WHERE ass_id = ? ORDER BY id DESC",
            (int(ass_id),),
        )
        if not rows:
            return []
        latest_time = rows[0].get("check_time")
        result = []
        for row in rows:
            if row.get("check_time") != latest_time:
                break
            try:
                row["missing_codepoints"] = json.loads(row.get("missing_codepoints") or "[]")
                row["faces_json"] = json.loads(row.get("faces_json") or "[]")
            except Exception:
                pass
            result.append(row)
        return result

    def set_ass_check_detail(
        self,
        ass_id: int,
        missing_details: List[Dict[str, Any]],
        file_sha256: str = "",
        index_version: int = 0,
        check_engine: str = "",
    ) -> None:
        self.execute(
            "UPDATE ass_files SET missing_details = ?, file_sha256 = ?, index_version = ?, check_engine = ? "
            "WHERE id = ?",
            (
                json.dumps(missing_details, ensure_ascii=False),
                file_sha256 or "",
                int(index_version or 0),
                check_engine or "",
                int(ass_id),
            ),
        )

    def all_missing_font_names(self) -> List[str]:
        """当前所有检查记录里仍缺失的字体名（严格上传匹配目标用）。

        以「每个 ass 每个字体最近一次检测」为准（历史快照只留档，不参与匹配）。
        """
        names = set()
        for row in self.query("SELECT DISTINCT missing_fonts FROM ass_files"):
            try:
                for name in json.loads(row.get("missing_fonts") or "[]"):
                    if name:
                        names.add(str(name))
            except Exception:
                continue
        try:
            rows = self.query(
                "SELECT g.font_name FROM ass_missing_glyphs g "
                "JOIN ass_files a ON a.id = g.ass_id "
                "WHERE g.id IN (SELECT MAX(id) FROM ass_missing_glyphs GROUP BY ass_id, font_name) "
                "AND g.status IN ('missing', 'partial')"
            )
            for row in rows:
                name = str(row.get("font_name") or "")
                if name:
                    names.add(name)
        except Exception:
            pass
        return sorted(names)

    def set_manual_font_mapping(self, source_name: str, target_name: str, file_sha256: str = "", note: str = "") -> None:
        self.execute(
            "INSERT INTO manual_font_mappings(source_name, target_name, file_sha256, note, created_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(source_name, target_name) DO UPDATE SET file_sha256 = excluded.file_sha256, "
            "note = excluded.note, created_at = excluded.created_at",
            (str(source_name), str(target_name), str(file_sha256 or ""), str(note or ""), self.now()),
        )

    def get_manual_font_mapping(self, source_name: str) -> Optional[Dict[str, Any]]:
        return self.query_one(
            "SELECT * FROM manual_font_mappings WHERE source_name = ? ORDER BY id DESC LIMIT 1",
            (str(source_name),),
        )

    def delete_manual_font_mapping_pair(self, source_name: str, target_name: str) -> None:
        """取消/移除未入库的上传时，清理对应的人工映射审计记录，避免幽灵记录。"""
        self.execute(
            "DELETE FROM manual_font_mappings WHERE source_name = ? AND target_name = ?",
            (str(source_name or ""), str(target_name or "")),
        )

    def list_manual_font_mappings(self) -> List[Dict[str, Any]]:
        return self.query("SELECT * FROM manual_font_mappings ORDER BY id DESC")

    def delete_manual_font_mapping(self, mapping_id: int) -> None:
        self.execute("DELETE FROM manual_font_mappings WHERE id = ?", (int(mapping_id),))

    def get_last_scan_time(self) -> str:
        """上次「全量检查」完成时间（字体库/检查页全量检查时由 set_last_scan_time 写入）

        优先取显式记录；无记录时回退旧口径：日志表里最新的「扫描…」日志时间。
        """
        saved = self.get_setting("last_scan", "")
        if saved:
            return str(saved)
        row = self.query_one("SELECT MAX(time) AS t FROM logs WHERE message LIKE '扫描%'")
        return row["t"] or "" if row else ""

    def set_last_scan_time(self) -> None:
        """记录一次全量检查完成时间（供仪表盘「上次全量检查」展示）"""
        try:
            self.set_setting("last_scan", self.now())
        except Exception:
            pass

    # ============ 数据库备份与恢复 ============

    # 备份中包含的业务表（导入/导出/清空的作用域）；logs 记录太多且非业务数据，不参与导入导出，
    # 但清空时一并清掉可选，这里仅清业务表，保留日志与 plugin_settings（配置镜像）。
    # 备份中参与导出/导入的业务表（logs 太多且非业务数据，不参与）。
    # ass_missing_glyphs（逐字形缺失快照）与 manual_font_mappings（人工字体映射）是用户数据，
    # 必须随备份保存，否则恢复后逐字符缺失明细/人工映射丢失。
    # 增量索引表（font_files/font_faces/font_aliases）含 BLOB（cmap 覆盖）且可从磁盘重建，
    # 不导出，恢复时清空并由插件重新索引。
    _EXPORT_TABLES = (
        "fonts",
        "pending_fonts",
        "ass_files",
        "ass_missing_glyphs",
        "manual_font_mappings",
        "subset_records",
        "subset_pending",
    )
    # 恢复时必须存在于备份中的核心表（缺失说明备份文件不完整，直接拒绝）
    _REQUIRED_EXPORT_TABLES = ("fonts", "ass_files", "pending_fonts")
    # 备份格式版本：v1（旧，缺缺失快照/人工映射）→ v2（当前）
    _BACKUP_VERSION = 2
    _CLEAR_TABLES = _EXPORT_TABLES + (
        "font_aliases",
        "font_faces",
        "font_files",
    )

    def export_all(self) -> Dict[str, Any]:
        """导出业务表数据 + 配置镜像为 JSON 备份"""
        with self._lock:
            self._ensure_connected()
            tables: Dict[str, List[Dict[str, Any]]] = {}
            for table in self._EXPORT_TABLES:
                tables[table] = self.query(f"SELECT * FROM {table}")
            return {
                "version": self._BACKUP_VERSION,
                "exported_at": self.now(),
                "tables": tables,
                "full_config": self.get_full_config(),
            }

    def import_all(self, backup: Dict[str, Any]) -> Dict[str, int]:
        """从 JSON 备份恢复：校验 → 单事务内替换业务表并清空字体索引。

        - 备份缺少核心表（fonts/ass_files/pending_fonts）→ 拒绝导入；
        - 旧版备份（v1）不含缺失字形快照/人工映射：保留现有数据不动，避免误清；
        - 字体索引（font_files/font_faces/font_aliases）随恢复清空并递增 index_version：
          恢复后的业务表来自另一份库，旧索引路径/名称/cmap 可能已错位，必须重建；
        - 全部动作在单一事务内完成，任何异常整体回滚。
        """
        tables = backup.get("tables") if isinstance(backup, dict) else None
        if not isinstance(tables, dict):
            raise ValueError("备份数据缺少 tables")
        for table in self._REQUIRED_EXPORT_TABLES:
            if not isinstance(tables.get(table), list):
                raise ValueError(f"备份数据缺少必要的数据表: {table}")
        with self._lock:
            self._ensure_connected()
            self._conn.execute("BEGIN")
            try:
                counts: Dict[str, int] = {}
                for table in self._EXPORT_TABLES:
                    if table not in tables:
                        # 旧版备份没有该表：保留当前数据（兼容迁移，不误清用户数据）
                        continue
                    rows = tables.get(table)
                    if not isinstance(rows, list):
                        raise ValueError(f"备份表 {table} 数据格式错误")
                    # 写回前按业务列白名单过滤，避免注入任意列
                    valid_cols = self._table_columns(table)
                    self._conn.execute(f"DELETE FROM {table}")
                    written = 0
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        clean = {k: v for k, v in row.items() if k in valid_cols}
                        if not clean:
                            continue
                        cols = ", ".join(clean.keys())
                        marks = ", ".join(["?"] * len(clean))
                        self._conn.execute(
                            f"INSERT INTO {table} ({cols}) VALUES ({marks})",
                            tuple(clean.values()),
                        )
                        written += 1
                    counts[table] = written
                # 恢复配置镜像（如果备份里带了）——直接用连接执行，保持在同一事务内
                cfg = backup.get("full_config")
                if isinstance(cfg, dict):
                    self._conn.execute(
                        "INSERT INTO plugin_settings (key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        ("full_config", json.dumps(cfg, ensure_ascii=False)),
                    )
                # 已处理源字体标记随恢复重置：恢复后的字体库已变化，待整理按重扫结果重算
                self._conn.execute("DELETE FROM processed_fonts")
                # 字体索引整体作废：恢复的业务表来自另一份库，旧索引可能与新库错位
                self._conn.execute("DELETE FROM font_aliases")
                self._conn.execute("DELETE FROM font_faces")
                self._conn.execute("DELETE FROM font_files")
                self._conn.execute(
                    "DELETE FROM index_state WHERE key IN ('last_rebuild', 'engine')"
                )
                vrow = self._conn.execute(
                    "SELECT value FROM index_state WHERE key = 'index_version'"
                ).fetchone()
                try:
                    version = int(vrow["value"]) if vrow else 0
                except Exception:
                    version = 0
                version += 1
                self._conn.execute(
                    "INSERT INTO index_state(key, value) VALUES('index_version', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (str(version),),
                )
                # 重置自增主键到当前最大值，避免导入后 id 冲突
                self._reset_auto_increment()
                self._conn.commit()
                return counts
            except Exception:
                self._conn.rollback()
                raise

    def clear_all(self) -> Dict[str, int]:
        """清空业务表（字体库、待确认、ASS 检查记录）；保留日志与配置镜像"""
        with self._lock:
            self._ensure_connected()
            counts: Dict[str, int] = {}
            for table in self._CLEAR_TABLES:
                row = self.query_one(f"SELECT COUNT(*) AS c FROM {table}")
                counts[table] = row["c"] if row else 0
                self.execute(f"DELETE FROM {table}")
            # 已处理源字体标记一并清空：清库后按重扫结果重算待整理
            self.execute("DELETE FROM processed_fonts")
            # 索引状态同步复位：清库后不能继续展示上一次的重建时间/引擎版本
            self.execute("DELETE FROM index_state WHERE key IN ('last_rebuild', 'engine')")
            self.execute("DELETE FROM index_state WHERE key = 'lib_dir'")
            self.bump_index_version()
            self._reset_auto_increment()
            return counts

    def _reset_auto_increment(self) -> None:
        """将 sqlite_sequence 重置为各表当前最大 id，避免导入/清空后主键冲突

        复合主键表（font_aliases）没有 id 列，逐表容错：单表失败不影响后续表。
        """
        for table in self._CLEAR_TABLES + ("logs",):
            try:
                row = self._conn.execute(f"SELECT MAX(id) AS m FROM {table}").fetchone()
                max_id = row["m"] if row and row["m"] is not None else 0
                self._conn.execute(
                    "UPDATE sqlite_sequence SET seq = ? WHERE name = ?",
                    (max_id, table),
                )
            except Exception:
                continue

    def _table_columns(self, table: str) -> set:
        """返回表的所有列名（白名单），用于导入时过滤字段"""
        rows = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {r["name"] for r in rows}

    # ============ 种子字体截取记录 ============

    def add_torrent_ingest(
        self,
        torrent_hash: str,
        downloader: str,
        torrent_name: str,
        source: str,
        status: str = "pending",
        picked: int = 0,
        added: int = 0,
        skipped: int = 0,
        failed: int = 0,
        detail: str = "",
    ) -> int:
        """新增一条种子截取记录，返回自增 ID。"""
        try:
            cur = self._conn.execute(
                "INSERT INTO torrent_ingest (hash, downloader, torrent_name, source, status, "
                "picked, added, skipped, failed, detail, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(torrent_hash or ""),
                    str(downloader or ""),
                    str(torrent_name or ""),
                    str(source or ""),
                    str(status or ""),
                    int(picked or 0),
                    int(added or 0),
                    int(skipped or 0),
                    int(failed or 0),
                    str(detail or "")[:1000],
                    self.now(),
                ),
            )
            try:
                self._conn.commit()
            except Exception:
                pass
            return int(cur.lastrowid or 0)
        except Exception:
            return 0

    def update_torrent_ingest(self, record_id: int, **fields: Any) -> None:
        """按 ID 更新种子截取记录（只允许白名单字段）。"""
        if not record_id:
            return
        allow = {"status", "picked", "added", "skipped", "failed", "detail", "torrent_name", "source"}
        pairs = [(k, v) for k, v in fields.items() if k in allow]
        if not pairs:
            return
        sets = ", ".join(f"{k} = ?" for k, _ in pairs)
        values = [v for _, v in pairs]
        values.append(int(record_id))
        try:
            self.execute(f"UPDATE torrent_ingest SET {sets} WHERE id = ?", tuple(values))
        except Exception:
            pass

    def list_torrent_ingest(self, limit: int = 20) -> List[Dict[str, Any]]:
        try:
            return self.query(
                "SELECT * FROM torrent_ingest ORDER BY id DESC LIMIT ?", (int(limit),)
            )
        except Exception:
            return []

    def get_torrent_ingest_by_hash(self, torrent_hash: str) -> Optional[Dict[str, Any]]:
        """取该种子最近一条成功记录（幂等判断用）。"""
        if not torrent_hash:
            return None
        try:
            rows = self.query(
                "SELECT * FROM torrent_ingest WHERE hash = ? AND status IN ('done', 'empty') "
                "ORDER BY id DESC LIMIT 1",
                (str(torrent_hash),),
            )
            return rows[0] if rows else None
        except Exception:
            return None

    def clear_torrent_ingest(self) -> int:
        """清空种子截取记录（只删记录，不动任何文件）。"""
        try:
            row = self.query_one("SELECT COUNT(*) AS c FROM torrent_ingest")
            count = int(row["c"]) if row else 0
            self.execute("DELETE FROM torrent_ingest")
            return count
        except Exception:
            return 0
