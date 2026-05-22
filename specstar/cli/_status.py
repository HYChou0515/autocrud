"""``specstar status`` — informational read-only sync report.

Phase 2.3. Always exits 0 (informational). Reports:

- whether each tracked source matches its recorded hash
- which of the four cases (per design doc §3.6) the project is in:
  case 1 (clean), 2 (spec.md edited), 3 (_generated.py edited), 4 (both)

The companion deterministic check that *fails* on drift is ``specstar
verify`` — use that in CI; reach for ``status`` interactively while editing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import msgspec

from specstar.descriptor import Manifest
from specstar.lockfile import compute_file_hash, read_manifest

_SPEC_MD_SUFFIX = "spec.md"
_GENERATED_PY_SUFFIX = "_generated.py"


def add_status_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``status`` subcommand on the top-level parser."""
    p = subparsers.add_parser(
        "status",
        help="Show current sync state of spec.lock.json sources (no LLM).",
        description=(
            "Report which tracked sources have drifted from spec.lock.json "
            "and classify the project into one of the four sync cases. "
            "Always exits 0; use `specstar verify` for a strict CI check."
        ),
    )
    p.add_argument(
        "--lock",
        default="spec.lock.json",
        help="Path to spec.lock.json (default: ./spec.lock.json).",
    )
    p.set_defaults(func=status_cmd)


def status_cmd(args: argparse.Namespace) -> int:
    return run_status(Path(args.lock), stream=sys.stdout, error_stream=sys.stderr)


def run_status(
    lock_path: Path,
    *,
    stream,
    error_stream,
) -> int:
    """Print the status report. Always returns 0."""
    if not lock_path.exists():
        print(
            f"no lock file at {lock_path} — run `specstar gen` to create one",
            file=stream,
        )
        return 0

    try:
        manifest = read_manifest(lock_path)
    except msgspec.DecodeError as exc:
        print(f"lock file at {lock_path} is unparseable: {exc}", file=error_stream)
        return 0

    project_root = lock_path.parent.resolve()
    file_lines, spec_changed, gen_changed = _classify_sources(manifest, project_root)
    case = _classify_case(spec_changed, gen_changed)

    print(
        f"spec.lock.json: specstar={manifest.specstar_version} "
        f"descriptor=v{manifest.descriptor_version}",
        file=stream,
    )
    print("sources:", file=stream)
    for line in file_lines:
        print(f"  {line}", file=stream)
    print(f"state: {case}", file=stream)
    return 0


def _classify_sources(
    manifest: Manifest, project_root: Path
) -> tuple[list[str], bool, bool]:
    """Return ``(human_lines, spec_md_changed, generated_py_changed)``."""
    spec_changed = False
    gen_changed = False
    lines: list[str] = []
    for relpath, expected in manifest.sources.items():
        actual_path = project_root / relpath
        if not actual_path.exists():
            lines.append(f"{relpath}: missing")
            if relpath.endswith(_SPEC_MD_SUFFIX):
                spec_changed = True
            if relpath.endswith(_GENERATED_PY_SUFFIX):
                gen_changed = True
            continue
        actual_sha, _ = compute_file_hash(actual_path)
        if actual_sha != expected.sha256:
            lines.append(
                f"{relpath}: modified "
                f"(lock={expected.sha256[:8]}, disk={actual_sha[:8]})"
            )
            if relpath.endswith(_SPEC_MD_SUFFIX):
                spec_changed = True
            if relpath.endswith(_GENERATED_PY_SUFFIX):
                gen_changed = True
        else:
            lines.append(f"{relpath}: ok")
    return lines, spec_changed, gen_changed


def _classify_case(spec_changed: bool, generated_changed: bool) -> str:
    """Map the (spec.md, _generated.py) drift pair to a case-1..4 label."""
    if not spec_changed and not generated_changed:
        return "case 1 — clean (no source changes)"
    if spec_changed and not generated_changed:
        return (
            "case 2 — spec.md changed; regenerate _generated.py "
            "via /specstar (or `specstar gen`)"
        )
    if not spec_changed and generated_changed:
        return (
            "case 3 — _generated.py changed without spec.md "
            "(drift: revert or promote into spec.md)"
        )
    return "case 4 — spec.md and _generated.py both changed; reconcile via skill"
