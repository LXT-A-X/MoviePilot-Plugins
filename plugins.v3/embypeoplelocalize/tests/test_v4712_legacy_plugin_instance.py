# -*- coding: utf-8 -*-
"""v4.7.12 回归：GitHub issue #13 —— 主程序历史插件实例残留的自我收敛。

覆盖：
  T1 真 SQLite：只删「本插件历史 ID 白名单 + instance_id==source_plugin_id + 未启用 + 无配置 + ID 非法」的纯残留行
  T2 安全护栏：已启用行 / 带配置行 / 源 ID 不同行 / 白名单外中文 ID 行 / 合法 ID 行 一律保留
  T3 幂等：再跑一次 status=none、removed=0；主库其它表数据不受影响
  T4 边界：表缺失→no_table；列缺失→no_columns；库不存在→no_db；CONFIG_PATH 空→no_config_path；
         主库文件名探测（user.db 不在、app.db 在）；配置列名为 `config` 时同样可用
  T5 源码级：init_plugin 接入、白名单常量、删除前留档日志、失败不抛
"""
import sys
import os
import re
import sqlite3
import textwrap
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
TMP = Path(tempfile.mkdtemp(prefix="epl4712_"))
_N = [0, 0]


def check(cond, msg):
    if cond:
        _N[0] += 1
        print(f"[PASS] {msg}")
    else:
        _N[1] += 1
        print(f"[FAIL] {msg}")


class _Logger:
    def __init__(self):
        self.infos, self.warnings, self.debugs, self.errors = [], [], [], []

    def debug(self, m, *a, **k):
        self.debugs.append(str(m))

    def info(self, m, *a, **k):
        self.infos.append(str(m))

    def warning(self, m, *a, **k):
        self.warnings.append(str(m))

    def error(self, m, *a, **k):
        self.errors.append(str(m))

    def log(self, *a, **k):
        pass


logger = _Logger()


class _Settings:
    CONFIG_PATH = ""


_settings = _Settings()


def _grab_method(src, name):
    mm = re.search(rf"^([ \t]*)def {re.escape(name)}\(", src, re.M)
    assert mm, f"未找到 {name}"
    indent = len(mm.group(1))
    lines = src[mm.start():].splitlines()
    out = [lines[0]]
    for ln in lines[1:]:
        _st = ln.lstrip()
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent and (_st.startswith("def ") or _st.startswith("@")):
            break
        out.append(ln)
    return textwrap.dedent("\n".join(out))


_ns = {"logger": logger, "os": os, "sqlite3": sqlite3, "re": re, "settings": _settings,
       "str": str, "int": int}
exec(_grab_method(_SRC, "_is_legal_plugin_instance_id"), _ns)
exec(_grab_method(_SRC, "_purge_legacy_instances_in_db"), _ns)
exec(_grab_method(_SRC, "_cleanup_legacy_plugin_instances"), _ns)


class _LP:
    _LEGACY_INSTANCE_IDS = ("Emby角色中文化",)
    _is_legal_plugin_instance_id = staticmethod(_ns["_is_legal_plugin_instance_id"])
    _purge_legacy_instances_in_db = _ns["_purge_legacy_instances_in_db"]
    _cleanup_legacy_plugin_instances = _ns["_cleanup_legacy_plugin_instances"]


_self = _LP()

# ─────────────────────────────────────────────
print("\n[T1/T2] 真 SQLite：只删纯残留，其余一律保留")
# ─────────────────────────────────────────────
MARK = "Emby角色中文化"
_T1 = Path(tempfile.mkdtemp(prefix="epl4712main_"))
_DB1 = _T1 / "user.db"
_con1 = sqlite3.connect(str(_DB1))
_con1.executescript("""
CREATE TABLE plugininstance (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  instance_id TEXT DEFAULT '',
  source_plugin_id TEXT DEFAULT '',
  plugin_name TEXT DEFAULT '',
  plugin_desc TEXT DEFAULT '',
  plugin_icon TEXT DEFAULT '',
  is_enabled INTEGER DEFAULT 0,
  config_data TEXT
);
CREATE TABLE plugin_config (id INTEGER PRIMARY KEY AUTOINCREMENT, v TEXT);
INSERT INTO plugin_config (v) VALUES ('keep-me');
""")
_rows_seed = [
    # ① 纯残留（issue #13 实测形态）→ 应删
    (MARK, MARK, "", "", "", 0, None),
    # ② 同中文 ID 但**已启用** → 保留（安全护栏）
    (MARK, MARK, "Emby 演职人员中文化", "", "", 1, None),
    # ③ 同中文 ID 但**带配置** → 保留
    (MARK, MARK, "", "", "", 0, '{"enabled": true}'),
    # ④ instance_id != source_plugin_id → 保留（不是同源自举）
    (MARK, "EmbyPeopleLocalize", "", "", "", 0, None),
    # ⑤ 白名单外的中文 ID（别的插件残留）→ 保留（不做通用清理）
    ("某插件中文名", "某插件中文名", "", "", "", 0, None),
    # ⑥ 合法 ID 的自举行 → 保留（ID 合法不需清理）
    ("EmbyPeopleLocalize", "EmbyPeopleLocalize", "", "", "", 0, None),
    # ⑦ config_data 为字面 'null' → 保留？按 issue 口径「config_data IS NULL」为残留；
    #    这里是 JSON 字面 'null' 文本，实现按空值/裸 null 处理 → 归为残留，删（仅本插件白名单内）
    #    为不引入歧义，本行改用「空串配置」验证空值口径
]
for _r in _rows_seed:
    _con1.execute("INSERT INTO plugininstance (instance_id, source_plugin_id, plugin_name, "
                  "plugin_desc, plugin_icon, is_enabled, config_data) VALUES (?,?,?,?,?,?,?)", _r)
# ⑧ 空串配置（等价于「无配置」）→ 应删
_con1.execute("INSERT INTO plugininstance (instance_id, source_plugin_id, plugin_name, "
              "plugin_desc, plugin_icon, is_enabled, config_data) "
              "VALUES (?,?,?,?,?,?,?)", (MARK, MARK, "", "", "", 0, ""))
_con1.commit()
_con1.close()

_settings.CONFIG_PATH = str(_T1)
logger.infos.clear()
_r1 = _self._cleanup_legacy_plugin_instances()
check(str(_r1.get("status")) == "done", f"命中残留 → status=done，实际 {_r1}")
check(int(_r1.get("removed") or 0) == 2, f"只删 2 行（NULL 配置 + 空串配置），实际 {_r1.get('removed')}")
check(list(_r1.get("ids") or []) == [MARK], f"回报被清的 ID，实际 {_r1.get('ids')}")
check(any("行 id=" in _m for _m in logger.infos),
      f"删除前留档（记录行 id + ID 文本，可手工复原），实际 {logger.infos[:1]}")
check(any("已清理主程序历史插件实例残留 2 行" in _m for _m in logger.infos),
      "删除后一条 INFO 说明清理结果")

_con1 = sqlite3.connect(str(_DB1))
_left = _con1.execute("SELECT instance_id, source_plugin_id, is_enabled, config_data "
                      "FROM plugininstance ORDER BY id").fetchall()
_marks = [r for r in _left if r[0] == MARK]
check(len(_marks) == 3, f"同中文 ID 的行应剩 3 条（已启用/带配置/源不同各 1），实际 {len(_marks)}")
check(len(_left) == 5, f"表里应剩 5 行（原 7 行 + 删 2 行），实际 {len(_left)}")
check(not any(r[0] == MARK and r[1] == MARK and not r[2] and not (r[3] or "").strip()
              for r in _left),
      "本插件「同源 + 未启用 + 无配置」的残留已全部消失")
check(any(r[0] == MARK and int(r[2] or 0) == 1 for r in _left),
      "**已启用的中文 ID 行保留**（不碰在用的实例）")
check(any(r[0] == MARK and str(r[3] or "") == '{"enabled": true}' for r in _left),
      "**带配置的中文 ID 行保留**（不碰有数据的实例）")
check(any(r[0] == MARK and r[1] == "EmbyPeopleLocalize" for r in _left),
      "源 ID 不同的行保留（只清 instance_id == source_plugin_id 的自举残留）")
check(any(r[0] == "某插件中文名" for r in _left),
      "**白名单外的非法 ID 行保留**（绝不做通用非法 ID 清理）")
check(any(r[0] == "EmbyPeopleLocalize" and r[1] == "EmbyPeopleLocalize" for r in _left),
      "合法 ID 的自举行保留（ID 合法无需清理）")
check(_con1.execute("SELECT COUNT(*) FROM plugin_config").fetchone()[0] == 1,
      "主库其它表数据不受影响")

# ─────────────────────────────────────────────
print("\n[T3] 幂等：再跑一次什么都不做")
# ─────────────────────────────────────────────
logger.infos.clear()
_r2 = _self._cleanup_legacy_plugin_instances()
check(str(_r2.get("status")) == "none" and int(_r2.get("removed") or 0) == 0,
      f"残留已清 → 第二次 status=none/removed=0，实际 {_r2}")
check(not any("已清理" in _m for _m in logger.infos), "无残留时不打清理日志（不刷屏）")
check(_con1.execute("SELECT COUNT(*) FROM plugininstance").fetchone()[0] == 5,
      "第二次运行不改动任何行")
_con1.close()

# ─────────────────────────────────────────────
print("\n[T4] 边界：表/列缺失、库名探测、CONFIG_PATH 空")
# ─────────────────────────────────────────────
# ① 库存在但没有 plugininstance 表
_T2 = Path(tempfile.mkdtemp(prefix="epl4712notable_"))
sqlite3.connect(str(_T2 / "user.db")).close()
_settings.CONFIG_PATH = str(_T2)
_r = _self._cleanup_legacy_plugin_instances()
check(str(_r.get("status")) == "no_table" and _r.get("ok") is True,
      f"无 plugininstance 表 → no_table（不报错），实际 {_r}")
# ② 表在但缺关键列
_T3 = Path(tempfile.mkdtemp(prefix="epl4712nocol_"))
_c3 = sqlite3.connect(str(_T3 / "user.db"))
_c3.execute("CREATE TABLE plugininstance (id INTEGER PRIMARY KEY, instance_id TEXT)")
_c3.commit(); _c3.close()
_settings.CONFIG_PATH = str(_T3)
_r = _self._cleanup_legacy_plugin_instances()
check(str(_r.get("status")) == "no_columns" and "缺少" in str(_r.get("reason") or ""),
      f"缺 instance_id/source_plugin_id/is_enabled → no_columns 且不动数据，实际 {_r}")
# ③ 主库文件一个都不存在
_T4 = Path(tempfile.mkdtemp(prefix="epl4712nodb_"))
_settings.CONFIG_PATH = str(_T4)
_r = _self._cleanup_legacy_plugin_instances()
check(str(_r.get("status")) == "no_db" and _r.get("ok") is True,
      f"无主库文件 → no_db（静默跳过），实际 {_r}")
# ④ CONFIG_PATH 为空
_settings.CONFIG_PATH = ""
_r = _self._cleanup_legacy_plugin_instances()
check(str(_r.get("status")) == "no_config_path", f"CONFIG_PATH 未知 → 明确原因，实际 {_r}")
# ⑤ 库名探测：user.db 不存在，脏行在 app.db
_T5 = Path(tempfile.mkdtemp(prefix="epl4712appdb_"))
_c5 = sqlite3.connect(str(_T5 / "app.db"))
_c5.execute("CREATE TABLE plugininstance (id INTEGER PRIMARY KEY, instance_id TEXT, "
            "source_plugin_id TEXT, is_enabled INTEGER, config_data TEXT)")
_c5.execute("INSERT INTO plugininstance (instance_id, source_plugin_id, is_enabled, config_data) "
            "VALUES (?,?,0,NULL)", (MARK, MARK))
_c5.commit(); _c5.close()
_settings.CONFIG_PATH = str(_T5)
_r = _self._cleanup_legacy_plugin_instances()
check(str(_r.get("status")) == "done" and int(_r.get("removed") or 0) == 1,
      f"user.db 不存在时探测到 app.db 并清理，实际 {_r}")
check(sqlite3.connect(str(_T5 / "app.db")).execute(
    "SELECT COUNT(*) FROM plugininstance").fetchone()[0] == 0, "app.db 里的残留确已删除")
# ⑥ 配置列名退化为 `config` 时同样可用
_T6 = Path(tempfile.mkdtemp(prefix="epl4712cfgcol_"))
_c6 = sqlite3.connect(str(_T6 / "user.db"))
_c6.execute("CREATE TABLE plugininstance (id INTEGER PRIMARY KEY, instance_id TEXT, "
            "source_plugin_id TEXT, is_enabled INTEGER, config TEXT)")
_c6.execute("INSERT INTO plugininstance (instance_id, source_plugin_id, is_enabled, config) "
            "VALUES (?,?,0,NULL)", (MARK, MARK))
_c6.execute("INSERT INTO plugininstance (instance_id, source_plugin_id, is_enabled, config) "
            "VALUES (?,?,0,'{\"x\":1}')", (MARK, MARK))
_c6.commit(); _c6.close()
_settings.CONFIG_PATH = str(_T6)
_r = _self._cleanup_legacy_plugin_instances()
check(str(_r.get("status")) == "done" and int(_r.get("removed") or 0) == 1,
      f"配置列名为 `config` 时同样只删无配置行，实际 {_r}")

# ─────────────────────────────────────────────
print("\n[T5] 源码级：接入点 / 白名单 / 安全条件 / 不抛")
# ─────────────────────────────────────────────
check('_LEGACY_INSTANCE_IDS = ("Emby角色中文化",)' in _SRC, "白名单常量只含本插件历史中文实例 ID")
check('r"^[A-Za-z][A-Za-z0-9_]*$"' in _SRC, "ID 合法性判定与主程序口径一致")
_purge_src = _grab_method(_SRC, "_purge_legacy_instances_in_db")
check("instance_id = source_plugin_id" in _purge_src, "SQL 要求 instance_id == source_plugin_id")
check("IN ('0','false')" in _purge_src, "SQL 要求 is_enabled 为假")
check("config_data" in _purge_src and "'null'" in _purge_src, "SQL 要求配置列为空（含裸 null）")
check("PRAGMA table_info(plugininstance)" in _purge_src, "列名不匹配时安全放弃（no_columns）")
_clean_src = _grab_method(_SRC, "_cleanup_legacy_plugin_instances")
check('for _name in ("user.db", "app.db", "moviepilot.db")' in _clean_src,
      "主库文件名按 user.db → app.db → moviepilot.db 探测（各版本不一致）")
check("no_config_path" in _clean_src, "CONFIG_PATH 未知时明确回报而非静默")
_init_src = _SRC[_SRC.index("def init_plugin"):]
_init_src = _init_src[:_init_src.index("def _load_config")]
check("self._cleanup_legacy_plugin_instances()" in _init_src, "init_plugin 启动时调用一次")
check(_init_src.index("self._load_state()") < _init_src.index("_cleanup_legacy_plugin_instances()"),
      "调用点放在 _load_state 之后（启动期，不影响配置加载）")
check("except Exception:\n                pass" in _init_src[
    _init_src.index("_cleanup_legacy_plugin_instances()"):][:400], "调用被 try/except 包住（失败不阻塞启动）")
check("logger.debug" in _grab_method(_SRC, "_purge_legacy_instances_in_db")
      and "return _out" in _grab_method(_SRC, "_purge_legacy_instances_in_db"),
      "数据库异常只记 debug 并返回，不向上抛")
check("_con.close()" in _grab_method(_SRC, "_purge_legacy_instances_in_db"), "连接用 finally 关闭")
check("已清理主程序历史插件实例残留" in _init_src, "启动日志把清理条数推给页面实时日志（_push_log）")

print("\n" + "=" * 72)
print(f"结果: {_N[0]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
