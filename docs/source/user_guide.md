# 📖 用戶指南

本指南將深入介紹 AutoCRUD 的所有功能和配置選項，幫助您充分利用這個強大的工具。

## 核心概念

### AutoCRUD 架構

AutoCRUD 基於以下核心組件：

```mermaid
graph TB
    A[AutoCRUD] --> B[路由模板]
    A --> C[模型註冊]
    A --> D[存儲後端]
    A --> E[序列化器]
    
    B --> B1[CreateRouteTemplate]
    B --> B2[ReadRouteTemplate]
    B --> B3[UpdateRouteTemplate]
    B --> B4[DeleteRouteTemplate]
    B --> B5[ListRouteTemplate]
    
    C --> C1[Pydantic模型]
    C --> C2[TypedDict]
    C --> C3[dataclass]
    C --> C4[msgspec.Struct]
    
    D --> D1[內存存儲]
    D --> D2[文件存儲]
    D --> D3[數據庫存儲]
    
    E --> E1[JSON序列化]
    E --> E2[msgspec序列化]
```

### 路由模板系統

路由模板定義了 CRUD 操作的行為：

```python
from autocrud.crud.core import (
    AutoCRUD,
    CreateRouteTemplate,    # POST   /model
    ReadRouteTemplate,      # GET    /model/{id}
    UpdateRouteTemplate,    # PUT    /model/{id}
    DeleteRouteTemplate,    # DELETE /model/{id}
    ListRouteTemplate,      # GET    /model
    PatchRouteTemplate,     # PATCH  /model/{id}
)

crud = AutoCRUD()

# 添加基本 CRUD 操作
crud.add_route_template(CreateRouteTemplate())
crud.add_route_template(ReadRouteTemplate())
crud.add_route_template(UpdateRouteTemplate())
crud.add_route_template(DeleteRouteTemplate())
crud.add_route_template(ListRouteTemplate())
```

## 支持的數據類型

### 1. Pydantic BaseModel (推薦)

```python
from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime

class User(BaseModel):
    id: Optional[str] = None
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., regex=r'^[^@]+@[^@]+\.[^@]+$')
    age: Optional[int] = Field(None, ge=0, le=150)
    created_at: Optional[datetime] = None
    is_active: bool = True

    @validator('username')
    def username_alphanumeric(cls, v):
        assert v.isalnum(), '用戶名只能包含字母和數字'
        return v

    class Config:
        # 示例數據
        schema_extra = {
            "example": {
                "username": "johndoe",
                "email": "john@example.com",
                "age": 25
            }
        }
```

### 2. TypedDict (輕量級)

```python
from typing import TypedDict, Optional

class Product(TypedDict):
    id: Optional[str]
    name: str
    price: float
    category: str
    in_stock: bool
    tags: list[str]

# 使用註解添加額外信息
class ProductMeta:
    """產品元數據"""
    
    @staticmethod
    def validate_price(price: float) -> float:
        if price < 0:
            raise ValueError("價格不能為負數")
        return price
```

### 3. dataclass (Python 原生)

```python
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

@dataclass
class Order:
    id: Optional[str] = None
    customer_id: str = ""
    items: List[dict] = field(default_factory=list)
    total: float = 0.0
    status: str = "pending"
    created_at: Optional[datetime] = None
    notes: Optional[str] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        
        # 計算總價
        if self.items and self.total == 0.0:
            self.total = sum(item.get('price', 0) * item.get('quantity', 1) 
                           for item in self.items)
```

### 4. msgspec.Struct (高性能)

```python
import msgspec
from typing import Optional

class Event(msgspec.Struct):
    id: Optional[str] = None
    type: str
    data: dict
    timestamp: float
    source: str = "system"
    priority: int = 1

    def __post_init__(self):
        # msgspec 不支持 __post_init__，使用工廠函數
        pass

def create_event(type: str, data: dict, **kwargs) -> Event:
    """事件工廠函數"""
    import time
    return Event(
        type=type,
        data=data,
        timestamp=kwargs.get('timestamp', time.time()),
        **{k: v for k, v in kwargs.items() if k != 'timestamp'}
    )
```

## 配置選項

### 命名約定

```python
# 1. kebab-case (推薦)
crud = AutoCRUD(model_naming="kebab")
# UserProfile -> /user-profile
# OrderItem -> /order-item

# 2. snake_case
crud = AutoCRUD(model_naming="snake")
# UserProfile -> /user_profile
# OrderItem -> /order_item

# 3. 保持原名
crud = AutoCRUD(model_naming="preserve")
# UserProfile -> /UserProfile
# OrderItem -> /OrderItem

# 4. 小寫
crud = AutoCRUD(model_naming="lower")
# UserProfile -> /userprofile
# OrderItem -> /orderitem

# 5. 自定義函數
def api_naming(model_type):
    """自定義 API 路徑命名"""
    name = model_type.__name__
    # 添加 api 前綴
    return f"api/{name.lower()}"

crud = AutoCRUD(model_naming=api_naming)
# User -> /api/user
# OrderItem -> /api/orderitem
```

### 路由配置

```python
from autocrud.crud.core import RouteConfig

# 基本路由配置
config = RouteConfig(
    prefix="/api/v1",           # 路由前綴
    tags=["CRUD API"],          # OpenAPI 標籤
    include_in_schema=True,     # 包含在 OpenAPI schema 中
    responses={
        404: {"description": "資源未找到"},
        422: {"description": "驗證錯誤"},
    }
)

crud = AutoCRUD(route_config=config)
```

### 高級路由模板配置

```python
from autocrud.crud.core import CreateRouteTemplate, ListRouteTemplate

# 自定義創建模板
create_template = CreateRouteTemplate(
    path="/",                    # 自定義路徑
    methods=["POST"],           # HTTP 方法
    status_code=201,            # 成功狀態碼
    response_model=None,        # 響應模型
    summary="創建新資源",        # OpenAPI 摘要
    description="創建一個新的資源實例"  # OpenAPI 描述
)

# 自定義列表模板 (支持分頁)
list_template = ListRouteTemplate(
    enable_pagination=True,     # 啟用分頁
    default_limit=20,          # 默認每頁數量
    max_limit=100,             # 最大每頁數量
    enable_sorting=True,       # 啟用排序
    enable_filtering=True,     # 啟用過濾
)

crud.add_route_template(create_template)
crud.add_route_template(list_template)
```

## 高級功能

### 1. 分頁查詢

```python
from autocrud.crud.core import ListRouteTemplate

# 配置分頁
list_template = ListRouteTemplate(
    enable_pagination=True,
    default_limit=20,
    max_limit=100
)

crud.add_route_template(list_template)
crud.add_model(User)
```

API 使用：
```bash
# 基本分頁
GET /user?limit=10&offset=0

# 獲取第二頁
GET /user?limit=10&offset=10

# 獲取特定頁面
GET /user?page=2&limit=20
```

響應格式：
```json
{
  "items": [...],
  "total": 150,
  "limit": 20,
  "offset": 0,
  "page": 1,
  "total_pages": 8
}
```

### 2. 排序功能

```python
# 啟用排序
list_template = ListRouteTemplate(
    enable_sorting=True,
    default_sort=["created_at"],      # 默認排序字段
    allowed_sort_fields=["name", "email", "created_at"]  # 允許的排序字段
)
```

API 使用：
```bash
# 按名稱升序
GET /user?sort=name

# 按名稱降序
GET /user?sort=-name

# 多字段排序
GET /user?sort=name,-created_at

# 複雜排序
GET /user?sort=status,name,-created_at
```

### 3. 過濾查詢

```python
from autocrud.crud.core import FilterConfig

filter_config = FilterConfig(
    allowed_fields=["name", "email", "age", "is_active"],
    operators=["eq", "ne", "gt", "lt", "ge", "le", "in", "like"]
)

list_template = ListRouteTemplate(
    enable_filtering=True,
    filter_config=filter_config
)
```

API 使用：
```bash
# 等於查詢
GET /user?filter=name:eq:john

# 大於查詢
GET /user?filter=age:gt:18

# 包含查詢
GET /user?filter=name:like:john

# 多條件查詢
GET /user?filter=age:gt:18&filter=is_active:eq:true

# IN 查詢
GET /user?filter=status:in:active,pending
```

### 4. 字段選擇

```python
list_template = ListRouteTemplate(
    enable_field_selection=True,
    default_fields=["id", "name", "email"],  # 默認返回字段
    allowed_fields=["id", "name", "email", "age", "created_at"]
)
```

API 使用：
```bash
# 選擇特定字段
GET /user?fields=id,name,email

# 排除字段
GET /user?exclude=password,secret_key

# 包含所有字段
GET /user?fields=*
```

### 5. 批量操作

```python
from autocrud.crud.core import BatchRouteTemplate

batch_template = BatchRouteTemplate(
    max_batch_size=100,        # 最大批量大小
    enable_transaction=True,   # 啟用事務
)

crud.add_route_template(batch_template)
```

API 使用：
```bash
# 批量創建
POST /user/batch
[
  {"name": "user1", "email": "user1@example.com"},
  {"name": "user2", "email": "user2@example.com"}
]

# 批量更新
PUT /user/batch
[
  {"id": "1", "name": "updated1"},
  {"id": "2", "name": "updated2"}
]

# 批量刪除
DELETE /user/batch?ids=1,2,3
```

## 存儲後端

### 1. 內存存儲 (默認)

```python
from autocrud.storage import MemoryStorage

storage = MemoryStorage(
    max_size=10000,           # 最大存儲條目數
    enable_persistence=True,   # 啟用持久化
    persistence_file="data.json"  # 持久化文件
)

crud = AutoCRUD(storage=storage)
```

### 2. 文件存儲

```python
from autocrud.storage import FileStorage

storage = FileStorage(
    base_path="./data",       # 基礎路徑
    file_format="json",       # 文件格式: json, yaml, pickle
    enable_compression=True,   # 啟用壓縮
    backup_enabled=True,      # 啟用備份
    max_backups=5            # 最大備份數量
)

crud = AutoCRUD(storage=storage)
```

### 3. 數據庫存儲

```python
from autocrud.storage import DatabaseStorage

# PostgreSQL
storage = DatabaseStorage(
    url="postgresql://user:password@localhost/dbname",
    table_prefix="autocrud_",
    enable_migrations=True
)

# MySQL
storage = DatabaseStorage(
    url="mysql://user:password@localhost/dbname",
    table_prefix="autocrud_",
    pool_size=10
)

# SQLite
storage = DatabaseStorage(
    url="sqlite:///./autocrud.db",
    enable_wal=True          # 啟用 WAL 模式
)

crud = AutoCRUD(storage=storage)
```

### 4. Redis 存儲

```python
from autocrud.storage import RedisStorage

storage = RedisStorage(
    url="redis://localhost:6379/0",
    key_prefix="autocrud:",
    enable_clustering=True,   # 啟用集群模式
    serializer="msgspec"      # 序列化器: json, pickle, msgspec
)

crud = AutoCRUD(storage=storage)
```

## 自定義序列化

### JSON 序列化器

```python
from autocrud.serializers import JSONSerializer
import json
from decimal import Decimal

class CustomJSONSerializer(JSONSerializer):
    def dumps(self, obj):
        def default(o):
            if isinstance(o, Decimal):
                return float(o)
            if hasattr(o, 'isoformat'):
                return o.isoformat()
            return str(o)
        
        return json.dumps(obj, default=default, ensure_ascii=False)
    
    def loads(self, data):
        return json.loads(data)

crud = AutoCRUD(serializer=CustomJSONSerializer())
```

### msgspec 序列化器

```python
from autocrud.serializers import MsgspecSerializer

serializer = MsgspecSerializer(
    enc_hook=lambda obj: obj.isoformat() if hasattr(obj, 'isoformat') else None,
    dec_hook=lambda type, obj: type(obj) if type else obj
)

crud = AutoCRUD(serializer=serializer)
```

## 中間件和鈎子

### 請求中間件

```python
from autocrud.middleware import RequestMiddleware

class LoggingMiddleware(RequestMiddleware):
    async def before_request(self, request, model_type):
        print(f"請求開始: {request.method} {request.url}")
        return request
    
    async def after_request(self, response, model_type):
        print(f"請求完成: {response.status_code}")
        return response

crud.add_middleware(LoggingMiddleware())
```

### 驗證鈎子

```python
from autocrud.hooks import ValidationHook

class UserValidationHook(ValidationHook):
    async def before_create(self, data, model_type):
        # 創建前驗證
        if model_type.__name__ == 'User':
            if 'email' in data:
                # 檢查 email 是否已存在
                existing = await self.storage.find_one(
                    model_type, {'email': data['email']}
                )
                if existing:
                    raise ValueError("電子郵件已存在")
        return data
    
    async def before_update(self, id, data, model_type):
        # 更新前驗證
        return data

crud.add_hook(UserValidationHook())
```

### 審計鈎子

```python
from autocrud.hooks import AuditHook
from datetime import datetime

class AuditTrailHook(AuditHook):
    async def after_create(self, id, data, result, model_type):
        await self.log_action("CREATE", model_type, id, data)
    
    async def after_update(self, id, data, result, model_type):
        await self.log_action("UPDATE", model_type, id, data)
    
    async def after_delete(self, id, model_type):
        await self.log_action("DELETE", model_type, id, None)
    
    async def log_action(self, action, model_type, id, data):
        audit_log = {
            "action": action,
            "model": model_type.__name__,
            "record_id": id,
            "data": data,
            "timestamp": datetime.now().isoformat(),
            "user": self.get_current_user()  # 從上下文獲取用戶
        }
        # 保存到審計日誌存儲
        await self.audit_storage.save(audit_log)

crud.add_hook(AuditTrailHook())
```

## 權限控制

### 基於角色的訪問控制 (RBAC)

```python
from autocrud.auth import RBACMiddleware, Permission

class UserRBACMiddleware(RBACMiddleware):
    def get_user_roles(self, request):
        # 從 JWT token 或 session 獲取用戶角色
        token = request.headers.get("Authorization")
        user = self.decode_token(token)
        return user.get("roles", [])
    
    def check_permission(self, roles, permission, model_type, record_id=None):
        model_name = model_type.__name__.lower()
        
        # 管理員可以訪問所有資源
        if "admin" in roles:
            return True
        
        # 用戶只能訪問自己的記錄
        if model_name == "user" and permission in [Permission.READ, Permission.UPDATE]:
            current_user_id = self.get_current_user_id()
            return record_id == current_user_id
        
        # 其他權限規則
        permission_map = {
            "user": {
                Permission.CREATE: ["manager", "admin"],
                Permission.READ: ["user", "manager", "admin"],
                Permission.UPDATE: ["manager", "admin"],
                Permission.DELETE: ["admin"],
            }
        }
        
        allowed_roles = permission_map.get(model_name, {}).get(permission, [])
        return any(role in roles for role in allowed_roles)

crud.add_middleware(UserRBACMiddleware())
```

### API 金鑰認證

```python
from autocrud.auth import APIKeyMiddleware

class CustomAPIKeyMiddleware(APIKeyMiddleware):
    def __init__(self):
        self.valid_keys = {
            "api_key_1": {"name": "服務A", "permissions": ["read"]},
            "api_key_2": {"name": "服務B", "permissions": ["read", "write"]},
            "admin_key": {"name": "管理員", "permissions": ["admin"]},
        }
    
    def validate_api_key(self, api_key):
        return api_key in self.valid_keys
    
    def get_key_permissions(self, api_key):
        return self.valid_keys.get(api_key, {}).get("permissions", [])

crud.add_middleware(CustomAPIKeyMiddleware())
```

## 性能優化

### 緩存策略

```python
from autocrud.cache import RedisCache, MemoryCache

# Redis 緩存
cache = RedisCache(
    url="redis://localhost:6379/1",
    default_ttl=3600,          # 默認過期時間 (秒)
    key_prefix="cache:",
    enable_compression=True
)

# 內存緩存
cache = MemoryCache(
    max_size=1000,            # 最大緩存條目數
    default_ttl=300,          # 默認過期時間
    cleanup_interval=60       # 清理間隔
)

crud = AutoCRUD(cache=cache)
```

### 連接池配置

```python
from autocrud.storage import DatabaseStorage

storage = DatabaseStorage(
    url="postgresql://user:password@localhost/dbname",
    pool_size=20,             # 連接池大小
    max_overflow=30,          # 最大溢出連接數
    pool_timeout=30,          # 連接超時時間
    pool_recycle=3600,        # 連接回收時間
    pool_pre_ping=True        # 連接預檢
)

crud = AutoCRUD(storage=storage)
```

### 異步處理

```python
from autocrud.async_support import AsyncCRUD

# 創建異步 CRUD 實例
crud = AsyncCRUD(
    enable_async=True,
    max_concurrent=100,       # 最大並發請求數
    request_timeout=30        # 請求超時時間
)

# 使用異步路由模板
from autocrud.async_support import AsyncCreateRouteTemplate

crud.add_route_template(AsyncCreateRouteTemplate())
```

## 監控和日誌

### 指標收集

```python
from autocrud.monitoring import MetricsCollector

metrics = MetricsCollector(
    enable_prometheus=True,   # 啟用 Prometheus 指標
    metrics_path="/metrics",  # 指標端點路徑
    collect_request_time=True,  # 收集請求時間
    collect_error_rate=True,    # 收集錯誤率
)

crud = AutoCRUD(metrics=metrics)
```

### 結構化日誌

```python
import logging
from autocrud.logging import StructuredLogger

# 配置結構化日誌
logger = StructuredLogger(
    level=logging.INFO,
    format="json",            # 日誌格式: json, text
    include_request_id=True,  # 包含請求 ID
    include_user_id=True,     # 包含用戶 ID
)

crud = AutoCRUD(logger=logger)
```

## 測試支持

### 測試配置

```python
# test_config.py
from autocrud.testing import TestCRUD, MockStorage

def create_test_crud():
    """創建測試用的 CRUD 實例"""
    storage = MockStorage()  # 使用模擬存儲
    
    crud = TestCRUD(
        storage=storage,
        enable_validation=True,   # 啟用測試驗證
        raise_on_error=True      # 遇到錯誤時拋出異常
    )
    
    return crud, storage
```

### 單元測試

```python
# test_user_api.py
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

class User(BaseModel):
    name: str
    email: str

def test_user_crud():
    crud, storage = create_test_crud()
    crud.add_model(User)
    
    app = FastAPI()
    router = APIRouter()
    crud.apply(router)
    app.include_router(router)
    
    client = TestClient(app)
    
    # 測試創建用戶
    response = client.post("/user", json={
        "name": "測試用戶",
        "email": "test@example.com"
    })
    assert response.status_code == 201
    user_data = response.json()
    user_id = user_data["id"]
    
    # 測試獲取用戶
    response = client.get(f"/user/{user_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "測試用戶"
    
    # 測試更新用戶
    response = client.put(f"/user/{user_id}", json={
        "name": "更新的用戶",
        "email": "updated@example.com"
    })
    assert response.status_code == 200
    
    # 測試刪除用戶
    response = client.delete(f"/user/{user_id}")
    assert response.status_code == 204
```

### 集成測試

```python
# test_integration.py
import pytest
from autocrud.testing import IntegrationTestSuite

class TestUserIntegration(IntegrationTestSuite):
    def setup_method(self):
        self.crud = self.create_crud_with_real_storage()
        self.crud.add_model(User)
    
    async def test_full_crud_cycle(self):
        # 測試完整的 CRUD 生命周期
        user_data = {"name": "集成測試", "email": "integration@test.com"}
        
        # 創建
        created = await self.crud.create(User, user_data)
        assert created["name"] == user_data["name"]
        
        # 讀取
        read = await self.crud.read(User, created["id"])
        assert read["email"] == user_data["email"]
        
        # 更新
        updated = await self.crud.update(User, created["id"], {"name": "更新後"})
        assert updated["name"] == "更新後"
        
        # 刪除
        await self.crud.delete(User, created["id"])
        
        # 驗證已刪除
        with pytest.raises(NotFoundError):
            await self.crud.read(User, created["id"])
```

## 最佳實踐

### 1. 模型設計

```python
# 好的實踐
class User(BaseModel):
    id: Optional[str] = None          # 可選 ID
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., regex=r'^[^@]+@[^@]+\.[^@]+$')
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        # 提供示例數據
        schema_extra = {
            "example": {
                "username": "johndoe",
                "email": "john@example.com"
            }
        }

# 避免的實踐
class BadUser(BaseModel):
    data: dict  # 過於泛化
    info: Any   # 缺乏類型信息
```

### 2. 錯誤處理

```python
from autocrud.exceptions import ValidationError, NotFoundError
from fastapi import HTTPException

class CustomErrorHandler:
    async def handle_validation_error(self, error: ValidationError):
        return HTTPException(
            status_code=422,
            detail={
                "error": "驗證失敗",
                "field_errors": error.field_errors,
                "message": str(error)
            }
        )
    
    async def handle_not_found_error(self, error: NotFoundError):
        return HTTPException(
            status_code=404,
            detail={
                "error": "資源未找到",
                "resource_type": error.resource_type,
                "resource_id": error.resource_id
            }
        )

crud.set_error_handler(CustomErrorHandler())
```

### 3. 安全配置

```python
from autocrud.security import SecurityConfig

security = SecurityConfig(
    # CORS 設置
    cors_enabled=True,
    cors_origins=["https://yourdomain.com"],
    cors_methods=["GET", "POST", "PUT", "DELETE"],
    
    # 速率限制
    rate_limiting_enabled=True,
    rate_limit="100/minute",
    
    # 請求大小限制
    max_request_size=1024 * 1024,  # 1MB
    
    # 安全頭
    security_headers=True
)

crud = AutoCRUD(security=security)
```

### 4. 環境配置

```python
import os

def create_app():
    # 根據環境調整配置
    environment = os.getenv("ENVIRONMENT", "development")
    
    if environment == "production":
        crud = AutoCRUD(
            model_naming="kebab",
            enable_cache=True,
            cache_ttl=3600,
            enable_compression=True,
            log_level="WARNING"
        )
    else:
        crud = AutoCRUD(
            model_naming="kebab", 
            enable_cache=False,
            log_level="DEBUG",
            enable_debug_mode=True
        )
    
    return crud
```

## 故障排除

### 常見問題

#### 1. 模型註冊失敗

**問題**: `ModelRegistrationError: 無法註冊模型`

**解決方案**:
```python
# 檢查模型是否有必要的類型註解
class User(BaseModel):
    name: str  # ✓ 正確
    # name     # ✗ 錯誤：缺少類型註解

# 檢查是否有循環依賴
# 使用 forward reference
from __future__ import annotations
```

#### 2. 序列化錯誤

**問題**: `SerializationError: 無法序列化對象`

**解決方案**:
```python
# 自定義序列化器處理特殊類型
class CustomSerializer(JSONSerializer):
    def dumps(self, obj):
        def default(o):
            if isinstance(o, datetime):
                return o.isoformat()
            if isinstance(o, Decimal):
                return float(o)
            return str(o)
        return json.dumps(obj, default=default)
```

#### 3. 性能問題

**問題**: API 響應慢

**解決方案**:
```python
# 啟用緩存
crud = AutoCRUD(
    enable_cache=True,
    cache_ttl=300
)

# 添加數據庫索引
# 在數據庫中為常查詢字段添加索引

# 啟用連接池
storage = DatabaseStorage(
    url="postgresql://...",
    pool_size=20
)
```

#### 4. 內存使用過高

**問題**: 應用內存持續增長

**解決方案**:
```python
# 限制內存緩存大小
cache = MemoryCache(max_size=1000)

# 啟用定期清理
crud = AutoCRUD(
    enable_gc=True,
    gc_interval=300  # 5分鐘清理一次
)

# 使用流式處理大量數據
list_template = ListRouteTemplate(
    enable_streaming=True,
    stream_chunk_size=100
)
```

### 調試技巧

```python
# 啟用調試模式
crud = AutoCRUD(debug=True)

# 添加詳細日誌
import logging
logging.basicConfig(level=logging.DEBUG)

# 檢查註冊的模型
print("已註冊的模型:", crud.get_registered_models())

# 檢查路由
print("已註冊的路由:", crud.get_registered_routes())

# 檢查存儲狀態
print("存儲統計:", crud.storage.get_stats())
```

## 下一步

現在您已經掌握了 AutoCRUD 的核心功能，建議：

1. 💡 查看 [示例集合](examples.md) 了解實際應用場景
2. 🔧 探索 [API 參考](api_reference.md) 了解詳細接口
3. 🤝 閱讀 [貢獻指南](contributing.md) 參與項目開發
4. 📋 查看 [更改日誌](changelog.md) 了解最新更新
