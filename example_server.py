"""完整的 FastAPI 服務器範例"""

from dataclasses import dataclass
from autocrud import AutoCRUD, DiskStorage
import uvicorn


@dataclass
class Book:
    title: str
    author: str
    isbn: str
    price: float
    published_year: int


@dataclass
class User:
    name: str
    email: str
    age: int
    is_active: bool = True


def create_book_api():
    """創建書籍管理 API"""
    storage = DiskStorage("./data/books")
    crud = AutoCRUD(model=Book, storage=storage, resource_name="books")

    return crud.create_fastapi_app(
        title="書籍管理 API",
        description="自動生成的書籍 CRUD API，支援完整的圖書管理功能",
        version="1.0.0",
    )


def create_user_api():
    """創建用戶管理 API"""
    storage = DiskStorage("./data/users")
    crud = AutoCRUD(model=User, storage=storage, resource_name="users")

    return crud.create_fastapi_app(
        title="用戶管理 API",
        description="自動生成的用戶 CRUD API，支援用戶註冊和管理功能",
        version="1.0.0",
    )


def create_combined_api():
    """創建包含多個資源的組合 API"""
    from fastapi import FastAPI
    from autocrud import FastAPIGenerator

    # 創建主應用
    main_app = FastAPI(
        title="圖書館管理系統",
        description="包含書籍和用戶管理的完整 API",
        version="1.0.0",
    )

    # 添加健康檢查
    @main_app.get("/health")
    async def health_check():
        return {"status": "healthy", "service": "圖書館管理系統"}

    # 創建書籍 CRUD
    book_storage = DiskStorage("./data/books")
    book_crud = AutoCRUD(model=Book, storage=book_storage, resource_name="books")

    # 創建用戶 CRUD
    user_storage = DiskStorage("./data/users")
    user_crud = AutoCRUD(model=User, storage=user_storage, resource_name="users")

    # 添加路由
    book_generator = FastAPIGenerator(book_crud)
    user_generator = FastAPIGenerator(user_crud)

    book_generator.create_routes(main_app, "/api/v1")
    user_generator.create_routes(main_app, "/api/v1")

    return main_app


def demo_api_calls():
    """展示如何調用 API"""
    print("=== API 調用示範 ===")
    print("""
# 使用 curl 調用 API 的例子：

# 1. 健康檢查
curl http://localhost:8000/health

# 2. 創建書籍
curl -X POST http://localhost:8000/api/v1/books \\
  -H "Content-Type: application/json" \\
  -d '{
    "title": "Python 程式設計",
    "author": "張三",
    "isbn": "978-1234567890",
    "price": 450.0,
    "published_year": 2023
  }'

# 3. 獲取所有書籍
curl http://localhost:8000/api/v1/books

# 4. 獲取特定書籍
curl http://localhost:8000/api/v1/books/{book_id}

# 5. 更新書籍
curl -X PUT http://localhost:8000/api/v1/books/{book_id} \\
  -H "Content-Type: application/json" \\
  -d '{
    "title": "Python 高級程式設計",
    "author": "張三",
    "isbn": "978-1234567890",
    "price": 520.0,
    "published_year": 2024
  }'

# 6. 刪除書籍
curl -X DELETE http://localhost:8000/api/v1/books/{book_id}

# 7. 創建用戶
curl -X POST http://localhost:8000/api/v1/users \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "李四",
    "email": "lisi@example.com",
    "age": 25,
    "is_active": true
  }'
""")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        api_type = sys.argv[1]
    else:
        api_type = "combined"

    print(f"啟動 {api_type} API 服務器...")

    if api_type == "books":
        app = create_book_api()
        print("書籍管理 API 已啟動")
    elif api_type == "users":
        app = create_user_api()
        print("用戶管理 API 已啟動")
    elif api_type == "combined":
        app = create_combined_api()
        print("組合 API 已啟動")
    else:
        print("未知的 API 類型，使用組合 API")
        app = create_combined_api()

    demo_api_calls()

    print("\n啟動服務器...")
    print("API 文檔: http://localhost:8000/docs")
    print("ReDoc 文檔: http://localhost:8000/redoc")
    print("按 Ctrl+C 停止服務器")

    # 啟動服務器
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=False,  # 設為 False 避免在生產環境中使用
    )
