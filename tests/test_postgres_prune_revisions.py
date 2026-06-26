"""Postgres-backed revision pruning — issue #377 (integration).

Auto-marked ``integration`` by the conftest file-pattern rule
(``test_postgres_*.py``), so excluded from the fast CI lane. Requires a live
Postgres at ``SPECSTAR_TEST_PG_DSN`` (defaults to the repo's local DSN).
"""

import datetime as dt
import io
import os
import uuid

import pytest
from msgspec import Struct

from specstar.resource_manager.basic import Encoding
from specstar.resource_manager.core import ResourceManager, SimpleStorage
from specstar.types import RevisionInfo, RevisionStatus

try:
    import psycopg2

    from specstar.resource_manager.meta_store.postgres import PostgresMetaStore
    from specstar.resource_manager.resource_store.postgres import PostgresResourceStore
except ImportError:  # pragma: no cover
    pytest.skip("psycopg2 not installed", allow_module_level=True)

PG_DSN = os.environ.get(
    "SPECSTAR_TEST_PG_DSN",
    "postgresql://admin:password@localhost:5432/your_database",
)

UTC = dt.timezone.utc


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


class Item(Struct):
    name: str
    value: int = 0


def t(minute: int) -> dt.datetime:
    return dt.datetime(2025, 1, 1, tzinfo=UTC) + dt.timedelta(minutes=minute)


def _suffixes(revs) -> list[int]:
    return sorted(int(r.rsplit(":", 1)[-1]) for r in revs)


def _drop(prefix: str) -> None:
    conn = psycopg2.connect(PG_DSN)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            for table in (
                f"{prefix}resource_index",
                f"{prefix}resource_data",
                f"{prefix}resource_meta",
            ):
                cur.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
    finally:
        conn.close()


@pytest.fixture
def prefix():
    p = f"t377_{uuid.uuid4().hex[:8]}_"
    yield p
    _drop(p)


@pytest.fixture
def pg_resource_store(prefix):
    return PostgresResourceStore(
        pg_dsn=PG_DSN, encoding=Encoding.json, table_prefix=prefix
    )


@pytest.fixture
def pg_rm(prefix):
    storage = SimpleStorage(
        PostgresMetaStore(
            pg_dsn=PG_DSN, encoding=Encoding.json, table_name=f"{prefix}resource_meta"
        ),
        PostgresResourceStore(
            pg_dsn=PG_DSN, encoding=Encoding.json, table_prefix=prefix
        ),
    )
    return ResourceManager(Item, storage=storage)


def _info(resource_id, revision_id, uid, *, created=None):
    now = created or dt.datetime.now(UTC)
    return RevisionInfo(
        uid=uid,
        resource_id=resource_id,
        revision_id=revision_id,
        schema_version=None,
        status=RevisionStatus.stable,
        created_time=now,
        updated_time=now,
        created_by="u",
        updated_by="u",
        parent_revision_id=None,
        data_hash="h",
    )


# ── store-level primitive ─────────────────────────────────────────────


def test_delete_revisions_removes_listed_only(pg_resource_store):
    rid = "res"
    for n in range(1, 4):
        pg_resource_store.save(
            _info(rid, f"{rid}:{n}", uuid.uuid4()), io.BytesIO(f"d{n}".encode())
        )
    pg_resource_store.delete_revisions(rid, [f"{rid}:1", f"{rid}:2"])
    assert sorted(pg_resource_store.list_revisions(rid)) == [f"{rid}:3"]


def test_delete_revisions_idempotent(pg_resource_store):
    rid = "res"
    pg_resource_store.save(_info(rid, f"{rid}:1", uuid.uuid4()), io.BytesIO(b"d"))
    pg_resource_store.delete_revisions(rid, [f"{rid}:9"])  # unknown → no-op
    pg_resource_store.delete_revisions(rid, [f"{rid}:1"])
    pg_resource_store.delete_revisions(rid, [f"{rid}:1"])  # again → no-op
    assert list(pg_resource_store.list_revisions(rid)) == []


def test_delete_revisions_refcounts_shared_uid(pg_resource_store):
    """Two revisions share a uid (the store dedups identical payloads): the
    data row survives until the last referencing index row is deleted."""
    rid = "res"
    shared = uuid.uuid4()
    pg_resource_store.save(_info(rid, f"{rid}:1", shared), io.BytesIO(b"shared"))
    pg_resource_store.save(_info(rid, f"{rid}:2", shared), io.BytesIO(b"shared"))

    pg_resource_store.delete_revisions(rid, [f"{rid}:1"])
    with pg_resource_store.get_data_bytes(rid, f"{rid}:2", None) as fh:
        assert fh.read() == b"shared"

    pg_resource_store.delete_revisions(rid, [f"{rid}:2"])
    assert list(pg_resource_store.list_revisions(rid)) == []


# ── manager-level prune ───────────────────────────────────────────────


def test_prune_keep_last_n(pg_rm):
    with pg_rm.using(user="a") as op:
        info = op.create(Item(name="v1"), now=t(1))
        rid = info.resource_id
        for i in range(2, 6):
            op.update(rid, Item(name=f"v{i}"), now=t(i))

    before = pg_rm.get_meta(rid)
    pruned = pg_rm.prune_revisions(rid, keep_last_n=2, user="a", now=t(50))
    after = pg_rm.get_meta(rid)

    assert _suffixes(pruned) == [1, 2, 3]
    assert _suffixes(pg_rm.list_revisions(rid)) == [4, 5]
    assert after.current_revision_id == before.current_revision_id
    assert after.total_revision_count == 5  # monotonic
    assert pg_rm.get(rid).data.name == "v5"
