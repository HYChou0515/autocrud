"""Which cursor a search uses, and why it must depend on the LIMIT.

A server-side (named) cursor is what stops an unbounded search from pulling a
whole table into memory. It costs `DECLARE` + an extra `FETCH` + `CLOSE`, inside
a transaction — six statements around one query.

psycopg2 drains a named cursor in batches of `itersize` (2000). So a search whose
LIMIT is no larger than one batch would be materialised in a single FETCH anyway:
the cursor buys nothing and costs five extra round-trips. Above that, it is
load-bearing and must stay.

Getting the condition wrong in the permissive direction loads an entire table
into memory, so both directions are pinned here.
"""

from unittest.mock import MagicMock, patch

import pytest

REG = "specstar.resource_manager._pg_pool"


@pytest.fixture(autouse=True)
def _reset_registry():
    from specstar.resource_manager import _pg_pool

    _pg_pool.close_all_pools()
    yield
    _pg_pool.close_all_pools()


def _store_and_conn():
    cursor = MagicMock(name="cursor")
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    cursor.__iter__ = MagicMock(return_value=iter([]))
    cursor.fetchall.return_value = []
    calls = {"n": 0}

    def _fetchone():
        calls["n"] += 1
        return [1] if calls["n"] == 1 else None  # first is the SELECT 1 health check

    cursor.fetchone.side_effect = _fetchone

    conn = MagicMock(name="conn")
    conn.cursor.return_value = cursor
    pool = MagicMock(name="pool")
    pool.getconn.return_value = conn

    with patch(f"{REG}.get_pool", return_value=pool):
        with patch(
            "specstar.resource_manager.meta_store.postgres."
            "PostgresMetaStore._init_postgres_table"
        ):
            with patch(
                "specstar.resource_manager.meta_store.postgres."
                "PostgresMetaStore._detect_pgvector",
                return_value=False,
            ):
                from specstar.resource_manager.meta_store.postgres import (
                    PostgresMetaStore,
                )

                store = PostgresMetaStore(pg_dsn="postgresql://fake/fake")
    return store, conn


def _named(conn):
    return [c for c in conn.cursor.call_args_list if c.kwargs.get("name")]


def _search(limit):
    from specstar.query_types import ResourceMetaSearchQuery

    store, conn = _store_and_conn()
    list(store.iter_search(ResourceMetaSearchQuery(limit=limit)))
    return conn


def test_a_page_sized_search_skips_the_server_side_cursor():
    assert _named(_search(50)) == [], "a 50-row page does not need to stream"


def test_a_search_at_the_batch_boundary_still_skips_it():
    assert _named(_search(2000)) == [], "one batch is one FETCH either way"


def test_a_search_larger_than_one_batch_keeps_streaming():
    conn = _search(2001)
    assert _named(conn), "past one batch the cursor is what bounds memory"


def test_the_unbounded_default_keeps_streaming():
    """The default limit is a sentinel (~4.29e9), not a page size. Treating it as
    a bound would pull the whole table into memory — the failure this cursor
    exists to prevent."""
    from specstar.query_types import DEFAULT_QUERY_LIMIT

    conn = _search(DEFAULT_QUERY_LIMIT)
    assert _named(conn), f"limit={DEFAULT_QUERY_LIMIT} must stream"


def test_an_aggregation_streams_unless_its_result_is_bounded():
    """A GROUP BY is NOT inherently small: grouping by a high-cardinality key
    returns one row per group, which can be one row per resource. So the rule is
    the same as for a search — the caller's `limit` is what bounds it, and
    without one the cursor stays.
    """
    from unittest.mock import MagicMock as MM

    from specstar.query_types import ResourceMetaSearchQuery

    by = MM(source="meta", key="n", path=None)

    store, conn = _store_and_conn()
    store.aggregate_by(ResourceMetaSearchQuery(), by, [], limit=50)
    assert _named(conn) == [], "a limited aggregation fits in one fetch"

    store2, conn2 = _store_and_conn()
    store2.aggregate_by(ResourceMetaSearchQuery(), by, [])
    assert _named(conn2), "an unlimited GROUP BY can return a row per resource"
