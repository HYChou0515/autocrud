import datetime as dt
from abc import ABC, abstractmethod
from collections.abc import Callable
import json
from typing import Any, Generic, Optional, TypeVar

import msgspec
from fastapi import APIRouter, Response, HTTPException, Query
from pydantic import BaseModel

from autocrud.types import (
    DataSearchCondition,
    DataSearchOperator,
    IResourceManager,
    ResourceMetaSearchQuery,
)
from autocrud.types import ResourceMeta, RevisionInfo

from autocrud.types import (
    ResourceDataSearchSort,
    ResourceMetaSearchSort,
    ResourceMetaSortDirection,
    ResourceMetaSortKey,
)

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


def jsonschema_to_openapi(structs: list[msgspec.Struct | Any]) -> dict:
    return msgspec.json.schema_components(
        structs,
        ref_template="#/components/schemas/{name}",
    )


def jsonschema_to_json_schema_extra(struct: msgspec.Struct | Any) -> dict:
    return jsonschema_to_openapi([struct])[0][0]


def struct_to_responses_type(
    struct: type[msgspec.Struct | Any], status_code: int = 200
):
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


class QueryInputs(BaseModel):
    # ResourceMetaSearchQuery 的查詢參數
    is_deleted: Optional[bool] = Query(
        None,
        description="Filter by deletion status",
    )
    created_time_start: Optional[str] = Query(
        None,
        description="Filter by created time start (ISO format)",
    )
    created_time_end: Optional[str] = Query(
        None,
        description="Filter by created time end (ISO format)",
    )
    updated_time_start: Optional[str] = Query(
        None,
        description="Filter by updated time start (ISO format)",
    )
    updated_time_end: Optional[str] = Query(
        None,
        description="Filter by updated time end (ISO format)",
    )
    created_bys: Optional[list[str]] = Query(None, description="Filter by creators")
    updated_bys: Optional[list[str]] = Query(None, description="Filter by updaters")
    data_conditions: Optional[str] = Query(
        None,
        description='Data filter conditions in JSON format. Example: \'[{"field_path": "department", "operator": "eq", "value": "Engineering"}]\'',
    )
    sorts: Optional[str] = Query(
        None,
        description='Sort conditions in JSON format. Example: \'[{"type": "meta", "key": "created_time", "direction": "+"}, {"type": "data", "field_path": "name", "direction": "-"}]\'',
    )
    limit: int = Query(10, description="Maximum number of results")
    offset: int = Query(0, description="Number of results to skip")


class QueryInputsWithReturns(QueryInputs):
    returns: str = Query(
        default="data,revision_info,meta",
        description="Fields to return, comma-separated. Options: data, revision_info, meta",
    )


def build_query(q: QueryInputs) -> ResourceMetaSearchQuery:
    query_kwargs = {
        "limit": q.limit,
        "offset": q.offset,
    }

    if q.is_deleted is not None:
        query_kwargs["is_deleted"] = q.is_deleted
    else:
        query_kwargs["is_deleted"] = msgspec.UNSET

    if q.created_time_start:
        query_kwargs["created_time_start"] = dt.datetime.fromisoformat(
            q.created_time_start,
        )
    else:
        query_kwargs["created_time_start"] = msgspec.UNSET

    if q.created_time_end:
        query_kwargs["created_time_end"] = dt.datetime.fromisoformat(
            q.created_time_end,
        )
    else:
        query_kwargs["created_time_end"] = msgspec.UNSET

    if q.updated_time_start:
        query_kwargs["updated_time_start"] = dt.datetime.fromisoformat(
            q.updated_time_start,
        )
    else:
        query_kwargs["updated_time_start"] = msgspec.UNSET

    if q.updated_time_end:
        query_kwargs["updated_time_end"] = dt.datetime.fromisoformat(
            q.updated_time_end,
        )
    else:
        query_kwargs["updated_time_end"] = msgspec.UNSET

    if q.created_bys:
        query_kwargs["created_bys"] = q.created_bys
    else:
        query_kwargs["created_bys"] = msgspec.UNSET

    if q.updated_bys:
        query_kwargs["updated_bys"] = q.updated_bys
    else:
        query_kwargs["updated_bys"] = msgspec.UNSET

    # 處理 data_conditions
    if q.data_conditions:
        try:
            # 解析 JSON 字符串
            conditions_data = json.loads(q.data_conditions)
            # 轉換為 DataSearchCondition 對象列表
            data_conditions = []
            for condition_dict in conditions_data:
                condition = DataSearchCondition(
                    field_path=condition_dict["field_path"],
                    operator=DataSearchOperator(condition_dict["operator"]),
                    value=condition_dict["value"],
                )
                data_conditions.append(condition)
            query_kwargs["data_conditions"] = data_conditions
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid data_conditions format: {e!s}",
            )
    else:
        query_kwargs["data_conditions"] = msgspec.UNSET

    # 處理 sorts
    if q.sorts:
        try:
            # 解析 JSON 字符串
            sorts_data = json.loads(q.sorts)
            # 轉換為排序對象列表
            sorts = []
            for sort_dict in sorts_data:
                if sort_dict["type"] == "meta":
                    # ResourceMetaSearchSort
                    sort = ResourceMetaSearchSort(
                        key=ResourceMetaSortKey(sort_dict["key"]),
                        direction=ResourceMetaSortDirection(sort_dict["direction"]),
                    )
                elif sort_dict["type"] == "data":
                    # ResourceDataSearchSort
                    sort = ResourceDataSearchSort(
                        field_path=sort_dict["field_path"],
                        direction=ResourceMetaSortDirection(sort_dict["direction"]),
                    )
                else:
                    raise ValueError(f"Invalid sort type: {sort_dict['type']}")
                sorts.append(sort)
            query_kwargs["sorts"] = sorts
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid sorts format: {e!s}",
            )
    else:
        query_kwargs["sorts"] = msgspec.UNSET

    return ResourceMetaSearchQuery(**query_kwargs)
