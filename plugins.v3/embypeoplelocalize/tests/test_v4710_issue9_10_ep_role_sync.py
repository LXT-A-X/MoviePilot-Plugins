# -*- coding: utf-8 -*-
"""v4.7.10 回归：GitHub issue #10（item_identity 层级）+ issue #9（单集条目级角色同步）。

覆盖：
  T1  issue #10 根因   `item_identity` 层级改为**聚合判定**（任一 Series 行 → series），
                       行选取优先与层级一致的行；`item_level_from_types` 口径（真 SQLite）
  T2  issue #10 建议 2 反查落空**退回再试**（Series/Movie → 不带类型限制），首次命中不退回
  T3  issue #10 建议 3 no_item_id / noop / no_people 各补一条 INFO（此前纯静默）
  T4  issue #9 单集级  剧条目写完再枚举各**单集条目**写同一份 role_map
                       （电影跳过 / 开关可关 / 单轮上限 / 非剧集 404 自然跳过）
  T5  issue #9 坑 2     role_map 取**多来源并集**（空来源打底 + 目标服务器覆盖）
  T6  配置接线          constants / _load_config / config getter / 设置页开关
"""
import sys
import os
import re
import time
import types
import textwrap
import tempfile
import importlib.util
from pathlib import Path
from typing import Any, Optional, Dict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl4710_"))
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
_CONST = (PLUGIN_DIR / "constants.py").read_text(encoding="utf-8")
_VUE = (PLUGIN_DIR / "src" / "views" / "SettingsView.vue").read_text(encoding="utf-8")
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
_m = types.ModuleType("app"); _s = types.ModuleType("app.sdk")
_l = types.ModuleType("app.sdk.logging"); _l.logger = logger
_c = types.ModuleType("app.sdk.config")
_c.settings = type("S", (), {"CONFIG_PATH": str(TMP)})()
_req = types.ModuleType("requests")


class _RS:
    def __init__(self):
        self.headers = {}

    def close(self):
        pass


_req.Session = _RS
_sch = types.ModuleType("app.schemas"); _sch.ServiceInfo = object
sys.modules.update({"app": _m, "app.sdk": _s, "app.sdk.logging": _l, "app.sdk.config": _c,
                    "requests": _req, "app.schemas": _sch})

_dspec = importlib.util.spec_from_file_location("epl_db4710", PLUGIN_DIR / "db.py")
dbm = importlib.util.module_from_spec(_dspec)
_dspec.loader.exec_module(dbm)
_cspec = importlib.util.spec_from_file_location("epl_cli4710", PLUGIN_DIR / "emby_client.py")
clim = importlib.util.module_from_spec(_cspec)
_cspec.loader.exec_module(clim)
_kspec = importlib.util.spec_from_file_location("epl_const4710", PLUGIN_DIR / "constants.py")
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


print("=" * 72)
print("v4.7.10 回归：issue #10（层级聚合 / 反查退回 / 不静默）+ issue #9（单集条目级）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] issue #10 根因：item_identity 层级聚合（真 SQLite）")
# ─────────────────────────────────────────────
check(dbm.item_level_from_types(["Episode", "Episode", "Series"]) == "series",
      "任一 Series 行 → series（斗破苍穹 3217 集行 + 13 剧行 也判为剧）")
check(dbm.item_level_from_types(["episode"]) == "episode", "只有集行 → episode")
check(dbm.item_level_from_types(["Movie"]) == "movie", "电影 → movie（单集级同步会跳过）")
check(dbm.item_level_from_types(["Episode", "Movie"]) == "movie", "movie 优先于 episode")
check(dbm.item_level_from_types(["", None]) == "" and dbm.item_level_from_types([]) == "",
      "无层级信息 → 空串（调用方按未知处理）")

dbm.PeopleDb.ensure_table()
_pdb = dbm.PeopleDb()
PID = "EmbyPeopleLocalize4710"
ITEM = "tmdb:79481"
dbm._x("DELETE FROM person WHERE plugin_id=?", (PID,))
# 复现 issue #10 的混合形态：Episode 行在前（person_index 更小）+ 13 行 Series
for _i in range(5):
    dbm._x("INSERT INTO person (plugin_id, server_id, item_id, item_type, season_num, episode_num, "
           "person_index, name_before, role_before, media_provider, media_id, emby_item_id, nfo_path) "
           "VALUES (?,?,?,?,1,?,?,?,?,?,?,?,?)",
           (PID, "Emby_S1", ITEM, "Episode", _i + 1, _i, f"n{_i}", f"r{_i}", "tmdb", "79481",
            "", f"X:/tv/dpcq/S01E{_i + 1:02d}.nfo"))
for _i in range(2):
    dbm._x("INSERT INTO person (plugin_id, server_id, item_id, item_type, person_index, name_before, "
           "role_before, media_provider, media_id, emby_item_id, nfo_path) "
           "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
           (PID, "Emby_S1", ITEM, "Series", 50 + _i, f"s{_i}", f"sr{_i}", "tmdb", "79481",
            "27475" if _i == 0 else "", "X:/tv/dpcq/tvshow.nfo"))
_ident = _pdb.item_identity(plugin_id=PID, item_id=ITEM, server_id=None) or {}
check(str(_ident.get("item_type")) == "series",
      f"整条目层级 = series（不再被 person_index 最小的 Episode 行带偏），实际 {_ident.get('item_type')}")
check(str(_ident.get("media_provider")) == "tmdb" and str(_ident.get("media_id")) == "79481",
      "媒体身份仍可拿到（反查 Emby itemId 的唯一入口）")
check(str(_ident.get("emby_item_id")) == "27475",
      f"行选取优先「与层级一致」的行 → 取到剧级 emby_item_id，实际 {_ident.get('emby_item_id')}")

dbm._x("DELETE FROM person WHERE plugin_id=?", (PID,))
dbm._x("INSERT INTO person (plugin_id, server_id, item_id, item_type, person_index, name_before, "
       "media_provider, media_id) VALUES (?,?,?,?,?,?,?,?)",
       (PID, "", "tmdb:1", "Movie", 0, "a", "tmdb", "1"))
check(str((_pdb.item_identity(plugin_id=PID, item_id="tmdb:1", server_id=None) or {}).get("item_type")) == "movie",
      "纯电影条目仍判 movie（单集级同步不触发）")

# ─────────────────────────────────────────────
print("\n[T2] issue #10 建议 2：反查退回再试（Series/Movie → 无类型限制）")
# ─────────────────────────────────────────────
_nsRoleId = {"logger": logger, "str": str, "cli": None}
exec(_grab_method(_SRC, "_emby_role_item_id"), _nsRoleId)


class _CliFallback:
    def __init__(self, hit_at):
        self.hit_at = hit_at          # 第几次调用开始返回 itemId（1-based），0 = 永不命中
        self.searches = []

    def search_item_by_provider(self, prov, mid, include_types=None):
        self.searches.append(include_types)
        if self.hit_at and len(self.searches) >= self.hit_at:
            return "27475"
        return ""


class _FallbackSelf:
    _emby_role_item_id = _nsRoleId["_emby_role_item_id"]


class _DbIdent:
    def __init__(self, ident, eid_by_path=""):
        self._ident, self._eid = ident, eid_by_path

    def item_identity(self, **kw):
        return self._ident

    def emby_item_id_by_nfo_path(self, **kw):
        return self._eid


class _RoleIdSelf:
    _emby_role_item_id = _nsRoleId["_emby_role_item_id"]

    def __init__(self, ident, eid_by_path=""):
        self._people_db = _DbIdent(ident, eid_by_path)


_ident_ep = {"emby_item_id": "", "media_provider": "tmdb", "media_id": "79481",
             "item_type": "episode"}
_cf = _CliFallback(hit_at=2)
_out = _RoleIdSelf(_ident_ep)._emby_role_item_id(_cf, server_id="S1", item_id="79481")
check(_out == "27475", f"首次落空 → 退回 Series/Movie 命中，实际 {_out!r}")
check(_cf.searches == [["Episode"], ["Series", "Movie"]],
      f"退回顺序：先推导层级 → 再 Series/Movie，实际 {_cf.searches}")
check(any("反查需退回Series/Movie才命中" in _m for _m in logger.infos),
      "退回命中落一条 INFO（可排查「库里层级=episode」这类数据）")

_cf2 = _CliFallback(hit_at=1)
_out2 = _RoleIdSelf(_ident_ep)._emby_role_item_id(_cf2, server_id="S1", item_id="79482")
check(_out2 == "27475" and len(_cf2.searches) == 1,
      f"首次即命中 → 不做多余请求，实际 {_cf2.searches}")

_cf3 = _CliFallback(hit_at=0)
logger.infos.clear()
_out3 = _RoleIdSelf({"emby_item_id": "", "media_provider": "tmdb", "media_id": "79483",
                     "item_type": ""})._emby_role_item_id(_cf3, server_id="S1", item_id="79483")
check(_cf3.searches[-1] is None and _out3 == "",
      f"推导层级落空 → 最后**不带类型限制**再试，实际 {_cf3.searches}")


class _CliNoneHit(_CliFallback):
    def search_item_by_provider(self, prov, mid, include_types=None):
        self.searches.append(include_types)
        return "27475" if include_types is None else ""


_cf5 = _CliNoneHit(hit_at=0)
_out5 = _RoleIdSelf(_ident_ep)._emby_role_item_id(_cf5, server_id="S1", item_id="79485")
check(_out5 == "27475" and _cf5.searches[-1] is None,
      f"只有「不带类型限制」能命中时也能救回（实测救回路径），实际 {_cf5.searches}")
_cf4 = _CliFallback(hit_at=0)
check(_RoleIdSelf(_ident_ep)._emby_role_item_id(_cf4, server_id="S1", item_id="79484") == "",
      "全部落空 → 仍返回空串（调用方按「无法同步」处理）")

# ─────────────────────────────────────────────
print("\n[T3] issue #10 建议 3：no_item_id / noop / no_people 不再静默")
# ─────────────────────────────────────────────
_nsRole = {"logger": logger, "Dict": Dict, "constants": cst, "Any": Any, "Optional": Optional,
           "time": time, "item_level_from_types": dbm.item_level_from_types,
           "ITEM_FOUND": clim.ITEM_FOUND, "ITEM_NOT_FOUND": clim.ITEM_NOT_FOUND}
exec(_grab_method(_SRC, "_emby_sync_item_roles"), _nsRole)
exec(_grab_method(_SRC, "_emby_sync_episode_roles"), _nsRole)
exec(_grab_method(_SRC, "_emby_role_item_id"), _nsRole)


class _Cli:
    def __init__(self, series=("noop", 0), ep=("noop", 0), eps=None, ep_status=None):
        self.series, self.ep = series, ep
        self.eps = eps or []
        self.ep_status = ep_status if ep_status is not None else (clim.ITEM_FOUND, self.eps, "")
        self.calls = []
        self.ep_calls = 0

    def update_item_roles(self, iid, role_map):
        self.calls.append(iid)
        return self.series if iid == "SERIES" else self.ep

    def get_series_episodes_status(self, sid, limit=200):
        self.ep_calls += 1
        return self.ep_status

    def search_item_by_provider(self, prov, mid, include_types=None):
        return "SERIES"


class _DbRows:
    def __init__(self, rows, ident=None, by_scope=None):
        self.rows, self.ident, self.by_scope = rows, ident or {"emby_item_id": "SERIES"}, by_scope

    def people_of_item(self, **kw):
        if self.by_scope is not None:
            return self.by_scope.get(str(kw.get("server_id") or ""), [])
        return self.rows

    def item_identity(self, **kw):
        return self.ident

    def emby_item_id_by_nfo_path(self, **kw):
        return ""


class _SyncSelf:
    _emby_sync_item_roles = _nsRole["_emby_sync_item_roles"]
    _emby_sync_episode_roles = _nsRole["_emby_sync_episode_roles"]
    _emby_role_item_id = _nsRole["_emby_role_item_id"]
    _emby_role_ep_sync = True

    def __init__(self, db, cli, enabled=True, ep_sync=True):
        self._people_db, self._cli = db, cli
        self._emby_role_sync = enabled
        self._emby_role_ep_sync = ep_sync

    def _emby_client_for_server(self, server_id="", allow_legacy_fallback=True):
        return self._cli, ""


_rows_role = [{"role_before": "A", "role_after": "甲", "item_type": "Series"},
              {"role_before": "B", "role_after": "乙", "item_type": "Episode"}]

# no_item_id（此前完全静默 → 现在必有 INFO）
logger.infos.clear()
_r = _SyncSelf(_DbRows(_rows_role, {"emby_item_id": "", "media_provider": "nfo", "media_id": "",
                                    "item_type": "Series"}),
               _Cli())._emby_sync_item_roles(item_id="79481", server_id="S1", ctx="自动写回")
check(str(_r.get("status")) == "no_item_id"
      and any("未取到 Emby itemId" in _m and "第二排无法写入 Emby 条目级" in _m for _m in logger.infos),
      f"no_item_id 落 INFO（含 server_id），实际 {logger.infos}")

# 剧条目 noop + 单集命中 → 合并计数、状态 ok
logger.infos.clear()
_cli = _Cli(series=("noop", 0), ep=("ok", 3), eps=[{"Id": "ep1"}, {"Id": "ep2"}, {"Id": "SERIES"}])
_r = _SyncSelf(_DbRows(_rows_role), _cli)._emby_sync_item_roles(item_id="79481", server_id="S1")
check(_r.get("ok") and int(_r.get("changed") or 0) == 6,
      f"剧条目 0 处 + 单集 2 个条目命中 → changed=6，实际 {_r}")
check(_cli.calls == ["SERIES", "ep1", "ep2"], f"剧条目 + 各单集都写同一份 role_map，实际 {_cli.calls}")
check(any("单集 2 个条目命中" in _m for _m in logger.infos),
      f"INFO 里区分「剧条目 N 处 + 单集 M 个条目命中」，实际 {logger.infos}")

# no_people / noop 各一条 INFO
logger.infos.clear()
_SyncSelf(_DbRows(_rows_role), _Cli(series=("no_people", 0),
                                    ep_status=(clim.ITEM_NOT_FOUND, [], "http_404"))
          )._emby_sync_item_roles(item_id="i2", server_id="S1")
check(any("People 名单为空" in _m for _m in logger.infos), f"no_people 落 INFO，实际 {logger.infos}")
logger.infos.clear()
_cli2 = _Cli(series=("noop", 0), eps=[], ep_status=(clim.ITEM_FOUND, [], ""))
_SyncSelf(_DbRows(_rows_role), _cli2)._emby_sync_item_roles(item_id="i3", server_id="S1")
check(any("未命中任何待写角色" in _m and "候选 2 个" in _m for _m in logger.infos),
      f"noop 落 INFO（带候选数），实际 {logger.infos}")

# ─────────────────────────────────────────────
print("\n[T4] issue #9：非电影条目 → 各单集条目写同一份 role_map")
# ─────────────────────────────────────────────
# ① 电影：不枚举单集（无需任何额外请求）
_cli = _Cli(series=("ok", 2), eps=[{"Id": "ep1"}])
_r = _SyncSelf(_DbRows([{"role_before": "A", "role_after": "甲", "item_type": "Movie"}]),
               _cli)._emby_sync_item_roles(item_id="m1", server_id="S1")
check(_cli.ep_calls == 0 and int(_r.get("changed") or 0) == 2,
      f"电影条目不做单集枚举（0 次枚举），实际 {_cli.ep_calls}")
# ② 开关关 → 不枚举（只写剧条目 + nfo）
_cli = _Cli(series=("noop", 0), eps=[{"Id": "ep1"}])
_r = _SyncSelf(_DbRows(_rows_role), _cli, ep_sync=False)._emby_sync_item_roles(item_id="s1", server_id="S1")
check(_cli.ep_calls == 0 and _cli.calls == ["SERIES"],
      f"「角色译文同步到单集条目」关 → 只写剧条目（保持 4.7.9 行为），实际 {_cli.ep_calls}/{_cli.calls}")
# ③ 非剧集 itemId（Emby 404）→ 自然跳过，剧条目结果照常回报
_cli = _Cli(series=("ok", 1), ep_status=(clim.ITEM_NOT_FOUND, [], "http_404"))
_r = _SyncSelf(_DbRows(_rows_role), _cli)._emby_sync_item_roles(item_id="x1", server_id="S1")
check(_r.get("ok") and int(_r.get("changed") or 0) == 1,
      f"itemId 不是剧集 → 单集段跳过、剧条目写入照常回报，实际 {_r}")
# ④ 单轮上限：超出部分留给下一轮
_cap_old = cst.EMBY_ROLE_EP_MAX
cst.EMBY_ROLE_EP_MAX = 2
logger.infos.clear()
_cli = _Cli(series=("noop", 0), ep=("ok", 1),
            eps=[{"Id": f"e{i}"} for i in range(5)])
_r = _SyncSelf(_DbRows(_rows_role), _cli)._emby_sync_item_roles(item_id="cap1", server_id="S1")
check(len(_cli.calls) == 3 and int(_r.get("changed") or 0) == 2,
      f"超过单轮上限 2 → 只处理前 2 个单集（+剧条目共 3 次写），实际 {_cli.calls}")
check(any("超过单轮上限" in _m for _m in logger.infos), "超上限落一条 INFO（说明本轮只处理前 N 个）")
cst.EMBY_ROLE_EP_MAX = _cap_old
# ⑤ 单集写入异常不影响整体（剧条目已成功）
_cli = _Cli(series=("ok", 1), eps=[{"Id": "boom"}])


def _boom(iid, role_map):
    raise RuntimeError("emby down")


_cli.update_item_roles = lambda iid, rm: (_boom(iid, rm) if iid == "boom" else ("ok", 1))
_r = _SyncSelf(_DbRows(_rows_role), _cli)._emby_sync_item_roles(item_id="b1", server_id="S1")
check(_r.get("ok") and int(_r.get("changed") or 0) == 1,
      f"单集写失败被吞掉（非致命），剧条目结果保留，实际 {_r}")

# ─────────────────────────────────────────────
print("\n[T5] issue #9 坑 2：role_map 取多来源并集（空来源打底 + 目标服务器覆盖）")
# ─────────────────────────────────────────────
_scope_rows = {
    "": [{"role_before": "A", "role_after": "甲", "item_type": "Series"},
         {"role_before": "B", "role_after": "旧乙", "item_type": "Episode"}],
    "S1": [{"role_before": "B", "role_after": "乙", "item_type": "Episode"},
           {"role_before": "C", "role_after": "丙", "item_type": "Episode"}],
}
_cli = _Cli(series=("noop", 0), eps=[], ep_status=(clim.ITEM_FOUND, [], ""))
_db = _DbRows(_rows_role, by_scope=_scope_rows)
_SyncSelf(_db, _cli)._emby_sync_item_roles(item_id="u1", server_id="S1")
check(_cli.calls == ["SERIES"], "先写剧条目")
# 通过记录型客户端取实际下发的 role_map
_seen = {}


class _CliRec(_Cli):
    def update_item_roles(self, iid, role_map):
        _seen[iid] = dict(role_map)
        return ("noop", 0)


_cli2 = _CliRec(series=("noop", 0), eps=[], ep_status=(clim.ITEM_FOUND, [], ""))
_SyncSelf(_DbRows(_rows_role, by_scope=_scope_rows), _cli2)._emby_sync_item_roles(item_id="u2",
                                                                                 server_id="S1")
_m2 = _seen.get("SERIES") or {}
check(_m2 == {"A": "甲", "B": "乙", "C": "丙"},
      f"并集：空来源行打底 + 目标服务器行覆盖（B 取服务器译文），实际 {_m2}")
check('_scopes = [""]' in _grab_method(_SRC, "_emby_sync_item_roles"),
      "多来源并集写在 _emby_sync_item_roles（源码级）")
check("server_id=_scp" in _grab_method(_SRC, "_emby_sync_item_roles"),
      "第二个来源查询带 server_id")

# ─────────────────────────────────────────────
print("\n[T6] 配置接线：constants / _load_config / getter / 设置页")
# ─────────────────────────────────────────────
check(getattr(cst, "CFG_EMBY_ROLE_EP_SYNC", "") == "emby_role_ep_sync",
      "constants 新增 CFG_EMBY_ROLE_EP_SYNC")
check(getattr(cst, "DEFAULT_EMBY_ROLE_EP_SYNC", None) is True,
      "默认开（父开关本就默认关；开启角色同步的用户要的正是「第二排稳定」）")
check(int(getattr(cst, "EMBY_ROLE_EP_MAX", 0)) == 800, "单轮单集上限 = 800（issue #9 建议值）")
check("_emby_role_ep_sync: bool = constants.DEFAULT_EMBY_ROLE_EP_SYNC" in _SRC, "类属性默认值接线")
check("_emby_role_ep_sync = constants.safe_bool(\n            config.get(constants.CFG_EMBY_ROLE_EP_SYNC)"
      in _SRC, "_load_config 读取该开关")
check('constants.CFG_EMBY_ROLE_EP_SYNC: bool(getattr(self, "_emby_role_ep_sync"' in _SRC,
      "配置回读（getter）包含该键")
check("emby_role_ep_sync: true," in _VUE and 'v-model="config.emby_role_ep_sync"' in _VUE,
      "设置页默认值 + 开关")
check("写剧与单集两个层级" in _VUE and "每个单集条目自己的" in _VUE,
      "设置页说明已更新为「剧 + 单集」两层（issue #9 建议）")
check("get_series_episodes_status" in _grab_method(_SRC, "_emby_sync_episode_roles"),
      "单集枚举复用既有客户端接口（不新增 Emby 接口）")
check("update_item_roles" in _grab_method(_SRC, "_emby_sync_episode_roles"),
      "单集写入复用 update_item_roles（精确命中才改 / 只改 Role）")

print("\n" + "=" * 72)
print(f"结果: {_N[0]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)