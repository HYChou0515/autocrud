# 🚀 AutoCRUD 使用指南

AutoCRUD 是一個專為 FastAPI 設計的自動化 CRUD 生成器。它不僅僅是生成路由，還提供了版本控制、軟刪除、資料遷移以及靈活的儲存後端支援。

## 📦 快速開始 (Quick Start)

只需幾行程式碼，即可為你的資料模型建立完整的 RESTful API。

```python
from fastapi import FastAPI
from autocrud import AutoCRUD
import msgspec

# 1. 定義你的資料模型 (支援 msgspec.Struct, dataclasses 等)
class User(msgspec.Struct):
    name: str
    email: str
    age: int

# 2. 初始化 FastAPI 與 AutoCRUD
app = FastAPI()
autocrud = AutoCRUD()

# 3. 註冊模型
autocrud.add_model(User)

# 4. 將生成的路由應用到 FastAPI
autocrud.apply(app)

# 5. OpenAPI Integration
autocrud.openapi(app)
```

啟動伺服器後，你將獲得 `/users` 的完整 CRUD 端點。

---

## ⚙️ 初始化設定 (AutoCRUD)

在實例化 `AutoCRUD` 時，你可以設定全域的行為模式。

```{seealso}
[`autocrud.crud.core.AutoCRUD`](#autocrud.crud.core.AutoCRUD)
```

### 自動資源命名 (`model_naming`)

`model_naming` 參數用於設定如何從 Python class 名稱自動生成資源名稱 (Resource Name)。

資源名稱在 AutoCRUD 中必須是獨一無二的，且會直接作為 CRUD API 的 URL 路徑（例如 `/users`）。由於 Python class 通常使用 PascalCase（如 `UserProfile`），但在 URL 中通常不建議使用這種格式，因此你可以透過此參數指定自動轉換規則，省去每次 `add_model` 都需要手動指定 `name` 的麻煩。

預設值為 `kebab` (kebab-case)。

除了內建的字串選項外，你也可以傳入一個函數來實作自定義的命名邏輯。

```{code-block} python
:emphasize-lines: 3
# 選項: "same", "pascal", "camel", "snake", "kebab"
# 將 UserProfile 自動轉換為 user_profile
autocrud = AutoCRUD(model_naming="snake") 
autocrud_custom.add_model(UserProfile)
# 生成路由: /user_profile
```

```{code-block} python
:emphasize-lines: 2-5
# 或者使用自定義函數
def my_naming(model_type: type) -> str:
    return f"api_{model_type.__name__.lower()}"

autocrud_custom = AutoCRUD(model_naming=my_naming)
autocrud_custom.add_model(UserProfile)
# 生成路由: /api_userprofile
```

### 選擇儲存模式 (`storage_factory`)

AutoCRUD 預設使用 **全記憶體 (Memory)** 儲存，適合快速原型開發與測試。若需要資料持久化，可以透過 `storage_factory` 參數切換儲存後端。

```{code-block} python
:emphasize-lines: 7
from autocrud import AutoCRUD, DiskStorageFactory
from pathlib import Path

# 切換為本地磁碟儲存 (Disk Storage)
# 資料將會保存在 ./data 資料夾中
autocrud = AutoCRUD(
    storage_factory=DiskStorageFactory(rootdir=Path("./data"))
)
```

```{seealso}
AutoCRUD 支援多種儲存後端（Memory, Disk, Redis, S3, SQLite, PostgreSQL 等）以及混合模式。關於如何配置進階儲存後端或自定義 Factory，請參閱下方的 [Storage](#storage) 章節。
```

### 資料編碼 (`encoding`)

`encoding` 參數決定了資料在儲存時的序列化格式。

- `Encoding.json` (預設): 使用 JSON 格式，可讀性高，適合除錯。
- `Encoding.msgpack`: 使用 MessagePack 格式，體積小、速度快，適合生產環境。

```{code-block} python
:emphasize-lines: 5
from autocrud import AutoCRUD
from autocrud.resource_manager.basic import Encoding

# 使用 MessagePack 進行高效儲存
autocrud = AutoCRUD(encoding=Encoding.msgpack)
```

### 預設使用者與時間 (`default_user` & `default_now`)

當 API 請求中未提供使用者資訊或時間戳記時，AutoCRUD 會使用這些預設值來記錄資源的 `created_by`, `updated_by`, `created_time`, `updated_time`。

這在測試環境或單人使用的應用中非常方便，可以省去處理認證與時間注入的麻煩。

```{code-block} python
:emphasize-lines: 5-6
from datetime import datetime

# 設定固定的預設使用者與動態時間
autocrud = AutoCRUD(
    default_user="system_admin",
    default_now=datetime.now
)
```

若未設定這些預設值，則在直接操作 `resource_manager` 時，必須透過 `meta_provide` 上下文管理器顯式提供使用者與時間資訊，否則會拋出錯誤。

```{code-block} python
:emphasize-lines: 5
# 若未設定 default_user 與 default_now
manager = autocrud.get_resource_manager(User)

# 必須使用 meta_provide
with manager.meta_provide(user="current_user", now=datetime.now()):
    manager.create(User(name="Alice", email="alice@example.com", age=30))
```

### 依賴注入 (`dependency_provider`)

`dependency_provider` 允許你將 FastAPI 的 `Depends` 注入到 AutoCRUD 生成的路由中。這對於全域的驗證（如 API Key 檢查）、資料庫連線注入或其他前置處理非常有用。

你需要實作 `DependencyProvider` 類別（或其子類別），並覆寫相應的方法。

```{code-block} python
:emphasize-lines: 14
from fastapi import Depends, HTTPException
from autocrud import AutoCRUD
from autocrud.crud.route_templates.basic import DependencyProvider

def verify_api_key(key: str):
    if key != "secret":
        raise HTTPException(403)

class MyDependency(DependencyProvider):
    # 將依賴注入到所有路由
    def get_all_dependencies(self):
        return [Depends(verify_api_key)]

autocrud = AutoCRUD(dependency_provider=MyDependency())
```

### 事件處理 (`event_handlers`)

AutoCRUD 支援事件驅動的架構。你可以註冊 `IEventHandler` 來監聽資源的變更事件（如 `ResourceCreated`, `ResourceUpdated`, `ResourceDeleted`），並執行相應的邏輯（如發送通知、觸發其他服務）。

```{code-block} python
:emphasize-lines: 4-9
from autocrud import AutoCRUD
from autocrud.types import IEventHandler, ResourceCreated

class NotificationHandler(IEventHandler):
    async def handle(self, event):
        if isinstance(event, ResourceCreated):
            print(f"New resource created: {event.resource_id}")

autocrud = AutoCRUD(event_handlers=[NotificationHandler()])
```

### 路由模板 (`route_templates`)

AutoCRUD 預設會為每個模型生成一組標準的 CRUD 路由（包含 Create, List, Read, Update, Patch, Delete, Restore 等）。如果你想要自定義生成的路由集合，例如只想要唯讀 API，或者想要加入自定義的路由模板，可以透過 `route_templates` 參數進行設定。

預設的路由模板列表包含：
- `CreateRouteTemplate`: 建立資源 (POST)
- `ListRouteTemplate`: 列表查詢 (GET)
- `ReadRouteTemplate`: 讀取單一資源 (GET)
- `UpdateRouteTemplate`: 全量更新 (PUT)
- `PatchRouteTemplate`: 部分更新 (PATCH)
- `DeleteRouteTemplate`: 軟刪除 (DELETE)
- `RestoreRouteTemplate`: 還原刪除 (POST)
- `SwitchRevisionRouteTemplate`: 切換版本 (POST)

你可以傳入一個自定義的列表來覆蓋預設行為。

```{code-block} python
:emphasize-lines: 6-10
from autocrud import AutoCRUD
from autocrud.crud.route_templates.get import ReadRouteTemplate
from autocrud.crud.route_templates.search import ListRouteTemplate

# 只生成讀取相關的路由 (Read-Only API)
autocrud = AutoCRUD(
    route_templates=[
        ListRouteTemplate(),
        ReadRouteTemplate()
    ]
)
```

此外，你也可以使用 `add_route_template` 方法在初始化後動態加入模板。

```{code-block} python
:emphasize-lines: 2
# 加入自定義的搜尋模板
autocrud.add_route_template(MyCustomSearchTemplate())
```

```{seealso}
全部路由列表請看[自動生成的路由列表](#auto-fastapi-routes)
```

#### 實作自定義模板

若要建立自己的路由模板，你可以選擇繼承 `BaseRouteTemplate` (推薦) 或直接實作 `IRouteTemplate` 介面。

**方法一：繼承 BaseRouteTemplate (推薦)**

`BaseRouteTemplate` 已經幫你處理好了 `dependency_provider` 的注入以及模板排序 (`order`) 的邏輯，你只需要專注於實作 `apply` 方法來定義路由。

```{code-block} python
from fastapi import APIRouter
from autocrud.crud.route_templates.basic import BaseRouteTemplate

class MyCustomTemplate(BaseRouteTemplate):
    def apply(self, model_name, resource_manager, router: APIRouter):
        # 定義你的路由
        @router.get(f"/{model_name}/hello")
        async def hello():
            return {"message": f"Hello from {model_name}"}

autocrud.add_route_template(MyCustomTemplate())
```

**方法二：實作 IRouteTemplate**

如果你需要完全控制模板的行為，可以直接實作 `IRouteTemplate` 介面。你需要自行實作 `apply` 方法與 `order` 屬性。

```{code-block} python
from autocrud.crud.route_templates.basic import IRouteTemplate

class MyRawTemplate(IRouteTemplate):
    @property
    def order(self) -> int:
        return 999  # 數字越小越先執行

    def apply(self, model_name, resource_manager, router):
        # 實作路由邏輯
        pass
```

---

## 🛠️ 註冊模型 (Adding Models)

使用 `add_model` 方法註冊資源時，除了基本的模型類別外，還支援多種參數來針對個別模型進行細部調整。這些設定會覆蓋全域設定（如果有的話）。

```{seealso}
[`autocrud.crud.core.AutoCRUD.add_model`](#autocrud.crud.core.AutoCRUD.add_model)
```

### 自訂資源名稱 (`name`)

指定資源在 URL 中的名稱。若未設定，則會根據全域的 `model_naming` 規則自動生成。

```{code-block} python
:emphasize-lines: 2
# URL 將變成 /people 而不是 /users
autocrud.add_model(User, name="people")
```

### 資料遷移 (`migration`)

當模型結構發生變化時，透過實作 `IMigration` 介面來處理舊版本資料的升級邏輯。這對於持久化儲存（如 Disk, S3）特別重要。

```{code-block} python
:emphasize-lines: 10
from autocrud.types import IMigration

class UserMigration(IMigration):
    schema_version = "v2"
    
    def migrate(self, data, old_version):
        # 處理資料升級
        return data

autocrud.add_model(User, migration=UserMigration())
```

```{seealso}
關於 Schema Migration 的詳細運作機制與完整範例，請參考 [Schema Migration](resource_manager.md#schema-migration) 章節。
```

### 索引欄位 (`indexed_fields`)

指定哪些欄位需要建立索引，以優化查詢效能。支援指定欄位名稱或路徑。

```{code-block} python
:emphasize-lines: 4
# 為 email 和 age 欄位建立索引
autocrud.add_model(
    User, 
    indexed_fields=["email", "age"]
)
```

```{seealso}
關於索引欄位的詳細說明與查詢方式，請參考 [Data Attribute Index](resource_manager.md#data-attribute-index) 章節。
```

### 事件處理 (`event_handlers`)

AutoCRUD 提供了強大的事件驅動機制，允許你在資源操作的各個階段（如建立前、更新後、失敗時）插入自定義邏輯。這對於實作審計日誌（Audit Log）、通知系統、資料驗證或副作用處理非常有用。

你可以透過 `event_handlers` 參數為特定模型註冊一個或多個事件處理器。

#### 使用 Fluent API (推薦)

AutoCRUD 提供了一個便捷的 `do` 函數，讓你以鍊式調用的方式快速註冊事件處理器，無需定義額外的類別。

```{code-block} python
:emphasize-lines: 1, 8-12
from autocrud.resource_manager.events import do
from autocrud.types import ResourceAction, EventContext

def log_creation(context: EventContext):
    print(f"User {context.user} is creating resource {context.resource_name}")

# 註冊事件處理器
handlers = (
    do(log_creation).before(ResourceAction.create)
    .do(lambda ctx: print("Created successfully!"))
    .on_success(ResourceAction.create)
)

autocrud.add_model(User, event_handlers=handlers)
```

#### 實作 IEventHandler 介面

對於更複雜的邏輯，你可以實作 `IEventHandler` 介面。你需要實作 `is_supported` 來決定是否處理該事件，以及 `handle_event` 來執行實際邏輯。

```{code-block} python
from autocrud.types import IEventHandler, EventContext, ResourceAction

class AuditLogHandler(IEventHandler):
    def is_supported(self, context: EventContext) -> bool:
        # 只處理寫入操作 (Create, Update, Delete, etc.)
        return context.action in ResourceAction.write

    def handle_event(self, context: EventContext) -> None:
        # 記錄操作日誌
        print(f"[{context.phase}] {context.action.name} by {context.user}")

autocrud.add_model(User, event_handlers=[AuditLogHandler()])
```

#### 事件階段 (Phases)

每個操作都會經歷以下階段：

- **before**: 操作執行前。可用於驗證或修改輸入資料。
- **after**: 操作執行後（無論成功失敗）。可用於清理資源。
- **on_success**: 操作成功完成後。可用於發送通知。
- **on_failure**: 操作發生錯誤時。可用於錯誤記錄。

#### 事件上下文 (EventContext)

`handle_event` 接收的 `context` 物件包含了當前操作的所有資訊：

- `action`: 當前操作類型 (ResourceAction.create, update, delete...)
- `phase`: 當前階段 (before, on_success...)
- `user`: 操作使用者
- `now`: 操作時間
- `resource_name`: 資源名稱
- `data`: (僅 Create/Update) 寫入的資料
- `resource_id`: (僅 Get/Update/Delete) 目標資源 ID
- `info`: (僅 on_success) 操作完成後的資源 metadata

```{seealso}
更多關於事件處理的詳細測試範例，可參考 `tests/test_event_handlers.py`。
```

### 資料編碼 (`encoding`)

為特定模型指定資料序列化格式，可覆蓋全域設定。

```{code-block} python
:emphasize-lines: 3
from autocrud.resource_manager.basic import Encoding

autocrud.add_model(User, encoding=Encoding.msgpack)
```

```{seealso}
關於支援的編碼格式詳細說明，請參考 [初始化設定 - 資料編碼](#encoding) 章節。
```

### 預設狀態 (`default_status`)

設定新建立資源的預設版本狀態。

```{code-block} python
:emphasize-lines: 4
from autocrud.types import RevisionStatus

# 新增的資源預設為草稿狀態
autocrud.add_model(User, default_status=RevisionStatus.draft)
```

### 預設使用者與時間 (`default_user` & `default_now`)

為特定模型設定預設的建立者與時間生成函數，優先級高於全域設定。

```{code-block} python
:emphasize-lines: 3-4
autocrud.add_model(
    User,
    default_user="system_bot",
    default_now=lambda: datetime.now(timezone.utc)
)
```
```{seealso}
關於預設使用者與時間詳細說明，請參考 [初始化設定 - 預設使用者與時間](#default-user-default-now) 章節。
```

### 自訂 ID 生成器 (`id_generator`)

預設使用 UUID4 生成資源 ID。你可以傳入一個無參數的函數來自訂 ID 生成邏輯。

```{code-block} python
:emphasize-lines: 3-4, 6
import time

def timestamp_id():
    return f"user_{int(time.time())}"

autocrud.add_model(User, id_generator=timestamp_id)
```

---

## 💾 備份與還原 (Backup & Restore)

AutoCRUD 內建了強大的資料備份與還原機制，支援將所有資料（包含歷史版本）匯出為 tar 檔案。

### 匯出資料 (Dump)

```python
# 將所有資料備份到檔案
with open("backup.tar", "wb") as f:
    autocrud.dump(f)
```

### 匯入資料 (Load)

```python
# 從備份檔案還原資料
# 注意：必須先註冊好相同的模型 (add_model)
with open("backup.tar", "rb") as f:
    autocrud.load(f)
```

這在環境遷移（如從開發環境遷移到正式環境）或災難復原時非常有用。

---

## Storage

AutoCRUD 的儲存層採用了 **Metadata** 與 **Payload** 分離的設計架構，這使得系統能夠同時兼顧高效的查詢性能與大規模資料的儲存需求。

### 核心架構

#### 1. Meta Store (元資料儲存)

負責管理資源的 Metadata（如 ID、建立時間、狀態、索引欄位等）。這層主要處理查詢、排序、分頁與權限檢查。

- **特性**: 高效查詢、多欄位索引。
- **技術**: 通常使用 RDBMS (PostgreSQL, SQLite) 或 Redis。
- **用途**: 快速列表、篩選資源、權限驗證。

#### 2. Resource Store (資源本體儲存)

負責儲存資源的實際內容（Payload）及其歷史版本。每次更新都會產生新的版本快照。

- **特性**: 大容量儲存、版本控制、Key-Value 存取。
- **技術**: 通常使用 Object Storage (S3, MinIO) 或本地檔案系統。
- **用途**: 儲存完整資料、檔案備份、版本回溯與還原。

### 設計理念

透過將 Metadata 與 Payload 分離，AutoCRUD 能夠靈活組合不同的儲存後端。例如，你可以使用 Redis 來處理極速的列表查詢，同時使用 S3 來廉價且安全地儲存海量的歷史版本資料。

當你執行 CRUD 操作時，AutoCRUD 會自動協調兩者：
- **建立/更新**: Meta Store 記錄索引與狀態，Resource Store 儲存資料快照。
- **查詢列表**: 僅存取 Meta Store，速度極快。
- **讀取詳情**: 先從 Meta Store 確認權限與位置，再從 Resource Store 撈取資料。

### 技術選型

你可以透過 `storage_factory` 參數來注入不同的儲存組合。AutoCRUD 內建了多種 Factory，也支援自定義。

#### 內建 Factory

- **[MemoryStorageFactory](#autocrud.resource_manager.storage_factory.MemoryStorageFactory)** (預設): 全記憶體儲存，適合測試。
- **[DiskStorageFactory](#autocrud.resource_manager.storage_factory.DiskStorageFactory)**: 本地磁碟儲存，適合單機持久化。

```python
from autocrud import AutoCRUD, DiskStorageFactory
from pathlib import Path

storage = DiskStorageFactory(rootdir=Path("./data"))
autocrud = AutoCRUD(storage_factory=storage)
```

```{seealso}
- [`autocrud.resource_manager.storage_factory.MemoryStorageFactory`](#autocrud.resource_manager.storage_factory.MemoryStorageFactory)
- [`autocrud.resource_manager.storage_factory.DiskStorageFactory`](#autocrud.resource_manager.storage_factory.DiskStorageFactory)
```

#### 自定義 Factory

若要使用進階的 Meta Store (如 Redis, SQLite) 或 Resource Store (如 S3)，你需要實作 `IStorageFactory` 介面，並在 `build` 方法中回傳 `SimpleStorage` 組合。

```{code-block} python
:emphasize-lines: 7-13
from autocrud import IStorageFactory, AutoCRUD
from autocrud.resource_manager.core import SimpleStorage
# 引入你需要的 Store
from autocrud.resource_manager.meta_store.redis import RedisMetaStore
from autocrud.resource_manager.resource_store.s3 import S3ResourceStore

class MyCustomStorageFactory(IStorageFactory):
    def build(self, model_name: str):
        # 在這裡組合你想要的 Meta Store 與 Resource Store
        return SimpleStorage(
            meta_store=RedisMetaStore(redis_url="redis://localhost:6379"),
            resource_store=S3ResourceStore(bucket="my-bucket")
        )

autocrud = AutoCRUD(storage_factory=MyCustomStorageFactory())
```

```{seealso}
- [`autocrud.resource_manager.storage_factory.IStorageFactory`](#autocrud.resource_manager.storage_factory.IStorageFactory)
- [`autocrud.resource_manager.core.SimpleStorage`](#autocrud.resource_manager.core.SimpleStorage)
```

以下是各類 Store 的詳細介紹與初始化範例，你可以參考這些範例來實作你的 `build` 方法。

### Meta Store

Meta Store 主要負責資源的索引、查詢、狀態控管。  
常見技術：PostgreSQL、SQLite、Redis  
支援：多欄位索引、複雜查詢、分頁、排序、權限審計

```{note}
每種 Meta Store 都實作了統一的介面（`IMetaStore`），可根據需求靈活替換或組合使用。
```

AutoCRUD 目前支援以下 Meta Store 實作：

#### **MemoryMetaStore**  
  - 完全以 Python dict 實作，資料存於記憶體，序列化採用 msgspec。  
  - 適合測試、單機快取、暫存用途，速度極快但資料不持久。
  - 支援基本 CRUD 與搜尋、排序，重啟後資料會消失。

  ```python
  from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
  
  meta_store = MemoryMetaStore(encoding="msgpack")
  ```

```{seealso}
[`autocrud.resource_manager.meta_store.simple.MemoryMetaStore`](#autocrud.resource_manager.meta_store.simple.MemoryMetaStore)
```

#### **DiskMetaStore**  
  - 每筆 metadata 以獨立檔案儲存於指定目錄，序列化採用 msgspec。  
  - 適合小型專案或本地持久化，無需資料庫安裝，易於備份與搬移。
  - 檔案命名以 resource_id 為主，支援基本搜尋與批次同步。

  ```python
  from pathlib import Path
  from autocrud.resource_manager.meta_store.simple import DiskMetaStore
  
  meta_store = DiskMetaStore(
      rootdir=Path("./data/meta"), 
      encoding="msgpack"
  )
  ```

```{seealso}
[`autocrud.resource_manager.meta_store.simple.DiskMetaStore`](#autocrud.resource_manager.meta_store.simple.DiskMetaStore)
```

#### **SqliteMetaStore**  
  - 以 SQLite 資料庫儲存，metadata 以 BLOB 欄位存放，並額外記錄索引欄位（indexed_data）。  
  - 支援 SQL 層級複雜查詢、排序、分頁，適合單機或嵌入式應用。
  - 支援批次寫入（save_many），資料持久且易於備份。

  ```python
  from pathlib import Path
  from autocrud.resource_manager.meta_store.sqlite3 import FileSqliteMetaStore
  
  meta_store = FileSqliteMetaStore(
      db_filepath=Path("./data/meta.db"),
      encoding="msgpack"
  )
  ```
```{seealso}
[`autocrud.resource_manager.meta_store.sqlite3.FileSqliteMetaStore`](#autocrud.resource_manager.meta_store.sqlite3.FileSqliteMetaStore)
[`autocrud.resource_manager.meta_store.sqlite3.MemorySqliteMetaStore`](#autocrud.resource_manager.meta_store.sqlite3.MemorySqliteMetaStore)
```

#### **PostgresMetaStore**
  - 以 PostgreSQL 資料庫儲存，metadata 以 JSONB 欄位存放，並支援 GIN 索引以優化查詢。
  - 適合正式環境、高併發、需強一致性與複雜查詢的場景。
  - 支援完整的 SQL 查詢能力與交易保護。

  ```python
  from autocrud.resource_manager.meta_store.postgres import PostgresMetaStore

  meta_store = PostgresMetaStore(
      pg_dsn="postgresql://user:password@localhost:5432/dbname",
      encoding="msgpack"
  )
  ```
```{seealso}
[`autocrud.resource_manager.meta_store.postgres.PostgresMetaStore`](#autocrud.resource_manager.meta_store.postgres.PostgresMetaStore)
```


#### **RedisMetaStore**  
  - 以 Redis 為後端，所有 metadata 以 key-value 方式儲存，序列化採用 msgspec。  
  - 適合高併發、分散式快取場景，支援批次同步（get_then_delete）與快速查詢。
  - 資料持久性依賴 Redis 設定，適合暫存或同步到慢速存儲。

  ```python
  from autocrud.resource_manager.meta_store.redis import RedisMetaStore
  
  meta_store = RedisMetaStore(
      redis_url="redis://localhost:6379/0",
      encoding="msgpack",
      prefix="my_app"
  )
  ```
```{seealso}
[`autocrud.resource_manager.meta_store.redis.RedisMetaStore`](#autocrud.resource_manager.meta_store.redis.RedisMetaStore)
```


#### **FastSlowMetaStore**  
  - **架構**: 結合「快速層」(Fast Store, 如 Redis) 與「慢速層」(Slow Store, 如 PostgreSQL) 的混合儲存策略。
  - **寫入策略**: 資料優先寫入快速層，立即返回，確保高併發寫入效能。
  - **同步機制**: 內建背景執行緒 (Background Thread)，定期將快速層的資料**批次**遷移至慢速層。這利用了慢速層（如 RDBMS）**批次寫入遠快於多次單筆寫入**的特性，大幅提升持久化效率。
  - **讀取策略**: 優先讀取快速層，若未命中則回退至慢速層。
  - **搜尋**: 執行搜尋時會自動觸發同步，確保慢速層的索引資料是最新的。
  - **適用場景**: 高頻寫入 (Write-Heavy) 且需持久保存的應用，如 Log 收集、即時數據分析。

  ```python
  from autocrud.resource_manager.meta_store.fast_slow import FastSlowMetaStore
  from autocrud.resource_manager.meta_store.redis import RedisMetaStore
  from autocrud.resource_manager.meta_store.postgres import PostgresMetaStore
  
  meta_store = FastSlowMetaStore(
      fast_store=RedisMetaStore(redis_url="redis://localhost:6379/0"),
      slow_store=PostgresMetaStore(pg_dsn="postgresql://user:password@localhost:5432/dbname"),
      sync_interval=1  # 每秒同步一次
  )
  ```
```{seealso}
[`autocrud.resource_manager.meta_store.fast_slow.FastSlowMetaStore`](#autocrud.resource_manager.meta_store.fast_slow.FastSlowMetaStore)
```

### Resource Store

Resource Store 主要負責資源本體的儲存與版本管理。  
常見技術：S3、Disk、本地檔案系統  
支援：多版本資料、回溯、還原、大型檔案管理

```{note}
每種 Resource Store 都實作了統一的介面（`IResourceStore`），可根據需求靈活替換或組合使用。
```
AutoCRUD 目前支援以下 Resource Store 實作：

#### **MemoryResourceStore**  
  - 完全以 Python dict 實作，所有資料與版本都存於記憶體。  
  - 適合測試、單機快取、暫存用途，速度極快但資料不持久。
  - 支援多版本、即時回溯，重啟後資料會消失。

  ```python
  from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
  
  res_store = MemoryResourceStore(encoding="msgpack")
  ```
```{seealso}
[`autocrud.resource_manager.resource_store.simple.MemoryResourceStore`](#autocrud.resource_manager.resource_store.simple.MemoryResourceStore)
```


#### **DiskResourceStore**  
  - 每個資源版本以獨立檔案儲存於本地目錄，結構化目錄管理所有版本。  
  - 適合小型專案、本地持久化，易於備份與搬移。
  - 支援多版本、回溯、還原，檔案命名與目錄結構依照 resource_id/revision_id/schema_version 分類。

  ```python
  from pathlib import Path
  from autocrud.resource_manager.resource_store.simple import DiskResourceStore
  
  res_store = DiskResourceStore(
      rootdir=Path("./data/resources"),
      encoding="msgpack"
  )
  ```
```{seealso}
[`autocrud.resource_manager.resource_store.simple.DiskResourceStore`](#autocrud.resource_manager.resource_store.simple.DiskResourceStore)
```



#### **S3ResourceStore**  
  - 以 S3 或 MinIO 為後端，所有版本資料與資訊分別存於 S3 物件，並以 UID 索引。  
  - 適合雲端、大型資料、分散式儲存，支援高可用性與備份。
  - 支援多版本、回溯、還原，索引結構設計可快速查找任意版本。

  ```python
  from autocrud.resource_manager.resource_store.s3 import S3ResourceStore
  
  res_store = S3ResourceStore(
      endpoint_url="http://minio:9000",
      bucket="my-bucket",
      prefix="resources/",
      encoding="msgpack",
      access_key_id="minioadmin",
      secret_access_key="minioadmin"
  )
  ```
```{seealso}
[`autocrud.resource_manager.resource_store.s3.S3ResourceStore`](#autocrud.resource_manager.resource_store.s3.S3ResourceStore)
```

---

## 🔒 進階功能

### 權限控制 (Permission)

你可以透過 `admin` 參數快速設定根管理員，或實作 `IPermissionChecker` 進行細粒度的權限控制。

```python
# 啟用 RBAC 並設定管理員
autocrud = AutoCRUD(admin="admin_user_id")
```

### 資料遷移 (Migration)

當模型結構改變時（例如新增欄位），可以透過實作 `IMigration` 介面來處理舊資料的升級。

```python
class UserMigration(IMigration):
    schema_version = "v2"
    
    def migrate(self, data, old_version):
        # 處理資料轉換邏輯
        if "new_field" not in data:
            data["new_field"] = "default_value"
        return data

autocrud.add_model(User, migration=UserMigration())
```

---

## 📑 OpenAPI 整合 (OpenAPI Integration)

為了讓 FastAPI 的自動文件 (Swagger UI / ReDoc) 能夠正確顯示 AutoCRUD 生成的動態模型與 `msgspec` 結構，你需要顯式呼叫 `openapi` 方法。

### 基本用法

在 `apply(app)` 之後呼叫 `openapi(app)`：

```{code-block} python
:emphasize-lines: 6
# ... 註冊模型 ...

autocrud.apply(app)

# 注入 OpenAPI Schema
autocrud.openapi(app)
```

這會修正 FastAPI 預設無法識別 `msgspec.Struct` 或動態生成類別的問題，確保 API 文件完整且正確。

### 包含額外模型

如果你有自定義的 `msgspec` 模型需要在 API 文件中顯示，可以透過 `structs` 參數傳入：

```{code-block} python
:emphasize-lines: 5
class ErrorResponse(msgspec.Struct):
    error: str
    detail: str

autocrud.openapi(app, structs=[ErrorResponse])
```

---

## 🚦 自動生成的路由列表 (Auto FastAPI Routes)

當你在 AutoCRUD 註冊一個 resource（例如 TodoItem、User），系統會自動生成一組 RESTful API 路由。這些路由會以你提供的 resource 名稱為基礎，並自動處理該 resource 的各種操作。

### 路由格式說明

- `[resource]` 代表你註冊的資源名稱（如 todo-item、user）
- `{resource_id}` 代表該資源的唯一識別碼
- `{revision_id}` 代表版本識別碼

### 路由列表

| 方法 | 路徑 | 功能說明 |
|------|-------------------------------|-----------------------------|
| POST   | /[resource]                        | 新增一筆 [resource] |
| GET    | /[resource]/data                   | 取得所有 [resource] 的資料 |
| GET    | /[resource]/meta                   | 取得所有 [resource] 的 metadata |
| GET    | /[resource]/revision-info          | 取得所有 [resource] 的目前版本資訊 |
| GET    | /[resource]/full                   | 取得所有 [resource] 的完整資訊 |
| GET    | /[resource]/count                  | 取得 [resource] 的數量 |
| GET    | /[resource]/{resource_id}/meta     | 取得指定 [resource] 的 metadata |
| GET    | /[resource]/{resource_id}/revision-info | 取得指定 [resource] 的版本資訊 |
| GET    | /[resource]/{resource_id}/full     | 取得指定 [resource] 的完整資訊 |
| GET    | /[resource]/{resource_id}/revision-list | 取得指定 [resource] 的歷史版本 |
| GET    | /[resource]/{resource_id}/data     | 取得指定 [resource] 的資料 |
| PUT    | /[resource]/{resource_id}          | 更新指定 [resource]（全量更新）|
| PATCH  | /[resource]/{resource_id}          | 局部更新指定 [resource] |
| DELETE | /[resource]/{resource_id}          | 刪除指定 [resource]（軟刪除）|
| POST   | /[resource]/{resource_id}/switch/{revision_id} | 切換到指定版本 |
| POST   | /[resource]/{resource_id}/restore  | 還原指定 [resource] |

### 使用範例

假設你註冊的 resource 是 `todo-item`，則會自動生成如下路由：

- `POST /todo-item` 新增待辦事項
- `GET /todo-item/{id}/data` 取得指定待辦事項資料
- `PATCH /todo-item/{id}` 局部更新
- `DELETE /todo-item/{id}` 刪除
- ...等

你只需提供 resource 結構，AutoCRUD 會自動處理資料的 CRUD、版本、還原等操作，讓 API 開發更簡單。

---

## 原始碼

```{eval-rst}
.. autoclass:: autocrud.crud.core.AutoCRUD
   :members:
```

```{eval-rst}
.. automodule:: autocrud.resource_manager.storage_factory
   :members:
```
```{eval-rst}
.. autoclass:: autocrud.resource_manager.core.SimpleStorage
   :members:
```
```{eval-rst}
.. automodule:: autocrud.resource_manager.meta_store.simple
   :members:
```

```{eval-rst}
.. automodule:: autocrud.resource_manager.meta_store.sqlite3
   :members:
```

```{eval-rst}
.. automodule:: autocrud.resource_manager.meta_store.postgres
   :members:
```

```{eval-rst}
.. automodule:: autocrud.resource_manager.meta_store.redis
   :members:
```

```{eval-rst}
.. automodule:: autocrud.resource_manager.meta_store.fast_slow
   :members:
```

```{eval-rst}
.. automodule:: autocrud.resource_manager.resource_store.simple
   :members:
```

```{eval-rst}
.. autoclass:: autocrud.resource_manager.resource_store.s3.S3ResourceStore
   :members:
```
