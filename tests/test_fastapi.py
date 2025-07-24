"""測試 FastAPI 自動生成功能"""

from autocrud import SingleModelCRUD, MemoryStorage, FastAPIGenerator
from .test_models import Product, User, Book


class TestFastAPIGenerator:
    """測試 FastAPI 生成器"""

    def test_create_generator(self):
        """測試創建 FastAPI 生成器"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Product, storage=storage, resource_name="products")

        generator = FastAPIGenerator(crud)

        assert generator.crud == crud
        assert generator.request_model is not None
        assert generator.response_model is not None

    def test_request_model_fields(self):
        """測試請求模型欄位"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Product, storage=storage, resource_name="products")
        generator = FastAPIGenerator(crud)

        request_fields = list(generator.request_model.model_fields.keys())

        # 請求模型不應該包含 id
        assert "name" in request_fields
        assert "description" in request_fields
        assert "price" in request_fields
        assert "category" in request_fields
        assert "id" not in request_fields

    def test_response_model_fields(self):
        """測試響應模型欄位"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Product, storage=storage, resource_name="products")
        generator = FastAPIGenerator(crud)

        response_fields = list(generator.response_model.model_fields.keys())

        # 響應模型應該包含 id
        assert "name" in response_fields
        assert "description" in response_fields
        assert "price" in response_fields
        assert "category" in response_fields
        assert "id" in response_fields

    def test_create_fastapi_app(self):
        """測試創建 FastAPI 應用"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Product, storage=storage, resource_name="products")
        generator = FastAPIGenerator(crud)

        app = generator.create_fastapi_app(
            title="產品管理 API", description="測試 API", version="1.0.0"
        )

        assert app.title == "產品管理 API"
        assert app.description == "測試 API"
        assert app.version == "1.0.0"

    def test_create_routes(self):
        """測試創建路由"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Product, storage=storage, resource_name="products")
        generator = FastAPIGenerator(crud)

        from fastapi import FastAPI

        app = FastAPI()

        generator.create_routes(app, "/api/v1")

        # 檢查路由是否已添加
        routes = []
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods:
                    if method not in ["HEAD", "OPTIONS"]:
                        routes.append(f"{method} {route.path}")

        expected_routes = [
            "POST /api/v1/products",
            "GET /api/v1/products/{resource_id}",
            "PUT /api/v1/products/{resource_id}",
            "DELETE /api/v1/products/{resource_id}",
            "GET /api/v1/products",
        ]

        for expected_route in expected_routes:
            assert expected_route in routes

    def test_pydantic_model_creation(self, sample_product_data):
        """測試 Pydantic 模型創建"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Product, storage=storage, resource_name="products")
        generator = FastAPIGenerator(crud)

        # 測試請求模型
        request_instance = generator.request_model(**sample_product_data)
        request_dict = request_instance.model_dump()

        assert request_dict["name"] == sample_product_data["name"]
        assert request_dict["price"] == sample_product_data["price"]

        # 測試響應模型
        response_data = {**sample_product_data, "id": "test-id"}
        response_instance = generator.response_model(**response_data)
        response_dict = response_instance.model_dump()

        assert response_dict["id"] == "test-id"
        assert response_dict["name"] == sample_product_data["name"]


class TestAutoCRUDFastAPIIntegration:
    """測試 AutoCRUD 與 FastAPI 的整合"""

    def test_create_fastapi_app_convenience_method(self):
        """測試便利方法創建 FastAPI 應用"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Product, storage=storage, resource_name="products")

        app = crud.create_fastapi_app(
            title="產品 API", description="便利方法創建的 API"
        )

        assert app.title == "產品 API"
        assert app.description == "便利方法創建的 API"

    def test_fastapi_app_has_health_endpoint(self):
        """測試 FastAPI 應用包含健康檢查端點"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Product, storage=storage, resource_name="products")

        app = crud.create_fastapi_app()

        # 檢查是否有健康檢查路由
        health_routes = []
        for route in app.routes:
            if hasattr(route, "path") and route.path == "/health":
                health_routes.append(route)

        assert len(health_routes) > 0

    def test_fastapi_app_has_openapi_docs(self):
        """測試 FastAPI 應用包含 OpenAPI 文檔端點"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Product, storage=storage, resource_name="products")

        app = crud.create_fastapi_app()

        # 檢查文檔路由
        doc_paths = []
        for route in app.routes:
            if hasattr(route, "path"):
                doc_paths.append(route.path)

        assert "/docs" in doc_paths
        assert "/redoc" in doc_paths
        assert "/openapi.json" in doc_paths


class TestFastAPIAppBehavior:
    """測試 FastAPI 應用行為（不實際啟動服務器）"""

    def test_app_creation_with_different_models(self):
        """測試使用不同模型創建應用"""

        models = [(User, "users"), (Book, "books"), (Product, "products")]

        for model, resource_name in models:
            storage = MemoryStorage()
            crud = SingleModelCRUD(
                model=model, storage=storage, resource_name=resource_name
            )

            app = crud.create_fastapi_app(title=f"{model.__name__} API")

            assert app.title == f"{model.__name__} API"

            # 檢查是否有對應的路由
            routes = []
            for route in app.routes:
                if hasattr(route, "path"):
                    routes.append(route.path)

            assert f"/api/v1/{resource_name}" in routes

    def test_custom_prefix_and_settings(self):
        """測試自定義前綴和設定"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Product, storage=storage, resource_name="products")
        generator = FastAPIGenerator(crud)

        from fastapi import FastAPI

        app = FastAPI()

        # 使用自定義前綴
        generator.create_routes(app, "/custom/v2")

        routes = []
        for route in app.routes:
            if hasattr(route, "path"):
                routes.append(route.path)

        assert "/custom/v2/products" in routes
