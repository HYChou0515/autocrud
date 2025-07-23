# 快速入門

## 5 分鐘開始使用 AutoCRUD

### 第一步：定義你的資料模型

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class User:
    name: str
    email: str
    age: Optional[int] = None
```

### 第二步：建立 CRUD 系統

```python
from autocrud import AutoCRUD
from autocrud.storage import MemoryStorage

# 建立儲存後端
storage = MemoryStorage()

# 建立 CRUD 實例
user_crud = AutoCRUD(model=User, storage=storage)
```

### 第三步：執行 CRUD 操作

```python
# 建立使用者
user_data = {"name": "Alice", "email": "alice@example.com", "age": 30}
created_user = user_crud.create(user_data)
print(f"建立的使用者: {created_user}")

# 取得使用者
user_id = created_user["id"]
retrieved_user = user_crud.get(user_id)
print(f"取得的使用者: {retrieved_user}")

# 更新使用者
updated_user = user_crud.update(user_id, {"age": 31})
print(f"更新的使用者: {updated_user}")

# 列出所有使用者
all_users = user_crud.list_all()
print(f"所有使用者: {all_users}")

# 刪除使用者
deleted = user_crud.delete(user_id)
print(f"刪除成功: {deleted}")
```

### 第四步：產生 FastAPI 應用

```python
# 建立 FastAPI 應用
app = user_crud.create_fastapi_app(
    title="User API",
    description="使用者管理 API"
)

# 執行應用 (需要安裝 uvicorn)
# uvicorn main:app --reload
```

### 多模型支援

```python
from autocrud import MultiModelAutoCRUD

@dataclass
class Product:
    name: str
    price: float
    category: str

# 建立多模型 CRUD 系統
multi_crud = MultiModelAutoCRUD(storage)

# 註冊多個模型
multi_crud.register_model(User)  # URL: /api/v1/users
multi_crud.register_model(Product, use_plural=False)  # URL: /api/v1/product

# 建立統一的 FastAPI 應用
app = multi_crud.create_fastapi_app(
    title="多模型 API",
    description="支援多個資料模型的 CRUD API"
)
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
