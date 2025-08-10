from collections.abc import Generator, Iterable, MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar
from enum import StrEnum
import functools
from typing import TypeVar, Generic
import datetime as dt
from uuid import UUID
from msgspec import UNSET, Struct, UnsetType
from abc import ABC, abstractmethod
from jsonpatch import JsonPatch
import msgspec

T = TypeVar("T")


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


class ResourceMetaSearchQuery(Struct, kw_only=True):
    is_deleted: bool | UnsetType = UNSET

    created_time_start: dt.datetime | UnsetType = UNSET
    created_time_end: dt.datetime | UnsetType = UNSET
    updated_time_start: dt.datetime | UnsetType = UNSET
    updated_time_end: dt.datetime | UnsetType = UNSET

    created_bys: list[str] | UnsetType = UNSET
    updated_bys: list[str] | UnsetType = UNSET

    limit: int = 10
    offset: int = 0

    sorts: list[ResourceMetaSearchSort] | UnsetType = UNSET


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


class IResourceManager(ABC, Generic[T]):
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


class Ctx(Generic[T]):
    def __init__(self, name: str):
        self.v = ContextVar[T](name)
        self.tok = None

    @contextmanager
    def ctx(self, value: T):
        self.tok = self.v.set(value)
        try:
            yield
        finally:
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
    return True


def bool_to_sign(b: bool) -> int:
    return 1 if b else -1


def get_sort_fn(qsorts: list[ResourceMetaSearchSort]):
    def compare(meta1: ResourceMeta, meta2: ResourceMeta) -> int:
        for sort in qsorts:
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
        return 0

    return functools.cmp_to_key(compare)


class MsgspecSerializer(Generic[T]):
    def __init__(self, encoding: Encoding, resource_type: type[T]):
        self.encoding = encoding
        if self.encoding == "msgpack":
            self.encoder = msgspec.msgpack.Encoder()
            self.decoder = msgspec.msgpack.Decoder(resource_type)
        else:
            self.encoder = msgspec.json.Encoder()
            self.decoder = msgspec.json.Decoder(resource_type)

    def encode(self, obj: T) -> bytes:
        return self.encoder.encode(obj)

    def decode(self, b: bytes) -> T:
        return self.decoder.decode(b)


class IMetaStore(MutableMapping[str, ResourceMeta]):
    @abstractmethod
    def iter_search(
        self, query: ResourceMetaSearchQuery
    ) -> Generator[ResourceMeta]: ...


class IFastMetaStore(IMetaStore):
    @abstractmethod
    @contextmanager
    def get_then_delete(self) -> Generator[Iterable[ResourceMeta]]: ...


class ISlowMetaStore(IMetaStore):
    @abstractmethod
    def save_many(self, metas: Iterable[ResourceMeta]) -> None: ...


class IResourceStore(ABC, Generic[T]):
    @abstractmethod
    def list_resources(self) -> Generator[str]: ...
    @abstractmethod
    def list_revisions(self, resource_id: str) -> Generator[str]: ...
    @abstractmethod
    def exists(self, resource_id: str, revision_id: str) -> bool: ...
    @abstractmethod
    def get(self, resource_id: str, revision_id: str) -> Resource[T]: ...
    @abstractmethod
    def save(self, data: Resource[T]) -> None: ...


class IStorage(ABC, Generic[T]):
    @abstractmethod
    def exists(self, resource_id: str) -> bool: ...
    @abstractmethod
    def revision_exists(self, resource_id: str, revision_id: str) -> bool: ...
    @abstractmethod
    def get_meta(self, resource_id: str) -> ResourceMeta: ...
    @abstractmethod
    def save_meta(self, meta: ResourceMeta) -> None: ...
    @abstractmethod
    def list_revisions(self, resource_id: str) -> list[str]: ...
    @abstractmethod
    def get_resource_revision(
        self, resource_id: str, revision_id: str
    ) -> Resource[T]: ...
    @abstractmethod
    def save_resource_revision(self, resource: Resource[T]) -> None: ...
    @abstractmethod
    def search(self, query: ResourceMetaSearchQuery) -> list[ResourceMeta]: ...
