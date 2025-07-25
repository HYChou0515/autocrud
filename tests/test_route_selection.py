"""
測試 Route Selection System
"""

from fastapi.testclient import TestClient

from autocrud import (
    SingleModelCRUD,
    AutoCRUD,
    MemoryStorage,
    FastAPIGenerator,
    RouteConfig,
)
from .test_models import User


class TestRouteConfig:
    """測試 RouteConfig 類"""

    def test_default_config(self):
        """測試預設配置"""
        config = RouteConfig()
        assert config.create is True
        assert config.get is True
        assert config.update is True
        assert config.delete is True
        assert config.list is True
        assert config.count is True

    def test_all_enabled(self):
        """測試全部啟用配置"""
        config = RouteConfig.all_enabled()
        assert all(config.to_dict().values())

    def test_all_disabled(self):
        """測試全部禁用配置"""
        config = RouteConfig.all_disabled()
        assert not any(config.to_dict().values())

    def test_read_only(self):
        """測試只讀配置"""
        config = RouteConfig.read_only()
        assert config.get is True
        assert config.list is True
        assert config.count is True
        assert config.create is False
        assert config.update is False
        assert config.delete is False

    def test_write_only(self):
        """測試只寫配置"""
        config = RouteConfig.write_only()
        assert config.create is True
        assert config.update is True
        assert config.delete is True
        assert config.get is False
        assert config.list is False
        assert config.count is False

    def test_basic_crud(self):
        """測試基本 CRUD 配置"""
        config = RouteConfig.basic_crud()
        assert config.create is True
        assert config.get is True
        assert config.update is True
        assert config.delete is True
        assert config.list is True
        assert config.count is False

    def test_custom_config(self):
        """測試自定義配置"""
        config = RouteConfig(
            create=True, get=False, update=True, delete=False, list=True, count=False
        )
        assert config.create is True
        assert config.get is False
        assert config.update is True
        assert config.delete is False
        assert config.list is True
        assert config.count is False

    def test_to_dict(self):
        """測試轉換為字典"""
        config = RouteConfig(create=True, get=False)
        config_dict = config.to_dict()
        assert config_dict["create"] is True
        assert config_dict["get"] is False

    def test_from_dict(self):
        """測試從字典創建"""
        data = {"create": False, "get": True, "update": False}
        config = RouteConfig.from_dict(data)
        assert config.create is False
        assert config.get is True
        assert config.update is False

    def test_str_representation(self):
        """測試字符串表示"""
        config = RouteConfig(
            create=True, get=True, update=False, delete=False, list=False, count=False
        )
        str_repr = str(config)
        assert "create" in str_repr
        assert "get" in str_repr
        assert "update" not in str_repr
        assert "delete" not in str_repr


class TestSingleModelCRUDRouteSelection:
    """測試 SingleModelCRUD 的路由選擇功能"""

    def setup_method(self):
        """設置測試環境"""
        self.storage = MemoryStorage()
        self.crud = SingleModelCRUD(User, self.storage, "users")

    def test_all_routes_enabled(self):
        """測試全部路由啟用"""
        config = RouteConfig.all_enabled()
        generator = FastAPIGenerator(self.crud, route_config=config)
        router = generator.create_router()

        # 檢查路由數量（應該有所有路由）
        routes = router.routes
        route_paths = [route.path for route in routes]

        assert "/users" in route_paths  # POST (create) 和 GET (list)
        assert "/users/{resource_id}" in route_paths  # GET, PUT, DELETE
        assert "/users/count" in route_paths  # count

    def test_read_only_routes(self):
        """測試只讀路由"""
        config = RouteConfig.read_only()
        generator = FastAPIGenerator(self.crud, route_config=config)
        app = generator.create_fastapi_app(route_config=config)
        client = TestClient(app)

        # 創建一些測試數據（直接通過 CRUD）
        user_data = {"name": "John", "age": 30}
        user_id = self.crud.create(user_data)

        # 應該可以讀取
        response = client.get(f"/api/v1/users/{user_id}")
        assert response.status_code == 200

        response = client.get("/api/v1/users")
        assert response.status_code == 200

        response = client.get("/api/v1/users/count")
        assert response.status_code == 200

        # 不應該能寫入
        response = client.post("/api/v1/users", json={"name": "Jane", "age": 25})
        assert response.status_code == 405  # Method Not Allowed

        response = client.put(
            f"/api/v1/users/{user_id}", json={"name": "Jane", "age": 25}
        )
        assert response.status_code == 405

        response = client.delete(f"/api/v1/users/{user_id}")
        assert response.status_code == 405

    def test_write_only_routes(self):
        """測試只寫路由"""
        config = RouteConfig.write_only()
        generator = FastAPIGenerator(self.crud, route_config=config)
        app = generator.create_fastapi_app(route_config=config)
        client = TestClient(app)

        # 應該可以創建
        response = client.post("/api/v1/users", json={"name": "John", "age": 30})
        assert response.status_code == 201
        user_data = response.json()
        user_id = user_data["id"]

        # 應該可以更新
        response = client.put(
            f"/api/v1/users/{user_id}", json={"name": "Jane", "age": 25}
        )
        assert response.status_code == 200

        # 應該可以刪除
        response = client.delete(f"/api/v1/users/{user_id}")
        assert response.status_code == 204  # No Content

        # 不應該能讀取
        response = client.get("/api/v1/users")
        assert response.status_code == 405

        response = client.get("/api/v1/users/count")
        assert response.status_code == 405

    def test_no_count_route(self):
        """測試禁用 count 路由"""
        config = RouteConfig(count=False)
        generator = FastAPIGenerator(self.crud, route_config=config)
        app = generator.create_fastapi_app(route_config=config)
        client = TestClient(app)

        # count 路由應該不存在
        response = client.get("/api/v1/users/count")
        assert response.status_code == 404

        # 其他路由應該正常
        response = client.post("/api/v1/users", json={"name": "John", "age": 30})
        assert response.status_code == 201

    def test_only_list_route(self):
        """測試只啟用 list 路由"""
        config = RouteConfig(
            create=False, get=False, update=False, delete=False, list=True, count=False
        )
        generator = FastAPIGenerator(self.crud, route_config=config)
        app = generator.create_fastapi_app(route_config=config)
        client = TestClient(app)

        # 只有 list 應該可用
        response = client.get("/api/v1/users")
        assert response.status_code == 200

        # 其他操作應該不可用
        response = client.post("/api/v1/users", json={"name": "John", "age": 30})
        assert response.status_code == 405


class TestAutoCRUDRouteSelection:
    """測試 AutoCRUD 的路由選擇功能"""

    def setup_method(self):
        """設置測試環境"""
        self.autocrud = AutoCRUD()
        self.autocrud.register_model(User, "users")

    def test_multi_model_route_config(self):
        """測試多模型路由配置"""
        config = RouteConfig.read_only()
        app = self.autocrud.create_fastapi_app(route_config=config)
        client = TestClient(app)

        # 創建測試數據（直接通過 CRUD）
        user_data = {"name": "John", "age": 30}
        user_id = self.autocrud.create("users", user_data)

        # 只讀操作應該可用
        response = client.get(f"/api/v1/users/{user_id}")
        assert response.status_code == 200

        response = client.get("/api/v1/users")
        assert response.status_code == 200

        # 寫操作應該不可用
        response = client.post("/api/v1/users", json={"name": "Jane", "age": 25})
        assert response.status_code == 405

    def test_multi_model_create_router(self):
        """測試多模型 create_router 方法"""
        config = RouteConfig.basic_crud()  # 沒有 count
        router = self.autocrud.create_router(route_config=config)

        # 檢查路由（應該沒有 count 路由）
        routes = router.routes
        route_paths = [route.path for route in routes]

        assert "/users" in route_paths
        assert "/users/{resource_id}" in route_paths
        assert "/users/count" not in route_paths


class TestRouteSelectionIntegration:
    """測試路由選擇的整合功能"""

    def setup_method(self):
        """設置測試環境"""
        self.storage = MemoryStorage()
        self.crud = SingleModelCRUD(User, self.storage, "users")

    def test_mixed_permissions_scenario(self):
        """測試混合權限場景"""
        # 創建一個允許讀取和創建，但不允許更新和刪除的配置
        config = RouteConfig(
            create=True, get=True, update=False, delete=False, list=True, count=True
        )

        generator = FastAPIGenerator(self.crud, route_config=config)
        app = generator.create_fastapi_app(route_config=config)
        client = TestClient(app)

        # 應該可以創建
        response = client.post("/api/v1/users", json={"name": "John", "age": 30})
        assert response.status_code == 201
        user_id = response.json()["id"]

        # 應該可以讀取
        response = client.get(f"/api/v1/users/{user_id}")
        assert response.status_code == 200

        response = client.get("/api/v1/users")
        assert response.status_code == 200

        response = client.get("/api/v1/users/count")
        assert response.status_code == 200

        # 不應該能更新或刪除
        response = client.put(
            f"/api/v1/users/{user_id}", json={"name": "Jane", "age": 25}
        )
        assert response.status_code == 405

        response = client.delete(f"/api/v1/users/{user_id}")
        assert response.status_code == 405

    def test_empty_api_scenario(self):
        """測試空 API 場景（所有路由都被禁用）"""
        config = RouteConfig.all_disabled()
        generator = FastAPIGenerator(self.crud, route_config=config)
        app = generator.create_fastapi_app(route_config=config)
        client = TestClient(app)

        # 健康檢查應該仍然可用
        response = client.get("/health")
        assert response.status_code == 200

        # 所有 CRUD 操作都應該不可用（404 因為路由不存在）
        response = client.post("/api/v1/users", json={"name": "John", "age": 30})
        assert response.status_code == 404

        response = client.get("/api/v1/users")
        assert response.status_code == 404

        response = client.get("/api/v1/users/count")
        assert response.status_code == 404

    def test_route_config_override(self):
        """測試路由配置覆蓋"""
        # 創建 generator 時設置一個配置
        initial_config = RouteConfig.all_enabled()
        generator = FastAPIGenerator(self.crud, route_config=initial_config)

        # 在 create_router 時覆蓋配置
        override_config = RouteConfig.read_only()
        router = generator.create_router(route_config=override_config)

        # 應該使用覆蓋的配置
        # 這裡我們檢查路由數量來驗證（實際實現中可能需要更精確的檢查）
        routes = router.routes
        assert len(routes) > 0  # 至少有一些路由

        # 或者我們可以通過檢查是否有 POST 路由來驗證
        post_routes = [
            route
            for route in routes
            if hasattr(route, "methods") and "POST" in route.methods
        ]
        assert len(post_routes) == 0  # 讀取模式不應該有 POST 路由
