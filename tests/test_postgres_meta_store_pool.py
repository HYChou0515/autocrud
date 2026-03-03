"""
Tests for PostgresMetaStore connection pool robustness.
Validates that connections are not leaked and pool exhaustion is handled gracefully.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestGetConnConnectionLeak:
    """
    get_conn 中 test_query 失敗時，連線應歸還 pool，不應造成洩漏。
    """

    def _make_store_with_mock_pool(self, pool_mock):
        """建立 PostgresMetaStore，注入 mock connection pool。"""
        with patch(
            "autocrud.resource_manager.meta_store.postgres.psycopg2.pool.SimpleConnectionPool",
            return_value=pool_mock,
        ):
            # 也 mock 掉 _init_postgres_table 以避免真實 DB 呼叫
            with patch(
                "autocrud.resource_manager.meta_store.postgres.PostgresMetaStore._init_postgres_table"
            ):
                from autocrud.resource_manager.meta_store.postgres import (
                    PostgresMetaStore,
                )

                store = PostgresMetaStore(pg_dsn="postgresql://fake/fake")
                store._conn_pool = pool_mock
                return store

    def test_failed_test_query_returns_conn_to_pool(self):
        """
        當 test_query 失敗時，get_conn 應透過 putconn 歸還壞連線，
        而不是任其洩漏在 pool 外面。
        """
        pool_mock = MagicMock()

        # 建立 mock connections
        bad_conn = MagicMock(name="bad_conn")
        good_conn = MagicMock(name="good_conn")

        # 第一次 getconn 回傳壞連線，第二次回傳好連線
        pool_mock.getconn.side_effect = [bad_conn, good_conn]

        store = self._make_store_with_mock_pool(pool_mock)

        # bad_conn 的 test_query 會失敗 (cursor execute raises)
        bad_cursor = MagicMock()
        bad_cursor.__enter__ = MagicMock(return_value=bad_cursor)
        bad_cursor.__exit__ = MagicMock(return_value=False)
        bad_cursor.execute.side_effect = Exception("connection is broken")
        bad_conn.cursor.return_value = bad_cursor

        # good_conn 的 test_query 會成功
        good_cursor = MagicMock()
        good_cursor.__enter__ = MagicMock(return_value=good_cursor)
        good_cursor.__exit__ = MagicMock(return_value=False)
        good_cursor.fetchone.return_value = (1,)
        good_conn.cursor.return_value = good_cursor

        conn = store.get_conn()

        # 應回傳好連線
        assert conn is good_conn

        # 壞連線應被歸還 pool（putconn 被呼叫）
        pool_mock.putconn.assert_called_once_with(bad_conn, close=True)

    def test_all_retries_fail_still_returns_connections(self):
        """
        即使所有 retry 都失敗，每一個借出的連線都應歸還 pool。
        """
        pool_mock = MagicMock()

        # 建立 5 個壞連線（retry = 5）
        bad_conns = [MagicMock(name=f"bad_conn_{i}") for i in range(5)]
        pool_mock.getconn.side_effect = bad_conns

        store = self._make_store_with_mock_pool(pool_mock)

        # 所有連線的 test_query 都失敗
        for bad_conn in bad_conns:
            bad_cursor = MagicMock()
            bad_cursor.__enter__ = MagicMock(return_value=bad_cursor)
            bad_cursor.__exit__ = MagicMock(return_value=False)
            bad_cursor.execute.side_effect = Exception("broken")
            bad_conn.cursor.return_value = bad_cursor

        with pytest.raises(ConnectionError):
            store.get_conn()

        # 所有 5 個壞連線都應被歸還
        assert pool_mock.putconn.call_count == 5
        for bad_conn in bad_conns:
            pool_mock.putconn.assert_any_call(bad_conn, close=True)

    def test_pool_exhausted_retries_with_backoff(self):
        """
        當 pool 耗盡時（PoolError），get_conn 應等待重試而非直接爆炸。
        """
        import psycopg2.pool

        pool_mock = MagicMock()

        good_conn = MagicMock(name="good_conn")
        good_cursor = MagicMock()
        good_cursor.__enter__ = MagicMock(return_value=good_cursor)
        good_cursor.__exit__ = MagicMock(return_value=False)
        good_cursor.fetchone.return_value = (1,)
        good_conn.cursor.return_value = good_cursor

        # 前2次 pool exhausted，第3次成功
        pool_mock.getconn.side_effect = [
            psycopg2.pool.PoolError("connection pool exhausted"),
            psycopg2.pool.PoolError("connection pool exhausted"),
            good_conn,
        ]

        store = self._make_store_with_mock_pool(pool_mock)

        with patch("autocrud.resource_manager.meta_store.postgres.time.sleep"):
            conn = store.get_conn()

        assert conn is good_conn

    def test_pool_exhausted_all_retries_fail_raises(self):
        """
        Pool 持續耗盡超過所有重試次數，應 raise PoolError 或 ConnectionError。
        """
        import psycopg2.pool

        pool_mock = MagicMock()
        pool_mock.getconn.side_effect = psycopg2.pool.PoolError(
            "connection pool exhausted"
        )

        store = self._make_store_with_mock_pool(pool_mock)

        with patch("autocrud.resource_manager.meta_store.postgres.time.sleep"):
            with pytest.raises((psycopg2.pool.PoolError, ConnectionError)):
                store.get_conn()
