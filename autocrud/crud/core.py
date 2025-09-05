from __future__ import annotations
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Callable
from contextlib import suppress
from enum import StrEnum
import io
import json
import tarfile
import textwrap
from typing import IO, Generic, Literal, TypeVar
import datetime as dt
from msgspec import UNSET
from fastapi.openapi.utils import get_openapi

from fastapi import APIRouter, FastAPI, HTTPException, Request, Query, Depends, Response
import msgspec
from typing import Optional

from autocrud.permission.rbac import RBACPermissionChecker
from autocrud.permission.simple import AllowAll
from autocrud.resource_manager.basic import (
    DataSearchCondition,
    DataSearchOperator,
    IMigration,
    IResourceManager,
    IStorage,
    Resource,
    ResourceMeta,
    RevisionInfo,
    IndexableField,
    ResourceMetaSearchSort,
    ResourceDataSearchSort,
    ResourceMetaSortDirection,
    ResourceMetaSortKey,
)
from autocrud.resource_manager.core import ResourceManager
from autocrud.resource_manager.data_converter import (
    decode_json_to_data,
)

from autocrud.resource_manager.basic import ResourceMetaSearchQuery
from autocrud.resource_manager.storage_factory import IStorageFactory
from autocrud.resource_manager.storage_factory import MemoryStorageFactory
from autocrud.util.naming import NameConverter


class ListResponseType(StrEnum):
    """列表響應類型枚舉"""

    DATA = "data"  # 只返回資源數據
    META = "meta"  # 只返回 ResourceMeta
    REVISION_INFO = "revision_info"  # 只返回 RevisionInfo
    FULL = "full"  # 返回所有信息 (data, meta, revision_info)
    REVISIONS = "revisions"  # 返回 meta 和所有 revision info


T = TypeVar("T")


class FullResourceResponse(msgspec.Struct, Generic[T]):
    data: T
    revision_info: RevisionInfo
    meta: ResourceMeta


class RevisionListResponse(msgspec.Struct):
    meta: ResourceMeta
    revisions: list[RevisionInfo]


def jsonschema_to_openapi(struct: msgspec.Struct) -> dict:
    return msgspec.json.schema_components(
        struct, ref_template="#/components/schemas/{name}"
    )


def struct_to_responses_type(struct: type[msgspec.Struct], status_code: int = 200):
    schema = msgspec.json.schema_components(
        [struct], ref_template="#/components/schemas/{name}"
    )[0][0]
    return {
        status_code: {
            "content": {"application/json": {"schema": schema}},
        },
    }


class MsgspecResponse(Response):
    media_type = "application/json"

    def render(self, content: msgspec.Struct) -> bytes:
        return msgspec.json.encode(content)


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
        self, model_name: str, resource_manager: IResourceManager[T], router: APIRouter
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


class BaseRouteTemplate(IRouteTemplate):
    def __init__(
        self, dependency_provider: DependencyProvider = None, order: int = 100
    ):
        """
        初始化路由模板

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


class CreateRouteTemplate(BaseRouteTemplate):
    """創建資源的路由模板"""

    def apply(
        self, model_name: str, resource_manager: IResourceManager[T], router: APIRouter
    ) -> None:
        # 動態創建響應模型
        resource_type = resource_manager.resource_type

        @router.post(
            f"/{model_name}",
            response_class=MsgspecResponse,
            responses=struct_to_responses_type(RevisionInfo),
            summary=f"Create {model_name}",
            tags=[f"{model_name}"],
            description=textwrap.dedent(
                f"""
                Create a new `{model_name}` resource.

                **Request Body:**
                - Send the resource data as JSON in the request body
                - The data will be validated against the `{model_name}` schema

                **Response:**
                - Returns revision information for the newly created resource
                - Includes `resource_id` and `revision_id` for tracking
                - All resources are version-controlled from creation

                **Examples:**
                - `POST /{model_name}` with JSON body - Create new resource
                - Response includes resource and revision identifiers

                **Error Responses:**
                - `422`: Validation error - Invalid data format or missing required fields
                - `400`: Bad request - General creation error"""
            ),
        )
        async def create_resource(
            request: Request,
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            try:
                # 直接接收原始 JSON bytes
                json_bytes = await request.body()

                data = decode_json_to_data(json_bytes, resource_type)

                with resource_manager.meta_provide(current_user, current_time):
                    info = resource_manager.create(data)
                return MsgspecResponse(info)
            except msgspec.ValidationError as e:
                # 數據驗證錯誤，返回 422
                raise HTTPException(status_code=422, detail=str(e))
            except Exception as e:
                # 其他錯誤，返回 400
                raise HTTPException(status_code=400, detail=str(e))


class ReadRouteTemplate(BaseRouteTemplate, Generic[T]):
    """讀取單一資源的路由模板"""

    def _get_resource_and_meta(
        self,
        resource_manager: IResourceManager[T],
        resource_id: str,
        revision_id: Optional[str],
        current_user: str,
        current_time: dt.datetime,
    ) -> tuple[Resource[T], ResourceMeta]:
        """獲取資源和元數據"""
        with resource_manager.meta_provide(current_user, current_time):
            meta = resource_manager.get_meta(resource_id)
            if revision_id:
                resource = resource_manager.get_resource_revision(
                    resource_id, revision_id
                )
            else:
                resource = resource_manager.get(resource_id)
        return resource, meta

    def apply(
        self, model_name: str, resource_manager: IResourceManager[T], router: APIRouter
    ) -> None:
        resource_type = resource_manager.resource_type

        @router.get(
            f"/{model_name}/{{resource_id}}/meta",
            response_class=MsgspecResponse,
            responses=struct_to_responses_type(list[ResourceMeta]),
            summary=f"Get {model_name} Meta by ID",
            tags=[f"{model_name}"],
        )
        async def get_resource_meta(
            resource_id: str,
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            # 獲取資源和元數據
            try:
                with resource_manager.meta_provide(current_user, current_time):
                    meta = resource_manager.get_meta(resource_id)
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=404, detail=str(e))

            # 根據響應類型處理數據
            return MsgspecResponse(meta)

        @router.get(
            f"/{model_name}/{{resource_id}}/revision-info",
            response_class=MsgspecResponse,
            responses=struct_to_responses_type(RevisionInfo),
            summary=f"Get {model_name} Revision Info",
            tags=[f"{model_name}"],
            description=textwrap.dedent(
                f"""
                Retrieve revision information for a specific `{model_name}` resource.

                **Path Parameters:**
                - `resource_id`: The unique identifier of the resource

                **Query Parameters:**
                - `revision_id` (optional): Specific revision ID to retrieve. If not provided, returns the current revision

                **Response:**
                - Returns detailed revision information including:
                  - `uid`: Unique identifier for this revision
                  - `revision_id`: The revision identifier
                  - `parent_revision_id`: ID of the parent revision (if any)
                  - `schema_version`: Schema version used for this revision
                  - `data_hash`: Hash of the resource data
                  - `status`: Current status of the revision

                **Use Cases:**
                - Get metadata about a specific revision
                - Track revision lineage and relationships
                - Verify data integrity through hash checking
                - Monitor revision status changes

                **Examples:**
                - `GET /{model_name}/123/revision-info` - Get current revision info
                - `GET /{model_name}/123/revision-info?revision_id=rev456` - Get specific revision info

                **Error Responses:**
                - `404`: Resource or revision not found"""
            ),
        )
        async def get_resource_revision_info(
            resource_id: str,
            revision_id: Optional[str] = Query(
                None,
                description="Specific revision ID to retrieve. If not provided, returns the current revision",
            ),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            # 獲取資源和元數據
            try:
                with resource_manager.meta_provide(current_user, current_time):
                    if revision_id:
                        resource = resource_manager.get_resource_revision(
                            resource_id, revision_id
                        )
                    else:
                        resource = resource_manager.get(resource_id)
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=404, detail=str(e))

            return MsgspecResponse(resource.info)

        @router.get(
            f"/{model_name}/{{resource_id}}/full",
            response_class=MsgspecResponse,
            responses=struct_to_responses_type(FullResourceResponse[resource_type]),
            summary=f"Get Complete {model_name} Information",
            tags=[f"{model_name}"],
            description=textwrap.dedent(
                f"""
                Retrieve complete information for a `{model_name}` resource including data, metadata, and revision info.

                **Path Parameters:**
                - `resource_id`: The unique identifier of the resource

                **Query Parameters:**
                - `revision_id` (optional): Specific revision ID to retrieve. If not provided, returns the current revision

                **Response:**
                - Returns comprehensive resource information including:
                  - `data`: The actual resource data
                  - `meta`: Resource metadata (creation time, update time, deletion status, etc.)
                  - `revision_info`: Detailed revision information (uid, revision_id, parent_revision, etc.)

                **Use Cases:**
                - Get all available information about a resource in one request
                - Complete resource inspection for debugging or auditing
                - Comprehensive data export including all metadata
                - Full context retrieval for complex operations

                **Examples:**
                - `GET /{model_name}/123/full` - Get complete current resource information
                - `GET /{model_name}/123/full?revision_id=rev456` - Get complete information for specific revision

                **Error Responses:**
                - `404`: Resource or revision not found"""
            ),
        )
        async def get_resource_full(
            resource_id: str,
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
            return MsgspecResponse(
                FullResourceResponse(
                    data=resource.data, revision_info=resource.info, meta=meta
                )
            )

        @router.get(
            f"/{model_name}/{{resource_id}}/revision-list",
            response_class=MsgspecResponse,
            responses=struct_to_responses_type(RevisionListResponse),
            summary=f"Get {model_name} Revision History",
            tags=[f"{model_name}"],
            description=textwrap.dedent(
                f"""
                Retrieve the complete revision history for a `{model_name}` resource.

                **Path Parameters:**
                - `resource_id`: The unique identifier of the resource

                **Response:**
                - Returns resource metadata and complete revision history including:
                  - `meta`: Current resource metadata
                  - `revisions`: Array of all revision information objects
                    - Each revision includes uid, revision_id, parent_revision_id, schema_version, data_hash, and status

                **Use Cases:**
                - View complete change history of a resource
                - Audit trail and compliance tracking
                - Understanding resource evolution over time
                - Selecting specific revisions for comparison or restoration

                **Version Control Benefits:**
                - Complete chronological history of all changes
                - Parent-child relationships between revisions
                - Data integrity verification through hashes
                - Status tracking for each revision

                **Examples:**
                - `GET /{model_name}/123/revision-list` - Get all revisions for resource 123
                - Response includes metadata and array of revision information

                **Error Responses:**
                - `404`: Resource not found"""
            ),
        )
        async def get_resource_revision_list(
            resource_id: str,
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            # 獲取資源和元數據
            try:
                with resource_manager.meta_provide(current_user, current_time):
                    meta = resource_manager.get_meta(resource_id)
                    revision_ids = resource_manager.list_revisions(resource_id)
                    revision_infos: list[RevisionInfo] = []
                    for rev_id in revision_ids:
                        try:
                            rev_resource = resource_manager.get_resource_revision(
                                resource_id, rev_id
                            )
                            revision_infos.append(rev_resource.info)
                        except Exception:
                            # 如果無法獲取某個版本，跳過
                            continue

                    return MsgspecResponse(
                        RevisionListResponse(
                            meta=meta,
                            revisions=revision_infos,
                        )
                    )
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=404, detail=str(e))

        @router.get(
            f"/{model_name}/{{resource_id}}/data",
            response_class=MsgspecResponse,
            responses=struct_to_responses_type(resource_type),
            summary=f"Get {model_name} Data",
            tags=[f"{model_name}"],
            description=textwrap.dedent(
                f"""
                Retrieve only the data content of a `{model_name}` resource.

                **Path Parameters:**
                - `resource_id`: The unique identifier of the resource

                **Query Parameters:**
                - `revision_id` (optional): Specific revision ID to retrieve. If not provided, returns the current revision

                **Response:**
                - Returns only the resource data without metadata or revision information
                - The response format matches the original resource schema
                - Most lightweight option for retrieving resource content

                **Use Cases:**
                - Simple data retrieval when metadata is not needed
                - Efficient resource content access
                - Integration with external systems that only need the data
                - Lightweight API calls to minimize response size

                **Performance Benefits:**
                - Minimal response payload
                - Faster response times
                - Reduced bandwidth usage
                - Direct access to resource content

                **Examples:**
                - `GET /{model_name}/123/data` - Get current resource data only
                - `GET /{model_name}/123/data?revision_id=rev456` - Get specific revision data only

                **Error Responses:**
                - `404`: Resource or revision not found"""
            ),
        )
        async def get_resource_data(
            resource_id: str,
            revision_id: Optional[str] = Query(
                None,
                description="Specific revision ID to retrieve. If not provided, returns the current revision",
            ),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            # 獲取資源和元數據
            try:
                with resource_manager.meta_provide(current_user, current_time):
                    if revision_id:
                        resource = resource_manager.get_resource_revision(
                            resource_id, revision_id
                        )
                    else:
                        resource = resource_manager.get(resource_id)
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=404, detail=str(e))

            return MsgspecResponse(resource.data)


class UpdateRouteTemplate(BaseRouteTemplate):
    """更新資源的路由模板"""

    def apply(
        self, model_name: str, resource_manager: IResourceManager[T], router: APIRouter
    ) -> None:
        resource_type = resource_manager.resource_type

        @router.put(
            f"/{model_name}/{{resource_id}}",
            response_class=MsgspecResponse,
            responses=struct_to_responses_type(RevisionInfo),
            summary=f"Update {model_name}",
            tags=[f"{model_name}"],
            description=textwrap.dedent(
                f"""
                Update an existing `{model_name}` resource by replacing it entirely.

                **Path Parameters:**
                - `resource_id`: The unique identifier of the resource to update

                **Request Body:**
                - Send the complete updated resource data as JSON
                - The data will be validated against the `{model_name}` schema
                - This is a full replacement update (PUT semantics)

                **Response:**
                - Returns revision information for the updated resource
                - Includes new `revision_id` and maintains `resource_id`
                - Creates a new version while preserving revision history

                **Version Control:**
                - Each update creates a new revision
                - Previous versions remain accessible via revision history
                - Original resource ID is preserved across updates

                **Examples:**
                - `PUT /{model_name}/123` with JSON body - Update resource with ID 123
                - Response includes updated revision information

                **Error Responses:**
                - `422`: Validation error - Invalid data format or missing required fields
                - `400`: Bad request - Resource not found or update error
                - `404`: Resource does not exist"""
            ),
        )
        async def update_resource(
            resource_id: str,
            request: Request,
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            try:
                # 直接接收原始 JSON bytes
                json_bytes = await request.body()

                data = decode_json_to_data(json_bytes, resource_type)

                with resource_manager.meta_provide(current_user, current_time):
                    info = resource_manager.update(resource_id, data)
                return MsgspecResponse(info)
            except msgspec.ValidationError as e:
                # 數據驗證錯誤，返回 422
                raise HTTPException(status_code=422, detail=str(e))
            except Exception as e:
                # 其他錯誤，返回 400
                raise HTTPException(status_code=400, detail=str(e))


class DeleteRouteTemplate(BaseRouteTemplate):
    """刪除資源的路由模板"""

    def apply(
        self, model_name: str, resource_manager: IResourceManager[T], router: APIRouter
    ) -> None:
        # 動態創建響應模型
        @router.delete(
            f"/{model_name}/{{resource_id}}",
            response_class=MsgspecResponse,
            responses=struct_to_responses_type(ResourceMeta),
            summary=f"Delete {model_name}",
            tags=[f"{model_name}"],
            description=textwrap.dedent(
                f"""
                Delete a `{model_name}` resource by marking it as deleted.

                **Path Parameters:**
                - `resource_id`: The unique identifier of the resource to delete

                **Soft Delete:**
                - Resources are marked as deleted rather than permanently removed
                - Deleted resources can be restored using the restore endpoint
                - All revision history is preserved after deletion

                **Response:**
                - Returns updated resource metadata
                - The `is_deleted` field will be set to `true`
                - Includes updated timestamp and user information

                **Version Control:**
                - Deletion creates a new revision in the resource history
                - Previous versions remain accessible for audit purposes
                - The resource can be restored to any previous revision

                **Examples:**
                - `DELETE /{model_name}/123` - Mark resource with ID 123 as deleted
                - Response shows updated metadata with deletion status

                **Error Responses:**
                - `400`: Bad request - Resource not found or deletion error
                - `404`: Resource does not exist"""
            ),
        )
        async def delete_resource(
            resource_id: str,
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            try:
                with resource_manager.meta_provide(current_user, current_time):
                    meta = resource_manager.delete(resource_id)
                return MsgspecResponse(meta)
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))


class ListRouteTemplate(BaseRouteTemplate):
    """列出所有資源的路由模板"""

    from pydantic import BaseModel

    class QueryInputs(BaseModel):
        # ResourceMetaSearchQuery 的查詢參數
        is_deleted: Optional[bool] = Query(
            None, description="Filter by deletion status"
        )
        created_time_start: Optional[str] = Query(
            None, description="Filter by created time start (ISO format)"
        )
        created_time_end: Optional[str] = Query(
            None, description="Filter by created time end (ISO format)"
        )
        updated_time_start: Optional[str] = Query(
            None, description="Filter by updated time start (ISO format)"
        )
        updated_time_end: Optional[str] = Query(
            None, description="Filter by updated time end (ISO format)"
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
                q.created_time_start
            )
        else:
            query_kwargs["created_time_start"] = UNSET

        if q.created_time_end:
            query_kwargs["created_time_end"] = dt.datetime.fromisoformat(
                q.created_time_end
            )
        else:
            query_kwargs["created_time_end"] = UNSET

        if q.updated_time_start:
            query_kwargs["updated_time_start"] = dt.datetime.fromisoformat(
                q.updated_time_start
            )
        else:
            query_kwargs["updated_time_start"] = UNSET

        if q.updated_time_end:
            query_kwargs["updated_time_end"] = dt.datetime.fromisoformat(
                q.updated_time_end
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
                    status_code=400, detail=f"Invalid data_conditions format: {str(e)}"
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
                    status_code=400, detail=f"Invalid sorts format: {str(e)}"
                )
        else:
            query_kwargs["sorts"] = UNSET

        return ResourceMetaSearchQuery(**query_kwargs)

    def apply(
        self, model_name: str, resource_manager: IResourceManager[T], router: APIRouter
    ) -> None:
        @router.get(
            f"/{model_name}/data",
            response_class=MsgspecResponse,
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
                - `400`: Bad request - Invalid query parameters or search error"""
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
            response_class=MsgspecResponse,
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
                - `400`: Bad request - Invalid query parameters or search error"""
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
            response_class=MsgspecResponse,
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
                - `400`: Bad request - Invalid query parameters or search error"""
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
            response_class=MsgspecResponse,
            responses=struct_to_responses_type(
                list[FullResourceResponse[resource_manager.resource_type]]
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
                - `400`: Bad request - Invalid query parameters or search error"""
            ),
        )
        async def list_resources_full(
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
                    resources_data: list[FullResourceResponse[T]] = []
                    for meta in metas:
                        try:
                            resource = resource_manager.get(meta.resource_id)
                            resources_data.append(
                                FullResourceResponse(
                                    data=resource.data,
                                    revision_info=resource.info,
                                    meta=meta,
                                )
                            )
                        except Exception:
                            # 如果無法獲取資源數據，跳過
                            continue

                return MsgspecResponse(resources_data)
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))


class PatchRouteTemplate(BaseRouteTemplate):
    """部分更新資源的路由模板"""

    def apply(
        self, model_name: str, resource_manager: IResourceManager[T], router: APIRouter
    ) -> None:
        # 動態創建響應模型
        @router.patch(
            f"/{model_name}/{{resource_id}}",
            response_class=MsgspecResponse,
            responses=struct_to_responses_type(RevisionInfo),
            summary=f"Partially update {model_name}",
            tags=[f"{model_name}"],
            description=textwrap.dedent(
                f"""
                Partially update a `{model_name}` resource using JSON Patch operations.

                **Path Parameters:**
                - `resource_id`: The unique identifier of the resource to patch

                **Request Body:**
                - Send JSON Patch operations as an array of patch objects
                - Each patch operation should follow RFC 6902 JSON Patch specification
                - Supports operations: `add`, `remove`, `replace`, `move`, `copy`, `test`

                **JSON Patch Format:**
                ```json
                [
                {{"op": "replace", "path": "/field_name", "value": "new_value"}},
                {{"op": "add", "path": "/new_field", "value": "field_value"}},
                {{"op": "remove", "path": "/unwanted_field"}}
                ]
                ```

                **Response:**
                - Returns revision information for the patched resource
                - Includes new `revision_id` and maintains `resource_id`
                - Creates a new version while preserving revision history

                **Version Control:**
                - Each patch creates a new revision
                - Previous versions remain accessible via revision history
                - Original resource ID is preserved across patches

                **Examples:**
                - `PATCH /{model_name}/123` with JSON Patch array - Apply patches to resource
                - Response includes updated revision information

                **Error Responses:**
                - `400`: Bad request - Invalid patch operations or resource not found
                - `404`: Resource does not exist"""
            ),
        )
        async def patch_resource(
            resource_id: str,
            patch_data: list[dict],
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            from jsonpatch import JsonPatch

            try:
                with resource_manager.meta_provide(current_user, current_time):
                    patch = JsonPatch(patch_data)
                    info = resource_manager.patch(resource_id, patch)
                return MsgspecResponse(info)
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))


class SwitchRevisionRouteTemplate(BaseRouteTemplate):
    """切換資源版本的路由模板"""

    def apply(
        self, model_name: str, resource_manager: IResourceManager[T], router: APIRouter
    ) -> None:
        @router.post(
            f"/{model_name}/{{resource_id}}/switch/{{revision_id}}",
            response_class=MsgspecResponse,
            responses=struct_to_responses_type(ResourceMeta),
            summary=f"Switch {model_name} to specific revision",
            tags=[f"{model_name}"],
            description=textwrap.dedent(
                f"""
                Switch a `{model_name}` resource to a specific revision, making it the current active version.

                **Path Parameters:**
                - `resource_id`: The unique identifier of the resource
                - `revision_id`: The specific revision ID to switch to

                **Version Control Operation:**
                - Changes the current active revision of the resource
                - The specified revision becomes the new "current" version
                - All previous revisions remain preserved in history
                - Does not create a new revision, just changes the pointer

                **Response:**
                - Returns confirmation with resource and revision information
                - Includes the new `current_revision_id`
                - Provides success message confirming the switch

                **Use Cases:**
                - Roll back to a previous version of a resource
                - Restore a specific revision as the current version
                - Undo recent changes by switching to an earlier revision
                - Switch between different versions for testing or comparison

                **Examples:**
                - `POST /{model_name}/123/switch/rev456` - Switch resource 123 to revision rev456
                - Response confirms the successful revision switch

                **Error Responses:**
                - `400`: Bad request - Invalid revision ID or switch operation failed
                - `404`: Resource or revision does not exist

                **Note:** This operation changes which revision is considered "current" but does not modify the revision history."""
            ),
        )
        async def switch_revision(
            resource_id: str,
            revision_id: str,
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            try:
                with resource_manager.meta_provide(current_user, current_time):
                    meta = resource_manager.switch(resource_id, revision_id)
                return MsgspecResponse(meta)
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))


class RestoreRouteTemplate(BaseRouteTemplate):
    """恢復已刪除資源的路由模板"""

    def apply(
        self, model_name: str, resource_manager: IResourceManager[T], router: APIRouter
    ) -> None:
        @router.post(
            f"/{model_name}/{{resource_id}}/restore",
            response_class=MsgspecResponse,
            responses=struct_to_responses_type(ResourceMeta),
            summary=f"Restore deleted {model_name}",
            tags=[f"{model_name}"],
            description=textwrap.dedent(
                f"""
                Restore a previously deleted `{model_name}` resource, making it active again.

                **Path Parameters:**
                - `resource_id`: The unique identifier of the deleted resource to restore

                **Restore Operation:**
                - Unmarks a soft-deleted resource, making it active again
                - Changes the `is_deleted` status from `true` to `false`
                - All revision history remains intact during restoration
                - The resource becomes accessible through normal operations again

                **Response:**
                - Returns confirmation with resource metadata
                - Includes updated `is_deleted` status (will be `false`)
                - Shows current `revision_id` and resource information
                - Provides success message confirming the restoration

                **Use Cases:**
                - Recover accidentally deleted resources
                - Restore resources that were soft-deleted for temporary removal
                - Undo deletion operations without losing data or history
                - Reactivate archived resources for continued use

                **Examples:**
                - `POST /{model_name}/123/restore` - Restore deleted resource with ID 123
                - Response shows updated metadata with `is_deleted: false`

                **Error Responses:**
                - `400`: Bad request - Resource is not deleted or restore operation failed
                - `404`: Resource does not exist

                **Note:** Only works with soft-deleted resources. The resource must exist and be marked as deleted to be restored."""
            ),
        )
        async def restore_resource(
            resource_id: str,
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            try:
                with resource_manager.meta_provide(current_user, current_time):
                    meta = resource_manager.restore(resource_id)
                return MsgspecResponse(meta)
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))


class AutoCRUD:
    """AutoCRUD - Automatic CRUD API Generator for FastAPI

    AutoCRUD is the main class that automatically generates complete CRUD (Create, Read, Update, Delete)
    APIs for your data models. It provides a powerful, flexible, and easy-to-use system for building
    RESTful APIs with built-in version control, soft deletion, and comprehensive querying capabilities.

    Key Features:
    - **Automatic API Generation**: Generates complete CRUD endpoints for any data model
    - **Version Control**: Built-in revision tracking for all resources with full history
    - **Soft Deletion**: Resources are marked as deleted rather than permanently removed
    - **Flexible Storage**: Support for both memory and disk-based storage backends
    - **Model Agnostic**: Works with msgspec Structs, and other data types
    - **Customizable Routes**: Extensible route template system for custom endpoints
    - **Data Migration**: Built-in support for schema evolution and data migration
    - **Comprehensive Querying**: Advanced filtering, sorting, and pagination capabilities

    Basic Usage:
    ```python
    from fastapi import FastAPI
    from autocrud import AutoCRUD

    # Create AutoCRUD instance
    autocrud = AutoCRUD()

    # Add your model
    autocrud.add_model(User)

    # Apply to FastAPI router
    app = FastAPI()
    autocrud.apply(app)
    ```

    This generates the following endpoints for your User model:
    - `POST /users` - Create a new user
    - `GET /users/data` - List all users (data only)
    - `GET /users/meta` - List all users (metadata only)
    - `GET /users/revision-info` - List all users (revision info only)
    - `GET /users/full` - List all users (complete information)
    - `GET /users/{id}/data` - Get specific user data
    - `GET /users/{id}/meta` - Get specific user metadata
    - `GET /users/{id}/revision-info` - Get specific user revision info
    - `GET /users/{id}/full` - Get complete user information
    - `GET /users/{id}/revision-list` - Get user revision history
    - `PUT /users/{id}` - Update user (full replacement)
    - `PATCH /users/{id}` - Partially update user (JSON Patch)
    - `DELETE /users/{id}` - Soft delete user
    - `POST /users/{id}/restore` - Restore deleted user
    - `POST /users/{id}/switch/{revision_id}` - Switch to specific revision

    Advanced Features:
    - **Custom Storage**: Use disk-based storage for persistence
    - **Data Migration**: Handle schema changes with migration support
    - **Custom Naming**: Control URL patterns and resource names
    - **Route Customization**: Add custom endpoints with route templates
    - **Backup/Restore**: Export and import complete datasets

    Args:
        model_naming: Controls how model names are converted to URL paths.
                     Options: "same", "pascal", "camel", "snake", "kebab" (default)
                     or a custom function that takes a type and returns a string.
        route_templates: Custom list of route templates to use instead of defaults.
                        If None, uses the standard CRUD route templates.

    Example with Advanced Features:
    ```python
    from autocrud import AutoCRUD, DiskStorageFactory
    from pathlib import Path

    # Use disk storage for persistence
    storage_factory = DiskStorageFactory(Path("./data"))

    # Custom naming (convert CamelCase to snake_case)
    autocrud = AutoCRUD(model_naming="snake")

    # Add model with custom configuration
    autocrud.add_model(
        User,
        name="people",  # Custom URL path
        storage_factory=storage_factory,
        id_generator=lambda: f"user_{uuid.uuid4()}"  # Custom ID generation
    )
    ```

    Thread Safety:
    The AutoCRUD instance is thread-safe for read operations, but adding models
    should be done during application startup before handling requests.

    Performance:
    - Memory storage: Suitable for development and small datasets
    - Disk storage: Recommended for production with large datasets
    - All operations are optimized for typical CRUD workloads
    - Built-in pagination prevents memory issues with large result sets

    See Also:
    - IStorageFactory: For implementing custom storage backends
    - IRouteTemplate: For creating custom endpoint templates
    - IResourceManager: For advanced programmatic resource management
    """

    def __init__(
        self,
        *,
        model_naming: Literal["same", "pascal", "camel", "snake", "kebab"]
        | Callable[[type], str] = "kebab",
        route_templates: list[IRouteTemplate] | None = None,
        storage_factory: IStorageFactory | None = None,
        admin: str | None = None,
    ):
        if storage_factory is None:
            self.storage_factory = MemoryStorageFactory()
        else:
            self.storage_factory = storage_factory
        self.resource_managers: OrderedDict[str, IResourceManager] = OrderedDict()
        self.model_naming = model_naming
        self.route_templates: list[IRouteTemplate] = (
            [
                CreateRouteTemplate(),
                ListRouteTemplate(),
                ReadRouteTemplate(),
                UpdateRouteTemplate(),
                PatchRouteTemplate(),
                SwitchRevisionRouteTemplate(),
                DeleteRouteTemplate(),
                RestoreRouteTemplate(),
            ]
            if route_templates is None
            else route_templates
        )
        self.route_templates.sort()
        if not admin:
            self.permission_checker = AllowAll()
        else:
            self.permission_checker = RBACPermissionChecker(
                storage_factory=self.storage_factory,
                root_user=admin,
            )

    def _resource_name(self, model: type[T]) -> str:
        """Convert model class name to resource name using the configured naming convention.

        This internal method handles the conversion of Python class names to URL-friendly
        resource names based on the model_naming configuration.

        Args:
            model: The model class whose name should be converted.

        Returns:
            The converted resource name string that will be used in URLs.

        Examples:
            With model_naming="kebab":
            - UserProfile -> "user-profile"
            - BlogPost -> "blog-post"

            With model_naming="snake":
            - UserProfile -> "user_profile"
            - BlogPost -> "blog_post"

            With custom function:
            - Can implement any custom naming logic
        """
        if callable(self.model_naming):
            return self.model_naming(model)
        original_name = model.__name__

        # 使用 NameConverter 進行轉換
        return NameConverter(original_name).to(self.model_naming)

    def add_route_template(self, template: IRouteTemplate) -> None:
        """Add a custom route template to extend the API with additional endpoints.

        Route templates define how to generate specific API endpoints for models.
        By adding custom templates, you can extend the default CRUD functionality
        with specialized endpoints for your use cases.

        Args:
            template: A custom route template implementing IRouteTemplate interface.

        Example:
            ```python
            class CustomSearchTemplate(BaseRouteTemplate):
                def apply(self, model_name, resource_manager, router):
                    @router.get(f"/{model_name}/search")
                    async def search_resources(query: str):
                        # Custom search logic
                        pass

            autocrud = AutoCRUD()
            autocrud.add_route_template(CustomSearchTemplate())
            autocrud.add_model(User)
            ```

        Note:
            Templates are sorted by their order property before being applied.
            Add templates before calling add_model() or apply() for best results.
        """
        self.route_templates.append(template)

    def add_model(
        self,
        model: type[T],
        *,
        name: str | None = None,
        id_generator: Callable[[], str] | None = None,
        storage: IStorage | None = None,
        migration: IMigration | None = None,
        indexed_fields: list[tuple[str, type] | IndexableField] | None = None,
    ) -> None:
        """Add a data model to AutoCRUD and configure its API endpoints.

        This is the main method for registering models with AutoCRUD. Once added,
        the model will have a complete set of CRUD API endpoints generated automatically.

        Args:
            model: The data model class (msgspec Struct, dataclasses, TypedDict).
            name: Custom resource name for URLs. If None, derived from model class name.
            storage_factory: Custom storage backend. If None, uses in-memory storage.
            id_generator: Custom function for generating resource IDs. If None, uses UUID4.
            migration: Migration handler for schema evolution. Used with disk storage.

        Examples:
            Basic usage:
            ```python
            autocrud.add_model(User)  # Creates /users endpoints
            ```

            With custom name:
            ```python
            autocrud.add_model(User, name="people")  # Creates /people endpoints
            ```

            With persistent storage:
            ```python
            storage = DiskStorageFactory("./data")
            autocrud.add_model(User, storage_factory=storage)
            ```

            With custom ID generation:
            ```python
            autocrud.add_model(
                User,
                id_generator=lambda: f"user_{int(time.time())}"
            )
            ```

            With migration support:
            ```python
            class UserMigration(IMigration):
                schema_version = "v2"
                def migrate(self, data, old_version):
                    # Handle schema changes
                    return updated_data

            autocrud.add_model(User, migration=UserMigration())
            ```

        Generated Endpoints:
            For a model named "User", this creates:
            - POST /users - Create new user
            - GET /users/data - List users (data only)
            - GET /users/meta - List users (metadata only)
            - GET /users/{id}/data - Get user data
            - GET /users/{id}/full - Get complete user info
            - PUT /users/{id} - Update user
            - DELETE /users/{id} - Soft delete user
            - And many more...

        Raises:
            ValueError: If model is invalid or conflicts with existing models.

        Note:
            Models should be added during application startup before handling requests.
            The order of adding models doesn't affect the generated APIs.
        """
        _indexed_fields = []
        for field in indexed_fields or []:
            if isinstance(field, IndexableField):
                _indexed_fields.append(field)
            elif (
                isinstance(field, tuple)
                and len(field) == 2
                and isinstance(field[0], str)
                and isinstance(field[1], type)
            ):
                field = IndexableField(field_path=field[0], field_type=field[1])
                _indexed_fields.append(field)
            else:
                raise TypeError(
                    "Invalid indexed field, should be IndexableField or tuple[field_name, field_type]"
                )
        model_name = name or self._resource_name(model)
        if storage is None:
            storage = self.storage_factory.build(model, model_name, migration=migration)
        resource_manager = ResourceManager(
            model,
            storage=storage,
            id_generator=id_generator,
            migration=migration,
            indexed_fields=_indexed_fields,
        )
        self.resource_managers[model_name] = resource_manager

    def openapi(self, app: FastAPI):
        # Handle root_path by setting servers if not already set
        servers = app.servers
        if app.root_path and not servers:
            servers = [{"url": app.root_path}]

        app.openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            summary=app.summary,
            description=app.description,
            terms_of_service=app.terms_of_service,
            contact=app.contact,
            license_info=app.license_info,
            routes=app.routes,
            webhooks=app.webhooks.routes,
            tags=app.openapi_tags,
            servers=servers,
            separate_input_output_schemas=app.separate_input_output_schemas,
        )
        app.openapi_schema["components"]["schemas"] |= jsonschema_to_openapi(
            [
                ResourceMeta,
                RevisionInfo,
                RevisionListResponse,
                *[rm.resource_type for rm in self.resource_managers.values()],
                *[
                    FullResourceResponse[rm.resource_type]
                    for rm in self.resource_managers.values()
                ],
            ]
        )[1]

    def apply(self, router: APIRouter) -> APIRouter:
        """Apply all route templates to generate API endpoints on the given router.

        This method generates all the CRUD endpoints for all registered models
        and applies them to the provided FastAPI router. This is typically the
        final step in setting up your AutoCRUD API.

        Args:
            router: FastAPI APIRouter or FastAPI app instance to add routes to.

        Returns:
            The same router instance with all generated routes added.

        Example:
            ```python
            from fastapi import FastAPI
            from autocrud import AutoCRUD

            app = FastAPI()
            autocrud = AutoCRUD()

            # Add your models
            autocrud.add_model(User)
            autocrud.add_model(Post)

            # Generate and apply all routes
            autocrud.apply(app)

            # Or with a sub-router
            api_router = APIRouter(prefix="/api/v1")
            autocrud.apply(api_router)
            app.include_router(api_router)
            ```

        Generated Routes:
            For each model, applies all route templates in order to create
            a comprehensive set of CRUD endpoints. The exact endpoints depend
            on the route templates configured.

        Note:
            - Call this method after adding all models and custom route templates
            - Each route template is applied to each model in the order specified
            - Routes are generated dynamically based on model structure
            - This method is idempotent - calling it multiple times is safe
        """
        for model_name, resource_manager in self.resource_managers.items():
            for route_template in self.route_templates:
                try:
                    route_template.apply(model_name, resource_manager, router)
                except Exception:
                    pass
        return router

    def dump(self, bio: IO[bytes]) -> None:
        """Export all resources and their data to a tar archive for backup or migration.

        This method creates a complete backup of all resources managed by AutoCRUD,
        including all data, metadata, and revision history. The output is a tar
        archive that can be used for backup, migration, or data transfer purposes.

        Args:
            bio: A binary I/O stream to write the tar archive to.

        Example:
            ```python
            # Backup to file
            with open("backup.tar", "wb") as f:
                autocrud.dump(f)

            # Backup to memory buffer
            import io
            buffer = io.BytesIO()
            autocrud.dump(buffer)
            backup_data = buffer.getvalue()

            # Upload to cloud storage
            import boto3
            s3 = boto3.client('s3')
            with io.BytesIO() as buffer:
                autocrud.dump(buffer)
                buffer.seek(0)
                s3.upload_fileobj(buffer, 'backup-bucket', 'autocrud-backup.tar')
            ```

        Archive Structure:
            The tar archive contains:
            - One directory per model (e.g., "users/", "posts/")
            - Within each directory, files containing resource data
            - All metadata, revision history, and relationships preserved
            - Compatible with the load() method for restoration

        Use Cases:
            - Regular backups of your data
            - Migrating between environments
            - Data archival and compliance
            - Disaster recovery preparations
            - Development data seeding

        Note:
            - The archive includes ALL resources, including soft-deleted ones
            - Large datasets may result in large archive files
            - Consider streaming to avoid memory issues with large datasets
            - The archive format is compatible across AutoCRUD versions
        """
        with tarfile.open(fileobj=bio, mode="w|") as tar:
            for model_name, mgr in self.resource_managers.items():
                for key, value in mgr.dump():
                    data = io.BytesIO(value)
                    tarinfo = tarfile.TarInfo(name=f"{model_name}/{key}")
                    tarinfo.size = len(value)
                    tar.addfile(tarinfo, fileobj=data)

    def load(self, bio: IO[bytes]) -> None:
        """Import resources from a tar archive created by the dump() method.

        This method restores resources from a backup archive, recreating all
        data, metadata, and revision history. It's the complement to dump()
        and enables complete data restoration and migration scenarios.

        Args:
            bio: A binary I/O stream containing the tar archive to load from.

        Example:
            ```python
            # Restore from file backup
            with open("backup.tar", "rb") as f:
                autocrud.load(f)

            # Restore from memory buffer
            import io
            buffer = io.BytesIO(backup_data)
            autocrud.load(buffer)

            # Download and restore from cloud storage
            import boto3
            s3 = boto3.client('s3')
            with io.BytesIO() as buffer:
                s3.download_fileobj('backup-bucket', 'autocrud-backup.tar', buffer)
                buffer.seek(0)
                autocrud.load(buffer)
            ```

        Behavior:
            - Only loads data for models that are registered with add_model()
            - Preserves all metadata including timestamps and user information
            - Restores complete revision history for each resource
            - Maintains data integrity and relationships
            - Handles both active and soft-deleted resources

        Migration Scenarios:
            ```python
            # Environment migration
            # On source system:
            autocrud_source.dump(backup_file)

            # On target system:
            autocrud_target.add_model(User)  # Must add models first
            autocrud_target.add_model(Post)
            autocrud_target.load(backup_file)
            ```

        Error Handling:
            - Raises ValueError if archive contains unknown models
            - Raises ValueError if archive format is invalid
            - Existing resources may be overwritten depending on storage backend

        Use Cases:
            - Disaster recovery and data restoration
            - Environment migrations (dev → staging → prod)
            - Data seeding for testing environments
            - Historical data imports
            - System migrations and upgrades

        Important Notes:
            - Models must be registered before loading data for them
            - Archive must be created by a compatible dump() method
            - Loading may overwrite existing resources with same IDs
            - Consider backup existing data before loading
            - Large archives may take significant time to process
        """
        with tarfile.open(fileobj=bio, mode="r|") as tar:
            for tarinfo in tar:
                if not tarinfo.isfile():
                    raise ValueError(f"TarInfo {tarinfo.name} is not a file.")
                model_name, key = tarinfo.name.split("/", 1)
                if model_name in self.resource_managers:
                    mgr = self.resource_managers[model_name]
                    mgr.load(key, tar.extractfile(tarinfo))
                else:
                    raise ValueError(
                        f"Model {model_name} not found in resource managers."
                    )
