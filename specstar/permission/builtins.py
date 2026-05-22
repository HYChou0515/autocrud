"""Ready-made ``CheckFunc`` vocabulary used by spec-driven codegen.

These functions plug into ``ActionBasedPermissionChecker.from_dict({
ResourceAction.read: any_authenticated, ...})``. They are the
5-token vocabulary that STEP 1 normalizes ``### Permissions`` prose
into; anything outside the vocabulary uses ``custom:<dotted.path>``
which the codegen turns into ``specstar.string_ref(...)``.
"""

from __future__ import annotations

from specstar.permission.checker import (
    DEFAULT_ROOT_USER,
    PermissionContext,
    PermissionResult,
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


def owner_self(context: PermissionContext) -> PermissionResult:
    """Allow when ``context.user`` matches the resource's ``meta.created_by``.

    For actions on resources that don't have a meta yet (e.g. create),
    no owner exists → deny.
    """
    meta = getattr(context, "meta", None)
    if meta is None:
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
