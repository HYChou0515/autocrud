"""Tests for parallel chunked upload with part_number and eager-merge.

Verifies:
- Out-of-order part arrival with eager merge
- total_parts validation at finalize
- Idempotent retry semantics
- parts_received tracking
- Gap detection (finalize with missing parts)
- part_number validation (< 1)
"""

from collections.abc import Generator

import pytest

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
        yield DiskBlobStore(tmp_path / "blobs_parallel")  # ty:ignore[unsupported-operator]
    else:
        raise ValueError(f"Unknown: {request.param}")


# Parts for testing
PART_A = b"AAAA"  # 4 bytes
PART_B = b"BBBBBBBB"  # 8 bytes
PART_C = b"CCCC"  # 4 bytes
PART_D = b"DD"  # 2 bytes
PART_E = b"EEEEE"  # 5 bytes
ALL_5_PARTS = PART_A + PART_B + PART_C + PART_D + PART_E


# ---------------------------------------------------------------------------
# Out-of-order arrival + eager merge
# ---------------------------------------------------------------------------


class TestOutOfOrderUpload:
    """Parts arrive out of order and the eager merge assembles them correctly."""

    def test_out_of_order_3_parts(self, blob_store: IBlobStore):
        """Arrival order: 1, 3, 2 → data must be PART_A + PART_B + PART_C."""
        session = blob_store.create_upload_session(total_parts=3)
        uid = session.upload_id

        blob_store.upload_to_session(uid, PART_A, part_number=1)
        blob_store.upload_to_session(uid, PART_C, part_number=3)  # buffered
        blob_store.upload_to_session(uid, PART_B, part_number=2)  # triggers chain flush

        result = blob_store.finalize_upload_session(uid)
        stored = blob_store.get(result.file_id)  # ty:ignore[invalid-argument-type]
        assert stored.data == PART_A + PART_B + PART_C

    def test_out_of_order_5_parts(self, blob_store: IBlobStore):
        """Arrival order: 1, 3, 5, 2, 4 → all 5 parts assembled in order."""
        session = blob_store.create_upload_session(total_parts=5)
        uid = session.upload_id

        blob_store.upload_to_session(uid, PART_A, part_number=1)
        blob_store.upload_to_session(uid, PART_C, part_number=3)
        blob_store.upload_to_session(uid, PART_E, part_number=5)
        blob_store.upload_to_session(uid, PART_B, part_number=2)  # flushes 2, 3
        blob_store.upload_to_session(uid, PART_D, part_number=4)  # flushes 4, 5

        result = blob_store.finalize_upload_session(uid)
        stored = blob_store.get(result.file_id)  # ty:ignore[invalid-argument-type]
        assert stored.data == ALL_5_PARTS

    def test_reverse_order(self, blob_store: IBlobStore):
        """Parts arrive in reverse: 3, 2, 1 → assembled correctly."""
        session = blob_store.create_upload_session(total_parts=3)
        uid = session.upload_id

        blob_store.upload_to_session(uid, PART_C, part_number=3)
        blob_store.upload_to_session(uid, PART_B, part_number=2)
        blob_store.upload_to_session(uid, PART_A, part_number=1)  # triggers full flush

        result = blob_store.finalize_upload_session(uid)
        stored = blob_store.get(result.file_id)  # ty:ignore[invalid-argument-type]
        assert stored.data == PART_A + PART_B + PART_C

    def test_uploaded_size_tracks_all_parts(self, blob_store: IBlobStore):
        """uploaded_size accumulates all received bytes regardless of order."""
        session = blob_store.create_upload_session()
        uid = session.upload_id

        blob_store.upload_to_session(uid, PART_C, part_number=3)
        s = blob_store.get_upload_session(uid)
        assert s.uploaded_size == len(PART_C)

        blob_store.upload_to_session(uid, PART_A, part_number=1)
        s = blob_store.get_upload_session(uid)
        assert s.uploaded_size == len(PART_A) + len(PART_C)


# ---------------------------------------------------------------------------
# parts_received tracking
# ---------------------------------------------------------------------------


class TestPartsReceived:
    """parts_received returns a sorted list of received part numbers."""

    def test_parts_received_in_order(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session()
        uid = session.upload_id

        blob_store.upload_to_session(uid, PART_A, part_number=1)
        s = blob_store.get_upload_session(uid)
        assert s.parts_received == [1]

        blob_store.upload_to_session(uid, PART_B, part_number=2)
        s = blob_store.get_upload_session(uid)
        assert s.parts_received == [1, 2]

    def test_parts_received_out_of_order(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session()
        uid = session.upload_id

        blob_store.upload_to_session(uid, PART_C, part_number=3)
        blob_store.upload_to_session(uid, PART_A, part_number=1)
        s = blob_store.get_upload_session(uid)
        assert s.parts_received == [1, 3]

    def test_parts_received_empty_initially(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session()
        s = blob_store.get_upload_session(session.upload_id)
        assert s.parts_received == []


# ---------------------------------------------------------------------------
# total_parts validation
# ---------------------------------------------------------------------------


class TestTotalPartsValidation:
    """total_parts is validated at finalize time."""

    def test_total_parts_match_succeeds(self, blob_store: IBlobStore):
        """Exactly total_parts parts received → finalize succeeds."""
        session = blob_store.create_upload_session(total_parts=2)
        uid = session.upload_id
        blob_store.upload_to_session(uid, PART_A, part_number=1)
        blob_store.upload_to_session(uid, PART_B, part_number=2)
        result = blob_store.finalize_upload_session(uid)
        assert result.size == len(PART_A) + len(PART_B)

    def test_total_parts_mismatch_raises(self, blob_store: IBlobStore):
        """Fewer parts than total_parts → ValueError at finalize."""
        session = blob_store.create_upload_session(total_parts=3)
        uid = session.upload_id
        blob_store.upload_to_session(uid, PART_A, part_number=1)
        blob_store.upload_to_session(uid, PART_B, part_number=2)
        with pytest.raises(ValueError, match="Expected 3 parts but received 2"):
            blob_store.finalize_upload_session(uid)

    def test_total_parts_none_skips_validation(self, blob_store: IBlobStore):
        """total_parts=None → no validation, any number of parts accepted."""
        session = blob_store.create_upload_session(total_parts=None)
        uid = session.upload_id
        blob_store.upload_to_session(uid, PART_A, part_number=1)
        result = blob_store.finalize_upload_session(uid)
        assert result.size == len(PART_A)

    def test_total_parts_preserved_in_session(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session(total_parts=5)
        s = blob_store.get_upload_session(session.upload_id)
        assert s.total_parts == 5


# ---------------------------------------------------------------------------
# Idempotent retry
# ---------------------------------------------------------------------------


class TestIdempotentRetry:
    """Retrying the same part_number is safe and idempotent."""

    def test_retry_already_merged_part_ignored(self, blob_store: IBlobStore):
        """Re-sending an already-merged part is silently ignored."""
        session = blob_store.create_upload_session(total_parts=2)
        uid = session.upload_id

        blob_store.upload_to_session(uid, PART_A, part_number=1)
        blob_store.upload_to_session(uid, PART_B, part_number=2)

        # Retry part 1 — already merged, should be ignored
        blob_store.upload_to_session(uid, b"XXXX", part_number=1)

        result = blob_store.finalize_upload_session(uid)
        stored = blob_store.get(result.file_id)  # ty:ignore[invalid-argument-type]
        # Data should be original PART_A + PART_B, not the retry bytes
        assert stored.data == PART_A + PART_B

    def test_retry_buffered_part_overwritten(self, blob_store: IBlobStore):
        """Re-sending a buffered (out-of-order) part overwrites it."""
        session = blob_store.create_upload_session(total_parts=2)
        uid = session.upload_id

        blob_store.upload_to_session(uid, b"old_data", part_number=2)  # buffered
        blob_store.upload_to_session(uid, PART_B, part_number=2)  # overwrite

        blob_store.upload_to_session(uid, PART_A, part_number=1)  # triggers flush

        result = blob_store.finalize_upload_session(uid)
        stored = blob_store.get(result.file_id)  # ty:ignore[invalid-argument-type]
        assert stored.data == PART_A + PART_B  # uses the retry data


# ---------------------------------------------------------------------------
# Gap detection (finalize with missing parts)
# ---------------------------------------------------------------------------


class TestGapDetection:
    """Finalize raises if there are buffered parts (missing earlier parts)."""

    def test_finalize_with_gap_raises(self, blob_store: IBlobStore):
        """Parts 1 and 3 received, part 2 missing → finalize raises."""
        session = blob_store.create_upload_session()
        uid = session.upload_id

        blob_store.upload_to_session(uid, PART_A, part_number=1)
        blob_store.upload_to_session(uid, PART_C, part_number=3)

        with pytest.raises(ValueError, match="buffered"):
            blob_store.finalize_upload_session(uid)


# ---------------------------------------------------------------------------
# part_number validation
# ---------------------------------------------------------------------------


class TestPartNumberValidation:
    """part_number must be >= 1."""

    def test_part_number_zero_raises(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session()
        with pytest.raises(ValueError, match="part_number must be >= 1"):
            blob_store.upload_to_session(session.upload_id, PART_A, part_number=0)

    def test_part_number_negative_raises(self, blob_store: IBlobStore):
        session = blob_store.create_upload_session()
        with pytest.raises(ValueError, match="part_number must be >= 1"):
            blob_store.upload_to_session(session.upload_id, PART_A, part_number=-1)
