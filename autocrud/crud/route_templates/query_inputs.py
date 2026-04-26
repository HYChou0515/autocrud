"""Query parameter parsing for search/list routes.

Defines the FastAPI ``QueryInputs`` pydantic model used as a parameter
container, plus :func:`build_query` which turns parsed inputs into a
:class:`ResourceMetaSearchQuery` understood by the storage layer.

The QB (query-builder) shorthand is accepted via the ``qb`` parameter; in
that mode only ``limit``, ``offset`` and ``is_deleted`` are allowed
alongside it — every other filter must be expressed inside the QB
expression.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Optional

import msgspec
from fastapi import HTTPException, Query, Request
from pydantic import BaseModel

from autocrud.query_types import (
    DEFAULT_QUERY_LIMIT,
    DataSearchCondition,
    DataSearchOperator,
    ResourceDataSearchSort,
    ResourceMetaSearchQuery,
    ResourceMetaSearchSort,
    ResourceMetaSortDirection,
    ResourceMetaSortKey,
)


class QueryInputs(BaseModel):
    # ResourceMetaSearchQuery 的查詢參數
    qb: Optional[str] = Query(
        None,
        description=(
            "Query Builder expression. Example: \"QB['foo'] == 123\" or "
            "\"QB['age'].gt(18) & QB['status'].eq('active')\". "
            "When qb is used, do not combine it with data_conditions, conditions, "
            "or sorts; only limit, offset, and is_deleted may be used alongside qb."
        ),
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
    limit: int = Query(
        DEFAULT_QUERY_LIMIT,
        description=(
            "Maximum number of results. Default comes from the "
            "AUTOCRUD_DEFAULT_QUERY_LIMIT environment variable at startup; "
            "set limit explicitly or use the /count endpoint if you need the full total."
        ),
    )
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


def build_query(
    q: QueryInputs,
    request: Request | None = None,
    forced_conflicting_params: set[str] | None = None,
) -> ResourceMetaSearchQuery:
    # 如果提供了 QB 表達式，檢查是否與其他參數衝突
    if q.qb:
        provided_params = (
            set(request.query_params.keys()) if request is not None else set()
        )
        if forced_conflicting_params:
            provided_params.update(forced_conflicting_params)

        # 只有 limit / offset 可以和 QB 一起使用；其他篩選必須寫進 QB 表達式。
        conflicting_params = []
        if q.data_conditions:
            conflicting_params.append("data_conditions")
        if q.conditions:
            conflicting_params.append("conditions")
        if q.sorts:
            conflicting_params.append("sorts")

        for param_name in [
            "created_time_start",
            "created_time_end",
            "updated_time_start",
            "updated_time_end",
            "created_bys",
            "updated_bys",
        ]:
            if param_name in provided_params and getattr(q, param_name) is not None:
                conflicting_params.append(param_name)

        if conflicting_params:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Cannot use 'qb' parameter together with: "
                    f"{', '.join(conflicting_params)}. Please use either 'qb' "
                    "or the individual query parameters. In QB mode, include "
                    "metadata filters directly in the QB expression."
                ),
            )

        try:
            from autocrud.crud.qb_parser import parse_qb_expression
            from autocrud.query import QB as _QB

            # 使用 AST parser 解析 QB 表達式（比 eval 更安全）
            qb_result = parse_qb_expression(q.qb)

            # 構建查詢對象，並套用 URL 參數中的 limit 和 offset
            query = qb_result.build()

            # 覆寫 limit 和 offset（如果 QB 表達式中有設置，URL 參數會覆蓋它）
            if q.limit != DEFAULT_QUERY_LIMIT or q.offset != 0:
                query = msgspec.structs.replace(query, limit=q.limit, offset=q.offset)

            # is_deleted 可以與 QB 同時使用（Swagger 永遠會帶預設值 false）。
            # 將 is_deleted 條件 append 進 conditions 列表，與 QB 條件形成 AND。
            if q.is_deleted is not None:
                is_deleted_cond = _QB.is_deleted().eq(q.is_deleted)._condition
                existing = (
                    [] if query.conditions is msgspec.UNSET else list(query.conditions)
                )
                query = msgspec.structs.replace(
                    query, conditions=existing + [is_deleted_cond]
                )

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
            conditions_data = json.loads(q.data_conditions)
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
            conditions_data = json.loads(q.conditions)
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
            sorts_data = json.loads(q.sorts)
            sorts = []
            for sort_dict in sorts_data:
                if sort_dict["type"] == "meta":
                    sort = ResourceMetaSearchSort(
                        key=ResourceMetaSortKey(sort_dict["key"]),
                        direction=ResourceMetaSortDirection(sort_dict["direction"]),
                    )
                elif sort_dict["type"] == "data":
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
