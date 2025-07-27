"""測試多模型 AutoCRUD 功能"""

import pytest
from dataclasses import dataclass
from autocrud import AutoCRUD, DefaultStorageFactory, ResourceNameStyle
from autocrud.metadata import MetadataConfig
from .test_models import User, Product, Cat, UserProfile, ProductCategory, Company


@dataclass
class Order:
    id: str
    user_id: str
    product_id: str
    quantity: int
    total_price: float
    status: str = "pending"


class TestMultiModelAutoCRUD:
    """測試多模型 AutoCRUD 基本功能"""

    def test_create_multi_model_crud(self):
        """測試創建多模型 CRUD 系統"""
        multi_crud = AutoCRUD()

        assert multi_crud.storage_factory is not None
        assert len(multi_crud.cruds) == 0
        assert len(multi_crud.models) == 0
        assert len(multi_crud.storages) == 0

    def test_register_single_model(self):
        """測試註冊單個模型"""
        # storage = MemoryStorage()  # 不再需要，使用 StorageFactory
        multi_crud = AutoCRUD()

        crud = multi_crud.register_model(User)

        assert len(multi_crud.cruds) == 1
        assert "users" in multi_crud.cruds
        assert multi_crud.cruds["users"] == crud
        assert multi_crud.models["users"] == User

    def test_register_multiple_models(self):
        """測試註冊多個模型"""
        # storage = MemoryStorage()  # 不再需要，使用 StorageFactory
        multi_crud = AutoCRUD()

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
        # storage = MemoryStorage()  # 不再需要，使用 StorageFactory
        multi_crud = AutoCRUD()

        crud = multi_crud.register_model(User, resource_name="people")

        assert "people" in multi_crud.cruds
        assert "users" not in multi_crud.cruds
        assert multi_crud.cruds["people"] == crud

    def test_duplicate_resource_name_error(self):
        """測試重複資源名稱錯誤"""
        # storage = MemoryStorage()  # 不再需要，使用 StorageFactory
        multi_crud = AutoCRUD()

        multi_crud.register_model(User)

        with pytest.raises(ValueError, match="Resource 'users' already registered"):
            multi_crud.register_model(User)

    def test_register_model_plural_choice(self):
        """測試資源名稱複數形式選擇"""
        # storage = MemoryStorage()  # 不再需要，使用 StorageFactory
        multi_crud = AutoCRUD()

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
        # storage = MemoryStorage()  # 不再需要，使用 StorageFactory
        multi_crud = AutoCRUD()

        # 測試不同的模型名稱
        test_cases = [
            ("User", "user"),
            ("Company", "company"),
            ("ProductCategory", "product_category"),
            ("XMLParser", "xml_parser"),
        ]

        for model_name, expected in test_cases:
            result = multi_crud._singularize_resource_name(
                model_name, ResourceNameStyle.SNAKE
            )
            assert result == expected, (
                f"Expected {expected}, got {result} for {model_name}"
            )

    def test_get_crud(self):
        """測試獲取 CRUD 實例"""
        # storage = MemoryStorage()  # 不再需要，使用 StorageFactory
        multi_crud = AutoCRUD()

        user_crud = multi_crud.register_model(User)

        assert multi_crud.get_crud("users") == user_crud

        with pytest.raises(ValueError, match="Resource 'nonexistent' not registered"):
            multi_crud.get_crud("nonexistent")

    def test_get_model(self):
        """測試獲取模型類"""
        # storage = MemoryStorage()  # 不再需要，使用 StorageFactory
        multi_crud = AutoCRUD()

        multi_crud.register_model(User)

        assert multi_crud.get_model("users") == User

        with pytest.raises(ValueError, match="Resource 'nonexistent' not registered"):
            multi_crud.get_model("nonexistent")

    def test_list_resources(self):
        """測試列出資源"""
        # storage = MemoryStorage()  # 不再需要，使用 StorageFactory
        multi_crud = AutoCRUD()

        assert multi_crud.list_resources() == []

        multi_crud.register_model(User)
        multi_crud.register_model(Product)

        resources = multi_crud.list_resources()
        assert len(resources) == 2
        assert "users" in resources
        assert "products" in resources

    def test_unregister_model(self):
        """測試取消註冊模型"""
        # storage = MemoryStorage()  # 不再需要，使用 StorageFactory
        multi_crud = AutoCRUD()

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
        # storage = MemoryStorage()  # 不再需要，使用 StorageFactory
        multi_crud = AutoCRUD()
        multi_crud.register_model(User)
        multi_crud.register_model(Product)
        multi_crud.register_model(Order)
        return multi_crud

    def test_create_operations(self, multi_crud):
        """測試創建操作"""
        # 創建用戶
        user_id = multi_crud.create(
            "users", {"name": "Alice", "email": "alice@example.com", "age": 30}
        )
        assert isinstance(user_id, str)

        # 驗證用戶創建成功
        user = multi_crud.get("users", user_id)
        assert user is not None
        assert user["name"] == "Alice"
        assert user["id"] == user_id

        # 創建產品
        product_id = multi_crud.create(
            "products",
            {
                "name": "筆記本電腦",
                "description": "高性能筆記本",
                "price": 25000.0,
                "category": "電子產品",
            },
        )
        assert isinstance(product_id, str)

        # 驗證產品創建成功
        product = multi_crud.get("products", product_id)
        assert product is not None
        assert product["name"] == "筆記本電腦"
        assert product["id"] == product_id

        # 創建訂單
        order_id = multi_crud.create(
            "orders",
            {
                "user_id": user_id,
                "product_id": product_id,
                "quantity": 1,
                "total_price": 25000.0,
            },
        )
        assert isinstance(order_id, str)

        # 驗證訂單創建成功
        order = multi_crud.get("orders", order_id)
        assert order is not None
        assert order["user_id"] == user_id
        assert order["status"] == "pending"  # 默認值
        assert order["id"] == order_id

    def test_get_operations(self, multi_crud):
        """測試獲取操作"""
        # 創建測試數據
        user_id = multi_crud.create(
            "users", {"name": "Bob", "email": "bob@example.com", "age": 25}
        )

        # 獲取存在的項目
        retrieved_user = multi_crud.get("users", user_id)
        assert retrieved_user is not None
        assert retrieved_user["name"] == "Bob"

        # 獲取不存在的項目
        nonexistent = multi_crud.get("users", "nonexistent-id")
        assert nonexistent is None

    def test_update_operations(self, multi_crud):
        """測試更新操作"""
        # 創建測試數據
        product_id = multi_crud.create(
            "products",
            {
                "name": "原始產品",
                "description": "原始描述",
                "price": 100.0,
                "category": "測試",
            },
        )

        # 更新產品
        success = multi_crud.update(
            "products",
            product_id,
            {
                "name": "更新產品",
                "description": "更新描述",
                "price": 200.0,
                "category": "測試",
            },
        )

        assert success is True

        # 驗證更新結果
        updated = multi_crud.get("products", product_id)
        assert updated is not None
        assert updated["name"] == "更新產品"
        assert updated["price"] == 200.0
        assert updated["id"] == product_id

    def test_delete_operations(self, multi_crud):
        """測試刪除操作"""
        # 創建測試數據
        user_id = multi_crud.create(
            "users", {"name": "Charlie", "email": "charlie@example.com", "age": 35}
        )

        # 確認項目存在
        assert multi_crud.exists("users", user_id) is True

        # 刪除項目
        deleted = multi_crud.delete("users", user_id)
        assert deleted is True

        # 確認項目已刪除
        assert multi_crud.exists("users", user_id) is False
        assert multi_crud.get("users", user_id) is None

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
            user_id = multi_crud.create("users", user_data)
            created_users.append(user_id)

        # 列出所有用戶
        all_users = multi_crud.list_all("users")
        assert len(all_users) == 3

        # 驗證所有用戶都在列表中
        user_ids = [user["id"] for user in all_users]
        for created_user_id in created_users:
            assert created_user_id in user_ids

        # 根據 ID 找到對應的用戶並驗證
        for i, created_user_id in enumerate(created_users):
            found_user = next(
                user for user in all_users if user["id"] == created_user_id
            )
            assert found_user["name"] == users_data[i]["name"]

    def test_cross_model_operations(self, multi_crud):
        """測試跨模型操作"""
        # 創建用戶和產品
        user_id = multi_crud.create(
            "users", {"name": "David", "email": "david@example.com", "age": 28}
        )

        product_id = multi_crud.create(
            "products",
            {
                "name": "滑鼠",
                "description": "無線滑鼠",
                "price": 500.0,
                "category": "電子產品",
            },
        )

        # 創建訂單連接用戶和產品
        order_id = multi_crud.create(
            "orders",
            {
                "user_id": user_id,
                "product_id": product_id,
                "quantity": 2,
                "total_price": 1000.0,
                "status": "confirmed",
            },
        )

        # 驗證訂單創建成功
        order = multi_crud.get("orders", order_id)
        assert order is not None
        assert order["user_id"] == user_id
        assert order["product_id"] == product_id

        # 驗證可以獲取關聯的數據
        retrieved_user = multi_crud.get("users", order["user_id"])
        retrieved_product = multi_crud.get("products", order["product_id"])

        assert retrieved_user["name"] == "David"
        assert retrieved_product["name"] == "滑鼠"


class TestResourceNameGeneration:
    """測試資源名稱生成"""

    def test_pluralize_simple_names(self):
        """測試簡單名稱複數化"""
        # storage = MemoryStorage()  # 不再需要，使用 StorageFactory
        multi_crud = AutoCRUD()

        @dataclass
        class Dog:
            id: str
            name: str

        multi_crud.register_model(Cat)
        multi_crud.register_model(Dog)

        resources = multi_crud.list_resources()
        assert "cats" in resources
        assert "dogs" in resources

    def test_pluralize_complex_names(self):
        """測試複雜名稱複數化"""
        # storage = MemoryStorage()  # 不再需要，使用 StorageFactory
        multi_crud = AutoCRUD()

        multi_crud.register_model(UserProfile)
        multi_crud.register_model(ProductCategory)

        resources = multi_crud.list_resources()
        assert "user_profiles" in resources
        assert "product_categories" in resources

    def test_pluralize_words_ending_in_y(self):
        """測試以 y 結尾的詞複數化"""
        # storage = MemoryStorage()  # 不再需要，使用 StorageFactory
        multi_crud = AutoCRUD()

        multi_crud.register_model(Company)

        resources = multi_crud.list_resources()
        assert "companies" in resources


class TestMultiModelFastAPIIntegration:
    """測試多模型 FastAPI 整合"""

    def test_create_fastapi_app(self):
        """測試創建 FastAPI 應用"""
        # storage = MemoryStorage()  # 不再需要，使用 StorageFactory
        multi_crud = AutoCRUD()

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
        # storage = MemoryStorage()  # 不再需要，使用 StorageFactory
        multi_crud = AutoCRUD()

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
        # storage = MemoryStorage()  # 不再需要，使用 StorageFactory
        multi_crud = AutoCRUD()

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
        # storage = MemoryStorage()  # 不再需要，使用 StorageFactory
        multi_crud = AutoCRUD()

        multi_crud.register_model(User)
        multi_crud.register_model(Product)

        # 創建數據
        user_id = multi_crud.create(
            "users", {"name": "Alice", "email": "alice@example.com", "age": 30}
        )
        product_id = multi_crud.create(
            "products",
            {
                "name": "商品",
                "description": "測試商品",
                "price": 100.0,
                "category": "測試",
            },
        )

        # 驗證數據
        assert multi_crud.get("users", user_id) is not None
        assert multi_crud.get("products", product_id) is not None

        assert len(multi_crud.list_all("users")) == 1
        assert len(multi_crud.list_all("products")) == 1

    def test_with_disk_storage(self, temp_dir):
        """測試使用磁碟存儲"""
        factory = DefaultStorageFactory.disk(temp_dir)
        multi_crud = AutoCRUD(storage_factory=factory)

        multi_crud.register_model(User)
        multi_crud.register_model(Product)

        # 創建數據
        user_id = multi_crud.create(
            "users", {"name": "Bob", "email": "bob@example.com", "age": 25}
        )
        product_id = multi_crud.create(
            "products",
            {
                "name": "商品",
                "description": "測試商品",
                "price": 200.0,
                "category": "測試",
            },
        )

        # 創建新的多模型實例來測試持久化，使用同一個目錄
        factory2 = DefaultStorageFactory.disk(temp_dir)
        multi_crud2 = AutoCRUD(storage_factory=factory2)
        multi_crud2.register_model(User)
        multi_crud2.register_model(Product)

        # 驗證數據持久化
        retrieved_user = multi_crud2.get("users", user_id)
        retrieved_product = multi_crud2.get("products", product_id)

        assert retrieved_user is not None
        assert retrieved_user["name"] == "Bob"
        assert retrieved_product is not None
        assert retrieved_product["name"] == "商品"


class TestAutoCRUDDefaults:
    """Test AutoCRUD with default configuration parameters"""

    def test_autocrud_with_default_metadata_config(self):
        """Test AutoCRUD with default metadata configuration"""
        # Use metadata config that doesn't require additional fields
        metadata_config = MetadataConfig(
            enable_timestamps=False, enable_user_tracking=False
        )
        autocrud = AutoCRUD(metadata_config=metadata_config)

        # Register model without explicit metadata config - should use default
        autocrud.register_model(User)

        # Check that the model uses the default metadata config
        # Use the resource name "users" (plural form by default)
        single_crud = autocrud.get_crud("users")
        assert single_crud.metadata_config == metadata_config
        assert not single_crud.metadata_config.enable_timestamps
        assert not single_crud.metadata_config.enable_user_tracking

    def test_autocrud_with_default_id_generator(self):
        """測試 AutoCRUD 初始化時提供預設 id_generator"""
        import time

        def custom_id_generator():
            return f"custom_{int(time.time() * 1000)}"

        multi_crud = AutoCRUD(id_generator=custom_id_generator)

        # 驗證預設 ID 生成器被設置
        assert multi_crud.default_id_generator == custom_id_generator

        # 註冊模型會使用預設 ID 生成器
        multi_crud.register_model(User)

        # 創建使用者來驗證自訂 ID 生成器被使用
        user_id = multi_crud.create(
            "users", {"name": "Test User", "email": "test@example.com", "age": 25}
        )

        assert user_id.startswith("custom_")

    def test_autocrud_with_default_use_plural(self):
        """測試 AutoCRUD 初始化時提供預設 use_plural 設定"""
        # 測試預設為 False（單數）
        multi_crud = AutoCRUD(use_plural=False)

        assert multi_crud.default_use_plural is False

        # 註冊模型會使用單數形式
        multi_crud.register_model(User)

        # 檢查資源名稱是單數
        resources = multi_crud.list_resources()
        assert "user" in resources  # 單數形式
        assert "users" not in resources

    def test_register_model_override_defaults(self):
        """測試 register_model 可以覆蓋預設配置"""
        # 設置預設配置 - 使用簡單配置避免欄位需求
        default_metadata = MetadataConfig(
            enable_timestamps=False, enable_user_tracking=False
        )

        def default_id_generator():
            return "default_id"

        multi_crud = AutoCRUD(
            metadata_config=default_metadata,
            id_generator=default_id_generator,
            use_plural=True,
        )

        # 覆蓋配置
        override_metadata = MetadataConfig(
            enable_timestamps=False, enable_user_tracking=False
        )

        def override_id_generator():
            return "override_id"

        multi_crud.register_model(
            User,
            metadata_config=override_metadata,
            id_generator=override_id_generator,
            use_plural=False,  # 覆蓋為單數
        )

        # 驗證覆蓋生效
        resources = multi_crud.list_resources()
        assert "user" in resources  # 使用了單數形式

        # 創建使用者驗證覆蓋的配置被使用
        user_id = multi_crud.create(
            "user",
            {"name": "Override User", "email": "override@example.com", "age": 30},
        )

        assert user_id == "override_id"  # 使用了覆蓋的 ID 生成器

    def test_none_defaults_use_builtin_behavior(self):
        """測試當預設值為 None 時使用內建行為"""
        multi_crud = AutoCRUD(metadata_config=None, id_generator=None, use_plural=True)

        # 註冊模型
        multi_crud.register_model(User)

        # 應該使用複數形式
        resources = multi_crud.list_resources()
        assert "users" in resources

        # 創建使用者
        user_id = multi_crud.create(
            "users",
            {"name": "None Default User", "email": "none@example.com", "age": 25},
        )

        # ID 應該是 UUID 格式（預設行為）
        import uuid

        assert uuid.UUID(user_id)

        user = multi_crud.get("users", user_id)
        # 沒有 metadata 配置，所以不應該有額外的欄位
        expected_fields = {"id", "name", "email", "age"}
        assert set(user.keys()) == expected_fields

    def test_mixed_default_and_explicit_models(self):
        """測試混合使用預設和明確配置的模型"""
        # 設置一些預設值 - 使用簡單配置避免欄位需求
        default_metadata = MetadataConfig(
            enable_timestamps=False, enable_user_tracking=False
        )
        multi_crud = AutoCRUD(
            metadata_config=default_metadata,
            use_plural=False,  # 預設單數
        )

        # 第一個模型使用預設配置
        multi_crud.register_model(User)  # 應該是 "user"

        # 第二個模型覆蓋 use_plural
        multi_crud.register_model(Product, use_plural=True)  # 應該是 "products"

        # 第三個模型指定資源名稱（忽略 use_plural）
        multi_crud.register_model(Order, resource_name="custom_orders")

        resources = multi_crud.list_resources()
        assert "user" in resources  # 使用預設單數
        assert "products" in resources  # 覆蓋為複數
        assert "custom_orders" in resources  # 明確指定名稱

        assert len(resources) == 3

    def test_storage_factory_with_defaults(self):
        """測試 storage_factory 與預設配置的結合"""
        from autocrud.storage_factory import DefaultStorageFactory

        # 使用自訂 storage_factory
        storage_factory = DefaultStorageFactory.disk("./test_data")
        metadata_config = MetadataConfig(
            enable_timestamps=False, enable_user_tracking=False
        )

        multi_crud = AutoCRUD(
            storage_factory=storage_factory, metadata_config=metadata_config
        )

        # 註冊模型
        multi_crud.register_model(User)

        # 驗證使用了正確的 storage
        storage = multi_crud.get_storage("users")
        assert storage.__class__.__name__ == "DiskStorage"

        # 驗證可以正常創建和取得資料
        user_id = multi_crud.create(
            "users",
            {"name": "Storage Test User", "email": "storage@example.com", "age": 28},
        )

        user = multi_crud.get("users", user_id)
        assert user["name"] == "Storage Test User"
