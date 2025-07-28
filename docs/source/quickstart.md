# 快速入門

## 🚀 從資料模型到完整 REST API

### 快速體驗：建立可用的 REST API

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
crud.register_model(User)  # 完整 REST API 自動生成

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
- **零配置**: 開箱即用，無需額外設置

### 💡 為什麼這是技術突破？

傳統手工建立一個 FastAPI CRUD 路由需要：

```python
# 傳統方式 - 繁瑣且容易出錯
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
    # 驗證、ID生成、存儲、錯誤處理邏輯...
    pass

@app.get("/users", response_model=List[UserResponse])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: Optional[str] = None,
    sort_order: str = Query("desc", regex="^(asc|desc)$")
):
    # 分頁、排序、查詢邏輯...
    pass

# ... 還需要 GET, PUT, DELETE, COUNT 等路由
# 每個模型都需要重複這些繁瑣的代碼！
```

**用 AutoCRUD，這些全部自動完成！**

### 進階應用：企業級多模型 API

```python
from autocrud import AutoCRUD
from dataclasses import dataclass
from typing import List
from enum import Enum

class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"

@dataclass
class User:
    id: str
    name: str
    email: str
    is_premium: bool = False

@dataclass  
class Product:
    id: str
    name: str
    price: float
    category: str
    
@dataclass
class Order:
    id: str
    user_id: str
    items: List[str]
    total: float
    status: OrderStatus = OrderStatus.PENDING

# 一次註冊，獲得完整的企業級 API 平台
crud = AutoCRUD()
crud.register_model(User)     # -> 完整的 /users API
crud.register_model(Product)  # -> 完整的 /products API  
crud.register_model(Order)    # -> 完整的 /orders API

app = crud.create_fastapi_app(title="企業級電商 API")
```

### 需要程式化控制？沒問題！

當自動 API 無法滿足所有需求時，你還有完整的程式化控制權：

```python
# 完整的程式化 CRUD 操作
user_id = crud.create("users", {"name": "Alice", "email": "alice@example.com"})
user = crud.get("users", user_id)
all_users = crud.list_all("users")

# 高級查詢操作
from autocrud import ListQueryParams, SortOrder

params = ListQueryParams(
    page=1,
    page_size=10,
    sort_by="name",
    sort_order=SortOrder.ASC
)
result = crud.list("users", params)
print(f"總共 {result.total} 個使用者")

# 更新和刪除
crud.update("users", user_id, {"age": 25})
crud.delete("users", user_id)
```

### 🎯 生產環境部署

AutoCRUD 生成的 API 可以直接部署到任何支持 FastAPI 的環境：

```python
# main.py - 生產就緒
from autocrud import AutoCRUD
from autocrud.storage import DiskStorage
import os

# 生產環境配置
storage = DiskStorage(storage_dir=os.getenv("DATA_DIR", "./data"))
crud = AutoCRUD(storage_factory=lambda name: storage)

# 註冊你的業務模型
crud.register_model(User)
crud.register_model(Product)

# 創建生產級應用
app = crud.create_fastapi_app(
    title="生產 API v1.0",
    version="1.0.0",
    prefix="/api/v1"
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**部署命令：**
```bash
# 開發環境
uvicorn main:app --reload

# 生產環境  
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

# Docker 部署
docker build -t my-api . && docker run -p 8000:8000 my-api
```

## 🌟 核心優勢

1. **🎯 自動 API 生成**: 這是技術核心！從資料模型直接產生完整的 REST API
2. **⚡ 零配置啟動**: 定義模型 → 註冊模型 → 執行應用，就這麼簡單
3. **📚 自動文檔**: 完整的 OpenAPI/Swagger 文檔，包含所有端點和驗證規則
4. **🔧 企業級功能**: 內建分頁、排序、查詢、驗證、錯誤處理
5. **💻 程式化控制**: 當自動 API 不夠用時，完整的 CRUD 方法讓你有完全控制權
6. **🚀 生產就緒**: 直接部署到任何 FastAPI 支援的平台，無需額外配置

## 下一步

- 查看 [範例](examples.md) 了解更多實際應用場景
- 閱讀 [使用手冊](user_guide.md) 深入了解所有功能
- 參考 [API 文檔](api_reference.md) 了解詳細的 API 說明

# 執行應用 (需要安裝 uvicorn)
# uvicorn main:app --reload
```

### 多模型支援

```python
from autocrud import AutoCRUD, ResourceNameStyle

@dataclass
class Product:
    id: str
    name: str
    price: float
    category: str

# 建立多模型 CRUD 系統
multi_crud = AutoCRUD(
    resource_name_style=ResourceNameStyle.SNAKE,
    use_plural=True
)

# 註冊多個模型
user_crud = multi_crud.register_model(User)  # URL: /users
product_crud = multi_crud.register_model(Product)  # URL: /products

# 建立統一的 FastAPI 應用
app = multi_crud.create_fastapi_app(
    title="多模型 API",
    description="支援多個資料模型的 CRUD API"
)
```

### 插件系統

AutoCRUD 支援插件系統來擴展功能：

```python
from autocrud import BaseRoutePlugin, plugin_manager
from fastapi import BackgroundTasks

class CustomPlugin(BaseRoutePlugin):
    def __init__(self):
        super().__init__("custom", "1.0.0")
    
    def get_routes(self, crud):
        async def custom_handler(crud, background_tasks: BackgroundTasks):
            return {"message": "自定義端點"}
        
        return [PluginRouteConfig(
            name="custom",
            path="/custom",
            method=RouteMethod.GET,
            handler=custom_handler,
            summary="自定義端點"
        )]

# 註冊插件
plugin_manager.register_plugin(CustomPlugin())
```

### 高級功能

#### 時間戳和用戶追蹤

```python
from autocrud import MetadataConfig

metadata_config = MetadataConfig(
    enable_timestamps=True,
    enable_user_tracking=True
)

user_crud = SingleModelCRUD(
    model=User,
    storage=storage,
    resource_name="users",
    metadata_config=metadata_config
)
```

#### 高級更新操作

```python
from autocrud import AdvancedUpdater, set_value, list_add

updater = AdvancedUpdater()

# 原子更新操作
operations = [
    set_value("name", "New Name"),
    list_add("tags", "new_tag")
]

success = updater.update(user_crud, user_id, operations)
```

### URL 形式自訂

```python
# 預設複數形式
multi_crud.register_model(User)  # -> /api/v1/users

# 指定單數形式
multi_crud.register_model(Product, use_plural=False)  # -> /api/v1/product

# 自訂資源名稱
multi_crud.register_model(Company, resource_name=\"organizations\")  # -> /api/v1/organizations
```

## 下一步

- 閱讀 [安裝指南](installation.md) 了解詳細的安裝說明
- 查看 [使用者指南](user_guide.md) 學習更多進階功能
- 瀏覽 [API 參考](api_reference.md) 了解完整的 API 檔案
- 查看 [範例](examples.md) 取得更多使用案例
