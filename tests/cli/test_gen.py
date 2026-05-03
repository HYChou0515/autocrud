"""Tests for ``specstar gen`` — two-step prompt printing (dry-run)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from specstar.cli import main as cli_main
from specstar.cli._gen import run_gen
from specstar.cli._init import run_init


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
