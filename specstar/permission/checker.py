"""Canonical home for the permission checker interface.

Defines:
- ``PermissionResult`` — outcome enum
- ``PermissionContext`` — alias of ``EventContext`` used at permission-check sites
- ``IPermissionChecker`` — ABC implemented by concrete checkers
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import StrEnum
from typing import TYPE_CHECKING, TypeVar

from specstar.events import EventContext

if TYPE_CHECKING:
    from specstar.types import ResourceAction

PermissionContext = EventContext

DEFAULT_ROOT_USER = "root"


class PermissionResult(StrEnum):
    """權限檢查結果"""

    allow = "allow"
    deny = "deny"
    not_applicable = "not_applicable"


class ResourcePart(StrEnum):
    """Slices of the *current* (stored) resource a permission checker may need
    loaded into a write-phase ``PermissionContext.current_resource``.

    A checker declares which slices it reads via
    :meth:`IPermissionChecker.required_resource_parts`; the ResourceManager
    loads only those before a write (update/modify/patch/delete) permission
    check, so an owner-only check stays a cheap ``meta`` read and never pays
    for the data blob.
    """

    META = "meta"
    DATA = "data"
    INFO = "info"


_CF = TypeVar("_CF", bound=Callable[..., "PermissionResult"])


def requires_resource_parts(*parts: ResourcePart) -> Callable[[_CF], _CF]:
    """Mark a ``CheckFunc`` with the :class:`ResourcePart` slices it reads.

    ``ActionBasedPermissionChecker`` (and ``ConditionalPermissionChecker``)
    aggregate these markers into their own
    :meth:`IPermissionChecker.required_resource_parts` so the ResourceManager
    knows what to preload. Unmarked functions need nothing.

    Example::

        @requires_resource_parts(ResourcePart.META)
        def owner_self(context): ...
    """
    frozen = frozenset(parts)

    def deco(func: _CF) -> _CF:
        func._required_resource_parts = frozen  # type: ignore[attr-defined]
        return func

    return deco


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

    def required_resource_parts(
        self, action: "ResourceAction"
    ) -> frozenset[ResourcePart]:
        """Resource slices this checker needs loaded into
        ``PermissionContext.current_resource`` for a before-phase **write**
        check of ``action`` (update / modify / patch / delete).

        Default: ``frozenset()`` — nothing is loaded, so existing checkers
        keep their zero-overhead behaviour. Override (or compose markers via
        :func:`requires_resource_parts`) to opt in.
        """
        return frozenset()


__all__ = [
    "DEFAULT_ROOT_USER",
    "IPermissionChecker",
    "PermissionContext",
    "PermissionResult",
    "ResourcePart",
    "requires_resource_parts",
]
