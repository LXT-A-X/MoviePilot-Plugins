"""
ui/progress.py - 扫描状态/进度 UI
v1.2.9: 拆出 - 处理 状态条 + 进度 + 4 步骤详情
"""
from typing import Dict, Any

from .common import (
    _row, _col, _icon, C_INFO, C_SUCCESS, C_WARNING, C_PRIMARY,
    CARD_BG, CARD_BORDER, CARD_SHADOW,
)


def build_status_bar(scan_status: Dict[str, Any], plugin=None) -> list:
    """v1.2.9: 状态条 - 含扫描进度 + 4 步骤详情 + 耗时

    scan_status: 由 plugin._build_scan_status() 返回的统一状态对象
    返回状态卡片的 content 列表（不含外层 VCard，由 dashboard 包裹）
    """
    is_running = scan_status.get("running", False)
    is_paused = scan_status.get("paused", False)
    last_run = scan_status.get("last_run_time")
    total = scan_status.get("total", 0)
    done = scan_status.get("done", 0)
    pct = scan_status.get("percent", 0)
    current_title = scan_status.get("current_title", "")
    current_library = scan_status.get("current_library", "")
    current_step = scan_status.get("current_step", "")
    step_status = scan_status.get("step_status", {}) or {}
    elapsed = scan_status.get("elapsed_seconds", 0)

    # 状态文字 / 颜色 / 图标
    if is_running:
        status_text = "正在扫描中..."
        status_color = C_INFO
        status_icon = "mdi-refresh"
    elif is_paused:
        status_text = "已暂停"
        status_color = C_WARNING
        status_icon = "mdi-pause-circle"
    elif last_run:
        from datetime import datetime
        lt = datetime.fromtimestamp(last_run).strftime("%m-%d %H:%M")
        status_text = f"上次运行：{lt}"
        status_color = C_SUCCESS
        status_icon = "mdi-check-circle"
    else:
        status_text = "尚未运行"
        status_color = "grey"
        status_icon = "mdi-minus-circle"

    content = [{"component": "VCardText", "props": {"class": "py-2 px-4 d-flex align-center"},
                "content": [
                    _icon(status_icon, color=status_color),
                    {"component": "span",
                     "props": {"class": "text-body-2 font-weight-medium text-high-emphasis"},
                     "text": status_text},
                ]}]

    # 进度条
    if is_running and total > 0:
        content.append({"component": "VCardText", "props": {"class": "px-4 pb-3"}, "content": [
            {"component": "div", "props": {"class": "d-flex align-center mb-2"}, "content": [
                {"component": "span", "props": {"class": "text-caption text-medium-emphasis flex-grow-1"},
                 "text": f"当前：{current_title or '准备中...'}"},
                {"component": "span", "props": {"class": "text-caption font-weight-bold", "style": {"color": C_INFO}},
                 "text": f"{done}/{total}  ({pct}%)"},
            ]},
            # v1.2.9: 进度条加渐变 - 蓝紫渐变营造科技感
            {"component": "VProgressLinear",
             "props": {"model": pct, "color": C_PRIMARY, "bg_color": C_INFO,
                       "buffer_value": 100, "density": "compact",
                       "rounded": True, "height": 6, "class": "mb-1",
                       "style": {"background": "rgba(8,145,178,0.15)"}}},
            {"component": "span", "props": {"class": "text-caption text-medium-emphasis"},
             "text": current_library or ""},
        ]})

    # 4 步骤详情 - v1.3.0: 改为只要 running 就显示，step_status 已由 init_plugin 默认初始化为 4 步骤 ○
    if is_running:
        # v1.3.2: 防御性兜底 - plugin 可能为 None（dashboard 未传参时）
        step_pending = getattr(plugin, "STEP_PENDING", "○") if plugin else "○"
        step_active = getattr(plugin, "STEP_ACTIVE", "●") if plugin else "●"
        step_done = getattr(plugin, "STEP_DONE", "✓") if plugin else "✓"
        # v1.3.2: STEP_NAMES 兜底 - 即便 plugin=None 也不崩
        default_steps = ("获取Emby", "提取演员", "AI翻译", "写回")
        step_names = getattr(plugin, "STEP_NAMES", default_steps) if plugin else default_steps
        step_color_map = {"✓": C_SUCCESS, "●": C_INFO, "○": "grey", "—": "grey"}
        step_rows = []
        # 使用插件类声明的标准步骤名，避免字典缺失时漏显
        for step_name in step_names:
            sym = step_status.get(step_name, step_pending)
            color = step_color_map.get(sym, "grey")
            is_current = (step_name == current_step and sym == step_active)
            step_rows.append({
                "component": "div", "props": {"class": "d-flex align-center mb-1"}, "content": [
                    {"component": "span", "props": {
                        "class": "mr-2",
                        "style": {"color": color, "fontWeight": "bold",
                                  "fontSize": "14px", "minWidth": "12px"}},
                     "text": sym},
                    {"component": "span", "props": {
                        "class": "text-caption",
                        "style": {"color": C_INFO if is_current else "inherit",
                                  "fontWeight": "bold" if is_current else "normal"}},
                     "text": step_name},
                ]
            })
        step_rows.append({"component": "div", "props": {"class": "mt-1 text-caption text-medium-emphasis"},
                          "text": f"耗时：{elapsed}秒"})

        content.append({
            "component": "VCardText", "props": {"class": "px-4 pb-3 pt-0"}, "content": [
                {"component": "div",
                 "props": {"class": "rounded pa-2",
                           "style": {"backgroundColor": "rgba(0,0,0,0.04)",
                                     "border": "1px solid rgba(0,0,0,0.08)"}},
                 "content": step_rows},
            ]
        })

        # v1.3.2: 在状态条内提供停止扫描按钮 - 第一页面就能直接停
        stop_btn = {
            "component": "VBtn",
            "props": {
                "color": "error", "variant": "tonal", "rounded": "lg",
                "prepend_icon": "mdi-stop-circle",
                "class": "text-none mt-2",
                "block": True,
            },
            "text": "⏹ 停止扫描",
            "events": {"click": {"api": "plugin/EmbyPeopleLocalize/stop", "method": "POST"}},
        }
        content.append({
            "component": "VCardText", "props": {"class": "px-4 pt-0 pb-3"}, "content": [stop_btn]
        })

    return content
