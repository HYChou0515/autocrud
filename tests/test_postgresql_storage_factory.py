"""
PostgreSQL Storage Factory Tests

Tests for PostgreSQLStorageFactory combining PostgreSQL MetaStore with S3 ResourceStore.
Tests use mock S3 (moto) and in-memory PostgreSQL (sqlite) to avoid external dependencies.
"""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from msgspec import Struct

from autocrud.crud.core import AutoCRUD
from autocrud.resource_manager.basic import Encoding
from autocrud.resource_manager.storage_factory import PostgreSQLStorageFactory

# Use mock backends for testing
USE_MOCK = True


class GameCharacter(Struct):
    """RPG game character model."""

    name: str
    character_class: str
    level: int
    hp: int
    mp: int
    gold: int


@pytest.fixture
def mock_postgres_factory():
    """Create PostgreSQL storage factory with mocked backends for testing."""
    with (
        patch("autocrud.resource_manager.storage_factory.PostgresMetaStore") as mock_pg,
        patch("autocrud.resource_manager.storage_factory.S3ResourceStore") as mock_s3,
        patch("autocrud.resource_manager.storage_factory.S3BlobStore") as mock_blob,
    ):
        # Create factory
        factory = PostgreSQLStorageFactory(
            connection_string="postgresql://test:test@localhost:5432/testdb",
            s3_bucket="test-bucket",
            s3_region="us-east-1",
            s3_access_key_id="test-key",
            s3_secret_access_key="test-secret",
            s3_endpoint_url="http://localhost:9000",
            encoding=Encoding.msgpack,
            table_prefix="test_",
        )

        yield factory, mock_pg, mock_s3, mock_blob


def test_postgresql_storage_factory_initialization():
    """Test PostgreSQLStorageFactory initialization with all parameters."""
    factory = PostgreSQLStorageFactory(
        connection_string="postgresql://admin:password@localhost:5432/your_database",
        s3_bucket="my-bucket",
        s3_region="ap-northeast-1",
        s3_access_key_id="my-key",
        s3_secret_access_key="my-secret",
        s3_endpoint_url="http://minio:9000",
        s3_client_kwargs={"use_ssl": True},
        encoding=Encoding.json,
        table_prefix="prod_",
        blob_bucket="blob-bucket",
        blob_prefix="files/",
    )

    assert (
        factory.connection_string
        == "postgresql://admin:password@localhost:5432/your_database"
    )
    assert factory.s3_bucket == "my-bucket"
    assert factory.s3_region == "ap-northeast-1"
    assert factory.s3_access_key_id == "my-key"
    assert factory.s3_secret_access_key == "my-secret"
    assert factory.s3_endpoint_url == "http://minio:9000"
    assert factory.s3_client_kwargs == {"use_ssl": True}
    assert factory.encoding == Encoding.json
    assert factory.table_prefix == "prod_"
    assert factory.blob_bucket == "blob-bucket"
    assert factory.blob_prefix == "files/"


def test_postgresql_storage_factory_defaults():
    """Test PostgreSQLStorageFactory with default parameters."""
    factory = PostgreSQLStorageFactory(
        connection_string="postgresql://localhost/db",
        s3_bucket="bucket",
    )

    assert factory.s3_region == "us-east-1"
    assert factory.s3_access_key_id == "minioadmin"
    assert factory.s3_secret_access_key == "minioadmin"
    assert factory.s3_endpoint_url is None
    assert factory.s3_client_kwargs == {}
    assert factory.encoding == Encoding.msgpack
    assert factory.table_prefix == ""
    assert factory.blob_bucket == "bucket"  # Same as s3_bucket
    assert factory.blob_prefix == "blobs/"


def test_postgresql_storage_factory_build(mock_postgres_factory):
    """Test build() method creates correct stores."""
    factory, mock_pg_class, mock_s3_class, _ = mock_postgres_factory

    # Build storage for a model
    storage = factory.build("GameCharacter")

    # Verify PostgresMetaStore was called correctly
    mock_pg_class.assert_called_once_with(
        pg_dsn="postgresql://test:test@localhost:5432/testdb",
        encoding=Encoding.msgpack,
        table_name="test_GameCharacter_meta",
    )

    # Verify S3ResourceStore was called correctly
    mock_s3_class.assert_called_once_with(
        bucket="test-bucket",
        region_name="us-east-1",
        access_key_id="test-key",
        secret_access_key="test-secret",
        endpoint_url="http://localhost:9000",
        prefix="GameCharacter/data/",
        encoding=Encoding.msgpack,
        client_kwargs={},
    )

    # Verify storage was created
    assert storage is not None


def test_postgresql_storage_factory_build_blob_store(mock_postgres_factory):
    """Test build_blob_store() method creates correct blob store."""
    factory, _, _, mock_blob_class = mock_postgres_factory

    # Build blob store
    blob_store = factory.build_blob_store()

    # Verify S3BlobStore was called correctly
    mock_blob_class.assert_called_once_with(
        bucket="test-bucket",
        region_name="us-east-1",
        access_key_id="test-key",
        secret_access_key="test-secret",
        endpoint_url="http://localhost:9000",
        prefix="blobs/",
        client_kwargs={},
    )

    assert blob_store is not None


def test_postgresql_storage_factory_table_prefix():
    """Test table name generation with and without prefix."""
    with (
        patch("autocrud.resource_manager.storage_factory.PostgresMetaStore") as mock_pg,
        patch("autocrud.resource_manager.storage_factory.S3ResourceStore"),
    ):
        # Without prefix
        factory1 = PostgreSQLStorageFactory(
            connection_string="postgresql://localhost/db",
            s3_bucket="bucket",
            table_prefix="",
        )
        factory1.build("User")
        call_kwargs = mock_pg.call_args[1]
        assert call_kwargs["table_name"] == "User_meta"

        # With prefix
        mock_pg.reset_mock()
        factory2 = PostgreSQLStorageFactory(
            connection_string="postgresql://localhost/db",
            s3_bucket="bucket",
            table_prefix="app_",
        )
        factory2.build("User")
        call_kwargs = mock_pg.call_args[1]
        assert call_kwargs["table_name"] == "app_User_meta"


def test_postgresql_storage_factory_separate_blob_bucket():
    """Test using separate bucket for blobs."""
    with patch("autocrud.resource_manager.storage_factory.S3BlobStore") as mock_blob:
        factory = PostgreSQLStorageFactory(
            connection_string="postgresql://localhost/db",
            s3_bucket="data-bucket",
            blob_bucket="blob-bucket",
            blob_prefix="uploads/",
        )

        factory.build_blob_store()

        call_kwargs = mock_blob.call_args[1]
        assert call_kwargs["bucket"] == "blob-bucket"
        assert call_kwargs["prefix"] == "uploads/"


def test_postgresql_storage_factory_s3_client_kwargs():
    """Test passing custom S3 client kwargs."""
    with (
        patch("autocrud.resource_manager.storage_factory.S3ResourceStore") as mock_s3,
        patch("autocrud.resource_manager.storage_factory.PostgresMetaStore"),
    ):
        custom_kwargs = {
            "use_ssl": True,
            "verify": "/path/to/ca.crt",
            "config": {"retries": {"max_attempts": 5}},
        }

        factory = PostgreSQLStorageFactory(
            connection_string="postgresql://localhost/db",
            s3_bucket="bucket",
            s3_client_kwargs=custom_kwargs,
        )

        factory.build("Model")

        call_kwargs = mock_s3.call_args[1]
        assert call_kwargs["client_kwargs"] == custom_kwargs


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
