"""Postgres ``contains`` SQL pushdown must respect list-typed indexed fields.

Issue #362. The in-process backends already do the right thing
(``basic.py:369-376`` — ``compare_value in field_value`` for list-typed
``field_value``). The Postgres backend's ``_build_condition`` does not —
it always emits ``LIKE '%v%'`` against the JSONB column's text
serialisation, which admits substring false-positives whenever list
elements share substrings (e.g. ``"c1"`` matches a row whose list is
``["c10", "c20"]`` because the literal substring ``c1`` appears).

The fix routes list-typed indexed fields through JSONB ``@>`` and leaves
string / numeric fields on ``LIKE`` so that:

* ``QB["str_field"].contains("substr")`` keeps its substring semantics;
* ``QB["list_field"].contains(element)`` becomes a true element-of test.

These tests pin the SQL emitted by ``_build_condition`` directly so they
don't require a live Postgres — they run inside the fast (no-services)
gate.
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
    return s


def test_contains_on_list_field_emits_jsonb_containment():
    """A field registered as list-typed must use JSONB ``@>``, not LIKE.

    Without the fix the row ``source_chunk_ids = ["c10", "c20"]`` would
    match ``contains("c1")`` because ``LIKE '%c1%'`` matches the literal
    substring inside ``"c10"``. The ``@>`` form rejects that row because
    ``"c1"`` is not an element of the array.
    """
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
    # The parameter is JSON-encoded so PG can compare arrays of strings.
    assert params == ['"c1"'], f"expected JSON-encoded element, got: {params!r}"


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
            IndexableField(field_path="tags", field_type=list[str]),  # list → registered
        ],
    )

    assert "tags" in registered, (
        f"register_list_field not invoked for list-typed field; got {registered!r}"
    )
    # A string field and an untyped (UNSET) field must both be left alone.
    assert "title" not in registered and "note" not in registered, (
        f"register_list_field called on a non-list field; got {registered!r}"
    )


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
