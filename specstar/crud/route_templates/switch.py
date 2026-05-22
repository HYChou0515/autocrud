import datetime as dt
import textwrap
from typing import TypeVar

from fastapi import APIRouter, Depends

from specstar.crud.route_templates.basic import (
    BaseRouteTemplate,
    MsgspecResponse,
    struct_to_responses_type,
)
from specstar.crud.route_templates.exception_handlers import to_http_exception
from specstar.types import (
    IResourceManager,
    ResourceMeta,
)

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
                normalized = _normalize_revision_id(resource_id, revision_id)
                with resource_manager.using(current_user, current_time):
                    meta = resource_manager.switch(resource_id, normalized)
                return MsgspecResponse(meta)
            except Exception as e:
                raise to_http_exception(e)


def _normalize_revision_id(resource_id: str, revision_id: str) -> str:
    """Accept either the full revision_id (``{resource_id}:{number}``) or
    the bare revision number, and reject obvious garbage with a 400 + hint.

    The path already carries ``resource_id``, so users naturally try to
    pass just the revision number on ``/switch/{revision_id}``. Without
    this normalization that produces a bare ``404`` with no hint.
    """
    if not revision_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="revision_id is required")
    if revision_id.isdigit():
        return f"{resource_id}:{revision_id}"
    expected_prefix = f"{resource_id}:"
    if revision_id.startswith(expected_prefix):
        suffix = revision_id[len(expected_prefix) :]
        if suffix.isdigit():
            return revision_id
    from fastapi import HTTPException

    raise HTTPException(
        status_code=400,
        detail=(
            f"Invalid revision_id {revision_id!r}. Expected the full id "
            f"{expected_prefix}<n> (e.g. {expected_prefix}3) or the bare "
            f"revision number (e.g. 3)."
        ),
    )
