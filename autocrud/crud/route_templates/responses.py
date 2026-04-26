"""HTTP response types and OpenAPI schema helpers used by route templates.

This module hosts response classes returned from FastAPI handlers, generic
container response shapes (e.g. :class:`FullResourceResponse`), and the
schema-massaging helpers that turn ``msgspec.json.schema_components`` output
into something safe to embed in an OpenAPI document.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

import msgspec
from fastapi import Response

from autocrud.types import (
    ResourceMeta,
    RevisionInfo,
)

T = TypeVar("T")


class JsonListResponse(Response):
    media_type = "application/json"

    def render(self, content: list[bytes]) -> bytes:
        return b"[" + b",".join(content) + b"]"


class MsgspecResponse(Response):
    media_type = "application/json"

    def render(self, content: msgspec.Struct) -> bytes:
        return msgspec.json.encode(content)


def _sanitize_schema_names(
    schemas: list[dict], components: dict[str, dict]
) -> tuple[list[dict], dict[str, dict]]:
    """Replace dots in OpenAPI component schema names and update all ``$ref`` pointers.

    ``msgspec`` may produce schema names containing dots when a generic type
    parameter is a union (e.g. ``FullResourceResponse[A | B]``) because it
    falls back to module-qualified names like ``mymod.A``.  Dots in component
    names are problematic for code generators, so we replace them with ``_``.
    """
    rename_map: dict[str, str] = {}
    for name in list(components):
        if "." in name:
            new_name = name.replace(".", "_")
            while new_name in components and new_name not in rename_map.values():
                new_name += "_"
            rename_map[name] = new_name

    if not rename_map:
        return schemas, components

    ref_prefix = "#/components/schemas/"

    def _rewrite(obj: Any) -> Any:
        """Recursively rewrite ``$ref`` strings inside a JSON-like structure.

        Also handles ``discriminator.mapping`` values which are ``$ref``-style
        component paths (e.g. ``#/components/schemas/__main__.Foo``).
        """
        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for k, v in obj.items():
                if k == "$ref" and isinstance(v, str) and v.startswith(ref_prefix):
                    old_name = v[len(ref_prefix) :]
                    new_name = rename_map.get(old_name, old_name)
                    out[k] = ref_prefix + new_name
                elif k == "mapping" and isinstance(v, dict):
                    out[k] = {
                        mk: (
                            ref_prefix + rename_map[mv[len(ref_prefix) :]]
                            if isinstance(mv, str)
                            and mv.startswith(ref_prefix)
                            and mv[len(ref_prefix) :] in rename_map
                            else mv
                        )
                        for mk, mv in v.items()
                    }
                else:
                    out[k] = _rewrite(v)
            return out
        if isinstance(obj, list):
            return [_rewrite(item) for item in obj]
        return obj

    schemas = [_rewrite(s) for s in schemas]

    new_components: dict[str, dict] = {}
    for old_key, value in components.items():
        new_key = rename_map.get(old_key, old_key)
        new_components[new_key] = _rewrite(value)

    return schemas, new_components


def jsonschema_to_openapi(structs: list[msgspec.Struct | Any]) -> dict:
    schemas, components = msgspec.json.schema_components(
        structs,
        ref_template="#/components/schemas/{name}",
    )
    schemas, components = _sanitize_schema_names(schemas, components)
    return schemas, components


def jsonschema_to_json_schema_extra(struct: msgspec.Struct | Any) -> dict:
    return jsonschema_to_openapi([struct])[0][0]


def struct_to_responses_type(
    struct: type[msgspec.Struct | Any], status_code: int = 200
):
    schema = jsonschema_to_json_schema_extra(struct)
    return {
        status_code: {
            "content": {"application/json": {"schema": schema}},
        },
    }


class RevisionListResponse(msgspec.Struct):
    meta: ResourceMeta
    revisions: list[RevisionInfo]
    # Total revisions matching query (before limit)
    total: int = 0
    # Whether more revisions are available beyond the returned list
    has_more: bool = False


class FullResourceResponse(msgspec.Struct, Generic[T]):
    data: T | msgspec.UnsetType = msgspec.UNSET
    revision_info: RevisionInfo | msgspec.UnsetType = msgspec.UNSET
    meta: ResourceMeta | msgspec.UnsetType = msgspec.UNSET
