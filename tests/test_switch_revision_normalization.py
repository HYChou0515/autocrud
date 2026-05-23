"""Tests for switch endpoint revision_id normalization + 400-with-hint behavior.

Issue 3: bare revision number used to return a bare 404 with no hint about the
expected format. We now accept either form and reject obvious garbage with a
400 + format hint.
"""

import msgspec
from fastapi import FastAPI
from fastapi.testclient import TestClient

from specstar import Schema, SpecStar


class Note(msgspec.Struct):
    text: str


def _setup():
    sp = SpecStar()
    sp.configure(default_user="tester")
    app = FastAPI()
    sp.add_model(Schema(Note, "v1"))
    sp.apply(app)
    client = TestClient(app)

    rid = client.post("/note", json={"text": "a"}).json()["resource_id"]
    client.put(f"/note/{rid}", json={"text": "b"})  # creates revision 2
    return client, rid


def test_switch_accepts_bare_revision_number():
    client, rid = _setup()
    r = client.post(f"/note/{rid}/switch/1")
    assert r.status_code == 200
    assert r.json()["current_revision_id"] == f"{rid}:1"


def test_switch_accepts_full_revision_id():
    client, rid = _setup()
    r = client.post(f"/note/{rid}/switch/{rid}:1")
    assert r.status_code == 200
    assert r.json()["current_revision_id"] == f"{rid}:1"


def test_switch_rejects_garbage_revision_id_with_400_and_hint():
    client, rid = _setup()
    r = client.post(f"/note/{rid}/switch/junk")
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "Invalid revision_id" in detail
    assert "junk" in detail
    assert rid in detail


def test_switch_unknown_bare_number_still_returns_404():
    """A bare number that's well-formed but doesn't exist should still hit
    the storage layer and return 404 (resource exists, revision doesn't)."""
    client, rid = _setup()
    r = client.post(f"/note/{rid}/switch/99")
    assert r.status_code == 404
