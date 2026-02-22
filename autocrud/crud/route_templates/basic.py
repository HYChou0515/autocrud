import datetime as dt
import json
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, Generic, NamedTuple, Optional, TypeVar

import msgspec
from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel

from autocrud.resource_manager.partial import create_partial_type
from autocrud.types import (
    DataSearchCondition,
    DataSearchOperator,
    IResourceManager,
    ResourceDataSearchSort,
    ResourceMeta,
    ResourceMetaSearchQuery,
    ResourceMetaSearchSort,
    ResourceMetaSortDirection,
    ResourceMetaSortKey,
    RevisionInfo,
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


class JsonListResponse(Response):
    media_type = "application/json"

    def render(self, content: list[bytes]) -> bytes:
        return b"[" + b",".join(content) + b"]"


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
    # Total revisions matching query (before limit)
    total: int = 0
    # Whether more revisions are available beyond the returned list
    has_more: bool = False


class FullResourceResponse(msgspec.Struct, Generic[T]):
    data: T | msgspec.UnsetType = msgspec.UNSET
    revision_info: RevisionInfo | msgspec.UnsetType = msgspec.UNSET
    meta: ResourceMeta | msgspec.UnsetType = msgspec.UNSET


class QueryInputs(BaseModel):
    # ResourceMetaSearchQuery 的查詢參數
    qb: Optional[str] = Query(
        None,
        description="Query Builder expression. Example: \"QB['foo'] == 123\" or \"QB['age'].gt(18) & QB['status'].eq('active')\"",
    )
    is_deleted: Optional[bool] = Query(
        False,
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
    conditions: Optional[str] = Query(
        None,
        description='General filter conditions in JSON format for meta fields or data. Example: \'[{"field_path": "resource_id", "operator": "starts_with", "value": "user-"}]\'',
    )
    sorts: Optional[str] = Query(
        None,
        description='Sort conditions in JSON format. Example: \'[{"type": "meta", "key": "created_time", "direction": "+"}, {"type": "data", "field_path": "name", "direction": "-"}]\'',
    )
    limit: int = Query(10, description="Maximum number of results")
    offset: int = Query(0, description="Number of results to skip")
    partial: Optional[list[str]] = Query(
        None,
        description="List of fields to retrieve (e.g. '/field1', '/nested/field2')",
    )
    partial_brackets: Optional[list[str]] = Query(
        None,
        alias="partial[]",
        description="List of fields to retrieve (e.g. '/field1', '/nested/field2') - for axios support",
        include_in_schema=False,
    )


class QueryInputsWithReturns(QueryInputs):
    returns: str = Query(
        default="data,revision_info,meta",
        description="Fields to return, comma-separated. Options: data, revision_info, meta",
    )


def get_partial_fields(
    request: Request,
    query_params: QueryInputs,
) -> list[str] | None:
    """Extract partial fields from query params with Pydantic v1 fallback.

    In Pydantic v1, aliased query parameters (e.g. ``partial[]``) are not
    properly bound by FastAPI.  This helper falls back to reading the raw
    query string when the alias-based field is ``None``.
    """
    fields = query_params.partial or query_params.partial_brackets
    if fields is None:
        raw = [v for k, v in request.query_params.multi_items() if k == "partial[]"]
        if raw:
            fields = raw
    return fields


class PartialFieldsSpec(NamedTuple):
    """Classified partial fields by prefix (meta/info/data)."""

    data_fields: list[str] | None = None
    meta_fields: list[str] | None = None
    info_fields: list[str] | None = None


def classify_partial_fields(
    fields: list[str] | None,
    default_category: str = "data",
) -> PartialFieldsSpec:
    """Classify partial field paths by prefix.

    Fields prefixed with ``meta/``, ``info/``, or ``data/`` are routed to the
    corresponding bucket.  Fields without a recognised prefix fall into
    *default_category* (``"data"`` by default, ``"meta"`` for meta-only
    endpoints, etc.).

    Args:
        fields: raw partial field list from the query string.
        default_category: where to place unprefixed fields
            (``"data"`` | ``"meta"`` | ``"info"``).

    Returns:
        A ``PartialFieldsSpec`` with each bucket set to ``None`` when empty.
    """
    if not fields:
        return PartialFieldsSpec()

    data_fields: list[str] = []
    meta_fields: list[str] = []
    info_fields: list[str] = []

    for raw in fields:
        # Normalise: strip leading slash
        stripped = raw.lstrip("/")

        if stripped.startswith("meta/"):
            meta_fields.append("/" + stripped[len("meta/") :])
        elif stripped.startswith("info/"):
            info_fields.append("/" + stripped[len("info/") :])
        elif stripped.startswith("data/"):
            data_fields.append("/" + stripped[len("data/") :])
        else:
            # No recognised prefix → default category
            path = raw if raw.startswith("/") else "/" + raw
            if default_category == "meta":
                meta_fields.append(path)
            elif default_category == "info":
                info_fields.append(path)
            else:
                data_fields.append(path)

    return PartialFieldsSpec(
        data_fields=data_fields or None,
        meta_fields=meta_fields or None,
        info_fields=info_fields or None,
    )


def filter_struct_partial(
    struct: msgspec.Struct,
    fields: list[str],
) -> msgspec.Struct:
    """Return a copy of *struct* keeping only the requested fields.

    Uses ``create_partial_type`` to build a lightweight Struct type that
    contains only the selected fields, then round-trips through msgspec
    JSON encode/decode for the actual filtering.
    """
    partial_type = create_partial_type(type(struct), fields)
    return msgspec.json.decode(msgspec.json.encode(struct), type=partial_type)


def build_query(q: QueryInputs) -> ResourceMetaSearchQuery:
    # 如果提供了 QB 表達式，檢查是否與其他參數衝突
    if q.qb:
        # 檢查是否同時提供了其他查詢參數
        conflicting_params = []
        if q.data_conditions:
            conflicting_params.append("data_conditions")
        if q.conditions:
            conflicting_params.append("conditions")
        if q.sorts:
            conflicting_params.append("sorts")

        if conflicting_params:
            raise HTTPException(
                status_code=422,
                detail=f"Cannot use 'qb' parameter together with: {', '.join(conflicting_params)}. Please use either 'qb' or the individual query parameters.",
            )

        try:
            from autocrud.crud.qb_parser import parse_qb_expression

            # 使用 AST parser 解析 QB 表達式（比 eval 更安全）
            qb_result = parse_qb_expression(q.qb)

            # 構建查詢對象，並套用 URL 參數中的 limit 和 offset
            query = qb_result.build()

            # 覆寫 limit 和 offset（如果 QB 表達式中有設置，URL 參數會覆蓋它）
            if q.limit != 10 or q.offset != 0:  # 檢查是否有設置非默認值
                query = msgspec.structs.replace(query, limit=q.limit, offset=q.offset)

            return query
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid QB expression: {e!s}",
            )

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

    # 處理 conditions
    if q.conditions:
        try:
            # 解析 JSON 字符串
            conditions_data = json.loads(q.conditions)
            # 轉換為 DataSearchCondition 對象列表
            conditions = []
            for condition_dict in conditions_data:
                condition = DataSearchCondition(
                    field_path=condition_dict["field_path"],
                    operator=DataSearchOperator(condition_dict["operator"]),
                    value=condition_dict["value"],
                )
                conditions.append(condition)
            query_kwargs["conditions"] = conditions
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid conditions format: {e!s}",
            )
    else:
        query_kwargs["conditions"] = msgspec.UNSET

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
