"""PostgreSQL bulk read under a memory budget (issue #434).

Needs a live Postgres at ``SPECSTAR_TEST_PG_DSN`` (defaults to the repo's
local DSN); auto-marked ``integration`` by ``tests/conftest.py``.

The point of the Postgres override is that ``octet_length`` reports payload
size **without transferring the payload**, so the batch can be packed to the
budget exactly. The generic fallback cannot do that — it only learns a size
after reading the row, so it always overshoots by one. The packing tests
below therefore double as proof the override is actually being used.
"""

from __future__ import annotations

import datetime as dt
import io
import os
import uuid

import pytest

try:
    import psycopg2

    from specstar.resource_manager.basic import Encoding
    from specstar.resource_manager.resource_store.postgres import (
        PostgresResourceStore,
    )
except ImportError:  # pragma: no cover
    pytest.skip("psycopg2 not installed", allow_module_level=True)

from specstar.types import RevisionInfo, RevisionStatus

PG_DSN = os.environ.get(
    "SPECSTAR_TEST_PG_DSN",
    "postgresql://admin:password@localhost:5432/your_database",
)

_NOW = dt.datetime(2026, 7, 20, tzinfo=dt.timezone.utc)


def _pg_reachable() -> bool:
    try:
        conn = psycopg2.connect(PG_DSN, connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _pg_reachable(), reason="no live Postgres at SPECSTAR_TEST_PG_DSN"
)


@pytest.fixture
def store():
    prefix = f"t{uuid.uuid4().hex[:12]}_"
    st = PostgresResourceStore(
        pg_dsn=PG_DSN, encoding=Encoding.json, table_prefix=prefix
    )
    yield st
    conn = psycopg2.connect(PG_DSN)
    try:
        with conn.cursor() as cur:
            cur.execute(f'DROP TABLE IF EXISTS "{prefix}resource_index"')
            cur.execute(f'DROP TABLE IF EXISTS "{prefix}resource_data"')
        conn.commit()
    finally:
        conn.close()


def _info(resource_id: str) -> RevisionInfo:
    return RevisionInfo(
        uid=uuid.uuid4(),
        resource_id=resource_id,
        revision_id="r1",
        schema_version=None,
        status=RevisionStatus.stable,
        created_time=_NOW,
        updated_time=_NOW,
        created_by="tester",
        updated_by="tester",
    )


def _seed(store, sizes: dict[str, int]) -> list[tuple[str, str, None]]:
    keys: list[tuple[str, str, None]] = []
    for rid, size in sizes.items():
        info = _info(rid)
        store.save(info, io.BytesIO(b"x" * size))
        keys.append((rid, info.revision_id, info.schema_version))
    return keys


def test_octet_length_sizes_the_batch_without_reading_it(store):
    keys = _seed(store, {"a": 10, "b": 20, "c": 30})

    assert store.payload_sizes(keys) == [10, 20, 30]


def test_read_many_packs_the_budget_exactly(store):
    """40 bytes fits a(10)+b(20); c(30) would overflow, so it is left behind.

    The generic fallback would have consumed all three — it can only notice
    the overflow after fetching c. Exact packing here means Postgres sized
    the batch up front.
    """
    keys = _seed(store, {"a": 10, "b": 20, "c": 30})

    data, consumed = store.read_many(keys, max_bytes=40)

    assert consumed == 2
    assert data == {"a": b"x" * 10, "b": b"x" * 20}


def test_read_many_returns_the_whole_batch_when_the_budget_is_ample(store):
    keys = _seed(store, {"a": 10, "b": 20, "c": 30})

    data, consumed = store.read_many(keys, max_bytes=10_000)

    assert consumed == 3
    assert data == {"a": b"x" * 10, "b": b"x" * 20, "c": b"x" * 30}


def test_read_many_always_makes_progress(store):
    keys = _seed(store, {"huge": 5_000})

    data, consumed = store.read_many(keys, max_bytes=1)

    assert consumed == 1
    assert data == {"huge": b"x" * 5_000}


def test_read_many_omits_rows_that_are_not_there(store):
    keys = _seed(store, {"a": 10, "c": 30})
    keys.insert(1, ("ghost", "r1", None))  # never saved

    data, consumed = store.read_many(keys, max_bytes=10_000)

    assert consumed == 3
    assert set(data) == {"a", "c"}


def test_read_many_with_no_items_touches_the_database_not_at_all(store):
    assert store.read_many([], max_bytes=1_000) == ({}, 0)


# ---------------------------------------------------------------------------
# Meta store bulk read — one ANY(...) instead of N queries
# ---------------------------------------------------------------------------


@pytest.fixture
def meta_store():
    from specstar.resource_manager.meta_store.postgres import PostgresMetaStore

    table = f"t{uuid.uuid4().hex[:12]}_resource_meta"
    st = PostgresMetaStore(pg_dsn=PG_DSN, table_name=table)
    yield st
    conn = psycopg2.connect(PG_DSN)
    try:
        with conn.cursor() as cur:
            cur.execute(f'DROP TABLE IF EXISTS "{table}"')
        conn.commit()
    finally:
        conn.close()


def _meta(resource_id: str):
    from specstar.types import ResourceMeta

    return ResourceMeta(
        resource_id=resource_id,
        current_revision_id="r1",
        total_revision_count=1,
        created_time=_NOW,
        updated_time=_NOW,
        created_by="tester",
        updated_by="tester",
        is_deleted=False,
        schema_version=None,
    )


def test_meta_get_many_reads_the_whole_set(meta_store):
    for rid in ("a", "b", "c"):
        meta_store[rid] = _meta(rid)

    found = meta_store.get_many(["a", "b", "c"])

    assert set(found) == {"a", "b", "c"}
    assert found["b"].resource_id == "b"


def test_meta_get_many_omits_unknown_ids(meta_store):
    meta_store["a"] = _meta("a")

    assert set(meta_store.get_many(["a", "ghost"])) == {"a"}


def test_meta_get_many_with_no_ids_issues_no_query(meta_store):
    assert meta_store.get_many([]) == {}
