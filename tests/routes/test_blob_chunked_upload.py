"""Tests for chunked blob upload via HTTP endpoints.

Exercises the chunked upload lifecycle through FastAPI routes:
create session → PUT chunk 1 → PUT chunk 2 → GET session (verify progress)
→ finalize → GET blob (verify data integrity).
"""

import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct

from autocrud.crud.core import AutoCRUD
from autocrud.types import Binary

# ---------------------------------------------------------------------------
# Test model
# ---------------------------------------------------------------------------


class Doc(Struct):
    title: str
    file: Binary


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def autocrud():
    app = AutoCRUD()
    app.add_model(Doc)
    return app


@pytest.fixture
def client(autocrud):
    app = FastAPI()
    autocrud.apply(app)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CHUNK_1 = b"X" * 5000
CHUNK_2 = b"Y" * 3000
CHUNK_3 = b"Z" * 2000
ALL_DATA = CHUNK_1 + CHUNK_2 + CHUNK_3


def _create_session(client, content_type="application/octet-stream", size=None):
    body = {"content_type": content_type}
    if size is not None:
        body["size"] = size
    resp = client.post("/blobs/upload-sessions", json=body)
    return resp


def _put_chunk(
    client, upload_id, data, *, part_number=1, content_type="application/octet-stream"
):
    return client.put(
        f"/blobs/upload-sessions/{upload_id}/content",
        params={"part_number": part_number},
        files={"file": ("chunk.bin", io.BytesIO(data), content_type)},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestChunkedUploadRoutes:
    """Full chunked upload happy path via HTTP."""

    def test_multi_chunk_upload_and_finalize(self, client):
        # Create session
        resp = _create_session(client, size=len(ALL_DATA))
        assert resp.status_code == 200
        session = resp.json()
        upload_id = session["upload_id"]
        assert session["status"] == "pending"
        assert session["uploaded_size"] == 0

        # Upload chunk 1
        resp = _put_chunk(client, upload_id, CHUNK_1, part_number=1)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "uploading"
        assert body["uploaded_size"] == len(CHUNK_1)

        # Upload chunk 2
        resp = _put_chunk(client, upload_id, CHUNK_2, part_number=2)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "uploading"
        assert body["uploaded_size"] == len(CHUNK_1) + len(CHUNK_2)

        # Upload chunk 3
        resp = _put_chunk(client, upload_id, CHUNK_3, part_number=3)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "uploading"
        assert body["uploaded_size"] == len(ALL_DATA)

        # GET session to verify state
        resp = client.get(f"/blobs/upload-sessions/{upload_id}")
        assert resp.status_code == 200
        session = resp.json()
        assert session["status"] == "uploading"
        assert session["uploaded_size"] == len(ALL_DATA)

        # Finalize
        resp = client.post(f"/blobs/upload-sessions/{upload_id}/finalize")
        assert resp.status_code == 200
        result = resp.json()
        file_id = result["file_id"]
        assert result["size"] == len(ALL_DATA)

        # Download and verify
        resp = client.get(f"/blobs/{file_id}")
        assert resp.status_code == 200
        assert resp.content == ALL_DATA

    def test_single_chunk_upload(self, client):
        """Single chunk still works through the session flow."""
        data = b"single chunk data"
        resp = _create_session(client, size=len(data))
        assert resp.status_code == 200
        upload_id = resp.json()["upload_id"]

        resp = _put_chunk(client, upload_id, data, part_number=1)
        assert resp.status_code == 200
        assert resp.json()["uploaded_size"] == len(data)

        resp = client.post(f"/blobs/upload-sessions/{upload_id}/finalize")
        assert resp.status_code == 200
        file_id = resp.json()["file_id"]

        resp = client.get(f"/blobs/{file_id}")
        assert resp.status_code == 200
        assert resp.content == data

    def test_abort_during_chunked_upload(self, client):
        """Abort mid-upload returns 204 and prevents further uploads."""
        resp = _create_session(client)
        upload_id = resp.json()["upload_id"]

        _put_chunk(client, upload_id, CHUNK_1, part_number=1)
        _put_chunk(client, upload_id, CHUNK_2, part_number=2)

        resp = client.post(f"/blobs/upload-sessions/{upload_id}/abort")
        assert resp.status_code == 204

        # Session is aborted
        resp = client.get(f"/blobs/upload-sessions/{upload_id}")
        assert resp.json()["status"] == "aborted"

        # Cannot upload more
        resp = _put_chunk(client, upload_id, CHUNK_3, part_number=3)
        assert resp.status_code == 409

    def test_cannot_finalize_pending_session(self, client):
        """Finalize without any upload should fail."""
        resp = _create_session(client)
        upload_id = resp.json()["upload_id"]

        resp = client.post(f"/blobs/upload-sessions/{upload_id}/finalize")
        assert resp.status_code == 409

    def test_chunked_upload_used_in_resource_create(self, client):
        """Upload via session, then use file_id in resource creation."""
        resp = _create_session(client, content_type="text/plain", size=len(ALL_DATA))
        upload_id = resp.json()["upload_id"]

        _put_chunk(client, upload_id, CHUNK_1, part_number=1)
        _put_chunk(client, upload_id, CHUNK_2, part_number=2)
        _put_chunk(client, upload_id, CHUNK_3, part_number=3)

        resp = client.post(f"/blobs/upload-sessions/{upload_id}/finalize")
        assert resp.status_code == 200
        file_id = resp.json()["file_id"]

        # Create a resource referencing the uploaded file
        resp = client.post(
            "/doc",
            json={"title": "Test", "file": {"file_id": file_id}},
        )
        assert resp.status_code == 200

        # Fetch resource and verify blob reference
        resource_id = resp.json()["resource_id"]
        resp = client.get(f"/doc/{resource_id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["file"]["file_id"] == file_id
