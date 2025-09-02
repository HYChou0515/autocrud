from typing import TypeVar
from enum import Flag, StrEnum, auto
import msgspec

from autocrud.resource_manager.basic import (
    DataSearchCondition,
    DataSearchOperator,
    IPermissionResourceManager,
    Resource,
    ResourceAction,
    ResourceMetaSearchSort,
    ResourceDataSearchSort,
    ResourceMetaSortDirection,
    ResourceMetaSortKey,
    IndexableField,
    ResourceMetaSearchQuery,
    SpecialIndex,
)
from autocrud.resource_manager.core import ResourceManager

T = TypeVar("T")


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
    """ACL 權限設定

    用於定義用戶或群組對特定資源的權限。

    Attributes:
        subject: 權限主體 (誰擁有這個權限)
            - 用戶格式：'user:username' (例如 'user:alice')
            - 群組格式：'group:groupname' (例如 'group:admin')
            - 服務格式：'service:servicename' (例如 'service:api')

        object: 權限客體 (對什麼資源的權限)
            - 特定資源：完整的 resource_id (例如 'document:123e4567-e89b-12d3-a456-426614174000')
            - 資源類型：resource_name (例如 'document', 'user', 'file')
            - 萬用權限：'*' (允許所有資源，需謹慎使用)
            - 繼承權限：None (從其他權限規則繼承，不推薦直接使用)

        action: 權限動作 (可以做什麼操作)
            - 標準動作：'create', 'get', 'update', 'delete', 'search_resources'
            - 特殊動作：'get_meta', 'get_resource_revision', 'patch', 'switch'
            - 萬用動作：'*' (所有操作，需謹慎使用)
            - 自定義動作：任何字串 (例如 'publish', 'approve')

        effect: 權限效果
            - Effect.allow: 允許執行該動作
            - Effect.deny: 拒絕執行該動作 (deny 優先級高於 allow)

        order: 權限優先級 (數字越小優先級越高，預設按建立時間排序)

    Examples:
        # 允許 alice 創建任何文檔
        ACLPermission(
            subject="user:alice",
            object="document",  # 資源類型
            action="create",
            effect=Effect.allow
        )

        # 允許 admin 群組對特定文檔的所有操作
        ACLPermission(
            subject="group:admin",
            object="document:123e4567-e89b-12d3-a456-426614174000",  # 特定資源
            action="*",
            effect=Effect.allow
        )

        # 拒絕所有人刪除重要文檔
        ACLPermission(
            subject="*",  # 所有用戶
            object="document:important-doc-id",
            action="delete",
            effect=Effect.deny,
            order=0  # 最高優先級
        )
    """

    subject: str
    object: str | None
    action: ResourceAction
    order: int | msgspec.UnsetType = msgspec.UNSET
    effect: Effect = Effect.allow


# === RBAC 角色成員關係 ===
class RoleMembership(BasePermission):
    subject: str  # 用戶/主體
    group: str  # 角色群組
    order: int | msgspec.UnsetType = msgspec.UNSET


# === 統一權限模型：使用 Union 類型 ===
Permission = ACLPermission | RoleMembership


class PermissionResourceManager(ResourceManager, IPermissionResourceManager):
    """權限資源管理器 - 支援 ACL、RBAC、ABAC 統一管理"""

    def __init__(
        self,
        resource_type=Permission,
        *,
        policy: Policy = Policy.strict,
        root_users: list[str] = None,
        **kwargs,
    ):
        # 設置 root 用戶列表
        self.root_users = set(root_users or ["root", "admin"])

        # 定義需要建立索引的欄位，以支援高效查詢
        indexed_fields = [
            IndexableField(field_path="type", field_type=SpecialIndex.msgspec_tag),
            IndexableField(field_path="subject", field_type=str),
            IndexableField(field_path="object", field_type=str),
            IndexableField(field_path="action", field_type=int),
            IndexableField(field_path="group", field_type=str),
            IndexableField(field_path="order", field_type=int),
        ]

        # 設置 indexed_fields 到 kwargs，如果還沒有的話
        kwargs.setdefault("indexed_fields", indexed_fields)

        super().__init__(
            resource_type,
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
        action: ResourceAction,
        resource_id: str | None,
        *,
        have_more_to_check: bool = False,
    ) -> bool | None:
        """檢查用戶對特定資源的 ACL 權限

        權限匹配順序（優先級從高到低）：
        1. Root 用戶檢查：如果是 root 用戶，直接允許所有操作
        2. 精確匹配：subject + object(具體resource_id) + action
        3. 資源類型匹配：subject + object(resource_name) + action
        4. 萬用資源匹配：subject + object("*") + action
        5. 萬用動作匹配：subject + object + action("*")
        6. 完全萬用匹配：subject + object("*") + action("*")

        Args:
            user: 用戶標識
            action: 要執行的動作
            resource_id: 具體的資源ID，可能為None
            have_more_to_check: 是否還有其他檢查器需要執行

        Returns:
            True: 允許
            False: 拒絕
            None: 沒有匹配的規則，需要其他檢查器決定
        """
        # 1. 首先檢查是否為 root 用戶
        if user in self.root_users:
            return True

        # 調試：打印輸入參數
        # 構建可能的 object 匹配值（按優先級排序）
        possible_objects = []

        if resource_id:
            # 檢查 resource_id 是完整的資源ID還是只是資源類型名稱
            if ":" in resource_id:
                # 1. 精確的資源ID匹配
                possible_objects.append(resource_id)

                # 2. 資源類型匹配 (從resource_id中提取resource_name)
                resource_name = resource_id.split(":", 1)[0]
                possible_objects.append(resource_name)
            else:
                # 這是資源類型名稱，直接使用
                possible_objects.append(resource_id)

        # 3. 萬用資源匹配
        possible_objects.append("*")

        # 4. None 值匹配（向後兼容，但不推薦）
        possible_objects.append(None)

        # Root 用戶可以做任何事
        if user == "root":
            return True

        # 構建可能的 action 匹配值
        has_allow = False
        has_deny = False

        # 按優先級順序檢查所有可能的組合
        for obj in possible_objects:
            try:
                # 設置為 root 來執行搜尋，避免無限遞歸
                with self.meta_provide("root", self.now_ctx.get()):
                    # 構建搜尋查詢
                    query = ResourceMetaSearchQuery(
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
                                value=obj,
                            ),
                            DataSearchCondition(
                                field_path="action",
                                operator=DataSearchOperator.contains,
                                value=action,
                            ),
                        ],
                    )

                    # 搜尋符合條件的 ACL 權限
                    search_results = self.search_resources(query)

                    # 處理找到的權限規則
                    for resource_info in search_results:
                        # 直接從 indexed_data 中獲取權限信息，避免嵌套 context
                        indexed_data = resource_info.indexed_data
                        if indexed_data.get("type") != "ACLPermission":
                            continue

                        effect_str = indexed_data.get("effect", "allow")  # 預設為 allow
                        effect = Effect.allow if effect_str == "allow" else Effect.deny

                        if effect == Effect.deny:
                            has_deny = True
                            # 如果是 deny 優先策略，立即拒絕
                            if Policy.deny_overrides in self.policy:
                                return False
                        elif effect == Effect.allow:
                            has_allow = True
                            # 如果是 allow 優先策略，立即允許
                            if Policy.allow_overrides in self.policy:
                                return True
            except Exception:
                continue

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
            print("DEBUG: Found deny rules, returning False")
            return False

        if has_allow:
            print("DEBUG: Found allow rules, returning True")
            return True

        # 什麼都沒有
        print("DEBUG: No matching rules found, using default policy")
        return self._default_action(have_more_to_check)

    def _check_rbac_permission(
        self, user: str, action: ResourceAction, resource_id: str | None
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
        self, user: str, action: ResourceAction, resource: str
    ) -> bool:
        """檢查用戶權限的主入口方法"""
        if user in self.root_users:
            return True
        return self._check_rbac_permission(user, action, resource)
