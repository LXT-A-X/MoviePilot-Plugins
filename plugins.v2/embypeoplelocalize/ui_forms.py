"""
ui_forms.py - Emby 演职人员中文化 页面布局
- 数据面板（build_page）：只显示状态与统计，去掉操作按钮
- 配置表单（build_form）：基础设置 + 大模型连接 + 翻译范围 + 提示词 + 高级设置 + 手动操作

设计方向（frontend-design 技能 + 用户偏好）：
- 极简、信息层级清晰
- 不使用白色底色卡片（宿主背景导致看不见），改用透明/ outlined 卡片 + 左侧强调线
- 主色：深靛青 #4338ca；功能色：青绿 #0d9488、琥珀 #d97706、玫红 #e11d48
- 避免花哨渐变与过度装饰

MoviePilot V2 前端约定：
- 页面按钮通过 events: {"click": {"api": "...", "method": "..."}} 触发
- 配置对话框由宿主提供「保存」按钮，表单内不要再放保存/返回按钮
"""
from typing import Any, Dict, List
from app.core.config import settings

# ============================================================
# 配色变量
# ============================================================
C_PRIMARY = "#4338ca"      # 深靛青 - 主操作 / 基础设置
C_SUCCESS = "#0d9488"      # 青绿 - 成功 / 手动操作
C_INFO = "#0891b2"         # 青色 - 翻译范围 / 信息
C_WARNING = "#d97706"      # 琥珀 - 高级设置 / 警告
C_ERROR = "#e11d48"        # 玫红 - 错误

# 卡片统一底色与边框（适配 MoviePilot 暗色主题，略亮于背景）
CARD_BG = "rgba(255, 255, 255, 0.04)"
CARD_BORDER = "rgba(255, 255, 255, 0.10)"
CARD_SHADOW = "0 1px 3px rgba(0,0,0,0.20)"



# ============================================================
# 通用辅助函数
# ============================================================


def _row(content, classes="mb-3", justify="start", align="start", no_gutters=False):
    """一行多列容器（使用 Vuetify 原生间距）"""
    props = {"dense": True, "class": classes, "justify": justify, "align": align}
    if no_gutters:
        props["no_gutters"] = True
    return {"component": "VRow", "props": props, "content": content}


def _col(cols, content, sm=None, md=None, lg=None):
    """列容器（支持响应式断点）"""
    props = {"cols": cols}
    if sm is not None:
        props["sm"] = sm
    if md is not None:
        props["md"] = md
    if lg is not None:
        props["lg"] = lg
    if isinstance(content, list):
        return {"component": "VCol", "props": props, "content": content}
    return {"component": "VCol", "props": props, "content": [content]}


def _section(title: str, accent: str, content_list):
    """带左侧强调线的卡片（暗色背景下略亮于背景）"""
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
            {
                "component": "VCardTitle",
                "props": {
                    "class": "text-subtitle-1 font-weight-bold d-flex align-center py-3 text-high-emphasis",
                    "style": {"letterSpacing": "0.02em"},
                },
                "text": title,
            },
            {"component": "VDivider", "props": {"class": "mb-3", "style": {"opacity": 0.4}}},
            {"component": "VCardText", "props": {"class": "pt-0 pb-4"}, "content": content_list},
        ],
    }


def _stat_card(label, value, accent):
    """统计卡片（带底色与边框，暗色背景下可见）"""
    return {
        "component": "VCard",
        "props": {
            "class": "rounded-lg h-100",
            "variant": "outlined",
            "style": {
                "backgroundColor": CARD_BG,
                "border": f"1px solid {CARD_BORDER}",
                "borderLeft": f"3px solid {accent}",
                "boxShadow": CARD_SHADOW,
            },
        },
        "content": [
            {
                "component": "VCardText",
                "props": {"class": "py-3 px-4 d-flex flex-column justify-center"},
                "content": [
                    {
                        "component": "div",
                        "props": {"class": "text-caption text-medium-emphasis mb-1"},
                        "text": label,
                    },
                    {
                        "component": "div",
                        "props": {"class": "text-h5 font-weight-bold text-high-emphasis"},
                        "text": str(value),
                    },
                ],
            }
        ],
    }


def _switch(key, label, hint="", disabled=False):
    """开关控件（始终返回单个 dict，hint 用 div 包裹）"""
    item = {
        "component": "VSwitch",
        "props": {
            "model": key,
            "label": label,
            "color": "primary",
            "density": "compact",
            "class": "mb-0",
            "disabled": disabled,
        },
    }
    if hint:
        return {
            "component": "div",
            "props": {"class": "w-100"},
            "content": [
                item,
                {
                    "component": "div",
                    "props": {"class": "text-caption text-medium-emphasis ml-4 mb-1"},
                    "text": hint,
                },
            ],
        }
    return item


def _text_field(key, label, placeholder="", hint="", input_type="text"):
    """文本输入框（始终返回单个 dict，hint 用 div 包裹）"""
    props = {
        "model": key,
        "label": label,
        "placeholder": placeholder,
        "density": "compact",
        "variant": "outlined",
        "class": "mb-1",
        "style": {
            "--v-field-border-opacity": "0.65",
            "--v-field-border-width": "1px",
        },
    }
    if input_type == "number":
        props["type"] = "number"
    elif input_type == "password":
        props["type"] = "password"
    field = {"component": "VTextField", "props": props}
    if hint:
        return {
            "component": "div",
            "props": {"class": "w-100"},
            "content": [
                field,
                {
                    "component": "div",
                    "props": {"class": "text-caption text-medium-emphasis ml-1 mb-2"},
                    "text": hint,
                },
            ],
        }
    return field


def _select(key, label, items, hint=""):
    """下拉选择框（多选，始终返回单个 dict，hint 用 div 包裹）"""
    props = {
        "model": key,
        "label": label,
        "items": items,
        "density": "compact",
        "variant": "outlined",
        "multiple": True,
        "chips": True,
        "deletable_chips": True,
        "class": "mb-1",
        "style": {
            "--v-field-border-opacity": "0.65",
            "--v-field-border-width": "1px",
        },
    }
    field = {"component": "VSelect", "props": props}
    if hint:
        return {
            "component": "div",
            "props": {"class": "w-100"},
            "content": [
                field,
                {
                    "component": "div",
                    "props": {"class": "text-caption text-medium-emphasis ml-1 mb-2"},
                    "text": hint,
                },
            ],
        }
    return field


def _textarea(key, label, placeholder="", hint="", rows=8):
    """多行文本框（始终返回单个 dict，hint 用 div 包裹）"""
    props = {
        "model": key,
        "label": label,
        "placeholder": placeholder,
        "density": "compact",
        "variant": "outlined",
        "rows": rows,
        "auto_grow": True,
        "class": "mb-1",
        "style": {
            "--v-field-border-opacity": "0.65",
            "--v-field-border-width": "1px",
        },
    }
    field = {"component": "VTextarea", "props": props}
    if hint:
        return {
            "component": "div",
            "props": {"class": "w-100"},
            "content": [
                field,
                {
                    "component": "div",
                    "props": {"class": "text-caption text-medium-emphasis ml-1 mb-2"},
                    "text": hint,
                },
            ],
        }
    return field


def _btn(text, color, api_path, method="POST", variant="elevated", block=True):
    """
    配置表单内按钮（MoviePilot V2 events 约定）
    api_path: 相对路径，如 "plugin/EmbyPeopleLocalize/scan"
    events 格式由 FormRender 编译为点击事件，自动调用 API 并弹窗展示结果。
    """
    props = {
        "color": color,
        "block": block,
        "variant": variant,
        "rounded": "lg",
        "type": "button",
    }
    if not block:
        props["class"] = "text-none"
    return {
        "component": "VBtn",
        "props": props,
        "text": text,
        "events": {"click": {"api": api_path, "method": method}},
    }


def _hint(text, color=None):
    """提示文字（使用 Vuetify 主题感知颜色）"""
    props = {"class": "text-caption mt-1 text-medium-emphasis", "style": {"lineHeight": 1.5}}
    if color:
        props["style"]["color"] = color
    return {"component": "div", "props": props, "text": text}


def _alert(text, alert_type="warning"):
    """警告提示条"""
    return {
        "component": "VAlert",
        "props": {
            "type": alert_type,
            "variant": "tonal",
            "density": "compact",
            "border": "start",
            "class": "rounded-lg",
        },
        "text": text,
    }


def _chip(text, color):
    """状态标签"""
    return {
        "component": "VChip",
        "props": {
            "color": color,
            "size": "small",
            "variant": "tonal",
            "class": "font-weight-medium",
        },
        "text": text,
    }


# ============================================================
# 第一页：数据面板（build_page）
# ============================================================


def build_page(plugin) -> List[dict]:
    """
    构建插件数据面板（只读展示）
    - 顶部：标题 + 状态
    - 运行状态条
    - 统计卡片
    - 最近历史列表
    操作按钮已统一移到设置页「手动操作」区域。
    """
    history = getattr(plugin, "_history", []) or []
    name_cache = getattr(plugin, "_name_cache", {}) or {}
    role_cache = getattr(plugin, "_role_cache", {}) or {}
    processed = getattr(plugin, "_processed", {}) or {}
    cache_hits = getattr(plugin, "_cache_hits", 0) or 0
    cache_misses = getattr(plugin, "_cache_misses", 0) or 0

    history_count = len(history)
    name_cache_count = sum(len(v) for v in name_cache.values())
    role_cache_count = sum(len(v) for v in role_cache.values())
    total_cache = name_cache_count + role_cache_count
    processed_count = len(processed)
    total_fields = sum(int(h.get("n_trans") or 0) for h in history)
    total_lookups = cache_hits + cache_misses
    cache_hit_rate = round(cache_hits / total_lookups * 100, 1) if total_lookups > 0 else 0.0

    # Cast 锁定率（从最近 50 条历史统计）
    recent = history[-50:]
    lock_checked = [h for h in recent if "cast_locked" in h]
    locked_n = sum(1 for h in lock_checked if h.get("cast_locked"))
    lock_rate = round(locked_n / len(lock_checked) * 100, 1) if lock_checked else 0

    emby_connected = getattr(plugin, "_emby", None) is not None
    llm_ready = getattr(plugin, "_llm", None) is not None
    llm_model = getattr(plugin._llm, "model", "") if llm_ready else ""
    plugin_llm_model = getattr(plugin, "_llm_model", "") or ""
    plugin_llm_base = getattr(plugin, "_llm_base_url", "") or ""
    plugin_llm_key = getattr(plugin, "_llm_api_key", "") or ""
    using_plugin_any = bool(plugin_llm_model or plugin_llm_base or plugin_llm_key)
    is_running = getattr(plugin, "_is_running", False)
    is_paused = getattr(plugin, "_is_paused", False)
    last_run = getattr(plugin, "_last_run_time", None)
    progress_total = getattr(plugin, "_progress_total", 0)
    progress_done = getattr(plugin, "_progress_done", 0)
    progress_current_title = getattr(plugin, "_progress_current_title", "")
    progress_current_library = getattr(plugin, "_progress_current_library", "")

    # ── 页面标题栏 ──
    header = {
        "component": "VCard",
        "props": {
            "class": "mb-3 rounded-lg",
            "variant": "outlined",
            "style": {
                "backgroundColor": CARD_BG,
                "border": f"1px solid {CARD_BORDER}",
                "borderLeft": f"4px solid {C_PRIMARY}",
                "boxShadow": CARD_SHADOW,
            },
        },
        "content": [
            {
                "component": "VCardText",
                "props": {"class": "py-3 px-4"},
                "content": [
                    _row(
                        [
                            _col(
                                "auto",
                                [
                                    {
                                        "component": "div",
                                        "props": {"class": "text-h6 font-weight-bold text-high-emphasis"},
                                        "text": "Emby 演职人员中文化",
                                    },
                                    {
                                        "component": "div",
                                        "props": {"class": "text-caption text-medium-emphasis mt-1"},
                                        "text": "利用大模型将英文 / 罗马音 / 日文人名翻译为简体中文",
                                    },
                                ],
                            ),
                            _col(
                                "auto",
                                [
                                    {
                                        "component": "div",
                                        "props": {
                                            "class": "d-flex ga-2",
                                            "style": {"flexWrap": "wrap", "justifyContent": "flex-end"},
                                        },
                                        "content": [
                                            _chip("Emby 已连接" if emby_connected else "Emby 未连接", "success" if emby_connected else "error"),
                                            _chip(f"LLM: {llm_model}" if llm_ready and llm_model else ("LLM 就绪" if llm_ready else "LLM 未配置"), "success" if llm_ready else "warning"),
                                            _chip("插件独立" if using_plugin_any else "MP 系统", "info" if using_plugin_any else "success"),
                                        ],
                                    }
                                ],
                                md="auto",
                            ),
                        ],
                        justify="space-between",
                        align="center",
                    )
                ],
            }
        ],
    }

    # ── 运行状态条 + 进度 ──
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

    # 构建状态条内容
    status_content = [
        {
            "component": "VCardText",
            "props": {"class": "py-2 px-4 d-flex align-center"},
            "content": [
                {
                    "component": "VIcon",
                    "props": {"color": status_color, "size": "small", "class": "mr-2"},
                    "text": status_icon,
                },
                {
                    "component": "span",
                    "props": {"class": "text-body-2 font-weight-medium text-high-emphasis"},
                    "text": status_text,
                },
            ],
        }
    ]

    # 扫描中显示进度
    if is_running and progress_total > 0:
        progress_pct = round(progress_done / max(progress_total, 1) * 100, 1)
        progress_bar = {
            "component": "VCardText",
            "props": {"class": "px-4 pb-3"},
            "content": [
                {
                    "component": "div",
                    "props": {"class": "d-flex align-center mb-2"},
                    "content": [
                        {
                            "component": "span",
                            "props": {"class": "text-caption text-medium-emphasis flex-grow-1"},
                            "text": f"当前：{progress_current_title or '准备中...'}",
                        },
                        {
                            "component": "span",
                            "props": {"class": "text-caption font-weight-bold", "style": {"color": C_INFO}},
                            "text": f"{progress_done}/{progress_total}  ({progress_pct}%)",
                        },
                    ],
                },
                {
                    "component": "VProgressLinear",
                    "props": {
                        "model": progress_pct,
                        "color": C_INFO,
                        "density": "compact",
                        "rounded": True,
                        "height": 4,
                        "class": "mb-1",
                    },
                },
                {
                    "component": "span",
                    "props": {"class": "text-caption text-medium-emphasis"},
                    "text": progress_current_library or "",
                },
            ],
        }
        status_content.append(progress_bar)

    status_bar = {
        "component": "VCard",
        "props": {
            "class": "mb-4 rounded-lg",
            "variant": "outlined",
            "style": {
                "backgroundColor": CARD_BG,
                "border": f"1px solid {CARD_BORDER}",
                "boxShadow": CARD_SHADOW,
            },
        },
        "content": status_content,
    }

    # ── 统计卡片行 ──
    stat_row = _row(
        [
            _col(6, [_stat_card("处理作品", history_count, C_PRIMARY)], sm=6, md=3),
            _col(6, [_stat_card("翻译字段", total_fields, C_SUCCESS)], sm=6, md=3),
            _col(6, [_stat_card("角色缓存", role_cache_count, C_INFO)], sm=6, md=3),
            _col(6, [_stat_card("缓存命中率", f"{cache_hit_rate}%", C_WARNING)], sm=6, md=3),
        ],
    )

    # ── 缓存详情摘要 ──
    cache_summary = {
        "component": "VCard",
        "props": {
            "class": "mt-3 mb-4 rounded-lg",
            "variant": "outlined",
            "style": {
                "backgroundColor": CARD_BG,
                "border": f"1px solid {CARD_BORDER}",
                "boxShadow": CARD_SHADOW,
            },
        },
        "content": [
            {
                "component": "VCardText",
                "props": {"class": "py-3 px-4 d-flex align-center justify-space-between"},
                "content": [
                    {
                        "component": "div",
                        "props": {"class": "d-flex align-center"},
                        "content": [
                            {
                                "component": "VIcon",
                                "props": {"color": C_INFO, "size": "small", "class": "mr-2"},
                                "text": "mdi-database",
                            },
                            {
                                "component": "span",
                                "props": {"class": "text-body-2 font-weight-medium text-high-emphasis"},
                                "text": "缓存统计",
                            },
                        ],
                    },
                    {
                        "component": "div",
                        "props": {"class": "d-flex align-center ga-3"},
                        "content": [
                            {
                                "component": "span",
                                "props": {"class": "text-caption text-medium-emphasis"},
                                "text": f"人名: {name_cache_count}",
                            },
                            {
                                "component": "span",
                                "props": {"class": "text-caption text-medium-emphasis"},
                                "text": f"角色: {role_cache_count}",
                            },
                            {
                                "component": "span",
                                "props": {"class": "text-caption font-weight-bold", "style": {"color": C_INFO if cache_hit_rate >= 50 else C_WARNING}},
                                "text": f"命中: {cache_hits} / 未命中: {cache_misses}",
                            },
                        ],
                    },
                ],
            }
        ],
    }

    # ── 锁定率摘要 ──
    lock_summary = {
        "component": "VCard",
        "props": {
            "class": "mt-3 mb-4 rounded-lg",
            "variant": "outlined",
            "style": {
                "backgroundColor": CARD_BG,
                "border": f"1px solid {CARD_BORDER}",
                "boxShadow": CARD_SHADOW,
            },
        },
        "content": [
            {
                "component": "VCardText",
                "props": {"class": "py-3 px-4 d-flex align-center justify-space-between"},
                "content": [
                    {
                        "component": "div",
                        "props": {"class": "d-flex align-center"},
                        "content": [
                            {
                                "component": "VIcon",
                                "props": {"color": C_SUCCESS if lock_rate >= 99 else C_WARNING, "size": "small", "class": "mr-2"},
                                "text": "mdi-lock" if lock_rate >= 99 else "mdi-lock-open",
                            },
                            {
                                "component": "span",
                                "props": {"class": "text-body-2 font-weight-medium text-high-emphasis"},
                                "text": "Cast 锁定率",
                            },
                        ],
                    },
                    {
                        "component": "span",
                        "props": {"class": "text-h6 font-weight-bold", "style": {"color": C_SUCCESS if lock_rate >= 99 else C_WARNING}},
                        "text": f"{lock_rate}%",
                    },
                ],
            }
        ],
    }

    # ── 历史记录列表 ──
    history_list = _build_history_list(history)

    # ── 整体外框 ──
    page_wrapper = {
        "component": "VCard",
        "props": {
            "class": "pa-4 rounded-xl",
            "variant": "outlined",
            "style": {
                "backgroundColor": "rgba(255, 255, 255, 0.02)",
                "border": f"1px solid {CARD_BORDER}",
                "boxShadow": "0 2px 8px rgba(0,0,0,0.25)",
            },
        },
        "content": [header, status_bar, stat_row, cache_summary, lock_summary, history_list],
    }

    return [
        {
            "component": "div",
            "props": {"class": "pa-4", "style": {"minHeight": "100vh"}},
            "content": [page_wrapper],
        }
    ]


def _build_history_list(history):
    """历史记录卡片列表"""
    if not history:
        return {
            "component": "VCard",
            "props": {
                "class": "mt-4 rounded-lg text-center pa-6",
                "variant": "outlined",
                "style": {
                    "backgroundColor": CARD_BG,
                    "border": f"1px solid {CARD_BORDER}",
                    "boxShadow": CARD_SHADOW,
                },
            },
            "content": [
                {
                    "component": "div",
                    "props": {"class": "text-medium-emphasis"},
                    "text": "暂无翻译历史记录",
                }
            ],
        }

    list_items = []
    for h in history[-50:]:
        locked = h.get("cast_locked")
        if locked is True:
            lock_icon = "mdi-lock"
            lock_color = C_SUCCESS
            lock_text = "已锁定"
        elif locked is False:
            lock_icon = "mdi-lock-open"
            lock_color = C_WARNING
            lock_text = "未锁定"
        else:
            lock_icon = "mdi-minus"
            lock_color = "grey"
            lock_text = "—"

        status = h.get("status", "")
        status_color = C_SUCCESS if status == "成功" else (C_ERROR if "失败" in status else "grey")

        list_items.append({
            "component": "VListItem",
            "props": {
                "class": "px-0 py-2",
                "style": {"borderBottom": "1px solid rgba(128,128,128,0.12)"},
            },
            "content": [
                {
                    "component": "VRow",
                    "props": {"dense": True, "align": "center"},
                    "content": [
                        {
                            "component": "VCol",
                            "props": {"cols": 12, "sm": 5, "class": "py-1"},
                            "content": [
                                {
                                    "component": "div",
                                    "props": {"class": "text-body-2 font-weight-medium text-high-emphasis text-truncate"},
                                    "text": h.get("title", "未知作品") or "未知作品",
                                },
                                {
                                    "component": "div",
                                    "props": {"class": "text-caption text-medium-emphasis text-truncate"},
                                    "text": f"{h.get('time', '')} · {h.get('library', '')}",
                                },
                            ],
                        },
                        {
                            "component": "VCol",
                            "props": {"cols": 4, "sm": 2, "class": "py-1 text-center"},
                            "content": [
                                {
                                    "component": "VChip",
                                    "props": {
                                        "color": status_color,
                                        "size": "small",
                                        "variant": "tonal",
                                        "label": True,
                                    },
                                    "text": status or "—",
                                }
                            ],
                        },
                        {
                            "component": "VCol",
                            "props": {"cols": 4, "sm": 2, "class": "py-1 text-center"},
                            "content": [
                                {
                                    "component": "div",
                                    "props": {"class": "text-caption text-medium-emphasis"},
                                    "text": f"翻译 {h.get('n_trans', 0)} 条",
                                }
                            ],
                        },
                        {
                            "component": "VCol",
                            "props": {"cols": 4, "sm": 3, "class": "py-1 d-flex justify-end align-center"},
                            "content": [
                                {
                                    "component": "VIcon",
                                    "props": {"color": lock_color, "size": "small", "class": "mr-1"},
                                    "text": lock_icon,
                                },
                                {
                                    "component": "span",
                                    "props": {"class": "text-caption", "style": {"color": lock_color}},
                                    "text": lock_text,
                                },
                            ],
                        },
                    ],
                }
            ],
        })

    return {
        "component": "VCard",
        "props": {
            "class": "mt-4 rounded-lg",
            "variant": "outlined",
            "style": {
                "backgroundColor": CARD_BG,
                "border": f"1px solid {CARD_BORDER}",
                "boxShadow": CARD_SHADOW,
            },
        },
        "content": [
            {
                "component": "VCardTitle",
                "props": {
                    "class": "text-subtitle-1 font-weight-bold py-3 px-4 text-high-emphasis",
                    "style": {"letterSpacing": "0.02em"},
                },
                "text": "最近翻译历史",
            },
            {"component": "VDivider", "props": {"style": {"opacity": 0.4}}},
            {
                "component": "VCardText",
                "props": {
                    "class": "px-4 pt-2 pb-2",
                    "style": {"maxHeight": "360px", "overflowY": "auto"}
                },
                "content": [
                    {"component": "VList", "props": {"class": "pa-0 bg-transparent"}, "content": list_items}
                ],
            },
        ],
    }


# ============================================================
# 第二页：设置页（build_form）
# ============================================================


def build_form(lib_options, plugin, invalid_libraries=None):
    """
    构建插件配置表单
    - 基础设置
    - 大模型连接（插件独立配置）
    - 翻译范围
    - 大模型提示词
    - 高级设置
    - 手动操作（立即扫描、补锁定、刷新状态、清空缓存）

    注意：宿主会自动渲染保存按钮，表单内不要再放保存/返回按钮。
    """
    invalid_libraries = invalid_libraries or []
    llm_ready = getattr(plugin, "_llm", None) is not None
    llm_model = getattr(plugin._llm, "model", "") if llm_ready else ""

    # ── 卡片 1：基础设置 ──
    is_scanning = getattr(plugin, "_is_running", False)

    basic_rows = [
        _row([
            _col(12, [_switch("enabled", "启用插件", "开启后定时 / 实时翻译演职人员")], sm=6),
            _col(12, [_switch("run_scan", "立即扫描（保存后执行）", "打开开关后点下方保存按钮，插件自动开始扫描")], sm=6),
        ]),
        _row([
            _col(12, [_switch("run_clear_cache", "清除缓存并重扫", "清空所有已处理记录和缓存，然后立即重新扫描全部条目")], sm=6),
            _col(12, [_switch("run_lock_cast", "批量补锁定旧条目", "为已翻译但未锁定的旧条目补充 Cast 锁定")], sm=6),
        ]),
        _row([
            _col(12, [_switch("notify_on_complete", "扫描完成后发送通知", "每次扫描完成推送通知，包含翻译统计和缓存命中率")], sm=6),
            _col(12, [_hint(
                "「立即扫描」「清除缓存」「补锁定」均为一次性触发，执行完成后自动复位。"
            )], sm=6),
        ]),
        _row([
            _col(12, [_select("libraries", "选择媒体库（多选，留空 = 全部）", lib_options,
                           "选择要扫描的媒体库，支持跨服务器；留空则扫描所有服务器所有库")]),
        ]),
        _row([
            _col(12, [_text_field("cron", "定时扫描 Cron", "0 4 * * *", "例：0 4 * * * 每天凌晨 4 点")], sm=6),
            _col(12, [_text_field("delay", "批间延迟（秒）", "2", "每次请求间隔，避免触发限流", "number")], sm=6),
        ]),
    ]
    if is_scanning:
        basic_rows.append(
            _row([
                _col(12, [
                    _btn("⏹  停止扫描", C_ERROR, "plugin/EmbyPeopleLocalize/stop", variant="tonal")
                ]),
            ])
        )
    if invalid_libraries:
        basic_rows.append(
            _row([
                _col(12, [_alert(
                    f"已自动移除失效的媒体库配置：{', '.join(invalid_libraries)}"。"
                    "它们通常来自历史版本残留或服务器地址变更。"
                )]),
            ])
        )
    if not lib_options:
        basic_rows.append(
            _row([
                _col(12, [_alert(
                    "未获取到任何媒体库，请检查 Emby 服务器是否在线、API Key 是否有效。",
                    "error"
                )]),
            ])
        )
    card_basic = _section("基础设置", C_PRIMARY, basic_rows)

    # ── 卡片 2：大模型连接（插件独立配置）──
    # 获取插件自身配置和 MP 系统配置，判断数据源
    plugin_base_url = getattr(plugin, "_llm_base_url", "") or ""
    plugin_api_key = getattr(plugin, "_llm_api_key", "") or ""
    plugin_model = getattr(plugin, "_llm_model", "") or ""
    mp_base_url = getattr(settings, "LLM_BASE_URL", "") or ""
    mp_api_key = getattr(settings, "LLM_API_KEY", "") or ""
    mp_model = getattr(settings, "LLM_MODEL", "") or ""

    using_plugin_base = bool(plugin_base_url)
    using_plugin_key = bool(plugin_api_key)
    using_plugin_model = bool(plugin_model)
    using_plugin_any = using_plugin_base or using_plugin_key or using_plugin_model

    # 显示有效模型名（实时读取，优先显示当前 LLM 客户端实际使用的模型）
    current_llm_model = llm_model or plugin_model or mp_model or "未配置"
    effective_source = "插件独立配置" if using_plugin_any else "MoviePilot 系统配置"

    llm_status_chip = _chip("已就绪", "success") if llm_ready else _chip("未配置", "warning")
    source_chip = _chip("插件独立 LLM", "info") if using_plugin_any else _chip("MP 系统 LLM", "success")

    # 构建每字段的来源提示
    def _src_label(plugin_val, mp_val, field_name):
        if plugin_val:
            return f"{field_name}：插件自定义"
        elif mp_val:
            return f"{field_name}：系统默认"
        else:
            return f"{field_name}：未配置"

    card_llm = _section("大模型连接", C_INFO, [
        _row([
            _col(12, [
                {
                    "component": "div",
                    "props": {"class": "d-flex align-center ga-2 mb-2 flex-wrap"},
                    "content": [
                        {"component": "span", "props": {"class": "text-body-2 font-weight-medium text-high-emphasis"}, "text": "当前状态："},
                        llm_status_chip,
                        source_chip,
                        {"component": "span", "props": {"class": "text-caption text-medium-emphasis ml-2"}, "text": f"模型：{current_llm_model}"},
                    ],
                }
            ]),
        ]),
        _row([
            _col(12, [_text_field("llm_base_url", "API 地址", "https://api.example.com/v1",
                                   _src_label(plugin_base_url, mp_base_url, "API 地址"))]),
        ]),
        _row([
            _col(12, [_text_field("llm_api_key", "API Key", "sk-xxx",
                                   _src_label(plugin_api_key, mp_api_key, "API Key"), "password")], sm=6),
            _col(12, [_text_field("llm_model", "模型名称", "deepseek-ai/DeepSeek-V4-Flash",
                                   _src_label(plugin_model, mp_model, "模型"), )], sm=4),
            _col(12, [_text_field("llm_timeout", "超时（秒）", "120", "LLM 请求超时", "number")], sm=2),
        ]),
        _row([
            _col(8, [_hint(
                "留空的字段自动回退到 MoviePilot 系统设置。"
                f" 当前：{effective_source}"
            )]),
            _col(4, [
                _btn("🔄 重新读取 MP 模型", "info", "plugin/EmbyPeopleLocalize/refresh_llm", variant="tonal", block=False)
            ]),
        ]),
    ])

    # ── 卡片 3：翻译范围 ──
    translate_all = getattr(plugin, "_translate_all", False)
    card_scope = _section("翻译范围", C_SUCCESS, [
        _row([
            _col(12, [_switch("translate_all", "全部翻译", "翻译所有人名 + 角色名，忽略下方单项选择")]),
        ]),
        _row([
            _col(12, [_switch("translate_role", "翻译剧中角色", "翻译第二行角色名（Role 字段），如 Goro Inogashira → 五郎 猪头", disabled=translate_all)]),
        ]),
        _row([
            _col(12, [_switch("translate_actor", "演员 Actor", "翻译演员 / 声优的人名", disabled=translate_all)], sm=4),
            _col(12, [_switch("translate_director", "导演 Director", "翻译导演名字", disabled=translate_all)], sm=4),
            _col(12, [_switch("translate_writer", "编剧 Writer", "翻译编剧名字", disabled=translate_all)], sm=4),
        ]),
        _row([
            _col(12, [_switch("translate_producer", "制作人 Producer", "翻译制作人名字", disabled=translate_all)], sm=4),
            _col(12, [_hint("开启「全部翻译」并保存后，以上开关显示为开启但不可操作。如需单独配置，请先关闭「全部翻译」。")], sm=8),
        ]),
    ])

    # ── 卡片 4：大模型提示词 ──
    card_prompt = _section("大模型提示词", C_WARNING, [
        _textarea(
            "prompt_template",
            "提示词模板（含 {title_json} {year_json} {terms_json} 占位符）",
            placeholder="留空使用内置默认提示词",
            hint="可用占位符：{title_json}=作品名，{year_json}=年份，{terms_json}=待翻译词条列表",
            rows=10,
        ),
    ])

    # ── 卡片 5：高级设置 ──
    advanced_rows = [
        _row([
            _col(12, [_text_field("max_people_per_title", "单部作品最多翻译人数", "10", "每部剧集或电影最多翻译前 N 个人名", "number")], sm=4),
            _col(12, [_text_field("max_people_per_batch", "每次请求翻译条数", "5", "一次请求中发送给 LLM 的词条数量", "number")], sm=4),
            _col(12, [_switch("overwrite_chinese", "重新翻译已有中文名", "开启后会重新翻译 Emby 中已有的中文译名")], sm=4),
        ]),
        _row([
            _col(12, [_switch("lock_cast", "扫描时自动锁定 Cast",
                              "开启后，每次翻译写回都会自动把 Cast 加入 LockedFields，防止后续刮削覆盖中文译名")]),
        ]),
        _row([
            _col(12, [_text_field("webhook_delay", "入库延迟(秒)", "60",
                                  "Emby 通过 Webhook 入库后等待 N 秒再扫描（等待刮源完成）", "number")]),
        ]),
    ]
    card_advanced = _section("高级设置", C_WARNING, advanced_rows)

    form = [
        card_basic,
        card_llm,
        card_scope,
        card_prompt,
        card_advanced,
    ]

    # 默认配置（用于初始化表单）
    default_config = {
        "enabled": False,
        "cron": "0 4 * * *",
        "delay": 2,
        "translate_actor": True,
        "translate_director": False,
        "translate_writer": False,
        "translate_producer": False,
        "translate_all": False,
        "translate_role": True,
        "prompt_template": "",
        "max_people_per_title": 10,
        "max_people_per_batch": 5,
        "overwrite_chinese": False,
        "libraries": [],
        "lock_cast": False,
        "llm_base_url": "",
        "llm_api_key": "",
        "llm_model": "",
        "llm_timeout": 120,
        "run_scan": False,
        "run_lock_cast": False,
        "run_clear_cache": False,
        "webhook_delay": 60,
        "notify_on_complete": False,
    }

    return form, default_config