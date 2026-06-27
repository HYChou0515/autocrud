"""Public permission API for end-user composition."""

from specstar.permission.access_scope import UNRESTRICTED, AccessScope
from specstar.permission.acl import ACLPermission, ACLPermissionChecker, Policy
from specstar.permission.action import ActionBasedPermissionChecker
from specstar.permission.builtins import (
    admin_only,
    any_authenticated,
    any_user,
    deny_all,
    owner_self,
)
from specstar.permission.checker import (
    IPermissionChecker,
    PermissionContext,
    PermissionResult,
    ResourcePart,
    requires_resource_parts,
)
from specstar.permission.composite import (
    CompositePermissionChecker,
    ConditionalPermissionChecker,
)
from specstar.permission.data_based import FieldLevelPermissionChecker
from specstar.permission.meta_based import ResourceOwnershipChecker
from specstar.permission.rbac import (
    RBACPermissionChecker,
    RBACPermissionEntry,
    RoleMembership,
)
from specstar.permission.simple import AllowAll, RootOnly
from specstar.types import ResourceAction

__all__ = [
    "ACLPermission",
    "ACLPermissionChecker",
    "AccessScope",
    "ActionBasedPermissionChecker",
    "AllowAll",
    "UNRESTRICTED",
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
    "ResourcePart",
    "RoleMembership",
    "RootOnly",
    "admin_only",
    "any_authenticated",
    "any_user",
    "deny_all",
    "owner_self",
    "requires_resource_parts",
]
