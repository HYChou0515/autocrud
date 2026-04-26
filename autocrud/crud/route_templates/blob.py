from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query, Response, UploadFile
from fastapi.responses import RedirectResponse
from msgspec import UNSET, UnsetType
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from autocrud.crud.route_templates.basic import BaseRouteTemplate, MsgspecResponse
from autocrud.crud.route_templates.exception_handlers import to_http_exception
from autocrud.resource_manager.basic import IBlobStore
from autocrud.resource_manager.core import ResourceManager
from autocrud.types import (
    Binary,
    IResourceManager,
)

# ---------------------------------------------------------------------------
# Request body for creating an upload session
# ---------------------------------------------------------------------------


class _CreateUploadSessionRequest(BaseModel):
    content_type: str | None = None
    size: int | None = None
    total_parts: int | None = None


class BlobRouteTemplate(BaseRouteTemplate):
    """Blob route template for downloading and uploading binary content.

    Provides global endpoints (mounted once regardless of how many models
    use it):

    - ``GET /blobs/{file_id}`` — download blob content directly.
    - ``POST /blobs/upload`` — upload a file via multipart/form-data and
      receive back ``{file_id, size, content_type}``.  The returned
      ``file_id`` can then be used in create/update payloads as
      ``{"avatar": {"file_id": "<id>"}}``, eliminating the need to
      base64-encode file data in the JSON body.
    - ``POST /blobs/upload-sessions`` — create an upload session.
    - ``GET /blobs/upload-sessions/{upload_id}`` — query session state.
    - ``PUT /blobs/upload-sessions/{upload_id}/content`` — upload bytes
      (proxy mode only).
    - ``POST /blobs/upload-sessions/{upload_id}/finalize`` — commit to
      blob store and return ``Binary`` metadata.
    - ``POST /blobs/upload-sessions/{upload_id}/abort`` — discard session.

    All upload-session management is delegated to the underlying
    :class:`IBlobStore` implementation.
    """

    def __init__(self, dependency_provider=None):
        super().__init__(dependency_provider)
        self.mounted = False
        self._blob_getter_rm: IResourceManager | None = None
        self._blob_store: IBlobStore | None = None

    def apply(
        self, model_name: str, resource_manager: IResourceManager, router: APIRouter
    ) -> None:
        if not isinstance(resource_manager, ResourceManager):
            return

        if resource_manager.blob_store is None:
            return

        # Handle unified route mounting
        if not self.mounted:
            self.mounted = True
            # Store the RM to use for fetching blobs (assuming shared blob store)
            self._blob_getter_rm = resource_manager
            self._blob_store = resource_manager.blob_store

            @router.get(
                "/blobs/{file_id}",
                response_class=Response,
                summary="Get blob content directly",
                tags=["Blobs"],
            )
            async def get_blob_direct(
                file_id: str = Path(..., description="File ID of the blob"),
            ):
                if self._blob_getter_rm is None:
                    # This shouldn't be possible if we are in this block, but for safety
                    raise HTTPException(
                        status_code=501, detail="Blob store not configured"
                    )

                try:
                    blob_resp = self._blob_getter_rm.get_blob_response(file_id)

                    if blob_resp.kind == "stream" and blob_resp.stream is not None:
                        media_type = "application/octet-stream"
                        if (
                            blob_resp.stream.content_type
                            and blob_resp.stream.content_type is not UNSET
                        ):
                            media_type = blob_resp.stream.content_type
                        return StreamingResponse(
                            blob_resp.stream.iterator,
                            media_type=media_type,
                            headers={
                                "Content-Length": str(blob_resp.stream.size),
                            },
                        )

                    if blob_resp.kind == "redirect" and blob_resp.url is not None:
                        return RedirectResponse(url=blob_resp.url)

                    if blob_resp.kind == "data" and blob_resp.blob is not None:
                        content = blob_resp.blob
                        if content.data is UNSET:
                            raise HTTPException(
                                status_code=500, detail="Blob data missing"
                            )
                        media_type = "application/octet-stream"
                        if content.content_type is not UNSET:
                            media_type = content.content_type
                        return Response(content=content.data, media_type=media_type)

                    raise HTTPException(
                        status_code=500,
                        detail="Blob store returned invalid response",
                    )
                except Exception as e:
                    raise to_http_exception(e)

            @router.post(
                "/blobs/upload",
                summary="Upload a file to the blob store",
                description=(
                    "Upload a file via multipart/form-data. Returns the blob "
                    "metadata (`file_id`, `size`, `content_type`). Use the "
                    "returned `file_id` in subsequent create/update requests "
                    "to reference the uploaded binary without base64 encoding."
                ),
                tags=["Blobs"],
            )
            async def upload_blob(file: UploadFile):
                if self._blob_store is None:
                    raise HTTPException(
                        status_code=501, detail="Blob store not configured"
                    )

                try:
                    data = await file.read()
                    content_type = file.content_type or "application/octet-stream"
                    stored = self._blob_store.put(data, content_type=content_type)
                    # Return metadata without the raw data
                    result = Binary(
                        file_id=stored.file_id,
                        size=stored.size,
                        content_type=stored.content_type,
                    )
                    return MsgspecResponse(result)
                except Exception as e:
                    raise to_http_exception(e)

            # ---------------------------------------------------------------
            # Upload-session routes
            # ---------------------------------------------------------------

            @router.post(
                "/blobs/upload-sessions",
                summary="Create an upload session",
                description=(
                    "Create a new upload session. Returns session metadata "
                    "including `upload_id` and `upload_method`. For proxy "
                    "uploads, PUT the file bytes to the `upload_url`."
                ),
                tags=["Blobs"],
            )
            async def create_upload_session(
                body: _CreateUploadSessionRequest,
            ):
                if self._blob_store is None:
                    raise HTTPException(
                        status_code=501, detail="Blob store not configured"
                    )

                ct_for_store: str | UnsetType = (
                    body.content_type if body.content_type else UNSET
                )

                try:
                    session = self._blob_store.create_upload_session(
                        content_type=ct_for_store,
                        size=body.size,
                        total_parts=body.total_parts,
                    )
                    return MsgspecResponse(session)
                except Exception as e:
                    raise to_http_exception(e)

            @router.get(
                "/blobs/upload-sessions/{upload_id}",
                summary="Get upload session status",
                tags=["Blobs"],
            )
            async def get_upload_session(
                upload_id: str = Path(..., description="Upload session ID"),
            ):
                if self._blob_store is None:
                    raise HTTPException(
                        status_code=501, detail="Blob store not configured"
                    )

                try:
                    session = self._blob_store.get_upload_session(upload_id)
                    return MsgspecResponse(session)
                except Exception as e:
                    raise to_http_exception(e)

            @router.put(
                "/blobs/upload-sessions/{upload_id}/content",
                summary="Upload bytes for an upload session (proxy mode)",
                description=(
                    "Upload a numbered part for a proxy-mode upload session. "
                    "May be called multiple times with different part numbers, "
                    "potentially in parallel. Returns the current session state "
                    "including `uploaded_size` and `parts_received`."
                ),
                tags=["Blobs"],
            )
            async def upload_session_content(
                file: UploadFile,
                upload_id: str = Path(..., description="Upload session ID"),
                part_number: int = Query(
                    ..., ge=1, description="1-based part number for this chunk"
                ),
            ):
                if self._blob_store is None:
                    raise HTTPException(
                        status_code=501, detail="Blob store not configured"
                    )

                data = await file.read()

                try:
                    self._blob_store.upload_to_session(
                        upload_id, data, part_number=part_number
                    )
                    session = self._blob_store.get_upload_session(upload_id)
                    return MsgspecResponse(session)
                except ValueError as e:
                    raise HTTPException(status_code=409, detail=str(e))
                except Exception as e:
                    raise to_http_exception(e)

            @router.post(
                "/blobs/upload-sessions/{upload_id}/finalize",
                summary="Finalize an upload session",
                description=(
                    "Commits buffered bytes to the blob store and returns "
                    "the final `Binary` metadata (without raw data)."
                ),
                tags=["Blobs"],
            )
            async def finalize_upload_session(
                upload_id: str = Path(..., description="Upload session ID"),
            ):
                if self._blob_store is None:
                    raise HTTPException(
                        status_code=501, detail="Blob store not configured"
                    )

                try:
                    result = self._blob_store.finalize_upload_session(upload_id)
                    return MsgspecResponse(
                        Binary(
                            file_id=result.file_id,
                            size=result.size,
                            content_type=result.content_type,
                        )
                    )
                except ValueError as e:
                    raise HTTPException(status_code=409, detail=str(e))
                except Exception as e:
                    raise to_http_exception(e)

            @router.post(
                "/blobs/upload-sessions/{upload_id}/abort",
                summary="Abort an upload session",
                status_code=204,
                tags=["Blobs"],
            )
            async def abort_upload_session(
                upload_id: str = Path(..., description="Upload session ID"),
            ):
                if self._blob_store is None:
                    raise HTTPException(
                        status_code=501, detail="Blob store not configured"
                    )

                try:
                    self._blob_store.abort_upload_session(upload_id)
                    return Response(status_code=204)
                except ValueError as e:
                    raise HTTPException(status_code=409, detail=str(e))
                except Exception as e:
                    raise to_http_exception(e)
