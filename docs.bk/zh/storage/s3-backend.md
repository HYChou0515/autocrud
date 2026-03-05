# S3 Backend 完整指南

本指南展示如何使用 AutoCRUD 搭配 S3 作為完整的 backend 存儲。

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

## 🚀 快速開始

```python
import os
from autocrud import AutoCRUD
from autocrud.resource_manager.storage_factory import S3StorageFactory
from msgspec import Struct

# 定義資料模型
class User(Struct):
    name: str
    email: str
    age: int

# 建立 S3StorageFactory
storage_factory = S3StorageFactory(
    bucket=os.getenv("S3_BUCKET", "my-bucket"),
    endpoint_url=os.getenv("S3_ENDPOINT_URL", "http://localhost:9000"),  # MinIO
    access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"),
    secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin"),
    region_name=os.getenv("AWS_REGION", "us-east-1"),
    prefix="my-app/",
)

# 建立 AutoCRUD
crud = AutoCRUD(storage_factory=storage_factory)
crud.add_model(User, indexed_fields=[("age", int)])

# 取得 ResourceManager
manager = crud.get_resource_manager(User)

# CRUD 操作
import datetime as dt
with manager.meta_provide("admin", dt.datetime.now()):
    # 建立
    info = manager.create(User(name="Alice", email="alice@example.com", age=30))
    
    # 讀取
    resource = manager.get(info.resource_id)
    print(resource.data)  # User(name='Alice', email='alice@example.com', age=30)
    
    # 更新
    manager.update(info.resource_id, User(name="Alice", email="new@example.com", age=31))
    
    # 刪除
    manager.delete(info.resource_id)
```

## 📊 進階功能

### 1. 版本控制

所有版本歷史都存於 S3：

```python
import datetime as dt

# 建立初始版本
with manager.meta_provide("user", dt.datetime.now()):
    info = manager.create(User(name="Bob", email="bob@example.com", age=25))

# 更新資料（創建新版本）
with manager.meta_provide("user", dt.datetime.now()):
    manager.update(
        info.resource_id, 
        User(name="Bob", email="bob.new@example.com", age=26)
    )

# 查看版本歷史
revisions = manager.list_revisions(info.resource_id)
for rev_id in revisions:
    print(f"Revision: {rev_id}")
```

### 2. 二進制數據存儲

圖片等二進制數據會自動存到 S3 BlobStore：

```python
import datetime as dt
from autocrud.types import Binary
from msgspec import Struct

class Product(Struct):
    name: str
    price: float
    image: Binary | None = None

# 註冊模型
crud.add_model(Product)
manager = crud.get_resource_manager(Product)

# 建立包含圖片的產品
with manager.meta_provide("admin", dt.datetime.now()):
    image_data = open("product.jpg", "rb").read()
    product = Product(
        name="筆電",
        price=999.99,
        image=Binary(data=image_data, content_type="image/jpeg")
    )
    info = manager.create(product)

# 讀取時二進制數據會自動從 S3 載入
resource = manager.get(info.resource_id)
with open("downloaded.jpg", "wb") as f:
    f.write(resource.data.image.data)
```

### 3. 使用 QueryBuilder 搜尋

搜尋會使用存於 S3 的 SQLite 索引：

```python
from autocrud.query import QB

# 搜尋年齡大於等於 25 的用戶，按年齡降序排列
query = QB["age"].gte(25).sort("-age").limit(10)
metas = manager.search_resources(query)
results = [manager.get(meta.resource_id) for meta in metas]

# 複雜查詢
query = (
    QB["age"].between(20, 30)
    .filter(QB["email"].contains("@example.com"))
    .sort("-age")
)
results = manager.search_resources(query)
```

### 4. FastAPI 整合

```python
import os
from fastapi import FastAPI
from autocrud import AutoCRUD
from autocrud.resource_manager.storage_factory import S3StorageFactory
from msgspec import Struct

class User(Struct):
    name: str
    email: str
    age: int

# 初始化 AutoCRUD
storage_factory = S3StorageFactory(
    bucket=os.getenv("S3_BUCKET", "my-bucket"),
    endpoint_url=os.getenv("S3_ENDPOINT_URL", "http://localhost:9000"),
    access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"),
    secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin"),
    region_name=os.getenv("AWS_REGION", "us-east-1"),
)
crud = AutoCRUD(storage_factory=storage_factory)
crud.add_model(User, indexed_fields=[("age", int)])

app = FastAPI()

# 將 AutoCRUD 路由掛載到 FastAPI
crud.apply(app)
crud.openapi(app)

# 啟動 API
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

API 端點會自動產生：
- `POST /user/data` - 建立用戶
- `GET /user/data/{resource_id}` - 讀取用戶
- `PUT /user/data/{resource_id}` - 更新用戶
- `DELETE /user/data/{resource_id}` - 刪除用戶
- `POST /user/search` - 搜尋用戶

## 🔍 S3 存儲結構

在 S3 bucket 中，數據會以下列結構存儲：

```
my-bucket/
├── my-app/                      # prefix
│   ├── user/                    # model name
│   │   ├── meta.db             # SQLite 資料庫 (元數據 + 索引)
│   │   └── resources/          # 資源數據
│   │       ├── resource/       # 資源索引
│   │       │   └── {resource_id}/
│   │       │       └── {revision_id}/
│   │       └── store/          # 實際數據
│   │           └── {uid}/
│   │               ├── data    # 資源內容
│   │               └── info    # 修訂資訊
│   ├── product/
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

**立即同步（預設）**
```python
storage_factory = S3StorageFactory(
    bucket="my-bucket",
    sync_interval=0,  # 每次操作後立即同步
    auto_sync=True
)
```
✅ 適合：小型應用、資料一致性要求高  
❌ 缺點：S3 請求次數較多

**定期同步**
```python
storage_factory = S3StorageFactory(
    bucket="my-bucket",
    sync_interval=5,  # 每 5 秒同步一次
    auto_sync=True
)
```
✅ 適合：高流量應用、降低成本  
❌ 缺點：可能有短暫的資料不一致


### 鎖定機制

**啟用樂觀鎖定（推薦）**
```python
storage_factory = S3StorageFactory(
    bucket="my-bucket",
    enable_locking=True,  # 使用 ETag 防止並發寫入衝突
    auto_reload_on_conflict=True  # 衝突時自動重載
)
```
✅ 防止多個實例同時寫入造成資料覆蓋  
✅ 適合：多實例部署、高並發場景

**關閉鎖定**
```python
storage_factory = S3StorageFactory(
    bucket="my-bucket",
    enable_locking=False  # 不檢查 ETag
)
```
⚠️ 僅適合單實例部署或開發環境

## 📝 完整範例

完整的 RPG 遊戲範例請參考：[examples/rpg_game_s3_api.py](../../../examples/rpg_game_s3_api.py)

執行範例：
```bash
# 先啟動 MinIO
docker run -p 9000:9000 -p 9001:9001 \
    -e "MINIO_ROOT_USER=minioadmin" \
    -e "MINIO_ROOT_PASSWORD=minioadmin" \
    quay.io/minio/minio server /data --console-address ":9001"

# 執行範例
uv run python examples/rpg_game_s3_api.py
```

## 🧪 測試

```bash
# 執行 S3StorageFactory 測試（需要 MinIO 運行）
uv run pytest tests/test_s3_storage_factory.py -v

# 執行所有測試
make test
```

## 技術特性

### 架構優勢

- **分散式儲存**: 元數據（SQLite）、資源數據、二進制檔案分別存於 S3，支援水平擴展
- **版本追蹤**: AutoCRUD 自動記錄所有修訂歷史，支援回溯至任意版本
- **去重優化**: 二進制數據使用內容雜湊去重，相同檔案只存一份
- **並發控制**: 基於 S3 ETag 的樂觀鎖定，避免多實例寫入衝突


## ⚠️ 注意事項

1. **索引欄位**: 需要搜尋的欄位必須在 `indexed_fields` 中定義
2. **同步延遲**: 使用 `sync_interval > 0` 時，可能有短暫的資料不一致
3. **並發控制**: 啟用 `enable_locking` 可防止並發寫入衝突
4. **成本考量**: AWS S3 會按請求次數和存儲量收費
5. **性能考量**: S3 存取速度比本地資料庫慢，不適合極高頻查詢場景

## 📚 相關文件

- [S3SqliteMetaStore 詳細說明](s3-sqlite-meta-store.md)
- [S3 鎖定機制](s3-sqlite-locking.md)
- [QueryBuilder 使用指南](../core-concepts/query-builder.md)
