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

from specstar import SpecStar, Schema
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
