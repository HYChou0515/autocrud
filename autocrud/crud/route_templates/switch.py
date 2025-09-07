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


class SwitchRevisionRouteTemplate(BaseRouteTemplate):
    """切換資源版本的路由模板"""

    def apply(
        self,
        model_name: str,
        resource_manager: IResourceManager[T],
        router: APIRouter,
    ) -> None:
        @router.post(
            f"/{model_name}/{{resource_id}}/switch/{{revision_id}}",
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

                **Note:** This operation changes which revision is considered "current" but does not modify the revision history.""",
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
