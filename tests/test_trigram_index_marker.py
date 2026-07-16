"""``TrigramIndex`` — opt-in pg_trgm GIN for substring / fuzzy search on a
text or ``list[str]`` field.

Like :class:`SortIndex`, the marker is opt-in and index-only: no column, no
backfill, no write-path change. ``indexed_data`` stays the single source of
truth, so adding or removing the annotation costs a ``CREATE`` / ``DROP INDEX``
and nothing else — an index's absence can only cost speed, never correctness.

Unlike ``SortIndex`` (scalar-only) it *also* accepts a ``list[str]`` field: the
GIN goes over the serialised-array text ``indexed_data->>'field'`` and coarse-
filters ``.any().contains()`` before an exact per-element recheck.

Service-free by design: ``tests/meta_store/`` is auto-marked ``integration`` and
never runs in CI. Live-Postgres behaviour is pinned by
``tests/meta_store/test_trigram_index.py``.
"""

import json
from typing import Annotated, Optional

import msgspec
import pytest

from specstar.query_types import (
    DataSearchCondition,
    DataSearchOperator,
    DataSearchQuantifier,
)
from specstar.resource_manager.meta_store.postgres import PostgresMetaStore
from specstar.types import TrigramIndex, extract_trigram_index_field_infos


def _builder(list_fields=(), trigram_indexes=()) -> PostgresMetaStore:
    """A store whose SQL builder runs without a live server (see #418's helper)."""
    store = object.__new__(PostgresMetaStore)
    store._list_fields = set(list_fields)
    store._set_columns = {}
    store._sort_indexes = set()
    store._trigram_indexes = set(trigram_indexes)
    return store


def _quant(op, value, quantifier, field_path="keys") -> DataSearchCondition:
    return DataSearchCondition(
        field_path=field_path, operator=op, value=value, quantifier=quantifier
    )


def test_extract_finds_a_scalar_text_field():
    class Foo(msgspec.Struct):
        title: Annotated[str, TrigramIndex()]
        plain: str  # not declared → ignored

    infos = extract_trigram_index_field_infos(Foo)
    assert {i.name: i.is_list for i in infos} == {"title": False}


def test_extract_marks_a_list_str_field_as_list():
    class Foo(msgspec.Struct):
        norm_keys: Annotated[list[str], TrigramIndex()]

    infos = extract_trigram_index_field_infos(Foo)
    assert {i.name: i.is_list for i in infos} == {"norm_keys": True}


def test_extract_rejects_a_numeric_scalar_field():
    class Foo(msgspec.Struct):
        score: Annotated[int, TrigramIndex()]

    with pytest.raises(TypeError, match="text"):
        extract_trigram_index_field_infos(Foo)


def test_extract_rejects_a_non_text_list_field():
    class Foo(msgspec.Struct):
        ids: Annotated[list[int], TrigramIndex()]

    with pytest.raises(TypeError, match="text"):
        extract_trigram_index_field_infos(Foo)


def test_optional_is_peeled_before_the_text_check():
    class Foo(msgspec.Struct):
        title: Annotated[Optional[str], TrigramIndex()] = None
        keys: Annotated[Optional[list[str]], TrigramIndex()] = None

    infos = extract_trigram_index_field_infos(Foo)
    assert {i.name: i.is_list for i in infos} == {"title": False, "keys": True}


def test_marker_nested_in_a_substruct_is_not_extracted():
    """Same reach as SortIndex / SetIndex / Vector: only top-level fields scan."""

    class Inner(msgspec.Struct):
        title: Annotated[str, TrigramIndex()]

    class Outer(msgspec.Struct):
        inner: Inner

    assert extract_trigram_index_field_infos(Outer) == []


def test_marker_is_exported_from_the_top_level_package():
    """Users annotate with ``from specstar import TrigramIndex`` like SortIndex."""
    import specstar

    assert specstar.TrigramIndex is TrigramIndex


# --- .any().eq() membership → GIN-probeable @> (no TrigramIndex needed) ------


def test_any_eq_routes_to_the_top_level_containment_probe():
    """``.any().eq(v)`` is exact element membership, so it can go through the
    shared ``idx_indexed_data_gin`` (``indexed_data @> {"f": [v]}``) instead of a
    per-row ``EXISTS(jsonb_array_elements_text …)`` scan."""
    sql, params = _builder(list_fields=["keys"])._build_condition(
        _quant(DataSearchOperator.equals, "mol", DataSearchQuantifier.any)
    )
    assert sql == "indexed_data @> %s::jsonb"
    assert json.loads(params[0]) == {"keys": ["mol"]}


def test_all_eq_is_not_membership_and_keeps_the_universal_exists():
    """``.all().eq(v)`` means EVERY element equals v — not membership — so the
    ``@>`` short-circuit must not swallow it."""
    sql, _ = _builder()._build_condition(
        _quant(DataSearchOperator.equals, "mol", DataSearchQuantifier.all)
    )
    assert "@>" not in sql
    assert "NOT EXISTS" in sql


def test_any_contains_is_substring_not_membership_and_keeps_exists():
    """``.any().contains(v)`` is substring, which ``@>`` (membership) cannot do."""
    sql, _ = _builder()._build_condition(
        _quant(DataSearchOperator.contains, "ol", DataSearchQuantifier.any)
    )
    assert "@>" not in sql
    assert "strpos(val" in sql


def test_any_eq_none_keeps_exists_not_a_containment_probe():
    """``@> {"f": [null]}`` would MATCH a stored JSON null; the reference returns
    Unknown for ``== None``. ``None`` must stay on the EXISTS path (see
    ``_gin_probeable``)."""
    sql, _ = _builder()._build_condition(
        _quant(DataSearchOperator.equals, None, DataSearchQuantifier.any)
    )
    assert "@>" not in sql
