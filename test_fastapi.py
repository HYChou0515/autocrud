"""測試 FastAPI 自動生成功能"""

from dataclasses import dataclass
from autocrud import AutoCRUD, MemoryStorage, FastAPIGenerator


@dataclass
class Product:
    name: str
    description: str
    price: float
    category: str


def test_fastapi_generation():
    """測試 FastAPI 應用生成"""
    print("=== 測試 FastAPI 自動生成 ===")

    # 創建 CRUD 系統
    storage = MemoryStorage()
    crud = AutoCRUD(model=Product, storage=storage, resource_name="products")

    # 方法1：使用 FastAPIGenerator
    print("\n1. 使用 FastAPIGenerator")
    generator = FastAPIGenerator(crud)

    # 檢查生成的 Pydantic 模型
    print(f"請求模型: {generator.request_model.__name__}")
    print(f"請求模型欄位: {list(generator.request_model.model_fields.keys())}")

    print(f"響應模型: {generator.response_model.__name__}")
    print(f"響應模型欄位: {list(generator.response_model.model_fields.keys())}")

    # 創建 FastAPI 應用
    app = generator.create_fastapi_app(
        title="產品管理 API", description="自動生成的產品 CRUD API", version="1.0.0"
    )

    print(f"FastAPI 應用標題: {app.title}")
    print(f"FastAPI 應用描述: {app.description}")

    # 方法2：使用便利方法
    print("\n2. 使用便利方法")
    app2 = crud.create_fastapi_app(
        title="產品 API v2", description="使用便利方法創建的 API"
    )

    print(f"便利方法應用標題: {app2.title}")

    # 檢查路由
    print("\n3. 檢查生成的路由")
    routes = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method != "HEAD":  # 忽略 HEAD 方法
                    routes.append(f"{method} {route.path}")
        elif hasattr(route, "path"):
            routes.append(f"GET {route.path}")

    routes.sort()
    for route in routes:
        print(f"  {route}")

    return app


def test_pydantic_models():
    """測試生成的 Pydantic 模型"""
    print("\n=== 測試 Pydantic 模型生成 ===")

    storage = MemoryStorage()
    crud = AutoCRUD(model=Product, storage=storage, resource_name="products")

    generator = FastAPIGenerator(crud)

    # 測試請求模型
    print("\n1. 測試請求模型")
    request_data = {
        "name": "筆記本電腦",
        "description": "高性能筆記本電腦",
        "price": 25000.0,
        "category": "電子產品",
    }

    try:
        request_instance = generator.request_model(**request_data)
        print(f"請求模型實例: {request_instance}")
        print(f"請求模型字典: {request_instance.model_dump()}")
    except Exception as e:
        print(f"創建請求模型失敗: {e}")

    # 測試響應模型
    print("\n2. 測試響應模型")
    response_data = {**request_data, "id": "test-id-123"}

    try:
        response_instance = generator.response_model(**response_data)
        print(f"響應模型實例: {response_instance}")
        print(f"響應模型字典: {response_instance.model_dump()}")
    except Exception as e:
        print(f"創建響應模型失敗: {e}")


def demo_api_usage():
    """展示 API 使用方法"""
    print("\n=== API 使用示範 ===")

    print("""
# 啟動 API 服務器的示例代碼：

```python
from dataclasses import dataclass
from autocrud import AutoCRUD, DiskStorage

@dataclass
class User:
    name: str
    email: str
    age: int

# 創建 CRUD 系统
storage = DiskStorage("./data")
crud = AutoCRUD(model=User, storage=storage, resource_name="users")

# 生成 FastAPI 應用
app = crud.create_fastapi_app(
    title="用戶管理 API",
    description="自動生成的用戶 CRUD API"
)

# 啟動服務器
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

# API 端點：
- POST   /api/v1/users          # 創建用戶
- GET    /api/v1/users/{id}     # 獲取用戶
- PUT    /api/v1/users/{id}     # 更新用戶
- DELETE /api/v1/users/{id}     # 刪除用戶
- GET    /api/v1/users          # 列出所有用戶
- GET    /health                # 健康檢查

# 自動生成的 OpenAPI 文檔：
- http://localhost:8000/docs    # Swagger UI
- http://localhost:8000/redoc   # ReDoc
""")


if __name__ == "__main__":
    test_fastapi_generation()
    test_pydantic_models()
    demo_api_usage()
