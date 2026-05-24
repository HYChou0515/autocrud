"""GET response-shape control via the `returns` vocabulary.

`?returns=data,meta,revision_info` (the default) returns the full envelope.
The new `only-*` values return a *bare* section (unwrapped), so a front end
that wants a plain object can ask for `?returns=only-data`. `only-*` must be
used alone — combining it with any other value is a 422.
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


def _client(**cfg) -> TestClient:
    sp = SpecStar()
    sp.configure(default_user="t", **cfg)
    sp.add_model(Widget, name="widget")
    app = FastAPI()
    sp.apply(app)
    return TestClient(app, raise_server_exceptions=False)


def _create(c: TestClient, name: str = "x") -> str:
    return c.post("/widget", json={"name": name}).json()["resource_id"]


def test_returns_only_data_is_a_bare_object():
    c = _client()
    rid = _create(c)
    r = c.get(f"/widget/{rid}", params={"returns": "only-data"})
    assert r.status_code == 200
    assert r.json() == {"name": "x"}  # bare object, not {"data": {...}}


def test_returns_only_meta_is_bare_meta():
    c = _client()
    rid = _create(c)
    r = c.get(f"/widget/{rid}", params={"returns": "only-meta"})
    assert r.status_code == 200
    body = r.json()
    assert body["resource_id"] == rid  # bare ResourceMeta, not {"meta": {...}}
    assert "current_revision_id" in body
    assert "meta" not in body


def test_returns_only_revision_info_is_bare_info():
    c = _client()
    rid = _create(c)
    r = c.get(f"/widget/{rid}", params={"returns": "only-revision_info"})
    assert r.status_code == 200
    body = r.json()
    assert body["revision_id"].startswith(rid)  # bare RevisionInfo
    assert "revision_info" not in body


def test_only_revision_dash_info_is_alias_for_underscore():
    c = _client()
    rid = _create(c)
    r = c.get(f"/widget/{rid}", params={"returns": "only-revision-info"})
    assert r.status_code == 200
    assert r.json()["revision_id"].startswith(rid)


def test_revision_dash_info_alias_in_envelope():
    # `revision-info` (hyphen) is an alias for the `revision_info` envelope key
    c = _client()
    rid = _create(c)
    r = c.get(f"/widget/{rid}", params={"returns": "data,revision-info"})
    assert r.status_code == 200
    body = r.json()
    assert "data" in body and "revision_info" in body


def test_only_combined_with_other_value_is_422():
    c = _client()
    rid = _create(c)
    for q in ("only-data,meta", "only-data,only-meta", "meta,only-data"):
        assert c.get(f"/widget/{rid}", params={"returns": q}).status_code == 422, q


def test_only_unknown_section_is_422():
    c = _client()
    rid = _create(c)
    assert c.get(f"/widget/{rid}", params={"returns": "only-bogus"}).status_code == 422


def test_default_get_returns_config_changes_the_default_shape():
    c = _client(default_get_returns="only-data")
    rid = _create(c)
    r = c.get(f"/widget/{rid}")  # no ?returns= → falls back to the config default
    assert r.status_code == 200
    assert r.json() == {"name": "x"}  # bare, because default is only-data


def test_per_request_returns_overrides_config_default():
    c = _client(default_get_returns="only-data")
    rid = _create(c)
    r = c.get(f"/widget/{rid}", params={"returns": "data,meta,revision_info"})
    body = r.json()
    assert "data" in body and "meta" in body and "revision_info" in body


def test_default_is_envelope_when_unconfigured():
    c = _client()
    rid = _create(c)
    body = c.get(f"/widget/{rid}").json()
    assert "data" in body and "meta" in body and "revision_info" in body


def test_default_envelope_emits_startup_advisory():
    sp = SpecStar()
    sp.configure(default_user="t")
    sp.add_model(Widget, name="widget")
    with pytest.warns(SpecStarWarning, match="default_get_returns"):
        sp.apply(FastAPI())


def test_non_default_get_returns_no_advisory():
    sp = SpecStar()
    sp.configure(default_user="t", default_get_returns="only-data")
    sp.add_model(Widget, name="widget")
    with warnings.catch_warnings(record=True) as rec:
        warnings.simplefilter("always")
        sp.apply(FastAPI())
    assert not any("default_get_returns" in str(w.message) for w in rec)
