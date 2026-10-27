"""复杂 ASS 全链路验证：fontTools 索引 → 字形级缺失 → 严格上传 → HarfBuzz 子集化。

依赖 Windows 系统字体（arial.ttf / msyh.ttc）；缺失时整组跳过。
"""

import os
import shutil
from io import BytesIO
from pathlib import Path

import pytest

from ziti_under_test import font_metadata as fm
from ziti_under_test import font_utils as fu
from ziti_under_test import glyph_checker as gc
from ziti_under_test import harfbuzz_engine as he
from ziti_under_test.db import FontDB

FIXTURE = Path(__file__).parent / "fixtures" / "complex2.ass"
FONT_DIR = Path(r"C:\Windows\Fonts")
ARIAL = FONT_DIR / "arial.ttf"
MSYH = FONT_DIR / "msyh.ttc"

pytestmark = pytest.mark.skipif(
    not (ARIAL.is_file() and MSYH.is_file() and he.hb_available()[0]),
    reason="需要 Windows 字体与 uharfbuzz",
)


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


def _resolve(db: FontDB):
    def resolve(name: str):
        refs = []
        for row in db.lookup_faces(name) or []:
            path = str(row.get("file_path") or "")
            if path and Path(path).is_file():
                refs.append(
                    he.FaceRef(
                        file_path=path,
                        face_index=int(row.get("face_index") or 0),
                        codepoints=set(row.get("codepoints") or set()),
                        names=list(row.get("names") or []),
                    )
                )
        return refs

    return resolve


def _lookup_coverage(db: FontDB):
    def lookup(name: str):
        return [
            gc.FaceCoverage(
                face_id=int(row.get("face_id") or 0),
                file_path=str(row.get("file_path") or ""),
                face_index=int(row.get("face_index") or 0),
                names=list(row.get("names") or []),
                codepoints=set(row.get("codepoints") or set()),
            )
            for row in db.lookup_faces(name) or []
        ]

    return lookup


def _plugin(db: FontDB, lib: Path, tmp_path: Path):
    import importlib

    plugin_mod = importlib.import_module("ziti_under_test.__init__")

    plugin = plugin_mod.Zitifenlei()
    plugin._db = db
    plugin._enabled = True
    plugin._config.update({"lib_dir": str(lib), "subset_engine": "harfbuzz"})
    plugin._tmp_dir = tmp_path / "tmp"
    plugin._tmp_dir.mkdir(parents=True, exist_ok=True)
    return plugin


def test_complex_ass_glyph_detection(tmp_path):
    lib = _make_lib(tmp_path)
    db = _make_db(tmp_path, lib)
    try:
        usage, warnings = gc.parse_ass_usage(FIXTURE.read_bytes())
        assert not warnings, warnings
        # @竖排样式归一到本体：索引能查到微软雅黑两个 face
        assert len(db.lookup_faces("@微软雅黑")) >= 1
        assert "@微软雅黑" in usage and "NoSuchFont" in usage

        result = gc.evaluate_usage(usage.values(), _lookup_coverage(db))
        by_name = {item.name: item for item in result.fonts}

        # 完全缺失：样式与 \fn 覆盖都指向的 NoSuchFont
        assert by_name["NoSuchFont"].status == "missing"
        assert by_name["NoSuchFont"].missing_count == by_name["NoSuchFont"].used_count
        # Arial 名称存在但中文不覆盖 → partial，且逐字符明细只含中文
        arial = by_name["Arial"]
        assert arial.status == "partial"
        missing = set(arial.missing_codepoints)
        assert ord("数") in missing and ord("字") in missing and ord("切") in missing
        assert ord("H") not in missing and ord("1") not in missing
        assert "数" in arial.missing_chars
        # 微软雅黑覆盖所用中文 → 非 missing
        yahei = by_name["Microsoft YaHei"]
        assert yahei.status in ("ok", "partial")
        assert ord("中") not in set(yahei.missing_codepoints)
        # 绘图模式里的矢量字符、Comment/Picture/Sound/Movie/Command 不计入
        assert ord("m") not in set(by_name["Arial"].missing_codepoints)
        assert not any("注释" in item.missing_chars for item in result.fonts)

        # 检查结果：按字形级写入快照（引擎标记 fonttools）
        plugin = _plugin(db, lib, tmp_path)
        src = tmp_path / FIXTURE.name
        # 去掉样例末尾的假 [Fonts] 段（否则会被判定为已子集化而跳过字形检测）
        raw = he.strip_fonts_section(FIXTURE.read_text(encoding="utf-8")).encode("utf-8")
        src.write_bytes(raw)
        out = plugin._check_ass_content(FIXTURE.name, raw, source="manual", file_path=str(src))
        assert out["status"] == "missing"
        assert "NoSuchFont" in out["missing_fonts"]
        assert out["total_missing_chars"] > 0
        details = {item["name"]: item for item in out["missing_details"]}
        assert details["Arial"]["status"] == "partial"
        assert details["Arial"]["missing_chars"]
        row = db.get_ass(out["id"])
        assert row["check_engine"] == "fonttools"
        assert db.index_version() or True  # 索引版本可读

        # 严格上传：普通 Arial 无法修复 NoSuchFont 的中文缺失（名称命中但零覆盖）
        targets = plugin._missing_glyph_targets()
        assert "nosuchfont" in targets
        reject = plugin._evaluate_font_for_targets(lib / ARIAL.name, targets, "NoSuchFont")
        assert not reject["ok"] and "未覆盖" in reject["reason"]
        # 人工映射到 NoSuchFont：微软雅黑能覆盖其缺失中文 → 放行
        accept = plugin._evaluate_font_for_targets(lib / MSYH.name, targets, "NoSuchFont")
        assert accept["ok"] and accept["match_kind"] == "manual"
        assert accept["covered_chars"]
        assert "缺" in accept["covered_chars"] or "字" in accept["covered_chars"]

        # HarfBuzz 子集化：缺字体拦截（不产出半成品）
        hb_out = tmp_path / "blocked.ziti.ass"
        blocked = plugin._subset_with_hb(src, hb_out)
        assert blocked["status"] == "missing"
        assert "NoSuchFont" in blocked["missing_fonts"]
        assert not hb_out.exists()

        # 把 NoSuchFont 换成微软雅黑后：成功内嵌、原字幕不变、字体名写回正确
        fixed = tmp_path / "fixed.ass"
        fixed.write_text(
            FIXTURE.read_text(encoding="utf-8").replace("NoSuchFont", "Microsoft YaHei"),
            encoding="utf-8",
        )
        ok_out = tmp_path / "fixed.ziti.ass"
        done = plugin._subset_with_hb(fixed, ok_out)
        assert done["status"] == "success", done
        assert ok_out.is_file()
        assert fixed.read_text(encoding="utf-8").count("[Fonts]") == 1
        embedded = dict(he.extract_embedded_fonts(ok_out.read_bytes()))
        # @竖排与同名常规字体合并成一份，内嵌标签不带 @
        assert {"Arial", "Microsoft YaHei", "微软雅黑"} <= set(embedded)
        from fontTools.ttLib import TTFont

        fixed_usage, _ = gc.parse_ass_usage(fixed.read_bytes())
        for name, blob in embedded.items():
            entry = fixed_usage.get(name) or fixed_usage.get("@" + name)
            assert entry is not None, name
            font = TTFont(BytesIO(blob), fontNumber=0)
            try:
                cmap = set(font.getBestCmap() or {})
                faces = _resolve(db)(name)
                covered = set(entry.codepoints) & set().union(*(f.codepoints for f in faces))
                assert covered <= cmap, f"{name} 缺少 {len(covered - cmap)} 个字符"
                # 内部 family 名已改成 ASS 引用名（libass 按内部元数据匹配）
                assert font["name"].getDebugName(1) == name
            finally:
                font.close()
    finally:
        db.close()
