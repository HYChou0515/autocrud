from typing import Optional
import strawberry
from autocrud.resource_manager.basic import DataSearchCondition, ResourceMetaSearchQuery
from examples.graphql.model import (
    Guild,
    get_crud,
    Character,
    CharacterClass,
    ItemRarity,
)


@strawberry.type
class GQL_Guild:
    id: str
    name: str
    description: str
    leader_id: str
    member_count: int = 1
    level: int = 1
    treasury: int = 1000

    @strawberry.field
    def leader(self) -> "GQL_Character":
        crudx = get_crud()
        mgr = crudx.get_manager(Character)
        d = mgr.get(self.leader_id)
        return GQL_Character(
            name=d.data.name,
            level=d.data.level,
            hp=d.data.hp,
            mp=d.data.mp,
            attack=d.data.attack,
            defense=d.data.defense,
            experience=d.data.experience,
            gold=d.data.gold,
            guild_id=d.data.guild,
        )

    @strawberry.field
    def size(self) -> int:
        crudx = get_crud()
        mgr = crudx.get_manager(Character)
        d = mgr.search_resources(
            ResourceMetaSearchQuery(
                data_conditions=[DataSearchCondition("guild", "eq", self.id)]
            )
        )
        return len(d)

    @strawberry.field
    def members(self) -> list["GQL_Character"]:
        crudx = get_crud()
        mgr = crudx.get_manager(Character)
        ks = mgr.search_resources(
            ResourceMetaSearchQuery(
                data_conditions=[DataSearchCondition("guild", "eq", self.id)]
            )
        )
        ds = [mgr.get(k.resource_id) for k in ks]
        return [
            GQL_Character(
                name=d.data.name,
                level=d.data.level,
                hp=d.data.hp,
                mp=d.data.mp,
                attack=d.data.attack,
                defense=d.data.defense,
                experience=d.data.experience,
                gold=d.data.gold,
                guild_id=d.data.guild,
            )
            for d in ds
        ]


@strawberry.type
class Equipment:
    """遊戲裝備"""

    name: str
    rarity: ItemRarity
    character_class_req: Optional[CharacterClass] = None
    attack_bonus: int = 0
    defense_bonus: int = 0
    special_effect: Optional[str] = None
    price: int = 100


@strawberry.type
class GQL_Character:
    """遊戲角色"""

    name: str
    level: int
    hp: int
    mp: int
    attack: int
    defense: int
    experience: int
    gold: int
    guild_id: str | None

    @strawberry.field
    def guild(self) -> GQL_Guild | None:
        if self.guild_id:
            crudx = get_crud()
            mgr = crudx.get_manager(Guild)
            d = mgr.get(self.guild_id)
            return GQL_Guild(
                id=self.guild_id,
                name=d.data.name,
                description=d.data.description,
                leader_id=d.data.leader,
                member_count=d.data.member_count,
                level=d.data.level,
                treasury=d.data.treasury,
            )
        return None


@strawberry.type
class Query:
    @strawberry.field
    def character(self, character_id: str) -> GQL_Character:
        crudx = get_crud()
        mgr = crudx.get_manager(Character)
        d = mgr.get(character_id)
        return GQL_Character(
            name=d.data.name,
            level=d.data.level,
            hp=d.data.hp,
            mp=d.data.mp,
            attack=d.data.attack,
            defense=d.data.defense,
            experience=d.data.experience,
            gold=d.data.gold,
            guild_id=d.data.guild,
        )
