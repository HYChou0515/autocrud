"""HTTP response types and OpenAPI schema helpers used by route templates.

This module hosts response classes returned from FastAPI handlers, generic
container response shapes (e.g. :class:`FullResourceResponse`), and the
schema-massaging helpers that turn ``msgspec.json.schema_components`` output
into something safe to embed in an OpenAPI document.
"""

from __future__ import annotations

import hashlib
from typing import Any, Generic, TypeVar

import msgspec
from fastapi import Response

from specstar.types import (
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


# PyYAML refuses a "simple key" longer than 1024 characters, and an OpenAPI
# component name is exactly that — a mapping key.  Cross the line and the whole
# document stops parsing for every consumer that routes through PyYAML, which
# includes ``datamodel-code-generator`` for any input whose file name does not
# end in ``.json``.  Budget below the cliff rather than on it.
_MAX_SCHEMA_NAME_LENGTH = 960

# A name that has to be replaced should come back readable, not merely legal —
# it becomes a class name in every generated client.
_SHORTENED_NAME_HEAD = 96


def _shorten_schema_name(name: str) -> str:
    """Return a short, deterministic stand-in for an over-long component name.

    The digest is taken over the *whole* original name so two names sharing a
    prefix stay distinct where plain truncation would merge them, and so the
    result is stable across runs — a regenerated client must not churn just
    because it was generated twice.
    """
    digest = hashlib.sha256(name.encode()).hexdigest()[:8]
    return f"{name[:_SHORTENED_NAME_HEAD].rstrip('_')}_{digest}"


def _sanitize_schema_names(
    schemas: list[dict], components: dict[str, dict]
) -> tuple[list[dict], dict[str, dict]]:
    """Normalise OpenAPI component schema names and update all ``$ref`` pointers.

    Two problems, both created by ``msgspec`` naming a generic whose parameter
    is a union (e.g. ``FullResourceResponse[A | B]``): it falls back to
    module-qualified member names like ``mymod.A``, so the name both contains
    dots *and* grows with the number of members times the length of their
    module path.

    * Dots are replaced with ``_`` — code generators choke on them.
    * Names past :data:`_MAX_SCHEMA_NAME_LENGTH` are replaced with a short
      deterministic name, because past 1024 characters PyYAML cannot read the
      document at all.

    Names already within budget are left exactly as they are: renaming one
    would break the generated client code that imports it by name.
    """
    rename_map: dict[str, str] = {}
    for name in list(components):
        new_name = name.replace(".", "_")
        if len(new_name) > _MAX_SCHEMA_NAME_LENGTH:
            new_name = _shorten_schema_name(new_name)
        if new_name != name:
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
    schemas, components = _sanitize_schema_names(schemas, components)  # ty:ignore[invalid-argument-type]
    return schemas, components  # ty:ignore[invalid-return-type]


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
