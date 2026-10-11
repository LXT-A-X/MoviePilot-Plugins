# -*- coding: utf-8 -*-
"""v4.7.5 回归测试：恢复 —— 「删除事件 → 观察期 → 恢复」时自动双写。

设计（与作者确认）：
  · 开关 = 现有「恢复：以库为准直接覆盖 Emby」（不新增开关）；关=不写、开=自动写
  · 触发 = **只认 recovered**（删除事件进观察期 → 同 ID 新版本入库），普通入库/扫描不受影响
  · 内容 = 库里已有的译文 → 双写：nfo 文件 + Emby 服务器（第一排 Person 改名 + 第二排条目级角色）+ 触发刷新
  · 「全部写回 / 写入」**行为完全不变**（4.7.4 对它的改动已撤回）

覆盖：
  T1 配置项 restore_overwrite_emby
  T2 _emby_sync_item_roles：force 绕过开关
  T3 _restore_item_to_nfo：新增 restore 参数 → 双写（第一排 + 第二排 + 刷新）
  T4 写回 worker：恢复绕过「待翻阻塞」，并传 restore=恢复开关
  T5 撤回： 「全部写回」不再被恢复开关改变（范围/通知/统计全部还原）
  T6 EmbyClient.refresh_item
  T7 选项 A：入库只认 recovered 才自动恢复；恢复优先于「自动写回」开关
  T8 v4.7.6：状态 / 文案用「自动写回」用户设置本身（`_wb_auto_setting`），不再被恢复开关顶成 true
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
TMP = Path(tempfile.mkdtemp(prefix="epl475_"))
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
print("v4.7.5 回归测试（恢复 = 删除事件→观察期→恢复 时自动双写）")
print("=" * 72)

# ─────────────────────────────────────────────
print("\n[T1] 配置项 restore_overwrite_emby")
# ─────────────────────────────────────────────
check('CFG_RESTORE_OVERWRITE_EMBY = "restore_overwrite_emby"' in _CONST,
      "constants：CFG_RESTORE_OVERWRITE_EMBY")
check("DEFAULT_RESTORE_OVERWRITE_EMBY = False" in _CONST, "默认关")
check("_overwrite_emby: bool = constants.DEFAULT_RESTORE_OVERWRITE_EMBY" in _SRC, "类属性默认值")
check("self._overwrite_emby = constants.safe_bool(\n            config.get(constants.CFG_RESTORE_OVERWRITE_EMBY)," in _SRC,
      "_load_config 读取")
check("constants.CFG_RESTORE_OVERWRITE_EMBY: bool(getattr(self, \"_overwrite_emby\"," in _SRC, "dump 回传")
check("restore_overwrite_emby: false," in _SV and "v-model=\"config.restore_overwrite_emby\"" in _SV,
      "设置页开关 + 默认值")

# ─────────────────────────────────────────────
print("\n[T2] _emby_sync_item_roles：force 绕过开关")
# ─────────────────────────────────────────────
check('force: bool = False) -> dict:' in _SRC, "签名新增 force")
check('if not force and not bool(getattr(self, "_emby_role_sync", constants.DEFAULT_EMBY_ROLE_SYNC)):' in _SRC,
      "force=True 不看「角色同步」开关")

# ─────────────────────────────────────────────
print("\n[T3] _restore_item_to_nfo：restore 参数 → 双写")
# ─────────────────────────────────────────────
check('scope: str = "both", restore: bool = False) -> dict:' in _SRC, "签名新增 restore 参数")
_rb = _grab_method(_SRC, "_restore_item_to_nfo")
check("_ov = bool(restore)" in _rb, "恢复标记取自 restore 参数（不再直接读全局开关）")
check('if _sc not in ("role", "both") and not _ov:' in _rb, "恢复模式不因「仅第一排」跳过第二排")
check("force=_ov) or {}" in _rb, "第二排同步带 force=恢复标记")
check("_emby_sync_manual_rename(_nb, _na, server_id=server_id)" in _rb,
      "双写第一排：恢复时同步 Emby Person 改名")
check("_emby_refresh_item(item_id, server_id, ctx=\"恢复\")" in _rb, "恢复时触发 Emby 刷新")
check('"emby_refresh": _rf' in _rb, "结果 data 带 emby_refresh")

# ─────────────────────────────────────────────
print("\n[T4] 写回 worker：恢复绕过待翻阻塞 + 传 restore")
# ─────────────────────────────────────────────
check('if not chk.get("ready") and not bool(getattr(self, "_overwrite_emby", False)):' in _SRC,
      "待翻词条在恢复模式不阻塞写回")
check("restore=bool(getattr(self, \"_overwrite_emby\", False)))" in _SRC,
      "常驻写回 worker 传 restore=恢复开关（唯一的恢复入口）")

# ─────────────────────────────────────────────
print("\n[T5] 撤回： 「全部写回」行为不再被恢复开关改变")
# ─────────────────────────────────────────────
_wall = _grab_method(_SRC, "_writeback_all_worker")
check('_title = "🔄 恢复完成（已覆盖 Emby）"' not in _wall, "标题不再被改（撤回 4.7.4）")
check('title="✅ 全部写回完成"' in _wall, "通知标题保持「✅ 全部写回完成」")
check("_new_pending" not in _wall, "不再注入「新增待翻」统计（撤回 4.7.4）")
check('if _ov:\n                _scope = "both"' not in _wall and "_ov" not in _wall,
      "不再强制范围 both（撤回 4.7.4）")
check("self._restore_item_to_nfo(_iid, _sid, scope=_scope)" in _wall,
      "「全部写回」调用不带 restore（行为与旧版一致）")

# ─────────────────────────────────────────────
print("\n[T6] EmbyClient.refresh_item")
# ─────────────────────────────────────────────
check("def refresh_item(self, item_id: str) -> bool:" in _EMBY, "新增 refresh_item")
check('f"/emby/Items/{_iid}/Refresh"' in _EMBY, "刷新端点正确")
check('"ReplaceAllMetadata": False' in _EMBY, "不整份替换")
_nsR = {"logger": logger}
exec(_grab_method(_EMBY, "refresh_item"), _nsR)


class _StubCli:
    def __init__(self): self.calls = []

    def _post(self, path, data=None):
        self.calls.append((path, data))
        return True


_sc = _StubCli()
check(_nsR["refresh_item"](_sc, "abc") is True and _sc.calls[0][0] == "/emby/Items/abc/Refresh",
      "行为：POST /emby/Items/abc/Refresh")
check(_nsR["refresh_item"](_sc, "") is False, "空 itemId → 不请求")

# ─────────────────────────────────────────────
print("\n[T7] 选项 A：只认「恢复」，且优先于「自动写回」开关")
# ─────────────────────────────────────────────
_ing = _grab_method(_SRC, "_ingest_nfo_pending")
check('if recovered and bool(getattr(self, "_overwrite_emby", False)):' in _ing,
      "只在 recovered（删除→观察期→恢复）时自动登记，普通入库不受影响")
check("self._wb_register_item(_riid, _rsid, target_scope=\"both\")" in _ing, "恢复即登记写回（自动）")
check("[Restore] 入库即登记恢复" in _ing, "有 INFO 自证")

_wbe = _grab_method(_SRC, "_wb_writeback_enabled")
check('if bool(getattr(self, "_overwrite_emby", False)):' in _wbe and "return True" in _wbe,
      "写回总门：恢复开关优先于「自动写回」")
_nsW = {}
exec(_wbe, _nsW)


class _S1:
    _overwrite_emby = True
    _auto_writeback = False
    _nfo_preview = True
    _tx_cfg_snapshot = None


class _S2:
    _overwrite_emby = False
    _auto_writeback = False
    _nfo_preview = False
    _tx_cfg_snapshot = None


check(_nsW["_wb_writeback_enabled"](_S1()) is True and _nsW["_wb_writeback_enabled"](_S2()) is False,
      "行为：恢复开→写；恢复关→维持原「自动写回」语义")
check("已自动恢复 Emby：第一排 Person 改名" in _SRC, "恢复通知里注明「已自动恢复 Emby（两排）」")

# ─────────────────────────────────────────────
print("\n[T8] v4.7.6：状态 / 文案用「自动写回」用户设置本身（不掺恢复开关）")
# ─────────────────────────────────────────────
check("def _wb_auto_setting(self) -> bool:" in _SRC, "新增 _wb_auto_setting（纯用户设置）")
check('"auto_writeback": self._wb_auto_setting(),' in _SRC,
      "状态 payload 的 auto_writeback 用 _wb_auto_setting（否则恢复开关会藏掉「全部写回」按钮）")
check('"auto_writeback": self._wb_writeback_enabled(),' not in _SRC,
      "状态 payload 不再复用写回总门（撤回 v4.7.5 的泄漏）")
check(_SRC.count("if self._wb_auto_setting() \\") == 2,
      "两条入队文案（库内翻译 / 重翻）用 _wb_auto_setting")
check(_SRC.count("self._wb_writeback_enabled()") >= 2,
      "写回 worker 门控仍用 _wb_writeback_enabled（保留恢复优先）")
_wbas = _grab_method(_SRC, "_wb_auto_setting")
_nsA = {}
exec(_wbas, _nsA)


class _A1:
    _auto_writeback = True
    _nfo_preview = False


class _A2:
    _auto_writeback = False
    _nfo_preview = False


class _A3:
    _auto_writeback = True
    _nfo_preview = True


check(_nsA["_wb_auto_setting"](_A1()) is True and _nsA["_wb_auto_setting"](_A2()) is False
      and _nsA["_wb_auto_setting"](_A3()) is False,
      "行为：auto_writeback 开且非预览→True；否则 False（与恢复开关无关）")

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
