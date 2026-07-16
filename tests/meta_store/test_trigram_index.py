"""TrigramIndex against a live Postgres.

Two things must hold, and the second matters more than the first:

* the pg_trgm GIN is actually USED for a substring ``.contains`` (otherwise the
  annotation is a lie);
* declaring or dropping it NEVER changes an answer — the index is a pure
  derivation of live ``indexed_data``, so its absence can only cost speed.

A scalar ``.contains`` already compiles to ``indexed_data->>'field' LIKE %s``,
the exact expression the GIN is built on, so it becomes index-served the moment
the index exists — no query rewrite (that lands for the ``.any()`` list case in a
later phase). The SQL shape is pinned service-free in
``tests/test_trigram_index_marker.py``.
"""

import uuid
from datetime import UTC, datetime

import pytest

from specstar.query import QB
from specstar.types import ResourceMeta

from .common import get_meta_store

# id -> title (scalar text) ; keys (list[str])
ROWS = {
    "1": ("molecular biology", ["mol", "capping"]),
    "2": ("polymer chains", ["m4", "m40"]),
    "3": ("small molecule", ["ol"]),
    "4": ("unrelated", []),
}


def _meta(rid: str, title: str, keys: list[str]) -> ResourceMeta:
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
        indexed_data={"id": rid, "title": title, "keys": keys},
    )


def _seed(store, rows=ROWS):
    for rid, (title, keys) in rows.items():
        m = _meta(rid, title, keys)
        store[m.resource_id] = m
    return store


def _ids(store, cond) -> list[str]:
    return sorted(m.indexed_data["id"] for m in store.iter_search(cond.build()))


def _explain(store, sql: str) -> str:
    with store.transaction() as cur:
        cur.execute("SET LOCAL enable_seqscan = off")
        cur.execute("EXPLAIN " + sql.format(t=f'"{store.table_name}"'))
        return "\n".join(r[0] for r in cur.fetchall())


@pytest.fixture
def store():
    return _seed(get_meta_store("postgres"))


def test_the_index_is_applicable_to_a_scalar_contains(store):
    """The point of the annotation: a substring ``.contains`` uses the GIN.

    ``enable_seqscan=off`` asks whether the index MATCHES the query, not whether
    the planner prefers it on four rows (it never would).
    """
    store.ensure_trigram_index("title")
    plan = _explain(
        store,
        "SELECT count(*) FROM {t} WHERE indexed_data->>'title' LIKE '%mole%'",
    )
    assert store._trigram_idx_name("title") in plan, plan


def test_declaring_the_index_does_not_change_contains_results(store):
    """The invariant: index in, index out, same answers."""
    before = _ids(store, QB["title"].contains("mole"))
    assert before == ["1", "3"]  # "molecular biology", "small molecule"

    store.ensure_trigram_index("title")

    assert _ids(store, QB["title"].contains("mole")) == before


def test_detect_reports_pg_trgm_available(store):
    """The capability flag mirrors supports_native_vector_search."""
    assert store.supports_native_trigram_search is True


def test_ensure_trigram_index_is_idempotent_across_restarts(store):
    """It runs from add_model, i.e. on every process start."""
    store.ensure_trigram_index("title")
    store.ensure_trigram_index("title")
    store.ensure_trigram_index("title")
    assert _ids(store, QB["title"].contains("mole")) == ["1", "3"]


def test_dropping_the_index_leaves_results_identical(store):
    """Rollback is a pure perf change and cannot be wrong: same SQL either way."""
    store.ensure_trigram_index("title")
    with_index = _ids(store, QB["title"].contains("mole"))

    with store.transaction() as cur:
        cur.execute(f'DROP INDEX "{store._trigram_idx_name("title")}"')
    store._trigram_indexes.discard("title")

    assert _ids(store, QB["title"].contains("mole")) == with_index


def test_the_index_builds_over_rows_that_already_exist(store):
    """No backfill exists or is needed: the GIN is derived from live rows."""
    store.ensure_trigram_index("title")  # rows were seeded BEFORE this
    assert _ids(store, QB["title"].contains("mole")) == ["1", "3"]


def _index_exists(store, idx_name: str) -> bool:
    with store.transaction() as cur:
        cur.execute("SELECT to_regclass(%s) IS NOT NULL", [idx_name])
        return cur.fetchone()[0]


def test_a_list_field_gets_a_gin_and_any_contains_stays_correct(store):
    """The DDL builds for a list field too (the ``.any()`` rewrite that USES it
    lands in a later phase). Meanwhile ``.any().contains`` stays correct by scan."""
    store.ensure_trigram_index("keys")
    assert _index_exists(store, store._trigram_idx_name("keys"))
    # substring over elements: "ol" ⊂ "mol" (row 1) and "ol" itself (row 3).
    assert _ids(store, QB["keys"].any().contains("ol")) == ["1", "3"]


def test_any_eq_membership_uses_the_shared_jsonb_gin(store):
    """``.any().eq(v)`` needs no TrigramIndex — as exact membership it rides the
    always-present shared jsonb GIN via ``indexed_data @> {"keys": [v]}``, not a
    per-row unnest scan."""
    assert _ids(store, QB["keys"].any().eq("mol")) == ["1"]  # only the literal "mol"
    plan = _explain(
        store,
        'SELECT count(*) FROM {t} WHERE indexed_data @> \'{{"keys": ["mol"]}}\'',
    )
    assert "idx_indexed_data_gin" in plan, plan


def test_any_eq_membership_matches_the_reference_answer(store):
    """Membership, not substring: "mol" hits only row 1, never "small molecule"
    (row 3's title) or the "m4"/"m40" keys."""
    assert _ids(store, QB["keys"].any().eq("mol")) == ["1"]
    assert _ids(store, QB["keys"].any().eq("m4")) == ["2"]
    assert _ids(store, QB["keys"].any().eq("nope")) == []
