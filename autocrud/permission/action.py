"""權限檢查上下文和策略模式實現

這個模組提供了一個靈活的權限檢查框架：
- PermissionContext：包含所有權限檢查所需的上下文資訊
- PermissionChecker：可插拔的權限檢查器接口
- DefaultPermissionChecker：預設實現，可以被繼承或組合
"""

import itertools as it
import logging
from collections.abc import Callable

from autocrud.types import (
    PermissionResult,
)
from autocrud.types import IPermissionChecker, PermissionContext, ResourceAction

logger = logging.getLogger(__name__)

CheckFunc = Callable[[PermissionContext], PermissionResult]


class ActionBasedPermissionChecker(IPermissionChecker):
    """基於 Action 的權限檢查器 - 為不同操作提供專門的檢查邏輯"""

    def __init__(self):
        self._action_handlers: dict[ResourceAction | str, list[CheckFunc]] = {}

    def register_action_handler(
        self,
        action: ResourceAction | str,
        handler: CheckFunc,
    ) -> None:
        """註冊 action 處理器

        Args:
            action: 動作名稱
            handler: 處理函數，接受 PermissionContext，返回 PermissionResult
        """
        if isinstance(action, str):
            action = ResourceAction[action]
        if action not in self._action_handlers:
            self._action_handlers[action] = []
        self._action_handlers[action].append(handler)

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        """根據 action 分發到對應的處理器"""
        handlers = [h for a, h in self._action_handlers.items() if context.action in a]
        for handler in it.chain.from_iterable(handlers):
            result = handler(context)
            if result != PermissionResult.not_applicable:
                return result

        return PermissionResult.not_applicable

    @classmethod
    def from_dict(
        cls,
        handlers: dict[ResourceAction | str, CheckFunc | list[CheckFunc]],
    ) -> "ActionBasedPermissionChecker":
        """創建自定義 action 檢查器，並註冊常用的 action 處理器"""
        checker = cls()

        for action, handler in handlers.items():
            if isinstance(action, str):
                action = ResourceAction[action]
            if not isinstance(handler, (list, tuple, set)):
                handler = [handler]
            for h in handler:
                checker.register_action_handler(action, h)

        return checker
