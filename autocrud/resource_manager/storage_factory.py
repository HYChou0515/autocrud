from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from autocrud.resource_manager.basic import Encoding, IBlobStore, IStorage
from autocrud.resource_manager.blob_store.s3 import S3BlobStore
from autocrud.resource_manager.core import SimpleStorage
from autocrud.resource_manager.meta_store.postgres import PostgresMetaStore
from autocrud.resource_manager.meta_store.simple import DiskMetaStore, MemoryMetaStore
from autocrud.resource_manager.meta_store.sqlite3 import S3SqliteMetaStore
from autocrud.resource_manager.resource_store.s3 import S3ResourceStore
from autocrud.resource_manager.resource_store.simple import (
    DiskResourceStore,
    MemoryResourceStore,
)


class IStorageFactory(ABC):
    @abstractmethod
    def build(
        self,
        model_name: str,
    ) -> IStorage: ...


class MemoryStorageFactory(IStorageFactory):
    def build(
        self,
        model_name: str,
    ) -> IStorage:
        meta_store = MemoryMetaStore()

        resource_store = MemoryResourceStore()

        return SimpleStorage(meta_store, resource_store)


class DiskStorageFactory(IStorageFactory):
    def __init__(
        self,
        rootdir: Path | str,
    ):
        self.rootdir = Path(rootdir)

    def build(
        self,
        model_name: str,
    ) -> IStorage:
        meta_store = DiskMetaStore(rootdir=self.rootdir / model_name / "meta")

        # 對於其他類型（msgspec.Struct, dataclass, TypedDict），使用原生支持
        resource_store = DiskResourceStore(
            rootdir=self.rootdir / model_name / "data",
        )

        return SimpleStorage(meta_store, resource_store)


class PostgreSQLStorageFactory(IStorageFactory):
    """PostgreSQL + S3 Storage Factory for production use.

    Uses PostgreSQL for metadata storage (fast queries, indexes) and S3 for resource data.
    Suitable for medium to large scale applications requiring high availability and scalability.

    Args:
        connection_string: PostgreSQL connection string (e.g., "postgresql://user:pass@host:port/db")
        s3_bucket: S3 bucket name for storing resource data
        s3_region: AWS region for S3 bucket (default: "us-east-1")
        s3_access_key_id: AWS access key ID (default: "minioadmin" for MinIO)
        s3_secret_access_key: AWS secret access key (default: "minioadmin" for MinIO)
        s3_endpoint_url: S3 endpoint URL, use for MinIO or S3-compatible services (default: None for AWS S3)
        s3_client_kwargs: Additional boto3 client kwargs (default: None)
        encoding: Encoding format for data serialization (default: Encoding.msgpack)
        table_prefix: Prefix for PostgreSQL table names (default: "")
        blob_bucket: S3 bucket name for blob storage (default: same as s3_bucket)
        blob_prefix: Prefix for blob storage in S3 (default: "blobs/")
    """

    def __init__(
        self,
        connection_string: str,
        s3_bucket: str,
        s3_region: str = "us-east-1",
        s3_access_key_id: str = "minioadmin",
        s3_secret_access_key: str = "minioadmin",
        s3_endpoint_url: str | None = None,
        s3_client_kwargs: dict | None = None,
        encoding: Encoding = Encoding.msgpack,
        table_prefix: str = "",
        blob_bucket: str | None = None,
        blob_prefix: str = "blobs/",
    ):
        self.connection_string = connection_string
        self.s3_bucket = s3_bucket
        self.s3_region = s3_region
        self.s3_access_key_id = s3_access_key_id
        self.s3_secret_access_key = s3_secret_access_key
        self.s3_endpoint_url = s3_endpoint_url
        self.s3_client_kwargs = s3_client_kwargs or {}
        self.encoding = encoding
        self.table_prefix = table_prefix
        self.blob_bucket = blob_bucket or s3_bucket
        self.blob_prefix = blob_prefix

    def build(
        self,
        model_name: str,
    ) -> IStorage:
        # Use PostgreSQL for metadata (indexes, search queries)
        table_name = (
            f"{self.table_prefix}{model_name}_meta"
            if self.table_prefix
            else f"{model_name}_meta"
        )
        meta_store = PostgresMetaStore(
            pg_dsn=self.connection_string,
            encoding=self.encoding,
            table_name=table_name,
        )

        # Use S3 for resource data storage
        resource_store = S3ResourceStore(
            bucket=self.s3_bucket,
            region_name=self.s3_region,
            access_key_id=self.s3_access_key_id,
            secret_access_key=self.s3_secret_access_key,
            endpoint_url=self.s3_endpoint_url,
            prefix=f"{model_name}/data/",
            encoding=self.encoding,
            client_kwargs=self.s3_client_kwargs,
        )

        return SimpleStorage(meta_store, resource_store)

    def build_blob_store(self) -> IBlobStore:
        """Build S3-based blob store for binary data."""
        return S3BlobStore(
            bucket=self.blob_bucket,
            region_name=self.s3_region,
            access_key_id=self.s3_access_key_id,
            secret_access_key=self.s3_secret_access_key,
            endpoint_url=self.s3_endpoint_url,
            prefix=self.blob_prefix,
            client_kwargs=self.s3_client_kwargs,
        )


class S3StorageFactory(IStorageFactory):
    """S3 Storage Factory with SQLite metadata store.

    Uses S3SqliteMetaStore (SQLite DB stored in S3) for metadata and S3 for resource data.
    Suitable for medium-scale applications requiring cloud storage without external database.

    Args:
        bucket: S3 bucket name
        access_key_id: AWS access key ID (default: "minioadmin" for MinIO)
        secret_access_key: AWS secret access key (default: "minioadmin" for MinIO)
        region_name: AWS region (default: "us-east-1")
        endpoint_url: S3 endpoint URL, use for MinIO or S3-compatible services (default: None for AWS S3)
        prefix: S3 key prefix (default: "")
        encoding: Encoding format for data serialization (default: Encoding.json)
        auto_sync: Auto-sync SQLite DB to S3 (default: True)
        sync_interval: Sync interval in seconds, 0 for immediate sync (default: 0)
        enable_locking: Enable ETag-based optimistic locking (default: True)
        auto_reload_on_conflict: Auto-reload from S3 on conflict detection (default: False)
        check_etag_on_read: Check ETag and reload on read if changed (default: True)
        client_kwargs: Additional boto3 client kwargs (default: None)
    """

    def __init__(
        self,
        bucket: str = "autocrud",
        access_key_id: str = "minioadmin",
        secret_access_key: str = "minioadmin",
        region_name: str = "us-east-1",
        endpoint_url: str | None = None,
        prefix: str = "",
        encoding: Encoding = Encoding.json,
        auto_sync: bool = True,
        sync_interval: float = 0,
        enable_locking: bool = True,
        auto_reload_on_conflict: bool = False,
        check_etag_on_read: bool = True,
        client_kwargs: dict[str, Any] | None = None,
    ):
        self.bucket = bucket
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.region_name = region_name
        self.endpoint_url = endpoint_url
        self.prefix = prefix
        self.encoding = encoding
        self.auto_sync = auto_sync
        self.sync_interval = sync_interval
        self.enable_locking = enable_locking
        self.auto_reload_on_conflict = auto_reload_on_conflict
        self.check_etag_on_read = check_etag_on_read
        self.client_kwargs = client_kwargs or {}

    def build(self, model_name: str) -> IStorage:
        """Build S3 backend storage for the specified model.

        Args:
            model_name: Model name (used as part of S3 key)

        Returns:
            IStorage: Storage with meta store and resource store
        """
        model_prefix = f"{self.prefix}{model_name}/"

        # Create S3SqliteMetaStore
        # SQLite DB will be stored in S3 at {prefix}{model_name}/meta.db
        meta_store = S3SqliteMetaStore(
            bucket=self.bucket,
            key=f"{model_prefix}meta.db",
            access_key_id=self.access_key_id,
            secret_access_key=self.secret_access_key,
            region_name=self.region_name,
            endpoint_url=self.endpoint_url,
            encoding=self.encoding,
            auto_sync=self.auto_sync,
            sync_interval=self.sync_interval,
            enable_locking=self.enable_locking,
            auto_reload_on_conflict=self.auto_reload_on_conflict,
            check_etag_on_read=self.check_etag_on_read,
        )

        # Create S3ResourceStore
        resource_store = S3ResourceStore(
            encoding=self.encoding,
            access_key_id=self.access_key_id,
            secret_access_key=self.secret_access_key,
            region_name=self.region_name,
            endpoint_url=self.endpoint_url,
            bucket=self.bucket,
            prefix=model_prefix,
            client_kwargs=self.client_kwargs,
        )

        return SimpleStorage(meta_store, resource_store)

    def build_blob_store(self) -> S3BlobStore:
        """Build S3-based blob store for binary data.

        Returns:
            S3BlobStore: S3 blob store
        """
        return S3BlobStore(
            access_key_id=self.access_key_id,
            secret_access_key=self.secret_access_key,
            region_name=self.region_name,
            endpoint_url=self.endpoint_url,
            bucket=self.bucket,
            prefix=f"{self.prefix}blobs/",
            client_kwargs=self.client_kwargs,
        )
