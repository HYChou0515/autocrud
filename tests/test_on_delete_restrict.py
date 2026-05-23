"""Tests for ``OnDelete.restrict`` (Item 31).

``restrict`` refuses to delete a referenced resource while any other
resource still references it. Compared to:

* ``dangling`` (default) — delete succeeds, references become dangling.
* ``cascade`` — delete the referencing resources too.
* ``set_null`` — null out the referencing fields.

``restrict`` is the safest option for "I want the caller to clean up
first." It raises :class:`ResourceConflictError` (HTTP 409) before the
delete is committed.
"""

from typing import Annotated

import msgspec
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from specstar import OnDelete, Ref, Schema, SpecStar


class Zone(msgspec.Struct):
    name: str


class Monster(msgspec.Struct):
    name: str
    zone_id: Annotated[str, Ref("zone", on_delete=OnDelete.restrict)]


@pytest.fixture
def client():
    sp = SpecStar()
    sp.configure(default_user="t")
    app = FastAPI()
    sp.add_model(Schema(Zone, "v1"))
    sp.add_model(Schema(Monster, "v1"))
    sp.apply(app)
    return TestClient(app)


def test_delete_unreferenced_target_succeeds(client):
    zid = client.post("/zone", json={"name": "empty"}).json()["resource_id"]
    assert client.delete(f"/zone/{zid}").status_code == 200


def test_delete_blocked_while_referenced(client):
    zid = client.post("/zone", json={"name": "z"}).json()["resource_id"]
    client.post("/monster", json={"name": "m", "zone_id": zid})

    resp = client.delete(f"/zone/{zid}")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "still referenced" in detail or "RESTRICT" in detail


def test_delete_succeeds_after_references_removed(client):
    zid = client.post("/zone", json={"name": "z"}).json()["resource_id"]
    mid = client.post("/monster", json={"name": "m", "zone_id": zid}).json()[
        "resource_id"
    ]

    # Blocked initially
    assert client.delete(f"/zone/{zid}").status_code == 409

    # Remove the referencer, then the delete passes
    assert client.delete(f"/monster/{mid}").status_code == 200
    assert client.delete(f"/zone/{zid}").status_code == 200


def test_restrict_blocker_message_names_the_source(client):
    zid = client.post("/zone", json={"name": "z"}).json()["resource_id"]
    mid = client.post("/monster", json={"name": "m", "zone_id": zid}).json()[
        "resource_id"
    ]

    resp = client.delete(f"/zone/{zid}")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert "monster.zone_id" in detail
    assert mid in detail
