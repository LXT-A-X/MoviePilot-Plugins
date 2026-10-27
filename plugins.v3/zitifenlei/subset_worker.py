"""子集化工作进程：在独立进程中执行 uharfbuzz/fontTools 子集化。

为什么单独进程：uharfbuzz 是 C 扩展，病态字体可能触发段错误（Python 层
try/except 拦不住），放主进程会直接拖垮 MoviePilot。本进程与父进程只通过
stdin/stdout 单行 JSON 通信，崩溃只影响当前这条字幕。

协议（v1）：
  请求: {"v":1, "task":"subset_ass", "ass_path":..., "out_path":...,
         "plan":[{"font_name","file_path","face_index","codepoints"}],
         "warnings":[...]}
  响应: SubsetResult.to_dict() 的单行 JSON（以 stderr 之外的通道输出）

不导入插件 __init__.py（避免触发 MoviePilot 宿主 SDK），用包垫片直接加载
harfbuzz_engine，这与 tests/conftest.py 的加载方式一致。
"""

from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path
from typing import Any, Dict

PLUGIN_DIR = Path(__file__).resolve().parent
PACKAGE_NAME = "ziti_subset_worker_pkg"
# 子进程地址空间上限：容纳 128MB 字体解析的中间数据，同时挡住病态字体把内存打爆
MEMORY_LIMIT_BYTES = 2 * 1024 * 1024 * 1024
PROTOCOL_VERSION = 1


def _harden_process() -> None:
    """崩溃可诊断 + 内存封顶（Windows 无 resource，自动跳过）。"""
    try:
        import faulthandler

        faulthandler.enable(all_threads=True)
    except Exception:
        pass
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
    except Exception:
        pass
    for stream in (sys.stdin, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _load_engine():
    """以合成包加载引擎模块，绕开插件 __init__.py（宿主 SDK 依赖）。"""
    package = types.ModuleType(PACKAGE_NAME)
    package.__path__ = [str(PLUGIN_DIR)]
    sys.modules[PACKAGE_NAME] = package
    return importlib.import_module(f"{PACKAGE_NAME}.harfbuzz_engine")


def _emit(real_stdout: Any, payload: Dict[str, Any]) -> None:
    real_stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    real_stdout.flush()


def _execute(engine: Any, payload: Any) -> Dict[str, Any]:
    """执行一条任务，返回可直接回传的 JSON 字典（不抛异常）。"""
    if not isinstance(payload, dict) or payload.get("task") != "subset_ass":
        return {"v": PROTOCOL_VERSION, "success": False, "errors": ["不支持的任务类型"]}
    try:
        result = engine.subset_ass_with_plan(
            payload.get("ass_path") or "",
            payload.get("out_path") or "",
            payload.get("plan") or [],
            warnings=payload.get("warnings") or [],
        )
        data = result.to_dict()
    except Exception as err:
        data = {
            "success": False,
            "out_path": "",
            "embedded": [],
            "missing_fonts": [],
            "errors": [f"子集化执行异常: {err}"],
            "warnings": [],
        }
    data["v"] = PROTOCOL_VERSION
    return data


def _serve(engine: Any, real_stdout: Any) -> int:
    """常驻模式：逐行读请求、逐行回响应，直到 EOF 或收到 shutdown 帧。"""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request_id = None
        try:
            payload = json.loads(line)
        except Exception as err:
            _emit(
                real_stdout,
                {
                    "v": PROTOCOL_VERSION,
                    "id": None,
                    "success": False,
                    "errors": [f"任务 JSON 解析失败: {err}"],
                },
            )
            continue
        if isinstance(payload, dict):
            request_id = payload.get("id")
            if payload.get("task") == "shutdown":
                break
        data = _execute(engine, payload)
        data["id"] = request_id
        _emit(real_stdout, data)
    return 0


def _oneshot(engine: Any, real_stdout: Any) -> int:
    """单次模式（脚本直调/调试）：读整个 stdin，回一条响应。"""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception as err:
        _emit(
            real_stdout,
            {
                "v": PROTOCOL_VERSION,
                "success": False,
                "errors": [f"任务 JSON 解析失败: {err}"],
            },
        )
        return 0
    data = _execute(engine, payload)
    if isinstance(payload, dict) and "id" in payload:
        data["id"] = payload.get("id")
    _emit(real_stdout, data)
    return 0


def main() -> int:
    real_stdout = sys.stdout
    # 协议独占 stdout：引擎/第三方库若意外 print，一律落到 stderr，避免污染 JSON
    sys.stdout = sys.stderr
    _harden_process()
    server = "--server" in sys.argv[1:]
    try:
        engine = _load_engine()
    except Exception as err:
        _emit(
            real_stdout,
            {
                "v": PROTOCOL_VERSION,
                "id": None,
                "success": False,
                "out_path": "",
                "embedded": [],
                "missing_fonts": [],
                "errors": [f"工作进程加载子集化引擎失败: {err}"],
                "warnings": [],
            },
        )
        return 0
    if server:
        return _serve(engine, real_stdout)
    return _oneshot(engine, real_stdout)


if __name__ == "__main__":
    # 正常失败一律 exit 0（错误走 JSON）；只有真正崩溃才会出现非 0，供父进程识别
    main()
