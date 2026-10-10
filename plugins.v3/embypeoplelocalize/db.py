r"""
db.py - 演职人员翻译记录 独立数据库层  (v3.4.31 重构)
不再占用 MP 主数据库（宿主 SQLite/PostgreSQL）的插件表，
改用插件自己的独立 SQLite 文件 data.db，存放于插件数据目录
（setting.CONFIG_PATH/plugins/embypeoplelocalize，NAS 容器 /config 挂载，
Windows 侧可见为 config/plugins/embypeoplelocalize）。
docstring 改 raw 字符串（原 \m 无效转义触发 SyntaxWarning，Python 未来版本会升级为 SyntaxError）。
启动时把 MP 主库旧表数据（plugin_embypeople_person / plugin_embypeople_name_map）
自动迁移一次（幂等，meta 标记）。
存储方式参考 zitifenlei 插件：原生 sqlite3 + 线程锁（RLock + WAL）。
"""
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.sdk.logging import logger


# ---------------- 数据目录 / 连接 ----------------

def _data_dir() -> Path:
    """插件数据目录：宿主 settings.CONFIG_PATH/plugins/embypeoplelocalize"""
    try:
        from app.sdk.config import settings
        cfg = getattr(settings, "CONFIG_PATH", None)
        if cfg is not None:
            return Path(str(cfg)) / "plugins" / "embypeoplelocalize"
    except Exception:
        pass
    # 兜底：相对 cwd（容器内 cwd=/ 时等价 /config/plugins/embypeoplelocalize）
    return Path("config") / "plugins" / "embypeoplelocalize"


def db_path() -> str:
    return str(_data_dir() / "data.db")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS person (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plugin_id TEXT DEFAULT '',
    server_id TEXT DEFAULT '',
    item_id TEXT DEFAULT '',
    item_type TEXT DEFAULT '',
    title TEXT DEFAULT '',
    series_name TEXT DEFAULT '',
    season_num INTEGER,
    episode_num INTEGER,
    library_name TEXT DEFAULT '',
    person_index INTEGER DEFAULT 0,
    person_type TEXT DEFAULT 'Actor',
    name_before TEXT DEFAULT '',
    name_after TEXT DEFAULT '',
    role_before TEXT DEFAULT '',
    role_after TEXT DEFAULT '',
    translated_at TEXT DEFAULT '',
    nfo_path TEXT DEFAULT '',
    deleted_at TEXT DEFAULT '',
    -- v4.6.66（P0-2）：Emby ItemId 与媒体 item_id 分离 —— item_id 存媒体身份
    -- （tmdb/tvdb/imdb/nfo:hash），emby_item_id 单存 Emby 服务器条目 ID（Webhook 事件 ID），
    -- 两者不得混用（日志/恢复/删除匹配各用各的）。
    emby_item_id TEXT DEFAULT '',
    -- v4.6.72（批次3 · 洗版稳定身份）：把 item_id 显式拆成「provider + id」并单列
    -- 「series_media_id」（集记录所属剧的稳定媒体身份）—— 洗版后路径/标题/Emby ItemId
    -- 全变，只要 provider 未变即可识别为同一媒体并恢复旧译文（见 docs 第八~十节）。
    media_provider TEXT DEFAULT '',
    media_id TEXT DEFAULT '',
    series_media_id TEXT DEFAULT '',
    -- 文件指纹（nfo 内容 + 大小签名），辅助识别「同一文件被重新刮削」——
    -- 仅作参考，稳定恢复仍以 provider 身份为准。
    file_fingerprint TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_person_lookup ON person (plugin_id, item_id, server_id, season_num, episode_num, person_index);
-- 库列表分页（library_items_page）聚合索引：GROUP BY COALESCE(server_id,''), COALESCE(item_id,'')
-- 与分组键逐字一致，使大库下分页聚合走索引顺序扫描、避免全表临时排序。
CREATE INDEX IF NOT EXISTS idx_person_page ON person (plugin_id, COALESCE(server_id,''), COALESCE(item_id,''));
-- v4.6.72（批次3）：稳定媒体身份索引（idx_person_media / idx_person_series_media）**不在此处建** ——
-- _SCHEMA 每次连接都执行，旧库 person 还没补 media_provider 列时 CREATE INDEX 会失败导致连接不可用。
-- 改由 migrate() 的 v12 在补列之后创建（与 idx_writeback_item 同理）。
CREATE TABLE IF NOT EXISTS name_map (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plugin_id TEXT DEFAULT '',
    name_type TEXT DEFAULT 'person',
    name_original TEXT DEFAULT '',
    name_zh TEXT DEFAULT '',
    source TEXT DEFAULT 'zhconv',
    updated_at TEXT DEFAULT '',
    -- 人名池主数据字段（Person 身份 = server_id + emby_person_id；名字只是属性）
    server_id TEXT DEFAULT '',
    emby_person_id TEXT DEFAULT '',
    name_current TEXT DEFAULT '',
    person_type TEXT DEFAULT '',
    person_types TEXT DEFAULT '',
    translation_status TEXT DEFAULT '',
    sync_status TEXT DEFAULT '',
    last_sync_at TEXT DEFAULT '',
    sync_error TEXT DEFAULT '',
    -- 无 emby_person_id 的旧导入行标记（用 server_id+name_original 作 legacy 临时键，防重复）
    legacy_identity INTEGER DEFAULT 0,
    -- 池生命周期（Emby 镜像态）—— active 本次见到 / stale 本次未见 / missing 连续多次未见
    pool_sync_state TEXT DEFAULT 'active',
    pool_miss_count INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_name_map_lookup ON name_map (plugin_id, name_type, name_original);
-- 第二排角色跨集复用（v4.6.70 · 报告第二十~三十四节）：同剧同角色的翻译记忆。
-- 全局 name_map 无法表达「按剧作用域」——同一角色名在不同作品本就可能有不同译文
-- （Guardian→守护者 / Guardian→守门人），故单列一张带 series_id 维度的记忆表。
-- 与 person 表**解耦**：删除某集 / 整剧删除 / 恢复 / 清空翻译记录都不会清它，
-- 只有显式「清除该剧翻译记忆」才删 —— 洗版后重建也能继续复用旧译文。
CREATE TABLE IF NOT EXISTS role_memory (
    plugin_id TEXT NOT NULL DEFAULT '',
    server_id TEXT NOT NULL DEFAULT '',
    series_id TEXT NOT NULL DEFAULT '',
    series_name TEXT DEFAULT '',
    role_original TEXT NOT NULL,
    role_translated TEXT DEFAULT '',
    source TEXT DEFAULT 'llm',
    updated_at TEXT DEFAULT '',
    PRIMARY KEY (plugin_id, server_id, series_id, role_original)
);
CREATE INDEX IF NOT EXISTS idx_role_mem_name
    ON role_memory (plugin_id, server_id, series_name, role_original);
-- 洗版历史身份别名（v4.6.72 · 报告第十节）—— 同一媒体洗版后 Emby ItemId / 路径 / 标题变化，
-- 但 provider（TMDB/TVDB/IMDb）未变：把「旧身份 → 新身份」记下来，后续查询可直接归一，
-- 也用于日志/排查「这是同一个媒体的洗版恢复」。与 person 表解耦，删除/恢复不清。
CREATE TABLE IF NOT EXISTS media_identity_alias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plugin_id TEXT DEFAULT '',
    server_id TEXT DEFAULT '',
    provider TEXT DEFAULT '',            -- tmdb / tvdb / imdb
    provider_id TEXT DEFAULT '',         -- provider 值（如 1177096）
    old_media_id TEXT DEFAULT '',        -- 旧媒体 item_id
    old_emby_item_id TEXT DEFAULT '',    -- 旧 Emby ItemId
    old_nfo_path TEXT DEFAULT '',
    old_title TEXT DEFAULT '',
    new_media_id TEXT DEFAULT '',        -- 新媒体 item_id
    first_seen TEXT DEFAULT '',
    last_seen TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_media_alias ON media_identity_alias (plugin_id, server_id, provider, provider_id);
CREATE INDEX IF NOT EXISTS idx_media_alias_old ON media_identity_alias (plugin_id, old_media_id);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT DEFAULT ''
);
-- 写回状态（条目级幂等：pending/writing/done/failed/missing）
CREATE TABLE IF NOT EXISTS writeback_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plugin_id TEXT DEFAULT '',
    server_id TEXT DEFAULT '',
    item_id TEXT DEFAULT '',
    nfo_path TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    last_attempt_at TEXT DEFAULT '',
    last_success_at TEXT DEFAULT '',
    error TEXT DEFAULT '',
    changed_count INTEGER DEFAULT 0,
    -- 条目写回指纹（译文内容 + nfo 文件签名）—— done 且指纹未变 → 不重复写（文档 §15）
    file_sig TEXT DEFAULT '',
    -- 写回尝试次数（失败自动重试上限；新译文重新登记时归零）
    attempts INTEGER DEFAULT 0,
    -- 登记该候选时的任务目标范围（person/role/both）——
    -- 就绪判定按此范围，不依赖瞬时 _tx_target_scope（防「只翻第二排」被第一排 pending 重新阻塞）
    target_scope TEXT DEFAULT '',
    updated_at TEXT DEFAULT ''
);
-- (plugin_id, server_id, item_id) 的唯一索引不能放在这里 —— _SCHEMA 每次连接
-- 都会执行，旧库若仍有并发登记产生的重复行，CREATE UNIQUE INDEX 会失败导致连接不可用。
-- 改为「先去重、后建唯一索引」的迁移步骤（见 migrate() 的 v7），此处只保留按路径查询的索引。
CREATE INDEX IF NOT EXISTS idx_writeback_path ON writeback_state (plugin_id, nfo_path);
-- 翻译任务持久化（v4.6.61 · P1-6）—— 重启不静默丢任务：
-- queued/running 的「重新翻译」Job 重启后恢复入队；统计口径与日志共用同一份数据。
CREATE TABLE IF NOT EXISTS translate_jobs (
    id TEXT PRIMARY KEY,
    plugin_id TEXT DEFAULT '',
    job_type TEXT DEFAULT '',        -- auto（常规消费许可）/ force（重新翻译）/ manual
    source TEXT DEFAULT '',          -- library / pool / both
    scope TEXT DEFAULT '',           -- person / role / both
    status TEXT DEFAULT 'queued',    -- queued/running/paused/rate_limited/quota_paused/done/failed/cancelled/interrupted
    batch_mode TEXT DEFAULT '',      -- per_title / global
    batch_size INTEGER DEFAULT 0,
    item_count INTEGER DEFAULT 0,
    term_count INTEGER DEFAULT 0,
    translated_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    llm_request_count INTEGER DEFAULT 0,
    rate_limit_count INTEGER DEFAULT 0,
    quota_error_count INTEGER DEFAULT 0,
    remaining_count INTEGER DEFAULT 0,
    writeback_pending_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT '',
    started_at TEXT DEFAULT '',
    finished_at TEXT DEFAULT '',
    next_retry_at TEXT DEFAULT '',
    error_message TEXT DEFAULT '',
    payload TEXT DEFAULT ''          -- JSON：force 任务的条目范围（items/terms/scope）等
);
CREATE INDEX IF NOT EXISTS idx_tjobs_status ON translate_jobs (plugin_id, status, created_at);
-- 翻译任务逐词条明细（v4.6.62 · 第 24 节）—— 精确重试与进度追溯：
-- 每个 Job 的待翻词条落一行，成功提交 / 失败留痕，重启后可据此重放未提交项。
CREATE TABLE IF NOT EXISTS translate_job_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT DEFAULT '',
    plugin_id TEXT DEFAULT '',
    term_id TEXT DEFAULT '',          -- 词条稳定键（term + item + kind）
    item_id TEXT DEFAULT '',
    server_id TEXT DEFAULT '',
    season_num INTEGER,
    episode_num INTEGER,
    person_index INTEGER DEFAULT 0,
    kind TEXT DEFAULT '',             -- person / role
    person_type TEXT DEFAULT '',
    original_text TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',    -- pending/claimed/translated/failed/skipped
    translation TEXT DEFAULT '',
    claimed_at TEXT DEFAULT '',
    translated_at TEXT DEFAULT '',
    error_message TEXT DEFAULT '',
    retry_count INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tjob_terms ON translate_job_terms (plugin_id, job_id, status);
-- 翻译任务逐批次明细（v4.6.62 · 第 24 节）—— 真实请求次数 / 返回条数 / 令牌 / 耗时留痕
CREATE TABLE IF NOT EXISTS translate_job_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT DEFAULT '',
    plugin_id TEXT DEFAULT '',
    batch_id INTEGER DEFAULT 0,
    status TEXT DEFAULT '',           -- ok/partial/failed/rate_limited/quota/etc
    request_no INTEGER DEFAULT 0,
    term_count INTEGER DEFAULT 0,
    returned_count INTEGER DEFAULT 0,
    attempt_count INTEGER DEFAULT 0,
    http_status INTEGER DEFAULT 0,
    error_kind TEXT DEFAULT '',
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    started_at TEXT DEFAULT '',
    finished_at TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_tjob_batches ON translate_job_batches (plugin_id, job_id, batch_id);
"""

SCHEMA_VERSION = 12

# 「词条 × 条目」明细对上限（v4.6.61 唯一快照用）—— 防超大库下一次拉取过多行；
# 触顶时快照按已取部分统计（日志 debug 提示），日常规模远小于该值。
_PENDING_PAIR_CAP = 60000

_NAME_MAP_V2_COLUMNS = (
    ("server_id", "TEXT DEFAULT ''"),
    ("emby_person_id", "TEXT DEFAULT ''"),
    ("name_current", "TEXT DEFAULT ''"),
    ("person_type", "TEXT DEFAULT ''"),
    ("person_types", "TEXT DEFAULT ''"),
    ("translation_status", "TEXT DEFAULT ''"),
    ("sync_status", "TEXT DEFAULT ''"),
    ("last_sync_at", "TEXT DEFAULT ''"),
    ("sync_error", "TEXT DEFAULT ''"),
)

_WRITEBACK_V3_COLUMNS = (
    ("file_sig", "TEXT DEFAULT ''"),
    ("attempts", "INTEGER DEFAULT 0"),
)

# v4.6.72（批次3）：person 稳定媒体身份列（旧库无损补列）。
_PERSON_V12_COLUMNS = (
    ("media_provider", "TEXT DEFAULT ''"),
    ("media_id", "TEXT DEFAULT ''"),
    ("series_media_id", "TEXT DEFAULT ''"),
    ("file_fingerprint", "TEXT DEFAULT ''"),
)

_NAME_MAP_V5_COLUMNS = (
    ("legacy_identity", "INTEGER DEFAULT 0"),
    ("pool_sync_state", "TEXT DEFAULT 'active'"),
    ("pool_miss_count", "INTEGER DEFAULT 0"),
)

_WRITEBACK_V6_COLUMNS = (
    ("target_scope", "TEXT DEFAULT ''"),
)


def _merge_scope(a: str, b: str) -> str:
    """合并写回候选的任务范围（person/role/both）—— 多次登记取并集语义：
    范围相同取自身；一个为空（旧记录/未知）取另一个；person+role 不同 → both。
    空串=未知（就绪判定回退到当前任务范围，兼容旧记录）。"""
    _a = str(a or "").strip().lower()
    _b = str(b or "").strip().lower()
    if _a not in ("person", "role", "both"):
        _a = ""
    if _b not in ("person", "role", "both"):
        _b = ""
    if not _a:
        return _b
    if not _b or _a == _b:
        return _a
    return "both"

_conn: Optional[sqlite3.Connection] = None
_conn_lock = threading.RLock()


def _cleanup_stale_wal() -> bool:
    """清理 WAL 残留（自愈）—— 仅在 -wal 为 0 字节时执行（确无未落盘事务，不会丢数据）。

    背景：WAL 模式依赖 -shm 共享内存；当 data.db 被另一台主机经 SMB/NAS 打开过
    （例如用外面的工具连过同一个库），-shm 可能被删/失效，此后本进程 read 直接
    "disk I/O error"。此时若 -wal 是 0 字节（没有待恢复事务），删掉 -wal/-shm 残留
    让 SQLite 重建即可恢复。非 0 字节一律不动（可能有未 checkpoint 的数据），
    只打日志提示用户在停用插件后手动处理。
    """
    try:
        path = db_path()
        fwal = path + "-wal"
        if not os.path.exists(fwal):
            return False
        try:
            _sz = os.path.getsize(fwal)
        except OSError:
            _sz = -1
        if _sz != 0:
            logger.warning(f"[DB] WAL 残留 {fwal} 非空（{_sz} 字节），不自动清理以免丢数据；"
                           f"请停用插件后手动删除 -wal/-shm 再启动")
            return False
        _removed = []
        for _f in (fwal, path + "-shm"):
            try:
                if os.path.exists(_f):
                    os.remove(_f)
                    _removed.append(os.path.basename(_f))
            except OSError as e:
                logger.warning(f"[DB] 清理 {_f} 失败: {e}")
        if _removed:
            logger.warning(f"[DB] 已清理 0 字节 WAL 残留（{'、'.join(_removed)}），重新建立连接")
        return bool(_removed)
    except Exception:
        return False


def _open_conn() -> sqlite3.Connection:
    """建立连接（WAL 不可用时回退 DELETE 日志模式）。"""
    path = db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.DatabaseError as e:
        logger.warning(f"[DB] WAL 模式不可用（{e}），回退 DELETE 日志模式")
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA synchronous=FULL")
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def _get_conn() -> sqlite3.Connection:
    global _conn
    with _conn_lock:
        if _conn is not None:
            return _conn
        last: Optional[BaseException] = None
        for _attempt in range(3):
            try:
                _conn = _open_conn()
                return _conn
            except sqlite3.DatabaseError as e:
                last = e
                _conn = None
                _m = str(e).lower()
                if ("disk i/o error" in _m) or ("unable to open database file" in _m):
                    if not _cleanup_stale_wal():
                        break
                else:
                    break
                time.sleep(0.5 * (_attempt + 1))
        raise last if last is not None else sqlite3.OperationalError("数据库连接失败")


def _drop_conn() -> None:
    """丢弃缓存连接（下次访问重建）—— 连接中途失效（如 WAL 被外部清掉）时用。"""
    global _conn
    try:
        if _conn is not None:
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None
    except Exception:
        _conn = None


def _q(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """查询（自动建连，返回 dict 列表）。v4.3.3: 连接失效时重建并重试一次。"""
    with _conn_lock:
        for _attempt in range(2):
            try:
                cur = _get_conn().execute(sql, params)
                rows = [dict(r) for r in cur.fetchall()]
                cur.close()
                return rows
            except sqlite3.DatabaseError as e:
                _m = str(e).lower()
                if _attempt == 0 and (("disk i/o error" in _m) or ("malformed" in _m)):
                    logger.warning(f"[DB] 查询失败（{e}），重建连接后重试")
                    _drop_conn()
                    continue
                raise


def _q1(sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    rows = _q(sql, params)
    return rows[0] if rows else None


def _x(sql: str, params: tuple = ()) -> int:
    """执行写操作并提交，返回影响行数。v4.3.3: 连接失效时重建并重试一次。"""
    with _conn_lock:
        for _attempt in range(2):
            try:
                conn = _get_conn()
                cur = conn.execute(sql, params)
                conn.commit()
                # v4.6.104（LIB-009）：只认影响库列表的写入（person 表）
                if "person" in sql.lower():
                    _bump_rev()
                n = cur.rowcount if cur.rowcount is not None else 0
                cur.close()
                return n
            except sqlite3.DatabaseError as e:
                _m = str(e).lower()
                if _attempt == 0 and (("disk i/o error" in _m) or ("malformed" in _m)):
                    logger.warning(f"[DB] 写操作失败（{e}），重建连接后重试")
                    _drop_conn()
                    continue
                raise


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ── v4.6.104（LIB-009）：库数据版本号 ──
# 库页左侧列表按「有变化才重拉」驱动：前端 8s 轮询 /status，只有本版本号变了才去拉 /db/items。
# 只在**真正影响列表的写入**（person 表）时自增 —— 翻译任务/批次等簿记写入不参与，避免刷屏。
_REV = [0]


def _bump_rev() -> None:
    _REV[0] += 1


def db_rev() -> int:
    """进程内单调自增的库数据版本号（插件 reload 后归零，前端只做「不等即变化」比较）。"""
    return int(_REV[0])



def get_meta(key: str, default: str = "") -> str:
    try:
        r = _q1("SELECT value FROM meta WHERE key=?", (str(key),))
        return str((r or {}).get("value") or default)
    except Exception:
        return default


def set_meta(key: str, value: str) -> bool:
    try:
        _x("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (str(key), str(value)))
        return True
    except Exception as e:
        logger.warning(f"[DB] 写 meta 失败 {key}: {e}")
        return False


def _table_columns(table: str) -> set:
    try:
        return {str(r.get("name") or "") for r in _q(f"PRAGMA table_info({table})")}
    except Exception:
        return set()


def _ensure_columns(table: str, cols) -> None:
    """幂等补列（先查 PRAGMA，再 ALTER）—— 旧库升级专用。"""
    have = _table_columns(table)
    for _name, _ddl in cols:
        if _name in have:
            continue
        _x(f"ALTER TABLE {table} ADD COLUMN {_name} {_ddl}")
        logger.info(f"[DB] 迁移：{table} 补列 {_name}")


_IDENTITY_SRC_PRIORITY = {"manual": 3, "tmdb": 2, "llm": 1, "zhconv": 0}


def _identity_src_rank(source: str) -> int:
    """源优先级评分（manual=3 / tmdb=2 / llm=1 / 其它=0）。"""
    return _IDENTITY_SRC_PRIORITY.get(str(source or "").strip().lower(), 0)


def _merge_person_types(rows: list) -> str:
    """合并多行的 person_types（JSON 数组 / 逗号串）为一个去重 JSON 数组字符串。"""
    seen: list = []
    for r in rows:
        raw = r.get("person_types")
        vals: list = []
        if isinstance(raw, (list, tuple)):
            vals = list(raw)
        elif raw is not None and str(raw).strip():
            s = str(raw).strip()
            if s.startswith("["):
                try:
                    vals = list(json.loads(s))
                except Exception:
                    vals = [x for x in s.strip("[]").split(",")]
            else:
                vals = [x for x in s.split(",")]
        for v in vals:
            vv = str(v or "").strip().strip('"').strip("'")
            if vv and vv not in seen:
                seen.append(vv)
    return json.dumps(seen, ensure_ascii=False) if seen else ""


def _dedupe_name_map_identity() -> int:
    """建唯一索引前，把同一 Person 身份
    (plugin_id, name_type, server_id, emby_person_id 且 id 非空) 的重复行合并为一行。
    合并规则（文档 §五）：源优先级 manual>llm>zhconv 定保留行；保留最新 name_current；
    person_types 取并集；name_zh 缺失时从其它行补（不丢译文）；保留较新的 last_sync_at
    与合理的 sync_error。其余重复行删除。emby_person_id 为空的行是旧缓存，不动。
    :return: 删除的重复行数
    """
    try:
        rows = _q("SELECT * FROM name_map WHERE emby_person_id IS NOT NULL AND emby_person_id<>'' "
                  "ORDER BY id")
    except Exception as e:
        logger.warning(f"[DB] P0-3 身份去重读取失败: {e}")
        return 0
    groups: Dict[tuple, list] = {}
    for r in rows:
        key = (str(r.get("plugin_id") or ""), str(r.get("name_type") or ""),
               str(r.get("server_id") or ""), str(r.get("emby_person_id") or ""))
        groups.setdefault(key, []).append(r)
    removed = 0
    for _key, grp in groups.items():
        if len(grp) < 2:
            continue
        # 保留行：源优先级最高 → updated_at 最新 → id 最大
        grp_sorted = sorted(
            grp,
            key=lambda x: (_identity_src_rank(x.get("source")),
                           str(x.get("updated_at") or ""),
                           int(x.get("id") or 0)),
            reverse=True,
        )
        keep = grp_sorted[0]
        keep_id = int(keep.get("id") or 0)

        def _first_nonempty(field: str):
            for r in grp_sorted:
                v = r.get(field)
                if v is not None and str(v).strip():
                    return v
            return ""

        # name_current：取 updated_at 最新且非空的值（文档：保留最新 name_current）
        name_current = ""
        for r in sorted(grp,
                        key=lambda x: (str(x.get("updated_at") or ""), int(x.get("id") or 0)),
                        reverse=True):
            if str(r.get("name_current") or "").strip():
                name_current = str(r.get("name_current") or "")
                break
        if not name_current:
            name_current = str(_first_nonempty("name_current") or "")

        # name_zh：保留行若为空，从其它行补一份（人工优先），不丢译文
        name_zh = str(keep.get("name_zh") or "").strip()
        source = str(keep.get("source") or "")
        if not name_zh:
            for r in grp_sorted:
                if str(r.get("name_zh") or "").strip():
                    name_zh = str(r.get("name_zh") or "").strip()
                    source = str(r.get("source") or source)
                    break

        person_types = _merge_person_types(grp_sorted)
        person_type = str(_first_nonempty("person_type") or "")
        translation_status = str(_first_nonempty("translation_status") or "")
        sync_status = str(_first_nonempty("sync_status") or "")
        last_sync_at = max([str(r.get("last_sync_at") or "") for r in grp] or [""])
        sync_error = str(_first_nonempty("sync_error") or "")
        name_original = str(_first_nonempty("name_original") or keep.get("name_original") or "")
        updated_at = (max([str(r.get("updated_at") or "") for r in grp] or [""])
                      or str(keep.get("updated_at") or "") or _now())
        try:
            _x("UPDATE name_map SET name_original=?, name_zh=?, source=?, name_current=?, "
               "person_type=?, person_types=?, translation_status=?, sync_status=?, "
               "last_sync_at=?, sync_error=?, updated_at=? WHERE id=?",
               (name_original, name_zh, source, name_current, person_type, person_types,
                translation_status, sync_status, last_sync_at, sync_error, updated_at, keep_id))
        except Exception as e:
            logger.warning(f"[DB] P0-3 身份去重合并失败 id={keep_id}: {e}")
            continue
        for r in grp:
            did = int(r.get("id") or 0)
            if did == keep_id:
                continue
            try:
                _x("DELETE FROM name_map WHERE id=?", (did,))
                removed += 1
            except Exception as e:
                logger.warning(f"[DB] P0-3 身份去重删除失败 id={did}: {e}")
    if removed:
        logger.info(f"[DB] P0-3 身份去重：合并删除 {removed} 条重复 Person 行")
    return removed


def _dedupe_writeback_identity() -> int:
    """建唯一索引前，把同一 (plugin_id, server_id, item_id) 的重复写回行去重，
    仅保留 id 最大的一行（最新状态）。旧库理论上无重复，此处兜底（防历史并发登记残留）。
    :return: 删除的重复行数
    """
    try:
        rows = _q("SELECT plugin_id, server_id, item_id, MAX(id) AS keep_id, COUNT(*) AS c "
                  "FROM writeback_state GROUP BY plugin_id, server_id, item_id HAVING c>1")
    except Exception as e:
        logger.warning(f"[DB] P1-D 写回去重读取失败: {e}")
        return 0
    removed = 0
    for r in rows:
        try:
            removed += _x("DELETE FROM writeback_state "
                          "WHERE plugin_id=? AND server_id=? AND item_id=? AND id<?",
                          (str(r.get("plugin_id") or ""), str(r.get("server_id") or ""),
                           str(r.get("item_id") or ""), int(r.get("keep_id") or 0)))
        except Exception as e:
            logger.warning(f"[DB] P1-D 写回去重删除失败 keep_id={r.get('keep_id')}: {e}")
    if removed:
        logger.info(f"[DB] P1-D 写回状态去重：删除 {removed} 条重复行")
    return removed


def migrate() -> int:
    """版本化迁移（幂等，可重复执行）—— 旧 data.db 无损升级到 SCHEMA_VERSION。
    任一步失败不写新版本号（下次启动重试），绝不删表/清数据。
    :return: 迁移完成后的版本号（失败返回当前版本；无法连接返回 -1）
    """
    try:
        _get_conn()
    except Exception as e:
        logger.warning(f"[DB] 迁移失败（连接不可用）: {e}")
        return -1
    try:
        cur_v = int(get_meta("schema_version", "0") or 0)
    except Exception:
        cur_v = 0
    # 0 / 空 视为「早期库」—— 与 v1 同等对待（只补列，不动数据）
    if cur_v >= SCHEMA_VERSION:
        return cur_v
    try:
        if cur_v < 2:
            _ensure_columns("name_map", _NAME_MAP_V2_COLUMNS)
            _x("CREATE INDEX IF NOT EXISTS idx_name_map_person "
               "ON name_map (plugin_id, server_id, emby_person_id)")
            _x("CREATE INDEX IF NOT EXISTS idx_name_map_orig "
               "ON name_map (plugin_id, server_id, name_original)")
        if cur_v < 3:
            _ensure_columns("writeback_state", _WRITEBACK_V3_COLUMNS)
        if cur_v < 4:
            _dedupe_name_map_identity()
            _x("CREATE UNIQUE INDEX IF NOT EXISTS idx_name_map_identity "
               "ON name_map (plugin_id, name_type, server_id, emby_person_id) "
               "WHERE emby_person_id IS NOT NULL AND emby_person_id<>''")
        if cur_v < 5:
            _ensure_columns("name_map", _NAME_MAP_V5_COLUMNS)
        if cur_v < 6:
            _ensure_columns("writeback_state", _WRITEBACK_V6_COLUMNS)
        if cur_v < 7:
            _dedupe_writeback_identity()
            # 旧库可能残留 P1-D 之前建的普通索引 idx_writeback_item（非唯一）—— 删除后用唯一索引替代。
            try:
                _x("DROP INDEX IF EXISTS idx_writeback_item")
            except Exception:
                pass
            _x("CREATE UNIQUE INDEX IF NOT EXISTS idx_writeback_identity "
               "ON writeback_state (plugin_id, server_id, item_id)")
        if cur_v < 8:
            # v4.6.61（P1-6）：翻译任务持久化表 —— 连接期 _SCHEMA 已建表，此处兜底（幂等）。
            _x("CREATE TABLE IF NOT EXISTS translate_jobs ("
               "id TEXT PRIMARY KEY, plugin_id TEXT DEFAULT '', job_type TEXT DEFAULT '', "
               "source TEXT DEFAULT '', scope TEXT DEFAULT '', status TEXT DEFAULT 'queued', "
               "batch_mode TEXT DEFAULT '', batch_size INTEGER DEFAULT 0, item_count INTEGER DEFAULT 0, "
               "term_count INTEGER DEFAULT 0, translated_count INTEGER DEFAULT 0, failed_count INTEGER DEFAULT 0, "
               "llm_request_count INTEGER DEFAULT 0, rate_limit_count INTEGER DEFAULT 0, "
               "quota_error_count INTEGER DEFAULT 0, remaining_count INTEGER DEFAULT 0, "
               "writeback_pending_count INTEGER DEFAULT 0, created_at TEXT DEFAULT '', started_at TEXT DEFAULT '', "
               "finished_at TEXT DEFAULT '', next_retry_at TEXT DEFAULT '', error_message TEXT DEFAULT '', "
               "payload TEXT DEFAULT '')")
            _x("CREATE INDEX IF NOT EXISTS idx_tjobs_status "
               "ON translate_jobs (plugin_id, status, created_at)")
        if cur_v < 9:
            # v4.6.62（第 24 节）：翻译 Job 逐词条 / 逐批次明细表 —— 连接期 _SCHEMA 已建表，此处兜底（幂等）。
            _x("CREATE TABLE IF NOT EXISTS translate_job_terms ("
               "id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT DEFAULT '', plugin_id TEXT DEFAULT '', "
               "term_id TEXT DEFAULT '', item_id TEXT DEFAULT '', server_id TEXT DEFAULT '', "
               "season_num INTEGER, episode_num INTEGER, person_index INTEGER DEFAULT 0, "
               "kind TEXT DEFAULT '', person_type TEXT DEFAULT '', original_text TEXT DEFAULT '', "
               "status TEXT DEFAULT 'pending', translation TEXT DEFAULT '', claimed_at TEXT DEFAULT '', "
               "translated_at TEXT DEFAULT '', error_message TEXT DEFAULT '', retry_count INTEGER DEFAULT 0)")
            _x("CREATE INDEX IF NOT EXISTS idx_tjob_terms "
               "ON translate_job_terms (plugin_id, job_id, status)")
            _x("CREATE TABLE IF NOT EXISTS translate_job_batches ("
               "id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT DEFAULT '', plugin_id TEXT DEFAULT '', "
               "batch_id INTEGER DEFAULT 0, status TEXT DEFAULT '', request_no INTEGER DEFAULT 0, "
               "term_count INTEGER DEFAULT 0, returned_count INTEGER DEFAULT 0, attempt_count INTEGER DEFAULT 0, "
               "http_status INTEGER DEFAULT 0, error_kind TEXT DEFAULT '', input_tokens INTEGER DEFAULT 0, "
               "output_tokens INTEGER DEFAULT 0, started_at TEXT DEFAULT '', finished_at TEXT DEFAULT '')")
            _x("CREATE INDEX IF NOT EXISTS idx_tjob_batches "
               "ON translate_job_batches (plugin_id, job_id, batch_id)")
        if cur_v < 10:
            # v4.6.66（P0-2）：person 补 emby_item_id 列 —— Emby ItemId 与媒体 item_id 分离保存。
            # 旧库无损：新列默认空（老数据补不了 Emby ID，重扫/重新入库时自动补上）。
            _ensure_columns("person", [("emby_item_id", "TEXT DEFAULT ''")])
        if cur_v < 11:
            # v4.6.70：同剧角色翻译记忆表 —— 连接期 _SCHEMA 已建表，此处兜底（幂等）。
            # 旧库无损（新表从空开始，随翻译逐步积累）。
            _x("CREATE TABLE IF NOT EXISTS role_memory ("
               "plugin_id TEXT NOT NULL DEFAULT '', server_id TEXT NOT NULL DEFAULT '', "
               "series_id TEXT NOT NULL DEFAULT '', series_name TEXT DEFAULT '', "
               "role_original TEXT NOT NULL, role_translated TEXT DEFAULT '', "
               "source TEXT DEFAULT 'llm', updated_at TEXT DEFAULT '', "
               "PRIMARY KEY (plugin_id, server_id, series_id, role_original))")
            _x("CREATE INDEX IF NOT EXISTS idx_role_mem_name "
               "ON role_memory (plugin_id, server_id, series_name, role_original)")
        if cur_v < 12:
            # v4.6.72（批次3 · 洗版稳定身份）：person 补稳定媒体身份列 + 建历史别名表。
            # 旧库无损：新列默认空，重扫/重新入库时自动补上 provider / series_media_id。
            _ensure_columns("person", _PERSON_V12_COLUMNS)
            _x("CREATE INDEX IF NOT EXISTS idx_person_media "
               "ON person (plugin_id, COALESCE(server_id,''), media_provider, media_id)")
            _x("CREATE INDEX IF NOT EXISTS idx_person_series_media "
               "ON person (plugin_id, COALESCE(server_id,''), series_media_id)")
            _x("CREATE TABLE IF NOT EXISTS media_identity_alias ("
               "id INTEGER PRIMARY KEY AUTOINCREMENT, plugin_id TEXT DEFAULT '', server_id TEXT DEFAULT '', "
               "provider TEXT DEFAULT '', provider_id TEXT DEFAULT '', old_media_id TEXT DEFAULT '', "
               "old_emby_item_id TEXT DEFAULT '', old_nfo_path TEXT DEFAULT '', old_title TEXT DEFAULT '', "
               "new_media_id TEXT DEFAULT '', first_seen TEXT DEFAULT '', last_seen TEXT DEFAULT '')")
            _x("CREATE INDEX IF NOT EXISTS idx_media_alias "
               "ON media_identity_alias (plugin_id, server_id, provider, provider_id)")
            _x("CREATE INDEX IF NOT EXISTS idx_media_alias_old "
               "ON media_identity_alias (plugin_id, old_media_id)")
    except Exception as e:
        logger.error(f"[DB] 迁移 v{cur_v} → v{SCHEMA_VERSION} 失败（版本号未更新，下次启动重试）: {e}")
        return cur_v
    set_meta("schema_version", str(SCHEMA_VERSION))
    logger.info(f"[DB] schema 迁移完成：v{cur_v} → v{SCHEMA_VERSION}")
    return SCHEMA_VERSION


_NP_SQL = "lower(replace(nfo_path, '\\', '/'))"


def _npath(p: str) -> str:
    """路径归一化（比较用）—— Windows/macOS/SMB 大小写差异不再漏判。"""
    return str(p or "").replace("\\", "/").lower()


def split_media_id(item_id: str) -> tuple:
    """把媒体身份 item_id 拆成 (provider, id)（v4.6.72 · 洗版稳定身份）。

    "tvdb:123" → ("tvdb", "123")；"imdb:tt123" → ("imdb", "tt123")；
    "nfo:abcd" → ("nfo", "abcd")；纯数字 → ("tmdb", "<数字>"，与 _item_id_from_dir_name
    的约定一致——裸 tmdbid 直接作 item_id)；其它含前缀视为 (prefix, 原值)；空 → ("", "")。
    """
    s = str(item_id or "").strip()
    if not s:
        return "", ""
    if ":" in s:
        p, _, v = s.partition(":")
        return p.lower(), v
    if s.isdigit():
        return "tmdb", s
    return "", s


def _media_strong_sql(*, item_id: str = "", media_provider: str = "", media_id: str = "",
                      series_media_id: str = "", emby_item_id: str = "",
                      season_num=None, episode_num=None) -> tuple:
    """构造「稳定媒体身份」强匹配 OR 片段 + 参数（v4.6.72 · 洗版恢复）。

    条件（任一命中）：
      emby_item_id=  （Emby 条目唯一 ID，仅「ID 未变」时命中）
      item_id=       + 季/集
      (provider,media_id) + 季/集
      series_media_id= + 季/集
    序列级身份（item_id / provider / series_media_id）在给出季/集时一并要求季集吻合，
    避免「一集恢复误命中同剧其它集」。
    :return: (sql_fragment, params)；片段以 " AND " 起头，无有效条件返回 ("", [])。
    """
    _ep = ""
    _epa: list = []
    if season_num is not None:
        _ep += " AND season_num IS ?"
        _epa.append(season_num)
    if episode_num is not None:
        _ep += " AND episode_num IS ?"
        _epa.append(episode_num)
    conds: list = []
    args: list = []
    if emby_item_id:
        conds.append("emby_item_id=?")
        args.append(str(emby_item_id))
    if item_id:
        conds.append("(item_id=?" + _ep + ")")
        args += [str(item_id)] + list(_epa)
    if media_provider and media_id:
        conds.append("(media_provider=? AND media_id=?" + _ep + ")")
        args += [str(media_provider), str(media_id)] + list(_epa)
    if series_media_id:
        conds.append("(series_media_id=?" + _ep + ")")
        args += [str(series_media_id)] + list(_epa)
    if not conds:
        return "", []
    return " AND (" + " OR ".join(conds) + ")", args


def _weak_sql(*, series_name: str = "", title: str = "", season_num=None,
              episode_num=None) -> tuple:
    """构造「弱匹配」片段（剧名 + 季集 / 标题）—— 仅用于候选计数与「唯一候选」清观察期。"""
    _ep = ""
    _epa: list = []
    if season_num is not None:
        _ep += " AND season_num IS ?"
        _epa.append(season_num)
    if episode_num is not None:
        _ep += " AND episode_num IS ?"
        _epa.append(episode_num)
    conds: list = []
    args: list = []
    if series_name:
        conds.append("(series_name=?" + _ep + ")")
        args += [str(series_name)] + list(_epa)
    if title and not series_name:
        conds.append("(title=?)")
        args.append(str(title))
    if not conds:
        return "", []
    return " OR ".join(conds), args


def _scope_sql(server_id: Optional[str]) -> tuple:
    """来源作用域 SQL 片段 + 参数（DB-001：媒体身份必须带 source scope）。

    None → 不限定来源（旧行为，仅供显式「跨来源」调用）；
    ""   → 仅本地 NFO 记录（server_id 为空）；
    其他 → 仅该 Emby 服务器。
    :return: (sql_fragment, params)；片段以 " AND " 起头，拼在已有 WHERE 条件之后。
    """
    if server_id is None:
        return "", []
    _s = str(server_id)
    if not _s:
        return " AND (server_id='' OR server_id IS NULL)", []
    return " AND server_id=?", [_s]


def _scope_sql_soft(server_id: Optional[str], include_legacy: bool = True) -> tuple:
    """「软」来源作用域（v4.6.67）：显式服务器时**同时纳入旧版遗留空来源行**。

    与 _scope_sql 的区别：指定 server_id=S1 时返回
    ` AND (server_id=? OR server_id IS NULL OR server_id='')` ——
    既隔离掉其它服务器（S2 不被误伤），又不漏掉升级前的遗留行（server_id=''）。
    用于「按 nfo_path / 剧名+季集 标记或解除观察期」等需要覆盖遗留数据的写入路径。
    None → 不限定来源（旧行为）；"" 与 _scope_sql 一致（仅空来源）。

    v4.6.99（P1-02 D）：新增 `include_legacy` —— **多服务器环境**下，空来源（legacy）行
    属于「原归属不明」的数据，不能被任意一台服务器的事件自动认领/修改。
    此时调用方应传 `include_legacy=False`（严格只命中 `server_id=?`），
    空来源行交由人工确认。单服务器环境保留 True（归属唯一可确定）。
    """
    if server_id is None:
        return "", []
    _s = str(server_id)
    if not _s:
        return " AND (server_id='' OR server_id IS NULL)", []
    if include_legacy:
        return " AND (server_id=? OR server_id IS NULL OR server_id='')", [_s]
    return " AND server_id=?", [_s]


_ALIVE_SQL = " AND (deleted_at='' OR deleted_at IS NULL)"


def _require_scope(server_id: Optional[str], fn: str, allow_unscoped: bool = False) -> bool:
    """v4.6.98（P1-02 E）：**写入 / 删除类**操作必须显式限定来源。

    `server_id=None` 表示「不限定来源」= 全表范围 —— 只允许明确知情且安全的调用方
    （例：本地维护线程判定「同一本地文件系统里该路径已消失」，对所有来源都成立）
    显式传 `allow_unscoped=True` 放行；其余调用一律拒绝并告警，
    避免调用方漏传 server_id 造成跨服务器误标（多台 Emby 同路径/同 Id 场景）。
    """
    if server_id is not None or allow_unscoped:
        return True
    logger.warning(f"[DB] {fn} 拒绝执行：未限定 server scope（server_id=None）—— "
                   f"如需跨来源请显式传 allow_unscoped=True")
    return False


def _excl_ep_sql(exclude_episodes: bool) -> str:
    """翻译口径门禁（v4.6.68 + v4.6.77）—— 待翻查询统一走本片段，保证各入口一致。

    ① 「处理单集」= 关 → 追加 ` AND COALESCE(item_type,'')<>'Episode'`：
       Episode 层级行仍可入库（供「库」页查看/编辑），但不进入待翻/预估/worker 收词/
       写回就绪判定，从而「不参与翻译、不调 AI」。
    ② v4.6.77：**观察期行（deleted_at 非空）一律不参与翻译口径** —— 被删条目/剧集的
       文件已不存在，其未翻译词条不应再被统计为待翻、更不该拿去调 AI（纯浪费配额）。
       译文本身不清除：观察期内重新入库（deleted_at 清空）后自动回到待翻队列；
       人工在观察期内的修改也照常保留（恢复时按序号/原文继承）。
    """
    _ep = " AND COALESCE(item_type,'')<>'Episode'" if exclude_episodes else ""
    return _ep + _ALIVE_SQL


def _group_person_rows(rows: list) -> list:
    """把 person 行按 (server_id, item_id) 归组为库列表条目。
    library_items（全表）与 library_items_page（分页）共用同一实现，保证字段语义一致。
    返回顺序 = 行的「首次出现」顺序（即 rows 的行序）；排序由调用方负责。"""
    grouped: dict = {}
    for r in rows:
        item_id = str(r.get("item_id") or "")
        # 分组键含来源（DB-001）：混合库下同 item_id 的不同来源不再被并成一格 ——
        # 否则「先出现的来源」会代表整组，按模式过滤时会把另一来源的条目整条漏掉。
        _src = str(r.get("server_id") or "")
        info = grouped.setdefault((_src, item_id), {
            "item_id": item_id,
            "item_type": r.get("item_type") or "",
            "title": r.get("title") or r.get("series_name") or item_id,
            "series_name": r.get("series_name") or "",
            "season_num": r.get("season_num"),
            "episode_num": r.get("episode_num"),
            "person_count": 0,
            "updated_at": r.get("translated_at") or "",
            "server_id": r.get("server_id") or "",
            "library_name": r.get("library_name") or "",
            "nfo_dir": "",
            "deleted_at": str(r.get("deleted_at") or ""),
            "deleted_rows": 0,
            "deleted_eps": 0,
            "_dep_set": set(),
        })
        if not info.get("nfo_dir"):
            _np = str(r.get("nfo_path") or "")
            if _np:
                info["nfo_dir"] = _np.replace("\\", "/").rsplit("/", 1)[0]
        # 集记录复用剧的 item_id —— 组内类型优先取剧/电影，避免整组被当集过滤
        if info["item_type"] == "Episode" and r.get("item_type") != "Episode":
            info["item_type"] = r.get("item_type") or ""
            if r.get("title"):
                info["title"] = r.get("title") or ""
        info["person_count"] += 1
        if str(r.get("deleted_at") or ""):
            info["deleted_rows"] += 1
            if r.get("season_num") is not None or r.get("episode_num") is not None:
                info["_dep_set"].add((r.get("season_num"), r.get("episode_num")))
        t = r.get("translated_at") or ""
        if t and t > info["updated_at"]:
            info["updated_at"] = t
    for _info in grouped.values():
        _info["deleted_eps"] = len(_info.pop("_dep_set", None) or ())
    return list(grouped.values())


def _scan_scope_sql(scan_mode: Optional[str]) -> str:
    """scan_mode → 来源过滤 SQL 片段（与 library_items 内联片段保持一致）。

    v4.6.66（P0-6 关键修复）：判定依据由「server_id 是否为空」改为「是否有本地 nfo_path」——
    Webhook 入库现在携带**真实 server_id**（P0-1），旧判据（nfo 模式只看 server_id=''）
    会让所有新入库条目在库页整批消失（用户实测：日志显示 3 个 NFO 入库成功、库页找不到）。
    NFO 工作流的记录必有 nfo_path（server_id 只是来源标识，不代表模式）；纯 API 老记录无 nfo_path。
    """
    if scan_mode == "nfo":
        return " AND nfo_path IS NOT NULL AND nfo_path<>''"
    if scan_mode == "api":
        return " AND (nfo_path IS NULL OR nfo_path='')"
    return ""


# v4.6.95：条目「显示名」聚合口径 —— 同一 item_id 下剧级行（非 Episode）title = 剧名、
# 各集行 title = 集名；旧写法 MAX(title) 是「按字符序取最大」，剧名与各集名混排时会误取集名
# （实测《某剧》在「待翻译明细」里显示成某一集名「转学生来了」）。
# 优先级：剧级行 title → series_name（剧名）→ 最后才退到 MAX(title)。
_SQL_ITEM_TITLE = ("COALESCE(MAX(CASE WHEN COALESCE(item_type,'')<>'Episode' THEN title END), "
                   "MAX(NULLIF(series_name,'')), MAX(title))")


# ---------------- 翻译记录（person） ----------------

class PeopleDb:
    """演职人员翻译记录 数据访问（独立 SQLite）。"""

    @staticmethod
    def ensure_table() -> None:
        """只初始化独立库 data.db（建表）；插件不接触 MP 主库，无任何迁移/清理。
        建表后跑版本化迁移（meta.schema_version，幂等），旧库无损升级。"""
        try:
            _get_conn()
            try:
                _x("ALTER TABLE person ADD COLUMN deleted_at TEXT DEFAULT ''")
            except Exception:
                pass  # 列已存在
            migrate()
        except Exception as e:
            logger.warning(f"[DB] 初始化 data.db 失败: {e}")

    # ── 写 ──
    def upsert_people(
        self,
        *,
        plugin_id: str,
        server_id: str,
        item_id: str,
        item_type: str,
        title: str,
        series_name: str = "",
        season_num: Optional[int] = None,
        episode_num: Optional[int] = None,
        library_name: str = "",
        people: List[dict] = None,
        nfo_path: str = "",
        emby_item_id: str = "",
        media_provider: str = "",
        media_id: str = "",
        series_media_id: str = "",
        file_fingerprint: str = "",
        db: Optional[Any] = None,
    ) -> int:
        """把某条目翻译后的 People 整体写入记录表。

        以 (plugin_id, server_id, item_id, season_num, episode_num) 为准先删除旧记录，
        再插入当前 People —— 剧记录与各集记录共用 item_id，靠 season/episode 区分层级。

        v4.6.66（P0-1/P0-3/P0-4）关键行为：
        - **server_id 不再由本层写死** —— 调用方（Webhook/Series 展开/扫描）必须传真实来源；
        - `emby_item_id` 单独保存 Emby ItemId（与媒体 item_id 分离，P0-2）；
        - **恢复/重新入库继承旧译文**：写库前读取旧行，按「person_index → 原文」匹配，
          原文未变且旧译文存在的行直接继承（name_after/role_after + translated_at），
          只有「新增词条 / 原文变化」的行才以原文占位进 pending（删除→恢复不再重翻）；
        - 旧版遗留行（server_id=''）在本次写入时按 nfo_path 迁移到真实 server_id，
          防止升级后同一条目出现「旧行(空来源)+新行(真实来源)」两份。
        :return: 写入行数
        """
        now = _now()
        people = people or []
        try:
            with _conn_lock:
                conn = _get_conn()
                _np = _npath(nfo_path) if nfo_path else ""
                # ── 1) 读旧行（含 server_id='' 的遗留行）→ 恢复继承用 ──
                _old_rows = []
                try:
                    if _np:
                        _old_rows = conn.execute(
                            "SELECT person_index, name_before, name_after, role_before, role_after, "
                            "translated_at FROM person WHERE plugin_id=? AND item_id=? "
                            "AND season_num IS ? AND episode_num IS ? "
                            f"AND (server_id=? OR ((server_id IS NULL OR server_id='') AND {_NP_SQL}=?))",
                            (plugin_id, item_id, season_num, episode_num, server_id, _np)).fetchall()
                    else:
                        _old_rows = conn.execute(
                            "SELECT person_index, name_before, name_after, role_before, role_after, "
                            "translated_at FROM person WHERE plugin_id=? AND item_id=? "
                            "AND season_num IS ? AND episode_num IS ? AND server_id=?",
                            (plugin_id, item_id, season_num, episode_num, server_id)).fetchall()
                except Exception:
                    _old_rows = []
                _by_idx: dict = {}
                _by_name: dict = {}
                for _r in _old_rows:
                    _by_idx[int(_r[0] or 0)] = _r
                    if _r[1]:
                        _by_name.setdefault(str(_r[1]), _r)
                # ── 2) 遗留行来源迁移（server_id='' → 真实 server_id，按 nfo_path 精确定位）──
                # 仅当本次带了真实 server_id + nfo_path 才迁移；扫描等无来源路径不受影响。
                if server_id and _np:
                    try:
                        conn.execute(
                            f"UPDATE person SET server_id=? WHERE plugin_id=? AND item_id=? "
                            f"AND season_num IS ? AND episode_num IS ? "
                            f"AND (server_id IS NULL OR server_id='') AND {_NP_SQL}=?",
                            (server_id, plugin_id, item_id, season_num, episode_num, _np))
                    except Exception:
                        pass
                # ── 3) 解除观察期 + 删旧行（保持既有语义）──
                # v4.6.72：稳定媒体身份（provider 未显式给时从 item_id 兜底拆分）。
                _mp = str(media_provider or "")
                _mid = str(media_id or "")
                if not (_mp and _mid):
                    _mp, _mid = split_media_id(item_id)
                if nfo_path:
                    conn.execute(f"UPDATE person SET deleted_at='' WHERE plugin_id=? AND server_id=? AND item_id=? "
                                 f"AND {_NP_SQL}=?",
                                 (plugin_id, server_id, item_id, _np))
                else:
                    conn.execute("UPDATE person SET deleted_at='' WHERE plugin_id=? AND server_id=? AND item_id=?",
                                 (plugin_id, server_id, item_id))
                if nfo_path:
                    conn.execute(
                        f"DELETE FROM person WHERE plugin_id=? AND server_id=? AND item_id=? "
                        f"AND season_num IS ? AND episode_num IS ? "
                        f"AND ({_NP_SQL}=? OR nfo_path='' OR nfo_path IS NULL)",
                        (plugin_id, server_id, item_id, season_num, episode_num, _np),
                    )
                    # v4.6.72（批次3 · 洗版去重）：provider 身份稳定（非 nfo:hash）时，
                    # 同一 (server, item, 季, 集) 下**旧路径**的残留行一并清理 —— 洗版改了
                    # 路径/文件名后，旧行不会被上面的 nfo_path 条件命中，否则会留下重复行。
                    if server_id and _mp and _mp != "nfo":
                        try:
                            conn.execute(
                                f"DELETE FROM person WHERE plugin_id=? AND server_id=? AND item_id=? "
                                f"AND season_num IS ? AND episode_num IS ? "
                                f"AND nfo_path IS NOT NULL AND nfo_path<>'' AND {_NP_SQL}<>?",
                                (plugin_id, server_id, item_id, season_num, episode_num, _np))
                        except Exception:
                            pass
                else:
                    conn.execute(
                        "DELETE FROM person WHERE plugin_id=? AND server_id=? AND item_id=? AND season_num IS ? AND episode_num IS ?",
                        (plugin_id, server_id, item_id, season_num, episode_num),
                    )
                # ── 4) 插入（含恢复继承）──
                _smi = str(series_media_id or "")
                _fp = str(file_fingerprint or "")
                rows_data = []
                for idx, p in enumerate(people):
                    name_before = str(p.get("before_name") or p.get("Name") or "")
                    role_before = str(p.get("before_role") or p.get("Role") or "")
                    _name_in = str(p.get("Name") or "").strip()
                    _role_in = str(p.get("Role") or "").strip()
                    _t_at = now
                    if _name_in and _name_in != name_before:
                        name_after = _name_in          # 显式新译文（person_map / 人工）
                    else:
                        name_after = name_before
                        _old = _by_idx.get(idx) or _by_name.get(name_before)
                        if _old is not None and str(_old[1] or "") == name_before \
                                and str(_old[2] or "").strip():
                            # 原文未变 + 旧译文存在 → 继承（恢复不重翻，P0-3/P0-4）
                            name_after = str(_old[2]).strip()
                            _t_at = str(_old[5] or "") or now
                    if _role_in and _role_in != role_before:
                        role_after = _role_in
                    else:
                        role_after = role_before
                        _old = _by_idx.get(idx) or _by_name.get(name_before)
                        if _old is not None and str(_old[3] or "") == role_before \
                                and str(_old[4] or "").strip():
                            role_after = str(_old[4]).strip()
                    rows_data.append(
                        (plugin_id, server_id, item_id, item_type, title, series_name,
                         season_num, episode_num, library_name, idx, str(p.get("Type") or "Actor"),
                         name_before, name_after, role_before, role_after, _t_at, nfo_path or "",
                         str(emby_item_id or ""), _mp, _mid, _smi, _fp))
                if rows_data:
                    conn.executemany(
                        "INSERT INTO person (plugin_id, server_id, item_id, item_type, title, series_name, "
                        "season_num, episode_num, library_name, person_index, person_type, name_before, "
                        "name_after, role_before, role_after, translated_at, nfo_path, emby_item_id, "
                        "media_provider, media_id, series_media_id, file_fingerprint) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows_data)
                conn.commit()
                # v4.6.104（LIB-009）：批量写入 person（最常见的写路径）→ 版本号自增
                if rows_data:
                    _bump_rev()
            return len(rows_data)
        except Exception as e:
            try:
                with _conn_lock:
                    _get_conn().rollback()
            except Exception:
                pass
            logger.warning(f"[DB] upsert_people 失败: {e}")
            return 0

    # ── 读：统计（v3.4.59: 纯聚合 SQL，零行加载 —— 万级库下每 5 秒轮询不拖垮宿主）──
    def stats(self, *, plugin_id: str, db: Optional[Any] = None) -> dict:
        """统计排除观察期（deleted_at 非空）行 —— 与库页列表口径一致，
        不再把"已判定即将清理"的条目算进「库中条目」。"""
        try:
            row = _q1(
                "SELECT COUNT(*) AS person_count, "
                "COUNT(DISTINCT item_id) AS item_count, "
                "COALESCE(SUM(CASE WHEN name_after IS NOT NULL AND name_after<>'' "
                "AND name_after<>name_before THEN 1 ELSE 0 END), 0) AS translated_people, "
                "MAX(translated_at) AS last_update "
                "FROM person WHERE plugin_id=? AND (deleted_at='' OR deleted_at IS NULL)",
                (plugin_id,))
        except Exception as e:
            logger.warning(f"[DB] 统计聚合失败: {e}")
            row = {}
        return {
            "person_count": int(row.get("person_count") or 0),
            "item_count": int(row.get("item_count") or 0),
            "translated_people": int(row.get("translated_people") or 0),
            "last_update": row.get("last_update"),
        }

    def episode_counts(self, *, plugin_id: str, item_ids: list,
                       server_id: Optional[str] = "",
                       db: Optional[Any] = None) -> dict:
        """批量取各条目的集数。server_id 见 _scope_sql —— 默认 "" 只统计本地 NFO 来源，
        混合库下不会把其它来源的同 item_id 集记录算进来（DB-001）。"""
        ids = [str(x) for x in (item_ids or []) if str(x)]
        if not ids:
            return {}
        marks = ",".join(["?"] * len(ids))
        _sc, _scp = _scope_sql(server_id)
        try:
            rows = _q(
                f"SELECT item_id, COUNT(DISTINCT COALESCE(season_num,'') || '@' || episode_num) AS c "
                f"FROM person WHERE plugin_id=? AND item_id IN ({marks}) "
                f"AND episode_num IS NOT NULL" + _sc + " GROUP BY item_id",
                [plugin_id, *ids, *_scp])
            return {str(r.get("item_id") or ""): int(r.get("c") or 0) for r in rows if r.get("item_id")}
        except Exception:
            return {}

    # ── 读：库列表（用于库页左侧）──
    def library_items(self, *, plugin_id: str, db: Optional[Any] = None,
                      scan_mode: Optional[str] = None) -> list:
        rows = _q("SELECT * FROM person WHERE plugin_id=?"
                  + _scan_scope_sql(scan_mode) + " ORDER BY id", (plugin_id,))
        result = _group_person_rows(rows)
        result.sort(key=lambda x: x["updated_at"], reverse=True)
        return result

    def library_items_page(self, *, plugin_id: str, scan_mode: Optional[str] = None,
                           limit: int = 200, offset: int = 0,
                           db: Optional[Any] = None) -> tuple:
        """库列表分页（内存修复 v4.6.33）：不再整表 SELECT * 落到 Python。

        做法：SQL 层 GROUP BY (COALESCE(server_id,''), COALESCE(item_id,'')) 聚合出「当前页」
        的分组键（按条目 updated_at=MAX(translated_at) 倒序，与 library_items 的排序一致；
        集类型组在 HAVING 中剔除），再仅取该页条目对应的 person 行做内存分组，
        字段/排序与 library_items 完全一致。分组键归一化与 _group_person_rows 对齐，
        避免 NULL 与 '' 被 SQL 拆成两组、又不被 Python 合并而致的重复项/total 虚高。
        走 idx_person_page 表达式索引，大库下不发全表临时排序。

        返回 (items, total)：items 为当前页条目列表；total 为过滤后的条目总数（供 has_more）。
        limit<=0 时退化为整表（调用方应改用 library_items 的旧路径）。"""
        try:
            _lim = int(limit or 0)
            _off = max(0, int(offset or 0))
        except Exception:
            _lim, _off = 0, 0
        if _lim <= 0:
            # 退化路径与分页路径保持一致：同样剔除「纯 Episode 组」
            # （对应 _annotate_db_items 中 item_type=='Episode' 过滤）。
            _all = self.library_items(plugin_id=plugin_id, scan_mode=scan_mode)
            _all = [it for it in _all if str(it.get("item_type") or "") != "Episode"]
            return _all, len(_all)
        _scope = _scan_scope_sql(scan_mode)
        # 分组键与 _group_person_rows 的归一化逐字对齐（COALESCE 把 NULL 视作 ''）：
        # 否则 SQL 会把 server_id=NULL 与 ='' 当成两个组，归一化后却是同一 key，
        # 导致同一逻辑条目在页内重复出现、total 虚高。
        _grp = " GROUP BY COALESCE(server_id,''), COALESCE(item_id,'')"
        # 组「保留」判定：组内存在任一非 Episode 行（COALESCE 把空类型视作非 Episode，
        # 与 library_items 中 `r.get("item_type") or ""` != "Episode" 的语义一致）。
        _keep = " HAVING MIN(CASE WHEN COALESCE(item_type,'')<>'Episode' THEN id END) IS NOT NULL"
        try:
            _cnt = _q1(
                "SELECT COUNT(*) AS c FROM (SELECT 1 FROM person WHERE plugin_id=?"
                + _scope + _grp + _keep + ")", (plugin_id,))
            total = int((_cnt or {}).get("c") or 0)
            keys = _q(
                "SELECT COALESCE(server_id,'') AS server_id, COALESCE(item_id,'') AS item_id, "
                "MIN(id) AS first_id, COALESCE(MAX(translated_at),'') AS updated_at "
                "FROM person WHERE plugin_id=?" + _scope + _grp
                + _keep + " ORDER BY updated_at DESC, first_id ASC LIMIT ? OFFSET ?",
                (plugin_id, _lim, _off))
            if not keys:
                return [], total
            _ids = [str(k.get("item_id") or "") for k in keys]
            marks = ",".join(["?"] * len(_ids))
            # item_id 归一化后为 '' 的组：其行在库里可能是 item_id='' 或 NULL，
            # IN 匹配不到 NULL，需补 OR item_id IS NULL（有 '' 组时才加，保持常规路径走索引）。
            _in = "item_id IN (" + marks + ")"
            if "" in _ids:
                _in = "(" + _in + " OR item_id IS NULL)"
            rows = _q("SELECT * FROM person WHERE plugin_id=?" + _scope
                      + " AND " + _in + " ORDER BY id",
                      [plugin_id, *_ids])
            _want = [(str(k.get("server_id") or ""), str(k.get("item_id") or "")) for k in keys]
            _want_set = set(_want)
            _grouped = {}
            for _it in _group_person_rows(rows):
                _key = (str(_it.get("server_id") or ""), str(_it.get("item_id") or ""))
                if _key in _want_set:
                    _grouped[_key] = _it
            items = [_grouped[k] for k in _want if k in _grouped]
            return items, total
        except Exception as e:
            logger.warning(f"[DB] library_items_page 失败: {e}")
            return [], 0


    def item_translation_counts(self, *, plugin_id: str, pairs: list,
                                db: Optional[Any] = None) -> dict:
        """按 (server_id, item_id) 统计「总行数 / 已翻行数」（v4.6.66 · 入库通知口径拆分用）。
        已翻 = name_after 非空且与 name_before 不同（与 stats 同口径）；排除观察期行。
        :return: {(server, item): {"total": n, "translated": m}}
        """
        out: dict = {}
        try:
            for _sid, _iid in (pairs or []):
                _iid = str(_iid or "")
                if not _iid:
                    continue
                _sid = str(_sid or "")
                row = _q1(
                    "SELECT COUNT(*) AS total, "
                    "COALESCE(SUM(CASE WHEN name_after IS NOT NULL AND name_after<>'' "
                    "AND name_after<>name_before THEN 1 ELSE 0 END),0) AS translated "
                    "FROM person WHERE plugin_id=? AND item_id=? "
                    "AND (server_id=? OR (server_id IS NULL OR server_id='')) "
                    "AND (deleted_at='' OR deleted_at IS NULL)",
                    (plugin_id, _iid, _sid))
                out[(_sid, _iid)] = {"total": int((row or {}).get("total") or 0),
                                     "translated": int((row or {}).get("translated") or 0)}
        except Exception:
            pass
        return out

    def item_has_series_row(self, *, plugin_id: str, item_id: str,
                            server_id: Optional[str] = "", exclude_deleted: bool = False,
                            db: Optional[Any] = None) -> bool:
        """该条目是否已有「非 Episode」层级行（剧/电影级）。

        v4.6.66（P0-6）：库页会把「纯 Episode 组」整体隐藏（防逐集刷屏）；若一部剧只入库了
        单集 nfo（tvshow.nfo 未就绪 / 路径映射差异），整部剧会从库页消失。本函数用于入库时
        判断要不要补写剧级行。
        v4.6.84（用户实测）：新增 `exclude_deleted` —— 传 True 时**观察期（deleted_at 非空）行
        不算「已有剧级行」**。否则「整部剧被误标观察期」后，剧级行虽然已删却仍算存在 →
        补写被跳过 → 剧级行永远停在观察期、剧名一直显示「待恢复」。
        """
        try:
            _sc, _scp = _scope_sql(server_id)
            _alive = " AND (deleted_at='' OR deleted_at IS NULL)" if exclude_deleted else ""
            r = _q1("SELECT COUNT(*) AS c FROM person WHERE plugin_id=? AND item_id=? "
                    "AND COALESCE(item_type,'')<>'Episode'" + _alive + _sc,
                    (plugin_id, str(item_id or ""), *_scp))
            return bool(int((r or {}).get("c") or 0))
        except Exception:
            return False

    def library_items_lite(self, *, plugin_id: str, limit: int = 800,
                           after_id: int = 0, db: Optional[Any] = None) -> list:
        """维护用：每个条目只取首行（nfo_path/title/series_name），GROUP BY 单查询。
        替代 library_items 的全表行加载 + 内存分组（万级库每小时一轮开销显著）。
        增加 after_id 轮转游标 —— 按 MIN(id) 递增分页，
        配合维护线程的 waterline 循环覆盖整个数据库（此前固定取最新 800 条，
        更早的条目永远不检查）。返回项含 id 供调用方推进游标。
        v4.6.66：分组含来源（server_id）—— 调用方按各自来源标记观察期
        （P0-1 后 Webhook 行带真实 server_id，仅按 '' 标记会漏掉这些行）。"""
        try:
            rows = _q(
                "SELECT item_id, COALESCE(server_id,'') AS server_id, MIN(id) AS id, "
                "MIN(nfo_path) AS nfo_path, MIN(title) AS title, "
                "MIN(series_name) AS series_name FROM person WHERE plugin_id=? "
                "AND (deleted_at='' OR deleted_at IS NULL) AND nfo_path<>'' "
                "GROUP BY COALESCE(server_id,''), COALESCE(item_id,'') "
                "HAVING MIN(id) > ? ORDER BY MIN(id) ASC LIMIT ?",
                (plugin_id, int(after_id or 0), int(limit)))
            out = []
            for r in rows:
                _np = str(r.get("nfo_path") or "").replace("\\", "/")
                out.append({
                    "item_id": str(r.get("item_id") or ""),
                    "server_id": str(r.get("server_id") or ""),
                    "id": int(r.get("id") or 0),
                    "title": str(r.get("title") or r.get("item_id") or ""),
                    "series_name": str(r.get("series_name") or ""),
                    "nfo_dir": _np.rsplit("/", 1)[0] if _np else "",
                    "deleted_at": "",
                })
            return out
        except Exception as e:
            logger.warning(f"[DB] library_items_lite 失败: {e}")
            return []

    def episode_nfo_paths(self, *, plugin_id: str, limit: int = 1500,
                          after_id: int = 0, db: Optional[Any] = None) -> list:
        """未标记记录的 nfo_path，供行级目录消失检查（整季删除但剧根仍在的场景：
        条目级 nfo_dir 检查永远发现不了）。
        增加 after_id 轮转游标 —— 按 id 递增分页返回
        [{id, nfo_path}]，配合维护 waterline 循环覆盖全库（此前固定取最新 1500 条，
        更早文件永不检查）。"""
        try:
            rows = _q("SELECT id, nfo_path FROM person WHERE plugin_id=? "
                      "AND (deleted_at='' OR deleted_at IS NULL) AND nfo_path<>'' "
                      "AND id > ? ORDER BY id ASC LIMIT ?",
                      (plugin_id, int(after_id or 0), int(limit)))
            return [{"id": int(r.get("id") or 0), "nfo_path": str(r.get("nfo_path") or "")}
                    for r in rows]
        except Exception:
            return []

    def item_id_by_nfo_path(self, *, plugin_id: str, nfo_path: str, db: Optional[Any] = None) -> str:
        try:
            r = _q1("SELECT item_id FROM person WHERE plugin_id=? AND nfo_path=? LIMIT 1",
                    (plugin_id, nfo_path or ""))
            return str((r or {}).get("item_id") or (r or {}).get("itemid") or "").strip()
        except Exception:
            return ""

    def migrate_item_id(self, *, plugin_id: str, old: str, new: str, db: Optional[Any] = None) -> int:
        if not old or not new or old == new:
            return 0
        try:
            return _x("UPDATE person SET item_id=? WHERE plugin_id=? AND item_id=?",
                      (new, plugin_id, old))
        except Exception:
            return 0

    def mark_deleted(self, *, plugin_id: str, item_ids: list,
                     deleted_ts: float = None, server_id: Optional[str] = None,
                     db: Optional[Any] = None) -> int:
        """按 item_id 标记观察期。server_id 见 _scope_sql ——
        本地 NFO 流程应传 ""（只作用于本地记录），不再误伤同 item_id 的其它来源记录（DB-001）。"""
        ids = [str(x) for x in (item_ids or []) if str(x)]
        if not ids:
            return 0
        ts = str(deleted_ts if deleted_ts is not None else time.time())
        marks = ",".join(["?"] * len(ids))
        _sc, _scp = _scope_sql(server_id)
        try:
            return _x(
                f"UPDATE person SET deleted_at=? WHERE plugin_id=? AND item_id IN ({marks}) "
                f"AND (deleted_at='' OR deleted_at IS NULL)" + _sc,
                [ts, plugin_id, *ids, *_scp])
        except Exception:
            return 0

    def mark_deleted_by_nfo_path(self, *, plugin_id: str, nfo_path: str,
                                 deleted_ts: float = None,
                                 server_id: Optional[str] = None,
                                 allow_unscoped: bool = False,
                                 include_legacy: bool = True,
                                 db: Optional[Any] = None) -> int:
        """按 nfo_path 行级标记观察期。集记录与剧共用 item_id，不能按 item_id 标记
        （会把整部剧一起标记为失效）；nfo_path 每行唯一，只影响被删的那一集/条目。
        宽限期内同 ID 新版本入库 → upsert_people 的 deleted_at='' 恢复逻辑自动解除。
        比较大小写/分隔符不敏感（Windows/macOS/SMB 路径漏判修复）。

        v4.6.67（P0 删除隔离）：新增 server_id —— Webhook 删除事件必须传来源服务器，
        此前不隔离：两台 Emby 服务器映射到同一 nfo 路径时，A 服删除会把 B 服同路径记录
        一起标记失效（B 服内容明明还在，库里却显示「待恢复」）。语义见 _scope_sql_soft：
        只作用于「该服务器 + 旧版遗留空来源」行，其它服务器不受影响。"""
        if not nfo_path:
            return 0
        if not _require_scope(server_id, "mark_deleted_by_nfo_path", allow_unscoped):
            return 0
        ts = str(deleted_ts if deleted_ts is not None else time.time())
        _sc, _scp = _scope_sql_soft(server_id, include_legacy)
        try:
            return _x(f"UPDATE person SET deleted_at=? WHERE plugin_id=? AND {_NP_SQL}=? "
                      f"AND (deleted_at='' OR deleted_at IS NULL)" + _sc,
                      (ts, plugin_id, _npath(nfo_path), *_scp))
        except Exception:
            return 0

    def mark_deleted_by_episode(self, *, plugin_id: str, item_id: str, season_num: int,
                                episode_num: int, deleted_ts: float = None,
                                server_id: Optional[str] = None,
                                db: Optional[Any] = None) -> int:
        """该剧在 Emby 已没有这一集（服务器删了但可能漏接删除事件）→ 只把这一集标记观察期，
        不波及整剧（剧记录 season/episode 为空，不受影响）。已标记过的不会重复计数。
        server_id 见 _scope_sql（本地 NFO 流程传 ""，不误伤同 item_id 的其它来源记录）。"""
        if not item_id:
            return 0
        ts = str(deleted_ts if deleted_ts is not None else time.time())
        _sc, _scp = _scope_sql(server_id)
        try:
            return _x("UPDATE person SET deleted_at=? WHERE plugin_id=? AND item_id=? "
                      "AND season_num IS ? AND episode_num IS ? "
                      "AND (deleted_at='' OR deleted_at IS NULL)" + _sc,
                      (ts, plugin_id, str(item_id), season_num, episode_num, *_scp))
        except Exception as e:
            logger.warning(f"[DB] mark_deleted_by_episode 失败: {e}")
            return 0

    def mark_deleted_by_nfo_path_prefix(self, *, plugin_id: str, path_prefix: str,
                                        deleted_ts: float = None,
                                        server_id: Optional[str] = None,
                                        allow_unscoped: bool = False,
                                        include_legacy: bool = True,
                                        db: Optional[Any] = None) -> int:
        """目录前缀标记：集记录与剧共用 item_id，整剧删除时逐集 episode.nfo 行
        都要进观察期（此前只标一个猜测文件，几十上百行漏标）。大小写不敏感。

        v4.6.67（P0 删除隔离）：新增 server_id（语义同 mark_deleted_by_nfo_path）——
        Webhook 整剧/整季删除必须传来源服务器；本地维护线程（同一本地文件系统）传 None
        （不限定来源，路径消失对所有来源都成立）。"""
        _p = _npath(path_prefix).rstrip("/")
        if not _p:
            return 0
        if not _require_scope(server_id, "mark_deleted_by_nfo_path_prefix", allow_unscoped):
            return 0
        ts = str(deleted_ts if deleted_ts is not None else time.time())
        _sc, _scp = _scope_sql_soft(server_id, include_legacy)
        try:
            return _x(f"UPDATE person SET deleted_at=? WHERE plugin_id=? "
                      f"AND (deleted_at='' OR deleted_at IS NULL) "
                      f"AND substr({_NP_SQL}, 1, ?) = ?" + _sc,
                      (ts, plugin_id, len(_p) + 1, _p + "/", *_scp))
        except Exception:
            return 0

    def episode_pairs_under_prefix(self, *, plugin_id: str, path_prefix: str,
                                   server_id: Optional[str] = None,
                                   db: Optional[Any] = None) -> list:
        """某目录前缀下、带季集信息的记录 → 去重升序的 [(season, episode), ...]。

        v4.6.85：容器级删除事件但容器**仍在 Emby**（内容变动）时，用它和 Emby 实际的
        集列表做差集，只把真正消失的那几集进观察期（不再整树标记）。"""
        _p = _npath(path_prefix).rstrip("/")
        if not _p:
            return []
        _sc, _scp = _scope_sql_soft(server_id)
        try:
            rows = _q("SELECT DISTINCT season_num, episode_num FROM person WHERE plugin_id=? "
                      "AND season_num IS NOT NULL AND episode_num IS NOT NULL "
                      f"AND substr({_NP_SQL}, 1, ?) = ?" + _sc,
                      (plugin_id, len(_p) + 1, _p + "/", *_scp))
            out = []
            for r in rows:
                try:
                    out.append((int(r.get("season_num")), int(r.get("episode_num"))))
                except Exception:
                    pass
            return sorted(set(out))
        except Exception:
            return []

    def mark_deleted_episodes_by_prefix(self, *, plugin_id: str, path_prefix: str, pairs: list,
                                        deleted_ts: float = None,
                                        server_id: Optional[str] = None,
                                        allow_unscoped: bool = False,
                                        include_legacy: bool = True,
                                        db: Optional[Any] = None) -> int:
        """只把「指定季集」的行标记观察期（限定在给定目录前缀内）。

        v4.6.85：容器仍存在时的**精确标记** —— 只标真正从 Emby 消失的那几集，
        同剧其它集一律不动（与此前「整树标记」相对）。"""
        _p = _npath(path_prefix).rstrip("/")
        try:
            _pairs = [(int(s), int(e)) for (s, e) in (pairs or [])]
        except Exception:
            return 0
        if not _p or not _pairs:
            return 0
        if not _require_scope(server_id, "mark_deleted_episodes_by_prefix", allow_unscoped):
            return 0
        ts = str(deleted_ts if deleted_ts is not None else time.time())
        _ors, _args = [], []
        for _s, _e in _pairs:
            _ors.append("(season_num IS ? AND episode_num IS ?)")
            _args += [_s, _e]
        _sc, _scp = _scope_sql_soft(server_id, include_legacy)
        try:
            return _x("UPDATE person SET deleted_at=? WHERE plugin_id=? "
                      "AND (deleted_at='' OR deleted_at IS NULL) "
                      "AND (" + " OR ".join(_ors) + ") "
                      f"AND substr({_NP_SQL}, 1, ?) = ?" + _sc,
                      (ts, plugin_id, *_args, len(_p) + 1, _p + "/", *_scp))
        except Exception:
            return 0

    def server_id_by_nfo_path(self, *, plugin_id: str, nfo_path: str,
                              db: Optional[Any] = None) -> str:
        """该 nfo_path 已登记记录里的**唯一**非空 server_id（无记录 / 多个不同来源 → 返回 ""）。

        v4.6.88：扫描路径没有服务器上下文（`_record_nfo_library` 未传 server_id → 落库为 ""），
        而 Webhook 路径带真实 server_id；两者按 server_id 隔离 → 「先 Webhook 入库、后扫描」
        同一文件会出现**两份记录**（实测：6 行 / 库页 2 个条目）。扫描写库前用本函数复用
        已有来源，upsert 便命中同一组（覆盖而非新增），**已有重复也会被顺带收编**。
        多台 Emby 映射同一本地路径（多个不同来源）→ 返回 ""（保持原状，避免误归属）。"""
        if not nfo_path:
            return ""
        try:
            rows = _q(f"SELECT DISTINCT COALESCE(server_id,'') sid FROM person "
                      f"WHERE plugin_id=? AND {_NP_SQL}=? AND COALESCE(server_id,'')<>''",
                      (plugin_id, _npath(nfo_path)))
            _ss = {str((r or {}).get("sid") or "") for r in (rows or [])}
            _ss.discard("")
            return next(iter(_ss)) if len(_ss) == 1 else ""
        except Exception:
            return ""

    def is_deleted_by_nfo_path(self, *, plugin_id: str, nfo_path: str,
                               server_id: Optional[str] = None,
                               db: Optional[Any] = None) -> bool:
        """该 nfo_path 是否有处于观察期（deleted_at 非空）的记录。
        用于 Webhook 入库时识别「这是被删条目的重新入库」→ 事件/通知走「恢复」语义。

        v4.6.67（P0 删除隔离）：新增 server_id（语义同 mark_deleted_by_nfo_path）——
        B 服入库不再被 A 服同路径的观察期行误判成「恢复」。"""
        if not nfo_path:
            return False
        _sc, _scp = _scope_sql_soft(server_id)
        try:
            r = _q1(f"SELECT COUNT(*) c FROM person WHERE plugin_id=? AND {_NP_SQL}=? "
                    f"AND deleted_at IS NOT NULL AND deleted_at!=''" + _sc,
                    (plugin_id, _npath(nfo_path), *_scp))
            return bool(r and int((r.get("c") or 0)) > 0)
        except Exception:
            return False

    def is_deleted_by_item(self, *, plugin_id: str, series_name: str = "",
                           season_num=None, episode_num=None,
                           server_id: Optional[str] = None,
                           db: Optional[Any] = None) -> bool:
        """按 剧名+季+集 判断是否在观察期（恢复识别的兜底：删除时集中的 ItemId 与
        重新入库后的 ItemId 不同，nfo 路径推断也可能因命名差异落空，用剧名+季集兜底）。

        v4.6.66（多服务器隔离）：server_id 非空时收窄到「该服务器 + 旧版遗留空来源」——
        此前跨服务器命中，B 服同名剧入库会被误判为「A 服删除条目的恢复」。
        None=跨来源（旧行为，仅供显式跨来源调用）。"""
        if not series_name and season_num is None and episode_num is None:
            return False
        _sc, _scp = _scope_sql_soft(server_id)
        try:
            sql = ("SELECT COUNT(*) c FROM person WHERE plugin_id=? "
                   "AND deleted_at IS NOT NULL AND deleted_at!=''")
            args = [plugin_id]
            if series_name:
                sql += " AND series_name=?"
                args.append(series_name)
            if season_num is not None:
                sql += " AND season_num=?"
                args.append(season_num)
            if episode_num is not None:
                sql += " AND episode_num=?"
                args.append(episode_num)
            sql += _sc
            args.extend(_scp)
            r = _q1(sql, tuple(args))
            return bool(r and int((r.get("c") or 0)) > 0)
        except Exception:
            return False

    def clear_deleted(self, *, plugin_id: str, nfo_path: str = "", series_name: str = "",
                      season_num=None, episode_num=None,
                      server_id: Optional[str] = None, db: Optional[Any] = None) -> int:
        """解除观察期（deleted_at 置空）。优先 nfo_path 行级精确；路径不命中（删除时
        推断路径与实际 nfo 命名不一致）或缺失时，按 剧名+季+集 行级兜底 ——
        单集恢复只清该集，不波及同剧其他观察期记录。

        v4.6.66（多服务器隔离）：server_id 非空时只清「该服务器 + 旧版遗留空来源」的行，
        B 服同名剧恢复不再误清 A 服的观察期行；None=跨来源（旧行为）。"""
        _sc, _scp = _scope_sql_soft(server_id)
        try:
            if nfo_path:
                n = _x(f"UPDATE person SET deleted_at='' WHERE plugin_id=? AND {_NP_SQL}=? "
                       f"AND deleted_at IS NOT NULL AND deleted_at!=''" + _sc,
                       (plugin_id, _npath(nfo_path), *_scp))
                if n:
                    return n
            if series_name and (season_num is not None or episode_num is not None):
                sql = ("UPDATE person SET deleted_at='' WHERE plugin_id=? AND series_name=? "
                       "AND deleted_at IS NOT NULL AND deleted_at!=''")
                args = [plugin_id, series_name]
                if season_num is not None:
                    sql += " AND season_num=?"
                    args.append(season_num)
                if episode_num is not None:
                    sql += " AND episode_num=?"
                    args.append(episode_num)
                sql += _sc
                args.extend(_scp)
                return _x(sql, tuple(args))
        except Exception:
            return 0
        return 0

    # ── v4.6.72（批次3）：洗版稳定媒体身份恢复 ──
    def is_deleted_by_media(self, *, plugin_id: str, item_id: str = "",
                            media_provider: str = "", media_id: str = "",
                            series_media_id: str = "", emby_item_id: str = "",
                            season_num=None, episode_num=None,
                            server_id: Optional[str] = None,
                            db: Optional[Any] = None) -> int:
        """按**稳定媒体身份**判断是否处于观察期（>0 → 走「恢复」语义）。

        强身份任一命中即算：Emby ItemId / 媒体 item_id / (provider,media_id) /
        series_media_id —— 序列级身份在给出季/集时一并要求季集吻合。洗版后路径 / 标题 /
        Emby ItemId 全变但 provider 未变 → 仍能命中（报告第八~十节）。
        :return: 命中行数
        """
        _sql, _args = _media_strong_sql(
            item_id=item_id, media_provider=media_provider, media_id=media_id,
            series_media_id=series_media_id, emby_item_id=emby_item_id,
            season_num=season_num, episode_num=episode_num)
        if not _sql:
            return 0
        _sc, _scp = _scope_sql_soft(server_id)
        try:
            r = _q1("SELECT COUNT(*) c FROM person WHERE plugin_id=? "
                    "AND deleted_at IS NOT NULL AND deleted_at!=''" + _sql + _sc,
                    (plugin_id, *_args, *_scp))
            return int((r or {}).get("c") or 0)
        except Exception:
            return 0

    def clear_deleted_by_media(self, *, plugin_id: str, item_id: str = "",
                               media_provider: str = "", media_id: str = "",
                               series_media_id: str = "", emby_item_id: str = "",
                               season_num=None, episode_num=None,
                               server_id: Optional[str] = None,
                               db: Optional[Any] = None) -> int:
        """按稳定媒体身份解除观察期（洗版恢复）。语义同 is_deleted_by_media。"""
        _sql, _args = _media_strong_sql(
            item_id=item_id, media_provider=media_provider, media_id=media_id,
            series_media_id=series_media_id, emby_item_id=emby_item_id,
            season_num=season_num, episode_num=episode_num)
        if not _sql:
            return 0
        _sc, _scp = _scope_sql_soft(server_id)
        try:
            return _x("UPDATE person SET deleted_at='' WHERE plugin_id=? "
                      "AND deleted_at IS NOT NULL AND deleted_at!=''" + _sql + _sc,
                      (plugin_id, *_args, *_scp))
        except Exception:
            return 0

    def sample_deleted_identities(self, *, plugin_id: str, item_id: str = "",
                                  media_provider: str = "", media_id: str = "",
                                  series_media_id: str = "", emby_item_id: str = "",
                                  season_num=None, episode_num=None,
                                  server_id: Optional[str] = None, limit: int = 20,
                                  db: Optional[Any] = None) -> list:
        """强身份命中的观察期行身份样本（写「洗版历史别名」用）。"""
        _sql, _args = _media_strong_sql(
            item_id=item_id, media_provider=media_provider, media_id=media_id,
            series_media_id=series_media_id, emby_item_id=emby_item_id,
            season_num=season_num, episode_num=episode_num)
        if not _sql:
            return []
        _sc, _scp = _scope_sql_soft(server_id)
        try:
            return _q("SELECT DISTINCT COALESCE(server_id,'') server_id, COALESCE(item_id,'') item_id, "
                      "COALESCE(emby_item_id,'') emby_item_id, COALESCE(nfo_path,'') nfo_path, "
                      "COALESCE(title,'') title, COALESCE(media_provider,'') media_provider, "
                      "COALESCE(media_id,'') media_id FROM person WHERE plugin_id=? "
                      "AND deleted_at IS NOT NULL AND deleted_at!=''" + _sql + _sc + " LIMIT ?",
                      (plugin_id, *_args, *_scp, int(limit)))
        except Exception:
            return []

    def deleted_weak_candidates(self, *, plugin_id: str, series_name: str = "",
                                title: str = "", season_num=None, episode_num=None,
                                server_id: Optional[str] = None,
                                db: Optional[Any] = None) -> int:
        """弱匹配（剧名 + 季集 / 标题）命中的**去重候选数**（distinct server+item）。

        仅当 ==1 才允许自动恢复；>1 = 存在多个候选，需人工确认（报告第九节 · 候选冲突保护）。
        :return: 去重候选数
        """
        _cond, _args = _weak_sql(series_name=series_name, title=title,
                                 season_num=season_num, episode_num=episode_num)
        if not _cond:
            return 0
        _sc, _scp = _scope_sql_soft(server_id)
        try:
            r = _q1("SELECT COUNT(*) c FROM (SELECT DISTINCT COALESCE(server_id,'') s, "
                    "COALESCE(item_id,'') i FROM person WHERE plugin_id=? "
                    "AND deleted_at IS NOT NULL AND deleted_at!='' AND (" + _cond + ")" + _sc + ")",
                    (plugin_id, *_args, *_scp))
            return int((r or {}).get("c") or 0)
        except Exception:
            return 0

    def clear_deleted_weak(self, *, plugin_id: str, series_name: str = "", title: str = "",
                           season_num=None, episode_num=None,
                           server_id: Optional[str] = None,
                           db: Optional[Any] = None) -> int:
        """弱匹配解除观察期 —— 调用方须先确认 deleted_weak_candidates==1（唯一候选）。"""
        _cond, _args = _weak_sql(series_name=series_name, title=title,
                                 season_num=season_num, episode_num=episode_num)
        if not _cond:
            return 0
        _sc, _scp = _scope_sql_soft(server_id)
        try:
            return _x("UPDATE person SET deleted_at='' WHERE plugin_id=? "
                      "AND deleted_at IS NOT NULL AND deleted_at!='' AND (" + _cond + ")" + _sc,
                      (plugin_id, *_args, *_scp))
        except Exception:
            return 0

    def media_identity_of_item(self, *, plugin_id: str, item_id: str,
                               server_id: Optional[str] = "",
                               db: Optional[Any] = None) -> dict:
        """某条目在 person 表里登记的稳定媒体身份（provider / media_id / series_media_id）。
        用于恢复时补齐「新记录无 provider 但旧行有」的场景。"""
        _sc, _scp = _scope_sql(server_id)
        try:
            r = _q1("SELECT media_provider, media_id, series_media_id FROM person "
                    "WHERE plugin_id=? AND item_id=?" + _sc +
                    " AND (media_id IS NOT NULL AND media_id<>'') LIMIT 1",
                    (plugin_id, item_id, *_scp))
        except Exception:
            r = None
        if not r:
            return {"media_provider": "", "media_id": "", "series_media_id": ""}
        return {"media_provider": str(r.get("media_provider") or ""),
                "media_id": str(r.get("media_id") or ""),
                "series_media_id": str(r.get("series_media_id") or "")}

    # ── v4.6.72（批次3）：洗版历史身份别名 ──
    def alias_put(self, *, plugin_id: str, server_id: str = "", provider: str = "",
                  provider_id: str = "", old_media_id: str = "", old_emby_item_id: str = "",
                  old_nfo_path: str = "", old_title: str = "", new_media_id: str = "",
                  db: Optional[Any] = None) -> int:
        """记录 / 刷新「同一媒体的历史身份别名」（洗版恢复）。

        按 (plugin_id, server_id, provider, provider_id, old_media_id, old_emby_item_id,
        old_nfo_path) 去重，命中刷新 last_seen；与 person 表解耦，删除 / 恢复都不清。

        v4.6.100：去重键补 old_nfo_path —— 同一部剧的不同集共享剧级 media_id、
        且被删行的 emby_item_id 往往为空，此前这些集别名键完全相同 → 后写覆盖先写，
        只有一个集的旧身份被留下（实测：某剧 S2E1/S3E1 只剩 1 条）。
        文件路径逐集唯一，纳入键即可让每集的旧身份各留一条。
        :return: 1 写入/刷新成功，0 无有效身份或失败
        """
        if not old_media_id and not old_emby_item_id:
            return 0
        _onp = str(old_nfo_path or "")
        now = _now()
        try:
            with _conn_lock:
                conn = _get_conn()
                row = conn.execute(
                    "SELECT id FROM media_identity_alias WHERE plugin_id=? "
                    "AND COALESCE(server_id,'')=COALESCE(?,'') AND provider=? AND provider_id=? "
                    "AND COALESCE(old_media_id,'')=COALESCE(?,'') "
                    "AND COALESCE(old_emby_item_id,'')=COALESCE(?,'') "
                    "AND COALESCE(old_nfo_path,'')=COALESCE(?,'')",
                    (plugin_id, server_id, provider, provider_id, old_media_id,
                     old_emby_item_id, _onp)
                ).fetchone()
                if row:
                    conn.execute("UPDATE media_identity_alias SET last_seen=?, new_media_id=?, "
                                 "old_title=? WHERE id=?",
                                 (now, str(new_media_id or ""), str(old_title or ""), row[0]))
                else:
                    conn.execute(
                        "INSERT INTO media_identity_alias (plugin_id, server_id, provider, provider_id, "
                        "old_media_id, old_emby_item_id, old_nfo_path, old_title, new_media_id, "
                        "first_seen, last_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (plugin_id, str(server_id or ""), str(provider or ""), str(provider_id or ""),
                         str(old_media_id or ""), str(old_emby_item_id or ""), _onp,
                         str(old_title or ""), str(new_media_id or ""), now, now))
                conn.commit()
            return 1
        except Exception as e:
            logger.debug(f"[DB] alias_put 失败: {e}")
            return 0

    def alias_resolve(self, *, plugin_id: str, server_id: Optional[str] = "",
                      provider: str = "", provider_id: str = "", item_id: str = "",
                      old_media_id: str = "", db: Optional[Any] = None) -> list:
        """按 provider / 旧媒体 id 查历史别名 → 返回关联的 media_id 集合
        （旧 id 与新 id 都包含，用于把洗版前后的身份归一）。"""
        ids: set = set()
        if item_id:
            ids.add(str(item_id))
        try:
            rows = []
            if provider and provider_id:
                _sc, _scp = _scope_sql_soft(server_id)
                rows = _q("SELECT old_media_id, new_media_id FROM media_identity_alias "
                          "WHERE plugin_id=? AND provider=? AND provider_id=?" + _sc,
                          (plugin_id, provider, provider_id, *_scp))
            if old_media_id:
                rows = rows + _q(
                    "SELECT old_media_id, new_media_id FROM media_identity_alias "
                    "WHERE plugin_id=? AND COALESCE(old_media_id,'')=COALESCE(?,'')",
                    (plugin_id, old_media_id))
            for r in rows:
                for v in (r.get("old_media_id"), r.get("new_media_id")):
                    if v:
                        ids.add(str(v))
        except Exception:
            return sorted(ids)
        return sorted(ids)

    def alias_rows(self, *, plugin_id: str, server_id: Optional[str] = "",
                   provider: str = "", provider_id: str = "",
                   db: Optional[Any] = None) -> list:
        """某 provider 身份的历史别名明细（日志/排查用）。"""
        if not (provider and provider_id):
            return []
        _sc, _scp = _scope_sql_soft(server_id)
        try:
            return _q("SELECT * FROM media_identity_alias WHERE plugin_id=? AND provider=? "
                      "AND provider_id=?" + _sc + " ORDER BY last_seen DESC",
                      (plugin_id, provider, provider_id, *_scp))
        except Exception:
            return []

    def media_probe(self, *, plugin_id: str, server_id: Optional[str] = None,
                    emby_item_id: str = "", item_id: str = "",
                    media_provider: str = "", media_id: str = "",
                    series_media_id: str = "", nfo_path: str = "",
                    season_num=None, episode_num=None, series_name: str = "",
                    title: str = "", db: Optional[Any] = None) -> dict:
        """「插件是否管理过该媒体」探测（v4.6.76 · 规范 §二/§三）—— **删除事件的第一道门禁**。

        Webhook 收到删除事件 ≠ 插件管理过该媒体：「选定媒体库」只说明路径属于用户选的库。
        本方法按稳定身份优先级逐个探测 person 表（含观察期行）与历史别名，返回：
          {"managed": bool, "match_type": emby_item_id/provider/item_id/series_media/
           path/series_episode/alias/none, "matched_rows": N, "ambiguous": bool}
        完全没有命中 → managed=False（调用方必须静默忽略，不建事件/不通知/不写库）。
        """
        out = {"managed": False, "match_type": "none", "matched_rows": 0,
               "ambiguous": False, "status": "ok"}
        _sc, _scp = _scope_sql_soft(server_id)

        def _fail() -> dict:
            """v4.6.98（P1-04）：数据库查询失败 → **不得伪装成「未管理」**。
            调用方据此「不改记录、不发普通删除通知」，并把事件保留为可重试的 error 状态。"""
            return {"managed": False, "match_type": "error", "matched_rows": 0,
                    "ambiguous": False, "status": "error"}

        def _cnt(cond: str, args: list) -> Optional[int]:
            """命中数；数据库查询失败 → None（≠ 0，调用方必须按 error 处理）。"""
            try:
                r = _q1("SELECT COUNT(*) c FROM person WHERE plugin_id=?" + cond + _sc,
                        (plugin_id, *args, *_scp))
                return int((r or {}).get("c") or 0)
            except Exception as _e:
                logger.warning(f"[DB] media_probe 计数查询失败（不当作命中 0，按 error 返回）: {_e}")
                return None

        def _hit(cond: str, args: list, match_type: str) -> Optional[dict]:
            """命中 → 结果 dict；未命中 → None（继续下一优先级）；查询失败 → error dict。"""
            _n = _cnt(cond, args)
            if _n is None:
                return _fail()
            if _n:
                return {"managed": True, "match_type": match_type,
                        "matched_rows": _n, "ambiguous": False, "status": "ok"}
            return None

        _ep = ""
        _epa: list = []
        if season_num is not None:
            _ep += " AND season_num IS ?"; _epa.append(season_num)
        if episode_num is not None:
            _ep += " AND episode_num IS ?"; _epa.append(episode_num)
        # 1) server_id + emby_item_id（同一条目的直接身份）
        if emby_item_id:
            _r = _hit(" AND emby_item_id=?", [str(emby_item_id)], "emby_item_id")
            if _r is not None:
                return _r
        # 2) server_id + (provider, media_id) [+ 季/集]
        if media_provider and media_id:
            _r = _hit(" AND media_provider=? AND media_id=?" + _ep,
                      [str(media_provider), str(media_id)] + _epa, "provider")
            if _r is not None:
                return _r
        # 3) server_id + 媒体 item_id [+ 季/集]
        if item_id:
            _r = _hit(" AND item_id=?" + _ep, [str(item_id)] + _epa, "item_id")
            if _r is not None:
                return _r
        # 4) server_id + series_media_id [+ 季/集]
        if series_media_id:
            _r = _hit(" AND series_media_id=?" + _ep, [str(series_media_id)] + _epa, "series_media")
            if _r is not None:
                return _r
        # 5) server_id + 归一化 nfo_path
        if nfo_path:
            _r = _hit(f" AND {_NP_SQL}=?", [_npath(nfo_path)], "path")
            if _r is not None:
                return _r
        # 6) 弱匹配（剧名 + 季集 / 标题）—— 只用于候选判断，不直接认领
        _wcond, _wargs = _weak_sql(series_name=series_name, title=title,
                                   season_num=season_num, episode_num=episode_num)
        if _wcond:
            try:
                r = _q1("SELECT COUNT(*) c FROM (SELECT DISTINCT COALESCE(server_id,'') s, "
                        "COALESCE(item_id,'') i FROM person WHERE plugin_id=? "
                        "AND (" + _wcond + ")" + _sc + ")", (plugin_id, *_wargs, *_scp))
                _cand = int((r or {}).get("c") or 0)
            except Exception as _e:
                logger.warning(f"[DB] media_probe 弱匹配查询失败（按 error 返回）: {_e}")
                return _fail()
            if _cand:
                # 唯一候选 → 可作为兜底认领（调用方仍需行级标记成功才通知）
                return {"managed": True, "match_type": "series_episode",
                        "matched_rows": _cand, "ambiguous": _cand > 1, "status": "ok"}
        # 7) 历史身份别名（洗版前的旧身份）
        if media_provider and media_id:
            try:
                _aliases = self.alias_resolve(plugin_id=plugin_id, server_id=server_id,
                                              provider=media_provider, provider_id=media_id)
            except Exception as _e:
                logger.warning(f"[DB] media_probe 别名查询失败（按 error 返回）: {_e}")
                return _fail()
            for _a in (_aliases or []):
                if _a and not str(_a).startswith("nfo:"):
                    _r = _hit(" AND item_id=?", [str(_a)], "alias")
                    if _r is not None:
                        return _r
        return out

    def mark_deleted_by_media(self, *, plugin_id: str, item_id: str = "",
                              media_provider: str = "", media_id: str = "",
                              series_media_id: str = "", emby_item_id: str = "",
                              season_num=None, episode_num=None,
                              server_id: Optional[str] = None, deleted_ts: float = None,
                              allow_unscoped: bool = False,
                              include_legacy: bool = True,
                              db: Optional[Any] = None) -> int:
        """按**稳定媒体身份**标记观察期（v4.6.76 · 规范 §二）—— 删除事件路径/命名不一致
        （洗版、Remux、nfo 改名）时，用 provider / item / emby_item_id / series_media_id
        兜底把该媒体全部（或指定季集）行标 deleted_at。
        季/集给定时只标该集；不给则标该媒体全部层级（整剧删除）。"""
        _sql, _args = _media_strong_sql(
            item_id=item_id, media_provider=media_provider, media_id=media_id,
            series_media_id=series_media_id, emby_item_id=emby_item_id,
            season_num=season_num, episode_num=episode_num)
        if not _sql:
            return 0
        if not _require_scope(server_id, "mark_deleted_by_media", allow_unscoped):
            return 0
        ts = str(deleted_ts if deleted_ts is not None else time.time())
        _sc, _scp = _scope_sql_soft(server_id, include_legacy)
        try:
            return _x("UPDATE person SET deleted_at=? WHERE plugin_id=? "
                      "AND (deleted_at='' OR deleted_at IS NULL)" + _sql + _sc,
                      (ts, plugin_id, *_args, *_scp))
        except Exception as e:
            logger.warning(f"[DB] mark_deleted_by_media 失败: {e}")
            return 0

    def expired_item_ids(self, *, plugin_id: str, grace_hours: float = 24,
                         db: Optional[Any] = None) -> list:
        """观察期已过的条目 ID（真删除判定）。
        时间戳比较转数值（CAST REAL）—— 不再依赖字符串字典序。"""
        cut = float(time.time() - float(grace_hours or 24) * 3600)
        try:
            rows = _q("SELECT DISTINCT item_id FROM person WHERE plugin_id=? "
                      "AND deleted_at!='' AND deleted_at IS NOT NULL AND CAST(deleted_at AS REAL) < ?",
                      (plugin_id, cut))
            return [str(r.get("item_id") or "") for r in rows if r.get("item_id")]
        except Exception:
            return []

    def purge_expired(self, *, plugin_id: str, grace_hours: float = 24,
                      db: Optional[Any] = None) -> int:
        """删除已过观察期（真删除）的条目记录。v3.9.7 L5: 同样改数值比较。"""
        cut = float(time.time() - float(grace_hours or 24) * 3600)
        try:
            return _x("DELETE FROM person WHERE plugin_id=? "
                      "AND deleted_at!='' AND deleted_at IS NOT NULL AND CAST(deleted_at AS REAL) < ?",
                      (plugin_id, cut))
        except Exception:
            return 0

    def purge_all_missing(self, *, plugin_id: str, db: Optional[Any] = None) -> int:
        try:
            return _x("DELETE FROM person WHERE plugin_id=? "
                      "AND deleted_at IS NOT NULL AND deleted_at!=''", (plugin_id,))
        except Exception:
            return 0

    def count_missing(self, *, plugin_id: str, db: Optional[Any] = None) -> int:
        """当前处于观察期（deleted_at 非空）的行数（v4.6.76 · 规范 §七）——
        0 条时 UI/日志明确「无需清理」；查询失败返回 -1（调用方不得据此判定为 0）。"""
        try:
            r = _q1("SELECT COUNT(*) c FROM person WHERE plugin_id=? "
                    "AND deleted_at IS NOT NULL AND deleted_at!=''", (plugin_id,))
            return int((r or {}).get("c") or 0)
        except Exception:
            return -1

    # ── 读：某条目全部人物 ──
    def people_of_item(self, *, plugin_id: str, item_id: str, server_id: Optional[str] = "",
                       db: Optional[Any] = None) -> list:
        """某条目的全部人物记录。server_id 见 _scope_sql：
        默认 "" = 仅本地 NFO 来源（DB-001 修复点 —— 旧实现是「过滤在 Python 层且空值
        等于不过滤」，混合库下会把其它来源的同 item_id 记录一并返回）；需要跨来源请显式传 None。"""
        _sc, _scp = _scope_sql(server_id)
        rows = _q(
            "SELECT * FROM person WHERE plugin_id=? AND item_id=?" + _sc +
            " ORDER BY season_num IS NOT NULL, season_num, episode_num, person_index",
            (plugin_id, item_id, *_scp),
        )
        out = []
        for r in rows:
            out.append({
                "index": r.get("person_index"),
                "type": r.get("person_type"),
                "name_before": r.get("name_before"),
                "name_after": r.get("name_after"),
                "role_before": r.get("role_before"),
                "role_after": r.get("role_after"),
                "translated_at": r.get("translated_at"),
                "item_type": r.get("item_type"),
                "season_num": r.get("season_num"),
                "episode_num": r.get("episode_num"),
                "title": r.get("title"),
                "series_name": r.get("series_name") or "",
                "nfo_path": r.get("nfo_path") or "",
                "deleted_at": str(r.get("deleted_at") or ""),
            })
        return out

    # ── 读：某条目标题信息（用于恢复）──
    def item_meta(self, *, plugin_id: str, item_id: str, server_id: Optional[str] = "",
                  db: Optional[Any] = None) -> Optional[dict]:
        """某条目标题信息（用于恢复）。server_id 见 _scope_sql（默认 "" = 仅本地 NFO 来源，
        DB-001）；需要跨来源请显式传 None。"""
        _sc, _scp = _scope_sql(server_id)
        rows = _q("SELECT * FROM person WHERE plugin_id=? AND item_id=?" + _sc, (plugin_id, item_id, *_scp))
        row = rows[0] if rows else None
        if not row:
            return None
        return {
            "item_id": row.get("item_id"),
            "item_type": row.get("item_type"),
            "title": row.get("title"),
            "series_name": row.get("series_name"),
            "season_num": row.get("season_num"),
            "episode_num": row.get("episode_num"),
            "server_id": row.get("server_id") or "",
            "nfo_path": row.get("nfo_path") or "",
        }

    def delete_item(self, *, plugin_id: str, item_id: str, server_id: Optional[str] = "",
                    db: Optional[Any] = None) -> int:
        """删除条目的全部记录。server_id 见 _scope_sql ——
        默认 "" 只删本地 NFO 来源（DB-001：不再连带删除同 item_id 的其它来源记录）；
        需要跨来源整删请显式传 None。"""
        _sc, _scp = _scope_sql(server_id)
        return _x("DELETE FROM person WHERE plugin_id=? AND item_id=?" + _sc,
                  (plugin_id, item_id, *_scp))

    def update_person(self, *, plugin_id: str, item_id: str, server_id: str = "",
                      season_num: int = None, episode_num: int = None, index: int = None,
                      name_after: str = "", role_after: str = "",
                      db: Optional[Any] = None) -> int:
        if index is None:
            return 0
        return _x(
            "UPDATE person SET name_after=?, role_after=?, translated_at=? "
            "WHERE plugin_id=? AND server_id=? AND item_id=? AND season_num IS ? AND episode_num IS ? AND person_index=?",
            (name_after, role_after, _now(), plugin_id, server_id, item_id, season_num, episode_num, index),
        )

    def search_people(self, *, plugin_id: str, keyword: str = "", limit: int = 500,
                      db: Optional[Any] = None) -> list:
        kw = (keyword or "").strip()
        where = "WHERE plugin_id=?"
        params: list = [plugin_id]
        if kw:
            where += " AND (name_before LIKE ? OR name_after LIKE ? OR role_before LIKE ? OR role_after LIKE ?)"
            params += [f"%{kw}%"] * 4
        params.append(int(limit or 500))
        rows = _q(f"SELECT * FROM person {where} ORDER BY translated_at DESC LIMIT ?", params)
        out = []
        for r in rows:
            out.append({
                "index": r.get("person_index"),
                "type": r.get("person_type"),
                "name_before": r.get("name_before"),
                "name_after": r.get("name_after"),
                "role_before": r.get("role_before"),
                "role_after": r.get("role_after"),
                "item_id": r.get("item_id"),
                "item_type": r.get("item_type"),
                "server_id": r.get("server_id") or "",
                "title": r.get("title"),
                "series_name": r.get("series_name") or "",
                "season_num": r.get("season_num"),
                "episode_num": r.get("episode_num"),
                "nfo_path": r.get("nfo_path") or "",
            })
        return out

    def update_by_name(self, *, plugin_id: str, name_before: str, name_after: str = "",
                       role_before: str = "", role_after: str = "",
                       db: Optional[Any] = None) -> int:
        """role_before 可选 —— 传了就按它精确匹配行（同名多角色不互相污染）；
        不传时空值不再补成空串（旧实现 (role_before or '') 只命中 role_before='' 的行，
        绝大多数记录不更新、全局修正基本失效）。"""
        if not name_before:
            return 0
        now = _now()
        if role_after:
            if role_before:
                return _x(
                    "UPDATE person SET name_after=?, role_after=?, translated_at=? "
                    "WHERE plugin_id=? AND name_before=? AND role_before=?",
                    (name_after, role_after, now, plugin_id, name_before, role_before))
            return _x(
                "UPDATE person SET name_after=?, role_after=?, translated_at=? "
                "WHERE plugin_id=? AND name_before=?",
                (name_after, role_after, now, plugin_id, name_before))
        return _x(
            "UPDATE person SET name_after=?, translated_at=? WHERE plugin_id=? AND name_before=?",
            (name_after, now, plugin_id, name_before))

    def update_role_by_before(self, *, plugin_id: str, role_before: str, role_after: str = "",
                              db: Optional[Any] = None) -> int:
        rb = (role_before or "").strip()
        ra = (role_after or "").strip()
        if not rb or not ra:
            return 0
        try:
            return _x("UPDATE person SET role_after=?, translated_at=? "
                      "WHERE plugin_id=? AND role_before=?",
                      (ra, _now(), plugin_id, rb))
        except Exception as e:
            logger.warning(f"[DB] update_role_by_before 失败: {e}")
            return 0

    def update_person_by_name_in_item(self, *, plugin_id: str, item_id: str, server_id: str = "",
                                      name_before: str = "", name_after: str = "",
                                      role_before: str = "", role_after: str = "",
                                      db: Optional[Any] = None) -> int:
        """在单个条目（剧/电影）内按原文名更新全部记录（剧+各集一次改完）。
        传 role_before 时角色按它精确匹配（同名多角色不互相污染）。"""
        if not item_id or not name_before:
            return 0
        now = _now()
        try:
            if role_after and role_before:
                return _x(
                    "UPDATE person SET name_after=?, role_after=?, translated_at=? "
                    "WHERE plugin_id=? AND server_id=? AND item_id=? AND name_before=? AND role_before=?",
                    (name_after or name_before, role_after, now, plugin_id, server_id,
                     item_id, name_before, role_before))
            if role_after:
                return _x(
                    "UPDATE person SET name_after=?, role_after=?, translated_at=? "
                    "WHERE plugin_id=? AND server_id=? AND item_id=? AND name_before=?",
                    (name_after or name_before, role_after, now, plugin_id, server_id,
                     item_id, name_before))
            return _x(
                "UPDATE person SET name_after=?, translated_at=? "
                "WHERE plugin_id=? AND server_id=? AND item_id=? AND name_before=?",
                (name_after or name_before, now, plugin_id, server_id, item_id, name_before))
        except Exception as e:
            logger.warning(f"[DB] update_person_by_name_in_item 失败: {e}")
            return 0

    def update_role_in_item(self, *, plugin_id: str, item_id: str, server_id: str = "",
                            role_before: str = "", role_after: str = "",
                            db: Optional[Any] = None) -> int:
        """在单个条目（剧/电影）内按角色原文更新（v4.6.60）。
        P0 数据一致性 —— 「重新翻译」是条目级任务，此前用全局 update_role_by_before(plugin_id, role_before)，
        会把**其它作品**里同名角色一起改掉（且那些条目并未登记写回 → 库与 NFO 不一致）。
        角色名必须带 item_id / server_id 精确限定。"""
        rb = (role_before or "").strip()
        ra = (role_after or "").strip()
        if not item_id or not rb or not ra:
            return 0
        try:
            return _x("UPDATE person SET role_after=?, translated_at=? "
                      "WHERE plugin_id=? AND server_id=? AND item_id=? AND role_before=?",
                      (ra, _now(), plugin_id, str(server_id or ""), item_id, rb))
        except Exception as e:
            logger.warning(f"[DB] update_role_in_item 失败: {e}")
            return 0

    def term_titles(self, *, plugin_id: str, terms: Optional[list] = None,
                    db: Optional[Any] = None) -> dict:
        """词条 → 作品名映射（v4.6.60 · P1-4）。
        供「按作品分批」（per_title）聚合时把同作品词条归到一组并带上作品上下文；
        同词条出现在多个作品时取首个非空作品名。
        :return {term: title}
        """
        _ts = [str(t) for t in (terms or []) if str(t or "").strip()]
        if not _ts:
            return {}
        out: dict = {}
        _marks = ",".join("?" * len(_ts))
        try:
            for _col in ("name_before", "role_before"):
                rows = _q(f"SELECT {_col} AS term, title FROM person "
                          f"WHERE plugin_id=? AND {_col} IN ({_marks}) "
                          f"AND title IS NOT NULL AND title<>'' LIMIT 4000",
                          tuple([plugin_id] + _ts))
                for r in rows:
                    _t = str(r.get("term") or "")
                    if _t and _t not in out:
                        out[_t] = str(r.get("title") or "")
        except Exception as e:
            logger.debug(f"[DB] term_titles 查询失败: {e}")
        return out

    def rows_by_name(self, *, plugin_id: str, name_before: str, limit: int = 1000,
                     server_id: str = "", db: Optional[Any] = None) -> list:
        """精确匹配 name_before 的全部行（剧级 + 各集），含定位键（item_id/季/集/序号），
        供「出现清单」展示与逐处编辑（仅改这一处）。
        UI-006：可选 server_id 限定来源媒体服务器，避免不同服务器同名人物混入清单。"""
        nm = (name_before or "").strip()
        if not nm:
            return []
        _sid = str(server_id or "").strip()
        try:
            _sql = (
                "SELECT item_id, server_id, item_type, title, series_name, season_num, episode_num, "
                "person_index, name_before, name_after, role_before, role_after, nfo_path, deleted_at "
                "FROM person WHERE plugin_id=? AND name_before=? "
            )
            _args: list = [plugin_id, nm]
            if _sid:
                _sql += "AND server_id=? "
                _args.append(_sid)
            _sql += ("ORDER BY series_name, season_num IS NOT NULL, season_num, episode_num, "
                     "person_index LIMIT ?")
            _args.append(int(limit))
            rows = _q(_sql, tuple(_args))
            out = []
            for r in rows:
                out.append({
                    "item_id": str(r.get("item_id") or ""),
                    "server_id": str(r.get("server_id") or ""),
                    "item_type": str(r.get("item_type") or ""),
                    "title": str(r.get("title") or ""),
                    "series_name": str(r.get("series_name") or ""),
                    "season_num": r.get("season_num"),
                    "episode_num": r.get("episode_num"),
                    "index": r.get("person_index"),
                    "name_before": str(r.get("name_before") or ""),
                    "name_after": str(r.get("name_after") or ""),
                    "role_before": str(r.get("role_before") or ""),
                    "role_after": str(r.get("role_after") or ""),
                    "nfo_path": str(r.get("nfo_path") or ""),
                    "deleted_at": str(r.get("deleted_at") or ""),
                })
            return out
        except Exception as e:
            logger.warning(f"[DB] rows_by_name 失败: {e}")
            return []

    def distinct_name_pairs(self, *, plugin_id: str, limit: int = 5000,
                            db: Optional[Any] = None) -> list:
        """返回库中所有「已翻译」的人名对（去重）。供批量同步 Emby 人名。"""
        try:
            rows = _q(
                "SELECT DISTINCT name_before, name_after FROM person "
                "WHERE plugin_id=? AND name_before<>'' AND name_after<>'' AND name_after<>name_before "
                "ORDER BY name_before LIMIT ?",
                (plugin_id, int(limit)))
            return [{"name_before": str(r.get("name_before") or "").strip(),
                     "name_after": str(r.get("name_after") or "").strip()} for r in rows]
        except Exception as e:
            logger.warning(f"[DB] distinct_name_pairs 失败: {e}")
            return []

    def pairs_for_names(self, *, plugin_id: str, names: list,
                        db: Optional[Any] = None) -> list:
        ns = [str(x).strip() for x in (names or []) if str(x or "").strip()]
        if not ns:
            return []
        marks = ",".join(["?"] * len(ns))
        try:
            rows = _q(
                f"SELECT name_before, MAX(name_after) AS name_after FROM person "
                f"WHERE plugin_id=? AND name_before IN ({marks}) "
                f"AND name_after<>'' AND name_after<>name_before GROUP BY name_before",
                tuple([plugin_id] + ns))
            return [{"name_before": str(r.get("name_before") or "").strip(),
                     "name_after": str(r.get("name_after") or "").strip()} for r in rows]
        except Exception as e:
            logger.warning(f"[DB] pairs_for_names 失败: {e}")
            return []

    def has_deleted_for_series(self, *, plugin_id: str, series_name: str,
                               server_id: Optional[str] = None,
                               db: Optional[Any] = None) -> bool:
        """该剧名是否还有处于观察期（deleted_at 非空）的记录。
        v4.6.66（P0-5 极端情况）：整剧删除事件的清除时机 —— 只有把该剧被删的记录
        全部恢复（不再有观察期行）才清「整部删除」事件，避免恢复 1 集就误清整部事件。
        server_id 见 _scope_sql：传具体服务器只查该来源；None=跨来源（保守，倾向保留）。"""
        _sn = str(series_name or "").strip()
        if not _sn:
            return False
        _sc, _scp = _scope_sql(server_id)
        try:
            r = _q1("SELECT COUNT(*) c FROM person WHERE plugin_id=? AND series_name=? "
                    "AND deleted_at IS NOT NULL AND deleted_at<>''" + _sc,
                    (plugin_id, _sn, *_scp))
            return bool(r and int(r.get("c") or 0) > 0)
        except Exception as e:
            logger.warning(f"[DB] has_deleted_for_series 失败: {e}")
            return True   # 查询失败 → 保守返回「仍有观察期」：宁可事件多留，不误清

    def missing_events(self, *, plugin_id: str, limit: int = 100) -> list:
        """返回处于观察期（deleted_at 非空）的记录，按剧/集聚合。"""
        try:
            rows = _q("SELECT item_id, title, series_name, season_num, episode_num, deleted_at, "
                      "COUNT(*) AS n FROM person "
                      "WHERE plugin_id=? AND deleted_at IS NOT NULL AND deleted_at<>'' "
                      "GROUP BY item_id, season_num, episode_num "
                      "ORDER BY deleted_at DESC LIMIT ?", (plugin_id, int(limit)))
            return [{"item_id": str(r.get("item_id") or ""),
                     "title": str(r.get("title") or ""),
                     "series_name": str(r.get("series_name") or ""),
                     "season_num": r.get("season_num"),
                     "episode_num": r.get("episode_num"),
                     "deleted_at": str(r.get("deleted_at") or ""),
                     "n": int(r.get("n") or 0)} for r in rows]
        except Exception as e:
            logger.warning(f"[DB] missing_events 失败: {e}")
            return []

    def probe_keys(self, *, plugin_id: str, db: Optional[Any] = None) -> dict:
        """返回库内「已知条目」与「已收录集」：
        {"items": {item_id, ...}, "episodes": {item_id: {(season, episode), ...}}}
        探测时与 Emby 清单对差，缺的集/全新条目才会被补翻。"""
        items: set = set()
        eps: dict = {}
        try:
            for r in _q("SELECT DISTINCT item_id, item_type FROM person "
                        "WHERE plugin_id=? AND item_type IN ('Series','Movie')", (plugin_id,)):
                _i = str(r.get("item_id") or "").strip()
                if _i:
                    items.add(_i)
            for r in _q("SELECT DISTINCT item_id, season_num, episode_num FROM person "
                        "WHERE plugin_id=? AND season_num IS NOT NULL AND episode_num IS NOT NULL",
                        (plugin_id,)):
                _i = str(r.get("item_id") or "").strip()
                if not _i:
                    continue
                eps.setdefault(_i, set()).add((int(r.get("season_num") or 0),
                                               int(r.get("episode_num") or 0)))
            # 有集记录的剧也算已知条目（剧级记录缺失时，剧仍不应被当「全新」处理）
            items.update(eps.keys())
        except Exception as e:
            logger.warning(f"[DB] probe_keys 失败: {e}")
        return {"items": items, "episodes": eps}

    def update_role_by_scope(self, *, plugin_id: str, item_id: str, server_id: str = "",
                             season_num: Optional[int] = None, episode_num: Optional[int] = None,
                             index: Optional[int] = None, role_before: str = "",
                             role_after: str = "", scope: str = "single",
                             db: Optional[Any] = None) -> int:
        """角色在 Emby 侧是逐条目的（可局部改，与人名的全局语义不同），故按范围更新。"""
        ra = (role_after or "").strip()
        if not ra or not item_id:
            return 0
        rb = (role_before or "").strip()
        sc = str(scope or "single").lower()
        try:
            now = _now()
            svr = str(server_id or "")
            if sc == "library":
                if not rb:
                    return 0
                return _x("UPDATE person SET role_after=?, translated_at=? "
                          "WHERE plugin_id=? AND server_id=? AND role_before=?",
                          (ra, now, plugin_id, svr, rb))
            if sc == "series":
                sql = ("UPDATE person SET role_after=?, translated_at=? "
                       "WHERE plugin_id=? AND server_id=? AND item_id=?")
                params: list = [ra, now, plugin_id, svr, item_id]
            elif sc == "season":
                sql = ("UPDATE person SET role_after=?, translated_at=? "
                       "WHERE plugin_id=? AND server_id=? AND item_id=? AND season_num IS ?")
                params = [ra, now, plugin_id, svr, item_id, season_num]
            elif sc == "tv":
                sql = ("UPDATE person SET role_after=?, translated_at=? "
                       "WHERE plugin_id=? AND server_id=? AND item_id=? AND season_num IS NULL AND episode_num IS NULL")
                params = [ra, now, plugin_id, svr, item_id]
            else:  # single（仅这一集 / 剧级单条）
                sql = ("UPDATE person SET role_after=?, translated_at=? "
                       "WHERE plugin_id=? AND server_id=? AND item_id=? AND season_num IS ? AND episode_num IS ?")
                params = [ra, now, plugin_id, svr, item_id, season_num, episode_num]
                if index is not None:
                    sql += " AND person_index=?"
                    params.append(int(index))
            if rb:
                sql += " AND role_before=?"
                params.append(rb)
            return _x(sql, tuple(params))
        except Exception as e:
            logger.warning(f"[DB] update_role_by_scope 失败: {e}")
            return 0

    def update_name_by_scope(self, *, plugin_id: str, name_before: str, name_after: str = "",
                             server_id: str = "", item_id: str = "",
                             season_num: Optional[int] = None, episode_num: Optional[int] = None,
                             index: Optional[int] = None, scope: str = "single",
                             db: Optional[Any] = None) -> int:
        """人名按范围更新（v4.6.74 · 报告第十四节）—— **默认只改当前人物身份**，
        不再默认「全库同名一起改」（同名的两个不同真人会被误改）。

        scope：
          single  （默认）只改当前这一条 occurrence（server + item + 季 + 集 + 序号）
          series  改该作品内同名（server + item 下的全部集/剧级行）
          library 「全库同名」—— 用户主动选择才走这里（跨作品，可能误改同名的另一个人）
        """
        na = str(name_after or "")
        nb = str(name_before or "").strip()
        if not nb:
            return 0
        sc = str(scope or "single").lower()
        now = _now()
        try:
            if sc == "library":
                # 全库同名（危险操作，仅在用户明确选择时调用）
                return int(self.update_by_name(plugin_id=plugin_id, name_before=nb,
                                               name_after=na) or 0)
            if not item_id:
                return 0
            svr = str(server_id or "")
            if sc == "series":
                sql = ("UPDATE person SET name_after=?, translated_at=? "
                       "WHERE plugin_id=? AND server_id=? AND item_id=?")
                params: list = [na, now, plugin_id, svr, item_id]
            else:  # single（仅这一条 occurrence）
                sql = ("UPDATE person SET name_after=?, translated_at=? "
                       "WHERE plugin_id=? AND server_id=? AND item_id=? "
                       "AND season_num IS ? AND episode_num IS ?")
                params = [na, now, plugin_id, svr, item_id, season_num, episode_num]
                if index is not None:
                    sql += " AND person_index=?"
                    params.append(int(index))
            sql += " AND name_before=?"
            params.append(nb)
            return _x(sql, tuple(params))
        except Exception as e:
            logger.warning(f"[DB] update_name_by_scope 失败: {e}")
            return 0

    def all_rows(self, *, plugin_id: str, db: Optional[Any] = None) -> list:
        """全量读取 person 表（库页「全部翻译」只翻译入库用）：含定位键与原文。"""
        try:
            rows = _q("SELECT * FROM person WHERE plugin_id=? ORDER BY id", (plugin_id,))
            return [{
                "id": r.get("id"),
                "item_id": str(r.get("item_id") or ""),
                "server_id": str(r.get("server_id") or ""),
                "season_num": r.get("season_num"),
                "episode_num": r.get("episode_num"),
                "person_index": r.get("person_index"),
                "person_type": r.get("person_type") or "Actor",
                "name_before": r.get("name_before") or "",
                "name_after": r.get("name_after") or "",
                "role_before": r.get("role_before") or "",
                "role_after": r.get("role_after") or "",
                "nfo_path": r.get("nfo_path") or "",
            } for r in rows]
        except Exception:
            return []

    _PENDING_KEY_CASE = ("CASE WHEN lower({c}) IN ('actor','voiceactor','star') THEN 'actor' "
                         "WHEN lower({c})='director' THEN 'director' "
                         "WHEN lower({c})='writer' THEN 'writer' "
                         "WHEN lower({c})='producer' THEN 'producer' ELSE 'guest' END")

    _LIM_UNLIMITED = 2147483647

    def pending_terms(self, *, plugin_id: str, db: Optional[Any] = None,
                      scan_mode: Optional[str] = None,
                      limits: Optional[dict] = None,
                      disabled_types: Optional[list] = None,
                      only_pending: bool = True,
                      exclude_episodes: bool = False) -> dict:
        """库内翻译收集用聚合 SQL —— 不整表加载。
        返回 {"names": [(term, type)...], "roles": [(term, type)...]}（两排同口径）。
        未翻译判定：name_after/role_after 空/NULL/==原文。
        scan_mode 传入时按扫描模式收窄口径（nfo 只取 server_id 空的本地条目；
        api 只取 server_id 非空的在线条目），与库页左侧列表口径一致。
        limits —— 按「每文件、每人物类型取前 N 个」（按 person_index 顺序）过滤人名词条；
        **角色名同口径一同过滤**（v4.6.48：类型 + 人数同时对两排生效）。
        数字语义：N<=0 / 留空 = 不限（该类型全部）；翻不翻该类型由「类型开关」决定（disabled_types）。
        结构 {"movie": {...}, "tvshow": {...}, "episode": {...}}；item_type=Movie→movie、Series→tvshow、Episode→episode。
        disabled_types —— 已关闭翻译的人物类型（命中即不计入，两排共用同一套类型开关）。
        v4.6.68：scan_mode 来源判定改用 _scan_scope_sql（按 nfo_path）—— 与库页同一口径；
        此前用「server_id 是否为空」，P0-1 后 Webhook 行带真实 server_id 会被误排除。
        """
        _scope = _scan_scope_sql(scan_mode)
        _dt = [str(t) for t in (disabled_types or []) if str(t or "").strip()]
        try:
            _nsql, _nparams = self._pending_kind_sql(plugin_id, _scope, limits, "name_before", _dt,
                                                     only_pending,
                                                     exclude_episodes=exclude_episodes)
            # 人数上限按「人」计数、对两排生效：**演员=3 + 只翻第二排 = 取前 3 个演员的角色名**
            # （角色名与第一排人名共用同一套「每文件每类型前 N 个」；且 N 只在「待翻」里数，
            #  已翻完的不占名额 —— 只要还有待翻的，就能翻到人）
            _rsql, _rparams = self._pending_kind_sql(plugin_id, _scope, limits, "role_before", _dt,
                                                     only_pending,
                                                     exclude_episodes=exclude_episodes)
            n_rows = _q(_nsql, _nparams)
            r_rows = _q(_rsql, _rparams)

            def _pairs(rows):
                out, seen = [], set()
                for r in rows:
                    _t = str(r.get("term") or "").strip()
                    if not _t or _t in seen:
                        continue
                    seen.add(_t)
                    out.append((_t, str(r.get("person_type") or "Actor").strip() or "Actor"))
                return out

            return {"names": _pairs(n_rows), "roles": _pairs(r_rows)}
        except Exception:
            return {"names": [], "roles": []}

    def force_item_occurrences(self, *, plugin_id: str, item_id: str, server_id: str = "",
                               limits: Optional[dict] = None,
                               disabled_types: Optional[list] = None,
                               only_pending: bool = False,
                               exclude_episodes: bool = False) -> dict:
        """「重新翻译」用：单条目在「人数上限（每文件每类型前 N）」约束下的 occurrence 明细
        （v4.6.64 · occurrence 化）—— 与 pending_terms_full 同一套 SQL/口径，但限定到该条目、
        默认 only_pending=False（强制重翻含已翻词条）。每项带 season/episode/person_index，
        供 apply_translations_occurrence 精确写回。
        :return {"names": [occ...], "roles": [occ...]}，occ = {term,type,item_id,server_id,
                 season_num,episode_num,person_index,title}
        """
        try:
            _nsql, _np = self._pending_kind_sql(plugin_id, "", limits, "name_before", disabled_types,
                                                only_pending, with_items=True,
                                                item_id=item_id, server_id=server_id,
                                                exclude_episodes=exclude_episodes)
            _rsql, _rp = self._pending_kind_sql(plugin_id, "", limits, "role_before", disabled_types,
                                                only_pending, with_items=True,
                                                item_id=item_id, server_id=server_id,
                                                exclude_episodes=exclude_episodes)

            def _mk(rows):
                out, seen = [], set()
                for r in rows:
                    _t = str(r.get("term") or "").strip()
                    if not _t:
                        continue
                    _occ = {"term": _t,
                            "type": str(r.get("person_type") or "Actor").strip() or "Actor",
                            "item_id": str(r.get("item_id") or ""),
                            "server_id": str(r.get("server_id") or ""),
                            "season_num": r.get("season_num"),
                            "episode_num": r.get("episode_num"),
                            "person_index": int(r.get("person_index") or 0),
                            "title": str(r.get("title") or "")}
                    _key = (_occ["season_num"], _occ["episode_num"], _occ["person_index"], _t)
                    if _key in seen:
                        continue
                    seen.add(_key)
                    out.append(_occ)
                return out

            return {"names": _mk(_q(_nsql, _np)), "roles": _mk(_q(_rsql, _rp))}
        except Exception:
            return {"names": [], "roles": []}

    def pending_terms_full(self, *, plugin_id: str, scan_mode: Optional[str] = None,
                           limits: Optional[dict] = None,
                           disabled_types: Optional[list] = None,
                           only_pending: bool = True,
                           exclude_episodes: bool = False) -> dict:
        """统一口径「词条 × 条目」明细（v4.6.61 · P1-2）—— 与 pending_terms 完全同一套
        SQL 口径（人数上限 / 类型过滤 / 未翻译判定），但每条附 item_id/server_id/title。

        供插件层「唯一待翻快照」同时得到：词条数（按 term 去重）、条目数（按 item 去重）、
        待翻译明细（按条目分组）—— 徽章 / 明细弹窗 / 预估 / worker 日志 / 通知全部走这一份，
        不再各自维护第二套 SQL 统计。
        返回 {"names": [{"term","type","item_id","server_id","title"}...],
              "roles": [同上]}；异常返回空结构（调用方兜底为 0）。
        v4.6.68：scan_mode 来源判定改用 _scan_scope_sql（按 nfo_path），与库页/ pending_terms 同口径。"""
        _scope = _scan_scope_sql(scan_mode)
        _dt = [str(t) for t in (disabled_types or []) if str(t or "").strip()]
        try:
            _nsql, _nparams = self._pending_kind_sql(plugin_id, _scope, limits, "name_before", _dt,
                                                     only_pending, with_items=True,
                                                     exclude_episodes=exclude_episodes)
            _rsql, _rparams = self._pending_kind_sql(plugin_id, _scope, limits, "role_before", _dt,
                                                     only_pending, with_items=True,
                                                     exclude_episodes=exclude_episodes)
            _n_rows = _q(_nsql, _nparams)
            _r_rows = _q(_rsql, _rparams)
            if len(_n_rows) >= _PENDING_PAIR_CAP or len(_r_rows) >= _PENDING_PAIR_CAP:
                logger.debug(f"[DB] 待翻明细对达到上限 {_PENDING_PAIR_CAP}（已按前 N 条统计）")

            def _rows(rows):
                out = []
                for r in rows:
                    _t = str(r.get("term") or "").strip()
                    if not _t:
                        continue
                    out.append({"term": _t,
                                "type": str(r.get("person_type") or "Actor").strip() or "Actor",
                                "item_id": str(r.get("item_id") or ""),
                                "server_id": str(r.get("server_id") or ""),
                                # v4.6.64：occurrence 精确定位键（同名原文分属不同作品/集/序号不串）
                                "season_num": r.get("season_num"),
                                "episode_num": r.get("episode_num"),
                                "person_index": int(r.get("person_index") or 0),
                                "title": str(r.get("title") or "")})
                return out

            return {"names": _rows(_n_rows), "roles": _rows(_r_rows)}
        except Exception:
            return {"names": [], "roles": []}

    def _pending_kind_sql(self, plugin_id: str, scope: str = "",
                          limits: Optional[dict] = None, column: str = "name_before",
                          disabled_types: Optional[list] = None,
                          only_pending: bool = True,
                          with_items: bool = False,
                          item_id: str = "", server_id: str = "",
                          exclude_episodes: bool = False) -> tuple:
        """构造「词条」查询（column = name_before / role_before），返回 (sql, params)。
        only_pending=True → 只取「未翻译」（for 待翻统计 / 翻译取词）；
        only_pending=False → 取「符合范围」的全部（不管是否已翻，for 预估里的「范围内 N 个」）。
        limits 空 → 不限人数（逐词条去重）；limits 有 → 按「同文件、同人物类型取前 N 个」（按 person_index 顺序）。
        数字语义（v4.6.48）：N<=0 或留空 = 不限（该类型全部）；producer 复用 writer 上限。
        item_type Movie→movie、Series→tvshow、Episode→episode。
        with_items=True（v4.6.61 唯一快照）→ 附 item_id/server_id/title，按「词条 × 条目」去重输出，
        供 Python 侧同时算出 词条数 / 条目数 / 待翻译明细（同一 SQL 口径，不再维护第二套统计）。
        disabled_types —— 已关闭翻译的人物类型（v4.6.53 起由本函数直接拼条件+参数，
        此前调用方只传了含 `?` 的 SQL 片段却没带参数 → 只要有任一类型开关关闭就报
        「bindings 数量不符」→ 被 except 吞掉 → 待翻恒为空，已修）。
        exclude_episodes（v4.6.68）—— 「处理单集」=关时排除 Episode 层级行（见 _excl_ep_sql）。"""
        _col = "role_before" if column == "role_before" else "name_before"
        _after = "role_after" if _col == "role_before" else "name_after"
        _dt = [str(t) for t in (disabled_types or []) if str(t or "").strip()]
        _marks = ""
        if _dt:
            _marks = (" AND (person_type IS NULL OR person_type='' "
                      f"OR person_type NOT IN ({','.join('?' * len(_dt))}))")
        _pend_sql = ""
        if only_pending:
            _pend_sql = f" AND ({_after}='' OR {_after} IS NULL OR {_after}={_col})"
        if not limits:
            _where = (f"FROM person WHERE plugin_id=? AND {_col}<>''" + _pend_sql + _marks
                      + _excl_ep_sql(exclude_episodes))
            if str(item_id or "").strip():
                _where += " AND item_id=? AND server_id=?"
            _p0 = (plugin_id, *_dt, str(item_id), str(server_id or "")) if str(item_id or "").strip() \
                else (plugin_id, *_dt)
            if with_items:
                return (f"SELECT {_col} AS term, person_type, item_id, server_id, season_num, episode_num, "
                        f"person_index, {_SQL_ITEM_TITLE} AS title "
                        + _where + scope +
                        f" GROUP BY {_col}, item_id, server_id, season_num, episode_num, person_index "
                        f"LIMIT {_PENDING_PAIR_CAP}", _p0)
            return (f"SELECT {_col} AS term, person_type " + _where + scope +
                    f" GROUP BY {_col}", _p0)
        _kind_case = self._PENDING_KEY_CASE.format(c="person_type")
        _lvl_case = ("CASE WHEN item_type='Series' THEN 'tvshow' "
                     "WHEN item_type='Episode' THEN 'episode' ELSE 'movie' END")
        _whens: List[str] = []
        for _lvl in ("movie", "tvshow", "episode"):
            _lm = limits.get(_lvl) or {}
            for _kind in ("actor", "guest", "director", "writer", "producer"):
                _lk = "writer" if _kind == "producer" else _kind
                _n = int(_lm.get(_lk, 0) or 0)
                if _n <= 0:
                    _n = self._LIM_UNLIMITED          # 0 / 留空 = 不限
                _whens.append(f"WHEN lvl='{_lvl}' AND kind='{_kind}' THEN {_n}")
        _lim_case = "CASE " + " ".join(_whens) + f" ELSE {self._LIM_UNLIMITED} END"
        # v4.6.62（关键修复）：「人数上限」改为**硬上限** —— 先按 person_index 取「该文件该类型前 N 个人」
        # 这个**固定集合**（不因已翻而缩小），再在集合内筛「仍未翻译」的。
        # 此前 only_pending 谓词写在内层（ROW_NUMBER 之前）→ 已翻完的行被排除后 ROW_NUMBER 重排，
        # 于是「超出上限」的那些人**逐个轮转补位**：上限=3、共 6 人时，翻完前 3 个后立刻又冒出后 3 个 →
        # 「完成 3 / 剩余 3」永远翻不完、待翻译明细一直挂着（用户实测「明明翻成功还显示待翻」）。
        # 结构化：r = 「前 N 个人」的固定集合（带 rn/lim 与 before/after 原始列），外层再筛未翻译。
        _inner = (f"FROM person WHERE plugin_id=? AND {_col}<>''" + _marks + scope
                  + _excl_ep_sql(exclude_episodes))
        _iparams: List[Any] = []
        # v4.6.64：条目级过滤（「重新翻译」按 item 取 occurrence，用同一套人数上限/类型口径）
        if str(item_id or "").strip():
            _inner += " AND item_id=? AND server_id=?"
            _iparams = [str(item_id), str(server_id or "")]
        _params_out = (plugin_id, *_dt, *_iparams)
        _outer_pend = (f" AND ({_after}='' OR {_after} IS NULL OR {_after}={_col})"
                       if only_pending else "")
        if with_items:
            # v4.6.64：带出 season_num / episode_num / person_index —— 构成 occurrence 精确定位键
            # v4.6.95：title 走「剧级行标题优先」聚合（见 _SQL_ITEM_TITLE）——
            # 中间层需透传 item_type/series_name 供外层聚合（否则只能拿到已折叠的 title）。
            _sql = (f"SELECT {_col} AS term, person_type, item_id, server_id, season_num, episode_num, "
                    f"person_index, {_SQL_ITEM_TITLE} AS title FROM ("
                    f"SELECT {_col}, person_type, item_id, server_id, season_num, episode_num, "
                    f"person_index, title, item_type, series_name, {_after}, "
                    "ROW_NUMBER() OVER (PARTITION BY server_id, item_id, season_num, episode_num, kind "
                    "ORDER BY person_index, id) AS rn, " + _lim_case + " AS lim "
                    f"FROM (SELECT {_col}, person_type, server_id, item_id, season_num, episode_num, "
                    "person_index, id, title, item_type, series_name, " + _after + ", "
                    + _lvl_case + " AS lvl, " + _kind_case + " AS kind "
                    + _inner + ") b) r WHERE rn <= lim" + _outer_pend +
                    f" GROUP BY {_col}, item_id, server_id, season_num, episode_num, person_index "
                    f"LIMIT {_PENDING_PAIR_CAP}")
            return (_sql, _params_out)
        _sql = (f"SELECT {_col} AS term, person_type FROM ("
                f"SELECT {_col}, person_type, {_after}, "
                "ROW_NUMBER() OVER (PARTITION BY server_id, item_id, season_num, episode_num, kind "
                "ORDER BY person_index, id) AS rn, " + _lim_case + " AS lim "
                f"FROM (SELECT {_col}, person_type, server_id, item_id, season_num, episode_num, "
                "person_index, id, " + _after + ", " + _lvl_case + " AS lvl, " + _kind_case + " AS kind "
                + _inner + ") b) r WHERE rn <= lim" + _outer_pend + f" GROUP BY {_col}")
        return (_sql, _params_out)


    def pending_items_count(self, *, plugin_id: str, scan_mode: Optional[str] = None,
                            person_on: bool = True, role_on: bool = True,
                            disabled_types: Optional[list] = None,
                            exclude_episodes: bool = False,
                            db: Optional[Any] = None) -> int:
        """库内「还有多少个条目没翻完」—— 库页顶部常驻统计（条目维度）。
        口径与 pending_terms 一致：仍未翻译判定 = *_after 空/NULL/== *_before；
        scan_mode 收窄本地/在线；person_on/role_on 为第一/第二排总开关；
        disabled_types 为「已关闭翻译」的人物类型（命中即不计入，未知类型不排除）。
        exclude_episodes（v4.6.68）—— 「处理单集」=关时不计 Episode 条目（与翻译门禁一致）。
        两个 SELECT 用 UNION 去重，同一 (item_id, server_id) 只算一次。"""
        _scope = _scan_scope_sql(scan_mode)
        _ex = _excl_ep_sql(exclude_episodes)
        _conds: List[str] = []
        _params: List[Any] = []
        _dt = [str(t) for t in (disabled_types or []) if str(t or "").strip()]
        if person_on:
            _c = ("SELECT item_id, server_id FROM person WHERE plugin_id=? "
                  "AND name_before<>'' AND (name_after='' OR name_after IS NULL OR name_after=name_before)")
            if _dt:
                _marks = ",".join("?" * len(_dt))
                _c += f" AND (person_type IS NULL OR person_type='' OR person_type NOT IN ({_marks}))"
            _c += _scope + _ex
            _conds.append(_c)
            _params.append((plugin_id, *_dt))
        if role_on:
            # v4.6.48：角色名与第一排共用同一套类型开关（disabled_types 同样作用于角色）
            _c = ("SELECT item_id, server_id FROM person WHERE plugin_id=? "
                  "AND role_before<>'' AND (role_after='' OR role_after IS NULL OR role_after=role_before)")
            if _dt:
                _marks = ",".join("?" * len(_dt))
                _c += f" AND (person_type IS NULL OR person_type='' OR person_type NOT IN ({_marks}))"
            _c += _scope + _ex
            _conds.append(_c)
            _params.append((plugin_id, *_dt))
        if not _conds:
            return 0
        try:
            _flat: List[Any] = []
            for _p in _params:
                _flat.extend(_p)
            _row = _q1("SELECT COUNT(*) AS c FROM (" + " UNION ".join(_conds) + ")", tuple(_flat))
            return int((_row or {}).get("c") or 0)
        except Exception:
            return 0

    def pending_items_list(self, *, plugin_id: str, scan_mode: Optional[str] = None,
                           person_on: bool = True, role_on: bool = True,
                           disabled_types: Optional[list] = None,
                           exclude_episodes: bool = False,
                           limit: int = 20, db: Optional[Any] = None) -> list:
        """库内「没翻完」的条目标题列表 —— 与 pending_items_count 完全同口径
        （仍未翻译判定 / scan_mode / person_on / role_on / disabled_types / exclude_episodes 一致），
        按 (item_id, server_id) 去重、取 MAX(title)，供「库」页徽章悬浮列出「到底是哪个」。
        :return: [{"item_id": str, "server_id": str, "title": str}, ...]（上限 limit 条）
        """
        _scope = _scan_scope_sql(scan_mode)
        _ex = _excl_ep_sql(exclude_episodes)
        _conds: List[str] = []
        _params: List[Any] = []
        _dt = [str(t) for t in (disabled_types or []) if str(t or "").strip()]
        if person_on:
            _c = ("SELECT item_id, server_id, " + _SQL_ITEM_TITLE + " AS title FROM person WHERE plugin_id=? "
                  "AND name_before<>'' AND (name_after='' OR name_after IS NULL OR name_after=name_before)")
            if _dt:
                _marks = ",".join("?" * len(_dt))
                _c += f" AND (person_type IS NULL OR person_type='' OR person_type NOT IN ({_marks}))"
            _c += _scope + _ex
            _c += " GROUP BY item_id, server_id"
            _conds.append(_c)
            _params.append((plugin_id, *_dt))
        if role_on:
            _c = ("SELECT item_id, server_id, " + _SQL_ITEM_TITLE + " AS title FROM person WHERE plugin_id=? "
                  "AND role_before<>'' AND (role_after='' OR role_after IS NULL OR role_after=role_before)")
            if _dt:
                _marks = ",".join("?" * len(_dt))
                _c += f" AND (person_type IS NULL OR person_type='' OR person_type NOT IN ({_marks}))"
            _c += _scope + _ex
            _c += " GROUP BY item_id, server_id"
            _conds.append(_c)
            _params.append((plugin_id, *_dt))
        if not _conds:
            return []
        try:
            _flat: List[Any] = []
            for _p in _params:
                _flat.extend(_p)
            _limit = max(1, min(100, int(limit or 20)))
            _sql = ("SELECT item_id, server_id, MAX(title) AS title FROM ("
                    + " UNION ".join(_conds)
                    + f") GROUP BY item_id, server_id ORDER BY title LIMIT {_limit}")
            rows = _q(_sql, tuple(_flat))
            return [
                {"item_id": str(r.get("item_id") or ""),
                 "server_id": str(r.get("server_id") or ""),
                 "title": str(r.get("title") or str(r.get("item_id") or "") or "(无标题)")}
                for r in rows
            ]
        except Exception:
            return []


    def force_item_terms(self, *, plugin_id: str, item_id: str, server_id: str = "",
                         limits: Optional[dict] = None,
                         only_pending: bool = False,
                         exclude_episodes: bool = False,
                         db: Optional[Any] = None) -> dict:
        """「重新翻译」用：单个条目在「人数上限（每文件 / 每类型前 N）」约束下应重翻的词条。
        与 _pending_kind_sql 同一套 kind/lvl 映射与 ROW_NUMBER 排序口径，
        但不要求「未翻译」（强制重翻：含已译词条）。
        **两排同口径**：角色名同样按「每文件每类型前 N 个」过滤（v4.6.48）。
        数字语义：N<=0 / 留空 = 不限（该类型全部）。
        exclude_episodes（v4.6.68）—— 「处理单集」=关时排除 Episode 层级行（翻译门禁一致）。
        返回 {"names": [(name_before, person_type)], "roles": [(role_before, person_type)]}（去重、保序）。
        """
        _sc, _scp = _scope_sql(server_id)
        _ex = _excl_ep_sql(exclude_episodes)
        _base = "FROM person WHERE plugin_id=? AND item_id=?" + _sc + _ex
        _args = (plugin_id, item_id, *_scp)

        def _ranked(col: str) -> str:
            _after = "role_after" if col == "role_before" else "name_after"
            _p = f" AND ({_after}='' OR {_after} IS NULL OR {_after}={col})" if only_pending else ""
            # 人数上限按「人」计数、两排共用（角色名同样按「每文件每类型前 N 个」）
            if not limits:
                return f"SELECT {col} AS term, person_type " + _base + f" AND {col}<>''" + _p
            _kind_case = self._PENDING_KEY_CASE.format(c="person_type")
            _lvl_case = ("CASE WHEN item_type='Series' THEN 'tvshow' "
                         "WHEN item_type='Episode' THEN 'episode' ELSE 'movie' END")
            _whens: List[str] = []
            for _lvl in ("movie", "tvshow", "episode"):
                _lm = limits.get(_lvl) or {}
                for _kind in ("actor", "guest", "director", "writer", "producer"):
                    _lk = "writer" if _kind == "producer" else _kind
                    _n = int(_lm.get(_lk, 0) or 0) or self._LIM_UNLIMITED
                    _whens.append(f"WHEN lvl='{_lvl}' AND kind='{_kind}' THEN {_n}")
            _lim_case = "CASE " + " ".join(_whens) + f" ELSE {self._LIM_UNLIMITED} END"
            return ("SELECT term, person_type FROM ("
                    f"SELECT {col} AS term, person_type, ROW_NUMBER() OVER ("
                    "PARTITION BY season_num, episode_num, kind ORDER BY person_index, id) AS rn, "
                    + _lim_case + " AS lim FROM ("
                    f"SELECT {col}, person_type, season_num, episode_num, person_index, id, "
                    + _lvl_case + " AS lvl, " + _kind_case + " AS kind " + _base + f" AND {col}<>''" + _p
                    + ") b) r WHERE rn <= lim")

        def _dedup(pairs):
            out, seen = [], set()
            for _t, _pt in pairs:
                if _t in seen:
                    continue
                seen.add(_t)
                out.append((_t, _pt))
            return out

        names: List[tuple] = []
        roles: List[tuple] = []
        try:
            for _r in _q(_ranked("name_before"), _args):
                _t = str(_r.get("term") or "").strip()
                if _t:
                    names.append((_t, str(_r.get("person_type") or "Actor").strip() or "Actor"))
            for _r in _q(_ranked("role_before"), _args):
                _t = str(_r.get("term") or "").strip()
                if _t:
                    roles.append((_t, str(_r.get("person_type") or "Actor").strip() or "Actor"))
        except Exception:
            return {"names": [], "roles": []}
        return {"names": _dedup(names), "roles": _dedup(roles)}


    def translated_map(self, *, plugin_id: str, names: Optional[list] = None,
                       roles: Optional[list] = None, db: Optional[Any] = None) -> dict:
        """取这些词条在库中已有的译文 —— 自动流水线（扫描/Webhook/探测）不调 LLM 时的
        「现成译文」来源（同一演员跨作品不再重复翻）。同一原文有多个译文时取出现次数最多的一个。
        :return: {"names": {原文: 译文}, "roles": {原文: 译文}}
        """
        def _map_of(col_before: str, col_after: str, terms) -> dict:
            out: Dict[str, str] = {}
            _ts = [str(t) for t in (terms or []) if str(t or "").strip()]
            for _i in range(0, len(_ts), 80):
                chunk = _ts[_i:_i + 80]
                marks = ",".join("?" * len(chunk))
                rows = _q(
                    f"SELECT {col_before} AS o, {col_after} AS z, COUNT(*) AS c FROM person "
                    f"WHERE plugin_id=? AND {col_before} IN ({marks}) "
                    f"AND {col_after}<>'' AND {col_after}<>{col_before} "
                    f"GROUP BY {col_before}, {col_after} ORDER BY c DESC",
                    (plugin_id, *chunk))
                for r in rows:
                    _o = str(r.get("o") or "").strip()
                    _z = str(r.get("z") or "").strip()
                    if _o and _z and _o not in out:
                        out[_o] = _z
            return out

        try:
            return {"names": _map_of("name_before", "name_after", names),
                    "roles": _map_of("role_before", "role_after", roles)}
        except Exception:
            return {"names": {}, "roles": {}}


    def find_item_types_by_name(self, *, plugin_id: str, name: str,
                                db: Optional[Any] = None) -> list:
        """按人名从库反推人物类型（可能多类型，如既 Actor 又 Director）。
        人名池拉取过滤用：库里查不到类型的 Person 不入池。"""
        nm = str(name or "").strip()
        if not nm:
            return []
        try:
            rows = _q("SELECT DISTINCT person_type FROM person WHERE plugin_id=? "
                      "AND (name_before=? OR name_after=?)", (plugin_id, nm, nm))
            out = []
            for r in rows:
                t = str(r.get("person_type") or "").strip()
                if t and t not in out:
                    out.append(t)
            return out
        except Exception:
            return []

    def item_pending_summary(self, *, plugin_id: str, item_id: str, server_id: str = "",
                             db: Optional[Any] = None) -> dict:
        """某条目待翻统计（写回就绪判定的原语，配置过滤由插件层叠加）：
        {'names': {person_type: n}, 'roles': n}。"""
        try:
            n_rows = _q(
                "SELECT person_type, COUNT(*) AS c FROM person WHERE plugin_id=? AND item_id=? AND server_id=? "
                "AND name_before<>'' AND (name_after='' OR name_after IS NULL OR name_after=name_before) "
                "GROUP BY person_type", (plugin_id, item_id, server_id))
            r = _q1(
                "SELECT COUNT(*) AS c FROM person WHERE plugin_id=? AND item_id=? AND server_id=? "
                "AND role_before<>'' AND (role_after='' OR role_after IS NULL OR role_after=role_before)",
                (plugin_id, item_id, server_id))
            return {
                "names": {str(x.get("person_type") or "Actor"): int(x.get("c") or 0) for x in n_rows},
                "roles": int((r or {}).get("c") or 0),
            }
        except Exception:
            return {"names": {}, "roles": 0}

    def items_for_terms(self, *, plugin_id: str, names: Optional[list] = None,
                        roles: Optional[list] = None, db: Optional[Any] = None) -> list:
        """返回包含这些「刚翻译词条」的条目清单（item_id/server_id 去重）。
        翻译 worker 每轮翻译成功写入 DB 后调用，把「有新译文的条目」登记为写回候选。
        只匹配仍处待翻状态的行（UPDATE 的同一谓词）—— 词条若早已有译文则不会返回，
        因此每次返回都意味着该条目确实发生了译文变化。"""
        out: List[dict] = []
        seen = set()

        def _collect(terms, col: str) -> None:
            _after = col.replace("_before", "_after")
            _ts = [str(t) for t in (terms or []) if str(t or "").strip()]
            for _i in range(0, len(_ts), 80):
                chunk = _ts[_i:_i + 80]
                marks = ",".join("?" * len(chunk))
                rows = _q(
                    f"SELECT DISTINCT item_id, server_id FROM person WHERE plugin_id=? "
                    f"AND {col} IN ({marks}) AND {col}<>'' "
                    f"AND ({_after}='' OR {_after} IS NULL OR {_after}={col})",
                    (plugin_id, *chunk))
                for r in rows:
                    _k = (str(r.get("item_id") or ""), str(r.get("server_id") or ""))
                    if _k[0] and _k not in seen:
                        seen.add(_k)
                        out.append({"item_id": _k[0], "server_id": _k[1]})

        try:
            _collect(names, "name_before")
            _collect(roles, "role_before")
        except Exception:
            pass
        return out

    def pending_terms_of_item(self, *, plugin_id: str, item_id: str, server_id: str = "",
                              exclude_episodes: bool = False,
                              db: Optional[Any] = None) -> list:
        """某条目仍待翻的词条明细（含类型）—— 写回「就绪」统一判定用。
        返回 [{'kind': 'name'|'role', 'term': 原文, 'person_type': 类型}]；
        配置过滤 / 失败排除 / AI 开关的判断在插件层（translation_pending_for_item）。
        exclude_episodes（v4.6.68）—— 「处理单集」=关时 Episode 层级行不产生待翻词条
        （否则集记录永远「未翻完」，写回就绪永不通过）。"""
        rows = _q("SELECT person_type, name_before, name_after, role_before, role_after FROM person "
                  "WHERE plugin_id=? AND item_id=? AND server_id=?"
                  + _excl_ep_sql(exclude_episodes), (plugin_id, item_id, server_id))
        out: List[dict] = []
        for r in rows:
            pt = str(r.get("person_type") or "Actor")
            nb = str(r.get("name_before") or "").strip()
            na = str(r.get("name_after") or "").strip()
            rb = str(r.get("role_before") or "").strip()
            ra = str(r.get("role_after") or "").strip()
            if nb and (not na or na == nb):
                out.append({"kind": "name", "term": nb, "person_type": pt})
            if rb and (not ra or ra == rb):
                out.append({"kind": "role", "term": rb, "person_type": pt})
        return out

    def find_pending_items(self, *, plugin_id: str, limit: int = 500,
                           exclude_episodes: bool = False,
                           db: Optional[Any] = None) -> list:
        """存在待翻词条（人名或角色）的条目清单（item_id/server_id 去重）。
        写回 worker 扫描「刚好翻完」的条目用；就绪判定由插件层按配置复核。
        exclude_episodes（v4.6.68）—— 「处理单集」=关时 Episode 条目不会进入本清单
        （它们不参与翻译，name_after 永远为空，否则会被写回 worker 无限重拾）。"""
        try:
            rows = _q(
                "SELECT item_id, server_id, MAX(item_type) AS item_type, "
                + _SQL_ITEM_TITLE + " AS title "
                "FROM person WHERE plugin_id=? AND ("
                "  (name_before<>'' AND (name_after='' OR name_after IS NULL OR name_after=name_before)) OR "
                "  (role_before<>'' AND (role_after='' OR role_after IS NULL OR role_after=role_before))"
                ")" + _excl_ep_sql(exclude_episodes) + " GROUP BY item_id, server_id LIMIT ?",
                (plugin_id, int(limit)))
            return [{
                "item_id": str(r.get("item_id") or ""),
                "server_id": str(r.get("server_id") or ""),
                "item_type": str(r.get("item_type") or ""),
                "title": str(r.get("title") or ""),
            } for r in rows]
        except Exception:
            return []

    # ── 第二排角色跨集复用（v4.6.70 · 报告第二十~三十四节）──
    _ROLE_SRC_RANK = {"manual": 5, "llm": 4, "tmdb": 3, "zhconv": 2, "reused": 1}

    def role_memory_get(self, *, plugin_id: str, keys: list, db: Optional[Any] = None) -> dict:
        """批量取「同剧角色翻译记忆」。

        :param keys: [(server_id, series_id, role_original), ...]
        :return: {(server_id, series_id, role_original): (role_translated, source)}
        作用域 = (server_id, series_id)：同一角色名在不同作品可有不同译文，互不串用
        （Guardian 在 A 剧=守护者、B 剧=守门人 可并存）。series_id 为空时退化为
        「该服务器全局角色记忆」（仍好于完全无记忆）。
        """
        out: dict = {}
        _ks = [k for k in (keys or []) if k and len(k) >= 3 and str(k[2] or "").strip()]
        if not _ks:
            return out
        try:
            for _i in range(0, len(_ks), 60):
                _chunk = _ks[_i:_i + 60]
                _conds: List[str] = []
                _args: List[Any] = [plugin_id]
                for _sid, _ser, _ro in _chunk:
                    _conds.append("(server_id=? AND series_id=? AND role_original=?)")
                    _args.extend([str(_sid or ""), str(_ser or ""), str(_ro)])
                rows = _q("SELECT server_id, series_id, role_original, role_translated, source "
                          "FROM role_memory WHERE plugin_id=? AND (" + " OR ".join(_conds) + ")",
                          tuple(_args))
                for r in rows:
                    _zh = str(r.get("role_translated") or "").strip()
                    if not _zh:
                        continue
                    out[(str(r.get("server_id") or ""), str(r.get("series_id") or ""),
                         str(r.get("role_original") or ""))] = (_zh, str(r.get("source") or "llm"))
        except Exception as e:
            logger.warning(f"[DB] role_memory_get 失败: {e}")
        return out

    def role_memory_put(self, *, plugin_id: str, rows: list, db: Optional[Any] = None) -> int:
        """批量写「同剧角色翻译记忆」。**源优先级** manual > llm > tmdb > zhconv > reused ——
        低优先级不覆盖高优先级（人工修正永不被 AI 结果改写）。
        rows: [{server_id, series_id, series_name, role_original, role_translated, source}]
        :return: 实际写入/更新行数
        """
        _rank = self._ROLE_SRC_RANK
        _n = 0
        _ts = _now()
        try:
            with _conn_lock:
                conn = _get_conn()
                for r in (rows or []):
                    _r = r or {}
                    _ro = str(_r.get("role_original") or "").strip()
                    _zh = str(_r.get("role_translated") or "").strip()
                    if not _ro or not _zh or _zh == _ro:
                        continue
                    _src = str(_r.get("source") or "llm").strip().lower() or "llm"
                    if _src not in _rank:
                        _src = "llm"
                    _sid = str(_r.get("server_id") or "")
                    _ser = str(_r.get("series_id") or "")
                    _sn = str(_r.get("series_name") or "")
                    try:
                        _cur = conn.execute(
                            "SELECT source FROM role_memory WHERE plugin_id=? AND server_id=? "
                            "AND series_id=? AND role_original=?",
                            (plugin_id, _sid, _ser, _ro)).fetchone()
                    except Exception:
                        _cur = None
                    if _cur is not None:
                        try:
                            _cs = str(_cur["source"] if isinstance(_cur, dict) else _cur[0] or "")
                        except Exception:
                            _cs = ""
                        if _rank.get(_cs, 0) > _rank.get(_src, 0):
                            continue   # 现有来源优先级更高 → 不覆盖（人工优先）
                    conn.execute(
                        "INSERT INTO role_memory (plugin_id, server_id, series_id, series_name, "
                        "role_original, role_translated, source, updated_at) VALUES (?,?,?,?,?,?,?,?) "
                        "ON CONFLICT(plugin_id, server_id, series_id, role_original) DO UPDATE SET "
                        "role_translated=excluded.role_translated, source=excluded.source, "
                        "series_name=excluded.series_name, updated_at=excluded.updated_at",
                        (plugin_id, _sid, _ser, _sn, _ro, _zh, _src, _ts))
                    _n += 1
                conn.commit()
        except Exception as e:
            logger.warning(f"[DB] role_memory_put 失败: {e}")
        return _n

    def role_memory_delete_series(self, *, plugin_id: str, server_id: str = "", series_id: str = "",
                                  series_name: str = "", db: Optional[Any] = None) -> int:
        """清除某剧的角色翻译记忆 —— **仅由显式「清除该剧翻译记忆」调用**。

        删除某集 / 整剧删除 / 删除恢复 / 清空翻译记录都**不**调用本方法：
        记忆必须跨洗版存活（重建后直接复用旧译文）。
        """
        _conds = ["plugin_id=?"]
        _args: List[Any] = [plugin_id]
        _sid = str(server_id or "")
        _ser = str(series_id or "")
        _sn = str(series_name or "").strip()
        if _ser:
            _conds.append("series_id=?")
            _args.append(_ser)
            if _sid:
                _conds.append("server_id=?")
                _args.append(_sid)
        elif _sn:
            _conds.append("series_name=?")
            _args.append(_sn)
            if _sid:
                _conds.append("server_id=?")
                _args.append(_sid)
        else:
            return 0
        try:
            return _x("DELETE FROM role_memory WHERE " + " AND ".join(_conds), tuple(_args))
        except Exception as e:
            logger.warning(f"[DB] role_memory_delete_series 失败: {e}")
            return 0

    def role_memory_stats(self, *, plugin_id: str, db: Optional[Any] = None) -> dict:
        """角色记忆统计（总数 + 按来源分布），供 UI / 日志展示。"""
        try:
            _row = _q1("SELECT COUNT(*) AS c FROM role_memory WHERE plugin_id=?", (plugin_id,))
            rows = _q("SELECT source, COUNT(*) AS c FROM role_memory WHERE plugin_id=? GROUP BY source",
                      (plugin_id,))
            return {"total": int((_row or {}).get("c") or 0),
                    "by_source": {str(r.get("source") or ""): int(r.get("c") or 0) for r in rows}}
        except Exception:
            return {"total": 0, "by_source": {}}

    def role_memory_of_item(self, *, plugin_id: str, item_id: str, server_id: str = "",
                            db: Optional[Any] = None) -> list:
        """某剧（item_id = 剧媒体身份）的角色翻译记忆明细，供库页展示。"""
        try:
            _conds = ["plugin_id=?", "series_id=?"]
            _args: List[Any] = [plugin_id, str(item_id or "")]
            _sid = str(server_id or "")
            if _sid:
                _conds.append("(server_id=? OR server_id='')")
                _args.append(_sid)
            rows = _q("SELECT server_id, series_name, role_original, role_translated, source, updated_at "
                      "FROM role_memory WHERE " + " AND ".join(_conds) + " ORDER BY role_original",
                      tuple(_args))
            return [{"server_id": str(r.get("server_id") or ""),
                     "series_name": str(r.get("series_name") or ""),
                     "role_original": str(r.get("role_original") or ""),
                     "role_translated": str(r.get("role_translated") or ""),
                     "source": str(r.get("source") or ""),
                     "updated_at": str(r.get("updated_at") or "")} for r in rows]
        except Exception:
            return []

    def batch_apply_translations(self, *, plugin_id: str, name_map: dict, role_map: dict,
                                 db: Optional[Any] = None) -> int:
        """把翻译映射批量写回库（不碰文件）—— 仅更新尚未翻译的占位行
        （name_after 为空或等于原文），已有人工修正/译文的行不覆盖。
        :return: 更新行数
        """
        n = 0
        try:
            for orig, zh in (name_map or {}).items():
                if not orig or not zh or zh == orig:
                    continue
                n += _x(
                    "UPDATE person SET name_after=?, translated_at=? "
                    "WHERE plugin_id=? AND name_before=? "
                    "AND (name_after='' OR name_after IS NULL OR name_after=name_before)",
                    (zh, _now(), plugin_id, orig))
            for orig, zh in (role_map or {}).items():
                if not orig or not zh or zh == orig:
                    continue
                n += _x(
                    "UPDATE person SET role_after=?, translated_at=? "
                    "WHERE plugin_id=? AND role_before=? "
                    "AND (role_after='' OR role_after IS NULL OR role_after=role_before)",
                    (zh, _now(), plugin_id, orig))
        except Exception as e:
            logger.warning(f"[DB] batch_apply_translations 失败: {e}")
        return n

    def apply_translations_occurrence(self, *, plugin_id: str, rows: list,
                                      override: bool = False,
                                      db: Optional[Any] = None) -> int:
        """occurrence 级精确写库（v4.6.64 · P0 数据一致性）。

        每条译文按 **occurrence 精确定位键**更新：
          plugin_id + server_id + item_id + season_num + episode_num + person_index + kind + 原文
        （season/episode 用 COALESCE 做 NULL 安全比较）

        为什么必须这样：不同作品的同名人物/角色**并不一定需要相同译法**；此前普通批量翻译用
        `WHERE plugin_id=? AND name_before=?`（全局按原文）→ 作品 A 的译文会把作品 B 的同名行
        一起改掉，且 B 未登记写回 → 库与 NFO 不一致（报告 P0/P1-DB-01）。
        rows: [{"kind","original_text","translation","item_id","server_id",
                "season_num","episode_num","person_index"}...]
        :return: 实际更新行数
        """
        n = 0
        _ts = _now()
        for r in (rows or []):
            if not isinstance(r, dict):
                continue
            _t = str(r.get("original_text") or "").strip()
            _z = str(r.get("translation") or "").strip()
            if not _t or not _z or _z == _t:
                continue
            _kind = "role" if str(r.get("kind")) == "role" else "name"
            _col = "role_before" if _kind == "role" else "name_before"
            _after = "role_after" if _kind == "role" else "name_after"
            # override=True（强制重翻）：覆盖已有译文；否则只补「尚未翻译」的行
            _guard = "" if override else f" AND ({_after}='' OR {_after} IS NULL OR {_after}={_col})"
            try:
                n += _x(
                    f"UPDATE person SET {_after}=?, translated_at=? "
                    f"WHERE plugin_id=? AND server_id=? AND item_id=? "
                    f"AND COALESCE(season_num,-1)=COALESCE(?,-1) "
                    f"AND COALESCE(episode_num,-1)=COALESCE(?,-1) "
                    f"AND person_index=? AND {_col}=?" + _guard,
                    (_z, _ts, plugin_id, str(r.get("server_id") or ""), str(r.get("item_id") or ""),
                     r.get("season_num"), r.get("episode_num"),
                     int(r.get("person_index") or 0), _t))
            except Exception as e:
                logger.warning(f"[DB] occurrence 写库失败: {e}")
        return n

    def delete_by_nfo_path_prefix(self, *, plugin_id: str, path_prefix: str,
                                  db: Optional[Any] = None) -> int:
        """删除 nfo_path 位于指定目录（含子目录）之下的全部记录 ——
        供「排除目录」清理已入库旧记录使用。
        路径分隔符归一到 '/'；必须是完整绝对路径（如 /media/示例库/排除目录），
        否则不误杀（只匹配自身与直接子路径）。
        """
        _p = str(path_prefix or "").replace("\\", "/").rstrip("/")
        if not _p or not (_p.startswith("/") or (_p[1:2] == ":" and _p[0].isalpha())):
            return 0  # 拒绝相对路径，防止误删
        esc = _p.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        return _x(
            "DELETE FROM person WHERE plugin_id=? AND ("
            "replace(nfo_path, '\\', '/') = ? OR "
            "replace(nfo_path, '\\', '/') LIKE ? ESCAPE '\\')",
            (plugin_id, _p, esc + "/%"),
        )

    def clear_all(self, *, plugin_id: str, db: Optional[Any] = None) -> int:
        return _x("DELETE FROM person WHERE plugin_id=?", (plugin_id,))

    def clear_by_source(self, *, plugin_id: str, nfo_only: bool,
                        db: Optional[Any] = None) -> int:
        if nfo_only:
            return _x("DELETE FROM person WHERE plugin_id=? AND server_id=''", (plugin_id,))
        return _x("DELETE FROM person WHERE plugin_id=? AND server_id<>''", (plugin_id,))

    def export_all(self, *, plugin_id: str, db: Optional[Any] = None) -> list:
        rows = _q("SELECT * FROM person WHERE plugin_id=?", (plugin_id,))
        return [{
            "plugin_id": r.get("plugin_id"), "server_id": r.get("server_id"),
            "item_id": r.get("item_id"), "item_type": r.get("item_type"),
            "title": r.get("title"), "series_name": r.get("series_name"),
            "season_num": r.get("season_num"), "episode_num": r.get("episode_num"),
            "library_name": r.get("library_name"), "person_index": r.get("person_index"),
            "person_type": r.get("person_type"), "name_before": r.get("name_before"),
            "name_after": r.get("name_after"), "role_before": r.get("role_before"),
            "role_after": r.get("role_after"), "translated_at": r.get("translated_at"),
            "nfo_path": r.get("nfo_path") or "", "deleted_at": r.get("deleted_at") or "",
        } for r in rows]

    def import_rows(self, *, plugin_id: str, rows: list, db: Optional[Any] = None) -> int:
        """去重键改行级（server, item, 季, 集, 序号）—— 此前按 (server, item)
        去重，同一条目的第 2..N 行全被跳过，备份恢复只剩每人第一行。
        P2: 单事务 executemany 批写（先一次性 SELECT 现有键到内存）。
        deleted_at 随导出恢复（观察期状态一并还原）。"""
        _pid = plugin_id
        existing = set()
        try:
            for r in _q("SELECT server_id, item_id, season_num, episode_num, person_index "
                        "FROM person WHERE plugin_id=?", (_pid,)):
                existing.add((str(r.get("server_id") or ""), str(r.get("item_id") or ""),
                              r.get("season_num"), r.get("episode_num"),
                              int(r.get("person_index") or 0)))
        except Exception as e:
            logger.warning(f"[DB] import_rows 读取现有键失败: {e}")
        batch = []
        for p in rows or []:
            if not isinstance(p, dict):
                continue
            itm = str(p.get("item_id") or "").strip()
            if not itm:
                continue
            svr = str(p.get("server_id") or "")
            key = (svr, itm, p.get("season_num"), p.get("episode_num"),
                   int(p.get("person_index") or 0))
            if key in existing:
                continue
            existing.add(key)
            batch.append(
                (_pid, svr, itm, str(p.get("item_type") or ""), str(p.get("title") or ""),
                 str(p.get("series_name") or ""), p.get("season_num"), p.get("episode_num"),
                 str(p.get("library_name") or ""), int(p.get("person_index") or 0),
                 str(p.get("person_type") or "Actor"), str(p.get("name_before") or ""),
                 str(p.get("name_after") or ""), str(p.get("role_before") or ""),
                 str(p.get("role_after") or ""), str(p.get("translated_at") or ""),
                 str(p.get("nfo_path") or ""), str(p.get("deleted_at") or "")),
            )
        if not batch:
            return 0
        with _conn_lock:
            conn = _get_conn()
            try:
                conn.executemany(
                    "INSERT INTO person (plugin_id, server_id, item_id, item_type, title, series_name, "
                    "season_num, episode_num, library_name, person_index, person_type, name_before, "
                    "name_after, role_before, role_after, translated_at, nfo_path, deleted_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
        return len(batch)


# ---------------- 人名池（name_map） ----------------

_SRC_PRIORITY = {"manual": 3, "tmdb": 2, "llm": 1, "zhconv": 0}



def _is_kana_text(s: str) -> bool:
    """假名检测（平假名 U+3041–U+309F / 片假名 U+30A0–U+30FF）。
    日语人名常含汉字（水桥 かおり、楠木ともり）—— 只看「有没有汉字」会把它们误判成
    「已是中文」，池里显示「无需操作」并跳过 TMDB/AI。含假名一律视为仍需翻译。
    与下方 SQL 片段使用相同码位区间，保证 Python 推导与 SQL 统计一致。"""
    return any(("\u3041" <= ch <= "\u309f") or ("\u30a0" <= ch <= "\u30ff")
               for ch in str(s or ""))


def _is_spaced_cjk_name(s: str) -> bool:
    """汉字名中夹空格（半角空格 / 全角空格 U+3000 / 其它 Unicode 空白）。

    v4.6.80 起**不再作为「是否已是中文」的排除条件**（用户实测：中文名里带个空格
    也被判成待翻译，永远翻不动还重复调 AI）—— 本函数仅为兼容保留。
    """
    _t = str(s or "").strip()
    if not _t:
        return False
    if not any("\u4e00" <= ch <= "\u9fff" for ch in _t):
        return False
    return len(_t.split()) > 1


def _is_chinese_text(s: str) -> bool:
    """中文（CJK 统一表意文字 U+4E00–U+9FFF）检测。

    v4.6.80（用户实测口径修正）：**含汉字且无假名 → 视为已是中文**。
    此前把「汉字夹空格」（「角田 雄二郎」——姓 名的日文写法）排除在中文之外，
    导致它被判「待翻译」，但繁简转换又是空操作、AI 也多半原样返回 →
    永远停在「待翻译」并每轮重复调 AI（用户实测：明明就是中文里多了个空格）。
    现在空格不再作为排除条件；**含假名的仍不算中文**（「水桥 かおり」仍需翻译）。
    与下方 SQL 片段使用相同的码位规则，保证「Python 推导」与「SQL 统计」判定一致。"""
    _s = str(s or "")
    if not any("\u4e00" <= ch <= "\u9fff" for ch in _s):
        return False
    return not _is_kana_text(_s)


_SQL_HAS_KANA = "(name_original GLOB '*[ぁ-ゟ]*' OR name_original GLOB '*[゠-ヿ]*')"
_SQL_HAS_NAME_SPACE = "(name_original LIKE '% %' OR name_original LIKE '%　%')"
# v4.6.80（口径修正）：含汉字且无假名即视为「已是中文」—— 空格不再是排除条件
# （「角田 雄二郎」这类中文里带空格的名字此前被判「待翻译」，永远翻不动还重复调 AI）。
_SQL_IS_ZH = f"((name_original GLOB '*[一-鿿]*' AND NOT {_SQL_HAS_KANA}))"
_SQL_ZH_HAS_KANA = "(name_zh GLOB '*[ぁ-ゟ]*' OR name_zh GLOB '*[゠-ヿ]*')"
_SQL_ZH_VALID = (f"(name_zh IS NOT NULL AND name_zh<>'' AND name_zh<>name_original "
                 f"AND NOT {_SQL_ZH_HAS_KANA})")
_SQL_NO_CHANGE = f"(NOT {_SQL_ZH_VALID} AND {_SQL_IS_ZH})"
_SQL_TARGET = (f"(CASE WHEN {_SQL_ZH_VALID} THEN name_zh "
               f"WHEN {_SQL_IS_ZH} THEN name_original ELSE '' END)")
_SQL_TRANS_PENDING = f"(NOT {_SQL_ZH_VALID} AND NOT {_SQL_IS_ZH})"
_SQL_CUR_UNKNOWN = "(name_current IS NULL OR name_current='')"
_SQL_SYNCED = f"({_SQL_TARGET}<>'' AND name_current<>'' AND name_current={_SQL_TARGET})"
# v4.6.93（口径修正）：同步维度只在「有东西可同步」时算待同步 ——
#   ① Emby 当前名已知且 ≠ 目标名 → 待同步（含「原文已是中文 + 当前名不同」）；
#   ② Emby 当前名未知（空：扫描缓存行/无 Emby 身份）→ 只有「有真译文」才待同步（等写回 Emby）；
#      原文已是中文（目标名 = 原文）时无所可同步 → 不再报待同步（显示「无需操作」）。
# 此前「当前名未知」一律判待同步 → 「阿澄 佳奈」这类已中文扫描缓存行常驻🟡待同步（用户实测困惑）。
_SQL_SYNC_PENDING = (f"({_SQL_TARGET}<>'' AND COALESCE(sync_status,'')<>'failed' AND "
                     f"(({_SQL_CUR_UNKNOWN} AND {_SQL_ZH_VALID}) "
                     f"OR (NOT {_SQL_CUR_UNKNOWN} AND name_current<>{_SQL_TARGET})))")
_SQL_SYNC_FAILED = (f"({_SQL_TARGET}<>'' AND (name_current IS NULL OR name_current='' "
                    f"OR name_current<>{_SQL_TARGET}) AND sync_status='failed')")


def pool_target_name(rec: dict) -> str:
    """池条目的目标名 —— 有效译文优先；无译文但原文已是中文 → 原文；否则空（仍需翻译）。
    含假名的 name_zh 不算有效译文（早期版本可能把 TMDB 日文别名当成中文名写入）。"""
    orig = str((rec or {}).get("name_original") or "").strip()
    zh = str((rec or {}).get("name_zh") or "").strip()
    if zh and zh != orig and not _is_kana_text(zh):
        return zh
    if _is_chinese_text(orig):
        return orig
    return ""


def derive_pool_status(rec: dict) -> dict:
    """由事实（name_original / name_zh / name_current）推导池状态，
    两个维度完全独立，不再长期相信旧 status：
    - translation ∈ {pending, no_change, translated, failed}
    - sync        ∈ {pending, synced, failed, unknown}
    - ui          组合显示串（待翻译/同步失败/待同步/无需操作/已同步）
    目标名见 pool_target_name；「原文已是中文」= no_change，若 Emby 当前名≠目标名则同步态仍为 pending（文档 §十二）。
    v4.6.93：Emby 当前名未知（空）时，「原文已是中文」不再判 pending —— 扫描缓存行无可同步之物，
    只报「无需操作」（此前常驻🟡待同步）；「有真译文」的缓存行仍为 pending（等待写回 Emby）。
    """
    zh = str((rec or {}).get("name_zh") or "").strip()
    orig = str((rec or {}).get("name_original") or "").strip()
    cur = str((rec or {}).get("name_current") or "").strip()
    target = pool_target_name(rec)
    if target:
        translation = "translated" if (target == zh and zh != orig) else "no_change"
    elif str((rec or {}).get("translation_status") or "") == "failed":
        translation = "failed"
    else:
        translation = "pending"
    if not target:
        sync = "unknown"
    elif cur and cur == target:
        sync = "synced"
    elif str((rec or {}).get("sync_status") or "") == "failed":
        sync = "failed"
    elif not cur and translation == "no_change":
        # v4.6.93：原文已是中文 + Emby 当前名未知（扫描缓存行/无 Emby 身份）→ 无同步可言（不报待同步）
        sync = "unknown"
    else:
        sync = "pending"
    if translation in ("pending", "failed"):
        ui = "待翻译"
    elif sync == "failed":
        ui = "同步失败"
    elif sync == "pending":
        ui = "待同步"
    elif translation == "no_change":
        # v4.6.94：文案改「无需操作」—— 原文已是中文的这类行不翻也不同步，什么都不用做；
        # 前端译名列也不再重复显示原文（只有「第一排改过」的才有译名，状态才变成待同步/已同步）。
        ui = "无需操作"
    else:
        ui = "已同步"
    if not str((rec or {}).get("emby_person_id") or "").strip():
        lifecycle = "unknown"
    else:
        lifecycle = str((rec or {}).get("pool_sync_state") or "active").strip() or "active"
    return {"translation": translation, "sync": sync, "ui": ui, "lifecycle": lifecycle}


class NameMapDb:
    """人名池数据访问（manual>llm>zhconv，低不覆盖高）。"""

    @staticmethod
    def ensure_table() -> None:
        try:
            _get_conn()
        except Exception as e:
            logger.warning(f"[NameMap] 初始化失败: {e}")

    # ── 读：全量加载（内存池）──
    def load_map(self, *, plugin_id: str, db: Optional[Any] = None) -> dict:
        """只返回「有效译文」行 —— 与 _SQL_ZH_VALID 同口径（name_zh 非空、
        不等于原文、且不含假名）。此前把含假名/等于原文的 name_zh 也当作命中，
        导致这些池行在翻译时被当成「池命中」而不重译，永远停留在 pending（死循环）。
        本方法返回的是【全局翻译记忆 (Translation Memory)】——
        键 = (name_type, name_original)，跨服务器聚合，不含 server_id。它只应作为
        「词条 → 译文」的记忆命中使用，**不得**被当作某台服务器的 Person 主数据
        （Person 主数据身份 = server_id + emby_person_id）。需要按身份隔离读 Person 译文时，
        请用 load_pool_identity_map()（优先身份，再 fallback 本全局 TM）。"""
        try:
            rows = _q("SELECT * FROM name_map WHERE plugin_id=?", (plugin_id,))
        except Exception as e:
            logger.warning(f"[NameMap] 加载失败: {e}")
            return {}
        return {
            (r.get("name_type"), r.get("name_original")): (r.get("name_zh"), r.get("source"))
            for r in rows
            if r.get("name_original") and r.get("name_zh")
            and str(r.get("name_zh")) != str(r.get("name_original"))
            and not _is_kana_text(r.get("name_zh"))
        }

    def load_pool_identity_map(self, *, plugin_id: str, db: Optional[Any] = None) -> dict:
        """Person 主数据的「身份维度」视图 —— 与 load_map() 的
        全局翻译记忆彻底分开（文档 §六：People Pool Person 键 = server_id + emby_person_id；
        Translation Memory 键 = name_type + name_original，两者不得混用）。
        只取带完整身份（server_id + emby_person_id 均非空）且译文有效的 person 行，返回：
          {"by_id":   {(server_id, emby_person_id): (name_zh, source)},
           "by_name": {(server_id, name_original):  (name_zh, source)}}
        by_id 供已知完整身份时的精确读取（池写回优先取「当前 Person 行」）；
        by_name 供已知服务器 + 原文名时的就地判定（写回就绪判定 server-aware）。
        同一键多行时按 source 优先级（manual>tmdb>llm>zhconv）取最强者，避免低级来源覆盖人工。"""
        out = {"by_id": {}, "by_name": {}}
        try:
            rows = _q("SELECT * FROM name_map WHERE plugin_id=? AND name_type='person' "
                      "AND server_id<>'' AND emby_person_id<>''", (plugin_id,))
        except Exception as e:
            logger.warning(f"[NameMap] 加载 Person 身份视图失败: {e}")
            return out

        def _better(cur, src) -> bool:
            return cur is None or _SRC_PRIORITY.get(src, 0) > _SRC_PRIORITY.get(str(cur[1] or ""), 0)

        for r in rows:
            orig = r.get("name_original")
            zh = r.get("name_zh")
            if not orig or not zh:
                continue
            _orig = str(orig)
            _zh = str(zh)
            if _zh == _orig or _is_kana_text(_zh):
                continue
            _src = str(r.get("source") or "")
            _sid = str(r.get("server_id") or "")
            _pid = str(r.get("emby_person_id") or "")
            _k_id = (_sid, _pid)
            if _better(out["by_id"].get(_k_id), _src):
                out["by_id"][_k_id] = (_zh, _src)
            _k_nm = (_sid, _orig)
            if _better(out["by_name"].get(_k_nm), _src):
                out["by_name"][_k_nm] = (_zh, _src)
        return out

    # ── 写：批量同步（新翻译回写池，低优先级不覆盖高）──
    def set_map_many(self, *, plugin_id: str, entries: list = None,
                     db: Optional[Any] = None) -> int:
        """单事务 batched 写入 —— 先一次性加载现有键到内存，
        避免每条 SELECT+INSERT+commit（2 次往返 + fsync），万级回写大幅加速。"""
        now = _now()
        try:
            cur_map = {}
            for r in _q("SELECT id, name_type, name_original, name_zh, source FROM name_map WHERE plugin_id=?",
                        (plugin_id,)):
                cur_map[(str(r.get("name_type") or ""), str(r.get("name_original") or ""))] = r
            ins, upd = [], []
            changed = 0
            seen = set()
            for e in entries or []:
                t = str(e.get("type") or "person")
                orig = str(e.get("original") or "").strip()
                zh = str(e.get("zh") or "").strip()
                src = str(e.get("source") or "zhconv").lower()
                if not orig or not zh:
                    continue
                _k = (t, orig)
                if _k in seen:
                    continue
                seen.add(_k)
                rec = cur_map.get(_k)
                if rec is None:
                    ins.append((plugin_id, t, orig, zh, src, now))
                    changed += 1
                else:
                    _old_zh = str(rec.get("name_zh") or "").strip()
                    _old_orig = str(rec.get("name_original") or "").strip()
                    _old_invalid = (not _old_zh) or (_old_zh == _old_orig) or _is_kana_text(_old_zh)
                    if _old_invalid or _SRC_PRIORITY.get(src, 0) >= _SRC_PRIORITY.get(str(rec.get("source") or ""), 0):
                        upd.append((zh, src, now, rec.get("id")))
                        changed += 1
            if not ins and not upd:
                return 0
            with _conn_lock:
                conn = _get_conn()
                try:
                    if ins:
                        conn.executemany(
                            "INSERT INTO name_map (plugin_id, name_type, name_original, name_zh, source, updated_at) "
                            "VALUES (?,?,?,?,?,?)", ins)
                    if upd:
                        conn.executemany(
                            "UPDATE name_map SET name_zh=?, source=?, updated_at=? WHERE id=?", upd)
                    conn.commit()
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    raise
            return changed
        except Exception as e:
            logger.warning(f"[NameMap] set_map_many 失败: {e}")
            return 0

    # ── 写：扫描/Webhook/探测库入库 → 按「翻译类型开关 + 人数上限」入池（人名池）──
    def add_pool_candidates(self, *, plugin_id: str, entries: list = None,
                            db: Optional[Any] = None) -> int:
        """把入库路径筛出的人名写入人名池（v4.6.44）。
        与既有写路径的区别：
          - set_map_many：要求 zh 非空 —— 无法登记「待翻译」占位行（扫描刚入库时还没有译文）；
          - upsert_pool_person：要求 emby_person_id —— 本地 NFO 扫描拿不到 Emby Person ID。
        本方法专为「扫描先把人名放进池、等翻译 worker 再翻」设计：
          - 允许 name_zh 为空（写入即 pending 待翻译，由 _translate_pending_round 消费）；
          - 无需 emby_person_id，落成「无 ID 缓存行」（server_id/emby_person_id 均空）；
            与 name_map 的「仅 emby_person_id 非空才唯一」索引不冲突（无 ID 行不参与唯一约束）；
          - 按 (name_type='person', name_original) 去重：同名已存在（无论带不带 ID）不新建，
            只合并 person_type/person_types 并补译文，避免池里出现重复人名；
          - name_zh 只增不覆盖 —— 不覆盖已有有效译文；低优先级来源不覆盖高优先级。
        entries: [{"original", "zh", "person_type", "source"}]
        :return: 新增 + 更新行数
        """
        now = _now()
        try:
            cand: dict = {}
            for e in entries or []:
                orig = str(e.get("original") or "").strip()
                if not orig:
                    continue
                pt = str(e.get("person_type") or "").strip()
                zh = str(e.get("zh") or "").strip()
                # v4.6.59：原文已是中文（如「上坂堇」）→ 目标名就是原文，直接落 name_zh，
                # 池里显示「译名 = 上坂堇」而不是「---」（与「拉取人名」路径一致）；
                # 含假名的日文名不算中文（_is_chinese_text 已排除）→ 仍显示待翻译；
                # v4.6.80：汉字夹空格（「角田 雄二郎」）现在**算**中文 → 直接落原名，不再挂待翻译。
                if not zh and _is_chinese_text(orig):
                    zh = orig
                src = str(e.get("source") or "scan").lower()
                rec = cand.get(orig)
                if rec is None:
                    cand[orig] = {"zh": zh, "src": src,
                                  "types": [pt] if pt else [], "ptype": pt}
                else:
                    if pt and pt not in rec["types"]:
                        rec["types"].append(pt)
                    if not rec["ptype"] and pt:
                        rec["ptype"] = pt
                    # zh 与 src 必须同进同退：取「更高优先级来源」的译文，
                    # 避免出现 src=manual 却存着 zhconv 译文的不一致（同批同名去重）。
                    if zh and (not rec["zh"]
                               or _SRC_PRIORITY.get(src, 0) > _SRC_PRIORITY.get(rec["src"], 0)):
                        rec["zh"] = zh
                        rec["src"] = src
            if not cand:
                return 0
            # 载入现有 Person 行（含带 ID 行）—— 同名不再新建，避免池里重复人名
            cur_map: dict = {}
            for r in _q("SELECT id, name_original, name_zh, source, person_type, person_types "
                        "FROM name_map WHERE plugin_id=? AND name_type='person'", (plugin_id,)):
                _o = str(r.get("name_original") or "").strip()
                if _o and _o not in cur_map:
                    cur_map[_o] = r
            ins, upd = [], []
            for orig, c in cand.items():
                _ptypes = json.dumps(list(dict.fromkeys(c["types"])), ensure_ascii=False) if c["types"] else ""
                rec = cur_map.get(orig)
                if rec is None:
                    ins.append((plugin_id, "person", orig, c["zh"], c["src"], now,
                                _ptypes, c["ptype"]))
                    continue
                _old_zh = str(rec.get("name_zh") or "").strip()
                _old_orig = str(rec.get("name_original") or "").strip()
                _old_invalid = (not _old_zh) or (_old_zh == _old_orig) or _is_kana_text(_old_zh)
                _exist_types: list = []
                try:
                    _json = json.loads(str(rec.get("person_types") or "") or "[]")
                    if isinstance(_json, list):
                        _exist_types = [str(x) for x in _json if str(x).strip()]
                except Exception:
                    _exist_types = []
                for _t in c["types"]:
                    if _t and _t not in _exist_types:
                        _exist_types.append(_t)
                _new_ptypes = json.dumps(_exist_types, ensure_ascii=False) if _exist_types else ""
                _ptype_keep = str(rec.get("person_type") or "") or c["ptype"]
                sets, params = [], []
                if _new_ptypes and _new_ptypes != str(rec.get("person_types") or ""):
                    sets.append("person_types=?")
                    params.append(_new_ptypes)
                if _ptype_keep and _ptype_keep != str(rec.get("person_type") or ""):
                    sets.append("person_type=?")
                    params.append(_ptype_keep)
                if c["zh"] and (_old_invalid
                                or _SRC_PRIORITY.get(c["src"], 0) >= _SRC_PRIORITY.get(str(rec.get("source") or ""), 0)):
                    sets.append("name_zh=?")
                    params.append(c["zh"])
                    sets.append("source=?")
                    params.append(c["src"])
                if not sets:
                    continue
                sets.append("updated_at=?")
                params.append(now)
                params.append(rec.get("id"))
                upd.append((f"UPDATE name_map SET {', '.join(sets)} WHERE id=?", tuple(params)))
            if not ins and not upd:
                return 0
            with _conn_lock:
                conn = _get_conn()
                try:
                    if ins:
                        conn.executemany(
                            "INSERT INTO name_map (plugin_id, name_type, name_original, name_zh, "
                            "source, updated_at, person_types, person_type) VALUES (?,?,?,?,?,?,?,?)", ins)
                    for _sql, _p in upd:
                        conn.execute(_sql, _p)
                    conn.commit()
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    raise
            return len(ins) + len(upd)
        except Exception as e:
            logger.warning(f"[NameMap] add_pool_candidates 失败: {e}")
            return 0

    # ── 读：分页查询（人名池管理）──
    def count_map(self, *, plugin_id: str, db: Optional[Any] = None) -> int:
        """人名池总数（/status 5s 轮询用）—— 一次 COUNT，省掉分页查询。"""
        try:
            r = _q1("SELECT COUNT(*) c FROM name_map WHERE plugin_id=?", (plugin_id,))
            return int((r or {}).get("c") or 0)
        except Exception:
            return 0

    def list_map(self, *, plugin_id: str, keyword: str = "", page: int = 1, size: int = 50,
                 db: Optional[Any] = None) -> dict:
        try:
            kw = (keyword or "").strip()
            where = "WHERE plugin_id=?"
            params: list = [plugin_id]
            if kw:
                where += " AND (name_original LIKE ? OR name_zh LIKE ?)"
                params += [f"%{kw}%", f"%{kw}%"]
            total = _q1(f"SELECT COUNT(*) AS c FROM name_map {where}", tuple(params))
            n = total.get("c") if total else 0
            offset = (max(1, int(page)) - 1) * max(1, int(size))
            rows = _q(
                f"SELECT * FROM name_map {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                tuple(params) + (max(1, int(size)), offset),
            )
            items = [{"id": r.get("id"), "type": r.get("name_type"), "original": r.get("name_original"),
                      "zh": r.get("name_zh"), "source": r.get("source"), "updated_at": r.get("updated_at")}
                     for r in rows]
            return {"items": items, "total": n}
        except Exception as e:
            logger.warning(f"[NameMap] 查询失败: {e}")
            return {"items": [], "total": 0}


    def find_pool_person(self, *, plugin_id: str, server_id: str, emby_person_id: str,
                         db: Optional[Any] = None) -> Optional[dict]:
        try:
            return _q1("SELECT * FROM name_map WHERE plugin_id=? AND server_id=? AND emby_person_id=? "
                       "AND emby_person_id<>''", (plugin_id, server_id, (emby_person_id or "").strip()))
        except Exception:
            return None

    def find_pool_persons_by_name(self, *, plugin_id: str, name_original: str,
                                  server_id: str = "", db: Optional[Any] = None) -> list:
        """按原文名在池中定位 Person 身份行（人工改人名→ID 优先同步用）。
        仅返回 emby_person_id 非空的行；server_id 为空则跨服务器返回全部（多服务器各自改名）。"""
        _nm = str(name_original or "").strip()
        if not _nm:
            return []
        try:
            sql = ("SELECT * FROM name_map WHERE plugin_id=? AND name_type='person' "
                   "AND name_original=? AND emby_person_id IS NOT NULL AND emby_person_id<>''")
            params: list = [plugin_id, _nm]
            _sk = str(server_id or "").strip()
            if _sk:
                sql += " AND server_id=?"
                params.append(_sk)
            sql += " ORDER BY updated_at DESC, id DESC"
            return _q(sql, tuple(params))
        except Exception as e:
            logger.warning(f"[NameMap] find_pool_persons_by_name 失败: {e}")
            return []

    def list_pool_person_ids(self, *, plugin_id: str, server_id: str = "",
                             db: Optional[Any] = None) -> set:
        """增量拉取用：该服务器池里已有的 emby_person_id 集合。"""
        try:
            rows = _q("SELECT emby_person_id FROM name_map WHERE plugin_id=? AND server_id=? "
                      "AND emby_person_id<>''", (plugin_id, server_id))
            return {str(r.get("emby_person_id") or "") for r in rows}
        except Exception:
            return set()

    def sweep_pool_lifecycle(self, *, plugin_id: str, server_id: str, seen_ids: set = None,
                             miss_threshold: int = 3, db: Optional[Any] = None) -> dict:
        """拉取完成后刷新池生命周期（Emby 镜像态）——
        - 本次见到的 ID（带 emby_person_id）→ active（miss_count 归零）
        - 池内该服务器其他带 ID 的行 → miss_count+1：连续 >= miss_threshold 次未见 → missing，否则 stale
        绝不删除任何行（历史翻译/人工译文保留）；无 ID 的 legacy 行不参与（无法比对，等 Emby 认领）。
        :return: {'active': n, 'stale': n, 'missing': n}
        """
        _seen = {str(x).strip() for x in (seen_ids or set()) if str(x).strip()}
        _thr = max(1, int(miss_threshold or 3))
        out = {"active": 0, "stale": 0, "missing": 0}
        try:
            with _conn_lock:
                conn = _get_conn()
                try:
                    conn.execute("CREATE TEMP TABLE IF NOT EXISTS _pool_seen (pid TEXT PRIMARY KEY)")
                    conn.execute("DELETE FROM _pool_seen")
                    _batch = [(_x,) for _x in _seen]
                    if _batch:
                        conn.executemany("INSERT OR IGNORE INTO _pool_seen (pid) VALUES (?)", _batch)
                    _base = ("plugin_id=? AND name_type='person' AND server_id=? "
                             "AND emby_person_id IS NOT NULL AND emby_person_id<>''")
                    cur = conn.execute(
                        f"UPDATE name_map SET pool_sync_state='active', pool_miss_count=0 "
                        f"WHERE {_base} AND emby_person_id IN (SELECT pid FROM _pool_seen)",
                        (plugin_id, server_id))
                    out["active"] = int(cur.rowcount or 0)
                    conn.execute(
                        f"UPDATE name_map SET pool_miss_count=COALESCE(pool_miss_count,0)+1 "
                        f"WHERE {_base} AND emby_person_id NOT IN (SELECT pid FROM _pool_seen)",
                        (plugin_id, server_id))
                    cur = conn.execute(
                        f"UPDATE name_map SET pool_sync_state = CASE WHEN pool_miss_count>=? "
                        f"THEN 'missing' ELSE 'stale' END "
                        f"WHERE {_base} AND COALESCE(pool_miss_count,0)>0 AND emby_person_id NOT IN "
                        f"(SELECT pid FROM _pool_seen)", (_thr, plugin_id, server_id))
                    out["stale"] = int(cur.rowcount or 0)
                    _mc = _q1("SELECT COUNT(*) AS c FROM name_map "
                              f"WHERE {_base} AND pool_sync_state='missing'", (plugin_id, server_id))
                    out["missing"] = int((_mc or {}).get("c") or 0)
                    conn.execute("DELETE FROM _pool_seen")
                    conn.commit()
                finally:
                    pass
        except Exception as e:
            logger.warning(f"[NameMap] sweep_pool_lifecycle 失败: {e}")
        return out

    def export_pool(self, *, plugin_id: str, db: Optional[Any] = None) -> list:
        """导出池内全部 Person（身份 + 当前名 + 译文 + 类型 + 状态）。"""
        try:
            rows = _q("SELECT * FROM name_map WHERE plugin_id=? AND name_type='person' ORDER BY id",
                      (plugin_id,))
        except Exception as e:
            logger.warning(f"[NameMap] export_pool 失败: {e}")
            return []
        return [{
            "server_id": str(r.get("server_id") or ""),
            "emby_person_id": str(r.get("emby_person_id") or ""),
            "name_original": str(r.get("name_original") or ""),
            "name_current": str(r.get("name_current") or ""),
            "name_zh": str(r.get("name_zh") or ""),
            "person_type": str(r.get("person_type") or ""),
            "person_types": r.get("person_types") or "",
            "translation_status": str(r.get("translation_status") or ""),
            "sync_status": str(r.get("sync_status") or ""),
            "source": str(r.get("source") or ""),
            "legacy_identity": int(r.get("legacy_identity") or 0),
            "pool_sync_state": str(r.get("pool_sync_state") or "active"),
        } for r in rows]

    def import_pool(self, *, plugin_id: str, rows: list = None, db: Optional[Any] = None) -> int:
        """导入 Person 到池：按 server_id+emby_person_id 身份 upsert；
        带译文的行以 manual 覆盖（导入=人工结果，最高优先级）；不带译文只补类型/状态，不动已有译文。"""
        if not rows:
            return 0
        now = _now()
        n = 0
        for r in rows:
            if not isinstance(r, dict):
                continue
            orig = str(r.get("name_original") or r.get("original") or "").strip()
            if not orig:
                continue
            sid = str(r.get("server_id") or "")
            pid = str(r.get("emby_person_id") or "")
            zh = str(r.get("name_zh") or r.get("zh") or "").strip()
            cur = str(r.get("name_current") or "")
            ptype = str(r.get("person_type") or "")
            ptypes = r.get("person_types") or ""
            if isinstance(ptypes, (list, tuple)):
                ptypes = json.dumps(list(ptypes), ensure_ascii=False)
            tstat = str(r.get("translation_status") or "")
            sstat = str(r.get("sync_status") or "")
            src = str(r.get("source") or ("manual" if zh else "emby"))
            _legacy = 0 if pid else 1
            try:
                rec = self.find_pool_person(plugin_id=plugin_id, server_id=sid, emby_person_id=pid) if pid else None
                if rec is None and not pid:
                    rec = _q1("SELECT * FROM name_map WHERE plugin_id=? AND name_type='person' "
                              "AND server_id=? AND name_original=? AND (emby_person_id IS NULL OR emby_person_id='') "
                              "ORDER BY id DESC LIMIT 1", (plugin_id, sid, orig))
                if rec is None:
                    try:
                        _x("INSERT INTO name_map (plugin_id, name_type, name_original, name_zh, source, updated_at, "
                           "server_id, emby_person_id, name_current, person_type, person_types, "
                           "translation_status, sync_status, legacy_identity) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                           (plugin_id, "person", orig, zh, src, now, sid, pid, cur, ptype,
                            str(ptypes or ""), tstat, sstat, _legacy))
                        n += 1
                        continue
                    except sqlite3.IntegrityError:
                        rec = self.find_pool_person(plugin_id=plugin_id, server_id=sid,
                                                    emby_person_id=pid) if pid else None
                        if rec is None:
                            continue
                sets = ["server_id=?", "emby_person_id=?", "name_current=?", "person_type=?",
                        "person_types=?", "translation_status=?", "sync_status=?", "updated_at=?",
                        "legacy_identity=?"]
                params = [sid, pid, cur, ptype, str(ptypes or ""), tstat, sstat, now, _legacy]
                if zh:
                    sets += ["name_zh=?", "source=?"]
                    params += [zh, src]
                params.append(rec.get("id"))
                _x(f"UPDATE name_map SET {', '.join(sets)} WHERE id=?", tuple(params))
                n += 1
            except Exception as e:
                logger.warning(f"[NameMap] import_pool 单条失败: {e}")
        return n

    def upsert_pool_person(self, *, plugin_id: str, server_id: str, emby_person_id: str,
                           name_original: str, name_current: str = "", name_zh: str = "",
                           person_type: str = "", person_types: list = None,
                           source: str = "", translation_status: str = "",
                           sync_status: str = "", db: Optional[Any] = None) -> str:
        """入池/更新一人（拉取 worker 用）。
        对已存在的 Person 也会刷新「Emby 事实」（name_original/name_current/
        person_type/person_types），返回三态便于统计；不再一律「跳过」。
        规则：name_zh 只增不覆盖 —— 拉取不带译文，绝不覆盖已有译文（人工/LLM 结果最高）；
        翻译/同步状态不在更新路径覆盖（由翻译/同步流程维护）。
        :return: 'added' | 'updated' | 'unchanged' | 'failed'
        """
        orig = str(name_original or "").strip()
        pid = str(emby_person_id or "").strip()
        if not orig:
            return "failed"
        _ptypes = json.dumps(list(person_types or ([person_type] if person_type else [])), ensure_ascii=False)
        now = _now()
        try:
            rec = self.find_pool_person(plugin_id=plugin_id, server_id=server_id, emby_person_id=pid) if pid else None
            if rec is None:
                # 无 ID（老缓存行）时按名字兜底找一次（仅同服务器）
                rec = _q1("SELECT * FROM name_map WHERE plugin_id=? AND name_type='person' "
                          "AND (name_original=? OR name_current=?) AND server_id=? AND emby_person_id=''",
                          (plugin_id, orig, orig, server_id))
            if rec is None:
                try:
                    _x("INSERT INTO name_map (plugin_id, name_type, name_original, name_zh, source, updated_at, "
                       "server_id, emby_person_id, name_current, person_type, person_types, "
                       "translation_status, sync_status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (plugin_id, "person", orig, str(name_zh or "").strip(), str(source or "emby"),
                        now, server_id, pid, str(name_current or "").strip(), str(person_type or ""),
                        _ptypes, str(translation_status or ""), str(sync_status or "")))
                    return "added"
                except sqlite3.IntegrityError:
                    rec = self.find_pool_person(plugin_id=plugin_id, server_id=server_id,
                                                emby_person_id=pid) if pid else None
                    if rec is None:
                        return "failed"
            _orig_keep = str(rec.get("name_original") or "").strip()
            _orig_new = _orig_keep or orig
            _cur_new = str(name_current or "").strip()
            _ex_zh = str(rec.get("name_zh") or "").strip()
            _zh_valid = (bool(_ex_zh) and _ex_zh != _orig_keep
                         and not _is_kana_text(_ex_zh))
            _zh_fill = (str(name_zh or "").strip() if not _zh_valid else "")
            _zh_clear = bool(_ex_zh) and not _zh_valid and not _zh_fill
            _zh_write = bool(_zh_fill) or _zh_clear
            _changed = (
                str(rec.get("name_current") or "").strip() != _cur_new
                or str(rec.get("person_type") or "") != str(person_type or "")
                or str(rec.get("person_types") or "") != _ptypes
                or str(rec.get("server_id") or "") != server_id
                or str(rec.get("emby_person_id") or "") != pid
                or _zh_write
            )
            if not _changed:
                return "unchanged"
            _x("UPDATE name_map SET server_id=?, emby_person_id=?, name_original=?, name_current=?, "
               "person_type=?, person_types=?, updated_at=?"
               + (", name_zh=?, source=?" if _zh_write else "") +
               " WHERE id=?",
               ((server_id, pid, _orig_new, _cur_new, str(person_type or ""), _ptypes, now)
                + ((_zh_fill, str(source or "emby") if _zh_fill else "")
                   if _zh_write else ())
                + (rec.get("id"),)))
            return "updated"
        except Exception as e:
            logger.warning(f"[NameMap] upsert_pool_person 失败: {e}")
            return "failed"

    def bind_pool_person_id(self, *, plugin_id: str, server_id: str = "", name_original: str = "",
                            emby_person_id: str, db: Optional[Any] = None) -> int:
        """legacy 行（无 ID）按名字同步成功后回填 emby_person_id，让后续同步走 ID 精确路径。
        只回填当前 emby_person_id 为空的行 —— 绝不覆盖已有身份（文档 §七 A / §十）。"""
        pid = str(emby_person_id or "").strip()
        if not pid:
            return 0
        try:
            return _x("UPDATE name_map SET emby_person_id=?, updated_at=? "
                      "WHERE plugin_id=? AND server_id=? AND name_original=? "
                      "AND (emby_person_id IS NULL OR emby_person_id='')",
                      (pid, _now(), plugin_id, str(server_id or ""), str(name_original or "").strip()))
        except Exception as e:
            logger.warning(f"[NameMap] bind_pool_person_id 失败: {e}")
            return 0

    def update_pool_status(self, *, plugin_id: str, server_id: str = "", emby_person_id: str = "",
                           name_original: str = "", translation_status: Optional[str] = None,
                           sync_status: Optional[str] = None, sync_error: Optional[str] = None,
                           last_sync_at: Optional[str] = None, name_current: Optional[str] = None,
                           db: Optional[Any] = None) -> int:
        """更新池条目状态（按身份定位；无 ID 时按 server_id+原文名兜底）。
        name_current: 改名成功后传译文 —— 「Emby 当前名」由事实推导状态（已同步=当前名==译文）。"""
        sets, params = [], []
        for _col, _val in (("translation_status", translation_status), ("sync_status", sync_status),
                           ("sync_error", sync_error), ("last_sync_at", last_sync_at),
                           ("name_current", name_current)):
            if _val is not None:
                sets.append(f"{_col}=?")
                params.append(str(_val))
        if not sets:
            return 0
        sets.append("updated_at=?")
        params.append(_now())
        pid = str(emby_person_id or "").strip()
        if pid:
            where = "plugin_id=? AND server_id=? AND emby_person_id=?"
            params += [plugin_id, server_id, pid]
        else:
            where = "plugin_id=? AND server_id=? AND name_original=?"
            params += [plugin_id, server_id, str(name_original or "").strip()]
        try:
            return _x(f"UPDATE name_map SET {', '.join(sets)} WHERE {where}", tuple(params))
        except Exception as e:
            logger.warning(f"[NameMap] update_pool_status 失败: {e}")
            return 0

    def set_pool_zh(self, *, plugin_id: str, server_id: str = "", emby_person_id: str = "",
                    name_original: str = "", name_zh: str = "", source: str = "manual",
                    db: Optional[Any] = None) -> bool:
        """写池译名（人名池单条编辑）—— 按身份（server_id + emby_person_id）定位，
        无 ID 时按 server_id + 原文名兜底；source 默认 manual（人工最高优先级，AI 不覆盖）。
        同时写 translation_status / sync_status，避免数据库残留旧状态。
        人工保存译文=translated；清空译文按原文语言回 pending / no_change（sync 由事实推导）。"""
        _zh = str(name_zh or "").strip()
        pid = str(emby_person_id or "").strip()
        try:
            if pid:
                where = "plugin_id=? AND server_id=? AND emby_person_id=?"
                params: list = [plugin_id, server_id, pid]
                _rec = _q1("SELECT name_original, name_current FROM name_map "
                           "WHERE plugin_id=? AND server_id=? AND emby_person_id=?",
                           (plugin_id, server_id, pid)) or {}
            else:
                where = "plugin_id=? AND server_id=? AND name_original=?"
                params = [plugin_id, server_id, str(name_original or "").strip()]
                _rec = _q1("SELECT name_original, name_current FROM name_map "
                           "WHERE plugin_id=? AND server_id=? AND name_original=?",
                           (plugin_id, server_id, str(name_original or "").strip())) or {}
            _orig = str(_rec.get("name_original") or name_original or "").strip()
            _cur = str(_rec.get("name_current") or "").strip()
            _d = derive_pool_status({"name_original": _orig, "name_zh": _zh, "name_current": _cur})
            _tstat = _d["translation"]
            _sstat = "" if _d["sync"] == "unknown" else _d["sync"]
            n = _x(f"UPDATE name_map SET name_zh=?, source=?, sync_error='', "
                   f"translation_status=?, sync_status=?, updated_at=? WHERE {where}",
                   (_zh, str(source or "manual"), _tstat, _sstat, _now(), *params))
            return bool(n)
        except Exception as e:
            logger.warning(f"[NameMap] set_pool_zh 失败: {e}")
            return False

    def list_pool(self, *, plugin_id: str, keyword: str = "", status: str = "",
                  ptype: str = "", server_id: str = "", page: int = 1, size: int = 50,
                  db: Optional[Any] = None) -> dict:
        """池列表（筛选 + 分页）。
        status 过滤与 derive_pool_status 同一套规则 ——
        pending 待翻译 / no_change 无需操作 / translated 待同步 / synced 已同步 / failed 同步失败。"""
        try:
            where = "WHERE plugin_id=? AND name_type='person'"
            params: list = [plugin_id]
            kw = str(keyword or "").strip()
            if kw:
                where += " AND (name_original LIKE ? OR name_zh LIKE ? OR name_current LIKE ?)"
                params += [f"%{kw}%", f"%{kw}%", f"%{kw}%"]
            if server_id:
                where += " AND server_id=?"
                params.append(server_id)
            if ptype:
                where += " AND (person_type=? OR person_types LIKE ?)"
                params += [ptype, f'%"{ptype}"%']
            st = str(status or "").strip()
            if st == "pending":
                where += f" AND {_SQL_TRANS_PENDING}"
            elif st == "no_change":
                where += f" AND {_SQL_NO_CHANGE}"
            elif st == "translated":
                where += f" AND {_SQL_SYNC_PENDING}"
            elif st == "synced":
                where += f" AND {_SQL_SYNCED}"
            elif st == "failed":
                where += f" AND {_SQL_SYNC_FAILED}"
            total = _q1(f"SELECT COUNT(*) AS c FROM name_map {where}", tuple(params))
            n = int((total or {}).get("c") or 0)
            offset = (max(1, int(page)) - 1) * max(1, int(size))
            rows = _q(f"SELECT * FROM name_map {where} ORDER BY "
                      f"CASE WHEN {_SQL_TRANS_PENDING} THEN 0 "
                      f"WHEN {_SQL_SYNC_FAILED} THEN 1 "
                      f"WHEN {_SQL_SYNC_PENDING} THEN 2 "
                      f"ELSE 3 END, "
                      "id DESC LIMIT ? OFFSET ?", tuple(params) + (max(1, int(size)), offset))
            items = []
            for r in rows:
                _d = derive_pool_status(r)
                items.append({
                    "id": r.get("id"),
                    "server_id": str(r.get("server_id") or ""),
                    "emby_person_id": str(r.get("emby_person_id") or ""),
                    "name_original": str(r.get("name_original") or ""),
                    "name_current": str(r.get("name_current") or ""),
                    "name_zh": str(r.get("name_zh") or ""),
                    "person_type": str(r.get("person_type") or ""),
                    "person_types": r.get("person_types") or "[]",
                    "source": str(r.get("source") or ""),
                    "status": _d["ui"],
                    "translation_status": _d["translation"],
                    "sync_status": _d["sync"],
                    "lifecycle": _d["lifecycle"],
                    "legacy_identity": int(r.get("legacy_identity") or 0),
                    "sync_error": str(r.get("sync_error") or ""),
                    "last_sync_at": str(r.get("last_sync_at") or ""),
                    "updated_at": str(r.get("updated_at") or ""),
                })
            return {"items": items, "total": n}
        except Exception as e:
            logger.warning(f"[NameMap] list_pool 失败: {e}")
            return {"items": [], "total": 0}

    def count_pool_status(self, *, plugin_id: str, server_id: str = "",
                          db: Optional[Any] = None) -> dict:
        """池统计（仪表盘/人名池页卡片）。
        与 derive_pool_status / list_pool 共用同一套 _SQL_* 规则，
        翻译维度与同步维度分离：
        pending=待翻译 / no_change=无需操作 / translated=待同步 / synced=已同步 / failed=同步失败。"""
        try:
            where = "WHERE plugin_id=? AND name_type='person'"
            params: list = [plugin_id]
            if server_id:
                where += " AND server_id=?"
                params.append(server_id)
            r = _q1(
                "SELECT COUNT(*) AS total, "
                f"SUM(CASE WHEN {_SQL_TRANS_PENDING} THEN 1 ELSE 0 END) AS pending, "
                f"SUM(CASE WHEN {_SQL_NO_CHANGE} THEN 1 ELSE 0 END) AS no_change, "
                f"SUM(CASE WHEN {_SQL_SYNC_PENDING} THEN 1 ELSE 0 END) AS translated, "
                f"SUM(CASE WHEN {_SQL_SYNCED} THEN 1 ELSE 0 END) AS synced, "
                f"SUM(CASE WHEN {_SQL_SYNC_FAILED} THEN 1 ELSE 0 END) AS failed "
                f"FROM name_map {where}", tuple(params))
            r = r or {}
            return {
                "total": int(r.get("total") or 0),
                "pending": int(r.get("pending") or 0),
                "no_change": int(r.get("no_change") or 0),
                "translated": int(r.get("translated") or 0),
                "synced": int(r.get("synced") or 0),
                "failed": int(r.get("failed") or 0),
            }
        except Exception:
            return {"total": 0, "pending": 0, "no_change": 0, "translated": 0, "synced": 0, "failed": 0}

    def list_translated_pending_sync(self, *, plugin_id: str, server_id: str = "", limit: int = 0,
                                     db: Optional[Any] = None) -> list:
        """待同步清单（存在有效目标名、Emby 当前名 != 目标名）。
        目标名 = 有效译文优先，无译文时原文（原文已是中文）——
        不再要求 name_zh<>''；「原文已是中文 + 当前名≠原文」也进入待同步。
        v4.6.93：当前名**未知**（空：扫描缓存行/无身份）时只有「有真译文」才进入
        —— 原文已是中文且当前名未知者无可同步之物，不再列入（也不再报待同步）。"""
        try:
            where = f"WHERE plugin_id=? AND name_type='person' AND {_SQL_SYNC_PENDING}"
            params: list = [plugin_id]
            if server_id:
                where += " AND server_id=?"
                params.append(server_id)
            sql = f"SELECT * FROM name_map {where} ORDER BY id LIMIT ?"
            _lim = int(limit) if int(limit or 0) > 0 else 100000
            return _q(sql, tuple(params) + (_lim,))
        except Exception:
            return []

    def remove_non_matching_types(self, *, plugin_id: str, allowed_types: list,
                                  keep_unknown: bool = True, db: Optional[Any] = None) -> int:
        """按类型白名单重筛池 —— 删除「池管理条目」（有 emby_person_id）中类型不在白名单的行；
        普通缓存行（无 ID）不动（它们由翻译范围开关控制）。
        类型未知（person_types 为空且 person_type 为空）≠ Actor，单列「未分类」态。
        keep_unknown=True（默认，§十）保留未分类条目；False 时未分类同样按白名单过滤（删除）。"""
        allow = {str(t or "").strip() for t in (allowed_types or []) if str(t or "").strip()}
        try:
            rows = _q("SELECT id, person_type, person_types FROM name_map WHERE plugin_id=? "
                      "AND name_type='person' AND emby_person_id<>''", (plugin_id,))
            _del = []
            for r in rows:
                try:
                    _types = json.loads(r.get("person_types") or "[]")
                    if not isinstance(_types, list):
                        _types = []
                except Exception:
                    _types = []
                _pt = str(r.get("person_type") or "").strip()
                if _pt and _pt not in _types:
                    _types.append(_pt)
                if not _types:
                    if keep_unknown:
                        continue
                    _del.append(r.get("id"))
                    continue
                if allow and any(t in allow for t in _types):
                    continue
                _del.append(r.get("id"))
            n = 0
            for _id in _del:
                n += _x("DELETE FROM name_map WHERE id=?", (_id,))
            return n
        except Exception as e:
            logger.warning(f"[NameMap] remove_non_matching_types 失败: {e}")
            return 0

    def upsert_manual(self, *, plugin_id: str, name_type: str, original: str, zh: str,
                      db: Optional[Any] = None) -> bool:
        try:
            orig = (original or "").strip()
            z = (zh or "").strip()
            if not orig or not z:
                return False
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rec = _q1("SELECT * FROM name_map WHERE plugin_id=? AND name_type=? AND name_original=?",
                      (plugin_id, name_type, orig))
            if rec is not None:
                _x("UPDATE name_map SET name_zh=?, source='manual', updated_at=? WHERE id=?",
                   (z, now, rec.get("id")))
            else:
                _x("INSERT INTO name_map (plugin_id, name_type, name_original, name_zh, source, updated_at) "
                   "VALUES (?,?,?,?,?,?)", (plugin_id, name_type, orig, z, "manual", now))
            return True
        except Exception:
            return False

    def delete_entry(self, *, plugin_id: str, name_type: str, original: str,
                     db: Optional[Any] = None) -> bool:
        try:
            _x("DELETE FROM name_map WHERE plugin_id=? AND name_type=? AND name_original=?",
               (plugin_id, name_type, (original or "").strip()))
            return True
        except Exception:
            return False

    def clear_auto(self, *, plugin_id: str, db: Optional[Any] = None) -> int:
        """清空人名池里的自动翻译条目（source=llm/zhconv），
        保留 manual（用户人工修正，防止被重新翻译覆盖）。返回删除行数。
        """
        try:
            return _x("DELETE FROM name_map WHERE plugin_id=? AND source<>'manual'", (plugin_id,))
        except Exception:
            return 0

    def clear_all(self, *, plugin_id: str, db: Optional[Any] = None) -> int:
        """清空人名池全部条目（含 manual）—— 供人名池页「清除人名池」使用：
        用户确认推倒重来（含人工修正也删，日志已提示）。
        与库页「清空翻译记录」彻底分开 —— 清库不再连带清池（池只由本入口管理）。
        只清 Person 池条目（name_type='person'）—— 不得误删第二排角色
        译文缓存（name_type='role'）等非池数据（清池 ≠ 清空全部翻译记忆）。
        """
        try:
            return _x("DELETE FROM name_map WHERE plugin_id=? AND name_type='person'", (plugin_id,))
        except Exception:
            return 0

    def vacuum(self, *, db: Optional[Any] = None) -> None:
        """WAL 检查点 + VACUUM（维护线程每天一次，防长期 WAL 膨胀）。"""
        try:
            with _conn_lock:
                conn = _get_conn()
                try:
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    conn.commit()
                except Exception:
                    pass
                try:
                    conn.execute("VACUUM")
                    conn.commit()
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"[DB] VACUUM 失败: {e}")



class WritebackDb:
    """条目写回状态机：pending → writing → done / failed / missing。
    写回 worker 靠它做幂等（writing 跳过、done+签名未变故跳过），进程重启不丢。"""

    @staticmethod
    def ensure_table() -> None:
        try:
            _get_conn()
        except Exception as e:
            logger.warning(f"[Writeback] 初始化失败: {e}")

    def get(self, *, plugin_id: str, server_id: str, item_id: str,
            db: Optional[Any] = None) -> Optional[dict]:
        try:
            return _q1("SELECT * FROM writeback_state WHERE plugin_id=? AND server_id=? AND item_id=? "
                       "ORDER BY id DESC LIMIT 1", (plugin_id, server_id, item_id))
        except Exception:
            return None

    def get_by_path(self, *, plugin_id: str, nfo_path: str,
                    db: Optional[Any] = None) -> Optional[dict]:
        try:
            return _q1(f"SELECT * FROM writeback_state WHERE plugin_id=? AND {_NP_SQL}=? "
                       "ORDER BY id DESC LIMIT 1", (plugin_id, _npath(nfo_path)))
        except Exception:
            return None

    def set_status(self, *, plugin_id: str, server_id: str, item_id: str, nfo_path: str = "",
                   status: str = "", error: Optional[str] = None,
                   changed_count: Optional[int] = None, file_sig: Optional[str] = None,
                   attempts: Optional[int] = None, bump_attempt: bool = False,
                   db: Optional[Any] = None) -> bool:
        """写状态（upsert）。status='done' 记 last_success_at；'writing'/'failed' 记 last_attempt_at。
        注意顺序纪律：先写文件成功，再调本方法标记 done（写失败绝不能标成功）。
        file_sig 记条目写回指纹；bump_attempt/attempts 维护重试计数。
        """
        now = _now()
        st = str(status or "").strip()
        try:
            status_set = 1 if st else 0
            np_set = 1 if str(nfo_path or "") else 0
            err_set = 1 if error is not None else 0
            cc_set = 1 if changed_count is not None else 0
            fs_set = 1 if file_sig is not None else 0
            att_bump = 1 if bump_attempt else 0
            att_explicit = 1 if (not bump_attempt and attempts is not None) else 0
            lat_set = 1 if st in ("writing", "failed") else 0
            lsat_set = 1 if st == "done" else 0
            # 新行 attempts 基线为 0：bump → 1；显式 → attempts；两者都没有 → 0
            att_new = int(attempts) if att_explicit else (1 if bump_attempt else 0)
            _x("INSERT INTO writeback_state (plugin_id, server_id, item_id, nfo_path, status, "
               "last_attempt_at, last_success_at, error, changed_count, file_sig, attempts, updated_at) "
               "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
               "ON CONFLICT(plugin_id, server_id, item_id) DO UPDATE SET "
               "status=CASE WHEN ? THEN excluded.status ELSE writeback_state.status END, "
               "nfo_path=CASE WHEN ? THEN excluded.nfo_path ELSE writeback_state.nfo_path END, "
               "error=CASE WHEN ? THEN excluded.error ELSE writeback_state.error END, "
               "changed_count=CASE WHEN ? THEN excluded.changed_count ELSE writeback_state.changed_count END, "
               "file_sig=CASE WHEN ? THEN excluded.file_sig ELSE writeback_state.file_sig END, "
               "attempts=CASE WHEN ? THEN writeback_state.attempts+1 "
               "WHEN ? THEN excluded.attempts ELSE writeback_state.attempts END, "
               "last_attempt_at=CASE WHEN ? THEN ? ELSE writeback_state.last_attempt_at END, "
               "last_success_at=CASE WHEN ? THEN ? ELSE writeback_state.last_success_at END, "
               "updated_at=?",
               (plugin_id, server_id, item_id, str(nfo_path or ""), st or "pending",
                now if st in ("writing", "failed") else "",
                now if st == "done" else "",
                "" if error is None else str(error), 0 if changed_count is None else int(changed_count),
                "" if file_sig is None else str(file_sig), att_new, now,
                status_set, np_set, err_set, cc_set, fs_set, att_bump, att_explicit, lat_set, now,
                lsat_set, now, now))
            return True
        except Exception as e:
            logger.warning(f"[Writeback] set_status 失败: {e}")
            return False

    def register(self, *, plugin_id: str, server_id: str, item_id: str, nfo_path: str = "",
                 file_sig: str = "", target_scope: str = "", db: Optional[Any] = None) -> str:
        """登记条目为「待写回」候选（翻译 worker 每轮有新译文时调用）。
        幂等纪律（文档 §15）：
          - writing → 不动（同一个条目只能有一个写回任务）；
          - done/failed/missing 且指纹一致 → 不重复登记（写回后译文与文件都没变）；
          - 其余（新条目 / 有新译文 / 文件被外部替换）→ 置 pending（新内容重新给足重试次数）。
        target_scope 记录本次登记的任务范围（person/role/both）——
        重复登记时按并集合并（写回就绪判定按该范围，不读瞬时状态）。
        改为单条原子 upsert（INSERT ... ON CONFLICT ... DO UPDATE）——
        依赖 (plugin_id, server_id, item_id) 唯一索引，杜绝并发登记产生的重复 pending 行；
        幂等纪律由 DO UPDATE 的 WHERE 承担（不满足即不更新 → skip），不再「先 SELECT 再决定」。
        :return: 'pending'（新登记或已置待写回）/ 'skip'（无需处理）
        """
        now = _now()
        _fp = str(file_sig or "")
        _ts = _merge_scope("", target_scope)
        try:
            n = _x("INSERT INTO writeback_state (plugin_id, server_id, item_id, nfo_path, status, "
                   "error, file_sig, attempts, target_scope, updated_at) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?) "
                   "ON CONFLICT(plugin_id, server_id, item_id) DO UPDATE SET "
                   "status='pending', error='', file_sig=excluded.file_sig, attempts=0, "
                   # 任务范围并集合并（与 _merge_scope 同语义：空取另一、相同取自身、不同取 both）
                   "target_scope=CASE "
                   "WHEN excluded.target_scope='' THEN writeback_state.target_scope "
                   "WHEN writeback_state.target_scope='' THEN excluded.target_scope "
                   "WHEN writeback_state.target_scope=excluded.target_scope THEN writeback_state.target_scope "
                   "ELSE 'both' END, "
                   "nfo_path=CASE WHEN excluded.nfo_path<>'' THEN excluded.nfo_path "
                   "ELSE writeback_state.nfo_path END, "
                   "updated_at=excluded.updated_at "
                   # 幂等纪律：writing 不动；done/failed/missing 且指纹一致不重复登记
                   "WHERE writeback_state.status<>'writing' "
                   "AND NOT (writeback_state.status IN ('done','failed','missing') "
                   "AND excluded.file_sig<>'' AND writeback_state.file_sig=excluded.file_sig)",
                   (plugin_id, server_id, item_id, str(nfo_path or ""), "pending", "", _fp, 0, _ts, now))
            return "pending" if n > 0 else "skip"
        except Exception as e:
            logger.warning(f"[Writeback] register 失败: {e}")
            return "skip"

    def clear_all(self, *, plugin_id: str, db: Optional[Any] = None) -> int:
        """清空写回队列（供库页「清空翻译记录」调用）—— 记录已删，残留候选只会空转。"""
        try:
            return _x("DELETE FROM writeback_state WHERE plugin_id=?", (plugin_id,))
        except Exception as e:
            logger.warning(f"[Writeback] clear_all 失败: {e}")
            return 0

    def list_by_status(self, *, plugin_id: str, status: str, limit: int = 200,
                       after_id: int = 0, db: Optional[Any] = None) -> list:
        """按状态取行（id 升序）。after_id 用于轮转游标 —— 就绪未到的行不会饿死后面的。"""
        try:
            return _q("SELECT * FROM writeback_state WHERE plugin_id=? AND status=? AND id>? "
                      "ORDER BY id LIMIT ?", (plugin_id, str(status), int(after_id or 0), int(limit)))
        except Exception:
            return []

    def reset_writing(self, *, plugin_id: str, db: Optional[Any] = None) -> int:
        """复位卡住的 writing 行（进程/线程重启后恢复，文档 §50「写回过程中进程重启可恢复」）。
        写文件本身是幂等的（解析→应用→内容无变化不落盘），复位后重跑安全。"""
        try:
            return _x("UPDATE writeback_state SET status='pending', error=?, updated_at=? "
                      "WHERE plugin_id=? AND status='writing'",
                      ("写回中断（进程重启），已自动恢复重试", _now(), plugin_id))
        except Exception as e:
            logger.warning(f"[Writeback] reset_writing 失败: {e}")
            return 0

    def reset_stale_writing(self, *, plugin_id: str, stale_sec: float = 900.0,
                            db: Optional[Any] = None) -> int:
        """把「超时仍停留在 writing」的行复位为 pending（WB-003 租约恢复）。

        与 reset_writing（进程重启时全量复位）互补：本方法按 last_attempt_at 判定 stale，
        由写回 worker 每轮调用 —— 线程崩溃/被强杀但进程还活着时同样能自愈，
        不再出现「行永远停在 writing、用户无法判断是否卡死」。
        阈值默认 15 分钟，远大于单条目写回耗时（秒级），不会误伤正在写入的行；
        写文件幂等（内容无变化不落盘），复位重跑安全。
        """
        _cut = (datetime.now() - timedelta(seconds=float(stale_sec or 900))).isoformat(timespec="seconds")
        try:
            return _x("UPDATE writeback_state SET status='pending', error=?, updated_at=? "
                      "WHERE plugin_id=? AND status='writing' "
                      "AND (last_attempt_at='' OR last_attempt_at IS NULL OR last_attempt_at < ?)",
                      ("写回中断（超时未完成），已自动恢复重试", _now(), plugin_id, _cut))
        except Exception as e:
            logger.warning(f"[Writeback] reset_stale_writing 失败: {e}")
            return 0

    def stats(self, *, plugin_id: str, db: Optional[Any] = None) -> dict:
        """写回状态统计（v4.6.61 · P1-7）—— 「翻译完成 ≠ 写回完成」：
        writeback_pending = pending + writing + failed（已翻完但尚未落盘，含待自动重试的失败）；
        库页/仪表盘据此与「待翻译」并列独立展示。"""
        _out = {"pending": 0, "writing": 0, "failed": 0, "missing": 0, "done": 0,
                "total": 0, "writeback_pending": 0}
        try:
            rows = _q("SELECT status, COUNT(*) AS c FROM writeback_state WHERE plugin_id=? "
                      "GROUP BY status", (plugin_id,))
            for r in rows:
                _st = str(r.get("status") or "").strip() or "pending"
                _c = int(r.get("c") or 0)
                if _st in _out:
                    _out[_st] += _c
                _out["total"] += _c
            _out["writeback_pending"] = _out["pending"] + _out["writing"] + _out["failed"]
        except Exception:
            pass
        return _out


class TranslateJobDb:
    """翻译任务持久化（v4.6.61 · P1-6）—— 重启不静默丢任务。

    - 每次「翻译消费许可」/「重新翻译」生成一行 Job（queued → running → done/failed/cancelled）；
    - rate_limited / quota_paused 记录 next_retry_at，窗口过后由 worker 自动续跑；
    - 进程重启时 mark_stale 把 running/paused 标记为 interrupted 并返回未完成行，
      调用方据此恢复（force 任务重新入队、常规任务提示 pending 仍在库中等待下一次许可）。
    """

    _FIELDS = ("status", "batch_mode", "batch_size", "item_count", "term_count",
               "translated_count", "failed_count", "llm_request_count",
               "rate_limit_count", "quota_error_count", "remaining_count",
               "writeback_pending_count", "started_at", "finished_at",
               "next_retry_at", "error_message", "payload")

    def create(self, *, plugin_id: str, job_id: str, job_type: str = "auto",
               source: str = "both", scope: str = "both", batch_mode: str = "",
               batch_size: int = 0, item_count: int = 0, term_count: int = 0,
               payload: str = "", db: Optional[Any] = None) -> bool:
        """新建 Job（同 id 已存在则不覆盖，幂等）。"""
        try:
            _x("INSERT INTO translate_jobs (id, plugin_id, job_type, source, scope, status, "
               "batch_mode, batch_size, item_count, term_count, created_at, payload) "
               "VALUES (?,?,?,?,?,'queued',?,?,?,?,?,?) "
               "ON CONFLICT(id) DO NOTHING",
               (str(job_id), plugin_id, str(job_type or "auto"), str(source or "both"),
                str(scope or "both"), str(batch_mode or ""), int(batch_size or 0),
                int(item_count or 0), int(term_count or 0), _now(), str(payload or "")))
            return True
        except Exception as e:
            logger.warning(f"[JobDb] create 失败: {e}")
            return False

    def update(self, *, plugin_id: str, job_id: str, db: Optional[Any] = None, **fields) -> int:
        """按白名单更新 Job 字段（非法字段忽略）。"""
        _kv = [(k, v) for k, v in (fields or {}).items() if k in self._FIELDS]
        if not _kv:
            return 0
        try:
            _sets = ", ".join(f"{k}=?" for k, _ in _kv)
            return _x(f"UPDATE translate_jobs SET {_sets} WHERE plugin_id=? AND id=?",
                      tuple(v for _, v in _kv) + (plugin_id, str(job_id)))
        except Exception as e:
            logger.warning(f"[JobDb] update 失败: {e}")
            return 0

    def get(self, *, plugin_id: str, job_id: str, db: Optional[Any] = None) -> Optional[dict]:
        try:
            return _q1("SELECT * FROM translate_jobs WHERE plugin_id=? AND id=?",
                       (plugin_id, str(job_id)))
        except Exception:
            return None

    def list_recent(self, *, plugin_id: str, limit: int = 20, db: Optional[Any] = None) -> list:
        """最近任务（新建在前）—— 供 /translate/jobs 查看。"""
        try:
            return _q("SELECT * FROM translate_jobs WHERE plugin_id=? "
                      "ORDER BY created_at DESC, id DESC LIMIT ?",
                      (plugin_id, max(1, min(200, int(limit or 20)))))
        except Exception:
            return []

    def unfinished(self, *, plugin_id: str, db: Optional[Any] = None) -> list:
        """未完成的任务（queued/running/paused/rate_limited/quota_paused）—— 启动恢复用。"""
        try:
            return _q("SELECT * FROM translate_jobs WHERE plugin_id=? AND status IN "
                      "('queued','running','paused','rate_limited','quota_paused') "
                      "ORDER BY created_at", (plugin_id,))
        except Exception:
            return []

    def mark_stale(self, *, plugin_id: str, db: Optional[Any] = None) -> list:
        """进程重启恢复（文档「重启后的任务处理」）—— 把遗留的 running/paused/
        rate_limited/quota_paused 标记为 interrupted（保留 stats 与 payload），
        并返回这些行；调用方按 job_type 决定恢复方式（force 重新入队 / 常规等待新许可）。"""
        _rows = self.unfinished(plugin_id=plugin_id)
        if not _rows:
            return []
        try:
            _x("UPDATE translate_jobs SET status='interrupted', finished_at=?, "
               "error_message=CASE WHEN error_message='' OR error_message IS NULL "
               "THEN '进程重启，任务中断（已保留统计与待翻数据）' ELSE error_message END "
               "WHERE plugin_id=? AND status IN ('queued','running','paused','rate_limited','quota_paused')",
               (_now(), plugin_id))
        except Exception as e:
            logger.warning(f"[JobDb] mark_stale 失败: {e}")
        return _rows

    # ────────────────── 逐词条明细（v4.6.62 · 第 24 节） ──────────────────

    def save_terms(self, *, plugin_id: str, job_id: str, rows: list,
                   db: Optional[Any] = None) -> int:
        """登记本 Job 的待翻词条（先清该 Job 旧明细再批量写入，幂等）。
        rows: [{"term_id","term"/"original_text","item_id","server_id","season_num","episode_num",
                "person_index","kind","person_type"}]"""
        _jid = str(job_id or "")
        if not _jid or not rows:
            return 0
        try:
            _x("DELETE FROM translate_job_terms WHERE plugin_id=? AND job_id=?", (plugin_id, _jid))
            _n = 0
            for r in rows:
                _x("INSERT INTO translate_job_terms (job_id, plugin_id, term_id, item_id, server_id, "
                   "season_num, episode_num, person_index, kind, person_type, original_text, status) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,'pending')",
                   (_jid, plugin_id, str(r.get("term_id") or ""), str(r.get("item_id") or ""),
                    str(r.get("server_id") or ""), r.get("season_num"), r.get("episode_num"),
                    int(r.get("person_index") or 0), str(r.get("kind") or ""),
                    str(r.get("person_type") or ""),
                    str(r.get("original_text") or r.get("term") or "")))
                _n += 1
            return _n
        except Exception as e:
            logger.warning(f"[JobDb] save_terms 失败: {e}")
            return 0

    def set_terms_status(self, *, plugin_id: str, job_id: str, term_ids: list,
                         status: str, translation: str = "", error: str = "",
                         bump_retry: bool = False, db: Optional[Any] = None) -> int:
        """批量置词条状态（translated/failed/skipped）。成功记 translation + translated_at。"""
        _ids = [str(x) for x in (term_ids or []) if str(x or "").strip()]
        if not _ids:
            return 0
        _st = str(status or "").strip()
        _ts = _now()
        try:
            _n = 0
            for _tid in _ids:
                _n += _x("UPDATE translate_job_terms SET status=?, translation=?, error_message=?, "
                         "translated_at=CASE WHEN ?='translated' THEN ? ELSE translated_at END, "
                         "retry_count=retry_count + ? "
                         "WHERE plugin_id=? AND job_id=? AND term_id=?",
                         (_st, str(translation or ""), str(error or ""),
                          _st, _ts, 1 if bump_retry else 0, plugin_id, job_id, _tid))
            return _n
        except Exception as e:
            logger.warning(f"[JobDb] set_terms_status 失败: {e}")
            return 0

    def list_terms(self, *, plugin_id: str, job_id: str, status: str = "",
                   limit: int = 500, db: Optional[Any] = None) -> list:
        try:
            if str(status or "").strip():
                return _q("SELECT * FROM translate_job_terms WHERE plugin_id=? AND job_id=? AND status=? "
                          "ORDER BY id LIMIT ?", (plugin_id, job_id, status, int(limit or 500)))
            return _q("SELECT * FROM translate_job_terms WHERE plugin_id=? AND job_id=? "
                      "ORDER BY id LIMIT ?", (plugin_id, job_id, int(limit or 500)))
        except Exception:
            return []

    def terms_summary(self, *, plugin_id: str, job_id: str, db: Optional[Any] = None) -> dict:
        """本 Job 词条状态计数（pending/translated/failed/skipped）—— 供进度追溯。"""
        _out = {"pending": 0, "claimed": 0, "translated": 0, "failed": 0, "skipped": 0, "total": 0}
        try:
            for r in _q("SELECT status, COUNT(*) AS c FROM translate_job_terms "
                        "WHERE plugin_id=? AND job_id=? GROUP BY status", (plugin_id, job_id)):
                _st = str(r.get("status") or "") or "pending"
                _c = int(r.get("c") or 0)
                if _st in _out:
                    _out[_st] += _c
                _out["total"] += _c
        except Exception:
            pass
        return _out

    def clear_terms(self, *, plugin_id: str, job_id: str = "", db: Optional[Any] = None) -> int:
        """清词条明细（job_id 空 = 清该插件的全部；由保留策略调用，避免无限膨胀）。"""
        try:
            if str(job_id or "").strip():
                return _x("DELETE FROM translate_job_terms WHERE plugin_id=? AND job_id=?",
                          (plugin_id, str(job_id)))
            return _x("DELETE FROM translate_job_terms WHERE plugin_id=?", (plugin_id,))
        except Exception:
            return 0

    # ────────────────── 逐批次明细（v4.6.62 · 第 24 节） ──────────────────

    def add_batch(self, *, plugin_id: str, job_id: str, batch_id: int, status: str = "",
                  request_no: int = 0, term_count: int = 0, returned_count: int = 0,
                  attempt_count: int = 0, http_status: int = 0, error_kind: str = "",
                  input_tokens: int = 0, output_tokens: int = 0,
                  started_at: str = "", finished_at: str = "",
                  db: Optional[Any] = None) -> int:
        """记一条批次留痕（真实请求次数 / 返回条数 / 令牌 / 耗时）。"""
        try:
            return _x("INSERT INTO translate_job_batches (job_id, plugin_id, batch_id, status, request_no, "
                      "term_count, returned_count, attempt_count, http_status, error_kind, "
                      "input_tokens, output_tokens, started_at, finished_at) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (str(job_id), plugin_id, int(batch_id or 0), str(status or ""),
                       int(request_no or 0), int(term_count or 0), int(returned_count or 0),
                       int(attempt_count or 0), int(http_status or 0), str(error_kind or ""),
                       int(input_tokens or 0), int(output_tokens or 0),
                       str(started_at or ""), str(finished_at or _now())))
        except Exception as e:
            logger.warning(f"[JobDb] add_batch 失败: {e}")
            return 0

    def list_batches(self, *, plugin_id: str, job_id: str, limit: int = 200,
                     db: Optional[Any] = None) -> list:
        try:
            return _q("SELECT * FROM translate_job_batches WHERE plugin_id=? AND job_id=? "
                      "ORDER BY id LIMIT ?", (plugin_id, job_id, int(limit or 200)))
        except Exception:
            return []

    def clear_batches(self, *, plugin_id: str, job_id: str = "", db: Optional[Any] = None) -> int:
        try:
            if str(job_id or "").strip():
                return _x("DELETE FROM translate_job_batches WHERE plugin_id=? AND job_id=?",
                          (plugin_id, str(job_id)))
            return _x("DELETE FROM translate_job_batches WHERE plugin_id=?", (plugin_id,))
        except Exception:
            return 0

    def prune(self, *, plugin_id: str, keep: int = 30, db: Optional[Any] = None) -> int:
        """只保留最近 keep 个 Job（清理更早 Job 的明细，防表无限膨胀）。
        Job 主表只保留最近 keep 条 finished 记录。"""
        _removed = 0
        try:
            _rows = _q("SELECT id FROM translate_jobs WHERE plugin_id=? AND status NOT IN "
                       "('queued','running','paused','rate_limited','quota_paused') "
                       "ORDER BY created_at DESC, id DESC", (plugin_id,))
            _ids = [str(r.get("id") or "") for r in _rows]
            for _old in _ids[max(0, int(keep or 30)):]:
                if not _old:
                    continue
                _removed += self.clear_terms(plugin_id=plugin_id, job_id=_old)
                _removed += self.clear_batches(plugin_id=plugin_id, job_id=_old)
                _x("DELETE FROM translate_jobs WHERE plugin_id=? AND id=?", (plugin_id, _old))
        except Exception as e:
            logger.warning(f"[JobDb] prune 失败: {e}")
        return _removed