from collections.abc import Generator, Iterable, MutableMapping
from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar
from enum import Enum, Flag, StrEnum, auto
import functools
from typing import IO, TypeVar, Generic, Any
import datetime as dt
from uuid import UUID
from msgspec import UNSET, Struct, UnsetType
from abc import ABC, abstractmethod
from jsonpatch import JsonPatch
import msgspec

T = TypeVar("T")


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


class ResourceMetaSortKey(StrEnum):
    created_time = "created_time"
    updated_time = "updated_time"
    resource_id = "resource_id"


class ResourceMetaSortDirection(StrEnum):
    ascending = "+"
    descending = "-"


class ResourceMetaSearchSort(Struct, kw_only=True):
    direction: ResourceMetaSortDirection = ResourceMetaSortDirection.ascending
    key: ResourceMetaSortKey


class ResourceDataSearchSort(Struct, kw_only=True):
    direction: ResourceMetaSortDirection = ResourceMetaSortDirection.ascending
    field_path: str


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


class ResourceConflictError(Exception):
    pass


class SchemaConflictError(ResourceConflictError):
    pass


class ResourceNotFoundError(Exception):
    pass


class ResourceIDNotFoundError(ResourceNotFoundError):
    def __init__(self, resource_id: str):
        super().__init__(f"Resource '{resource_id}' not found.")
        self.resource_id = resource_id


class ResourceIsDeletedError(ResourceNotFoundError):
    def __init__(self, resource_id: str):
        super().__init__(f"Resource '{resource_id}' is deleted.")
        self.resource_id = resource_id


class RevisionNotFoundError(ResourceNotFoundError):
    pass


class RevisionIDNotFoundError(RevisionNotFoundError):
    def __init__(self, resource_id: str, revision_id: str):
        super().__init__(
            f"Revision '{revision_id}' of Resource '{resource_id}' not found."
        )
        self.resource_id = resource_id
        self.revision_id = revision_id


class PermissionDeniedError(Exception):
    pass


class IMigration(ABC):
    @abstractmethod
    def migrate(self, data: IO[bytes], schema_version: str | None) -> T: ...
    @property
    @abstractmethod
    def schema_version(self) -> str: ...


class IResourceManager(ABC, Generic[T]):
    @property
    @abstractmethod
    def user(self) -> str: ...
    @property
    @abstractmethod
    def now(self) -> dt.datetime: ...
    @property
    @abstractmethod
    def user_or_unset(self) -> str | UnsetType: ...
    @property
    @abstractmethod
    def now_or_unset(self) -> dt.datetime | UnsetType: ...
    @property
    @abstractmethod
    def resource_type(self) -> type[T]: ...

    @property
    @abstractmethod
    def resource_name(self) -> str: ...

    @abstractmethod
    def meta_provide(
        self, user: str, now: dt.datetime, *, resource_id: str | UnsetType = UNSET
    ) -> AbstractContextManager: ...

    @abstractmethod
    def create(self, data: T) -> RevisionInfo:
        """Create resource and return the metadata.

        Arguments:

            - data (T): the data to be created.

        Returns:

            - info (RevisionInfo): the metadata of the created data.

        """

    @abstractmethod
    def get(self, resource_id: str) -> Resource[T]:
        """Get the current revision of the resource.

        Arguments:

            - resource_id (str): the id of the resource to get.

        Returns:

            - resource (Resource[T]): the resource with its data and revision info.

        Raises:

            - ResourceIDNotFoundError: if resource id does not exist.
            - ResourceIsDeletedError: if resource is soft-deleted.

        ---

        Returns the current revision of the specified resource. The current revision
        is determined by the `current_revision_id` field in ResourceMeta.

        This method will raise different exceptions based on the resource state:
        - ResourceIDNotFoundError: The resource ID does not exist in storage
        - ResourceIsDeletedError: The resource exists but is marked as deleted (is_deleted=True)

        For soft-deleted resources, use restore() first to make them accessible again.
        """

    @abstractmethod
    def get_resource_revision(self, resource_id: str, revision_id: str) -> Resource[T]:
        """Get a specific revision of the resource.

        Arguments:

            - resource_id (str): the id of the resource.
            - revision_id (str): the id of the specific revision to retrieve.

        Returns:

            - resource (Resource[T]): the resource with its data and revision info for the specified revision.

        Raises:

            - ResourceIDNotFoundError: if resource id does not exist.
            - RevisionIDNotFoundError: if revision id does not exist for this resource.

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

        Arguments:

            - resource_id (str): the id of the resource.

        Returns:

            - list[str]: list of revision IDs for the resource, typically ordered chronologically.

        Raises:

            - ResourceIDNotFoundError: if resource id does not exist.

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

        Arguments:

            - resource_id (str): the id of the resource to get metadata for.

        Returns:

            - meta (ResourceMeta): the metadata of the resource.

        Raises:

            - ResourceIDNotFoundError: if resource id does not exist.
            - ResourceIsDeletedError: if resource is soft-deleted.

        ---

        Returns the metadata of the specified resource, including its current revision,
        total revision count, creation and update timestamps, and user information.
        This method will raise exceptions similar to get() based on the resource state.
        """

    @abstractmethod
    def search_resources(self, query: ResourceMetaSearchQuery) -> list[ResourceMeta]:
        """Search for resources based on a query.

        Arguments:

            - query (ResourceMetaSearchQuery): the search criteria and options.

        Returns:

            - list[ResourceMeta]: list of resource metadata matching the query criteria.

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
    def update(self, resource_id: str, data: T) -> RevisionInfo:
        """Update the data of the resource by creating a new revision.

        Arguments:

            - resource_id (str): the id of the resource to update.
            - data (T): the data to replace the current one.

        Returns:

            - info (RevisionInfo): the metadata of the newly created revision.

        Raises:

            - ResourceIDNotFoundError: if resource id does not exist.
            - ResourceIsDeletedError: if resource is soft-deleted.

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
    def patch(self, resource_id: str, patch_data: JsonPatch) -> RevisionInfo:
        """Apply RFC 6902 JSON Patch operations to the resource.

        Arguments:

            - resource_id (str): the id of the resource to patch.
            - patch_data (JsonPatch): RFC 6902 JSON Patch operations to apply.

        Returns:

            - info (RevisionInfo): the metadata of the newly created revision.

        Raises:

            - ResourceIDNotFoundError: if resource id does not exist.
            - ResourceIsDeletedError: if resource is soft-deleted.

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

        Arguments:

            - resource_id (str): the id of the resource.
            - revision_id (str): the id of the revision to switch to.

        Returns:

            - meta (ResourceMeta): the metadata of the resource after switching.

        Raises:

            - ResourceIDNotFoundError: if resource id does not exist.
            - ResourceIsDeletedError: if resource is soft-deleted.
            - RevisionIDNotFoundError: if revision id does not exist.

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

        Arguments:

            - resource_id (str): the id of the resource to delete.

        Returns:

            - meta (ResourceMeta): the updated metadata with is_deleted=True.

        Raises:

            - ResourceIDNotFoundError: if resource id does not exist.
            - ResourceIsDeletedError: if resource is already soft-deleted.

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

        Arguments:

            - resource_id (str): the id of the resource to restore.

        Returns:

            - meta (ResourceMeta): the updated metadata with is_deleted=False.

        Raises:

            - ResourceIDNotFoundError: if resource id does not exist.

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

            - Generator[tuple[str, IO[bytes]]]: generator yielding (filename, fileobj) pairs for each resource.

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

        Arguments:

            - key (str): the unique identifier for the resource being loaded.
            - bio (IO[bytes]): the tar archive containing the resource data.

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


class IPermissionResourceManager(IResourceManager):
    @abstractmethod
    def check_permission(
        self, user: str, action: ResourceAction, resource: str
    ) -> bool: ...


class Ctx(Generic[T]):
    def __init__(self, name: str, *, strict_type: type[T] | UnsetType = UNSET):
        self.strict_type = strict_type
        self.v = ContextVar[T](name)
        self.tok = None

    @contextmanager
    def ctx(self, value: T):
        if self.strict_type is not UNSET and not isinstance(value, self.strict_type):
            raise TypeError(f"Context value must be of type {self.strict_type}")
        self.tok = self.v.set(value)
        try:
            yield
        finally:
            if self.tok is not None:
                self.v.reset(self.tok)
                self.tok = None

    def get(self) -> T:
        return self.v.get()


class Encoding(StrEnum):
    json = "json"
    msgpack = "msgpack"


def is_match_query(meta: ResourceMeta, query: ResourceMetaSearchQuery) -> bool:
    if query.is_deleted is not UNSET and meta.is_deleted != query.is_deleted:
        return False

    if (
        query.created_time_start is not UNSET
        and meta.created_time < query.created_time_start
    ):
        return False
    if (
        query.created_time_end is not UNSET
        and meta.created_time > query.created_time_end
    ):
        return False
    if (
        query.updated_time_start is not UNSET
        and meta.updated_time < query.updated_time_start
    ):
        return False
    if (
        query.updated_time_end is not UNSET
        and meta.updated_time > query.updated_time_end
    ):
        return False

    if query.created_bys is not UNSET and meta.created_by not in query.created_bys:
        return False
    if query.updated_bys is not UNSET and meta.updated_by not in query.updated_bys:
        return False

    if query.data_conditions is not UNSET and meta.indexed_data is not UNSET:
        for condition in query.data_conditions:
            if not _match_data_condition(meta.indexed_data, condition):
                return False
    elif query.data_conditions is not UNSET:
        # 如果有 data 條件但沒有索引資料，不匹配
        return False

    return True


def _match_data_condition(
    indexed_data: dict[str, Any], condition: DataSearchCondition
) -> bool:
    """檢查索引資料是否匹配 data 條件"""
    field_value = indexed_data.get(condition.field_path)

    if condition.operator == DataSearchOperator.equals:
        return field_value == condition.value
    elif condition.operator == DataSearchOperator.not_equals:
        return field_value != condition.value
    elif condition.operator == DataSearchOperator.greater_than:
        return field_value is not None and field_value > condition.value
    elif condition.operator == DataSearchOperator.greater_than_or_equal:
        return field_value is not None and field_value >= condition.value
    elif condition.operator == DataSearchOperator.less_than:
        return field_value is not None and field_value < condition.value
    elif condition.operator == DataSearchOperator.less_than_or_equal:
        return field_value is not None and field_value <= condition.value
    elif condition.operator == DataSearchOperator.contains:
        # 特殊處理：如果 field_value 是列表，檢查 condition.value 是否在列表中
        if isinstance(field_value, list):
            return condition.value in field_value
        if isinstance(condition.value, Flag) and isinstance(field_value, int):
            return (condition.value.value & field_value) == condition.value.value
        # 標準字符串包含檢查
        return field_value is not None and str(condition.value) in str(field_value)
    elif condition.operator == DataSearchOperator.starts_with:
        return field_value is not None and str(field_value).startswith(
            str(condition.value)
        )
    elif condition.operator == DataSearchOperator.ends_with:
        return field_value is not None and str(field_value).endswith(
            str(condition.value)
        )
    elif condition.operator == DataSearchOperator.in_list:
        return (
            field_value in condition.value
            if isinstance(condition.value, (list, tuple, set))
            else False
        )
    elif condition.operator == DataSearchOperator.not_in_list:
        return (
            field_value not in condition.value
            if isinstance(condition.value, (list, tuple, set))
            else True
        )

    return False


def bool_to_sign(b: bool) -> int:
    return 1 if b else -1


def get_sort_fn(qsorts: list[ResourceMetaSearchSort | ResourceDataSearchSort]):
    def compare(meta1: ResourceMeta, meta2: ResourceMeta) -> int:
        for sort in qsorts:
            if isinstance(sort, ResourceMetaSearchSort):
                if sort.key == ResourceMetaSortKey.created_time:
                    if meta1.created_time != meta2.created_time:
                        return bool_to_sign(meta1.created_time > meta2.created_time) * (
                            1
                            if sort.direction == ResourceMetaSortDirection.ascending
                            else -1
                        )
                elif sort.key == ResourceMetaSortKey.updated_time:
                    if meta1.updated_time != meta2.updated_time:
                        return bool_to_sign(meta1.updated_time > meta2.updated_time) * (
                            1
                            if sort.direction == ResourceMetaSortDirection.ascending
                            else -1
                        )
                elif sort.key == ResourceMetaSortKey.resource_id:
                    if meta1.resource_id != meta2.resource_id:
                        return bool_to_sign(meta1.resource_id > meta2.resource_id) * (
                            1
                            if sort.direction == ResourceMetaSortDirection.ascending
                            else -1
                        )
            else:
                v1 = meta1.indexed_data.get(sort.field_path)
                v2 = meta2.indexed_data.get(sort.field_path)
                if v1 != v2:
                    return bool_to_sign(v1 > v2) * (
                        1
                        if sort.direction == ResourceMetaSortDirection.ascending
                        else -1
                    )
        return 0

    return functools.cmp_to_key(compare)


class MsgspecSerializer(Generic[T]):
    def __init__(self, encoding: Encoding, resource_type: type[T]):
        self.encoding = encoding
        if self.encoding == "msgpack":
            self.encoder = msgspec.msgpack.Encoder(order="deterministic")
            self.decoder = msgspec.msgpack.Decoder(resource_type)
        else:
            self.encoder = msgspec.json.Encoder(order="deterministic")
            self.decoder = msgspec.json.Decoder(resource_type)

    def encode(self, obj: T) -> bytes:
        return self.encoder.encode(obj)

    def decode(self, b: bytes) -> T:
        return self.decoder.decode(b)


class IMetaStore(MutableMapping[str, ResourceMeta]):
    """Interface for a metadata store that manages resource metadata.

    This interface provides a dictionary-like interface for storing and retrieving
    resource metadata, with additional search capabilities. It serves as the primary
    storage mechanism for ResourceMeta objects in the AutoCRUD system.

    The store can be used like a standard Python dictionary, with resource IDs as keys
    and ResourceMeta objects as values. It extends the MutableMapping interface with
    search functionality to support complex queries.

    See: https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping
    """

    @abstractmethod
    def __getitem__(self, pk: str) -> ResourceMeta:
        """Get resource metadata by resource ID.

        Arguments:
            pk (str): The resource ID (primary key) to retrieve metadata for.

        Returns:
            ResourceMeta: The metadata object for the specified resource.

        Raises:
            KeyError: If the resource ID does not exist in the store.
        """

    @abstractmethod
    def __setitem__(self, pk: str, b: ResourceMeta) -> None:
        """Store resource metadata by resource ID.

        Arguments:
            pk (str): The resource ID (primary key) to store metadata under.
            b (ResourceMeta): The metadata object to store.

        ---
        This method stores or updates the metadata for a resource. If the resource ID
        already exists, the metadata will be replaced. The implementation should ensure
        the metadata is persisted according to the store's persistence strategy.
        """

    @abstractmethod
    def __delitem__(self, pk: str) -> None:
        """Delete resource metadata by resource ID.

        Arguments:
            pk (str): The resource ID (primary key) to delete metadata for.

        Raises:
            KeyError: If the resource ID does not exist in the store.

        ---
        This method permanently removes the metadata for a resource from the store.
        Note that this is different from soft deletion - this completely removes
        the metadata record from storage.
        """

    @abstractmethod
    def __iter__(self) -> Generator[str]:
        """Iterate over all resource IDs in the store.

        Returns:
            Generator[str]: A generator yielding all resource IDs in the store.

        ---
        This method allows iteration over all resource IDs currently stored in the
        metadata store. The order of iteration may vary depending on the implementation.
        """

    @abstractmethod
    def __len__(self) -> int:
        """Return the total number of resources in the store.

        Returns:
            int: The count of all resource metadata records in the store.

        ---
        This method provides the total count of all resource metadata records,
        including both active and soft-deleted resources.
        """

    @abstractmethod
    def iter_search(self, query: ResourceMetaSearchQuery) -> Generator[ResourceMeta]:
        """Search for resource metadata based on query criteria.

        Arguments:
            query (ResourceMetaSearchQuery): The search criteria including filters,
                sorting, and pagination options.

        Returns:
            Generator[ResourceMeta]: A generator yielding ResourceMeta objects that
                match the query criteria.

        ---
        This method performs a search across all resource metadata using the provided
        query parameters. The query supports:
        - Filtering by deletion status, timestamps, and user information
        - Data content filtering based on indexed_data fields
        - Sorting by metadata fields or data content fields
        - Pagination with limit and offset

        The results are yielded in the order specified by the sort criteria and
        limited by the pagination parameters.
        """


class IFastMetaStore(IMetaStore):
    """Interface for a fast, temporary metadata store with bulk operations.

    This interface extends IMetaStore with additional capabilities for high-performance
    temporary storage. It's designed for scenarios where metadata needs to be quickly
    stored and then bulk-transferred to a slower, more persistent store.

    Fast meta stores are typically implemented using in-memory storage (like Redis or
    memory-based stores) and provide optimized performance for frequent read/write
    operations at the cost of potential data loss if the store goes down.

    The key feature is the get_then_delete operation which enables efficient bulk
    synchronization with slower storage systems while maintaining data consistency.
    """

    @abstractmethod
    @contextmanager
    def get_then_delete(self) -> Generator[Iterable[ResourceMeta]]:
        """Atomically retrieve all metadata and mark it for deletion.

        Returns:
            Generator[Iterable[ResourceMeta]]: A context manager that yields an
                iterable of all ResourceMeta objects currently in the store.

        ---
        This method provides an atomic operation that:
        1. Retrieves all metadata currently stored in the fast store
        2. Marks that metadata for deletion
        3. Actually deletes it only if the context exits successfully

        If an exception occurs within the context, the metadata will NOT be deleted,
        ensuring data consistency during bulk transfer operations.

        Use Cases:
        - Bulk synchronization from fast storage to slow storage
        - Batch processing of accumulated metadata
        - Atomic transfer operations between storage tiers

        Example:
            ```python
            with fast_store.get_then_delete() as metas:
                slow_store.save_many(metas)
                # Metadata is deleted from fast store only if save_many succeeds
            ```

        The deletion occurs only after the context manager exits successfully,
        providing transactional semantics for bulk operations.
        """


class ISlowMetaStore(IMetaStore):
    """Interface for a persistent, durable metadata store with batch operations.

    This interface extends IMetaStore with capabilities optimized for persistent
    storage systems. Slow meta stores prioritize data durability and consistency
    over raw performance, making them suitable for long-term metadata storage.

    These stores are typically implemented using persistent storage systems like
    databases (PostgreSQL, SQLite) or distributed storage systems, providing
    guarantees about data persistence even in the event of system failures.

    The key feature is the save_many operation which enables efficient bulk
    insertion and update operations, optimizing performance for batch scenarios
    while maintaining the durability guarantees of persistent storage.
    """

    @abstractmethod
    def save_many(self, metas: Iterable[ResourceMeta]) -> None:
        """Bulk save operation for multiple resource metadata objects.

        Arguments:
            metas (Iterable[ResourceMeta]): An iterable of ResourceMeta objects
                to be saved to persistent storage.

        ---
        This method provides an optimized bulk save operation that can efficiently
        handle multiple metadata objects in a single transaction or batch operation.
        It's designed to minimize the overhead of individual save operations when
        dealing with large numbers of metadata objects.

        Behavior:
        - All metadata objects are saved atomically where possible
        - Existing metadata with the same resource_id will be updated
        - New metadata objects will be inserted
        - The operation should be optimized for the underlying storage system

        Use Cases:
        - Bulk synchronization from fast storage to persistent storage
        - Initial data loading and migration operations
        - Batch processing scenarios with multiple metadata updates
        - Periodic bulk backup operations

        Performance Considerations:
        - Implementation should use batch operations where available
        - Transaction boundaries should be optimized for the storage system
        - Error handling should provide partial success information where possible

        The method may raise storage-specific exceptions if the bulk operation fails,
        and implementations should provide appropriate error handling and rollback
        mechanisms where supported by the underlying storage system.
        """


class IResourceStore(ABC, Generic[T]):
    """Interface for storing and retrieving versioned resource data.

    This interface manages the storage of actual resource data and their revision
    information. Unlike metadata stores that handle ResourceMeta objects, resource
    stores manage the complete Resource[T] objects including both data content and
    revision information.

    The store provides version control capabilities by maintaining all revisions
    of each resource, allowing for complete history tracking and point-in-time
    recovery. Each resource can have multiple revisions, and each revision
    contains both the data at that point in time and metadata about the revision.

    Type Parameters:
        T: The type of data stored in resources. This allows the store to be
           type-safe for specific resource data structures.
    """

    @abstractmethod
    def list_resources(self) -> Generator[str]:
        """Iterate over all resource IDs in the store.

        Returns:
            Generator[str]: A generator yielding all unique resource IDs that
                have at least one revision stored in the system.

        ---
        This method provides access to all resource identifiers currently stored
        in the system, regardless of their deletion status or number of revisions.
        Each resource ID represents a unique resource that may have one or more
        revisions stored.

        The iteration order is implementation-dependent and may vary between
        different storage backends. For consistent ordering, use appropriate
        sorting mechanisms in the calling code.
        """

    @abstractmethod
    def list_revisions(self, resource_id: str) -> Generator[str]:
        """Iterate over all revision IDs for a specific resource.

        Arguments:
            resource_id (str): The unique identifier of the resource to list
                revisions for.

        Returns:
            Generator[str]: A generator yielding all revision IDs for the
                specified resource.

        Raises:
            ResourceIDNotFoundError: If the resource ID does not exist in the store.

        ---
        This method provides access to all revision identifiers for a specific
        resource, enabling complete history traversal and revision management.
        The revisions represent the complete change history of the resource.

        The iteration order is typically chronological (oldest to newest) but
        may vary depending on the implementation. For guaranteed ordering,
        consider using revision timestamps or sequence numbers.
        """

    @abstractmethod
    def exists(self, resource_id: str, revision_id: str) -> bool:
        """Check if a specific revision exists for a given resource.

        Arguments:
            resource_id (str): The unique identifier of the resource.
            revision_id (str): The unique identifier of the revision to check.

        Returns:
            bool: True if the specified revision exists, False otherwise.

        ---
        This method provides a fast existence check without retrieving the actual
        data. It's useful for validation and conditional logic before attempting
        to retrieve or operate on specific revisions.

        The method returns False if either the resource doesn't exist or the
        specific revision doesn't exist for that resource.
        """

    @abstractmethod
    def get(self, resource_id: str, revision_id: str) -> Resource[T]:
        """Retrieve a specific revision of a resource.

        Arguments:
            resource_id (str): The unique identifier of the resource.
            revision_id (str): The unique identifier of the revision to retrieve.

        Returns:
            Resource[T]: The complete resource object including both data and
                revision information for the specified revision.

        Raises:
            ResourceIDNotFoundError: If the resource ID does not exist.
            RevisionIDNotFoundError: If the revision ID does not exist for the resource.

        ---
        This method retrieves the complete resource data and metadata for a specific
        revision. The returned Resource object contains both the data as it existed
        at that revision and the RevisionInfo with metadata about that revision.

        This is the primary method for accessing historical data and enables
        point-in-time recovery and data comparison between revisions.
        """

    @abstractmethod
    def get_revision_info(self, resource_id: str, revision_id: str) -> RevisionInfo:
        """Retrieve revision metadata without the resource data.

        Arguments:
            resource_id (str): The unique identifier of the resource.
            revision_id (str): The unique identifier of the revision.

        Returns:
            RevisionInfo: The revision metadata including timestamps, user info,
                parent revision references, and other revision-specific information.

        Raises:
            ResourceIDNotFoundError: If the resource ID does not exist.
            RevisionIDNotFoundError: If the revision ID does not exist for the resource.

        ---
        This method provides access to revision metadata without loading the
        potentially large resource data. It's useful for revision browsing,
        audit trails, and operations that only need revision metadata.

        The RevisionInfo includes information such as:
        - Creation and update timestamps
        - User information (who created/updated)
        - Parent revision relationships
        - Revision status and schema version
        - Data integrity hashes
        """

    @abstractmethod
    def save(self, data: Resource[T]) -> None:
        """Store a complete resource revision.

        Arguments:
            data (Resource[T]): The complete resource object including both
                data content and revision information to be stored.

        ---
        This method stores a complete resource revision, including both the data
        content and all associated revision metadata. If a revision with the same
        resource_id and revision_id already exists, it will be replaced.

        The save operation should be atomic where possible, ensuring that both
        the data and revision information are stored consistently. The method
        should handle serialization of the data content according to the store's
        encoding strategy.

        Error handling should ensure that partial writes don't leave the store
        in an inconsistent state, and appropriate exceptions should be raised
        for storage failures or constraint violations.
        """

    @abstractmethod
    def encode(self, data: T) -> bytes:
        """Encode resource data into bytes for storage.

        Arguments:
            data (T): The resource data object to encode.

        Returns:
            bytes: The encoded representation of the data suitable for storage.

        ---
        This method handles the serialization of resource data into a byte format
        suitable for storage in the underlying storage system. The encoding method
        should be consistent and reversible, allowing the data to be accurately
        reconstructed when retrieved.

        The encoding strategy may vary depending on the store implementation:
        - JSON encoding for text-based storage
        - MessagePack for binary efficiency
        - Custom encoding for specialized data types

        The method should handle type-specific serialization requirements and
        maintain data integrity during the encoding process.
        """


class IStorage(ABC, Generic[T]):
    """Interface for unified storage management combining metadata and resource data.

    This interface provides a high-level abstraction that combines both metadata
    storage (IMetaStore) and resource data storage (IResourceStore) into a single
    unified interface. It serves as the primary storage abstraction for the
    ResourceManager and handles the coordination between metadata and data storage.

    The storage interface manages the complete lifecycle of resources including:
    - Resource and revision existence checking
    - Metadata and data storage coordination
    - Search and query operations across metadata
    - Bulk data export and import operations
    - Data encoding and serialization

    Type Parameters:
        T: The type of data stored in resources. This ensures type safety
           for resource data operations throughout the storage layer.

    This interface is typically implemented by storage systems that coordinate
    between separate metadata and resource stores, providing a unified view
    while optimizing for different access patterns and performance requirements.
    """

    @abstractmethod
    def exists(self, resource_id: str) -> bool:
        """Check if a resource exists in the storage system.

        Arguments:
            resource_id (str): The unique identifier of the resource to check.

        Returns:
            bool: True if the resource exists (has metadata), False otherwise.

        ---
        This method checks for resource existence at the metadata level. A resource
        is considered to exist if it has associated metadata, regardless of its
        deletion status or the number of revisions it has.

        This is a lightweight operation that only checks metadata presence and
        does not verify the existence of specific revisions or data integrity.
        """

    @abstractmethod
    def revision_exists(self, resource_id: str, revision_id: str) -> bool:
        """Check if a specific revision exists for a given resource.

        Arguments:
            resource_id (str): The unique identifier of the resource.
            revision_id (str): The unique identifier of the revision to check.

        Returns:
            bool: True if the specified revision exists, False otherwise.

        ---
        This method verifies the existence of a specific revision within the
        resource's history. It checks both that the resource exists and that
        the particular revision is available in the storage system.

        This operation may involve checking both metadata consistency and
        data availability depending on the storage implementation.
        """

    @abstractmethod
    def get_meta(self, resource_id: str) -> ResourceMeta:
        """Retrieve metadata for a specific resource.

        Arguments:
            resource_id (str): The unique identifier of the resource.

        Returns:
            ResourceMeta: The complete metadata object for the resource.

        Raises:
            ResourceIDNotFoundError: If the resource does not exist.

        ---
        This method retrieves the complete metadata for a resource, including
        current revision information, timestamps, user data, deletion status,
        and indexed data for search operations.

        The metadata provides essential information about the resource without
        requiring access to the potentially large resource data content.
        """

    @abstractmethod
    def save_meta(self, meta: ResourceMeta) -> None:
        """Store or update metadata for a resource.

        Arguments:
            meta (ResourceMeta): The metadata object to store.

        ---
        This method stores or updates the metadata for a resource. If metadata
        for the resource already exists, it will be replaced. The operation
        should be atomic and ensure consistency between the metadata and any
        associated indexes.

        The method handles persistence of all metadata fields including indexed
        data that may be used for search operations.
        """

    @abstractmethod
    def list_revisions(self, resource_id: str) -> list[str]:
        """List all revision IDs for a specific resource.

        Arguments:
            resource_id (str): The unique identifier of the resource.

        Returns:
            list[str]: A list of all revision IDs for the resource, typically
                ordered chronologically from oldest to newest.

        Raises:
            ResourceIDNotFoundError: If the resource does not exist.

        ---
        This method provides a complete list of all revisions available for a
        resource, enabling full history traversal and revision management
        operations. The ordering facilitates understanding the evolution of
        the resource over time.
        """

    @abstractmethod
    def get_resource_revision(self, resource_id: str, revision_id: str) -> Resource[T]:
        """Retrieve a specific revision of a resource with complete data.

        Arguments:
            resource_id (str): The unique identifier of the resource.
            revision_id (str): The unique identifier of the revision.

        Returns:
            Resource[T]: The complete resource object including both data
                and revision information.

        Raises:
            ResourceIDNotFoundError: If the resource does not exist.
            RevisionIDNotFoundError: If the revision does not exist.

        ---
        This method retrieves the complete resource data and metadata for a
        specific revision, providing access to the resource as it existed at
        that point in time. This enables point-in-time recovery and historical
        data analysis.
        """

    @abstractmethod
    def get_resource_revision_info(
        self, resource_id: str, revision_id: str
    ) -> RevisionInfo:
        """Retrieve revision information without the resource data.

        Arguments:
            resource_id (str): The unique identifier of the resource.
            revision_id (str): The unique identifier of the revision.

        Returns:
            RevisionInfo: The revision metadata including creation info,
                parent relationships, and status information.

        Raises:
            ResourceIDNotFoundError: If the resource does not exist.
            RevisionIDNotFoundError: If the revision does not exist.

        ---
        This method provides access to revision metadata without loading the
        potentially large resource data. It's optimized for operations that
        only need revision information such as audit trails, version browsing,
        and revision relationship analysis.
        """

    @abstractmethod
    def save_resource_revision(self, resource: Resource[T]) -> None:
        """Store a complete resource revision including data and metadata.

        Arguments:
            resource (Resource[T]): The complete resource object to store.

        ---
        This method stores a complete resource revision, coordinating the storage
        of both the resource data and its revision information. The operation
        should ensure consistency between the data and metadata components.

        The method handles serialization of the resource data and proper indexing
        for search operations while maintaining referential integrity between
        revisions and their parent relationships.
        """

    @abstractmethod
    def search(self, query: ResourceMetaSearchQuery) -> list[ResourceMeta]:
        """Search for resources based on metadata and data criteria.

        Arguments:
            query (ResourceMetaSearchQuery): The search criteria including
                filters, sorting, and pagination parameters.

        Returns:
            list[ResourceMeta]: A list of metadata objects for resources
                that match the search criteria.

        ---
        This method provides comprehensive search capabilities across both
        metadata fields and indexed resource data. It supports complex
        filtering, sorting, and pagination to enable efficient resource
        discovery and management operations.

        The search operates on the metadata level but can filter based on
        indexed data content, providing powerful query capabilities without
        requiring full data loading for each resource.
        """

    @abstractmethod
    def encode_data(self, data: T) -> bytes:
        """Encode resource data for storage.

        Arguments:
            data (T): The resource data to encode.

        Returns:
            bytes: The encoded data suitable for storage.

        ---
        This method handles the serialization of resource data into a format
        suitable for storage. It coordinates with the underlying storage
        systems to ensure consistent encoding strategies and data integrity.

        The encoding method should be reversible and maintain data fidelity
        across storage and retrieval operations.
        """

    @abstractmethod
    def dump_meta(self) -> Generator[ResourceMeta]:
        """Export all resource metadata for backup or migration.

        Returns:
            Generator[ResourceMeta]: A generator yielding all metadata
                objects in the storage system.

        ---
        This method provides a way to export all resource metadata for backup,
        migration, or analysis purposes. It iterates through all resources
        regardless of their deletion status, providing complete metadata
        coverage.

        The generator approach allows for memory-efficient processing of large
        datasets without loading all metadata into memory simultaneously.
        """

    @abstractmethod
    def dump_resource(self) -> Generator[Resource[T]]:
        """Export all resource data including complete revision information.

        Returns:
            Generator[Resource[T]]: A generator yielding all resource objects
                with their complete data and revision information.

        ---
        This method provides comprehensive data export capabilities, including
        both resource data and revision metadata. It's designed for complete
        system backups and data migration scenarios where full data fidelity
        is required.

        The export includes all revisions of all resources, providing complete
        historical data preservation. The generator approach enables processing
        of large datasets efficiently.
        """


# Data Search Related Classes


class SpecialIndex(Enum):
    msgspec_tag = "msgspec_tag"


class IndexableField(Struct, kw_only=True):
    """Defines a field that should be indexed for searching."""

    field_path: str  # JSON path to the field, e.g., "name", "user.email"
    field_type: (
        type | SpecialIndex
    )  # The type of the field (str, int, float, bool, datetime)


class UnifiedSortKey(StrEnum):
    # Meta 欄位
    created_time = "created_time"
    updated_time = "updated_time"
    resource_id = "resource_id"

    # Data 欄位（用前綴區分）
    data_prefix = "data."  # 實際使用時會是 "data.name", "data.user.email" 等


class UnifiedSearchSort(Struct, kw_only=True):
    direction: ResourceMetaSortDirection = ResourceMetaSortDirection.ascending
    key: str  # 可以是 meta 欄位名或 "data.field_path"


class IndexEntry(Struct, kw_only=True):
    resource_id: str
    revision_id: str
    field_path: str
    field_value: Any
    field_type: str  # Store type name as string
