from fastapi import APIRouter, HTTPException, Path, Response

from autocrud.crud.route_templates.basic import BaseRouteTemplate
from autocrud.types import IResourceManager
from autocrud.resource_manager.core import ResourceManager


class BlobRouteTemplate(BaseRouteTemplate):
    def __init__(self, dependency_provider=None):
        super().__init__(dependency_provider)
        self.mounted = False
        self._blob_getter_rm: IResourceManager | None = None

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
                    content = self._blob_getter_rm.get_blob(file_id)
                    return Response(
                        content=content, media_type="application/octet-stream"
                    )
                except FileNotFoundError:
                    raise HTTPException(status_code=404, detail="Blob not found")
                except NotImplementedError:
                    raise HTTPException(
                        status_code=501, detail="Blob store not configured"
                    )
