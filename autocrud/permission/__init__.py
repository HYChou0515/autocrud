"""Public permission API for end-user composition."""

from autocrud.permission.acl import ACLPermission, ACLPermissionChecker, Policy
from autocrud.permission.action import ActionBasedPermissionChecker
from autocrud.permission.composite import (
    CompositePermissionChecker,
    ConditionalPermissionChecker,
)
from autocrud.permission.data_based import FieldLevelPermissionChecker
from autocrud.permission.meta_based import ResourceOwnershipChecker
from autocrud.permission.rbac import (
    RBACPermissionChecker,
    RBACPermissionEntry,
    RoleMembership,
)
from autocrud.permission.simple import AllowAll, RootOnly
from autocrud.types import (
    IPermissionChecker,
    PermissionContext,
    PermissionResult,
    ResourceAction,
)

__all__ = [
    "ACLPermission",
    "ACLPermissionChecker",
    "ActionBasedPermissionChecker",
    "AllowAll",
    "CompositePermissionChecker",
    "ConditionalPermissionChecker",
    "FieldLevelPermissionChecker",
    "IPermissionChecker",
    "PermissionContext",
    "PermissionResult",
    "Policy",
    "RBACPermissionChecker",
    "RBACPermissionEntry",
    "ResourceAction",
    "ResourceOwnershipChecker",
    "RoleMembership",
    "RootOnly",
]
