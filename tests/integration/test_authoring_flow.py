"""End-to-end integration tests for the spec-driven authoring loop.

These tests simulate the full daily user flow without invoking an LLM:
the "skill" steps are replaced by scripted file edits, and we assert
that the deterministic CLI commands (init / status / lock / verify)
compose correctly across the four sync cases per design doc §3.6.

This is the closest we can get to Phase 3.3 (skill integration tests)
without standing up an Anthropic mock — the LLM-driven half is exercised
separately via :mod:`tests.skill.test_prompts`.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from specstar.cli._init import run_init
from specstar.cli._lock import run_lock
from specstar.cli._status import run_status
from specstar.cli._verify import run_verify
from specstar.lockfile import read_manifest


def _streams() -> tuple[io.StringIO, io.StringIO]:
    return io.StringIO(), io.StringIO()


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """A starter project that immediately ``verify``s clean."""
    out, err = _streams()
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


def _chdir(path: Path):
    import contextlib
    import os

    @contextlib.contextmanager
    def cm():
        before = Path.cwd()
        os.chdir(path)
        try:
            yield
        finally:
            os.chdir(before)

    return cm()


# ---------------------------------------------------------------------------
# Daily flow: edit spec → edit generated → lock → verify
# ---------------------------------------------------------------------------


class TestDailyAuthoringLoop:
    def test_full_loop_init_then_simulate_skill_then_lock_then_verify(
        self, project: Path
    ) -> None:
        # 0. starter is clean.
        out, err = _streams()
        assert run_status(project / "spec.lock.json", stream=out, error_stream=err) == 0
        assert "case 1" in out.getvalue()

        # 1. user edits spec.md (via Claude Code chat → skill). Simulate the
        #    skill-curated prose by appending a new resource section.
        spec = project / "spec.md"
        spec.write_text(
            spec.read_text()
            + "\n## Resource: Tag\n\n### Fields\n- `label`: required string\n",
            encoding="utf-8",
        )
        out, err = _streams()
        run_status(project / "spec.lock.json", stream=out, error_stream=err)
        assert "case 2" in out.getvalue()
        assert "spec.md: modified" in out.getvalue()

        # 2. skill writes the corresponding declarative Python.
        generated = project / "my_app" / "_generated.py"
        generated.write_text(
            generated.read_text().rstrip()
            + "\n\n\nclass Tag(msgspec.Struct):\n    label: str\n\n\n"
            'spec.add_model(Tag, name="tag")\n',
            encoding="utf-8",
        )
        out, err = _streams()
        run_status(project / "spec.lock.json", stream=out, error_stream=err)
        # Both spec.md and _generated.py drift from lock → case 4.
        assert "case 4" in out.getvalue()

        # 3. user runs `specstar lock` to regenerate the manifest.
        with _chdir(project):
            out, err = _streams()
            rc = run_lock(
                module_name=None,
                spec_path=Path("spec.md"),
                generated_path=None,
                out_path=Path("spec.lock.json"),
                stream=out,
                error_stream=err,
            )
        assert rc == 0, err.getvalue()

        # 4. status returns to case 1.
        out, err = _streams()
        run_status(project / "spec.lock.json", stream=out, error_stream=err)
        assert "case 1" in out.getvalue()

        # 5. verify is green.
        out, err = _streams()
        rc = run_verify(project / "spec.lock.json", stream=out, error_stream=err)
        assert rc == 0, err.getvalue()

        # 6. lock now contains the new Tag resource in its descriptor.
        manifest = read_manifest(project / "spec.lock.json")
        ids = {n.id for n in manifest.descriptor.nodes}
        assert "resource:user" in ids
        assert "resource:tag" in ids


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------


class TestDriftScenarios:
    def test_case_3_user_edits_only_generated(self, project: Path) -> None:
        # User hand-edits _generated.py (e.g. tweak a model attribute).
        generated = project / "my_app" / "_generated.py"
        generated.write_text(
            generated.read_text().replace(
                'spec.add_model(User, name="user")',
                'spec.add_model(User, name="user_v2")',
            ),
            encoding="utf-8",
        )
        out, err = _streams()
        run_status(project / "spec.lock.json", stream=out, error_stream=err)
        assert "case 3" in out.getvalue()
        # Verify fails on hash mismatch.
        out, err = _streams()
        rc = run_verify(project / "spec.lock.json", stream=out, error_stream=err)
        assert rc == 1
        assert "hash mismatch" in err.getvalue()

    def test_case_2_user_edits_only_spec_md(self, project: Path) -> None:
        spec = project / "spec.md"
        spec.write_text(spec.read_text() + "\nextra prose\n", encoding="utf-8")
        out, err = _streams()
        run_status(project / "spec.lock.json", stream=out, error_stream=err)
        assert "case 2" in out.getvalue()
        out, err = _streams()
        rc = run_verify(project / "spec.lock.json", stream=out, error_stream=err)
        assert rc == 1


# ---------------------------------------------------------------------------
# AST validator integration along the loop
# ---------------------------------------------------------------------------


class TestAstAlongTheLoop:
    def test_lock_fails_when_generated_has_blocked_import(self, project: Path) -> None:
        # Replace the entire _generated.py with a forbidden top-level import.
        # (Cannot prepend; from __future__ must be first.)
        generated = project / "my_app" / "_generated.py"
        generated.write_text(
            "import os\n"
            "import msgspec\n"
            "from specstar import spec\n"
            "\n"
            "class User(msgspec.Struct):\n"
            "    name: str\n"
            "    email: str\n"
            "\n"
            'spec.add_model(User, name="user")\n',
            encoding="utf-8",
        )
        with _chdir(project):
            out, err = _streams()
            rc = run_lock(
                module_name=None,
                spec_path=Path("spec.md"),
                generated_path=None,
                out_path=Path("spec.lock.json"),
                stream=out,
                error_stream=err,
            )
        assert rc == 1
        assert "blocked_import" in err.getvalue()
        # Lock is still written for audit, with ast_check=failed.
        manifest = read_manifest(project / "spec.lock.json")
        assert manifest.validation.ast_check == "failed"

    def test_verify_fails_when_generated_has_blocked_pattern(
        self, project: Path
    ) -> None:
        # Pre-corrupt the file *after* the lock was written, so hashes
        # mismatch *and* the AST validator fails.
        generated = project / "my_app" / "_generated.py"
        generated.write_text(
            generated.read_text() + "\nimport socket  # noqa\n", encoding="utf-8"
        )
        out, err = _streams()
        rc = run_verify(project / "spec.lock.json", stream=out, error_stream=err)
        assert rc == 1
        # Both errors surface.
        combined = err.getvalue()
        assert "hash mismatch" in combined
        assert "blocked_import" in combined


# ---------------------------------------------------------------------------
# Hash normalization end-to-end
# ---------------------------------------------------------------------------


class TestHashNormalization:
    def test_crlf_edit_does_not_trigger_drift(self, project: Path) -> None:
        # Simulate a Windows editor saving the file with CRLF line endings.
        spec = project / "spec.md"
        original = spec.read_bytes()
        spec.write_bytes(original.replace(b"\n", b"\r\n"))
        out, err = _streams()
        rc = run_verify(project / "spec.lock.json", stream=out, error_stream=err)
        assert rc == 0, err.getvalue()
