"""Brute-force vector search via MemoryMetaStore (no pgvector required)."""

from __future__ import annotations

import datetime as dt

from specstar.query_types import (
    DataSearchCondition,
    DataSearchOperator,
    ResourceMetaSearchQuery,
    VectorDistanceCondition,
    VectorDistanceSort,
)
from specstar.resource_manager.meta_store.simple import MemoryMetaStore
from specstar.types import ResourceMeta


def _make_meta(rid: str, *, vector: list[float], doctype: str = "abc") -> ResourceMeta:
    now = dt.datetime(2026, 5, 22, tzinfo=dt.timezone.utc)
    return ResourceMeta(
        resource_id=rid,
        current_revision_id=f"{rid}-rev",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="tester",
        updated_by="tester",
        is_deleted=False,
        indexed_data={"embedding": vector, "doctype": doctype},
    )


# BF1: tracer — filter by cosine distance, get rows whose vector is near query
def test_bf_cosine_filter_returns_near_rows() -> None:
    store = MemoryMetaStore()
    # Vectors aligned with x axis vs orthogonal
    store["a"] = _make_meta("a", vector=[1.0, 0.0])  # cosine dist to [1,0] = 0
    store["b"] = _make_meta("b", vector=[0.0, 1.0])  # cosine dist to [1,0] = 1
    store["c"] = _make_meta("c", vector=[0.9, 0.1])  # cosine dist small

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
    ids = [m.resource_id for m in store.iter_search(q)]
    assert "a" in ids
    assert "c" in ids
    assert "b" not in ids  # b is too far (cosine dist ~= 1)


# BF2: sort by cosine ascending — nearest rows first
def test_bf_cosine_sort_ascending() -> None:
    store = MemoryMetaStore()
    store["a"] = _make_meta("a", vector=[0.9, 0.1])  # close to [1,0]
    store["b"] = _make_meta("b", vector=[0.0, 1.0])  # far
    store["c"] = _make_meta("c", vector=[1.0, 0.0])  # closest

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


# BF3: L2 distance
def test_bf_l2_filter_and_sort() -> None:
    store = MemoryMetaStore()
    store["near"] = _make_meta("near", vector=[1.0, 1.0])
    store["far"] = _make_meta("far", vector=[10.0, 10.0])

    q = ResourceMetaSearchQuery(
        sorts=[
            VectorDistanceSort(
                field_path="embedding",
                query_vector=[0.0, 0.0],
                distance="l2",
            ),
        ],
    )
    ids = [m.resource_id for m in store.iter_search(q)]
    assert ids == ["near", "far"]


# BF3 cont: inner-product distance (lower = more similar by our convention)
def test_bf_ip_distance() -> None:
    store = MemoryMetaStore()
    store["aligned"] = _make_meta("aligned", vector=[1.0, 1.0])  # dot = 2 → dist=-2
    store["opposed"] = _make_meta("opposed", vector=[-1.0, -1.0])  # dot=-2 → dist=2

    q = ResourceMetaSearchQuery(
        sorts=[
            VectorDistanceSort(
                field_path="embedding",
                query_vector=[1.0, 1.0],
                distance="ip",
            ),
        ],
    )
    ids = [m.resource_id for m in store.iter_search(q)]
    assert ids == ["aligned", "opposed"]


# BF4: scalar AND vector conditions compose
def test_bf_scalar_and_vector_filters_compose() -> None:
    store = MemoryMetaStore()
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
    )
    ids = sorted(m.resource_id for m in store.iter_search(q))
    assert ids == ["abc-near"]


# BF5: rows without a vector in indexed_data are excluded from results
def test_bf_missing_vector_excluded() -> None:
    store = MemoryMetaStore()
    store["has"] = _make_meta("has", vector=[1.0, 0.0])
    # Row without "embedding" key
    now = dt.datetime(2026, 5, 22, tzinfo=dt.timezone.utc)
    store["lacks"] = ResourceMeta(
        resource_id="lacks",
        current_revision_id="lacks-rev",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="t",
        updated_by="t",
        is_deleted=False,
        indexed_data={"doctype": "abc"},  # no "embedding"
    )

    q = ResourceMetaSearchQuery(
        conditions=[
            VectorDistanceCondition(
                field_path="embedding",
                query_vector=[1.0, 0.0],
                operator=DataSearchOperator.less_than,
                threshold=1.5,
                distance="cosine",
            ),
        ],
    )
    ids = [m.resource_id for m in store.iter_search(q)]
    assert ids == ["has"]


# BF6: capability flag — memory backend reports brute-force
def test_bf_memory_store_capability_flag() -> None:
    store = MemoryMetaStore()
    assert store.supports_native_vector_search is False
