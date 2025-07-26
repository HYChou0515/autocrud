"""
Plugin system for AutoCRUD route generation.
允許用戶定義自己的 route 並注入到系統中。
"""

from typing import Protocol, Any, Dict, List, Optional, Callable, Union
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from .core import SingleModelCRUD
from .route_config import RouteOptions


class RouteMethod(Enum):
    """HTTP methods supported by routes"""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


@dataclass
class PluginRouteConfig:
    """Configuration for a plugin route"""

    # Route identification
    name: str  # 路由名稱，用於識別
    path: str  # 路由路徑，相對於資源路徑
    method: RouteMethod  # HTTP 方法

    # Route behavior
    handler: Callable  # 路由處理函數
    options: RouteOptions  # 路由選項（包含 background task 配置）

    # FastAPI route parameters
    response_model: Optional[Any] = None
    status_code: Optional[int] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    dependencies: Optional[List[Any]] = None
    responses: Optional[Dict[Union[int, str], Dict[str, Any]]] = None

    # Plugin metadata
    priority: int = 100  # 路由優先級，數字越小優先級越高
    requires_crud: bool = True  # 是否需要 CRUD 實例作為依賴


class RoutePlugin(Protocol):
    """
    Protocol for route plugins.
    所有的 route plugin 都必須實現這個 interface。
    """

    @property
    def name(self) -> str:
        """Plugin 名稱"""
        ...

    @property
    def version(self) -> str:
        """Plugin 版本"""
        ...

    def get_routes(self, crud: SingleModelCRUD) -> List[PluginRouteConfig]:
        """
        獲取這個 plugin 提供的所有路由配置

        Args:
            crud: SingleModelCRUD 實例，用於訪問模型和存儲

        Returns:
            List[PluginRouteConfig]: 路由配置列表
        """
        ...

    def is_compatible(self, crud: SingleModelCRUD) -> bool:
        """
        檢查這個 plugin 是否與給定的 CRUD 實例兼容

        Args:
            crud: SingleModelCRUD 實例

        Returns:
            bool: 是否兼容
        """
        ...


class BaseRoutePlugin(ABC):
    """
    Base class for route plugins.
    提供一些常用的實現。
    """

    def __init__(self, name: str, version: str = "1.0.0"):
        self._name = name
        self._version = version

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return self._version

    @abstractmethod
    def get_routes(self, crud: SingleModelCRUD) -> List[PluginRouteConfig]:
        """子類必須實現這個方法"""
        pass

    def is_compatible(self, crud: SingleModelCRUD) -> bool:
        """默認實現：所有 CRUD 都兼容"""
        return True

    def _create_handler_with_crud(self, handler: Callable) -> Callable:
        """
        創建一個包裝器，將 CRUD 實例注入到處理函數中
        """

        def wrapper(crud: SingleModelCRUD):
            def inner(*args, **kwargs):
                return handler(crud, *args, **kwargs)

            return inner

        return wrapper


class PluginManager:
    """
    Plugin manager for managing and executing route plugins.
    """

    def __init__(self):
        self._plugins: List[RoutePlugin] = []
        self._default_plugins: List[RoutePlugin] = []

    def register_plugin(self, plugin: RoutePlugin, is_default: bool = False):
        """
        註冊一個 plugin

        Args:
            plugin: 要註冊的 plugin
            is_default: 是否為系統預設的 plugin
        """
        if is_default:
            self._default_plugins.append(plugin)
        else:
            self._plugins.append(plugin)

    def unregister_plugin(self, plugin_name: str):
        """
        移除一個 plugin

        Args:
            plugin_name: plugin 名稱
        """
        self._plugins = [p for p in self._plugins if p.name != plugin_name]

    def get_all_plugins(self) -> List[RoutePlugin]:
        """獲取所有已註冊的 plugins（預設 + 用戶定義）"""
        ensure_default_plugins_registered()
        return self._default_plugins + self._plugins

    def get_user_plugins(self) -> List[RoutePlugin]:
        """只獲取用戶定義的 plugins"""
        return self._plugins.copy()

    def get_default_plugins(self) -> List[RoutePlugin]:
        """只獲取系統預設的 plugins"""
        ensure_default_plugins_registered()
        return self._default_plugins.copy()

    def get_routes_for_crud(self, crud: SingleModelCRUD) -> List[PluginRouteConfig]:
        """
        獲取適用於指定 CRUD 的所有路由配置

        Args:
            crud: SingleModelCRUD 實例

        Returns:
            List[PluginRouteConfig]: 按優先級排序的路由配置列表
        """
        ensure_default_plugins_registered()
        all_routes = []

        for plugin in self.get_all_plugins():
            if plugin.is_compatible(crud):
                routes = plugin.get_routes(crud)
                all_routes.extend(routes)

        # 按優先級排序（數字越小優先級越高）
        all_routes.sort(key=lambda r: r.priority)

        return all_routes

    def clear_user_plugins(self):
        """清除所有用戶定義的 plugins"""
        self._plugins.clear()


# Global plugin manager instance
plugin_manager = PluginManager()


# 在模組載入時自動註冊預設 plugins
def _register_default_plugins():
    """註冊預設 plugins"""
    try:
        from .default_plugins import DEFAULT_PLUGINS

        for plugin in DEFAULT_PLUGINS:
            plugin_manager.register_plugin(plugin, is_default=True)
    except ImportError:
        # 如果 default_plugins 模組還沒載入，忽略錯誤
        pass


# 延遲註冊，在需要時才註冊
_default_plugins_registered = False


def ensure_default_plugins_registered():
    """確保預設 plugins 已註冊"""
    global _default_plugins_registered
    if not _default_plugins_registered:
        _register_default_plugins()
        _default_plugins_registered = True
