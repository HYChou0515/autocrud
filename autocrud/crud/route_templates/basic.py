import datetime as dt
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Generic, TypeVar

import msgspec
from fastapi import APIRouter, Response

from autocrud.types import IResourceManager
from autocrud.types import ResourceMeta, RevisionInfo

T = TypeVar("T")


class IRouteTemplate(ABC):
    """路由模板基類，定義如何為資源生成單一 API 路由"""

    @abstractmethod
    def apply(
        self,
        model_name: str,
        resource_manager: IResourceManager[T],
        router: APIRouter,
    ) -> None:
        """將路由模板應用到指定的資源管理器和路由器

        Args:
            model_name: 模型名稱
            resource_manager: 資源管理器
            router: FastAPI 路由器
        """

    @property
    @abstractmethod
    def order(self) -> int:
        """獲取路由模板的排序權重"""


class DependencyProvider:
    """依賴提供者，統一管理用戶和時間的依賴函數"""

    def __init__(self, get_user: Callable = None, get_now: Callable = None):
        """初始化依賴提供者

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


class BaseRouteTemplate(IRouteTemplate):
    def __init__(
        self,
        dependency_provider: DependencyProvider = None,
        order: int = 100,
    ):
        """初始化路由模板

        Args:
            dependency_provider: 依賴提供者，如果為 None 則創建預設的
        """
        self.deps = dependency_provider or DependencyProvider()
        self._order = order

    @property
    def order(self) -> int:
        return self._order

    def __lt__(self, other: IRouteTemplate):
        return self.order < other.order

    def __le__(self, other: IRouteTemplate):
        return self.order <= other.order


class MsgspecResponse(Response):
    media_type = "application/json"

    def render(self, content: msgspec.Struct) -> bytes:
        return msgspec.json.encode(content)


def jsonschema_to_openapi(structs: list[msgspec.Struct]) -> dict:
    return msgspec.json.schema_components(
        structs,
        ref_template="#/components/schemas/{name}",
    )


def jsonschema_to_json_schema_extra(struct: msgspec.Struct) -> dict:
    return jsonschema_to_openapi([struct])[0][0]


def struct_to_responses_type(struct: type[msgspec.Struct], status_code: int = 200):
    schema = jsonschema_to_json_schema_extra(struct)
    return {
        status_code: {
            "content": {"application/json": {"schema": schema}},
        },
    }


class RevisionListResponse(msgspec.Struct):
    meta: ResourceMeta
    revisions: list[RevisionInfo]


class FullResourceResponse(msgspec.Struct, Generic[T]):
    data: T | msgspec.UnsetType = msgspec.UNSET
    revision_info: RevisionInfo | msgspec.UnsetType = msgspec.UNSET
    meta: ResourceMeta | msgspec.UnsetType = msgspec.UNSET
