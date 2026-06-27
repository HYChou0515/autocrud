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
from specstar.permission.action import ActionBasedPermissionChecker
from specstar.permission.builtins import any_user
from specstar.permission.checker import PermissionContext, PermissionResult
from specstar.resource_manager.core import ResourceManager, SimpleStorage
from specstar.resource_manager.meta_store.simple import MemoryMetaStore
from specstar.resource_manager.resource_store.simple import MemoryResourceStore
from specstar.types import (
    IndexableField,
    OnUnindexedQuery,
    PermissionDeniedError,
    ResourceAction,
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
def _mk_rm(
    access_scope=scope_for,
    on_unindexed_query=OnUnindexedQuery.warn,
    permission_checker=None,
):
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
        permission_checker=permission_checker,
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
# Write access-scope gate (#398 follow-up) — a resource outside the caller's
# scope is hidden as 404 on writes too, *before* the permission checker runs.
# access_scope is a necessary precondition for request-originated writes; the
# permission checker still authorizes the in-scope ones.
# --------------------------------------------------------------------------- #
def test_out_of_scope_update_is_404():
    rm = _mk_rm()
    ids = _seed(rm)
    # bob may update his own in-scope doc
    with rm.using("bob", NOW, apply_access_scope=True) as op:
        op.update(ids["bob_priv"], Doc(owner="bob", visibility="private"))
    # ...but carol's private doc is hidden as not-found on write too (not 403/200)
    with rm.using("bob", NOW, apply_access_scope=True) as op:  # noqa: SIM117
        with pytest.raises(ResourceIDNotFoundError):
            op.update(ids["carol_priv"], Doc(owner="carol", visibility="private"))


def _deny_update(context: PermissionContext) -> PermissionResult:
    # No @requires_resource_parts marker → declares no slices, so the
    # current_resource load does *not* incidentally trigger the scope probe.
    return PermissionResult.deny


def _deny_update_checker() -> ActionBasedPermissionChecker:
    return ActionBasedPermissionChecker.from_dict(
        {
            ResourceAction.create: any_user,
            ResourceAction.read: any_user,
            ResourceAction.update: _deny_update,
        }
    )


def test_out_of_scope_write_404s_before_permission_403():
    """Scope is evaluated first: an out-of-scope write 404s (existence hidden)
    before the permission checker can 403 — even when the checker declares no
    resource parts, so the current_resource load wouldn't incidentally probe."""
    rm = _mk_rm(permission_checker=_deny_update_checker())
    ids = _seed(rm)
    with rm.using("bob", NOW, apply_access_scope=True) as op:  # noqa: SIM117
        # carol's doc is out of bob's scope → not-found, never the deny verdict
        with pytest.raises(ResourceIDNotFoundError):
            op.update(ids["carol_priv"], Doc(owner="carol", visibility="private"))


def test_in_scope_write_still_runs_the_checker():
    """Scope is a precondition, not authorization: an in-scope write still goes
    through the permission checker (here: deny → 403, not a silent allow)."""
    rm = _mk_rm(permission_checker=_deny_update_checker())
    ids = _seed(rm)
    with rm.using("bob", NOW, apply_access_scope=True) as op:  # noqa: SIM117
        # bob_priv IS in bob's scope, so the checker runs and denies it
        with pytest.raises(PermissionDeniedError):
            op.update(ids["bob_priv"], Doc(owner="bob", visibility="private"))


def test_internal_writes_are_never_scoped():
    """Without ``apply_access_scope=True`` (every internal call), a write of a
    resource the predicate would hide still succeeds — internal machinery is
    trusted, exactly like internal reads."""
    rm = _mk_rm()
    ids = _seed(rm)
    with rm.using("bob", NOW) as op:  # no apply_access_scope
        op.update(ids["carol_priv"], Doc(owner="carol", visibility="private"))
        op.delete(ids["carol_priv"])  # carol's doc, out of bob's read scope


def test_write_unaffected_when_no_access_scope_configured():
    """A model with no ``access_scope`` pays nothing and behaves exactly as
    before, even under ``apply_access_scope=True``."""
    rm = _mk_rm(access_scope=None)
    ids = _seed(rm)
    with rm.using("dave", NOW, apply_access_scope=True) as op:
        op.update(ids["carol_priv"], Doc(owner="carol", visibility="private"))


def test_out_of_scope_lifecycle_writes_are_404():
    """Every request-originated write that targets an existing resource by id
    is gated, so an out-of-scope caller cannot soft-delete / hard-delete /
    switch / restore a resource they can't even see."""
    rm = _mk_rm()
    ids = _seed(rm)
    carol = ids["carol_priv"]  # out of bob's scope
    with rm.using("bob", NOW, apply_access_scope=True) as op:
        with pytest.raises(ResourceIDNotFoundError):
            op.delete(carol)
        with pytest.raises(ResourceIDNotFoundError):
            op.permanently_delete(carol)
        with pytest.raises(ResourceIDNotFoundError):
            op.switch(carol, "any-revision")
        with pytest.raises(ResourceIDNotFoundError):
            op.restore(carol)


def test_in_scope_restore_after_soft_delete_passes_the_gate():
    """A soft-deleted but in-scope resource can still be restored under the
    write gate — the scope probe must not filter out deleted rows, or restore
    would 404 itself."""
    rm = _mk_rm()
    ids = _seed(rm)
    bob_doc = ids["bob_priv"]
    with rm.using("bob", NOW, apply_access_scope=True) as op:
        op.delete(bob_doc)  # soft-delete own (in scope)
        meta = op.restore(bob_doc)  # restore own — the gate must still allow it
    assert meta.is_deleted is False


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


def test_http_writes_are_scoped(client: TestClient):
    """Every request-originated write route opts into access-scope: a caller
    who can't see a resource gets 404 (existence hidden) on writes too, while
    the owner can still write their own."""
    carol_priv = _create(client, "carol", visibility="private")
    body = {"owner": "carol", "visibility": "private", "readers": []}
    bob = {"X-User": "bob"}
    assert client.put(f"/doc/{carol_priv}", json=body, headers=bob).status_code == 404
    assert client.delete(f"/doc/{carol_priv}", headers=bob).status_code == 404
    assert (
        client.delete(f"/doc/{carol_priv}/permanently", headers=bob).status_code == 404
    )
    assert client.post(f"/doc/{carol_priv}/restore", headers=bob).status_code == 404
    # carol (owner, in scope) can update her own doc
    assert (
        client.put(
            f"/doc/{carol_priv}", json=body, headers={"X-User": "carol"}
        ).status_code
        == 200
    )


def test_http_batch_delete_only_touches_in_scope_rows(client: TestClient):
    """A batch delete is bounded by the caller's scope — it cannot reach rows
    the caller can't even see."""
    pub = _create(client, "alice", visibility="public")
    carol_priv = _create(client, "carol", visibility="private")
    # bob batch-deletes everything he can: only the public row is in scope
    r = client.request("DELETE", "/doc", headers={"X-User": "bob"})
    assert r.status_code == 200, r.text
    deleted = {m["resource_id"] for m in r.json()}
    assert deleted == {pub}
    # carol's private row was never touched (still visible & active to carol)
    assert (
        client.get(f"/doc/{carol_priv}", headers={"X-User": "carol"}).status_code == 200
    )
