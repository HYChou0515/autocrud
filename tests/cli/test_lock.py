"""Tests for ``specstar lock`` — descriptor regeneration via subprocess."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from specstar.cli import main as cli_main
from specstar.cli._init import run_init
from specstar.cli._lock import run_lock
from specstar.cli._verify import run_verify
from specstar.lockfile import read_manifest


@pytest.fixture()
def starter_project(tmp_path: Path) -> Path:
    """Lay down a real starter via ``specstar init`` so ``lock`` has
    something to import. Returns the project root."""
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


def _lock(project: Path, **kwargs) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    cwd = Path.cwd()
    try:
        import os

        os.chdir(project)
        rc = run_lock(
            module_name=kwargs.pop("module_name", None),
            spec_path=Path(kwargs.pop("spec_path", "spec.md")),
            generated_path=kwargs.pop("generated_path", None),
            out_path=Path(kwargs.pop("out_path", "spec.lock.json")),
            stream=out,
            error_stream=err,
        )
    finally:
        os.chdir(cwd)
    return rc, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestRegenerateFromStarter:
    def test_lock_regenerates_clean_starter(self, starter_project: Path) -> None:
        rc, out, _ = _lock(starter_project)
        assert rc == 0
        assert "wrote" in out
        assert "ast_check=passed" in out

    def test_lock_then_verify_is_clean(self, starter_project: Path) -> None:
        _lock(starter_project)
        out = io.StringIO()
        err = io.StringIO()
        rc = run_verify(
            starter_project / "spec.lock.json", stream=out, error_stream=err
        )
        assert rc == 0, err.getvalue()

    def test_auto_detects_module_from_existing_lock(
        self, starter_project: Path
    ) -> None:
        # No --module passed; should auto-detect ``my_app._generated``.
        rc, out, _ = _lock(starter_project)
        assert rc == 0

    def test_explicit_module_argument(self, starter_project: Path) -> None:
        rc, out, _ = _lock(starter_project, module_name="my_app._generated")
        assert rc == 0


# ---------------------------------------------------------------------------
# Edits to spec.md flow through to lock
# ---------------------------------------------------------------------------


class TestEditsArePickedUp:
    def test_spec_md_change_updates_hash(self, starter_project: Path) -> None:
        before = read_manifest(starter_project / "spec.lock.json")
        before_hash = before.sources["spec.md"].sha256

        (starter_project / "spec.md").write_text(
            "# my_app\n\nadded text\n", encoding="utf-8"
        )
        _lock(starter_project)

        after = read_manifest(starter_project / "spec.lock.json")
        assert after.sources["spec.md"].sha256 != before_hash

    def test_generated_py_change_updates_hash(self, starter_project: Path) -> None:
        # User adds an extra (still declarative) line to _generated.py.
        gen = starter_project / "my_app" / "_generated.py"
        gen.write_text(gen.read_text() + "\nNAMESPACE = 'my_app'\n", encoding="utf-8")
        rc, out, _ = _lock(starter_project)
        assert rc == 0


# ---------------------------------------------------------------------------
# AST validation integration
# ---------------------------------------------------------------------------


class TestAstValidation:
    def test_blocked_import_in_generated_fails_lock(
        self, starter_project: Path
    ) -> None:
        gen = starter_project / "my_app" / "_generated.py"
        # Rewrite the whole file with a forbidden top-level import. Cannot
        # prepend ``import os`` to the existing template because the template
        # starts with ``from __future__ import annotations``, which must be
        # the first statement.
        gen.write_text(
            "import os\n"
            "import msgspec\n"
            "from specstar import spec\n"
            "\n"
            "class User(msgspec.Struct):\n"
            "    name: str\n"
            "    email: str\n"
            "\n"
            "spec.add_model(User, name='user')\n",
            encoding="utf-8",
        )
        rc, _, err = _lock(starter_project)
        # AST failure → exit 1 + ast_check=failed.
        assert rc == 1
        assert "blocked_import" in err

    def test_failed_ast_still_writes_lock_for_audit(
        self, starter_project: Path
    ) -> None:
        gen = starter_project / "my_app" / "_generated.py"
        gen.write_text(
            "import os\n"
            "import msgspec\n"
            "from specstar import spec\n"
            "\n"
            "class User(msgspec.Struct):\n"
            "    name: str\n"
            "    email: str\n"
            "\n"
            "spec.add_model(User, name='user')\n",
            encoding="utf-8",
        )
        _lock(starter_project)
        manifest = read_manifest(starter_project / "spec.lock.json")
        assert manifest.validation.ast_check == "failed"
        assert any(e["kind"] == "blocked_import" for e in manifest.validation.errors)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_missing_spec_md_returns_two(self, tmp_path: Path) -> None:
        out = io.StringIO()
        err = io.StringIO()
        rc = run_lock(
            module_name="my_app._generated",
            spec_path=tmp_path / "spec.md",
            generated_path=None,
            out_path=tmp_path / "spec.lock.json",
            stream=out,
            error_stream=err,
        )
        assert rc == 2
        assert "spec file not found" in err.getvalue()

    def test_no_module_and_no_lock_returns_two(self, tmp_path: Path) -> None:
        (tmp_path / "spec.md").write_text("# demo\n", encoding="utf-8")
        out = io.StringIO()
        err = io.StringIO()
        rc = run_lock(
            module_name=None,
            spec_path=tmp_path / "spec.md",
            generated_path=None,
            out_path=tmp_path / "spec.lock.json",
            stream=out,
            error_stream=err,
        )
        assert rc == 2
        assert "--module is required" in err.getvalue()

    def test_unimportable_module_reports_error(self, tmp_path: Path) -> None:
        (tmp_path / "spec.md").write_text("# demo\n", encoding="utf-8")
        (tmp_path / "fake.py").write_text("dummy\n", encoding="utf-8")
        out = io.StringIO()
        err = io.StringIO()
        rc = run_lock(
            module_name="this_module_does_not_exist",
            spec_path=tmp_path / "spec.md",
            generated_path=tmp_path / "fake.py",
            out_path=tmp_path / "spec.lock.json",
            stream=out,
            error_stream=err,
        )
        assert rc == 1
        # Error is written to stderr from the subprocess.


# ---------------------------------------------------------------------------
# CLI dispatch
# ---------------------------------------------------------------------------


class TestCliDispatch:
    def test_lock_appears_in_help(self, capsys) -> None:
        rc = cli_main([])
        captured = capsys.readouterr()
        assert rc == 0
        assert "lock" in captured.out

    def test_lock_via_main(self, starter_project: Path, monkeypatch) -> None:
        monkeypatch.chdir(starter_project)
        rc = cli_main(["lock"])
        assert rc == 0
