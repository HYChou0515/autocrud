# 🚀 快速開始

5 分鐘上手 AutoCRUD。

## 安裝

```{termynal}
    $ pip install autocrud
    -->
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

- `POST /todo-item` - 創建
- `GET /todo-item/{id}/data` - 讀取
- `PATCH /todo-item/{id}` - JSON Patch 更新
- `DELETE /todo-item/{id}` - 軟刪除
- `GET /todo-list/data` - 列表, 支援搜尋

➡️ *[自動路由說明](auto_routes.md)*

## 透過 ResourceManager 操作資源

ResourceManager 是 AutoCRUD 的資源操作入口，負責管理資源的建立、查詢、更新、刪除、版本等操作。

➡️ *[ResourceManager 使用說明](resource_manager.md)*

## 🚀 快速開始

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

# 創建 CRUD API
crud = AutoCRUD()
crud.add_model(TodoItem)
crud.add_model(TodoList)

app = FastAPI()
crud.apply(app)

# 測試
client = TestClient(app)
resp = client.post("/todo-list", json={"items": [], "notes": "我的待辦"})
todo_id = resp.json()["resource_id"]

# 使用 JSON Patch 添加項目
client.patch(f"/todo-list/{todo_id}", json=[{
    "op": "add", 
    "path": "/items/-",
    "value": {
        "title": "完成項目",
        "completed": False,
        "due": (datetime.now() + timedelta(hours=1)).isoformat()
    }
}])

# 獲取結果
result = client.get(f"/todo-list/{todo_id}/data")
print(result.json())
```

**啟動開發服務器:**

```bash
python -m fastapi dev main.py
```

訪問 http://localhost:8000/docs 查看自動生成的 API 文檔。


## 更多範例請看`quick_start.py`

```bash
python quick_start.py
```

---
