# 示例集合

本頁面提供了各種使用 AutoCRUD 的實際示例。

## 基礎示例

### 1. 最簡單的 API

```python
from pydantic import BaseModel
from fastapi import FastAPI, APIRouter
from autocrud.crud.core import AutoCRUD, CreateRouteTemplate, ReadRouteTemplate

class Task(BaseModel):
    title: str
    completed: bool = False

crud = AutoCRUD()
crud.add_route_template(CreateRouteTemplate())
crud.add_route_template(ReadRouteTemplate())
crud.add_model(Task)

app = FastAPI()
router = APIRouter()
crud.apply(router)
app.include_router(router)
```

### 2. 多數據類型示例

```python
from dataclasses import dataclass
from typing import TypedDict, Optional
from pydantic import BaseModel
import msgspec
from fastapi import FastAPI, APIRouter

from autocrud.crud.core import (
    AutoCRUD, CreateRouteTemplate, ReadRouteTemplate, 
    UpdateRouteTemplate, DeleteRouteTemplate, ListRouteTemplate
)

# 不同的數據類型
class BlogPost(TypedDict):
    title: str
    content: str
    published: bool

class User(BaseModel):
    username: str
    email: str
    age: Optional[int] = None

@dataclass
class Comment:
    author: str
    content: str
    post_id: str

class Tag(msgspec.Struct):
    name: str
    color: str = "#000000"

# 創建 API
crud = AutoCRUD(model_naming="kebab")

# 添加所有 CRUD 操作
templates = [
    CreateRouteTemplate(),
    ReadRouteTemplate(),
    UpdateRouteTemplate(),
    DeleteRouteTemplate(),
    ListRouteTemplate(),
]

for template in templates:
    crud.add_route_template(template)

# 註冊所有模型
crud.add_model(BlogPost)  # /blog-post
crud.add_model(User)      # /user
crud.add_model(Comment)   # /comment
crud.add_model(Tag)       # /tag

app = FastAPI(title="Multi-Type Blog API")
router = APIRouter()
crud.apply(router)
app.include_router(router)
```

## 進階示例

### 3. 電商 API

```python
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from decimal import Decimal
from datetime import datetime
from enum import Enum

class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class Product(BaseModel):
    name: str
    description: str
    price: Decimal
    stock_quantity: int
    category: str
    tags: List[str] = []

class Customer(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    address: Optional[str] = None

class OrderItem(BaseModel):
    product_id: str
    quantity: int
    unit_price: Decimal

class Order(BaseModel):
    customer_id: str
    items: List[OrderItem]
    status: OrderStatus = OrderStatus.PENDING
    total_amount: Decimal
    notes: Optional[str] = None

# 創建電商 API
crud = AutoCRUD(model_naming="kebab")

# 添加完整 CRUD 功能
crud.add_route_template(CreateRouteTemplate())
crud.add_route_template(ReadRouteTemplate())
crud.add_route_template(UpdateRouteTemplate())
crud.add_route_template(DeleteRouteTemplate())
crud.add_route_template(ListRouteTemplate())

# 註冊所有模型
crud.add_model(Product)   # /product
crud.add_model(Customer)  # /customer
crud.add_model(Order)     # /order

app = FastAPI(title="E-commerce API")
router = APIRouter()
crud.apply(router)
app.include_router(router)
```

### 4. 自定義依賴注入

```python
from fastapi import Depends, HTTPException, Header
from autocrud.crud.core import DependencyProvider
import jwt
from datetime import datetime

# 自定義用戶認證
def get_current_user(authorization: str = Header(None)):
    if not authorization:
        return "anonymous"
    
    try:
        token = authorization.replace("Bearer ", "")
        payload = jwt.decode(token, "secret", algorithms=["HS256"])
        return payload.get("user_id", "anonymous")
    except:
        return "anonymous"

# 自定義時間提供者
def get_current_time():
    return datetime.utcnow()

# 創建自定義依賴提供者
deps = DependencyProvider(
    get_user=get_current_user,
    get_now=get_current_time
)

# 使用自定義依賴
crud = AutoCRUD()
crud.add_route_template(CreateRouteTemplate(dependency_provider=deps))
crud.add_route_template(ReadRouteTemplate(dependency_provider=deps))
# ... 其他模板

class SecureDocument(BaseModel):
    title: str
    content: str
    confidential: bool = False

crud.add_model(SecureDocument)
```

### 5. 只讀 API

```python
from dataclasses import dataclass
from typing import List

@dataclass
class Report:
    id: str
    title: str
    data: dict
    generated_at: str

@dataclass
class Metric:
    name: str
    value: float
    unit: str
    timestamp: str

# 創建只讀 API
crud = AutoCRUD(model_naming="snake")

# 只添加讀取操作
crud.add_route_template(ReadRouteTemplate())
crud.add_route_template(ListRouteTemplate())

crud.add_model(Report)  # /report
crud.add_model(Metric)  # /metric

app = FastAPI(title="Analytics Dashboard API")
router = APIRouter()
crud.apply(router)
app.include_router(router)
```

### 6. 高級版本控制

```python
from autocrud.crud.core import (
    PatchRouteTemplate,
    SwitchRevisionRouteTemplate,
    RestoreRouteTemplate
)

class Document(BaseModel):
    title: str
    content: str
    version: str = "1.0"

crud = AutoCRUD()

# 基礎 CRUD
crud.add_route_template(CreateRouteTemplate())
crud.add_route_template(ReadRouteTemplate())
crud.add_route_template(UpdateRouteTemplate())
crud.add_route_template(DeleteRouteTemplate())
crud.add_route_template(ListRouteTemplate())

# 高級版本控制功能
crud.add_route_template(PatchRouteTemplate())           # PATCH 部分更新
crud.add_route_template(SwitchRevisionRouteTemplate())  # 切換到指定版本
crud.add_route_template(RestoreRouteTemplate())         # 恢復已刪除文檔

crud.add_model(Document)

# 現在可以使用:
# PATCH /document/{id} - 部分更新
# POST /document/{id}/switch/{revision_id} - 切換版本  
# POST /document/{id}/restore - 恢復已刪除文檔
```

## 部署示例

### 7. Docker 部署

```python
# main.py
from fastapi import FastAPI, APIRouter
from pydantic import BaseModel
from autocrud.crud.core import AutoCRUD, CreateRouteTemplate, ReadRouteTemplate

class Item(BaseModel):
    name: str
    description: str

crud = AutoCRUD()
crud.add_route_template(CreateRouteTemplate())
crud.add_route_template(ReadRouteTemplate())
crud.add_model(Item)

app = FastAPI()
router = APIRouter()
crud.apply(router)
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY main.py .

EXPOSE 8000

CMD ["python", "main.py"]
```

```txt
# requirements.txt
autocrud
fastapi
uvicorn[standard]
```

### 8. 環境配置

```python
import os
from typing import Dict, Any

def get_config() -> Dict[str, Any]:
    """根據環境獲取配置"""
    env = os.getenv("ENVIRONMENT", "development")
    
    configs = {
        "development": {
            "model_naming": "kebab",
            "debug": True,
            "title": "Development API"
        },
        "production": {
            "model_naming": "snake", 
            "debug": False,
            "title": "Production API"
        }
    }
    
    return configs.get(env, configs["development"])

def create_app():
    config = get_config()
    
    crud = AutoCRUD(model_naming=config["model_naming"])
    # ... 添加路由模板和模型
    
    app = FastAPI(
        title=config["title"],
        debug=config["debug"]
    )
    
    router = APIRouter()
    crud.apply(router)
    app.include_router(router)
    
    return app

app = create_app()
```

## 測試示例

### 9. API 測試

```python
# test_api.py
import pytest
from fastapi.testclient import TestClient
from main import app  # 假設您的應用在 main.py

client = TestClient(app)

def test_create_user():
    response = client.post("/user", json={
        "name": "Test User",
        "email": "test@example.com",
        "age": 25
    })
    assert response.status_code == 200
    data = response.json()
    assert "resource_id" in data
    assert "revision_id" in data

def test_get_user():
    # 先創建用戶
    create_response = client.post("/user", json={
        "name": "Test User",
        "email": "test@example.com"
    })
    user_id = create_response.json()["resource_id"]
    
    # 獲取用戶
    response = client.get(f"/user/{user_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test User"
    assert data["email"] == "test@example.com"

def test_list_users():
    response = client.get("/user")
    assert response.status_code == 200
    data = response.json()
    assert "resources" in data
    assert isinstance(data["resources"], list)
```

## 性能優化示例

### 10. 高性能配置

```python
import msgspec
from autocrud.crud.core import AutoCRUD

# 使用 msgspec 以獲得最佳性能
class HighPerformanceEvent(msgspec.Struct):
    id: str
    type: str
    payload: bytes  # 使用 bytes 而不是 dict
    timestamp: float

# 最小化路由模板以減少開銷
crud = AutoCRUD(model_naming="same")  # 避免名稱轉換開銷
crud.add_route_template(CreateRouteTemplate())
crud.add_route_template(ReadRouteTemplate())

crud.add_model(HighPerformanceEvent)

# 對於高頻操作，考慮使用自定義存儲
```

這些示例涵蓋了從基礎到高級的各種使用場景。您可以根據具體需求選擇合適的模式和配置。
