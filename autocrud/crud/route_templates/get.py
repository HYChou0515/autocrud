import datetime as dt
import textwrap
from typing import Generic, Optional, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from msgspec import UNSET

from autocrud.crud.route_templates.basic import (
    BaseRouteTemplate,
    FullResourceResponse,
    MsgspecResponse,
    RevisionListResponse,
    classify_partial_fields,
    filter_struct_partial,
    struct_to_responses_type,
)
from autocrud.types import (
    IResourceManager,
    ResourceMeta,
    RevisionInfo,
)

T = TypeVar("T")


class ReadRouteTemplate(BaseRouteTemplate, Generic[T]):
    """讀取單一資源的路由模板"""

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
            deprecated=True,
            description=f"Deprecated: use `GET /{model_name}/{{resource_id}}?returns=meta` instead.",
        )
        async def get_resource_meta(
            request: Request,
            resource_id: str,
            partial: Optional[list[str]] = Query(
                None,
                description="List of meta fields to retrieve (e.g. '/resource_id', '/created_time')",
            ),
            partial_brackets: Optional[list[str]] = Query(
                None,
                alias="partial[]",
                description="List of meta fields to retrieve - for axios support",
                include_in_schema=False,
            ),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            # 獲取資源和元數據
            try:
                fields = partial or partial_brackets
                if fields is None:
                    raw = [
                        v
                        for k, v in request.query_params.multi_items()
                        if k == "partial[]"
                    ]
                    if raw:
                        fields = raw

                with resource_manager.meta_provide(current_user, current_time):
                    meta = resource_manager.get_meta(resource_id)
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=404, detail=str(e))

            # Apply partial filtering (unprefixed fields treated as meta)
            if fields:
                spec = classify_partial_fields(fields, default_category="meta")
                if spec.meta_fields:
                    meta = filter_struct_partial(meta, spec.meta_fields)

            # 根據響應類型處理數據
            return MsgspecResponse(meta)

        @router.get(
            f"/{model_name}/{{resource_id}}/revision-info",
            responses=struct_to_responses_type(RevisionInfo),
            summary=f"Get {model_name} Revision Info",
            tags=[f"{model_name}"],
            deprecated=True,
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
            request: Request,
            resource_id: str,
            revision_id: Optional[str] = Query(
                None,
                description="Specific revision ID to retrieve. If not provided, returns the current revision",
            ),
            partial: Optional[list[str]] = Query(
                None,
                description="List of revision info fields to retrieve (e.g. '/revision_id', '/status')",
            ),
            partial_brackets: Optional[list[str]] = Query(
                None,
                alias="partial[]",
                description="List of revision info fields to retrieve - for axios support",
                include_in_schema=False,
            ),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            # 獲取資源和元數據
            try:
                fields = partial or partial_brackets
                if fields is None:
                    raw = [
                        v
                        for k, v in request.query_params.multi_items()
                        if k == "partial[]"
                    ]
                    if raw:
                        fields = raw

                with resource_manager.meta_provide(current_user, current_time):
                    info = resource_manager.get_revision_info(
                        resource_id,
                        revision_id or UNSET,
                    )
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=404, detail=str(e))

            # Apply partial filtering (unprefixed fields treated as info)
            if fields:
                spec = classify_partial_fields(fields, default_category="info")
                if spec.info_fields:
                    info = filter_struct_partial(info, spec.info_fields)

            return MsgspecResponse(info)

        # Shared implementation for /full and bare path GET endpoints
        async def _handle_get_with_returns(
            request,
            resource_id,
            revision_id,
            partial,
            partial_brackets,
            current_user,
            current_time,
            returns,
        ):
            # 獲取資源和元數據
            try:
                fields = partial or partial_brackets
                if fields is None:
                    raw = [
                        v
                        for k, v in request.query_params.multi_items()
                        if k == "partial[]"
                    ]
                    if raw:
                        fields = raw
                returns_list = [r.strip() for r in returns.split(",")]

                # Classify partial fields by prefix
                spec = classify_partial_fields(fields, default_category="data")

                with resource_manager.meta_provide(current_user, current_time):
                    meta = resource_manager.get_meta(resource_id)
                    target_revision_id = revision_id or meta.current_revision_id

                    data = UNSET
                    revision_info = UNSET

                    # 1. Get Data
                    if "data" in returns_list:
                        if spec.data_fields:
                            data = resource_manager.get_partial(
                                resource_id,
                                target_revision_id,
                                spec.data_fields,
                                schema_version=meta.schema_version,
                            )
                        else:
                            resource = resource_manager.get_resource_revision(
                                resource_id,
                                target_revision_id,
                                schema_version=meta.schema_version,
                            )
                            data = resource.data
                            # Optimization: if we fetched full resource, we have info too
                            if "revision_info" in returns_list:
                                revision_info = resource.info

                    # 2. Get Revision Info (if needed and not yet fetched)
                    if "revision_info" in returns_list and revision_info is UNSET:
                        revision_info = resource_manager.get_revision_info(
                            resource_id,
                            target_revision_id,
                            schema_version=meta.schema_version,
                        )

            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=404, detail=str(e))

            if "meta" not in returns_list:
                meta = UNSET

            # Apply partial filtering on meta and revision_info
            if spec.meta_fields and meta is not UNSET:
                meta = filter_struct_partial(meta, spec.meta_fields)
            if spec.info_fields and revision_info is not UNSET:
                revision_info = filter_struct_partial(revision_info, spec.info_fields)

            return MsgspecResponse(
                FullResourceResponse(
                    data=data,
                    revision_info=revision_info,
                    meta=meta,
                ),
            )

        @router.get(
            f"/{model_name}/{{resource_id}}/full",
            responses=struct_to_responses_type(FullResourceResponse[resource_type]),
            summary=f"Get Complete {model_name} Information",
            tags=[f"{model_name}"],
            deprecated=True,
            description=textwrap.dedent(
                f"""
                Deprecated: use `GET /{model_name}/{{resource_id}}` instead.

                Retrieve complete information for a `{model_name}` resource including data, metadata, and revision info.

                **Query Parameters:**
                - `revision_id` (optional): Specific revision ID to retrieve
                - `partial` (optional): List of fields to retrieve
                - `returns`: Comma-separated fields to return (data, revision_info, meta)

                **Error Responses:**
                - `404`: Resource or revision not found""",
            ),
        )
        async def get_resource_full(
            request: Request,
            resource_id: str,
            revision_id: Optional[str] = Query(
                None,
                description="Specific revision ID to retrieve. If not provided, returns the current revision",
            ),
            partial: Optional[list[str]] = Query(
                None,
                description="List of fields to retrieve (e.g. '/field1', '/nested/field2')",
            ),
            partial_brackets: Optional[list[str]] = Query(
                None,
                alias="partial[]",
                description="List of fields to retrieve (e.g. '/field1', '/nested/field2') - for axios support",
                include_in_schema=False,
            ),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
            returns: str = Query(
                default="data,revision_info,meta",
                description="Fields to return, comma-separated. Options: data, revision_info, meta",
            ),
        ):
            return await _handle_get_with_returns(
                request,
                resource_id,
                revision_id,
                partial,
                partial_brackets,
                current_user,
                current_time,
                returns,
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
                                    - `total`: Total number of revisions matching the query (before limit)
                                    - `has_more`: Whether more revisions are available beyond the returned list

                                **Query Parameters:**
                                - `limit` (default 10): Maximum number of revisions to return
                                - `offset` (default 0): Number of revisions to skip
                                - `sort`: `created_time` or `-created_time` (default `-created_time`)
                                - `created_time_start`: ISO datetime lower bound (inclusive)
                                - `created_time_end`: ISO datetime upper bound (inclusive)
                                - `from_revision_id`: Start listing from this revision_id (inclusive)
                                - `chain_only`: Return only the parent chain from current revision

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
                - `GET /{model_name}/123/revision-list?limit=10&offset=20`
                - `GET /{model_name}/123/revision-list?created_time_start=2025-01-01T00:00:00`
                - `GET /{model_name}/123/revision-list?from_revision_id=rev123`
                - `GET /{model_name}/123/revision-list?chain_only=true`
                - Response includes metadata and array of revision information

                **Error Responses:**
                - `404`: Resource not found""",
            ),
        )
        async def get_resource_revision_list(
            request: Request,
            resource_id: str,
            limit: int = 10,
            offset: int = 0,
            created_time_start: str | None = None,
            created_time_end: str | None = None,
            from_revision_id: str | None = None,
            chain_only: bool = False,
            sort: str = "-created_time",
            partial: Optional[list[str]] = Query(
                None,
                description="List of fields to retrieve (e.g. '/revision_id', '/status', '/meta/resource_id')",
            ),
            partial_brackets: Optional[list[str]] = Query(
                None,
                alias="partial[]",
                description="List of fields to retrieve - for axios support",
                include_in_schema=False,
            ),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            # 獲取資源和元數據
            try:
                fields = partial or partial_brackets
                if fields is None:
                    raw = [
                        v
                        for k, v in request.query_params.multi_items()
                        if k == "partial[]"
                    ]
                    if raw:
                        fields = raw

                # Classify: unprefixed fields default to info
                spec = classify_partial_fields(fields, default_category="info")

                with resource_manager.meta_provide(current_user, current_time):
                    meta = resource_manager.get_meta(resource_id)

                    if sort not in {"created_time", "-created_time"}:
                        raise HTTPException(status_code=400, detail="Invalid sort")

                    if limit < 1:
                        raise HTTPException(
                            status_code=400, detail="limit must be >= 1"
                        )
                    if offset < 0:
                        raise HTTPException(
                            status_code=400, detail="offset must be >= 0"
                        )

                    revision_ids = resource_manager.list_revisions(resource_id)
                    revision_infos: list[RevisionInfo] = []
                    for rev_id in revision_ids:
                        try:
                            info = resource_manager.get_revision_info(
                                resource_id,
                                rev_id,
                                schema_version=meta.schema_version,
                            )
                            revision_infos.append(info)
                        except Exception:
                            # 如果無法獲取某個版本，跳過
                            continue

                    # Sort by created_time
                    reverse = sort == "-created_time"
                    revision_infos.sort(key=lambda r: r.created_time, reverse=reverse)

                    # Filter by created_time range
                    if created_time_start:
                        start_dt = dt.datetime.fromisoformat(created_time_start)
                        revision_infos = [
                            r for r in revision_infos if r.created_time >= start_dt
                        ]
                    if created_time_end:
                        end_dt = dt.datetime.fromisoformat(created_time_end)
                        revision_infos = [
                            r for r in revision_infos if r.created_time <= end_dt
                        ]

                    # Filter by starting revision_id (inclusive)
                    if from_revision_id:
                        idx = next(
                            (
                                i
                                for i, r in enumerate(revision_infos)
                                if r.revision_id == from_revision_id
                            ),
                            None,
                        )
                        if idx is None:
                            raise HTTPException(
                                status_code=404, detail="revision_id not found"
                            )
                        revision_infos = revision_infos[idx:]

                    # Parent chain only (walk via parent_revision_id)
                    if chain_only:
                        by_id = {r.revision_id: r for r in revision_infos}
                        chain: list[RevisionInfo] = []
                        cur = (
                            from_revision_id
                            if from_revision_id
                            else meta.current_revision_id
                        )
                        while cur:
                            info = by_id.get(cur)
                            if info is None:
                                break
                            chain.append(info)
                            cur = info.parent_revision_id
                        revision_infos = chain

                    total = len(revision_infos)
                    revision_infos = revision_infos[offset : offset + limit]
                    has_more = offset + limit < total

                    # Apply partial filtering
                    if spec.meta_fields:
                        meta = filter_struct_partial(meta, spec.meta_fields)
                    if spec.info_fields:
                        revision_infos = [
                            filter_struct_partial(r, spec.info_fields)
                            for r in revision_infos
                        ]

                    return MsgspecResponse(
                        RevisionListResponse(
                            meta=meta,
                            revisions=revision_infos,
                            total=total,
                            has_more=has_more,
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
            deprecated=True,
            description=textwrap.dedent(
                f"""
                Retrieve only the data content of a `{model_name}` resource.

                **Path Parameters:**
                - `resource_id`: The unique identifier of the resource

                **Query Parameters:**
                - `revision_id` (optional): Specific revision ID to retrieve. If not provided, returns the current revision
                - `partial` (optional): List of fields to retrieve (e.g. '/field1', '/nested/field2')

                **Response:**
                - Returns only the resource data without metadata or revision information
                - The response format matches the original resource schema
                - Most lightweight option for retrieving resource content

                **Use Cases:**
                - Simple data retrieval when metadata is not needed
                - Efficient resource content access
                - Integration with external systems that only need the data
                - Lightweight API calls to minimize response size
                - Fetching only necessary data for UI components (using partial)

                **Performance Benefits:**
                - Minimal response payload
                - Faster response times
                - Reduced bandwidth usage
                - Direct access to resource content

                **Examples:**
                - `GET /{model_name}/123/data` - Get current resource data only
                - `GET /{model_name}/123/data?revision_id=rev456` - Get specific revision data only
                - `GET /{model_name}/123/data?partial=/name&partial=/email` - Get specific fields

                **Error Responses:**
                - `404`: Resource or revision not found""",
            ),
        )
        async def get_resource_data(
            request: Request,
            resource_id: str,
            revision_id: Optional[str] = Query(
                None,
                description="Specific revision ID to retrieve. If not provided, returns the current revision",
            ),
            partial: Optional[list[str]] = Query(
                None,
                description="List of fields to retrieve (e.g. '/field1', '/nested/field2')",
            ),
            partial_brackets: Optional[list[str]] = Query(
                None,
                alias="partial[]",
                description="List of fields to retrieve (e.g. '/field1', '/nested/field2') - for axios support",
                include_in_schema=False,
            ),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            # 獲取資源和元數據
            try:
                with resource_manager.meta_provide(current_user, current_time):
                    fields = partial or partial_brackets
                    if fields is None:
                        raw = [
                            v
                            for k, v in request.query_params.multi_items()
                            if k == "partial[]"
                        ]
                        if raw:
                            fields = raw
                    schema_version = UNSET

                    if fields:
                        if not revision_id:
                            meta = resource_manager.get_meta(resource_id)
                            revision_id = meta.current_revision_id
                            schema_version = meta.schema_version
                        return MsgspecResponse(
                            resource_manager.get_partial(
                                resource_id,
                                revision_id,
                                fields,
                                schema_version=schema_version,
                            )
                        )
                    if not revision_id:
                        meta = resource_manager.get_meta(resource_id)
                        schema_version = meta.schema_version
                        revision_id = meta.current_revision_id

                    resource = resource_manager.get_resource_revision(
                        resource_id, revision_id, schema_version=schema_version
                    )
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=404, detail=str(e))

            return MsgspecResponse(resource.data)

        @router.get(
            f"/{model_name}/{{resource_id}}/blobs/{{file_id}}",
            response_class=Response,
            summary="Get blob content",
            tags=[f"{model_name}"],
        )
        async def get_blob(
            resource_id: str = Path(..., description="Resource ID"),
            file_id: str = Path(..., description="File ID of the blob"),
            user: str = Depends(self.deps.get_user),
        ):
            try:
                # Permission check through get()
                with resource_manager.meta_provide(user=user):
                    resource_manager.get(resource_id)
            except Exception:
                raise HTTPException(
                    status_code=403,
                    detail="Permission denied or Resource not found",
                )

            try:
                content = resource_manager.get_blob(file_id)
                if content.data is UNSET:
                    raise HTTPException(status_code=500, detail="Blob data missing")

                media_type = "application/octet-stream"
                if content.content_type is not UNSET:
                    media_type = content.content_type

                return Response(content=content.data, media_type=media_type)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="Blob not found")
            except NotImplementedError:
                raise HTTPException(status_code=400, detail="Blob store not configured")

        # New bare path endpoint — canonical GET for a single resource
        @router.get(
            f"/{model_name}/{{resource_id}}",
            responses=struct_to_responses_type(FullResourceResponse[resource_type]),
            summary=f"Get {model_name} resource",
            tags=[f"{model_name}"],
            description=textwrap.dedent(
                f"""
                Retrieve a `{model_name}` resource by ID.

                Use the `returns` query parameter to control which sections are included in the response.
                By default all sections are returned: `data`, `revision_info`, `meta`.

                **Query Parameters:**
                - `returns` (default `"data,revision_info,meta"`): Comma-separated list of sections to include.
                  Allowed values: `data`, `revision_info`, `meta`.
                - `revision_id` (optional): Specific revision ID to retrieve.
                - `partial` / `partial[]` (optional): List of fields for partial response.

                **Examples:**
                - `GET /{model_name}/123` — full response (data + meta + revision_info)
                - `GET /{model_name}/123?returns=data` — data only
                - `GET /{model_name}/123?returns=data,meta` — data + meta, no revision_info
                - `GET /{model_name}/123?returns=meta` — metadata only
                - `GET /{model_name}/123?partial=/name&partial=/email` — partial data fields

                **Error Responses:**
                - `404`: Resource or revision not found""",
            ),
        )
        async def get_resource(
            request: Request,
            resource_id: str,
            revision_id: Optional[str] = Query(
                None,
                description="Specific revision ID to retrieve. If not provided, returns the current revision",
            ),
            partial: Optional[list[str]] = Query(
                None,
                description="List of fields to retrieve (e.g. '/field1', '/nested/field2')",
            ),
            partial_brackets: Optional[list[str]] = Query(
                None,
                alias="partial[]",
                description="List of fields to retrieve (e.g. '/field1', '/nested/field2') - for axios support",
                include_in_schema=False,
            ),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
            returns: str = Query(
                default="data,revision_info,meta",
                description="Fields to return, comma-separated. Options: data, revision_info, meta",
            ),
        ):
            return await _handle_get_with_returns(
                request,
                resource_id,
                revision_id,
                partial,
                partial_brackets,
                current_user,
                current_time,
                returns,
            )
