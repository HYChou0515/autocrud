# 範例集合

這裡提供了 AutoCRUD 的各種使用範例，從簡單到複雜的實際應用場景。

## 基礎範例

### 1. 簡單的使用者管理

```python
from autocrud import AutoCRUD
from autocrud.storage import MemoryStorage
from dataclasses import dataclass
from typing import Optional

@dataclass
class User:
    name: str
    email: str
    age: Optional[int] = None

# 設定
storage = MemoryStorage()
crud = AutoCRUD(model=User, storage=storage)

# 建立使用者
user = crud.create({
    "name": "Alice",
    "email": "alice@example.com",
    "age": 30
})
print(f"建立使用者: {user}")

# 查詢所有使用者
users = crud.list_all()
print(f"所有使用者: {users}")
```

### 2. 使用 Pydantic 模型

```python
from pydantic import BaseModel, EmailStr, validator
from autocrud import AutoCRUD
from autocrud.storage import DiskStorage

class Product(BaseModel):
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
product_crud = AutoCRUD(model=Product, storage=storage)

# 建立產品
product = product_crud.create({
    "name": "筆記型電腦",
    "price": 999.99,
    "category": "電子產品"
})
```

## 多模型應用

### 3. 電商系統

```python
from autocrud import MultiModelAutoCRUD
from autocrud.storage import DiskStorage
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

@dataclass
class User:
    name: str
    email: str
    created_at: datetime
    is_active: bool = True

@dataclass
class Product:
    name: str
    price: float
    category: str
    stock: int = 0

@dataclass
class Order:
    user_id: str
    product_ids: List[str]
    total_amount: float
    status: str = "pending"
    created_at: datetime = None

# 設定多模型系統
storage = DiskStorage(storage_dir="./ecommerce")
multi_crud = MultiModelAutoCRUD(storage)

# 註冊模型
multi_crud.register_model(User)
multi_crud.register_model(Product)
multi_crud.register_model(Order)

# 建立使用者
user = multi_crud.create("users", {
    "name": "John Doe",
    "email": "john@example.com",
    "created_at": datetime.now()
})

# 建立產品
product = multi_crud.create("products", {
    "name": "iPhone 15",
    "price": 999.99,
    "category": "手機",
    "stock": 50
})

# 建立訂單
order = multi_crud.create("orders", {
    "user_id": user["id"],
    "product_ids": [product["id"]],
    "total_amount": 999.99,
    "created_at": datetime.now()
})
```

## FastAPI 整合

### 4. 完整的 API 伺服器

```python
from autocrud import AutoCRUD
from autocrud.storage import DiskStorage
from pydantic import BaseModel
from fastapi import FastAPI
from typing import Optional

class Task(BaseModel):
    title: str
    description: Optional[str] = None
    completed: bool = False

# 設定 CRUD
storage = DiskStorage(storage_dir="./tasks")
task_crud = AutoCRUD(model=Task, storage=storage)

# 建立 FastAPI 應用
app = task_crud.create_fastapi_app(
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
from autocrud import MultiModelAutoCRUD
from autocrud.storage import DiskStorage
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class User(BaseModel):
    name: str
    email: EmailStr
    created_at: datetime = datetime.now()

class Post(BaseModel):
    title: str
    content: str
    author_id: str
    published: bool = False
    created_at: datetime = datetime.now()

# 設定
storage = DiskStorage(storage_dir="./blog")
multi_crud = MultiModelAutoCRUD(storage)

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
from autocrud import AutoCRUD
from autocrud.storage import MemoryStorage
import uuid
import time

def custom_id_generator():
    """產生基於時間戳的 ID"""
    timestamp = int(time.time())
    random_part = str(uuid.uuid4())[:8]
    return f"{timestamp}-{random_part}"

storage = MemoryStorage()
crud = AutoCRUD(
    model=User,
    storage=storage,
    id_generator=custom_id_generator
)

user = crud.create({
    "name": "測試使用者",
    "email": "test@example.com"
})
print(f"產生的 ID: {user['id']}")
```

### 7. 不同序列化格式

```python
from autocrud import AutoCRUD
from autocrud.storage import DiskStorage
from autocrud.serializer import SerializerFactory

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
from autocrud import AutoCRUD
from autocrud.exceptions import ValidationError, StorageError
from autocrud.storage import MemoryStorage

storage = MemoryStorage()
crud = AutoCRUD(model=User, storage=storage)

try:
    # 嘗試建立無效的使用者
    user = crud.create({
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
from autocrud import AutoCRUD
from autocrud.storage import DiskStorage
import json

storage = DiskStorage(storage_dir="./users")
crud = AutoCRUD(model=User, storage=storage)

# 批次匯入
users_data = [
    {"name": "Alice", "email": "alice@example.com", "age": 30},
    {"name": "Bob", "email": "bob@example.com", "age": 25},
    {"name": "Charlie", "email": "charlie@example.com", "age": 35}
]

for user_data in users_data:
    crud.create(user_data)

# 匯出所有資料
all_users = crud.list_all()
with open("users_backup.json", "w", encoding="utf-8") as f:
    json.dump(all_users, f, ensure_ascii=False, indent=2)

print(f"匯出了 {len(all_users)} 個使用者")
```

### 10. 效能測試

```python
from autocrud import AutoCRUD
from autocrud.storage import MemoryStorage
import time

storage = MemoryStorage()
crud = AutoCRUD(model=User, storage=storage)

# 批次建立測試
start_time = time.time()
for i in range(1000):
    crud.create({
        "name": f"User {i}",
        "email": f"user{i}@example.com",
        "age": 20 + (i % 50)
    })

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
from autocrud import MultiModelAutoCRUD
from autocrud.storage import DiskStorage
import os
from pathlib import Path

# 生產環境設定
STORAGE_DIR = os.environ.get("STORAGE_DIR", "./production_data")
Path(STORAGE_DIR).mkdir(parents=True, exist_ok=True)

# 使用 JSON 序列化以便於除錯
storage = DiskStorage(
    storage_dir=STORAGE_DIR,
    serializer_type="json"
)

multi_crud = MultiModelAutoCRUD(storage)
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
