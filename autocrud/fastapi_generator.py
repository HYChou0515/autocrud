"""FastAPI 自動生成模組"""

from typing import Optional, Type, Callable, Any
from functools import wraps
from fastapi import FastAPI, APIRouter, BackgroundTasks
from pydantic import BaseModel, create_model
from .core import SingleModelCRUD
from .converter import ModelConverter
from .route_config import RouteConfig, BackgroundTaskMode, RouteOptions
from .plugin_system import plugin_manager, PluginRouteConfig, RouteMethod


def background_task_decorator(func: Callable) -> Callable:
    """
    Decorator 來確保 background task 函數接收正確的參數格式：
    (route_name: str, resource_name: str, route_input: Any, route_output: Any)
    """

    @wraps(func)
    def wrapper(
        route_name: str, resource_name: str, route_input: Any, route_output: Any
    ):
        return func(route_name, resource_name, route_input, route_output)

    return wrapper


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

    def _with_background_task(
        self,
        route_name: str,
        route_options: RouteOptions,
    ):
        """Decorator 來自動處理 background task 的執行"""

        def decorator(route_func: Callable) -> Callable:
            @wraps(route_func)
            async def wrapper(*args, **kwargs):
                # 執行原始的路由函數
                result = await route_func(*args, **kwargs)

                # 從 kwargs 中獲取 background_tasks（確保一定存在）
                background_tasks = kwargs["background_tasks"]

                # 執行 background task，傳遞完整的 args 和 kwargs
                self._execute_background_task(
                    route_options,
                    background_tasks,
                    route_name,
                    args,  # route_args: 位置參數
                    kwargs,  # route_kwargs: 關鍵字參數
                    result,  # route_output: 路由的返回值
                )

                return result

            return wrapper

        return decorator

    def _execute_background_task(
        self,
        route_options: RouteOptions,
        background_tasks: BackgroundTasks,
        route_name: str,
        route_args,
        route_kwargs,
        route_output,
    ):
        """統一的背景任務執行邏輯"""
        # 檢查是否禁用背景任務
        if route_options.background_task == BackgroundTaskMode.DISABLED:
            return

        # 檢查是否有背景任務函數
        if not route_options.background_task_func:
            return

        # 自動裝飾 background task 函數以確保正確的參數格式
        decorated_func = background_task_decorator(route_options.background_task_func)

        # 構建 route_input，包含 args 和 kwargs（排除 background_tasks）
        route_input = {
            "args": route_args,
            "kwargs": {
                k: v for k, v in route_kwargs.items() if k != "background_tasks"
            },
        }

        if route_options.background_task == BackgroundTaskMode.CONDITIONAL:
            # 條件式執行：需要檢查條件函數
            if (
                route_options.background_task_condition
                and route_options.background_task_condition(route_output)
            ):
                background_tasks.add_task(
                    decorated_func,
                    route_name,
                    self.crud.resource_name,
                    route_input,
                    route_output,
                )
        else:  # BackgroundTaskMode.ENABLED
            # 直接執行
            background_tasks.add_task(
                decorated_func,
                route_name,
                self.crud.resource_name,
                route_input,
                route_output,
            )

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

        # 從 plugin manager 獲取所有適用的路由配置
        plugin_routes = plugin_manager.get_routes_for_crud(self.crud)

        # 根據 route_config 過濾和處理路由
        for plugin_route in plugin_routes:
            # 檢查路由是否啟用
            if not config.is_route_enabled(plugin_route.name):
                continue

            # 獲取路由選項，可能會覆蓋 plugin 的預設選項
            route_options = config.get_route_options(plugin_route.name)

            # 合併路由選項
            merged_options = self._merge_route_options(
                plugin_route.options, route_options
            )

            # 註冊路由到 router
            self._register_plugin_route(router, plugin_route, merged_options)

        return router

    def _merge_route_options(
        self, plugin_options: RouteOptions, config_options: RouteOptions
    ) -> RouteOptions:
        """合併 plugin 選項和配置選項"""
        # config_options 優先級更高
        return RouteOptions(
            enabled=config_options.enabled,
            background_task=config_options.background_task
            if config_options.background_task != BackgroundTaskMode.DISABLED
            else plugin_options.background_task,
            background_task_func=config_options.background_task_func
            or plugin_options.background_task_func,
            background_task_condition=config_options.background_task_condition
            or plugin_options.background_task_condition,
            custom_status_code=config_options.custom_status_code
            or plugin_options.custom_status_code,
            custom_dependencies=config_options.custom_dependencies
            or plugin_options.custom_dependencies,
        )

    def _register_plugin_route(
        self, router: APIRouter, plugin_route: PluginRouteConfig, options: RouteOptions
    ):
        """註冊一個 plugin 路由到 router"""
        # 準備路由裝飾器參數
        route_kwargs = {
            "path": plugin_route.path,
        }

        # 添加可選參數
        if plugin_route.response_model:
            route_kwargs["response_model"] = plugin_route.response_model
        if options.custom_status_code or plugin_route.status_code:
            route_kwargs["status_code"] = (
                options.custom_status_code or plugin_route.status_code
            )
        if plugin_route.summary:
            route_kwargs["summary"] = plugin_route.summary
        if plugin_route.description:
            route_kwargs["description"] = plugin_route.description
        if plugin_route.tags:
            route_kwargs["tags"] = plugin_route.tags
        if plugin_route.responses:
            route_kwargs["responses"] = plugin_route.responses

        # 合併依賴
        combined_dependencies = []
        if plugin_route.dependencies:
            combined_dependencies.extend(plugin_route.dependencies)
        if options.custom_dependencies:
            combined_dependencies.extend(options.custom_dependencies)
        if combined_dependencies:
            route_kwargs["dependencies"] = combined_dependencies

        # 創建路由處理函數
        handler = self._create_route_handler(plugin_route, options)

        # 根據 HTTP 方法註冊路由
        method_map = {
            RouteMethod.GET: router.get,
            RouteMethod.POST: router.post,
            RouteMethod.PUT: router.put,
            RouteMethod.DELETE: router.delete,
            RouteMethod.PATCH: router.patch,
            RouteMethod.HEAD: router.head,
            RouteMethod.OPTIONS: router.options,
        }

        route_decorator = method_map.get(plugin_route.method)
        if route_decorator:
            route_decorator(**route_kwargs)(handler)
        else:
            raise ValueError(f"Unsupported HTTP method: {plugin_route.method}")

    def _create_route_handler(
        self, plugin_route: PluginRouteConfig, options: RouteOptions
    ):
        """創建路由處理函數，包含 background task 和 CRUD 注入邏輯"""
        original_handler = plugin_route.handler

        # 添加背景任務支持
        @self._with_background_task(plugin_route.name, options)
        async def final_handler(*args, **kwargs):
            # 檢查是否為異步函數
            import asyncio

            # 如果需要 CRUD 實例，將其作為第一個參數傳入
            if plugin_route.requires_crud:
                if asyncio.iscoroutinefunction(original_handler):
                    return await original_handler(self.crud, *args, **kwargs)
                else:
                    return original_handler(self.crud, *args, **kwargs)
            else:
                if asyncio.iscoroutinefunction(original_handler):
                    return await original_handler(*args, **kwargs)
                else:
                    return original_handler(*args, **kwargs)

        # 保持原始函數的註解信息
        if hasattr(original_handler, "__annotations__"):
            final_handler.__annotations__ = original_handler.__annotations__.copy()

        # 保持原始函數的參數信息
        import inspect

        if hasattr(original_handler, "__code__"):
            # 獲取原始函數的參數信息，但要跳過第一個 crud 參數（如果有的話）
            original_sig = inspect.signature(original_handler)
            params = list(original_sig.parameters.values())

            if plugin_route.requires_crud and params:
                # 跳過第一個 crud 參數
                params = params[1:]

            # 重建簽名
            new_sig = inspect.Signature(
                parameters=params, return_annotation=original_sig.return_annotation
            )
            final_handler.__signature__ = new_sig

        return final_handler

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
