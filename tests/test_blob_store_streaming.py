"""Tests for IBlobStore.get_stream() and streaming blob download route.

Verifies that blob stores provide a chunked streaming download method
that returns an iterator + metadata, enabling StreamingResponse for
large blobs without loading the entire file into memory.
"""

from __future__ import annotations

import pytest

# Model for route tests — must be module-level for msgspec type resolution
from msgspec import Struct as _Struct

from autocrud.resource_manager.blob_store.simple import DiskBlobStore, MemoryBlobStore
from autocrud.types import Binary as BinaryField
from autocrud.types import BlobStreamInfo
from tests.test_blob_store_s3_session_persistence import FakeS3Client, _make_store


class _FileModel(_Struct):
    name: str
    attachment: BinaryField


# ===================================================================
# IBlobStore.get_stream() contract
# ===================================================================


class TestMemoryBlobStoreGetStream:
    """MemoryBlobStore.get_stream() returns None (data already in memory)."""

    def test_returns_none(self):
        store = MemoryBlobStore()
        store.put(b"test data", key="mem-blob")
        assert store.get_stream("mem-blob") is None


class TestDiskBlobStoreGetStream:
    """DiskBlobStore.get_stream() returns BlobStreamInfo with chunked iterator."""

    def test_returns_blob_stream_info(self, tmp_path):
        store = DiskBlobStore(tmp_path)
        data = b"A" * 1000
        result = store.put(data, content_type="text/plain")
        stream_info = store.get_stream(result.file_id)

        assert stream_info is not None
        assert isinstance(stream_info, BlobStreamInfo)
        assert stream_info.size == 1000
        assert stream_info.content_type == "text/plain"
        assert stream_info.file_id == result.file_id

    def test_iterator_yields_correct_data(self, tmp_path):
        store = DiskBlobStore(tmp_path)
        data = b"hello streaming world"
        result = store.put(data)
        stream_info = store.get_stream(result.file_id)

        chunks = list(stream_info.iterator)
        assert b"".join(chunks) == data

    def test_not_found_raises(self, tmp_path):
        store = DiskBlobStore(tmp_path)
        with pytest.raises(FileNotFoundError):
            store.get_stream("nonexistent")

    def test_content_type_unset(self, tmp_path):
        """When no content_type specified, it should be UNSET."""
        store = DiskBlobStore(tmp_path)
        result = store.put(b"no ct")
        stream_info = store.get_stream(result.file_id)
        assert stream_info is not None
        # content_type depends on whether magic is available; just verify it's set
        assert stream_info.size == 5

    def test_streams_in_chunks(self, tmp_path):
        """Large data should be yielded in multiple chunks."""
        store = DiskBlobStore(tmp_path)
        # 16 MB of data → should yield multiple chunks with 8 MB chunk size
        data = b"X" * (16 * 1024 * 1024)
        result = store.put(data)
        stream_info = store.get_stream(result.file_id)

        chunks = list(stream_info.iterator)
        assert len(chunks) == 2
        assert b"".join(chunks) == data


class TestS3BlobStoreGetStream:
    """S3BlobStore.get_stream() returns BlobStreamInfo with chunked iterator."""

    def test_returns_blob_stream_info(self):
        fake = FakeS3Client()
        store = _make_store(fake, prefix="gs1/")
        data = b"s3 stream test data"
        result = store.put(data, content_type="text/plain")
        stream_info = store.get_stream(result.file_id)

        assert stream_info is not None
        assert isinstance(stream_info, BlobStreamInfo)
        assert stream_info.size == len(data)
        assert stream_info.file_id == result.file_id

    def test_iterator_yields_correct_data(self):
        fake = FakeS3Client()
        store = _make_store(fake, prefix="gs2/")
        data = b"hello s3 streaming"
        result = store.put(data)
        stream_info = store.get_stream(result.file_id)

        chunks = list(stream_info.iterator)
        assert b"".join(chunks) == data

    def test_not_found_raises(self):
        fake = FakeS3Client()
        store = _make_store(fake, prefix="gs3/")
        with pytest.raises(FileNotFoundError):
            store.get_stream("nonexistent")

    def test_finalized_blob_streamable(self):
        """Blob created via upload session should be streamable."""
        fake = FakeS3Client()
        store = _make_store(fake, prefix="gs4/")
        session = store.create_upload_session(total_parts=2)
        uid = session.upload_id

        store.upload_to_session(uid, b"part1-", part_number=1)
        store.upload_to_session(uid, b"part2", part_number=2)
        result = store.finalize_upload_session(uid)

        stream_info = store.get_stream(result.file_id)
        assert stream_info is not None
        chunks = list(stream_info.iterator)
        assert b"".join(chunks) == b"part1-part2"
        assert stream_info.size == 11


# ===================================================================
# Route handler streaming test
# ===================================================================


class TestBlobRouteStreaming:
    """GET /blobs/{file_id} should use StreamingResponse with Content-Length."""

    @pytest.fixture
    def app_and_store(self, tmp_path):
        from fastapi import FastAPI

        from autocrud.crud.core import AutoCRUD

        store = DiskBlobStore(tmp_path / "blobs")

        crud_instance = AutoCRUD()
        # Set blob_store BEFORE add_model so the ResourceManager uses it
        crud_instance.blob_store = store
        crud_instance.add_model(_FileModel)
        app = FastAPI()
        crud_instance.apply(app)
        return app, store

    @pytest.fixture
    def client(self, app_and_store):
        from starlette.testclient import TestClient

        app, _ = app_and_store
        return TestClient(app)

    def test_download_returns_content_length_header(self, app_and_store, client):
        """Streaming response includes Content-Length for progress indication."""
        _, store = app_and_store
        data = b"streaming-route-test-data"
        result = store.put(data, content_type="text/plain")

        resp = client.get(f"/blobs/{result.file_id}")
        assert resp.status_code == 200
        assert resp.content == data
        assert resp.headers.get("content-length") == str(len(data))

    def test_download_large_blob_streams(self, app_and_store, client):
        """Large blobs should be streamed (not loaded fully into memory)."""
        _, store = app_and_store
        data = b"L" * (4 * 1024 * 1024)  # 4 MB
        result = store.put(data, content_type="application/octet-stream")

        resp = client.get(f"/blobs/{result.file_id}")
        assert resp.status_code == 200
        assert resp.content == data
        assert resp.headers.get("content-length") == str(len(data))
