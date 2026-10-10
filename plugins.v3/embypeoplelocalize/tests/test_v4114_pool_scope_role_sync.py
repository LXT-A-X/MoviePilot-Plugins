# -*- coding: utf-8 -*-
"""v4.6.114 回归测试：GitHub issue #4 / #5 + 两处顺带发现。

运行：python tests/test_v4114_pool_scope_role_sync.py

覆盖：
  1 issue #4 人名池「拉取人名」弹窗来源被 3 秒轮询打回：
      · 前端弹窗来源与配置值彻底分离（fetchScope / scopeCfg）
      · /pool/status 回「最近一次任务实际来源」（scope）+ 配置值（scope_cfg）
      · 拉取来源同句落**文件日志**（此前只进页面实时日志内存缓冲）
  2 issue #5 第二排角色译文写入 Emby 条目级 People[].Role：
      · update_item_roles 命中才整份回写、只改 Role 不动 Name、状态机完整
      · db.item_identity（emby_item_id 为空时按媒体 ID 反查的入口）
      · _emby_sync_item_roles（开关 / 无译文 / 取不到 itemId 都明确回报）
      · 挂在写回成功路径（自动写回 / 单条 / 全部写回一次覆盖）
  3 lockedfields 分隔符：Emby 原生 `|` / 逗号 / 分号都认；写回统一 `|` 并去重
  4 worker 热重载守卫跨代共享（`_wb_active` / `_tx_active` 类属性守卫失效）
"""
import sys
import re
import types
import textwrap
import tempfile
import importlib.util
from pathlib import Path
from typing import Any, List, Optional, Dict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl114_"))
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
_DB = (PLUGIN_DIR / "db.py").read_text(encoding="utf-8")
_CLI = (PLUGIN_DIR / "emby_client.py").read_text(encoding="utf-8")
_NFO = (PLUGIN_DIR / "nfo.py").read_text(encoding="utf-8")
_CONST = (PLUGIN_DIR / "constants.py").read_text(encoding="utf-8")

_N = [0, 0]


def check(cond, msg):
    _N[0] += 1
    if cond:
        print(f"  [PASS] {msg}")
    else:
        _N[1] += 1
        print(f"  [FAIL] {msg}")


class _Logger:
    def __init__(self):
        self.infos = []

    def debug(self, *a, **k): pass
    def info(self, *a, **k): self.infos.append(" ".join(str(x) for x in a))
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass
    def log(self, *a, **k): pass


logger = _Logger()
_m = types.ModuleType("app"); _s = types.ModuleType("app.sdk")
_l = types.ModuleType("app.sdk.logging"); _l.logger = logger
_c = types.ModuleType("app.sdk.config")


class _S:
    CONFIG_PATH = str(TMP)


_c.settings = _S()
_req = types.ModuleType("requests")


class _RS:
    def __init__(self): self.headers = {}

    def close(self): pass


_req.Session = _RS
_sch = types.ModuleType("app.schemas"); _sch.ServiceInfo = object
sys.modules.update({"app": _m, "app.sdk": _s, "app.sdk.logging": _l, "app.sdk.config": _c,
                    "requests": _req, "app.schemas": _sch})

_dspec = importlib.util.spec_from_file_location("epl_db114", PLUGIN_DIR / "db.py")
dbm = importlib.util.module_from_spec(_dspec)
_dspec.loader.exec_module(dbm)
_cspec = importlib.util.spec_from_file_location("epl_cli114", PLUGIN_DIR / "emby_client.py")
clim = importlib.util.module_from_spec(_cspec)
_cspec.loader.exec_module(clim)
_nspec = importlib.util.spec_from_file_location("epl_nfo114", PLUGIN_DIR / "nfo.py")
nfom = importlib.util.module_from_spec(_nspec)
_nspec.loader.exec_module(nfom)
_kspec = importlib.util.spec_from_file_location("epl_const114", PLUGIN_DIR / "constants.py")
cst = importlib.util.module_from_spec(_kspec)
_kspec.loader.exec_module(cst)


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


def _code(text):
    """去掉整行注释（避免说明性注释里出现被检查的旧写法）。"""
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))


print("=" * 72)
print("v4.6.114 回归测试（issue #4 弹窗来源 / issue #5 角色写入 Emby / lockedfields / worker 守卫）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] lockedfields 分隔符：Emby 原生 `|` / 逗号 / 分号都认，写回统一 `|` 并去重")
# ─────────────────────────────────────────────


def _mk_doc(inner: str):
    _p = TMP / f"nfo{_N[0]}_{abs(hash(inner)) % 100000}.nfo"
    _p.write_text(f"<movie>{inner}</movie>", encoding="utf-8")
    d = nfom.NfoDoc(str(_p))
    assert d.load(), "NfoDoc.load 失败"
    return d


_d = _mk_doc("<lockedfields>Cast|Cast|Cast|Cast</lockedfields>")
check(_d.is_cast_locked() is True, "`Cast|Cast|Cast|Cast` → 认得出已锁定（此前只按 , 切分 → 误判未锁定）")
_v = _d.set_lock(True)
check(_v is True and (_d.root.find("lockedfields").text or "") == "Cast",
      f"重复 Cast 归一为单个 Cast（去重），实际 {_d.root.find('lockedfields').text!r}")
check(_d.set_lock(True) is False, "已归一后再次 set_lock 不再改动文件（幂等）")

_d = _mk_doc("<lockedfields>Genres,Cast</lockedfields>")
check(_d.is_cast_locked() is True, "逗号分隔形态也认得出 Cast")
_d.set_lock(True)
check((_d.root.find("lockedfields").text or "") == "Genres|Cast",
      f"逗号改写为 Emby 原生 `|`（`Genres|Cast`），实际 {_d.root.find('lockedfields').text!r}")

_d = _mk_doc("<lockedfields>Genres;Studios</lockedfields>")
check(_d.is_cast_locked() is False, "分号分隔且无 Cast → 未锁定")
_d.set_lock(True)
check((_d.root.find("lockedfields").text or "") == "Genres|Studios|Cast",
      f"分号形态补 Cast 并用 `|` 连接，实际 {_d.root.find('lockedfields').text!r}")

_d = _mk_doc("")
check(_d.is_cast_locked() is False, "无 lockedfields → 未锁定")
check(_d.set_lock(True) is True and (_d.root.find("lockedfields").text or "") == "Cast",
      "无 lockedfields → 新建并写 Cast")
_d = _mk_doc("<lockedfields>Cast</lockedfields>")
check(_d.set_lock(True) is False, "已是单个 Cast → 不动文件")
check("def _lock_field_names" in _NFO and "[|,;]" in _NFO, "解析函数按 `| , ;` 三种分隔符切分")

# ─────────────────────────────────────────────
print("\n[T2] update_item_roles：只改 Role、命中才整份回写")
# ─────────────────────────────────────────────
check("People,LockedFields" in clim.EmbyClient._ITEM_FIELDS_UPDATE
      and "ProviderIds" in clim.EmbyClient._ITEM_FIELDS_UPDATE,
      "_ITEM_FIELDS_UPDATE 含 People/LockedFields/ProviderIds（整份回写不丢元数据）")


class _Resp:
    def __init__(self, code, payload=None):
        self.status_code, self._p = code, payload

    def json(self):
        return self._p


class _Sess:
    def __init__(self, seq):
        self.seq = list(seq)
        self.n = 0
        self.calls = []

    def get(self, url, **kw):
        self.calls.append((url, kw.get("params")))
        _r = self.seq[min(self.n, len(self.seq) - 1)]
        self.n += 1
        return _r

    def close(self):
        pass


def _mk(seq):
    c = clim.EmbyClient("http://emby.test:8096", "k")
    c.session = _Sess(seq)
    c._get_user_id = lambda: "u1"
    return c


_people = [{"Id": "p1", "Name": "Tom", "Role": "Peter Parker / Spider-Man"},
           {"Id": "p2", "Name": "Zendaya", "Role": "MJ"},
           {"Id": "p3", "Name": "X", "Role": "Partygoer"}]
_c = _mk([_Resp(200, {"Id": "i1", "Name": "蜘蛛侠：崭新之日", "Overview": "简介",
                      "People": [dict(p) for p in _people]})])
_posts = []
_c._post = lambda path, data=None: (_posts.append((path, data)), True)[1]
_st, _ch = _c.update_item_roles("i1", {"Peter Parker / Spider-Man": "彼得·帕克 / 蜘蛛侠"})
check(_st == "ok" and _ch == 1, f"命中角色 → ok/changed=1，实际 {_st}/{_ch}")
check(len(_posts) == 1 and _posts[0][0] == "/emby/Items/i1", "整份 POST /emby/Items/{id}")
_body = _posts[0][1]
_roles = {p["Name"]: p["Role"] for p in _body["People"]}
check(_roles.get("Tom") == "彼得·帕克 / 蜘蛛侠", "目标人物 Role 已改中文")
check(_roles.get("Zendaya") == "MJ" and _roles.get("X") == "Partygoer", "未命中的角色原样保留")
check(all(p["Name"] in ("Tom", "Zendaya", "X") for p in _body["People"]), "**Name 一律不动**（只改 Role）")
check(_body.get("Overview") == "简介", "整份回写保留其它元数据（Overview）")
check(_c.session.calls[0][1].get("Fields") == clim.EmbyClient._ITEM_FIELDS_UPDATE,
      "读取时用的是更宽的字段集（整份回写不丢字段）")

_c = _mk([_Resp(200, {"Id": "i1", "People": [dict(p) for p in _people]})])
_posts = []
_c._post = lambda path, data=None: (_posts.append(path), True)[1]
check(_c.update_item_roles("i1", {"不存在的角色": "中文"}) == ("noop", 0) and not _posts,
      "一个都没命中 → noop 且**不发写请求**")
check(_c.update_item_roles("i1", {}) == ("noop", 0), "空 role_map → noop")
check(_mk([_Resp(200, {"Id": "i1", "People": []})]).update_item_roles("i1", {"a": "b"}) == ("no_people", 0),
      "Emby 该条目没有 People → no_people（不写）")
check(_mk([_Resp(404, {})]).update_item_roles("i1", {"a": "b"}) == ("not_found", 0), "404 → not_found")
check(_mk([_Resp(500, {})]).update_item_roles("i1", {"a": "b"}) == ("unavailable", 0), "500 → unavailable")
_c = _mk([_Resp(200, {"Id": "i1", "People": [dict(p) for p in _people]})])
_c._post = lambda path, data=None: False
check(_c.update_item_roles("i1", {"Peter Parker / Spider-Man": "彼得·帕克 / 蜘蛛侠"}) == ("failed", 0),
      "整份回写失败 → failed/changed=0")
check("def fetch_item_status(self, item_id: str, fields: Optional[str] = None)" in _CLI,
      "fetch_item_status 支持显式 fields（默认行为不变）")

# ─────────────────────────────────────────────
print("\n[T3] db.item_identity：Emby 侧身份（优先非空 emby_item_id）")
# ─────────────────────────────────────────────
pdb = dbm.PeopleDb()
pdb.ensure_table()
PID = "EPL114"
dbm._x("DELETE FROM person WHERE plugin_id=?", (PID,))
pdb.upsert_people(plugin_id=PID, server_id="", item_id="tmdb:969681", item_type="Movie",
                  title="蜘蛛侠：崭新之日", nfo_path="X:/m/spider/movie.nfo",
                  people=[{"before_name": "A", "Name": "A"}], media_provider="tmdb", media_id="969681")
_idt = pdb.item_identity(plugin_id=PID, item_id="tmdb:969681", server_id="")
check(_idt and _idt.get("media_provider") == "tmdb" and _idt.get("media_id") == "969681",
      f"item_identity 返回媒体身份，实际 {_idt}")
check(_idt.get("emby_item_id") == "", "纯 NFO 扫描入库 → emby_item_id 为空（需按媒体 ID 反查）")
dbm._x("UPDATE person SET emby_item_id='999' WHERE plugin_id=? AND item_id=?", (PID, "tmdb:969681"))
check(pdb.item_identity(plugin_id=PID, item_id="tmdb:969681", server_id="").get("emby_item_id") == "999",
      "有 emby_item_id 时优先返回")
check(pdb.item_identity(plugin_id=PID, item_id="tmdb:none", server_id="") is None, "无记录 → None")

# ─────────────────────────────────────────────
print("\n[T4] _emby_sync_item_roles：开关 / 无译文 / itemId 反查")
# ─────────────────────────────────────────────
_nsRole = {"logger": logger, "Dict": Dict, "constants": cst, "Any": Any, "Optional": Optional}
exec(_grab_method(_SRC, "_emby_sync_item_roles"), _nsRole)
exec(_grab_method(_SRC, "_emby_role_item_id"), _nsRole)


class _CliRole:
    def __init__(self, status="ok", changed=2):
        self.status, self.changed = status, changed
        self.calls = []

    def update_item_roles(self, iid, role_map):
        self.calls.append((iid, dict(role_map)))
        return self.status, self.changed

    def search_item_by_provider(self, prov, mid, include_types=None):
        return "E-FOUND"


class _RoleSelf:
    _emby_sync_item_roles = _nsRole["_emby_sync_item_roles"]
    _emby_role_item_id = _nsRole["_emby_role_item_id"]

    def __init__(self, db=None, enabled=True, cli=None, err="", role_rows=None):
        self._people_db = db
        self._emby_role_sync = enabled
        self._cli = cli
        self._err = err
        self._role_rows = role_rows or []
        self.ident_calls = 0

    def _emby_client_for_server(self, server_id="", allow_legacy_fallback=True):
        return (self._cli, self._err) if self._cli is not None else (None, self._err or "无服务")


class _DbRole:
    def __init__(self, rows, ident):
        self._rows, self._ident = rows, ident
        self.ident_calls = 0

    def people_of_item(self, **kw):
        return self._rows

    def item_identity(self, **kw):
        self.ident_calls += 1
        return self._ident


_rows_role = [{"role_before": "Peter Parker / Spider-Man", "role_after": "彼得·帕克 / 蜘蛛侠"},
              {"role_before": "MJ", "role_after": "MJ"},
              {"role_before": "", "role_after": "空角色"}]
_r = _RoleSelf(db=_DbRole([], None), enabled=False)._emby_sync_item_roles(item_id="i1")
check(_r.get("status") == "disabled", f"开关关 → status=disabled，实际 {_r}")
_r = _RoleSelf(db=_DbRole([{"role_before": "MJ", "role_after": "MJ"}], None))._emby_sync_item_roles(item_id="i1")
check(_r.get("status") == "noop" and _r.get("changed") == 0, f"没有可同步的角色译文 → noop，实际 {_r}")
_dbr = _DbRole(_rows_role, {"emby_item_id": "888", "media_provider": "tmdb", "media_id": "969681",
                            "item_type": "Movie"})
_cr = _CliRole()
_r = _RoleSelf(db=_dbr, cli=_cr)._emby_sync_item_roles(item_id="i1", ctx="写回")
check(_r.get("ok") and _r.get("changed") == 2, f"有译文 + 有 emby_item_id → 同步成功，实际 {_r}")
check(_cr.calls and _cr.calls[0][0] == "888", f"用 emby_item_id 作为目标，实际 {_cr.calls}")
check(_cr.calls[0][1] == {"Peter Parker / Spider-Man": "彼得·帕克 / 蜘蛛侠"},
      f"只收真正有译文的角色（空角色/未翻的剔除），实际 {_cr.calls[0][1]}")
# emby_item_id 为空 → 按媒体 ID 反查
_dbr2 = _DbRole(_rows_role, {"emby_item_id": "", "media_provider": "tmdb", "media_id": "969681",
                             "item_type": "Movie"})
_cr2 = _CliRole()
_r = _RoleSelf(db=_dbr2, cli=_cr2)._emby_sync_item_roles(item_id="i1")
check(_r.get("ok") and _cr2.calls and _cr2.calls[0][0] == "E-FOUND",
      f"emby_item_id 为空 → search_item_by_provider 反查，实际 {_cr2.calls}")
# 反查缓存：第二次不再查库（用全新的桩，避免与上面断言共用计数）
_dbr3 = _DbRole(_rows_role, {"emby_item_id": "", "media_provider": "tmdb", "media_id": "969681",
                             "item_type": "Movie"})
_o = _RoleSelf(db=_dbr3, cli=_CliRole())
_o._emby_sync_item_roles(item_id="i1")
_o._emby_sync_item_roles(item_id="i1")
check(_dbr3.ident_calls == 1, f"itemId 反查结果被缓存（第二次不再查库），实际查库 {_dbr3.ident_calls} 次")
_r = _RoleSelf(db=_DbRole(_rows_role, {"emby_item_id": "", "media_provider": "nfo", "media_id": ""}),
               cli=_CliRole())._emby_sync_item_roles(item_id="i1")
check(_r.get("status") == "no_item_id", f"确实取不到 itemId → no_item_id（明确回报，不静默），实际 {_r}")
_r = _RoleSelf(db=_DbRole(_rows_role, {"emby_item_id": "888"}),
               cli=_CliRole(status="failed", changed=0))._emby_sync_item_roles(item_id="i1")
check(_r.get("ok") is False and "failed" in str(_r.get("status")), f"Emby 写入失败 → 明确失败，实际 {_r}")

# ─────────────────────────────────────────────
print("\n[T5] issue #4：/pool/status 回任务事实 + 配置值分离")
# ─────────────────────────────────────────────
check(_pool_src := "_pool_last_scope: str = \"\"" in _SRC, "类属性 _pool_last_scope 已声明")
_wb = _code(_grab_method(_SRC, "_pool_fetch_worker"))
check("self._pool_last_scope = _scope" in _wb, "worker 记录本次任务实际来源")
check("logger.info(_begin_msg)" in _wb and "_begin_msg" in _wb,
      "「来源=…」同句落文件日志（此前只进页面实时日志内存缓冲）")
check('_scope not in ("libraries", "all")' in _wb, "非法来源值归一为 libraries")

_nsStat = {"logger": logger, "constants": cst, "dict": dict, "bool": bool, "str": str, "int": int,
           "NameMapDb": dbm.NameMapDb}
exec(_grab_method(_SRC, "_api_pool_status"), _nsStat)


class _StatSelf:
    _api_pool_status = _nsStat["_api_pool_status"]

    def __init__(self, last="", cfg="all"):
        self._pool_last_scope = last
        self._pool_fetch_scope = cfg
        self._name_map_db = None
        self._translate_status = {}
        self._pool_pulling = False
        self._pool_status = {}
        self._is_running = False

    def _tx_state_snapshot(self, _cnt):
        return {}

    def _task_running(self, k):
        return False

    def _pool_fetch_trans_types(self):
        return ["Actor"]

    def _emby_clients(self):
        return {}

    def _task_state(self):
        return "IDLE"


_d = _StatSelf(last="", cfg="all")._api_pool_status()["data"]
check(_d.get("scope_cfg") == "all", f"scope_cfg = 设置页配置值，实际 {_d.get('scope_cfg')}")
check(_d.get("scope") == "all", f"没跑过任务 → scope 回落配置值，实际 {_d.get('scope')}")
_d = _StatSelf(last="libraries", cfg="all")._api_pool_status()["data"]
check(_d.get("scope") == "libraries" and _d.get("scope_cfg") == "all",
      f"跑过任务 → scope 回**任务事实**（不再被配置值冒充），实际 {_d.get('scope')}/{_d.get('scope_cfg')}")

_pv = (PLUGIN_DIR / "src" / "views" / "PeoplePoolView.vue").read_text(encoding="utf-8")
_pv_code = _code(_pv)
check("const fetchScope = ref(" in _pv and "const scopeCfg = ref(" in _pv,
      "前端拆成 fetchScope（弹窗本次）/ scopeCfg（配置值）两个 ref")
check("scope.value = d.scope" not in _pv_code, "loadStatus 不再回填弹窗用的 ref（旧写法已移除）")
check("scopeCfg.value = d.scope_cfg || d.scope" in _pv, "loadStatus 只回填配置值（含旧字段兜底）")
check("fetchScope.value = scopeCfg.value" in _pv, "openFetch 打开弹窗时用配置值初始化")
check("scope: fetchScope.value" in _pv, "doFetch 提交的是弹窗本次选择")
check('v-model="fetchScope"' in _pv, "弹窗单选绑定弹窗局部 state")
check("仅本次拉取生效" in _pv, "弹窗内说明「本次覆盖」语义")
_dv = (PLUGIN_DIR / "src" / "views" / "DashboardView.vue").read_text(encoding="utf-8")
check("跟随设置页「拉取来源」" in _dv, "仪表盘入口标明来源跟随设置页（两入口语义可区分）")

# ─────────────────────────────────────────────
print("\n[T6] issue #5：前端开关 + 配置接线 + 写回挂载")
# ─────────────────────────────────────────────
check(hasattr(cst, "CFG_EMBY_ROLE_SYNC") and cst.CFG_EMBY_ROLE_SYNC == "emby_role_sync",
      "constants 新增 CFG_EMBY_ROLE_SYNC")
check(cst.DEFAULT_EMBY_ROLE_SYNC is False, "默认关（对外部系统的写操作保守默认）")
check("_emby_role_sync: bool = constants.DEFAULT_EMBY_ROLE_SYNC" in _SRC, "类属性默认值接线")
check("constants.CFG_EMBY_ROLE_SYNC: bool(getattr(self, \"_emby_role_sync\"" in _SRC,
      "_dump_config 下发该键（设置页读得到）")
check("_ers = constants.safe_bool(config.get(constants.CFG_EMBY_ROLE_SYNC)" in _SRC,
      "_load_config 解析该键")
check("self.__dict__.pop(\"_emby_role_id_cache\", None)" in _SRC, "开关变化时清空 itemId 反查缓存")
_rs = _code(_grab_method(_SRC, "_restore_item_to_nfo"))
check("self._emby_sync_item_roles(" in _rs and "\"emby_roles\": _ers" in _rs,
      "角色同步挂在写回成功路径（自动写回/单条/全部写回一次覆盖）")
check("not bool(getattr(self, \"_nfo_preview\", False))" in _rs, "预览模式不同步（与写回策略一致）")
_sv = (PLUGIN_DIR / "src" / "views" / "SettingsView.vue").read_text(encoding="utf-8")
check("emby_role_sync: false," in _sv and 'v-model="config.emby_role_sync"' in _sv,
      "设置页新增「角色译文同步到 Emby 条目」独立开关")
_dist = list((PLUGIN_DIR / "dist" / "assets").glob("__federation_expose_Page-*.js"))
check(bool(_dist) and "角色译文同步到 Emby 条目" in _dist[0].read_text(encoding="utf-8", errors="replace"),
      "前端 dist 已重建并包含新开关文案")

# ─────────────────────────────────────────────
print("\n[T7] worker 热重载守卫：跨代共享注册表")
# ─────────────────────────────────────────────
_nsReg = {"threading": __import__("threading"), "Dict": Dict, "Any": Any}
exec(_grab_method(_SRC, "_worker_registry"), _nsReg)
_reg1 = _nsReg["_worker_registry"]
_nsReg2 = {"threading": __import__("threading"), "Dict": Dict, "Any": Any}
exec(_grab_method(_SRC, "_worker_registry"), _nsReg2)
_reg2 = _nsReg2["_worker_registry"]          # 模拟热重载后的「新一代」函数对象


class _Gen1:
    pass


class _Gen2:
    pass


_g1, _g2 = _Gen1(), _Gen2()
_reg1()["EPL:writeback"] = _g1
check(_reg1().get("EPL:writeback") is _g1, "注册表写入可读回")
_reg2()["EPL:writeback"] = _g2               # 新一代实例接管（不同模块代次）
check(_reg1().get("EPL:writeback") is _g2,
      "**旧代次线程也能看到新代次写入**（注册表跨热重载共享 → 守卫不再恒不成立）")
check(getattr(__import__("threading"), "_epl_worker_reg", None) is not None,
      "注册表挂在常驻 threading 模块上（随进程消亡、不被插件重载重建）")
check('getattr(self.__class__, "_wb_active", None)' not in _SRC, "写回守卫不再读类属性")
check('getattr(self.__class__, "_tx_active", None)' not in _SRC, "翻译守卫不再读类属性")
check('_worker_registry()[f"{self.__class__.__name__}:writeback"] = self' in _SRC
      and '_worker_registry().get(f"{_pid}:writeback")' in _SRC, "写回启动/守卫都走注册表")
check('_worker_registry()[f"{self.__class__.__name__}:translate"] = self' in _SRC
      and '_worker_registry().get(f"{_pid}:translate")' in _SRC, "翻译启动/守卫都走注册表")

# ─────────────────────────────────────────────
print("\n[T8] 窄屏徽章文案：竖屏显示短前缀「待翻译 」（不再只剩数字）")
# ─────────────────────────────────────────────
_lv = (PLUGIN_DIR / "src" / "views" / "LibraryView.vue").read_text(encoding="utf-8")
check('<span class="epl-pending-prefix">有任务 · 待翻译 </span><span class="epl-pending-prefix-short">待翻译 </span>'
      in _lv, "徽章同时带长前缀与窄屏短前缀")
check(".epl-pending-prefix-short { display: none; }" in _lv, "短前缀默认隐藏（宽屏只用长前缀）")
_mq = _lv.split("@media (max-width: 600px) {")[1].split("\n}")[0]
check(".epl-pending-prefix { display: none; }" in _mq
      and ".epl-pending-prefix-short { display: inline; }" in _mq,
      "≤600px：隐藏长前缀的同时**显示短前缀**（旧版只隐藏、徽章只剩数字）")
check('<span v-else>无待翻译</span>' in _lv
      and "txPreview.items_pending > 0 ? 'warning' : 'success'" in _lv,
      "无任务态文案「无待翻译」+ 绿色 success（与 PC 一致，未改动）")

# ─────────────────────────────────────────────
print("\n[T9] 写回范围（哪一排）：单条写入 / 全部写回 都能选，默认两排")
# ─────────────────────────────────────────────
check("def _restore_item_to_nfo(self, item_id: str, server_id: str = \"\", auto: bool = False,\n                             scope: str = \"both\")" in _SRC,
      "_restore_item_to_nfo 新增 scope 参数（默认 both）")
check("def _write_nfo_once(self, item_id: str, server_id: str, nfo_path: str,\n                        people_records: Optional[list] = None, auto: bool = False,\n                        scope: str = \"both\")" in _SRC,
      "_write_nfo_once 透传 scope")
check("auto=auto, scope=scope)" in _SRC, "落盘入口把 scope 一路传下去")
_rl = _code(_grab_method(_SRC, "_restore_nfo_from_db_locked"))
check('_want_person = _sc in ("person", "both")' in _rl and '_want_role = _sc in ("role", "both")' in _rl,
      "写回核心按 scope 决定是否构造 person_map / role_map")
check("if _want_person:" in _rl and "if _want_role:" in _rl,
      "未选中的那一排映射保持为空（apply 自然不动那排文本）")
check("if _want_role and doc.root is not None:" in _rl, "角色一致性补写也被 scope 门控")
check('_sc not in ("role", "both")' in _grab_method(_SRC, "_restore_item_to_nfo"),
      "单条写回：范围不含第二排时明确回「本次未包含第二排」")
check('if _scope in ("person", "both") \\' in _grab_method(_SRC, "_api_db_restore"),
      "单条写回：第一排 Person 改名仅在范围含第一排时执行")

# 全部写回：入参 → worker → 通知
_wa = _grab_method(_SRC, "_api_db_writeback_all")
check('(data or {}).get("target_scope")' in _wa and '{"scope": _scope}' in _wa,
      "全部写回接口接受 target_scope 并传给 worker")
_wbw = _grab_method(_SRC, "_writeback_all_worker")
check('(data or {}).get("scope")' in _wbw and "scope=_scope" in _wbw, "worker 解析并透传 scope")
check("🧭 写回范围" in _wbw, "通知新增「写回范围」行")
check("🎭 Emby 角色" in _wbw, "通知新增「Emby 角色」行（第二排写入 Emby 的结果）")
check('_scope not in ("role", "both")' in _wbw and "本次未包含第二排" in _wbw,
      "范围不含第二排时明说「本次未包含第二排」")
check("本次未包含第二排" in _wbw, "（重复确认）范围提示文案存在")
check('if _scope in ("person", "both") and not bool(getattr(self, "_nfo_preview", False)):' in _wbw,
      "全部写回：第一排 Emby 人名同步仅在范围含第一排时执行")

# 行为级：跑真实 _writeback_all_worker（stub 掉落盘），验证 scope 透传 + 通知内容
_nsWB = {"logger": logger, "Dict": Dict, "Optional": Optional, "Any": Any, "constants": cst,
         "NotificationType": type("NotificationType", (), {"Manual": "Manual"})}
exec(_grab_method(_SRC, "_writeback_all_worker"), _nsWB)


class _WbDb:
    def library_items(self, **kw):
        return [{"item_id": "i1", "server_id": ""}, {"item_id": "i2", "server_id": ""}]


class _WbSelf:
    _writeback_all_worker = _nsWB["_writeback_all_worker"]

    def __init__(self, role_status="ok", enable_role=True, sends=None):
        self._people_db = _WbDb()
        self._writeback_status = {}
        self._wb_stop = False
        self._nfo_preview = False
        self._nfo_backup = False
        self._lock_cast = False
        self._nfo_episode_overwrite = False
        self._sync_direction = "s2e"
        self._emby_name_sync = False
        self._emby_role_sync = enable_role
        self._notify_on_complete = True
        self.got_scope = []
        self.logs = []
        self.msgs = []
        self._role_status = role_status
        self._sends = sends if sends is not None else self.msgs

    def _restore_item_to_nfo(self, iid, sid="", auto=False, scope="both"):
        self.got_scope.append(scope)
        _er = ({"changed": 3, "status": "ok", "reason": "已同步 3 处"}
               if self._role_status == "ok"
               else {"changed": 0, "status": self._role_status, "reason": "未取到 Emby itemId"})
        return {"success": True, "message": "ok", "data": {"changed": 5, "scope": scope,
                                                           "emby_roles": _er}}

    def _wb_db(self):
        class _D:
            def set_status(self, **kw): return 0
        return _D()

    def _wb_item_fp(self, *a, **k):
        return ""

    def _push_log(self, lvl, msg):
        self.logs.append(msg)

    def post_message(self, mtype=None, title="", text=""):
        self.msgs.append(text)

    def _set_task_running(self, *a, **k):
        pass

    def _save_state(self):
        pass

    def _pool_sync_all(self, ctx=""):
        return {"total": 0}


_o = _WbSelf()
_o._writeback_all_worker({"scope": "role"})
check(_o.got_scope == ["role", "role"], f"全部写回按 scope=role 逐条透传，实际 {_o.got_scope}")
check(_o.msgs and "🧭 写回范围：仅第二排角色" in _o.msgs[0],
      f"通知含范围行，实际 {_o.msgs[0] if _o.msgs else '（无）'}")
check(_o.msgs and "🎭 Emby 角色：同步 6 处（2 个条目）" in _o.msgs[0],
      f"通知含第二排 Emby 同步结果（2 条目 × 3 处），实际 {_o.msgs[0] if _o.msgs else '（无）'}")
_o = _WbSelf()
_o._writeback_all_worker({"scope": "person"})
check(_o.msgs and "🎭 Emby 角色：本次未包含第二排" in _o.msgs[0],
      "范围=仅第一排 → 通知明说本次不含第二排")
_o = _WbSelf(enable_role=False)
_o._writeback_all_worker({})
check(_o.got_scope == ["both", "both"], "未传 scope → 默认两排")
check(_o.msgs and "🎭 Emby 角色：未开启" in _o.msgs[0],
      "默认两排 + 角色同步开关关 → 通知提示未开启（不静默）")
_o = _WbSelf(role_status="no_item_id")
_o._writeback_all_worker({"scope": "both"})
check(_o.msgs and "未取到 itemId 2" in _o.msgs[0],
      f"取不到 Emby itemId 时汇总回报，实际 {_o.msgs[0] if _o.msgs else '（无）'}")

# 前端：两个入口都走写回范围弹窗
_lv2 = (PLUGIN_DIR / "src" / "views" / "LibraryView.vue").read_text(encoding="utf-8")
check("openWritebackDlg('item')" in _lv2 and "openWritebackDlg('library')" in _lv2,
      "「写入」与「全部写回」都先开写回范围弹窗")
check('v-model="wbScope"' in _lv2 and 'value="both"' in _lv2 and 'value="person"' in _lv2
      and 'value="role"' in _lv2, "弹窗提供 两排/仅第一排/仅第二排 三个单选")
check("wbScope.value = 'both'" in _lv2, "弹窗默认选中「两排都写」")
check("target_scope: _scope" in _lv2, "前端把选择作为 target_scope 提交")
check("可选只写第一排" in _lv2, "按钮提示写明可选写回范围")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)