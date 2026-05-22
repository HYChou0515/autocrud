"""Tests for the plan orchestration layer.

Decision-tree logic is exercised exhaustively (8 cases × force flags).
LLM invocations use a mock client; no real API calls.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from specstar.skill.plan import (
    ExecutionResult,
    StepDecision,
    apply_python_plan,
    apply_result,
    apply_spec_plan,
    decide_steps,
    execute_plan,
    render_decision,
    render_python_plan,
    render_spec_plan,
    run_step1,
    run_step2,
)
from specstar.skill.schemas import PythonPlan, SpecPlan


class _RecordingClient:
    """Mock LLMClient that returns canned plans and records every call."""

    def __init__(
        self,
        *,
        spec_plan: SpecPlan | None = None,
        python_plan: PythonPlan | None = None,
    ):
        self.spec_plan = spec_plan or SpecPlan(
            reasoning="r", summary="s", spec_md_after="# generated spec\n"
        )
        self.python_plan = python_plan or PythonPlan(
            reasoning="r",
            summary="s",
            generated_py_after="# generated py\n",
        )
        self.calls: list[dict] = []

    def call(self, *, system, user, response_model):
        self.calls.append(
            {"system": system, "user": user, "response_model": response_model}
        )
        if response_model is SpecPlan:
            return self.spec_plan
        if response_model is PythonPlan:
            return self.python_plan
        raise RuntimeError(f"unexpected response_model: {response_model}")


# ---------------------------------------------------------------------------
# decide_steps — exhaustive decision tree
# ---------------------------------------------------------------------------


class TestDecideStepsCaseTable:
    """Verify the 8 cases of the design-doc decision tree."""

    def test_case_1_clean(self) -> None:
        d = decide_steps(intent_changed=False, spec_changed=False, gen_changed=False)
        assert d.case == 1
        assert d.run_step1 is False and d.run_step2 is False
        assert d.conflicts == ()

    def test_case_2_intent_only(self) -> None:
        d = decide_steps(intent_changed=True, spec_changed=False, gen_changed=False)
        assert d.case == 2
        assert d.run_step1 is True and d.run_step2 is True

    def test_case_3_spec_only(self) -> None:
        d = decide_steps(intent_changed=False, spec_changed=True, gen_changed=False)
        assert d.case == 3
        assert d.run_step1 is False
        assert d.run_step2 is True

    def test_case_4_gen_only(self) -> None:
        d = decide_steps(intent_changed=False, spec_changed=False, gen_changed=True)
        assert d.case == 4
        assert d.run_step1 is False and d.run_step2 is False

    def test_case_5_intent_and_spec(self) -> None:
        d = decide_steps(intent_changed=True, spec_changed=True, gen_changed=False)
        assert d.case == 5
        assert d.run_step1 is False  # respect user spec
        assert d.run_step2 is True
        assert d.conflicts  # warns intent.md ignored

    def test_case_6_spec_and_gen(self) -> None:
        d = decide_steps(intent_changed=False, spec_changed=True, gen_changed=True)
        assert d.case == 6
        assert d.run_step1 is False and d.run_step2 is False
        assert d.conflicts

    def test_case_7_intent_and_gen(self) -> None:
        d = decide_steps(intent_changed=True, spec_changed=False, gen_changed=True)
        assert d.case == 7
        assert d.run_step1 is True
        assert d.run_step2 is False  # respect user py
        assert d.conflicts

    def test_case_8_all_changed(self) -> None:
        d = decide_steps(intent_changed=True, spec_changed=True, gen_changed=True)
        assert d.case == 8
        assert d.run_step1 is False and d.run_step2 is False
        assert d.conflicts


class TestDecideStepsForceFlags:
    def test_force_runs_both_steps(self) -> None:
        d = decide_steps(
            intent_changed=False, spec_changed=False, gen_changed=False, force=True
        )
        assert d.run_step1 is True and d.run_step2 is True
        assert d.case == 0

    def test_force_overrides_user_edits(self) -> None:
        # case 4 (user edited py) — force should still run both steps.
        d = decide_steps(
            intent_changed=False, spec_changed=False, gen_changed=True, force=True
        )
        assert d.run_step1 is True and d.run_step2 is True

    def test_from_spec_skips_step1_runs_step2(self) -> None:
        d = decide_steps(
            intent_changed=False,
            spec_changed=False,
            gen_changed=False,
            from_spec=True,
        )
        assert d.run_step1 is False
        assert d.run_step2 is True

    def test_force_and_from_spec_mutually_exclusive(self) -> None:
        with pytest.raises(ValueError, match="mutually exclusive"):
            decide_steps(
                intent_changed=False,
                spec_changed=False,
                gen_changed=False,
                force=True,
                from_spec=True,
            )


# ---------------------------------------------------------------------------
# run_step1 / run_step2 — LLM call wrappers
# ---------------------------------------------------------------------------


class TestRunSteps:
    def test_run_step1_passes_step1_system_prompt(self) -> None:
        client = _RecordingClient()
        result = run_step1(
            client,
            intent_md="my intent",
            previous_spec_md="# old\n",
            package_name="my_app",
        )
        assert isinstance(result, SpecPlan)
        assert len(client.calls) == 1
        # The system prompt should be the STEP 1 system prompt.
        from specstar.skill.prompts import STEP1_SYSTEM_PROMPT

        assert client.calls[0]["system"] == STEP1_SYSTEM_PROMPT
        assert "my intent" in client.calls[0]["user"]
        assert client.calls[0]["response_model"] is SpecPlan

    def test_run_step2_passes_step2_system_prompt(self) -> None:
        client = _RecordingClient()
        result = run_step2(
            client,
            spec_md="# spec\n",
            previous_generated_py="x = 1\n",
            package_name="my_app",
        )
        assert isinstance(result, PythonPlan)
        from specstar.skill.prompts import STEP2_SYSTEM_PROMPT

        assert client.calls[0]["system"] == STEP2_SYSTEM_PROMPT
        assert client.calls[0]["response_model"] is PythonPlan

    def test_run_step2_propagates_error_feedback_into_user_prompt(self) -> None:
        # When the caller provides error_feedback (e.g. captured stderr
        # from a previous failing import), run_step2 must thread it
        # through to the user prompt so the LLM sees the actual error
        # and can self-correct.
        client = _RecordingClient()
        feedback = (
            "TypeError: Schema.__init__() missing 1 required "
            "positional argument: 'version'"
        )
        run_step2(
            client,
            spec_md="# spec\n",
            previous_generated_py="x = 1\n",
            package_name="my_app",
            error_feedback=feedback,
        )
        user_msg = client.calls[0]["user"]
        assert "previous attempt" in user_msg.lower()
        assert "Schema.__init__()" in user_msg

    def test_run_step2_propagates_enabled_features(self) -> None:
        # run_step2 must thread enabled_features through to the user
        # prompt so the gen --call orchestrator can drive STEP 2's
        # codegen scope.
        client = _RecordingClient()
        run_step2(
            client,
            spec_md="# spec\n",
            previous_generated_py="x = 1\n",
            package_name="my_app",
            enabled_features=("permissions", "workflows"),
        )
        user_msg = client.calls[0]["user"]
        assert "Enabled features" in user_msg
        assert "permissions" in user_msg
        assert "workflows" in user_msg

    def test_run_step2_default_error_feedback_omitted(self) -> None:
        # When error_feedback is omitted, the user prompt must look
        # exactly like the no-feedback case (no leftover header).
        client = _RecordingClient()
        run_step2(
            client,
            spec_md="# spec\n",
            previous_generated_py="x = 1\n",
            package_name="my_app",
        )
        assert "previous attempt" not in client.calls[0]["user"].lower()


# ---------------------------------------------------------------------------
# apply_*  — file write
# ---------------------------------------------------------------------------


class TestApplyPlan:
    def test_apply_spec_plan_writes_full_content(self, tmp_path: Path) -> None:
        plan = SpecPlan(reasoning="r", summary="s", spec_md_after="# new spec\n")
        target = tmp_path / "spec.md"
        apply_spec_plan(plan, target)
        assert target.read_text() == "# new spec\n"

    def test_apply_python_plan_creates_parent_dir(self, tmp_path: Path) -> None:
        plan = PythonPlan(reasoning="r", summary="s", generated_py_after="x = 1\n")
        target = tmp_path / "my_app" / "_generated.py"
        # Parent dir doesn't exist yet — apply must create it.
        apply_python_plan(plan, target)
        assert target.read_text() == "x = 1\n"


# ---------------------------------------------------------------------------
# execute_plan — orchestration
# ---------------------------------------------------------------------------


class TestExecutePlan:
    @pytest.fixture()
    def project(self, tmp_path: Path) -> Path:
        (tmp_path / "intent.md").write_text("we have users\n", encoding="utf-8")
        (tmp_path / "spec.md").write_text("# old spec\n", encoding="utf-8")
        pkg = tmp_path / "my_app"
        pkg.mkdir()
        (pkg / "_generated.py").write_text("# old gen\n", encoding="utf-8")
        return tmp_path

    def test_runs_both_steps_when_decision_says_so(self, project: Path) -> None:
        client = _RecordingClient()
        decision = StepDecision(True, True, 2, "case 2", ())
        result = execute_plan(
            decision=decision,
            client=client,
            intent_path=project / "intent.md",
            spec_path=project / "spec.md",
            generated_path=project / "my_app" / "_generated.py",
            package_name="my_app",
        )
        assert result.spec_plan is not None
        assert result.python_plan is not None
        assert len(client.calls) == 2

    def test_step2_uses_step1_output_not_disk(self, project: Path) -> None:
        # If STEP 1 ran, STEP 2 should see the *new* spec.md content
        # (from the SpecPlan), not whatever's currently on disk.
        client = _RecordingClient(
            spec_plan=SpecPlan(
                reasoning="r", summary="s", spec_md_after="# brand new spec\n"
            )
        )
        decision = StepDecision(True, True, 2, "case 2", ())
        execute_plan(
            decision=decision,
            client=client,
            intent_path=project / "intent.md",
            spec_path=project / "spec.md",
            generated_path=project / "my_app" / "_generated.py",
            package_name="my_app",
        )
        # The second LLM call (STEP 2) must contain the new spec.
        assert "brand new spec" in client.calls[1]["user"]
        # And NOT the old spec.
        assert "old spec" not in client.calls[1]["user"]

    def test_skips_step1_runs_step2_only(self, project: Path) -> None:
        client = _RecordingClient()
        decision = StepDecision(False, True, 3, "case 3", ())
        result = execute_plan(
            decision=decision,
            client=client,
            intent_path=project / "intent.md",
            spec_path=project / "spec.md",
            generated_path=project / "my_app" / "_generated.py",
            package_name="my_app",
        )
        assert result.spec_plan is None
        assert result.python_plan is not None
        assert len(client.calls) == 1

    def test_case_4_runs_neither(self, project: Path) -> None:
        client = _RecordingClient()
        decision = StepDecision(False, False, 4, "case 4", ())
        result = execute_plan(
            decision=decision,
            client=client,
            intent_path=project / "intent.md",
            spec_path=project / "spec.md",
            generated_path=project / "my_app" / "_generated.py",
            package_name="my_app",
        )
        assert result.spec_plan is None
        assert result.python_plan is None
        assert len(client.calls) == 0

    def test_writes_no_files_during_execute(self, project: Path) -> None:
        # execute_plan must not write to disk — caller decides after
        # showing the plan to the user.
        original_spec = (project / "spec.md").read_text()
        original_gen = (project / "my_app" / "_generated.py").read_text()
        client = _RecordingClient()
        execute_plan(
            decision=StepDecision(True, True, 2, "case 2", ()),
            client=client,
            intent_path=project / "intent.md",
            spec_path=project / "spec.md",
            generated_path=project / "my_app" / "_generated.py",
            package_name="my_app",
        )
        assert (project / "spec.md").read_text() == original_spec
        assert (project / "my_app" / "_generated.py").read_text() == original_gen


class TestApplyResult:
    def test_writes_both_when_both_plans_present(self, tmp_path: Path) -> None:
        result = ExecutionResult(
            decision=StepDecision(True, True, 2, "x", ()),
            spec_plan=SpecPlan(reasoning="r", summary="s", spec_md_after="A"),
            python_plan=PythonPlan(reasoning="r", summary="s", generated_py_after="B"),
        )
        spec = tmp_path / "spec.md"
        gen = tmp_path / "pkg" / "_generated.py"
        written = apply_result(result, spec_path=spec, generated_path=gen)
        assert spec.read_text() == "A"
        assert gen.read_text() == "B"
        assert len(written) == 2

    def test_writes_nothing_when_no_plans(self, tmp_path: Path) -> None:
        result = ExecutionResult(decision=StepDecision(False, False, 1, "x", ()))
        spec = tmp_path / "spec.md"
        gen = tmp_path / "pkg" / "_generated.py"
        written = apply_result(result, spec_path=spec, generated_path=gen)
        assert written == ()
        assert not spec.exists()
        assert not gen.exists()


# ---------------------------------------------------------------------------
# Renderers — terminal display formatting
# ---------------------------------------------------------------------------


class TestRenderers:
    def test_render_decision_includes_case_label(self) -> None:
        d = StepDecision(True, True, 2, "case 2: intent changed", ())
        rendered = render_decision(d)
        assert "case 2" in rendered
        assert "STEP 1" in rendered
        assert "STEP 2" in rendered

    def test_render_decision_shows_conflicts(self) -> None:
        d = StepDecision(False, False, 8, "case 8", ("full divergence",))
        rendered = render_decision(d)
        assert "full divergence" in rendered

    def test_render_decision_for_clean_state(self) -> None:
        d = StepDecision(False, False, 1, "case 1: clean", ())
        rendered = render_decision(d)
        assert "nothing" in rendered

    def test_render_spec_plan_includes_summary(self) -> None:
        p = SpecPlan(
            reasoning="r",
            summary="add User",
            spec_md_after="# very long spec content " * 20,
        )
        rendered = render_spec_plan(p)
        assert "add User" in rendered
        # Full content NOT in rendered output (we just count bytes).
        assert "spec.md:" in rendered
        assert "bytes" in rendered

    def test_render_python_plan_includes_summary(self) -> None:
        p = PythonPlan(
            reasoning="r",
            summary="generate User struct",
            generated_py_after="x = 1\n",
        )
        rendered = render_python_plan(p)
        assert "generate User struct" in rendered
