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

CREATE TABLE IF NOT EXISTS ass_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT DEFAULT '',
    source TEXT DEFAULT 'manual',
    status TEXT DEFAULT 'ok',
    check_time TEXT,
    missing_count INTEGER DEFAULT 0,
    missing_fonts TEXT DEFAULT '[]',
    all_fonts TEXT DEFAULT '[]',
    file_path TEXT DEFAULT ''
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
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS subset_pending (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT DEFAULT '',
    file_path TEXT DEFAULT '',
    source TEXT DEFAULT 'upload',
    created_at TEXT
);
"""


class FontDB:
    """SQLite 封装，线程安全"""

    def __init__(self, db_path: str | Path):
        self._path = str(db_path)
        self._lock = threading.RLock()
        self._conn = None
        self._ensure_connected()

    def _ensure_connected(self) -> None:
        if self._conn is None:
            self._conn = sqlite3.connect(self._path, check_same_thread=False)
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

    def close(self) -> None:
        with self._lock:
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

    def add_log(self, message: str, level: str = "info") -> None:
        try:
            self.execute(
                "INSERT INTO logs (time, level, message) VALUES (?, ?, ?)",
                (self.now(), level, message),
            )
            # 保留最近 200 条日志
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
        """读取插件内部状态（存储为字符串，返回时尝试还原）"""
        try:
            row = self.query_one("SELECT value FROM plugin_settings WHERE key = ?", (key,))
            if row is None:
                return default
            val = row["value"]
            if val == "True":
                return True
            if val == "False":
                return False
            if val.isdigit():
                return int(val)
            return val
        except Exception:
            return default

    def set_setting(self, key: str, value: Any) -> None:
        """保存插件内部状态"""
        try:
            if value is True or value is False:
                val = "True" if value else "False"
            elif value is None:
                val = ""
            else:
                val = str(value)
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
        self.execute(
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
        row = self.query_one("SELECT id FROM fonts WHERE file_path = ? ORDER BY id DESC LIMIT 1", (item.get("file_path", ""),))
        return row["id"] if row else 0

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
        return {
            "total": total,
            "pending": pending,
            "archived": archived,
            "error": missing,
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
            """INSERT INTO subset_records (file_name, file_path, status, reason, out_file, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                item.get("file_name", ""),
                item.get("file_path", ""),
                item.get("status", "pending"),
                item.get("reason", ""),
                item.get("out_file", ""),
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
    ) -> None:
        self.execute(
            """INSERT INTO ass_files (file_name, source, status, check_time, missing_count, missing_fonts, all_fonts, file_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                file_name,
                source,
                status,
                self.now(),
                len(missing_fonts),
                json.dumps(missing_fonts, ensure_ascii=False),
                json.dumps(all_fonts, ensure_ascii=False),
                file_path,
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
            f"SELECT id, file_name, source, status, check_time, missing_count FROM ass_files {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?",
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
        self.execute("DELETE FROM ass_files WHERE id = ?", (int(ass_id),))

    def clear_ass(self) -> None:
        self.execute("DELETE FROM ass_files")

    def all_font_families(self) -> List[str]:
        rows = self.query("SELECT DISTINCT family FROM fonts WHERE family != ''")
        names = [r["family"] for r in rows]
        names += [r["name"] for r in self.query("SELECT DISTINCT name FROM fonts WHERE name != ''")]
        return list(set(names))

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
    _BUSINESS_TABLES = ("fonts", "pending_fonts", "ass_files", "subset_records", "subset_pending")

    def export_all(self) -> Dict[str, Any]:
        """导出业务表数据 + 配置镜像为 JSON 备份"""
        with self._lock:
            self._ensure_connected()
            tables: Dict[str, List[Dict[str, Any]]] = {}
            for table in self._BUSINESS_TABLES:
                tables[table] = self.query(f"SELECT * FROM {table}")
            return {
                "version": 1,
                "exported_at": self.now(),
                "tables": tables,
                "full_config": self.get_full_config(),
            }

    def import_all(self, backup: Dict[str, Any]) -> Dict[str, int]:
        """从 JSON 备份恢复：校验版本 → 清空业务表 → 逐表写回数据；返回各表写入行数"""
        tables = backup.get("tables") if isinstance(backup, dict) else None
        if not isinstance(tables, dict):
            raise ValueError("备份数据缺少 tables")
        with self._lock:
            self._ensure_connected()
            self._conn.execute("BEGIN")
            try:
                counts: Dict[str, int] = {}
                for table in self._BUSINESS_TABLES:
                    rows = tables.get(table)
                    if not isinstance(rows, list):
                        self._conn.execute(f"DELETE FROM {table}")
                        counts[table] = 0
                        continue
                    # 写回前按业务列白名单过滤，避免注入任意列
                    valid_cols = self._table_columns(table)
                    self._conn.execute(f"DELETE FROM {table}")
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
                    counts[table] = len(rows)
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
            for table in self._BUSINESS_TABLES:
                row = self.query_one(f"SELECT COUNT(*) AS c FROM {table}")
                counts[table] = row["c"] if row else 0
                self.execute(f"DELETE FROM {table}")
            # 已处理源字体标记一并清空：清库后按重扫结果重算待整理
            self.execute("DELETE FROM processed_fonts")
            self._reset_auto_increment()
            return counts

    def _reset_auto_increment(self) -> None:
        """将 sqlite_sequence 重置为各表当前最大 id，避免导入/清空后主键冲突"""
        try:
            for table in self._BUSINESS_TABLES + ("logs",):
                row = self._conn.execute(f"SELECT MAX(id) AS m FROM {table}").fetchone()
                max_id = row["m"] if row and row["m"] is not None else 0
                self._conn.execute(
                    "UPDATE sqlite_sequence SET seq = ? WHERE name = ?",
                    (max_id, table),
                )
        except Exception:
            pass

    def _table_columns(self, table: str) -> set:
        """返回表的所有列名（白名单），用于导入时过滤字段"""
        rows = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {r["name"] for r in rows}