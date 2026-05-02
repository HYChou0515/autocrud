"""Typed nodes, edges, and manifest for the SpecStar descriptor.

The descriptor is a property graph: typed nodes connected by typed edges. It is
the canonical structured AST sitting between ``spec.md`` (prose) and
``_generated.py`` (executable Python), serving three audiences simultaneously:

1. visualization tools and human reviewers
2. future LLM sessions that need to reason about the registered model
3. ``specstar verify`` deterministic CI checks

See ``docs/design/spec-driven-architecture.md`` §3.3 for the design rationale,
node/edge type rationale, and identity rules.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from msgspec import Struct

DESCRIPTOR_VERSION: int = 1
"""Version of the descriptor schema.

Bump on backward-incompatible changes. ``specstar verify`` refuses to operate
across mismatched versions and prompts the user to regenerate.
"""


class NodeType(StrEnum):
    """Typed nodes in the property graph.

    See design doc §3.3 for the full list rationale. Each node represents a
    SpecStar-level concept; HTTP-level details (e.g. headers, MIME types) are
    deliberately *not* nodes — they live in the OpenAPI document referenced by
    ``route`` nodes.
    """

    resource = "resource"
    field = "field"
    schema_version = "schema_version"
    route = "route"
    route_template = "route_template"
    storage_backend = "storage_backend"
    permission_policy = "permission_policy"
    action = "action"
    role = "role"


class EdgeType(StrEnum):
    """Typed directed edges in the property graph.

    See design doc §3.3 for the rationale of each edge type.
    """

    has_field = "has_field"
    """resource -> field"""

    references = "references"
    """field -> resource (Ref / RefRevision)"""

    migrates_to = "migrates_to"
    """schema_version -> schema_version"""

    validated_by = "validated_by"
    """schema_version -> validator (validator may itself be a node in v1.x)"""

    exposes = "exposes"
    """resource -> route"""

    generated_by = "generated_by"
    """route -> route_template"""

    performs = "performs"
    """route -> action"""

    stored_in = "stored_in"
    """resource -> storage_backend"""

    gates = "gates"
    """permission_policy -> action (with optional scope=resource/field)"""

    granted_to = "granted_to"
    """permission_policy -> role"""

    requires = "requires"
    """field -> constraint (e.g. unique, not-null)"""


class Source(StrEnum):
    """Provenance label for nodes/edges, used by viz tools to colour-code trust.

    See design doc §3.2 for how each source level maps to audit cost.
    """

    declared = "declared"
    """Pure declaration (field type, storage binding). AST-trivial; zero trust cost."""

    expr_tree = "expr_tree"
    """Operator-overloaded expression tree (permission expr, QB filter).

    The lambda body, if any, was AST-validated to be pure. Low trust cost.
    """

    ref = "ref"
    """String reference to user-written Python (e.g. ``my_app.logic.fn``).

    Framework does not inspect contents. Trust budget falls on the user's own
    test suite for the referenced module.
    """

    scaffolded = "scaffolded"
    """Skill emitted a (β) scaffold awaiting user implementation.

    Should not appear in production-ready ``spec.lock.json``. CI may flag it.
    """

    generated = "generated"
    """Pure-function Python written by the skill, AST-validated.

    Common case: migration row-transform functions. The function source is
    attached to the node/edge as a ``code`` property for inline audit.
    """


class Node(Struct, frozen=True):
    """A typed node in the property graph.

    Attributes:
        id: Path-based identity (e.g. ``resource:User``, ``field:User.email``).
            Stable across regenerations as long as the underlying name path is
            unchanged.
        type: One of :class:`NodeType`.
        properties: Free-form metadata. Conventional keys per node type live in
            the descriptor schema doc (e.g. ``code`` for ``generated`` nodes,
            ``python_type`` for ``field`` nodes).
        source: Provenance label; viz tools render this for trust signalling.
        stable_id: Optional rename-safe handle. Set to a UUID-like string and
            preserved across renames so that diffs detect renames as such
            instead of "delete + add".
    """

    id: str
    type: NodeType
    properties: dict[str, Any] = {}
    source: Source = Source.declared
    stable_id: str | None = None


class Edge(Struct, frozen=True):
    """A typed directed edge between two nodes.

    Attributes:
        type: One of :class:`EdgeType`.
        source_id: Origin node id.
        target_id: Destination node id.
        properties: Free-form edge metadata (e.g. ``scope`` on ``gates``,
            ``code`` on ``migrates_to`` for generated migration bodies).
    """

    type: EdgeType
    source_id: str
    target_id: str
    properties: dict[str, Any] = {}


class Descriptor(Struct, frozen=True):
    """The property graph itself: a flat list of nodes and edges."""

    nodes: list[Node]
    edges: list[Edge]


class SourceFile(Struct, frozen=True):
    """Hash-tracked source file entry in the manifest.

    ``sha256`` is computed after content normalization (LF line endings, trim
    trailing whitespace for Markdown; ``ruff format`` for Python). See design
    doc §3.6.
    """

    sha256: str
    size: int
    regenerated_at: str | None = None


class ValidationStatus(Struct, frozen=True):
    """AST validator outcome attached to the manifest.

    ``ast_check`` values: ``"passed"``, ``"failed"``, ``"skipped"``.
    """

    ast_check: str = "skipped"
    errors: list[dict[str, Any]] = []


class Manifest(Struct, frozen=True):
    """Top-level structure of ``spec.lock.json``.

    ``sources`` keys are project-relative file paths. Conventional entries:
    ``"spec.md"`` and ``"<package>/_generated.py"`` (path varies by project).
    """

    specstar_version: str
    skill_version: str
    descriptor_version: int
    sources: dict[str, SourceFile]
    descriptor: Descriptor
    validation: ValidationStatus
