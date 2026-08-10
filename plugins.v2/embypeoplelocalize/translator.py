"""
translator.py - 翻译引擎协调层
负责：人名缓存管理、繁简转换、调用 LLM 客户端、批量分批
"""
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    import zhconv
    HAS_ZHCONV = True
except ImportError:
    HAS_ZHCONV = False


class PeopleTranslator:
    """演职人员翻译引擎"""

    def __init__(self, llm_client, emby_client=None,
                 name_cache: Optional[Dict[str, Dict[str, str]]] = None,
                 state_lock: Optional[threading.Lock] = None,
                 plugin=None):
        self.llm = llm_client
        self.emby = emby_client
        self._cache = name_cache or {}
        self._lock = state_lock or threading.Lock()
        self.plugin = plugin  # 用于读取 max_people_per_batch 等配置

    # ─────────────────────────────────────
    # 缓存管理
    # ─────────────────────────────────────
    def get_cached(self, name: str) -> Optional[str]:
        """查缓存"""
        with self._lock:
            for lang_cache in self._cache.values():
                if name in lang_cache:
                    return lang_cache[name]
        return None

    def set_cached(self, name: str, translated: str, lang: str = "default"):
        """写缓存"""
        with self._lock:
            if lang not in self._cache:
                self._cache[lang] = {}
            self._cache[lang][name] = translated

    def cache_size(self) -> int:
        with self._lock:
            return sum(len(v) for v in self._cache.values())

    # ─────────────────────────────────────
    # 核心翻译方法
    # ─────────────────────────────────────
    def translate_people(self, title: str, year: Any,
                         people: List[dict]) -> Tuple[List[dict], Dict[str, str]]:
        """
        翻译一批演职人员
        返回：(新 people 列表, {原文: 译文} 映射)
        """
        if not people:
            return [], {}

        # 1. 提取待翻译名字
        names = [p.get("Name", "").strip() for p in people if p.get("Name", "").strip()]
        if not names:
            return people, {}

        # 2. 繁简转换（省 LLM）
        remaining = []
        translations = {}
        for name in names:
            cached = self.get_cached(name)
            if cached:
                translations[name] = cached
                continue
            if HAS_ZHCONV and self._is_traditional(name):
                try:
                    simplified = zhconv.convert(name, 'zh-cn')
                    if simplified != name:
                        translations[name] = simplified
                        self.set_cached(name, simplified)
                        continue
                except Exception:
                    pass
            remaining.append(name)

        # 3. LLM 分批翻译
        batch_size = 5
        if self.plugin:
            batch_size = getattr(self.plugin, '_max_people_per_batch', 5)

        for i in range(0, len(remaining), batch_size):
            batch = remaining[i:i + batch_size]
            try:
                result = self.llm.translate_terms(title, year, batch)
                if isinstance(result, dict):
                    for orig, trans in result.items():
                        if trans and trans != orig:
                            translations[orig] = trans
                            self.set_cached(orig, trans)
            except Exception as e:
                print(f"[Translator] LLM 批次翻译失败: {e}")
            time.sleep(0.5)  # 防止频率过高

        # 4. 构建新 people 列表
        new_people = []
        for p in people:
            name = p.get("Name", "")
            if name in translations:
                np = dict(p)
                np["Name"] = translations[name]
                new_people.append(np)
            else:
                new_people.append(p)

        return new_people, translations

    # ─────────────────────────────────────
    # 辅助
    # ─────────────────────────────────────
    def _is_traditional(self, text: str) -> bool:
        """粗略判断是否为繁体中文"""
        # 繁体特征字
        trad_markers = set("這來個們時會對說後從種這們為從來個是時說會對點樣問題")
        return any(c in trad_markers for c in text)

    def stats(self) -> Dict[str, Any]:
        """缓存统计"""
        with self._lock:
            return {
                "languages": list(self._cache.keys()),
                "total_entries": sum(len(v) for v in self._cache.values()),
                "zhconv_available": HAS_ZHCONV,
            }