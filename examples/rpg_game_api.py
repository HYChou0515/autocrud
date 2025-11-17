#!/usr/bin/env python3
"""⚔️ RPG 遊戲 API 系統 - AutoCRUD + FastAPI 完整示範 🛡️

這個範例展示：
- 完整的 AutoCRUD + FastAPI 集成
- Schema 演化和版本控制
- 預填遊戲數據
- 可直接使用的 OpenAPI 文檔

運行方式：
    python rpg_system.py

然後訪問：
    http://localhost:8000/docs - OpenAPI 文檔
    http://localhost:8000/character - 角色 API
    http://localhost:8000/guild - 公會 API
"""

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import uvicorn
from fastapi import FastAPI

from autocrud import AutoCRUD
from autocrud.resource_manager.storage_factory import DiskStorageFactory


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


@dataclass
class Character:
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
    guild_name: Optional[str] = None
    special_ability: Optional[str] = None
    created_at: dt.datetime = dt.datetime.now()


@dataclass
class Guild:
    """遊戲公會"""

    name: str
    description: str
    leader: str
    member_count: int = 1
    level: int = 1
    treasury: int = 1000
    founded_at: dt.datetime = dt.datetime.now()


@dataclass
class Equipment:
    """遊戲裝備"""

    name: str
    rarity: ItemRarity
    character_class_req: Optional[CharacterClass] = None
    attack_bonus: int = 0
    defense_bonus: int = 0
    special_effect: Optional[str] = None
    price: int = 100


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
    equipment_list = [
        Equipment(
            name="AutoCRUD 神劍",
            rarity=ItemRarity.AUTOCRUD,
            character_class_req=CharacterClass.DATA_KEEPER,
            attack_bonus=200,
            defense_bonus=50,
            special_effect="🚀 自動生成 CRUD 操作",
            price=1000000,
        ),
        Equipment(
            name="數據庫守護盾",
            rarity=ItemRarity.LEGENDARY,
            character_class_req=CharacterClass.WARRIOR,
            attack_bonus=20,
            defense_bonus=150,
            special_effect="🛡️ 防止 SQL 注入攻擊",
            price=500000,
        ),
        Equipment(
            name="API 魔法杖",
            rarity=ItemRarity.EPIC,
            character_class_req=CharacterClass.MAGE,
            attack_bonus=100,
            defense_bonus=30,
            special_effect="✨ 法術冷卻時間減少 50%",
            price=250000,
        ),
        Equipment(
            name="精準查詢弓",
            rarity=ItemRarity.RARE,
            character_class_req=CharacterClass.ARCHER,
            attack_bonus=80,
            special_effect="🎯 100% 命中率",
            price=150000,
        ),
        Equipment(
            name="新手村木劍",
            rarity=ItemRarity.COMMON,
            attack_bonus=5,
            special_effect="🌱 經驗值獲得 +10%",
            price=50,
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


def get_crud():
    """創建並返回 AutoCRUD 實例"""
    storage_type = input("使用memory or disk storage？ [[M]emory/(D)isk]: ")

    if storage_type.lower() in ("d", "disk"):
        storage_path = (
            input("請輸入磁盤存儲路徑（預設: ./rpg_game_data）: ") or "./rpg_game_data"
        )
        crud = AutoCRUD(storage_factory=DiskStorageFactory(rootdir=storage_path))
    else:
        crud = AutoCRUD()

    # 註冊模型
    crud.add_model(Character, indexed_fields=[("level", int)])
    crud.add_model(Guild)
    crud.add_model(Equipment)

    return crud


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
        - 🚀 **AutoCRUD 驅動**: 自動生成的完整 CRUD API
        - 📊 **數據搜尋**: 強大的查詢和篩選功能
        - 📖 **版本控制**: 追蹤所有數據變更歷史
        
        🎯 **快速開始**:
        1. 查看角色列表: `GET /character/data`
        2. 創建新角色: `POST /character`  
        3. 查看公會列表: `GET /guild/data`
        4. 瀏覽裝備: `GET /equipment/data`
        5. 查看完整資訊: `GET /character/full`
        """,
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # 創建 AutoCRUD 實例
    crud = get_crud()

    # 應用到 FastAPI
    crud.apply(app)
    crud.openapi(app)

    # 創建示範數據
    ans = input("需要創建示範數據嗎？[y/N]: ")
    if ans.lower() == "y":
        create_sample_data(crud)

    print("\n🚀 === 服務器啟動成功 === 🚀")
    print("📖 OpenAPI 文檔: http://localhost:8000/docs")
    print("🔍 ReDoc 文檔: http://localhost:8000/redoc")
    print("⚔️ 角色 API: http://localhost:8000/character/data")
    print("🏰 公會 API: http://localhost:8000/guild/data")
    print("🗡️ 裝備 API: http://localhost:8000/equipment/data")
    print("📊 完整資訊: http://localhost:8000/character/full")
    print("\n🎮 開始你的 RPG 冒險吧！")

    # 啟動服務器
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    main()
