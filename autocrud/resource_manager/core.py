import datetime as dt
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager, suppress
from functools import cached_property, wraps
import io
import traceback
from typing import (
    IO,
    TYPE_CHECKING,
    Any,
    Generic,
    NamedTuple,
    TypeVar,
    get_args,
    get_origin,
)
from uuid import uuid4
import inspect
import msgspec
from jsonpatch import JsonPatch
from msgspec import UNSET, Struct, UnsetType
from xxhash import xxh3_128_hexdigest
from autocrud.types import (
    AfterMigrate,
    AfterModify,
    BeforeMigrate,
    BeforeModify,
    CannotModifyResourceError,
    OnFailureMigrate,
    OnFailureModify,
    OnSuccessMigrate,
    OnSuccessModify,
    PermissionDeniedError,
    RawResource,
)
import more_itertools as mit
from autocrud.types import (
    AfterCreate,
    AfterDelete,
    AfterDump,
    AfterGet,
    AfterGetMeta,
    AfterGetResourceRevision,
    AfterListRevisions,
    AfterLoad,
    AfterPatch,
    AfterRestore,
    AfterSearchResources,
    AfterSwitch,
    AfterUpdate,
    BeforeCreate,
    BeforeDelete,
    BeforeDump,
    BeforeGet,
    BeforeGetMeta,
    BeforeGetResourceRevision,
    BeforeListRevisions,
    BeforeLoad,
    BeforePatch,
    BeforeRestore,
    BeforeSearchResources,
    BeforeSwitch,
    BeforeUpdate,
    EventContext,
    IMigration,
    IResourceManager,
    IndexableField,
    OnFailureCreate,
    OnFailureDelete,
    OnFailureDump,
    OnFailureGet,
    OnFailureGetMeta,
    OnFailureGetResourceRevision,
    OnFailureListRevisions,
    OnFailureLoad,
    OnFailurePatch,
    OnFailureRestore,
    OnFailureSearchResources,
    OnFailureSwitch,
    OnFailureUpdate,
    OnSuccessCreate,
    OnSuccessDelete,
    OnSuccessDump,
    OnSuccessGet,
    OnSuccessGetMeta,
    OnSuccessGetResourceRevision,
    OnSuccessListRevisions,
    OnSuccessLoad,
    OnSuccessPatch,
    OnSuccessRestore,
    OnSuccessSearchResources,
    OnSuccessSwitch,
    OnSuccessUpdate,
    Resource,
    ResourceAction,
    ResourceIDNotFoundError,
    ResourceIsDeletedError,
    ResourceMeta,
    ResourceMetaSearchQuery,
    RevisionIDNotFoundError,
    RevisionInfo,
    RevisionStatus,
    SpecialIndex,
)
from autocrud.types import IEventHandler

if TYPE_CHECKING:
    from autocrud.types import IPermissionChecker


from autocrud.types import PermissionResult
from autocrud.resource_manager.basic import (
    Ctx,
    Encoding,
    IMetaStore,
    IResourceStore,
    IStorage,
    MsgspecSerializer,
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


class SimpleStorage(IStorage):
    def __init__(self, meta_store: IMetaStore, resource_store: IResourceStore):
        self._meta_store = meta_store
        self._resource_store = resource_store

    def exists(self, resource_id: str) -> bool:
        return resource_id in self._meta_store

    def revision_exists(self, resource_id: str, revision_id: str) -> bool:
        meta = self.get_meta(resource_id)
        return self.exists(resource_id) and self._resource_store.exists(
            resource_id,
            revision_id,
            meta.schema_version,
        )

    def get_meta(self, resource_id: str) -> ResourceMeta:
        return self._meta_store[resource_id]

    def save_meta(self, meta: ResourceMeta) -> None:
        self._meta_store[meta.resource_id] = meta

    def list_revisions(self, resource_id: str) -> list[str]:
        return list(self._resource_store.list_revisions(resource_id))

    def get_data_bytes(self, resource_id: str, revision_id: str) -> IO[bytes]:
        meta = self.get_meta(resource_id)
        return self._resource_store.get_data_bytes(
            resource_id, revision_id, meta.schema_version
        )

    def get_resource_revision_info(
        self,
        resource_id: str,
        revision_id: str,
    ) -> RevisionInfo:
        meta = self.get_meta(resource_id)
        return self._resource_store.get_revision_info(
            resource_id, revision_id, meta.schema_version
        )

    def save_revision(self, info: RevisionInfo, data: IO[bytes]) -> None:
        self._resource_store.save(info, data)

    def search(self, query: ResourceMetaSearchQuery) -> list[ResourceMeta]:
        return list(self._meta_store.iter_search(query))

    def count(self, query: ResourceMetaSearchQuery) -> int:
        return mit.ilen(self._meta_store.iter_search(query))

    def dump_meta(self) -> Generator[ResourceMeta]:
        yield from self._meta_store.values()

    def dump_resource(self) -> Generator[tuple[RevisionInfo, IO[bytes]]]:
        for resource_id in self._resource_store.list_resources():
            for revision_id in self._resource_store.list_revisions(resource_id):
                for schema_version in self._resource_store.list_schema_versions(
                    resource_id, revision_id
                ):
                    info = self._resource_store.get_revision_info(
                        resource_id, revision_id, schema_version
                    )
                    with self._resource_store.get_data_bytes(
                        resource_id, revision_id, schema_version
                    ) as data:
                        yield info, data


class _BuildRevInfoCreate(Struct):
    data: T
    status: RevisionStatus = RevisionStatus.stable


class _BuildRevInfoUpdate(Struct):
    prev_res_meta: ResourceMeta
    data: T
    status: RevisionStatus = RevisionStatus.stable


class _BuildRevInfoModify(Struct):
    prev_res_meta: ResourceMeta
    prev_info: RevisionInfo
    data: T | UnsetType
    status: RevisionStatus | UnsetType = RevisionStatus.stable


class _BuildResMetaCreate(Struct):
    rev_info: RevisionInfo
    data: T


class _BuildResMetaUpdate(Struct):
    prev_res_meta: ResourceMeta
    rev_info: RevisionInfo
    data: T


class _BuildResMetaModify(Struct):
    prev_res_meta: ResourceMeta
    rev_info: RevisionInfo
    data: T | UnsetType


class _Contexts(NamedTuple):
    before: EventContext
    after: EventContext
    on_success: EventContext
    on_failure: EventContext


class PermissionEventHandler(IEventHandler):
    def __init__(self, permission_checker: "IPermissionChecker"):
        self.permission_checker = permission_checker

    def is_supported(self, context: EventContext) -> bool:
        with suppress(AttributeError):
            return context.action in ResourceAction and context.phase == "before"
        return False

    def handle_event(self, context: EventContext) -> None:
        result = self.permission_checker.check_permission(context)
        if result != PermissionResult.allow:
            raise PermissionDeniedError(
                f"Permission denied for user '{context.user}' "
                f"to perform '{context.action}' on '{context.resource_name}'",
            )


def execute_with_events(
    contexts: _Contexts,
    result: str | Callable[[Any], dict[str, Any]],
    *,
    inputs: dict[str, str | UnsetType] | None = None,
):
    contexts = _Contexts(*contexts)
    if isinstance(result, str):

        def _build_result(x):
            return {result: x}

    else:
        _build_result = result

    def wrapper(func):
        sig = inspect.signature(func)

        @wraps(func)
        def wrapped(self: "ResourceManager", *args, **kwargs):
            bound_args = sig.bind(self, *args, **kwargs)
            bound_args.apply_defaults()  # 應用默認值

            func_inputs = dict(bound_args.arguments)
            del func_inputs["self"]

            inputs_ = func_inputs | {
                "user": self.user_or_unset,
                "now": self.now_or_unset,
                "resource_name": self.resource_name,
            }
            if inputs:

                def get_from_path(d, path: str):
                    parts = path.split(".")
                    current = d
                    for part in parts:
                        if hasattr(current, part):
                            current = getattr(current, part)
                        else:
                            current = current[part]
                    return current

                for k, v in inputs.items():
                    if v is UNSET:
                        del inputs_[k]
                    else:
                        inputs_[k] = get_from_path(func_inputs, v)
            self._handle_event(contexts.before(**inputs_))
            try:
                result = func(self, *args, **kwargs)
                built_result = _build_result(result)
                self._handle_event(contexts.on_success(**inputs_, **built_result))
                return result
            except Exception as e:
                self._handle_event(
                    contexts.on_failure(
                        **inputs_,
                        error=str(e),
                        stack_trace=traceback.format_exc(),
                    )
                )
                raise
            finally:
                self._handle_event(contexts.after(**inputs_))

        return wrapped

    return wrapper


class ResourceManager(IResourceManager[T], Generic[T]):
    def __init__(
        self,
        resource_type: type[T],
        *,
        storage: IStorage,
        id_generator: Callable[[], str] | None = None,
        migration: IMigration[T] | None = None,
        indexed_fields: list[IndexableField] | None = None,
        permission_checker: "IPermissionChecker | None" = None,
        name: str | NamingFormat = NamingFormat.SNAKE,
        event_handlers: Sequence[IEventHandler] | None = None,
        encoding: Encoding = Encoding.json,
        default_status: RevisionStatus = RevisionStatus.stable,
        default_user: str | UnsetType = UNSET,
        default_now: Callable[[], dt.datetime] | UnsetType = UNSET,
    ):
        if default_user is UNSET:
            self.user_ctx = Ctx("user_ctx", strict_type=str)
        else:
            self.user_ctx = Ctx("user_ctx", strict_type=str, default=default_user)
        if default_now is UNSET:
            self.now_ctx = Ctx("now_ctx", strict_type=dt.datetime)
        else:
            self.now_ctx = Ctx(
                "now_ctx", strict_type=dt.datetime, default_factory=default_now
            )
        self.id_ctx = Ctx[str | UnsetType]("id_ctx", default=UNSET)
        self._resource_type = resource_type
        self.storage = storage
        self.data_converter = DataConverter(self.resource_type)
        schema_version = migration.schema_version if migration else None
        self._schema_version = schema_version
        self._indexed_fields = indexed_fields or []
        self._migration = migration
        self._data_serializer = MsgspecSerializer(
            encoding=encoding,
            resource_type=resource_type,
        )
        self.default_status = default_status

        if isinstance(name, NamingFormat):
            self._resource_name = NameConverter(_get_type_name(resource_type)).to(
                NamingFormat.SNAKE,
            )
        else:
            self._resource_name = name

        def default_id_generator():
            return f"{self._resource_name}:{uuid4()}"

        self.id_generator = (
            default_id_generator if id_generator is None else id_generator
        )
        self.event_handlers = list(event_handlers) if event_handlers else []
        # 設定權限檢查器
        if permission_checker is not None:
            self.event_handlers.append(
                PermissionEventHandler(permission_checker),
            )

    def encode(self, data: T) -> bytes:
        return self._data_serializer.encode(data)

    def decode(self, data: bytes) -> T:
        return self._data_serializer.decode(data)

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
    def schema_version(self) -> str:
        if self._schema_version is None:
            raise ValueError("Schema version is not set for this resource manager")
        return self._schema_version

    @execute_with_events(
        (
            BeforeMigrate,
            AfterMigrate,
            OnSuccessMigrate,
            OnFailureMigrate,
        ),
        "meta",
    )
    def migrate(self, resource_id: str) -> ResourceMeta:
        if self._migration is None:
            raise ValueError("Migration is not set for this resource manager")

        # 獲取當前資源和元數據
        meta = self._get_meta_no_check_is_deleted(resource_id)
        info = self.storage.get_resource_revision_info(
            resource_id, meta.current_revision_id
        )

        # 檢查是否需要遷移
        if info.schema_version == self._migration.schema_version:
            # 如果已經是最新版本，直接返回當前元數據
            return meta

        # 執行數據遷移
        # 序列化當前數據
        with self.storage.get_data_bytes(
            resource_id, meta.current_revision_id
        ) as data_io:
            migrated_data = self._migration.migrate(data_io, info.schema_version)

        # 更新 resource info 的 schema_version
        info.parent_schema_version = info.schema_version
        info.schema_version = self._migration.schema_version
        meta.schema_version = self._migration.schema_version
        meta.indexed_data = self._extract_indexed_values(migrated_data)

        self.storage.save_meta(meta)
        self.storage.save_revision(info, io.BytesIO(self.encode(migrated_data)))

        return meta

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
            value = UNSET
            if field.field_type == SpecialIndex.msgspec_tag:
                with suppress(Exception):
                    value = msgspec.inspect.type_info(type(data)).tag
            else:
                # 使用 JSON path 提取值
                with suppress(Exception):
                    value = self._extract_by_path(data, field.field_path)
            if value is not UNSET:
                indexed_data[field.field_path] = value

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
        self,
        user: str | UnsetType = UNSET,
        now: dt.datetime | UnsetType = UNSET,
        *,
        resource_id: str | UnsetType = UNSET,
    ):
        with (
            self.user_ctx.ctx(user) if user is not UNSET else suppress(),
            self.now_ctx.ctx(now) if now is not UNSET else suppress(),
            self.id_ctx.ctx(resource_id) if resource_id is not UNSET else suppress(),
        ):
            yield

    def _res_meta(
        self,
        mode: _BuildResMetaCreate | _BuildResMetaUpdate | _BuildResMetaModify,
    ) -> ResourceMeta:
        if isinstance(mode, _BuildResMetaCreate):
            current_revision_id = mode.rev_info.revision_id
            resource_id = mode.rev_info.resource_id
            total_revision_count = 1
            created_time = self.now_ctx.get()
            created_by = self.user_ctx.get()
            indexed_data = self._extract_indexed_values(mode.data)
        elif isinstance(mode, _BuildResMetaUpdate):
            current_revision_id = mode.rev_info.revision_id
            resource_id = mode.prev_res_meta.resource_id
            total_revision_count = mode.prev_res_meta.total_revision_count + 1
            created_time = mode.prev_res_meta.created_time
            created_by = mode.prev_res_meta.created_by
            indexed_data = self._extract_indexed_values(mode.data)
        elif isinstance(mode, _BuildResMetaModify):
            current_revision_id = mode.rev_info.revision_id
            resource_id = mode.prev_res_meta.resource_id
            total_revision_count = mode.prev_res_meta.total_revision_count
            created_time = mode.prev_res_meta.created_time
            created_by = mode.prev_res_meta.created_by
            if mode.data is UNSET:
                indexed_data = mode.prev_res_meta.indexed_data
            else:
                indexed_data = self._extract_indexed_values(mode.data)

        return ResourceMeta(
            current_revision_id=current_revision_id,
            resource_id=resource_id,
            schema_version=self._schema_version,
            total_revision_count=total_revision_count,
            created_time=created_time,
            updated_time=self.now_ctx.get(),
            created_by=created_by,
            updated_by=self.user_ctx.get(),
            indexed_data=indexed_data,
        )

    def get_data_hash(self, data: T) -> str:
        b = self.encode(data)
        self.decode(b)  # 確保可解碼
        data_hash = f"xxh3_128:{xxh3_128_hexdigest(b)}"
        return data_hash

    def _rev_info(
        self,
        mode: _BuildRevInfoCreate | _BuildRevInfoUpdate | _BuildRevInfoModify,
    ) -> RevisionInfo:
        uid = uuid4()
        if isinstance(mode, _BuildRevInfoCreate):
            _id = self.id_ctx.get()
            if _id is UNSET:
                resource_id = self.id_generator()
            else:
                resource_id = _id
            revision_id = f"{resource_id}:1"
            last_revision_id = None
            created_time = self.now_ctx.get()
            created_by = self.user_ctx.get()
            status = mode.status
            data_hash = self.get_data_hash(mode.data)

        elif isinstance(mode, _BuildRevInfoUpdate):
            prev_res_meta = mode.prev_res_meta
            resource_id = prev_res_meta.resource_id
            revision_id = f"{resource_id}:{prev_res_meta.total_revision_count + 1}"
            last_revision_id = prev_res_meta.current_revision_id
            created_time = self.now_ctx.get()
            created_by = self.user_ctx.get()
            status = mode.status
            data_hash = self.get_data_hash(mode.data)

        elif isinstance(mode, _BuildRevInfoModify):
            prev_info = mode.prev_info
            prev_res_meta = mode.prev_res_meta
            resource_id = prev_res_meta.resource_id
            revision_id = prev_res_meta.current_revision_id
            created_time = prev_info.created_time
            last_revision_id = prev_info.parent_revision_id
            created_by = prev_info.created_by
            status = mode.status
            if mode.status is UNSET:
                status = prev_info.status
            else:
                status = mode.status
            if mode.data is UNSET:
                data_hash = prev_info.data_hash
            else:
                data_hash = self.get_data_hash(mode.data)

        info = RevisionInfo(
            uid=uid,
            resource_id=resource_id,
            revision_id=revision_id,
            parent_revision_id=last_revision_id,
            schema_version=self._schema_version,
            data_hash=data_hash,
            status=status,
            created_time=created_time,
            updated_time=self.now_ctx.get(),
            created_by=created_by,
            updated_by=self.user_ctx.get(),
        )
        return info

    def _handle_event(self, context: EventContext) -> None:
        for eh in self.event_handlers:
            if eh.is_supported(context):
                eh.handle_event(context)

    def _get_meta_no_check_is_deleted(self, resource_id: str) -> ResourceMeta:
        if not self.storage.exists(resource_id):
            raise ResourceIDNotFoundError(resource_id)
        meta = self.storage.get_meta(resource_id)
        return meta

    def exists(self, resource_id: str) -> bool:
        return self.storage.exists(resource_id)

    def revision_exists(self, resource_id: str, revision_id: str) -> bool:
        return self.storage.revision_exists(resource_id, revision_id)

    @execute_with_events(
        (
            BeforeGetMeta,
            AfterGetMeta,
            OnSuccessGetMeta,
            OnFailureGetMeta,
        ),
        "meta",
    )
    def get_meta(self, resource_id: str) -> ResourceMeta:
        meta = self._get_meta_no_check_is_deleted(resource_id)
        if meta.is_deleted:
            raise ResourceIsDeletedError(resource_id)
        return meta

    def count_resources(self, query: ResourceMetaSearchQuery) -> int:
        return self.storage.count(query)

    @execute_with_events(
        (
            BeforeSearchResources,
            AfterSearchResources,
            OnSuccessSearchResources,
            OnFailureSearchResources,
        ),
        "results",
    )
    def search_resources(self, query: ResourceMetaSearchQuery) -> list[ResourceMeta]:
        return self.storage.search(query)

    @execute_with_events(
        (BeforeCreate, AfterCreate, OnSuccessCreate, OnFailureCreate),
        "info",
    )
    def create(
        self, data: T, *, status: RevisionStatus | UnsetType = UNSET
    ) -> RevisionInfo:
        status = self.default_status if status is UNSET else status
        info = self._rev_info(_BuildRevInfoCreate(data, status))
        self.storage.save_revision(info, io.BytesIO(self.encode(data)))
        self.storage.save_meta(self._res_meta(_BuildResMetaCreate(info, data)))
        return info

    @execute_with_events(
        (BeforeGet, AfterGet, OnSuccessGet, OnFailureGet),
        "resource",
    )
    def get(self, resource_id: str) -> Resource[T]:
        meta = self.get_meta(resource_id)
        return self.get_resource_revision(resource_id, meta.current_revision_id)

    @execute_with_events(
        (
            BeforeGetResourceRevision,
            AfterGetResourceRevision,
            OnSuccessGetResourceRevision,
            OnFailureGetResourceRevision,
        ),
        "resource",
    )
    def get_resource_revision(self, resource_id: str, revision_id: str) -> Resource[T]:
        info = self.storage.get_resource_revision_info(resource_id, revision_id)
        with self.storage.get_data_bytes(resource_id, revision_id) as data_io:
            data = self.decode(data_io.read())
        return Resource(info=info, data=data)

    @execute_with_events(
        (
            BeforeListRevisions,
            AfterListRevisions,
            OnSuccessListRevisions,
            OnFailureListRevisions,
        ),
        "revisions",
    )
    def list_revisions(self, resource_id: str) -> list[str]:
        return self.storage.list_revisions(resource_id)

    @execute_with_events(
        (BeforeUpdate, AfterUpdate, OnSuccessUpdate, OnFailureUpdate),
        "revision_info",
    )
    def update(
        self, resource_id: str, data: T, *, status: RevisionStatus | UnsetType = UNSET
    ) -> RevisionInfo:
        status = self.default_status if status is UNSET else status
        prev_res_meta = self.get_meta(resource_id)
        prev_info = self.storage.get_resource_revision_info(
            resource_id,
            prev_res_meta.current_revision_id,
        )
        rev_info = self._rev_info(_BuildRevInfoUpdate(prev_res_meta, data, status))
        if prev_info.data_hash == rev_info.data_hash:
            return prev_info
        res_meta = self._res_meta(_BuildResMetaUpdate(prev_res_meta, rev_info, data))
        self.storage.save_revision(rev_info, io.BytesIO(self.encode(data)))
        self.storage.save_meta(res_meta)
        return rev_info

    def create_or_update(
        self, resource_id, data, *, status: RevisionStatus | UnsetType = UNSET
    ):
        try:
            return self.update(resource_id, data, status=status)
        except ResourceIDNotFoundError:
            return self.create(data, status=status)

    @execute_with_events(
        (BeforeModify, AfterModify, OnSuccessModify, OnFailureModify),
        "revision_info",
    )
    def modify(
        self,
        resource_id: str,
        data: T | JsonPatch | UnsetType = UNSET,
        status: RevisionStatus | UnsetType = UNSET,
    ) -> RevisionInfo:
        if data is UNSET and status is not UNSET:
            return self._modify_status(resource_id, status)

        prev_res_meta = self.get_meta(resource_id)
        prev_info = self.storage.get_resource_revision_info(
            resource_id,
            prev_res_meta.current_revision_id,
        )
        if data is UNSET and status is UNSET:
            return prev_info
        if (
            prev_info.status != RevisionStatus.draft
            and status is not RevisionStatus.draft
        ):
            raise CannotModifyResourceError(resource_id)
        if type(data) is JsonPatch:
            data = self._apply_patch(resource_id, data)

        rev_info = self._rev_info(
            _BuildRevInfoModify(prev_res_meta, prev_info, data, status=status)
        )
        if prev_info.data_hash == rev_info.data_hash:
            return prev_info
        res_meta = self._res_meta(_BuildResMetaModify(prev_res_meta, rev_info, data))
        self.storage.save_revision(rev_info, io.BytesIO(self.encode(data)))
        self.storage.save_meta(res_meta)
        return rev_info

    def _modify_status(self, resource_id: str, status: RevisionStatus) -> RevisionInfo:
        prev_res_meta = self.get_meta(resource_id)
        prev_info = self.storage.get_resource_revision_info(
            resource_id,
            prev_res_meta.current_revision_id,
        )
        if prev_info.status == status:
            return prev_info
        rev_info = self._rev_info(
            _BuildRevInfoModify(prev_res_meta, prev_info, UNSET, status=status)
        )
        res_meta = self._res_meta(_BuildResMetaModify(prev_res_meta, rev_info, UNSET))
        with self.storage.get_data_bytes(
            resource_id, prev_res_meta.current_revision_id
        ) as data_io:
            self.storage.save_revision(rev_info, data_io)
        self.storage.save_meta(res_meta)
        return rev_info

    @execute_with_events(
        (BeforePatch, AfterPatch, OnSuccessPatch, OnFailurePatch),
        "revision_info",
        inputs={"patch_data": "patch_data.patch"},
    )
    def patch(self, resource_id: str, patch_data: JsonPatch) -> RevisionInfo:
        """
        Apply RFC 6902 JSON Patch operations to the resource.

        Arguments:
            - resource_id (str): the id of the resource to patch.
            - patch_data (JsonPatch): RFC 6902 JSON Patch operations to apply.

        Returns:
            - info (RevisionInfo): the metadata of the newly created revision.

        Raises:
            - ResourceIDNotFoundError: if resource id does not exist.
            - ResourceIsDeletedError: if resource is soft-deleted.
        """
        data = self._apply_patch(resource_id, patch_data)
        return self.update(resource_id, data)

    def _apply_patch(self, resource_id: str, patch_data: JsonPatch) -> T:
        data = self.get(resource_id).data
        d = self.data_converter.data_to_builtins(data)
        patch_data.apply(d, in_place=True)
        return self.data_converter.builtins_to_data(d)

    @execute_with_events(
        (BeforeSwitch, AfterSwitch, OnSuccessSwitch, OnFailureSwitch),
        "meta",
    )
    def switch(self, resource_id: str, revision_id: str) -> ResourceMeta:
        meta = self.get_meta(resource_id)
        if meta.current_revision_id == revision_id:
            return meta
        if not self.storage.revision_exists(resource_id, revision_id):
            raise RevisionIDNotFoundError(resource_id, revision_id)

        # 切換到指定版本時，需要更新索引數據
        if self._indexed_fields:
            with self.storage.get_data_bytes(resource_id, revision_id) as dataio:
                data = self.decode(dataio.read())
            meta.indexed_data = self._extract_indexed_values(data)

        meta.updated_by = self.user_ctx.get()
        meta.updated_time = self.now_ctx.get()
        meta.current_revision_id = revision_id
        self.storage.save_meta(meta)
        return meta

    @execute_with_events(
        (BeforeDelete, AfterDelete, OnSuccessDelete, OnFailureDelete),
        "meta",
    )
    def delete(self, resource_id: str) -> ResourceMeta:
        meta = self.get_meta(resource_id)
        meta.is_deleted = True
        meta.updated_by = self.user_ctx.get()
        meta.updated_time = self.now_ctx.get()
        self.storage.save_meta(meta)
        return meta

    @execute_with_events(
        (BeforeRestore, AfterRestore, OnSuccessRestore, OnFailureRestore),
        "meta",
    )
    def restore(self, resource_id: str) -> ResourceMeta:
        meta = self._get_meta_no_check_is_deleted(resource_id)
        if meta.is_deleted:
            meta.is_deleted = False
            meta.updated_by = self.user_ctx.get()
            meta.updated_time = self.now_ctx.get()
            self.storage.save_meta(meta)
        return meta

    @execute_with_events(
        (BeforeDump, AfterDump, OnSuccessDump, OnFailureDump),
        "result",
    )
    def dump(self) -> Generator[tuple[str, IO[bytes]]]:
        for meta in self.storage.dump_meta():
            yield (
                f"meta/{meta.resource_id}",
                io.BytesIO(self.meta_serializer.encode(meta)),
            )
        for info, data_io in self.storage.dump_resource():
            raw_res = self.resource_serializer.encode(
                RawResource(info=info, raw_data=data_io.read())
            )
            yield f"data/{info.uid}", io.BytesIO(raw_res)

    @execute_with_events(
        (BeforeLoad, AfterLoad, OnSuccessLoad, OnFailureLoad),
        lambda _: {},
        inputs={"bio": UNSET},
    )
    def load(self, key: str, bio: IO[bytes]) -> None:
        if key.startswith("meta/"):
            self.storage.save_meta(self.meta_serializer.decode(bio.read()))
        elif key.startswith("data/"):
            raw_res = self.resource_serializer.decode(bio.read())
            self.storage.save_revision(raw_res.info, io.BytesIO(raw_res.raw_data))

    @cached_property
    def meta_serializer(self):
        return MsgspecSerializer(encoding=Encoding.msgpack, resource_type=ResourceMeta)

    @cached_property
    def resource_serializer(self):
        return MsgspecSerializer(
            encoding=Encoding.msgpack,
            resource_type=RawResource,
        )
