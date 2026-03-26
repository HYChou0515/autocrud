"""Tests for S3BlobStore cross-instance session persistence (HPA-safe).

Upload session state is persisted to S3 rather than kept in memory,
allowing any S3BlobStore instance sharing the same bucket/prefix to
access sessions created by other instances.  This is critical for
Horizontal Pod Autoscaler (HPA) and multi-instance deployments.
"""

from __future__ import annotations

import io
from typing import Any
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError

from autocrud.resource_manager.blob_store.s3 import S3BlobStore

SAMPLE_BYTES = b"cross-instance-test-data"


# ---------------------------------------------------------------------------
# FakeS3Client — shared in-memory S3 that multiple stores can use
# ---------------------------------------------------------------------------


class FakeS3Client:
    """Minimal in-memory S3 client that simulates shared S3 storage.

    Create a single instance and inject it into multiple ``S3BlobStore``
    objects to simulate the HPA scenario where pods share the same S3.
    """

    def __init__(self) -> None:
        self._objects: dict[tuple[str, str], dict[str, Any]] = {}

    # -- Bucket ops --------------------------------------------------------

    def head_bucket(self, **kwargs: Any) -> dict:
        return {}

    def create_bucket(self, **kwargs: Any) -> None:
        pass

    # -- Object ops --------------------------------------------------------

    def put_object(self, **kwargs: Any) -> None:
        bucket, key = kwargs["Bucket"], kwargs["Key"]
        body = kwargs["Body"]
        if isinstance(body, (bytes, bytearray)):
            body = bytes(body)
        self._objects[(bucket, key)] = {
            "Body": body,
            "ContentType": kwargs.get("ContentType"),
            "ContentLength": len(body),
        }

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        bucket, key = kwargs["Bucket"], kwargs["Key"]
        obj = self._objects.get((bucket, key))
        if obj is None:
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}},
                "GetObject",
            )
        body = obj["Body"]
        return {
            "Body": io.BytesIO(body) if isinstance(body, bytes) else body,
            "ContentType": obj.get("ContentType"),
            "ContentLength": obj.get("ContentLength", 0),
        }

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        bucket, key = kwargs["Bucket"], kwargs["Key"]
        obj = self._objects.get((bucket, key))
        if obj is None:
            raise ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadObject",
            )
        return {
            "ContentType": obj.get("ContentType"),
            "ContentLength": obj.get("ContentLength", 0),
        }

    def delete_object(self, **kwargs: Any) -> None:
        bucket, key = kwargs["Bucket"], kwargs["Key"]
        self._objects.pop((bucket, key), None)

    def copy_object(self, **kwargs: Any) -> None:
        bucket, key = kwargs["Bucket"], kwargs["Key"]
        src = kwargs["CopySource"]
        src_key = (src["Bucket"], src["Key"])
        if src_key not in self._objects:
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}},
                "CopyObject",
            )
        self._objects[(bucket, key)] = dict(self._objects[src_key])

    def generate_presigned_url(
        self,
        ClientMethod: str | None = None,
        Params: dict | None = None,
        ExpiresIn: int = 3600,
    ) -> str:
        params = Params or {}
        return (
            f"http://fake-s3/{params.get('Bucket')}"
            f"/{params.get('Key')}?presigned&expires={ExpiresIn}"
        )


# ---------------------------------------------------------------------------
# Helper: create S3BlobStore with injected FakeS3Client
# ---------------------------------------------------------------------------


def _make_store(
    fake_client: FakeS3Client,
    prefix: str = "test/",
    upload_method: str = "proxy",
) -> S3BlobStore:
    """Create an S3BlobStore backed by the given FakeS3Client."""
    with patch("boto3.client", return_value=fake_client):
        return S3BlobStore(prefix=prefix, upload_method=upload_method)


# ===================================================================
# Cross-instance session access — proxy mode (HPA scenario)
# ===================================================================


class TestCrossInstanceProxy:
    """Proxy mode: sessions created on one instance are accessible
    from another instance sharing the same bucket/prefix."""

    def test_get_session_from_different_instance(self):
        fake = FakeS3Client()
        store_a = _make_store(fake, prefix="a/")
        store_b = _make_store(fake, prefix="a/")

        session = store_a.create_upload_session(
            content_type="text/plain",
            size=100,
        )
        retrieved = store_b.get_upload_session(session.upload_id)

        assert retrieved.upload_id == session.upload_id
        assert retrieved.status == "pending"
        assert retrieved.content_type == "text/plain"
        assert retrieved.size == 100

    def test_upload_on_b_finalize_on_a(self):
        fake = FakeS3Client()
        store_a = _make_store(fake, prefix="b/")
        store_b = _make_store(fake, prefix="b/")

        session = store_a.create_upload_session(content_type="text/plain")
        store_b.upload_to_session(session.upload_id, SAMPLE_BYTES)
        result = store_a.finalize_upload_session(session.upload_id)

        assert result.file_id
        assert result.size == len(SAMPLE_BYTES)
        blob = store_b.get(result.file_id)
        assert blob.data == SAMPLE_BYTES

    def test_abort_from_different_instance(self):
        fake = FakeS3Client()
        store_a = _make_store(fake, prefix="c/")
        store_b = _make_store(fake, prefix="c/")

        session = store_a.create_upload_session()
        store_b.abort_upload_session(session.upload_id)
        retrieved = store_a.get_upload_session(session.upload_id)
        assert retrieved.status == "aborted"

    def test_status_transitions_visible_cross_instance(self):
        fake = FakeS3Client()
        store_a = _make_store(fake, prefix="d/")
        store_b = _make_store(fake, prefix="d/")

        session = store_a.create_upload_session()
        assert store_b.get_upload_session(session.upload_id).status == "pending"

        store_a.upload_to_session(session.upload_id, SAMPLE_BYTES)
        assert store_b.get_upload_session(session.upload_id).status == "uploaded"

        store_a.finalize_upload_session(session.upload_id)
        assert store_b.get_upload_session(session.upload_id).status == "finalized"

    def test_finalize_with_custom_key_cross_instance(self):
        fake = FakeS3Client()
        store_a = _make_store(fake, prefix="e/")
        store_b = _make_store(fake, prefix="e/")

        session = store_a.create_upload_session(
            key="custom-blob-key",
            content_type="text/plain",
        )
        store_b.upload_to_session(session.upload_id, SAMPLE_BYTES)
        result = store_a.finalize_upload_session(session.upload_id)
        assert result.file_id == "custom-blob-key"
        blob = store_b.get("custom-blob-key")
        assert blob.data == SAMPLE_BYTES


# ===================================================================
# Cross-instance session access — single_put mode
# ===================================================================


class TestCrossInstanceSinglePut:
    """Single-put mode: sessions work across instances."""

    def test_get_session_from_different_instance(self):
        fake = FakeS3Client()
        store_a = _make_store(fake, prefix="sp1/", upload_method="single_put")
        store_b = _make_store(fake, prefix="sp1/", upload_method="single_put")

        session = store_a.create_upload_session(content_type="text/plain")
        retrieved = store_b.get_upload_session(session.upload_id)
        assert retrieved.upload_id == session.upload_id
        assert retrieved.status == "pending"

    def test_finalize_from_different_instance(self):
        fake = FakeS3Client()
        store_a = _make_store(fake, prefix="sp2/", upload_method="single_put")
        store_b = _make_store(fake, prefix="sp2/", upload_method="single_put")

        session = store_a.create_upload_session(content_type="text/plain")
        # Simulate client uploading directly to S3 temp key
        s3_key = f"sp2/_uploads/{session.upload_id}"
        fake.put_object(
            Bucket=store_a.bucket,
            Key=s3_key,
            Body=SAMPLE_BYTES,
            ContentType="text/plain",
        )

        result = store_b.finalize_upload_session(session.upload_id)
        assert result.file_id
        assert result.size == len(SAMPLE_BYTES)

    def test_abort_from_different_instance(self):
        fake = FakeS3Client()
        store_a = _make_store(fake, prefix="sp3/", upload_method="single_put")
        store_b = _make_store(fake, prefix="sp3/", upload_method="single_put")

        session = store_a.create_upload_session()
        store_b.abort_upload_session(session.upload_id)
        retrieved = store_a.get_upload_session(session.upload_id)
        assert retrieved.status == "aborted"


# ===================================================================
# Single-instance regressions (ensure no breakage)
# ===================================================================


class TestSingleInstanceProxy:
    """Proxy-mode operations with a single instance (regression)."""

    def test_full_lifecycle(self):
        fake = FakeS3Client()
        store = _make_store(fake, prefix="si/")

        session = store.create_upload_session(content_type="text/plain")
        assert session.status == "pending"
        assert session.upload_method == "proxy"

        store.upload_to_session(session.upload_id, SAMPLE_BYTES)
        retrieved = store.get_upload_session(session.upload_id)
        assert retrieved.status == "uploaded"
        assert retrieved.size == len(SAMPLE_BYTES)

        result = store.finalize_upload_session(session.upload_id)
        assert result.file_id
        assert result.size == len(SAMPLE_BYTES)
        blob = store.get(result.file_id)
        assert blob.data == SAMPLE_BYTES

    def test_not_found_session(self):
        fake = FakeS3Client()
        store = _make_store(fake, prefix="nf/")
        with pytest.raises(FileNotFoundError):
            store.get_upload_session("nonexistent")

    def test_cannot_upload_twice(self):
        fake = FakeS3Client()
        store = _make_store(fake, prefix="ut/")

        session = store.create_upload_session()
        store.upload_to_session(session.upload_id, b"first")
        with pytest.raises(ValueError, match="uploaded"):
            store.upload_to_session(session.upload_id, b"second")

    def test_abort_then_finalize_fails(self):
        fake = FakeS3Client()
        store = _make_store(fake, prefix="af/")

        session = store.create_upload_session()
        store.upload_to_session(session.upload_id, SAMPLE_BYTES)
        store.abort_upload_session(session.upload_id)
        with pytest.raises(ValueError, match="aborted"):
            store.finalize_upload_session(session.upload_id)

    def test_finalize_without_upload_raises(self):
        fake = FakeS3Client()
        store = _make_store(fake, prefix="fu/")

        session = store.create_upload_session()
        with pytest.raises(ValueError, match="pending"):
            store.finalize_upload_session(session.upload_id)

    def test_abort_finalized_raises(self):
        fake = FakeS3Client()
        store = _make_store(fake, prefix="abf/")

        session = store.create_upload_session()
        store.upload_to_session(session.upload_id, SAMPLE_BYTES)
        store.finalize_upload_session(session.upload_id)
        with pytest.raises(ValueError, match="finalized"):
            store.abort_upload_session(session.upload_id)


class TestSingleInstanceSinglePut:
    """Single-put mode operations with a single instance (regression)."""

    def test_full_lifecycle(self):
        fake = FakeS3Client()
        store = _make_store(fake, prefix="ssp/", upload_method="single_put")

        session = store.create_upload_session(content_type="text/plain")
        assert session.status == "pending"
        assert session.upload_method == "single_put"
        assert session.upload_url.startswith("http")

        # Simulate client upload via presigned URL
        s3_key = f"ssp/_uploads/{session.upload_id}"
        fake.put_object(
            Bucket=store.bucket,
            Key=s3_key,
            Body=SAMPLE_BYTES,
            ContentType="text/plain",
        )

        result = store.finalize_upload_session(session.upload_id)
        assert result.file_id
        assert result.size == len(SAMPLE_BYTES)

    def test_finalize_without_client_upload_raises(self):
        fake = FakeS3Client()
        store = _make_store(fake, prefix="ssnc/", upload_method="single_put")

        session = store.create_upload_session()
        with pytest.raises(ValueError, match="not found|not uploaded"):
            store.finalize_upload_session(session.upload_id)

    def test_upload_to_session_raises_not_implemented(self):
        fake = FakeS3Client()
        store = _make_store(fake, prefix="ssni/", upload_method="single_put")

        session = store.create_upload_session()
        with pytest.raises(NotImplementedError, match="single_put"):
            store.upload_to_session(session.upload_id, b"data")

    def test_finalize_already_finalized_raises(self):
        fake = FakeS3Client()
        store = _make_store(fake, prefix="ssff/", upload_method="single_put")

        session = store.create_upload_session()
        s3_key = f"ssff/_uploads/{session.upload_id}"
        fake.put_object(Bucket=store.bucket, Key=s3_key, Body=SAMPLE_BYTES)
        store.finalize_upload_session(session.upload_id)
        with pytest.raises(ValueError, match="already been finalized"):
            store.finalize_upload_session(session.upload_id)

    def test_finalize_aborted_raises(self):
        fake = FakeS3Client()
        store = _make_store(fake, prefix="ssfa/", upload_method="single_put")

        session = store.create_upload_session()
        store.abort_upload_session(session.upload_id)
        with pytest.raises(ValueError, match="has been aborted"):
            store.finalize_upload_session(session.upload_id)

    def test_finalize_with_custom_key(self):
        fake = FakeS3Client()
        store = _make_store(fake, prefix="ssck/", upload_method="single_put")

        session = store.create_upload_session(key="my-sp-key")
        s3_key = f"ssck/_uploads/{session.upload_id}"
        fake.put_object(Bucket=store.bucket, Key=s3_key, Body=SAMPLE_BYTES)

        result = store.finalize_upload_session(session.upload_id)
        assert result.file_id == "my-sp-key"
        blob = store.get("my-sp-key")
        assert blob.data == SAMPLE_BYTES

    def test_abort_cleans_up_s3_object(self):
        fake = FakeS3Client()
        store = _make_store(fake, prefix="ssab/", upload_method="single_put")

        session = store.create_upload_session()
        s3_key = f"ssab/_uploads/{session.upload_id}"
        fake.put_object(Bucket=store.bucket, Key=s3_key, Body=b"discard")

        store.abort_upload_session(session.upload_id)
        # Temp object should be cleaned up
        file_id = s3_key.removeprefix(store.prefix)
        assert not store.exists(file_id)
        retrieved = store.get_upload_session(session.upload_id)
        assert retrieved.status == "aborted"
