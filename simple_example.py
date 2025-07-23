"""簡單的多模型使用示例"""

from dataclasses import dataclass
from autocrud import MultiModelAutoCRUD, MemoryStorage


@dataclass
class User:
    name: str
    email: str
    age: int


@dataclass
class Product:
    name: str
    price: float
    category: str


def main():
    # 創建多模型系統
    storage = MemoryStorage()
    multi_crud = MultiModelAutoCRUD(storage)

    # 註冊模型
    multi_crud.register_model(User)  # 自動變成 'users'
    multi_crud.register_model(Product)  # 自動變成 'products'

    # 創建數據
    user = multi_crud.create(
        "users", {"name": "Alice", "email": "alice@example.com", "age": 30}
    )

    product = multi_crud.create(
        "products", {"name": "筆記本電腦", "price": 25000.0, "category": "電子產品"}
    )

    print(f"創建用戶: {user['name']}")
    print(f"創建產品: {product['name']}")

    # 創建 FastAPI 應用
    app = multi_crud.create_fastapi_app(title="商店 API", description="多模型 CRUD API")

    print(f"\nAPI 包含 {len(multi_crud.list_resources())} 個資源:")
    for resource in multi_crud.list_resources():
        print(f"- {resource}")

    return app


if __name__ == "__main__":
    app = main()
    print("\n可以使用 uvicorn simple_example:app --reload 啟動服務器")
