"""`partial` is a slash-path field selector, not a boolean. Passing
`partial=true` selects a (non-existent) field named "true" and silently clears
the section — a common front-end mistake. We emit a SpecStarWarning nudge.
"""

import warnings

import msgspec
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from specstar import SpecStar
from specstar.errors import SpecStarWarning


class Widget(msgspec.Struct):
    name: str


def _client() -> TestClient:
    sp = SpecStar()
    sp.configure(default_user="t")
    sp.add_model(Widget, name="widget")
    app = FastAPI()
    sp.apply(app)
    return TestClient(app, raise_server_exceptions=False)


def _create(c: TestClient) -> str:
    return c.post("/widget", json={"name": "x"}).json()["resource_id"]


def test_partial_boolean_value_emits_nudge():
    c = _client()
    rid = _create(c)
    with pytest.warns(SpecStarWarning, match="partial"):
        c.get(f"/widget/{rid}", params={"partial": "true"})


def test_partial_real_path_emits_no_nudge():
    c = _client()
    rid = _create(c)
    with warnings.catch_warnings():
        warnings.simplefilter("error", SpecStarWarning)
        c.get(f"/widget/{rid}", params={"partial": "/name"})  # must not warn
