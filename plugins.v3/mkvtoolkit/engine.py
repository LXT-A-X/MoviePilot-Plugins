"""
外部引擎（MKVToolNix / ffmpeg）的探测、版本自检与安装。

插件不在加载时联网或安装任何东西：``detect()`` 只做本地只读探测，
安装动作必须由用户在页面上显式触发，并在后台线程执行、把日志回传给前端。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any, Callable, Optional

MKV_TOOLS = ("mkvmerge", "mkvpropedit", "mkvextract")
FF_TOOLS = ("ffmpeg", "ffprobe")

# 单独安装目标：每个引擎/压缩包工具都可以单独补装，不用整体重装
INSTALL_TARGETS = {
    "all", "mkvmerge", "mkvpropedit", "mkvextract", "ffmpeg", "ffprobe", "7z", "unrar",
}
# apt 包组合（apt 里 mkvtoolnix 一个包就包含三个工具，ffmpeg 包包含 ffmpeg/ffprobe）
APT_GROUPS: dict[str, list[list[str]]] = {
    "mkvmerge": [["mkvtoolnix"]],
    "mkvpropedit": [["mkvtoolnix"]],
    "mkvextract": [["mkvtoolnix"]],
    "ffmpeg": [["ffmpeg"]],
    "ffprobe": [["ffmpeg"]],
    "7z": [["p7zip-full", "7zip", "7zip-full"]],
    "unrar": [["unrar-free", "unrar"]],
    "all": [["mkvtoolnix"], ["p7zip-full", "7zip", "7zip-full"]],
}
TARGET_LABELS = {
    "all": "全部（MKVToolNix + 压缩包工具）",
    "mkvmerge": "mkvmerge",
    "mkvpropedit": "mkvpropedit",
    "mkvextract": "mkvextract",
    "ffmpeg": "ffmpeg",
    "ffprobe": "ffprobe",
    "7z": "7z（zip/7z/rar 解压）",
    "unrar": "unrar（rar 解压）",
}

# 官方 AppImage 固定版本（glibc >= 2.28 即可，官方镜像满足）
APPIMAGE_VERSION = "103.0"
APPIMAGE_URL = (
    "https://mkvtoolnix.download/appimage/"
    f"MKVToolNix_GUI-{APPIMAGE_VERSION}-x86_64.AppImage"
)

_VERSION_PATTERNS = {
    "mkvmerge": re.compile(r"v(\d+(?:\.\d+)*)"),
    "mkvpropedit": re.compile(r"v(\d+(?:\.\d+)*)"),
    "mkvextract": re.compile(r"v(\d+(?:\.\d+)*)"),
    "ffmpeg": re.compile(r"version\s+(\d+(?:\.\d+)*)"),
    "ffprobe": re.compile(r"version\s+(\d+(?:\.\d+)*)"),
}

_INSTALL_TIMEOUT = 900


class EngineManager:
    """
    引擎路径解析与安装状态机。

    :param data_dir: 插件数据目录
    :param log: 日志回调（接收一行文本）
    """

    def __init__(self, data_dir: Path, log: Optional[Callable[[str], None]] = None) -> None:
        self.data_dir = Path(data_dir)
        self.bin_dir = self.data_dir / "bin"
        self.bin_dir.mkdir(parents=True, exist_ok=True)
        self._log = log or (lambda _message: None)
        self._lock = threading.RLock()
        self._states: dict[str, dict[str, Any]] = {}
        self._install_running = False
        self._install_ok = False
        self._install_log: deque[str] = deque(maxlen=400)
        self._install_method = ""
        self._install_target = "all"

    # ------------------------------------------------------------------ 探测
    def detect(self, config: dict[str, Any], force: bool = False) -> dict[str, Any]:
        """
        探测所有引擎并返回状态。

        :param config: 插件配置（读取用户手填路径）
        :param force: 忽略缓存重新探测
        :return: ``{"mode": ..., "mkvmerge": {...}, ...}``
        """
        with self._lock:
            if self._states and not force:
                return self._snapshot()
            states: dict[str, dict[str, Any]] = {}
            for tool in MKV_TOOLS:
                states[tool] = self._detect_tool(tool, str(config.get(f"{tool}_path") or ""))
            for tool in FF_TOOLS:
                states[tool] = self._detect_tool(tool, str(config.get(f"{tool}_path") or ""))
            self._states = states
            return self._snapshot()

    def refresh(self, config: dict[str, Any]) -> dict[str, Any]:
        """强制重新探测。"""
        return self.detect(config, force=True)

    def _snapshot(self) -> dict[str, Any]:
        """返回探测结果的浅拷贝并附带引擎模式。"""
        data: dict[str, Any] = {tool: dict(state) for tool, state in self._states.items()}
        data["mode"] = self.mode()
        return data

    def mode(self) -> str:
        """
        计算当前可用的执行引擎。

        :return: ``mkvmerge``（完整能力） / ``ffmpeg``（降级） / ``none``
        """
        if self._ok("mkvmerge") and self._ok("mkvpropedit"):
            return "mkvmerge"
        if self._ok("ffmpeg") and self._ok("ffprobe"):
            return "ffmpeg"
        return "none"

    def _ok(self, tool: str) -> bool:
        """指定工具是否可用。"""
        return bool(self._states.get(tool, {}).get("ok"))

    def path_of(self, tool: str) -> Optional[str]:
        """指定工具的可用路径。"""
        state = self._states.get(tool) or {}
        return state.get("path") if state.get("ok") else None

    def _detect_tool(self, tool: str, configured: str) -> dict[str, Any]:
        """
        按「配置路径 → 数据目录 bin → PATH → /usr/bin」顺序查找并自检工具。

        :param tool: 工具名
        :param configured: 用户配置的绝对路径
        :return: ``{"path", "version", "ok"}``
        """
        candidates: list[Path] = []
        if configured:
            candidates.append(Path(configured).expanduser())
        candidates.append(self.bin_dir / tool)
        found = shutil.which(tool)
        if found:
            candidates.append(Path(found))
        candidates.append(Path("/usr/bin") / tool)
        candidates.append(Path("/usr/local/bin") / tool)
        for candidate in candidates:
            if not candidate.is_file() or not os.access(candidate, os.X_OK):
                continue
            version = self._probe(candidate, tool)
            if version:
                return {"path": str(candidate), "version": version, "ok": True}
        return {"path": "", "version": "", "ok": False}

    def _probe(self, path: Path, tool: str) -> str:
        """
        执行 ``--version`` 并解析版本号，失败返回空串。

        :param path: 可执行文件路径
        :param tool: 工具名
        :return: 版本号
        """
        try:
            result = subprocess.run(
                [str(path), "--version"],
                capture_output=True, text=True, timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        output = f"{result.stdout}\n{result.stderr}"
        match = _VERSION_PATTERNS.get(tool, re.compile(r"(\d+(?:\.\d+)*)")).search(output)
        return match.group(1) if match else ""

    # ------------------------------------------------------------------ 安装
    @property
    def install_state(self) -> dict[str, Any]:
        """安装进度快照，供 ``/status`` 返回。"""
        with self._lock:
            return {
                "running": self._install_running,
                "ok": self._install_ok,
                "method": self._install_method,
                "target": self._install_target,
                "log_tail": "\n".join(list(self._install_log)[-80:]),
            }

    def start_install(self, method: str, path: str = "", target: str = "all") -> dict[str, Any]:
        """
        启动后台安装线程。

        :param method: ``apt`` / ``appimage`` / ``path``
        :param path: ``path`` 模式下用户提供的二进制路径
        :param target: 单独安装目标（见 ``INSTALL_TARGETS``）
        :return: 启动结果
        :raises RuntimeError: 已有安装在执行或参数不合法
        """
        with self._lock:
            if self._install_running:
                raise RuntimeError("已有安装任务在执行")
            if method not in {"apt", "appimage", "path"}:
                raise RuntimeError(f"未知安装方式：{method}")
            if target not in INSTALL_TARGETS:
                raise RuntimeError(f"未知安装目标：{target}")
            if method in {"appimage", "path"} and target not in {"all", "mkvmerge", "mkvpropedit", "mkvextract"}:
                raise RuntimeError(f"{TARGET_LABELS.get(target, target)} 只能用 apt 安装")
            self._install_running = True
            self._install_ok = False
            self._install_method = method
            self._install_target = target
            self._install_log.clear()
        thread = threading.Thread(
            target=self._install_worker, args=(method, path, target),
            name="MkvToolkit-engine-install", daemon=True,
        )
        thread.start()
        return {"started": True, "method": method, "target": target}

    def _install_worker(self, method: str, path: str, target: str = "all") -> None:
        """安装线程主体。"""
        try:
            if method == "apt":
                self._install_apt(target)
            elif method == "appimage":
                self._install_appimage()
            else:
                self._install_manual(path)
            self._install_ok = self._install_state_ok(target)
        except Exception as error:  # noqa: BLE001 - 安装失败要回传给前端
            self._append_log(f"安装失败：{error}")
            self._install_ok = False
        finally:
            with self._lock:
                self._install_running = False

    @staticmethod
    def _archive_tool_ok() -> bool:
        """zip/7z/rar 解压工具是否可用。"""
        return bool(
            shutil.which("7z") or shutil.which("7zz") or shutil.which("7za")
            or shutil.which("unrar") or shutil.which("unrar-free")
        )

    def _install_state_ok(self, target: str = "all") -> bool:
        """安装完成后立即重探测，按目标判断是否成功。"""
        info = self.detect({}, force=True)
        if target == "all":
            return info.get("mode") != "none" and self._archive_tool_ok()
        if target in MKV_TOOLS or target in FF_TOOLS:
            return bool((info.get(target) or {}).get("ok"))
        if target == "7z":
            return bool(shutil.which("7z") or shutil.which("7zz") or shutil.which("7za"))
        if target == "unrar":
            return bool(shutil.which("unrar") or shutil.which("unrar-free"))
        return False

    def _append_log(self, line: str) -> None:
        """追加一行安装日志并转发给插件日志。"""
        text = str(line).rstrip()
        if not text:
            return
        with self._lock:
            self._install_log.append(text)
        self._log(text)

    def _run_stream(self, args: list[str], cwd: Optional[Path] = None) -> int:
        """
        执行命令并把输出逐行写入安装日志。

        :param args: 命令与参数
        :param cwd: 工作目录
        :return: 退出码
        """
        self._append_log("$ " + " ".join(args))
        env = dict(os.environ)
        env.setdefault("DEBIAN_FRONTEND", "noninteractive")
        process = subprocess.Popen(
            args, cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=env,
        )
        try:
            assert process.stdout is not None
            for line in process.stdout:
                self._append_log(line)
        finally:
            process.wait(timeout=_INSTALL_TIMEOUT)
        return process.returncode

    def _install_apt(self, target: str = "all") -> None:
        """Debian/Ubuntu 下用 apt 安装指定目标（需要 root）。"""
        if os.geteuid() != 0:
            raise RuntimeError(
                "当前容器不是 root，无法使用 apt 安装；请改用 AppImage 解包或手动指定路径"
            )
        update_code = self._run_stream(["apt-get", "update"])
        if update_code != 0:
            raise RuntimeError("apt-get update 失败，请检查容器网络或软件源")
        groups = APT_GROUPS.get(target) or APT_GROUPS["all"]
        for group in groups:
            installed = False
            for package in group:
                self._append_log(f"安装目标 {TARGET_LABELS.get(target, target)}：尝试 apt 包 {package}")
                code = self._run_stream([
                    "apt-get", "install", "-y", "--no-install-recommends", package,
                ])
                if code == 0:
                    installed = True
                    break
            if not installed:
                raise RuntimeError(
                    f"apt-get install {' / '.join(group)} 失败，请查看上方日志"
                )
        if target == "all":
            # unrar 只是 7z 之外的备选，装不上不影响整体结果（7z 也能解 rar）
            for package in ("unrar-free", "unrar"):
                try:
                    if self._run_stream([
                        "apt-get", "install", "-y", "--no-install-recommends", package,
                    ]) == 0:
                        break
                except Exception:  # noqa: BLE001 - 可选组件失败忽略
                    continue

    def _install_appimage(self) -> None:
        """下载官方 AppImage 并解包到插件数据目录（免 root）。"""
        work = self.data_dir / "appimage"
        work.mkdir(parents=True, exist_ok=True)
        target = work / f"MKVToolNix_GUI-{APPIMAGE_VERSION}-x86_64.AppImage"
        if not target.exists() or target.stat().st_size < 10 * 1024 * 1024:
            self._append_log(f"下载 {APPIMAGE_URL}")
            temp = target.with_suffix(".part")
            request = urllib.request.Request(
                APPIMAGE_URL, headers={"User-Agent": "Mozilla/5.0 MkvToolkit"},
            )
            with urllib.request.urlopen(request, timeout=60) as response, temp.open("wb") as handle:
                total = int(response.headers.get("Content-Length") or 0)
                written = 0
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    handle.write(chunk)
                    written += len(chunk)
                    if total:
                        percent = written * 100 // total
                        if percent % 10 == 0:
                            self._append_log(f"下载进度 {percent}%（{written // 1024 // 1024} MB）")
            os.replace(temp, target)
            target.chmod(0o755)
        extract_dir = work / "squashfs-root"
        if not extract_dir.exists():
            code = self._run_stream([str(target), "--appimage-extract"], cwd=work)
            if code != 0 or not extract_dir.exists():
                raise RuntimeError("AppImage 解包失败，可手动把二进制放进插件数据目录 bin/")
        self._write_wrappers(extract_dir)

    def _write_wrappers(self, extract_dir: Path) -> None:
        """为解包目录里的 CLI 工具生成带库路径的启动脚本。"""
        tools_dir = extract_dir / "usr" / "bin"
        lib_dir = extract_dir / "usr" / "lib"
        written: list[str] = []
        for tool in MKV_TOOLS:
            binary = tools_dir / tool
            if not binary.is_file():
                continue
            wrapper = self.bin_dir / tool
            wrapper.write_text(
                "#!/bin/sh\n"
                f'export LD_LIBRARY_PATH="{lib_dir}${{LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}}"\n'
                f'exec "{binary}" "$@"\n',
                encoding="utf-8",
            )
            wrapper.chmod(0o755)
            written.append(tool)
        if not written:
            raise RuntimeError("AppImage 中未找到 mkvmerge/mkvpropedit，解包产物不完整")
        self._append_log("已生成启动脚本：" + ", ".join(written))

    def _install_manual(self, path: str) -> None:
        """校验用户指定的 mkvmerge 路径，并在同目录补齐其余工具。"""
        candidate = Path(str(path or "")).expanduser()
        if not candidate.is_file():
            raise RuntimeError(f"文件不存在：{candidate}")
        version = self._probe(candidate, "mkvmerge")
        if not version:
            raise RuntimeError("该文件不是可用的 mkvmerge（--version 自检失败）")
        self._append_log(f"检测到 mkvmerge {version}：{candidate}")
        # 同目录下的其余工具复制/软链到数据目录 bin
        for tool in MKV_TOOLS:
            sibling = candidate.parent / tool
            if sibling.is_file():
                link = self.bin_dir / tool
                try:
                    if link.exists() or link.is_symlink():
                        link.unlink()
                    os.symlink(sibling, link)
                    self._append_log(f"已链接 {tool} → {sibling}")
                except OSError:
                    self._append_log(f"无法链接 {tool}，将直接使用 {sibling}")

    # ------------------------------------------------------------------ 诊断
    def diagnostics(self, config: dict[str, Any]) -> dict[str, Any]:
        """
        生成一份可展示的引擎诊断信息。

        :param config: 插件配置
        :return: 诊断结果
        """
        states = self.detect(config)
        return {
            "engine": states,
            "mode": states.get("mode"),
            "euid": os.geteuid(),
            "is_root": os.geteuid() == 0,
            "data_dir": str(self.data_dir),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
