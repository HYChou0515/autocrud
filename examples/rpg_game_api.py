#!/usr/bin/env python3
"""⚔️ RPG 遊戲 API 系統 - AutoCRUD + FastAPI 完整示範 🛡️

這個範例展示：
- 完整的 AutoCRUD + FastAPI 集成
- Schema 演化和版本控制
- 預填遊戲數據
- 可直接使用的 OpenAPI 文檔
- Message Queue 異步任務處理（遊戲事件系統）

運行方式：
    python rpg_system.py

然後訪問：
    http://localhost:8000/docs - OpenAPI 文檔
    http://localhost:8000/character - 角色 API
    http://localhost:8000/guild - 公會 API
    http://localhost:8000/game-event - 遊戲事件任務 API
"""

import datetime as dt
from msgspec import Struct
from enum import Enum
from typing import Optional
import time
import random

import uvicorn
from fastapi import FastAPI

from autocrud import AutoCRUD
from autocrud.crud.route_templates.blob import BlobRouteTemplate
from autocrud.types import Binary, Job, Resource
from autocrud.crud.route_templates.graphql import GraphQLRouteTemplate
from autocrud.crud.route_templates.migrate import MigrateRouteTemplate
from autocrud.resource_manager.storage_factory import DiskStorageFactory
from autocrud.message_queue.simple import SimpleMessageQueueFactory
from autocrud.message_queue.rabbitmq import RabbitMQMessageQueueFactory


class CharacterClass(Enum):
    """職業系統"""

    WARRIOR = "⚔️ 戰士"
    MAGE = "🔮 法師"
    ARCHER = "🏹 弓箭手"
    DATA_KEEPER = "💾 數據守護者"  # AutoCRUD 特色職業


class ItemRarity(Enum):
    """裝備稀有度"""

    COMMON = "普通"
    RARE = "稀有"
    EPIC = "史詩"
    LEGENDARY = "傳奇"
    AUTOCRUD = "🚀 AutoCRUD 神器"  # 特殊等級


class Character(Struct):
    """遊戲角色"""

    name: str
    character_class: CharacterClass
    valueAD__x: int = 12
    level: int = 1
    hp: int = 100
    mp: int = 50
    attack: int = 10
    defense: int = 5
    experience: int = 0
    gold: int = 100
    guild_name: Optional[str] = None
    special_ability: Optional[str] = None
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


class Equipment(Struct):
    """遊戲裝備"""

    name: str
    rarity: ItemRarity
    character_class_req: Optional[CharacterClass] = None
    attack_bonus: int = 0
    defense_bonus: int = 0
    special_effect: Optional[str] = None
    price: int = 100
    icon: Optional[Binary] = None  # Binary 類型欄位


# ===== Message Queue 使用範例：遊戲事件系統 =====


class GameEventType(Enum):
    """遊戲事件類型"""

    LEVEL_UP = "level_up"  # 角色升級
    GUILD_REWARD = "guild_reward"  # 公會獎勵
    DAILY_LOGIN = "daily_login"  # 每日登入獎勵
    QUEST_COMPLETE = "quest_complete"  # 任務完成
    EQUIPMENT_ENHANCE = "equipment_enhance"  # 裝備強化


class GameEventPayload(Struct):
    """遊戲事件載荷數據"""

    event_type: GameEventType
    character_name: str
    description: str
    reward_gold: int = 0
    reward_exp: int = 0
    extra_data: dict = {}


class GameEvent(Job[GameEventPayload]):
    """遊戲事件任務（使用 Message Queue 處理）"""

    pass


def get_random_image():
    import httpx

    r = httpx.get("https://picsum.photos/200", follow_redirects=True)
    return r.content


def create_sample_data(crud: AutoCRUD):
    """創建示範數據"""
    print("🎮 創建示範遊戲數據...")

    # 取得資源管理器
    guild_manager = crud.resource_managers.get("guild")
    character_manager = crud.resource_managers.get("character")
    equipment_manager = crud.resource_managers.get("equipment")

    if not all([guild_manager, character_manager, equipment_manager]):
        print("❌ 資源管理器未找到，請確保已註冊模型")
        return

    current_user = "game_admin"
    current_time = dt.datetime.now()

    # 🏰 創建公會
    guilds = [
        Guild(
            name="AutoCRUD 開發者聯盟",
            description="致力於推廣 AutoCRUD 技術的頂尖公會",
            leader="架構師阿明",
            member_count=50,
            level=10,
            treasury=100000,
        ),
        Guild(
            name="數據庫騎士團",
            description="守護數據安全的傳奇騎士",
            leader="DBA 女王",
            member_count=25,
            level=8,
            treasury=50000,
        ),
        Guild(
            name="API 法師學院",
            description="精通各種 API 魔法的學者聚集地",
            leader="RESTful 大師",
            member_count=75,
            level=12,
            treasury=150000,
        ),
        Guild(
            name="新手村互助會",
            description="歡迎所有新手加入的溫馨公會",
            leader="村長老王",
            member_count=200,
            level=3,
            treasury=10000,
        ),
    ]

    # 創建公會數據
    with guild_manager.meta_provide(current_user, current_time):
        for guild in guilds:
            try:
                guild_manager.create(guild)
                print(f"✅ 創建公會: {guild.name}")
            except Exception as e:
                print(f"❌ 公會創建失敗: {e}")

    # ⚔️ 創建角色
    characters = [
        Character(
            name="AutoCRUD 大神",
            character_class=CharacterClass.DATA_KEEPER,
            level=99,
            hp=9999,
            mp=9999,
            attack=500,
            defense=300,
            experience=999999,
            gold=1000000,
            guild_name="AutoCRUD 開發者聯盟",
            special_ability="🚀 一鍵生成完美 API",
        ),
        Character(
            name="資料庫女王",
            character_class=CharacterClass.MAGE,
            level=85,
            hp=2500,
            mp=5000,
            attack=200,
            defense=150,
            experience=750000,
            gold=500000,
            guild_name="數據庫騎士團",
            special_ability="💾 瞬間優化查詢",
        ),
        Character(
            name="RESTful 劍聖",
            character_class=CharacterClass.WARRIOR,
            level=90,
            hp=5000,
            mp=1000,
            attack=400,
            defense=250,
            experience=850000,
            gold=750000,
            guild_name="API 法師學院",
            special_ability="⚡ HTTP 狀態碼斬",
        ),
        Character(
            name="Schema 設計師",
            character_class=CharacterClass.ARCHER,
            level=75,
            hp=2000,
            mp=3000,
            attack=300,
            defense=120,
            experience=600000,
            gold=400000,
            guild_name="AutoCRUD 開發者聯盟",
            special_ability="🎯 精準數據建模",
        ),
        Character(
            name="新手小白",
            character_class=CharacterClass.WARRIOR,
            level=5,
            hp=150,
            mp=75,
            attack=15,
            defense=8,
            experience=500,
            gold=250,
            guild_name="新手村互助會",
            special_ability="🌱 學習能力超強",
        ),
        Character(
            name="API 魔法師",
            character_class=CharacterClass.MAGE,
            level=60,
            hp=1500,
            mp=4000,
            attack=180,
            defense=90,
            experience=400000,
            gold=300000,
            guild_name="API 法師學院",
            special_ability="🔮 自動生成文檔",
        ),
    ]

    # 創建角色數據
    with character_manager.meta_provide(current_user, current_time):
        for character in characters:
            try:
                character_manager.create(character)
                print(f"✅ 創建角色: {character.name} (Lv.{character.level})")
            except Exception as e:
                print(f"❌ 角色創建失敗: {e}")

    # 🗡️ 創建裝備
    # 創建一個簡單的 1x1 PNG圖片 作為圖標

    equipment_list = [
        Equipment(
            name="AutoCRUD 神劍",
            rarity=ItemRarity.AUTOCRUD,
            character_class_req=CharacterClass.DATA_KEEPER,
            attack_bonus=200,
            defense_bonus=50,
            special_effect="🚀 自動生成 CRUD 操作",
            price=1000000,
            icon=Binary(data=get_random_image()),
        ),
        Equipment(
            name="數據庫守護盾",
            rarity=ItemRarity.LEGENDARY,
            character_class_req=CharacterClass.WARRIOR,
            attack_bonus=20,
            defense_bonus=150,
            special_effect="🛡️ 防止 SQL 注入攻擊",
            price=500000,
            icon=Binary(data=get_random_image()),
        ),
        Equipment(
            name="API 魔法杖",
            rarity=ItemRarity.EPIC,
            character_class_req=CharacterClass.MAGE,
            attack_bonus=100,
            defense_bonus=30,
            special_effect="✨ 法術冷卻時間減少 50%",
            price=250000,
            icon=Binary(data=get_random_image()),
        ),
        Equipment(
            name="精準查詢弓",
            rarity=ItemRarity.RARE,
            character_class_req=CharacterClass.ARCHER,
            attack_bonus=80,
            special_effect="🎯 100% 命中率",
            price=150000,
            icon=Binary(data=get_random_image()),
        ),
        Equipment(
            name="新手村木劍",
            rarity=ItemRarity.COMMON,
            attack_bonus=5,
            special_effect="🌱 經驗值獲得 +10%",
            price=50,
            icon=Binary(data=get_random_image()),
        ),
    ]

    # 創建裝備數據
    with equipment_manager.meta_provide(current_user, current_time):
        for equipment in equipment_list:
            try:
                equipment_manager.create(equipment)
                print(f"✅ 創建裝備: {equipment.name} [{equipment.rarity.value}]")
            except Exception as e:
                print(f"❌ 裝備創建失敗: {e}")


_crud = None


def get_crud():
    """創建並返回 AutoCRUD 實例"""
    global _crud
    if _crud is None:
        storage_type = input("使用memory or disk storage？ [[M]emory/(D)isk]: ")

        if storage_type.lower() in ("d", "disk"):
            storage_path = (
                input("請輸入磁盤存儲路徑（預設: ./rpg_game_data）: ")
                or "./rpg_game_data"
            )
            storage_factory = DiskStorageFactory(rootdir=storage_path)
        else:
            storage_factory = None

        mq_type = input("使用rabbit mq嗎？ [y/N]: ")
        if mq_type.lower() == "y":
            mq_factory = RabbitMQMessageQueueFactory()
        else:
            mq_factory = SimpleMessageQueueFactory()
        _crud = AutoCRUD(
            storage_factory=storage_factory, message_queue_factory=mq_factory
        )
    _crud.add_route_template(GraphQLRouteTemplate())
    _crud.add_route_template(BlobRouteTemplate())
    _crud.add_route_template(MigrateRouteTemplate())

    # 註冊模型
    _crud.add_model(Character, indexed_fields=[("level", int), ("name", str)])
    _crud.add_model(Guild)
    _crud.add_model(Equipment)

    # 註冊遊戲事件任務模型（使用 Message Queue）
    # 注意：需要提供 job_handler 才會啟用 message queue
    # 這裡先用一個簡單的佔位函數，實際處理會在背景執行緒中進行
    _crud.add_model(
        GameEvent,
        indexed_fields=[("status", str)],
        job_handler=process_game_event,
    )

    return _crud


def process_game_event(event_resource: Resource[GameEvent]):
    """
    處理遊戲事件的背景工作函數

    這個函數會在背景執行緒中運行，從 message queue 取出事件並處理
    """
    global _crud
    event = event_resource.data
    payload = event.payload

    print(f"\n🎮 處理遊戲事件: {payload.event_type.value}")
    print(f"   角色: {payload.character_name}")
    print(f"   描述: {payload.description}")

    # 模擬異步處理
    time.sleep(random.uniform(0.5, 2.0))

    # 根據事件類型處理
    if payload.event_type == GameEventType.LEVEL_UP:
        # 處理角色升級
        print(f"   ⬆️ 角色升級！獎勵經驗值: {payload.reward_exp}")

    elif payload.event_type == GameEventType.GUILD_REWARD:
        # 處理公會獎勵
        print(f"   💰 公會獎勵發放！金幣: {payload.reward_gold}")

    elif payload.event_type == GameEventType.DAILY_LOGIN:
        # 處理每日登入
        print(
            f"   📅 每日登入獎勵！經驗: {payload.reward_exp}, 金幣: {payload.reward_gold}"
        )

    elif payload.event_type == GameEventType.QUEST_COMPLETE:
        # 處理任務完成
        print(
            f"   ✅ 任務完成！獎勵: 經驗 {payload.reward_exp}, 金幣 {payload.reward_gold}"
        )

    elif payload.event_type == GameEventType.EQUIPMENT_ENHANCE:
        # 處理裝備強化
        equipment_name = payload.extra_data.get("equipment_name", "未知裝備")
        print(f"   🔨 裝備強化！{equipment_name} 強化成功")

    result_msg = f"✅ 事件處理成功: {payload.description}"
    print(f"   {result_msg}")


def create_sample_events(crud: AutoCRUD):
    """創建一些示範遊戲事件"""
    print("\n🎮 創建示範遊戲事件...")

    event_manager = crud.resource_managers.get("game-event")
    if not event_manager:
        print("❌ 遊戲事件管理器未找到")
        return

    current_time = dt.datetime.now()

    # 創建各種遊戲事件
    sample_events = [
        GameEventPayload(
            event_type=GameEventType.LEVEL_UP,
            character_name="新手小白",
            description="角色升級到 6 級",
            reward_exp=500,
            reward_gold=100,
        ),
        GameEventPayload(
            event_type=GameEventType.GUILD_REWARD,
            character_name="AutoCRUD 大神",
            description="公會活動獎勵發放",
            reward_gold=5000,
        ),
        GameEventPayload(
            event_type=GameEventType.DAILY_LOGIN,
            character_name="API 魔法師",
            description="每日登入獎勵",
            reward_exp=200,
            reward_gold=50,
        ),
        GameEventPayload(
            event_type=GameEventType.QUEST_COMPLETE,
            character_name="RESTful 劍聖",
            description="完成任務：擊敗 SQL 注入怪獸",
            reward_exp=1000,
            reward_gold=500,
        ),
        GameEventPayload(
            event_type=GameEventType.EQUIPMENT_ENHANCE,
            character_name="Schema 設計師",
            description="裝備強化成功",
            reward_gold=0,
            extra_data={"equipment_name": "精準查詢弓", "enhance_level": 5},
        ),
    ]

    with event_manager.meta_provide(user="game_admin", now=current_time):
        for event_payload in sample_events:
            try:
                # 使用 message queue 的 put 方法加入事件
                event_manager.create(GameEvent(payload=event_payload))
                print(
                    f"✅ 創建事件: {event_payload.event_type.value} - {event_payload.description}"
                )
            except Exception as e:
                print(f"❌ 事件創建失敗: {e}")

    print(f"\n📊 已加入 {len(sample_events)} 個遊戲事件到處理隊列")
    print("   背景工作執行緒將會自動處理這些事件\n")


def main():
    """主程序"""
    print("🎮 === RPG 遊戲 API 系統啟動 === ⚔️")

    # 創建 FastAPI 應用
    app = FastAPI(
        title="⚔️ RPG 遊戲管理系統",
        description="""
        🎮 **完整的 RPG 遊戲管理 API**
        
        功能特色：
        - ⚔️ **角色管理**: 創建、查詢、升級遊戲角色
        - 🏰 **公會系統**: 管理遊戲公會和成員
        - 🗡️ **裝備系統**: 武器裝備的完整管理
        - 🎯 **遊戲事件系統**: 使用 Message Queue 處理異步遊戲事件
        - 🚀 **AutoCRUD 驅動**: 自動生成的完整 CRUD API
        - 📊 **數據搜尋**: 強大的查詢和篩選功能
        - 📖 **版本控制**: 追蹤所有數據變更歷史
        
        🎯 **快速開始**:
        1. 查看角色列表: `GET /character/data`
        2. 創建新角色: `POST /character`  
        3. 查看公會列表: `GET /guild/data`
        4. 瀏覽裝備: `GET /equipment/data`
        5. 查看遊戲事件: `GET /game-event/data`
        6. 觸發遊戲事件: `POST /game-event`
        """,
        version="2.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # 創建 AutoCRUD 實例
    crud = get_crud()

    # 應用到 FastAPI
    crud.apply(app)
    crud.openapi(app)
    crud.get_resource_manager(GameEvent).start_consume(block=False)

    # 創建示範數據
    ans = input("需要創建示範數據嗎？[y/N]: ")
    if ans.lower() == "y":
        create_sample_data(crud)

    # 啟動遊戲事件處理背景工作執行緒
    print("\n🔄 啟動遊戲事件處理系統...")

    # 創建示範遊戲事件
    ans = input("需要創建示範遊戲事件嗎？[y/N]: ")
    if ans.lower() == "y":
        create_sample_events(crud)

    print("\n🚀 === 服務器啟動成功 === 🚀")
    print("📖 OpenAPI 文檔: http://localhost:8000/docs")
    print("🔍 ReDoc 文檔: http://localhost:8000/redoc")
    print("⚔️ 角色 API: http://localhost:8000/character/data")
    print("🏰 公會 API: http://localhost:8000/guild/data")
    print("🗡️ 裝備 API: http://localhost:8000/equipment/data")
    print("🎯 遊戲事件 API: http://localhost:8000/game-event/data")
    print("📊 完整資訊: http://localhost:8000/character/full")
    print("\n💡 Message Queue 使用範例:")
    print("   - 遊戲事件會在背景自動處理")
    print("   - 可透過 API 查看事件狀態: GET /game-event/data")
    print("   - 可手動觸發新事件: POST /game-event")
    print("\n🎮 開始你的 RPG 冒險吧！")

    # 啟動服務器
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    main()
