from autocrud.resource_manager.permission import ACLPermission

from msgspec import UNSET, UnsetType, Struct


class RoleMembership(Struct, kw_only=True, tag=True):
    subject: str  # 用戶/主體
    group: str  # 角色群組
    order: int | UnsetType = UNSET


class ACLPermission_(ACLPermission, tag=True): ...


Permission = ACLPermission_ | RoleMembership
