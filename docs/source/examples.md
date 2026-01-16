# 🚀 快速開始

10 分鐘打造完整的 RESTful API 系統。

## 安裝

```{termynal}
$ pip install autocrud
-->
```

## 核心概念

AutoCRUD 讓你只需定義數據模型，就能自動生成完整的 CRUD API：

- ✅ **使用 `msgspec.Struct`** 定義數據模型（不是 Pydantic）
- ✅ **自動生成** RESTful API 端點
- ✅ **內建版本控制** 追蹤所有變更
- ✅ **支援搜尋與索引** 強大的查詢功能
- ✅ **Message Queue 整合** 處理異步任務
- ✅ **Binary 檔案處理** 自動優化儲存

## 第一個 API：RPG 遊戲系統

讓我們建立一個完整的 RPG 遊戲管理系統，展示 AutoCRUD 的核心功能。

### 1️⃣ 定義數據模型

```python
from msgspec import Struct
from enum import Enum
from typing import Optional
import datetime as dt

class CharacterClass(Enum):
    """職業系統"""
    WARRIOR = "⚔️ 戰士"
    MAGE = "🔮 法師"
    ARCHER = "🏹 弓箭手"

class Character(Struct):
    """遊戲角色"""
    name: str
    character_class: CharacterClass
    level: int = 1
    hp: int = 100
    mp: int = 50
    attack: int = 10
    defense: int = 5
    experience: int = 0
    gold: int = 100
    created_at: dt.datetime = dt.datetime.now()

class Guild(Struct):
    """遊戲公會"""
    name: str
    description: str
    leader: str
    member_count: int = 1
    level: int = 1
    treasury: int = 1000
    founded_at: dt.datetime = dt.datetime.now()
```

### 2️⃣ 創建 API

```python
from fastapi import FastAPI
from autocrud import AutoCRUD
import uvicorn

# 創建 AutoCRUD 實例
crud = AutoCRUD()

# 註冊模型（支援搜尋索引）
crud.add_model(Character, indexed_fields=[("level", int), ("name", str)])
crud.add_model(Guild)

# 創建 FastAPI 應用
app = FastAPI(
    title="⚔️ RPG 遊戲管理系統",
    description="使用 AutoCRUD 構建的完整遊戲 API"
)

# 應用 AutoCRUD 到 FastAPI
crud.apply(app)

# 啟動服務器
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### 3️⃣ 啟動並測試

```bash
python main.py
```

訪問 **http://localhost:8000/docs** 查看自動生成的 API 文檔。

## 自動生成的端點

每個模型自動產生以下端點：

### Character API
- `POST /character` - 創建角色
- `GET /character/{id}/full` - 完整資訊（含數據與元數據）
- `GET /character/{id}/meta` - 僅元數據
- `GET /character/{id}/revision-info` - 版本資訊
- `GET /character/data` - 列出所有角色數據（支援搜尋與過濾）
- `GET /character/full` - 列出所有完整資訊
- `GET /character/meta` - 列出所有元數據
- `PATCH /character/{id}` - JSON Patch 更新
- `DELETE /character/{id}` - 軟刪除

### Guild API
- `POST /guild` - 創建公會
- `GET /guild/{id}/full` - 完整資訊
- `GET /guild/data` - 列出所有公會數據
- `PATCH /guild/{id}` - 更新公會
- `DELETE /guild/{id}` - 刪除公會

➡️ *[完整路由說明](auto_routes.md)*

## 使用 API 範例

### 創建角色

```bash
curl -X POST "http://localhost:8000/character" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "AutoCRUD 大神",
    "character_class": "⚔️ 戰士",
    "level": 99,
    "hp": 9999,
    "attack": 500,
    "defense": 300,
    "gold": 1000000
  }'
```

回應：
```json
{
  "resource_id": "chr_abc123",
  "revision_id": "rev_001",
  "status": "stable"
}
```

### 查詢角色

```bash
# 取得角色完整資訊
curl "http://localhost:8000/character/chr_abc123/full"

# 使用 QB (Query Builder) 搜尋高等級角色
curl -G "http://localhost:8000/character/data" \
  --data-urlencode "qb=QB['level'].gte(50)"

# 使用 data_conditions 搜尋（JSON 格式）
curl "http://localhost:8000/character/data?data_conditions=[{\"field_path\":\"level\",\"operator\":\"gte\",\"value\":50}]"

# 列出所有角色
curl "http://localhost:8000/character/data"
```

### 更新角色（JSON Patch）

```bash
curl -X PATCH "http://localhost:8000/character/chr_abc123" \
  -H "Content-Type: application/json" \
  -d '[
    {"op": "replace", "path": "/level", "value": 100},
    {"op": "add", "path": "/gold", "value": 5000}
  ]'
```

## 進階功能

### 📦 Binary 檔案處理

AutoCRUD 自動優化 Binary 類型欄位，避免重複儲存：

```python
from autocrud.types import Binary

class Equipment(Struct):
    name: str
    attack_bonus: int
    icon: Optional[Binary] = None  # 自動去重複化儲存

# 使用
equipment = Equipment(
    name="神劍",
    attack_bonus=100,
    icon=Binary(data=image_bytes)  # 自動計算 hash 並儲存
)
```

### 🔍 進階搜尋與 QueryBuilder (QB)

#### 建立索引

**重要**：使用查詢功能前，必須先為欄位建立索引：

```python
from autocrud.query import QB  # QueryBuilder

crud.add_model(
    Character, 
    indexed_fields=[
        ("level", int),              # 等級索引
        ("name", str),               # 名稱索引
        ("gold", int),               # 金幣索引
        ("guild_name", str | None),  # 公會名稱索引（可選類型）
        ("character_class", CharacterClass),  # 職業索引
    ]
)
```

#### QB 查詢語法

AutoCRUD 支援強大的 QB (Query Builder) 表達式，讓你能以直覺的方式建立查詢條件：

```bash
# 基本查詢
curl -G "http://localhost:8000/character/data" \
  --data-urlencode "qb=QB['level'].gte(50)"

# 複雜條件 (AND)
curl -G "http://localhost:8000/character/data" \
  --data-urlencode "qb=QB['level'].gte(50) & QB['character_class'].eq('⚔️ 戰士')"

# 排序與分頁
curl -G "http://localhost:8000/character/data" \
  --data-urlencode "qb=QB['level'].gte(1).sort('-level').limit(10)"

# 字串搜尋
curl -G "http://localhost:8000/character/data" \
  --data-urlencode "qb=QB['name'].contains('大神')"
```

#### QueryBuilder (QB) 進階查詢

通過 ResourceManager 使用 QB 進行更強大的查詢：

```python
from autocrud.query import QB

# 取得 ResourceManager
char_mgr = crud.get_resource_manager(Character)

# 1. 基本查詢
metas = char_mgr.search_resources(QB["level"].gte(50).limit(10))
for meta in metas:
    resource = char_mgr.get(meta.resource_id)
    print(f"{resource.data.name}: Lv.{resource.data.level}")

# 2. 複雜條件 (AND)
query = (
    QB["level"].between(20, 80) & 
    QB["guild_name"].is_not_null()
).limit(5)
metas = char_mgr.search_resources(query)

# 3. 使用 filter 方法（更可讀）
query = QB["gold"].gt(100000).filter(
    QB["character_class"].eq(CharacterClass.WARRIOR)
).limit(5)

# 4. OR 查詢
query = QB["level"].gte(80) | QB["gold"].gte(500000)

# 5. 排序
query = QB["level"].gte(1).sort("-level").limit(3)  # 降序
query = QB["gold"].gte(1).sort(QB["gold"].desc()).limit(3)  # 使用方法

# 6. 分頁
query = QB["status"].eq("active").page(1, 20)  # 第1頁，每頁20個

# 7. 字串查詢
query = QB["name"].contains("大神")
query = QB["guild_name"].in_(["公會A", "公會B"])

# 8. 元數據查詢
import datetime as dt
query = QB.created_time().gte(
    dt.datetime.now() - dt.timedelta(hours=1)
).sort(QB.created_time().desc())

# 9. 排除條件
query = QB["level"].gte(1).exclude(
    QB["guild_name"].eq("新手村")
).sort("-level")

# 10. 取第一筆
query = QB["level"].gte(1).sort("-level").first()
```

#### QB 支援的操作

**比較操作**：
- `eq()` / `==` - 等於
- `ne()` / `!=` - 不等於
- `gt()` / `>` - 大於
- `gte()` / `>=` - 大於等於
- `lt()` / `<` - 小於
- `lte()` / `<=` - 小於等於
- `between(min, max)` - 範圍查詢

**字串操作**：
- `contains()` - 包含
- `starts_with()` - 開頭匹配
- `ends_with()` - 結尾匹配
- `regex()` - 正則表達式

**集合操作**：
- `in_(list)` - 在列表中
- `not_in(list)` - 不在列表中

**NULL 檢查**：
- `is_null()` - 是 NULL
- `is_not_null()` - 不是 NULL
- `has_value()` - 有值（is_not_null 別名）

**邏輯操作**：
- `&` - AND
- `|` - OR
- `~` - NOT
- `filter(*conditions)` - AND 多個條件
- `exclude(*conditions)` - 排除條件

**排序與分頁**：
- `sort(field)` - 排序（`"-field"` 降序，`"+field"` 升序）
- `order_by(field)` - sort 的別名
- `limit(n)` - 限制數量
- `offset(n)` - 偏移量
- `page(page, size)` - 分頁
- `first()` - 只取第一筆

**元數據欄位**：
- `QB.created_time()` - 創建時間
- `QB.updated_time()` - 更新時間
- `QB.resource_id()` - 資源 ID
- `QB.status()` - 狀態

### 📊 版本控制

每次修改自動創建新版本：

```python
# 取得版本歷史
GET /character/{id}/history

# 切換到特定版本
POST /character/{id}/switch
{
  "revision_id": "rev_001"
}
```

### 🎯 Message Queue（異步任務）

處理遊戲事件等異步任務：

```python
from autocrud.types import Job

class GameEventPayload(Struct):
    event_type: str
    character_name: str
    reward_gold: int = 0

class GameEvent(Job[GameEventPayload]):
    pass

def process_event(event_resource):
    """背景處理函數"""
    payload = event_resource.data.payload
    print(f"處理事件: {payload.event_type}")
    # 執行異步邏輯...

# 註冊 Job 模型
crud.add_model(GameEvent, job_handler=process_event)

# 啟動消費者
crud.get_resource_manager(GameEvent).start_consume(block=False)
```

### 💾 持久化儲存

使用磁碟儲存替代記憶體：

```python
from autocrud.resource_manager.storage_factory import DiskStorageFactory

crud = AutoCRUD(
    storage_factory=DiskStorageFactory(rootdir="./game_data")
)
```

## 透過 ResourceManager 直接操作

除了 HTTP API，也可以直接使用 `ResourceManager` 和 `QueryBuilder (QB)`：

```python
from autocrud import AutoCRUD
from autocrud.query import QB
import datetime as dt

crud = AutoCRUD()
crud.add_model(
    Character,
    indexed_fields=[
        ("level", int),
        ("name", str),
        ("gold", int),
        ("character_class", CharacterClass),
    ]
)

# 取得 ResourceManager
char_mgr = crud.get_resource_manager(Character)

# 創建資源
with char_mgr.meta_provide(user="admin", now=dt.datetime.now()):
    info = char_mgr.create(Character(
        name="測試角色",
        character_class=CharacterClass.WARRIOR
    ))
    
# 讀取資源
resource = char_mgr.get(info.resource_id)
print(resource.data.name)  # "測試角色"

# 更新資源
char_mgr.modify(info.resource_id, {"level": 10})

# 使用 QB 搜尋資源
query = QB["level"].gte(5).sort("-level").limit(10)
metas = char_mgr.search_resources(query)
for meta in metas:
    res = char_mgr.get(meta.resource_id)
    print(f"{res.data.name}: Lv.{res.data.level}")

# 複雜查詢
query = (
    QB["level"].between(10, 50) & 
    QB["character_class"].eq(CharacterClass.WARRIOR)
).sort("-gold").page(1, 20)
metas = char_mgr.search_resources(query)
```

➡️ *[ResourceManager 完整說明](resource_manager.md)*

## 完整範例

查看 `examples/rpg_game_api.py` 獲得完整的實作範例：

```bash
cd examples
python rpg_game_api.py
```

此範例包含：
- ⚔️ 完整的角色、公會、裝備系統
- 🎯 Message Queue 遊戲事件處理
- 📦 Binary 檔案（裝備圖標）處理
- 🔍 QueryBuilder (QB) 進階搜尋與索引（12個實用範例）
- 📊 版本控制與歷史追蹤
- 💾 支援記憶體與磁碟儲存

---
