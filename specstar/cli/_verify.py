"""``specstar verify`` — deterministic check that ``spec.lock.json`` is in
sync with the source files it tracks.

Phase 2.2 implementation. All checks are deterministic — no LLM, no network.

Performed checks:

1. Each file referenced in ``manifest.sources`` exists on disk.
2. Each on-disk file's SHA-256 matches the hash recorded in the manifest.
3. Every source path ending in ``_generated.py`` passes the AST validator.

Deferred to a follow-up commit (still in Phase 2.2):

- Recompute the descriptor by importing the user's ``_generated.py`` and
  calling :meth:`SpecStar.dump_descriptor`, then compare against the manifest's
  embedded descriptor. Skipped here because importing user code requires a
  convention for locating the SpecStar instance that we have not yet pinned
  down.

Exit codes:

- 0 — all checks passed
- 1 — drift detected (missing file, hash mismatch, AST validation failure)
- 2 — invalid invocation (lock file missing or unparseable)
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

import msgspec

from specstar.descriptor import Manifest
from specstar.lockfile import compute_file_hash, read_manifest
from specstar.validator import DeclarativeASTValidator, ValidationError


def add_verify_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``verify`` subcommand on the top-level parser."""
    p = subparsers.add_parser(
        "verify",
        help="Verify spec.lock.json against source files (no LLM, deterministic).",
        description=(
            "Recompute hashes for files tracked in spec.lock.json and run the "
            "AST validator on every _generated.py source. Exits 0 if everything "
            "matches, 1 on drift, 2 on invalid invocation."
        ),
    )
    p.add_argument(
        "--lock",
        default="spec.lock.json",
        help="Path to spec.lock.json (default: ./spec.lock.json).",
    )
    p.set_defaults(func=verify_cmd)


def verify_cmd(args: argparse.Namespace) -> int:
    """Argparse entry point. Returns process exit code."""
    lock_path = Path(args.lock)
    return run_verify(lock_path, stream=sys.stdout, error_stream=sys.stderr)


def run_verify(
    lock_path: Path,
    *,
    stream,
    error_stream,
) -> int:
    """Execute the verify pipeline against a lock file. Returns exit code.

    Pure-ish: takes streams as arguments so tests can capture output without
    monkey-patching ``sys.stdout``.
    """
    if not lock_path.exists():
        print(f"error: lock file not found: {lock_path}", file=error_stream)
        return 2

    try:
        manifest = read_manifest(lock_path)
    except msgspec.DecodeError as exc:
        print(f"error: cannot parse {lock_path}: {exc}", file=error_stream)
        return 2

    project_root = lock_path.parent.resolve()
    failures: list[str] = []

    failures.extend(_check_source_hashes(manifest, project_root))
    failures.extend(_check_generated_python_ast(manifest, project_root))

    if failures:
        for line in failures:
            print(line, file=error_stream)
        print(f"verify: {len(failures)} issue(s) detected", file=error_stream)
        return 1

    n = len(manifest.sources)
    print(f"verify: ok ({n} source{'s' if n != 1 else ''} match lock)", file=stream)
    return 0


def _check_source_hashes(manifest: Manifest, project_root: Path) -> Iterable[str]:
    """Yield human-readable failure lines for hash mismatches / missing files."""
    for relpath, expected in manifest.sources.items():
        actual_path = project_root / relpath
        if not actual_path.exists():
            yield f"missing: {relpath} (referenced in lock but not on disk)"
            continue
        actual_sha, _ = compute_file_hash(actual_path)
        if actual_sha != expected.sha256:
            yield (
                f"hash mismatch: {relpath} "
                f"(lock={expected.sha256[:12]}…, disk={actual_sha[:12]}…)"
            )


def _check_generated_python_ast(
    manifest: Manifest, project_root: Path
) -> Iterable[str]:
    """Run the AST validator on every ``_generated.py`` tracked in the lock."""
    for relpath in manifest.sources:
        if not relpath.endswith("_generated.py"):
            continue
        actual_path = project_root / relpath
        if not actual_path.exists():
            # Already reported by hash check; skip.
            continue
        try:
            source = actual_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            yield f"AST: cannot decode {relpath}: {exc}"
            continue
        try:
            errors = DeclarativeASTValidator().validate(
                source, filename=str(actual_path)
            )
        except SyntaxError as exc:
            yield f"AST: syntax error in {relpath}: line {exc.lineno}: {exc.msg}"
            continue
        for err in errors:
            yield _format_validator_error(relpath, err)


def _format_validator_error(relpath: str, err: ValidationError) -> str:
    return f"AST: {relpath}:{err.line}:{err.col} [{err.kind}] {err.message}"
