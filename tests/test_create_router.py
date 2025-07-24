"""測試 create_router 新功能"""

from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from autocrud import SingleModelCRUD, MemoryStorage
from autocrud.fastapi_generator import FastAPIGenerator
from .test_models import Product


def test_create_router_basic():
    """測試基本的 create_router 功能"""
    storage = MemoryStorage()
    crud = SingleModelCRUD(model=Product, storage=storage, resource_name="products")
    generator = FastAPIGenerator(crud)

    # 創建路由
    router = generator.create_router(prefix="/api/v1")

    # 驗證路由類型
    assert isinstance(router, APIRouter)
    assert router.prefix == "/api/v1"


def test_create_router_with_parameters():
    """測試 create_router 支持 APIRouter 參數"""
    storage = MemoryStorage()
    crud = SingleModelCRUD(model=Product, storage=storage, resource_name="products")
    generator = FastAPIGenerator(crud)

    # 模擬依賴注入函數
    def get_current_user():
        return {"user_id": "test_user"}

    # 創建帶參數的路由
    router = generator.create_router(
        prefix="/api/v2",
        tags=["products", "inventory"],
        dependencies=[Depends(get_current_user)],
        responses={404: {"description": "Product not found"}},
    )

    # 驗證參數
    assert router.prefix == "/api/v2"
    assert router.tags == ["products", "inventory"]
    assert len(router.dependencies) == 1
    assert router.responses == {404: {"description": "Product not found"}}


def test_create_router_route_order():
    """測試路由順序：count 應該在 {resource_id} 之前"""
    storage = MemoryStorage()
    crud = SingleModelCRUD(model=Product, storage=storage, resource_name="products")
    generator = FastAPIGenerator(crud)  # 使用預設配置，包含 count

    # 創建應用並添加路由
    from fastapi import FastAPI

    app = FastAPI()
    router = generator.create_router(prefix="/api/v1")
    app.include_router(router)

    # 收集路由信息
    routes = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method not in ["HEAD", "OPTIONS"]:
                    routes.append(f"{method} {route.path}")

    # 驗證路由存在
    assert "GET /api/v1/products/count" in routes
    assert "GET /api/v1/products/{resource_id}" in routes
    assert "POST /api/v1/products" in routes

    # 測試 count 端點不會被錯誤匹配為 resource_id
    client = TestClient(app)

    # 先創建一個產品
    response = client.post(
        "/api/v1/products", json={"name": "Test Product", "price": 99.99}
    )
    assert response.status_code == 201

    # 測試 count 端點
    response = client.get("/api/v1/products/count")
    assert response.status_code == 200
    assert response.json() == {"count": 1}

    # 測試獲取具體資源（使用真實的 ID）
    created_product = client.post(
        "/api/v1/products", json={"name": "Another Product", "price": 149.99}
    ).json()
    response = client.get(f"/api/v1/products/{created_product['id']}")
    assert response.status_code == 200
    assert response.json()["name"] == "Another Product"


def test_create_router_with_disabled_count():
    """測試禁用 count 時的路由"""
    from autocrud.route_config import RouteConfig

    storage = MemoryStorage()
    crud = SingleModelCRUD(model=Product, storage=storage, resource_name="products")
    config = RouteConfig(count=False)
    generator = FastAPIGenerator(crud, route_config=config)

    from fastapi import FastAPI

    app = FastAPI()
    router = generator.create_router(prefix="/api/v1")
    app.include_router(router)

    # 收集路由信息
    routes = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method not in ["HEAD", "OPTIONS"]:
                    routes.append(f"{method} {route.path}")

    # 驗證沒有 count 路由
    assert "GET /api/v1/products/count" not in routes
    # 驗證其他路由存在
    assert "GET /api/v1/products/{resource_id}" in routes
    assert "POST /api/v1/products" in routes


def test_create_router_custom_tags():
    """測試自定義標籤功能"""
    storage = MemoryStorage()
    crud = SingleModelCRUD(model=Product, storage=storage, resource_name="products")
    generator = FastAPIGenerator(crud)

    # 測試默認標籤
    router1 = generator.create_router()
    assert router1.tags == ["products"]

    # 測試自定義標籤
    router2 = generator.create_router(tags=["inventory", "store"])
    assert router2.tags == ["inventory", "store"]


def test_create_router_integration_with_multi_model():
    """測試 create_router 與多模型系統的集成"""
    from autocrud import AutoCRUD

    multi_crud = AutoCRUD()
    multi_crud.register_model(Product)

    # 獲取單個模型的 CRUD
    product_crud = multi_crud.get_crud("products")
    generator = FastAPIGenerator(product_crud)

    # 創建路由
    router = generator.create_router(prefix="/api/v1", tags=["products"])

    # 驗證路由創建成功
    assert isinstance(router, APIRouter)
    assert router.prefix == "/api/v1"
    assert router.tags == ["products"]
