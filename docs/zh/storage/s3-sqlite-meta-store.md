---
title: S3 + SQLite MetaStore
description: 將 SQLite 資料庫儲存在 S3 上的 MetaStore 實作
---

# S3 + SQLite MetaStore

S3SqliteMetaStore 結合了 SQLite 的高效能查詢能力和 S3 的持久化儲存優勢，讓你可以將 metadata 存放在雲端物件儲存上。

## ✨ 特性

- 🔄 **自動同步**：自動同步本地 SQLite 資料庫到 S3
- ⚙️ **可配置同步間隔**：設定每 N 次操作後自動同步
- 🎯 **手動同步**：支援手動觸發同步操作
- 📁 **臨時檔案管理**：自動管理本地臨時資料庫檔案
- ☁️ **S3 相容**：支援 AWS S3、MinIO、LocalStack 等 S3 相容服務
- 📦 **多編碼格式**：支援 JSON 和 msgpack 編碼

## 使用範例

### 基本用法

```python
from autocrud.resource_manager.meta_store.sqlite3 import S3SqliteMetaStore

# 建立 S3SqliteMetaStore
meta_store = S3SqliteMetaStore(
    bucket="my-bucket",
    key="metadata/my-database.db",
    access_key_id="your-access-key",
    secret_access_key="your-secret-key",
    endpoint_url="http://localhost:9000",  # MinIO 範例
    auto_sync=True,  # 啟用自動同步
    sync_interval=10,  # 每 10 次操作同步一次
)

# 使用方式與其他 MetaStore 相同
from autocrud.types import ResourceMeta
import datetime as dt

now = dt.datetime.now(dt.timezone.utc)
meta = ResourceMeta(
    current_revision_id="rev-001",
    resource_id="resource-123",
    total_revision_count=1,
    created_time=now,
    updated_time=now,
    created_by="user1",
    updated_by="user1",
    is_deleted=False,
    schema_version="1",
)

# 儲存 metadata
meta_store["resource-123"] = meta

# 手動同步到 S3
meta_store.sync_to_s3()

# 關閉時自動同步
meta_store.close()
```

### 與 AutoCRUD 整合

```python
from autocrud.crud import AutoCRUD
from autocrud.resource_manager.meta_store.sqlite3 import S3SqliteMetaStore
from autocrud.resource_manager.blob_store.simple import MemoryBlobStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.types import IStorage
from msgspec import Struct


class Product(Struct):
    name: str
    price: float
    category: str


class S3SqliteStorageFactory:
    """使用 S3 SQLite 的 Storage Factory"""
    
    def __init__(self, bucket: str = "autocrud-metadata"):
        self.bucket = bucket
    
    def __call__(self, model_name: str) -> IStorage:
        meta_store = S3SqliteMetaStore(
            bucket=self.bucket,
            key=f"metadata/{model_name}.db",
            endpoint_url="http://localhost:9000",
            auto_sync=True,
            sync_interval=5,
        )
        
        return IStorage(
            meta=meta_store,
            resource=MemoryResourceStore(),
            blob=MemoryBlobStore(),
        )


# 建立 AutoCRUD 實例
crud = AutoCRUD(storage_factory=S3SqliteStorageFactory())
crud.add_model(Product, indexed_fields=[("price", float), ("category", str)])
```

### 使用 AWS S3

```python
from autocrud.resource_manager.meta_store.sqlite3 import S3SqliteMetaStore

# 使用 AWS S3 憑證
meta_store = S3SqliteMetaStore(
    bucket="my-production-bucket",
    key="autocrud/metadata/products.db",
    region_name="ap-northeast-1",  # 東京區域
    access_key_id="AWS_ACCESS_KEY",
    secret_access_key="AWS_SECRET_KEY",
    endpoint_url=None,  # 使用預設 AWS S3 endpoint
)

# 或在 EC2/ECS 上使用 IAM Role
meta_store = S3SqliteMetaStore(
    bucket="my-production-bucket",
    key="autocrud/metadata/products.db",
    region_name="ap-northeast-1",
    # boto3 會自動使用 IAM Role 憑證
)
```

## ⚙️ 配置選項

| 參數 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `bucket` | `str` | (必需) | S3 bucket 名稱 |
| `key` | `str` | (必需) | S3 object key (資料庫檔案路徑) |
| `access_key_id` | `str` | `"minioadmin"` | AWS access key ID |
| `secret_access_key` | `str` | `"minioadmin"` | AWS secret access key |
| `region_name` | `str` | `"us-east-1"` | AWS region |
| `endpoint_url` | `str \| None` | `None` | 自訂 endpoint URL (用於 MinIO 等) |
| `encoding` | `Encoding` | `Encoding.json` | 編碼格式 (json 或 msgpack) |
| `auto_sync` | `bool` | `True` | 是否自動同步到 S3 |
| `sync_interval` | `int` | `10` | 自動同步間隔 (操作次數) |

## 📊 與 MemorySqliteMetaStore 的比較

| 特性 | MemorySqliteMetaStore | S3SqliteMetaStore |
|------|----------------------|-------------------|
| 儲存位置 | 記憶體 (`:memory:`) | S3 + 本地臨時檔案 |
| 持久化 | ❌ 重啟後資料遺失 | ✅ 資料持久化在 S3 |
| 效能 | 🚀 最快 | ⚡ 快速 (本地操作) |
| 適用場景 | 測試、暫存 | 生產環境、分散式系統 |
| 資料共享 | ❌ 單實例 | ✅ 多實例共享 |

## ⚠️ 注意事項

1. **並發控制**：多個實例同時寫入同一個 S3 資料庫可能導致衝突。建議：
   - 單寫入者多讀取者模式
   - 或使用[分散式鎖機制](s3-sqlite-locking.md)

2. **同步策略**：
   - `auto_sync=True`：適合頻繁寫入的場景
   - `auto_sync=False` + 手動 `sync_to_s3()`：適合批次操作

3. **本地快取**：資料庫下載到本地臨時檔案，提供快速查詢效能

4. **清理**：使用 `close()` 方法確保資料同步並清理臨時檔案

## 📝 完整範例

查看範例程式碼：

:octicons-mark-github-16: [examples/s3_sqlite_meta_store_example.py](https://github.com/HYChou0515/autocrud/blob/master/examples/s3_sqlite_meta_store_example.py)

## 🧪 測試

```bash
# 執行 S3SqliteMetaStore 測試
uv run pytest tests/test_s3_meta_store.py -v

# 執行所有測試
make test
```
