from __future__ import annotations

import io
import tarfile
from collections import OrderedDict
from collections.abc import Callable, Sequence
from typing import IO, Literal, TypeVar
import logging
from fastapi import APIRouter, FastAPI
import datetime as dt
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
from autocrud.resource_manager.core import ResourceManager
from autocrud.resource_manager.storage_factory import (
    IStorageFactory,
    MemoryStorageFactory,
)
from autocrud.types import (
    IEventHandler,
    IMigration,
    IPermissionChecker,
    IResourceManager,
    IndexableField,
    ResourceMeta,
    RevisionInfo,
    RevisionStatus,
)
from autocrud.util.naming import NameConverter

logger = logging.getLogger(__name__)
T = TypeVar("T")


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
        route_templates: Custom list of route templates to use instead of defaults.
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
        route_templates: list[IRouteTemplate] | None = None,
        storage_factory: IStorageFactory | None = None,
        admin: str | None = None,
        permission_checker: IPermissionChecker | None = None,
        dependency_provider: DependencyProvider | None = None,
        event_handlers: Sequence[IEventHandler] | None = None,
        encoding: Encoding = Encoding.json,
        default_user: str | UnsetType = UNSET,
        default_now: Callable[[], dt.datetime] | UnsetType = UNSET,
    ):
        if storage_factory is None:
            self.storage_factory = MemoryStorageFactory()
        else:
            self.storage_factory = storage_factory
        self.resource_managers: OrderedDict[str, IResourceManager] = OrderedDict()
        self.model_names: dict[type[T], str | None] = {}
        self.model_naming = model_naming
        self.route_templates: list[IRouteTemplate] = (
            [
                CreateRouteTemplate(dependency_provider=dependency_provider),
                ListRouteTemplate(dependency_provider=dependency_provider),
                ReadRouteTemplate(dependency_provider=dependency_provider),
                UpdateRouteTemplate(dependency_provider=dependency_provider),
                PatchRouteTemplate(dependency_provider=dependency_provider),
                SwitchRevisionRouteTemplate(dependency_provider=dependency_provider),
                DeleteRouteTemplate(dependency_provider=dependency_provider),
                RestoreRouteTemplate(dependency_provider=dependency_provider),
            ]
            if route_templates is None
            else route_templates
        )
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
        default_user: str | UnsetType = UNSET,
        default_now: Callable[[], dt.datetime] | UnsetType = UNSET,
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
        _indexed_fields = []
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
        resource_manager = ResourceManager(
            model,
            storage=storage,
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
