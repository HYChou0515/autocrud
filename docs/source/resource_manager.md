# 🗂️ Resource Manager

ResourceManager 是 AutoCRUD 的核心類別，負責管理各類型資源的 CRUD、版本、索引、權限、事件等操作。以下文檔將介紹其主要功能、常用方法與使用範例。

---

## Resource 管理哲學

- **專注業務邏輯**：metadata 自動管理，業務只需定義資料本體  

    所有資源的 metadata（如 id、建立者、時間、schema 版本等）與本體分離，減少重複設計，支援自動生成、查詢、排序、索引。  
    ➡️ *[Resource Meta 與 Revision Info](#resource-meta-revision-info)*

- **完整版本控管**：所有操作均可回溯、復原  

    每次更新、刪除都會產生新版本（revision），可回溯歷史、切換版本，支援列出所有版本、還原已刪除資源。  
    ➡️ *[版本管理](#version-control)*

- **多元儲存機制**: 提供PostgreSQL, S3, Redis

    metadata與本體分開儲存: metadata可使用RDMBS以便快速查找任意index欄位,
    本體使用S3或Disk, 以便快速以key-value方式讀取  
    ➡️ *[Storage](auto_routes.md#storage)*

- **彈性的結構變更**：schema 版本控管，支援自訂搬遷邏輯  

    當需要不相容的結構更新時，僅須定義最小化/僅業務的搬遷邏輯，即可支援自動升級與資料遷移。  
    ➡️ *[Schema Migration](#schema-migration)*

- **進階功能皆以資源為中心**：權限、事件驅動、備份

    權限檢查可細緻到資源層級，事件處理支援多階段，索引查詢與資料備份還原皆方便整合第三方功能。  
    ➡️ *[Advance Usage](#advance-usage)*

---

## Resource Manager 與一般 ORM（如 SQLAlchemy）的差異

- **沒有 Foreign Key（外鍵），行為明確在程式碼**

    - 行為不藏在資料庫設定：外鍵常啟用 `ON DELETE/UPDATE CASCADE`、`SET NULL` 等自動行為；一旦在 DB 層啟用，即使更動應用程式邏輯也會持續生效，導致行為不完全體現在程式碼、從程式碼角度難以審核與測試（除非同步調整 DB schema）。  
    - 索引不等於外鍵：若目標只是查詢效能或標記關聯，建立索引即可，未必要外鍵。外鍵的核心是參照完整性與（可選的）自動行為，而非查詢能力；需要 DB 級一致性才用外鍵，不需要時用索引即可。  
    - 不提供關聯與外鍵標記：AutoCRUD 不支援跨資源「關聯」或外鍵標記，也不會在 DB 層面強制參照完整性或啟用自動行為。你可在結構中自行存放其他資源的 `resource_id` 或 `revision_id` 作為業務欄位，但框架不視為外鍵、也不產生隱性副作用。  
    - 所見即所得、事件驅動：所有行為都在程式碼中明確呈現；需要級聯刪除或同步更新時，請以事件處理器（event handler）顯性實作。沒有 handler，就不做隱性動作。系統因此更單純、易讀、可測、可審計。  

- **版本控制**

    - 版本是核心概念：每次建立、更新、修補都會產生新版本（revision），完整保留歷史；一般 ORM 多以覆蓋更新為主，版本留存需自行設計。  
    - 可切換與還原：支援列出版本、讀取任意版本、切換到指定版本、軟刪除後還原；一般 ORM 通常不原生提供版本切換與還原。  
    - 草稿與正式分離：草稿（draft）狀態允許不進版修改（`modify`），確認後再進版為正式（stable）；多數 ORM 不內建此狀態流與不進版編輯。  
    - 刪除仍保留歷史：刪除為軟刪除，資料與版本仍在；一般 ORM 的刪除常為硬刪除或需自行擴充。  
    - 查詢與審計友善：版本完整、行為可回溯，適合比對、審核、恢復；一般 ORM 需額外審計表或事件機制才有同等能力。  
    
    ➡️ *[版本管理](#version-control)*

- **Schema Migration**
    - 類似 [Alembic](https://alembic.sqlalchemy.org/en/latest/)，但更強調「跨版本欄位變動」的可觀測性。
    - 僅需提供一個函式：輸入舊版 schema 的資料（`IO[bytes]`），輸出新版 schema 的物件。
    - 遷移細節由你掌握，簡單透明。  

    ➡️ *[Schema Migration](#schema-migration)*

- **Pure Python**
    - 完全以 Python 實作與使用，無框架耦合與隱性魔術；易讀、易測、易整合，部署與維運成本低。

- **Event Driven**
    - 以事件驅動擴展行為：支援自訂事件處理器（event handler）在建立、更新、刪除、遷移等階段插入邏輯。
    - 需要級聯刪除、同步更新、通知等流程時，透過事件顯性實作；未註冊事件則不做隱性動作。

- **權限管理**
    - 以資源為中心的權限檢查：可注入 `IPermissionChecker`，細緻到資源/版本層級的讀寫控制。
    - 支援情境化權限（依使用者、時間、狀態）、複合策略與審計需求，易於與既有認證系統整合。

---

## 註冊資源

透過 AutoCRUD 來註冊模型並取得 ResourceManager 實例：

```{code-block} python
:emphasize-lines: 9
from autocrud import AutoCRUD
from msgspec import Struct

class TodoItem(Struct):
    title: str
    completed: bool

autocrud = AutoCRUD(default_user="user", default_now=datetime.now)
autocrud.add_model(TodoItem)
manager = autocrud.get_resource_manager(TodoItem)
```

你可以在 add_model 時指定 storage、migration、indexed_fields 等參數，AutoCRUD 會自動建立並管理 ResourceManager。

```{code-block} python
:emphasize-lines: 3
autocrud.add_model(
    TodoItem,
    indexed_fields=["completed"],
)
```


---

### Terminology

| 方法 | 說明 | 範例 |
|------|------|------|
| `resource_type` | 資源的型別 | TodoItem |
| `resource_id` | 資源的唯一識別碼，每個資源都會有一個獨立的 resource_id。類似 Git repo 的名稱，不管內容怎麼改，檔案名稱都不變。| `todo-item:1fff687d5e8f` |
| `revision_id` | 資源版本的唯一識別碼，每次資源內容變更（如更新、修改）都會產生新的 revision_id（進版）。像是 Git 的 commit hash，每次 commit 都會產生一個新的 hash，並且紀錄誰更新, 何時更新。| `todo-item:1fff687d5e8f:1` |
| `resource_name` | 資源類別名稱, 從autocrud取得manager時或是自動生成的CRUD API endpoint用到。| todo-item |
| `revision_status` | 資源目前版本的狀態，常見有 stable（穩定）、draft（草稿）等，影響可執行的操作。當狀態為 stable 時，無法執行不進版的修改（modify），僅 draft 狀態可用。| stable/draft |
| `indexed_field` | 被索引的欄位，用於快速查找，排序資源。| title/completed  |
| `schema_version` | 資源的 schema 版本。| None/v1 |

---

## 資源操作方法

| 方法 | 說明 |
|------|------|
| [＃建立](#create)|
| [`create(data, status=...)`](#autocrud.resource_manager.core.ResourceManager.create)                                       | 建立新資源 |
| [＃讀取](#read)|
| [`get(resource_id)`](#autocrud.resource_manager.core.ResourceManager.get)                                                  | 取得資源最新版本 |
| [`get_resource_revision(resource_id, revision_id)`](#autocrud.resource_manager.core.ResourceManager.get_resource_revision) | 取得指定版本 |
| [`search_resources(query)`](#autocrud.resource_manager.core.ResourceManager.search_resources)                              | 查詢資源（支援索引, 分頁, 排序）|
| [`count_resources(query)`](#autocrud.resource_manager.core.ResourceManager.count_resources)                                | 計算資源數量 |
| [`list_revisions(resource_id)`](#autocrud.resource_manager.core.ResourceManager.list_revisions)                            | 列出所有版本 |
| [＃更新](#update)|
| [`update(resource_id, data, status=...)`](#autocrud.resource_manager.core.ResourceManager.update)                          | 全量更新資源，會產生新的 revision id（進版） |
| [`patch(resource_id, patch_data)`](#autocrud.resource_manager.core.ResourceManager.patch)                                  | 套用 JSON Patch，會產生新 revision id（進版） |
| [`modify(resource_id, data/patch, status=...)`](#autocrud.resource_manager.core.ResourceManager.modify)                    | 全量或局部更新，不會產生新 revision id（不進版），僅限資源狀態為 draft，狀態為 stable 時會失敗 |
| [`switch(resource_id, revision_id)`](#autocrud.resource_manager.core.ResourceManager.switch)                               | 切換到指定版本 |
| [＃刪除](#delete) |
| [`delete(resource_id)`](#autocrud.resource_manager.core.ResourceManager.delete)                                            | 軟刪除資源 |
| [`restore(resource_id)`](#autocrud.resource_manager.core.ResourceManager.restore)                                          | 還原已刪除資源 |
| [＃管理](#management)|
| [`migrate(resource_id)`](#autocrud.resource_manager.core.ResourceManager.migrate)                                          | 執行 schema 遷移 |
| [`dump()`](#autocrud.resource_manager.core.ResourceManager.dump)                                                           | 備份所有資源資料 |
| [`load(key, bio)`](#autocrud.resource_manager.core.ResourceManager.load)                                                   | 還原資料 |

### Create

建立新資源，會產生獨立的 resource_id 與第一個 revision。  
常用於新增資料，支援指定初始狀態（如 draft/stable）。

- [`create(data, status=...)`](#autocrud.resource_manager.core.ResourceManager.create)：建立新資源，回傳`ResourceMeta`。

```python
manager: ResourceManager[TodoItem]
# 建立一個新的 TodoItem 資源
info: ResourceMeta = manager.create(TodoItem(title="買牛奶", completed=False), status="draft")
print(info.resource_id)  # 取得新資源的 resource_id
```

---

### Read

取得資源最新版本或指定版本，支援查詢、分頁、排序、計數、版本列表。

- [`get(resource_id)`](#autocrud.resource_manager.core.ResourceManager.get)：取得資源最新版本。

```python
# 取得指定 resource_id 的當前版本
resource = manager.get(resource_id)
print(resource.data)  # resource data
print(resource.info)  # resource info
```

- [`get_resource_revision(resource_id, revision_id)`](#autocrud.resource_manager.core.ResourceManager.get_resource_revision)：取得指定版本內容。

```python
# 取得指定 resource_id 與 revision_id 的版本內容
resource = manager.get_resource_revision(resource_id, revision_id)
print(resource.data)  # resource data
print(resource.info)  # resource info
```

- [`search_resources(query)`](#autocrud.resource_manager.core.ResourceManager.search_resources)：依條件查詢資源（支援索引、分頁、排序）。

```{important}
使用data_conditions必須先建立該field的index, 參考[這裡](#data-attribute-index)獲得更多資訊。
```
```{seealso}
[Resource Searching](#resource-searching)
```

```python
from autocrud.types import ResourceMetaSearchQuery, DataSearchCondition

# 查詢已完成的 TodoItem
query = ResourceMetaSearchQuery(
    # 使用data_conditions必須先建立該field的index
    data_conditions=[
        DataSearchCondition(field_path="completed", operator="eq", value=True)
    ]
)
metas = manager.search_resources(query)
for meta in metas:
    print(meta.resource_id, meta.indexed_data)
```

- [`count_resources(query)`](#autocrud.resource_manager.core.ResourceManager.count_resources)：計算符合條件的資源數量。

```python
# 計算已完成的 TodoItem 數量
count = manager.count_resources(query)
print("已完成數量:", count)
```

- [`list_revisions(resource_id)`](#autocrud.resource_manager.core.ResourceManager.list_revisions)：列出所有版本資訊。

```python
# 列出指定 resource_id 的所有版本資訊
revisions = manager.list_revisions(resource_id)
for rev in revisions:
    print(rev.revision_id, rev.status, rev.created_time)
```

---

### Update

更新資源內容，分為進版（產生新 revision）與不進版（僅限 draft 狀態）。
```{seealso}
[版本管理](#version-control)
```  

- [`update(resource_id, data, status=...)`](#autocrud.resource_manager.core.ResourceManager.update)：全量更新，進版。

```python
# 全量更新資源內容，並進版
manager.update(resource_id, TodoItem(title="新標題", completed=True), status="stable")
```

- [`patch(resource_id, patch_data)`](#autocrud.resource_manager.core.ResourceManager.patch)：套用 JSON Patch，進版。

```python
from jsonpatch import JsonPatch

# 局部更新（JSON Patch），並進版
patch = JsonPatch([{"op": "replace", "path": "/completed", "value": True}])
manager.patch(resource_id, patch)
```

```{seealso}
JSON Patch 定義了一種 JSON 文件結構，用來描述一連串要套用在JSON上的操作序列；這種格式適合用於 HTTP PATCH 方法。  

- [Python `jsonpatch`官方文檔](https://python-json-patch.readthedocs.io/en/latest/tutorial.html#creating-a-patch)
- [JSON Patch (RFC6902) 官方文檔](https://datatracker.ietf.org/doc/html/rfc6902)
```

- [`modify(resource_id, data/patch, status=...)`](#autocrud.resource_manager.core.ResourceManager.modify)：不進版更新（僅 draft 可用）。

```python
# 草稿狀態下直接修改內容（不進版）
manager.modify(resource_id, TodoItem(title="draft修改", completed=False))
# 或用 patch
manager.modify(resource_id, JsonPatch([{"op": "replace", "path": "/title", "value": "draft again"}]))
```

- [`switch(resource_id, revision_id)`](#autocrud.resource_manager.core.ResourceManager.switch)：切換到指定版本。

```python
# 切換到指定 revision_id 的版本
manager.switch(resource_id, revision_id)
```

---

### Delete

軟刪除資源，保留所有版本，可隨時還原。

- [`delete(resource_id)`](#autocrud.resource_manager.core.ResourceManager.delete)：軟刪除資源。

```python
# 軟刪除指定資源
manager.delete(resource_id)
```

- [`restore(resource_id)`](#autocrud.resource_manager.core.ResourceManager.restore)：還原已刪除資源。

```python
# 還原已刪除的資源
manager.restore(resource_id)
```

---

### Management

進行 schema 遷移、資料備份與還原。

- [`migrate(resource_id)`](#autocrud.resource_manager.core.ResourceManager.migrate)：執行 schema migration。  
```{seealso}
[Schema Migration](#schema-migration)
```  

```python
# 執行 schema migration
manager.migrate(resource_id)
```

- [`dump()`](#autocrud.resource_manager.core.ResourceManager.dump)：備份所有資源資料。

```python
# 備份所有資源資料
backup = manager.dump()
```

- [`load(key, bio)`](#autocrud.resource_manager.core.ResourceManager.load)：還原資料。

```python
# 還原資料
with open("backup_file", "rb") as bio:
    manager.load(key, bio)
```

---

## 使用範例

```{code-block} python
:emphasize-lines: 13,16,20,23,26
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

## Resource Meta 與 Revision Info

Resource Meta 負責資源的整體狀態與索引，Revision Info 負責每個版本的細節與追蹤。

**Resource Meta 紀錄資源層級的資訊**
- `resource_id`：資源唯一識別碼
- `current_revision_id`：目前版本的 revision id
- `schema_version`：目前資料結構的版本
- `total_revision_count`：該資源的所有版本數量
- `created_time` / `updated_time`：建立與更新時間
- `created_by` / `updated_by`：建立者與最後更新者
- `is_deleted`：是否已刪除
- `indexed_data`：用於快速查找的索引欄位

**Revision Info 紀錄每個版本的詳細資訊**
- `revision_id`：版本唯一識別碼
- `parent_revision_id`：父版本 id（如有）
- `schema_version` / `parent_schema_version`：本版與父版的 schema 版本
- `data_hash`：資料雜湊值（用於比對內容是否變更）
- `status`：版本狀態（stable/draft）
- `created_time` / `updated_time`：建立與更新時間
- `created_by` / `updated_by`：建立者與最後更新者


### Resource Searching

```{code-block} python
:emphasize-lines: 3-6
# query過去7天內建立的todo items
manager = autocrud.get_resource_manager(TodoItem)
query = ResourceMetaSearchQuery(
    created_time_start=datetime.now()-timedelta(days=7)
)
metas: list[ResourceMeta] = manager.search_resources(query)
count = manager.count_resources(query)
assert len(metas) == count
```

| 欄位 | 說明 | 型別 |
|------|------|------|
| [`is_deleted`](#autocrud.types.ResourceMetaSearchQuery.is_deleted)                  |資源是否被刪除                 | bool                                |
| [`created_time_start`](#autocrud.types.ResourceMetaSearchQuery.created_time_start)  |在這之後建立（含）                   | datetime                    |
| [`created_time_end`](#autocrud.types.ResourceMetaSearchQuery.created_time_end)      |在這之前建立（含）                   | datetime                      |
| [`updated_time_start`](#autocrud.types.ResourceMetaSearchQuery.updated_time_start)  |在這之後修改（含）                   | datetime                    |
| [`updated_time_end`](#autocrud.types.ResourceMetaSearchQuery.updated_time_end)      |在這之前修改（含）                   | datetime                      |
| [`created_bys`](#autocrud.types.ResourceMetaSearchQuery.created_bys)                |誰建立                         | list[str]                          |
| [`updated_bys`](#autocrud.types.ResourceMetaSearchQuery.updated_bys)                |誰更新                         | list[str]                          |
| [`data_conditions`](#autocrud.types.ResourceMetaSearchQuery.data_conditions)        |使用data的indexed fields搜尋 (see [data attribute index](#data-attribute-index))  | list[DataSearchCondition]                     |
| [`sorts`](#autocrud.types.ResourceMetaSearchQuery.sorts)                            |sort fields (see [sorting](#sorting))                    | list[ResourceMetaSearchSort or ResourceDataSearchSort] |
| [`limit`](#autocrud.types.ResourceMetaSearchQuery.limit)                            |pagination limit (see [pagination](#pagination))               | int = 10                                            |
| [`offset`](#autocrud.types.ResourceMetaSearchQuery.offset)                          |pagination offset (see [pagination](#pagination))              | int = 0                                            |


#### Data Attribute Index

你可以在`AutoCrud.add_model`時指定需要index的attributes有哪些, 
ResourceMeta會根據設定負責紀錄需要作為索引的attributes。
想要搜尋時即可使用indexed fields最為篩選條件。

```{code-block} python
:emphasize-lines: 3-11,18
autocrud.add_model(
    TodoItem,
    indexed_fields=[
        # to use completed as an index.
        "completed",
        # ("completed", bool),
        # IndexableField("completed", str)
        
        # to use type as an index
        IndexableField("type", SpecialIndex.msgspec_tag)
    ]
)
...
manager = autocrud.get_resource_manager(TodoItem)
metas = manager.search_resources(ResourceMetaSearchQuery(
    data_conditions=[
        DataSearchCondition(
            field_path="completed", operator="eq", value=True,
        ),
    ]
))
```

`DataSearchCondition`可以提供基本的搜尋功能，詳細使用方式可以參考[DataSearchCondition](#autocrud.types.DataSearchCondition)

#### Sorting

可以使用內建的key來排序，也可以使用[data attribute index](#data-attribute-index)。

```python
# 取得 todo items，先依 completed 排序，再依建立時間排序（升冪）
query = ResourceMetaSearchQuery(
    sorts=[
        # 先依 completed 欄位（已完成在前）排序
        ResourceDataSearchSort(direction="+", field_path="completed"),
        # 再依 created_time（建立時間）排序
        ResourceMetaSearchSort(direction="+", key="created_time"),
    ]
)
```
詳細使用方式可以參考[ResourceDataSearchSort](#autocrud.types.ResourceDataSearchSort)與[ResourceMetaSearchSort](#autocrud.types.ResourceMetaSearchSort)

#### Pagination

這個function示範如何用 limit/offset 參數分批取得查詢結果：

- `limit` 設定每頁最大筆數（這裡用 page_size+1 是為了判斷是否還有下一頁）。
- `offset` 設定目前查詢的起始位置。
- 每次查詢後，`yield` 回傳本頁資料，並判斷是否已到最後一頁（如果回傳筆數 <= page_size 就結束）。
- 這種寫法適合用在大量資料分頁查詢，避免一次載入全部資料造成記憶體壓力。

你可以根據需求調整 page_size，或在 yield 前做資料處理。

```python
def pagination_recipe(query: ResourceMetaSearchQuery):
    query = copy(query)
    page_size = 10
    page_index = 0
    query.limit = page_size+1
    while True:
        query.offset = page_index*page_size
        page_index += 1
        with manager.meta_provide(user, now):
            metas = manager.search_resources(query)
        yield metas[:page_size]
        if len(metas) <= page_size:
            break
```

---

## 版本管理 (Version Control)

AutoCRUD 的版本管理機制，旨在確保每一次資源內容的變更都能被完整記錄、回溯與還原。每個資源都擁有獨立的版本編號（revision id），不論是建立、更新、修改或刪除，都會留下歷史紀錄，方便日後查詢、比對、審計與復原。

這種設計特別適合需要審核流程、草稿反覆編輯、正式版本控管、以及資料安全的場景。無論是草稿階段的暫存、正式發佈的進版、或是誤刪後的還原，都能透過版本管理功能輕鬆實現。

### 進版或不進版

AutoCRUD 的版本管理設計，讓每次資源內容變更都能被完整記錄與回溯。

**進版（create/update/patch）**：
每次呼叫 create、update 或 patch 方法時，系統都會產生新的 revision id，代表一次「進版」操作。這樣可以保留所有歷史版本，方便查詢、比對、還原。

**不進版（modify）**：
只有在資源狀態為 draft（草稿）時，才允許直接修改內容而不產生新 revision id。這種修改僅限於草稿階段，適合反覆編輯、暫存，等到內容確定後再進版。

**查詢與切換版本**：
可用 list_revisions 取得所有 revision id，並用 get_resource_revision 取得任意版本內容。switch 可切換目前版本到任意 revision。

**還原已刪除資源**：
delete 為軟刪除，所有版本仍保留，可用 restore 還原。

這種設計讓資源管理既安全又彈性，能滿足審計、回溯、草稿編輯等多種需求。

---

#### 進版與不進版的實務建議

- **草稿流程**：在內容尚未確定前，建議先將資源 update 成 draft 狀態，再用 modify 反覆編輯內容，最後再用 modify 將狀態切換為 stable，這樣可以避免產生過多無用版本。
    典型流程如下：
    1. 先用 `update(resource_id, ..., status="draft")` 產生 draft 版本。
    2. 用 `modify(resource_id, new_data)` 反覆編輯內容。
    3. 確認內容後，用 `modify(resource_id, ..., status="stable")` 進版為正式。
- **回溯/比對**：所有進版操作都會保留歷史版本，可隨時用 get_resource_revision 取得任意版本內容，或用 switch 切換目前版本，方便比對差異或還原。
- **刪除與還原**：delete 只會標記資源為已刪除，所有版本仍保留，隨時可用 restore 還原，確保資料安全。


#### 狀態切換：stable 改為 draft

若資源目前為 stable 狀態，想要重新進入草稿模式（draft）以便修改，可以直接呼叫：

```python
# 將 stable 狀態改為 draft，並可繼續用 modify 編輯
mgr.modify(resource_id, status="draft")
```
此操作會將資源狀態切換為 draft，之後即可用 modify 反覆編輯內容，直到把status改為stable或是再次進版。

#### API 操作流程範例

```python
# 建立草稿
info = manager.create(data, status="draft")
# 草稿階段反覆修改
manager.modify(info.resource_id, new_data)
# 草稿確認後進版
manager.update(info.resource_id, final_data)
# 取得所有版本
revisions = manager.list_revisions(info.resource_id)
# 切換到舊版本
manager.switch(info.resource_id, revisions[0])
# 軟刪除資源
manager.delete(info.resource_id)
# 還原已刪除資源
manager.restore(info.resource_id)
```

---

## Schema Migration

你只需要提供必要的schema升級邏輯，其他的雜事都由AutoCRUD處理。

當你需要breaking change時，可以告訴AutoCRUD該如何把舊資料舊格式換成新格式，你可以在`add_model`時注入`Migration`。

### 案例

原始`TodoItem`的schema想要加入`category: str`。

```python
# 原始TodoItem schema
class TodoItem(Struct):
    title: str
    completed: bool

autocrud = AutoCRUD(default_user="user", default_now=datetime.now)
autocrud.add_model(TodoItem)
manager = autocrud.get_resource_manager(TodoItem)

# 已經有舊資料存在系統
res: Resource[TodoItem] = manager.get(old_res_id)
```

寫一個`Migration`注入model即可使用`migrate API`做schema migration。

```{code-block} python
:emphasize-lines: 7-18,21

# 新版TodoItem schema
class TodoItem(Struct):
    title: str
    completed: bool
    category: str

class TodoItemMigration(IMigration):
    def migrate(self, data: IO[bytes], schema_version: str | None) -> TodoItem:
        if schema_version is None: # no migration then schema version is None
            obj = msgspec.json.decode(data.read())  # JSON is the default serialization
            obj["category"] = "uncategorized"  # add default category for old data
            return msgspec.convert(obj, TodoItem)  # return new TodoItem object
        # do not support unexpected schema version.
        raise ValueError(f"{schema_version=} is not supported")

    @property
    def schema_version(self) -> str|None:
        return "v1.0"

autocrud = AutoCRUD(default_user="user", default_now=datetime.now)
autocrud.add_model(TodoItem, migration=TodoItemMigration())
manager = autocrud.get_resource_manager(TodoItem)

# 已經有舊資料存在系統
manager.get(old_res_id)
# > msgspec.ValidationError: Object missing required field `category`
# 可以直接使用`migrate`進版
manager.migrate(old_res_id)
# 過後直接使用id取值即可拿到新版資料
res: Resource[TodoItem] = manager.get(old_res_id)
assert res.category == "uncategorized"
```

## 進階功能（Advance Usage）

- 權限檢查：可注入 `IPermissionChecker` 實現細緻權限控管
- 事件處理：支援自訂事件處理器，擴展行為

---

## 原始碼

```{eval-rst}
.. autoclass:: autocrud.types.ResourceMeta
   :members:
   :show-inheritance:
```

```{eval-rst}
.. autoclass:: autocrud.types.RevisionInfo
   :members:
   :show-inheritance:
```

```{eval-rst}
.. autoclass:: autocrud.resource_manager.core.ResourceManager
   :members:
   :no-undoc-members:
   :show-inheritance:
```

```{eval-rst}
.. autoclass:: autocrud.types.ResourceMetaSearchQuery
   :members:
   :no-undoc-members:
   :show-inheritance:
```


```{eval-rst}
.. autoclass:: autocrud.types.DataSearchCondition
   :members:
.. autoclass:: autocrud.types.DataSearchOperator
   :members:
```

```{eval-rst}
.. autoclass:: autocrud.types.ResourceMetaSearchSort
   :members:
.. autoclass:: autocrud.types.ResourceDataSearchSort
   :members:
.. autoclass:: autocrud.types.ResourceMetaSortKey
   :members:
.. autoclass:: autocrud.types.ResourceMetaSortDirection
   :members:
```
