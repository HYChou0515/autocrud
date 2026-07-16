"""A faithful Python port of pg_trgm's trigram similarity, for the reference
(memory / disk / sqlite) backends.

Postgres serves ``.fuzzy()`` / ``.similarity()`` with the ``pg_trgm`` extension.
So the non-Postgres backends return the **same** rows (not merely "something
fuzzy"), this module reproduces pg_trgm's algorithms exactly:

* :func:`trigram_sequence` mirrors ``generate_trgm_only`` — words are the maximal
  alphanumeric runs (``KEEPONLYALNUM``), each lower-cased (``IGNORECASE``) and
  blank-padded ``"  " + word + " "`` (``LPADDING=2``, ``RPADDING=1``), then cut
  into 3-grams **in text order, without de-duplication**.
* :func:`similarity` mirrors ``similarity()`` / ``%`` — Jaccard over the distinct
  trigram sets: ``count / (len1 + len2 - count)``.
* :func:`word_similarity` mirrors ``word_similarity()`` / ``<%`` — the sliding
  window over the target's ordered trigram sequence (``iterate_word_similarity``),
  a line-by-line port so the greedy left-shrink matches Postgres bit-for-bit.

All ratios are rounded to ``float4`` (:func:`_f4`) exactly as Postgres computes
them, so a value compared against a threshold lands on the same side of the cut.

Trigrams are stored here as their raw padded strings rather than pg_trgm's hashed
representation; since :func:`similarity` / :func:`word_similarity` only ever count
set intersections and unions, the hashing is a pure relabelling and does not
affect the result. The one caveat is non-ASCII case folding / word-boundary
classification, which follows Python's Unicode tables rather than the database
collation — for ASCII text the two agree exactly.
"""

from __future__ import annotations

import struct

# pg_trgm defaults (contrib/pg_trgm/trgm.h): 2 leading + 1 trailing blank.
LPADDING = 2
RPADDING = 1

# pg_trgm GUC defaults (contrib/pg_trgm/trgm_op.c). ``.fuzzy()`` with no explicit
# threshold uses the ``<%`` operator, i.e. word_similarity >= this value.
SIMILARITY_THRESHOLD = 0.3
WORD_SIMILARITY_THRESHOLD = 0.6


def _f4(value: float) -> float:
    """Round a Python double to IEEE single precision, as Postgres' ``float4``.

    pg_trgm computes every similarity ratio in ``float4``; rounding here keeps a
    result on the same side of a threshold as the server would put it.
    """
    return struct.unpack("f", struct.pack("f", value))[0]


def _calcsml(count: int, len1: int, len2: int) -> float:
    """``CALCSML`` — ``count / (len1 + len2 - count)`` in ``float4``."""
    return _f4(count / (len1 + len2 - count))


def trigram_sequence(text: str) -> list[str]:
    """Return the ordered, **non-deduplicated** trigrams of *text*.

    Mirrors ``generate_trgm_only``: split on non-alphanumeric boundaries, then for
    each maximal word emit the 3-grams of its lower-cased, blank-padded form in
    order. Words are concatenated in text order, so a later
    :func:`word_similarity` sees the same sequence Postgres does.
    """
    pad_left = " " * LPADDING
    pad_right = " " * RPADDING
    seq: list[str] = []
    for word in _words(text):
        padded = pad_left + word.lower() + pad_right
        seq.extend(padded[i : i + 3] for i in range(len(padded) - 2))
    return seq


def _words(text: str) -> list[str]:
    """Split *text* into maximal alphanumeric runs (pg_trgm ``KEEPONLYALNUM``)."""
    words: list[str] = []
    current: list[str] = []
    for ch in text:
        if ch.isalnum():
            current.append(ch)
        elif current:
            words.append("".join(current))
            current = []
    if current:
        words.append("".join(current))
    return words


def similarity(a: str, b: str) -> float:
    """pg_trgm ``similarity(a, b)`` / ``a % b`` — Jaccard over trigram sets."""
    set_a = set(trigram_sequence(a))
    set_b = set(trigram_sequence(b))
    if not set_a or not set_b:
        return 0.0
    count = len(set_a & set_b)
    return _calcsml(count, len(set_a), len(set_b))


def word_similarity(query: str, target: str) -> float:
    """pg_trgm ``word_similarity(query, target)`` / ``query <% target``.

    The greatest similarity between *query*'s trigram set and any continuous
    extent of *target*'s ordered trigram sequence. A line-by-line port of
    ``calc_word_similarity`` + ``iterate_word_similarity`` (plain, non-strict).
    """
    q_seq = trigram_sequence(query)
    t_seq = trigram_sequence(target)
    if not q_seq or not t_seq:
        return 0.0

    # Assign a canonical id to each distinct trigram value across query ∪ target.
    # (pg_trgm gets these ids by sorting; any consistent labelling gives the same
    # counts, since only set membership matters downstream.)
    ids: dict[str, int] = {}
    for tg in q_seq:
        if tg not in ids:
            ids[tg] = len(ids)
    for tg in t_seq:
        if tg not in ids:
            ids[tg] = len(ids)

    found = [False] * len(ids)
    for tg in set(q_seq):
        found[ids[tg]] = True
    ulen1 = sum(found)  # distinct query trigrams
    trg2indexes = [ids[tg] for tg in t_seq]

    return _iterate_word_similarity(trg2indexes, found, ulen1, len(ids))


def _iterate_word_similarity(
    trg2indexes: list[int],
    found: list[bool],
    ulen1: int,
    n_ids: int,
) -> float:
    """Port of ``iterate_word_similarity`` (plain word similarity, ``flags == 0``).

    Walks the target's ordered trigram ids and, at every position whose trigram is
    present in the query, evaluates the window ``[lower, i]`` and greedily advances
    ``lower`` while that raises the similarity — keeping the running maximum.
    """
    len2 = len(trg2indexes)
    lastpos = [-1] * n_ids
    ulen2 = 0
    count = 0
    upper = -1
    lower = -1
    smlr_max = 0.0

    for i in range(len2):
        trgindex = trg2indexes[i]

        if lower >= 0 or found[trgindex]:
            if lastpos[trgindex] < 0:
                ulen2 += 1
                if found[trgindex]:
                    count += 1
            lastpos[trgindex] = i

        if found[trgindex]:
            upper = i
            if lower == -1:
                lower = i
                ulen2 = 1

            smlr_cur = _calcsml(count, ulen1, ulen2)

            tmp_count = count
            tmp_ulen2 = ulen2
            prev_lower = lower
            for tmp_lower in range(lower, upper + 1):
                smlr_tmp = _calcsml(tmp_count, ulen1, tmp_ulen2)
                if smlr_tmp > smlr_cur:
                    smlr_cur = smlr_tmp
                    ulen2 = tmp_ulen2
                    lower = tmp_lower
                    count = tmp_count

                tmp_trgindex = trg2indexes[tmp_lower]
                if lastpos[tmp_trgindex] == tmp_lower:
                    tmp_ulen2 -= 1
                    if found[tmp_trgindex]:
                        tmp_count -= 1

            if smlr_cur > smlr_max:
                smlr_max = smlr_cur

            for tmp_lower in range(prev_lower, lower):
                tmp_trgindex = trg2indexes[tmp_lower]
                if lastpos[tmp_trgindex] == tmp_lower:
                    lastpos[tmp_trgindex] = -1

    return smlr_max
