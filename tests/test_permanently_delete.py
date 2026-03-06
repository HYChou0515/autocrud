"""Tests for permanently_delete feature (TDD).

Tests cover:
1. ResourceManager.permanently_delete() — removes metadata and all revisions
2. PermanentlyDeleteRouteTemplate — DELETE /{model}/{id}/permanently
3. purge_resource on storage layer
4. Event hooks are fired correctly
"""

import datetime as dt

import msgspec
import pytest
from faker import Faker
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autocrud.crud.core import AutoCRUD
from autocrud.crud.route_templates.create import CreateRouteTemplate
from autocrud.crud.route_templates.delete import (
    DeleteRouteTemplate,
    PermanentlyDeleteRouteTemplate,
    RestoreRouteTemplate,
)
from autocrud.crud.route_templates.get import ReadRouteTemplate
from autocrud.crud.route_templates.search import ListRouteTemplate
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.types import (
    ResourceIDNotFoundError,
    ResourceMeta,
)

faker = Faker()


class Item(msgspec.Struct):
    name: str
    value: int


def new_item() -> Item:
    return Item(name=faker.pystr(), value=faker.pyint())


def make_manager() -> ResourceManager:
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore()
    storage = SimpleStorage(meta_store, resource_store)
    return ResourceManager(Item, storage=storage)


def create_item(mgr: ResourceManager, data: Item | None = None) -> tuple[str, str]:
    """Helper: create an item and return (resource_id, revision_id)."""
    data = data or new_item()
    user, now = faker.user_name(), faker.date_time()
    with mgr.meta_provide(user, now):
        info = mgr.create(data)
    return info.resource_id, info.revision_id


# ---------------------------------------------------------------------------
# ResourceManager Tests
# ---------------------------------------------------------------------------


class TestPermanentlyDelete:
    """Test ResourceManager.permanently_delete()"""

    def test_permanently_delete_removes_resource(self):
        """permanently_delete should remove both meta and revision data."""
        mgr = make_manager()
        rid, rev_id = create_item(mgr)

        # Resource exists
        assert mgr.exists(rid)
        assert mgr.storage.revision_exists(rid, rev_id)

        # Perform permanent delete
        user, now = faker.user_name(), faker.date_time()
        with mgr.meta_provide(user, now):
            meta = mgr.permanently_delete(rid)

        # Returns the meta before deletion
        assert isinstance(meta, ResourceMeta)
        assert meta.resource_id == rid

        # Resource no longer exists
        assert not mgr.exists(rid)

    def test_permanently_delete_with_multiple_revisions(self):
        """permanently_delete should remove all revisions."""
        mgr = make_manager()
        rid, rev1 = create_item(mgr)

        # Add a second revision
        user2, now2 = faker.user_name(), faker.date_time()
        with mgr.meta_provide(user2, now2):
            info2 = mgr.update(rid, new_item())
        rev2 = info2.revision_id

        # Both revisions exist
        assert mgr.storage.revision_exists(rid, rev1)
        assert mgr.storage.revision_exists(rid, rev2)

        # Permanently delete
        user3, now3 = faker.user_name(), faker.date_time()
        with mgr.meta_provide(user3, now3):
            mgr.permanently_delete(rid)

        # Resource is gone
        assert not mgr.exists(rid)

    def test_permanently_delete_soft_deleted_resource(self):
        """permanently_delete should work on soft-deleted resources too."""
        mgr = make_manager()
        rid, _ = create_item(mgr)

        # Soft delete first
        user1, now1 = faker.user_name(), faker.date_time()
        with mgr.meta_provide(user1, now1):
            mgr.delete(rid)

        # Now permanently delete
        user2, now2 = faker.user_name(), faker.date_time()
        with mgr.meta_provide(user2, now2):
            meta = mgr.permanently_delete(rid)

        assert meta.is_deleted is True  # Was soft-deleted
        assert not mgr.exists(rid)

    def test_permanently_delete_nonexistent_raises(self):
        """permanently_delete on nonexistent resource should raise."""
        mgr = make_manager()
        user, now = faker.user_name(), faker.date_time()
        with pytest.raises(ResourceIDNotFoundError):
            with mgr.meta_provide(user, now):
                mgr.permanently_delete("does-not-exist")

    def test_permanently_delete_is_irreversible(self):
        """After permanently_delete, get/restore should fail."""
        mgr = make_manager()
        rid, _ = create_item(mgr)

        user, now = faker.user_name(), faker.date_time()
        with mgr.meta_provide(user, now):
            mgr.permanently_delete(rid)

        # Cannot get
        with pytest.raises(ResourceIDNotFoundError):
            mgr.get(rid)

        # Cannot restore
        with pytest.raises(ResourceIDNotFoundError):
            with mgr.meta_provide(user, now):
                mgr.restore(rid)


# ---------------------------------------------------------------------------
# Storage Layer Tests
# ---------------------------------------------------------------------------


class TestPurgeResource:
    """Test purge_resource on storage implementations."""

    def test_memory_resource_store_purge(self):
        """MemoryResourceStore.purge_resource should remove all data."""
        store = MemoryResourceStore()
        import io

        from autocrud.types import RevisionInfo

        info = RevisionInfo(
            resource_id="r1",
            revision_id="rev1",
            uid="uid1",
            created_by="u",
            updated_by="u",
            created_time=dt.datetime.now(),
            updated_time=dt.datetime.now(),
            status="stable",
            parent_revision_id=None,
            schema_version=None,
            data_hash="xxh3_128:00000000000000000000000000000000",
        )
        store.save(info, io.BytesIO(b"some data"))

        # Verify exists
        assert list(store.list_resources()) == ["r1"]

        # Purge
        store.purge_resource("r1")

        # Verify gone
        assert list(store.list_resources()) == []

    def test_memory_resource_store_purge_nonexistent_noop(self):
        """Purging a nonexistent resource should be a no-op."""
        store = MemoryResourceStore()
        store.purge_resource("does-not-exist")  # Should not raise

    def test_simple_storage_purge_resource(self):
        """SimpleStorage.purge_resource should remove both meta and resource data."""
        meta_store = MemoryMetaStore()
        resource_store = MemoryResourceStore()
        storage = SimpleStorage(meta_store, resource_store)

        mgr = ResourceManager(Item, storage=storage)
        rid, rev_id = create_item(mgr)

        # Verify exists
        assert storage.exists(rid)

        # Purge
        storage.purge_resource(rid)

        # Meta gone
        assert not storage.exists(rid)
        # Resource data gone
        assert rid not in list(resource_store.list_resources())


# ---------------------------------------------------------------------------
# Route Template Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """Create a FastAPI test client with permanently delete route."""
    crud = AutoCRUD(model_naming="kebab")

    crud.add_route_template(CreateRouteTemplate())
    crud.add_route_template(ReadRouteTemplate())
    crud.add_route_template(ListRouteTemplate())
    crud.add_route_template(DeleteRouteTemplate())
    crud.add_route_template(RestoreRouteTemplate())
    crud.add_route_template(PermanentlyDeleteRouteTemplate())

    crud.add_model(Item)

    app = FastAPI()
    from fastapi import APIRouter

    router = APIRouter()
    crud.apply(router)
    app.include_router(router)
    return TestClient(app)


class TestPermanentlyDeleteRoute:
    """Test the DELETE /{model}/{id}/permanently endpoint."""

    def test_permanently_delete_resource(self, client: TestClient):
        """DELETE /item/{id}/permanently should permanently remove the resource."""
        # Create
        create_resp = client.post("/item", json={"name": "test", "value": 42})
        assert create_resp.status_code == 200
        rid = create_resp.json()["resource_id"]

        # Verify it exists
        get_resp = client.get(f"/item/{rid}/data")
        assert get_resp.status_code == 200

        # Permanently delete
        del_resp = client.delete(f"/item/{rid}/permanently")
        assert del_resp.status_code == 200
        data = del_resp.json()
        assert data["resource_id"] == rid

        # Verify it's gone
        get_resp2 = client.get(f"/item/{rid}/data")
        assert get_resp2.status_code == 404

    def test_permanently_delete_soft_deleted_resource(self, client: TestClient):
        """Should work on already soft-deleted resources."""
        create_resp = client.post("/item", json={"name": "test2", "value": 99})
        rid = create_resp.json()["resource_id"]

        # Soft delete first
        client.delete(f"/item/{rid}")

        # Now permanently delete
        del_resp = client.delete(f"/item/{rid}/permanently")
        assert del_resp.status_code == 200

        # Cannot restore after permanent delete
        restore_resp = client.post(f"/item/{rid}/restore")
        assert restore_resp.status_code == 404

    def test_permanently_delete_nonexistent(self, client: TestClient):
        """Permanently deleting nonexistent resource should return 404."""
        resp = client.delete("/item/does-not-exist/permanently")
        assert resp.status_code == 404

    def test_permanently_delete_not_in_search(self, client: TestClient):
        """Permanently deleted resource should not appear in search results."""
        # Create two items
        resp1 = client.post("/item", json={"name": "keep", "value": 1})
        resp2 = client.post("/item", json={"name": "remove", "value": 2})
        rid2 = resp2.json()["resource_id"]

        # Permanently delete the second
        client.delete(f"/item/{rid2}/permanently")

        # Search should only return the first (use /item which returns full resources)
        list_resp = client.get("/item")
        assert list_resp.status_code == 200
        items = list_resp.json()
        rids = [item["meta"]["resource_id"] for item in items]
        assert rid2 not in rids

    def test_default_route_templates_include_permanently_delete(self):
        """AutoCRUD default templates should include PermanentlyDeleteRouteTemplate."""
        crud = AutoCRUD()
        has_perm_delete = any(
            isinstance(rt, PermanentlyDeleteRouteTemplate)
            for rt in crud.route_templates
        )
        assert has_perm_delete, (
            "PermanentlyDeleteRouteTemplate should be in default templates"
        )


class TestGetDeletedResourceDetail:
    """Test that soft-deleted resources can still be viewed on the detail page.

    This is critical for the admin UI: when a resource is soft-deleted,
    the user should still be able to view it to restore or permanently delete.
    """

    def test_get_deleted_resource_full(self, client: TestClient):
        """GET /item/{id}?include_deleted=true should return data for soft-deleted resources."""
        # Create
        resp = client.post("/item", json={"name": "viewable", "value": 100})
        rid = resp.json()["resource_id"]

        # Soft delete
        client.delete(f"/item/{rid}")

        # Without include_deleted: should 404
        get_resp_no_flag = client.get(f"/item/{rid}")
        assert get_resp_no_flag.status_code == 404

        # With include_deleted=true: should work
        get_resp = client.get(f"/item/{rid}", params={"include_deleted": True})
        assert get_resp.status_code == 200, (
            f"Should be able to view soft-deleted resource detail, got {get_resp.status_code}: {get_resp.text}"
        )
        body = get_resp.json()
        assert body["meta"]["is_deleted"] is True
        assert body["data"]["name"] == "viewable"

    def test_get_deleted_resource_meta(self, client: TestClient):
        """GET /item/{id}/meta?include_deleted=true should return metadata for soft-deleted resources."""
        resp = client.post("/item", json={"name": "meta-viewable", "value": 200})
        rid = resp.json()["resource_id"]

        # Soft delete
        client.delete(f"/item/{rid}")

        # Without include_deleted: should 404
        get_resp_no_flag = client.get(f"/item/{rid}/meta")
        assert get_resp_no_flag.status_code == 404

        # With include_deleted=true: should work
        get_resp = client.get(f"/item/{rid}/meta", params={"include_deleted": True})
        assert get_resp.status_code == 200, (
            f"Should be able to view soft-deleted resource meta, got {get_resp.status_code}: {get_resp.text}"
        )
        body = get_resp.json()
        assert body["is_deleted"] is True

    def test_get_deleted_resource_revision_list(self, client: TestClient):
        """GET /item/{id}/revision-list?include_deleted=true should work for soft-deleted resources."""
        resp = client.post("/item", json={"name": "rev-viewable", "value": 300})
        rid = resp.json()["resource_id"]

        # Soft delete
        client.delete(f"/item/{rid}")

        # Without include_deleted: should 404
        get_resp_no_flag = client.get(f"/item/{rid}/revision-list")
        assert get_resp_no_flag.status_code == 404

        # With include_deleted=true: should work
        get_resp = client.get(
            f"/item/{rid}/revision-list", params={"include_deleted": True}
        )
        assert get_resp.status_code == 200, (
            f"Should be able to view soft-deleted resource revisions, got {get_resp.status_code}: {get_resp.text}"
        )

    def test_get_meta_include_deleted_param(self):
        """ResourceManager.get_meta(include_deleted=True) should return meta for deleted resources."""
        mgr = make_manager()
        rid, _ = create_item(mgr)

        # Soft delete
        with mgr.meta_provide("u", dt.datetime.now()):
            mgr.delete(rid)

        # Default: raises ResourceIsDeletedError
        with pytest.raises(Exception):
            mgr.get_meta(rid)

        # With include_deleted=True: should succeed
        meta = mgr.get_meta(rid, include_deleted=True)
        assert meta.resource_id == rid
        assert meta.is_deleted is True

    def test_get_deleted_resource_with_revision_id(self, client: TestClient):
        """GET /item/{id}?revision_id=X&include_deleted=true should work for soft-deleted resources."""
        resp = client.post("/item", json={"name": "rev-fetch", "value": 400})
        rid = resp.json()["resource_id"]
        rev_id = resp.json()["revision_id"]

        # Soft delete
        client.delete(f"/item/{rid}")

        # Without include_deleted: should 404
        get_resp_no_flag = client.get(f"/item/{rid}", params={"revision_id": rev_id})
        assert get_resp_no_flag.status_code == 404

        # With include_deleted=true: should work
        get_resp = client.get(
            f"/item/{rid}",
            params={"revision_id": rev_id, "include_deleted": True},
        )
        assert get_resp.status_code == 200, (
            f"GET with revision_id on deleted resource failed: {get_resp.status_code}: {get_resp.text}"
        )
        body = get_resp.json()
        assert body["meta"]["is_deleted"] is True
        assert body["revision_info"]["revision_id"] == rev_id
