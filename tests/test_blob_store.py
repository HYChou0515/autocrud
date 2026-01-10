import pytest
from autocrud.resource_manager.basic import IBlobStore
from autocrud.resource_manager.blob_store.simple import DiskBlobStore, MemoryBlobStore
from xxhash import xxh3_128_hexdigest

# -----------------------------------------------------------------------------
# Behavior / Contract Tests
# -----------------------------------------------------------------------------


@pytest.fixture(params=["memory", "simple"])
def blob_store(
    request: pytest.FixtureRequest, tmp_path: pytest.TempPathFactory
) -> IBlobStore:
    """Fixture ensuring tests run against all `IBlobStore` implementations."""
    if request.param == "memory":
        return MemoryBlobStore()
    elif request.param == "simple":
        return DiskBlobStore(tmp_path / "blobs_behavior")
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
        file_id = self.blob_store.put(data)
        assert file_id == expected_hash

        # 2. Get
        retrieved = self.blob_store.get(file_id)
        assert retrieved == data
        assert isinstance(retrieved, bytes)

    def test_exists(self):
        data = b"check_existence"
        file_id = self.blob_store.put(data)

        # True for existing
        assert self.blob_store.exists(file_id) is True

        # False for non-existing
        assert self.blob_store.exists("non_existent_id_999") is False

    def test_put_idempotency(self):
        data = b"idempotent_data"

        # First write
        file_id_1 = self.blob_store.put(data)

        # Second write
        file_id_2 = self.blob_store.put(data)

        assert file_id_1 == file_id_2
        # Ensure data is stillretrievable
        assert self.blob_store.get(file_id_1) == data

    def test_get_not_found(self):
        with pytest.raises(FileNotFoundError):
            self.blob_store.get("missing_file_id")

    def test_multiple_files(self):
        data1 = b"file_1"
        data2 = b"file_2"

        id1 = self.blob_store.put(data1)
        id2 = self.blob_store.put(data2)

        assert id1 != id2
        assert self.blob_store.get(id1) == data1
        assert self.blob_store.get(id2) == data2
