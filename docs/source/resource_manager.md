# ResourceManager 使用說明

ResourceManager 是 AutoCRUD 的核心類別，負責管理各類型資源的 CRUD、版本、索引、權限、事件等操作。以下文檔將介紹其主要功能、常用方法與使用範例。

---

## 主要功能

- 資源的建立、查詢、更新、刪除（CRUD）
- 資源版本管理與切換
- 支援資料遷移（schema migration）
- 欄位索引與查詢
- 權限檢查與事件處理
- 資料備份與還原

---


## 建構方式

通常不直接初始化 ResourceManager，而是透過 AutoCRUD 來註冊模型並取得 ResourceManager 實例：

```python
from autocrud import AutoCRUD
from autocrud.storage import LocalStorage

autocrud = AutoCRUD()
autocrud.add_model(TodoItem, storage=LocalStorage())
manager = autocrud.get_resource_manager(TodoItem)
```

你可以在 add_model 時指定 storage、migration、indexed_fields 等參數，AutoCRUD 會自動建立並管理 ResourceManager。

---

## 常用屬性

- `resource_id`：資源的唯一識別碼，每個資源（如一筆 TodoItem）都會有一個獨立的 resource_id。
- `revision_id`：資源版本的唯一識別碼，每次資源內容變更（如更新、修改）都會產生新的 revision_id（進板）。
- `revision_status`：資源目前版本的狀態，常見有 stable（穩定）、draft（草稿）等，影響可執行的操作。當狀態為 stable 時，無法執行不進板的修改（modify），僅 draft 狀態可用。
- `resource_type`：資源的型別
- `resource_name`：資源名稱（自動轉換格式）
- `indexed_fields`：被索引的欄位
- `schema_version`：目前 schema 版本


### resource_id 與 revision_id 的核心差異

- `resource_id` 用來標識一個資源本身（如某一個使用者、某一筆待辦事項），不會因內容變更而改變。
- `revision_id` 則用來標識資源的某個版本，每次資源內容有變動（如更新、修正）都會產生新的 revision_id，方便追蹤歷史紀錄與版本切換。


簡單來說：
- `resource_id` = 資源的「身份證字號」
- `revision_id` = 資源某次「內容快照」的編號

#### 與 Git Repo 的比對
- `resource_id` 類似 Git repo 的檔案名稱（如 README.md），不管內容怎麼改，檔案名稱都不變。
- `revision_id` 則像是 Git 的 commit hash，每次 commit 都會產生一個新的 hash，代表檔案在某個時間點的狀態。

---

## 主要方法

| 方法 | 說明 |
|------|------|
| `create(data, status=...)` | 建立新資源 |
| `get(resource_id)` | 取得資源最新版本 |
| `get_resource_revision(resource_id, revision_id)` | 取得指定版本 |
| `update(resource_id, data, status=...)` | 全量更新資源，會產生新的 revision id（進板） |
| `modify(resource_id, data/patch, status=...)` | 全量或局部更新，不會產生新 revision id（不進板），僅限資源狀態為 draft，狀態為 stable 時會失敗 |
| `patch(resource_id, patch_data)` | 套用 JSON Patch，預設會產生新 revision id（進板），可選用 modify mode（不進板） |
| `delete(resource_id)` | 軟刪除資源 |
| `restore(resource_id)` | 還原已刪除資源 |
| `switch(resource_id, revision_id)` | 切換到指定版本 |
| `list_revisions(resource_id)` | 列出所有版本 |
| `search_resources(query)` | 查詢資源（支援索引）|
| `count_resources(query)` | 計算資源數量 |
| `migrate(resource_id)` | 執行 schema 遷移 |
| `dump()` | 備份所有資源資料 |
| `load(key, bio)` | 還原資料 |

---

## 使用範例

```python
from autocrud.resource_manager import ResourceManager
from autocrud.storage import LocalStorage

# 假設有一個 TodoItem 結構
class TodoItem(Struct):
    title: str
    completed: bool

storage = LocalStorage()
manager = ResourceManager(TodoItem, storage=storage)

# 建立資源
info = manager.create(TodoItem(title="test", completed=False))

# 查詢資源
resource = manager.get(info.resource_id)
print(resource.data)

# 更新資源
manager.update(info.resource_id, TodoItem(title="done", completed=True))

# 刪除資源
manager.delete(info.resource_id)

# 還原資源
manager.restore(info.resource_id)
```

---

## 進階功能

- 權限檢查：可注入 `IPermissionChecker` 實現細緻權限控管
- 事件處理：支援自訂事件處理器，擴展行為
- 索引查詢：可設定 `indexed_fields` 以加速查詢
- 資料遷移：支援 schema 版本升級與資料轉換

---

## 注意事項

- ResourceManager 需搭配合適的 Storage 實現
- 建議使用 msgspec.Struct 作為資源型別以獲得最佳效能
- 欄位索引需在初始化時指定

---

如需更詳細 API 說明，請參考原始碼或提出問題！
