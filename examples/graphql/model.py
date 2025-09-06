from dataclasses import dataclass
from enum import Enum
from typing import Optional


from autocrud import AutoCRUD


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
    special_ability: Optional[str] = None
    guild: Optional[str] = None
    equips: Optional[str] = None


@dataclass
class Guild:
    """遊戲公會"""

    name: str
    description: str
    leader: str
    member_count: int = 1
    level: int = 1
    treasury: int = 1000


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


_crudx = None


def get_crud():
    global _crudx
    if _crudx is None:
        # 創建 AutoCRUD 實例
        _crudx = AutoCRUD()

        # 註冊模型
        _crudx.add_model(Character, indexed_fields=[("guild", str)])
        _crudx.add_model(Guild)
        _crudx.add_model(Equipment)
    return _crudx
