# -*- coding: utf-8 -*-
"""v3.2.1 回归测试：解压工具容错 / 一键安装 / GBK zip 文件名。"""
import zipfile
from pathlib import Path

import pytest

from ziti_under_test import archive_utils as au


class _R:
    def __init__(self, code, out="", err=""):
        self.returncode = code
        self.stdout = out
        self.stderr = err


def test_rar_candidates_exclude_7za(monkeypatch):
    """7za/7zr 是精简版 7-Zip，没有 Rar 解码器，不能当成 rar 能力。"""
    monkeypatch.setattr(
        au, "detect_extract_tools",
        lambda refresh=False: {"7z": "7z", "7za": "7za", "7zr": "7zr", "unar": "unar"},
    )
    assert [name for name, _ in au.rar_candidates()] == ["7z", "unar"]
    assert [name for name, _ in au.seven_zip_candidates()] == ["7z", "7za", "7zr", "unar"]


def test_extract_external_falls_back_when_first_tool_broken(monkeypatch, tmp_path):
    """第一个工具启动失败（如 0 字节应用别名/坏 exe）时，必须继续试下一个。"""
    src = tmp_path / "a.rar"
    src.write_bytes(b"Rar!\x1a\x07\x00fake")
    monkeypatch.setattr(au, "detect_extract_tools", lambda refresh=False: {"7z": "bad7z", "unar": "unar"})
    monkeypatch.setattr(au, "_precheck_with_7z", lambda *a, **k: None)

    def _fake_run(cmd, **kwargs):
        if str(cmd[0]) == "bad7z":
            raise OSError("[WinError 193] 不是有效的 Win32 应用程序")
        outdir = Path(cmd[cmd.index("-o") + 1])
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "a.ttf").write_bytes(b"AAAA")
        return _R(0)

    monkeypatch.setattr(au.subprocess, "run", _fake_run)
    result = au.extract_external(src, tmp_path / "out", (".ttf",))
    assert [Path(f.path).name for f in result.files] == ["a.ttf"]
    assert result.errors == []


def test_extract_external_accepts_7z_warning_exit_code(monkeypatch, tmp_path):
    """7-Zip 退出码 1 = 部分成员有警告但已解出文件，不能判整包失败。"""
    src = tmp_path / "a.7z"
    src.write_bytes(b"fake")
    monkeypatch.setattr(au, "detect_extract_tools", lambda refresh=False: {"7z": "7z"})
    monkeypatch.setattr(au, "_precheck_with_7z", lambda *a, **k: None)

    def _fake_run(cmd, **kwargs):
        outdir = Path(str(cmd[4])[2:])
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "a.ttf").write_bytes(b"AAAA")
        return _R(1, "", "WARNING: Cannot create symbolic link")

    monkeypatch.setattr(au.subprocess, "run", _fake_run)
    result = au.extract_external(src, tmp_path / "out", (".ttf",))
    assert [Path(f.path).name for f in result.files] == ["a.ttf"]


def test_extract_external_cleans_staging_on_all_failures(monkeypatch, tmp_path):
    src = tmp_path / "a.rar"
    src.write_bytes(b"fake")
    monkeypatch.setattr(au, "detect_extract_tools", lambda refresh=False: {"7z": "7z"})
    monkeypatch.setattr(au, "_precheck_with_7z", lambda *a, **k: None)
    monkeypatch.setattr(au, "_host_unpack", lambda *a, **k: "宿主不可用")
    monkeypatch.setattr(
        au.subprocess, "run",
        lambda cmd, **kw: _R(2, "", "ERROR: Can not open the file as archive"),
    )
    result = au.extract_external(src, tmp_path / "out", (".ttf",))
    assert result.files == []
    assert result.errors and "解压失败" in result.errors[0][1]
    assert not list((tmp_path / "out").glob(".extract_*"))


def test_zip_member_name_recovers_gbk():
    class _Info:
        flag_bits = 0
        filename = "字体.TTF".encode("gbk").decode("cp437")

    assert au._zip_member_name(_Info()) == "字体.TTF"


def test_install_extract_tools_without_package_manager(monkeypatch):
    monkeypatch.setattr(au.shutil, "which", lambda name: None)
    result = au.install_extract_tools()
    assert result["ok"] is False
    assert "apt-get/apk" in result["message"]


def test_install_extract_tools_success_simulated(monkeypatch):
    monkeypatch.setattr(
        au.shutil, "which",
        lambda name: "/usr/bin/apt-get" if name == "apt-get" else None,
    )
    monkeypatch.setattr(
        au, "_run_install_command",
        lambda *a, **k: {"cmd": " ".join(a[0]), "ok": True, "output": "ok"},
    )
    monkeypatch.setattr(au, "detect_extract_tools", lambda refresh=False: {"unar": "unar"})
    result = au.install_extract_tools()
    assert result["ok"] is True
    assert result["state"]["rar"] is True
