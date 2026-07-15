"""``contains`` on list-typed indexed fields must be element membership.

Issue #362. The in-process backends already do the right thing
(``basic.py:369-376`` — ``compare_value in field_value`` for list-typed
``field_value``). The SQL backends did not — they emitted ``LIKE '%v%'``
against the column's JSON text serialisation, which admits substring
false-positives whenever list elements share substrings (e.g. ``"c1"``
matches a row whose list is ``["c10", "c20"]`` because the literal substring
``c1`` appears).

The fix routes list-typed indexed fields through element containment
(Postgres JSONB ``@>``; SQLite ``json_each`` membership) and leaves string /
numeric fields on ``LIKE`` so that:

* ``QB["str_field"].contains("substr")`` keeps its substring semantics;
* ``QB["list_field"].contains(element)`` becomes a true element-of test.

The Postgres tests pin the emitted SQL via a ``__new__`` bypass (no live
server needed); SQLite is in-process so its tests exercise real
``iter_search``. Both run in the fast (no-services) gate.
"""

from __future__ import annotations

from specstar.query_types import DataSearchCondition, DataSearchOperator
from specstar.resource_manager.meta_store.postgres import PostgresMetaStore


def _make_store() -> PostgresMetaStore:
    """Build a PostgresMetaStore without touching the network.

    ``__init__`` opens a connection pool and probes pgvector — both
    require a live server. Bypassing via ``__new__`` lets us exercise the
    pure SQL builder (``_build_condition``) in the fast gate. The
    attributes set below are the only ones the builder reads.
    """
    s = PostgresMetaStore.__new__(PostgresMetaStore)
    s.table_name = "resource_meta"
    s._vec_columns = {}
    s._list_fields = set()
    s._set_columns = {}
    s._sort_indexes = set()  # #418
    return s


def test_contains_on_list_field_emits_jsonb_containment():
    """A field registered as list-typed must use JSONB ``@>``, not LIKE.

    Without the fix the row ``source_chunk_ids = ["c10", "c20"]`` would
    match ``contains("c1")`` because ``LIKE '%c1%'`` matches the literal
    substring inside ``"c10"``. The ``@>`` form rejects that row because
    ``"c1"`` is not an element of the array.

    #416 moved the probe from the extract (``indexed_data->'f' @> '"c1"'``) to
    the top level (``indexed_data @> '{"f": ["c1"]}'``): both are exact element
    membership, but only the top-level form can be served by the GIN on
    ``indexed_data``. The membership semantics this test guards are unchanged.
    """
    import json

    store = _make_store()
    store.register_list_field("source_chunk_ids")

    cond = DataSearchCondition(
        field_path="source_chunk_ids",
        operator=DataSearchOperator.contains,
        value="c1",
    )
    sql, params = store._build_condition(cond)
    assert "@>" in sql, f"expected JSONB containment for list field, got: {sql!r}"
    assert "LIKE" not in sql, f"list-field contains must not fall back to LIKE: {sql!r}"
    assert "indexed_data @> " in sql, f"probe must be top-level for the GIN: {sql!r}"
    # The element is wrapped in its field + a one-element array, so containment
    # scopes to THIS field and stays element-exact.
    assert json.loads(params[0]) == {"source_chunk_ids": ["c1"]}, (
        f"expected a scoped JSON-encoded element, got: {params!r}"
    )


def test_contains_on_unregistered_field_falls_back_to_like():
    """A field that was *not* registered as list-typed keeps ``LIKE`` semantics.

    ``QB["description"].contains("urgent")`` is the canonical
    string-substring use; the fix must not regress it.
    """
    store = _make_store()
    # No register_list_field call — same as today's behaviour.

    cond = DataSearchCondition(
        field_path="description",
        operator=DataSearchOperator.contains,
        value="urgent",
    )
    sql, params = store._build_condition(cond)
    assert "LIKE" in sql, f"string field must use LIKE, got: {sql!r}"
    assert "@>" not in sql, f"string field must not use JSONB containment: {sql!r}"
    assert params == ["%urgent%"]


def test_register_list_field_is_idempotent():
    """Re-registering the same field is a no-op (callers may register on every add_model).

    Mirrors the ``add_indexed_field`` contract on the resource manager
    (``core.py:1393-1401``).
    """
    store = _make_store()
    store.register_list_field("tags")
    store.register_list_field("tags")  # second call should not raise
    cond = DataSearchCondition(
        field_path="tags",
        operator=DataSearchOperator.contains,
        value="x",
    )
    sql, _ = store._build_condition(cond)
    assert "@>" in sql


# ---------------------------------------------------------------------------
# Auto-wiring from ``add_model``
# ---------------------------------------------------------------------------


def test_add_model_auto_registers_list_typed_indexed_fields(monkeypatch):
    """``add_model`` calls ``register_list_field`` on the meta store for list-typed fields.

    Mirrors the existing ``ensure_vector_column`` auto-wiring (``crud/core.py:1583``):
    a user declaring ``IndexableField(field_path="tags", field_type=list[str])``
    should get correct Postgres ``contains`` semantics without manually
    calling ``register_list_field``. Verified by monkey-patching the
    in-memory meta store to expose ``register_list_field`` and asserting
    that ``add_model`` invokes it with the right field path.
    """
    from msgspec import Struct

    from specstar import SpecStar
    from specstar.resource_manager.meta_store.simple import MemoryMetaStore
    from specstar.types import IndexableField

    class Doc(Struct):
        title: str
        note: str = ""
        tags: list[str] = []

    registered: list[str] = []
    monkeypatch.setattr(
        MemoryMetaStore,
        "register_list_field",
        lambda self, fp: registered.append(fp),
        raising=False,
    )

    sp = SpecStar()
    sp.configure(default_user="t")
    sp.add_model(
        Doc,
        indexed_fields=[
            IndexableField(field_path="title", field_type=str),  # str → not registered
            IndexableField(field_path="note"),  # field_type UNSET → skipped
            IndexableField(
                field_path="tags", field_type=list[str]
            ),  # list → registered
        ],
    )

    assert "tags" in registered, (
        f"register_list_field not invoked for list-typed field; got {registered!r}"
    )
    # A string field and an untyped (UNSET) field must both be left alone.
    assert "title" not in registered and "note" not in registered, (
        f"register_list_field called on a non-list field; got {registered!r}"
    )


# ---------------------------------------------------------------------------
# SQLite has the same bug as Postgres — and being in-process, we can pin it
# end-to-end (real ``iter_search``) rather than just the emitted SQL.
# ---------------------------------------------------------------------------


def _sqlite_store_with_row(*, tags: list[str], desc: str = ""):
    import uuid
    from datetime import UTC, datetime

    from specstar.resource_manager.meta_store.sqlite3 import MemorySqliteMetaStore
    from specstar.types import ResourceMeta

    store = MemorySqliteMetaStore()
    base = datetime(2024, 1, 1, tzinfo=UTC)
    meta = ResourceMeta(
        current_revision_id="r1",
        resource_id=str(uuid.uuid4()),
        total_revision_count=1,
        created_time=base,
        updated_time=base,
        created_by="t",
        updated_by="t",
        is_deleted=False,
        indexed_data={"id": "1", "tags": tags, "desc": desc},
    )
    store[meta.resource_id] = meta
    return store


def _sqlite_contains_ids(store, field: str, value: str) -> list[str]:
    from specstar.query_types import ResourceMetaSearchQuery

    q = ResourceMetaSearchQuery(
        conditions=[
            DataSearchCondition(
                field_path=field, operator=DataSearchOperator.contains, value=value
            )
        ],
        limit=100,
    )
    return sorted(r.indexed_data["id"] for r in store.iter_search(q))


def test_sqlite_contains_on_list_field_is_exact_membership_not_substring():
    """SQLite mirror of the #362 fix: ``contains`` on a registered list field is
    exact element membership, not a substring of the JSON serialisation."""
    store = _sqlite_store_with_row(tags=["c10", "c20"])
    store.register_list_field("tags")
    assert _sqlite_contains_ids(store, "tags", "c1") == []  # not a member
    assert _sqlite_contains_ids(store, "tags", "c10") == ["1"]  # real member


def test_sqlite_contains_on_string_field_keeps_substring_semantics():
    """A plain string field keeps ``LIKE`` substring behaviour (the legit use)."""
    store = _sqlite_store_with_row(tags=["x"], desc="this is urgent")
    assert _sqlite_contains_ids(store, "desc", "urgent") == ["1"]


def test_add_model_is_a_noop_on_backends_without_register_list_field():
    """The auto-wiring is guarded by ``hasattr(meta_store, "register_list_field")``.

    On the default in-memory backend (no such method) ``add_model`` must skip
    the wiring silently — list-field ``contains`` just stays on the shared path.
    """
    from msgspec import Struct

    from specstar import SpecStar
    from specstar.types import IndexableField

    class Doc(Struct):
        tags: list[str] = []

    sp = SpecStar()
    sp.configure(default_user="t")
    # No monkeypatch: MemoryMetaStore has no register_list_field, so the guard
    # is False and the loop is skipped — this must not raise.
    sp.add_model(
        Doc,
        indexed_fields=[IndexableField(field_path="tags", field_type=list[str])],
    )
    assert sp.get_resource_manager(Doc) is not None
