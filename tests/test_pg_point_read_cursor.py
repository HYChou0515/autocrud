"""A point read must not open a server-side cursor.

`stream_cursor()` opens a NAMED psycopg2 cursor, which makes postgres do
`DECLARE` / `FETCH` / `CLOSE` — three round-trips instead of one. That is the
right trade when iterating a whole table, and pure loss when the caller has
already decided it wants a single row.

Measured against a local postgres before this change: one `get()` by primary key
cost 14 SQL statements, of which only 3 fetched data (issue #442).
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


def _store_with_row(row):
    """A store whose connection returns `row` from `fetchone`, and which records
    every `conn.cursor(...)` call so the test can see whether it was named."""
    cursor = MagicMock(name="cursor")
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    # `get_conn` health-checks every checkout with `SELECT 1` before the caller's
    # query runs — itself one of the round-trips issue #442 counts.
    calls = {"n": 0}

    def _fetchone():
        calls["n"] += 1
        return [1] if calls["n"] == 1 else row  # first is the SELECT 1 health check

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


def _named_cursor_calls(conn):
    return [c for c in conn.cursor.call_args_list if c.kwargs.get("name")]


def test_getitem_does_not_open_a_server_side_cursor():
    """The hot one: every `rm.get()` resolves meta through here."""
    store, conn = _store_with_row({"data": b""})
    store._serializer = MagicMock(decode=MagicMock(return_value="meta"))

    assert store["some-id"] == "meta"
    assert _named_cursor_calls(conn) == [], conn.cursor.call_args_list


def test_len_does_not_open_a_server_side_cursor():
    """A COUNT returns exactly one row — there is nothing to stream."""
    store, conn = _store_with_row([7])

    assert len(store) == 7
    assert _named_cursor_calls(conn) == [], conn.cursor.call_args_list


def test_a_bounded_read_runs_without_a_transaction():
    """`BEGIN` and `COMMIT` are two more round-trips, and a single-statement read
    has nothing to make atomic. `get_conn` turns autocommit off for writers; a
    bounded read turns it back on for its own duration."""
    store, conn = _store_with_row({"data": b""})
    store._serializer = MagicMock(decode=MagicMock(return_value="meta"))

    assert store["some-id"] == "meta"
    assert conn.commit.call_count == 0, "a read committed a transaction it never needed"
    assert conn.autocommit is False, "autocommit must be restored before the connection goes back"
