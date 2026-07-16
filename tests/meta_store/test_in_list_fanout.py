"""``in_list`` must not fan out into one GIN probe per value (#416 follow-up).

#416 rewrote ``in_list`` into ``value1 @> … OR value2 @> … OR …`` so the GIN on
``indexed_data`` could serve it. That is a large win for the short lists it was
benchmarked on, and a severe regression for long ones: the OR'd form's cost grows
SUPERLINEARLY (Postgres must plan and BitmapOr one branch per value), while the
pre-#416 form was a flat Seq Scan. Measured on a 60k-row table, filtering an
``IN`` over N ids:

    N        OR'd @>  (plan+exec)      flat scan
    1            0.15 ms                ~7 ms
    100          5.95 ms                ~8 ms      <- still ahead
    200         14.33 ms                ~8 ms      <- crossover passed
    1000       168.25 ms                ~8 ms
    2000       977.00 ms               ~15 ms      <- 64x SLOWER

Real callers hit the bad end: a document list pages 2000 rows and then counts
each row's chunks with one ``file_id IN (<2000 ids>)``, twice per request.

The long-list path must stay TYPE-STRICT. Falling back to the pre-#416
``indexed_data->>'f' IN (…)`` would be fast but type-blind (it compares
``str(value)``), so the SAME query would answer differently depending on how many
values it was given — a silent correctness bug strictly worse than the slowness.
``indexed_data->'f' = ANY(ARRAY[…]::jsonb[])`` is jsonb equality, so it agrees
with the short-list probes and with the reference matcher, and it is flat
(measured ~15-24 ms at N=200/1000/2000).
"""

import uuid
from datetime import UTC, datetime

import pytest

from specstar.query import QB
from specstar.query_types import DataSearchCondition, DataSearchOperator
from specstar.resource_manager.meta_store.postgres import IN_LIST_PROBE_LIMIT
from specstar.types import ResourceMeta

from .common import get_meta_store


def _meta(rid: str, **indexed) -> ResourceMeta:
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
        indexed_data={"id": rid, **indexed},
    )


def _cond(values: list) -> DataSearchCondition:
    return DataSearchCondition(
        field_path="fid", operator=DataSearchOperator.in_list, value=values
    )


def test_short_in_list_still_probes_the_gin():
    # The #416 win must survive: a short list stays one probe per value, which
    # Postgres BitmapOr's across the single GIN.
    store = get_meta_store("postgres")
    sql, params = store._build_condition(_cond(["a", "b", "c"]))
    assert sql.count("@>") == 3
    assert len(params) == 3


def test_long_in_list_does_not_emit_one_probe_per_value():
    # The regression guard. At this length the OR'd form is both slower to plan
    # and slower to run than a single flat predicate.
    store = get_meta_store("postgres")
    n = IN_LIST_PROBE_LIMIT + 1
    sql, params = store._build_condition(_cond([f"v{i}" for i in range(n)]))
    assert sql.count("@>") == 0, f"fanned out into {sql.count('@>')} probes"
    assert "= ANY(" in sql
    # One array parameter, not one parameter per value.
    assert len(params) == 1


def test_long_in_list_stays_type_strict_like_the_short_one():
    # The whole point of #416 was that ``->>`` is type-blind while the reference
    # matcher is a Python ``==``. The long-list path must not quietly undo that,
    # or the answer would depend on the list's LENGTH.
    store = get_meta_store("postgres")
    long_sql, _ = store._build_condition(
        _cond([f"v{i}" for i in range(IN_LIST_PROBE_LIMIT + 1)])
    )
    assert "->>" not in long_sql


@pytest.mark.parametrize("n", [3, IN_LIST_PROBE_LIMIT + 1])
def test_both_paths_return_the_same_rows_as_the_reference(n: int):
    # Length must change only the plan, never the answer.
    store = get_meta_store("postgres")
    for i in range(10):
        m = _meta(str(i), fid=f"v{i}")
        store[m.resource_id] = m
    # Ask for v0..v2 plus enough padding to cross the threshold.
    wanted = ["v0", "v1", "v2"] + [f"pad{i}" for i in range(max(0, n - 3))]
    q = QB["fid"].in_(wanted).build()
    assert sorted(m.indexed_data["id"] for m in store.iter_search(q)) == ["0", "1", "2"]


def test_long_in_list_of_ints_matches_ints_not_their_strings():
    store = get_meta_store("postgres")
    for i in range(5):
        m = _meta(str(i), num=i)
        store[m.resource_id] = m
    padding = [10_000 + i for i in range(IN_LIST_PROBE_LIMIT + 1)]
    q = QB["num"].in_([1, 2, *padding]).build()
    assert sorted(m.indexed_data["id"] for m in store.iter_search(q)) == ["1", "2"]
    # A string "1" must NOT match the stored number 1 — same rule the short path
    # follows, and the same rule the reference matcher (`==`) follows.
    q = QB["num"].in_(["1", *[str(p) for p in padding]]).build()
    assert list(store.iter_search(q)) == []
