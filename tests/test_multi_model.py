"""測試多模型 AutoCRUD 功能"""

import pytest
from dataclasses import dataclass
from autocrud import MultiModelAutoCRUD, MemoryStorage, DiskStorage


@dataclass
class User:
    name: str
    email: str
    age: int


@dataclass
class Product:
    name: str
    description: str
    price: float
    category: str


@dataclass
class Order:
    user_id: str
    product_id: str
    quantity: int
    total_price: float
    status: str = "pending"


class TestMultiModelAutoCRUD:
    """測試多模型 AutoCRUD 基本功能"""

    def test_create_multi_model_crud(self):
        """測試創建多模型 CRUD 系統"""
        storage = MemoryStorage()
        multi_crud = MultiModelAutoCRUD(storage)

        assert multi_crud.storage == storage
        assert len(multi_crud.cruds) == 0
        assert len(multi_crud.models) == 0

    def test_register_single_model(self):
        """測試註冊單個模型"""
        storage = MemoryStorage()
        multi_crud = MultiModelAutoCRUD(storage)

        crud = multi_crud.register_model(User)

        assert len(multi_crud.cruds) == 1
        assert "users" in multi_crud.cruds
        assert multi_crud.cruds["users"] == crud
        assert multi_crud.models["users"] == User

    def test_register_multiple_models(self):
        """測試註冊多個模型"""
        storage = MemoryStorage()
        multi_crud = MultiModelAutoCRUD(storage)

        user_crud = multi_crud.register_model(User)
        product_crud = multi_crud.register_model(Product)
        order_crud = multi_crud.register_model(Order)

        assert len(multi_crud.cruds) == 3
        assert "users" in multi_crud.cruds
        assert "products" in multi_crud.cruds
        assert "orders" in multi_crud.cruds

        assert multi_crud.cruds["users"] == user_crud
        assert multi_crud.cruds["products"] == product_crud
        assert multi_crud.cruds["orders"] == order_crud

    def test_custom_resource_name(self):
        """測試自定義資源名稱"""
        storage = MemoryStorage()
        multi_crud = MultiModelAutoCRUD(storage)

        crud = multi_crud.register_model(User, resource_name="people")

        assert "people" in multi_crud.cruds
        assert "users" not in multi_crud.cruds
        assert multi_crud.cruds["people"] == crud

    def test_duplicate_resource_name_error(self):
        """測試重複資源名稱錯誤"""
        storage = MemoryStorage()
        multi_crud = MultiModelAutoCRUD(storage)

        multi_crud.register_model(User)

        with pytest.raises(ValueError, match="Resource 'users' already registered"):
            multi_crud.register_model(User)

    def test_register_model_plural_choice(self):
        """測試資源名稱複數形式選擇"""
        storage = MemoryStorage()
        multi_crud = MultiModelAutoCRUD(storage)
        
        # 測試默認行為（複數）
        multi_crud.register_model(User)
        assert "users" in multi_crud.list_resources()
        
        # 測試明確指定複數
        multi_crud.unregister_model("users")
        multi_crud.register_model(User, use_plural=True)
        assert "users" in multi_crud.list_resources()
        
        # 測試指定單數
        multi_crud.unregister_model("users")
        multi_crud.register_model(User, use_plural=False) 
        assert "user" in multi_crud.list_resources()
        
        # 測試自定義資源名稱（忽略 use_plural）
        multi_crud.unregister_model("user")
        multi_crud.register_model(User, resource_name="people", use_plural=False)
        assert "people" in multi_crud.list_resources()
        assert "person" not in multi_crud.list_resources()

    def test_singularize_resource_name(self):
        """測試單數資源名稱生成"""
        storage = MemoryStorage()
        multi_crud = MultiModelAutoCRUD(storage)
        
        # 測試不同的模型名稱
        test_cases = [
            ("User", "user"),
            ("Company", "company"), 
            ("ProductCategory", "product_category"),
            ("XMLParser", "xml_parser"),
        ]
        
        for model_name, expected in test_cases:
            result = multi_crud._singularize_resource_name(model_name)
            assert result == expected, f"Expected {expected}, got {result} for {model_name}"

    def test_get_crud(self):
        """測試獲取 CRUD 實例"""
        storage = MemoryStorage()
        multi_crud = MultiModelAutoCRUD(storage)

        user_crud = multi_crud.register_model(User)

        assert multi_crud.get_crud("users") == user_crud

        with pytest.raises(ValueError, match="Resource 'nonexistent' not registered"):
            multi_crud.get_crud("nonexistent")

    def test_get_model(self):
        """測試獲取模型類"""
        storage = MemoryStorage()
        multi_crud = MultiModelAutoCRUD(storage)

        multi_crud.register_model(User)

        assert multi_crud.get_model("users") == User

        with pytest.raises(ValueError, match="Resource 'nonexistent' not registered"):
            multi_crud.get_model("nonexistent")

    def test_list_resources(self):
        """測試列出資源"""
        storage = MemoryStorage()
        multi_crud = MultiModelAutoCRUD(storage)

        assert multi_crud.list_resources() == []

        multi_crud.register_model(User)
        multi_crud.register_model(Product)

        resources = multi_crud.list_resources()
        assert len(resources) == 2
        assert "users" in resources
        assert "products" in resources

    def test_unregister_model(self):
        """測試取消註冊模型"""
        storage = MemoryStorage()
        multi_crud = MultiModelAutoCRUD(storage)

        multi_crud.register_model(User)
        multi_crud.register_model(Product)

        assert len(multi_crud.cruds) == 2

        # 取消註冊存在的模型
        result = multi_crud.unregister_model("users")
        assert result is True
        assert len(multi_crud.cruds) == 1
        assert "users" not in multi_crud.cruds
        assert "products" in multi_crud.cruds

        # 取消註冊不存在的模型
        result = multi_crud.unregister_model("nonexistent")
        assert result is False


class TestMultiModelCRUDOperations:
    """測試多模型 CRUD 操作"""

    @pytest.fixture
    def multi_crud(self):
        """創建配置好的多模型 CRUD 系統"""
        storage = MemoryStorage()
        multi_crud = MultiModelAutoCRUD(storage)
        multi_crud.register_model(User)
        multi_crud.register_model(Product)
        multi_crud.register_model(Order)
        return multi_crud

    def test_create_operations(self, multi_crud):
        """測試創建操作"""
        # 創建用戶
        user = multi_crud.create(
            "users", {"name": "Alice", "email": "alice@example.com", "age": 30}
        )
        assert user["name"] == "Alice"
        assert "id" in user

        # 創建產品
        product = multi_crud.create(
            "products",
            {
                "name": "筆記本電腦",
                "description": "高性能筆記本",
                "price": 25000.0,
                "category": "電子產品",
            },
        )
        assert product["name"] == "筆記本電腦"
        assert "id" in product

        # 創建訂單
        order = multi_crud.create(
            "orders",
            {
                "user_id": user["id"],
                "product_id": product["id"],
                "quantity": 1,
                "total_price": 25000.0,
            },
        )
        assert order["user_id"] == user["id"]
        assert order["status"] == "pending"  # 默認值
        assert "id" in order

    def test_get_operations(self, multi_crud):
        """測試獲取操作"""
        # 創建測試數據
        user = multi_crud.create(
            "users", {"name": "Bob", "email": "bob@example.com", "age": 25}
        )

        # 獲取存在的項目
        retrieved_user = multi_crud.get("users", user["id"])
        assert retrieved_user is not None
        assert retrieved_user["name"] == "Bob"

        # 獲取不存在的項目
        nonexistent = multi_crud.get("users", "nonexistent-id")
        assert nonexistent is None

    def test_update_operations(self, multi_crud):
        """測試更新操作"""
        # 創建測試數據
        product = multi_crud.create(
            "products",
            {
                "name": "原始產品",
                "description": "原始描述",
                "price": 100.0,
                "category": "測試",
            },
        )

        # 更新產品
        updated = multi_crud.update(
            "products",
            product["id"],
            {
                "name": "更新產品",
                "description": "更新描述",
                "price": 200.0,
                "category": "測試",
            },
        )

        assert updated is not None
        assert updated["name"] == "更新產品"
        assert updated["price"] == 200.0
        assert updated["id"] == product["id"]

    def test_delete_operations(self, multi_crud):
        """測試刪除操作"""
        # 創建測試數據
        user = multi_crud.create(
            "users", {"name": "Charlie", "email": "charlie@example.com", "age": 35}
        )

        # 確認項目存在
        assert multi_crud.exists("users", user["id"]) is True

        # 刪除項目
        deleted = multi_crud.delete("users", user["id"])
        assert deleted is True

        # 確認項目已刪除
        assert multi_crud.exists("users", user["id"]) is False
        assert multi_crud.get("users", user["id"]) is None

    def test_list_all_operations(self, multi_crud):
        """測試列出所有項目操作"""
        # 創建多個用戶
        users_data = [
            {"name": "Alice", "email": "alice@example.com", "age": 30},
            {"name": "Bob", "email": "bob@example.com", "age": 25},
            {"name": "Charlie", "email": "charlie@example.com", "age": 35},
        ]

        created_users = []
        for user_data in users_data:
            user = multi_crud.create("users", user_data)
            created_users.append(user)

        # 列出所有用戶
        all_users = multi_crud.list_all("users")
        assert len(all_users) == 3

        # 驗證所有用戶都在列表中
        for created_user in created_users:
            assert created_user["id"] in all_users
            assert all_users[created_user["id"]]["name"] == created_user["name"]

    def test_cross_model_operations(self, multi_crud):
        """測試跨模型操作"""
        # 創建用戶和產品
        user = multi_crud.create(
            "users", {"name": "David", "email": "david@example.com", "age": 28}
        )

        product = multi_crud.create(
            "products",
            {
                "name": "滑鼠",
                "description": "無線滑鼠",
                "price": 500.0,
                "category": "電子產品",
            },
        )

        # 創建訂單連接用戶和產品
        order = multi_crud.create(
            "orders",
            {
                "user_id": user["id"],
                "product_id": product["id"],
                "quantity": 2,
                "total_price": 1000.0,
                "status": "confirmed",
            },
        )

        # 驗證關聯
        assert order["user_id"] == user["id"]
        assert order["product_id"] == product["id"]

        # 驗證可以獲取關聯的數據
        retrieved_user = multi_crud.get("users", order["user_id"])
        retrieved_product = multi_crud.get("products", order["product_id"])

        assert retrieved_user["name"] == "David"
        assert retrieved_product["name"] == "滑鼠"


class TestResourceNameGeneration:
    """測試資源名稱生成"""

    def test_pluralize_simple_names(self):
        """測試簡單名稱複數化"""
        storage = MemoryStorage()
        multi_crud = MultiModelAutoCRUD(storage)

        @dataclass
        class Cat:
            name: str

        @dataclass
        class Dog:
            name: str

        multi_crud.register_model(Cat)
        multi_crud.register_model(Dog)

        resources = multi_crud.list_resources()
        assert "cats" in resources
        assert "dogs" in resources

    def test_pluralize_complex_names(self):
        """測試複雜名稱複數化"""
        storage = MemoryStorage()
        multi_crud = MultiModelAutoCRUD(storage)

        @dataclass
        class UserProfile:
            name: str

        @dataclass
        class ProductCategory:
            name: str

        multi_crud.register_model(UserProfile)
        multi_crud.register_model(ProductCategory)

        resources = multi_crud.list_resources()
        assert "user_profiles" in resources
        assert "product_categories" in resources

    def test_pluralize_words_ending_in_y(self):
        """測試以 y 結尾的詞複數化"""
        storage = MemoryStorage()
        multi_crud = MultiModelAutoCRUD(storage)

        @dataclass
        class Company:
            name: str

        multi_crud.register_model(Company)

        resources = multi_crud.list_resources()
        assert "companies" in resources


class TestMultiModelFastAPIIntegration:
    """測試多模型 FastAPI 整合"""

    def test_create_fastapi_app(self):
        """測試創建 FastAPI 應用"""
        storage = MemoryStorage()
        multi_crud = MultiModelAutoCRUD(storage)

        multi_crud.register_model(User)
        multi_crud.register_model(Product)

        app = multi_crud.create_fastapi_app(
            title="測試 API", description="測試描述", version="2.0.0"
        )

        assert app.title == "測試 API"
        assert app.description == "測試描述"
        assert app.version == "2.0.0"

    def test_fastapi_routes_generation(self):
        """測試 FastAPI 路由生成"""
        storage = MemoryStorage()
        multi_crud = MultiModelAutoCRUD(storage)

        multi_crud.register_model(User)
        multi_crud.register_model(Product)

        app = multi_crud.create_fastapi_app()

        # 收集所有路由
        routes = []
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods:
                    if method not in ["HEAD", "OPTIONS"]:
                        routes.append(f"{method} {route.path}")

        # 檢查用戶路由
        expected_user_routes = [
            "POST /api/v1/users",
            "GET /api/v1/users/{resource_id}",
            "PUT /api/v1/users/{resource_id}",
            "DELETE /api/v1/users/{resource_id}",
            "GET /api/v1/users",
        ]

        # 檢查產品路由
        expected_product_routes = [
            "POST /api/v1/products",
            "GET /api/v1/products/{resource_id}",
            "PUT /api/v1/products/{resource_id}",
            "DELETE /api/v1/products/{resource_id}",
            "GET /api/v1/products",
        ]

        for expected_route in expected_user_routes + expected_product_routes:
            assert expected_route in routes

    def test_health_endpoint_with_model_info(self):
        """測試健康檢查端點包含模型信息"""
        storage = MemoryStorage()
        multi_crud = MultiModelAutoCRUD(storage)

        multi_crud.register_model(User)
        multi_crud.register_model(Product)
        multi_crud.register_model(Order)

        app = multi_crud.create_fastapi_app()

        # 檢查是否有健康檢查路由
        health_routes = []
        for route in app.routes:
            if hasattr(route, "path") and route.path == "/health":
                health_routes.append(route)

        assert len(health_routes) > 0


class TestMultiModelWithDifferentStorages:
    """測試多模型使用不同存儲後端"""

    def test_with_memory_storage(self):
        """測試使用內存存儲"""
        storage = MemoryStorage()
        multi_crud = MultiModelAutoCRUD(storage)

        multi_crud.register_model(User)
        multi_crud.register_model(Product)

        # 創建數據
        user = multi_crud.create(
            "users", {"name": "Alice", "email": "alice@example.com", "age": 30}
        )
        product = multi_crud.create(
            "products",
            {
                "name": "商品",
                "description": "測試商品",
                "price": 100.0,
                "category": "測試",
            },
        )

        # 驗證數據
        assert multi_crud.get("users", user["id"]) is not None
        assert multi_crud.get("products", product["id"]) is not None

        assert len(multi_crud.list_all("users")) == 1
        assert len(multi_crud.list_all("products")) == 1

    def test_with_disk_storage(self, temp_dir):
        """測試使用磁碟存儲"""
        storage = DiskStorage(temp_dir)
        multi_crud = MultiModelAutoCRUD(storage)

        multi_crud.register_model(User)
        multi_crud.register_model(Product)

        # 創建數據
        user = multi_crud.create(
            "users", {"name": "Bob", "email": "bob@example.com", "age": 25}
        )
        product = multi_crud.create(
            "products",
            {
                "name": "商品",
                "description": "測試商品",
                "price": 200.0,
                "category": "測試",
            },
        )

        # 創建新的多模型實例來測試持久化
        storage2 = DiskStorage(temp_dir)
        multi_crud2 = MultiModelAutoCRUD(storage2)
        multi_crud2.register_model(User)
        multi_crud2.register_model(Product)

        # 驗證數據持久化
        retrieved_user = multi_crud2.get("users", user["id"])
        retrieved_product = multi_crud2.get("products", product["id"])

        assert retrieved_user is not None
        assert retrieved_user["name"] == "Bob"
        assert retrieved_product is not None
        assert retrieved_product["name"] == "商品"
