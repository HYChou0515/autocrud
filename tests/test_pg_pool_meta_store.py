"""
Tests for PostgresMetaStore connection pool behaviour.

Two contracts:
* Stores sharing a DSN share one process-global pool (#380).
* ``get_conn`` does not leak connections and survives pool exhaustion.
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


def _make_store_with_mock_pool(pool_mock):
    """Build a PostgresMetaStore whose shared pool is *pool_mock*."""
    with patch(f"{REG}.get_pool", return_value=pool_mock):
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

                return PostgresMetaStore(pg_dsn="postgresql://fake/fake")


class TestSharedPool:
    """All stores on one DSN reuse a single process-global pool."""

    def _patches(self):
        return (
            patch(
                f"{REG}.psycopg2.pool.ThreadedConnectionPool",
                side_effect=lambda *a, **k: MagicMock(name="pool"),
            ),
            patch(
                "specstar.resource_manager.meta_store.postgres."
                "PostgresMetaStore._init_postgres_table"
            ),
            patch(
                "specstar.resource_manager.meta_store.postgres."
                "PostgresMetaStore._detect_pgvector",
                return_value=False,
            ),
            patch(
                "specstar.resource_manager.resource_store.postgres."
                "PostgresResourceStore._init_tables"
            ),
        )

    def test_two_meta_stores_same_dsn_share_pool(self):
        ctor, init_meta, detect, init_res = self._patches()
        with ctor, init_meta, detect, init_res:
            from specstar.resource_manager.meta_store.postgres import (
                PostgresMetaStore,
            )

            dsn = "postgresql://u:p@localhost:5432/db"
            s1 = PostgresMetaStore(pg_dsn=dsn)
            s2 = PostgresMetaStore(pg_dsn=dsn)

            assert s1._conn_pool is s2._conn_pool

    def test_meta_and_resource_store_same_dsn_share_pool(self):
        ctor, init_meta, detect, init_res = self._patches()
        with ctor, init_meta, detect, init_res:
            from specstar.resource_manager.meta_store.postgres import (
                PostgresMetaStore,
            )
            from specstar.resource_manager.resource_store.postgres import (
                PostgresResourceStore,
            )

            dsn = "postgresql://u:p@localhost:5432/db"
            meta = PostgresMetaStore(pg_dsn=dsn)
            resource = PostgresResourceStore(pg_dsn=dsn)

            assert meta._conn_pool is resource._conn_pool


class TestGetConnConnectionLeak:
    """A failed ``test_query`` returns the bad connection to the pool."""

    def test_failed_test_query_returns_conn_to_pool(self):
        pool_mock = MagicMock()

        bad_conn = MagicMock(name="bad_conn")
        good_conn = MagicMock(name="good_conn")
        pool_mock.getconn.side_effect = [bad_conn, good_conn]

        store = _make_store_with_mock_pool(pool_mock)

        bad_cursor = MagicMock()
        bad_cursor.__enter__ = MagicMock(return_value=bad_cursor)
        bad_cursor.__exit__ = MagicMock(return_value=False)
        bad_cursor.execute.side_effect = Exception("connection is broken")
        bad_conn.cursor.return_value = bad_cursor

        good_cursor = MagicMock()
        good_cursor.__enter__ = MagicMock(return_value=good_cursor)
        good_cursor.__exit__ = MagicMock(return_value=False)
        good_cursor.fetchone.return_value = (1,)
        good_conn.cursor.return_value = good_cursor

        conn = store.get_conn()

        assert conn is good_conn
        pool_mock.putconn.assert_called_once_with(bad_conn, close=True)

    def test_all_retries_fail_still_returns_connections(self):
        pool_mock = MagicMock()

        bad_conns = [MagicMock(name=f"bad_conn_{i}") for i in range(5)]
        pool_mock.getconn.side_effect = bad_conns

        store = _make_store_with_mock_pool(pool_mock)

        for bad_conn in bad_conns:
            bad_cursor = MagicMock()
            bad_cursor.__enter__ = MagicMock(return_value=bad_cursor)
            bad_cursor.__exit__ = MagicMock(return_value=False)
            bad_cursor.execute.side_effect = Exception("broken")
            bad_conn.cursor.return_value = bad_cursor

        with pytest.raises(ConnectionError):
            store.get_conn()

        assert pool_mock.putconn.call_count == 5
        for bad_conn in bad_conns:
            pool_mock.putconn.assert_any_call(bad_conn, close=True)

    def test_pool_exhausted_retries_with_backoff(self):
        import psycopg2.pool

        pool_mock = MagicMock()

        good_conn = MagicMock(name="good_conn")
        good_cursor = MagicMock()
        good_cursor.__enter__ = MagicMock(return_value=good_cursor)
        good_cursor.__exit__ = MagicMock(return_value=False)
        good_cursor.fetchone.return_value = (1,)
        good_conn.cursor.return_value = good_cursor

        pool_mock.getconn.side_effect = [
            psycopg2.pool.PoolError("connection pool exhausted"),
            psycopg2.pool.PoolError("connection pool exhausted"),
            good_conn,
        ]

        store = _make_store_with_mock_pool(pool_mock)

        with patch("specstar.resource_manager.meta_store.postgres.time.sleep"):
            conn = store.get_conn()

        assert conn is good_conn

    def test_pool_exhausted_all_retries_fail_raises(self):
        import psycopg2.pool

        pool_mock = MagicMock()
        pool_mock.getconn.side_effect = psycopg2.pool.PoolError(
            "connection pool exhausted"
        )

        store = _make_store_with_mock_pool(pool_mock)

        with patch("specstar.resource_manager.meta_store.postgres.time.sleep"):
            with pytest.raises((psycopg2.pool.PoolError, ConnectionError)):
                store.get_conn()
