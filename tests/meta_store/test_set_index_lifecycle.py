"""SetIndex over its whole lifecycle, not just "someone added the annotation".

#417 fixed the ADD case: backfill before enabling the fast path. It backfilled
only rows whose column was NULL, which is not the same question. A row can hold a
STALE value — writes populate the shadow column from ``_set_columns``, so while the
annotation is absent the column is not maintained, and ``ON CONFLICT DO UPDATE``
never touches it. Such a row is non-NULL and wrong, so an ``IS NULL`` backfill
skips it and the fast path answers from stale data.

That failure is worse in kind than the one #417 fixed: a NULL column only ever
loses rows, but a stale column also RETURNS rows that do not match.

The invariant these tests pin: the shadow column is a derivation of
``indexed_data``, so after ``ensure_set_column`` it must agree with it — whatever
happened in between.
"""

import uuid
from datetime import UTC, datetime

from specstar.query import QB
from specstar.types import ResourceMeta


def _meta(rid: str, keys: list) -> ResourceMeta:
    base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    return ResourceMeta(
        current_revision_id=f"rev_{rid}",
        resource_id=f"id-{rid}",
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


def _boot(table: str):
    """A pod starting up WITHOUT the annotation."""
    from specstar.resource_manager.meta_store.postgres import PostgresMetaStore

    store = PostgresMetaStore(
        pg_dsn="postgresql://admin:password@localhost:5432/your_database",
        table_name=table,
    )
    store.register_list_field("keys")
    return store


def _table() -> str:
    return "lifecycle_" + uuid.uuid4().hex[:8]


def test_removing_the_annotation_falls_back_to_correct_results():
    """No shadow column in play → the shared containment path answers."""
    t = _table()
    a = _boot(t)
    a["id-1"] = _meta("1", ["a"])
    a["id-2"] = _meta("2", ["b"])
    a.ensure_set_column("keys", str)
    assert _ids(a, ["a"]) == ["1"]

    b = _boot(t)  # annotation removed → ensure_set_column is never called
    assert _ids(b, ["a"]) == ["1"]


def test_readding_the_annotation_after_rows_changed_does_not_serve_stale_data():
    """remove → write → re-add. The write went unmirrored; the column is stale.

    ``IS NULL`` skips it (it is not NULL, just wrong), so the fast path returns a
    row that no longer matches AND misses the value it now has.
    """
    t = _table()
    a = _boot(t)
    a["id-1"] = _meta("1", ["a"])
    a.ensure_set_column("keys", str)
    assert _ids(a, ["a"]) == ["1"]

    b = _boot(t)  # annotation removed
    b["id-1"] = _meta("1", ["zzz"])  # the row's keys CHANGE while unannotated
    assert _ids(b, ["zzz"]) == ["1"]
    assert _ids(b, ["a"]) == []

    c = _boot(t)  # annotation re-added
    c.ensure_set_column("keys", str)

    assert _ids(c, ["zzz"]) == ["1"], "re-adding the annotation lost a real match"
    assert _ids(c, ["a"]) == [], (
        "re-adding the annotation resurrected a stale match — the shadow column "
        "still holds the pre-removal value"
    )


def test_backfill_repairs_a_column_that_disagrees_with_indexed_data():
    """The public CLI entry point must fix stale values, not just missing ones."""
    t = _table()
    a = _boot(t)
    a["id-1"] = _meta("1", ["a"])
    a.ensure_set_column("keys", str)

    # corrupt the shadow column behind the store's back (what an unannotated
    # deployment effectively does)
    with a.transaction() as cur:
        cur.execute(
            f'UPDATE "{t}" SET set_keys = %s WHERE resource_id = %s',
            [["wrong"], "id-1"],
        )
    assert _ids(a, ["a"]) == []  # proves the column is what answers

    assert a.backfill_set_column("keys") == 1
    assert _ids(a, ["a"]) == ["1"]
    assert _ids(a, ["wrong"]) == []


def test_backfill_is_a_noop_when_the_column_already_agrees():
    """Startup runs this on every boot; a clean table must cost zero writes."""
    t = _table()
    a = _boot(t)
    for i in range(20):
        a[f"id-{i}"] = _meta(str(i), [f"k{i}"])
    a.ensure_set_column("keys", str)

    assert a.backfill_set_column("keys") == 0


def test_rows_added_while_unannotated_are_picked_up_on_re_add():
    """A brand-new row written with no annotation has a NULL column."""
    t = _table()
    a = _boot(t)
    a["id-1"] = _meta("1", ["a"])
    a.ensure_set_column("keys", str)

    b = _boot(t)  # annotation removed
    b["id-2"] = _meta("2", ["a"])  # NEW row, shadow column never populated

    c = _boot(t)  # annotation re-added
    c.ensure_set_column("keys", str)
    assert _ids(c, ["a"]) == ["1", "2"]
