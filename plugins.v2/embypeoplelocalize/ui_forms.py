"""
ui_forms.py - Emby 演职人员中文化 页面布局
v0.9.0 重构版 - 简化事件绑定

设计方向：
- 极简、信息层级清晰
- 不使用白色底色卡片（宿主背景导致看不见），改用透明/ outlined 卡片
- 主色：深靛青 #4338ca；功能色：青绿 #0d9488、琥珀 #d97706、玫红 #e11d48
"""
from typing import Any, Dict, List
from app.core.config import settings


C_PRIMARY = "#4338ca"
C_SUCCESS = "#0d9488"
C_INFO = "#0891b2"
C_WARNING = "#d97706"
C_ERROR = "#e11d48"

CARD_BG = "rgba(255, 255, 255, 0.04)"
CARD_BORDER = "rgba(255, 255, 255, 0.10)"
CARD_SHADOW = "0 1px 3px rgba(0,0,0,0.20)"


def _row(content, classes="mb-3", justify="start", align="start"):
    return {"component": "VRow", "props": {"dense": True, "class": classes, "justify": justify, "align": align},
            "content": content}


def _col(cols, content, sm=None, md=None, lg=None):
    props = {"cols": cols}
    if sm: props["sm"] = sm
    if md: props["md"] = md
    if lg: props["lg"] = lg
    if isinstance(content, list):
        return {"component": "VCol", "props": props, "content": content}
    return {"component": "VCol", "props": props, "content": [content]}


def _section(title, accent, content_list):
    return {
        "component": "VCard",
        "props": {
            "class": "mb-4 rounded-lg",
            "variant": "outlined",
            "style": {
                "backgroundColor": CARD_BG,
                "border": f"1px solid {CARD_BORDER}",
                "borderLeft": f"4px solid {accent}",
                "boxShadow": CARD_SHADOW,
            },
        },
        "content": [
            {"component": "VCardTitle", "props": {"class": "text-subtitle-1 font-weight-bold d-flex align-center py-3 text-high-emphasis"},
             "text": title},
            {"component": "VDivider", "props": {"class": "mb-3", "style": {"opacity": 0.4}}},
            {"component": "VCardText", "props": {"class": "pt-0 pb-4"}, "content": content_list},
        ],
    }