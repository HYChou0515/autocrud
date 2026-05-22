"""Tests for ``specstar status`` — case 1/2/3/4 sync classification."""

from __future__ import annotations

import io
from pathlib import Path

from specstar.cli import main as cli_main
from specstar.cli._status import run_status
from specstar.descriptor import Descriptor
from specstar.lockfile import build_manifest, write_manifest


def _make_project(tmp_path: Path) -> Path:
    spec_md = tmp_path / "spec.md"
    spec_md.write_text("# demo spec\n", encoding="utf-8")

    pkg = tmp_path / "my_app"
    pkg.mkdir()
    gen = pkg / "_generated.py"
    gen.write_text("x = 1\n", encoding="utf-8")

    manifest = build_manifest(
        Descriptor(nodes=[], edges=[]),
        sources={"spec.md": spec_md, "my_app/_generated.py": gen},
    )
    lock_path = tmp_path / "spec.lock.json"
    write_manifest(manifest, lock_path)
    return lock_path


def _run(lock_path: Path) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    rc = run_status(lock_path, stream=out, error_stream=err)
    return rc, out.getvalue(), err.getvalue()


class TestSyncCases:
    """Each of the four cases produces a clearly-labelled status line."""

    def test_case_1_clean(self, tmp_path: Path) -> None:
        lock = _make_project(tmp_path)
        rc, out, _ = _run(lock)
        assert rc == 0
        assert "case 1" in out
        assert ": ok" in out

    def test_case_2_spec_md_changed(self, tmp_path: Path) -> None:
        lock = _make_project(tmp_path)
        (tmp_path / "spec.md").write_text("# spec — edited\n", encoding="utf-8")
        rc, out, _ = _run(lock)
        assert rc == 0
        assert "case 2" in out
        assert "spec.md: modified" in out

    def test_case_3_generated_changed_only(self, tmp_path: Path) -> None:
        lock = _make_project(tmp_path)
        (tmp_path / "my_app" / "_generated.py").write_text("y = 2\n", encoding="utf-8")
        rc, out, _ = _run(lock)
        assert rc == 0
        assert "case 3" in out
        assert "_generated.py: modified" in out

    def test_case_4_both_changed(self, tmp_path: Path) -> None:
        lock = _make_project(tmp_path)
        (tmp_path / "spec.md").write_text("changed\n", encoding="utf-8")
        (tmp_path / "my_app" / "_generated.py").write_text("y = 2\n", encoding="utf-8")
        rc, out, _ = _run(lock)
        assert rc == 0
        assert "case 4" in out


class TestMissingFiles:
    def test_missing_spec_md_treated_as_changed(self, tmp_path: Path) -> None:
        lock = _make_project(tmp_path)
        (tmp_path / "spec.md").unlink()
        rc, out, _ = _run(lock)
        assert rc == 0
        assert "spec.md: missing" in out
        # Spec.md missing → counts as changed → case 2.
        assert "case 2" in out

    def test_missing_lock_file_prints_hint(self, tmp_path: Path) -> None:
        rc, out, _ = _run(tmp_path / "nope.lock.json")
        assert rc == 0
        assert "no lock file" in out
        assert "specstar gen" in out

    def test_unparseable_lock_warns_to_stderr(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.lock.json"
        bad.write_text("{not json", encoding="utf-8")
        rc, _, err = _run(bad)
        assert rc == 0
        assert "unparseable" in err


class TestCliDispatch:
    def test_status_via_main(self, tmp_path: Path) -> None:
        lock = _make_project(tmp_path)
        rc = cli_main(["status", "--lock", str(lock)])
        assert rc == 0

    def test_status_appears_in_help(self, capsys) -> None:
        rc = cli_main([])
        captured = capsys.readouterr()
        assert rc == 0
        assert "status" in captured.out


class TestReportContent:
    def test_each_source_listed(self, tmp_path: Path) -> None:
        lock = _make_project(tmp_path)
        _, out, _ = _run(lock)
        assert "spec.md" in out
        assert "my_app/_generated.py" in out

    def test_specstar_version_shown(self, tmp_path: Path) -> None:
        from specstar import __version__

        lock = _make_project(tmp_path)
        _, out, _ = _run(lock)
        assert __version__ in out
