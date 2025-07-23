"""測試 Memory 存儲持久化功能"""

import os
import tempfile
from dataclasses import dataclass
from autocrud import AutoCRUD, MemoryStorage, SerializerFactory


@dataclass
class Product:
    name: str
    price: float
    category: str


def test_memory_persistence():
    """測試內存存儲持久化功能"""
    print("=== 測試 Memory 存儲持久化 ===")

    # 創建臨時文件
    temp_dir = tempfile.mkdtemp()
    persist_file = os.path.join(temp_dir, "test_data.json")
    print(f"使用持久化文件: {persist_file}")

    # 第一階段：創建數據並保存
    print("\n1. 創建數據並保存到文件")

    # 使用持久化的內存存儲
    storage1 = MemoryStorage(persist_file=persist_file)
    crud1 = AutoCRUD(model=Product, storage=storage1, resource_name="products")

    # 創建一些產品
    products_data = [
        {"name": "筆記本電腦", "price": 25000.0, "category": "電子產品"},
        {"name": "無線滑鼠", "price": 800.0, "category": "電子產品"},
        {"name": "咖啡豆", "price": 450.0, "category": "食品"},
    ]

    created_products = []
    for product_data in products_data:
        product = crud1.create(product_data)
        created_products.append(product)
        print(f"創建產品: {product}")

    print(f"總共創建了 {len(created_products)} 個產品")

    # 檢查文件是否存在
    print(f"持久化文件存在: {os.path.exists(persist_file)}")
    if os.path.exists(persist_file):
        file_size = os.path.getsize(persist_file)
        print(f"文件大小: {file_size} bytes")

    # 第二階段：重新載入數據
    print("\n2. 重新載入數據")

    # 創建新的存儲實例，應該自動載入之前的數據
    storage2 = MemoryStorage(persist_file=persist_file)
    crud2 = AutoCRUD(model=Product, storage=storage2, resource_name="products")

    # 列出所有產品
    all_products = crud2.list_all()
    print(f"載入後的產品數量: {len(all_products)}")

    for product_id, product in all_products.items():
        print(f"載入產品: {product_id} -> {product}")

    # 第三階段：修改數據並測試持久化
    print("\n3. 修改數據並測試持久化")

    # 更新第一個產品
    if created_products:
        first_product_id = created_products[0]["id"]
        updated_data = {
            "name": "高端筆記本電腦",
            "price": 30000.0,
            "category": "電子產品",
        }
        updated_product = crud2.update(first_product_id, updated_data)
        print(f"更新產品: {updated_product}")

        # 刪除最後一個產品
        last_product_id = created_products[-1]["id"]
        deleted = crud2.delete(last_product_id)
        print(f"刪除產品 {last_product_id}: {deleted}")

    # 第四階段：再次載入驗證變更
    print("\n4. 再次載入驗證變更")

    storage3 = MemoryStorage(persist_file=persist_file)
    crud3 = AutoCRUD(model=Product, storage=storage3, resource_name="products")

    final_products = crud3.list_all()
    print(f"最終產品數量: {len(final_products)}")

    for product_id, product in final_products.items():
        print(f"最終產品: {product_id} -> {product}")

    # 清理
    if os.path.exists(persist_file):
        os.remove(persist_file)
        print(f"\n清理測試文件: {persist_file}")


def test_different_serializers_persistence():
    """測試不同序列化器的持久化"""
    print("\n=== 測試不同序列化器的持久化 ===")

    temp_dir = tempfile.mkdtemp()
    test_data = {"name": "測試產品", "price": 100.0, "category": "測試"}

    serializer_types = ["json", "pickle", "msgpack"]

    for serializer_type in serializer_types:
        print(f"\n測試 {serializer_type} 序列化器")

        persist_file = os.path.join(temp_dir, f"test_{serializer_type}.json")

        try:
            # 創建特定序列化器的存儲
            serializer = SerializerFactory.create(serializer_type)
            storage = MemoryStorage(serializer=serializer, persist_file=persist_file)
            crud = AutoCRUD(
                model=Product, storage=storage, resource_name="test_products"
            )

            # 創建數據
            product = crud.create(test_data)
            print(f"  創建: {product}")

            # 重新載入
            storage2 = MemoryStorage(serializer=serializer, persist_file=persist_file)
            crud2 = AutoCRUD(
                model=Product, storage=storage2, resource_name="test_products"
            )

            loaded_products = crud2.list_all()
            print(f"  載入: {len(loaded_products)} 個產品")

            # 清理
            if os.path.exists(persist_file):
                os.remove(persist_file)

        except Exception as e:
            print(f"  {serializer_type} 測試失敗: {e}")


if __name__ == "__main__":
    test_memory_persistence()
    test_different_serializers_persistence()
