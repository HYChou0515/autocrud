"""#416: rewriting ``->>`` to ``@>`` must not change a single result.

The contract is parity with the reference matcher (``basic.py``, plain Python
``==``), which the memory store uses directly. Postgres is the only backend whose
SQL was rewritten, so every case here runs against BOTH and asserts they agree.

``tests/test_gin_containment.py`` pins the generated SQL in CI's service-free lane;
this file needs a live Postgres and is auto-marked ``integration``.
"""

import uuid
from datetime import UTC, datetime

import pytest

from specstar.query import QB
from specstar.types import ResourceMeta

from .common import get_meta_store

# (id, indexed_data) — deliberately mixes JSON types on `n` and `flag` so a
# type-blind rewrite would show up as a parity break.
ROWS = [
    (
        "a",
        {"coll": "c1", "n": 5000, "flag": True, "tags": ["team-a", "x"], "opt": None},
    ),
    ("b", {"coll": "c2", "n": 1, "flag": False, "tags": ["team-b"], "opt": "set"}),
    ("c", {"coll": "c10", "n": 0, "flag": True, "tags": ["team"], "opt": None}),
    ("d", {"coll": "c1", "n": 5000, "flag": False, "tags": [], "opt": "set"}),
]

QUERIES = {
    "equals str": QB["coll"] == "c1",
    "equals str no match": QB["coll"] == "nope",
    "equals int": QB["n"] == 5000,
    "equals int zero": QB["n"] == 0,
    "equals bool true": QB["flag"] == True,  # noqa: E712
    "equals bool false": QB["flag"] == False,  # noqa: E712
    "equals none": QB["opt"] == None,  # noqa: E711
    "in_list str": QB["coll"].in_(["c1", "c2"]),
    "in_list one": QB["coll"].in_(["c10"]),
    "in_list int": QB["n"].in_([0, 1]),
    "in_list no match": QB["coll"].in_(["zz"]),
    "contains exact element": QB["tags"].contains("team"),
    "contains other element": QB["tags"].contains("team-a"),
    "not_equals": QB["coll"] != "c1",
    "greater_than": QB["n"] > 1,
}


def _meta(rid: str, indexed: dict) -> ResourceMeta:
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


def _seed(store):
    for rid, indexed in ROWS:
        m = _meta(rid, indexed)
        store[m.resource_id] = m
    return store


def _ids(store, cond) -> list[str]:
    return sorted(m.indexed_data["id"] for m in store.iter_search(cond.build()))


@pytest.fixture(scope="module")
def reference():
    # No ``register_list_field``: that is Postgres-only plumbing to tell the SQL
    # builder a field is list-typed. The reference matcher sees real Python lists.
    return _seed(get_meta_store("memory"))


@pytest.fixture(scope="module")
def postgres():
    store = _seed(get_meta_store("postgres"))
    store.register_list_field("tags")
    return store


@pytest.mark.parametrize("label", list(QUERIES))
def test_postgres_matches_the_reference_matcher(label, reference, postgres):
    cond = QUERIES[label]
    assert _ids(postgres, cond) == _ids(reference, cond), label


def test_contains_does_not_match_a_prefix_of_another_element(postgres):
    """#362/#378: ``"team"`` must not match a row whose tag is ``"team-a"``."""
    assert _ids(postgres, QB["tags"].contains("team")) == ["c"]


def test_equality_is_type_strict_like_the_reference(postgres, reference):
    """``->>' n' = str(5000)`` used to match the STRING "5000" too.

    The reference compares with Python ``==``, where ``5000 != "5000"``, so the
    old Postgres path was the odd one out. Containment lines them up.
    """
    assert _ids(postgres, QB["n"] == "5000") == _ids(reference, QB["n"] == "5000") == []


def test_empty_in_list_matches_nothing_instead_of_raising(postgres, reference):
    """``IN ()`` is a syntax error; the old path emitted it verbatim."""
    assert (
        _ids(postgres, QB["coll"].in_([])) == _ids(reference, QB["coll"].in_([])) == []
    )
