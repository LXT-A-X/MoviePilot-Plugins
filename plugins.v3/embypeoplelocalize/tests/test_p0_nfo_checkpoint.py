# -*- coding: utf-8 -*-
"""P0 回归测试：NFO 扫描断点 / 文件签名（NFO-001 / NFO-003 / NFO-004）。

不依赖 pytest，直接运行：
    python tests/test_p0_nfo_checkpoint.py

说明：MoviePilot 宿主模块（app.*）以桩件注入，仅用于把插件模块导入起来；
本测试只覆盖插件自身的断点与签名逻辑，不触碰宿主交互。
NFO-002（入库失败不得计入断点）是扫描 worker 内的控制流，需要宿主运行环境，
见测试末尾说明 —— 当前由代码审查 + 本文件的不变量断言共同保证。
"""
import os
import sys
import tempfile
import time
import types

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)          # 插件目录
_PKG_PARENT = os.path.dirname(_ROOT)    # 插件目录的父级（供 import 包名）
if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)

_TMP = tempfile.mkdtemp(prefix="epl_p0_test_")


def _install_host_stubs():
    """注入 MoviePilot 宿主最小桩件（只为导入插件，不测宿主行为）。"""
    class _Logger:
        def _p(self, *a, **k):
            pass
        info = debug = warning = error = exception = critical = _p

    class _Settings:
        CONFIG_PATH = _TMP

    class _PluginBase:
        pass

    class _EventTypeMeta(type):
        def __getattr__(cls, name):
            return name   # 任意事件名可用（类体上 @eventmanager.register(...) 用）

    class _EventType(metaclass=_EventTypeMeta):
        pass

    class _NotificationType:
        Manual = "Manual"

    class _ServiceInfo(dict):
        pass

    class _Event:
        def __init__(self, *a, **k):
            pass

    class _EventManager:
        def register(self, *a, **k):
            def _deco(fn):
                return fn
            return _deco

        def send_event(self, *a, **k):
            pass

    class _MediaServerHelper:
        pass

    def _mk(name, **attrs):
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[name] = m
        return m

    app = _mk("app")
    sdk = _mk("app.sdk")
    _cfg = _mk("app.sdk.config", settings=_Settings)
    _log = _mk("app.sdk.logging", logger=_Logger())
    _ev = _mk("app.sdk.events", eventmanager=_EventManager(), Event=_Event)
    _svc = _mk("app.sdk.services", MediaServerHelper=_MediaServerHelper)
    _plugins = _mk("app.plugins", _PluginBase=_PluginBase)
    schemas = _mk("app.schemas", ServiceInfo=_ServiceInfo, NotificationType=_NotificationType)
    _types = _mk("app.schemas.types", EventType=_EventType)
    sdk.config, sdk.logging, sdk.events, sdk.services = _cfg, _log, _ev, _svc
    app.sdk, app.plugins, app.schemas = sdk, _plugins, schemas
    schemas.types = _types

    # requests 缺失时给最小桩件（仅导入用；本测试不发起任何 HTTP）
    try:
        import requests  # noqa: F401
    except Exception:
        _ex = _mk("requests.exceptions", RequestException=Exception, ConnectionError=Exception,
                  Timeout=Exception, HTTPError=Exception)
        _mk("requests", Session=object, get=lambda *a, **k: None, post=lambda *a, **k: None,
            exceptions=_ex, RequestException=Exception)


_install_host_stubs()

from embypeoplelocalize import EmbyPeopleLocalize as _Cls  # noqa: E402

_PASS = 0
_FAIL = 0


def check(name, cond, detail=""):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  [PASS] {name}")
    else:
        _FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


def _fake_plugin(scan_sig="SIG-1"):
    """不带宿主 __init__ 的插件实例（只挂断点相关属性）。"""
    obj = object.__new__(_Cls)
    obj._scan_cursor = None
    obj._saved = 0
    obj._save_state = lambda: setattr(obj, "_saved", obj._saved + 1)
    obj._all_nfo_roots = lambda: ["X:/lib"]
    obj._nfo_recursive = True
    obj._nfo_include_episodes = False
    obj._nfo_scan_sig = lambda *a, **k: scan_sig
    return obj


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def test_sig_precision():
    """NFO-003：秒级 mtime + 同长度重写曾无法分辨 → 纳秒签名 + 旧格式兼容层。"""
    print("A) NFO-003 文件签名纳秒精度")
    d = tempfile.mkdtemp(prefix="sig_", dir=_TMP)
    fp = os.path.join(d, "a.nfo")
    _write(fp, "A" * 20)
    s1 = _Cls._file_sig(fp)
    time.sleep(0.02)
    _write(fp, "B" * 20)          # 同长度重写（旧实现只看秒级 mtime+size）
    s2 = _Cls._file_sig(fp)
    check("同长度重写后签名可分辨", s1 != s2, f"{s1} vs {s2}")
    try:
        _ns = int(str(s1).split("|")[0])
        check("签名使用纳秒段", _ns > 10 ** 15, str(_ns))
    except Exception as e:
        check("签名使用纳秒段", False, str(e))
    _o, _sz = s1.split("|")
    check("旧版秒级签名被识别为同一状态",
          _Cls._sig_legacy_same(f"{int(_o) // 1000000000}|{_sz}", s1))
    check("大小不一致 → 不视为同一状态",
          not _Cls._sig_legacy_same(f"{int(_o) // 1000000000}|{int(_sz) + 1}", s1))
    check("秒数不一致 → 不视为同一状态",
          not _Cls._sig_legacy_same(f"{int(_o) // 1000000000 - 5}|{_sz}", s1))
    check("空签名不参与等价判定",
          not _Cls._sig_legacy_same("", s1) and not _Cls._sig_legacy_same(s1, ""))


def test_done_skip():
    """NFO-001：断点命中必须比对「处理时的文件签名」，改动后要重新处理。"""
    print("B) NFO-001 断点命中判定")
    obj = _fake_plugin()
    d = tempfile.mkdtemp(prefix="done_", dir=_TMP)
    fp = os.path.join(d, "b.nfo")
    _write(fp, "X" * 10)
    done = {fp: _Cls._file_sig(fp)}
    check("签名一致 → 跳过", obj._nfo_done_skip(fp, done) is True)
    check("旧格式断点（无签名）→ 维持原跳过语义",
          obj._nfo_done_skip(fp, {fp: ""}) is True)
    check("文件不存在/读不到 → 跳过（无可处理内容）",
          obj._nfo_done_skip(os.path.join(d, "none.nfo"), {"x": "1"}) is True)
    time.sleep(0.02)
    _write(fp, "Y" * 10)
    check("断点后文件被改动 → 不跳过（重新处理）",
          obj._nfo_done_skip(fp, done) is False)


def test_cursor_roundtrip():
    """NFO-004：断点按处理顺序截断 + 新格式 {路径: 签名} 与旧格式兼容读取。"""
    print("C) NFO-004 断点持久化/续跑状态")
    obj = _fake_plugin()
    done = {f"X:/lib/{i}.nfo": f"{1700000000000000000 + i}|10" for i in range(60000)}
    obj._save_nfo_cursor("SIG-1", done)
    nfo = (obj._scan_cursor or {}).get("nfo") or {}
    got = nfo.get("done") or {}
    check("断点上限 50000 条", len(got) == 50000, str(len(got)))
    check("按处理顺序截断（保留最近处理的）",
          ("X:/lib/0.nfo" not in got) and ("X:/lib/59999.nfo" in got))
    check("断点为 {路径: 签名} 结构且签名保留",
          isinstance(got.get("X:/lib/59999.nfo"), str) and got.get("X:/lib/59999.nfo") != "")
    check("断点写入触发状态落盘", obj._saved >= 1)
    st = obj._nfo_resume_state()
    check("续跑状态可读（签名匹配+计数）",
          st.get("ok") is True and st.get("done") == 50000, str(st))
    obj._scan_cursor = {"nfo": {"sig": "SIG-1", "done": ["a.nfo", "b.nfo"]}}
    st2 = obj._nfo_resume_state()
    check("旧格式（纯路径列表）断点可读", st2.get("ok") is True and st2.get("done") == 2, str(st2))
    obj._scan_cursor = {"nfo": {"sig": "SIG-OTHER", "done": {"a.nfo": "1|1"}}}
    st3 = obj._nfo_resume_state()
    check("签名不匹配 → 断点不可续跑", st3.get("ok") is False and st3.get("done") == 1, str(st3))


def test_scan_worker_invariants():
    """NFO-002 不变量（源码级）：失败不得写入断点、失败要从签名表移除。"""
    print("D) NFO-002 入库失败不入断点（源码不变量）")
    src = open(os.path.join(_ROOT, "__init__.py"), encoding="utf-8").read()
    check("主循环：done 写入受 _db_ok 守卫",
          "if _db_ok:\n                    _done[fp] = _fp_sig" in src)
    check("主循环：失败时从签名表移除",
          "elif _write_sigs:\n                    # 本次处理失败：签名表也忘记它" in src)
    check("预览分支：except 后不再无条件 _done.add",
          "_done.add(" not in src)
    check("集解析失败会阻止父级计入断点", "_db_ok = False   # 集解析失败" in src)


if __name__ == "__main__":
    print(f"插件目录: {_ROOT}")
    print(f"临时目录: {_TMP}")
    test_sig_precision()
    test_done_skip()
    test_cursor_roundtrip()
    test_scan_worker_invariants()
    print(f"\n结果: {_PASS} 通过 / {_FAIL} 失败")
    sys.exit(1 if _FAIL else 0)