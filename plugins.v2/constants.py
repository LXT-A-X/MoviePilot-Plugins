"""
constants.py - Emby 演职人员中文化 常量配置
"""

# ========== 默认提示词 ==========
DEFAULT_PROMPT = """你是一位世界级的影视专家，扮演一个只返回 JSON 的 API。
任务：将外语/拼音/日文演员名和角色名翻译成简体中文。

输入格式：
context: {"title": 作品名, "year": 年份}
terms: 待翻译字符串列表

策略：
1. 利用 title + year 确定具体作品，找官方/最公认的中文译名
2. 拼音/英文/日文 → 汉字
3. 目标语言永远是简体中文
4. 无法翻译则保留原文

输出格式（强制 JSON，禁止 markdown）：
{"原文1": "译文1", "原文2": "译文2"}
"""

# ========== Emby 写入时剔除的只读字段 ==========
# ⚠️ 注意：LockedFields 和 People 不能在这里，否则 update_people 设的值会被删掉
EMBY_STRIP_FIELDS = frozenset([
    "Id", "Key", "Guid", "ExternalUrls", "MediaStreams", "MediaSources",
    "PlaylistItemId", "PlaylistIndex", "PlaylistLength",
    "ImageTags", "BackdropImageTags", "ScreenshotImageTags", "ParentId",
    "Type", "MediaType",
    "Path", "OriginalTitle", "PremiereDate",
    "CriticRating", "CommunityRating", "RunTimeTicks",
    "PlayAccess", "ProductionYear",
])

# ========== 扫描相关常量 ==========
PAGE_SIZE = 50                # 每次分页拉取条目数
HISTORY_MAX = 200             # 历史记录最大条数
CACHE_SAVE_INTERVAL = 50     # 每处理多少个条目保存一次缓存
REQUEST_TIMEOUT = (5, 10)    # 连接超时5秒，读取超时10秒

# ========== 支持的演职人员类型 ==========
PERSON_TYPES = {
    "Actor":       "演员",
    "Director":    "导演",
    "Writer":      "编剧",
    "Producer":    "制作人",
    "VoiceActor":  "声优",
    "GuestStar":   "客串",
    "Composer":    "作曲",
    "Cinematographer": "摄影",
    "Editor":      "剪辑",
}
