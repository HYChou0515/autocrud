#!/usr/bin/env python3
"""
博客 API 示例

這個示例展示了如何使用 AutoCRUD 構建一個完整的博客 API，
包括文章、用戶、評論和標籤管理。

運行方式:
    python examples/blog_api_example.py

然後訪問:
    - API 文檔: http://localhost:8000/docs
    - 替代文檔: http://localhost:8000/redoc
"""

from dataclasses import dataclass
from typing import List, Optional, TypedDict
from pydantic import BaseModel, EmailStr
import msgspec
from fastapi import FastAPI, APIRouter

from autocrud.crud.core import (
    AutoCRUD,
    CreateRouteTemplate,
    ReadRouteTemplate,
    UpdateRouteTemplate,
    DeleteRouteTemplate,
    ListRouteTemplate,
)


# 使用不同的數據類型來展示 AutoCRUD 的多類型支持


# 1. Pydantic - 用於需要驗證的用戶數據
class User(BaseModel):
    username: str
    email: EmailStr
    display_name: str
    bio: Optional[str] = None
    is_active: bool = True


# 2. dataclass - 用於文章數據
@dataclass
class BlogPost:
    title: str
    content: str
    author_id: str
    published: bool = False
    tags: List[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


# 3. TypedDict - 用於簡單的評論數據
class Comment(TypedDict):
    content: str
    author_id: str
    post_id: str
    approved: bool


# 4. msgspec.Struct - 用於高性能的標籤數據
class Tag(msgspec.Struct):
    name: str
    description: str
    color: str = "#007bff"
    usage_count: int = 0


def create_blog_api() -> FastAPI:
    """創建博客 API 應用"""

    # 創建 AutoCRUD 實例，使用 kebab-case 命名
    crud = AutoCRUD(model_naming="kebab")

    # 添加所有 CRUD 路由模板
    crud.add_route_template(CreateRouteTemplate())
    crud.add_route_template(ReadRouteTemplate())
    crud.add_route_template(UpdateRouteTemplate())
    crud.add_route_template(DeleteRouteTemplate())
    crud.add_route_template(ListRouteTemplate())

    # 註冊所有數據模型
    crud.add_model(User)  # 生成 /user/* 端點
    crud.add_model(BlogPost)  # 生成 /blog-post/* 端點
    crud.add_model(Comment)  # 生成 /comment/* 端點
    crud.add_model(Tag)  # 生成 /tag/* 端點

    # 創建 FastAPI 應用
    app = FastAPI(
        title="博客 API",
        description="使用 AutoCRUD 構建的完整博客系統",
        version="1.0.0",
    )

    # 應用 AutoCRUD 生成的路由
    router = APIRouter()
    crud.apply(router)
    app.include_router(router)

    # 添加歡迎頁面
    @app.get("/", tags=["首頁"])
    async def welcome():
        return {
            "message": "歡迎使用博客 API！",
            "documentation": "/docs",
            "endpoints": {
                "users": "/user",
                "posts": "/blog-post",
                "comments": "/comment",
                "tags": "/tag",
            },
            "features": [
                "完整的 CRUD 操作",
                "支持多種數據類型",
                "自動 API 文檔生成",
                "RESTful 接口設計",
            ],
        }

    return app


def demo_usage():
    """演示 API 使用方法"""
    print("🎯 博客 API 演示")
    print("\n📚 可用端點:")

    endpoints = [
        ("POST /user", "創建新用戶"),
        ("GET /user", "列出所有用戶"),
        ("GET /user/{id}", "獲取用戶詳情"),
        ("PUT /user/{id}", "更新用戶信息"),
        ("DELETE /user/{id}", "刪除用戶"),
        "",
        ("POST /blog-post", "創建新文章"),
        ("GET /blog-post", "列出所有文章"),
        ("GET /blog-post/{id}", "獲取文章詳情"),
        ("PUT /blog-post/{id}", "更新文章"),
        ("DELETE /blog-post/{id}", "刪除文章"),
        "",
        ("POST /comment", "創建新評論"),
        ("GET /comment", "列出所有評論"),
        ("GET /comment/{id}", "獲取評論詳情"),
        ("PUT /comment/{id}", "更新評論"),
        ("DELETE /comment/{id}", "刪除評論"),
        "",
        ("POST /tag", "創建新標籤"),
        ("GET /tag", "列出所有標籤"),
        ("GET /tag/{id}", "獲取標籤詳情"),
        ("PUT /tag/{id}", "更新標籤"),
        ("DELETE /tag/{id}", "刪除標籤"),
    ]

    for endpoint in endpoints:
        if endpoint:
            method_url, description = endpoint
            print(f"  {method_url:<20} - {description}")
        else:
            print()

    print("\n📖 示例請求:")
    print("""
# 創建用戶
curl -X POST "http://localhost:8000/user" \\
  -H "Content-Type: application/json" \\
  -d '{
    "username": "john_doe",
    "email": "john@example.com",
    "display_name": "John Doe",
    "bio": "軟件開發者"
  }'

# 創建文章
curl -X POST "http://localhost:8000/blog-post" \\
  -H "Content-Type: application/json" \\
  -d '{
    "title": "我的第一篇文章",
    "content": "這是文章內容...",
    "author_id": "USER_ID",
    "published": true,
    "tags": ["技術", "編程"]
  }'

# 創建評論
curl -X POST "http://localhost:8000/comment" \\
  -H "Content-Type: application/json" \\
  -d '{
    "content": "很棒的文章！",
    "author_id": "USER_ID",
    "post_id": "POST_ID",
    "approved": true
  }'

# 創建標籤
curl -X POST "http://localhost:8000/tag" \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "Python",
    "description": "Python 編程語言相關內容",
    "color": "#3776ab"
  }'
""")


def main():
    """主函數"""
    app = create_blog_api()
    demo_usage()

    print("\n🚀 正在啟動博客 API 服務器...")
    print("📍 服務器地址: http://localhost:8000")
    print("📖 API 文檔: http://localhost:8000/docs")
    print("📋 替代文檔: http://localhost:8000/redoc")
    print("\n按 Ctrl+C 停止服務器")

    try:
        import uvicorn

        uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)
    except ImportError:
        print("❌ 需要安裝 uvicorn: pip install uvicorn")
        print("或者手動運行: uvicorn blog_api_example:app --reload")
        return app


if __name__ == "__main__":
    main()
