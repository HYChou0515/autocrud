"""FastAPI 自動生成模組"""

from typing import Optional, Type
from fastapi import FastAPI, HTTPException, status, APIRouter, BackgroundTasks
from pydantic import BaseModel, create_model
from .core import SingleModelCRUD
from .converter import ModelConverter
from .route_config import RouteConfig, BackgroundTaskMode


class FastAPIGenerator:
    """FastAPI 路由生成器"""

    def __init__(
        self,
        crud: SingleModelCRUD,
        route_config: Optional[RouteConfig] = None,
    ):
        self.crud = crud
        self.converter = ModelConverter()
        # 使用預設配置如果沒有提供
        if route_config is None:
            self.route_config = RouteConfig()
        else:
            self.route_config = route_config

    def _execute_background_task(
        self, route_options, background_tasks: BackgroundTasks, route_output
    ):
        """統一的背景任務執行邏輯"""
        if not route_options.background_task_func:
            return

        if route_options.background_task == BackgroundTaskMode.CONDITIONAL:
            # 條件式執行：需要檢查條件函數
            if (
                route_options.background_task_condition
                and route_options.background_task_condition(route_output)
            ):
                background_tasks.add_task(
                    route_options.background_task_func,
                    route_output,
                )
        else:  # BackgroundTaskMode.ENABLED
            # 直接執行
            background_tasks.add_task(route_options.background_task_func, route_output)

    @property
    def request_model(self) -> Type[BaseModel]:
        """生成請求模型（用於 POST/PUT）"""
        # 使用 schema_analyzer 的 get_create_model 方法
        # 這個方法能正確處理可選字段和默認值
        return self.crud.schema_analyzer.get_create_model()

    @property
    def response_model(self) -> Type[BaseModel]:
        """生成響應模型（用於 GET）"""
        fields = self.converter.extract_fields(self.crud.model)

        # 確保響應包含 id 字段
        fields["id"] = str

        # 創建 Pydantic 模型
        return create_model(
            f"{self.crud.model.__name__}Response",
            **{name: (field_type, ...) for name, field_type in fields.items()},
        )

    def create_router(
        self,
        prefix: str = "",
        tags: Optional[list] = None,
        dependencies: Optional[list] = None,
        responses: Optional[dict] = None,
        route_config: Optional[RouteConfig] = None,
        **kwargs,
    ) -> APIRouter:
        """創建並返回包含 CRUD 路由的 APIRouter

        Args:
            prefix: 路由前綴
            tags: OpenAPI 標籤
            dependencies: 依賴注入列表
            responses: 響應模型定義
            route_config: 路由配置，控制哪些路由要啟用
            **kwargs: 其他 APIRouter 參數
        """
        # 使用提供的配置或預設配置
        config = route_config or self.route_config

        router = APIRouter(
            prefix=prefix,
            tags=tags or [self.crud.resource_name],
            dependencies=dependencies,
            responses=responses,
            **kwargs,
        )

        request_model = self.request_model
        response_model = self.response_model
        crud = self.crud

        # CREATE 路由
        if config.is_route_enabled("create"):
            create_options = config.get_route_options("create")

            # 構建路由裝飾器參數
            route_kwargs = {
                "path": f"/{self.crud.resource_name}",
                "response_model": response_model,
                "status_code": create_options.custom_status_code
                or status.HTTP_201_CREATED,
            }

            # 添加自定義依賴
            if create_options.custom_dependencies:
                route_kwargs["dependencies"] = create_options.custom_dependencies

            # 決定是否需要 BackgroundTasks 參數
            if create_options.background_task != BackgroundTaskMode.DISABLED:

                @router.post(**route_kwargs)
                async def create_resource(item, background_tasks: BackgroundTasks):
                    """創建資源（包含 background task）"""
                    try:
                        item_dict = item.model_dump()
                        created_id = crud.create(item_dict)
                        created_item = crud.get(created_id)

                        # 執行 background task
                        self._execute_background_task(
                            create_options, background_tasks, created_item
                        )

                        return created_item
                    except Exception as e:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"創建失敗: {str(e)}",
                        )

                # 設定類型提示
                create_resource.__annotations__["item"] = request_model
            else:

                @router.post(**route_kwargs)
                async def create_resource(item):
                    """創建資源"""
                    try:
                        item_dict = item.model_dump()
                        created_id = crud.create(item_dict)
                        created_item = crud.get(created_id)
                        return created_item
                    except Exception as e:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"創建失敗: {str(e)}",
                        )

                # 設定類型提示
                create_resource.__annotations__["item"] = request_model

        # COUNT 路由（必須在 {resource_id} 路由之前）
        if config.is_route_enabled("count"):
            count_options = config.get_route_options("count")

            # 構建路由裝飾器參數
            route_kwargs = {"path": f"/{self.crud.resource_name}/count"}

            # 添加自定義依賴
            if count_options.custom_dependencies:
                route_kwargs["dependencies"] = count_options.custom_dependencies

            # 決定是否需要 BackgroundTasks 參數
            if count_options.background_task != BackgroundTaskMode.DISABLED:

                @router.get(**route_kwargs)
                async def count_resources(background_tasks: BackgroundTasks):
                    """獲取資源總數（包含 background task）"""
                    count = crud.count()
                    count_result = {"count": count}

                    # 執行 background task
                    self._execute_background_task(
                        count_options, background_tasks, count_result
                    )

                    return count_result
            else:

                @router.get(**route_kwargs)
                async def count_resources():
                    """獲取資源總數"""
                    count = crud.count()
                    count_result = {"count": count}
                    return count_result

        # GET 單個資源路由
        if config.is_route_enabled("get"):
            get_options = config.get_route_options("get")

            # 構建路由裝飾器參數
            route_kwargs = {
                "path": f"/{self.crud.resource_name}/{{resource_id}}",
                "response_model": response_model,
            }

            # 添加自定義依賴
            if get_options.custom_dependencies:
                route_kwargs["dependencies"] = get_options.custom_dependencies

            # 決定是否需要 BackgroundTasks 參數
            if get_options.background_task != BackgroundTaskMode.DISABLED:

                @router.get(**route_kwargs)
                async def get_resource(
                    resource_id: str, background_tasks: BackgroundTasks
                ):
                    """獲取單個資源（包含 background task）"""
                    item = crud.get(resource_id)
                    if item is None:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND, detail="資源不存在"
                        )

                    # 執行 background task
                    self._execute_background_task(get_options, background_tasks, item)

                    return item
            else:

                @router.get(**route_kwargs)
                async def get_resource(resource_id: str):
                    """獲取單個資源"""
                    item = crud.get(resource_id)
                    if item is None:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND, detail="資源不存在"
                        )
                    return item

        # UPDATE 路由
        if config.is_route_enabled("update"):
            update_options = config.get_route_options("update")

            # 構建路由裝飾器參數
            route_kwargs = {
                "path": f"/{self.crud.resource_name}/{{resource_id}}",
                "response_model": response_model,
                "status_code": update_options.custom_status_code or status.HTTP_200_OK,
            }

            # 添加自定義依賴
            if update_options.custom_dependencies:
                route_kwargs["dependencies"] = update_options.custom_dependencies

            if update_options.background_task != BackgroundTaskMode.DISABLED:

                @router.put(**route_kwargs)
                async def update_resource(
                    resource_id: str, item, background_tasks: BackgroundTasks
                ):
                    """更新資源（包含 background task）"""
                    try:
                        item_dict = item.model_dump()
                        success = crud.update(resource_id, item_dict)
                        if not success:
                            raise HTTPException(
                                status_code=status.HTTP_404_NOT_FOUND,
                                detail="資源不存在",
                            )
                        updated_item = crud.get(resource_id)

                        # 執行 background task
                        self._execute_background_task(
                            update_options, background_tasks, updated_item
                        )

                        return updated_item
                    except Exception as e:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"更新失敗: {str(e)}",
                        )

                # 設定類型提示
                update_resource.__annotations__["item"] = request_model
            else:

                @router.put(**route_kwargs)
                async def update_resource(resource_id: str, item):
                    """更新資源"""
                    try:
                        item_dict = item.model_dump()
                        success = crud.update(resource_id, item_dict)
                        if not success:
                            raise HTTPException(
                                status_code=status.HTTP_404_NOT_FOUND,
                                detail="資源不存在",
                            )
                        updated_item = crud.get(resource_id)
                        return updated_item
                    except Exception as e:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"更新失敗: {str(e)}",
                        )

                # 設定類型提示
                update_resource.__annotations__["item"] = request_model

        # DELETE 路由
        if config.is_route_enabled("delete"):
            delete_options = config.get_route_options("delete")

            # 構建路由裝飾器參數
            route_kwargs = {
                "path": f"/{self.crud.resource_name}/{{resource_id}}",
                "status_code": delete_options.custom_status_code
                or status.HTTP_204_NO_CONTENT,
            }

            # 添加自定義依賴
            if delete_options.custom_dependencies:
                route_kwargs["dependencies"] = delete_options.custom_dependencies

            if delete_options.background_task != BackgroundTaskMode.DISABLED:

                @router.delete(**route_kwargs)
                async def delete_resource(
                    resource_id: str, background_tasks: BackgroundTasks
                ):
                    """刪除資源（包含 background task）"""
                    success = crud.delete(resource_id)
                    if not success:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND, detail="資源不存在"
                        )

                    # DELETE 路由的回傳值是 None (204 No Content)
                    delete_result = None

                    # 執行 background task
                    self._execute_background_task(
                        delete_options, background_tasks, delete_result
                    )

                    # 204 No Content 不應該有響應體
                    return delete_result
            else:

                @router.delete(**route_kwargs)
                async def delete_resource(resource_id: str):
                    """刪除資源"""
                    success = crud.delete(resource_id)
                    if not success:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND, detail="資源不存在"
                        )
                    # 204 No Content 不應該有響應體
                    return

        # LIST 所有資源路由
        if config.is_route_enabled("list"):
            list_options = config.get_route_options("list")

            # 構建路由裝飾器參數
            route_kwargs = {"path": f"/{self.crud.resource_name}"}

            # 添加自定義依賴
            if list_options.custom_dependencies:
                route_kwargs["dependencies"] = list_options.custom_dependencies

            # 決定是否需要 BackgroundTasks 參數
            if list_options.background_task != BackgroundTaskMode.DISABLED:

                @router.get(**route_kwargs)
                async def list_resources(background_tasks: BackgroundTasks):
                    """列出所有資源（包含 background task）"""
                    items = crud.list_all()

                    # 執行 background task
                    self._execute_background_task(list_options, background_tasks, items)

                    return items
            else:

                @router.get(**route_kwargs)
                async def list_resources():
                    """列出所有資源"""
                    items = crud.list_all()
                    return items

        return router

    def create_routes(self, app: FastAPI, prefix: str = "") -> FastAPI:
        """在 FastAPI 應用中創建 CRUD 路由（向後兼容方法）"""
        router = self.create_router()
        app.include_router(router, prefix=prefix)
        return app

    def create_fastapi_app(
        self,
        title: Optional[str] = None,
        description: Optional[str] = None,
        version: str = "1.0.0",
        prefix: str = "/api/v1",
        route_config: Optional[RouteConfig] = None,
    ) -> FastAPI:
        """創建完整的 FastAPI 應用"""

        if title is None:
            title = f"{self.crud.model.__name__} API"

        if description is None:
            description = f"自動生成的 {self.crud.model.__name__} CRUD API"

        # 使用提供的配置或實例的配置
        if route_config is None:
            route_config = self.route_config

        app = FastAPI(title=title, description=description, version=version)

        # 添加健康檢查端點
        @app.get("/health")
        async def health_check():
            return {"status": "healthy", "service": title}

        # 使用新的 router 方法創建路由
        router = self.create_router(route_config=route_config)
        app.include_router(router, prefix=prefix)

        return app


# 添加便利方法到 SingleModelCRUD 類
def create_fastapi_app_method(self, route_config=None, **kwargs) -> FastAPI:
    """便利方法：直接從 CRUD 實例創建 FastAPI 應用"""
    generator = FastAPIGenerator(self, route_config=route_config)
    return generator.create_fastapi_app(**kwargs)


def create_router_method(
    self,
    route_config=None,
    prefix: str = "",
    tags: Optional[list] = None,
    dependencies: Optional[list] = None,
    responses: Optional[dict] = None,
    **kwargs,
) -> APIRouter:
    """便利方法：直接從 CRUD 實例創建 APIRouter"""
    generator = FastAPIGenerator(self, route_config=route_config)
    return generator.create_router(
        route_config=route_config,
        prefix=prefix,
        tags=tags,
        dependencies=dependencies,
        responses=responses,
        **kwargs,
    )


# 將方法注入到 SingleModelCRUD 類
from . import core  # noqa: E402

core.SingleModelCRUD.create_fastapi_app = create_fastapi_app_method
core.SingleModelCRUD.create_router = create_router_method


if __name__ == "__main__":
    # 使用範例
    from dataclasses import dataclass
    from .storage import MemoryStorage

    @dataclass
    class User:
        name: str
        email: str
        age: int

    # 創建 CRUD 實例
    storage = MemoryStorage()
    crud = SingleModelCRUD(model=User, storage=storage, resource_name="users")

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
    print("- GET /api/v1/users/count")
