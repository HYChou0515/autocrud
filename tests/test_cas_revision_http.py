"""#342 follow-up B — CAS at the HTTP boundary.

- Writes return ``ETag: <revision_id>@<data_hash>`` so clients can grab it.
- ``If-Match`` on PUT/PATCH forwards to the manager's ``expected_etag`` (and
  the bare ``revision_id`` form keeps working as ``expected_revision_id``).
- ``If-None-Match: *`` on PUT becomes ``if_not_exists=True`` — atomic
  create-only at a known URL.
"""

import msgspec
from fastapi import FastAPI
from fastapi.testclient import TestClient

from specstar import SpecStar


class Widget(msgspec.Struct):
    name: str


def _client() -> TestClient:
    sp = SpecStar()
    sp.configure(default_user="t")
    sp.add_model(Widget, name="widget")
    app = FastAPI()
    sp.apply(app)
    return TestClient(app, raise_server_exceptions=False)


def test_post_returns_etag_header():
    c = _client()
    r = c.post("/widget", json={"name": "v1"})
    assert r.status_code == 200
    etag = r.headers.get("ETag")
    assert etag is not None and "@" in etag  # <revision_id>@<data_hash>


def test_put_with_if_match_etag_succeeds_and_returns_new_etag():
    # Round-trip: client reads ETag from POST, sends it back on PUT.
    c = _client()
    r1 = c.post("/widget", json={"name": "v1"})
    rid, etag = r1.json()["resource_id"], r1.headers["ETag"]
    r2 = c.put(f"/widget/{rid}", json={"name": "v2"}, headers={"If-Match": etag})
    assert r2.status_code == 200
    new_etag = r2.headers["ETag"]
    assert new_etag != etag


def test_put_with_stale_if_match_returns_412():
    c = _client()
    r1 = c.post("/widget", json={"name": "v1"})
    rid, stale = r1.json()["resource_id"], r1.headers["ETag"]
    c.put(f"/widget/{rid}", json={"name": "v2"})  # concurrent forward move
    r = c.put(f"/widget/{rid}", json={"name": "v3"}, headers={"If-Match": stale})
    assert r.status_code == 412


def test_put_with_if_none_match_star_on_existing_returns_412():
    # PUT /widget/{id} If-None-Match: * — HTTP-standard atomic create-only at
    # a known URL. Resource already exists -> 412 Precondition Failed.
    c = _client()
    r1 = c.post("/widget", json={"name": "v1"})
    rid = r1.json()["resource_id"]
    r2 = c.put(f"/widget/{rid}", json={"name": "v2"}, headers={"If-None-Match": "*"})
    assert r2.status_code == 412


def test_put_with_if_none_match_star_creates_at_known_id():
    # Same precondition on a fresh id: PUT creates the resource and returns
    # the ETag the client can use for follow-up CAS writes.
    c = _client()
    r = c.put(
        "/widget/widget:fresh-1",
        json={"name": "v1"},
        headers={"If-None-Match": "*"},
    )
    assert r.status_code == 200, r.text
    assert r.headers.get("ETag") is not None


def test_patch_with_if_match_etag_round_trip():
    # PATCH (modify) honors etag too — needed for the in-place draft edit case.
    c = _client()
    r1 = c.post("/widget", json={"name": "v1"})
    rid, etag = r1.json()["resource_id"], r1.headers["ETag"]
    r2 = c.patch(
        f"/widget/{rid}",
        json={"name": "v2"},
        headers={"If-Match": etag, "Content-Type": "application/merge-patch+json"},
    )
    assert r2.status_code == 200, r2.text
