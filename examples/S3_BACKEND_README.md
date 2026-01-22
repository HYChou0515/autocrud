# S3 Backend 範例

這個範例展示如何使用 AutoCRUD 搭配 S3 作為完整的 backend 存儲。

## 🏗️ 架構

使用 `S3StorageFactory` 會建立：

- **S3SqliteMetaStore**: SQLite 資料庫存於 S3，支援 ETag-based 樂觀鎖定
- **S3ResourceStore**: 資源數據直接存於 S3
- **S3BlobStore**: 二進制數據（如圖片）存於 S3

## 📋 前置需求

### 選項 1: 使用 MinIO (本地開發)

MinIO 是一個 S3 相容的物件存儲，適合本地開發和測試。

```bash
# 使用 Docker 啟動 MinIO
docker run -p 9000:9000 -p 9001:9001 \
    -e "MINIO_ROOT_USER=minioadmin" \
    -e "MINIO_ROOT_PASSWORD=minioadmin" \
    quay.io/minio/minio server /data --console-address ":9001"
```

MinIO Console: http://localhost:9001 (帳號: minioadmin / minioadmin)

### 選項 2: 使用 AWS S3

需要準備：
- AWS Access Key ID
- AWS Secret Access Key  
- S3 Bucket 名稱
- AWS Region

## 🚀 執行範例

```bash
# 安裝依賴
uv sync

# 執行範例
uv run python examples/rpg_game_s3_api.py
```

程式會詢問：
1. 使用 AWS S3 還是 MinIO
2. S3 配置參數（endpoint、bucket、credentials）
3. 是否創建示範數據
4. 是否展示 S3 特性

## 📊 功能展示

### 1. 基本 CRUD 操作

所有 CRUD 操作的數據都會存於 S3：

```python
from autocrud import AutoCRUD
from autocrud.resource_manager.s3_storage_factory import S3StorageFactory

# 建立 S3StorageFactory
storage_factory = S3StorageFactory(
    bucket="my-bucket",
    endpoint_url="http://localhost:9000",  # MinIO
    prefix="my-app/",
)

# 建立 AutoCRUD
crud = AutoCRUD(storage_factory=storage_factory)
crud.add_model(Character, indexed_fields=[("level", int)])
```

### 2. 版本控制

所有版本歷史都存於 S3：

```python
# 建立新版本
with manager.meta_provide("user", dt.datetime.now()):
    new_rev = manager.create_new_revision(resource_id)
    manager.modify(new_rev.info.uid, modified_data)
    manager.switch(new_rev.info.uid)
```

### 3. 二進制數據存儲

圖片等二進制數據會自動存到 S3 BlobStore：

```python
from autocrud.types import Binary

class Equipment(Struct):
    name: str
    icon: Binary | None = None  # 會自動存到 S3

# 建立包含圖片的裝備
equipment = Equipment(
    name="神劍",
    icon=Binary(data=image_bytes)
)
```

### 4. 使用 QueryBuilder 搜尋

搜尋會使用存於 S3 的 SQLite 索引：

```python
from autocrud.query import QB

# 搜尋高等級角色
query = QB["level"].gte(80).sort("-level").limit(10)
results = manager.search_resources(query)
```

## 🔍 S3 存儲結構

在 S3 bucket 中，數據會以下列結構存儲：

```
my-bucket/
├── rpg-game/                    # prefix
│   ├── character/               # model name
│   │   ├── meta.db             # SQLite 資料庫 (元數據 + 索引)
│   │   └── resources/          # 資源數據
│   │       ├── resource/       # 資源索引
│   │       │   └── {resource_id}/
│   │       │       └── {revision_id}/
│   │       └── store/          # 實際數據
│   │           └── {uid}/
│   │               ├── data    # 資源內容
│   │               └── info    # 修訂資訊
│   ├── guild/
│   │   └── ...
│   └── blobs/                  # 二進制數據
│       └── {file_id}           # 以 content hash 為檔名
```

## ⚙️ 配置選項

### S3StorageFactory 參數

```python
S3StorageFactory(
    bucket="my-bucket",              # S3 bucket 名稱
    access_key_id="...",             # AWS Access Key
    secret_access_key="...",         # AWS Secret Key
    region_name="us-east-1",         # AWS Region
    endpoint_url=None,               # 自訂 endpoint (MinIO)
    prefix="",                       # S3 key 前綴
    encoding=Encoding.json,          # json 或 msgpack
    auto_sync=True,                  # 自動同步 SQLite 到 S3
    sync_interval=0,                 # 同步間隔（秒）
    enable_locking=True,             # ETag-based 樂觀鎖定
    auto_reload_on_conflict=False,   # 衝突時自動重載
    check_etag_on_read=True,         # 讀取前檢查 ETag
)
```

### 同步策略

- `sync_interval=0`: 立即同步（預設，適合小型應用）
- `sync_interval=5`: 每 5 秒同步一次（減少 S3 請求）
- `auto_sync=False`: 手動控制同步

### 鎖定機制

- `enable_locking=True`: 使用 ETag 防止並發寫入衝突
- `auto_reload_on_conflict=True`: 衝突時自動從 S3 重載

## 🔧 API 端點

範例啟動後可存取：

- **OpenAPI 文檔**: http://localhost:8000/docs
- **ReDoc 文檔**: http://localhost:8000/redoc
- **角色 API**: http://localhost:8000/character/data
- **公會 API**: http://localhost:8000/guild/data
- **裝備 API**: http://localhost:8000/equipment/data

## 📝 注意事項

1. **索引欄位**: 需要搜尋的欄位必須在 `indexed_fields` 中定義
2. **同步延遲**: 使用 `sync_interval > 0` 時，可能有短暫的資料不一致
3. **並發控制**: 啟用 `enable_locking` 可防止並發寫入衝突
4. **成本考量**: AWS S3 會按請求次數和存儲量收費

## 🧪 測試

```bash
# 執行 S3StorageFactory 測試（需要 MinIO 運行）
uv run pytest tests/test_s3_storage_factory.py -v

# 執行所有測試
make test
```

## 🌟 優勢

- ✅ **無伺服器**: 不需要獨立的資料庫伺服器
- ✅ **無限擴展**: S3 的容量和請求數可無限擴展
- ✅ **高可用性**: S3 提供 99.999999999% 的耐久性
- ✅ **版本控制**: 內建完整的版本追蹤
- ✅ **成本效益**: 按使用量付費，閒置時成本低
- ✅ **簡單部署**: 無需管理資料庫實例

## 📚 相關文件

- [AutoCRUD 文檔](../../README.md)
- [QueryBuilder 使用指南](../../docs/query-builder.md)
- [MinIO 官方文檔](https://min.io/docs/minio/linux/index.html)
- [AWS S3 文檔](https://docs.aws.amazon.com/s3/)
