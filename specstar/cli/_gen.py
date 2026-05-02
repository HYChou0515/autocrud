"""``specstar gen`` — print the spec-driven LLM prompt for non-Claude-Code users.

Phase 2.5 ships a **dry-run-only** version: ``specstar gen`` reads the
current project state plus the user's brief prose, builds the system +
user prompts via :mod:`specstar.skill.prompts`, and prints them. Users
pipe the output into their own LLM tooling (Anthropic SDK script, Claude
desktop, OpenAI-compatible local model, etc.) and apply the resulting
plan manually — typically via subsequent ``specstar lock`` + ``specstar
verify`` invocations.

A future release will add a ``--call`` flag that invokes the Anthropic API
directly; the prompt building stays in :mod:`specstar.skill.prompts` so
both surfaces stay aligned.

Output formats:

- **text** (default): the prompts in human-readable form, sectioned
  ``=== system ===`` / ``=== user ===``
- **json** (``--format json``): the messages list shaped for the
  Anthropic ``messages.create`` API (system as a top-level field,
  ``messages`` as the conversation array)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import msgspec

from specstar.lockfile import read_manifest
from specstar.skill.prompts import (
    build_messages,
    build_system_prompt,
    state_from_paths,
)


def add_gen_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``gen`` subcommand on the top-level parser."""
    p = subparsers.add_parser(
        "gen",
        help="Print the spec-driven LLM prompt (v0.11: dry-run only).",
        description=(
            "Build and print the system + user prompts for the spec-driven "
            "authoring LLM call. Pipe into your own LLM client. A future "
            "release will add direct Anthropic API integration via --call."
        ),
    )
    p.add_argument(
        "brief",
        nargs="?",
        default=None,
        help="Brief prose describing the change. If omitted, read from stdin.",
    )
    p.add_argument(
        "--package",
        default=None,
        help=(
            "Python package name (e.g. my_app). Auto-detected from existing "
            "spec.lock.json when omitted."
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
            "Path to _generated.py. Auto-detected from --package or existing "
            "lock when omitted."
        ),
    )
    p.add_argument(
        "--lock",
        default="spec.lock.json",
        help="Path to spec.lock.json (default: ./spec.lock.json).",
    )
    p.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format. ``text`` for human reading; ``json`` for the "
        "Anthropic API messages list.",
    )
    p.set_defaults(func=gen_cmd)


def gen_cmd(args: argparse.Namespace) -> int:
    return run_gen(
        brief=args.brief,
        package=args.package,
        spec_path=Path(args.spec),
        generated_path=Path(args.generated) if args.generated else None,
        lock_path=Path(args.lock),
        output_format=args.format,
        stdin=sys.stdin,
        stream=sys.stdout,
        error_stream=sys.stderr,
    )


def run_gen(
    *,
    brief: str | None,
    package: str | None,
    spec_path: Path,
    generated_path: Path | None,
    lock_path: Path,
    output_format: str,
    stdin,
    stream,
    error_stream,
) -> int:
    """Build prompts and print them. Returns process exit code."""
    if brief is None:
        brief = stdin.read()
    if not brief.strip():
        print(
            "error: brief prose is required (positional arg or stdin)",
            file=error_stream,
        )
        return 2

    if not spec_path.exists():
        print(f"error: spec file not found: {spec_path}", file=error_stream)
        return 2

    # Auto-detect package and generated path from lock if available.
    manifest = None
    if lock_path.exists():
        try:
            manifest = read_manifest(lock_path)
        except msgspec.DecodeError as exc:
            print(
                f"error: cannot parse {lock_path}: {exc}",
                file=error_stream,
            )
            return 2

    if package is None or generated_path is None:
        if manifest is not None:
            for relpath in manifest.sources:
                if relpath.endswith("_generated.py"):
                    detected = Path(relpath)
                    if generated_path is None:
                        generated_path = detected
                    if package is None:
                        package = detected.parent.name
                    break

    if package is None:
        print(
            "error: --package is required when no existing lock is present",
            file=error_stream,
        )
        return 2
    if generated_path is None:
        generated_path = Path(package) / "_generated.py"
    if not generated_path.exists():
        print(
            f"error: generated file not found: {generated_path}",
            file=error_stream,
        )
        return 2

    state = state_from_paths(
        spec_md_path=spec_path,
        generated_py_path=generated_path,
        manifest=manifest,
        package_name=package,
    )

    if output_format == "json":
        payload = {
            "system": build_system_prompt(),
            "messages": build_messages(brief, state),
        }
        print(json.dumps(payload, indent=2), file=stream)
    else:
        print("=== system ===", file=stream)
        print(build_system_prompt(), file=stream)
        print(file=stream)
        print("=== user ===", file=stream)
        print(build_messages(brief, state)[0]["content"], file=stream)
        print(file=stream)
        print(
            "(specstar gen v0.11: dry-run only. Pipe the prompts above into "
            "your own LLM client, then apply the plan manually via edits + "
            "`specstar lock` + `specstar verify`. Direct API integration is "
            "coming in a future release.)",
            file=stream,
        )
    return 0
