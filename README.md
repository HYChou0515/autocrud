# AutoCRUD

自動化 CRUD 系統，解決重複性 CRUD 操作的煩人問題。

## 目標

### 問題
CRUD 操作幾乎都長一樣，每次都要重複寫相同的代碼，很煩人。希望能有一個系統性的解決方案。

### 解決方案
創建一個自動化系統，輸入數據模型，自動生成完整的 CRUD API。

## 核心功能

### 1. 支援多種輸入格式
- `dataclasses` - Python 標準數據類
- `pydantic` - 數據驗證和序列化
- `typeddict` - 類型化字典

### 2. 自動生成 FastAPI CRUD 接口
- `GET /{resource}/{id}` - 獲取單個資源
- `POST /{resource}` - 創建資源（自動生成 ID）
- `PUT /{resource}/{id}` - 更新資源
- `DELETE /{resource}/{id}` - 刪除資源

### 3. 靈活的存儲後端
支援簡單的 key-value 存儲，不一定要 SQL：
- **Memory** - 純內存存儲（快速、測試用、重啟後數據消失）
- **Disk** - 文件系統存儲（持久化、本地存儲）
- **S3** - 雲端對象存儲（未來實現）

### 4. 多種序列化格式支援
支援各種序列化方法，可根據需求選擇最適合的格式：
- **msgpack** - 高效二進制格式，體積小速度快
- **json** - 標準文本格式，易讀易調試
- **pickle** - Python 原生格式，支援複雜對象
- **其他** - 可擴展支援更多自定義格式

## 預期使用方式

```python
from dataclasses import dataclass
from autocrud import AutoCRUD, MemoryStorage, DiskStorage

@dataclass
class User:
    name: str
    email: str
    age: int

# 純內存存儲（演示用）
crud_memory = AutoCRUD(
    model=User,
    storage=MemoryStorage(),
    resource_name="users"
)

# 持久化磁碟存儲
crud_disk = AutoCRUD(
    model=User,
    storage=DiskStorage("./data"),
    resource_name="users"
)

# 生成 FastAPI 應用
app = crud_disk.create_fastapi_app(title="用戶管理 API")
```

## 開發計劃

### 第1步：數據類型轉換器 ✅
- ✅ 創建統一的數據類型轉換器
- ✅ 支援 dataclasses, pydantic, typeddict 轉換
- ✅ 實現多種序列化格式：msgpack, json, pickle

### 第2步：存儲抽象層 ✅
- ✅ 定義通用的 key-value 存儲接口
- ✅ 實現 Memory 存儲後端（純內存、演示用）
- ✅ 實現 Disk 存儲後端（文件系統持久化）
- 🔄 實現 S3 存儲後端
- ✅ 支援基本操作：get, set, delete, exists
- ✅ 可配置序列化格式

### 第3步：FastAPI 自動生成 ✅
- ✅ 基於數據模型自動生成 CRUD 路由
- ✅ 自動 ID 生成和管理
- ✅ 統一錯誤處理和響應格式
- ✅ 自動生成 Pydantic 請求/響應模型
- ✅ 支援 OpenAPI 文檔自動生成
- ✅ 健康檢查端點

## 快速開始

### 安裝依賴
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

# 創建 CRUD 系統
storage = DiskStorage("./data")
crud = AutoCRUD(model=User, storage=storage, resource_name="users")

# 生成 FastAPI 應用
app = crud.create_fastapi_app(title="用戶管理 API")

# 啟動服務器
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### API 端點
- `POST /api/v1/users` - 創建用戶
- `GET /api/v1/users/{id}` - 獲取用戶
- `PUT /api/v1/users/{id}` - 更新用戶  
- `DELETE /api/v1/users/{id}` - 刪除用戶
- `GET /api/v1/users` - 列出所有用戶
- `GET /health` - 健康檢查

### 自動生成文檔
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 技術棧

- **FastAPI** - Web 框架
- **Pydantic** - 數據驗證
- **dependency-injector** - 依賴注入
- **msgpack** - 高效序列化
- **json** - 標準序列化
- **pickle** - Python 原生序列化