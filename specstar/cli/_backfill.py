"""``specstar backfill-vectors`` — batch re-encode Vector / Embedding fields.

Loads a SpecStar instance from ``--spec module:attr`` and runs
:func:`specstar.resource_manager.backfill.backfill_vectors` against the
named model + field.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from typing import TextIO


def add_backfill_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``backfill-vectors`` subcommand."""
    p = subparsers.add_parser(
        "backfill-vectors",
        help="Re-encode Vector / Embedding fields for existing rows.",
        description=(
            "Scan a registered model's resources and call the configured "
            "encoder for any Embedding field where the stored vector is "
            "missing or stale (encoder_id differs from the current one)."
        ),
    )
    p.add_argument(
        "--spec",
        required=True,
        help="Module path to your SpecStar instance, e.g. 'myapp:spec'.",
    )
    p.add_argument(
        "--model",
        required=True,
        help="Registered model name (the same string used in add_model name=...).",
    )
    p.add_argument(
        "--field",
        required=True,
        help="Name of the Embedding field on the model.",
    )
    p.set_defaults(func=backfill_vectors_cmd)


def backfill_vectors_cmd(
    args: argparse.Namespace,
    *,
    stream: TextIO | None = None,
    error_stream: TextIO | None = None,
) -> int:
    stream = stream or sys.stdout
    error_stream = error_stream or sys.stderr

    try:
        module_name, attr = args.spec.split(":", 1)
    except ValueError:
        print(f"--spec must be 'module:attr', got {args.spec!r}", file=error_stream)
        return 2

    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        print(f"cannot import {module_name!r}: {exc}", file=error_stream)
        return 2

    spec = getattr(module, attr, None)
    if spec is None:
        print(f"{module_name!r} has no attribute {attr!r}", file=error_stream)
        return 2

    try:
        rm = spec.get_resource_manager(args.model)
    except (KeyError, ValueError) as exc:
        print(f"model {args.model!r} not registered: {exc}", file=error_stream)
        return 2

    from specstar.resource_manager.backfill import backfill_vectors

    summary = backfill_vectors(rm, field_name=args.field)
    print(
        f"backfill-vectors[{args.model}.{args.field}]: "
        f"encoded={summary.encoded} skipped={summary.skipped}",
        file=stream,
    )
    return 0


def add_backfill_set_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``backfill-set-index`` subcommand."""
    p = subparsers.add_parser(
        "backfill-set-index",
        help="Populate SetIndex shadow columns for existing rows.",
        description=(
            "Repopulate the dedicated array column for a SetIndex field from "
            "indexed_data across all existing rows — needed for rows written "
            "before the column was added (Postgres only; a no-op elsewhere)."
        ),
    )
    p.add_argument(
        "--spec",
        required=True,
        help="Module path to your SpecStar instance, e.g. 'myapp:spec'.",
    )
    p.add_argument(
        "--model",
        required=True,
        help="Registered model name (the same string used in add_model name=...).",
    )
    p.add_argument(
        "--field",
        required=True,
        help="Name of the SetIndex field on the model.",
    )
    p.set_defaults(func=backfill_set_cmd)


def backfill_set_cmd(
    args: argparse.Namespace,
    *,
    stream: TextIO | None = None,
    error_stream: TextIO | None = None,
) -> int:
    stream = stream or sys.stdout
    error_stream = error_stream or sys.stderr

    try:
        module_name, attr = args.spec.split(":", 1)
    except ValueError:
        print(f"--spec must be 'module:attr', got {args.spec!r}", file=error_stream)
        return 2

    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        print(f"cannot import {module_name!r}: {exc}", file=error_stream)
        return 2

    spec = getattr(module, attr, None)
    if spec is None:
        print(f"{module_name!r} has no attribute {attr!r}", file=error_stream)
        return 2

    try:
        rm = spec.get_resource_manager(args.model)
    except (KeyError, ValueError) as exc:
        print(f"model {args.model!r} not registered: {exc}", file=error_stream)
        return 2

    from specstar.resource_manager.backfill import backfill_set_columns

    summary = backfill_set_columns(rm, field_name=args.field)
    print(
        f"backfill-set-index[{args.model}.{args.field}]: encoded={summary.encoded}",
        file=stream,
    )
    return 0
