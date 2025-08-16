from collections.abc import Callable
from contextlib import contextmanager
from typing import Any, TypeVar, Generic
import datetime as dt
from uuid import uuid4
from msgspec import UNSET, Struct
from jsonpatch import JsonPatch
import json
import msgspec


from autocrud.resource_manager.basic import (
    Ctx,
    IMetaStore,
    IResourceManager,
    IResourceStore,
    IStorage,
    Resource,
    ResourceIDNotFoundError,
    ResourceIsDeletedError,
    ResourceMeta,
    ResourceMetaSearchQuery,
    RevisionIDNotFoundError,
    RevisionInfo,
    RevisionStatus,
)
from autocrud.util.naming import NameConverter, NamingFormat

try:
    import pydantic
except ImportError:
    pydantic = None

T = TypeVar("T")


class DataConverter:
    """數據轉換器，處理不同數據類型的序列化和反序列化"""

    @staticmethod
    def is_pydantic_model(model_type: type) -> bool:
        """檢查是否是 Pydantic 模型"""
        if pydantic is not None:
            return issubclass(model_type, pydantic.BaseModel)
        return False  # assume not pydantic if not installed.

    @staticmethod
    def decode_json_to_data(json_bytes: bytes, resource_type: type) -> msgspec.Raw | T:
        """將 JSON bytes 轉換為指定類型的數據"""
        if pydantic is not None and issubclass(resource_type, pydantic.BaseModel):
            # 對於 Pydantic 模型，先解析為字典再創建實例，然後存儲為 Raw
            json_data = json.loads(json_bytes)
            pydantic_instance = resource_type.model_validate(json_data)
            # 將 Pydantic 實例序列化為 Raw 格式存儲
            return msgspec.Raw(pydantic_instance.model_dump_json().encode())
        else:
            # 對於其他類型，使用 msgspec 直接解析
            return msgspec.json.decode(json_bytes, type=resource_type)

    @staticmethod
    def data_to_builtins(data: msgspec.Raw | T) -> Any:
        """將數據轉換為 Python 內建類型，特殊處理 msgspec.Raw"""
        if isinstance(data, msgspec.Raw):
            # 如果是 Raw 數據，先解碼為 JSON，再解析為 Python 對象
            return json.loads(bytes(data).decode("utf-8"))
        else:
            # 對於其他類型，使用 msgspec.to_builtins
            return msgspec.to_builtins(data)

    @staticmethod
    def builtins_to_data(obj: Any, resource_type: type[T]) -> msgspec.Raw | T:
        if pydantic is not None and issubclass(resource_type, pydantic.BaseModel):
            pydantic_instance = resource_type.model_validate(obj)
            return msgspec.Raw(pydantic_instance.model_dump_json().encode())
        return msgspec.convert(obj, type=resource_type)


class SimpleStorage(IStorage[T]):
    def __init__(self, meta_store: IMetaStore, resource_store: IResourceStore[T]):
        self._meta_store = meta_store
        self._resource_store = resource_store

    def exists(self, resource_id: str) -> bool:
        return resource_id in self._meta_store

    def revision_exists(self, resource_id: str, revision_id: str) -> bool:
        return self.exists(resource_id) and self._resource_store.exists(
            resource_id, revision_id
        )

    def get_meta(self, resource_id: str) -> ResourceMeta:
        return self._meta_store[resource_id]

    def save_meta(self, meta: ResourceMeta) -> None:
        self._meta_store[meta.resource_id] = meta

    def list_revisions(self, resource_id: str) -> list[str]:
        return list(self._resource_store.list_revisions(resource_id))

    def get_resource_revision(self, resource_id: str, revision_id: str) -> Resource[T]:
        return self._resource_store.get(resource_id, revision_id)

    def save_resource_revision(self, resource: Resource[T]) -> None:
        self._resource_store.save(resource)

    def search(self, query: ResourceMetaSearchQuery) -> list[ResourceMeta]:
        return list(self._meta_store.iter_search(query))


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
        storage: IStorage[T],
        id_generator: Callable[[], str] | None = None,
    ):
        self.user_ctx = Ctx[str]("user_ctx")
        self.now_ctx = Ctx[dt.datetime]("now_ctx")
        self.resource_type = resource_type
        self.storage = storage
        _model_name = NameConverter(resource_type.__name__).to(NamingFormat.SNAKE)

        def default_id_generator():
            return f"{_model_name}:{uuid4()}"

        self.id_generator = (
            default_id_generator if id_generator is None else id_generator
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
            resource_id = self.id_generator()
            revision_id = f"{resource_id}:1"
            last_revision_id = UNSET
        elif isinstance(mode, _BuildRevInfoUpdate):
            prev_res_meta = mode.prev_res_meta
            resource_id = prev_res_meta.resource_id
            revision_id = f"{resource_id}:{prev_res_meta.total_revision_count + 1}"
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
        self.storage.save_resource_revision(resource)
        self.storage.save_meta(self._res_meta(_BuildResMetaCreate(info)))
        return info

    def get(self, resource_id: str) -> Resource[T]:
        meta = self.get_meta(resource_id)
        return self.get_resource_revision(resource_id, meta.current_revision_id)

    def get_resource_revision(self, resource_id: str, revision_id: str) -> Resource[T]:
        return self.storage.get_resource_revision(resource_id, revision_id)

    def list_revisions(self, resource_id: str) -> list[str]:
        return self.storage.list_revisions(resource_id)

    def update(self, resource_id: str, data: T) -> RevisionInfo:
        prev_res_meta = self.get_meta(resource_id)
        rev_info = self._rev_info(_BuildRevInfoUpdate(prev_res_meta))
        res_meta = self._res_meta(_BuildResMetaUpdate(prev_res_meta, rev_info))
        resource = Resource(
            info=rev_info,
            data=data,
        )
        self.storage.save_resource_revision(resource)
        self.storage.save_meta(res_meta)
        return rev_info

    def patch(self, resource_id: str, patch_data: JsonPatch) -> RevisionInfo:
        data = self.get(resource_id).data
        d = DataConverter.data_to_builtins(data)
        patch_data.apply(d, in_place=True)
        data = DataConverter.builtins_to_data(d, self.resource_type)
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
