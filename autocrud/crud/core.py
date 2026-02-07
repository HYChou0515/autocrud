from __future__ import annotations

import datetime as dt
import io
import logging
import tarfile
from collections import OrderedDict
from collections.abc import Callable, Sequence
from typing import IO, Any, Literal, TypeVar

from fastapi import APIRouter, FastAPI
from fastapi.openapi.utils import get_openapi
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
    DeleteRouteTemplate,
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
from autocrud.crud.route_templates.search import ListRouteTemplate
from autocrud.crud.route_templates.switch import SwitchRevisionRouteTemplate
from autocrud.crud.route_templates.update import UpdateRouteTemplate
from autocrud.permission.rbac import RBACPermissionChecker
from autocrud.permission.simple import AllowAll
from autocrud.resource_manager.basic import (
    Encoding,
    IStorage,
)
from autocrud.resource_manager.blob_store.simple import DiskBlobStore, MemoryBlobStore
from autocrud.resource_manager.core import ResourceManager
from autocrud.resource_manager.storage_factory import (
    DiskStorageFactory,
    IStorageFactory,
    MemoryStorageFactory,
)
from autocrud.types import (
    IEventHandler,
    IMessageQueue,
    IMessageQueueFactory,
    IMigration,
    IndexableField,
    IPermissionChecker,
    IResourceManager,
    Job,
    Resource,
    ResourceMeta,
    RevisionInfo,
    RevisionStatus,
    TaskStatus,
)
from autocrud.util.naming import NameConverter

logger = logging.getLogger(__name__)
T = TypeVar("T")


class LazyJobHandler:
    def __init__(self, factory):
        self._factory = factory
        self._handler = None

    def __call__(self, resource):
        if self._handler is None:
            self._handler = self._factory()
        return self._handler(resource)


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
        if storage_factory is None:
            self.storage_factory = MemoryStorageFactory()
        else:
            self.storage_factory = storage_factory

        self.blob_store = None
        if isinstance(self.storage_factory, DiskStorageFactory):
            self.blob_store = DiskBlobStore(self.storage_factory.rootdir / "_blobs")
        elif hasattr(self.storage_factory, "build_blob_store"):
            # S3StorageFactory 或其他提供 build_blob_store 方法的 factory
            self.blob_store = self.storage_factory.build_blob_store()
        else:
            self.blob_store = MemoryBlobStore()

        self.resource_managers: OrderedDict[str, IResourceManager] = OrderedDict()
        self.message_queues: OrderedDict[str, IMessageQueue] = OrderedDict()
        self.model_names: dict[type[T], str | None] = {}
        self.model_naming = model_naming

        # Set default message queue factory
        if message_queue_factory is None:
            from autocrud.message_queue.simple import SimpleMessageQueueFactory

            self.message_queue_factory = SimpleMessageQueueFactory()
        else:
            self.message_queue_factory = message_queue_factory
        self.route_templates: list[IRouteTemplate] = []
        if route_templates is None or isinstance(route_templates, dict):
            route_templates = route_templates or {}
            for rt in [
                CreateRouteTemplate,
                ListRouteTemplate,
                ReadRouteTemplate,
                UpdateRouteTemplate,
                PatchRouteTemplate,
                SwitchRevisionRouteTemplate,
                DeleteRouteTemplate,
                RestoreRouteTemplate,
            ]:
                more_kwargs = route_templates.get(rt, {})
                more_kwargs.setdefault("dependency_provider", dependency_provider)
                self.route_templates.append(rt(**more_kwargs))
        else:
            self.route_templates = route_templates
        if permission_checker is None:
            if not admin:
                self.permission_checker = AllowAll()
            else:
                self.permission_checker = RBACPermissionChecker(
                    storage_factory=self.storage_factory,
                    root_user=admin,
                )
        else:
            self.permission_checker = permission_checker

        self.event_handlers = event_handlers
        self.default_encoding = encoding
        self.default_user = default_user
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

        # Update model_naming
        if model_naming is not UNSET:
            self.model_naming = model_naming

        # Update storage_factory and blob_store
        if storage_factory is not UNSET:
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
                    DeleteRouteTemplate,
                    RestoreRouteTemplate,
                ]:
                    more_kwargs = route_templates_dict.get(rt, {})
                    more_kwargs.setdefault("dependency_provider", dep_provider)
                    self.route_templates.append(rt(**more_kwargs))
            else:
                self.route_templates = route_templates

        # Update permission_checker
        if permission_checker is not UNSET:
            self.permission_checker = permission_checker
        elif admin is not UNSET:
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
                f"Model {model.__name__} is registered with multiple names."
            )
        return self.resource_managers[model_name]

    def _is_job_subclass(self, model: type) -> bool:
        """Check if a model is a subclass of Job.

        Args:
            model: The model class to check.

        Returns:
            True if the model is a Job subclass, False otherwise.
        """
        try:
            from typing import get_origin

            # First check if model itself is a generic Job type like Job[T]
            origin = get_origin(model)
            if origin is Job:
                return True

            # Check if model has __mro__ (method resolution order)
            if not hasattr(model, "__mro__"):
                return False

            # Walk through the MRO to find Job
            for base in model.__mro__:
                base_origin = get_origin(base)
                if base_origin is not None:
                    # This is a generic type, check if origin is Job
                    if base_origin is Job:
                        return True
                elif base is Job:
                    return True

            return False
        except (AttributeError, TypeError):
            return False

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
        original_name = model.__name__

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

    def add_model(
        self,
        model: type[T],
        *,
        name: str | None = None,
        id_generator: Callable[[], str] | None = None,
        storage: IStorage | None = None,
        migration: IMigration | None = None,
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

        model_name = name or self._resource_name(model)
        if model_name in self.resource_managers:
            raise ValueError(f"Model name {model_name} already exists.")
        if model in self.model_names:
            self.model_names[model] = None
            logger.warning(
                f"Model {model.__name__} is already registered with a different name. "
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
            migration=migration,
            indexed_fields=_indexed_fields,
            event_handlers=self.event_handlers or event_handlers,
            permission_checker=self.permission_checker or permission_checker,
            encoding=encoding,
            name=model_name,
            **other_options,
        )
        self.resource_managers[model_name] = resource_manager

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
        self.route_templates.sort()
        for model_name, resource_manager in self.resource_managers.items():
            for route_template in self.route_templates:
                try:
                    route_template.apply(model_name, resource_manager, router)
                except Exception:
                    pass
        return router

    def dump(self, bio: IO[bytes]) -> None:
        """Export all resources and their data to a tar archive for backup or migration.

        This method creates a complete backup of all resources managed by AutoCRUD,
        including all data, metadata, and revision history. The output is a tar
        archive that can be used for backup, migration, or data transfer purposes.

        Args:
            bio: A binary I/O stream to write the tar archive to.

        Example:
            ```python
            # Backup to file
            with open("backup.tar", "wb") as f:
                autocrud.dump(f)

            # Backup to memory buffer
            import io

            buffer = io.BytesIO()
            autocrud.dump(buffer)
            backup_data = buffer.getvalue()

            # Upload to cloud storage
            import boto3

            s3 = boto3.client("s3")
            with io.BytesIO() as buffer:
                autocrud.dump(buffer)
                buffer.seek(0)
                s3.upload_fileobj(buffer, "backup-bucket", "autocrud-backup.tar")
            ```

        Archive Structure:
            The tar archive contains:
            - One directory per model (e.g., "users/", "posts/")
            - Within each directory, files containing resource data
            - All metadata, revision history, and relationships preserved
            - Compatible with the load() method for restoration

        Use Cases:
            - Regular backups of your data
            - Migrating between environments
            - Data archival and compliance
            - Disaster recovery preparations
            - Development data seeding

        Note:
            - The archive includes ALL resources, including soft-deleted ones
            - Large datasets may result in large archive files
            - Consider streaming to avoid memory issues with large datasets
            - The archive format is compatible across AutoCRUD versions
        """
        with tarfile.open(fileobj=bio, mode="w|") as tar:
            for model_name, mgr in self.resource_managers.items():
                for key, value in mgr.dump():
                    tarinfo = tarfile.TarInfo(name=f"{model_name}/{key}")
                    if isinstance(value, io.BytesIO):
                        tarinfo.size = value.getbuffer().nbytes
                    else:
                        value.seek(0, io.SEEK_END)
                        tarinfo.size = value.tell()
                        value.seek(0)
                    tar.addfile(tarinfo, fileobj=value)

    def load(self, bio: IO[bytes]) -> None:
        """Import resources from a tar archive created by the dump() method.

        This method restores resources from a backup archive, recreating all
        data, metadata, and revision history. It's the complement to dump()
        and enables complete data restoration and migration scenarios.

        Args:
            bio: A binary I/O stream containing the tar archive to load from.

        Example:
            ```python
            # Restore from file backup
            with open("backup.tar", "rb") as f:
                autocrud.load(f)

            # Restore from memory buffer
            import io

            buffer = io.BytesIO(backup_data)
            autocrud.load(buffer)

            # Download and restore from cloud storage
            import boto3

            s3 = boto3.client("s3")
            with io.BytesIO() as buffer:
                s3.download_fileobj("backup-bucket", "autocrud-backup.tar", buffer)
                buffer.seek(0)
                autocrud.load(buffer)
            ```

        Behavior:
            - Only loads data for models that are registered with add_model()
            - Preserves all metadata including timestamps and user information
            - Restores complete revision history for each resource
            - Maintains data integrity and relationships
            - Handles both active and soft-deleted resources

        Migration Scenarios:
            ```python
            # Environment migration
            # On source system:
            autocrud_source.dump(backup_file)

            # On target system:
            autocrud_target.add_model(User)  # Must add models first
            autocrud_target.add_model(Post)
            autocrud_target.load(backup_file)
            ```

        Error Handling:
            - Raises ValueError if archive contains unknown models
            - Raises ValueError if archive format is invalid
            - Existing resources may be overwritten depending on storage backend

        Use Cases:
            - Disaster recovery and data restoration
            - Environment migrations (dev → staging → prod)
            - Data seeding for testing environments
            - Historical data imports
            - System migrations and upgrades

        Important Notes:
            - Models must be registered before loading data for them
            - Archive must be created by a compatible dump() method
            - Loading may overwrite existing resources with same IDs
            - Consider backup existing data before loading
            - Large archives may take significant time to process
        """
        with tarfile.open(fileobj=bio, mode="r|") as tar:
            for tarinfo in tar:
                if not tarinfo.isfile():
                    raise ValueError(f"TarInfo {tarinfo.name} is not a file.")
                model_name, key = tarinfo.name.split("/", 1)
                if model_name in self.resource_managers:
                    mgr = self.resource_managers[model_name]
                    mgr.load(key, tar.extractfile(tarinfo))
                else:
                    raise ValueError(
                        f"Model {model_name} not found in resource managers.",
                    )
