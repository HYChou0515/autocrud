from fastapi import APIRouter, Depends, HTTPException, Path, Response

from autocrud.crud.route_templates.basic import BaseRouteTemplate
from autocrud.types import IResourceManager
from autocrud.resource_manager.core import ResourceManager


class BlobRouteTemplate(BaseRouteTemplate):
    def apply(
        self, model_name: str, resource_manager: IResourceManager, router: APIRouter
    ) -> None:
        if not isinstance(resource_manager, ResourceManager):
            return

        if resource_manager.blob_store is None:
            return

        @router.get(
            f"/{model_name}/{{resource_id}}/blobs/{{file_id}}",
            response_class=Response,
            summary="Get blob content",
            tags=[model_name],
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
                    status_code=403, detail="Permission denied or Resource not found"
                )

            try:
                content = resource_manager.get_blob(file_id)
                return Response(content=content, media_type="application/octet-stream")
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="Blob not found")
            except NotImplementedError:
                raise HTTPException(status_code=501, detail="Blob store not configured")
