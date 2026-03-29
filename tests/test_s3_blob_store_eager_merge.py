"""Tests for S3BlobStore eager-merge algorithm and streaming finalize.

Verifies that S3BlobStore tracks part ordering (next_expected) and
uses streaming hash + server-side copy during finalization, matching
the eager-merge pattern of DiskBlobStore.
"""

from __future__ import annotations

import pytest
from xxhash import xxh3_128_hexdigest

from tests.test_blob_store_s3_session_persistence import FakeS3Client, _make_store

# ===================================================================
# Eager-merge metadata tracking
# ===================================================================


class TestS3EagerMergeTracking:
    """Verify eager-merge metadata tracking in upload_to_session."""

    def test_next_expected_advances_in_order(self):
        """Parts 1, 2, 3 uploaded in order → next_expected = 4."""
        fake = FakeS3Client()
        store = _make_store(fake, prefix="em1/")
        session = store.create_upload_session(total_parts=3)
        uid = session.upload_id

        store.upload_to_session(uid, b"AAA", part_number=1)
        meta = store._load_session(uid)
        assert meta.next_expected == 2

        store.upload_to_session(uid, b"BBB", part_number=2)
        meta = store._load_session(uid)
        assert meta.next_expected == 3

        store.upload_to_session(uid, b"CCC", part_number=3)
        meta = store._load_session(uid)
        assert meta.next_expected == 4

    def test_next_expected_advances_after_gap_fills(self):
        """Parts 3, 1, 2 → after part 2 arrives, next_expected jumps to 4."""
        fake = FakeS3Client()
        store = _make_store(fake, prefix="em2/")
        session = store.create_upload_session(total_parts=3)
        uid = session.upload_id

        store.upload_to_session(uid, b"CCC", part_number=3)
        meta = store._load_session(uid)
        assert meta.next_expected == 1  # gap at 1, 2

        store.upload_to_session(uid, b"AAA", part_number=1)
        meta = store._load_session(uid)
        assert meta.next_expected == 2  # gap at 2

        store.upload_to_session(uid, b"BBB", part_number=2)
        meta = store._load_session(uid)
        assert meta.next_expected == 4  # all consecutive

    def test_uploaded_size_accurate_on_retry(self):
        """Retrying a part must not double-count uploaded_size."""
        fake = FakeS3Client()
        store = _make_store(fake, prefix="em3/")
        session = store.create_upload_session(total_parts=2)
        uid = session.upload_id

        store.upload_to_session(uid, b"AAAA", part_number=1)  # 4 bytes
        meta = store._load_session(uid)
        assert meta.uploaded_size == 4

        # Retry part 1 with same data
        store.upload_to_session(uid, b"AAAA", part_number=1)  # still 4 bytes
        meta = store._load_session(uid)
        assert meta.uploaded_size == 4  # NOT 8

        store.upload_to_session(uid, b"BB", part_number=2)  # 2 bytes
        meta = store._load_session(uid)
        assert meta.uploaded_size == 6

    def test_uploaded_size_correct_for_retry_with_different_size(self):
        """Retry with different data size → uploaded_size reflects latest."""
        fake = FakeS3Client()
        store = _make_store(fake, prefix="em3b/")
        session = store.create_upload_session(total_parts=1)
        uid = session.upload_id

        store.upload_to_session(uid, b"AAAA", part_number=1)  # 4 bytes
        meta = store._load_session(uid)
        assert meta.uploaded_size == 4

        # Retry part 1 with different (larger) data
        store.upload_to_session(uid, b"BBBBBB", part_number=1)  # 6 bytes
        meta = store._load_session(uid)
        assert meta.uploaded_size == 6  # uses latest size, not 4+6=10

    def test_parts_received_sorted(self):
        """Out-of-order uploads → parts_received is always sorted."""
        fake = FakeS3Client()
        store = _make_store(fake, prefix="em4/")
        session = store.create_upload_session(total_parts=3)
        uid = session.upload_id

        store.upload_to_session(uid, b"C", part_number=3)
        store.upload_to_session(uid, b"A", part_number=1)
        store.upload_to_session(uid, b"B", part_number=2)

        meta = store._load_session(uid)
        assert meta.parts_received == [1, 2, 3]


# ===================================================================
# Streaming finalize (no full-object read + re-upload)
# ===================================================================


class TestS3FinalizeStreaming:
    """Verify finalize uses streaming hash + S3 server-side copy."""

    def test_finalize_without_key_correct_hash(self):
        """Content-addressed finalize: file_id = xxh3_128 hash of data."""
        fake = FakeS3Client()
        store = _make_store(fake, prefix="fs1/")
        session = store.create_upload_session(total_parts=2)
        uid = session.upload_id

        store.upload_to_session(uid, b"hello", part_number=1)
        store.upload_to_session(uid, b"world", part_number=2)
        result = store.finalize_upload_session(uid)

        expected_hash = xxh3_128_hexdigest(b"helloworld")
        assert result.file_id == expected_hash
        assert result.size == 10

        blob = store.get(result.file_id)
        assert blob.data == b"helloworld"

    def test_finalize_with_key(self):
        """Key-based finalize: file_id = key, blob accessible."""
        fake = FakeS3Client()
        store = _make_store(fake, prefix="fs2/")
        session = store.create_upload_session(key="my-blob", total_parts=1)
        uid = session.upload_id

        store.upload_to_session(uid, b"keyed data", part_number=1)
        result = store.finalize_upload_session(uid)

        assert result.file_id == "my-blob"
        assert result.size == 10

        blob = store.get("my-blob")
        assert blob.data == b"keyed data"

    def test_finalize_cleans_temp_key(self):
        """After finalize, the temp upload key in S3 is deleted."""
        fake = FakeS3Client()
        store = _make_store(fake, prefix="fs3/")
        session = store.create_upload_session(key="final-key", total_parts=1)
        uid = session.upload_id
        s3_temp_key = f"fs3/_uploads/{uid}"

        store.upload_to_session(uid, b"clean test", part_number=1)

        # Before finalize: temp key exists (after complete_multipart_upload)
        store.finalize_upload_session(uid)

        # After finalize: temp key cleaned, final key exists
        assert (store.bucket, s3_temp_key) not in fake._objects
        assert (store.bucket, "fs3/final-key") in fake._objects

    def test_finalize_out_of_order_parts(self):
        """Parts uploaded out of order → finalize produces correct data."""
        fake = FakeS3Client()
        store = _make_store(fake, prefix="fs4/")
        session = store.create_upload_session(total_parts=3)
        uid = session.upload_id

        store.upload_to_session(uid, b"CCC", part_number=3)
        store.upload_to_session(uid, b"AAA", part_number=1)
        store.upload_to_session(uid, b"BBB", part_number=2)

        result = store.finalize_upload_session(uid)
        blob = store.get(result.file_id)
        assert blob.data == b"AAABBBCCC"
        assert result.size == 9

    def test_finalize_validates_total_parts(self):
        """Finalize raises if not all parts received."""
        fake = FakeS3Client()
        store = _make_store(fake, prefix="fs5/")
        session = store.create_upload_session(total_parts=3)
        uid = session.upload_id

        store.upload_to_session(uid, b"AAA", part_number=1)
        store.upload_to_session(uid, b"BBB", part_number=2)
        # Missing part 3

        with pytest.raises(ValueError, match="Expected 3 parts but received 2"):
            store.finalize_upload_session(uid)

    def test_finalize_content_addressed_dedup(self):
        """Two sessions with same data → same file_id (content hash)."""
        fake = FakeS3Client()
        store = _make_store(fake, prefix="fs6/")
        data = b"dedup-content"

        # Session 1
        s1 = store.create_upload_session(total_parts=1)
        store.upload_to_session(s1.upload_id, data, part_number=1)
        r1 = store.finalize_upload_session(s1.upload_id)

        # Session 2 — same data
        s2 = store.create_upload_session(total_parts=1)
        store.upload_to_session(s2.upload_id, data, part_number=1)
        r2 = store.finalize_upload_session(s2.upload_id)

        assert r1.file_id == r2.file_id
        assert r1.file_id == xxh3_128_hexdigest(data)
