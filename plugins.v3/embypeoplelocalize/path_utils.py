"""
路径工具（PathUtils）
====================
把原先散落在 `__init__.py` 的「纯路径归一化 / 段安全前缀匹配 / 根替换」收拢到一处。

设计原则（保守抽取，行为与原实现逐字一致）：
- 只做「移动」，不改语义；方法名、签名、返回值、修饰符（staticmethod/classmethod）全部保持原样。
- 通过 mixin 混入插件主类，`self._norm_nfo_roots(...)` / `self._apply_root_replace(...)`
  等调用点（含测试里的 `_fake_plugin()` 实例）无需改动。
- 本组方法不依赖实例状态，仅依赖 Python 标准库 `re`，因此可安全独立成模块。
"""
import re


class PathUtilsMixin:
    """NFO 根目录规范化与「段安全」路径前缀匹配/替换（纯函数，无实例状态）。"""

    @staticmethod
    def _norm_nfo_roots(raw) -> list:
        """规范化 NFO 根目录：兼容 字符串/列表/被打散的逐字符残值。输出为行列表。"""
        try:
            if raw is None:
                return []
            if isinstance(raw, str):
                text = raw
            elif isinstance(raw, (list, tuple)):
                raw_items = [str(x or "") for x in raw]
                if raw_items and all(len(x) == 1 for x in raw_items):
                    # 被打散成单字符列表（list("路径") 的产物的还原）
                    text = "".join(raw_items)
                else:
                    text = "\n".join(x for x in raw_items if x.strip())
            else:
                text = ""
            return [x.strip() for x in text.splitlines() if x.strip()]
        except Exception:
            return []

    # ============================================================
    # ============================================================
    @staticmethod
    def _norm_seg_path(path: str) -> str:
        """路径段安全归一化。
        统一分隔符（\\ → /）、折叠重复 /、去掉末尾 /（根除外）。
        仅用于「段级前缀」比较，避免 `/media` 误匹配 `/media2`。
        统一返回正斜杠（Python 在 Windows/Linux 均接受 / 分隔）。"""
        try:
            p = str(path or "").strip()
            if not p:
                return ""
            p = p.replace("\\", "/")
            while "//" in p:
                p = p.replace("//", "/")
            if len(p) > 1:
                p = p.rstrip("/")
            return p
        except Exception:
            return ""

    @staticmethod
    def _looks_windows_path(path: str) -> bool:
        """判断是否 Windows 风格路径（盘符 / 反斜杠）—— 段比较需大小写不敏感。"""
        try:
            s = str(path or "")
            return bool(re.match(r"^[A-Za-z]:", s)) or ("\\" in s)
        except Exception:
            return False

    @classmethod
    def _seg_prefix_match(cls, path: str, prefix: str) -> bool:
        """段安全前缀匹配。
        仅当 prefix 是 path 的完整路径段前缀（path == prefix，或 path 以 prefix + '/' 开头）才算命中。
        例：prefix='/media' 不匹配 '/media2/movie'，但匹配 '/media/movie'。"""
        p = cls._norm_seg_path(path)
        f = cls._norm_seg_path(prefix)
        if not p or not f:
            return False
        if cls._looks_windows_path(p) or cls._looks_windows_path(prefix):
            p = p.lower()
            f = f.lower()
        if p == f:
            return True
        return p.startswith(f.rstrip("/") + "/")

    @classmethod
    def _apply_root_replace(cls, path: str, replace_from: str, replace_to: str) -> str:
        """路径前缀替换（段安全）。

        - replace_from 非空且为 path 的完整路径段前缀 → 用 replace_to 替换该前缀
        - 未配置 replace_from（空）或 replace_to（空）→ 返回归一化后的原路径
        - 命中判断按完整路径段，避免 /media 误匹配 /media2
        - Windows 风格路径大小写不敏感（统一转小写比较，替换后仍保留原大小写尾部）
        """
        p = cls._norm_seg_path(path)
        if not p:
            return str(path or "")
        f = cls._norm_seg_path(replace_from)
        t = cls._norm_seg_path(replace_to)
        if not f or not t:
            return p
        if not cls._seg_prefix_match(p, f):
            return p
        if p == f:
            return t
        return t.rstrip("/") + p[len(f):]
