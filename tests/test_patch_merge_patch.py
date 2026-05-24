"""Slice 2: PATCH accepts both RFC 6902 (JSON Patch) and RFC 7386 (Merge Patch).

The same endpoint disambiguates by Content-Type when explicit, else by body
shape: a JSON array is RFC 6902 ops (unchanged); a JSON object is an RFC 7386
merge patch (previously a 400). ``null`` in a merge patch deletes/optionalises
a field per RFC 7386.
"""

import msgspec
from fastapi import FastAPI
from fastapi.testclient import TestClient

from specstar import Schema, SpecStar


class Item(msgspec.Struct):
    qty: int = 0
    name: str = ""
    note: str | None = None


def _client():
    sp = SpecStar()
    sp.configure(default_user="t")
    app = FastAPI()
    sp.add_model(Schema(Item, "v1"))
    sp.apply(app)
    return TestClient(app)


def _data(c, rid):
    return c.get(f"/item/{rid}/data").json()


def test_merge_patch_partial_object_merges_and_succeeds():
    c = _client()
    rid = c.post("/item", json={"qty": 1, "name": "a"}).json()["resource_id"]
    r = c.patch(f"/item/{rid}", json={"qty": 50})
    assert r.status_code == 200
    # qty updated, name preserved (merge, not full replace)
    assert _data(c, rid) == {"qty": 50, "name": "a", "note": None}


def test_rfc6902_array_still_works():
    c = _client()
    rid = c.post("/item", json={"qty": 1, "name": "a"}).json()["resource_id"]
    r = c.patch(f"/item/{rid}", json=[{"op": "replace", "path": "/qty", "value": 9}])
    assert r.status_code == 200
    assert _data(c, rid)["qty"] == 9


def test_merge_patch_null_deletes_field():
    c = _client()
    rid = c.post("/item", json={"qty": 1, "name": "a", "note": "hi"}).json()[
        "resource_id"
    ]
    r = c.patch(f"/item/{rid}", json={"note": None})
    assert r.status_code == 200
    assert _data(c, rid)["note"] is None


def test_merge_patch_via_explicit_content_type():
    c = _client()
    rid = c.post("/item", json={"qty": 1, "name": "a"}).json()["resource_id"]
    r = c.patch(
        f"/item/{rid}",
        content=b'{"qty": 7}',
        headers={"Content-Type": "application/merge-patch+json"},
    )
    assert r.status_code == 200
    assert _data(c, rid)["qty"] == 7


def test_stray_single_6902_op_object_gives_helpful_error():
    c = _client()
    rid = c.post("/item", json={"qty": 1, "name": "a"}).json()["resource_id"]
    r = c.patch(f"/item/{rid}", json={"op": "replace", "path": "/qty", "value": 5})
    assert r.status_code == 422
    assert "array of operations" in r.json()["detail"]


def test_resource_id_in_merge_patch_object_rejected():
    c = _client()
    rid = c.post("/item", json={"qty": 1, "name": "a"}).json()["resource_id"]
    r = c.patch(f"/item/{rid}", json={"qty": 2, "resource_id": "x"})
    assert r.status_code == 422
    assert "resource_id" in r.json()["detail"]
