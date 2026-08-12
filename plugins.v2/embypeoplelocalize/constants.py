"""
constants.py - Emby 演职人员中文化 常量配置
v0.9.0 重构版
"""

DEFAULT_PROMPT = """你是一位世界级的影视专家，扮演一个只返回 JSON 的 API。
任务：将外语/罗马音/日文演员名和角色名翻译成简体中文。

context: {"title": {title_json}, "year": {year_json}}
terms: {terms_json}

策略：
1. 利用 title + year 确定具体作品，找官方/最公认的中文译名
2. 拼音/英文/日文 → 汉字
3. 目标语言永远是简体中文
4. 无法翻译则保留原文

输出格式（强制 JSON，禁止 markdown）：
{"原文1": "译文1", "原文2": "译文2"}
"""

EMBY_STRIP_FIELDS = frozenset([
    "Id", "Key", "Guid", "ExternalUrls", "MediaStreams", "MediaSources",
    "PlaylistItemId", "PlaylistIndex", "PlaylistLength",
    "ImageTags", "BackdropImageTags", "ScreenshotImageTags", "ParentId",
    "Type", "MediaType",
    "Path", "OriginalTitle", "PremiereDate",
    "CriticRating", "CommunityRating", "RunTimeTicks",
    "PlayAccess", "ProductionYear",
])

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
CFG_TRANSLATE_ROLE = "translate_role"
CFG_TRANSLATE_ACTOR = "translate_actor"
CFG_TRANSLATE_DIRECTOR = "translate_director"
CFG_TRANSLATE_WRITER = "translate_writer"
CFG_TRANSLATE_PRODUCER = "translate_producer"
CFG_MAX_PEOPLE_PER_TITLE = "max_people_per_title"
CFG_MAX_PEOPLE_PER_BATCH = "max_people_per_batch"
CFG_OVERWRITE_CHINESE = "overwrite_chinese"
CFG_DELAY = "delay"
CFG_LOCK_CAST = "lock_cast"
CFG_WEBHOOK_DELAY = "webhook_delay"
CFG_NOTIFY_ON_COMPLETE = "notify_on_complete"
CFG_SEARCH_KEYWORD = "history_search_keyword"
CFG_LLM_BASE_URL = "llm_base_url"
CFG_LLM_API_KEY = "llm_api_key"
CFG_LLM_MODEL = "llm_model"
CFG_LLM_TIMEOUT = "llm_timeout"
CFG_USE_PROXY = "use_proxy"

# 运行时触发键
CFG_RUN_SCAN = "run_scan"
CFG_RUN_LOCK_CAST = "run_lock_cast"
CFG_RUN_CLEAR_CACHE = "run_clear_cache"
CFG_ONCE = "onlyonce"

# 默认值
DEFAULT_DELAY = 2
DEFAULT_WEBHOOK_DELAY = 60
DEFAULT_MAX_PEOPLE = 20  # v1.3.1: 10→20，剧集演员较多
DEFAULT_BATCH_SIZE = 5
DEFAULT_LLM_TIMEOUT = 120
DEFAULT_USE_PROXY = False  # v1.3.1: 默认不读系统代理
MAX_HISTORY = 200
