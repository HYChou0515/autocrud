"""S3 Storage Factory for AutoCRUD

提供完整的 S3 backend storage 實作，包含：
- S3SqliteMetaStore: 使用 SQLite + S3 backend 的元數據存儲
- S3ResourceStore: S3 資源數據存儲
- S3BlobStore: S3 二進制數據存儲
"""

from typing import Any

from autocrud.resource_manager.basic import Encoding, IStorage
from autocrud.resource_manager.blob_store.s3 import S3BlobStore
from autocrud.resource_manager.core import SimpleStorage
from autocrud.resource_manager.meta_store.sqlite3 import S3SqliteMetaStore
from autocrud.resource_manager.resource_store.s3 import S3ResourceStore
from autocrud.resource_manager.storage_factory import IStorageFactory


class S3StorageFactory(IStorageFactory):
    """完全使用 S3 作為 backend 的 Storage Factory

    這個 factory 會建立：
    - S3SqliteMetaStore: 使用 SQLite database 存於 S3 的元數據存儲
    - S3ResourceStore: 直接存於 S3 的資源數據
    - S3BlobStore: 直接存於 S3 的二進制數據

    範例:
        # 使用預設 MinIO 設定 (適用於本地開發)
        factory = S3StorageFactory(
            bucket="autocrud-data",
            endpoint_url="http://localhost:9000",
        )

        # 使用 AWS S3
        factory = S3StorageFactory(
            bucket="my-autocrud-bucket",
            access_key_id="AKIAIOSFODNN7EXAMPLE",
            secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            region_name="us-west-2",
        )

    Args:
        bucket: S3 bucket 名稱
        access_key_id: AWS access key ID (預設: minioadmin，適用於 MinIO)
        secret_access_key: AWS secret access key (預設: minioadmin，適用於 MinIO)
        region_name: AWS region (預設: us-east-1)
        endpoint_url: S3 endpoint URL (用於 MinIO、LocalStack 等，預設: None 表示使用 AWS)
        prefix: S3 key 的前綴 (用於同一 bucket 中區分不同應用)
        encoding: 編碼格式 (json 或 msgpack)
        auto_sync: 是否自動同步 SQLite DB 到 S3
        sync_interval: 同步間隔（秒），0 表示立即同步
        enable_locking: 啟用 ETag-based 樂觀鎖定
        auto_reload_on_conflict: 當偵測到衝突時自動從 S3 重新載入
        check_etag_on_read: 讀取前檢查 ETag 並重新載入（若有變更）
        client_kwargs: 額外的 boto3 client 參數
    """

    def __init__(
        self,
        bucket: str = "autocrud",
        access_key_id: str = "minioadmin",
        secret_access_key: str = "minioadmin",
        region_name: str = "us-east-1",
        endpoint_url: str | None = None,  # e.g., "http://localhost:9000" for MinIO
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
        """為指定的模型建立完整的 S3 backend storage

        Args:
            model_name: 模型名稱（會用作 S3 key 的一部分）

        Returns:
            IStorage: 包含 meta store 和 resource store 的存儲
        """
        # 為每個 model 建立獨立的 prefix
        model_prefix = f"{self.prefix}{model_name}/"

        # 建立 S3SqliteMetaStore
        # SQLite DB 會存在 S3 的 {prefix}{model_name}/meta.db
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

        # 建立 S3ResourceStore
        # 資源數據會直接存在 S3
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
        """建立共用的 S3BlobStore

        Returns:
            S3BlobStore: S3 二進制數據存儲
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
