# 實用範例

體驗 AutoCRUD 的功能！

## 🚀 快速開始

快速搭建一個完整的 REST API：

```python
from autocrud import AutoCRUD
from dataclasses import dataclass

@dataclass
class User:
    id: str
    name: str
    email: str
    age: int = 0

# 簡單設定
crud = AutoCRUD()
crud.register_model(User)  # 自動產生完整的 REST API

# 創建生產級 API 應用
app = crud.create_fastapi_app(title="我的 API")
# 執行: uvicorn main:app --reload
# 訪問: http://localhost:8000/docs
```

**🎯 主要功能：**
- **完整的 REST API**: `GET /users`, `POST /users`, `PUT /users/{id}`, `DELETE /users/{id}`, `GET /users/count`
- **高級查詢功能**: `GET /users?page=1&page_size=10&sort_by=name&sort_order=asc`
- **時間範圍篩選**: `GET /users?created_time_start=2024-01-01&created_time_end=2024-12-31`
- **完整 Swagger 文檔**: 自動產生的交互式 API 文檔 (訪問 `/docs`)
- **資料驗證**: 自動請求/響應驗證，錯誤處理
- **開箱即用**: 無需額外設置

**💪 程式化控制選項：**
```python
# 如果自動 API 不夠用，還有完整的 CRUD 控制
user_id = crud.create("users", {"name": "Alice", "email": "alice@example.com"})
alice = crud.get("users", user_id)
all_users = crud.list_all("users")
print(f"Hello {alice['name']}!")  # Hello Alice!
```

## 💡 為什麼選擇 AutoCRUD？

- **🎯 自動 API 生成**: 從數據模型自動產生完整的 REST API
- **🚀 簡化路由**: 不需要手寫 FastAPI 路由、請求/響應模型、驗證邏輯
- **📊 高級查詢 API**: 自動支持分頁、排序、時間範圍查詢等功能
- **📚 自動文檔**: 完整的 OpenAPI/Swagger 文檔
- **🔧 程式化控制**: 當自動 API 不夠用時，完整的 CRUD 方法控制

## 🌟 技術價值：自動 API 路由

手寫完整的 FastAPI CRUD 路由通常需要：

```python
# 傳統方式 - 大量重複代碼
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List

app = FastAPI()

class UserCreate(BaseModel):
    name: str
    email: str
    age: int = 0

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    age: int

@app.post("/users", response_model=UserResponse, status_code=201)
async def create_user(user: UserCreate):
    # 驗證邏輯
    # ID 生成邏輯
    # 存儲邏輯
    # 錯誤處理
    pass

@app.get("/users", response_model=List[UserResponse])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: Optional[str] = None,
    sort_order: str = Query("desc", regex="^(asc|desc)$")
):
    # 分頁邏輯
    # 排序邏輯
    # 查詢邏輯
    pass

@app.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str):
    # 查詢邏輯
    # 404 處理
    pass

# ... 還有 PUT, DELETE, COUNT 等路由
# 每個模型都要重複這些代碼！
```

**用 AutoCRUD，這些全部自動完成：**

```python
# AutoCRUD 方式 - 零樣板代碼
from autocrud import AutoCRUD

crud = AutoCRUD()
crud.register_model(User)  # 上面所有路由自動生成！
app = crud.create_fastapi_app(title="API")
```

## � 企業級多模型 API

想要管理複雜的業務數據？一樣簡單：

```python
from autocrud import AutoCRUD
from dataclasses import dataclass
from typing import List
from enum import Enum

class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"

@dataclass
class User:
    id: str
    name: str
    email: str
    phone: str
    is_premium: bool = False

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
    items: List[str]  
    total: float
    status: OrderStatus = OrderStatus.PENDING

# 一次註冊，獲得完整的電商 API 平台
crud = AutoCRUD()
crud.register_model(User)     # -> 完整的 /users API
crud.register_model(Product)  # -> 完整的 /products API  
crud.register_model(Order)    # -> 完整的 /orders API

# 立即可用的企業級 API 平台
app = crud.create_fastapi_app(
    title="電商 API 平台",
    description="基於 AutoCRUD 的企業級電商 API",
    version="1.0.0"
)
```

**🎯 你立即獲得的完整 API 端點：**

**用戶管理 API:**
- `POST /users` - 創建用戶
- `GET /users` - 列出用戶（支持分頁、排序、篩選）
- `GET /users/{id}` - 獲取特定用戶
- `PUT /users/{id}` - 更新用戶
- `DELETE /users/{id}` - 刪除用戶
- `GET /users/count` - 用戶總數統計

**商品管理 API:**
- `POST /products` - 添加商品
- `GET /products?category=electronics&stock_gt=0` - 高級篩選
- `GET /products?sort_by=price&sort_order=desc` - 價格排序
- 其他所有 CRUD 操作...

**訂單管理 API:**
- `POST /orders` - 創建訂單
- `GET /orders?status=pending&user_id=123` - 複雜查詢
- 完整的訂單生命週期管理...

**而且當自動 API 不夠用時，你還有完整的程式化控制：**

```python
# 自定義業務邏輯示例
async def create_order_with_inventory_check(user_id: str, items: List[str]):
    # 檢查庫存
    for item_id in items:
        product = crud.get("products", item_id)
        if not product or product["stock"] <= 0:
            raise HTTPException(400, f"商品 {item_id} 庫存不足")
    
    # 創建訂單
    order_data = {
        "user_id": user_id,
        "items": items,
        "total": calculate_total(items)
    }
    order_id = crud.create("orders", order_data)
    
    # 更新庫存
    for item_id in items:
        product = crud.get("products", item_id)
        crud.update("products", item_id, {"stock": product["stock"] - 1})
    
    return order_id
```

## 🎨 使用 Pydantic 獲得企業級數據驗證

```python
from autocrud import AutoCRUD
from pydantic import BaseModel, EmailStr, validator, Field
from typing import Optional
from decimal import Decimal

class User(BaseModel):
    id: str
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr  # 自動 email 格式驗證
    age: int = Field(..., ge=0, le=150)
    phone: Optional[str] = Field(None, regex=r'^\+?1?\d{9,15}$')
    
    @validator('name')
    def name_must_not_be_empty(cls, v):
        if not v.strip():
            raise ValueError('姓名不能為空')
        return v.strip()

class Product(BaseModel):
    id: str
    name: str = Field(..., min_length=1, max_length=200)
    price: Decimal = Field(..., gt=0, decimal_places=2)
    category: str
    stock: int = Field(0, ge=0)
    
    @validator('price')
    def price_must_be_reasonable(cls, v):
        if v > 1000000:
            raise ValueError('價格不能超過 100 萬')
        return v

# 自動獲得企業級驗證的 API
crud = AutoCRUD()
crud.register_model(User)
crud.register_model(Product)

app = crud.create_fastapi_app(title="企業級驗證 API")
```

**🎯 你自動獲得的驗證功能：**
- **輸入驗證**: 所有 POST/PUT 請求自動驗證
- **類型轉換**: 自動將字符串轉換為合適的數據類型
- **錯誤回報**: 詳細的驗證錯誤訊息，符合 REST API 標準
- **API 文檔**: Swagger 文檔自動顯示所有驗證規則

**程式化使用時同樣有驗證保護：**
```python
try:
    # 這會自動觸發驗證
    user_id = crud.create("users", {
        "name": "Alice",
        "email": "alice@example.com",
        "age": 25
    })
except ValidationError as e:
    print(f"數據驗證失敗: {e}")
```

## ⚡ 需要數據持久化？

預設情況下，AutoCRUD 使用記憶體存儲（重啟後數據消失）。需要持久化？

```python
from autocrud import AutoCRUD
from autocrud.storage import DiskStorage

# 使用文件存儲
storage = DiskStorage(storage_dir="./my_data")  
crud = AutoCRUD(storage_factory=lambda name: storage)

crud.register_model(User)

# 數據會自動保存到 ./my_data/ 文件夾
user_id = crud.create("users", {"name": "Alice", "email": "alice@example.com"})
```

## 🌐 生產環境部署

AutoCRUD 生成的 API 可以直接部署到任何支持 FastAPI 的環境：

```python
# main.py - 生產就緒的代碼
from autocrud import AutoCRUD
from autocrud.storage import DiskStorage
from models import User, Product, Order  # 你的模型定義
import os

# 生產環境配置
DATA_DIR = os.getenv("DATA_DIR", "./production_data")
storage = DiskStorage(storage_dir=DATA_DIR, serializer_type="json")

# 創建生產級 API
crud = AutoCRUD(storage_factory=lambda name: storage)
crud.register_model(User)
crud.register_model(Product) 
crud.register_model(Order)

# 生產就緒的 FastAPI 應用
app = crud.create_fastapi_app(
    title="電商 API v1.0",
    description="基於 AutoCRUD 的企業級電商 API",
    version="1.0.0",
    prefix="/api/v1"  # 所有路由將以 /api/v1 開頭
)

# 自定義健康檢查端點
@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "version": "1.0.0",
        "models": crud.list_resources()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=int(os.getenv("PORT", "8000")),
        workers=int(os.getenv("WORKERS", "1"))
    )
```

**🚀 部署命令：**
```bash
# 開發環境
uvicorn main:app --reload

# 生產環境
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

# Docker 部署
docker build -t my-api .
docker run -p 8000:8000 -v ./data:/app/data my-api

# K8s/雲服務部署
# 任何支持 FastAPI 的平台都可以直接部署
```

**🎯 你獲得的生產級功能：**
- **完整的 REST API**: 符合 REST 標準的所有端點
- **自動文檔**: 訪問 `/docs` 或 `/redoc` 查看完整 API 文檔
- **數據持久化**: 支持文件存儲，數據不會丟失
- **錯誤處理**: 統一的錯誤格式和 HTTP 狀態碼
- **性能優化**: 內建分頁避免大數據量問題
- **類型安全**: 完整的類型檢查和驗證

## 🔥 實際應用場景

### 部落格系統

```python
from autocrud import AutoCRUD  
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class User(BaseModel):
    id: str
    username: str
    email: str
    is_active: bool = True
    
class Post(BaseModel):
    id: str
    title: str
    content: str
    author_id: str
    published: bool = False
    created_at: Optional[datetime] = None

class Comment(BaseModel):
    id: str
    post_id: str
    author_id: str
    content: str

# 3分鐘搭建完整部落格 API
blog = AutoCRUD()
blog.register_model(User)     # /users
blog.register_model(Post)     # /posts  
blog.register_model(Comment)  # /comments

app = blog.create_fastapi_app(title="部落格 API")
```

### 任務管理系統

```python  
from autocrud import AutoCRUD
from dataclasses import dataclass
from typing import Optional
from enum import Enum

class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium" 
    HIGH = "high"

@dataclass
class Task:
    id: str
    title: str
    description: Optional[str] = None
    priority: Priority = Priority.MEDIUM
    completed: bool = False
    assignee: Optional[str] = None

# 立即可用的任務管理 API
tasks = AutoCRUD()
tasks.register_model(Task)

app = tasks.create_fastapi_app(title="任務管理 API")
```

### 庫存管理系統

```python
from autocrud import AutoCRUD
from pydantic import BaseModel, validator

class Product(BaseModel):
    id: str
    name: str
    sku: str
    price: float
    stock: int = 0
    category: str
    
    @validator('price')
    def price_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('價格必須大於 0')
        return v
        
    @validator('stock')  
    def stock_must_be_non_negative(cls, v):
        if v < 0:
            raise ValueError('庫存不能為負數')
        return v

inventory = AutoCRUD()
inventory.register_model(Product)

app = inventory.create_fastapi_app(title="庫存管理 API")
```

## 🛠️ 常見需求解決方案

### 我需要自定義 API 路由名稱

```python
# 預設：User -> /users
crud.register_model(User)

# 自定義路由名稱  
crud.register_model(User, resource_name="members")  # -> /members

# 使用單數形式
crud.register_model(Product, use_plural=False)  # -> /product
```

### 我需要時間戳記錄

```python
from autocrud import AutoCRUD, MetadataConfig

# 啟用自動時間戳
config = MetadataConfig(enable_timestamps=True)
crud = AutoCRUD(metadata_config=config)
crud.register_model(User)

# 創建時自動添加 created_time 和 updated_time
user_id = crud.create("users", {"name": "Alice", "email": "alice@example.com"})
user = crud.get("users", user_id)
print(user["created_time"])  # 2024-01-15T10:30:00Z
```

### 我需要分頁和排序

```python
from autocrud import ListQueryParams, SortOrder

# 獲取第一頁，每頁10條，按名稱排序
params = ListQueryParams(
    page=1,
    page_size=10,
    sort_by="name",
    sort_order=SortOrder.ASC
)

result = crud.list("users", params)
print(f"總共 {result.total} 個用戶")
print(f"第 {result.page} 頁，共 {len(result.items)} 條")
```

### 我需要搜索和篩選

```python
# 按時間範圍搜索
from datetime import datetime, timedelta

now = datetime.now()
params = ListQueryParams(
    created_time_start=now - timedelta(days=7),  # 最近7天
    created_time_end=now
)

recent_users = crud.list("users", params)
```

### 我需要自定義 ID 生成

```python  
import uuid

def my_id_generator():
    return f"user_{uuid.uuid4().hex[:8]}"

crud = AutoCRUD(id_generator=my_id_generator)
crud.register_model(User)

user_id = crud.create("users", {"name": "Alice", "email": "alice@example.com"})
print(user_id)  # user_a1b2c3d4
```

## 🎯 最佳實踐

### 1. 模型設計建議

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class User(BaseModel):
    id: str = Field(..., description="用戶唯一標識")
    name: str = Field(..., min_length=1, max_length=100, description="用戶姓名")
    email: str = Field(..., description="電子郵件地址")
    age: Optional[int] = Field(None, ge=0, le=150, description="年齡")
    is_active: bool = Field(True, description="是否啟用")
    created_at: Optional[datetime] = Field(None, description="創建時間")
    
    class Config:
        schema_extra = {
            "example": {
                "id": "user123",
                "name": "張三",
                "email": "zhang@example.com",
                "age": 25,
                "is_active": True
            }
        }
```

### 2. 生產環境配置

```python
from autocrud import AutoCRUD
from autocrud.storage import DiskStorage
import os

# 環境變量配置
DATA_DIR = os.getenv("DATA_DIR", "./production_data")
API_PREFIX = os.getenv("API_PREFIX", "/api/v1")

# 持久化存儲
storage = DiskStorage(storage_dir=DATA_DIR, serializer_type="json")
crud = AutoCRUD(storage_factory=lambda name: storage)

# 註冊所有模型
crud.register_model(User)
crud.register_model(Product)

# 創建生產就緒的應用
app = crud.create_fastapi_app(
    title="生產 API",
    description="基於 AutoCRUD 的生產環境 API",
    version="1.0.0",
    prefix=API_PREFIX
)

# 添加健康檢查
@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
```

### 3. Docker 部署

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安裝依賴
COPY requirements.txt .
RUN pip install -r requirements.txt

# 複製代碼
COPY . .

# 創建數據目錄
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**docker-compose.yml:**
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
      - DATA_DIR=/app/data
      - API_PREFIX=/api/v1
```

## 🚀 從這裡開始

1. **安裝 AutoCRUD**: `pip install autocrud`
2. **定義你的數據模型**
3. **創建 AutoCRUD 實例並註冊模型**  
4. **運行 FastAPI 應用**
5. **訪問 `/docs` 查看自動生成的 API 文檔**

就這麼簡單！AutoCRUD 讓你專注於業務邏輯，而不是重複的 CRUD 代碼。
