"""Smoke tests for the descriptor data model.

These tests anchor the public shape of :mod:`specstar.descriptor.types`. They
cover construction, JSON round-trip via ``msgspec.json``, and basic invariants
required by ``spec.dump()`` and ``specstar verify`` in later phases.
"""

from __future__ import annotations

from msgspec.json import decode, encode

from specstar.descriptor import (
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


class TestNodeAndEdge:
    """Construction and field defaults for :class:`Node` and :class:`Edge`."""

    def test_node_minimal_construction(self) -> None:
        node = Node(id="resource:User", type=NodeType.resource)
        assert node.id == "resource:User"
        assert node.type is NodeType.resource
        assert node.properties == {}
        assert node.source is Source.declared
        assert node.stable_id is None

    def test_node_with_properties_and_source(self) -> None:
        node = Node(
            id="field:User.email",
            type=NodeType.field,
            properties={"python_type": "str", "format": "email"},
            source=Source.declared,
        )
        assert node.properties["python_type"] == "str"
        assert node.source is Source.declared

    def test_edge_minimal_construction(self) -> None:
        edge = Edge(
            type=EdgeType.has_field,
            source_id="resource:User",
            target_id="field:User.email",
        )
        assert edge.type is EdgeType.has_field
        assert edge.source_id == "resource:User"
        assert edge.target_id == "field:User.email"

    def test_default_dict_is_per_instance(self) -> None:
        # Guard against the classic mutable-default-shared-across-instances
        # bug. msgspec handles this safely but we assert it explicitly so a
        # future refactor doesn't regress.
        a = Node(id="resource:A", type=NodeType.resource)
        b = Node(id="resource:B", type=NodeType.resource)
        assert a.properties is not b.properties


class TestEnums:
    """Every documented node/edge type is represented in the StrEnum."""

    def test_node_type_coverage(self) -> None:
        # Mirrors design doc §3.3.
        expected = {
            "resource",
            "field",
            "schema_version",
            "route",
            "route_template",
            "storage_backend",
            "permission_policy",
            "action",
            "role",
        }
        actual = {nt.value for nt in NodeType}
        assert actual == expected

    def test_edge_type_coverage(self) -> None:
        expected = {
            "has_field",
            "references",
            "migrates_to",
            "validated_by",
            "exposes",
            "generated_by",
            "performs",
            "stored_in",
            "gates",
            "granted_to",
            "requires",
        }
        actual = {et.value for et in EdgeType}
        assert actual == expected

    def test_source_levels(self) -> None:
        expected = {"declared", "expr_tree", "ref", "scaffolded", "generated"}
        actual = {s.value for s in Source}
        assert actual == expected


class TestJSONRoundTrip:
    """Manifest must be JSON-serializable with shape preserved."""

    def _sample_manifest(self) -> Manifest:
        descriptor = Descriptor(
            nodes=[
                Node(id="resource:User", type=NodeType.resource),
                Node(
                    id="field:User.email",
                    type=NodeType.field,
                    properties={"python_type": "str"},
                ),
            ],
            edges=[
                Edge(
                    type=EdgeType.has_field,
                    source_id="resource:User",
                    target_id="field:User.email",
                )
            ],
        )
        return Manifest(
            specstar_version="0.11.0",
            skill_version="0.11.0",
            descriptor_version=DESCRIPTOR_VERSION,
            sources={
                "spec.md": SourceFile(sha256="a" * 64, size=1234),
                "my_app/_generated.py": SourceFile(sha256="b" * 64, size=5678),
            },
            descriptor=descriptor,
            validation=ValidationStatus(ast_check="passed"),
        )

    def test_round_trip_preserves_structure(self) -> None:
        original = self._sample_manifest()
        blob = encode(original)
        restored = decode(blob, type=Manifest)
        assert restored == original

    def test_descriptor_version_is_serialized(self) -> None:
        manifest = self._sample_manifest()
        blob = encode(manifest)
        # Cheap sanity: the version number must appear in the JSON output.
        assert b'"descriptor_version":1' in blob

    def test_validation_status_default(self) -> None:
        status = ValidationStatus()
        assert status.ast_check == "skipped"
        assert status.errors == []
