# -*- coding: utf-8 -*-
"""v4.7.4 回归测试：恢复（以库为准 · 直接覆盖 Emby）。

覆盖：
  T1 配置项 restore_overwrite_emby（常量 / 加载 / dump / 重置 / 前端开关）
  T2 _emby_sync_item_roles：force 绕过「角色同步」开关（恢复=两排一起写服务器）
  T3 _restore_item_to_nfo：恢复模式下强制第二排 + 触发 Emby 刷新 + data.emby_refresh
  T4 写回 worker：恢复模式绕过「待翻阻塞」
  T5 全部写回：范围强制 both + 通知标题「🔄 恢复完成（已覆盖 Emby）」+ 新增待翻
  T6 EmbyClient.refresh_item → POST /emby/Items/{id}/Refresh
"""
import sys
import os
import re
import types
import textwrap
import tempfile
import importlib.util
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PLUGIN_DIR = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="epl474_"))
_SRC = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
_CONST = (PLUGIN_DIR / "constants.py").read_text(encoding="utf-8")
_EMBY = (PLUGIN_DIR / "emby_client.py").read_text(encoding="utf-8")
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
print("v4.7.4 回归测试（恢复 · 以库为准直接覆盖 Emby）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] 配置项 restore_overwrite_emby")
# ─────────────────────────────────────────────
check('CFG_RESTORE_OVERWRITE_EMBY = "restore_overwrite_emby"' in _CONST,
      "constants：新增 CFG_RESTORE_OVERWRITE_EMBY")
check("DEFAULT_RESTORE_OVERWRITE_EMBY = False" in _CONST, "默认关")
check("_overwrite_emby: bool = constants.DEFAULT_RESTORE_OVERWRITE_EMBY" in _SRC,
      "类属性默认值")
check("self._overwrite_emby = constants.safe_bool(\n            config.get(constants.CFG_RESTORE_OVERWRITE_EMBY)," in _SRC,
      "_load_config 读取该配置")
check("constants.CFG_RESTORE_OVERWRITE_EMBY: bool(getattr(self, \"_overwrite_emby\"," in _SRC,
      "get_form/dump 回传该配置（往返不丢）")
check("self._overwrite_emby = constants.DEFAULT_RESTORE_OVERWRITE_EMBY" in _SRC,
      "重置路径恢复默认")
check("restore_overwrite_emby: false," in _SV and "v-model=\"config.restore_overwrite_emby\"" in _SV,
      "设置页：开关 + 默认值")

# ─────────────────────────────────────────────
print("\n[T2] _emby_sync_item_roles：force 绕过开关")
# ─────────────────────────────────────────────
check('def _emby_sync_item_roles(self, *, item_id: str, server_id: str = "", ctx: str = "",\n'
      '                              force: bool = False) -> dict:' in _SRC,
      "签名新增 force 参数")
check('if not force and not bool(getattr(self, "_emby_role_sync", constants.DEFAULT_EMBY_ROLE_SYNC)):' in _SRC,
      "force=True 时不看「角色译文同步到 Emby」开关（恢复=两排一起写服务器）")

# ─────────────────────────────────────────────
print("\n[T3] _restore_item_to_nfo：恢复模式强制第二排 + 触发 Emby 刷新")
# ─────────────────────────────────────────────
_rb = _grab_method(_SRC, "_restore_item_to_nfo")
check('_ov = bool(getattr(self, "_overwrite_emby", False))' in _rb,
      "读取恢复开关")
check('if _sc not in ("role", "both") and not _ov:' in _rb,
      "恢复模式不再因「仅第一排」跳过第二排同步")
check('force=_ov) or {}' in _rb, "第二排同步带 force=恢复开关")
check('_rf = self._emby_refresh_item(item_id, server_id, ctx="恢复") or {}' in _rb,
      "恢复模式写完后触发 Emby 刷新")
check('"emby_refresh": _rf' in _rb, "结果 data 带 emby_refresh（供上层统计/提示）")
check("def _emby_refresh_item(self, item_id: str, server_id: str = \"\", ctx: str = \"\") -> dict:" in _SRC,
      "新增 _emby_refresh_item")
check("_cli.refresh_item(_eid)" in _SRC, "_emby_refresh_item 调 EmbyClient.refresh_item")

# ─────────────────────────────────────────────
print("\n[T4] 写回 worker：恢复模式绕过「待翻阻塞」")
# ─────────────────────────────────────────────
check('if not chk.get("ready") and not bool(getattr(self, "_overwrite_emby", False)):' in _SRC,
      "_wb_process_item_locked：恢复模式下待翻词条不再阻塞写回（库里有多少写多少）")

# ─────────────────────────────────────────────
print("\n[T5] 全部写回：范围强制 both + 恢复通知")
# ─────────────────────────────────────────────
_wall = _grab_method(_SRC, "_writeback_all_worker")
check('if _ov:\n                _scope = "both"' in _wall or 'if _ov:' in _wall and '_scope = "both"' in _wall,
      "恢复模式范围强制 both（两排一起写）")
check('_title = "🔄 恢复完成（已覆盖 Emby）"' in _wall, "恢复模式通知标题单独一条")
check('_title = "✅ 全部写回完成"' in _wall, "非恢复模式保持原标题")
check("🖥️ 已按「以库为准」覆盖 Emby 服务器元数据（第一排 + 第二排）" in _wall,
      "通知注明已覆盖 Emby 两排")
check("🆕 新增待翻" in _wall and "_new_pending" in _wall,
      "统计并提示「新增待翻」（Emby 新刮、库里没有的保留原样）")
check("elif not _ov and not bool(getattr(self, \"_emby_role_sync\"" in _wall,
      "恢复模式下不误报「Emby 角色未开启」")

# ─────────────────────────────────────────────
print("\n[T6] EmbyClient.refresh_item → POST /emby/Items/{id}/Refresh")
# ─────────────────────────────────────────────
check("def refresh_item(self, item_id: str) -> bool:" in _EMBY, "新增 EmbyClient.refresh_item")
check('f"/emby/Items/{_iid}/Refresh"' in _EMBY, "刷新端点正确")
check('"MetadataRefreshMode": "FullRefresh"' in _EMBY and '"ReplaceAllMetadata": False' in _EMBY,
      "只刷元数据、不整份替换（避免冲掉 Emby 其它信息）")

_nsR = {"logger": logger}
exec(_grab_method(_EMBY, "refresh_item"), _nsR)


class _StubCli:
    def __init__(self): self.calls = []

    def _post(self, path, data=None):
        self.calls.append((path, data))
        return True


_sc = _StubCli()
_ok = _nsR["refresh_item"](_sc, "abc")
check(_ok is True and _sc.calls and _sc.calls[0][0] == "/emby/Items/abc/Refresh",
      "refresh_item 行为：POST 到 /emby/Items/abc/Refresh")
check(_nsR["refresh_item"](_sc, "") is False, "空 itemId → 不请求、返回 False")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
