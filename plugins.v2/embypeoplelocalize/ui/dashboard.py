"""
ui/dashboard.py - 首页数据面板
v1.2.9: 拆出 - 包含 header / 状态条 / 统计 / Webhook / 缓存 / 失败中心 / 最近活动 / 历史
"""
from datetime import datetime
from typing import Any, Dict, List

from app.log import logger

from .common import (
    _row, _col, _section, _stat_card, _icon, _chip, C_PRIMARY, C_SUCCESS, C_INFO,
    C_WARNING, C_ERROR, CARD_BG, CARD_BORDER, CARD_SHADOW,
)
from .progress import build_status_bar


def _build_header(plugin) -> dict:
    """v1.2.9: 字体升级 - 标题 h5 / 数字 h4 / 描述 caption
    v1.3.2: 新增插件启动状态徽章 - 让用户一眼看出插件是否已加载
    """
    emby_connected = getattr(plugin, "_emby", None) is not None
    llm_ready = getattr(plugin, "_llm", None) is not None
    llm_model = getattr(plugin._llm, "model", "") if llm_ready else ""
    plugin_llm_model = getattr(plugin, "_llm_model", "") or ""
    plugin_llm_base = getattr(plugin, "_llm_base_url", "") or ""
    plugin_llm_key = getattr(plugin, "_llm_api_key", "") or ""
    using_plugin_any = bool(plugin_llm_model or plugin_llm_base or plugin_llm_key)

    # v1.3.2: 插件启动状态 - 区分 5 种情况
    plugin_state = "unknown"
    if not emby_connected and not llm_ready:
        plugin_state = "未启动"  # Emby+LLM 都没就绪 = 插件未真正启动
    elif not emby_connected:
        plugin_state = "Emby 未连接"
    elif not llm_ready:
        plugin_state = "LLM 未配置"
    else:
        plugin_state = "运行中"

    state_chip_map = {
        "运行中": ("success", "mdi-check-circle"),
        "未启动": ("error", "mdi-power-off"),
        "Emby 未连接": ("warning", "mdi-server-off"),
        "LLM 未配置": ("warning", "mdi-robot-off"),
        "unknown": ("grey", "mdi-help-circle"),
    }
    state_color, state_icon = state_chip_map.get(plugin_state, ("grey", "mdi-help-circle"))

    # v1.3.2: 插件版本号 - 让用户清楚当前加载的版本
    plugin_version = getattr(plugin, "plugin_version", "?")

    return {
        "component": "VCard",
        "props": {"class": "mb-3 rounded-lg", "variant": "outlined",
                  "style": {"backgroundColor": CARD_BG, "border": f"1px solid {CARD_BORDER}",
                            "borderLeft": f"4px solid {C_PRIMARY}", "boxShadow": CARD_SHADOW}},
        "content": [{"component": "VCardText", "props": {"class": "py-3 px-4"}, "content": [
            _row([
                _col("auto", [
                    # v1.2.9: 页面标题升级 text-h5 + icon
                    {"component": "div", "props": {"class": "d-flex align-center"},
                     "content": [
                         _icon("mdi-movie-open", color=C_PRIMARY, size="default", extra_class="mr-2"),
                         {"component": "span",
                          "props": {"class": "text-h5 font-weight-bold text-high-emphasis"},
                          "text": "Emby 演职人员中文化"},
                         # v1.3.2: 版本号徽章
                         _chip(f"v{plugin_version}", "primary", icon="mdi-tag-outline"),
                     ]},
                    {"component": "div", "props": {"class": "text-caption text-medium-emphasis mt-1"},
                     "text": "利用大模型将英文 / 罗马音 / 日文人名翻译为简体中文"},
                ]),
                _col("auto", [
                    {"component": "div", "props": {"class": "d-flex ga-2", "style": {"flexWrap": "wrap"}},
                     "content": [
                         # v1.3.2: 启动状态徽章 - 第一个显示
                         _chip(f"插件{plugin_state}", state_color, icon=state_icon),
                         _chip("Emby 已连接" if emby_connected else "Emby 未连接",
                               "success" if emby_connected else "error",
                               icon="mdi-server-network" if emby_connected else "mdi-server-off"),
                         _chip(f"LLM: {llm_model}" if llm_ready and llm_model else ("LLM 就绪" if llm_ready else "LLM 未配置"),
                               "success" if llm_ready else "warning",
                               icon="mdi-robot"),
                         _chip("插件独立" if using_plugin_any else "MP 系统",
                               "info" if using_plugin_any else "success",
                               icon="mdi-cog-outline" if using_plugin_any else "mdi-cog"),
                     ]}
                ], md="auto"),
            ], justify="space-between", align="center")]
        }]
    }


def _build_status_bar(scan_status: Dict[str, Any], plugin=None) -> dict:
    """v1.2.9: 状态卡 - 包裹 build_status_bar 的 content
    v1.3.2: 修复 - 必须传入 plugin，否则 progress.py 访问 plugin.STEP_NAMES 会崩
    """
    content = build_status_bar(scan_status, plugin=plugin)
    return {"component": "VCard", "props": {"class": "mb-3 rounded-lg", "variant": "outlined",
                                           "style": {"backgroundColor": CARD_BG, "border": f"1px solid {CARD_BORDER}",
                                                     "boxShadow": CARD_SHADOW}},
            "content": content}


def _build_stat_row(plugin) -> dict:
    """统计卡片 - v1.2.9: 升级数字 text-h4 + 加 icon"""
    history = getattr(plugin, "_history", []) or []
    name_cache = getattr(plugin, "_name_cache", {}) or {}
    role_cache = getattr(plugin, "_role_cache", {}) or {}
    cache_hits = getattr(plugin, "_cache_hits", 0) or 0
    cache_misses = getattr(plugin, "_cache_misses", 0) or 0
    failed_count = len(getattr(plugin, "_failed", []) or [])

    history_count = len(history)
    name_cache_count = sum(len(v) for v in name_cache.values())
    role_cache_count = sum(len(v) for v in role_cache.values())
    total_fields = sum(int(h.get("n_trans") or 0) for h in history)
    total_lookups = cache_hits + cache_misses
    cache_hit_rate = round(cache_hits / total_lookups * 100, 1) if total_lookups > 0 else 0.0

    return _row([
        _col(6, [_stat_card("已处理", history_count, C_PRIMARY, icon="mdi-check-circle-outline")], sm=6, md=3),
        _col(6, [_stat_card("翻译字段", total_fields, C_SUCCESS, icon="mdi-translate")], sm=6, md=3),
        _col(6, [_stat_card("缓存", name_cache_count + role_cache_count, C_INFO, icon="mdi-database")], sm=6, md=3),
        _col(6, [_stat_card("失败", failed_count, C_ERROR if failed_count > 0 else "grey",
                            icon="mdi-alert-circle-outline")], sm=6, md=3),
    ])


def _build_webhook_card(plugin) -> dict:
    """Webhook 状态卡"""
    wh_received = getattr(plugin, "_webhook_received", 0) or 0
    wh_processed = getattr(plugin, "_webhook_processed", 0) or 0
    wh_failed = getattr(plugin, "_webhook_failed", 0) or 0
    wh_last_time = getattr(plugin, "_webhook_last_time", None)
    wh_last_event = getattr(plugin, "_webhook_last_event", "") or ""
    wh_error = getattr(plugin, "_webhook_error", "") or ""
    wh_success_rate = round(wh_processed / max(wh_received, 1) * 100, 1) if wh_received > 0 else 0.0
    # v1.3.2: 状态文字 + 颜色分离 - 「正常」不应该是红色
    if wh_received == 0:
        # 没收到过任何事件 - 中性「等待中」(info/grey)
        wh_status_text = "等待中"
        wh_status_color = "info"
    elif wh_success_rate >= 90:
        wh_status_text = f"正常 {wh_success_rate}%"
        wh_status_color = "success"
    elif wh_success_rate >= 50:
        wh_status_text = f"部分失败 {wh_success_rate}%"
        wh_status_color = "warning"
    else:
        wh_status_text = f"异常 {wh_success_rate}%"
        wh_status_color = "error"
    wh_last_time_str = datetime.fromtimestamp(wh_last_time).strftime("%m-%d %H:%M:%S") if wh_last_time else ""

    return {"component": "VCard", "props": {"class": "mb-3 rounded-lg", "variant": "outlined",
                                            "style": {"backgroundColor": CARD_BG, "border": f"1px solid {CARD_BORDER}",
                                                      "borderLeft": f"4px solid {C_INFO}", "boxShadow": CARD_SHADOW}},
            "content": [
                {"component": "VCardText", "props": {"class": "py-2 px-4"}, "content": [
                    _row([
                        _col(6, [
                            {"component": "div", "props": {"class": "d-flex align-center"}, "content": [
                                _icon("mdi-webhook", color=C_INFO),
                                {"component": "span", "props": {"class": "text-subtitle-2 font-weight-bold text-high-emphasis"},
                                 "text": "Webhook"},
                                _chip(wh_status_text, wh_status_color),
                            ]},
                            {"component": "div", "props": {"class": "text-caption text-medium-emphasis mt-1"},
                             "text": f"已接收 {wh_received} · 成功 {wh_processed} · 失败 {wh_failed}"},
                        ], sm=6),
                        _col(6, [
                            {"component": "div", "props": {"class": "d-flex align-center"}, "content": [
                                _icon("mdi-clock-outline", color=C_WARNING if wh_error else C_SUCCESS),
                                {"component": "span", "props": {"class": "text-caption text-medium-emphasis"},
                                 "text": f"最后事件: {wh_last_time_str or '无'}"},
                            ]},
                            {"component": "div", "props": {"class": "text-caption text-medium-emphasis mt-1 text-truncate"},
                             "text": wh_error or wh_last_event or "等待入库事件..."},
                        ], sm=6),
                    ], align="center"),
                ]},
            ]}


def _build_cache_card(plugin) -> dict:
    """缓存统计卡 - 一行紧凑"""
    name_cache = getattr(plugin, "_name_cache", {}) or {}
    role_cache = getattr(plugin, "_role_cache", {}) or {}
    cache_hits = getattr(plugin, "_cache_hits", 0) or 0
    cache_misses = getattr(plugin, "_cache_misses", 0) or 0
    name_cache_count = sum(len(v) for v in name_cache.values())
    role_cache_count = sum(len(v) for v in role_cache.values())
    total_lookups = cache_hits + cache_misses
    cache_hit_rate = round(cache_hits / total_lookups * 100, 1) if total_lookups > 0 else 0.0

    return {"component": "VCard", "props": {"class": "mb-3 rounded-lg", "variant": "outlined",
                                            "style": {"backgroundColor": CARD_BG, "border": f"1px solid {CARD_BORDER}",
                                                      "boxShadow": CARD_SHADOW}},
            "content": [
                {"component": "VCardText", "props": {"class": "py-2 px-4 d-flex align-center justify-space-between"},
                 "content": [
                     {"component": "div", "props": {"class": "d-flex align-center"}, "content": [
                         _icon("mdi-database", color=C_INFO),
                         {"component": "span", "props": {"class": "text-body-2 font-weight-medium text-high-emphasis"},
                          "text": "缓存统计"},
                     ]},
                     {"component": "div", "props": {"class": "d-flex align-center ga-3"}, "content": [
                         {"component": "span", "props": {"class": "text-caption text-medium-emphasis"},
                          "text": f"人名 {name_cache_count}"},
                         {"component": "span", "props": {"class": "text-caption text-medium-emphasis"},
                          "text": f"角色 {role_cache_count}"},
                         {"component": "span", "props": {"class": "text-caption font-weight-bold",
                                                          "style": {"color": C_INFO if cache_hit_rate >= 50 else C_WARNING}},
                          "text": f"命中率 {cache_hit_rate}%"},
                     ]},
                 ]},
            ]}


def _build_recent_activity_card(plugin) -> dict:
    """v1.2.9: 新增 - 最近活动列表（最新 5 条）
    替代 / 补充翻译历史列表 - 强调"刚刚发生了什么"
    v1.3.0 补丁: 失败项也展示 reason（合并自 _failed 列表）
    """
    history = getattr(plugin, "_history", []) or []
    failed = getattr(plugin, "_failed", []) or []

    # v1.3.0: 合并历史与失败 - 失败项也带 reason 显示
    # 统一格式：{"title", "status", "n_trans", "time", "reason"}
    merged = []
    for h in history[-10:]:
        merged.append({
            "title": h.get("title") or h.get("series_name") or "未知作品",
            "status": h.get("status", "成功"),
            "n_trans": h.get("n_trans", 0) or 0,
            "time": h.get("time", ""),
            "reason": "",
        })
    for f in failed[-10:]:
        # 时间戳转字符串用于排序
        ts = f.get("time", 0) or 0
        merged.append({
            "title": f.get("title", "未知作品"),
            "status": "失败",
            "n_trans": 0,
            "time": datetime.fromtimestamp(ts).isoformat(timespec="seconds") if ts else "",
            "reason": f.get("reason", "未知错误"),
        })
    # 按 time 倒序取最近 5
    merged.sort(key=lambda x: x.get("time", "") or "", reverse=True)
    recent = merged[:5]

    if not recent:
        return {"component": "VCard", "props": {"class": "mb-3 rounded-lg text-center pa-4",
                                                "variant": "outlined",
                                                "style": {"backgroundColor": CARD_BG,
                                                          "border": f"1px solid {CARD_BORDER}",
                                                          "boxShadow": CARD_SHADOW}},
                "content": [{"component": "div", "props": {"class": "text-medium-emphasis d-flex align-center justify-center"},
                             "content": [
                                 _icon("mdi-history", color="grey", extra_class="mr-2"),
                                 {"component": "span", "text": "暂无活动"},
                             ]}]}

    list_items = []
    for h in recent:
        title = h.get("title", "未知作品")
        status = h.get("status", "")
        n_trans = h.get("n_trans", 0) or 0
        reason = h.get("reason", "")
        # 状态图标
        if status in ("成功", "ok"):
            sym = "✓"
            color = C_SUCCESS
        elif "失败" in status:
            sym = "✗"
            color = C_ERROR
        else:
            sym = "—"
            color = "grey"

        # v1.3.0 补丁: 失败项在标题下加 reason chip
        if "失败" in status and reason:
            content_children = [
                {"component": "div", "props": {"class": "d-flex align-center ga-2"}, "content": [
                    {"component": "span", "props": {"style": {"color": color, "fontWeight": "bold", "minWidth": "14px"}},
                     "text": sym},
                    {"component": "span",
                     "props": {"class": "text-body-2 text-high-emphasis text-truncate flex-grow-1"},
                     "text": title},
                ]},
                # 失败原因 - 缩进、淡红色
                {"component": "div", "props": {"class": "ml-4 mt-1 text-caption",
                                                "style": {"color": C_ERROR, "opacity": 0.85}},
                 "text": f"原因：{reason[:60]}{'…' if len(reason) > 60 else ''}"},
            ]
        else:
            content_children = [
                {"component": "div", "props": {"class": "d-flex align-center ga-2"}, "content": [
                    {"component": "span", "props": {"style": {"color": color, "fontWeight": "bold", "minWidth": "14px"}},
                     "text": sym},
                    {"component": "span",
                     "props": {"class": "text-body-2 text-high-emphasis text-truncate flex-grow-1"},
                     "text": title},
                    {"component": "span", "props": {"class": "text-caption text-medium-emphasis"},
                     "text": f"{n_trans}条"},
                ]}
            ]
        list_items.append({
            "component": "VListItem", "props": {"class": "px-2 py-1"},
            "content": content_children,
        })

    return {"component": "VCard", "props": {"class": "mb-3 rounded-lg", "variant": "outlined",
                                            "style": {"backgroundColor": CARD_BG,
                                                      "border": f"1px solid {CARD_BORDER}",
                                                      "boxShadow": CARD_SHADOW}},
            "content": [
                {"component": "VCardTitle",
                 "props": {"class": "text-subtitle-2 font-weight-bold py-2 px-3 text-high-emphasis d-flex align-center"},
                 "content": [
                     _icon("mdi-pulse", color=C_SUCCESS, extra_class="mr-2"),
                     {"component": "span", "text": "最近活动"},
                 ]},
                {"component": "VDivider", "props": {"style": {"opacity": 0.3}}},
                {"component": "VCardText", "props": {"class": "px-3 py-2"}, "content": [
                    {"component": "VList", "props": {"class": "pa-0 bg-transparent", "density": "compact"},
                     "content": list_items},
                ]},
            ]}


def _build_failed_card(plugin) -> dict:
    """v1.2.9: 新增 - 失败中心卡片
    显示失败任务数 + 最近 3 条失败 + 重试按钮
    """
    failed = list(getattr(plugin, "_failed", []) or [])
    is_running = getattr(plugin, "_is_running", False)
    if not failed:
        return {"component": "VCard", "props": {"class": "mb-3 rounded-lg", "variant": "outlined",
                                                "style": {"backgroundColor": CARD_BG,
                                                          "border": f"1px solid {CARD_BORDER}",
                                                          "boxShadow": CARD_SHADOW}},
                "content": [
                    {"component": "VCardText", "props": {"class": "py-2 px-4 d-flex align-center"}, "content": [
                        _icon("mdi-check-circle", color=C_SUCCESS),
                        {"component": "span",
                         "props": {"class": "text-body-2 font-weight-medium text-high-emphasis"},
                         "text": "失败任务：0"},
                        {"component": "span", "props": {"class": "ml-2 text-caption text-medium-emphasis"},
                         "text": "无需重试"},
                    ]},
                ]}

    color = C_ERROR if len(failed) > 0 else "grey"
    recent_failed = list(reversed(failed[-3:]))
    list_items = []
    for f in recent_failed:
        reason = f.get("reason", "") or ""
        list_items.append({"component": "div", "props": {"class": "py-1"}, "content": [
            {"component": "div", "props": {"class": "d-flex align-center"}, "content": [
                _icon("mdi-alert", color=C_ERROR, size="x-small", extra_class="mr-2"),
                {"component": "span",
                 "props": {"class": "text-caption text-truncate flex-grow-1"},
                 "text": f.get("title", "?")},
            ]},
            # v1.3.2: 失败原因不截断到 30 字符，最多 100 + tooltip
            {"component": "div", "props": {"class": "ml-5 mt-1 text-caption",
                                           "style": {"color": C_ERROR, "opacity": 0.85}},
             "text": f"原因：{reason[:100]}{'…' if len(reason) > 100 else ''}",
             "title": reason} if reason else None,
        ]})

    content_blocks = [
        {"component": "VCardText", "props": {"class": "py-2 px-4 d-flex align-center justify-space-between"},
         "content": [
             {"component": "div", "props": {"class": "d-flex align-center"}, "content": [
                 _icon("mdi-alert-circle", color=color),
                 {"component": "span",
                  "props": {"class": "text-body-2 font-weight-medium text-high-emphasis"},
                  "text": f"失败任务：{len(failed)}"},
             ]},
             # v1.2.9: 重试按钮 - 用 tonal 等级视觉降权
             {"component": "VBtn",
              "props": {"color": C_ERROR, "variant": "tonal", "size": "small",
                        "rounded": "lg", "prepend_icon": "mdi-refresh",
                        "class": "text-none",
                        "disabled": is_running},
              "text": "重试",
              "events": {"click": {"api": "plugin/EmbyPeopleLocalize/retry_failed", "method": "POST"}}},
         ]},
    ]
    if list_items:
        content_blocks.append(
            {"component": "VCardText", "props": {"class": "px-4 pt-0 pb-3"}, "content": list_items})

    return {"component": "VCard", "props": {"class": "mb-3 rounded-lg", "variant": "outlined",
                                            "style": {"backgroundColor": CARD_BG,
                                                      "border": f"1px solid {CARD_BORDER}",
                                                      "borderLeft": f"4px solid {color}",
                                                      "boxShadow": CARD_SHADOW}},
            "content": content_blocks}


def _build_history_list(plugin) -> dict:
    """v1.2.9: 保留完整历史列表（精简版 - 只显示更多条）"""
    history = getattr(plugin, "_history", []) or []
    if not history:
        return {"component": "VCard", "props": {"class": "mb-3 rounded-lg text-center pa-4", "variant": "outlined",
                                                "style": {"backgroundColor": CARD_BG,
                                                          "border": f"1px solid {CARD_BORDER}",
                                                          "boxShadow": CARD_SHADOW}},
                "content": [{"component": "div", "props": {"class": "text-medium-emphasis"},
                             "text": "暂无翻译历史记录"}]}

    # 按系列和季分组聚合
    series_data = {}
    for h in history:
        title = h.get("title", "未知作品") or "未知作品"
        item_type = h.get("item_type", "")
        stored_series = h.get("series_name", "")
        stored_season = h.get("season_num")
        stored_episode = h.get("episode_num")
        series_name = stored_series or title
        season_num = stored_season
        episode_num = stored_episode
        if season_num is None or episode_num is None:
            import re
            m = re.match(r'^(.+?)\s+S(\d{2})E(\d{2})$', title)
            if m:
                series_name = stored_series or m.group(1).strip()
                season_num = season_num if season_num is not None else int(m.group(2))
                episode_num = episode_num if episode_num is not None else int(m.group(3))

        if item_type == "Episode" and season_num is not None and episode_num is not None:
            key = f"{series_name}||S{season_num}"
            if key not in series_data:
                series_data[key] = {
                    "type": "season", "series": series_name, "season": season_num,
                    "episodes": {}, "total_trans": 0,
                    "success_count": 0, "fail_count": 0, "skipped_count": 0,
                    "last_time": h.get("time", ""), "library": h.get("library", ""),
                    "year": h.get("year", ""),
                }
            sd = series_data[key]
            sd["episodes"][episode_num] = h
            sd["total_trans"] += h.get("n_trans", 0)
            status = h.get("status", "")
            if status in ("成功", "ok"):
                sd["success_count"] += 1
            elif "失败" in status:
                sd["fail_count"] += 1
            else:
                sd["skipped_count"] += 1
            sd["last_time"] = h.get("time", "")
        else:
            key = f"movie||{title}"
            if key not in series_data:
                series_data[key] = {"type": "movie", "title": title, "item": h}

    list_items = []
    for key, data in list(series_data.items())[:50]:
        if data["type"] == "movie":
            h = data["item"]
            status = h.get("status", "")
            status_color = C_SUCCESS if status in ("成功", "ok") else (C_ERROR if "失败" in status else "grey")
            list_items.append({"component": "VListItem", "props": {"class": "px-0 py-1",
                                                                    "style": {"borderBottom": "1px solid rgba(128,128,128,0.12)"}},
                               "content": [{"component": "VRow", "props": {"dense": True, "align": "center"}, "content": [
                                   _col(12, [
                                       {"component": "div",
                                        "props": {"class": "text-body-2 font-weight-medium text-high-emphasis text-truncate"},
                                        "text": data["title"]},
                                       {"component": "div",
                                        "props": {"class": "text-caption text-medium-emphasis text-truncate"},
                                        "text": f"{h.get('time', '')} · {h.get('library', '')}"},
                                   ], sm=6),
                                   _col(4, [{"component": "VChip",
                                             "props": {"color": status_color, "size": "x-small",
                                                       "variant": "tonal", "label": True},
                                             "text": status or "—"}], sm=2),
                                   _col(4, [{"component": "div",
                                             "props": {"class": "text-caption text-medium-emphasis"},
                                             "text": f"翻译 {h.get('n_trans', 0)} 条"}], sm=2),
                                   _col(3, [_icon("mdi-movie", color=C_PRIMARY, extra_class="")], sm=1),
                               ]}]})
        else:
            season_num = data["season"]
            ep_nums = sorted(data["episodes"].keys())
            success_color = C_SUCCESS if data["success_count"] > 0 else "grey"
            fail_color = C_ERROR if data["fail_count"] > 0 else "grey"
            if ep_nums:
                if min(ep_nums) == max(ep_nums):
                    ep_display = f"第{min(ep_nums)}集"
                else:
                    ep_display = f"第{min(ep_nums)}-{max(ep_nums)}集"
                series_display = f"{data['series']} 第{season_num}季 {ep_display}"
            else:
                series_display = f"{data['series']} 第{season_num}季"
            list_items.append({"component": "VListItem", "props": {"class": "px-0 py-1",
                                                                    "style": {"borderBottom": "1px solid rgba(128,128,128,0.12)"}},
                               "content": [{"component": "VRow", "props": {"dense": True, "align": "center"}, "content": [
                                   _col(12, [
                                       {"component": "div",
                                        "props": {"class": "text-body-2 font-weight-medium text-high-emphasis text-truncate"},
                                        "text": series_display},
                                       {"component": "div",
                                        "props": {"class": "text-caption text-medium-emphasis text-truncate"},
                                        "text": f"{data['last_time']} · {data.get('library', '')}"},
                                   ], sm=7),
                                   _col(3, [{"component": "VChip",
                                             "props": {"color": success_color, "size": "x-small",
                                                       "variant": "tonal", "label": True},
                                             "text": f"成功 {data['success_count']}"}], sm=2),
                                   _col(3, [{"component": "VChip",
                                             "props": {"color": fail_color, "size": "x-small",
                                                       "variant": "tonal", "label": True},
                                             "text": f"失败 {data['fail_count']}"}], sm=2),
                                   _col(3, [{"component": "div",
                                             "props": {"class": "d-flex align-center ga-1"},
                                             "content": [
                                                 _icon("mdi-television-classic", color=C_INFO, extra_class=""),
                                                 {"component": "span",
                                                  "props": {"class": "text-caption text-medium-emphasis"},
                                                  "text": f"{len(ep_nums)} 集"},
                                             ]}], sm=1),
                               ]}]})

    return {"component": "VCard", "props": {"class": "mb-3 rounded-lg", "variant": "outlined",
                                            "style": {"backgroundColor": CARD_BG,
                                                      "border": f"1px solid {CARD_BORDER}",
                                                      "boxShadow": CARD_SHADOW}},
            "content": [
                {"component": "VCardTitle",
                 "props": {"class": "text-subtitle-2 font-weight-bold py-2 px-3 text-high-emphasis d-flex align-center"},
                 "content": [
                     _icon("mdi-history", color=C_PRIMARY, extra_class="mr-2"),
                     {"component": "span", "text": "翻译历史"},
                 ]},
                {"component": "VDivider", "props": {"style": {"opacity": 0.3}}},
                {"component": "VCardText",
                 "props": {"class": "px-3 pt-2 pb-2", "style": {"maxHeight": "380px", "overflowY": "auto"}},
                 "content": [{"component": "VList", "props": {"class": "pa-0 bg-transparent"},
                              "content": list_items}]},
            ]}


def build_page(plugin) -> List[dict]:
    """v1.2.9: 首页 - header / 状态 / 统计 / 失败中心 / Webhook / 缓存 / 最近活动 / 历史
    通过 _build_scan_status() 获取统一状态对象

    v1.3.2: 防御 - plugin 为 None 时返回空页面（避免 'NoneType has no attribute X' 崩溃）
    """
    if plugin is None:
        logger.warning("build_page: plugin is None，返回空页面")
        return [{"component": "VAlert", "props": {"type": "warning", "variant": "tonal"},
                 "text": "插件实例不可用，请刷新页面或重新加载插件"}]

    scan_status = plugin._build_scan_status() if hasattr(plugin, "_build_scan_status") else {}

    page_content = [
        _build_header(plugin),
        _build_status_bar(scan_status, plugin=plugin),  # v1.3.2: 传 plugin 给 progress
        _build_stat_row(plugin),
        _build_failed_card(plugin),
        _row([
            _col(12, [_build_webhook_card(plugin)], md=7),
            _col(12, [_build_cache_card(plugin)], md=5),
        ], classes="mb-0"),
        _row([
            _col(12, [_build_recent_activity_card(plugin)], md=6),
            _col(12, [_build_history_list(plugin)], md=6),
        ], classes="mb-0"),
    ]
    page_wrapper = {
        "component": "VCard",
        "props": {"class": "pa-3 rounded-xl", "variant": "outlined",
                  "style": {"backgroundColor": "rgba(255, 255, 255, 0.02)",
                            "border": f"1px solid {CARD_BORDER}",
                            "boxShadow": "0 2px 8px rgba(0,0,0,0.25)"}},
        "content": page_content,
    }
    return [{"component": "div", "props": {"class": "pa-3"}, "content": [page_wrapper]}]
