"""多模型 AutoCRUD 系統"""

from typing import Dict, Type, List, Any, Optional
from fastapi import FastAPI
from .core import AutoCRUD
from .storage import Storage
from .fastapi_generator import FastAPIGenerator


class MultiModelAutoCRUD:
    """支持多個模型的 AutoCRUD 系統"""

    def __init__(self, storage: Storage):
        """
        初始化多模型 CRUD 系統

        Args:
            storage: 共享的存儲後端
        """
        self.storage = storage
        self.cruds: Dict[str, AutoCRUD] = {}
        self.models: Dict[str, Type] = {}

    def register_model(
        self,
        model: Type,
        resource_name: Optional[str] = None,
        id_generator: Optional[callable] = None,
        use_plural: bool = True,
    ) -> AutoCRUD:
        """
        註冊一個模型

        Args:
            model: 要註冊的模型類
            resource_name: 資源名稱，如果為 None 則自動生成
            id_generator: ID 生成器函數
            use_plural: 是否使用複數形式，僅在 resource_name 為 None 時生效

        Returns:
            創建的 AutoCRUD 實例
        """
        if resource_name is None:
            # 自動生成資源名稱
            if use_plural:
                # ModelName -> model_names
                resource_name = self._pluralize_resource_name(model.__name__)
            else:
                # ModelName -> model_name
                resource_name = self._singularize_resource_name(model.__name__)

        if resource_name in self.cruds:
            raise ValueError(f"Resource '{resource_name}' already registered")

        # 創建該模型的 CRUD 實例
        crud = AutoCRUD(
            model=model,
            storage=self.storage,
            resource_name=resource_name,
            id_generator=id_generator,
        )

        self.cruds[resource_name] = crud
        self.models[resource_name] = model

        return crud

    def get_crud(self, resource_name: str) -> AutoCRUD:
        """獲取指定資源的 CRUD 實例"""
        if resource_name not in self.cruds:
            raise ValueError(f"Resource '{resource_name}' not registered")
        return self.cruds[resource_name]

    def get_model(self, resource_name: str) -> Type:
        """獲取指定資源的模型類"""
        if resource_name not in self.models:
            raise ValueError(f"Resource '{resource_name}' not registered")
        return self.models[resource_name]

    def list_resources(self) -> List[str]:
        """列出所有註冊的資源名稱"""
        return list(self.cruds.keys())

    def unregister_model(self, resource_name: str) -> bool:
        """取消註冊一個模型"""
        if resource_name in self.cruds:
            del self.cruds[resource_name]
            del self.models[resource_name]
            return True
        return False

    def create_fastapi_app(
        self,
        title: str = "Multi-Model CRUD API",
        description: str = "自動生成的多模型 CRUD API",
        version: str = "1.0.0",
        prefix: str = "/api/v1",
    ) -> FastAPI:
        """
        創建包含所有註冊模型路由的 FastAPI 應用

        Args:
            title: API 標題
            description: API 描述
            version: API 版本
            prefix: 路由前綴

        Returns:
            配置好的 FastAPI 應用
        """
        app = FastAPI(title=title, description=description, version=version)

        # 添加健康檢查端點
        @app.get("/health")
        async def health_check():
            return {
                "status": "healthy",
                "service": title,
                "registered_models": len(self.cruds),
                "resources": list(self.cruds.keys()),
            }

        # 為每個註冊的模型創建路由
        for resource_name, crud in self.cruds.items():
            generator = FastAPIGenerator(crud)
            generator.create_routes(app, prefix)

        return app

    def _pluralize_resource_name(self, model_name: str) -> str:
        """
        將模型名稱轉換為複數資源名稱

        Args:
            model_name: 模型類名稱

        Returns:
            複數形式的資源名稱
        """
        # 將駝峰命名轉換為下劃線命名
        import re

        snake_case = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", model_name)
        snake_case = re.sub("([a-z0-9])([A-Z])", r"\1_\2", snake_case).lower()

        # 簡單的複數化規則
        if snake_case.endswith("y"):
            return snake_case[:-1] + "ies"
        elif snake_case.endswith(("s", "sh", "ch", "x", "z")):
            return snake_case + "es"
        else:
            return snake_case + "s"

    def _singularize_resource_name(self, model_name: str) -> str:
        """
        將模型名稱轉換為單數資源名稱

        Args:
            model_name: 模型類名稱

        Returns:
            單數形式的資源名稱
        """
        # 將駝峰命名轉換為下劃線命名
        import re

        snake_case = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", model_name)
        snake_case = re.sub("([a-z0-9])([A-Z])", r"\1_\2", snake_case).lower()

        return snake_case

    # 便利方法：直接在多模型系統上執行 CRUD 操作
    def create(self, resource_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """在指定資源上創建項目"""
        return self.get_crud(resource_name).create(data)

    def get(self, resource_name: str, resource_id: str) -> Optional[Dict[str, Any]]:
        """從指定資源獲取項目"""
        return self.get_crud(resource_name).get(resource_id)

    def update(
        self, resource_name: str, resource_id: str, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """更新指定資源的項目"""
        return self.get_crud(resource_name).update(resource_id, data)

    def delete(self, resource_name: str, resource_id: str) -> bool:
        """從指定資源刪除項目"""
        return self.get_crud(resource_name).delete(resource_id)

    def list_all(self, resource_name: str) -> Dict[str, Dict[str, Any]]:
        """列出指定資源的所有項目"""
        return self.get_crud(resource_name).list_all()

    def exists(self, resource_name: str, resource_id: str) -> bool:
        """檢查指定資源的項目是否存在"""
        return self.get_crud(resource_name).exists(resource_id)
