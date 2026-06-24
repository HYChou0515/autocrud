"""``contains`` on list-typed indexed fields, via the SQLAlchemy meta store.

Issue #378. The in-process backends (``basic.py``) define ``contains`` on a
list field as element membership (``value in field_value``). The raw psycopg
(``postgres.py``) and sqlite3 (``sqlite3.py``) stores were aligned to that in
#367 / #374, but the SQLAlchemy store still emitted substring ``LIKE`` against
the serialised JSON array — so the same query returned different rows on a
SQLAlchemy-backed Postgres/MySQL/SQLite/Oracle deployment (e.g. ``contains("m4")``
wrongly matched a row whose list was ``["m40"]``). It also gated Oracle's true
member check on a ``"list" in field_path.lower()`` *field-name* heuristic, so a
``norm_keys`` field silently fell back to substring matching.

The fix mirrors the other backends: list-typed fields are declared via
``register_list_field`` and ``contains`` lowers to true element membership per
dialect (PG ``@>``; SQLite ``json_each``; MySQL ``JSON_CONTAINS``; Oracle
``JSON_EXISTS`` — now gated on the registry, not the field name). Scalar string
fields keep substring ``LIKE``.

SQLite is in-process, so its tests exercise real ``iter_search``. The
PG/MySQL/Oracle tests pin the emitted SQL by compiling the expression against
the target dialect (no live server needed). All run in the fast (no-services)
gate — only ``sqlalchemy`` is required.
"""

from __future__ import annotations

import datetime as dt
import json

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import MetaData  # noqa: E402
from sqlalchemy.dialects import mysql, oracle, postgresql  # noqa: E402

from specstar.query_types import (  # noqa: E402
    DataSearchCondition,
    DataSearchOperator,
    ResourceMetaSearchQuery,
)
from specstar.resource_manager.meta_store.sqlalchemy import (  # noqa: E402
    DialectType,
    SQLAlchemyMetaStore,
    _build_resource_meta_table,
)
from specstar.types import ResourceMeta  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _meta(rid: str, norm_keys: list[str]) -> ResourceMeta:
    now = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    return ResourceMeta(
        current_revision_id=f"{rid}-r1",
        resource_id=rid,
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="t",
        updated_by="t",
        indexed_data={"norm_keys": norm_keys, "title": rid},
    )


def _contains_sql(dialect_type: DialectType, sa_dialect, field_path: str, value):
    """Compile the ``contains`` predicate for *field_path* against a dialect.

    Bypasses ``__init__`` (no DB connection) and exercises the pure builder so
    the PG/MySQL/Oracle SQL can be pinned without a live server. ``norm_keys``
    is pre-registered as list-typed; pass an unregistered ``field_path`` to
    exercise the scalar fallback.
    """
    s = SQLAlchemyMetaStore.__new__(SQLAlchemyMetaStore)
    s._list_fields = {"norm_keys"}
    s._table = _build_resource_meta_table(
        "resource_meta", MetaData(), dialect=dialect_type
    )
    s._get_dialect = lambda: dialect_type
    cond = DataSearchCondition(
        field_path=field_path,
        operator=DataSearchOperator.contains,
        value=value,
    )
    expr = s._build_data_condition(cond, field_path, cond.operator, cond.value)
    compiled = expr.compile(dialect=sa_dialect)
    return str(compiled), compiled.params


# ---------------------------------------------------------------------------
# SQLite — in-process, real iter_search
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_store(tmp_path):
    db = tmp_path / "contains378.db"
    store = SQLAlchemyMetaStore(url=f"sqlite:///{db}")
    store.register_list_field("norm_keys")
    store.save_many(
        [
            _meta("forty", ["m40"]),
            _meta("four", ["capping", "m4"]),
            _meta("under", ["a_b"]),
        ]
    )
    return store


def _search(store, field_path, value):
    query = ResourceMetaSearchQuery(
        data_conditions=[
            DataSearchCondition(
                field_path=field_path,
                operator=DataSearchOperator.contains,
                value=value,
            ),
        ],
    )
    return sorted(m.resource_id for m in store.iter_search(query))


def test_sqlite_list_contains_is_element_membership(sqlite_store):
    """``contains("m4")`` must not match a row whose list is ``["m40"]``.

    The substring-LIKE bug returned both rows because ``"m4"`` is a substring
    of the serialised ``["m40"]``. Element membership returns only ``four``.
    """
    assert _search(sqlite_store, "norm_keys", "m4") == ["four"]
    assert _search(sqlite_store, "norm_keys", "m40") == ["forty"]
    assert _search(sqlite_store, "norm_keys", "capping") == ["four"]
    # Element not present anywhere.
    assert _search(sqlite_store, "norm_keys", "m") == []


def test_sqlite_list_contains_does_not_treat_value_as_like_wildcard(sqlite_store):
    """An underscore in the value is a literal char, not a LIKE ``_`` wildcard.

    Under substring LIKE, ``contains("axb")`` would match ``["a_b"]`` because
    ``_`` matches any single char. Membership compares the element verbatim.
    """
    assert _search(sqlite_store, "norm_keys", "axb") == []
    assert _search(sqlite_store, "norm_keys", "a_b") == ["under"]


def test_sqlite_scalar_field_keeps_substring(sqlite_store):
    """A non-list field keeps substring ``LIKE`` semantics (must not regress)."""
    # "our" is a substring of the title "four".
    assert _search(sqlite_store, "title", "our") == ["four"]


# ---------------------------------------------------------------------------
# PostgreSQL / MySQL / Oracle — compiled-SQL pinning
# ---------------------------------------------------------------------------


def test_postgresql_list_contains_uses_jsonb_containment():
    sql, params = _contains_sql(
        DialectType.postgresql, postgresql.dialect(), "norm_keys", "m4"
    )
    assert "@>" in sql, sql
    assert "LIKE" not in sql.upper(), sql
    # The value is JSON-encoded text cast to jsonb — exactly the param the raw
    # psycopg store sends — not double-encoded by the JSONB bind processor.
    assert json.dumps("m4") in params.values(), params
    assert '"\\"m4\\""' not in params.values(), f"double-encoded: {params}"


def test_postgresql_scalar_field_keeps_like():
    sql, params = _contains_sql(
        DialectType.postgresql, postgresql.dialect(), "description", "urgent"
    )
    assert "LIKE" in sql.upper(), sql
    assert "@>" not in sql, sql
    # SQLAlchemy's ``.contains`` wraps the wildcards in SQL, binding the raw value.
    assert "urgent" in params.values(), params


def test_mysql_list_contains_uses_json_contains():
    sql, params = _contains_sql(DialectType.mysql, mysql.dialect(), "norm_keys", "m4")
    assert "JSON_CONTAINS" in sql.upper(), sql
    assert "LIKE" not in sql.upper(), sql
    # Candidate is JSON-encoded so MySQL parses it as a JSON scalar string.
    assert json.dumps("m4") in params.values(), params


def test_oracle_list_contains_uses_json_exists():
    sql, _ = _contains_sql(DialectType.oracle, oracle.dialect(), "norm_keys", "m4")
    assert "JSON_EXISTS" in sql.upper(), sql
    assert "LIKE" not in sql.upper(), sql


def test_oracle_no_longer_keys_on_field_name_heuristic():
    """The removed ``"list" in field_path`` heuristic must not drive dispatch.

    Before #378, Oracle treated any field whose *name* contained "list" as an
    array and everything else as a string. Now dispatch is purely the
    registry: a registered ``norm_keys`` (no "list" in the name) gets the
    member check, and an unregistered ``mylist`` (has "list") gets substring.
    """
    # Registered but name has no "list" -> member check.
    sql_member, _ = _contains_sql(
        DialectType.oracle, oracle.dialect(), "norm_keys", "m4"
    )
    assert "JSON_EXISTS" in sql_member.upper(), sql_member

    # Unregistered but name has "list" -> substring LIKE (no false array path).
    sql_scalar, _ = _contains_sql(DialectType.oracle, oracle.dialect(), "mylist", "m4")
    assert "JSON_EXISTS" not in sql_scalar.upper(), sql_scalar
    assert "LIKE" in sql_scalar.upper(), sql_scalar
