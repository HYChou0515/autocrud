"""Contract tests for IBlobStore chunked upload-session API.

Exercises the chunked upload lifecycle (create → upload chunk 1 →
upload chunk 2 → … → finalize) against MemoryBlobStore and DiskBlobStore.
S3BlobStore is tested separately since it requires a running S3/MinIO
service.
"""

from collections.abc import Generator

import pytest
from msgspec import UNSET

from autocrud.resource_manager.basic import IBlobStore
from autocrud.resource_manager.blob_store.simple import DiskBlobStore, MemoryBlobStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(params=["memory", "disk"])
def blob_store(
    request: pytest.FixtureRequest, tmp_path: pytest.TempPathFactory
) -> Generator[IBlobStore]:
    if request.param == "memory":
        yield MemoryBlobStore()
    elif request.param == "disk":
        yield DiskBlobStore(tmp_path / "blobs_chunked")
    else:
        raise ValueError(f"Unknown: {request.param}")


CHUNK_1 = b"A" * 1024
CHUNK_2 = b"B" * 2048
CHUNK_3 = b"C" * 512
ALL_DATA = CHUNK_1 + CHUNK_2 + CHUNK_3


# ---------------------------------------------------------------------------
# Tests — chunked upload happy path
# ---------------------------------------------------------------------------


class TestChunkedUploadHappyPath:
    """Multiple upload_to_session calls → finalize → data intact."""

    def test_multi_chunk_finalize(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session(
            content_type="application/octet-stream"
        )
        uid = session.upload_id
        assert session.status == "pending"
        assert session.uploaded_size == 0

        # Upload chunk 1
        blob_store.upload_to_session(uid, CHUNK_1, part_number=1)
        s1 = blob_store.get_upload_session(uid)
        assert s1.status == "uploading"
        assert s1.uploaded_size == len(CHUNK_1)

        # Upload chunk 2
        blob_store.upload_to_session(uid, CHUNK_2, part_number=2)
        s2 = blob_store.get_upload_session(uid)
        assert s2.status == "uploading"
        assert s2.uploaded_size == len(CHUNK_1) + len(CHUNK_2)

        # Upload chunk 3
        blob_store.upload_to_session(uid, CHUNK_3, part_number=3)
        s3 = blob_store.get_upload_session(uid)
        assert s3.status == "uploading"
        assert s3.uploaded_size == len(ALL_DATA)

        # Finalize
        result = blob_store.finalize_upload_session(uid)
        assert result.size is not UNSET
        assert result.size == len(ALL_DATA)
        assert result.file_id is not UNSET

        # Verify data integrity
        stored = blob_store.get(result.file_id)
        assert stored.data == ALL_DATA

    def test_two_chunks_with_custom_key(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session(key="my-file")
        uid = session.upload_id

        blob_store.upload_to_session(uid, CHUNK_1, part_number=1)
        blob_store.upload_to_session(uid, CHUNK_2, part_number=2)
        result = blob_store.finalize_upload_session(uid)

        assert result.file_id == "my-file"
        stored = blob_store.get("my-file")
        assert stored.data == CHUNK_1 + CHUNK_2


class TestChunkedUploadProgress:
    """uploaded_size tracks cumulative bytes correctly."""

    def test_uploaded_size_increments(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session(size=len(ALL_DATA))
        uid = session.upload_id

        expected_size = 0
        for i, chunk in enumerate([CHUNK_1, CHUNK_2, CHUNK_3], start=1):
            blob_store.upload_to_session(uid, chunk, part_number=i)
            expected_size += len(chunk)
            s = blob_store.get_upload_session(uid)
            assert s.uploaded_size == expected_size

    def test_initial_uploaded_size_is_zero(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session()
        assert session.uploaded_size == 0
        s = blob_store.get_upload_session(session.upload_id)
        assert s.uploaded_size == 0


class TestChunkedUploadAbort:
    """Abort during chunked upload cleans up properly."""

    def test_abort_during_uploading(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session()
        uid = session.upload_id

        blob_store.upload_to_session(uid, CHUNK_1, part_number=1)
        blob_store.upload_to_session(uid, CHUNK_2, part_number=2)
        s = blob_store.get_upload_session(uid)
        assert s.status == "uploading"

        blob_store.abort_upload_session(uid)
        s = blob_store.get_upload_session(uid)
        assert s.status == "aborted"

    def test_cannot_upload_after_abort(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session()
        uid = session.upload_id

        blob_store.upload_to_session(uid, CHUNK_1, part_number=1)
        blob_store.abort_upload_session(uid)

        with pytest.raises(ValueError, match="aborted"):
            blob_store.upload_to_session(uid, CHUNK_2, part_number=2)

    def test_cannot_finalize_after_abort(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session()
        uid = session.upload_id

        blob_store.upload_to_session(uid, CHUNK_1, part_number=1)
        blob_store.abort_upload_session(uid)

        with pytest.raises(ValueError):
            blob_store.finalize_upload_session(uid)


class TestChunkedUploadErrors:
    """Error cases for chunked upload."""

    def test_cannot_upload_after_finalize(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session()
        uid = session.upload_id

        blob_store.upload_to_session(uid, CHUNK_1, part_number=1)
        blob_store.finalize_upload_session(uid)

        with pytest.raises(ValueError):
            blob_store.upload_to_session(uid, CHUNK_2, part_number=2)

    def test_cannot_finalize_pending_session(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session()
        with pytest.raises(ValueError, match="pending"):
            blob_store.finalize_upload_session(session.upload_id)


class TestBackwardCompatibility:
    """Single-call upload_to_session still works (status becomes 'uploading', finalize accepts it)."""

    def test_single_upload_still_works(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session(content_type="text/plain")
        uid = session.upload_id

        data = b"single upload data"
        blob_store.upload_to_session(uid, data, part_number=1)

        s = blob_store.get_upload_session(uid)
        assert s.status == "uploading"
        assert s.uploaded_size == len(data)

        result = blob_store.finalize_upload_session(uid)
        assert result.size == len(data)

        stored = blob_store.get(result.file_id)
        assert stored.data == data
