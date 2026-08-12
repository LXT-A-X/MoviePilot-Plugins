"""
ui/common.py - 通用颜色常量、布局辅助函数
v1.2.9: 从原 ui_forms.py 拆出，供 dashboard / progress / settings 复用
"""
from typing import Any, Dict, List

# ────────── 颜色常量 ──────────
# 主色：深靛青；功能色：青绿/琥珀/玫红
# 在 MoviePilot 深色背景下用透明/ outlined 卡片，避免白底
C_PRIMARY = "#4338ca"
C_SUCCESS = "#0d9488"
C_INFO = "#0891b2"
C_WARNING = "#d97706"
C_ERROR = "#e11d48"

CARD_BG = "rgba(255, 255, 255, 0.04)"
CARD_BORDER = "rgba(255, 255, 255, 0.10)"
CARD_SHADOW = "0 1px 3px rgba(0,0,0,0.20)"

# 渐变色（v1.2.9: 扫描状态科技感渐变）
GRADIENT_SCAN = "linear-gradient(90deg, #4338ca 0%, #0891b2 100%)"


# ────────── 布局辅助 ──────────
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


def _section(title, accent, content_list, icon: str = ""):
    """带 accent 左边框的卡片区块
    v1.2.9: 增加 icon 支持，标题前加 icon 视觉标识
    """
    title_content = []
    if icon:
        title_content.append({"component": "VIcon", "props": {"color": accent, "size": "small", "class": "mr-2"},
                              "text": icon})
    title_content.append({"component": "span", "props": {"class": "text-subtitle-1 font-weight-bold text-high-emphasis"},
                          "text": title})
    return {
        "component": "VCard",
        "props": {
            "class": "mb-3 rounded-lg",
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
             "content": title_content},
            {"component": "VDivider", "props": {"class": "mb-3", "style": {"opacity": 0.4}}},
            {"component": "VCardText", "props": {"class": "pt-0 pb-3"}, "content": content_list},
        ],
    }


def _stat_card(label, value, accent, icon: str = ""):
    """v1.2.9: 字体升级 - 数字 text-h4 一眼可见，加 icon"""
    content = [
        {"component": "div", "props": {"class": "d-flex align-center mb-1"}, "content": [
            {"component": "VIcon", "props": {"color": accent, "size": "small", "class": "mr-1"}, "text": icon} if icon else None,
            {"component": "span", "props": {"class": "text-caption text-medium-emphasis"}, "text": label},
        ]}
    ]
    # 清理 None
    content[0]["content"] = [c for c in content[0]["content"] if c]
    content.append({"component": "div", "props": {"class": "text-h4 font-weight-bold text-high-emphasis"},
                    "text": str(value)})
    return {
        "component": "VCard",
        "props": {"class": "rounded-lg h-100", "variant": "outlined",
                  "style": {"backgroundColor": CARD_BG, "border": f"1px solid {CARD_BORDER}",
                            "borderLeft": f"3px solid {accent}", "boxShadow": CARD_SHADOW}},
        "content": [{"component": "VCardText", "props": {"class": "py-3 px-3 d-flex flex-column justify-center"},
                     "content": content}],
    }


def _switch(key, label, hint="", disabled=False):
    item = {"component": "VSwitch", "props": {"model": key, "label": label, "color": "primary",
                                              "density": "compact", "class": "mb-0", "disabled": disabled}}
    if hint:
        return {"component": "div", "props": {"class": "w-100"}, "content": [
            item,
            {"component": "div", "props": {"class": "text-caption text-medium-emphasis ml-4 mb-1"}, "text": hint},
        ]}
    return item


def _text_field(key, label, placeholder="", hint="", input_type="text"):
    props = {"model": key, "label": label, "placeholder": placeholder, "density": "compact",
             "variant": "outlined", "class": "mb-1",
             "style": {"--v-field-border-opacity": "0.65", "--v-field-border-width": "1px"}}
    if input_type == "number": props["type"] = "number"
    elif input_type == "password": props["type"] = "password"
    field = {"component": "VTextField", "props": props}
    if hint:
        return {"component": "div", "props": {"class": "w-100"}, "content": [
            field,
            {"component": "div", "props": {"class": "text-caption text-medium-emphasis ml-1 mb-2"}, "text": hint},
        ]}
    return field


def _select(key, label, items, hint=""):
    props = {"model": key, "label": label, "items": items, "density": "compact", "variant": "outlined",
             "multiple": True, "chips": True, "deletable_chips": True, "class": "mb-1",
             "style": {"--v-field-border-opacity": "0.65", "--v-field-border-width": "1px"}}
    field = {"component": "VSelect", "props": props}
    if hint:
        return {"component": "div", "props": {"class": "w-100"}, "content": [
            field,
            {"component": "div", "props": {"class": "text-caption text-medium-emphasis ml-1 mb-2"}, "text": hint},
        ]}
    return field


def _textarea(key, label, placeholder="", hint="", rows=8):
    props = {"model": key, "label": label, "placeholder": placeholder, "density": "compact",
             "variant": "outlined", "rows": rows, "auto_grow": True, "class": "mb-1",
             "style": {"--v-field-border-opacity": "0.65", "--v-field-border-width": "1px"}}
    field = {"component": "VTextarea", "props": props}
    if hint:
        return {"component": "div", "props": {"class": "w-100"}, "content": [
            field,
            {"component": "div", "props": {"class": "text-caption text-medium-emphasis ml-1 mb-2"}, "text": hint},
        ]}
    return field


def _btn(text, color, api_path, method="POST", variant="elevated", block=True, icon: str = ""):
    """v1.2.9: 按钮三级 - elevated(主) / outlined(普通) / tonal(危险)"""
    props = {"color": color, "block": block, "variant": variant, "rounded": "lg", "type": "button"}
    if not block:
        props["class"] = "text-none"
    if icon:
        props["prepend_icon"] = icon
    return {"component": "VBtn", "props": props, "text": text,
            "events": {"click": {"api": api_path, "method": method}}}


def _chip(text, color, icon: str = ""):
    props = {"color": color, "size": "small", "variant": "tonal",
             "class": "font-weight-medium"}
    if icon:
        props["prepend_icon"] = icon
    return {"component": "VChip", "props": props, "text": text}


def _alert(text, alert_type="warning", icon: str = ""):
    props = {"type": alert_type, "variant": "tonal", "density": "compact",
             "border": "start", "class": "rounded-lg"}
    if icon:
        props["prepend_icon"] = icon
    return {"component": "VAlert", "props": props, "text": text}


def _icon(name: str, color: str = "", size: str = "small", extra_class: str = "mr-2"):
    """v1.2.9: 图标统一辅助 - 所有 chip/icon 都通过这里走 mdi-*"""
    props = {"size": size, "class": extra_class}
    if color:
        props["color"] = color
    return {"component": "VIcon", "props": props, "text": name}


# v1.3.0: 危险操作二次确认 - VDialog 包按钮
# 用法：_confirm_danger_zone(is_scanning=False) 返回一个危险操作按钮
# MoviePilot 前端基于 Vuetify，支持 VDialog
def _confirm_danger_zone(is_scanning: bool = False) -> dict:
    """v1.3.0: 危险操作二次确认卡
    包含一个 tonal 红色按钮，触发 VDialog 确认弹窗
    确认后真正调用清空缓存 API
    """
    # 按钮本身（弹窗触发器）
    trigger_btn = {
        "component": "VBtn",
        "props": {
            "color": C_ERROR, "variant": "tonal", "rounded": "lg",
            "prepend_icon": "mdi-delete-alert",
            "class": "text-none",
            "block": True,
            "disabled": is_scanning,
        },
        "text": "清空缓存（危险）",
        # 点击不会直接调 API，而是打开 VDialog
        "events": {"click": {"action": "open_dialog", "target": "clear_cache_confirm"}},
    }
    # 弹窗内容
    dialog_content = {
        "component": "VCard",
        "props": {"class": "rounded-lg", "variant": "outlined",
                  "style": {"backgroundColor": "rgba(255,255,255,0.04)",
                            "border": f"1px solid {CARD_BORDER}"}},
        "content": [
            {"component": "VCardTitle", "props": {"class": "d-flex align-center py-3"},
             "content": [
                 {"component": "VIcon", "props": {"color": C_ERROR, "size": "default", "class": "mr-2"},
                  "text": "mdi-alert-octagon"},
                 {"component": "span",
                  "props": {"class": "text-h6 font-weight-bold text-high-emphasis"},
                  "text": "确认清空缓存？"},
             ]},
            {"component": "VDivider", "props": {"style": {"opacity": 0.3}}},
            {"component": "VCardText", "props": {"class": "py-4"}, "content": [
                {"component": "div",
                 "props": {"class": "text-body-2 text-high-emphasis mb-2"},
                 "text": "将清除以下数据（不可恢复）："},
                {"component": "ul",
                 "props": {"class": "text-caption text-medium-emphasis", "style": {"paddingLeft": "20px"}},
                 "content": [
                     {"component": "li", "text": "人名翻译缓存"},
                     {"component": "li", "text": "角色名翻译缓存"},
                     {"component": "li", "text": "已处理记录（重扫会重新翻译全部条目）"},
                 ]},
                {"component": "div",
                 "props": {"class": "mt-3 text-caption", "style": {"color": C_WARNING}},
                 "text": "⚠ 建议先用「立即扫描」跑完一轮，再用「清空缓存」处理异常条目。"},
            ]},
            {"component": "VDivider", "props": {"style": {"opacity": 0.3}}},
            {"component": "VCardActions", "props": {"class": "pa-3"}, "content": [
                {"component": "VSpacer"},
                # 取消按钮 - outlined
                {"component": "VBtn",
                 "props": {"variant": "outlined", "rounded": "lg", "class": "text-none mr-2",
                           "color": "grey"},
                 "text": "取消",
                 "events": {"click": {"action": "close_dialog", "target": "clear_cache_confirm"}}},
                # 真正确认按钮 - elevated + error
                {"component": "VBtn",
                 "props": {"variant": "elevated", "rounded": "lg", "class": "text-none",
                           "color": C_ERROR, "prepend_icon": "mdi-delete-forever"},
                 "text": "确认清空",
                 "events": {"click": {"api": "plugin/EmbyPeopleLocalize/clear_cache",
                                      "method": "POST",
                                      "action": "close_dialog", "target": "clear_cache_confirm"}}},
            ]},
        ]
    }
    # 触发按钮 + 隐藏的 VDialog
    return {
        "component": "div", "props": {"class": "mt-2"},
        "content": [
            trigger_btn,
            # 弹窗（Vuetify 组件）
            {
                "component": "VDialog",
                "props": {"model": False, "max_width": 480, "persistent": True},
                "content": [dialog_content],
                # 标记用于前端识别
                "id": "clear_cache_confirm",
            },
        ]
    }

