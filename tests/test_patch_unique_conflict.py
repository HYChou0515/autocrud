"""Tests for PATCH route handling of UniqueConstraintError.

Verifies that PATCH /{model}/{id} returns HTTP 409 Conflict when
a JSON Patch operation violates a Unique constraint, matching the
behavior of POST and PUT endpoints.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct

from autocrud.crud.core import AutoCRUD
from autocrud.types import Unique

# ── models ────────────────────────────────────────────────────────────


class UniqueItem(Struct):
    name: Annotated[str, Unique()]
    value: int = 0


# ── helpers ───────────────────────────────────────────────────────────


def _make_app() -> tuple[AutoCRUD, TestClient]:
    """Build an AutoCRUD + FastAPI app with a unique-constrained model."""
    crud = AutoCRUD(
        default_user="tester",
        default_now=dt.datetime.now,
    )
    crud.add_model(UniqueItem, name="uniqueitem")
    app = FastAPI()
    crud.apply(app)
    return crud, TestClient(app)


# ── tests ─────────────────────────────────────────────────────────────


class TestPatchUniqueConflict:
    """PATCH should return 409 Conflict for UniqueConstraintError."""

    def test_patch_unique_field_returns_409(self):
        """PATCH that violates unique constraint should return 409, not 400."""
        crud, client = _make_app()

        # Create two resources with different unique names
        resp_a = client.post("/uniqueitem", json={"name": "alpha", "value": 1})
        assert resp_a.status_code == 200
        resource_id_a = resp_a.json()["resource_id"]

        resp_b = client.post("/uniqueitem", json={"name": "beta", "value": 2})
        assert resp_b.status_code == 200
        resource_id_b = resp_b.json()["resource_id"]

        # PATCH resource B's name to "alpha" → should conflict
        patch_body = [{"op": "replace", "path": "/name", "value": "alpha"}]
        resp = client.patch(f"/uniqueitem/{resource_id_b}", json=patch_body)

        assert resp.status_code == 409, (
            f"Expected 409 Conflict but got {resp.status_code}: {resp.json()}"
        )
        body = resp.json()
        assert "field" in body["detail"]
        assert body["detail"]["field"] == "name"

    def test_patch_non_unique_field_ok(self):
        """PATCH that doesn't touch unique fields should succeed."""
        crud, client = _make_app()

        resp_a = client.post("/uniqueitem", json={"name": "alpha", "value": 1})
        assert resp_a.status_code == 200
        resource_id_a = resp_a.json()["resource_id"]

        # PATCH non-unique field
        patch_body = [{"op": "replace", "path": "/value", "value": 99}]
        resp = client.patch(f"/uniqueitem/{resource_id_a}", json=patch_body)

        assert resp.status_code == 200

    def test_post_unique_conflict_returns_409(self):
        """POST (create) with duplicate unique field should return 409."""
        _crud, client = _make_app()

        resp = client.post("/uniqueitem", json={"name": "alpha", "value": 1})
        assert resp.status_code == 200

        # Duplicate
        resp = client.post("/uniqueitem", json={"name": "alpha", "value": 2})
        assert resp.status_code == 409

    def test_put_unique_conflict_returns_409(self):
        """PUT (update) with duplicate unique field should return 409."""
        _crud, client = _make_app()

        resp_a = client.post("/uniqueitem", json={"name": "alpha", "value": 1})
        assert resp_a.status_code == 200

        resp_b = client.post("/uniqueitem", json={"name": "beta", "value": 2})
        assert resp_b.status_code == 200
        resource_id_b = resp_b.json()["resource_id"]

        # PUT resource B with name "alpha" → should conflict
        resp = client.put(
            f"/uniqueitem/{resource_id_b}",
            json={"name": "alpha", "value": 3},
        )
        assert resp.status_code == 409

    def test_all_write_endpoints_consistent_409(self):
        """POST, PUT, and PATCH should all return 409 for unique violations."""
        crud, client = _make_app()

        # Seed: create "alpha"
        resp = client.post("/uniqueitem", json={"name": "alpha", "value": 1})
        assert resp.status_code == 200

        # POST duplicate → 409
        resp_post = client.post("/uniqueitem", json={"name": "alpha", "value": 2})
        assert resp_post.status_code == 409

        # Create "beta" for PUT/PATCH tests
        resp_b = client.post("/uniqueitem", json={"name": "beta", "value": 3})
        assert resp_b.status_code == 200
        rid_b = resp_b.json()["resource_id"]

        # PUT duplicate → 409
        resp_put = client.put(
            f"/uniqueitem/{rid_b}",
            json={"name": "alpha", "value": 4},
        )
        assert resp_put.status_code == 409

        # PATCH duplicate → 409
        resp_patch = client.patch(
            f"/uniqueitem/{rid_b}",
            json=[{"op": "replace", "path": "/name", "value": "alpha"}],
        )
        assert resp_patch.status_code == 409
