import datetime as dt
import textwrap
from typing import Any, Literal, TypeVar

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


class RFC6902_Copy(msgspec.Struct, tag_field="op", tag="copy"):
    from_: str = msgspec.field(name="from")
    path: str


class RFC6902_Test(msgspec.Struct, tag_field="op", tag="test"):
    path: str
    value: Any


class RFC6902_Move(msgspec.Struct, tag_field="op", tag="move"):
    from_: str = msgspec.field(name="from")
    path: str


class RFC6902_Replace(msgspec.Struct, tag_field="op", tag="replace"):
    path: str
    value: Any


class RFC6902_Remove(msgspec.Struct, tag_field="op", tag="remove"):
    path: str


class RFC6902_Add(msgspec.Struct, tag_field="op", tag="add"):
    path: str
    value: Any


RFC6902 = (
    RFC6902_Add
    | RFC6902_Remove
    | RFC6902_Replace
    | RFC6902_Move
    | RFC6902_Test
    | RFC6902_Copy
)


class PatchRouteTemplate(BaseRouteTemplate):
    """部分更新資源的路由模板"""

    def apply(
        self,
        model_name: str,
        resource_manager: IResourceManager[T],
        router: APIRouter,
    ) -> None:
        @router.patch(
            f"/{model_name}/{{resource_id}}",
            responses=struct_to_responses_type(RevisionInfo),
            summary=f"Partially update {model_name}",
            tags=[f"{model_name}"],
            description=textwrap.dedent(
                f"""
                Partially update a `{model_name}` resource using JSON Patch operations.

                **Path Parameters:**
                - `resource_id`: The unique identifier of the resource to patch

                **Request Body:**
                - Send JSON Patch operations as an array of patch objects
                - Each patch operation should follow RFC 6902 JSON Patch specification
                - Supports operations: `add`, `remove`, `replace`, `move`, `copy`, `test`

                **JSON Patch Format:**
                ```json
                [
                {{"op": "replace", "path": "/field_name", "value": "new_value"}},
                {{"op": "add", "path": "/new_field", "value": "field_value"}},
                {{"op": "remove", "path": "/unwanted_field"}}
                ]
                ```

                **Response:**
                - Returns revision information for the patched resource
                - Includes new `revision_id` and maintains `resource_id`
                - Creates a new version while preserving revision history

                **Version Control:**
                - Each patch creates a new revision
                - Previous versions remain accessible via revision history
                - Original resource ID is preserved across patches

                **Examples:**
                - `PATCH /{model_name}/123` with JSON Patch array - Apply patches to resource
                - Response includes updated revision information

                **Error Responses:**
                - `400`: Bad request - Invalid patch operations or resource not found
                - `404`: Resource does not exist""",
            ),
        )
        async def patch_resource(
            resource_id: str,
            body=Body(
                title="RFC6902",
                json_schema_extra=jsonschema_to_json_schema_extra(list[RFC6902]),
            ),
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
            change_status: RevisionStatus | None = None,
            mode: Literal["update", "modify"] = "update",
        ):
            from jsonpatch import JsonPatch

            if mode != "modify" and change_status is not None:
                raise HTTPException(
                    status_code=400,
                    detail="change_status can only be used with mode 'modify'",
                )
            try:
                with resource_manager.meta_provide(current_user, current_time):
                    patch = JsonPatch(body)
                    if mode == "update":
                        info = resource_manager.patch(resource_id, patch)
                    else:  # mode == "modify"
                        info = resource_manager.modify(
                            resource_id,
                            patch,
                            status=msgspec.UNSET
                            if change_status is None
                            else change_status,
                        )
                return MsgspecResponse(info)
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
