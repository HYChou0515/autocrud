"""測試 count API 功能"""

from autocrud import SingleModelCRUD, AutoCRUD, MemoryStorage
from .test_models import Item, User, Product


class TestCountAPI:
    """測試 count API 功能"""

    def test_count_empty(self):
        """測試空集合的 count"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Item, storage=storage, resource_name="items")

        assert crud.count() == 0

    def test_count_after_create(self):
        """測試建立項目後的 count"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Item, storage=storage, resource_name="items")

        # 建立幾個項目
        crud.create({"name": "item1", "value": 1})
        assert crud.count() == 1

        crud.create({"name": "item2", "value": 2})
        assert crud.count() == 2

        crud.create({"name": "item3", "value": 3})
        assert crud.count() == 3

    def test_count_after_delete(self):
        """測試刪除項目後的 count"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Item, storage=storage, resource_name="items")

        # 建立項目
        item1 = crud.create({"name": "item1", "value": 1})
        item2 = crud.create({"name": "item2", "value": 2})
        item3 = crud.create({"name": "item3", "value": 3})

        assert crud.count() == 3

        # 刪除一個項目
        crud.delete(item1)
        assert crud.count() == 2

        # 刪除另一個項目
        crud.delete(item2)
        assert crud.count() == 1

        # 刪除最後一個項目
        crud.delete(item3)
        assert crud.count() == 0

    def test_count_with_multiple_resources(self):
        """測試多個資源的 count 獨立性"""
        storage1 = MemoryStorage()
        storage2 = MemoryStorage()
        crud1 = SingleModelCRUD(model=Item, storage=storage1, resource_name="items1")
        crud2 = SingleModelCRUD(model=Item, storage=storage2, resource_name="items2")

        # 在第一個資源中建立項目
        crud1.create({"name": "item1", "value": 1})
        crud1.create({"name": "item2", "value": 2})

        # 在第二個資源中建立項目
        crud2.create({"name": "item3", "value": 3})

        # 驗證 count 是獨立的
        assert crud1.count() == 2
        assert crud2.count() == 1


class TestMultiModelCount:
    """測試多模型 count 功能"""

    def test_multi_model_count(self):
        """測試多模型的 count 功能"""
        multi_crud = AutoCRUD()

        # 註冊模型
        multi_crud.register_model(User)
        multi_crud.register_model(Product)

        # 初始 count 應該為 0
        assert multi_crud.count("users") == 0
        assert multi_crud.count("products") == 0

        # 建立使用者
        multi_crud.create("users", {"name": "Alice", "email": "alice@example.com"})
        multi_crud.create("users", {"name": "Bob", "email": "bob@example.com"})

        # 建立產品
        multi_crud.create("products", {"name": "Laptop", "price": 999.99})

        # 驗證各自的 count
        assert multi_crud.count("users") == 2
        assert multi_crud.count("products") == 1

        # 新增更多項目
        multi_crud.create("products", {"name": "Mouse", "price": 29.99})
        multi_crud.create("products", {"name": "Keyboard", "price": 99.99})

        # 再次驗證
        assert multi_crud.count("users") == 2
        assert multi_crud.count("products") == 3

    def test_multi_model_count_after_operations(self):
        """測試多模型在各種操作後的 count"""
        multi_crud = AutoCRUD()

        multi_crud.register_model(User)

        # 建立幾個使用者
        user1 = multi_crud.create(
            "users", {"name": "Alice", "email": "alice@example.com"}
        )
        user2 = multi_crud.create("users", {"name": "Bob", "email": "bob@example.com"})
        user3 = multi_crud.create(
            "users", {"name": "Charlie", "email": "charlie@example.com"}
        )

        assert multi_crud.count("users") == 3

        # 更新使用者（count 不應該改變）
        multi_crud.update(
            "users",
            user1,
            {"name": "Alice Smith", "email": "alice.smith@example.com"},
        )
        assert multi_crud.count("users") == 3

        # 刪除使用者
        multi_crud.delete("users", user2)
        assert multi_crud.count("users") == 2

        # 再刪除一個
        multi_crud.delete("users", user3)
        assert multi_crud.count("users") == 1


class TestCountFastAPI:
    """測試 count API 端點"""

    def test_count_api_endpoint_creation(self):
        """測試 count API 端點是否被建立"""
        from autocrud.fastapi_generator import FastAPIGenerator

        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Item, storage=storage, resource_name="items")
        generator = FastAPIGenerator(crud)

        from fastapi import FastAPI

        app = FastAPI()
        generator.create_routes(app, "/api/v1")

        # 檢查是否有 count 路由
        routes = []
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods:
                    if method not in ["HEAD", "OPTIONS"]:
                        routes.append(f"{method} {route.path}")

        # 應該包含 count 端點
        assert "GET /api/v1/items/count" in routes

    def test_count_api_response_format(self):
        """測試 count API 的回應格式"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Item, storage=storage, resource_name="items")

        # 建立一些項目
        crud.create({"name": "item1", "value": 1})
        crud.create({"name": "item2", "value": 2})

        # 建立 FastAPI 應用
        app = crud.create_fastapi_app()

        # 使用 TestClient 測試
        from fastapi.testclient import TestClient

        client = TestClient(app)

        response = client.get("/api/v1/items/count")

        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert data["count"] == 2
        assert isinstance(data["count"], int)

    def test_multi_model_count_api(self):
        """測試多模型的 count API"""

        multi_crud = AutoCRUD()
        multi_crud.register_model(User)
        multi_crud.register_model(Item, resource_name="items")

        # 建立一些資料
        multi_crud.create("users", {"name": "Alice", "email": "alice@example.com"})
        multi_crud.create("items", {"name": "item1", "value": 1})
        multi_crud.create("items", {"name": "item2", "value": 2})

        # 建立 FastAPI 應用
        app = multi_crud.create_fastapi_app()

        from fastapi.testclient import TestClient

        client = TestClient(app)

        # 測試 users count
        response = client.get("/api/v1/users/count")
        assert response.status_code == 200
        assert response.json()["count"] == 1

        # 測試 items count
        response = client.get("/api/v1/items/count")
        assert response.status_code == 200
        assert response.json()["count"] == 2


class TestCountAPIOptions:
    """測試 count API 選項功能"""

    def test_count_api_disabled_in_generator(self):
        """測試在 FastAPIGenerator 中禁用 count API"""
        from autocrud.fastapi_generator import FastAPIGenerator
        from autocrud.route_config import RouteConfig

        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Item, storage=storage, resource_name="items")

        # 創建禁用 count 的生成器
        config = RouteConfig(count=False)
        generator = FastAPIGenerator(crud, route_config=config)

        from fastapi import FastAPI

        app = FastAPI()
        generator.create_routes(app, "/api/v1")

        # 檢查路由
        routes = []
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods:
                    if method not in ["HEAD", "OPTIONS"]:
                        routes.append(f"{method} {route.path}")

        # 驗證沒有 count 路由
        assert "GET /api/v1/items/count" not in routes
        # 驗證其他路由存在
        assert "POST /api/v1/items" in routes
        assert "GET /api/v1/items/{resource_id}" in routes

    def test_autocrud_count_disabled(self):
        """測試 AutoCRUD.create_fastapi_app 禁用 count"""
        from autocrud.route_config import RouteConfig

        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Item, storage=storage, resource_name="items")

        # 創建禁用 count 的應用
        config = RouteConfig(count=False)
        app = crud.create_fastapi_app(route_config=config)

        routes = []
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods:
                    if method not in ["HEAD", "OPTIONS"]:
                        routes.append(f"{method} {route.path}")

        assert "GET /api/v1/items/count" not in routes

    def test_autocrud_count_enabled_by_default(self):
        """測試 AutoCRUD.create_fastapi_app 預設啟用 count"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Item, storage=storage, resource_name="items")

        # 創建應用（預設啟用 count）
        app = crud.create_fastapi_app()

        routes = []
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods:
                    if method not in ["HEAD", "OPTIONS"]:
                        routes.append(f"{method} {route.path}")

        assert "GET /api/v1/items/count" in routes

    def test_multi_model_count_disabled(self):
        """測試多模型禁用 count API"""
        from autocrud.route_config import RouteConfig

        multi_crud = AutoCRUD()
        multi_crud.register_model(User)
        multi_crud.register_model(Item, resource_name="items")

        # 創建禁用 count 的多模型應用
        config = RouteConfig(count=False)
        app = multi_crud.create_fastapi_app(route_config=config)

        routes = []
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods:
                    if method not in ["HEAD", "OPTIONS"]:
                        routes.append(f"{method} {route.path}")

        # 驗證所有模型都沒有 count 路由
        assert "GET /api/v1/users/count" not in routes
        assert "GET /api/v1/items/count" not in routes
        # 驗證其他路由存在
        assert "GET /api/v1/users" in routes
        assert "GET /api/v1/items" in routes

    def test_multi_model_count_enabled_by_default(self):
        """測試多模型預設啟用 count API"""

        multi_crud = AutoCRUD()
        multi_crud.register_model(User)
        multi_crud.register_model(Item, resource_name="items")

        # 創建應用（預設啟用 count）
        app = multi_crud.create_fastapi_app()

        routes = []
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods:
                    if method not in ["HEAD", "OPTIONS"]:
                        routes.append(f"{method} {route.path}")

        # 驗證所有模型都有 count 路由
        assert "GET /api/v1/users/count" in routes
        assert "GET /api/v1/items/count" in routes
