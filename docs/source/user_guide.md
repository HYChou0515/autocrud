# 用戶指南

深入了解 AutoCRUD 的功能和最佳實踐。

## 數據模型支持

AutoCRUD 支持多種 Python 數據模型格式：

### Dataclass 模型

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class User:
    name: str
    email: str
    age: Optional[int] = None
    is_active: bool = True
```

### Pydantic 模型

```python
from pydantic import BaseModel, EmailStr
from typing import Optional

class User(BaseModel):
    name: str
    email: EmailStr
    age: Optional[int] = None
    is_active: bool = True
```

### TypedDict 模型

```python
from typing import TypedDict, Optional

class User(TypedDict):
    name: str
    email: str
    age: Optional[int]
    is_active: bool
```

## 存儲後端

### 記憶體存儲 (MemoryStorage)

適用於開發、測試或臨時數據：

```python
from autocrud.storage import MemoryStorage

storage = MemoryStorage()
```

特點：
- 快速存取
- 程序結束後數據消失
- 適合測試和原型開發

### 磁碟存儲 (DiskStorage)

適用於持久化數據：

```python
from autocrud.storage import DiskStorage

storage = DiskStorage(
    storage_dir="./data",
    serializer_type="json"  # 或 "pickle", "msgpack"
)
```

特點：
- 數據持久化
- 支持多種序列化格式
- 自動創建存儲目錄

## 序列化格式

### JSON (推薦)

```python
storage = DiskStorage(serializer_type="json")
```

- 人類可讀
- 跨語言兼容
- 較小的檔案大小

### Pickle

```python
storage = DiskStorage(serializer_type="pickle")
```

- Python 原生支持
- 支持任意 Python 對象
- 僅限 Python 使用

### MessagePack

```python
storage = DiskStorage(serializer_type="msgpack")
```

- 二進制格式
- 高效壓縮
- 跨語言支持

## 多模型管理

### 基本用法

```python
from autocrud import MultiModelAutoCRUD
from autocrud.storage import MemoryStorage

storage = MemoryStorage()
multi_crud = MultiModelAutoCRUD(storage)

# 註冊多個模型
multi_crud.register_model(User)
multi_crud.register_model(Product)
multi_crud.register_model(Order)
```

### 資源名稱自定義

```python
# 自動生成複數形式 (默認)
multi_crud.register_model(User)  # -> users

# 指定單數形式
multi_crud.register_model(Product, use_plural=False)  # -> product

# 完全自定義名稱
multi_crud.register_model(Company, resource_name="organizations")  # -> organizations
```

### 跨模型操作

```python
# 直接在多模型系統上執行操作
user = multi_crud.create("users", {"name": "Alice", "email": "alice@example.com"})
product = multi_crud.create("products", {"name": "Laptop", "price": 999.99})

# 獲取特定模型的 CRUD 實例
user_crud = multi_crud.get_crud("users")
all_users = user_crud.list_all()
```

## FastAPI 集成

### 單模型 API

```python
from autocrud import AutoCRUD

user_crud = AutoCRUD(model=User, storage=storage)
app = user_crud.create_fastapi_app(
    title="User API",
    description="用戶管理 API",
    version="1.0.0"
)
```

### 多模型 API

```python
from autocrud import MultiModelAutoCRUD

multi_crud = MultiModelAutoCRUD(storage)
multi_crud.register_model(User)
multi_crud.register_model(Product)

app = multi_crud.create_fastapi_app(
    title="多模型 API",
    description="統一的 CRUD API",
    prefix="/api/v1"
)
```

### 自定義路由前綴

```python
app = multi_crud.create_fastapi_app(
    prefix="/api/v2"  # 所有路由將以 /api/v2 開頭
)
```

## ID 生成器

### 默認 UUID 生成器

```python
# 使用默認的 UUID4 生成器
crud = AutoCRUD(model=User, storage=storage)
```

### 自定義 ID 生成器

```python
def custom_id_generator():
    import time
    return f"user_{int(time.time())}"

crud = AutoCRUD(
    model=User,
    storage=storage,
    id_generator=custom_id_generator
)
```

### 序列 ID 生成器

```python
def sequential_id_generator():
    if not hasattr(sequential_id_generator, 'counter'):
        sequential_id_generator.counter = 0
    sequential_id_generator.counter += 1
    return str(sequential_id_generator.counter)

crud = AutoCRUD(
    model=User,
    storage=storage,
    id_generator=sequential_id_generator
)
```

## 錯誤處理

### 常見異常

```python
from autocrud.exceptions import AutoCRUDError, ValidationError, StorageError

try:
    user = crud.create(invalid_data)
except ValidationError as e:
    print(f"數據驗證錯誤: {e}")
except StorageError as e:
    print(f"存儲錯誤: {e}")
except AutoCRUDError as e:
    print(f"通用錯誤: {e}")
```

### 數據驗證

```python
# Pydantic 模型會自動進行數據驗證
from pydantic import BaseModel, validator

class User(BaseModel):
    name: str
    age: int
    
    @validator('age')
    def validate_age(cls, v):
        if v < 0:
            raise ValueError('年齡不能為負數')
        return v
```

## 最佳實踐

### 1. 模型設計

```python
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime

@dataclass
class User:
    name: str
    email: str
    age: Optional[int] = None
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    tags: List[str] = field(default_factory=list)
```

### 2. 存儲選擇

- **開發/測試**: 使用 `MemoryStorage`
- **生產環境**: 使用 `DiskStorage` 配合適當的序列化格式
- **大量數據**: 考慮實現自定義存儲後端

### 3. API 設計

```python
# 為不同的資源使用合適的 URL 形式
multi_crud.register_model(User)  # RESTful: /users
multi_crud.register_model(Config, use_plural=False)  # Singleton: /config
multi_crud.register_model(Company, resource_name="organizations")  # Custom: /organizations
```

### 4. 錯誤處理

```python
from fastapi import HTTPException

def safe_create_user(data: dict):
    try:
        return user_crud.create(data)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except StorageError as e:
        raise HTTPException(status_code=500, detail="存儲錯誤")
```

## 性能考慮

### 記憶體使用

- `MemoryStorage` 將所有數據保存在記憶體中
- 對於大量數據，考慮使用 `DiskStorage`

### 序列化性能

- JSON: 平衡性能和可讀性
- Pickle: 最快，但僅限 Python
- MessagePack: 高效的二進制格式

### 併發訪問

目前的實現不是線程安全的。在高併發環境中：

1. 使用適當的鎖機制
2. 考慮使用數據庫後端
3. 實現自定義的線程安全存儲後端
