"""Python-only, server-rendered, read-only admin UI.

Opt-in via ``spec.apply(app, admin_ui="/admin")`` (needs the ``[admin-ui]``
extra). Renders from the in-process registry; no Node / pnpm / vite.
"""

import builtins

import msgspec
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from specstar import SpecStar


class Widget(msgspec.Struct):
    name: str
    qty: int = 0


def _client(**apply_kw) -> TestClient:
    sp = SpecStar()
    sp.configure(default_user="t")
    sp.add_model(Widget, name="widget")
    app = FastAPI()
    sp.apply(app, admin_ui="/admin", **apply_kw)
    return TestClient(app)


def test_admin_index_lists_registered_models():
    c = _client()
    r = c.get("/admin")
    assert r.status_code == 200
    assert "widget" in r.text


def test_model_list_shows_resource_rows():
    c = _client()
    c.post("/widget", json={"name": "alpha", "qty": 3})
    c.post("/widget", json={"name": "beta", "qty": 5})
    r = c.get("/admin/widget")
    assert r.status_code == 200
    assert "alpha" in r.text and "beta" in r.text


def test_model_list_unknown_model_404():
    c = _client()
    assert c.get("/admin/nope").status_code == 404


def test_detail_shows_data_and_meta():
    c = _client()
    rid = c.post("/widget", json={"name": "alpha", "qty": 3}).json()["resource_id"]
    r = c.get(f"/admin/widget/{rid}")
    assert r.status_code == 200
    assert "alpha" in r.text  # data field
    assert rid in r.text  # resource_id (from meta)


def test_detail_unknown_resource_404():
    c = _client()
    assert c.get("/admin/widget/widget:does-not-exist").status_code == 404


def test_revisions_page_lists_all_revisions():
    c = _client()
    rid = c.post("/widget", json={"name": "v1", "qty": 1}).json()["resource_id"]
    c.put(f"/widget/{rid}", json={"name": "v2", "qty": 2})  # creates a 2nd revision
    r = c.get(f"/admin/widget/{rid}/revisions")
    assert r.status_code == 200
    assert f"{rid}:1" in r.text and f"{rid}:2" in r.text


def test_admin_list_respects_permission_checker():
    # The admin must not bypass permissions: a denied read -> 403, not data/500.
    from specstar.permission.checker import IPermissionChecker, PermissionResult
    from specstar.types import ResourceAction

    class DenyListing(IPermissionChecker):
        def check_permission(self, ctx):
            if ctx.action == ResourceAction.search_resources:
                return PermissionResult.deny
            return PermissionResult.allow

    sp = SpecStar()
    sp.configure(default_user="t", permission_checker=DenyListing())
    sp.add_model(Widget, name="widget")
    app = FastAPI()
    sp.apply(app, admin_ui="/admin")
    c = TestClient(app, raise_server_exceptions=False)
    c.post("/widget", json={"name": "x"})  # create is allowed
    assert c.get("/admin/widget").status_code == 403


def test_missing_admin_ui_extra_gives_clear_error(monkeypatch):
    # Simulate the [admin-ui] extra not being installed (no jinja2).
    real_import = builtins.__import__

    def no_jinja2(name, *args, **kwargs):
        if name == "jinja2" or name.startswith("jinja2."):
            raise ImportError("No module named 'jinja2'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_jinja2)

    sp = SpecStar()
    sp.configure(default_user="t")
    sp.add_model(Widget, name="widget")
    with pytest.raises(ImportError, match="admin-ui"):
        sp.apply(FastAPI(), admin_ui="/admin")
