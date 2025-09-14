import io
from uuid import uuid4
import datetime as dt

import pytest

from autocrud.resource_manager.basic import Encoding
from autocrud.resource_manager.resource_store.simple import (
    DiskResourceStore,
    MemoryResourceStore,
)
from autocrud.types import RevisionInfo, RevisionStatus

# Try to import S3ResourceStore, but make it optional
try:
    from autocrud.resource_manager.resource_store.s3 import S3ResourceStore

    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False


class TestIResourceStore:
    """Test suite for IResourceStore interface implementations."""

    @pytest.fixture(params=["memory", "disk"] + (["s3"] if S3_AVAILABLE else []))
    def resource_store(self, request, tmp_path):
        """Parametrized fixture that creates different resource store implementations."""
        if request.param == "memory":
            yield MemoryResourceStore(encoding=Encoding.json)
        elif request.param == "disk":
            yield DiskResourceStore(encoding=Encoding.json, rootdir=tmp_path)
        elif request.param == "s3" and S3_AVAILABLE:
            # Use tmp_path for unique prefix to avoid conflicts between tests
            prefix = f"test-{tmp_path.name}/"
            store = S3ResourceStore(
                encoding=Encoding.json,
                endpoint_url="http://localhost:9000",
                bucket="test-autocrud",
                prefix=prefix,
            )
            # Clean up before and after
            try:
                store.cleanup()
            except Exception:
                pass
            yield store
            try:
                store.cleanup()
            except Exception:
                pass
        else:
            pytest.skip(f"Store type {request.param} not available")

    @pytest.fixture
    def sample_revision_info(self):
        """Create a sample RevisionInfo for testing."""
        now = dt.datetime.now(dt.timezone.utc)
        return RevisionInfo(
            uid=uuid4(),
            resource_id="test_resource_1",
            revision_id="rev_001",
            schema_version="1.0",
            status=RevisionStatus.stable,
            created_time=now,
            updated_time=now,
            created_by="test_user",
            updated_by="test_user",
            parent_revision_id=None,
            data_hash="test_hash",
        )

    @pytest.fixture
    def sample_data(self):
        """Create sample data for testing."""
        return io.BytesIO(b'{"name": "test", "value": 42}')

    def test_save_and_exists(self, resource_store, sample_revision_info, sample_data):
        """Test saving data and checking existence."""
        # Initially should not exist
        assert not resource_store.exists(
            sample_revision_info.resource_id,
            sample_revision_info.revision_id,
            sample_revision_info.schema_version,
        )

        # Save the data
        resource_store.save(sample_revision_info, sample_data)

        # Now should exist
        assert resource_store.exists(
            sample_revision_info.resource_id,
            sample_revision_info.revision_id,
            sample_revision_info.schema_version,
        )

    def test_save_and_get_data_bytes(
        self, resource_store, sample_revision_info, sample_data
    ):
        """Test saving and retrieving data bytes."""
        original_data = sample_data.read()
        sample_data.seek(0)  # Reset stream position

        # Save the data
        resource_store.save(sample_revision_info, sample_data)

        # Retrieve the data
        with resource_store.get_data_bytes(
            sample_revision_info.resource_id,
            sample_revision_info.revision_id,
            sample_revision_info.schema_version,
        ) as data_stream:
            retrieved_data = data_stream.read()

        assert retrieved_data == original_data

    def test_save_and_get_revision_info(
        self, resource_store, sample_revision_info, sample_data
    ):
        """Test saving and retrieving revision info."""
        # Save the data
        resource_store.save(sample_revision_info, sample_data)

        # Retrieve the revision info
        retrieved_info = resource_store.get_revision_info(
            sample_revision_info.resource_id,
            sample_revision_info.revision_id,
            sample_revision_info.schema_version,
        )

        # Compare relevant fields (some fields might be auto-generated)
        assert retrieved_info.uid == sample_revision_info.uid
        assert retrieved_info.resource_id == sample_revision_info.resource_id
        assert retrieved_info.revision_id == sample_revision_info.revision_id
        assert retrieved_info.schema_version == sample_revision_info.schema_version
        assert retrieved_info.data_hash == sample_revision_info.data_hash

    def test_list_resources(self, resource_store, sample_data):
        """Test listing resources."""
        # Initially empty
        resources = list(resource_store.list_resources())
        assert len(resources) == 0

        # Add some resources
        now = dt.datetime.now(dt.timezone.utc)
        info1 = RevisionInfo(
            uid=uuid4(),
            resource_id="resource_1",
            revision_id="rev_001",
            schema_version="1.0",
            status=RevisionStatus.stable,
            created_time=now,
            updated_time=now,
            created_by="test_user",
            updated_by="test_user",
            parent_revision_id=None,
            data_hash="hash1",
        )
        info2 = RevisionInfo(
            uid=uuid4(),
            resource_id="resource_2",
            revision_id="rev_001",
            schema_version="1.0",
            status=RevisionStatus.stable,
            created_time=now,
            updated_time=now,
            created_by="test_user",
            updated_by="test_user",
            parent_revision_id=None,
            data_hash="hash2",
        )

        sample_data.seek(0)
        resource_store.save(info1, sample_data)
        sample_data.seek(0)
        resource_store.save(info2, sample_data)

        # List resources
        resources = set(resource_store.list_resources())
        assert resources == {"resource_1", "resource_2"}

    def test_list_revisions(self, resource_store, sample_data):
        """Test listing revisions for a resource."""
        resource_id = "test_resource"

        # Add multiple revisions
        now = dt.datetime.now(dt.timezone.utc)
        revisions = ["rev_001", "rev_002", "rev_003"]
        for revision_id in revisions:
            info = RevisionInfo(
                uid=uuid4(),
                resource_id=resource_id,
                revision_id=revision_id,
                schema_version="1.0",
                status=RevisionStatus.stable,
                created_time=now,
                updated_time=now,
                created_by="test_user",
                updated_by="test_user",
                parent_revision_id=None,
                data_hash=f"hash_{revision_id}",
            )
            sample_data.seek(0)
            resource_store.save(info, sample_data)

        # List revisions
        retrieved_revisions = set(resource_store.list_revisions(resource_id))
        assert retrieved_revisions == set(revisions)

    def test_list_schema_versions(self, resource_store, sample_data):
        """Test listing schema versions for a resource revision."""
        resource_id = "test_resource"
        revision_id = "rev_001"

        # Add multiple schema versions
        now = dt.datetime.now(dt.timezone.utc)
        schema_versions = ["1.0", "1.1", None]  # Include None for no version
        for schema_version in schema_versions:
            info = RevisionInfo(
                uid=uuid4(),
                resource_id=resource_id,
                revision_id=revision_id,
                schema_version=schema_version,
                status=RevisionStatus.stable,
                created_time=now,
                updated_time=now,
                created_by="test_user",
                updated_by="test_user",
                parent_revision_id=None,
                data_hash=f"hash_{schema_version}",
            )
            sample_data.seek(0)
            resource_store.save(info, sample_data)

        # List schema versions
        retrieved_versions = set(
            resource_store.list_schema_versions(resource_id, revision_id)
        )
        assert retrieved_versions == set(schema_versions)

    def test_different_schema_versions_same_resource_revision(
        self, resource_store, sample_data
    ):
        """Test that different schema versions can coexist for the same resource/revision."""
        resource_id = "test_resource"
        revision_id = "rev_001"

        # Create data for different schema versions
        now = dt.datetime.now(dt.timezone.utc)
        data_v1 = io.BytesIO(b'{"name": "test", "version": 1}')
        data_v2 = io.BytesIO(b'{"name": "test", "version": 2, "new_field": "value"}')

        info_v1 = RevisionInfo(
            uid=uuid4(),
            resource_id=resource_id,
            revision_id=revision_id,
            schema_version="1.0",
            status=RevisionStatus.stable,
            created_time=now,
            updated_time=now,
            created_by="test_user",
            updated_by="test_user",
            parent_revision_id=None,
            data_hash="hash_v1",
        )

        info_v2 = RevisionInfo(
            uid=uuid4(),
            resource_id=resource_id,
            revision_id=revision_id,
            schema_version="2.0",
            status=RevisionStatus.stable,
            created_time=now,
            updated_time=now,
            created_by="test_user",
            updated_by="test_user",
            parent_revision_id=None,
            data_hash="hash_v2",
        )

        # Save both versions
        resource_store.save(info_v1, data_v1)
        resource_store.save(info_v2, data_v2)

        # Both should exist
        assert resource_store.exists(resource_id, revision_id, "1.0")
        assert resource_store.exists(resource_id, revision_id, "2.0")

        # Retrieve and verify data
        with resource_store.get_data_bytes(resource_id, revision_id, "1.0") as stream:
            data_v1_retrieved = stream.read()
        with resource_store.get_data_bytes(resource_id, revision_id, "2.0") as stream:
            data_v2_retrieved = stream.read()

        assert data_v1_retrieved == b'{"name": "test", "version": 1}'
        assert (
            data_v2_retrieved == b'{"name": "test", "version": 2, "new_field": "value"}'
        )

    def test_uid_deduplication(self, resource_store):
        """Test that same UID data is deduplicated."""
        same_uid = uuid4()
        now = dt.datetime.now(dt.timezone.utc)
        same_data = io.BytesIO(b'{"shared": "data"}')

        # Create two different resource/revision combinations with same UID
        info1 = RevisionInfo(
            uid=same_uid,
            resource_id="resource_1",
            revision_id="rev_001",
            schema_version="1.0",
            status=RevisionStatus.stable,
            created_time=now,
            updated_time=now,
            created_by="test_user",
            updated_by="test_user",
            parent_revision_id=None,
            data_hash="same_hash",
        )

        info2 = RevisionInfo(
            uid=same_uid,
            resource_id="resource_2",
            revision_id="rev_002",
            schema_version="1.0",
            status=RevisionStatus.stable,
            created_time=now,
            updated_time=now,
            created_by="test_user",
            updated_by="test_user",
            parent_revision_id=None,
            data_hash="same_hash",
        )

        # Save both (should share the same underlying data)
        same_data.seek(0)
        resource_store.save(info1, same_data)
        same_data.seek(0)
        resource_store.save(info2, same_data)

        # Both should exist and return the same data
        assert resource_store.exists("resource_1", "rev_001", "1.0")
        assert resource_store.exists("resource_2", "rev_002", "1.0")

        with resource_store.get_data_bytes("resource_1", "rev_001", "1.0") as stream:
            data1 = stream.read()
        with resource_store.get_data_bytes("resource_2", "rev_002", "1.0") as stream:
            data2 = stream.read()

        assert data1 == data2 == b'{"shared": "data"}'

    def test_nonexistent_resource_operations(self, resource_store):
        """Test operations on nonexistent resources."""
        # exists should return False
        assert not resource_store.exists("nonexistent", "rev_001", "1.0")

        # get_data_bytes should raise KeyError or FileNotFoundError
        with pytest.raises((KeyError, FileNotFoundError)):
            with resource_store.get_data_bytes("nonexistent", "rev_001", "1.0"):
                pass

        # get_revision_info should raise KeyError or FileNotFoundError
        with pytest.raises((KeyError, FileNotFoundError)):
            resource_store.get_revision_info("nonexistent", "rev_001", "1.0")

    def test_encoding_variants(self):
        """Test different encoding types."""
        now = dt.datetime.now(dt.timezone.utc)
        for encoding in [Encoding.json, Encoding.msgpack]:
            store = MemoryResourceStore(encoding=encoding)

            info = RevisionInfo(
                uid=uuid4(),
                resource_id="test_resource",
                revision_id="rev_001",
                schema_version="1.0",
                status=RevisionStatus.stable,
                created_time=now,
                updated_time=now,
                created_by="test_user",
                updated_by="test_user",
                parent_revision_id=None,
                data_hash="test_hash",
            )

            data = io.BytesIO(b'{"test": "data"}')
            store.save(info, data)

            # Should be able to retrieve regardless of encoding
            assert store.exists("test_resource", "rev_001", "1.0")
            retrieved_info = store.get_revision_info("test_resource", "rev_001", "1.0")
            assert retrieved_info.uid == info.uid
