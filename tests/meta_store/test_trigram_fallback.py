"""When pg_trgm is absent, Postgres .fuzzy()/.similarity() degrade to a Python
computation (the specstar.util.trigram port), not a cryptic operator error.

Unlike pgvector (declared by a Vector annotation, so a missing extension can fail
at boot), .fuzzy() can be sent over ?qb= against ANY field with no annotation —
you cannot know at boot who will use it. So the reference-correct behaviour is
reactive: at query time, if the extension is missing, warn once and compute the
same word_similarity in Python. Correct everywhere, only slower — the same
"absence costs speed, never correctness" contract as the GIN.

Simulated by forcing ``_has_pg_trgm = False`` on a live-Postgres store (the test
DB really has pg_trgm, so the fallback path — not the raw error — is what we pin).
"""

import pytest

from specstar.errors import SpecStarWarning
from specstar.query import QB

from .common import get_meta_store
from .test_trigram_index import _ids, _ordered_ids, _seed


@pytest.fixture
def no_trgm_store():
    store = _seed(get_meta_store("postgres"))
    store._has_pg_trgm = False  # simulate a database without the pg_trgm extension
    return store


def test_fuzzy_scoped_by_a_pushdown_filter_falls_back_to_python(no_trgm_store):
    """The common query: a fuzzy match AND a filter that CAN be pushed to SQL.
    The filter bounds the candidate set; the fuzzy is applied in Python."""
    store = no_trgm_store
    with pytest.warns(SpecStarWarning, match="pg_trgm"):
        # title contains "biology" (SQL) AND fuzzy-matches "molecular" (Python)
        got = _ids(
            store, QB["title"].contains("biology") & QB["title"].fuzzy("molecular")
        )
    assert got == ["1"]  # "molecular biology" — not row 3 "small molecule"


def test_bare_fuzzy_falls_back_to_python(no_trgm_store):
    """No pushdown filter → a full scan in Python, but still correct + warned."""
    store = no_trgm_store
    with pytest.warns(SpecStarWarning, match="pg_trgm"):
        got = _ids(store, QB["title"].fuzzy("molecular"))
    assert got == ["1", "3"]  # matches "molecular biology" and "small molecule"


def test_custom_threshold_fuzzy_falls_back_to_python(no_trgm_store):
    store = no_trgm_store
    with pytest.warns(SpecStarWarning, match="pg_trgm"):
        loose = _ids(store, QB["title"].fuzzy("molec", threshold=0.5))
        tight = _ids(store, QB["title"].fuzzy("molec", threshold=0.99))
    assert loose == ["1", "3"]
    assert tight == []


def test_similarity_sort_falls_back_to_python(no_trgm_store):
    """The ranking sort computes word_similarity in Python and orders by it."""
    store = no_trgm_store
    with pytest.warns(SpecStarWarning, match="pg_trgm"):
        desc = (
            QB["title"]
            .fuzzy("molecular")
            .sort(QB["title"].similarity("molecular").desc())
        )
        order = _ordered_ids(store, desc)
    assert order == ["1", "3"]  # exact word (1.0) before partial (0.7)


def test_fallback_matches_the_native_pg_trgm_answer(no_trgm_store):
    """The Python fallback returns exactly what native pg_trgm would — same rows."""
    native = _seed(get_meta_store("postgres"))  # _has_pg_trgm stays True
    for cond in [
        QB["title"].fuzzy("molecular"),
        QB["title"].fuzzy("polymer"),
        QB["title"].fuzzy("zzznope"),
        QB["keys"].fuzzy("capp"),
        QB["title"].contains("biology") & QB["title"].fuzzy("molecular"),
    ]:
        assert _ids(no_trgm_store, cond) == _ids(native, cond)


def test_count_falls_back_when_pg_trgm_absent(no_trgm_store):
    store = no_trgm_store
    with pytest.warns(SpecStarWarning, match="pg_trgm"):
        n = store.count(QB["title"].fuzzy("molecular").build())
    assert n == 2
