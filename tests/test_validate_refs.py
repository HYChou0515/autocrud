"""Tests for opt-in write-time ref validation (Item 30).

By default, you can create a resource pointing at a non-existent target
(the reference is "dangling"). When ``SpecStar(validate_refs=True)``,
``create()`` / ``update()`` / ``modify()`` reject the write if any
``Ref(...)`` (``RefType.resource_id``) points at a target that does not
exist (or is soft-deleted).

``RefType.revision_id`` refs are *not* validated — they can legitimately
carry either a revision id or a bare resource id.
"""

from typing import Annotated, Optional

import msgspec
from fastapi import FastAPI
from fastapi.testclient import TestClient

from specstar import Ref, Schema, SpecStar


class Zone(msgspec.Struct):
    name: str


class Monster(msgspec.Struct):
    name: str
    zone_id: Annotated[str, Ref("zone")]
    sibling_id: Annotated[Optional[str], Ref("monster")] = None


def _client(validate_refs: bool) -> TestClient:
    sp = SpecStar(validate_refs=validate_refs)
    sp.configure(default_user="t")
    app = FastAPI()
    sp.add_model(Schema(Zone, "v1"))
    sp.add_model(Schema(Monster, "v1"))
    sp.apply(app)
    return TestClient(app)


def test_default_off_allows_dangling_refs():
    c = _client(validate_refs=False)
    r = c.post("/monster", json={"name": "Bear", "zone_id": "zone:nonexistent"})
    assert r.status_code == 200


def test_validate_refs_rejects_unknown_target():
    c = _client(validate_refs=True)
    r = c.post("/monster", json={"name": "Bear", "zone_id": "zone:nonexistent"})
    assert r.status_code == 422
    detail = r.json()["detail"]
    if isinstance(detail, str):
        assert "not found" in detail and "zone_id" in detail
    else:
        # structured_errors mode
        assert "not found" in detail.get("message", "")


def test_validate_refs_allows_existing_target():
    c = _client(validate_refs=True)
    zid = c.post("/zone", json={"name": "Forest"}).json()["resource_id"]
    r = c.post("/monster", json={"name": "Bear", "zone_id": zid})
    assert r.status_code == 200


def test_validate_refs_on_update_too():
    c = _client(validate_refs=True)
    zid = c.post("/zone", json={"name": "Forest"}).json()["resource_id"]
    mid = c.post("/monster", json={"name": "Bear", "zone_id": zid}).json()[
        "resource_id"
    ]
    # Update with bad ref
    bad = c.put(f"/monster/{mid}", json={"name": "Bear", "zone_id": "zone:nope"})
    assert bad.status_code == 422
    # Update with good ref
    ok = c.put(f"/monster/{mid}", json={"name": "Bear2", "zone_id": zid})
    assert ok.status_code == 200


def test_validate_refs_nullable_field_can_be_null():
    """Optional ref fields with value=None should pass validation."""
    c = _client(validate_refs=True)
    zid = c.post("/zone", json={"name": "Forest"}).json()["resource_id"]
    r = c.post(
        "/monster",
        json={"name": "Bear", "zone_id": zid, "sibling_id": None},
    )
    assert r.status_code == 200
