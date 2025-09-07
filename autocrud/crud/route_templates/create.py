import datetime as dt
import textwrap
from typing import TypeVar

import msgspec
from fastapi import APIRouter, Depends, HTTPException
from fastapi.params import Body

from autocrud.crud.route_templates.basic import (
    BaseRouteTemplate,
    MsgspecResponse,
    jsonschema_to_json_schema_extra,
    struct_to_responses_type,
)
from autocrud.types import IResourceManager
from autocrud.types import RevisionInfo

T = TypeVar("T")


class CreateRouteTemplate(BaseRouteTemplate):
    """創建資源的路由模板"""

    def apply(
        self,
        model_name: str,
        resource_manager: IResourceManager[T],
        router: APIRouter,
    ) -> None:
        # 動態創建響應模型
        resource_type = resource_manager.resource_type

        @router.post(
            f"/{model_name}",
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
                - `400`: Bad request - General creation error""",
            ),
        )
        async def create_resource(
            body=Body(
                json_schema_extra=jsonschema_to_json_schema_extra(resource_type),
            ),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            try:
                data = msgspec.convert(body, resource_type)

                with resource_manager.meta_provide(current_user, current_time):
                    info = resource_manager.create(data)
                return MsgspecResponse(info)
            except msgspec.ValidationError as e:
                # 數據驗證錯誤，返回 422
                raise HTTPException(status_code=422, detail=str(e))
            except Exception as e:
                # 其他錯誤，返回 400
                raise HTTPException(status_code=400, detail=str(e))
