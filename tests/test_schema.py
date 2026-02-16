"""Unit tests for ``autocrud.schema.Schema``."""

from __future__ import annotations

import io
from typing import IO, Any

import msgspec
import pytest
from msgspec import Struct

from autocrud.schema import Schema
from autocrud.types import IMigration, IValidator, ValidationError

# =====================================================================
# Test data models
# =====================================================================


class V1Data(Struct):
    name: str
    value: int


class V2Data(Struct):
    name: str
    value: int
    tag: str


class V3Data(Struct):
    name: str
    value: int
    tag: str
    score: float


# =====================================================================
# Helper migration functions
# =====================================================================


def migrate_v1_to_v2(data: IO[bytes]) -> V2Data:
    """v1 → v2: add ``tag`` field."""
    obj = msgspec.json.decode(data.read(), type=V1Data)
    return V2Data(name=obj.name, value=obj.value, tag="migrated")


def migrate_v2_to_v3(data: IO[bytes]) -> V3Data:
    """v2 → v3: add ``score`` field."""
    obj = msgspec.json.decode(data.read(), type=V2Data)
    return V3Data(name=obj.name, value=obj.value, tag=obj.tag, score=0.0)


def migrate_v1_to_v3_direct(data: IO[bytes]) -> V3Data:
    """v1 → v3 shortcut."""
    obj = msgspec.json.decode(data.read(), type=V1Data)
    return V3Data(name=obj.name, value=obj.value, tag="direct", score=99.0)


# =====================================================================
# Tests: Construction & properties
# =====================================================================


class TestSchemaConstruction:
    def test_basic_creation(self):
        s = Schema("v2")
        assert s.version == "v2"
        assert s.schema_version == "v2"  # IMigration compat
        assert not s.has_migration
        assert not s.has_validator

    def test_none_version(self):
        s = Schema()
        assert s.version is None
        assert s.schema_version is None

    def test_with_validator_callable(self):
        def my_val(data):
            pass

        s = Schema("v1", validator=my_val)
        assert s.has_validator
        assert s.raw_validator is my_val

    def test_with_validator_ivalidator(self):
        class MyVal(IValidator):
            def validate(self, data: Any) -> None:
                if getattr(data, "value", 0) < 0:
                    raise ValueError("negative")

        val = MyVal()
        s = Schema("v1", validator=val)
        assert s.has_validator
        assert s.raw_validator is val

    def test_repr_basic(self):
        s = Schema("v2")
        assert repr(s) == "Schema('v2')"

    def test_repr_with_steps(self):
        s = Schema("v3").step("v1", migrate_v1_to_v2).step("v2", migrate_v2_to_v3)
        r = repr(s)
        assert ".step('v1', ...)" in r
        assert ".step('v2', ...)" in r

    def test_repr_with_plus(self):
        s = (
            Schema("v3")
            .step("v1", migrate_v1_to_v2)
            .step("v2", migrate_v2_to_v3)
            .plus("v1", migrate_v1_to_v3_direct)
        )
        r = repr(s)
        assert ".plus('v1', ...)" in r

    def test_repr_with_validator(self):
        s = Schema("v2", validator=lambda d: None)
        assert "validator=..." in repr(s)


# =====================================================================
# Tests: Step chain inference
# =====================================================================


class TestStepChainInference:
    """Test auto-inference of ``to`` in step chains."""

    def test_single_step_infers_to_target(self):
        """Last step in chain → Schema target version."""
        s = Schema("v2").step("v1", migrate_v1_to_v2)
        graph = s._resolve()
        assert "v1" in graph
        edges = graph["v1"]
        assert len(edges) == 1
        assert edges[0][0] == "v2"  # to_ver

    def test_two_step_chain_infers_middle(self):
        """Middle step's ``to`` = next step's ``from``."""
        s = Schema("v3").step("v1", migrate_v1_to_v2).step("v2", migrate_v2_to_v3)
        graph = s._resolve()
        # v1 → v2 (inferred from next step)
        assert graph["v1"][0][0] == "v2"
        # v2 → v3 (inferred from target)
        assert graph["v2"][0][0] == "v3"

    def test_explicit_to_overrides(self):
        """Explicit ``to=`` overrides auto inference."""
        s = (
            Schema("v3")
            .step("v1", migrate_v1_to_v2, to="v2")
            .step("v2", migrate_v2_to_v3)
        )
        graph = s._resolve()
        assert graph["v1"][0][0] == "v2"
        assert graph["v2"][0][0] == "v3"

    def test_no_version_no_to_raises(self):
        """If Schema has no version and step has no explicit ``to``, raise."""
        s = Schema().step("v1", migrate_v1_to_v2)
        with pytest.raises(ValueError, match="Cannot infer target version"):
            s._resolve()

    def test_explicit_to_on_last_step_overrides_target(self):
        """Explicit ``to=`` on last step can differ from Schema.version."""
        s = Schema("v4").step("v1", migrate_v1_to_v2, to="v2")
        graph = s._resolve()
        assert graph["v1"][0][0] == "v2"


# =====================================================================
# Tests: plus() parallel chains
# =====================================================================


class TestPlusParallelChains:
    def test_plus_creates_new_chain(self):
        s = (
            Schema("v3")
            .step("v1", migrate_v1_to_v2)
            .step("v2", migrate_v2_to_v3)
            .plus("v1", migrate_v1_to_v3_direct)
        )
        graph = s._resolve()
        # v1 should have two edges: → v2 (chain 0) and → v3 (chain 1)
        assert len(graph["v1"]) == 2
        to_versions = {edge[0] for edge in graph["v1"]}
        assert to_versions == {"v2", "v3"}
        # v2 → v3
        assert graph["v2"][0][0] == "v3"

    def test_plus_chain_inference_independent(self):
        """Each chain resolves ``to`` independently."""
        # Chain 0: v1 → v2, v2 → v3
        # Chain 1: v1 → v3 (last step, target)
        s = (
            Schema("v3")
            .step("v1", migrate_v1_to_v2)
            .step("v2", migrate_v2_to_v3)
            .plus("v1", migrate_v1_to_v3_direct)
        )
        graph = s._resolve()
        # All inferences should be correct
        assert graph["v2"][0][0] == "v3"

    def test_equivalence_ordering(self):
        """Equivalent definitions produce same graph regardless of order."""
        fn1, fn2, fn3 = migrate_v1_to_v2, migrate_v2_to_v3, migrate_v1_to_v3_direct

        s1 = Schema("v3").step("v1", fn1).step("v2", fn2).plus("v1", fn3)
        s2 = Schema("v3").step("v1", fn3).plus("v1", fn1).step("v2", fn2)

        g1, g2 = s1._resolve(), s2._resolve()
        # Both should have v1 → {v2, v3} and v2 → {v3}
        assert sorted(t for t, _ in g1["v1"]) == sorted(t for t, _ in g2["v1"])
        assert g1["v2"][0][0] == g2["v2"][0][0] == "v3"

    def test_plus_explicit_to(self):
        s = (
            Schema("v3")
            .step("v1", migrate_v1_to_v2)
            .step("v2", migrate_v2_to_v3)
            .plus("v1", migrate_v1_to_v3_direct, to="v3")
        )
        graph = s._resolve()
        to_v3_edges = [fn for to, fn in graph["v1"] if to == "v3"]
        assert len(to_v3_edges) == 1


# =====================================================================
# Tests: BFS path finding
# =====================================================================


class TestPathFinding:
    def test_single_step_path(self):
        s = Schema("v2").step("v1", migrate_v1_to_v2)
        path = s._find_path("v1", "v2")
        assert len(path) == 1
        assert path[0][0] == "v1"
        assert path[0][1] == "v2"

    def test_two_step_path(self):
        s = Schema("v3").step("v1", migrate_v1_to_v2).step("v2", migrate_v2_to_v3)
        path = s._find_path("v1", "v3")
        assert len(path) == 2
        assert path[0][:2] == ("v1", "v2")
        assert path[1][:2] == ("v2", "v3")

    def test_shortcut_preferred(self):
        """BFS should find shortest path (1 step) over longer path (2 steps)."""
        s = (
            Schema("v3")
            .step("v1", migrate_v1_to_v2)
            .step("v2", migrate_v2_to_v3)
            .plus("v1", migrate_v1_to_v3_direct)
        )
        path = s._find_path("v1", "v3")
        # Should pick the shortcut (1 step) over chain (2 steps)
        assert len(path) == 1
        assert path[0][:2] == ("v1", "v3")

    def test_same_version_empty_path(self):
        s = Schema("v2").step("v1", migrate_v1_to_v2)
        path = s._find_path("v2", "v2")
        assert path == []

    def test_no_path_raises(self):
        s = Schema("v3").step("v1", migrate_v1_to_v2)
        with pytest.raises(ValueError, match="No migration path"):
            s._find_path("v2", "v3")

    def test_unknown_source_raises(self):
        s = Schema("v2").step("v1", migrate_v1_to_v2)
        with pytest.raises(ValueError, match="No migration path"):
            s._find_path("v999", "v2")


# =====================================================================
# Tests: migrate() execution
# =====================================================================


class TestMigrateExecution:
    def _make_stream(self, obj: Any) -> io.BytesIO:
        return io.BytesIO(msgspec.json.encode(obj))

    def test_single_step_migration(self):
        s = Schema("v2").step("v1", migrate_v1_to_v2)
        data = self._make_stream(V1Data(name="alice", value=42))
        result = s.migrate(data, "v1")
        assert isinstance(result, V2Data)
        assert result.name == "alice"
        assert result.value == 42
        assert result.tag == "migrated"

    def test_chain_migration(self):
        s = Schema("v3").step("v1", migrate_v1_to_v2).step("v2", migrate_v2_to_v3)
        data = self._make_stream(V1Data(name="bob", value=10))
        result = s.migrate(data, "v1")
        assert isinstance(result, V3Data)
        assert result.name == "bob"
        assert result.tag == "migrated"
        assert result.score == 0.0

    def test_shortcut_migration(self):
        s = (
            Schema("v3")
            .step("v1", migrate_v1_to_v2)
            .step("v2", migrate_v2_to_v3)
            .plus("v1", migrate_v1_to_v3_direct)
        )
        data = self._make_stream(V1Data(name="carol", value=5))
        result = s.migrate(data, "v1")
        # Should use shortcut
        assert isinstance(result, V3Data)
        assert result.tag == "direct"
        assert result.score == 99.0

    def test_migrate_from_middle(self):
        """Migrate from v2 (intermediate) to v3."""
        s = Schema("v3").step("v1", migrate_v1_to_v2).step("v2", migrate_v2_to_v3)
        data = self._make_stream(V2Data(name="dave", value=7, tag="existing"))
        result = s.migrate(data, "v2")
        assert isinstance(result, V3Data)
        assert result.tag == "existing"
        assert result.score == 0.0

    def test_migrate_already_at_target(self):
        s = Schema("v2").step("v1", migrate_v1_to_v2)
        raw = msgspec.json.encode(V2Data(name="eve", value=1, tag="ok"))
        data = io.BytesIO(raw)
        result = s.migrate(data, "v2")
        # Returns raw bytes (already at target)
        assert result == raw

    def test_migrate_no_target_version_raises(self):
        s = Schema()
        data = io.BytesIO(b"{}")
        with pytest.raises(ValueError, match="Schema has no target version"):
            s.migrate(data, "v1")

    def test_migrate_no_path_raises(self):
        s = Schema("v3").step("v1", migrate_v1_to_v2)
        data = io.BytesIO(b"{}")
        with pytest.raises(ValueError, match="No migration path"):
            s.migrate(data, "v2")


# =====================================================================
# Tests: Reindex-only scenario
# =====================================================================


class TestReindexOnly:
    """Schema("v2") with no steps = reindex only."""

    def test_reindex_only_properties(self):
        s = Schema("v2")
        assert s.version == "v2"
        assert not s.has_migration
        assert s.schema_version == "v2"

    def test_reindex_only_no_from_version_raises(self):
        """When no steps defined and from != target, no path is possible."""
        s = Schema("v2")
        data = io.BytesIO(b"{}")
        with pytest.raises(ValueError, match="No migration path"):
            s.migrate(data, "v1")

    def test_reindex_only_same_version_returns_bytes(self):
        """Already at target = return raw bytes."""
        s = Schema("v2")
        raw = b'{"name":"test"}'
        data = io.BytesIO(raw)
        result = s.migrate(data, "v2")
        assert result == raw


# =====================================================================
# Tests: Validation
# =====================================================================


class TestSchemaValidation:
    def test_validate_callable(self):
        def check(data):
            if getattr(data, "value", 0) < 0:
                raise ValueError("negative value")

        s = Schema("v1", validator=check)
        ok = V1Data(name="ok", value=1)
        s.validate(ok)  # no error

        bad = V1Data(name="bad", value=-1)
        with pytest.raises(ValidationError, match="negative value"):
            s.validate(bad)

    def test_validate_ivalidator(self):
        class NonNeg(IValidator):
            def validate(self, data: Any) -> None:
                if data.value < 0:
                    raise ValueError("must be non-negative")

        s = Schema("v1", validator=NonNeg())
        with pytest.raises(ValidationError, match="must be non-negative"):
            s.validate(V1Data(name="x", value=-5))

    def test_validate_none_is_noop(self):
        s = Schema("v1")
        s.validate(V1Data(name="anything", value=0))  # should not raise

    def test_validate_preserves_validation_error(self):
        def check(data):
            raise ValidationError("custom")

        s = Schema("v1", validator=check)
        with pytest.raises(ValidationError, match="custom"):
            s.validate(V1Data(name="x", value=0))


# =====================================================================
# Tests: from_legacy
# =====================================================================


class TestFromLegacy:
    def test_wraps_imigration(self):
        class LegacyMig(IMigration[V2Data]):
            @property
            def schema_version(self) -> str:
                return "v2"

            def migrate(self, data: IO[bytes], schema_version: str | None) -> V2Data:
                obj = msgspec.json.decode(data.read(), type=V1Data)
                return V2Data(name=obj.name, value=obj.value, tag="legacy")

        legacy = LegacyMig()
        s = Schema.from_legacy(legacy)

        assert s.schema_version == "v2"
        assert s.has_migration
        assert s.version == "v2"

        data = io.BytesIO(msgspec.json.encode(V1Data(name="t", value=1)))
        result = s.migrate(data, "v1")
        assert isinstance(result, V2Data)
        assert result.tag == "legacy"

    def test_from_legacy_invalid_type_raises(self):
        with pytest.raises(TypeError, match="Expected IMigration instance"):
            Schema.from_legacy("not a migration")  # type: ignore

    def test_from_legacy_has_migration(self):
        class Mig(IMigration[V1Data]):
            @property
            def schema_version(self) -> str:
                return "v1"

            def migrate(self, data: IO[bytes], schema_version: str | None) -> V1Data:
                return V1Data(name="x", value=0)

        s = Schema.from_legacy(Mig())
        assert s.has_migration


# =====================================================================
# Tests: Edge cases
# =====================================================================


class TestEdgeCases:
    def test_graph_invalidation_on_step(self):
        """Adding a step invalidates the cached graph."""
        s = Schema("v2").step("v1", migrate_v1_to_v2)
        _ = s._resolve()  # populate cache
        assert s._graph is not None
        s.step("v2", migrate_v2_to_v3)
        assert s._graph is None  # invalidated

    def test_multiple_edges_from_same_version(self):
        """Multiple paths from the same source version."""

        def fn_a(d):
            return V2Data(name="a", value=0, tag="a")

        def fn_b(d):
            return V3Data(name="b", value=0, tag="b", score=0)

        s = Schema("v3").step("v1", fn_a, to="v2").plus("v1", fn_b)
        graph = s._resolve()
        assert len(graph["v1"]) == 2

    def test_diamond_graph(self):
        """Diamond-shaped graph: v1 → v2a, v1 → v2b, v2a → v3, v2b → v3."""

        def fn_a(d):
            return V2Data(name="a", value=0, tag="via-a")

        def fn_b(d):
            return V2Data(name="b", value=0, tag="via-b")

        def fn_a3(d):
            return V3Data(name="a", value=0, tag="via-a", score=0)

        def fn_b3(d):
            return V3Data(name="b", value=0, tag="via-b", score=0)

        s = (
            Schema("v3")
            .step("v1", fn_a, to="v2a")
            .step("v2a", fn_a3)
            .plus("v1", fn_b, to="v2b")
            .step("v2b", fn_b3)
        )
        graph = s._resolve()
        # v1 has two outgoing edges
        assert len(graph["v1"]) == 2
        # Both paths lead to v3
        path = s._find_path("v1", "v3")
        assert len(path) == 2  # Both paths are length 2, BFS picks first

    def test_step_returns_self(self):
        s = Schema("v2")
        result = s.step("v1", migrate_v1_to_v2)
        assert result is s

    def test_plus_returns_self(self):
        s = Schema("v3").step("v1", migrate_v1_to_v2)
        result = s.plus("v1", migrate_v1_to_v3_direct)
        assert result is s

    def test_resolve_caches(self):
        s = Schema("v2").step("v1", migrate_v1_to_v2)
        g1 = s._resolve()
        g2 = s._resolve()
        assert g1 is g2  # same object, cached
