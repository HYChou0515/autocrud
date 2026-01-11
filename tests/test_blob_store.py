from collections.abc import Generator
from msgspec import UNSET
import pytest
from autocrud.resource_manager.basic import IBlobStore
from autocrud.resource_manager.blob_store.simple import DiskBlobStore, MemoryBlobStore
from autocrud.types import Binary
from xxhash import xxh3_128_hexdigest

# -----------------------------------------------------------------------------
# Behavior / Contract Tests
# -----------------------------------------------------------------------------


def test_fallback_content_type_guesser():
    """Test that the fallback content type guesser returns UNSET."""
    from autocrud.resource_manager.blob_store.simple import (
        _fallback_content_type_guesser,
    )

    data = b"some binary data"
    content_type = _fallback_content_type_guesser(data)
    assert content_type is UNSET


@pytest.fixture(params=["memory", "simple", "s3"])
def blob_store(
    request: pytest.FixtureRequest, tmp_path: pytest.TempPathFactory
) -> Generator[IBlobStore]:
    """Fixture ensuring tests run against all `IBlobStore` implementations."""
    if request.param == "memory":
        yield MemoryBlobStore()
    elif request.param == "simple":
        yield DiskBlobStore(tmp_path / "blobs_behavior")
    elif request.param == "s3":
        from autocrud.resource_manager.blob_store.s3 import S3BlobStore

        prefix = f"{tmp_path.name}/"
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
        retrieved = self.blob_store.get(file_id)
        assert retrieved.data == data
        assert isinstance(retrieved, Binary)
        assert retrieved.file_id == file_id
        assert retrieved.size == len(data)

    def test_exists(self):
        data = b"check_existence"
        file_id = self.blob_store.put(data).file_id

        # True for existing
        assert self.blob_store.exists(file_id) is True

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
        assert self.blob_store.get(file_id_1).data == data

    def test_get_not_found(self):
        with pytest.raises(FileNotFoundError):
            self.blob_store.get("missing_file_id")

    def test_multiple_files(self):
        data1 = b"file_1"
        data2 = b"file_2"

        id1 = self.blob_store.put(data1).file_id
        id2 = self.blob_store.put(data2).file_id

        assert id1 != id2
        assert self.blob_store.get(id1).data == data1
        assert self.blob_store.get(id2).data == data2

    def test_get_url_contract(self):
        """Ensure get_url returns str or None (and no error)."""
        data = b"url_check_data"
        file_id = self.blob_store.put(data).file_id

        url = self.blob_store.get_url(file_id)
        assert url is None or isinstance(url, str)
