from __future__ import annotations

import asyncio
import datetime as dt
import inspect
import logging
import warnings
from collections import OrderedDict
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import (
    IO,
    Any,
    Literal,
    TypeVar,
    cast,
)

from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.params import Body
from msgspec import UNSET, Struct, UnsetType

from specstar.backend import BackendConfig, build_backend_bundle
from specstar.crud.custom_actions import (
    LazyJobHandler,
    _PendingCreateAction,
    _PendingUpdateAction,
)
from specstar.crud.ref_manager import install_ref_integrity_handlers
from specstar.crud.route_templates.backup import (
    ExportRouteTemplate,
    ImportRouteTemplate,
)
from specstar.crud.route_templates.basic import (
    DependencyProvider,
    IRouteTemplate,
)
from specstar.crud.route_templates.blob import BlobRouteTemplate
from specstar.crud.route_templates.create import CreateRouteTemplate
from specstar.crud.route_templates.delete import (
    BatchDeleteRouteTemplate,
    BatchRestoreRouteTemplate,
    DeleteRouteTemplate,
    PermanentlyDeleteRouteTemplate,
    RestoreRouteTemplate,
)
from specstar.crud.route_templates.get import ReadRouteTemplate
from specstar.crud.route_templates.job_logs import JobLogsRouteTemplate
from specstar.crud.route_templates.patch import (
    PatchRouteTemplate,
)
from specstar.crud.route_templates.rerun import RerunRouteTemplate
from specstar.crud.route_templates.search import ListRouteTemplate
from specstar.crud.route_templates.switch import SwitchRevisionRouteTemplate
from specstar.crud.route_templates.update import UpdateRouteTemplate
from specstar.descriptor import Descriptor
from specstar.events import IEventHandler
from specstar.permission.checker import IPermissionChecker
from specstar.permission.rbac import RBACPermissionChecker
from specstar.permission.simple import AllowAll
from specstar.query import Query
from specstar.query_types import (
    DataSearchCondition,
    DataSearchOperator,
    ResourceMetaSearchQuery,
)
from specstar.resource_manager.basic import (
    Encoding,
    IStorage,
)
from specstar.resource_manager.blob_store.simple import MemoryBlobStore
from specstar.resource_manager.core import ResourceManager
from specstar.resource_manager.pydantic_converter import (
    is_pydantic_model,
    pydantic_to_struct,
)
from specstar.resource_manager.storage_factory import (
    IStorageFactory,
    MemoryStorageFactory,
)
from specstar.schema import Schema
from specstar.types import (
    IConstraintChecker,
    IMessageQueue,
    IMessageQueueFactory,
    IMigration,
    IndexableField,
    IResourceManager,
    IValidator,
    Job,
    OnDelete,
    OnDuplicate,
    Resource,
    ResourceIDNotFoundError,
    ResourceIsDeletedError,
    RevisionInfo,
    RevisionStatus,
    TaskStatus,
    _RefInfo,
    extract_refs,
)
from specstar.util.naming import NameConverter
from specstar.util.type_utils import (
    get_type_name,
    is_generic_subclass,
    unwrap_annotated,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")


class LoadStats:
    """Per-model statistics returned by :meth:`SpecStar.load`."""

    __slots__ = ("loaded", "skipped", "total")

    def __init__(self) -> None:
        self.loaded = 0
        self.skipped = 0
        self.total = 0

    def __repr__(self) -> str:
        return (
            f"LoadStats(loaded={self.loaded}, skipped={self.skipped}, "
            f"total={self.total})"
        )


class SpecStar:
    """High-level entry point for registering resource models and generating CRUD routes.

    SpecStar manages a set of per-resource `ResourceManager`s and applies a set of
    route templates to a FastAPI `APIRouter` (or `FastAPI` app) to generate endpoints.

    Typical setup:

    ```python
    from fastapi import FastAPI
    from specstar import spec  # global instance

    app = FastAPI()

    # configure once at startup (optional)
    spec.configure(model_naming="kebab")

    # register models/schemas
    spec.add_model(User)
    spec.add_model(Post)

    # generate routes
    spec.apply(app)
    ```

    Notes:
    - Call `configure()` / `add_model()` during application startup, before serving requests.
    - `apply()` installs route templates, custom create/update actions, ref routes, and backup routes.
    - `openapi()` customizes OpenAPI schema to include SpecStar-specific schemas and extensions.

    Args:
        model_naming:
            How model names are converted to resource names (URL paths). Either one of:
            `"same"`, `"pascal"`, `"camel"`, `"snake"`, `"kebab"`, or a callable `(type) -> str`.
        route_templates:
            Route templates to apply. When `None` or a `dict`, default templates are used and
            can be configured via `{TemplateClass: kwargs}`.
        backend:
            Higher-level unified backend configuration. Accepts a typed config object,
            a plain dict, or a JSON file path. This is the easiest way to configure
            metadata, resource, blob, and message-queue backends together.
        storage_factory:
            Lower-level storage factory for models that don't specify `storage`.
            Use this when you want more explicit control over storage composition.
        message_queue_factory:
            Lower-level message queue factory used for Job models (when enabled).
        admin:
            If provided and `permission_checker` is not set, enables RBAC with `admin` as root user.
        permission_checker:
            Permission checker used by default for models that don't override it.
        dependency_provider:
            Dependency injection provider passed to route templates (when using defaults).
        event_handlers:
            Global event handlers used by default for models that don't override it.
        encoding:
            Default encoding for stored payloads (e.g. json/msgpack).
        default_user:
            Default user (or factory) used when user is not specified.
            When set, the ``DependencyProvider``'s default ``get_user``
            returns this value instead of ``"anonymous"``.  A custom
            ``get_user`` on the provider always takes priority.
        default_now:
            Default timestamp function used when time is not specified.
        default_status:
            Default revision status applied when registering models via
            :meth:`add_model` (e.g. ``RevisionStatus.draft``). Per-model
            ``default_status`` on ``add_model`` overrides this. If neither
            is set, ``ResourceManager`` falls back to
            ``RevisionStatus.stable``.
        strict_operation_context:
            When ``True``, all write operations (create, update, delete, etc.)
            will raise :class:`MissingOperationContextError` if required
            context fields (``user``, ``now``) are not fully resolved from
            any source (explicit kwargs, ``using()`` scope, or manager
            defaults).  Defaults to ``False``.
        forbid_unknown_fields:
            When ``True``, ``create()`` / ``update()`` / ``modify()`` reject
            inputs (dict / JSON body / Pydantic) that contain top-level keys
            not declared on the registered resource ``Struct``, raising
            :class:`specstar.types.ValidationError` (HTTP 422 on routes).
            Defaults to ``False`` for backward compatibility — unknown fields
            are silently dropped, matching msgspec's default behavior.

    See also:
        - `Schema`: declare schema/validation/migration for a resource.
        - `Ref`, `RefRevision`: reference types used across APIs and OpenAPI schema.
        - `dump()`, `load()`: export/import utilities for backups.
        - Routes: docs/howto/routes.md
        - Behavior & lifecycle: docs/reference/behavior.md
        - Performance notes: docs/guides/performance.md
    """

    def __init__(
        self,
        *,
        model_naming: Literal["same", "pascal", "camel", "snake", "kebab"]
        | Callable[[type], str] = "kebab",
        route_templates: list[IRouteTemplate]
        | dict[type, dict[str, Any]]
        | None = None,
        backend: BackendConfig | dict[str, Any] | str | Path | None = None,
        storage_factory: IStorageFactory | None = None,
        message_queue_factory: IMessageQueueFactory | None = None,
        admin: str | None = None,
        permission_checker: IPermissionChecker | None = None,
        dependency_provider: DependencyProvider | None = None,
        event_handlers: Sequence[IEventHandler] | None = None,
        encoding: Encoding = Encoding.json,
        default_user: str | Callable[[], str] | UnsetType = UNSET,
        default_now: Callable[[], dt.datetime] | UnsetType = UNSET,
        default_status: RevisionStatus | UnsetType = UNSET,
        strict_operation_context: bool = False,
        forbid_unknown_fields: bool = False,
    ):
        # Initialize empty collections
        self.resource_managers: OrderedDict[str, IResourceManager] = OrderedDict()
        self.message_queues: OrderedDict[str, IMessageQueue] = OrderedDict()
        self.model_names: dict[type, str | None] = {}
        self.relationships: list[_RefInfo] = []

        # Initialize attributes with defaults before applying configuration
        self.storage_factory = MemoryStorageFactory()
        self.blob_store = MemoryBlobStore()
        self.model_naming = "kebab"
        self.message_queue_factory = None
        self.route_templates: list[IRouteTemplate] = []
        self.permission_checker = AllowAll()
        self.event_handlers = None
        self.default_encoding = Encoding.json
        self.default_user = UNSET
        self.default_now = UNSET
        self.default_status: RevisionStatus | UnsetType = UNSET
        self.strict_operation_context = False
        self.forbid_unknown_fields = False
        self._pending_create_actions: list[_PendingCreateAction] = []
        self._pending_update_actions: list[_PendingUpdateAction] = []
        self.backend: BackendConfig | None = None

        # Vector + Embedding: encoder registry shared across all models
        from specstar.resource_manager.encoder_registry import EncoderRegistry

        self.encoder_registry = EncoderRegistry()

        # Apply configuration using shared logic
        self._apply_configuration(
            model_naming=model_naming,
            route_templates=route_templates,
            backend=backend,
            storage_factory=storage_factory,
            message_queue_factory=message_queue_factory,
            admin=admin,
            permission_checker=permission_checker,
            dependency_provider=dependency_provider,
            event_handlers=event_handlers,
            encoding=encoding,
            default_user=default_user,
            default_now=default_now,
            default_status=default_status,
            strict_operation_context=strict_operation_context,
            forbid_unknown_fields=forbid_unknown_fields,
        )

    def _apply_configuration(
        self,
        *,
        model_naming: Literal["same", "pascal", "camel", "snake", "kebab"]
        | Callable[[type], str]
        | UnsetType = UNSET,
        route_templates: list[IRouteTemplate]
        | dict[type, dict[str, Any]]
        | None
        | UnsetType = UNSET,
        backend: BackendConfig | dict[str, Any] | str | Path | None | UnsetType = UNSET,
        storage_factory: IStorageFactory | None | UnsetType = UNSET,
        message_queue_factory: IMessageQueueFactory | None | UnsetType = UNSET,
        admin: str | None | UnsetType = UNSET,
        permission_checker: IPermissionChecker | None | UnsetType = UNSET,
        dependency_provider: DependencyProvider | None | UnsetType = UNSET,
        event_handlers: Sequence[IEventHandler] | None | UnsetType = UNSET,
        encoding: Encoding | UnsetType = UNSET,
        default_user: str | Callable[[], str] | UnsetType = UNSET,
        default_now: Callable[[], dt.datetime] | UnsetType = UNSET,
        default_status: RevisionStatus | UnsetType = UNSET,
        strict_operation_context: bool | UnsetType = UNSET,
        forbid_unknown_fields: bool | UnsetType = UNSET,
    ) -> None:
        """Apply configuration settings to the SpecStar instance.

        This internal method contains the shared logic for both __init__ and configure.
        It handles UNSET values to allow partial updates in configure() while still
        working with direct values in __init__().
        """
        # Update model_naming
        if model_naming is not UNSET:
            self.model_naming = model_naming

        # Update backend / storage / blob / message queue through one resolver
        has_unified_backend = backend is not UNSET and backend is not None
        if (
            has_unified_backend
            or storage_factory is not UNSET
            or message_queue_factory is not UNSET
        ):
            legacy_storage_factory = (
                self.storage_factory
                if storage_factory is UNSET
                else (
                    MemoryStorageFactory()
                    if storage_factory is None
                    else storage_factory
                )
            )

            if message_queue_factory is UNSET:
                legacy_message_queue_factory = self.message_queue_factory
            elif message_queue_factory is None:
                from specstar.message_queue.simple import SimpleMessageQueueFactory

                legacy_message_queue_factory = SimpleMessageQueueFactory()
            else:
                legacy_message_queue_factory = message_queue_factory

            bundle = build_backend_bundle(
                backend if has_unified_backend else None,
                storage_factory=legacy_storage_factory,
                message_queue_factory=legacy_message_queue_factory,
            )
            self.backend = bundle.config
            self.storage_factory = bundle.storage_factory
            self.blob_store = bundle.blob_store
            self.message_queue_factory = bundle.message_queue_factory

        # Update route_templates
        # If dependency_provider or default_user is changed, we need to
        # rebuild route_templates so the DependencyProvider picks up the
        # correct default user.
        rebuild_templates = route_templates is not UNSET or (
            (dependency_provider is not UNSET or default_user is not UNSET)
            and route_templates is UNSET
        )

        if rebuild_templates:
            self.route_templates = []
            if (
                route_templates is UNSET
                or route_templates is None
                or isinstance(route_templates, dict)
            ):
                route_templates_dict = (
                    route_templates if isinstance(route_templates, dict) else {}
                )
                dep_provider = (
                    dependency_provider if dependency_provider is not UNSET else None
                )

                # Propagate default_user to the DependencyProvider so that
                # route handlers receive the configured user instead of
                # "anonymous" when no custom get_user is set.
                effective_default_user = (
                    default_user if default_user is not UNSET else self.default_user
                )
                if effective_default_user is not UNSET:
                    base_dp = dep_provider or DependencyProvider()
                    dep_provider = base_dp.with_default_user(effective_default_user)

                for rt in [
                    CreateRouteTemplate,
                    ListRouteTemplate,
                    ReadRouteTemplate,
                    UpdateRouteTemplate,
                    PatchRouteTemplate,
                    SwitchRevisionRouteTemplate,
                    RerunRouteTemplate,
                    JobLogsRouteTemplate,
                    DeleteRouteTemplate,
                    PermanentlyDeleteRouteTemplate,
                    RestoreRouteTemplate,
                    BatchDeleteRouteTemplate,
                    BatchRestoreRouteTemplate,
                    ExportRouteTemplate,
                    ImportRouteTemplate,
                    BlobRouteTemplate,
                ]:
                    more_kwargs = route_templates_dict.get(rt, {})
                    more_kwargs.setdefault("dependency_provider", dep_provider)
                    self.route_templates.append(rt(**more_kwargs))
            else:
                self.route_templates = route_templates

        # Update permission_checker
        if permission_checker is not UNSET:
            if permission_checker is None:
                # Determine based on admin setting
                if admin is not UNSET:
                    if not admin:
                        self.permission_checker = AllowAll()
                    else:
                        self.permission_checker = RBACPermissionChecker(
                            storage_factory=self.storage_factory,
                            root_user=admin,
                        )
                else:
                    # Default when permission_checker=None but admin not provided
                    self.permission_checker = AllowAll()
            else:
                self.permission_checker = permission_checker
        elif admin is not UNSET:
            # admin changed but permission_checker not explicitly set
            if not admin:
                self.permission_checker = AllowAll()
            else:
                self.permission_checker = RBACPermissionChecker(
                    storage_factory=self.storage_factory,
                    root_user=admin,
                )

        # Update event_handlers
        if event_handlers is not UNSET:
            self.event_handlers = event_handlers

        # Update encoding
        if encoding is not UNSET:
            self.default_encoding = encoding

        # Update default_user
        if default_user is not UNSET:
            self.default_user = default_user

        # Update default_now
        if default_now is not UNSET:
            self.default_now = default_now

        # Update default_status
        if default_status is not UNSET:
            self.default_status = default_status

        # Update strict_operation_context
        if strict_operation_context is not UNSET:
            self.strict_operation_context = strict_operation_context

        # Update forbid_unknown_fields
        if forbid_unknown_fields is not UNSET:
            self.forbid_unknown_fields = forbid_unknown_fields

    def configure(
        self,
        *,
        model_naming: Literal["same", "pascal", "camel", "snake", "kebab"]
        | Callable[[type], str]
        | UnsetType = UNSET,
        route_templates: list[IRouteTemplate]
        | dict[type, dict[str, Any]]
        | UnsetType = UNSET,
        backend: BackendConfig | dict[str, Any] | str | Path | None | UnsetType = UNSET,
        storage_factory: IStorageFactory | None | UnsetType = UNSET,
        message_queue_factory: IMessageQueueFactory | None | UnsetType = UNSET,
        admin: str | None | UnsetType = UNSET,
        permission_checker: IPermissionChecker | UnsetType = UNSET,
        dependency_provider: DependencyProvider | UnsetType = UNSET,
        event_handlers: Sequence[IEventHandler] | UnsetType = UNSET,
        encoding: Encoding | UnsetType = UNSET,
        default_user: str | Callable[[], str] | UnsetType = UNSET,
        default_now: Callable[[], dt.datetime] | UnsetType = UNSET,
        default_status: RevisionStatus | UnsetType = UNSET,
        strict_operation_context: bool | UnsetType = UNSET,
        forbid_unknown_fields: bool | UnsetType = UNSET,
        vector_encoders: dict[str, Callable] | UnsetType = UNSET,
    ) -> None:
        """Configure the SpecStar instance dynamically.

        This method allows you to reconfigure an existing SpecStar instance,
        useful for the global instance pattern where you import a pre-created
        instance and configure it later in your application startup.

        Warning:
            This method should only be called during application initialization,
            before any models are registered or routes are applied. Calling this
            after models have been registered may lead to inconsistent behavior.

        Args:
            model_naming: Controls how model names are converted to URL paths.
            route_templates: Custom list of route templates or configuration dict.
            backend: Unified backend configuration. Accepts a typed config object,
                a plain dict, or a JSON file path.
            storage_factory: Lower-level storage backend to use for all models.
                This path offers more direct control than the unified ``backend=`` API.
            message_queue_factory: Lower-level message queue factory for async job
                processing.
            admin: Admin user for RBAC permission system.
            permission_checker: Custom permission checker implementation.
            dependency_provider: Dependency injection provider for routes.
            event_handlers: List of event handlers for lifecycle hooks.
            encoding: Default encoding format (json/msgpack).
            default_user: Default user for operations when not specified.  When set,
                the ``DependencyProvider``'s default ``get_user`` will return this
                value instead of ``"anonymous"``.  A custom ``get_user`` on the
                provider always takes priority.
            default_now: Default timestamp function for operations.
            default_status: Default revision status applied when registering models
                via :meth:`add_model` (e.g. ``RevisionStatus.draft``). Per-model
                ``default_status`` on ``add_model`` overrides this. If neither is
                set, ``ResourceManager`` falls back to ``RevisionStatus.stable``.
            strict_operation_context: When ``True``, write operations on all
                registered models will raise
                :class:`MissingOperationContextError` if ``user`` and ``now``
                are not resolved from any source (explicit kwargs,
                ``using()`` scope, or manager defaults).
            forbid_unknown_fields: When ``True``, dict / JSON inputs to
                ``create()`` / ``update()`` / ``modify()`` containing keys
                that are not declared on the registered ``Struct`` raise
                :class:`specstar.types.ValidationError` (HTTP 422) instead of
                being silently dropped. Defaults to ``False`` — kept off to
                preserve current behavior; turn it on at the start of a new
                project or as part of a coordinated 1.0 cutover.

        Example:
            ```python
            from specstar import BackendBinding, BackendConfig, ConnectionProfile, spec

            # Configure the global instance with the higher-level backend API
            spec.configure(
                backend=BackendConfig(
                    connections={
                        "local": ConnectionProfile(
                            type="disk",
                            options={"rootdir": "./data"},
                        )
                    },
                    meta=BackendBinding(use="local"),
                    resource=BackendBinding(use="local"),
                    blob=BackendBinding(use="local"),
                ),
                model_naming="snake",
                admin="root@example.com",
            )

            # Now register models
            spec.add_model(User)
            ```
        """
        if self.resource_managers:
            logger.warning(
                "configure() called after models have been registered. "
                "This may lead to inconsistent behavior."
            )

        # Apply configuration using shared logic
        self._apply_configuration(
            model_naming=model_naming,
            route_templates=route_templates,
            backend=backend,
            storage_factory=storage_factory,
            message_queue_factory=message_queue_factory,
            admin=admin,
            permission_checker=permission_checker,
            dependency_provider=dependency_provider,
            event_handlers=event_handlers,
            encoding=encoding,
            default_user=default_user,
            default_now=default_now,
            default_status=default_status,
            strict_operation_context=strict_operation_context,
            forbid_unknown_fields=forbid_unknown_fields,
        )

        # Register vector encoders into the registry
        if vector_encoders is not UNSET:
            for name, fn in vector_encoders.items():
                self.encoder_registry.register(name, fn)

    def get_resource_manager(self, model: type[T] | str) -> IResourceManager[T]:
        """Get the resource manager for a registered model.

        This method allows you to access the underlying ResourceManager for a specific model.
        The ResourceManager provides low-level access to storage, events, and other
        internal components for that model.

        Args:
            model: The model class or its registered resource name.

        Returns:
            The IResourceManager instance associated with the model.

        Raises:
            KeyError: If the model is not registered.
            ValueError: If the model class is registered with multiple names (ambiguous).

        Example:
            ```python
            # Get by model class
            manager = specstar.get_resource_manager(User)

            # Get by resource name
            manager = specstar.get_resource_manager("users")

            # Access underlying storage
            storage = manager.storage
            ```
        """
        if isinstance(model, str):
            return self.resource_managers[model]
        model_name = self.model_names[model]
        if model_name is None:
            raise ValueError(
                f"Model {get_type_name(model) or repr(model)} is registered with multiple names."
            )
        return self.resource_managers[model_name]

    def _is_job_subclass(self, model: type) -> bool:
        """Check if a model is a subclass of Job.

        Args:
            model: The model class to check.

        Returns:
            True if the model is a Job subclass, False otherwise.
        """
        return is_generic_subclass(model, Job)

    def _resource_name(self, model: type[T]) -> str:
        """Convert model class name to resource name using the configured naming convention.

        This internal method handles the conversion of Python class names to URL-friendly
        resource names based on the model_naming configuration.

        Args:
            model: The model class whose name should be converted.

        Returns:
            The converted resource name string that will be used in URLs.

        Examples:
            With model_naming="kebab":
            - UserProfile -> "user-profile"
            - BlogPost -> "blog-post"

            With model_naming="snake":
            - UserProfile -> "user_profile"
            - BlogPost -> "blog_post"

            With custom function:
            - Can implement any custom naming logic
        """
        if callable(self.model_naming):
            return self.model_naming(model)
        original_name = get_type_name(model)
        if original_name is None:
            raise ValueError(
                f"Cannot automatically infer a resource name for type {model!r}. "
                f"Please provide a name explicitly via "
                f"add_model(..., name='your_name')."
            )

        # 使用 NameConverter 進行轉換
        return NameConverter(original_name).to(self.model_naming)

    def add_route_template(self, template: IRouteTemplate) -> None:
        """Add a custom route template to extend the API with additional endpoints.

        Route templates define how to generate specific API endpoints for models.
        By adding custom templates, you can extend the default CRUD functionality
        with specialized endpoints for your use cases.

        If a template of the **same type** already exists (e.g. added by the
        default ``configure()``), it is **replaced** rather than duplicated.
        This prevents ``Duplicate Operation ID`` warnings for templates that
        mount global routes such as ``BlobRouteTemplate`` and
        ``GraphQLRouteTemplate``.

        Args:
            template: A custom route template implementing IRouteTemplate interface.

        Example:
            ```python
            class CustomSearchTemplate(BaseRouteTemplate):
                def apply(self, model_name, resource_manager, router):
                    @router.get(f"/{model_name}/search")
                    async def search_resources(query: str):
                        # Custom search logic
                        pass


            specstar = SpecStar()
            specstar.add_route_template(CustomSearchTemplate())
            specstar.add_model(User)
            ```

        Note:
            Templates are sorted by their order property before being applied.
            Add templates before calling add_model() or apply() for best results.
        """
        # Replace any existing template of the same type to avoid duplicates.
        # This is important for templates that mount global routes (e.g.
        # BlobRouteTemplate, GraphQLRouteTemplate) — having two instances
        # would register the same path twice, producing a FastAPI
        # "Duplicate Operation ID" warning.
        template_type = type(template)
        self.route_templates = [
            t for t in self.route_templates if type(t) is not template_type
        ]
        self.route_templates.append(template)

    def create_action(
        self,
        resource_name: str,
        *,
        path: str | None = None,
        label: str | None = None,
        async_mode: Literal["job", "background"] | None = None,
        job_name: str | None = None,
    ) -> Callable:
        """Decorator to register a custom create action for a resource.

        The decorated function is a standard FastAPI endpoint handler — all input
        parsing (``Body``, ``Query``, ``Path``, ``Depends``, etc.) is handled by
        FastAPI.  If the handler returns a resource-type object, SpecStar will
        automatically call ``resource_manager.create()`` and respond with
        ``RevisionInfo``.  If it returns ``None``, no automatic creation occurs.

        When ``async_mode='job'`` is set, the framework automatically:

        1. Generates a ``Job`` model with the handler's body type as payload.
        2. Registers the Job model with a message queue.
        3. On POST, creates a Job instance (PENDING) and enqueues it.
        4. Returns HTTP 202 with :class:`~specstar.types.JobRedirectInfo`.
        5. In the background, executes the handler with the payload.
        6. If the handler returns a resource object, auto-creates it and
           stores the ``RevisionInfo`` as the Job's artifact.

        When ``async_mode='background'`` is set, the framework:

        1. On POST, schedules the handler via FastAPI ``BackgroundTasks``.
        2. Returns HTTP 202 with :class:`~specstar.types.BackgroundTaskAccepted`
           immediately.
        3. The handler runs in the background; if it returns a resource object,
           ``resource_manager.create()`` is called automatically.
        4. No Job model is created — the task is fire-and-forget.
        5. Errors are logged but not surfaced to the client.

        This mode is suitable for tasks that take a few seconds to complete
        and do not require progress tracking.

        Args:
            resource_name: The name of the resource this action belongs to.
            path: URL path suffix (e.g. ``"import-from-url"``).  If ``None``,
                inferred from the function name (underscores → hyphens).
            label: Human-friendly label shown in the UI.  If ``None``,
                inferred from *path* (hyphens → spaces, title-cased).
            async_mode: Execution mode for the action.  ``None`` (default)
                executes synchronously.  ``'job'`` executes asynchronously
                via the message queue system.  ``'background'`` executes
                asynchronously via FastAPI ``BackgroundTasks``
                (fire-and-forget, no Job tracking).
            job_name: Custom resource name for the auto-generated Job model
                (e.g. ``"my-custom-job"``).  If ``None``, derived automatically
                from *path* and *resource_name*.  Only meaningful when
                ``async_mode='job'``.

        Returns:
            A decorator that registers the handler and returns it unchanged.

        Example:
            ```python
            class ImportFromUrl(Struct):
                url: str


            @spec.create_action("article", label="Import from URL")
            async def import_from_url(body: ImportFromUrl = Body(...)):
                content = await fetch_and_parse(body.url)
                return Article(content=content)  # auto-created


            class GenerateRequest(Struct):
                prompt: str


            @spec.create_action("article", async_mode="job", label="Generate")
            def generate_article(payload: GenerateRequest = Body(...)) -> Article:
                content = call_llm(payload.prompt)  # long-running
                return Article(content=content)  # auto-created in background
            ```

        Note:
            This decorator is lazy — it stores metadata without registering any
            route.  Routes are created when ``apply()`` is called, so the
            decorator can be used before or after ``add_model()``.
        """

        def decorator(func: Callable) -> Callable:
            action_path = path or getattr(func, "__name__", "action").replace("_", "-")
            action_label = label or action_path.replace("-", " ").title()
            self._pending_create_actions.append(
                _PendingCreateAction(
                    resource_name=resource_name,
                    path=action_path,
                    label=action_label,
                    handler=func,
                    async_mode=async_mode,
                    job_name=job_name,
                )
            )
            return func

        return decorator

    def update_action(
        self,
        resource_name: str,
        *,
        path: str | None = None,
        label: str | None = None,
        mode: Literal["update", "modify"] = "update",
        existing_param: str = "existing",
        info_param: str = "info",
        meta_param: str = "meta",
        async_mode: Literal["job", "background"] | None = None,
        job_name: str | None = None,
    ) -> Callable:
        """Decorator to register a custom update action for a resource.

        The decorated function receives the existing resource data (auto-injected)
        and any custom input parameters.  If the handler returns a resource-type
        object, SpecStar will automatically call ``resource_manager.update()`` (or
        ``resource_manager.modify()`` when ``mode='modify'``) and respond with
        ``RevisionInfo``.  If it returns ``None``, no update occurs.

        The existing resource data is automatically fetched via
        ``resource_manager.get(resource_id)`` and injected into the handler
        parameter named by *existing_param* (default ``"existing"``).

        Similarly, the handler may declare parameters named *info_param*
        (default ``"info"``) and *meta_param* (default ``"meta"``) to
        receive the existing resource's ``RevisionInfo`` and ``ResourceMeta``
        respectively.  Like *existing_param*, these are detected by
        **parameter name** and only injected when the handler declares them.

        When ``async_mode='job'`` is set, the framework automatically:

        1. Generates a ``Job`` model with the handler's body type as payload
           (plus an auto-injected ``resource_id`` field).
        2. Registers the Job model with a message queue.
        3. On POST, creates a Job instance (PENDING) and enqueues it.
        4. Returns HTTP 202 with :class:`~specstar.types.JobRedirectInfo`.
        5. In the background, fetches existing resource (lazy), executes
           the handler with the payload and existing data.
        6. If the handler returns a resource object, auto-updates it and
           stores the ``RevisionInfo`` as the Job's artifact.

        When ``async_mode='background'`` is set, the framework:

        1. On POST, schedules the handler via FastAPI ``BackgroundTasks``.
        2. Returns HTTP 202 with :class:`~specstar.types.BackgroundTaskAccepted`
           immediately.
        3. The handler runs in the background; if it returns a resource object,
           ``resource_manager.update()`` (or ``modify()``) is called
           automatically.
        4. No Job model is created — the task is fire-and-forget.
        5. Errors are logged but not surfaced to the client.

        Args:
            resource_name: The name of the resource this action belongs to.
            path: URL path suffix (e.g. ``"level-up"``).  If ``None``,
                inferred from the function name (underscores → hyphens).
            label: Human-friendly label shown in the UI.  If ``None``,
                inferred from *path* (hyphens → spaces, title-cased).
            mode: Update mode.  ``"update"`` (default) creates a new
                revision.  ``"modify"`` performs an in-place edit (only
                valid for draft-status resources).
            existing_param: The handler parameter name into which the
                existing resource data will be injected.  Defaults to
                ``"existing"``.
            info_param: The handler parameter name into which the
                existing resource's ``RevisionInfo`` will be injected.
                Defaults to ``"info"``.
            meta_param: The handler parameter name into which the
                existing resource's ``ResourceMeta`` will be injected.
                Defaults to ``"meta"``.
            async_mode: Execution mode for the action.  ``None`` (default)
                executes synchronously.  ``'job'`` executes asynchronously
                via the message queue system.  ``'background'`` executes
                asynchronously via FastAPI ``BackgroundTasks``
                (fire-and-forget, no Job tracking).
            job_name: Custom resource name for the auto-generated Job model
                (e.g. ``"my-custom-job"``).  If ``None``, derived automatically
                from *path* and *resource_name*.  Only meaningful when
                ``async_mode='job'``.

        Returns:
            A decorator that registers the handler and returns it unchanged.

        Example:
            ```python
            class LevelUpInput(Struct):
                levels: int = 1


            @spec.update_action("character", label="Level Up")
            def level_up(
                existing: Character,
                body: LevelUpInput = Body(...),
            ) -> Character:
                return Character(
                    name=existing.name,
                    level=existing.level + body.levels,
                )


            @spec.update_action(
                "character",
                label="Train",
                async_mode="job",
            )
            def train(
                existing: Character,
                body: LevelUpInput = Body(...),
            ) -> Character:
                import time

                time.sleep(10)  # long-running training
                return Character(
                    name=existing.name,
                    level=existing.level + body.levels,
                )


            @spec.update_action(
                "character",
                label="Background Heal",
                async_mode="background",
            )
            def bg_heal(existing: Character) -> Character:
                import time

                time.sleep(5)
                return Character(name=existing.name, level=existing.level + 1)
            ```

        Note:
            This decorator is lazy — it stores metadata without registering any
            route.  Routes are created when ``apply()`` is called.
            The route is ``POST /{resource_name}/{resource_id}/{action_path}``.
        """

        def decorator(func: Callable) -> Callable:
            action_path = path or getattr(func, "__name__", "action").replace("_", "-")
            action_label = label or action_path.replace("-", " ").title()
            self._pending_update_actions.append(
                _PendingUpdateAction(
                    resource_name=resource_name,
                    path=action_path,
                    label=action_label,
                    handler=func,
                    mode=mode,
                    existing_param=existing_param,
                    info_param=info_param,
                    meta_param=meta_param,
                    async_mode=async_mode,
                    job_name=job_name,
                )
            )
            return func

        return decorator

    def add_model(
        self,
        model: "type[T] | Schema[T]",
        *,
        name: str | None = None,
        id_generator: Callable[[], str] | None = None,
        storage: IStorage | None = None,
        migration: "IMigration | Schema | None" = None,
        indexed_fields: list[str | tuple[str, type] | IndexableField] | None = None,
        event_handlers: Sequence[IEventHandler] | None = None,
        permission_checker: IPermissionChecker | None = None,
        encoding: Encoding | None = None,
        default_status: RevisionStatus | UnsetType = UNSET,
        default_user: str | Callable[[], str] | UnsetType = UNSET,
        default_now: Callable[[], dt.datetime] | UnsetType = UNSET,
        message_queue_factory: IMessageQueueFactory | None | UnsetType = UNSET,
        job_handler: Callable[[Resource[Job[T]]], None] | None = None,
        job_handler_factory: Callable[[], Callable[[Resource[Job[T]]], None]]
        | None = None,
        validator: "Callable[[T], None] | IValidator | type | None" = None,
        constraint_checkers: "Sequence[IConstraintChecker | Callable[[ResourceManager], IConstraintChecker]] | None" = None,
        vector_encoders: dict[str, str | Callable] | None = None,
    ) -> None:
        """Register a resource model (or `Schema`) and create its `ResourceManager`.

        After a model is registered, calling `apply(router)` will generate FastAPI routes for it
        using the configured route templates.

        You can register either:
        - a plain model type: `add_model(User)`
        - a `Schema`: `add_model(Schema(User, version=...))`

        Args:
            model:
                Resource type or `Schema`. Supported types depend on your project setup, commonly
                msgspec `Struct`. Pydantic `BaseModel` is supported and will be converted to a struct.
            name:
                Resource name (used as route base path). If `None`, derived from the model type and
                `model_naming`.
            id_generator:
                Custom ID generator for created resources. If `None`, the default generator is used
                by `ResourceManager`.
            storage:
                Storage instance for this resource. If `None`, a storage is created via
                `self.storage_factory.build(model_name)`.
            migration:
                Schema/migration configuration.
                - If `model` is a `Schema`, `migration` must be `None`.
                - If `migration` is a `Schema`, it is used as the resolved schema for this model.
                - Passing `IMigration` is supported but **deprecated** (converted via `Schema.from_legacy`).
            indexed_fields:
                Fields to index for search/query. Each element can be:
                - `IndexableField`
                - `str` (field path)
                - `(field_path: str, field_type: type)` tuple
            event_handlers:
                Per-model event handlers. If `self.event_handlers` is configured globally, it takes
                precedence; otherwise these handlers are used.
            permission_checker:
                Per-model permission checker. If `self.permission_checker` is configured globally, it
                takes precedence; otherwise this checker is used.
            encoding:
                Encoding for stored payloads. If `None`, uses `self.default_encoding`.
            default_status:
                Per-model default revision status. If `UNSET`, falls back to
                `self.default_status` when configured; otherwise `ResourceManager`'s
                own default (`RevisionStatus.stable`) applies.
            default_user:
                Per-model default user (or factory). If `UNSET`, falls back to `self.default_user`
                when configured.
            default_now:
                Per-model default timestamp function. If `UNSET`, falls back to `self.default_now`
                when configured.
            message_queue_factory:
                Overrides message queue behavior for Job models:
                - `UNSET`: use `self.message_queue_factory`
                - `None`: explicitly disable queue
                - factory instance: use the provided factory
            job_handler:
                Handler for Job resources (when the model is detected as a Job subclass).
            job_handler_factory:
                Lazy factory producing a job handler. If provided, it is wrapped as a lazy handler.
            validator:
                Validation hook(s). When the model is a Pydantic `BaseModel` and no validator is set
                on the resolved schema, the Pydantic model is used as validator by default.
            constraint_checkers:
                Extra constraint checkers for this resource. Each element can be an instance or a
                factory callable that receives the `ResourceManager` and returns a checker.

        Behavior:
            - If `model` is a `Schema`, it must declare `resource_type`; schema-level migration/validator
            should be provided on the `Schema` itself.
            - If the model is a Pydantic type, it is converted to a struct for storage and the Pydantic
            model can be used for validation.
            - Ref relationships are collected from `Ref` / `RefRevision` annotations for later route and
            referential integrity setup.
            - Ref fields (resource_id refs only) are auto-indexed for searchability.
            - For Job models with a message queue enabled, `status` and `retries` are auto-indexed
            (if not already present in `indexed_fields`).

        Raises:
            ValueError:
                - if the resource name already exists
                - if `Schema` is passed as first argument but `migration`/`validator` is also provided
                - if `Ref(..., on_delete=set_null)` is used on a non-optional field
            TypeError:
                - if `indexed_fields` contains an invalid item

        Examples:
            Basic registration:

            ```python
            from specstar import SpecStar

            specstar = SpecStar()
            specstar.add_model(User)
            ```

            Custom resource name:

            ```python
            specstar.add_model(User, name="people")
            ```

            Provide explicit storage:

            ```python
            # storage is per-model; if you want a default for all models, pass `storage_factory=...`
            # when constructing SpecStar / calling configure().
            model_name = "people"
            st = specstar.storage_factory.build(model_name)
            specstar.add_model(User, name=model_name, storage=st)
            ```

            Using Schema as the first argument:

            ```python
            schema = Schema(User, version="v1")
            specstar.add_model(schema)
            ```
        """
        _indexed_fields: list[IndexableField] = []
        for field in indexed_fields or []:
            if isinstance(field, IndexableField):
                _indexed_fields.append(field)
            elif (
                isinstance(field, tuple)
                and len(field) == 2
                and isinstance(field[0], str)
            ):
                field = IndexableField(field_path=field[0], field_type=field[1])
                _indexed_fields.append(field)
            elif isinstance(field, str):
                field = IndexableField(field_path=field, field_type=UNSET)
                _indexed_fields.append(field)
            else:
                raise TypeError(
                    "Invalid indexed field, should be IndexableField or tuple[field_name, field_type]",
                )

        # ── Resolve Schema vs type argument ────────────────────────
        resolved_schema: Schema | None = None
        resolved_model: type
        if isinstance(model, Schema):
            # Schema passed as first argument
            if migration is not None:
                raise ValueError(
                    "Cannot specify 'migration' when passing Schema as the first argument. "
                    "Define migration steps on the Schema instead."
                )
            if validator is not None:
                raise ValueError(
                    "Cannot specify 'validator' when passing Schema as the first argument. "
                    "Pass validator to Schema(..., validator=...) instead."
                )
            resolved_schema = model
            schema_type = resolved_schema.resource_type
            if schema_type is None:
                raise ValueError(
                    "Schema passed as first argument must have a resource_type."
                )
            resolved_model = schema_type
        else:
            # model is a plain type
            resolved_model = model
            if isinstance(migration, Schema):
                resolved_schema = migration
            elif isinstance(migration, IMigration):
                warnings.warn(
                    "Passing IMigration to migration= is deprecated. "
                    "Use Schema(resource_type, version).step(...) instead.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                resolved_schema = Schema.from_legacy(migration)
            # else migration is None → no schema

        model_name = name or self._resource_name(resolved_model)

        # Handle Pydantic BaseModel as model type:
        # auto-generate struct and use Pydantic for validation
        pydantic_model: type | None = None
        if is_pydantic_model(resolved_model):
            # ``is_pydantic_model`` runtime-narrows to ``type[BaseModel]``
            # but ty doesn't track the BaseModel constraint through it.
            pydantic_model = resolved_model
            resolved_model = pydantic_to_struct(cast(Any, pydantic_model))
            if validator is None and (
                resolved_schema is None or not resolved_schema.has_validator
            ):
                validator = pydantic_model

        if model_name in self.resource_managers:
            raise ValueError(f"Model name {model_name} already exists.")
        if resolved_model in self.model_names:
            self.model_names[resolved_model] = None
            logger.warning(
                f"Model {get_type_name(resolved_model) or repr(resolved_model)} is already registered with a different name. "
                f"This resource manager will not be accessible by its type.",
            )
        else:
            self.model_names[resolved_model] = model_name
        if storage is None:
            storage = self.storage_factory.build(model_name)
        if encoding is None:
            encoding = self.default_encoding
        other_options = {}
        if default_status is not UNSET:
            other_options["default_status"] = default_status
        elif self.default_status is not UNSET:
            other_options["default_status"] = self.default_status
        if default_user is not UNSET:
            other_options["default_user"] = default_user
        elif self.default_user is not UNSET:
            other_options["default_user"] = self.default_user
        if default_now is not UNSET:
            other_options["default_now"] = default_now
        elif self.default_now is not UNSET:
            other_options["default_now"] = self.default_now
        # Auto-detect Job subclass and create message queue
        if self._is_job_subclass(resolved_model) and (
            job_handler is not None or job_handler_factory is not None
        ):
            # Determine which factory to use
            if message_queue_factory is UNSET:
                mq_factory = self.message_queue_factory
            elif message_queue_factory is None:
                mq_factory = None  # Explicitly disabled
            else:
                mq_factory = message_queue_factory

            if mq_factory is not None:
                if job_handler_factory is not None:
                    real_handler: Callable[[Resource[Job[T]]], None] = LazyJobHandler(
                        job_handler_factory
                    )
                else:
                    assert job_handler is not None  # outer guard
                    real_handler = job_handler

                # Create message queue with job handler
                other_options["message_queue"] = mq_factory.build(real_handler)

                # Check if status is already in indexed fields
                if not any(field.field_path == "status" for field in _indexed_fields):
                    _indexed_fields.append(
                        IndexableField(field_path="status", field_type=TaskStatus)
                    )

                # Check if retries is already in indexed fields
                if not any(field.field_path == "retries" for field in _indexed_fields):
                    _indexed_fields.append(
                        IndexableField(field_path="retries", field_type=int)
                    )

        # Auto-mount dim validator for any Vector / Embedding fields
        from specstar.resource_manager.vector_validator import (
            CompositeValidator,
            VectorDimValidator,
        )
        from specstar.types import extract_vector_field_infos

        vector_infos = extract_vector_field_infos(resolved_model)
        if vector_infos:
            dim_validator = VectorDimValidator(resolved_model)
            if validator is None:
                validator = dim_validator
            else:
                validator = CompositeValidator([dim_validator, validator])

            # Make vector values searchable via indexed_data (brute-force
            # backends use this; pgvector backend reads it for indexed copy).
            # For Embedding fields, extract from "<name>.vector" but expose
            # the value under the short alias "<name>" so QB["<name>"]
            # matches naturally.
            existing_keys = {(f.index_key or f.field_path) for f in _indexed_fields}
            for vinfo in vector_infos:
                if vinfo.is_embedding:
                    field_path = f"{vinfo.name}.vector"
                    index_key = vinfo.name
                else:
                    field_path = vinfo.name
                    index_key = None
                key_in_use = index_key or field_path
                if key_in_use not in existing_keys:
                    _indexed_fields.append(
                        IndexableField(
                            field_path=field_path,
                            field_type=list,
                            index_key=index_key,
                        )
                    )

        # ResourceManager binds T from ``resolved_model`` (typed as bare
        # ``type`` after Pydantic conversion), erasing the caller's T.
        # Cast the parameterised inputs to the corresponding T-erased
        # form so ty can match against ``IMigration[object]`` etc.
        resource_manager = ResourceManager(
            resolved_model,
            storage=storage,
            blob_store=self.blob_store,
            id_generator=id_generator,
            migration=cast("IMigration | Schema | None", resolved_schema or migration),
            indexed_fields=_indexed_fields,
            event_handlers=self.event_handlers or event_handlers,
            permission_checker=self.permission_checker or permission_checker,
            encoding=encoding,
            name=model_name,
            validator=cast(
                "Callable[[Any], None] | IValidator | type | None", validator
            ),
            pydantic_type=pydantic_model,
            constraint_checkers=constraint_checkers,
            strict_operation_context=self.strict_operation_context,
            forbid_unknown_fields=self.forbid_unknown_fields,
            encoder_registry=self.encoder_registry,
            vector_encoders=vector_encoders,
            **other_options,
        )
        self.resource_managers[model_name] = resource_manager

        # If meta store supports native vector indexing, register pgvector
        # columns + HNSW indices for each Vector / Embedding field
        meta_store = getattr(resource_manager.storage, "_meta_store", None)
        if (
            vector_infos
            and meta_store is not None
            and getattr(meta_store, "supports_native_vector_search", False)
            and hasattr(meta_store, "ensure_vector_column")
        ):
            for vinfo in vector_infos:
                # Use the short alias (matches the indexed_data key).
                meta_store.ensure_vector_column(
                    vinfo.name,
                    dim=vinfo.marker.dim,
                    distance=vinfo.marker.distance or "cosine",
                )

        # Scan Ref / RefRevision annotations and collect relationships
        refs = extract_refs(resolved_model, model_name)
        self.relationships.extend(refs)
        # Validate set_null requires nullable field
        for ref_info in refs:
            if ref_info.on_delete == OnDelete.set_null and not ref_info.nullable:
                raise ValueError(
                    f"Ref on '{get_type_name(model) or repr(model)}.{ref_info.source_field}' uses "
                    f"on_delete=set_null but the field is not Optional. "
                    f"Use Annotated[str | None, Ref(...)] instead."
                )

        # Auto-index Ref fields (resource_id refs only) for searchability
        for ref_info in refs:
            if ref_info.ref_type == "resource_id":
                # Use list[str] for list refs, str for scalar refs
                field_type = list[str] if ref_info.is_list else str
                resource_manager.add_indexed_field(
                    IndexableField(
                        field_path=ref_info.source_field,
                        field_type=field_type,
                    )
                )

    def openapi(self, app: FastAPI, structs: list[type] | None = None) -> None:
        """Generate and register the OpenAPI schema for the FastAPI application.

        This method customizes the OpenAPI schema generation to include all the
        SpecStar-specific types, models, and response schemas. It ensures that
        the generated API documentation (Swagger UI / ReDoc) correctly reflects
        the structure of your resources and their endpoints.

        Args:
            app: The FastAPI application instance.
            structs: Optional list of additional msgspec Structs to include in the schema.

        Note:
            When :meth:`apply` is called with a ``FastAPI`` instance as the
            first argument, this method is called automatically at the end of
            ``apply()``.  You only need to call it manually if you passed a
            bare ``APIRouter`` to ``apply()`` or need to customise the
            ``structs`` parameter separately.
        """
        from specstar.crud.openapi_builder import OpenAPIBuilder

        OpenAPIBuilder(
            resource_managers=self.resource_managers,
            route_templates=self.route_templates,
            pending_create_actions=self._pending_create_actions,
            pending_update_actions=self._pending_update_actions,
            async_job_registry=getattr(self, "_async_job_registry", {}),
            async_update_job_registry=getattr(self, "_async_update_job_registry", {}),
        ).customize(app, structs)

    def _install_ref_integrity_handlers(self) -> None:
        install_ref_integrity_handlers(self.relationships, self.resource_managers)

    @staticmethod
    def _inline_embedded_schema_ref(schema_extra: dict, source_type: Any) -> dict:
        from specstar.crud.openapi_builder import OpenAPIBuilder

        return OpenAPIBuilder._inline_embedded_schema_ref(schema_extra, source_type)

    @staticmethod
    def _resolve_missing_schema_refs(schema: dict) -> None:
        from specstar.crud.openapi_builder import OpenAPIBuilder

        OpenAPIBuilder._resolve_missing_schema_refs(schema)

    @staticmethod
    def _promote_defs_to_components(schema: dict) -> None:
        from specstar.crud.openapi_builder import OpenAPIBuilder

        OpenAPIBuilder._promote_defs_to_components(schema)

    def apply(
        self,
        app: FastAPI | APIRouter,
        *,
        router: APIRouter | None = None,
        structs: list[type] | None = None,
        auto_include: bool = True,
    ) -> APIRouter:
        """Apply all route templates to generate API endpoints.

        This method generates all the CRUD endpoints for all registered models.
        When ``app`` is a :class:`~fastapi.FastAPI` instance, the OpenAPI schema
        is automatically customised via :meth:`openapi` after route generation.

        Args:
            app: The FastAPI application or an APIRouter to attach routes to.
                When a ``FastAPI`` instance is provided, :meth:`openapi` is
                called automatically after route generation.
            router: Optional sub-router.  When provided, routes are generated
                on this router instead of directly on ``app``.  If
                ``auto_include`` is ``True`` and ``app`` is a ``FastAPI``
                instance, the router is automatically included on ``app``
                via ``app.include_router(router)`` before OpenAPI generation.
            structs: Additional ``msgspec.Struct`` types to include in the
                OpenAPI ``components/schemas``.  Forwarded to :meth:`openapi`.
            auto_include: When ``True`` (the default) and both ``app`` is a
                ``FastAPI`` instance and ``router`` is provided, automatically
                call ``app.include_router(router)`` so that the sub-router's
                routes are reachable and visible in the OpenAPI schema.
                Set to ``False`` if you have already called
                ``app.include_router(router)`` yourself.

        Returns:
            The router that routes were generated on — either ``router``
            (if provided) or ``app``.

        Example:
            ```python
            from fastapi import FastAPI, APIRouter
            from specstar import SpecStar

            app = FastAPI()
            specstar = SpecStar()
            specstar.add_model(User)
            specstar.add_model(Post)

            # 1. Simplest — routes on app, auto OpenAPI
            specstar.apply(app)

            # 2. With a sub-router — auto include + auto OpenAPI
            api_router = APIRouter(prefix="/api/v1")
            specstar.apply(app, router=api_router)

            # 3. Manual include (e.g. already included elsewhere)
            api_router = APIRouter(prefix="/api/v1")
            specstar.apply(app, router=api_router, auto_include=False)
            app.include_router(api_router)
            specstar.openapi(app)

            # 4. Pure APIRouter (no FastAPI, no OpenAPI)
            api_router = APIRouter(prefix="/api/v1")
            specstar.apply(api_router)
            ```

        Note:
            - Call this method after adding all models and custom route templates.
            - When ``app`` is a bare ``APIRouter``, OpenAPI customisation is
              skipped (``APIRouter`` has no OpenAPI schema).
            - ``structs`` is ignored when ``app`` is not a ``FastAPI`` instance.
        """
        # Determine the target router for route generation. ``FastAPI``
        # is not an ``APIRouter``, but it owns one at ``.router``; the
        # downstream route templates only need an APIRouter-shaped
        # target, so unwrap.
        if router is not None:
            target: APIRouter = router
        elif isinstance(app, FastAPI):
            target = app.router
        else:
            target = app

        # Validate all Ref targets point to registered resources
        registered = set(self.resource_managers.keys())
        for ref_info in self.relationships:
            if ref_info.target not in registered:
                logger.warning(
                    f"Ref on '{ref_info.source}.{ref_info.source_field}' targets "
                    f"resource '{ref_info.target}' which is not registered. "
                    f"The reference will be dangling at runtime."
                )

        # Install referential integrity event handlers
        self._install_ref_integrity_handlers()

        # Auto-register Job models for async create actions BEFORE applying
        # route templates so the Jobs get their own CRUD endpoints.
        self._register_async_job_models()

        # Auto-register Job models for async update actions.
        self._register_async_update_job_models()

        self.route_templates.sort(key=lambda rt: rt.order)
        for model_name, resource_manager in self.resource_managers.items():
            for route_template in self.route_templates:
                try:
                    route_template.apply(model_name, resource_manager, target)
                except Exception:
                    pass

        # Register custom create action routes
        self._apply_create_actions(target)

        # Register custom update action routes
        self._apply_update_actions(target)

        # Add ref-specific routes (referrers + relationships)
        self._apply_ref_routes(target)

        # Global backup / restore endpoints
        self._apply_backup_routes(target)

        # Auto include_router + auto openapi when app is a FastAPI instance
        is_fastapi = isinstance(app, FastAPI)
        if is_fastapi:
            if router is not None and auto_include:
                app.include_router(router)
            # Only generate OpenAPI when routes are actually on the app.
            # When router is provided but auto_include is False, the routes
            # live on the sub-router and are not yet reachable from app.routes,
            # so skip openapi and let the user call it manually.
            if router is None or auto_include:
                self.openapi(app, structs or [])

        # Return the externally-meaningful router/app: the caller's ``router``
        # if one was provided, otherwise the original ``app`` (FastAPI or
        # APIRouter). Note ``target`` may be ``app.router`` when ``app`` is a
        # FastAPI instance, which is an internal detail.
        if router is not None:
            return router
        return app  # ty:ignore[invalid-return-type]

    def _register_async_job_models(self) -> None:
        from specstar.crud.async_jobs import register_async_create_jobs

        self._async_job_registry = register_async_create_jobs(
            self._pending_create_actions, self.resource_managers, self.add_model
        )

    def _register_async_update_job_models(self) -> None:
        from specstar.crud.async_jobs import register_async_update_jobs

        self._async_update_job_registry = register_async_update_jobs(
            self._pending_update_actions, self.resource_managers, self.add_model
        )

    def _apply_create_actions(self, router: APIRouter) -> None:
        """Register routes for all pending custom create actions."""
        import msgspec as _msgspec

        from specstar.crud.route_templates.basic import (
            BaseRouteTemplate,
            DependencyProvider,
            MsgspecResponse,
            jsonschema_to_json_schema_extra,
            struct_to_responses_type,
        )

        # Resolve DependencyProvider: try to reuse one from existing route
        # templates so that custom create actions share the same get_user /
        # get_now dependency as standard CRUD routes.
        deps: DependencyProvider | None = None
        for rt in self.route_templates:
            if isinstance(rt, BaseRouteTemplate) and hasattr(rt, "deps"):
                deps = rt.deps
                break
        if deps is None:
            # No route templates have a DP — create one that respects
            # default_user if configured.
            deps = DependencyProvider()
            if self.default_user is not UNSET:
                deps = deps.with_default_user(self.default_user)

        def _is_msgspec_struct_type(ann: type) -> bool:
            """Check if *ann* is a msgspec.Struct subclass."""
            return isinstance(ann, type) and issubclass(ann, _msgspec.Struct)

        def _is_upload_file_annotation(ann: Any) -> bool:
            """Check if *ann* is or contains ``UploadFile``."""
            raw, _ = unwrap_annotated(ann)
            return isinstance(raw, type) and issubclass(raw, UploadFile)

        async def _convert_params_for_payload(
            kwargs: dict,
            param_convs: dict[str, tuple[str, type]],
            auto_payload_type: type[Struct] | None,
        ) -> None:
            """Convert non-serialisable kwargs to their payload surrogates.

            Mutates *kwargs* in place so they can be packed into the
            auto-generated payload Struct.
            """
            from specstar.crud.async_job_builder import UploadFilePayload
            from specstar.types import Binary

            # Get the struct field types for Pydantic conversion targets
            _field_types: dict[str, type] = {}
            if auto_payload_type is not None:
                for fi in _msgspec.structs.fields(auto_payload_type):
                    _field_types[fi.name] = fi.type

            for field_name, (conv_kind, _orig_type) in param_convs.items():
                if field_name not in kwargs:
                    continue
                val = kwargs[field_name]

                if conv_kind == "upload_file":
                    content = await val.read()
                    kwargs[field_name] = UploadFilePayload(
                        binary=Binary(
                            data=content,
                            content_type=val.content_type,
                            size=val.size,
                        ),
                        filename=val.filename,
                    )
                elif conv_kind == "pydantic":
                    target_type = _field_types.get(field_name)
                    if target_type is not None:
                        kwargs[field_name] = _msgspec.convert(
                            val.model_dump(mode="python"), target_type
                        )
                elif conv_kind == "to_str":
                    kwargs[field_name] = str(val)

        def _build_fastapi_compatible_handler(
            handler,
            resource_manager,
            *,
            async_job_config=None,
            background_mode=False,
            deps=None,
        ):
            """Build a FastAPI-compatible endpoint function.

            The user-provided handler may use ``msgspec.Struct`` type hints on
            ``Body()`` parameters.  FastAPI cannot introspect those directly
            (it requires Pydantic), so we build a new function whose signature
            replaces Struct-annotated Body parameters with un-typed
            ``Body(json_schema_extra=...)`` — the same pattern used by
            ``CreateRouteTemplate``.  Inside the wrapper we convert the raw
            dict back to the Struct via ``msgspec.convert`` before calling
            the user handler.

            Plain scalar parameters (``str``, ``int``, etc.) without any
            FastAPI decorator are left as-is — FastAPI will treat them as
            query parameters, which is the correct behaviour.

            Args:
                handler: The user's endpoint function.
                resource_manager: The target resource's ResourceManager.
                async_job_config: When set, a
                    ``(job_rm, job_resource_name, auto_payload_type,
                    param_conversions)`` tuple that switches the wrapper
                    into async-job mode.  Instead of calling *handler* and
                    creating the target resource, the wrapper creates a Job
                    resource and returns HTTP 202 with
                    :class:`JobRedirectInfo`.  When *auto_payload_type* is
                    not ``None``, individual kwargs are packed into the
                    auto-generated payload Struct before creating the Job.
                    *param_conversions* maps field names that need
                    serialisation conversion at endpoint time.
                background_mode: When ``True``, the wrapper uses
                    FastAPI ``BackgroundTasks`` to schedule the handler
                    execution in the background.  The endpoint returns
                    HTTP 202 with :class:`BackgroundTaskAccepted`
                    immediately.  No Job model is created.
                deps: A :class:`DependencyProvider` instance used to inject
                    ``current_user`` and ``current_time`` into the wrapper
                    function signature via ``Depends()``.  When ``None`` a
                    default ``DependencyProvider()`` is created.
            """
            if deps is None:
                deps = DependencyProvider()

            sig = inspect.signature(handler)
            # Identify parameters whose annotation is a msgspec.Struct subclass
            # so we can convert them from raw dicts.
            struct_params: dict[str, type] = {}
            # Pydantic BaseModel params that need manual conversion
            # (required when UploadFile forces multipart/form-data)
            pydantic_params: dict[str, type] = {}
            new_params: list[inspect.Parameter] = []
            new_annotations: dict[str, Any] = {}

            # Pre-scan: check if UploadFile is present — forces
            # multipart/form-data encoding where complex types arrive as
            # JSON strings.
            _has_upload_file = any(
                _is_upload_file_annotation(p.annotation)
                for p in sig.parameters.values()
            )

            def _is_pydantic_model_type(ann: type) -> bool:
                """Check if *ann* is a Pydantic BaseModel subclass."""
                if not isinstance(ann, type):
                    return False
                try:
                    from pydantic import BaseModel

                    return issubclass(ann, BaseModel)
                except ImportError:
                    return False

            for name, param in sig.parameters.items():
                ann = param.annotation
                if ann is inspect.Parameter.empty:
                    new_params.append(param)
                    continue

                # Unwrap Annotated[T, Body(...)] → check T
                raw_ann, _ = unwrap_annotated(ann)

                if _is_msgspec_struct_type(raw_ann):
                    # Replace with untyped Body(json_schema_extra=...)
                    struct_params[name] = raw_ann
                    schema_extra = jsonschema_to_json_schema_extra(raw_ann)
                    if _has_upload_file:
                        schema_extra = self._inline_embedded_schema_ref(
                            schema_extra, raw_ann
                        )
                    new_default = Body(
                        json_schema_extra=schema_extra,
                    )
                    new_param = param.replace(
                        annotation=inspect.Parameter.empty,
                        default=new_default,
                    )
                    new_params.append(new_param)
                elif _has_upload_file and _is_pydantic_model_type(raw_ann):
                    # When UploadFile forces multipart/form-data, Pydantic
                    # model params arrive as JSON strings.  Replace them
                    # with untyped Body() and handle conversion in the
                    # wrapper — same approach as Struct params.
                    pydantic_params[name] = raw_ann
                    try:
                        _pydantic_schema = raw_ann.model_json_schema()
                    except Exception:
                        _pydantic_schema = {}
                    new_default = Body(
                        json_schema_extra=_pydantic_schema,
                    )
                    new_param = param.replace(
                        annotation=inspect.Parameter.empty,
                        default=new_default,
                    )
                    new_params.append(new_param)
                else:
                    new_params.append(param)
                    if ann is not inspect.Parameter.empty:
                        new_annotations[name] = ann

            # Inject current_user and current_time via Depends()
            new_params.append(
                inspect.Parameter(
                    "current_user",
                    inspect.Parameter.KEYWORD_ONLY,
                    default=Depends(deps.get_user),
                    annotation=str,
                )
            )
            new_params.append(
                inspect.Parameter(
                    "current_time",
                    inspect.Parameter.KEYWORD_ONLY,
                    default=Depends(deps.get_now),
                    annotation=dt.datetime,
                )
            )
            new_annotations["current_user"] = str
            new_annotations["current_time"] = dt.datetime

            # Inject BackgroundTasks when background_mode is enabled
            if background_mode:
                from starlette.background import BackgroundTasks

                new_params.append(
                    inspect.Parameter(
                        "background_tasks",
                        inspect.Parameter.KEYWORD_ONLY,
                        annotation=BackgroundTasks,
                    )
                )
                new_annotations["background_tasks"] = BackgroundTasks

            new_sig = sig.replace(
                parameters=new_params, return_annotation=inspect.Parameter.empty
            )

            def _ensure_dict(val: Any) -> Any:
                """Parse JSON string to dict when multipart/form-data
                delivers complex fields as strings."""
                if isinstance(val, str):
                    import json as _json

                    return _json.loads(val)
                return val

            # ---- async-job mode: create Job + return 202 ----------------
            if async_job_config is not None:
                from specstar.types import JobRedirectInfo

                job_rm, job_resource_name, auto_payload_type, _param_convs = (
                    async_job_config
                )
                _param_convs = _param_convs or {}
                # First Struct param is the Job payload (explicit Struct case)
                payload_param_name = next(iter(struct_params), None)

                async def wrapper(*args, **kwargs):
                    _current_user = kwargs.pop("current_user")
                    _current_time = kwargs.pop("current_time")
                    for pname, struct_type in struct_params.items():
                        if pname in kwargs:
                            kwargs[pname] = _msgspec.convert(
                                _ensure_dict(kwargs[pname]), struct_type
                            )
                    for pname, pydantic_type in pydantic_params.items():
                        if pname in kwargs:
                            kwargs[pname] = pydantic_type(**_ensure_dict(kwargs[pname]))

                    # Convert non-serialisable params before packing
                    if _param_convs:
                        await _convert_params_for_payload(
                            kwargs, _param_convs, auto_payload_type
                        )

                    if auto_payload_type is not None:
                        # Auto-generated payload: pack individual kwargs
                        payload_data = auto_payload_type(
                            **{
                                f: kwargs[f]
                                for f in auto_payload_type.__struct_fields__
                                if f in kwargs
                            }
                        )
                    elif payload_param_name is not None:
                        # Explicit Struct parameter: use it directly
                        payload_data = kwargs.get(payload_param_name)
                    else:
                        payload_data = None

                    if payload_data is None:
                        raise HTTPException(
                            status_code=400,
                            detail="Missing payload for async create action.",
                        )

                    job_data = job_rm.resource_type(payload=payload_data)
                    with job_rm.using(_current_user, _current_time):
                        info = job_rm.create(job_data)

                    redirect_url = f"/{job_resource_name}/{info.resource_id}"
                    return MsgspecResponse(
                        JobRedirectInfo(
                            job_resource_name=job_resource_name,
                            job_resource_id=info.resource_id,
                            redirect_url=redirect_url,
                        ),
                        status_code=202,
                    )

            # ---- background mode: schedule via BackgroundTasks + 202 ----
            elif background_mode:
                from specstar.types import BackgroundTaskAccepted

                _bg_is_async = inspect.iscoroutinefunction(handler)

                async def wrapper(*args, **kwargs):
                    _current_user = kwargs.pop("current_user")
                    _current_time = kwargs.pop("current_time")
                    _bg_tasks = kwargs.pop("background_tasks")
                    # Convert raw dicts to Struct / Pydantic instances
                    for pname, struct_type in struct_params.items():
                        if pname in kwargs:
                            kwargs[pname] = _msgspec.convert(
                                _ensure_dict(kwargs[pname]), struct_type
                            )
                    for pname, pydantic_type in pydantic_params.items():
                        if pname in kwargs:
                            kwargs[pname] = pydantic_type(**_ensure_dict(kwargs[pname]))

                    # Snapshot converted kwargs for the background closure
                    _snapshot_kwargs = dict(kwargs)

                    # Always define _run_bg as a sync function so that
                    # Starlette dispatches it via ``run_in_threadpool``.
                    # This ensures the HTTP 202 response is flushed to the
                    # client *before* the background work starts.  If the
                    # original handler is async we bridge into a new event
                    # loop inside the worker thread with ``asyncio.run()``.
                    def _run_bg() -> None:
                        try:
                            if _bg_is_async:
                                result = asyncio.run(handler(*args, **_snapshot_kwargs))
                            else:
                                result = handler(*args, **_snapshot_kwargs)
                            if result is not None:
                                with resource_manager.using(
                                    _current_user, _current_time
                                ):
                                    resource_manager.create(result)
                        except Exception:
                            logger.exception(
                                "Background create action '%s' failed",
                                handler.__name__,
                            )

                    _bg_tasks.add_task(_run_bg)
                    return MsgspecResponse(
                        BackgroundTaskAccepted(message="Task accepted"),
                        status_code=202,
                    )

            # ---- sync mode: call handler + create resource --------------
            elif inspect.iscoroutinefunction(handler):

                async def wrapper(*args, **kwargs):
                    _current_user = kwargs.pop("current_user")
                    _current_time = kwargs.pop("current_time")
                    # Convert raw dicts to Struct instances
                    for pname, struct_type in struct_params.items():
                        if pname in kwargs:
                            kwargs[pname] = _msgspec.convert(
                                _ensure_dict(kwargs[pname]), struct_type
                            )
                    for pname, pydantic_type in pydantic_params.items():
                        if pname in kwargs:
                            kwargs[pname] = pydantic_type(**_ensure_dict(kwargs[pname]))
                    result = await handler(*args, **kwargs)
                    if result is None:
                        return None
                    with resource_manager.using(_current_user, _current_time):
                        info = resource_manager.create(result)
                    return MsgspecResponse(info)

            else:

                def wrapper(*args, **kwargs):
                    _current_user = kwargs.pop("current_user")
                    _current_time = kwargs.pop("current_time")
                    for pname, struct_type in struct_params.items():
                        if pname in kwargs:
                            kwargs[pname] = _msgspec.convert(
                                _ensure_dict(kwargs[pname]), struct_type
                            )
                    for pname, pydantic_type in pydantic_params.items():
                        if pname in kwargs:
                            kwargs[pname] = pydantic_type(**_ensure_dict(kwargs[pname]))
                    result = handler(*args, **kwargs)
                    if result is None:
                        return None
                    with resource_manager.using(_current_user, _current_time):
                        info = resource_manager.create(result)
                    return MsgspecResponse(info)

            wrapper.__name__ = handler.__name__
            wrapper.__qualname__ = handler.__qualname__
            wrapper.__module__ = handler.__module__
            wrapper.__doc__ = handler.__doc__
            setattr(wrapper, "__signature__", new_sig)
            wrapper.__annotations__ = new_annotations
            return wrapper

        for action in self._pending_create_actions:
            rm = self.resource_managers.get(action.resource_name)
            if rm is None:
                logger.warning(
                    f"create_action '{action.path}' targets resource "
                    f"'{action.resource_name}' which is not registered. Skipping."
                )
                continue

            # Strip leading slash from action.path to avoid double-slash
            action_path_segment = action.path.lstrip("/")
            route_path = f"/{action.resource_name}/{action_path_segment}"

            # --- async_mode='job': build an endpoint that creates a Job ---
            if action.async_mode == "job":
                registry_entry = self._async_job_registry.get(id(action.handler))
                if registry_entry is None:
                    logger.warning(
                        f"async create_action '{action.path}' has no registered "
                        f"Job model. Falling back to sync."
                    )
                    action.async_mode = None
                    # Fall through to sync handler below
                else:
                    (
                        job_resource_name,
                        job_model,
                        target_rm,
                        auto_payload_type,
                        param_conversions,
                    ) = registry_entry
                    job_rm = self.resource_managers[job_resource_name]

                    # Same handler, same FastAPI signature — only the
                    # wrapper behaviour changes (create Job + 202).
                    _wrapper = _build_fastapi_compatible_handler(
                        action.handler,
                        rm,
                        async_job_config=(
                            job_rm,
                            job_resource_name,
                            auto_payload_type,
                            param_conversions,
                        ),
                        deps=deps,
                    )

                    router.post(
                        route_path,
                        response_model=None,
                        status_code=202,
                        summary=f"{action.label} ({action.resource_name})",
                        tags=[f"{action.resource_name}"],
                        openapi_extra={
                            "x-specstar-create-action": {
                                "resource": action.resource_name,
                                "label": action.label,
                            },
                        },
                    )(_wrapper)
                    continue

            # --- async_mode='background': fire-and-forget via BackgroundTasks ---
            if action.async_mode == "background":
                _wrapper = _build_fastapi_compatible_handler(
                    action.handler, rm, background_mode=True, deps=deps
                )

                router.post(
                    route_path,
                    response_model=None,
                    status_code=202,
                    summary=f"{action.label} ({action.resource_name})",
                    tags=[f"{action.resource_name}"],
                    openapi_extra={
                        "x-specstar-create-action": {
                            "resource": action.resource_name,
                            "label": action.label,
                        },
                    },
                )(_wrapper)
                continue

            # --- sync (default) handler ---
            _wrapper = _build_fastapi_compatible_handler(action.handler, rm, deps=deps)

            router.post(
                route_path,
                response_model=None,
                responses=struct_to_responses_type(RevisionInfo),
                summary=f"{action.label} ({action.resource_name})",
                tags=[f"{action.resource_name}"],
                openapi_extra={
                    "x-specstar-create-action": {
                        "resource": action.resource_name,
                        "label": action.label,
                    },
                },
            )(_wrapper)

    def _apply_update_actions(self, router: APIRouter) -> None:
        """Register routes for all pending custom update actions."""
        import msgspec as _msgspec

        from specstar.crud.route_templates.basic import (
            BaseRouteTemplate,
            DependencyProvider,
            MsgspecResponse,
            jsonschema_to_json_schema_extra,
            struct_to_responses_type,
        )

        if not self._pending_update_actions:
            return

        # Resolve DependencyProvider (same logic as _apply_create_actions)
        deps: DependencyProvider | None = None
        for rt in self.route_templates:
            if isinstance(rt, BaseRouteTemplate) and hasattr(rt, "deps"):
                deps = rt.deps
                break
        if deps is None:
            deps = DependencyProvider()
            if self.default_user is not UNSET:
                deps = deps.with_default_user(self.default_user)

        def _is_msgspec_struct_type(ann: type) -> bool:
            return isinstance(ann, type) and issubclass(ann, _msgspec.Struct)

        def _build_fastapi_compatible_update_handler(
            handler,
            resource_manager,
            *,
            existing_param: str = "existing",
            info_param: str = "info",
            meta_param: str = "meta",
            update_mode: str = "update",
            async_job_config=None,
            background_mode=False,
            deps=None,
        ):
            """Build a FastAPI-compatible endpoint for a custom update action.

            Similar to ``_build_fastapi_compatible_handler`` but:
            - Adds ``resource_id`` as a path parameter.
            - Auto-fetches the existing resource via ``rm.get(resource_id)``
              and injects it into the handler's *existing_param*.
            - Auto-injects ``RevisionInfo`` into *info_param* and
              ``ResourceMeta`` into *meta_param* when declared.
            - Calls ``rm.update()`` or ``rm.modify()`` based on *update_mode*.

            Args:
                handler: The user's update-action endpoint function.
                resource_manager: The target resource's ResourceManager.
                existing_param: Handler param name for existing resource data.
                info_param: Handler param name for RevisionInfo.
                meta_param: Handler param name for ResourceMeta.
                update_mode: ``"update"`` or ``"modify"``.
                async_job_config: When set, a tuple
                    ``(job_rm, job_resource_name, auto_payload_type,
                    param_conversions)`` that switches the wrapper into
                    async-job mode (creates a Job + returns HTTP 202).
                background_mode: When ``True``, schedules the handler via
                    FastAPI ``BackgroundTasks`` and returns HTTP 202.
                deps: A :class:`DependencyProvider` for injecting
                    ``current_user`` and ``current_time``.
            """
            if deps is None:
                deps = DependencyProvider()

            sig = inspect.signature(handler)
            _has_existing_param = existing_param in sig.parameters
            _has_info_param = info_param in sig.parameters
            _has_meta_param = meta_param in sig.parameters
            struct_params: dict[str, type] = {}
            pydantic_params: dict[str, type] = {}
            new_params: list[inspect.Parameter] = []
            new_annotations: dict[str, Any] = {}

            # Add resource_id as first path parameter
            new_params.append(
                inspect.Parameter(
                    "resource_id",
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=str,
                )
            )
            new_annotations["resource_id"] = str

            for name, param in sig.parameters.items():
                # Skip params that will be injected at runtime
                if name == existing_param:
                    continue
                if name == info_param or name == meta_param:
                    continue
                ann = param.annotation
                if ann is inspect.Parameter.empty:
                    new_params.append(param)
                    continue

                raw_ann, _ = unwrap_annotated(ann)

                if _is_msgspec_struct_type(raw_ann):
                    struct_params[name] = raw_ann
                    new_default = Body(
                        json_schema_extra=jsonschema_to_json_schema_extra(raw_ann),
                    )
                    new_param = param.replace(
                        annotation=inspect.Parameter.empty,
                        default=new_default,
                    )
                    new_params.append(new_param)
                else:
                    new_params.append(param)
                    if ann is not inspect.Parameter.empty:
                        new_annotations[name] = ann

            # Inject current_user and current_time via Depends()
            new_params.append(
                inspect.Parameter(
                    "current_user",
                    inspect.Parameter.KEYWORD_ONLY,
                    default=Depends(deps.get_user),
                    annotation=str,
                )
            )
            new_params.append(
                inspect.Parameter(
                    "current_time",
                    inspect.Parameter.KEYWORD_ONLY,
                    default=Depends(deps.get_now),
                    annotation=dt.datetime,
                )
            )
            new_annotations["current_user"] = str
            new_annotations["current_time"] = dt.datetime

            # Inject BackgroundTasks when background_mode is enabled
            if background_mode:
                from starlette.background import BackgroundTasks

                new_params.append(
                    inspect.Parameter(
                        "background_tasks",
                        inspect.Parameter.KEYWORD_ONLY,
                        annotation=BackgroundTasks,
                    )
                )
                new_annotations["background_tasks"] = BackgroundTasks

            new_sig = sig.replace(
                parameters=new_params, return_annotation=inspect.Parameter.empty
            )

            def _ensure_dict(val: Any) -> Any:
                if isinstance(val, str):
                    import json as _json

                    return _json.loads(val)
                return val

            from specstar.types import ResourceIDNotFoundError

            # ---- async-job mode: create Job + return 202 ----------------
            if async_job_config is not None:
                from specstar.types import JobRedirectInfo

                job_rm, job_resource_name, auto_payload_type, _param_convs = (
                    async_job_config
                )
                _param_convs = _param_convs or {}
                payload_param_name = next(iter(struct_params), None)

                async def wrapper(*args, **kwargs):
                    _resource_id = kwargs.pop("resource_id")
                    _current_user = kwargs.pop("current_user")
                    _current_time = kwargs.pop("current_time")
                    for pname, struct_type in struct_params.items():
                        if pname in kwargs:
                            kwargs[pname] = _msgspec.convert(
                                _ensure_dict(kwargs[pname]), struct_type
                            )

                    if auto_payload_type is not None and payload_param_name is not None:
                        # Explicit Struct param — wrap as payload_data
                        inner_data = kwargs.get(payload_param_name)
                        payload_data = auto_payload_type(
                            resource_id=_resource_id, payload_data=inner_data
                        )
                    elif auto_payload_type is not None:
                        # Auto-generated payload: pack individual kwargs
                        payload_data = auto_payload_type(
                            resource_id=_resource_id,
                            **{
                                f: kwargs[f]
                                for f in auto_payload_type.__struct_fields__
                                if f in kwargs and f != "resource_id"
                            },
                        )
                    else:
                        raise HTTPException(
                            status_code=400,
                            detail="Missing payload for async update action.",
                        )

                    job_data = job_rm.resource_type(payload=payload_data)
                    with job_rm.using(_current_user, _current_time):
                        info = job_rm.create(job_data)

                    redirect_url = f"/{job_resource_name}/{info.resource_id}"
                    return MsgspecResponse(
                        JobRedirectInfo(
                            job_resource_name=job_resource_name,
                            job_resource_id=info.resource_id,
                            redirect_url=redirect_url,
                        ),
                        status_code=202,
                    )

            # ---- background mode: schedule via BackgroundTasks + 202 ----
            elif background_mode:
                from specstar.types import BackgroundTaskAccepted

                _bg_is_async = inspect.iscoroutinefunction(handler)

                async def wrapper(*args, **kwargs):
                    _resource_id = kwargs.pop("resource_id")
                    _current_user = kwargs.pop("current_user")
                    _current_time = kwargs.pop("current_time")
                    _bg_tasks = kwargs.pop("background_tasks")
                    for pname, struct_type in struct_params.items():
                        if pname in kwargs:
                            kwargs[pname] = _msgspec.convert(
                                _ensure_dict(kwargs[pname]), struct_type
                            )
                    for pname, pydantic_type in pydantic_params.items():
                        if pname in kwargs:
                            kwargs[pname] = pydantic_type(**_ensure_dict(kwargs[pname]))

                    _snapshot_kwargs = dict(kwargs)

                    def _run_bg() -> None:
                        try:
                            # Lazy-fetch existing resource at BG execution time
                            with resource_manager.using(_current_user, _current_time):
                                existing_resource = resource_manager.get(_resource_id)
                            if _has_existing_param:
                                _snapshot_kwargs[existing_param] = (
                                    existing_resource.data
                                )
                            if _has_info_param:
                                _snapshot_kwargs[info_param] = existing_resource.info
                            if _has_meta_param:
                                with resource_manager.using(
                                    _current_user, _current_time
                                ):
                                    _snapshot_kwargs[meta_param] = (
                                        resource_manager.get_meta(_resource_id)
                                    )

                            if _bg_is_async:
                                result = asyncio.run(handler(*args, **_snapshot_kwargs))
                            else:
                                result = handler(*args, **_snapshot_kwargs)
                            if result is not None:
                                with resource_manager.using(
                                    _current_user, _current_time
                                ):
                                    if update_mode == "modify":
                                        resource_manager.modify(
                                            _resource_id, data=result
                                        )
                                    else:
                                        resource_manager.update(_resource_id, result)
                        except Exception:
                            logger.exception(
                                "Background update action '%s' failed",
                                handler.__name__,
                            )

                    _bg_tasks.add_task(_run_bg)
                    return MsgspecResponse(
                        BackgroundTaskAccepted(message="Task accepted"),
                        status_code=202,
                    )

            # ---- sync mode: call handler + update resource --------------
            elif inspect.iscoroutinefunction(handler):

                async def wrapper(*args, **kwargs):
                    _resource_id = kwargs.pop("resource_id")
                    _current_user = kwargs.pop("current_user")
                    _current_time = kwargs.pop("current_time")
                    for pname, struct_type in struct_params.items():
                        if pname in kwargs:
                            kwargs[pname] = _msgspec.convert(
                                _ensure_dict(kwargs[pname]), struct_type
                            )
                    for pname, pydantic_type in pydantic_params.items():
                        if pname in kwargs:
                            kwargs[pname] = pydantic_type(**_ensure_dict(kwargs[pname]))
                    # Fetch existing resource and inject (only if handler declares it)
                    try:
                        with resource_manager.using(_current_user, _current_time):
                            existing_resource = resource_manager.get(_resource_id)
                    except ResourceIDNotFoundError:
                        raise HTTPException(
                            status_code=404,
                            detail=f"Resource '{_resource_id}' not found.",
                        )
                    if _has_existing_param:
                        kwargs[existing_param] = existing_resource.data
                    if _has_info_param:
                        kwargs[info_param] = existing_resource.info
                    if _has_meta_param:
                        with resource_manager.using(_current_user, _current_time):
                            kwargs[meta_param] = resource_manager.get_meta(_resource_id)
                    result = await handler(**kwargs)
                    if result is None:
                        return None
                    with resource_manager.using(_current_user, _current_time):
                        if update_mode == "modify":
                            info = resource_manager.modify(_resource_id, data=result)
                        else:
                            info = resource_manager.update(_resource_id, result)
                    return MsgspecResponse(info)

            else:

                def wrapper(*args, **kwargs):
                    _resource_id = kwargs.pop("resource_id")
                    _current_user = kwargs.pop("current_user")
                    _current_time = kwargs.pop("current_time")
                    for pname, struct_type in struct_params.items():
                        if pname in kwargs:
                            kwargs[pname] = _msgspec.convert(
                                _ensure_dict(kwargs[pname]), struct_type
                            )
                    for pname, pydantic_type in pydantic_params.items():
                        if pname in kwargs:
                            kwargs[pname] = pydantic_type(**_ensure_dict(kwargs[pname]))
                    # Fetch existing resource and inject (only if handler declares it)
                    try:
                        with resource_manager.using(_current_user, _current_time):
                            existing_resource = resource_manager.get(_resource_id)
                    except ResourceIDNotFoundError:
                        raise HTTPException(
                            status_code=404,
                            detail=f"Resource '{_resource_id}' not found.",
                        )
                    if _has_existing_param:
                        kwargs[existing_param] = existing_resource.data
                    if _has_info_param:
                        kwargs[info_param] = existing_resource.info
                    if _has_meta_param:
                        with resource_manager.using(_current_user, _current_time):
                            kwargs[meta_param] = resource_manager.get_meta(_resource_id)
                    result = handler(**kwargs)
                    if result is None:
                        return None
                    with resource_manager.using(_current_user, _current_time):
                        if update_mode == "modify":
                            info = resource_manager.modify(_resource_id, data=result)
                        else:
                            info = resource_manager.update(_resource_id, result)
                    return MsgspecResponse(info)

            wrapper.__name__ = handler.__name__
            wrapper.__qualname__ = handler.__qualname__
            wrapper.__module__ = handler.__module__
            wrapper.__doc__ = handler.__doc__
            setattr(wrapper, "__signature__", new_sig)
            wrapper.__annotations__ = new_annotations
            return wrapper

        for action in self._pending_update_actions:
            rm = self.resource_managers.get(action.resource_name)
            if rm is None:
                logger.warning(
                    f"update_action '{action.path}' targets resource "
                    f"'{action.resource_name}' which is not registered. Skipping."
                )
                continue

            action_path_segment = action.path.lstrip("/")
            route_path = (
                f"/{action.resource_name}/{{resource_id}}/{action_path_segment}"
            )

            # --- async_mode='job': build an endpoint that creates a Job ---
            if action.async_mode == "job":
                registry_entry = self._async_update_job_registry.get(id(action.handler))
                if registry_entry is None:
                    logger.warning(
                        f"async update_action '{action.path}' has no registered "
                        f"Job model. Falling back to sync."
                    )
                    action.async_mode = None
                    # Fall through to sync handler below
                else:
                    (
                        job_resource_name,
                        job_model,
                        target_rm,
                        auto_payload_type,
                        param_conversions,
                        _update_mode,
                        _existing_param,
                        _info_param,
                        _meta_param,
                    ) = registry_entry
                    job_rm = self.resource_managers[job_resource_name]

                    _wrapper = _build_fastapi_compatible_update_handler(
                        action.handler,
                        rm,
                        existing_param=action.existing_param,
                        info_param=action.info_param,
                        meta_param=action.meta_param,
                        update_mode=action.mode,
                        async_job_config=(
                            job_rm,
                            job_resource_name,
                            auto_payload_type,
                            param_conversions,
                        ),
                        deps=deps,
                    )

                    router.post(
                        route_path,
                        response_model=None,
                        status_code=202,
                        summary=f"{action.label} ({action.resource_name})",
                        tags=[f"{action.resource_name}"],
                        openapi_extra={
                            "x-specstar-update-action": {
                                "resource": action.resource_name,
                                "label": action.label,
                                "mode": action.mode,
                            },
                        },
                    )(_wrapper)
                    continue

            # --- async_mode='background': fire-and-forget via BackgroundTasks ---
            if action.async_mode == "background":
                _wrapper = _build_fastapi_compatible_update_handler(
                    action.handler,
                    rm,
                    existing_param=action.existing_param,
                    info_param=action.info_param,
                    meta_param=action.meta_param,
                    update_mode=action.mode,
                    background_mode=True,
                    deps=deps,
                )

                router.post(
                    route_path,
                    response_model=None,
                    status_code=202,
                    summary=f"{action.label} ({action.resource_name})",
                    tags=[f"{action.resource_name}"],
                    openapi_extra={
                        "x-specstar-update-action": {
                            "resource": action.resource_name,
                            "label": action.label,
                            "mode": action.mode,
                        },
                    },
                )(_wrapper)
                continue

            # --- sync (default) handler ---
            _wrapper = _build_fastapi_compatible_update_handler(
                action.handler,
                rm,
                existing_param=action.existing_param,
                info_param=action.info_param,
                meta_param=action.meta_param,
                update_mode=action.mode,
                deps=deps,
            )

            router.post(
                route_path,
                response_model=None,
                responses=struct_to_responses_type(RevisionInfo),
                summary=f"{action.label} ({action.resource_name})",
                tags=[f"{action.resource_name}"],
                openapi_extra={
                    "x-specstar-update-action": {
                        "resource": action.resource_name,
                        "label": action.label,
                        "mode": action.mode,
                    },
                },
            )(_wrapper)

    # ------------------------------------------------------------------
    # Ref query routes
    # ------------------------------------------------------------------

    def _apply_ref_routes(self, router: APIRouter) -> None:
        """Generate ref-related API routes on *router*.

        Creates:
        * ``GET /{target}/{resource_id}/referrers`` for each model that is a
          *target* of at least one ``Ref`` annotation.  Returns a list of
          referrer groups with ``source``, ``source_field``, ``ref_type``,
          ``on_delete``, and ``resource_ids``.
        * ``GET /_relationships`` — a global metadata endpoint returning the
          full relationship graph.
        """
        from collections import defaultdict

        # Build target -> list[_RefInfo]
        target_refs: dict[str, list[_RefInfo]] = defaultdict(list)
        for ref_info in self.relationships:
            target_refs[ref_info.target].append(ref_info)

        registered = set(self.resource_managers.keys())

        # Per-target referrers endpoint
        for target_name, refs in target_refs.items():
            if target_name not in registered:
                continue

            # Filter to refs whose source is also registered
            actionable_refs = [r for r in refs if r.source in registered]
            if not actionable_refs:
                continue

            self._add_referrers_route(router, target_name, actionable_refs)

        # Global relationships metadata endpoint
        all_rels = self.relationships

        @router.get(
            "/_relationships",
            summary="List all resource relationships",
            tags=["_meta"],
            description=(
                "Returns the complete relationship graph discovered from "
                "Ref / RefRevision annotations across all registered models."
            ),
        )
        async def _list_relationships() -> list[dict]:
            return [
                {
                    "source": r.source,
                    "source_field": r.source_field,
                    "target": r.target,
                    "ref_type": r.ref_type,
                    "on_delete": r.on_delete.value,
                    "nullable": r.nullable,
                }
                for r in all_rels
            ]

    def _add_referrers_route(
        self,
        router: APIRouter,
        target_name: str,
        refs: list[_RefInfo],
    ) -> None:
        """Register ``GET /{target_name}/{resource_id}/referrers`` on *router*."""
        resource_managers = self.resource_managers

        @router.get(
            f"/{target_name}/{{resource_id}}/referrers",
            summary=f"List referrers of a {target_name} resource",
            tags=[f"{target_name}"],
            description=(
                f"Find all resources that reference a specific `{target_name}` "
                f"resource via Ref-annotated fields.  Results are grouped by "
                f"source model and field."
            ),
        )
        async def _list_referrers(resource_id: str) -> list[dict]:
            # Verify the target resource exists
            target_rm = resource_managers.get(target_name)
            if target_rm is None:
                raise HTTPException(
                    status_code=404, detail=f"Unknown resource type: {target_name}"
                )
            try:
                target_rm.get_meta(resource_id)
            except (ResourceIDNotFoundError, ResourceIsDeletedError):
                raise HTTPException(
                    status_code=404,
                    detail=f"{target_name} '{resource_id}' not found",
                )
            results: list[dict] = []
            for ref_info in refs:
                source_rm = resource_managers.get(ref_info.source)
                if source_rm is None:
                    continue
                # Only resource_id refs are auto-indexed and searchable
                if ref_info.ref_type != "resource_id":
                    continue
                # For list ref fields (e.g. list[Annotated[str, Ref(...)]]),
                # use 'contains' to check if the list includes the target ID.
                # For scalar ref fields, use 'equals' for exact match.
                op = (
                    DataSearchOperator.contains
                    if ref_info.is_list
                    else DataSearchOperator.equals
                )
                metas = source_rm.search_resources(
                    ResourceMetaSearchQuery(
                        is_deleted=False,
                        conditions=[
                            DataSearchCondition(
                                field_path=ref_info.source_field,
                                operator=op,
                                value=resource_id,
                            )
                        ],
                        limit=10_000,
                    )
                )
                if metas:
                    results.append(
                        {
                            "source": ref_info.source,
                            "source_field": ref_info.source_field,
                            "ref_type": ref_info.ref_type,
                            "on_delete": ref_info.on_delete.value,
                            "resource_ids": [m.resource_id for m in metas],
                        }
                    )
            return results

    # ------------------------------------------------------------------
    # Global backup / restore routes
    # ------------------------------------------------------------------

    def _apply_backup_routes(self, router: APIRouter) -> None:
        """Register global ``/_backup/export`` and ``/_backup/import``
        endpoints on *router*.

        * ``GET /_backup/export``  — download a ``.acbak`` archive
          containing **all** registered models.
        * ``POST /_backup/import`` — upload a ``.acbak`` archive and
          load its contents into the matching resource managers.
        """
        import io as _io

        from fastapi import Query as _Query
        from fastapi.responses import StreamingResponse

        specstar_ref = self  # closure over self

        @router.get(
            "/_backup/export",
            summary="Export all models",
            tags=["_backup"],
            description=(
                "Download a `.acbak` archive containing all registered "
                "models.  Optionally pass `models` query parameter to "
                "restrict which models are exported."
            ),
            response_class=StreamingResponse,
            responses={
                200: {
                    "content": {"application/octet-stream": {}},
                    "description": "Streaming .acbak archive.",
                }
            },
        )
        async def global_export(
            models: list[str] | None = _Query(
                None,
                description=(
                    "Model names to include.  When omitted all registered "
                    "models are exported."
                ),
            ),
        ):
            model_queries: dict[str, Query | ResourceMetaSearchQuery | None] | None = (
                None
            )
            if models:
                unknown = set(models) - set(specstar_ref.resource_managers)
                if unknown:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Unknown model(s): {', '.join(sorted(unknown))}",
                    )
                model_queries = {m: None for m in models}

            buf = _io.BytesIO()
            specstar_ref.dump(buf, model_queries=model_queries)
            buf.seek(0)
            return StreamingResponse(
                buf,
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": 'attachment; filename="backup.acbak"',
                },
            )

        @router.post(
            "/_backup/import",
            summary="Import from archive",
            tags=["_backup"],
            description=(
                "Upload a `.acbak` archive.  All model sections found in "
                "the archive will be loaded into the corresponding resource "
                "managers.  Use `on_duplicate` to control the duplicate "
                "handling strategy."
            ),
        )
        async def global_import(
            file: UploadFile = File(..., description=".acbak archive file"),
            on_duplicate: str = _Query(
                "overwrite",
                description="Strategy: overwrite | skip | raise_error",
            ),
        ) -> dict:
            try:
                strategy = OnDuplicate(on_duplicate)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Invalid on_duplicate: {on_duplicate}. "
                        "Must be one of: overwrite, skip, raise_error"
                    ),
                )

            data = await file.read()
            try:
                stats = specstar_ref.load(_io.BytesIO(data), on_duplicate=strategy)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

            return {
                model: {
                    "loaded": s.loaded,
                    "skipped": s.skipped,
                    "total": s.total,
                }
                for model, s in stats.items()
            }

    def dump_descriptor(self, path: str | Path | None = None) -> Descriptor | None:
        """Build a property-graph descriptor of the registered models.

        The descriptor is the machine-readable artifact behind
        ``spec.lock.json`` and the spec-driven authoring workflow. It is
        deterministic — same registered state always yields the same graph —
        and contains no LLM-generated content.

        Args:
            path: If given, write the descriptor as indented JSON to ``path``
                and return ``None``. If omitted, return the
                :class:`~specstar.descriptor.Descriptor` instance for in-process
                inspection.

        Coverage in v0.11: ``resource`` / ``field`` nodes, ``has_field`` and
        ``references`` edges. Subsequent v0.11 follow-ups extend coverage to
        ``schema_version`` / ``route`` / ``storage_backend`` /
        ``permission_policy`` etc. without changing this signature.

        See ``docs/design/spec-driven-architecture.md`` §3.3 for the full
        descriptor schema and rationale.
        """
        import msgspec.json as _json

        from specstar.descriptor.builder import build_descriptor

        descriptor = build_descriptor(self)
        if path is None:
            return descriptor

        encoded = _json.format(_json.encode(descriptor), indent=2)
        Path(path).write_bytes(encoded)
        return None

    def dump(
        self,
        bio: IO[bytes],
        model_queries: dict[str, Query | ResourceMetaSearchQuery | None] | None = None,
    ) -> None:
        """Export resources to a streaming msgpack archive.

        Args:
            bio: Binary I/O stream to write to.
            model_queries: Optional ``{model_name: QB_query}`` mapping.
                When *None*, all registered models are exported in full.
                When provided, only the listed models are exported;
                each value is a ``Query`` / ``ResourceMetaSearchQuery``
                (or *None* for "all resources of that model").

        Example::

            # Dump everything
            with open("backup.acbak", "wb") as f:
                specstar.dump(f)

            # Dump only User resources where name == "Alice"
            from specstar.query import QB

            with open("backup.acbak", "wb") as f:
                specstar.dump(f, model_queries={"user": QB.name == "Alice"})
        """
        from specstar.resource_manager.dump_format import (
            DumpStreamWriter,
            EofRecord,
            HeaderRecord,
            ModelEndRecord,
            ModelStartRecord,
        )

        writer = DumpStreamWriter(bio)
        writer.write(HeaderRecord())

        # Determine which models to dump
        if model_queries is None:
            models_to_dump = {name: None for name in self.resource_managers}
        else:
            models_to_dump = model_queries

        for model_name, query in models_to_dump.items():
            if model_name not in self.resource_managers:
                raise ValueError(
                    f"Model '{model_name}' not found in resource managers."
                )
            mgr = self.resource_managers[model_name]
            writer.write(ModelStartRecord(model_name=model_name))
            for record in mgr.dump(query=query):
                writer.write(record)
            writer.write(ModelEndRecord(model_name=model_name))

        writer.write(EofRecord())

    def load(
        self,
        bio: IO[bytes],
        on_duplicate: "OnDuplicate | None" = None,
    ) -> dict[str, "LoadStats"]:
        """Import resources from a streaming msgpack archive.

        Args:
            bio: Binary I/O stream to read from.
            on_duplicate: Strategy for duplicate resource IDs.
                Defaults to ``OnDuplicate.overwrite``.

        Returns:
            Per-model load statistics: ``{model_name: LoadStats}``.

        Raises:
            ValueError: If the archive format is invalid or contains
                unknown models.
        """
        from specstar.resource_manager.dump_format import (
            BlobRecord,
            DumpStreamReader,
            EofRecord,
            HeaderRecord,
            MetaRecord,
            ModelEndRecord,
            ModelStartRecord,
            RevisionRecord,
        )
        from specstar.types import OnDuplicate as _OnDuplicate

        if on_duplicate is None:
            on_duplicate = _OnDuplicate.overwrite

        reader = DumpStreamReader(bio)
        stats: dict[str, LoadStats] = {}

        # Read header
        first = next(reader)
        if not isinstance(first, HeaderRecord):
            raise ValueError(f"Expected HeaderRecord, got {type(first).__name__}.")
        if first.version != 2:
            raise ValueError(f"Unsupported dump format version {first.version}.")

        current_model: str | None = None
        current_mgr = None
        # Per-model record buffers for bulk load
        meta_buf: list[MetaRecord] = []
        rev_buf: list[RevisionRecord] = []
        blob_buf: list[BlobRecord] = []

        for record in reader:
            if isinstance(record, ModelStartRecord):
                current_model = record.model_name
                if current_model not in self.resource_managers:
                    raise ValueError(
                        f"Model '{current_model}' not found in resource managers."
                    )
                current_mgr = self.resource_managers[current_model]
                meta_buf.clear()
                rev_buf.clear()
                blob_buf.clear()
                if current_model not in stats:
                    stats[current_model] = LoadStats()

            elif isinstance(record, ModelEndRecord):
                # Flush buffered records via bulk load
                if current_mgr is not None and current_model is not None:
                    st = current_mgr.load_records_bulk(
                        meta_buf,
                        rev_buf,
                        blob_buf,
                        on_duplicate=on_duplicate,
                    )
                    s = stats[current_model]
                    s.loaded += st.loaded
                    s.skipped += st.skipped
                    s.total += st.total
                current_model = None
                current_mgr = None
                meta_buf.clear()
                rev_buf.clear()
                blob_buf.clear()

            elif isinstance(record, MetaRecord):
                if current_mgr is None:
                    raise ValueError("MetaRecord outside of model section.")
                meta_buf.append(record)

            elif isinstance(record, RevisionRecord):
                if current_mgr is None:
                    raise ValueError("RevisionRecord outside of model section.")
                rev_buf.append(record)

            elif isinstance(record, BlobRecord):
                if current_mgr is None:
                    raise ValueError("BlobRecord outside of model section.")
                blob_buf.append(record)

            elif isinstance(record, EofRecord):
                break

        return stats
