"""``specstar gen`` — print the spec-driven LLM prompts (dry-run only).

v0.11 transitional state:

This command builds and prints the system + user prompts for the
**two-step** spec-driven pipeline (intent.md → spec.md, spec.md →
_generated.py). It does not yet invoke an LLM directly — that lands in
a follow-up commit when the orchestration layer (`specstar.skill.plan`)
arrives. Pipe the printed prompts into your own LLM client for now:

::

    specstar gen --step 1 --format json | <your-LLM-tool>
    specstar gen --step 2 --format json | <your-LLM-tool>

Output formats:

- **text** (default): human-readable, sectioned ``=== system ===`` /
  ``=== user ===``
- **json** (``--format json``): Anthropic-API shape with system as a
  top-level field

The Claude Code skill does the full two-step flow interactively. This
CLI exists for users without Claude Code who want to plug their own
LLM toolchain (any provider, including self-hosted) into SpecStar.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import msgspec

from specstar.lockfile import read_manifest
from specstar.skill.prompts import (
    STEP1_SYSTEM_PROMPT,
    STEP2_SYSTEM_PROMPT,
    Step1Input,
    Step2Input,
    build_step1_messages,
    build_step2_messages,
)


def add_gen_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``gen`` subcommand on the top-level parser."""
    p = subparsers.add_parser(
        "gen",
        help="Print the spec-driven LLM prompts (v0.11: dry-run only).",
        description=(
            "Build and print the system + user prompts for the two-step "
            "spec-driven authoring pipeline. Pipe into your own LLM client. "
            "Direct API integration via litellm lands in a follow-up commit."
        ),
    )
    p.add_argument(
        "--step",
        type=int,
        choices=[1, 2],
        default=1,
        help=(
            "Which step to print: 1 = intent.md → spec.md, "
            "2 = spec.md → _generated.py. Default 1."
        ),
    )
    p.add_argument(
        "--package",
        default=None,
        help=(
            "Python package name (e.g. my_app). Auto-detected from "
            "spec.lock.json when omitted."
        ),
    )
    p.add_argument(
        "--intent",
        default="intent.md",
        help="Path to intent.md (default: ./intent.md).",
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
        "Anthropic API shape.",
    )
    p.set_defaults(func=gen_cmd)


def gen_cmd(args: argparse.Namespace) -> int:
    return run_gen(
        step=args.step,
        package=args.package,
        intent_path=Path(args.intent),
        spec_path=Path(args.spec),
        generated_path=Path(args.generated) if args.generated else None,
        lock_path=Path(args.lock),
        output_format=args.format,
        stream=sys.stdout,
        error_stream=sys.stderr,
    )


def run_gen(
    *,
    step: int,
    package: str | None,
    intent_path: Path,
    spec_path: Path,
    generated_path: Path | None,
    lock_path: Path,
    output_format: str,
    stream,
    error_stream,
) -> int:
    """Build prompts for ``step`` and print them. Returns process exit code."""
    if step not in (1, 2):
        print(f"error: unknown step {step}", file=error_stream)
        return 2

    # Auto-detect package and generated path from existing lock.
    manifest = None
    if lock_path.exists():
        try:
            manifest = read_manifest(lock_path)
        except msgspec.DecodeError as exc:
            print(f"error: cannot parse {lock_path}: {exc}", file=error_stream)
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

    if step == 1:
        if not intent_path.exists():
            print(f"error: intent file not found: {intent_path}", file=error_stream)
            return 2
        previous_spec_md = (
            spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""
        )
        step_input = Step1Input(
            intent_md=intent_path.read_text(encoding="utf-8"),
            previous_spec_md=previous_spec_md,
            package_name=package,
        )
        system_prompt = STEP1_SYSTEM_PROMPT
        messages = build_step1_messages(step_input)
        step_label = "STEP 1 (intent.md → spec.md)"
    else:
        if not spec_path.exists():
            print(f"error: spec file not found: {spec_path}", file=error_stream)
            return 2
        if generated_path is None:
            generated_path = Path(package) / "_generated.py"
        previous_generated_py = (
            generated_path.read_text(encoding="utf-8")
            if generated_path.exists()
            else ""
        )
        step_input = Step2Input(
            spec_md=spec_path.read_text(encoding="utf-8"),
            previous_generated_py=previous_generated_py,
            package_name=package,
        )
        system_prompt = STEP2_SYSTEM_PROMPT
        messages = build_step2_messages(step_input)
        step_label = "STEP 2 (spec.md → _generated.py)"

    if output_format == "json":
        payload = {"step": step, "system": system_prompt, "messages": messages}
        print(json.dumps(payload, indent=2), file=stream)
    else:
        print(f"=== {step_label} ===", file=stream)
        print(file=stream)
        print("=== system ===", file=stream)
        print(system_prompt, file=stream)
        print(file=stream)
        print("=== user ===", file=stream)
        print(messages[0]["content"], file=stream)
        print(file=stream)
        print(
            "(specstar gen v0.11: dry-run only. Pipe these prompts into your LLM "
            "client; apply the resulting Plan via edits + `specstar lock` + "
            "`specstar verify`. Direct API integration coming in a follow-up release.)",
            file=stream,
        )
    return 0
