import datetime as dt
from abc import ABC, abstractmethod
from collections.abc import Generator, Iterable
from contextlib import AbstractContextManager
from enum import Enum, Flag, StrEnum, auto
from typing import (
    IO,
    Annotated,
    Any,
    Callable,
    Generic,
    TypeVar,
    get_args,
    get_origin,
    get_type_hints,
)
from uuid import UUID

from jsonpatch import JsonPatch
from jsonpointer import JsonPointer
from msgspec import UNSET, Struct, UnsetType, defstruct
from typing_extensions import Literal

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Resource References (Ref / RefRevision)
# ---------------------------------------------------------------------------


class OnDelete(StrEnum):
    """Defines the referential action when the referenced resource is deleted."""

    dangling = "dangling"
    """No action taken. The reference becomes dangling. (default)"""

    set_null = "set_null"
    """Set the referencing field to null. Requires the field to be Optional."""

    cascade = "cascade"
    """Delete the referencing resource as well."""


class Ref:
    """Metadata marker for a field that references another resource's resource_id.

    Use with ``Annotated`` to annotate a ``str`` field that holds a reference
    to another AutoCRUD resource.

    Example::

        class Monster(Struct):
            zone_id: Annotated[str, Ref("zone")]
            guild_id: Annotated[
                str | None, Ref("guild", on_delete=OnDelete.set_null)
            ] = None
            owner_id: Annotated[str, Ref("character", on_delete=OnDelete.cascade)]
    """

    __slots__ = ("resource", "on_delete")

    def __init__(
        self, resource: str, *, on_delete: OnDelete = OnDelete.dangling
    ) -> None:
        self.resource = resource
        self.on_delete = OnDelete(on_delete)

    def __repr__(self) -> str:
        return f"Ref({self.resource!r}, on_delete={self.on_delete!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Ref):
            return NotImplemented
        return self.resource == other.resource and self.on_delete == other.on_delete

    def __hash__(self) -> int:
        return hash((self.resource, self.on_delete))


class RefRevision:
    """Metadata marker for a field that references another resource's revision_id.

    Example::

        class Monster(Struct):
            zone_revision_id: Annotated[str, RefRevision("zone")]
    """

    __slots__ = ("resource",)

    def __init__(self, resource: str) -> None:
        self.resource = resource

    def __repr__(self) -> str:
        return f"RefRevision({self.resource!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RefRevision):
            return NotImplemented
        return self.resource == other.resource

    def __hash__(self) -> int:
        return hash(self.resource)


class _RefInfo(Struct, frozen=True, kw_only=True):
    """Describes a single reference relationship discovered from type annotations."""

    source: str
    """Name of the resource that contains the reference."""
    source_field: str
    """Field name on the source resource."""
    target: str
    """Name of the referenced resource."""
    ref_type: str
    """Either ``'resource_id'`` or ``'revision_id'``."""
    on_delete: OnDelete
    """Referential action on delete."""
    nullable: bool
    """Whether the field is nullable (Optional)."""
    is_list: bool = False
    """Whether the field is a list of references (e.g. ``list[Annotated[str, Ref(...)]]``)."""


def extract_refs(struct_type: type, source_name: str) -> list[_RefInfo]:
    """Scan a Struct's annotated fields and extract all Ref / RefRevision markers.

    Handles both direct ``Annotated[str, Ref(...)]`` and nullable
    ``Annotated[str | None, Ref(...)]`` forms.
    """
    refs: list[_RefInfo] = []
    try:
        hints = get_type_hints(struct_type, include_extras=True)
    except Exception:
        return refs

    for field_name, hint in hints.items():
        _extract_from_hint(hint, field_name, source_name, refs)
    return refs


def _extract_from_hint(
    hint: Any,
    field_name: str,
    source_name: str,
    out: list[_RefInfo],
    *,
    is_list: bool = False,
) -> None:
    origin = get_origin(hint)

    if origin is Annotated:
        args = get_args(hint)
        inner_type = args[0] if args else None
        nullable = _is_nullable(inner_type)
        for metadata in args[1:]:
            if isinstance(metadata, Ref):
                out.append(
                    _RefInfo(
                        source=source_name,
                        source_field=field_name,
                        target=metadata.resource,
                        ref_type="resource_id",
                        on_delete=metadata.on_delete,
                        nullable=nullable,
                        is_list=is_list,
                    )
                )
            elif isinstance(metadata, RefRevision):
                out.append(
                    _RefInfo(
                        source=source_name,
                        source_field=field_name,
                        target=metadata.resource,
                        ref_type="revision_id",
                        on_delete=OnDelete.dangling,
                        nullable=nullable,
                        is_list=is_list,
                    )
                )
        return

    # Fallback: unwrap Union/Optional and recurse into each arg
    # Detect list origin to propagate is_list flag
    if origin is list:
        is_list = True
    args = get_args(hint)
    if args:
        for arg in args:
            _extract_from_hint(arg, field_name, source_name, out, is_list=is_list)


def _is_nullable(tp: Any) -> bool:
    """Return True if ``tp`` is a Union that includes NoneType."""
    origin = get_origin(tp)
    if origin is not None:
        args = get_args(tp)
        return type(None) in args
    return tp is type(None)


class DisplayName:
    """Annotation marker designating a ``str`` field as the display name.

    Usage::

        class Character(Struct):
            name: Annotated[str, DisplayName()]  # ← this field is the display name
            level: int = 1

    The AutoCRUD framework will inject ``x-display-name-field`` into the
    OpenAPI schema so the web frontend can show a friendly name instead of
    just the resource ID.
    """

    __slots__ = ("label",)

    def __init__(self, label: str | None = None) -> None:
        self.label = label

    def __repr__(self) -> str:
        if self.label is None:
            return "DisplayName()"
        return f"DisplayName({self.label!r})"


def extract_display_name(struct_type: type) -> str | None:
    """Return the field name annotated with :class:`DisplayName`, or ``None``."""
    try:
        hints = get_type_hints(struct_type, include_extras=True)
    except Exception:
        return None
    for field_name, hint in hints.items():
        origin = get_origin(hint)
        if origin is Annotated:
            for metadata in get_args(hint)[1:]:
                if isinstance(metadata, DisplayName):
                    return field_name
    return None


class RevisionStatus(StrEnum):
    draft = "draft"
    stable = "stable"


class RevisionInfo(Struct, kw_only=True):
    """Metadata about a specific revision of a resource.

    This class contains essential information about a particular revision,
    """

    uid: UUID
    """The unique identifier for this revision.
    
    This is a UUID that uniquely identifies this specific revision of the resource.
    You don't need this value for most operations; use `resource_id` and `revision_id` instead.
    """
    resource_id: str
    """The ID of this revision of the resource."""
    revision_id: str
    """The unique identifier for the resource."""

    parent_revision_id: str | None = None
    """The ID of the parent revision, if any."""
    parent_schema_version: str | None | UnsetType = UNSET
    """The schema version of the parent revision, if any.
    
    This field is UNSET if the parent revision does not exist.
    """
    schema_version: str | None = None
    """The schema version of this revision.
    
    None is a valid schema version, indicating the default version.
    """
    data_hash: str | UnsetType = UNSET
    """The hash of the data for this revision.
    
    If UNSET, the hash has not been computed.
    """

    status: RevisionStatus
    """The status of this revision."""

    created_time: dt.datetime
    """The time when this revision was created."""
    updated_time: dt.datetime
    """The time when this revision was last updated.
    
    Note that this may only be different from created_time if the revision was 
    modified without creating a new revision (e.g., patching a draft).
    """
    created_by: str
    """The user who created this revision."""
    updated_by: str
    """The user who last updated this revision.
    
    Note that this may only be different from created_by if the revision was 
    modified without creating a new revision (e.g., patching a draft).
    """


class Resource(Struct, Generic[T]):
    info: RevisionInfo
    data: T


class Binary(Struct):
    """A wrapper for binary data that handles storage optimization.

    When creating a resource, you can populate the `data` field with bytes.
    The system will automatically extract it, store it in the blob store,
    and populate `file_id` (which is the hash of the content) and `size`.
    The `data` field will be cleared in the stored resource.
    """

    file_id: str | UnsetType = UNSET
    """The unique identifier of the stored blob (hash of the content)."""

    size: int | UnsetType = UNSET
    """Size of the binary content in bytes."""

    content_type: str | UnsetType = UNSET
    """MIME type of the content."""

    data: bytes | UnsetType = UNSET
    """Binary content. Used for input or specific retrieval, usually None in storage."""


class RawResource(Struct):
    info: RevisionInfo
    raw_data: bytes


class ResourceMeta(Struct, kw_only=True):
    """Metadata about a resource, including its current revision and status.

    This class provides essential information about a resource without including
    the full data content.
    """

    current_revision_id: str
    """The ID of the current revision of the resource."""
    resource_id: str
    """The unique identifier for the resource."""
    schema_version: str | None = None
    """The schema version of the resource.
    
    This indicates the version of the data schema that the resource conforms to.
    """

    total_revision_count: int
    """The total number of revisions for the resource."""

    created_time: dt.datetime
    """The time when the resource was created."""
    updated_time: dt.datetime
    """The time when the resource was last updated."""
    created_by: str
    """The user who created the resource."""
    updated_by: str
    """The user who last updated the resource."""

    is_deleted: bool = False
    """Indicates whether the resource has been deleted."""

    indexed_data: dict[str, Any] | UnsetType = UNSET
    """A dictionary of indexed fields for the resource, used for searching and sorting."""


class SearchedResource(Struct, Generic[T]):
    """A resource item returned by list_resources.

    Each field may be the full type, a partial Struct (when partial fields
    are requested), or UNSET (when excluded via the *returns* parameter).
    """

    data: T | Struct | UnsetType = UNSET
    info: RevisionInfo | Struct | UnsetType = UNSET
    meta: ResourceMeta | Struct | UnsetType = UNSET


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
    migrate = auto()
    modify = auto()

    create_or_update = create | update | modify

    read = get | get_meta | get_resource_revision | list_revisions
    read_list = search_resources
    write = create | update | modify | patch
    lifecycle = switch | delete | restore
    backup = dump | load | migrate
    full = read | read_list | write | lifecycle | backup
    owner = read | patch | update | modify | lifecycle


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
    is_null = "is_null"
    exists = "exists"
    isna = "isna"
    regex = "regex"


class FieldTransform(StrEnum):
    """Field transformation functions that can be applied before comparison."""

    length = "len"  # Get length of string, list, dict, etc.


class DataSearchCondition(Struct, kw_only=True, tag=True):
    field_path: str
    operator: DataSearchOperator
    value: Any
    transform: FieldTransform | None = None  # Optional field transformation


class DataSearchLogicOperator(StrEnum):
    and_op = "and"
    or_op = "or"
    not_op = "not"


class DataSearchGroup(Struct, kw_only=True, tag=True):
    operator: DataSearchLogicOperator
    conditions: list["DataSearchCondition | DataSearchGroup"]


DataSearchFilter = DataSearchCondition | DataSearchGroup


class ResourceMetaSortDirection(StrEnum):
    ascending = "+"
    descending = "-"


class ResourceDataSearchSort(Struct, kw_only=True, tag=True):
    direction: ResourceMetaSortDirection = ResourceMetaSortDirection.ascending
    field_path: str


class ResourceMetaSortKey(StrEnum):
    created_time = "created_time"
    updated_time = "updated_time"
    resource_id = "resource_id"


class ResourceMetaSearchSort(Struct, kw_only=True, tag=True):
    direction: ResourceMetaSortDirection = ResourceMetaSortDirection.ascending
    key: ResourceMetaSortKey


class ResourceMetaSearchQuery(Struct, kw_only=True):
    is_deleted: bool | UnsetType = UNSET
    """Filter by deletion status of the resource."""

    created_time_start: dt.datetime | UnsetType = UNSET
    """Filter resources created >= this time."""
    created_time_end: dt.datetime | UnsetType = UNSET
    """Filter resources created <= this time."""
    updated_time_start: dt.datetime | UnsetType = UNSET
    """Filter resources updated >= this time."""
    updated_time_end: dt.datetime | UnsetType = UNSET
    """Filter resources updated <= this time."""

    created_bys: list[str] | UnsetType = UNSET
    """Filter resources created by these users."""
    updated_bys: list[str] | UnsetType = UNSET
    """Filter resources updated by these users."""

    data_conditions: list[DataSearchFilter] | UnsetType = UNSET
    """Deprecated. Use `conditions` instead. Conditions to filter resources based on their indexed data fields."""

    conditions: list[DataSearchFilter] | UnsetType = UNSET
    """Conditions to filter resources based on their metadata or indexed data fields."""

    limit: int = 10
    """Maximum number of results to return."""
    offset: int = 0
    """Number of results to skip before starting to collect the result set."""

    sorts: list[ResourceMetaSearchSort | ResourceDataSearchSort] | UnsetType = UNSET
    """Sorting criteria for the search results."""


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
    ("key", str),
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


class IMigration(ABC, Generic[T]):
    """Interface for handling data migration between different schema versions.

    This interface defines the contract for migrating resource data when schema
    versions change. Implementations should handle the transformation of data
    from older schema versions to the current version.
    """

    @abstractmethod
    def migrate(self, data: IO[bytes], schema_version: str | None) -> T:
        """Migrate resource data from an older schema version to the current version.

        Args:
            data: Binary stream containing the serialized resource data
            schema_version: The schema version of the input data, or UNSET if unknown

        Returns:
            T: The migrated data object in the current schema format

        Raises:
            ValueError: If the schema version is not supported
        """
        ...

    @property
    @abstractmethod
    def schema_version(self) -> str | None:
        """The target schema version for this migration.

        Returns:
            str | None: The schema version that this migration targets,
            or None if no specific version is targeted.
        """
        ...


class IResourceManager(ABC, Generic[T]):
    """Interface for managing versioned resources with full lifecycle support.

    This is the core interface for AutoCRUD's resource management system.
    It provides CRUD operations, versioning, search, permissions, and more.
    """

    @property
    @abstractmethod
    def user(self) -> str:
        """Get the current user from context.

        Returns:
            str: The current user identifier.

        Raises:
            LookupError: If no user is set in the context.
        """

    @property
    @abstractmethod
    def now(self) -> dt.datetime:
        """Get the current timestamp from context.

        Returns:
            datetime: The current timestamp.

        Raises:
            LookupError: If no timestamp is set in the context.
        """

    @property
    @abstractmethod
    def user_or_unset(self) -> str | UnsetType:
        """Get the current user from context, or UNSET if not available.

        Returns:
            str | UnsetType: The current user identifier or UNSET.
        """

    @property
    @abstractmethod
    def now_or_unset(self) -> dt.datetime | UnsetType:
        """Get the current timestamp from context, or UNSET if not available.

        Returns:
            datetime | UnsetType: The current timestamp or UNSET.
        """

    @property
    @abstractmethod
    def resource_type(self) -> type[T]:
        """Get the resource data type managed by this manager.

        Returns:
            type[T]: The resource type class.
        """

    @abstractmethod
    def migrate(self, resource_id: str) -> ResourceMeta:
        """Migrate a resource to the latest schema version.

        Args:
            resource_id: The ID of the resource to migrate.

        Returns:
            ResourceMeta: The updated metadata after migration.

        Raises:
            ValueError: If migration logic is not configured.
            ResourceIDNotFoundError: If the resource ID does not exist.
        """

    @property
    @abstractmethod
    def schema_version(self) -> str:
        """Get the current schema version for this resource type.

        Returns:
            str: The schema version identifier.

        Raises:
            ValueError: If schema version is not configured.
        """

    @property
    @abstractmethod
    def resource_name(self) -> str:
        """Get the name of this resource type.

        Returns:
            str: The resource name.
        """

    @abstractmethod
    def meta_provide(
        self,
        user: str | UnsetType = UNSET,
        now: dt.datetime | UnsetType = UNSET,
        *,
        resource_id: str | UnsetType = UNSET,
    ) -> AbstractContextManager:
        """Context manager to provide metadata context (user, time, resource_id).

        Args:
            user: The user performing the action.
            now: The current timestamp.
            resource_id: Specific resource ID to use.

        Yields:
            None: Use this as a context manager with 'with' statement.
        """

    @abstractmethod
    def create(
        self, data: T, *, status: RevisionStatus | UnsetType = UNSET
    ) -> RevisionInfo:
        """Create a new resource.

        This method creates a new resource with an initial revision. The resource
        will be assigned a unique resource_id and revision_id.

        Args:
            data: The resource data object conforming to the resource type.
            status: The initial status of the resource (default: stable).

        Returns:
            RevisionInfo: Metadata about the created revision including
                resource_id, revision_id, created_time, created_by, and status.

        Note:
            Binary fields (Binary type) will be automatically extracted and stored
            in the blob store if configured.
        """

    @abstractmethod
    def exists(self, resource_id: str) -> bool:
        """Check if a resource exists.

        Args:
            resource_id: The ID of the resource to check.

        Returns:
            bool: True if the resource exists, False otherwise.
        """

    @abstractmethod
    def revision_exists(self, resource_id: str, revision_id: str) -> bool:
        """Check if a specific revision of a resource exists.

        Args:
            resource_id: The ID of the resource.
            revision_id: The revision ID to check.

        Returns:
            bool: True if the revision exists, False otherwise.
        """

    @abstractmethod
    def get(
        self,
        resource_id: str,
        *,
        revision_id: str | UnsetType = UNSET,
        schema_version: str | None | UnsetType = UNSET,
    ) -> Resource[T]:
        """Get the current revision of the resource.

        Args:
            resource_id (str): the id of the resource to get.
            revision_id (str | UnsetType): the id of a specific revision to get.
              If UNSET, the current revision is returned.
        Returns:
            resource (Resource[T]): the resource with its data and revision info.

        Raises:
            ResourceIDNotFoundError: if resource id does not exist.
            ResourceIsDeletedError: if resource is soft-deleted.

        ---

        Returns the current revision of the specified resource. The current revision
        is determined by the `current_revision_id` field in ResourceMeta.

        This method will raise different exceptions based on the resource state:
        - ResourceIDNotFoundError: The resource ID does not exist in storage
        - ResourceIsDeletedError: The resource exists but is marked as deleted (is_deleted=True)

        For soft-deleted resources, use restore() first to make them accessible again.
        """

    @abstractmethod
    def get_partial(
        self, resource_id: str, revision_id: str, partial: Iterable[str | JsonPointer]
    ) -> Struct:
        """Get a partial view of the resource data for a specific revision.

        Args:
            resource_id (str): the id of the resource.
            revision_id (str): the id of the specific revision to retrieve.
            partial (Iterable[str | JsonPointer]): list of field paths to include in the result.
        Returns:
            partial_data (Struct): a Struct containing only the requested fields.
        Raises:
            ResourceIDNotFoundError: if resource id does not exist.
            RevisionIDNotFoundError: if revision id does not exist for this resource.

        Retrieves a subset of the resource's data for the specified revision,
        based on the provided list of field paths. This allows clients to fetch
        only the data they need, reducing bandwidth and processing overhead.
        This method does NOT check the is_deleted status of the resource metadata,
        allowing access to revisions of soft-deleted resources for audit and
        recovery purposes.
        The returned Struct contains only the fields specified in the `partial`
        argument, preserving the original data structure for those fields.
        """

    @abstractmethod
    def get_revision_info(
        self, resource_id: str, revision_id: str | UnsetType = UNSET
    ) -> RevisionInfo:
        """Get the RevisionInfo for a specific revision of the resource.

        Args:
            resource_id (str): the id of the resource.
            revision_id (str | UnsetType): the id of the specific revision to retrieve.
              If UNSET, the current revision is returned.
        Returns:
            info (RevisionInfo): the metadata of the specified revision.
        Raises:
            ResourceIDNotFoundError: if resource id does not exist.
            RevisionIDNotFoundError: if revision id does not exist for this resource.

        Retrieves the RevisionInfo metadata for a specific revision of the resource.
        If revision_id is UNSET, the current revision's info is returned. This method does NOT
        check the is_deleted status of the resource metadata, allowing access to revisions of
        soft-deleted resources for audit and recovery purposes.
        """

    @abstractmethod
    def get_resource_revision(
        self,
        resource_id: str,
        revision_id: str,
        schema_version: str | None | UnsetType = UNSET,
    ) -> Resource[T]:
        """Get a specific revision of the resource.

        Args:
            resource_id (str): the id of the resource.
            revision_id (str): the id of the specific revision to retrieve.

        Returns:
            resource (Resource[T]): the resource with its data and revision info for the specified revision.

        Raises:
            ResourceIDNotFoundError: if resource id does not exist.
            RevisionIDNotFoundError: if revision id does not exist for this resource.

        ---

        Retrieves a specific historical revision of the resource identified by both
        resource_id and revision_id. Unlike get() which returns the current revision,
        this method allows access to any revision in the resource's history.

        This method does NOT check the is_deleted status of the resource metadata,
        allowing access to revisions of soft-deleted resources for audit and
        recovery purposes.

        The returned Resource contains both the data as it existed at that revision
        and the RevisionInfo with metadata about that specific revision.
        """

    @abstractmethod
    def list_revisions(self, resource_id: str) -> list[str]:
        """Get a list of all revision IDs for the resource.

        Args:
            resource_id (str): the id of the resource.

        Returns:
            list[str]: list of revision IDs for the resource, typically ordered chronologically.

        Raises:
            ResourceIDNotFoundError: if resource id does not exist.

        ---

        Returns all revision IDs that exist for the specified resource, providing
        a complete history of all revisions. This is useful for:
        - Browsing the complete revision history
        - Selecting specific revisions for comparison
        - Audit trails and compliance reporting
        - Determining available restore points

        The revision IDs are typically returned in chronological order (oldest to newest),
        but the exact ordering may depend on the implementation.

        This method does NOT check the is_deleted status of the resource, allowing
        access to revision lists for soft-deleted resources.
        """

    @abstractmethod
    def get_meta(self, resource_id: str) -> ResourceMeta:
        """Get the metadata of the resource.

        Args:
            resource_id (str): the id of the resource to get metadata for.

        Returns:
            meta (ResourceMeta): the metadata of the resource.

        Raises:
            ResourceIDNotFoundError: if resource id does not exist.
            ResourceIsDeletedError: if resource is soft-deleted.

        ---

        Returns the metadata of the specified resource, including its current revision,
        total revision count, creation and update timestamps, and user information.
        This method will raise exceptions similar to get() based on the resource state.
        """

    @abstractmethod
    def get_blob(self, file_id: str) -> Binary:
        """Get the binary content of a blob by its file ID."""
        pass

    @abstractmethod
    def get_blob_url(self, file_id: str) -> str | None:
        """Get the direct download URL for a blob by its file ID, if available."""
        pass

    @abstractmethod
    def count_resources(self, query: ResourceMetaSearchQuery) -> int:
        """"""

    @abstractmethod
    def search_resources(self, query: ResourceMetaSearchQuery) -> list[ResourceMeta]:
        """Search for resources based on a query.

        Args:
            query (ResourceMetaSearchQuery): the search criteria and options.

        Returns:
            list[ResourceMeta]: list of resource metadata matching the query criteria.

        ---

        This method allows searching for resources based on various criteria defined
        in the ResourceMetaSearchQuery. The query supports filtering by:
        - Deletion status (is_deleted)
        - Time ranges (created_time_start/end, updated_time_start/end)
        - User filters (created_bys, updated_bys)
        - Pagination (limit, offset)
        - Sorting (sorts with direction and key)

        The results are returned as a list of resource metadata that match the specified
        criteria, ordered according to the sort parameters and limited by the
        pagination settings.
        """

    @abstractmethod
    def list_resources(
        self,
        query: ResourceMetaSearchQuery,
        *,
        returns: list[str] | None = None,
        partial: list[str] | None = None,
    ) -> list["SearchedResource[T]"]:
        """Search for resources and fetch their data in one call.

        Internally calls ``search_resources(query)`` (which triggers
        Before/After/OnSuccess/OnFailure SearchResources events), then
        fetches the requested sections for each matching resource.

        Args:
            query: search criteria (same as ``search_resources``).
            returns: sections to include per item.  Allowed values are
                ``"data"``, ``"info"``, ``"meta"``.  ``None`` means all three.
            partial: optional list of field paths to retrieve.  Paths may
                be prefixed with ``data/``, ``meta/``, or ``info/`` to
                target a specific section; unprefixed paths default to
                ``"data"``.

        Returns:
            list[SearchedResource[T]]: one item per matched resource.
                Fields excluded by *returns* are ``UNSET``.  Fields
                narrowed by *partial* are partial ``Struct`` instances.
        """

    @abstractmethod
    def update(self, resource_id: str, data: T) -> RevisionInfo:
        """Update the data of the resource by creating a new revision.

        Args:
            resource_id (str): the id of the resource to update.
            data (T): the data to replace the current one.

        Returns:
            info (RevisionInfo): the metadata of the newly created revision.

        Raises:
            ResourceIDNotFoundError: if resource id does not exist.
            ResourceIsDeletedError: if resource is soft-deleted.

        ---

        Creates a new revision with the provided data and updates the resource's
        current_revision_id to point to this new revision. The new revision's
        parent_revision_id will be set to the previous current_revision_id.

        This operation will fail if the resource is soft-deleted. Use restore()
        first to make soft-deleted resources accessible for updates.

        For partial updates, use patch() instead of update().
        """

    @abstractmethod
    def create_or_update(self, resource_id: str, data: T) -> RevisionInfo:
        pass

    @abstractmethod
    def modify(
        self,
        resource_id: str,
        data: T | JsonPatch | UnsetType = UNSET,
        status: RevisionStatus | UnsetType = UNSET,
    ) -> RevisionInfo:
        """Modify the data of the resource by update the current revision.

        Args:
            resource_id (str): the id of the resource to modify.
            data (T): the data to replace the current one.
        Returns:
            info (RevisionInfo): the metadata of the modified revision.
        Raises:
            ResourceIDNotFoundError: if resource id does not exist.
            ResourceIsDeletedError: if resource is soft-deleted.
            CannotModifyResourceError: if resource is not in draft status.
        """

    @abstractmethod
    def patch(self, resource_id: str, patch_data: JsonPatch) -> RevisionInfo:
        """Apply RFC 6902 JSON Patch operations to the resource.

        Args:
            resource_id (str): the id of the resource to patch.
            patch_data (JsonPatch): RFC 6902 JSON Patch operations to apply.

        Returns:
            info (RevisionInfo): the metadata of the newly created revision.

        Raises:
            ResourceIDNotFoundError: if resource id does not exist.
            ResourceIsDeletedError: if resource is soft-deleted.

        ---

        Applies the provided JSON Patch operations to the current revision data
        and creates a new revision with the modified data. The patch operations
        follow RFC 6902 standard.

        This method internally:
        1. Gets the current revision data
        2. Applies the patch operations in-place
        3. Creates a new revision via update()

        This operation will fail if the resource is soft-deleted. Use restore()
        first to make soft-deleted resources accessible for patching.
        """

    @abstractmethod
    def switch(self, resource_id: str, revision_id: str) -> ResourceMeta:
        """Switch the current revision to a specific revision.

        Args:
            resource_id (str): the id of the resource.
            revision_id (str): the id of the revision to switch to.

        Returns:
            meta (ResourceMeta): the metadata of the resource after switching.

        Raises:
            ResourceIDNotFoundError: if resource id does not exist.
            ResourceIsDeletedError: if resource is soft-deleted.
            RevisionIDNotFoundError: if revision id does not exist.

        ---

        Changes the current_revision_id in ResourceMeta to point to the specified
        revision. This allows you to make any historical revision the current one
        without deleting any revisions. All historical revisions remain accessible.

        Behavior:
        - If switching to the same revision (current_revision_id == revision_id),
          returns the current metadata without any changes
        - Otherwise, updates current_revision_id, updated_time, and updated_by
        - Subsequent update/patch operations will use the new current revision as parent

        This operation will fail if the resource is soft-deleted. The revision_id
        must exist in the resource's revision history.
        """

    @abstractmethod
    def delete(self, resource_id: str) -> ResourceMeta:
        """Mark the resource as deleted (soft delete).

        Args:
            resource_id (str): the id of the resource to delete.

        Returns:
            meta (ResourceMeta): the updated metadata with is_deleted=True.

        Raises:
            ResourceIDNotFoundError: if resource id does not exist.
            ResourceIsDeletedError: if resource is already soft-deleted.

        ---

        This operation performs a soft delete by setting the `is_deleted` flag to True
        in the ResourceMeta. The resource and all its revisions remain in storage
        and can be recovered later.

        Behavior:
        - Sets `is_deleted = True` in ResourceMeta
        - Updates `updated_time` and `updated_by` to record the deletion
        - All revision data and metadata are preserved
        - Resource can be restored using restore()

        This operation will fail if the resource is already soft-deleted.
        This is a reversible operation that maintains data integrity while
        marking the resource as logically deleted.
        """

    @abstractmethod
    def restore(self, resource_id: str) -> ResourceMeta:
        """Restore a previously deleted resource (undo soft delete).

        Args:
            resource_id (str): the id of the resource to restore.

        Returns:
            meta (ResourceMeta): the updated metadata with is_deleted=False.

        Raises:
            ResourceIDNotFoundError: if resource id does not exist.

        ---

        This operation restores a previously soft-deleted resource by setting
        the `is_deleted` flag back to False in the ResourceMeta. This undoes
        the soft delete operation.

        Behavior:
        - If resource is deleted (is_deleted=True):
          - Sets `is_deleted = False` in ResourceMeta
          - Updates `updated_time` and `updated_by` to record the restoration
          - Saves the updated metadata to storage
        - If resource is not deleted (is_deleted=False):
          - Returns the current metadata without any changes
          - No timestamps are updated

        All revision data and metadata remain unchanged. The resource becomes
        accessible again through normal operations only if it was previously deleted.

        Note: This method pairs with delete() to provide reversible
        soft delete functionality.
        """

    @abstractmethod
    def dump(self) -> Generator[tuple[str, IO[bytes]]]:
        """Dump all resource data as a series of tar archive entries.

        Returns:
            Generator[tuple[str, IO[bytes]]]: generator yielding (filename, fileobj) pairs for each resource.

        ---

        Exports all resources in the manager as a series of tar archive entries.
        Each entry represents one resource and contains both its metadata and
        all revision data in a structured format.

        The generator yields tuples where:
        - filename: A unique identifier for the resource (typically the resource_id)
        - fileobj: An IO[bytes] object containing the tar archive data for that resource

        This method is designed for:
        - Complete data backup and export operations
        - Migrating resources between different systems
        - Creating portable resource archives
        - Bulk data transfer scenarios

        The tar archive format ensures that all resource information including
        metadata, revision history, and data content is preserved in a
        standardized, portable format.

        Note: This method does not filter by deletion status, so both active
        and soft-deleted resources will be included in the dump.
        """

    @abstractmethod
    def load(self, key: str, bio: IO[bytes]) -> None:
        """Load resource data from a tar archive entry.

        Args:
            key (str): the unique identifier for the resource being loaded.
            bio (IO[bytes]): the tar archive containing the resource data.

        ---

        Imports a single resource from a tar archive entry, typically created
        by the dump() method. The tar archive should contain both metadata
        and all revision data for the resource.

        The key parameter serves as the resource identifier and should match
        the filename used when the resource was dumped. The bio parameter
        contains the complete tar archive data for that specific resource.

        This method handles:
        - Extracting metadata and revision information from the archive
        - Restoring all historical revisions with proper parent-child relationships
        - Maintaining data integrity and revision ordering
        - Preserving timestamps, user information, and other metadata

        Use Cases:
        - Restoring resources from backup archives
        - Importing resources from external systems
        - Migrating data between different AutoCRUD instances
        - Bulk resource restoration operations

        Behavior:
        - If a resource with the same key already exists, the behavior depends on implementation
        - All revision history and metadata from the archive will be restored
        - The resource's deletion status and other flags are preserved as archived

        Note: This method should be used in conjunction with dump() for
        complete backup and restore workflows.
        """

    @abstractmethod
    def restore_binary(self, data: T) -> T:
        """
        還原 data 中的 binary.data (如果是從 blob store 讀取).
        這對於需要讀取 Binary 原始資料時很有用.
        """

    @abstractmethod
    def start_consume(self, *, block: bool = True) -> None:
        """Start consuming jobs from the message queue.

        Uses the callback function that was configured when the message queue was created.

        Raises:
            NotImplementedError: if message queue is not configured.
        """


class PermissionDeniedError(Exception):
    pass


class ResourceNotFoundError(Exception):
    pass


class RevisionNotFoundError(ResourceNotFoundError):
    pass


class RevisionIDNotFoundError(RevisionNotFoundError):
    def __init__(self, resource_id: str, revision_id: str):
        super().__init__(
            f"Revision '{revision_id}' of Resource '{resource_id}' not found.",
        )
        self.resource_id = resource_id
        self.revision_id = revision_id


class ResourceIsDeletedError(ResourceNotFoundError):
    def __init__(self, resource_id: str):
        super().__init__(f"Resource '{resource_id}' is deleted.")
        self.resource_id = resource_id


class ResourceIDNotFoundError(ResourceNotFoundError):
    def __init__(self, resource_id: str):
        super().__init__(f"Resource '{resource_id}' not found.")
        self.resource_id = resource_id


class ResourceConflictError(Exception):
    pass


class SchemaConflictError(ResourceConflictError):
    pass


class CannotModifyResourceError(ResourceConflictError):
    def __init__(self, resource_id: str):
        super().__init__(f"Resource '{resource_id}' cannot be modified.")
        self.resource_id = resource_id


class ValidationError(ValueError):
    """Raised when data fails custom validation.

    Inherits from ValueError so it can be caught broadly.
    This is distinct from msgspec.ValidationError which handles
    type-level validation.
    """

    pass


class IValidator(ABC):
    """Interface for custom data validators.

    Implement this to create reusable validators that can be
    attached to ResourceManager via ``add_model(validator=...)``.

    Example::

        class PriceValidator(IValidator):
            def validate(self, data) -> None:
                if data.price < 0:
                    raise ValueError("Price must be non-negative")


        crud.add_model(Item, validator=PriceValidator())
    """

    @abstractmethod
    def validate(self, data: Any) -> None:
        """Validate the data.

        Args:
            data: The resource data (a msgspec Struct instance).

        Raises:
            ValueError: If validation fails. The error will be
                wrapped in a ``ValidationError``.
        """


PermissionContext = EventContext


class PermissionResult(StrEnum):
    """權限檢查結果"""

    allow = "allow"
    deny = "deny"
    not_applicable = "not_applicable"  # 這個檢查器不適用於此操作


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


class SpecialIndex(Enum):
    msgspec_tag = "msgspec_tag"


class IndexableField(Struct):
    """Defines a field that should be indexed for searching."""

    field_path: str  # JSON path to the field, e.g., "name", "user.email"
    field_type: type | SpecialIndex | UnsetType = (
        UNSET  # The type of the field (str, int, float, bool, datetime)
    )


class IEventHandler(ABC):
    @abstractmethod
    def is_supported(self, context: EventContext) -> bool: ...

    @abstractmethod
    def handle_event(self, context: EventContext) -> None: ...


class TaskStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(Struct, Generic[T]):
    payload: T
    """The actual job data/resource."""

    status: TaskStatus = TaskStatus.PENDING
    """Current status of the job."""

    errmsg: str | None = None
    """Result or error message after processing."""

    retries: int = 0
    """Number of times the job has been retried."""

    periodic_interval_seconds: int | None = None
    """If set, the job will be re-enqueued every N seconds after completion."""

    periodic_max_runs: int | None = None
    """Maximum number of times to run the periodic job. None means run indefinitely."""

    periodic_runs: int = 0
    """Number of times this periodic job has been executed."""

    periodic_initial_delay_seconds: int | None = None
    """Delay in seconds before the first execution. If None, executes immediately."""


class IMessageQueue(ABC, Generic[T]):
    """Interface for a message queue that manages jobs as resources."""

    @abstractmethod
    def put(self, resource_id: str) -> Resource[Job[T]]:
        """Enqueue a job that has already been created.

        Args:
            resource_id: The ID of the job resource that was already created.

        Returns:
            The job resource.
        """
        ...

    @abstractmethod
    def pop(self) -> Resource[Job[T]] | None:
        """Dequeue the next pending job."""
        ...

    @abstractmethod
    def complete(self, resource_id: str, result: str | None = None) -> Resource[Job[T]]:
        """Mark a job as completed."""
        ...

    @abstractmethod
    def fail(self, resource_id: str, error: str) -> Resource[Job[T]]:
        """Mark a job as failed."""
        ...

    @abstractmethod
    def start_consume(self) -> None:
        """Start consuming jobs from the queue.

        Uses the callback function that was provided during construction.
        """
        ...

    @abstractmethod
    def stop_consuming(self) -> None:
        """Stop consuming jobs from the queue."""
        ...


class IMessageQueueFactory(ABC):
    """Factory interface for creating message queues."""

    @abstractmethod
    def build(
        self, do: "Callable[[Resource[Job[T]]], None]"
    ) -> "Callable[[IResourceManager[Job[T]]], IMessageQueue[T]]":
        """Build a message queue factory function.

        Args:
            do: Callback function to process each job.

        Returns:
            A callable that accepts an IResourceManager and returns an IMessageQueue instance.
            The ResourceManager will inject itself when calling this function.
        """
        ...
