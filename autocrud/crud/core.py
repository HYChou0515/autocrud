from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import StrEnum
from typing import Literal, TypeVar, Any
import re
import datetime as dt

from fastapi import APIRouter, HTTPException, Request, Query, Depends
from pydantic import create_model, BaseModel
import msgspec
from typing import Optional

from autocrud.resource_manager.basic import IStorage, ResourceMeta, RevisionInfo
from autocrud.resource_manager.core import ResourceManager


# Pydantic 版本的 ResourceMeta
class ResourceMetaResponse(BaseModel):
    current_revision_id: str
    resource_id: str
    schema_version: Optional[str] = None
    total_revision_count: int
    created_time: dt.datetime  # 使用原生 dt.datetime
    updated_time: dt.datetime  # 使用原生 dt.datetime
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
    REVISIONS = "revisions"  # 返回 meta 和所有 revision info


def convert_resource_meta_to_response(meta: ResourceMeta) -> ResourceMetaResponse:
    """將 ResourceMeta 轉換為 Pydantic 響應對象"""
    from msgspec import UNSET

    return ResourceMetaResponse(
        current_revision_id=meta.current_revision_id,
        resource_id=meta.resource_id,
        schema_version=meta.schema_version
        if meta.schema_version is not UNSET
        else None,
        total_revision_count=meta.total_revision_count,
        created_time=meta.created_time,  # 直接使用 dt.datetime 對象
        updated_time=meta.updated_time,  # 直接使用 dt.datetime 對象
        created_by=meta.created_by,
        updated_by=meta.updated_by,
        is_deleted=meta.is_deleted,
    )


def convert_revision_info_to_response(info: RevisionInfo) -> RevisionInfoResponse:
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


class DependencyProvider:
    """依賴提供者，統一管理用戶和時間的依賴函數"""

    def __init__(self, get_user: Callable = None, get_now: Callable = None):
        """
        初始化依賴提供者

        Args:
            get_user: 獲取當前用戶的 dependency 函數，如果為 None 則創建預設函數
            get_now: 獲取當前時間的 dependency 函數，如果為 None 則創建預設函數
        """
        # 如果沒有提供 get_user，創建一個預設的 dependency 函數
        self.get_user = get_user or self._create_default_user_dependency()
        # 如果沒有提供 get_now，創建一個預設的 dependency 函數
        self.get_now = get_now or self._create_default_now_dependency()

    def _create_default_user_dependency(self) -> Callable:
        """創建預設的用戶 dependency 函數"""

        def default_get_user() -> str:
            return "anonymous"

        return default_get_user

    def _create_default_now_dependency(self) -> Callable:
        """創建預設的時間 dependency 函數"""

        def default_get_now() -> dt.datetime:
            return dt.datetime.now()

        return default_get_now


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


class BaseRouteTemplate(IRouteTemplate):
    def __init__(self, dependency_provider: DependencyProvider = None):
        """
        初始化路由模板

        Args:
            dependency_provider: 依賴提供者，如果為 None 則創建預設的
        """
        self.deps = dependency_provider or DependencyProvider()


class CreateRouteTemplate(BaseRouteTemplate):
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
        async def create_resource(
            request: Request,
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ) -> dict:
            try:
                # 直接接收原始 JSON bytes
                json_bytes = await request.body()

                # 使用 msgspec 直接從 JSON bytes 轉換為目標類型
                data = msgspec.json.decode(json_bytes, type=resource_type)

                with resource_manager.meta_provide(current_user, current_time):
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


class ReadRouteTemplate(BaseRouteTemplate):
    """讀取單一資源的路由模板"""

    def _get_resource_and_meta(
        self,
        resource_manager: ResourceManager[T],
        resource_id: str,
        revision_id: Optional[str],
        current_user: str,
        current_time: dt.datetime,
    ) -> tuple[Any, Optional[ResourceMeta]]:
        """獲取資源和元數據"""
        with resource_manager.meta_provide(current_user, current_time):
            if revision_id:
                resource = resource_manager.storage.get_resource_revision(
                    resource_id, revision_id
                )
                meta = None
            else:
                resource = resource_manager.get(resource_id)
                meta = resource_manager.get_meta(resource_id)
        return resource, meta

    def _handle_meta_response(self, meta: Optional[ResourceMeta]) -> dict:
        """處理 META 響應類型"""
        if not meta:
            raise HTTPException(
                status_code=400,
                detail="Meta not available for specific revision",
            )
        return convert_resource_meta_to_response(meta)

    def _handle_revision_info_response(self, resource: Any) -> dict:
        """處理 REVISION_INFO 響應類型"""
        return convert_revision_info_to_response(resource.info)

    def _handle_full_response(
        self, resource: Any, meta: Optional[ResourceMeta]
    ) -> dict:
        """處理 FULL 響應類型"""
        result = {
            "data": msgspec.to_builtins(resource.data),
            "revision_info": convert_revision_info_to_response(resource.info),
        }
        if meta:
            result["meta"] = convert_resource_meta_to_response(meta)
        return result

    def _handle_revisions_response(
        self,
        resource_manager: ResourceManager[T],
        resource_id: str,
        revision_id: Optional[str],
        meta: Optional[ResourceMeta],
        current_user: str,
        current_time: dt.datetime,
    ) -> dict:
        """處理 REVISIONS 響應類型"""
        if revision_id:
            raise HTTPException(
                status_code=400,
                detail="Cannot list revisions when specific revision_id is provided",
            )

        if not meta:
            raise HTTPException(
                status_code=400,
                detail="Meta not available for revisions response",
            )

        with resource_manager.meta_provide(current_user, current_time):
            revision_ids = resource_manager.storage.list_revisions(resource_id)
            revision_infos = []
            for rev_id in revision_ids:
                try:
                    rev_resource = resource_manager.storage.get_resource_revision(
                        resource_id, rev_id
                    )
                    revision_infos.append(
                        convert_revision_info_to_response(rev_resource.info)
                    )
                except Exception:
                    # 如果無法獲取某個版本，跳過
                    continue

            return {
                "meta": convert_resource_meta_to_response(meta),
                "revisions": revision_infos,
            }

    def _handle_data_response(self, resource: Any) -> dict:
        """處理 DATA 響應類型（預設）"""
        return msgspec.to_builtins(resource.data)

    def apply(
        self, model_name: str, resource_manager: ResourceManager[T], router: APIRouter
    ) -> None:
        @router.get(f"/{model_name}/{{resource_id}}")
        async def get_resource(
            resource_id: str,
            response_type: ListResponseType = Query(
                ListResponseType.DATA,
                description="Type of data to return: data, meta, revision_info, full, or revisions",
            ),
            revision_id: Optional[str] = Query(
                None,
                description="Specific revision ID to retrieve. If not provided, returns the current revision",
            ),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            # 獲取資源和元數據
            try:
                resource, meta = self._get_resource_and_meta(
                    resource_manager,
                    resource_id,
                    revision_id,
                    current_user,
                    current_time,
                )
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=404, detail=str(e))

            # 根據響應類型處理數據
            if response_type == ListResponseType.META:
                return self._handle_meta_response(meta)

            elif response_type == ListResponseType.REVISION_INFO:
                return self._handle_revision_info_response(resource)

            elif response_type == ListResponseType.FULL:
                return self._handle_full_response(resource, meta)

            elif response_type == ListResponseType.REVISIONS:
                return self._handle_revisions_response(
                    resource_manager,
                    resource_id,
                    revision_id,
                    meta,
                    current_user,
                    current_time,
                )

            else:  # DATA (預設)
                return self._handle_data_response(resource)


class UpdateRouteTemplate(BaseRouteTemplate):
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
        async def update_resource(
            resource_id: str,
            request: Request,
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ) -> dict:
            try:
                # 直接接收原始 JSON bytes
                json_bytes = await request.body()

                # 使用 msgspec 直接從 JSON bytes 轉換為目標類型
                data = msgspec.json.decode(json_bytes, type=resource_type)

                with resource_manager.meta_provide(current_user, current_time):
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


class DeleteRouteTemplate(BaseRouteTemplate):
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
        async def delete_resource(
            resource_id: str,
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ) -> dict:
            try:
                with resource_manager.meta_provide(current_user, current_time):
                    meta = resource_manager.delete(resource_id)
                return {"resource_id": meta.resource_id, "deleted": True}
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))


class ListRouteTemplate(BaseRouteTemplate):
    """列出所有資源的路由模板"""

    def apply(
        self, model_name: str, resource_manager: ResourceManager[T], router: APIRouter
    ) -> None:
        from autocrud.resource_manager.basic import ResourceMetaSearchQuery
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
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ) -> dict:
            from msgspec import UNSET

            try:
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

                with resource_manager.meta_provide(current_user, current_time):
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


class PatchRouteTemplate(BaseRouteTemplate):
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
        async def patch_resource(
            resource_id: str,
            patch_data: list[dict],
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ) -> dict:
            from jsonpatch import JsonPatch

            try:
                with resource_manager.meta_provide(current_user, current_time):
                    patch = JsonPatch(patch_data)
                    info = resource_manager.patch(resource_id, patch)
                return {
                    "resource_id": info.resource_id,
                    "revision_id": info.revision_id,
                }
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))


class SwitchRevisionRouteTemplate(BaseRouteTemplate):
    """切換資源版本的路由模板"""

    def apply(
        self, model_name: str, resource_manager: ResourceManager[T], router: APIRouter
    ) -> None:
        # 動態創建響應模型
        switch_response_model = create_model(
            f"{resource_manager.resource_type.__name__}SwitchResponse",
            resource_id=(str, ...),
            current_revision_id=(str, ...),
            message=(str, ...),
        )

        @router.post(
            f"/{model_name}/{{resource_id}}/switch/{{revision_id}}",
            response_model=switch_response_model,
        )
        async def switch_revision(
            resource_id: str,
            revision_id: str,
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ) -> dict:
            try:
                with resource_manager.meta_provide(current_user, current_time):
                    meta = resource_manager.switch(resource_id, revision_id)
                return {
                    "resource_id": meta.resource_id,
                    "current_revision_id": meta.current_revision_id,
                    "message": f"Successfully switched to revision {revision_id}",
                }
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))


class RestoreRouteTemplate(BaseRouteTemplate):
    """恢復已刪除資源的路由模板"""

    def apply(
        self, model_name: str, resource_manager: ResourceManager[T], router: APIRouter
    ) -> None:
        # 動態創建響應模型
        restore_response_model = create_model(
            f"{resource_manager.resource_type.__name__}RestoreResponse",
            resource_id=(str, ...),
            current_revision_id=(str, ...),
            message=(str, ...),
            is_deleted=(bool, ...),
        )

        @router.post(
            f"/{model_name}/{{resource_id}}/restore",
            response_model=restore_response_model,
        )
        async def restore_resource(
            resource_id: str,
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ) -> dict:
            try:
                with resource_manager.meta_provide(current_user, current_time):
                    meta = resource_manager.restore(resource_id)
                return {
                    "resource_id": meta.resource_id,
                    "current_revision_id": meta.current_revision_id,
                    "is_deleted": meta.is_deleted,
                    "message": f"Successfully restored resource {resource_id}",
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
