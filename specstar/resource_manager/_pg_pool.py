"""Process-global PostgreSQL connection-pool registry (#380).

Every model historically built its own meta + resource store, and every
store opened its own ``SimpleConnectionPool``. Connection count therefore
scaled with ``models * 2 * replicas`` and exhausted ``max_connections``
before serving any real traffic.

This module decouples that: all stores sharing a DSN share **one**
process-global :class:`psycopg2.pool.ThreadedConnectionPool`. Connection
count is bounded by the number of distinct DSNs, not the number of models.

Pools are owned by this registry for the lifetime of the process; stores
must not close them. :func:`close_all_pools` is the single explicit
shutdown / test-teardown entry point.
"""

from __future__ import annotations

import threading
from typing import Any

try:
    import psycopg2
    import psycopg2.pool
except ImportError:  # pragma: no cover
    psycopg2 = None  # type: ignore[assignment]  # ty:ignore[invalid-assignment]

#: Lazy by default — open no connection until first checkout, so ``apply()``
#: no longer triggers a boot-time connection storm.
DEFAULT_MINCONN = 0
#: Per-process, per-DSN ceiling on concurrent connections — shared across
#: every model / meta / resource store on that DSN. Tune via
#: ``ConnectionProfile.options.maxconn`` for high-concurrency deployments.
DEFAULT_MAXCONN = 16

_lock = threading.Lock()
_pools: dict[Any, Any] = {}
_configs: dict[Any, tuple[int, int]] = {}


def get_pool(
    dsn: str, *, minconn: int = DEFAULT_MINCONN, maxconn: int = DEFAULT_MAXCONN
):
    """Return the shared pool for *dsn*, creating it on first use.

    The pool is keyed by a normalized DSN so equivalent connection strings
    (URI vs keyword form, reordered params) collapse onto one pool.
    First-writer-wins: the first caller fixes the pool size. A later caller
    requesting a different ``(minconn, maxconn)`` for the same DSN raises
    ``ValueError`` rather than silently reusing a mismatched pool.
    """
    key = _normalize_dsn(dsn)
    with _lock:
        existing = _pools.get(key)
        if existing is not None:
            if _configs[key] != (minconn, maxconn):
                raise ValueError(
                    f"connection pool for this DSN already exists with "
                    f"minconn/maxconn={_configs[key]}, cannot rebind to "
                    f"{(minconn, maxconn)}; use one consistent pool size per DSN"
                )
            return existing
        # Force every connection's session TimeZone to UTC. SpecStar normalises
        # all datetimes to tz-aware UTC (see ResourceManager), and the SQL
        # metastore's naive TIMESTAMP columns then store/read a UTC wall-clock
        # regardless of the server's default timezone — which keeps time filters
        # and the datetime Min/Max push-down (#406) coordinate-free.
        pool = psycopg2.pool.ThreadedConnectionPool(
            minconn, maxconn, dsn=dsn, options="-c timezone=UTC"
        )
        _pools[key] = pool
        _configs[key] = (minconn, maxconn)
        return pool


def close_all_pools() -> None:
    """Close every registered pool and clear the registry.

    The explicit lifecycle entry point — for graceful shutdown and test
    teardown. Stores never call this on garbage collection.
    """
    with _lock:
        for pool in _pools.values():
            try:
                pool.closeall()
            except Exception:
                pass
        _pools.clear()
        _configs.clear()


def _normalize_dsn(dsn: str) -> Any:
    """Canonicalize *dsn* so equivalent strings map to the same key.

    Falls back to the raw string when psycopg2 cannot parse it.
    """
    try:
        parsed = psycopg2.extensions.parse_dsn(dsn)
    except Exception:
        return dsn
    return tuple(sorted(parsed.items()))
