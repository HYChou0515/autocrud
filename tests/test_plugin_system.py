"""
測試 Plugin System 功能
"""

from dataclasses import dataclass
from typing import Optional

from autocrud import (
    AutoCRUD,
    SingleModelCRUD,
    MemoryStorage,
    plugin_manager,
    BaseRoutePlugin,
    PluginRouteConfig,
    RouteMethod,
    RouteOptions,
)
from fastapi import BackgroundTasks


@dataclass
class User:
    id: str
    name: str
    email: str
    age: Optional[int] = None


class CustomPingPlugin(BaseRoutePlugin):
    """自定義 ping 路由 plugin 範例"""

    def __init__(self):
        super().__init__("ping", "1.0.0")

    def get_routes(self, crud):
        """生成 ping 路由"""

        async def ping_handler(crud, background_tasks: BackgroundTasks):
            """Ping 端點"""
            return {
                "message": "pong",
                "resource": crud.resource_name,
                "model": crud.model.__name__,
                "storage_type": type(crud.storage).__name__,
            }

        return [
            PluginRouteConfig(
                name="ping",
                path=f"/{crud.resource_name}/ping",
                method=RouteMethod.GET,
                handler=ping_handler,
                options=RouteOptions.enabled_route(),
                summary=f"Ping {crud.model.__name__} service",
                description=f"健康檢查端點，用於檢查 {crud.model.__name__} 服務狀態",
                priority=1,  # 高優先級
            )
        ]


def test_plugin_system_basic():
    """測試基本的 plugin system 功能"""
    print("=== 測試 Plugin System 基本功能 ===")

    # 創建 CRUD
    crud = SingleModelCRUD(model=User, storage=MemoryStorage(), resource_name="users")

    # 檢查預設 plugins 是否已註冊
    default_plugins = plugin_manager.get_default_plugins()
    default_plugin_names = {p.name for p in default_plugins}

    print(f"預設 plugins: {default_plugin_names}")
    assert "create" in default_plugin_names
    assert "get" in default_plugin_names
    assert "update" in default_plugin_names
    assert "delete" in default_plugin_names
    assert "list" in default_plugin_names
    assert "count" in default_plugin_names

    # 測試獲取路由
    routes = plugin_manager.get_routes_for_crud(crud)
    route_names = {r.name for r in routes}

    print(f"可用路由: {route_names}")
    assert "create" in route_names
    assert "get" in route_names
    assert "update" in route_names
    assert "delete" in route_names
    assert "list" in route_names
    assert "count" in route_names

    print("✅ 基本 plugin system 測試通過")


def test_custom_plugin():
    """測試自定義 plugin"""
    print("\n=== 測試自定義 Plugin ===")

    # 註冊自定義 plugin
    custom_plugin = CustomPingPlugin()
    plugin_manager.register_plugin(custom_plugin)

    # 創建 CRUD
    crud = SingleModelCRUD(model=User, storage=MemoryStorage(), resource_name="users")

    # 獲取路由，應該包含自定義的 ping 路由
    routes = plugin_manager.get_routes_for_crud(crud)
    route_names = {r.name for r in routes}

    print(f"包含自定義 plugin 的路由: {route_names}")
    assert "ping" in route_names

    # 檢查 ping 路由的配置
    ping_route = next(r for r in routes if r.name == "ping")
    assert ping_route.path == "/users/ping"
    assert ping_route.method == RouteMethod.GET
    assert ping_route.priority == 1

    print("✅ 自定義 plugin 測試通過")

    # 清理
    plugin_manager.unregister_plugin("ping")


def test_fastapi_generator_with_plugins():
    """測試 FastAPIGenerator 與 plugin system 的整合"""
    print("\n=== 測試 FastAPIGenerator 與 Plugin System 整合 ===")

    # 註冊自定義 plugin
    custom_plugin = CustomPingPlugin()
    plugin_manager.register_plugin(custom_plugin)

    try:
        # 創建 CRUD
        crud = SingleModelCRUD(
            model=User, storage=MemoryStorage(), resource_name="users"
        )

        # 創建 router
        router = crud.create_router()

        # 檢查路由是否已創建
        routes = []
        for route in router.routes:
            if hasattr(route, "path") and hasattr(route, "methods"):
                routes.append((route.path, list(route.methods)))

        print(f"生成的路由: {routes}")

        # 檢查是否包含預期的路由
        route_paths = [path for path, methods in routes]

        # 預設路由
        assert "/users" in route_paths  # CREATE (POST) 和 LIST (GET)
        assert "/users/{resource_id}" in route_paths  # GET, PUT, DELETE
        assert "/users/count" in route_paths  # COUNT

        # 自定義路由
        assert "/users/ping" in route_paths  # PING

        print("✅ FastAPIGenerator 與 plugin system 整合測試通過")

    finally:
        # 清理
        plugin_manager.unregister_plugin("ping")


def test_autocrud_with_plugins():
    """測試 AutoCRUD 與 plugin system"""
    print("\n=== 測試 AutoCRUD 與 Plugin System ===")

    # 註冊自定義 plugin
    custom_plugin = CustomPingPlugin()
    plugin_manager.register_plugin(custom_plugin)

    try:
        # 創建 AutoCRUD
        autocrud = AutoCRUD()
        autocrud.register_model(User)

        # 直接創建 FastAPI router
        router = autocrud.create_router()

        # 檢查路由
        routes = []
        for route in router.routes:
            if hasattr(route, "path") and hasattr(route, "methods"):
                routes.append((route.path, list(route.methods)))

        print(f"AutoCRUD 生成的路由: {routes}")

        route_paths = [path for path, methods in routes]
        assert "/users/ping" in route_paths  # 自定義 ping 路由

        print("✅ AutoCRUD 與 plugin system 測試通過")

    finally:
        # 清理
        plugin_manager.unregister_plugin("ping")


if __name__ == "__main__":
    test_plugin_system_basic()
    test_custom_plugin()
    test_fastapi_generator_with_plugins()
    test_autocrud_with_plugins()
    print("\n🎉 所有 Plugin System 測試通過！")
