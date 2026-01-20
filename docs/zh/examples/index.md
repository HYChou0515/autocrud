---
title: 範例集
description: AutoCRUD 的各種使用範例
---

# 範例集

這裡收集了 AutoCRUD 的各種使用範例，從基礎到進階應用。所有範例都可以在 [GitHub examples 目錄](https://github.com/HYChou0515/autocrud/tree/master/examples) 找到完整程式碼。

## ⭐ 完整範例：RPG 遊戲 API 系統

這是一個功能完整的 RPG 遊戲管理系統，展示 AutoCRUD 的所有核心功能。

### 功能特色

- ⚔️ **角色系統**：創建、查詢、升級遊戲角色
- 🏰 **公會管理**：管理公會和成員關係
- 🗡️ **裝備系統**：武器裝備的完整管理（包含二進位圖片）
- 🎯 **事件系統**：使用 Message Queue 處理異步遊戲事件
- 🔍 **QueryBuilder**：12+ 種查詢範例（排序、分頁、條件組合）
- 📖 **版本控制**：追蹤所有數據變更歷史
- 🚀 **自動 API**：完整的 OpenAPI 文檔

### 資料模型

```python
from msgspec import Struct
from enum import Enum
from autocrud.types import Binary

class CharacterClass(Enum):
    WARRIOR = "⚔️ 戰士"
    MAGE = "🔮 法師"
    ARCHER = "🏹 弓箭手"
    DATA_KEEPER = "💾 數據守護者"

class Character(Struct):
    """遊戲角色"""
    name: str
    character_class: CharacterClass
    level: int = 1
    hp: int = 100
    attack: int = 10
    defense: int = 5
    gold: int = 100
    guild_name: str | None = None
    special_ability: str | None = None

class Guild(Struct):
    """遊戲公會"""
    name: str
    description: str
    leader: str
    member_count: int = 1
    level: int = 1
    treasury: int = 1000

class Equipment(Struct):
    """遊戲裝備"""
    name: str
    rarity: ItemRarity
    attack_bonus: int = 0
    defense_bonus: int = 0
    icon: Binary | None = None  # 二進位圖片欄位
```

### 設定 AutoCRUD

```python
from autocrud import AutoCRUD
from autocrud.resource_manager.storage_factory import DiskStorageFactory
from autocrud.message_queue.simple import SimpleMessageQueueFactory

crud = AutoCRUD(
    storage_factory=DiskStorageFactory("./game_data"),
    message_queue_factory=SimpleMessageQueueFactory(),
)

# 註冊模型並指定索引欄位
crud.add_model(
    Character,
    indexed_fields=[
        ("level", int),
        ("guild_name", str | None),
        ("gold", int),
        ("character_class", CharacterClass),
    ]
)

crud.add_model(
    Guild,
    indexed_fields=[
        ("level", int),
        ("member_count", int),
    ]
)

crud.add_model(Equipment)
crud.add_model(GameEvent)  # Message Queue 事件
```

### QueryBuilder 使用範例

```python
from autocrud.query import QB

# 範例 1: 基本條件查詢
high_level = character_manager.search_resources(
    QB["level"].gte(50).limit(10)
)

# 範例 2: 複雜條件組合
mid_level_with_guild = character_manager.search_resources(
    (QB["level"].between(20, 80) & QB["guild_name"].is_not_null()).limit(5)
)

# 範例 3: OR 查詢
elite_players = character_manager.search_resources(
    (QB["level"].gte(80) | QB["gold"].gte(500000)).limit(5)
)

# 範例 4: 排序和分頁
top_players = character_manager.search_resources(
    QB["level"].gte(1).sort("-level").page(1, 10)
)

# 範例 5: 字串搜尋
search_name = character_manager.search_resources(
    QB["name"].contains("大").limit(5)
)

# 範例 6: IN 查詢
guild_members = character_manager.search_resources(
    QB["guild_name"].in_(["AutoCRUD 開發者聯盟", "API 法師學院"])
)
```

### Message Queue 事件處理

```python
from autocrud.types import Job

class GameEventPayload(Struct):
    event_type: GameEventType
    character_name: str
    description: str
    reward_gold: int = 0
    reward_exp: int = 0

class GameEvent(Job[GameEventPayload]):
    """遊戲事件任務（背景處理）"""
    pass

# 創建事件
event_manager.create(GameEvent(
    payload=GameEventPayload(
        event_type=GameEventType.LEVEL_UP,
        character_name="勇者小明",
        description="升級到 Lv.50",
        reward_gold=1000,
        reward_exp=5000,
    )
))

# 啟動背景處理
event_manager.start_consume(block=False)
```

### 啟動服務

```python
python examples/rpg_game_api.py
```

訪問：

- 📖 OpenAPI 文檔：`http://localhost:8000/docs`
- ⚔️ 角色 API：`GET /character/data`
- 🏰 公會 API：`GET /guild/data`
- 🗡️ 裝備 API：`GET /equipment/data`
- 🎯 事件 API：`GET /game-event/data`

### 完整程式碼

:octicons-mark-github-16: [examples/rpg_game_api.py](https://github.com/HYChou0515/autocrud/blob/master/examples/rpg_game_api.py)

---

## 其他實用範例

## 其他實用範例

### 快速開始範本

最簡單的 AutoCRUD 應用：

```python
from fastapi import FastAPI
from autocrud import AutoCRUD
from msgspec import Struct

class Item(Struct):
    name: str
    price: float

crud = AutoCRUD()
crud.add_model(Item)

app = FastAPI()
crud.apply(app)
```

運行後訪問 `http://localhost:8000/docs` 即可看到自動生成的 API 文檔。

### 版本控制範例

展示如何使用版本控制功能：

```python
# 創建初始版本
resource = manager.create(data)

# 修改草稿
manager.modify(resource.resource_id, {"price": 299})

# 發布為穩定版本
manager.switch_to_stable(resource.resource_id)

# 創建新版本
new_version = manager.update(resource.resource_id, new_data)
```

:octicons-mark-github-16: [examples/cute_pet_versioning_demo.py](https://github.com/HYChou0515/autocrud/blob/master/examples/cute_pet_versioning_demo.py)

### 權限控制範例

實作基於角色的權限控制：

```python
from autocrud.permission import RBACPermissionChecker

permission_checker = RBACPermissionChecker({
    "admin": {"read", "create", "update", "delete"},
    "editor": {"read", "create", "update"},
    "viewer": {"read"}
})

crud = AutoCRUD(permission_checker=permission_checker)
```

:octicons-mark-github-16: [examples/advanced_permission_example.py](https://github.com/HYChou0515/autocrud/blob/master/examples/advanced_permission_example.py)

### 資料搜尋範例

使用 QueryBuilder 進行複雜搜尋：

```python
from autocrud.query import QB

# 複雜條件查詢
results = manager.search_resources(
    QB["price"].between(100, 500) & 
    QB["category"].eq("electronics") &
    QB["stock"].gt(0)
)
```

:octicons-mark-github-16: [examples/data_search.py](https://github.com/HYChou0515/autocrud/blob/master/examples/data_search.py)

### Schema 升級範例

處理資料模型演化：

```python
# 定義遷移函數
def migrate_v1_to_v2(data: dict) -> dict:
    # 添加新欄位
    data["new_field"] = "default_value"
    return data

# 註冊遷移
crud.add_model(
    MyModel,
    migration={"1": ("2", migrate_v1_to_v2)}
)
```

:octicons-mark-github-16: [examples/schema_upgrade.py](https://github.com/HYChou0515/autocrud/blob/master/examples/schema_upgrade.py)

### 備份與還原

```python
from autocrud.util.backup import backup_all, restore_all

# 備份所有資料
backup_all(crud, output_path="./backup.tar.gz")

# 還原資料
restore_all(crud, input_path="./backup.tar.gz")
```

:octicons-mark-github-16: [examples/backup.py](https://github.com/HYChou0515/autocrud/blob/master/examples/backup.py)

### Message Queue 範例

使用 RabbitMQ 處理異步任務：

```python
from autocrud.message_queue.rabbitmq import RabbitMQMessageQueueFactory

crud = AutoCRUD(
    message_queue_factory=RabbitMQMessageQueueFactory(
        amqp_url="amqp://guest:guest@localhost:5672"
    )
)
```

:octicons-mark-github-16: [examples/rabbitmq_retry_example.py](https://github.com/HYChou0515/autocrud/blob/master/examples/rabbitmq_retry_example.py)

## 程式碼片段

### 帶索引的模型

支援搜尋與過濾：

```python
crud.add_model(
    Product,
    indexed_fields=[
        ("price", float),
        ("category", str),
        ("stock", int),
    ]
)
```

### 事件處理

```python
from autocrud.types import IEventHandler, EventContext

class LoggingHandler(IEventHandler):
    def after_create(self, ctx: EventContext, resource):
        print(f"Created: {resource.resource_id}")
    
    def after_update(self, ctx: EventContext, resource):
        print(f"Updated: {resource.resource_id}")

crud = AutoCRUD(event_handlers=[LoggingHandler()])
```

### 自定義預設值函數

```python
def get_current_user():
    # 從請求上下文獲取當前用戶
    return "current_user"

crud.add_model(
    Article,
    default_user_function=get_current_user
)
```

:octicons-mark-github-16: [examples/default_user_function_example.py](https://github.com/HYChou0515/autocrud/blob/master/examples/default_user_function_example.py)

:octicons-mark-github-16: [examples/default_user_function_example.py](https://github.com/HYChou0515/autocrud/blob/master/examples/default_user_function_example.py)

## 更多資源

### 完整範例庫

所有範例的完整程式碼都可以在 GitHub 上找到：

:octicons-mark-github-16: [GitHub - autocrud/examples](https://github.com/HYChou0515/autocrud/tree/master/examples)

### 進階主題

- [效能測試](../benchmarks/index.md) - 查看 AutoCRUD 的效能基準
- [核心概念](../core-concepts/architecture.md) - 深入了解架構設計
- [API 參考](../reference/autocrud.md) - 完整的 API 文檔

### 社群範例

歡迎貢獻你的範例！提交 Pull Request 到：

:octicons-mark-github-16: [貢獻指南](https://github.com/HYChou0515/autocrud/blob/master/CONTRIBUTING.md)