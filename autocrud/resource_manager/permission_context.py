"""權限檢查上下文和策略模式實現

這個模組提供了一個靈活的權限檢查框架：
- PermissionContext：包含所有權限檢查所需的上下文資訊
- PermissionChecker：可插拔的權限檢查器接口
- DefaultPermissionChecker：預設實現，可以被繼承或組合
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import StrEnum
from typing import Any, Dict
import datetime as dt
from msgspec import UNSET, Struct, UnsetType
import logging
from autocrud.resource_manager.basic import ResourceAction, ResourceMeta

from autocrud.resource_manager.basic import IPermissionResourceManager

from autocrud.resource_manager.core import ResourceManager

logger = logging.getLogger(__name__)


class PermissionResult(StrEnum):
    """權限檢查結果"""

    ALLOW = "allow"
    DENY = "deny"
    NOT_APPLICABLE = "not_applicable"  # 這個檢查器不適用於此操作


class PermissionContext(Struct, kw_only=True):
    """權限檢查上下文 - 包含所有權限檢查所需的資訊"""

    # 基本資訊
    user: str
    now: dt.datetime
    action: ResourceAction
    resource_name: str

    # 方法調用資訊
    method_args: tuple = ()
    method_kwargs: Dict[str, Any] = {}

    # 額外上下文資料
    resource_id: str | UnsetType = UNSET
    resource_meta: ResourceMeta | UnsetType = UNSET
    resource_data: Any | UnsetType = UNSET
    extra_data: Dict[str, Any] = {}


class IPermissionChecker(ABC):
    """權限檢查器接口"""

    @abstractmethod
    def check_permission(self, context: PermissionContext) -> PermissionResult:
        """檢查權限

        Args:
            context: 權限檢查上下文

        Returns:
            PermissionResult: 檢查結果
        """
        pass


class CompositePermissionChecker(IPermissionChecker):
    """組合權限檢查器 - 執行多個檢查器，任何 DENY 都會拒絕操作"""

    def __init__(self, checkers: list[IPermissionChecker]):
        self.checkers = checkers

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        """執行所有檢查器，收集所有結果，任何 DENY 都會拒絕操作"""
        has_allow = False

        for checker in self.checkers:
            result = checker.check_permission(context)

            # 任何 DENY 立即拒絕
            if result == PermissionResult.DENY:
                return PermissionResult.DENY

            # 記錄是否有 ALLOW
            if result == PermissionResult.ALLOW:
                has_allow = True

        # 如果有 ALLOW 且沒有 DENY，則允許
        if has_allow:
            return PermissionResult.ALLOW

        # 所有檢查器都不適用，預設拒絕
        return PermissionResult.NOT_APPLICABLE


class AllowAll(IPermissionChecker):
    """允許所有操作的權限檢查器"""

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        """始終允許所有操作"""
        return PermissionResult.ALLOW


class DefaultPermissionChecker(IPermissionChecker):
    """預設權限檢查器 - 使用傳統的 ACL/RBAC 模式"""

    def __init__(self, permission_manager: "IPermissionResourceManager"):
        self.permission_manager = permission_manager

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        """使用現有的權限管理器進行檢查"""
        try:
            with self.permission_manager.meta_provide("root", context.now):
                allowed = self.permission_manager.check_permission(
                    context.user, context.action, context.resource_name
                )
            return PermissionResult.ALLOW if allowed else PermissionResult.DENY
        except Exception:
            logger.exception("Error on checking permission, so deny")
            return PermissionResult.DENY


class ActionBasedPermissionChecker(IPermissionChecker):
    """基於 Action 的權限檢查器 - 為不同操作提供專門的檢查邏輯"""

    def __init__(self):
        self._action_handlers: Dict[str, callable] = {}

    def register_action_handler(self, action: str, handler: callable) -> None:
        """註冊 action 處理器

        Args:
            action: 動作名稱
            handler: 處理函數，接受 PermissionContext，返回 PermissionResult
        """
        self._action_handlers[action] = handler

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        """根據 action 分發到對應的處理器"""

        handlers = [h for a, h in self._action_handlers.items() if context.action in a]
        for handler in handlers:
            result = handler(context)
            if result != PermissionResult.NOT_APPLICABLE:
                return result

        return PermissionResult.NOT_APPLICABLE

    @classmethod
    def from_dict(
        cls,
        handlers: dict[
            ResourceAction | str, Callable[[PermissionContext], PermissionResult]
        ],
    ) -> "ActionBasedPermissionChecker":
        """創建自定義 action 檢查器，並註冊常用的 action 處理器"""
        checker = cls()

        for action, handler in handlers.items():
            if isinstance(action, str):
                action = ResourceAction[action]
            checker.register_action_handler(action, handler)

        return checker


class ResourceOwnershipChecker(IPermissionChecker):
    """資源所有權檢查器 - 檢查用戶是否為資源創建者"""

    def __init__(
        self,
        resource_manager: ResourceManager,
        allowed_actions: ResourceAction = ResourceAction.owner,
    ):
        self.resource_manager = resource_manager
        self.allowed_actions = allowed_actions

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        """檢查用戶是否為資源擁有者"""
        # 只對特定 action 生效
        if context.action not in self.allowed_actions:
            return PermissionResult.NOT_APPLICABLE

        # 需要有 resource_id
        if context.resource_id is UNSET:
            return PermissionResult.NOT_APPLICABLE

        try:
            # 獲取資源元資料
            if context.resource_meta is UNSET:
                meta = self.resource_manager.get_meta(context.resource_id)
                context.resource_meta = meta
            else:
                meta = context.resource_meta

            # 檢查創建者
            if meta.created_by == context.user:
                return PermissionResult.ALLOW
            else:
                return PermissionResult.DENY

        except Exception:
            return PermissionResult.DENY


class FieldLevelPermissionChecker(IPermissionChecker):
    """欄位級權限檢查器 - 檢查用戶是否可以修改特定欄位"""

    def __init__(
        self,
        allowed_fields_by_user: Dict[str, set[str]] = None,
        allowed_fields_by_role: Dict[str, set[str]] = None,
    ):
        self.allowed_fields_by_user = allowed_fields_by_user or {}
        self.allowed_fields_by_role = allowed_fields_by_role or {}

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        """檢查欄位級權限"""
        # 只對 update/patch 操作生效
        if not (context.action & (ResourceAction.update | ResourceAction.patch)):
            return PermissionResult.NOT_APPLICABLE

        # 從方法參數中提取要修改的欄位
        modified_fields = self._extract_modified_fields(context)
        if not modified_fields:
            return PermissionResult.NOT_APPLICABLE

        # 獲取用戶允許修改的欄位
        allowed_fields = self._get_user_allowed_fields(context.user)

        # 檢查是否所有修改的欄位都被允許
        if modified_fields.issubset(allowed_fields):
            return PermissionResult.ALLOW
        else:
            return PermissionResult.DENY

    def _extract_modified_fields(self, context: PermissionContext) -> set[str]:
        """從上下文中提取要修改的欄位"""
        # 這裡可以根據實際的 update/patch 方法實現來提取
        # 例如從 method_kwargs 中獲取 data 參數，然後分析要修改的欄位
        modified_fields = set()

        if "data" in context.method_kwargs:
            data = context.method_kwargs["data"]
            if hasattr(data, "__dict__"):
                modified_fields = set(data.__dict__.keys())
            elif isinstance(data, dict):
                modified_fields = set(data.keys())

        return modified_fields

    def _get_user_allowed_fields(self, user: str) -> set[str]:
        """獲取用戶允許修改的欄位"""
        allowed = set()

        # 直接用戶權限
        if user in self.allowed_fields_by_user:
            allowed.update(self.allowed_fields_by_user[user])

        # TODO: 可以在這裡添加角色查詢邏輯
        # 例如查詢用戶所屬角色，然後獲取角色的允許欄位

        return allowed


class ConditionalPermissionChecker(IPermissionChecker):
    """條件式權限檢查器 - 基於資源內容的動態權限檢查"""

    def __init__(self):
        self._conditions: list[callable] = []

    def add_condition(self, condition: callable) -> None:
        """添加條件函數

        Args:
            condition: 條件函數，接受 PermissionContext，返回 PermissionResult
        """
        self._conditions.append(condition)

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        """執行所有條件檢查"""
        for condition in self._conditions:
            result = condition(context)
            if result != PermissionResult.NOT_APPLICABLE:
                return result

        return PermissionResult.NOT_APPLICABLE


# 便利函數：快速創建常用的權限檢查器組合
def create_default_permission_checker(
    permission_manager: IPermissionResourceManager,
    resource_manager: ResourceManager = None,
    enable_ownership_check: bool = True,
    field_permissions: Dict[str, set[str]] = None,
) -> IPermissionChecker:
    """創建預設的權限檢查器組合"""
    checkers = []

    # 添加基本的 ACL/RBAC 檢查器
    checkers.append(DefaultPermissionChecker(permission_manager))

    # 添加資源所有權檢查器
    if enable_ownership_check and resource_manager:
        checkers.append(ResourceOwnershipChecker(resource_manager))

    # 添加欄位級權限檢查器
    if field_permissions:
        checkers.append(
            FieldLevelPermissionChecker(allowed_fields_by_user=field_permissions)
        )

    return CompositePermissionChecker(checkers)
