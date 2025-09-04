from msgspec import UNSET
import logging
from autocrud.permission.basic import PermissionResult
from autocrud.permission.basic import PermissionContext
from autocrud.permission.basic import IPermissionChecker
from autocrud.resource_manager.basic import ResourceAction


from autocrud.resource_manager.core import ResourceManager

logger = logging.getLogger(__name__)


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
            return PermissionResult.not_applicable

        # 需要有 resource_id
        if context.resource_id is UNSET:
            return PermissionResult.not_applicable

        try:
            # 獲取資源元資料
            if context.resource_meta is UNSET:
                meta = self.resource_manager.get_meta(context.resource_id)
                context.resource_meta = meta
            else:
                meta = context.resource_meta

            # 檢查創建者
            if meta.created_by == context.user:
                return PermissionResult.allow
            else:
                return PermissionResult.deny

        except Exception:
            return PermissionResult.deny
