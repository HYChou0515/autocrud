"""Live-Postgres proof that connection count decouples from model count (#380).

Auto-marked ``integration`` by ``conftest.py`` (``test_postgres_*.py``), so
it runs against a real database in the integration job, never in fast CI.

Contract: many stores sharing one DSN share a single process-global pool,
so the number of server connections is bounded by that pool's ``maxconn``
— not by ``models * 2``.
"""

from __future__ import annotations

import uuid

import pytest

psycopg2 = pytest.importorskip("psycopg2")

from specstar.resource_manager import _pg_pool  # noqa: E402
from specstar.resource_manager.meta_store.postgres import (  # noqa: E402
    PostgresMetaStore,
)
from specstar.resource_manager.resource_store.postgres import (  # noqa: E402
    PostgresResourceStore,
)

_BASE_DSN = "postgresql://admin:password@localhost:5432/your_database"
_APP_NAME = "specstar_pool380_test"
# Stores attach this application_name so the monitor query can count *only*
# this test's pooled connections, ignoring unrelated sessions.
_POOL_DSN = f"{_BASE_DSN}?application_name={_APP_NAME}"

N_STORES = 8
MAXCONN = 4


def _can_connect() -> bool:
    try:
        conn = psycopg2.connect(_BASE_DSN)
    except Exception:
        return False
    conn.close()
    return True


pytestmark = pytest.mark.skipif(
    not _can_connect(), reason="requires a live PostgreSQL at the test DSN"
)


def _count_pool_connections(monitor) -> int:
    with monitor.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE application_name = %s",
            (_APP_NAME,),
        )
        return cur.fetchone()[0]


def test_many_stores_share_one_bounded_pool():
    suffix = uuid.uuid4().hex[:8]
    monitor = psycopg2.connect(_BASE_DSN)
    meta_tables: list[str] = []
    res_prefixes: list[str] = []
    try:
        _pg_pool.close_all_pools()

        stores = []
        for i in range(N_STORES):
            meta_name = f"sp380_{suffix}_meta_{i}"
            res_prefix = f"sp380_{suffix}_res_{i}_"
            meta_tables.append(meta_name)
            res_prefixes.append(res_prefix)
            stores.append(
                PostgresMetaStore(
                    pg_dsn=_POOL_DSN, table_name=meta_name, maxconn=MAXCONN
                )
            )
            stores.append(
                PostgresResourceStore(
                    pg_dsn=_POOL_DSN, table_prefix=res_prefix, maxconn=MAXCONN
                )
            )

        # 1) All 2*N stores resolve to the *same* pool object.
        pool = stores[0]._conn_pool
        assert all(s._conn_pool is pool for s in stores), (
            "stores on one DSN must share a single pool"
        )

        # 2) Hold maxconn connections concurrently from the shared pool; this
        #    is the most the pool can ever open at once.
        held = []
        for _ in range(MAXCONN):
            conn = pool.getconn()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            held.append(conn)
        try:
            # 3) Server connection count is bounded by maxconn, not 2*N.
            open_conns = _count_pool_connections(monitor)
        finally:
            for conn in held:
                pool.putconn(conn)

        assert open_conns <= MAXCONN, (
            f"{2 * N_STORES} stores opened {open_conns} connections; "
            f"expected <= maxconn={MAXCONN}"
        )
        assert 2 * N_STORES > MAXCONN  # the decoupling is meaningful
    finally:
        _pg_pool.close_all_pools()
        with monitor.cursor() as cur:
            for name in meta_tables:
                cur.execute(f'DROP TABLE IF EXISTS "{name}" CASCADE')
            for prefix in res_prefixes:
                cur.execute(f'DROP TABLE IF EXISTS "{prefix}resource_index" CASCADE')
                cur.execute(f'DROP TABLE IF EXISTS "{prefix}resource_data" CASCADE')
        monitor.commit()
        monitor.close()
