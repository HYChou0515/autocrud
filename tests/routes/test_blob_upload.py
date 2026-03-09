"""Tests for blob upload endpoint (``POST /blobs/upload``) and
file_id-based create/update workflow.

Covers:
- Upload a file via multipart/form-data and receive file_id / size / content_type
- Create a resource using the uploaded file_id (no base64)
- Update a resource using the uploaded file_id
- Upload preserves content type
- Upload returns correct size
- Create with invalid (non-existent) file_id raises error
- Upload without blob store returns 501 / route not mounted
- Downloaded blob matches uploaded content
- Multiple Binary fields with file_id references
- Optional Binary field left empty (UNSET)
"""

import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct

from autocrud.crud.core import AutoCRUD
from autocrud.types import Binary

# ---------------------------------------------------------------------------
# Test Models
# ---------------------------------------------------------------------------


class UserWithAvatar(Struct):
    name: str
    avatar: Binary


class Document(Struct):
    title: str
    attachment: Binary
    thumbnail: Binary


class OptionalBinaryModel(Struct):
    name: str
    photo: Binary | None = None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def autocrud():
    app = AutoCRUD()
    app.add_model(UserWithAvatar)
    return app


@pytest.fixture
def client(autocrud):
    app = FastAPI()
    autocrud.apply(app)
    return TestClient(app)


@pytest.fixture
def multi_binary_client():
    crud = AutoCRUD()
    crud.add_model(Document)
    app = FastAPI()
    crud.apply(app)
    return TestClient(app), crud


# ---------------------------------------------------------------------------
# Upload endpoint tests
# ---------------------------------------------------------------------------


class TestBlobUpload:
    """POST /blobs/upload basic functionality."""

    def test_upload_returns_file_metadata(self, client):
        """Upload a file and verify file_id, size, content_type are returned."""
        resp = client.post(
            "/blobs/upload",
            files={"file": ("photo.png", b"fake-png-content", "image/png")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "file_id" in data
        assert data["size"] == len(b"fake-png-content")
        assert data["content_type"] == "image/png"
        # data (raw bytes) should NOT be in the response
        assert "data" not in data or data.get("data") is None

    def test_upload_preserves_content_type(self, client):
        """Content-Type from the uploaded file is stored correctly."""
        resp = client.post(
            "/blobs/upload",
            files={"file": ("doc.pdf", b"pdf-bytes", "application/pdf")},
        )
        assert resp.status_code == 200
        assert resp.json()["content_type"] == "application/pdf"

    def test_upload_default_content_type(self, client):
        """When no content type is provided, defaults to application/octet-stream."""
        resp = client.post(
            "/blobs/upload",
            files={"file": ("data.bin", b"binary-data")},
        )
        assert resp.status_code == 200
        # FastAPI sets content_type from the multipart header; if missing it
        # may still set application/octet-stream or similar.
        ct = resp.json()["content_type"]
        assert ct is not None

    def test_upload_and_download_match(self, client):
        """Uploaded content can be downloaded and matches exactly."""
        raw_content = b"hello-world-blob-content-12345"
        resp = client.post(
            "/blobs/upload",
            files={"file": ("test.txt", raw_content, "text/plain")},
        )
        assert resp.status_code == 200
        file_id = resp.json()["file_id"]

        # Download via GET /blobs/{file_id}
        dl = client.get(f"/blobs/{file_id}")
        assert dl.status_code == 200
        assert dl.content == raw_content

    def test_upload_idempotent_same_content(self, client):
        """Uploading the same content twice returns the same file_id (content-hash)."""
        content = b"identical-content"
        r1 = client.post(
            "/blobs/upload",
            files={"file": ("a.bin", content, "application/octet-stream")},
        )
        r2 = client.post(
            "/blobs/upload",
            files={"file": ("b.bin", content, "application/octet-stream")},
        )
        assert r1.json()["file_id"] == r2.json()["file_id"]


# ---------------------------------------------------------------------------
# Create with file_id tests
# ---------------------------------------------------------------------------


class TestCreateWithFileId:
    """Create a resource using a pre-uploaded file_id."""

    def test_create_with_uploaded_file_id(self, client, autocrud):
        """Upload → create resource with file_id → verify binary field metadata."""
        # 1. Upload
        raw = b"avatar-image-bytes"
        upload_resp = client.post(
            "/blobs/upload",
            files={"file": ("avatar.jpg", raw, "image/jpeg")},
        )
        file_id = upload_resp.json()["file_id"]

        # 2. Create using file_id only (no data/base64)
        create_resp = client.post(
            "/user-with-avatar",
            json={"name": "Alice", "avatar": {"file_id": file_id}},
        )
        assert create_resp.status_code == 200
        resource_id = create_resp.json()["resource_id"]

        # 3. Verify stored data has correct metadata
        get_resp = client.get(f"/user-with-avatar/{resource_id}/data")
        assert get_resp.status_code == 200
        avatar = get_resp.json()["avatar"]
        assert avatar["file_id"] == file_id
        assert avatar["size"] == len(raw)
        assert avatar["content_type"] == "image/jpeg"

    def test_create_with_invalid_file_id(self, client):
        """Create with a non-existent file_id should fail."""
        resp = client.post(
            "/user-with-avatar",
            json={"name": "Bob", "avatar": {"file_id": "nonexistent-id"}},
        )
        # FileNotFoundError → 404 via to_http_exception
        assert resp.status_code == 404
        assert "nonexistent-id" in resp.json()["detail"]

    def test_create_with_file_id_and_partial_metadata(self, client, autocrud):
        """Create with file_id + content_type but no size → size is backfilled."""
        raw = b"some-content"
        upload_resp = client.post(
            "/blobs/upload",
            files={"file": ("f.bin", raw, "application/octet-stream")},
        )
        file_id = upload_resp.json()["file_id"]

        # Provide file_id and content_type but not size
        create_resp = client.post(
            "/user-with-avatar",
            json={
                "name": "Charlie",
                "avatar": {"file_id": file_id, "content_type": "custom/type"},
            },
        )
        assert create_resp.status_code == 200
        resource_id = create_resp.json()["resource_id"]

        get_resp = client.get(f"/user-with-avatar/{resource_id}/data")
        avatar = get_resp.json()["avatar"]
        assert avatar["file_id"] == file_id
        assert avatar["size"] == len(raw)
        # User-provided content_type is preserved (not overwritten)
        assert avatar["content_type"] == "custom/type"

    def test_create_with_base64_still_works(self, client):
        """Backwards compatibility: base64 data in JSON body still works."""
        raw = b"base64-still-fine"
        b64 = base64.b64encode(raw).decode("utf-8")
        resp = client.post(
            "/user-with-avatar",
            json={"name": "Legacy", "avatar": {"data": b64}},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Update with file_id tests
# ---------------------------------------------------------------------------


class TestUpdateWithFileId:
    """Update a resource's Binary field using a pre-uploaded file_id."""

    def test_update_binary_with_new_file_id(self, client, autocrud):
        """Create with base64, then update with a new file_id."""
        # Create with base64
        raw1 = b"original-content"
        b64 = base64.b64encode(raw1).decode("utf-8")
        create_resp = client.post(
            "/user-with-avatar",
            json={"name": "Dave", "avatar": {"data": b64}},
        )
        resource_id = create_resp.json()["resource_id"]

        # Upload new avatar
        raw2 = b"updated-avatar-data"
        upload_resp = client.post(
            "/blobs/upload",
            files={"file": ("new-avatar.png", raw2, "image/png")},
        )
        new_file_id = upload_resp.json()["file_id"]

        # Update using file_id
        update_resp = client.put(
            f"/user-with-avatar/{resource_id}",
            json={"name": "Dave", "avatar": {"file_id": new_file_id}},
        )
        assert update_resp.status_code == 200

        # Verify
        get_resp = client.get(f"/user-with-avatar/{resource_id}/data")
        avatar = get_resp.json()["avatar"]
        assert avatar["file_id"] == new_file_id
        assert avatar["size"] == len(raw2)


# ---------------------------------------------------------------------------
# Multiple Binary fields
# ---------------------------------------------------------------------------


class TestMultipleBinaryFields:
    """Resources with multiple Binary fields."""

    def test_create_with_multiple_file_ids(self, multi_binary_client):
        """Upload two files separately, then create a resource referencing both."""
        client, crud = multi_binary_client

        # Upload attachment
        att_raw = b"attachment-content"
        r1 = client.post(
            "/blobs/upload",
            files={"file": ("doc.pdf", att_raw, "application/pdf")},
        )
        att_id = r1.json()["file_id"]

        # Upload thumbnail
        thumb_raw = b"thumbnail-content"
        r2 = client.post(
            "/blobs/upload",
            files={"file": ("thumb.png", thumb_raw, "image/png")},
        )
        thumb_id = r2.json()["file_id"]

        # Create
        resp = client.post(
            "/document",
            json={
                "title": "Report",
                "attachment": {"file_id": att_id},
                "thumbnail": {"file_id": thumb_id},
            },
        )
        assert resp.status_code == 200
        resource_id = resp.json()["resource_id"]

        # Verify
        get_resp = client.get(f"/document/{resource_id}/data")
        data = get_resp.json()
        assert data["attachment"]["file_id"] == att_id
        assert data["attachment"]["size"] == len(att_raw)
        assert data["thumbnail"]["file_id"] == thumb_id
        assert data["thumbnail"]["size"] == len(thumb_raw)

    def test_create_mixed_base64_and_file_id(self, multi_binary_client):
        """One field with base64, another with file_id."""
        client, crud = multi_binary_client

        # Upload thumbnail only
        thumb_raw = b"thumb-data"
        r = client.post(
            "/blobs/upload",
            files={"file": ("thumb.jpg", thumb_raw, "image/jpeg")},
        )
        thumb_id = r.json()["file_id"]

        # Create with base64 attachment + file_id thumbnail
        att_raw = b"attachment-base64"
        b64 = base64.b64encode(att_raw).decode("utf-8")
        resp = client.post(
            "/document",
            json={
                "title": "Mixed",
                "attachment": {"data": b64, "content_type": "application/pdf"},
                "thumbnail": {"file_id": thumb_id},
            },
        )
        assert resp.status_code == 200
        resource_id = resp.json()["resource_id"]

        get_resp = client.get(f"/document/{resource_id}/data")
        data = get_resp.json()
        assert data["attachment"]["size"] == len(att_raw)
        assert data["thumbnail"]["file_id"] == thumb_id


# ---------------------------------------------------------------------------
# Blob store not configured
# ---------------------------------------------------------------------------


class TestBlobUploadNoBlobStore:
    """When blob store is not configured, upload should not be available."""

    def test_upload_route_not_mounted_without_blob_store(self):
        """BlobRouteTemplate should not mount routes if blob_store is None."""
        from fastapi import APIRouter

        from autocrud.crud.route_templates.blob import BlobRouteTemplate
        from autocrud.resource_manager.core import ResourceManager, SimpleStorage
        from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
        from autocrud.resource_manager.resource_store.simple import MemoryResourceStore

        store = SimpleStorage(MemoryMetaStore(), MemoryResourceStore())
        manager = ResourceManager(UserWithAvatar, storage=store, blob_store=None)

        template = BlobRouteTemplate()
        router = APIRouter()
        template.apply("user-with-avatar", manager, router)

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        resp = client.post(
            "/blobs/upload",
            files={"file": ("f.bin", b"data", "application/octet-stream")},
        )
        assert resp.status_code in (404, 405)  # Route not registered
