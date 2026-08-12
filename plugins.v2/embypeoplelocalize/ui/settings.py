"""
ui/settings.py - 设置页
v1.2.9: 拆出 - 基础设置 / LLM 连接 / 范围 / 提示词 / 高级 / Webhook
"""
from app.core.config import settings as _mp_settings

from .common import (
    _row, _col, _section, _switch, _text_field, _select, _textarea,
    _btn, _chip, _alert, _confirm_danger_zone,
    C_PRIMARY, C_INFO, C_SUCCESS, C_WARNING, C_ERROR,
)


def build_form(lib_options, plugin, invalid_libraries=None) -> list:
    """v1.2.9: 设置页表单 - 拆出独立函数
    三个等级按钮：
    - 主操作 (开始扫描): elevated + primary
    - 普通 (保存): outlined
    - 危险 (清空缓存): tonal + error
    """
    invalid_libraries = invalid_libraries or []
    llm_ready = getattr(plugin, "_llm", None) is not None
    llm_model = getattr(plugin._llm, "model", "") if llm_ready else ""
    # v1.3.0: 统一从 _scan_status 读取"运行中"状态，杜绝 _is_running 未恢复导致按钮卡住的隐患
    scan_status = plugin._build_scan_status() if hasattr(plugin, "_build_scan_status") else {}
    is_scanning = bool(scan_status.get("running", False))

    # ────────── 基础设置 ──────────
    basic_rows = [
        _row([
            _col(12, [_switch("enabled", "启用插件", "开启后入库时自动翻译演职人员")], sm=6),
            _col(12, [_switch("run_scan", "立即扫描（保存后执行）", "打开开关后点下方保存按钮，插件自动开始扫描")], sm=6),
        ]),
        _row([
            _col(12, [_switch("run_clear_cache", "清除缓存并重扫", "清空所有已处理记录和缓存，然后立即重新扫描全部条目")], sm=6),
            _col(12, [_switch("run_lock_cast", "批量补锁定旧条目", "为已翻译但未锁定的旧条目补充 Cast 锁定")], sm=6),
        ]),
        _row([
            _col(12, [_switch("notify_on_complete", "扫描完成后发送通知", "每次扫描完成推送通知，包含翻译统计和缓存命中率")], sm=6),
            _col(12, [{"component": "div", "props": {"class": "text-caption text-medium-emphasis"},
                        "text": "「立即扫描」「清除缓存」「补锁定」均为一次性触发，执行完成后自动复位。"}], sm=6),
        ]),
        _row([
            _col(12, [_select("libraries", "选择媒体库（多选，留空 = 全部）", lib_options,
                               "选择要扫描的媒体库，支持跨服务器；留空则扫描所有服务器所有库")]),
        ]),
        _row([
            _col(12, [_text_field("delay", "批间延迟（秒）", "2", "每次请求间隔，避免触发限流", "number")], sm=6),
        ]),
    ]
    if is_scanning:
        # v1.2.9: 停止扫描按钮 - tonal 等级
        basic_rows.append(_row([_col(12, [_btn("⏹ 停止扫描", C_ERROR,
                                                 "plugin/EmbyPeopleLocalize/stop",
                                                 variant="tonal", icon="mdi-stop-circle")])]))
    # v1.3.0: 危险操作二次确认 - 清空缓存 VDialog
    basic_rows.append(_row([_col(12, [_confirm_danger_zone(is_scanning)])]))
    if invalid_libraries:
        basic_rows.append(_row([_col(12, [_alert(f"已自动移除失效的媒体库配置：{', '.join(invalid_libraries)}。")])]))
    if not lib_options:
        basic_rows.append(_row([_col(12, [_alert("未获取到任何媒体库，请检查 Emby 服务器是否在线、API Key 是否有效。", "error")])]))
    card_basic = _section("基础设置", C_PRIMARY, basic_rows, icon="mdi-cog-outline")

    # ────────── LLM 连接 ──────────
    plugin_base_url = getattr(plugin, "_llm_base_url", "") or ""
    plugin_api_key = getattr(plugin, "_llm_api_key", "") or ""
    plugin_model = getattr(plugin, "_llm_model", "") or ""
    mp_base_url = getattr(_mp_settings, "LLM_BASE_URL", "") or ""
    mp_api_key = getattr(_mp_settings, "LLM_API_KEY", "") or ""
    mp_model = getattr(_mp_settings, "LLM_MODEL", "") or ""
    using_plugin_any = bool(plugin_base_url or plugin_api_key or plugin_model)
    current_llm_model = llm_model or plugin_model or mp_model or "未配置"
    effective_source = "插件独立配置" if using_plugin_any else "MoviePilot 系统配置"

    def _src_label(plugin_val, mp_val, field_name):
        if plugin_val: return f"{field_name}：插件自定义"
        elif mp_val: return f"{field_name}：系统默认"
        else: return f"{field_name}：未配置"

    card_llm = _section("大模型连接", C_INFO, [
        _row([_col(12, [{"component": "div", "props": {"class": "d-flex align-center ga-2 mb-2 flex-wrap"}, "content": [
            {"component": "span", "props": {"class": "text-body-2 font-weight-medium text-high-emphasis"}, "text": "当前状态："},
            _chip("已就绪", "success", icon="mdi-check-circle") if llm_ready else _chip("未配置", "warning", icon="mdi-alert"),
            _chip("插件独立 LLM", "info", icon="mdi-cog-outline") if using_plugin_any else _chip("MP 系统 LLM", "success", icon="mdi-server"),
            {"component": "span", "props": {"class": "text-caption text-medium-emphasis ml-2"}, "text": f"模型：{current_llm_model}"},
        ]}])]),
        _row([
            _col(12, [_text_field("llm_base_url", "API 地址", "https://api.example.com/v1",
                                   _src_label(plugin_base_url, mp_base_url, "API 地址"))]),
        ]),
        _row([
            _col(12, [_text_field("llm_api_key", "API Key", "sk-xxx",
                                   _src_label(plugin_api_key, mp_api_key, "API Key"), "password")], sm=6),
            _col(12, [_text_field("llm_model", "模型名称", "deepseek-ai/DeepSeek-V4-Flash",
                                   _src_label(plugin_model, mp_model, "模型"))], sm=4),
            _col(12, [_text_field("llm_timeout", "超时（秒）", "120", "LLM 请求超时", "number")], sm=2),
        ]),
        _row([
            _col(8, [{"component": "div", "props": {"class": "text-caption text-medium-emphasis"},
                       "text": f"留空 = 使用 {effective_source}（避免硬编码，提升可维护性）"}], sm=9),
            # v1.2.9: 刷新 LLM 按钮 - 主操作
            _col(4, [_btn("🔄 刷新 LLM", C_PRIMARY,
                            "plugin/EmbyPeopleLocalize/refresh_llm",
                            variant="elevated", block=False, icon="mdi-refresh")], sm=3),
        ]),
    ], icon="mdi-robot")

    # ────────── 翻译范围 ──────────
    translate_all = getattr(plugin, "_translate_all", False)
    card_scope = _section("翻译范围", C_SUCCESS, [
        _row([_col(12, [_switch("translate_all", "全部翻译",
                                "开启后忽略下方角色类型，所有职位的人名+角色名都翻译（会与下方各角色类型开关互斥）")])]),
        _row([
            _col(12, [_switch("translate_actor", "演员 Actor", "电影/剧集的主演", disabled=translate_all)], sm=6),
            _col(12, [_switch("translate_director", "导演 Director", disabled=translate_all)], sm=6),
        ]),
        _row([
            _col(12, [_switch("translate_writer", "编剧 Writer", disabled=translate_all)], sm=6),
            _col(12, [_switch("translate_producer", "制片人 Producer", disabled=translate_all)], sm=6),
        ]),
        _row([
            _col(12, [_switch("translate_role", "翻译角色名",
                                "翻译人物饰演的具体角色名（如\"钢铁侠\"→中文），不影响已有人名")]),
        ]),
        _row([
            _col(12, [_switch("overwrite_chinese", "重译已有中文名",
                                "对已经是中文的人名/角色名强制重新翻译（适合换了更准确的译名时使用）")]),
        ]),
        _row([
            _col(12, [_text_field("max_people_per_title", "单作品最大人数", "10",
                                   "每个作品最多翻译多少个人物，超出截断", "number")], sm=6),
            _col(12, [_text_field("max_people_per_batch", "单批翻译条数", "5",
                                   "每批 LLM 翻译多少条；越大越快但 token 越多", "number")], sm=6),
        ]),
    ], icon="mdi-account-multiple-outline")

    # ────────── 提示词 ──────────
    default_prompt = "你是影视翻译专家。将以下词条翻译成简体中文。\ncontext: {\"title\": {title_json}, \"year\": {year_json}}\nterms: {terms_json}\n输出: JSON 对象，键为原文，值为译文。无法翻译保留原文。只输出 JSON，不要 markdown。"
    current_prompt = getattr(plugin, "_prompt_template", "") or default_prompt
    card_prompt = _section("提示词模板", C_WARNING, [
        _row([_col(12, [_textarea("prompt_template", "提示词", default_prompt,
                                   "支持占位符 {title_json} / {year_json} / {terms_json}，留空使用默认模板", rows=8)])]),
        _row([_col(12, [{"component": "div", "props": {"class": "text-caption text-medium-emphasis"},
                          "text": f"当前长度：{len(current_prompt)} 字符。修改后会与 LLM 配置一起保存。"}])]),
    ], icon="mdi-message-text-outline")

    # ────────── 高级 ──────────
    card_advanced = _section("高级选项", C_WARNING, [
        _row([
            _col(12, [_switch("lock_cast", "翻译后立即锁定 Cast",
                                "在 Emby 中锁定该作品的演职人员列表，避免重新刮削时覆盖中文名")]),
        ]),
    ], icon="mdi-lock-outline")

    # ────────── Webhook ──────────
    webhook_delay = getattr(plugin, "_webhook_delay", 60) or 60
    card_webhook = _section("Webhook 入库触发", C_INFO, [
        _row([
            _col(12, [_text_field("webhook_delay", "入库延迟（秒）", "60",
                                   "Emby 入库后等待多少秒再开始翻译，给元数据刮削留时间", "number")]),
        ]),
        _row([_col(12, [{"component": "div", "props": {"class": "text-caption text-medium-emphasis"},
                          "text": f"在 Emby Webhook 中配置：'http://<MoviePilot地址>/api/webhook?token=<你的Token>'，" \
                                  f"事件选 Library - New 或类似。延迟默认 {webhook_delay} 秒。"}])]),
    ], icon="mdi-webhook")

    # ────────── 保存按钮（v1.2.9: 主操作 - elevated 蓝紫）──────────
    save_row = _row([_col(12, [
        _btn("保存设置", C_PRIMARY, "plugin/EmbyPeopleLocalize/save_config",
             variant="elevated", icon="mdi-content-save"),
    ])])

    form = [card_basic, card_llm, card_scope, card_prompt, card_advanced, card_webhook, save_row]
    return form
