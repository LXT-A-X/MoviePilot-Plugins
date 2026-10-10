# -*- coding: utf-8 -*-
"""v4.6.115 回归测试：一个媒体库多条 Locations（全部路径参与显示与扫描）。

运行：python tests/test_v4115_multi_locations.py

覆盖：
  1 emby_client.get_libraries 返回**全部** Locations（Path 保留=第一个）
  2 _get_emby_libraries 逐路径构建 paths[]（每条带映射/存在性/key）+ 旧字段兼容
  3 _selected_library_paths：扁平化全部路径 + 同服去重 + 父子剪枝 + 跨服务器不合并
  4 _library_name_for_path：最长前缀优先（父子库并存时归更具体的库）
  5 路径映射：服务器级默认 + 路径级覆盖（_path_mapping_for / _resolve_library_path）
  6 _check_one_path(idx) / check_all 逐路径 / browse 选路径
  7 前端：逐路径行渲染 + 映射▾ + 扫描根汇总 + 路径级 pathCheck key
"""
import sys
import re
import os
import types
import textwrap
import tempfile
import importlib.util
from pathlib import Path
from typing import Any, List, Optional, Dict, Tuple

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl115_"))
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
_CLI = (PLUGIN_DIR / "emby_client.py").read_text(encoding="utf-8")
_SV = (PLUGIN_DIR / "src" / "views" / "SettingsView.vue").read_text(encoding="utf-8")

_N = [0, 0]


def check(cond, msg):
    _N[0] += 1
    if cond:
        print(f"  [PASS] {msg}")
    else:
        _N[1] += 1
        print(f"  [FAIL] {msg}")


class _Logger:
    def debug(self, *a, **k): pass
    def info(self, *a, **k): pass
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

_cs = importlib.util.spec_from_file_location("epl_cli115", PLUGIN_DIR / "emby_client.py")
clim = importlib.util.module_from_spec(_cs)
_cs.loader.exec_module(clim)


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
print("v4.6.115 回归测试（媒体库多 Locations：显示即扫描范围）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] emby_client.get_libraries：返回全部 Locations")
# ─────────────────────────────────────────────
check('"Locations": locs,' in _CLI, "返回体新增 Locations 列表")
check('"Path": locs[0] if locs else "",' in _CLI, "Path 保留=第一个（兼容旧调用点）")
check("next((str(x).strip()" not in _CLI, "已移除「只取第一个 Location」的 next(...)")


class _Resp:
    def __init__(self, code, payload):
        self.status_code, self._p = code, payload

    def json(self):
        return self._p


class _Sess:
    def __init__(self, payload):
        self._payload = payload

    def get(self, *a, **k):
        return _Resp(200, self._payload)

    def close(self):
        pass


_libs_payload = [
    {"ItemId": "L1", "Name": "华语电影", "CollectionType": "movies",
     "Locations": ["/video/影视资源/华语电影", "/video/影视资源/外语电影",
                   "/video/影视资源/pt硬链接资源/华语电影", "/video/影视资源/pt硬链接资源/外语电影"]},
    {"ItemId": "L2", "Name": "合集", "CollectionType": "folder", "Locations": []},
]
_c = clim.EmbyClient("http://emby.test:8096", "k")
_c.session = _Sess(_libs_payload)
_c._get_user_id = lambda: "u1"
_libs = _c.get_libraries()
check(len(_libs) == 2, f"两个库都返回，实际 {len(_libs)}")
check(len(_libs[0]["Locations"]) == 4, f"库1 的 4 条 Locations 全部返回，实际 {_libs[0]['Locations']}")
check(_libs[0]["Path"] == "/video/影视资源/华语电影", "Path = 第一条（兼容）")
check(_libs[1]["Locations"] == [] and _libs[1]["Path"] == "", "合集库无 Locations → 空（界面显示空）")

# ─────────────────────────────────────────────
print("\n[T2] _get_emby_libraries：逐路径构建 paths[] + 旧字段兼容")
# ─────────────────────────────────────────────
_ns = {"logger": logger, "EmbyClient": None, "os": os, "time": __import__("time"),
       "List": List, "Dict": Dict, "Optional": Optional, "Tuple": Tuple, "Any": Any,
       "ServiceInfo": object, "NotificationType": object, "json": __import__("json")}
for _n in ("_get_emby_libraries", "_path_mapping_for", "_server_mapping",
           "_migrate_legacy_mapping_for", "_apply_root_replace", "_canonical_server_id",
           "_get_all_emby_services", "_get_server_identifier", "_get_service_url",
           "_get_service_api_key", "_get_service_user_id"):
    try:
        exec(_grab_method(_SRC, _n), _ns)
    except AssertionError:
        pass
# _apply_root_replace / _seg_prefix_match 来自 PathUtilsMixin（classmethod）→ 逐字执行真实实现
_PU = (PLUGIN_DIR / "path_utils.py").read_text(encoding="utf-8")
_nsPU = {"re": re}
for _n in ("_norm_seg_path", "_looks_windows_path", "_seg_prefix_match", "_apply_root_replace"):
    exec(_grab_method(_PU, _n), _nsPU)


class _PUCls:
    @staticmethod
    def _norm_seg_path(p):
        return _nsPU["_norm_seg_path"](p)

    @staticmethod
    def _looks_windows_path(p):
        return _nsPU["_looks_windows_path"](p)

    @classmethod
    def _apply_root_replace(cls, path, f, t):
        return _nsPU["_apply_root_replace"](cls, path, f, t)

    @classmethod
    def _seg_prefix_match(cls, path, prefix):
        return _nsPU["_seg_prefix_match"](cls, path, prefix)


def _arr(path, f, t):
    return _PUCls._apply_root_replace(path, f, t)


class _FakeClient:
    def __init__(self, *a, **k):
        pass

    def get_libraries(self):
        return [
            {"Id": "L1", "Name": "华语电影", "Type": "movies",
             "Path": "/video/影视资源/华语电影",
             "Locations": ["/video/影视资源/华语电影", "/video/影视资源/外语电影"]},
            {"Id": "L2", "Name": "合集", "Type": "folder", "Path": "", "Locations": []},
        ]


class _G:
    _get_emby_libraries = _ns["_get_emby_libraries"]
    _path_mapping_for = _ns["_path_mapping_for"]
    _server_mapping = _ns["_server_mapping"]

    def __init__(self, maps=None):
        self._lib_cache = None
        self._lib_cache_ts = 0
        self._legacy_mapping = ("", "")
        self._nfo_path_mappings = maps or []
        self._use_proxy = False

    def _get_all_emby_services(self):
        return ["svc1"]

    def _get_server_identifier(self, svc):
        return "S1"

    def _get_service_url(self, svc):
        return "http://emby.test:8096"

    def _get_service_api_key(self, svc):
        return "k"

    def _get_service_user_id(self, svc):
        return "u1"

    def _migrate_legacy_mapping_for(self, *a, **k):
        return False

    def _canonical_server_id(self, sid):
        return sid

    def _apply_root_replace(self, path, f, t):
        return _arr(path, f, t)


_ns["EmbyClient"] = _FakeClient
_g = _G()
_libs2 = _g._get_emby_libraries()
check(len(_libs2) == 2, "两个库都返回")
_r1 = _libs2[0]
check(len(_r1["paths"]) == 2 and _r1["path_count"] == 2, f"库1 展开 2 条路径，实际 {_r1.get('path_count')}")
check([p["emby_path"] for p in _r1["paths"]] == ["/video/影视资源/华语电影", "/video/影视资源/外语电影"],
      "逐条给出 emby_path")
check(all(p["key"] == f"S1:L1:{i}" for i, p in enumerate(_r1["paths"])), "每条路径带唯一 key（skey:lib_id:idx）")
check(_r1["emby_path"] == "/video/影视资源/华语电影" and _r1["path"] == "/video/影视资源/华语电影",
      "旧字段（emby_path/path）= 第一条（兼容）")
check(_r1["path_exists"] == _r1["paths"][0]["exists"], "旧字段 path_exists = 第一条的存在性")
check(_libs2[1]["paths"] == [] and _libs2[1]["path_count"] == 0, "合集库（无 Locations）paths 为空")
check(all("exists" in p and "readable" in p and "is_dir" in p for p in _r1["paths"]),
      "每条路径都带存在性/可读/是否目录")

# ─────────────────────────────────────────────
print("\n[T3] _selected_library_roots / _selected_library_paths：扁平化 + 去重 + 父子剪枝 + 跨服务器不合并")
# ─────────────────────────────────────────────
_nsP = {"List": List, "Dict": Dict, "Tuple": Tuple}
# v4.6.116（P1-07）：扁平化改由 _selected_library_roots 承载，_selected_library_paths 是其投影
exec(_grab_method(_SRC, "_selected_library_roots"), _nsP)
exec(_grab_method(_SRC, "_prune_roots"), _nsP)
exec(_grab_method(_SRC, "_selected_library_paths"), _nsP)


class _Sel:
    _selected_library_roots = _nsP["_selected_library_roots"]
    _prune_roots = staticmethod(_nsP["_prune_roots"])
    _selected_library_paths = _nsP["_selected_library_paths"]

    def __init__(self, libs, selected):
        self._libraries = selected
        self._libs = libs
        self.warns = []

    def _get_emby_libraries(self):
        return self._libs

    def _warn_once(self, key, msg):
        self.warns.append(key)


def _mk_lib(skey, lid, paths):
    return {"skey": skey, "server_id": skey, "lib_id": lid, "full_key": f"{skey}:{lid}",
            "paths": [{"idx": i, "key": f"{skey}:{lid}:{i}", "emby_path": p, "path": p}
                      for i, p in enumerate(paths)]}


# 多路径扁平化
_o = _Sel([_mk_lib("S1", "L1", ["/v/a", "/v/b", "/v/c"])], ["S1:L1"])
check(_o._selected_library_paths() == ["/v/a", "/v/b", "/v/c"],
      f"一个库的 3 条路径全部成为扫描根，实际 {_o._selected_library_paths()}")
# 同服去重
_o = _Sel([_mk_lib("S1", "L1", ["/v/a", "/v/a"])], ["S1:L1"])
check(_o._selected_library_paths() == ["/v/a"], "同服务器内去重")
# 父子剪枝
_o = _Sel([_mk_lib("S1", "L1", ["/v/a", "/v/a/sub"])], ["S1:L1"])
check(_o._selected_library_paths() == ["/v/a"], f"父子并存 → 剪掉子路径，实际 {_o._selected_library_paths()}")
# 跨服务器不合并（同路径不同服务器都要保留）
_o = _Sel([_mk_lib("S1", "L1", ["/v/a"]), _mk_lib("S2", "L1", ["/v/a"])], ["S1:L1", "S2:L1"])
check(sorted(_o._selected_library_paths()) == ["/v/a", "/v/a"],
      f"跨服务器同路径各自保留（不合并），实际 {_o._selected_library_paths()}")
# 未选任何库
_o = _Sel([_mk_lib("S1", "L1", ["/v/a"])], [])
check(_o._selected_library_paths() == [], "未选库 → 空")
# 无 paths 的旧结构兼容
_o = _Sel([{"skey": "S1", "lib_id": "L1", "full_key": "S1:L1", "path": "/v/old"}], ["S1:L1"])
check(_o._selected_library_paths() == ["/v/old"], "旧结构（无 paths）回退到单 path")
# v4.6.116（P1-07）：结构化根保留 server 归属（供 NFO 扫描写入正确来源）
_o = _Sel([_mk_lib("S1", "L1", ["/v/a", "/v/b"])], ["S1:L1"])
_roots = _o._selected_library_roots()
check(len(_roots) == 2
      and all(r.get("server_id") == "S1" and r.get("lib_id") == "L1" for r in _roots)
      and {r.get("path") for r in _roots} == {"/v/a", "/v/b"},
      f"扫描根为结构化对象，保留 server_id/lib_id（实际 {_roots}）")
# 裸 lib_id 在多台服务器同 ID → 歧义跳过（不跨服务器全选）
_o = _Sel([_mk_lib("S1", "L1", ["/v/a"]), _mk_lib("S2", "L1", ["/v/b"])], ["L1"])
check(_o._selected_library_paths() == [] and bool(_o.warns),
      "裸 lib_id 多服务器同 ID → 跳过并告警（不跨服务器全选）")

# ─────────────────────────────────────────────
print("\n[T4] _library_name_for_path：最长前缀优先")
# ─────────────────────────────────────────────
_nsN = {"List": List, "Dict": Dict, "Tuple": Tuple}
exec(_grab_method(_SRC, "_library_name_for_path"), _nsN)


class _NameFor:
    _library_name_for_path = _nsN["_library_name_for_path"]

    def __init__(self, libs):
        self._libs = libs

    def _get_emby_libraries(self):
        return self._libs


_libs_n = [
    {"server_name": "服务器1", "lib_name": "影视资源", "path": "/v",
     "paths": [{"path": "/v"}]},
    {"server_name": "服务器1", "lib_name": "华语电影", "path": "/v/华语电影",
     "paths": [{"path": "/v/华语电影"}, {"path": "/v/外语电影"}]},
]
_n1 = _NameFor(_libs_n)
check(_n1._library_name_for_path("/v/华语电影/片名/tvshow.nfo") == "服务器1 · 华语电影",
      f"父子库并存 → 归更具体的库，实际 {_n1._library_name_for_path('/v/华语电影/片名/tvshow.nfo')}")
check(_n1._library_name_for_path("/v/外语电影/片名/a.nfo") == "服务器1 · 华语电影",
      "命中该库的第 2 条路径 → 同样归它")
check(_n1._library_name_for_path("/v/其它/片名/a.nfo") == "服务器1 · 影视资源",
      "只有父路径命中 → 归父库")
check(_n1._library_name_for_path("/other/a.nfo") == "", "都不命中 → 空（未分类）")
# 列表顺序颠倒也应归更具体的库（不再「第一个命中」）
_n2 = _NameFor(list(reversed(_libs_n)))
check(_n2._library_name_for_path("/v/华语电影/片名/a.nfo") == "服务器1 · 华语电影",
      "库顺序颠倒仍按最长前缀 → 不受列表顺序影响")

# ─────────────────────────────────────────────
print("\n[T5] 路径映射：服务器级默认 + 路径级覆盖")
# ─────────────────────────────────────────────
_nsM = {"Tuple": Tuple, "Optional": Optional, "logger": logger}
for _n in ("_server_mapping", "_path_mapping_for", "_resolve_library_path"):
    exec(_grab_method(_SRC, _n), _nsM)


class _Map:
    _server_mapping = _nsM["_server_mapping"]
    _path_mapping_for = _nsM["_path_mapping_for"]
    _resolve_library_path = _nsM["_resolve_library_path"]

    def __init__(self, maps):
        self._nfo_path_mappings = maps

    def _apply_root_replace(self, path, f, t):
        return _arr(path, f, t)


_maps = [{"server_id": "S1", "from": "/emby", "to": "/mp"}]
_mo = _Map(_maps)
check(_mo._server_mapping("S1") == ("/emby", "/mp"), "服务器级映射可读")
check(_mo._path_mapping_for("S1", "L1", 0) == ("/emby", "/mp", False), "无路径级 → 用服务器级默认")
check(_mo._resolve_library_path("S1", "/emby/华语电影", "L1", 0) == "/mp/华语电影",
      f"统一 resolver 用服务器级映射，实际 {_mo._resolve_library_path('S1', '/emby/华语电影', 'L1', 0)}")
# 路径级覆盖
_maps2 = [{"server_id": "S1", "from": "/emby", "to": "/mp"},
          {"server_id": "S1", "lib_id": "L1", "idx": 1, "from": "/disk2", "to": "/mnt/d2"}]
_mo2 = _Map(_maps2)
check(_mo2._server_mapping("S1") == ("/emby", "/mp"), "服务器级条目仍可取（路径级条目被跳过）")
check(_mo2._path_mapping_for("S1", "L1", 0) == ("/emby", "/mp", False), "idx=0 无覆盖 → 服务器级")
check(_mo2._path_mapping_for("S1", "L1", 1) == ("/disk2", "/mnt/d2", True), "idx=1 命中路径级覆盖")
check(_mo2._resolve_library_path("S1", "/disk2/华语电影", "L1", 1) == "/mnt/d2/华语电影",
      "路径级覆盖生效（该条路径）")
check(_mo2._resolve_library_path("S1", "/emby/华语电影", "L1", 0) == "/mp/华语电影",
      "同库其它路径仍走服务器级默认")
check(_mo2._resolve_library_path("S1", "/disk2/华语电影") == "/disk2/华语电影",
      "未给 lib_id/idx 时不套用路径级覆盖（保持旧行为）")
# 无映射 → 原路径
_mo3 = _Map([])
check(_mo3._resolve_library_path("S1", "/video/影视资源/华语电影") == "/video/影视资源/华语电影",
      "未配置映射 → 原路径（用户实际情况）")

# ─────────────────────────────────────────────
print("\n[T6] 逐路径预检 / 浏览 / 汇总（源码级 + 行为级）")
# ─────────────────────────────────────────────
_nsC = {"logger": logger, "os": os, "Optional": Optional, "Dict": Dict, "List": List,
        "Tuple": Tuple, "ServiceInfo": object}
for _n in ("_check_one_path", "_path_mapping_for", "_server_mapping",
           "_resolve_library_path", "_seg_prefix_match", "_apply_root_replace"):
    try:
        exec(_grab_method(_SRC, _n), _nsC)
    except AssertionError:
        pass


class _Check:
    _check_one_path = _nsC["_check_one_path"]
    _path_mapping_for = _nsC["_path_mapping_for"]
    _server_mapping = _nsC["_server_mapping"]
    _resolve_library_path = _nsC["_resolve_library_path"]

    def __init__(self, libs, maps=None):
        self._libs = libs
        self._nfo_path_mappings = maps or []

    def _get_emby_libraries(self):
        return self._libs

    def _apply_root_replace(self, path, f, t):
        return _arr(path, f, t)

    @staticmethod
    def _seg_prefix_match(path, prefix):
        return True


_d1 = TMP / "华语电影"
_d2 = TMP / "外语电影"
_d1.mkdir(exist_ok=True)
(_d1 / "a.nfo").write_text("<movie/>", encoding="utf-8")
_d2.mkdir(exist_ok=True)
_lib_real = [{"skey": "S1", "lib_id": "L1", "full_key": "S1:L1",
              "paths": [{"idx": 0, "key": "S1:L1:0", "emby_path": str(_d1), "path": str(_d1),
                         "mapping_from": "", "mapping_to": "", "mapping_path_level": False},
                        {"idx": 1, "key": "S1:L1:1", "emby_path": str(_d2), "path": str(_d2),
                         "mapping_from": "", "mapping_to": "", "mapping_path_level": False}]}]
_ck = _Check(_lib_real)
_i0 = _ck._check_one_path("S1", "L1", idx=0)
_i1 = _ck._check_one_path("S1", "L1", idx=1)
check(_i0["path"] == str(_d1) and _i1["path"] == str(_d2), "idx 决定检查哪条路径")
check(_i0["key"] == "S1:L1:0" and _i1["key"] == "S1:L1:1", "返回体带路径唯一 key")
check(_i0["exists"] and _i0["is_dir"], "第 1 条路径真实存在 → exists/is_dir")
check(_i0["nfo_count"] == 1, f"顶层 nfo 计数正确，实际 {_i0.get('nfo_count')}")
check(_ck._check_one_path("S1", "L1")["path"] == str(_d1), "不传 idx → 默认第一条（兼容）")

check("rows.append(self._check_one_path" in _struct if (_struct := _grab_method(_SRC, "_api_nfo_path_check_all")) else False,
      "check_all 逐路径调用 _check_one_path")
check("for p in _ps:" in _struct and "idx=p.get(\"idx\")" in _struct, "check_all 遍历全部路径并传 idx")
_browse = _grab_method(_SRC, "_api_nfo_path_browse")
check("idx: int = -1" in _browse and "_idx = int(idx)" in _browse, "browse 接受 idx（缺省=第一条）")
check("for _x in _ps:" in _browse and 'if int(_x.get("idx")) == _idx' in _browse, "browse 按 idx 选根目录")

# ─────────────────────────────────────────────
print("\n[T7] 前端：逐路径渲染 + 映射▾ + 扫描根汇总")
# ─────────────────────────────────────────────
for _need in ("function libPaths(l)", "function pathKey(l, p)", "function pathOk(l, p)",
              "function pathStateText(l, p)", "function testPath(serverId, libId, idx)",
              "function setPathMapping(", "function clearPathMapping(",
              "function browsePath(g, l, p)", "scanRootSummary"):
    check(_need in _SV, f"前端新增：{_need}")
check('v-for="p in libPaths(l)"' in _SV, "按路径逐条渲染（有几条显示几行）")
check(":key=\"pathKey(l, p)\"" in _SV, "路径行以路径 key 作为渲染 key")
check("libPaths(l).length > 1" in _SV and "个路径）" in _SV, "库名行标注「(N 个路径)」")
check("libOk(l) === null" in _SV and "无路径" in _SV, "无路径库 → 显示空（灰 chip「无路径」）")
check("本次扫描根" in _SV and "个可访问目录" in _SV, "显示「本次扫描根 = N 个可访问目录」汇总")
check("不可访问已跳过" in _SV, "汇总注明不可访问已跳过")
check("idx: b.idx" in _SV, "浏览请求带 idx（进入指定的那条路径）")
check("row.key ||" in _SV, "批量测试结果按路径 key 回填")
check("function _isPathLevel(m)" in _SV and "!_isPathLevel(x)" in _SV,
      "服务器级/路径级映射互相不串（服务器级编辑不误改路径级条目）")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
