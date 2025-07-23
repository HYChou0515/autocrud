"""測試 API URL 複數形式選擇功能"""

from autocrud import MultiModelAutoCRUD
from autocrud.storage import MemoryStorage
from dataclasses import dataclass


@dataclass
class User:
    name: str
    email: str


@dataclass
class Company:
    name: str
    industry: str


def test_plural_choice():
    storage = MemoryStorage()
    multi_crud = MultiModelAutoCRUD(storage)

    # 測試默認行為（複數）
    print("=== 測試默認行為（複數） ===")
    user_crud = multi_crud.register_model(User)
    print(f"User 模型註冊為資源: {list(multi_crud.list_resources())}")
    
    # 測試明確指定複數
    multi_crud.unregister_model("users")
    print("\n=== 測試明確指定複數 ===")
    user_crud = multi_crud.register_model(User, use_plural=True)
    print(f"User 模型註冊為資源: {list(multi_crud.list_resources())}")
    
    # 測試指定單數
    print("\n=== 測試指定單數 ===")
    company_crud = multi_crud.register_model(Company, use_plural=False)
    print(f"所有資源: {list(multi_crud.list_resources())}")
    
    # 測試自定義資源名稱（忽略 use_plural）
    multi_crud.unregister_model("users")
    print("\n=== 測試自定義資源名稱 ===")
    user_crud = multi_crud.register_model(User, resource_name="people", use_plural=False)
    print(f"所有資源: {list(multi_crud.list_resources())}")

    # 創建 FastAPI 應用並檢查路由
    print("\n=== 測試 FastAPI 路由生成 ===")
    app = multi_crud.create_fastapi_app()
    
    # 列出所有路由
    routes = []
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            routes.append(f"{list(route.methods)[0]} {route.path}")
    
    print("生成的路由:")
    for route in sorted(routes):
        print(f"  {route}")


if __name__ == "__main__":
    test_plural_choice()
