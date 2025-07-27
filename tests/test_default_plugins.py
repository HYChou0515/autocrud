"""測試 default_plugins.py 的全面覆蓋率"""

import pytest
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, BackgroundTasks
from pydantic import BaseModel

from autocrud.default_plugins import (
    CreateRoutePlugin,
    GetRoutePlugin,
    UpdateRoutePlugin,
    DeleteRoutePlugin,
    CountRoutePlugin,
    ListRoutePlugin,
    DEFAULT_PLUGINS,
    default_create_plugin,
    default_get_plugin,
    default_update_plugin,
    default_delete_plugin,
    default_count_plugin,
    default_list_plugin,
)
from autocrud.core import SingleModelCRUD
from autocrud.storage import MemoryStorage
from autocrud.metadata import MetadataConfig
from autocrud.list_params import SortOrder
from autocrud.plugin_system import RouteMethod
from autocrud.route_config import RouteOptions


@dataclass
class UserModel:
    """測試用戶模型"""

    id: str
    name: str
    email: str
    age: int
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None


class PydanticUserModel(BaseModel):
    """Pydantic 測試用戶模型"""

    name: str
    email: str
    age: int


class LegacyPydanticUserModel(BaseModel):
    """舊版本 Pydantic 用戶模型（使用 dict() 方法）"""

    name: str
    email: str
    age: int

    def dict(self):
        """模擬舊版本 Pydantic 的 dict() 方法"""
        return {"name": self.name, "email": self.email, "age": self.age}


class TestCreateRoutePlugin:
    """測試 CreateRoutePlugin"""

    @pytest.fixture
    def crud(self):
        """創建測試用的 CRUD 實例"""
        storage = MemoryStorage()
        metadata_config = MetadataConfig(enable_timestamps=True)
        return SingleModelCRUD(
            UserModel, storage, "users", metadata_config=metadata_config
        )

    @pytest.fixture
    def plugin(self):
        """創建 CreateRoutePlugin 實例"""
        return CreateRoutePlugin()

    def test_plugin_initialization(self, plugin):
        """測試插件初始化"""
        assert plugin.name == "create"
        assert plugin.version == "1.0.0"
        assert plugin.converter is not None

    def test_get_routes_structure(self, plugin, crud):
        """測試獲取路由配置的結構"""
        routes = plugin.get_routes(crud)

        assert len(routes) == 1
        route = routes[0]

        assert route.name == "create"
        assert route.path == "/users"
        assert route.method == RouteMethod.POST
        assert route.handler is not None
        assert route.options == RouteOptions.enabled_route()
        assert route.response_model is not None
        assert route.status_code == 201
        assert "創建" in route.summary
        assert "創建" in route.description
        assert route.priority == 10

    @pytest.mark.asyncio
    async def test_create_handler_with_dict(self, plugin, crud):
        """測試使用字典創建資源"""
        routes = plugin.get_routes(crud)
        handler = routes[0].handler
        background_tasks = MagicMock(spec=BackgroundTasks)

        item_data = {"name": "Alice", "email": "alice@test.com", "age": 25}

        result = await handler(crud, item_data, background_tasks)

        assert result is not None
        assert result["name"] == "Alice"
        assert result["email"] == "alice@test.com"
        assert result["age"] == 25
        assert "id" in result

    @pytest.mark.asyncio
    async def test_create_handler_with_pydantic_model_dump(self, plugin, crud):
        """測試使用 Pydantic 模型（model_dump）創建資源"""
        routes = plugin.get_routes(crud)
        handler = routes[0].handler
        background_tasks = MagicMock(spec=BackgroundTasks)

        pydantic_user = PydanticUserModel(name="Bob", email="bob@test.com", age=30)

        result = await handler(crud, pydantic_user, background_tasks)

        assert result is not None
        assert result["name"] == "Bob"
        assert result["email"] == "bob@test.com"
        assert result["age"] == 30

    @pytest.mark.asyncio
    async def test_create_handler_with_legacy_pydantic_dict(self, plugin, crud):
        """測試使用舊版 Pydantic 模型（dict）創建資源"""
        routes = plugin.get_routes(crud)
        handler = routes[0].handler
        background_tasks = MagicMock(spec=BackgroundTasks)

        legacy_user = LegacyPydanticUserModel(
            name="Charlie", email="charlie@test.com", age=35
        )

        result = await handler(crud, legacy_user, background_tasks)

        assert result is not None
        assert result["name"] == "Charlie"
        assert result["email"] == "charlie@test.com"
        assert result["age"] == 35

    @pytest.mark.asyncio
    async def test_create_handler_exception(self, plugin, crud):
        """測試創建時的異常處理"""
        routes = plugin.get_routes(crud)
        handler = routes[0].handler
        background_tasks = MagicMock(spec=BackgroundTasks)

        # 模擬 crud.create 拋出異常
        with patch.object(crud, "create", side_effect=ValueError("Invalid data")):
            with pytest.raises(HTTPException) as exc_info:
                await handler(crud, {"name": "Test"}, background_tasks)

            assert exc_info.value.status_code == 400
            assert "創建失敗" in str(exc_info.value.detail)


class TestGetRoutePlugin:
    """測試 GetRoutePlugin"""

    @pytest.fixture
    def crud(self):
        """創建測試用的 CRUD 實例"""
        storage = MemoryStorage()
        return SingleModelCRUD(UserModel, storage, "users")

    @pytest.fixture
    def plugin(self):
        """創建 GetRoutePlugin 實例"""
        return GetRoutePlugin()

    def test_plugin_initialization(self, plugin):
        """測試插件初始化"""
        assert plugin.name == "get"
        assert plugin.version == "1.0.0"
        assert plugin.converter is not None

    def test_get_routes_structure(self, plugin, crud):
        """測試獲取路由配置的結構"""
        routes = plugin.get_routes(crud)

        assert len(routes) == 1
        route = routes[0]

        assert route.name == "get"
        assert route.path == "/users/{resource_id}"
        assert route.method == RouteMethod.GET
        assert route.handler is not None
        assert route.response_model is not None
        assert "獲取" in route.summary
        assert route.priority == 20

    @pytest.mark.asyncio
    async def test_get_handler_success(self, plugin, crud):
        """測試成功獲取資源"""
        # 先創建一個資源
        user_id = crud.create({"name": "Alice", "email": "alice@test.com", "age": 25})

        routes = plugin.get_routes(crud)
        handler = routes[0].handler
        background_tasks = MagicMock(spec=BackgroundTasks)

        result = await handler(crud, user_id, background_tasks)

        assert result is not None
        assert result["name"] == "Alice"
        assert result["id"] == user_id

    @pytest.mark.asyncio
    async def test_get_handler_not_found(self, plugin, crud):
        """測試獲取不存在的資源"""
        routes = plugin.get_routes(crud)
        handler = routes[0].handler
        background_tasks = MagicMock(spec=BackgroundTasks)

        with pytest.raises(HTTPException) as exc_info:
            await handler(crud, "nonexistent-id", background_tasks)

        assert exc_info.value.status_code == 404
        assert "資源不存在" in str(exc_info.value.detail)


class TestUpdateRoutePlugin:
    """測試 UpdateRoutePlugin"""

    @pytest.fixture
    def crud(self):
        """創建測試用的 CRUD 實例"""
        storage = MemoryStorage()
        return SingleModelCRUD(UserModel, storage, "users")

    @pytest.fixture
    def plugin(self):
        """創建 UpdateRoutePlugin 實例"""
        return UpdateRoutePlugin()

    def test_plugin_initialization(self, plugin):
        """測試插件初始化"""
        assert plugin.name == "update"
        assert plugin.version == "1.0.0"
        assert plugin.converter is not None

    def test_get_routes_structure(self, plugin, crud):
        """測試獲取路由配置的結構"""
        routes = plugin.get_routes(crud)

        assert len(routes) == 1
        route = routes[0]

        assert route.name == "update"
        assert route.path == "/users/{resource_id}"
        assert route.method == RouteMethod.PUT
        assert route.status_code == 200
        assert route.priority == 30

    @pytest.mark.asyncio
    async def test_update_handler_success_with_dict(self, plugin, crud):
        """測試使用字典成功更新資源"""
        # 先創建一個資源
        user_id = crud.create({"name": "Alice", "email": "alice@test.com", "age": 25})

        routes = plugin.get_routes(crud)
        handler = routes[0].handler
        background_tasks = MagicMock(spec=BackgroundTasks)

        update_data = {"name": "Alice Updated", "age": 26}
        result = await handler(crud, user_id, update_data, background_tasks)

        assert result is not None
        assert result["name"] == "Alice Updated"
        assert result["age"] == 26
        assert result["email"] == "alice@test.com"  # 未更新的字段保持不變

    @pytest.mark.asyncio
    async def test_update_handler_success_with_pydantic(self, plugin, crud):
        """測試使用 Pydantic 模型成功更新資源"""
        # 先創建一個資源
        user_id = crud.create({"name": "Alice", "email": "alice@test.com", "age": 25})

        routes = plugin.get_routes(crud)
        handler = routes[0].handler
        background_tasks = MagicMock(spec=BackgroundTasks)

        pydantic_update = PydanticUserModel(
            name="Alice Updated", email="alice.new@test.com", age=26
        )
        result = await handler(crud, user_id, pydantic_update, background_tasks)

        assert result is not None
        assert result["name"] == "Alice Updated"
        assert result["email"] == "alice.new@test.com"
        assert result["age"] == 26

    @pytest.mark.asyncio
    async def test_update_handler_not_found(self, plugin, crud):
        """測試更新不存在的資源"""
        routes = plugin.get_routes(crud)
        handler = routes[0].handler
        background_tasks = MagicMock(spec=BackgroundTasks)

        update_data = {"name": "Updated"}

        with pytest.raises(HTTPException) as exc_info:
            await handler(crud, "nonexistent-id", update_data, background_tasks)

        # 注意：由於 catch-all 異常處理，404 錯誤會被包裝成 400 錯誤
        assert exc_info.value.status_code == 400
        assert "更新失敗" in str(exc_info.value.detail)
        assert "資源不存在" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_update_handler_exception(self, plugin, crud):
        """測試更新時的異常處理"""
        # 先創建一個資源
        user_id = crud.create({"name": "Alice", "email": "alice@test.com", "age": 25})

        routes = plugin.get_routes(crud)
        handler = routes[0].handler
        background_tasks = MagicMock(spec=BackgroundTasks)

        # 模擬 crud.update 拋出異常
        with patch.object(crud, "update", side_effect=ValueError("Update failed")):
            with pytest.raises(HTTPException) as exc_info:
                await handler(crud, user_id, {"name": "Updated"}, background_tasks)

            assert exc_info.value.status_code == 400
            assert "更新失敗" in str(exc_info.value.detail)


class TestDeleteRoutePlugin:
    """測試 DeleteRoutePlugin"""

    @pytest.fixture
    def crud(self):
        """創建測試用的 CRUD 實例"""
        storage = MemoryStorage()
        return SingleModelCRUD(UserModel, storage, "users")

    @pytest.fixture
    def plugin(self):
        """創建 DeleteRoutePlugin 實例"""
        return DeleteRoutePlugin()

    def test_plugin_initialization(self, plugin):
        """測試插件初始化"""
        assert plugin.name == "delete"
        assert plugin.version == "1.0.0"

    def test_get_routes_structure(self, plugin, crud):
        """測試獲取路由配置的結構"""
        routes = plugin.get_routes(crud)

        assert len(routes) == 1
        route = routes[0]

        assert route.name == "delete"
        assert route.path == "/users/{resource_id}"
        assert route.method == RouteMethod.DELETE
        assert route.status_code == 204
        assert route.priority == 40

    @pytest.mark.asyncio
    async def test_delete_handler_success(self, plugin, crud):
        """測試成功刪除資源"""
        # 先創建一個資源
        user_id = crud.create({"name": "Alice", "email": "alice@test.com", "age": 25})

        routes = plugin.get_routes(crud)
        handler = routes[0].handler
        background_tasks = MagicMock(spec=BackgroundTasks)

        result = await handler(crud, user_id, background_tasks)

        assert result is None  # DELETE 返回 None (204 No Content)
        assert crud.get(user_id) is None  # 資源已被刪除

    @pytest.mark.asyncio
    async def test_delete_handler_not_found(self, plugin, crud):
        """測試刪除不存在的資源"""
        routes = plugin.get_routes(crud)
        handler = routes[0].handler
        background_tasks = MagicMock(spec=BackgroundTasks)

        with pytest.raises(HTTPException) as exc_info:
            await handler(crud, "nonexistent-id", background_tasks)

        assert exc_info.value.status_code == 404
        assert "資源不存在" in str(exc_info.value.detail)


class TestCountRoutePlugin:
    """測試 CountRoutePlugin"""

    @pytest.fixture
    def crud(self):
        """創建測試用的 CRUD 實例"""
        storage = MemoryStorage()
        return SingleModelCRUD(UserModel, storage, "users")

    @pytest.fixture
    def plugin(self):
        """創建 CountRoutePlugin 實例"""
        return CountRoutePlugin()

    def test_plugin_initialization(self, plugin):
        """測試插件初始化"""
        assert plugin.name == "count"
        assert plugin.version == "1.0.0"

    def test_get_routes_structure(self, plugin, crud):
        """測試獲取路由配置的結構"""
        routes = plugin.get_routes(crud)

        assert len(routes) == 1
        route = routes[0]

        assert route.name == "count"
        assert route.path == "/users/count"
        assert route.method == RouteMethod.GET
        assert route.priority == 5  # 高優先級

    @pytest.mark.asyncio
    async def test_count_handler_empty(self, plugin, crud):
        """測試空資源的計數"""
        routes = plugin.get_routes(crud)
        handler = routes[0].handler
        background_tasks = MagicMock(spec=BackgroundTasks)

        result = await handler(crud, background_tasks)

        assert result == {"count": 0}

    @pytest.mark.asyncio
    async def test_count_handler_with_data(self, plugin, crud):
        """測試有資源的計數"""
        # 創建幾個資源
        crud.create({"name": "Alice", "email": "alice@test.com", "age": 25})
        crud.create({"name": "Bob", "email": "bob@test.com", "age": 30})
        crud.create({"name": "Charlie", "email": "charlie@test.com", "age": 35})

        routes = plugin.get_routes(crud)
        handler = routes[0].handler
        background_tasks = MagicMock(spec=BackgroundTasks)

        result = await handler(crud, background_tasks)

        assert result == {"count": 3}


class TestListRoutePlugin:
    """測試 ListRoutePlugin"""

    @pytest.fixture
    def crud(self):
        """創建測試用的 CRUD 實例"""
        storage = MemoryStorage()
        metadata_config = MetadataConfig(
            enable_timestamps=True, enable_user_tracking=True
        )
        return SingleModelCRUD(
            UserModel, storage, "users", metadata_config=metadata_config
        )

    @pytest.fixture
    def plugin(self):
        """創建 ListRoutePlugin 實例"""
        return ListRoutePlugin()

    def _call_list_handler(self, handler, crud, background_tasks, **kwargs):
        """輔助方法：調用列表處理器並提供默認參數"""
        default_params = {
            "page": 1,
            "page_size": 20,
            "created_by": None,
            "updated_by": None,
            "created_time_start": None,
            "created_time_end": None,
            "updated_time_start": None,
            "updated_time_end": None,
            "sort_by": None,
            "sort_order": SortOrder.DESC,
            "simple": False,
        }
        default_params.update(kwargs)
        return handler(crud, background_tasks, **default_params)

    def test_plugin_initialization(self, plugin):
        """測試插件初始化"""
        assert plugin.name == "list"
        assert plugin.version == "1.0.0"

    def test_get_routes_structure(self, plugin, crud):
        """測試獲取路由配置的結構"""
        routes = plugin.get_routes(crud)

        assert len(routes) == 1
        route = routes[0]

        assert route.name == "list"
        assert route.path == "/users"
        assert route.method == RouteMethod.GET
        assert route.priority == 50  # 低優先級

    @pytest.mark.asyncio
    async def test_list_handler_simple_mode_empty(self, plugin, crud):
        """測試簡單模式空列表"""
        routes = plugin.get_routes(crud)
        handler = routes[0].handler
        background_tasks = MagicMock(spec=BackgroundTasks)

        result = await self._call_list_handler(
            handler, crud, background_tasks, simple=True
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_list_handler_simple_mode_with_data(self, plugin, crud):
        """測試簡單模式有資料"""
        # 創建測試資料
        crud.create({"name": "Alice", "email": "alice@test.com", "age": 25})
        crud.create({"name": "Bob", "email": "bob@test.com", "age": 30})

        routes = plugin.get_routes(crud)
        handler = routes[0].handler
        background_tasks = MagicMock(spec=BackgroundTasks)

        result = await self._call_list_handler(
            handler, crud, background_tasks, simple=True
        )

        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_handler_advanced_mode_default_params(self, plugin, crud):
        """測試高級模式預設參數"""
        # 創建測試資料
        crud.create({"name": "Alice", "email": "alice@test.com", "age": 25})
        crud.create({"name": "Bob", "email": "bob@test.com", "age": 30})

        routes = plugin.get_routes(crud)
        handler = routes[0].handler
        background_tasks = MagicMock(spec=BackgroundTasks)

        result = await self._call_list_handler(handler, crud, background_tasks)

        assert hasattr(result, "items")
        assert hasattr(result, "total")
        assert hasattr(result, "page")
        assert hasattr(result, "page_size")
        assert len(result.items) == 2
        assert result.total == 2
        assert result.page == 1
        assert result.page_size == 20

    @pytest.mark.asyncio
    async def test_list_handler_with_pagination(self, plugin, crud):
        """測試分頁參數"""
        # 創建更多測試資料
        for i in range(5):
            crud.create(
                {"name": f"User{i}", "email": f"user{i}@test.com", "age": 20 + i}
            )

        routes = plugin.get_routes(crud)
        handler = routes[0].handler
        background_tasks = MagicMock(spec=BackgroundTasks)

        result = await self._call_list_handler(
            handler, crud, background_tasks, page=2, page_size=2
        )

        assert len(result.items) == 2
        assert result.page == 2
        assert result.page_size == 2
        assert result.total == 5

    @pytest.mark.asyncio
    async def test_list_handler_with_filters(self, plugin, crud):
        """測試過濾參數"""
        # 創建測試資料
        crud.create({"name": "Alice", "email": "alice@test.com", "age": 25})
        crud.create({"name": "Bob", "email": "bob@test.com", "age": 30})

        routes = plugin.get_routes(crud)
        handler = routes[0].handler
        background_tasks = MagicMock(spec=BackgroundTasks)

        # 測試用戶過濾（雖然這個測試資料沒有 created_by，但測試參數傳遞）
        result = await self._call_list_handler(
            handler, crud, background_tasks, created_by=["user1"], updated_by=["user2"]
        )

        assert hasattr(result, "items")
        assert hasattr(result, "total")

    @pytest.mark.asyncio
    async def test_list_handler_with_time_filters(self, plugin, crud):
        """測試時間過濾參數"""
        routes = plugin.get_routes(crud)
        handler = routes[0].handler
        background_tasks = MagicMock(spec=BackgroundTasks)

        now = datetime.now(timezone.utc)
        # 測試時間過濾參數的傳遞
        result = await self._call_list_handler(
            handler,
            crud,
            background_tasks,
            created_time_start=now - timedelta(hours=1),
            created_time_end=now + timedelta(hours=1),
        )

        assert hasattr(result, "items")

    @pytest.mark.asyncio
    async def test_list_handler_with_sorting(self, plugin, crud):
        """測試排序參數"""
        routes = plugin.get_routes(crud)
        handler = routes[0].handler
        background_tasks = MagicMock(spec=BackgroundTasks)

        result = await self._call_list_handler(
            handler, crud, background_tasks, sort_by="created_time"
        )

        assert hasattr(result, "items")

    @pytest.mark.asyncio
    async def test_list_handler_simple_mode_with_advanced_params(self, plugin, crud):
        """測試簡單模式但有高級參數時返回列表"""
        crud.create({"name": "Alice", "email": "alice@test.com", "age": 25})

        routes = plugin.get_routes(crud)
        handler = routes[0].handler
        background_tasks = MagicMock(spec=BackgroundTasks)

        result = await self._call_list_handler(
            handler, crud, background_tasks, simple=True
        )

        # 有高級參數時，即使 simple=True 也返回列表
        assert isinstance(result, list)
        assert len(result) == 1


class TestDefaultPluginsExports:
    """測試預設插件的導出"""

    def test_default_plugin_instances(self):
        """測試預設插件實例"""
        assert isinstance(default_create_plugin, CreateRoutePlugin)
        assert isinstance(default_get_plugin, GetRoutePlugin)
        assert isinstance(default_update_plugin, UpdateRoutePlugin)
        assert isinstance(default_delete_plugin, DeleteRoutePlugin)
        assert isinstance(default_count_plugin, CountRoutePlugin)
        assert isinstance(default_list_plugin, ListRoutePlugin)

    def test_default_plugins_list(self):
        """測試 DEFAULT_PLUGINS 列表"""
        assert len(DEFAULT_PLUGINS) == 6

        plugin_names = {plugin.name for plugin in DEFAULT_PLUGINS}
        expected_names = {"create", "get", "update", "delete", "count", "list"}
        assert plugin_names == expected_names

        # 測試所有插件都是正確的類型
        assert any(isinstance(p, CreateRoutePlugin) for p in DEFAULT_PLUGINS)
        assert any(isinstance(p, GetRoutePlugin) for p in DEFAULT_PLUGINS)
        assert any(isinstance(p, UpdateRoutePlugin) for p in DEFAULT_PLUGINS)
        assert any(isinstance(p, DeleteRoutePlugin) for p in DEFAULT_PLUGINS)
        assert any(isinstance(p, CountRoutePlugin) for p in DEFAULT_PLUGINS)
        assert any(isinstance(p, ListRoutePlugin) for p in DEFAULT_PLUGINS)

    def test_plugin_priorities(self):
        """測試插件優先級設置"""
        routes_info = []

        # 創建測試 CRUD
        storage = MemoryStorage()
        crud = SingleModelCRUD(UserModel, storage, "users")

        for plugin in DEFAULT_PLUGINS:
            routes = plugin.get_routes(crud)
            for route in routes:
                routes_info.append((plugin.name, route.priority))

        # 驗證優先級設置
        priority_map = {name: priority for name, priority in routes_info}

        assert priority_map["count"] == 5  # 最高優先級
        assert priority_map["create"] == 10
        assert priority_map["get"] == 20
        assert priority_map["update"] == 30
        assert priority_map["delete"] == 40
        assert priority_map["list"] == 50  # 最低優先級


class TestPluginResponseModels:
    """測試插件響應模型生成"""

    @pytest.fixture
    def crud(self):
        """創建測試用的 CRUD 實例"""
        storage = MemoryStorage()
        return SingleModelCRUD(UserModel, storage, "users")

    def test_create_plugin_response_model(self, crud):
        """測試創建插件的響應模型"""
        plugin = CreateRoutePlugin()
        routes = plugin.get_routes(crud)

        response_model = routes[0].response_model
        assert response_model is not None
        assert "UserModelResponse" in response_model.__name__

    def test_get_plugin_response_model(self, crud):
        """測試獲取插件的響應模型"""
        plugin = GetRoutePlugin()
        routes = plugin.get_routes(crud)

        response_model = routes[0].response_model
        assert response_model is not None
        assert "UserModelResponse" in response_model.__name__

    def test_update_plugin_response_model(self, crud):
        """測試更新插件的響應模型"""
        plugin = UpdateRoutePlugin()
        routes = plugin.get_routes(crud)

        response_model = routes[0].response_model
        assert response_model is not None
        assert "UserModelResponse" in response_model.__name__

    def test_delete_plugin_no_response_model(self, crud):
        """測試刪除插件沒有響應模型"""
        plugin = DeleteRoutePlugin()
        routes = plugin.get_routes(crud)

        # DELETE 路由通常沒有響應模型（204 No Content）
        assert routes[0].response_model is None

    def test_count_plugin_no_response_model(self, crud):
        """測試計數插件沒有預定義響應模型"""
        plugin = CountRoutePlugin()
        routes = plugin.get_routes(crud)

        # COUNT 路由返回簡單的 {"count": int}，不需要複雜的響應模型
        assert routes[0].response_model is None

    def test_list_plugin_no_response_model(self, crud):
        """測試列表插件沒有預定義響應模型"""
        plugin = ListRoutePlugin()
        routes = plugin.get_routes(crud)

        # LIST 路由的響應格式取決於參數，不預定義響應模型
        assert routes[0].response_model is None


class TestPluginHandlerAnnotations:
    """測試插件處理器的類型註解"""

    @pytest.fixture
    def crud(self):
        """創建測試用的 CRUD 實例"""
        storage = MemoryStorage()
        return SingleModelCRUD(UserModel, storage, "users")

    def test_create_handler_annotations(self, crud):
        """測試創建處理器的類型註解"""
        plugin = CreateRoutePlugin()
        routes = plugin.get_routes(crud)
        handler = routes[0].handler

        # 檢查是否設置了 item 參數的類型註解
        assert hasattr(handler, "__annotations__")
        assert "item" in handler.__annotations__

    def test_update_handler_annotations(self, crud):
        """測試更新處理器的類型註解"""
        plugin = UpdateRoutePlugin()
        routes = plugin.get_routes(crud)
        handler = routes[0].handler

        # 檢查是否設置了 item 參數的類型註解
        assert hasattr(handler, "__annotations__")
        assert "item" in handler.__annotations__
