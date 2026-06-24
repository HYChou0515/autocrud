"""``add_model`` must auto-register list-typed indexed fields from the model's
own annotations — issue #378.

The in-process backends define ``contains`` on a list field as element
membership; the SQL backends only honour that for fields the meta store was
told are list-typed via ``register_list_field`` (wired from ``add_model``).
That wiring keyed solely on an *explicit* ``IndexableField.field_type`` whose
``get_origin`` was exactly ``list``/``tuple``/``set`` — so the idiomatic
bare-string declaration ``indexed_fields=["norm_keys"]`` (``field_type`` UNSET)
was never registered, and a list field silently degraded to substring ``LIKE``
on every SQL backend (e.g. ``contains("m4")`` matching ``["m40"]``). Optional
list annotations (``list[str] | None``) slipped through the same gap.

These tests drive the public API end-to-end on an in-process SQLite backend
(which, unlike the Memory backend, actually distinguishes substring from
membership), so they survive any refactor of *how* ``add_model`` informs the
store — they only assert *what* a search returns.
"""

from __future__ import annotations

import datetime as dt

from msgspec import Struct, field

from specstar import SpecStar
from specstar.query_types import (
    DataSearchCondition,
    DataSearchOperator,
    ResourceMetaSearchQuery,
)
from specstar.resource_manager.core import SimpleStorage
from specstar.resource_manager.meta_store.sqlite3 import MemorySqliteMetaStore
from specstar.resource_manager.resource_store.simple import MemoryResourceStore
from specstar.resource_manager.storage_factory import IStorageFactory

_NOW = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


class _SqliteMemFactory(IStorageFactory):
    """In-process SQL backend: SQLite meta store + memory resource store.

    The Memory meta store always does element membership, so it cannot surface
    the substring bug; the SQLite meta store can (it is the same lowering path
    as Postgres for ``contains``).
    """

    def build(self, model_name: str) -> SimpleStorage:
        return SimpleStorage(MemorySqliteMetaStore(), MemoryResourceStore())


class Card(Struct):
    title: str
    norm_keys: list[str] = field(default_factory=list)


class OptCard(Struct):
    title: str
    norm_keys: list[str] | None = None


def _managed(model_cls, indexed_fields, rows):
    sp = SpecStar(storage_factory=_SqliteMemFactory())
    sp.add_model(model_cls, name="card", indexed_fields=indexed_fields)
    mgr = sp.resource_managers["card"]
    with mgr.using(user="t", now=_NOW) as op:
        for row in rows:
            op.create(row)
    return mgr


def _contains(mgr, field_path, value):
    with mgr.using(user="t", now=_NOW):
        q = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path=field_path,
                    operator=DataSearchOperator.contains,
                    value=value,
                )
            ]
        )
        return sorted(m.indexed_data["title"] for m in mgr.search_resources(q))


def test_contains_on_bare_string_list_index_is_element_membership():
    """The idiomatic ``indexed_fields=["norm_keys"]`` must give membership.

    ``"m4"`` is a substring of ``"m40"`` but not an element of ``["m40"]``;
    only the card whose list actually contains ``"m4"`` may match.
    """
    mgr = _managed(
        Card,
        ["title", "norm_keys"],
        [
            Card(title="forty", norm_keys=["m40"]),
            Card(title="four", norm_keys=["m4", "capping"]),
        ],
    )
    assert _contains(mgr, "norm_keys", "m4") == ["four"]


def test_contains_on_bare_string_scalar_index_keeps_substring():
    """The fix must not over-register: a scalar field stays substring ``contains``.

    ``"our"`` is a substring of ``"four"`` but not of ``"forty"`` — scalar
    string ``contains`` is intentionally substring, and must be left alone.
    """
    mgr = _managed(
        Card,
        ["title", "norm_keys"],
        [
            Card(title="four"),
            Card(title="forty"),
        ],
    )
    assert _contains(mgr, "title", "our") == ["four"]


def test_contains_on_optional_list_index_is_element_membership():
    """``norm_keys: list[str] | None`` (Optional) must also get membership.

    The ``Union`` wrapper previously hid the ``list`` origin, so even an
    explicitly-typed Optional list degraded to substring. Unwrapping the
    Optional restores membership.
    """
    mgr = _managed(
        OptCard,
        ["title", "norm_keys"],
        [
            OptCard(title="forty", norm_keys=["m40"]),
            OptCard(title="four", norm_keys=["m4", "capping"]),
        ],
    )
    assert _contains(mgr, "norm_keys", "m4") == ["four"]


def test_add_model_registers_bare_string_list_field_not_scalar(monkeypatch):
    """Pinpoint the mechanism: ``add_model`` calls ``register_list_field`` for a
    bare-string list field (type resolved from the model) and not for a scalar.

    Mirrors ``test_add_model_auto_registers_list_typed_indexed_fields`` but for
    the idiomatic ``indexed_fields=["norm_keys"]`` form (no explicit type).
    """
    from specstar.resource_manager.meta_store.simple import MemoryMetaStore

    registered: list[str] = []
    monkeypatch.setattr(
        MemoryMetaStore,
        "register_list_field",
        lambda self, fp: registered.append(fp),
        raising=False,
    )

    sp = SpecStar()
    sp.configure(default_user="t")
    sp.add_model(Card, name="card", indexed_fields=["title", "norm_keys"])

    assert "norm_keys" in registered, (
        f"bare-string list field not registered; got {registered!r}"
    )
    assert "title" not in registered, (
        f"scalar field wrongly registered as list; got {registered!r}"
    )
