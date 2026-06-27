"""Ready-made ``CheckFunc`` vocabulary used by spec-driven codegen.

These functions plug into ``ActionBasedPermissionChecker.from_dict({
ResourceAction.read: any_authenticated, ...})``. They are the
5-token vocabulary that STEP 1 normalizes ``### Permissions`` prose
into; anything outside the vocabulary uses ``custom:<dotted.path>``
which the codegen turns into ``specstar.string_ref(...)``.
"""

from __future__ import annotations

from msgspec import UNSET

from specstar.permission.checker import (
    DEFAULT_ROOT_USER,
    PermissionContext,
    PermissionResult,
    ResourcePart,
    requires_resource_parts,
)


def any_user(context: PermissionContext) -> PermissionResult:
    """Allow everyone — including anonymous. Maps to spec.md ``public``."""
    return PermissionResult.allow


def any_authenticated(context: PermissionContext) -> PermissionResult:
    """Allow when ``context.user`` is set and not anonymous."""
    user = getattr(context, "user", None)
    if user and user != "anonymous":
        return PermissionResult.allow
    return PermissionResult.deny


def admin_only(context: PermissionContext) -> PermissionResult:
    """Allow only the configured admin user (default ``"root"``)."""
    if getattr(context, "user", None) == DEFAULT_ROOT_USER:
        return PermissionResult.allow
    return PermissionResult.deny


def deny_all(context: PermissionContext) -> PermissionResult:
    """Always deny — useful for actions no caller should ever invoke."""
    return PermissionResult.deny


@requires_resource_parts(ResourcePart.META)
def owner_self(context: PermissionContext) -> PermissionResult:
    """Allow when ``context.user`` matches the current resource's
    ``meta.created_by``.

    Reads the pre-write ``current_resource`` snapshot the ResourceManager
    loads for write checks (update/modify/patch/delete and the lifecycle verbs
    switch/permanently_delete/restore) — the
    ``@requires_resource_parts(ResourcePart.META)`` marker is what makes that
    ``meta`` slice available. For actions with no current resource (e.g.
    create, or read contexts that don't carry the snapshot) no owner exists
    → deny.
    """
    current = getattr(context, "current_resource", UNSET)
    if current is UNSET or current is None:
        return PermissionResult.deny
    meta = getattr(current, "meta", UNSET)
    if meta is UNSET or meta is None:
        return PermissionResult.deny
    created_by = getattr(meta, "created_by", None)
    if created_by is None:
        return PermissionResult.deny
    user = getattr(context, "user", None)
    if user and user == created_by:
        return PermissionResult.allow
    return PermissionResult.deny


__all__ = [
    "admin_only",
    "any_authenticated",
    "any_user",
    "deny_all",
    "owner_self",
]
