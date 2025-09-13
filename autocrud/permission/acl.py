import logging
from enum import Flag, auto

from msgspec import UNSET, Struct, UnsetType

from autocrud.permission.basic import (
    DEFAULT_ROOT_USER,
    IPermissionCheckerWithStore,
)
from autocrud.permission.simple import RootOnly
from autocrud.types import (
    IndexableField,
)
from autocrud.resource_manager.core import ResourceManager
from autocrud.resource_manager.storage_factory import (
    IStorageFactory,
    MemoryStorageFactory,
)
from autocrud.types import (
    DataSearchCondition,
    DataSearchOperator,
    PermissionContext,
    PermissionResult,
    ResourceAction,
    ResourceDataSearchSort,
    ResourceMetaSearchQuery,
    ResourceMetaSortDirection,
)

logger = logging.getLogger(__name__)


class ACLPermission(Struct):
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
            - PermissionResult.ALLOW: 允許執行該動作
            - PermissionResult.DENY: 拒絕執行該動作 (deny 優先級高於 allow)

        order: 權限優先級 (數字越小優先級越高，預設按建立時間排序)

    Examples:
        # 允許 alice 創建任何文檔
        ACLPermission(
            subject="user:alice",
            object="document",  # 資源類型
            action="create",
            effect=PermissionResult.ALLOW
        )

        # 允許 admin 群組對特定文檔的所有操作
        ACLPermission(
            subject="group:admin",
            object="document:123e4567-e89b-12d3-a456-426614174000",  # 特定資源
            action="*",
            effect=PermissionResult.ALLOW
        )

        # 拒絕所有人刪除重要文檔
        ACLPermission(
            subject="*",  # 所有用戶
            object="document:important-doc-id",
            action="delete",
            effect=PermissionResult.DENY,
            order=0  # 最高優先級
        )
    """

    subject: str
    object: str | None
    action: ResourceAction
    order: int | UnsetType = UNSET
    effect: PermissionResult = PermissionResult.allow


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


class ACLPermissionChecker(IPermissionCheckerWithStore[ACLPermission]):
    """ACL 權限檢查器"""

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
        storage = self.storage_factory.build("ACLPermission")
        self.pm = ResourceManager(
            ACLPermission,
            storage=storage,
            indexed_fields=[
                IndexableField(field_path="subject", field_type=str),
                IndexableField(field_path="object", field_type=str),
                IndexableField(field_path="action", field_type=int),
                IndexableField(field_path="order", field_type=int),
            ],
            permission_checker=RootOnly(root_user),
        )
        self.policy = policy
        self.root_user = root_user

    @property
    def resource_manager(self):
        return self.pm

    def _default_action(self, have_more_to_check: bool) -> PermissionResult:
        if have_more_to_check:
            return PermissionResult.not_applicable
        # 處理所有規則後仍無決定，使用預設策略
        if Policy.default_allow in self.policy:
            return PermissionResult.allow
        if Policy.default_deny in self.policy:
            return PermissionResult.deny
        # 如果沒有指定預設策略，使用最保守的拒絕
        return PermissionResult.deny

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
                    for resource_info in search_results:
                        # 直接從 indexed_data 中獲取權限信息，避免嵌套 context
                        indexed_data = resource_info.indexed_data
                        effect_str = indexed_data.get("effect", "allow")  # 預設為 allow
                        effect = PermissionResult[effect_str]

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

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        """檢查用戶權限的主入口方法"""
        if context.user == self.root_user:
            return PermissionResult.allow
        return self._check_acl_permission(context)
