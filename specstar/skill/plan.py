"""Two-step pipeline orchestration.

Wires together the LLM client (:mod:`specstar.skill.llm`), prompt
builders (:mod:`specstar.skill.prompts`), and Pydantic schemas
(:mod:`specstar.skill.schemas`) into the spec-driven authoring loop.

Design boundaries:

- :func:`decide_steps` — pure function. Given hash-vs-lock booleans for
  the three tracked files, returns which steps to run plus a case label
  and any conflict warnings. **No I/O.**
- :func:`run_step1` / :func:`run_step2` — single LLM call each, returns
  a typed Plan. **Reads from disk; writes nothing.**
- :func:`apply_spec_plan` / :func:`apply_python_plan` — writes the LLM
  output to disk. **Pure file-write.**
- :func:`regenerate` — top-level orchestration. Composes the above.

The CLI (`specstar gen`) is a thin shell that builds the LLMClient from
config, calls `regenerate`, and presents the plans to the user for
confirmation. Tests can pass a mock `LLMClient` to `regenerate` without
touching real APIs.
"""

from __future__ import annotations

from pathlib import Path

from msgspec import Struct

from specstar.skill.llm import LLMClient
from specstar.skill.prompts import (
    STEP1_SYSTEM_PROMPT,
    STEP2_SYSTEM_PROMPT,
    Step1Input,
    Step2Input,
    build_step1_user_prompt,
    build_step2_user_prompt,
)
from specstar.skill.schemas import PythonPlan, SpecPlan

# ---------------------------------------------------------------------------
# Decision: which step(s) to run
# ---------------------------------------------------------------------------


class StepDecision(Struct, frozen=True):
    """Output of :func:`decide_steps`.

    Attributes:
        run_step1: Whether to invoke STEP 1 (intent.md → spec.md).
        run_step2: Whether to invoke STEP 2 (spec.md → _generated.py).
        case: One of 1..8 per the design doc decision table. ``0`` for
            forced runs that don't fit the table.
        case_description: Human-readable label.
        conflicts: Free-form conflict warnings to surface to the user.
            Empty list when there's no ambiguity.
    """

    run_step1: bool
    run_step2: bool
    case: int
    case_description: str
    conflicts: tuple[str, ...] = ()


def decide_steps(
    *,
    intent_changed: bool,
    spec_changed: bool,
    gen_changed: bool,
    force: bool = False,
    from_spec: bool = False,
) -> StepDecision:
    """Pure decision: which steps to run given hash-vs-lock state.

    The ``intent_changed`` / ``spec_changed`` / ``gen_changed`` booleans
    must be precomputed by the caller (typically by hashing the on-disk
    file and comparing to ``manifest.sources[*].sha256``).

    Flags:
        force: Run STEP 1 + STEP 2 unconditionally. Equivalent to
            ``--force`` / ``--from-intent``.
        from_spec: Skip STEP 1, run STEP 2 unconditionally. Equivalent to
            ``--from-spec``. (Cannot combine with ``force``.)
    """
    if force and from_spec:
        raise ValueError("force and from_spec are mutually exclusive")
    if force:
        return StepDecision(True, True, 0, "forced: both steps", ())
    if from_spec:
        return StepDecision(False, True, 0, "forced: from spec", ())

    if not intent_changed and not spec_changed and not gen_changed:
        return StepDecision(False, False, 1, "case 1: clean — nothing to do", ())
    if intent_changed and not spec_changed and not gen_changed:
        return StepDecision(
            True, True, 2, "case 2: intent changed — regenerate both", ()
        )
    if not intent_changed and spec_changed and not gen_changed:
        return StepDecision(
            False,
            True,
            3,
            "case 3: user edited spec.md — only regenerate _generated.py",
            (),
        )
    if not intent_changed and not spec_changed and gen_changed:
        return StepDecision(
            False,
            False,
            4,
            "case 4: user edited _generated.py (SSOT) — refresh lock only",
            (),
        )
    if intent_changed and spec_changed and not gen_changed:
        return StepDecision(
            False,
            True,
            5,
            "case 5: respect user spec.md edits — only regenerate _generated.py",
            ("intent.md changes ignored — user has taken over spec.md",),
        )
    if not intent_changed and spec_changed and gen_changed:
        return StepDecision(
            False,
            False,
            6,
            "case 6: respect user _generated.py edits — refresh lock only",
            ("spec.md edits preserved but not propagated to _generated.py",),
        )
    if intent_changed and not spec_changed and gen_changed:
        return StepDecision(
            True,
            False,
            7,
            "case 7: regenerate spec.md but respect user _generated.py",
            (
                "spec.md will diverge from _generated.py after STEP 1 — "
                "reconcile manually or re-run with --force",
            ),
        )
    # All three changed.
    return StepDecision(
        False,
        False,
        8,
        "case 8: all three layers diverged — refresh lock only",
        ("full divergence — reconcile manually or re-run with --force",),
    )


# ---------------------------------------------------------------------------
# LLM step invocations
# ---------------------------------------------------------------------------


def run_step1(
    client: LLMClient,
    *,
    intent_md: str,
    previous_spec_md: str,
    package_name: str,
) -> SpecPlan:
    """Invoke STEP 1: intent.md → SpecPlan."""
    state = Step1Input(
        intent_md=intent_md,
        previous_spec_md=previous_spec_md,
        package_name=package_name,
    )
    return client.call(
        system=STEP1_SYSTEM_PROMPT,
        user=build_step1_user_prompt(state),
        response_model=SpecPlan,
    )


def run_step2(
    client: LLMClient,
    *,
    spec_md: str,
    previous_generated_py: str,
    package_name: str,
    error_feedback: str = "",
    enabled_features: tuple[str, ...] = (),
) -> PythonPlan:
    """Invoke STEP 2: spec.md → PythonPlan.

    ``error_feedback`` is captured stderr from a previous failed import
    of an LLM-generated _generated.py. When non-empty, it is embedded in
    the user prompt under a 'previous attempt failed' header so the LLM
    can see the runtime error and self-correct.

    ``enabled_features`` lists the feature toggles in effect for this
    gen run (typically the result of
    :func:`specstar.skill.features.resolve_features`). Empty tuple means
    "no gating" — the LLM falls back to its full pre-toggle behavior.
    """
    state = Step2Input(
        spec_md=spec_md,
        previous_generated_py=previous_generated_py,
        package_name=package_name,
        error_feedback=error_feedback,
        enabled_features=enabled_features,
    )
    return client.call(
        system=STEP2_SYSTEM_PROMPT,
        user=build_step2_user_prompt(state),
        response_model=PythonPlan,
    )


# ---------------------------------------------------------------------------
# File apply
# ---------------------------------------------------------------------------


def apply_spec_plan(plan: SpecPlan, spec_path: Path) -> None:
    """Write ``plan.spec_md_after`` to ``spec_path``."""
    spec_path.write_text(plan.spec_md_after, encoding="utf-8")


def apply_python_plan(plan: PythonPlan, generated_path: Path) -> None:
    """Write ``plan.generated_py_after`` to ``generated_path``."""
    generated_path.parent.mkdir(parents=True, exist_ok=True)
    generated_path.write_text(plan.generated_py_after, encoding="utf-8")


# ---------------------------------------------------------------------------
# Result + top-level orchestration
# ---------------------------------------------------------------------------


class ExecutionResult(Struct, frozen=True):
    """Outcome of :func:`execute_plan`.

    Attributes:
        decision: The :class:`StepDecision` that drove this execution.
        spec_plan: STEP 1 output, or ``None`` if STEP 1 was skipped.
        python_plan: STEP 2 output, or ``None`` if STEP 2 was skipped.
        files_written: Project-relative paths actually written. Empty if
            both steps were skipped (or if the user declined apply).
    """

    decision: StepDecision
    spec_plan: SpecPlan | None = None
    python_plan: PythonPlan | None = None
    files_written: tuple[str, ...] = ()


def execute_plan(
    *,
    decision: StepDecision,
    client: LLMClient,
    intent_path: Path,
    spec_path: Path,
    generated_path: Path,
    package_name: str,
    enabled_features: tuple[str, ...] = (),
) -> ExecutionResult:
    """Run whichever steps the decision says to run. Does not write files.

    Returns plans for the caller to present to the user. The caller is
    responsible for invoking :func:`apply_spec_plan` /
    :func:`apply_python_plan` after user confirmation.

    ``enabled_features`` is the resolved feature toggle list (typically
    from :func:`specstar.skill.features.resolve_features`). Threaded
    through to STEP 2 so the LLM sees which kwargs it may emit.
    """
    spec_plan: SpecPlan | None = None
    python_plan: PythonPlan | None = None

    if decision.run_step1:
        intent_md = intent_path.read_text(encoding="utf-8")
        previous_spec_md = (
            spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""
        )
        spec_plan = run_step1(
            client,
            intent_md=intent_md,
            previous_spec_md=previous_spec_md,
            package_name=package_name,
        )

    if decision.run_step2:
        # If STEP 1 just ran, use its proposed spec.md content; else use
        # whatever's currently on disk (the user-edited version).
        if spec_plan is not None:
            spec_md = spec_plan.spec_md_after
        else:
            spec_md = spec_path.read_text(encoding="utf-8")
        previous_generated_py = (
            generated_path.read_text(encoding="utf-8")
            if generated_path.exists()
            else ""
        )
        python_plan = run_step2(
            client,
            spec_md=spec_md,
            previous_generated_py=previous_generated_py,
            package_name=package_name,
            enabled_features=enabled_features,
        )

    return ExecutionResult(
        decision=decision,
        spec_plan=spec_plan,
        python_plan=python_plan,
    )


def apply_result(
    result: ExecutionResult,
    *,
    spec_path: Path,
    generated_path: Path,
) -> tuple[str, ...]:
    """Write any plans in ``result`` to disk. Returns paths actually written.

    Idempotent given the same ``ExecutionResult`` — calling twice writes
    the same content to the same paths.
    """
    written: list[str] = []
    if result.spec_plan is not None:
        apply_spec_plan(result.spec_plan, spec_path)
        written.append(str(spec_path))
    if result.python_plan is not None:
        apply_python_plan(result.python_plan, generated_path)
        written.append(str(generated_path))
    return tuple(written)


# ---------------------------------------------------------------------------
# Plan rendering for terminal display
# ---------------------------------------------------------------------------


def render_decision(decision: StepDecision) -> str:
    """Format the decision header for display."""
    lines = [f"sync state: {decision.case_description}"]
    if decision.conflicts:
        lines.append("conflicts:")
        for c in decision.conflicts:
            lines.append(f"  ! {c}")
    if decision.run_step1 or decision.run_step2:
        steps = []
        if decision.run_step1:
            steps.append("STEP 1 (intent.md → spec.md)")
        if decision.run_step2:
            steps.append("STEP 2 (spec.md → _generated.py)")
        lines.append("will run: " + ", ".join(steps))
    else:
        lines.append("will run: nothing — refresh lock only")
    return "\n".join(lines)


def render_spec_plan(plan: SpecPlan) -> str:
    """Format a SpecPlan for terminal display (without dumping the full
    spec_md_after — that's saved to disk on apply)."""
    lines = ["", "=== STEP 1 plan: intent → spec ===", "", f"summary: {plan.summary}"]
    if plan.resources:
        lines.append("")
        lines.append("resources:")
        for r in plan.resources:
            lines.append(f"  {r.kind}: {r.resource}")
            for fc in r.field_changes:
                lines.append(f"    {fc.kind}: {fc.field} — {fc.detail}")
    if plan.inferred_decisions:
        lines.append("")
        lines.append("inferred decisions:")
        for d in plan.inferred_decisions:
            lines.append(f"  - {d.target} = {d.chosen_value} ({d.reason})")
    if plan.breaking_changes:
        lines.append("")
        lines.append("BREAKING CHANGES:")
        for bc in plan.breaking_changes:
            lines.append(f"  ! {bc.description} → {bc.suggested_migration}")
    lines.append("")
    lines.append(f"new spec.md: {len(plan.spec_md_after)} bytes")
    return "\n".join(lines)


def render_python_plan(plan: PythonPlan) -> str:
    """Format a PythonPlan for terminal display."""
    lines = ["", "=== STEP 2 plan: spec → python ===", "", f"summary: {plan.summary}"]
    if plan.inferred_decisions:
        lines.append("")
        lines.append("inferred decisions (during Python translation):")
        for d in plan.inferred_decisions:
            lines.append(f"  - {d.target} = {d.chosen_value} ({d.reason})")
    lines.append("")
    lines.append(f"new _generated.py: {len(plan.generated_py_after)} bytes")
    return "\n".join(lines)
