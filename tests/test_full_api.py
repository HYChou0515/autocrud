"""測試完整 API 創建功能"""

import pytest
from autocrud import SingleModelCRUD, MemoryStorage
from .test_models import Book, User


class TestFullAPICreation:
    """測試完整的 API 創建流程"""

    @pytest.fixture
    def sample_books(self):
        """提供測試書籍數據"""
        return [
            {
                "title": "Python 程式設計",
                "author": "張三",
                "isbn": "978-1111111111",
                "price": 450.0,
                "published_year": 2023,
            },
            {
                "title": "Web 開發實戰",
                "author": "李四",
                "isbn": "978-2222222222",
                "price": 520.0,
                "published_year": 2024,
            },
            {
                "title": "資料結構與算法",
                "author": "王五",
                "isbn": "978-3333333333",
                "price": 380.0,
                "published_year": 2022,
            },
        ]

    def test_api_creation_basic(self):
        """測試基本 API 創建"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Book, storage=storage, resource_name="books")

        app = crud.create_fastapi_app(
            title="書籍管理 API",
            description="自動生成的書籍 CRUD API，支援完整的圖書管理功能",
            version="1.0.0",
        )

        assert app.title == "書籍管理 API"
        assert app.description == "自動生成的書籍 CRUD API，支援完整的圖書管理功能"
        assert app.version == "1.0.0"

    def test_api_routes_generation(self):
        """測試 API 路由生成"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Book, storage=storage, resource_name="books")

        app = crud.create_fastapi_app()

        # 收集所有路由
        routes = []
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods:
                    if method not in ["HEAD", "OPTIONS"]:
                        routes.append(f"{method} {route.path}")

        expected_routes = [
            "POST /api/v1/books",
            "GET /api/v1/books/{resource_id}",
            "PUT /api/v1/books/{resource_id}",
            "DELETE /api/v1/books/{resource_id}",
            "GET /api/v1/books",
        ]

        for expected_route in expected_routes:
            assert expected_route in routes

    def test_api_with_preloaded_data(self, sample_books):
        """測試預載數據的 API"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Book, storage=storage, resource_name="books")

        # 預填測試數據
        created_books = []
        for book_data in sample_books:
            book_id = crud.create(book_data)
            created_books.append(crud.get(book_id))

        assert len(created_books) == 3

        # 創建 API
        crud.create_fastapi_app(title="書籍管理 API", description="預載數據的 API")

        # 驗證數據仍然存在
        all_books = crud.list_all()
        assert len(all_books) == 3

        # 驗證每本書的數據
        for i, book in enumerate(all_books):
            original_book = sample_books[i]
            assert book["title"] == original_book["title"]
            assert book["author"] == original_book["author"]
            assert book["isbn"] == original_book["isbn"]

    def test_crud_operations_through_api_backend(self, sample_books):
        """測試通過 API 後端進行 CRUD 操作"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Book, storage=storage, resource_name="books")

        # 創建 API
        crud.create_fastapi_app()

        # 添加測試數據
        created_books = []
        for book_data in sample_books:
            book_id = crud.create(book_data)
            created_books.append(crud.get(book_id))

        # 測試列出所有書籍
        all_books = crud.list_all()
        assert len(all_books) == 3

        # 測試獲取特定書籍
        first_book_id = created_books[0]["id"]
        retrieved_book = crud.get(first_book_id)
        assert retrieved_book["title"] == sample_books[0]["title"]

        # 測試更新書籍
        updated_data = {
            "title": "Python 高級程式設計",
            "author": "張三",
            "isbn": "978-1111111111",
            "price": 550.0,
            "published_year": 2024,
        }
        assert crud.update(first_book_id, updated_data)
        updated_book = crud.get(first_book_id)
        assert updated_book["title"] == "Python 高級程式設計"
        assert updated_book["price"] == 550.0

        # 測試刪除書籍
        last_book_id = created_books[-1]["id"]
        deleted = crud.delete(last_book_id)
        assert deleted is True

        # 驗證最終狀態
        final_books = crud.list_all()
        assert len(final_books) == 2  # 3 - 1 = 2

    def test_api_with_different_models(self):
        """測試不同模型的 API 創建"""

        from dataclasses import dataclass

        @dataclass
        class Article:
            id: str
            title: str
            content: str
            author: str
            published: bool

        models = [
            (Book, "books", "書籍管理 API"),
            (Article, "articles", "文章管理 API"),
            (User, "users", "用戶管理 API"),
        ]

        for model, resource_name, title in models:
            storage = MemoryStorage()
            crud = SingleModelCRUD(
                model=model, storage=storage, resource_name=resource_name
            )

            app = crud.create_fastapi_app(title=title)

            assert app.title == title

            # 檢查路由
            routes = []
            for route in app.routes:
                if hasattr(route, "path"):
                    routes.append(route.path)

            assert f"/api/v1/{resource_name}" in routes

    def test_api_health_and_docs_endpoints(self):
        """測試 API 健康檢查和文檔端點"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Book, storage=storage, resource_name="books")

        app = crud.create_fastapi_app()

        # 收集所有路由路徑
        paths = []
        for route in app.routes:
            if hasattr(route, "path"):
                paths.append(route.path)

        # 檢查標準端點
        assert "/health" in paths
        assert "/docs" in paths
        assert "/redoc" in paths
        assert "/openapi.json" in paths

    def test_api_configuration_options(self):
        """測試 API 配置選項"""
        storage = MemoryStorage()
        crud = SingleModelCRUD(model=Book, storage=storage, resource_name="books")

        # 測試完整配置
        app = crud.create_fastapi_app(
            title="自定義標題",
            description="自定義描述",
            version="2.1.0",
            prefix="/custom/v2",
        )

        assert app.title == "自定義標題"
        assert app.description == "自定義描述"
        assert app.version == "2.1.0"
