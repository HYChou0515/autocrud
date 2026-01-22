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