"""Contract tests for IBlobStore upload-session API.

Exercises the full upload-session lifecycle (create → upload → finalize /
abort) against every IBlobStore implementation: MemoryBlobStore,
DiskBlobStore, S3BlobStore (proxy mode), and S3BlobStore (single_put mode).
"""

from collections.abc import Generator

import pytest
from msgspec import UNSET

from specstar.resource_manager.basic import IBlobStore
from specstar.resource_manager.blob_store.simple import DiskBlobStore, MemoryBlobStore
from specstar.types import BlobUploadSession

# ---------------------------------------------------------------------------
# Parametrized fixture — runs every test against all implementations
# ---------------------------------------------------------------------------


@pytest.fixture(
    params=[
        "memory",
        "disk",
        pytest.param("s3_proxy", marks=pytest.mark.integration),
        pytest.param("s3_single_put", marks=pytest.mark.integration),
    ]
)
def blob_store(
    request: pytest.FixtureRequest, tmp_path: pytest.TempPathFactory
) -> Generator[IBlobStore]:
    """Fixture that yields each IBlobStore implementation."""
    if request.param == "memory":
        yield MemoryBlobStore()
    elif request.param == "disk":
        yield DiskBlobStore(tmp_path / "blobs_session")  # ty:ignore[unsupported-operator]
    elif request.param == "s3_proxy":
        from specstar.resource_manager.blob_store.s3 import S3BlobStore

        prefix = f"{tmp_path.name}_proxy/"  # ty:ignore[unresolved-attribute]
        store = S3BlobStore(
            endpoint_url="http://localhost:9000",
            prefix=prefix,
            upload_method="proxy",
        )
        yield store
    elif request.param == "s3_single_put":
        from specstar.resource_manager.blob_store.s3 import S3BlobStore

        prefix = f"{tmp_path.name}_sput/"  # ty:ignore[unresolved-attribute]
        store = S3BlobStore(
            endpoint_url="http://localhost:9000",
            prefix=prefix,
            upload_method="single_put",
        )
        yield store
    else:
        raise ValueError(f"Unknown blob store type: {request.param}")


# Convenience helper — only proxy stores
@pytest.fixture(
    params=[
        "memory",
        "disk",
        pytest.param("s3_proxy", marks=pytest.mark.integration),
    ]
)
def proxy_blob_store(
    request: pytest.FixtureRequest, tmp_path: pytest.TempPathFactory
) -> Generator[IBlobStore]:
    """Fixture yielding only proxy-mode blob stores (excludes single_put)."""
    if request.param == "memory":
        yield MemoryBlobStore()
    elif request.param == "disk":
        yield DiskBlobStore(tmp_path / "blobs_proxy")  # ty:ignore[unsupported-operator]
    elif request.param == "s3_proxy":
        from specstar.resource_manager.blob_store.s3 import S3BlobStore

        prefix = f"{tmp_path.name}_pxy/"  # ty:ignore[unresolved-attribute]
        store = S3BlobStore(
            endpoint_url="http://localhost:9000",
            prefix=prefix,
            upload_method="proxy",
        )
        yield store
    else:
        raise ValueError(f"Unknown blob store type: {request.param}")


SAMPLE_BYTES = b"upload-session-test-data"
SAMPLE_CT = "text/plain"


# ===================================================================
# create_upload_session
# ===================================================================


class TestCreateUploadSession:
    def test_returns_blob_upload_session(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session()
        assert isinstance(session, BlobUploadSession)

    def test_status_is_pending(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session()
        assert session.status == "pending"

    def test_upload_id_is_nonempty(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session()
        assert len(session.upload_id) > 0

    def test_content_type_preserved(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session(content_type="image/png")
        assert session.content_type == "image/png"

    def test_size_preserved(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session(size=42)
        assert session.size == 42

    def test_default_content_type_is_unset(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session()
        assert session.content_type is UNSET

    def test_proxy_stores_have_proxy_method(self, proxy_blob_store: IBlobStore):
        session = proxy_blob_store.create_upload_session()
        assert session.upload_method == "proxy"
        assert session.upload_id in session.upload_url

    @pytest.mark.integration
    def test_s3_single_put_has_single_put_method(self, tmp_path):
        """S3 single_put returns upload_method='single_put' with a presigned URL."""
        from specstar.resource_manager.blob_store.s3 import S3BlobStore

        store = S3BlobStore(
            endpoint_url="http://localhost:9000",
            prefix=f"{tmp_path.name}_test_sp/",
            upload_method="single_put",
        )
        session = store.create_upload_session(content_type="application/octet-stream")
        assert session.upload_method == "single_put"
        assert session.upload_url.startswith("http")


# ===================================================================
# get_upload_session
# ===================================================================


class TestGetUploadSession:
    def test_returns_pending_session(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session()
        retrieved = blob_store.get_upload_session(session.upload_id)
        assert retrieved.upload_id == session.upload_id
        assert retrieved.status == "pending"

    def test_not_found_raises(self, blob_store: IBlobStore):
        with pytest.raises(FileNotFoundError):
            blob_store.get_upload_session("nonexistent-upload-id")


# ===================================================================
# upload_to_session (proxy mode only)
# ===================================================================


class TestUploadToSession:
    def test_upload_bytes(self, proxy_blob_store: IBlobStore):
        session = proxy_blob_store.create_upload_session(content_type=SAMPLE_CT)
        proxy_blob_store.upload_to_session(
            session.upload_id, SAMPLE_BYTES, part_number=1
        )
        retrieved = proxy_blob_store.get_upload_session(session.upload_id)
        assert retrieved.status == "uploading"
        assert retrieved.uploaded_size == len(SAMPLE_BYTES)

    def test_not_found_raises(self, proxy_blob_store: IBlobStore):
        with pytest.raises(FileNotFoundError):
            proxy_blob_store.upload_to_session("nonexistent", b"data", part_number=1)

    def test_upload_twice_appends_chunks(self, proxy_blob_store: IBlobStore):
        """Uploading twice appends data (chunked upload support)."""
        session = proxy_blob_store.create_upload_session()
        proxy_blob_store.upload_to_session(session.upload_id, b"first", part_number=1)
        proxy_blob_store.upload_to_session(session.upload_id, b"second", part_number=2)
        retrieved = proxy_blob_store.get_upload_session(session.upload_id)
        assert retrieved.status == "uploading"
        assert retrieved.uploaded_size == len(b"first") + len(b"second")

    def test_cannot_upload_after_finalize(self, proxy_blob_store: IBlobStore):
        session = proxy_blob_store.create_upload_session()
        proxy_blob_store.upload_to_session(
            session.upload_id, SAMPLE_BYTES, part_number=1
        )
        proxy_blob_store.finalize_upload_session(session.upload_id)
        with pytest.raises(ValueError, match="finalized"):
            proxy_blob_store.upload_to_session(
                session.upload_id, b"more", part_number=2
            )

    def test_cannot_upload_after_abort(self, proxy_blob_store: IBlobStore):
        session = proxy_blob_store.create_upload_session()
        proxy_blob_store.abort_upload_session(session.upload_id)
        with pytest.raises(ValueError, match="aborted"):
            proxy_blob_store.upload_to_session(
                session.upload_id, b"more", part_number=1
            )

    @pytest.mark.integration
    def test_s3_single_put_raises_not_implemented(self, tmp_path):
        """In single_put mode, upload_to_session is not supported."""
        from specstar.resource_manager.blob_store.s3 import S3BlobStore

        store = S3BlobStore(
            endpoint_url="http://localhost:9000",
            prefix=f"{tmp_path.name}_upl/",
            upload_method="single_put",
        )
        session = store.create_upload_session()
        with pytest.raises(NotImplementedError, match="single_put"):
            store.upload_to_session(session.upload_id, b"data", part_number=1)


# ===================================================================
# finalize_upload_session (proxy mode)
# ===================================================================


class TestFinalizeUploadSession:
    def test_happy_path(self, proxy_blob_store: IBlobStore):
        """create → upload → finalize → data retrievable via get()."""
        session = proxy_blob_store.create_upload_session(content_type=SAMPLE_CT)
        proxy_blob_store.upload_to_session(
            session.upload_id, SAMPLE_BYTES, part_number=1
        )
        result = proxy_blob_store.finalize_upload_session(session.upload_id)

        assert result.file_id
        assert result.size == len(SAMPLE_BYTES)

        # Data must be in the blob store
        blob = proxy_blob_store.get(result.file_id)  # ty:ignore[invalid-argument-type]
        assert blob.data == SAMPLE_BYTES

    def test_finalize_without_upload_raises(self, proxy_blob_store: IBlobStore):
        session = proxy_blob_store.create_upload_session()
        with pytest.raises(ValueError, match="pending"):
            proxy_blob_store.finalize_upload_session(session.upload_id)

    def test_finalize_twice_raises(self, proxy_blob_store: IBlobStore):
        session = proxy_blob_store.create_upload_session()
        proxy_blob_store.upload_to_session(
            session.upload_id, SAMPLE_BYTES, part_number=1
        )
        proxy_blob_store.finalize_upload_session(session.upload_id)
        with pytest.raises(ValueError, match="finalized"):
            proxy_blob_store.finalize_upload_session(session.upload_id)

    def test_not_found_raises(self, proxy_blob_store: IBlobStore):
        with pytest.raises(FileNotFoundError):
            proxy_blob_store.finalize_upload_session("nonexistent")

    def test_session_status_after_finalize(self, proxy_blob_store: IBlobStore):
        session = proxy_blob_store.create_upload_session()
        proxy_blob_store.upload_to_session(
            session.upload_id, SAMPLE_BYTES, part_number=1
        )
        proxy_blob_store.finalize_upload_session(session.upload_id)
        retrieved = proxy_blob_store.get_upload_session(session.upload_id)
        assert retrieved.status == "finalized"

    def test_finalize_with_custom_key(self, proxy_blob_store: IBlobStore):
        """When key is specified in create_upload_session, put() uses that key."""
        session = proxy_blob_store.create_upload_session(
            key="my-custom-blob-key", content_type=SAMPLE_CT
        )
        proxy_blob_store.upload_to_session(
            session.upload_id, SAMPLE_BYTES, part_number=1
        )
        result = proxy_blob_store.finalize_upload_session(session.upload_id)
        assert result.file_id == "my-custom-blob-key"
        blob = proxy_blob_store.get("my-custom-blob-key")
        assert blob.data == SAMPLE_BYTES


# ===================================================================
# abort_upload_session
# ===================================================================


class TestAbortUploadSession:
    def test_abort_pending(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session()
        blob_store.abort_upload_session(session.upload_id)
        retrieved = blob_store.get_upload_session(session.upload_id)
        assert retrieved.status == "aborted"

    def test_abort_uploaded(self, proxy_blob_store: IBlobStore):
        session = proxy_blob_store.create_upload_session()
        proxy_blob_store.upload_to_session(
            session.upload_id, SAMPLE_BYTES, part_number=1
        )
        proxy_blob_store.abort_upload_session(session.upload_id)
        retrieved = proxy_blob_store.get_upload_session(session.upload_id)
        assert retrieved.status == "aborted"

    def test_abort_finalized_raises(self, proxy_blob_store: IBlobStore):
        session = proxy_blob_store.create_upload_session()
        proxy_blob_store.upload_to_session(
            session.upload_id, SAMPLE_BYTES, part_number=1
        )
        proxy_blob_store.finalize_upload_session(session.upload_id)
        with pytest.raises(ValueError, match="finalized"):
            proxy_blob_store.abort_upload_session(session.upload_id)

    def test_not_found_raises(self, blob_store: IBlobStore):
        with pytest.raises(FileNotFoundError):
            blob_store.abort_upload_session("nonexistent")

    def test_abort_then_finalize_raises(self, proxy_blob_store: IBlobStore):
        """After abort, finalize must fail."""
        session = proxy_blob_store.create_upload_session()
        proxy_blob_store.upload_to_session(
            session.upload_id, SAMPLE_BYTES, part_number=1
        )
        proxy_blob_store.abort_upload_session(session.upload_id)
        with pytest.raises(ValueError, match="aborted"):
            proxy_blob_store.finalize_upload_session(session.upload_id)


# ===================================================================
# S3 single_put finalize (requires actual S3 object)
# ===================================================================


@pytest.mark.integration
class TestS3SinglePutFinalize:
    """Tests specific to S3 single_put mode finalize behavior.

    Every test in the class needs a live S3 / MinIO endpoint reachable
    at ``http://localhost:9000`` (see fixture below), so the class is
    marked ``integration`` wholesale.
    """

    @pytest.fixture
    def s3_single_put_store(self, tmp_path):
        from specstar.resource_manager.blob_store.s3 import S3BlobStore

        return S3BlobStore(
            endpoint_url="http://localhost:9000",
            prefix=f"{tmp_path.name}_spf/",
            upload_method="single_put",
        )

    def test_finalize_after_client_upload(self, s3_single_put_store):
        """Simulate: create session → client PUT to S3 → finalize."""
        store = s3_single_put_store
        session = store.create_upload_session(content_type="text/plain")

        # Simulate client uploading directly to S3 via the temp key
        s3_key = f"{store.prefix}_uploads/{session.upload_id}"
        store.client.put_object(
            Bucket=store.bucket,
            Key=s3_key,
            Body=SAMPLE_BYTES,
            ContentType="text/plain",
        )

        result = store.finalize_upload_session(session.upload_id)
        assert result.file_id  # non-empty
        assert result.size == len(SAMPLE_BYTES)

        # Verify the blob is at the final location
        blob = store.get(result.file_id)
        assert blob.data == SAMPLE_BYTES

    def test_finalize_without_client_upload_raises(self, s3_single_put_store):
        """Finalize before the client has uploaded should raise ValueError."""
        store = s3_single_put_store
        session = store.create_upload_session()
        with pytest.raises(ValueError, match="not found|not uploaded"):
            store.finalize_upload_session(session.upload_id)

    def test_finalize_with_custom_key(self, s3_single_put_store):
        """When key is specified, the final blob uses that key."""
        store = s3_single_put_store
        session = store.create_upload_session(key="sp-custom-key")

        # Simulate client upload
        s3_key = f"{store.prefix}_uploads/{session.upload_id}"
        store.client.put_object(
            Bucket=store.bucket,
            Key=s3_key,
            Body=SAMPLE_BYTES,
        )

        result = store.finalize_upload_session(session.upload_id)
        assert result.file_id == "sp-custom-key"
        blob = store.get("sp-custom-key")
        assert blob.data == SAMPLE_BYTES

    def test_abort_cleans_up_s3_object(self, s3_single_put_store):
        """Abort should attempt to delete the temp S3 object."""
        store = s3_single_put_store
        session = store.create_upload_session()
        s3_key = f"{store.prefix}_uploads/{session.upload_id}"

        # Simulate client upload
        store.client.put_object(Bucket=store.bucket, Key=s3_key, Body=b"discard")
        store.abort_upload_session(session.upload_id)

        # Temp object should be gone
        assert not store.exists(s3_key.removeprefix(store.prefix))
        retrieved = store.get_upload_session(session.upload_id)
        assert retrieved.status == "aborted"

    def test_finalize_already_finalized_raises(self, s3_single_put_store):
        """Finalizing an already-finalized session should raise ValueError."""
        store = s3_single_put_store
        session = store.create_upload_session(content_type="text/plain")
        s3_key = f"{store.prefix}_uploads/{session.upload_id}"
        store.client.put_object(
            Bucket=store.bucket,
            Key=s3_key,
            Body=SAMPLE_BYTES,
            ContentType="text/plain",
        )
        store.finalize_upload_session(session.upload_id)
        with pytest.raises(ValueError, match="already been finalized"):
            store.finalize_upload_session(session.upload_id)

    def test_finalize_aborted_session_raises(self, s3_single_put_store):
        """Finalizing an aborted session should raise ValueError."""
        store = s3_single_put_store
        session = store.create_upload_session()
        store.abort_upload_session(session.upload_id)
        with pytest.raises(ValueError, match="has been aborted"):
            store.finalize_upload_session(session.upload_id)


# ===================================================================
# Full lifecycle (end-to-end, proxy mode)
# ===================================================================


class TestFullLifecycle:
    def test_create_upload_finalize_download(self, proxy_blob_store: IBlobStore):
        """Full proxy lifecycle: create → upload → finalize → get blob."""
        content = b"e2e-lifecycle-test-blob"
        session = proxy_blob_store.create_upload_session(
            content_type="application/octet-stream"
        )
        proxy_blob_store.upload_to_session(session.upload_id, content, part_number=1)
        result = proxy_blob_store.finalize_upload_session(session.upload_id)
        assert result.file_id
        blob = proxy_blob_store.get(result.file_id)  # ty:ignore[invalid-argument-type]
        assert blob.data == content

    def test_create_abort_then_finalize_fails(self, proxy_blob_store: IBlobStore):
        session = proxy_blob_store.create_upload_session()
        proxy_blob_store.upload_to_session(
            session.upload_id, SAMPLE_BYTES, part_number=1
        )
        proxy_blob_store.abort_upload_session(session.upload_id)
        with pytest.raises(ValueError):
            proxy_blob_store.finalize_upload_session(session.upload_id)

    def test_multiple_sessions_independent(self, proxy_blob_store: IBlobStore):
        """Multiple concurrent sessions don't interfere with each other."""
        s1 = proxy_blob_store.create_upload_session()
        s2 = proxy_blob_store.create_upload_session()
        proxy_blob_store.upload_to_session(s1.upload_id, b"data1", part_number=1)
        proxy_blob_store.upload_to_session(s2.upload_id, b"data2", part_number=1)
        r1 = proxy_blob_store.finalize_upload_session(s1.upload_id)
        r2 = proxy_blob_store.finalize_upload_session(s2.upload_id)
        assert proxy_blob_store.get(r1.file_id).data == b"data1"  # ty:ignore[invalid-argument-type]
        assert proxy_blob_store.get(r2.file_id).data == b"data2"  # ty:ignore[invalid-argument-type]
