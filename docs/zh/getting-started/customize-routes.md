---
title: 調整 API Routes
description: 自定義 AutoCRUD 的 API 路由和端點
---

# 調整 API Routes

AutoCRUD 提供強大的路由自定義功能，讓你可以完全控制 API 的端點設計。從簡單的資源命名，到進階的路由模板客製化。

## 基礎：自定義資源名稱

### 使用 `name` 參數

最簡單的方式是在 `add_model` 時指定自定義名稱：

```python
from msgspec import Struct
from autocrud import AutoCRUD

class TodoItem(Struct):
    title: str
    completed: bool = False

crud = AutoCRUD()

# 預設會是 "todo-item"
# crud.add_model(TodoItem)

# 自定義為 "tasks"
crud.add_model(TodoItem, name="tasks")
```

生成的端點：

- `/tasks` - 建立任務
- `/tasks/{id}/data` - 取得任務資料
- `/tasks/data` - 列出所有任務

### 全域命名策略

使用 `model_naming` 參數設定全域的命名轉換規則：

```python
from autocrud import AutoCRUD

# Kebab case (預設): UserProfile -> user-profile
crud = AutoCRUD(model_naming="kebab")

# Snake case: UserProfile -> user_profile
crud = AutoCRUD(model_naming="snake")

# Camel case: UserProfile -> userProfile
crud = AutoCRUD(model_naming="camel")

# Pascal case: UserProfile -> UserProfile
crud = AutoCRUD(model_naming="pascal")

# 保持原樣: UserProfile -> UserProfile
crud = AutoCRUD(model_naming="same")
```

### 自定義命名函數

```python
def custom_naming(model_type: type) -> str:
    """自定義命名邏輯"""
    name = model_type.__name__
    # 例如：在所有資源前加上 api/v1/ 前綴
    return f"api/v1/{name.lower()}"

crud = AutoCRUD(model_naming=custom_naming)
crud.add_model(TodoItem)  # 生成 /api/v1/todoitem
```

## 路由模板系統

AutoCRUD 使用「路由模板」(Route Template) 來生成 API 端點。每個模板負責生成一組相關的路由。

### 內建路由模板

預設包含以下模板：

1. **CreateRouteTemplate** - 建立資源
2. **ReadRouteTemplate** - 讀取資源
3. **UpdateRouteTemplate** - 更新資源
4. **PatchRouteTemplate** - 部分更新 (JSON Patch)
5. **DeleteRouteTemplate** - 刪除資源
6. **RestoreRouteTemplate** - 還原資源
7. **ListRouteTemplate** - 列表與搜尋
8. **SwitchRevisionRouteTemplate** - 版本切換

### 選擇性啟用路由模板

你可以只啟用需要的路由模板：

```python
from autocrud import AutoCRUD
from autocrud.crud.route_templates.create import CreateRouteTemplate
from autocrud.crud.route_templates.get import ReadRouteTemplate
from autocrud.crud.route_templates.search import ListRouteTemplate

# 只提供讀取功能的 API
crud = AutoCRUD(
    route_templates=[
        ReadRouteTemplate(),
        ListRouteTemplate(),
    ]
)

crud.add_model(TodoItem)
```

這樣只會生成：

- `GET /todo-item/{id}/data` - 讀取文章
- `GET /todo-item/data` - 列出文章

而不會有建立、更新、刪除等端點。

## 進階路由模板

### GraphQL 支援

啟用 GraphQL 查詢端點：

```python
from autocrud import AutoCRUD
from autocrud.crud.route_templates.graphql import GraphQLRouteTemplate

crud = AutoCRUD()
crud.add_route_template(GraphQLRouteTemplate())
crud.add_model(TodoItem)
```

生成端點：`POST /todo-item/graphql`

使用範例：

```graphql
query {
  users(filter: { age: { _gte: 18 } }, limit: 10) {
    resource_id
    data {
      name
      email
    }
  }
}
```

### Blob 檔案處理

為包含二進位檔案的資源啟用專用端點：

```python
from autocrud import AutoCRUD
from autocrud.crud.route_templates.blob import BlobRouteTemplate
from autocrud.types import Binary
from msgspec import Struct

class ProfileImage(Struct):
    user_id: str
    image: Binary  # 二進位檔案
    description: str = ""

crud = AutoCRUD()
crud.add_route_template(BlobRouteTemplate())
crud.add_model(ProfileImage)
```

生成額外端點：

- `GET /profile-image/{id}/blobs/{field_name}` - 下載二進位檔案
- `PUT /profile-image/{id}/blobs/{field_name}` - 上傳二進位檔案

### Schema 遷移端點

啟用資料遷移測試端點：

```python
from autocrud import AutoCRUD
from autocrud.crud.route_templates.migrate import MigrateRouteTemplate
from autocrud.types import IMigration
from typing import IO

crud = AutoCRUD()
crud.add_route_template(MigrateRouteTemplate())

# 定義遷移邏輯
class TodoItemMigration(IMigration):
    schema_version = "2"
    
    def migrate(self, data: IO[bytes], schema_version: str | None) -> dict:
        import msgspec
        old_data = msgspec.json.decode(data.read())
        old_data["new_field"] = "default_value"
        return old_data

crud.add_model(
    TodoItem,
    migration=TodoItemMigration()
)
```

生成端點：

- `POST /todo-item/migrate/test` - 測試遷移（不實際修改資料）
- `POST /todo-item/migrate/execute` - 執行遷移

## 實際範例

### 範例 1：唯讀 API

```python title="readonly_api.py"
from msgspec import Struct
from fastapi import FastAPI
from autocrud import AutoCRUD
from autocrud.crud.route_templates.get import ReadRouteTemplate
from autocrud.crud.route_templates.search import ListRouteTemplate

class Product(Struct):
    name: str
    price: float
    stock: int

# 只允許讀取，不允許修改
crud = AutoCRUD(
    route_templates=[
        ReadRouteTemplate(),
        ListRouteTemplate(),
    ]
)

crud.add_model(Product)

app = FastAPI(title="Product Catalog (Read-only)")
crud.apply(app)
```

### 範例 2：完整功能 API

```python title="full_featured_api.py"
from msgspec import Struct
from autocrud import AutoCRUD
from autocrud.crud.route_templates.graphql import GraphQLRouteTemplate
from autocrud.crud.route_templates.blob import BlobRouteTemplate
from autocrud.crud.route_templates.migrate import MigrateRouteTemplate
from autocrud.types import Binary

class Document(Struct):
    title: str
    content: str
    attachment: Binary | None = None
    version: int = 1

crud = AutoCRUD()

# 添加進階功能
crud.add_route_template(GraphQLRouteTemplate())
crud.add_route_template(BlobRouteTemplate())
crud.add_route_template(MigrateRouteTemplate())

crud.add_model(Document)

# 生成的端點包括：
# - 標準 CRUD
# - GraphQL 查詢
# - 檔案上傳/下載
# - Schema 遷移
```

### 範例 3：多資源不同配置

```python title="mixed_config.py"
from msgspec import Struct
from fastapi import FastAPI, APIRouter
from autocrud import AutoCRUD
from autocrud.crud.route_templates.create import CreateRouteTemplate
from autocrud.crud.route_templates.get import ReadRouteTemplate
from autocrud.crud.route_templates.search import ListRouteTemplate

class User(Struct):
    username: str
    email: str

class AuditLog(Struct):
    action: str
    user_id: str
    timestamp: str

app = FastAPI()

# User: 完整 CRUD（使用預設路由模板）
user_crud = AutoCRUD()
user_crud.add_model(User)
user_crud.apply(app)

# AuditLog: 只能建立和讀取（Append-only）
audit_crud = AutoCRUD(
    route_templates=[
        CreateRouteTemplate(),
        ReadRouteTemplate(),
        ListRouteTemplate(),
    ]
)
audit_crud.add_model(AuditLog)
audit_crud.apply(app)
```

### 範例 4：自定義路由前綴

```python title="custom_prefix.py"
from msgspec import Struct
from fastapi import FastAPI
from autocrud import AutoCRUD

class User(Struct):
    name: str

class Product(Struct):
    title: str

crud = AutoCRUD()

# 方式 1: 使用 name 參數
crud.add_model(User, name="api/v1/users")
crud.add_model(Product, name="api/v1/products")

# 方式 2: 使用 FastAPI 的 prefix
app = FastAPI()
from fastapi import APIRouter
api_router = APIRouter(prefix="/api/v1")
crud.apply(api_router)
app.include_router(api_router)
```

## 自定義路由模板

你可以建立自己的路由模板來添加自定義端點：

```python
from autocrud.crud.route_templates.basic import IRouteTemplate, BaseRouteTemplate
from fastapi import APIRouter

class CustomStatsRouteTemplate(BaseRouteTemplate):
    """自定義統計資訊端點"""
    
    @property
    def order(self) -> int:
        return 1000  # 控制路由註冊順序
    
    def apply(self, model_name: str, resource_manager, router: APIRouter):
        @router.get(f"/{model_name}/stats")
        async def get_stats():
            """取得資源統計資訊"""
            total = len(resource_manager.list())
            return {
                "total_count": total,
                "model_name": model_name,
            }

# 使用自定義模板
crud = AutoCRUD()
crud.add_route_template(CustomStatsRouteTemplate())
crud.add_model(User)

# 生成端點: GET /user/stats
```

## 路由優先順序

路由模板透過 `order` 屬性控制註冊順序。數字越小越早註冊：

- 0-99: 高優先級（特殊路由）
- 100-199: CRUD 基本操作
- 200-299: 進階功能
- 300+: 自定義路由

確保更具體的路由（如 `/user/stats`）在更通用的路由（如 `/user/{id}`）之前註冊。

## 最佳實踐

### 1. 明確指定需要的端點

```python
# ✅ 好：明確列出需要的功能
crud = AutoCRUD(
    route_templates=[
        CreateRouteTemplate(),
        ReadRouteTemplate(),
        ListRouteTemplate(),
    ]
)
```

### 2. 為不同資源使用不同配置

不同的資源可以使用不同的 AutoCRUD 實例來配置不同的路由：

```python
# User: 完整 CRUD
user_crud = AutoCRUD()
user_crud.add_model(User)

# AuditLog: 只有建立和讀取
audit_crud = AutoCRUD(
    route_templates=[
        CreateRouteTemplate(),
        ReadRouteTemplate(),
        ListRouteTemplate(),
    ]
)
audit_crud.add_model(AuditLog)

# 應用到同一個 FastAPI app
app = FastAPI()
user_crud.apply(app)
audit_crud.apply(app)
```

### 3. 使用語意化的資源名稱

```python
# ✅ 好：清楚的資源名稱
crud.add_model(UserProfile, name="profiles")
crud.add_model(BlogPost, name="posts")

# ❌ 避免：過於簡短或不清楚
crud.add_model(UserProfile, name="up")
```

### 4. 組織 API 版本

```python
# ✅ 好：清楚的版本控制
crud.add_model(User, name="user")
crud.add_model(UserV2, name="user-v2")
```

## 常見問題

### Q: 如何移除特定端點？

A: 使用 `route_templates` 參數只包含需要的模板。

### Q: 可以為同一個模型註冊多次嗎？

A: 可以，使用不同的 `name` 參數即可。

```python
crud.add_model(User, name="user")
crud.add_model(User, name="admin-user")  # 不同的端點
```

### Q: 如何添加認證到特定端點？

A: 在自定義路由模板中使用 FastAPI 的 `Depends`：

```python
from fastapi import Depends, APIRouter
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from autocrud.crud.route_templates.basic import BaseRouteTemplate

security = HTTPBearer()

class SecureReadTemplate(BaseRouteTemplate):
    @property
    def order(self) -> int:
        return 100
    
    def apply(self, model_name: str, resource_manager, router: APIRouter):
        @router.get(
            f"/{model_name}/{{resource_id}}/data",
            dependencies=[Depends(security)]  # 需要認證
        )
        async def read_resource(
            resource_id: str,
            credentials: HTTPAuthorizationCredentials = Depends(security)
        ):
            # 驗證 token（範例）
            # if not verify_token(credentials.credentials):
            #     raise HTTPException(status_code=401, detail="Invalid token")
            
            # 取得資源
            resource = resource_manager.get(resource_id)
            return resource.data

# 使用範例
crud = AutoCRUD()
crud.add_route_template(SecureReadTemplate())
crud.add_model(User)
```

### Q: 路由模板的執行順序重要嗎？

A: 是的，特別是有路徑衝突時。使用 `order` 屬性確保更具體的路由先註冊。

## 下一步

<div class="grid cards" markdown>

-   :material-routes: __了解自動生成的路由__

    ---

    查看 AutoCRUD 自動生成的完整端點列表

    [:octicons-arrow-right-24: AutoCRUD 路由](../core-concepts/auto-routes.md)

-   :material-code-braces: __查看實際範例__

    ---

    探索完整的 API 配置範例

    [:octicons-arrow-right-24: RPG 遊戲 API](../examples/index.md)

-   :material-api: __API 參考文件__

    ---

    深入了解所有路由模板的 API

    [:octicons-arrow-right-24: API Reference](../reference/autocrud.md)

</div>
