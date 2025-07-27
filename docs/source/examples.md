# 範例集合

這裡提供了 AutoCRUD 的各種使用範例，從簡單到複雜的實際應用場景。

## 基礎範例

### 1. 簡單的使用者管理

```python
from autocrud import SingleModelCRUD
from autocrud.storage import MemoryStorage
from dataclasses import dataclass
from typing import Optional

@dataclass
class User:
    id: str  # 必需的 ID 欄位
    name: str
    email: str
    age: Optional[int] = None

# 設定
storage = MemoryStorage()
crud = SingleModelCRUD(model=User, storage=storage, resource_name="users")

# 建立使用者
user_id = crud.create({
    "name": "Alice",
    "email": "alice@example.com", 
    "age": 30
})
print(f"建立使用者 ID: {user_id}")

# 查詢使用者
user = crud.get(user_id)
print(f"查詢到的使用者: {user}")

# 列出所有使用者（使用分頁）
from autocrud import ListQueryParams
query_params = ListQueryParams(page=1, page_size=10)
result = crud.list(query_params)
print(f"使用者列表: {result.items}")
print(f"總數: {result.total}")
```

### 2. 使用 Pydantic 模型

```python
from pydantic import BaseModel, EmailStr, validator
from autocrud import SingleModelCRUD
from autocrud.storage import DiskStorage

class Product(BaseModel):
    id: str  # 必需的 ID 欄位
    name: str
    price: float
    category: str
    
    @validator('price')
    def price_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('價格必須大於 0')
        return v

# 使用硬碟儲存
storage = DiskStorage(storage_dir="./products", serializer_type="json")
product_crud = SingleModelCRUD(model=Product, storage=storage, resource_name="products")

# 建立產品
product_id = product_crud.create({
    "name": "筆記型電腦",
    "price": 999.99,
    "category": "電子產品"
})
```

## 多模型應用

### 3. 電商系統

```python
from autocrud import AutoCRUD, MetadataConfig
from autocrud.storage import DiskStorage
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

@dataclass
class User:
    id: str
    name: str
    email: str
    is_active: bool = True

@dataclass  
class Product:
    id: str
    name: str
    price: float
    category: str
    stock: int = 0

@dataclass
class Order:
    id: str
    user_id: str
    product_ids: List[str]
    total_amount: float
    status: str = "pending"

# 設定多模型系統（啟用時間戳）
metadata_config = MetadataConfig(enable_timestamps=True)
multi_crud = AutoCRUD(metadata_config=metadata_config)

# 註冊模型
user_crud = multi_crud.register_model(User)
product_crud = multi_crud.register_model(Product)
order_crud = multi_crud.register_model(Order)

# 建立使用者
user_id = multi_crud.create("users", {
    "name": "John Doe",
    "email": "john@example.com"
})

# 建立產品
product_id = multi_crud.create("products", {
    "name": "iPhone 15",
    "price": 999.99,
    "category": "手機",
    "stock": 50
})

# 建立訂單
order_id = multi_crud.create("orders", {
    "user_id": user_id,
    "product_ids": [product_id],
    "total_amount": 999.99
})
```

## FastAPI 整合

### 4. 完整的 API 伺服器

```python
from autocrud import SingleModelCRUD
from autocrud.storage import DiskStorage
from autocrud.fastapi_generator import FastAPIGenerator
from pydantic import BaseModel
from typing import Optional

class Task(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    completed: bool = False

# 設定 CRUD
storage = DiskStorage(storage_dir="./tasks")
task_crud = SingleModelCRUD(model=Task, storage=storage, resource_name="tasks")

# 使用 FastAPIGenerator 建立應用
generator = FastAPIGenerator()
app = generator.create_app(
    crud_systems=[task_crud],
    title="任務管理 API",
    description="簡單的任務管理系統",
    version="1.0.0"
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### 5. 多模型 API 伺服器

```python
from autocrud import AutoCRUD
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class User(BaseModel):  
    id: str
    name: str
    email: EmailStr

class Post(BaseModel):
    id: str
    title: str
    content: str
    author_id: str
    published: bool = False

# 設定
multi_crud = AutoCRUD()

# 註冊模型
multi_crud.register_model(User)
multi_crud.register_model(Post)

# 建立 API
app = multi_crud.create_fastapi_app(
    title="部落格 API",
    description="使用者和貼文管理",
    prefix="/api/v1"
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

## 進階用法

### 6. 自訂 ID 產生器

```python
from autocrud import SingleModelCRUD
from autocrud.storage import MemoryStorage
from dataclasses import dataclass
import uuid
import time

@dataclass
class User:
    id: str
    name: str
    email: str

def custom_id_generator():
    """產生基於時間戳的 ID"""
    timestamp = int(time.time())
    random_part = str(uuid.uuid4())[:8]
    return f"{timestamp}-{random_part}"

storage = MemoryStorage()
crud = SingleModelCRUD(
    model=User,
    storage=storage,
    resource_name="users",
    id_generator=custom_id_generator
)

user_id = crud.create({
    "name": "測試使用者",
    "email": "test@example.com"
})
print(f"產生的 ID: {user_id}")
```

### 7. 插件系統範例

```python
from autocrud import (
    AutoCRUD, BaseRoutePlugin, PluginRouteConfig, 
    RouteMethod, plugin_manager
)
from fastapi import BackgroundTasks
from dataclasses import dataclass

@dataclass
class User:
    id: str
    name: str
    email: str

class StatsPlugin(BaseRoutePlugin):
    """統計資訊插件"""
    
    def __init__(self):
        super().__init__("stats", "1.0.0")
    
    def get_routes(self, crud):
        async def stats_handler(crud, background_tasks: BackgroundTasks):
            # 獲取統計資訊
            total = crud.count()
            return {
                "resource": crud.resource_name,
                "total_items": total,
                "model_type": crud.model.__name__
            }
        
        return [PluginRouteConfig(
            name="stats",
            path="/stats",
            method=RouteMethod.GET,
            handler=stats_handler,
            summary="獲取統計資訊",
            priority=1
        )]

# 註冊自訂插件
plugin_manager.register_plugin(StatsPlugin())

# 建立 AutoCRUD 系統
multi_crud = AutoCRUD()
multi_crud.register_model(User)

# 建立 API（會包含自訂的統計端點）
app = multi_crud.create_fastapi_app(title="使用者 API with Stats")
```

### 8. 高級查詢範例

```python
from autocrud import SingleModelCRUD, ListQueryParams, SortOrder
from autocrud.storage import MemoryStorage
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

@dataclass
class User:
    id: str
    name: str
    email: str
    created_time: datetime
    age: int

# 建立測試資料
storage = MemoryStorage()
crud = SingleModelCRUD(model=User, storage=storage, resource_name="users")

# 創建測試使用者
now = datetime.now(timezone.utc)
for i in range(10):
    crud.create({
        "name": f"User{i}",
        "email": f"user{i}@example.com",
        "age": 20 + i,
        "created_time": now - timedelta(days=i)
    })

# 分頁查詢
query_params = ListQueryParams(
    page=1,
    page_size=5,
    sort_by="name",
    sort_order=SortOrder.ASC
)
result = crud.list(query_params)
print(f"第一頁使用者: {[user['name'] for user in result.items]}")

# 時間範圍查詢  
query_params = ListQueryParams(
    created_time_start=now - timedelta(days=3),
    created_time_end=now,
    sort_by="created_time",
    sort_order=SortOrder.DESC
)
recent_users = crud.list(query_params)
print(f"最近3天的使用者: {len(recent_users.items)}")
```

### 9. 高級更新操作

```python
from autocrud import AdvancedUpdater, set_value, list_add, list_remove
from dataclasses import dataclass
from typing import List

@dataclass
class User:
    id: str
    name: str
    tags: List[str]
    metadata: dict

# 建立使用者
user_id = crud.create({
    "name": "Alice",
    "tags": ["user", "active"],
    "metadata": {"level": 1, "points": 100}
})

# 使用高級更新器
updater = AdvancedUpdater()

# 定義更新操作
operations = [
    set_value("name", "Alice Smith"),
    list_add("tags", "premium"),
    list_remove("tags", "active"),
    dict_update("metadata", {"level": 2, "last_login": "2024-01-01"})
]

# 執行原子更新
success = updater.update(crud, user_id, operations)
print(f"更新成功: {success}")

updated_user = crud.get(user_id)
print(f"更新後的使用者: {updated_user}")
```

# JSON 序列化 (預設)
json_storage = DiskStorage(
    storage_dir="./data_json",
    serializer=SerializerFactory.create("json")
)

# Pickle 序列化
pickle_storage = DiskStorage(
    storage_dir="./data_pickle",
    serializer=SerializerFactory.create("pickle")
)

# MessagePack 序列化 (需要安裝 msgpack)
try:
    msgpack_storage = DiskStorage(
        storage_dir="./data_msgpack",
        serializer=SerializerFactory.create("msgpack")
    )
except ImportError:
    print("msgpack 未安裝，跳過 MessagePack 範例")
```

### 8. 錯誤處理

```python
from autocrud import SingleModelCRUD
from autocrud.exceptions import ValidationError, StorageError
from autocrud.storage import MemoryStorage

storage = MemoryStorage()
crud = SingleModelCRUD(model=User, storage=storage, resource_name="users")

try:
    # 嘗試建立無效的使用者
    user_id = crud.create({
        "name": "",  # 空名稱
        "email": "invalid-email"  # 無效的 email
    })
except ValidationError as e:
    print(f"驗證錯誤: {e}")
except StorageError as e:
    print(f"儲存錯誤: {e}")
except Exception as e:
    print(f"其他錯誤: {e}")
```

### 9. 資料匯入匯出

```python
from autocrud import SingleModelCRUD
from autocrud.storage import DiskStorage
import json

storage = DiskStorage(storage_dir="./users")
crud = SingleModelCRUD(model=User, storage=storage, resource_name="users")

# 批次匯入
users_data = [
    {"name": "Alice", "email": "alice@example.com", "age": 30},
    {"name": "Bob", "email": "bob@example.com", "age": 25},
    {"name": "Charlie", "email": "charlie@example.com", "age": 35}
]

created_ids = []
for user_data in users_data:
    user_id = crud.create(user_data)
    created_ids.append(user_id)

# 匯出所有資料
all_users = crud.list_all()
with open("users_backup.json", "w", encoding="utf-8") as f:
    json.dump(all_users, f, ensure_ascii=False, indent=2)

print(f"匯出了 {len(all_users)} 個使用者")
```

### 10. 效能測試

```python
from autocrud import SingleModelCRUD
from autocrud.storage import MemoryStorage
import time

storage = MemoryStorage()
crud = SingleModelCRUD(model=User, storage=storage, resource_name="users")

# 批次建立測試
start_time = time.time()
created_ids = []
for i in range(1000):
    user_id = crud.create({
        "name": f"User {i}",
        "email": f"user{i}@example.com",
        "age": 20 + (i % 50)
    })
    created_ids.append(user_id)

create_time = time.time() - start_time
print(f"建立 1000 個使用者耗時: {create_time:.2f} 秒")

# 查詢測試
start_time = time.time()
all_users = crud.list_all()
query_time = time.time() - start_time
print(f"查詢 {len(all_users)} 個使用者耗時: {query_time:.4f} 秒")
```

## 部署範例

### 11. Docker 部署

建立 `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

建立 `docker-compose.yml`:

```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
    environment:
      - STORAGE_DIR=/app/data
```

### 12. 生產環境設定

```python
from autocrud import AutoCRUD
from autocrud.storage import DiskStorage
import os
from pathlib import Path

# 生產環境設定
STORAGE_DIR = os.environ.get("STORAGE_DIR", "./production_data")
Path(STORAGE_DIR).mkdir(parents=True, exist_ok=True)

# 使用 JSON 序列化以便於除錯
multi_crud = AutoCRUD()
multi_crud.register_model(User)
multi_crud.register_model(Product)
multi_crud.register_model(Order)

app = multi_crud.create_fastapi_app(
    title="生產環境 API",
    description="電商平台 API",
    version="2.0.0",
    prefix="/api/v2"
)

# 新增健康檢查端點
@app.get("/health")
def health_check():
    return {"status": "健康", "timestamp": datetime.now().isoformat()}
```

這些範例涵蓋了 AutoCRUD 的主要使用場景，從簡單的 CRUD 操作到複雜的多模型應用和生產環境部署。
