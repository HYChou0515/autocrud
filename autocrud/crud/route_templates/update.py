import datetime as dt
import textwrap
from typing import TypeVar, Literal

import msgspec
from fastapi import APIRouter, Depends, HTTPException
from fastapi.params import Body

from autocrud.crud.route_templates.basic import (
    BaseRouteTemplate,
    MsgspecResponse,
    jsonschema_to_json_schema_extra,
    struct_to_responses_type,
)
from autocrud.types import IResourceManager, RevisionStatus
from autocrud.types import RevisionInfo

T = TypeVar("T")


class UpdateRouteTemplate(BaseRouteTemplate):
    """更新資源的路由模板"""

    def apply(
        self,
        model_name: str,
        resource_manager: IResourceManager[T],
        router: APIRouter,
    ) -> None:
        resource_type = resource_manager.resource_type

        @router.put(
            f"/{model_name}/{{resource_id}}",
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
                - `404`: Resource does not exist""",
            ),
        )
        async def update_resource(
            resource_id: str,
            body=Body(
                None,
                json_schema_extra=jsonschema_to_json_schema_extra(resource_type),
            ),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
            change_status: RevisionStatus | None = None,
            mode: Literal["update", "modify"] = "update",
        ):
            if mode != "modify" and change_status is not None:
                raise HTTPException(
                    status_code=400,
                    detail="change_status can only be used with mode 'modify'",
                )
            try:
                if body is None:
                    data = msgspec.UNSET
                else:
                    data = msgspec.convert(body, resource_type)
                if mode == "update":
                    with resource_manager.meta_provide(current_user, current_time):
                        info = resource_manager.update(resource_id, data)
                else:  # mode == "modify"
                    with resource_manager.meta_provide(current_user, current_time):
                        info = resource_manager.modify(
                            resource_id,
                            data,
                            status=msgspec.UNSET
                            if change_status is None
                            else change_status,
                        )
                return MsgspecResponse(info)
            except msgspec.ValidationError as e:
                # 數據驗證錯誤，返回 422
                raise HTTPException(status_code=422, detail=str(e))
            except Exception as e:
                # 其他錯誤，返回 400
                raise HTTPException(status_code=400, detail=str(e))
