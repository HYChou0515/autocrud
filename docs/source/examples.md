# 💡 示例集合

本節提供了 AutoCRUD 的豐富實際使用案例，涵蓋從基礎到高級的各種場景。

## 基礎示例

### 1. 快速開始

最簡單的 CRUD API 示例：

```python
# simple_example.py
from pydantic import BaseModel
from fastapi import FastAPI, APIRouter
from autocrud.crud.core import (
    AutoCRUD, CreateRouteTemplate, ReadRouteTemplate,
    UpdateRouteTemplate, DeleteRouteTemplate, ListRouteTemplate
)

class User(BaseModel):
    name: str
    email: str
    age: int = None

# 創建 CRUD
crud = AutoCRUD(model_naming="kebab")

# 添加所有 CRUD 操作
for template in [CreateRouteTemplate(), ReadRouteTemplate(), 
                UpdateRouteTemplate(), DeleteRouteTemplate(), 
                ListRouteTemplate()]:
    crud.add_route_template(template)

# 註冊模型
crud.add_model(User)

# 集成到 FastAPI
app = FastAPI(title="簡單 CRUD API")
router = APIRouter()
crud.apply(router)
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

運行後可訪問：
- `POST /user` - 創建用戶
- `GET /user/{id}` - 獲取用戶
- `PUT /user/{id}` - 更新用戶
- `DELETE /user/{id}` - 刪除用戶
- `GET /user` - 列出用戶

### 2. 多數據類型支持

展示所有支持的數據類型：

```python
# multi_type_example.py
from typing import TypedDict, Optional, List
from dataclasses import dataclass
from pydantic import BaseModel, Field
import msgspec
from datetime import datetime

# 1. Pydantic (推薦用於 API)
class User(BaseModel):
    id: Optional[str] = None
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., regex=r'^[^@]+@[^@]+\.[^@]+$')
    age: Optional[int] = Field(None, ge=0, le=150)
    created_at: Optional[datetime] = None

# 2. TypedDict (輕量級)
class Product(TypedDict):
    id: Optional[str]
    name: str
    price: float
    category: str
    in_stock: bool

# 3. dataclass (Python 原生)
@dataclass
class Order:
    id: Optional[str] = None
    customer_id: str = ""
    items: List[dict] = None
    total: float = 0.0
    status: str = "pending"
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.items is None:
            self.items = []
        if self.created_at is None:
            self.created_at = datetime.now()

# 4. msgspec (高性能)
class Event(msgspec.Struct):
    id: Optional[str] = None
    type: str
    data: dict
    timestamp: float
    priority: int = 1

# 創建統一 CRUD
from autocrud.crud.core import AutoCRUD
from fastapi import FastAPI, APIRouter

crud = AutoCRUD(model_naming="kebab")

# 添加路由模板
from autocrud.crud.core import (
    CreateRouteTemplate, ReadRouteTemplate, UpdateRouteTemplate,
    DeleteRouteTemplate, ListRouteTemplate
)

templates = [
    CreateRouteTemplate(),
    ReadRouteTemplate(),
    UpdateRouteTemplate(),
    DeleteRouteTemplate(),
    ListRouteTemplate()
]

for template in templates:
    crud.add_route_template(template)

# 註冊所有模型
crud.add_model(User)      # /user/*
crud.add_model(Product)   # /product/*
crud.add_model(Order)     # /order/*
crud.add_model(Event)     # /event/*

app = FastAPI(title="多類型 CRUD API")
router = APIRouter()
crud.apply(router, prefix="/api/v1")
app.include_router(router)
```

## 電商系統示例

### 3. 完整電商 API

一個功能完整的電商系統示例：

```python
# ecommerce_example.py
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict
from enum import Enum
from decimal import Decimal
from datetime import datetime
from fastapi import FastAPI, APIRouter, Depends, HTTPException

# 枚舉定義
class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

class ProductStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    OUT_OF_STOCK = "out_of_stock"

# 模型定義
class Category(BaseModel):
    id: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    parent_id: Optional[str] = None
    created_at: Optional[datetime] = None

class Product(BaseModel):
    id: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    price: Decimal = Field(..., gt=0, decimal_places=2)
    category_id: str
    sku: str = Field(..., min_length=1, max_length=50)
    stock: int = Field(..., ge=0)
    status: ProductStatus = ProductStatus.ACTIVE
    images: List[str] = Field(default_factory=list)
    attributes: Dict[str, str] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @validator('sku')
    def sku_must_be_alphanumeric(cls, v):
        if not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError('SKU 只能包含字母、數字、連字符和下劃線')
        return v.upper()

class Customer(BaseModel):
    id: Optional[str] = None
    email: str = Field(..., regex=r'^[^@]+@[^@]+\.[^@]+$')
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    phone: Optional[str] = Field(None, regex=r'^\+?[\d\s\-\(\)]+$')
    address: Optional[Dict[str, str]] = None
    created_at: Optional[datetime] = None

class OrderItem(BaseModel):
    product_id: str
    quantity: int = Field(..., gt=0)
    unit_price: Decimal = Field(..., gt=0)
    total_price: Optional[Decimal] = None

    def __init__(self, **data):
        super().__init__(**data)
        if self.total_price is None:
            self.total_price = self.unit_price * self.quantity

class Order(BaseModel):
    id: Optional[str] = None
    customer_id: str
    items: List[OrderItem] = Field(..., min_items=1)
    status: OrderStatus = OrderStatus.PENDING
    subtotal: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    shipping: Optional[Decimal] = None
    total: Optional[Decimal] = None
    shipping_address: Dict[str, str]
    billing_address: Optional[Dict[str, str]] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __init__(self, **data):
        super().__init__(**data)
        if self.billing_address is None:
            self.billing_address = self.shipping_address
        self.calculate_totals()

    def calculate_totals(self):
        """計算訂單總額"""
        self.subtotal = sum(item.total_price for item in self.items)
        if self.tax is None:
            self.tax = self.subtotal * Decimal('0.1')  # 10% 稅率
        if self.shipping is None:
            self.shipping = Decimal('10.00')  # 固定運費
        self.total = self.subtotal + self.tax + self.shipping

# 創建 CRUD 系統
from autocrud.crud.core import AutoCRUD
from autocrud.crud.core import (
    CreateRouteTemplate, ReadRouteTemplate, UpdateRouteTemplate,
    DeleteRouteTemplate, ListRouteTemplate, PatchRouteTemplate
)

# 創建不同配置的 CRUD
crud = AutoCRUD(model_naming="kebab")

# 基本 CRUD 模板
basic_templates = [
    CreateRouteTemplate(),
    ReadRouteTemplate(),
    UpdateRouteTemplate(),
    DeleteRouteTemplate(),
    ListRouteTemplate(
        enable_pagination=True,
        default_limit=20,
        max_limit=100,
        enable_sorting=True,
        enable_filtering=True
    )
]

# 添加部分更新模板
patch_template = PatchRouteTemplate()

for template in basic_templates + [patch_template]:
    crud.add_route_template(template)

# 註冊所有模型
crud.add_model(Category)
crud.add_model(Product)
crud.add_model(Customer)
crud.add_model(Order)

# 創建 FastAPI 應用
app = FastAPI(
    title="電商 CRUD API",
    description="使用 AutoCRUD 構建的電商系統 API",
    version="1.0.0"
)

# 應用 CRUD 路由
router = APIRouter()
crud.apply(router, prefix="/api/v1", tags=["電商 API"])
app.include_router(router)

# 添加健康檢查端點
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

API 使用示例：

```bash
# 創建類別
curl -X POST "http://localhost:8000/api/v1/category" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "電子產品",
       "description": "各種電子設備"
     }'

# 創建產品
curl -X POST "http://localhost:8000/api/v1/product" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "iPhone 15",
       "description": "最新的 iPhone",
       "price": "999.00",
       "category_id": "category_id_here",
       "sku": "IPHONE-15",
       "stock": 100
     }'

# 查詢產品 (帶過濾和排序)
curl "http://localhost:8000/api/v1/product?filter=price:gt:500&sort=-created_at&limit=10"

# 創建客戶
curl -X POST "http://localhost:8000/api/v1/customer" \
     -H "Content-Type: application/json" \
     -d '{
       "email": "customer@example.com",
       "first_name": "張",
       "last_name": "三",
       "phone": "+86-138-0000-0000"
     }'

# 創建訂單
curl -X POST "http://localhost:8000/api/v1/order" \
     -H "Content-Type: application/json" \
     -d '{
       "customer_id": "customer_id_here",
       "items": [
         {
           "product_id": "product_id_here",
           "quantity": 2,
           "unit_price": "999.00"
         }
       ],
       "shipping_address": {
         "street": "123 Main St",
         "city": "台北",
         "country": "台灣"
       }
     }'
```

### 4. 博客系統

```python
# blog_example.py
from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime
from enum import Enum

class PostStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"

class Author(BaseModel):
    id: Optional[str] = None
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., regex=r'^[^@]+@[^@]+\.[^@]+$')
    full_name: str = Field(..., min_length=1, max_length=100)
    bio: Optional[str] = Field(None, max_length=500)
    avatar_url: Optional[str] = None
    social_links: Optional[dict] = Field(default_factory=dict)
    created_at: Optional[datetime] = None

class Tag(BaseModel):
    id: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=50)
    slug: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = Field(None, regex=r'^#[0-9A-Fa-f]{6}$')

    @validator('slug', always=True)
    def generate_slug(cls, v, values):
        if v is None and 'name' in values:
            return values['name'].lower().replace(' ', '-')
        return v

class Post(BaseModel):
    id: Optional[str] = None
    title: str = Field(..., min_length=1, max_length=200)
    slug: Optional[str] = None
    content: str = Field(..., min_length=1)
    excerpt: Optional[str] = Field(None, max_length=500)
    author_id: str
    status: PostStatus = PostStatus.DRAFT
    tags: List[str] = Field(default_factory=list)  # Tag IDs
    featured_image: Optional[str] = None
    meta_title: Optional[str] = Field(None, max_length=60)
    meta_description: Optional[str] = Field(None, max_length=160)
    published_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    view_count: int = Field(default=0, ge=0)

    @validator('slug', always=True)
    def generate_slug(cls, v, values):
        if v is None and 'title' in values:
            import re
            slug = re.sub(r'[^\w\s-]', '', values['title'].lower())
            return re.sub(r'[-\s]+', '-', slug)
        return v

    @validator('excerpt', always=True)
    def generate_excerpt(cls, v, values):
        if v is None and 'content' in values:
            content = values['content']
            # 簡單的摘要生成（取前 200 字符）
            return content[:200] + "..." if len(content) > 200 else content
        return v

class Comment(BaseModel):
    id: Optional[str] = None
    post_id: str
    author_name: str = Field(..., min_length=1, max_length=100)
    author_email: str = Field(..., regex=r'^[^@]+@[^@]+\.[^@]+$')
    content: str = Field(..., min_length=1, max_length=1000)
    parent_id: Optional[str] = None  # 用於回覆
    approved: bool = False
    created_at: Optional[datetime] = None

# 設置 CRUD
from autocrud.crud.core import AutoCRUD
from autocrud.crud.core import (
    CreateRouteTemplate, ReadRouteTemplate, UpdateRouteTemplate,
    DeleteRouteTemplate, ListRouteTemplate
)

crud = AutoCRUD(model_naming="kebab")

# 列表模板配置
list_template = ListRouteTemplate(
    enable_pagination=True,
    default_limit=10,
    max_limit=50,
    enable_sorting=True,
    enable_filtering=True,
    enable_field_selection=True
)

templates = [
    CreateRouteTemplate(),
    ReadRouteTemplate(),
    UpdateRouteTemplate(),
    DeleteRouteTemplate(),
    list_template
]

for template in templates:
    crud.add_route_template(template)

# 註冊模型
crud.add_model(Author)
crud.add_model(Tag)
crud.add_model(Post)
crud.add_model(Comment)

# FastAPI 應用
from fastapi import FastAPI, APIRouter

app = FastAPI(title="博客 CRUD API")
router = APIRouter()
crud.apply(router, prefix="/api/v1")
app.include_router(router)
```

## 進階示例

### 5. 多租戶系統

```python
# multi_tenant_example.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Header

class Tenant(BaseModel):
    id: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=100)
    domain: str = Field(..., min_length=1, max_length=100)
    settings: dict = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    is_active: bool = True

class User(BaseModel):
    id: Optional[str] = None
    tenant_id: str  # 重要：每個用戶都屬於一個租戶
    username: str = Field(..., min_length=3, max_length=50)
    email: str
    role: str = "user"
    created_at: Optional[datetime] = None

class Project(BaseModel):
    id: Optional[str] = None
    tenant_id: str  # 重要：每個項目都屬於一個租戶
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    owner_id: str
    members: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None

# 租戶中間件
class TenantMiddleware:
    def __init__(self):
        self.tenant_cache = {}
    
    async def get_current_tenant(self, x_tenant_id: str = Header(None)) -> str:
        """從請求頭獲取租戶 ID"""
        if not x_tenant_id:
            raise HTTPException(status_code=400, detail="缺少租戶 ID")
        return x_tenant_id
    
    async def filter_by_tenant(self, tenant_id: str, filters: dict = None) -> dict:
        """添加租戶過濾"""
        if filters is None:
            filters = {}
        filters['tenant_id'] = tenant_id
        return filters

# 自定義路由模板，自動添加租戶過濾
from autocrud.crud.core import ListRouteTemplate, CreateRouteTemplate

class TenantAwareListTemplate(ListRouteTemplate):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.middleware = TenantMiddleware()
    
    async def list_handler(self, model_type, storage, tenant_id: str = Depends(TenantMiddleware().get_current_tenant), **kwargs):
        # 自動添加租戶過濾
        filters = kwargs.get('filters', {})
        filters = await self.middleware.filter_by_tenant(tenant_id, filters)
        kwargs['filters'] = filters
        return await super().list_handler(model_type, storage, **kwargs)

class TenantAwareCreateTemplate(CreateRouteTemplate):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.middleware = TenantMiddleware()
    
    async def create_handler(self, data, model_type, storage, tenant_id: str = Depends(TenantMiddleware().get_current_tenant)):
        # 自動添加租戶 ID
        data['tenant_id'] = tenant_id
        return await super().create_handler(data, model_type, storage)

# 設置 CRUD
crud = AutoCRUD(model_naming="kebab")

# 使用租戶感知的模板
crud.add_route_template(TenantAwareCreateTemplate())
crud.add_route_template(ReadRouteTemplate())
crud.add_route_template(UpdateRouteTemplate())
crud.add_route_template(DeleteRouteTemplate())
crud.add_route_template(TenantAwareListTemplate())

# 註冊模型
crud.add_model(Tenant)  # 租戶本身不需要租戶過濾
crud.add_model(User)
crud.add_model(Project)

app = FastAPI(title="多租戶 CRUD API")
router = APIRouter()
crud.apply(router, prefix="/api/v1")
app.include_router(router)
```

### 6. 高級版本控制

```python
# versioning_example.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class ChangeType(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    RESTORE = "restore"

class DocumentVersion(BaseModel):
    id: Optional[str] = None
    document_id: str
    version_number: int
    content: Dict[str, Any]
    change_type: ChangeType
    changed_by: str
    change_summary: Optional[str] = None
    created_at: Optional[datetime] = None

class Document(BaseModel):
    id: Optional[str] = None
    title: str = Field(..., min_length=1, max_length=200)
    content: Dict[str, Any] = Field(default_factory=dict)
    current_version: int = 1
    created_by: str
    updated_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None

# 版本控制模板
from autocrud.crud.core import BaseRouteTemplate
from fastapi import APIRouter

class VersioningRouteTemplate(BaseRouteTemplate):
    def __init__(self):
        super().__init__(path="/{id}/versions", methods=["GET"])
    
    async def get_versions_handler(self, id: str, model_type, storage):
        """獲取文檔的所有版本"""
        versions = await storage.list(
            DocumentVersion,
            filters={"document_id": id},
            sort=["-version_number"]
        )
        return {"versions": versions[0], "total": versions[1]}

class SwitchVersionTemplate(BaseRouteTemplate):
    def __init__(self):
        super().__init__(path="/{id}/switch/{version_id}", methods=["POST"])
    
    async def switch_version_handler(self, id: str, version_id: str, model_type, storage):
        """切換到指定版本"""
        # 獲取目標版本
        version = await storage.read(DocumentVersion, version_id)
        if not version or version['document_id'] != id:
            raise HTTPException(status_code=404, detail="版本未找到")
        
        # 獲取當前文檔
        document = await storage.read(model_type, id)
        if not document:
            raise HTTPException(status_code=404, detail="文檔未找到")
        
        # 創建新版本記錄（當前狀態）
        current_version = DocumentVersion(
            document_id=id,
            version_number=document['current_version'] + 1,
            content=document['content'],
            change_type=ChangeType.UPDATE,
            changed_by="system",  # 實際應用中從上下文獲取
            change_summary=f"切換到版本 {version['version_number']}"
        )
        await storage.create(DocumentVersion, current_version.dict())
        
        # 更新文檔內容
        updated_document = document.copy()
        updated_document['content'] = version['content']
        updated_document['current_version'] = document['current_version'] + 1
        updated_document['updated_at'] = datetime.now()
        
        await storage.update(model_type, id, updated_document)
        return updated_document

class RestoreTemplate(BaseRouteTemplate):
    def __init__(self):
        super().__init__(path="/{id}/restore", methods=["POST"])
    
    async def restore_handler(self, id: str, model_type, storage):
        """恢復已刪除的文檔"""
        document = await storage.read(model_type, id)
        if not document:
            raise HTTPException(status_code=404, detail="文檔未找到")
        
        if not document['is_deleted']:
            raise HTTPException(status_code=400, detail="文檔未被刪除")
        
        # 恢復文檔
        document['is_deleted'] = False
        document['deleted_at'] = None
        document['updated_at'] = datetime.now()
        document['current_version'] += 1
        
        # 記錄版本
        version = DocumentVersion(
            document_id=id,
            version_number=document['current_version'],
            content=document['content'],
            change_type=ChangeType.RESTORE,
            changed_by="system",
            change_summary="文檔恢復"
        )
        await storage.create(DocumentVersion, version.dict())
        
        await storage.update(model_type, id, document)
        return document

# 自定義 CRUD 模板，自動處理版本控制
class VersionedUpdateTemplate(UpdateRouteTemplate):
    async def update_handler(self, id: str, data: dict, model_type, storage, **kwargs):
        # 獲取當前文檔
        current = await storage.read(model_type, id)
        if not current:
            raise HTTPException(status_code=404, detail="文檔未找到")
        
        # 創建版本記錄
        version = DocumentVersion(
            document_id=id,
            version_number=current.get('current_version', 1) + 1,
            content=current.get('content', {}),
            change_type=ChangeType.UPDATE,
            changed_by=data.get('updated_by', 'anonymous'),
            change_summary=data.get('change_summary', '更新文檔')
        )
        await storage.create(DocumentVersion, version.dict())
        
        # 更新文檔
        data['current_version'] = current.get('current_version', 1) + 1
        data['updated_at'] = datetime.now()
        
        return await super().update_handler(id, data, model_type, storage, **kwargs)

class VersionedDeleteTemplate(DeleteRouteTemplate):
    def __init__(self):
        super().__init__(enable_soft_delete=True)
    
    async def delete_handler(self, id: str, model_type, storage, **kwargs):
        # 軟刪除
        document = await storage.read(model_type, id)
        if not document:
            raise HTTPException(status_code=404, detail="文檔未找到")
        
        # 創建刪除版本記錄
        version = DocumentVersion(
            document_id=id,
            version_number=document.get('current_version', 1) + 1,
            content=document.get('content', {}),
            change_type=ChangeType.DELETE,
            changed_by="system",
            change_summary="文檔刪除"
        )
        await storage.create(DocumentVersion, version.dict())
        
        # 標記為已刪除
        document['is_deleted'] = True
        document['deleted_at'] = datetime.now()
        document['current_version'] += 1
        
        await storage.update(model_type, id, document)
        return None

# 設置 CRUD
crud = AutoCRUD(model_naming="kebab")

# 添加標準模板
crud.add_route_template(CreateRouteTemplate())
crud.add_route_template(ReadRouteTemplate())
crud.add_route_template(VersionedUpdateTemplate())
crud.add_route_template(VersionedDeleteTemplate())
crud.add_route_template(ListRouteTemplate())

# 添加版本控制模板
crud.add_route_template(VersioningRouteTemplate())
crud.add_route_template(SwitchVersionTemplate())
crud.add_route_template(RestoreTemplate())

# 註冊模型
crud.add_model(Document)
crud.add_model(DocumentVersion)

app = FastAPI(title="版本控制 CRUD API")
router = APIRouter()
crud.apply(router, prefix="/api/v1")
app.include_router(router)

# 現在 API 支持：
# POST /document - 創建文檔
# GET /document/{id} - 獲取文檔
# PUT /document/{id} - 更新文檔 (自動創建版本)
# DELETE /document/{id} - 軟刪除文檔
# GET /document - 列出文檔
# GET /document/{id}/versions - 獲取文檔版本歷史
# POST /document/{id}/switch/{version_id} - 切換版本  
# POST /document/{id}/restore - 恢復已刪除文檔
```

## 部署示例

### 7. Docker 部署

```python
# main.py
from fastapi import FastAPI, APIRouter
from pydantic import BaseModel
from autocrud.crud.core import AutoCRUD, CreateRouteTemplate, ReadRouteTemplate

class Item(BaseModel):
    name: str
    description: str

crud = AutoCRUD()
crud.add_route_template(CreateRouteTemplate())
crud.add_route_template(ReadRouteTemplate())
crud.add_model(Item)

app = FastAPI()
router = APIRouter()
crud.apply(router)
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY main.py .

EXPOSE 8000

CMD ["python", "main.py"]
```

```txt
# requirements.txt
autocrud
fastapi
uvicorn[standard]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ENVIRONMENT=production
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    restart: unless-stopped

  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: autocrud
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

volumes:
  postgres_data:
```

### 8. 環境配置

```python
import os
from typing import Dict, Any

def get_config() -> Dict[str, Any]:
    """根據環境獲取配置"""
    env = os.getenv("ENVIRONMENT", "development")
    
    configs = {
        "development": {
            "model_naming": "kebab",
            "debug": True,
            "title": "Development API"
        },
        "production": {
            "model_naming": "snake", 
            "debug": False,
            "title": "Production API"
        }
    }
    
    return configs.get(env, configs["development"])

def create_app():
    config = get_config()
    
    crud = AutoCRUD(model_naming=config["model_naming"])
    # ... 添加路由模板和模型
    
    app = FastAPI(
        title=config["title"],
        debug=config["debug"]
    )
    
    router = APIRouter()
    crud.apply(router)
    app.include_router(router)
    
    return app

app = create_app()
```

### 9. Kubernetes 部署

```yaml
# k8s-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: autocrud-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: autocrud-api
  template:
    metadata:
      labels:
        app: autocrud-api
    spec:
      containers:
      - name: api
        image: autocrud-api:latest
        ports:
        - containerPort: 8000
        env:
        - name: ENVIRONMENT
          value: "production"
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: url
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"

---
apiVersion: v1
kind: Service
metadata:
  name: autocrud-api-service
spec:
  selector:
    app: autocrud-api
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
  type: LoadBalancer
```

## 性能優化示例

### 10. 高性能配置

```python
# high_performance_example.py
from autocrud.crud.core import AutoCRUD
from autocrud.storage import DatabaseStorage, RedisCache
from autocrud.serializers import MsgspecSerializer
import msgspec
from typing import Optional

# 使用 msgspec 的高性能模型
class User(msgspec.Struct):
    id: Optional[str] = None
    username: str
    email: str
    age: int

# 配置高性能存儲
storage = DatabaseStorage(
    url="postgresql://user:pass@localhost/db",
    pool_size=50,           # 大連接池
    max_overflow=100,       # 允許更多溢出連接
    pool_timeout=30,
    pool_recycle=3600,
    pool_pre_ping=True
)

# 配置 Redis 緩存
cache = RedisCache(
    url="redis://localhost:6379/0",
    pool_size=20,
    default_ttl=1800,       # 30分鐘緩存
    enable_compression=True  # 啟用壓縮節省內存
)

# 使用高性能序列化器
serializer = MsgspecSerializer()

# 創建優化的 CRUD
crud = AutoCRUD(
    model_naming="kebab",
    storage=storage,
    cache=cache,
    serializer=serializer
)

# 優化的列表模板
from autocrud.crud.core import ListRouteTemplate

list_template = ListRouteTemplate(
    enable_pagination=True,
    default_limit=50,       # 更大的默認頁面
    max_limit=200,          # 允許更大的頁面
    enable_caching=True,    # 啟用查詢緩存
    cache_ttl=600          # 10分鐘查詢緩存
)

# 添加模板
crud.add_route_template(CreateRouteTemplate())
crud.add_route_template(ReadRouteTemplate())
crud.add_route_template(UpdateRouteTemplate())
crud.add_route_template(DeleteRouteTemplate())
crud.add_route_template(list_template)

crud.add_model(User)

# FastAPI 應用配置
from fastapi import FastAPI

app = FastAPI(
    title="高性能 CRUD API",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 添加中間件
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 應用 CRUD
from fastapi import APIRouter
router = APIRouter()
crud.apply(router, prefix="/api/v1")
app.include_router(router)

# 添加性能監控
@app.middleware("http")
async def add_process_time_header(request, call_next):
    import time
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000,
        workers=4,              # 多進程
        access_log=False,       # 關閉訪問日誌提升性能
        use_colors=False
    )
```

這些示例涵蓋了從基礎到高級的各種使用場景。您可以根據具體需求選擇合適的模式和配置。

## 測試示例

### 11. 單元測試

```python
# test_crud.py
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from autocrud.crud.core import AutoCRUD, CreateRouteTemplate, ReadRouteTemplate
from fastapi import FastAPI, APIRouter

class TestUser(BaseModel):
    name: str
    email: str

@pytest.fixture
def app():
    crud = AutoCRUD()
    crud.add_route_template(CreateRouteTemplate())
    crud.add_route_template(ReadRouteTemplate())
    crud.add_model(TestUser)
    
    app = FastAPI()
    router = APIRouter()
    crud.apply(router)
    app.include_router(router)
    
    return app

@pytest.fixture
def client(app):
    return TestClient(app)

def test_create_user(client):
    response = client.post("/test-user", json={
        "name": "Test User",
        "email": "test@example.com"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test User"
    assert "id" in data

def test_read_user(client):
    # 先創建用戶
    create_response = client.post("/test-user", json={
        "name": "Test User",
        "email": "test@example.com"
    })
    user_id = create_response.json()["id"]
    
    # 然後讀取
    response = client.get(f"/test-user/{user_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test User"
```

### 12. 集成測試

```python
# test_integration.py
import pytest
import asyncio
from autocrud.crud.core import AutoCRUD
from autocrud.storage import MemoryStorage

@pytest.mark.asyncio
async def test_full_crud_cycle():
    storage = MemoryStorage()
    crud = AutoCRUD(storage=storage)
    
    # 測試數據
    user_data = {"name": "Integration Test", "email": "test@example.com"}
    
    # 創建
    user_id = await storage.create(TestUser, user_data)
    assert user_id is not None
    
    # 讀取
    user = await storage.read(TestUser, user_id)
    assert user["name"] == user_data["name"]
    
    # 更新
    updated_data = {"name": "Updated User", "email": "updated@example.com"}
    updated_user = await storage.update(TestUser, user_id, updated_data)
    assert updated_user["name"] == "Updated User"
    
    # 刪除
    deleted = await storage.delete(TestUser, user_id)
    assert deleted is True
    
    # 驗證已刪除
    user = await storage.read(TestUser, user_id)
    assert user is None
```

這個完整的示例集合展示了 AutoCRUD 在各種實際場景中的應用，從簡單的 CRUD 操作到複雜的企業級功能。
