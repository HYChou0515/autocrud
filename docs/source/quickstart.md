# 🚀 快速開始

5 分鐘上手 AutoCRUD。

## 安裝

```bash
pip install autocrud
```

## 第一個 API

```python
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
from autocrud import AutoCRUD
from msgspec import Struct

class TodoItem(Struct):
    title: str
    completed: bool
    due: datetime

class TodoList(Struct):
    items: list[TodoItem]
    notes: str

# 創建 AutoCRUD
crud = AutoCRUD()
crud.add_model(TodoItem)
crud.add_model(TodoList)

app = FastAPI()
crud.apply(app)

uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
```
## 自動生成的端點

更多自動路由細節請參考 [自動路由說明](auto_routes.md)

- `POST /todo-item` - 創建
- `GET /todo-item/{id}/data` - 讀取
- `PATCH /todo-item/{id}` - JSON Patch 更新
- `DELETE /todo-item/{id}` - 軟刪除
- `GET /todo-list/data` - 列表, 支援搜尋


## ResourceManager 簡介

ResourceManager 是 AutoCRUD 的核心類別，負責管理資源的 CRUD、版本、索引、權限等操作。你可以透過 AutoCRUD 取得 ResourceManager 來進行進階操作。

詳細說明請參考：[ResourceManager 使用說明](resource_manager.md)

### 簡單使用範例
```python
from autocrud import AutoCRUD
from autocrud.storage import LocalStorage

autocrud = AutoCRUD()
autocrud.add_model(TodoItem, storage=LocalStorage())
manager = autocrud.get_resource_manager(TodoItem)

# 建立資源
info = manager.create(TodoItem(title="test", completed=False, due=datetime.now()))

# 取得最新版本
resource = manager.get(info.resource_id)
print(resource.data)
```


## python example

```python
def test():
    client = TestClient(app)
    
    # 創建 TODO 清單
    resp = client.post("/todo-list", json={
        "items": [], 
        "notes": "我的待辦事項"
    })
    todo_list_id = resp.json()["resource_id"]
    
    # 使用 JSON Patch 添加項目
    resp = client.patch(f"/todo-list/{todo_list_id}", json=[{
        "op": "add",
        "path": "/items/-",
        "value": {
            "title": "Todo 1",
            "completed": False,
            "due": (datetime.now() + timedelta(hours=1)).isoformat(),
        },
    }])
    
    # 查看結果
    resp = client.get(f"/todo-list/{todo_list_id}/data")
    print(resp.json())
    
    # 標記完成
    resp = client.patch(f"/todo-list/{todo_list_id}", json=[
        {"op": "replace", "path": "/items/0/completed", "value": True}
    ])

if __name__ == "__main__":
    test()
```

## 支援的數據類型

### msgspec.Struct (推薦)
```python
from msgspec import Struct
class User(Struct):
    name: str
    age: int
```

### dataclass
```python
from dataclasses import dataclass
@dataclass
class User:
    name: str
    age: int
```

### TypedDict
```python
from typing import TypedDict
class User(TypedDict):
    name: str
    age: int
```

## Quick Start範例

此處使用`examples/quick_start.py`

```bash
# 默認 msgspec
python quick_start.py

# 其他類型
python quick_start.py dataclass
python quick_start.py typeddict

# 開發服務器
python -m fastapi dev quick_start.py
```
---
