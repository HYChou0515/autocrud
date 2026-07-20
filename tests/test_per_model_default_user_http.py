"""Slice 1: per-model ``default_user`` must reach HTTP-created audit fields.

Previously ``add_model(default_user="alice")`` only set the manager's
programmatic default; HTTP requests still recorded ``"anonymous"`` because the
route pushed the global DependencyProvider's user. These tests pin the fixed
precedence: real ``get_user`` (auth) > per-model default_user >
global ``configure`` default_user > ``"anonymous"``.
"""

import datetime as dt

import msgspec
from fastapi import FastAPI
from fastapi.testclient import TestClient

from specstar import Schema, SpecStar
from specstar.crud.route_templates.basic import DependencyProvider


class Item(msgspec.Struct):
    name: str


def _created_by(sp: SpecStar) -> str:
    app = FastAPI()
    sp.apply(app)
    c = TestClient(app)
    rid = c.post("/item", json={"name": "x"}).json()["resource_id"]
    return sp.get_resource_manager(Item).get_meta(rid).created_by


def test_add_model_default_user_reaches_http_created_by():
    sp = SpecStar()
    sp.configure()
    sp.add_model(Schema(Item, "v1"), default_user="alice")
    assert _created_by(sp) == "alice"


def test_real_get_user_wins_over_per_model_default():
    """A real authentication ``get_user`` must never be overridden by a
    per-model default — auth is the top of the precedence chain."""
    sp = SpecStar()
    sp.configure(dependency_provider=DependencyProvider(get_user=lambda: "real-bob"))
    sp.add_model(Schema(Item, "v1"), default_user="alice")
    assert _created_by(sp) == "real-bob"


def test_per_model_default_user_overrides_global_configure():
    sp = SpecStar()
    sp.configure(default_user="global-bob")
    sp.add_model(Schema(Item, "v1"), default_user="alice")
    assert _created_by(sp) == "alice"


def test_add_model_default_now_overrides_configure_default_now():
    """Per-model ``default_now`` overrides the global one (programmatic path).
    (We intentionally do not wire default_now into HTTP; see the issue.)"""
    per_model = dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc)
    sp = SpecStar()
    sp.configure(
        default_user="t",
        default_now=lambda: dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc),
    )
    sp.add_model(Schema(Item, "v1"), default_now=lambda: per_model)
    mgr = sp.get_resource_manager(Item)
    info = mgr.create(Item(name="x"))
    assert mgr.get_meta(info.resource_id).created_time == per_model
