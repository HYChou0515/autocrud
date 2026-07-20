"""Regression tests that lock the behaviors documented by the doc-fix PRs.

Guards against the doc/reality drift found while evaluating SpecStar 0.11:
  * RevisionNotMigratedError is importable from `specstar.errors`
  * generated routes use the singular model name + `{resource_id}`
  * migrate routes are NOT registered by default (opt-in via MigrateRouteTemplate)
  * the documented migrate -> rollback flow works for a breaking change
"""

import datetime as dt
from typing import Literal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct

from specstar import Schema, SpecStar
from specstar.backend import DiskStorageFactory
from specstar.crud.route_templates.migrate import MigrateRouteTemplate


def _fresh(tmp_path):
    s = SpecStar()
    s.configure(
        storage_factory=DiskStorageFactory(str(tmp_path)),
        default_user="test",
        default_now=lambda: dt.datetime.now(dt.timezone.utc),
    )
    return s


def test_revision_not_migrated_error_import_path():
    from specstar.errors import RevisionNotMigratedError  # noqa: F401


def test_routes_use_singular_name_and_resource_id(tmp_path):
    class User(Struct):
        name: str
        email: str

    sp = _fresh(tmp_path)
    app = FastAPI()
    sp.add_model(Schema(User, "v1"))
    sp.apply(app)

    paths = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/user" in paths
    assert "/user/{resource_id}" in paths
    assert "/users" not in paths


def test_migrate_routes_are_opt_in(tmp_path):
    class User(Struct):
        name: str
        email: str

    # default: no migrate routes
    sp = _fresh(tmp_path)
    app = FastAPI()
    sp.add_model(Schema(User, "v1"))
    sp.apply(app)
    assert not any("migrate" in r.path for r in app.routes if hasattr(r, "path"))

    # opt-in: migrate routes appear
    sp2 = _fresh(tmp_path)
    sp2.add_route_template(MigrateRouteTemplate())
    app2 = FastAPI()
    sp2.add_model(Schema(User, "v1"))
    sp2.apply(app2)
    migrate_paths = {
        r.path for r in app2.routes if hasattr(r, "path") and "migrate" in r.path
    }
    assert "/user/migrate/execute" in migrate_paths
    assert "/user/migrate/single/{resource_id}" in migrate_paths


def test_breaking_migration_then_rollback(tmp_path):
    class User(Struct):
        name: str
        email: str

    sp = _fresh(tmp_path)
    app = FastAPI()
    sp.add_model(Schema(User, "v1"))
    sp.apply(app)
    c = TestClient(app)
    rid = c.post("/user", json={"name": "Bob", "email": "a@x.com"}).json()[
        "resource_id"
    ]
    c.put(f"/user/{rid}", json={"name": "Bob", "email": "b@x.com"})

    class UserV1(Struct):
        name: str
        email: str

    class User(Struct):  # v2 shape, same model name -> same storage
        name: str
        role: Literal["admin", "guest"]
        email: str = ""

    def migrate_v1_to_v2(old: UserV1) -> User:
        return User(name=old.name, role="guest", email=old.email)

    sp2 = _fresh(tmp_path)
    app2 = FastAPI()
    sp2.add_model(Schema(User, "v2").step("v1", migrate_v1_to_v2, source_type=UserV1))
    sp2.apply(app2)
    rm = sp2.get_resource_manager(User)

    rm.migrate(rid)
    assert rm.get(rid).data.role == "guest"

    # Roll back to the oldest revision. Migrating that specific revision first is
    # the documented, always-safe path. (Note: whether switching an *un-migrated*
    # revision raises RevisionNotMigratedError appears state-dependent in 0.11,
    # so we don't assert on that here -- see the companion issue.)
    oldest = rm.list_revisions(rid)[-1]
    rm.migrate(rid, revision_id=oldest)
    rm.switch(rid, oldest)
    assert rm.get(rid).data.name == "Bob"


# --- Data Versioning quickstart (docs/en/quickstart/data-versioning.md) ---


class _Doc(Struct):
    title: str
    body: str = ""


def _doc_mgr(tmp_path):
    sp = _fresh(tmp_path)
    app = FastAPI()
    sp.add_model(Schema(_Doc, "v1"))
    sp.apply(app)
    return sp.get_resource_manager(_Doc)


def test_get_old_revision_after_soft_delete_with_include_deleted(tmp_path):
    """§5: after a soft delete you can still read an older revision via
    ``get(..., include_deleted=True)``."""
    rm = _doc_mgr(tmp_path)
    info = rm.create(_Doc(title="Onboarding", body="v1"))
    rm.update(info.resource_id, _Doc(title="Onboarding", body="v2"))
    rm.delete(info.resource_id)

    old = rm.get(info.resource_id, revision_id=info.revision_id, include_deleted=True)
    assert old.data.body == "v1"


def test_get_after_soft_delete_still_raises_by_default(tmp_path):
    """Back-compat: ``include_deleted`` defaults to False, so reading a
    soft-deleted resource still raises (no behavior change)."""
    from specstar.types import ResourceIsDeletedError

    rm = _doc_mgr(tmp_path)
    info = rm.create(_Doc(title="Onboarding", body="v1"))
    rm.delete(info.resource_id)

    with pytest.raises(ResourceIsDeletedError):
        rm.get(info.resource_id, revision_id=info.revision_id)


def test_list_revisions_returns_ids_and_get_revision_info(tmp_path):
    """§4: list_revisions() returns revision-id *strings*; rich per-revision
    metadata (revision_id / created_time / created_by) comes from
    get_revision_info()."""
    rm = _doc_mgr(tmp_path)
    info = rm.create(_Doc(title="t", body="v1"))
    rm.update(info.resource_id, _Doc(title="t", body="v2"))

    rev_ids = rm.list_revisions(info.resource_id)
    assert len(rev_ids) == 2
    assert all(isinstance(rid, str) for rid in rev_ids)

    rev = rm.get_revision_info(info.resource_id, revision_id=rev_ids[0])
    assert isinstance(rev.revision_id, str)
    assert rev.created_time is not None
    assert isinstance(rev.created_by, str)


def test_delete_returns_resource_meta_not_revision_info(tmp_path):
    """§5: delete() returns a ResourceMeta (is_deleted=True) — it has
    current_revision_id, not a .revision_id."""
    from specstar.types import ResourceMeta

    rm = _doc_mgr(tmp_path)
    info = rm.create(_Doc(title="t", body="v1"))
    meta = rm.delete(info.resource_id)

    assert isinstance(meta, ResourceMeta)
    assert meta.is_deleted is True
    assert isinstance(meta.current_revision_id, str)
    assert not hasattr(meta, "revision_id")


# --- Prune revisions how-to (docs/en/howto/prune-revisions.md) ---


class _Cfg(Struct):
    value: str


def _cfg_history(tmp_path, n=8):
    """A resource with ``n`` revisions stamped one day apart (rev 1 oldest ...
    rev n current), mirroring the how-to's example. Returns (mgr, rid, base)."""
    sp = _fresh(tmp_path)
    app = FastAPI()
    sp.add_model(Schema(_Cfg, "v1"))
    sp.apply(app)
    mgr = sp.get_resource_manager(_Cfg)
    base = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
    info = mgr.create(_Cfg(value="v0"), now=base)
    rid = info.resource_id
    for i in range(1, n):
        mgr.update(rid, _Cfg(value=f"v{i}"), now=base + dt.timedelta(days=i))
    return mgr, rid, base


def test_prune_keep_last_n_drops_oldest_and_keeps_current(tmp_path):
    """keep_last_n keeps the current + the (n-1) newest; the rest are pruned."""
    mgr, rid, _ = _cfg_history(tmp_path)
    assert len(mgr.list_revisions(rid)) == 8
    assert mgr.get_meta(rid).total_revision_count == 8

    pruned = mgr.prune_revisions(rid, keep_last_n=3)

    assert isinstance(pruned, list) and all(isinstance(r, str) for r in pruned)
    assert len(pruned) == 5
    assert len(mgr.list_revisions(rid)) == 3
    # the current revision is never pruned and stays readable
    assert mgr.get(rid).data.value == "v7"


def test_prune_leaves_total_revision_count_monotonic(tmp_path):
    """The live count is len(list_revisions()); total_revision_count never drops
    (it seeds new revision ids)."""
    mgr, rid, _ = _cfg_history(tmp_path)
    mgr.prune_revisions(rid, keep_last_n=3)
    assert len(mgr.list_revisions(rid)) == 3
    assert mgr.get_meta(rid).total_revision_count == 8


def test_prune_before_drops_strictly_older(tmp_path):
    """before keeps revisions created at/after the cutoff, prunes strictly older
    ones."""
    mgr, rid, base = _cfg_history(tmp_path)
    cutoff = base + dt.timedelta(days=4)  # keep rev 5..8 (v4..v7), prune v0..v3
    pruned = mgr.prune_revisions(rid, before=cutoff)
    assert len(pruned) == 4
    survivors = {
        mgr.get(rid, revision_id=r).data.value for r in mgr.list_revisions(rid)
    }
    assert survivors == {"v4", "v5", "v6", "v7"}


def test_prune_union_is_conservative(tmp_path):
    """With both knobs the kept sets union: a revision survives if *either* knob
    keeps it, so combining prunes no more than either knob alone."""
    # keep_last_n=2 alone would prune 6 (keep only v6, v7) ...
    mgr_a, rid_a, _ = _cfg_history(tmp_path)
    assert len(mgr_a.prune_revisions(rid_a, keep_last_n=2)) == 6

    # ... but unioned with before=day4 (which keeps v4..v7), only v0..v3 are
    # pruned: v4, v5 survive because `before` keeps them.
    mgr_b, rid_b, base = _cfg_history(tmp_path)
    pruned = mgr_b.prune_revisions(
        rid_b, keep_last_n=2, before=base + dt.timedelta(days=4)
    )
    assert len(pruned) == 4
    survivors = {
        mgr_b.get(rid_b, revision_id=r).data.value for r in mgr_b.list_revisions(rid_b)
    }
    assert survivors == {"v4", "v5", "v6", "v7"}


def test_prune_requires_a_knob_and_validates(tmp_path):
    """Neither knob, or keep_last_n < 1, raises ValueError; an unknown resource
    id raises ResourceIDNotFoundError."""
    from specstar.types import ResourceIDNotFoundError

    mgr, rid, _ = _cfg_history(tmp_path)
    with pytest.raises(ValueError):
        mgr.prune_revisions(rid)  # neither keep_last_n nor before
    with pytest.raises(ValueError):
        mgr.prune_revisions(rid, keep_last_n=0)
    with pytest.raises(ResourceIDNotFoundError):
        mgr.prune_revisions(rid.split(":")[0] + ":nonexistent", keep_last_n=1)
