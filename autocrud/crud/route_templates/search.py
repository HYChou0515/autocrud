import datetime as dt
import textwrap
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from autocrud.crud.route_templates.basic import (
    BaseRouteTemplate,
    FullResourceResponse,
    MsgspecResponse,
    QueryInputs,
    QueryInputsWithReturns,
    build_query,
    get_partial_fields,
    struct_to_responses_type,
)
from autocrud.types import (
    IResourceManager,
    ResourceMeta,
    RevisionInfo,
)

T = TypeVar("T")


class ListRouteTemplate(BaseRouteTemplate):
    """列出所有資源的路由模板"""

    def __init__(
        self,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

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
            deprecated=True,
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
                - `conditions`: Filter by meta fields or data content (JSON format)

                **General Filtering:**
                - Use `conditions` parameter to filter by metadata fields or data content
                - Format: JSON array of condition objects
                - Attributes: `field_path`, `operator`, `value`
                - Meta fields: `resource_id`, `is_deleted`, `created_time`, `updated_time`, `created_by`, `updated_by`
                - Example: `[{{"field_path": "resource_id", "operator": "starts_with", "value": "user-"}}]`

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

                **Partial Response:**
                - `partial`: List of fields to retrieve (e.g. '/field1', '/nested/field2')
                - Useful for reducing payload size when only specific fields are needed

                **Performance Benefits:**
                - Minimal response payload size
                - Faster response times
                - Reduced bandwidth usage
                - Direct access to resource content only

                **Examples:**
                - `GET /{model_name}/data` - Get first 10 resources (data only)
                - `GET /{model_name}/data?limit=20&offset=40` - Get resources 41-60 (data only)
                - `GET /{model_name}/data?is_deleted=false&limit=5` - Get 5 non-deleted resources (data only)
                - `GET /{model_name}/data?partial=/name&partial=/email` - Get specific fields for all resources

                **Error Responses:**
                - `400`: Bad request - Invalid query parameters or search error""",
            ),
        )
        async def list_resources_data(
            request: Request,
            query_params: QueryInputs = Query(...),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ) -> list[T]:
            try:
                query = build_query(query_params)
                fields = get_partial_fields(request, query_params)

                with resource_manager.meta_provide(current_user, current_time):
                    results = resource_manager.list_resources(
                        query,
                        returns=["data"],
                        partial=fields,
                    )
                return MsgspecResponse([item.data for item in results])
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        @router.get(
            f"/{model_name}/meta",
            responses=struct_to_responses_type(list[ResourceMeta]),
            summary=f"List {model_name} Metadata Only",
            tags=[f"{model_name}"],
            deprecated=True,
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
                - `conditions`: Filter by meta fields or data content (JSON format)

                **General Filtering:**
                - Use `conditions` parameter to filter by metadata fields or data content
                - Format: JSON array of condition objects
                - Attributes: `field_path`, `operator`, `value`
                - Meta fields: `resource_id`, `is_deleted`, `created_time`, `updated_time`, `created_by`, `updated_by`
                - Example: `[{{"field_path": "resource_id", "operator": "starts_with", "value": "user-"}}]`

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
            request: Request,
            query_params: QueryInputs = Query(...),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            try:
                query = build_query(query_params)
                fields = get_partial_fields(request, query_params)
                # For meta-only, prepend "meta/" prefix to unprefixed fields
                meta_partial = None
                if fields:
                    meta_partial = []
                    for f in fields:
                        stripped = f.lstrip("/")
                        if not stripped.startswith(("meta/", "info/", "data/")):
                            meta_partial.append("meta/" + stripped)
                        else:
                            meta_partial.append(f)

                with resource_manager.meta_provide(current_user, current_time):
                    results = resource_manager.list_resources(
                        query,
                        returns=["meta"],
                        partial=meta_partial,
                    )
                return MsgspecResponse([item.meta for item in results])
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        @router.get(
            f"/{model_name}/revision-info",
            responses=struct_to_responses_type(list[RevisionInfo]),
            summary=f"List {model_name} Current Revision Info",
            tags=[f"{model_name}"],
            deprecated=True,
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
                - `conditions`: Filter by meta fields or data content (JSON format)

                **General Filtering:**
                - Use `conditions` parameter to filter by metadata fields or data content
                - Format: JSON array of condition objects
                - Attributes: `field_path`, `operator`, `value`
                - Meta fields: `resource_id`, `is_deleted`, `created_time`, `updated_time`, `created_by`, `updated_by`
                - Example: `[{{"field_path": "resource_id", "operator": "starts_with", "value": "user-"}}]`

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
            request: Request,
            query_params: QueryInputs = Query(...),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            try:
                query = build_query(query_params)
                fields = get_partial_fields(request, query_params)
                # For info-only, prepend "info/" prefix to unprefixed fields
                info_partial = None
                if fields:
                    info_partial = []
                    for f in fields:
                        stripped = f.lstrip("/")
                        if not stripped.startswith(("meta/", "info/", "data/")):
                            info_partial.append("info/" + stripped)
                        else:
                            info_partial.append(f)

                with resource_manager.meta_provide(current_user, current_time):
                    results = resource_manager.list_resources(
                        query,
                        returns=["info"],
                        partial=info_partial,
                    )
                return MsgspecResponse([item.info for item in results])
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        # Shared implementation for /full and bare path collection GET endpoints
        async def _handle_list_with_returns(
            request,
            query_params,
            current_user,
            current_time,
        ):
            raw_returns = [r.strip() for r in query_params.returns.split(",")]
            # Map route-level "revision_info" to RM-level "info"
            returns = ["info" if r == "revision_info" else r for r in raw_returns]
            try:
                query = build_query(query_params)
                fields = get_partial_fields(request, query_params)

                with resource_manager.meta_provide(current_user, current_time):
                    results = resource_manager.list_resources(
                        query,
                        returns=returns,
                        partial=fields,
                    )

                # Map SearchedResource back to FullResourceResponse for API compat
                responses = []
                for item in results:
                    responses.append(
                        FullResourceResponse(
                            data=item.data,
                            revision_info=item.info,
                            meta=item.meta,
                        )
                    )
                return MsgspecResponse(responses)
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        @router.get(
            f"/{model_name}/full",
            responses=struct_to_responses_type(
                list[FullResourceResponse[resource_manager.resource_type]],
            ),
            summary=f"List {model_name} Complete Information",
            tags=[f"{model_name}"],
            deprecated=True,
            description=f"Deprecated: use `GET /{model_name}` instead. "
            f"Retrieve a list of `{model_name}` resources with complete information including data, metadata, and revision info.",
        )
        async def list_resources_full(
            request: Request,
            query_params: QueryInputsWithReturns = Query(...),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            return await _handle_list_with_returns(
                request,
                query_params,
                current_user,
                current_time,
            )

        @router.get(
            f"/{model_name}/count",
            summary=f"Count {model_name} Resources",
            tags=[f"{model_name}"],
            description=textwrap.dedent(
                f"""
                Retrieve the count of `{model_name}` resources matching the search criteria.

                **Response Format:**
                - Returns a single integer representing the count of matching resources.

                **Filtering Options:**
                - `is_deleted`: Filter by deletion status (true/false)
                - `created_time_start/end`: Filter by creation time range (ISO format)
                - `updated_time_start/end`: Filter by update time range (ISO format)
                - `created_bys`: Filter by resource creators (list of usernames)
                - `updated_bys`: Filter by resource updaters (list of usernames)
                - `data_conditions`: Filter by data content (JSON format)
                - `conditions`: Filter by meta fields or data content (JSON format)

                **General Filtering:**
                - Use `conditions` parameter to filter by metadata fields or data content
                - Format: JSON array of condition objects
                - Attributes: `field_path`, `operator`, `value`
                - Meta fields: `resource_id`, `is_deleted`, `created_time`, `updated_time`, `created_by`, `updated_by`
                - Example: `[{{"field_path": "resource_id", "operator": "starts_with", "value": "user-"}}]`

                **Data Filtering:**
                - Use `data_conditions` parameter to filter resources by their data content
                - Format: JSON array of condition objects
                - Each condition has: `field_path`, `operator`, `value`
                - Supported operators: `eq`, `ne`, `gt`, `lt`, `gte`, `lte`, `contains`, `starts_with`, `ends_with`, `in`, `not_in`
                - Example: `[{{"field_path": "name", "operator": "contains", "value": "project"}}]`

                **Use Cases:**
                - Getting total number of resources for pagination calculations
                - Statistical analysis
                - Checking existence of resources matching criteria

                **Examples:**
                - `GET /{model_name}/count` - Get total count of all resources
                - `GET /{model_name}/count?is_deleted=false` - Get count of active resources

                **Error Responses:**
                - `400`: Bad request - Invalid query parameters or search error""",
            ),
        )
        async def get_resources_count(
            query_params: QueryInputs = Query(...),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ) -> int:
            try:
                # 構建查詢對象
                query = build_query(query_params)
                with resource_manager.meta_provide(current_user, current_time):
                    count = resource_manager.count_resources(query)
                return count
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        # New bare path endpoint — canonical GET for listing resources
        @router.get(
            f"/{model_name}",
            responses=struct_to_responses_type(
                list[FullResourceResponse[resource_manager.resource_type]],
            ),
            summary=f"List {model_name} resources",
            tags=[f"{model_name}"],
            description=textwrap.dedent(
                f"""
                Retrieve a list of `{model_name}` resources.

                Use the `returns` query parameter to control which sections are included in each item.
                By default all sections are returned: `data`, `revision_info`, `meta`.

                **Query Parameters:**
                - `returns` (default `"data,revision_info,meta"`): Comma-separated list of sections to include.
                  Allowed values: `data`, `revision_info`, `meta`.
                - `limit` / `offset`: Pagination controls.
                - `partial` / `partial[]`: Partial field selection.
                - All standard filtering and sorting parameters.

                **Examples:**
                - `GET /{model_name}` — full list (data + meta + revision_info)
                - `GET /{model_name}?returns=data` — data only
                - `GET /{model_name}?returns=data,meta` — data + meta, no revision_info
                - `GET /{model_name}?limit=20&offset=40` — pagination

                **Error Responses:**
                - `400`: Bad request - Invalid query parameters or search error""",
            ),
        )
        async def list_resources(
            request: Request,
            query_params: QueryInputsWithReturns = Query(...),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            return await _handle_list_with_returns(
                request,
                query_params,
                current_user,
                current_time,
            )
