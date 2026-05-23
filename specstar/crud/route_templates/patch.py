import datetime as dt
import textwrap
from typing import Any, Literal, TypeVar

import msgspec
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.params import Body

from specstar.crud.route_templates.basic import (
    BaseRouteTemplate,
    MsgspecResponse,
    jsonschema_to_json_schema_extra,
    reject_resource_id_in_body,
    reject_resource_id_in_patch,
    struct_declares_resource_id,
    struct_to_responses_type,
)
from specstar.crud.route_templates.exception_handlers import to_http_exception
from specstar.crud.route_templates.update import _check_precondition
from specstar.types import (
    IResourceManager,
    MergePatch,
    RevisionInfo,
    RevisionStatus,
)

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


def _patch_flavor(content_type: str | None, body) -> str:
    """Decide which PATCH flavor a request uses.

    Explicit media types win (RFC 6902 ``application/json-patch+json`` vs
    RFC 7386 ``application/merge-patch+json``). For a generic
    ``application/json`` we disambiguate by shape: a JSON *array* is a 6902 op
    list, a JSON *object* is a 7386 merge patch. The two are structurally
    disjoint for object resources, so this is unambiguous.

    Returns ``"merge"`` (RFC 7386) or ``"patch"`` (RFC 6902).
    """
    ct = (content_type or "").lower()
    if "merge-patch+json" in ct:
        return "merge"
    if "json-patch+json" in ct:
        return "patch"
    return "merge" if isinstance(body, dict) else "patch"


def _guard_merge_patch_body(body, content_type, struct_owns_resource_id) -> None:
    """Validate an RFC 7386 merge-patch body before handing it to the manager.

    HTTP-layer concerns only: reject ``resource_id`` in the body, and raise a
    helpful ``422`` when an object looks like a stray RFC 6902 operation the
    caller forgot to wrap in an array. The merge itself is the manager's job
    (``patch`` / ``modify`` with a ``MergePatch``).
    """
    explicit_merge = "merge-patch+json" in (content_type or "").lower()
    if (
        not explicit_merge
        and isinstance(body, dict)
        and "op" in body
        and "path" in body
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "This looks like a single JSON Patch (RFC 6902) operation. "
                "RFC 6902 patches must be a JSON array of operations "
                '(e.g. [{"op": "replace", "path": "/field", "value": ...}]). '
                "For a partial update (RFC 7386 merge patch), send the changed "
                "fields as an object without op/path keys."
            ),
        )
    if not struct_owns_resource_id:
        reject_resource_id_in_body(body)


class PatchRouteTemplate(BaseRouteTemplate):
    """部分更新資源的路由模板"""

    def apply(
        self,
        model_name: str,
        resource_manager: IResourceManager[T],
        router: APIRouter,
    ) -> None:
        _struct_owns_resource_id = struct_declares_resource_id(
            resource_manager.resource_type
        )

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
                - `422`: Validation error (schema/type validation or custom validator)
                - `409`: Conflict - unique constraint violation
                - `400`: Bad request (invalid patch operations, resource not found, permission denied, or other patch failures)
                """
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
            expected_revision_id: str | None = Query(
                None,
                description=(
                    "Optimistic concurrency: assert the resource is currently "
                    "at this revision_id. Mismatch → 412 Precondition Failed."
                ),
            ),
            if_match: str | None = Header(
                None,
                alias="If-Match",
                description=(
                    "Alternative to expected_revision_id (HTTP-standard "
                    "optimistic concurrency)."
                ),
            ),
            content_type: str | None = Header(None, alias="Content-Type"),
        ):
            if mode != "modify" and change_status is not None:
                raise HTTPException(
                    status_code=400,
                    detail="change_status can only be used with mode 'modify'",
                )

            flavor = _patch_flavor(content_type, body)
            try:
                _check_precondition(
                    resource_manager, resource_id, expected_revision_id, if_match
                )
                with resource_manager.using(current_user, current_time):
                    if flavor == "merge":
                        _guard_merge_patch_body(
                            body, content_type, _struct_owns_resource_id
                        )
                        merge = MergePatch(body)
                        if mode == "update":
                            info = resource_manager.patch(resource_id, merge)
                        else:  # mode == "modify"
                            info = resource_manager.modify(
                                resource_id,
                                merge,
                                status=msgspec.UNSET
                                if change_status is None
                                else change_status,
                            )
                    else:  # RFC 6902 JSON Patch
                        from jsonpatch import JsonPatch

                        if not _struct_owns_resource_id:
                            reject_resource_id_in_patch(body)
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
                raise to_http_exception(e)
