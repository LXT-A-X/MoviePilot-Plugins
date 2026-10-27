"""进程隔离子集化：共享入口 subset_ass_with_plan + subset_worker 协议回归。"""

import importlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from ziti_under_test import font_metadata as fm
from ziti_under_test import harfbuzz_engine as he
from ziti_under_test.db import FontDB
from ziti_under_test.subset_worker_client import (
    SubsetWorkerCrashed,
    SubsetWorkerTimeout,
)

FONT_DIR = Path(r"C:\Windows\Fonts")
ARIAL = FONT_DIR / "arial.ttf"
MSYH = FONT_DIR / "msyh.ttc"
FIXTURE = Path(__file__).parent / "fixtures" / "complex.ass"
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
WORKER = PLUGIN_ROOT / "subset_worker.py"

plugin_mod = importlib.import_module("ziti_under_test.__init__")

pytestmark = pytest.mark.skipif(
    not (ARIAL.is_file() and he.hb_available()[0]), reason="需要 Windows 字体与 uharfbuzz"
)

ASS_TEXT = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Style: Default,Arial,52,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,1,2,30,30,30,1

[Events]
Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,AB
"""


def _payload(tmp_path: Path) -> dict:
    src = tmp_path / "ep.ass"
    src.write_text(ASS_TEXT, encoding="utf-8")
    return {
        "v": 1,
        "task": "subset_ass",
        "ass_path": str(src),
        "out_path": str(tmp_path / "ep.ziti.ass"),
        "plan": [
            {
                "font_name": "Arial",
                "file_path": str(ARIAL),
                "face_index": 0,
                "codepoints": [ord("A"), ord("B")],
            }
        ],
        "warnings": ["来源：进度隔离测试"],
    }


def test_subset_ass_with_plan_writes_and_validates(tmp_path):
    payload = _payload(tmp_path)
    result = he.subset_ass_with_plan(
        payload["ass_path"], payload["out_path"], payload["plan"], warnings=payload["warnings"]
    )
    assert result.success, result.errors
    out = Path(result.out_path)
    assert out.is_file()
    assert result.warnings == ["来源：进度隔离测试"]
    assert [item.font_name for item in result.embedded] == ["Arial"]
    assert result.embedded[0].required == 2
    embedded = dict(he.extract_embedded_fonts(out.read_bytes()))
    assert "Arial" in embedded
    # 原字幕不变
    assert Path(payload["ass_path"]).read_text(encoding="utf-8") == ASS_TEXT


def test_subset_ass_with_plan_reports_bad_font_path(tmp_path):
    payload = _payload(tmp_path)
    payload["plan"][0]["file_path"] = str(tmp_path / "no-such-font.ttf")
    result = he.subset_ass_with_plan(
        payload["ass_path"], payload["out_path"], payload["plan"]
    )
    assert result.success is False
    assert any("字体「Arial」" in err for err in result.errors), result.errors
    assert not Path(payload["out_path"]).exists()


def _run_worker(payload: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(WORKER)],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        cwd=str(PLUGIN_ROOT),
        env=env,
    )


def test_worker_protocol_roundtrip(tmp_path):
    payload = _payload(tmp_path)
    proc = _run_worker(json.dumps(payload, ensure_ascii=False))
    assert proc.returncode == 0, proc.stderr
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, proc.stdout
    data = json.loads(lines[0])
    assert data["v"] == 1
    assert data["success"] is True, data.get("errors")
    assert data["out_path"] == payload["out_path"]
    assert [item["font_name"] for item in data["embedded"]] == ["Arial"]
    assert Path(payload["out_path"]).is_file()


def test_worker_rejects_unknown_task_and_bad_json(tmp_path):
    proc = _run_worker(json.dumps({"v": 1, "task": "other"}))
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout.strip())
    assert data["success"] is False
    assert data["errors"] == ["不支持的任务类型"]

    proc = _run_worker("{not-json")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout.strip())
    assert data["success"] is False
    assert any("JSON" in err for err in data["errors"])


def test_worker_reports_failure_without_crashing(tmp_path):
    payload = _payload(tmp_path)
    payload["plan"][0]["file_path"] = str(tmp_path / "missing.ttf")
    proc = _run_worker(json.dumps(payload, ensure_ascii=False))
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout.strip())
    assert data["success"] is False
    assert any("字体「Arial」" in err for err in data["errors"])
    assert not Path(payload["out_path"]).exists()


@pytest.mark.skipif(not MSYH.exists(), reason="需要 Windows 微软雅黑字体")
def test_worker_server_mode_serves_multiple_requests(tmp_path):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.Popen(
        [sys.executable, str(WORKER), "--server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
        cwd=str(PLUGIN_ROOT),
        env=env,
    )
    try:
        base = _payload(tmp_path)
        for idx in (1, 2):
            req = dict(base)
            req["id"] = idx
            req["out_path"] = str(tmp_path / f"ep{idx}.ziti.ass")
            proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
            proc.stdin.flush()
            data = json.loads(proc.stdout.readline())
            assert data["id"] == idx
            assert data["success"] is True, data.get("errors")
            assert Path(req["out_path"]).is_file()
        proc.stdin.write(json.dumps({"id": 0, "task": "shutdown"}) + "\n")
        proc.stdin.flush()
        assert proc.wait(timeout=30) == 0
    finally:
        if proc.poll() is None:
            proc.kill()


# ─── 父进程接入：隔离执行 / 崩溃 / 超时 / 降级 ───────────────────────────


def _make_lib(tmp_path: Path) -> Path:
    lib = tmp_path / "lib"
    lib.mkdir()
    for src in (ARIAL, MSYH):
        dst = lib / src.name
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)
    return lib


def _plugin_with_index(tmp_path: Path):
    lib = _make_lib(tmp_path)
    db = FontDB(tmp_path / "ziti.db")
    for item in sorted(lib.iterdir()):
        if item.is_file():
            db.upsert_font_file(fm.inspect_font(item))
    plugin = plugin_mod.Zitifenlei()
    plugin._db = db
    plugin._enabled = True
    plugin._config.update(
        {"lib_dir": str(lib), "subset_process_isolation": True}
    )
    plugin._tmp_dir = tmp_path / "tmp"
    plugin._tmp_dir.mkdir(exist_ok=True)
    src = tmp_path / "ep.ass"
    src.write_text(
        he.strip_fonts_section(FIXTURE.read_text(encoding="utf-8")).replace(
            "NoSuchFont", "Microsoft YaHei"
        ),
        encoding="utf-8",
    )
    return plugin, db, src, tmp_path / "ep.ziti.ass"


@pytest.mark.skipif(not MSYH.exists(), reason="需要 Windows 微软雅黑字体")
def test_subset_with_hb_runs_in_worker_and_succeeds(tmp_path):
    plugin, db, src, out = _plugin_with_index(tmp_path)
    try:
        result = plugin._subset_with_hb(src, out)
        assert result["status"] == "success", result
        assert Path(result["out"]) == out
        assert out.is_file()
        embedded = dict(he.extract_embedded_fonts(out.read_bytes()))
        assert {"Arial", "Microsoft YaHei"} <= set(embedded)
    finally:
        db.close()


@pytest.mark.skipif(not MSYH.exists(), reason="需要 Windows 微软雅黑字体")
def test_subset_with_hb_worker_crash_isolated(tmp_path, monkeypatch):
    plugin, db, src, out = _plugin_with_index(tmp_path)
    client = plugin._get_subset_worker()
    assert client is not None

    def _crash(payload, timeout):
        raise SubsetWorkerCrashed("工作进程已退出（exit=3）: Segmentation fault (core dumped)")

    monkeypatch.setattr(client, "request", _crash)
    out.write_text("OLD-PRODUCT", encoding="utf-8")
    try:
        result = plugin._subset_with_hb(src, out)
        assert result["status"] == "error", result
        assert "已隔离" in result["reason"]
        # 旧成品必须保持不动（进程崩溃不会产生半成品）
        assert out.read_text(encoding="utf-8") == "OLD-PRODUCT"
    finally:
        plugin._close_subset_worker()
        db.close()


@pytest.mark.skipif(not MSYH.exists(), reason="需要 Windows 微软雅黑字体")
def test_subset_with_hb_worker_timeout_isolated(tmp_path, monkeypatch):
    plugin, db, src, out = _plugin_with_index(tmp_path)
    client = plugin._get_subset_worker()
    assert client is not None

    def _timeout(payload, timeout):
        raise SubsetWorkerTimeout("请求超时（1 秒），工作进程已终止")

    monkeypatch.setattr(client, "request", _timeout)
    stale = tmp_path / f".{out.name}.stale.tmp"
    stale.write_text("half-written", encoding="utf-8")
    try:
        result = plugin._subset_with_hb(src, out)
        assert result["status"] == "error", result
        assert "超时" in result["reason"]
        assert not out.exists()
        # 被杀进程留下的临时文件一并清理
        assert not stale.exists()
    finally:
        plugin._close_subset_worker()
        db.close()


@pytest.mark.skipif(not MSYH.exists(), reason="需要 Windows 微软雅黑字体")
def test_subset_with_hb_worker_unavailable_fails_when_isolated(tmp_path, monkeypatch):
    """隔离开启时工作进程起不来：直接报错，且绝不在主进程内调用 HarfBuzz。"""
    plugin, db, src, out = _plugin_with_index(tmp_path)
    monkeypatch.setattr(plugin, "_get_subset_worker", lambda: None)

    def _must_not_call(*args, **kwargs):
        raise AssertionError("隔离开启时不得回退主进程执行 HarfBuzz 子集化")

    monkeypatch.setattr(plugin_mod, "hb_subset_ass_file", _must_not_call)
    try:
        result = plugin._subset_with_hb(src, out)
        assert result["status"] == "error", result
        assert "工作进程无法启动" in result["reason"]
        assert not out.exists()
    finally:
        db.close()


@pytest.mark.skipif(not MSYH.exists(), reason="需要 Windows 微软雅黑字体")
def test_subset_with_hb_worker_unavailable_falls_back_when_isolation_off(tmp_path, monkeypatch):
    """显式关闭隔离：工作进程不可用时允许进程内执行（功能不降级）。"""
    plugin, db, src, out = _plugin_with_index(tmp_path)
    plugin._config["subset_process_isolation"] = False
    monkeypatch.setattr(plugin, "_get_subset_worker", lambda: None)
    try:
        result = plugin._subset_with_hb(src, out)
        assert result["status"] == "success", result
        assert out.is_file()
    finally:
        db.close()


@pytest.mark.skipif(not MSYH.exists(), reason="需要 Windows 微软雅黑字体")
def test_subset_with_hb_isolation_disabled_runs_in_process(tmp_path, monkeypatch):
    plugin, db, src, out = _plugin_with_index(tmp_path)
    plugin._config["subset_process_isolation"] = False

    def _must_not_call(*args, **kwargs):
        raise AssertionError("隔离关闭时不应启动工作进程")

    monkeypatch.setattr(plugin, "_subset_via_worker", _must_not_call)
    try:
        result = plugin._subset_with_hb(src, out)
        assert result["status"] == "success", result
        assert out.is_file()
    finally:
        db.close()


@pytest.mark.skipif(not MSYH.exists(), reason="需要 Windows 微软雅黑字体")
def test_worker_process_reused_across_requests(tmp_path):
    """常驻进程：连续两条字幕复用同一个工作进程（不重复启动）。"""
    plugin, db, src, out = _plugin_with_index(tmp_path)
    try:
        first = plugin._subset_with_hb(src, out)
        assert first["status"] == "success", first
        client = plugin._subset_worker
        assert client is not None and client.alive
        pid = client.pid
        assert pid

        second = plugin._subset_with_hb(src, tmp_path / "ep2.ziti.ass")
        assert second["status"] == "success", second
        assert plugin._subset_worker is client
        assert client.pid == pid
        assert client.alive
    finally:
        plugin._close_subset_worker()
        db.close()


@pytest.mark.skipif(not MSYH.exists(), reason="需要 Windows 微软雅黑字体")
def test_worker_auto_restarts_after_crash(tmp_path):
    """工作进程被杀（模拟段错误）后，下一条字幕自动重启并成功。"""
    plugin, db, src, out = _plugin_with_index(tmp_path)
    try:
        assert plugin._subset_with_hb(src, out)["status"] == "success"
        client = plugin._subset_worker
        assert client is not None
        old_pid = client.pid
        assert old_pid
        client._proc.kill()
        client._proc.wait(timeout=10)

        again = plugin._subset_with_hb(src, tmp_path / "ep2.ziti.ass")
        assert again["status"] == "success", again
        assert plugin._subset_worker is client
        assert client.pid and client.pid != old_pid
    finally:
        plugin._close_subset_worker()
        db.close()


@pytest.mark.skipif(not MSYH.exists(), reason="需要 Windows 微软雅黑字体")
def test_close_subset_worker_releases_process(tmp_path):
    plugin, db, src, out = _plugin_with_index(tmp_path)
    try:
        assert plugin._subset_with_hb(src, out)["status"] == "success"
        client = plugin._subset_worker
        assert client is not None and client.alive
        plugin._close_subset_worker()
        assert plugin._subset_worker is None
        assert not client.alive
    finally:
        db.close()


@pytest.mark.skipif(not MSYH.exists(), reason="需要 Windows 微软雅黑字体")
def test_worker_reclaimed_when_idle(tmp_path, monkeypatch):
    """空闲超过 TTL：工作进程自动退出，下一条字幕再按需重启。"""
    from ziti_under_test.subset_worker_client import SubsetWorkerClient

    monkeypatch.setattr(SubsetWorkerClient, "IDLE_TTL_SECONDS", 0.2)
    plugin, db, src, out = _plugin_with_index(tmp_path)
    try:
        assert plugin._subset_with_hb(src, out)["status"] == "success"
        client = plugin._subset_worker
        assert client is not None and client.alive
        old_pid = client.pid
        assert old_pid
        deadline = time.time() + 10
        while client.pid is not None and time.time() < deadline:
            time.sleep(0.05)
        assert client.pid is None, "空闲超时后工作进程应被回收"

        again = plugin._subset_with_hb(src, tmp_path / "ep2.ziti.ass")
        assert again["status"] == "success", again
        assert client.pid and client.pid != old_pid
    finally:
        plugin._close_subset_worker()
        db.close()
