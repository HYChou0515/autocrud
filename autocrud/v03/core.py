from collections import defaultdict
from collections.abc import Collection
from contextlib import contextmanager
from contextvars import ContextVar
from enum import StrEnum
import functools
from pathlib import Path
from typing import Literal, TypeVar, Generic
import datetime as dt
from uuid import uuid4, UUID
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
    def archive(self) -> Collection[str]:
        """Trigger the archiving of resources.

        Implements a fast-slow storage architecture for optimal performance:
        - Fast storage: No indexing, optimized for quick writes (slow search, fast write)
        - Slow storage: Indexed storage, optimized for quick searches (fast search, slow write)

        The archive operation migrates metadata from fast storage to slow storage,
        typically selecting the oldest resources by update_time (oldest x% of resources).
        This creates search indexes in slow storage for efficient querying while
        maintaining fast write performance in the primary fast storage.

        Returns:

            - Collection[str]: Resource IDs that were successfully archived.

        ---

        This method enables horizontal scaling by separating write-heavy operations
        (using fast storage) from read-heavy operations (using indexed slow storage).
        The archiving process is typically triggered based on:

        1. Time-based criteria (resources older than threshold)
        2. Storage capacity thresholds
        3. Performance optimization needs

        Post-archive, search operations will query both fast and slow storage
        to provide unified results across all resources.
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


class MsgspecSerializer(Generic[T]):
    def __init__(self, encoding: Literal["json", "msgpack"], resource_type: type[T]):
        if encoding not in ["json", "msgpack"]:
            raise ValueError("Encoding must be either 'json' or 'msgpack'")
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


class IStorage(ABC):
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
    def get_resource_revision(self, resource_id: str, revision_id: str) -> bytes: ...
    @abstractmethod
    def save_resource_revision(
        self, resource_id: str, revision_id: str, b: bytes
    ) -> None: ...
    @abstractmethod
    def search(self, query: ResourceMetaSearchQuery) -> list[ResourceMeta]: ...


class IFastSlowStorage(IStorage):
    @abstractmethod
    def trigger_archive(self) -> Collection[str]: ...


class MemoryStorage(IFastSlowStorage):
    def __init__(self, *, encoding: Literal["json", "msgpack"] = "json"):
        self._slow_meta: dict[str, bytes] = {}
        self._fast_meta: dict[str, bytes] = {}
        self._resource_revisions: dict[str, dict[str, bytes]] = defaultdict(dict)
        self._resmeta_serializer = MsgspecSerializer(
            encoding=encoding, resource_type=ResourceMeta
        )

    def exists(self, resource_id: str) -> bool:
        return resource_id in self._fast_meta or resource_id in self._slow_meta

    def revision_exists(self, resource_id: str, revision_id: str) -> bool:
        return (
            self.exists(resource_id)
            and revision_id in self._resource_revisions[resource_id]
        )

    def get_meta(self, resource_id: str) -> ResourceMeta:
        if resource_id in self._fast_meta:
            meta_b = self._fast_meta[resource_id]
        else:
            meta_b = self._slow_meta[resource_id]
        return self._resmeta_serializer.decode(meta_b)

    def save_meta(self, meta: ResourceMeta) -> None:
        b = self._resmeta_serializer.encode(meta)
        if meta.resource_id in self._slow_meta:
            self._slow_meta[meta.resource_id] = b
        else:
            self._fast_meta[meta.resource_id] = b

    def list_revisions(self, resource_id: str) -> list[str]:
        return list(self._resource_revisions[resource_id].keys())

    def get_resource_revision(self, resource_id: str, revision_id: str) -> bytes:
        return self._resource_revisions[resource_id][revision_id]

    def save_resource_revision(
        self, resource_id: str, revision_id: str, b: bytes
    ) -> None:
        self._resource_revisions[resource_id][revision_id] = b

    def trigger_archive(self) -> Collection[str]:
        to_archived = list(self._fast_meta)
        for r in to_archived:
            self._slow_meta[r] = self._fast_meta.pop(r)
        return to_archived

    def search(self, query: ResourceMetaSearchQuery) -> list[ResourceMeta]:
        rms = self._search_fast(query)
        rms.extend(self._search_slow(query))
        rms.sort(key=self._get_sort_fn([] if query.sorts is UNSET else query.sorts))
        return rms[query.offset : query.offset + query.limit]

    @staticmethod
    def _is_match_query(meta: ResourceMeta, query: ResourceMetaSearchQuery) -> bool:
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

    @staticmethod
    def _get_sort_fn(qsorts: list[ResourceMetaSearchSort]):
        def bool_to_sign(b: bool) -> int:
            return 1 if b else -1

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

    def _search_slow(self, query: ResourceMetaSearchQuery) -> list[ResourceMeta]:
        results: list[ResourceMeta] = []
        for res_id in self._slow_meta.keys():
            meta = self.get_meta(res_id)
            if self._is_match_query(meta, query):
                results.append(meta)
        results.sort(key=self._get_sort_fn([] if query.sorts is UNSET else query.sorts))
        return results[: query.offset + query.limit]

    def _search_fast(self, query: ResourceMetaSearchQuery) -> list[ResourceMeta]:
        results: list[ResourceMeta] = []
        for res_id in self._fast_meta.keys():
            meta = self.get_meta(res_id)
            if self._is_match_query(meta, query):
                results.append(meta)
        results.sort(key=self._get_sort_fn([] if query.sorts is UNSET else query.sorts))
        return results[: query.offset + query.limit]

class MemoryDiskStore(IFastSlowStorage):
    def __init__(self, *, encoding: Literal["json", "msgpack"] = "json", slow_rootdir: Path|str):
        self._slow_rootdir = Path(slow_rootdir)
        self._fast_meta: dict[str, bytes] = {}
        self._resource_revisions: dict[str, dict[str, bytes]] = defaultdict(dict)
        self._resmeta_serializer = MsgspecSerializer(
            encoding=encoding, resource_type=ResourceMeta
        )

    def exists(self, resource_id: str) -> bool:
        return resource_id in self._fast_meta or resource_id in self._slow_meta

    def revision_exists(self, resource_id: str, revision_id: str) -> bool:
        return (
            self.exists(resource_id)
            and revision_id in self._resource_revisions[resource_id]
        )

    def get_meta(self, resource_id: str) -> ResourceMeta:
        if resource_id in self._fast_meta:
            meta_b = self._fast_meta[resource_id]
        else:
            meta_b = self._slow_meta[resource_id]
        return self._resmeta_serializer.decode(meta_b)

    def save_meta(self, meta: ResourceMeta) -> None:
        b = self._resmeta_serializer.encode(meta)
        if meta.resource_id in self._slow_meta:
            self._slow_meta[meta.resource_id] = b
        else:
            self._fast_meta[meta.resource_id] = b

    def list_revisions(self, resource_id: str) -> list[str]:
        return list(self._resource_revisions[resource_id].keys())

    def get_resource_revision(self, resource_id: str, revision_id: str) -> bytes:
        return self._resource_revisions[resource_id][revision_id]

    def save_resource_revision(
        self, resource_id: str, revision_id: str, b: bytes
    ) -> None:
        self._resource_revisions[resource_id][revision_id] = b

    def trigger_archive(self) -> Collection[str]:
        to_archived = list(self._fast_meta)
        for r in to_archived:
            self._slow_meta[r] = self._fast_meta.pop(r)
        return to_archived

    def search(self, query: ResourceMetaSearchQuery) -> list[ResourceMeta]:
        rms = self._search_fast(query)
        rms.extend(self._search_slow(query))
        rms.sort(key=self._get_sort_fn([] if query.sorts is UNSET else query.sorts))
        return rms[query.offset : query.offset + query.limit]

    @staticmethod
    def _is_match_query(meta: ResourceMeta, query: ResourceMetaSearchQuery) -> bool:
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

    @staticmethod
    def _get_sort_fn(qsorts: list[ResourceMetaSearchSort]):
        def bool_to_sign(b: bool) -> int:
            return 1 if b else -1

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

    def _search_slow(self, query: ResourceMetaSearchQuery) -> list[ResourceMeta]:
        results: list[ResourceMeta] = []
        for res_id in self._slow_meta.keys():
            meta = self.get_meta(res_id)
            if self._is_match_query(meta, query):
                results.append(meta)
        results.sort(key=self._get_sort_fn([] if query.sorts is UNSET else query.sorts))
        return results[: query.offset + query.limit]

    def _search_fast(self, query: ResourceMetaSearchQuery) -> list[ResourceMeta]:
        results: list[ResourceMeta] = []
        for res_id in self._fast_meta.keys():
            meta = self.get_meta(res_id)
            if self._is_match_query(meta, query):
                results.append(meta)
        results.sort(key=self._get_sort_fn([] if query.sorts is UNSET else query.sorts))
        return results[: query.offset + query.limit]

    

class _BuildRevMetaCreate(Struct):
    pass


class _BuildRevInfoUpdate(Struct):
    prev_res_meta: ResourceMeta


class _BuildResMetaCreate(Struct):
    rev_info: RevisionInfo


class _BuildResMetaUpdate(Struct):
    prev_res_meta: ResourceMeta
    rev_info: RevisionInfo


class ResourceManager(IResourceManager[T], Generic[T]):
    def __init__(
        self,
        resource_type: type[T],
        *,
        encoding: Literal["json", "msgpack"] = "json",
        storage: IStorage,
    ):
        self.user_ctx = Ctx[str]("user_ctx")
        self.now_ctx = Ctx[dt.datetime]("now_ctx")
        self.resource_type = resource_type
        self.resource_serializer = MsgspecSerializer(
            encoding=encoding, resource_type=Resource[self.resource_type]
        )
        self.storage = storage
        self._support_archive = isinstance(self.storage, IFastSlowStorage)

    @contextmanager
    def meta_provide(self, user: str, now: dt.datetime):
        with (
            self.user_ctx.ctx(user),
            self.now_ctx.ctx(now),
        ):
            yield

    def _res_meta(
        self, mode: _BuildResMetaCreate | _BuildResMetaUpdate
    ) -> ResourceMeta:
        if isinstance(mode, _BuildResMetaCreate):
            current_revision_id = mode.rev_info.revision_id
            resource_id = mode.rev_info.resource_id
            total_revision_count = 1
            created_time = self.now_ctx.get()
            created_by = self.user_ctx.get()
        elif isinstance(mode, _BuildResMetaUpdate):
            current_revision_id = mode.rev_info.revision_id
            resource_id = mode.prev_res_meta.resource_id
            total_revision_count = mode.prev_res_meta.total_revision_count + 1
            created_time = mode.prev_res_meta.created_time
            created_by = mode.prev_res_meta.created_by
        return ResourceMeta(
            current_revision_id=current_revision_id,
            resource_id=resource_id,
            total_revision_count=total_revision_count,
            created_time=created_time,
            updated_time=self.now_ctx.get(),
            created_by=created_by,
            updated_by=self.user_ctx.get(),
        )

    def _rev_info(
        self, mode: _BuildRevMetaCreate | _BuildRevInfoUpdate
    ) -> RevisionInfo:
        uid = uuid4()
        if isinstance(mode, _BuildRevMetaCreate):
            resource_id = str(uid)
            revision_id = f"{resource_id}-1"
            last_revision_id = UNSET
        elif isinstance(mode, _BuildRevInfoUpdate):
            prev_res_meta = mode.prev_res_meta
            resource_id = prev_res_meta.resource_id
            revision_id = f"{resource_id}-{prev_res_meta.total_revision_count + 1}"
            last_revision_id = prev_res_meta.current_revision_id

        info = RevisionInfo(
            uid=uid,
            resource_id=resource_id,
            revision_id=revision_id,
            parent_revision_id=last_revision_id,
            status=RevisionStatus.stable,
            created_time=self.now_ctx.get(),
            updated_time=self.now_ctx.get(),
            created_by=self.user_ctx.get(),
            updated_by=self.user_ctx.get(),
        )
        return info

    def _get_meta_no_check_is_deleted(self, resource_id: str) -> ResourceMeta:
        if not self.storage.exists(resource_id):
            raise ResourceIDNotFoundError(resource_id)
        meta = self.storage.get_meta(resource_id)
        return meta

    def get_meta(self, resource_id: str) -> ResourceMeta:
        meta = self._get_meta_no_check_is_deleted(resource_id)
        if meta.is_deleted:
            raise ResourceIsDeletedError(resource_id)
        return meta

    def search_resources(self, query: ResourceMetaSearchQuery) -> list[ResourceMeta]:
        return self.storage.search(query)

    def create(self, data: T) -> RevisionInfo:
        info = self._rev_info(_BuildRevMetaCreate())
        resource = Resource(
            info=info,
            data=data,
        )
        self.storage.save_resource_revision(
            info.resource_id,
            info.revision_id,
            self.resource_serializer.encode(resource),
        )
        self.storage.save_meta(self._res_meta(_BuildResMetaCreate(info)))
        return info

    def get(self, resource_id: str) -> Resource[T]:
        meta = self.get_meta(resource_id)
        data_b = self.storage.get_resource_revision(
            resource_id, meta.current_revision_id
        )
        return self.resource_serializer.decode(data_b)

    def update(self, resource_id: str, data: T) -> RevisionInfo:
        prev_res_meta = self.get_meta(resource_id)
        rev_info = self._rev_info(_BuildRevInfoUpdate(prev_res_meta))
        res_meta = self._res_meta(_BuildResMetaUpdate(prev_res_meta, rev_info))
        resource = Resource(
            info=rev_info,
            data=data,
        )
        self.storage.save_resource_revision(
            resource_id, rev_info.revision_id, self.resource_serializer.encode(resource)
        )
        self.storage.save_meta(res_meta)
        return rev_info

    def patch(self, resource_id: str, patch_data: JsonPatch) -> RevisionInfo:
        data = self.get(resource_id).data
        d = msgspec.to_builtins(data)
        patch_data.apply(d, in_place=True)
        data = msgspec.convert(d, type=self.resource_type)
        return self.update(resource_id, data)

    def switch(self, resource_id: str, revision_id: str) -> ResourceMeta:
        meta = self.get_meta(resource_id)
        if meta.current_revision_id == revision_id:
            return meta
        if not self.storage.revision_exists(resource_id, revision_id):
            raise RevisionIDNotFoundError(resource_id, revision_id)
        meta.updated_by = self.user_ctx.get()
        meta.updated_time = self.now_ctx.get()
        meta.current_revision_id = revision_id
        self.storage.save_meta(meta)
        return meta

    def delete(self, resource_id: str) -> ResourceMeta:
        meta = self.get_meta(resource_id)
        meta.is_deleted = True
        meta.updated_by = self.user_ctx.get()
        meta.updated_time = self.now_ctx.get()
        self.storage.save_meta(meta)
        return meta

    def restore(self, resource_id: str) -> ResourceMeta:
        meta = self._get_meta_no_check_is_deleted(resource_id)
        if meta.is_deleted:
            meta.is_deleted = False
            meta.updated_by = self.user_ctx.get()
            meta.updated_time = self.now_ctx.get()
            self.storage.save_meta(meta)
        return meta

    def archive(self) -> Collection[str]:
        if self._support_archive:
            self.storage: IFastSlowStorage
            archived = self.storage.trigger_archive()
            return archived
        return []
