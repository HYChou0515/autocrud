#!/usr/bin/env python3
"""
展示泛型類型支援的示例

本示例展示如何使用 SingleModelCRUD[T] 和 AutoCRUD 提供類型安全的 CRUD 操作。
"""

from dataclasses import dataclass
from typing import Optional
from autocrud import SingleModelCRUD, AutoCRUD
from autocrud.storage import MemoryStorage
from autocrud.metadata import MetadataConfig


@dataclass
class User:
    id: str
    name: str
    email: str
    age: Optional[int] = None
    created_time: Optional[str] = None
    updated_time: Optional[str] = None


@dataclass
class Product:
    id: str
    name: str
    price: float
    description: Optional[str] = None
    category: Optional[str] = None
    created_time: Optional[str] = None
    updated_time: Optional[str] = None


def example_single_model_crud():
    """展示泛型 SingleModelCRUD 的使用"""
    print("=== SingleModelCRUD[User] 示例 ===")

    # 創建帶有類型安全的 SingleModelCRUD
    storage = MemoryStorage()
    metadata_config = MetadataConfig.with_timestamps()

    user_crud: SingleModelCRUD[User] = SingleModelCRUD[User](
        model=User,
        storage=storage,
        resource_name="users",
        metadata_config=metadata_config,
    )

    # 創建用戶
    user_data = {"name": "Alice", "email": "alice@example.com", "age": 30}

    created_user = user_crud.create(user_data)
    print(f"創建用戶: {created_user['name']} ({created_user['email']})")
    print(f"創建時間: {created_user.get('created_time', 'N/A')}")

    # 獲取用戶
    user_id = created_user["id"]
    retrieved_user = user_crud.get(user_id)

    if retrieved_user:
        print(f"獲取用戶: {retrieved_user['name']}")

    # 列出所有用戶
    all_users = user_crud.list_all()
    print(f"用戶0: {all_users[0]}")
    print(f"總用戶數: {user_crud.count()}")

    return user_crud


def example_multi_model_autocrud():
    """展示多模型 AutoCRUD 的使用"""
    print("\n=== AutoCRUD 多模型示例 ===")

    # 創建多模型 AutoCRUD
    autocrud = AutoCRUD()

    # 註冊帶有類型安全的模型
    autocrud.register_model(User)
    autocrud.register_model(Product)

    print(f"註冊的資源: {list(autocrud.list_resources())}")

    # 創建用戶
    user_data = {"name": "Bob", "email": "bob@example.com", "age": 25}
    created_user = autocrud.create("users", user_data)
    print(f"創建用戶: {created_user['name']}")

    # 創建產品
    product_data = {
        "name": "iPhone 15",
        "price": 999.99,
        "description": "Latest smartphone",
        "category": "Electronics",
    }
    created_product = autocrud.create("products", product_data)
    print(f"創建產品: {created_product['name']} (${created_product['price']})")

    # 統計
    print(f"用戶總數: {autocrud.count('users')}")
    print(f"產品總數: {autocrud.count('products')}")

    return autocrud


def example_fastapi_integration():
    """展示 FastAPI 整合"""
    print("\n=== FastAPI 整合示例 ===")

    try:
        # 創建單模型 CRUD
        storage = MemoryStorage()
        user_crud: SingleModelCRUD[User] = SingleModelCRUD[User](
            model=User, storage=storage, resource_name="users"
        )

        # 創建 FastAPI 應用
        user_crud.create_fastapi_app(title="User API", version="1.0.0")
        print("FastAPI 應用創建成功！")
        print("可用的端點:")
        print("- GET /users - 列出所有用戶")
        print("- POST /users - 創建用戶")
        print("- GET /users/{user_id} - 獲取特定用戶")
        print("- PUT /users/{user_id} - 更新用戶")
        print("- DELETE /users/{user_id} - 刪除用戶")
        print("- GET /users/count - 獲取用戶總數")

        # 多模型 FastAPI 整合
        autocrud = AutoCRUD()
        autocrud.register_model(User)
        autocrud.register_model(Product)

        autocrud.create_fastapi_app(title="Multi-Model API")
        print("\n多模型 FastAPI 應用創建成功！")
        print("支援 users 和 products 兩種資源")

    except ImportError:
        print("FastAPI 未安裝，跳過 FastAPI 整合示例")


if __name__ == "__main__":
    # 運行示例
    example_single_model_crud()
    example_multi_model_autocrud()
    example_fastapi_integration()

    print("\n=== 類型安全特性 ===")
    print("使用泛型可以獲得:")
    print("1. IDE 自動完成支援")
    print("2. 靜態類型檢查")
    print("3. 更好的代碼可讀性")
    print("4. 編譯時錯誤檢測")

    print("\n示例完成！")
