"""Tests for DiskBlobStore raw storage format.

DiskBlobStore should store blob data as raw bytes on disk with a sidecar
metadata file, avoiding msgpack's 4 GB encoding limit and enabling
zero-copy finalization via file rename.
"""

from autocrud.resource_manager.blob_store.simple import DiskBlobStore


class TestDiskBlobStoreRawStorage:
    """Verify DiskBlobStore stores raw bytes, not msgpack-encoded Binary."""

    def test_put_stores_raw_bytes_on_disk(self, tmp_path):
        """File on disk should be raw bytes, not msgpack-encoded Binary."""
        store = DiskBlobStore(tmp_path)
        data = b"hello world raw storage test"
        result = store.put(data)

        safe_name = result.file_id.replace("/", "_").replace("..", "_")  # ty:ignore[unresolved-attribute]
        blob_path = tmp_path / safe_name
        assert blob_path.read_bytes() == data

    def test_put_writes_metadata_sidecar(self, tmp_path):
        """A .blobmeta sidecar should be written alongside the raw file."""
        store = DiskBlobStore(tmp_path)
        data = b"sidecar test"
        result = store.put(data, content_type="text/plain")

        safe_name = result.file_id.replace("/", "_").replace("..", "_")  # ty:ignore[unresolved-attribute]
        meta_path = tmp_path / f"{safe_name}.blobmeta"
        assert meta_path.exists()

    def test_put_get_roundtrip(self, tmp_path):
        """put() followed by get() returns identical data."""
        store = DiskBlobStore(tmp_path)
        data = b"roundtrip test data " * 100
        result = store.put(data, content_type="text/plain")

        retrieved = store.get(result.file_id)  # ty:ignore[invalid-argument-type]
        assert retrieved.data == data
        assert retrieved.file_id == result.file_id
        assert retrieved.size == len(data)
        assert retrieved.content_type == "text/plain"

    def test_put_with_custom_key(self, tmp_path):
        """put() with a custom key uses that key as file_id."""
        store = DiskBlobStore(tmp_path)
        data = b"custom key test"
        result = store.put(data, key="my-blob-id")
        assert result.file_id == "my-blob-id"

        retrieved = store.get("my-blob-id")
        assert retrieved.data == data

    def test_put_hash_dedup(self, tmp_path):
        """Duplicate content (same hash key) should not re-write the file."""
        store = DiskBlobStore(tmp_path)
        data = b"dedup test data"
        r1 = store.put(data)
        r2 = store.put(data)
        assert r1.file_id == r2.file_id
        assert store.get(r1.file_id).data == data  # ty:ignore[invalid-argument-type]

    def test_exists_after_put(self, tmp_path):
        """exists() should find blobs stored via put()."""
        store = DiskBlobStore(tmp_path)
        data = b"exists test"
        result = store.put(data)
        assert store.exists(result.file_id)  # ty:ignore[invalid-argument-type]
        assert not store.exists("nonexistent")

    def test_finalize_stores_raw_bytes(self, tmp_path):
        """finalize should produce a raw-bytes blob, retrievable via get()."""
        store = DiskBlobStore(tmp_path)
        session = store.create_upload_session(total_parts=1)
        data = b"finalize raw test"
        store.upload_to_session(session.upload_id, data, part_number=1)
        result = store.finalize_upload_session(session.upload_id)

        safe_name = result.file_id.replace("/", "_").replace("..", "_")  # ty:ignore[unresolved-attribute]
        blob_path = tmp_path / safe_name
        # The blob file should contain raw bytes, NOT msgpack-encoded Binary
        assert blob_path.read_bytes() == data

        # get() should return the same data
        retrieved = store.get(result.file_id)  # ty:ignore[invalid-argument-type]
        assert retrieved.data == data

    def test_finalize_with_key_zero_copy_rename(self, tmp_path):
        """When key is provided, finalize renames .data → final (same inode)."""
        store = DiskBlobStore(tmp_path)
        session = store.create_upload_session(key="blob-key", total_parts=1)
        store.upload_to_session(session.upload_id, b"rename test", part_number=1)

        data_path = store._session_data_path(session.upload_id)
        data_inode = data_path.stat().st_ino

        result = store.finalize_upload_session(session.upload_id)
        assert result.file_id == "blob-key"

        blob_path = tmp_path / "blob-key"
        # Same inode = renamed, not copied via read+write
        assert blob_path.stat().st_ino == data_inode

    def test_finalize_multipart_raw(self, tmp_path):
        """Multi-part finalize stores concatenated raw bytes."""
        store = DiskBlobStore(tmp_path)
        session = store.create_upload_session(total_parts=3)
        uid = session.upload_id
        store.upload_to_session(uid, b"AAA", part_number=1)
        store.upload_to_session(uid, b"BBB", part_number=2)
        store.upload_to_session(uid, b"CCC", part_number=3)
        result = store.finalize_upload_session(uid)

        retrieved = store.get(result.file_id)  # ty:ignore[invalid-argument-type]
        assert retrieved.data == b"AAABBBCCC"
        assert retrieved.size == 9
