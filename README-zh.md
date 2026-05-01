# SpecStar

[![Docs](https://img.shields.io/badge/Docs-Documentation-blue)](https://hychou0515.github.io/specstar/)
[![Wizard](https://img.shields.io/badge/Wizard-Starter_Wizard-ff69b4)](https://hychou0515.github.io/specstar/wizard/)
[![PyPI](https://img.shields.io/pypi/v/specstar)](https://pypi.org/project/specstar/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Automation-009688)](https://fastapi.tiangolo.com)
[![GraphQL](https://img.shields.io/badge/GraphQL-Supported-E10098?logo=graphql)](https://graphql.org/)
[![msgspec](https://img.shields.io/badge/msgspec-Supported-5e60ce)](https://github.com/jcrist/msgspec)
[![Versioning](https://img.shields.io/badge/Versioning-Built--in-blue)]()

<div style="padding:12px;border:1px solid #add3ff99;border-radius:8px;background: #add3ff33;">
  <strong>SpecStar 是模型驅動的自動化FastAPI：</strong>內建版本控制、權限與搜尋，聚焦業務邏輯快速上線。
</div>

## ✨ 特色

- 🧠 **只需關心業務與模型**：開發者只需專注 business logic 與 domain model schema；metadata、索引、事件、權限等基礎能力由框架自動處理
- ⚙️ **自動 FastAPI**：一行代碼套用模型，自動生成 CRUD 路由與 OpenAPI/Swagger，零樣板、零手工綁定
- 🗂️ **版本控制**：原生支援完整版本歷史、草稿不進版編輯、版本切換與還原，適合審計/回溯/草稿流程
- 🔧 **高度可定制**：靈活的路由命名、索引欄位、事件處理器與權限檢查
- 🏎️ **高性能**：基於 FastAPI + msgspec，低延遲高吞吐

## 🧙 Starter Wizard

使用互動式 **Starter Wizard** 快速生成可直接執行的 SpecStar 專案，包含模型、儲存與權限配置 — 免去手動撰寫樣板程式碼。

👉 [https://hychou0515.github.io/specstar/wizard/](https://hychou0515.github.io/specstar/wizard/)

## 功能概覽

| 功能 | 說明 |
| :--- | :--- |
| ✅ 自動生成 (Schema → API/Storage) | `Schema as Infrastructure`：自動產生路由、邏輯綁定與儲存映射 |
| ✅ 版本控制 (Revision History) | Draft→Update / Stable→Append、完整 parent revision 鏈 |
| ✅ 遷移 (Migration) | Functional Converter，Lazy Upgrade on Read + Save |
| ✅ 儲存架構 (Storage) | Hybrid：Meta (SQL/Redis) + Payload (Object Store) + Blob |
| ✅ 可擴展性 (Scale Out) | 使用 Object Storage 與索引分離，便於水平擴展 |
| ✅ 局部更新 (Partial Update / PATCH) | JSON Patch精準更新, 提速省頻寬 |
| ✅ 局部讀取 (Partial Read) | msgspec 解碼階段跳過不必要欄位, 提速省頻寬 |
| ✅ GraphQL 整合 | 自動產生 Strawberry GraphQL Endpoint |
| ✅ Blob優化 | BlobStore 去重、延遲載入、Upload Session（支援 proxy 與 presigned URL） |
| ✅ 權限控制 (Permissions) | Global / Model / Resource 三層 RBAC 與自定義檢查器 |
| ✅ Event Hooks | 每種操作都可以自訂 Before / After / OnSuccess / OnError |
| ✅ Route Templates | 標準 CRUD 與plug-in自定義端點 |
| ✅ 搜尋與索引 (Search / Index) | Meta Store 提供高效篩選、排序、分頁與複雜查詢 |
| ✅ 審計 / 日誌 (Audit / Logging) | 支援事件後的審計紀錄與審查流程 |
| ✅ 訊息佇列 (Message Queue) | 內建非同步任務處理，將 Job 視為資源進行版本與狀態管理 |

## 安裝

```
pip install specstar
```

**Optional Dependencies**

若需要 **S3** 儲存支援：

```
pip install "specstar[s3]"
```

若需要 **BlobStore 自動偵測 Content-Type**：

```
pip install "specstar[magic]"
```

`specstar[magic]` 依賴 `python-magic`。
- **Linux**: 需確認環境已安裝 `libmagic` (例如 Ubuntu 下執行 `sudo apt-get install libmagic1`)。
- **其他 OS**: 請參考 [python-magic 安裝說明](https://github.com/ahupp/python-magic#installation)。

## 文檔

https://hychou0515.github.io/specstar/

## 查詢分頁預設值設定

列表型端點預設會分頁。若想調整啟動時的預設上限，可設定環境變數：

```bash
export AUTOCRUD_DEFAULT_QUERY_LIMIT=1000
```

- 若未設定，系統會使用非常大的 fallback
- 單次請求仍可用 `limit` 參數覆寫
- 若需要精確總數，請呼叫 `/count`

## SpecStar Web Generator

[`specstar-web-generator`](https://www.npmjs.com/package/specstar-web-generator) 可以直接從 SpecStar 後端的 OpenAPI 規格，在幾秒內生成一個完整的 React 管理後台，不需要手寫任何前端樣板程式碼。

對著正在執行的 API 跑一次 generator，就能得到：

- **TypeScript 型別** — 從 OpenAPI schemas 自動推導
- **Axios API client** — 每個資源各自一份，可直接使用
- **列表頁面** — 含伺服器端分頁、排序與搜尋
- **新增頁面** — 依 schema 自動產生表單，搭配 Zod 驗證
- **詳情頁面** — 含完整版本歷史瀏覽（SpecStar revision）
- **Dashboard** — 顯示各資源的即時數量

生成結果是完整獨立的 [Vite](https://vitejs.dev/) + [React](https://react.dev/) + [Mantine](https://mantine.dev/) + [TanStack Router](https://tanstack.com/router) 專案，產出的程式碼完全歸你所有，可以自由客製化。

**快速開始**（後端須先在 `http://localhost:8000` 執行）：

```bash
npm install -g specstar-web-generator
specstar-web init my-app
cd my-app && pnpm install
pnpm generate --url http://localhost:8000
pnpm dev
```

完整的 CLI 選項與客製化說明請見 [generator README](web/generator/README.md)。

## 第一個 API

```python
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
from specstar import SpecStar
from msgspec import Struct

class TodoItem(Struct):
    title: str
    completed: bool
    due: datetime

class TodoList(Struct):
    items: list[TodoItem]
    notes: str

# 創建 SpecStar
crud = SpecStar()
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

➡️ *[SpecStar 使用指南](https://hychou0515.github.io/specstar/auto_routes)*

## 透過 ResourceManager 操作資源

ResourceManager 是 SpecStar 的資源操作入口，負責管理資源的建立、查詢、更新、刪除、版本等操作。

其核心是「版本控制」：每次 `create/update/patch` 都會產生新的 `revision_id`（進版），完整保留歷史；草稿（`draft`）可用 `modify` 不進版反覆編輯，確認後切換為 `stable`。你也可以列出所有版本、讀取任意版本、`switch` 切換目前版本，或在軟刪除後 `restore` 還原。索引查詢支援依 metadata 與資料欄位（indexed fields）進行篩選、排序與分頁，適合審計、回溯與大量資料的檢索。

➡️ *[ResourceManager 使用說明](https://hychou0515.github.io/specstar/resource_manager)*


## 🚀 快速開始


```python
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
from specstar import SpecStar
from msgspec import Struct

class TodoItem(Struct):
    title: str
    completed: bool
    due: datetime

class TodoList(Struct):
    items: list[TodoItem]
    notes: str

# 創建 CRUD API
crud = SpecStar()
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
