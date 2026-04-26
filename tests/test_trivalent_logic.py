"""Trivalent (three-valued) search semantics, exercised through ``is_match_query``.

``is_match_query`` is the public matching predicate used by every meta_store
backend. It returns ``True`` only when the trivalent evaluator returns
``True``; both ``False`` (definitely no match) and ``Unknown`` (a missing or
NULL field, which SQL would compare as ``NULL``) collapse to a non-match —
which is what the user observes as "this resource is excluded from results".

The interesting distinction is the ``NOT`` operator: in classical logic
``NOT(missing == 1)`` would be ``True`` (and the resource would match), but
trivalent logic propagates Unknown through ``NOT``, so the resource is still
excluded.
"""

from __future__ import annotations

import datetime as dt

from autocrud.query_types import (
    DataSearchCondition,
    DataSearchGroup,
    DataSearchLogicOperator,
    DataSearchOperator,
    ResourceMetaSearchQuery,
)
from autocrud.resource_manager.basic import is_match_query
from autocrud.types import ResourceMeta


def _meta(indexed: dict | None) -> ResourceMeta:
    now = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    return ResourceMeta(
        current_revision_id="r1",
        resource_id="x",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="alice",
        updated_by="alice",
        indexed_data=indexed if indexed is not None else {},
    )


def _query_with(condition) -> ResourceMetaSearchQuery:
    return ResourceMetaSearchQuery(data_conditions=[condition])


def test_missing_key_is_unknown_and_excluded():
    cond = DataSearchCondition(
        field_path="missing", operator=DataSearchOperator.equals, value=1
    )
    assert is_match_query(_meta({"existing": 1}), _query_with(cond)) is False


def test_not_of_missing_key_stays_unknown_and_excluded():
    """trivalent NOT(Unknown) = Unknown; binary NOT(False) would be True."""
    inner = DataSearchCondition(
        field_path="missing", operator=DataSearchOperator.equals, value=1
    )
    group = DataSearchGroup(operator=DataSearchLogicOperator.not_op, conditions=[inner])
    assert is_match_query(_meta({"existing": 1}), _query_with(group)) is False


def test_not_of_missing_inequality_stays_unknown_and_excluded():
    inner = DataSearchCondition(
        field_path="missing", operator=DataSearchOperator.not_equals, value=1
    )
    group = DataSearchGroup(operator=DataSearchLogicOperator.not_op, conditions=[inner])
    assert is_match_query(_meta({"existing": 1}), _query_with(group)) is False


def test_null_field_equality_is_unknown_and_excluded():
    cond = DataSearchCondition(
        field_path="null_field", operator=DataSearchOperator.equals, value=1
    )
    assert is_match_query(_meta({"null_field": None}), _query_with(cond)) is False


def test_exists_returns_definite_false_for_missing_key():
    cond = DataSearchCondition(
        field_path="missing", operator=DataSearchOperator.exists, value=True
    )
    assert is_match_query(_meta({"existing": 1}), _query_with(cond)) is False


def test_not_exists_returns_definite_true_for_missing_key():
    inner = DataSearchCondition(
        field_path="missing", operator=DataSearchOperator.exists, value=True
    )
    group = DataSearchGroup(operator=DataSearchLogicOperator.not_op, conditions=[inner])
    assert is_match_query(_meta({"existing": 1}), _query_with(group)) is True


def test_isna_returns_definite_true_for_missing_key():
    cond = DataSearchCondition(
        field_path="missing", operator=DataSearchOperator.isna, value=True
    )
    assert is_match_query(_meta({"existing": 1}), _query_with(cond)) is True


def test_not_isna_returns_definite_false_for_missing_key():
    inner = DataSearchCondition(
        field_path="missing", operator=DataSearchOperator.isna, value=True
    )
    group = DataSearchGroup(operator=DataSearchLogicOperator.not_op, conditions=[inner])
    assert is_match_query(_meta({"existing": 1}), _query_with(group)) is False


def test_unknown_and_true_is_unknown_and_excluded():
    """trivalent Unknown AND True stays Unknown; user sees exclusion."""
    cond_unknown = DataSearchCondition(
        field_path="missing", operator=DataSearchOperator.equals, value=1
    )
    cond_true = DataSearchCondition(
        field_path="a", operator=DataSearchOperator.equals, value=1
    )
    group = DataSearchGroup(
        operator=DataSearchLogicOperator.and_op,
        conditions=[cond_unknown, cond_true],
    )
    assert is_match_query(_meta({"a": 1}), _query_with(group)) is False


def test_unknown_or_true_is_true_and_included():
    """trivalent Unknown OR True = True; user sees the resource match."""
    cond_unknown = DataSearchCondition(
        field_path="missing", operator=DataSearchOperator.equals, value=1
    )
    cond_true = DataSearchCondition(
        field_path="a", operator=DataSearchOperator.equals, value=1
    )
    group = DataSearchGroup(
        operator=DataSearchLogicOperator.or_op,
        conditions=[cond_unknown, cond_true],
    )
    assert is_match_query(_meta({"a": 1}), _query_with(group)) is True


def test_unknown_or_false_stays_unknown_and_excluded():
    cond_unknown = DataSearchCondition(
        field_path="missing", operator=DataSearchOperator.equals, value=1
    )
    cond_false = DataSearchCondition(
        field_path="a", operator=DataSearchOperator.equals, value=2
    )
    group = DataSearchGroup(
        operator=DataSearchLogicOperator.or_op,
        conditions=[cond_unknown, cond_false],
    )
    assert is_match_query(_meta({"a": 1}), _query_with(group)) is False
