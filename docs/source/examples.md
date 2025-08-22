# 💡 使用案例

## 📁 可用範例

- `quick_start.py` - 基本 CRUD 操作
- `resource_crud.py` - 完整功能演示
- `schema_upgrade.py` - 數據遷移  
- `backup.py` - 備份與還原

## 🛠️ 完整功能演示

```python
from datetime import datetime
from fastapi import FastAPI
from fastapi.testclient import TestClient
from autocrud import AutoCRUD
from msgspec import Struct

class Product(Struct):
    name: str
    quantity: int
    price: int
    tags: list[str]

crud = AutoCRUD()
crud.add_model(Product)

app = FastAPI()
crud.apply(app)

def test():
    client = TestClient(app)

    print("=== 添加 3 個產品 ===")
    client.post("/product", json={
        "name": "Apple", "quantity": 10, "price": 100, "tags": ["fruit", "food"]
    })
    
    dt2 = datetime.now()
    client.post("/product", json={
        "name": "Banana", "quantity": 5, "price": 50, "tags": ["fruit", "food"]
    })
    
    dt3 = datetime.now()
    client.post("/product", json={
        "name": "Cherry", "quantity": 2, "price": 25, "tags": ["fruit", "food"]
    })

    print("=== 時間範圍查詢 ===")
    resp = client.get("/product/full", params={
        "created_time_end": dt3, 
        "created_time_start": dt2
    })
    print(f"在時間範圍內的產品: {len(resp.json())}")

    print("=== 獲取 Banana 元數據 ===")
    banana = client.get(f"/product/{resp.json()[0]['meta']['resource_id']}/meta")
    banana_resource_id = banana.json()["resource_id"]

    print("=== JSON Patch 更新 ===")
    resp = client.patch(f"/product/{banana_resource_id}", json=[
        {"op": "replace", "path": "/quantity", "value": 20},
        {"op": "add", "path": "/tags/-", "value": "snack"},
        {"op": "move", "from": "/tags/0", "path": "/tags/-"},
        {"op": "remove", "path": "/tags/0"},
    ])

    print("=== PUT 完整更新 ===")
    resp = client.put(f"/product/{banana_resource_id}", json={
        "name": "Banana", "quantity": 5, "price": 250, "tags": ["fruit", "food"]
    })

    print("=== 版本控制 - 切換回之前版本 ===")
    client.post(f"/product/{banana_resource_id}/switch/{banana.json()['current_revision_id']}")

    print("=== 軟刪除產品 ===")
    client.delete(f"/product/{banana_resource_id}")

    print("=== 查詢已刪除產品 ===")
    resp = client.get("/product/meta", params={"is_deleted": True})
    print(f"已刪除產品: {len(resp.json())}")

    print("=== 恢復產品 ===")
    client.post(f"/product/{banana_resource_id}/restore")
    resp = client.get(f"/product/{banana_resource_id}/data")
    print("產品已恢復")

if __name__ == "__main__":
    test()
```

## 🔄 數據遷移

```python
from autocrud import AutoCRUD
from autocrud.crud.core import DiskStorageFactory
from autocrud.resource_manager.basic import IMigration, MsgspecSerializer, Encoding
from msgspec import Struct, UnsetType
from typing import IO

# 舊版本模型
class UserV1(Struct):
    name: str
    income: float

# 新版本模型
class UserV2(Struct):
    name: str
    age: int

# 遷移實現
class Migration(IMigration):
    @property
    def schema_version(self):
        return "v1"

    def migrate(self, data: IO[bytes], schema_version: str | UnsetType):
        BeforeUser = UserV1
        s = MsgspecSerializer(encoding=Encoding.json, resource_type=BeforeUser)
        od = s.decode(data.read())
        
        # 遷移邏輯
        return UserV2(name=od.name, age=-1)

def test_migration():
    # 階段1: 創建舊格式數據
    crud_old = AutoCRUD()
    storage_factory = DiskStorageFactory("test_data")
    crud_old.add_model(UserV1, storage_factory=storage_factory)
    
    app_old = FastAPI()
    crud_old.apply(app_old)
    
    client = TestClient(app_old)
    client.post("/user-v1", json={"name": "John", "income": 100})
    
    # 階段2: 使用新模型和遷移
    crud_new = AutoCRUD()
    crud_new.add_model(UserV2, storage_factory=storage_factory, migration=Migration())
    
    app_new = FastAPI()
    crud_new.apply(app_new)
    
    client = TestClient(app_new)
    users = client.get("/user-v2/full").json()
    print(f"遷移後用戶: {users}")
```

## 💾 備份與還原

```python
import shutil
from autocrud import AutoCRUD
from autocrud.crud.core import DiskStorageFactory

def backup_demo():
    # 清理舊數據
    shutil.rmtree("backup_test", ignore_errors=True)
    
    def create_system():
        crud = AutoCRUD()
        storage_factory = DiskStorageFactory("backup_test")
        crud.add_model(User, storage_factory=storage_factory)
        
        app = FastAPI()
        crud.apply(app)
        return app, crud
    
    # 創建數據
    app, crud = create_system()
    client = TestClient(app)
    resp = client.post("/user", json={"name": "John", "age": 42})
    
    print("=== 備份 ===")
    with open("backup.dump", "wb") as f:
        crud.dump(f)
    
    print("=== 模擬災難 ===")
    shutil.rmtree("backup_test")
    
    print("=== 恢復 ===")
    app_restored, crud_restored = create_system()
    with open("backup.dump", "rb") as f:
        crud_restored.load(f)
    
    client_restored = TestClient(app_restored)
    restored_users = client_restored.get("/user/full").json()
    print(f"恢復了 {len(restored_users)} 個用戶")
```

## 🔍 自動生成的端點

| 方法 | 路徑 | 功能 |
|------|------|------|
| `POST` | `/model` | 創建資源 |
| `GET` | `/model/{id}/data` | 獲取數據 |
| `GET` | `/model/{id}/meta` | 獲取元數據 |
| `GET` | `/model/{id}/full` | 獲取完整資源 |
| `PUT` | `/model/{id}` | 完整更新 |
| `PATCH` | `/model/{id}` | JSON Patch 更新 |
| `DELETE` | `/model/{id}` | 軟刪除 |
| `GET` | `/model/data` | 列出所有數據 |
| `GET` | `/model/meta` | 列出所有元數據 |
| `GET` | `/model/full` | 列出完整資源 |
| `POST` | `/model/{id}/switch/{revision}` | 版本切換 |
| `POST` | `/model/{id}/restore` | 恢復已刪除 |

## 🚀 運行範例

```bash
# 基本範例
python examples/quick_start.py
python examples/resource_crud.py

# 數據遷移
python examples/schema_upgrade.py

# 備份還原
python examples/backup.py

# 不同數據類型
python examples/quick_start.py pydantic
python examples/resource_crud.py dataclass

# 開發服務器
python -m fastapi dev examples/quick_start.py
```