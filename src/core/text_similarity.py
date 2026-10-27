"""Text similarity functions ported from Translumo's StringExtensions.cs.

Provides Jaro distance and Sorensen-Dice coefficient for fuzzy text matching,
used by the translation cache to avoid redundant translations when OCR produces
near-duplicate results.
"""


def jaro_similarity(s1: str, s2: str) -> float:
    """Jaro distance between two strings (0.0–1.0).

    Finds common characters within floor(max(len(s1),len(s2))/2) - 1 distance
    and counts transpositions.
    """
    if s1 == s2:
        return 1.0

    len1 = len(s1)
    len2 = len(s2)

    if len1 == 0 or len2 == 0:
        return 0.0

    match_distance = max(len1, len2) // 2 - 1
    if match_distance < 0:
        match_distance = 0

    s1_matches = [False] * len1
    s2_matches = [False] * len2

    matches = 0
    transpositions = 0

    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)

        for j in range(start, end):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    return (
        matches / len1 + matches / len2 + (matches - transpositions / 2) / matches
    ) / 3.0


def dice_similarity(s1: str, s2: str) -> float:
    """Sorensen-Dice coefficient using character bigrams (0.0–1.0).

    ``2 * |intersection| / (|bigrams1| + |bigrams2|)``
    """
    if s1 == s2:
        return 1.0

    if len(s1) < 2 or len(s2) < 2:
        return 0.0

    bigrams1: dict[str, int] = {}
    for i in range(len(s1) - 1):
        bg = s1[i:i + 2]
        bigrams1[bg] = bigrams1.get(bg, 0) + 1

    bigrams2: dict[str, int] = {}
    for i in range(len(s2) - 1):
        bg = s2[i:i + 2]
        bigrams2[bg] = bigrams2.get(bg, 0) + 1

    intersection = 0
    for bg, count in bigrams1.items():
        if bg in bigrams2:
            intersection += min(count, bigrams2[bg])

    total = (len(s1) - 1) + (len(s2) - 1)
    if total == 0:
        return 0.0

    return 2.0 * intersection / total


def text_similarity(s1: str, s2: str) -> float:
    """Blended similarity score (Translumo's formula).

    ``(jaro + dice) / 2.0``, or ``(dice + dice) / 2.0`` if jaro == 0.
    """
    jaro = jaro_similarity(s1, s2)
    dice = dice_similarity(s1, s2)

    if jaro == 0.0:
        return (dice + dice) / 2.0
    return (jaro + dice) / 2.0
