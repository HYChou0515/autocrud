from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import StrEnum
from typing import Literal, TypeVar, Any
import re
import datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import create_model
import msgspec

from autocrud.v03.resource_manager.basic import IStorage
from autocrud.v03.resource_manager.core import ResourceManager


class NamingFormat(StrEnum):
    """命名格式枚舉"""

    SAME = "same"
    PASCAL = "pascal"
    CAMEL = "camel"
    SNAKE = "snake"
    KEBAB = "kebab"
    UNKNOWN = "unknown"


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

                with resource_manager.meta_provide("system", datetime.datetime.now()):
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
        # 動態創建響應模型
        resource_type = resource_manager.resource_type

        # 創建包含資源數據和元數據的響應模型
        response_model = create_model(
            f"{resource_type.__name__}ReadResponse",
            resource_id=(str, ...),
            revision_id=(str, ...),
            data=(Any, ...),  # 使用 Any 來避免 Pydantic 處理 msgspec 類型的問題
        )

        @router.get(f"/{model_name}/{{resource_id}}", response_model=response_model)
        async def get_resource(resource_id: str) -> dict:
            try:
                with resource_manager.meta_provide("system", datetime.datetime.now()):
                    resource = resource_manager.get(resource_id)

                # 使用 msgspec.to_builtins 直接轉換為字典
                data_json = msgspec.to_builtins(resource.data)

                return {
                    "resource_id": resource.info.resource_id,
                    "revision_id": resource.info.revision_id,
                    "data": data_json,
                }
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

                with resource_manager.meta_provide("system", datetime.datetime.now()):
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
                with resource_manager.meta_provide("system", datetime.datetime.now()):
                    meta = resource_manager.delete(resource_id)
                return {"resource_id": meta.resource_id, "deleted": True}
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))


class ListRouteTemplate(IRouteTemplate):
    """列出所有資源的路由模板"""

    def apply(
        self, model_name: str, resource_manager: ResourceManager[T], router: APIRouter
    ) -> None:
        # 動態創建資源摘要模型
        resource_summary_model = create_model(
            f"{resource_manager.resource_type.__name__}Summary",
            resource_id=(str, ...),
            updated_time=(str, ...),
        )

        # 動態創建列表響應模型
        list_response_model = create_model(
            f"{resource_manager.resource_type.__name__}ListResponse",
            resources=(list[resource_summary_model], ...),
        )

        @router.get(f"/{model_name}", response_model=list_response_model)
        async def list_resources() -> dict:
            try:
                from autocrud.v03.resource_manager.basic import ResourceMetaSearchQuery

                with resource_manager.meta_provide("system", datetime.datetime.now()):
                    query = ResourceMetaSearchQuery()
                    metas = resource_manager.search_resources(query)
                return {
                    "resources": [
                        {
                            "resource_id": meta.resource_id,
                            "updated_time": meta.updated_time.isoformat(),
                        }
                        for meta in metas
                    ]
                }
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

                with resource_manager.meta_provide("system", datetime.datetime.now()):
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
