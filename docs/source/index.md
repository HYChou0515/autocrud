# AutoCRUD

🚀 **自動生成 CRUD API 的 Python 庫** - 支持多種數據類型，零配置快速構建 REST API

## ✨ 特色

- 🎯 **多數據類型**: msgspec.Struct, Pydantic, dataclass, TypedDict
- ⚡ **零配置**: 一行代碼生成完整 CRUD API  
- 📚 **自動文檔**: 集成 OpenAPI/Swagger
- 🔧 **高度可定制**: 靈活的路由和命名
- 🏎️ **高性能**: 基於 FastAPI 和 msgspec

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

## 📚 完整文檔導航

```{toctree}
:maxdepth: 2
:caption: 目錄

quickstart
examples  
user_guide
installation
api_reference
```

## 🔗 快速連結

- {doc}`quickstart` - 5分鐘入門
- {doc}`examples` - **完整程式碼範例**
- {doc}`api_reference` - **完整原始碼**
- {doc}`user_guide` - 進階功能
```bash
python -m fastapi dev your_file.py
```

## 📚 文檔

```{toctree}
:maxdepth: 2

quickstart
examples
user_guide
installation
api_reference
contributing
```