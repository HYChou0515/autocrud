"""Auto-generated stub for specstar.events."""
# THIS FILE IS GENERATED — do not edit by hand.
# Regenerate with: make stubs

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from collections.abc import Callable, Generator, Sequence
from typing import IO, Any, Generic, Protocol, Self, runtime_checkable

from jsonpatch import JsonPatch
from msgspec import UNSET, Struct, UnsetType
from typing_extensions import Literal
from typing_extensions import TypeVar as TypeVarExt

from specstar.query_types import ResourceMetaSearchQuery as ResourceMetaSearchQuery
from specstar.types import Resource as Resource
from specstar.types import ResourceAction as ResourceAction
from specstar.types import ResourceMeta as ResourceMeta
from specstar.types import RevisionInfo as RevisionInfo
from specstar.types import RevisionStatus as RevisionStatus
from specstar.types import SearchedResource as SearchedResource

T = TypeVarExt("T", default=None)

# ── Structural protocols (re-exported from runtime) ──────
@runtime_checkable
class EventContextProto(Protocol):
    action: ResourceAction
    phase: str
    resource_name: str

@runtime_checkable
class HasData(EventContextProto, Protocol):
    data: Any

@runtime_checkable
class HasResourceId(EventContextProto, Protocol):
    resource_id: str

@runtime_checkable
class HasDataAndResourceId(EventContextProto, Protocol):
    data: Any
    resource_id: str

@runtime_checkable
class HasRevisionId(HasResourceId, Protocol):
    revision_id: str

@runtime_checkable
class HasInfo(EventContextProto, Protocol):
    info: RevisionInfo

# ── Generated event-context classes ──────────────────────

class BeforeCreate(
    Struct, Generic[T], kw_only=True, tag=True, tag_field="context_type"
):
    phase: Literal["before"] = "before"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.create] = ResourceAction.create
    data: T
    status: RevisionStatus | UnsetType = UNSET
    if_not_exists: bool | UnsetType = UNSET

class AfterCreate(Struct, Generic[T], kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["after"] = "after"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.create] = ResourceAction.create
    data: T
    status: RevisionStatus | UnsetType = UNSET
    if_not_exists: bool | UnsetType = UNSET

class OnSuccessCreate(
    Struct, Generic[T], kw_only=True, tag=True, tag_field="context_type"
):
    phase: Literal["on_success"] = "on_success"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.create] = ResourceAction.create
    data: T
    status: RevisionStatus | UnsetType = UNSET
    if_not_exists: bool | UnsetType = UNSET
    info: RevisionInfo

class OnFailureCreate(
    Struct, Generic[T], kw_only=True, tag=True, tag_field="context_type"
):
    phase: Literal["on_failure"] = "on_failure"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    error: str
    stack_trace: str | None = None
    action: Literal[ResourceAction.create] = ResourceAction.create
    data: T
    status: RevisionStatus | UnsetType = UNSET
    if_not_exists: bool | UnsetType = UNSET

class BeforeDelete(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["before"] = "before"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.delete] = ResourceAction.delete
    resource_id: str
    current_resource: SearchedResource[T] | UnsetType = UNSET

class AfterDelete(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["after"] = "after"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.delete] = ResourceAction.delete
    resource_id: str

class OnSuccessDelete(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["on_success"] = "on_success"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.delete] = ResourceAction.delete
    resource_id: str
    meta: ResourceMeta

class OnFailureDelete(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["on_failure"] = "on_failure"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    error: str
    stack_trace: str | None = None
    action: Literal[ResourceAction.delete] = ResourceAction.delete
    resource_id: str

class BeforeDump(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["before"] = "before"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.dump] = ResourceAction.dump

class AfterDump(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["after"] = "after"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.dump] = ResourceAction.dump

class OnSuccessDump(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["on_success"] = "on_success"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.dump] = ResourceAction.dump
    result: Generator[tuple[str, IO[bytes]], None, None]

class OnFailureDump(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["on_failure"] = "on_failure"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    error: str
    stack_trace: str | None = None
    action: Literal[ResourceAction.dump] = ResourceAction.dump

class BeforeGet(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["before"] = "before"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.get] = ResourceAction.get
    resource_id: str
    revision_id: str | UnsetType = UNSET
    schema_version: str | None | UnsetType = UNSET
    include_deleted: bool = False

class AfterGet(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["after"] = "after"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.get] = ResourceAction.get
    resource_id: str
    revision_id: str | UnsetType = UNSET
    schema_version: str | None | UnsetType = UNSET
    include_deleted: bool = False

class OnSuccessGet(
    Struct, Generic[T], kw_only=True, tag=True, tag_field="context_type"
):
    phase: Literal["on_success"] = "on_success"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.get] = ResourceAction.get
    resource_id: str
    revision_id: str | UnsetType = UNSET
    schema_version: str | None | UnsetType = UNSET
    include_deleted: bool = False
    resource: Resource[T]

class OnFailureGet(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["on_failure"] = "on_failure"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    error: str
    stack_trace: str | None = None
    action: Literal[ResourceAction.get] = ResourceAction.get
    resource_id: str
    revision_id: str | UnsetType = UNSET
    schema_version: str | None | UnsetType = UNSET
    include_deleted: bool = False

class BeforeGetMeta(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["before"] = "before"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.get_meta] = ResourceAction.get_meta
    resource_id: str

class AfterGetMeta(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["after"] = "after"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.get_meta] = ResourceAction.get_meta
    resource_id: str

class OnSuccessGetMeta(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["on_success"] = "on_success"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.get_meta] = ResourceAction.get_meta
    resource_id: str
    meta: ResourceMeta

class OnFailureGetMeta(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["on_failure"] = "on_failure"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    error: str
    stack_trace: str | None = None
    action: Literal[ResourceAction.get_meta] = ResourceAction.get_meta
    resource_id: str

class BeforeGetResourceRevision(
    Struct, kw_only=True, tag=True, tag_field="context_type"
):
    phase: Literal["before"] = "before"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.get_resource_revision] = (
        ResourceAction.get_resource_revision
    )
    resource_id: str
    revision_id: str
    schema_version: str | None | UnsetType = UNSET

class AfterGetResourceRevision(
    Struct, kw_only=True, tag=True, tag_field="context_type"
):
    phase: Literal["after"] = "after"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.get_resource_revision] = (
        ResourceAction.get_resource_revision
    )
    resource_id: str
    revision_id: str
    schema_version: str | None | UnsetType = UNSET

class OnSuccessGetResourceRevision(
    Struct, Generic[T], kw_only=True, tag=True, tag_field="context_type"
):
    phase: Literal["on_success"] = "on_success"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.get_resource_revision] = (
        ResourceAction.get_resource_revision
    )
    resource_id: str
    revision_id: str
    schema_version: str | None | UnsetType = UNSET
    resource: Resource[T]

class OnFailureGetResourceRevision(
    Struct, kw_only=True, tag=True, tag_field="context_type"
):
    phase: Literal["on_failure"] = "on_failure"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    error: str
    stack_trace: str | None = None
    action: Literal[ResourceAction.get_resource_revision] = (
        ResourceAction.get_resource_revision
    )
    resource_id: str
    revision_id: str
    schema_version: str | None | UnsetType = UNSET

class BeforeListRevisions(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["before"] = "before"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.list_revisions] = ResourceAction.list_revisions
    resource_id: str

class AfterListRevisions(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["after"] = "after"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.list_revisions] = ResourceAction.list_revisions
    resource_id: str

class OnSuccessListRevisions(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["on_success"] = "on_success"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.list_revisions] = ResourceAction.list_revisions
    resource_id: str
    revisions: list[str]

class OnFailureListRevisions(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["on_failure"] = "on_failure"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    error: str
    stack_trace: str | None = None
    action: Literal[ResourceAction.list_revisions] = ResourceAction.list_revisions
    resource_id: str

class BeforeLoad(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["before"] = "before"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.load] = ResourceAction.load
    record_type: str

class AfterLoad(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["after"] = "after"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.load] = ResourceAction.load
    record_type: str

class OnSuccessLoad(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["on_success"] = "on_success"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.load] = ResourceAction.load
    record_type: str

class OnFailureLoad(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["on_failure"] = "on_failure"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    error: str
    stack_trace: str | None = None
    action: Literal[ResourceAction.load] = ResourceAction.load
    record_type: str

class BeforeMigrate(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["before"] = "before"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.migrate] = ResourceAction.migrate
    resource_id: str
    revision_id: str | UnsetType = UNSET

class AfterMigrate(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["after"] = "after"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.migrate] = ResourceAction.migrate
    resource_id: str
    revision_id: str | UnsetType = UNSET

class OnSuccessMigrate(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["on_success"] = "on_success"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.migrate] = ResourceAction.migrate
    resource_id: str
    revision_id: str | UnsetType = UNSET
    meta: ResourceMeta

class OnFailureMigrate(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["on_failure"] = "on_failure"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    error: str
    stack_trace: str | None = None
    action: Literal[ResourceAction.migrate] = ResourceAction.migrate
    resource_id: str
    revision_id: str | UnsetType = UNSET

class BeforeModify(
    Struct, Generic[T], kw_only=True, tag=True, tag_field="context_type"
):
    phase: Literal["before"] = "before"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.modify] = ResourceAction.modify
    resource_id: str
    data: T | UnsetType = UNSET
    status: RevisionStatus | UnsetType = UNSET
    expected_revision_id: str | UnsetType = UNSET
    expected_etag: str | UnsetType = UNSET
    current_resource: SearchedResource[T] | UnsetType = UNSET

class AfterModify(Struct, Generic[T], kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["after"] = "after"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.modify] = ResourceAction.modify
    resource_id: str
    data: T | UnsetType = UNSET
    status: RevisionStatus | UnsetType = UNSET
    expected_revision_id: str | UnsetType = UNSET
    expected_etag: str | UnsetType = UNSET

class OnSuccessModify(
    Struct, Generic[T], kw_only=True, tag=True, tag_field="context_type"
):
    phase: Literal["on_success"] = "on_success"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.modify] = ResourceAction.modify
    resource_id: str
    data: T | UnsetType = UNSET
    status: RevisionStatus | UnsetType = UNSET
    expected_revision_id: str | UnsetType = UNSET
    expected_etag: str | UnsetType = UNSET
    revision_info: RevisionInfo

class OnFailureModify(
    Struct, Generic[T], kw_only=True, tag=True, tag_field="context_type"
):
    phase: Literal["on_failure"] = "on_failure"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    error: str
    stack_trace: str | None = None
    action: Literal[ResourceAction.modify] = ResourceAction.modify
    resource_id: str
    data: T | UnsetType = UNSET
    status: RevisionStatus | UnsetType = UNSET
    expected_revision_id: str | UnsetType = UNSET
    expected_etag: str | UnsetType = UNSET

class BeforePatch(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["before"] = "before"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.patch] = ResourceAction.patch
    resource_id: str
    patch_data: JsonPatch
    expected_revision_id: str | UnsetType = UNSET
    expected_etag: str | UnsetType = UNSET
    current_resource: SearchedResource[T] | UnsetType = UNSET

class AfterPatch(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["after"] = "after"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.patch] = ResourceAction.patch
    resource_id: str
    patch_data: JsonPatch
    expected_revision_id: str | UnsetType = UNSET
    expected_etag: str | UnsetType = UNSET

class OnSuccessPatch(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["on_success"] = "on_success"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.patch] = ResourceAction.patch
    resource_id: str
    patch_data: JsonPatch
    expected_revision_id: str | UnsetType = UNSET
    expected_etag: str | UnsetType = UNSET
    revision_info: RevisionInfo

class OnFailurePatch(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["on_failure"] = "on_failure"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    error: str
    stack_trace: str | None = None
    action: Literal[ResourceAction.patch] = ResourceAction.patch
    resource_id: str
    patch_data: JsonPatch
    expected_revision_id: str | UnsetType = UNSET
    expected_etag: str | UnsetType = UNSET

class BeforePermanentlyDelete(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["before"] = "before"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.permanently_delete] = (
        ResourceAction.permanently_delete
    )
    resource_id: str
    current_resource: SearchedResource[T] | UnsetType = UNSET

class AfterPermanentlyDelete(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["after"] = "after"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.permanently_delete] = (
        ResourceAction.permanently_delete
    )
    resource_id: str

class OnSuccessPermanentlyDelete(
    Struct, kw_only=True, tag=True, tag_field="context_type"
):
    phase: Literal["on_success"] = "on_success"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.permanently_delete] = (
        ResourceAction.permanently_delete
    )
    resource_id: str
    meta: ResourceMeta

class OnFailurePermanentlyDelete(
    Struct, kw_only=True, tag=True, tag_field="context_type"
):
    phase: Literal["on_failure"] = "on_failure"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    error: str
    stack_trace: str | None = None
    action: Literal[ResourceAction.permanently_delete] = (
        ResourceAction.permanently_delete
    )
    resource_id: str

class BeforePrune(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["before"] = "before"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.prune] = ResourceAction.prune
    resource_id: str
    keep_last_n: int | UnsetType = UNSET
    before: dt.datetime | UnsetType = UNSET

class AfterPrune(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["after"] = "after"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.prune] = ResourceAction.prune
    resource_id: str
    keep_last_n: int | UnsetType = UNSET
    before: dt.datetime | UnsetType = UNSET

class OnSuccessPrune(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["on_success"] = "on_success"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.prune] = ResourceAction.prune
    resource_id: str
    keep_last_n: int | UnsetType = UNSET
    before: dt.datetime | UnsetType = UNSET
    pruned: list[str]

class OnFailurePrune(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["on_failure"] = "on_failure"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    error: str
    stack_trace: str | None = None
    action: Literal[ResourceAction.prune] = ResourceAction.prune
    resource_id: str
    keep_last_n: int | UnsetType = UNSET
    before: dt.datetime | UnsetType = UNSET

class BeforeRestore(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["before"] = "before"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.restore] = ResourceAction.restore
    resource_id: str
    current_resource: SearchedResource[T] | UnsetType = UNSET

class AfterRestore(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["after"] = "after"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.restore] = ResourceAction.restore
    resource_id: str

class OnSuccessRestore(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["on_success"] = "on_success"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.restore] = ResourceAction.restore
    resource_id: str
    meta: ResourceMeta

class OnFailureRestore(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["on_failure"] = "on_failure"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    error: str
    stack_trace: str | None = None
    action: Literal[ResourceAction.restore] = ResourceAction.restore
    resource_id: str

class BeforeSearchResources(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["before"] = "before"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.search_resources] = ResourceAction.search_resources
    query: ResourceMetaSearchQuery

class AfterSearchResources(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["after"] = "after"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.search_resources] = ResourceAction.search_resources
    query: ResourceMetaSearchQuery

class OnSuccessSearchResources(
    Struct, kw_only=True, tag=True, tag_field="context_type"
):
    phase: Literal["on_success"] = "on_success"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.search_resources] = ResourceAction.search_resources
    query: ResourceMetaSearchQuery
    results: list[ResourceMeta]

class OnFailureSearchResources(
    Struct, kw_only=True, tag=True, tag_field="context_type"
):
    phase: Literal["on_failure"] = "on_failure"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    error: str
    stack_trace: str | None = None
    action: Literal[ResourceAction.search_resources] = ResourceAction.search_resources
    query: ResourceMetaSearchQuery

class BeforeSwitch(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["before"] = "before"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.switch] = ResourceAction.switch
    resource_id: str
    revision_id: str
    current_resource: SearchedResource[T] | UnsetType = UNSET

class AfterSwitch(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["after"] = "after"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.switch] = ResourceAction.switch
    resource_id: str
    revision_id: str

class OnSuccessSwitch(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["on_success"] = "on_success"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.switch] = ResourceAction.switch
    resource_id: str
    revision_id: str
    meta: ResourceMeta

class OnFailureSwitch(Struct, kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["on_failure"] = "on_failure"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    error: str
    stack_trace: str | None = None
    action: Literal[ResourceAction.switch] = ResourceAction.switch
    resource_id: str
    revision_id: str

class BeforeUpdate(
    Struct, Generic[T], kw_only=True, tag=True, tag_field="context_type"
):
    phase: Literal["before"] = "before"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.update] = ResourceAction.update
    resource_id: str
    data: T
    status: RevisionStatus | UnsetType = UNSET
    expected_revision_id: str | UnsetType = UNSET
    expected_etag: str | UnsetType = UNSET
    current_resource: SearchedResource[T] | UnsetType = UNSET

class AfterUpdate(Struct, Generic[T], kw_only=True, tag=True, tag_field="context_type"):
    phase: Literal["after"] = "after"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.update] = ResourceAction.update
    resource_id: str
    data: T
    status: RevisionStatus | UnsetType = UNSET
    expected_revision_id: str | UnsetType = UNSET
    expected_etag: str | UnsetType = UNSET

class OnSuccessUpdate(
    Struct, Generic[T], kw_only=True, tag=True, tag_field="context_type"
):
    phase: Literal["on_success"] = "on_success"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    action: Literal[ResourceAction.update] = ResourceAction.update
    resource_id: str
    data: T
    status: RevisionStatus | UnsetType = UNSET
    expected_revision_id: str | UnsetType = UNSET
    expected_etag: str | UnsetType = UNSET
    revision_info: RevisionInfo

class OnFailureUpdate(
    Struct, Generic[T], kw_only=True, tag=True, tag_field="context_type"
):
    phase: Literal["on_failure"] = "on_failure"
    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    error: str
    stack_trace: str | None = None
    action: Literal[ResourceAction.update] = ResourceAction.update
    resource_id: str
    data: T
    status: RevisionStatus | UnsetType = UNSET
    expected_revision_id: str | UnsetType = UNSET
    expected_etag: str | UnsetType = UNSET

# ── Union of every event-context class ───────────────────
EventContext = (
    BeforeCreate
    | AfterCreate
    | OnSuccessCreate
    | OnFailureCreate
    | BeforeDelete
    | AfterDelete
    | OnSuccessDelete
    | OnFailureDelete
    | BeforeDump
    | AfterDump
    | OnSuccessDump
    | OnFailureDump
    | BeforeGet
    | AfterGet
    | OnSuccessGet
    | OnFailureGet
    | BeforeGetMeta
    | AfterGetMeta
    | OnSuccessGetMeta
    | OnFailureGetMeta
    | BeforeGetResourceRevision
    | AfterGetResourceRevision
    | OnSuccessGetResourceRevision
    | OnFailureGetResourceRevision
    | BeforeListRevisions
    | AfterListRevisions
    | OnSuccessListRevisions
    | OnFailureListRevisions
    | BeforeLoad
    | AfterLoad
    | OnSuccessLoad
    | OnFailureLoad
    | BeforeMigrate
    | AfterMigrate
    | OnSuccessMigrate
    | OnFailureMigrate
    | BeforeModify
    | AfterModify
    | OnSuccessModify
    | OnFailureModify
    | BeforePatch
    | AfterPatch
    | OnSuccessPatch
    | OnFailurePatch
    | BeforePermanentlyDelete
    | AfterPermanentlyDelete
    | OnSuccessPermanentlyDelete
    | OnFailurePermanentlyDelete
    | BeforePrune
    | AfterPrune
    | OnSuccessPrune
    | OnFailurePrune
    | BeforeRestore
    | AfterRestore
    | OnSuccessRestore
    | OnFailureRestore
    | BeforeSearchResources
    | AfterSearchResources
    | OnSuccessSearchResources
    | OnFailureSearchResources
    | BeforeSwitch
    | AfterSwitch
    | OnSuccessSwitch
    | OnFailureSwitch
    | BeforeUpdate
    | AfterUpdate
    | OnSuccessUpdate
    | OnFailureUpdate
)

ContextFunc = Callable[[EventContext], None]

# ── Handler interface (mirrors runtime) ──────────────────
class IEventHandler(ABC):
    @abstractmethod
    def is_supported(self, context: EventContext) -> bool: ...
    @abstractmethod
    def handle_event(self, context: EventContext) -> None: ...

class SimpleEventHandler(IEventHandler):
    func: ContextFunc
    phase: str
    action: ResourceAction
    def __init__(
        self,
        func: ContextFunc,
        phase: str,
        action: ResourceAction,
    ) -> None: ...
    def is_supported(self, context: EventContext) -> bool: ...
    def handle_event(self, context: EventContext) -> None: ...

class SimpleEventHandlerBuilder(Sequence[SimpleEventHandler]):
    func: list[ContextFunc] | None
    def __init__(self, func: ContextFunc | list[ContextFunc]) -> None: ...
    def __len__(self) -> int: ...
    def __getitem__(self, index: int) -> SimpleEventHandler: ...  # ty: ignore[invalid-method-override]
    def do(self, func: ContextFunc | list[ContextFunc]) -> Self: ...
    def before(self, action: ResourceAction) -> Self: ...
    def after(self, action: ResourceAction) -> Self: ...
    def on_success(self, action: ResourceAction) -> Self: ...
    def on_failure(self, action: ResourceAction) -> Self: ...

def do(func: ContextFunc | list[ContextFunc]) -> SimpleEventHandlerBuilder: ...

class StringRefEventHandler(IEventHandler):
    target: str
    phase: str
    action: ResourceAction
    def __init__(
        self,
        target: str,
        *,
        phase: str,
        action: ResourceAction,
    ) -> None: ...
    def is_supported(self, context: EventContext) -> bool: ...
    def handle_event(self, context: EventContext) -> None: ...
