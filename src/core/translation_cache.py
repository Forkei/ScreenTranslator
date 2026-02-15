import logging
from collections import OrderedDict

logger = logging.getLogger(__name__)


class TranslationCache:
    """LRU cache for translations, keyed by (text, source_lang, target_lang)."""

    def __init__(self, max_size: int = 500):
        self.max_size = max_size
        self._cache: OrderedDict[tuple, str] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, text: str, source_lang: str, target_lang: str) -> str | None:
        """Look up a cached translation.

        Returns translated text or None if not cached.
        """
        key = (text, source_lang, target_lang)
        if key in self._cache:
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]
        self._misses += 1
        return None

    def put(self, text: str, source_lang: str, target_lang: str, translation: str) -> None:
        """Store a translation in the cache."""
        key = (text, source_lang, target_lang)
        self._cache[key] = translation
        self._cache.move_to_end(key)
        while len(self._cache) > self.max_size:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        """Clear all cached translations."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    @property
    def size(self) -> int:
        return len(self._cache)

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0
