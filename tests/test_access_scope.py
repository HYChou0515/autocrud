"""Per-model read/list access-scope predicate — issue #398, part A.

``access_scope`` is a per-model callable ``user -> ConditionBuilder | None |
UNRESTRICTED`` that specstar ANDs into every *request-originated* read
(list/search/count + every single-resource GET variant) at the
ResourceManager read layer. Out-of-scope resources become 404 (existence
hidden, uniformly with list filtering); ``None`` denies all (fail-closed) and
``UNRESTRICTED`` skips scoping. Internal ResourceManager reads stay unscoped.

These tests pin the behaviour at three levels:

* ResourceManager (in-memory) — the enforcement logic itself;
* the SQLAlchemy meta store (real sqlite) — cross-backend consistency, and the
  ``contains_any`` operator the canonical ACL predicate needs (previously
  silently dropped on SQLAlchemy — a security hole this feature exposed);
* the generated HTTP routes (TestClient) — that every read route opts in.
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi import APIRouter, FastAPI, Header
from fastapi.testclient import TestClient
from msgspec import Struct

from specstar import QB, UNRESTRICTED, SpecStar
from specstar.crud.route_templates.dependency_provider import DependencyProvider
from specstar.resource_manager.core import ResourceManager, SimpleStorage
from specstar.resource_manager.meta_store.simple import MemoryMetaStore
from specstar.resource_manager.resource_store.simple import MemoryResourceStore
from specstar.types import (
    IndexableField,
    OnUnindexedQuery,
    ResourceIDNotFoundError,
    UnindexedQueryError,
)

NOW = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc)


class Doc(Struct):
    owner: str = ""
    visibility: str = "private"
    readers: list[str] = []  # noqa: RUF012


def scope_for(user: str):
    """Canonical row-level ACL: public, or you own it, or you're a reader.

    Admins see everything; a banned user sees nothing (fail-closed).
    """
    if user == "admin":
        return UNRESTRICTED
    if user == "banned":
        return None
    return (
        (QB["visibility"] == "public")
        | (QB["owner"] == user)
        | QB["readers"].contains_any([user])
    )


def _indexed_fields() -> list[IndexableField]:
    return [
        IndexableField(field_path="visibility", field_type=str),
        IndexableField(field_path="owner", field_type=str),
        IndexableField(field_path="readers", field_type=list),
    ]


# --------------------------------------------------------------------------- #
# ResourceManager-level (in-memory)
# --------------------------------------------------------------------------- #
def _mk_rm(access_scope=scope_for, on_unindexed_query=OnUnindexedQuery.warn):
    storage = SimpleStorage(
        meta_store=MemoryMetaStore(),
        resource_store=MemoryResourceStore(Doc),  # ty:ignore[invalid-argument-type]
    )
    return ResourceManager(
        Doc,
        storage=storage,
        indexed_fields=_indexed_fields(),
        access_scope=access_scope,
        on_unindexed_query=on_unindexed_query,
    )


def _seed(rm) -> dict[str, str]:
    """Create four docs; return name -> resource_id."""
    docs = {
        "pub": Doc(owner="alice", visibility="public", readers=[]),
        "alice_priv": Doc(owner="alice", visibility="private", readers=["bob"]),
        "bob_priv": Doc(owner="bob", visibility="private", readers=[]),
        "carol_priv": Doc(owner="carol", visibility="private", readers=["alice"]),
    }
    ids = {}
    for name, doc in docs.items():
        with rm.using(doc.owner, NOW) as op:
            ids[name] = op.create(doc).resource_id
    return ids


def test_list_filters_rows_by_scope():
    rm = _mk_rm()
    ids = _seed(rm)

    # bob: public + his own + docs he can read
    with rm.using("bob", NOW, apply_access_scope=True) as op:
        got = {r.meta.resource_id for r in op.list_resources()}
    assert got == {ids["pub"], ids["alice_priv"], ids["bob_priv"]}
    assert ids["carol_priv"] not in got

    # alice: public + her own + carol's doc shared with her
    with rm.using("alice", NOW, apply_access_scope=True) as op:
        got = {r.meta.resource_id for r in op.list_resources()}
    assert got == {ids["pub"], ids["alice_priv"], ids["carol_priv"]}

    # dave: only the public one
    with rm.using("dave", NOW, apply_access_scope=True) as op:
        got = {r.meta.resource_id for r in op.list_resources()}
    assert got == {ids["pub"]}


def test_count_is_scoped_like_list():
    rm = _mk_rm()
    _seed(rm)
    for user, expected in [("bob", 3), ("alice", 3), ("dave", 1), ("admin", 4)]:
        with rm.using(user, NOW, apply_access_scope=True) as op:
            assert op.count_resources() == expected, user


def test_single_get_hides_out_of_scope_as_404():
    rm = _mk_rm()
    ids = _seed(rm)
    # bob may read his own private doc
    with rm.using("bob", NOW, apply_access_scope=True) as op:
        assert op.get(ids["bob_priv"]).data.owner == "bob"
    # ...but carol's private doc is hidden as not-found, not 403
    with rm.using("bob", NOW, apply_access_scope=True) as op:  # noqa: SIM117
        with pytest.raises(ResourceIDNotFoundError):
            op.get(ids["carol_priv"])


def test_single_get_meta_and_revision_info_also_404():
    rm = _mk_rm()
    ids = _seed(rm)
    with rm.using("bob", NOW, apply_access_scope=True) as op:
        with pytest.raises(ResourceIDNotFoundError):
            op.get_meta(ids["carol_priv"])
    # revision-info with an *explicit* revision id is the one single-resource
    # path that does not lead with get_meta — it must still be gated.
    rev = rm.get_revision_info(ids["carol_priv"]).revision_id  # internal, unscoped
    with rm.using("bob", NOW, apply_access_scope=True) as op:
        with pytest.raises(ResourceIDNotFoundError):
            op.get_revision_info(ids["carol_priv"], rev)
        with pytest.raises(ResourceIDNotFoundError):
            op.get_revision_info(ids["carol_priv"])  # UNSET branch too


def test_none_denies_all_fail_closed():
    rm = _mk_rm()
    ids = _seed(rm)
    with rm.using("banned", NOW, apply_access_scope=True) as op:
        assert op.list_resources() == []
        assert op.count_resources() == 0
        with pytest.raises(ResourceIDNotFoundError):
            op.get(ids["pub"])  # even the public doc is hidden


def test_unrestricted_sees_everything():
    rm = _mk_rm()
    ids = _seed(rm)
    with rm.using("admin", NOW, apply_access_scope=True) as op:
        assert {r.meta.resource_id for r in op.list_resources()} == set(ids.values())
        assert op.get(ids["carol_priv"]).data.owner == "carol"


def test_internal_reads_are_never_scoped():
    """Without ``apply_access_scope=True`` (every internal call), reads see
    everything — even for a user the predicate would otherwise restrict."""
    rm = _mk_rm()
    ids = _seed(rm)
    with rm.using("dave", NOW) as op:  # no apply_access_scope
        assert {r.meta.resource_id for r in op.list_resources()} == set(ids.values())
        assert op.count_resources() == len(ids)
        assert op.get(ids["carol_priv"]).data.owner == "carol"


def test_scope_anded_with_user_query():
    """A caller's own filter ANDs with the scope, never widens it."""
    rm = _mk_rm()
    ids = _seed(rm)
    with rm.using("bob", NOW, apply_access_scope=True) as op:
        # Narrowing to owner==alice keeps only the in-scope alice docs.
        got = {r.meta.resource_id for r in op.list_resources(QB["owner"] == "alice")}
        assert got == {ids["pub"], ids["alice_priv"]}
        # Querying for carol's docs returns nothing — the scope still hides them
        # even though the user's filter explicitly asks for owner==carol.
        widen = list(op.list_resources(QB["owner"] == "carol"))
    assert widen == []


def test_scope_on_unindexed_field_always_raises():
    """A scope predicate over a non-indexed field must fail loudly (never
    silently degrade), regardless of the lenient ``on_unindexed_query``."""

    def bad_scope(user: str):
        return QB["secret"] == "x"  # 'secret' is not indexed

    rm = _mk_rm(access_scope=bad_scope, on_unindexed_query=OnUnindexedQuery.warn)
    ids = _seed(rm)
    with rm.using("bob", NOW, apply_access_scope=True) as op:
        with pytest.raises(UnindexedQueryError):
            op.list_resources()
        with pytest.raises(UnindexedQueryError):
            op.get(ids["pub"])


def test_contains_any_membership_in_memory():
    """The ACL list-membership term resolves to true element overlap."""
    rm = _mk_rm()
    ids = _seed(rm)
    # bob is a reader of alice_priv only
    with rm.using("bob", NOW, apply_access_scope=True) as op:
        got = {r.meta.resource_id for r in op.list_resources()}
    assert ids["alice_priv"] in got


# --------------------------------------------------------------------------- #
# SQLAlchemy meta store (real sqlite) — cross-backend consistency + the
# previously-missing contains_any operator (#398 / #378).
# --------------------------------------------------------------------------- #
def _mk_sqlalchemy_rm():
    from sqlalchemy import create_engine

    from specstar.resource_manager.meta_store.sqlalchemy import SQLAlchemyMetaStore

    engine = create_engine("sqlite://")  # in-process; pooled kwargs rejected by sqlite
    meta_store = SQLAlchemyMetaStore("sqlite://", engine=engine)
    meta_store.register_list_field("readers")
    storage = SimpleStorage(
        meta_store=meta_store,
        resource_store=MemoryResourceStore(Doc),  # ty:ignore[invalid-argument-type]
    )
    return ResourceManager(
        Doc,
        storage=storage,
        indexed_fields=_indexed_fields(),
        access_scope=scope_for,
    )


def test_sqlalchemy_contains_any_builds_membership_predicate():
    """Regression: ``contains_any`` was unhandled in the SQLAlchemy builder and
    silently dropped — for an access scope that is over-matching (a security
    hole). It must now compile to JSON element membership, not vanish."""
    from sqlalchemy import create_engine
    from sqlalchemy.dialects import sqlite

    from specstar.query_types import DataSearchCondition, DataSearchOperator
    from specstar.resource_manager.meta_store.sqlalchemy import SQLAlchemyMetaStore

    store = SQLAlchemyMetaStore("sqlite://", engine=create_engine("sqlite://"))
    store.register_list_field("readers")
    cond = DataSearchCondition(
        field_path="readers",
        operator=DataSearchOperator.contains_any,
        value=["alice", "bob"],
    )
    expr = store._build_condition(cond)
    assert expr is not None, "contains_any must not be dropped"
    sql = str(
        expr.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True})
    )
    assert "json_each" in sql  # element membership, not a substring LIKE
    # empty candidate set matches nothing (not everything)
    empty = store._build_condition(
        DataSearchCondition(
            field_path="readers",
            operator=DataSearchOperator.contains_any,
            value=[],
        )
    )
    assert empty is not None


def test_sqlalchemy_backend_scope_consistent_with_memory():
    rm = _mk_sqlalchemy_rm()
    ids = _seed(rm)
    # Same expectations as the in-memory backend → cross-backend consistency.
    with rm.using("bob", NOW, apply_access_scope=True) as op:
        listed = {r.meta.resource_id for r in op.list_resources()}
        count = op.count_resources()
    assert listed == {ids["pub"], ids["alice_priv"], ids["bob_priv"]}
    assert count == 3
    with rm.using("bob", NOW, apply_access_scope=True) as op:  # noqa: SIM117
        with pytest.raises(ResourceIDNotFoundError):
            op.get(ids["carol_priv"])


# --------------------------------------------------------------------------- #
# HTTP routes (TestClient) — every read route opts into scoping.
# --------------------------------------------------------------------------- #
def _get_user(x_user: str = Header(default="anonymous")) -> str:
    return x_user


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    router = APIRouter()
    spec = SpecStar(dependency_provider=DependencyProvider(get_user=_get_user))
    spec.add_model(
        Doc,
        indexed_fields=[("visibility", str), ("owner", str), ("readers", list)],
        access_scope=scope_for,
    )
    spec.apply(router)
    app.include_router(router)
    return TestClient(app)


def _create(client: TestClient, owner: str, **kw) -> str:
    body = {
        "owner": owner,
        "visibility": kw.get("visibility", "private"),
        "readers": kw.get("readers", []),
    }
    r = client.post("/doc", json=body, headers={"X-User": owner})
    assert r.status_code == 200, r.text
    return r.json()["resource_id"]


def test_http_list_and_single_get_are_scoped(client: TestClient):
    pub = _create(client, "alice", visibility="public")
    alice_priv = _create(client, "alice", visibility="private", readers=["bob"])
    bob_priv = _create(client, "bob", visibility="private")
    carol_priv = _create(client, "carol", visibility="private", readers=["alice"])

    # bob's list: public + own + reader-of
    r = client.get("/doc", headers={"X-User": "bob"})
    assert r.status_code == 200
    got = {item["meta"]["resource_id"] for item in r.json()}
    assert got == {pub, alice_priv, bob_priv}

    # count agrees
    r = client.get("/doc/count", headers={"X-User": "bob"})
    assert r.status_code == 200 and r.json() == 3

    # carol's private doc is a 404 for bob (existence hidden), 200 for carol
    assert (
        client.get(f"/doc/{carol_priv}", headers={"X-User": "bob"}).status_code == 404
    )
    assert (
        client.get(f"/doc/{carol_priv}", headers={"X-User": "carol"}).status_code == 200
    )

    # admin (UNRESTRICTED) sees all four
    r = client.get("/doc/count", headers={"X-User": "admin"})
    assert r.json() == 4


def test_http_banned_user_sees_nothing(client: TestClient):
    pub = _create(client, "alice", visibility="public")
    r = client.get("/doc", headers={"X-User": "banned"})
    assert r.status_code == 200 and r.json() == []
    assert client.get(f"/doc/{pub}", headers={"X-User": "banned"}).status_code == 404
