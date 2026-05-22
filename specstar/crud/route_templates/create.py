import datetime as dt
import textwrap
from typing import TypeVar

import msgspec
from fastapi import APIRouter, Depends, HTTPException
from fastapi.params import Body

from specstar.crud.route_templates.basic import (
    BaseRouteTemplate,
    MsgspecResponse,
    jsonschema_to_json_schema_extra,
    struct_to_responses_type,
)
from specstar.crud.route_templates.exception_handlers import to_http_exception
from specstar.types import (
    IResourceManager,
    RevisionInfo,
)

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

        # ``resource_id`` belongs to the server-generated meta, not the
        # resource's data. Reject it loudly if a client tries to set it via
        # the POST body unless the Struct actually declares such a field
        # (rare). This avoids the previous silent-drop behavior where a
        # client thought they'd set the id but the server generated a
        # different one anyway.
        try:
            _struct_field_names = {
                f.name for f in msgspec.structs.fields(resource_type)
            }
        except TypeError:
            _struct_field_names = set()
        _reject_resource_id_in_body = "resource_id" not in _struct_field_names

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
            if (
                _reject_resource_id_in_body
                and isinstance(body, dict)
                and "resource_id" in body
            ):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "`resource_id` cannot be supplied in the POST body — "
                        "the server always generates it. To customise id "
                        "generation, pass `id_generator=` when calling "
                        "`spec.add_model(...)`."
                    ),
                )
            try:
                # Pass the raw body through so the manager's ``_coerce_data``
                # decorator can apply ``forbid_unknown_fields`` checks before
                # ``msgspec.convert`` drops unknown keys.
                with resource_manager.using(current_user, current_time):
                    info = resource_manager.create(body)
                return MsgspecResponse(info)
            except Exception as e:
                raise to_http_exception(e)
