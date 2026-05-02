"""SpecStar command-line dispatcher.

This package hosts two CLI surfaces that coexist:

- The legacy resource-browser tool (``build.py``, ``config.py``,
  ``__main__.py``), invoked via ``python -m specstar.cli``. Untouched by the
  v0.11 spec-driven layer.
- The v0.11 spec-driven dev tool, exposed as the ``specstar`` shell command
  (wired in ``pyproject.toml [project.scripts]``) and dispatched by
  :func:`main` below.

Subcommands shipped in v0.11:

- ``specstar verify`` — deterministic ``spec.lock.json`` consistency check
  (CI-friendly, exits non-zero on drift).
- ``specstar status`` — informational read-only sync report (always exits 0).

Future v0.11 follow-ups (``init``, ``gen``) hook into :func:`build_parser`
in subsequent commits.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from specstar.cli._status import add_status_parser
from specstar.cli._verify import add_verify_parser


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argparse parser with all subcommands attached."""
    parser = argparse.ArgumentParser(
        prog="specstar",
        description=(
            "Spec-driven backend platform for FastAPI. "
            "Run with no subcommand to print help."
        ),
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    add_verify_parser(sub)
    add_status_parser(sub)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch a CLI invocation. Returns process exit code.

    ``argv`` defaults to ``sys.argv[1:]`` when ``None`` (the normal entry-point
    case); tests pass an explicit list to avoid touching real argv.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover - thin entry point
    sys.exit(main())
