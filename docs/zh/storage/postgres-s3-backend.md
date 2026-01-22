# PostgreSQL + S3 後端配置指南

## 概述

PostgreSQL + S3 後端組合提供了生產級的儲存解決方案，適用於需要高可用性、可擴展性和強大查詢能力的中大型應用。

**架構特點:**

- **PostgreSQL**: 儲存元數據（metadata），支援複雜索引和快速查詢
- **S3**: 儲存資源數據（resource data）和二進制檔案（blob）
- **適用場景**: 需要處理 10,000+ 資源的中大型應用

## 快速開始

### 1. 安裝依賴

```bash
# PostgreSQL driver
uv add psycopg2-binary

# AWS SDK (for S3)
uv add boto3
```

### 2. 準備基礎設施

#### PostgreSQL 設定

```bash
# Docker 快速啟動 PostgreSQL
docker run -d \
  --name postgres-autocrud \
  -e POSTGRES_USER=gameuser \
  -e POSTGRES_PASSWORD=gamepass \
  -e POSTGRES_DB=gamedb \
  -p 5432:5432 \
  postgres:15
```

#### S3 設定

**選項 A: 使用 AWS S3**

```bash
# 設定 AWS credentials
export AWS_ACCESS_KEY_ID="your_access_key"
export AWS_SECRET_ACCESS_KEY="your_secret_key"
export S3_BUCKET="my-app-data"
export S3_REGION="us-east-1"
```

**選項 B: 使用 MinIO (本地 S3 替代)**

```bash
# Docker 啟動 MinIO
docker run -d \
  --name minio-autocrud \
  -p 9000:9000 \
  -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin \
  -e MINIO_ROOT_PASSWORD=minioadmin \
  minio/minio server /data --console-address ":9001"

# 設定 MinIO endpoint
export AWS_ACCESS_KEY_ID="minioadmin"
export AWS_SECRET_ACCESS_KEY="minioadmin"
export AWS_ENDPOINT_URL="http://localhost:9000"
export S3_BUCKET="autocrud-data"
```

### 3. 基本使用

```python
import os
from autocrud.crud.core import AutoCRUD
from autocrud.resource_manager.storage_factory import PostgreSQLStorageFactory
from autocrud.resource_manager.basic import Encoding

# 建立 PostgreSQL + S3 storage factory
storage_factory = PostgreSQLStorageFactory(
    connection_string=os.getenv(
        "POSTGRES_DSN",
        "postgresql://admin:password@localhost:5432/your_database"
    ),
    s3_bucket=os.getenv("S3_BUCKET", "my-app-data"),
    s3_region=os.getenv("S3_REGION", "us-east-1"),
    s3_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"),
    s3_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin"),
    s3_endpoint_url=os.getenv("S3_ENDPOINT_URL", "http://localhost:9000"),  # None for AWS S3, "http://localhost:9000" for MinIO
    encoding=Encoding.msgpack,  # 使用 msgpack 以提升效能
    table_prefix="app_",  # 表格前綴，避免命名衝突
    blob_bucket="my-app-blobs",  # 可選：使用不同的 bucket 存放 blob
    blob_prefix="files/",  # blob 儲存路徑前綴
)

# 初始化 AutoCRUD
crud = AutoCRUD(storage_factory=storage_factory)

# 註冊模型（支援索引欄位）
from msgspec import Struct
from enum import Enum

class Priority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class Task(Struct):
    title: str
    priority: Priority
    assignee: str
    completed: bool = False

crud.add_model(
    Task,
    indexed_fields=[
        ("priority", str),  # Enum 會自動轉為字串
        ("assignee", str),
        ("completed", bool),
    ]
)
```

## 進階配置

### MinIO 設定

使用 MinIO 作為本地 S3 替代方案：

```python
storage_factory = PostgreSQLStorageFactory(
    connection_string="postgresql://admin:password@localhost:5432/your_database",
    s3_bucket="autocrud-data",
    s3_region="us-east-1",
    s3_access_key_id="minioadmin",
    s3_secret_access_key="minioadmin",
    s3_endpoint_url="http://localhost:9000",  # MinIO endpoint
    encoding=Encoding.msgpack,
)
```

### AWS S3 設定

使用 AWS S3 (從環境變數讀取憑證)：

```python
import os

storage_factory = PostgreSQLStorageFactory(
    connection_string=os.getenv("POSTGRES_DSN"),
    s3_bucket="production-app-data",
    s3_region="ap-northeast-1",  # Tokyo region
    s3_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    s3_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    s3_endpoint_url=None,  # Use AWS S3
    encoding=Encoding.msgpack,
    table_prefix="prod_",
    blob_bucket="production-app-blobs",  # 分離 blob 儲存
)
```

### 自訂 boto3 客戶端參數

傳遞額外的 boto3 參數（如 SSL、超時設定等）：

```python
storage_factory = PostgreSQLStorageFactory(
    connection_string="postgresql://admin:password@localhost:5432/your_database",
    s3_bucket="my-bucket",
    s3_region="us-east-1",
    s3_access_key_id="...",
    s3_secret_access_key="...",
    s3_client_kwargs={
        "use_ssl": True,
        "verify": "/path/to/ca-bundle.crt",  # 自訂 CA 憑證
        "config": {
            "connect_timeout": 5,
            "read_timeout": 60,
            "retries": {"max_attempts": 3},
        },
    },
)
```

### 連線池設定

PostgreSQL MetaStore 預設使用連線池（1-10 連線）。如需調整，可以修改 `PostgresMetaStore`:

```python
from autocrud.resource_manager.meta_store.postgres import PostgresMetaStore

# 自訂連線池大小
meta_store = PostgresMetaStore(
    pg_dsn="postgresql://admin:password@localhost:5432/your_database",
    encoding=Encoding.msgpack,
    table_name="custom_table_meta",
)
```

### 索引策略

PostgreSQL 支援多種索引類型，AutoCRUD 會自動為 `indexed_fields` 建立 B-tree 索引:

```python
# 範例：為多個欄位建立索引
crud.add_model(
    User,
    indexed_fields=[
        ("email", str),          # 唯一性查詢
        ("age", int),            # 範圍查詢
        ("created_at", int),     # 時間排序
        ("status", str),         # 狀態過濾
    ]
)
```

**索引最佳實踐:**

- ✅ 常用於搜尋條件的欄位
- ✅ 需要排序的欄位
- ✅ 外鍵關聯欄位
- ❌ 避免索引過多（影響寫入效能）
- ❌ 避免索引選擇性低的欄位（如 boolean）

## 完整範例

參考 [`examples/rpg_game_postgres_s3_api.py`](https://github.com/HYChou0515/autocrud/blob/master/examples/rpg_game_postgres_s3_api.py) 查看完整的 RPG 遊戲 API 實作，包含:

- Character、Item、Quest 模型定義
- 索引欄位配置
- 資料 seeding
- FastAPI 整合
- 搜尋與查詢範例

## 相關文件

- [儲存架構總覽](index.md)
- [S3 後端配置](s3-backend.md)
- [自訂儲存後端](custom-storage.md)
