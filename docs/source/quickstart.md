# 快速入門

## 5 分鐘開始使用 AutoCRUD

### 第一步：定義你的數據模型

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class User:
    name: str
    email: str
    age: Optional[int] = None
```

### 第二步：創建 CRUD 系統

```python
from autocrud import AutoCRUD
from autocrud.storage import MemoryStorage

# 創建存儲後端
storage = MemoryStorage()

# 創建 CRUD 實例
user_crud = AutoCRUD(model=User, storage=storage)
```

### 第三步：執行 CRUD 操作

```python
# 創建用戶
user_data = {"name": "Alice", "email": "alice@example.com", "age": 30}
created_user = user_crud.create(user_data)
print(f"創建的用戶: {created_user}")

# 獲取用戶
user_id = created_user["id"]
retrieved_user = user_crud.get(user_id)
print(f"獲取的用戶: {retrieved_user}")

# 更新用戶
updated_user = user_crud.update(user_id, {"age": 31})
print(f"更新的用戶: {updated_user}")

# 列出所有用戶
all_users = user_crud.list_all()
print(f"所有用戶: {all_users}")

# 刪除用戶
deleted = user_crud.delete(user_id)
print(f"刪除成功: {deleted}")
```

### 第四步：生成 FastAPI 應用

```python
# 創建 FastAPI 應用
app = user_crud.create_fastapi_app(
    title="User API",
    description="用戶管理 API"
)

# 運行應用 (需要安裝 uvicorn)
# uvicorn main:app --reload
```

### 多模型支持

```python
from autocrud import MultiModelAutoCRUD

@dataclass
class Product:
    name: str
    price: float
    category: str

# 創建多模型 CRUD 系統
multi_crud = MultiModelAutoCRUD(storage)

# 註冊多個模型
multi_crud.register_model(User)  # URL: /api/v1/users
multi_crud.register_model(Product, use_plural=False)  # URL: /api/v1/product

# 創建統一的 FastAPI 應用
app = multi_crud.create_fastapi_app(
    title="多模型 API",
    description="支持多個數據模型的 CRUD API"
)
```

### URL 形式自定義

```python
# 默認複數形式
multi_crud.register_model(User)  # -> /api/v1/users

# 指定單數形式
multi_crud.register_model(Product, use_plural=False)  # -> /api/v1/product

# 自定義資源名稱
multi_crud.register_model(Company, resource_name=\"organizations\")  # -> /api/v1/organizations
```

## 下一步

- 閱讀 [安裝指南](installation.md) 了解詳細的安裝說明
- 查看 [用戶指南](user_guide.md) 學習更多高級功能
- 瀏覽 [API 參考](api_reference.md) 了解完整的 API 文檔
- 查看 [示例](examples.md) 獲取更多使用案例
