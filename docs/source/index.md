# AutoCRUD

[![FastAPI](https://img.shields.io/badge/FastAPI-Automation-009688)](https://fastapi.tiangolo.com)
[![msgspec](https://img.shields.io/badge/msgspec-Supported-5e60ce)](https://github.com/jcrist/msgspec)
[![Versioning](https://img.shields.io/badge/Versioning-Built--in-blue)]()

<div style="padding:12px;border:1px solid #add3ff99;border-radius:8px;background: #add3ff33;">
  <strong>AutoCRUD 是模型驅動的自動化FastAPI：</strong>內建版本控制、權限與搜尋，聚焦業務邏輯快速上線。
</div>

## ✨ 特色

- 🧠 **只需關心業務與模型**：開發者只需專注 business logic 與 domain model schema；metadata、索引、事件、權限等基礎能力由框架自動處理
- ⚙️ **自動 FastAPI**：一行代碼套用模型，自動生成 CRUD 路由與 OpenAPI/Swagger，零樣板、零手工綁定
- 🗂️ **版本控制**：原生支援完整版本歷史、草稿不進版編輯、版本切換與還原，適合審計/回溯/草稿流程
- 🔧 **高度可定制**：靈活的路由命名、索引欄位、事件處理器與權限檢查
- 🏎️ **高性能**：基於 FastAPI + msgspec，低延遲高吞吐

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
crud.openapi(app)

uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
```
## 自動生成的CRUD端點

- `POST /todo-item` - 創建
- `GET /todo-item/{id}/data` - 讀取
- `PATCH /todo-item/{id}` - JSON Patch 更新
- `DELETE /todo-item/{id}` - 軟刪除
- `GET /todo-list/data` - 列表, 支援搜尋
- *其他十多種auto endpoints*

➡️ *[AutoCRUD 使用指南](auto_routes.md)*

## 透過 ResourceManager 操作資源

ResourceManager 是 AutoCRUD 的資源操作入口，負責管理資源的建立、查詢、更新、刪除、版本等操作。

其核心是「版本控制」：每次 `create/update/patch` 都會產生新的 `revision_id`（進版），完整保留歷史；草稿（`draft`）可用 `modify` 不進版反覆編輯，確認後切換為 `stable`。你也可以列出所有版本、讀取任意版本、`switch` 切換目前版本，或在軟刪除後 `restore` 還原。索引查詢支援依 metadata 與資料欄位（indexed fields）進行篩選、排序與分頁，適合審計、回溯與大量資料的檢索。

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

## 文檔導覽

```{toctree}
:maxdepth: 1

auto_routes
resource_manager
examples

permission_quick_start
permission_setup_guide
permission_system_guide
```
