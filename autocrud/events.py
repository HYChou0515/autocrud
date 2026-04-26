"""Event subsystem for AutoCRUD.

Canonical home for everything event-shaped:

- All ``Before/After/OnSuccess/OnFailure`` event-context structs.
- The :data:`EventContext` union and the structural ``EventContextProto``
  family (``HasData``, ``HasResourceId``, ``HasDataAndResourceId``,
  ``HasRevisionId``, ``HasInfo``).
- The :class:`IEventHandler` ABC implemented by concrete handlers.
- The :func:`do` builder helper and :class:`SimpleEventHandler`.

Imports flow only inward: this module pulls a handful of domain primitives
from :mod:`autocrud.types` and ``ResourceMetaSearchQuery`` from
:mod:`autocrud.query_types`, and never the other way around.
"""

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from collections.abc import Callable, Generator, Sequence
from typing import IO, Any, Protocol, Self, runtime_checkable

from jsonpatch import JsonPatch
from msgspec import UNSET, UnsetType, defstruct
from typing_extensions import Literal
from typing_extensions import TypeVar as TypeVarExt

from autocrud.query_types import ResourceMetaSearchQuery
from autocrud.types import (
    Resource,
    ResourceAction,
    ResourceMeta,
    RevisionInfo,
    RevisionStatus,
)

T = TypeVarExt("T", default=None)

# Event Context Protocols
# ============================================================================
#
# ``defstruct`` generates ``Struct`` subclasses at runtime, which are
# invisible to static type checkers (pyright / mypy).  The ``Protocol``
# classes below describe the *structural shape* of each context category
# so that event handler implementations can annotate their private
# methods with precise, type-checkable signatures instead of the opaque
# ``EventContext`` union.
#
# These are provided for **structural sub-typing** — you never need to
# explicitly inherit from them; any ``defstruct``-generated instance
# that has the matching attributes will satisfy the protocol.


@runtime_checkable
class EventContextProto(Protocol):
    """Minimal protocol shared by every event context."""

    action: ResourceAction
    phase: str
    resource_name: str


@runtime_checkable
class HasData(EventContextProto, Protocol):
    """Event context that carries a ``data`` payload."""

    data: Any


@runtime_checkable
class HasResourceId(EventContextProto, Protocol):
    """Event context that carries ``resource_id``."""

    resource_id: str


@runtime_checkable
class HasDataAndResourceId(EventContextProto, Protocol):
    """Event context that carries both ``data`` and ``resource_id``."""

    data: Any
    resource_id: str


@runtime_checkable
class HasRevisionId(HasResourceId, Protocol):
    """Event context that also carries ``revision_id``."""

    revision_id: str


@runtime_checkable
class HasInfo(EventContextProto, Protocol):
    """Event context that carries a ``info`` (:class:`RevisionInfo`)."""

    info: RevisionInfo


# ============================================================================
# Base Context Classes
# ============================================================================

_type_setting = {
    "kw_only": True,
    "tag": True,
    "tag_field": "context_type",
}
_base_context = [
    ("user", str | UnsetType),
    ("now", dt.datetime | UnsetType),
    ("resource_name", str),
]
_before_context = [
    ("phase", Literal["before"], "before"),
    *_base_context,
]
_after_context = [
    ("phase", Literal["after"], "after"),
    *_base_context,
]
_on_success_context = [
    ("phase", Literal["on_success"], "on_success"),
    *_base_context,
]
_on_failure_context = [
    ("phase", Literal["on_failure"], "on_failure"),
    *_base_context,
    ("error", str),
    ("stack_trace", str | None, None),
]

# ============================================================================
# Create Context Classes
# ============================================================================

_create_context = [
    ("action", Literal[ResourceAction.create], ResourceAction.create),
    ("data", T),
    ("status", RevisionStatus | UnsetType, UNSET),
]

BeforeCreate = defstruct(
    "BeforeCreate",
    [
        *_before_context,
        *_create_context,
    ],
    **_type_setting,
)

AfterCreate = defstruct(
    "AfterCreate",
    [
        *_after_context,
        *_create_context,
    ],
    **_type_setting,
)

OnSuccessCreate = defstruct(
    "OnSuccessCreate",
    [
        *_on_success_context,
        *_create_context,
        ("info", RevisionInfo),
    ],
    **_type_setting,
)

OnFailureCreate = defstruct(
    "OnFailureCreate",
    [
        *_on_failure_context,
        *_create_context,
    ],
    **_type_setting,
)


# ============================================================================
# Get Context Classes
# ============================================================================

_get_context = [
    ("action", Literal[ResourceAction.get], ResourceAction.get),
    ("resource_id", str),
    ("revision_id", str | UnsetType, UNSET),
    ("schema_version", str | None | UnsetType, UNSET),
]

BeforeGet = defstruct(
    "BeforeGet",
    [
        *_before_context,
        *_get_context,
    ],
    **_type_setting,
)

AfterGet = defstruct(
    "AfterGet",
    [
        *_after_context,
        *_get_context,
    ],
    **_type_setting,
)

OnSuccessGet = defstruct(
    "OnSuccessGet",
    [
        *_on_success_context,
        *_get_context,
        ("resource", Resource[T]),
    ],
    **_type_setting,
)

OnFailureGet = defstruct(
    "OnFailureGet",
    [
        *_on_failure_context,
        *_get_context,
    ],
    **_type_setting,
)


# ============================================================================
# Get Resource Revision Context Classes
# ============================================================================

_get_resource_revision_context = [
    (
        "action",
        Literal[ResourceAction.get_resource_revision],
        ResourceAction.get_resource_revision,
    ),
    ("resource_id", str),
    ("revision_id", str),
    ("schema_version", str | None | UnsetType, UNSET),
]

BeforeGetResourceRevision = defstruct(
    "BeforeGetResourceRevision",
    [
        *_before_context,
        *_get_resource_revision_context,
    ],
    **_type_setting,
)

AfterGetResourceRevision = defstruct(
    "AfterGetResourceRevision",
    [
        *_after_context,
        *_get_resource_revision_context,
    ],
    **_type_setting,
)

OnSuccessGetResourceRevision = defstruct(
    "OnSuccessGetResourceRevision",
    [
        *_on_success_context,
        *_get_resource_revision_context,
        ("resource", Resource[T]),
    ],
    **_type_setting,
)

OnFailureGetResourceRevision = defstruct(
    "OnFailureGetResourceRevision",
    [
        *_on_failure_context,
        *_get_resource_revision_context,
    ],
    **_type_setting,
)


# ============================================================================
# List Revisions Context Classes
# ============================================================================

_list_revisions_context = [
    ("action", Literal[ResourceAction.list_revisions], ResourceAction.list_revisions),
    ("resource_id", str),
]

BeforeListRevisions = defstruct(
    "BeforeListRevisions",
    [
        *_before_context,
        *_list_revisions_context,
    ],
    **_type_setting,
)

AfterListRevisions = defstruct(
    "AfterListRevisions",
    [
        *_after_context,
        *_list_revisions_context,
    ],
    **_type_setting,
)

OnSuccessListRevisions = defstruct(
    "OnSuccessListRevisions",
    [
        *_on_success_context,
        *_list_revisions_context,
        ("revisions", list[str]),
    ],
    **_type_setting,
)

OnFailureListRevisions = defstruct(
    "OnFailureListRevisions",
    [
        *_on_failure_context,
        *_list_revisions_context,
    ],
    **_type_setting,
)


# ============================================================================
# Get Meta Context Classes
# ============================================================================

_get_meta_context = [
    ("action", Literal[ResourceAction.get_meta], ResourceAction.get_meta),
    ("resource_id", str),
]

BeforeGetMeta = defstruct(
    "BeforeGetMeta",
    [
        *_before_context,
        *_get_meta_context,
    ],
    **_type_setting,
)

AfterGetMeta = defstruct(
    "AfterGetMeta",
    [
        *_after_context,
        *_get_meta_context,
    ],
    **_type_setting,
)

OnSuccessGetMeta = defstruct(
    "OnSuccessGetMeta",
    [
        *_on_success_context,
        *_get_meta_context,
        ("meta", ResourceMeta),
    ],
    **_type_setting,
)

OnFailureGetMeta = defstruct(
    "OnFailureGetMeta",
    [
        *_on_failure_context,
        *_get_meta_context,
    ],
    **_type_setting,
)


# ============================================================================
# Search Resources Context Classes
# ============================================================================

_search_resources_context = [
    (
        "action",
        Literal[ResourceAction.search_resources],
        ResourceAction.search_resources,
    ),
    ("query", ResourceMetaSearchQuery),
]

BeforeSearchResources = defstruct(
    "BeforeSearchResources",
    [
        *_before_context,
        *_search_resources_context,
    ],
    **_type_setting,
)

AfterSearchResources = defstruct(
    "AfterSearchResources",
    [
        *_after_context,
        *_search_resources_context,
    ],
    **_type_setting,
)

OnSuccessSearchResources = defstruct(
    "OnSuccessSearchResources",
    [
        *_on_success_context,
        *_search_resources_context,
        ("results", list[ResourceMeta]),
    ],
    **_type_setting,
)

OnFailureSearchResources = defstruct(
    "OnFailureSearchResources",
    [
        *_on_failure_context,
        *_search_resources_context,
    ],
    **_type_setting,
)


# ============================================================================
# Update Context Classes
# ============================================================================

_update_context = [
    ("action", Literal[ResourceAction.update], ResourceAction.update),
    ("resource_id", str),
    ("data", T),
    ("status", RevisionStatus | UnsetType, UNSET),
]

BeforeUpdate = defstruct(
    "BeforeUpdate",
    [
        *_before_context,
        *_update_context,
    ],
    **_type_setting,
)

AfterUpdate = defstruct(
    "AfterUpdate",
    [
        *_after_context,
        *_update_context,
    ],
    **_type_setting,
)

OnSuccessUpdate = defstruct(
    "OnSuccessUpdate",
    [
        *_on_success_context,
        *_update_context,
        ("revision_info", RevisionInfo),
    ],
    **_type_setting,
)

OnFailureUpdate = defstruct(
    "OnFailureUpdate",
    [
        *_on_failure_context,
        *_update_context,
    ],
    **_type_setting,
)


# ============================================================================
# Modify Context Classes
# ============================================================================

_modify_context = [
    ("action", Literal[ResourceAction.modify], ResourceAction.modify),
    ("resource_id", str),
    ("data", T | UnsetType, UNSET),
    ("status", RevisionStatus | UnsetType, UNSET),
]

BeforeModify = defstruct(
    "BeforeModify",
    [
        *_before_context,
        *_modify_context,
    ],
    **_type_setting,
)

AfterModify = defstruct(
    "AfterModify",
    [
        *_after_context,
        *_modify_context,
    ],
    **_type_setting,
)

OnSuccessModify = defstruct(
    "OnSuccessModify",
    [
        *_on_success_context,
        *_modify_context,
        ("revision_info", RevisionInfo),
    ],
    **_type_setting,
)

OnFailureModify = defstruct(
    "OnFailureModify",
    [
        *_on_failure_context,
        *_modify_context,
    ],
    **_type_setting,
)


# ============================================================================
# Patch Context Classes
# ============================================================================

_patch_context = [
    ("action", Literal[ResourceAction.patch], ResourceAction.patch),
    ("resource_id", str),
    ("patch_data", JsonPatch),
]

BeforePatch = defstruct(
    "BeforePatch",
    [
        *_before_context,
        *_patch_context,
    ],
    **_type_setting,
)

AfterPatch = defstruct(
    "AfterPatch",
    [
        *_after_context,
        *_patch_context,
    ],
    **_type_setting,
)

OnSuccessPatch = defstruct(
    "OnSuccessPatch",
    [
        *_on_success_context,
        *_patch_context,
        ("revision_info", RevisionInfo),
    ],
    **_type_setting,
)

OnFailurePatch = defstruct(
    "OnFailurePatch",
    [
        *_on_failure_context,
        *_patch_context,
    ],
    **_type_setting,
)


# ============================================================================
# Switch Context Classes
# ============================================================================

_switch_context = [
    ("action", Literal[ResourceAction.switch], ResourceAction.switch),
    ("resource_id", str),
    ("revision_id", str),
]

BeforeSwitch = defstruct(
    "BeforeSwitch",
    [
        *_before_context,
        *_switch_context,
    ],
    **_type_setting,
)

AfterSwitch = defstruct(
    "AfterSwitch",
    [
        *_after_context,
        *_switch_context,
    ],
    **_type_setting,
)

OnSuccessSwitch = defstruct(
    "OnSuccessSwitch",
    [
        *_on_success_context,
        *_switch_context,
        ("meta", ResourceMeta),
    ],
    **_type_setting,
)

OnFailureSwitch = defstruct(
    "OnFailureSwitch",
    [
        *_on_failure_context,
        *_switch_context,
    ],
    **_type_setting,
)


# ============================================================================
# Delete Context Classes
# ============================================================================

_delete_context = [
    ("action", Literal[ResourceAction.delete], ResourceAction.delete),
    ("resource_id", str),
]

BeforeDelete = defstruct(
    "BeforeDelete",
    [
        *_before_context,
        *_delete_context,
    ],
    **_type_setting,
)

AfterDelete = defstruct(
    "AfterDelete",
    [
        *_after_context,
        *_delete_context,
    ],
    **_type_setting,
)

OnSuccessDelete = defstruct(
    "OnSuccessDelete",
    [
        *_on_success_context,
        *_delete_context,
        ("meta", ResourceMeta),
    ],
    **_type_setting,
)

OnFailureDelete = defstruct(
    "OnFailureDelete",
    [
        *_on_failure_context,
        *_delete_context,
    ],
    **_type_setting,
)


# ============================================================================
# PermanentlyDelete Context Classes
# ============================================================================

_permanently_delete_context = [
    (
        "action",
        Literal[ResourceAction.permanently_delete],
        ResourceAction.permanently_delete,
    ),
    ("resource_id", str),
]

BeforePermanentlyDelete = defstruct(
    "BeforePermanentlyDelete",
    [
        *_before_context,
        *_permanently_delete_context,
    ],
    **_type_setting,
)

AfterPermanentlyDelete = defstruct(
    "AfterPermanentlyDelete",
    [
        *_after_context,
        *_permanently_delete_context,
    ],
    **_type_setting,
)

OnSuccessPermanentlyDelete = defstruct(
    "OnSuccessPermanentlyDelete",
    [
        *_on_success_context,
        *_permanently_delete_context,
        ("meta", ResourceMeta),
    ],
    **_type_setting,
)

OnFailurePermanentlyDelete = defstruct(
    "OnFailurePermanentlyDelete",
    [
        *_on_failure_context,
        *_permanently_delete_context,
    ],
    **_type_setting,
)


# ============================================================================
# Restore Context Classes
# ============================================================================

_restore_context = [
    ("action", Literal[ResourceAction.restore], ResourceAction.restore),
    ("resource_id", str),
]

BeforeRestore = defstruct(
    "BeforeRestore",
    [
        *_before_context,
        *_restore_context,
    ],
    **_type_setting,
)

AfterRestore = defstruct(
    "AfterRestore",
    [
        *_after_context,
        *_restore_context,
    ],
    **_type_setting,
)

OnSuccessRestore = defstruct(
    "OnSuccessRestore",
    [
        *_on_success_context,
        *_restore_context,
        ("meta", ResourceMeta),
    ],
    **_type_setting,
)

OnFailureRestore = defstruct(
    "OnFailureRestore",
    [
        *_on_failure_context,
        *_restore_context,
    ],
    **_type_setting,
)

# ============================================================================
# Migrate Context Classes
# ============================================================================

_migrate_context = [
    ("action", Literal[ResourceAction.migrate], ResourceAction.migrate),
    ("resource_id", str),
    ("revision_id", str | UnsetType, UNSET),
]

BeforeMigrate = defstruct(
    "BeforeMigrate",
    [
        *_before_context,
        *_migrate_context,
    ],
    **_type_setting,
)

AfterMigrate = defstruct(
    "AfterMigrate",
    [
        *_after_context,
        *_migrate_context,
    ],
    **_type_setting,
)

OnSuccessMigrate = defstruct(
    "OnSuccessMigrate",
    [
        *_on_success_context,
        *_migrate_context,
        ("meta", ResourceMeta),
    ],
    **_type_setting,
)

OnFailureMigrate = defstruct(
    "OnFailureMigrate",
    [
        *_on_failure_context,
        *_migrate_context,
    ],
    **_type_setting,
)


# ============================================================================
# Dump Context Classes
# ============================================================================

_dump_context = [
    ("action", Literal[ResourceAction.dump], ResourceAction.dump),
]

BeforeDump = defstruct(
    "BeforeDump",
    [
        *_before_context,
        *_dump_context,
    ],
    **_type_setting,
)

AfterDump = defstruct(
    "AfterDump",
    [
        *_after_context,
        *_dump_context,
    ],
    **_type_setting,
)

OnSuccessDump = defstruct(
    "OnSuccessDump",
    [
        *_on_success_context,
        *_dump_context,
        ("result", Generator[tuple[str, IO[bytes]], None, None]),
    ],
    **_type_setting,
)

OnFailureDump = defstruct(
    "OnFailureDump",
    [
        *_on_failure_context,
        *_dump_context,
    ],
    **_type_setting,
)


# ============================================================================
# Load Context Classes
# ============================================================================

_load_context = [
    ("action", Literal[ResourceAction.load], ResourceAction.load),
    ("record_type", str),
]

BeforeLoad = defstruct(
    "BeforeLoad",
    [
        *_before_context,
        *_load_context,
    ],
    **_type_setting,
)

AfterLoad = defstruct(
    "AfterLoad",
    [
        *_after_context,
        *_load_context,
    ],
    **_type_setting,
)

OnSuccessLoad = defstruct(
    "OnSuccessLoad",
    [
        *_on_success_context,
        *_load_context,
    ],
    **_type_setting,
)

OnFailureLoad = defstruct(
    "OnFailureLoad",
    [
        *_on_failure_context,
        *_load_context,
    ],
    **_type_setting,
)

EventContext = (
    BeforeCreate
    | AfterCreate
    | OnSuccessCreate
    | OnFailureCreate
    | BeforeGet
    | AfterGet
    | OnSuccessGet
    | OnFailureGet
    | BeforeGetResourceRevision
    | AfterGetResourceRevision
    | OnSuccessGetResourceRevision
    | OnFailureGetResourceRevision
    | BeforeListRevisions
    | AfterListRevisions
    | OnSuccessListRevisions
    | OnFailureListRevisions
    | BeforeGetMeta
    | AfterGetMeta
    | OnSuccessGetMeta
    | OnFailureGetMeta
    | BeforeSearchResources
    | AfterSearchResources
    | OnSuccessSearchResources
    | OnFailureSearchResources
    | BeforeUpdate
    | AfterUpdate
    | OnSuccessUpdate
    | OnFailureUpdate
    | BeforePatch
    | AfterPatch
    | OnSuccessPatch
    | OnFailurePatch
    | BeforeSwitch
    | AfterSwitch
    | OnSuccessSwitch
    | OnFailureSwitch
    | BeforeDelete
    | AfterDelete
    | OnSuccessDelete
    | OnFailureDelete
    | BeforePermanentlyDelete
    | AfterPermanentlyDelete
    | OnSuccessPermanentlyDelete
    | OnFailurePermanentlyDelete
    | BeforeRestore
    | AfterRestore
    | OnSuccessRestore
    | OnFailureRestore
    | BeforeDump
    | AfterDump
    | OnSuccessDump
    | OnFailureDump
    | BeforeLoad
    | AfterLoad
    | OnSuccessLoad
    | OnFailureLoad
)


# ============================================================================
# Event Handler Interface
# ============================================================================


class IEventHandler(ABC):
    """An event handler invoked by :class:`ResourceManager` when an event fires."""

    @abstractmethod
    def is_supported(self, context: EventContext) -> bool: ...

    @abstractmethod
    def handle_event(self, context: EventContext) -> None: ...


# ============================================================================
# Builder helper: do(callable).{phase}(action)
# ============================================================================

ContextFunc = Callable[[EventContext], None]


class SimpleEventHandler(IEventHandler):
    def __init__(self, func: ContextFunc, phase: str, action: ResourceAction):
        self.func = func
        self.phase = phase
        self.action = action

    def is_supported(self, context: EventContext) -> bool:
        return context.phase == self.phase and context.action in self.action

    def handle_event(self, context: EventContext) -> None:
        self.func(context)


class SimpleEventHandlerBuilder(Sequence[SimpleEventHandler]):
    def __init__(self, func: ContextFunc | list[ContextFunc]):
        self._ehs: list[SimpleEventHandler] = []
        self.func: list[ContextFunc] | None = None
        self._set_func(func)

    def __len__(self) -> int:
        return len(self._ehs)

    def __getitem__(self, index):
        return self._ehs[index]

    def _set_func(self, func: ContextFunc | list[ContextFunc]) -> None:
        if self.func is None:
            self.func = []
        if not isinstance(func, list):
            self.func.append(func)
        else:
            self.func.extend(func)

    def _build_phase(self, phase: str, action: ResourceAction) -> Self:
        if phase not in {"before", "after", "on_success", "on_failure"}:
            raise ValueError(f"Invalid phase: {phase}")
        if self.func is None:
            raise ValueError("Function must be provided before setting phase")
        for f in self.func:
            self._ehs.append(SimpleEventHandler(f, phase, action))
        self.func = None
        return self

    def do(self, func: ContextFunc | list[ContextFunc]) -> Self:
        self._set_func(func)
        return self

    def before(self, action: ResourceAction) -> Self:
        return self._build_phase("before", action)

    def after(self, action: ResourceAction) -> Self:
        return self._build_phase("after", action)

    def on_success(self, action: ResourceAction) -> Self:
        return self._build_phase("on_success", action)

    def on_failure(self, action: ResourceAction) -> Self:
        return self._build_phase("on_failure", action)


def do(func: ContextFunc | list[ContextFunc]) -> SimpleEventHandlerBuilder:
    """Start a chain that builds :class:`SimpleEventHandler` instances.

    Example::

        handlers = (
            do(my_callback).before(ResourceAction.create).after(ResourceAction.update)
        )
    """
    return SimpleEventHandlerBuilder(func)


__all__ = [
    "AfterCreate",
    "AfterDelete",
    "AfterDump",
    "AfterGet",
    "AfterGetMeta",
    "AfterGetResourceRevision",
    "AfterListRevisions",
    "AfterLoad",
    "AfterMigrate",
    "AfterModify",
    "AfterPatch",
    "AfterPermanentlyDelete",
    "AfterRestore",
    "AfterSearchResources",
    "AfterSwitch",
    "AfterUpdate",
    "BeforeCreate",
    "BeforeDelete",
    "BeforeDump",
    "BeforeGet",
    "BeforeGetMeta",
    "BeforeGetResourceRevision",
    "BeforeListRevisions",
    "BeforeLoad",
    "BeforeMigrate",
    "BeforeModify",
    "BeforePatch",
    "BeforePermanentlyDelete",
    "BeforeRestore",
    "BeforeSearchResources",
    "BeforeSwitch",
    "BeforeUpdate",
    "ContextFunc",
    "EventContext",
    "EventContextProto",
    "HasData",
    "HasDataAndResourceId",
    "HasInfo",
    "HasResourceId",
    "HasRevisionId",
    "IEventHandler",
    "OnFailureCreate",
    "OnFailureDelete",
    "OnFailureDump",
    "OnFailureGet",
    "OnFailureGetMeta",
    "OnFailureGetResourceRevision",
    "OnFailureListRevisions",
    "OnFailureLoad",
    "OnFailureMigrate",
    "OnFailureModify",
    "OnFailurePatch",
    "OnFailurePermanentlyDelete",
    "OnFailureRestore",
    "OnFailureSearchResources",
    "OnFailureSwitch",
    "OnFailureUpdate",
    "OnSuccessCreate",
    "OnSuccessDelete",
    "OnSuccessDump",
    "OnSuccessGet",
    "OnSuccessGetMeta",
    "OnSuccessGetResourceRevision",
    "OnSuccessListRevisions",
    "OnSuccessLoad",
    "OnSuccessMigrate",
    "OnSuccessModify",
    "OnSuccessPatch",
    "OnSuccessPermanentlyDelete",
    "OnSuccessRestore",
    "OnSuccessSearchResources",
    "OnSuccessSwitch",
    "OnSuccessUpdate",
    "ResourceAction",
    "SimpleEventHandler",
    "SimpleEventHandlerBuilder",
    "do",
]
