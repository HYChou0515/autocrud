import datetime as dt
import textwrap
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException

from autocrud.crud.route_templates.basic import (
    BaseRouteTemplate,
    MsgspecResponse,
    struct_to_responses_type,
)
from autocrud.types import IResourceManager
from autocrud.types import ResourceMeta

T = TypeVar("T")


class DeleteRouteTemplate(BaseRouteTemplate):
    """刪除資源的路由模板"""

    def apply(
        self,
        model_name: str,
        resource_manager: IResourceManager[T],
        router: APIRouter,
    ) -> None:
        # 動態創建響應模型
        @router.delete(
            f"/{model_name}/{{resource_id}}",
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
                - `404`: Resource does not exist""",
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


class RestoreRouteTemplate(BaseRouteTemplate):
    """恢復已刪除資源的路由模板"""

    def apply(
        self,
        model_name: str,
        resource_manager: IResourceManager[T],
        router: APIRouter,
    ) -> None:
        @router.post(
            f"/{model_name}/{{resource_id}}/restore",
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

                **Note:** Only works with soft-deleted resources. The resource must exist and be marked as deleted to be restored.""",
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
