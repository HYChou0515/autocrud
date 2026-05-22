"""Tests for POST rejecting client-supplied ``resource_id`` (Item 44).

The previous behavior silently dropped ``resource_id`` from the POST body
and let the server generate one anyway, which made clients think they'd
set a custom id when they hadn't. We now reject it loudly with HTTP 422
unless the resource Struct *actually* declares a ``resource_id`` field.
"""

import msgspec
from fastapi import FastAPI
from fastapi.testclient import TestClient

from specstar import Schema, SpecStar


class Note(msgspec.Struct):
    title: str


class HasResourceIdField(msgspec.Struct):
    """Edge case: the Struct itself declares ``resource_id`` as a data field.
    In this case the rejection should NOT trigger.
    """

    resource_id: str
    note: str


def _client_for(model: type) -> TestClient:
    sp = SpecStar()
    sp.configure(default_user="t")
    app = FastAPI()
    sp.add_model(Schema(model, "v1"))
    sp.apply(app)
    return TestClient(app)


def test_post_with_resource_id_in_body_rejected_with_422():
    client = _client_for(Note)
    resp = client.post("/note", json={"title": "a", "resource_id": "my-custom-id"})
    assert resp.status_code == 422
    assert "resource_id" in resp.json()["detail"]
    assert "server always generates" in resp.json()["detail"]


def test_post_without_resource_id_still_succeeds():
    client = _client_for(Note)
    resp = client.post("/note", json={"title": "a"})
    assert resp.status_code == 200
    # Server-generated id follows {model}:{uuid} format
    assert resp.json()["resource_id"].startswith("note:")


def test_struct_with_legitimate_resource_id_field_still_allowed():
    """If a user actually declares ``resource_id`` as a data field, the
    rejection guard should step aside and let the data flow through."""
    client = _client_for(HasResourceIdField)
    resp = client.post(
        "/has-resource-id-field",
        json={"resource_id": "user-defined-id", "note": "hi"},
    )
    assert resp.status_code == 200
