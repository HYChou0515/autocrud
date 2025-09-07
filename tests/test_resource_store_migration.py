import datetime as dt
import math
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import IO
from uuid import uuid4

import msgspec
import pytest
from msgspec import UNSET, Struct

from autocrud.resource_manager.basic import (
    Encoding,
)
from autocrud.resource_manager.resource_store.s3 import S3ResourceStore
from autocrud.resource_manager.resource_store.simple import (
    DiskResourceStore,
    MemoryResourceStore,
)
from autocrud.types import IMigration, Resource, RevisionInfo, RevisionStatus


# Legacy data structures for migration testing
class LegacyInnerData(Struct):
    string: str
    number: int
    fp: float
    times: dt.datetime


class LegacyData(Struct):
    string: str
    number: int
    data: LegacyInnerData
    # Missing fp, times, list_data, dict_data compared to Data


# Current data structures
class InnerData(Struct):
    string: str
    number: int
    fp: float
    times: dt.datetime


class Data(Struct):
    string: str
    number: int
    fp: float
    times: dt.datetime
    data: InnerData
    list_data: list[InnerData]
    dict_data: dict[str, InnerData]


# Migration implementation
class DataMigration(IMigration):
    def __init__(self, target_schema_version: str = "2.0"):
        self._schema_version = target_schema_version

    @property
    def schema_version(self) -> str:
        return self._schema_version

    def migrate(self, data: IO[bytes], schema_version: str | None) -> Data:
        """Migrate from LegacyData to Data by adding missing fields"""
        data.seek(0)  # Ensure we're at the beginning
        data_bytes = data.read()

        # Handle both explicit "1.0" and UNSET/None as legacy version
        if schema_version == "1.0" or schema_version is None or schema_version == UNSET:
            # Decode as legacy format
            decoder = msgspec.json.Decoder(LegacyData)
            legacy_data = decoder.decode(data_bytes)

            # Create new InnerData preserving original values
            new_inner_data = InnerData(
                string=legacy_data.data.string,
                number=legacy_data.data.number,
                fp=legacy_data.data.fp,
                times=legacy_data.data.times,
            )

            # Create new Data adding missing fields with defaults
            migrated_data = Data(
                string=legacy_data.string,
                number=legacy_data.number,
                fp=0.0,  # Default value for new field
                times=dt.datetime(2023, 1, 1),  # Default value for new field
                data=new_inner_data,
                list_data=[],  # Empty list for new field
                dict_data={},  # Empty dict for new field
            )

            return migrated_data
        # For other versions, try to decode as current format
        decoder = msgspec.json.Decoder(Data)
        return decoder.decode(data_bytes)


def create_legacy_resource(resource_id: str, revision_id: str) -> Resource[LegacyData]:
    """Helper to create a legacy format resource"""
    legacy_inner = LegacyInnerData(
        string="legacy_inner",
        number=42,
        fp=math.pi,
        times=dt.datetime(2023, 6, 15, 10, 30),
    )
    legacy_data = LegacyData(string="legacy_string", number=100, data=legacy_inner)

    info = RevisionInfo(
        uid=uuid4(),
        resource_id=resource_id,
        revision_id=revision_id,
        schema_version="1.0",  # Old schema version
        status=RevisionStatus.stable,
        created_time=dt.datetime.now(),
        updated_time=dt.datetime.now(),
        created_by="test_user",
        updated_by="test_user",
    )

    return Resource(info=info, data=legacy_data)


def create_current_resource(resource_id: str, revision_id: str) -> Resource[Data]:
    """Helper to create a current format resource"""
    inner = InnerData(
        string="current_inner",
        number=99,
        fp=math.e,
        times=dt.datetime(2023, 12, 25),
    )
    data = Data(
        string="current_string",
        number=200,
        fp=1.41,
        times=dt.datetime(2023, 11, 15),
        data=inner,
        list_data=[inner],
        dict_data={"key1": inner},
    )

    info = RevisionInfo(
        uid=uuid4(),
        resource_id=resource_id,
        revision_id=revision_id,
        schema_version="2.0",  # Current schema version
        status=RevisionStatus.stable,
        created_time=dt.datetime.now(),
        updated_time=dt.datetime.now(),
        created_by="test_user",
        updated_by="test_user",
    )

    return Resource(info=info, data=data)


@pytest.fixture
def tmpdir():
    """Fixture to provide a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.mark.parametrize("store_type", ["memory", "disk", "s3"])
class TestResourceStoreMigration:
    @pytest.fixture(autouse=True)
    def cleanup(self, store_type: str, tmpdir: Path):
        yield
        if store_type == "s3":
            s3 = S3ResourceStore(
                Data,
                encoding="msgpack",
                endpoint_url="http://localhost:9000",
                prefix=str(tmpdir).rsplit("/", 1)[-1] + "/",
            )
            with suppress(Exception):
                s3.cleanup()

    def get_store_with_migration(
        self,
        store_type: str,
        tmpdir: Path = None,
        memory_store_to_copy=None,
    ):
        """Create a resource store with migration enabled"""
        migration = DataMigration()

        if store_type == "memory":
            new_store = MemoryResourceStore(
                Data,
                encoding=Encoding.json,
                migration=migration,
            )
            # Copy data from legacy store if provided
            if memory_store_to_copy is not None:
                new_store._data_store = memory_store_to_copy._data_store.copy()
                new_store._info_store = memory_store_to_copy._info_store.copy()
            return new_store
        if store_type == "disk":
            rootdir = tmpdir / "test_store"
            return DiskResourceStore(
                Data,
                encoding=Encoding.json,
                rootdir=rootdir,
                migration=migration,
            )
        if store_type == "s3":
            return S3ResourceStore(
                Data,
                encoding=Encoding.json,
                endpoint_url="http://localhost:9000",
                prefix=str(tmpdir).rsplit("/", 1)[-1] + "/",
                migration=migration,
            )

    def get_store_without_migration(self, store_type: str, tmpdir: Path = None):
        """Create a resource store without migration (for saving legacy data)"""
        if store_type == "memory":
            return MemoryResourceStore(LegacyData, encoding=Encoding.json)
        if store_type == "disk":
            rootdir = tmpdir / "test_store"
            return DiskResourceStore(
                LegacyData,
                encoding=Encoding.json,
                rootdir=rootdir,
            )
        if store_type == "s3":
            return S3ResourceStore(
                LegacyData,
                encoding=Encoding.json,
                endpoint_url="http://localhost:9000",
                prefix=str(tmpdir).rsplit("/", 1)[-1] + "/",
            )

    def test_migration_on_get(self, store_type: str, tmpdir: Path):
        """Test that migration happens automatically when getting legacy data"""
        resource_id = "test_resource"
        revision_id = "rev_001"

        # Step 1: Save legacy data using store without migration
        legacy_store = self.get_store_without_migration(store_type, tmpdir)
        legacy_resource = create_legacy_resource(resource_id, revision_id)
        legacy_store.save(legacy_resource)

        # Verify legacy data is saved
        assert legacy_store.exists(resource_id, revision_id)
        retrieved_legacy = legacy_store.get(resource_id, revision_id)
        assert retrieved_legacy.info.schema_version == "1.0"
        assert isinstance(retrieved_legacy.data, LegacyData)

        # Step 2: Read with migration-enabled store
        migration_store = self.get_store_with_migration(
            store_type,
            tmpdir,
            memory_store_to_copy=legacy_store if store_type == "memory" else None,
        )
        migrated_resource = migration_store.get(resource_id, revision_id)

        # Verify data has been migrated
        assert migrated_resource.info.schema_version == "2.0"  # Updated schema version
        assert isinstance(migrated_resource.data, Data)

        # Verify migrated data content
        migrated_data = migrated_resource.data
        assert migrated_data.string == "legacy_string"
        assert migrated_data.number == 100
        assert migrated_data.fp == 0.0  # Default value for new field
        assert migrated_data.times == dt.datetime(
            2023,
            1,
            1,
        )  # Default value for new field
        assert migrated_data.data.string == "legacy_inner"
        assert migrated_data.data.number == 42
        assert migrated_data.data.fp == math.pi  # From original legacy data
        assert migrated_data.data.times == dt.datetime(
            2023,
            6,
            15,
            10,
            30,
        )  # From original legacy data
        assert migrated_data.list_data == []  # New field with default
        assert migrated_data.dict_data == {}  # New field with default

    def test_no_migration_for_current_data(self, store_type: str, tmpdir: Path):
        """Test that current data doesn't get migrated"""
        resource_id = "test_resource"
        revision_id = "rev_001"

        # Save current format data
        store = self.get_store_with_migration(store_type, tmpdir)
        current_resource = create_current_resource(resource_id, revision_id)
        store.save(current_resource)

        # Retrieve data
        retrieved_resource = store.get(resource_id, revision_id)

        # Verify data is unchanged
        assert retrieved_resource.info.schema_version == "2.0"
        assert isinstance(retrieved_resource.data, Data)

    def test_no_migration_when_no_migrator(self, store_type: str, tmpdir: Path):
        """Test that no migration happens when no migrator is provided"""
        resource_id = "test_resource"
        revision_id = "rev_001"

        # Create store without migration
        store = self.get_store_without_migration(store_type, tmpdir)

        # Save legacy data
        legacy_resource = create_legacy_resource(resource_id, revision_id)
        store.save(legacy_resource)

        # Retrieve data
        retrieved_resource = store.get(resource_id, revision_id)

        # Verify data is unchanged
        assert retrieved_resource.info.schema_version == "1.0"
        assert isinstance(retrieved_resource.data, LegacyData)

    def test_multiple_gets_after_migration(self, store_type: str, tmpdir: Path):
        """Test that subsequent gets don't re-migrate (migration is persistent)"""
        resource_id = "test_resource"
        revision_id = "rev_001"

        # Save legacy data
        legacy_store = self.get_store_without_migration(store_type, tmpdir)
        legacy_resource = create_legacy_resource(resource_id, revision_id)
        legacy_store.save(legacy_resource)

        # First get with migration
        migration_store = self.get_store_with_migration(
            store_type,
            tmpdir,
            memory_store_to_copy=legacy_store if store_type == "memory" else None,
        )
        first_get = migration_store.get(resource_id, revision_id)
        assert first_get.info.schema_version == "2.0"

        # Second get should not re-migrate
        second_get = migration_store.get(resource_id, revision_id)
        assert second_get.info.schema_version == "2.0"

        # Data should be identical
        assert first_get.data == second_get.data

        # For disk store, verify the schema version was persisted
        if store_type == "disk":
            # Create a new store instance to ensure we're reading from disk
            new_migration_store = self.get_store_with_migration(store_type, tmpdir)
            third_get = new_migration_store.get(resource_id, revision_id)
            assert third_get.info.schema_version == "2.0"

    def test_mixed_schema_versions(self, store_type: str, tmpdir: Path):
        """Test handling resources with different schema versions"""
        # Save one legacy resource
        legacy_store = self.get_store_without_migration(store_type, tmpdir)
        legacy_resource = create_legacy_resource("legacy_resource", "rev_001")
        legacy_store.save(legacy_resource)

        # Save one current resource using migration store (with copied data for memory)
        migration_store = self.get_store_with_migration(
            store_type,
            tmpdir,
            memory_store_to_copy=legacy_store if store_type == "memory" else None,
        )
        current_resource = create_current_resource("current_resource", "rev_001")
        migration_store.save(current_resource)

        # Retrieve both with migration store
        legacy_result = migration_store.get("legacy_resource", "rev_001")
        current_result = migration_store.get("current_resource", "rev_001")

        # Both should now have current schema version
        assert legacy_result.info.schema_version == "2.0"
        assert current_result.info.schema_version == "2.0"

        # But data should reflect their origins
        assert legacy_result.data.string == "legacy_string"  # From migration
        assert current_result.data.string == "current_string"  # Original data

    def test_schema_version_unset_handling(self, store_type: str, tmpdir: Path):
        """Test handling of resources with UNSET schema_version"""
        resource_id = "test_resource"
        revision_id = "rev_001"

        # Create a resource with UNSET schema_version
        legacy_inner = LegacyInnerData(
            string="unset_inner",
            number=42,
            fp=1.23,
            times=dt.datetime(2023, 3, 15, 14, 30),
        )
        legacy_data = LegacyData(string="unset_string", number=100, data=legacy_inner)

        info = RevisionInfo(
            uid=uuid4(),
            resource_id=resource_id,
            revision_id=revision_id,
            schema_version=UNSET,  # No schema version set
            status=RevisionStatus.stable,
            created_time=dt.datetime.now(),
            updated_time=dt.datetime.now(),
            created_by="test_user",
            updated_by="test_user",
        )

        unset_resource = Resource(info=info, data=legacy_data)

        # Save using legacy store
        legacy_store = self.get_store_without_migration(store_type, tmpdir)
        legacy_store.save(unset_resource)

        # Retrieve with migration store
        migration_store = self.get_store_with_migration(
            store_type,
            tmpdir,
            memory_store_to_copy=legacy_store if store_type == "memory" else None,
        )
        migrated_resource = migration_store.get(resource_id, revision_id)

        # Should be migrated since schema_version was UNSET (treated as old version)
        assert migrated_resource.info.schema_version == "2.0"
        assert isinstance(migrated_resource.data, Data)
