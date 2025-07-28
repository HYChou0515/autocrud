"""
Default CRUD route plugins.
將現有的 CRUD 路由重構為 plugin 形式。
"""

from typing import List, Optional, Any
from datetime import datetime
from fastapi import HTTPException, status, BackgroundTasks, Query
from pydantic import create_model

from .plugin_system import BaseRoutePlugin, PluginRouteConfig, RouteMethod
from .core import SingleModelCRUD
from .route_config import RouteOptions
from .converter import ModelConverter
from .list_params import ListQueryParams, DateTimeRange, SortOrder


class CreateRoutePlugin(BaseRoutePlugin):
    """Plugin for CREATE route (POST /{resource})"""

    def __init__(self):
        super().__init__("create", "1.0.0")
        self.converter = ModelConverter()

    def get_routes(self, crud: SingleModelCRUD) -> List[PluginRouteConfig]:
        """Generate CREATE route configuration"""

        async def create_handler(
            crud: SingleModelCRUD, item: Any, background_tasks: BackgroundTasks
        ):
            """創建資源"""
            try:
                # 如果 item 是 Pydantic 模型，轉換為字典
                if hasattr(item, "model_dump"):
                    item_dict = item.model_dump()
                elif hasattr(item, "dict"):
                    item_dict = item.dict()
                else:
                    item_dict = item

                created_id = crud.create(item_dict)
                created_item = crud.get(created_id)
                return created_item
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"創建失敗: {str(e)}",
                )

        # 生成請求模型
        request_model = crud.schema_analyzer.get_create_model()

        # 生成響應模型
        fields = self.converter.extract_fields(crud.model)
        response_model = create_model(
            f"{crud.model.__name__}Response",
            **{name: (field_type, ...) for name, field_type in fields.items()},
        )

        # 設置類型提示
        create_handler.__annotations__["item"] = request_model

        return [
            PluginRouteConfig(
                name="create",
                path=f"/{crud.resource_name}",
                method=RouteMethod.POST,
                handler=create_handler,
                options=RouteOptions.enabled_route(),
                response_model=response_model,
                status_code=status.HTTP_201_CREATED,
                summary=f"創建 {crud.model.__name__}",
                description=f"創建一個新的 {crud.model.__name__} 資源",
                priority=10,
            )
        ]


class GetRoutePlugin(BaseRoutePlugin):
    """Plugin for GET route (GET /{resource}/{id})"""

    def __init__(self):
        super().__init__("get", "1.0.0")
        self.converter = ModelConverter()

    def get_routes(self, crud: SingleModelCRUD) -> List[PluginRouteConfig]:
        """Generate GET route configuration"""

        async def get_handler(
            crud: SingleModelCRUD, resource_id: str, background_tasks: BackgroundTasks
        ):
            """獲取單個資源"""
            item = crud.get(resource_id)
            if item is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="資源不存在"
                )
            return item

        # 生成響應模型
        fields = self.converter.extract_fields(crud.model)
        response_model = create_model(
            f"{crud.model.__name__}Response",
            **{name: (field_type, ...) for name, field_type in fields.items()},
        )

        return [
            PluginRouteConfig(
                name="get",
                path=f"/{crud.resource_name}/{{resource_id}}",
                method=RouteMethod.GET,
                handler=get_handler,
                options=RouteOptions.enabled_route(),
                response_model=response_model,
                summary=f"獲取 {crud.model.__name__}",
                description=f"根據 ID 獲取特定的 {crud.model.__name__} 資源",
                priority=20,
            )
        ]


class UpdateRoutePlugin(BaseRoutePlugin):
    """Plugin for UPDATE route (PUT /{resource}/{id})"""

    def __init__(self):
        super().__init__("update", "1.0.0")
        self.converter = ModelConverter()

    def get_routes(self, crud: SingleModelCRUD) -> List[PluginRouteConfig]:
        """Generate UPDATE route configuration"""

        async def update_handler(
            crud: SingleModelCRUD,
            resource_id: str,
            item: Any,
            background_tasks: BackgroundTasks,
        ):
            """更新資源"""
            try:
                # 如果 item 是 Pydantic 模型，轉換為字典
                if hasattr(item, "model_dump"):
                    item_dict = item.model_dump()
                elif hasattr(item, "dict"):
                    item_dict = item.dict()
                else:
                    item_dict = item

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

        # 生成請求模型
        request_model = crud.schema_analyzer.get_create_model()

        # 生成響應模型
        fields = self.converter.extract_fields(crud.model)
        response_model = create_model(
            f"{crud.model.__name__}Response",
            **{name: (field_type, ...) for name, field_type in fields.items()},
        )

        # 設置類型提示
        update_handler.__annotations__["item"] = request_model

        return [
            PluginRouteConfig(
                name="update",
                path=f"/{crud.resource_name}/{{resource_id}}",
                method=RouteMethod.PUT,
                handler=update_handler,
                options=RouteOptions.enabled_route(),
                response_model=response_model,
                status_code=status.HTTP_200_OK,
                summary=f"更新 {crud.model.__name__}",
                description=f"更新指定 ID 的 {crud.model.__name__} 資源",
                priority=30,
            )
        ]


class DeleteRoutePlugin(BaseRoutePlugin):
    """Plugin for DELETE route (DELETE /{resource}/{id})"""

    def __init__(self):
        super().__init__("delete", "1.0.0")

    def get_routes(self, crud: SingleModelCRUD) -> List[PluginRouteConfig]:
        """Generate DELETE route configuration"""

        async def delete_handler(
            crud: SingleModelCRUD, resource_id: str, background_tasks: BackgroundTasks
        ):
            """刪除資源"""
            success = crud.delete(resource_id)
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="資源不存在"
                )
            # DELETE 路由的回傳值是 None (204 No Content)
            return None

        return [
            PluginRouteConfig(
                name="delete",
                path=f"/{crud.resource_name}/{{resource_id}}",
                method=RouteMethod.DELETE,
                handler=delete_handler,
                options=RouteOptions.enabled_route(),
                status_code=status.HTTP_204_NO_CONTENT,
                summary=f"刪除 {crud.model.__name__}",
                description=f"刪除指定 ID 的 {crud.model.__name__} 資源",
                priority=40,
            )
        ]


class CountRoutePlugin(BaseRoutePlugin):
    """Plugin for COUNT route (GET /{resource}/count)"""

    def __init__(self):
        super().__init__("count", "1.0.0")

    def get_routes(self, crud: SingleModelCRUD) -> List[PluginRouteConfig]:
        """Generate COUNT route configuration"""

        async def count_handler(
            crud: SingleModelCRUD, background_tasks: BackgroundTasks
        ):
            """獲取資源總數"""
            count = crud.count()
            return {"count": count}

        return [
            PluginRouteConfig(
                name="count",
                path=f"/{crud.resource_name}/count",
                method=RouteMethod.GET,
                handler=count_handler,
                options=RouteOptions.enabled_route(),
                summary=f"統計 {crud.model.__name__} 數量",
                description=f"獲取 {crud.model.__name__} 資源的總數量",
                priority=5,  # 高優先級，確保在 {resource_id} 路由之前
            )
        ]


class ListRoutePlugin(BaseRoutePlugin):
    """Plugin for LIST route (GET /{resource})"""

    def __init__(self):
        super().__init__("list", "1.0.0")

    def get_routes(self, crud: SingleModelCRUD) -> List[PluginRouteConfig]:
        """Generate LIST route configuration"""

        async def list_handler(
            crud: SingleModelCRUD,
            background_tasks: BackgroundTasks,
            # 分頁參數
            page: int = Query(1, ge=1, description="頁碼"),
            page_size: int = Query(20, ge=1, le=1000, description="每頁大小"),
            # 過濾參數
            created_by: Optional[List[str]] = Query(None, description="按創建者過濾"),
            updated_by: Optional[List[str]] = Query(None, description="按更新者過濾"),
            created_time_start: Optional[datetime] = Query(
                None, description="創建時間開始"
            ),
            created_time_end: Optional[datetime] = Query(
                None, description="創建時間結束"
            ),
            updated_time_start: Optional[datetime] = Query(
                None, description="更新時間開始"
            ),
            updated_time_end: Optional[datetime] = Query(
                None, description="更新時間結束"
            ),
            # 排序參數
            sort_by: Optional[str] = Query(None, description="排序字段"),
            sort_order: SortOrder = Query(SortOrder.DESC, description="排序順序"),
            # 向後兼容：簡單模式
            simple: bool = Query(
                False, description="簡單模式（返回項目列表而非分頁結果）"
            ),
        ):
            """列出所有資源"""
            # 檢查是否使用了任何高級查詢參數
            has_advanced_params = any(
                [
                    page != 1,
                    page_size != 20,
                    created_by,
                    updated_by,
                    created_time_start,
                    created_time_end,
                    updated_time_start,
                    updated_time_end,
                    sort_by,
                ]
            )

            if not has_advanced_params and simple:
                # 向後兼容：返回簡單的項目列表
                items = crud.list_all()
                return items
            else:
                # 構建查詢參數
                params = ListQueryParams(
                    page=page,
                    page_size=page_size,
                    created_by_filter=created_by,
                    updated_by_filter=updated_by,
                    created_time_range=DateTimeRange(
                        start=created_time_start, end=created_time_end
                    )
                    if created_time_start or created_time_end
                    else None,
                    updated_time_range=DateTimeRange(
                        start=updated_time_start, end=updated_time_end
                    )
                    if updated_time_start or updated_time_end
                    else None,
                    sort_by=sort_by,
                    sort_order=sort_order,
                )

                if simple:
                    # 簡單模式：只返回項目列表
                    items = crud.list_all(params)
                    return items
                else:
                    # 高級模式：返回分頁結果
                    result = crud.list_with_params(params)
                    return result

        return [
            PluginRouteConfig(
                name="list",
                path=f"/{crud.resource_name}",
                method=RouteMethod.GET,
                handler=list_handler,
                options=RouteOptions.enabled_route(),
                summary=f"列出 {crud.model.__name__}",
                description=f"列出所有 {crud.model.__name__} 資源，支援分頁、過濾和排序",
                priority=50,  # 低優先級，確保在具體路徑之後
            )
        ]


# 創建所有預設 plugin 實例
default_create_plugin = CreateRoutePlugin()
default_get_plugin = GetRoutePlugin()
default_update_plugin = UpdateRoutePlugin()
default_delete_plugin = DeleteRoutePlugin()
default_count_plugin = CountRoutePlugin()
default_list_plugin = ListRoutePlugin()

# 將所有預設 plugins 導出
DEFAULT_PLUGINS = [
    default_create_plugin,
    default_get_plugin,
    default_update_plugin,
    default_delete_plugin,
    default_count_plugin,
    default_list_plugin,
]
