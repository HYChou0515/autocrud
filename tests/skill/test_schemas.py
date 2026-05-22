"""Tests for the LLM-output Pydantic schemas."""

from __future__ import annotations

from specstar.skill.schemas import (
    BreakingChange,
    FieldChange,
    InferredDecision,
    PythonPlan,
    ResourceChange,
    SpecPlan,
)


class TestSpecPlan:
    def test_minimal_construction(self) -> None:
        plan = SpecPlan(
            reasoning="thought process",
            summary="summary",
            spec_md_after="# spec\n",
        )
        assert plan.reasoning == "thought process"
        assert plan.spec_md_after == "# spec\n"
        assert plan.resources == []
        assert plan.inferred_decisions == []
        assert plan.breaking_changes == []

    def test_with_resources(self) -> None:
        plan = SpecPlan(
            reasoning="r",
            summary="s",
            spec_md_after="x",
            resources=[
                ResourceChange(
                    resource="User",
                    kind="added",
                    field_changes=[
                        FieldChange(
                            resource="User",
                            field="name",
                            kind="added",
                            detail="str",
                        )
                    ],
                )
            ],
        )
        assert plan.resources[0].field_changes[0].field == "name"

    def test_reasoning_is_first_field_in_schema(self) -> None:
        # CoT scratchpad ordering: reasoning must be the first field so JSON
        # schemas emit it before subsequent structured fields. This lets the
        # LLM think before committing to its answer.
        keys = list(SpecPlan.model_json_schema()["properties"].keys())
        assert keys[0] == "reasoning"

    def test_spec_md_after_is_required(self) -> None:
        required = SpecPlan.model_json_schema().get("required", [])
        assert "spec_md_after" in required


class TestPythonPlan:
    def test_minimal_construction(self) -> None:
        plan = PythonPlan(
            reasoning="r",
            summary="s",
            generated_py_after="x = 1\n",
        )
        assert plan.generated_py_after == "x = 1\n"

    def test_reasoning_is_first(self) -> None:
        keys = list(PythonPlan.model_json_schema()["properties"].keys())
        assert keys[0] == "reasoning"

    def test_no_spec_md_after_field(self) -> None:
        # STEP 2 must not be allowed to modify spec.md — the schema
        # structurally enforces this by simply not having a spec_md_after
        # field.
        keys = set(PythonPlan.model_json_schema()["properties"].keys())
        assert "spec_md_after" not in keys


class TestBreakingChange:
    def test_required_fields(self) -> None:
        bc = BreakingChange(
            description="rename email",
            suggested_migration="declarative_rename",
        )
        assert bc.migration_prose == ""

    def test_with_prose(self) -> None:
        bc = BreakingChange(
            description="split name",
            suggested_migration="scaffolded_python",
            migration_prose="See migrations/split_name.py",
        )
        assert "split_name" in bc.migration_prose


class TestInferredDecision:
    def test_all_fields_required(self) -> None:
        d = InferredDecision(
            target="User.permissions.delete",
            chosen_value="admin",
            reason="default for sensitive resources",
        )
        assert d.target == "User.permissions.delete"
