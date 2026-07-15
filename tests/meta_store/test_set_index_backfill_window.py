"""#417: declaring SetIndex on a table that already has rows must not hide them.

``tests/meta_store/test_set_index.py`` states the invariant — "Declaring SetIndex
must NOT change results — only how fast they come back" — but every test there
creates the column BEFORE seeding, so the write path fills it. Real deployments do
the opposite: the data already exists, then you add the annotation and ship.

These tests pin that order. Without the fix, ``ensure_set_column`` adds the column
(existing rows -> NULL) and enables the ``&&`` fast path in the same breath, so
every pre-existing row silently stops matching until an operator remembers to run
``specstar backfill set-columns``.
"""

import uuid
from datetime import UTC, datetime

import pytest

from specstar.query import QB
from specstar.types import ResourceMeta

from .common import get_meta_store

SEED = {"1": ["a", "b"], "2": ["b", "c"], "3": ["x"]}


def _meta(rid: str, keys: list) -> ResourceMeta:
    base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    return ResourceMeta(
        current_revision_id=f"rev_{rid}",
        resource_id=str(uuid.uuid4()),
        total_revision_count=1,
        created_time=base,
        updated_time=base,
        created_by="t",
        updated_by="t",
        is_deleted=False,
        indexed_data={"id": rid, "keys": keys},
    )


def _seed(store, data: dict = SEED):
    for rid, keys in data.items():
        m = _meta(rid, keys)
        store[m.resource_id] = m


def _ids(store, values) -> list[str]:
    q = QB["keys"].contains_any(values).build()
    return sorted(m.indexed_data["id"] for m in store.iter_search(q))


def test_annotating_a_table_that_already_has_rows_keeps_them_visible():
    """The #417 repro: data first, annotation second — the real deployment order."""
    store = get_meta_store("postgres")
    _seed(store)
    before = _ids(store, ["a", "z"])
    assert before == ["1"]  # sanity: the fallback path is correct

    # A developer adds Annotated[list[str], SetIndex()] and deploys. add_model()
    # calls ensure_set_column() at startup — that is ALL it does.
    store.ensure_set_column("keys", str)

    assert _ids(store, ["a", "z"]) == before, (
        "pre-existing rows vanished: the && fast path went live against a column "
        "that is still NULL for every row written before the annotation"
    )


def test_pre_existing_and_new_rows_are_both_visible_after_annotating():
    """The dangerous shape of the bug: the query keeps *working* on new rows.

    It does not raise or return nothing — it silently returns a SUBSET, so
    nothing looks wrong.
    """
    store = get_meta_store("postgres")
    _seed(store)
    store.ensure_set_column("keys", str)

    m = _meta("4", ["a", "q"])
    store[m.resource_id] = m

    assert _ids(store, ["a", "z"]) == ["1", "4"]


def test_the_fast_path_is_still_taken_after_the_fix():
    """The fix must not silently disable the optimisation to buy correctness."""
    from specstar.query_types import DataSearchCondition, DataSearchOperator

    store = get_meta_store("postgres")
    _seed(store)
    store.ensure_set_column("keys", str)

    sql, _ = store._build_condition(
        DataSearchCondition(
            field_path="keys",
            operator=DataSearchOperator.contains_any,
            value=["a", "b"],
        )
    )
    assert "&&" in sql and "set_keys" in sql


def test_ensure_set_column_is_idempotent_across_restarts():
    """``ensure_set_column`` runs on every add_model, i.e. every process start."""
    store = get_meta_store("postgres")
    _seed(store)
    store.ensure_set_column("keys", str)
    store.ensure_set_column("keys", str)  # "restart"
    store.ensure_set_column("keys", str)  # and again
    assert _ids(store, ["a", "z"]) == ["1"]


def test_rows_whose_field_is_absent_or_not_an_array_do_not_match():
    """A row with no ``keys`` at all must stay out of contains_any results."""
    store = get_meta_store("postgres")
    _seed(store)
    m = _meta("5", [])
    m.indexed_data = {"id": "5"}  # field absent entirely
    store[m.resource_id] = m
    store.ensure_set_column("keys", str)

    assert _ids(store, ["a", "z"]) == ["1"]


@pytest.mark.parametrize(
    ("elem_type", "seed", "probe", "expected"),
    [
        pytest.param(str, {"1": ["a"], "2": ["b"]}, ["a"], ["1"], id="list[str]"),
        pytest.param(int, {"1": [1, 2], "2": [3]}, [3], ["2"], id="list[int]"),
        pytest.param(float, {"1": [1.5], "2": [2.5]}, [2.5], ["2"], id="list[float]"),
    ],
)
def test_backfill_covers_every_supported_element_type(elem_type, seed, probe, expected):
    """SetIndex infers text / bigint / double precision from the annotation."""
    store = get_meta_store("postgres")
    _seed(store, seed)
    store.ensure_set_column("keys", elem_type)
    assert _ids(store, probe) == expected
