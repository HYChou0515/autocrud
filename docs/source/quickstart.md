# 快速入門

## 5 分鐘開始使用 AutoCRUD

### 第一步：定義你的資料模型

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class User:
    id: str  # ID 欄位是必需的
    name: str
    email: str
    age: Optional[int] = None
```

### 第二步：建立 CRUD 系統

```python
from autocrud import SingleModelCRUD
from autocrud.storage import MemoryStorage

# 建立儲存後端
storage = MemoryStorage()

# 建立單模型 CRUD 實例
user_crud = SingleModelCRUD(model=User, storage=storage, resource_name="users")
```

### 第三步：執行 CRUD 操作

```python
# 建立使用者
user_data = {"name": "Alice", "email": "alice@example.com", "age": 30}
user_id = user_crud.create(user_data)  # 返回生成的 ID
print(f"建立的使用者 ID: {user_id}")

# 取得使用者
retrieved_user = user_crud.get(user_id)
print(f"取得的使用者: {retrieved_user}")

# 更新使用者
success = user_crud.update(user_id, {"age": 31})
print(f"更新成功: {success}")

# 列出所有使用者（支援分頁和排序）
from autocrud import ListQueryParams, SortOrder

query_params = ListQueryParams(
    page=1,
    page_size=10,
    sort_by="name",
    sort_order=SortOrder.ASC
)
result = user_crud.list(query_params)
print(f"使用者列表: {result.items}")
print(f"總數: {result.total}")

# 刪除使用者
deleted = user_crud.delete(user_id)
print(f"刪除成功: {deleted}")
```

### 第四步：產生 FastAPI 應用

```python
from autocrud.fastapi_generator import FastAPIGenerator

# 創建 FastAPI 生成器
generator = FastAPIGenerator()

# 生成 FastAPI 應用
app = generator.create_app(
    crud_systems=[user_crud],
    title="User API",
    description="使用者管理 API",
    version="1.0.0"
)

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
