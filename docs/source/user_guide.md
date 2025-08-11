# 用戶指南

本指南深入介紹 AutoCRUD 的功能和配置選項。

## 數據類型支持

AutoCRUD v0.3 支持四種主要的 Python 數據類型，每種都有其優勢：

### TypedDict

適合簡單場景，輕量級且與標準庫兼容：

```python
from typing import TypedDict, Optional

class Product(TypedDict):
    name: str
    price: float
    description: Optional[str]
    in_stock: bool

# 使用
crud.add_model(Product)  # 生成 /product 端點
```

**優點：**
- 零依賴，使用標準庫
- 輕量級，內存佔用小
- 與現有字典代碼兼容

**適用場景：**
- 簡單的數據結構
- 原型開發
- 需要與字典兼容的場景

### Pydantic BaseModel

提供強大的數據驗證和序列化功能：

```python
from pydantic import BaseModel, EmailStr, validator
from typing import Optional
from datetime import datetime

class User(BaseModel):
    name: str
    email: EmailStr
    age: Optional[int] = None
    created_at: datetime = datetime.now()
    
    @validator('age')
    def validate_age(cls, v):
        if v is not None and v < 0:
            raise ValueError('Age must be positive')
        return v

# 使用
crud.add_model(User)
```

**優點：**
- 強大的數據驗證
- 豐富的類型支持
- 優秀的錯誤消息
- 廣泛的生態系統

**適用場景：**
- 需要複雜驗證邏輯
- 與現有 Pydantic 代碼集成
- 對數據完整性要求高

### dataclass

Python 原生支持，平衡性能和功能：

```python
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime

@dataclass
class Order:
    id: str
    customer_name: str
    items: List[str] = field(default_factory=list)
    total_amount: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    status: str = "pending"

# 使用
crud.add_model(Order)
```

**優點：**
- Python 原生支持
- 良好的性能
- 清晰的語法
- IDE 支持良好

**適用場景：**
- 需要 Python 原生支持
- 對性能有一定要求
- 中等複雜度的數據結構

### msgspec.Struct

高性能序列化，適合對性能要求極高的場景：

```python
import msgspec
from typing import Optional

class Event(msgspec.Struct):
    id: str
    type: str
    payload: dict
    timestamp: Optional[float] = None
    processed: bool = False

# 使用
crud.add_model(Event)
```

**優點：**
- 極高的序列化性能
- 緊湊的內存佔用
- 支持二進制序列化
- 現代化的類型系統

**適用場景：**
- 高頻數據處理
- 微服務間通信
- 對性能要求極高的場景

## 配置選項

### 命名約定

AutoCRUD 支持多種命名約定：

```python
# kebab-case (推薦)
crud = AutoCRUD(model_naming="kebab")
# UserProfile -> /user-profile

# snake_case
crud = AutoCRUD(model_naming="snake")
# UserProfile -> /user_profile

# camelCase
crud = AutoCRUD(model_naming="camel")
# UserProfile -> /userProfile

# PascalCase
crud = AutoCRUD(model_naming="pascal")
# UserProfile -> /UserProfile

# 保持原名
crud = AutoCRUD(model_naming="same")
# UserProfile -> /UserProfile

# 自定義函數
def custom_naming(model_type):
    return f"api_{model_type.__name__.lower()}"

crud = AutoCRUD(model_naming=custom_naming)
# UserProfile -> /api_userprofile
```

### 路由模板

AutoCRUD 使用路由模板系統，您可以選擇需要的操作：

```python
from autocrud.crud.core import (
    CreateRouteTemplate,
    ReadRouteTemplate,
    UpdateRouteTemplate,
    DeleteRouteTemplate,
    ListRouteTemplate,
    PatchRouteTemplate,
    SwitchRevisionRouteTemplate,
    RestoreRouteTemplate,
)

crud = AutoCRUD()

# 只添加讀取操作
crud.add_route_template(ReadRouteTemplate())
crud.add_route_template(ListRouteTemplate())

# 添加基本 CRUD
crud.add_route_template(CreateRouteTemplate())
crud.add_route_template(ReadRouteTemplate())
crud.add_route_template(UpdateRouteTemplate())
crud.add_route_template(DeleteRouteTemplate())
crud.add_route_template(ListRouteTemplate())

# 添加高級功能
crud.add_route_template(PatchRouteTemplate())        # PATCH 部分更新
crud.add_route_template(SwitchRevisionRouteTemplate()) # 版本切換
crud.add_route_template(RestoreRouteTemplate())       # 恢復已刪除資源
```

### 自定義存儲

默認情況下，AutoCRUD 使用內存存儲。您也可以提供自定義存儲：

```python
from autocrud.resource_manager.core import SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore

def create_custom_storage():
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore[User](resource_type=User)
    return SimpleStorage(meta_store, resource_store)

# 使用自定義存儲
crud.add_model(User, storage_factory=create_custom_storage)
```

## 高級功能

### 依賴注入

您可以自定義用戶和時間的獲取方式：

```python
from autocrud.crud.core import DependencyProvider

def get_current_user():
    return "current_user_id"

def get_current_time():
    return datetime.now()

deps = DependencyProvider(
    get_user=get_current_user,
    get_now=get_current_time
)

# 使用自定義依賴
crud.add_route_template(CreateRouteTemplate(dependency_provider=deps))
```

### 響應類型

列表和讀取操作支持多種響應類型：

```python
# GET /user?response_type=data (默認)
# 返回: {"name": "John", "email": "john@example.com"}

# GET /user?response_type=meta
# 返回: {"resource_id": "123", "created_time": "...", ...}

# GET /user?response_type=full
# 返回: {"data": {...}, "meta": {...}, "revision_info": {...}}

# GET /user?response_type=revision_info
# 返回: {"revision_id": "abc", "status": "active", ...}
```

### 查詢和篩選

列表操作支持豐富的查詢選項：

```python
# 分頁
GET /user?limit=10&offset=20

# 時間範圍篩選
GET /user?created_time_start=2024-01-01&created_time_end=2024-12-31

# 按創建者篩選
GET /user?created_bys=user1,user2

# 包含已刪除項目
GET /user?is_deleted=true
```

## 錯誤處理

AutoCRUD 提供統一的錯誤處理：

- `400 Bad Request`: 一般錯誤
- `404 Not Found`: 資源不存在
- `422 Unprocessable Entity`: 數據驗證錯誤

## 最佳實踐

### 1. 選擇合適的數據類型

- **簡單項目**: TypedDict
- **需要驗證**: Pydantic
- **追求性能**: msgspec.Struct
- **平衡選擇**: dataclass

### 2. 合理命名

使用 kebab-case 作為 API 端點命名：

```python
crud = AutoCRUD(model_naming="kebab")
```

### 3. 模塊化路由模板

根據需求選擇路由模板：

```python
# 只讀 API
read_only_templates = [ReadRouteTemplate(), ListRouteTemplate()]

# 完整 CRUD
full_crud_templates = [
    CreateRouteTemplate(),
    ReadRouteTemplate(),
    UpdateRouteTemplate(),
    DeleteRouteTemplate(),
    ListRouteTemplate(),
]
```

### 4. 環境配置

```python
import os

def create_app():
    crud = AutoCRUD(
        model_naming=os.getenv("NAMING_STYLE", "kebab")
    )
    # ... 其他配置
```

## 遷移指南

從 AutoCRUD v0.2 遷移到 v0.3：

### 舊版本 (v0.2)
```python
from autocrud import AutoCRUD

crud = AutoCRUD()
crud.register_model(User)
app = crud.create_fastapi_app()
```

### 新版本 (v0.3)
```python
from autocrud.crud.core import AutoCRUD, CreateRouteTemplate, ReadRouteTemplate
from fastapi import FastAPI, APIRouter

crud = AutoCRUD(model_naming="kebab")
crud.add_route_template(CreateRouteTemplate())
crud.add_route_template(ReadRouteTemplate())
crud.add_model(User)

app = FastAPI()
router = APIRouter()
crud.apply(router)
app.include_router(router)
```

主要變化：
1. 更明確的路由模板系統
2. 分離的 FastAPI 應用創建
3. 支持多種數據類型
4. 更靈活的配置選項
