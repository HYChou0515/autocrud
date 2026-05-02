"""Tests for ``specstar gen`` — dry-run prompt printing."""

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
    return tmp_path


def _gen(project: Path, brief: str | None, **kwargs) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    stdin = io.StringIO(kwargs.pop("stdin_text", ""))
    cwd = Path.cwd()
    import os

    os.chdir(project)
    try:
        rc = run_gen(
            brief=brief,
            package=kwargs.pop("package", None),
            spec_path=Path(kwargs.pop("spec_path", "spec.md")),
            generated_path=kwargs.pop("generated_path", None),
            lock_path=Path(kwargs.pop("lock_path", "spec.lock.json")),
            output_format=kwargs.pop("output_format", "text"),
            stdin=stdin,
            stream=out,
            error_stream=err,
        )
    finally:
        os.chdir(cwd)
    return rc, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestTextOutput:
    def test_prints_system_and_user_sections(self, starter_project: Path) -> None:
        rc, out, _ = _gen(starter_project, "add a Phone resource")
        assert rc == 0
        assert "=== system ===" in out
        assert "=== user ===" in out

    def test_user_section_includes_brief(self, starter_project: Path) -> None:
        rc, out, _ = _gen(starter_project, "add a Phone resource")
        assert rc == 0
        assert "add a Phone resource" in out

    def test_user_section_includes_spec_md(self, starter_project: Path) -> None:
        spec = (starter_project / "spec.md").read_text()
        rc, out, _ = _gen(starter_project, "add Phone")
        assert rc == 0
        assert spec in out

    def test_dry_run_disclaimer_present(self, starter_project: Path) -> None:
        rc, out, _ = _gen(starter_project, "add Phone")
        assert rc == 0
        assert "dry-run" in out


class TestJsonOutput:
    def test_emits_valid_json(self, starter_project: Path) -> None:
        rc, out, _ = _gen(starter_project, "add Phone", output_format="json")
        assert rc == 0
        payload = json.loads(out)
        assert "system" in payload
        assert "messages" in payload

    def test_messages_are_anthropic_shape(self, starter_project: Path) -> None:
        rc, out, _ = _gen(starter_project, "add Phone", output_format="json")
        payload = json.loads(out)
        msgs = payload["messages"]
        assert isinstance(msgs, list)
        assert msgs[0]["role"] == "user"
        assert "content" in msgs[0]


class TestStdinFallback:
    def test_brief_from_stdin_when_arg_omitted(self, starter_project: Path) -> None:
        rc, out, _ = _gen(
            starter_project, brief=None, stdin_text="add a Phone resource"
        )
        assert rc == 0
        assert "add a Phone resource" in out

    def test_empty_brief_returns_two(self, starter_project: Path) -> None:
        rc, _, err = _gen(starter_project, brief=None, stdin_text="")
        assert rc == 2
        assert "brief prose is required" in err


# ---------------------------------------------------------------------------
# Auto-detection
# ---------------------------------------------------------------------------


class TestAutoDetection:
    def test_package_detected_from_lock(self, starter_project: Path) -> None:
        # No --package passed; should auto-detect "my_app" from the lock.
        rc, out, _ = _gen(starter_project, "add Phone")
        assert rc == 0
        assert "PACKAGE: my_app" in out

    def test_explicit_package_overrides(self, starter_project: Path) -> None:
        rc, out, _ = _gen(starter_project, "add Phone", package="my_app")
        assert rc == 0


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_missing_spec_returns_two(self, tmp_path: Path) -> None:
        out = io.StringIO()
        err = io.StringIO()
        stdin = io.StringIO("")
        rc = run_gen(
            brief="x",
            package="my_app",
            spec_path=tmp_path / "spec.md",
            generated_path=tmp_path / "gen.py",
            lock_path=tmp_path / "lock.json",
            output_format="text",
            stdin=stdin,
            stream=out,
            error_stream=err,
        )
        assert rc == 2
        assert "spec file not found" in err.getvalue()

    def test_no_package_no_lock_returns_two(self, tmp_path: Path) -> None:
        (tmp_path / "spec.md").write_text("# demo\n", encoding="utf-8")
        out = io.StringIO()
        err = io.StringIO()
        stdin = io.StringIO("")
        rc = run_gen(
            brief="x",
            package=None,
            spec_path=tmp_path / "spec.md",
            generated_path=None,
            lock_path=tmp_path / "spec.lock.json",
            output_format="text",
            stdin=stdin,
            stream=out,
            error_stream=err,
        )
        assert rc == 2
        assert "--package is required" in err.getvalue()


# ---------------------------------------------------------------------------
# CLI dispatch
# ---------------------------------------------------------------------------


class TestCliDispatch:
    def test_gen_appears_in_help(self, capsys) -> None:
        rc = cli_main([])
        captured = capsys.readouterr()
        assert rc == 0
        assert "gen" in captured.out

    def test_gen_via_main(self, starter_project: Path, monkeypatch) -> None:
        monkeypatch.chdir(starter_project)
        rc = cli_main(["gen", "add Phone"])
        assert rc == 0
