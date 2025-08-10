from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import StrEnum
from typing import Literal, TypeVar, Any
import re
import datetime as dt
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import create_model, BaseModel
import msgspec
from typing import Optional

from autocrud.v03.resource_manager.basic import IStorage
from autocrud.v03.resource_manager.core import ResourceManager


# Pydantic 版本的 ResourceMeta
class ResourceMetaResponse(BaseModel):
    current_revision_id: str
    resource_id: str
    schema_version: Optional[str] = None
    total_revision_count: int
    created_time: datetime  # 使用原生 datetime
    updated_time: datetime  # 使用原生 datetime
    created_by: str
    updated_by: str
    is_deleted: bool = False


# Pydantic 版本的 RevisionInfo
class RevisionInfoResponse(BaseModel):
    uid: str  # UUID as string
    resource_id: str
    revision_id: str
    parent_revision_id: Optional[str] = None
    schema_version: Optional[str] = None
    data_hash: Optional[str] = None
    status: str


class NamingFormat(StrEnum):
    """命名格式枚舉"""

    SAME = "same"
    PASCAL = "pascal"
    CAMEL = "camel"
    SNAKE = "snake"
    KEBAB = "kebab"
    UNKNOWN = "unknown"


class ListResponseType(StrEnum):
    """列表響應類型枚舉"""

    DATA = "data"  # 只返回資源數據
    META = "meta"  # 只返回 ResourceMeta
    REVISION_INFO = "revision_info"  # 只返回 RevisionInfo
    FULL = "full"  # 返回所有信息 (data, meta, revision_info)


def convert_resource_meta_to_response(meta) -> ResourceMetaResponse:
    """將 ResourceMeta 轉換為 Pydantic 響應對象"""
    from msgspec import UNSET

    return ResourceMetaResponse(
        current_revision_id=meta.current_revision_id,
        resource_id=meta.resource_id,
        schema_version=meta.schema_version
        if meta.schema_version is not UNSET
        else None,
        total_revision_count=meta.total_revision_count,
        created_time=meta.created_time,  # 直接使用 datetime 對象
        updated_time=meta.updated_time,  # 直接使用 datetime 對象
        created_by=meta.created_by,
        updated_by=meta.updated_by,
        is_deleted=meta.is_deleted,
    )


def convert_revision_info_to_response(info) -> RevisionInfoResponse:
    """將 RevisionInfo 轉換為 Pydantic 響應對象"""
    from msgspec import UNSET

    return RevisionInfoResponse(
        uid=str(info.uid),
        resource_id=info.resource_id,
        revision_id=info.revision_id,
        parent_revision_id=info.parent_revision_id
        if info.parent_revision_id is not UNSET
        else None,
        schema_version=info.schema_version
        if info.schema_version is not UNSET
        else None,
        data_hash=info.data_hash if info.data_hash is not UNSET else None,
        status=info.status,
    )


class NameConverter:
    """名稱轉換器，用於在不同命名格式之間轉換"""

    def __init__(self, original_name: str):
        self.original_name = original_name
        self._current_format = self._detect_format()

    def _detect_format(self) -> NamingFormat:
        """檢測名稱的格式"""
        name = self.original_name

        if not name:
            return NamingFormat.UNKNOWN

        # 檢查是否包含底線 (snake_case)
        if "_" in name:
            return NamingFormat.SNAKE

        # 檢查是否包含連字符 (kebab-case)
        if "-" in name:
            return NamingFormat.KEBAB

        # 檢查是否是 PascalCase (首字母大寫)
        if name[0].isupper() and re.search(r"[A-Z]", name[1:]):
            return NamingFormat.PASCAL

        # 檢查是否是 camelCase (首字母小寫，但後面有大寫)
        if name[0].islower() and re.search(r"[A-Z]", name):
            return NamingFormat.CAMEL

        # 檢查是否首字母大寫但沒有其他大寫字母
        if name[0].isupper() and name[1:].islower():
            return NamingFormat.PASCAL

        return NamingFormat.UNKNOWN

    def _to_snake_case(self) -> str:
        """將名稱轉換為 snake_case"""
        name = self.original_name

        if self._current_format == NamingFormat.SNAKE:
            return name.lower()
        elif self._current_format == NamingFormat.KEBAB:
            return name.replace("-", "_").lower()
        elif self._current_format in [NamingFormat.PASCAL, NamingFormat.CAMEL]:
            # PascalCase/camelCase -> snake_case
            snake_case = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
            snake_case = re.sub("([a-z0-9])([A-Z])", r"\1_\2", snake_case).lower()
            return snake_case
        else:
            # unknown，直接轉為小寫
            return name.lower()

    def to(self, target_format: NamingFormat | str) -> str:
        """轉換為指定格式"""
        if isinstance(target_format, str):
            target_format = NamingFormat(target_format)

        if target_format == NamingFormat.SAME:
            return self.original_name

        # 先轉換為 snake_case 作為中間格式
        snake_name = self._to_snake_case()

        if target_format == NamingFormat.SNAKE:
            return snake_name
        elif target_format == NamingFormat.KEBAB:
            return snake_name.replace("_", "-")
        elif target_format == NamingFormat.PASCAL:
            return "".join(word.capitalize() for word in snake_name.split("_"))
        elif target_format == NamingFormat.CAMEL:
            components = snake_name.split("_")
            return components[0] + "".join(word.capitalize() for word in components[1:])
        else:
            return self.original_name


T = TypeVar("T")


class IRouteTemplate(ABC):
    """路由模板基類，定義如何為資源生成單一 API 路由"""

    @abstractmethod
    def apply(
        self, model_name: str, resource_manager: ResourceManager[T], router: APIRouter
    ) -> None:
        """將路由模板應用到指定的資源管理器和路由器

        Args:
            model_name: 模型名稱
            resource_manager: 資源管理器
            router: FastAPI 路由器
        """
        raise NotImplementedError("子類必須實作 apply 方法")


class CreateRouteTemplate(IRouteTemplate):
    """創建資源的路由模板"""

    def apply(
        self, model_name: str, resource_manager: ResourceManager[T], router: APIRouter
    ) -> None:
        # 動態創建響應模型
        create_response_model = create_model(
            f"{resource_manager.resource_type.__name__}CreateResponse",
            resource_id=(str, ...),
            revision_id=(str, ...),
        )

        resource_type = resource_manager.resource_type

        @router.post(f"/{model_name}", response_model=create_response_model)
        async def create_resource(request: Request) -> dict:
            try:
                # 直接接收原始 JSON bytes
                json_bytes = await request.body()

                # 使用 msgspec 直接從 JSON bytes 轉換為目標類型
                data = msgspec.json.decode(json_bytes, type=resource_type)

                with resource_manager.meta_provide("system", dt.datetime.now()):
                    info = resource_manager.create(data)
                return {
                    "resource_id": info.resource_id,
                    "revision_id": info.revision_id,
                }
            except msgspec.ValidationError as e:
                # 數據驗證錯誤，返回 422
                raise HTTPException(status_code=422, detail=str(e))
            except Exception as e:
                # 其他錯誤，返回 400
                raise HTTPException(status_code=400, detail=str(e))


class ReadRouteTemplate(IRouteTemplate):
    """讀取單一資源的路由模板"""

    def apply(
        self, model_name: str, resource_manager: ResourceManager[T], router: APIRouter
    ) -> None:
        # 根據不同的響應類型創建不同的響應模型
        @router.get(f"/{model_name}/{{resource_id}}")
        async def get_resource(
            resource_id: str,
            response_type: ListResponseType = Query(
                ...,
                description="Type of data to return: data, meta, revision_info, or full",
            ),
        ):
            try:
                with resource_manager.meta_provide("system", dt.datetime.now()):
                    resource = resource_manager.get(resource_id)
                    meta = resource_manager.get_meta(resource_id)

                # 根據響應類型返回不同的數據
                if response_type == ListResponseType.DATA:
                    # 只返回資源數據
                    return msgspec.to_builtins(resource.data)
                elif response_type == ListResponseType.META:
                    # 只返回 ResourceMeta (使用 Pydantic 模型)
                    return convert_resource_meta_to_response(meta)
                elif response_type == ListResponseType.REVISION_INFO:
                    # 只返回 RevisionInfo (使用 Pydantic 模型)
                    return convert_revision_info_to_response(resource.info)
                elif response_type == ListResponseType.FULL:
                    # 返回所有信息
                    return {
                        "data": msgspec.to_builtins(resource.data),
                        "meta": convert_resource_meta_to_response(meta),
                        "revision_info": convert_revision_info_to_response(
                            resource.info
                        ),
                    }
                else:
                    # 預設返回資源數據
                    return msgspec.to_builtins(resource.data)

            except Exception as e:
                raise HTTPException(status_code=404, detail=str(e))


class UpdateRouteTemplate(IRouteTemplate):
    """更新資源的路由模板"""

    def apply(
        self, model_name: str, resource_manager: ResourceManager[T], router: APIRouter
    ) -> None:
        # 動態創建響應模型
        update_response_model = create_model(
            f"{resource_manager.resource_type.__name__}UpdateResponse",
            resource_id=(str, ...),
            revision_id=(str, ...),
        )

        resource_type = resource_manager.resource_type

        @router.put(
            f"/{model_name}/{{resource_id}}", response_model=update_response_model
        )
        async def update_resource(resource_id: str, request: Request) -> dict:
            try:
                # 直接接收原始 JSON bytes
                json_bytes = await request.body()

                # 使用 msgspec 直接從 JSON bytes 轉換為目標類型
                data = msgspec.json.decode(json_bytes, type=resource_type)

                with resource_manager.meta_provide("system", dt.datetime.now()):
                    info = resource_manager.update(resource_id, data)
                return {
                    "resource_id": info.resource_id,
                    "revision_id": info.revision_id,
                }
            except msgspec.ValidationError as e:
                # 數據驗證錯誤，返回 422
                raise HTTPException(status_code=422, detail=str(e))
            except Exception as e:
                # 其他錯誤，返回 400
                raise HTTPException(status_code=400, detail=str(e))


class DeleteRouteTemplate(IRouteTemplate):
    """刪除資源的路由模板"""

    def apply(
        self, model_name: str, resource_manager: ResourceManager[T], router: APIRouter
    ) -> None:
        # 動態創建響應模型
        delete_response_model = create_model(
            f"{resource_manager.resource_type.__name__}DeleteResponse",
            resource_id=(str, ...),
            deleted=(bool, ...),
        )

        @router.delete(
            f"/{model_name}/{{resource_id}}", response_model=delete_response_model
        )
        async def delete_resource(resource_id: str) -> dict:
            try:
                with resource_manager.meta_provide("system", dt.datetime.now()):
                    meta = resource_manager.delete(resource_id)
                return {"resource_id": meta.resource_id, "deleted": True}
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))


class ListRouteTemplate(IRouteTemplate):
    """列出所有資源的路由模板"""

    def apply(
        self, model_name: str, resource_manager: ResourceManager[T], router: APIRouter
    ) -> None:
        from autocrud.v03.resource_manager.basic import ResourceMetaSearchQuery
        from typing import Optional

        # 動態創建列表響應模型
        list_response_model = create_model(
            f"{resource_manager.resource_type.__name__}ListResponse",
            resources=(list[Any], ...),
        )

        @router.get(f"/{model_name}", response_model=list_response_model)
        async def list_resources(
            # 響應類型選擇
            response_type: ListResponseType = Query(
                description="Type of data to return: data, meta, revision_info, resource, or full"
            ),
            # ResourceMetaSearchQuery 的查詢參數
            is_deleted: Optional[bool] = Query(
                None, description="Filter by deletion status"
            ),
            created_time_start: Optional[str] = Query(
                None, description="Filter by created time start (ISO format)"
            ),
            created_time_end: Optional[str] = Query(
                None, description="Filter by created time end (ISO format)"
            ),
            updated_time_start: Optional[str] = Query(
                None, description="Filter by updated time start (ISO format)"
            ),
            updated_time_end: Optional[str] = Query(
                None, description="Filter by updated time end (ISO format)"
            ),
            created_bys: Optional[list[str]] = Query(
                None, description="Filter by creators"
            ),
            updated_bys: Optional[list[str]] = Query(
                None, description="Filter by updaters"
            ),
            limit: int = Query(10, description="Maximum number of results"),
            offset: int = Query(0, description="Number of results to skip"),
        ) -> dict:
            try:
                from msgspec import UNSET
                import datetime as dt

                # 構建查詢對象
                query_kwargs = {
                    "limit": limit,
                    "offset": offset,
                }

                if is_deleted is not None:
                    query_kwargs["is_deleted"] = is_deleted
                else:
                    query_kwargs["is_deleted"] = UNSET

                if created_time_start:
                    query_kwargs["created_time_start"] = dt.datetime.fromisoformat(
                        created_time_start
                    )
                else:
                    query_kwargs["created_time_start"] = UNSET

                if created_time_end:
                    query_kwargs["created_time_end"] = dt.datetime.fromisoformat(
                        created_time_end
                    )
                else:
                    query_kwargs["created_time_end"] = UNSET

                if updated_time_start:
                    query_kwargs["updated_time_start"] = dt.datetime.fromisoformat(
                        updated_time_start
                    )
                else:
                    query_kwargs["updated_time_start"] = UNSET

                if updated_time_end:
                    query_kwargs["updated_time_end"] = dt.datetime.fromisoformat(
                        updated_time_end
                    )
                else:
                    query_kwargs["updated_time_end"] = UNSET

                if created_bys:
                    query_kwargs["created_bys"] = created_bys
                else:
                    query_kwargs["created_bys"] = UNSET

                if updated_bys:
                    query_kwargs["updated_bys"] = updated_bys
                else:
                    query_kwargs["updated_bys"] = UNSET

                query_kwargs["sorts"] = UNSET

                query = ResourceMetaSearchQuery(**query_kwargs)

                with resource_manager.meta_provide("system", dt.datetime.now()):
                    metas = resource_manager.search_resources(query)

                    # 根據響應類型處理資源數據
                    resources_data = []
                    for meta in metas:
                        try:
                            if response_type == ListResponseType.META:
                                # 只返回 ResourceMeta
                                resources_data.append(msgspec.to_builtins(meta))
                            elif response_type == ListResponseType.REVISION_INFO:
                                # 只返回 RevisionInfo，需要獲取 resource
                                resource = resource_manager.get(meta.resource_id)
                                resources_data.append(
                                    msgspec.to_builtins(resource.info)
                                )
                            elif response_type == ListResponseType.FULL:
                                # 返回所有信息
                                resource = resource_manager.get(meta.resource_id)
                                resources_data.append(
                                    {
                                        "data": msgspec.to_builtins(resource.data),
                                        "meta": msgspec.to_builtins(meta),
                                        "revision_info": msgspec.to_builtins(
                                            resource.info
                                        ),
                                    }
                                )
                            else:  # ListResponseType.DATA (預設)
                                # 只返回資源數據
                                resource = resource_manager.get(meta.resource_id)
                                resources_data.append(
                                    msgspec.to_builtins(resource.data)
                                )
                        except Exception:
                            # 如果無法獲取資源數據，跳過
                            continue

                return {"resources": resources_data}
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))


class PatchRouteTemplate(IRouteTemplate):
    """部分更新資源的路由模板"""

    def apply(
        self, model_name: str, resource_manager: ResourceManager[T], router: APIRouter
    ) -> None:
        # 動態創建響應模型
        patch_response_model = create_model(
            f"{resource_manager.resource_type.__name__}PatchResponse",
            resource_id=(str, ...),
            revision_id=(str, ...),
        )

        @router.patch(
            f"/{model_name}/{{resource_id}}", response_model=patch_response_model
        )
        async def patch_resource(resource_id: str, patch_data: list[dict]) -> dict:
            try:
                from jsonpatch import JsonPatch

                with resource_manager.meta_provide("system", dt.datetime.now()):
                    patch = JsonPatch(patch_data)
                    info = resource_manager.patch(resource_id, patch)
                return {
                    "resource_id": info.resource_id,
                    "revision_id": info.revision_id,
                }
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))


class AutoCRUD:
    def __init__(
        self,
        *,
        model_naming: Literal["same", "pascal", "camel", "snake", "kebab"]
        | Callable[[type], str] = "kebab",
    ):
        self.resource_managers: dict[str, ResourceManager] = {}
        self.model_naming = model_naming
        self.route_templates: list[IRouteTemplate] = []

    def _resource_name(self, model: type[T]) -> str:
        if callable(self.model_naming):
            return self.model_naming(model)
        original_name = model.__name__

        # 使用 NameConverter 進行轉換
        return NameConverter(original_name).to(self.model_naming)

    def add_route_template(self, template: IRouteTemplate) -> None:
        """添加路由模板"""
        self.route_templates.append(template)

    def add_model(
        self,
        model: type[T],
        *,
        name: str | None = None,
        storage_factory: Callable[[], IStorage[T]],
    ) -> None:
        """
        Add a model to the AutoCRUD system.

        :param model: The model class to add.
        :param storage_factory: A callable that returns an IStorage instance for the model.
        :return: An instance of the model.
        """
        storage = storage_factory()
        resource_manager = ResourceManager(model, storage=storage)
        model_name = name or self._resource_name(model)
        self.resource_managers[model_name] = resource_manager

    def apply(self, router: APIRouter) -> APIRouter:
        """將所有路由模板應用到所有模型"""
        for model_name, resource_manager in self.resource_managers.items():
            for route_template in self.route_templates:
                route_template.apply(model_name, resource_manager, router)
        return router
