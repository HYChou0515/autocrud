"""多模型 AutoCRUD 系統"""

from typing import Dict, Type, List, Any, Optional, TYPE_CHECKING, TypeVar
from enum import Enum
from fastapi import FastAPI, APIRouter
from .core import SingleModelCRUD
from .storage import Storage
from .storage_factory import StorageFactory, DefaultStorageFactory
from .metadata import MetadataConfig
from .list_params import ListQueryParams, ListResult

if TYPE_CHECKING:
    from .route_config import RouteConfig

# 定義泛型類型變數
T = TypeVar("T")


class ResourceNameStyle(Enum):
    """資源名稱命名風格"""

    SNAKE = "snake"  # user_profile -> user_profiles
    CAMEL = "camel"  # user_profile -> userProfiles
    DASH = "dash"  # user_profile -> user-profiles


class AutoCRUD:
    """支持多個模型的 AutoCRUD 系統"""

    def __init__(
        self,
        storage_factory: Optional[StorageFactory] = None,
        metadata_config: Optional[MetadataConfig] = None,
        id_generator: Optional[callable] = None,
        use_plural: bool = True,
        resource_name_style: ResourceNameStyle = ResourceNameStyle.SNAKE,
    ):
        """
        初始化多模型 CRUD 系統

        Args:
            storage_factory: 存儲工廠，用於為每個資源創建獨立的存儲後端
                           如果為 None，將使用默認的內存存儲工廠
            metadata_config: 預設的 metadata 配置，在 register_model 時可以被覆蓋
            id_generator: 預設的 ID 生成器，在 register_model 時可以被覆蓋
            use_plural: 預設是否使用複數形式，在 register_model 時可以被覆蓋
            resource_name_style: 資源名稱命名風格 (snake/camel/dash)
        """
        if storage_factory is not None:
            self.storage_factory = storage_factory
        else:
            # 默認使用內存存儲工廠
            self.storage_factory = DefaultStorageFactory.memory()

        # 預設配置
        self.default_metadata_config = metadata_config
        self.default_id_generator = id_generator
        self.default_use_plural = use_plural
        self.default_resource_name_style = resource_name_style

        self.cruds: Dict[str, SingleModelCRUD] = {}
        self.models: Dict[str, Type] = {}
        self.storages: Dict[str, Storage] = {}  # 記錄每個資源的 storage
        self.model_to_resources: Dict[
            Type, List[str]
        ] = {}  # model class 到 resource names 的映射

    def register_model(
        self,
        model: Type[T],
        resource_name: Optional[str] = None,
        storage: Optional[Storage] = None,
        id_generator: Optional[callable] = None,
        metadata_config: Optional[MetadataConfig] = None,
        use_plural: Optional[bool] = None,
        resource_name_style: Optional[ResourceNameStyle] = None,
        default_values: Optional[Dict[str, Any]] = None,
    ) -> SingleModelCRUD[T]:
        """
        註冊一個模型

        Args:
            model: 要註冊的模型類
            resource_name: 資源名稱，如果為 None 則自動生成
            storage: 該資源專用的存儲後端，如果為 None 則使用 storage_factory 創建
            id_generator: ID 生成器函數，如果為 None 則使用預設值
            metadata_config: metadata 配置，如果為 None 則使用預設值
            use_plural: 是否使用複數形式，如果為 None 則使用預設值，僅在 resource_name 為 None 時生效
            resource_name_style: 資源名稱命名風格，如果為 None 則使用預設值，僅在 resource_name 為 None 時生效
            default_values: 預設值字典，對於 TypedDict 特別有用，可以讓必填欄位變成選填

        Returns:
            創建的 SingleModelCRUD 實例
        """
        # 使用預設值填充未提供的參數
        actual_id_generator = (
            id_generator if id_generator is not None else self.default_id_generator
        )
        actual_metadata_config = (
            metadata_config
            if metadata_config is not None
            else self.default_metadata_config
        )
        actual_use_plural = (
            use_plural if use_plural is not None else self.default_use_plural
        )
        actual_resource_name_style = (
            resource_name_style
            if resource_name_style is not None
            else self.default_resource_name_style
        )

        if resource_name is None:
            # 自動生成資源名稱
            if actual_use_plural:
                # ModelName -> model_names (根據風格)
                resource_name = self._pluralize_resource_name(
                    model.__name__, actual_resource_name_style
                )
            else:
                # ModelName -> model_name (根據風格)
                resource_name = self._singularize_resource_name(
                    model.__name__, actual_resource_name_style
                )

        if resource_name in self.cruds:
            raise ValueError(f"Resource '{resource_name}' already registered")

        # 決定使用哪個 storage
        if storage is not None:
            actual_storage = storage
        else:
            # 使用工廠為該資源創建獨立的存儲
            actual_storage = self.storage_factory.create_storage(resource_name)

        # 創建該模型的 CRUD 實例
        crud = SingleModelCRUD(
            model=model,
            storage=actual_storage,
            resource_name=resource_name,
            id_generator=actual_id_generator,
            metadata_config=actual_metadata_config,
            default_values=default_values,
        )

        self.cruds[resource_name] = crud
        self.models[resource_name] = model
        self.storages[resource_name] = actual_storage

        # 更新 model class 到 resource names 的映射
        if model not in self.model_to_resources:
            self.model_to_resources[model] = []
        self.model_to_resources[model].append(resource_name)

        return crud

    def get_crud(self, resource_name: str) -> SingleModelCRUD:
        """獲取指定資源的 CRUD 實例"""
        if resource_name not in self.cruds:
            raise ValueError(f"Resource '{resource_name}' not registered")
        return self.cruds[resource_name]

    def get_model(self, resource_name: str) -> Type:
        """獲取指定資源的模型類"""
        if resource_name not in self.models:
            raise ValueError(f"Resource '{resource_name}' not registered")
        return self.models[resource_name]

    def get_model_by_class(self, model_class: Type) -> Type:
        """根據 model class 獲取模型類

        Args:
            model_class: 要查找的模型類

        Returns:
            模型類（其實就是輸入的 model_class）

        Raises:
            ValueError: 如果模型未註冊
            ValueError: 如果模型註冊了多次（有多個不同的 resource_name）
        """
        if model_class not in self.model_to_resources:
            raise ValueError(f"Model class '{model_class.__name__}' not registered")

        resource_names = self.model_to_resources[model_class]
        if len(resource_names) > 1:
            raise ValueError(
                f"Model class '{model_class.__name__}' is registered multiple times "
                f"with different resource names: {resource_names}. "
                f"Please use get_model(resource_name) instead."
            )

        return model_class

    def get_crud_by_class(self, model_class: Type) -> SingleModelCRUD:
        """根據 model class 獲取 CRUD 實例

        Args:
            model_class: 要查找的模型類

        Returns:
            對應的 SingleModelCRUD 實例

        Raises:
            ValueError: 如果模型未註冊
            ValueError: 如果模型註冊了多次（有多個不同的 resource_name）
        """
        if model_class not in self.model_to_resources:
            raise ValueError(f"Model class '{model_class.__name__}' not registered")

        resource_names = self.model_to_resources[model_class]
        if len(resource_names) > 1:
            raise ValueError(
                f"Model class '{model_class.__name__}' is registered multiple times "
                f"with different resource names: {resource_names}. "
                f"Please use get_crud(resource_name) instead."
            )

        resource_name = resource_names[0]
        return self.cruds[resource_name]

    def get_storage_by_class(self, model_class: Type) -> Storage:
        """根據 model class 獲取存儲後端

        Args:
            model_class: 要查找的模型類

        Returns:
            對應的 Storage 實例

        Raises:
            ValueError: 如果模型未註冊
            ValueError: 如果模型註冊了多次（有多個不同的 resource_name）
        """
        if model_class not in self.model_to_resources:
            raise ValueError(f"Model class '{model_class.__name__}' not registered")

        resource_names = self.model_to_resources[model_class]
        if len(resource_names) > 1:
            raise ValueError(
                f"Model class '{model_class.__name__}' is registered multiple times "
                f"with different resource names: {resource_names}. "
                f"Please use get_storage(resource_name) instead."
            )

        resource_name = resource_names[0]
        return self.storages[resource_name]

    def list_model_classes(self) -> List[Type]:
        """列出所有註冊的模型類"""
        return list(self.model_to_resources.keys())

    def get_resource_names_by_class(self, model_class: Type) -> List[str]:
        """獲取指定模型類對應的所有 resource names

        Args:
            model_class: 要查找的模型類

        Returns:
            該模型類對應的所有 resource names

        Raises:
            ValueError: 如果模型未註冊
        """
        if model_class not in self.model_to_resources:
            raise ValueError(f"Model class '{model_class.__name__}' not registered")

        return self.model_to_resources[model_class].copy()

    def get_storage(self, resource_name: str) -> Storage:
        """獲取指定資源的存儲後端"""
        if resource_name not in self.storages:
            raise ValueError(f"Resource '{resource_name}' not registered")
        return self.storages[resource_name]

    def list_resources(self) -> List[str]:
        """列出所有註冊的資源名稱"""
        return list(self.cruds.keys())

    def unregister_model(self, resource_name: str) -> bool:
        """取消註冊一個模型"""
        if resource_name in self.cruds:
            del self.cruds[resource_name]
            del self.models[resource_name]
            del self.storages[resource_name]
            return True
        return False

    def create_router(
        self,
        prefix: str = "",
        route_config: Optional["RouteConfig"] = None,
    ) -> "APIRouter":
        """
        創建包含所有註冊模型路由的 APIRouter

        Args:
            prefix: 路由前綴
            route_config: 路由配置，控制哪些路由要啟用

        Returns:
            配置好的 APIRouter
        """
        from fastapi import APIRouter
        from .route_config import RouteConfig

        main_router = APIRouter()

        # 使用預設配置如果沒有提供
        if route_config is None:
            route_config = RouteConfig()

        # 為每個註冊的模型創建路由
        for resource_name, crud in self.cruds.items():
            from .fastapi_generator import FastAPIGenerator

            generator = FastAPIGenerator(crud, route_config=route_config)
            resource_router = generator.create_router(route_config=route_config)
            main_router.include_router(resource_router)

        return main_router

    def create_fastapi_app(
        self,
        title: str = "Multi-Model CRUD API",
        description: str = "自動生成的多模型 CRUD API",
        version: str = "1.0.0",
        prefix: str = "/api/v1",
        route_config: Optional["RouteConfig"] = None,
    ) -> FastAPI:
        """
        創建包含所有註冊模型路由的 FastAPI 應用

        Args:
            title: API 標題
            description: API 描述
            version: API 版本
            prefix: 路由前綴
            route_config: 路由配置，控制哪些路由要啟用

        Returns:
            配置好的 FastAPI 應用
        """
        app = FastAPI(title=title, description=description, version=version)

        # 添加健康檢查端點
        @app.get("/health")
        async def health_check():
            resources_info = {}
            for resource_name in self.cruds.keys():
                storage = self.storages[resource_name]
                resources_info[resource_name] = {
                    "model": self.models[resource_name].__name__,
                    "storage_type": storage.__class__.__name__,
                }

            return {
                "status": "healthy",
                "service": title,
                "registered_models": len(self.cruds),
                "resources": resources_info,
            }

        # 創建路由
        router = self.create_router(route_config=route_config)
        app.include_router(router, prefix=prefix)

        return app

    def _pluralize_resource_name(
        self, model_name: str, style: ResourceNameStyle
    ) -> str:
        """
        將模型名稱轉換為複數資源名稱

        Args:
            model_name: 模型類名稱
            style: 命名風格

        Returns:
            複數形式的資源名稱
        """
        # 先轉換為基本形式 (snake_case)
        import re

        snake_case = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", model_name)
        snake_case = re.sub("([a-z0-9])([A-Z])", r"\1_\2", snake_case).lower()

        # 簡單的複數化規則
        if snake_case.endswith("y"):
            plural_snake = snake_case[:-1] + "ies"
        elif snake_case.endswith(("s", "sh", "ch", "x", "z")):
            plural_snake = snake_case + "es"
        else:
            plural_snake = snake_case + "s"

        # 根據風格轉換
        return self._convert_to_style(plural_snake, style)

    def _singularize_resource_name(
        self, model_name: str, style: ResourceNameStyle
    ) -> str:
        """
        將模型名稱轉換為單數資源名稱

        Args:
            model_name: 模型類名稱
            style: 命名風格

        Returns:
            單數形式的資源名稱
        """
        # 先轉換為基本形式 (snake_case)
        import re

        snake_case = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", model_name)
        snake_case = re.sub("([a-z0-9])([A-Z])", r"\1_\2", snake_case).lower()

        # 根據風格轉換
        return self._convert_to_style(snake_case, style)

    def _convert_to_style(self, snake_case_name: str, style: ResourceNameStyle) -> str:
        """
        將 snake_case 名稱轉換為指定風格

        Args:
            snake_case_name: snake_case 格式的名稱
            style: 目標命名風格

        Returns:
            轉換後的名稱
        """
        if style == ResourceNameStyle.SNAKE:
            return snake_case_name
        elif style == ResourceNameStyle.CAMEL:
            # snake_case -> camelCase
            components = snake_case_name.split("_")
            return components[0] + "".join(word.capitalize() for word in components[1:])
        elif style == ResourceNameStyle.DASH:
            # snake_case -> dash-case
            return snake_case_name.replace("_", "-")
        else:
            return snake_case_name

    # 便利方法：直接在多模型系統上執行 CRUD 操作
    def create(self, resource_name: str, data: Dict[str, Any]) -> str:
        """在指定資源上創建項目，返回創建的項目ID"""
        return self.get_crud(resource_name).create(data)

    def get(self, resource_name: str, resource_id: str) -> Optional[Dict[str, Any]]:
        """從指定資源獲取項目"""
        return self.get_crud(resource_name).get(resource_id)

    def update(
        self, resource_name: str, resource_id: str, data: Dict[str, Any]
    ) -> bool:
        """更新指定資源的項目，返回是否成功"""
        return self.get_crud(resource_name).update(resource_id, data)

    def advanced_update(
        self, resource_name: str, resource_id: str, update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """使用 Advanced Updater 更新指定資源的項目"""
        return self.get_crud(resource_name).advanced_update(resource_id, update_data)

    def delete(self, resource_name: str, resource_id: str) -> bool:
        """從指定資源刪除項目"""
        return self.get_crud(resource_name).delete(resource_id)

    def list_all(
        self, resource_name: str, params: Optional[ListQueryParams] = None
    ) -> List[Dict[str, Any]]:
        """列出指定資源的所有項目"""
        return self.get_crud(resource_name).list_all(params)

    def list_with_params(
        self, resource_name: str, params: ListQueryParams
    ) -> ListResult:
        """使用查詢參數列出指定資源的項目"""
        return self.get_crud(resource_name).list_with_params(params)

    def count(self, resource_name: str) -> int:
        """取得指定資源的總數量"""
        return self.get_crud(resource_name).count()

    def exists(self, resource_name: str, resource_id: str) -> bool:
        """檢查指定資源的項目是否存在"""
        return self.get_crud(resource_name).exists(resource_id)
