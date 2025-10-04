import datetime as dt
import json
import textwrap
from contextlib import suppress
from typing import Optional, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query
from msgspec import UNSET

from autocrud.crud.route_templates.basic import (
    BaseRouteTemplate,
    FullResourceResponse,
    MsgspecResponse,
    struct_to_responses_type,
)
from autocrud.types import (
    IResourceManager,
)
from autocrud.types import (
    DataSearchCondition,
    DataSearchOperator,
    ResourceDataSearchSort,
    ResourceMeta,
    ResourceMetaSearchQuery,
    ResourceMetaSearchSort,
    ResourceMetaSortDirection,
    ResourceMetaSortKey,
    RevisionInfo,
)

T = TypeVar("T")


class ListRouteTemplate(BaseRouteTemplate):
    """列出所有資源的路由模板"""

    from pydantic import BaseModel

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

    def _build_query(self, q: QueryInputs) -> ResourceMetaSearchQuery:
        query_kwargs = {
            "limit": q.limit,
            "offset": q.offset,
        }

        if q.is_deleted is not None:
            query_kwargs["is_deleted"] = q.is_deleted
        else:
            query_kwargs["is_deleted"] = UNSET

        if q.created_time_start:
            query_kwargs["created_time_start"] = dt.datetime.fromisoformat(
                q.created_time_start,
            )
        else:
            query_kwargs["created_time_start"] = UNSET

        if q.created_time_end:
            query_kwargs["created_time_end"] = dt.datetime.fromisoformat(
                q.created_time_end,
            )
        else:
            query_kwargs["created_time_end"] = UNSET

        if q.updated_time_start:
            query_kwargs["updated_time_start"] = dt.datetime.fromisoformat(
                q.updated_time_start,
            )
        else:
            query_kwargs["updated_time_start"] = UNSET

        if q.updated_time_end:
            query_kwargs["updated_time_end"] = dt.datetime.fromisoformat(
                q.updated_time_end,
            )
        else:
            query_kwargs["updated_time_end"] = UNSET

        if q.created_bys:
            query_kwargs["created_bys"] = q.created_bys
        else:
            query_kwargs["created_bys"] = UNSET

        if q.updated_bys:
            query_kwargs["updated_bys"] = q.updated_bys
        else:
            query_kwargs["updated_bys"] = UNSET

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
            query_kwargs["data_conditions"] = UNSET

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
            query_kwargs["sorts"] = UNSET

        return ResourceMetaSearchQuery(**query_kwargs)

    def apply(
        self,
        model_name: str,
        resource_manager: IResourceManager[T],
        router: APIRouter,
    ) -> None:
        @router.get(
            f"/{model_name}/data",
            responses=struct_to_responses_type(list[resource_manager.resource_type]),
            summary=f"List {model_name} Data Only",
            tags=[f"{model_name}"],
            description=textwrap.dedent(
                f"""
                Retrieve a list of `{model_name}` resources returning only the data content.

                **Response Format:**
                - Returns only the resource data for each item (most lightweight option)
                - Excludes metadata and revision information
                - Ideal for applications that only need the core resource content

                **Filtering Options:**
                - `is_deleted`: Filter by deletion status (true/false)
                - `created_time_start/end`: Filter by creation time range (ISO format)
                - `updated_time_start/end`: Filter by update time range (ISO format)
                - `created_bys`: Filter by resource creators (list of usernames)
                - `updated_bys`: Filter by resource updaters (list of usernames)
                - `data_conditions`: Filter by data content (JSON format)

                **Data Filtering:**
                - Use `data_conditions` parameter to filter resources by their data content
                - Format: JSON array of condition objects
                - Each condition has: `field_path`, `operator`, `value`
                - Supported operators: `eq`, `ne`, `gt`, `lt`, `gte`, `lte`, `contains`, `starts_with`, `ends_with`, `in`, `not_in`
                - Example: `[{{"field_path": "department", "operator": "eq", "value": "Engineering"}}]`

                **Sorting Options:**
                - Use `sorts` parameter to specify sorting criteria
                - Format: JSON array of sort objects
                - Each sort object has: `type`, `direction`, and either `key` (for meta) or `field_path` (for data)
                - Sort types: `meta` (for metadata fields), `data` (for data content fields)
                - Directions: `+` (ascending), `-` (descending)
                - Meta sort keys: `created_time`, `updated_time`, `resource_id`
                - Example: `[{{"type": "meta", "key": "created_time", "direction": "+"}}, {{"type": "data", "field_path": "name", "direction": "-"}}]`

                **Pagination:**
                - `limit`: Maximum number of results to return (default: 10)
                - `offset`: Number of results to skip for pagination (default: 0)

                **Performance Benefits:**
                - Minimal response payload size
                - Faster response times
                - Reduced bandwidth usage
                - Direct access to resource content only

                **Examples:**
                - `GET /{model_name}/data` - Get first 10 resources (data only)
                - `GET /{model_name}/data?limit=20&offset=40` - Get resources 41-60 (data only)
                - `GET /{model_name}/data?is_deleted=false&limit=5` - Get 5 non-deleted resources (data only)

                **Error Responses:**
                - `400`: Bad request - Invalid query parameters or search error""",
            ),
        )
        async def list_resources_data(
            query_params: ListRouteTemplate.QueryInputs = Query(...),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ) -> list[T]:
            try:
                # 構建查詢對象
                query = self._build_query(query_params)
                with resource_manager.meta_provide(current_user, current_time):
                    resources_data: list[T] = []
                    metas = resource_manager.search_resources(query)
                    # 根據響應類型處理資源數據
                    for meta in metas:
                        try:
                            resource = resource_manager.get(meta.resource_id)
                            resources_data.append(resource.data)
                        except Exception:
                            # 如果無法獲取資源數據，跳過
                            continue

                return MsgspecResponse(resources_data)
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        @router.get(
            f"/{model_name}/meta",
            responses=struct_to_responses_type(list[ResourceMeta]),
            summary=f"List {model_name} Metadata Only",
            tags=[f"{model_name}"],
            description=textwrap.dedent(
                f"""
                Retrieve a list of `{model_name}` resources returning only the metadata.

                **Response Format:**
                - Returns only resource metadata for each item
                - Excludes actual data content and revision information
                - Ideal for browsing resource overviews and management operations

                **Metadata Includes:**
                - `resource_id`: Unique identifier of the resource
                - `current_revision_id`: ID of the current active revision
                - `total_revision_count`: Total number of revisions
                - `created_time` / `updated_time`: Timestamps
                - `created_by` / `updated_by`: User information
                - `is_deleted`: Deletion status
                - `schema_version`: Schema version information

                **Filtering Options:**
                - `is_deleted`: Filter by deletion status (true/false)
                - `created_time_start/end`: Filter by creation time range (ISO format)
                - `updated_time_start/end`: Filter by update time range (ISO format)
                - `created_bys`: Filter by resource creators (list of usernames)
                - `updated_bys`: Filter by resource updaters (list of usernames)
                - `data_conditions`: Filter by data content (JSON format)

                **Data Filtering:**
                - Use `data_conditions` parameter to filter resources by their data content
                - Format: JSON array of condition objects
                - Each condition has: `field_path`, `operator`, `value`
                - Supported operators: `eq`, `ne`, `gt`, `lt`, `gte`, `lte`, `contains`, `starts_with`, `ends_with`, `in`, `not_in`
                - Example: `[{{"field_path": "age", "operator": "gt", "value": 25}}]`

                **Sorting Options:**
                - Use `sorts` parameter to specify sorting criteria
                - Format: JSON array of sort objects
                - Each sort object has: `type`, `direction`, and either `key` (for meta) or `field_path` (for data)
                - Sort types: `meta` (for metadata fields), `data` (for data content fields)
                - Directions: `+` (ascending), `-` (descending)
                - Meta sort keys: `created_time`, `updated_time`, `resource_id`
                - Example: `[{{"type": "meta", "key": "updated_time", "direction": "-"}}, {{"type": "data", "field_path": "department", "direction": "+"}}]`

                **Pagination:**
                - `limit`: Maximum number of results to return (default: 10)
                - `offset`: Number of results to skip for pagination (default: 0)

                **Use Cases:**
                - Resource management and administration
                - Audit trail analysis
                - Bulk operations planning
                - System monitoring and statistics

                **Examples:**
                - `GET /{model_name}/meta` - Get metadata for first 10 resources
                - `GET /{model_name}/meta?is_deleted=true` - Get metadata for deleted resources
                - `GET /{model_name}/meta?created_bys=admin&limit=50` - Get metadata for admin-created resources

                **Error Responses:**
                - `400`: Bad request - Invalid query parameters or search error""",
            ),
        )
        async def list_resources_meta(
            query_params: ListRouteTemplate.QueryInputs = Query(...),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            try:
                # 構建查詢對象
                query = self._build_query(query_params)
                with resource_manager.meta_provide(current_user, current_time):
                    metas = resource_manager.search_resources(query)

                    # 根據響應類型處理資源數據
                    resources_data: list[ResourceMeta] = []
                    for meta in metas:
                        with suppress(Exception):
                            resources_data.append(meta)

                return MsgspecResponse(resources_data)
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        @router.get(
            f"/{model_name}/revision-info",
            responses=struct_to_responses_type(list[RevisionInfo]),
            summary=f"List {model_name} Current Revision Info",
            tags=[f"{model_name}"],
            description=textwrap.dedent(
                f"""
                Retrieve a list of `{model_name}` resources returning only the current revision information.

                **Response Format:**
                - Returns only revision information for the current revision of each resource
                - Excludes actual data content and resource metadata
                - Focuses on version control and revision tracking information

                **Revision Info Includes:**
                - `uid`: Unique identifier for this revision
                - `resource_id`: ID of the parent resource
                - `revision_id`: The revision identifier
                - `parent_revision_id`: ID of the parent revision (if any)
                - `schema_version`: Schema version used for this revision
                - `data_hash`: Hash of the resource data for integrity checking
                - `status`: Current status of the revision (draft/stable)

                **Filtering Options:**
                - `is_deleted`: Filter by deletion status (true/false)
                - `created_time_start/end`: Filter by creation time range (ISO format)
                - `updated_time_start/end`: Filter by update time range (ISO format)
                - `created_bys`: Filter by resource creators (list of usernames)
                - `updated_bys`: Filter by resource updaters (list of usernames)
                - `data_conditions`: Filter by data content (JSON format)

                **Data Filtering:**
                - Use `data_conditions` parameter to filter resources by their data content
                - Format: JSON array of condition objects
                - Each condition has: `field_path`, `operator`, `value`
                - Supported operators: `eq`, `ne`, `gt`, `lt`, `gte`, `lte`, `contains`, `starts_with`, `ends_with`, `in`, `not_in`
                - Example: `[{{"field_path": "status", "operator": "eq", "value": "active"}}]`

                **Pagination:**
                - `limit`: Maximum number of results to return (default: 10)
                - `offset`: Number of results to skip for pagination (default: 0)

                **Use Cases:**
                - Version control system integration
                - Data integrity verification through hashes
                - Revision status monitoring
                - Change tracking and audit trails

                **Examples:**
                - `GET /{model_name}/revision-info` - Get current revision info for first 10 resources
                - `GET /{model_name}/revision-info?limit=100` - Get revision info for first 100 resources
                - `GET /{model_name}/revision-info?updated_bys=editor` - Get revision info for editor-modified resources

                **Error Responses:**
                - `400`: Bad request - Invalid query parameters or search error""",
            ),
        )
        async def list_resources_revision_info(
            query_params: ListRouteTemplate.QueryInputs = Query(...),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            try:
                # 構建查詢對象
                query = self._build_query(query_params)
                with resource_manager.meta_provide(current_user, current_time):
                    metas = resource_manager.search_resources(query)

                    # 根據響應類型處理資源數據
                    resources_data: list[RevisionInfo] = []
                    for meta in metas:
                        try:
                            resource = resource_manager.get(meta.resource_id)
                            resources_data.append(resource.info)
                        except Exception:
                            # 如果無法獲取資源數據，跳過
                            continue
                return MsgspecResponse(resources_data)
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        @router.get(
            f"/{model_name}/full",
            responses=struct_to_responses_type(
                list[FullResourceResponse[resource_manager.resource_type]],
            ),
            summary=f"List {model_name} Complete Information",
            tags=[f"{model_name}"],
            description=textwrap.dedent(
                f"""
                Retrieve a list of `{model_name}` resources with complete information including data, metadata, and revision info.

                **Response Format:**
                - Returns comprehensive information for each resource
                - Includes data content, resource metadata, and current revision information
                - Most complete but also largest response format

                **Complete Information Includes:**
                - `data`: The actual resource data content
                - `meta`: Resource metadata (timestamps, user info, deletion status, etc.)
                - `revision_info`: Current revision details (uid, revision_id, parent_revision, hash, status)

                **Filtering Options:**
                - `is_deleted`: Filter by deletion status (true/false)
                - `created_time_start/end`: Filter by creation time range (ISO format)
                - `updated_time_start/end`: Filter by update time range (ISO format)
                - `created_bys`: Filter by resource creators (list of usernames)
                - `updated_bys`: Filter by resource updaters (list of usernames)
                - `data_conditions`: Filter by data content (JSON format)

                **Data Filtering:**
                - Use `data_conditions` parameter to filter resources by their data content
                - Format: JSON array of condition objects
                - Each condition has: `field_path`, `operator`, `value`
                - Supported operators: `eq`, `ne`, `gt`, `lt`, `gte`, `lte`, `contains`, `starts_with`, `ends_with`, `in`, `not_in`
                - Example: `[{{"field_path": "name", "operator": "contains", "value": "project"}}]`

                **Pagination:**
                - `limit`: Maximum number of results to return (default: 10)
                - `offset`: Number of results to skip for pagination (default: 0)

                **Use Cases:**
                - Complete data export operations
                - Comprehensive resource inspection
                - Full context retrieval for complex operations
                - Debugging and detailed analysis
                - Administrative overview with all details

                **Performance Considerations:**
                - Largest response payload size
                - May have slower response times for large datasets
                - Consider using pagination with smaller limits

                **Examples:**
                - `GET /{model_name}/full` - Get complete info for first 10 resources
                - `GET /{model_name}/full?limit=5` - Get complete info for first 5 resources (smaller payload)
                - `GET /{model_name}/full?is_deleted=false&limit=20` - Get complete info for 20 active resources

                **Error Responses:**
                - `400`: Bad request - Invalid query parameters or search error""",
            ),
        )
        async def list_resources_full(
            query_params: ListRouteTemplate.QueryInputsWithReturns = Query(...),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            returns = [r.strip() for r in query_params.returns.split(",")]
            try:
                # 構建查詢對象
                query = self._build_query(query_params)
                with resource_manager.meta_provide(current_user, current_time):
                    metas = resource_manager.search_resources(query)

                    # 根據響應類型處理資源數據
                    resources_data: list[FullResourceResponse[T]] = []
                    for meta in metas:
                        try:
                            resource = resource_manager.get(meta.resource_id)
                            if "data" in returns:
                                data = resource.data
                            else:
                                data = UNSET
                            if "revision_info" in returns:
                                revision_info = resource.info
                            else:
                                revision_info = UNSET
                            if "meta" in returns:
                                meta = meta
                            else:
                                meta = UNSET
                            resources_data.append(
                                FullResourceResponse(
                                    data=data,
                                    revision_info=revision_info,
                                    meta=meta,
                                ),
                            )
                        except Exception:
                            # 如果無法獲取資源數據，跳過
                            continue

                return MsgspecResponse(resources_data)
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        @router.get(
            f"/{model_name}/count",
            summary=f"List {model_name} Complete Information",
            tags=[f"{model_name}"],
            description=textwrap.dedent(
                f"""
                Retrieve a list of `{model_name}` resources with complete information including data, metadata, and revision info.

                **Response Format:**
                - Returns comprehensive information for each resource
                - Includes data content, resource metadata, and current revision information
                - Most complete but also largest response format

                **Complete Information Includes:**
                - `data`: The actual resource data content
                - `meta`: Resource metadata (timestamps, user info, deletion status, etc.)
                - `revision_info`: Current revision details (uid, revision_id, parent_revision, hash, status)

                **Filtering Options:**
                - `is_deleted`: Filter by deletion status (true/false)
                - `created_time_start/end`: Filter by creation time range (ISO format)
                - `updated_time_start/end`: Filter by update time range (ISO format)
                - `created_bys`: Filter by resource creators (list of usernames)
                - `updated_bys`: Filter by resource updaters (list of usernames)
                - `data_conditions`: Filter by data content (JSON format)

                **Data Filtering:**
                - Use `data_conditions` parameter to filter resources by their data content
                - Format: JSON array of condition objects
                - Each condition has: `field_path`, `operator`, `value`
                - Supported operators: `eq`, `ne`, `gt`, `lt`, `gte`, `lte`, `contains`, `starts_with`, `ends_with`, `in`, `not_in`
                - Example: `[{{"field_path": "name", "operator": "contains", "value": "project"}}]`

                **Pagination:**
                - `limit`: Maximum number of results to return (default: 10)
                - `offset`: Number of results to skip for pagination (default: 0)

                **Use Cases:**
                - Complete data export operations
                - Comprehensive resource inspection
                - Full context retrieval for complex operations
                - Debugging and detailed analysis
                - Administrative overview with all details

                **Performance Considerations:**
                - Largest response payload size
                - May have slower response times for large datasets
                - Consider using pagination with smaller limits

                **Examples:**
                - `GET /{model_name}/full` - Get complete info for first 10 resources
                - `GET /{model_name}/full?limit=5` - Get complete info for first 5 resources (smaller payload)
                - `GET /{model_name}/full?is_deleted=false&limit=20` - Get complete info for 20 active resources

                **Error Responses:**
                - `400`: Bad request - Invalid query parameters or search error""",
            ),
        )
        async def get_resources_count(
            query_params: ListRouteTemplate.QueryInputs = Query(...),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ) -> int:
            try:
                # 構建查詢對象
                query = self._build_query(query_params)
                with resource_manager.meta_provide(current_user, current_time):
                    count = resource_manager.count_resources(query)
                return count
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
