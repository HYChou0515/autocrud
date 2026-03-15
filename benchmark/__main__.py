"""CLI entry point for the benchmark module.

Usage::

    uv run python -m benchmark                          # all scenarios
    uv run python -m benchmark --list                   # list scenarios
    uv run python -m benchmark --scenario <name>        # single scenario
    uv run python -m benchmark --config path/to.yaml    # custom config
    uv run python -m benchmark --output-dir ./results   # custom output
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _default_config_path() -> Path:
    """Resolve the default config path relative to *this* package."""
    return Path(__file__).parent / "config.yaml"


def main(argv: list[str] | None = None) -> None:
    """Parse CLI arguments and run (or list) benchmark scenarios."""
    parser = argparse.ArgumentParser(
        prog="benchmark",
        description="AutoCRUD configurable CRUD benchmark suite.",
    )
    parser.add_argument(
        "--config",
        default=str(_default_config_path()),
        help="Path to YAML config (default: benchmark/config.yaml).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Override output directory for results.",
    )
    parser.add_argument(
        "--scenario",
        default=None,
        help="Only run scenarios whose name contains this substring.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_scenarios",
        help="List all configured scenarios and exit.",
    )
    args = parser.parse_args(argv)

    # Late import so --help is fast
    from benchmark.config import load_config
    from benchmark.reporter import print_console, save_charts, save_json
    from benchmark.runner import list_scenarios, run_benchmarks

    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error loading config: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.output_dir:
        config.output_dir = args.output_dir

    # --list mode
    if args.list_scenarios:
        list_scenarios(config)
        return

    # Run benchmarks
    report = run_benchmarks(
        config,
        scenario_filter=args.scenario,
        config_path=args.config,
    )

    # Output results
    print_console(report)
    save_json(report, config.output_dir)
    save_charts(report, config.output_dir)


if __name__ == "__main__":
    main()
