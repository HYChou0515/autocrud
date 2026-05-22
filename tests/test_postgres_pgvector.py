"""Integration tests for PostgresMetaStore + pgvector."""

from __future__ import annotations

import datetime as dt
import uuid

import psycopg2
import pytest

from specstar.query_types import (
    DataSearchCondition,
    DataSearchOperator,
    ResourceMetaSearchQuery,
    VectorDistanceCondition,
    VectorDistanceSort,
)
from specstar.resource_manager.basic import Encoding
from specstar.resource_manager.meta_store.postgres import PostgresMetaStore
from specstar.types import ResourceMeta

PG_DSN = "postgresql://admin:password@localhost:5432/your_database"


@pytest.fixture
def store():
    """Fresh PostgresMetaStore with a unique table name per test."""
    table_name = f"vec_test_{uuid.uuid4().hex[:8]}"
    s = PostgresMetaStore(pg_dsn=PG_DSN, encoding=Encoding.json, table_name=table_name)
    yield s
    # Cleanup
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE')
    finally:
        conn.close()


def _make_meta(rid: str, *, vector: list[float], doctype: str = "abc") -> ResourceMeta:
    now = dt.datetime(2026, 5, 22)
    return ResourceMeta(
        resource_id=rid,
        current_revision_id=f"{rid}-rev",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="t",
        updated_by="t",
        is_deleted=False,
        indexed_data={"embedding": vector, "doctype": doctype},
    )


# PV1: capability flag is True when pgvector extension is available
def test_pv_capability_flag_true_when_pgvector_present(store: PostgresMetaStore) -> None:
    assert store.supports_native_vector_search is True


# PV2: ensure_vector_column creates a vector(N) column + HNSW index
def test_pv_ensure_vector_column_creates_col_and_index(
    store: PostgresMetaStore,
) -> None:
    store.ensure_vector_column("embedding", dim=4, distance="cosine")

    conn = psycopg2.connect(PG_DSN)
    try:
        with conn.cursor() as cur:
            # Column exists with vector type
            cur.execute(
                f"""
                SELECT column_name, udt_name
                FROM information_schema.columns
                WHERE table_name = '{store.table_name}'
                  AND column_name = 'vec_embedding'
                """
            )
            row = cur.fetchone()
            assert row is not None
            assert row[1] == "vector"

            # HNSW index exists for this column
            cur.execute(
                f"""
                SELECT indexname FROM pg_indexes
                WHERE tablename = '{store.table_name}'
                  AND indexname LIKE '%embedding%'
                """
            )
            assert cur.fetchone() is not None
    finally:
        conn.close()


# PV3: cosine distance filter executes natively via SQL
def test_pv_cosine_filter_sql(store: PostgresMetaStore) -> None:
    store.ensure_vector_column("embedding", dim=2, distance="cosine")

    store["a"] = _make_meta("a", vector=[1.0, 0.0])
    store["b"] = _make_meta("b", vector=[0.0, 1.0])
    store["c"] = _make_meta("c", vector=[0.9, 0.1])

    q = ResourceMetaSearchQuery(
        conditions=[
            VectorDistanceCondition(
                field_path="embedding",
                query_vector=[1.0, 0.0],
                operator=DataSearchOperator.less_than,
                threshold=0.3,
                distance="cosine",
            ),
        ],
    )
    ids = sorted(m.resource_id for m in store.iter_search(q))
    assert "a" in ids
    assert "c" in ids
    assert "b" not in ids


# PV4: cosine sort via ORDER BY — nearest rows first
def test_pv_cosine_sort_sql(store: PostgresMetaStore) -> None:
    store.ensure_vector_column("embedding", dim=2, distance="cosine")

    store["a"] = _make_meta("a", vector=[0.9, 0.1])
    store["b"] = _make_meta("b", vector=[0.0, 1.0])
    store["c"] = _make_meta("c", vector=[1.0, 0.0])

    q = ResourceMetaSearchQuery(
        sorts=[
            VectorDistanceSort(
                field_path="embedding",
                query_vector=[1.0, 0.0],
                distance="cosine",
            ),
        ],
    )
    ids = [m.resource_id for m in store.iter_search(q)]
    assert ids == ["c", "a", "b"]


# PV5: dim > HNSW_MAX_DIM (2000) is truncated to first 2000 in the indexed col
def test_pv_dim_over_limit_truncates(store: PostgresMetaStore) -> None:
    big_dim = 2500
    store.ensure_vector_column("big_vec", dim=big_dim, distance="cosine")

    # Verify the column was created with vector(2000), not vector(2500)
    conn = psycopg2.connect(PG_DSN)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT atttypmod
                FROM pg_attribute
                JOIN pg_class ON attrelid = pg_class.oid
                WHERE relname = '{store.table_name}'
                  AND attname = 'vec_big_vec'
                """
            )
            row = cur.fetchone()
            # pgvector stores dim directly in atttypmod
            assert row is not None
            assert row[0] == store.HNSW_MAX_DIM
    finally:
        conn.close()

    # Writing a 2500-dim vector → first 2000 are stored
    long_vec = [float(i % 7) / 10 for i in range(big_dim)]
    now = dt.datetime(2026, 5, 22)
    meta = ResourceMeta(
        resource_id="x",
        current_revision_id="x-rev",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="t",
        updated_by="t",
        is_deleted=False,
        indexed_data={"big_vec": long_vec},
    )
    store["x"] = meta
    # Query with prefix of stored vector → must match
    q = ResourceMetaSearchQuery(
        conditions=[
            VectorDistanceCondition(
                field_path="big_vec",
                query_vector=long_vec,  # full-length; framework truncates to 2000
                operator=DataSearchOperator.less_than,
                threshold=0.01,
                distance="cosine",
            ),
        ],
    )
    ids = [m.resource_id for m in store.iter_search(q)]
    assert ids == ["x"]


# PV6: scalar (jsonb) + vector conditions compose in WHERE
def test_pv_scalar_and_vector_compose(store: PostgresMetaStore) -> None:
    store.ensure_vector_column("embedding", dim=2, distance="cosine")

    store["abc-near"] = _make_meta("abc-near", vector=[1.0, 0.0], doctype="abc")
    store["abc-far"] = _make_meta("abc-far", vector=[0.0, 1.0], doctype="abc")
    store["xyz-near"] = _make_meta("xyz-near", vector=[1.0, 0.0], doctype="xyz")

    q = ResourceMetaSearchQuery(
        conditions=[
            DataSearchCondition(
                field_path="doctype",
                operator=DataSearchOperator.equals,
                value="abc",
            ),
            VectorDistanceCondition(
                field_path="embedding",
                query_vector=[1.0, 0.0],
                operator=DataSearchOperator.less_than,
                threshold=0.3,
                distance="cosine",
            ),
        ],
        sorts=[
            VectorDistanceSort(
                field_path="embedding",
                query_vector=[1.0, 0.0],
                distance="cosine",
            ),
        ],
        limit=10,
    )
    ids = [m.resource_id for m in store.iter_search(q)]
    assert ids == ["abc-near"]
