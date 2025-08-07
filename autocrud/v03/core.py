from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from enum import StrEnum
from typing import Any, Literal, TypeVar, Generic
import datetime as dt
from uuid import uuid4, UUID
from msgspec import Struct
from abc import ABC, abstractmethod
from jsonpatch import JsonPatch
import msgspec

T = TypeVar("T")


class ResourceMeta(Struct, kw_only=True):
    current_revision_id: str
    resource_id: str
    schema_version: str

    total_revision_count: int

    created_time: dt.datetime
    updated_time: dt.datetime
    created_by: str
    updated_by: str

    is_deleted: bool = False


class RevisionStatus(StrEnum):
    draft = "draft"
    stable = "stable"


class RevisionInfo(Struct, kw_only=True):
    uid: UUID
    resource_id: str
    revision_id: str
    parent_revision_id: str
    schema_version: str
    data_hash: str

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
    pass


class RevisionNotFoundError(ResourceNotFoundError):
    pass


class RevisionIDNotFoundError(RevisionNotFoundError):
    pass


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
    def get(self, resource_id: str) -> T:
        """Get the latest revision of the resource_id.

        Arguments:

            - resource_id (str): the id of the resource want to get.

        Returns:

            - resource (Resource[T]): the resource got for the id.

        Raises:

            - ResourceIDNotFoundError: if resource id not exists.
            - ResourceIDNotFoundError: if resource id has no revision.
            - SchemaConflictError: if resource schema version doesn't match the latest version.

        ---

        If resource id not found, raises ResourceIDNotFoundError.
        If no revisions found, raises RevisionNotFoundError.

        If schema version doesn't match:
        - if self.auto_migrate is True, migrate to latest schema version
        - otherwise, raises SchemaConflictError
        """

    @abstractmethod
    def update(self, resource_id: str, data: T) -> RevisionInfo:
        """Update the data of the resource.

        Arguments:

            - resource_id (str): the id of the resource want to update.
            - data (T): the data want to replace the current one.

        Returns:

            info (RevisionInfo): the metadata of the updated data

        Raises:

            - ResourceIDNotFoundError: if resource id not exists.
            - SchemaConflictError: if resource schema version doesn't match the latest version.

        It will directly replace the data. If need partial update, use patch.
        """

    @abstractmethod
    def patch(self, resource_id: str, patch_data: JsonPatch) -> RevisionInfo:
        """Patch update data of the resource.

        Arguments:

            - resource_id (str): the id of the resource want to update.
            - patch_data (JsonPatch): patch data with format JsonPatch.

        Returns:

            info (RevisionInfo): the metadata of the updated data

        Raises:

            - ResourceIDNotFoundError: if resource id not exists.
            - SchemaConflictError: if resource schema version doesn't match the latest version.

        Use RCF6902 to update the resource data.
        """

    @abstractmethod
    def switch(self, resource_id: str, revision_id: str) -> ResourceMeta:
        """Switch the current revision to a specific revision.

        Arguments:

            - resource_id (str): the id of the resource.
            - revision_id (str): the id of the revision to switch to.

        Returns:

            meta (ResourceMeta): the metadata of the resource after switching.

        Raises:

            - ResourceIDNotFoundError: if resource id not exists.
            - RevisionIDNotFoundError: if revision id not exists.

        Switch the current revision pointer to the specified revision.
        This allows you to make any historical revision the current one without
        deleting any revisions. All historical revisions remain accessible.

        The operation only updates the current_revision_id in ResourceMeta,
        and records the switch time and user in updated_time and updated_by fields.
        """

    @abstractmethod
    def delete(self, resource_id: str) -> ResourceMeta:
        """Mark the resource as deleted (soft delete).

        Arguments:

            - resource_id (str): the id of the resource to delete.

        Raises:

            - ResourceIDNotFoundError: if resource id does not exist.

        ---

        This operation performs a soft delete by setting the `is_deleted` flag to True
        in the ResourceMeta. The resource and all its revisions remain in storage
        and can be recovered later.

        Behavior:
        - Sets `is_deleted = True` in ResourceMeta
        - Updates `updated_time` and `updated_by` to record the deletion
        - All revision data and metadata are preserved
        - Resource can be restored by setting `is_deleted = False`

        This is a reversible operation that maintains data integrity while
        marking the resource as logically deleted.
        """

    @abstractmethod
    def restore(self, resource_id: str) -> ResourceMeta:
        """Restore a previously deleted resource (undo soft delete).

        Arguments:

            - resource_id (str): the id of the resource to restore.

        Raises:

            - ResourceIDNotFoundError: if resource id does not exist.

        ---

        This operation restores a previously soft-deleted resource by setting
        the `is_deleted` flag back to False in the ResourceMeta. This undoes
        the soft delete operation.

        Behavior:
        - Sets `is_deleted = False` in ResourceMeta
        - Updates `updated_time` and `updated_by` to record the restoration
        - All revision data and metadata remain unchanged
        - Resource becomes accessible again through normal operations

        This operation can be performed on any resource that was previously
        soft-deleted using the delete() method. If the resource is not
        currently marked as deleted, the operation will still update the
        metadata timestamps.

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


class IStorage:
    @abstractmethod
    def list_revisions(self, resource_id: str): ...


class MemoryStorage(IStorage):
    def __init__(self):
        self.meta: dict[str, bytes] = {}
        self.resource_revisions: dict[str, dict[str, bytes]] = defaultdict(dict)

    def exists(self, resource_id: str) -> bool:
        return resource_id in self.meta

    def revision_exists(self, resource_id: str, revision_id: str) -> bool:
        return (
            self.exists(resource_id)
            and revision_id in self.resource_revisions[resource_id]
        )

    def get_meta(self, resource_id: str) -> bytes:
        return self.meta[resource_id]

    def save_meta(self, resource_id: str, b: bytes) -> None:
        self.meta[resource_id] = b

    def list_revisions(self, resource_id: str) -> list[str]:
        return list(self.resource_revisions[resource_id].keys())

    def get_resource_revision(self, resource_id: str, revision_id: str) -> bytes:
        return self.resource_revisions[resource_id][revision_id]

    def save_resource_revision(
        self, resource_id: str, revision_id: str, b: bytes
    ) -> None:
        self.resource_revisions[resource_id][revision_id] = b


class _BuildRevMetaCreate(Struct):
    pass


class _BuildRevInfoUpdate(Struct):
    prev_res_meta: ResourceMeta


class _BuildResMetaCreate(Struct):
    rev_info: RevisionInfo


class _BuildResMetaUpdate(Struct):
    prev_res_meta: ResourceMeta
    rev_info: RevisionInfo


class MsgspecSerializer:
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

    def encode(self, obj: Any) -> bytes:
        return self.encoder.encode(obj)

    def decode(self, b: bytes) -> T:
        return self.decoder.decode(b)


class ResourceManager(IResourceManager[T], Generic[T]):
    def __init__(
        self, resource_type: type[T], *, encoding: Literal["json", "msgpack"] = "json"
    ):
        self.user_ctx = Ctx[str]("user_ctx")
        self.now_ctx = Ctx[dt.datetime]("now_ctx")
        self.resource_type = resource_type
        self.storage = MemoryStorage()
        self.reource_serializer = MsgspecSerializer(
            encoding=encoding, resource_type=Resource[self.resource_type]
        )
        self.resmeta_serializer = MsgspecSerializer(
            encoding=encoding, resource_type=ResourceMeta
        )
        self.revinfo_serializer = MsgspecSerializer(
            encoding=encoding, resource_type=RevisionInfo
        )

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
            schema_version="",
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
            last_revision_id = ""
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
            schema_version="",
            data_hash="",
            status=RevisionStatus.stable,
            created_time=self.now_ctx.get(),
            updated_time=self.now_ctx.get(),
            created_by=self.user_ctx.get(),
            updated_by=self.user_ctx.get(),
        )
        return info

    def get_meta(self, resource_id: str) -> ResourceMeta:
        if not self.storage.exists(resource_id):
            raise ResourceIDNotFoundError(f"Resource '{resource_id}' not found.")
        meta_b = self.storage.get_meta(resource_id)
        meta = self.resmeta_serializer.decode(meta_b)
        return meta

    def create(self, data: T) -> RevisionInfo:
        info = self._rev_info(_BuildRevMetaCreate())
        resource = Resource(
            info=info,
            data=data,
        )
        self.storage.save_resource_revision(
            info.resource_id, info.revision_id, self.reource_serializer.encode(resource)
        )
        self.storage.save_meta(
            info.resource_id,
            self.resmeta_serializer.encode(self._res_meta(_BuildResMetaCreate(info))),
        )
        return info

    def _get_meta_and_check_not_deleted(self, resource_id: str) -> ResourceMeta:
        meta = self.get_meta(resource_id)
        if meta.is_deleted:
            raise ResourceIDNotFoundError(f"Resource '{resource_id}' is deleted.")
        return meta

    def get(self, resource_id: str) -> Resource[T]:
        meta = self._get_meta_and_check_not_deleted(resource_id)
        data_b = self.storage.get_resource_revision(
            resource_id, meta.current_revision_id
        )
        return self.reource_serializer.decode(data_b)

    def update(self, resource_id: str, data: T) -> RevisionInfo:
        prev_res_meta = self._get_meta_and_check_not_deleted(resource_id)
        rev_info = self._rev_info(_BuildRevInfoUpdate(prev_res_meta))
        res_meta = self._res_meta(_BuildResMetaUpdate(prev_res_meta, rev_info))
        resource = Resource(
            info=rev_info,
            data=data,
        )
        self.storage.save_resource_revision(
            resource_id, rev_info.revision_id, self.reource_serializer.encode(resource)
        )
        self.storage.save_meta(resource_id, self.resmeta_serializer.encode(res_meta))
        return rev_info

    def patch(self, resource_id: str, patch_data: JsonPatch) -> RevisionInfo:
        data = self.get(resource_id).data
        d = msgspec.to_builtins(data)
        patch_data.apply(d, in_place=True)
        data = msgspec.convert(d, type=self.resource_type)
        return self.update(resource_id, data)

    def switch(self, resource_id: str, revision_id: str) -> ResourceMeta:
        meta = self._get_meta_and_check_not_deleted(resource_id)
        if meta.current_revision_id == revision_id:
            return meta
        if not self.storage.revision_exists(resource_id, revision_id):
            raise ResourceIDNotFoundError(
                f"Revision '{resource_id}'/'{revision_id}' not found."
            )
        meta.updated_by = self.user_ctx.get()
        meta.updated_time = self.now_ctx.get()
        meta.current_revision_id = revision_id
        self.storage.save_meta(resource_id, self.resmeta_serializer.encode(meta))
        return meta

    def delete(self, resource_id: str) -> ResourceMeta:
        meta = self._get_meta_and_check_not_deleted(resource_id)
        meta.is_deleted = True
        meta.updated_by = self.user_ctx.get()
        meta.updated_time = self.now_ctx.get()
        self.storage.save_meta(resource_id, self.resmeta_serializer.encode(meta))
        return meta

    def restore(self, resource_id) -> ResourceMeta:
        meta = self.get_meta(resource_id)
        if meta.is_deleted:
            meta.is_deleted = False
            meta.updated_by = self.user_ctx.get()
            meta.updated_time = self.now_ctx.get()
            self.storage.save_meta(
                resource_id,
                self.resmeta_serializer.encode(meta),
            )
        return meta
