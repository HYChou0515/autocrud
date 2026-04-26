"""Tests for IBlobStore.get_response() — blob store self-determined download strategy.

Each blob store decides its own preferred response order via ``get_response()``.
The route handler delegates entirely to the blob store, removing download
strategy logic from the router.

Default order: get_stream() → get() → get_url()
S3 with prefer_presigned_url=True: get_url() → get_stream() → get()
"""

from __future__ import annotations

import pytest
from msgspec import Struct as _Struct

from autocrud.resource_manager.blob_store.simple import DiskBlobStore, MemoryBlobStore
from autocrud.types import Binary as BinaryField
from autocrud.types import (
    BlobResponse,
    BlobStreamInfo,
)
from tests.test_blob_store_s3_session_persistence import FakeS3Client, _make_store


def _make_store_with_presigned(
    fake_client: FakeS3Client,
    prefix: str = "test/",
    prefer_presigned_url: bool = False,
):
    """Create an S3BlobStore with prefer_presigned_url support."""
    from unittest.mock import patch

    from autocrud.resource_manager.blob_store.s3 import S3BlobStore

    with patch("boto3.client", return_value=fake_client):
        return S3BlobStore(prefix=prefix, prefer_presigned_url=prefer_presigned_url)


# ===================================================================
# BlobResponse type
# ===================================================================


class TestBlobResponseType:
    """BlobResponse correctly represents the three download strategies."""

    def test_stream_variant(self):
        def gen():
            yield b"data"

        info = BlobStreamInfo(gen(), size=4, content_type="text/plain", file_id="f1")
        resp = BlobResponse(kind="stream", stream=info)
        assert resp.kind == "stream"
        assert resp.stream is info

    def test_redirect_variant(self):
        resp = BlobResponse(kind="redirect", url="https://example.com/blob")
        assert resp.kind == "redirect"
        assert resp.url == "https://example.com/blob"

    def test_data_variant(self):
        blob = BinaryField(
            file_id="f1", size=5, data=b"hello", content_type="text/plain"
        )
        resp = BlobResponse(kind="data", blob=blob)
        assert resp.kind == "data"
        assert resp.blob is blob


# ===================================================================
# MemoryBlobStore.get_response()
# ===================================================================


class TestMemoryBlobStoreGetResponse:
    """MemoryBlobStore falls back to data (get_stream returns None)."""

    def test_returns_data_response(self):
        store = MemoryBlobStore()
        store.put(b"hello memory", key="mem1", content_type="text/plain")
        resp = store.get_response("mem1")
        # MemoryBlobStore has no streaming, no URL → must be data
        assert resp.kind == "data"
        assert resp.blob is not None
        assert resp.blob.data == b"hello memory"

    def test_not_found_raises(self):
        store = MemoryBlobStore()
        with pytest.raises(FileNotFoundError):
            store.get_response("nonexistent")


# ===================================================================
# DiskBlobStore.get_response()
# ===================================================================


class TestDiskBlobStoreGetResponse:
    """DiskBlobStore prefers streaming (default order)."""

    def test_returns_stream_response(self, tmp_path):
        store = DiskBlobStore(tmp_path)
        data = b"disk content"
        result = store.put(data, content_type="application/pdf")
        resp = store.get_response(result.file_id)

        assert resp.kind == "stream"
        assert resp.stream is not None
        assert resp.stream.size == len(data)
        chunks = list(resp.stream.iterator)
        assert b"".join(chunks) == data

    def test_stream_has_correct_content_type(self, tmp_path):
        store = DiskBlobStore(tmp_path)
        result = store.put(b"test", content_type="image/png")
        resp = store.get_response(result.file_id)
        assert resp.kind == "stream"
        assert resp.stream.content_type == "image/png"

    def test_not_found_raises(self, tmp_path):
        store = DiskBlobStore(tmp_path)
        with pytest.raises(FileNotFoundError):
            store.get_response("nonexistent")


# ===================================================================
# S3BlobStore.get_response() — default (no presigned preference)
# ===================================================================


class TestS3BlobStoreGetResponseDefault:
    """S3BlobStore default: streaming first."""

    def test_returns_stream_by_default(self):
        fake = FakeS3Client()
        store = _make_store(fake, prefix="gr1/")
        data = b"s3 stream content"
        result = store.put(data, content_type="text/plain")

        resp = store.get_response(result.file_id)
        assert resp.kind == "stream"
        assert resp.stream is not None
        chunks = list(resp.stream.iterator)
        assert b"".join(chunks) == data

    def test_not_found_raises(self):
        fake = FakeS3Client()
        store = _make_store(fake, prefix="gr2/")
        with pytest.raises(FileNotFoundError):
            store.get_response("nonexistent")


# ===================================================================
# S3BlobStore.get_response() — prefer_presigned_url=True
# ===================================================================


class TestS3BlobStoreGetResponsePresigned:
    """S3BlobStore with prefer_presigned_url=True: redirect first."""

    def test_returns_redirect_when_prefer_presigned(self):
        fake = FakeS3Client()
        store = _make_store_with_presigned(
            fake, prefix="gr3/", prefer_presigned_url=True
        )
        data = b"presigned content"
        result = store.put(data)

        resp = store.get_response(result.file_id)
        assert resp.kind == "redirect"
        assert resp.url is not None
        # The presigned URL should contain the file_id
        assert result.file_id in resp.url


# ===================================================================
# Route integration: router delegates to get_response
# ===================================================================


class _RouteFileModel(_Struct):
    name: str
    attachment: BinaryField


class TestBlobRouteGetResponse:
    """GET /blobs/{file_id} delegates to blob_store.get_response()."""

    @pytest.fixture
    def app_and_store(self, tmp_path):
        from fastapi import FastAPI

        from autocrud.crud.core import AutoCRUD

        store = DiskBlobStore(tmp_path / "blobs")

        crud_instance = AutoCRUD()
        crud_instance.blob_store = store
        crud_instance.add_model(_RouteFileModel)
        app = FastAPI()
        crud_instance.apply(app)
        return app, store

    @pytest.fixture
    def client(self, app_and_store):
        from starlette.testclient import TestClient

        app, _ = app_and_store
        return TestClient(app)

    def test_download_streams_with_content_length(self, app_and_store, client):
        """Route returns streaming response via get_response()."""
        _, store = app_and_store
        data = b"route-test-data"
        result = store.put(data, content_type="text/plain")

        resp = client.get(f"/blobs/{result.file_id}")
        assert resp.status_code == 200
        assert resp.content == data
        assert resp.headers.get("content-length") == str(len(data))

    def test_download_large_blob(self, app_and_store, client):
        """Large blobs are streamed without loading fully into memory."""
        _, store = app_and_store
        data = b"L" * (4 * 1024 * 1024)  # 4 MB
        result = store.put(data, content_type="application/octet-stream")

        resp = client.get(f"/blobs/{result.file_id}")
        assert resp.status_code == 200
        assert resp.content == data

    def test_404_for_missing_blob(self, app_and_store, client):
        resp = client.get("/blobs/nonexistent")
        assert resp.status_code == 404
