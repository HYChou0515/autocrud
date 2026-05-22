"""Tests for limit/offset bounds (Item 40 in FINDINGS).

``limit=0`` and ``offset<0`` used to silently produce surprising behavior
(zero rows / negative skip). Both are now rejected with HTTP 422 at the
route boundary.
"""

import msgspec
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from specstar import Schema, SpecStar


class Note(msgspec.Struct):
    title: str


@pytest.fixture
def client():
    sp = SpecStar()
    sp.configure(default_user="t")
    app = FastAPI()
    sp.add_model(Schema(Note, "v1"))
    sp.apply(app)
    c = TestClient(app)
    for i in range(3):
        c.post("/note", json={"title": f"n{i}"})
    return c


@pytest.mark.parametrize("path", ["/note", "/note/data", "/note/meta", "/note/full"])
def test_limit_zero_rejected(client, path):
    assert client.get(f"{path}?limit=0").status_code == 422


@pytest.mark.parametrize("path", ["/note", "/note/data", "/note/meta", "/note/full"])
def test_limit_negative_rejected(client, path):
    assert client.get(f"{path}?limit=-1").status_code == 422


@pytest.mark.parametrize("path", ["/note", "/note/data", "/note/meta", "/note/full"])
def test_offset_negative_rejected(client, path):
    assert client.get(f"{path}?offset=-1").status_code == 422


def test_valid_pagination_succeeds(client):
    assert client.get("/note?limit=2&offset=0").status_code == 200
    assert client.get("/note?limit=10&offset=1").status_code == 200


def test_revision_list_limit_offset_validated(client):
    rid = client.get("/note").json()[0]["meta"]["resource_id"]
    assert client.get(f"/note/{rid}/revision-list?limit=0").status_code == 422
    assert client.get(f"/note/{rid}/revision-list?offset=-1").status_code == 422
    assert client.get(f"/note/{rid}/revision-list?limit=5").status_code == 200
