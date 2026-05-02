"""Descriptor data model for the spec-driven property graph.

The descriptor is the machine-readable artifact produced by ``spec.dump()`` and
written to ``spec.lock.json``. See ``docs/design/spec-driven-architecture.md``
for design rationale.

This module is internal to the v0.11 spec-driven layer and is **not** part of
the public ``specstar`` API. Public API surface is finalized once the
descriptor format stabilizes.
"""

from __future__ import annotations

from specstar.descriptor.types import (
    DESCRIPTOR_VERSION,
    Descriptor,
    Edge,
    EdgeType,
    Manifest,
    Node,
    NodeType,
    Source,
    SourceFile,
    ValidationStatus,
)

__all__ = [
    "DESCRIPTOR_VERSION",
    "Descriptor",
    "Edge",
    "EdgeType",
    "Manifest",
    "Node",
    "NodeType",
    "Source",
    "SourceFile",
    "ValidationStatus",
]
