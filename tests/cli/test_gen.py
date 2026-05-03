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

    def call(self, *, system, user, response_model):
        self.calls.append(response_model)
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
