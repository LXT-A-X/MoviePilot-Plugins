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
  T7 选项 A：入库只认 recovered 才自动恢复；恢复与「自动写回」开关解耦（v4.7.7）
  T8 v4.7.6：状态 / 文案用「自动写回」用户设置本身（`_wb_auto_setting`），不再被恢复开关顶成 true
  T9 v4.7.7：恢复改走队列标记 reason='restore'（真 SQLite：粘性 / 不受指纹幂等约束 / 清回）
  T10 v4.7.8：文件级恢复（只写本次回来的文件）+ 接收通知区分 📥 新入库 / 🔁 恢复入库
  T11 v4.7.9：恢复写回标 phase='restore'、不复用「自动写回」文案；worker 空闲必复位 running（卡片不再挂着）
  T12 v4.7.9：恢复的 Emby 侧按「文件」定位（不再打到同剧别的集）；改名复读校验空值归一
  T13 v4.7.9：入库通知「已有译文」口径补上第二排（只翻第二排也算已译）
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
check('scope: str = "both", restore: bool = False,' in _SRC
      and "only_paths: Optional[set] = None) -> dict:" in _SRC, "签名新增 restore / only_paths 参数")
_rb = _grab_method(_SRC, "_restore_item_to_nfo")
check("_ov = bool(restore)" in _rb, "恢复标记取自 restore 参数（不再直接读全局开关）")
check('if _sc not in ("role", "both") and not _ov:' in _rb, "恢复模式不因「仅第一排」跳过第二排")
check("force=True, nfo_path=_p)" in _rb, "第二排同步带 force=恢复标记（并按文件定位）")
check("_emby_sync_manual_rename(_nb, _na, server_id=server_id)" in _rb,
      "双写第一排：恢复时同步 Emby Person 改名")
check('ctx="恢复", nfo_path=_p)' in _rb, "恢复时按文件触发 Emby 刷新")
check('"emby_refresh": _rf' in _rb, "结果 data 带 emby_refresh")

# ─────────────────────────────────────────────
print("\n[T4] 写回 worker：恢复按行判定（reason=restore）+ 传 restore")
# ─────────────────────────────────────────────
check('_is_restore = str(rec.get("reason") or "") == "restore"' in _SRC,
      "按行判定是否恢复登记（v4.7.7 解耦，不再看全局恢复开关）")
check('if not chk.get("ready") and not _is_restore:' in _SRC,
      "待翻词条在恢复登记不阻塞写回（普通候选仍阻塞）")
check("item_id, server_id, auto=True, restore=_is_restore, only_paths=_only_paths)" in _SRC,
      "常驻写回 worker 按行传 restore（恢复登记才 True）")

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
check("self._wb_register_item(_riid, _rsid, target_scope=\"both\"," in _ing
      and 'reason="restore", nfo_path=nfo_path' in _ing,
      "恢复即登记写回（自动，reason='restore' + 本次回来的 nfo 路径）")
check("[Restore] 入库即登记恢复" in _ing, "有 INFO 自证")

_wbe = _grab_method(_SRC, "_wb_writeback_enabled")
check("_overwrite_emby" not in _wbe, "写回总门不再含恢复旁路（v4.7.7 解耦）")
check("return self._wb_auto_setting()" in _wbe, "写回总门回落到「自动写回」用户设置本身")
_nsW = {}
exec(_grab_method(_SRC, "_wb_auto_setting"), _nsW)
exec(_wbe, _nsW)


class _S1:
    # 自动写回开 + 恢复开 → 放行
    _overwrite_emby = True
    _auto_writeback = True
    _nfo_preview = False
    _tx_cfg_snapshot = None
    _wb_auto_setting = _nsW["_wb_auto_setting"]
    _wb_writeback_enabled = _nsW["_wb_writeback_enabled"]


class _S2:
    # 恢复开、自动写回关 → 不放行（恢复不再借本门）
    _overwrite_emby = True
    _auto_writeback = False
    _nfo_preview = False
    _tx_cfg_snapshot = None
    _wb_auto_setting = _nsW["_wb_auto_setting"]
    _wb_writeback_enabled = _nsW["_wb_writeback_enabled"]


check(_S1()._wb_writeback_enabled() is True and _S2()._wb_writeback_enabled() is False,
      "行为：写回总门只看「自动写回」；恢复开关开着也不放行（v4.7.7 解耦）")
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
      "写回 worker 门控仍用 _wb_writeback_enabled（只管自动写回；恢复按行判定）")
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

# ─────────────────────────────────────────────
print("\n[T9] v4.7.7 解耦：恢复改走队列标记 reason='restore'（不借自动写回门）")
# ─────────────────────────────────────────────
check("def _wb_register_item(self, item_id: str, server_id: str = \"\", target_scope: str = \"\",\n"
      "                          reason: str = \"\", nfo_path: str = \"\") -> str:" in _SRC,
      "_wb_register_item 新增 reason / nfo_path 参数（v4.7.8）")
_wpr = _grab_method(_SRC, "_writeback_pending_round")
check('_is_r = str(rec.get("reason") or "") == "restore"' in _wpr
      and "if not self._wb_writeback_enabled() and not _is_r:" in _wpr,
      "本轮：自动写回关时普通候选跳过、恢复候选照常处理")
check("has_pending_restore(plugin_id=_pid)" in _SRC, "worker 用 has_pending_restore 决定是否进入本轮")
# v4.7.9（审查 P1-02）：收尾改走 `finish` + 认领代数 —— 写回期间来的新登记不再被丢/被清
check("wdb.finish(plugin_id=pi_d, server_id=server_id, item_id=item_id" in _SRC
      and "claimed_gen=_claimed_gen" in _SRC,
      "写回收尾走 finish + 认领代数（P1-02）")
check("clear_restore" not in _SRC, "不再依赖 clear_restore（清回由 finish 原子完成）")

# 真 SQLite 行为：reason 粘性 + restore 不受指纹幂等约束 + has_pending_restore + clear_reason
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("epl_db_v477", str(PLUGIN_DIR / "db.py"))
_db = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_db)
check(_db.SCHEMA_VERSION >= 17, f"SCHEMA_VERSION 升到 17+（实际 {_db.SCHEMA_VERSION}）")
check(any(c[0] == "reason" for c in _db._WRITEBACK_V15_COLUMNS), "迁移补列含 reason")
check(any(c[0] == "restore_paths" for c in _db._WRITEBACK_V16_COLUMNS), "迁移补列含 restore_paths")
check(any(c[0] == "gen" for c in _db._WRITEBACK_V17_COLUMNS), "迁移补列含 gen（写回代数）")
_db.PeopleDb.ensure_table()   # 建表 + 跑版本化迁移（writeback_state 唯一索引由 migrate 创建）
_wdb = _db.WritebackDb()
_wdb.ensure_table()
_PID = "EmbyPeopleLocalizeProbe"
_wdb.clear_all(plugin_id=_PID)
# 恢复登记不受「指纹一致」约束（done + 同指纹也要重新写）
_wdb.register(plugin_id=_PID, server_id="s1", item_id="i1", file_sig="sigX", target_scope="both")
_wdb.set_status(plugin_id=_PID, server_id="s1", item_id="i1", status="done", file_sig="sigX")
_r_plain = _wdb.register(plugin_id=_PID, server_id="s1", item_id="i1", file_sig="sigX", target_scope="both")
check(_r_plain == "skip", "普通登记：done 且指纹一致 → skip（幂等不变）")
_r_restore = _wdb.register(plugin_id=_PID, server_id="s1", item_id="i1", file_sig="sigX",
                           target_scope="both", reason="restore", restore_path="/v/S01E01.nfo")
check(_r_restore == "pending", "恢复登记：done 且指纹一致也重新置 pending（必须重写）")
_rec = _wdb.get(plugin_id=_PID, server_id="s1", item_id="i1") or {}
check(str(_rec.get("reason") or "") == "restore", "行上记下 reason='restore'")
check(str(_rec.get("restore_paths") or "") == "/v/S01E01.nfo", "行上记下本次恢复路径")
check(_wdb.has_pending_restore(plugin_id=_PID) is True, "has_pending_restore → True")
# v4.7.8：多集恢复（整季洗版）按条目累加合并；重复同一条不重复追加
_wdb.register(plugin_id=_PID, server_id="s1", item_id="i1", file_sig="sigX",
              target_scope="both", reason="restore", restore_path="/v/S01E02.nfo")
_wdb.register(plugin_id=_PID, server_id="s1", item_id="i1", file_sig="sigX",
              target_scope="both", reason="restore", restore_path="/v/S01E02.nfo")   # 重复
_rec = _wdb.get(plugin_id=_PID, server_id="s1", item_id="i1") or {}
_pths = [p for p in str(_rec.get("restore_paths") or "").splitlines() if p]
check(_pths == ["/v/S01E01.nfo", "/v/S01E02.nfo"], f"多集恢复累加合并且去重（实际 {_pths}）")
# 粘性：随后普通登记不清掉 restore / restore_paths
_wdb.register(plugin_id=_PID, server_id="s1", item_id="i1", file_sig="sigX", target_scope="role")
_rec = _wdb.get(plugin_id=_PID, server_id="s1", item_id="i1") or {}
check(str(_rec.get("reason") or "") == "restore", "普通登记不覆盖已存在的 restore（粘性）")
check(str(_rec.get("restore_paths") or "") != "", "普通登记不清空 restore_paths")
# v4.7.9（审查 P1-02）收尾带「代数」：
#  – 认领后又有新登记（gen 变了）→ **不收尾、不清恢复登记**，交回 pending 重跑
#  – 没有新登记 → 正常收尾并清回 reason + restore_paths
_rec = _wdb.get(plugin_id=_PID, server_id="s1", item_id="i1") or {}
_gen_now = int(_rec.get("gen") or 0)
check(_gen_now >= 1, f"每次登记都 +1 代数（gen={_gen_now}）")
_wdb.set_status(plugin_id=_PID, server_id="s1", item_id="i1", status="writing")
check(_wdb.finish(plugin_id=_PID, server_id="s1", item_id="i1", status="done",
                  file_sig="sigZ", claimed_gen=_gen_now - 1) == "requeued",
      "认领代数已被顶替 → 收尾被拒（requeued）")
_rec = _wdb.get(plugin_id=_PID, server_id="s1", item_id="i1") or {}
check(str(_rec.get("status") or "") == "pending"
      and str(_rec.get("reason") or "") == "restore"
      and str(_rec.get("restore_paths") or "") != "",
      "被顶替时：不收尾、**不清恢复登记**，交回 pending（新内容下一轮重新写）")
check(_wdb.has_pending_restore(plugin_id=_PID) is True, "仍在待恢复（下一轮会重新写）")
check(_wdb.finish(plugin_id=_PID, server_id="s1", item_id="i1", status="done",
                  file_sig="sigZ", claimed_gen=_gen_now) == "done",
      "代数一致 → 正常收尾")
_rec = _wdb.get(plugin_id=_PID, server_id="s1", item_id="i1") or {}
check(str(_rec.get("reason") or "") == "" and str(_rec.get("restore_paths") or "") == "",
      "正常收尾后清回 reason + restore_paths（普通写回不再被误当恢复）")
check(_wdb.has_pending_restore(plugin_id=_PID) is False, "收尾后 has_pending_restore → False")
# 写回进行中（writing）来的新登记：不再被丢弃、也不打断当前轮（status/attempts 不动）
_wdb.clear_all(plugin_id=_PID)
_wdb.register(plugin_id=_PID, server_id="s1", item_id="i2", file_sig="a", target_scope="both")
_wdb.set_status(plugin_id=_PID, server_id="s1", item_id="i2", status="writing", bump_attempt=True)
_r_w = _wdb.register(plugin_id=_PID, server_id="s1", item_id="i2", file_sig="b",
                     target_scope="both", reason="restore", restore_path="/v/S02E01.nfo")
check(_r_w == "pending", "写回进行中来登记 → 不再 skip（累积为新一代，P1-02）")
_rec2 = _wdb.get(plugin_id=_PID, server_id="s1", item_id="i2") or {}
check(str(_rec2.get("status") or "") == "writing", "不打断当前这一轮（status 仍为 writing）")
check(str(_rec2.get("reason") or "") == "restore"
      and str(_rec2.get("restore_paths") or "") == "/v/S02E01.nfo",
      "新恢复登记与路径已并进队列（此前会被静默丢弃）")
check(int(_rec2.get("gen") or 0) == 1, f"gen 递增（新一代，实际 {_rec2.get('gen')}）")
_wdb.clear_all(plugin_id=_PID)

# ─────────────────────────────────────────────
print("\n[T10] v4.7.8 文件级恢复（只写本次回来的文件）+ 接收通知区分恢复")
# ─────────────────────────────────────────────
check('scope: str = "both", restore: bool = False,\n'
      '                             only_paths: Optional[set] = None) -> dict:' in _SRC,
      "_restore_item_to_nfo 新增 only_paths（文件级恢复）")
_rif = _grab_method(_SRC, "_restore_item_to_nfo")
check('in _want' in _rif and 'if str(r.get("nfo_path") or "").strip()' in _rif,
      "按 only_paths 过滤人物记录")
check("only_paths=_only_paths)" in _SRC, "worker 恢复时传入本次回来的路径集合")
check('_rp = [p.strip() for p in str(rec.get("restore_paths") or "").splitlines() if p.strip()]' in _SRC,
      "worker 从 restore_paths 解析路径集合")

# 行为：只写本次回来的那一个文件（同剧其它集不越界）
_nsR2 = {"os": os, "time": __import__("time"), "logger": logger,
         "Optional": __import__("typing").Optional, "traceback": __import__("traceback")}
exec(_rif, _nsR2)
_D = Path(tempfile.mkdtemp(prefix="epl478_"))
_p1 = _D / "S01E01.nfo"
_p2 = _D / "S01E02.nfo"
_p3 = _D / "S01E03.nfo"
for _p in (_p1, _p2, _p3):
    _p.write_text("<movie/>", encoding="utf-8")


class _Pdb:
    def item_meta(self, **k):
        return {"title": "T"}

    def people_of_item(self, **k):
        return [{"nfo_path": str(_p1), "name_before": "a", "name_after": "甲"},
                {"nfo_path": str(_p2), "name_before": "b", "name_after": "乙"},
                {"nfo_path": str(_p3), "name_before": "c", "name_after": "丙"}]


class _Rob:
    _restore_item_to_nfo = _nsR2["_restore_item_to_nfo"]
    _nfo_preview = False
    _people_db = _Pdb()

    def __init__(self):
        self.written = []

    def _norm_writeback_scope(self, s):
        _s = str(s or "both").strip().lower()
        return _s if _s in ("person", "role", "both") else "both"

    def _write_nfo_once(self, item_id, server_id, path, people_records=None, auto=False, scope="both"):
        self.written.append(path)
        return {"success": True, "data": {"changed": 1}}

    def _emby_sync_item_roles(self, **k):
        return {}


_o1 = _Rob()
_r1 = _o1._restore_item_to_nfo("296101", "s1", only_paths={str(_p1)})
check(_o1.written == [str(_p1)],
      f"只写本次回来的文件（实际 {[os.path.basename(x) for x in _o1.written]}）")
check(_r1.get("success") is True and str(_p2) not in _o1.written and str(_p3) not in _o1.written,
      "同剧其它集不被写入（只删 E01 就只恢复 E01）")
_o2 = _Rob()
_o2._restore_item_to_nfo("296101", "s1")   # 不传 only_paths → 整条目（旧行为）
check(len(_o2.written) == 3, "不传 only_paths → 整条目写（旧行为，兼容）")
_o3 = _Rob()
_r3 = _o3._restore_item_to_nfo("296101", "s1", only_paths={"/nonexistent.nfo"})
check(_o3.written == [] and _r3.get("success") is False, "目标文件库里已无记录 → 跳过不写")

# ② 接收通知：区分 📥 新入库 / 🔁 恢复入库（查我们库）
check("def _webhook_recovery_ingress(self, brief: dict, server_id: str = \"\") -> bool:" in _SRC,
      "新增 _webhook_recovery_ingress（收到事件时查我们库的观察期记录）")
check("deleted_weak_candidates(" in _grab_method(_SRC, "_webhook_recovery_ingress"),
      "恢复判定走我们库的观察期候选")
check('_brief["recovered_ingress"] = self._webhook_recovery_ingress(_brief, server_id)' in _SRC,
      "入库事件带上恢复标记")
check('"recovered_ingress": bool(brief.get("recovered_ingress"))' in _SRC, "接收队列透传标记")
_flush = _grab_method(_SRC, "_flush_received_notification")
check('_head = "🔁 恢复入库"' in _flush, "命中的批次报「🔁 恢复入库」")
check("📥 收到 {total} 条入库事件" in _flush, "未命中仍报「📥 收到 N 条入库事件」")
check("_all_recov" in _flush, "按批次是否全为恢复分流（📥 vs 🔁）")
check("本次仅入库" in _flush, "恢复开关关时如实说明「仅入库」")

# ─────────────────────────────────────────────
print("\n[T11] v4.7.9：恢复写回不再冒充「自动写回」+ 卡片不再永久挂着")
# ─────────────────────────────────────────────
_wwork = _grab_method(_SRC, "_writeback_worker")
check("def _wb_status_idle(self) -> None:" in _SRC, "新增 _wb_status_idle（空闲复位 running）")
check(_wwork.count("self._wb_status_idle()") >= 4,
      f"每个「不干活」的分支都复位 running（实际 {_wwork.count('self._wb_status_idle()')} 处）")
check('"phase": ("restore" if _rs else "writeback")' in _SRC, "恢复写回用 phase='restore'")
check('_label = "恢复写回" if _rs else "自动写回"' in _SRC, "日志按恢复/自动分流文案")
_wpr2 = _grab_method(_SRC, "_writeback_pending_round")
check('"restore": 0' in _wpr2 and 'stats["restore"] = int(stats.get("restore") or 0) + 1' in _wpr2,
      "本轮统计「恢复」实际干活的条数")

_nsI = {}
exec(_grab_method(_SRC, "_wb_status_idle"), _nsI)


class _SX:
    def __init__(s, st):
        s._writeback_status = st


_x = _SX({"running": True, "phase": "restore"})
_nsI["_wb_status_idle"](_x)
check(_x._writeback_status["running"] is False, "空闲复位 running（phase=restore，就是那个卡住的场景）")
_y = _SX({"running": True, "phase": "writeback_all"})
_nsI["_wb_status_idle"](_y)
check(_y._writeback_status["running"] is True, "不动手动「全部写回」的卡片（phase=writeback_all）")
_z = _SX({"running": True, "phase": "writeback"})
_nsI["_wb_status_idle"](_z)
check(_z._writeback_status["running"] is False, "空闲复位 running（phase=writeback）")

_DV = (PLUGIN_DIR / "src" / "views" / "DashboardView.vue").read_text(encoding="utf-8")
check("'恢复写回'" in _DV and "wb.phase" in _DV, "仪表盘按 phase 显示「恢复写回」")

# ─────────────────────────────────────────────
print("\n[T12] v4.7.9：恢复的 Emby 侧按「文件」定位（不再打到同剧别的集）+ 改名复读空值归一")
# ─────────────────────────────────────────────
check("def emby_item_id_by_nfo_path(self, *, plugin_id: str, nfo_path: str," in
      (PLUGIN_DIR / "db.py").read_text(encoding="utf-8"),
      "db 新增 emby_item_id_by_nfo_path（按文件取 Emby itemId）")
check("def _emby_role_item_id(self, cli, *, server_id: str, item_id: str, nfo_path: str = \"\") -> str:" in _SRC,
      "_emby_role_item_id 新增 nfo_path")
check('_key = (str(server_id or ""), str(item_id or ""), _np)' in _SRC, "缓存键带上文件（集）")
check("def _emby_refresh_item(self, item_id: str, server_id: str = \"\", ctx: str = \"\"," in _SRC
      and "nfo_path: str = \"\") -> dict:" in _SRC, "_emby_refresh_item 新增 nfo_path")
check('_tpaths = [str(_p) for _p in (path_groups or {}).keys()]' in _SRC, "恢复按本次写回的文件逐个定位")
check("force=True, nfo_path=_p)" in _SRC, "角色同步按文件定位")
check("ctx=\"恢复\", nfo_path=_p)" in _SRC, "刷新按文件定位")

_nsRI = {"logger": logger}
exec(_grab_method(_SRC, "_emby_role_item_id"), _nsRI)


class _Pdb2:
    def emby_item_id_by_nfo_path(self, **k):
        return "32087" if str(k.get("nfo_path") or "").endswith("E02.nfo") else ""

    def item_identity(self, **k):
        return {"emby_item_id": "32085", "media_provider": "", "media_id": "", "item_type": ""}


class _Rid:
    _emby_role_item_id = _nsRI["_emby_role_item_id"]
    _people_db = _Pdb2()

    def __init__(self):
        self.__dict__["_emby_role_id_cache"] = {}


_o = _Rid()
check(_o._emby_role_item_id(None, server_id="s1", item_id="296101", nfo_path="/v/S01E02.nfo") == "32087",
      "按文件定位到本集（E02=32087），不再永远是同剧第一集（E01=32085）")
check(_o._emby_role_item_id(None, server_id="s1", item_id="296101") == "32085",
      "不给 nfo_path → 退回 item_identity（旧行为不变）")

# ② 改名复读校验：空字段被 Emby 省略不再误判
_nsRN = {"logger": logger, "Optional": __import__("typing").Optional}
exec(_grab_method(_EMBY, "rename_person"), _nsRN)


class _RenCli:
    _PERSON_KEEP_FIELDS = ("Overview", "LockedFields", "ProviderIds", "ImageTags")

    def __init__(self, before, after):
        self._b, self._a, self._n = before, after, 0

    def get_person_detail(self, pid):
        self._n += 1
        return self._b if self._n == 1 else self._a

    def _post(self, path, data=None):
        return True


_c1 = _RenCli({"Name": "a", "Overview": "", "LockedFields": [], "ProviderIds": {}, "ImageTags": {}},
              {"Name": "b"})   # 空字段被 Emby 全部省略 → None
check(_nsRN["rename_person"](_c1, "p1", "b") is True,
      "改名前 '' / [] / {} → 复读后字段不存在（None）不再误判失败")
_c2 = _RenCli({"Name": "a", "Overview": "旧简介"}, {"Name": "b", "Overview": ""})
check(_nsRN["rename_person"](_c2, "p1", "b") is False, "真有内容被改（旧简介→空）仍判失败")
_c3 = _RenCli({"Name": "a", "ImageTags": {"Primary": "x"}}, {"Name": "b", "ImageTags": {}})
check(_nsRN["rename_person"](_c3, "p1", "b") is False, "非空→空的丢字段仍判失败")

# ─────────────────────────────────────────────
print("\n[T13] v4.7.9：入库通知「已有译文」口径补上第二排（role_after）")
# ─────────────────────────────────────────────
_dbd = (PLUGIN_DIR / "db.py").read_text(encoding="utf-8")
check("(role_after IS NOT NULL AND role_after<>'' AND role_after<>role_before) " in _dbd,
      "item_translation_counts 把角色译文也算「已翻」")
_pdb13 = _db.PeopleDb()
_PID13, _SRV13 = "EmbyPeopleLocalizeProbe13", "srv13"
_pdb13.delete_item(plugin_id=_PID13, item_id="I1", server_id=None)
_pdb13.upsert_people(plugin_id=_PID13, server_id=_SRV13, item_id="I1", item_type="Episode",
                     title="E1", season_num=1, episode_num=1,
                     people=[{"before_name": "越谷夏海", "Name": "越谷夏海",   # 人名未译（汉字日文名）
                              "before_role": "役名", "Role": "角色名"}],      # 第二排已译
                     nfo_path="/v/I1.nfo", emby_item_id="1")
_c13 = _pdb13.item_translation_counts(plugin_id=_PID13, pairs=[(_SRV13, "I1")]).get((_SRV13, "I1")) or {}
check(int(_c13.get("translated") or 0) == 1,
      f"只翻第二排也算「已有译文」（total={_c13.get('total')} translated={_c13.get('translated')}）")
_pdb13.delete_item(plugin_id=_PID13, item_id="I1", server_id=None)

print("\n" + "=" * 72)
if _N[1] == 0:
    print(f"结果: {_N[0]} 通过 / 0 失败")
else:
    print(f"结果: {_N[0] - _N[1]} 通过 / {_N[1]} 失败")
print("=" * 72)
sys.exit(1 if _N[1] else 0)
