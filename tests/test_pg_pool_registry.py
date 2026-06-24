"""Process-global PostgreSQL connection-pool registry (#380).

These tests pin the registry contract with a mocked
``ThreadedConnectionPool`` — no live database. They run in the fast CI job
(no ``integration`` marker).
"""

from unittest.mock import MagicMock, patch

import pytest

MOD = "specstar.resource_manager._pg_pool"

DSN = "postgresql://u:p@localhost:5432/db"


def _ctor_patch():
    """Patch the pool constructor so each build yields a distinct object."""
    return patch(
        f"{MOD}.psycopg2.pool.ThreadedConnectionPool",
        side_effect=lambda *a, **k: MagicMock(name="pool"),
    )


@pytest.fixture(autouse=True)
def _reset_registry():
    """Keep the process-global registry from leaking across tests."""
    from specstar.resource_manager import _pg_pool

    _pg_pool.close_all_pools()
    yield
    _pg_pool.close_all_pools()


def test_same_dsn_returns_same_pool():
    from specstar.resource_manager._pg_pool import get_pool

    with _ctor_patch() as ctor:
        p1 = get_pool(DSN, minconn=0, maxconn=16)
        p2 = get_pool(DSN, minconn=0, maxconn=16)

    assert p1 is p2
    assert ctor.call_count == 1


def test_distinct_dsn_returns_distinct_pool():
    from specstar.resource_manager._pg_pool import get_pool

    other = "postgresql://u:p@localhost:5432/other"
    with _ctor_patch() as ctor:
        p1 = get_pool(DSN)
        p2 = get_pool(other)

    assert p1 is not p2
    assert ctor.call_count == 2


def test_equivalent_dsn_forms_collapse_to_one_pool():
    """URI and keyword forms of the same target share a pool."""
    from specstar.resource_manager._pg_pool import get_pool

    keyword = "host=localhost port=5432 dbname=db user=u password=p"
    with _ctor_patch() as ctor:
        p_uri = get_pool(DSN)
        p_kw = get_pool(keyword)

    assert p_uri is p_kw
    assert ctor.call_count == 1


def test_conflicting_pool_size_raises():
    from specstar.resource_manager._pg_pool import get_pool

    with _ctor_patch():
        get_pool(DSN, minconn=0, maxconn=16)
        with pytest.raises(ValueError):
            get_pool(DSN, minconn=0, maxconn=32)


def test_close_all_pools_allows_rebuild():
    from specstar.resource_manager._pg_pool import close_all_pools, get_pool

    with _ctor_patch() as ctor:
        p1 = get_pool(DSN)
        close_all_pools()
        p2 = get_pool(DSN)

    assert p1 is not p2
    assert ctor.call_count == 2


def test_pool_built_with_requested_sizes():
    """minconn/maxconn are passed straight through to the pool ctor."""
    from specstar.resource_manager._pg_pool import get_pool

    with _ctor_patch() as ctor:
        get_pool(DSN, minconn=0, maxconn=8)

    args, kwargs = ctor.call_args
    assert args[0] == 0  # minconn — lazy, no boot-time connection
    assert args[1] == 8  # maxconn


def test_default_pool_is_lazy():
    """Default minconn is 0 so apply() opens no eager connections."""
    from specstar.resource_manager._pg_pool import DEFAULT_MINCONN, get_pool

    assert DEFAULT_MINCONN == 0
    with _ctor_patch() as ctor:
        get_pool(DSN)

    args, _ = ctor.call_args
    assert args[0] == 0
