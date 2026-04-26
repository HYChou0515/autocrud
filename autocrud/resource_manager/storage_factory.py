from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Literal

from autocrud.resource_manager.basic import Encoding, IBlobStore, IStorage
from autocrud.resource_manager.blob_store.s3 import S3BlobStore
from autocrud.resource_manager.core import SimpleStorage
from autocrud.resource_manager.meta_store.postgres import PostgresMetaStore
from autocrud.resource_manager.meta_store.simple import DiskMetaStore, MemoryMetaStore
from autocrud.resource_manager.meta_store.sqlite3 import S3SqliteMetaStore
from autocrud.resource_manager.resource_store.postgres import PostgresResourceStore
from autocrud.resource_manager.resource_store.s3 import S3ResourceStore
from autocrud.resource_manager.resource_store.simple import (
    DiskResourceStore,
    MemoryResourceStore,
)
from autocrud.util.naming import NameConverter


def _pg_safe_name(model_name: str) -> str:
    """Convert a model name to a PostgreSQL-safe snake_case identifier."""
    return NameConverter(model_name).to("snake")


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


class PostgresStorageFactory(IStorageFactory):
    """PostgreSQL-only Storage Factory.

    Uses PostgreSQL for both metadata storage and resource data storage.
    No external object storage (S3) dependency — all structured data lives in
    PostgreSQL. This is useful for database-centric deployments, but it is not
    the project's default recommendation when durable blob uploads are part of
    the system.

    Args:
        connection_string: PostgreSQL connection string
            (e.g. ``"postgresql://user:pass@host:port/db"``).
        encoding: Encoding format for data serialization
            (default: ``Encoding.msgpack``).
        table_prefix: Prefix for PostgreSQL table names (default: ``""``).  The
            meta table will be named ``<prefix><model>_meta`` and the resource
            tables ``<prefix><model>_resource_data`` /
            ``<prefix><model>_resource_index``.
    """

    def __init__(
        self,
        connection_string: str,
        encoding: Encoding = Encoding.msgpack,
        table_prefix: str = "",
    ):
        self.connection_string = connection_string
        self.encoding = encoding
        self.table_prefix = table_prefix

    def build(
        self,
        model_name: str,
    ) -> IStorage:
        """Build a PostgreSQL-only storage for the specified model.

        Args:
            model_name: Model name (used for table naming).

        Returns:
            Storage combining PostgreSQL meta store and PostgreSQL resource store.
        """
        safe_name = _pg_safe_name(model_name)
        table_name = (
            f"{self.table_prefix}{safe_name}_meta"
            if self.table_prefix
            else f"{safe_name}_meta"
        )
        meta_store = PostgresMetaStore(
            pg_dsn=self.connection_string,
            encoding=self.encoding,
            table_name=table_name,
        )

        resource_table_prefix = (
            f"{self.table_prefix}{safe_name}_" if self.table_prefix else f"{safe_name}_"
        )
        resource_store = PostgresResourceStore(
            pg_dsn=self.connection_string,
            encoding=self.encoding,
            table_prefix=resource_table_prefix,
        )

        return SimpleStorage(meta_store, resource_store)


class PostgreSQLS3StorageFactory(IStorageFactory):
    """PostgreSQL + S3 Storage Factory for object-storage-first production use.

    Uses PostgreSQL for metadata storage (fast queries, indexes) and S3 for resource data.
    This remains a strong option for medium to large scale applications, especially
    when deployments prefer object storage for payloads as well as blobs.

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
        upload_method: How upload sessions deliver bytes to S3:
            ``"proxy"`` (default) — bytes flow through the server;
            ``"single_put"`` — a presigned PUT URL is returned so the
            client uploads directly to S3.
        presigned_url_expiry: Expiry in seconds for presigned URLs
            (default ``3600``).
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
        upload_method: Literal["proxy", "single_put"] = "proxy",
        presigned_url_expiry: int = 3600,
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
        self.upload_method = upload_method
        self.presigned_url_expiry = presigned_url_expiry

    def build(
        self,
        model_name: str,
    ) -> IStorage:
        # Use PostgreSQL for metadata (indexes, search queries)
        safe_name = _pg_safe_name(model_name)
        table_name = (
            f"{self.table_prefix}{safe_name}_meta"
            if self.table_prefix
            else f"{safe_name}_meta"
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
            upload_method=self.upload_method,
            presigned_url_expiry=self.presigned_url_expiry,
            client_kwargs=self.s3_client_kwargs,
        )


class PostgresDiskStorageFactory(IStorageFactory):
    """PostgreSQL + Disk Storage Factory for hybrid deployments.

    Uses PostgreSQL for metadata storage (fast queries, indexes) and local or
    mounted disk for resource data. This is a good fit when you want strong
    metadata querying while keeping structured payloads on local or mounted
    storage.

    Blob durability is a separate concern. If your application stores uploads
    or binary artifacts, use :class:`PostgresDiskS3StorageFactory` or provide
    your own explicit blob-store wiring.

    Args:
        connection_string: PostgreSQL connection string
            (e.g., ``"postgresql://user:pass@host:port/db"``).
        rootdir: Root directory for disk-based resource data storage.
        encoding: Encoding format for data serialization (default: ``Encoding.msgpack``).
        table_prefix: Prefix for PostgreSQL table names (default: ``""``).
    """

    def __init__(
        self,
        connection_string: str,
        rootdir: Path | str,
        encoding: Encoding = Encoding.msgpack,
        table_prefix: str = "",
    ):
        self.connection_string = connection_string
        self.rootdir = Path(rootdir)
        self.encoding = encoding
        self.table_prefix = table_prefix

    def build(
        self,
        model_name: str,
    ) -> IStorage:
        """Build a PostgreSQL + Disk storage for the specified model.

        Args:
            model_name: Model name (used for table naming and directory structure).

        Returns:
            Storage combining PostgreSQL meta store and disk resource store.
        """
        # Use PostgreSQL for metadata (indexes, search queries)
        safe_name = _pg_safe_name(model_name)
        table_name = (
            f"{self.table_prefix}{safe_name}_meta"
            if self.table_prefix
            else f"{safe_name}_meta"
        )
        meta_store = PostgresMetaStore(
            pg_dsn=self.connection_string,
            encoding=self.encoding,
            table_name=table_name,
        )

        # Use disk for resource data storage
        resource_store = DiskResourceStore(
            rootdir=self.rootdir / model_name / "data",
        )

        return SimpleStorage(meta_store, resource_store)


class PostgresDiskS3StorageFactory(PostgresDiskStorageFactory):
    """PostgreSQL + Disk + S3 blob Storage Factory for production use.

    Uses PostgreSQL for metadata storage, local or mounted disk for resource
    data, and S3-compatible storage for blobs. This is the out-of-the-box
    production-oriented factory when you want searchable metadata, durable
    resource files on disk, and durable binary uploads in object storage.

    Args:
        connection_string: PostgreSQL connection string
            (e.g., ``"postgresql://user:pass@host:port/db"``).
        rootdir: Root directory for disk-based resource data storage.
        s3_bucket: S3 bucket name for blob storage.
        s3_region: AWS region for the S3 bucket (default: ``"us-east-1"``).
        s3_access_key_id: AWS access key ID (default: ``"minioadmin"``).
        s3_secret_access_key: AWS secret access key (default: ``"minioadmin"``).
        s3_endpoint_url: S3 endpoint URL for MinIO or S3-compatible services.
        s3_client_kwargs: Additional boto3 client kwargs.
        encoding: Encoding format for data serialization (default: ``Encoding.msgpack``).
        table_prefix: Prefix for PostgreSQL table names (default: ``""``).
        blob_bucket: Optional dedicated bucket for blobs. Defaults to ``s3_bucket``.
        blob_prefix: Prefix for blob storage in S3 (default: ``"blobs/"``).
        upload_method: How upload sessions deliver bytes to S3.
        presigned_url_expiry: Expiry in seconds for presigned URLs.
    """

    def __init__(
        self,
        connection_string: str,
        rootdir: Path | str,
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
        upload_method: Literal["proxy", "single_put"] = "proxy",
        presigned_url_expiry: int = 3600,
    ):
        super().__init__(
            connection_string=connection_string,
            rootdir=rootdir,
            encoding=encoding,
            table_prefix=table_prefix,
        )
        self.s3_bucket = s3_bucket
        self.s3_region = s3_region
        self.s3_access_key_id = s3_access_key_id
        self.s3_secret_access_key = s3_secret_access_key
        self.s3_endpoint_url = s3_endpoint_url
        self.s3_client_kwargs = s3_client_kwargs or {}
        self.blob_bucket = blob_bucket or s3_bucket
        self.blob_prefix = blob_prefix
        self.upload_method = upload_method
        self.presigned_url_expiry = presigned_url_expiry

    def build_blob_store(self) -> IBlobStore:
        """Build S3-based blob store for binary data."""
        return S3BlobStore(
            bucket=self.blob_bucket,
            region_name=self.s3_region,
            access_key_id=self.s3_access_key_id,
            secret_access_key=self.s3_secret_access_key,
            endpoint_url=self.s3_endpoint_url,
            prefix=self.blob_prefix,
            upload_method=self.upload_method,
            presigned_url_expiry=self.presigned_url_expiry,
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
        upload_method: How upload sessions deliver bytes to S3:
            ``"proxy"`` (default) — bytes flow through the server;
            ``"single_put"`` — a presigned PUT URL is returned so the
            client uploads directly to S3.
        presigned_url_expiry: Expiry in seconds for presigned URLs
            (default ``3600``).
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
        upload_method: Literal["proxy", "single_put"] = "proxy",
        presigned_url_expiry: int = 3600,
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
        self.upload_method = upload_method
        self.presigned_url_expiry = presigned_url_expiry

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
            upload_method=self.upload_method,
            presigned_url_expiry=self.presigned_url_expiry,
            client_kwargs=self.client_kwargs,
        )
