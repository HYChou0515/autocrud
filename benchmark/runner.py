"""Benchmark runner — orchestrates scenario execution.

Reads a :class:`~benchmark.config.BenchmarkConfig`, iterates over each
scenario, builds the appropriate AutoCRUD instance, runs the requested
CRUD operations, and collects results into a :class:`BenchmarkReport`.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console

from benchmark.config import BenchmarkConfig, ScenarioConfig
from benchmark.models import MODEL_REGISTRY
from benchmark.operations import (
    OperationResult,
    bench_create,
    bench_delete,
    bench_get,
    bench_list_resources,
    bench_modify,
    bench_patch,
    bench_restore,
    bench_search,
    bench_switch,
    bench_update,
)
from benchmark.storage import build_storage_factory, check_availability, cleanup_storage

console = Console()


# ---------------------------------------------------------------------------
# Report containers
# ---------------------------------------------------------------------------


@dataclass
class ScenarioResult:
    """Results from a single benchmark scenario."""

    name: str
    storage: str
    encoding: str
    model: str
    n: int
    operations: dict[str, OperationResult] = field(default_factory=dict)
    skipped: bool = False
    skip_reason: str = ""


@dataclass
class BenchmarkReport:
    """Aggregated results from all scenarios."""

    timestamp: str = ""
    config_path: str = ""
    scenarios: list[ScenarioResult] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (for JSON output)."""
        return {
            "timestamp": self.timestamp,
            "config_path": self.config_path,
            "scenarios": [
                {
                    "name": s.name,
                    "storage": s.storage,
                    "encoding": s.encoding,
                    "model": s.model,
                    "n": s.n,
                    "skipped": s.skipped,
                    "skip_reason": s.skip_reason,
                    "operations": {k: v.as_dict() for k, v in s.operations.items()},
                }
                for s in self.scenarios
            ],
        }


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------


def _run_scenario(
    scenario: ScenarioConfig,
    config: BenchmarkConfig,
) -> ScenarioResult:
    """Execute a single benchmark scenario.

    Args:
        scenario: The scenario configuration.
        config: Global benchmark configuration (for defaults).

    Returns:
        A :class:`ScenarioResult` with timing data for each operation.
    """
    from autocrud.crud.core import AutoCRUD
    from autocrud.resource_manager.basic import Encoding

    n = scenario.n or config.default_n
    warmup = scenario.warmup or config.default_warmup
    repeat = scenario.repeat or config.default_repeat
    _ = warmup  # reserved for future warmup logic

    model_info = MODEL_REGISTRY[scenario.model]
    encoding = Encoding(scenario.encoding)
    storage_cfg = config.storage[scenario.storage]

    # Check availability
    available, reason = check_availability(storage_cfg.name, storage_cfg.params)
    if not available:
        return ScenarioResult(
            name=scenario.name,
            storage=scenario.storage,
            encoding=scenario.encoding,
            model=scenario.model,
            n=n,
            skipped=True,
            skip_reason=reason,
        )

    result = ScenarioResult(
        name=scenario.name,
        storage=scenario.storage,
        encoding=scenario.encoding,
        model=scenario.model,
        n=n,
    )

    # Teardown leftover artefacts from previous runs
    cleanup_storage(storage_cfg.name, storage_cfg.params)

    # Build AutoCRUD instance per scenario (isolated)
    storage_factory = build_storage_factory(
        storage_cfg.name, storage_cfg.params, encoding
    )
    crud = AutoCRUD(storage_factory=storage_factory, encoding=encoding)
    crud.add_model(
        model_info.struct_type,
        indexed_fields=model_info.indexed_fields,
    )
    rm = crud.get_resource_manager(model_info.struct_type)

    # Generate test data (repeat * n for multiple rounds)
    total_data_needed = n * repeat
    all_data = model_info.generate(total_data_needed)

    # All operations run inside meta_provide context
    with rm.meta_provide("benchmark-user", dt.datetime.now(dt.timezone.utc)):
        ops = scenario.operations

        # Track resource IDs across operations within each round
        all_results: dict[str, list[OperationResult]] = {op: [] for op in ops}

        for r in range(repeat):
            round_data = all_data[r * n : (r + 1) * n]
            resource_ids: list[str] = []

            # --- CREATE (or seed data for later operations) ---
            if "create" in ops:
                cr = bench_create(rm, round_data)
                all_results["create"].append(cr)
                resource_ids = cr._resource_ids  # type: ignore[attr-defined]
            else:
                # Seed data silently for other operations
                for data in round_data:
                    info = rm.create(data)
                    resource_ids.append(info.resource_id)

            # --- GET ---
            if "get" in ops and resource_ids:
                all_results["get"].append(bench_get(rm, resource_ids))

            # --- SEARCH ---
            if "search" in ops:
                all_results["search"].append(bench_search(rm, n))

            # --- LIST_RESOURCES ---
            if "list_resources" in ops:
                all_results["list_resources"].append(bench_list_resources(rm, n))

            # --- PATCH ---
            if "patch" in ops and resource_ids:
                all_results["patch"].append(bench_patch(rm, resource_ids))

            # --- MODIFY ---
            if "modify" in ops:
                update_data = model_info.generate(min(n, len(resource_ids)))
                all_results["modify"].append(
                    bench_modify(rm, resource_ids, update_data)
                )

            # --- UPDATE ---
            if "update" in ops and resource_ids:
                update_data = model_info.generate(len(resource_ids))
                all_results["update"].append(
                    bench_update(rm, resource_ids, update_data)
                )

            # --- SWITCH ---
            if "switch" in ops:
                switch_data = model_info.generate(min(n, len(resource_ids)))
                all_results["switch"].append(
                    bench_switch(rm, resource_ids, switch_data)
                )

            # --- RESTORE (delete then restore) ---
            if "restore" in ops and resource_ids:
                all_results["restore"].append(bench_restore(rm, resource_ids))

            # --- DELETE ---
            if "delete" in ops and resource_ids:
                # Restore any soft-deleted resources first (from restore op)
                for rid in resource_ids:
                    try:
                        rm.restore(rid)
                    except Exception:
                        pass
                all_results["delete"].append(bench_delete(rm, resource_ids))

            # Cleanup remaining resources for this round
            for rid in resource_ids:
                try:
                    rm.delete(rid)
                except Exception:
                    pass
                try:
                    rm.permanently_delete(rid)
                except Exception:
                    pass

        # Merge repeated rounds into a single OperationResult per operation
        for op in ops:
            rounds = all_results.get(op, [])
            if not rounds:
                continue
            merged_timings: list[float] = []
            for rr in rounds:
                merged_timings.extend(rr.timings)
            from benchmark.operations import _build_result

            result.operations[op] = _build_result(op, merged_timings)

    # Cleanup storage artefacts
    cleanup_storage(storage_cfg.name, storage_cfg.params)

    return result


def run_benchmarks(
    config: BenchmarkConfig,
    *,
    scenario_filter: str | None = None,
    config_path: str = "",
) -> BenchmarkReport:
    """Run all (or filtered) benchmark scenarios.

    Args:
        config: Parsed benchmark configuration.
        scenario_filter: If set, only run scenarios whose name contains
            this substring.
        config_path: Path to the config file (for metadata).

    Returns:
        A :class:`BenchmarkReport` with all scenario results.
    """
    report = BenchmarkReport(
        timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
        config_path=config_path,
    )

    scenarios = config.scenarios
    if scenario_filter:
        scenarios = [s for s in scenarios if scenario_filter in s.name]

    if not scenarios:
        console.print("[yellow]No matching scenarios found.[/yellow]")
        return report

    console.print(f"\n[bold]Running {len(scenarios)} benchmark scenario(s)...[/bold]\n")

    for i, scenario in enumerate(scenarios, 1):
        console.print(
            f"[cyan][{i}/{len(scenarios)}][/cyan] {scenario.name} "
            f"(storage={scenario.storage}, encoding={scenario.encoding}, "
            f"model={scenario.model})"
        )

        sr = _run_scenario(scenario, config)
        report.scenarios.append(sr)

        if sr.skipped:
            console.print(f"  [yellow]SKIPPED[/yellow]: {sr.skip_reason}")
        else:
            op_count = len(sr.operations)
            console.print(f"  [green]DONE[/green]: {op_count} operation(s) benchmarked")

    console.print("\n[bold green]Benchmark complete.[/bold green]\n")
    return report


# ---------------------------------------------------------------------------
# Listing helper
# ---------------------------------------------------------------------------


def list_scenarios(config: BenchmarkConfig) -> None:
    """Print all configured scenarios and their storage availability."""
    from rich.table import Table

    table = Table(title="Benchmark Scenarios", show_lines=True)
    table.add_column("Scenario", style="bold")
    table.add_column("Storage")
    table.add_column("Encoding")
    table.add_column("Model")
    table.add_column("N")
    table.add_column("Operations")
    table.add_column("Available", justify="center")

    for s in config.scenarios:
        n = s.n or config.default_n
        storage_cfg = config.storage.get(s.storage)
        if storage_cfg:
            available, reason = check_availability(storage_cfg.name, storage_cfg.params)
            avail_str = "[green]✓[/green]" if available else f"[red]✗[/red] {reason}"
        else:
            avail_str = "[red]✗ not configured[/red]"

        table.add_row(
            s.name,
            s.storage,
            s.encoding,
            s.model,
            str(n),
            ", ".join(s.operations),
            avail_str,
        )

    console.print(table)
