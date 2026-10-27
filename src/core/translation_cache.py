import logging
import time
from collections import OrderedDict, deque

from src.core.text_similarity import jaro_similarity, text_similarity

logger = logging.getLogger(__name__)

# Language codes considered "Asian" (CJK, Thai, etc.) — need lower similarity threshold
_ASIAN_LANG_PREFIXES = frozenset({
    "zho", "jpn", "kor", "tha", "mya", "khm", "lao", "vie",
})


def is_asian_language(lang_code: str) -> bool:
    """Check if a FLORES-200 language code is CJK/Thai/etc."""
    prefix = lang_code.split("_")[0] if "_" in lang_code else lang_code[:3]
    return prefix in _ASIAN_LANG_PREFIXES


class TranslationCache:
    """LRU cache with fuzzy matching, TTL expiry, and translation dedup.

    Key improvements over exact-match cache:
    - Fuzzy source text lookup avoids redundant translations when OCR produces
      near-duplicate results (Translumo's core insight)
    - TTL-based expiry clears stale entries when text disappears
    - Translation output dedup suppresses overlay flicker
    """

    def __init__(self, max_size: int = 500, similarity_threshold: float = 0.65,
                 ttl_seconds: float = 3.0):
        self.max_size = max_size
        self.similarity_threshold = similarity_threshold
        self.ttl_seconds = ttl_seconds

        self._cache: OrderedDict[tuple, str] = OrderedDict()
        self._last_access_time: float = time.monotonic()
        self._recent_translations: deque[str] = deque(maxlen=6)

        self._hits = 0
        self._misses = 0
        self._fuzzy_hits = 0

    def get(self, text: str, source_lang: str, target_lang: str) -> str | None:
        """Look up a cached translation with fuzzy matching.

        1. Check TTL — clear cache if stale
        2. Try exact match (fast path, O(1))
        3. If miss, scan entries for fuzzy text_similarity > threshold
        """
        now = time.monotonic()

        # TTL check: clear cache if no access for ttl_seconds
        if now - self._last_access_time > self.ttl_seconds and self._cache:
            logger.debug("Cache TTL expired (%.1fs idle), clearing %d entries",
                         now - self._last_access_time, len(self._cache))
            self._cache.clear()

        self._last_access_time = now

        # Exact match (fast path)
        key = (text, source_lang, target_lang)
        if key in self._cache:
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]

        # Fuzzy match: scan cache for similar source text
        threshold = 0.55 if is_asian_language(source_lang) else self.similarity_threshold
        best_score = 0.0
        best_translation = None

        for (cached_text, cached_src, cached_tgt), translation in self._cache.items():
            if cached_src != source_lang or cached_tgt != target_lang:
                continue
            score = text_similarity(text, cached_text)
            if score > threshold and score > best_score:
                best_score = score
                best_translation = translation

        if best_translation is not None:
            self._fuzzy_hits += 1
            self._hits += 1
            logger.info("Fuzzy cache hit (score=%.3f, threshold=%.2f)", best_score, threshold)
            # Store the new text variant with the same translation for future exact hits
            self.put(text, source_lang, target_lang, best_translation)
            return best_translation

        self._misses += 1
        return None

    def put(self, text: str, source_lang: str, target_lang: str, translation: str) -> None:
        """Store a translation in the cache."""
        key = (text, source_lang, target_lang)
        self._cache[key] = translation
        self._cache.move_to_end(key)
        while len(self._cache) > self.max_size:
            self._cache.popitem(last=False)
        self._last_access_time = time.monotonic()

    def is_translation_duplicate(self, translation: str) -> bool:
        """Check if a translation is near-identical to a recent one.

        Uses jaro_similarity > 0.955 against the last 6 translations.
        Called by the pipeline before emitting blocks to suppress overlay flicker.
        """
        for recent in self._recent_translations:
            if jaro_similarity(translation, recent) > 0.955:
                return True
        self._recent_translations.append(translation)
        return False

    def clear(self) -> None:
        """Clear all cached translations."""
        self._cache.clear()
        self._recent_translations.clear()
        self._hits = 0
        self._misses = 0
        self._fuzzy_hits = 0

    @property
    def size(self) -> int:
        return len(self._cache)

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0
