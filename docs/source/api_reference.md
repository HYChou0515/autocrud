# API 參考

AutoCRUD v0.3 完整 API 參考文檔。

## 核心類

### AutoCRUD

主要的 CRUD 管理器類。

```python
from autocrud.crud.core import AutoCRUD

crud = AutoCRUD(model_naming="kebab")
```

#### 參數

- `model_naming` (str | Callable): 模型命名策略
  - `"kebab"`: UserProfile → user-profile (推薦)
  - `"snake"`: UserProfile → user_profile  
  - `"camel"`: UserProfile → userProfile
  - `"pascal"`: UserProfile → UserProfile
  - `"same"`: 保持原名
  - 自定義函數: `(model_type) → str`

#### 方法

##### `add_route_template(template: IRouteTemplate)`

添加路由模板。

```python
crud.add_route_template(CreateRouteTemplate())
```

##### `add_model(model, *, name=None, storage_factory=None)`

註冊數據模型。

```python
crud.add_model(User)  # 自動命名
crud.add_model(User, name="custom-user")  # 自定義名稱
crud.add_model(User, storage_factory=my_storage_factory)  # 自定義存儲
```

**參數:**
- `model`: 數據模型類 (Pydantic, dataclass, TypedDict, msgspec.Struct)
- `name`: 可選的自定義端點名稱
- `storage_factory`: 可選的自定義存儲工廠函數

##### `apply(router: APIRouter) → APIRouter`

將所有生成的路由應用到 FastAPI 路由器。

```python
router = APIRouter()
crud.apply(router)
```

## 路由模板

所有路由模板都實現 `IRouteTemplate` 接口。

### CreateRouteTemplate

生成創建資源的端點。

```python
from autocrud.crud.core import CreateRouteTemplate

template = CreateRouteTemplate(dependency_provider=deps)
```

**生成端點:** `POST /{model_name}`

**響應:**
```json
{
  "resource_id": "uuid",
  "revision_id": "uuid"
}
```

### ReadRouteTemplate

生成讀取單一資源的端點。

```python
from autocrud.crud.core import ReadRouteTemplate

template = ReadRouteTemplate(dependency_provider=deps)
```

**生成端點:** `GET /{model_name}/{resource_id}`

**查詢參數:**
- `response_type`: 響應類型 (data|meta|revision_info|full)
- `revision_id`: 特定版本 ID

**響應類型:**
- `data` (默認): 只返回資源數據
- `meta`: 只返回元數據
- `revision_info`: 只返回版本信息
- `full`: 返回所有信息

### UpdateRouteTemplate

生成更新資源的端點。

```python
from autocrud.crud.core import UpdateRouteTemplate

template = UpdateRouteTemplate(dependency_provider=deps)
```

**生成端點:** `PUT /{model_name}/{resource_id}`

**響應:**
```json
{
  "resource_id": "uuid",
  "revision_id": "uuid"
}
```

### DeleteRouteTemplate

生成刪除資源的端點。

```python
from autocrud.crud.core import DeleteRouteTemplate

template = DeleteRouteTemplate(dependency_provider=deps)
```

**生成端點:** `DELETE /{model_name}/{resource_id}`

**響應:**
```json
{
  "resource_id": "uuid", 
  "deleted": true
}
```

### ListRouteTemplate

生成列出所有資源的端點。

```python
from autocrud.crud.core import ListRouteTemplate

template = ListRouteTemplate(dependency_provider=deps)
```

**生成端點:** `GET /{model_name}`

**查詢參數:**
- `response_type`: 響應類型 (data|meta|revision_info|full)
- `limit`: 最大結果數 (默認 10)
- `offset`: 跳過的結果數 (默認 0)
- `is_deleted`: 是否包含已刪除項目
- `created_time_start`: 創建時間範圍開始
- `created_time_end`: 創建時間範圍結束
- `updated_time_start`: 更新時間範圍開始  
- `updated_time_end`: 更新時間範圍結束
- `created_bys`: 創建者列表
- `updated_bys`: 更新者列表

**響應:**
```json
{
  "resources": [...]
}
```

### PatchRouteTemplate

生成 JSON Patch 部分更新端點。

```python
from autocrud.crud.core import PatchRouteTemplate

template = PatchRouteTemplate(dependency_provider=deps)
```

**生成端點:** `PATCH /{model_name}/{resource_id}`

**請求體:** JSON Patch 操作數組
```json
[
  {"op": "replace", "path": "/name", "value": "新名稱"},
  {"op": "add", "path": "/tags/-", "value": "新標籤"}
]
```

### SwitchRevisionRouteTemplate

生成版本切換端點。

```python
from autocrud.crud.core import SwitchRevisionRouteTemplate

template = SwitchRevisionRouteTemplate(dependency_provider=deps)
```

**生成端點:** `POST /{model_name}/{resource_id}/switch/{revision_id}`

### RestoreRouteTemplate

生成恢復已刪除資源的端點。

```python
from autocrud.crud.core import RestoreRouteTemplate

template = RestoreRouteTemplate(dependency_provider=deps)
```

**生成端點:** `POST /{model_name}/{resource_id}/restore`

## 依賴注入

### DependencyProvider

管理用戶和時間依賴的提供者。

```python
from autocrud.crud.core import DependencyProvider

def get_current_user() -> str:
    return "user_123"

def get_current_time() -> datetime:
    return datetime.utcnow()

deps = DependencyProvider(
    get_user=get_current_user,
    get_now=get_current_time
)

template = CreateRouteTemplate(dependency_provider=deps)
```

#### 參數

- `get_user`: 返回當前用戶 ID 的函數
- `get_now`: 返回當前時間的函數

如果不提供，會使用默認實現：
- 默認用戶: `"anonymous"`
- 默認時間: `datetime.now()`

## 數據轉換器

### DataConverter

處理不同數據類型的序列化和反序列化。

```python
from autocrud.crud.core import DataConverter

# 檢查是否是 Pydantic 模型
is_pydantic = DataConverter.is_pydantic_model(User)

# 將 JSON bytes 轉換為數據
data = DataConverter.decode_json_to_data(json_bytes, User)

# 將數據轉換為 Python 內建類型
builtins = DataConverter.data_to_builtins(data)
```

#### 靜態方法

##### `is_pydantic_model(model_type: type) → bool`

檢查類型是否是 Pydantic BaseModel。

##### `decode_json_to_data(json_bytes: bytes, resource_type: type) → Any`

將 JSON bytes 轉換為指定類型的數據對象。

##### `data_to_builtins(data: Any) → Any`

將數據轉換為 Python 內建類型，特殊處理 msgspec.Raw。

## 命名轉換器

### NameConverter

在不同命名格式之間轉換。

```python
from autocrud.crud.core import NameConverter

converter = NameConverter("UserProfile")
kebab = converter.to("kebab")  # "user-profile"
snake = converter.to("snake")  # "user_profile"
```

#### 方法

##### `to(target_format: NamingFormat | str) → str`

轉換到目標格式。

支持的格式：
- `"same"`: 保持原名
- `"pascal"`: PascalCase
- `"camel"`: camelCase  
- `"snake"`: snake_case
- `"kebab"`: kebab-case

## 枚舉

### NamingFormat

命名格式枚舉。

```python
from autocrud.crud.core import NamingFormat

NamingFormat.KEBAB   # "kebab"
NamingFormat.SNAKE   # "snake"
NamingFormat.CAMEL   # "camel"
NamingFormat.PASCAL  # "pascal"
NamingFormat.SAME    # "same"
```

### ListResponseType

列表響應類型枚舉。

```python
from autocrud.crud.core import ListResponseType

ListResponseType.DATA          # "data"
ListResponseType.META          # "meta"
ListResponseType.REVISION_INFO # "revision_info"
ListResponseType.FULL          # "full"
ListResponseType.REVISIONS     # "revisions"
```

## 響應模型

### ResourceMetaResponse

資源元數據響應模型。

```python
{
  "current_revision_id": "string",
  "resource_id": "string", 
  "schema_version": "string",
  "total_revision_count": 0,
  "created_time": "2024-01-01T00:00:00",
  "updated_time": "2024-01-01T00:00:00",
  "created_by": "string",
  "updated_by": "string", 
  "is_deleted": false
}
```

### RevisionInfoResponse

版本信息響應模型。

```python
{
  "uid": "string",
  "resource_id": "string",
  "revision_id": "string", 
  "parent_revision_id": "string",
  "schema_version": "string",
  "data_hash": "string",
  "status": "string"
}
```

## 錯誤響應

AutoCRUD 使用標準 HTTP 狀態碼：

- `200 OK`: 成功
- `400 Bad Request`: 一般錯誤
- `404 Not Found`: 資源不存在
- `422 Unprocessable Entity`: 數據驗證錯誤

錯誤響應格式：
```json
{
  "detail": "錯誤描述"
}
```

## 使用示例

### 基本使用

```python
from autocrud.crud.core import AutoCRUD, CreateRouteTemplate
from pydantic import BaseModel

class User(BaseModel):
    name: str
    email: str

crud = AutoCRUD()
crud.add_route_template(CreateRouteTemplate())
crud.add_model(User)

# 應用到 FastAPI
from fastapi import FastAPI, APIRouter
app = FastAPI()
router = APIRouter()
crud.apply(router)
app.include_router(router)
```

### 自定義依賴

```python
from fastapi import Depends, Header

def get_user(authorization: str = Header(None)):
    # 自定義用戶認證邏輯
    return extract_user_from_token(authorization)

deps = DependencyProvider(get_user=get_user)
template = CreateRouteTemplate(dependency_provider=deps)
```

### 多類型支持

```python
from typing import TypedDict
from dataclasses import dataclass
import msgspec

class Config(TypedDict):
    key: str
    value: str

@dataclass
class Log:
    message: str
    level: str

class Event(msgspec.Struct):
    type: str
    data: bytes

# 註冊所有類型
crud.add_model(Config)  # /config
crud.add_model(Log)     # /log  
crud.add_model(Event)   # /event
```
