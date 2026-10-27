"""第四轮审查（2026-10-27）修复回归：

P0-1 ASS 记录删除不得删原始字幕；P0-2 备份/恢复完整性与索引作废；
P0-3 全量重建不确定失败不提交；P1-4 严格上传逐 face；
P1-5 检测与子集单 face 口径一致；P1-6 unknown/partial_check 状态；
P1-7 字体删除级联重检；P1-8 启动轻检发现磁盘新文件；P1-10 缺失字体专用目录；
P2-12 同内容多路径口径一致；P2-13 监控失败重试；P2-16 配置保存如实反馈。
"""

import importlib
import os
import shutil
import time
from pathlib import Path

import pytest

from ziti_under_test import font_metadata as fm
from ziti_under_test import glyph_checker as gc
from ziti_under_test import harfbuzz_engine as he
from ziti_under_test.db import FontDB

FONT_DIR = Path(r"C:\Windows\Fonts")
ARIAL = FONT_DIR / "arial.ttf"
MSYH = FONT_DIR / "msyh.ttc"
FIXTURE = Path(__file__).parent / "fixtures" / "complex.ass"

plugin_mod = importlib.import_module("ziti_under_test.__init__")

needs_fonts = pytest.mark.skipif(
    not (ARIAL.is_file() and MSYH.is_file()), reason="需要 Windows 系统字体"
)


# ─── 脚手架 ──────────────────────────────────────────────────────────────


def _plugin(tmp_path: Path, db: FontDB, lib: Path):
    plugin = plugin_mod.Zitifenlei()
    plugin._db = db
    plugin._enabled = True
    plugin._config.update({"lib_dir": str(lib)})
    plugin._tmp_dir = tmp_path / "tmp"
    plugin._tmp_dir.mkdir(parents=True, exist_ok=True)
    return plugin


def _make_lib(tmp_path: Path) -> Path:
    lib = tmp_path / "lib"
    lib.mkdir(parents=True, exist_ok=True)
    for src in (ARIAL, MSYH):
        dst = lib / src.name
        if dst.exists():
            continue
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)
    return lib


def _make_db(tmp_path: Path, lib: Path) -> FontDB:
    db = FontDB(tmp_path / "ziti.db")
    for item in sorted(lib.iterdir()):
        if item.is_file():
            db.upsert_font_file(fm.inspect_font(item))
    return db


ASS_TEXT = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Style: Default,Arial,52,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,1,2,30,30,30,1

[Events]
Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,AB
"""


# ─── P0-1 删除 ASS 记录不删原始字幕 ─────────────────────────────────────


def test_ass_delete_and_clear_keep_original_subtitles(tmp_path):
    lib = _make_lib(tmp_path)
    db = FontDB(tmp_path / "ziti.db")
    try:
        plugin = _plugin(tmp_path, db, lib)
        watch_dir = tmp_path / "watch"
        watch_dir.mkdir()
        original = watch_dir / "original.ass"
        original.write_text(ASS_TEXT, encoding="utf-8")
        copied = plugin._tmp_dir / "manual-copy.ass"
        copied.write_text(ASS_TEXT, encoding="utf-8")

        # 监控目录原件（source=auto）与插件临时副本（source=manual）各一条记录
        db.add_ass(
            file_name=original.name,
            source="auto",
            status="ok",
            missing_fonts=[],
            all_fonts=["Arial"],
            file_path=str(original),
        )
        db.add_ass(
            file_name=copied.name,
            source="manual",
            status="ok",
            missing_fonts=[],
            all_fonts=["Arial"],
            file_path=str(copied),
        )
        auto_id = db.query_one("SELECT id FROM ass_files WHERE file_path = ?", (str(original),))["id"]
        manual_id = db.query_one("SELECT id FROM ass_files WHERE file_path = ?", (str(copied),))["id"]

        # 单条删除：原文只删记录、临时副本才删文件
        assert plugin.api_ass_delete(auto_id)["success"] is True
        assert original.is_file(), "监控目录里的原始字幕不得被删除"
        assert plugin.api_ass_delete(manual_id)["success"] is True
        assert not copied.exists(), "插件临时目录内的副本随记录清理"

        # 清空：原件保留，临时副本清理
        keep = watch_dir / "keep.ass"
        keep.write_text(ASS_TEXT, encoding="utf-8")
        db.add_ass(file_name=keep.name, source="auto", status="ok", missing_fonts=[], all_fonts=[], file_path=str(keep))
        another = plugin._tmp_dir / "manual-copy2.ass"
        another.write_text(ASS_TEXT, encoding="utf-8")
        db.add_ass(file_name=another.name, source="manual", status="ok", missing_fonts=[], all_fonts=[], file_path=str(another))
        result = plugin.api_ass_clear()
        assert result["success"] is True
        assert keep.is_file(), "清空记录不得删除监控目录原始字幕"
        assert not another.exists()
        assert db.query("SELECT id FROM ass_files") == []
    finally:
        db.close()


# ─── P0-2 备份/恢复 ──────────────────────────────────────────────────────


def test_export_import_covers_user_tables_and_resets_index(tmp_path):
    lib = _make_lib(tmp_path)
    db = _make_db(tmp_path, lib)
    try:
        plugin = _plugin(tmp_path, db, lib)
        ass_id = db.add_ass(
            file_name="ep.ass", source="manual", status="missing",
            missing_fonts=["NoSuchFont"], all_fonts=["NoSuchFont"], file_path=str(tmp_path / "ep.ass"),
        )
        db.replace_missing_glyphs(
            ass_id, str(tmp_path / "ep.ass"),
            [{"name": "NoSuchFont", "status": "missing", "missing_count": 1,
              "missing_codepoints": [0x4E2D], "missing_chars": "中", "used_count": 1}],
        )
        db.set_manual_font_mapping("内名", "NoSuchFont", file_sha256="abc", note="测试")

        backup = plugin.api_db_export()["data"]
        assert "ass_missing_glyphs" in backup["tables"]
        assert "manual_font_mappings" in backup["tables"]
        assert backup["tables"]["ass_missing_glyphs"], "逐字形快照必须随备份导出"
        assert backup["tables"]["manual_font_mappings"], "人工映射必须随备份导出"
        assert backup["version"] >= 2

        lib_before = db.index_stats()
        assert lib_before["files"] >= 2

        # 清库 → 恢复：业务数据回来了，索引被作废（待重建）
        db.clear_all()
        assert db.index_stats()["files"] == 0
        assert db.index_get("last_rebuild", "") == ""
        counts = db.import_all(backup)
        assert counts["ass_missing_glyphs"] >= 1
        assert db.list_manual_font_mappings()
        assert db.query_one("SELECT COUNT(*) AS c FROM ass_files")["c"] == 1
        assert db.index_stats()["files"] == 0, "恢复后旧索引必须作废，等待重建"
        assert db.index_version() > 0
    finally:
        db.close()


def test_import_rejects_incomplete_backup_and_rolls_back(tmp_path):
    lib = _make_lib(tmp_path)
    db = _make_db(tmp_path, lib)
    try:
        db.add_ass(file_name="ep.ass", source="manual", status="ok", missing_fonts=[], all_fonts=[], file_path="")
        with pytest.raises(ValueError):
            db.import_all({"tables": {"fonts": []}})  # 缺核心表 → 拒绝

        # 表数据格式错误：必须整体回滚，原记录仍在
        bad = {
            "version": 2,
            "tables": {
                "fonts": [],
                "pending_fonts": [],
                "ass_files": [{"file_name": "x"}, "not-a-dict"],
            },
        }
        try:
            db.import_all(bad)
        except Exception:
            pass
        assert db.query_one("SELECT COUNT(*) AS c FROM ass_files")["c"] == 1, "导入异常必须回滚原数据"
    finally:
        db.close()


# ─── P0-3 全量重建完整性门槛 ────────────────────────────────────────────


@needs_fonts
def test_full_rebuild_refuses_incomplete_stage(tmp_path, monkeypatch):
    lib = _make_lib(tmp_path)
    db = _make_db(tmp_path, lib)
    try:
        plugin = _plugin(tmp_path, db, lib)
        before = db.index_stats()
        bad = lib / "broken.ttf"
        bad.write_bytes(b"not a font")
        # 让其中一个文件解析抛异常（模拟权限/IO/解析异常 = 结果不确定）
        real_inspect = plugin_mod.inspect_font

        def _flaky(path):
            if Path(path).name == "broken.ttf":
                raise OSError("read error")
            return real_inspect(path)

        monkeypatch.setattr(plugin_mod, "inspect_font", _flaky)
        result = plugin.api_subset_rebuild_index()
        assert result["success"] is False, result
        assert "结果不确定" in result["message"] or "未提交" in result["message"]
        # 旧索引原样保留（文件数不变、可继续查询）
        after = db.index_stats()
        assert after["files"] == before["files"]
        assert db.lookup_faces("Arial"), "旧索引必须仍可查询"

        # 显式允许不完整后才提交（此时 broken.ttf 走确认损坏路径）
        monkeypatch.setattr(plugin_mod, "inspect_font", real_inspect)
        ok = plugin.api_subset_rebuild_index()
        assert ok["success"] is True, ok
        assert db.lookup_faces("Arial")
    finally:
        db.close()


# ─── P1-4 严格上传逐 face ──────────────────────────────────────────────


def _fake_inspection(tmp_path, faces):
    class _Face:
        def __init__(self, idx, family, aliases, codepoints):
            self.face_index = idx
            self.family = family
            self.subfamily = "Regular"
            self.full_name = family
            self.postscript_name = family
            self.aliases = list(aliases)
            self.codepoints = set(codepoints)
            self.status = "ok"
            self.error = ""

        def alias_keys(self):
            return [plugin_mod.normalize_font_key(a) for a in self.aliases]

        def display_name(self):
            return self.family

    class _Inspection:
        def __init__(self):
            self.path = str(tmp_path / "fake.ttc")
            self.sha256 = "0" * 64
            self.file_size = 1
            self.mtime_ns = 1
            self.format = "ttc"
            self.status = "ok"
            self.error = ""
            self.faces = [
                _Face(i, fam, aliases, cps) for i, (fam, aliases, cps) in enumerate(faces)
            ]

    return _Inspection()


def test_strict_upload_requires_single_face_name_and_coverage(tmp_path, monkeypatch):
    lib = _make_lib(tmp_path)
    db = FontDB(tmp_path / "ziti.db")
    try:
        plugin = _plugin(tmp_path, db, lib)
        targets = {
            "nosuchfont": {
                "name": "NoSuchFont",
                "count": 1,
                "codepoints": {ord("中")},
                "chars": "中",
                "glyph": True,
            }
        }
        # face0 名称匹配但零覆盖；face1 覆盖「中」但名称不匹配 → 整体必须拒绝
        fake = _fake_inspection(
            tmp_path,
            [("NoSuchFont", ["NoSuchFont"], [ord("A")]), ("Other", ["Other"], [ord("中")])],
        )
        monkeypatch.setattr(plugin_mod, "inspect_font", lambda _p: fake)
        verdict = plugin._evaluate_font_for_targets(tmp_path / "fake.ttc", targets)
        assert verdict["ok"] is False
        assert "未覆盖" in verdict["reason"]

        # 同一 face 名称匹配且覆盖缺失字符 → 通过，并返回该 face_index
        fake2 = _fake_inspection(
            tmp_path,
            [("Other", ["Other"], [ord("A")]), ("NoSuchFont", ["NoSuchFont"], [ord("中")])],
        )
        monkeypatch.setattr(plugin_mod, "inspect_font", lambda _p: fake2)
        verdict2 = plugin._evaluate_font_for_targets(tmp_path / "fake.ttc", targets)
        assert verdict2["ok"] is True, verdict2
        assert verdict2["face_index"] == 1
        assert ord("中") in verdict2["covered"]

        # 人工指定目标不能绕过覆盖验证（名称不匹配且零覆盖 → 拒绝）
        fake3 = _fake_inspection(tmp_path, [("Other", ["Other"], [ord("A")])])
        monkeypatch.setattr(plugin_mod, "inspect_font", lambda _p: fake3)
        verdict3 = plugin._evaluate_font_for_targets(
            tmp_path / "fake.ttc", targets, target_hint="NoSuchFont"
        )
        assert verdict3["ok"] is False
        assert "未覆盖" in verdict3["reason"]

        # 历史记录没有缺失码点明细：只凭名称不能算通过
        legacy = {"nosuchfont": {"name": "NoSuchFont", "count": 1, "codepoints": set(), "chars": "", "glyph": False}}
        fake4 = _fake_inspection(tmp_path, [("NoSuchFont", ["NoSuchFont"], [ord("中")])])
        monkeypatch.setattr(plugin_mod, "inspect_font", lambda _p: fake4)
        verdict4 = plugin._evaluate_font_for_targets(tmp_path / "fake.ttc", legacy)
        assert verdict4["ok"] is False
        assert "重新检查" in verdict4["reason"]
    finally:
        db.close()


# ─── P1-5 / P1-6 检测口径与未验证状态 ───────────────────────────────────


def test_glyph_checker_uses_single_face_semantics():
    usage = [gc.AssFontUse(name="Dual", codepoints={ord("A"), ord("B")})]

    def lookup(_name):
        return [
            gc.FaceCoverage(face_id=1, file_path="a.ttc", face_index=0, names=["Dual"], codepoints={ord("A")}),
            gc.FaceCoverage(face_id=2, file_path="a.ttc", face_index=1, names=["Dual"], codepoints={ord("B")}),
        ]

    result = gc.evaluate_usage(usage, lookup)
    verdict = result.fonts[0]
    # 两个 face 覆盖互补：不能判「完整」，与子集化只嵌入单个 face 的口径一致
    assert verdict.status == "partial"
    assert verdict.missing_count == 1
    assert verdict.face_index == 0
    assert any("多个 face 覆盖互补" in w for w in result.warnings)

    # 无 face → missing；有 face 但 cmap 为空 → unknown（不能当完整）
    assert gc.evaluate_usage(usage, lambda _n: []).fonts[0].status == "missing"
    empty = gc.evaluate_usage(
        usage, lambda _n: [gc.FaceCoverage(face_id=3, file_path="b.ttf", face_index=0, names=["Dual"], codepoints=set())]
    ).fonts[0]
    assert empty.status == "unknown"


def test_name_only_fallback_reports_partial_check(tmp_path, monkeypatch):
    lib = _make_lib(tmp_path)
    db = FontDB(tmp_path / "ziti.db")
    try:
        plugin = _plugin(tmp_path, db, lib)
        raw = ASS_TEXT.encode("utf-8")
        src = tmp_path / "ep.ass"
        src.write_bytes(raw)
        # 索引不可用（模拟）：回退名称级 → 名称在库内也不能报「字体完整」
        monkeypatch.setattr(plugin, "_glyph_check", lambda _raw: None)
        monkeypatch.setattr(plugin, "_lib_font_keys", lambda: ({"arial"}, "db"))
        result = plugin._check_ass_content("ep.ass", raw, source="manual", file_path=str(src))
        assert result["status"] == "partial_check"
        assert result["check_engine"] == "name-only"
        assert "未验证字形" in result["status_text"]
        row = db.get_ass(result["id"])
        assert row["status"] == "partial_check"
        # 详情页实时重算也不能把它改口成 ok
        detail = plugin.api_ass_detail(result["id"])["data"]
        assert detail["status"] == "partial_check"

        # 空 Events 字幕（无有效用字）同样不能是「字体完整」
        empty_ass = tmp_path / "empty.ass"
        empty_ass.write_bytes(
            b"[Script Info]\nScriptType: v4.00+\n\n[V4+ Styles]\n"
            b"Style: Default,Arial,52,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,1,2,30,30,30,1\n\n[Events]\n"
        )
        raw2 = empty_ass.read_bytes()
        result2 = plugin._check_ass_content("empty.ass", raw2, source="manual", file_path=str(empty_ass))
        assert result2["status"] == "partial_check", result2
    finally:
        db.close()


# ─── P1-7 字体删除级联 ──────────────────────────────────────────────────


def test_font_delete_cascades_recheck(tmp_path):
    from fontTools.ttLib import TTFont

    lib = _make_lib(tmp_path)
    db = _make_db(tmp_path, lib)
    try:
        plugin = _plugin(tmp_path, db, lib)
        raw = he.strip_fonts_section(FIXTURE.read_text(encoding="utf-8")).encode("utf-8")
        src = tmp_path / "cascade.ass"
        src.write_bytes(raw)
        checked = plugin._check_ass_content(FIXTURE.name, raw, source="manual", file_path=str(src))
        assert "NoSuchFont" in (checked.get("missing_fonts") or [])

        # 造一份覆盖中文、内部名叫 NoSuchFont 的字体归档入库 → 缺失消失
        incoming = tmp_path / "incoming"
        incoming.mkdir()
        clone_src = incoming / "NoSuchFont.ttf"
        font = TTFont(str(MSYH), fontNumber=0)
        try:
            for name_id in (1, 4, 6, 16, 17):
                font["name"].setName("NoSuchFont", name_id, 3, 1, 0x409)
            font.save(str(clone_src))
        finally:
            font.close()
        added = plugin._archive_font_file(clone_src, source="missing")
        assert added and added > 0
        plugin._recheck_missing_after_library_change("测试补齐")
        assert "NoSuchFont" not in (db.get_ass(checked["id"]).get("missing_fonts") or [])

        # 删除该字体：记录 + 索引 + 级联重检一起完成，字幕重新回到 missing
        row = db.query_one("SELECT id, file_path FROM fonts WHERE name = ?", ("NoSuchFont",))
        assert row, "归档记录应存在"
        clone = Path(row["file_path"])
        result = plugin.api_font_delete(row["id"])
        assert result["success"] is True, result
        assert not clone.exists()
        assert not db.lookup_faces("NoSuchFont"), "索引贡献必须撤销"
        assert "NoSuchFont" in (db.get_ass(checked["id"]).get("missing_fonts") or []), "受影响字幕必须重检回缺失"
    finally:
        db.close()


# ─── P1-8 启动轻检发现磁盘新文件 ────────────────────────────────────────


@needs_fonts
def test_startup_light_check_discovers_unindexed_files(tmp_path):
    lib = _make_lib(tmp_path)
    db = FontDB(tmp_path / "ziti.db")  # 空库
    try:
        plugin = _plugin(tmp_path, db, lib)
        plugin._startup_light_check()  # 空索引 → 全量重建
        assert db.query_one("SELECT COUNT(*) AS c FROM font_files")["c"] == 2

        # 外部直接放入新字体（watchdog 漏事件）→ 轻检发现并补索引
        extra = lib / "extra.ttf"
        shutil.copy2(ARIAL, extra)
        plugin._startup_light_check()
        paths = {r["path"] for r in db.query("SELECT path FROM font_files")}
        assert str(extra.resolve()) in paths
    finally:
        db.close()


# ─── P1-10 缺失字体专用目录 ─────────────────────────────────────────────


def test_missing_dir_rejects_unrelated_and_accepts_match(tmp_path, monkeypatch):
    lib = _make_lib(tmp_path)
    db = FontDB(tmp_path / "ziti.db")
    try:
        plugin = _plugin(tmp_path, db, lib)
        missing_dir = tmp_path / "missing"
        missing_dir.mkdir()
        plugin._config.update({"missing_font_dir": str(missing_dir)})

        unrelated = missing_dir / "unrelated.ttf"
        unrelated.write_bytes(ARIAL.read_bytes())
        monkeypatch.setattr(
            plugin,
            "_missing_glyph_targets",
            lambda: {
                "nosuchfont": {
                    "name": "NoSuchFont",
                    "count": 1,
                    "codepoints": {ord("中")},
                    "chars": "中",
                    "glyph": True,
                }
            },
        )
        monkeypatch.setattr(
            plugin,
            "_evaluate_font_for_targets",
            lambda _p, _t, _h="": {"ok": False, "reason": "与当前缺失字体不匹配"},
        )
        archived = []
        monkeypatch.setattr(plugin, "_archive_font_file", lambda p, source="auto": archived.append(str(p)) or 1)
        assert plugin._handle_missing_dir_font(unrelated) is True
        assert not unrelated.exists()
        rejected = list((missing_dir / "rejected").glob("*.ttf"))
        assert rejected and rejected[0].name == "unrelated.ttf"
        assert archived == [], "未通过严格校验的字体不得入库"

        matched = missing_dir / "matched.ttf"
        matched.write_bytes(MSYH.read_bytes())
        monkeypatch.setattr(
            plugin,
            "_evaluate_font_for_targets",
            lambda _p, _t, _h="": {"ok": True, "matched": "NoSuchFont", "covered_chars": "中", "reason": ""},
        )
        assert plugin._handle_missing_dir_font(matched) is True
        assert archived == [str(matched)]
    finally:
        db.close()


# ─── P2-12 同内容多路径 ─────────────────────────────────────────────────


@needs_fonts
def test_same_content_keeps_separate_path_records(tmp_path):
    lib = _make_lib(tmp_path)
    db = FontDB(tmp_path / "ziti.db")
    try:
        first = lib / "a.ttf"
        second = lib / "b.ttf"
        shutil.copy2(ARIAL, first)
        shutil.copy2(ARIAL, second)
        db.upsert_font_file(fm.inspect_font(first))
        db.upsert_font_file(fm.inspect_font(second))
        paths = {r["path"] for r in db.query("SELECT path FROM font_files")}
        assert str(first.resolve()) in paths and str(second.resolve()) in paths, "两份同内容字体仍是两条独立记录"
        # 删除其中一份不影响另一份的索引
        db.remove_font_file(str(first.resolve()))
        assert db.lookup_faces("Arial")
        assert {r["path"] for r in db.query("SELECT path FROM font_files")} == {str(second.resolve())}
    finally:
        db.close()


# ─── P2-13 监控失败重试 ─────────────────────────────────────────────────


def test_watch_failure_clears_dedup_and_schedules_retry(tmp_path):
    lib = _make_lib(tmp_path)
    db = FontDB(tmp_path / "ziti.db")
    try:
        plugin = _plugin(tmp_path, db, lib)
        plugin._config["lib_dir"] = ""  # 未配置库目录 → 归档必然失败
        font = tmp_path / "incoming" / "new.ttf"
        font.parent.mkdir()
        font.write_bytes(b"x")
        plugin._on_watch_event_impl(str(font))
        key = str(font.resolve())
        assert key not in plugin._processed_recent, "失败不得保留 60 秒去重标记"
        assert plugin._watch_retries.get(key) == 1
        with plugin._lock:
            timers = [t for p, t in plugin._watch_timers.items() if p == str(font)]
            for t in timers:
                t.cancel()
    finally:
        db.close()


@needs_fonts
def test_lib_dir_event_indexes_without_archiving(tmp_path):
    """字体库目录也纳入监控：外部直接放入的字体事件级增量索引，不重复归档。"""
    lib = _make_lib(tmp_path)
    db = FontDB(tmp_path / "ziti.db")
    try:
        plugin = _plugin(tmp_path, db, lib)
        dropped = lib / "dropped.ttf"
        shutil.copy2(ARIAL, dropped)
        plugin._on_watch_event_impl(str(dropped))
        paths = {r["path"] for r in db.query("SELECT path FROM font_files")}
        assert str(dropped.resolve()) in paths, "库目录事件必须立即补索引"
        assert plugin._db.query_one("SELECT COUNT(*) AS c FROM fonts")["c"] == 0, "库内文件不得被再次归档"
        assert dropped.is_file(), "库内文件不得被移动/删除"
    finally:
        db.close()


# ─── P2-16 配置保存如实反馈 ─────────────────────────────────────────────


def test_config_save_reports_persist_failure(tmp_path):
    lib = _make_lib(tmp_path)
    db = FontDB(tmp_path / "ziti.db")
    try:
        plugin = _plugin(tmp_path, db, lib)

        class _Req:
            async def json(self):
                return {"notify_enabled": True}

        def _boom(_cfg):
            raise RuntimeError("host write failed")

        plugin.update_config = _boom  # type: ignore[assignment]
        result = plugin_mod.asyncio.run(plugin.api_save_config(_Req()))
        assert result["success"] is False
        assert "持久化失败" in result["message"]
        assert result["data"]["persisted"] is False
        # 运行时仍生效（当前会话可用），但已如实告知重启可能丢失
        assert plugin._config["notify_enabled"] is True
    finally:
        db.close()