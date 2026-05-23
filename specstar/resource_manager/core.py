import concurrent.futures
import datetime as dt
import inspect
import io
import json
import threading
import traceback
import warnings
from collections.abc import Callable, Generator, Iterable, Sequence
from contextlib import AbstractContextManager, ExitStack, contextmanager, suppress
from functools import cached_property, wraps
from typing import (
    IO,
    TYPE_CHECKING,
    Any,
    Generic,
    Literal,
    NamedTuple,
    TypedDict,
    TypeVar,
)
from uuid import uuid4

import more_itertools as mit
import msgspec
from jsonpatch import JsonPatch
from jsonpointer import JsonPointer
from msgspec import UNSET, Struct, UnsetType
from xxhash import xxh3_128_hexdigest

from specstar.events import (
    AfterCreate,
    AfterDelete,
    AfterDump,
    AfterGet,
    AfterGetMeta,
    AfterGetResourceRevision,
    AfterListRevisions,
    AfterLoad,
    AfterMigrate,
    AfterModify,
    AfterPatch,
    AfterPermanentlyDelete,
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
    BeforeMigrate,
    BeforeModify,
    BeforePatch,
    BeforePermanentlyDelete,
    BeforeRestore,
    BeforeSearchResources,
    BeforeSwitch,
    BeforeUpdate,
    EventContext,
    IEventHandler,
    OnFailureCreate,
    OnFailureDelete,
    OnFailureDump,
    OnFailureGet,
    OnFailureGetMeta,
    OnFailureGetResourceRevision,
    OnFailureListRevisions,
    OnFailureLoad,
    OnFailureMigrate,
    OnFailureModify,
    OnFailurePatch,
    OnFailurePermanentlyDelete,
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
    OnSuccessMigrate,
    OnSuccessModify,
    OnSuccessPatch,
    OnSuccessPermanentlyDelete,
    OnSuccessRestore,
    OnSuccessSearchResources,
    OnSuccessSwitch,
    OnSuccessUpdate,
)
from specstar.query_types import ResourceMetaSearchQuery
from specstar.resource_manager.partial import (
    classify_partial_fields,
    create_partial_type,
    filter_struct_partial,
    prune_object,
)
from specstar.resource_manager.pydantic_converter import (  # noqa: E402
    build_validator,
    pydantic_to_dict,
)
from specstar.types import (
    Binary,
    CannotModifyResourceError,
    DuplicateResourceError,
    IConstraintChecker,
    IMessageQueue,
    IMigration,
    IndexableField,
    IResourceManager,
    IValidator,
    MergePatch,
    OnDuplicate,
    PermissionDeniedError,
    RawResource,
    Resource,
    ResourceAction,
    ResourceIDNotFoundError,
    ResourceIsDeletedError,
    ResourceMeta,
    RevisionIDNotFoundError,
    RevisionInfo,
    RevisionNotMigratedError,
    RevisionStatus,
    SearchedResource,
    SpecialIndex,
    ValidationError,
)

if TYPE_CHECKING:
    from specstar.permission.checker import IPermissionChecker
    from specstar.schema import Schema

from specstar.permission.checker import PermissionResult
from specstar.query import Query
from specstar.resource_manager.basic import (
    Ctx,
    Encoding,
    IBlobStore,
    IMetaStore,
    IResourceStore,
    IStorage,
    MsgspecSerializer,
)
from specstar.resource_manager.binary_processor import BinaryProcessor
from specstar.resource_manager.dump_format import (
    BlobRecord,
    MetaRecord,
    RevisionRecord,
)
from specstar.util.naming import NameConverter, NamingFormat
from specstar.util.type_utils import (
    get_type_display_name,
)

T = TypeVar("T")


class IndexedValueExtractor:
    """從資源資料中提取需要索引的欄位值（Enum 會自動轉換為 value）"""

    def __init__(self, indexed_fields: list[IndexableField]):
        self.indexed_fields = indexed_fields

    def _convert_enum_to_value(self, value: Any) -> Any:
        """將 Enum 轉換為其值，但保留其他類型（如 datetime）"""
        from enum import Enum

        if isinstance(value, Enum):
            return value.value
        elif isinstance(value, list):
            return [self._convert_enum_to_value(v) for v in value]
        elif isinstance(value, dict):
            return {k: self._convert_enum_to_value(v) for k, v in value.items()}
        else:
            # 保留其他類型（datetime, int, str, etc.）
            return value

    def extract_indexed_values(self, data: Any) -> dict[str, Any]:
        """從 data 中提取需要索引的值，並將 Enum 轉換為其值"""

        indexed_data = {}
        for field in self.indexed_fields:
            value = UNSET
            if field.field_type == SpecialIndex.msgspec_tag:
                with suppress(Exception):
                    value = getattr(msgspec.inspect.type_info(type(data)), "tag", UNSET)
            else:
                # 使用 JSON path 提取值
                with suppress(Exception):
                    value = self._extract_by_path(data, field.field_path)

            if value is not UNSET:
                # 將 Enum 轉換為其值（但保留其他類型如 datetime）
                key = field.index_key or field.field_path
                indexed_data[key] = self._convert_enum_to_value(value)

        return indexed_data

    def _extract_by_path(self, data: Any, field_path: str) -> Any:
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

    def find_revision_schema_version(
        self, resource_id: str, revision_id: str
    ) -> str | None | UnsetType:
        """Find the most recent schema version stored for a revision.

        Returns the highest schema version if the revision exists, or
        ``UNSET`` if the revision was never stored.  Note that ``None``
        is a valid schema version (meaning "no schema configured").
        """
        try:
            versions = list(
                self._resource_store.list_schema_versions(resource_id, revision_id)
            )
        except KeyError:
            return UNSET
        if not versions:
            return UNSET
        # Return the highest (newest) schema version.
        # ``None`` means "no schema" and is always the lowest.
        non_none = [v for v in versions if v is not None]
        if non_none:
            return max(non_none)
        return None  # only None-keyed entry exists

    def get_meta(self, resource_id: str) -> ResourceMeta:
        return self._meta_store[resource_id]

    def save_meta(self, meta: ResourceMeta) -> None:
        self._meta_store[meta.resource_id] = meta

    def list_revisions(self, resource_id: str) -> list[str]:
        return list(self._resource_store.list_revisions(resource_id))

    def get_data_bytes(
        self,
        resource_id: str,
        revision_id: str,
        schema_version: str | None | UnsetType = UNSET,
    ) -> AbstractContextManager[IO[bytes]]:
        if schema_version is UNSET:
            meta = self.get_meta(resource_id)
            schema_version = meta.schema_version
        return self._resource_store.get_data_bytes(
            resource_id, revision_id, schema_version
        )

    def get_resource_revision_info(
        self,
        resource_id: str,
        revision_id: str,
        schema_version: str | None | UnsetType = UNSET,
    ) -> RevisionInfo:
        if schema_version is UNSET:
            meta = self.get_meta(resource_id)
            schema_version = meta.schema_version
        return self._resource_store.get_revision_info(
            resource_id, revision_id, schema_version
        )

    def save_revision(self, info: RevisionInfo, data: IO[bytes]) -> None:
        self._resource_store.save(info, data)

    def search(self, query: ResourceMetaSearchQuery) -> list[ResourceMeta]:
        return list(self._meta_store.iter_search(query))

    def iter_search(self, query: ResourceMetaSearchQuery) -> Generator[ResourceMeta]:
        yield from self._meta_store.iter_search(query)

    def count(self, query: ResourceMetaSearchQuery) -> int:
        return mit.ilen(self._meta_store.iter_search(query))

    def purge_meta(self, resource_id: str) -> None:
        """Hard-delete metadata for a resource (no soft-delete, no event hooks).

        Used as a compensating action for unique-constraint race-condition
        rollback.  Removes the entry from the meta store directly.
        """
        del self._meta_store[resource_id]

    def purge_resource(self, resource_id: str) -> None:
        """Hard-delete metadata and all revision data for a resource.

        Used by ``permanently_delete`` to physically remove all traces of a
        resource from storage.
        """
        del self._meta_store[resource_id]
        self._resource_store.purge_resource(resource_id)

    def dump_meta(
        self, resource_ids: frozenset[str] | None = None
    ) -> Generator[ResourceMeta]:
        if resource_ids is None:
            yield from self._meta_store.values()
        else:
            for rid in resource_ids:
                if rid in self._meta_store:
                    yield self._meta_store[rid]

    def dump_resource(
        self, resource_id: str
    ) -> Generator[tuple[RevisionInfo, IO[bytes]]]:
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

    def dump_resources_bulk(
        self, resource_ids: frozenset[str] | None = None
    ) -> dict[str, list[tuple[RevisionInfo, bytes]]] | None:
        """Bulk pre-fetch all revisions (concurrent when supported).

        Returns ``None`` when the underlying resource store does not
        provide a bulk dump method, signalling the caller to fall back
        to per-resource streaming via :meth:`dump_resource`.
        """
        return self._resource_store.dump_all_revisions(resource_ids=resource_ids)

    # ------------------------------------------------------------------
    # Bulk load helpers
    # ------------------------------------------------------------------

    def save_metas_bulk(self, metas: list["ResourceMeta"]) -> None:
        """Bulk save multiple metas.

        Uses the underlying meta store's ``save_many`` when available
        (e.g. PostgreSQL ``execute_batch``); otherwise falls back to
        sequential ``__setitem__`` calls.
        """
        if not metas:
            return
        self._meta_store.save_many(metas)

    def save_revisions_bulk(self, items: list[tuple[RevisionInfo, bytes]]) -> None:
        """Bulk save multiple revisions.

        Uses the underlying resource store's ``save_many`` when
        available (e.g. concurrent S3 PUTs); otherwise falls back to
        sequential :meth:`save` calls.
        """
        if not items:
            return
        self._resource_store.save_many(items)


class _BlobEntry(Struct, kw_only=True):
    """Internal struct for serialising blob data in dump streams."""

    file_id: str
    data: bytes
    size: int
    content_type: str


class _BuildRevInfoCreate(Struct, Generic[T]):
    data: T
    status: RevisionStatus = RevisionStatus.stable


class _BuildRevInfoUpdate(Struct, Generic[T]):
    prev_res_meta: ResourceMeta
    data: T
    status: RevisionStatus = RevisionStatus.stable


class _BuildRevInfoModify(Struct, Generic[T]):
    prev_res_meta: ResourceMeta
    prev_info: RevisionInfo
    data: T | UnsetType
    status: RevisionStatus | UnsetType = RevisionStatus.stable


class _BuildResMetaCreate(Struct, Generic[T]):
    rev_info: RevisionInfo
    data: T


class _BuildResMetaUpdate(Struct, Generic[T]):
    prev_res_meta: ResourceMeta
    rev_info: RevisionInfo
    data: T


class _BuildResMetaModify(Struct, Generic[T]):
    prev_res_meta: ResourceMeta
    rev_info: RevisionInfo
    data: T | UnsetType


class _Contexts(NamedTuple):
    # Each entry is one of the 64 event-context Struct *classes*; we
    # construct via ``contexts.before(**inputs_)`` etc. ty can't
    # statically validate the dict-spread against the specific
    # constructor signature, so we widen to ``Any``.
    before: Any
    after: Any
    on_success: Any
    on_failure: Any


class _LoadCtxKw(TypedDict):
    """Common kwargs shared by every Load event context constructor."""

    user: str | UnsetType
    now: dt.datetime | UnsetType
    resource_name: str
    record_type: str


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


def _rfc7386_merge(target, patch):
    """Apply an RFC 7386 JSON Merge Patch to ``target`` and return the result.

    A non-object patch replaces the target wholesale; ``null`` values delete the
    corresponding key; nested objects merge recursively.
    """
    if not isinstance(patch, dict):
        return patch
    result = dict(target) if isinstance(target, dict) else {}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict):
            result[key] = _rfc7386_merge(result.get(key), value)
        else:
            result[key] = value
    return result


def coerce_data_to_resource_type(func):
    """Decorator that coerces the ``data`` argument to the resource Struct type
    **before** the wrapped function (and therefore before any event handlers)
    executes.  Applied as the *outermost* decorator so that
    ``@execute_with_events`` passes already-coerced data to event contexts.
    """

    @wraps(func)
    def wrapper(self: "ResourceManager", *args, **kwargs):
        sig = inspect.signature(func)
        bound = sig.bind(self, *args, **kwargs)
        bound.apply_defaults()
        data_arg = bound.arguments.get("data")
        if data_arg is not None and data_arg is not UNSET:
            bound.arguments["data"] = self._coerce_data(data_arg)
        # Re-pack into positional + keyword
        new_args = tuple(bound.args[1:])  # strip self
        return func(self, *new_args, **bound.kwargs)

    return wrapper


def execute_with_events(
    contexts: "_Contexts | tuple[Any, Any, Any, Any]",
    result: str | Callable[[Any], dict[str, Any]],
    *,
    inputs: dict[str, str | UnsetType] | None = None,
    context_aware: bool = False,
):
    contexts = _Contexts(*contexts)
    if isinstance(result, str):

        def _build_result(x):
            return {result: x}

    else:
        _build_result = result

    # Names of the context kwargs that context_aware methods accept.
    _CTX_KWARGS = ("user", "now", "resource_id")

    def wrapper(func):
        sig = inspect.signature(func)

        @wraps(func)
        def wrapped(self: "ResourceManager", *args, **kwargs):
            bound_args = sig.bind(self, *args, **kwargs)
            bound_args.apply_defaults()  # 應用默認值

            func_inputs = dict(bound_args.arguments)
            del func_inputs["self"]

            # ── context_aware: push explicit kwargs into ContextVar ──
            if context_aware:
                stack = ExitStack()
                ctx_user = func_inputs.get("user", UNSET)
                ctx_now = func_inputs.get("now", UNSET)
                ctx_rid = func_inputs.get("resource_id", UNSET)
                if ctx_user is not UNSET:
                    stack.enter_context(self.user_ctx.ctx(ctx_user))
                if ctx_now is not UNSET:
                    stack.enter_context(self.now_ctx.ctx(ctx_now))
                if ctx_rid is not UNSET:
                    stack.enter_context(self.id_ctx.ctx(ctx_rid))
            else:
                stack = None

            # Strip context-only kwargs from func_inputs so they don't
            # leak into event contexts as raw UNSET values.  A kwarg is
            # "context-only" when its default is UNSET in the function
            # signature (user, now, and — for create — resource_id).
            # Positional parameters with the same name (e.g. resource_id
            # in update/delete) must be preserved for event payloads.
            if context_aware:
                for name in ("user", "now", "resource_id"):
                    param = sig.parameters.get(name)
                    if param is not None and param.default is UNSET:
                        func_inputs.pop(name, None)

            try:
                if stack is not None:
                    stack.__enter__()

                # Strict mode validation (after ContextVar push)
                if context_aware and self._strict_operation_context:
                    self._validate_write_context(func.__name__)

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
            finally:
                if stack is not None:
                    stack.__exit__(None, None, None)

        return wrapped

    return wrapper


class ResourceOps(Generic[T]):
    """Context-capturing proxy returned by :meth:`ResourceManager.using`.

    ``ResourceOps`` captures ``user``, ``now``, and ``resource_id`` at
    creation time.  Each method call **re-applies** these values via the
    manager's context system, ensuring that multiple ``ResourceOps``
    instances created from the same manager do not interfere with each
    other.

    This enables the *multiple using()* pattern::

        with mgr.using(user="u1") as op1, mgr.using(user="u2") as op2:
            op1.create(data1)  # created_by = "u1"
            op2.create(data2)  # created_by = "u2"

    After the ``with`` block exits, or if an exception propagates, the
    proxy is **deactivated** and any subsequent method call raises
    :class:`RuntimeError`.

    Note:
        Calling ``op.using(...)`` or ``op.meta_provide(...)`` is
        forbidden and raises :class:`RuntimeError`.
    """

    __slots__ = ("_mgr", "_user", "_now", "_resource_id", "_active")

    def __init__(
        self,
        mgr: "IResourceManager[T]",
        user: "str | UnsetType",
        now: "dt.datetime | UnsetType",
        resource_id: "str | UnsetType",
    ) -> None:
        object.__setattr__(self, "_mgr", mgr)
        object.__setattr__(self, "_user", user)
        object.__setattr__(self, "_now", now)
        object.__setattr__(self, "_resource_id", resource_id)
        object.__setattr__(self, "_active", True)

    def _deactivate(self) -> None:
        """Mark this proxy as inactive (called automatically on context exit)."""
        object.__setattr__(self, "_active", False)

    def __getattr__(self, name: str) -> Any:
        if name in ("using", "meta_provide"):
            raise RuntimeError("Cannot rebind context through ResourceOps")
        if not self._active:
            raise RuntimeError("ResourceOps is no longer active")
        attr = getattr(self._mgr, name)
        if inspect.ismethod(attr):

            @wraps(attr)
            def _wrapper(*args: Any, **kwargs: Any) -> Any:
                if not self._active:
                    raise RuntimeError("ResourceOps is no longer active")
                with self._mgr._apply_context(
                    self._user, self._now, resource_id=self._resource_id
                ):
                    return attr(*args, **kwargs)

            return _wrapper
        return attr

    if TYPE_CHECKING:
        # -- Stubs for IDE auto-complete / type checking --
        def create(
            self,
            data: T,
            *,
            status: RevisionStatus | UnsetType = ...,
            user: str | UnsetType = ...,
            now: dt.datetime | UnsetType = ...,
            resource_id: str | UnsetType = ...,
        ) -> RevisionInfo: ...
        def update(
            self,
            resource_id: str,
            data: T,
            *,
            user: str | UnsetType = ...,
            now: dt.datetime | UnsetType = ...,
        ) -> RevisionInfo: ...
        def create_or_update(
            self,
            resource_id: str,
            data: T,
            *,
            user: str | UnsetType = ...,
            now: dt.datetime | UnsetType = ...,
        ) -> RevisionInfo: ...
        def get(
            self,
            resource_id: str,
            *,
            revision_id: str | UnsetType = ...,
            schema_version: str | None | UnsetType = ...,
        ) -> Resource[T]: ...
        def get_partial(
            self,
            resource_id: str,
            revision_id: str,
            partial: Iterable[str | JsonPointer],
        ) -> Struct: ...
        def get_revision_info(
            self,
            resource_id: str,
            revision_id: str | UnsetType = ...,
        ) -> RevisionInfo: ...
        def get_resource_revision(
            self,
            resource_id: str,
            revision_id: str,
            schema_version: str | None | UnsetType = ...,
        ) -> Resource[T]: ...
        def list_revisions(self, resource_id: str) -> list[str]: ...
        def get_meta(
            self, resource_id: str, include_deleted: bool = ...
        ) -> ResourceMeta: ...
        def exists(self, resource_id: str) -> bool: ...
        def revision_exists(self, resource_id: str, revision_id: str) -> bool: ...
        def count_resources(self, query: ResourceMetaSearchQuery) -> int: ...
        def search_resources(
            self, query: ResourceMetaSearchQuery
        ) -> list[ResourceMeta]: ...
        def list_resources(
            self,
            query: ResourceMetaSearchQuery,
            *,
            returns: list[str] | None = ...,
            partial: list[str] | None = ...,
        ) -> list[SearchedResource[T]]: ...
        def modify(
            self,
            resource_id: str,
            data: T | JsonPatch | UnsetType = ...,
            status: RevisionStatus | UnsetType = ...,
            *,
            user: str | UnsetType = ...,
            now: dt.datetime | UnsetType = ...,
        ) -> RevisionInfo: ...
        def patch(
            self,
            resource_id: str,
            patch_data: JsonPatch,
            *,
            user: str | UnsetType = ...,
            now: dt.datetime | UnsetType = ...,
        ) -> RevisionInfo: ...
        def switch(
            self,
            resource_id: str,
            revision_id: str,
            *,
            user: str | UnsetType = ...,
            now: dt.datetime | UnsetType = ...,
        ) -> ResourceMeta: ...
        def delete(
            self,
            resource_id: str,
            *,
            user: str | UnsetType = ...,
            now: dt.datetime | UnsetType = ...,
        ) -> ResourceMeta: ...
        def restore(
            self,
            resource_id: str,
            *,
            user: str | UnsetType = ...,
            now: dt.datetime | UnsetType = ...,
        ) -> ResourceMeta: ...
        def permanently_delete(
            self,
            resource_id: str,
            *,
            user: str | UnsetType = ...,
            now: dt.datetime | UnsetType = ...,
        ) -> ResourceMeta: ...
        def migrate(
            self,
            resource_id: str,
            *,
            revision_id: str | UnsetType = ...,
        ) -> ResourceMeta: ...
        def get_blob(self, file_id: str) -> Binary: ...
        def get_blob_url(self, file_id: str) -> str | None: ...


class ResourceManager(IResourceManager[T], Generic[T]):
    def __init__(
        self,
        resource_type: type[T],
        *,
        storage: IStorage,
        blob_store: IBlobStore | None = None,
        message_queue: Callable[["IResourceManager[T]"], IMessageQueue] | None = None,
        id_generator: Callable[[], str] | None = None,
        migration: "IMigration[T] | Schema[T] | None" = None,
        indexed_fields: list[IndexableField] | None = None,
        permission_checker: "IPermissionChecker | None" = None,
        name: str | NamingFormat = NamingFormat.SNAKE,
        event_handlers: Sequence[IEventHandler] | None = None,
        encoding: Encoding = Encoding.json,
        default_status: RevisionStatus = RevisionStatus.stable,
        default_user: str | Callable[[], str] | UnsetType = UNSET,
        default_now: Callable[[], dt.datetime] | UnsetType = UNSET,
        validator: "Callable[[T], None] | IValidator | type | None" = None,
        pydantic_type: type | None = None,
        constraint_checkers: "Sequence[IConstraintChecker | Callable[[ResourceManager], IConstraintChecker]] | None" = None,
        strict_operation_context: bool = False,
        forbid_unknown_fields: bool = False,
        encoder_registry: "Any | None" = None,
        vector_encoders: "dict[str, str | Callable] | None" = None,
    ):
        """Initialize a ResourceManager.


        Args:
        strict_operation_context (bool):
            Whether strict operation context validation is enabled.

            When ``True``, write operations (create, update, delete, etc.) will
            raise :class:`MissingOperationContextError` if required context
            fields (``user``, ``now``) are not fully resolved from any source
            (explicit kwargs, ``using()`` scope, or manager defaults).
        forbid_unknown_fields (bool):
            When ``True``, ``create()`` / ``update()`` / ``modify()`` reject
            dict inputs (or Pydantic instances) carrying keys that are not
            declared on the resource ``Struct``, raising
            :class:`specstar.types.ValidationError`. Defaults to ``False`` —
            unknown keys are silently dropped, matching msgspec's default.
        """
        self._pydantic_type = pydantic_type
        self._strict_operation_context = strict_operation_context
        self._forbid_unknown_fields = forbid_unknown_fields

        # ── Resolve Schema vs legacy migration/validator ──────────────
        from specstar.schema import Schema as _Schema

        if isinstance(migration, _Schema):
            self._schema = migration
            # Extract validator from Schema if present and no explicit validator
            if migration.has_validator and validator is None:
                validator = migration._validator  # already normalized callable
            # Use Schema as migration if it has migration steps
            migration_obj = migration if migration.has_migration else None
        elif isinstance(migration, IMigration):
            self._schema = _Schema.from_legacy(migration)
            migration_obj = self._schema
        elif migration is None:
            self._schema = None
            migration_obj = None
        else:
            raise TypeError(
                f"migration must be Schema, IMigration, or None, got {type(migration).__name__}"
            )

        self.user_ctx: Ctx[str]
        self.now_ctx: Ctx[dt.datetime]
        if default_user is UNSET:
            self.user_ctx = Ctx("user_ctx", strict_type=str)
        elif isinstance(default_user, str):
            self.user_ctx = Ctx("user_ctx", strict_type=str, default=default_user)
        else:
            self.user_ctx = Ctx(
                "user_ctx",
                strict_type=str,
                default_factory=default_user,
            )
        if default_now is UNSET:
            self.now_ctx = Ctx("now_ctx", strict_type=dt.datetime)
        else:
            self.now_ctx = Ctx(
                "now_ctx", strict_type=dt.datetime, default_factory=default_now
            )
        self.id_ctx = Ctx[str | UnsetType]("id_ctx", default=UNSET)
        self._resource_type = resource_type
        self.storage = storage
        self.blob_store = blob_store

        # Set resource_name early because message_queue initialization may need it
        if isinstance(name, NamingFormat):
            self._resource_name = NameConverter(
                get_type_display_name(resource_type)
            ).to(
                NamingFormat.SNAKE,
            )
        else:
            self._resource_name = name

        schema_version = (
            self._schema.schema_version if self._schema is not None else None
        )
        self._schema_version = schema_version
        self._indexed_fields = indexed_fields or []
        self._indexed_value_extractor = IndexedValueExtractor(self._indexed_fields)
        self._migration = self._schema if self._schema is not None else migration_obj
        self._encoding = encoding
        # Sync encoding to Schema so multi-step migrations re-encode
        # intermediate results in the correct format (json vs msgpack).
        if self._schema is not None:
            self._schema.set_encoding(encoding)
        self._data_serializer = MsgspecSerializer(
            encoding=encoding,
            resource_type=resource_type,
        )
        self.default_status = default_status

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

        # Constraint checkers（放在最後，在 PermissionEventHandler 之後執行）
        from specstar.resource_manager.constraint_lifecycle import (
            build_constraint_handler,
        )

        self._constraint_handler = build_constraint_handler(self, constraint_checkers)
        if self._constraint_handler is not None:
            self.event_handlers.append(self._constraint_handler)

        self._binary_processor = BinaryProcessor(resource_type)

        # ── Vector / Embedding ────────────────────────────────────────────
        from specstar.resource_manager.embedding_processor import EmbeddingProcessor
        from specstar.resource_manager.encoder_registry import EncoderRegistry

        self._encoder_registry = encoder_registry or EncoderRegistry()
        self._vector_encoders = vector_encoders or {}
        self._embedding_processor = EmbeddingProcessor(
            resource_type,
            self._encoder_registry,
            model_overrides=self._vector_encoders,
        )

        # Set up validator
        self._validator = build_validator(validator)

        # Message queue is provided as a factory callable
        if message_queue is not None:
            self.message_queue = message_queue(self)
        else:
            self.message_queue = None

        # Reverse mapping filled by SpecStar._register_async_job_models().
        # Maps job resource name → job ResourceManager for async create actions
        # that target this resource.
        self._async_create_job_rms: dict[str, "IResourceManager"] = {}

        # Reverse mapping filled by SpecStar._register_async_update_job_models().
        # Maps job resource name → job ResourceManager for async update actions
        # that target this resource.
        self._async_update_job_rms: dict[str, "IResourceManager"] = {}

    def register_async_create_job(
        self, job_resource_name: str, job_rm: "IResourceManager"
    ) -> None:
        """Register an async create-job ResourceManager for this resource.

        Called by :meth:`SpecStar._register_async_job_models` to populate the
        reverse mapping so that :meth:`start_consume` can locate child job
        consumers via ``custom_creation``.

        Args:
            job_resource_name: The registered name of the Job resource.
            job_rm: The :class:`ResourceManager` instance for the Job resource.

        Raises:
            ValueError: If *job_resource_name* is already registered.
        """
        if job_resource_name in self._async_create_job_rms:
            raise ValueError(
                f"Async create-job '{job_resource_name}' is already registered "
                f"on resource '{self.resource_name}'."
            )
        self._async_create_job_rms[job_resource_name] = job_rm

    @property
    def async_create_job_names(self) -> list[str]:
        """Return the names of all registered async create-job resources.

        Returns:
            A list of job resource names registered via
            :meth:`register_async_create_job`.
        """
        return list(self._async_create_job_rms.keys())

    def register_async_update_job(
        self, job_resource_name: str, job_rm: "ResourceManager"
    ) -> None:
        """Register an async update-job ResourceManager for this resource.

        Called by :meth:`SpecStar._register_async_update_job_models` to
        populate the reverse mapping so that consumers can locate child
        job resources.

        Args:
            job_resource_name: The registered name of the Job resource.
            job_rm: The :class:`ResourceManager` instance for the Job resource.

        Raises:
            ValueError: If *job_resource_name* is already registered.
        """
        if job_resource_name in self._async_update_job_rms:
            raise ValueError(
                f"Async update-job '{job_resource_name}' is already registered "
                f"on resource '{self.resource_name}'."
            )
        self._async_update_job_rms[job_resource_name] = job_rm

    @property
    def async_update_job_names(self) -> list[str]:
        """Return the names of all registered async update-job resources.

        Returns:
            A list of job resource names registered via
            :meth:`register_async_update_job`.
        """
        return list(self._async_update_job_rms.keys())

    def encode(self, data: T) -> bytes:
        return self._data_serializer.encode(data)

    def decode(self, data: bytes) -> T:
        return self._data_serializer.decode(data)

    def _decode_and_validate(self, data: bytes) -> None:
        return self._data_serializer.decode_and_validate(data)

    def _run_validator(self, data: T) -> None:
        """Run the custom validator on the data if one is configured."""
        if self._validator is not None:
            try:
                self._validator(data)
            except ValidationError:
                raise
            except Exception as e:
                raise ValidationError(str(e)) from e

    def _coerce_data(self, data: Any) -> T:
        """Coerce data to the resource Struct type.

        Accepts:
        - msgspec Struct instance → returned as-is
        - dict → converted via msgspec.convert
        - Pydantic BaseModel instance (when pydantic_type is set)
          → model_dump() → msgspec.convert

        When ``forbid_unknown_fields`` is set on the manager, dict / Pydantic
        inputs carrying keys outside the resource ``Struct``'s declared
        top-level fields raise :class:`ValidationError` instead of having
        those keys silently dropped by ``msgspec.convert``.

        This allows Pydantic users to pass native Pydantic instances
        or plain dicts without knowing about msgspec.
        """
        if data is UNSET or type(data) is JsonPatch or type(data) is MergePatch:
            return data
        if isinstance(data, Struct):
            return data
        if isinstance(data, dict):
            if self._forbid_unknown_fields:
                self._check_no_unknown_fields(data)
            return msgspec.convert(data, self._resource_type)
        # Accept Pydantic instance when RM was configured with pydantic_type
        if self._pydantic_type is not None and isinstance(data, self._pydantic_type):
            as_dict = pydantic_to_dict(data)
            if self._forbid_unknown_fields:
                self._check_no_unknown_fields(as_dict)
            return msgspec.convert(as_dict, self._resource_type)
        return data

    def _check_no_unknown_fields(self, data: dict) -> None:
        """Raise :class:`ValidationError` if ``data`` carries keys outside the
        resource ``Struct``'s top-level fields.

        Top-level only — nested ``Struct`` fields still rely on msgspec's
        default permissive behavior. This catches the common typo case
        without imposing deep-walk overhead on every write.
        """
        try:
            allowed = {f.name for f in msgspec.structs.fields(self._resource_type)}
        except TypeError:
            return
        extra = [k for k in data.keys() if k not in allowed]
        if extra:
            raise ValidationError(
                f"Unknown field(s) for {self._resource_type.__name__}: "
                f"{sorted(extra)}. Allowed fields: {sorted(allowed)}"
            )

    @property
    def pydantic_type(self) -> type | None:
        """The original Pydantic model class, if this RM was created from one."""
        return self._pydantic_type

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
    def migrate(
        self,
        resource_id: str,
        *,
        revision_id: str | UnsetType = UNSET,
    ) -> ResourceMeta:
        """
        Migrate a resource to the latest schema version.

        When *revision_id* is ``UNSET`` (the default), the **current**
        revision (``meta.current_revision_id``) is migrated and
        ``meta.schema_version`` is updated accordingly.

        When *revision_id* is provided, only **that specific revision**
        is migrated.  ``meta.schema_version`` is **not** changed (it
        should already be at the latest version from migrating the
        current revision first).

        Arguments:
            resource_id (str): The ID of the resource to migrate.
            revision_id (str | UnsetType): Optional. A specific revision
                to migrate. If ``UNSET``, migrates the current revision.

        Returns:
            meta (ResourceMeta): The (possibly updated) metadata after migration.

        Raises:
            ValueError: If migration logic is not configured.
            ResourceIDNotFoundError: If the resource ID does not exist.
            RevisionIDNotFoundError: If *revision_id* does not exist.
        """
        if self._migration is None:
            raise ValueError("Migration is not set for this resource manager")

        meta = self._get_meta_no_check_is_deleted(resource_id)

        if revision_id is UNSET:
            # --- Migrate the current revision (original behaviour) ---
            target_rev = meta.current_revision_id
            actual_sv = meta.schema_version
        else:
            # --- Migrate a specific (possibly non-current) revision ---
            target_rev = revision_id
            actual_sv = self.storage.find_revision_schema_version(
                resource_id, target_rev
            )
            if actual_sv is UNSET:
                raise RevisionIDNotFoundError(resource_id, target_rev)

        info = self.storage.get_resource_revision_info(
            resource_id, target_rev, schema_version=actual_sv
        )

        # 檢查是否需要遷移
        if info.schema_version == self._migration.schema_version:
            return meta

        # 執行數據遷移
        with self.storage.get_data_bytes(
            resource_id, target_rev, schema_version=actual_sv
        ) as data_io:
            migrated_data = self._migration.migrate(data_io, info.schema_version)

        # 更新 resource info 的 schema_version
        info.parent_schema_version = info.schema_version
        info.schema_version = self._migration.schema_version

        if revision_id is UNSET:
            # Only update meta-level schema_version when migrating *current* revision
            meta.schema_version = self._migration.schema_version
            meta.indexed_data = self._extract_indexed_values(migrated_data)
            self.storage.save_meta(meta)

        self.storage.save_revision(info, io.BytesIO(self.encode(migrated_data)))

        return meta

    def backfill_revision_meta(self) -> int:
        """Populate ``ResourceMeta.rev_*`` for resources created before this feature.

        Iterates every resource currently in the meta store; for each one
        whose ``rev_status`` is still ``UNSET`` (i.e. the resource was
        created on a release that did not yet embed current-revision info),
        loads the current ``RevisionInfo`` from the resource store and
        copies its ``status`` / ``created_by`` / ``updated_by`` /
        ``created_time`` / ``updated_time`` into the meta, then saves it.

        Returns:
            int: The number of resources that were updated.

        Notes:
            This is opt-in (not auto-run on startup) because for very
            large stores it can be expensive — every backfilled resource
            triggers a read against ``IResourceStore``.  Run it once
            after upgrading.
        """
        updated = 0
        # Snapshot the metas first so an update half-way through doesn't
        # disturb the iterator (some meta stores are dict-backed).
        for meta in list(self.storage.dump_meta()):
            if meta.rev_status is not UNSET:
                continue
            try:
                info = self.storage.get_resource_revision_info(
                    meta.resource_id,
                    meta.current_revision_id,
                    schema_version=meta.schema_version,
                )
            except Exception:
                # Skip resources whose current revision cannot be read —
                # the caller can investigate them separately.
                continue
            meta.rev_status = info.status
            meta.rev_created_by = info.created_by
            meta.rev_updated_by = info.updated_by
            meta.rev_created_time = info.created_time
            meta.rev_updated_time = info.updated_time
            self.storage.save_meta(meta)
            updated += 1
        return updated

    @property
    def resource_name(self):
        return self._resource_name

    @property
    def strict_operation_context(self) -> bool:
        """Whether strict operation context validation is enabled."""
        return self._strict_operation_context

    @property
    def indexed_fields(self) -> list[IndexableField]:
        """取得被索引的 data 欄位列表"""
        return self._indexed_fields

    def add_indexed_field(self, field: IndexableField) -> None:
        """新增一個索引欄位並重建 extractor。

        如果該欄位已存在（依 ``field_path`` 判斷），則不重複新增。
        """
        existing = {f.field_path for f in self._indexed_fields}
        if field.field_path not in existing:
            self._indexed_fields.append(field)
            self._indexed_value_extractor = IndexedValueExtractor(self._indexed_fields)

    def _extract_indexed_values(self, data: T) -> dict[str, Any]:
        """從 data 中提取需要索引的值（保留原始類型，Enum 會在序列化時轉換）"""
        return self._indexed_value_extractor.extract_indexed_values(data)

    def _load_revision_data(
        self,
        resource_id: str,
        revision_id: str,
        schema_version: str | None | UnsetType = UNSET,
    ) -> T:
        """Load and decode data for a specific revision."""
        with self.storage.get_data_bytes(
            resource_id, revision_id, schema_version=schema_version
        ) as data_io:
            return self.decode(data_io.read())

    @contextmanager
    def using(
        self,
        user: str | UnsetType = UNSET,
        now: dt.datetime | UnsetType = UNSET,
        *,
        resource_id: str | UnsetType = UNSET,
    ) -> Generator[ResourceOps[T], None, None]:
        """Context manager to provide operation context for write operations.

        Returns a :class:`ResourceOps` proxy that **captures** the supplied
        ``user``, ``now``, and ``resource_id`` values.  Each method call on
        the proxy re-applies its captured context, so multiple proxies
        created from the same manager do not interfere with each other.

        Resolution order (highest to lowest priority):
            1. Explicit keyword arguments on the method call
            2. Active ``using()`` scope (via the :class:`ResourceOps` proxy)
            3. Manager defaults (``default_user``, ``default_now``)

        Args:
            user: The user performing the action.
            now: The current timestamp.
            resource_id: Specific resource ID to use for ``create()``.

        Yields:
            ResourceOps[T]: A context-capturing proxy.  Calling methods
                on it is equivalent to calling them on the manager with
                the captured context.

        Example::

            # Single context
            with mgr.using(user="alice", now=datetime.now()) as op:
                op.create(data1)
                op.update(rid, data2)

            # Multiple contexts (safe — each proxy has its own capture)
            with (
                mgr.using(user="u1", now=now) as op1,
                mgr.using(user="u2", now=now) as op2,
            ):
                op1.create(data1)  # created_by = "u1"
                op2.create(data2)  # created_by = "u2"
        """
        ops = ResourceOps(self, user, now, resource_id)
        with self._apply_context(user=user, now=now, resource_id=resource_id):
            try:
                yield ops
            finally:
                ops._deactivate()

    @contextmanager
    def meta_provide(
        self,
        user: str | UnsetType = UNSET,
        now: dt.datetime | UnsetType = UNSET,
        *,
        resource_id: str | UnsetType = UNSET,
    ):
        """Context manager to provide metadata context (user, time, resource_id).

        .. deprecated::
            Use :meth:`using` instead.  ``meta_provide`` will be removed
            in a future release.

        Arguments:
            user (str, optional): The user performing the action.
            now (datetime, optional): The current timestamp.
            resource_id (str, optional): Specific resource ID to use.
        """
        warnings.warn(
            "meta_provide() is deprecated, use using() instead",
            DeprecationWarning,
            stacklevel=2,
        )
        with self.using(user, now, resource_id=resource_id):
            yield

    @contextmanager
    def _apply_context(
        self,
        user: str | UnsetType = UNSET,
        now: dt.datetime | UnsetType = UNSET,
        *,
        resource_id: str | UnsetType = UNSET,
    ):
        """Internal context manager — same as using() but without yielding self."""
        with (
            self.user_ctx.ctx(user) if user is not UNSET else suppress(),
            self.now_ctx.ctx(now) if now is not UNSET else suppress(),
            self.id_ctx.ctx(resource_id) if resource_id is not UNSET else suppress(),
        ):
            yield

    def _validate_write_context(self, method_name: str | None = None) -> None:
        """Validate that required context fields are available for write ops."""
        from specstar.types import MissingOperationContextError

        missing: list[str] = []
        if self.user_or_unset is UNSET:
            missing.append("user")
        if self.now_or_unset is UNSET:
            missing.append("now")
        if missing:
            raise MissingOperationContextError(missing, method_name)

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

        # rev_* fields mirror the now-current ``RevisionInfo`` so that
        # search/sort by *current revision* attributes does not require an
        # extra read against ``IResourceStore``.
        rev_info = mode.rev_info
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
            rev_status=rev_info.status,
            rev_created_by=rev_info.created_by,
            rev_updated_by=rev_info.updated_by,
            rev_created_time=rev_info.created_time,
            rev_updated_time=rev_info.updated_time,
        )

    def get_data_hash(self, data: T) -> str:
        b = self.encode(data)
        self._decode_and_validate(b)  # 確保可解碼
        self._run_validator(data)  # 執行自訂驗證
        data_hash = f"xxh3_128:{xxh3_128_hexdigest(b)}"
        return data_hash

    def _process_binary_fields(self, data: Any) -> Any:
        return self._binary_processor.process(data, self.blob_store)

    def restore_binary(self, data: T) -> T:
        """
        還原 data 中的 binary.data (如果是從 blob store 讀取).
        這對於需要讀取 Binary 原始資料時很有用.
        """
        return self._binary_processor.restore(data, self.blob_store)

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
        """
        Check if a resource exists.

        Arguments:
            resource_id (str): The ID of the resource to check.

        Returns:
            bool: True if the resource exists, False otherwise.
        """
        return self.storage.exists(resource_id)

    def revision_exists(self, resource_id: str, revision_id: str) -> bool:
        """
        Check if a specific revision of a resource exists.

        Arguments:
            resource_id (str): The ID of the resource.
            revision_id (str): The revision ID to check.

        Returns:
            bool: True if the revision exists, False otherwise.
        """
        return self.storage.revision_exists(resource_id, revision_id)

    @execute_with_events(
        (
            BeforeGetMeta,
            AfterGetMeta,
            OnSuccessGetMeta,
            OnFailureGetMeta,
        ),
        "meta",
        inputs={"include_deleted": UNSET},
    )
    def get_meta(self, resource_id: str, include_deleted: bool = False) -> ResourceMeta:
        """
        Get the metadata of a resource.

        Arguments:
            resource_id (str): The ID of the resource.
            include_deleted (bool): If True, return metadata even for
                soft-deleted resources. Defaults to False.

        Returns:
            meta (ResourceMeta): The metadata object.

        Raises:
            ResourceIDNotFoundError: If the resource ID does not exist.
            ResourceIsDeletedError: If the resource has been soft-deleted
                and *include_deleted* is False.
        """
        meta = self._get_meta_no_check_is_deleted(resource_id)
        if meta.is_deleted and not include_deleted:
            raise ResourceIsDeletedError(resource_id)
        return meta

    def get_blob(self, file_id: str) -> Binary:
        if self.blob_store is None:
            raise NotImplementedError("Blob store is not configured")
        return self.blob_store.get(file_id)

    def get_blob_url(self, file_id: str) -> str | None:
        if self.blob_store is None:
            raise NotImplementedError("Blob store is not configured")
        return self.blob_store.get_url(file_id)

    def get_blob_stream(self, file_id: str):
        """Return a streaming iterator for blob content, or ``None``."""
        if self.blob_store is None:
            raise NotImplementedError("Blob store is not configured")
        get_stream = getattr(self.blob_store, "get_stream", None)
        if get_stream is None:
            return None
        return get_stream(file_id)

    def get_blob_response(self, file_id: str):
        """Return the blob store's preferred download response."""
        from specstar.types import BlobResponse

        if self.blob_store is None:
            raise NotImplementedError("Blob store is not configured")
        response = self.blob_store.get_response(file_id)
        if response is not None:
            return response
        # Fallback for blob stores that don't implement get_response:
        # use the RM's own get_blob (which may be overridden in subclasses)
        blob = self.get_blob(file_id)
        return BlobResponse("data", blob=blob)

    def start_consume(
        self,
        *,
        block: bool = True,
        custom_creation: "Literal['all'] | list[str] | None" = None,
        custom_update: "Literal['all'] | list[str] | None" = None,
    ) -> "threading.Thread | None":
        """Start consuming jobs from the message queue.

        When both *custom_creation* and *custom_update* are ``None``
        (default) the resource’s own message-queue consumer is started.

        When *custom_creation* is ``"all"``, all async-create-job consumers
        that target this resource are started (but **not** this resource’s
        own consumer).

        When *custom_creation* is a list of job resource names, only those
        specific create-job consumers are started.

        When *custom_update* is ``"all"``, all async-update-job consumers
        that target this resource are started.

        When *custom_update* is a list of job resource names, only those
        specific update-job consumers are started.

        Both *custom_creation* and *custom_update* can be used together
        in the same call.

        Args:
            block: If ``True`` (default), block until the consumer thread(s)
                finish.  ``False`` returns immediately after launching the
                daemon thread(s).
            custom_creation: Which async-create-job consumers to start.
                ``None`` → ignored (no create-job consumers started).
                ``"all"`` → every registered async create-job consumer.
                ``["name", ...]`` → only the listed job resource names.
            custom_update: Which async-update-job consumers to start.
                ``None`` → ignored (no update-job consumers started).
                ``"all"`` → every registered async update-job consumer.
                ``["name", ...]`` → only the listed job resource names.

        Raises:
            NotImplementedError: If both *custom_creation* and *custom_update*
                are ``None`` and no message queue is configured on this
                resource.
            ValueError: If a name in *custom_creation* or *custom_update*
                is not a registered async job for this resource.
        """
        if custom_creation is None and custom_update is None:
            # Original behaviour: start this RM’s own MQ consumer.
            if self.message_queue is None:
                raise NotImplementedError("Message queue is not configured")
            worker_thread = threading.Thread(
                target=self.message_queue.start_consume, daemon=True
            )
            worker_thread.start()
            if block:
                worker_thread.join()
            return worker_thread

        threads = []

        # --- custom_creation mode ---
        if custom_creation is not None:
            if custom_creation == "all":
                create_targets = list(self._async_create_job_rms.values())
            else:
                create_targets = []
                for name in custom_creation:
                    job_rm = self._async_create_job_rms.get(name)
                    if job_rm is None:
                        raise ValueError(
                            f"'{name}' is not a registered async create-job "
                            f"for resource '{self.resource_name}'. "
                            f"Available: {list(self._async_create_job_rms.keys())}"
                        )
                    create_targets.append(job_rm)

            for job_rm in create_targets:
                t = job_rm.start_consume(block=False)
                threads.append(t)

        # --- custom_update mode ---
        if custom_update is not None:
            if custom_update == "all":
                update_targets = list(self._async_update_job_rms.values())
            else:
                update_targets = []
                for name in custom_update:
                    job_rm = self._async_update_job_rms.get(name)
                    if job_rm is None:
                        raise ValueError(
                            f"'{name}' is not a registered async update-job "
                            f"for resource '{self.resource_name}'. "
                            f"Available: {list(self._async_update_job_rms.keys())}"
                        )
                    update_targets.append(job_rm)

            for job_rm in update_targets:
                t = job_rm.start_consume(block=False)
                threads.append(t)

        if block:
            for t in threads:
                t.join()

    def count_resources(self, query: ResourceMetaSearchQuery | Query) -> int:
        """
        Count the number of resources matching the query.

        Arguments:
            query (ResourceMetaSearchQuery | Query): The search query object or Query builder.

        Returns:
            count (int): The number of matching resources.
        """
        if isinstance(query, Query):
            query = query.build()
        query = self._resolve_str_query_vectors(query)
        return self.storage.count(query)

    def _resolve_str_query_vectors(
        self, query: ResourceMetaSearchQuery
    ) -> ResourceMetaSearchQuery:
        """Convert any ``str`` ``query_vector`` in conditions/sorts to a
        ``list[float]`` by invoking the field's registered encoder.

        Sync only: raises if a required encoder is async.
        """
        import inspect

        import msgspec

        from specstar.query_types import (
            DataSearchGroup as _DSG,
        )
        from specstar.query_types import (
            VectorDistanceCondition as _VC,
        )
        from specstar.query_types import (
            VectorDistanceSort as _VS,
        )
        from specstar.resource_manager.encoder_registry import lookup_encoder
        from specstar.types import extract_vector_field_infos

        # Build per-field encoder cache once
        infos = {i.name: i for i in extract_vector_field_infos(self._resource_type)}

        # Embedding fields' field_path in query is the parent name (e.g. "summary"),
        # which corresponds to info.name; raw vector fields map directly too.

        def _encode(field_path: str, text: str) -> list[float]:
            top = field_path.split(".")[0]
            info = infos.get(top)
            if info is None:
                raise ValueError(
                    f"Vector field {field_path!r} not registered on "
                    f"{self._resource_type.__name__}; cannot encode str query_vector."
                )
            encoder = lookup_encoder(
                self._encoder_registry,
                field_info=info,
                model_overrides=self._vector_encoders,
            )
            if encoder is None:
                raise ValueError(
                    f"No encoder configured for field {field_path!r}; "
                    f"cannot encode str query_vector."
                )
            vec = encoder(text)
            if inspect.isawaitable(vec):
                # Close the unawaited coroutine to avoid a RuntimeWarning
                try:
                    vec.close()  # type: ignore[attr-defined]
                except Exception:
                    pass
                raise RuntimeError(
                    f"Encoder for field {field_path!r} is async but search was "
                    f"invoked synchronously. Register a sync encoder or use the "
                    f"async query path."
                )
            return vec

        def _maybe_resolve_cond(c):
            if isinstance(c, _VC) and isinstance(c.query_vector, str):
                return msgspec.structs.replace(
                    c, query_vector=_encode(c.field_path, c.query_vector)
                )
            if isinstance(c, _DSG):
                new_sub = [_maybe_resolve_cond(sub) for sub in c.conditions]
                if any(a is not b for a, b in zip(new_sub, c.conditions)):
                    return msgspec.structs.replace(c, conditions=new_sub)
            return c

        def _maybe_resolve_sort(s):
            if isinstance(s, _VS) and isinstance(s.query_vector, str):
                return msgspec.structs.replace(
                    s, query_vector=_encode(s.field_path, s.query_vector)
                )
            return s

        changes: dict = {}
        if query.conditions is not UNSET:
            new_conds = [_maybe_resolve_cond(c) for c in query.conditions]
            if any(a is not b for a, b in zip(new_conds, query.conditions)):
                changes["conditions"] = new_conds
        if query.sorts is not UNSET:
            new_sorts = [_maybe_resolve_sort(s) for s in query.sorts]
            if any(a is not b for a, b in zip(new_sorts, query.sorts)):
                changes["sorts"] = new_sorts
        if not changes:
            return query
        return msgspec.structs.replace(query, **changes)

    @execute_with_events(
        (
            BeforeSearchResources,
            AfterSearchResources,
            OnSuccessSearchResources,
            OnFailureSearchResources,
        ),
        "results",
    )
    def search_resources(
        self, query: ResourceMetaSearchQuery | Query
    ) -> list[ResourceMeta]:
        """
        Search resources based on the provided query.

        Arguments:
            query (ResourceMetaSearchQuery | Query): The search query object or Query builder.

        Returns:
            results (list[ResourceMeta]): A list of ResourceMeta objects matching the query.
        """
        if isinstance(query, Query):
            query = query.build()
        query = self._resolve_str_query_vectors(query)
        return self.storage.search(query)

    def iter_all(
        self,
        query: "ResourceMetaSearchQuery | Query | None" = None,
        *,
        batch_size: int = 1000,
    ) -> Generator[ResourceMeta]:
        """Yield *every* resource matching ``query``, paging internally.

        Unlike :meth:`search_resources` — which is bounded by the query's
        ``limit`` and can silently truncate — this walks the full result set
        in ``batch_size`` chunks. Use it whenever you genuinely want "all
        rows" so a forgotten ``limit`` can't drop data. ``query`` defaults to
        "all resources".

        Arguments:
            query: search query (or ``Query`` builder); ``None`` matches all.
            batch_size: page size used internally for the scan.

        Yields:
            ResourceMeta: one per matching resource, oldest page first.
        """
        if query is None:
            query = ResourceMetaSearchQuery()
        elif isinstance(query, Query):
            query = query.build()
        offset = 0
        while True:
            page = self.search_resources(
                msgspec.structs.replace(query, limit=batch_size, offset=offset)
            )
            if not page:
                return
            yield from page
            if len(page) < batch_size:
                return
            offset += batch_size

    def _default_worker_num(self, nr_work: int) -> int:
        """Calculate the number of worker threads for parallel fetch."""
        if nr_work <= 10:
            return 1
        return max(1, min(16, nr_work // 3))

    def list_resources(
        self,
        query: ResourceMetaSearchQuery | Query,
        *,
        returns: list[str] | None = None,
        partial: list[str] | None = None,
    ) -> list[SearchedResource[T]]:
        """Search for resources and fetch their data in one call.

        Internally calls ``search_resources(query)`` (which triggers
        Before/After/OnSuccess/OnFailure SearchResources events), then
        fetches the requested sections for each matching resource.

        Arguments:
            query (ResourceMetaSearchQuery | Query): The search query.
            returns: sections to include per item.  Allowed values are
                ``"data"``, ``"info"``, ``"meta"``.  ``None`` means all three.
            partial: optional list of field paths to retrieve.  Paths may
                be prefixed with ``data/``, ``meta/``, or ``info/`` to
                target a specific section; unprefixed paths default to
                ``"data"``.

        Returns:
            resources (list[SearchedResource[T]]): one item per matched resource.
        """
        # 1. Search — triggers SearchResources events
        metas = self.search_resources(query)
        if not metas:
            return []

        # 2. Normalise returns
        if returns is None:
            returns = ["data", "info", "meta"]

        # 3. Classify partial fields
        spec = classify_partial_fields(partial, default_category="data")

        # 4. Define per-item fetch function
        def _fetch_one(meta: ResourceMeta) -> SearchedResource[T] | None:
            try:
                data = UNSET
                info = UNSET

                if "data" in returns:
                    if spec.data_fields:
                        data = self.get_partial(
                            meta.resource_id,
                            meta.current_revision_id,
                            spec.data_fields,
                            schema_version=meta.schema_version,
                        )
                    else:
                        resource = self.get(
                            meta.resource_id,
                            revision_id=meta.current_revision_id,
                            schema_version=meta.schema_version,
                        )
                        data = resource.data
                        if "info" in returns:
                            info = resource.info

                if "info" in returns and info is UNSET:
                    info = self.get_revision_info(
                        meta.resource_id,
                        meta.current_revision_id,
                        schema_version=meta.schema_version,
                    )

                if "meta" in returns:
                    meta_out = meta
                else:
                    meta_out = UNSET

                # Apply partial filtering on meta and info
                if spec.meta_fields and meta_out is not UNSET:
                    meta_out = filter_struct_partial(meta_out, spec.meta_fields)
                if spec.info_fields and info is not UNSET:
                    info = filter_struct_partial(info, spec.info_fields)

                return SearchedResource(data=data, info=info, meta=meta_out)
            except Exception:
                return None

        # 5. Execute — single-threaded or parallel
        worker_num = self._default_worker_num(len(metas))
        results: list[SearchedResource[T]] = []

        if worker_num <= 1:
            for meta in metas:
                item = _fetch_one(meta)
                if item is not None:
                    results.append(item)
        else:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=worker_num,
            ) as executor:
                futures = [executor.submit(_fetch_one, meta) for meta in metas]
                for future in futures:
                    item = future.result()
                    if item is not None:
                        results.append(item)

        return results

    @coerce_data_to_resource_type
    @execute_with_events(
        (BeforeCreate, AfterCreate, OnSuccessCreate, OnFailureCreate),
        "info",
        context_aware=True,
    )
    def create(
        self,
        data: T,
        *,
        status: RevisionStatus | UnsetType = UNSET,
        user: str | UnsetType = UNSET,
        now: dt.datetime | UnsetType = UNSET,
        resource_id: str | UnsetType = UNSET,
    ) -> RevisionInfo:
        """
        Create a new resource.

        Arguments:
            data (T): The resource data object.
            status (RevisionStatus | UnsetType): The initial status of the resource (default: stable).
            user (str | UnsetType): The user performing the action.
                Overrides any active ``using()`` scope or manager default.
            now (datetime | UnsetType): The current timestamp.
                Overrides any active ``using()`` scope or manager default.
            resource_id (str | UnsetType): Specific resource ID to use
                instead of auto-generating one.

        Returns:
            info (RevisionInfo): The revision info of the created resource.

        Raises:
            UniqueConstraintError: If a field annotated with :class:`Unique` already
                has the same value on another non-deleted resource.
        """
        status = self.default_status if status is UNSET else status
        data = self._process_binary_fields(data)
        data = self._embedding_processor.process_sync(data)
        info = self._rev_info(_BuildRevInfoCreate(data, status))
        self.storage.save_revision(info, io.BytesIO(self.encode(data)))
        self.storage.save_meta(self._res_meta(_BuildResMetaCreate(info, data)))
        if self.message_queue is not None:
            self.message_queue.put(info.resource_id)
        return info

    @execute_with_events(
        (BeforeGet, AfterGet, OnSuccessGet, OnFailureGet),
        "resource",
    )
    def get(
        self,
        resource_id: str,
        *,
        revision_id: str | UnsetType = UNSET,
        schema_version: str | None | UnsetType = UNSET,
        include_deleted: bool = False,
    ) -> Resource[T]:
        """
        Get a resource by its ID.

        Arguments:
            resource_id (str): The ID of the resource to retrieve.
            revision_id (str | UnsetType): (Optional) The specific revision ID to retrieve. If not set, retrieves the latest revision.
            schema_version (str | None | UnsetType): (Optional) The schema version of the resource.
            include_deleted (bool): If True, return the requested revision even
                for a soft-deleted resource instead of raising
                ``ResourceIsDeletedError``. Mirrors ``get_meta()``. Defaults to
                ``False`` so existing behavior is unchanged.

        Returns:
            resource (Resource[T]): The resource object containing both data and metadata.

        Raises:
            ResourceIDNotFoundError: If the resource ID or revision ID does not exist.
            ResourceIsDeletedError: If the resource has been soft-deleted and
                *include_deleted* is ``False``.
        """
        if revision_id is UNSET or schema_version is UNSET:
            meta = self.get_meta(resource_id, include_deleted=include_deleted)
            if revision_id is UNSET:
                revision_id = meta.current_revision_id
            if schema_version is UNSET:
                schema_version = meta.schema_version
        return self.get_resource_revision(
            resource_id, revision_id, schema_version=schema_version
        )

    def get_partial(
        self,
        resource_id: str,
        revision_id: str,
        partial: Iterable[str | JsonPointer],
        *,
        schema_version: str | None | UnsetType = UNSET,
    ) -> Struct:
        """
        Get a partial view of a resource (only specified fields).

        Arguments:
            resource_id (str): The ID of the resource.
            revision_id (str): The revision ID of the resource.
            partial (Iterable[str | JsonPointer]): A list of fields or JSON pointers to retrieve.

        Returns:
            partial_data (Struct): A struct containing only the requested fields.
        """
        with self.storage.get_data_bytes(
            resource_id, revision_id, schema_version=schema_version
        ) as data_io:
            PartialType = create_partial_type(self._resource_type, partial)
            s = MsgspecSerializer(
                encoding=self._encoding,
                resource_type=PartialType,
            )
            decoded = s.decode(data_io.read())
            return prune_object(decoded, partial)

    def get_revision_info(
        self,
        resource_id: str,
        revision_id: str | UnsetType = UNSET,
        *,
        schema_version: str | None | UnsetType = UNSET,
    ) -> RevisionInfo:
        """
        Get the metadata (RevisionInfo) of a specific revision.

        Arguments:
            resource_id (str): The ID of the resource.
            revision_id (str | UnsetType): The revision ID. If not set, returns the latest revision info.

        Returns:
            info (RevisionInfo): The metadata of the revision.
        """
        if revision_id is UNSET:
            meta = self.get_meta(resource_id)
            revision_id = meta.current_revision_id
            if schema_version is UNSET:
                schema_version = meta.schema_version

        return self.storage.get_resource_revision_info(
            resource_id, revision_id, schema_version=schema_version
        )

    @execute_with_events(
        (
            BeforeGetResourceRevision,
            AfterGetResourceRevision,
            OnSuccessGetResourceRevision,
            OnFailureGetResourceRevision,
        ),
        "resource",
    )
    def get_resource_revision(
        self,
        resource_id: str,
        revision_id: str,
        schema_version: str | None | UnsetType = UNSET,
    ) -> Resource[T]:
        """
        Get a specific revision of a resource.

        Arguments:
            resource_id (str): The ID of the resource.
            revision_id (str): The specific revision ID.

        Returns:
            resource (Resource[T]): The resource object.
        """
        info = self.storage.get_resource_revision_info(
            resource_id, revision_id, schema_version
        )
        with self.storage.get_data_bytes(
            resource_id, revision_id, schema_version
        ) as data_io:
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
        """
        List all revision IDs for a given resource.

        Arguments:
            resource_id (str): The ID of the resource.

        Returns:
            revisions (list[str]): A list of revision IDs.
        """
        return self.storage.list_revisions(resource_id)

    @coerce_data_to_resource_type
    @execute_with_events(
        (BeforeUpdate, AfterUpdate, OnSuccessUpdate, OnFailureUpdate),
        "revision_info",
        context_aware=True,
    )
    def update(
        self,
        resource_id: str,
        data: T,
        *,
        status: RevisionStatus | UnsetType = UNSET,
        user: str | UnsetType = UNSET,
        now: dt.datetime | UnsetType = UNSET,
    ) -> RevisionInfo:
        """
        Update an existing resource with new data (creates a new revision).

        Arguments:
            resource_id (str): The ID of the resource to update.
            data (T): The new resource data.
            status (RevisionStatus | UnsetType): The status of the new revision (default: stable).
            user (str | UnsetType): The user performing the action.
            now (datetime | UnsetType): The current timestamp.

        Returns:
            info (RevisionInfo): The revision info of the updated resource.

        Raises:
            ResourceIDNotFoundError: If the resource ID does not exist.
        """
        status = self.default_status if status is UNSET else status
        data = self._process_binary_fields(data)
        prev_res_meta = self.get_meta(resource_id)
        prev_info = self.storage.get_resource_revision_info(
            resource_id,
            prev_res_meta.current_revision_id,
        )
        # Pass previous data for Embedding cache reuse (bypass events: raw decode)
        prev_data = None
        try:
            with self.storage.get_data_bytes(
                resource_id, prev_res_meta.current_revision_id
            ) as fh:
                prev_data = self._data_serializer.decode(fh.read())
        except Exception:
            pass
        data = self._embedding_processor.process_sync(data, previous=prev_data)
        rev_info = self._rev_info(_BuildRevInfoUpdate(prev_res_meta, data, status))
        if prev_info.data_hash == rev_info.data_hash:
            return prev_info
        res_meta = self._res_meta(_BuildResMetaUpdate(prev_res_meta, rev_info, data))
        self.storage.save_revision(rev_info, io.BytesIO(self.encode(data)))
        self.storage.save_meta(res_meta)
        return rev_info

    def create_or_update(
        self,
        resource_id,
        data,
        *,
        status: RevisionStatus | UnsetType = UNSET,
        user: str | UnsetType = UNSET,
        now: dt.datetime | UnsetType = UNSET,
    ):
        """
        Create a new resource or update if it already exists.

        Arguments:
            resource_id (str): The ID of the resource.
            data (T): The resource data.
            status (RevisionStatus | UnsetType): The status (default: stable).
            user (str | UnsetType): The user performing the action.
            now (datetime | UnsetType): The current timestamp.

        Returns:
            info (RevisionInfo): The revision info.
        """
        with self._apply_context(user=user, now=now, resource_id=resource_id):
            try:
                return self.update(resource_id, data, status=status)
            except ResourceIDNotFoundError:
                return self.create(data, status=status)

    @coerce_data_to_resource_type
    @execute_with_events(
        (BeforeModify, AfterModify, OnSuccessModify, OnFailureModify),
        "revision_info",
        context_aware=True,
    )
    def modify(
        self,
        resource_id: str,
        data: "T | JsonPatch | MergePatch | UnsetType" = UNSET,
        status: RevisionStatus | UnsetType = UNSET,
        *,
        user: str | UnsetType = UNSET,
        now: dt.datetime | UnsetType = UNSET,
    ) -> RevisionInfo:
        """
        Modify a resource without creating a new revision (only for DRAFT status).

        Arguments:
            resource_id (str): The ID of the resource.
            data (T | JsonPatch | UnsetType): The new data or JSON patch to apply.
            status (RevisionStatus | UnsetType): The new status.
            user (str | UnsetType): The user performing the action.
            now (datetime | UnsetType): The current timestamp.

        Returns:
            info (RevisionInfo): The updated revision info.

        Raises:
            CannotModifyResourceError: If the resource is not in DRAFT status.
        """
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
        elif type(data) is MergePatch:
            data = self._apply_merge_patch(resource_id, data)

        if data is not UNSET:
            data = self._process_binary_fields(data)
            prev_data = None
            try:
                with self.storage.get_data_bytes(
                    resource_id, prev_res_meta.current_revision_id
                ) as fh:
                    prev_data = self._data_serializer.decode(fh.read())
            except Exception:
                pass
            data = self._embedding_processor.process_sync(data, previous=prev_data)

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
        context_aware=True,
    )
    def patch(
        self,
        resource_id: str,
        patch_data: "JsonPatch | MergePatch",
        *,
        user: str | UnsetType = UNSET,
        now: dt.datetime | UnsetType = UNSET,
    ) -> RevisionInfo:
        """
        Apply an RFC 6902 JSON Patch or RFC 7386 Merge Patch to the resource.

        Arguments:
            resource_id (str): the id of the resource to patch.
            patch_data (JsonPatch | MergePatch): RFC 6902 operations
                (``JsonPatch``) or an RFC 7386 merge patch (``MergePatch``).
            user (str | UnsetType): The user performing the action.
            now (datetime | UnsetType): The current timestamp.

        Returns:
            info (RevisionInfo): the metadata of the newly created revision.

        Raises:
            ResourceIDNotFoundError: if resource id does not exist.
            ResourceIsDeletedError: if resource is soft-deleted.
        """
        if type(patch_data) is MergePatch:
            data = self._apply_merge_patch(resource_id, patch_data)
        else:
            data = self._apply_patch(resource_id, patch_data)
        return self.update(resource_id, data)

    def _apply_patch(self, resource_id: str, patch_data: JsonPatch) -> T:
        data = self.get(resource_id).data
        if isinstance(data, msgspec.Raw):
            d = json.loads(bytes(data))
        else:
            d = msgspec.to_builtins(data)
        patch_data.apply(d, in_place=True)
        return msgspec.convert(d, self.resource_type)

    def _apply_merge_patch(self, resource_id: str, merge_patch: dict) -> T:
        """RFC 7386 analogue of :meth:`_apply_patch`: merge ``merge_patch`` into
        the current data and return the resulting full resource."""
        data = self.get(resource_id).data
        if isinstance(data, msgspec.Raw):
            d = json.loads(bytes(data))
        else:
            d = msgspec.to_builtins(data)
        return msgspec.convert(_rfc7386_merge(d, merge_patch), self.resource_type)

    @execute_with_events(
        (BeforeSwitch, AfterSwitch, OnSuccessSwitch, OnFailureSwitch),
        "meta",
        context_aware=True,
    )
    def switch(
        self,
        resource_id: str,
        revision_id: str,
        *,
        user: str | UnsetType = UNSET,
        now: dt.datetime | UnsetType = UNSET,
    ) -> ResourceMeta:
        """
        Switch specific resource to another revision.

        Arguments:
            resource_id (str): The ID of the resource.
            revision_id (str): The revision ID to switch to.
            user (str | UnsetType): The user performing the action.
            now (datetime | UnsetType): The current timestamp.

        Returns:
            meta (ResourceMeta): The updated metadata.

        Raises:
            RevisionIDNotFoundError: If the revision ID does not exist.
            RevisionNotMigratedError: If the revision has a different
                schema version than the resource's current schema version
                and migration is configured.  The revision must be
                migrated first via ``migrate(resource_id, revision_id=...)``.
        """
        meta = self.get_meta(resource_id)
        if meta.current_revision_id == revision_id:
            return meta

        # When migration is configured, use find_revision_schema_version
        # to locate the revision regardless of its schema_version key.
        if self._migration is not None:
            actual_sv = self.storage.find_revision_schema_version(
                resource_id, revision_id
            )
            if actual_sv is UNSET:
                raise RevisionIDNotFoundError(resource_id, revision_id)
            if actual_sv != meta.schema_version:
                raise RevisionNotMigratedError(
                    resource_id, revision_id, actual_sv, meta.schema_version
                )
        else:
            # No migration configured — use the original check
            if not self.storage.revision_exists(resource_id, revision_id):
                raise RevisionIDNotFoundError(resource_id, revision_id)

        # 切換到指定版本時，需要更新索引數據
        if self._indexed_fields:
            data = self._load_revision_data(resource_id, revision_id)
            meta.indexed_data = self._extract_indexed_values(data)

        # Refresh the embedded ``rev_*`` mirror to point at the new
        # current revision so search-by-revision-attrs stays consistent.
        target_info = self.storage.get_resource_revision_info(
            resource_id, revision_id, schema_version=meta.schema_version
        )
        meta.rev_status = target_info.status
        meta.rev_created_by = target_info.created_by
        meta.rev_updated_by = target_info.updated_by
        meta.rev_created_time = target_info.created_time
        meta.rev_updated_time = target_info.updated_time

        meta.updated_by = self.user_ctx.get()
        meta.updated_time = self.now_ctx.get()
        meta.current_revision_id = revision_id
        self.storage.save_meta(meta)
        return meta

    @execute_with_events(
        (BeforeDelete, AfterDelete, OnSuccessDelete, OnFailureDelete),
        "meta",
        context_aware=True,
    )
    def delete(
        self,
        resource_id: str,
        *,
        user: str | UnsetType = UNSET,
        now: dt.datetime | UnsetType = UNSET,
    ) -> ResourceMeta:
        """
        Soft delete a resource.

        Arguments:
            resource_id (str): The ID of the resource to delete.
            user (str | UnsetType): The user performing the action.
            now (datetime | UnsetType): The current timestamp.

        Returns:
            meta (ResourceMeta): The updated metadata (is_deleted=True).

        Raises:
            ResourceIDNotFoundError: If the resource ID does not exist.
        """
        meta = self.get_meta(resource_id)
        meta.is_deleted = True
        meta.updated_by = self.user_ctx.get()
        meta.updated_time = self.now_ctx.get()
        self.storage.save_meta(meta)
        return meta

    @execute_with_events(
        (BeforeRestore, AfterRestore, OnSuccessRestore, OnFailureRestore),
        "meta",
        context_aware=True,
    )
    def restore(
        self,
        resource_id: str,
        *,
        user: str | UnsetType = UNSET,
        now: dt.datetime | UnsetType = UNSET,
    ) -> ResourceMeta:
        """
        Restore a soft-deleted resource.

        Arguments:
            resource_id (str): The ID of the resource to restore.
            user (str | UnsetType): The user performing the action.
            now (datetime | UnsetType): The current timestamp.

        Returns:
            meta (ResourceMeta): The updated metadata (is_deleted=False).

        Raises:
            ResourceIDNotFoundError: If the resource ID does not exist.
        """
        meta = self._get_meta_no_check_is_deleted(resource_id)
        if meta.is_deleted:
            meta.is_deleted = False
            meta.updated_by = self.user_ctx.get()
            meta.updated_time = self.now_ctx.get()
            self.storage.save_meta(meta)
        return meta

    @execute_with_events(
        (
            BeforePermanentlyDelete,
            AfterPermanentlyDelete,
            OnSuccessPermanentlyDelete,
            OnFailurePermanentlyDelete,
        ),
        "meta",
        context_aware=True,
    )
    def permanently_delete(
        self,
        resource_id: str,
        *,
        user: str | UnsetType = UNSET,
        now: dt.datetime | UnsetType = UNSET,
    ) -> ResourceMeta:
        """Permanently delete a resource and all its revision data.

        This is an irreversible operation that removes the resource metadata
        and all associated revision data from storage.

        Args:
            resource_id: The ID of the resource to permanently delete.
            user: The user performing the action.  Overrides any active
                ``using()`` scope or manager default.
            now: The current timestamp.  Overrides any active ``using()``
                scope or manager default.

        Returns:
            The metadata of the resource before deletion.

        Raises:
            ResourceIDNotFoundError: If the resource ID does not exist.
        """
        meta = self._get_meta_no_check_is_deleted(resource_id)
        self.storage.purge_resource(resource_id)
        return meta

    @execute_with_events(
        (BeforeDump, AfterDump, OnSuccessDump, OnFailureDump),
        "result",
        inputs={"query": UNSET},
    )
    def dump(
        self,
        query: Query | ResourceMetaSearchQuery | None = None,
    ) -> Generator[MetaRecord | RevisionRecord | BlobRecord]:
        """Dump metadata, revision data, and blobs as Record objects.

        Args:
            query: Optional QB/search query.  When given, only matching
                resources are exported.  ``None`` exports everything.

        Yields:
            :class:`MetaRecord`, :class:`RevisionRecord`, and
            :class:`BlobRecord` instances.  For each resource the meta
            record is yielded first, immediately followed by all its
            revision records — no intermediate id collection needed.
            Blob records are emitted at the end.
        """

        # Pre-hoist encoders
        meta_encode = self.meta_serializer.encode
        res_encode = self.resource_serializer.encode
        has_blobs = self.blob_store is not None
        collect = self._binary_processor.collect_file_ids if has_blobs else None
        data_decode = self._data_serializer.decode if has_blobs else None
        blob_file_ids: set[str] = set()

        # Build meta iterator
        if query is not None:
            if isinstance(query, Query):
                query = query.build()
            q = msgspec.structs.replace(query, limit=2**31 - 1, offset=0)
            metas = self.storage.iter_search(q)
        else:
            metas = self.storage.dump_meta(None)

        # --- helpers shared by both fast/slow paths ---
        def _make_rev_record(info, raw_data: bytes):
            return RevisionRecord(
                data=res_encode(RawResource(info=info, raw_data=raw_data))
            )

        def _collect_blobs(raw_data: bytes):
            if collect is not None and data_decode is not None:
                try:
                    blob_file_ids.update(collect(data_decode(raw_data)))
                except Exception:
                    pass

        # Try bulk pre-fetch (concurrent S3 downloads when supported).
        # Materialise the metas once: the bulk path needs the id set, and
        # the slow fallback iterates the same list.
        metas_list = list(metas)
        rid_set = frozenset(m.resource_id for m in metas_list)
        bulk = self.storage.dump_resources_bulk(resource_ids=rid_set)

        if bulk is not None:
            for meta in metas_list:
                yield MetaRecord(data=meta_encode(meta))
                for info, raw_data in bulk.get(meta.resource_id, []):
                    yield _make_rev_record(info, raw_data)
                    _collect_blobs(raw_data)
        else:
            # Slow path: stream one resource at a time
            dump_resource = self.storage.dump_resource
            for meta in metas_list:
                yield MetaRecord(data=meta_encode(meta))
                for info, data_io in dump_resource(meta.resource_id):
                    raw_data = data_io.read()
                    yield _make_rev_record(info, raw_data)
                    _collect_blobs(raw_data)

        # Blobs (must come after all revisions so file_ids are fully collected)
        if has_blobs and blob_file_ids:
            blob_store = self.blob_store
            for file_id in blob_file_ids:
                try:
                    blob = blob_store.get(file_id)
                    if blob.data is not UNSET:
                        yield BlobRecord(
                            file_id=file_id,
                            blob_data=blob.data,
                            size=blob.size
                            if blob.size is not UNSET
                            else len(blob.data),
                            content_type=blob.content_type
                            if blob.content_type is not UNSET
                            else "",
                        )
                except Exception:
                    pass

    @execute_with_events(
        (BeforeLoad, AfterLoad, OnSuccessLoad, OnFailureLoad),
        lambda _: {},
        inputs={"bio": UNSET},
    )
    def load(self, record_type: str, bio: IO[bytes]) -> None:
        """Legacy load interface — load a single keyed item.

        .. deprecated::
            Use :meth:`load_record` with :class:`DumpRecord` objects instead.
        """
        if record_type.startswith("meta/"):
            self.storage.save_meta(self.meta_serializer.decode(bio.read()))
        elif record_type.startswith("data/"):
            raw_res = self.resource_serializer.decode(bio.read())
            self.storage.save_revision(raw_res.info, io.BytesIO(raw_res.raw_data))
        elif record_type.startswith("blob/"):
            blob_entry = self._blob_serializer.decode(bio.read())
            if self.blob_store is not None:
                self.blob_store.put(
                    blob_entry.data, content_type=blob_entry.content_type
                )

    def load_record(
        self,
        record: "MetaRecord | RevisionRecord | BlobRecord",
        on_duplicate: "OnDuplicate" = OnDuplicate.raise_error,
    ) -> bool:
        """Load a single :class:`DumpRecord` into storage.

        Args:
            record: A :class:`MetaRecord`, :class:`RevisionRecord`, or
                :class:`BlobRecord` instance (typically produced by
                :meth:`dump`).
            on_duplicate: Strategy when a resource with the same ID already
                exists.  Only meaningful for :class:`MetaRecord`; revision
                and blob records are always written.

        Returns:
            ``True`` if the record was stored, ``False`` if it was skipped
            (only possible when *on_duplicate* is :attr:`OnDuplicate.skip`).

        Raises:
            DuplicateResourceError: When the resource already exists and
                *on_duplicate* is :attr:`OnDuplicate.raise_error`.
        """
        record_type = type(record).__name__
        ctx_kw: _LoadCtxKw = {
            "user": self.user_or_unset,
            "now": self.now_or_unset,
            "resource_name": self.resource_name,
            "record_type": record_type,
        }
        self._handle_event(BeforeLoad(**ctx_kw))
        try:
            result = self._load_record_impl(record, on_duplicate)
            self._handle_event(OnSuccessLoad(**ctx_kw))
            return result
        except Exception as e:
            self._handle_event(
                OnFailureLoad(
                    **ctx_kw,
                    error=str(e),
                    stack_trace=traceback.format_exc(),
                )
            )
            raise
        finally:
            self._handle_event(AfterLoad(**ctx_kw))

    def _load_record_impl(
        self,
        record: "MetaRecord | RevisionRecord | BlobRecord",
        on_duplicate: "OnDuplicate",
    ) -> bool:
        """Internal implementation of load_record."""
        if isinstance(record, MetaRecord):
            meta = self.meta_serializer.decode(record.data)
            exists = self.storage.exists(meta.resource_id)
            if exists:
                if on_duplicate is OnDuplicate.skip:
                    return False
                if on_duplicate is OnDuplicate.raise_error:
                    raise DuplicateResourceError(meta.resource_id)
                # OnDuplicate.overwrite — fall through and save
            self.storage.save_meta(meta)
            return True

        if isinstance(record, RevisionRecord):
            raw_res = self.resource_serializer.decode(record.data)
            self.storage.save_revision(raw_res.info, io.BytesIO(raw_res.raw_data))
            return True

        if isinstance(record, BlobRecord):
            if self.blob_store is not None:
                self.blob_store.put(
                    record.blob_data,
                    content_type=record.content_type,
                )
            return True

        return True

    # ------------------------------------------------------------------
    # Bulk load
    # ------------------------------------------------------------------

    def load_records_bulk(
        self,
        meta_records: "list[MetaRecord]",
        revision_records: "list[RevisionRecord]",
        blob_records: "list[BlobRecord]",
        on_duplicate: "OnDuplicate" = OnDuplicate.raise_error,
    ):
        """Batch-load multiple dump records into storage.

        Instead of writing each record one-by-one (which incurs per-call
        overhead especially on remote backends like S3 / PostgreSQL), this
        method:

        1. Decodes **all** meta records, applies the *on_duplicate*
           strategy, and bulk-saves them via
           :meth:`SimpleStorage.save_metas_bulk`.
        2. Decodes **all** revision records and bulk-saves them via
           :meth:`SimpleStorage.save_revisions_bulk` (which may use
           concurrent I/O on S3).
        3. Writes blob records sequentially (typically few in number).

        Events (Before/After/OnSuccess/OnFailure Load) are fired **once
        per batch**, not per record.

        Returns:
            A :class:`LoadStats` instance with *loaded*, *skipped* and
            *total* counts (counted per distinct ``resource_id``).
        """
        from specstar.crud.core import LoadStats as _LoadStats

        stats = _LoadStats()

        # --- fire BeforeLoad once for the batch --------------------------
        ctx_kw: _LoadCtxKw = {
            "user": self.user_or_unset,
            "now": self.now_or_unset,
            "resource_name": self.resource_name,
            "record_type": "bulk",
        }
        self._handle_event(BeforeLoad(**ctx_kw))

        try:
            # --- 1. decode + deduplicate metas ----------------------------
            metas_to_save: list[ResourceMeta] = []
            skipped_ids: set[str] = set()

            for rec in meta_records:
                meta = self.meta_serializer.decode(rec.data)
                stats.total += 1
                exists = self.storage.exists(meta.resource_id)
                if exists:
                    if on_duplicate is OnDuplicate.skip:
                        stats.skipped += 1
                        skipped_ids.add(meta.resource_id)
                        continue
                    if on_duplicate is OnDuplicate.raise_error:
                        raise DuplicateResourceError(meta.resource_id)
                metas_to_save.append(meta)
                stats.loaded += 1

            # bulk write metas
            self.storage.save_metas_bulk(metas_to_save)

            # --- 2. decode + bulk write revisions -------------------------
            revisions_to_save: list[tuple[RevisionInfo, bytes]] = []
            for rec in revision_records:
                raw_res = self.resource_serializer.decode(rec.data)
                if raw_res.info.resource_id in skipped_ids:
                    continue
                revisions_to_save.append((raw_res.info, raw_res.raw_data))

            self.storage.save_revisions_bulk(revisions_to_save)

            # --- 3. blob records (sequential — usually few) ---------------
            if self.blob_store is not None:
                for rec in blob_records:
                    self.blob_store.put(
                        rec.blob_data,
                        content_type=rec.content_type,
                    )

            self._handle_event(OnSuccessLoad(**ctx_kw))
        except Exception as e:
            self._handle_event(
                OnFailureLoad(
                    **ctx_kw,
                    error=str(e),
                    stack_trace=traceback.format_exc(),
                )
            )
            raise
        finally:
            self._handle_event(AfterLoad(**ctx_kw))

        return stats

    @cached_property
    def meta_serializer(self):
        return MsgspecSerializer(encoding=Encoding.msgpack, resource_type=ResourceMeta)

    @cached_property
    def resource_serializer(self):
        return MsgspecSerializer(
            encoding=Encoding.msgpack,
            resource_type=RawResource,
        )

    @cached_property
    def _blob_serializer(self):
        return MsgspecSerializer(encoding=Encoding.msgpack, resource_type=_BlobEntry)

    @cached_property
    def _binary_processor(self) -> BinaryProcessor:
        return BinaryProcessor(self._resource_type)
