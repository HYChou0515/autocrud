"""Tests for the feature-toggle resolver.

Pure function: combines pyproject config + CLI overrides into the final
list of enabled feature names. Used by gen --call to drive STEP 2's
codegen scope (which `add_model` kwargs the LLM is told to emit).
"""

from __future__ import annotations

from pathlib import Path

from specstar.skill.features import (
    DEFAULT_FEATURES,
    load_features_from_pyproject,
    resolve_features,
)


class TestResolveFeatures:
    def test_no_config_no_cli_returns_default(self) -> None:
        # Tracer: with neither pyproject nor CLI, the conservative
        # default list applies.
        assert resolve_features() == DEFAULT_FEATURES

    def test_pyproject_value_replaces_default(self) -> None:
        # If [tool.specstar].features is set, that's the authoritative
        # base — it wholly replaces the framework default.
        result = resolve_features(pyproject_value=["permissions", "indexes"])
        assert result == ("permissions", "indexes")

    def test_pyproject_empty_list_disables_all_features(self) -> None:
        # Empty list ≠ "key absent". Empty = "I deliberately want
        # no features" (e.g., diff between vanilla msgspec models
        # and full SpecStar). None = fall back to default.
        result = resolve_features(pyproject_value=[])
        assert result == ()

    def test_cli_enable_adds_to_base(self) -> None:
        # `--feature storage` on top of pyproject = ["permissions"]
        # widens the run scope without editing the project's pyproject.
        result = resolve_features(
            pyproject_value=["permissions"], cli_enable=["storage"]
        )
        assert result == ("permissions", "storage")

    def test_cli_disable_removes_from_base(self) -> None:
        # `--no-feature workflows` lets a user dial back the project
        # default for one run (e.g., to debug a permission issue
        # without the workflow handler noise).
        result = resolve_features(
            pyproject_value=["permissions", "workflows", "schema"],
            cli_disable=["workflows"],
        )
        assert result == ("permissions", "schema")

    def test_cli_disable_silent_when_not_in_base(self) -> None:
        # Disabling a feature that's not enabled is a no-op, not an
        # error — keeps `--no-feature` safe for shell aliases.
        result = resolve_features(pyproject_value=["permissions"], cli_disable=["mq"])
        assert result == ("permissions",)

    def test_disable_wins_when_both_enable_and_disable_reference_same(
        self,
    ) -> None:
        # If a user types `--feature X --no-feature X`, the disable
        # wins — explicit opt-out beats explicit opt-in.
        result = resolve_features(
            pyproject_value=[],
            cli_enable=["storage"],
            cli_disable=["storage"],
        )
        assert result == ()


class TestLoadFeaturesFromPyproject:
    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        # No pyproject.toml at all → key-absent semantics → caller
        # falls back to default. Silent rather than erroring keeps
        # the no-config UX clean.
        assert load_features_from_pyproject(tmp_path / "pyproject.toml") is None

    def test_no_specstar_section_returns_none(self, tmp_path: Path) -> None:
        # File exists but lacks [tool.specstar].features → also key-absent.
        path = tmp_path / "pyproject.toml"
        path.write_text("[project]\nname = 'x'\n", encoding="utf-8")
        assert load_features_from_pyproject(path) is None

    def test_reads_features_list(self, tmp_path: Path) -> None:
        path = tmp_path / "pyproject.toml"
        path.write_text(
            '[tool.specstar]\nfeatures = ["permissions", "schema"]\n',
            encoding="utf-8",
        )
        assert load_features_from_pyproject(path) == ["permissions", "schema"]

    def test_reads_explicit_empty_list(self, tmp_path: Path) -> None:
        # Empty list is meaningful — must round-trip as [], not None.
        path = tmp_path / "pyproject.toml"
        path.write_text(
            "[tool.specstar]\nfeatures = []\n",
            encoding="utf-8",
        )
        assert load_features_from_pyproject(path) == []
