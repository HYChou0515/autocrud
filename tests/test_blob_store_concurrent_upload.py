"""Tests for concurrent upload_to_session — race condition prevention.

Parallel calls to ``upload_to_session`` from multiple threads must not
lose parts, corrupt ``uploaded_size``, or produce incorrect data after
finalization.

Both ``MemoryBlobStore`` (thread-pool scenario) and ``DiskBlobStore``
(multi-worker / multi-pod scenario) are covered.
"""

import threading

from autocrud.resource_manager.blob_store.simple import DiskBlobStore, MemoryBlobStore


def _run_concurrent_uploads(
    store, upload_id: str, parts: dict[int, bytes]
) -> list[tuple[int, Exception]]:
    """Launch one thread per part, all starting simultaneously via a barrier."""
    n = len(parts)
    barrier = threading.Barrier(n)
    errors: list[tuple[int, Exception]] = []

    def worker(part_num: int, data: bytes):
        try:
            barrier.wait(timeout=5)
            store.upload_to_session(upload_id, data, part_number=part_num)
        except Exception as exc:
            errors.append((part_num, exc))

    threads = [
        threading.Thread(target=worker, args=(num, data)) for num, data in parts.items()
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    return errors


# ------------------------------------------------------------------ #
# DiskBlobStore                                                        #
# ------------------------------------------------------------------ #


class TestDiskBlobStoreConcurrency:
    """DiskBlobStore must handle concurrent uploads without data loss."""

    def test_all_parts_received(self, tmp_path):
        """All part numbers are recorded even under heavy concurrency."""
        store = DiskBlobStore(tmp_path)
        n_parts = 20
        session = store.create_upload_session(total_parts=n_parts)
        uid = session.upload_id

        parts = {i: f"P{i:02d}".encode() for i in range(1, n_parts + 1)}
        errors = _run_concurrent_uploads(store, uid, parts)

        assert not errors, f"Upload errors: {errors}"
        sess = store.get_upload_session(uid)
        assert sorted(sess.parts_received) == list(range(1, n_parts + 1))

    def test_uploaded_size_consistent(self, tmp_path):
        """uploaded_size equals the sum of all part sizes after concurrent upload."""
        store = DiskBlobStore(tmp_path)
        n_parts = 20
        parts = {i: (f"D{i}" * i).encode() for i in range(1, n_parts + 1)}
        session = store.create_upload_session(total_parts=n_parts)
        uid = session.upload_id

        errors = _run_concurrent_uploads(store, uid, parts)

        assert not errors
        sess = store.get_upload_session(uid)
        expected = sum(len(d) for d in parts.values())
        assert sess.uploaded_size == expected

    def test_finalized_data_in_part_order(self, tmp_path):
        """Data is reassembled in part_number order after concurrent upload."""
        store = DiskBlobStore(tmp_path)
        n_parts = 10
        parts = {i: f"[{i}]".encode() for i in range(1, n_parts + 1)}
        session = store.create_upload_session(total_parts=n_parts)
        uid = session.upload_id

        errors = _run_concurrent_uploads(store, uid, parts)
        assert not errors

        result = store.finalize_upload_session(uid)
        blob = store.get(result.file_id)  # ty:ignore[invalid-argument-type]
        expected = b"".join(f"[{i}]".encode() for i in range(1, n_parts + 1))
        assert blob.data == expected


# ------------------------------------------------------------------ #
# MemoryBlobStore                                                      #
# ------------------------------------------------------------------ #


class TestMemoryBlobStoreConcurrency:
    """MemoryBlobStore must handle concurrent uploads without data loss."""

    def test_all_parts_received(self):
        """All part numbers are recorded even under heavy concurrency."""
        store = MemoryBlobStore()
        n_parts = 20
        session = store.create_upload_session(total_parts=n_parts)
        uid = session.upload_id

        parts = {i: f"P{i:02d}".encode() for i in range(1, n_parts + 1)}
        errors = _run_concurrent_uploads(store, uid, parts)

        assert not errors, f"Upload errors: {errors}"
        sess = store.get_upload_session(uid)
        assert sorted(sess.parts_received) == list(range(1, n_parts + 1))

    def test_uploaded_size_consistent(self):
        """uploaded_size equals the sum of all part sizes after concurrent upload."""
        store = MemoryBlobStore()
        n_parts = 20
        parts = {i: (f"D{i}" * i).encode() for i in range(1, n_parts + 1)}
        session = store.create_upload_session(total_parts=n_parts)
        uid = session.upload_id

        errors = _run_concurrent_uploads(store, uid, parts)

        assert not errors
        sess = store.get_upload_session(uid)
        expected = sum(len(d) for d in parts.values())
        assert sess.uploaded_size == expected

    def test_finalized_data_in_part_order(self):
        """Data is reassembled in part_number order after concurrent upload."""
        store = MemoryBlobStore()
        n_parts = 10
        parts = {i: f"[{i}]".encode() for i in range(1, n_parts + 1)}
        session = store.create_upload_session(total_parts=n_parts)
        uid = session.upload_id

        errors = _run_concurrent_uploads(store, uid, parts)
        assert not errors

        result = store.finalize_upload_session(uid)
        blob = store.get(result.file_id)  # ty:ignore[invalid-argument-type]
        expected = b"".join(f"[{i}]".encode() for i in range(1, n_parts + 1))
        assert blob.data == expected
