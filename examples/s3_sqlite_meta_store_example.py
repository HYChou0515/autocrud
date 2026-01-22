"""
S3SqliteMetaStore 使用範例

此範例展示如何使用 S3SqliteMetaStore 將 SQLite 數據庫存儲在 S3 上。
適用於需要持久化 metadata 並利用 S3 分佈式存儲優勢的場景。

包含：
- 基本使用
- 自動同步
- ETag 樂觀鎖機制
- 衝突處理
"""

from msgspec import Struct

from autocrud.crud import AutoCRUD
from autocrud.resource_manager.meta_store.sqlite3 import (
    S3ConflictError,
    S3SqliteMetaStore,
)


class Product(Struct):
    """產品資料結構"""

    name: str
    price: float
    category: str
    stock: int


def create_s3_storage_factory():
    """
    創建使用 S3SqliteMetaStore 的 StorageFactory

    這個範例使用 MinIO (本地 S3 兼容存儲) 進行演示。
    在生產環境中，可以使用 AWS S3 或其他 S3 兼容服務。
    """
    from autocrud.resource_manager.blob_store.simple import MemoryBlobStore
    from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
    from autocrud.types import IStorage

    class S3SqliteStorageFactory:
        """使用 S3 作為 SQLite 後端的 Storage Factory"""

        def __init__(
            self,
            bucket: str = "autocrud-metadata",
            endpoint_url: str | None = None,
            access_key_id: str = "minioadmin",
            secret_access_key: str = "minioadmin",
        ):
            self.bucket = bucket
            self.endpoint_url = endpoint_url
            self.access_key_id = access_key_id
            self.secret_access_key = secret_access_key

        def __call__(self, model_name: str) -> IStorage:
            """為每個模型創建獨立的存儲實例"""
            # 每個模型使用獨立的 S3 key
            meta_store = S3SqliteMetaStore(
                bucket=self.bucket,
                key=f"metadata/{model_name}.db",
                endpoint_url=self.endpoint_url,
                access_key_id=self.access_key_id,
                secret_access_key=self.secret_access_key,
                auto_sync=True,  # 自動同步到 S3
                sync_interval=5,  # 每 5 次操作同步一次
            )

            # Resource store 和 blob store 可以使用記憶體或其他儲存
            resource_store = MemoryResourceStore()
            blob_store = MemoryBlobStore()

            return IStorage(
                meta=meta_store,
                resource=resource_store,
                blob=blob_store,
            )

    return S3SqliteStorageFactory()


def main():
    """主要範例流程"""
    # 創建 AutoCRUD 實例，使用 S3 存儲
    crud = AutoCRUD(
        storage_factory=create_s3_storage_factory(),
    )

    # 註冊模型，指定需要索引的欄位
    crud.add_model(
        Product,
        indexed_fields=[
            ("price", float),
            ("category", str),
            ("stock", int),
        ],
    )

    print("=== S3SqliteMetaStore 使用範例 ===\n")

    # 建立產品資料
    print("1. 建立產品資料...")
    from autocrud.resource_manager.core import ResourceManager

    mgr: ResourceManager[Product] = crud.managers["Product"]

    import datetime as dt

    with mgr.meta_provide(user="admin", now=dt.datetime.now()):
        # 建立多個產品
        products = [
            Product(name="筆記型電腦", price=30000.0, category="3C", stock=10),
            Product(name="滑鼠", price=500.0, category="3C", stock=50),
            Product(name="鍵盤", price=1500.0, category="3C", stock=30),
            Product(name="咖啡豆", price=350.0, category="食品", stock=100),
            Product(name="綠茶", price=200.0, category="食品", stock=80),
        ]

        for product in products:
            info = mgr.create(product)
            print(f"   建立產品: {product.name} (ID: {info.resource_id})")

    print("\n2. 查詢產品資料...")
    from autocrud.types import (
        DataSearchCondition,
        DataSearchOperator,
        ResourceMetaSearchQuery,
    )

    # 搜尋 3C 類別的產品
    query = ResourceMetaSearchQuery(
        data_conditions=[
            DataSearchCondition(
                field_path="category",
                operator=DataSearchOperator.equals,
                value="3C",
            ),
        ],
        limit=100,
        offset=0,
    )

    results = list(mgr.search(query))
    print(f"   找到 {len(results)} 個 3C 產品:")
    for meta in results:
        resource = mgr.get(meta.resource_id)
        print(
            f"     - {resource.data.name}: ${resource.data.price} (庫存: {resource.data.stock})"
        )

    # 搜尋價格大於 1000 的產品
    print("\n3. 搜尋高價產品 (價格 > 1000)...")
    query = ResourceMetaSearchQuery(
        data_conditions=[
            DataSearchCondition(
                field_path="price",
                operator=DataSearchOperator.greater_than,
                value=1000.0,
            ),
        ],
        limit=100,
        offset=0,
    )

    results = list(mgr.search(query))
    print(f"   找到 {len(results)} 個高價產品:")
    for meta in results:
        resource = mgr.get(meta.resource_id)
        print(
            f"     - {resource.data.name}: ${resource.data.price} (類別: {resource.data.category})"
        )

    print("\n4. 手動同步到 S3...")
    # 可以手動觸發同步
    storage = crud.storages["Product"]
    if hasattr(storage.meta, "sync_to_s3"):
        storage.meta.sync_to_s3()
        print("   ✓ 已同步到 S3")

    print("\n=== 完成 ===")
    print("\n提示:")
    print("- Metadata 已自動同步到 S3")
    print("- S3 路徑: s3://{bucket}/metadata/Product.db")
    print("- 可以在多個實例間共享此資料庫")
    print("- 支援自動同步或手動同步模式")


def example_with_aws_s3():
    """使用真實 AWS S3 的範例配置"""
    print("\n=== AWS S3 配置範例 ===\n")
    print("如果要使用真實的 AWS S3，可以這樣配置：\n")

    example_code = """
    from autocrud.resource_manager.meta_store.sqlite3 import S3SqliteMetaStore
    
    # 使用 AWS S3
    meta_store = S3SqliteMetaStore(
        bucket="my-production-bucket",
        key="autocrud/metadata/products.db",
        region_name="ap-northeast-1",  # 東京
        access_key_id="YOUR_AWS_ACCESS_KEY",
        secret_access_key="YOUR_AWS_SECRET_KEY",
        endpoint_url=None,  # 使用預設 AWS S3 endpoint
        auto_sync=True,
        sync_interval=10,
    )
    
    # 或使用 IAM Role (在 EC2/ECS 上)
    meta_store = S3SqliteMetaStore(
        bucket="my-production-bucket",
        key="autocrud/metadata/products.db",
        region_name="ap-northeast-1",
        # 不需要提供 access_key_id 和 secret_access_key
        # boto3 會自動使用 IAM Role
    )
    """

    print(example_code)


def example_with_locking():
    """展示 ETag 樂觀鎖機制"""
    print("\n=== ETag 樂觀鎖範例 ===\n")

    # 創建啟用鎖定的 store
    store = S3SqliteMetaStore(
        bucket="test-bucket",
        key="metadata/locked.db",
        enable_locking=True,  # 啟用 ETag 鎖定（默認）
        auto_reload_on_conflict=False,  # 衝突時不自動重新載入
        auto_sync=False,
    )

    print("1. ETag 樂觀鎖已啟用")
    print(f"   當前 ETag: {store.get_current_etag()}")

    # 模擬數據操作
    import datetime as dt

    from autocrud.types import ResourceMeta

    now = dt.datetime.now(dt.timezone.utc)
    meta = ResourceMeta(
        current_revision_id="rev-001",
        resource_id="product-1",
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by="user1",
        updated_by="user1",
        is_deleted=False,
        schema_version="1",
    )

    store["product-1"] = meta
    print("\n2. 添加了一筆資料")

    # 嘗試同步
    print("\n3. 同步到 S3...")
    try:
        store.sync_to_s3()
        print("   ✓ 同步成功")
        print(f"   新 ETag: {store.get_current_etag()}")
    except S3ConflictError as e:
        print(f"   ✗ 衝突: {e}")

    # 檢查是否需要同步
    print("\n4. 檢查同步狀態...")
    if store.is_sync_needed():
        print("   需要同步（S3 版本已變更）")
    else:
        print("   無需同步（版本一致）")

    # 強制同步範例
    print("\n5. 強制同步（繞過 ETag 檢查）...")
    try:
        store.sync_to_s3(force=True)
        print("   ✓ 強制同步成功")
    except Exception as e:
        print(f"   ✗ 錯誤: {e}")

    print("\n提示:")
    print("- enable_locking=True: 啟用樂觀鎖防止衝突")
    print("- auto_reload_on_conflict=True: 衝突時自動重新載入")
    print("- sync_to_s3(force=True): 強制同步，忽略 ETag 檢查")


def example_conflict_handling():
    """展示衝突處理策略"""
    print("\n=== 衝突處理範例 ===\n")

    print("策略 1: 重新載入並重試")
    print("```python")
    print(
        """
def safe_update(store, resource_id, new_data):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            store[resource_id] = new_data
            store.sync_to_s3()
            return True
        except S3ConflictError:
            if attempt < max_retries - 1:
                store.reload_from_s3()
                continue
            else:
                raise
    return False
"""
    )
    print("```")

    print("\n策略 2: 使用自動重新載入")
    print("```python")
    print(
        """
store = S3SqliteMetaStore(
    bucket="my-bucket",
    key="metadata/my-db.db",
    auto_reload_on_conflict=True,  # 衝突時自動重新載入
)

try:
    store[resource_id] = new_data
    store.sync_to_s3()
except S3ConflictError:
    # 已自動重新載入，重新執行操作
    store[resource_id] = new_data
    store.sync_to_s3()
"""
    )
    print("```")


if __name__ == "__main__":
    # 運行主要範例
    # 注意: 需要先啟動 MinIO 或配置 AWS S3
    try:
        main()
    except Exception as e:
        print(f"\n錯誤: {e}")
        print("\n提示: 請確保 S3/MinIO 服務正在運行")
        print("MinIO 啟動命令範例:")
        print(
            "  docker run -p 9000:9000 -p 9001:9001 minio/minio server /data --console-address ':9001'"
        )

    # 顯示 AWS S3 配置範例
    example_with_aws_s3()

    # 顯示 ETag 樂觀鎖範例
    try:
        example_with_locking()
    except Exception as e:
        print(f"\n鎖定範例錯誤: {e}")

    # 顯示衝突處理策略
    example_conflict_handling()
