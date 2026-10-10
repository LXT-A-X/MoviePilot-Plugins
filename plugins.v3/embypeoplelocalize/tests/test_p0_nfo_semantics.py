# -*- coding: utf-8 -*-
"""P0 回归测试：NFO 解析语义（NFO-008 非影视 NFO 不采集 / NFO-009 编码兼容）。

运行：python tests/test_p0_nfo_semantics.py
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import test_p0_nfo_checkpoint as base     # noqa: E402  （安装宿主桩件）
import test_p0_scan_e2e as e2e            # noqa: E402  （复用扫描用的假插件/夹具）

check = base.check

from embypeoplelocalize import nfo as nfo_engine  # noqa: E402
from embypeoplelocalize.db import PeopleDb        # noqa: E402

_SEM_ROOT = os.path.join(base._TMP, "semantics")
os.makedirs(_SEM_ROOT, exist_ok=True)

MOVIE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<movie><title>Movie X</title><tmdbid>1001</tmdbid>
<actor><name>Tom Hanks</name><role>Forrest</role><type>Actor</type></actor></movie>
"""
ALBUM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<album><title>Some Album</title><artist>Some Artist</artist></album>
"""


def _w(path, text, enc="utf-8", bom=False):
    data = text.encode(enc)
    if bom and enc == "utf-8":
        data = b"\xef\xbb\xbf" + data
    if bom and enc.startswith("utf-16"):
        data = ("\ufeff" + text).encode(enc)
    with open(path, "wb") as f:
        f.write(data)
    return path


def test_encoding():
    print("A) NFO-009：编码支持（UTF-8 / UTF-8 BOM / UTF-16 双字节序）")
    d = os.path.join(_SEM_ROOT, "enc")
    os.makedirs(d, exist_ok=True)
    p_u8 = _w(os.path.join(d, "u8.nfo"), MOVIE_XML)
    p_bom = _w(os.path.join(d, "bom.nfo"), MOVIE_XML, bom=True)
    p_le = _w(os.path.join(d, "le.nfo"), MOVIE_XML, enc="utf-16-le", bom=True)
    p_be = _w(os.path.join(d, "be.nfo"), MOVIE_XML, enc="utf-16-be", bom=True)
    check("UTF-8 正常解析", nfo_engine.parse_nfo(p_u8) is not None)
    doc_bom = nfo_engine.parse_nfo(p_bom)
    check("UTF-8 BOM 正常解析且识别 BOM", doc_bom is not None and doc_bom.has_bom is True)
    doc_le = nfo_engine.parse_nfo(p_le)
    check("UTF-16 LE 正常解析（原先整批跳过）", doc_le is not None and doc_le.encoding == "utf-16-le")
    doc_be = nfo_engine.parse_nfo(p_be)
    check("UTF-16 BE 正常解析", doc_be is not None and doc_be.encoding == "utf-16-be")
    check("UTF-16 文件内容解析正确",
          doc_le is not None and (doc_le.root.findtext("title") or "") == "Movie X")
    # 写回保持原编码（不把用户文件转成 UTF-8）
    ok = doc_le.save(backup=False)
    raw = open(p_le, "rb").read()
    check("UTF-16 文件写回成功", bool(ok), "save failed")
    check("写回后仍是 UTF-16 LE + BOM", raw.startswith(b"\xff\xfe"), raw[:4])
    check("写回后内容可读回", "Movie X" in raw.decode("utf-16"))
    # 无 BOM 的非 UTF-8（如 GBK）不猜测、不误读
    p_gbk = os.path.join(d, "gbk.nfo")
    with open(p_gbk, "wb") as f:
        f.write(MOVIE_XML.replace("Movie X", "测试电影·汤姆汉克斯").encode("gbk"))
    doc_gbk = nfo_engine.parse_nfo(p_gbk)
    check("GBK（无 BOM）明确拒绝而非乱码入库", doc_gbk is None)


def test_non_video_root():
    print("B) NFO-008：非影视 NFO 按根节点识别")
    d = os.path.join(_SEM_ROOT, "root")
    os.makedirs(d, exist_ok=True)
    p_album = _w(os.path.join(d, "album.nfo"), ALBUM_XML)
    doc = nfo_engine.parse_nfo(p_album)
    check("album.nfo（根 <album>）判为非影视", doc is not None and doc.unsupported is True)
    check("给出跳过原因", "album" in str(getattr(doc, "unsupported_reason", "")))
    p_movie = _w(os.path.join(d, "Movie X.nfo"), MOVIE_XML)
    doc_m = nfo_engine.parse_nfo(p_movie)
    check("普通电影 nfo（无 movie.nfo 文件名、根 <movie>）照常处理",
          doc_m is not None and not getattr(doc_m, "unsupported", False))
    p_unknown = _w(os.path.join(d, "weird.nfo"),
                   "<?xml version=\"1.0\"?><foo><bar>1</bar></foo>")
    doc_w = nfo_engine.parse_nfo(p_unknown)
    check("未知根节点不表态（沿用文件名判定，保持旧行为）",
          doc_w is not None and not getattr(doc_w, "unsupported", False))
    check("root_level 映射正确",
          nfo_engine.root_level("ALBUM") == "unsupported"
          and nfo_engine.root_level("movie") == "movie"
          and nfo_engine.root_level("Whatever") == "")


def test_scan_skips_non_video():
    print("C) 扫描流程：非影视 NFO 不入库、计入签名表（不重复解析）")
    lib = os.path.join(_SEM_ROOT, "lib")
    os.makedirs(os.path.join(lib, "Movie X"), exist_ok=True)
    os.makedirs(os.path.join(lib, "Music"), exist_ok=True)
    base._write(os.path.join(lib, "Movie X", "movie.nfo"), MOVIE_XML)
    _w(os.path.join(lib, "Music", "album.nfo"), ALBUM_XML)
    obj = e2e._new_plugin(lib)
    calls = e2e._wrap_calls(obj)
    e2e._run_scan(obj, lib)
    items = PeopleDb().library_items(plugin_id="EmbyPeopleLocalize") or []
    check("只有影视条目入库", [str(it.get("item_id")) for it in items] == ["1001"],
          str([it.get("item_id") for it in items]))
    check("album.nfo 未被记录", all("album" not in str(p).lower() for p in calls), str(calls))
    check("日志报告跳过非影视", any("跳过非影视 1 个" in m for m in obj._logs),
          str([m for m in obj._logs if "跳过" in m][-2:]))
    check("album.nfo 已进签名表（下轮不再解析）",
          any("album" in k.lower() for k in (obj._nfo_file_sigs or {})),
          str(list((obj._nfo_file_sigs or {}).keys())))
    # 第二轮：整库按签名跳过，不再出现「跳过非影视」计数
    obj2 = e2e._new_plugin(lib)
    obj2._nfo_file_sigs = dict(obj._nfo_file_sigs or {})
    obj2._nfo_sigs_cfg = obj._nfo_sigs_cfg
    e2e._run_scan(obj2, lib)
    check("第二轮不再重复解析非影视文件",
          not any("跳过非影视" in m for m in obj2._logs), str(obj2._logs[-3:]))


if __name__ == "__main__":
    print(f"语义测试目录: {_SEM_ROOT}")
    test_encoding()
    test_non_video_root()
    test_scan_skips_non_video()
    print(f"\n结果: {base._PASS} 通过 / {base._FAIL} 失败")
    sys.exit(1 if base._FAIL else 0)