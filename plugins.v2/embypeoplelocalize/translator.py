"""
translator.py - 翻译引擎协调层
v0.9.0 重构版 - 统一翻译逻辑，简化缓存管理
"""
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from app.log import logger

try:
    import zhconv
    HAS_ZHCONV = True
except ImportError:
    HAS_ZHCONV = False


class PeopleTranslator:
    """演职人员翻译引擎"""

    def __init__(self, llm_client, name_cache: Optional[Dict[str, Dict[str, str]]] = None,
                 role_cache: Optional[Dict[str, Dict[str, str]]] = None,
                 state_lock: Optional[threading.Lock] = None,
                 plugin=None):
        self.llm = llm_client
        # v1.2.4: 修复缓存与插件状态脱离问题
        # 当传入 None 时直接初始化为空字典，但当传入空字典时也直接引用
        # 不再在 | 运算中产生新字典对象，确保 Translator 与插件共享同一份缓存引用
        if name_cache is None:
            self._name_cache = {}
        else:
            self._name_cache = name_cache
        if role_cache is None:
            self._role_cache = {}
        else:
            self._role_cache = role_cache
        # v1.2.9: 默认用 RLock 替代 Lock - 防止嵌套调用 (get -> set) 死锁
        # 外部传入 Lock/RLock 都兼容，None 时统一用 RLock
        if state_lock is None:
            self._lock = threading.RLock()
        else:
            # 外部传入的锁直接用 - 调用方负责线程安全
            self._lock = state_lock
        self.plugin = plugin

    # ─────────────────────────────────────
    # 缓存管理
    # ─────────────────────────────────────
    # v1.2.8: 默认语言 - 简体
    DEFAULT_LANG = "zh-cn"

    def _get_lang_cache(self, cache_dict: dict, lang: str = None) -> dict:
        """v1.2.8: 获取指定语言的缓存子字典
        缓存结构：{"zh-cn": {...}, "zh-tw": {...}, "default": {...}}
        - 优先返回指定语言子字典
        - 不存在则自动创建空字典
        - 兼容旧的 "default" 顶层结构
        """
        lang = lang or self.DEFAULT_LANG
        if lang not in cache_dict:
            cache_dict[lang] = {}
        return cache_dict[lang]

    def get_cached_name(self, name: str, lang: str = None) -> Optional[str]:
        """查人名缓存（v1.2.8: 支持语言层级）"""
        with self._lock:
            # 优先查目标语言
            lang = lang or self.DEFAULT_LANG
            if lang in self._name_cache and name in self._name_cache[lang]:
                return self._name_cache[lang][name]
            # 兜底：兼容旧 default 缓存
            for fallback_lang, lang_cache in self._name_cache.items():
                if name in lang_cache:
                    return lang_cache[name]
        return None

    def get_cached_role(self, role: str, lang: str = None) -> Optional[str]:
        """查角色缓存（v1.2.8: 支持语言层级）"""
        with self._lock:
            lang = lang or self.DEFAULT_LANG
            if lang in self._role_cache and role in self._role_cache[lang]:
                return self._role_cache[lang][role]
            # 兜底：兼容旧 default 缓存
            for fallback_lang, lang_cache in self._role_cache.items():
                if role in lang_cache:
                    return lang_cache[role]
        return None

    def set_cached_name(self, name: str, translated: str, lang: str = None):
        """写人名缓存（v1.2.8: 按语言隔离，避免简繁冲突）"""
        with self._lock:
            lang = lang or self.DEFAULT_LANG
            if lang not in self._name_cache:
                self._name_cache[lang] = {}
            self._name_cache[lang][name] = translated

    def set_cached_role(self, role: str, translated: str, lang: str = None):
        """写角色缓存（v1.2.8: 按语言隔离）"""
        with self._lock:
            lang = lang or self.DEFAULT_LANG
            if lang not in self._role_cache:
                self._role_cache[lang] = {}
            self._role_cache[lang][role] = translated

    def name_cache_size(self) -> int:
        with self._lock:
            return sum(len(v) for v in self._name_cache.values())

    def role_cache_size(self) -> int:
        with self._lock:
            return sum(len(v) for v in self._role_cache.values())

    # ─────────────────────────────────────
    # 繁简转换
    # ─────────────────────────────────────
    @staticmethod
    def contains_chinese(text: str) -> bool:
        """检测是否包含中文"""
        for c in text:
            cp = ord(c)
            if 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF:
                return True
        return False

    def try_zhconv(self, text: str) -> Optional[str]:
        """繁简转换，成功返回简体，失败返回 None"""
        if not HAS_ZHCONV or not self.contains_chinese(text):
            return None
        try:
            simplified = zhconv.convert(text, 'zh-cn')
            if simplified != text:
                return simplified
        except Exception:
            pass
        return None

    # ─────────────────────────────────────
    # 核心翻译方法
    # ─────────────────────────────────────
    def translate_batch(self, title: str, year: Any,
                        name_terms: List[str], role_terms: List[str],
                        batch_size: int = 5) -> Tuple[Dict[str, str], Dict[str, str]]:
        """
        批量翻译人名和角色名
        返回: (人名翻译映射, 角色翻译映射)
        """
        name_translations = {}
        role_translations = {}

        # 1. 处理人名
        name_remaining = []
        for name in name_terms:
            cached = self.get_cached_name(name)
            if cached:
                name_translations[name] = cached
                continue
            simplified = self.try_zhconv(name)
            if simplified:
                name_translations[name] = simplified
                self.set_cached_name(name, simplified)
                continue
            name_remaining.append(name)

        # 2. 处理角色名
        role_remaining = []
        for role in role_terms:
            cached = self.get_cached_role(role)
            if cached:
                role_translations[role] = cached
                continue
            simplified = self.try_zhconv(role)
            if simplified:
                role_translations[role] = simplified
                self.set_cached_role(role, simplified)
                continue
            role_remaining.append(role)

        # 3. LLM 翻译剩余文本（合并去重）
        # v1.2.7: 使用 dict.fromkeys 保留输入顺序
        # 避免 set() 打乱顺序导致 LLM 上下文理解下降
        all_remaining = list(dict.fromkeys(name_remaining + role_remaining))
        if not all_remaining or not self.llm:
            return name_translations, role_translations

        for i in range(0, len(all_remaining), batch_size):
            batch = all_remaining[i:i + batch_size]
            try:
                result = self.llm.translate_terms(title, year, batch)
                if isinstance(result, dict):
                    for orig, trans in result.items():
                        if trans and trans != orig:
                            if orig in name_remaining:
                                name_translations[orig] = trans
                                self.set_cached_name(orig, trans)
                            if orig in role_remaining:
                                role_translations[orig] = trans
                                self.set_cached_role(orig, trans)
                elif result is None:
                    # v1.2.4: LLM 返回 None（API 错误/超时/JSON 解析失败）时显式标记
                    logger.warning(f"[Translator] LLM 返回 None，跳过该批次 (size={len(batch)})")
                else:
                    logger.warning(f"[Translator] LLM 返回了非字典类型: {type(result).__name__}")
            except Exception as e:
                # v1.2.4: 分类错误，便于排查
                err_type = type(e).__name__
                err_msg = str(e)
                if "timeout" in err_msg.lower() or "timed out" in err_msg.lower():
                    tag = "[LLM_TIMEOUT]"
                elif "apikey" in err_msg.lower() or "auth" in err_msg.lower() or "401" in err_msg or "403" in err_msg:
                    tag = "[LLM_AUTH_ERROR]"
                elif "json" in err_msg.lower() or "parse" in err_msg.lower():
                    tag = "[JSON_PARSE_ERROR]"
                elif "connection" in err_msg.lower() or "connect" in err_msg.lower():
                    tag = "[LLM_CONNECTION_ERROR]"
                else:
                    tag = "[LLM_ERROR]"
                logger.error(f"[Translator] {tag} 批次翻译失败 ({err_type}): {e}")
            time.sleep(0.3)

        return name_translations, role_translations

    def apply_translations(self, people: List[dict],
                           name_translations: Dict[str, str],
                           role_translations: Dict[str, str]) -> List[dict]:
        """将翻译结果应用到 people 列表"""
        new_people = []
        for p in people:
            np = dict(p)
            cur_name = np.get("Name", "")
            if cur_name in name_translations:
                np["Name"] = name_translations[cur_name]
            cur_role = np.get("Role", "")
            if cur_role and cur_role in role_translations:
                np["Role"] = role_translations[cur_role]
            new_people.append(np)
        return new_people
