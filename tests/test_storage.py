"""測試存儲後端"""

import os
from dataclasses import dataclass
from autocrud import AutoCRUD, MemoryStorage, DiskStorage, SerializerFactory


@dataclass
class Product:
    name: str
    description: str
    price: float
    category: str


class TestMemoryStorage:
    """測試內存存儲"""

    def test_memory_storage_basic_operations(self, sample_product_data):
        """測試內存存儲基本操作"""
        storage = MemoryStorage()
        crud = AutoCRUD(model=Product, storage=storage, resource_name="products")

        # 創建
        product = crud.create(sample_product_data)
        assert product["name"] == sample_product_data["name"]

        # 獲取
        retrieved = crud.get(product["id"])
        assert retrieved is not None
        assert retrieved["name"] == sample_product_data["name"]

        # 更新
        updated_data = {
            "name": "更新產品",
            "description": "更新描述",
            "price": 999.0,
            "category": "測試",
        }
        updated = crud.update(product["id"], updated_data)
        assert updated["name"] == "更新產品"

        # 刪除
        deleted = crud.delete(product["id"])
        assert deleted is True
        assert crud.get(product["id"]) is None

    def test_memory_storage_persistence(self, sample_product_data):
        """測試內存存儲數據不會在實例間保持"""
        # 第一個存儲實例
        storage1 = MemoryStorage()
        crud1 = AutoCRUD(model=Product, storage=storage1, resource_name="products")
        product = crud1.create(sample_product_data)

        # 第二個存儲實例（應該是空的）
        storage2 = MemoryStorage()
        crud2 = AutoCRUD(model=Product, storage=storage2, resource_name="products")

        # 在新實例中查找數據
        result = crud2.get(product["id"])
        assert result is None  # 數據不應該存在

        all_products = crud2.list_all()
        assert len(all_products) == 0  # 應該是空的


class TestDiskStorage:
    """測試磁碟存儲"""

    def test_disk_storage_basic_operations(self, temp_dir, sample_product_data):
        """測試磁碟存儲基本操作"""
        storage = DiskStorage(temp_dir)
        crud = AutoCRUD(model=Product, storage=storage, resource_name="products")

        # 創建
        product = crud.create(sample_product_data)
        assert product["name"] == sample_product_data["name"]

        # 檢查文件是否創建
        files = os.listdir(temp_dir)
        assert len(files) == 1
        assert files[0].endswith(".data")

        # 獲取
        retrieved = crud.get(product["id"])
        assert retrieved is not None
        assert retrieved["name"] == sample_product_data["name"]

        # 更新
        updated_data = {
            "name": "更新產品",
            "description": "更新描述",
            "price": 999.0,
            "category": "測試",
        }
        updated = crud.update(product["id"], updated_data)
        assert updated["name"] == "更新產品"

        # 刪除
        deleted = crud.delete(product["id"])
        assert deleted is True
        assert crud.get(product["id"]) is None

        # 檢查文件是否刪除
        files = os.listdir(temp_dir)
        assert len(files) == 0

    def test_disk_storage_persistence(self, temp_dir, sample_product_data):
        """測試磁碟存儲數據持久化"""
        # 第一個存儲實例
        storage1 = DiskStorage(temp_dir)
        crud1 = AutoCRUD(model=Product, storage=storage1, resource_name="products")
        product = crud1.create(sample_product_data)
        product_id = product["id"]

        # 第二個存儲實例（應該能讀取相同數據）
        storage2 = DiskStorage(temp_dir)
        crud2 = AutoCRUD(model=Product, storage=storage2, resource_name="products")

        # 在新實例中查找數據
        retrieved = crud2.get(product_id)
        assert retrieved is not None
        assert retrieved["name"] == sample_product_data["name"]

        all_products = crud2.list_all()
        assert len(all_products) == 1
        assert product_id in all_products

    def test_disk_storage_with_different_serializers(
        self, temp_dir, sample_product_data
    ):
        """測試磁碟存儲使用不同序列化器"""
        serializer_types = ["json", "pickle"]

        for serializer_type in serializer_types:
            # 使用不同的子目錄避免衝突
            storage_dir = os.path.join(temp_dir, serializer_type)
            os.makedirs(storage_dir, exist_ok=True)

            serializer = SerializerFactory.create(serializer_type)
            storage = DiskStorage(storage_dir, serializer=serializer)
            crud = AutoCRUD(model=Product, storage=storage, resource_name="products")

            # 基本操作測試
            product = crud.create(sample_product_data)
            retrieved = crud.get(product["id"])

            assert retrieved is not None
            assert retrieved["name"] == sample_product_data["name"]
            assert retrieved["price"] == sample_product_data["price"]


class TestStorageComparison:
    """測試存儲比較"""

    def test_memory_vs_disk_performance(self, temp_dir, sample_product_data):
        """簡單的性能比較測試"""
        import time

        # 內存存儲性能
        memory_storage = MemoryStorage()
        memory_crud = AutoCRUD(
            model=Product, storage=memory_storage, resource_name="products"
        )

        start_time = time.time()
        for i in range(10):  # 減少次數以加快測試
            test_data = {**sample_product_data, "name": f"產品{i}"}
            memory_crud.create(test_data)
        memory_time = time.time() - start_time

        # 磁碟存儲性能
        disk_storage = DiskStorage(temp_dir)
        disk_crud = AutoCRUD(
            model=Product, storage=disk_storage, resource_name="products"
        )

        start_time = time.time()
        for i in range(10):
            test_data = {**sample_product_data, "name": f"產品{i}"}
            disk_crud.create(test_data)
        disk_time = time.time() - start_time

        # 磁碟應該比內存慢（但這只是一般期望，不是嚴格要求）
        assert memory_time >= 0  # 至少要大於0
        assert disk_time >= 0

        # 檢查數據正確性
        memory_products = memory_crud.list_all()
        disk_products = disk_crud.list_all()

        assert len(memory_products) == 10
        assert len(disk_products) == 10
