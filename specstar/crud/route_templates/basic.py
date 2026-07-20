"""Route template protocol and shared error helpers.

This module hosts the foundation that every route template builds on:

* :class:`IRouteTemplate` — the abstract route template interface.
* :class:`BaseRouteTemplate` — concrete base providing dependency wiring
  and an ``order`` for stable application order.
* :func:`raise_unique_conflict` — converts a
  :class:`UniqueConstraintError` into an HTTP 409 response.

For backward compatibility, this module also re-exports the helpers that
historically lived here:

* :class:`DependencyProvider` from
  :mod:`specstar.crud.route_templates.dependency_provider`.
* Response types and JSON-schema helpers from
  :mod:`specstar.crud.route_templates.responses`.
* Query parameter parsing from
  :mod:`specstar.crud.route_templates.query_inputs`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

import msgspec
from fastapi import APIRouter, HTTPException

from specstar.crud.route_templates.dependency_provider import DependencyProvider
from specstar.crud.route_templates.query_inputs import (
    QueryInputs,
    QueryInputsWithReturns,
    build_query,
    get_partial_fields,
)
from specstar.crud.route_templates.responses import (
    FullResourceResponse,
    JsonListResponse,
    MsgspecResponse,
    RevisionListResponse,
    _sanitize_schema_names,
    jsonschema_to_json_schema_extra,
    jsonschema_to_openapi,
    struct_to_responses_type,
)
from specstar.types import (
    IResourceManager,
    UniqueConstraintError,
)

__all__ = [
    "BaseRouteTemplate",
    "DependencyProvider",
    "FullResourceResponse",
    "IRouteTemplate",
    "JsonListResponse",
    "MsgspecResponse",
    "QueryInputs",
    "QueryInputsWithReturns",
    "RevisionListResponse",
    "_sanitize_schema_names",
    "build_query",
    "get_partial_fields",
    "jsonschema_to_json_schema_extra",
    "jsonschema_to_openapi",
    "raise_unique_conflict",
    "reject_resource_id_in_body",
    "reject_resource_id_in_patch",
    "struct_declares_resource_id",
    "struct_to_responses_type",
]

T = TypeVar("T")

# ``resource_id`` is part of the server-generated meta, never resource data.
# A client that puts it in a create/replace body or a patch op thinks it is
# choosing/changing the id, but the server owns it — so we fail loudly rather
# than silently dropping it. The "server always generates" wording is relied
# on by tests; keep it when editing.
RESOURCE_ID_IN_BODY_DETAIL = (
    "`resource_id` cannot be supplied in the request body — the server "
    "always generates it at creation and it is immutable thereafter. "
    "To customise id generation, pass `id_generator=` when calling "
    "`spec.add_model(...)`."
)


def raise_unique_conflict(e: UniqueConstraintError) -> None:
    """Convert a :class:`UniqueConstraintError` into an HTTP 409 response."""
    raise HTTPException(
        status_code=409,
        detail={
            "message": str(e),
            "field": e.field,
            "conflicting_resource_id": e.conflicting_resource_id,
        },
    )


def struct_declares_resource_id(resource_type) -> bool:
    """Return ``True`` if the resource Struct declares its own ``resource_id``
    field.

    In that (rare) case a body-level ``resource_id`` is legitimate data rather
    than an attempt to set the server-managed identity, so the rejection guards
    below should step aside.
    """
    try:
        return any(
            f.name == "resource_id" for f in msgspec.structs.fields(resource_type)
        )
    except TypeError:
        return False


def reject_resource_id_in_body(body) -> None:
    """Reject a create/replace body that carries ``resource_id`` with HTTP 422.

    Call only when the Struct does not declare a ``resource_id`` field (see
    :func:`struct_declares_resource_id`).
    """
    if isinstance(body, dict) and "resource_id" in body:
        raise HTTPException(status_code=422, detail=RESOURCE_ID_IN_BODY_DETAIL)


def reject_resource_id_in_patch(body) -> None:
    """Reject a JSON Patch body whose operations target ``/resource_id``.

    The patch analogue of :func:`reject_resource_id_in_body`: a client cannot
    rewrite the server-managed identity through a patch op either. Call only
    when the Struct does not declare a ``resource_id`` field.
    """
    if not isinstance(body, list):
        return
    for op in body:
        if isinstance(op, dict) and op.get("path") == "/resource_id":
            raise HTTPException(status_code=422, detail=RESOURCE_ID_IN_BODY_DETAIL)


class IRouteTemplate(ABC):
    """路由模板基類，定義如何為資源生成單一 API 路由"""

    @abstractmethod
    def apply(
        self,
        model_name: str,
        resource_manager: IResourceManager[T],
        router: APIRouter,
    ) -> None:
        """將路由模板應用到指定的資源管理器和路由器

        Args:
            model_name: 模型名稱
            resource_manager: 資源管理器
            router: FastAPI 路由器
        """

    @property
    @abstractmethod
    def order(self) -> int:
        """獲取路由模板的排序權重"""


class BaseRouteTemplate(IRouteTemplate):
    def __init__(
        self,
        dependency_provider: DependencyProvider = None,  # ty:ignore[invalid-parameter-default]
        order: int = 100,
    ):
        """初始化路由模板

        Args:
            dependency_provider: 依賴提供者，如果為 None 則創建預設的
        """
        self.deps = dependency_provider or DependencyProvider()
        self._order = order

    @property
    def order(self) -> int:
        return self._order

    def __lt__(self, other: IRouteTemplate):
        return self.order < other.order

    def __le__(self, other: IRouteTemplate):
        return self.order <= other.order
