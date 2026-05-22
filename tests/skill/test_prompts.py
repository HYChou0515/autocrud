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

    def test_defaults_section_documented(self) -> None:
        # Phase 2.5: STEP 1 lists ### Defaults as an optional section.
        assert "### Defaults" in STEP1_SYSTEM_PROMPT

    def test_indexes_section_documented(self) -> None:
        # Phase 2.2: STEP 1 must mention the new ### Indexes section
        # so prose like "we'll often search by email" gets normalized
        # to a deterministic bullet list.
        assert "### Indexes" in STEP1_SYSTEM_PROMPT

    def test_project_section_documented(self) -> None:
        # Phase 3.3: STEP 1 lists a top-level ## Project block for
        # project-wide scalars (model_naming, admin, etc.).
        assert "## Project" in STEP1_SYSTEM_PROMPT

    def test_permission_token_vocabulary_documented(self) -> None:
        # Phase 3.1: STEP 1 must normalize free permission prose
        # ("any logged-in user") into one of the 5 built-in tokens
        # (or custom:<dotted>). Each token must appear in the prompt
        # so the LLM has a deterministic target vocabulary.
        for token in (
            "public",
            "authenticated",
            "admin",
            "owner",
            "denied",
        ):
            assert token in STEP1_SYSTEM_PROMPT, (
                f"STEP 1 prompt must list permission token {token!r}"
            )
        # Custom escape must be documented too.
        assert "custom:" in STEP1_SYSTEM_PROMPT

    def test_workflows_micro_syntax_requires_phase_action_dotted_ref(self) -> None:
        # Phase 2.1: STEP 1 must teach how to normalize free workflow
        # prose into bullets STEP 2 can deterministically translate.
        # Each ``### Workflows`` bullet should declare phase
        # (before/after/on_success/on_failure), action (create/update/
        # delete/...), and a dotted string reference to user logic.
        wf_section = STEP1_SYSTEM_PROMPT
        # Mentions all four phases.
        for phase in ("before", "after", "on_success", "on_failure"):
            assert phase in wf_section, (
                f"STEP 1 prompt must mention workflow phase {phase!r}"
            )
        # Names the dotted string-reference convention explicitly.
        assert "my_app.logic." in wf_section, (
            "STEP 1 prompt must show the dotted string-ref shape so "
            "the LLM normalizes intent.md prose into a machine-readable form"
        )


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

    def test_includes_concrete_add_model_example_with_kwargs(self) -> None:
        # Without a worked example, the LLM hallucinates kwargs that don't
        # exist (e.g. `permissions={"read": "any auth"}`). The prompt must
        # show a real, copy-pasteable spec.add_model() call so the LLM has
        # ground truth instead of guessing.
        # Pattern: spec.add_model(SomeClass, name="...") — a structural
        # signature, not just the bare phrase "spec.add_model(...) calls".
        import re

        assert re.search(
            r"spec\.add_model\(\s*\w+\s*,\s*name=",
            STEP2_SYSTEM_PROMPT,
        ), "prompt must contain a real spec.add_model(<Class>, name=...) example"

    def test_teaches_real_permission_checker_kwarg_not_hallucinated(self) -> None:
        # The bug we hit: LLM emitted spec.add_model(..., permissions={...})
        # which raises TypeError because no such kwarg exists. The real API
        # uses permission_checker= (taking an IPermissionChecker instance).
        # The prompt must (a) mention the real kwarg with an example and
        # (b) explicitly forbid the hallucinated permissions= form.
        assert "permission_checker=" in STEP2_SYSTEM_PROMPT, (
            "must mention the real `permission_checker=` kwarg"
        )
        assert "`permissions=`" in STEP2_SYSTEM_PROMPT or (
            "permissions=" in STEP2_SYSTEM_PROMPT
            and "does not exist" in STEP2_SYSTEM_PROMPT.lower()
        ), "must explicitly call out that `permissions=` is hallucinated and forbidden"

    def test_includes_schema_example_with_required_version(self) -> None:
        # Bug we hit: LLM emitted `Schema(Book)` and the import raised
        # `TypeError: Schema.__init__() missing 1 required positional
        # argument: 'version'`. The prompt must show a real
        # `Schema(<Class>, "<version>")` call so the LLM doesn't drop
        # the version arg.
        import re

        assert re.search(
            r"Schema\(\s*\w+\s*,\s*['\"]\w+['\"]",
            STEP2_SYSTEM_PROMPT,
        ), (
            'prompt must contain a real Schema(<Class>, "<version>") '
            "example so the LLM doesn't drop the required `version` arg"
        )

    def test_includes_defaults_example_with_default_status(self) -> None:
        # Phase 2.5: ### Defaults bullets translate to default_status=
        # / default_user= kwargs. Anchor on the explicit RevisionStatus
        # enum value LLM should reach for.
        assert "default_status=RevisionStatus." in STEP2_SYSTEM_PROMPT

    def test_includes_encoding_example(self) -> None:
        # Phase 2.6: ### Defaults > encoding: msgpack translates to
        # ``encoding=Encoding.msgpack``.
        assert "encoding=Encoding." in STEP2_SYSTEM_PROMPT

    def test_includes_id_generator_example_with_string_ref(self) -> None:
        # Phase 2.7: id_generator is a callable; LLM must wrap a
        # dotted ref via ``specstar.string_ref(...)`` rather than
        # importing user code directly.
        assert "id_generator=specstar.string_ref(" in STEP2_SYSTEM_PROMPT

    def test_includes_default_now_uuid4_builtins(self) -> None:
        # Phase 3.5: ship batteries-included defaults so common cases
        # (UTC timestamps, UUID ids) don't need user code.
        assert "specstar.defaults.utcnow" in STEP2_SYSTEM_PROMPT
        assert "specstar.defaults.now(" in STEP2_SYSTEM_PROMPT
        assert "specstar.id_generators.uuid4" in STEP2_SYSTEM_PROMPT

    def test_includes_storage_example_with_backend_config(self) -> None:
        # Phase 2.8: ### Storage drives a top-of-file
        # spec.configure(backend=BackendConfig(...)) call.
        assert "spec.configure(" in STEP2_SYSTEM_PROMPT
        assert "BackendConfig(" in STEP2_SYSTEM_PROMPT
        assert "ConnectionProfile(" in STEP2_SYSTEM_PROMPT
        # And must show specstar.env() for the DSN.
        assert 'specstar.env("' in STEP2_SYSTEM_PROMPT

    def test_includes_mq_example_with_backend_binding(self) -> None:
        # Phase 2.9: ### Message queue extends spec.configure with
        # mq=BackendBinding(type="simple_mq" | "rabbitmq", options=...).
        assert "### Message queue" in STEP2_SYSTEM_PROMPT
        assert "mq=BackendBinding(" in STEP2_SYSTEM_PROMPT

    def test_includes_blob_example_with_backend_binding(self) -> None:
        # Phase 2.10: ### Blob extends spec.configure with
        # blob=BackendBinding(type="memory" | "disk" | "s3", options=...).
        assert "### Blob" in STEP2_SYSTEM_PROMPT
        assert "blob=BackendBinding(" in STEP2_SYSTEM_PROMPT

    def test_includes_graphql_cors_documented_as_init_py_concern(self) -> None:
        # Phase 3.4: GraphQL + CORS both touch the FastAPI app layer
        # (require external deps / middleware order). The prompt must
        # acknowledge them but instruct the LLM to emit comments only,
        # not real imports, so lock+verify works without strawberry-
        # graphql installed.
        assert (
            "## Project: graphql" in STEP2_SYSTEM_PROMPT
            or "graphql" in STEP2_SYSTEM_PROMPT.lower()
        )
        assert "CORS" in STEP2_SYSTEM_PROMPT or "cors" in STEP2_SYSTEM_PROMPT.lower()
        # Should be in __init__.py, not _generated.py.
        assert "__init__.py" in STEP2_SYSTEM_PROMPT

    def test_includes_project_scalars_example_with_spec_configure(self) -> None:
        # Phase 3.3: ## Project scalars (model_naming, admin,
        # strict_operation_context) lift into the spec.configure(...)
        # call as keyword args.
        assert "model_naming=" in STEP2_SYSTEM_PROMPT
        assert "admin=" in STEP2_SYSTEM_PROMPT
        assert "strict_operation_context=" in STEP2_SYSTEM_PROMPT

    def test_includes_permission_example_with_action_based_checker(self) -> None:
        # Phase 3.1: ### Permissions tokens translate to
        # ActionBasedPermissionChecker.from_dict({ResourceAction.read:
        # any_authenticated, ...}). Anchor the prompt on the dict
        # shape so the LLM produces deterministic code.
        assert "ActionBasedPermissionChecker.from_dict(" in STEP2_SYSTEM_PROMPT
        # Built-in tokens must be referenced as Python symbols.
        for symbol in ("any_user", "any_authenticated", "admin_only", "owner_self"):
            assert symbol in STEP2_SYSTEM_PROMPT, (
                f"prompt must reference built-in CheckFunc {symbol!r}"
            )

    def test_includes_validator_example_with_string_ref(self) -> None:
        # Phase 2.11: ### Validation → validator=specstar.string_ref(...).
        # Constraints are deferred — they're called eagerly at add_model
        # time so a lazy string ref would break lock.
        assert "### Validation" in STEP2_SYSTEM_PROMPT
        assert "validator=specstar.string_ref(" in STEP2_SYSTEM_PROMPT

    def test_constraints_translate_to_string_ref_constraint_checker(self) -> None:
        # Phase 3.2: ### Constraints now translates to real code via
        # StringRefConstraintChecker (instances, not factories — works
        # at add_model time without forcing eager import).
        assert "### Constraints" in STEP2_SYSTEM_PROMPT
        assert "StringRefConstraintChecker(" in STEP2_SYSTEM_PROMPT
        assert "constraint_checkers=[" in STEP2_SYSTEM_PROMPT

    def test_includes_indexes_example_with_indexed_fields(self) -> None:
        # Phase 2.2: when "indexes" is enabled, spec.md ### Indexes
        # bullets translate to `indexed_fields=["email", ...]`.
        # The prompt must show this concretely so the LLM doesn't
        # invent its own keyword. Anchor on the worked example that
        # mentions both ### Indexes (the spec.md side) and the
        # indexed_fields= kwarg with a list literal (the code side).
        assert "### Indexes" in STEP2_SYSTEM_PROMPT
        import re

        assert re.search(
            r"indexed_fields=\[",
            STEP2_SYSTEM_PROMPT,
        )

    def test_includes_workflow_example_with_string_ref_event_handler(self) -> None:
        # Phase 2.1: when the "workflows" feature is enabled, the LLM
        # must translate ``### Workflows`` bullets to a real
        # ``event_handlers=[StringRefEventHandler("my_app.logic.X",
        # phase=..., action=...)]`` call. The prompt must show a
        # copy-pasteable example so the LLM doesn't invent its own
        # event-handler API.
        import re

        # Must mention the wrapper class by name (it lives in
        # specstar.events).
        assert "StringRefEventHandler" in STEP2_SYSTEM_PROMPT
        # Must show the concrete call shape, including a dotted ref
        # to a user logic module.
        assert re.search(
            r'StringRefEventHandler\(\s*["\']\w+(?:\.\w+)+["\']',
            STEP2_SYSTEM_PROMPT,
        ), "prompt must show StringRefEventHandler with a dotted string ref"
        # And the phase/action keyword args so the LLM knows what to fill.
        assert "phase=" in STEP2_SYSTEM_PROMPT
        assert "action=ResourceAction." in STEP2_SYSTEM_PROMPT

    def test_referenced_symbols_actually_exist_in_specstar(self) -> None:
        # If the prompt's worked examples reference symbols that don't
        # exist (typo / wishful thinking), the LLM will faithfully
        # reproduce them and the user's _generated.py will ImportError.
        # Anchor every public symbol the prompt mentions to real SpecStar.
        # Note: msgspec is third-party; just verify SpecStar-side names.
        from specstar import Schema, spec  # noqa: F401  (must be importable)
        from specstar.permission import AllowAll, RootOnly  # noqa: F401
        from specstar.types import OnDelete, Ref  # noqa: F401

        # And make sure the prompt actually mentions each so a future
        # rewrite of the prompt that drops one would be caught.
        for symbol in (
            "spec.add_model",
            "Schema",
            "AllowAll",
            "RootOnly",
            "Ref",
            "OnDelete",
        ):
            assert symbol in STEP2_SYSTEM_PROMPT, (
                f"prompt mentions {symbol} but symbol must also be present"
            )


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

    def test_no_error_feedback_section_when_empty(
        self, step2_input: Step2Input
    ) -> None:
        # Default: error_feedback is "" and the user prompt should not
        # mention any "previous attempt failed" framing — that would
        # confuse the LLM on a fresh first call.
        up = build_step2_user_prompt(step2_input)
        assert "previous attempt" not in up.lower()
        assert "error" not in up.lower() or "errors" in up.lower(), (
            "the bare prompt must not introduce an error-feedback frame"
        )

    def test_embeds_error_feedback_when_provided(self) -> None:
        # When the previous LLM output failed at import-time, the caller
        # passes the captured stderr back via Step2Input.error_feedback.
        # The user prompt must surface it under a clear "previous attempt
        # failed" header so the LLM understands what went wrong.
        state = Step2Input(
            spec_md="# my_app\n",
            previous_generated_py="from specstar import spec\n",
            package_name="my_app",
            error_feedback=(
                "TypeError: Schema.__init__() missing 1 required "
                "positional argument: 'version'"
            ),
        )
        up = build_step2_user_prompt(state)
        assert "previous attempt" in up.lower()
        assert "Schema.__init__()" in up
        assert "version" in up

    def test_error_feedback_is_optional_default_empty(self) -> None:
        # Backwards compatibility: existing callers must not need to
        # provide error_feedback.
        state = Step2Input(spec_md="x", previous_generated_py="y", package_name="z")
        assert state.error_feedback == ""

    def test_enabled_features_preamble_listed_in_user_prompt(self) -> None:
        # Tracer for slice B: when the caller specifies enabled
        # features, the user prompt must surface them so the LLM
        # knows which add_model kwargs it is allowed to emit.
        state = Step2Input(
            spec_md="# x\n",
            previous_generated_py="# y\n",
            package_name="my_app",
            enabled_features=("permissions", "schema"),
        )
        up = build_step2_user_prompt(state)
        assert "Enabled features" in up
        assert "permissions" in up
        assert "schema" in up

    def test_no_features_no_preamble(self, step2_input: Step2Input) -> None:
        # Backwards compat: when enabled_features defaults to empty
        # (existing callers), the user prompt must not introduce the
        # preamble — that would force gating semantics on legacy
        # callers and break their flow.
        up = build_step2_user_prompt(step2_input)
        assert "Enabled features" not in up


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
