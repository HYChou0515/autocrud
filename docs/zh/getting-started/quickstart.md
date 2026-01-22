---
title: 快速開始
description: 5 分鐘快速上手 AutoCRUD
---

# 快速開始

這份指南將帶你在 5 分鐘內建立一個完整的 CRUD API。

## 第一步：安裝

```bash
pip install autocrud
```

## 第二步：定義資料模型

使用 `msgspec.Struct` 定義你的資料模型：

```python
from msgspec import Struct
from datetime import datetime

class TodoItem(Struct):
    title: str
    completed: bool = False
    due: datetime | None = None
```

!!! tip "為什麼用 msgspec？"
    AutoCRUD 使用 `msgspec` 而非 Pydantic，因為它提供：
    
    - ⚡ 更快的序列化/反序列化速度
    - 🎯 更精確的型別檢查
    - 💾 更小的記憶體佔用

## 第三步：建立 AutoCRUD 實例

```python
from autocrud import AutoCRUD

crud = AutoCRUD()
crud.add_model(TodoItem)
```

## 第四步：整合到 FastAPI

```python
from fastapi import FastAPI

app = FastAPI()
crud.apply(app)
# 建立 swagger docs
crud.openapi(app)
```

## 完整範例

將以上步驟組合起來：

```python title="main.py"
from msgspec import Struct
from datetime import datetime
from fastapi import FastAPI
from autocrud import AutoCRUD

class TodoItem(Struct):
    title: str
    completed: bool = False
    due: datetime | None = None

# 建立 AutoCRUD
crud = AutoCRUD()
crud.add_model(TodoItem)

# 建立 FastAPI app
app = FastAPI(title="Todo API")
crud.apply(app)
# 建立 swagger docs
crud.openapi(app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

## 啟動服務

=== "使用 uvicorn"

    ```bash
    uvicorn main:app --reload
    ```

=== "使用 FastAPI CLI"

    ```bash
    fastapi dev main.py
    ```

=== "使用 uv"

    ```bash
    uv run uvicorn main:app --reload
    ```

## 測試 API

啟動後訪問 [http://localhost:8000/docs](http://localhost:8000/docs) 查看自動生成的 Swagger UI。

### 建立一筆待辦事項

```bash
curl -X POST "http://localhost:8000/todo-item" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "學習 AutoCRUD",
    "completed": false,
    "due": "2025-01-20T12:00:00"
  }'
```

回應：

```json
{
  "resource_id": "todo-item_abc123",
  "revision_id": "rev_xyz789",
  "status": "stable",
  "created_at": "2025-01-17T10:30:00Z"
}
```

### 查詢待辦事項

```bash
curl "http://localhost:8000/todo-item/todo-item_abc123/data"
```

### 更新待辦事項

使用 JSON Patch 標準：

```bash
curl -X PATCH "http://localhost:8000/todo-item/todo-item_abc123" \
  -H "Content-Type: application/json" \
  -d '[
    {"op": "replace", "path": "/completed", "value": true}
  ]'
```

### 列出所有待辦事項

```bash
curl "http://localhost:8000/todo-item/data"
```

## 自動生成的端點

AutoCRUD 為 `TodoItem` 自動生成了以下端點：

| 方法 | 路徑 | 說明 |
|------|------|------|
| `POST` | `/todo-item` | 建立資源 |
| `GET` | `/todo-item/{id}/data` | 取得資源內容 |
| `GET` | `/todo-item/{id}` | 取得資源 metadata |
| `PATCH` | `/todo-item/{id}` | JSON Patch 更新 |
| `PUT` | `/todo-item/{id}` | 完整更新 |
| `DELETE` | `/todo-item/{id}` | 軟刪除 |
| `POST` | `/todo-item/{id}/restore` | 還原已刪除資源 |
| `GET` | `/todo-item/data` | 列表與搜尋 |
| `GET` | `/todo-item/{id}/revisions` | 取得版本歷史 |
| `POST` | `/todo-item/{id}/switch` | 切換版本 |

!!! info "還有更多端點"
    完整的端點列表請參考 [AutoCRUD 路由](../core-concepts/auto-routes.md#auto-fastapi-routes)。

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