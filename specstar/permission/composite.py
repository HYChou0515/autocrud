"""權限檢查上下文和策略模式實現

這個模組提供了一個靈活的權限檢查框架：
- PermissionContext：包含所有權限檢查所需的上下文資訊
- PermissionChecker：可插拔的權限檢查器接口
- DefaultPermissionChecker：預設實現，可以被繼承或組合
"""

import logging
from collections.abc import Callable

from specstar.permission.checker import (
    IPermissionChecker,
    PermissionContext,
    PermissionResult,
    ResourcePart,
)
from specstar.types import ResourceAction

logger = logging.getLogger(__name__)


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
            if result == PermissionResult.deny:
                return PermissionResult.deny

            # 記錄是否有 ALLOW
            if result == PermissionResult.allow:
                has_allow = True

        # 如果有 ALLOW 且沒有 DENY，則允許
        if has_allow:
            return PermissionResult.allow

        # 所有檢查器都不適用，預設拒絕
        return PermissionResult.not_applicable

    def required_resource_parts(
        self, action: ResourceAction
    ) -> frozenset[ResourcePart]:
        """Union of every child checker's needs — any child that reads the
        current resource forces it to be loaded for the composite check."""
        parts: frozenset[ResourcePart] = frozenset()
        for checker in self.checkers:
            parts |= checker.required_resource_parts(action)
        return parts


class ConditionalPermissionChecker(IPermissionChecker):
    """條件式權限檢查器 - 基於資源內容的動態權限檢查"""

    def __init__(self):
        self._conditions: list[Callable] = []

    def add_condition(self, condition: Callable) -> None:
        """添加條件函數

        Args:
            condition: 條件函數，接受 PermissionContext，返回 PermissionResult
        """
        self._conditions.append(condition)

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        """執行所有條件檢查"""
        for condition in self._conditions:
            result = condition(context)
            if result != PermissionResult.not_applicable:
                return result

        return PermissionResult.not_applicable

    def required_resource_parts(
        self, action: ResourceAction
    ) -> frozenset[ResourcePart]:
        """Union of the ``@requires_resource_parts`` markers across all
        conditions (conditions aren't keyed by action, so this is
        action-independent)."""
        parts: frozenset[ResourcePart] = frozenset()
        for condition in self._conditions:
            parts |= getattr(condition, "_required_resource_parts", frozenset())
        return parts
