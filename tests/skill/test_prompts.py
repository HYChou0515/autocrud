"""Tests for the two-step prompt builders.

Content checks anchor the wording shared by the Claude Code skill and the
upcoming ``specstar gen`` CLI. Real LLM behavior is exercised separately.
"""

from __future__ import annotations

import pytest

from specstar.skill import (
    STEP1_SYSTEM_PROMPT,
    STEP2_SYSTEM_PROMPT,
    Step1Input,
    Step2Input,
    build_step1_messages,
    build_step1_user_prompt,
    build_step2_messages,
    build_step2_user_prompt,
)


@pytest.fixture()
def step1_input() -> Step1Input:
    return Step1Input(
        intent_md="I want a User resource with name and email.",
        previous_spec_md="# my_app\n",
        package_name="my_app",
    )


@pytest.fixture()
def step2_input() -> Step2Input:
    return Step2Input(
        spec_md="# my_app\n\n## Resource: User\n\n### Fields\n- `name`: str\n",
        previous_generated_py="from specstar import spec\n",
        package_name="my_app",
    )


# ---------------------------------------------------------------------------
# STEP 1 system prompt
# ---------------------------------------------------------------------------


class TestStep1SystemPrompt:
    def test_describes_beta_protocol(self) -> None:
        assert "β heading protocol" in STEP1_SYSTEM_PROMPT
        assert "## Resource:" in STEP1_SYSTEM_PROMPT
        assert "### Fields" in STEP1_SYSTEM_PROMPT

    def test_requires_breaking_change_detection(self) -> None:
        assert "breaking change" in STEP1_SYSTEM_PROMPT.lower()

    def test_requires_inferred_decisions_listed(self) -> None:
        assert "inferred" in STEP1_SYSTEM_PROMPT.lower()
        assert "InferredDecision" in STEP1_SYSTEM_PROMPT

    def test_requires_practical_stability(self) -> None:
        assert (
            "stability" in STEP1_SYSTEM_PROMPT.lower()
            or "verbatim" in STEP1_SYSTEM_PROMPT.lower()
        )

    def test_specifies_specplan_output(self) -> None:
        assert "SpecPlan" in STEP1_SYSTEM_PROMPT
        assert "spec_md_after" in STEP1_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# STEP 2 system prompt
# ---------------------------------------------------------------------------


class TestStep2SystemPrompt:
    def test_states_declarative_only_rule(self) -> None:
        assert "declarative" in STEP2_SYSTEM_PROMPT.lower()

    def test_lists_blocked_imports(self) -> None:
        for module in ["os", "subprocess", "socket", "requests"]:
            assert module in STEP2_SYSTEM_PROMPT

    def test_lists_blocked_statements(self) -> None:
        for stmt in ["Try", "While", "Raise", "AsyncFunctionDef"]:
            assert stmt in STEP2_SYSTEM_PROMPT

    def test_lists_blocked_builtins(self) -> None:
        for bi in ["exec", "eval", "open", "__import__", "getattr"]:
            assert bi in STEP2_SYSTEM_PROMPT

    def test_mentions_dunder_guard(self) -> None:
        assert "__class__" in STEP2_SYSTEM_PROMPT or "dunder" in STEP2_SYSTEM_PROMPT

    def test_describes_string_reference_for_io(self) -> None:
        assert "string reference" in STEP2_SYSTEM_PROMPT.lower()
        # Concrete example included
        assert "my_app.logic" in STEP2_SYSTEM_PROMPT

    def test_specifies_pythonplan_output(self) -> None:
        assert "PythonPlan" in STEP2_SYSTEM_PROMPT
        assert "generated_py_after" in STEP2_SYSTEM_PROMPT

    def test_states_step2_cannot_modify_spec_md(self) -> None:
        # Important invariant: STEP 2 must not touch spec.md
        assert "spec_md_after" in STEP2_SYSTEM_PROMPT
        assert "cannot modify spec.md" in STEP2_SYSTEM_PROMPT.lower()


# ---------------------------------------------------------------------------
# Step 1 user prompt
# ---------------------------------------------------------------------------


class TestStep1UserPrompt:
    def test_embeds_intent(self, step1_input: Step1Input) -> None:
        up = build_step1_user_prompt(step1_input)
        assert step1_input.intent_md in up

    def test_embeds_previous_spec(self, step1_input: Step1Input) -> None:
        up = build_step1_user_prompt(step1_input)
        assert step1_input.previous_spec_md in up

    def test_mentions_package_name(self, step1_input: Step1Input) -> None:
        up = build_step1_user_prompt(step1_input)
        assert step1_input.package_name in up

    def test_asks_for_specplan(self, step1_input: Step1Input) -> None:
        up = build_step1_user_prompt(step1_input)
        assert "SpecPlan" in up


# ---------------------------------------------------------------------------
# Step 2 user prompt
# ---------------------------------------------------------------------------


class TestStep2UserPrompt:
    def test_embeds_spec_md(self, step2_input: Step2Input) -> None:
        up = build_step2_user_prompt(step2_input)
        assert step2_input.spec_md in up

    def test_embeds_previous_generated_py(self, step2_input: Step2Input) -> None:
        up = build_step2_user_prompt(step2_input)
        assert step2_input.previous_generated_py in up

    def test_mentions_package_name(self, step2_input: Step2Input) -> None:
        up = build_step2_user_prompt(step2_input)
        assert step2_input.package_name in up

    def test_asks_for_pythonplan(self, step2_input: Step2Input) -> None:
        up = build_step2_user_prompt(step2_input)
        assert "PythonPlan" in up

    def test_includes_generated_py_path_with_package(
        self, step2_input: Step2Input
    ) -> None:
        up = build_step2_user_prompt(step2_input)
        assert f"{step2_input.package_name}/_generated.py" in up


# ---------------------------------------------------------------------------
# build_messages — Anthropic API shape
# ---------------------------------------------------------------------------


class TestBuildMessages:
    def test_step1_returns_one_user_message(self, step1_input: Step1Input) -> None:
        msgs = build_step1_messages(step1_input)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == build_step1_user_prompt(step1_input)

    def test_step2_returns_one_user_message(self, step2_input: Step2Input) -> None:
        msgs = build_step2_messages(step2_input)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == build_step2_user_prompt(step2_input)
