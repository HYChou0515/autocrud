# 📖 用戶指南

深入了解 AutoCRUD 的完整功能。

## 🏗️ 核心概念

### 架構組件

```
AutoCRUD
├── 模型註冊 (add_model)
├── 路由生成 (apply) 
├── 存儲管理 (Storage)
├── 序列化 (msgspec)
└── 版本控制 (Versioning)
```

### 基本流程

1. **註冊模型**: `crud.add_model(Model)`
2. **應用到app**: `crud.apply(app)`
3. **自動生成**: 完整 CRUD API
4. **版本管理**: 自動追蹤變更

## 📊 數據類型支持

### msgspec.Struct (推薦)

```python
from msgspec import Struct
from datetime import datetime

class User(Struct):
    name: str
    email: str  
    age: int
    created_at: datetime = datetime.now()

crud = AutoCRUD()
crud.add_model(User)
```
**優點**: 極快序列化、類型安全、內存效率

### dataclass

```python
from dataclasses import dataclass, field
from typing import List

@dataclass
class Product:
    name: str
    price: float
    tags: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.name.strip():
            raise ValueError('名稱不能為空')
        if self.price <= 0:
            raise ValueError('價格必須大於0')

crud = AutoCRUD()
crud.add_model(Product)
```
**優點**: Python 原生、簡潔、驗證靈活

```python
from dataclasses import dataclass, field
from typing import List

@dataclass
class Task:
    title: str
    completed: bool = False
    tags: List[str] = field(default_factory=list)

crud = AutoCRUD()
crud.add_model(Task)
```
**優點**: Python 原生、簡潔

### TypedDict

```python
from typing import TypedDict, Optional

class Order(TypedDict):
    customer: str
    total: float
    status: str
    notes: Optional[str]

crud = AutoCRUD()
crud.add_model(Order)
```
**優點**: 輕量、向後兼容

## ⚙️ 配置選項

### AutoCRUD 初始化

```python
crud = AutoCRUD(
    model_naming="kebab"  # 命名風格: kebab/snake/camel
)
```

### 命名約定

```python
# kebab-case (推薦)
crud = AutoCRUD(model_naming="kebab")  # /todo-item

# snake_case  
crud = AutoCRUD(model_naming="snake")  # /todo_item

# camelCase
crud = AutoCRUD(model_naming="camel")  # /todoItem
```

## 💾 存儲管理

### 內存存儲 (默認)

```python
# 默認內存存儲
crud = AutoCRUD()
crud.add_model(User)
```
- ✅ 極快速度
- ❌ 重啟丟失

### 磁碟存儲

```python
from autocrud.crud.core import DiskStorageFactory

storage = DiskStorageFactory("./data")
crud.add_model(User, storage_factory=storage)
```
- ✅ 持久化
- ✅ 可備份

### 混合存儲

```python
# 重要數據用磁碟
disk_storage = DiskStorageFactory("./data")
crud.add_model(User, storage_factory=disk_storage)

# 臨時數據用內存
from autocrud.crud.core import MemoryStorageFactory
memory_storage = MemoryStorageFactory()
crud.add_model(Session, storage_factory=memory_storage)
```

## 🔄 版本控制

### 自動版本管理

```python
# 創建資源
resp = client.post("/user", json={"name": "Alice", "age": 25})
user_id = resp.json()["resource_id"]

# 更新會創建新版本
client.patch(f"/user/{user_id}", json=[
    {"op": "replace", "path": "/age", "value": 26}
])

# 查看版本歷史
revisions = client.get(f"/user/{user_id}/revisions").json()
```

### 版本切換

```python
# 切換到舊版本
old_revision = revisions[0]['revision_id']
client.post(f"/user/{user_id}/switch/{old_revision}")
```

## 🗑️ 軟刪除

```python
# 軟刪除
client.delete(f"/user/{user_id}")

# 查詢已刪除
deleted = client.get("/user/meta", params={"is_deleted": True})

# 恢復
client.post(f"/user/{user_id}/restore")
```

## 📝 JSON Patch

### 基本操作

```python
# 替換值
{"op": "replace", "path": "/name", "value": "新名稱"}

# 添加到數組末尾
{"op": "add", "path": "/tags/-", "value": "新標籤"}

# 移除
{"op": "remove", "path": "/tags/0"}

# 移動
{"op": "move", "from": "/tags/0", "path": "/tags/2"}
```

### 複雜更新

```python
client.patch(f"/product/{id}", json=[
    {"op": "replace", "path": "/quantity", "value": 20},
    {"op": "add", "path": "/tags/-", "value": "sale"},
    {"op": "remove", "path": "/tags/0"}
])
```

## 🔄 數據遷移

### 實現遷移

```python
from autocrud.resource_manager.basic import IMigration

class UserMigration(IMigration):
    @property
    def schema_version(self):
        return "2.0"
    
    def migrate(self, data, schema_version):
        # 遷移邏輯
        old_user = deserialize_old(data)
        return UserV2(
            name=old_user.full_name,
            age=calculate_age(old_user.birth_year)
        )
```

### 應用遷移

```python
crud.add_model(
    UserV2,
    storage_factory=storage,
    migration=UserMigration()
)
```

## 💾 備份還原

### 完整備份

```python
# 備份
with open("backup.dump", "wb") as f:
    crud.dump(f)

# 還原
with open("backup.dump", "rb") as f:
    crud.load(f)
```

## 🔍 查詢功能

### 時間範圍

```python
resp = client.get("/user/full", params={
    "created_time_start": "2024-01-01T00:00:00",
    "created_time_end": "2024-12-31T23:59:59"
})
```

### 狀態過濾

```python
# 已刪除資源
deleted = client.get("/user/meta", params={"is_deleted": True})

# 活躍資源
active = client.get("/user/meta", params={"is_deleted": False})
```

## 🔧 自定義路由

```python
from autocrud.crud.core import CreateRouteTemplate

class CustomCreateRoute(CreateRouteTemplate):
    def get_route_info(self):
        info = super().get_route_info()
        info.summary = "自定義創建"
        info.tags = ["Custom"]
        return info

crud = AutoCRUD()
crud.add_route_template(CustomCreateRoute())
```

## 🚀 最佳實踐

### 生產環境

```python
import os
from autocrud.crud.core import DiskStorageFactory

# 環境配置
data_dir = os.getenv("DATA_DIR", "./data")
storage = DiskStorageFactory(data_dir)

crud = AutoCRUD(model_naming="kebab")
crud.add_model(User, storage_factory=storage)

app = FastAPI(title="Production API")
crud.apply(app)
```

### 錯誤處理

```python
try:
    resp = client.post("/user", json=data)
    resp.raise_for_status()
except Exception as e:
    print(f"操作失敗: {e}")
```

### 批量操作

```python
# 批量創建
for data in user_list:
    client.post("/user", json=data)

# 批量查詢
all_users = client.get("/user/data").json()
```

這份指南涵蓋了 AutoCRUD 的所有核心功能，幫助您在實際項目中有效使用。