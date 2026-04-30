#!/usr/bin/env python3
"""⚔️ RPG 遊戲 API 系統（Pydantic 版本）- AutoCRUD + FastAPI 完整示範 🛡️

這個範例展示 AutoCRUD 如何使用 Pydantic BaseModel：
- Pydantic BaseModel → 自動驗證 + 高效存儲
- 使用 @field_validator (Pydantic v2) 進行資料驗證
- Pydantic Discriminated Union (Field(discriminator=...)) 完整支援
- 完整的 AutoCRUD + FastAPI 集成

與 rpg_game_api.py 的差異：
- 使用 Pydantic BaseModel 定義模型，享受 Pydantic 驗證能力
- 不需要額外寫 validator，Pydantic 本身就是驗證器
- create/update 可直接傳入 dict 或 Pydantic instance
- get 回傳 Pydantic instance（對 Pydantic 使用者零學習成本）

運行方式：
    python rpg_game_pydantic_api.py

然後訪問：
    http://localhost:8000/docs - OpenAPI 文檔
"""

import datetime as dt
from enum import Enum
from typing import Annotated, Literal, Optional, Union

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator

from autocrud import DisplayName, OnDelete, Ref, crud
from autocrud.crud.route_templates.blob import BlobRouteTemplate
from autocrud.crud.route_templates.graphql import GraphQLRouteTemplate
from autocrud.crud.route_templates.migrate import MigrateRouteTemplate
from autocrud.message_queue.simple import SimpleMessageQueueFactory
from autocrud.resource_manager.storage_factory import DiskStorageFactory
from autocrud.types import Binary

# ===== Enum 定義 =====


class CharacterClass(Enum):
    """職業系統"""

    WARRIOR = "⚔️ 戰士"
    MAGE = "🔮 法師"
    ARCHER = "🏹 弓箭手"
    DATA_KEEPER = "💾 數據守護者"


class ItemRarity(Enum):
    """裝備稀有度"""

    COMMON = "普通"
    RARE = "稀有"
    EPIC = "史詩"
    LEGENDARY = "傳奇"
    AUTOCRUD = "🚀 AutoCRUD 神器"


# ===== 技能系統 — Pydantic Discriminated Union =====
#
# Pydantic v2 使用 Literal + Field(discriminator=...) 來實現
# 被辨別的聯合類型 (discriminated union)，AutoCRUD 完整支援。


class ActiveSkillData(BaseModel):
    """主動技能數據"""

    skill_type: Literal["active"] = "active"
    mp_cost: int = 0
    cooldown_seconds: int = 0
    damage: int = 0

    @field_validator("mp_cost")
    @classmethod
    def mp_cost_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("MP 消耗不可為負數")
        return v

    @field_validator("cooldown_seconds")
    @classmethod
    def cooldown_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("冷卻時間不可為負數")
        return v


class PassiveSkillData(BaseModel):
    """被動技能數據"""

    skill_type: Literal["passive"] = "passive"
    buff_percentage: int = 0

    @field_validator("buff_percentage")
    @classmethod
    def buff_in_range(cls, v: int) -> int:
        if v < 0 or v > 100:
            raise ValueError("增益百分比必須在 0~100 之間")
        return v


class UltimateSkillData(BaseModel):
    """終極技能數據"""

    skill_type: Literal["ultimate"] = "ultimate"
    mp_cost: int = 0
    cooldown_seconds: int = 0
    damage: int = 0
    area_of_effect: bool = False

    @field_validator("damage")
    @classmethod
    def damage_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("終極技能傷害必須大於 0")
        return v


# Pydantic v2 discriminated union 類型別名
SkillDetail = Annotated[
    Union[ActiveSkillData, PassiveSkillData, UltimateSkillData],
    Field(discriminator="skill_type"),
]


# ===== Pydantic BaseModel 定義（含驗證） =====


class Skill(BaseModel):
    """遊戲技能 — Pydantic 版（使用 Discriminated Union）

    驗證邏輯直接內建於模型中，不需要額外的 validator。
    """

    model_config = ConfigDict(use_enum_values=False)

    skname: Annotated[str, DisplayName()]
    detail: Annotated[
        Union[ActiveSkillData, PassiveSkillData, UltimateSkillData],
        Field(discriminator="skill_type"),  # Pydantic v2 discriminated union
    ]
    description: str = ""
    required_level: int = 1
    required_class: Optional[CharacterClass] = None

    @field_validator("skname")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("技能名稱不可為空")
        return v

    @field_validator("required_level")
    @classmethod
    def level_at_least_one(cls, v: int) -> int:
        if v < 1:
            raise ValueError("技能需求等級至少為 1")
        return v


class Equipment(BaseModel):
    """遊戲裝備 — Pydantic 版"""

    model_config = ConfigDict(
        use_enum_values=False,
        arbitrary_types_allowed=True,  # 允許 Binary 等自定義類型
    )

    name: Annotated[str, DisplayName()]
    rarity: ItemRarity
    owner_id: Annotated[str | None, Ref("character", on_delete=OnDelete.set_null)] = (
        None
    )
    character_class_req: Optional[CharacterClass] = None
    attack_bonus: int = 0
    defense_bonus: int = 0
    special_effects: list[str] = []
    price: int = 100
    icon: Optional[Binary] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("裝備名稱不可為空")
        return v

    @field_validator("price")
    @classmethod
    def price_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("裝備價格不可為負數")
        return v

    @field_validator("attack_bonus")
    @classmethod
    def attack_bonus_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("攻擊加成不可為負數")
        return v

    @field_validator("defense_bonus")
    @classmethod
    def defense_bonus_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("防禦加成不可為負數")
        return v


class Character(BaseModel):
    """遊戲角色 — Pydantic 版

    所有驗證邏輯都透過 @field_validator 定義在模型上，
    AutoCRUD 會自動使用 Pydantic 進行資料驗證。
    """

    model_config = ConfigDict(use_enum_values=False)

    name: Annotated[str, DisplayName()]
    character_class: CharacterClass
    level: int = 1
    hp: int = 100
    mp: int = 50
    attack: int = 10
    defense: int = 5
    experience: int = 0
    gold: int = 100
    guild_id: Annotated[str | None, Ref("guild", on_delete=OnDelete.set_null)] = None
    guild_name: Optional[str] = None
    special_ability: Optional[str] = None
    skill_ids: list[Annotated[str, Ref("skill")]] = []

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("角色名稱不可為空")
        return v

    @field_validator("level")
    @classmethod
    def level_in_range(cls, v: int) -> int:
        if v < 1 or v > 999:
            raise ValueError("等級必須在 1~999 之間")
        return v

    @field_validator("hp", "mp", "attack", "defense", "experience", "gold")
    @classmethod
    def stats_non_negative(cls, v: int, info) -> int:
        if v < 0:
            raise ValueError(f"{info.field_name} 不可為負數")
        return v


class Guild(BaseModel):
    """遊戲公會 — Pydantic 版"""

    model_config = ConfigDict(use_enum_values=False)

    name: Annotated[str, DisplayName()]
    description: str
    leader: str
    member_count: int = 1
    level: int = 1
    treasury: int = 1000
    founded_at: dt.datetime = dt.datetime.now()

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("公會名稱不可為空")
        return v

    @field_validator("member_count")
    @classmethod
    def member_count_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("公會成員數至少為 1")
        return v

    @field_validator("level")
    @classmethod
    def level_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("公會等級至少為 1")
        return v

    @field_validator("treasury")
    @classmethod
    def treasury_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("公會金庫不可為負數")
        return v


# ===== 數據創建 =====


def create_sample_data():
    """創建示範數據"""
    print("🎮 創建示範遊戲數據（Pydantic 版）...")

    guild_manager = crud.resource_managers.get("guild")
    skill_manager = crud.resource_managers.get("skill")
    character_manager = crud.resource_managers.get("character")
    equipment_manager = crud.resource_managers.get("equipment")

    if not all([guild_manager, skill_manager, character_manager, equipment_manager]):
        print("❌ 資源管理器未找到，請確保已註冊模型")
        return

    current_user = "game_admin"
    current_time = dt.datetime.now()

    # 🏰 創建公會
    guilds_data = [
        {
            "name": "AutoCRUD 開發者聯盟",
            "description": "致力於推廣 AutoCRUD 技術的頂尖公會",
            "leader": "架構師阿明",
            "member_count": 50,
            "level": 10,
            "treasury": 100000,
        },
        {
            "name": "數據庫騎士團",
            "description": "守護數據安全的傳奇騎士",
            "leader": "DBA 女王",
            "member_count": 25,
            "level": 8,
            "treasury": 50000,
        },
        {
            "name": "API 法師學院",
            "description": "精通各種 API 魔法的學者聚集地",
            "leader": "RESTful 大師",
            "member_count": 75,
            "level": 12,
            "treasury": 150000,
        },
    ]

    guild_ids = {}
    with guild_manager.meta_provide(current_user, current_time):  # ty:ignore[unresolved-attribute]
        for gdata in guilds_data:
            try:
                # 直接傳入 dict — ResourceManager 會自動轉換
                info = guild_manager.create(gdata)  # ty:ignore[unresolved-attribute]
                guild_ids[gdata["name"]] = info.resource_id
                print(f"✅ 創建公會: {gdata['name']}")
            except Exception as e:
                print(f"❌ 公會創建失敗: {e}")

    # 🎯 創建技能（展示 discriminated union）
    skills_data = [
        {
            "skname": "火球術",
            "detail": {
                "skill_type": "active",
                "mp_cost": 30,
                "cooldown_seconds": 5,
                "damage": 150,
            },
            "description": "向敵人發射一顆強力火球",
            "required_level": 10,
            "required_class": CharacterClass.MAGE.value,
        },
        {
            "skname": "治癒之光",
            "detail": {"skill_type": "active", "mp_cost": 25, "cooldown_seconds": 8},
            "description": "恢復自身或隊友的生命值",
            "required_level": 5,
        },
        {
            "skname": "CRUD 終極奧義",
            "detail": {
                "skill_type": "ultimate",
                "mp_cost": 100,
                "cooldown_seconds": 60,
                "damage": 9999,
                "area_of_effect": True,
            },
            "description": "一鍵生成完美的 RESTful API，對所有敵人造成毀滅性打擊",
            "required_level": 50,
            "required_class": CharacterClass.DATA_KEEPER.value,
        },
        {
            "skname": "鋼鐵意志",
            "detail": {"skill_type": "passive", "buff_percentage": 20},
            "description": "永久提升防禦力 20%",
            "required_level": 20,
            "required_class": CharacterClass.WARRIOR.value,
        },
        {
            "skname": "經驗加成",
            "detail": {"skill_type": "passive", "buff_percentage": 10},
            "description": "獲得的經驗值增加 10%",
            "required_level": 1,
        },
    ]

    skill_ids = {}
    with skill_manager.meta_provide(current_user, current_time):  # ty:ignore[unresolved-attribute]
        for sdata in skills_data:
            try:
                info = skill_manager.create(sdata)  # ty:ignore[unresolved-attribute]
                skill_ids[sdata["skname"]] = info.resource_id
                print(f"✅ 創建技能: {sdata['skname']}")
            except Exception as e:
                print(f"❌ 技能創建失敗: {e}")

    # ⚔️ 創建角色
    characters_data = [
        {
            "name": "AutoCRUD 大神",
            "character_class": CharacterClass.DATA_KEEPER.value,
            "level": 99,
            "hp": 9999,
            "mp": 9999,
            "attack": 500,
            "defense": 300,
            "experience": 999999,
            "gold": 1000000,
            "guild_id": guild_ids.get("AutoCRUD 開發者聯盟"),
            "guild_name": "AutoCRUD 開發者聯盟",
            "special_ability": "🚀 一鍵生成完美 API",
            "skill_ids": [
                skill_ids.get("CRUD 終極奧義", ""),
                skill_ids.get("經驗加成", ""),
            ],
        },
        {
            "name": "資料庫女王",
            "character_class": CharacterClass.MAGE.value,
            "level": 85,
            "hp": 2500,
            "mp": 5000,
            "attack": 200,
            "defense": 150,
            "experience": 750000,
            "gold": 500000,
            "guild_id": guild_ids.get("數據庫騎士團"),
            "guild_name": "數據庫騎士團",
            "special_ability": "💾 瞬間優化查詢",
            "skill_ids": [
                skill_ids.get("火球術", ""),
                skill_ids.get("治癒之光", ""),
            ],
        },
        {
            "name": "新手小白",
            "character_class": CharacterClass.WARRIOR.value,
            "level": 5,
            "hp": 150,
            "mp": 75,
            "attack": 15,
            "defense": 8,
            "experience": 500,
            "gold": 250,
            "guild_id": guild_ids.get("API 法師學院"),
            "guild_name": "API 法師學院",
            "special_ability": "🌱 學習能力超強",
            "skill_ids": [skill_ids.get("經驗加成", "")],
        },
    ]

    with character_manager.meta_provide(current_user, current_time):  # ty:ignore[unresolved-attribute]
        for cdata in characters_data:
            try:
                info = character_manager.create(cdata)  # ty:ignore[unresolved-attribute]
                print(f"✅ 創建角色: {cdata['name']} (Lv.{cdata['level']})")
            except Exception as e:
                print(f"❌ 角色創建失敗: {e}")

    # 🗡️ 創建裝備
    equipment_data = [
        {
            "name": "AutoCRUD 神劍",
            "rarity": ItemRarity.AUTOCRUD.value,
            "attack_bonus": 200,
            "defense_bonus": 50,
            "special_effects": ["🚀 自動生成 CRUD 操作", "⚡ API 響應速度 +100%"],
            "price": 1000000,
        },
        {
            "name": "新手村木劍",
            "rarity": ItemRarity.COMMON.value,
            "attack_bonus": 5,
            "special_effects": ["🌱 經驗值獲得 +10%"],
            "price": 50,
        },
    ]

    with equipment_manager.meta_provide(current_user, current_time):  # ty:ignore[unresolved-attribute]
        for edata in equipment_data:
            try:
                info = equipment_manager.create(edata)  # ty:ignore[unresolved-attribute]
                print(f"✅ 創建裝備: {edata['name']}")
            except Exception as e:
                print(f"❌ 裝備創建失敗: {e}")

    # 💡 展示 Pydantic 驗證效果
    print("\n🔒 === Pydantic 驗證範例 ===")
    print("嘗試創建不合法的資料...")

    with character_manager.meta_provide(current_user, current_time):  # ty:ignore[unresolved-attribute]
        # 嘗試建立一個 HP 為負數的角色
        try:
            character_manager.create(  # ty:ignore[unresolved-attribute]
                {
                    "name": "壞資料角色",
                    "character_class": CharacterClass.WARRIOR.value,
                    "hp": -100,  # ❌ 負數 — Pydantic 驗證會攔截
                }
            )
            print("❌ 預期驗證失敗但沒有")
        except Exception as e:
            print(f"✅ 驗證攔截成功: {e}")

        # 嘗試建立一個名稱為空的角色
        try:
            character_manager.create(  # ty:ignore[unresolved-attribute]
                {
                    "name": "   ",  # ❌ 空白名稱 — Pydantic 驗證會攔截
                    "character_class": CharacterClass.MAGE.value,
                }
            )
            print("❌ 預期驗證失敗但沒有")
        except Exception as e:
            print(f"✅ 驗證攔截成功: {e}")


def configure_crud():
    """設定全域 crud 實例"""
    storage_type = input("使用memory or disk storage？ [[M]emory/(D)isk]: ")

    if storage_type.lower() in ("d", "disk"):
        storage_path = (
            input("請輸入磁盤存儲路徑（預設: ./rpg_pydantic_data）: ")
            or "./rpg_pydantic_data"
        )
        storage_factory = DiskStorageFactory(rootdir=storage_path)
    else:
        storage_factory = None

    mq_factory = SimpleMessageQueueFactory()

    crud.configure(storage_factory=storage_factory, message_queue_factory=mq_factory)

    # 添加額外的路由模板
    crud.add_route_template(GraphQLRouteTemplate())
    crud.add_route_template(BlobRouteTemplate())
    crud.add_route_template(MigrateRouteTemplate())

    # 🎯 重點：直接傳入 Pydantic BaseModel！
    # AutoCRUD 會自動：
    # 1. 使用 Pydantic model 作為驗證器
    # 2. create/update 接受 dict 或 Pydantic instance
    # 3. get 回傳 Pydantic instance
    # 4. 保留 Annotated 元數據（Ref, DisplayName 等）
    crud.add_model(
        Character,  # ← Pydantic BaseModel，直接傳入即可！
        indexed_fields=[
            ("level", int),
            ("name", str),
            ("gold", int),
            ("guild_name", str | None),
            ("character_class", CharacterClass),
        ],  # ty:ignore[invalid-argument-type]
        # validator 不需要指定 — AutoCRUD 自動使用 Pydantic model
    )

    crud.add_model(Guild)
    crud.add_model(
        Skill,
        indexed_fields=[
            ("skname", str),
            ("required_level", int),
        ],
    )
    crud.add_model(Equipment)


def main():
    """主程序"""
    print("🎮 === RPG 遊戲 API 系統（Pydantic 版）啟動 === ⚔️")
    print("📦 使用 Pydantic BaseModel → 自動驗證 + 高效存儲")

    app = FastAPI(
        title="⚔️ RPG 遊戲管理系統（Pydantic 版）",
        description="""
        🎮 **使用 Pydantic 定義模型的 RPG 遊戲管理 API**
        
        與 rpg_game_api.py 的差異：
        - 📦 使用 **Pydantic BaseModel** 定義模型
        - ✅ 使用 **@field_validator** (Pydantic v2) 進行資料驗證
        - 🔄 create/update 接受 **dict 或 Pydantic instance**
        - 📤 get 回傳 **Pydantic instance**
        - 🏷️ Pydantic **Discriminated Union** 完整支援
        
        🎯 所有 AutoCRUD 功能完整支援：
        - Ref 關聯、DisplayName、Binary 二進位資料
        - 版本控制、搜尋索引、QueryBuilder
        """,
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    configure_crud()
    crud.apply(app)
    crud.openapi(app)

    ans = input("需要創建示範數據嗎？[y/N]: ")
    if ans.lower() == "y":
        create_sample_data()

    print("\n🚀 === 服務器啟動成功 === 🚀")
    print("📖 OpenAPI 文檔: http://localhost:8000/docs")
    print("⚔️ 角色 API: http://localhost:8000/character/data")
    print("🏰 公會 API: http://localhost:8000/guild/data")
    print("🗡️ 裝備 API: http://localhost:8000/equipment/data")
    print("🎯 技能 API: http://localhost:8000/skill/data")
    print("\n💡 提示: 試著建立一個 HP 為負數的角色，")
    print("   Pydantic 的 @field_validator 會自動攔截不合法資料！")

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    main()
