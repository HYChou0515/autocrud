"""Unit tests for ``autocrud.schema.Schema``."""

from __future__ import annotations

import io
import re
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
        s = Schema(V2Data, "v2")
        assert s.version == "v2"
        assert s.schema_version == "v2"  # IMigration compat
        assert not s.has_migration
        assert not s.has_validator
        assert s.resource_type is V2Data

    def test_with_validator_callable(self):
        def my_val(data):
            pass

        s = Schema(V1Data, "v1", validator=my_val)
        assert s.has_validator
        assert s.raw_validator is my_val

    def test_with_validator_ivalidator(self):
        class MyVal(IValidator):
            def validate(self, data: Any) -> None:
                if getattr(data, "value", 0) < 0:
                    raise ValueError("negative")

        val = MyVal()
        s = Schema(V1Data, "v1", validator=val)
        assert s.has_validator
        assert s.raw_validator is val

    def test_repr_basic(self):
        s = Schema(V2Data, "v2")
        assert repr(s) == "Schema(V2Data, 'v2')"

    def test_repr_with_steps(self):
        s = (
            Schema(V3Data, "v3")
            .step("v1", migrate_v1_to_v2)
            .step("v2", migrate_v2_to_v3)
        )
        r = repr(s)
        assert ".step('v1', ...)" in r
        assert ".step('v2', ...)" in r

    def test_repr_with_plus(self):
        s = (
            Schema(V3Data, "v3")
            .step("v1", migrate_v1_to_v2)
            .step("v2", migrate_v2_to_v3)
            .plus("v1", migrate_v1_to_v3_direct)
        )
        r = repr(s)
        assert ".plus('v1', ...)" in r

    def test_repr_with_validator(self):
        s = Schema(V2Data, "v2", validator=lambda d: None)
        assert "validator=..." in repr(s)


# =====================================================================
# Tests: Step chain inference
# =====================================================================


class TestStepChainInference:
    """Test auto-inference of ``to`` in step chains."""

    def test_single_step_infers_to_target(self):
        """Last step in chain → Schema target version."""
        s = Schema(V2Data, "v2").step("v1", migrate_v1_to_v2)
        graph = s._resolve()
        assert "v1" in graph
        edges = graph["v1"]
        assert len(edges) == 1
        assert edges[0][0] == "v2"  # to_ver

    def test_two_step_chain_infers_middle(self):
        """Middle step's ``to`` = next step's ``from``."""
        s = (
            Schema(V3Data, "v3")
            .step("v1", migrate_v1_to_v2)
            .step("v2", migrate_v2_to_v3)
        )
        graph = s._resolve()
        # v1 → v2 (inferred from next step)
        assert graph["v1"][0][0] == "v2"
        # v2 → v3 (inferred from target)
        assert graph["v2"][0][0] == "v3"

    def test_explicit_to_overrides(self):
        """Explicit ``to=`` overrides auto inference."""
        s = (
            Schema(V3Data, "v3")
            .step("v1", migrate_v1_to_v2, to="v2")
            .step("v2", migrate_v2_to_v3)
        )
        graph = s._resolve()
        assert graph["v1"][0][0] == "v2"
        assert graph["v2"][0][0] == "v3"

    def test_explicit_to_on_last_step_overrides_target(self):
        """Explicit ``to=`` on last step can differ from Schema.version."""
        s = Schema(V2Data, "v4").step("v1", migrate_v1_to_v2, to="v2")
        graph = s._resolve()
        assert graph["v1"][0][0] == "v2"


# =====================================================================
# Tests: plus() parallel chains
# =====================================================================


class TestPlusParallelChains:
    def test_plus_creates_new_chain(self):
        s = (
            Schema(V3Data, "v3")
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
            Schema(V3Data, "v3")
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

        s1 = Schema(V3Data, "v3").step("v1", fn1).step("v2", fn2).plus("v1", fn3)
        s2 = Schema(V3Data, "v3").step("v1", fn3).plus("v1", fn1).step("v2", fn2)

        g1, g2 = s1._resolve(), s2._resolve()
        # Both should have v1 → {v2, v3} and v2 → {v3}
        assert sorted(t for t, _ in g1["v1"]) == sorted(t for t, _ in g2["v1"])
        assert g1["v2"][0][0] == g2["v2"][0][0] == "v3"

    def test_plus_explicit_to(self):
        s = (
            Schema(V3Data, "v3")
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
        s = Schema(V2Data, "v2").step("v1", migrate_v1_to_v2)
        path = s._find_path("v1", "v2")
        assert len(path) == 1
        assert path[0][0] == "v1"
        assert path[0][1] == "v2"

    def test_two_step_path(self):
        s = (
            Schema(V3Data, "v3")
            .step("v1", migrate_v1_to_v2)
            .step("v2", migrate_v2_to_v3)
        )
        path = s._find_path("v1", "v3")
        assert len(path) == 2
        assert path[0][:2] == ("v1", "v2")
        assert path[1][:2] == ("v2", "v3")

    def test_shortcut_preferred(self):
        """BFS should find shortest path (1 step) over longer path (2 steps)."""
        s = (
            Schema(V3Data, "v3")
            .step("v1", migrate_v1_to_v2)
            .step("v2", migrate_v2_to_v3)
            .plus("v1", migrate_v1_to_v3_direct)
        )
        path = s._find_path("v1", "v3")
        # Should pick the shortcut (1 step) over chain (2 steps)
        assert len(path) == 1
        assert path[0][:2] == ("v1", "v3")

    def test_same_version_empty_path(self):
        s = Schema(V2Data, "v2").step("v1", migrate_v1_to_v2)
        path = s._find_path("v2", "v2")
        assert path == []

    def test_no_path_raises(self):
        s = Schema(V3Data, "v3").step("v1", migrate_v1_to_v2)
        with pytest.raises(ValueError, match="No migration path"):
            s._find_path("v2", "v3")

    def test_unknown_source_raises(self):
        s = Schema(V2Data, "v2").step("v1", migrate_v1_to_v2)
        with pytest.raises(ValueError, match="No migration path"):
            s._find_path("v999", "v2")


# =====================================================================
# Tests: migrate() execution
# =====================================================================


class TestMigrateExecution:
    def _make_stream(self, obj: Any) -> io.BytesIO:
        return io.BytesIO(msgspec.json.encode(obj))

    def test_single_step_migration(self):
        s = Schema(V2Data, "v2").step("v1", migrate_v1_to_v2)
        data = self._make_stream(V1Data(name="alice", value=42))
        result = s.migrate(data, "v1")
        assert isinstance(result, V2Data)
        assert result.name == "alice"
        assert result.value == 42
        assert result.tag == "migrated"

    def test_chain_migration(self):
        s = (
            Schema(V3Data, "v3")
            .step("v1", migrate_v1_to_v2)
            .step("v2", migrate_v2_to_v3)
        )
        data = self._make_stream(V1Data(name="bob", value=10))
        result = s.migrate(data, "v1")
        assert isinstance(result, V3Data)
        assert result.name == "bob"
        assert result.tag == "migrated"
        assert result.score == 0.0

    def test_shortcut_migration(self):
        s = (
            Schema(V3Data, "v3")
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
        s = (
            Schema(V3Data, "v3")
            .step("v1", migrate_v1_to_v2)
            .step("v2", migrate_v2_to_v3)
        )
        data = self._make_stream(V2Data(name="dave", value=7, tag="existing"))
        result = s.migrate(data, "v2")
        assert isinstance(result, V3Data)
        assert result.tag == "existing"
        assert result.score == 0.0

    def test_migrate_already_at_target(self):
        s = Schema(V2Data, "v2").step("v1", migrate_v1_to_v2)
        raw = msgspec.json.encode(V2Data(name="eve", value=1, tag="ok"))
        data = io.BytesIO(raw)
        result = s.migrate(data, "v2")
        # Returns raw bytes (already at target)
        assert result == raw

    def test_migrate_no_path_raises(self):
        s = Schema(V3Data, "v3").step("v1", migrate_v1_to_v2)
        data = io.BytesIO(b"{}")
        with pytest.raises(ValueError, match="No migration path"):
            s.migrate(data, "v2")


# =====================================================================
# Tests: Reindex-only scenario
# =====================================================================


class TestReindexOnly:
    """Schema(MyModel, "v2") with no steps = reindex only."""

    def test_reindex_only_properties(self):
        s = Schema(V2Data, "v2")
        assert s.version == "v2"
        assert not s.has_migration
        assert s.schema_version == "v2"

    def test_reindex_only_no_from_version_raises(self):
        """When no steps defined and from != target, no path is possible."""
        s = Schema(V2Data, "v2")
        data = io.BytesIO(b"{}")
        with pytest.raises(ValueError, match="No migration path"):
            s.migrate(data, "v1")

    def test_reindex_only_same_version_returns_bytes(self):
        """Already at target = return raw bytes."""
        s = Schema(V2Data, "v2")
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

        s = Schema(V1Data, "v1", validator=check)
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

        s = Schema(V1Data, "v1", validator=NonNeg())
        with pytest.raises(ValidationError, match="must be non-negative"):
            s.validate(V1Data(name="x", value=-5))

    def test_validate_none_is_noop(self):
        s = Schema(V1Data, "v1")
        s.validate(V1Data(name="anything", value=0))  # should not raise

    def test_validate_preserves_validation_error(self):
        def check(data):
            raise ValidationError("custom")

        s = Schema(V1Data, "v1", validator=check)
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
        """Adding a step invalidates the cached graph and path cache."""
        s = Schema(V2Data, "v2").step("v1", migrate_v1_to_v2)
        _ = s._resolve()  # populate cache
        assert s._graph is not None
        s.step("v2", migrate_v2_to_v3)
        assert s._graph is None  # invalidated
        assert s._path_cache == {}  # invalidated

    def test_multiple_edges_from_same_version(self):
        """Multiple paths from the same source version."""

        def fn_a(d):
            return V2Data(name="a", value=0, tag="a")

        def fn_b(d):
            return V3Data(name="b", value=0, tag="b", score=0)

        s = Schema(V3Data, "v3").step("v1", fn_a, to="v2").plus("v1", fn_b)
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
            Schema(V3Data, "v3")
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
        s = Schema(V2Data, "v2")
        result = s.step("v1", migrate_v1_to_v2)
        assert result is s

    def test_plus_returns_self(self):
        s = Schema(V3Data, "v3").step("v1", migrate_v1_to_v2)
        result = s.plus("v1", migrate_v1_to_v3_direct)
        assert result is s

    def test_resolve_caches(self):
        s = Schema(V2Data, "v2").step("v1", migrate_v1_to_v2)
        g1 = s._resolve()
        g2 = s._resolve()
        assert g1 is g2  # same object, cached

    def test_resource_type_property(self):
        s = Schema(V1Data, "v1")
        assert s.resource_type is V1Data

    def test_from_legacy_resource_type_is_none(self):
        class Mig(IMigration[V1Data]):
            @property
            def schema_version(self) -> str:
                return "v1"

            def migrate(self, data, sv):
                return V1Data(name="x", value=0)

        s = Schema.from_legacy(Mig())
        assert s.resource_type is None


# =====================================================================
# Tests: Regex from_ver in step/plus
# =====================================================================


class TestRegexFromVer:
    """Test regex patterns as from_ver in step() and plus()."""

    def _make_stream(self, obj: Any) -> io.BytesIO:
        return io.BytesIO(msgspec.json.encode(obj))

    def test_regex_step_matches_multiple_versions(self):
        """A regex from_ver creates edges from all matched versions at runtime."""
        # v1 → v2 (literal), v2 → v3 (literal), then regex v[12] → v3
        s = (
            Schema(V3Data, "v3")
            .step("v1", migrate_v1_to_v2, to="v2")
            .step("v2", migrate_v2_to_v3)
            .plus(re.compile(r"v[12]"), migrate_v1_to_v3_direct)
        )
        # Regex edges are NOT in _resolve() graph — use _edges_for()
        v1_targets = {edge[0] for edge in s._edges_for("v1")}
        assert "v2" in v1_targets  # literal
        assert "v3" in v1_targets  # regex
        # v2 should also match the regex
        v2_targets = {edge[0] for edge in s._edges_for("v2")}
        assert "v3" in v2_targets

    def test_regex_step_single_chain(self):
        """Regex from_ver in main chain with explicit to — stored as regex edge."""
        s = Schema(V3Data, "v3").step(
            re.compile(r"v[12]"), migrate_v1_to_v3_direct, to="v3"
        )
        # No build-time error — regex is stored for runtime matching
        s._resolve()
        assert len(s._regex_edges) == 1
        # At runtime, v1 matches
        assert len(s._edges_for("v1")) == 1
        assert s._edges_for("v1")[0][0] == "v3"

    def test_regex_with_literal_sources(self):
        """Regex step creates edges at runtime for matching versions."""
        s = (
            Schema(V3Data, "v3")
            .step("v1", migrate_v1_to_v2, to="v2")
            .plus(re.compile(r"v1"), migrate_v1_to_v3_direct)
        )
        # v1 → v2 (literal), v1 → v3 (regex matching "v1")
        v1_targets = sorted(edge[0] for edge in s._edges_for("v1"))
        assert v1_targets == ["v2", "v3"]

    def test_regex_excludes_to_ver(self):
        """Regex does not create self-loops (from == to is excluded)."""

        def noop(d):
            return d

        s = (
            Schema(V3Data, "v3")
            .step("v1", migrate_v1_to_v2, to="v2")
            .step("v2", migrate_v2_to_v3)
            .plus(re.compile(r"v.*"), noop)  # matches v1, v2, v3
        )
        # v1 → v3 and v2 → v3 should exist from regex
        assert any(edge[0] == "v3" for edge in s._edges_for("v1"))
        assert any(edge[0] == "v3" for edge in s._edges_for("v2"))
        # v3 should NOT have a self-loop → v3
        v3_targets = [edge[0] for edge in s._edges_for("v3")]
        assert "v3" not in v3_targets

    def test_regex_matches_runtime_version(self):
        """Regex matches a version NOT declared in any literal step."""

        def upgrade_any_to_v3(data: IO[bytes]) -> V3Data:
            obj = msgspec.json.decode(data.read(), type=V1Data)
            return V3Data(name=obj.name, value=obj.value, tag="auto", score=0.0)

        s = Schema(V3Data, "v3").step(re.compile(r"v\d+"), upgrade_any_to_v3, to="v3")
        # v99 was never declared but matches regex at runtime
        assert len(s._edges_for("v99")) == 1
        data = self._make_stream(V1Data(name="surprise", value=7))
        result = s.migrate(data, "v99")
        assert isinstance(result, V3Data)
        assert result.name == "surprise"

    def test_regex_migration_execution(self):
        """Actually run a migration via a regex-defined path."""

        def upgrade_any_to_v3(data: IO[bytes]) -> V3Data:
            obj = msgspec.json.decode(data.read(), type=V1Data)
            return V3Data(name=obj.name, value=obj.value, tag="auto", score=0.0)

        s = (
            Schema(V3Data, "v3")
            .step("v1", migrate_v1_to_v2, to="v2")
            .plus(re.compile(r"v[12]"), upgrade_any_to_v3)
        )
        # Migrate from v1 → v3 (should use regex shortcut)
        data = self._make_stream(V1Data(name="test", value=42))
        result = s.migrate(data, "v1")
        assert isinstance(result, V3Data)
        assert result.tag == "auto"

    def test_regex_plus_creates_parallel_chain(self):
        """plus() with regex correctly flushes previous chain."""
        s = (
            Schema(V3Data, "v3")
            .step("v1", migrate_v1_to_v2, to="v2")
            .step("v2", migrate_v2_to_v3)
            .plus(re.compile(r"v1"), migrate_v1_to_v3_direct)
        )
        # v1 has: v2 (literal) + v3 (regex)
        v1_targets = sorted(edge[0] for edge in s._edges_for("v1"))
        assert v1_targets == ["v2", "v3"]
        # v2 has: v3 (literal only — regex r"v1" doesn't match "v2")
        graph = s._resolve()
        assert graph["v2"][0][0] == "v3"

    def test_regex_repr(self):
        """Repr shows regex pattern."""
        s = Schema(V3Data, "v3").step(
            re.compile(r"v[12]"), migrate_v1_to_v3_direct, to="v3"
        )
        r = repr(s)
        assert "re.compile" in r
        assert "v[12]" in r

    def test_regex_next_step_inference_raises(self):
        """Cannot infer to_ver when next step uses regex."""

        def noop(d):
            return d

        s = Schema(V3Data, "v3").step("v1", noop).step(re.compile(r"v2"), noop, to="v3")
        with pytest.raises(ValueError, match="next step uses a regex pattern"):
            s._resolve()

    def test_regex_with_explicit_to_on_middle_step(self):
        """Regex in a multi-step chain with explicit to."""

        def upgrade_to_v2(data: IO[bytes]) -> V2Data:
            obj = msgspec.json.decode(data.read(), type=V1Data)
            return V2Data(name=obj.name, value=obj.value, tag="regex")

        s = (
            Schema(V3Data, "v3")
            .step("v1", migrate_v1_to_v2, to="v2")
            .step("v2", migrate_v2_to_v3)
            .plus(re.compile(r"v1"), upgrade_to_v2, to="v2")
        )
        # v1 has: v2 (literal), v2 (regex) — two edges to v2
        v1_edges = s._edges_for("v1")
        assert len(v1_edges) == 2
        assert all(edge[0] == "v2" for edge in v1_edges)


# =====================================================================
# Tests: Coverage supplementary
# =====================================================================


class TestCoverageSupplementary:
    """Tests to cover remaining branches and edge-case lines."""

    def _make_stream(self, obj: Any) -> io.BytesIO:
        return io.BytesIO(msgspec.json.encode(obj))

    def test_plus_on_empty_chain(self):
        """Calling plus() when _current_chain is already empty (branch false)."""
        s = Schema(V3Data, "v3")
        # plus() as first call — _current_chain is empty, skip flush
        s.plus("v1", migrate_v1_to_v3_direct)
        graph = s._resolve()
        assert graph["v1"][0][0] == "v3"

    def test_from_legacy_migrate_delegates(self):
        """from_legacy schema has _version that may be None; migrate delegates."""

        class NoneVersionMig(IMigration[V1Data]):
            @property
            def schema_version(self) -> str | None:
                return None

            def migrate(self, data: IO[bytes], sv: str | None) -> V1Data:
                return V1Data(name="legacy", value=0)

        s = Schema.from_legacy(NoneVersionMig())
        assert s.version is None
        # migrate() delegates to legacy directly (line 305)
        result = s.migrate(io.BytesIO(b"{}"), None)
        assert isinstance(result, V1Data)
        assert result.name == "legacy"

    def test_from_legacy_resolve_with_none_version(self):
        """from_legacy schema with None version: _resolve works (no steps)."""

        class NoneVersionMig(IMigration[V1Data]):
            @property
            def schema_version(self) -> str | None:
                return None

            def migrate(self, data: IO[bytes], sv: str | None) -> V1Data:
                return V1Data(name="x", value=0)

        s = Schema.from_legacy(NoneVersionMig())
        # _resolve() with no chains and None version — empty graph
        graph = s._resolve()
        assert graph == {}

    def test_bfs_exhausted_no_path(self):
        """BFS exhausts all reachable nodes but never reaches target."""

        def noop(d: IO[bytes]) -> V2Data:
            return V2Data(name="x", value=0, tag="x")

        # v1 → v2, but no edge to v3 — from_ver IS in graph
        s = Schema(V3Data, "v3").step("v1", noop, to="v2")
        with pytest.raises(ValueError, match="No migration path"):
            s._find_path("v1", "v3")

    def test_path_cache_hit(self):
        """Second call to _find_path returns cached path."""
        s = (
            Schema(V3Data, "v3")
            .step("v1", migrate_v1_to_v2)
            .step("v2", migrate_v2_to_v3)
        )
        path1 = s._find_path("v1", "v3")
        path2 = s._find_path("v1", "v3")
        assert path1 is path2  # exact same cached object

    def test_edges_for_combines_literal_and_regex(self):
        """_edges_for merges literal graph edges with regex matches."""

        def noop(d):
            return d

        s = (
            Schema(V3Data, "v3")
            .step("v1", migrate_v1_to_v2, to="v2")
            .plus(re.compile(r"v\d+"), noop)
        )
        edges = s._edges_for("v1")
        # v1 has literal → v2 and regex → v3
        targets = {e[0] for e in edges}
        assert targets == {"v2", "v3"}

    def test_chain_migration_with_bytes_intermediate(self):
        """Chain migration where fn returns bytes (not Struct)."""

        def fn_v1_to_v2_bytes(data: IO[bytes]) -> bytes:
            """Returns raw bytes instead of decoded object."""
            obj = msgspec.json.decode(data.read(), type=V1Data)
            v2 = V2Data(name=obj.name, value=obj.value, tag="bytes")
            return msgspec.json.encode(v2)

        s = (
            Schema(V3Data, "v3")
            .step("v1", fn_v1_to_v2_bytes, to="v2")
            .step("v2", migrate_v2_to_v3)
        )
        data = self._make_stream(V1Data(name="test", value=1))
        result = s.migrate(data, "v1")
        assert isinstance(result, V3Data)
        assert result.name == "test"
        assert result.tag == "bytes"
        assert result.score == 0.0

    def test_chain_migration_with_decoded_intermediate(self):
        """Chain migration where fn returns decoded Struct (re-serialized)."""
        # This is the standard chain test, but let's make sure the
        # re-serialization branch (line 324) is hit.
        s = (
            Schema(V3Data, "v3")
            .step("v1", migrate_v1_to_v2)
            .step("v2", migrate_v2_to_v3)
        )
        data = self._make_stream(V1Data(name="chain", value=99))
        result = s.migrate(data, "v1")
        # migrate_v1_to_v2 returns V2Data (Struct), which triggers
        # re-serialization via msgspec.json.encode before next step
        assert isinstance(result, V3Data)
        assert result.name == "chain"
        assert result.tag == "migrated"

    def test_from_legacy_step_without_to_raises(self):
        """from_legacy with None version + step (no to=) → ValueError on _resolve."""

        class NoneVerMig(IMigration[V1Data]):
            @property
            def schema_version(self) -> str | None:
                return None

            def migrate(self, data: IO[bytes], sv: str | None) -> V1Data:
                return V1Data(name="x", value=0)

        s = Schema.from_legacy(NoneVerMig())
        # Add a step without explicit to= → last step tries self._version (None)
        s.step("v1", migrate_v1_to_v2)
        with pytest.raises(ValueError, match="Cannot infer target version"):
            s._resolve()
