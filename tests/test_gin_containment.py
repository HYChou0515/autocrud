"""#416: indexed_data filters must use the GIN, via ``@>`` containment.

``indexed_data->>'f' = %s`` is a function call on every row, so Postgres seq-scans
the whole table and the GIN it already maintains is never used. Rewriting to
top-level containment (``indexed_data @> '{"f": "v"}'``) is served by that index.

These tests pin the generated SQL and live in CI's service-free lane on purpose:
``tests/meta_store/`` is auto-marked ``integration`` and never runs in CI, so a
regression there would be invisible. Cross-backend result parity is pinned by
``tests/meta_store/test_gin_containment_parity.py``.
"""

import json
from enum import Enum

import pytest

from specstar.query_types import (
    DataSearchCondition,
    DataSearchOperator,
    FieldTransform,
)
from specstar.resource_manager.meta_store.postgres import PostgresMetaStore


def _builder(list_fields=(), set_columns=None) -> PostgresMetaStore:
    """A store whose SQL builder runs without a live server.

    ``__init__`` eagerly opens a pool and creates tables; ``_build_condition``
    only reads ``_list_fields`` / ``_set_columns``, so bypassing it keeps these
    tests service-free.
    """
    store = object.__new__(PostgresMetaStore)
    store._list_fields = set(list_fields)
    store._set_columns = dict(set_columns or {})
    return store


def _cond(op, value, field_path="collection_id", transform=None):
    return DataSearchCondition(
        field_path=field_path, operator=op, value=value, transform=transform
    )


class Colour(str, Enum):
    red = "red"


class Level(Enum):
    high = 3


# --- equality ------------------------------------------------------------


def test_equals_uses_top_level_containment_so_the_gin_can_serve_it():
    sql, params = _builder()._build_condition(_cond(DataSearchOperator.equals, "c1"))
    assert sql == "indexed_data @> %s::jsonb"
    assert json.loads(params[0]) == {"collection_id": "c1"}
    assert "->>" not in sql  # the seq-scan forcing extraction is gone


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(5000, id="int"),
        pytest.param(1.5, id="float"),
        pytest.param(True, id="bool"),
        pytest.param("5000", id="str"),
    ],
)
def test_equals_preserves_the_json_type_of_the_value(value):
    """``@>`` is type-strict: ``{"n": "5000"}`` does NOT match a stored ``5000``.

    ``str(value)`` would silently return zero rows, so the value must be encoded
    with its real JSON type — matching how the write path stores it
    (``json.dumps(meta.indexed_data)``).
    """
    sql, params = _builder()._build_condition(
        _cond(DataSearchOperator.equals, value, field_path="n")
    )
    assert sql == "indexed_data @> %s::jsonb"
    assert json.loads(params[0]) == {"n": value}
    assert type(json.loads(params[0])["n"]) is type(value)


def test_equals_none_is_not_rewritten():
    """The reference matcher returns Unknown for ``field == None`` (no match).

    ``@> '{"f": null}'`` would instead MATCH rows storing a JSON null — a
    behaviour change. #416 is a speed change only, so ``None`` keeps the old path.
    """
    sql, _ = _builder()._build_condition(_cond(DataSearchOperator.equals, None))
    assert "@>" not in sql


def test_equals_with_a_transform_is_not_rewritten():
    """``@>`` matches the STORED value; a transform compares a derived one."""
    sql, _ = _builder()._build_condition(
        _cond(DataSearchOperator.equals, 3, transform=FieldTransform.length)
    )
    assert "@>" not in sql
    assert "jsonb_array_length" in sql


def test_equals_on_a_list_value_stays_exact_equality_not_containment():
    """``{"f": [1, 2, 3]} @> {"f": [1]}`` is true — but ``[1,2,3] != [1]``.

    Containment is the wrong operator for equality on a composite value.
    """
    sql, _ = _builder()._build_condition(_cond(DataSearchOperator.equals, [1]))
    assert "indexed_data->'collection_id' = %s::jsonb" == sql


def test_enum_is_normalised_to_its_value_like_the_reference_matcher():
    """``basic.py`` compares against ``condition.value.value`` for Enums.

    Without normalising, ``json.dumps(Level.high)`` raises TypeError outright.
    """
    _, params = _builder()._build_condition(
        _cond(DataSearchOperator.equals, Colour.red)
    )
    assert json.loads(params[0]) == {"collection_id": "red"}

    _, params = _builder()._build_condition(
        _cond(DataSearchOperator.equals, Level.high)
    )
    assert json.loads(params[0]) == {"collection_id": 3}


# --- in_list -------------------------------------------------------------


def test_in_list_becomes_an_or_of_containments():
    """Postgres bitmap-ORs the probes on the one GIN."""
    sql, params = _builder()._build_condition(
        _cond(DataSearchOperator.in_list, ["c1", "c2"])
    )
    assert sql == "(indexed_data @> %s::jsonb OR indexed_data @> %s::jsonb)"
    assert [json.loads(p) for p in params] == [
        {"collection_id": "c1"},
        {"collection_id": "c2"},
    ]


def test_in_list_preserves_value_types():
    _, params = _builder()._build_condition(
        _cond(DataSearchOperator.in_list, [1, 2], field_path="n")
    )
    assert [json.loads(p) for p in params] == [{"n": 1}, {"n": 2}]


def test_in_list_with_none_is_not_rewritten():
    sql, _ = _builder()._build_condition(
        _cond(DataSearchOperator.in_list, ["c1", None])
    )
    assert "@>" not in sql


def test_in_list_empty_matches_nothing():
    sql, params = _builder()._build_condition(_cond(DataSearchOperator.in_list, []))
    assert sql == "FALSE"
    assert params == []


# --- contains on a list field --------------------------------------------


def test_contains_on_a_list_field_probes_at_the_top_level():
    """``indexed_data->'f' @> '"v"'`` is containment on the EXTRACT — the GIN on
    ``indexed_data`` cannot serve it either. Only a top-level probe is indexed.

    Element membership stays EXACT (#362/#378): ``{"tags": ["team"]}`` must not
    match a stored ``["team-a"]``.
    """
    sql, params = _builder(list_fields=["tags"])._build_condition(
        _cond(DataSearchOperator.contains, "team", field_path="tags")
    )
    assert sql == "indexed_data @> %s::jsonb"
    assert json.loads(params[0]) == {"tags": ["team"]}


def test_contains_on_a_string_field_still_uses_like():
    sql, _ = _builder()._build_condition(_cond(DataSearchOperator.contains, "abc"))
    assert "LIKE" in sql
    assert "@>" not in sql


# --- what must NOT change ------------------------------------------------


@pytest.mark.parametrize(
    "op",
    [
        DataSearchOperator.not_equals,
        DataSearchOperator.not_in_list,
        DataSearchOperator.greater_than,
        DataSearchOperator.less_than,
        DataSearchOperator.starts_with,
        DataSearchOperator.regex,
    ],
)
def test_operators_a_gin_cannot_serve_are_left_alone(op):
    """A GIN is a value->row inverted index: no ordering, no negation, no prefix.

    Rewriting these would be a lie. They stay Seq Scans until #418.
    """
    value = ["c1"] if op == DataSearchOperator.not_in_list else "c1"
    sql, _ = _builder()._build_condition(_cond(op, value))
    assert "indexed_data @> " not in sql
