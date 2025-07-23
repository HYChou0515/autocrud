"""FastAPI 自動生成模組"""

from typing import Dict, Optional, Type
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, create_model
from .core import AutoCRUD
from .converter import ModelConverter


class FastAPIGenerator:
    """FastAPI 路由自動生成器"""

    def __init__(self, crud: AutoCRUD):
        self.crud = crud
        self.converter = ModelConverter()

        # 生成 Pydantic 模型用於請求/響應
        self.request_model = self._create_request_model()
        self.response_model = self._create_response_model()

    def _create_request_model(self) -> Type[BaseModel]:
        """創建請求模型（不包含 ID）"""
        fields = self.converter.extract_fields(self.crud.model)

        # 移除 ID 欄位（如果存在）
        fields.pop("id", None)

        # 創建 Pydantic 模型
        return create_model(
            f"{self.crud.model.__name__}Request",
            **{name: (field_type, ...) for name, field_type in fields.items()},
        )

    def _create_response_model(self) -> Type[BaseModel]:
        """創建響應模型（包含 ID）"""
        fields = self.converter.extract_fields(self.crud.model)

        # 確保包含 ID 欄位
        fields["id"] = str

        # 創建 Pydantic 模型
        return create_model(
            f"{self.crud.model.__name__}Response",
            **{name: (field_type, ...) for name, field_type in fields.items()},
        )

    def create_routes(self, app: FastAPI, prefix: str = "") -> FastAPI:
        """在 FastAPI 應用中創建 CRUD 路由"""

        resource_path = f"{prefix}/{self.crud.resource_name}"
        request_model = self.request_model
        response_model = self.response_model
        crud = self.crud

        @app.post(
            f"{resource_path}",
            response_model=response_model,
            status_code=status.HTTP_201_CREATED,
        )
        async def create_resource(item):
            """創建資源"""
            try:
                item_dict = item.model_dump()
                created_item = crud.create(item_dict)
                return created_item
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"創建失敗: {str(e)}",
                )

        # 設定類型提示
        create_resource.__annotations__["item"] = request_model

        @app.get(f"{resource_path}/{{resource_id}}", response_model=response_model)
        async def get_resource(resource_id: str):
            """獲取單個資源"""
            item = crud.get(resource_id)
            if item is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"資源不存在: {resource_id}",
                )
            return item

        @app.put(f"{resource_path}/{{resource_id}}", response_model=response_model)
        async def update_resource(resource_id: str, item):
            """更新資源"""
            if not crud.exists(resource_id):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"資源不存在: {resource_id}",
                )

            try:
                item_dict = item.model_dump()
                updated_item = crud.update(resource_id, item_dict)
                return updated_item
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"更新失敗: {str(e)}",
                )

        # 設定類型提示
        update_resource.__annotations__["item"] = request_model

        @app.delete(
            f"{resource_path}/{{resource_id}}", status_code=status.HTTP_204_NO_CONTENT
        )
        async def delete_resource(resource_id: str):
            """刪除資源"""
            if not crud.exists(resource_id):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"資源不存在: {resource_id}",
                )

            success = crud.delete(resource_id)
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="刪除失敗"
                )

        @app.get(f"{resource_path}", response_model=Dict[str, response_model])
        async def list_resources():
            """列出所有資源"""
            return crud.list_all()

        return app

    def create_fastapi_app(
        self,
        title: Optional[str] = None,
        description: Optional[str] = None,
        version: str = "1.0.0",
        prefix: str = "/api/v1",
    ) -> FastAPI:
        """創建完整的 FastAPI 應用"""

        if title is None:
            title = f"{self.crud.model.__name__} API"

        if description is None:
            description = f"自動生成的 {self.crud.model.__name__} CRUD API"

        app = FastAPI(title=title, description=description, version=version)

        # 添加健康檢查端點
        @app.get("/health")
        async def health_check():
            return {"status": "healthy", "service": title}

        # 添加 CRUD 路由
        self.create_routes(app, prefix)

        return app


# 為了向後兼容，在 AutoCRUD 類中添加 create_fastapi_app 方法
def create_fastapi_app_method(self, **kwargs) -> FastAPI:
    """創建 FastAPI 應用的便利方法"""
    generator = FastAPIGenerator(self)
    return generator.create_fastapi_app(**kwargs)


# 使用範例
if __name__ == "__main__":
    from dataclasses import dataclass
    from .storage import MemoryStorage
    from .core import AutoCRUD

    @dataclass
    class User:
        name: str
        email: str
        age: int

    # 創建 CRUD 系統
    storage = MemoryStorage()
    crud = AutoCRUD(model=User, storage=storage, resource_name="users")

    # 生成 FastAPI 應用
    generator = FastAPIGenerator(crud)
    app = generator.create_fastapi_app(
        title="用戶管理 API", description="自動生成的用戶 CRUD API"
    )

    print("FastAPI 應用已創建！")
    print("可用端點:")
    print("- POST /api/v1/users")
    print("- GET /api/v1/users/{id}")
    print("- PUT /api/v1/users/{id}")
    print("- DELETE /api/v1/users/{id}")
    print("- GET /api/v1/users")
