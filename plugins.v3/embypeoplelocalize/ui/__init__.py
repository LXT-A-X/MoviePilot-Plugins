"""
ui/__init__.py - UI 子包入口
v1.2.9: 拆出 ui_forms.py 为 ui/ 子包
- ui.common: 颜色常量 + 通用辅助
- ui.dashboard: 首页数据面板
- ui.progress: 扫描状态/4 步骤
- ui.settings: 设置页
- ui.logs: 实时日志

外部调用：
    from .ui import build_page, build_form
"""
from .dashboard import build_page
from .settings import build_form

__all__ = ["build_page", "build_form"]
