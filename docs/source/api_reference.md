# 🔧 API 參考

本節提供 AutoCRUD 的完整 API 文檔，包括所有類、方法和配置選項。

## 核心模塊

### AutoCRUD

主要的 CRUD 管理器類。

```python
class AutoCRUD:
    """AutoCRUD 主類，用於管理 CRUD 操作和路由"""
    
    def __init__(
        self,
        model_naming: Union[str, Callable] = "kebab",
        storage: Optional[Storage] = None,
        serializer: Optional[Serializer] = None,
        cache: Optional[Cache] = None,
        route_config: Optional[RouteConfig] = None,
        **kwargs
    ):
        """
        初始化 AutoCRUD 實例
        
        Args:
            model_naming: 模型命名策略 ("kebab", "snake", "lower", "preserve" 或自定義函數)
            storage: 存儲後端實例
            serializer: 序列化器實例  
            cache: 緩存實例
            route_config: 路由配置
            **kwargs: 其他配置選項
        """
```

#### 方法

##### add_model

```python
def add_model(
    self,
    model_type: Type,
    name: Optional[str] = None,
    config: Optional[ModelConfig] = None
) -> None:
    """
    註冊模型類型
    
    Args:
        model_type: 要註冊的模型類型 (Pydantic, TypedDict, dataclass, msgspec.Struct)
        name: 自定義模型名稱 (可選)
        config: 模型特定配置 (可選)
        
    Raises:
        ModelRegistrationError: 當模型註冊失敗時
        
    Example:
        >>> crud.add_model(User)
        >>> crud.add_model(Product, name="products")
    """
```

##### add_route_template

```python
def add_route_template(
    self,
    template: RouteTemplate,
    model_types: Optional[List[Type]] = None
) -> None:
    """
    添加路由模板
    
    Args:
        template: 路由模板實例
        model_types: 應用到特定模型類型 (可選，默認應用到所有模型)
        
    Example:
        >>> crud.add_route_template(CreateRouteTemplate())
        >>> crud.add_route_template(ReadRouteTemplate(), [User, Product])
    """
```

##### apply

```python
def apply(
    self,
    router: APIRouter,
    prefix: str = "",
    tags: Optional[List[str]] = None
) -> None:
    """
    將 CRUD 路由應用到 FastAPI 路由器
    
    Args:
        router: FastAPI 路由器實例
        prefix: 路由前綴
        tags: OpenAPI 標籤
        
    Example:
        >>> router = APIRouter()
        >>> crud.apply(router, prefix="/api/v1", tags=["CRUD"])
        >>> app.include_router(router)
    """
```

##### get_registered_models

```python
def get_registered_models(self) -> List[Type]:
    """
    獲取已註冊的模型列表
    
    Returns:
        已註冊模型類型的列表
    """
```

##### get_model_routes

```python
def get_model_routes(self, model_type: Type) -> List[Route]:
    """
    獲取特定模型的路由列表
    
    Args:
        model_type: 模型類型
        
    Returns:
        該模型的路由列表
    """
```

## 路由模板

### BaseRouteTemplate

所有路由模板的基類。

```python
class BaseRouteTemplate(ABC):
    """路由模板基類"""
    
    def __init__(
        self,
        path: Optional[str] = None,
        methods: Optional[List[str]] = None,
        status_code: int = 200,
        response_model: Optional[Type] = None,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        **kwargs
    ):
        """
        初始化路由模板
        
        Args:
            path: 路由路徑模式
            methods: HTTP 方法列表
            status_code: 成功響應狀態碼
            response_model: 響應模型類型
            summary: OpenAPI 摘要
            description: OpenAPI 描述
            tags: OpenAPI 標籤
        """
```

### CreateRouteTemplate

處理資源創建的路由模板。

```python
class CreateRouteTemplate(BaseRouteTemplate):
    """創建資源的路由模板"""
    
    def __init__(
        self,
        path: str = "/",
        methods: List[str] = ["POST"],
        status_code: int = 201,
        enable_validation: bool = True,
        return_created_resource: bool = True,
        **kwargs
    ):
        """
        初始化創建路由模板
        
        Args:
            path: 路由路徑 (默認 "/")
            methods: HTTP 方法 (默認 ["POST"])
            status_code: 成功狀態碼 (默認 201)
            enable_validation: 啟用輸入驗證
            return_created_resource: 返回創建的資源
        """
    
    async def create_handler(
        self,
        data: dict,
        model_type: Type,
        storage: Storage
    ) -> dict:
        """
        創建資源的處理函數
        
        Args:
            data: 要創建的數據
            model_type: 模型類型
            storage: 存儲實例
            
        Returns:
            創建的資源數據
            
        Raises:
            ValidationError: 驗證失敗
            CreateError: 創建失敗
        """
```

### ReadRouteTemplate

處理資源讀取的路由模板。

```python
class ReadRouteTemplate(BaseRouteTemplate):
    """讀取資源的路由模板"""
    
    def __init__(
        self,
        path: str = "/{id}",
        methods: List[str] = ["GET"],
        enable_field_selection: bool = False,
        default_fields: Optional[List[str]] = None,
        **kwargs
    ):
        """
        初始化讀取路由模板
        
        Args:
            path: 路由路徑 (默認 "/{id}")
            methods: HTTP 方法 (默認 ["GET"])
            enable_field_selection: 啟用字段選擇
            default_fields: 默認返回字段
        """
    
    async def read_handler(
        self,
        id: str,
        model_type: Type,
        storage: Storage,
        fields: Optional[List[str]] = None
    ) -> dict:
        """
        讀取資源的處理函數
        
        Args:
            id: 資源 ID
            model_type: 模型類型
            storage: 存儲實例
            fields: 要返回的字段
            
        Returns:
            資源數據
            
        Raises:
            NotFoundError: 資源不存在
        """
```

### UpdateRouteTemplate

處理資源更新的路由模板。

```python
class UpdateRouteTemplate(BaseRouteTemplate):
    """更新資源的路由模板"""
    
    def __init__(
        self,
        path: str = "/{id}",
        methods: List[str] = ["PUT"],
        enable_partial_update: bool = False,
        enable_optimistic_locking: bool = False,
        **kwargs
    ):
        """
        初始化更新路由模板
        
        Args:
            path: 路由路徑 (默認 "/{id}")
            methods: HTTP 方法 (默認 ["PUT"])
            enable_partial_update: 啟用部分更新
            enable_optimistic_locking: 啟用樂觀鎖
        """
    
    async def update_handler(
        self,
        id: str,
        data: dict,
        model_type: Type,
        storage: Storage,
        partial: bool = False
    ) -> dict:
        """
        更新資源的處理函數
        
        Args:
            id: 資源 ID
            data: 更新數據
            model_type: 模型類型
            storage: 存儲實例
            partial: 是否為部分更新
            
        Returns:
            更新後的資源數據
            
        Raises:
            NotFoundError: 資源不存在
            ValidationError: 驗證失敗
            ConflictError: 樂觀鎖衝突
        """
```

### DeleteRouteTemplate

處理資源刪除的路由模板。

```python
class DeleteRouteTemplate(BaseRouteTemplate):
    """刪除資源的路由模板"""
    
    def __init__(
        self,
        path: str = "/{id}",
        methods: List[str] = ["DELETE"],
        status_code: int = 204,
        enable_soft_delete: bool = False,
        **kwargs
    ):
        """
        初始化刪除路由模板
        
        Args:
            path: 路由路徑 (默認 "/{id}")
            methods: HTTP 方法 (默認 ["DELETE"])
            status_code: 成功狀態碼 (默認 204)
            enable_soft_delete: 啟用軟刪除
        """
    
    async def delete_handler(
        self,
        id: str,
        model_type: Type,
        storage: Storage,
        soft: bool = False
    ) -> Optional[dict]:
        """
        刪除資源的處理函數
        
        Args:
            id: 資源 ID
            model_type: 模型類型
            storage: 存儲實例
            soft: 是否為軟刪除
            
        Returns:
            None 或刪除的資源數據
            
        Raises:
            NotFoundError: 資源不存在
        """
```

### ListRouteTemplate

處理資源列表的路由模板。

```python
class ListRouteTemplate(BaseRouteTemplate):
    """列出資源的路由模板"""
    
    def __init__(
        self,
        path: str = "/",
        methods: List[str] = ["GET"],
        enable_pagination: bool = True,
        default_limit: int = 20,
        max_limit: int = 100,
        enable_sorting: bool = True,
        enable_filtering: bool = True,
        enable_field_selection: bool = False,
        **kwargs
    ):
        """
        初始化列表路由模板
        
        Args:
            path: 路由路徑 (默認 "/")
            methods: HTTP 方法 (默認 ["GET"])
            enable_pagination: 啟用分頁
            default_limit: 默認每頁數量
            max_limit: 最大每頁數量
            enable_sorting: 啟用排序
            enable_filtering: 啟用過濾
            enable_field_selection: 啟用字段選擇
        """
    
    async def list_handler(
        self,
        model_type: Type,
        storage: Storage,
        limit: int = 20,
        offset: int = 0,
        sort: Optional[List[str]] = None,
        filters: Optional[Dict] = None,
        fields: Optional[List[str]] = None
    ) -> dict:
        """
        列出資源的處理函數
        
        Args:
            model_type: 模型類型
            storage: 存儲實例
            limit: 每頁數量
            offset: 偏移量
            sort: 排序字段
            filters: 過濾條件
            fields: 返回字段
            
        Returns:
            包含資源列表和分頁信息的字典
        """
```

## 存儲後端

### Storage

存儲後端的抽象基類。

```python
class Storage(ABC):
    """存儲後端抽象基類"""
    
    @abstractmethod
    async def create(self, model_type: Type, data: dict) -> str:
        """創建資源並返回 ID"""
        
    @abstractmethod
    async def read(self, model_type: Type, id: str) -> Optional[dict]:
        """根據 ID 讀取資源"""
        
    @abstractmethod
    async def update(self, model_type: Type, id: str, data: dict) -> dict:
        """更新資源"""
        
    @abstractmethod
    async def delete(self, model_type: Type, id: str) -> bool:
        """刪除資源"""
        
    @abstractmethod
    async def list(
        self, 
        model_type: Type,
        limit: int = 20,
        offset: int = 0,
        filters: Optional[Dict] = None,
        sort: Optional[List[str]] = None
    ) -> Tuple[List[dict], int]:
        """列出資源，返回 (項目列表, 總數)"""
        
    @abstractmethod
    async def exists(self, model_type: Type, id: str) -> bool:
        """檢查資源是否存在"""
        
    @abstractmethod
    async def count(self, model_type: Type, filters: Optional[Dict] = None) -> int:
        """計算資源數量"""
```

### MemoryStorage

內存存儲實現。

```python
class MemoryStorage(Storage):
    """內存存儲實現"""
    
    def __init__(
        self,
        max_size: int = 10000,
        enable_persistence: bool = False,
        persistence_file: Optional[str] = None,
        auto_save_interval: int = 300
    ):
        """
        初始化內存存儲
        
        Args:
            max_size: 最大存儲條目數
            enable_persistence: 啟用持久化
            persistence_file: 持久化文件路徑
            auto_save_interval: 自動保存間隔 (秒)
        """
    
    async def save_to_file(self, file_path: Optional[str] = None) -> None:
        """保存數據到文件"""
        
    async def load_from_file(self, file_path: Optional[str] = None) -> None:
        """從文件加載數據"""
        
    def get_stats(self) -> dict:
        """獲取存儲統計信息"""
```

### FileStorage

文件存儲實現。

```python
class FileStorage(Storage):
    """文件存儲實現"""
    
    def __init__(
        self,
        base_path: str = "./data",
        file_format: str = "json",
        enable_compression: bool = False,
        enable_backup: bool = True,
        max_backups: int = 5
    ):
        """
        初始化文件存儲
        
        Args:
            base_path: 基礎存儲路徑
            file_format: 文件格式 ("json", "yaml", "pickle", "msgpack")
            enable_compression: 啟用壓縮
            enable_backup: 啟用備份
            max_backups: 最大備份數量
        """
    
    async def backup(self) -> str:
        """創建備份，返回備份路徑"""
        
    async def restore(self, backup_path: str) -> None:
        """從備份恢復"""
        
    async def cleanup_backups(self) -> None:
        """清理舊備份"""
```

### DatabaseStorage

數據庫存儲實現。

```python
class DatabaseStorage(Storage):
    """數據庫存儲實現"""
    
    def __init__(
        self,
        url: str,
        table_prefix: str = "autocrud_",
        pool_size: int = 10,
        max_overflow: int = 20,
        enable_migrations: bool = True,
        migration_path: Optional[str] = None
    ):
        """
        初始化數據庫存儲
        
        Args:
            url: 數據庫連接 URL
            table_prefix: 表名前綴
            pool_size: 連接池大小
            max_overflow: 最大溢出連接數
            enable_migrations: 啟用數據遷移
            migration_path: 遷移文件路徑
        """
    
    async def create_tables(self) -> None:
        """創建數據表"""
        
    async def migrate(self) -> None:
        """執行數據遷移"""
        
    async def get_connection(self) -> Connection:
        """獲取數據庫連接"""
        
    async def execute_query(self, query: str, params: dict = None) -> Any:
        """執行查詢"""
```

## 序列化器

### Serializer

序列化器抽象基類。

```python
class Serializer(ABC):
    """序列化器抽象基類"""
    
    @abstractmethod
    def dumps(self, obj: Any) -> str:
        """序列化對象為字符串"""
        
    @abstractmethod
    def loads(self, data: str) -> Any:
        """反序列化字符串為對象"""
        
    @abstractmethod
    def serialize_model(self, model_instance: Any, model_type: Type) -> dict:
        """序列化模型實例為字典"""
        
    @abstractmethod
    def deserialize_model(self, data: dict, model_type: Type) -> Any:
        """反序列化字典為模型實例"""
```

### JSONSerializer

JSON 序列化器實現。

```python
class JSONSerializer(Serializer):
    """JSON 序列化器"""
    
    def __init__(
        self,
        ensure_ascii: bool = False,
        indent: Optional[int] = None,
        sort_keys: bool = False,
        default: Optional[Callable] = None
    ):
        """
        初始化 JSON 序列化器
        
        Args:
            ensure_ascii: 確保 ASCII 編碼
            indent: 縮進空格數
            sort_keys: 排序鍵
            default: 自定義默認函數
        """
```

### MsgspecSerializer

msgspec 序列化器實現。

```python
class MsgspecSerializer(Serializer):
    """msgspec 序列化器 (高性能)"""
    
    def __init__(
        self,
        enc_hook: Optional[Callable] = None,
        dec_hook: Optional[Callable] = None,
        strict: bool = True
    ):
        """
        初始化 msgspec 序列化器
        
        Args:
            enc_hook: 編碼鈎子函數
            dec_hook: 解碼鈎子函數
            strict: 嚴格模式
        """
```

## 緩存

### Cache

緩存抽象基類。

```python
class Cache(ABC):
    """緩存抽象基類"""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """獲取緩存值"""
        
    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """設置緩存值"""
        
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """刪除緩存值"""
        
    @abstractmethod
    async def clear(self) -> None:
        """清空緩存"""
        
    @abstractmethod
    async def exists(self, key: str) -> bool:
        """檢查鍵是否存在"""
```

### MemoryCache

內存緩存實現。

```python
class MemoryCache(Cache):
    """內存緩存實現"""
    
    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: int = 300,
        cleanup_interval: int = 60
    ):
        """
        初始化內存緩存
        
        Args:
            max_size: 最大緩存條目數
            default_ttl: 默認過期時間 (秒)
            cleanup_interval: 清理間隔 (秒)
        """
    
    def get_stats(self) -> dict:
        """獲取緩存統計信息"""
```

### RedisCache

Redis 緩存實現。

```python
class RedisCache(Cache):
    """Redis 緩存實現"""
    
    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        key_prefix: str = "autocrud:",
        default_ttl: int = 300,
        enable_compression: bool = False,
        pool_size: int = 10
    ):
        """
        初始化 Redis 緩存
        
        Args:
            url: Redis 連接 URL
            key_prefix: 鍵前綴
            default_ttl: 默認過期時間 (秒)
            enable_compression: 啟用壓縮
            pool_size: 連接池大小
        """
    
    async def ping(self) -> bool:
        """檢查 Redis 連接"""
        
    async def get_info(self) -> dict:
        """獲取 Redis 信息"""
```

## 配置類

### RouteConfig

路由配置類。

```python
@dataclass
class RouteConfig:
    """路由配置"""
    
    prefix: str = ""                    # 路由前綴
    tags: Optional[List[str]] = None    # OpenAPI 標籤
    include_in_schema: bool = True      # 包含在 OpenAPI schema 中
    dependencies: Optional[List[Depends]] = None  # 依賴項
    responses: Optional[Dict[int, Dict]] = None    # 響應定義
    deprecated: bool = False            # 是否已棄用
    operation_id_prefix: str = ""       # 操作 ID 前綴
    
    # 中間件配置
    enable_cors: bool = False           # 啟用 CORS
    cors_origins: List[str] = None      # CORS 允許的源
    cors_methods: List[str] = None      # CORS 允許的方法
    
    # 安全配置
    enable_rate_limiting: bool = False  # 啟用速率限制
    rate_limit: str = "100/minute"      # 速率限制規則
    
    # 請求/響應配置
    max_request_size: int = 1024 * 1024  # 最大請求大小 (1MB)
    enable_compression: bool = False     # 啟用響應壓縮
```

### ModelConfig

模型配置類。

```python
@dataclass
class ModelConfig:
    """模型配置"""
    
    name: Optional[str] = None          # 自定義模型名稱
    path: Optional[str] = None          # 自定義路由路徑
    exclude_templates: List[str] = None # 排除的路由模板
    
    # 驗證配置
    enable_validation: bool = True      # 啟用驗證
    validate_on_create: bool = True     # 創建時驗證
    validate_on_update: bool = True     # 更新時驗證
    
    # 字段配置
    id_field: str = "id"               # ID 字段名
    created_at_field: str = "created_at"  # 創建時間字段名
    updated_at_field: str = "updated_at"  # 更新時間字段名
    deleted_at_field: str = "deleted_at"  # 刪除時間字段名 (軟刪除)
    
    # 查詢配置
    enable_soft_delete: bool = False    # 啟用軟刪除
    enable_versioning: bool = False     # 啟用版本控制
    version_field: str = "version"      # 版本字段名
    
    # 緩存配置
    enable_cache: bool = True           # 啟用緩存
    cache_ttl: Optional[int] = None     # 緩存過期時間
    cache_key_format: str = "{model}:{id}"  # 緩存鍵格式
```

### FilterConfig

過濾配置類。

```python
@dataclass
class FilterConfig:
    """過濾配置"""
    
    allowed_fields: List[str] = None    # 允許過濾的字段
    operators: List[str] = None         # 允許的操作符
    max_filters: int = 10               # 最大過濾條件數
    
    # 默認操作符
    DEFAULT_OPERATORS = [
        "eq",    # 等於
        "ne",    # 不等於
        "gt",    # 大於
        "ge",    # 大於等於
        "lt",    # 小於
        "le",    # 小於等於
        "in",    # 包含在
        "not_in", # 不包含在
        "like",  # 模糊匹配
        "ilike", # 不區分大小寫模糊匹配
        "is_null",    # 為空
        "is_not_null" # 不為空
    ]
```

## 異常類

### AutoCRUDError

所有 AutoCRUD 異常的基類。

```python
class AutoCRUDError(Exception):
    """AutoCRUD 基礎異常類"""
    
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[dict] = None
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(message)
```

### 具體異常類

```python
class ModelRegistrationError(AutoCRUDError):
    """模型註冊錯誤"""
    pass

class ValidationError(AutoCRUDError):
    """驗證錯誤"""
    
    def __init__(self, message: str, field_errors: dict = None):
        super().__init__(message)
        self.field_errors = field_errors or {}

class NotFoundError(AutoCRUDError):
    """資源未找到錯誤"""
    
    def __init__(self, resource_type: Type, resource_id: str):
        message = f"{resource_type.__name__} with id '{resource_id}' not found"
        super().__init__(message)
        self.resource_type = resource_type
        self.resource_id = resource_id

class ConflictError(AutoCRUDError):
    """資源衝突錯誤 (例如樂觀鎖)"""
    pass

class StorageError(AutoCRUDError):
    """存儲錯誤"""
    pass

class SerializationError(AutoCRUDError):
    """序列化錯誤"""
    pass

class CacheError(AutoCRUDError):
    """緩存錯誤"""
    pass
```

## 工具函數

### 模型檢查

```python
def is_pydantic_model(model_type: Type) -> bool:
    """檢查是否為 Pydantic 模型"""

def is_dataclass_model(model_type: Type) -> bool:
    """檢查是否為 dataclass"""

def is_typeddict_model(model_type: Type) -> bool:
    """檢查是否為 TypedDict"""

def is_msgspec_model(model_type: Type) -> bool:
    """檢查是否為 msgspec.Struct"""

def get_model_fields(model_type: Type) -> dict:
    """獲取模型字段信息"""

def validate_model_type(model_type: Type) -> bool:
    """驗證模型類型是否受支持"""
```

### 命名工具

```python
def kebab_case(name: str) -> str:
    """轉換為 kebab-case"""

def snake_case(name: str) -> str:
    """轉換為 snake_case"""

def camel_case(name: str) -> str:
    """轉換為 camelCase"""

def pascal_case(name: str) -> str:
    """轉換為 PascalCase"""

def get_model_name(model_type: Type, naming_strategy: Union[str, Callable]) -> str:
    """根據命名策略獲取模型名稱"""
```

### ID 生成

```python
def generate_uuid() -> str:
    """生成 UUID4 字符串"""

def generate_short_id(length: int = 8) -> str:
    """生成短 ID"""

def generate_timestamp_id() -> str:
    """生成基於時間戳的 ID"""

class IDGenerator(ABC):
    """ID 生成器抽象基類"""
    
    @abstractmethod
    def generate(self) -> str:
        """生成唯一 ID"""

class UUIDGenerator(IDGenerator):
    """UUID 生成器"""
    
class TimestampIDGenerator(IDGenerator):
    """時間戳 ID 生成器"""

class SequentialIDGenerator(IDGenerator):
    """順序 ID 生成器"""
```

## 類型定義

```python
from typing import Union, Optional, List, Dict, Any, Callable, Type, Tuple
from typing_extensions import TypedDict, Literal

# 命名策略類型
NamingStrategy = Union[
    Literal["kebab", "snake", "lower", "preserve"],
    Callable[[Type], str]
]

# 支持的模型類型
ModelType = Union[
    type,  # Pydantic BaseModel
    type,  # dataclass
    type,  # TypedDict
    type   # msgspec.Struct
]

# 過濾操作符
FilterOperator = Literal[
    "eq", "ne", "gt", "ge", "lt", "le",
    "in", "not_in", "like", "ilike",
    "is_null", "is_not_null"
]

# 排序方向
SortDirection = Literal["asc", "desc"]

# HTTP 方法
HTTPMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]

# 序列化格式
SerializationFormat = Literal["json", "msgpack", "pickle", "yaml"]

# 存儲類型
StorageType = Literal["memory", "file", "database", "redis"]

# 緩存類型
CacheType = Literal["memory", "redis", "memcached"]
```

## 常量

```python
# 默認配置
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
DEFAULT_CACHE_TTL = 300
MAX_REQUEST_SIZE = 1024 * 1024  # 1MB

# HTTP 狀態碼
class HTTPStatus:
    OK = 200
    CREATED = 201
    NO_CONTENT = 204
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    VALIDATION_ERROR = 422
    INTERNAL_SERVER_ERROR = 500

# 錯誤碼
class ErrorCode:
    MODEL_REGISTRATION_FAILED = "MODEL_REGISTRATION_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    RESOURCE_CONFLICT = "RESOURCE_CONFLICT"
    STORAGE_ERROR = "STORAGE_ERROR"
    SERIALIZATION_ERROR = "SERIALIZATION_ERROR"
    CACHE_ERROR = "CACHE_ERROR"
```

## 使用示例

### 基本使用

```python
from autocrud.crud.core import AutoCRUD, CreateRouteTemplate, ReadRouteTemplate
from pydantic import BaseModel

class User(BaseModel):
    name: str
    email: str

crud = AutoCRUD(model_naming="kebab")
crud.add_route_template(CreateRouteTemplate())
crud.add_route_template(ReadRouteTemplate())
crud.add_model(User)

# 應用到 FastAPI
from fastapi import FastAPI, APIRouter

app = FastAPI()
router = APIRouter()
crud.apply(router, prefix="/api/v1")
app.include_router(router)
```

### 高級配置

```python
from autocrud.crud.core import AutoCRUD, RouteConfig, ModelConfig
from autocrud.storage import DatabaseStorage
from autocrud.cache import RedisCache

# 配置存儲
storage = DatabaseStorage(
    url="postgresql://user:pass@localhost/db",
    pool_size=20
)

# 配置緩存
cache = RedisCache(
    url="redis://localhost:6379/0",
    default_ttl=3600
)

# 配置路由
route_config = RouteConfig(
    prefix="/api/v1",
    tags=["CRUD API"],
    enable_cors=True,
    cors_origins=["*"]
)

# 創建 CRUD 實例
crud = AutoCRUD(
    model_naming="kebab",
    storage=storage,
    cache=cache,
    route_config=route_config
)

# 配置模型
model_config = ModelConfig(
    enable_validation=True,
    enable_soft_delete=True,
    enable_cache=True,
    cache_ttl=1800
)

crud.add_model(User, config=model_config)
```

這個 API 參考涵蓋了 AutoCRUD 的所有主要組件和功能。如需更詳細的信息，請參考源代碼中的文檔字符串和類型註解。
