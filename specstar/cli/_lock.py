"""``specstar lock`` — regenerate ``spec.lock.json`` from current sources.

Phase 2.x. The deterministic half of ``specstar gen`` (the LLM-driven
``gen`` command will eventually wrap this plus prompt-driven editing of
``_generated.py``).

Workflow it closes:

::

    user edits spec.md
    /specstar regen   in Claude Code     # skill edits _generated.py
    specstar lock                        # this command — re-hashes + rebuilds lock
    specstar verify                      # CI-style sanity check

Implementation: spawn a Python subprocess that imports the user's
``_generated.py`` (so any ``add_model`` side effects fire on a fresh
:class:`specstar.SpecStar` global), prints the descriptor as JSON, and
exits. The parent process reads the JSON, runs the AST validator on
``_generated.py``, builds the :class:`Manifest`, and writes
``spec.lock.json``.

Subprocess isolation matters: if we imported the user's module in-process,
running ``specstar lock`` twice would re-register models on the global
``spec`` instance and trigger ``ValueError: model already exists``.

Convention assumed: ``_generated.py`` populates the global
``specstar.spec`` instance. Custom-instance projects need to point
``--global-name`` at their attribute (not yet implemented; deferred to v1.x).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import msgspec
import msgspec.json

from specstar.descriptor import Descriptor, ValidationStatus
from specstar.lockfile import build_manifest, now_iso, read_manifest, write_manifest
from specstar.validator import DeclarativeASTValidator


def add_lock_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``lock`` subcommand on the top-level parser."""
    p = subparsers.add_parser(
        "lock",
        help="Regenerate spec.lock.json from current spec.md and _generated.py.",
        description=(
            "Import _generated.py in a subprocess, snapshot the descriptor, "
            "rehash the source files, and write spec.lock.json. Deterministic "
            "(no LLM)."
        ),
    )
    p.add_argument(
        "--module",
        default=None,
        help=(
            "Dotted Python path of the module that registers resources "
            "(e.g. my_app._generated). Auto-detected from existing "
            "spec.lock.json when omitted."
        ),
    )
    p.add_argument(
        "--intent",
        default="intent.md",
        help=(
            "Path to intent.md (default: ./intent.md). Included in lock sources "
            "if it exists; silently skipped otherwise."
        ),
    )
    p.add_argument(
        "--spec",
        default="spec.md",
        help="Path to spec.md (default: ./spec.md).",
    )
    p.add_argument(
        "--generated",
        default=None,
        help=(
            "Path to _generated.py. Auto-detected from --module or existing "
            "lock when omitted."
        ),
    )
    p.add_argument(
        "--out",
        default="spec.lock.json",
        help="Path to write the lock file (default: ./spec.lock.json).",
    )
    p.set_defaults(func=lock_cmd)


def lock_cmd(args: argparse.Namespace) -> int:
    return run_lock(
        intent_path=Path(args.intent),
        module_name=args.module,
        spec_path=Path(args.spec),
        generated_path=Path(args.generated) if args.generated else None,
        out_path=Path(args.out),
        stream=sys.stdout,
        error_stream=sys.stderr,
    )


def run_lock(
    *,
    module_name: str | None,
    spec_path: Path,
    generated_path: Path | None,
    out_path: Path,
    stream,
    error_stream,
    intent_path: Path | None = None,
) -> int:
    """Regenerate the lock file. Returns process exit code.

    ``intent_path`` is included in lock sources only if it exists on
    disk. Optional so that single-spec-only projects (no intent.md
    layer) still work; in the canonical two-step pipeline ``init``
    creates intent.md alongside spec.md and we want it tracked.
    """
    if not spec_path.exists():
        print(f"error: spec file not found: {spec_path}", file=error_stream)
        return 2

    # Auto-detect module / generated path from existing lock if available.
    if (module_name is None or generated_path is None) and out_path.exists():
        try:
            existing = read_manifest(out_path)
            for relpath in existing.sources:
                if relpath.endswith("_generated.py"):
                    if generated_path is None:
                        generated_path = Path(relpath)
                    if module_name is None:
                        module_name = _path_to_module(Path(relpath))
                    break
        except msgspec.DecodeError:
            pass  # Fall through to error below if still unresolved.

    if module_name is None:
        print(
            "error: --module is required when no existing spec.lock.json "
            "is present to auto-detect from",
            file=error_stream,
        )
        return 2
    if generated_path is None:
        generated_path = _module_to_path(module_name)

    if not generated_path.exists():
        print(
            f"error: generated file not found: {generated_path}",
            file=error_stream,
        )
        return 2

    descriptor = _snapshot_descriptor(module_name, error_stream)
    if descriptor is None:
        return 1

    validation = _run_ast_validator(generated_path, error_stream)

    sources: dict[str, str | Path] = {}
    if intent_path is not None and intent_path.exists():
        sources[str(intent_path)] = intent_path
    sources[str(spec_path)] = spec_path
    sources[str(generated_path)] = generated_path

    manifest = build_manifest(
        descriptor,
        sources=sources,
        validation=validation,
        regenerated_at=now_iso(),
    )
    write_manifest(manifest, out_path)

    n_nodes = len(descriptor.nodes)
    n_edges = len(descriptor.edges)
    print(
        f"lock: wrote {out_path} ({n_nodes} node(s), {n_edges} edge(s), "
        f"ast_check={validation.ast_check})",
        file=stream,
    )
    return 0 if validation.ast_check == "passed" else 1


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _path_to_module(path: Path) -> str:
    """Convert ``my_app/_generated.py`` → ``my_app._generated``."""
    return ".".join(path.with_suffix("").parts)


def _module_to_path(module: str) -> Path:
    """Convert ``my_app._generated`` → ``my_app/_generated.py``."""
    return Path(*module.split(".")).with_suffix(".py")


def _snapshot_descriptor(module_name: str, error_stream) -> Descriptor | None:
    """Run the user's _generated.py in a subprocess and capture the descriptor.

    Subprocess isolation prevents global-state pollution across multiple
    ``specstar lock`` invocations in the same shell session.
    """
    snippet = (
        "import sys, importlib\n"
        "sys.path.insert(0, '.')\n"
        f"importlib.import_module({module_name!r})\n"
        "from specstar import spec\n"
        "import msgspec.json\n"
        "sys.stdout.buffer.write(msgspec.json.encode(spec.dump_descriptor()))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", snippet],
        capture_output=True,
    )
    if result.returncode != 0:
        print(
            f"error: failed to import {module_name!r}:",
            file=error_stream,
        )
        sys.stderr.write(result.stderr.decode("utf-8", errors="replace"))
        return None
    try:
        return msgspec.json.decode(result.stdout, type=Descriptor)
    except msgspec.DecodeError as exc:
        print(
            f"error: subprocess produced invalid descriptor JSON: {exc}",
            file=error_stream,
        )
        return None


def _run_ast_validator(generated_path: Path, error_stream) -> ValidationStatus:
    """Run the AST validator on ``_generated.py`` and shape the status."""
    source = generated_path.read_text(encoding="utf-8")
    validator = DeclarativeASTValidator()
    try:
        errors = validator.validate(source, filename=str(generated_path))
    except SyntaxError as exc:
        print(
            f"AST: syntax error in {generated_path}: line {exc.lineno}: {exc.msg}",
            file=error_stream,
        )
        return ValidationStatus(ast_check="failed", errors=[])
    if errors:
        for err in errors:
            print(
                f"AST: {generated_path}:{err.line}:{err.col} "
                f"[{err.kind}] {err.message}",
                file=error_stream,
            )
        return ValidationStatus(ast_check="failed", errors=validator.to_dicts())
    return ValidationStatus(ast_check="passed", errors=[])
