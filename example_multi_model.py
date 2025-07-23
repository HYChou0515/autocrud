"""多模型 AutoCRUD 使用範例"""

from dataclasses import dataclass
from autocrud import MultiModelAutoCRUD, MemoryStorage


# 定義多個模型
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


def main():
    """多模型 CRUD 示例"""
    print("=== 多模型 AutoCRUD 示例 ===")

    # 創建多模型 CRUD 系統
    storage = MemoryStorage()
    multi_crud = MultiModelAutoCRUD(storage)

    # 註冊多個模型
    print("\n📝 註冊模型...")
    _ = multi_crud.register_model(User)  # 自動命名為 'users'
    _ = multi_crud.register_model(Product)  # 自動命名為 'products'
    _ = multi_crud.register_model(Order)  # 自動命名為 'orders'

    print(f"已註冊的資源: {multi_crud.list_resources()}")

    # 創建一些測試數據
    print("\n👤 創建用戶...")
    user1 = multi_crud.create(
        "users", {"name": "Alice", "email": "alice@example.com", "age": 30}
    )
    user2 = multi_crud.create(
        "users", {"name": "Bob", "email": "bob@example.com", "age": 25}
    )
    print(f"創建用戶: {user1['name']} (ID: {user1['id'][:8]}...)")
    print(f"創建用戶: {user2['name']} (ID: {user2['id'][:8]}...)")

    print("\n📦 創建產品...")
    product1 = multi_crud.create(
        "products",
        {
            "name": "筆記本電腦",
            "description": "高性能筆記本電腦",
            "price": 25000.0,
            "category": "電子產品",
        },
    )
    product2 = multi_crud.create(
        "products",
        {
            "name": "無線滑鼠",
            "description": "高精度無線滑鼠",
            "price": 800.0,
            "category": "電子產品",
        },
    )
    print(f"創建產品: {product1['name']} (ID: {product1['id'][:8]}...)")
    print(f"創建產品: {product2['name']} (ID: {product2['id'][:8]}...)")

    print("\n🛒 創建訂單...")
    order1 = multi_crud.create(
        "orders",
        {
            "user_id": user1["id"],
            "product_id": product1["id"],
            "quantity": 1,
            "total_price": 25000.0,
            "status": "confirmed",
        },
    )
    order2 = multi_crud.create(
        "orders",
        {
            "user_id": user2["id"],
            "product_id": product2["id"],
            "quantity": 2,
            "total_price": 1600.0,
        },
    )
    print(
        f"創建訂單: {order1['id'][:8]}... (用戶: {user1['name']}, 產品: {product1['name']})"
    )
    print(
        f"創建訂單: {order2['id'][:8]}... (用戶: {user2['name']}, 產品: {product2['name']})"
    )

    # 查詢數據
    print("\n📊 查詢統計...")
    all_users = multi_crud.list_all("users")
    all_products = multi_crud.list_all("products")
    all_orders = multi_crud.list_all("orders")

    print(f"總用戶數: {len(all_users)}")
    print(f"總產品數: {len(all_products)}")
    print(f"總訂單數: {len(all_orders)}")

    # 演示跨模型查詢
    print("\n🔍 訂單詳情查詢...")
    for order_id, order in all_orders.items():
        user = multi_crud.get("users", order["user_id"])
        product = multi_crud.get("products", order["product_id"])

        print(f"訂單 {order_id[:8]}...:")
        print(
            f"  用戶: {user['name'] if user else '未知'} ({user['email'] if user else 'N/A'})"
        )
        print(f"  產品: {product['name'] if product else '未知'}")
        print(f"  數量: {order['quantity']}")
        print(f"  總價: ${order['total_price']:,.2f}")
        print(f"  狀態: {order['status']}")
        print()

    # 更新數據
    print("📝 更新訂單狀態...")
    updated_order = multi_crud.update(
        "orders",
        order2["id"],
        {
            "user_id": order2["user_id"],
            "product_id": order2["product_id"],
            "quantity": order2["quantity"],
            "total_price": order2["total_price"],
            "status": "shipped",
        },
    )
    print(f"訂單 {updated_order['id'][:8]}... 狀態更新為: {updated_order['status']}")

    # 刪除數據
    print("\n🗑️ 刪除數據...")
    deleted = multi_crud.delete("users", user2["id"])
    print(f"刪除用戶 {user2['name']}: {'成功' if deleted else '失敗'}")

    print(f"\n最終用戶數: {len(multi_crud.list_all('users'))}")

    return multi_crud


def demo_fastapi_integration():
    """演示 FastAPI 整合"""
    print("\n=== FastAPI 整合示例 ===")

    # 創建多模型系統
    storage = MemoryStorage()
    multi_crud = MultiModelAutoCRUD(storage)

    # 註冊模型
    multi_crud.register_model(User)
    multi_crud.register_model(Product)
    multi_crud.register_model(Order)

    # 創建 FastAPI 應用
    app = multi_crud.create_fastapi_app(
        title="多模型商店 API",
        description="支援用戶、產品和訂單管理的完整 CRUD API",
        version="1.0.0",
    )

    print("✅ FastAPI 應用創建成功")
    print(f"   標題: {app.title}")
    print(f"   描述: {app.description}")
    print(f"   版本: {app.version}")

    # 檢查生成的路由
    print("\n📋 生成的 API 端點:")
    routes = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method not in ["HEAD", "OPTIONS"]:
                    routes.append(f"   {method:6} {route.path}")

    # 按資源分組顯示
    user_routes = [r for r in routes if "/users" in r]
    product_routes = [r for r in routes if "/products" in r]
    order_routes = [r for r in routes if "/orders" in r]
    other_routes = [
        r
        for r in routes
        if not any(res in r for res in ["/users", "/products", "/orders"])
    ]

    if user_routes:
        print("  👤 用戶相關:")
        for route in user_routes:
            print(route)

    if product_routes:
        print("  📦 產品相關:")
        for route in product_routes:
            print(route)

    if order_routes:
        print("  🛒 訂單相關:")
        for route in order_routes:
            print(route)

    if other_routes:
        print("  🔧 其他:")
        for route in other_routes:
            print(route)

    print(f"\n總共生成了 {len([r for r in routes if r.strip()])} 個 API 端點")

    return app


if __name__ == "__main__":
    # 運行基本示例
    multi_crud = main()

    # 運行 FastAPI 整合示例
    app = demo_fastapi_integration()

    print("\n🚀 要啟動 API 服務器，請運行:")
    print("   pip install uvicorn")
    print("   uvicorn example_multi_model:app --reload")
    print("\n📖 API 文檔將在以下地址提供:")
    print("   http://localhost:8000/docs")
    print("   http://localhost:8000/redoc")
