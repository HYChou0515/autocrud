"""Descriptor graph builder.

Pure functions that introspect a :class:`specstar.SpecStar` instance's
in-memory state and emit a :class:`specstar.descriptor.types.Descriptor`.

This is the deterministic side of the spec-driven pipeline — no LLM, no I/O.
``SpecStar.dump_descriptor()`` delegates here.

Coverage as of Phase 1.2 + 1.2 extension:

- ``resource`` + ``field`` nodes from registered models
- ``has_field`` edges
- ``references`` edges from ``Ref`` annotations
- ``route_template`` nodes for each entry in ``spec.route_templates``
- ``route`` nodes for each (resource × template) pair, with ``exposes``
  and ``generated_by`` edges
- ``storage_backend`` node for the global ``storage_factory`` plus
  ``stored_in`` edges from every resource
- ``permission_policy`` node for the global ``permission_checker`` plus
  ``gates`` edges from every resource

Still deferred:

- ``schema_version`` + ``migrates_to`` edges (from ``Schema`` chains)
- ``action`` / ``role`` nodes
- per-resource overrides for storage / permission (currently only the
  global default is captured)

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


def _route_template_short(template: object) -> str:
    """Strip the ``RouteTemplate`` suffix off a template class name.

    ``CreateRouteTemplate`` → ``"create"``, ``BatchDeleteRouteTemplate`` →
    ``"batchdelete"``. Lowercased so it composes cleanly into IDs.
    """
    cls = type(template) if not isinstance(template, type) else template
    name = cls.__name__
    if name.endswith("RouteTemplate"):
        name = name[: -len("RouteTemplate")]
    return name.lower()


def _route_template_id(short: str) -> str:
    return f"route_template:{short}"


def _route_id(model_name: str, short: str) -> str:
    return f"route:{model_name}.{short}"


_STORAGE_BACKEND_ID = "storage_backend:default"
_PERMISSION_POLICY_ID = "permission_policy:global"


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


def _build_route_nodes(
    spec: "SpecStar", model_names: list[str]
) -> tuple[list[Node], list[Edge]]:
    """Build ``route_template`` nodes plus per-resource ``route`` nodes."""
    nodes: list[Node] = []
    edges: list[Edge] = []

    templates = list(spec.route_templates)
    if not templates:
        return nodes, edges

    template_shorts: list[str] = []
    for tmpl in templates:
        short = _route_template_short(tmpl)
        cls = type(tmpl) if not isinstance(tmpl, type) else tmpl
        nodes.append(
            Node(
                id=_route_template_id(short),
                type=NodeType.route_template,
                properties={
                    "name": cls.__name__,
                    "short_name": short,
                },
                source=Source.declared,
            )
        )
        template_shorts.append(short)

    for model_name in model_names:
        for short in template_shorts:
            route = _route_id(model_name, short)
            nodes.append(
                Node(
                    id=route,
                    type=NodeType.route,
                    properties={
                        "resource": model_name,
                        "template": short,
                    },
                    source=Source.declared,
                )
            )
            edges.append(
                Edge(
                    type=EdgeType.exposes,
                    source_id=_resource_id(model_name),
                    target_id=route,
                )
            )
            edges.append(
                Edge(
                    type=EdgeType.generated_by,
                    source_id=route,
                    target_id=_route_template_id(short),
                )
            )

    return nodes, edges


def _build_storage_node(
    spec: "SpecStar", model_names: list[str]
) -> tuple[Node, list[Edge]]:
    """One ``storage_backend`` node + ``stored_in`` edges from each resource."""
    factory = spec.storage_factory
    node = Node(
        id=_STORAGE_BACKEND_ID,
        type=NodeType.storage_backend,
        properties={
            "factory": type(factory).__name__,
            "factory_module": type(factory).__module__,
        },
        source=Source.declared,
    )
    edges = [
        Edge(
            type=EdgeType.stored_in,
            source_id=_resource_id(model_name),
            target_id=node.id,
        )
        for model_name in model_names
    ]
    return node, edges


def _build_permission_node(
    spec: "SpecStar", model_names: list[str]
) -> tuple[Node, list[Edge]]:
    """One global ``permission_policy`` node + ``gates`` edges per resource.

    v0.11 minimal: only the project-wide ``permission_checker`` is captured.
    Per-resource permission overrides will land alongside ``action`` /
    ``role`` nodes in a follow-up.
    """
    checker = spec.permission_checker
    node = Node(
        id=_PERMISSION_POLICY_ID,
        type=NodeType.permission_policy,
        properties={
            "checker": type(checker).__name__,
            "checker_module": type(checker).__module__,
        },
        source=Source.declared,
    )
    edges = [
        Edge(
            type=EdgeType.gates,
            source_id=node.id,
            target_id=_resource_id(model_name),
        )
        for model_name in model_names
    ]
    return node, edges


def build_descriptor(spec: "SpecStar") -> Descriptor:
    """Walk a :class:`SpecStar` instance and emit a :class:`Descriptor`.

    Pure, deterministic for a given input state. Does not mutate ``spec``.

    Coverage in this version: see the module docstring.
    """
    nodes: list[Node] = []
    edges: list[Edge] = []

    model_names = list(spec.resource_managers)

    for model_name, manager in spec.resource_managers.items():
        resource_type = manager.resource_type
        resource_node, field_nodes, has_field_edges = _build_resource_and_fields(
            model_name, resource_type
        )
        nodes.append(resource_node)
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

    if model_names:
        route_nodes, route_edges = _build_route_nodes(spec, model_names)
        nodes.extend(route_nodes)
        edges.extend(route_edges)

        storage_node, storage_edges = _build_storage_node(spec, model_names)
        nodes.append(storage_node)
        edges.extend(storage_edges)

        permission_node, permission_edges = _build_permission_node(spec, model_names)
        nodes.append(permission_node)
        edges.extend(permission_edges)

    return Descriptor(nodes=nodes, edges=edges)
