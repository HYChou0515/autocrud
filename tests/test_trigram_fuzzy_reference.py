"""``.fuzzy()`` / ``.similarity()`` on the reference backends return the SAME rows
as Postgres.

Trigram similarity (pg_trgm ``word_similarity``) is reproduced faithfully by
:mod:`specstar.util.trigram`, so the memory / disk / sqlite backends compute it
in Python rather than rejecting it — a query behaves identically whether a
developer runs it against an in-memory store or against production Postgres.

This runs in CI (no external services). The exact values are pinned in
``tests/test_trigram_reference.py``; live-Postgres parity is guarded by
``tests/meta_store/test_trigram_index.py``.
"""

import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from msgspec import UNSET

from specstar.query import QB
from specstar.query_types import ResourceMetaSearchQuery
from specstar.resource_manager.meta_store.simple import DiskMetaStore, MemoryMetaStore
from specstar.resource_manager.meta_store.sqlite3 import MemorySqliteMetaStore
from specstar.types import ResourceMeta


@pytest.fixture
def tmp():
    with tempfile.TemporaryDirectory(dir="./") as d:
        yield Path(d)


def _stores(tmp: Path):
    return [
        MemoryMetaStore(encoding="msgpack"),
        DiskMetaStore(encoding="msgpack", rootdir=tmp),
        MemorySqliteMetaStore(encoding="msgpack"),
    ]


def _meta(rid: str, **indexed) -> ResourceMeta:
    base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    return ResourceMeta(
        current_revision_id=f"rev_{rid}",
        resource_id=str(uuid.uuid4()),
        total_revision_count=1,
        created_time=base,
        updated_time=base,
        created_by="t",
        updated_by="t",
        is_deleted=False,
        indexed_data={"id": rid, **indexed},
    )


def _load(store, metas):
    for m in metas:
        store[m.resource_id] = m
    return store


# ── Scalar-field fuzzy filter ────────────────────────────────────────────────

_TITLES = [
    ("1", "molecular biology"),
    ("2", "small molecule"),
    ("3", "capping protein"),
    ("4", "quantum physics"),
]


@pytest.mark.parametrize(
    ("make_query", "expected"),
    [
        # default threshold (0.6): "mol" is similar to both molecule titles.
        (lambda: QB["title"].fuzzy("mol").build(), {"1", "2"}),
        # "capor" ~ "capping" is only 0.5 — below 0.6, so nothing at the default.
        (lambda: QB["title"].fuzzy("capor").build(), set()),
        # loosen to 0.3 and the typo now finds "capping protein".
        (lambda: QB["title"].fuzzy("capor", threshold=0.3).build(), {"3"}),
        # a fragment present in nothing matches nothing.
        (lambda: QB["title"].fuzzy("xyz").build(), set()),
    ],
    ids=["default-mol", "default-capor-none", "threshold-0.3-capor", "xyz-none"],
)
def test_fuzzy_filter_returns_same_rows_on_every_backend(tmp, make_query, expected):
    for store in _stores(tmp):
        _load(store, [_meta(rid, title=title) for rid, title in _TITLES])
        got = {m.indexed_data["id"] for m in store.iter_search(make_query())}
        assert got == expected


def test_fuzzy_and_or_combined_with_a_filter_on_every_backend(tmp):
    """The essential 'scope + fuzzy' query — a fuzzy condition AND/OR-combined
    with another filter. It nests inside a DataSearchGroup, which every backend
    must dispatch to the fuzzy path rather than treat as a plain scalar condition
    (regression: it used to raise ``'TrigramFuzzyCondition' has no attribute
    'operator'/'transform'`` on Postgres / memory)."""
    for store in _stores(tmp):
        _load(
            store,
            [
                _meta("1", coll="a", title="molecular biology"),
                _meta("2", coll="a", title="capping protein"),
                _meta("3", coll="b", title="molecular biology"),
            ],
        )
        # AND: collection "a" AND fuzzy-matches "mol" -> only row 1
        q_and = ((QB["coll"] == "a") & QB["title"].fuzzy("mol")).build()
        assert {m.indexed_data["id"] for m in store.iter_search(q_and)} == {"1"}
        # OR: collection "b" OR fuzzy-matches "mol" -> row 1 (fuzzy) + row 3 (coll b)
        q_or = ((QB["coll"] == "b") | QB["title"].fuzzy("mol")).build()
        assert {m.indexed_data["id"] for m in store.iter_search(q_or)} == {"1", "3"}


# ── List-field fuzzy filter (any element may match) ──────────────────────────

_TAGGED = [
    ("1", ["capping", "protein"]),
    ("2", ["quantum", "physics"]),
]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("cap", {"1"}),  # similar to the "capping" element of row 1
        ("phys", {"2"}),  # similar to the "physics" element of row 2
    ],
)
def test_fuzzy_on_a_list_field_matches_any_element_on_every_backend(
    tmp, query, expected
):
    for store in _stores(tmp):
        _load(store, [_meta(rid, tags=tags) for rid, tags in _TAGGED])
        got = {
            m.indexed_data["id"]
            for m in store.iter_search(QB["tags"].fuzzy(query).build())
        }
        assert got == expected


# ── Similarity ranking sort ──────────────────────────────────────────────────

_RANKED = [
    ("molecular", "molecular"),
    ("mole", "mole"),
    ("molar", "molar"),
    ("physics", "physics"),
]


@pytest.mark.parametrize(
    ("sort_expr", "expected_order"),
    [
        # word_similarity("molecu", ·): molecular .857 > mole .571 > molar .428 > 0
        (
            lambda: QB["title"].similarity("molecu").desc(),
            ["molecular", "mole", "molar", "physics"],
        ),
        (
            lambda: QB["title"].similarity("molecu").asc(),
            ["physics", "molar", "mole", "molecular"],
        ),
    ],
    ids=["desc-best-first", "asc-worst-first"],
)
def test_similarity_sort_gives_same_order_on_every_backend(
    tmp, sort_expr, expected_order
):
    for store in _stores(tmp):
        _load(store, [_meta(rid, title=title) for rid, title in _RANKED])
        query = ResourceMetaSearchQuery(sorts=[sort_expr()], limit=100)
        order = [m.indexed_data["id"] for m in store.iter_search(query)]
        assert order == expected_order


def test_fuzzy_on_an_empty_store_returns_nothing_not_an_error(tmp):
    """The feature is present on every backend now — an empty store simply
    yields no rows (it does not raise)."""
    for store in _stores(tmp):
        assert list(store.iter_search(QB["title"].fuzzy("mol").build())) == []


def _meta_without_indexed_data(rid: str) -> ResourceMeta:
    base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    return ResourceMeta(
        current_revision_id=f"rev_{rid}",
        resource_id=str(uuid.uuid4()),
        total_revision_count=1,
        created_time=base,
        updated_time=base,
        created_by="t",
        updated_by="t",
        is_deleted=False,
        indexed_data=UNSET,
    )


def test_fuzzy_excludes_rows_with_no_usable_text_on_every_backend(tmp):
    """A row is excluded — never matched, never a crash — when the field is
    absent, holds a non-text value, or the row has no ``indexed_data`` at all."""
    for store in _stores(tmp):
        _load(
            store,
            [
                _meta("hit", title="molecular biology"),  # the only real match
                _meta("no_title", other="x"),  # field absent → None text
                _meta("nontext", title=123),  # not str / list
                _meta_without_indexed_data("blank"),  # no indexed_data
            ],
        )
        got = {
            m.indexed_data["id"]
            for m in store.iter_search(QB["title"].fuzzy("mol").build())
        }
        assert got == {"hit"}
