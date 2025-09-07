import logging
from typing import Dict

from autocrud.types import (
    PermissionResult,
)
from autocrud.types import IPermissionChecker, PermissionContext, ResourceAction

logger = logging.getLogger(__name__)


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
            return PermissionResult.not_applicable

        # 從方法參數中提取要修改的欄位
        modified_fields = self._extract_modified_fields(context)
        if not modified_fields:
            return PermissionResult.not_applicable

        # 獲取用戶允許修改的欄位
        allowed_fields = self._get_user_allowed_fields(context.user)

        # 檢查是否所有修改的欄位都被允許
        if modified_fields.issubset(allowed_fields):
            return PermissionResult.allow
        return PermissionResult.deny

    def _extract_modified_fields(self, context: PermissionContext) -> set[str]:
        """從上下文中提取要修改的欄位"""
        # 這裡可以根據實際的 update/patch 方法實現來提取
        # 例如從 method_kwargs 中獲取 data 參數，然後分析要修改的欄位
        modified_fields = set()

        data = context.data
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
