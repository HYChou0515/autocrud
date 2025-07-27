"""測試持久化功能"""

import importlib.util
import os
import pytest
from autocrud import SingleModelCRUD, DiskStorage, SerializerFactory
from .test_models import Product

try:
    importlib.util.find_spec("msgpack")

    HAS_MSGPACK = True
except ImportError:
    HAS_MSGPACK = False


class TestDiskPersistence:
    """測試硬碟儲存持久化功能"""

    def test_disk_persistence_basic(self, temp_dir):
        """測試基本持久化功能"""
        # 第一階段：創建數據並保存
        storage1 = DiskStorage(temp_dir)
        crud1 = SingleModelCRUD(
            model=Product, storage=storage1, resource_name="products"
        )

        # 創建一些產品
        products_data = [
            {
                "name": "筆記本電腦",
                "description": "高性能筆記本",
                "price": 25000.0,
                "category": "電子產品",
            },
            {
                "name": "無線滑鼠",
                "description": "高精度無線滑鼠",
                "price": 800.0,
                "category": "電子產品",
            },
            {
                "name": "咖啡豆",
                "description": "精品咖啡豆",
                "price": 450.0,
                "category": "食品",
            },
        ]

        created_products = []
        for product_data in products_data:
            product = crud1.create(product_data)
            created_products.append(product)

        assert len(created_products) == 3

        # 第二階段：重新載入數據
        storage2 = DiskStorage(temp_dir)
        crud2 = SingleModelCRUD(
            model=Product, storage=storage2, resource_name="products"
        )

        all_products = crud2.list_all()
        assert len(all_products) == 3

        # 驗證產品內容
        for product in all_products:
            assert "name" in product
            assert "description" in product
            assert "price" in product
            assert "category" in product

    def test_disk_persistence_updates(self, temp_dir):
        """測試持久化更新操作"""
        # 創建初始數據
        storage1 = DiskStorage(temp_dir)
        crud1 = SingleModelCRUD(
            model=Product, storage=storage1, resource_name="products"
        )

        product_id = crud1.create(
            {
                "name": "筆記本電腦",
                "description": "普通筆記本",
                "price": 25000.0,
                "category": "電子產品",
            }
        )

        # 更新數據
        assert crud1.update(
            product_id,
            {
                "name": "高端筆記本電腦",
                "description": "高端遊戲筆記本",
                "price": 30000.0,
                "category": "電子產品",
            },
        )
        updated_product = crud1.get(product_id)

        assert updated_product["name"] == "高端筆記本電腦"
        assert updated_product["price"] == 30000.0

        # 重新載入驗證更新
        storage2 = DiskStorage(temp_dir)
        crud2 = SingleModelCRUD(
            model=Product, storage=storage2, resource_name="products"
        )

        loaded_product = crud2.get(product_id)
        assert loaded_product["name"] == "高端筆記本電腦"
        assert loaded_product["price"] == 30000.0

    def test_disk_persistence_deletions(self, temp_dir):
        """測試持久化刪除操作"""
        # 創建初始數據
        storage1 = DiskStorage(temp_dir)
        crud1 = SingleModelCRUD(
            model=Product, storage=storage1, resource_name="products"
        )

        product1 = crud1.create(
            {
                "name": "產品1",
                "description": "測試產品1",
                "price": 100.0,
                "category": "測試",
            }
        )
        crud1.create(
            {
                "name": "產品2",
                "description": "測試產品2",
                "price": 200.0,
                "category": "測試",
            }
        )

        # 刪除一個產品
        deleted = crud1.delete(product1)
        assert deleted is True

        # 驗證只剩一個產品
        all_products = crud1.list_all()
        assert len(all_products) == 1

        # 重新載入驗證刪除
        storage2 = DiskStorage(temp_dir)
        crud2 = SingleModelCRUD(
            model=Product, storage=storage2, resource_name="products"
        )

        loaded_products = crud2.list_all()
        assert len(loaded_products) == 1

        remaining_product = loaded_products[0]
        assert remaining_product["name"] == "產品2"


class TestSerializerPersistence:
    """測試不同序列化器的持久化"""

    @pytest.mark.parametrize("serializer_type", ["json", "pickle", "msgpack"])
    def test_different_serializers_persistence(self, temp_dir, serializer_type):
        """測試不同序列化器的持久化"""
        if serializer_type == "msgpack" and not HAS_MSGPACK:
            pytest.skip("msgpack not available")

        test_data = {
            "name": "測試產品",
            "description": "測試描述",
            "price": 100.0,
            "category": "測試",
        }

        # 為每個序列化器使用不同的目錄
        storage_dir = os.path.join(temp_dir, serializer_type)
        os.makedirs(storage_dir, exist_ok=True)

        # 創建特定序列化器的存儲
        serializer = SerializerFactory.create(serializer_type)
        storage = DiskStorage(storage_dir, serializer=serializer)
        crud = SingleModelCRUD(model=Product, storage=storage, resource_name="products")

        # 創建數據
        product_id = crud.create(test_data)
        product = crud.get(product_id)
        assert product["name"] == test_data["name"]
        assert product["price"] == test_data["price"]

        # 重新載入
        storage2 = DiskStorage(storage_dir, serializer=serializer)
        crud2 = SingleModelCRUD(
            model=Product, storage=storage2, resource_name="products"
        )

        loaded_products = crud2.list_all()
        assert len(loaded_products) == 1

        loaded_product = loaded_products[0]
        assert loaded_product["name"] == test_data["name"]
        assert loaded_product["price"] == test_data["price"]

    def test_persistence_file_corruption_handling(self, temp_dir):
        """測試持久化文件損壞處理"""
        # 創建損壞的文件
        corrupt_file = os.path.join(temp_dir, "products:test.data")
        with open(corrupt_file, "w") as f:
            f.write("{ invalid json content")

        # 應該能處理損壞的文件並創建新的存儲
        storage = DiskStorage(temp_dir)
        crud = SingleModelCRUD(model=Product, storage=storage, resource_name="products")

        # 應該能正常創建數據
        product_id = crud.create(
            {
                "name": "測試產品",
                "description": "測試描述",
                "price": 100.0,
                "category": "測試",
            }
        )

        product = crud.get(product_id)
        assert product["name"] == "測試產品"

    def test_persistence_directory_creation(self, temp_dir):
        """測試持久化時自動創建目錄"""
        nested_dir = os.path.join(temp_dir, "nested", "path")

        # 目錄不應該存在
        assert not os.path.exists(nested_dir)

        # 創建存儲應該自動創建目錄
        storage = DiskStorage(nested_dir)
        crud = SingleModelCRUD(model=Product, storage=storage, resource_name="products")

        crud.create(
            {
                "name": "測試產品",
                "description": "測試描述",
                "price": 100.0,
                "category": "測試",
            }
        )

        # 目錄應該被創建
        assert os.path.exists(nested_dir)

        # 重新載入應該正常工作
        storage2 = DiskStorage(nested_dir)
        crud2 = SingleModelCRUD(
            model=Product, storage=storage2, resource_name="products"
        )

        loaded_products = crud2.list_all()
        assert len(loaded_products) == 1
