"""測試 FastAPI 應用創建（不運行服務器）"""

from dataclasses import dataclass
from autocrud import AutoCRUD, MemoryStorage


@dataclass
class Book:
    title: str
    author: str
    isbn: str
    price: float
    published_year: int


def test_full_api_creation():
    """測試完整的 API 創建流程"""
    print("=== 測試完整 API 創建 ===")

    # 使用內存存儲進行測試
    storage = MemoryStorage()
    crud = AutoCRUD(model=Book, storage=storage, resource_name="books")

    # 創建 FastAPI 應用
    app = crud.create_fastapi_app(
        title="書籍管理 API",
        description="自動生成的書籍 CRUD API，支援完整的圖書管理功能",
        version="1.0.0",
    )

    print("✅ API 創建成功")
    print(f"   標題: {app.title}")
    print(f"   描述: {app.description}")
    print(f"   版本: {app.version}")

    # 檢查路由
    print("\n📋 生成的路由:")
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method not in ["HEAD", "OPTIONS"]:
                    print(f"   {method:6} {route.path}")

    # 預填一些測試數據
    print("\n📚 添加測試數據:")
    test_books = [
        {
            "title": "Python 程式設計",
            "author": "張三",
            "isbn": "978-1111111111",
            "price": 450.0,
            "published_year": 2023,
        },
        {
            "title": "Web 開發實戰",
            "author": "李四",
            "isbn": "978-2222222222",
            "price": 520.0,
            "published_year": 2024,
        },
        {
            "title": "資料結構與算法",
            "author": "王五",
            "isbn": "978-3333333333",
            "price": 380.0,
            "published_year": 2022,
        },
    ]

    created_books = []
    for book_data in test_books:
        book = crud.create(book_data)
        created_books.append(book)
        print(f"   📖 {book['title']} (ID: {book['id'][:8]}...)")

    # 測試 CRUD 操作
    print("\n🔍 測試 CRUD 操作:")

    # 列出所有書籍
    all_books = crud.list_all()
    print(f"   列出所有書籍: {len(all_books)} 本")

    # 獲取特定書籍
    first_book_id = created_books[0]["id"]
    retrieved_book = crud.get(first_book_id)
    print(f"   獲取特定書籍: {retrieved_book['title']}")

    # 更新書籍
    updated_data = {
        "title": "Python 高級程式設計",
        "author": "張三",
        "isbn": "978-1111111111",
        "price": 550.0,
        "published_year": 2024,
    }
    updated_book = crud.update(first_book_id, updated_data)
    print(f"   更新書籍: {updated_book['title']}")

    # 刪除書籍
    last_book_id = created_books[-1]["id"]
    deleted = crud.delete(last_book_id)
    print(f"   刪除書籍: {'成功' if deleted else '失敗'}")

    # 最終狀態
    final_books = crud.list_all()
    print(f"   最終書籍數量: {len(final_books)} 本")

    return app


def show_deployment_info():
    """顯示部署信息"""
    print("\n🚀 部署信息:")
    print("""
要運行實際的 API 服務器，需要安裝 uvicorn:
    pip install uvicorn

然後可以這樣啟動服務器:
    
```python
from dataclasses import dataclass
from autocrud import AutoCRUD, DiskStorage

@dataclass
class Book:
    title: str
    author: str
    isbn: str
    price: float
    published_year: int

# 創建 API
storage = DiskStorage("./data")
crud = AutoCRUD(model=Book, storage=storage, resource_name="books")
app = crud.create_fastapi_app(title="書籍管理 API")

# 啟動服務器
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

或直接使用命令行:
    uvicorn example_server:app --host 0.0.0.0 --port 8000 --reload

API 文檔將在以下地址可用:
    • Swagger UI: http://localhost:8000/docs
    • ReDoc:      http://localhost:8000/redoc
    • OpenAPI:    http://localhost:8000/openapi.json
""")


if __name__ == "__main__":
    app = test_full_api_creation()
    show_deployment_info()

    print("\n✅ 第3步 FastAPI 自動生成完成！")
