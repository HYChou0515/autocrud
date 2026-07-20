"""Tests for QB vector methods: cosine / l2 / ip on Field."""

from __future__ import annotations

import pytest

from specstar.query import QB, Query
from specstar.query_types import (
    DataSearchOperator,
    ResourceMetaSortDirection,
    VectorDistanceCondition,
    VectorDistanceSort,
)


def _vc(cb) -> VectorDistanceCondition:
    """Pull the VectorDistanceCondition out of a ConditionBuilder."""
    return cb._condition


# QB1 + QB2: Field.cosine(q) returns expr; expr < t builds a vector cond
def test_qb_cosine_returns_expr_with_distance() -> None:
    expr = QB["embedding"].cosine([0.1, 0.2, 0.3])
    cb = expr < 0.3
    cond = _vc(cb)
    assert isinstance(cond, VectorDistanceCondition)
    assert cond.field_path == "embedding"
    assert cond.distance == "cosine"
    assert cond.query_vector == [0.1, 0.2, 0.3]
    assert cond.operator == DataSearchOperator.less_than
    assert cond.threshold == 0.3


# QB3: lte / gt / gte all produce VectorDistanceCondition with right operator
def test_qb_comparison_operators_cover_all_four() -> None:
    q = [0.1, 0.2, 0.3]
    assert (
        _vc(QB["e"].cosine(q) <= 0.5).operator == DataSearchOperator.less_than_or_equal
    )
    assert _vc(QB["e"].cosine(q) > 0.5).operator == DataSearchOperator.greater_than
    assert (
        _vc(QB["e"].cosine(q) >= 0.5).operator
        == DataSearchOperator.greater_than_or_equal
    )


# QB4: l2 and ip methods carry the correct distance metric
def test_qb_l2_and_ip_methods() -> None:
    q = [0.1, 0.2]
    assert _vc(QB["e"].l2(q) < 1.0).distance == "l2"
    assert _vc(QB["e"].ip(q) > 0.5).distance == "ip"


# QB5: passing expr to .sort() yields ascending VectorDistanceSort
def test_qb_expr_passed_to_sort_yields_ascending_sort() -> None:
    q = [0.1, 0.2, 0.3]
    query = Query().sort(QB["embedding"].cosine(q)).limit(10).build()
    assert len(query.sorts) == 1
    s = query.sorts[0]
    assert isinstance(s, VectorDistanceSort)
    assert s.field_path == "embedding"
    assert s.query_vector == q
    assert s.direction == ResourceMetaSortDirection.ascending
    assert s.distance == "cosine"


# QB6: .desc() produces descending sort
def test_qb_expr_desc_yields_descending_sort() -> None:
    q = [0.1, 0.2]
    query = Query().sort(QB["e"].cosine(q).desc()).build()
    s = query.sorts[0]
    assert isinstance(s, VectorDistanceSort)
    assert s.direction == ResourceMetaSortDirection.descending


# QB7: vector condition composes with scalar conditions via &
def test_qb_vector_condition_composes_with_and() -> None:
    q = [0.1, 0.2, 0.3]
    # ConditionBuilder is itself a Query, so chain .sort().limit().build() on it
    query = (
        ((QB["doctype"] == "abc") & (QB["vec"].cosine(q) < 0.3))
        .sort(QB["vec"].cosine(q))
        .limit(10)
        .build()
    )

    assert len(query.conditions) == 1
    from specstar.query_types import DataSearchGroup

    group = query.conditions[0]
    assert isinstance(group, DataSearchGroup)
    # Group has both a scalar condition and a vector-distance condition
    types_in_group = {type(c) for c in group.conditions}
    assert VectorDistanceCondition in types_in_group
    # sort wired up
    assert isinstance(query.sorts[0], VectorDistanceSort)
    assert query.limit == 10
