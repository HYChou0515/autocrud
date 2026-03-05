---
title: 設定儲存後端
description: 了解如何配置 AutoCRUD 的儲存後端
---

# 設定儲存後端

AutoCRUD 提供靈活的儲存後端選項，讓你可以根據需求選擇最適合的儲存方式。從快速開發的記憶體儲存，到生產環境的磁碟儲存，甚至是自定義的資料庫後端。

## 內建儲存選項

### Memory Storage (記憶體儲存)

預設的儲存方式，所有資料存放在記憶體中，適合開發和測試。

```python
from autocrud import AutoCRUD

# 使用預設的記憶體儲存
crud = AutoCRUD()
crud.add_model(TodoItem)
```

**特性：**

- ⚡ 最快的讀寫速度
- 🔄 應用程式重啟後資料會遺失
- 💡 適合開發、測試、原型設計
- 📦 不需要額外設定

### Disk Storage (磁碟儲存)

將資料持久化到磁碟，適合生產環境使用。

```python
from autocrud import AutoCRUD
from autocrud.resource_manager.storage_factory import DiskStorageFactory
from pathlib import Path

# 設定磁碟儲存路徑
storage_factory = DiskStorageFactory(rootdir=Path("./data"))

crud = AutoCRUD(storage_factory=storage_factory)
crud.add_model(TodoItem)
```

**特性：**

- 💾 資料持久化，重啟不遺失
- 📁 以檔案系統方式組織資料
- 🔍 支援完整的索引和搜尋功能
- 🎯 適合中小型應用的生產環境

**目錄結構：**

```
./data/
├── todo-item/
│   ├── meta/          # 資源 metadata 和索引
│   └── data/          # 資源實際內容
└── user/
    ├── meta/
    └── data/
```

## 為不同模型設定不同儲存

你可以為每個模型單獨指定儲存後端：

```python
from autocrud import AutoCRUD
from autocrud.resource_manager.storage_factory import DiskStorageFactory, MemoryStorageFactory

# 全域使用記憶體儲存
crud = AutoCRUD()

# User 使用磁碟儲存（需要持久化）
crud.add_model(
    User,
    storage_factory=DiskStorageFactory("./data")
)

# Session 使用記憶體儲存（臨時資料）
crud.add_model(
    Session,
    storage_factory=MemoryStorageFactory()
)
```

## SimpleStorage 組合式儲存

AutoCRUD 的核心儲存設計允許你自由組合 MetaStore 和 ResourceStore。`SimpleStorage` 是最基本的組合方式，讓你能夠：

- 將 metadata（索引、搜尋）和實際資料分開儲存
- 根據需求選擇不同的後端組合

### 範例 1：SimpleStorageFactory 基本用法

```python
from autocrud import AutoCRUD
from autocrud.resource_manager.core import SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import DiskResourceStore
from autocrud.resource_manager.storage_factory import IStorageFactory
from autocrud.resource_manager.basic import IStorage
from pathlib import Path

class CustomSimpleStorageFactory(IStorageFactory):
    """自定義儲存工廠：記憶體索引 + 磁碟資料"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
    
    def build(self, model_name: str) -> IStorage:
        # MetaStore: 記憶體（快速搜尋）
        meta_store = MemoryMetaStore()
        
        # ResourceStore: 磁碟（持久化資料）
        resource_store = DiskResourceStore(
            rootdir=self.data_dir / model_name
        )
        
        return SimpleStorage(meta_store, resource_store)

# 使用自定義工廠
storage_factory = CustomSimpleStorageFactory(data_dir=Path("./data"))
crud = AutoCRUD(storage_factory=storage_factory)
crud.add_model(Article)
```

**優勢：**

- ⚡ 記憶體索引提供極快的搜尋速度
- 💾 磁碟儲存確保資料不遺失
- 🎯 適合讀取多、搜尋頻繁的場景

### 範例 2：PostgreSQL Meta + S3 Resource

生產環境最佳實踐：使用 PostgreSQL 存放 metadata（支援複雜查詢），S3 存放實際資料（低成本、高可靠性）。

```python
from autocrud import AutoCRUD
from autocrud.resource_manager.core import SimpleStorage
from autocrud.resource_manager.meta_store.postgres import PostgresMetaStore
from autocrud.resource_manager.resource_store.s3 import S3ResourceStore
from autocrud.resource_manager.storage_factory import IStorageFactory
from autocrud.resource_manager.basic import IStorage, Encoding
from msgspec import Struct

class Article(Struct):
    title: str
    content: str
    author: str

class PostgresS3StorageFactory(IStorageFactory):
    """PostgreSQL metadata + S3 資料儲存"""
    
    def __init__(
        self,
        pg_dsn: str,
        s3_bucket: str,
        s3_endpoint: str | None = None,
        s3_access_key: str = "minioadmin",
        s3_secret_key: str = "minioadmin",
    ):
        self.pg_dsn = pg_dsn
        self.s3_bucket = s3_bucket
        self.s3_endpoint = s3_endpoint
        self.s3_access_key = s3_access_key
        self.s3_secret_key = s3_secret_key
    
    def build(self, model_name: str) -> IStorage:
        # PostgreSQL MetaStore：強大的查詢能力
        meta_store = PostgresMetaStore(
            pg_dsn=self.pg_dsn,
            encoding=Encoding.msgpack,  # MessagePack 效能更好
            table_name=f"meta_{model_name}",
        )
        
        # S3 ResourceStore：低成本、高可靠性
        resource_store = S3ResourceStore(
            bucket=self.s3_bucket,
            prefix=f"{model_name}/",
            endpoint_url=self.s3_endpoint,
            access_key_id=self.s3_access_key,
            secret_access_key=self.s3_secret_key,
            encoding=Encoding.msgpack,
        )
        
        return SimpleStorage(meta_store, resource_store)

# 生產環境配置
storage_factory = PostgresS3StorageFactory(
    pg_dsn="postgresql://user:password@localhost:5432/autocrud_db",
    s3_bucket="my-app-data",
    s3_endpoint="https://s3.amazonaws.com",  # 或 MinIO: "http://localhost:9000"
    s3_access_key="YOUR_ACCESS_KEY",
    s3_secret_key="YOUR_SECRET_KEY",
)

crud = AutoCRUD(storage_factory=storage_factory)
crud.add_model(Article, indexed_fields=[("author", str)])

# PostgreSQL 會儲存：resource_id, revision_id, created_time, author (indexed)
# S3 會儲存：完整的 Article 資料（title, content, author）
```

**使用場景：**

- 📊 需要複雜查詢和統計的應用
- 💰 大量資料需要低成本儲存
- 🌐 分散式部署環境
- 🔒 需要資料備份和災難恢復

## 進階儲存組合

### 範例 3：S3 + SQLite Meta + S3 Resource（雲端 S3 方案）

✨ 適合完全基於雲端物件儲存的場景，使用 S3SqliteMetaStore（SQLite 資料庫檔案存放在 S3）。

!!! info "New in version 0.7.6"

```python
from autocrud.resource_manager.meta_store.sqlite3 import S3SqliteMetaStore
from autocrud.resource_manager.resource_store.s3 import S3ResourceStore

class S3StorageFactory(IStorageFactory):
    """完全使用 S3 儲存的方案（SQLite DB 檔案也在 S3）"""
    
    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        access_key_id: str = "minioadmin",
        secret_access_key: str = "minioadmin",
        region_name: str = "us-east-1",
    ):
        self.bucket = bucket
        self.endpoint_url = endpoint_url
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.region_name = region_name
    
    def build(self, model_name: str) -> IStorage:
        # S3SqliteMetaStore：SQLite 資料庫存放在 S3
        meta_store = S3SqliteMetaStore(
            bucket=self.bucket,
            key=f"meta/{model_name}.sqlite",
            endpoint_url=self.endpoint_url,
            access_key_id=self.access_key_id,
            secret_access_key=self.secret_access_key,
            region_name=self.region_name,
            encoding=Encoding.msgpack,
            auto_sync=True,  # 自動同步到 S3
            sync_interval=5.0,  # 每 5 秒同步一次
            enable_locking=True,  # 啟用 ETag 鎖定防止衝突
        )
        
        # S3 ResourceStore：資料存放在 S3
        resource_store = S3ResourceStore(
            bucket=self.bucket,
            prefix=f"data/{model_name}/",
            endpoint_url=self.endpoint_url,
            access_key_id=self.access_key_id,
            secret_access_key=self.secret_access_key,
            region_name=self.region_name,
            encoding=Encoding.msgpack,
        )
        
        return SimpleStorage(meta_store, resource_store)

# MinIO 或 AWS S3 配置
storage_factory = S3StorageFactory(
    bucket="my-app-storage",
    endpoint_url="http://localhost:9000",  # MinIO，AWS S3 則省略此參數
    access_key_id="minioadmin",
    secret_access_key="minioadmin",
)

crud = AutoCRUD(storage_factory=storage_factory)
```

**特性：**

- ☁️ 完全雲端化，不依賴本地磁碟
- 🔐 ETag 樂觀鎖定防止併發寫入衝突
- 🔄 自動同步 SQLite 資料庫到 S3
- 💾 適合 serverless 或容器化部署

**詳細說明：**

查看 [S3 + SQLite MetaStore 文件](../storage/s3-sqlite-meta-store.md) 了解更多關於 S3SqliteMetaStore 的配置選項和最佳實踐。

### 範例 4：Redis Meta + PostgreSQL Meta（雙層快取）

使用 Redis 作為快速查詢層，PostgreSQL 作為持久化層。

```python
from autocrud.resource_manager.meta_store.redis import RedisMetaStore
from autocrud.resource_manager.meta_store.fast_slow import FastSlowMetaStore

class RedisPgStorageFactory(IStorageFactory):
    """Redis（快）+ PostgreSQL（慢）雙層 MetaStore"""
    
    def __init__(
        self,
        redis_url: str,
        pg_dsn: str,
        data_dir: Path,
    ):
        self.redis_url = redis_url
        self.pg_dsn = pg_dsn
        self.data_dir = Path(data_dir)
    
    def build(self, model_name: str) -> IStorage:
        # 快速層：Redis（記憶體快取）
        fast_store = RedisMetaStore(
            redis_url=self.redis_url,
            prefix=f"{model_name}:",
            encoding=Encoding.msgpack,
        )
        
        # 慢速層：PostgreSQL（持久化）
        slow_store = PostgresMetaStore(
            pg_dsn=self.pg_dsn,
            encoding=Encoding.msgpack,
            table_name=f"meta_{model_name}",
        )
        
        # 組合成雙層 MetaStore
        meta_store = FastSlowMetaStore(
            fast_store=fast_store,
            slow_store=slow_store,
        )
        
        # ResourceStore 使用磁碟
        resource_store = DiskResourceStore(
            rootdir=self.data_dir / model_name
        )
        
        return SimpleStorage(meta_store, resource_store)

# 雙層快取配置
storage_factory = RedisPgStorageFactory(
    redis_url="redis://localhost:6379/0",
    pg_dsn="postgresql://user:password@localhost:5432/autocrud_db",
    data_dir=Path("./data"),
)

crud = AutoCRUD(storage_factory=storage_factory)
crud.add_model(User, indexed_fields=[("email", str), ("department", str)])

# 讀取流程：先查 Redis → 未命中則查 PostgreSQL → 寫回 Redis
# 寫入流程：同時寫入 Redis 和 PostgreSQL
```

**優勢：**

- ⚡⚡⚡ Redis 提供極速讀取
- 💾 PostgreSQL 保證資料持久化
- 🔄 自動快取同步
- 📈 適合高併發讀取場景

### 範例 5：Cached S3 Resource（S3 + 多層快取）

為 S3 加上記憶體和磁碟快取層，減少 S3 存取次數。

```python
from autocrud.resource_manager.resource_store.cached_s3 import CachedS3ResourceStore
from autocrud.resource_manager.resource_store.cache import MemoryCache, DiskCache
from pathlib import Path

class CachedS3StorageFactory(IStorageFactory):
    """帶多層快取的 S3 儲存"""
    
    def __init__(
        self,
        s3_bucket: str,
        s3_endpoint: str,
        cache_dir: Path,
        s3_access_key: str = "minioadmin",
        s3_secret_key: str = "minioadmin",
    ):
        self.s3_bucket = s3_bucket
        self.s3_endpoint = s3_endpoint
        self.cache_dir = Path(cache_dir)
        self.s3_access_key = s3_access_key
        self.s3_secret_key = s3_secret_key
    
    def build(self, model_name: str) -> IStorage:
        # MetaStore 使用記憶體（快速）
        meta_store = MemoryMetaStore()
        
        # 建立快取層
        mem_cache = MemoryCache(max_size=100)  # 最多快取 100 個資源
        disk_cache = DiskCache(
            cache_dir=str(self.cache_dir / model_name)
        )
        
        # CachedS3ResourceStore：S3 + 多層快取
        resource_store = CachedS3ResourceStore(
            caches=[mem_cache, disk_cache],  # 快取鏈：記憶體 → 磁碟 → S3
            ttl_draft=3600,      # Draft 資料快取 1 小時
            ttl_stable=86400,    # Stable 資料快取 24 小時
            bucket=self.s3_bucket,
            prefix=f"{model_name}/",
            endpoint_url=self.s3_endpoint,
            access_key_id=self.s3_access_key,
            secret_access_key=self.s3_secret_key,
            encoding=Encoding.msgpack,
        )
        
        return SimpleStorage(meta_store, resource_store)

# 使用快取 S3
storage_factory = CachedS3StorageFactory(
    s3_bucket="my-app-cache",
    s3_endpoint="http://localhost:9000",  # MinIO 或 AWS S3
    cache_dir=Path("./cache"),
)

crud = AutoCRUD(storage_factory=storage_factory)
crud.add_model(Document)

# 讀取流程：記憶體快取 → 磁碟快取 → S3
# 快取命中時避免 S3 存取，大幅提升效能
```

**快取策略：**

- 🎯 **Draft 資料**：較短 TTL（1小時），因為可能頻繁修改
- 🔒 **Stable 資料**：較長 TTL（24小時），因為不可變
- 💾 **多層快取**：記憶體 → 磁碟 → S3，逐層降級
- 🔄 **自動失效**：TTL 過期自動清理

### 範例 6：進階 Cached S3（訊息佇列同步）

多實例環境下，使用 RabbitMQ 同步快取失效。

```python
from autocrud.resource_manager.resource_store.mq_cached_s3 import MQCachedS3ResourceStore

class MQCachedS3StorageFactory(IStorageFactory):
    """支援多實例快取同步的 S3 儲存"""
    
    def __init__(
        self,
        s3_config: dict,
        cache_dir: Path,
        amqp_url: str = "amqp://guest:guest@localhost:5672",
    ):
        self.s3_config = s3_config
        self.cache_dir = Path(cache_dir)
        self.amqp_url = amqp_url
    
    def build(self, model_name: str) -> IStorage:
        meta_store = MemoryMetaStore()
        
        # MQ-based Cached S3 ResourceStore
        resource_store = MQCachedS3ResourceStore(
            caches=[
                MemoryCache(max_size=100),
                DiskCache(cache_dir=str(self.cache_dir / model_name))
            ],
            amqp_url=self.amqp_url,
            queue_prefix=f"autocrud_{model_name}_",
            ttl_draft=1800,
            ttl_stable=3600,
            **self.s3_config
        )
        
        return SimpleStorage(meta_store, resource_store)

# 多實例部署配置
storage_factory = MQCachedS3StorageFactory(
    s3_config={
        "bucket": "production-data",
        "endpoint_url": "https://s3.amazonaws.com",
        "access_key_id": "YOUR_KEY",
        "secret_access_key": "YOUR_SECRET",
    },
    cache_dir=Path("/var/cache/autocrud"),
    amqp_url="amqp://user:password@rabbitmq.example.com:5672",
)

crud = AutoCRUD(storage_factory=storage_factory)
crud.add_model(Product)

# 當 Instance A 更新資料時，會透過 RabbitMQ 通知所有實例清除快取
# Instance B, C, D... 會自動失效本地快取，下次讀取時更新
```

**適用場景：**

- 🌐 多實例/多伺服器部署
- 🔄 需要快取一致性
- 📡 分散式系統
- ⚖️ 負載平衡環境

## 實際範例

### 範例 1：開發環境快速啟動

```python title="dev.py"
from msgspec import Struct
from fastapi import FastAPI
from autocrud import AutoCRUD

class Article(Struct):
    title: str
    content: str
    published: bool = False

# 開發環境：使用記憶體儲存
crud = AutoCRUD()
crud.add_model(Article)

app = FastAPI()
crud.apply(app)
```

### 範例 2：生產環境配置

```python title="production.py"
from msgspec import Struct
from fastapi import FastAPI
from autocrud import AutoCRUD
from autocrud.resource_manager.storage_factory import DiskStorageFactory
from pathlib import Path
import os

class Article(Struct):
    title: str
    content: str
    published: bool = False

# 生產環境：使用磁碟儲存
data_dir = Path(os.getenv("DATA_DIR", "./production_data"))
storage_factory = DiskStorageFactory(rootdir=data_dir)

crud = AutoCRUD(storage_factory=storage_factory)
crud.add_model(Article)

app = FastAPI()
crud.apply(app)
```

### 範例 3：混合儲存策略

```python title="hybrid.py"
from msgspec import Struct
from datetime import datetime
from autocrud import AutoCRUD
from autocrud.resource_manager.storage_factory import (
    DiskStorageFactory,
    MemoryStorageFactory,
)

class User(Struct):
    username: str
    email: str

class Session(Struct):
    user_id: str
    token: str
    expires_at: datetime

class Article(Struct):
    title: str
    content: str
    author_id: str

crud = AutoCRUD()

# 用戶資料：磁碟儲存（重要資料）
crud.add_model(
    User,
    storage_factory=DiskStorageFactory("./data/users")
)

# Session：記憶體儲存（臨時資料）
crud.add_model(
    Session,
    storage_factory=MemoryStorageFactory()
)

# 文章：磁碟儲存（需要持久化）
crud.add_model(
    Article,
    storage_factory=DiskStorageFactory("./data/articles")
)
```

## 儲存架構對比表

| 儲存方案 | MetaStore | ResourceStore | 適用場景 | 效能 | 成本 |
|---------|-----------|---------------|---------|------|------|
| **Memory** | 記憶體 | 記憶體 | 開發/測試 | ⚡⚡⚡⚡⚡ | 低 |
| **Disk** | 磁碟 | 磁碟 | 小型生產 | ⚡⚡⚡⚡ | 低 |
| **Memory + Disk** | 記憶體 | 磁碟 | 快速搜尋 | ⚡⚡⚡⚡⚡ | 低 |
| **PostgreSQL + S3** | PostgreSQL | S3 | 大型生產 | ⚡⚡⚡⚡ | 中 |
| **Redis + PostgreSQL** | Redis+PG | 磁碟/S3 | 高併發 | ⚡⚡⚡⚡⚡ | 中 |
| **Cached S3** | 記憶體 | S3+快取 | 雲端優先 | ⚡⚡⚡⚡ | 低 |
| **MQ Cached S3** | 記憶體 | S3+快取+MQ | 分散式 | ⚡⚡⚡⚡ | 中 |

## 進階：自定義儲存後端

你可以實作 `IStorageFactory` 介面來建立自定義的儲存後端。

```python
from autocrud.resource_manager.storage_factory import IStorageFactory
from autocrud.resource_manager.basic import IStorage

class CustomStorageFactory(IStorageFactory):
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
    
    def build(self, model_name: str) -> IStorage:
        # 實作你的儲存邏輯
        # 例如：MongoDB, Cassandra, Elasticsearch 等
        pass
```

### 儲存架構說明

AutoCRUD 的儲存層分為三個部分：

1. **MetaStore**: 儲存資源的 metadata、索引和搜尋資訊
2. **ResourceStore**: 儲存資源的實際資料內容
3. **BlobStore**: 儲存二進位大型物件（如圖片、檔案）

這種分離設計讓你可以：

- 使用 SQL 資料庫存放 metadata（快速查詢）
- 使用 Object Storage（如 S3）存放資料內容（低成本）
- 使用 CDN 或專用儲存存放二進位檔案（高效能）

## 效能考量

### Memory Storage

- **讀取速度**: ⚡⚡⚡⚡⚡ 極快
- **寫入速度**: ⚡⚡⚡⚡⚡ 極快
- **資料量限制**: 受限於可用記憶體
- **適用場景**: 開發、測試、快取、臨時資料

### Disk Storage

- **讀取速度**: ⚡⚡⚡⚡ 快
- **寫入速度**: ⚡⚡⚡ 中等
- **資料量限制**: 受限於磁碟空間
- **適用場景**: 生產環境、中小型應用、資料持久化需求

## 常見問題

### Q: 可以在運行時切換儲存後端嗎？

A: 不建議在運行時切換。儲存後端應該在應用啟動時設定，並在整個生命週期內保持不變。

### Q: 如何備份資料？

A: Disk Storage 的資料可以直接複製整個資料目錄。Memory Storage 需要使用 AutoCRUD 的匯出功能。

```python
# 匯出所有資料
await crud.export_all(output_path="./backup.tar.gz")

# 匯入資料
await crud.import_all(input_path="./backup.tar.gz")
```

### Q: 支援哪些資料庫？

A: 目前內建支援記憶體和磁碟儲存。對於 PostgreSQL、MongoDB 等資料庫，你可以透過實作 `IStorageFactory` 介面來自定義。

### Q: Disk Storage 的資料格式是什麼？

A: 預設使用 JSON 格式儲存資料，也可以設定為 MessagePack 以獲得更好的效能和更小的檔案大小。

```python
from autocrud.resource_manager.basic import Encoding

crud = AutoCRUD(
    storage_factory=DiskStorageFactory("./data"),
    encoding=Encoding.msgpack  # 使用 MessagePack
)
```

## 下一步

<div class="grid cards" markdown>

-   :material-database-cog: __了解儲存架構__

    ---

    深入了解 AutoCRUD 的混合儲存架構設計

    [:octicons-arrow-right-24: 架構概覽](../core-concepts/architecture.md)


-   :material-database-cog: __了解儲存架構__

    ---

    比較不同儲存後端的效能表現

    [:octicons-arrow-right-24: 儲存後端效能比較](../benchmarks/index.md)


-   :material-file-export: __資料備份與還原__

    ---

    學習如何備份和還原 AutoCRUD 資料

    [:octicons-arrow-right-24: 備份範例](../examples/index.md)

-   :material-cog: __自定義儲存實作__

    ---

    了解如何實作自定義的儲存後端

    [:octicons-arrow-right-24: API 參考](../reference/resource-manager.md)

</div>
