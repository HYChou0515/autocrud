"""``specstar.util.trigram`` — the Python port of pg_trgm's trigram similarity.

The reference (memory / disk / sqlite) backends serve ``.fuzzy()`` / ``.similarity()``
with this module, so they return the **same** rows as production Postgres — not
merely "something fuzzy". Every expected value below is pinned from **live
Postgres** ``word_similarity`` / ``similarity`` / ``show_trgm`` (the port matches
pg_trgm bit-for-bit over a 140k-pair fuzz; the standing guard is
``tests/meta_store/test_trigram_index.py::test_reference_matches_live_postgres``).

Service-free by design — this runs in CI.
"""

import pytest

from specstar.util import trigram


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # lower-cased, blank-padded "  W ", 3-grams, distinct set (show_trgm order).
        ("mol", ["  m", " mo", "mol", "ol "]),
        ("m4", ["  m", " m4", "m4 "]),
        ("MOL", ["  m", " mo", "mol", "ol "]),  # IGNORECASE
        ("a", ["  a", " a "]),
        (
            "hello world",  # split on the space; each word padded independently
            [
                "  h",
                "  w",
                " he",
                " wo",
                "ell",
                "hel",
                "ld ",
                "llo",
                "lo ",
                "orl",
                "rld",
                "wor",
            ],
        ),
        # '_' is not alphanumeric → a word boundary (KEEPONLYALNUM)
        (
            "under_score",
            [
                "  s",
                "  u",
                " sc",
                " un",
                "cor",
                "der",
                "er ",
                "nde",
                "ore",
                "re ",
                "sco",
                "und",
            ],
        ),
        ("", []),  # too short → no trigrams
        ("   ", []),  # only boundaries → no words
    ],
)
def test_trigram_sequence_matches_show_trgm(text, expected):
    assert sorted(set(trigram.trigram_sequence(text))) == sorted(expected)


def test_trigram_sequence_is_ordered_and_not_deduplicated():
    """word_similarity needs the target's trigrams in text order, with repeats —
    ``generate_trgm_only`` does not sort or unique them."""
    seq = trigram.trigram_sequence("ababa")
    # "  a", " ab", "aba", "bab", "aba", "ba " — "aba" repeats, order preserved.
    assert seq == ["  a", " ab", "aba", "bab", "aba", "ba "]


@pytest.mark.parametrize(
    ("query", "target", "expected"),
    [
        ("mol", "molecular biology", 3 / 4),
        ("mol", "small molecule", 3 / 4),
        ("mol", "capping protein", 0.0),
        ("molec", "molecular", 5 / 6),
        ("molecu", "molecular", 6 / 7),
        ("molecu", "mole", 4 / 7),
        ("molecu", "molar", 3 / 7),
        ("mu", "must-have", 2 / 3),  # word-split on the hyphen
        ("capor", "capping", 1 / 2),  # partial: below the 0.6 default
        ("bio", "molecular biology", 3 / 4),
        ("quick", "the quick brown fox", 1.0),  # fully contained → 1.0
        ("xyz", "molecular", 0.0),
        ("", "anything", 0.0),  # empty query
        ("mol", "", 0.0),  # empty target
        # non-ASCII: relabelling-invariant, so still exact vs Postgres
        ("分子", "分子生物學", 2 / 3),
        ("中文", "中文測試", 2 / 3),
        # multi-word / repeated-trigram targets — these drive the sliding window's
        # greedy left-shrink and the last-position bookkeeping (the extent may sit
        # anywhere in the target, junk words and repeats notwithstanding).
        ("cat", "zzz cat", 1.0),
        ("cat", "zzzz cat cat", 1.0),
        ("abc", "abcabc", 3 / 4),  # a repeated trigram within one word
        ("cat", "cat cat cat", 1.0),
        ("dog", "the lazy dog runs", 1.0),
        ("xy", "ab xy ab xy", 1.0),
        ("cat", "a b c cat d e", 1.0),
        ("hello", "say hello hello there", 1.0),
        ("mol", "xx mol yy mol zz", 1.0),
        ("cat cat", "the cat", 1.0),  # a repeated trigram in the QUERY
    ],
)
def test_word_similarity_matches_postgres(query, target, expected):
    assert trigram.word_similarity(query, target) == pytest.approx(expected, abs=1e-6)


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("molecular", "molecular biology", 5 / 9),
        ("molecular", "small molecule", 7 / 18),
        ("mol", "mol", 1.0),
        ("abc", "xyz", 0.0),
        ("", "abc", 0.0),
        ("分子", "分子生物學", 2 / 7),
    ],
)
def test_similarity_matches_postgres(a, b, expected):
    assert trigram.similarity(a, b) == pytest.approx(expected, abs=1e-6)


def test_word_similarity_is_float4_rounded():
    """Ratios are computed in float4, exactly as Postgres does — so a value lands
    on the same side of a threshold as the server would put it."""
    value = trigram.word_similarity("molecu", "molecular")
    assert value == trigram._f4(6 / 7)
    # a plain double would differ in the low bits
    assert value != 6 / 7


def test_default_thresholds_match_pg_trgm_gucs():
    assert trigram.WORD_SIMILARITY_THRESHOLD == 0.6
    assert trigram.SIMILARITY_THRESHOLD == 0.3
