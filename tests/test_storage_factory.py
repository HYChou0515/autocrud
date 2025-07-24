"""測試 StorageFactory 功能"""

import os
import tempfile
from autocrud import (
    AutoCRUD,
    StorageFactory,
    DefaultStorageFactory,
    MemoryStorage,
    DiskStorage,
)
from .test_models import User, Product


def test_memory_storage_factory():
    """測試內存存儲工廠"""
    factory = DefaultStorageFactory.memory()
    multi_crud = AutoCRUD(storage_factory=factory)

    # 註冊兩個模型
    multi_crud.register_model(User, "users")
    multi_crud.register_model(Product, "products")

    # 確認每個資源都有獨立的存儲
    user_storage = multi_crud.get_storage("users")
    product_storage = multi_crud.get_storage("products")

    assert isinstance(user_storage, MemoryStorage)
    assert isinstance(product_storage, MemoryStorage)
    assert user_storage is not product_storage  # 不同的實例

    # 創建數據測試存儲隔離
    user_data = {"name": "Alice", "email": "alice@example.com"}
    product_data = {"name": "Laptop", "price": 999.99}

    multi_crud.create("users", user_data)
    multi_crud.create("products", product_data)

    # 確認數據在正確的存儲中
    assert multi_crud.count("users") == 1
    assert multi_crud.count("products") == 1

    # 確認存儲是獨立的
    assert user_storage.size() == 1
    assert product_storage.size() == 1


def test_disk_storage_factory():
    """測試磁盤存儲工廠"""
    with tempfile.TemporaryDirectory() as temp_dir:
        factory = DefaultStorageFactory.disk(temp_dir)
        multi_crud = AutoCRUD(storage_factory=factory)

        # 註冊模型
        multi_crud.register_model(User, "users")
        multi_crud.register_model(Product, "products")

        # 確認每個資源都有獨立的磁盤存儲
        user_storage = multi_crud.get_storage("users")
        product_storage = multi_crud.get_storage("products")

        assert isinstance(user_storage, DiskStorage)
        assert isinstance(product_storage, DiskStorage)
        assert user_storage.base_dir != product_storage.base_dir

        # 確認基礎目錄正確
        expected_user_dir = os.path.join(temp_dir, "users")
        expected_product_dir = os.path.join(temp_dir, "products")

        assert user_storage.base_dir == expected_user_dir
        assert product_storage.base_dir == expected_product_dir

        # 創建數據
        user_data = {"name": "Bob", "email": "bob@example.com"}
        product_data = {"name": "Mouse", "price": 25.99}

        created_user_id = multi_crud.create("users", user_data)
        created_product_id = multi_crud.create("products", product_data)

        # 確認目錄被創建並且數據被存儲
        assert os.path.exists(expected_user_dir)
        assert os.path.exists(expected_product_dir)

        # 確認可以檢索數據
        assert multi_crud.get("users", created_user_id) is not None
        assert multi_crud.get("products", created_product_id) is not None


def test_custom_storage_factory():
    """測試自定義存儲工廠"""
    created_storages = []

    def custom_factory(resource_name: str) -> MemoryStorage:
        storage = MemoryStorage()
        storage.resource_name = resource_name  # 添加標識
        created_storages.append((resource_name, storage))
        return storage

    factory = DefaultStorageFactory.custom(custom_factory)
    multi_crud = AutoCRUD(storage_factory=factory)

    # 註冊模型
    multi_crud.register_model(User, "users")
    multi_crud.register_model(Product, "products")

    # 確認自定義工廠被調用
    assert len(created_storages) == 2
    assert created_storages[0][0] == "users"
    assert created_storages[1][0] == "products"

    # 確認存儲有正確的標識
    user_storage = multi_crud.get_storage("users")
    product_storage = multi_crud.get_storage("products")

    assert hasattr(user_storage, "resource_name")
    assert user_storage.resource_name == "users"
    assert product_storage.resource_name == "products"


def test_storage_factory_config():
    """測試存儲工廠配置"""
    # 使用配置創建工廠
    config = {"serializer": "json"}
    factory = StorageFactory(storage_type=DiskStorage, storage_config=config)
    multi_crud = AutoCRUD(storage_factory=factory)
    multi_crud.register_model(User, "users")

    user_storage = multi_crud.get_storage("users")
    assert isinstance(user_storage, DiskStorage)
    # 基礎目錄應該是自動生成的
    assert user_storage.base_dir == "data/users"


def test_mixed_storage_assignment():
    """測試混合存儲分配（工廠 + 手動指定）"""
    factory = DefaultStorageFactory.memory()
    multi_crud = AutoCRUD(storage_factory=factory)

    # 手動指定的存儲
    manual_storage = MemoryStorage()
    manual_storage.manual_flag = True

    # 一個使用工廠，一個手動指定
    multi_crud.register_model(User, "users")  # 使用工廠
    multi_crud.register_model(Product, "products", storage=manual_storage)  # 手動指定

    user_storage = multi_crud.get_storage("users")
    product_storage = multi_crud.get_storage("products")

    # 確認 users 使用工廠創建的存儲
    assert isinstance(user_storage, MemoryStorage)
    assert not hasattr(user_storage, "manual_flag")

    # 確認 products 使用手動指定的存儲
    assert product_storage is manual_storage
    assert hasattr(product_storage, "manual_flag")
    assert product_storage.manual_flag is True


def test_storage_factory_data_isolation():
    """測試存儲工廠創建的存儲之間的數據隔離"""
    factory = DefaultStorageFactory.memory()
    multi_crud = AutoCRUD(storage_factory=factory)

    # 註冊多個相同模型但不同資源名稱
    multi_crud.register_model(User, "users")
    multi_crud.register_model(User, "admins")
    multi_crud.register_model(User, "guests")

    # 在每個資源中創建數據
    multi_crud.create("users", {"name": "User1", "email": "user1@example.com"})
    multi_crud.create("admins", {"name": "Admin1", "email": "admin1@example.com"})
    multi_crud.create("guests", {"name": "Guest1", "email": "guest1@example.com"})

    # 確認數據隔離
    assert multi_crud.count("users") == 1
    assert multi_crud.count("admins") == 1
    assert multi_crud.count("guests") == 1

    # 確認每個資源有獨立的存儲
    users_storage = multi_crud.get_storage("users")
    admins_storage = multi_crud.get_storage("admins")
    guests_storage = multi_crud.get_storage("guests")

    assert users_storage is not admins_storage
    assert admins_storage is not guests_storage
    assert users_storage is not guests_storage

    # 確認數據只存在於正確的存儲中
    assert users_storage.size() == 1
    assert admins_storage.size() == 1
    assert guests_storage.size() == 1


def test_storage_factory_backwards_compatibility():
    """測試向後兼容性 - 不使用工廠的情況"""
    # 創建 AutoCRUD 而不指定工廠，應該使用默認的內存工廠
    multi_crud = AutoCRUD()

    multi_crud.register_model(User, "users")

    user_storage = multi_crud.get_storage("users")
    assert isinstance(user_storage, MemoryStorage)

    # 功能應該正常工作
    user_data = {"name": "TestUser", "email": "test@example.com"}
    created_user_id = multi_crud.create("users", user_data)
    created_user = multi_crud.get("users", created_user_id)
    assert created_user["name"] == "TestUser"
    assert multi_crud.count("users") == 1
