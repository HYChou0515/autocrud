"""Tests for the SpecStar.forbid_unknown_fields option (Issue 2)."""

import msgspec
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from specstar import Schema, SpecStar
from specstar.types import ValidationError


class Post(msgspec.Struct):
    title: str
    body: str


def _make_app(*, forbid_unknown_fields: bool) -> TestClient:
    sp = SpecStar(forbid_unknown_fields=forbid_unknown_fields)
    sp.configure(default_user="tester")
    app = FastAPI()
    sp.add_model(Schema(Post, "v1"))
    sp.apply(app)
    return TestClient(app)


def test_default_off_unknown_fields_are_dropped():
    client = _make_app(forbid_unknown_fields=False)
    r = client.post("/post", json={"title": "t", "body": "b", "ghost": "X"})
    assert r.status_code == 200
    rid = r.json()["resource_id"]
    stored = client.get(f"/post/{rid}").json()["data"]
    assert stored == {"title": "t", "body": "b"}


def test_strict_unknown_fields_are_rejected_with_422():
    client = _make_app(forbid_unknown_fields=True)
    r = client.post("/post", json={"title": "t", "body": "b", "ghost": "X"})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "ghost" in detail
    assert "Post" in detail


def test_strict_clean_payload_still_succeeds():
    client = _make_app(forbid_unknown_fields=True)
    r = client.post("/post", json={"title": "t", "body": "b"})
    assert r.status_code == 200


def test_strict_put_full_replace_rejects_unknown_fields():
    client = _make_app(forbid_unknown_fields=True)
    rid = client.post("/post", json={"title": "t", "body": "b"}).json()["resource_id"]
    r = client.put(
        f"/post/{rid}",
        json={"title": "t2", "body": "b2", "rogue": "Y"},
    )
    assert r.status_code == 422
    assert "rogue" in r.json()["detail"]


def test_configure_toggles_the_flag():
    sp = SpecStar()
    assert sp.forbid_unknown_fields is False
    sp.configure(forbid_unknown_fields=True)
    assert sp.forbid_unknown_fields is True


def test_resource_manager_direct_call_with_dict_is_validated():
    sp = SpecStar(forbid_unknown_fields=True)
    sp.configure(default_user="tester")
    sp.add_model(Schema(Post, "v1"))
    rm = sp.get_resource_manager(Post)
    with pytest.raises(ValidationError):
        rm.create({"title": "t", "body": "b", "ghost": "X"})
