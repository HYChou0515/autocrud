import datetime as dt
import textwrap
from typing import Generic, Optional, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query
from msgspec import UNSET

from autocrud.crud.route_templates.basic import (
    BaseRouteTemplate,
    FullResourceResponse,
    MsgspecResponse,
    RevisionListResponse,
    struct_to_responses_type,
)
from autocrud.types import (
    IResourceManager,
)
from autocrud.types import Resource, ResourceMeta, RevisionInfo

T = TypeVar("T")


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
                    resource_id,
                    revision_id,
                )
            else:
                resource = resource_manager.get(resource_id)
        return resource, meta

    def apply(
        self,
        model_name: str,
        resource_manager: IResourceManager[T],
        router: APIRouter,
    ) -> None:
        resource_type = resource_manager.resource_type

        @router.get(
            f"/{model_name}/{{resource_id}}/meta",
            responses=struct_to_responses_type(ResourceMeta),
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
                - `404`: Resource or revision not found""",
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
                            resource_id,
                            revision_id,
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
                - `404`: Resource or revision not found""",
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
            returns: str = Query(
                default="data,revision_info,meta",
                description="Fields to return, comma-separated. Options: data, revision_info, meta",
            ),
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
            returns = [r.strip() for r in returns.split(",")]
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
            return MsgspecResponse(
                FullResourceResponse(
                    data=data,
                    revision_info=revision_info,
                    meta=meta,
                ),
            )

        @router.get(
            f"/{model_name}/{{resource_id}}/revision-list",
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
                - `404`: Resource not found""",
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
                                resource_id,
                                rev_id,
                            )
                            revision_infos.append(rev_resource.info)
                        except Exception:
                            # 如果無法獲取某個版本，跳過
                            continue

                    return MsgspecResponse(
                        RevisionListResponse(
                            meta=meta,
                            revisions=revision_infos,
                        ),
                    )
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=404, detail=str(e))

        @router.get(
            f"/{model_name}/{{resource_id}}/data",
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
                - `404`: Resource or revision not found""",
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
                            resource_id,
                            revision_id,
                        )
                    else:
                        resource = resource_manager.get(resource_id)
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=404, detail=str(e))

            return MsgspecResponse(resource.data)
