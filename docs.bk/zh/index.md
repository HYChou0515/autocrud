---
title: AutoCRUD
description: 模型驅動的自動化 FastAPI：內建版本控制、權限與搜尋
---

# AutoCRUD

<div class="grid cards" markdown>

-   :material-clock-fast:{ .lg .middle } __快速上手__

    ---

    定義資料模型，一行代碼生成完整 CRUD API

    [:octicons-arrow-right-24: 開始使用](getting-started/quickstart.md)

-   :material-wizard-hat:{ .lg .middle } __Starter Wizard__

    ---

    互動式快速生成完整 AutoCRUD 專案，零樣板配置

    [:octicons-arrow-right-24: 開始使用 Wizard](https://hychou0515.github.io/autocrud/wizard/){ target="_blank" }

-   :material-cog-outline:{ .lg .middle } __自動化一切__

    ---

    自動生成路由、權限、版本控制、搜尋與索引

    [:octicons-arrow-right-24: 核心概念](core-concepts/architecture.md)

-   :material-speedometer:{ .lg .middle } __高效能__

    ---

    基於 FastAPI + msgspec，提供極速序列化與部分讀寫

    [:octicons-arrow-right-24: 效能測試](benchmarks/index.md)

-   :material-puzzle-outline:{ .lg .middle } __高度可擴展__

    ---

    靈活的事件系統、自定義路由與混合儲存策略

    [:octicons-arrow-right-24: 查看範例](examples/index.md)

</div>

## 特色功能

<div class="grid" markdown>

:material-brain:{ .lg .middle } __只需關心業務與模型__

開發者只需專注 business logic 與 domain model schema；metadata、索引、事件、權限等基礎能力由框架自動處理

:material-cog-sync:{ .lg .middle } __自動 FastAPI__

一行代碼套用模型，自動生成 CRUD 路由與 OpenAPI/Swagger，零樣板、零手工綁定

:material-file-tree:{ .lg .middle } __版本控制__

原生支援完整版本歷史、草稿不進版編輯、版本切換與還原，適合審計/回溯/草稿流程

:material-tune-variant:{ .lg .middle } __高度可定制__

靈活的路由命名、索引欄位、事件處理器與權限檢查

:material-rocket-launch:{ .lg .middle } __高性能__

基於 FastAPI + msgspec，低延遲高吞吐

:material-shield-check:{ .lg .middle } __權限系統__

Global / Model / Resource 三層 RBAC 與自定義檢查器

</div>

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
| ✅ Blob優化 | BlobStore 去重、延遲載入 |
| ✅ 權限控制 (Permissions) | Global / Model / Resource 三層 RBAC 與自定義檢查器 |
| ✅ Event Hooks | 每種操作都可以自訂 Before / After / OnSuccess / OnError |
| ✅ Route Templates | 標準 CRUD 與plug-in自定義端點 |
| ✅ 搜尋與索引 (Search / Index) | Meta Store 提供高效篩選、排序、分頁與複雜查詢 |
| ✅ 審計 / 日誌 (Audit / Logging) | 支援事件後的審計紀錄與審查流程 |
| ✅ 訊息佇列 (Message Queue) | 內建非同步任務處理，將 Job 視為資源進行版本與狀態管理 |

## 快速範例

```python
from datetime import datetime
from fastapi import FastAPI
from autocrud import AutoCRUD
from msgspec import Struct

class TodoItem(Struct):
    title: str
    completed: bool
    due: datetime

# 創建 AutoCRUD
crud = AutoCRUD()
crud.add_model(TodoItem)

app = FastAPI()
crud.apply(app)

# 就這樣！自動生成以下端點：
# - POST /todo-item - 創建
# - GET /todo-item/{id}/data - 讀取
# - PATCH /todo-item/{id} - JSON Patch 更新
# - DELETE /todo-item/{id} - 軟刪除
# - GET /todo-item/data - 列表搜尋
# 還有十多種其他端點...
```

!!! tip "啟動開發服務器"
    ```bash
    uv run fastapi dev main.py
    ```
    
    訪問 [http://localhost:8000/docs](http://localhost:8000/docs) 查看自動生成的 API 文檔。

## 安裝

=== "基本安裝"

    ```bash
    pip install autocrud
    ```

=== "包含 S3 支援"

    ```bash
    pip install "autocrud[s3]"
    ```

=== "包含 Magic (Content-Type 偵測)"

    ```bash
    pip install "autocrud[magic]"
    ```

!!! note "python-magic 依賴"
    `autocrud[magic]` 依賴 `python-magic`。
    
    - **Linux**: 需確認環境已安裝 `libmagic` (例如 Ubuntu 下執行 `sudo apt-get install libmagic1`)。
    - **其他 OS**: 請參考 [python-magic 安裝說明](https://github.com/ahupp/python-magic#installation)。

## 下一步

<div class="grid cards" markdown>

-   [:material-book-open-page-variant: 快速開始](getting-started/quickstart.md)
-   [:material-domain: 架構概覽](core-concepts/architecture.md)
-   [:material-api: AutoCRUD 路由](core-concepts/auto-routes.md)
-   [:material-code-braces: 範例集](examples/index.md)
-   [:material-wizard-hat: Starter Wizard](https://hychou0515.github.io/autocrud/wizard/){ target="_blank" }

</div>