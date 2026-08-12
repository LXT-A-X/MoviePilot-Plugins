"""
ui/logs.py - 实时日志 UI 组件
v1.2.9: 拆出 - 由前端通过 /live_log 轮询拉取
v1.3.0: 压缩日志高度 240px（小屏适配）；加 data-polling 属性让前端识别要拉 /live_log
"""
from typing import Any, Dict, List

from .common import _row, _col, _section, _icon, C_INFO, C_SUCCESS, C_WARNING, C_ERROR


# v1.3.0: 实时日志拉取配置
LIVE_LOG_API = "plugin/EmbyPeopleLocalize/live_log"
LIVE_LOG_INTERVAL_MS = 2000  # 2 秒拉一次
LOG_MAX_HEIGHT = 240  # v1.3.0: 320→240，小屏适配


# 前端组件期望通过 /api/plugin/EmbyPeopleLocalize/live_log 拉取
# 这里只提供"日志查看器"嵌入式组件的 schema，前端负责轮询渲染
LOG_VIEWER_SCHEMA = {
    "component": "VCard", "props": {"class": "mb-3 rounded-lg", "variant": "outlined",
                                    "style": {"backgroundColor": "rgba(255,255,255,0.04)",
                                              "border": "1px solid rgba(255,255,255,0.10)"}},
    "content": [
        {"component": "VCardTitle",
         "props": {"class": "text-subtitle-2 font-weight-bold py-2 px-3 text-high-emphasis d-flex align-center"},
         "content": [
             _icon("mdi-text-box-search-outline", color=C_INFO),
             {"component": "span", "text": "实时日志"},
             # v1.3.0: 用 chip 显示"自动刷新"状态
             {"component": "VChip",
              "props": {"color": C_SUCCESS, "size": "x-small", "variant": "tonal",
                        "class": "ml-2", "prepend_icon": "mdi-refresh"},
              "text": f"每 {LIVE_LOG_INTERVAL_MS // 1000}s 刷新"},
         ]},
        {"component": "VDivider", "props": {"style": {"opacity": 0.3}}},
        {"component": "VCardText",
         # v1.3.0: 320→240 - 小屏适配，不让日志区占太多空间
         "props": {"class": "px-3 py-2", "style": {"maxHeight": f"{LOG_MAX_HEIGHT}px", "overflowY": "auto"}},
         # v1.3.0: 加 data-* 属性让前端识别 - 拉哪个 API、用什么间隔
         "content": [
             {"component": "div",
              "props": {
                  "id": "live_log_container",
                  "class": "text-caption",
                  "style": {"fontFamily": "monospace", "whiteSpace": "pre-wrap"},
                  # 前端轮询配置
                  "data-api": LIVE_LOG_API,
                  "data-polling": LIVE_LOG_INTERVAL_MS,
                  "data-level-classes": '{"INFO":"text-medium-emphasis","OK":"text-success","WARNING":"text-warning","ERROR":"text-error"}',
              },
              "text": "（实时日志正在加载...）"}
         ]},
    ],
}


def build_log_section() -> dict:
    """v1.3.0: 返回实时日志 section schema，供 dashboard 嵌入"""
    return LOG_VIEWER_SCHEMA
