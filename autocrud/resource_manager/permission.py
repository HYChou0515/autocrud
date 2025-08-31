from enum import Flag, StrEnum, auto
from typing import Literal
import msgspec

from autocrud.resource_manager.core import ResourceManager
from autocrud.resource_manager.basic import (
    DataSearchCondition,
    DataSearchOperator,
    Resource,
    ResourceMetaSearchSort,
    ResourceDataSearchSort,
    ResourceMetaSortDirection,
    ResourceMetaSortKey,
    IndexableField,
    ResourceMetaSearchQuery,
    SpecialIndex,
)

ResourceAction = Literal[
    "create",
    "get",
    "get_resource_revision",
    "list_revisions",
    "get_meta",
    "search_resources",
    "update",
    "create_or_update",
    "patch",
    "switch",
    "delete",
    "restore",
    "dump",
    "load",
]


class Effect(StrEnum):
    allow = "allow"
    deny = "deny"


class Policy(Flag):
    # 基本策略
    deny_overrides = auto()  # deny 優先：任何 deny 都會拒絕
    allow_overrides = auto()  # allow 優先：任何 allow 都會允許

    # 無匹配時的行為
    default_allow = auto()  # 沒有匹配規則時預設允許
    default_deny = auto()  # 沒有匹配規則時預設拒絕

    # 常用組合
    strict = deny_overrides | default_deny  # 嚴格模式：deny 優先且獲勝，無規則拒絕
    permissive = (
        allow_overrides | default_allow
    )  # 寬鬆模式：allow 優先且獲勝，無規則允許


class BasePermission(msgspec.Struct, kw_only=True, tag=True):
    pass


# === ACL 權限 ===
class ACLPermission(BasePermission):
    subject: str
    object: str | None
    action: ResourceAction | str
    order: int | msgspec.UnsetType = msgspec.UNSET
    effect: Effect = Effect.allow


# === RBAC 角色成員關係 ===
class RoleMembership(BasePermission):
    subject: str  # 用戶/主體
    group: str  # 角色群組
    order: int | msgspec.UnsetType = msgspec.UNSET


# === 統一權限模型：使用 Union 類型 ===
Permission = ACLPermission | RoleMembership


class PermissionResourceManager(ResourceManager[Permission]):
    """權限資源管理器 - 支援 ACL、RBAC、ABAC 統一管理"""

    def __init__(self, *args, policy: Policy = Policy.strict, **kwargs):
        # 定義需要建立索引的欄位，以支援高效查詢
        indexed_fields = [
            IndexableField(field_path="type", field_type=SpecialIndex.msgspec_tag),
            IndexableField(field_path="subject", field_type=str),
            IndexableField(field_path="object", field_type=str),
            IndexableField(field_path="action", field_type=str),
            IndexableField(field_path="group", field_type=str),
            IndexableField(field_path="order", field_type=int),
        ]

        # 設置 indexed_fields 到 kwargs，如果還沒有的話
        kwargs.setdefault("indexed_fields", indexed_fields)

        super().__init__(
            Permission,  # resource_type
            *args,
            **kwargs,
        )
        self.policy = policy

    def _default_action(self, have_more_to_check: bool) -> bool | None:
        if have_more_to_check:
            return None
        # 處理所有規則後仍無決定，使用預設策略
        if Policy.default_allow in self.policy:
            return True
        elif Policy.default_deny in self.policy:
            return False
        else:
            # 如果沒有指定預設策略，使用最保守的拒絕
            return False

    def _check_acl_permission(
        self,
        user: str,
        action: ResourceAction | str,
        resource_id: str | None,
        *,
        have_more_to_check: bool = False,
    ) -> bool | None:
        """檢查用戶對特定資源的 ACL 權限"""
        acl_metas = self.search_resources(
            ResourceMetaSearchQuery(
                data_conditions=[
                    DataSearchCondition(
                        field_path="type",
                        operator=DataSearchOperator.equals,
                        value="ACLPermission",
                    ),
                    DataSearchCondition(
                        field_path="subject",
                        operator=DataSearchOperator.equals,
                        value=user,
                    ),
                    DataSearchCondition(
                        field_path="object",
                        operator=DataSearchOperator.equals,
                        value=resource_id,
                    ),
                    DataSearchCondition(
                        field_path="action",
                        operator=DataSearchOperator.equals,
                        value=action,
                    ),
                ],
                sorts=[
                    ResourceDataSearchSort(
                        direction=ResourceMetaSortDirection.ascending,
                        field_path="order",
                    ),
                    ResourceMetaSearchSort(
                        direction=ResourceMetaSortDirection.descending,
                        key=ResourceMetaSortKey.updated_time,
                    ),
                ],
            )
        )
        has_allow = False
        has_deny = False

        for acl_meta in acl_metas:
            acl: Resource[ACLPermission] = self.get(acl_meta.resource_id)

            if acl.data.effect == Effect.deny:
                has_deny = True
                # 如果是 deny 優先策略，立即拒絕
                if Policy.deny_overrides in self.policy:
                    return False
            elif acl.data.effect == Effect.allow:
                has_allow = True
                # 如果是 allow 優先策略，立即允許
                if Policy.allow_overrides in self.policy:
                    return True

        # 能到達此處的條件真值表：
        # 前提：沒有在循環中提前返回（即沒有觸發優先策略）
        #
        # ┌───────────┬──────────┬─────────────────┬────────────────┬──────────┬────────────────────────┐
        # │ has_allow │ has_deny │ allow_overrides │ deny_overrides │ 邏輯結果  │ 說明                    │
        # ├───────────┼──────────┼─────────────────┼────────────────┼──────────┼────────────────────────┤
        # │ False     │ True     │ *               │ False          │ Deny     │ 只有deny，沒有衝突       │
        # │ True      │ False    │ False           │ *              │ Allow    │ 只有allow，沒有衝突      │
        # │ True      │ True     │ False           │ False          │ Deny     │ 有衝突，deny勝出         │
        # │ False     │ False    │ *               │ *              │ Default  │ 無匹配規則，使用預設策略   │
        # └───────────┴──────────┴─────────────────┴────────────────┴──────────┴────────────────────────┘

        # 下方邏輯已實現上述條件真值表的所有情況
        if has_deny:
            return False

        if has_allow:
            return True

        # 什麼都沒有
        return self._default_action(have_more_to_check)

    def _check_rbac_permission(
        self, user: str, action: ResourceAction | str, resource_id: str | None
    ) -> bool:
        """檢查用戶對特定資源的 RBAC 權限"""
        stack: list[str] = []
        stack.append(user)
        while stack:
            role_name = stack.pop()
            p = self._check_acl_permission(
                role_name, action, resource_id, have_more_to_check=True
            )
            if p is not None:
                return p

            role_metas = self.search_resources(
                ResourceMetaSearchQuery(
                    data_conditions=[
                        DataSearchCondition(
                            field_path="type",
                            operator=DataSearchOperator.equals,
                            value="RoleMembership",
                        ),
                        DataSearchCondition(
                            field_path="subject",
                            operator=DataSearchOperator.equals,
                            value=role_name,
                        ),
                    ],
                    sorts=[
                        ResourceDataSearchSort(
                            direction=ResourceMetaSortDirection.ascending,
                            field_path="order",
                        ),
                        ResourceMetaSearchSort(
                            direction=ResourceMetaSortDirection.descending,
                            key=ResourceMetaSortKey.updated_time,
                        ),
                    ],
                )
            )
            for meta in role_metas:
                role: Resource[RoleMembership] = self.get(meta.resource_id)
                stack.append(role.data.group)

        return self._default_action(False)

    def check_permission(
        self, user: str, action: ResourceAction | str, resource: str
    ) -> bool:
        if self._check_rbac_permission(user, action, resource):
            return True
        return False
