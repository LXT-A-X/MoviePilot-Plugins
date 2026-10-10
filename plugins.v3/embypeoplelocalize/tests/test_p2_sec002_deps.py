# -*- coding: utf-8 -*-
"""P2 回归测试：SEC-002 依赖需要「经验证兼容区间」（含上限）+ constraints 锁 + CI。

对应整改文档：
  SEC-002：requirements.txt / package.json 依赖只有下限，openai/httpx 等大版本升级
          可能导致未测试的破坏。修复：锁定经验证的兼容区间（constraints/lock）
          + CI 编译与测试。
  回归（静态守卫，无需安装依赖）：
    1) requirements.txt 每条依赖都必须同时含下限(>=)与上限(<)；
    2) pyproject.toml 的 dependencies 与 requirements.txt 区间一致（都带上限）；
    3) constraints.txt 存在且覆盖全部依赖并带上限；
    4) CI 工作流存在，且包含 安装(constraints) + 编译 + 测试 + 前端构建。

运行：python tests/test_p2_sec002_deps.py
"""
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import test_p0_nfo_checkpoint as base   # noqa: E402

check = base.check

_PROJ = os.path.dirname(_HERE)
_REQ = os.path.join(_PROJ, "requirements.txt")
_PYPROJECT = os.path.join(_PROJ, "pyproject.toml")
_CONSTRAINTS = os.path.join(_PROJ, "constraints.txt")
_CI = os.path.join(_PROJ, ".github", "workflows", "ci.yml")

_EXPECTED = ["requests", "httpx", "PySocks", "zhconv", "openai"]


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _spec_for(name, text):
    """抓取某个依赖的完整版本区间字符串（含 extras）。"""
    pat = re.compile(
        r"(?im)^\s*['\"]?" + re.escape(name) + r"(\[[^\]]*\])?\s*(>=?[^'\"\n]+)?")
    m = pat.search(text)
    if not m:
        return None
    extras = m.group(1) or ""
    spec = (m.group(2) or "").strip()
    return extras + spec


def test_requirements_have_upper_bounds():
    print("A) requirements.txt：每条依赖含下限且必须有上限")
    txt = _read(_REQ)
    lines = [ln.strip() for ln in txt.splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    check("requirements.txt 非空", len(lines) >= 5, str(len(lines)))
    for ln in lines:
        check(f"依赖有上限: {ln}", "<" in ln, ln)
    for name in _EXPECTED:
        spec = _spec_for(name, txt)
        check(f"含依赖 {name}", spec is not None, str(spec))
        if spec is not None:
            check(f"{name} 有下限(>=)与上限(<)", ">=" in spec and "<" in spec, spec)


def test_pyproject_consistent():
    print("B) pyproject.toml：dependencies 与 requirements 区间一致（均带上限）")
    ptxt = _read(_PYPROJECT)
    for name in _EXPECTED:
        spec = _spec_for(name, ptxt)
        check(f"pyproject 含依赖 {name}", spec is not None, str(spec))
        if spec is not None:
            check(f"pyproject {name} 带上限", "<" in spec and ">=" in spec, spec)
    # 与 requirements.txt 对应项完全一致
    rtxt = _read(_REQ)
    for name in _EXPECTED:
        r = _spec_for(name, rtxt) or ""
        p = _spec_for(name, ptxt) or ""
        # pyproject 允许 httpx 带 extras，requirements 也带，字符串应可直接比较（去空格）
        check(f"{name} 两处区间一致",
              r.replace(" ", "") == p.replace(" ", ""), f"req={r!r} pyproject={p!r}")


def test_constraints_lock():
    print("C) constraints.txt：覆盖全部依赖且带上限（已验证区间锁）")
    check("constraints.txt 存在", os.path.isfile(_CONSTRAINTS), _CONSTRAINTS)
    if not os.path.isfile(_CONSTRAINTS):
        return
    ctxt = _read(_CONSTRAINTS)
    for name in _EXPECTED:
        spec = _spec_for(name, ctxt)
        check(f"constraints 含 {name}", spec is not None, str(spec))
        if spec is not None:
            check(f"constraints {name} 带上下限", ">=" in spec and "<" in spec, spec)
    # httpx 在 constraints 中应给出与代码相符的下限（proxy= 参数）
    hspec = _spec_for("httpx", ctxt) or ""
    check("constraints httpx 下限 >=0.26", "0.26" in hspec, hspec)


def test_ci_gate():
    print("D) CI：安装(constraints) + 编译 + 测试 + 前端构建")
    check("CI 工作流存在", os.path.isfile(_CI), _CI)
    if not os.path.isfile(_CI):
        return
    c = _read(_CI)
    check("CI 引用 constraints.txt", "constraints.txt" in c, "")
    check("CI 执行编译检查", "compileall" in c, "")
    check("CI 运行测试", "tests/test_" in c, "")
    check("CI 执行前端构建", "npm run build" in c, "")


if __name__ == "__main__":
    test_requirements_have_upper_bounds()
    test_pyproject_consistent()
    test_constraints_lock()
    test_ci_gate()
    print(f"\n结果: {base._PASS} 通过 / {base._FAIL} 失败")
    sys.exit(1 if base._FAIL else 0)
