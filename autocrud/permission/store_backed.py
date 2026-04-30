"""Shared scaffolding for permission checkers backed by a ResourceManager.

Both :class:`~autocrud.permission.acl.ACLPermissionChecker` and
:class:`~autocrud.permission.rbac.RBACPermissionChecker` share the same
construction pattern:

1. Build (or accept) a :class:`IStorageFactory`.
2. Build a storage instance under a fixed logical name.
3. Wrap it in a :class:`ResourceManager` with a fixed set of
   :class:`IndexableField` definitions.
4. Use :class:`RootOnly` as the meta permission checker so only root can
   read/write the permission data itself.
5. Apply a :class:`Policy` describing how default / conflicting decisions
   resolve.

This module hosts the common pieces:

* :class:`Policy` — the policy flag (lives here so it can be reused without
  pulling :mod:`autocrud.permission.acl`).
* :class:`StoreBackedPermissionChecker` — base class implementing the
  construction pattern and the default-action policy resolution.
"""

from __future__ import annotations

from enum import Flag, auto
from typing import TYPE_CHECKING, Generic, TypeVar

from autocrud.permission.checker import (
    DEFAULT_ROOT_USER,
    IPermissionChecker,
    PermissionResult,
)
from autocrud.permission.simple import RootOnly
from autocrud.types import IndexableField

if TYPE_CHECKING:
    from autocrud.resource_manager.storage_factory import IStorageFactory

T = TypeVar("T")


class Policy(Flag):
    """Permission resolution policy used by store-backed checkers."""

    # 基本策略
    deny_overrides = auto()  # deny 優先：任何 deny 都會拒絕
    allow_overrides = auto()  # allow 優先：任何 allow 都會允許

    # 無匹配時的行為
    default_allow = auto()  # 沒有匹配規則時預設允許
    default_deny = auto()  # 沒有匹配規則時預設拒絕

    # 常用組合
    strict = deny_overrides | default_deny  # 嚴格模式：deny 優先且獲勝，無規則拒絕
    permissive = (
        allow_overrides | default_allow
    )  # 寬鬆模式：allow 優先且獲勝，無規則允許


class StoreBackedPermissionChecker(IPermissionChecker, Generic[T]):
    """Permission checker backed by a private :class:`ResourceManager`.

    Subclasses configure three class-level attributes:

    * ``data_type`` — the msgspec type stored in the manager.
    * ``storage_name`` — the logical name passed to ``storage_factory.build``.
    * ``indexed_fields`` — index definitions for the underlying store.

    The constructor wires storage, the permission resource manager, the
    policy, and the root user.  ``_default_action`` provides the shared
    policy-resolution logic used by both ACL and RBAC checkers.
    """

    data_type: type
    storage_name: str
    indexed_fields: list[IndexableField]

    def __init__(
        self,
        *,
        policy: Policy = Policy.strict,
        storage_factory: IStorageFactory | None = None,
        root_user: str = DEFAULT_ROOT_USER,
    ):
        from autocrud.resource_manager.core import ResourceManager
        from autocrud.resource_manager.storage_factory import MemoryStorageFactory

        self.storage_factory = storage_factory or MemoryStorageFactory()
        storage = self.storage_factory.build(self.storage_name)
        self.pm = ResourceManager[T](
            self.data_type,  # ty:ignore[invalid-argument-type]
            storage=storage,
            indexed_fields=self.indexed_fields,
            permission_checker=RootOnly(root_user),
        )
        self.resource_manager = self.pm
        self.policy = policy
        self.root_user = root_user

    def _default_action(self, have_more_to_check: bool) -> PermissionResult:
        if have_more_to_check:
            return PermissionResult.not_applicable
        # 處理所有規則後仍無決定，使用預設策略
        if Policy.default_allow in self.policy:
            return PermissionResult.allow
        if Policy.default_deny in self.policy:
            return PermissionResult.deny
        # 如果沒有指定預設策略，使用最保守的拒絕
        return PermissionResult.deny
