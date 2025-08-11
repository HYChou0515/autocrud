# 🚀 快速開始

AutoCRUD 讓您在 5 分鐘內就能創建一個功能完整的 CRUD API。本指南將帶您快速上手。

## 前置要求

- Python 3.8+
- 基本的 Python 和 FastAPI 知識

## 安裝

::::{tab-set}

:::{tab-item} pip
```bash
pip install autocrud
```
:::

:::{tab-item} uv
```bash
uv add autocrud
```
:::

:::{tab-item} poetry
```bash
poetry add autocrud
```
:::

::::

## 第一個 API

讓我們從最簡單的示例開始：

```python
# main.py
from pydantic import BaseModel
from fastapi import FastAPI, APIRouter
from autocrud.crud.core import (
    AutoCRUD, CreateRouteTemplate, ReadRouteTemplate,
    UpdateRouteTemplate, DeleteRouteTemplate, ListRouteTemplate
)

# 1. 定義數據模型
class User(BaseModel):
    name: str
    email: str
    age: int = None

# 2. 創建 AutoCRUD 實例
crud = AutoCRUD(model_naming="kebab")

# 3. 添加 CRUD 操作
crud.add_route_template(CreateRouteTemplate())
crud.add_route_template(ReadRouteTemplate())
crud.add_route_template(UpdateRouteTemplate())
crud.add_route_template(DeleteRouteTemplate())
crud.add_route_template(ListRouteTemplate())

# 4. 註冊模型
crud.add_model(User)

# 5. 集成到 FastAPI
app = FastAPI(title="我的第一個 CRUD API")
router = APIRouter()
crud.apply(router)
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

## 運行應用

```bash
# 方法 1: 直接運行
python main.py

# 方法 2: 使用 uvicorn
uvicorn main:app --reload

# 方法 3: 指定端口
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## 測試 API

應用啟動後，您將擁有以下端點：

### 1. 創建用戶
```bash
curl -X POST "http://localhost:8000/user" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "張三",
       "email": "zhangsan@example.com",
       "age": 25
     }'
```

### 2. 獲取用戶列表
```bash
curl http://localhost:8000/user
```

### 3. 獲取特定用戶
```bash
curl http://localhost:8000/user/{user_id}
```

### 4. 更新用戶
```bash
curl -X PUT "http://localhost:8000/user/{user_id}" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "張三",
       "email": "zhangsan.new@example.com",
       "age": 26
     }'
```

### 5. 刪除用戶
```bash
curl -X DELETE http://localhost:8000/user/{user_id}
```

## 查看 API 文檔

FastAPI 自動生成交互式 API 文檔：

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 多數據類型示例

AutoCRUD 支持多種 Python 數據類型：

```python
from typing import TypedDict, Optional
from dataclasses import dataclass
from pydantic import BaseModel
import msgspec

# TypedDict - 輕量級
class Product(TypedDict):
    name: str
    price: float
    in_stock: bool

# Pydantic - 強驗證
class User(BaseModel):
    username: str
    email: str
    age: Optional[int] = None

# dataclass - 原生支持
@dataclass
class Order:
    customer_id: str
    items: list
    total: float = 0.0

# msgspec - 高性能
class Event(msgspec.Struct):
    type: str
    data: dict
    timestamp: float

# 創建統一的 CRUD API
crud = AutoCRUD(model_naming="kebab")

# 添加所有路由模板
for template in [CreateRouteTemplate(), ReadRouteTemplate(), 
                UpdateRouteTemplate(), DeleteRouteTemplate(), 
                ListRouteTemplate()]:
    crud.add_route_template(template)

# 註冊所有模型
crud.add_model(Product)   # /product/*
crud.add_model(User)      # /user/*
crud.add_model(Order)     # /order/*
crud.add_model(Event)     # /event/*

# 應用到 FastAPI
app = FastAPI(title="多類型 CRUD API")
router = APIRouter()
crud.apply(router)
app.include_router(router)
```

## 自定義配置

### 命名約定

```python
# kebab-case (推薦)
crud = AutoCRUD(model_naming="kebab")
# UserProfile -> /user-profile

# snake_case
crud = AutoCRUD(model_naming="snake")
# UserProfile -> /user_profile

# 自定義命名
def custom_naming(model_type):
    return f"api_{model_type.__name__.lower()}"

crud = AutoCRUD(model_naming=custom_naming)
```

### 選擇性功能

```python
# 只讀 API
crud = AutoCRUD()
crud.add_route_template(ReadRouteTemplate())
crud.add_route_template(ListRouteTemplate())

# 基本 CRUD (無列表)
crud = AutoCRUD()
crud.add_route_template(CreateRouteTemplate())
crud.add_route_template(ReadRouteTemplate())
crud.add_route_template(UpdateRouteTemplate())
crud.add_route_template(DeleteRouteTemplate())
```

## 錯誤處理

AutoCRUD 自動處理常見錯誤：

```python
# 自動返回適當的 HTTP 狀態碼
# 404 - 資源不存在
# 422 - 驗證錯誤
# 400 - 請求格式錯誤
# 500 - 服務器內部錯誤
```

## 下一步

現在您已經有了一個基本的 CRUD API！接下來可以：

1. 📖 閱讀 [用戶指南](user_guide.md) 了解高級功能
2. 💡 查看 [示例集合](examples.md) 獲取更多靈感
3. 🔧 探索 [API 參考](api_reference.md) 了解所有配置選項
4. 🛠️ 學習 [安裝指南](installation.md) 進行生產部署

## 常見問題

### Q: 如何添加自定義驗證？

使用 Pydantic 的驗證功能：

```python
from pydantic import BaseModel, validator

class User(BaseModel):
    name: str
    email: str
    age: int

    @validator('age')
    def validate_age(cls, v):
        if v < 0 or v > 150:
            raise ValueError('年齡必須在 0-150 之間')
        return v
```

### Q: 如何自定義響應格式？

```python
from autocrud.crud.core import ReadRouteTemplate

class CustomReadTemplate(ReadRouteTemplate):
    def get_response_model(self, model_type):
        # 自定義響應模型
        pass
```

### Q: 如何添加認證？

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

def verify_token(token: str = Depends(security)):
    # 驗證邏輯
    if not token:
        raise HTTPException(status_code=401)
    return token

# 在應用中使用
app.include_router(router, dependencies=[Depends(verify_token)])
```

### Q: 支持哪些數據庫？

AutoCRUD 設計為存儲無關。默認使用內存存儲，但可以輕松擴展到：
- PostgreSQL
- MySQL
- MongoDB
- Redis
- 文件系統

更多信息請參見 [用戶指南](user_guide.md#存儲後端)。
