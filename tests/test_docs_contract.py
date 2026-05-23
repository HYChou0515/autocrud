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
    migrate_paths = {r.path for r in app2.routes if hasattr(r, "path") and "migrate" in r.path}
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
    rid = c.post("/user", json={"name": "Bob", "email": "a@x.com"}).json()["resource_id"]
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

    old = rm.get(
        info.resource_id, revision_id=info.revision_id, include_deleted=True
    )
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
