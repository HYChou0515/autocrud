import datetime as dt
from collections.abc import Generator

import pytest
from msgspec import UNSET
from xxhash import xxh3_128_hexdigest

from specstar.resource_manager.basic import IBlobStore
from specstar.resource_manager.blob_store.simple import DiskBlobStore, MemoryBlobStore
from specstar.types import Binary

# -----------------------------------------------------------------------------
# Behavior / Contract Tests
# -----------------------------------------------------------------------------


def test_fallback_content_type_guesser():
    """Test that the fallback content type guesser returns UNSET."""
    from specstar.resource_manager.blob_store.simple import (
        _fallback_content_type_guesser,
    )

    data = b"some binary data"
    content_type = _fallback_content_type_guesser(data)
    assert content_type is UNSET


def test_get_content_type_guesser_warns_when_libmagic_missing():
    """When python-magic is installed but libmagic is absent, warn and fallback."""
    import warnings
    from unittest.mock import MagicMock

    from specstar.resource_manager.blob_store import simple as mod

    # Create a fake magic module whose from_buffer raises an OSError
    # (simulates libmagic shared library not found)
    fake_magic = MagicMock()
    fake_magic.from_buffer.side_effect = OSError("failed to find libmagic")

    original_import = (
        __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__
    )

    def patched_import(name, *args, **kwargs):
        if name == "magic":
            return fake_magic
        return original_import(name, *args, **kwargs)

    import builtins

    old_import = builtins.__import__
    builtins.__import__ = patched_import  # ty:ignore[invalid-assignment]
    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            guesser = mod.get_content_type_guesser()
            # Should have emitted a warning
            assert len(w) == 1
            assert (
                "libmagic" in str(w[0].message).lower()
                or "magic" in str(w[0].message).lower()
            )
        # Guesser should be the fallback
        result = guesser(b"test data")
        assert result is UNSET
    finally:
        builtins.__import__ = old_import


@pytest.fixture(
    params=[
        "memory",
        "simple",
        pytest.param("s3", marks=pytest.mark.integration),
    ]
)
def blob_store(
    request: pytest.FixtureRequest, tmp_path: pytest.TempPathFactory
) -> Generator[IBlobStore]:
    """Fixture ensuring tests run against all `IBlobStore` implementations."""
    if request.param == "memory":
        yield MemoryBlobStore()
    elif request.param == "simple":
        yield DiskBlobStore(tmp_path / "blobs_behavior")  # ty:ignore[unsupported-operator]
    elif request.param == "s3":
        from specstar.resource_manager.blob_store.s3 import S3BlobStore

        prefix = f"{tmp_path.name}/"  # ty:ignore[unresolved-attribute]
        store = S3BlobStore(
            endpoint_url="http://localhost:9000",
            prefix=prefix,
        )
        yield store
    else:
        raise ValueError(f"Unknown blob store type: {request.param}")


class TestIBlobStoreBehavior:
    """Standard behavior tests for any class implementing IBlobStore."""

    @pytest.fixture(autouse=True)
    def setup_method(self, blob_store: IBlobStore):
        self.blob_store = blob_store

    def test_put_and_get(self):
        data = b"behavior_data_1"
        expected_hash = xxh3_128_hexdigest(data)

        # 1. Put
        file_id = self.blob_store.put(data).file_id
        assert file_id == expected_hash

        # 2. Get
        retrieved = self.blob_store.get(file_id)  # ty:ignore[invalid-argument-type]
        assert retrieved.data == data
        assert isinstance(retrieved, Binary)
        assert retrieved.file_id == file_id
        assert retrieved.size == len(data)

    def test_exists(self):
        data = b"check_existence"
        file_id = self.blob_store.put(data).file_id

        # True for existing
        assert self.blob_store.exists(file_id) is True  # ty:ignore[invalid-argument-type]

        # False for non-existing
        assert self.blob_store.exists("non_existent_id_999") is False

    def test_put_idempotency(self):
        data = b"idempotent_data"

        # First write
        file_id_1 = self.blob_store.put(data).file_id

        # Second write
        file_id_2 = self.blob_store.put(data).file_id

        assert file_id_1 == file_id_2
        # Ensure data is stillretrievable
        assert self.blob_store.get(file_id_1).data == data  # ty:ignore[invalid-argument-type]

    def test_get_not_found(self):
        with pytest.raises(FileNotFoundError):
            self.blob_store.get("missing_file_id")

    def test_multiple_files(self):
        data1 = b"file_1"
        data2 = b"file_2"

        id1 = self.blob_store.put(data1).file_id
        id2 = self.blob_store.put(data2).file_id

        assert id1 != id2
        assert self.blob_store.get(id1).data == data1  # ty:ignore[invalid-argument-type]
        assert self.blob_store.get(id2).data == data2  # ty:ignore[invalid-argument-type]

    def test_get_url_contract(self):
        """Ensure get_url returns str or None (and no error)."""
        data = b"url_check_data"
        file_id = self.blob_store.put(data).file_id

        url = self.blob_store.get_url(file_id)  # ty:ignore[invalid-argument-type]
        assert url is None or isinstance(url, str)

    def test_put_with_custom_key(self):
        """put(data, key='my-key') uses the caller-specified key as file_id."""
        data = b"custom_key_data"
        result = self.blob_store.put(data, key="my-custom-key")
        assert result.file_id == "my-custom-key"
        assert result.size == len(data)
        assert result.data == data

        # Retrievable by custom key
        retrieved = self.blob_store.get("my-custom-key")
        assert retrieved.data == data
        assert retrieved.file_id == "my-custom-key"

    def test_put_custom_key_overwrite(self):
        """put(data, key='k') with the same key overwrites the previous content."""
        key = "overwrite-key"
        data_v1 = b"version_1"
        data_v2 = b"version_2_longer"

        self.blob_store.put(data_v1, key=key)
        assert self.blob_store.get(key).data == data_v1

        # Overwrite with new data
        result = self.blob_store.put(data_v2, key=key)
        assert result.file_id == key
        assert result.size == len(data_v2)

        retrieved = self.blob_store.get(key)
        assert retrieved.data == data_v2

    def test_get_custom_key(self):
        """get() works for both hash-based and custom-keyed blobs."""
        # Hash-based
        hash_data = b"hash_based_blob"
        hash_id = self.blob_store.put(hash_data).file_id

        # Custom key
        custom_data = b"custom_keyed_blob"
        self.blob_store.put(custom_data, key="ck-get-test")

        assert self.blob_store.get(hash_id).data == hash_data  # ty:ignore[invalid-argument-type]
        assert self.blob_store.get("ck-get-test").data == custom_data

    def test_exists_custom_key(self):
        """exists() returns True for custom-keyed blobs."""
        unique_key = f"ck-exists-test-{id(self.blob_store)}"
        assert self.blob_store.exists(unique_key) is False

        self.blob_store.put(b"exists_data", key=unique_key)
        assert self.blob_store.exists(unique_key) is True


class TestIBlobStoreGarbageCollection:
    """Contract tests for the blob garbage-collection primitives (issue #370).

    Exercised against every ``IBlobStore`` implementation via the shared
    ``blob_store`` fixture.
    """

    @pytest.fixture(autouse=True)
    def setup_method(self, blob_store: IBlobStore):
        self.blob_store = blob_store

    def test_delete_removes_blob(self):
        """delete(file_id) makes the blob no longer retrievable."""
        file_id = self.blob_store.put(b"to_be_deleted").file_id

        self.blob_store.delete(file_id)

        assert self.blob_store.exists(file_id) is False
        with pytest.raises(FileNotFoundError):
            self.blob_store.get(file_id)

    def test_quarantine_lists_and_keeps_retrievable(self):
        """A quarantined blob stays readable (fall-through) and is listed by
        iter_quarantined, filtered by its recorded entry time."""
        t = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        file_id = self.blob_store.put(b"quarantined_payload").file_id

        self.blob_store.quarantine(file_id, now=t)

        # Reversible: data is not lost — get/exists fall through to quarantine.
        assert self.blob_store.get(file_id).data == b"quarantined_payload"
        assert self.blob_store.exists(file_id) is True

        # Listed when the cutoff is after its entry time, not before.
        after = set(
            self.blob_store.iter_quarantined(entered_before=t + dt.timedelta(seconds=1))
        )
        before = set(
            self.blob_store.iter_quarantined(entered_before=t - dt.timedelta(seconds=1))
        )
        assert file_id in after
        assert file_id not in before

    def test_restore_from_quarantine_brings_back_to_active(self):
        """restore_from_quarantine moves a blob back to active; it leaves the
        quarantine listing and stays retrievable."""
        t = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        file_id = self.blob_store.put(b"resurrect_me").file_id
        self.blob_store.quarantine(file_id, now=t)

        self.blob_store.restore_from_quarantine(file_id)

        assert self.blob_store.get(file_id).data == b"resurrect_me"
        listed = set(
            self.blob_store.iter_quarantined(entered_before=t + dt.timedelta(days=999))
        )
        assert file_id not in listed

    def test_delete_removes_quarantined_blob(self):
        """delete() removes a blob even while it sits in quarantine."""
        t = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        file_id = self.blob_store.put(b"quarantined_then_deleted").file_id
        self.blob_store.quarantine(file_id, now=t)

        self.blob_store.delete(file_id)

        assert self.blob_store.exists(file_id) is False
        assert file_id not in set(
            self.blob_store.iter_quarantined(entered_before=t + dt.timedelta(days=999))
        )

    def test_incref_decref_track_count(self):
        """incref/decref return the adjusted approximate count; decref clamps at 0."""
        file_id = self.blob_store.put(b"counted").file_id

        assert self.blob_store.incref(file_id) == 1
        assert self.blob_store.incref(file_id) == 2
        assert self.blob_store.decref(file_id) == 1
        assert self.blob_store.decref(file_id) == 0
        # Approximate / best-effort: never goes negative.
        assert self.blob_store.decref(file_id) == 0

    def test_iter_active_lists_active_blobs_only(self):
        """iter_active yields active file_ids and excludes quarantined ones."""
        t = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        active_id = self.blob_store.put(b"i_am_active").file_id
        quarantined_id = self.blob_store.put(b"i_am_quarantined").file_id
        self.blob_store.quarantine(quarantined_id, now=t)

        active = set(self.blob_store.iter_active())

        assert active_id in active
        assert quarantined_id not in active

    def test_get_mtime_reports_recent_write_time(self):
        """get_mtime returns the blob's last-write time (≈ now at put)."""
        before = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=5)
        file_id = self.blob_store.put(b"freshly_written").file_id
        after = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=5)

        mtime = self.blob_store.get_mtime(file_id)

        assert mtime is not None
        assert before <= mtime <= after

    def test_get_mtime_missing_returns_none(self):
        assert self.blob_store.get_mtime("no-such-blob-xyz") is None

    def test_touch_advances_mtime(self):
        """touch refreshes the blob's mtime forward."""
        file_id = self.blob_store.put(b"touch_me").file_id
        m0 = self.blob_store.get_mtime(file_id)
        assert m0 is not None

        self.blob_store.touch(file_id, now=m0 + dt.timedelta(hours=1))

        m1 = self.blob_store.get_mtime(file_id)
        assert m1 is not None
        assert m1 > m0

    def test_decref_to_zero_makes_orphan_candidate(self):
        """A blob whose count drops to <=0 becomes an orphan candidate eligible
        for the incremental pass (once older than the modified_before cutoff)."""
        file_id = self.blob_store.put(b"candidate").file_id
        self.blob_store.incref(file_id)
        self.blob_store.decref(file_id)  # back to 0 -> candidate

        cutoff = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
        candidates = set(self.blob_store.iter_orphan_candidates(modified_before=cutoff))
        assert file_id in candidates

    def test_incref_clears_orphan_candidate(self):
        """A re-referenced blob is no longer an orphan candidate."""
        file_id = self.blob_store.put(b"recandidate").file_id
        self.blob_store.decref(file_id)  # 0 -> candidate
        self.blob_store.incref(file_id)  # 1 -> cleared

        cutoff = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
        candidates = set(self.blob_store.iter_orphan_candidates(modified_before=cutoff))
        assert file_id not in candidates

    def test_fresh_orphan_candidate_excluded_by_cutoff(self):
        """A candidate written after the cutoff (too fresh) is not yielded —
        this is the T1 grace at the blob-store level."""
        file_id = self.blob_store.put(b"fresh_candidate").file_id
        self.blob_store.decref(file_id)  # candidate

        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
        candidates = set(self.blob_store.iter_orphan_candidates(modified_before=cutoff))
        assert file_id not in candidates
