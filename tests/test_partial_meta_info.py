"""Tests for partial prefix routing support (meta/info/data)."""

import msgspec
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from autocrud.crud.core import AutoCRUD
from autocrud.crud.route_templates.basic import (
    PartialFieldsSpec,
    classify_partial_fields,
    filter_struct_partial,
)
from autocrud.crud.route_templates.create import CreateRouteTemplate
from autocrud.crud.route_templates.get import ReadRouteTemplate
from autocrud.crud.route_templates.search import ListRouteTemplate
from autocrud.crud.route_templates.update import UpdateRouteTemplate
from autocrud.types import ResourceMeta

# ---------------------------------------------------------------------------
# Test model
# ---------------------------------------------------------------------------


class Item(msgspec.Struct):
    name: str
    description: str
    price: int


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def autocrud():
    crud = AutoCRUD(model_naming="kebab")
    crud.add_route_template(CreateRouteTemplate())
    crud.add_route_template(ReadRouteTemplate())
    crud.add_route_template(UpdateRouteTemplate())
    crud.add_route_template(ListRouteTemplate())
    crud.add_model(Item)
    return crud


@pytest.fixture
def client(autocrud):
    app = FastAPI()
    router = APIRouter()
    autocrud.apply(router)
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def resource_id(client):
    """Create one Item and return its resource_id."""
    resp = client.post(
        "/item", json={"name": "Widget", "description": "A fine widget", "price": 42}
    )
    assert resp.status_code == 200
    return resp.json()["resource_id"]


# ===========================================================================
# Unit tests: classify_partial_fields
# ===========================================================================


class TestClassifyPartialFields:
    def test_none_input(self):
        spec = classify_partial_fields(None)
        assert spec == PartialFieldsSpec(None, None, None)

    def test_empty_list(self):
        spec = classify_partial_fields([])
        assert spec == PartialFieldsSpec(None, None, None)

    def test_unprefixed_defaults_to_data(self):
        spec = classify_partial_fields(["/name", "/email"])
        assert spec.data_fields == ["/name", "/email"]
        assert spec.meta_fields is None
        assert spec.info_fields is None

    def test_meta_prefix(self):
        spec = classify_partial_fields(["/meta/resource_id", "/meta/created_time"])
        assert spec.meta_fields == ["/resource_id", "/created_time"]
        assert spec.data_fields is None
        assert spec.info_fields is None

    def test_info_prefix(self):
        spec = classify_partial_fields(["/info/revision_id", "/info/status"])
        assert spec.info_fields == ["/revision_id", "/status"]
        assert spec.data_fields is None
        assert spec.meta_fields is None

    def test_data_prefix(self):
        spec = classify_partial_fields(["/data/name", "/data/price"])
        assert spec.data_fields == ["/name", "/price"]
        assert spec.meta_fields is None
        assert spec.info_fields is None

    def test_mixed_prefixes(self):
        spec = classify_partial_fields(
            ["/meta/resource_id", "/info/status", "/data/name", "/price"]
        )
        assert spec.meta_fields == ["/resource_id"]
        assert spec.info_fields == ["/status"]
        assert spec.data_fields == ["/name", "/price"]

    def test_default_category_meta(self):
        spec = classify_partial_fields(
            ["/resource_id", "/created_time"], default_category="meta"
        )
        assert spec.meta_fields == ["/resource_id", "/created_time"]
        assert spec.data_fields is None

    def test_default_category_info(self):
        spec = classify_partial_fields(
            ["/revision_id", "/status"], default_category="info"
        )
        assert spec.info_fields == ["/revision_id", "/status"]
        assert spec.data_fields is None

    def test_no_leading_slash(self):
        """Fields without leading / should still be handled."""
        spec = classify_partial_fields(["name", "meta/resource_id"])
        assert spec.data_fields == ["/name"]
        assert spec.meta_fields == ["/resource_id"]

    def test_explicit_data_prefix_with_meta_default(self):
        """data/ prefix overrides the default_category."""
        spec = classify_partial_fields(
            ["/data/name", "/resource_id"], default_category="meta"
        )
        assert spec.data_fields == ["/name"]
        assert spec.meta_fields == ["/resource_id"]


# ===========================================================================
# Unit tests: filter_struct_partial
# ===========================================================================


class TestFilterStructPartial:
    def test_filter_resource_meta_single_field(self):
        meta = ResourceMeta(
            current_revision_id="rev1",
            resource_id="r1",
            total_revision_count=1,
            created_time=msgspec.UNSET,
            updated_time=msgspec.UNSET,
            created_by="user",
            updated_by="user",
        )
        result = filter_struct_partial(meta, ["/resource_id"])
        assert result.resource_id == "r1"
        # Partial type only contains requested fields
        assert not hasattr(result, "current_revision_id")

    def test_filter_resource_meta_multiple_fields(self):
        meta = ResourceMeta(
            current_revision_id="rev1",
            resource_id="r1",
            total_revision_count=3,
            created_time=msgspec.UNSET,
            updated_time=msgspec.UNSET,
            created_by="admin",
            updated_by="admin",
        )
        result = filter_struct_partial(meta, ["/resource_id", "/created_by"])
        assert result.resource_id == "r1"
        assert result.created_by == "admin"
        assert not hasattr(result, "current_revision_id")

    def test_filter_item_struct(self):
        item = Item(name="Widget", description="A fine widget", price=42)
        result = filter_struct_partial(item, ["/name"])
        assert result.name == "Widget"
        assert (
            not hasattr(result, "description")
            or getattr(result, "description", msgspec.UNSET) is msgspec.UNSET
        )


# ===========================================================================
# Integration tests: GET /{model}/{id}/meta with partial
# ===========================================================================


class TestGetMetaPartial:
    def test_meta_partial_single_field(self, client, resource_id):
        resp = client.get(
            f"/item/{resource_id}/meta", params={"partial": "/resource_id"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "resource_id" in data
        assert "created_time" not in data

    def test_meta_partial_with_prefix(self, client, resource_id):
        """Explicit /meta/ prefix should also work on the /meta endpoint."""
        resp = client.get(
            f"/item/{resource_id}/meta", params={"partial": "/meta/resource_id"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "resource_id" in data
        assert "created_time" not in data

    def test_meta_partial_multiple_fields(self, client, resource_id):
        resp = client.get(
            f"/item/{resource_id}/meta",
            params={"partial": ["/resource_id", "/created_by"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "resource_id" in data
        assert "created_by" in data
        assert "updated_time" not in data

    def test_meta_no_partial_returns_full(self, client, resource_id):
        resp = client.get(f"/item/{resource_id}/meta")
        assert resp.status_code == 200
        data = resp.json()
        assert "resource_id" in data
        assert "created_time" in data
        assert "current_revision_id" in data

    def test_meta_partial_brackets(self, client, resource_id):
        resp = client.get(
            f"/item/{resource_id}/meta",
            params={"partial[]": ["/resource_id", "/is_deleted"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "resource_id" in data
        assert "is_deleted" in data
        assert "created_time" not in data


# ===========================================================================
# Integration tests: GET /{model}/{id}/revision-info with partial
# ===========================================================================


class TestGetRevisionInfoPartial:
    def test_revision_info_partial_single(self, client, resource_id):
        resp = client.get(
            f"/item/{resource_id}/revision-info",
            params={"partial": "/revision_id"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "revision_id" in data
        assert "uid" not in data

    def test_revision_info_partial_two_fields(self, client, resource_id):
        resp = client.get(
            f"/item/{resource_id}/revision-info",
            params={"partial": ["/revision_id", "/status"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "revision_id" in data
        assert "status" in data
        assert "uid" not in data

    def test_revision_info_partial_with_info_prefix(self, client, resource_id):
        resp = client.get(
            f"/item/{resource_id}/revision-info",
            params={"partial": "/info/revision_id"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "revision_id" in data
        assert "uid" not in data

    def test_revision_info_no_partial(self, client, resource_id):
        resp = client.get(f"/item/{resource_id}/revision-info")
        assert resp.status_code == 200
        data = resp.json()
        assert "revision_id" in data
        assert "uid" in data
        assert "status" in data

    def test_revision_info_partial_brackets(self, client, resource_id):
        resp = client.get(
            f"/item/{resource_id}/revision-info",
            params={"partial[]": ["/revision_id", "/status"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "revision_id" in data
        assert "status" in data
        assert "uid" not in data


# ===========================================================================
# Integration tests: GET /{model}/{id}/full with prefix partial
# ===========================================================================


class TestGetFullPartial:
    def test_full_unprefixed_is_data_partial(self, client, resource_id):
        """Unprefixed partial on /full should filter data (backward compat)."""
        resp = client.get(f"/item/{resource_id}/full", params={"partial": "/name"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == {"name": "Widget"}
        # meta and revision_info should be returned in full
        assert "resource_id" in body["meta"]
        assert "revision_id" in body["revision_info"]

    def test_full_meta_prefix(self, client, resource_id):
        resp = client.get(
            f"/item/{resource_id}/full",
            params={"partial": "/meta/resource_id"},
        )
        assert resp.status_code == 200
        body = resp.json()
        # data should be full (no data partial)
        assert body["data"]["name"] == "Widget"
        assert body["data"]["price"] == 42
        # meta should be filtered
        assert "resource_id" in body["meta"]
        assert "created_time" not in body["meta"]

    def test_full_info_prefix(self, client, resource_id):
        resp = client.get(
            f"/item/{resource_id}/full",
            params={"partial": "/info/status"},
        )
        assert resp.status_code == 200
        body = resp.json()
        # data should be full
        assert body["data"]["name"] == "Widget"
        # revision_info should be filtered
        assert "status" in body["revision_info"]
        assert "uid" not in body["revision_info"]

    def test_full_mixed_prefixes(self, client, resource_id):
        resp = client.get(
            f"/item/{resource_id}/full",
            params={
                "partial": [
                    "/meta/resource_id",
                    "/info/status",
                    "/data/name",
                ]
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == {"name": "Widget"}
        assert "resource_id" in body["meta"]
        assert "created_time" not in body["meta"]
        assert "status" in body["revision_info"]
        assert "uid" not in body["revision_info"]

    def test_full_partial_brackets_mixed(self, client, resource_id):
        resp = client.get(
            f"/item/{resource_id}/full",
            params={
                "partial[]": [
                    "/meta/resource_id",
                    "/info/revision_id",
                    "/data/name",
                ]
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == {"name": "Widget"}
        assert "resource_id" in body["meta"]
        assert "created_time" not in body["meta"]
        assert "revision_id" in body["revision_info"]
        assert "uid" not in body["revision_info"]


# ===========================================================================
# Integration tests: GET /{model}/{id}/revision-list with partial
# ===========================================================================


class TestGetRevisionListPartial:
    def test_revision_list_partial_info(self, client, resource_id):
        resp = client.get(
            f"/item/{resource_id}/revision-list",
            params={"partial": ["/revision_id", "/status"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        # meta should be full (no meta partial)
        assert "resource_id" in body["meta"]
        assert "created_time" in body["meta"]
        # revisions should be filtered
        for rev in body["revisions"]:
            assert "revision_id" in rev
            assert "status" in rev
            assert "uid" not in rev

    def test_revision_list_partial_meta(self, client, resource_id):
        resp = client.get(
            f"/item/{resource_id}/revision-list",
            params={"partial": "/meta/resource_id"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "resource_id" in body["meta"]
        assert "created_time" not in body["meta"]
        # revisions should be full (no info partial)
        for rev in body["revisions"]:
            assert "uid" in rev
            assert "revision_id" in rev

    def test_revision_list_partial_mixed(self, client, resource_id):
        resp = client.get(
            f"/item/{resource_id}/revision-list",
            params={"partial": ["/meta/resource_id", "/info/revision_id"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "resource_id" in body["meta"]
        assert "created_time" not in body["meta"]
        for rev in body["revisions"]:
            assert "revision_id" in rev
            assert "uid" not in rev

    def test_revision_list_no_partial(self, client, resource_id):
        resp = client.get(f"/item/{resource_id}/revision-list")
        assert resp.status_code == 200
        body = resp.json()
        assert "resource_id" in body["meta"]
        assert "created_time" in body["meta"]
        for rev in body["revisions"]:
            assert "uid" in rev
            assert "revision_id" in rev
            assert "status" in rev


# ===========================================================================
# Integration tests: search endpoints with partial
# ===========================================================================


class TestSearchMetaPartial:
    def test_list_meta_partial(self, client, resource_id):
        resp = client.get("/item/meta", params={"partial": "/resource_id"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        for item in data:
            assert "resource_id" in item
            assert "created_time" not in item

    def test_list_meta_partial_with_prefix(self, client, resource_id):
        resp = client.get("/item/meta", params={"partial": "/meta/resource_id"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        for item in data:
            assert "resource_id" in item
            assert "created_time" not in item


class TestSearchRevisionInfoPartial:
    def test_list_revision_info_partial(self, client, resource_id):
        resp = client.get(
            "/item/revision-info",
            params={"partial": ["/revision_id", "/status"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        for item in data:
            assert "revision_id" in item
            assert "status" in item
            assert "uid" not in item

    def test_list_revision_info_partial_with_prefix(self, client, resource_id):
        resp = client.get(
            "/item/revision-info",
            params={"partial": "/info/revision_id"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        for item in data:
            assert "revision_id" in item
            assert "uid" not in item


class TestSearchFullPartial:
    def test_list_full_unprefixed_data_partial(self, client, resource_id):
        resp = client.get("/item/full", params={"partial": "/name"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        for item in data:
            assert item["data"] == {"name": "Widget"}
            # meta and revision_info should be full
            assert "resource_id" in item["meta"]
            assert "revision_id" in item["revision_info"]

    def test_list_full_mixed_prefixes(self, client, resource_id):
        resp = client.get(
            "/item/full",
            params={"partial": ["/meta/resource_id", "/data/name"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        for item in data:
            assert item["data"] == {"name": "Widget"}
            assert "resource_id" in item["meta"]
            assert "created_time" not in item["meta"]

    def test_list_full_info_prefix(self, client, resource_id):
        resp = client.get(
            "/item/full",
            params={"partial": "/info/status"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        for item in data:
            # data should be full
            assert "name" in item["data"]
            assert "price" in item["data"]
            # revision_info should be filtered
            assert "status" in item["revision_info"]
            assert "uid" not in item["revision_info"]

    def test_list_data_partial_on_data_endpoint(self, client, resource_id):
        """The /data endpoint should still work with unprefixed partial."""
        resp = client.get("/item/data", params={"partial": "/name"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        for item in data:
            assert "name" in item
            assert "price" not in item
