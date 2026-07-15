"""#418: ``SortIndex`` — opt-in btree expression index for a stabilised field.

A jsonb GIN answers ``@>``/``?``/``?|``/``?&`` and nothing else: it is a value->row
inverted index with no ordering, so ranges and ``ORDER BY`` can never be served by
it at any index size (#416 covers what it *can* serve). A btree over the extract
``(indexed_data->'f')`` serves range, ORDER BY and equality from ONE index.

The marker is opt-in and index-only: no column, no backfill, no write-path change.
``indexed_data`` stays the single source of truth, so adding or removing the
annotation costs a ``CREATE``/``DROP INDEX`` and nothing else — an index's absence
can only cost speed, never correctness.

Service-free by design: ``tests/meta_store/`` is auto-marked ``integration`` and
never runs in CI. Live-Postgres behaviour is pinned by
``tests/meta_store/test_sort_index.py``.
"""

from typing import Annotated, Optional

import msgspec
import pytest

from specstar.query_types import DataSearchCondition, DataSearchOperator
from specstar.resource_manager.meta_store.postgres import PostgresMetaStore
from specstar.types import SortIndex, extract_sort_index_field_infos


def _builder(sort_indexes=()) -> PostgresMetaStore:
    """A store whose SQL builder runs without a live server (see #416's helper)."""
    store = object.__new__(PostgresMetaStore)
    store._list_fields = set()
    store._set_columns = {}
    store._sort_indexes = set(sort_indexes)
    return store


def _cond(op, value, field_path="score"):
    return DataSearchCondition(field_path=field_path, operator=op, value=value)


# --- the marker ----------------------------------------------------------


def test_extract_finds_the_marker_and_infers_the_value_type():
    class Foo(msgspec.Struct):
        score: Annotated[int, SortIndex()]
        ratio: Annotated[float, SortIndex()]
        name: Annotated[str, SortIndex()]
        plain: int  # not declared → ignored

    infos = extract_sort_index_field_infos(Foo)
    assert {i.name: i.value_type for i in infos} == {
        "score": int,
        "ratio": float,
        "name": str,
    }


def test_optional_is_peeled_to_the_underlying_type():
    """``None`` sorts into its own jsonb band, which is the desired SQL semantics."""

    class Foo(msgspec.Struct):
        score: Annotated[Optional[int], SortIndex()] = None

    assert [i.value_type for i in extract_sort_index_field_infos(Foo)] == [int]


def test_marker_nested_in_a_substruct_is_not_extracted():
    """Same reach as SetIndex / Vector: only top-level struct fields are scanned."""

    class Inner(msgspec.Struct):
        score: Annotated[int, SortIndex()]

    class Outer(msgspec.Struct):
        inner: Inner

    assert extract_sort_index_field_infos(Outer) == []


def test_a_list_field_cannot_take_a_sort_index():
    """A btree over a jsonb array would order by the whole array, which is not
    what anyone means by sorting. ``SetIndex`` is the marker for list fields."""

    class Foo(msgspec.Struct):
        tags: Annotated[list[str], SortIndex()]

    with pytest.raises(TypeError, match="SetIndex"):
        extract_sort_index_field_infos(Foo)


def test_markers_compare_by_identity_like_setindex():
    assert SortIndex() == SortIndex()
    assert len({SortIndex(), SortIndex()}) == 1


# --- range SQL -----------------------------------------------------------


@pytest.mark.parametrize(
    ("op", "sql_op"),
    [
        (DataSearchOperator.greater_than, ">"),
        (DataSearchOperator.greater_than_or_equal, ">="),
        (DataSearchOperator.less_than, "<"),
        (DataSearchOperator.less_than_or_equal, "<="),
    ],
)
def test_range_on_an_annotated_field_uses_the_indexable_jsonb_form(op, sql_op):
    """``(indexed_data->>'f')::numeric > %s`` is a per-row cast no index can serve.

    ``indexed_data->'f' > %s::jsonb`` matches the indexed expression exactly, and
    jsonb orders numbers numerically (``9 > 100`` is correctly false).
    """
    import json

    sql, params = _builder(sort_indexes=["score"])._build_condition(_cond(op, 50))
    assert sql == f"indexed_data->'score' {sql_op} %s::jsonb"
    assert json.loads(params[0]) == 50


def test_range_on_an_unannotated_field_keeps_the_numeric_cast():
    """Without an index the jsonb form is SLOWER (the cast form parallelises), so
    the rewrite must be opt-in rather than global."""
    sql, _ = _builder()._build_condition(_cond(DataSearchOperator.greater_than, 50))
    assert sql == "(indexed_data->>'score')::numeric > %s"


def test_range_preserves_the_json_type_of_the_value():
    import json

    sql, params = _builder(sort_indexes=["name"])._build_condition(
        _cond(DataSearchOperator.greater_than, "abc", field_path="name")
    )
    assert json.loads(params[0]) == "abc"
    assert sql == "indexed_data->'name' > %s::jsonb"


def test_equality_still_prefers_containment_from_416():
    """#416's ``@>`` probe is served by the shared GIN and stays the equality path;
    a SortIndex field does not need its own equality rewrite."""
    sql, _ = _builder(sort_indexes=["score"])._build_condition(
        _cond(DataSearchOperator.equals, 50)
    )
    assert sql == "indexed_data @> %s::jsonb"
