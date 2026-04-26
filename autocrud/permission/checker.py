"""Canonical home for the permission checker interface.

Defines:
- ``PermissionResult`` — outcome enum
- ``PermissionContext`` — alias of ``EventContext`` used at permission-check sites
- ``IPermissionChecker`` — ABC implemented by concrete checkers
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum

from autocrud.events import EventContext

PermissionContext = EventContext

DEFAULT_ROOT_USER = "root"


class PermissionResult(StrEnum):
    """權限檢查結果"""

    allow = "allow"
    deny = "deny"
    not_applicable = "not_applicable"


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


__all__ = [
    "DEFAULT_ROOT_USER",
    "IPermissionChecker",
    "PermissionContext",
    "PermissionResult",
]
