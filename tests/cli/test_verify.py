"""End-to-end tests for ``specstar verify``.

These tests exercise the deterministic CLI pipeline by:

1. Building a temp project tree (``spec.md``, ``_generated.py``,
   ``spec.lock.json``) on disk.
2. Calling ``specstar.cli.main(["verify", "--lock", ...])`` with captured
   stdout/stderr.
3. Asserting the exit code and the human-readable output.

This is the first user-visible command in the v0.11 spec-driven layer.
"""

from __future__ import annotations

import io
import textwrap
from pathlib import Path

import pytest

from specstar.cli import main as cli_main
from specstar.cli._verify import run_verify
from specstar.descriptor import Descriptor, ValidationStatus
from specstar.lockfile import build_manifest, write_manifest


def _make_project(tmp_path: Path, generated_source: str = "x = 1\n") -> Path:
    """Lay out a minimal project (spec.md + _generated.py + lock) in ``tmp_path``."""
    spec_md = tmp_path / "spec.md"
    spec_md.write_text("# demo spec\n", encoding="utf-8")

    pkg = tmp_path / "my_app"
    pkg.mkdir()
    gen = pkg / "_generated.py"
    gen.write_text(generated_source, encoding="utf-8")

    descriptor = Descriptor(nodes=[], edges=[])
    manifest = build_manifest(
        descriptor,
        sources={"spec.md": spec_md, "my_app/_generated.py": gen},
        validation=ValidationStatus(ast_check="passed"),
    )
    lock_path = tmp_path / "spec.lock.json"
    write_manifest(manifest, lock_path)
    return lock_path


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestVerifyHappyPath:
    def test_clean_project_exits_zero(self, tmp_path: Path) -> None:
        lock = _make_project(tmp_path)
        out = io.StringIO()
        err = io.StringIO()
        rc = run_verify(lock, stream=out, error_stream=err)
        assert rc == 0
        assert "ok" in out.getvalue().lower()
        assert err.getvalue() == ""

    def test_summary_includes_source_count(self, tmp_path: Path) -> None:
        lock = _make_project(tmp_path)
        out = io.StringIO()
        err = io.StringIO()
        run_verify(lock, stream=out, error_stream=err)
        assert "2 source" in out.getvalue()

    def test_main_dispatch_zero_for_clean_project(self, tmp_path: Path) -> None:
        lock = _make_project(tmp_path)
        rc = cli_main(["verify", "--lock", str(lock)])
        assert rc == 0


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------


class TestDriftDetection:
    def test_modified_spec_md_flagged_as_hash_mismatch(self, tmp_path: Path) -> None:
        lock = _make_project(tmp_path)
        # User edits spec.md after lock was written.
        (tmp_path / "spec.md").write_text("# demo spec — edited\n", encoding="utf-8")
        out = io.StringIO()
        err = io.StringIO()
        rc = run_verify(lock, stream=out, error_stream=err)
        assert rc == 1
        assert "hash mismatch" in err.getvalue()
        assert "spec.md" in err.getvalue()

    def test_deleted_source_flagged_as_missing(self, tmp_path: Path) -> None:
        lock = _make_project(tmp_path)
        (tmp_path / "spec.md").unlink()
        out = io.StringIO()
        err = io.StringIO()
        rc = run_verify(lock, stream=out, error_stream=err)
        assert rc == 1
        assert "missing" in err.getvalue()

    def test_summary_counts_failures(self, tmp_path: Path) -> None:
        lock = _make_project(tmp_path)
        (tmp_path / "spec.md").write_text("changed\n", encoding="utf-8")
        (tmp_path / "my_app" / "_generated.py").write_text("y = 2\n", encoding="utf-8")
        out = io.StringIO()
        err = io.StringIO()
        rc = run_verify(lock, stream=out, error_stream=err)
        assert rc == 1
        assert "2 issue" in err.getvalue()


# ---------------------------------------------------------------------------
# AST validation
# ---------------------------------------------------------------------------


class TestAstValidation:
    def test_blocked_import_in_generated_py_fails_verify(self, tmp_path: Path) -> None:
        bad_source = textwrap.dedent("""\
            import os
            x = 1
        """)
        # Build the project so the lock's hash matches the bad source.
        lock = _make_project(tmp_path, generated_source=bad_source)
        out = io.StringIO()
        err = io.StringIO()
        rc = run_verify(lock, stream=out, error_stream=err)
        assert rc == 1
        assert "blocked_import" in err.getvalue()
        assert "_generated.py" in err.getvalue()

    def test_blocked_statement_in_generated_py_fails_verify(
        self, tmp_path: Path
    ) -> None:
        bad_source = textwrap.dedent("""\
            try:
                x = 1
            except Exception:
                x = 2
        """)
        lock = _make_project(tmp_path, generated_source=bad_source)
        out = io.StringIO()
        err = io.StringIO()
        rc = run_verify(lock, stream=out, error_stream=err)
        assert rc == 1
        assert "blocked_statement" in err.getvalue() or "Try" in err.getvalue()


# ---------------------------------------------------------------------------
# Invalid invocation
# ---------------------------------------------------------------------------


class TestInvalidInvocation:
    def test_missing_lock_file_returns_two(self, tmp_path: Path) -> None:
        out = io.StringIO()
        err = io.StringIO()
        rc = run_verify(tmp_path / "nope.lock.json", stream=out, error_stream=err)
        assert rc == 2
        assert "lock file not found" in err.getvalue()

    def test_unparseable_lock_returns_two(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.lock.json"
        bad.write_text("{not json", encoding="utf-8")
        out = io.StringIO()
        err = io.StringIO()
        rc = run_verify(bad, stream=out, error_stream=err)
        assert rc == 2
        assert "cannot parse" in err.getvalue()


# ---------------------------------------------------------------------------
# Top-level help / no-arg
# ---------------------------------------------------------------------------


class TestTopLevelDispatch:
    def test_no_subcommand_prints_help_and_returns_zero(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = cli_main([])
        captured = capsys.readouterr()
        assert rc == 0
        assert "verify" in captured.out
        assert "specstar" in captured.out.lower()

    def test_unknown_subcommand_returns_nonzero(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as exc_info:
            cli_main(["nonexistent"])
        assert exc_info.value.code != 0
