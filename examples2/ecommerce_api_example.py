#!/usr/bin/env python3
"""
電商 API 示例

這個示例展示了如何使用 AutoCRUD 構建一個電商系統，
包括商品、客戶、訂單和庫存管理。

特色功能:
- 支持多種數據類型 (Pydantic, dataclass, TypedDict, msgspec)
- 完整的 CRUD 操作
- 自動生成的 API 文檔
- RESTful 接口設計

運行方式:
    python examples/ecommerce_api_example.py
"""

from dataclasses import dataclass, field
from typing import List, Optional, TypedDict
from pydantic import BaseModel, EmailStr, validator
from decimal import Decimal
from enum import Enum
import msgspec
from datetime import datetime
from fastapi import FastAPI, APIRouter

from autocrud.crud.core import (
    AutoCRUD,
    CreateRouteTemplate,
    ReadRouteTemplate,
    UpdateRouteTemplate,
    DeleteRouteTemplate,
    ListRouteTemplate,
)


# 枚舉類型
class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class PaymentStatus(str, Enum):
    UNPAID = "unpaid"
    PAID = "paid"
    REFUNDED = "refunded"


# 1. Pydantic - 用於需要複雜驗證的商品數據
class Product(BaseModel):
    name: str
    description: str
    price: Decimal
    stock_quantity: int
    category: str
    brand: Optional[str] = None
    tags: List[str] = []
    is_active: bool = True

    @validator("price")
    def price_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError("價格必須大於0")
        return v

    @validator("stock_quantity")
    def stock_must_not_be_negative(cls, v):
        if v < 0:
            raise ValueError("庫存不能為負數")
        return v


# 2. Pydantic - 用於客戶數據驗證
class Customer(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    country: str = "Taiwan"
    is_vip: bool = False

    @validator("phone")
    def validate_phone(cls, v):
        if v and not v.replace("-", "").replace(" ", "").isdigit():
            raise ValueError("無效的電話號碼格式")
        return v


# 3. dataclass - 用於訂單項目
@dataclass
class OrderItem:
    product_id: str
    product_name: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal = field(init=False)

    def __post_init__(self):
        self.total_price = self.quantity * self.unit_price


# 4. dataclass - 用於訂單數據
@dataclass
class Order:
    customer_id: str
    items: List[OrderItem]
    status: OrderStatus = OrderStatus.PENDING
    payment_status: PaymentStatus = PaymentStatus.UNPAID
    total_amount: Decimal = field(init=False)
    shipping_address: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        # 計算總金額
        self.total_amount = sum(item.total_price for item in self.items)


# 5. TypedDict - 用於簡單的庫存記錄
class InventoryRecord(TypedDict):
    product_id: str
    change_type: str  # 'in', 'out', 'adjustment'
    quantity: int
    reason: str
    timestamp: str


# 6. msgspec.Struct - 用於高性能的分類數據
class Category(msgspec.Struct):
    name: str
    description: str
    parent_id: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True


def create_ecommerce_api() -> FastAPI:
    """創建電商 API 應用"""

    # 創建 AutoCRUD 實例
    crud = AutoCRUD(model_naming="kebab")

    # 添加所有 CRUD 路由模板
    templates = [
        CreateRouteTemplate(),
        ReadRouteTemplate(),
        UpdateRouteTemplate(),
        DeleteRouteTemplate(),
        ListRouteTemplate(),
    ]

    for template in templates:
        crud.add_route_template(template)

    # 註冊所有數據模型
    crud.add_model(Product)  # /product
    crud.add_model(Customer)  # /customer
    crud.add_model(Order)  # /order
    crud.add_model(OrderItem)  # /order-item
    crud.add_model(InventoryRecord)  # /inventory-record
    crud.add_model(Category)  # /category

    # 創建 FastAPI 應用
    app = FastAPI(
        title="電商 API",
        description="使用 AutoCRUD 構建的完整電商系統",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # 應用路由
    router = APIRouter()
    crud.apply(router)
    app.include_router(router)

    # 首頁
    @app.get("/", tags=["首頁"])
    async def home():
        return {
            "message": "歡迎使用電商 API",
            "version": "1.0.0",
            "documentation": "/docs",
            "features": ["商品管理", "客戶管理", "訂單處理", "庫存跟踪", "分類管理"],
            "endpoints": {
                "products": "/product",
                "customers": "/customer",
                "orders": "/order",
                "order_items": "/order-item",
                "inventory": "/inventory-record",
                "categories": "/category",
            },
        }

    # 健康檢查
    @app.get("/health", tags=["系統"])
    async def health_check():
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "service": "ecommerce-api",
        }

    return app


def demo_data_examples():
    """展示示例數據"""
    print("📦 電商 API 數據示例:")
    print()

    print("🛍️ 商品示例:")
    print("""
{
  "name": "MacBook Pro 14吋",
  "description": "Apple M2 Pro 晶片，16GB 記憶體，512GB SSD",
  "price": "65900.00",
  "stock_quantity": 50,
  "category": "筆記型電腦",
  "brand": "Apple",
  "tags": ["筆電", "Apple", "M2", "專業"],
  "is_active": true
}""")

    print("\n👤 客戶示例:")
    print("""
{
  "name": "王小明",
  "email": "wang@example.com",
  "phone": "0912-345-678",
  "address": "台北市信義區信義路五段7號",
  "city": "台北市",
  "postal_code": "110",
  "country": "Taiwan",
  "is_vip": false
}""")

    print("\n📋 訂單示例:")
    print("""
{
  "customer_id": "customer_123",
  "items": [
    {
      "product_id": "product_456",
      "product_name": "MacBook Pro 14吋",
      "quantity": 1,
      "unit_price": "65900.00"
    }
  ],
  "status": "pending",
  "payment_status": "unpaid",
  "shipping_address": "台北市信義區信義路五段7號",
  "notes": "請小心包裝"
}""")

    print("\n📊 庫存記錄示例:")
    print("""
{
  "product_id": "product_456",
  "change_type": "in",
  "quantity": 100,
  "reason": "新商品入庫",
  "timestamp": "2024-01-15T10:30:00"
}""")

    print("\n🏷️ 分類示例:")
    print("""
{
  "name": "筆記型電腦",
  "description": "各品牌筆記型電腦",
  "parent_id": null,
  "sort_order": 1,
  "is_active": true
}""")


def demo_api_usage():
    """演示 API 使用方法"""
    print("\n🔗 API 端點使用指南:")
    print()

    print("📝 創建商品:")
    print('curl -X POST "http://localhost:8000/product" \\')
    print('  -H "Content-Type: application/json" \\')
    print(
        '  -d \'{"name": "iPhone 15", "description": "最新 iPhone", "price": "32900", "stock_quantity": 100, "category": "手機"}\''
    )

    print("\n📋 列出所有商品:")
    print('curl "http://localhost:8000/product"')

    print("\n🔍 查詢特定商品:")
    print('curl "http://localhost:8000/product/{product_id}"')

    print("\n✏️ 更新商品:")
    print('curl -X PUT "http://localhost:8000/product/{product_id}" \\')
    print('  -H "Content-Type: application/json" \\')
    print('  -d \'{"name": "iPhone 15 Pro", "price": "38900"}\'')

    print("\n🗑️ 刪除商品:")
    print('curl -X DELETE "http://localhost:8000/product/{product_id}"')

    print("\n📊 查詢選項:")
    print("  • 分頁: ?limit=10&offset=0")
    print("  • 時間篩選: ?created_time_start=2024-01-01&created_time_end=2024-12-31")
    print("  • 響應類型: ?response_type=data|meta|full")


def main():
    """主函數"""
    app = create_ecommerce_api()

    print("🛒 電商 API 服務器")
    print("=" * 50)

    demo_data_examples()
    demo_api_usage()

    print("\n🚀 啟動服務器...")
    print("📍 服務器地址: http://localhost:8000")
    print("📖 API 文檔: http://localhost:8000/docs")
    print("📋 ReDoc 文檔: http://localhost:8000/redoc")
    print("🏠 首頁: http://localhost:8000")
    print("\n按 Ctrl+C 停止服務器")

    try:
        import uvicorn

        uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)
    except ImportError:
        print("\n❌ 需要安裝 uvicorn:")
        print("pip install uvicorn")
        print("\n或手動運行:")
        print("uvicorn ecommerce_api_example:app --reload")
        return app


if __name__ == "__main__":
    main()
