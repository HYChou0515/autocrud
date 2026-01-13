from collections.abc import Callable
import datetime as dt
import io
import textwrap
from contextlib import contextmanager, suppress
from typing import IO, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query
from msgspec import UNSET
import msgspec
from qqabc.rurl import resolve
from qqabc.types import IUrlGrammar, IWorker, InData, OutData

from autocrud.crud.route_templates.basic import (
    BaseRouteTemplate,
    FullResourceResponse,
    JsonListResponse,
    MsgspecResponse,
    QueryInputs,
    QueryInputsWithReturns,
    build_query,
    struct_to_responses_type,
)
from autocrud.types import (
    IResourceManager,
)
from autocrud.types import (
    ResourceMeta,
    RevisionInfo,
)

T = TypeVar("T")


class Worker(IWorker):
    def __init__(
        self,
        resource_manager: IResourceManager[T],
        fields: list[str] | None,
        returns: list[str] | str,
    ):
        self.resource_manager = resource_manager
        self.fields = fields
        self.returns = returns

    @contextmanager
    def start(self, worker_id: int):
        self.worker_id = worker_id
        yield self

    def get_resource(self, meta: ResourceMeta) -> bytes:
        data = UNSET
        revision_info = UNSET

        if "data" in self.returns:
            if self.fields:
                data = self.resource_manager.get_partial(
                    meta.resource_id,
                    meta.current_revision_id,
                    self.fields,
                    schema_version=meta.schema_version,
                )
            else:
                resource = self.resource_manager.get(
                    meta.resource_id,
                    revision_id=meta.current_revision_id,
                    schema_version=meta.schema_version,
                )
                data = resource.data
                if "revision_info" in self.returns:
                    revision_info = resource.info

        if "revision_info" in self.returns and revision_info is UNSET:
            revision_info = self.resource_manager.get_revision_info(
                meta.resource_id,
                meta.current_revision_id,
                schema_version=meta.schema_version,
            )

        if "meta" in self.returns:
            meta_out = meta
        else:
            meta_out = UNSET

        if isinstance(self.returns, str):
            if self.returns == "data":
                return msgspec.json.encode(data)
            elif self.returns == "meta":
                return msgspec.json.encode(meta_out)
            elif self.returns == "revision_info":
                return msgspec.json.encode(revision_info)
            else:
                raise ValueError(f"Unknown return type: {self.returns}")
        else:
            return msgspec.json.encode(
                FullResourceResponse(
                    data=data,
                    revision_info=revision_info,
                    meta=meta_out,
                )
            )

    def resolve(self, indata: InData) -> OutData:
        meta = self.resource_manager.get_meta(indata.url)
        try:
            b = self.get_resource(meta)
        except Exception:
            # 如果無法獲取資源數據，跳過
            b = b""
        return OutData(task_id=indata.task_id, data=io.BytesIO(b))


class CustomGrammar(IUrlGrammar):
    def parse_url(self, fp: IO[bytes]) -> str | None:
        return fp.read().decode("utf-8")


def default_worker_num(nr_work: int) -> int:
    if nr_work <= 10:
        return 1
    return max(1, min(16, nr_work // 3))


class ListRouteTemplate(BaseRouteTemplate):
    """列出所有資源的路由模板"""

    def __init__(
        self,
        *args,
        worker_num_calc: Callable[[int], int] | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.worker_num_calc = worker_num_calc or default_worker_num

    def fetch_resources_data(
        self, metas: list[ResourceMeta], get_worker: Callable[[], Worker]
    ) -> list[bytes]:
        resources_data: list[bytes] = []
        worker_num = self.worker_num_calc(len(metas))
        if worker_num <= 1:
            for meta in metas:
                resource = get_worker().get_resource(meta)
                resources_data.append(resource)
        else:
            with resolve(
                num_workers=worker_num,
                worker=get_worker,
                job_chance=1,
                grammars=[CustomGrammar()],
            ) as resolver:
                # 根據響應類型處理資源數據
                tasks = []
                for meta in metas:
                    tasks.append(resolver.add(str(meta.resource_id)))

                for task in tasks:
                    outd = resolver.wait(task)
                    if b := outd.data.read():
                        resources_data.append(b)
        return resources_data

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
            query_params: QueryInputs = Query(...),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ) -> list[T]:
            try:
                # 構建查詢對象
                query = build_query(query_params)
                fields = query_params.partial or query_params.partial_brackets

                def get_worker():
                    return Worker(
                        resource_manager,
                        fields,
                        "data",
                    )

                with resource_manager.meta_provide(current_user, current_time):
                    resources_data = self.fetch_resources_data(
                        resource_manager.search_resources(query),
                        get_worker,
                    )
                return JsonListResponse(resources_data)
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
            query_params: QueryInputs = Query(...),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            try:
                # 構建查詢對象
                query = build_query(query_params)
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
            query_params: QueryInputs = Query(...),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            try:
                # 構建查詢對象
                query = build_query(query_params)

                def get_worker():
                    return Worker(
                        resource_manager,
                        None,
                        "revision_info",
                    )

                with resource_manager.meta_provide(current_user, current_time):
                    resources_data = self.fetch_resources_data(
                        resource_manager.search_resources(query),
                        get_worker,
                    )
                return JsonListResponse(resources_data)
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

                **Pagination:**
                - `limit`: Maximum number of results to return (default: 10)
                - `offset`: Number of results to skip for pagination (default: 0)

                **Partial Response:**
                - `partial`: List of fields to retrieve (e.g. '/field1', '/nested/field2')
                - Useful for reducing payload size when only specific fields are needed

                **Use Cases:**
                - Complete data export operations
                - Comprehensive resource inspection
                - Full context retrieval for complex operations
                - Debugging and detailed analysis
                - Administrative overview with all details
                - Fetching only necessary data fields while keeping metadata (using partial)

                **Performance Considerations:**
                - Largest response payload size
                - May have slower response times for large datasets
                - Consider using pagination with smaller limits

                **Examples:**
                - `GET /{model_name}/full` - Get complete info for first 10 resources
                - `GET /{model_name}/full?limit=5` - Get complete info for first 5 resources (smaller payload)
                - `GET /{model_name}/full?is_deleted=false&limit=20` - Get complete info for 20 active resources
                - `GET /{model_name}/full?partial=/name&partial=/email` - Get specific fields for all resources

                **Error Responses:**
                - `400`: Bad request - Invalid query parameters or search error""",
            ),
        )
        async def list_resources_full(
            query_params: QueryInputsWithReturns = Query(...),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            returns = [r.strip() for r in query_params.returns.split(",")]
            try:
                # 構建查詢對象
                query = build_query(query_params)
                fields = query_params.partial or query_params.partial_brackets

                def get_worker():
                    return Worker(
                        resource_manager,
                        fields,
                        returns,
                    )

                with resource_manager.meta_provide(current_user, current_time):
                    resources_data = self.fetch_resources_data(
                        resource_manager.search_resources(query),
                        get_worker,
                    )
                return JsonListResponse(resources_data)
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

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
