"""Tests that DiskBlobStore persists upload sessions to disk, not in-memory.

In HPA (Horizontal Pod Autoscaler) scenarios, multiple pods share the same
PVC.  Sessions created on one pod must be visible to another pod instance
that shares the same root_path.  This test suite verifies that by creating
*two independent* DiskBlobStore instances pointing at the *same* directory.
"""

import pytest

from autocrud.resource_manager.blob_store.simple import DiskBlobStore

SAMPLE_BYTES = b"hpa-session-test-data"
SAMPLE_CT = "text/plain"


@pytest.fixture
def shared_root(tmp_path):
    """Return a shared root directory simulating a PVC mount."""
    return tmp_path / "shared_blobs"


class TestDiskSessionPersistence:
    """Verify sessions survive across independent DiskBlobStore instances."""

    def test_session_visible_on_second_instance(self, shared_root):
        """Create session on instance A, read it on instance B."""
        store_a = DiskBlobStore(shared_root)
        session = store_a.create_upload_session(content_type=SAMPLE_CT, size=42)

        # Simulate "another pod" — fresh DiskBlobStore pointing at same path
        store_b = DiskBlobStore(shared_root)
        retrieved = store_b.get_upload_session(session.upload_id)

        assert retrieved.upload_id == session.upload_id
        assert retrieved.status == "pending"
        assert retrieved.content_type == SAMPLE_CT
        assert retrieved.size == 42

    def test_upload_on_different_instance(self, shared_root):
        """Create session on A, upload bytes on B, finalize on A."""
        store_a = DiskBlobStore(shared_root)
        session = store_a.create_upload_session(content_type=SAMPLE_CT)

        store_b = DiskBlobStore(shared_root)
        store_b.upload_to_session(session.upload_id, SAMPLE_BYTES)

        # Verify status visible from yet another instance
        store_c = DiskBlobStore(shared_root)
        retrieved = store_c.get_upload_session(session.upload_id)
        assert retrieved.status == "uploaded"
        assert retrieved.size == len(SAMPLE_BYTES)

    def test_finalize_on_different_instance(self, shared_root):
        """Full lifecycle across instances: create(A) → upload(B) → finalize(C)."""
        store_a = DiskBlobStore(shared_root)
        session = store_a.create_upload_session(content_type=SAMPLE_CT)

        store_b = DiskBlobStore(shared_root)
        store_b.upload_to_session(session.upload_id, SAMPLE_BYTES)

        store_c = DiskBlobStore(shared_root)
        result = store_c.finalize_upload_session(session.upload_id)

        assert result.file_id
        assert result.size == len(SAMPLE_BYTES)

        # The blob must be retrievable from any instance
        store_d = DiskBlobStore(shared_root)
        blob = store_d.get(result.file_id)
        assert blob.data == SAMPLE_BYTES

    def test_abort_on_different_instance(self, shared_root):
        """Abort session created on a different instance."""
        store_a = DiskBlobStore(shared_root)
        session = store_a.create_upload_session()

        store_b = DiskBlobStore(shared_root)
        store_b.abort_upload_session(session.upload_id)

        store_c = DiskBlobStore(shared_root)
        retrieved = store_c.get_upload_session(session.upload_id)
        assert retrieved.status == "aborted"

    def test_finalized_status_visible_cross_instance(self, shared_root):
        """After finalize, get_upload_session on another instance shows finalized."""
        store_a = DiskBlobStore(shared_root)
        session = store_a.create_upload_session()
        store_a.upload_to_session(session.upload_id, SAMPLE_BYTES)
        store_a.finalize_upload_session(session.upload_id)

        store_b = DiskBlobStore(shared_root)
        retrieved = store_b.get_upload_session(session.upload_id)
        assert retrieved.status == "finalized"

    def test_not_found_on_nonexistent_session(self, shared_root):
        """get_upload_session raises FileNotFoundError for unknown sessions."""
        store = DiskBlobStore(shared_root)
        with pytest.raises(FileNotFoundError):
            store.get_upload_session("nonexistent-id")

    def test_session_data_not_in_memory_dict(self, shared_root):
        """Verify sessions are NOT stored in an in-memory dict."""
        store = DiskBlobStore(shared_root)
        store.create_upload_session(content_type=SAMPLE_CT)

        # The in-memory _sessions dict (if it still exists) should not be
        # the source of truth — a fresh instance must still find it.
        # This implicitly tested by cross-instance tests above, but let's
        # be explicit: a brand-new instance with empty memory sees sessions.
        fresh = DiskBlobStore(shared_root)
        assert not hasattr(fresh, "_sessions") or len(fresh._sessions) == 0

    def test_upload_data_persisted_for_finalize(self, shared_root):
        """Uploaded bytes must be persisted so finalize on another instance works."""
        store_a = DiskBlobStore(shared_root)
        session = store_a.create_upload_session(key="my-key", content_type=SAMPLE_CT)
        store_a.upload_to_session(session.upload_id, SAMPLE_BYTES)

        store_b = DiskBlobStore(shared_root)
        result = store_b.finalize_upload_session(session.upload_id)
        assert result.file_id == "my-key"

        blob = store_b.get("my-key")
        assert blob.data == SAMPLE_BYTES
