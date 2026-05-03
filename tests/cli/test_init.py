"""Tests for ``specstar init``: starter project layout, refusal to overwrite,
and that the generated lock immediately ``verify``s clean.
"""

from __future__ import annotations

import io
from pathlib import Path

from specstar.cli import main as cli_main
from specstar.cli._init import run_init
from specstar.cli._verify import run_verify
from specstar.lockfile import read_manifest


def _run(tmp_path: Path, **kwargs) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    rc = run_init(
        package=kwargs.pop("package", "my_app"),
        root=tmp_path,
        force=kwargs.pop("force", False),
        write_lock=kwargs.pop("write_lock", True),
        stream=out,
        error_stream=err,
    )
    return rc, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


class TestStarterLayout:
    def test_creates_all_expected_files(self, tmp_path: Path) -> None:
        rc, _, _ = _run(tmp_path)
        assert rc == 0
        assert (tmp_path / "intent.md").exists()
        assert (tmp_path / "spec.md").exists()
        assert (tmp_path / "my_app" / "__init__.py").exists()
        assert (tmp_path / "my_app" / "_generated.py").exists()
        assert (tmp_path / "spec.lock.json").exists()

    def test_intent_md_contains_package_name(self, tmp_path: Path) -> None:
        _run(tmp_path, package="acme_api")
        intent = (tmp_path / "intent.md").read_text()
        assert "acme_api" in intent

    def test_intent_md_invites_user_to_describe(self, tmp_path: Path) -> None:
        _run(tmp_path)
        intent = (tmp_path / "intent.md").read_text()
        # The starter prose should hint at "your own words" / replace this.
        assert "your own words" in intent

    def test_spec_md_has_generated_header(self, tmp_path: Path) -> None:
        _run(tmp_path)
        spec = (tmp_path / "spec.md").read_text()
        # Header marks the file as generated but editable.
        assert "GENERATED" in spec
        assert "may edit" in spec.lower()

    def test_generated_py_has_generated_header(self, tmp_path: Path) -> None:
        _run(tmp_path)
        gen = (tmp_path / "my_app" / "_generated.py").read_text()
        assert "GENERATED" in gen
        assert "SSOT" in gen

    def test_custom_package_name(self, tmp_path: Path) -> None:
        rc, _, _ = _run(tmp_path, package="acme_api")
        assert rc == 0
        assert (tmp_path / "acme_api" / "__init__.py").exists()
        assert (tmp_path / "acme_api" / "_generated.py").exists()
        # Both intent.md and spec.md mention the package name in headings.
        assert "acme_api" in (tmp_path / "intent.md").read_text()
        assert "acme_api" in (tmp_path / "spec.md").read_text()

    def test_no_lock_skips_lock_file(self, tmp_path: Path) -> None:
        rc, _, _ = _run(tmp_path, write_lock=False)
        assert rc == 0
        assert (tmp_path / "intent.md").exists()
        assert (tmp_path / "spec.md").exists()
        assert not (tmp_path / "spec.lock.json").exists()

    def test_summary_lists_created_files(self, tmp_path: Path) -> None:
        _, out, _ = _run(tmp_path)
        assert "intent.md" in out
        assert "spec.md" in out
        assert "my_app/_generated.py" in out
        assert "spec.lock.json" in out

    def test_summary_next_steps_point_to_intent_md(self, tmp_path: Path) -> None:
        _, out, _ = _run(tmp_path)
        assert "edit intent.md" in out


# ---------------------------------------------------------------------------
# Lock content
# ---------------------------------------------------------------------------


class TestStarterLockContent:
    def test_generated_lock_immediately_verifies_clean(self, tmp_path: Path) -> None:
        _run(tmp_path)
        out = io.StringIO()
        err = io.StringIO()
        rc = run_verify(tmp_path / "spec.lock.json", stream=out, error_stream=err)
        assert rc == 0, (
            f"verify failed: stdout={out.getvalue()} stderr={err.getvalue()}"
        )
        assert "ok" in out.getvalue().lower()

    def test_lock_descriptor_contains_user_resource(self, tmp_path: Path) -> None:
        _run(tmp_path)
        manifest = read_manifest(tmp_path / "spec.lock.json")
        ids = {n.id for n in manifest.descriptor.nodes}
        assert "resource:user" in ids
        assert "field:user.name" in ids
        assert "field:user.email" in ids

    def test_lock_sources_match_disk_files(self, tmp_path: Path) -> None:
        _run(tmp_path)
        manifest = read_manifest(tmp_path / "spec.lock.json")
        assert "intent.md" in manifest.sources
        assert "spec.md" in manifest.sources
        assert "my_app/_generated.py" in manifest.sources

    def test_lock_intent_md_hash_matches_disk(self, tmp_path: Path) -> None:
        import hashlib

        from specstar.lockfile import normalize_text

        _run(tmp_path)
        manifest = read_manifest(tmp_path / "spec.lock.json")
        on_disk = (tmp_path / "intent.md").read_bytes()
        expected = hashlib.sha256(normalize_text(on_disk)).hexdigest()
        assert manifest.sources["intent.md"].sha256 == expected


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------


class TestOverwriteSafety:
    def test_refuses_to_overwrite_existing_files(self, tmp_path: Path) -> None:
        (tmp_path / "spec.md").write_text("preserve me\n", encoding="utf-8")
        rc, _, err = _run(tmp_path)
        assert rc == 1
        assert "refusing to overwrite" in err
        assert "spec.md" in err
        # File still has its original contents.
        assert (tmp_path / "spec.md").read_text() == "preserve me\n"

    def test_force_overwrites_existing_files(self, tmp_path: Path) -> None:
        (tmp_path / "spec.md").write_text("old content\n", encoding="utf-8")
        rc, _, _ = _run(tmp_path, force=True)
        assert rc == 0
        assert "old content" not in (tmp_path / "spec.md").read_text()


class TestInputValidation:
    def test_invalid_package_name_rejected(self, tmp_path: Path) -> None:
        rc, _, err = _run(tmp_path, package="123-bad")
        assert rc == 2
        assert "not a valid Python package name" in err

    def test_missing_root_rejected(self, tmp_path: Path) -> None:
        out = io.StringIO()
        err = io.StringIO()
        rc = run_init(
            package="my_app",
            root=tmp_path / "nonexistent",
            force=False,
            write_lock=True,
            stream=out,
            error_stream=err,
        )
        assert rc == 2
        assert "root directory does not exist" in err.getvalue()


# ---------------------------------------------------------------------------
# CLI dispatch
# ---------------------------------------------------------------------------


class TestCliDispatch:
    def test_init_via_main(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        rc = cli_main(["init"])
        assert rc == 0
        assert (tmp_path / "my_app" / "_generated.py").exists()

    def test_init_with_custom_package_via_main(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.chdir(tmp_path)
        rc = cli_main(["init", "acme"])
        assert rc == 0
        assert (tmp_path / "acme" / "_generated.py").exists()

    def test_init_appears_in_help(self, capsys) -> None:
        rc = cli_main([])
        captured = capsys.readouterr()
        assert rc == 0
        assert "init" in captured.out
