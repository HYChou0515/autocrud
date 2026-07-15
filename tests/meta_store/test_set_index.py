"""SetIndex: a dedicated array column + GIN for fast ``contains_any`` overlap.

Postgres-only (the shadow column / GIN are pgvector-style native acceleration;
memory & SQLite already serve ``contains_any`` from the shared path). Declaring
SetIndex must NOT change results — only how fast they come back — so these tests
pin that the shadow-column path returns the SAME answers as the reference, plus
that the fast ``&&`` path is actually taken.
"""

import uuid
from datetime import UTC, datetime

from specstar.query import QB
from specstar.types import ResourceMeta

from .common import get_meta_store


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


def _ids(store, values) -> list[str]:
    q = QB["keys"].contains_any(values).build()
    return sorted(m.indexed_data["id"] for m in store.iter_search(q))


def _seed(store, data: dict):
    for rid, keys in data.items():
        m = _meta(rid, keys)
        store[m.resource_id] = m


def test_contains_any_via_set_index_column_returns_correct_results():
    store = get_meta_store("postgres")
    store.ensure_set_column("keys", str)
    _seed(store, {"1": ["a", "b"], "2": ["b", "c"], "3": ["x"]})
    assert _ids(store, ["a", "z"]) == ["1"]


def test_set_index_field_uses_array_overlap_not_containment_fanout():
    # The optimization proof: a SetIndex field routes contains_any to a single
    # ``&&`` on the shadow column; a plain field falls back to ``@>`` fan-out.
    from specstar.query_types import DataSearchCondition, DataSearchOperator

    store = get_meta_store("postgres")
    store.ensure_set_column("keys", str)
    fast, _ = store._build_condition(
        DataSearchCondition(
            field_path="keys",
            operator=DataSearchOperator.contains_any,
            value=["a", "b"],
        )
    )
    assert "&&" in fast and "set_keys" in fast
    slow, _ = store._build_condition(
        DataSearchCondition(
            field_path="other", operator=DataSearchOperator.contains_any, value=["a"]
        )
    )
    assert "@>" in slow and "&&" not in slow


def test_set_index_results_match_the_reference_including_cjk_and_empty():
    # Declaring SetIndex must NOT change answers — only speed.
    store = get_meta_store("postgres")
    store.ensure_set_column("keys", str)
    _seed(
        store,
        {"1": ["a", "b"], "2": ["b", "c"], "3": ["x"], "4": [], "5": ["中文", "良い"]},
    )
    assert _ids(store, ["b", "x"]) == ["1", "2", "3"]
    assert _ids(store, ["zzz"]) == []
    assert _ids(store, []) == []
    assert "4" not in _ids(store, ["a", "b", "c", "x"])
    assert _ids(store, ["中文"]) == ["5"]
    assert _ids(store, ["良い", "a"]) == ["1", "5"]


def test_update_keeps_the_set_index_column_in_sync():
    store = get_meta_store("postgres")
    store.ensure_set_column("keys", str)
    m = _meta("1", ["a"])
    store[m.resource_id] = m
    assert _ids(store, ["a"]) == ["1"]
    # Overwrite the same resource with different keys.
    m2 = ResourceMeta(
        current_revision_id="rev_1b",
        resource_id=m.resource_id,
        total_revision_count=2,
        created_time=m.created_time,
        updated_time=m.updated_time,
        created_by="t",
        updated_by="t",
        is_deleted=False,
        indexed_data={"id": "1", "keys": ["z"]},
    )
    store[m.resource_id] = m2
    assert _ids(store, ["a"]) == []  # old key gone from the shadow column
    assert _ids(store, ["z"]) == ["1"]  # new key present


def test_add_model_with_set_index_annotation_wires_shadow_column_end_to_end():
    # The public path: declare SetIndex on the model, crud auto-creates the
    # shadow column (like it does pgvector columns) and contains_any just works.
    import uuid
    from typing import Annotated

    import msgspec

    from specstar import SpecStar
    from specstar.resource_manager.storage_factory import PostgresStorageFactory
    from specstar.types import SetIndex

    class Foo(msgspec.Struct):
        keys: Annotated[list[str], SetIndex()]

    sp = SpecStar()
    sp.configure(
        storage_factory=PostgresStorageFactory(
            connection_string="postgresql://admin:password@localhost:5432/your_database",
            table_prefix=f"t{uuid.uuid4().hex[:8]}_",
        ),
        default_user="t",
    )
    sp.add_model(Foo, name="foo")
    rm = sp.get_resource_manager(Foo)
    rm.create(Foo(keys=["a", "b"]))
    rm.create(Foo(keys=["x"]))

    # crud auto-wired the dedicated shadow column (fast path).
    assert "keys" in rm.storage.meta_store._set_columns
    # and the query works end-to-end through the declared field.
    rows = rm.list_resources(QB["keys"].contains_any(["a", "z"]).build())
    assert [r.data.keys for r in rows] == [["a", "b"]]


def test_backfill_populates_set_column_for_rows_written_before_it_existed():
    # There is no schema-change gap: ensure_set_column populates the column for
    # rows written before it existed, BEFORE enabling the && fast path (#417).
    #
    # This deliberately does NOT mirror Vector fields. backfill_vectors cannot
    # run implicitly because it must re-embed — expensive, external, and not
    # something a meta store can do at startup. The SetIndex column is "a pure
    # derivation of indexed_data (no re-encoding needed), so it runs entirely in
    # SQL" (backfill_set_column.__doc__) — nothing to defer to an operator, and
    # deferring it silently hid every pre-existing row.
    store = get_meta_store("postgres")
    _seed(store, {"1": ["a", "b"], "2": ["c"]})  # written BEFORE the column
    store.ensure_set_column("keys", str)
    assert _ids(store, ["a"]) == ["1"]  # visible immediately, no manual step
    assert _ids(store, ["c"]) == ["2"]
    # backfill_set_column stays, as the way to force a full re-derivation.
    assert store.backfill_set_column("keys") == 2
    assert _ids(store, ["a"]) == ["1"]


def _pg_spec_with_foo(extra_field: bool = False):
    import uuid
    from typing import Annotated

    import msgspec

    from specstar import SpecStar
    from specstar.resource_manager.storage_factory import PostgresStorageFactory
    from specstar.types import SetIndex

    class Foo(msgspec.Struct):
        keys: Annotated[list[str], SetIndex()]
        tags: Annotated[list[str], SetIndex()] = msgspec.field(default_factory=list)

    sp = SpecStar()
    sp.configure(
        storage_factory=PostgresStorageFactory(
            connection_string="postgresql://admin:password@localhost:5432/your_database",
            table_prefix=f"t{uuid.uuid4().hex[:8]}_",
        ),
        default_user="t",
    )
    sp.add_model(Foo, name="foo")
    return sp, sp.get_resource_manager(Foo), Foo


def test_backfill_set_columns_script_runs_via_resource_manager():
    from specstar.resource_manager.backfill import backfill_set_columns

    _, rm, Foo = _pg_spec_with_foo()
    rm.create(Foo(keys=["a", "b"]))
    rm.create(Foo(keys=["c"]))

    summary = backfill_set_columns(rm, field_name="keys")
    assert summary.encoded == 2
    # still queryable after backfill
    assert len(rm.list_resources(QB["keys"].contains_any(["a"]).build())) == 1


def test_multiple_set_index_fields_each_get_their_own_column():
    # Aligns with Vector: a resource can declare many SetIndex fields, each
    # backed by its own shadow column + GIN.
    _, rm, Foo = _pg_spec_with_foo()
    ms = rm.storage.meta_store
    assert "keys" in ms._set_columns and "tags" in ms._set_columns
    rm.create(Foo(keys=["a"], tags=["x"]))
    rm.create(Foo(keys=["b"], tags=["x", "y"]))
    assert len(rm.list_resources(QB["keys"].contains_any(["a"]).build())) == 1
    assert len(rm.list_resources(QB["tags"].contains_any(["y"]).build())) == 1
    assert len(rm.list_resources(QB["tags"].contains_any(["x"]).build())) == 2


def test_set_index_supports_int_element_type():
    store = get_meta_store("postgres")
    store.ensure_set_column("nums", int)
    for rid, nums in {"1": [1, 2], "2": [2, 3], "3": [9]}.items():
        m = _meta(rid, [])
        m.indexed_data["nums"] = nums  # type: ignore[index]
        store[m.resource_id] = m
    q = QB["nums"].contains_any([2, 7]).build()
    assert sorted(r.indexed_data["id"] for r in store.iter_search(q)) == ["1", "2"]
