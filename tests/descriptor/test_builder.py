"""Integration tests for ``spec.dump_descriptor()`` and the graph builder.

These tests register real models on a real ``SpecStar`` instance and assert
the shape of the resulting :class:`~specstar.descriptor.Descriptor`. They
double as the executable contract for the v0.11 minimal coverage:

- one ``resource`` node per registered model
- one ``field`` node per msgspec.Struct field
- ``has_field`` edges
- ``references`` edges from ``Ref`` annotations
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import msgspec
import pytest

from specstar import SpecStar
from specstar.descriptor import (
    Descriptor,
    EdgeType,
    NodeType,
    Source,
)
from specstar.descriptor.builder import build_descriptor
from specstar.types import OnDelete, Ref

# ---------------------------------------------------------------------------
# Sample models
# ---------------------------------------------------------------------------


class _User(msgspec.Struct):
    name: str
    email: str
    age: int = 0


class _Account(msgspec.Struct):
    owner_id: Annotated[str, Ref("user", on_delete=OnDelete.cascade)]
    balance: int


class _Tag(msgspec.Struct):
    label: str


@pytest.fixture()
def populated_spec() -> SpecStar:
    """Fresh SpecStar with three resources covering field shapes and refs."""
    spec = SpecStar()
    spec.add_model(_User, name="user")
    spec.add_model(_Account, name="account")
    spec.add_model(_Tag, name="tag")
    return spec


# ---------------------------------------------------------------------------
# Resource and field coverage
# ---------------------------------------------------------------------------


class TestResourceAndFieldNodes:
    def test_one_resource_node_per_registered_model(
        self, populated_spec: SpecStar
    ) -> None:
        d = build_descriptor(populated_spec)
        resource_ids = {n.id for n in d.nodes if n.type is NodeType.resource}
        assert resource_ids == {"resource:user", "resource:account", "resource:tag"}

    def test_resource_node_carries_python_name(self, populated_spec: SpecStar) -> None:
        d = build_descriptor(populated_spec)
        user_node = next(n for n in d.nodes if n.id == "resource:user")
        assert user_node.properties["python_name"] == "_User"
        assert user_node.properties["model_name"] == "user"
        assert user_node.source is Source.declared

    def test_field_node_per_msgspec_field(self, populated_spec: SpecStar) -> None:
        d = build_descriptor(populated_spec)
        user_fields = {
            n.properties["name"]
            for n in d.nodes
            if n.type is NodeType.field and n.id.startswith("field:user.")
        }
        assert user_fields == {"name", "email", "age"}

    def test_field_required_flag_reflects_default(
        self, populated_spec: SpecStar
    ) -> None:
        d = build_descriptor(populated_spec)
        by_id = {n.id: n for n in d.nodes if n.type is NodeType.field}
        assert by_id["field:user.name"].properties["required"] is True
        assert by_id["field:user.email"].properties["required"] is True
        assert by_id["field:user.age"].properties["required"] is False

    def test_has_field_edges(self, populated_spec: SpecStar) -> None:
        d = build_descriptor(populated_spec)
        has_field = [e for e in d.edges if e.type is EdgeType.has_field]
        # Three resources × respective field counts; assert the User triplet.
        user_targets = {
            e.target_id for e in has_field if e.source_id == "resource:user"
        }
        assert user_targets == {
            "field:user.name",
            "field:user.email",
            "field:user.age",
        }


# ---------------------------------------------------------------------------
# Refs
# ---------------------------------------------------------------------------


class TestReferenceEdges:
    def test_ref_creates_field_to_resource_edge(self, populated_spec: SpecStar) -> None:
        d = build_descriptor(populated_spec)
        ref_edges = [e for e in d.edges if e.type is EdgeType.references]
        assert len(ref_edges) == 1
        edge = ref_edges[0]
        assert edge.source_id == "field:account.owner_id"
        assert edge.target_id == "resource:user"

    def test_ref_metadata_recorded_on_edge(self, populated_spec: SpecStar) -> None:
        d = build_descriptor(populated_spec)
        edge = next(e for e in d.edges if e.type is EdgeType.references)
        assert edge.properties["ref_type"] == "resource_id"
        assert edge.properties["on_delete"] == "cascade"
        assert edge.properties["nullable"] is False
        assert edge.properties["is_list"] is False


# ---------------------------------------------------------------------------
# SpecStar.dump_descriptor() public entry point
# ---------------------------------------------------------------------------


class TestDumpDescriptorPublicAPI:
    def test_returns_descriptor_when_no_path(self, populated_spec: SpecStar) -> None:
        result = populated_spec.dump_descriptor()
        assert isinstance(result, Descriptor)
        assert any(n.id == "resource:user" for n in result.nodes)

    def test_writes_indented_json_when_path_given(
        self, populated_spec: SpecStar, tmp_path: Path
    ) -> None:
        out = tmp_path / "spec.lock.json"
        result = populated_spec.dump_descriptor(out)
        assert result is None
        assert out.exists()
        text = out.read_text()
        assert "  " in text  # indented
        parsed = json.loads(text)
        assert "nodes" in parsed and "edges" in parsed
        assert any(n["id"] == "resource:user" for n in parsed["nodes"])

    def test_descriptor_does_not_mutate_specstar(
        self, populated_spec: SpecStar
    ) -> None:
        before = list(populated_spec.resource_managers)
        populated_spec.dump_descriptor()
        populated_spec.dump_descriptor()
        after = list(populated_spec.resource_managers)
        assert before == after

    def test_empty_specstar_yields_empty_graph(self) -> None:
        spec = SpecStar()
        d = spec.dump_descriptor()
        assert d is not None
        assert d.nodes == []
        assert d.edges == []

    def test_existing_dump_method_is_untouched(self) -> None:
        # ``SpecStar.dump`` (the legacy resource-archive exporter) must still
        # exist with its original signature. Adding ``dump_descriptor`` must
        # not shadow it.
        from specstar.crud.core import SpecStar as _SS

        assert hasattr(_SS, "dump")
        assert hasattr(_SS, "dump_descriptor")
        assert _SS.dump is not _SS.dump_descriptor
