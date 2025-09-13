import logging
from copy import copy

from msgspec import UNSET, Struct, UnsetType

from autocrud.permission.acl import ACLPermission, ACLPermissionChecker, Policy
from autocrud.permission.basic import (
    DEFAULT_ROOT_USER,
    IPermissionCheckerWithStore,
)
from autocrud.permission.simple import RootOnly
from autocrud.types import (
    SpecialIndex,
)
from autocrud.resource_manager.core import ResourceManager
from autocrud.resource_manager.storage_factory import (
    IStorageFactory,
    MemoryStorageFactory,
)
from autocrud.types import (
    DataSearchCondition,
    DataSearchOperator,
    IndexableField,
    PermissionContext,
    PermissionResult,
    Resource,
    ResourceDataSearchSort,
    ResourceMetaSearchQuery,
    ResourceMetaSearchSort,
    ResourceMetaSortDirection,
    ResourceMetaSortKey,
)

logger = logging.getLogger(__name__)


class RoleMembership(Struct, kw_only=True, tag=True):
    subject: str  # 用戶/主體
    group: str  # 角色群組
    order: int | UnsetType = UNSET


class RBACPermissionEntry(ACLPermission, tag=True): ...


RBACPermission = RBACPermissionEntry | RoleMembership


class RBACPermissionChecker(
    ACLPermissionChecker,
    IPermissionCheckerWithStore[RBACPermission],
):
    """RBAC 權限檢查器"""

    def __init__(
        self,
        *,
        policy: Policy = Policy.strict,
        storage_factory: IStorageFactory | None = None,
        root_user: str = DEFAULT_ROOT_USER,
    ):
        if storage_factory is None:
            self.storage_factory = MemoryStorageFactory()
        else:
            self.storage_factory = storage_factory
        storage = self.storage_factory.build("RBACPermission")
        self.pm = ResourceManager[RBACPermission](
            RBACPermission,
            storage=storage,
            indexed_fields=[
                IndexableField(field_path="type", field_type=SpecialIndex.msgspec_tag),
                IndexableField(field_path="subject", field_type=str),
                IndexableField(field_path="object", field_type=str),
                IndexableField(field_path="action", field_type=int),
                IndexableField(field_path="group", field_type=str),
                IndexableField(field_path="order", field_type=int),
            ],
            permission_checker=RootOnly(root_user),
        )
        self.policy = policy
        self.root_user = root_user

    def _check_acl_permission(
        self,
        context: PermissionContext,
        *,
        have_more_to_check: bool = False,
    ) -> PermissionResult:
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
            PermissionResult
        """
        # 1. 首先檢查是否為 root 用戶
        if context.user == self.root_user:
            return PermissionResult.allow

        # 調試：打印輸入參數
        # 構建可能的 object 匹配值（按優先級排序）
        possible_objects = [context.resource_name, "*"]

        # 構建可能的 action 匹配值
        has_allow = False
        has_deny = False

        # 按優先級順序檢查所有可能的組合
        for obj in possible_objects:
            try:
                # 設置為 root 來執行搜尋，避免無限遞歸
                with self.pm.meta_provide(self.root_user, context.now):
                    # 構建搜尋查詢
                    query = ResourceMetaSearchQuery(
                        data_conditions=[
                            DataSearchCondition(
                                field_path="type",
                                operator=DataSearchOperator.equals,
                                value="RBACPermissionEntry",
                            ),
                            DataSearchCondition(
                                field_path="subject",
                                operator=DataSearchOperator.equals,
                                value=context.user,
                            ),
                            DataSearchCondition(
                                field_path="object",
                                operator=DataSearchOperator.equals,
                                value=obj,
                            ),
                            DataSearchCondition(
                                field_path="action",
                                operator=DataSearchOperator.contains,
                                value=context.action,
                            ),
                        ],
                        sorts=[
                            ResourceDataSearchSort(
                                direction=ResourceMetaSortDirection.ascending,
                                field_path="order",
                            ),
                        ],
                    )

                    # 搜尋符合條件的 ACL 權限
                    search_results = self.pm.search_resources(query)

                    # 處理找到的權限規則
                    for meta in search_results:
                        # 直接從 indexed_data 中獲取權限信息，避免嵌套 context
                        resource = self.pm.get(meta.resource_id)
                        data = resource.data
                        if not isinstance(data, RBACPermissionEntry):
                            logger.warning(
                                "Found non-RBACPermissionEntry resource: %s",
                                meta.resource_id,
                            )
                            continue
                        effect = data.effect
                        if effect == PermissionResult.deny:
                            has_deny = True
                            # 如果是 deny 優先策略，立即拒絕
                            if Policy.deny_overrides in self.policy:
                                return PermissionResult.deny
                        elif effect == PermissionResult.allow:
                            has_allow = True
                            # 如果是 allow 優先策略，立即允許
                            if Policy.allow_overrides in self.policy:
                                return PermissionResult.allow
            except Exception:
                logger.exception(
                    "Error on searching ACL permissions, so ignore this part",
                )
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
            return PermissionResult.deny

        if has_allow:
            return PermissionResult.allow

        # 什麼都沒有
        return self._default_action(have_more_to_check)

    def _check_rbac_permission(
        self,
        context: PermissionContext,
    ) -> bool:
        """檢查用戶對特定資源的 RBAC 權限"""
        stack: list[str] = []
        stack.append(context.user)
        while stack:
            role_name = stack.pop()
            context_copy = copy(context)
            context_copy.user = role_name
            p = self._check_acl_permission(context_copy, have_more_to_check=True)
            if p != PermissionResult.not_applicable:
                return p

            with self.pm.meta_provide(self.root_user, context.now):
                role_metas = self.pm.search_resources(
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
                    ),
                )
                for meta in role_metas:
                    role: Resource[RoleMembership] = self.pm.get(meta.resource_id)
                    stack.append(role.data.group)

        return self._default_action(False)

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        """檢查用戶權限的主入口方法"""
        if context.user == self.root_user:
            return PermissionResult.allow
        return self._check_rbac_permission(context)
