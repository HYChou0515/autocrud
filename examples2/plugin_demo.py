"""
AutoCRUD Plugin System 使用範例
展示如何創建和使用自定義 route plugins
"""

import asyncio
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime

from autocrud import (
    AutoCRUD,
    plugin_manager,
    BaseRoutePlugin,
    PluginRouteConfig,
    RouteMethod,
    RouteOptions,
)
from fastapi import BackgroundTasks, HTTPException, status


@dataclass
class User:
    id: str
    name: str
    email: str
    age: Optional[int] = None
    created_time: Optional[str] = None
    updated_time: Optional[str] = None


class HealthCheckPlugin(BaseRoutePlugin):
    """健康檢查 plugin"""

    def __init__(self):
        super().__init__("health", "1.0.0")

    def get_routes(self, crud):
        """生成健康檢查路由"""

        async def health_handler(crud, background_tasks: BackgroundTasks):
            """健康檢查端點"""
            try:
                # 嘗試執行一個簡單的存儲操作來檢查系統狀態
                count = crud.count()

                return {
                    "status": "healthy",
                    "service": f"{crud.model.__name__} CRUD Service",
                    "resource": crud.resource_name,
                    "total_items": count,
                    "timestamp": datetime.now().isoformat(),
                    "storage_type": type(crud.storage).__name__,
                }
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Service unhealthy: {str(e)}",
                )

        return [
            PluginRouteConfig(
                name="health",
                path=f"/{crud.resource_name}/health",
                method=RouteMethod.GET,
                handler=health_handler,
                options=RouteOptions.enabled_route(),
                summary=f"{crud.model.__name__} 健康檢查",
                description=f"檢查 {crud.model.__name__} 服務的健康狀態",
                priority=1,
            )
        ]


class StatisticsPlugin(BaseRoutePlugin):
    """統計信息 plugin"""

    def __init__(self):
        super().__init__("statistics", "1.0.0")

    def get_routes(self, crud):
        """生成統計路由"""

        async def stats_handler(crud, background_tasks: BackgroundTasks):
            """統計端點"""
            all_items = crud.list_all()

            stats = {
                "total_count": len(all_items),
                "resource_type": crud.model.__name__,
                "resource_name": crud.resource_name,
                "storage_type": type(crud.storage).__name__,
            }

            # 如果是 User 模型，添加年齡統計
            if crud.model.__name__ == "User":
                ages = [
                    item.get("age") for item in all_items if item.get("age") is not None
                ]
                if ages:
                    stats.update(
                        {
                            "average_age": sum(ages) / len(ages),
                            "min_age": min(ages),
                            "max_age": max(ages),
                            "users_with_age": len(ages),
                        }
                    )

            return stats

        return [
            PluginRouteConfig(
                name="statistics",
                path=f"/{crud.resource_name}/statistics",
                method=RouteMethod.GET,
                handler=stats_handler,
                options=RouteOptions.enabled_route(),
                summary=f"{crud.model.__name__} 統計信息",
                description=f"獲取 {crud.model.__name__} 資源的統計信息",
                priority=2,
            )
        ]


class BulkOperationsPlugin(BaseRoutePlugin):
    """批量操作 plugin"""

    def __init__(self):
        super().__init__("bulk", "1.0.0")

    def get_routes(self, crud):
        """生成批量操作路由"""

        async def bulk_create_handler(
            crud, items: List[dict], background_tasks: BackgroundTasks
        ):
            """批量創建端點"""
            try:
                created_items = []
                for item_data in items:
                    item_id = crud.create(item_data)
                    created_item = crud.get(item_id)
                    created_items.append(created_item)

                return {"created_count": len(created_items), "items": created_items}
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"批量創建失敗: {str(e)}",
                )

        async def bulk_delete_handler(
            crud, ids: List[str], background_tasks: BackgroundTasks
        ):
            """批量刪除端點"""
            try:
                deleted_count = 0
                failed_ids = []

                for item_id in ids:
                    if crud.delete(item_id):
                        deleted_count += 1
                    else:
                        failed_ids.append(item_id)

                return {
                    "deleted_count": deleted_count,
                    "failed_ids": failed_ids,
                    "total_requested": len(ids),
                }
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"批量刪除失敗: {str(e)}",
                )

        return [
            PluginRouteConfig(
                name="bulk_create",
                path=f"/{crud.resource_name}/bulk",
                method=RouteMethod.POST,
                handler=bulk_create_handler,
                options=RouteOptions.enabled_route(),
                summary=f"批量創建 {crud.model.__name__}",
                description=f"一次創建多個 {crud.model.__name__} 資源",
                priority=10,
            ),
            PluginRouteConfig(
                name="bulk_delete",
                path=f"/{crud.resource_name}/bulk",
                method=RouteMethod.DELETE,
                handler=bulk_delete_handler,
                options=RouteOptions.enabled_route(),
                summary=f"批量刪除 {crud.model.__name__}",
                description=f"根據 ID 列表批量刪除 {crud.model.__name__} 資源",
                priority=11,
            ),
        ]


async def demo_plugin_system():
    """演示 plugin system 的使用"""
    print("🚀 AutoCRUD Plugin System 演示")
    print("=" * 50)

    # 註冊自定義 plugins
    print("1. 註冊自定義 plugins...")
    plugin_manager.register_plugin(HealthCheckPlugin())
    plugin_manager.register_plugin(StatisticsPlugin())
    plugin_manager.register_plugin(BulkOperationsPlugin())

    # 創建 AutoCRUD 實例
    print("2. 創建 AutoCRUD 實例...")
    autocrud = AutoCRUD()
    autocrud.register_model(User)

    # 檢查可用的 plugins
    all_plugins = plugin_manager.get_all_plugins()
    print(f"3. 可用的 plugins: {[p.name for p in all_plugins]}")

    # 獲取所有路由
    crud = autocrud.get_crud("users")
    routes = plugin_manager.get_routes_for_crud(crud)
    print("4. 可用的路由:")
    for route in routes:
        print(f"   - {route.method.value} {route.path} ({route.name})")

    # 創建一些測試數據
    print("5. 創建測試數據...")
    test_users = [
        {"name": "Alice", "email": "alice@example.com", "age": 25},
        {"name": "Bob", "email": "bob@example.com", "age": 30},
        {"name": "Charlie", "email": "charlie@example.com", "age": 35},
    ]

    for user_data in test_users:
        autocrud.create("users", user_data)

    print(f"   創建了 {len(test_users)} 個用戶")

    # 創建 FastAPI 應用來測試 plugins
    print("6. 創建 FastAPI 應用...")
    from fastapi.testclient import TestClient

    app = autocrud.create_fastapi_app(
        title="Plugin Demo API", description="展示 AutoCRUD Plugin System 的 API"
    )

    client = TestClient(app)

    # 測試標準 CRUD 操作
    print("7. 測試標準 CRUD 操作...")

    # 列出所有用戶
    response = client.get("/api/v1/users")
    users = response.json()
    print(f"   GET /api/v1/users: {len(users)} 個用戶")

    # 測試自定義 plugin 路由
    print("8. 測試自定義 plugin 路由...")

    # 健康檢查
    response = client.get("/api/v1/users/health")
    if response.status_code == 200:
        health_data = response.json()
        print(f"   GET /api/v1/users/health: {health_data['status']}")
        print(f"     - 總項目數: {health_data['total_items']}")

    # 統計信息
    response = client.get("/api/v1/users/statistics")
    if response.status_code == 200:
        stats_data = response.json()
        print("   GET /api/v1/users/statistics:")
        print(f"     - 總數: {stats_data['total_count']}")
        if "average_age" in stats_data:
            print(f"     - 平均年齡: {stats_data['average_age']:.1f}")

    # 批量操作測試
    print("9. 測試批量操作...")
    bulk_data = [
        {"name": "David", "email": "david@example.com", "age": 28},
        {"name": "Eve", "email": "eve@example.com", "age": 32},
    ]

    response = client.post("/api/v1/users/bulk", json=bulk_data)
    if response.status_code == 200:
        bulk_result = response.json()
        print(
            f"   POST /api/v1/users/bulk: 創建了 {bulk_result['created_count']} 個用戶"
        )

    # 最終統計
    response = client.get("/api/v1/users/statistics")
    if response.status_code == 200:
        final_stats = response.json()
        print(f"10. 最終統計: 總共 {final_stats['total_count']} 個用戶")

    print("\n✅ Plugin System 演示完成！")
    print("🎯 所有自定義 plugins 都正常工作")


if __name__ == "__main__":
    asyncio.run(demo_plugin_system())
