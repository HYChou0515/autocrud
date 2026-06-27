from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from msgspec import UNSET

from specstar.permission.checker import (
    IPermissionChecker,
    PermissionContext,
    PermissionResult,
    ResourcePart,
)
from specstar.types import ResourceAction

if TYPE_CHECKING:
    from specstar.resource_manager.core import ResourceManager

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

    def required_resource_parts(
        self, action: ResourceAction
    ) -> frozenset[ResourcePart]:
        """Needs the ``meta`` slice for the write actions it guards, so the
        ResourceManager preloads it into ``current_resource`` (avoiding the
        explicit ``get_meta`` round-trip below on writes)."""
        if action in self.allowed_actions:
            return frozenset({ResourcePart.META})
        return frozenset()

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        """檢查用戶是否為資源擁有者"""
        # 只對特定 action 生效
        if context.action not in self.allowed_actions:
            return PermissionResult.not_applicable

        # 需要有 resource_id (some context variants don't carry it)
        resource_id = getattr(context, "resource_id", UNSET)
        if resource_id is UNSET:
            return PermissionResult.not_applicable

        try:
            # Prefer the pre-loaded write-phase snapshot; fall back to an
            # explicit read for read-phase / non-write contexts that don't
            # carry it.
            meta = UNSET
            current = getattr(context, "current_resource", UNSET)
            if current is not UNSET and current is not None:
                meta = getattr(current, "meta", UNSET)
            if meta is UNSET or meta is None:
                meta = self.resource_manager.get_meta(resource_id)

            # 檢查創建者
            if meta.created_by == context.user:
                return PermissionResult.allow
            return PermissionResult.deny

        except Exception:
            return PermissionResult.deny
