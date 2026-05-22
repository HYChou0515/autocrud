"""Event subsystem for SpecStar.

Canonical home for everything event-shaped:

- All ``Before/After/OnSuccess/OnFailure`` event-context structs.
- The :data:`EventContext` union and the structural ``EventContextProto``
  family (``HasData``, ``HasResourceId``, ``HasDataAndResourceId``,
  ``HasRevisionId``, ``HasInfo``).
- The :class:`IEventHandler` ABC implemented by concrete handlers.
- The :func:`do` builder helper and :class:`SimpleEventHandler`.

Imports flow only inward: this module pulls a handful of domain primitives
from :mod:`specstar.types` and ``ResourceMetaSearchQuery`` from
:mod:`specstar.query_types`, and never the other way around.
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

from specstar.query_types import ResourceMetaSearchQuery
from specstar.types import (
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
_DefstructField = tuple[str, Any] | tuple[str, Any, Any]
_base_context: list[_DefstructField] = [
    ("user", str | UnsetType),
    ("now", dt.datetime | UnsetType),
    ("resource_name", str),
]
_before_context: list[_DefstructField] = [
    ("phase", Literal["before"], "before"),
    *_base_context,
]
_after_context: list[_DefstructField] = [
    ("phase", Literal["after"], "after"),
    *_base_context,
]
_on_success_context: list[_DefstructField] = [
    ("phase", Literal["on_success"], "on_success"),
    *_base_context,
]
_on_failure_context: list[_DefstructField] = [
    ("phase", Literal["on_failure"], "on_failure"),
    *_base_context,
    ("error", str),
    ("stack_trace", str | None, None),
]

# ============================================================================
# Create Context Classes
# ============================================================================

_create_context: list[_DefstructField] = [
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
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

AfterCreate = defstruct(
    "AfterCreate",
    [
        *_after_context,
        *_create_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnSuccessCreate = defstruct(
    "OnSuccessCreate",
    [
        *_on_success_context,
        *_create_context,
        ("info", RevisionInfo),
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnFailureCreate = defstruct(
    "OnFailureCreate",
    [
        *_on_failure_context,
        *_create_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)


# ============================================================================
# Get Context Classes
# ============================================================================

_get_context: list[_DefstructField] = [
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
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

AfterGet = defstruct(
    "AfterGet",
    [
        *_after_context,
        *_get_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnSuccessGet = defstruct(
    "OnSuccessGet",
    [
        *_on_success_context,
        *_get_context,
        ("resource", Resource[T]),
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnFailureGet = defstruct(
    "OnFailureGet",
    [
        *_on_failure_context,
        *_get_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)


# ============================================================================
# Get Resource Revision Context Classes
# ============================================================================

_get_resource_revision_context: list[_DefstructField] = [
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
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

AfterGetResourceRevision = defstruct(
    "AfterGetResourceRevision",
    [
        *_after_context,
        *_get_resource_revision_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnSuccessGetResourceRevision = defstruct(
    "OnSuccessGetResourceRevision",
    [
        *_on_success_context,
        *_get_resource_revision_context,
        ("resource", Resource[T]),
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnFailureGetResourceRevision = defstruct(
    "OnFailureGetResourceRevision",
    [
        *_on_failure_context,
        *_get_resource_revision_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)


# ============================================================================
# List Revisions Context Classes
# ============================================================================

_list_revisions_context: list[_DefstructField] = [
    ("action", Literal[ResourceAction.list_revisions], ResourceAction.list_revisions),
    ("resource_id", str),
]

BeforeListRevisions = defstruct(
    "BeforeListRevisions",
    [
        *_before_context,
        *_list_revisions_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

AfterListRevisions = defstruct(
    "AfterListRevisions",
    [
        *_after_context,
        *_list_revisions_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnSuccessListRevisions = defstruct(
    "OnSuccessListRevisions",
    [
        *_on_success_context,
        *_list_revisions_context,
        ("revisions", list[str]),
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnFailureListRevisions = defstruct(
    "OnFailureListRevisions",
    [
        *_on_failure_context,
        *_list_revisions_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)


# ============================================================================
# Get Meta Context Classes
# ============================================================================

_get_meta_context: list[_DefstructField] = [
    ("action", Literal[ResourceAction.get_meta], ResourceAction.get_meta),
    ("resource_id", str),
]

BeforeGetMeta = defstruct(
    "BeforeGetMeta",
    [
        *_before_context,
        *_get_meta_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

AfterGetMeta = defstruct(
    "AfterGetMeta",
    [
        *_after_context,
        *_get_meta_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnSuccessGetMeta = defstruct(
    "OnSuccessGetMeta",
    [
        *_on_success_context,
        *_get_meta_context,
        ("meta", ResourceMeta),
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnFailureGetMeta = defstruct(
    "OnFailureGetMeta",
    [
        *_on_failure_context,
        *_get_meta_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)


# ============================================================================
# Search Resources Context Classes
# ============================================================================

_search_resources_context: list[_DefstructField] = [
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
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

AfterSearchResources = defstruct(
    "AfterSearchResources",
    [
        *_after_context,
        *_search_resources_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnSuccessSearchResources = defstruct(
    "OnSuccessSearchResources",
    [
        *_on_success_context,
        *_search_resources_context,
        ("results", list[ResourceMeta]),
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnFailureSearchResources = defstruct(
    "OnFailureSearchResources",
    [
        *_on_failure_context,
        *_search_resources_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)


# ============================================================================
# Update Context Classes
# ============================================================================

_update_context: list[_DefstructField] = [
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
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

AfterUpdate = defstruct(
    "AfterUpdate",
    [
        *_after_context,
        *_update_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnSuccessUpdate = defstruct(
    "OnSuccessUpdate",
    [
        *_on_success_context,
        *_update_context,
        ("revision_info", RevisionInfo),
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnFailureUpdate = defstruct(
    "OnFailureUpdate",
    [
        *_on_failure_context,
        *_update_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)


# ============================================================================
# Modify Context Classes
# ============================================================================

_modify_context: list[_DefstructField] = [
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
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

AfterModify = defstruct(
    "AfterModify",
    [
        *_after_context,
        *_modify_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnSuccessModify = defstruct(
    "OnSuccessModify",
    [
        *_on_success_context,
        *_modify_context,
        ("revision_info", RevisionInfo),
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnFailureModify = defstruct(
    "OnFailureModify",
    [
        *_on_failure_context,
        *_modify_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)


# ============================================================================
# Patch Context Classes
# ============================================================================

_patch_context: list[_DefstructField] = [
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
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

AfterPatch = defstruct(
    "AfterPatch",
    [
        *_after_context,
        *_patch_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnSuccessPatch = defstruct(
    "OnSuccessPatch",
    [
        *_on_success_context,
        *_patch_context,
        ("revision_info", RevisionInfo),
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnFailurePatch = defstruct(
    "OnFailurePatch",
    [
        *_on_failure_context,
        *_patch_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)


# ============================================================================
# Switch Context Classes
# ============================================================================

_switch_context: list[_DefstructField] = [
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
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

AfterSwitch = defstruct(
    "AfterSwitch",
    [
        *_after_context,
        *_switch_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnSuccessSwitch = defstruct(
    "OnSuccessSwitch",
    [
        *_on_success_context,
        *_switch_context,
        ("meta", ResourceMeta),
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnFailureSwitch = defstruct(
    "OnFailureSwitch",
    [
        *_on_failure_context,
        *_switch_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)


# ============================================================================
# Delete Context Classes
# ============================================================================

_delete_context: list[_DefstructField] = [
    ("action", Literal[ResourceAction.delete], ResourceAction.delete),
    ("resource_id", str),
]

BeforeDelete = defstruct(
    "BeforeDelete",
    [
        *_before_context,
        *_delete_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

AfterDelete = defstruct(
    "AfterDelete",
    [
        *_after_context,
        *_delete_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnSuccessDelete = defstruct(
    "OnSuccessDelete",
    [
        *_on_success_context,
        *_delete_context,
        ("meta", ResourceMeta),
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnFailureDelete = defstruct(
    "OnFailureDelete",
    [
        *_on_failure_context,
        *_delete_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)


# ============================================================================
# PermanentlyDelete Context Classes
# ============================================================================

_permanently_delete_context: list[_DefstructField] = [
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
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

AfterPermanentlyDelete = defstruct(
    "AfterPermanentlyDelete",
    [
        *_after_context,
        *_permanently_delete_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnSuccessPermanentlyDelete = defstruct(
    "OnSuccessPermanentlyDelete",
    [
        *_on_success_context,
        *_permanently_delete_context,
        ("meta", ResourceMeta),
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnFailurePermanentlyDelete = defstruct(
    "OnFailurePermanentlyDelete",
    [
        *_on_failure_context,
        *_permanently_delete_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)


# ============================================================================
# Restore Context Classes
# ============================================================================

_restore_context: list[_DefstructField] = [
    ("action", Literal[ResourceAction.restore], ResourceAction.restore),
    ("resource_id", str),
]

BeforeRestore = defstruct(
    "BeforeRestore",
    [
        *_before_context,
        *_restore_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

AfterRestore = defstruct(
    "AfterRestore",
    [
        *_after_context,
        *_restore_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnSuccessRestore = defstruct(
    "OnSuccessRestore",
    [
        *_on_success_context,
        *_restore_context,
        ("meta", ResourceMeta),
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnFailureRestore = defstruct(
    "OnFailureRestore",
    [
        *_on_failure_context,
        *_restore_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

# ============================================================================
# Migrate Context Classes
# ============================================================================

_migrate_context: list[_DefstructField] = [
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
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

AfterMigrate = defstruct(
    "AfterMigrate",
    [
        *_after_context,
        *_migrate_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnSuccessMigrate = defstruct(
    "OnSuccessMigrate",
    [
        *_on_success_context,
        *_migrate_context,
        ("meta", ResourceMeta),
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnFailureMigrate = defstruct(
    "OnFailureMigrate",
    [
        *_on_failure_context,
        *_migrate_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)


# ============================================================================
# Dump Context Classes
# ============================================================================

_dump_context: list[_DefstructField] = [
    ("action", Literal[ResourceAction.dump], ResourceAction.dump),
]

BeforeDump = defstruct(
    "BeforeDump",
    [
        *_before_context,
        *_dump_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

AfterDump = defstruct(
    "AfterDump",
    [
        *_after_context,
        *_dump_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnSuccessDump = defstruct(
    "OnSuccessDump",
    [
        *_on_success_context,
        *_dump_context,
        ("result", Generator[tuple[str, IO[bytes]], None, None]),
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnFailureDump = defstruct(
    "OnFailureDump",
    [
        *_on_failure_context,
        *_dump_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)


# ============================================================================
# Load Context Classes
# ============================================================================

_load_context: list[_DefstructField] = [
    ("action", Literal[ResourceAction.load], ResourceAction.load),
    ("record_type", str),
]

BeforeLoad = defstruct(
    "BeforeLoad",
    [
        *_before_context,
        *_load_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

AfterLoad = defstruct(
    "AfterLoad",
    [
        *_after_context,
        *_load_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnSuccessLoad = defstruct(
    "OnSuccessLoad",
    [
        *_on_success_context,
        *_load_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
)

OnFailureLoad = defstruct(
    "OnFailureLoad",
    [
        *_on_failure_context,
        *_load_context,
    ],
    kw_only=True,
    tag=True,
    tag_field="context_type",
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
    def is_supported(self, context: EventContext) -> bool: ...  # ty:ignore[invalid-type-form]

    @abstractmethod
    def handle_event(self, context: EventContext) -> None: ...  # ty:ignore[invalid-type-form]


# ============================================================================
# Builder helper: do(callable).{phase}(action)
# ============================================================================

ContextFunc = Callable[[EventContext], None]  # ty:ignore[invalid-type-form]


class SimpleEventHandler(IEventHandler):
    def __init__(self, func: ContextFunc, phase: str, action: ResourceAction):
        self.func = func
        self.phase = phase
        self.action = action

    def is_supported(self, context: EventContext) -> bool:  # ty:ignore[invalid-type-form]
        return context.phase == self.phase and context.action in self.action

    def handle_event(self, context: EventContext) -> None:  # ty:ignore[invalid-type-form]
        self.func(context)


def _resolve_string_ref(target: str) -> Callable[[EventContext], None]:  # ty:ignore[invalid-type-form]
    """Resolve a dotted ``module.path.attr`` reference.

    Thin wrapper kept for backwards compatibility — delegates to the
    canonical :func:`specstar.refs.resolve`.
    """
    from specstar.refs import resolve

    return resolve(target)


class StringRefEventHandler(IEventHandler):
    """An event handler whose target is a dotted string reference.

    Used by spec-driven codegen so ``_generated.py`` can wire a
    workflow without importing the user's logic module at module-top
    time. The target is resolved via :func:`importlib.import_module`
    on the first :meth:`handle_event` call.

    Example::

        spec.add_model(
            Book,
            name="book",
            event_handlers=[
                StringRefEventHandler(
                    "my_app.logic.notify_customers_new_book",
                    phase="after",
                    action=ResourceAction.create,
                ),
            ],
        )
    """

    def __init__(self, target: str, *, phase: str, action: ResourceAction):
        self.target = target
        self.phase = phase
        self.action = action
        self._resolved: Callable[[EventContext], None] | None = None  # ty:ignore[invalid-type-form]

    def is_supported(self, context: EventContext) -> bool:  # ty:ignore[invalid-type-form]
        return context.phase == self.phase and context.action in self.action

    def handle_event(self, context: EventContext) -> None:  # ty:ignore[invalid-type-form]
        if self._resolved is None:
            self._resolved = _resolve_string_ref(self.target)
        self._resolved(context)


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
            self.func.extend(func)  # ty:ignore[invalid-argument-type]

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
    "StringRefEventHandler",
    "do",
]
