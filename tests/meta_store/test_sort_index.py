"""#418: SortIndex against a live Postgres.

Two things must hold, and the second matters more than the first:

* the btree is actually USED for ranges and ORDER BY (otherwise the annotation
  is a lie);
* declaring or dropping it NEVER changes an answer — the index is a pure
  derivation of live ``indexed_data``, so its absence can only cost speed.

The SQL shape is pinned service-free in ``tests/test_sort_index_marker.py``.
"""

import uuid
from datetime import UTC, datetime

import pytest

from specstar.query import QB
from specstar.query_types import (
    ResourceDataSearchSort,
    ResourceMetaSearchQuery,
    ResourceMetaSortDirection,
)
from specstar.types import ResourceMeta

from .common import get_meta_store

ROWS = {"1": 10, "2": 5, "3": 100, "4": 9}


def _meta(rid: str, score) -> ResourceMeta:
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
        indexed_data={"id": rid, "score": score},
    )


def _seed(store, rows=ROWS):
    for rid, score in rows.items():
        m = _meta(rid, score)
        store[m.resource_id] = m
    return store


def _ids(store, cond) -> list[str]:
    return sorted(m.indexed_data["id"] for m in store.iter_search(cond.build()))


def _sorted_ids(store, direction) -> list[str]:
    q = ResourceMetaSearchQuery(
        sorts=[ResourceDataSearchSort(field_path="score", direction=direction)],
        limit=100,
    )
    return [m.indexed_data["id"] for m in store.iter_search(q)]


@pytest.fixture
def store():
    return _seed(get_meta_store("postgres"))


def test_declaring_the_index_does_not_change_range_results(store):
    """The invariant: index in, index out, same answers."""
    before = _ids(store, QB["score"] > 9)
    assert before == ["1", "3"]  # sanity: the cast path is correct

    store.ensure_sort_index("score")

    assert _ids(store, QB["score"] > 9) == before


def test_ranges_are_numeric_not_lexicographic(store):
    """jsonb orders numbers numerically: 9 > 100 must stay false.

    A text-ordered rewrite would put "100" before "9" and silently corrupt every
    range on a numeric field.
    """
    store.ensure_sort_index("score")
    assert _ids(store, QB["score"] > 9) == ["1", "3"]
    assert _ids(store, QB["score"] < 10) == ["2", "4"]
    assert _ids(store, QB["score"] >= 10) == ["1", "3"]
    assert _ids(store, QB["score"] <= 9) == ["2", "4"]


def test_sort_order_is_numeric_and_unchanged_by_the_index(store):
    """ORDER BY already emits ``indexed_data->'score'`` — the very expression the
    index is built on — so sorting needs no SQL change at all, only the index."""
    before_asc = _sorted_ids(store, ResourceMetaSortDirection.ascending)
    before_desc = _sorted_ids(store, ResourceMetaSortDirection.descending)
    assert before_asc == ["2", "4", "1", "3"]  # 5, 9, 10, 100 — numeric

    store.ensure_sort_index("score")

    assert _sorted_ids(store, ResourceMetaSortDirection.ascending) == before_asc
    assert _sorted_ids(store, ResourceMetaSortDirection.descending) == before_desc


def test_the_index_is_applicable_to_a_range(store):
    """Otherwise the annotation is decoration.

    This asserts the index MATCHES the query's expression, not that the planner
    prefers it: on a handful of rows a seq scan is genuinely cheaper and always
    wins, so ``enable_seqscan=off`` asks the question we actually care about.
    (Whether it pays off is a cost decision — measured separately: at 100k rows a
    range goes 22.9 ms Seq Scan -> 2.3 ms Bitmap.)
    """
    store.ensure_sort_index("score")
    plan = _explain(store, "SELECT count(*) FROM {t} WHERE indexed_data->'score' > '9'")
    assert store._sort_idx_name("score") in plan, plan


def test_the_index_is_applicable_to_order_by(store):
    """ORDER BY needs no SQL change — it already emits the indexed expression."""
    store.ensure_sort_index("score")
    plan = _explain(
        store,
        "SELECT resource_id FROM {t} ORDER BY indexed_data->'score' DESC LIMIT 2",
    )
    assert store._sort_idx_name("score") in plan, plan
    assert "Sort" not in plan, f"index should remove the sort entirely:\n{plan}"


def _explain(store, sql: str) -> str:
    with store.transaction() as cur:
        cur.execute("SET LOCAL enable_seqscan = off")
        cur.execute("EXPLAIN " + sql.format(t=f'"{store.table_name}"'))
        return "\n".join(r[0] for r in cur.fetchall())


def test_dropping_the_index_leaves_results_identical(store):
    """Rollback is a pure perf change and cannot be wrong: same SQL either way."""
    store.ensure_sort_index("score")
    with_index = _ids(store, QB["score"] > 9)

    with store.transaction() as cur:
        cur.execute(f'DROP INDEX "{store._sort_idx_name("score")}"')
    store._sort_indexes.discard("score")

    assert _ids(store, QB["score"] > 9) == with_index


def test_ensure_sort_index_is_idempotent_across_restarts(store):
    """It runs from add_model, i.e. on every process start."""
    store.ensure_sort_index("score")
    store.ensure_sort_index("score")
    store.ensure_sort_index("score")
    assert _ids(store, QB["score"] > 9) == ["1", "3"]


def test_a_row_missing_the_field_never_matches_a_range(store):
    m = _meta("5", 0)
    m.indexed_data = {"id": "5"}  # no score at all
    store[m.resource_id] = m
    store.ensure_sort_index("score")
    assert _ids(store, QB["score"] > 9) == ["1", "3"]


def test_the_index_builds_over_rows_that_already_exist(store):
    """No backfill exists or is needed: the index is derived from live rows.

    This is the structural difference from SetIndex (#417), whose shadow column
    was NULL for pre-existing rows and silently hid them.
    """
    store.ensure_sort_index("score")  # rows were seeded BEFORE this
    assert _ids(store, QB["score"] > 9) == ["1", "3"]


def test_a_value_of_an_unexpected_type_neither_breaks_writes_nor_the_index(store):
    """Indexing the raw extract (no cast) is what buys this.

    ``((indexed_data->>'score')::numeric)`` would be faster, but it turns the
    index into a write constraint: this row would be rejected outright.
    """
    store.ensure_sort_index("score")
    m = _meta("6", "n/a")  # a string where numbers live
    store[m.resource_id] = m  # must not raise
    # String sorts into a different jsonb band, so it never matches a numeric range.
    assert _ids(store, QB["score"] > 9) == ["1", "3"]
