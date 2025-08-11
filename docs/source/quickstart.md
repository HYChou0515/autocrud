# 快速開始

歡迎使用 AutoCRUD！這個指南將幫助您在幾分鐘內創建一個功能完整的 CRUD API。

## 安裝

```bash
pip install autocrud
# 或使用 uv
uv add autocrud
```

## 5 分鐘快速開始

### 第 1 步：定義數據模型

AutoCRUD 支持多種 Python 數據類型。選擇最適合您需求的：

```python
from dataclasses import dataclass
from typing import Optional, TypedDict
from pydantic import BaseModel
import msgspec

# 選項 1: TypedDict - 輕量級，適合簡單場景
class TypedDictUser(TypedDict):
    name: str
    email: str
    age: Optional[int]

# 選項 2: Pydantic - 強大的數據驗證
class PydanticUser(BaseModel):
    name: str
    email: str
    age: Optional[int] = None

# 選項 3: dataclass - Python 原生，平衡性能和功能
@dataclass
class DataclassUser:
    name: str
    email: str
    age: Optional[int] = None

# 選項 4: msgspec - 高性能序列化
class MsgspecUser(msgspec.Struct):
    name: str
    email: str
    age: Optional[int] = None
```

### 第 2 步：創建 AutoCRUD 實例

```python
from autocrud.crud.core import (
    AutoCRUD,
    CreateRouteTemplate,
    ReadRouteTemplate,
    UpdateRouteTemplate,
    DeleteRouteTemplate,
    ListRouteTemplate,
)

# 創建 AutoCRUD 實例
crud = AutoCRUD(model_naming="kebab")  # 使用 kebab-case 命名

# 添加所有 CRUD 操作
crud.add_route_template(CreateRouteTemplate())
crud.add_route_template(ReadRouteTemplate())
crud.add_route_template(UpdateRouteTemplate())
crud.add_route_template(DeleteRouteTemplate())
crud.add_route_template(ListRouteTemplate())
```

### 第 3 步：註冊數據模型

```python
# 就這麼簡單！
crud.add_model(PydanticUser)  # 自動生成 /pydantic-user 端點
```

### 第 4 步：集成到 FastAPI

```python
from fastapi import FastAPI, APIRouter

app = FastAPI(title="My CRUD API")
router = APIRouter()

# 應用所有生成的路由
crud.apply(router)
app.include_router(router)
```

### 完整示例

```python
from dataclasses import dataclass
from typing import Optional
from pydantic import BaseModel
from fastapi import FastAPI, APIRouter

from autocrud.crud.core import (
    AutoCRUD,
    CreateRouteTemplate,
    ReadRouteTemplate,
    UpdateRouteTemplate,
    DeleteRouteTemplate,
    ListRouteTemplate,
)

# 定義數據模型
class User(BaseModel):
    name: str
    email: str
    age: Optional[int] = None

# 創建 AutoCRUD
crud = AutoCRUD(model_naming="kebab")
crud.add_route_template(CreateRouteTemplate())
crud.add_route_template(ReadRouteTemplate())
crud.add_route_template(UpdateRouteTemplate())
crud.add_route_template(DeleteRouteTemplate())
crud.add_route_template(ListRouteTemplate())

# 註冊模型
crud.add_model(User)

# 創建 FastAPI 應用
app = FastAPI(title="User Management API")
router = APIRouter()
crud.apply(router)
app.include_router(router)

# 運行: uvicorn main:app --reload
```

## 生成的 API 端點

註冊 `User` 模型後，AutoCRUD 會自動生成以下端點：

| 方法 | 端點 | 描述 |
|------|------|------|
| POST | `/user` | 創建新用戶 |
| GET | `/user/{id}` | 獲取用戶詳情 |
| PUT | `/user/{id}` | 更新用戶 |
| DELETE | `/user/{id}` | 刪除用戶 |
| GET | `/user` | 列出所有用戶 |

## 測試 API

啟動服務器後，訪問 `http://localhost:8000/docs` 查看自動生成的 API 文檔。

### 創建用戶
```bash
curl -X POST "http://localhost:8000/user" \
  -H "Content-Type: application/json" \
  -d '{"name": "John Doe", "email": "john@example.com", "age": 30}'
```

### 獲取用戶
```bash
curl "http://localhost:8000/user/USER_ID"
```

### 列出所有用戶
```bash
curl "http://localhost:8000/user"
```

## 下一步

- 了解更多 [配置選項](user_guide.md#配置)
- 查看 [完整示例](examples.md)
- 瀏覽 [API 參考](api_reference.md)

恭喜！您已經成功創建了第一個 AutoCRUD API。🎉
