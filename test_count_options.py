"""測試 count API 選項功能"""

from dataclasses import dataclass
from autocrud import AutoCRUD, MultiModelAutoCRUD, MemoryStorage
from autocrud.fastapi_generator import FastAPIGenerator


@dataclass
class Item:
    name: str
    value: int


def test_fastapi_generator_with_count_disabled():
    """測試禁用 count API 的 FastAPIGenerator"""
    storage = MemoryStorage()
    crud = AutoCRUD(model=Item, storage=storage, resource_name="items")

    # 建立一些測試資料
    crud.create({"name": "item1", "value": 1})
    crud.create({"name": "item2", "value": 2})

    # 創建禁用 count 的生成器
    generator = FastAPIGenerator(crud, enable_count=False)

    from fastapi import FastAPI

    app = FastAPI()
    generator.create_routes(app, "/api/v1")

    # 檢查路由
    routes = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method not in ["HEAD", "OPTIONS"]:
                    routes.append(f"{method} {route.path}")

    print("禁用 count 時的路由:")
    for route in routes:
        print(f"  {route}")

    # 驗證沒有 count 路由
    assert "GET /api/v1/items/count" not in routes
    # 驗證其他路由存在
    assert "POST /api/v1/items" in routes
    assert "GET /api/v1/items/{resource_id}" in routes
    assert "GET /api/v1/items" in routes

    print("✅ 成功禁用 count 路由")


def test_fastapi_generator_with_count_enabled():
    """測試啟用 count API 的 FastAPIGenerator"""
    storage = MemoryStorage()
    crud = AutoCRUD(model=Item, storage=storage, resource_name="items")

    # 創建啟用 count 的生成器（預設行為）
    generator = FastAPIGenerator(crud, enable_count=True)

    from fastapi import FastAPI

    app = FastAPI()
    generator.create_routes(app, "/api/v1")

    # 檢查路由
    routes = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method not in ["HEAD", "OPTIONS"]:
                    routes.append(f"{method} {route.path}")

    print("\n啟用 count 時的路由:")
    for route in routes:
        print(f"  {route}")

    # 驗證 count 路由存在
    assert "GET /api/v1/items/count" in routes
    # 驗證其他路由存在
    assert "POST /api/v1/items" in routes
    assert "GET /api/v1/items/{resource_id}" in routes
    assert "GET /api/v1/items" in routes

    print("✅ 成功啟用 count 路由")


def test_autocrud_create_fastapi_app_count_options():
    """測試 AutoCRUD 的 create_fastapi_app 方法的 count 選項"""
    storage = MemoryStorage()
    crud = AutoCRUD(model=Item, storage=storage, resource_name="items")

    # 建立一些測試資料
    crud.create({"name": "item1", "value": 1})
    crud.create({"name": "item2", "value": 2})

    print("\n測試 AutoCRUD.create_fastapi_app 的 count 選項:")

    # 測試禁用 count
    app_without_count = crud.create_fastapi_app(enable_count=False)

    routes = []
    for route in app_without_count.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method not in ["HEAD", "OPTIONS"]:
                    routes.append(f"{method} {route.path}")

    assert "GET /api/v1/items/count" not in routes
    print("✅ AutoCRUD.create_fastapi_app(enable_count=False) 成功")

    # 測試啟用 count（預設）
    app_with_count = crud.create_fastapi_app(enable_count=True)

    routes = []
    for route in app_with_count.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method not in ["HEAD", "OPTIONS"]:
                    routes.append(f"{method} {route.path}")

    assert "GET /api/v1/items/count" in routes
    print("✅ AutoCRUD.create_fastapi_app(enable_count=True) 成功")


def test_multi_model_count_options():
    """測試多模型的 count 選項功能"""

    @dataclass
    class User:
        name: str
        email: str

    storage = MemoryStorage()
    multi_crud = MultiModelAutoCRUD(storage)
    multi_crud.register_model(User)
    multi_crud.register_model(Item, resource_name="items")

    print("\n測試多模型的 count 選項:")

    # 測試禁用 count
    app_without_count = multi_crud.create_fastapi_app(enable_count=False)

    routes = []
    for route in app_without_count.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method not in ["HEAD", "OPTIONS"]:
                    routes.append(f"{method} {route.path}")

    assert "GET /api/v1/users/count" not in routes
    assert "GET /api/v1/items/count" not in routes
    print("✅ MultiModelAutoCRUD.create_fastapi_app(enable_count=False) 成功")

    # 測試啟用 count
    app_with_count = multi_crud.create_fastapi_app(enable_count=True)

    routes = []
    for route in app_with_count.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method not in ["HEAD", "OPTIONS"]:
                    routes.append(f"{method} {route.path}")

    assert "GET /api/v1/users/count" in routes
    assert "GET /api/v1/items/count" in routes
    print("✅ MultiModelAutoCRUD.create_fastapi_app(enable_count=True) 成功")


def test_count_api_functionality():
    """測試 count API 的實際功能"""
    storage = MemoryStorage()
    crud = AutoCRUD(model=Item, storage=storage, resource_name="items")

    # 建立測試資料
    crud.create({"name": "item1", "value": 1})
    crud.create({"name": "item2", "value": 2})

    # 創建啟用 count 的應用
    app = crud.create_fastapi_app(enable_count=True)

    from fastapi.testclient import TestClient

    client = TestClient(app)

    print("\n測試 count API 功能:")

    # 測試 count 端點
    response = client.get("/api/v1/items/count")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    print(f"✅ Count API 回傳正確結果: {data}")


if __name__ == "__main__":
    print("🧪 測試 count API 選項功能\n")

    test_fastapi_generator_with_count_disabled()
    test_fastapi_generator_with_count_enabled()
    test_autocrud_create_fastapi_app_count_options()
    test_multi_model_count_options()
    test_count_api_functionality()

    print("\n🎉 所有測試通過！count API 選項功能正常運作")
