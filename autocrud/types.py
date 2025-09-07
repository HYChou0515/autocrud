import datetime as dt
from enum import Flag, StrEnum, auto
from typing import Any

from msgspec import UNSET, Struct, UnsetType


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


class BaseCreateContext(BaseContext):
    action: ResourceAction = ResourceAction.create


class BeforeCreate(BaseCreateContext, BaseBeforeContext): ...


class AfterCreate(BaseCreateContext, BaseAfterContext): ...


class OnSuccessCreate(BaseCreateContext, BaseOnSuccessContext): ...


class OnFailureCreate(BaseCreateContext, BaseOnFailureContext): ...


class BaseGetContext(BaseContext):
    action: ResourceAction = ResourceAction.get


class BeforeGet(BaseGetContext, BaseBeforeContext): ...


class AfterGet(BaseGetContext, BaseAfterContext): ...


class OnSuccessGet(BaseGetContext, BaseOnSuccessContext): ...


class OnFailureGet(BaseGetContext, BaseOnFailureContext): ...


class BaseGetResourceRevisionContext(BaseContext):
    action: ResourceAction = ResourceAction.get_resource_revision


class BeforeGetResourceRevision(BaseGetResourceRevisionContext, BaseBeforeContext): ...


class AfterGetResourceRevision(BaseGetResourceRevisionContext, BaseAfterContext): ...


class OnSuccessGetResourceRevision(
    BaseGetResourceRevisionContext, BaseOnSuccessContext
): ...


class OnFailureGetResourceRevision(
    BaseGetResourceRevisionContext, BaseOnFailureContext
): ...


class BaseListRevisionsContext(BaseContext):
    action: ResourceAction = ResourceAction.list_revisions


class BeforeListRevisions(BaseListRevisionsContext, BaseBeforeContext): ...


class AfterListRevisions(BaseListRevisionsContext, BaseAfterContext): ...


class OnSuccessListRevisions(BaseListRevisionsContext, BaseOnSuccessContext): ...


class OnFailureListRevisions(BaseListRevisionsContext, BaseOnFailureContext): ...


class BaseGetMetaContext(BaseContext):
    action: ResourceAction = ResourceAction.get_meta


class BeforeGetMeta(BaseGetMetaContext, BaseBeforeContext):
    resource_id: str


class AfterGetMeta(BeforeGetMeta, BaseAfterContext): ...


class OnSuccessGetMeta(BeforeGetMeta, BaseOnSuccessContext):
    meta: ResourceMeta


class OnFailureGetMeta(BeforeGetMeta, BaseOnFailureContext): ...


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


class BaseUpdateContext(BaseContext):
    action: ResourceAction = ResourceAction.update


class BeforeUpdate(BaseUpdateContext, BaseBeforeContext): ...


class AfterUpdate(BaseUpdateContext, BaseAfterContext): ...


class OnSuccessUpdate(BaseUpdateContext, BaseOnSuccessContext): ...


class OnFailureUpdate(BaseUpdateContext, BaseOnFailureContext): ...


class BasePatchContext(BaseContext):
    action: ResourceAction = ResourceAction.patch


class BeforePatch(BasePatchContext, BaseBeforeContext): ...


class AfterPatch(BasePatchContext, BaseAfterContext): ...


class OnSuccessPatch(BasePatchContext, BaseOnSuccessContext): ...


class OnFailurePatch(BasePatchContext, BaseOnFailureContext): ...


class BaseSwitchContext(BaseContext):
    action: ResourceAction = ResourceAction.switch


class BeforeSwitch(BaseSwitchContext, BaseBeforeContext): ...


class AfterSwitch(BaseSwitchContext, BaseAfterContext): ...


class OnSuccessSwitch(BaseSwitchContext, BaseOnSuccessContext): ...


class OnFailureSwitch(BaseSwitchContext, BaseOnFailureContext): ...


class BaseDeleteContext(BaseContext):
    action: ResourceAction = ResourceAction.delete


class BeforeDelete(BaseDeleteContext, BaseBeforeContext): ...


class AfterDelete(BaseDeleteContext, BaseAfterContext): ...


class OnSuccessDelete(BaseDeleteContext, BaseOnSuccessContext): ...


class OnFailureDelete(BaseDeleteContext, BaseOnFailureContext): ...


class BaseRestoreContext(BaseContext):
    action: ResourceAction = ResourceAction.restore


class BeforeRestore(BaseRestoreContext, BaseBeforeContext): ...


class AfterRestore(BaseRestoreContext, BaseAfterContext): ...


class OnSuccessRestore(BaseRestoreContext, BaseOnSuccessContext): ...


class OnFailureRestore(BaseRestoreContext, BaseOnFailureContext): ...


class BaseDumpContext(BaseContext):
    action: ResourceAction = ResourceAction.dump


class BeforeDump(BaseDumpContext, BaseBeforeContext): ...


class AfterDump(BaseDumpContext, BaseAfterContext): ...


class OnSuccessDump(BaseDumpContext, BaseOnSuccessContext): ...


class OnFailureDump(BaseDumpContext, BaseOnFailureContext): ...


class BaseLoadContext(BaseContext):
    action: ResourceAction = ResourceAction.load


class BeforeLoad(BaseLoadContext, BaseBeforeContext): ...


class AfterLoad(BaseLoadContext, BaseAfterContext): ...


class OnSuccessLoad(BaseLoadContext, BaseOnSuccessContext): ...


class OnFailureLoad(BaseLoadContext, BaseOnFailureContext): ...
