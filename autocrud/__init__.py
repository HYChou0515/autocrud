"""AutoCRUD - 自動化 CRUD 系統"""

__version__ = "0.2.1"

from .core import SingleModelCRUD
from .multi_model import AutoCRUD, ResourceNameStyle
from .storage import MemoryStorage, DiskStorage, Storage
from .converter import ModelConverter
from .serializer import SerializerFactory
from .fastapi_generator import FastAPIGenerator
from .storage_factory import StorageFactory, DefaultStorageFactory
from .route_config import RouteConfig, RouteOptions
from .metadata import MetadataConfig
from .schema_analyzer import SchemaAnalyzer
from .list_params import ListQueryParams, ListResult, DateTimeRange, SortOrder
from .plugin_system import (
    RoutePlugin,
    BaseRoutePlugin,
    PluginManager,
    PluginRouteConfig,
    RouteMethod,
    plugin_manager,
    ensure_default_plugins_registered,
)
from .default_plugins import DEFAULT_PLUGINS
from .updater import (
    AdvancedUpdater,
    UpdateOperation,
    UpdateAction,
    undefined,
    set_value,
    list_set,
    list_add,
    list_remove,
    dict_set,
    dict_update,
    dict_remove,
)

__all__ = [
    "AutoCRUD",
    "ResourceNameStyle",
    "SingleModelCRUD",
    "MemoryStorage",
    "DiskStorage",
    "Storage",
    "ModelConverter",
    "SerializerFactory",
    "FastAPIGenerator",
    "StorageFactory",
    "DefaultStorageFactory",
    "RouteConfig",
    "RouteOptions",
    "MetadataConfig",
    "SchemaAnalyzer",
    "ListQueryParams",
    "ListResult",
    "DateTimeRange",
    "SortOrder",
    "RoutePlugin",
    "BaseRoutePlugin",
    "PluginManager",
    "PluginRouteConfig",
    "RouteMethod",
    "plugin_manager",
    "ensure_default_plugins_registered",
    "DEFAULT_PLUGINS",
    "AdvancedUpdater",
    "UpdateOperation",
    "UpdateAction",
    "undefined",
    "set_value",
    "list_set",
    "list_add",
    "list_remove",
    "dict_set",
    "dict_update",
    "dict_remove",
]
