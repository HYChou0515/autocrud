"""Tests for ``specstar gen`` — dry-run prompts + --call orchestration."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from specstar.cli import main as cli_main
from specstar.cli._gen import run_gen
from specstar.cli._init import run_init
from specstar.skill.schemas import PythonPlan, SpecPlan


@pytest.fixture()
def starter_project(tmp_path: Path) -> Path:
    out = io.StringIO()
    err = io.StringIO()
    rc = run_init(
        package="my_app",
        root=tmp_path,
        force=False,
        write_lock=True,
        stream=out,
        error_stream=err,
    )
    assert rc == 0, err.getvalue()
    # `specstar init` now scaffolds intent.md automatically; replace the
    # default with a more recognisable string for assertions below.
    (tmp_path / "intent.md").write_text(
        "# my_app intent\n\nWe have users.\n", encoding="utf-8"
    )
    return tmp_path


def _gen(project: Path, **kwargs) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    cwd = Path.cwd()
    import os

    os.chdir(project)
    try:
        rc = run_gen(
            step=kwargs.pop("step", 1),
            package=kwargs.pop("package", None),
            intent_path=Path(kwargs.pop("intent_path", "intent.md")),
            spec_path=Path(kwargs.pop("spec_path", "spec.md")),
            generated_path=kwargs.pop("generated_path", None),
            lock_path=Path(kwargs.pop("lock_path", "spec.lock.json")),
            output_format=kwargs.pop("output_format", "text"),
            stream=out,
            error_stream=err,
        )
    finally:
        os.chdir(cwd)
    return rc, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# Step 1
# ---------------------------------------------------------------------------


class TestStep1:
    def test_prints_step1_label(self, starter_project: Path) -> None:
        rc, out, _ = _gen(starter_project, step=1)
        assert rc == 0
        assert "STEP 1" in out

    def test_includes_intent_md_content(self, starter_project: Path) -> None:
        rc, out, _ = _gen(starter_project, step=1)
        assert rc == 0
        assert "We have users." in out

    def test_includes_previous_spec_md(self, starter_project: Path) -> None:
        spec_content = (starter_project / "spec.md").read_text()
        rc, out, _ = _gen(starter_project, step=1)
        assert rc == 0
        assert spec_content in out

    def test_system_section_describes_beta_protocol(
        self, starter_project: Path
    ) -> None:
        rc, out, _ = _gen(starter_project, step=1)
        assert rc == 0
        assert "β heading protocol" in out

    def test_dry_run_disclaimer(self, starter_project: Path) -> None:
        rc, out, _ = _gen(starter_project, step=1)
        assert "dry-run" in out


# ---------------------------------------------------------------------------
# Step 2
# ---------------------------------------------------------------------------


class TestStep2:
    def test_prints_step2_label(self, starter_project: Path) -> None:
        rc, out, _ = _gen(starter_project, step=2)
        assert rc == 0
        assert "STEP 2" in out

    def test_includes_spec_md(self, starter_project: Path) -> None:
        spec_content = (starter_project / "spec.md").read_text()
        rc, out, _ = _gen(starter_project, step=2)
        assert rc == 0
        assert spec_content in out

    def test_includes_previous_generated_py(self, starter_project: Path) -> None:
        gen_content = (starter_project / "my_app" / "_generated.py").read_text()
        rc, out, _ = _gen(starter_project, step=2)
        assert rc == 0
        assert gen_content in out

    def test_system_section_lists_blocked_imports(self, starter_project: Path) -> None:
        rc, out, _ = _gen(starter_project, step=2)
        assert rc == 0
        # AST allow/block list lives in step 2's system prompt.
        for module in ["os", "subprocess", "requests"]:
            assert module in out


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------


class TestJsonOutput:
    def test_step1_json(self, starter_project: Path) -> None:
        rc, out, _ = _gen(starter_project, step=1, output_format="json")
        assert rc == 0
        payload = json.loads(out)
        assert payload["step"] == 1
        assert "system" in payload
        assert isinstance(payload["messages"], list)
        assert payload["messages"][0]["role"] == "user"

    def test_step2_json(self, starter_project: Path) -> None:
        rc, out, _ = _gen(starter_project, step=2, output_format="json")
        assert rc == 0
        payload = json.loads(out)
        assert payload["step"] == 2


# ---------------------------------------------------------------------------
# Auto-detection
# ---------------------------------------------------------------------------


class TestAutoDetection:
    def test_package_auto_detected_from_lock(self, starter_project: Path) -> None:
        # No --package; should pick up "my_app" from spec.lock.json
        rc, out, _ = _gen(starter_project, step=2)
        assert rc == 0
        assert "my_app/_generated.py" in out


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TestErrors:
    def test_missing_intent_returns_two(self, tmp_path: Path) -> None:
        (tmp_path / "spec.md").write_text("# x\n", encoding="utf-8")
        out = io.StringIO()
        err = io.StringIO()
        rc = run_gen(
            step=1,
            package="my_app",
            intent_path=tmp_path / "intent.md",
            spec_path=tmp_path / "spec.md",
            generated_path=tmp_path / "gen.py",
            lock_path=tmp_path / "spec.lock.json",
            output_format="text",
            stream=out,
            error_stream=err,
        )
        assert rc == 2
        assert "intent file not found" in err.getvalue()

    def test_missing_spec_step2_returns_two(self, tmp_path: Path) -> None:
        out = io.StringIO()
        err = io.StringIO()
        rc = run_gen(
            step=2,
            package="my_app",
            intent_path=tmp_path / "intent.md",
            spec_path=tmp_path / "spec.md",
            generated_path=tmp_path / "gen.py",
            lock_path=tmp_path / "spec.lock.json",
            output_format="text",
            stream=out,
            error_stream=err,
        )
        assert rc == 2
        assert "spec file not found" in err.getvalue()

    def test_no_package_no_lock_returns_two(self, tmp_path: Path) -> None:
        (tmp_path / "intent.md").write_text("hi\n", encoding="utf-8")
        out = io.StringIO()
        err = io.StringIO()
        rc = run_gen(
            step=1,
            package=None,
            intent_path=tmp_path / "intent.md",
            spec_path=tmp_path / "spec.md",
            generated_path=None,
            lock_path=tmp_path / "spec.lock.json",
            output_format="text",
            stream=out,
            error_stream=err,
        )
        assert rc == 2
        assert "--package is required" in err.getvalue()


# ---------------------------------------------------------------------------
# CLI dispatch
# ---------------------------------------------------------------------------


class TestCliDispatch:
    def test_gen_appears_in_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cli_main([])
        captured = capsys.readouterr()
        assert rc == 0
        assert "gen" in captured.out

    def test_gen_via_main(
        self, starter_project: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(starter_project)
        rc = cli_main(["gen", "--step", "1"])
        assert rc == 0


# ---------------------------------------------------------------------------
# --call mode (real LLM orchestration with mock client)
# ---------------------------------------------------------------------------


_GENERATED_PY_BODY = '''\
"""GENERATED."""

from __future__ import annotations

import msgspec

from specstar import spec


class User(msgspec.Struct):
    name: str
    email: str


spec.add_model(User, name="user")
'''


class _MockClient:
    """Mock LLMClient for --call tests. Returns canned plans."""

    def __init__(
        self,
        *,
        spec_md_after: str | None = None,
        generated_py_after: str | None = None,
    ):
        self._spec_md_after = spec_md_after
        self._generated_py_after = generated_py_after or _GENERATED_PY_BODY
        self.calls: list[type] = []
        self.user_prompts: list[str] = []

    def call(self, *, system, user, response_model):
        self.calls.append(response_model)
        self.user_prompts.append(user)
        if response_model is SpecPlan:
            return SpecPlan(
                reasoning="r",
                summary="add Tag",
                spec_md_after=self._spec_md_after
                or (
                    "<!-- GENERATED -->\n"
                    "# my_app\n\n"
                    "## Resource: User\n\n"
                    "### Fields\n"
                    "- `name`: str\n"
                    "- `email`: str\n"
                ),
            )
        if response_model is PythonPlan:
            return PythonPlan(
                reasoning="r",
                summary="generate User",
                generated_py_after=self._generated_py_after,
            )
        raise RuntimeError(f"unexpected: {response_model}")


def _call(project: Path, **kwargs) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    cwd = Path.cwd()
    import os

    os.chdir(project)
    try:
        rc = run_gen(
            call=True,
            package=kwargs.pop("package", None),
            intent_path=Path(kwargs.pop("intent_path", "intent.md")),
            spec_path=Path(kwargs.pop("spec_path", "spec.md")),
            generated_path=kwargs.pop("generated_path", None),
            lock_path=Path(kwargs.pop("lock_path", "spec.lock.json")),
            yes=kwargs.pop("yes", True),
            force=kwargs.pop("force", False),
            from_spec=kwargs.pop("from_spec", False),
            feedback_retries=kwargs.pop("feedback_retries", 0),
            cli_enable_features=kwargs.pop("cli_enable_features", []),
            cli_disable_features=kwargs.pop("cli_disable_features", []),
            client=kwargs.pop("client", None),
            confirm=kwargs.pop("confirm", None),
            env=kwargs.pop("env", None),
            stream=out,
            error_stream=err,
        )
    finally:
        os.chdir(cwd)
    return rc, out.getvalue(), err.getvalue()


@pytest.fixture()
def pristine_project(tmp_path: Path) -> Path:
    """A starter project where no file has been modified post-init.

    Hashes match the lock exactly → case 1. Different from
    ``starter_project`` (which intentionally overwrites intent.md to
    create a recognisable assertion target for dry-run tests).
    """
    out = io.StringIO()
    err = io.StringIO()
    rc = run_init(
        package="my_app",
        root=tmp_path,
        force=False,
        write_lock=True,
        stream=out,
        error_stream=err,
    )
    assert rc == 0
    return tmp_path


class TestCallCase1Clean:
    def test_clean_state_skips_llm_and_refreshes_lock(
        self, pristine_project: Path
    ) -> None:
        client = _MockClient()
        rc, out, _ = _call(pristine_project, client=client)
        assert rc == 0
        assert client.calls == []  # no LLM invocation
        assert "case 1" in out


class TestCallCase2BothSteps:
    @pytest.fixture()
    def edited_intent(self, starter_project: Path) -> Path:
        # Edit intent.md to flip case 1 → case 2.
        (starter_project / "intent.md").write_text(
            "# my_app intent\n\nWe have users.\nNew change here.\n",
            encoding="utf-8",
        )
        return starter_project

    def test_runs_both_steps(self, edited_intent: Path) -> None:
        client = _MockClient()
        rc, out, err = _call(edited_intent, client=client)
        assert rc == 0, err
        assert SpecPlan in client.calls
        assert PythonPlan in client.calls
        assert "case 2" in out

    def test_writes_spec_md_and_generated_py(self, edited_intent: Path) -> None:
        client = _MockClient(generated_py_after=_GENERATED_PY_BODY)
        _call(edited_intent, client=client)
        spec_after = (edited_intent / "spec.md").read_text()
        gen_after = (edited_intent / "my_app" / "_generated.py").read_text()
        assert "GENERATED" in spec_after
        assert "User" in gen_after

    def test_aborts_when_confirm_returns_false(self, edited_intent: Path) -> None:
        before_spec = (edited_intent / "spec.md").read_text()
        before_gen = (edited_intent / "my_app" / "_generated.py").read_text()
        client = _MockClient()
        rc, out, _ = _call(
            edited_intent,
            client=client,
            yes=False,
            confirm=lambda _prompt: False,
        )
        assert rc == 1
        assert "aborted" in out
        assert (edited_intent / "spec.md").read_text() == before_spec
        assert (edited_intent / "my_app" / "_generated.py").read_text() == before_gen


class TestCallCase4UserEditedGenerated:
    def test_user_only_edited_gen_skips_both_steps(
        self, pristine_project: Path
    ) -> None:
        # Add a (still declarative) comment to _generated.py so its hash
        # diverges from the lock.
        gen = pristine_project / "my_app" / "_generated.py"
        gen.write_text(gen.read_text() + "# user comment\n", encoding="utf-8")
        client = _MockClient()
        rc, out, _ = _call(pristine_project, client=client)
        assert rc == 0
        assert client.calls == []
        assert "case 4" in out


class TestForceFlag:
    def test_force_runs_both_steps_on_clean(self, pristine_project: Path) -> None:
        client = _MockClient()
        rc, _, _ = _call(pristine_project, client=client, force=True)
        assert rc == 0
        assert SpecPlan in client.calls
        assert PythonPlan in client.calls

    def test_force_and_from_spec_mutually_exclusive(
        self, pristine_project: Path
    ) -> None:
        client = _MockClient()
        rc, _, err = _call(pristine_project, client=client, force=True, from_spec=True)
        assert rc == 2
        assert "mutually exclusive" in err


class TestProviderConfig:
    def test_no_api_key_returns_two(self, starter_project: Path) -> None:
        # Need to actually trigger LLM resolution path. Edit intent so case 2.
        (starter_project / "intent.md").write_text("changed\n", encoding="utf-8")
        rc, _, err = _call(starter_project, client=None, env={})
        assert rc == 2
        assert "API key" in err

    def test_self_host_skips_api_key_check(self, starter_project: Path) -> None:
        (starter_project / "intent.md").write_text("changed\n", encoding="utf-8")

        out = io.StringIO()
        err = io.StringIO()
        cwd = Path.cwd()
        import os

        os.chdir(starter_project)
        try:
            rc = run_gen(
                call=True,
                package=None,
                intent_path=Path("intent.md"),
                spec_path=Path("spec.md"),
                generated_path=None,
                lock_path=Path("spec.lock.json"),
                yes=True,
                provider="openai-compatible",
                model="llama3.1",
                base_url="http://localhost:11434/v1",
                client=_MockClient(),
                env={},
                stream=out,
                error_stream=err,
            )
        finally:
            os.chdir(cwd)
        assert rc == 0, err.getvalue()


class TestCliDispatchCall:
    def test_help_lists_call_flag(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit):
            cli_main(["gen", "--help"])
        captured = capsys.readouterr()
        assert "--call" in captured.out
        assert "--force" in captured.out
        assert "--from-spec" in captured.out


# ---------------------------------------------------------------------------
# Failure recovery: rollback when LLM-generated code breaks
# ---------------------------------------------------------------------------


_BAD_KWARG_GENERATED_PY = '''\
"""GENERATED — but with a hallucinated kwarg."""

from __future__ import annotations

import msgspec

from specstar import spec


class User(msgspec.Struct):
    name: str
    email: str


spec.add_model(User, name="user", permissions={"read": "any"})
'''


class TestRollbackOnBrokenLLMCode:
    """When the LLM produces code that AST-validates but TypeErrors at
    import, gen --call must restore the previous file content rather
    than leave the user with a broken _generated.py.
    """

    @pytest.fixture()
    def edited_intent_pristine(self, pristine_project: Path) -> Path:
        # Edit intent.md so we're in case 2 (LLM call expected).
        (pristine_project / "intent.md").write_text(
            "# my_app intent\n\nA tiny change to trigger STEP 1+2.\n",
            encoding="utf-8",
        )
        return pristine_project

    def test_broken_kwarg_triggers_rollback(self, edited_intent_pristine: Path) -> None:
        gen_path = edited_intent_pristine / "my_app" / "_generated.py"
        spec_path = edited_intent_pristine / "spec.md"
        before_gen = gen_path.read_text()
        before_spec = spec_path.read_text()

        # Mock LLM that emits Python with a hallucinated `permissions=` kwarg.
        client = _MockClient(generated_py_after=_BAD_KWARG_GENERATED_PY)
        rc, out, err = _call(edited_intent_pristine, client=client)

        # Failure must surface non-zero and rollback the files.
        assert rc != 0, "broken LLM code must not return success"
        assert gen_path.read_text() == before_gen, (
            "broken _generated.py must be rolled back to its pre-write content"
        )
        assert spec_path.read_text() == before_spec, (
            "spec.md must also be rolled back when the pipeline fails"
        )

    def test_rollback_message_surfaced_to_user(
        self, edited_intent_pristine: Path
    ) -> None:
        client = _MockClient(generated_py_after=_BAD_KWARG_GENERATED_PY)
        rc, out, err = _call(edited_intent_pristine, client=client)
        assert rc != 0
        # Combined output must mention rollback so the user understands
        # why their working tree was reverted.
        combined = out + err
        assert "roll" in combined.lower() or "revert" in combined.lower()

    def test_rollback_preserves_pre_call_lock(
        self, edited_intent_pristine: Path
    ) -> None:
        from specstar.lockfile import read_manifest

        lock_path = edited_intent_pristine / "spec.lock.json"
        before_lock_bytes = lock_path.read_bytes()

        client = _MockClient(generated_py_after=_BAD_KWARG_GENERATED_PY)
        _call(edited_intent_pristine, client=client)

        # Lock content must not be modified by a failed run.
        assert lock_path.read_bytes() == before_lock_bytes, (
            "lock must not be rewritten when apply+verify fail"
        )
        # And it must still be readable / valid.
        manifest = read_manifest(lock_path)
        assert "intent.md" in manifest.sources


_MALICIOUS_GENERATED_PY = '''\
"""LLM emitted forbidden import — would damage the host if executed."""

from __future__ import annotations

import os  # AST-blocked; would be malicious if it reached subprocess
import msgspec

from specstar import spec


class User(msgspec.Struct):
    name: str


# This code at module top-level executes during subprocess import.
# AST validator must catch the `import os` BEFORE we write the file,
# so the subprocess never gets to load this module at all.
spec.add_model(User, name="user")
'''


class TestAstValidationBeforeWrite:
    """The AST validator must run on the LLM output **before** the file
    is written and **before** the subprocess imports it.

    Why: any malicious / forbidden code at module top-level executes
    during ``import``. Catching it post-write means the damage is done
    by the time the validator runs. Catching it pre-write means the
    user's working tree is never even touched.
    """

    @pytest.fixture()
    def edited_intent_pristine(self, pristine_project: Path) -> Path:
        (pristine_project / "intent.md").write_text(
            "# my_app intent\n\nA tiny change to trigger STEP 1+2.\n",
            encoding="utf-8",
        )
        return pristine_project

    def test_blocked_import_caught_before_write(
        self, edited_intent_pristine: Path
    ) -> None:
        gen_path = edited_intent_pristine / "my_app" / "_generated.py"
        before = gen_path.read_text()

        client = _MockClient(generated_py_after=_MALICIOUS_GENERATED_PY)
        rc, out, err = _call(edited_intent_pristine, client=client)

        assert rc != 0, "blocked import must abort the run"
        # The file content was never touched by this run.
        assert gen_path.read_text() == before, (
            "AST validation must run BEFORE writing — broken file must "
            "never appear on disk"
        )

    def test_blocked_import_message_attributes_to_ast(
        self, edited_intent_pristine: Path
    ) -> None:
        client = _MockClient(generated_py_after=_MALICIOUS_GENERATED_PY)
        rc, _, err = _call(edited_intent_pristine, client=client)
        assert rc != 0
        # Surface the AST validator's specific complaint, not a generic
        # subprocess import failure.
        assert "blocked_import" in err or "ast" in err.lower(), (
            "user must see an AST-attributed error, not a downstream subprocess failure"
        )

    def test_no_write_happens_for_pre_write_failure(
        self, edited_intent_pristine: Path
    ) -> None:
        # Pre-write AST validation means we never execute the apply step.
        # The success message "wrote N file(s):" only fires after a
        # successful apply. If we see it for an AST-rejected plan, then
        # AST ran post-write (and the rollback merely undid the damage).
        # We want pre-write semantics: no write at all, ever.
        client = _MockClient(generated_py_after=_MALICIOUS_GENERATED_PY)
        rc, out, _ = _call(edited_intent_pristine, client=client)
        assert rc != 0
        assert "wrote" not in out, (
            "AST validator must run BEFORE apply; no `wrote N file(s):` "
            "line should appear when LLM output is AST-rejected"
        )

    def test_subprocess_never_runs_for_pre_write_failure(
        self, edited_intent_pristine: Path
    ) -> None:
        # Defense-in-depth: malicious code at module top-level executes
        # during subprocess import. Pre-write AST means the subprocess
        # never runs at all, so any side effects in the malicious code
        # never happen.
        client = _MockClient(generated_py_after=_MALICIOUS_GENERATED_PY)
        _, out, err = _call(edited_intent_pristine, client=client)
        combined = out + err
        assert "failed to import" not in combined, (
            "subprocess must not run when AST validator already rejected the LLM output"
        )


# ---------------------------------------------------------------------------
# Recreate-from-intent: missing or emptied spec.md must run STEP 1
# ---------------------------------------------------------------------------


class TestRecreateSpecFromIntent:
    """When the user removes or empties spec.md, that is a 'recreate from
    intent.md' signal. STEP 1 must run; we must NOT treat this as the
    case-5 'user took over spec' path which would skip STEP 1 and leave
    the user with no spec.md.
    """

    def test_removed_spec_md_triggers_step1(self, pristine_project: Path) -> None:
        (pristine_project / "intent.md").write_text(
            "# my_app intent\n\nA Book resource with title.\n",
            encoding="utf-8",
        )
        (pristine_project / "spec.md").unlink()

        client = _MockClient()
        rc, _, err = _call(pristine_project, client=client)

        assert rc == 0, f"removed spec.md should not error: {err}"
        assert SpecPlan in client.calls, (
            "removed spec.md must trigger STEP 1 (recreate from intent.md), "
            "not skip to STEP 2 like the case-5 'user took over' path"
        )
        # spec.md must exist again after the run.
        assert (pristine_project / "spec.md").exists()

    def test_emptied_spec_md_also_triggers_step1(self, pristine_project: Path) -> None:
        # User cleared spec.md to empty file — strong "recreate" signal.
        (pristine_project / "intent.md").write_text(
            "# my_app intent\n\nA Book resource.\n", encoding="utf-8"
        )
        (pristine_project / "spec.md").write_text("", encoding="utf-8")

        client = _MockClient()
        rc, _, err = _call(pristine_project, client=client)

        assert rc == 0, f"empty spec.md should not error: {err}"
        assert SpecPlan in client.calls, (
            "empty spec.md is a strong 'recreate' signal — STEP 1 must run"
        )


# ---------------------------------------------------------------------------
# Feedback retry loop: re-call STEP 2 with captured stderr on lock failure
# ---------------------------------------------------------------------------


_BAD_SCHEMA_GENERATED_PY = '''\
"""GENERATED — Schema is missing the required version arg."""

from __future__ import annotations

import msgspec

from specstar import Schema, spec


class User(msgspec.Struct):
    name: str


# Hallucinated: Schema(User) without the required `version` positional.
# AST passes (it's a normal call); import raises TypeError.
schema = Schema(User)
spec.add_model(User, name="user", schema=schema)
'''


_GOOD_GENERATED_PY = '''\
"""GENERATED — valid."""

from __future__ import annotations

import msgspec

from specstar import spec


class User(msgspec.Struct):
    name: str


spec.add_model(User, name="user")
'''


class _SequencingMockClient:
    """LLMClient mock that returns a different ``generated_py_after`` per
    PythonPlan call. Used to simulate the LLM self-correcting on retry.
    """

    def __init__(
        self,
        *,
        spec_md_after: str | None = None,
        py_sequence: list[str],
    ):
        self._spec_md_after = spec_md_after
        self._py_sequence = list(py_sequence)
        self._py_idx = 0
        self.calls: list[type] = []
        self.user_prompts: list[str] = []

    def call(self, *, system, user, response_model):
        self.calls.append(response_model)
        self.user_prompts.append(user)
        if response_model is SpecPlan:
            return SpecPlan(
                reasoning="r",
                summary="s",
                spec_md_after=self._spec_md_after
                or (
                    "<!-- GENERATED -->\n"
                    "# my_app\n\n"
                    "## Resource: User\n\n"
                    "### Fields\n"
                    "- `name`: str\n"
                ),
            )
        if response_model is PythonPlan:
            idx = min(self._py_idx, len(self._py_sequence) - 1)
            content = self._py_sequence[idx]
            self._py_idx += 1
            return PythonPlan(
                reasoning="r",
                summary=f"attempt {self._py_idx}",
                generated_py_after=content,
            )
        raise RuntimeError(f"unexpected: {response_model}")


class TestFeedbackRetryLoop:
    """When ``specstar lock`` fails to import the LLM-generated
    ``_generated.py`` (e.g. ``TypeError`` from a hallucinated kwarg or
    a missing positional arg on ``Schema``), gen --call must capture
    that error, feed it back to STEP 2 as additional context, and let
    the LLM self-correct — up to ``feedback_retries`` times.
    """

    @pytest.fixture()
    def edited_intent(self, pristine_project: Path) -> Path:
        (pristine_project / "intent.md").write_text(
            "# my_app intent\n\nA tiny change.\n", encoding="utf-8"
        )
        return pristine_project

    def test_retry_succeeds_on_second_attempt(self, edited_intent: Path) -> None:
        # First STEP 2 emits broken code (Schema missing version).
        # Second STEP 2 emits valid code. Pipeline must end rc=0 with
        # the good code on disk and no rollback.
        gen_path = edited_intent / "my_app" / "_generated.py"
        client = _SequencingMockClient(
            py_sequence=[_BAD_SCHEMA_GENERATED_PY, _GOOD_GENERATED_PY],
        )
        rc, out, err = _call(edited_intent, client=client, feedback_retries=2)
        assert rc == 0, f"retry should succeed; out={out!r} err={err!r}"
        # STEP 2 was called twice — first + retry.
        assert client.calls.count(PythonPlan) == 2
        # Final on-disk content must be the good output.
        assert gen_path.read_text() == _GOOD_GENERATED_PY

    def test_retry_user_prompt_carries_captured_stderr(
        self, edited_intent: Path
    ) -> None:
        client = _SequencingMockClient(
            py_sequence=[_BAD_SCHEMA_GENERATED_PY, _GOOD_GENERATED_PY],
        )
        _call(edited_intent, client=client, feedback_retries=2)
        # Calls in order: SpecPlan, PythonPlan(first), PythonPlan(retry).
        assert client.calls == [SpecPlan, PythonPlan, PythonPlan]
        retry_user_prompt = client.user_prompts[2]
        assert "previous attempt" in retry_user_prompt.lower()
        # The captured stderr should contain the actual TypeError text
        # (or at least the symbol name that triggered it).
        assert "Schema" in retry_user_prompt
        assert "TypeError" in retry_user_prompt or "version" in retry_user_prompt

    def test_retry_budget_exhausted_rolls_back(self, edited_intent: Path) -> None:
        gen_path = edited_intent / "my_app" / "_generated.py"
        before = gen_path.read_text()
        # Every attempt produces broken code.
        client = _SequencingMockClient(
            py_sequence=[_BAD_SCHEMA_GENERATED_PY] * 5,
        )
        rc, out, err = _call(edited_intent, client=client, feedback_retries=2)
        assert rc != 0
        # 1 first attempt + 2 retries = 3 STEP 2 calls.
        assert client.calls.count(PythonPlan) == 3
        # Working tree restored.
        assert gen_path.read_text() == before
        combined = out + err
        assert "roll" in combined.lower(), (
            "exhausted-retries path must still roll back the working tree"
        )

    def test_feedback_retries_zero_disables_retry_loop(
        self, edited_intent: Path
    ) -> None:
        # feedback_retries=0 keeps the legacy behavior: rollback on the
        # first lock failure with no LLM retry.
        gen_path = edited_intent / "my_app" / "_generated.py"
        before = gen_path.read_text()
        client = _SequencingMockClient(
            py_sequence=[_BAD_SCHEMA_GENERATED_PY, _GOOD_GENERATED_PY],
        )
        rc, out, err = _call(edited_intent, client=client, feedback_retries=0)
        assert rc != 0
        assert client.calls.count(PythonPlan) == 1, (
            "with feedback_retries=0 there must be no second STEP 2 call"
        )
        assert gen_path.read_text() == before


# ---------------------------------------------------------------------------
# Removing spec.lock.json = "rebuild from scratch" signal
# ---------------------------------------------------------------------------


class TestMissingLockRebuilds:
    """When the user deletes spec.lock.json, gen --call must treat it as
    "no recorded baseline" and rebuild from intent.md (equivalent to
    --force). This mirrors the missing-spec.md / missing-_generated.py
    semantics: a missing tracked artifact = "please regenerate it".
    """

    def test_missing_lock_does_not_error_out(self, pristine_project: Path) -> None:
        # Tracer bullet: removing spec.lock.json must not return rc=2
        # with "lock file not found". It must run the pipeline and end
        # with rc=0 + a fresh lock on disk.
        lock_path = pristine_project / "spec.lock.json"
        lock_path.unlink()

        client = _MockClient()
        rc, out, err = _call(pristine_project, client=client)

        assert rc == 0, (
            f"missing lock must not be a hard error (got rc={rc!r}, err={err!r})"
        )
        assert lock_path.exists(), "missing lock must be regenerated"

    def test_missing_lock_runs_step1_and_step2(self, pristine_project: Path) -> None:
        # The whole point of the rebuild semantics: missing lock must
        # actually invoke the LLM to regenerate from intent.md, not
        # silently rebuild the lock from current files (which would be
        # case-8 "freeze current state").
        (pristine_project / "spec.lock.json").unlink()

        client = _MockClient()
        rc, _, _ = _call(pristine_project, client=client)
        assert rc == 0
        assert SpecPlan in client.calls, (
            "missing lock = rebuild from intent.md → STEP 1 must run"
        )
        assert PythonPlan in client.calls, (
            "missing lock = rebuild from intent.md → STEP 2 must run"
        )

    def test_missing_lock_with_from_spec_skips_step1(
        self, pristine_project: Path
    ) -> None:
        # Escape hatch: user has hand-edited spec.md and wants the
        # rebuild to start from STEP 2, not from intent.md. --from-spec
        # must override the implicit force triggered by the missing lock.
        (pristine_project / "spec.lock.json").unlink()

        client = _MockClient()
        rc, _, _ = _call(pristine_project, client=client, from_spec=True)
        assert rc == 0
        assert SpecPlan not in client.calls, (
            "--from-spec must skip STEP 1 even when the lock is missing"
        )
        assert PythonPlan in client.calls, (
            "--from-spec still runs STEP 2 from current spec.md"
        )

    def test_missing_lock_and_missing_intent_still_errors(
        self, pristine_project: Path
    ) -> None:
        # Sanity: rebuild semantics need intent.md as the ground truth.
        # If both the lock AND intent.md are gone, there is no signal
        # to rebuild from — must error rather than silently produce an
        # empty / hallucinated spec.
        (pristine_project / "spec.lock.json").unlink()
        (pristine_project / "intent.md").unlink()

        client = _MockClient()
        rc, _, err = _call(pristine_project, client=client)
        assert rc != 0
        assert "intent" in err.lower(), (
            "error must point at the missing intent.md, not at the lock"
        )


# ---------------------------------------------------------------------------
# Feature toggle wiring (Phase 1.0 infrastructure)
# ---------------------------------------------------------------------------


class TestFeatureToggleWiring:
    """gen --call must read [tool.specstar].features from pyproject.toml
    and CLI overrides (--feature / --no-feature), then surface the
    resolved list in the STEP 2 user prompt as the 'Enabled features'
    preamble. This drives downstream codegen scope (which add_model
    kwargs the LLM is instructed to emit).
    """

    @pytest.fixture()
    def edited_intent(self, pristine_project: Path) -> Path:
        # Force STEP 2 to run so we have a prompt to inspect.
        (pristine_project / "intent.md").write_text(
            "# my_app intent\n\nA tiny change.\n", encoding="utf-8"
        )
        return pristine_project

    def _step2_prompt(self, client: _MockClient) -> str:
        # Pull the user prompt for the PythonPlan call.
        idx = client.calls.index(PythonPlan)
        return client.user_prompts[idx]

    def test_pyproject_features_reach_step2_prompt(self, edited_intent: Path) -> None:
        # Tracer: pyproject.toml [tool.specstar].features must flow
        # through to the STEP 2 user prompt verbatim.
        (edited_intent / "pyproject.toml").write_text(
            '[tool.specstar]\nfeatures = ["permissions", "indexes"]\n',
            encoding="utf-8",
        )
        client = _MockClient()
        rc, _, _ = _call(edited_intent, client=client)
        assert rc == 0
        prompt = self._step2_prompt(client)
        assert "Enabled features" in prompt
        assert "permissions" in prompt
        assert "indexes" in prompt

    def test_default_features_when_no_pyproject(self, edited_intent: Path) -> None:
        # No pyproject.toml = framework default
        # ("permissions", "workflows", "schema") shows up in prompt.
        client = _MockClient()
        rc, _, _ = _call(edited_intent, client=client)
        assert rc == 0
        prompt = self._step2_prompt(client)
        assert "Enabled features" in prompt
        for name in ("permissions", "workflows", "schema"):
            assert name in prompt

    def test_cli_feature_flag_adds_to_pyproject_features(
        self, edited_intent: Path
    ) -> None:
        # --feature storage on top of pyproject = ["permissions"]
        # widens scope for this run only (pyproject untouched).
        (edited_intent / "pyproject.toml").write_text(
            '[tool.specstar]\nfeatures = ["permissions"]\n',
            encoding="utf-8",
        )
        client = _MockClient()
        rc, _, _ = _call(edited_intent, client=client, cli_enable_features=["storage"])
        assert rc == 0
        prompt = self._step2_prompt(client)
        assert "permissions" in prompt
        assert "storage" in prompt

    def test_cli_no_feature_flag_removes_from_pyproject_features(
        self, edited_intent: Path
    ) -> None:
        client = _MockClient()
        rc, _, _ = _call(
            edited_intent,
            client=client,
            cli_disable_features=["workflows"],
        )
        assert rc == 0
        prompt = self._step2_prompt(client)
        # workflows was in default, should now be absent from preamble
        # (but it could still appear elsewhere in the prompt as part
        # of the spec.md content; check the preamble line specifically).
        # Find the preamble line:
        preamble_start = prompt.index("Enabled features")
        preamble_end = prompt.index("```", preamble_start)
        preamble_block = prompt[preamble_start:preamble_end]
        assert "workflows" not in preamble_block
        assert "permissions" in preamble_block


# ---------------------------------------------------------------------------
# Phase 2.1: workflows feature end-to-end
# ---------------------------------------------------------------------------


_WORKFLOW_GENERATED_PY = '''\
"""GENERATED with a workflow handler via string reference."""

from __future__ import annotations

import msgspec

from specstar import spec
from specstar.events import StringRefEventHandler
from specstar.types import ResourceAction


class Book(msgspec.Struct):
    title: str


spec.add_model(
    Book,
    name="book",
    event_handlers=[
        StringRefEventHandler(
            "my_app.logic.notify_customers_new_book",
            phase="after",
            action=ResourceAction.create,
        ),
    ],
)
'''


class TestWorkflowsEndToEnd:
    """Tracer for Phase 2.1: an LLM that emits ``event_handlers=
    [StringRefEventHandler(...)]`` survives the full gen --call
    pipeline (AST validate → write → lock → verify) because the
    handler instance is constructible at module-import time without
    pulling in user code.
    """

    @pytest.fixture()
    def edited_intent(self, pristine_project: Path) -> Path:
        (pristine_project / "intent.md").write_text(
            "# my_app intent\n\n"
            "A Book resource. When a book is created, notify customers.\n",
            encoding="utf-8",
        )
        return pristine_project

    def test_string_ref_event_handler_import_survives_lock(
        self, edited_intent: Path
    ) -> None:
        # End-to-end: LLM emits a _generated.py importing
        # StringRefEventHandler from specstar.events. The pipeline
        # must (a) AST-accept the import + call, (b) lock the
        # descriptor (subprocess imports the module — handler instance
        # constructs without resolving the dotted ref), (c) verify
        # the lock against on-disk sources.
        client = _MockClient(generated_py_after=_WORKFLOW_GENERATED_PY)
        rc, out, err = _call(edited_intent, client=client)
        assert rc == 0, (
            "workflow-style _generated.py must survive lock+verify; "
            f"out={out!r} err={err!r}"
        )
        gen_path = edited_intent / "my_app" / "_generated.py"
        assert "StringRefEventHandler" in gen_path.read_text()


_INDEXED_GENERATED_PY = '''\
"""GENERATED with indexed fields."""

from __future__ import annotations

import msgspec

from specstar import spec


class User(msgspec.Struct):
    name: str
    email: str


spec.add_model(User, name="user", indexed_fields=["email", "name"])
'''


_VERSIONED_SCHEMA_GENERATED_PY = '''\
"""GENERATED with versioned schema migration."""

from __future__ import annotations

import msgspec

from specstar import Schema, spec


def _migrate_v1_to_v2(d: dict) -> dict:
    return {**d, "title": d.pop("name", "")}


class BookV2(msgspec.Struct):
    title: str
    author: str


schema = Schema(BookV2, "v2").step("v1", _migrate_v1_to_v2)
spec.add_model(schema, name="book")
'''


class TestSchemaEndToEnd:
    """Phase 2.3: a Schema(Cls, "v2").step("v1", fn) chain must
    survive the full gen --call pipeline. Verifies the worked example
    in the STEP 2 prompt is actually executable (catches the
    Schema-missing-version regression that triggered Phase 2's
    feedback-retry loop in the first place).
    """

    def test_schema_chain_survives_lock(self, pristine_project: Path) -> None:
        (pristine_project / "intent.md").write_text(
            "# my_app intent\n\n"
            "Books used to be called by `name`; rename to `title`.\n",
            encoding="utf-8",
        )
        client = _MockClient(generated_py_after=_VERSIONED_SCHEMA_GENERATED_PY)
        rc, out, err = _call(pristine_project, client=client)
        assert rc == 0, (
            f"Schema chain must survive lock+verify; out={out!r} err={err!r}"
        )
        gen_text = (pristine_project / "my_app" / "_generated.py").read_text()
        assert 'Schema(BookV2, "v2")' in gen_text
        assert ".step(" in gen_text


_DEFAULTS_GENERATED_PY = '''\
"""GENERATED with default_status and default_user."""

from __future__ import annotations

import msgspec

from specstar import spec
from specstar.types import RevisionStatus


class Article(msgspec.Struct):
    title: str
    body: str


spec.add_model(
    Article,
    name="article",
    default_status=RevisionStatus.draft,
    default_user="anonymous",
)
'''


_BLOB_GENERATED_PY = '''\
"""GENERATED with project-level blob= binding."""

from __future__ import annotations

import msgspec

from specstar import BackendBinding, BackendConfig, spec


spec.configure(
    backend=BackendConfig(
        meta=BackendBinding(type="memory"),
        resource=BackendBinding(type="memory"),
        blob=BackendBinding(type="memory"),
    ),
)


class Asset(msgspec.Struct):
    name: str


spec.add_model(Asset, name="asset")
'''


class TestBlobEndToEnd:
    """Phase 2.10: ``### Blob`` extends ``spec.configure`` with
    ``blob=BackendBinding(type=...)``.
    """

    def test_blob_binding_survives_lock(self, pristine_project: Path) -> None:
        (pristine_project / "intent.md").write_text(
            "# my_app intent\n\nAssets need a blob store for uploads.\n",
            encoding="utf-8",
        )
        client = _MockClient(generated_py_after=_BLOB_GENERATED_PY)
        rc, out, err = _call(pristine_project, client=client)
        assert rc == 0, (
            f"blob=BackendBinding must survive lock+verify; out={out!r} err={err!r}"
        )
        text = (pristine_project / "my_app" / "_generated.py").read_text()
        assert 'blob=BackendBinding(type="memory")' in text


_MQ_GENERATED_PY = '''\
"""GENERATED with project-level mq= binding."""

from __future__ import annotations

import msgspec

from specstar import BackendBinding, BackendConfig, spec


spec.configure(
    backend=BackendConfig(
        meta=BackendBinding(type="memory"),
        resource=BackendBinding(type="memory"),
        mq=BackendBinding(type="simple"),
    ),
)


class JobItem(msgspec.Struct):
    payload: str


spec.add_model(JobItem, name="job_item")
'''


class TestMqEndToEnd:
    """Phase 2.9: ``### Message queue`` extends ``spec.configure`` with
    ``mq=BackendBinding(type=...)``. Exercises the simple_mq variant
    (in-process, no broker) for E2E without external services.
    """

    def test_simple_mq_binding_survives_lock(self, pristine_project: Path) -> None:
        (pristine_project / "intent.md").write_text(
            "# my_app intent\n\nUse a simple message queue for jobs.\n",
            encoding="utf-8",
        )
        client = _MockClient(generated_py_after=_MQ_GENERATED_PY)
        rc, out, err = _call(pristine_project, client=client)
        assert rc == 0, (
            f"mq=BackendBinding must survive lock+verify; out={out!r} err={err!r}"
        )
        text = (pristine_project / "my_app" / "_generated.py").read_text()
        assert 'mq=BackendBinding(type="simple")' in text


_STORAGE_GENERATED_PY = '''\
"""GENERATED with project-level spec.configure(backend=)."""

from __future__ import annotations

import msgspec

from specstar import BackendBinding, BackendConfig, spec


spec.configure(
    backend=BackendConfig(
        meta=BackendBinding(type="memory"),
        resource=BackendBinding(type="memory"),
    ),
)


class Book(msgspec.Struct):
    title: str


spec.add_model(Book, name="book")
'''


class TestStorageEndToEnd:
    """Phase 2.8: ``### Storage`` lifts to a ``spec.configure(backend=
    BackendConfig(...))`` call at the top of ``_generated.py``. The
    memory variant is exercised end-to-end (no env / no real DB) to
    prove the call shape survives lock + verify.
    """

    def test_spec_configure_with_memory_backend_survives_lock(
        self, pristine_project: Path
    ) -> None:
        (pristine_project / "intent.md").write_text(
            "# my_app intent\n\nUse memory storage for development.\n",
            encoding="utf-8",
        )
        client = _MockClient(generated_py_after=_STORAGE_GENERATED_PY)
        rc, out, err = _call(pristine_project, client=client)
        assert rc == 0, (
            f"spec.configure(backend=...) must survive lock+verify; "
            f"out={out!r} err={err!r}"
        )
        text = (pristine_project / "my_app" / "_generated.py").read_text()
        assert "spec.configure(" in text
        assert "BackendConfig(" in text


_CONSTRAINTS_GENERATED_PY = '''\
"""GENERATED with constraint_checkers (StringRefConstraintChecker)."""

from __future__ import annotations

import msgspec

from specstar import spec
from specstar.resource_manager import StringRefConstraintChecker


class Book(msgspec.Struct):
    title: str
    isbn: str
    price: float


spec.add_model(
    Book,
    name="book",
    constraint_checkers=[
        StringRefConstraintChecker("my_app.logic.no_duplicate_isbn"),
        StringRefConstraintChecker("my_app.logic.price_must_be_positive"),
    ],
)
'''


class TestConstraintsEndToEnd:
    """Phase 3.2: ``### Constraints`` translates to real
    ``StringRefConstraintChecker`` instances. The wrapper is an
    IConstraintChecker (not a factory), so it survives ``add_model``
    without resolving user code; that only happens on first ``check``.
    """

    def test_string_ref_constraint_checker_survives_lock(
        self, pristine_project: Path
    ) -> None:
        (pristine_project / "intent.md").write_text(
            "# my_app intent\n\nBooks have ISBN uniqueness + price > 0.\n",
            encoding="utf-8",
        )
        client = _MockClient(generated_py_after=_CONSTRAINTS_GENERATED_PY)
        rc, out, err = _call(pristine_project, client=client)
        assert rc == 0, (
            f"constraint_checkers=[StringRefConstraintChecker(...)] must "
            f"survive lock+verify; out={out!r} err={err!r}"
        )
        text = (pristine_project / "my_app" / "_generated.py").read_text()
        assert "StringRefConstraintChecker(" in text


_PERMISSIONS_GENERATED_PY = '''\
"""GENERATED with per-action permissions."""

from __future__ import annotations

import msgspec

from specstar import spec
from specstar.permission import (
    ActionBasedPermissionChecker,
    admin_only,
    any_authenticated,
    owner_self,
)
from specstar.types import ResourceAction


class Document(msgspec.Struct):
    title: str
    body: str


spec.add_model(
    Document,
    name="document",
    permission_checker=ActionBasedPermissionChecker.from_dict(
        {
            ResourceAction.read: any_authenticated,
            ResourceAction.update: owner_self,
            ResourceAction.delete: admin_only,
        }
    ),
)
'''


class TestPermissionsEndToEnd:
    """Phase 3.1: ``### Permissions`` translates to
    ``permission_checker=ActionBasedPermissionChecker.from_dict({...})``
    using the 5 built-in CheckFunc symbols.
    """

    def test_action_based_checker_survives_lock(
        self, pristine_project: Path
    ) -> None:
        (pristine_project / "intent.md").write_text(
            "# my_app intent\n\n"
            "Documents: any logged-in user can read; owner can update; "
            "admin can delete.\n",
            encoding="utf-8",
        )
        client = _MockClient(generated_py_after=_PERMISSIONS_GENERATED_PY)
        rc, out, err = _call(pristine_project, client=client)
        assert rc == 0, (
            f"ActionBasedPermissionChecker must survive lock+verify; "
            f"out={out!r} err={err!r}"
        )
        text = (pristine_project / "my_app" / "_generated.py").read_text()
        assert "ActionBasedPermissionChecker.from_dict" in text
        assert "any_authenticated" in text


_VALIDATOR_GENERATED_PY = '''\
"""GENERATED with validator (string ref)."""

from __future__ import annotations

import msgspec

import specstar
from specstar import spec


class Book(msgspec.Struct):
    title: str
    isbn: str


spec.add_model(
    Book,
    name="book",
    validator=specstar.string_ref("my_app.logic.validate_book"),
)
'''


class TestValidatorEndToEnd:
    """Phase 2.11: ``### Validation`` → ``validator=`` via
    ``specstar.string_ref(...)``. validator is called at create/update
    time (not at add_model time), so the lazy ref doesn't blow up lock.
    ``constraint_checkers`` is deferred (called eagerly during
    add_model — needs a dedicated lazy wrapper before it can ship).
    """

    def test_validator_string_ref_survives_lock(self, pristine_project: Path) -> None:
        (pristine_project / "intent.md").write_text(
            "# my_app intent\n\nBooks need ISBN format validation.\n",
            encoding="utf-8",
        )
        client = _MockClient(generated_py_after=_VALIDATOR_GENERATED_PY)
        rc, out, err = _call(pristine_project, client=client)
        assert rc == 0, (
            f"validator=specstar.string_ref(...) must survive lock+verify; "
            f"out={out!r} err={err!r}"
        )
        text = (pristine_project / "my_app" / "_generated.py").read_text()
        assert 'validator=specstar.string_ref("my_app.logic.validate_book")' in text


_ID_GEN_GENERATED_PY = '''\
"""GENERATED with id_generator via string_ref."""

from __future__ import annotations

import msgspec

import specstar
from specstar import spec


class Order(msgspec.Struct):
    user_id: str
    amount: int


spec.add_model(
    Order,
    name="order",
    id_generator=specstar.string_ref("my_app.logic.gen_order_id"),
)
'''


class TestIdGeneratorEndToEnd:
    """Phase 2.7: id_generator= via specstar.string_ref(...) — lazy
    callable that resolves the dotted path on first invocation. Must
    survive import + lock + verify without the user logic module
    being present at lock time.
    """

    def test_id_generator_string_ref_survives_lock(
        self, pristine_project: Path
    ) -> None:
        (pristine_project / "intent.md").write_text(
            "# my_app intent\n\nOrders use a custom ID generator.\n",
            encoding="utf-8",
        )
        client = _MockClient(generated_py_after=_ID_GEN_GENERATED_PY)
        rc, out, err = _call(pristine_project, client=client)
        assert rc == 0, (
            f"id_generator=specstar.string_ref(...) must survive lock+verify; "
            f"out={out!r} err={err!r}"
        )
        text = (pristine_project / "my_app" / "_generated.py").read_text()
        assert 'string_ref("my_app.logic.gen_order_id")' in text


_ENCODING_GENERATED_PY = '''\
"""GENERATED with encoding= kwarg."""

from __future__ import annotations

import msgspec

from specstar import spec
from specstar.resource_manager import Encoding


class Blob(msgspec.Struct):
    name: str
    payload: bytes


spec.add_model(Blob, name="blob", encoding=Encoding.msgpack)
'''


class TestEncodingEndToEnd:
    """Phase 2.6: ``encoding: msgpack`` in ### Defaults translates to
    ``encoding=Encoding.msgpack`` on add_model.
    """

    def test_encoding_kwarg_survives_lock(self, pristine_project: Path) -> None:
        (pristine_project / "intent.md").write_text(
            "# my_app intent\n\nBlob resources use msgpack for compactness.\n",
            encoding="utf-8",
        )
        client = _MockClient(generated_py_after=_ENCODING_GENERATED_PY)
        rc, out, err = _call(pristine_project, client=client)
        assert rc == 0, f"encoding= must survive lock+verify; out={out!r} err={err!r}"
        assert (
            "encoding=Encoding.msgpack"
            in (pristine_project / "my_app" / "_generated.py").read_text()
        )


class TestDefaultsEndToEnd:
    """Phase 2.5: ``### Defaults`` translates to ``default_status=``,
    ``default_user=`` kwargs. The kwargs must survive import + lock +
    verify (RevisionStatus is a real enum; default_user accepts a
    plain literal string).
    """

    def test_default_status_and_user_survive_lock(self, pristine_project: Path) -> None:
        (pristine_project / "intent.md").write_text(
            "# my_app intent\n\nArticles default to draft status.\n",
            encoding="utf-8",
        )
        client = _MockClient(generated_py_after=_DEFAULTS_GENERATED_PY)
        rc, out, err = _call(pristine_project, client=client)
        assert rc == 0, (
            f"defaults kwargs must survive lock+verify; out={out!r} err={err!r}"
        )
        text = (pristine_project / "my_app" / "_generated.py").read_text()
        assert "default_status=RevisionStatus.draft" in text
        assert 'default_user="anonymous"' in text


class TestIndexesEndToEnd:
    """Phase 2.2: ``### Indexes`` translates to ``indexed_fields=`` in
    _generated.py. The kwarg is a plain list literal, so the only
    pipeline check is that import + lock + verify still pass.
    """

    def test_indexed_fields_kwarg_survives_lock(self, pristine_project: Path) -> None:
        (pristine_project / "intent.md").write_text(
            "# my_app intent\n\nUsers with name + email; search by email.\n",
            encoding="utf-8",
        )
        client = _MockClient(generated_py_after=_INDEXED_GENERATED_PY)
        rc, out, err = _call(pristine_project, client=client)
        assert rc == 0, (
            f"indexed_fields= must survive lock+verify; out={out!r} err={err!r}"
        )
        gen_path = pristine_project / "my_app" / "_generated.py"
        assert 'indexed_fields=["email", "name"]' in gen_path.read_text()
