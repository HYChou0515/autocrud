"""Descriptor graph builder.

Pure functions that introspect a :class:`specstar.SpecStar` instance's
in-memory state and emit a :class:`specstar.descriptor.types.Descriptor`.

This is the deterministic side of the spec-driven pipeline — no LLM, no I/O.
``SpecStar.dump()`` delegates here.

Phase 1.2 ships a **minimal** builder that covers ``resource``, ``field``, and
``references`` (Refs). Subsequent Phase 1.2 follow-ups extend coverage to:

- ``schema_version`` + ``migrates_to`` edges (from ``Schema`` chains)
- ``route`` + ``route_template`` + ``exposes`` + ``generated_by`` edges
- ``storage_backend`` + ``stored_in`` edges
- ``permission_policy`` + ``action`` + ``role`` + ``gates`` / ``granted_to``

These are deferred so we can land the wiring (``SpecStar.dump()`` → builder →
``Descriptor`` → JSON) before exhaustively encoding every node type. Each
addition is a small extension to :func:`build_descriptor`.

This module is internal to the v0.11 spec-driven layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import msgspec

from specstar.descriptor.types import (
    Descriptor,
    Edge,
    EdgeType,
    Node,
    NodeType,
    Source,
)

if TYPE_CHECKING:
    from specstar.crud.core import SpecStar


def _resource_id(model_name: str) -> str:
    return f"resource:{model_name}"


def _field_id(model_name: str, field_name: str) -> str:
    return f"field:{model_name}.{field_name}"


def _stringify_type(annotation: object) -> str:
    """Render a type annotation for descriptor display.

    Best-effort: prefers ``__name__`` for plain classes, falls back to
    ``repr``. Not stable across Python versions — descriptor consumers should
    treat this as a hint, not a contract.
    """
    if isinstance(annotation, type):
        return annotation.__name__
    return repr(annotation)


def _build_resource_and_fields(
    model_name: str, resource_type: type
) -> tuple[Node, list[Node], list[Edge]]:
    """Build the resource node, its field nodes, and ``has_field`` edges."""
    resource_node = Node(
        id=_resource_id(model_name),
        type=NodeType.resource,
        properties={
            "model_name": model_name,
            "python_name": getattr(resource_type, "__name__", model_name),
        },
        source=Source.declared,
    )

    field_nodes: list[Node] = []
    has_field_edges: list[Edge] = []

    try:
        struct_fields = msgspec.structs.fields(resource_type)
    except TypeError:
        # Not a msgspec.Struct (e.g. dataclass or plain class). Skip field
        # introspection — resource node alone is still a valid graph entry.
        return resource_node, field_nodes, has_field_edges

    for f in struct_fields:
        fid = _field_id(model_name, f.name)
        required = (
            f.default is msgspec.NODEFAULT and f.default_factory is msgspec.NODEFAULT
        )
        field_nodes.append(
            Node(
                id=fid,
                type=NodeType.field,
                properties={
                    "name": f.name,
                    "python_type": _stringify_type(f.type),
                    "required": required,
                },
                source=Source.declared,
            )
        )
        has_field_edges.append(
            Edge(
                type=EdgeType.has_field,
                source_id=resource_node.id,
                target_id=fid,
            )
        )

    return resource_node, field_nodes, has_field_edges


def build_descriptor(spec: "SpecStar") -> Descriptor:
    """Walk a :class:`SpecStar` instance and emit a :class:`Descriptor`.

    Pure, deterministic for a given input state. Does not mutate ``spec``.

    Coverage in this version:

    - ``resource`` nodes for every registered model
    - ``field`` nodes for each msgspec.Struct field (best-effort introspection)
    - ``has_field`` edges
    - ``references`` edges from ``spec.relationships``

    Gaps (intentionally deferred — see module docstring).
    """
    nodes: list[Node] = []
    edges: list[Edge] = []
    seen_resource_ids: set[str] = set()

    for model_name, manager in spec.resource_managers.items():
        resource_type = manager.resource_type
        resource_node, field_nodes, has_field_edges = _build_resource_and_fields(
            model_name, resource_type
        )
        nodes.append(resource_node)
        seen_resource_ids.add(resource_node.id)
        nodes.extend(field_nodes)
        edges.extend(has_field_edges)

    for ref in spec.relationships:
        source_field_id = _field_id(ref.source, ref.source_field)
        target_resource_id = _resource_id(ref.target)
        edges.append(
            Edge(
                type=EdgeType.references,
                source_id=source_field_id,
                target_id=target_resource_id,
                properties={
                    "ref_type": ref.ref_type,
                    "on_delete": ref.on_delete.value,
                    "nullable": ref.nullable,
                    "is_list": ref.is_list,
                },
            )
        )

    return Descriptor(nodes=nodes, edges=edges)
