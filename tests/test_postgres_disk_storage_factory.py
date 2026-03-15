"""
PostgreSQL + Disk Storage Factory Tests

Tests for PostgresDiskStorageFactory combining PostgreSQL MetaStore
with Disk ResourceStore. Uses mocked backends to avoid external dependencies.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from msgspec import Struct

from autocrud.resource_manager.basic import Encoding
from autocrud.resource_manager.storage_factory import PostgresDiskStorageFactory


class SampleItem(Struct):
    """Simple test model."""

    name: str
    value: int


class TestPostgresDiskStorageFactoryInit:
    """Tests for PostgresDiskStorageFactory initialization."""

    def test_initialization_all_params(self):
        """Test initialization with all parameters explicitly set."""
        factory = PostgresDiskStorageFactory(
            connection_string="postgresql://admin:password@localhost:5432/mydb",
            rootdir="/data/autocrud",
            encoding=Encoding.json,
            table_prefix="prod_",
        )

        assert (
            factory.connection_string
            == "postgresql://admin:password@localhost:5432/mydb"
        )
        assert factory.rootdir == Path("/data/autocrud")
        assert factory.encoding == Encoding.json
        assert factory.table_prefix == "prod_"

    def test_initialization_defaults(self):
        """Test initialization with default parameters."""
        factory = PostgresDiskStorageFactory(
            connection_string="postgresql://localhost/db",
            rootdir="/tmp/test",
        )

        assert factory.connection_string == "postgresql://localhost/db"
        assert factory.rootdir == Path("/tmp/test")
        assert factory.encoding == Encoding.msgpack
        assert factory.table_prefix == ""

    def test_rootdir_string_converted_to_path(self):
        """Test that string rootdir is converted to Path."""
        factory = PostgresDiskStorageFactory(
            connection_string="postgresql://localhost/db",
            rootdir="/tmp/test",
        )
        assert isinstance(factory.rootdir, Path)

    def test_rootdir_path_preserved(self):
        """Test that Path rootdir is preserved as-is."""
        p = Path("/tmp/test")
        factory = PostgresDiskStorageFactory(
            connection_string="postgresql://localhost/db",
            rootdir=p,
        )
        assert factory.rootdir == p


class TestPostgresDiskStorageFactoryBuild:
    """Tests for PostgresDiskStorageFactory.build() method."""

    @pytest.fixture
    def mock_factory(self):
        """Create factory with mocked stores."""
        with (
            patch(
                "autocrud.resource_manager.storage_factory.PostgresMetaStore"
            ) as mock_pg,
            patch(
                "autocrud.resource_manager.storage_factory.DiskResourceStore"
            ) as mock_disk,
        ):
            factory = PostgresDiskStorageFactory(
                connection_string="postgresql://test:test@localhost:5432/testdb",
                rootdir="/tmp/autocrud-test",
                encoding=Encoding.msgpack,
                table_prefix="bench_",
            )
            yield factory, mock_pg, mock_disk

    def test_build_creates_correct_meta_store(self, mock_factory):
        """Test build() creates PostgresMetaStore with correct arguments."""
        factory, mock_pg, _ = mock_factory
        factory.build("TestItem")

        mock_pg.assert_called_once_with(
            pg_dsn="postgresql://test:test@localhost:5432/testdb",
            encoding=Encoding.msgpack,
            table_name="bench_TestItem_meta",
        )

    def test_build_creates_correct_resource_store(self, mock_factory):
        """Test build() creates DiskResourceStore with correct arguments."""
        factory, _, mock_disk = mock_factory
        factory.build("TestItem")

        mock_disk.assert_called_once_with(
            rootdir=Path("/tmp/autocrud-test") / "TestItem" / "data",
        )

    def test_build_returns_storage(self, mock_factory):
        """Test build() returns a valid storage instance."""
        factory, _, _ = mock_factory
        storage = factory.build("TestItem")
        assert storage is not None

    def test_build_multiple_models(self, mock_factory):
        """Test build() works for multiple different models."""
        factory, mock_pg, mock_disk = mock_factory

        factory.build("User")
        factory.build("Post")

        assert mock_pg.call_count == 2
        assert mock_disk.call_count == 2

        # Verify different table names and directories
        pg_calls = mock_pg.call_args_list
        assert pg_calls[0][1]["table_name"] == "bench_User_meta"
        assert pg_calls[1][1]["table_name"] == "bench_Post_meta"

        disk_calls = mock_disk.call_args_list
        assert disk_calls[0][1]["rootdir"] == Path("/tmp/autocrud-test/User/data")
        assert disk_calls[1][1]["rootdir"] == Path("/tmp/autocrud-test/Post/data")


class TestPostgresDiskStorageFactoryTablePrefix:
    """Tests for table name generation with and without prefix."""

    def test_table_name_without_prefix(self):
        """Test table name without prefix."""
        with (
            patch(
                "autocrud.resource_manager.storage_factory.PostgresMetaStore"
            ) as mock_pg,
            patch("autocrud.resource_manager.storage_factory.DiskResourceStore"),
        ):
            factory = PostgresDiskStorageFactory(
                connection_string="postgresql://localhost/db",
                rootdir="/tmp/test",
                table_prefix="",
            )
            factory.build("User")

            call_kwargs = mock_pg.call_args[1]
            assert call_kwargs["table_name"] == "User_meta"

    def test_table_name_with_prefix(self):
        """Test table name with prefix."""
        with (
            patch(
                "autocrud.resource_manager.storage_factory.PostgresMetaStore"
            ) as mock_pg,
            patch("autocrud.resource_manager.storage_factory.DiskResourceStore"),
        ):
            factory = PostgresDiskStorageFactory(
                connection_string="postgresql://localhost/db",
                rootdir="/tmp/test",
                table_prefix="app_",
            )
            factory.build("User")

            call_kwargs = mock_pg.call_args[1]
            assert call_kwargs["table_name"] == "app_User_meta"

    def test_table_name_with_long_prefix(self):
        """Test table name with a longer prefix."""
        with (
            patch(
                "autocrud.resource_manager.storage_factory.PostgresMetaStore"
            ) as mock_pg,
            patch("autocrud.resource_manager.storage_factory.DiskResourceStore"),
        ):
            factory = PostgresDiskStorageFactory(
                connection_string="postgresql://localhost/db",
                rootdir="/tmp/test",
                table_prefix="my_project_v2_",
            )
            factory.build("Character")

            call_kwargs = mock_pg.call_args[1]
            assert call_kwargs["table_name"] == "my_project_v2_Character_meta"


class TestPostgresDiskStorageFactoryEncoding:
    """Tests for encoding parameter handling."""

    def test_json_encoding(self):
        """Test factory with JSON encoding."""
        with (
            patch(
                "autocrud.resource_manager.storage_factory.PostgresMetaStore"
            ) as mock_pg,
            patch("autocrud.resource_manager.storage_factory.DiskResourceStore"),
        ):
            factory = PostgresDiskStorageFactory(
                connection_string="postgresql://localhost/db",
                rootdir="/tmp/test",
                encoding=Encoding.json,
            )
            factory.build("Model")

            call_kwargs = mock_pg.call_args[1]
            assert call_kwargs["encoding"] == Encoding.json

    def test_msgpack_encoding(self):
        """Test factory with msgpack encoding."""
        with (
            patch(
                "autocrud.resource_manager.storage_factory.PostgresMetaStore"
            ) as mock_pg,
            patch("autocrud.resource_manager.storage_factory.DiskResourceStore"),
        ):
            factory = PostgresDiskStorageFactory(
                connection_string="postgresql://localhost/db",
                rootdir="/tmp/test",
                encoding=Encoding.msgpack,
            )
            factory.build("Model")

            call_kwargs = mock_pg.call_args[1]
            assert call_kwargs["encoding"] == Encoding.msgpack


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
