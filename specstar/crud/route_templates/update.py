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
            if_none_match: str | None = Header(
                None,
                alias="If-None-Match",
                description=(
                    "Atomic create-only at a known URL. ``If-None-Match: *`` "
                    "asserts the resource does NOT yet exist; the request "
                    "creates it, else 412 Precondition Failed."
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
                if if_none_match is not None and if_none_match.strip() == "*":
                    # HTTP-standard PUT-create-only at a known URL.
                    data = msgspec.UNSET if body is None else body
                    try:
                        with resource_manager.using(current_user, current_time):
                            info = resource_manager.create(  # ty:ignore[invalid-argument-type]
                                data,
                                resource_id=resource_id,
                                if_not_exists=True,
                            )
                    except Exception as exc:
                        from specstar.types import DuplicateResourceError as _DRE
                        from specstar.types import PreconditionFailedError as _PFE

                        if isinstance(exc, _DRE):
                            # RFC 7232: If-None-Match precondition failure
                            # MUST be 412 (not 409 Conflict).
                            raise _PFE(
                                resource_id=resource_id,
                                expected_revision_id="*",
                                actual_revision_id="exists",
                            ) from exc
                        raise
                    return MsgspecResponse(info, headers={"ETag": f'"{info.etag}"'})
                expected_etag, expected_rev_id = _resolve_precondition(
                    expected_revision_id, if_match
                )
                # Pass the raw body through so the manager's ``_coerce_data``
                # decorator can apply ``forbid_unknown_fields`` checks before
                # ``msgspec.convert`` drops unknown keys.
                data = msgspec.UNSET if body is None else body
                if mode == "update":
                    with resource_manager.using(
                        current_user, current_time, apply_access_scope=True
                    ):
                        info = resource_manager.update(  # ty:ignore[invalid-argument-type]
                            resource_id,
                            data,
                            expected_revision_id=expected_rev_id,
                            expected_etag=expected_etag,
                        )
                else:  # mode == "modify"
                    with resource_manager.using(
                        current_user, current_time, apply_access_scope=True
                    ):
                        info = resource_manager.modify(
                            resource_id,
                            data,
                            status=msgspec.UNSET
                            if change_status is None
                            else change_status,
                            expected_revision_id=expected_rev_id,
                            expected_etag=expected_etag,
                        )
                return MsgspecResponse(info, headers={"ETag": f'"{info.etag}"'})
            except Exception as e:
                raise to_http_exception(e)


def _resolve_precondition(
    expected_revision_id: str | None,
    if_match: str | None,
) -> tuple[str | msgspec.UnsetType, str | msgspec.UnsetType]:
    """Resolve the ``If-Match`` header / ``expected_revision_id`` query into
    manager kwargs.

    Returns ``(expected_etag, expected_revision_id)`` — at most one is set
    (the other is ``msgspec.UNSET``). ``If-Match`` may carry a bare
    ``revision_id`` (legacy) or an ``etag`` (``<rev>@<hash>``); we detect the
    etag form by the ``@`` separator. Surrounding double quotes are stripped
    (HTTP-standard ETag syntax).

    If both ``expected_revision_id`` (query) and ``If-Match`` (header) are
    sent and disagree, the request is rejected with 400. The actual CAS check
    happens in the manager, which raises ``PreconditionFailedError`` (→ 412)
    on mismatch.
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
        return msgspec.UNSET, msgspec.UNSET
    if "@" in expected:
        return expected, msgspec.UNSET
    return msgspec.UNSET, expected
