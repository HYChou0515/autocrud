"""PostgresBackendProvider threads pool sizing from connection options (#380)."""

from unittest.mock import MagicMock, patch

import pytest

REG = "specstar.resource_manager._pg_pool"
DSN = "postgresql://u:p@localhost:5432/db"


@pytest.fixture(autouse=True)
def _reset_registry():
    from specstar.resource_manager import _pg_pool

    _pg_pool.close_all_pools()
    yield
    _pg_pool.close_all_pools()


def _provider_patches():
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


def test_maxconn_minconn_options_flow_to_pool():
    from specstar.backend import BackendDefaults, PostgresBackendProvider

    ctor, init_meta, detect, init_res = _provider_patches()
    with ctor as ctor_mock, init_meta, detect, init_res:
        PostgresBackendProvider().build_meta(
            model_name="thing",
            options={"dsn": DSN, "minconn": 2, "maxconn": 8},
            defaults=BackendDefaults(),
        )

    args, kwargs = ctor_mock.call_args
    assert args[0] == 2  # minconn
    assert args[1] == 8  # maxconn


def test_pool_options_default_when_absent():
    from specstar.backend import BackendDefaults, PostgresBackendProvider
    from specstar.resource_manager._pg_pool import DEFAULT_MAXCONN, DEFAULT_MINCONN

    ctor, init_meta, detect, init_res = _provider_patches()
    with ctor as ctor_mock, init_meta, detect, init_res:
        PostgresBackendProvider().build_resource(
            model_name="thing",
            options={"dsn": DSN},
            defaults=BackendDefaults(),
        )

    args, _ = ctor_mock.call_args
    assert args[0] == DEFAULT_MINCONN
    assert args[1] == DEFAULT_MAXCONN
