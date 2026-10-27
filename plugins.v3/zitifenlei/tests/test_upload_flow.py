"""上传链路验证：zip 解包路由、缺失字体严格上传（含人工映射）、批量 HarfBuzz 子集化落盘。"""

import asyncio
import importlib
import io
import os
import shutil
import zipfile
from pathlib import Path

import pytest

from ziti_under_test import font_metadata as fm
from ziti_under_test import font_utils as fu
from ziti_under_test import harfbuzz_engine as he
from ziti_under_test.db import FontDB

FIXTURE = Path(__file__).parent / "fixtures" / "complex2.ass"
FONT_DIR = Path(r"C:\Windows\Fonts")
ARIAL = FONT_DIR / "arial.ttf"
MSYH = FONT_DIR / "msyh.ttc"

needs_fonts = pytest.mark.skipif(
    not (ARIAL.is_file() and MSYH.is_file() and he.hb_available()[0]),
    reason="需要 Windows 字体与 uharfbuzz",
)


# ─── 上传桩：模拟 FastAPI UploadFile / Request.form ──────────────────────


class _Upload:
    def __init__(self, filename: str, data: bytes) -> None:
        self.filename = filename
        self._data = data

    async def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            data, self._data = self._data, b""
            return data
        chunk, self._data = self._data[:size], self._data[size:]
        return chunk


class _Form:
    def __init__(self, files, target: str = "") -> None:
        self._files = list(files)
        self._target = target

    def getlist(self, key: str):
        return list(self._files) if key == "file" else []

    def get(self, key: str):
        return self._target if key == "target" else None


class _Request:
    def __init__(self, form: _Form) -> None:
        self._form = form

    async def form(self) -> _Form:
        return self._form


def _make_zip(members: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


# ─── 公共脚手架 ──────────────────────────────────────────────────────────


def _plugin(tmp_path: Path, db: FontDB, lib: Path):
    plugin_mod = importlib.import_module("ziti_under_test.__init__")
    plugin = plugin_mod.Zitifenlei()
    plugin._db = db
    plugin._enabled = True
    plugin._config.update({"lib_dir": str(lib), "subset_engine": "harfbuzz"})
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


# ─── 1. 压缩包上传路由 ──────────────────────────────────────────────────


def test_receive_uploads_zip_routes_extensions(tmp_path):
    plugin_mod = importlib.import_module("ziti_under_test.__init__")
    plugin = plugin_mod.Zitifenlei()
    plugin._tmp_dir = tmp_path / "tmp"
    plugin._tmp_dir.mkdir(parents=True, exist_ok=True)

    font_zip = _make_zip(
        {
            "fonts/arial.ttf": b"font-bytes",
            "__MACOSX/._arial.ttf": b"junk",
            "readme.txt": b"not-a-font",
            "inner.zip": b"PK\x03\x04nested",
        }
    )
    files, notes = asyncio.run(
        plugin._receive_uploads(
            [_Upload("Fonts.zip", font_zip), _Upload("direct.ttf", b"direct-bytes")],
            fu.FONT_EXTENSIONS,
            prefix="up",
        )
    )
    names = sorted(item["file_name"] for item in files)
    assert names == ["arial.ttf", "direct.ttf"]
    zipped = next(item for item in files if item["file_name"] == "arial.ttf")
    assert zipped["from_archive"] == "Fonts.zip"
    assert Path(zipped["path"]).read_bytes() == b"font-bytes"
    direct = next(item for item in files if item["file_name"] == "direct.ttf")
    assert direct["from_archive"] == ""
    # 跳过项要回显：非字体、嵌套压缩包、__MACOSX 垃圾目录
    joined = "\n".join(notes)
    assert "readme.txt" in joined
    assert "inner.zip" in joined
    assert "__MACOSX" in joined or "._arial.ttf" in joined

    ass_zip = _make_zip({"sub/a.ass": b"[Script Info]", "sub/b.srt": b"1"})
    ass_files, _ = asyncio.run(
        plugin._receive_uploads([_Upload("Subs.zip", ass_zip)], fu.ASS_EXTENSIONS, prefix="ass")
    )
    assert [item["file_name"] for item in ass_files] == ["a.ass"]


# ─── 2. 缺失字体严格上传 ────────────────────────────────────────────────


@needs_fonts
def test_missing_upload_strict_and_manual_mapping(tmp_path):
    lib = _make_lib(tmp_path)
    db = _make_db(tmp_path, lib)
    try:
        plugin = _plugin(tmp_path, db, lib)
        raw = he.strip_fonts_section(FIXTURE.read_text(encoding="utf-8")).encode("utf-8")
        src = tmp_path / "strict.ass"
        src.write_bytes(raw)
        checked = plugin._check_ass_content(FIXTURE.name, raw, source="manual", file_path=str(src))
        assert checked["status"] == "missing"
        targets = plugin._missing_glyph_targets()
        assert "nosuchfont" in targets

        # Arial 名称不匹配且中文零覆盖 → 拒绝（临时文件随即删除）
        bad = asyncio.run(
            plugin.api_missing_upload(
                _Request(_Form([_Upload("arial.ttf", ARIAL.read_bytes())], target="NoSuchFont"))
            )
        )
        assert bad["success"] is False
        assert "没有字体通过缺失校验" in bad["message"]
        assert "未覆盖" in bad["message"]
        assert not list((tmp_path / "tmp").glob("missing_*")) or all(
            not p.is_file() for p in (tmp_path / "tmp").glob("missing_*")
        )

        # 微软雅黑（人工指定 NoSuchFont）通过校验，并写入审计映射
        good = asyncio.run(
            plugin.api_missing_upload(
                _Request(
                    _Form(
                        [_Upload("fonts.zip", _make_zip({"MSYH.TTC": MSYH.read_bytes()}))],
                        target="NoSuchFont",
                    )
                )
            )
        )
        assert good["success"] is True, good.get("message")
        data = good["data"]
        assert data["count"] == 1
        item = data["items"][0]
        assert item["match_kind"] == "manual"
        assert item["matched"].lower() == "nosuchfont"
        assert item["covered_chars"]
        assert item["required_chars"]
        mappings = db.list_manual_font_mappings()
        assert any(row["source_name"] == item["name"] for row in mappings)
    finally:
        db.close()


@needs_fonts
def test_library_upload_resolves_missing_without_missing_page(tmp_path):
    """字体库那边补齐字体后：缺失页/检查详情立即不再显示（无需在缺失页上传）。"""
    from fontTools.ttLib import TTFont

    lib = _make_lib(tmp_path)
    db = _make_db(tmp_path, lib)
    try:
        plugin = _plugin(tmp_path, db, lib)
        raw = he.strip_fonts_section(FIXTURE.read_text(encoding="utf-8")).encode("utf-8")
        src = tmp_path / "library_fix.ass"
        src.write_bytes(raw)
        checked = plugin._check_ass_content(FIXTURE.name, raw, source="manual", file_path=str(src))
        targets = plugin._missing_glyph_targets()
        assert "nosuchfont" in targets
        assert "nosuchfont" in {item["key"] for item in plugin.api_missing_summary()["data"]["check"]}

        # 模拟「字体库」上传：把一份带完整中文覆盖的字体重命名为 NoSuchFont 后归档入库
        clone = lib / "NoSuchFont.ttf"
        font = TTFont(str(MSYH), fontNumber=0)
        try:
            for name_id in (1, 4, 6, 16, 17):
                font["name"].setName("NoSuchFont", name_id, 3, 1, 0x409)
            font.save(str(clone))
        finally:
            font.close()
        plugin._index_font_path(clone)

        # 缺失聚合/上传目标/检查详情全部按当前字体库实时扣除
        assert "nosuchfont" not in {item["key"] for item in plugin.api_missing_summary()["data"]["check"]}
        assert "nosuchfont" not in plugin._missing_glyph_targets()
        detail = plugin.api_ass_detail(checked["id"])["data"]
        assert "NoSuchFont" not in (detail.get("missing_fonts") or [])
        by_name = {item["name"]: item for item in detail.get("missing_details") or []}
        assert by_name["NoSuchFont"]["status"] == "ok"
        assert by_name["NoSuchFont"]["missing_count"] == 0
        # Arial 仍部分缺失（库内 Arial 不含那些中文），不受影响
        assert "Arial" in (detail.get("missing_fonts") or [])

        # 字体库归档后的重检：存储状态同步更新（源字幕存在时）
        recheck = plugin._recheck_missing_after_library_change("测试字体库补齐")
        assert recheck["checked"] >= 1
        row = db.get_ass(checked["id"])
        assert "NoSuchFont" not in (row.get("missing_fonts") or [])
    finally:
        db.close()


@needs_fonts
def test_startup_light_check_rebuilds_empty_and_drops_deleted(tmp_path):
    """启动轻检：索引为空时从磁盘重建；磁盘删除的字体撤销索引（不需要全量重扫）。"""
    lib = _make_lib(tmp_path)
    db = FontDB(tmp_path / "ziti.db")  # 空索引，模拟升级后首次启动
    try:
        plugin = _plugin(tmp_path, db, lib)
        plugin._config["startup_light_check"] = True

        plugin._startup_light_check()
        stats = db.index_stats()
        assert stats["files"] == 2
        assert stats["faces"] >= 2

        removed = lib / "arial.ttf"
        removed.unlink()
        plugin._startup_light_check()
        assert db.get_font_file(str(removed.resolve())) is None
        assert db.index_stats()["files"] == 1
    finally:
        db.close()


@needs_fonts
def test_full_rebuild_clears_and_reparses_all(tmp_path):
    """「全部重建」：清空索引后逐文件重新解析（indexed=全部，不是增量的 unchanged 跳过）。"""
    lib = _make_lib(tmp_path)
    db = _make_db(tmp_path, lib)
    try:
        plugin = _plugin(tmp_path, db, lib)
        # 先做一次普通增量：全部命中 unchanged
        inc = plugin._rebuild_font_index()
        assert inc["ok"] and inc["indexed"] == 0 and inc["unchanged"] == 2

        full = plugin._rebuild_font_index(full=True)
        assert full["ok"]
        assert full["indexed"] == 2 and full["unchanged"] == 0
        assert db.index_stats()["files"] == 2
        assert db.index_stats()["faces"] >= 2
    finally:
        db.close()


@needs_fonts
def test_inbound_subset_overwrite_option(tmp_path):
    """MP 入库：默认保留原字幕出 .ziti.ass；开启「替换原字幕」后就地替换且不再多一份。"""
    lib = _make_lib(tmp_path)
    db = _make_db(tmp_path, lib)
    try:
        plugin = _plugin(tmp_path, db, lib)
        media = tmp_path / "media"
        media.mkdir()
        src = media / "episode.ass"
        src.write_text(
            he.strip_fonts_section(FIXTURE.read_text(encoding="utf-8")).replace(
                "NoSuchFont", "Microsoft YaHei"
            ),
            encoding="utf-8",
        )
        # 默认关：原字幕不动，生成副本
        stats = plugin._run_subset_batch([src], source="inbound")
        assert stats["success"] == 1, stats
        copied = media / "episode.ziti.ass"
        assert copied.is_file()
        assert not fu.has_embedded_fonts(src.read_bytes())

        # 开启后：就地替换原字幕，不再生成副本
        plugin._config["inbound_subset_overwrite"] = True
        copied.unlink()
        stats = plugin._run_subset_batch([src], source="inbound")
        assert stats["success"] == 1, stats
        assert fu.has_embedded_fonts(src.read_bytes())
        assert not copied.exists()
    finally:
        db.close()


@needs_fonts
def test_watch_output_dir_overwrite_only_deletes_source(tmp_path):
    """目录监控 + 输出目录：成品一律进输出目录；「覆盖原文件」只决定是否删监控目录源字幕。"""
    lib = _make_lib(tmp_path)
    db = _make_db(tmp_path, lib)
    try:
        plugin = _plugin(tmp_path, db, lib)
        watch = tmp_path / "watch"
        out = tmp_path / "out"
        watch.mkdir()
        out.mkdir()
        plugin._config.update({"subset_dir": str(watch), "subset_out_dir": str(out)})
        body = he.strip_fonts_section(FIXTURE.read_text(encoding="utf-8")).replace(
            "NoSuchFont", "Microsoft YaHei"
        )

        # 默认关：源字幕保留，成品输出到输出目录
        src = watch / "movie.ass"
        src.write_text(body, encoding="utf-8")
        stats = plugin._run_subset_batch([src], source="watch")
        assert stats["success"] == 1, stats
        assert src.is_file()
        produced = list(out.rglob("*.ass"))
        assert len(produced) == 1, produced
        assert fu.has_embedded_fonts(produced[0].read_bytes())

        # 开启「覆盖原文件」：成品输出成功后删除监控目录的源字幕
        src2 = watch / "movie2.ass"
        src2.write_text(body, encoding="utf-8")
        plugin._config["subset_overwrite"] = True
        stats = plugin._run_subset_batch([src2], source="watch")
        assert stats["success"] == 1, stats
        assert not src2.exists()
        assert len(list(out.rglob("*.ass"))) == 2
    finally:
        db.close()


# ─── 3. 批量子集化真实落盘 ──────────────────────────────────────────────

@needs_fonts
def test_run_subset_batch_outputs_ziti_and_skips_embedded(tmp_path):
    lib = _make_lib(tmp_path)
    db = _make_db(tmp_path, lib)
    try:
        plugin = _plugin(tmp_path, db, lib)
        fixed = plugin._tmp_dir / "episode.ass"
        fixed.write_text(
            he.strip_fonts_section(FIXTURE.read_text(encoding="utf-8")).replace(
                "NoSuchFont", "Microsoft YaHei"
            ),
            encoding="utf-8",
        )
        stats = plugin._run_subset_batch([fixed], source="manual")
        assert stats["success"] == 1, stats
        assert stats["missing"] == 0 and stats["error"] == 0
        out = plugin._tmp_dir / "episode.ziti.ass"
        assert out.is_file()
        embedded = dict(he.extract_embedded_fonts(out.read_bytes()))
        # @竖排与同名常规字体合并成一份，内嵌标签不带 @
        assert {"Arial", "Microsoft YaHei", "微软雅黑"} <= set(embedded)
        # 成品再跑一次：识别为已子集化 → 跳过，不重复内嵌
        again = plugin._run_subset_batch([out], source="manual")
        assert again["skipped"] == 1 and again["success"] == 0
        records = db.list_subset_records(limit=10)["list"]
        assert records[0]["status"] == "skipped"
        assert any(row["status"] == "success" for row in records)
    finally:
        db.close()


# ─── 4. ASS 字体名解析回归（通知/缺失检测共同口径）────────────────────

def test_parse_ass_fonts_skips_comment_and_nested_t():
    """注释里的示例 \\fn、\\t(...) 嵌套标签不能变成字体名，更不能跨行吞掉整段字幕。"""
    raw = FIXTURE.read_text(encoding="utf-8")
    names = fu.parse_ass_fonts(raw.encode("utf-8"))
    assert {"Arial", "Microsoft YaHei", "@微软雅黑", "NoSuchFont"} <= set(names)
    # 注释行示例（"覆盖：…\\fn 覆盖…"）不应被当成字体
    assert "覆盖" not in names and "覆盖、" not in names
    # \t(0,800,\fnArial) 尾部的 ")" 必须剥掉，与 glyph_checker 口径一致
    assert "Arial)" not in names and "微软雅黑)" not in names
    # 跨行/超长垃圾条目一律不允许出现
    assert all("\n" not in n and len(n) <= 64 for n in names)
    # Comment 事件行不参与渲染，里面的 \fn 也不能被当成字体
    with_comment = raw + '\nComment: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,{\\fnCommentFont}注释\n'
    assert "CommentFont" not in fu.parse_ass_fonts(with_comment.encode("utf-8"))


# ─── 5. 通知链路（真实触发，桩记录 post_message）────────────────────────

def _notify_recorder(plugin):
    """接管 post_message，返回 (已发送消息列表, 原始实现)。"""
    sent = []

    def _fake(**kwargs):
        sent.append(kwargs)
        return True

    plugin.post_message = _fake
    return sent


@needs_fonts
def test_auto_monitor_real_archive_sends_notify(tmp_path):
    """轮询兜底真实归档一个新字体 → 必须发一条「自动归档（复制模式）」通知且计数正确。"""
    lib = tmp_path / "lib"
    lib.mkdir()
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    shutil.copy2(ARIAL, incoming / ARIAL.name)
    db = FontDB(tmp_path / "ziti.db")
    try:
        plugin = _plugin(tmp_path, db, lib)
        plugin._config.update(
            {
                "input_dir": str(incoming),
                "archive_mode": "copy",
                "auto_collect": True,
                "notify_enabled": True,
            }
        )
        sent = _notify_recorder(plugin)
        getattr(plugin, "_Zitifenlei__auto_monitor_scan")()
        assert len(sent) == 1, sent
        assert "自动归档" in sent[0]["title"] and "复制模式" in sent[0]["title"]
        body = sent[0]["text"]
        assert "新增归档 1 个" in body and ARIAL.name in body
    finally:
        db.close()


@needs_fonts
def test_agg_notify_splits_fonts_and_subtitles(tmp_path):
    """聚合通知：字体一条、字幕一条；缺失/已子集化/齐全三类都进字幕正文。"""
    lib = _make_lib(tmp_path)
    db = _make_db(tmp_path, lib)
    try:
        plugin = _plugin(tmp_path, db, lib)
        plugin._config["notify_enabled"] = True
        sent = _notify_recorder(plugin)
        with plugin._lock:
            plugin._notify_agg["fonts"] = ["arial.ttf"]
            plugin._notify_agg["fonts_skipped"] = ["msyh.ttc"]
            plugin._notify_agg["font_failed"] = 1
            plugin._notify_agg["archive_mode"] = "copy"
            plugin._notify_agg["subs_missing"] = [
                {"name": "ep01.ass", "count": 2, "fonts": ["方正兰亭黑", "思源黑体"]}
            ]
            plugin._notify_agg["subs_subset"] = ["ep02.ziti.ass"]
            plugin._notify_agg["subs_ok"] = ["ep03.ass"]
        plugin._flush_agg_notify()
        assert len(sent) == 2, sent
        titles = [m["title"] for m in sent]
        assert any("自动归档" in t for t in titles)
        sub = next(m for m in sent if "字幕检查" in m["title"])
        assert "缺 2 个字体" in sub["text"]
        assert "已子集化（自带内嵌字体）1 个" in sub["text"]
        assert "字体齐全（已逐字符验证）1 个" in sub["text"]
        # 发送后缓冲必须清空，避免重复通知
        assert plugin._notify_agg["fonts"] == []
        assert plugin._notify_agg["subs_missing"] == []
    finally:
        db.close()


@needs_fonts
def test_run_show_scan_real_missing_notify(tmp_path):
    """MP 入库剧集聚合检查真实跑：缺字体通知带剧名、总数、缺失种数。"""
    lib = _make_lib(tmp_path)
    db = _make_db(tmp_path, lib)
    try:
        plugin = _plugin(tmp_path, db, lib)
        plugin._config.update({"auto_inbound": True, "auto_subset": False, "notify_enabled": True})
        ep = tmp_path / "media" / "ep01.ass"
        ep.parent.mkdir()
        # 去掉内嵌 [Fonts] 段，才会走「字体库比对/缺失」路径
        ep.write_text(
            he.strip_fonts_section(FIXTURE.read_text(encoding="utf-8")), encoding="utf-8"
        )
        sent = _notify_recorder(plugin)
        plugin._run_show_scan("测试剧:1", "1", "测试剧", [str(ep)])
        assert len(sent) == 1, sent
        assert "《测试剧》字幕检查完成" in sent[0]["title"]
        body = sent[0]["text"]
        assert "共 1 个字幕" in body and "缺失" in body
    finally:
        db.close()


@needs_fonts
def test_run_show_subset_real_notify(tmp_path):
    """MP 入库自动子集化真实跑（同步）：成功 1 个 → 通知标题带剧名、正文报成功数。"""
    lib = _make_lib(tmp_path)
    db = _make_db(tmp_path, lib)
    try:
        plugin = _plugin(tmp_path, db, lib)
        plugin._config.update({"notify_enabled": True, "inbound_subset_overwrite": False})
        ep = tmp_path / "media" / "ep01.ass"
        ep.parent.mkdir()
        ep.write_text(
            he.strip_fonts_section(FIXTURE.read_text(encoding="utf-8")).replace(
                "NoSuchFont", "Microsoft YaHei"
            ),
            encoding="utf-8",
        )
        sent = _notify_recorder(plugin)
        plugin._run_show_subset([ep], "测试剧", source="inbound")
        assert len(sent) == 1, sent
        assert "子集化完成（测试剧）" in sent[0]["title"]
        assert "已子集化 1 个字幕" in sent[0]["text"]
    finally:
        db.close()


@needs_fonts
def test_notify_disabled_and_exception_safe(tmp_path):
    """通知关闭时静默；post_message 抛异常时整条链路不崩。"""
    lib = _make_lib(tmp_path)
    db = _make_db(tmp_path, lib)
    try:
        plugin = _plugin(tmp_path, db, lib)
        plugin._config["notify_enabled"] = False
        sent = _notify_recorder(plugin)
        with plugin._lock:
            plugin._notify_agg["subs_ok"] = ["ep01.ass"]
        plugin._flush_agg_notify()
        assert sent == []

        plugin._config["notify_enabled"] = True

        def _boom(**kwargs):
            raise RuntimeError("宿主通知通道异常")

        plugin.post_message = _boom
        assert plugin._notify("测试", "正文") is False
        with plugin._lock:
            plugin._notify_agg["subs_ok"] = ["ep01.ass"]
        plugin._flush_agg_notify()  # 不应抛异常
    finally:
        db.close()


# ─── 3. 竖排 @ 字体与同名常规字体合并 ────────────────────────────────────


@needs_fonts
def test_vertical_font_merges_with_regular_same_family(tmp_path):
    """@竖排与同名常规字体只内嵌一份，字符取并集，内部 family 不带 @。"""
    from fontTools.ttLib import TTFont

    raw = (he.strip_fonts_section(FIXTURE.read_text(encoding="utf-8")) + "\n").encode("utf-8")
    src = tmp_path / "vertical.ass"
    src.write_text(raw.decode("utf-8"), encoding="utf-8")
    out = tmp_path / "vertical.ziti.ass"

    usage = {
        "@Microsoft YaHei": {ord(c) for c in "竖排"},
        "Microsoft YaHei": {ord(c) for c in "字体"},
    }
    faces = [he.FaceRef(str(MSYH), 0, codepoints=set(range(0x20, 0x9FA6)))]
    result = he.subset_ass_file(src, out, usage, lambda _name: faces)
    assert result.success, result.errors
    assert len(result.embedded) == 1, [i.font_name for i in result.embedded]
    assert result.embedded[0].font_name == "Microsoft YaHei"
    assert result.embedded[0].required == 4  # 竖/排/字/体 四个字符的并集

    embedded = he.extract_embedded_fonts(out.read_bytes())
    assert [name for name, _ in embedded] == ["Microsoft YaHei"]
    font = TTFont(io.BytesIO(embedded[0][1]))
    try:
        cmap = font.getBestCmap()
        for ch in "竖排字体":
            assert ord(ch) in cmap
        family = font["name"].getDebugName(1) or ""
        assert not family.startswith("@")
        assert family == "Microsoft YaHei"
    finally:
        font.close()


# ─── 4. P0 安全/数据修复回归 ────────────────────────────────────────────


@needs_fonts
def test_archive_sanitizes_evil_internal_name(tmp_path, monkeypatch):
    """字体内部名为 ../../escape 时归档仍必须落在字体库内，且文件名不含分隔符。"""
    plugin_mod = importlib.import_module("ziti_under_test.__init__")
    lib = _make_lib(tmp_path)
    db = _make_db(tmp_path, lib)
    try:
        plugin = _plugin(tmp_path, db, lib)
        plugin._config.update({"font_name_internal": False, "archive_mode": "copy"})

        evil = tmp_path / "evil.ttf"
        evil.write_bytes(ARIAL.read_bytes())
        # 模拟字体 name 表被写入 "../../escape"（真实文件由 fontTools 构造等价，这里直接桩元数据）
        monkeypatch.setattr(
            plugin_mod,
            "parse_font_metadata",
            lambda *a, **k: {
                "name": "../../escape",
                "family": "evil",
                "vendor": "..",
                "designer": "",
            },
        )

        font_id = plugin._archive_font_file(evil, source="test")
        assert font_id
        archived = [p for p in lib.rglob("*.ttf") if "escape" in p.name]
        assert archived, list(lib.rglob("*"))
        for path in archived:
            assert path.resolve().is_relative_to(lib.resolve())
            assert not any(ch in path.name for ch in '\\/:*?"<>|')
        assert evil.exists()  # copy 模式不动源文件
    finally:
        db.close()


@needs_fonts
def test_subset_failure_keeps_previous_output(tmp_path):
    """缺字体重跑时不得删除上一轮成功生成的 .ziti.ass。"""
    lib = _make_lib(tmp_path)
    db = _make_db(tmp_path, lib)
    try:
        plugin = _plugin(tmp_path, db, lib)
        src = tmp_path / "missing.ass"
        src.write_text(
            "[Script Info]\nScriptType: v4.00+\n\n"
            "[V4+ Styles]\n"
            "Style: Default,NoSuchFont,52,&H00FFFFFF,&H000000FF,&H00000000,"
            "&H00000000,0,0,0,0,100,100,0,0,1,2,1,2,30,30,30,1\n\n"
            "[Events]\n"
            "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,缺字体\n",
            encoding="utf-8",
        )
        out = tmp_path / "missing.ziti.ass"
        out.write_text("OLD-PRODUCT", encoding="utf-8")

        res = plugin._subset_with_hb(src, out)
        assert res["status"] == "missing"
        assert out.read_text(encoding="utf-8") == "OLD-PRODUCT"
    finally:
        db.close()


def test_get_api_write_endpoints_require_admin(monkeypatch):
    """写接口要带管理员依赖，只读接口不带。"""
    plugin_mod = importlib.import_module("ziti_under_test.__init__")
    monkeypatch.setattr(plugin_mod, "_admin_write_dependencies", lambda: ["ADMIN"])
    plugin = plugin_mod.Zitifenlei()
    apis = plugin.get_api()
    assert apis
    for api in apis:
        mutating = any(str(m).upper() in ("POST", "PUT", "PATCH", "DELETE") for m in api["methods"])
        assert ("dependencies" in api) == mutating, api["path"]
        if mutating:
            assert api["dependencies"] == ["ADMIN"]

