"""Tests for the shared prompt builders.

Anchors the wording that both the Claude Code skill and ``specstar gen``
will eventually use. Tests are content-checks, not deep behavior tests:
the actual LLM behavior is exercised via ``specstar gen`` integration
tests once that command lands.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from specstar.descriptor import Descriptor, ValidationStatus
from specstar.lockfile import build_manifest
from specstar.skill import (
    AuthoringState,
    build_messages,
    build_system_prompt,
    build_user_prompt,
)
from specstar.skill.prompts import state_from_paths


@pytest.fixture()
def sample_state() -> AuthoringState:
    return AuthoringState(
        spec_md="# my_app\n\n## Resource: User\n",
        generated_py="from specstar import spec\n",
        manifest_json='{"specstar_version": "0.11.0"}',
        package_name="my_app",
    )


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


class TestSystemPrompt:
    def test_includes_declarative_python_rule(self) -> None:
        sp = build_system_prompt()
        assert (
            "declarative Python only" in sp.lower()
            or "declarative python only" in sp.lower()
        )

    def test_lists_blocked_imports(self) -> None:
        sp = build_system_prompt()
        # Spot-check a few high-risk modules.
        for module in ["os", "subprocess", "socket", "requests"]:
            assert module in sp

    def test_lists_blocked_statements(self) -> None:
        sp = build_system_prompt()
        for stmt in ["Try", "While", "Raise", "AsyncFunctionDef"]:
            assert stmt in sp

    def test_lists_blocked_builtins(self) -> None:
        sp = build_system_prompt()
        for builtin in ["exec", "eval", "open", "__import__", "getattr"]:
            assert builtin in sp

    def test_mentions_dunder_guard(self) -> None:
        sp = build_system_prompt()
        assert "__class__" in sp or "dunder" in sp

    def test_lists_case_decision_tree(self) -> None:
        sp = build_system_prompt()
        assert "Case" in sp or "case" in sp
        assert "1" in sp and "2" in sp and "3" in sp and "4" in sp

    def test_requires_inferred_decisions_listed(self) -> None:
        sp = build_system_prompt()
        assert "inferred" in sp.lower()

    def test_forbids_silent_fallback(self) -> None:
        sp = build_system_prompt()
        assert "improvise" in sp.lower() or "never" in sp.lower()

    def test_describes_beta_string_reference(self) -> None:
        sp = build_system_prompt()
        # Either β/beta vocabulary or the literal pattern of a string ref.
        assert (
            "string reference" in sp.lower()
            or "string ref" in sp.lower()
            or "my_app.logic" in sp
        )


# ---------------------------------------------------------------------------
# User prompt
# ---------------------------------------------------------------------------


class TestUserPrompt:
    def test_includes_brief(self, sample_state: AuthoringState) -> None:
        up = build_user_prompt("add a Phone field to User", sample_state)
        assert "add a Phone field to User" in up

    def test_strips_brief_whitespace(self, sample_state: AuthoringState) -> None:
        up = build_user_prompt("  trimmed  \n", sample_state)
        # Stripped — leading/trailing whitespace gone.
        assert "BRIEF:\ntrimmed" in up

    def test_embeds_spec_md(self, sample_state: AuthoringState) -> None:
        up = build_user_prompt("change", sample_state)
        assert sample_state.spec_md in up

    def test_embeds_generated_py(self, sample_state: AuthoringState) -> None:
        up = build_user_prompt("change", sample_state)
        assert sample_state.generated_py in up

    def test_embeds_manifest_json(self, sample_state: AuthoringState) -> None:
        up = build_user_prompt("change", sample_state)
        assert sample_state.manifest_json in up

    def test_mentions_package_name(self, sample_state: AuthoringState) -> None:
        up = build_user_prompt("change", sample_state)
        assert sample_state.package_name in up

    def test_asks_for_plan_not_files(self, sample_state: AuthoringState) -> None:
        up = build_user_prompt("change", sample_state)
        assert "plan" in up.lower()
        assert "do not write" in up.lower()


# ---------------------------------------------------------------------------
# build_messages — Anthropic API shape
# ---------------------------------------------------------------------------


class TestBuildMessages:
    def test_returns_list_of_role_content_dicts(
        self, sample_state: AuthoringState
    ) -> None:
        msgs = build_messages("brief", sample_state)
        assert isinstance(msgs, list)
        assert len(msgs) >= 1
        assert all("role" in m and "content" in m for m in msgs)

    def test_first_message_is_user_role(self, sample_state: AuthoringState) -> None:
        msgs = build_messages("brief", sample_state)
        assert msgs[0]["role"] == "user"

    def test_user_message_body_matches_user_prompt(
        self, sample_state: AuthoringState
    ) -> None:
        msgs = build_messages("brief", sample_state)
        assert msgs[0]["content"] == build_user_prompt("brief", sample_state)


# ---------------------------------------------------------------------------
# state_from_paths convenience
# ---------------------------------------------------------------------------


class TestStateFromPaths:
    def test_reads_files_and_serializes_manifest(self, tmp_path: Path) -> None:
        spec_md = tmp_path / "spec.md"
        spec_md.write_text("# demo\n", encoding="utf-8")
        gen = tmp_path / "_generated.py"
        gen.write_text("x = 1\n", encoding="utf-8")
        manifest = build_manifest(
            Descriptor(nodes=[], edges=[]),
            sources={"spec.md": spec_md},
            validation=ValidationStatus(ast_check="passed"),
        )
        state = state_from_paths(
            spec_md_path=spec_md,
            generated_py_path=gen,
            manifest=manifest,
            package_name="my_app",
        )
        assert state.spec_md == "# demo\n"
        assert state.generated_py == "x = 1\n"
        assert "specstar_version" in state.manifest_json
        assert state.package_name == "my_app"

    def test_handles_missing_manifest(self, tmp_path: Path) -> None:
        spec_md = tmp_path / "spec.md"
        spec_md.write_text("# demo\n", encoding="utf-8")
        gen = tmp_path / "_generated.py"
        gen.write_text("x = 1\n", encoding="utf-8")
        state = state_from_paths(
            spec_md_path=spec_md,
            generated_py_path=gen,
            manifest=None,
            package_name="my_app",
        )
        assert "no spec.lock.json" in state.manifest_json
