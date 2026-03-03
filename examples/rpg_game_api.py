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
    http://localhost:8000/skill - 技能 API
    http://localhost:8000/game-event - 遊戲事件任務 API
"""

import datetime as dt
import random
import time
from enum import Enum
from typing import Annotated, Optional

import msgspec
import uvicorn
from fastapi import Body, FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from msgspec import Struct
from pydantic_core import Url

from autocrud import IValidator, OnDelete, Ref, Schema, crud, struct_to_pydantic

# 預先將 Struct 轉為 Pydantic Model，供 FastAPI 端點作為型別標註使用
# 直接在 annotation 寫 struct_to_pydantic(Skill) 會被 Pylance 報 reportInvalidTypeForm
from autocrud.crud.route_templates.blob import BlobRouteTemplate
from autocrud.crud.route_templates.graphql import GraphQLRouteTemplate
from autocrud.crud.route_templates.migrate import MigrateRouteTemplate
from autocrud.message_queue.basic import DelayRetry
from autocrud.message_queue.rabbitmq import RabbitMQMessageQueueFactory
from autocrud.message_queue.simple import SimpleMessageQueueFactory
from autocrud.query import QB
from autocrud.resource_manager.storage_factory import DiskStorageFactory
from autocrud.types import (
    Binary,
    DisplayName,
    Job,
    RefType,
    Resource,
    Unique,
)


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


class ActiveSkillData(Struct, tag="active"):
    """主動技能數據"""

    mp_cost: int = 0
    cooldown_seconds: int = 0
    damage: int = 0


class PassiveSkillData(Struct, tag="passive"):
    """被動技能數據"""

    buff_percentage: int = 0  # 增益百分比


class UltimateSkillData(Struct, tag="ultimate"):
    """終極技能數據"""

    mp_cost: int = 0
    cooldown_seconds: int = 0
    damage: int = 0
    area_of_effect: bool = False  # 是否為範圍攻擊


class Skill(Struct):
    """遊戲技能（使用 Union 區分技能類型）"""

    skname: Annotated[str, DisplayName()]
    detail: ActiveSkillData | PassiveSkillData | UltimateSkillData
    description: str = ""
    required_level: int = 1
    required_class: Optional[CharacterClass] = None  # None = 所有職業可學


class Equipment(Struct, tag=True):
    """遊戲裝備"""

    name: Annotated[str, DisplayName()]
    rarity: ItemRarity
    # 1:N 關係：裝備歸屬某個角色（可為空代表在商店中）
    owner_id: Annotated[str | None, Ref("character", on_delete=OnDelete.set_null)] = (
        None
    )
    character_class_req: Optional[CharacterClass] = None
    attack_bonus: int = 0
    defense_bonus: int = 0
    special_effects: list[str] = []  # 裝備特效列表
    price: int = 100
    icon: Optional[Binary] = None  # Binary 類型欄位


class Item(Struct, tag=True):
    """遊戲物品（裝備和消耗品的基類）"""

    name: Annotated[str, DisplayName()]
    description: str = ""
    price: int = 100
    icon: Optional[Binary] = None  # Binary 類型欄位


class Character(Struct):
    """遊戲角色"""

    name: Annotated[str, DisplayName(), Unique()]
    character_class: CharacterClass
    valueAD__x: int | str = 12
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
    # N:N 關係：角色學會的技能（透過 skill resource_id 列表）
    skill_ids: list[Annotated[str, Ref("skill")]] = []
    equipments: list[Equipment | Item] = []  # 角色裝備列表（嵌入式，非 Ref）
    created_at: dt.datetime = dt.datetime.now()


class Dog(Struct, tag=True, kw_only=True):
    """遊戲中的寵物系統示例"""

    name: Annotated[str, DisplayName()]
    breed: str
    level: int = 1
    hp: int = 100
    mp: int = 50
    attack: int = 10
    defense: int = 5
    owner_id: Annotated[str, Ref("character", on_delete=OnDelete.set_null)]


class Mount(Struct, tag=True, kw_only=True):
    """遊戲中的坐騎系統示例"""

    name: Annotated[str, DisplayName()]
    species: str
    speed: int = 10
    stamina: int = 100
    owner_id: Annotated[str, Ref("character", on_delete=OnDelete.set_null)]


Pet = Mount | Dog  # 寵物可以是坐騎或寵物狗


class Guild(Struct):
    """遊戲公會"""

    name: Annotated[str, DisplayName()]
    description: str
    leader: str
    member_count: int = 1
    level: int = 1
    treasury: int = 1000
    founded_at: dt.datetime = dt.datetime.now()


# ===== Message Queue 使用範例：遊戲事件系統 =====


class GameEventType(Enum):
    """遊戲事件類型"""

    LEVEL_UP = "level_up"  # 角色升級
    GUILD_REWARD = "guild_reward"  # 公會獎勵
    DAILY_LOGIN = "daily_login"  # 每日登入獎勵
    QUEST_COMPLETE = "quest_complete"  # 任務完成
    EQUIPMENT_ENHANCE = "equipment_enhance"  # 裝備強化
    RAID_BOSS = "raid_boss"  # 團隊 BOSS 戰（需要等待隊伍集結）
    SERVER_MAINTENANCE = "server_maintenance"  # 伺服器維護（需要延遲處理）


class EventBodyA(Struct, tag=True):
    """事件類型 A 的專屬數據"""

    extra_info_a: str
    extra_value_a: int


class EventBodyB(Struct, tag=True):
    """事件類型 B 的專屬數據"""

    some_field: str
    cooldown_seconds: int


class EventBodyX(Struct, tag=True):
    """事件類型 X 的專屬數據"""

    good: str
    great: int


class GameEventPayload(Struct):
    """遊戲事件載荷數據"""

    event_type: GameEventType
    character_name: str
    character_id: Annotated[
        Optional[str], Ref("character", ref_type=RefType.revision_id)
    ]
    # event_x2: EventBodyX
    # event_x3: list[EventBodyX | EventBodyB | EventBodyA] | EventBodyX | EventBodyB
    # event_x4: list[EventBodyX | EventBodyB | EventBodyA] | EventBodyX
    # event_x5: list[EventBodyA] | EventBodyX
    # event_x6: list[EventBodyA] | EventBodyX | EventBodyX  | None
    # event_x7: list[EventBodyA] | dict[str, EventBodyX]
    # event_x8: list[list[list[EventBodyX | EventBodyB] | EventBodyB | EventBodyA]]
    description: str
    reward_gold: int = 0
    reward_exp: int = 0
    extra_data: dict = {}
    event_body: EventBodyA | EventBodyB | None = None
    event_x: EventBodyX | None = None


class GameEvent(Job[GameEventPayload]):
    """遊戲事件任務（使用 Message Queue 處理）"""

    pass


# ===== 資料驗證器 =====


def validate_character(data: Character) -> None:
    """角色資料驗證（Callable 風格）"""
    errors = []
    if not data.name.strip():
        errors.append("角色名稱不可為空")
    if data.level < 1 or data.level > 999:
        errors.append("等級必須在 1~999 之間")
    if data.hp < 0:
        errors.append("生命值不可為負數")
    if data.mp < 0:
        errors.append("魔力值不可為負數")
    if data.attack < 0:
        errors.append("攻擊力不可為負數")
    if data.defense < 0:
        errors.append("防禦力不可為負數")
    if data.gold < 0:
        errors.append("金幣不可為負數")
    if data.experience < 0:
        errors.append("經驗值不可為負數")
    if errors:
        raise ValueError("; ".join(errors))


def validate_guild(data: Guild) -> None:
    """公會資料驗證（Callable 風格）"""
    errors = []
    if not data.name.strip():
        errors.append("公會名稱不可為空")
    if data.member_count < 1:
        errors.append("公會成員數至少為 1")
    if data.level < 1:
        errors.append("公會等級至少為 1")
    if data.treasury < 0:
        errors.append("公會金庫不可為負數")
    if errors:
        raise ValueError("; ".join(errors))


class SkillValidator(IValidator):
    """技能資料驗證（IValidator 風格）"""

    def validate(self, data: Skill) -> None:
        errors = []
        if not data.skname.strip():
            errors.append("技能名稱不可為空")
        if data.required_level < 1:
            errors.append("技能需求等級至少為 1")
        if isinstance(data.detail, ActiveSkillData):
            if data.detail.mp_cost < 0:
                errors.append("MP 消耗不可為負數")
            if data.detail.cooldown_seconds < 0:
                errors.append("冷卻時間不可為負數")
        elif isinstance(data.detail, UltimateSkillData):
            if data.detail.mp_cost < 0:
                errors.append("MP 消耗不可為負數")
            if data.detail.damage <= 0:
                errors.append("終極技能傷害必須大於 0")
        if errors:
            raise ValueError("; ".join(errors))


def validate_equipment(data: Equipment) -> None:
    """裝備資料驗證（Callable 風格）"""
    errors = []
    if not data.name.strip():
        errors.append("裝備名稱不可為空")
    if data.price < 0:
        errors.append("裝備價格不可為負數")
    if data.attack_bonus < 0:
        errors.append("攻擊加成不可為負數")
    if data.defense_bonus < 0:
        errors.append("防禦加成不可為負數")
    if errors:
        raise ValueError("; ".join(errors))


def get_random_image():
    import httpx

    r = httpx.get("https://picsum.photos/200", follow_redirects=True, timeout=2)
    return r.content


character_ids = {}  # name -> resource_id
character_revs = {}  # name -> RefRevision
history_seed = 20240216


def generate_character_update_history(
    character_manager,
    current_user: str,
    base_time: dt.datetime,
    seed: int = history_seed,
    min_updates: int = 5,
    max_updates: int = 30,
) -> None:
    rng = random.Random(seed)
    for idx, (name, resource_id) in enumerate(character_ids.items()):
        revisions: list[str] = []
        if name in character_revs:
            revisions.append(character_revs[name])

        update_count = rng.randint(min_updates, max_updates)
        current_time = base_time + dt.timedelta(hours=idx)

        for _ in range(update_count):
            current_time += dt.timedelta(minutes=rng.randint(15, 180))
            with character_manager.meta_provide(current_user, current_time):
                if len(revisions) > 1 and rng.random() < 0.35:
                    branch_target = rng.choice(revisions[:-1])
                    character_manager.switch(resource_id, branch_target)

            parent_info = character_manager.get_revision_info(resource_id)
            if current_time <= parent_info.created_time:
                current_time = parent_info.created_time + dt.timedelta(minutes=1)

            with character_manager.meta_provide(current_user, current_time):
                resource = character_manager.get(resource_id).data
                updated = msgspec.structs.replace(
                    resource,
                    level=min(999, resource.level + rng.randint(0, 2)),
                    experience=max(0, resource.experience + rng.randint(50, 500)),
                    gold=max(0, resource.gold + rng.randint(-200, 800)),
                    hp=max(1, resource.hp + rng.randint(-20, 80)),
                    mp=max(0, resource.mp + rng.randint(-15, 60)),
                    attack=max(0, resource.attack + rng.randint(-2, 6)),
                    defense=max(0, resource.defense + rng.randint(-2, 6)),
                )
                info = character_manager.update(resource_id, updated)
                revisions.append(info.revision_id)
                character_revs[name] = info.revision_id


def create_sample_data():
    """創建示範數據"""
    print("🎮 創建示範遊戲數據...")

    # 取得資源管理器
    guild_manager = crud.get_resource_manager(Guild)
    skill_manager = crud.get_resource_manager(Skill)
    character_manager = crud.get_resource_manager(Character)
    equipment_manager = crud.get_resource_manager(Equipment)
    pet_manager = crud.get_resource_manager(Pet)

    if not all(
        [
            guild_manager,
            skill_manager,
            character_manager,
            equipment_manager,
            pet_manager,
        ]
    ):
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
    guild_ids = {}  # name -> resource_id
    with guild_manager.meta_provide(current_user, current_time):
        for guild in guilds:
            try:
                info = guild_manager.create(guild)
                guild_ids[guild.name] = info.resource_id
                print(f"✅ 創建公會: {guild.name}")
            except Exception as e:
                print(f"❌ 公會創建失敗: {e}")

    # 🎯 創建技能
    skills = [
        Skill(
            skname="火球術",
            detail=ActiveSkillData(mp_cost=30, cooldown_seconds=5, damage=150),
            description="向敵人發射一顆強力火球",
            required_level=10,
            required_class=CharacterClass.MAGE,
        ),
        Skill(
            skname="治癒之光",
            detail=ActiveSkillData(mp_cost=25, cooldown_seconds=8),
            description="恢復自身或隊友的生命值",
            required_level=5,
        ),
        Skill(
            skname="重擊",
            detail=ActiveSkillData(mp_cost=20, cooldown_seconds=3, damage=200),
            description="對單一敵人造成巨額物理傷害",
            required_level=15,
            required_class=CharacterClass.WARRIOR,
        ),
        Skill(
            skname="精準射擊",
            detail=ActiveSkillData(mp_cost=15, cooldown_seconds=2, damage=120),
            description="100% 命中的遠程攻擊",
            required_level=8,
            required_class=CharacterClass.ARCHER,
        ),
        Skill(
            skname="CRUD 終極奧義",
            detail=UltimateSkillData(
                mp_cost=100, cooldown_seconds=60, damage=9999, area_of_effect=True
            ),
            description="一鍵生成完美的 RESTful API，對所有敵人造成毀滅性打擊",
            required_level=50,
            required_class=CharacterClass.DATA_KEEPER,
        ),
        Skill(
            skname="鋼鐵意志",
            detail=PassiveSkillData(buff_percentage=20),
            description="永久提升防禦力 20%",
            required_level=20,
            required_class=CharacterClass.WARRIOR,
        ),
        Skill(
            skname="魔力親和",
            detail=PassiveSkillData(buff_percentage=15),
            description="永久降低所有技能 MP 消耗 15%",
            required_level=15,
            required_class=CharacterClass.MAGE,
        ),
        Skill(
            skname="經驗加成",
            detail=PassiveSkillData(buff_percentage=10),
            description="獲得的經驗值增加 10%",
            required_level=1,
        ),
    ]

    skill_ids = {}  # name -> resource_id
    with skill_manager.meta_provide(current_user, current_time):
        for skill in skills:
            try:
                info = skill_manager.create(skill)
                skill_ids[skill.skname] = info.resource_id
                print(f"✅ 創建技能: {skill.skname} [{type(skill.detail).__name__}]")
            except Exception as e:
                print(f"❌ 技能創建失敗: {e}")

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
            guild_id=guild_ids.get("AutoCRUD 開發者聯盟"),
            guild_name="AutoCRUD 開發者聯盟",
            special_ability="🚀 一鍵生成完美 API",
            skill_ids=[
                skill_ids.get("CRUD 終極奧義", ""),
                skill_ids.get("經驗加成", ""),
                skill_ids.get("治癒之光", ""),
            ],
            equipments=[
                Equipment(
                    name="AutoCRUD 神劍",
                    rarity=ItemRarity.AUTOCRUD,
                    attack_bonus=200,
                    defense_bonus=50,
                    special_effects=["🚀 自動生成 CRUD 操作", "⚡ API 響應速度 +100%"],
                ),
                Equipment(
                    name="版本控制護符",
                    rarity=ItemRarity.LEGENDARY,
                    defense_bonus=100,
                    special_effects=["📖 自動追蹤所有變更", "🔄 一鍵回滾"],
                ),
                Item(
                    name="神秘的 AutoCRUD 卷軸",
                    description="一卷記載著 AutoCRUD 最高機密的古老卷軸，使用後可能會帶來意想不到的效果",
                    price=999999,
                    icon=Binary(data=get_random_image()),
                ),
            ],
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
            guild_id=guild_ids.get("數據庫騎士團"),
            guild_name="數據庫騎士團",
            special_ability="💾 瞬間優化查詢",
            skill_ids=[
                skill_ids.get("火球術", ""),
                skill_ids.get("魔力親和", ""),
                skill_ids.get("治癒之光", ""),
            ],
            equipments=[
                Equipment(
                    name="數據庫守護盾",
                    rarity=ItemRarity.LEGENDARY,
                    defense_bonus=150,
                    special_effects=["🛡️ 防止 SQL 注入攻擊", "💾 查詢效能 +200%"],
                ),
                Item(
                    name="easy mode 模組",
                    description="一個神奇的模組，安裝後遊戲將變得非常簡單，適合新手玩家",
                    price=500000,
                    icon=Binary(data=get_random_image()),
                ),
            ],
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
            guild_id=guild_ids.get("API 法師學院"),
            guild_name="API 法師學院",
            special_ability="⚡ HTTP 狀態碼斬",
            skill_ids=[
                skill_ids.get("重擊", ""),
                skill_ids.get("鋼鐵意志", ""),
                skill_ids.get("經驗加成", ""),
            ],
            equipments=[
                Equipment(
                    name="API 魔法杖",
                    rarity=ItemRarity.EPIC,
                    attack_bonus=100,
                    defense_bonus=30,
                    special_effects=["✨ 法術冷卻時間減少 50%"],
                ),
                Item(
                    name="未鑑定的神秘裝備",
                    description="一個普通的物品，沒有什麼特別的效果",
                    price=1000,
                    icon=Binary(data=get_random_image()),
                ),
                Equipment(
                    name="精準查詢弓",
                    rarity=ItemRarity.RARE,
                    attack_bonus=80,
                    special_effects=["🎯 100% 命中率"],
                ),
            ],
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
            guild_id=guild_ids.get("AutoCRUD 開發者聯盟"),
            guild_name="AutoCRUD 開發者聯盟",
            special_ability="🎯 精準數據建模",
            skill_ids=[
                skill_ids.get("精準射擊", ""),
                skill_ids.get("經驗加成", ""),
            ],
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
            guild_id=guild_ids.get("新手村互助會"),
            guild_name="新手村互助會",
            special_ability="🌱 學習能力超強",
            skill_ids=[
                skill_ids.get("經驗加成", ""),
            ],
            equipments=[
                Equipment(
                    name="新手村木劍",
                    rarity=ItemRarity.COMMON,
                    attack_bonus=5,
                    special_effects=["🌱 經驗值獲得 +10%"],
                ),
            ],
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
            guild_id=guild_ids.get("API 法師學院"),
            guild_name="API 法師學院",
            special_ability="🔮 自動生成文檔",
            skill_ids=[
                skill_ids.get("火球術", ""),
                skill_ids.get("治癒之光", ""),
            ],
        ),
    ]

    # 創建角色數據
    with character_manager.meta_provide(
        current_user, current_time - dt.timedelta(days=90)
    ):
        for character in characters:
            try:
                info = character_manager.create(character)
                character_ids[character.name] = info.resource_id
                character_revs[character.name] = info.revision_id
                print(f"✅ 創建角色: {character.name} (Lv.{character.level})")
            except Exception as e:
                print(f"❌ 角色創建失敗: {e}")

    # Generate deterministic update history for revision tree testing
    generate_character_update_history(
        character_manager,
        current_user,
        dt.datetime(2024, 1, 1, 12, 0, 0),
    )

    # 🗡️ 創建裝備
    # 創建一個簡單的 1x1 PNG圖片 作為圖標

    equipment_list = [
        Equipment(
            name="AutoCRUD 神劍",
            rarity=ItemRarity.AUTOCRUD,
            owner_id=character_ids.get("AutoCRUD 大神"),  # 1:N — 歸屬角色
            character_class_req=CharacterClass.DATA_KEEPER,
            attack_bonus=200,
            defense_bonus=50,
            special_effects=[
                "🚀 自動生成 CRUD 操作",
                "⚡ API 響應速度 +100%",
                "📊 自動生成文檔",
            ],
            price=1000000,
            icon=Binary(data=get_random_image()),
        ),
        Equipment(
            name="數據庫守護盾",
            rarity=ItemRarity.LEGENDARY,
            owner_id=character_ids.get("資料庫女王"),  # 1:N — 歸屬角色
            character_class_req=CharacterClass.WARRIOR,
            attack_bonus=20,
            defense_bonus=150,
            special_effects=["🛡️ 防止 SQL 注入攻擊", "💾 查詢效能 +200%"],
            price=500000,
            icon=Binary(data=get_random_image()),
        ),
        Equipment(
            name="API 魔法杖",
            rarity=ItemRarity.EPIC,
            owner_id=character_ids.get("RESTful 劍聖"),  # 1:N — 歸屬角色
            character_class_req=CharacterClass.MAGE,
            attack_bonus=100,
            defense_bonus=30,
            special_effects=["✨ 法術冷卻時間減少 50%", "🔮 魔力恢復速度 +30%"],
            price=250000,
            icon=Binary(data=get_random_image()),
        ),
        Equipment(
            name="精準查詢弓",
            rarity=ItemRarity.RARE,
            owner_id=character_ids.get("Schema 設計師"),  # 1:N — 歸屬角色
            character_class_req=CharacterClass.ARCHER,
            attack_bonus=80,
            special_effects=["🎯 100% 命中率", "🏹 穿透防禦 20%"],
            price=150000,
            icon=Binary(data=get_random_image()),
        ),
        Equipment(
            name="新手村木劍",
            rarity=ItemRarity.COMMON,
            owner_id=character_ids.get("新手小白"),  # 1:N — 歸屬角色
            attack_bonus=5,
            special_effects=["🌱 經驗值獲得 +10%"],
            price=50,
            icon=Binary(data=get_random_image()),
        ),
        Equipment(
            name="傳說中的未鑑定裝備",
            rarity=ItemRarity.LEGENDARY,
            owner_id=None,  # 無人持有 — 在商店中
            attack_bonus=999,
            defense_bonus=999,
            special_effects=["❓ 未鑑定效果"],
            price=9999999,
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

    # 🐾 創建寵物
    pets: list[Pet] = [
        Dog(
            name="像素柴犬",
            breed="柴犬",
            level=15,
            hp=300,
            mp=50,
            attack=45,
            defense=30,
            owner_id=character_ids.get("AutoCRUD 大神"),
        ),
        Dog(
            name="數據獵犬",
            breed="德國牧羊犬",
            level=25,
            hp=500,
            mp=80,
            attack=70,
            defense=55,
            owner_id=character_ids.get("資料庫女王"),
        ),
        Dog(
            name="除錯小柯基",
            breed="柯基",
            level=8,
            hp=180,
            mp=30,
            attack=20,
            defense=15,
            owner_id=character_ids.get("新手小白"),
        ),
        Mount(
            name="API 飛龍",
            species="火龍",
            speed=80,
            stamina=500,
            owner_id=character_ids.get("RESTful 劍聖"),
        ),
        Mount(
            name="查詢獨角獸",
            species="獨角獸",
            speed=60,
            stamina=400,
            owner_id=character_ids.get("Schema 設計師"),
        ),
        Mount(
            name="版本控制飛馬",
            species="飛馬",
            speed=70,
            stamina=450,
            owner_id=character_ids.get("AutoCRUD 大神"),
        ),
        Dog(
            name="SQL 注入偵測犬",
            breed="邊境牧羊犬",
            level=40,
            hp=600,
            mp=120,
            attack=90,
            defense=70,
            owner_id=character_ids.get("API 魔法師"),
        ),
        Mount(
            name="新手村小毛驢",
            species="毛驢",
            speed=20,
            stamina=200,
            owner_id=character_ids.get("新手小白"),
        ),
    ]

    # 創建寵物數據
    with pet_manager.meta_provide(current_user, current_time):
        for pet in pets:
            try:
                pet_manager.create(pet)
                kind = "🐕 狗狗" if isinstance(pet, Dog) else "🐴 坐騎"
                print(f"✅ 創建寵物: {pet.name} [{kind}]")
            except Exception as e:
                print(f"❌ 寵物創建失敗: {e}")


def demonstrate_qb_queries():
    """展示 QueryBuilder (QB) 的使用範例"""
    print("\n🔍 === QueryBuilder (QB) 使用範例 ===")

    character_manager = crud.get_resource_manager(Character)
    if not character_manager:
        print("❌ 角色管理器未找到")
        return

    print("\n📊 範例 1: 基本查詢 - 搜尋高等級角色 (level >= 50)")
    query1 = QB["level"].gte(50).limit(10)
    metas1 = character_manager.search_resources(query1)
    print(f"   找到 {len(metas1)} 個高等級角色:")
    for meta in metas1:
        resource = character_manager.get(meta.resource_id)
        print(f"   - {resource.data.name}: Lv.{resource.data.level}")

    print(
        "\n📊 範例 2: 複雜條件 - 中等級且有公會的角色 (20 <= level <= 80 AND guild_name)"
    )
    query2 = (QB["level"].between(20, 80) & QB["guild_name"].is_not_null()).limit(5)
    metas2 = character_manager.search_resources(query2)
    print(f"   找到 {len(metas2)} 個符合條件的角色:")
    for meta in metas2:
        resource = character_manager.get(meta.resource_id)
        print(
            f"   - {resource.data.name}: Lv.{resource.data.level}, 公會: {resource.data.guild_name}"
        )

    print(
        "\n📊 範例 3: 使用 filter - 富有的戰士 (gold > 100000 AND character_class == WARRIOR)"
    )
    query3 = (
        QB["gold"]
        .gt(100000)
        .filter(
            QB["character_class"].eq(CharacterClass.WARRIOR),
        )
        .limit(5)
    )
    metas3 = character_manager.search_resources(query3)
    print(f"   找到 {len(metas3)} 個富有的戰士:")
    for meta in metas3:
        resource = character_manager.get(meta.resource_id)
        print(
            f"   - {resource.data.name}: 金幣 {resource.data.gold}, {resource.data.character_class.value}"
        )

    print("\n📊 範例 4: OR 查詢 - 高等級或高金幣 (level >= 80 OR gold >= 500000)")
    query4 = (QB["level"].gte(80) | QB["gold"].gte(500000)).limit(5)
    metas4 = character_manager.search_resources(query4)
    print(f"   找到 {len(metas4)} 個角色:")
    for meta in metas4:
        resource = character_manager.get(meta.resource_id)
        print(
            f"   - {resource.data.name}: Lv.{resource.data.level}, 金幣 {resource.data.gold}"
        )

    print("\n📊 範例 5: 排序 - 按等級降序，取前3名")
    query5 = QB["level"].gte(1).sort("-level").limit(3)  # 字串排序：-表示降序
    metas5 = character_manager.search_resources(query5)
    print("   🏆 等級排行榜 TOP 3:")
    for i, meta in enumerate(metas5, 1):
        resource = character_manager.get(meta.resource_id)
        print(
            f"   {i}. {resource.data.name}: Lv.{resource.data.level} - {resource.data.special_ability}"
        )

    print("\n📊 範例 6: 使用 QB 內建方法排序 - 按金幣降序")
    query6 = QB["gold"].gte(1).sort(QB["gold"].desc()).limit(3)
    metas6 = character_manager.search_resources(query6)
    print("   💰 財富排行榜 TOP 3:")
    for i, meta in enumerate(metas6, 1):
        resource = character_manager.get(meta.resource_id)
        print(f"   {i}. {resource.data.name}: {resource.data.gold} 金幣")

    print("\n📊 範例 7: 分頁查詢 - 第1頁，每頁2個")
    query7 = QB["level"].gte(1).sort("-created_at").page(1, 2)  # 第1頁，每頁2個
    metas7 = character_manager.search_resources(query7)
    print(f"   第1頁結果 (共 {len(metas7)} 個):")
    for meta in metas7:
        resource = character_manager.get(meta.resource_id)
        print(f"   - {resource.data.name}")

    print("\n📊 範例 8: 字串包含查詢 - 名字包含 '大' 的角色")
    query8 = QB["name"].contains("大").limit(5)
    metas8 = character_manager.search_resources(query8)
    print(f"   找到 {len(metas8)} 個角色:")
    for meta in metas8:
        resource = character_manager.get(meta.resource_id)
        print(f"   - {resource.data.name}")

    print("\n📊 範例 9: IN 查詢 - 特定公會的成員")
    target_guilds = ["AutoCRUD 開發者聯盟", "API 法師學院"]
    query9 = QB["guild_name"].in_(target_guilds).limit(10)
    metas9 = character_manager.search_resources(query9)
    print(f"   找到 {len(metas9)} 個目標公會成員:")
    for meta in metas9:
        resource = character_manager.get(meta.resource_id)
        print(f"   - {resource.data.name} ({resource.data.guild_name})")

    print("\n📊 範例 10: 使用元數據查詢 - 最近創建的角色")
    query10 = (
        QB.created_time()
        .gte(dt.datetime.now() - dt.timedelta(hours=1))
        .sort(QB.created_time().desc())
        .limit(3)
    )
    metas10 = character_manager.search_resources(query10)
    print(f"   最近1小時內創建的角色 ({len(metas10)} 個):")
    for meta in metas10:
        resource = character_manager.get(meta.resource_id)
        print(
            f"   - {resource.data.name}, 創建時間: {meta.created_time.strftime('%Y-%m-%d %H:%M:%S')}"
        )

    print("\n📊 範例 11: exclude 使用 - 排除新手村的角色")
    query11 = (
        QB["level"]
        .gte(1)
        .exclude(QB["guild_name"].eq("新手村互助會"))
        .sort("-level")
        .limit(5)
    )
    metas11 = character_manager.search_resources(query11)
    print(f"   找到 {len(metas11)} 個非新手村角色:")
    for meta in metas11:
        resource = character_manager.get(meta.resource_id)
        print(f"   - {resource.data.name}: {resource.data.guild_name or '無公會'}")

    print("\n📊 範例 12: first() 使用 - 取得等級最高的角色")
    query12 = QB["level"].gte(1).sort("-level").first()
    metas12 = character_manager.search_resources(query12)
    if metas12:
        top_meta = metas12[0]
        top = character_manager.get(top_meta.resource_id)
        print(f"   🏆 最強角色: {top.data.name} (Lv.{top.data.level})")
        print(
            f"   屬性: HP={top.data.hp}, 攻擊={top.data.attack}, 防禦={top.data.defense}"
        )
        print(f"   特殊能力: {top.data.special_ability}")

    print("\n✅ QueryBuilder 範例演示完成！")
    print("\n💡 提示: QB 提供了強大且直觀的查詢接口：")
    print("   - 使用 QB['field'] 或 QB.field() 存取欄位")
    print("   - 支援 Python 運算符: ==, !=, >, >=, <, <=, &, |, ~")
    print("   - 提供豐富的方法: contains, in_, between, is_null 等")
    print("   - 支援排序: sort(), order_by(), asc(), desc()")
    print("   - 支援分頁: limit(), offset(), page(), first()")
    print("   - 提供元數據查詢: QB.created_time(), QB.status() 等\n")


def configure_crud():
    """設定全域 crud 實例"""
    storage_type = input("使用memory or disk storage？ [[M]emory/(D)isk]: ")

    if storage_type.lower() in ("d", "disk"):
        storage_path = (
            input("請輸入磁盤存儲路徑（預設: ./rpg_game_data）: ") or "./rpg_game_data"
        )
        storage_factory = DiskStorageFactory(rootdir=storage_path)
    else:
        storage_factory = None

    mq_type = input("使用rabbit mq嗎？ [y/N]: ")
    if mq_type.lower() == "y":
        mq_factory = RabbitMQMessageQueueFactory()
    else:
        mq_factory = SimpleMessageQueueFactory()

    # 使用全域 crud 實例的 configure 方法
    crud.configure(storage_factory=storage_factory, message_queue_factory=mq_factory)

    # 添加額外的路由模板
    crud.add_route_template(GraphQLRouteTemplate())
    crud.add_route_template(BlobRouteTemplate())
    crud.add_route_template(MigrateRouteTemplate())

    # 註冊模型
    # 推薦做法：使用 Schema 將 resource type、version、validator 統一管理
    # 注意：使用 QB 查詢的欄位必須建立索引
    crud.add_model(
        Schema(Character, "v1", validator=validate_character),  # Callable 風格驗證器
        indexed_fields=[
            ("level", int),  # 用於等級查詢、排序
            ("name", str),  # 用於名稱搜尋、字串包含查詢
            ("gold", int),  # 用於金幣查詢、排序
            ("guild_name", str | None),  # 用於公會查詢、is_not_null 檢查
            ("character_class", CharacterClass),  # 用於職業篩選
            # guild_id 會由 Ref 自動索引，不需手動添加
        ],
    )
    crud.add_model(Schema(Guild, "v1", validator=validate_guild))  # Callable 風格驗證器
    crud.add_model(
        Schema(Skill, "v1", validator=SkillValidator()),  # IValidator 風格驗證器
        indexed_fields=[
            ("name", str),
            ("required_level", int),
        ],
    )
    crud.add_model(
        Schema(Equipment, "v1", validator=validate_equipment)
    )  # Callable 風格驗證器
    crud.add_model(
        Schema(Pet, "v1"),
        name="pet",
        indexed_fields=[
            ("name", str),
            ("level", int),
        ],
    )
    crud.add_model(
        Schema(Job[Pet], "v1"),
        name="pet-job",
    )

    # 註冊遊戲事件任務模型（使用 Message Queue）
    # 注意：需要提供 job_handler 才會啟用 message queue
    # 這裡先用一個簡單的佔位函數，實際處理會在背景執行緒中進行
    crud.add_model(
        GameEvent,
        indexed_fields=[("status", str)],
        job_handler=process_game_event,
    )

    @crud.create_action("character", label="New Character1", path="/{name}/new")
    async def create_new_character1(
        name: Annotated[str, Ref("equipment")],
    ):
        return Character(
            name=name,
            character_class=CharacterClass.WARRIOR,
        )

    @crud.create_action("character", label="New Character2")
    async def create_new_character2(
        name: Annotated[str, Ref("equipment")],
    ):
        return Character(
            name=name,
            character_class=CharacterClass.WARRIOR,
        )

    @crud.create_action("character", label="New Character3")
    async def create_new_character4(
        x: int | str,
        y: Url,
        name: Annotated[str, Body(embed=True), Ref("equipment")],
        z: UploadFile,
        f: struct_to_pydantic(Skill),  # type: ignore[reportInvalidTypeForm]
    ):
        return Character(
            name=f"{name} ({x}, {y} {z.size} {f})",
            character_class=CharacterClass.WARRIOR,
        )


def process_game_event(event_resource: Resource[GameEvent]):
    """
    處理遊戲事件的背景工作函數

    這個函數會在背景執行緒中運行，從 message queue 取出事件並處理

    DelayRetry 使用範例：
    - 當需要延遲處理時，拋出 DelayRetry(delay_seconds=N)
    - 系統會在 N 秒後自動重新執行此事件
    - 適用於需要等待外部資源、隊伍集結、冷卻時間等場景
    """
    event = event_resource.data
    payload = event.payload

    print(f"\n🎮 處理遊戲事件: {payload.event_type.value}")
    print(f"   角色: {payload.character_name}")
    print(f"   描述: {payload.description}")
    print(f"   重試次數: {event.retries}")

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

    elif payload.event_type == GameEventType.RAID_BOSS:
        # 🎯 DelayRetry 範例 1: 團隊 BOSS 戰需要等待隊伍集結
        required_members = payload.extra_data.get("required_members", 5)
        current_members = payload.extra_data.get("current_members", 0)

        if current_members < required_members:
            wait_time = 10  # 等待 10 秒讓更多玩家加入
            print(f"   ⏳ 隊伍人數不足 ({current_members}/{required_members})")
            print(f"   等待 {wait_time} 秒後重試...")
            # 拋出 DelayRetry，系統會在指定秒數後重新執行
            raise DelayRetry(delay_seconds=wait_time)

        boss_name = payload.extra_data.get("boss_name", "未知 BOSS")
        print(f"   ⚔️ 團隊集結完成！開始挑戰 {boss_name}")
        print(f"   💰 擊敗 BOSS 獲得獎勵: {payload.reward_gold} 金幣")

    elif payload.event_type == GameEventType.SERVER_MAINTENANCE:
        # 🎯 DelayRetry 範例 2: 伺服器維護期間延遲處理
        maintenance_end_time = payload.extra_data.get("maintenance_end_time")

        if maintenance_end_time:
            # 檢查維護是否結束
            end_time = dt.datetime.fromisoformat(maintenance_end_time)
            now = dt.datetime.now()

            if now < end_time:
                delay = int((end_time - now).total_seconds())
                print(f"   🔧 伺服器維護中，預計 {delay} 秒後結束")
                print("   事件將延遲至維護結束後處理")
                # 延遲到維護結束
                raise DelayRetry(delay_seconds=min(delay, 30))  # 最多延遲30秒

        print("   ✅ 伺服器維護結束，獎勵已發放")
        print(
            f"   💰 補償獎勵: {payload.reward_gold} 金幣, {payload.reward_exp} 經驗值"
        )

    result_msg = f"✅ 事件處理成功: {payload.description}"
    print(f"   {result_msg}")


def create_sample_events():
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
            character_id=character_revs.get("新手小白").rpartition(":")[0],
            description="角色升級到 6 級",
            reward_exp=500,
            reward_gold=100,
        ),
        GameEventPayload(
            event_type=GameEventType.GUILD_REWARD,
            character_name="AutoCRUD 大神",
            character_id=character_revs.get("AutoCRUD 大神"),
            description="公會活動獎勵發放",
            reward_gold=5000,
        ),
        GameEventPayload(
            event_type=GameEventType.DAILY_LOGIN,
            character_name="API 魔法師",
            character_id=character_revs.get("API 魔法師").rpartition(":")[0],
            description="每日登入獎勵",
            reward_exp=200,
            reward_gold=50,
        ),
        GameEventPayload(
            event_type=GameEventType.QUEST_COMPLETE,
            character_name="RESTful 劍聖",
            character_id=character_revs.get("RESTful 劍聖"),
            description="完成任務：擊敗 SQL 注入怪獸",
            reward_exp=1000,
            reward_gold=500,
        ),
        GameEventPayload(
            event_type=GameEventType.EQUIPMENT_ENHANCE,
            character_name="Schema 設計師",
            character_id=character_revs.get("Schema 設計師").rpartition(":")[0],
            description="裝備強化成功",
            reward_gold=0,
            extra_data={"equipment_name": "精準查詢弓", "enhance_level": 5},
        ),
        # 🎯 DelayRetry 範例事件
        GameEventPayload(
            event_type=GameEventType.RAID_BOSS,
            character_name="AutoCRUD 開發者聯盟",
            character_id=None,
            description="挑戰世界 BOSS：代碼債務巨龍",
            reward_gold=50000,
            reward_exp=10000,
            extra_data={
                "boss_name": "代碼債務巨龍",
                "required_members": 5,
                "current_members": 2,  # 人數不足，會觸發 DelayRetry
            },
        ),
        GameEventPayload(
            event_type=GameEventType.SERVER_MAINTENANCE,
            character_id=None,
            character_name="全體玩家",
            description="伺服器維護補償獎勵",
            reward_gold=1000,
            reward_exp=500,
            extra_data={
                "maintenance_end_time": (
                    current_time + dt.timedelta(seconds=15)
                ).isoformat(),
            },
        ),
    ] * 30

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
    print("   背景工作執行緒將會自動處理這些事件")
    print("\n💡 DelayRetry 使用說明：")
    print("   - 團隊 BOSS 戰事件會因人數不足而延遲 10 秒重試")
    print("   - 伺服器維護事件會延遲到維護結束後處理")
    print("   - 你可以透過 GET /game-event/data 查看事件狀態和重試次數\n")


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

    # 加入 CORS middleware 允許前端存取
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 開發環境允許所有來源，生產環境應限制具體網域
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 設定全域 crud 實例
    configure_crud()

    # 應用到 FastAPI
    crud.apply(app)
    crud.openapi(app)
    crud.get_resource_manager(GameEvent).start_consume(block=False)

    # 創建示範數據
    ans = input("需要創建示範數據嗎？[y/N]: ")
    if ans.lower() == "y":
        create_sample_data()

    # 啟動遊戲事件處理背景工作執行緒
    print("\n🔄 啟動遊戲事件處理系統...")

    # 創建示範遊戲事件
    ans = input("需要創建示範遊戲事件嗎？[y/N]: ")
    if ans.lower() == "y":
        create_sample_events()

    # 展示 QueryBuilder 使用範例
    ans = input("需要展示 QueryBuilder (QB) 使用範例嗎？[y/N]: ")
    if ans.lower() == "y":
        demonstrate_qb_queries()

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
