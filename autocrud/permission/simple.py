from autocrud.permission.basic import (
    DEFAULT_ROOT_USER,
)
from autocrud.types import IPermissionChecker, PermissionContext, PermissionResult


class AllowAll(IPermissionChecker):
    """允許所有操作的權限檢查器"""

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        """始終允許所有操作"""
        return PermissionResult.allow


class RootOnly(IPermissionChecker):
    """允許所有操作的權限檢查器"""

    def __init__(self, root_user: str = DEFAULT_ROOT_USER):
        self.root_user = root_user

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        """檢查用戶是否為 root"""
        if context.user == self.root_user:
            return PermissionResult.allow
        return PermissionResult.deny
