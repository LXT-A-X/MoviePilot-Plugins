"""
constants.py - Emby 演职人员中文化 常量配置
重构版
"""

import json

# v4.6.109（LIB-017）：旧版默认提示词 —— 仅用于「用户从未改过时自动升级」的比对，
# 不要再用它做默认值。它的第 6 条「无法确认或无需翻译时保留原文」被模型当成逃生口：
# 纯假名（楠木ともり）/罗马音（SOUNGDOK）/拉丁名（Lia）全部原样返回 →
# 插件记为「无需翻译」→ 池里永远显示「🔴 待翻译」，且每次重启都要重发一遍。
DEFAULT_PROMPT_LEGACY = """你是一位专业的影视人名翻译专家，只返回 JSON，不输出任何其它内容。

任务：把影视条目中的演员名、角色名翻译成最符合简体中文观众认知的译名。

context: {"title": {title_json}, "year": {year_json}}
terms: {terms_json}

翻译规则：
1. 利用作品名与年份确定具体作品，优先采用中文圈公认/官方译名；记不准时不要强行套用。
2. 人名：日文/罗马音/英文/韩文等 → 简体中文；已有公认译名（如长泽雅美、新垣结衣等）必须使用该译名，不要逐字直译。
3. 角色名：按中文圈公认译名处理。
4. 本身就是简体中文的词条原样保留。
5. 无法确认公认译名时：英文/罗马音按普通话发音音译（如 Tom Hanks → 汤姆·汉克斯），保持稳定一致，不要生造译名。
6. 无法确认或无需翻译时保留原文，不编造。
7. 一律使用简体中文，禁用繁体、拼音、假名、罗马音。

输出格式（严格 JSON：键=原文，值=译文，禁止 markdown、注释、额外文字）：
{"原文1": "译文1", "原文2": "译文2"}
"""

DEFAULT_PROMPT = """你是一位专业的影视人名翻译专家，只返回 JSON，不输出任何其它内容。

任务：把影视条目中的演员名、角色名翻译成最符合简体中文观众认知的译名。

context: {"title": {title_json}, "year": {year_json}}
terms: {terms_json}

翻译规则：
1. 利用作品名与年份确定具体作品，优先采用中文圈公认/官方译名。
2. 人名：日文（含平假名/片假名）、罗马音、英文、韩文等 → 简体中文；已有公认译名（如长泽雅美、新垣结衣、汤姆·克鲁斯等）必须使用该译名，不要逐字直译。
3. 角色名：按中文圈公认译名处理。
4. **日文假名一律音译**：按日语读音转成简体中文常用汉字，**不得保留假名**（例：ともり → 灯、あげは → 扬羽、マサキ → 正树）。
5. **罗马音 / 英文 / 拉丁字母一律音译**：按该语言的读音音译成简体中文（例：Tom Hanks → 汤姆·汉克斯、Lia → 莉娅、SOUNGDOK → 宋德），保持稳定一致。
6. **记不准公认译名时也必须给出音译，不要原样返回原文、不要编造意译**。
7. 只有「词条本身已经是简体中文」时才原样保留；其余一律给出简体中文译文。
8. 一律使用简体中文，禁用繁体、拼音、假名、罗马音、拉丁字母。

输出格式（严格 JSON：键=原文，值=译文，禁止 markdown、注释、额外文字）：
{"原文1": "译文1", "原文2": "译文2"}
"""

PERSON_TYPE_MAP = {
    "Actor": "演员",
    "Director": "导演",
    "Writer": "编剧",
    "Producer": "制作人",
    "VoiceActor": "声优",
    "GuestStar": "客串",
    "Composer": "作曲",
    "Cinematographer": "摄影",
    "Editor": "剪辑",
}

# 配置键
CFG_ENABLED = "enabled"
CFG_LIBRARIES = "libraries"
CFG_PROMPT_TEMPLATE = "prompt_template"
CFG_TRANSLATE_ALL = "translate_all"
CFG_TRANSLATE_PERSON = "translate_person"
CFG_TRANSLATE_ROLE = "translate_role"
CFG_TRANSLATE_ACTOR = "translate_actor"
CFG_TRANSLATE_DIRECTOR = "translate_director"
CFG_TRANSLATE_WRITER = "translate_writer"
CFG_TRANSLATE_PRODUCER = "translate_producer"
CFG_TRANSLATE_GUEST_STAR = "translate_guest_star"
CFG_ACTOR_LIMIT = "actor_limit"
CFG_GUEST_LIMIT = "guest_limit"        # 客串/配角人数（替代 max_guest_per_episode 语义）
CFG_DIRECTOR_LIMIT = "director_limit"
CFG_WRITER_LIMIT = "writer_limit"      # 编剧/制片人人数
CFG_JA_NAME_POLICY = "ja_name_policy"
CFG_MAX_PEOPLE_PER_BATCH = "max_people_per_batch"
CFG_MAX_GUEST_PER_EPISODE = "max_guest_per_episode"
CFG_ENABLE_AI = "enable_ai"
CFG_MOVIE_ACTOR_LIMIT = "movie_actor_limit"      # 电影 nfo 演员人数
CFG_MOVIE_GUEST_LIMIT = "movie_guest_limit"      # 电影 nfo 客串/配角人数
CFG_MOVIE_DIRECTOR_LIMIT = "movie_director_limit"  # 电影 nfo 导演人数
CFG_MOVIE_WRITER_LIMIT = "movie_writer_limit"    # 电影 nfo 编剧/制片人人数
CFG_TV_ACTOR_LIMIT = "tv_actor_limit"            # 剧 tvshow.nfo 主演人数
CFG_EP_ACTOR_LIMIT = "ep_actor_limit"            # 各集 episode.nfo 演员人数
CFG_TV_GUEST_LIMIT = "tv_guest_limit"            # 剧/集 客串/配角人数
CFG_TV_DIRECTOR_LIMIT = "tv_director_limit"      # 剧/集 导演人数
CFG_TV_WRITER_LIMIT = "tv_writer_limit"          # 剧/集 编剧/制片人人数
CFG_SCHEDULE_ENABLED = "schedule_enabled"
CFG_SCHEDULE_INTERVAL_HOURS = "schedule_interval_hours"
CFG_OVERWRITE_CHINESE = "overwrite_chinese"
CFG_LOCK_CAST = "lock_cast"
CFG_EMBY_NAME_SYNC = "emby_name_sync"
CFG_PROBE_ENABLED = "probe_enabled"                    # 开关（默认关）
CFG_PROBE_INTERVAL_MINUTES = "probe_interval_minutes"  # 间隔（分钟，默认 60，下限 10）
CFG_WEBHOOK_DELAY = "webhook_delay"
CFG_WEBHOOK_ENABLED = "webhook_enabled"
CFG_NOTIFY_ON_COMPLETE = "notify_on_complete"
CFG_SEARCH_KEYWORD = "history_search_keyword"
CFG_LLM_BASE_URL = "llm_base_url"
CFG_LLM_API_KEY = "llm_api_key"
CFG_LLM_MODEL = "llm_model"
CFG_LLM_TIMEOUT = "llm_timeout"
CFG_LLM_MODE = "llm_mode"
CFG_USE_PROXY = "use_proxy"
CFG_LLM_VERIFY_SSL = "llm_verify_ssl"
CFG_TRANSLATE_BATCHING = "translate_batching"
CFG_SCAN_MODE = "scan_mode"
CFG_NFO_ROOTS = "nfo_roots"
CFG_NFO_PATH_MAPPINGS = "nfo_path_mappings"
CFG_NFO_RECURSIVE = "nfo_recursive"
CFG_NFO_INCLUDE_EPISODES = "nfo_include_episodes"
CFG_NFO_BACKUP = "nfo_backup"
CFG_NFO_DRY_RUN = "nfo_dry_run"
CFG_NFO_EPISODE_SYNC = "nfo_episode_sync"
CFG_NFO_EPISODE_OVERWRITE = "nfo_episode_overwrite"
CFG_SYNC_DIRECTION = "sync_direction"
SYNC_DIRECTIONS = ("off", "s2e", "e2s")
CFG_NFO_PREVIEW = "nfo_preview"
CFG_NFO_DEAD_GRACE_HOURS = "nfo_dead_grace_hours"
DEFAULT_NFO_DEAD_GRACE_HOURS = 24
DEFAULT_NFO_BACKUP = True

CFG_POOL_FETCH_SCOPE = "pool_fetch_scope"   # 拉取来源："libraries"=仅已选媒体库（默认）/ "all"=全库 Person
DEFAULT_POOL_FETCH_SCOPE = "libraries"
CFG_POOL_FETCH_TYPES = "pool_fetch_types"   # 人名池「拉取类型」独立配置（v4.6.48）；Person 类型列表
DEFAULT_POOL_FETCH_TYPES = ("Actor",)       # 默认「演员」（勾选 Actor 即同时收 VoiceActor）
CFG_LIMITS_UNIFIED = "limits_unified"       # v4.6.48：人数上限「三套合并为一套」的迁移标记
CFG_POOL_AUTO_TRANSLATE = "pool_auto_translate"
DEFAULT_POOL_AUTO_TRANSLATE = False
CFG_POOL_AUTO_SYNC = "pool_auto_sync"
DEFAULT_POOL_AUTO_SYNC = False
CFG_POOL_KEEP_UNKNOWN = "pool_keep_unknown"
DEFAULT_POOL_KEEP_UNKNOWN = True
CFG_POOL_TRANSLATE_ENABLED = "pool_translation_enabled"
DEFAULT_POOL_TRANSLATE_ENABLED = True
CFG_POOL_TMDB_FILL = "pool_tmdb_fill"
DEFAULT_POOL_TMDB_FILL = True
CFG_POOL_TMDB_CREDITS = "pool_tmdb_credits"
DEFAULT_POOL_TMDB_CREDITS = False

CFG_AUTO_TRANSLATE_WEBHOOK = "auto_translate_webhook"
DEFAULT_AUTO_TRANSLATE_WEBHOOK = False

CFG_AUTO_TRANSLATE_SCAN = "auto_translate_scan"
DEFAULT_AUTO_TRANSLATE_SCAN = False

CFG_LLM_MIN_INTERVAL = "llm_min_interval"
CFG_AUTO_WRITEBACK = "auto_writeback"
DEFAULT_LLM_MIN_INTERVAL = 3.0
CFG_LLM_MAX_RPM = "llm_max_rpm"
DEFAULT_LLM_MAX_RPM = 60
# v4.6.61（P2-3）：TPM 令牌预算（每分钟估算令牌上限，0 = 不限制）—— 减少 429 限流
CFG_LLM_TPM_BUDGET = "llm_tpm_budget"
DEFAULT_LLM_TPM_BUDGET = 0
CFG_LLM_THINKING_OFF = "llm_thinking_off"
DEFAULT_LLM_THINKING_OFF = True
CFG_LLM_THINKING_PARAMS = "llm_thinking_params"
DEFAULT_LLM_THINKING_PARAMS = ""

# 运行时触发键（v3.5.0: 仅保留前端「清空缓存」开关；API 模式 legacy 开关已下线）
CFG_RUN_CLEAR_CACHE = "run_clear_cache"

# 默认值
DEFAULT_WEBHOOK_DELAY = 60
CFG_SERIES_MAX_WORKERS = "series_max_workers"
DEFAULT_SERIES_MAX_WORKERS = 3
# v4.6.90：整剧入库口径 —— 默认**只收新增**（Emby 发「整部剧」事件时，只入库最近加入的集），
# 想一次补齐整部剧（含旧集）时打开本开关，或点「扫描」/对该剧「重新拉取」。
CFG_SERIES_INGEST_ALL = "series_ingest_all"
DEFAULT_SERIES_INGEST_ALL = False
SERIES_NEW_ONLY_LOOKBACK_HOURS = 168   # 「只收新增」的回看窗口：7 天
DEFAULT_WEBHOOK_ENABLED = False
DEFAULT_TRANSLATE_PERSON = True
DEFAULT_NFO_PATH_MAPPINGS = []
DEFAULT_BATCH_SIZE = 30
DEFAULT_LLM_TIMEOUT = 120
DEFAULT_USE_PROXY = False
DEFAULT_LLM_VERIFY_SSL = True


# ============================================================
# ------------------------------------------------------------
# 多个 int(config.get(...)) 若用户手改配置为 "abc" 会在启动阶段直接 ValueError；
# bool("false") 也会得到 True（真值字符串）。统一走下列安全转换：
# 非法/缺失值一律回退默认，数值再夹到 [min, max]，避免"每个配置自己写一套 try"。
# ============================================================
def safe_int(value, default: int = 0, min_value=None, max_value=None) -> int:
    """安全取整：非法/空值回退 default，结果夹在 [min_value, max_value]。"""
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        if isinstance(value, bool):
            n = int(value)
        elif isinstance(value, str):
            n = int(float(value))
        else:
            n = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if min_value is not None and n < min_value:
        n = min_value
    if max_value is not None and n > max_value:
        n = max_value
    return n


def safe_float(value, default: float = 0.0, min_value=None, max_value=None) -> float:
    """安全取浮点：非法/空值回退 default，结果夹在 [min_value, max_value]。"""
    try:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        f = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if min_value is not None and f < min_value:
        f = min_value
    if max_value is not None and f > max_value:
        f = max_value
    return f


def safe_bool(value, default: bool = False) -> bool:
    """安全取布尔：兼容 true/false/1/0/yes/no/on/off 等字符串写法。"""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "1", "yes", "on", "y", "t"):
            return True
        if v in ("false", "0", "no", "off", "n", "f", ""):
            return False
        return default
    return bool(value)


def safe_json_list(value, default=None):
    """安全解析 JSON 列表：兼容 JSON 字符串 / 逗号分隔串 / 已是列表；非法回退 default。"""
    if default is None:
        default = []
    if value is None or value == "":
        return list(default)
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return list(default)
        try:
            parsed = json.loads(s)
        except Exception:
            return [x.strip() for x in s.split(",") if x.strip()]
        if isinstance(parsed, list):
            return list(parsed)
        if isinstance(parsed, tuple):
            return list(parsed)
        return list(default)
    return list(default)
