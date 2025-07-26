"""
Route configuration system for controlling which CRUD routes to enable.
"""

from typing import Dict, Optional, Union, Callable, Any
from dataclasses import dataclass
from enum import Enum


class BackgroundTaskMode(Enum):
    """Background task execution modes"""

    DISABLED = "disabled"
    ENABLED = "enabled"
    CONDITIONAL = "conditional"


@dataclass
class RouteOptions:
    """Options for individual route configuration"""

    enabled: bool = True
    background_task: BackgroundTaskMode = BackgroundTaskMode.DISABLED
    background_task_func: Optional[Callable] = None
    background_task_condition: Optional[Callable] = None

    # Additional route-specific options
    custom_status_code: Optional[int] = None
    custom_dependencies: Optional[list] = None

    @classmethod
    def enabled_route(cls) -> "RouteOptions":
        """Create a simple enabled route"""
        return cls(enabled=True)

    @classmethod
    def disabled_route(cls) -> "RouteOptions":
        """Create a disabled route"""
        return cls(enabled=False)

    @classmethod
    def background_route(
        cls,
        func: Callable,
        mode: BackgroundTaskMode = BackgroundTaskMode.ENABLED,
        condition: Optional[Callable] = None,
    ) -> "RouteOptions":
        """Create a route with background task"""
        return cls(
            enabled=True,
            background_task=mode,
            background_task_func=func,
            background_task_condition=condition,
        )


@dataclass
class RouteConfig:
    """Configuration for CRUD route generation"""

    # Basic CRUD operations - now using RouteOptions instead of bool
    create: Union[bool, RouteOptions] = True
    get: Union[bool, RouteOptions] = True
    update: Union[bool, RouteOptions] = True
    delete: Union[bool, RouteOptions] = True
    list: Union[bool, RouteOptions] = True

    # Additional operations
    count: Union[bool, RouteOptions] = True

    def __post_init__(self):
        """Convert bool values to RouteOptions for consistency"""
        for field_name in ["create", "get", "update", "delete", "list", "count"]:
            # 使用 object.__getattribute__ 避免自定義 __getattribute__ 的干擾
            value = object.__getattribute__(self, field_name)
            # 只轉換 bool 值，保留已經是 RouteOptions 的值
            if isinstance(value, bool):
                if value:
                    setattr(self, field_name, RouteOptions.enabled_route())
                else:
                    setattr(self, field_name, RouteOptions.disabled_route())
            # RouteOptions 實例保持不變

    def __getattribute__(self, name):
        """Provide backward compatibility by returning bool for direct attribute access"""
        if name in ["create", "get", "update", "delete", "list", "count"]:
            route_options = object.__getattribute__(self, name)
            if isinstance(route_options, RouteOptions):
                return route_options.enabled
        return object.__getattribute__(self, name)

    def get_route_options(self, route_name: str) -> RouteOptions:
        """Get RouteOptions for a specific route"""
        try:
            # 直接通過 object.__getattribute__ 獲取原始值，避免 __getattribute__ 的布爾轉換
            options = object.__getattribute__(self, route_name)
            if isinstance(options, RouteOptions):
                return options
            # 如果是 bool，轉換成 RouteOptions
            if options:
                return RouteOptions.enabled_route()
            else:
                return RouteOptions.disabled_route()
        except AttributeError:
            # 對於未知的路由名稱，返回預設啟用的選項
            return RouteOptions.enabled_route()

    def is_route_enabled(self, route_name: str) -> bool:
        """Check if a route is enabled"""
        try:
            options = object.__getattribute__(self, route_name)
            if isinstance(options, RouteOptions):
                return options.enabled
            # 處理遺留的布爾值
            return bool(options)
        except AttributeError:
            # 對於未知的路由名稱，預設為啟用
            return True

    @classmethod
    def all_enabled(cls) -> "RouteConfig":
        """Create config with all routes enabled"""
        return cls(
            create=True, get=True, update=True, delete=True, list=True, count=True
        )

    @classmethod
    def all_disabled(cls) -> "RouteConfig":
        """Create config with all routes disabled"""
        return cls(
            create=False, get=False, update=False, delete=False, list=False, count=False
        )

    @classmethod
    def only_read(cls) -> "RouteConfig":
        """Create config with only read operations enabled"""
        return cls(create=False, update=False, delete=False)

    @classmethod
    def read_only(cls) -> "RouteConfig":
        """Create config with only read operations enabled"""
        return cls(
            create=False, update=False, delete=False, get=True, list=True, count=True
        )

    @classmethod
    def write_only(cls) -> "RouteConfig":
        """Create config with only write operations enabled"""
        return cls(
            create=True, update=True, delete=True, get=False, list=False, count=False
        )

    @classmethod
    def basic_crud(cls) -> "RouteConfig":
        """Create config with basic CRUD operations only (no count)"""
        return cls(count=False)

    @classmethod
    def no_list(cls) -> "RouteConfig":
        """Create config without list operation"""
        return cls(list=False)

    @classmethod
    def no_count(cls) -> "RouteConfig":
        """Create config without count operation"""
        return cls(count=False)

    @classmethod
    def with_background_tasks(
        cls,
        create_bg_func: Optional[Callable] = None,
        update_bg_func: Optional[Callable] = None,
        delete_bg_func: Optional[Callable] = None,
        **kwargs,
    ) -> "RouteConfig":
        """Create config with background tasks for specified operations"""
        # 先創建配置實例，這會觸發 __post_init__ 轉換
        config = cls(**kwargs)

        # 然後設置背景任務
        if create_bg_func:
            setattr(config, "create", RouteOptions.background_route(create_bg_func))
        if update_bg_func:
            setattr(config, "update", RouteOptions.background_route(update_bg_func))
        if delete_bg_func:
            setattr(config, "delete", RouteOptions.background_route(delete_bg_func))

        return config

    def to_dict(self) -> Dict[str, Union[bool, Dict[str, Any]]]:
        """Convert to dictionary - with backward compatibility option"""
        result = {}
        for field_name in ["create", "get", "update", "delete", "list", "count"]:
            options = object.__getattribute__(self, field_name)  # 直接取得 RouteOptions
            if isinstance(options, RouteOptions):
                # 如果沒有使用進階功能，則返回簡單的 bool
                if (
                    options.background_task == BackgroundTaskMode.DISABLED
                    and options.custom_status_code is None
                    and options.custom_dependencies is None
                ):
                    result[field_name] = options.enabled
                else:
                    # 有進階功能時返回詳細資訊
                    result[field_name] = {
                        "enabled": options.enabled,
                        "background_task": options.background_task.value,
                        "has_background_func": options.background_task_func is not None,
                        "custom_status_code": options.custom_status_code,
                    }
            else:
                result[field_name] = options
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Union[bool, Dict[str, Any]]]) -> "RouteConfig":
        """Create from dictionary (supports both bool and dict values)"""
        kwargs = {}
        for field_name, value in data.items():
            if isinstance(value, bool):
                kwargs[field_name] = value  # 會在 __post_init__ 中轉換
            elif isinstance(value, dict):
                options = RouteOptions(
                    enabled=value.get("enabled", True),
                    background_task=BackgroundTaskMode(
                        value.get("background_task", "disabled")
                    ),
                    custom_status_code=value.get("custom_status_code"),
                )
                kwargs[field_name] = options
            else:
                kwargs[field_name] = value
        return cls(**kwargs)

    def __str__(self) -> str:
        """String representation"""
        enabled_routes = []
        bg_routes = []

        for field_name in ["create", "get", "update", "delete", "list", "count"]:
            # 使用 get_route_options 獲取統一的 RouteOptions 對象
            options = self.get_route_options(field_name)
            if options.enabled:
                enabled_routes.append(field_name)
                if options.background_task != BackgroundTaskMode.DISABLED:
                    bg_routes.append(f"{field_name}(bg)")

        result = f"RouteConfig(enabled: {enabled_routes}"
        if bg_routes:
            result += f", background: {bg_routes}"
        result += ")"
        return result
