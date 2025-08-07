from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from enum import StrEnum
from typing import Any, Literal, TypeVar, TypedDict, Generic
import datetime as dt
from uuid import uuid4, UUID
from msgspec import Struct
from abc import ABC, abstractmethod
import msgspec

T = TypeVar('T')

class ResourceMeta(Struct, kw_only=True):
    current_revision_id: str
    resource_id: str
    schema_version: str

    total_revision_count: int
    valid_revision_count: int

    created_time: dt.datetime
    updated_time: dt.datetime
    created_by: str
    updated_by: str

class RevisionStatus(StrEnum):
    draft = "draft"
    stable = "stable"
    deleted = "deleted"

class RevisionMeta(Struct, kw_only=True):
    uid: UUID
    resource_id: str
    revision_id: str
    last_revision_id: str
    schema_version: str
    data_hash: str

    status: RevisionStatus

    created_time: dt.datetime
    updated_time: dt.datetime
    created_by: str
    updated_by: str

class Resource(Struct, Generic[T]):
    meta: RevisionMeta
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


RCF9802 = list[dict[str, Any]]

class IResourceManager(ABC, Generic[T]):
    @abstractmethod
    def create(self, data: T) -> RevisionMeta:
        """Create resource and return the metadata.
        
        Arguments:

            - data (T): the data to be created.

        Returns:

            - meta (RevisionMeta): the metadata of the created data.
        
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
    def update(self, resource_id: str, data: T) -> RevisionMeta:
        """Update the data of the resource.

        Arguments:

            - resource_id (str): the id of the resource want to update.
            - data (T): the data want to replace the current one.

        Returns:

            meta (RevisionMeta): the metadata of the updated data

        Raises:

            - ResourceIDNotFoundError: if resource id not exists.
            - SchemaConflictError: if resource schema version doesn't match the latest version.

        It will directly replace the data. If need partial update, use patch.
        """

    @abstractmethod
    def patch(self, resource_id: str, patch_data: RCF9802) -> RevisionMeta:
        """Patch update data of the resource.

        Arguments:

            - resource_id (str): the id of the resource want to update.
            - patch_data (RCF9802): patch data with format RCF9802.

        Returns:

            meta (RevisionMeta): the metadata of the updated data

        Raises:

            - ResourceIDNotFoundError: if resource id not exists.
            - SchemaConflictError: if resource schema version doesn't match the latest version.

        Use RCF9802 to update the resource data.
        """

    @abstractmethod
    def yank(self, resource_id: str, revision_id: str) -> RevisionMeta:
        """Delete a revision of a resource.

        Arguments:

            - resource_id (str): the id of the resource want to update.
            - revision_id (str): the id of the revision.

        Returns:

            meta (RevisionMeta): the metadata of the updated data

        Raises:

            - ResourceIDNotFoundError: if resource id not exists.
            - RevisionIDNotFoundError: if revision id not exists.

        Yank a revision of a resource. The next latest revision will be used as the current revision.
        If no revision left, this action is identical to `delete(resource_id)`.
        """

    @abstractmethod
    def delete(self, resource_id: str) -> None:
        """Delete the resource.

        Arguments:

            - resource_id (str): the id of the resource want to update.

        Raises:

            - ResourceIDNotFoundError: if resource id not exists.

        Delete a resource with the resource ID. It will delete all revision of the resource.
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
    
    def get_meta(self, resource_id: str) -> bytes:
        return self.meta[resource_id]
    
    def save_meta(self, resource_id: str, b: bytes) -> None:
        self.meta[resource_id] = b

    def list_revisions(self, resource_id: str) -> list[str]:
        return list(self.resource_revisions[resource_id].keys())
    
    def get_resource_revision(self, resource_id: str, revision_id: str) -> bytes:
        return self.resource_revisions[resource_id][revision_id]
    
    def save_resource_revision(self, resource_id: str, revision_id: str, b: bytes) -> None:
        self.resource_revisions[resource_id][revision_id] = b

class _BuildRevMetaCreate(Struct):
    pass
class _BuildRevMetaUpdate(Struct):
    prev_res_meta: ResourceMeta
    
class _BuildResMetaCreate(Struct):
    rev_meta: RevisionMeta

class _BuildResMetaUpdate(Struct):
    prev_res_meta: ResourceMeta
    rev_meta: RevisionMeta
    

class ResourceManager(Generic[T]):
    def __init__(self, resource_type: type[T]):
        self.user_ctx = Ctx[str]("user_ctx")
        self.now_ctx = Ctx[dt.datetime]("now_ctx")
        self.resource_type = resource_type
        self.storage = MemoryStorage()

    @contextmanager
    def meta_provide(self, user: str, now: dt.datetime):
        
        with (
            self.user_ctx.ctx(user),
            self.now_ctx.ctx(now),
        ):
            yield
            
    def _res_meta(self, mode: _BuildResMetaCreate|_BuildResMetaUpdate) -> ResourceMeta:
        if isinstance(mode, _BuildResMetaCreate):
            current_revision_id=mode.rev_meta.revision_id
            resource_id=mode.rev_meta.resource_id
            total_revision_count=1
            valid_revision_count=1
            created_time=self.now_ctx.get()
            created_by=self.user_ctx.get()
        elif isinstance(mode, _BuildResMetaUpdate):
            current_revision_id = mode.rev_meta.revision_id
            resource_id = mode.prev_res_meta.resource_id
            total_revision_count=mode.prev_res_meta.total_revision_count+1
            valid_revision_count=mode.prev_res_meta.valid_revision_count+1
            created_time=mode.prev_res_meta.created_time
            created_by=mode.prev_res_meta.created_by
        return ResourceMeta(
            current_revision_id=current_revision_id,
            resource_id=resource_id,
            total_revision_count=total_revision_count,
            valid_revision_count=valid_revision_count,
            schema_version="",
            created_time=created_time,
            updated_time=self.now_ctx.get(),
            created_by=created_by,
            updated_by=self.user_ctx.get(),
        )
            
    def _rev_meta(self, mode: _BuildRevMetaCreate|_BuildRevMetaUpdate) -> RevisionMeta:
        uid=uuid4()
        if isinstance(mode, _BuildRevMetaCreate):
            resource_id=str(uid)
            revision_id=f"{resource_id}-1"
            last_revision_id = ""
        elif isinstance(mode, _BuildRevMetaUpdate):
            prev_res_meta = mode.prev_res_meta
            resource_id = prev_res_meta.resource_id
            revision_id = f"{resource_id}-{prev_res_meta.total_revision_count+1}"
            last_revision_id=prev_res_meta.current_revision_id

        meta = RevisionMeta(
            uid=uid,
            resource_id=resource_id,
            revision_id=revision_id,
            last_revision_id=last_revision_id,
            schema_version="",
            data_hash="",
            status=RevisionStatus.stable,
            created_time=self.now_ctx.get(),
            updated_time=self.now_ctx.get(),
            created_by=self.user_ctx.get(),
            updated_by=self.user_ctx.get(),
        )
        return meta
    
    def get_meta(self, resource_id: str) -> ResourceMeta:
        meta_b = self.storage.get_meta(resource_id)
        meta = msgspec.json.decode(meta_b, type=ResourceMeta)
        return meta

    def create(self, data: T) -> RevisionMeta:
        """Create resource and return the metadata.
        
        Arguments:

            - data (T): the data to be created.

        Returns:

            - meta (RevisionMeta): the metadata of the created data.
        
        """
        meta = self._rev_meta(_BuildRevMetaCreate())
        resource = Resource(
            meta=meta,
            data=data,
        )
        self.storage.save_resource_revision(
            meta.resource_id, meta.revision_id, msgspec.json.encode(resource)
        )
        self.storage.save_meta(
            meta.resource_id,
            msgspec.json.encode(self._res_meta(_BuildResMetaCreate(meta)))
        )
        return meta

    def get(self, resource_id: str) -> Resource[T]:
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
        meta = self.get_meta(resource_id)
        data_b = self.storage.get_resource_revision(
            resource_id,
            meta.current_revision_id
        )
        return msgspec.json.decode(data_b, type=Resource[self.resource_type])

    def update(self, resource_id: str, data: T) -> RevisionMeta:
        """Update the data of the resource.

        Arguments:

            - resource_id (str): the id of the resource want to update.
            - data (T): the data want to replace the current one.

        Returns:

            meta (RevisionMeta): the metadata of the updated data

        Raises:

            - ResourceIDNotFoundError: if resource id not exists.
            - SchemaConflictError: if resource schema version doesn't match the latest version.

        It will directly replace the data. If need partial update, use patch.
        """
        prev_res_meta = self.get_meta(resource_id)
        rev_meta = self._rev_meta(_BuildRevMetaUpdate(prev_res_meta))
        res_meta = self._res_meta(_BuildResMetaUpdate(prev_res_meta, rev_meta))
        resource = Resource(
            meta=rev_meta,
            data=data,
        )
        self.storage.save_resource_revision(
            resource_id, rev_meta.revision_id, msgspec.json.encode(resource)
        )
        self.storage.save_meta(
            resource_id,
            msgspec.json.encode(res_meta)
        )
        return rev_meta

    def patch(self, resource_id: str, patch_data: RCF9802) -> RevisionMeta:
        """Patch update data of the resource.

        Arguments:

            - resource_id (str): the id of the resource want to update.
            - patch_data (RCF9802): patch data with format RCF9802.

        Returns:

            meta (RevisionMeta): the metadata of the updated data

        Raises:

            - ResourceIDNotFoundError: if resource id not exists.
            - SchemaConflictError: if resource schema version doesn't match the latest version.

        Use RCF9802 to update the resource data.
        """

    def yank(self, resource_id: str, revision_id: str) -> RevisionMeta:
        """Delete a revision of a resource.

        Arguments:

            - resource_id (str): the id of the resource want to update.
            - revision_id (str): the id of the revision.

        Returns:

            meta (RevisionMeta): the metadata of the updated data

        Raises:

            - ResourceIDNotFoundError: if resource id not exists.
            - RevisionIDNotFoundError: if revision id not exists.

        Yank a revision of a resource. The next latest revision will be used as the current revision.
        If no revision left, this action is identical to `delete(resource_id)`.
        """

    def delete(self, resource_id: str) -> None:
        """Delete the resource.

        Arguments:

            - resource_id (str): the id of the resource want to update.

        Raises:

            - ResourceIDNotFoundError: if resource id not exists.

        Delete a resource with the resource ID. It will delete all revision of the resource.
        """
