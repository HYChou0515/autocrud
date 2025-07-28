# 使用者指南

深入了解 AutoCRUD 的功能，掌握從原型到生產的完整開發流程。

## 🎯 核心概念：自動 API 生成

AutoCRUD 的核心價值在於**自動從資料模型生成完整的 REST API**。這不僅僅是簡單的 CRUD 操作，而是包含驗證、文檔、分頁、查詢的 API 解決方案。

### 系統架構

AutoCRUD 提供兩個層次的介面：

- **`AutoCRUD`**：**主要推薦**！多模型 API 管理系統，自動生成 REST API
- **`SingleModelCRUD`**：單一模型的程式化 CRUD 操作（當你需要細粒度控制時使用）

## 🚀 推薦開發流程

### 1. 從 AutoCRUD 開始

```python
from autocrud import AutoCRUD
from dataclasses import dataclass

@dataclass
class User:
    id: str
    name: str
    email: str

# 主要開發入口
crud = AutoCRUD()
crud.register_model(User)  # 🎯 完整 REST API 自動生成

app = crud.create_fastapi_app(title="我的 API")
# 訪問 http://localhost:8000/docs 查看自動生成的 API
```

### 2. 當需要程式化控制時

```python
# AutoCRUD 同時提供程式化介面
user_id = crud.create("users", {"name": "Alice", "email": "alice@example.com"})
user = crud.get("users", user_id)

# 如果需要更細粒度的控制，可以獲取單模型 CRUD
user_crud = crud.get_crud("users")  # 返回 SingleModelCRUD 實例
```

## 🎨 資料模型支援

AutoCRUD 支援所有主流 Python 資料模型格式，讓你用喜歡的方式定義資料結構。**重要：所有模型都必須包含 `id` 欄位。**

### 🔥 推薦：使用 Pydantic 獲得進階驗證

```python
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional
from datetime import datetime

class User(BaseModel):
    id: str
    name: str = Field(..., min_length=1, max_length=100, description="使用者姓名")
    email: EmailStr  # 自動 email 格式驗證
    age: Optional[int] = Field(None, ge=0, le=150, description="年齡")
    is_active: bool = Field(True, description="是否啟用")
    
    @validator('name')
    def name_must_not_be_empty(cls, v):
        if not v.strip():
            raise ValueError('姓名不能為空')
        return v.strip()

# 註冊後自動獲得完整的驗證 API
crud = AutoCRUD()
crud.register_model(User)  # 🎯 所有驗證規則自動應用到 API
```

### 📦 簡潔選擇：Dataclass

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class Product:
    id: str
    name: str
    price: float
    category: str
    stock: int = 0
    
# 同樣能獲得完整的 REST API
crud.register_model(Product)  # -> 完整的 /products API
```

### 🔧 靈活選擇：TypedDict

```python
from typing import TypedDict, Optional

class Order(TypedDict):
    id: str
    user_id: str
    items: list
    total: float
    status: str

crud.register_model(Order)  # -> 完整的 /orders API
```

## ⚙️ 企業級功能配置

### 🕒 自動時間戳管理

讓 AutoCRUD 自動管理資料的創建和更新時間：

```python
from autocrud import AutoCRUD, MetadataConfig

# 啟用自動時間戳
metadata_config = MetadataConfig(
    enable_timestamps=True,  # 自動添加 created_time 和 updated_time
    enable_user_tracking=True,  # 自動添加 created_by 和 updated_by（如果需要）
    timestamp_field_names={
        "created_time": "created_time",
        "updated_time": "updated_time"
    }
)

crud = AutoCRUD(metadata_config=metadata_config)
crud.register_model(User)

# 創建資料時自動添加時間戳
user_id = crud.create("users", {"name": "Alice", "email": "alice@example.com"})
user = crud.get("users", user_id)
print(user["created_time"])  # 2024-01-15T10:30:00Z
print(user["updated_time"])  # 2024-01-15T10:30:00Z

# 你的 API 也自動支援時間範圍查詢
# GET /users?created_time_start=2024-01-01&created_time_end=2024-12-31
```

### 🔍 高級查詢功能

AutoCRUD 自動為你的 API 提供豐富的查詢功能：

```python
from autocrud import ListQueryParams, SortOrder
from datetime import datetime, timedelta

# 程式化查詢範例
params = ListQueryParams(
    page=1,
    page_size=20,
    sort_by="created_time",
    sort_order=SortOrder.DESC,
    created_time_start=datetime.now() - timedelta(days=7),  # 最近7天
    created_time_end=datetime.now()
)

result = crud.list("users", params)
print(f"找到 {result.total} 個最近創建的使用者")

# 這些查詢功能自動對應到 REST API：
# GET /users?page=1&page_size=20&sort_by=created_time&sort_order=desc
#             &created_time_start=2024-01-08T10:00:00Z
#             &created_time_end=2024-01-15T10:00:00Z
```

## 🏢 生產環境：資料持久化

### 開發環境：記憶體存儲

適用於原型開發和測試：

```python
# 預設使用記憶體存儲，重啟後資料消失
crud = AutoCRUD()  # 開發時最簡單
crud.register_model(User)
```

### 生產環境：磁碟存儲

確保資料持久化，適用於生產環境：

```python
from autocrud.storage import MemoryStorage

storage = MemoryStorage()
```

特點：
- 快速存取
- 程式結束後資料消失
- 適合測試和原型開發

### 硬碟儲存 (DiskStorage)

適用於持久化資料：

```python
from autocrud.storage import DiskStorage

storage = DiskStorage(
    storage_dir="./data",
    serializer_type="json"  # 或 "pickle", "msgpack"
)
```

特點：
- 資料持久化
- 支援多種序列化格式
- 自動建立儲存目錄

### 儲存工廠系統

AutoCRUD 支援儲存工廠來為不同資源創建專用的儲存後端：

```python
from autocrud import DefaultStorageFactory

# 使用預設工廠（每個資源使用獨立的記憶體儲存）
factory = DefaultStorageFactory()

multi_crud = AutoCRUD(storage_factory=factory)
```

## 查詢和分頁

AutoCRUD 支援複雜的查詢、分頁和排序：

```python
from autocrud import ListQueryParams, SortOrder

# 基本分頁查詢
query_params = ListQueryParams(
    page=1,
    page_size=20,
    sort_by="created_time",
    sort_order=SortOrder.DESC
)

result = user_crud.list(query_params)
print(f"總數: {result.total}")
print(f"當前頁: {result.page}")
print(f"項目: {result.items}")

# 時間範圍查詢
from datetime import datetime, timezone, timedelta

now = datetime.now(timezone.utc)
query_params = ListQueryParams(
    created_time_start=now - timedelta(days=7),
    created_time_end=now,
    sort_by="name"
)

recent_users = user_crud.list(query_params)
```

## 序列化格式

### JSON (推薦)

```python
storage = DiskStorage(serializer_type="json")
```

- 人類可讀
- 跨語言相容
- 較小的檔案大小

### Pickle

```python
storage = DiskStorage(serializer_type="pickle")
```

- Python 原生支援
- 支援任意 Python 對象
- 僅限 Python 使用

### MessagePack

```python
storage = DiskStorage(serializer_type="msgpack")
```

- 二進位格式
- 高效壓縮
- 跨語言支援

## 多模型管理

### 基本用法

```python
from autocrud import AutoCRUD, ResourceNameStyle
from autocrud.storage import MemoryStorage

# 建立多模型系統
multi_crud = AutoCRUD(
    resource_name_style=ResourceNameStyle.SNAKE,  # 命名風格
    use_plural=True  # 預設使用複數形式
)

# 註冊多個模型
user_crud = multi_crud.register_model(User)  # 返回 SingleModelCRUD 實例
product_crud = multi_crud.register_model(Product)
order_crud = multi_crud.register_model(Order)
```

### 資源名稱自訂

```python
# 自動產生複數形式 (預設)
multi_crud.register_model(User)  # -> users

# 指定單數形式
multi_crud.register_model(Product, use_plural=False)  # -> product

# 完全自訂名稱
multi_crud.register_model(Company, resource_name="organizations")  # -> organizations

# 不同的命名風格
multi_crud = AutoCRUD(resource_name_style=ResourceNameStyle.CAMEL)
multi_crud.register_model(UserProfile)  # -> userProfiles
```

### 跨模型操作

```python
# 直接在多模型系統上執行操作
user_id = multi_crud.create("users", {"name": "Alice", "email": "alice@example.com"})
product_id = multi_crud.create("products", {"name": "Laptop", "price": 999.99})

# 取得特定模型的 CRUD 實例
user_crud = multi_crud.get_resource_crud("users")
all_users = user_crud.list_all()

# 列出所有註冊的資源
resources = multi_crud.list_resources()
```

## 插件系統

AutoCRUD 支援可擴展的插件系統：

### 使用預設插件

```python
from autocrud import DEFAULT_PLUGINS, plugin_manager

# 預設插件包含：create, get, update, delete, count, list
print([plugin.name for plugin in DEFAULT_PLUGINS])

# 確保註冊預設插件
from autocrud import ensure_default_plugins_registered
ensure_default_plugins_registered()
```

### 創建自訂插件

```python
from autocrud import BaseRoutePlugin, PluginRouteConfig, RouteMethod
from fastapi import BackgroundTasks

class HealthCheckPlugin(BaseRoutePlugin):
    def __init__(self):
        super().__init__("health", "1.0.0")
    
    def get_routes(self, crud):
        async def health_handler(crud, background_tasks: BackgroundTasks):
            return {"status": "healthy", "resource": crud.resource_name}
        
        return [PluginRouteConfig(
            name="health",
            path="/health",
            method=RouteMethod.GET,
            handler=health_handler,
            summary="健康檢查",
            priority=1  # 高優先級
        )]

# 註冊插件
from autocrud import plugin_manager
plugin_manager.register_plugin(HealthCheckPlugin())
```

## 高級更新系統

AutoCRUD 支援原子操作的高級更新：

```python
from autocrud import AdvancedUpdater, set_value, list_add, dict_update

updater = AdvancedUpdater()

# 定義更新操作
operations = [
    set_value("status", "active"),
    list_add("tags", "premium"),
    dict_update("metadata", {"last_login": "2024-01-01"})
]

# 執行原子更新
success = updater.update(user_crud, user_id, operations)
```

## FastAPI 整合

### 單模型 API

```python
from autocrud import SingleModelCRUD
from autocrud.fastapi_generator import FastAPIGenerator

user_crud = SingleModelCRUD(model=User, storage=storage, resource_name="users")

# 使用 FastAPIGenerator
generator = FastAPIGenerator()
app = generator.create_app(
    crud_systems=[user_crud],
    title="User API",
    description="使用者管理 API",
    version="1.0.0"
)
```

### 多模型 API

```python
from autocrud import AutoCRUD

multi_crud = AutoCRUD()
multi_crud.register_model(User)
multi_crud.register_model(Product)

app = multi_crud.create_fastapi_app(
    title="多模型 API",
    description="統一的 CRUD API",
    prefix="/api/v1"
)
```

### 路由配置

可以透過 RouteConfig 自訂路由行為：

```python
from autocrud import RouteConfig, RouteOptions

# 自訂路由配置
route_config = RouteConfig(
    create=RouteOptions.enabled_route(),
    get=RouteOptions.enabled_route(),
    update=RouteOptions.disabled_route(),  # 禁用更新
    delete=RouteOptions.disabled_route(),  # 禁用刪除
    list=RouteOptions.enabled_route(),
    count=RouteOptions.enabled_route()
)

user_crud = SingleModelCRUD(
    model=User,
    storage=storage,
    resource_name="users",
    route_config=route_config
)
```

### 自訂路由前綴

```python
app = multi_crud.create_fastapi_app(
    prefix="/api/v2"  # 所有路由將以 /api/v2 開頭
)
```

## 錯誤處理

AutoCRUD 提供了統一的錯誤處理機制：

```python
# CRUD 方法的返回值
user_id = user_crud.create(data)  # 成功返回 ID，失敗拋出異常
user = user_crud.get(user_id)  # 成功返回資料，不存在返回 None
success = user_crud.update(user_id, data)  # 成功返回 True，失敗返回 False
success = user_crud.delete(user_id)  # 成功返回 True，失敗返回 False

# FastAPI 路由會自動處理異常並返回適當的HTTP狀態碼
```

## 效能最佳化

### 大量資料處理

```python
# 使用 list_all 時要小心記憶體使用
all_users = user_crud.list_all()  # 可能消耗大量記憶體

# 建議使用分頁查詢
query_params = ListQueryParams(page=1, page_size=100)
page_result = user_crud.list(query_params)
```

### 儲存後端選擇

```python
# 開發和測試：使用記憶體儲存
storage = MemoryStorage()

# 生產環境：使用硬碟儲存搭配 JSON 序列化
storage = DiskStorage(storage_dir="./data", serializer_type="json")

# 高效能需求：使用 MessagePack 序列化
storage = DiskStorage(storage_dir="./data", serializer_type="msgpack")
```

## ID 產生器

### 預設 UUID 產生器

```python
# 使用預設的 UUID4 產生器
crud = SingleModelCRUD(model=User, storage=storage, resource_name="users")
```

### 自訂 ID 產生器

```python
def custom_id_generator():
    import time
    return f"user_{int(time.time())}"

crud = SingleModelCRUD(
    model=User,
    storage=storage,
    resource_name="users",
    id_generator=custom_id_generator
)
```

### 序列 ID 產生器

```python
def sequential_id_generator():
    if not hasattr(sequential_id_generator, 'counter'):
        sequential_id_generator.counter = 0
    sequential_id_generator.counter += 1
    return str(sequential_id_generator.counter)

crud = SingleModelCRUD(
    model=User,
    storage=storage,
    resource_name="users",
    id_generator=sequential_id_generator
)
```

## 錯誤處理

### 常見異常

```python
from autocrud.exceptions import AutoCRUDError, ValidationError, StorageError

try:
    user = crud.create(invalid_data)
except ValidationError as e:
    print(f"資料驗證錯誤: {e}")
except StorageError as e:
    print(f"儲存錯誤: {e}")
except AutoCRUDError as e:
    print(f"通用錯誤: {e}")
```

### 資料驗證

```python
# Pydantic 模型會自動進行資料驗證
from pydantic import BaseModel, validator

class User(BaseModel):
    name: str
    age: int
    
    @validator('age')
    def validate_age(cls, v):
        if v < 0:
            raise ValueError('年齡不能為負數')
        return v
```

## 最佳實踐

### 1. 模型設計

```python
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime

@dataclass
class User:
    name: str
    email: str
    age: Optional[int] = None
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    tags: List[str] = field(default_factory=list)
```

### 2. 儲存選擇

- **開發/測試**: 使用 `MemoryStorage`
- **生產環境**: 使用 `DiskStorage` 配合適當的序列化格式
- **大量資料**: 考慮實作自訂儲存後端

### 3. API 設計

```python
# 為不同的資源使用合適的 URL 形式
multi_crud.register_model(User)  # RESTful: /users
multi_crud.register_model(Config, use_plural=False)  # Singleton: /config
multi_crud.register_model(Company, resource_name="organizations")  # Custom: /organizations
```

### 4. 錯誤處理

```python
from fastapi import HTTPException

def safe_create_user(data: dict):
    try:
        return user_crud.create(data)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except StorageError as e:
        raise HTTPException(status_code=500, detail="儲存錯誤")
```

## 效能考慮

### 記憶體使用

- `MemoryStorage` 將所有資料保存在記憶體中
- 對於大量資料，考慮使用 `DiskStorage`

### 序列化效能

- JSON: 平衡效能和可讀性
- Pickle: 最快，但僅限 Python
- MessagePack: 高效的二進位格式

### 併發存取

目前的實作不是執行緒安全的。在高併發環境中：

1. 使用適當的鎖機制
2. 考慮使用資料庫後端
3. 實作自訂的執行緒安全儲存後端
