# 示例集合

這裡提供了 AutoCRUD 的各種使用示例，從簡單到複雜的實際應用場景。

## 基礎示例

### 1. 簡單的用戶管理

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

# 設置
storage = MemoryStorage()
crud = AutoCRUD(model=User, storage=storage)

# 創建用戶
user = crud.create({
    "name": "Alice",
    "email": "alice@example.com",
    "age": 30
})
print(f"創建用戶: {user}")

# 查詢所有用戶
users = crud.list_all()
print(f"所有用戶: {users}")
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

# 使用磁碟存儲
storage = DiskStorage(storage_dir="./products", serializer_type="json")
product_crud = AutoCRUD(model=Product, storage=storage)

# 創建產品
product = product_crud.create({
    "name": "筆記本電腦",
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
    stock: int
    description: Optional[str] = None

@dataclass
class Order:
    user_id: str
    product_ids: List[str]
    total_amount: float
    status: str = "pending"
    created_at: datetime = None

# 設置多模型系統
storage = DiskStorage(storage_dir="./ecommerce", serializer_type="json")
multi_crud = MultiModelAutoCRUD(storage)

# 註冊模型
multi_crud.register_model(User)          # /api/v1/users
multi_crud.register_model(Product)       # /api/v1/products  
multi_crud.register_model(Order)         # /api/v1/orders

# 創建 FastAPI 應用
app = multi_crud.create_fastapi_app(
    title="電商 API",
    description="完整的電商管理系統",
    version="1.0.0"
)

# 業務邏輯示例
def create_order(user_id: str, product_ids: List[str]):
    # 計算總金額
    total = 0.0
    for pid in product_ids:
        product = multi_crud.get("products", pid)
        if product:
            total += product["price"]
    
    # 創建訂單
    order = multi_crud.create("orders", {
        "user_id": user_id,
        "product_ids": product_ids,
        "total_amount": total,
        "created_at": datetime.now()
    })
    return order

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

## FastAPI 集成示例

### 4. 自定義路由和中間件

```python
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from autocrud import MultiModelAutoCRUD
from autocrud.storage import MemoryStorage

# 數據模型
@dataclass
class Task:
    title: str
    description: str
    completed: bool = False
    priority: int = 1

# 設置
storage = MemoryStorage()
multi_crud = MultiModelAutoCRUD(storage)
multi_crud.register_model(Task)

# 創建基礎應用
app = multi_crud.create_fastapi_app(
    title="任務管理 API",
    description="簡單的任務管理系統"
)

# 添加 CORS 中間件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 自定義端點
@app.get("/api/v1/tasks/completed")
async def get_completed_tasks():
    """獲取所有已完成的任務"""
    all_tasks = multi_crud.list_all("tasks")
    completed = [task for task in all_tasks.values() if task["completed"]]
    return completed

@app.put("/api/v1/tasks/{task_id}/toggle")
async def toggle_task_completion(task_id: str):
    """切換任務完成狀態"""
    task = multi_crud.get("tasks", task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任務不存在")
    
    updated_task = multi_crud.update("tasks", task_id, {
        "completed": not task["completed"]
    })
    return updated_task
```

### 5. 認證和授權

```python
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta
import jwt

# 簡單的認證系統
security = HTTPBearer()
SECRET_KEY = "your-secret-key"

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=["HS256"])
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="無效的令牌")
        return user_id
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="無效的令牌")

# 受保護的端點
@app.get("/api/v1/protected-tasks")
async def get_user_tasks(user_id: str = Depends(verify_token)):
    """獲取當前用戶的任務"""
    all_tasks = multi_crud.list_all("tasks")
    user_tasks = [task for task in all_tasks.values() if task.get("user_id") == user_id]
    return user_tasks
```

## 高級用法

### 6. 自定義 ID 生成和驗證

```python
import uuid
from typing import Dict, Any

class CustomAutoCRUD(AutoCRUD):
    def __init__(self, *args, **kwargs):
        # 自定義 ID 生成器
        def custom_id_generator():
            return f"item_{uuid.uuid4().hex[:8]}"
        
        kwargs['id_generator'] = custom_id_generator
        super().__init__(*args, **kwargs)
    
    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # 添加創建時間
        data = data.copy()
        data['created_at'] = datetime.now().isoformat()
        return super().create(data)
    
    def update(self, resource_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # 添加更新時間
        data = data.copy()
        data['updated_at'] = datetime.now().isoformat()
        return super().update(resource_id, data)

# 使用自定義 CRUD
custom_crud = CustomAutoCRUD(model=User, storage=storage)
```

### 7. 數據遷移和備份

```python
import json
from pathlib import Path

def backup_data(multi_crud: MultiModelAutoCRUD, backup_path: str):
    """備份所有數據到 JSON 文件"""
    backup_data = {}
    
    for resource_name in multi_crud.list_resources():
        all_items = multi_crud.list_all(resource_name)
        backup_data[resource_name] = all_items
    
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(backup_data, f, ensure_ascii=False, indent=2)
    
    print(f"數據已備份到 {backup_path}")

def restore_data(multi_crud: MultiModelAutoCRUD, backup_path: str):
    """從 JSON 文件恢復數據"""
    with open(backup_path, 'r', encoding='utf-8') as f:
        backup_data = json.load(f)
    
    for resource_name, items in backup_data.items():
        if resource_name in multi_crud.list_resources():
            for item_id, item_data in items.items():
                # 移除 ID 讓系統重新生成，或者保持原有 ID
                existing = multi_crud.get(resource_name, item_id)
                if not existing:
                    multi_crud.create(resource_name, item_data)
    
    print(f"數據已從 {backup_path} 恢復")

# 使用示例
backup_data(multi_crud, "backup.json")
restore_data(multi_crud, "backup.json")
```

### 8. 批量操作

```python
from typing import List, Dict, Any

class BatchAutoCRUD:
    def __init__(self, multi_crud: MultiModelAutoCRUD):
        self.multi_crud = multi_crud
    
    def batch_create(self, resource_name: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """批量創建項目"""
        results = []
        for item in items:
            try:
                created = self.multi_crud.create(resource_name, item)
                results.append(created)
            except Exception as e:
                results.append({"error": str(e), "data": item})
        return results
    
    def batch_update(self, resource_name: str, updates: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """批量更新項目"""
        results = {}
        for item_id, update_data in updates.items():
            try:
                updated = self.multi_crud.update(resource_name, item_id, update_data)
                results[item_id] = updated
            except Exception as e:
                results[item_id] = {"error": str(e)}
        return results
    
    def batch_delete(self, resource_name: str, item_ids: List[str]) -> Dict[str, bool]:
        """批量刪除項目"""
        results = {}
        for item_id in item_ids:
            try:
                deleted = self.multi_crud.delete(resource_name, item_id)
                results[item_id] = deleted
            except Exception as e:
                results[item_id] = False
        return results

# 使用批量操作
batch_crud = BatchAutoCRUD(multi_crud)

# 批量創建用戶
users_data = [
    {"name": "User1", "email": "user1@example.com"},
    {"name": "User2", "email": "user2@example.com"},
    {"name": "User3", "email": "user3@example.com"},
]
created_users = batch_crud.batch_create("users", users_data)
```

## 測試示例

### 9. 單元測試

```python
import pytest
from autocrud import AutoCRUD, MultiModelAutoCRUD
from autocrud.storage import MemoryStorage

@pytest.fixture
def user_crud():
    storage = MemoryStorage()
    return AutoCRUD(model=User, storage=storage)

@pytest.fixture
def multi_crud():
    storage = MemoryStorage()
    crud = MultiModelAutoCRUD(storage)
    crud.register_model(User)
    crud.register_model(Product)
    return crud

def test_create_user(user_crud):
    user_data = {"name": "Test User", "email": "test@example.com"}
    created_user = user_crud.create(user_data)
    
    assert created_user["name"] == "Test User"
    assert created_user["email"] == "test@example.com"
    assert "id" in created_user

def test_multi_model_operations(multi_crud):
    # 創建用戶
    user = multi_crud.create("users", {"name": "Alice", "email": "alice@example.com"})
    
    # 創建產品
    product = multi_crud.create("products", {"name": "Laptop", "price": 999.99, "category": "Electronics"})
    
    # 驗證創建成功
    assert multi_crud.exists("users", user["id"])
    assert multi_crud.exists("products", product["id"])
    
    # 測試跨模型獨立性
    assert len(multi_crud.list_all("users")) == 1
    assert len(multi_crud.list_all("products")) == 1

if __name__ == "__main__":
    pytest.main([__file__])
```

### 10. API 測試

```python
from fastapi.testclient import TestClient
import pytest

@pytest.fixture
def test_app():
    storage = MemoryStorage()
    multi_crud = MultiModelAutoCRUD(storage)
    multi_crud.register_model(User)
    return multi_crud.create_fastapi_app()

@pytest.fixture
def client(test_app):
    return TestClient(test_app)

def test_create_user_api(client):
    user_data = {"name": "API Test User", "email": "api@example.com"}
    response = client.post("/api/v1/users", json=user_data)
    
    assert response.status_code == 200
    created_user = response.json()
    assert created_user["name"] == "API Test User"

def test_list_users_api(client):
    # 先創建一個用戶
    user_data = {"name": "List Test User", "email": "list@example.com"}
    client.post("/api/v1/users", json=user_data)
    
    # 獲取用戶列表
    response = client.get("/api/v1/users")
    assert response.status_code == 200
    
    users = response.json()
    assert len(users) >= 1
```

這些示例涵蓋了從基本使用到高級功能的各種場景，可以作為你開發項目的參考和起點。
