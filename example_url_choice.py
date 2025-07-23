"""演示 API URL 複數形式選擇功能的完整範例"""

from autocrud import MultiModelAutoCRUD
from autocrud.storage import MemoryStorage
from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    name: str
    email: str
    age: Optional[int] = None


@dataclass
class Product:
    name: str
    price: float
    category: str


@dataclass
class Company:
    name: str
    industry: str
    employee_count: int


def main():
    # 創建共享存儲
    storage = MemoryStorage()
    multi_crud = MultiModelAutoCRUD(storage)

    print("=== 註冊模型與 URL 形式設定 ===")

    # 1. 使用默認複數形式 (users)
    print("1. User 模型 - 默認複數形式")
    _ = multi_crud.register_model(User)
    print("   資源名稱: users")

    # 2. 明確指定單數形式 (product)
    print("2. Product 模型 - 指定單數形式")
    _ = multi_crud.register_model(Product, use_plural=False)
    print("   資源名稱: product")

    # 3. 自定義資源名稱 (organizations)
    print("3. Company 模型 - 自定義資源名稱")
    _ = multi_crud.register_model(Company, resource_name="organizations")
    print("   資源名稱: organizations")

    print(f"\n所有註冊的資源: {multi_crud.list_resources()}")

    # 創建 FastAPI 應用
    app = multi_crud.create_fastapi_app(
        title="靈活 URL API", description="展示不同 URL 形式的 CRUD API"
    )

    # 添加一些示例數據
    print("\n=== 添加示例數據 ===")

    # 添加用戶（複數 URL）
    user1 = multi_crud.create(
        "users", {"name": "Alice", "email": "alice@example.com", "age": 30}
    )
    print(f"創建用戶: {user1}")

    # 添加產品（單數 URL）
    product1 = multi_crud.create(
        "product", {"name": "筆記本電腦", "price": 999.99, "category": "電子產品"}
    )
    print(f"創建產品: {product1}")

    # 添加公司（自定義 URL）
    company1 = multi_crud.create(
        "organizations",
        {"name": "科技公司", "industry": "軟體開發", "employee_count": 100},
    )
    print(f"創建組織: {company1}")

    # 顯示生成的 API 路由
    print("\n=== 生成的 API 路由 ===")
    routes = []
    for route in app.routes:
        if (
            hasattr(route, "path")
            and hasattr(route, "methods")
            and route.path.startswith("/api")
        ):
            method = list(route.methods)[0] if route.methods else "GET"
            routes.append(f"{method:6} {route.path}")

    for route in sorted(routes):
        print(f"  {route}")

    print("\n=== API 使用說明 ===")
    print("複數形式 (users):")
    print("  GET    /api/v1/users        - 列出所有用戶")
    print("  POST   /api/v1/users        - 創建新用戶")
    print("  GET    /api/v1/users/{id}   - 獲取特定用戶")
    print("  PUT    /api/v1/users/{id}   - 更新用戶")
    print("  DELETE /api/v1/users/{id}   - 刪除用戶")
    print()
    print("單數形式 (product):")
    print("  GET    /api/v1/product      - 列出所有產品")
    print("  POST   /api/v1/product      - 創建新產品")
    print("  GET    /api/v1/product/{id} - 獲取特定產品")
    print("  PUT    /api/v1/product/{id} - 更新產品")
    print("  DELETE /api/v1/product/{id} - 刪除產品")
    print()
    print("自定義形式 (organizations):")
    print("  GET    /api/v1/organizations      - 列出所有組織")
    print("  POST   /api/v1/organizations      - 創建新組織")
    print("  GET    /api/v1/organizations/{id} - 獲取特定組織")
    print("  PUT    /api/v1/organizations/{id} - 更新組織")
    print("  DELETE /api/v1/organizations/{id} - 刪除組織")

    print("\n=== API 生成完成 ===")
    print("你可以使用 uvicorn 啟動伺服器:")
    print("  pip install uvicorn")
    print("  uvicorn example_url_choice:app --reload")
    print("然後訪問 http://127.0.0.1:8000/docs 查看 API 文檔")

    return app


if __name__ == "__main__":
    app = main()
