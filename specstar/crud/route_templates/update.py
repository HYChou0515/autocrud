import datetime as dt
import textwrap
from typing import Literal, TypeVar

import msgspec
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.params import Body

from specstar.crud.route_templates.basic import (
    BaseRouteTemplate,
    MsgspecResponse,
    jsonschema_to_json_schema_extra,
    reject_resource_id_in_body,
    struct_declares_resource_id,
    struct_to_responses_type,
)
from specstar.crud.route_templates.exception_handlers import to_http_exception
from specstar.types import (
    IResourceManager,
    PreconditionFailedError,
    RevisionInfo,
    RevisionStatus,
)

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
        _struct_owns_resource_id = struct_declares_resource_id(resource_type)

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
        ):
            if mode != "modify" and change_status is not None:
                raise HTTPException(
                    status_code=400,
                    detail="change_status can only be used with mode 'modify'",
                )
            if not _struct_owns_resource_id:
                reject_resource_id_in_body(body)
            try:
                _check_precondition(resource_manager, resource_id, expected_revision_id, if_match)
                # Pass the raw body through so the manager's ``_coerce_data``
                # decorator can apply ``forbid_unknown_fields`` checks before
                # ``msgspec.convert`` drops unknown keys.
                data = msgspec.UNSET if body is None else body
                if mode == "update":
                    with resource_manager.using(current_user, current_time):
                        info = resource_manager.update(resource_id, data)  # ty:ignore[invalid-argument-type]
                else:  # mode == "modify"
                    with resource_manager.using(current_user, current_time):
                        info = resource_manager.modify(
                            resource_id,
                            data,
                            status=msgspec.UNSET
                            if change_status is None
                            else change_status,
                        )
                return MsgspecResponse(info)
            except Exception as e:
                raise to_http_exception(e)


def _check_precondition(
    resource_manager,
    resource_id: str,
    expected_revision_id: str | None,
    if_match: str | None,
) -> None:
    """Enforce ``If-Match`` / ``expected_revision_id`` optimistic-concurrency
    precondition before allowing a write.

    Both forms are accepted; if both are present they must agree. ``If-Match``
    may arrive with surrounding double quotes (HTTP standard ETag syntax).
    """
    expected = expected_revision_id
    if if_match is not None:
        cleaned = if_match.strip().strip('"')
        if expected is None:
            expected = cleaned
        elif cleaned != expected:
            raise HTTPException(
                status_code=400,
                detail=(
                    "If-Match header and expected_revision_id query param "
                    "disagree; provide one or matching values."
                ),
            )
    if expected is None:
        return
    meta = resource_manager.get_meta(resource_id)
    actual = meta.current_revision_id
    if actual != expected:
        raise PreconditionFailedError(resource_id, expected, actual)
