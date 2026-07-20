"""Tests for optimistic concurrency (If-Match / expected_revision_id, Item 34).

Two equivalent ways for a client to assert "the resource is currently at
*this* revision, update only if so":

* ``If-Match: <revision_id>`` header (HTTP-standard ETag-style)
* ``?expected_revision_id=<revision_id>`` query param

Mismatch → ``412 Precondition Failed`` with structured detail naming
``expected_revision_id`` and ``actual_revision_id`` so the client can
fetch + reapply.
"""

import msgspec
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from specstar import Schema, SpecStar


class Note(msgspec.Struct):
    title: str


@pytest.fixture
def client_and_resource():
    sp = SpecStar()
    sp.configure(default_user="t")
    app = FastAPI()
    sp.add_model(Schema(Note, "v1"))
    sp.apply(app)
    c = TestClient(app)
    info = c.post("/note", json={"title": "a"}).json()
    return c, info["resource_id"], info["revision_id"]


# ── PUT --------------------------------------------------------------------


def test_put_with_matching_expected_revision_id_succeeds(client_and_resource):
    c, rid, rev1 = client_and_resource
    r = c.put(f"/note/{rid}?expected_revision_id={rev1}", json={"title": "b"})
    assert r.status_code == 200


def test_put_with_stale_expected_revision_id_returns_412(client_and_resource):
    c, rid, rev1 = client_and_resource
    c.put(f"/note/{rid}", json={"title": "b"})  # rev2 is now current
    r = c.put(f"/note/{rid}?expected_revision_id={rev1}", json={"title": "c"})
    assert r.status_code == 412
    detail = r.json()["detail"]
    assert detail["code"] == "PRECONDITION_FAILED"
    assert detail["expected_revision_id"] == rev1
    assert detail["actual_revision_id"].endswith(":2")


def test_put_with_matching_if_match_header_succeeds(client_and_resource):
    c, rid, rev1 = client_and_resource
    r = c.put(f"/note/{rid}", json={"title": "b"}, headers={"If-Match": rev1})
    assert r.status_code == 200


def test_put_accepts_quoted_if_match_header(client_and_resource):
    """Standard HTTP ETag clients wrap the value in double quotes."""
    c, rid, rev1 = client_and_resource
    r = c.put(
        f"/note/{rid}",
        json={"title": "b"},
        headers={"If-Match": f'"{rev1}"'},
    )
    assert r.status_code == 200


def test_put_with_stale_if_match_header_returns_412(client_and_resource):
    c, rid, rev1 = client_and_resource
    c.put(f"/note/{rid}", json={"title": "b"})
    r = c.put(f"/note/{rid}", json={"title": "c"}, headers={"If-Match": rev1})
    assert r.status_code == 412


def test_put_conflicting_header_and_query_param_returns_400(client_and_resource):
    c, rid, rev1 = client_and_resource
    r = c.put(
        f"/note/{rid}?expected_revision_id={rev1}",
        json={"title": "b"},
        headers={"If-Match": "different-id"},
    )
    assert r.status_code == 400


# ── PATCH -----------------------------------------------------------------


def test_patch_with_matching_expected_revision_id_succeeds(client_and_resource):
    c, rid, rev1 = client_and_resource
    r = c.patch(
        f"/note/{rid}?expected_revision_id={rev1}",
        json=[{"op": "replace", "path": "/title", "value": "b"}],
    )
    assert r.status_code == 200


def test_patch_with_stale_expected_revision_id_returns_412(client_and_resource):
    c, rid, rev1 = client_and_resource
    c.put(f"/note/{rid}", json={"title": "b"})
    r = c.patch(
        f"/note/{rid}?expected_revision_id={rev1}",
        json=[{"op": "replace", "path": "/title", "value": "c"}],
    )
    assert r.status_code == 412


# ── No precondition supplied still works ----------------------------------


def test_put_without_precondition_still_succeeds(client_and_resource):
    c, rid, _ = client_and_resource
    r = c.put(f"/note/{rid}", json={"title": "b"})
    assert r.status_code == 200
