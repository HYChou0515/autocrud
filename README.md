# AutoCRUD

自動化 CRUD 系統，解決重複性 CRUD 操作的煩人問題。

## 目標

### 問題
CRUD 操作幾乎都長一樣，每次都要重複寫相同的代碼，很煩人。希望能有一個系統性的解決方案。

### 解決方案
建立一個自動化系統，輸入資料模型，自動產生完整的 CRUD API。

## 核心功能

### 1. 支援多種輸入格式
- `dataclasses` - Python 標準資料類
- `pydantic` - 資料驗證和序列化
- `typeddict` - 類型化字典

### 2. 自動產生 FastAPI CRUD 接口
- `GET /{resource}/{id}` - 取得單個資源
- `POST /{resource}` - 建立資源（自動產生 ID）
- `PUT /{resource}/{id}` - 更新資源
- `DELETE /{resource}/{id}` - 刪除資源

### 3. 靈活的儲存後端
支援簡單的 key-value 儲存，不一定要 SQL：
- **Memory** - 純內存儲存（快速、測試用、重啟後資料消失）
- **Disk** - 文件系統儲存（持久化、本地儲存）
- **S3** - 雲端對象儲存（未來實現）

### 4. 多種序列化格式支援
支援各種序列化方法，可根據需求選擇最適合的格式：
- **msgpack** - 高效二進制格式，體積小速度快
- **json** - 標準文本格式，易讀易調試
- **pickle** - Python 原生格式，支援複雜對象
- **其他** - 可擴展支援更多自訂格式

## 預期使用方式

```python
from dataclasses import dataclass
from autocrud import AutoCRUD, MemoryStorage, DiskStorage

@dataclass
class User:
    name: str
    email: str
    age: int

# 純內存儲存（演示用）
crud_memory = AutoCRUD(
    model=User,
    storage=MemoryStorage(),
    resource_name="users"
)

# 持久化磁碟儲存
crud_disk = AutoCRUD(
    model=User,
    storage=DiskStorage("./data"),
    resource_name="users"
)

# 產生 FastAPI 應用
app = crud_disk.create_fastapi_app(title="使用者管理 API")
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

### 安裝dependency
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