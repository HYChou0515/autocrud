#!/usr/bin/env python3
"""⚔️ RPG 遊戲 API 系統 - AutoCRUD + Celery Message Queue 示範 🛡️

這個範例展示：
- 完整的 AutoCRUD + FastAPI + Celery 集成
- 使用 Celery 處理異步任務
- Redis 作為 Celery broker 和 result backend
- 分散式任務處理架構
- 遊戲事件異步處理系統

環境需求：
    pip install celery redis

Redis 服務器：
    Docker: docker run -d -p 6379:6379 redis
    或本地安裝 Redis

Celery Worker 啟動：
    # 在另一個終端運行
    celery -A examples.rpg_game_celery_api worker --loglevel=info

運行方式：
    python examples/rpg_game_celery_api.py

然後訪問：
    http://localhost:8000/docs - OpenAPI 文檔
    http://localhost:8000/character - 角色 API
    http://localhost:8000/game-event - 遊戲事件任務 API
"""

import datetime as dt
import random
import time
from enum import Enum

import uvicorn
from celery import Celery
from fastapi import FastAPI
from msgspec import Struct

from autocrud import AutoCRUD
from autocrud.crud.route_templates.graphql import GraphQLRouteTemplate
from autocrud.message_queue.basic import DelayRetry, NoRetry
from autocrud.message_queue.celery_queue import CeleryMessageQueueFactory
from autocrud.resource_manager.storage_factory import DiskStorageFactory
from autocrud.types import Job, Resource

# ===== Celery 配置 =====
# 創建 Celery 應用實例
celery_app = Celery(
    "rpg_game",
    broker="redis://localhost:6379/0",  # Redis 作為消息隊列
    backend="redis://localhost:6379/1",  # Redis 作為結果儲存
)

# Celery 配置
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Taipei",
    enable_utc=True,
    task_track_started=True,  # 追蹤任務開始狀態
    task_time_limit=300,  # 任務最長執行時間 5 分鐘
    task_soft_time_limit=240,  # 軟限制 4 分鐘
    worker_prefetch_multiplier=4,  # Worker 預取任務數量
    worker_max_tasks_per_child=1000,  # 每個 worker 最多執行 1000 個任務後重啟
)


# ===== 遊戲數據模型 =====


class CharacterClass(Enum):
    """職業系統"""

    WARRIOR = "⚔️ 戰士"
    MAGE = "🔮 法師"
    ARCHER = "🏹 弓箭手"
    ASSASSIN = "🗡️ 刺客"
    CLERIC = "✨ 牧師"


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


# ===== Celery 異步任務系統 =====


class GameEventType(Enum):
    """遊戲事件類型"""

    LEVEL_UP = "level_up"  # 角色升級
    DAILY_LOGIN = "daily_login"  # 每日登入獎勵
    QUEST_COMPLETE = "quest_complete"  # 任務完成
    BOSS_FIGHT = "boss_fight"  # BOSS 戰鬥
    DUNGEON_RAID = "dungeon_raid"  # 副本挑戰（需要隊伍集結）
    ARENA_MATCH = "arena_match"  # 競技場匹配（需要等待對手）
    CRAFTING = "crafting"  # 裝備製作（需要時間）
    AUCTION_BID = "auction_bid"  # 拍賣競標（需要等待結束時間）


class GameEventPayload(Struct):
    """遊戲事件載荷數據"""

    event_type: GameEventType
    character_name: str
    description: str
    reward_gold: int = 0
    reward_exp: int = 0
    extra_data: dict = {}


class GameEvent(Job[GameEventPayload]):
    """遊戲事件任務（使用 Celery 處理）"""

    pass


# ===== 遊戲事件處理函數 =====


def process_game_event(event_resource: Resource[GameEvent]):
    """
    處理遊戲事件的 Celery 任務

    這個函數會被 Celery worker 執行，支援：
    - 分散式任務處理
    - 自動重試機制
    - DelayRetry 延遲重試
    - NoRetry 不重試異常
    """
    event = event_resource.data
    payload = event.payload

    print(f"\n🎮 [Celery Worker] 處理遊戲事件: {payload.event_type.value}")
    print(f"   角色: {payload.character_name}")
    print(f"   描述: {payload.description}")
    print(f"   重試次數: {event.retries}")
    print(f"   任務 ID: {event_resource.info.resource_id}")

    # 模擬異步處理
    processing_time = random.uniform(0.5, 2.0)
    time.sleep(processing_time)

    # 根據事件類型處理
    if payload.event_type == GameEventType.LEVEL_UP:
        # 處理角色升級
        new_level = payload.extra_data.get("new_level", 2)
        print(f"   ⬆️ 角色升級到 Lv.{new_level}！")
        print(
            f"   獲得獎勵 - 經驗值: {payload.reward_exp}, 金幣: {payload.reward_gold}"
        )

    elif payload.event_type == GameEventType.DAILY_LOGIN:
        # 處理每日登入
        consecutive_days = payload.extra_data.get("consecutive_days", 1)
        print(f"   📅 連續登入第 {consecutive_days} 天！")
        print(f"   每日獎勵 - 經驗: {payload.reward_exp}, 金幣: {payload.reward_gold}")

    elif payload.event_type == GameEventType.QUEST_COMPLETE:
        # 處理任務完成
        quest_name = payload.extra_data.get("quest_name", "未知任務")
        difficulty = payload.extra_data.get("difficulty", "普通")
        print(f"   ✅ 完成任務: {quest_name} (難度: {difficulty})")
        print(f"   任務獎勵 - 經驗: {payload.reward_exp}, 金幣: {payload.reward_gold}")

    elif payload.event_type == GameEventType.BOSS_FIGHT:
        # BOSS 戰鬥
        boss_name = payload.extra_data.get("boss_name", "未知 BOSS")
        boss_hp = payload.extra_data.get("boss_hp", 10000)

        # 模擬戰鬥失敗需要重試的情況
        if random.random() < 0.3 and event.retries < 2:  # 30% 失敗率，最多重試2次
            print(f"   ⚔️ 挑戰 {boss_name} 失敗！")
            print(f"   BOSS 剩餘 HP: {boss_hp * 0.5}")
            raise ValueError("BOSS 戰鬥失敗，將自動重試")

        print(f"   🏆 成功擊敗 {boss_name}！")
        print(f"   戰利品 - 經驗: {payload.reward_exp}, 金幣: {payload.reward_gold}")

    elif payload.event_type == GameEventType.DUNGEON_RAID:
        # 🎯 DelayRetry 範例 1: 副本需要等待隊伍集結
        required_members = payload.extra_data.get("required_members", 4)
        current_members = payload.extra_data.get("current_members", 0)

        if current_members < required_members:
            wait_time = 15  # 等待 15 秒讓更多玩家加入
            print(f"   ⏳ 副本隊伍人數不足 ({current_members}/{required_members})")
            print(f"   等待 {wait_time} 秒後重試...")
            # 拋出 DelayRetry，系統會在指定秒數後重新執行
            raise DelayRetry(delay_seconds=wait_time)

        dungeon_name = payload.extra_data.get("dungeon_name", "未知副本")
        print(f"   🏰 隊伍集結完成！開始挑戰 {dungeon_name}")
        print(f"   通關獎勵 - 經驗: {payload.reward_exp}, 金幣: {payload.reward_gold}")

    elif payload.event_type == GameEventType.ARENA_MATCH:
        # 🎯 DelayRetry 範例 2: 競技場需要等待匹配對手
        has_opponent = payload.extra_data.get("has_opponent", False)

        if not has_opponent:
            wait_time = 10  # 等待 10 秒匹配對手
            print("   🎯 競技場匹配中...")
            print(f"   等待 {wait_time} 秒尋找對手...")
            raise DelayRetry(delay_seconds=wait_time)

        opponent_name = payload.extra_data.get("opponent_name", "神秘對手")
        print(f"   ⚔️ 匹配成功！對手: {opponent_name}")
        print(f"   勝利獎勵 - 經驗: {payload.reward_exp}, 金幣: {payload.reward_gold}")

    elif payload.event_type == GameEventType.CRAFTING:
        # 🎯 DelayRetry 範例 3: 裝備製作需要時間
        crafting_end_time = payload.extra_data.get("crafting_end_time")

        if crafting_end_time:
            end_time = dt.datetime.fromisoformat(crafting_end_time)
            now = dt.datetime.now()

            if now < end_time:
                delay = int((end_time - now).total_seconds())
                item_name = payload.extra_data.get("item_name", "未知裝備")
                print(f"   🔨 製作中: {item_name}")
                print(f"   還需要 {delay} 秒完成...")
                raise DelayRetry(delay_seconds=min(delay, 30))  # 最多延遲30秒

        item_name = payload.extra_data.get("item_name", "未知裝備")
        quality = payload.extra_data.get("quality", "普通")
        print(f"   ✅ 製作完成: {item_name} ({quality})")
        print(f"   獲得 {payload.reward_exp} 經驗值")

    elif payload.event_type == GameEventType.AUCTION_BID:
        # 🎯 DelayRetry 範例 4: 拍賣需要等待結束時間
        auction_end_time = payload.extra_data.get("auction_end_time")

        if auction_end_time:
            end_time = dt.datetime.fromisoformat(auction_end_time)
            now = dt.datetime.now()

            if now < end_time:
                delay = int((end_time - now).total_seconds())
                item_name = payload.extra_data.get("item_name", "未知道具")
                print(f"   🎪 拍賣進行中: {item_name}")
                print(f"   距離結束還有 {delay} 秒...")
                raise DelayRetry(delay_seconds=min(delay, 30))

        is_winner = payload.extra_data.get("is_winner", True)
        item_name = payload.extra_data.get("item_name", "未知道具")

        if is_winner:
            print(f"   🎉 競標成功！獲得: {item_name}")
            print(f"   花費: {payload.reward_gold} 金幣")
        else:
            print(f"   😢 競標失敗: {item_name}")
            # 競標失敗不需要重試
            raise NoRetry("競標失敗，不再重試")

    result_msg = f"✅ 事件處理成功: {payload.description}"
    print(f"   {result_msg}")
    print(f"   處理時間: {processing_time:.2f} 秒")

    # 返回 False 可以停止週期性任務
    # 返回 None 或 True 繼續執行週期性任務
    return None


# ===== AutoCRUD 與 FastAPI 集成 =====

_crud = None


def get_crud():
    """創建並返回 AutoCRUD 實例"""
    global _crud
    if _crud is None:
        print("\n⚙️ 初始化 AutoCRUD + Celery...")

        # 使用磁盤存儲
        storage_factory = DiskStorageFactory(rootdir="./rpg_celery_data")

        # 🎯 關鍵：使用 CeleryMessageQueueFactory
        celery_mq_factory = CeleryMessageQueueFactory(
            celery_app=celery_app,
            queue_prefix="rpg.",  # 佇列前綴
            max_retries=3,  # 最大重試次數
            retry_delay_seconds=10,  # 重試延遲（秒）
        )

        _crud = AutoCRUD(
            default_now=lambda: dt.datetime.now(),
            storage_factory=storage_factory,
            message_queue_factory=celery_mq_factory,  # ty:ignore[invalid-argument-type]
        )

        # 添加路由模板
        _crud.add_route_template(GraphQLRouteTemplate())

        # 註冊角色模型
        _crud.add_model(
            Character,
            indexed_fields=[
                ("level", int),
                ("name", str),
                ("gold", int),
                ("character_class", CharacterClass),
            ],
        )

        # 🎯 關鍵：註冊遊戲事件模型，指定 job_handler
        _crud.add_model(
            GameEvent,
            indexed_fields=[("status", str)],
            job_handler=process_game_event,  # ty:ignore[invalid-argument-type]
        )

        print("✅ AutoCRUD 初始化完成")
        print(f"   Celery Broker: {celery_app.conf.broker_url}")
        print(f"   Celery Backend: {celery_app.conf.result_backend}")
        print(
            "   Queue Prefix: rpg. (實際佇列名稱: rpg.game_event 或 rpg.job 視類型名稱而定)"
        )

    return _crud


def create_sample_characters(crud: AutoCRUD):
    """創建示範角色"""
    print("\n👥 創建示範角色...")

    character_manager = crud.resource_managers.get("character")
    if not character_manager:
        print("❌ 角色管理器未找到")
        return

    characters = [
        Character(
            name="Celery 戰士",
            character_class=CharacterClass.WARRIOR,
            level=50,
            hp=5000,
            attack=200,
            defense=150,
            gold=50000,
        ),
        Character(
            name="異步法師",
            character_class=CharacterClass.MAGE,
            level=45,
            hp=2000,
            mp=8000,
            attack=300,
            defense=80,
            gold=40000,
        ),
        Character(
            name="分散式弓手",
            character_class=CharacterClass.ARCHER,
            level=42,
            hp=3000,
            attack=250,
            defense=100,
            gold=35000,
        ),
        Character(
            name="Redis 刺客",
            character_class=CharacterClass.ASSASSIN,
            level=48,
            hp=2500,
            attack=350,
            defense=70,
            gold=45000,
        ),
        Character(
            name="Worker 牧師",
            character_class=CharacterClass.CLERIC,
            level=40,
            hp=3500,
            mp=6000,
            attack=100,
            defense=120,
            gold=30000,
        ),
    ]

    with character_manager.meta_provide(user="game_admin"):
        for char in characters:
            try:
                character_manager.create(char)
                print(f"   ✅ {char.name} (Lv.{char.level})")
            except Exception as e:
                print(f"   ❌ 創建失敗: {e}")


def create_sample_events(crud: AutoCRUD):
    """創建示範遊戲事件"""
    print("\n🎮 創建示範遊戲事件...")

    event_manager = crud.resource_managers.get("game-event")
    if not event_manager:
        print("❌ 遊戲事件管理器未找到")
        return

    current_time = dt.datetime.now()

    # 各種類型的遊戲事件
    sample_events = [
        GameEventPayload(
            event_type=GameEventType.LEVEL_UP,
            character_name="Celery 戰士",
            description="角色升級",
            reward_exp=1000,
            reward_gold=500,
            extra_data={"new_level": 51},
        ),
        GameEventPayload(
            event_type=GameEventType.DAILY_LOGIN,
            character_name="異步法師",
            description="每日登入獎勵",
            reward_exp=200,
            reward_gold=100,
            extra_data={"consecutive_days": 7},
        ),
        GameEventPayload(
            event_type=GameEventType.QUEST_COMPLETE,
            character_name="分散式弓手",
            description="完成任務：消滅 Bug 怪獸",
            reward_exp=1500,
            reward_gold=800,
            extra_data={"quest_name": "消滅 Bug 怪獸", "difficulty": "困難"},
        ),
        GameEventPayload(
            event_type=GameEventType.BOSS_FIGHT,
            character_name="Redis 刺客",
            description="挑戰世界 BOSS",
            reward_exp=5000,
            reward_gold=3000,
            extra_data={"boss_name": "內存洩漏惡龍", "boss_hp": 100000},
        ),
        # 🎯 DelayRetry 範例事件
        GameEventPayload(
            event_type=GameEventType.DUNGEON_RAID,
            character_name="隊伍集結",
            description="副本挑戰：死鎖迷宮",
            reward_exp=8000,
            reward_gold=5000,
            extra_data={
                "dungeon_name": "死鎖迷宮",
                "required_members": 4,
                "current_members": 2,  # 人數不足，會觸發 DelayRetry
            },
        ),
        GameEventPayload(
            event_type=GameEventType.ARENA_MATCH,
            character_name="Worker 牧師",
            description="競技場匹配",
            reward_exp=1000,
            reward_gold=600,
            extra_data={
                "has_opponent": False,  # 未找到對手，會觸發 DelayRetry
            },
        ),
        GameEventPayload(
            event_type=GameEventType.CRAFTING,
            character_name="Celery 戰士",
            description="製作傳說裝備",
            reward_exp=2000,
            extra_data={
                "item_name": "異步神劍",
                "quality": "傳說",
                "crafting_end_time": (
                    current_time + dt.timedelta(seconds=20)
                ).isoformat(),
            },
        ),
        GameEventPayload(
            event_type=GameEventType.AUCTION_BID,
            character_name="異步法師",
            description="拍賣競標",
            reward_gold=10000,
            extra_data={
                "item_name": "極速魔杖",
                "auction_end_time": (
                    current_time + dt.timedelta(seconds=25)
                ).isoformat(),
                "is_winner": True,
            },
        ),
    ]

    with event_manager.meta_provide(user="game_admin", now=current_time):
        for event_payload in sample_events:
            try:
                event_manager.create(GameEvent(payload=event_payload))
                print(
                    f"   ✅ {event_payload.event_type.value}: {event_payload.description}"
                )
            except Exception as e:
                print(f"   ❌ 事件創建失敗: {e}")

    print(f"\n📊 已創建 {len(sample_events)} 個遊戲事件")
    print("\n💡 Celery Worker 使用說明：")
    print("   1. 在另一個終端啟動 Worker:")
    print("      celery -A examples.rpg_game_celery_api worker --loglevel=info")
    print("\n   2. Worker 會自動處理隊列中的事件")
    print("   3. 你可以透過 GET /game-event/data 查看事件狀態")
    print("   4. 支援的特性:")
    print("      - 自動重試失敗的任務")
    print("      - DelayRetry 延遲重試")
    print("      - 分散式任務處理")
    print("      - 任務狀態追蹤\n")


def main():
    """主程序"""
    print("🎮 === RPG 遊戲 API 系統 (Celery 版) === ⚔️")
    print("\n📋 環境檢查：")
    print("   - Redis 服務器需要運行在 localhost:6379")
    print("   - Celery worker 需要在另一個終端啟動")
    print("   - 命令: celery -A examples.rpg_game_celery_api worker --loglevel=info\n")

    # 創建 FastAPI 應用
    app = FastAPI(
        title="⚔️ RPG 遊戲管理系統 (Celery 版)",
        description="""
        🎮 **使用 Celery 的 RPG 遊戲管理 API**
        
        功能特色：
        - ⚔️ **角色管理**: 創建、查詢、升級遊戲角色
        - 🎯 **Celery 異步任務**: 使用 Celery 處理遊戲事件
        - 🔄 **分散式處理**: 支援多個 Worker 並行處理
        - 🚀 **自動重試**: 失敗任務自動重試
        - ⏰ **延遲重試**: 支援 DelayRetry 機制
        - 📊 **任務追蹤**: 實時查看任務狀態
        
        🎯 **Celery 特性展示**:
        - 副本挑戰：需要等待隊伍集結 (DelayRetry)
        - 競技場匹配：需要等待對手 (DelayRetry)
        - 裝備製作：需要一定時間 (DelayRetry)
        - 拍賣競標：需要等待結束時間 (DelayRetry)
        - BOSS 戰鬥：失敗自動重試
        
        📖 **API 端點**:
        - GET /character/data - 查看角色列表
        - POST /character - 創建新角色
        - GET /game-event/data - 查看遊戲事件狀態
        - POST /game-event - 創建新的遊戲事件
        
        ⚙️ **Celery Worker**:
        ```bash
        celery -A examples.rpg_game_celery_api worker --loglevel=info
        ```
        """,
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # 創建 AutoCRUD 實例
    crud = get_crud()

    # 應用到 FastAPI
    crud.apply(app)
    crud.openapi(app)

    # 創建示範數據
    ans = input("需要創建示範角色嗎？[y/N]: ")
    if ans.lower() == "y":
        create_sample_characters(crud)

    # 創建示範遊戲事件
    ans = input("需要創建示範遊戲事件嗎？[y/N]: ")
    if ans.lower() == "y":
        create_sample_events(crud)

    crud.get_resource_manager(GameEvent).start_consume(block=False)

    print("\n🚀 === 服務器啟動成功 === 🚀")
    print("📖 OpenAPI 文檔: http://localhost:8000/docs")
    print("🔍 ReDoc 文檔: http://localhost:8000/redoc")
    print("⚔️ 角色 API: http://localhost:8000/character/data")
    print("🎯 遊戲事件 API: http://localhost:8000/game-event/data")
    print("   celery -A examples.rpg_game_celery_api worker --loglevel=info")
    print("\n🎮 開始你的 Celery 異步冒險吧！")

    # 啟動服務器
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    main()
