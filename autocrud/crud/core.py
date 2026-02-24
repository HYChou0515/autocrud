from __future__ import annotations

import asyncio
import datetime as dt
import inspect
import logging
import warnings
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import (
    IO,
    Any,
    Literal,
    TypeVar,
)

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.openapi.utils import get_openapi
from fastapi.params import Body
from msgspec import UNSET, UnsetType

from autocrud.crud.route_templates.basic import (
    DependencyProvider,
    FullResourceResponse,
    IRouteTemplate,
    RevisionListResponse,
    jsonschema_to_openapi,
)
from autocrud.crud.route_templates.create import CreateRouteTemplate
from autocrud.crud.route_templates.delete import (
    BatchDeleteRouteTemplate,
    BatchRestoreRouteTemplate,
    DeleteRouteTemplate,
    PermanentlyDeleteRouteTemplate,
    RestoreRouteTemplate,
)
from autocrud.crud.route_templates.get import ReadRouteTemplate
from autocrud.crud.route_templates.patch import (
    RFC6902,
    PatchRouteTemplate,
    RFC6902_Add,
    RFC6902_Copy,
    RFC6902_Move,
    RFC6902_Remove,
    RFC6902_Replace,
    RFC6902_Test,
)
from autocrud.crud.route_templates.rerun import RerunRouteTemplate
from autocrud.crud.route_templates.search import ListRouteTemplate
from autocrud.crud.route_templates.switch import SwitchRevisionRouteTemplate
from autocrud.crud.route_templates.update import UpdateRouteTemplate
from autocrud.permission.rbac import RBACPermissionChecker
from autocrud.permission.simple import AllowAll
from autocrud.query import Query
from autocrud.resource_manager.basic import (
    Encoding,
    IStorage,
)
from autocrud.resource_manager.blob_store.simple import DiskBlobStore, MemoryBlobStore
from autocrud.resource_manager.core import ResourceManager
from autocrud.resource_manager.pydantic_converter import (
    is_pydantic_model,
    pydantic_to_struct,
)
from autocrud.resource_manager.storage_factory import (
    DiskStorageFactory,
    IStorageFactory,
    MemoryStorageFactory,
)
from autocrud.schema import Schema
from autocrud.types import (
    DataSearchCondition,
    DataSearchOperator,
    EventContext,
    HasResourceId,
    IConstraintChecker,
    IEventHandler,
    IMessageQueue,
    IMessageQueueFactory,
    IMigration,
    IndexableField,
    IPermissionChecker,
    IResourceManager,
    IValidator,
    Job,
    OnDelete,
    OnDuplicate,
    Ref,
    RefRevision,
    RefType,
    Resource,
    ResourceAction,
    ResourceIDNotFoundError,
    ResourceIsDeletedError,
    ResourceMeta,
    ResourceMetaSearchQuery,
    RevisionInfo,
    RevisionStatus,
    TaskStatus,
    _RefInfo,
    extract_refs,
)
from autocrud.util.naming import NameConverter
from autocrud.util.type_utils import (
    collect_nested_struct_types,
    get_type_name,
    get_union_args,
    is_generic_subclass,
    is_union_type,
    unwrap_annotated,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")


class LoadStats:
    """Per-model statistics returned by :meth:`AutoCRUD.load`."""

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


@dataclass
class _PendingCreateAction:
    """Metadata for a custom create action registered via @crud.create_action()."""

    resource_name: str
    path: str
    label: str
    handler: Callable


class LazyJobHandler:
    def __init__(self, factory):
        self._factory = factory
        self._handler = None

    def __call__(self, resource):
        if self._handler is None:
            self._handler = self._factory()
        return self._handler(resource)


class _RefIntegrityHandler(IEventHandler):
    """Internal event handler that enforces referential integrity on delete.

    When a *target* resource is deleted, this handler iterates over all
    ``_RefInfo`` entries that reference the target and applies the configured
    ``on_delete`` action:

    * ``cascade``  — soft-delete each referencing resource.
    * ``set_null`` — set the referencing field to ``None`` via update.
    * ``dangling`` — (not handled here; no action needed).
    """

    def __init__(
        self,
        refs: list[_RefInfo],
        resource_managers: dict[str, IResourceManager],
    ):
        self._refs = refs
        self._resource_managers = resource_managers

    # ------------------------------------------------------------------
    # IEventHandler interface
    # ------------------------------------------------------------------

    def is_supported(self, context: EventContext) -> bool:
        return isinstance(context, HasResourceId) and (
            context.phase == "on_success" and context.action is ResourceAction.delete
        )

    def handle_event(self, context: EventContext) -> None:
        if not isinstance(context, HasResourceId):
            return
        deleted_resource_id: str = context.resource_id
        for ref_info in self._refs:
            source_rm = self._resource_managers.get(ref_info.source)
            if source_rm is None:
                continue

            # Find all source resources referencing the deleted target
            matching = source_rm.search_resources(
                ResourceMetaSearchQuery(
                    is_deleted=False,
                    conditions=[
                        DataSearchCondition(
                            field_path=ref_info.source_field,
                            operator=DataSearchOperator.equals,
                            value=deleted_resource_id,
                        )
                    ],
                    limit=10_000,
                )
            )

            for meta in matching:
                if ref_info.on_delete == OnDelete.cascade:
                    source_rm.delete(meta.resource_id)
                elif ref_info.on_delete == OnDelete.set_null:
                    from jsonpatch import JsonPatch

                    patch = JsonPatch(
                        [
                            {
                                "op": "replace",
                                "path": f"/{ref_info.source_field}",
                                "value": None,
                            }
                        ]
                    )
                    source_rm.patch(meta.resource_id, patch)


class AutoCRUD:
    """AutoCRUD - Automatic CRUD API Generator for FastAPI

    AutoCRUD is the main class that automatically generates complete CRUD (Create, Read, Update, Delete)
    APIs for your data models. It provides a powerful, flexible, and easy-to-use system for building
    RESTful APIs with built-in version control, soft deletion, and comprehensive querying capabilities.

    Key Features:
    - **Automatic API Generation**: Generates complete CRUD endpoints for any data model
    - **Version Control**: Built-in revision tracking for all resources with full history
    - **Soft Deletion**: Resources are marked as deleted rather than permanently removed
    - **Flexible Storage**: Support for both memory and disk-based storage backends
    - **Model Agnostic**: Works with msgspec Structs, and other data types
    - **Customizable Routes**: Extensible route template system for custom endpoints
    - **Data Migration**: Built-in support for schema evolution and data migration
    - **Comprehensive Querying**: Advanced filtering, sorting, and pagination capabilities

    Basic Usage:
    ```python
    from fastapi import FastAPI
    from autocrud import AutoCRUD

    # Create AutoCRUD instance
    autocrud = AutoCRUD()

    # Add your model
    autocrud.add_model(User)

    # Apply to FastAPI router
    app = FastAPI()
    autocrud.apply(app)
    ```

    This generates the following endpoints for your User model:
    - `POST /users` - Create a new user
    - `GET /users/data` - List all users (data only)
    - `GET /users/meta` - List all users (metadata only)
    - `GET /users/revision-info` - List all users (revision info only)
    - `GET /users/full` - List all users (complete information)
    - `GET /users/{id}/data` - Get specific user data
    - `GET /users/{id}/meta` - Get specific user metadata
    - `GET /users/{id}/revision-info` - Get specific user revision info
    - `GET /users/{id}/full` - Get complete user information
    - `GET /users/{id}/revision-list` - Get user revision history
    - `PUT /users/{id}` - Update user (full replacement)
    - `PATCH /users/{id}` - Partially update user (JSON Patch)
    - `DELETE /users/{id}` - Soft delete user
    - `POST /users/{id}/restore` - Restore deleted user
    - `POST /users/{id}/switch/{revision_id}` - Switch to specific revision

    Advanced Features:
    - **Custom Storage**: Use disk-based storage for persistence
    - **Data Migration**: Handle schema changes with migration support
    - **Custom Naming**: Control URL patterns and resource names
    - **Route Customization**: Add custom endpoints with route templates
    - **Backup/Restore**: Export and import complete datasets

    Args:
        model_naming: Controls how model names are converted to URL paths.
                     Options: "same", "pascal", "camel", "snake", "kebab" (default)
                     or a custom function that takes a type and returns a string.
        route_templates: Custom list of route templates to use instead of defaults,
                        or a dictionary of template classes to kwargs for configuring defaults.
                        If None, uses the standard CRUD route templates.

    Example with Advanced Features:
    ```python
    from autocrud import AutoCRUD, DiskStorageFactory
    from pathlib import Path

    # Use disk storage for persistence
    storage_factory = DiskStorageFactory(Path("./data"))

    # Custom naming (convert CamelCase to snake_case)
    autocrud = AutoCRUD(model_naming="snake")

    # Add model with custom configuration
    autocrud.add_model(
        User,
        name="people",  # Custom URL path
        storage_factory=storage_factory,
        id_generator=lambda: f"user_{uuid.uuid4()}",  # Custom ID generation
    )
    ```

    Thread Safety:
    The AutoCRUD instance is thread-safe for read operations, but adding models
    should be done during application startup before handling requests.

    Performance:
    - Memory storage: Suitable for development and small datasets
    - Disk storage: Recommended for production with large datasets
    - All operations are optimized for typical CRUD workloads
    - Built-in pagination prevents memory issues with large result sets

    See Also:
    - IStorageFactory: For implementing custom storage backends
    - IRouteTemplate: For creating custom endpoint templates
    - IResourceManager: For advanced programmatic resource management
    """

    def __init__(
        self,
        *,
        model_naming: Literal["same", "pascal", "camel", "snake", "kebab"]
        | Callable[[type], str] = "kebab",
        route_templates: list[IRouteTemplate]
        | dict[type, dict[str, Any]]
        | None = None,
        storage_factory: IStorageFactory | None = None,
        message_queue_factory: IMessageQueueFactory | None = None,
        admin: str | None = None,
        permission_checker: IPermissionChecker | None = None,
        dependency_provider: DependencyProvider | None = None,
        event_handlers: Sequence[IEventHandler] | None = None,
        encoding: Encoding = Encoding.json,
        default_user: str | Callable[[], str] | UnsetType = UNSET,
        default_now: Callable[[], dt.datetime] | UnsetType = UNSET,
    ):
        # Initialize empty collections
        self.resource_managers: OrderedDict[str, IResourceManager] = OrderedDict()
        self.message_queues: OrderedDict[str, IMessageQueue] = OrderedDict()
        self.model_names: dict[type[T], str | None] = {}
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
        self._pending_create_actions: list[_PendingCreateAction] = []

        # Apply configuration using shared logic
        self._apply_configuration(
            model_naming=model_naming,
            route_templates=route_templates,
            storage_factory=storage_factory,
            message_queue_factory=message_queue_factory,
            admin=admin,
            permission_checker=permission_checker,
            dependency_provider=dependency_provider,
            event_handlers=event_handlers,
            encoding=encoding,
            default_user=default_user,
            default_now=default_now,
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
        storage_factory: IStorageFactory | None | UnsetType = UNSET,
        message_queue_factory: IMessageQueueFactory | None | UnsetType = UNSET,
        admin: str | None | UnsetType = UNSET,
        permission_checker: IPermissionChecker | None | UnsetType = UNSET,
        dependency_provider: DependencyProvider | None | UnsetType = UNSET,
        event_handlers: Sequence[IEventHandler] | None | UnsetType = UNSET,
        encoding: Encoding | UnsetType = UNSET,
        default_user: str | Callable[[], str] | UnsetType = UNSET,
        default_now: Callable[[], dt.datetime] | UnsetType = UNSET,
    ) -> None:
        """Apply configuration settings to the AutoCRUD instance.

        This internal method contains the shared logic for both __init__ and configure.
        It handles UNSET values to allow partial updates in configure() while still
        working with direct values in __init__().
        """
        # Update model_naming
        if model_naming is not UNSET:
            self.model_naming = model_naming

        # Update storage_factory and blob_store
        if storage_factory is not UNSET:
            if storage_factory is None:
                self.storage_factory = MemoryStorageFactory()
            else:
                self.storage_factory = storage_factory

            # Recreate blob_store based on new storage_factory
            if isinstance(self.storage_factory, DiskStorageFactory):
                self.blob_store = DiskBlobStore(self.storage_factory.rootdir / "_blobs")
            elif hasattr(self.storage_factory, "build_blob_store"):
                self.blob_store = self.storage_factory.build_blob_store()
            else:
                self.blob_store = MemoryBlobStore()

        # Update message_queue_factory
        if message_queue_factory is not UNSET:
            if message_queue_factory is None:
                from autocrud.message_queue.simple import SimpleMessageQueueFactory

                self.message_queue_factory = SimpleMessageQueueFactory()
            else:
                self.message_queue_factory = message_queue_factory

        # Update route_templates
        # If dependency_provider is changed, we need to rebuild route_templates
        rebuild_templates = route_templates is not UNSET or (
            dependency_provider is not UNSET and route_templates is UNSET
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
                for rt in [
                    CreateRouteTemplate,
                    ListRouteTemplate,
                    ReadRouteTemplate,
                    UpdateRouteTemplate,
                    PatchRouteTemplate,
                    SwitchRevisionRouteTemplate,
                    RerunRouteTemplate,
                    DeleteRouteTemplate,
                    PermanentlyDeleteRouteTemplate,
                    RestoreRouteTemplate,
                    BatchDeleteRouteTemplate,
                    BatchRestoreRouteTemplate,
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

    def configure(
        self,
        *,
        model_naming: Literal["same", "pascal", "camel", "snake", "kebab"]
        | Callable[[type], str]
        | UnsetType = UNSET,
        route_templates: list[IRouteTemplate]
        | dict[type, dict[str, Any]]
        | UnsetType = UNSET,
        storage_factory: IStorageFactory | UnsetType = UNSET,
        message_queue_factory: IMessageQueueFactory | UnsetType = UNSET,
        admin: str | None | UnsetType = UNSET,
        permission_checker: IPermissionChecker | UnsetType = UNSET,
        dependency_provider: DependencyProvider | UnsetType = UNSET,
        event_handlers: Sequence[IEventHandler] | UnsetType = UNSET,
        encoding: Encoding | UnsetType = UNSET,
        default_user: str | Callable[[], str] | UnsetType = UNSET,
        default_now: Callable[[], dt.datetime] | UnsetType = UNSET,
    ) -> None:
        """Configure the AutoCRUD instance dynamically.

        This method allows you to reconfigure an existing AutoCRUD instance,
        useful for the global instance pattern where you import a pre-created
        instance and configure it later in your application startup.

        Warning:
            This method should only be called during application initialization,
            before any models are registered or routes are applied. Calling this
            after models have been registered may lead to inconsistent behavior.

        Args:
            model_naming: Controls how model names are converted to URL paths.
            route_templates: Custom list of route templates or configuration dict.
            storage_factory: Storage backend to use for all models.
            message_queue_factory: Message queue factory for async job processing.
            admin: Admin user for RBAC permission system.
            permission_checker: Custom permission checker implementation.
            dependency_provider: Dependency injection provider for routes.
            event_handlers: List of event handlers for lifecycle hooks.
            encoding: Default encoding format (json/msgpack).
            default_user: Default user for operations when not specified.
            default_now: Default timestamp function for operations.

        Example:
            ```python
            from autocrud import crud
            from autocrud.resource_manager.storage_factory import DiskStorageFactory

            # Configure the global instance
            crud.configure(
                storage_factory=DiskStorageFactory("./data"),
                model_naming="snake",
                admin="root@example.com",
            )

            # Now register models
            crud.add_model(User)
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
            storage_factory=storage_factory,
            message_queue_factory=message_queue_factory,
            admin=admin,
            permission_checker=permission_checker,
            dependency_provider=dependency_provider,
            event_handlers=event_handlers,
            encoding=encoding,
            default_user=default_user,
            default_now=default_now,
        )

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
            manager = autocrud.get_resource_manager(User)

            # Get by resource name
            manager = autocrud.get_resource_manager("users")

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


            autocrud = AutoCRUD()
            autocrud.add_route_template(CustomSearchTemplate())
            autocrud.add_model(User)
            ```

        Note:
            Templates are sorted by their order property before being applied.
            Add templates before calling add_model() or apply() for best results.
        """
        self.route_templates.append(template)

    def create_action(
        self,
        resource_name: str,
        *,
        path: str | None = None,
        label: str | None = None,
    ) -> Callable:
        """Decorator to register a custom create action for a resource.

        The decorated function is a standard FastAPI endpoint handler — all input
        parsing (``Body``, ``Query``, ``Path``, ``Depends``, etc.) is handled by
        FastAPI.  If the handler returns a resource-type object, AutoCRUD will
        automatically call ``resource_manager.create()`` and respond with
        ``RevisionInfo``.  If it returns ``None``, no automatic creation occurs.

        Args:
            resource_name: The name of the resource this action belongs to.
            path: URL path suffix (e.g. ``"import-from-url"``).  If ``None``,
                inferred from the function name (underscores → hyphens).
            label: Human-friendly label shown in the UI.  If ``None``,
                inferred from *path* (hyphens → spaces, title-cased).

        Returns:
            A decorator that registers the handler and returns it unchanged.

        Example:
            ```python
            class ImportFromUrl(Struct):
                url: str


            @crud.create_action("article", label="Import from URL")
            async def import_from_url(body: ImportFromUrl = Body(...)):
                content = await fetch_and_parse(body.url)
                return Article(content=content)  # auto-created
            ```

        Note:
            This decorator is lazy — it stores metadata without registering any
            route.  Routes are created when ``apply()`` is called, so the
            decorator can be used before or after ``add_model()``.
        """

        def decorator(func: Callable) -> Callable:
            action_path = path or func.__name__.replace("_", "-")
            action_label = label or action_path.replace("-", " ").title()
            self._pending_create_actions.append(
                _PendingCreateAction(
                    resource_name=resource_name,
                    path=action_path,
                    label=action_label,
                    handler=func,
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
        default_status: RevisionStatus | None = None,
        default_user: str | Callable[[], str] | UnsetType = UNSET,
        default_now: Callable[[], dt.datetime] | UnsetType = UNSET,
        message_queue_factory: IMessageQueueFactory | None | UnsetType = UNSET,
        job_handler: Callable[[Resource[Job[T]]], None] | None = None,
        job_handler_factory: Callable[[], Callable[[Resource[Job[T]]], None]]
        | None = None,
        validator: "Callable[[T], None] | IValidator | type | None" = None,
        constraint_checkers: "Sequence[IConstraintChecker | Callable[[ResourceManager], IConstraintChecker]] | None" = None,
    ) -> None:
        """Add a data model to AutoCRUD and configure its API endpoints.

        This is the main method for registering models with AutoCRUD. Once added,
        the model will have a complete set of CRUD API endpoints generated automatically.

        Args:
            model: The data model class (msgspec Struct, dataclasses, TypedDict).
            name: Custom resource name for URLs. If None, derived from model class name.
            storage_factory: Custom storage backend. If None, uses in-memory storage.
            id_generator: Custom function for generating resource IDs. If None, uses UUID4.
            migration: Migration handler for schema evolution. Used with disk storage.

        Examples:
            Basic usage:
            ```python
            autocrud.add_model(User)  # Creates /users endpoints
            ```

            With custom name:
            ```python
            autocrud.add_model(User, name="people")  # Creates /people endpoints
            ```

            With persistent storage:
            ```python
            storage = DiskStorageFactory("./data")
            autocrud.add_model(User, storage_factory=storage)
            ```

            With custom ID generation:
            ```python
            autocrud.add_model(User, id_generator=lambda: f"user_{int(time.time())}")
            ```

            With migration support:
            ```python
            class UserMigration(IMigration):
                schema_version = "v2"

                def migrate(self, data, old_version):
                    # Handle schema changes
                    return updated_data


            autocrud.add_model(User, migration=UserMigration())
            ```

        Generated Endpoints:
            For a model named "User", this creates:
            - POST /users - Create new user
            - GET /users/data - List users (data only)
            - GET /users/meta - List users (metadata only)
            - GET /users/{id}/data - Get user data
            - GET /users/{id}/full - Get complete user info
            - PUT /users/{id} - Update user
            - DELETE /users/{id} - Soft delete user
            - And many more...

        Raises:
            ValueError: If model is invalid or conflicts with existing models.

        Note:
            Models should be added during application startup before handling requests.
            The order of adding models doesn't affect the generated APIs.
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
        import warnings

        resolved_schema: Schema | None = None
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
            model = resolved_schema.resource_type  # type: ignore[assignment]
            if model is None:
                raise ValueError(
                    "Schema passed as first argument must have a resource_type."
                )
        else:
            # model is a plain type
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

        model_name = name or self._resource_name(model)

        # Handle Pydantic BaseModel as model type:
        # auto-generate struct and use Pydantic for validation
        pydantic_model = None
        if is_pydantic_model(model):
            pydantic_model = model
            model = pydantic_to_struct(pydantic_model)
            if validator is None and (
                resolved_schema is None or not resolved_schema.has_validator
            ):
                validator = pydantic_model

        if model_name in self.resource_managers:
            raise ValueError(f"Model name {model_name} already exists.")
        if model in self.model_names:
            self.model_names[model] = None
            logger.warning(
                f"Model {get_type_name(model) or repr(model)} is already registered with a different name. "
                f"This resource manager will not be accessible by its type.",
            )
        else:
            self.model_names[model] = model_name
        if storage is None:
            storage = self.storage_factory.build(model_name)
        if encoding is None:
            encoding = self.default_encoding
        other_options = {}
        if default_status is not None:
            other_options["default_status"] = default_status
        if default_user is not UNSET:
            other_options["default_user"] = default_user
        elif self.default_user is not UNSET:
            other_options["default_user"] = self.default_user
        if default_now is not UNSET:
            other_options["default_now"] = default_now
        elif self.default_now is not UNSET:
            other_options["default_now"] = self.default_now
        # Auto-detect Job subclass and create message queue
        if self._is_job_subclass(model) and (
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
                real_handler = job_handler
                if job_handler_factory is not None:
                    real_handler = LazyJobHandler(job_handler_factory)

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

        resource_manager = ResourceManager(
            model,
            storage=storage,
            blob_store=self.blob_store,
            id_generator=id_generator,
            migration=resolved_schema or migration,
            indexed_fields=_indexed_fields,
            event_handlers=self.event_handlers or event_handlers,
            permission_checker=self.permission_checker or permission_checker,
            encoding=encoding,
            name=model_name,
            validator=validator,
            pydantic_type=pydantic_model,
            constraint_checkers=constraint_checkers,
            **other_options,
        )
        self.resource_managers[model_name] = resource_manager

        # Scan Ref / RefRevision annotations and collect relationships
        refs = extract_refs(model, model_name)
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

    @staticmethod
    def _get_unique_fields(rm: ResourceManager) -> list[str]:
        """Extract unique field names from the RM's registered constraint checkers."""
        from autocrud.resource_manager.constraint_handler import (
            ConstraintEventHandler,
        )
        from autocrud.resource_manager.unique_handler import (
            UniqueConstraintChecker,
        )

        for h in rm.event_handlers:
            handler = None
            if isinstance(h, ConstraintEventHandler):
                handler = h
            if handler is not None:
                for c in handler.checkers:
                    if isinstance(c, UniqueConstraintChecker):
                        return c.unique_fields
        return []

    def openapi(self, app: FastAPI, structs: list[type] = None) -> None:
        """Generate and register the OpenAPI schema for the FastAPI application.

        This method customizes the OpenAPI schema generation to include all the
        AutoCRUD-specific types, models, and response schemas. It ensures that
        the generated API documentation (Swagger UI / ReDoc) correctly reflects
        the structure of your resources and their endpoints.

        Args:
            app: The FastAPI application instance.
            structs: Optional list of additional msgspec Structs to include in the schema.

        Note:
            This method is automatically called when you use `autocrud.apply(app)` if
            you haven't disabled it. You typically don't need to call this manually
            unless you are doing advanced customization of the OpenAPI schema.
        """

        # Handle root_path by setting servers if not already set
        structs = structs or []
        servers = app.servers
        if app.root_path and not servers:
            servers = [{"url": app.root_path}]

        app.openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            summary=app.summary,
            description=app.description,
            terms_of_service=app.terms_of_service,
            contact=app.contact,
            license_info=app.license_info,
            routes=app.routes,
            webhooks=app.webhooks.routes,
            tags=app.openapi_tags,
            servers=servers,
            separate_input_output_schemas=app.separate_input_output_schemas,
        )
        app.openapi_schema["components"]["schemas"] |= jsonschema_to_openapi(
            [
                ResourceMeta,
                RevisionInfo,
                RevisionListResponse,
                *[rm.resource_type for rm in self.resource_managers.values()],
                *[
                    FullResourceResponse[rm.resource_type]
                    for rm in self.resource_managers.values()
                ],
                RFC6902_Add,
                RFC6902_Remove,
                RFC6902_Replace,
                RFC6902_Move,
                RFC6902_Test,
                RFC6902_Copy,
                RFC6902,
                *structs,
            ],
        )[1]

        # Include custom create action body schemas in components
        action_body_structs = []
        for action in self._pending_create_actions:
            if action.resource_name not in self.resource_managers:
                warnings.warn(
                    f"Resource '{action.resource_name}' not found in resource managers. "
                    f"Skipping action '{action.handler.__name__}'.",
                    stacklevel=2,
                )
                continue
            action_body_structs.extend(self._collect_action_body_structs(action))
        if action_body_structs:
            app.openapi_schema["components"]["schemas"] |= jsonschema_to_openapi(
                action_body_structs,
            )[1]

        # Inject x-ref-* / x-ref-revision-* metadata into schema properties
        self._inject_ref_metadata(app.openapi_schema)

        # Inject x-autocrud-custom-create-actions top-level extension
        self._inject_custom_create_actions(app.openapi_schema)

    def _inject_ref_metadata(self, schema: dict) -> None:
        """Post-process OpenAPI schema to inject ``x-ref-*`` extensions.

        This scans all registered resource Structs — and their nested Struct
        fields (e.g. ``Job[PayloadType]``) — for ``Ref`` / ``RefRevision``
        annotations and writes the corresponding ``x-ref-resource``,
        ``x-ref-type``, and ``x-ref-on-delete`` extensions into the matching
        schema properties so the web generator can discover relationships.
        """
        components = schema.get("components", {}).get("schemas", {})
        all_refs: list[_RefInfo] = []

        # Collect (schema_name, refs) pairs for both top-level and nested Structs
        processed_structs: set[type] = set()

        def _inject_into_component(comp_name: str, refs: list[_RefInfo]) -> None:
            comp = components.get(comp_name)
            if not comp or "properties" not in comp:
                return
            for ref_info in refs:
                prop = comp["properties"].get(ref_info.source_field)
                if not prop:
                    continue
                ext: dict[str, str] = {
                    "x-ref-resource": ref_info.target,
                    "x-ref-type": ref_info.ref_type,
                }
                if ref_info.ref_type == "resource_id":
                    ext["x-ref-on-delete"] = ref_info.on_delete.value
                prop.update(ext)

        def _process_single_struct(
            struct_type: type,
            model_name: str,
            *,
            inject_unique: bool = False,
            rm: Any = None,
        ) -> None:
            """Inject ref / display-name / unique metadata for a single Struct
            type into its OpenAPI component, and recurse into nested Structs.
            """
            struct_name = get_type_name(struct_type)
            if struct_name is None:
                return

            refs = extract_refs(struct_type, model_name)
            all_refs.extend(refs)
            _inject_into_component(struct_name, refs)

            # DisplayName annotation
            from autocrud.types import extract_display_name

            dn_field = extract_display_name(struct_type)
            if dn_field is not None:
                comp = components.get(struct_name)
                if comp is not None:
                    comp["x-display-name-field"] = dn_field

            # Unique field annotations (only for top-level resource types)
            if inject_unique and rm is not None:
                unique_fields = self._get_unique_fields(rm)
                if unique_fields:
                    comp = components.get(struct_name)
                    if comp is not None:
                        props = comp.get("properties", {})
                        for uf in unique_fields:
                            prop = props.get(uf)
                            if prop is not None:
                                prop["x-unique"] = True

            # Nested Struct types (e.g. Job[Payload])
            nested = collect_nested_struct_types(struct_type, set())
            for nested_struct in nested:
                if nested_struct in processed_structs:
                    continue
                processed_structs.add(nested_struct)
                nested_refs = extract_refs(nested_struct, model_name)
                all_refs.extend(nested_refs)
                nested_name = get_type_name(nested_struct)
                if nested_name is not None:
                    _inject_into_component(nested_name, nested_refs)

        for model_name, rm in self.resource_managers.items():
            processed_structs.add(rm.resource_type)

            if is_union_type(rm.resource_type):
                # Union type (e.g. Cat | Dog) — process each member type
                member_types = get_union_args(rm.resource_type) or ()
                for member_type in member_types:
                    if member_type in processed_structs:
                        continue
                    processed_structs.add(member_type)
                    _process_single_struct(
                        member_type, model_name, inject_unique=False, rm=rm
                    )
                continue

            # Regular (non-union) resource Struct
            _process_single_struct(
                rm.resource_type, model_name, inject_unique=True, rm=rm
            )

        # Also process custom create action body schemas so that Ref /
        # RefRevision annotations in action body Structs get x-ref-*
        # extensions injected into their OpenAPI components.
        for action in self._pending_create_actions:
            if action.resource_name not in self.resource_managers:
                continue
            for body_struct in self._collect_action_body_structs(action):
                if body_struct in processed_structs:
                    continue
                processed_structs.add(body_struct)
                _process_single_struct(
                    body_struct,
                    action.resource_name,
                    inject_unique=False,
                    rm=None,
                )

        # Also inject a top-level x-autocrud-relationships extension
        if all_refs:
            schema["x-autocrud-relationships"] = [
                {
                    "source": r.source,
                    "sourceField": r.source_field,
                    "target": r.target,
                    "refType": r.ref_type,
                    "onDelete": r.on_delete.value,
                    "nullable": r.nullable,
                }
                for r in all_refs
            ]

    @staticmethod
    def _get_body_schema_name(handler: Any) -> str | None:
        """Extract the body parameter's schema name from a handler signature.

        Scans the handler's parameters for the first ``msgspec.Struct`` or
        Pydantic ``BaseModel`` type annotation and returns its ``__name__``.
        """
        import msgspec

        sig = inspect.signature(handler)
        for param in sig.parameters.values():
            ann = param.annotation
            if ann is inspect.Parameter.empty:
                continue
            # Unwrap Annotated[T, ...] → T
            ann, _ = unwrap_annotated(ann)
            if isinstance(ann, type) and issubclass(ann, msgspec.Struct):
                return ann.__name__
            # Pydantic BaseModel check
            if isinstance(ann, type):
                try:
                    from pydantic import BaseModel

                    if issubclass(ann, BaseModel):
                        return ann.__name__
                except ImportError:
                    pass
        return None

    @staticmethod
    def _collect_action_body_structs(action: Any) -> list[type]:
        """Return all ``msgspec.Struct`` types found in *action* handler params.

        Used by both ``_customize_openapi()`` (to register component schemas)
        and ``_inject_ref_metadata()`` (to inject ``x-ref-*`` extensions).
        """
        import msgspec

        structs: list[type] = []
        sig = inspect.signature(action.handler)
        for param in sig.parameters.values():
            ann = param.annotation
            if ann is inspect.Parameter.empty:
                continue
            ann, _ = unwrap_annotated(ann)
            if isinstance(ann, type) and issubclass(ann, msgspec.Struct):
                structs.append(ann)
        return structs

    @staticmethod
    def _extract_handler_ref_map(handler: Any) -> dict[str, dict[str, str]]:
        """Scan *handler* parameter annotations for ``Ref`` / ``RefRevision``
        markers and return a mapping of ``{param_name: x-ref-* extensions}``.

        This enables path / query / inline-body parameters annotated with
        ``Annotated[str, Ref(...)]`` to carry ``x-ref-resource``, ``x-ref-type``,
        and ``x-ref-on-delete`` metadata into the OpenAPI extension so the web
        generator can render them as RefSelect / RefRevisionSelect.
        """
        ref_map: dict[str, dict[str, str]] = {}
        sig = inspect.signature(handler)
        for param in sig.parameters.values():
            ann = param.annotation
            if ann is inspect.Parameter.empty:
                continue
            _, metadata = unwrap_annotated(ann)
            for meta in metadata:
                if isinstance(meta, Ref):
                    ext: dict[str, str] = {
                        "x-ref-resource": meta.resource,
                        "x-ref-type": meta.ref_type.value,
                    }
                    if meta.ref_type == RefType.resource_id:
                        ext["x-ref-on-delete"] = meta.on_delete.value
                    ref_map[param.name] = ext
                    break
                if isinstance(meta, RefRevision):
                    ref_map[param.name] = {
                        "x-ref-resource": meta.resource,
                        "x-ref-type": "revision_id",
                    }
                    break
        return ref_map

    def _inject_custom_create_actions(self, schema: dict) -> None:
        """Inject ``x-autocrud-custom-create-actions`` top-level extension.

        Groups all registered create actions by resource name and writes a
        lookup table into the OpenAPI schema so the web generator can
        discover custom create actions for each resource.
        """
        if not self._pending_create_actions:
            return

        from collections import defaultdict

        actions_by_resource: dict[str, list[dict]] = defaultdict(list)
        for action in self._pending_create_actions:
            if action.resource_name not in self.resource_managers:
                continue
            # Strip leading slash from action.path to avoid double-slash
            # when the user writes path="/{name}/new".
            action_path_segment = action.path.lstrip("/")
            info: dict[str, str] = {
                "path": f"/{action.resource_name}/{action_path_segment}",
                "label": action.label,
                "operationId": action.handler.__name__,
            }
            body_schema = self._get_body_schema_name(action.handler)
            if body_schema:
                info["bodySchema"] = body_schema
            # Expose path / query parameters from the generated spec
            # so the frontend generator can produce form fields for them.
            paths = schema.get("paths", {})
            operation_path = f"/{action.resource_name}/{action_path_segment}"
            operation = paths.get(operation_path, {}).get("post", {})
            parameters = operation.get("parameters", [])
            pp = [
                {
                    "name": p["name"],
                    "required": p.get("required", True),
                    "schema": p.get("schema", {}),
                }
                for p in parameters
                if p.get("in") == "path"
            ]
            qp = [
                {
                    "name": p["name"],
                    "required": p.get("required", False),
                    "schema": p.get("schema", {}),
                }
                for p in parameters
                if p.get("in") == "query"
            ]
            # Inject x-ref-* metadata from handler annotations into
            # path / query param schemas so the frontend generator can
            # render RefSelect / RefRevisionSelect for these params.
            ref_map = self._extract_handler_ref_map(action.handler)
            for param_list in (pp, qp):
                for p in param_list:
                    ref_ext = ref_map.get(p["name"])
                    if ref_ext:
                        p["schema"].update(ref_ext)
            if pp:
                info["pathParams"] = pp
            if qp:
                info["queryParams"] = qp
            # Extract inline body params and file params from the request body
            # schema.  This works both when bodySchema is set (mixed case with
            # additional Body(embed=True) / UploadFile params) and when there is
            # no body schema (pure compositional case).
            # When UploadFile is present, FastAPI uses multipart/form-data
            # instead of application/json, so we check both content types.
            content = operation.get("requestBody", {}).get("content", {})
            rb = content.get("application/json", {}).get("schema", {})
            # Fall back to multipart/form-data (when UploadFile is present)
            if not rb:
                rb = content.get("multipart/form-data", {}).get("schema", {})
            # Resolve $ref to components/schemas
            if "$ref" in rb:
                ref_name = rb["$ref"].split("/")[-1]
                rb = schema.get("components", {}).get("schemas", {}).get(ref_name, {})
            props: dict = rb.get("properties", {})
            required_list: list = rb.get("required", [])
            # When bodySchema is set, identify the property that IS the body
            # schema (via $ref or allOf.$ref) so we can exclude it from inline
            # params and avoid duplication.
            body_schema_prop_names: set[str] = set()
            if body_schema:
                for pname, pschema in props.items():
                    ref_target = pschema.get("$ref", "")
                    if not ref_target and "allOf" in pschema:
                        for item in pschema["allOf"]:
                            if "$ref" in item:
                                ref_target = item["$ref"]
                                break
                    if ref_target and ref_target.split("/")[-1] == body_schema:
                        body_schema_prop_names.add(pname)
            # Record the handler parameter name for the body schema so
            # the frontend generator can build the correct FormData /
            # JSON body key when mixing body-schema + other param types.
            if body_schema_prop_names:
                info["bodySchemaParamName"] = next(iter(body_schema_prop_names))
            # Separate file params (format=binary) from inline body params
            file_params: list[dict] = []
            inline_params: list[dict] = []
            for pname, pschema in props.items():
                if pname in body_schema_prop_names:
                    continue  # Skip the body schema field itself
                if pschema.get("format") == "binary":
                    file_params.append(
                        {
                            "name": pname,
                            "required": pname in required_list,
                            "schema": {
                                "type": pschema.get("type", "string"),
                                "format": "binary",
                            },
                        }
                    )
                else:
                    inline_params.append(
                        {
                            "name": pname,
                            "required": pname in required_list,
                            "schema": pschema,
                        }
                    )
            # Inject x-ref-* into inline body param schemas
            for p in inline_params:
                ref_ext = ref_map.get(p["name"])
                if ref_ext:
                    p["schema"].update(ref_ext)
            if inline_params:
                info["inlineBodyParams"] = inline_params
            if file_params:
                info["fileParams"] = file_params
            # Warn when two actions for the same resource share the same label —
            # duplicate labels cause frontend key collisions and confuse users.
            existing_labels = {
                a["label"] for a in actions_by_resource[action.resource_name]
            }
            if action.label in existing_labels:
                warnings.warn(
                    f"Resource '{action.resource_name}' already has a create action "
                    f"with label '{action.label}' "
                    f"(duplicate handler: '{action.handler.__name__}'). "
                    f"Duplicate labels will cause frontend key collisions.",
                    stacklevel=2,
                )
            actions_by_resource[action.resource_name].append(info)

        if actions_by_resource:
            schema["x-autocrud-custom-create-actions"] = dict(actions_by_resource)

    def _install_ref_integrity_handlers(self) -> None:
        """Install event handlers for referential integrity (cascade / set_null).

        For each registered resource that is a *target* of a ``Ref`` with
        ``on_delete`` of ``cascade`` or ``set_null``, this method registers a
        ``_RefIntegrityHandler`` on the target's ``ResourceManager`` so that
        when the target is deleted the referencing resources are automatically
        updated.
        """
        registered = set(self.resource_managers.keys())

        # Build a mapping: target_resource -> list of actionable refs
        from collections import defaultdict

        target_refs: dict[str, list[_RefInfo]] = defaultdict(list)
        for ref_info in self.relationships:
            if (
                ref_info.on_delete != OnDelete.dangling
                and ref_info.target in registered
                and ref_info.source in registered
            ):
                target_refs[ref_info.target].append(ref_info)

        for target_name, refs in target_refs.items():
            handler = _RefIntegrityHandler(
                refs=refs,
                resource_managers=self.resource_managers,
            )
            target_rm = self.resource_managers[target_name]
            target_rm.event_handlers.append(handler)

    def apply(self, router: APIRouter) -> APIRouter:
        """Apply all route templates to generate API endpoints on the given router.

        This method generates all the CRUD endpoints for all registered models
        and applies them to the provided FastAPI router. This is typically the
        final step in setting up your AutoCRUD API.

        Args:
            router: FastAPI APIRouter or FastAPI app instance to add routes to.

        Returns:
            The same router instance with all generated routes added.

        Example:
            ```python
            from fastapi import FastAPI
            from autocrud import AutoCRUD

            app = FastAPI()
            autocrud = AutoCRUD()

            # Add your models
            autocrud.add_model(User)
            autocrud.add_model(Post)

            # Generate and apply all routes
            autocrud.apply(app)

            # Or with a sub-router
            api_router = APIRouter(prefix="/api/v1")
            autocrud.apply(api_router)
            app.include_router(api_router)
            ```

        Generated Routes:
            For each model, applies all route templates in order to create
            a comprehensive set of CRUD endpoints. The exact endpoints depend
            on the route templates configured.

        Note:
            - Call this method after adding all models and custom route templates
            - Each route template is applied to each model in the order specified
            - Routes are generated dynamically based on model structure
            - This method is idempotent - calling it multiple times is safe
        """
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

        self.route_templates.sort()
        for model_name, resource_manager in self.resource_managers.items():
            for route_template in self.route_templates:
                try:
                    route_template.apply(model_name, resource_manager, router)
                except Exception:
                    pass

        # Register custom create action routes
        self._apply_create_actions(router)

        # Add ref-specific routes (referrers + relationships)
        self._apply_ref_routes(router)

        return router

    def _apply_create_actions(self, router: APIRouter) -> None:
        """Register routes for all pending custom create actions."""
        import msgspec as _msgspec

        from autocrud.crud.route_templates.basic import (
            MsgspecResponse,
            jsonschema_to_json_schema_extra,
            struct_to_responses_type,
        )

        def _is_msgspec_struct_type(ann: type) -> bool:
            """Check if *ann* is a msgspec.Struct subclass."""
            return isinstance(ann, type) and issubclass(ann, _msgspec.Struct)

        def _build_fastapi_compatible_handler(handler, resource_manager):
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
            """
            sig = inspect.signature(handler)
            # Identify parameters whose annotation is a msgspec.Struct subclass
            # so we can convert them from raw dicts.
            struct_params: dict[str, type] = {}
            new_params: list[inspect.Parameter] = []
            new_annotations: dict[str, Any] = {}

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

            new_sig = sig.replace(
                parameters=new_params, return_annotation=inspect.Parameter.empty
            )

            if asyncio.iscoroutinefunction(handler):

                async def wrapper(*args, **kwargs):
                    # Convert raw dicts to Struct instances
                    for pname, struct_type in struct_params.items():
                        if pname in kwargs:
                            kwargs[pname] = _msgspec.convert(kwargs[pname], struct_type)
                    result = await handler(*args, **kwargs)
                    if result is None:
                        return None
                    with resource_manager.meta_provide("system", dt.datetime.now()):
                        info = resource_manager.create(result)
                    return MsgspecResponse(info)

            else:

                def wrapper(*args, **kwargs):
                    for pname, struct_type in struct_params.items():
                        if pname in kwargs:
                            kwargs[pname] = _msgspec.convert(kwargs[pname], struct_type)
                    result = handler(*args, **kwargs)
                    if result is None:
                        return None
                    with resource_manager.meta_provide("system", dt.datetime.now()):
                        info = resource_manager.create(result)
                    return MsgspecResponse(info)

            wrapper.__name__ = handler.__name__
            wrapper.__qualname__ = handler.__qualname__
            wrapper.__module__ = handler.__module__
            wrapper.__doc__ = handler.__doc__
            wrapper.__signature__ = new_sig
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
            _wrapper = _build_fastapi_compatible_handler(action.handler, rm)

            router.post(
                route_path,
                response_model=None,
                responses=struct_to_responses_type(RevisionInfo),
                summary=f"{action.label} ({action.resource_name})",
                tags=[f"{action.resource_name}"],
                openapi_extra={
                    "x-autocrud-create-action": {
                        "resource": action.resource_name,
                        "label": action.label,
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
                autocrud.dump(f)

            # Dump only User resources where name == "Alice"
            from autocrud.query import QB

            with open("backup.acbak", "wb") as f:
                autocrud.dump(f, model_queries={"user": QB.name == "Alice"})
        """
        from autocrud.resource_manager.dump_format import (
            BlobRecord,
            DumpStreamWriter,
            EofRecord,
            HeaderRecord,
            MetaRecord,
            ModelEndRecord,
            ModelStartRecord,
            RevisionRecord,
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
            for key, value in mgr.dump(query=query):
                data = value.read()
                if key.startswith("meta/"):
                    writer.write(MetaRecord(data=data))
                elif key.startswith("data/"):
                    writer.write(RevisionRecord(data=data))
                elif key.startswith("blob/"):
                    blob_entry = mgr._blob_serializer.decode(data)
                    writer.write(
                        BlobRecord(
                            file_id=blob_entry.file_id,
                            blob_data=blob_entry.data,
                            size=blob_entry.size,
                            content_type=blob_entry.content_type,
                        )
                    )
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
        from autocrud.resource_manager.dump_format import (
            BlobRecord,
            DumpStreamReader,
            EofRecord,
            HeaderRecord,
            MetaRecord,
            ModelEndRecord,
            ModelStartRecord,
            RevisionRecord,
        )
        from autocrud.types import OnDuplicate as _OnDuplicate

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
        skipped_ids: set[str] = set()

        for record in reader:
            if isinstance(record, ModelStartRecord):
                current_model = record.model_name
                if current_model not in self.resource_managers:
                    raise ValueError(
                        f"Model '{current_model}' not found in resource managers."
                    )
                current_mgr = self.resource_managers[current_model]
                skipped_ids = set()
                if current_model not in stats:
                    stats[current_model] = LoadStats()

            elif isinstance(record, ModelEndRecord):
                current_model = None
                current_mgr = None
                skipped_ids = set()

            elif isinstance(record, MetaRecord):
                if current_mgr is None:
                    raise ValueError("MetaRecord outside of model section.")
                st = stats[current_model]
                st.total += 1
                try:
                    loaded = current_mgr.load_record(record, on_duplicate)
                except Exception:
                    raise
                if loaded:
                    st.loaded += 1
                else:
                    st.skipped += 1
                    # Track skipped resource_id so we skip its revisions too
                    meta = current_mgr.meta_serializer.decode(record.data)
                    skipped_ids.add(meta.resource_id)

            elif isinstance(record, RevisionRecord):
                if current_mgr is None:
                    raise ValueError("RevisionRecord outside of model section.")
                # If the parent resource was skipped, skip its revisions
                raw_res = current_mgr.resource_serializer.decode(record.data)
                if raw_res.info.resource_id in skipped_ids:
                    continue
                current_mgr.load_record(record, on_duplicate)

            elif isinstance(record, BlobRecord):
                if current_mgr is None:
                    raise ValueError("BlobRecord outside of model section.")
                current_mgr.load_record(record, on_duplicate)

            elif isinstance(record, EofRecord):
                break

        return stats
