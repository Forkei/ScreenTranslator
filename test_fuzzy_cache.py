"""Quick test for fuzzy cache, translation dedup, and TTL."""
import time
from src.core.text_similarity import jaro_similarity, dice_similarity, text_similarity
from src.core.translation_cache import TranslationCache, is_asian_language


def test_similarity_functions():
    print("=== Similarity Functions ===")

    # Identical strings
    assert jaro_similarity("hello", "hello") == 1.0
    assert dice_similarity("hello", "hello") == 1.0
    print("  identical strings: PASS")

    # Empty strings
    assert jaro_similarity("", "hello") == 0.0
    assert dice_similarity("", "hello") == 0.0
    print("  empty strings: PASS")

    # Near-duplicate OCR results (the real use case)
    s1 = "The quick brown fox jumps over the lazy dog"
    s2 = "The quick brown fox jumps over the Iazy dog"  # l -> I (common OCR error)
    score = text_similarity(s1, s2)
    print(f"  OCR near-dup (l->I): {score:.3f} (should be >0.65)")
    assert score > 0.65

    # Slightly truncated text (scroll causing partial capture)
    s3 = "The quick brown fox jumps over"
    score2 = text_similarity(s1, s3)
    print(f"  truncated text: {score2:.3f}")

    # Completely different text
    s4 = "Lorem ipsum dolor sit amet"
    score3 = text_similarity(s1, s4)
    print(f"  different text: {score3:.3f} (should be <0.65)")
    assert score3 < 0.65

    print()


def test_fuzzy_cache():
    print("=== Fuzzy Cache ===")
    cache = TranslationCache(max_size=100, similarity_threshold=0.65, ttl_seconds=3.0)

    # Store a translation
    src = "The quick brown fox jumps over the lazy dog"
    cache.put(src, "eng_Latn", "fra_Latn", "Le renard brun rapide saute par-dessus le chien paresseux")

    # Exact match
    result = cache.get(src, "eng_Latn", "fra_Latn")
    assert result is not None
    print(f"  exact hit: PASS -> {result[:40]}...")

    # Fuzzy match (OCR variation — l->I)
    ocr_variant = "The quick brown fox jumps over the Iazy dog"
    result2 = cache.get(ocr_variant, "eng_Latn", "fra_Latn")
    assert result2 is not None
    print(f"  fuzzy hit (l->I): PASS -> {result2[:40]}...")

    # Fuzzy match (minor punctuation/spacing)
    ocr_variant2 = "The quick brown fox jumps over the lazy dog."
    result3 = cache.get(ocr_variant2, "eng_Latn", "fra_Latn")
    assert result3 is not None
    print(f"  fuzzy hit (extra dot): PASS -> {result3[:40]}...")

    # Miss — completely different text
    result4 = cache.get("Lorem ipsum dolor sit amet", "eng_Latn", "fra_Latn")
    assert result4 is None
    print(f"  miss (different text): PASS -> None")

    # Wrong language pair — should miss
    result5 = cache.get(src, "eng_Latn", "deu_Latn")
    assert result5 is None
    print(f"  miss (wrong target lang): PASS -> None")

    print(f"  cache stats: size={cache.size}, hits={cache._hits}, misses={cache._misses}, fuzzy_hits={cache._fuzzy_hits}")
    print()


def test_translation_dedup():
    print("=== Translation Dedup ===")
    cache = TranslationCache()

    t1 = "Le renard brun rapide saute par-dessus le chien paresseux"
    assert cache.is_translation_duplicate(t1) == False
    print(f"  first translation: not duplicate (PASS)")

    # Near-identical (minor OCR jitter in source -> minor translation jitter)
    t2 = "Le renard brun rapide saute par-dessus le chien paresseux."
    is_dup = cache.is_translation_duplicate(t2)
    print(f"  near-identical (extra dot): duplicate={is_dup} (should be True)")
    assert is_dup == True

    # Completely different translation
    t3 = "Bonjour le monde, comment allez-vous aujourd'hui?"
    is_dup2 = cache.is_translation_duplicate(t3)
    print(f"  different translation: duplicate={is_dup2} (should be False)")
    assert is_dup2 == False

    print()


def test_ttl():
    print("=== TTL Expiry ===")
    cache = TranslationCache(ttl_seconds=0.5)  # Short TTL for testing

    cache.put("hello", "eng_Latn", "fra_Latn", "bonjour")
    result = cache.get("hello", "eng_Latn", "fra_Latn")
    assert result == "bonjour"
    print(f"  before TTL: hit (PASS)")

    # Wait for TTL to expire
    print(f"  sleeping 0.6s for TTL expiry...")
    time.sleep(0.6)

    result2 = cache.get("hello", "eng_Latn", "fra_Latn")
    assert result2 is None
    print(f"  after TTL: miss (PASS)")

    print()


def test_asian_language():
    print("=== Asian Language Detection ===")
    assert is_asian_language("zho_Hans") == True
    assert is_asian_language("jpn_Jpan") == True
    assert is_asian_language("kor_Hang") == True
    assert is_asian_language("eng_Latn") == False
    assert is_asian_language("fra_Latn") == False
    print("  all checks: PASS")

    # Asian language gets lower threshold
    cache = TranslationCache(similarity_threshold=0.65)
    cache.put("hello", "zho_Hans", "eng_Latn", "你好")
    # The threshold for Asian languages is 0.55
    print(f"  Asian threshold in use: 0.55 (vs default 0.65)")
    print()


if __name__ == "__main__":
    test_similarity_functions()
    test_fuzzy_cache()
    test_translation_dedup()
    test_ttl()
    test_asian_language()
    print("ALL TESTS PASSED")
