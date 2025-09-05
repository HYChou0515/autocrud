from collections.abc import Callable, Generator
from contextlib import contextmanager
from functools import cached_property, wraps
from typing import IO, TypeVar, Generic, Any, get_origin, get_args, TYPE_CHECKING
import datetime as dt
from uuid import uuid4
from msgspec import UNSET, Struct, UnsetType
from jsonpatch import JsonPatch
import msgspec
from xxhash import xxh3_128_hexdigest


if TYPE_CHECKING:
    from autocrud.permission.basic import IPermissionChecker


from autocrud.permission.basic import PermissionResult
from autocrud.resource_manager.basic import (
    Ctx,
    Encoding,
    IMetaStore,
    IMigration,
    IResourceManager,
    IResourceStore,
    IStorage,
    MsgspecSerializer,
    Resource,
    ResourceAction,
    ResourceIDNotFoundError,
    ResourceIsDeletedError,
    ResourceMeta,
    ResourceMetaSearchQuery,
    RevisionIDNotFoundError,
    RevisionInfo,
    RevisionStatus,
    IndexableField,
    SpecialIndex,
)
from autocrud.resource_manager.data_converter import DataConverter
from autocrud.util.naming import NameConverter, NamingFormat


T = TypeVar("T")


def _get_type_name(resource_type) -> str:
    """取得類型名稱，處理 Union 類型"""
    if hasattr(resource_type, "__name__"):
        return resource_type.__name__

    # 處理 Union 類型
    origin = get_origin(resource_type)
    if origin is not None:
        args = get_args(resource_type)
        if args:
            # 使用第一個類型的名稱，或者創建一個組合名稱
            first_type = args[0]
            if hasattr(first_type, "__name__"):
                return f"{first_type.__name__}Union"
        return "UnionType"

    # 後備方案
    return str(resource_type).replace(" ", "").replace("|", "Or")


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

    def get_resource_revision_info(
        self, resource_id: str, revision_id: str
    ) -> RevisionInfo:
        return self._resource_store.get_revision_info(resource_id, revision_id)

    def save_resource_revision(self, resource: Resource[T]) -> None:
        self._resource_store.save(resource)

    def search(self, query: ResourceMetaSearchQuery) -> list[ResourceMeta]:
        return list(self._meta_store.iter_search(query))

    def encode_data(self, data: T) -> bytes:
        return self._resource_store.encode(data)

    def dump_meta(self) -> Generator[ResourceMeta]:
        yield from self._meta_store.values()

    def dump_resource(self) -> Generator[Resource[T]]:
        for resource_id in self._resource_store.list_resources():
            for revision_id in self._resource_store.list_revisions(resource_id):
                yield self._resource_store.get(resource_id, revision_id)


class _BuildRevMetaCreate(Struct):
    data: T


class _BuildRevInfoUpdate(Struct):
    prev_res_meta: ResourceMeta
    data: T


class _BuildResMetaCreate(Struct):
    rev_info: RevisionInfo
    data: T


class _BuildResMetaUpdate(Struct):
    prev_res_meta: ResourceMeta
    rev_info: RevisionInfo
    data: T


def smart_permission_check():
    """
    智能權限檢查裝飾器 - 支援新的上下文模式

    Args:
        action: 權限動作，如果為 None 則使用方法名
        extract_resource_id: 是否從方法參數中提取 resource_id
        **extra_context: 額外的上下文資料
    """

    def decorator(method):
        action = ResourceAction[method.__name__]

        @wraps(method)
        def _permission_check(self: IResourceManager[T], *method_args, **method_kwargs):
            from autocrud.permission.basic import (
                PermissionContext,
            )
            from autocrud.resource_manager.basic import PermissionDeniedError

            user = self.user_or_unset
            context = PermissionContext(
                user=user,
                now=self.now_or_unset,
                action=action,
                resource_name=self.resource_name,
                method_args=method_args,
                method_kwargs=method_kwargs,
            )
            # 執行權限檢查
            result = self.permission_checker.check_permission(context)

            if result != PermissionResult.allow:
                raise PermissionDeniedError(
                    f"Permission denied for user '{context.user}' "
                    f"to perform '{context.action}' on '{context.resource_name}'"
                )

            return method(self, *method_args, **method_kwargs)

        return _permission_check

    return decorator


class ResourceManager(IResourceManager[T], Generic[T]):
    def __init__(
        self,
        resource_type: type[T],
        *,
        storage: IStorage[T],
        id_generator: Callable[[], str] | None = None,
        migration: IMigration | None = None,
        indexed_fields: list[IndexableField] | None = None,
        permission_checker: "IPermissionChecker | None" = None,
        name: str | NamingFormat = NamingFormat.SNAKE,
    ):
        self.user_ctx = Ctx("user_ctx", strict_type=str)
        self.now_ctx = Ctx("now_ctx", strict_type=dt.datetime)
        self.id_ctx = Ctx[str | UnsetType]("id_ctx")
        self._resource_type = resource_type
        self.storage = storage
        self.data_converter = DataConverter(self.resource_type)
        schema_version = migration.schema_version if migration else None
        self.schema_version = UNSET if schema_version is None else schema_version
        self._indexed_fields = indexed_fields or []

        if isinstance(name, NamingFormat):
            self._resource_name = NameConverter(_get_type_name(resource_type)).to(
                NamingFormat.SNAKE
            )
        else:
            self._resource_name = name

        def default_id_generator():
            return f"{self._resource_name}:{uuid4()}"

        self.id_generator = (
            default_id_generator if id_generator is None else id_generator
        )
        # 設定權限檢查器
        if permission_checker is not None:
            self.permission_checker = permission_checker
        else:
            from autocrud.permission.simple import AllowAll

            self.permission_checker = AllowAll()

    @property
    def user(self) -> str:
        return self.user_ctx.get()

    @property
    def now(self) -> dt.datetime:
        return self.now_ctx.get()

    @property
    def user_or_unset(self) -> str | UnsetType:
        try:
            return self.user_ctx.get()
        except LookupError:
            return UNSET

    @property
    def now_or_unset(self) -> dt.datetime | UnsetType:
        try:
            return self.now_ctx.get()
        except LookupError:
            return UNSET

    @property
    def resource_type(self):
        return self._resource_type

    @property
    def resource_name(self):
        return self._resource_name

    @property
    def indexed_fields(self) -> list[IndexableField]:
        """取得被索引的 data 欄位列表"""
        return self._indexed_fields

    def _extract_indexed_values(self, data: T) -> dict[str, Any]:
        """從 data 中提取需要索引的值"""
        indexed_data = {}
        for field in self._indexed_fields:
            try:
                if field.field_type == SpecialIndex.msgspec_tag:
                    value = msgspec.inspect.type_info(type(data)).tag
                else:
                    # 使用 JSON path 提取值
                    value = self._extract_by_path(data, field.field_path)
                indexed_data[field.field_path] = value
            except Exception:
                # 如果提取失敗，跳過該字段
                continue

        return indexed_data

    def _extract_by_path(self, data: T, field_path: str) -> Any:
        """使用 JSON path 從 data 中提取值"""
        # 簡單的點分隔路徑解析 (e.g., "user.email")
        parts = field_path.split(".")
        current = data

        for part in parts:
            if hasattr(current, part):
                current = getattr(current, part)
            elif isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None

        if current is UNSET:
            return None
        return current

    @contextmanager
    def meta_provide(
        self, user: str, now: dt.datetime, *, resource_id: str | UnsetType = UNSET
    ):
        with (
            self.user_ctx.ctx(user),
            self.now_ctx.ctx(now),
            self.id_ctx.ctx(resource_id),
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

        # 提取索引數據
        indexed_data = {}
        if self._indexed_fields:
            extracted = self._extract_indexed_values(mode.data)
            if extracted:
                indexed_data = extracted

        return ResourceMeta(
            current_revision_id=current_revision_id,
            resource_id=resource_id,
            schema_version=self.schema_version,
            total_revision_count=total_revision_count,
            created_time=created_time,
            updated_time=self.now_ctx.get(),
            created_by=created_by,
            updated_by=self.user_ctx.get(),
            indexed_data=indexed_data,
        )

    def get_data_hash(self, data: T) -> str:
        b = self.storage.encode_data(data)
        data_hash = f"xxh3_128:{xxh3_128_hexdigest(b)}"
        return data_hash

    def _rev_info(
        self, mode: _BuildRevMetaCreate | _BuildRevInfoUpdate
    ) -> RevisionInfo:
        uid = uuid4()
        if isinstance(mode, _BuildRevMetaCreate):
            _id = self.id_ctx.get()
            if _id is UNSET:
                resource_id = self.id_generator()
            else:
                resource_id = _id
            revision_id = f"{resource_id}:1"
            last_revision_id = UNSET
        elif isinstance(mode, _BuildRevInfoUpdate):
            prev_res_meta = mode.prev_res_meta
            resource_id = prev_res_meta.resource_id
            revision_id = f"{resource_id}:{prev_res_meta.total_revision_count + 1}"
            last_revision_id = prev_res_meta.current_revision_id

        data_hash = self.get_data_hash(mode.data)

        info = RevisionInfo(
            uid=uid,
            resource_id=resource_id,
            revision_id=revision_id,
            parent_revision_id=last_revision_id,
            schema_version=self.schema_version,
            data_hash=data_hash,
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

    @smart_permission_check()
    def get_meta(self, resource_id: str) -> ResourceMeta:
        meta = self._get_meta_no_check_is_deleted(resource_id)
        if meta.is_deleted:
            raise ResourceIsDeletedError(resource_id)
        return meta

    @smart_permission_check()
    def search_resources(self, query: ResourceMetaSearchQuery) -> list[ResourceMeta]:
        return self.storage.search(query)

    @smart_permission_check()
    def create(self, data: T) -> RevisionInfo:
        info = self._rev_info(_BuildRevMetaCreate(data))
        resource = Resource(
            info=info,
            data=data,
        )
        self.storage.save_resource_revision(resource)
        self.storage.save_meta(self._res_meta(_BuildResMetaCreate(info, data)))
        return info

    @smart_permission_check()
    def get(self, resource_id: str) -> Resource[T]:
        meta = self.get_meta(resource_id)
        return self.get_resource_revision(resource_id, meta.current_revision_id)

    @smart_permission_check()
    def get_resource_revision(self, resource_id: str, revision_id: str) -> Resource[T]:
        obj = self.storage.get_resource_revision(resource_id, revision_id)
        return obj

    @smart_permission_check()
    def list_revisions(self, resource_id: str) -> list[str]:
        return self.storage.list_revisions(resource_id)

    @smart_permission_check()
    def update(self, resource_id: str, data: T) -> RevisionInfo:
        prev_res_meta = self.get_meta(resource_id)
        prev_info = self.storage.get_resource_revision_info(
            resource_id, prev_res_meta.current_revision_id
        )
        cur_data_hash = self.get_data_hash(data)
        if prev_info.data_hash == cur_data_hash:
            return prev_info
        rev_info = self._rev_info(_BuildRevInfoUpdate(prev_res_meta, data))
        res_meta = self._res_meta(_BuildResMetaUpdate(prev_res_meta, rev_info, data))
        resource = Resource(
            info=rev_info,
            data=data,
        )
        self.storage.save_resource_revision(resource)
        self.storage.save_meta(res_meta)
        return rev_info

    @smart_permission_check()
    def create_or_update(self, resource_id, data):
        try:
            return self.update(resource_id, data)
        except ResourceIDNotFoundError:
            return self.create(data)

    @smart_permission_check()
    def patch(self, resource_id: str, patch_data: JsonPatch) -> RevisionInfo:
        data = self.get(resource_id).data
        d = self.data_converter.data_to_builtins(data)
        patch_data.apply(d, in_place=True)
        data = self.data_converter.builtins_to_data(d)
        return self.update(resource_id, data)

    @smart_permission_check()
    def switch(self, resource_id: str, revision_id: str) -> ResourceMeta:
        meta = self.get_meta(resource_id)
        if meta.current_revision_id == revision_id:
            return meta
        if not self.storage.revision_exists(resource_id, revision_id):
            raise RevisionIDNotFoundError(resource_id, revision_id)

        # 切換到指定版本時，需要更新索引數據
        if self._indexed_fields:
            resource = self.storage.get_resource_revision(resource_id, revision_id)
            indexed_data = self._extract_indexed_values(resource.data)
            meta.indexed_data = indexed_data if indexed_data else UNSET

        meta.updated_by = self.user_ctx.get()
        meta.updated_time = self.now_ctx.get()
        meta.current_revision_id = revision_id
        self.storage.save_meta(meta)
        return meta

    @smart_permission_check()
    def delete(self, resource_id: str) -> ResourceMeta:
        meta = self.get_meta(resource_id)
        meta.is_deleted = True
        meta.updated_by = self.user_ctx.get()
        meta.updated_time = self.now_ctx.get()
        self.storage.save_meta(meta)
        return meta

    @smart_permission_check()
    def restore(self, resource_id: str) -> ResourceMeta:
        meta = self._get_meta_no_check_is_deleted(resource_id)
        if meta.is_deleted:
            meta.is_deleted = False
            meta.updated_by = self.user_ctx.get()
            meta.updated_time = self.now_ctx.get()
            self.storage.save_meta(meta)
        return meta

    @smart_permission_check()
    def dump(self) -> Generator[tuple[str, IO[bytes]]]:
        for meta in self.storage.dump_meta():
            yield f"meta/{meta.resource_id}", self.meta_serializer.encode(meta)
        for resource in self.storage.dump_resource():
            yield f"data/{resource.info.uid}", self.resource_serializer.encode(resource)

    @smart_permission_check()
    def load(self, key: str, bio: IO[bytes]) -> None:
        if key.startswith("meta/"):
            self.storage.save_meta(self.meta_serializer.decode(bio.read()))
        elif key.startswith("data/"):
            self.storage.save_resource_revision(
                self.resource_serializer.decode(bio.read())
            )

    @cached_property
    def meta_serializer(self):
        return MsgspecSerializer(encoding=Encoding.msgpack, resource_type=ResourceMeta)

    @cached_property
    def resource_serializer(self):
        return MsgspecSerializer(
            encoding=Encoding.msgpack, resource_type=Resource[self.resource_type]
        )
