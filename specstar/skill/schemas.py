"""Pydantic schemas for LLM-generated plans.

Two schemas because the spec-driven pipeline runs two LLM steps with
different shapes:

- **STEP 1** (``intent.md`` → ``spec.md``): produces a :class:`SpecPlan`.
  Output includes the full new ``spec.md`` content.
- **STEP 2** (``spec.md`` → ``_generated.py``): produces a :class:`PythonPlan`.
  Output includes the full new ``_generated.py`` content.

Both schemas have a leading ``reasoning`` field so the LLM produces its
chain-of-thought *before* the structured payload (CoT scratchpad pattern).
JSON serialization order follows declaration order, so the LLM is forced
to think first.

These are the **contract** for SpecStar's LLM calls — the underlying
transport (litellm, instructor, raw SDK, ...) is interchangeable as long
as the output validates against these.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class FieldChange(BaseModel):
    """A single field-level change for the human-facing summary.

    Attributes:
        resource: The resource model name (e.g. ``"User"``).
        field: The field name (e.g. ``"email"``).
        kind: Change kind: ``"added"``, ``"renamed"``, ``"type_changed"``,
            ``"constraint_changed"``, or ``"dropped"``.
        detail: Human-readable description of the change.
    """

    resource: str
    field: str
    kind: str
    detail: str


class ResourceChange(BaseModel):
    """A resource-level change with optional field-level breakdown."""

    resource: str
    kind: str
    """``"added"``, ``"modified"``, ``"renamed"``, or ``"dropped"``."""
    field_changes: list[FieldChange] = Field(default_factory=list)


class InferredDecision(BaseModel):
    """A decision the LLM filled in without explicit user instruction.

    Per the design rules, every inferred decision must be surfaced for
    confirmation; this struct is what the user sees in the plan summary.
    """

    target: str
    """Path to the decision point, e.g. ``"User.permissions.delete"``."""

    chosen_value: str
    """The value the LLM picked, e.g. ``"role(admin)"``."""

    reason: str
    """Human-readable explanation."""


class BreakingChange(BaseModel):
    """A schema change that requires a data migration.

    The LLM declares breaking changes itself by comparing the new spec
    against the previous spec.md content provided in the prompt. SpecStar
    does not auto-detect — the LLM's judgment + user confirmation is the
    safety boundary.
    """

    description: str
    """One-line summary, e.g. ``"renamed User.email → User.email_address"``."""

    suggested_migration: str
    """``"declarative_rename"``, ``"scaffolded_python"``, or ``"no_versioning"``."""

    migration_prose: str = ""
    """Optional human-readable migration story to embed in spec.md."""


class SpecPlan(BaseModel):
    """STEP 1 output: ``intent.md`` translated into a structured ``spec.md``.

    The LLM is allowed to rewrite the entire ``spec.md`` — that is the
    expected behavior for STEP 1. SpecStar's edit-respect logic is what
    decides *whether* to invoke STEP 1 (it skips if the user manually
    edited ``spec.md``).
    """

    reasoning: str
    """Chain-of-thought scratchpad. **Must be the first field** so JSON
    schemas emit it before subsequent fields, letting the LLM think before
    committing to its structured output."""

    summary: str
    """One-paragraph human-readable summary of the change."""

    resources: list[ResourceChange] = Field(default_factory=list)
    inferred_decisions: list[InferredDecision] = Field(default_factory=list)
    breaking_changes: list[BreakingChange] = Field(default_factory=list)

    spec_md_after: str
    """Complete new contents of ``spec.md``."""


class PythonPlan(BaseModel):
    """STEP 2 output: ``spec.md`` translated into ``_generated.py``.

    The LLM **may not** modify ``spec.md`` in this step — that's why the
    schema has no ``spec_md_after`` field. SpecStar's prompt makes this
    constraint explicit; the schema enforces it structurally.
    """

    reasoning: str
    """Chain-of-thought scratchpad. **Must be the first field**."""

    summary: str
    """One-paragraph human-readable summary."""

    inferred_decisions: list[InferredDecision] = Field(default_factory=list)
    """Decisions filled in during the Python translation (e.g. import order
    when the spec doesn't specify, helper names, etc.)."""

    generated_py_after: str
    """Complete new contents of ``<package>/_generated.py``."""
