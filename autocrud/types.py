import datetime as dt
from enum import Flag, StrEnum, auto
from typing import Any, Generic, TypeVar
from uuid import UUID

from msgspec import UNSET, Struct, UnsetType

T = TypeVar("T")


class RevisionStatus(StrEnum):
    draft = "draft"
    stable = "stable"


class RevisionInfo(Struct, kw_only=True):
    uid: UUID
    resource_id: str
    revision_id: str

    parent_revision_id: str | UnsetType = UNSET
    schema_version: str | UnsetType = UNSET
    data_hash: str | UnsetType = UNSET

    status: RevisionStatus

    created_time: dt.datetime
    updated_time: dt.datetime
    created_by: str
    updated_by: str


class Resource(Struct, Generic[T]):
    info: RevisionInfo
    data: T


class ResourceMeta(Struct, kw_only=True):
    current_revision_id: str
    resource_id: str
    schema_version: str | UnsetType = UNSET

    total_revision_count: int

    created_time: dt.datetime
    updated_time: dt.datetime
    created_by: str
    updated_by: str

    is_deleted: bool = False

    # 新增：存儲被索引的 data 欄位值
    indexed_data: dict[str, Any] | UnsetType = UNSET


class ResourceAction(Flag):
    create = auto()
    get = auto()
    get_resource_revision = auto()
    list_revisions = auto()
    get_meta = auto()
    search_resources = auto()
    update = auto()
    patch = auto()
    switch = auto()
    delete = auto()
    restore = auto()
    dump = auto()
    load = auto()

    create_or_update = create | update

    read = get | get_meta | get_resource_revision | list_revisions
    read_list = search_resources
    write = create | update | patch
    lifecycle = switch | delete | restore
    backup = dump | load
    full = read | read_list | write | lifecycle | backup
    owner = update | switch | restore | delete | patch


class DataSearchOperator(StrEnum):
    equals = "eq"
    not_equals = "ne"
    greater_than = "gt"
    greater_than_or_equal = "gte"
    less_than = "lt"
    less_than_or_equal = "lte"
    contains = "contains"  # For string fields
    starts_with = "starts_with"  # For string fields
    ends_with = "ends_with"  # For string fields
    in_list = "in"
    not_in_list = "not_in"


class DataSearchCondition(Struct, kw_only=True):
    field_path: str
    operator: DataSearchOperator
    value: Any


class ResourceMetaSortDirection(StrEnum):
    ascending = "+"
    descending = "-"


class ResourceDataSearchSort(Struct, kw_only=True):
    direction: ResourceMetaSortDirection = ResourceMetaSortDirection.ascending
    field_path: str


class ResourceMetaSortKey(StrEnum):
    created_time = "created_time"
    updated_time = "updated_time"
    resource_id = "resource_id"


class ResourceMetaSearchSort(Struct, kw_only=True):
    direction: ResourceMetaSortDirection = ResourceMetaSortDirection.ascending
    key: ResourceMetaSortKey


class ResourceMetaSearchQuery(Struct, kw_only=True):
    is_deleted: bool | UnsetType = UNSET

    created_time_start: dt.datetime | UnsetType = UNSET
    created_time_end: dt.datetime | UnsetType = UNSET
    updated_time_start: dt.datetime | UnsetType = UNSET
    updated_time_end: dt.datetime | UnsetType = UNSET

    created_bys: list[str] | UnsetType = UNSET
    updated_bys: list[str] | UnsetType = UNSET

    # 新增：data 欄位搜尋條件
    data_conditions: list[DataSearchCondition] | UnsetType = UNSET

    limit: int = 10
    offset: int = 0

    sorts: list[ResourceMetaSearchSort | ResourceDataSearchSort] | UnsetType = UNSET


# ============================================================================
# Base Context Classes
# ============================================================================


class BaseContext(Struct, tag=True, tag_field="context_type"): ...


class BaseBeforeContext(BaseContext):
    phase: str = "before"


class BaseAfterContext(BaseContext):
    phase: str = "after"


class BaseOnSuccessContext(BaseContext):
    phase: str = "on_success"


class BaseOnFailureContext(BaseContext):
    phase: str = "on_failure"
    error: str
    stack_trace: str | None = None


# ============================================================================
# Create Context Classes
# ============================================================================


class BaseCreateContext(BaseContext):
    action: ResourceAction = ResourceAction.create
    data: T


class BeforeCreate(BaseCreateContext, BaseBeforeContext):
    pass


class AfterCreate(BaseCreateContext, BaseAfterContext):
    pass


class OnSuccessCreate(BaseCreateContext, BaseOnSuccessContext):
    info: RevisionInfo


class OnFailureCreate(BaseCreateContext, BaseOnFailureContext):
    pass


# ============================================================================
# Get Context Classes
# ============================================================================


class BaseGetContext(BaseContext):
    action: ResourceAction = ResourceAction.get
    resource_id: str


class BeforeGet(BaseGetContext, BaseBeforeContext):
    pass


class AfterGet(BaseGetContext, BaseAfterContext):
    pass


class OnSuccessGet(BaseGetContext, BaseOnSuccessContext):
    resource: Resource[T]


class OnFailureGet(BaseGetContext, BaseOnFailureContext):
    pass


# ============================================================================
# Get Resource Revision Context Classes
# ============================================================================


class BaseGetResourceRevisionContext(BaseContext):
    action: ResourceAction = ResourceAction.get_resource_revision
    resource_id: str
    revision_id: str


class BeforeGetResourceRevision(BaseGetResourceRevisionContext, BaseBeforeContext):
    pass


class AfterGetResourceRevision(BaseGetResourceRevisionContext, BaseAfterContext):
    pass


class OnSuccessGetResourceRevision(
    BaseGetResourceRevisionContext, BaseOnSuccessContext
):
    resource: Resource[T]


class OnFailureGetResourceRevision(
    BaseGetResourceRevisionContext, BaseOnFailureContext
):
    pass


# ============================================================================
# List Revisions Context Classes
# ============================================================================


class BaseListRevisionsContext(BaseContext):
    action: ResourceAction = ResourceAction.list_revisions
    resource_id: str


class BeforeListRevisions(BaseListRevisionsContext, BaseBeforeContext): ...


class AfterListRevisions(BaseListRevisionsContext, BaseAfterContext): ...


class OnSuccessListRevisions(BaseListRevisionsContext, BaseOnSuccessContext):
    revisions: list[str]


class OnFailureListRevisions(BaseListRevisionsContext, BaseOnFailureContext): ...


# ============================================================================
# Get Meta Context Classes
# ============================================================================


class BaseGetMetaContext(BaseContext):
    action: ResourceAction = ResourceAction.get_meta
    resource_id: str


class BeforeGetMeta(BaseGetMetaContext, BaseBeforeContext): ...


class AfterGetMeta(BeforeGetMeta, BaseAfterContext): ...


class OnSuccessGetMeta(BeforeGetMeta, BaseOnSuccessContext):
    meta: ResourceMeta


class OnFailureGetMeta(BeforeGetMeta, BaseOnFailureContext): ...


# ============================================================================
# Search Resources Context Classes
# ============================================================================


class BaseSearchResourcesContext(BaseContext):
    action: ResourceAction = ResourceAction.search_resources
    query: "ResourceMetaSearchQuery"


class BeforeSearchResources(BaseSearchResourcesContext, BaseBeforeContext):
    pass


class AfterSearchResources(BaseSearchResourcesContext, BaseAfterContext):
    pass


class OnSuccessSearchResources(BaseSearchResourcesContext, BaseOnSuccessContext):
    results: list[ResourceMeta]


class OnFailureSearchResources(BaseSearchResourcesContext, BaseOnFailureContext):
    pass


# ============================================================================
# Update Context Classes
# ============================================================================


class BaseUpdateContext(BaseContext):
    action: ResourceAction = ResourceAction.update
    resource_id: str
    data: T


class BeforeUpdate(BaseUpdateContext, BaseBeforeContext):
    pass


class AfterUpdate(BaseUpdateContext, BaseAfterContext):
    pass


class OnSuccessUpdate(BaseUpdateContext, BaseOnSuccessContext):
    revision_info: RevisionInfo


class OnFailureUpdate(BaseUpdateContext, BaseOnFailureContext):
    pass


# ============================================================================
# Patch Context Classes
# ============================================================================


class BasePatchContext(BaseContext):
    action: ResourceAction = ResourceAction.patch
    resource_id: str
    patch_data: list[dict[str, Any]]  # JsonPatch.patch


class BeforePatch(BasePatchContext, BaseBeforeContext):
    pass


class AfterPatch(BasePatchContext, BaseAfterContext):
    pass


class OnSuccessPatch(BasePatchContext, BaseOnSuccessContext):
    revision_info: RevisionInfo


class OnFailurePatch(BasePatchContext, BaseOnFailureContext):
    pass


# ============================================================================
# Switch Context Classes
# ============================================================================


class BaseSwitchContext(BaseContext):
    action: ResourceAction = ResourceAction.switch
    resource_id: str
    revision_id: str


class BeforeSwitch(BaseSwitchContext, BaseBeforeContext):
    pass


class AfterSwitch(BaseSwitchContext, BaseAfterContext):
    pass


class OnSuccessSwitch(BaseSwitchContext, BaseOnSuccessContext):
    meta: ResourceMeta


class OnFailureSwitch(BaseSwitchContext, BaseOnFailureContext):
    pass


# ============================================================================
# Delete Context Classes
# ============================================================================


class BaseDeleteContext(BaseContext):
    action: ResourceAction = ResourceAction.delete
    resource_id: str


class BeforeDelete(BaseDeleteContext, BaseBeforeContext):
    pass


class AfterDelete(BaseDeleteContext, BaseAfterContext):
    pass


class OnSuccessDelete(BaseDeleteContext, BaseOnSuccessContext):
    meta: ResourceMeta


class OnFailureDelete(BaseDeleteContext, BaseOnFailureContext):
    pass


# ============================================================================
# Restore Context Classes
# ============================================================================


class BaseRestoreContext(BaseContext):
    action: ResourceAction = ResourceAction.restore
    resource_id: str


class BeforeRestore(BaseRestoreContext, BaseBeforeContext):
    pass


class AfterRestore(BaseRestoreContext, BaseAfterContext):
    pass


class OnSuccessRestore(BaseRestoreContext, BaseOnSuccessContext):
    meta: ResourceMeta


class OnFailureRestore(BaseRestoreContext, BaseOnFailureContext):
    pass


# ============================================================================
# Dump Context Classes
# ============================================================================


class BaseDumpContext(BaseContext):
    action: ResourceAction = ResourceAction.dump


class BeforeDump(BaseDumpContext, BaseBeforeContext):
    pass


class AfterDump(BaseDumpContext, BaseAfterContext):
    pass


class OnSuccessDump(BaseDumpContext, BaseOnSuccessContext): ...


class OnFailureDump(BaseDumpContext, BaseOnFailureContext):
    pass


# ============================================================================
# Load Context Classes
# ============================================================================


class BaseLoadContext(BaseContext):
    action: ResourceAction = ResourceAction.load
    key: str


class BeforeLoad(BaseLoadContext, BaseBeforeContext):
    pass


class AfterLoad(BaseLoadContext, BaseAfterContext):
    pass


class OnSuccessLoad(BaseLoadContext, BaseOnSuccessContext):
    pass


class OnFailureLoad(BaseLoadContext, BaseOnFailureContext):
    pass
