---
title: 建立第一個 API
description: 詳細步驟指南：從零開始建立完整的 CRUD API
---

# 建立第一個 API

這份指南將詳細說明如何建立一個功能完整的待辦事項 API，包含版本控制、搜尋與過濾功能。

## 專案結構

建議的專案結構：

```
my-todo-api/
├── main.py          # 應用程式入口
├── models.py        # 資料模型定義
├── requirements.txt # 依賴清單
└── .env            # 環境變數（可選）
```

## 步驟 1：安裝依賴

建立 `requirements.txt`：

```txt title="requirements.txt"
autocrud
fastapi
uvicorn[standard]
```

安裝：

```bash
pip install -r requirements.txt
```

## 步驟 2：定義資料模型

建立 `models.py`：

```python title="models.py"
from msgspec import Struct
from datetime import datetime

class TodoItem(Struct):
    """單一待辦事項"""
    title: str
    description: str = ""
    completed: bool = False
    priority: int = 0  # 0=低, 1=中, 2=高
    due: datetime | None = None
    tags: list[str] = []

class TodoList(Struct):
    """待辦清單（包含多個事項）"""
    name: str
    description: str = ""
    items: list[TodoItem] = []
    owner: str = "anonymous"
```

!!! tip "設計資料模型的建議"
    - 使用 `msgspec.Struct` 而非 Pydantic `BaseModel`
    - 為所有非必填欄位提供預設值
    - 使用型別提示來確保資料正確性
    - 善用 Python 3.10+ 的 Union 語法（`str | None`）

## 步驟 3：建立 AutoCRUD 實例

建立 `main.py`：

```python title="main.py"
from fastapi import FastAPI
from autocrud import AutoCRUD
from models import TodoItem, TodoList

# 建立 AutoCRUD 實例
crud = AutoCRUD()

# 註冊模型
# 可選：指定哪些欄位要建立索引以支援搜尋
crud.add_model(
    TodoItem,
    indexed_fields=[
        ("priority", int),
        ("completed", bool),
    ]
)

crud.add_model(
    TodoList,
    indexed_fields=[
        ("owner", str),
    ]
)

# 建立 FastAPI app
app = FastAPI(
    title="Todo API",
    description="使用 AutoCRUD 建立的待辦事項 API",
    version="1.0.0"
)

# 將 CRUD 路由應用到 app
crud.apply(app)
```

## 步驟 4：啟動應用

```bash
uvicorn main:app --reload
```

訪問 [http://localhost:8000/docs](http://localhost:8000/docs) 查看 API 文檔。

## 步驟 5：測試 API

### 建立待辦清單

```bash
curl -X POST "http://localhost:8000/todo-list" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "工作事項",
    "description": "本週工作清單",
    "owner": "alice"
  }'
```

回應：

```json
{
  "resource_id": "todo-list_abc123",
  "revision_id": "rev_xyz789",
  "status": "stable",
  "created_at": "2025-01-17T10:00:00Z",
  "updated_at": "2025-01-17T10:00:00Z"
}
```

### 使用 JSON Patch 添加事項

```bash
curl -X PATCH "http://localhost:8000/todo-list/todo-list_abc123" \
  -H "Content-Type: application/json" \
  -d '[
    {
      "op": "add",
      "path": "/items/-",
      "value": {
        "title": "完成 AutoCRUD 文檔",
        "description": "更新快速開始指南",
        "priority": 2,
        "completed": false,
        "due": "2025-01-20T18:00:00",
        "tags": ["文檔", "高優先"]
      }
    }
  ]'
```

### 建立單一待辦事項

```bash
curl -X POST "http://localhost:8000/todo-item" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "學習 msgspec",
    "priority": 1,
    "tags": ["學習", "技術"]
  }'
```

### 搜尋與過濾

搜尋所有高優先級且未完成的事項：

```bash
curl -X GET "http://localhost:8000/todo-item/data" \
  -H "Content-Type: application/json" \
  -d '{
    "conditions": {
      "and": [
        {
          "field": "priority",
          "operator": "eq",
          "value": 2
        },
        {
          "field": "completed",
          "operator": "eq",
          "value": false
        }
      ]
    },
    "limit": 10
  }'
```

!!! note "索引欄位"
    只有在 `add_model()` 中指定為 `indexed_fields` 的欄位才能用於搜尋條件。

### 查看版本歷史

```bash
curl "http://localhost:8000/todo-list/todo-list_abc123/revisions"
```

## 進階功能

### 添加權限控制

```python
from autocrud.permission import SimplePermissionChecker

# 建立簡單的權限檢查器
permission_checker = SimplePermissionChecker(
    allow_read=True,
    allow_create=True,
    allow_update=True,
    allow_delete=False  # 禁止刪除
)

crud = AutoCRUD(permission_checker=permission_checker)
```

### 添加事件處理器

```python
from autocrud.types import EventContext, IEventHandler

class AuditEventHandler(IEventHandler):
    def after_create(self, ctx: EventContext, resource):
        print(f"資源已建立: {resource.resource_id}")
    
    def after_update(self, ctx: EventContext, resource):
        print(f"資源已更新: {resource.resource_id}")

crud = AutoCRUD(event_handlers=[AuditEventHandler()])
```

### 自定義路由命名

```python
crud.add_model(
    TodoItem,
    route_name="tasks",  # 路由將是 /tasks 而非 /todo-item
    indexed_fields=[("priority", int)]
)
```

## 常見問題

??? question "如何修改已建立的資源？"
    使用 `PATCH` 端點配合 JSON Patch 操作，或使用 `PUT` 進行完整更新。

??? question "資源被刪除後能復原嗎？"
    可以！AutoCRUD 使用軟刪除。使用 `POST /{model}/{id}/restore` 端點復原。

??? question "如何查看資源的所有版本？"
    使用 `GET /{model}/{id}/revisions` 端點取得版本列表。

??? question "能不能只讀取部分欄位？"
    可以！使用 `GET /{model}/{id}/partial` 端點，傳入 `fields` 參數。

## 下一步

<div class="grid cards" markdown>

-   :material-book-open-page-variant: __設定儲存後端__

    ---

    看範例瞭解如何設定儲存後端, 內建memory, disk, sqlite, postgres等等可供選擇

    [:octicons-arrow-right-24: 設定儲存後端](../storage/index.md)

-   :material-book-open-page-variant: __調整API Routes__

    ---

    看範例瞭解如何調整API Routes, 包含設定resource name, route template

    [:octicons-arrow-right-24: 調整API Routes](customize-routes.md)

-   :material-book-open-page-variant: __深入了解__

    ---

    學習 AutoCRUD 的核心概念與架構

    [:octicons-arrow-right-24: 架構概覽](../core-concepts/architecture.md)

-   :material-code-braces: __查看更多範例__

    ---

    探索權限、版本控制等進階功能

    [:octicons-arrow-right-24: 範例集](../examples/index.md)

-   :material-cog: __ResourceManager__

    ---

    直接使用 ResourceManager 進行資源操作

    [:octicons-arrow-right-24: ResourceManager](../core-concepts/resource-manager.md)

</div>