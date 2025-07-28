# AutoCRUD

**🚀 從資料模型到完整 REST API**

AutoCRUD 是一個 Python 函式庫，能夠自動從資料模型生成完整的、生產就緒的 REST API。核心技術價值在於自動化 API 路由生成，而不只是簡單的程式化 CRUD 操作。

## 🎯 核心價值

**AutoCRUD 自動化傳統 FastAPI CRUD 開發中的重複工作：**

```python
from autocrud import AutoCRUD
from dataclasses import dataclass

@dataclass
class User:
    id: str
    name: str
    email: str

# 簡單設定
crud = AutoCRUD()
crud.register_model(User)  # 完整 REST API 自動生成

# 創建生產就緒的 API 應用
app = crud.create_fastapi_app(title="我的 API")
# 執行: uvicorn main:app --reload
# 訪問: http://localhost:8000/docs
```

**🎯 主要功能：**
- **完整的 REST API**: `GET /users`, `POST /users`, `PUT /users/{id}`, `DELETE /users/{id}`, `GET /users/count`
- **高級查詢功能**: `GET /users?page=1&page_size=10&sort_by=name&sort_order=asc`
- **時間範圍篩選**: `GET /users?created_time_start=2024-01-01&created_time_end=2024-12-31`
- **自動 Swagger 文檔**: 交互式 API 文檔 (訪問 `/docs`)
- **資料驗證**: 自動請求/響應驗證，錯誤處理
- **開箱即用**: 無需額外設置

## 🌟 為什麼選擇 AutoCRUD？

### 🎯 自動 API 生成優勢

手寫完整的 FastAPI CRUD 路由需要大量樣板代碼：

```python
# 傳統方式 - 繁瑣且容易出錯
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List

# 每個模型都需要這樣的重複代碼...
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
```

**用 AutoCRUD，這些全部自動完成！**

- � **自動 API 路由產生**: 從資料模型直接產生生產級 REST API
- 🔄 **企業級多模型支援**: 一次管理多個業務實體的完整 API 生態系統
- 📦 **全格式支援**: Pydantic、Dataclass、TypedDict 無縫整合
- 💾 **生產級持久化**: 從原型到生產環境的儲存解決方案
- 🔧 **企業級序列化**: JSON、Pickle、MessagePack 多重選擇
- ⚙️ **高度可客製化**: 資源命名、ID 策略、路由配置完全可控
- ⚡ **進階查詢 API**: 複雜查詢、排序、分頁、時間範圍篩選
- 📖 **零維護文檔**: 完整 OpenAPI/Swagger 文檔自動同步
- 💻 **程式化後備**: 當 API 不夠用時，完整的程式化 CRUD 控制

## 🎨 企業級多模型範例

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

# 立即可用的企業級 API 平台
app = crud.create_fastapi_app(
    title="電商 API 平台",
    description="基於 AutoCRUD 的企業級電商 API",
    version="1.0.0"
)

# 執行: uvicorn main:app --reload
# 訪問: http://localhost:8000/docs
```

## 🚀 生產環境部署

```python
# main.py - 生產就緒
from autocrud import AutoCRUD
from autocrud.storage import DiskStorage
import os

# 生產環境配置
storage = DiskStorage(storage_dir=os.getenv("DATA_DIR", "./production_data"))
crud = AutoCRUD(storage_factory=lambda name: storage)

# 註冊你的業務模型
crud.register_model(User)
crud.register_model(Product)
crud.register_model(Order)

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

## 開發計劃

### 第1步：資料類型轉換器 ✅
- ✅ 建立統一的資料類型轉換器
- ✅ 支援 dataclasses, pydantic, typeddict 轉換
- ✅ 實現多種序列化格式：msgpack, json, pickle

### 第2步：儲存抽象層 ✅
- ✅ 定義通用的 key-value 儲存接口
- ✅ 實現 Memory 儲存後端（純內存、演示用）
- ✅ 實現 Disk 儲存後端（文件系統持久化）
- 🔄 實現 S3 儲存後端
- ✅ 支援基本操作：get, set, delete, exists
- ✅ 可設定序列化格式

### 第3步：FastAPI 自動產生 ✅
- ✅ 基於資料模型自動產生 CRUD routing
- ✅ 自動 ID 產生和管理
- ✅ 統一錯誤處理和響應格式
- ✅ 自動產生 Pydantic 請求/響應模型
- ✅ 支援 OpenAPI 文件自動產生
- ✅ 健康檢查端點

## 快速開始

### 安裝依賴套件
```bash
pip install fastapi uvicorn
```

### 基本使用
```python
from dataclasses import dataclass
from autocrud import AutoCRUD, DiskStorage

@dataclass
class User:
    name: str
    email: str
    age: int

# 建立 CRUD 系統
storage = DiskStorage("./data")
crud = AutoCRUD(model=User, storage=storage, resource_name="users")

# 產生 FastAPI 應用
app = crud.create_fastapi_app(title="使用者管理 API")

# 啟動服務器
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### API 端點
- `POST /api/v1/users` - 建立使用者
- `GET /api/v1/users/{id}` - 取得使用者
- `PUT /api/v1/users/{id}` - 更新使用者  
- `DELETE /api/v1/users/{id}` - 刪除使用者
- `GET /api/v1/users` - 列出所有使用者
- `GET /health` - 健康檢查

### 自動產生文件
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 技術棧

- **FastAPI** - Web 框架
- **Pydantic** - 資料驗證
- **dependency-injector** - dependency注入
- **msgpack** - 高效序列化
- **json** - 標準序列化
- **pickle** - Python 原生序列化