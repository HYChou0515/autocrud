"""Tests for vector-aware additions to query_types.py."""

from __future__ import annotations

from specstar.query_types import (
    DataSearchOperator,
    ResourceMetaSortDirection,
    VectorDistanceCondition,
    VectorDistanceSort,
)


# VC1: VectorDistanceCondition constructs with required fields
def test_vector_distance_condition_constructs() -> None:
    cond = VectorDistanceCondition(
        field_path="embedding",
        query_vector=[0.1, 0.2, 0.3],
        operator=DataSearchOperator.less_than,
        threshold=0.3,
    )
    assert cond.field_path == "embedding"
    assert cond.query_vector == [0.1, 0.2, 0.3]
    assert cond.operator == DataSearchOperator.less_than
    assert cond.threshold == 0.3
    assert cond.distance is None  # default


# VC2: query_vector accepts a str (will be encoded at query time)
def test_vector_distance_condition_accepts_str() -> None:
    cond = VectorDistanceCondition(
        field_path="embedding",
        query_vector="hello world",
        operator=DataSearchOperator.less_than,
        threshold=0.3,
        distance="cosine",
    )
    assert cond.query_vector == "hello world"
    assert cond.distance == "cosine"


# VC3: VectorDistanceSort defaults to ascending
def test_vector_distance_sort_defaults_ascending() -> None:
    s = VectorDistanceSort(
        field_path="embedding",
        query_vector=[0.1, 0.2, 0.3],
    )
    assert s.field_path == "embedding"
    assert s.query_vector == [0.1, 0.2, 0.3]
    assert s.direction == ResourceMetaSortDirection.ascending
    assert s.distance is None


# VC4: ResourceMetaSearchQuery accepts vector primitives in conditions/sorts
def test_resource_meta_search_query_accepts_vector_primitives() -> None:
    from specstar.query_types import (
        DataSearchCondition,
        ResourceMetaSearchQuery,
    )

    q = ResourceMetaSearchQuery(
        conditions=[
            DataSearchCondition(
                field_path="doctype",
                operator=DataSearchOperator.equals,
                value="abc",
            ),
            VectorDistanceCondition(
                field_path="embedding",
                query_vector=[0.1, 0.2, 0.3, 0.4],
                operator=DataSearchOperator.less_than,
                threshold=0.3,
            ),
        ],
        sorts=[
            VectorDistanceSort(
                field_path="embedding",
                query_vector=[0.1, 0.2, 0.3, 0.4],
            ),
        ],
        limit=10,
    )
    assert len(q.conditions) == 2
    assert isinstance(q.conditions[1], VectorDistanceCondition)
    assert isinstance(q.sorts[0], VectorDistanceSort)

    # round-trip through msgspec — proves the union is correctly declared,
    # not just accepted by Python at construction time
    import msgspec

    encoded = msgspec.json.encode(q)
    decoded = msgspec.json.decode(encoded, type=type(q))
    assert isinstance(decoded.conditions[1], VectorDistanceCondition)
    assert isinstance(decoded.sorts[0], VectorDistanceSort)
