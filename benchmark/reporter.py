"""Benchmark result reporters.

Three output formats:

1. **Console** — rich table printed to stdout.
2. **JSON** — machine-readable result file.
3. **Chart** — matplotlib bar charts and heatmap.
"""

from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from benchmark.runner import BenchmarkReport

console = Console()


# ---------------------------------------------------------------------------
# 1. Console table
# ---------------------------------------------------------------------------


def print_console(report: BenchmarkReport) -> None:
    """Print a rich table summarising every scenario × operation."""
    for sr in report.scenarios:
        if sr.skipped:
            console.print(f"\n[yellow]● {sr.name}[/yellow] — SKIPPED: {sr.skip_reason}")
            continue

        table = Table(
            title=f"[bold]{sr.name}[/bold]  "
            f"(storage={sr.storage}, encoding={sr.encoding}, "
            f"model={sr.model}, n={sr.n})",
            show_lines=True,
        )
        table.add_column("Operation", style="bold")
        table.add_column("N", justify="right")
        table.add_column("Avg (ms)", justify="right")
        table.add_column("P50 (ms)", justify="right")
        table.add_column("P95 (ms)", justify="right")
        table.add_column("P99 (ms)", justify="right")
        table.add_column("Min (ms)", justify="right")
        table.add_column("Max (ms)", justify="right")
        table.add_column("Throughput", justify="right", style="green")

        for op_name, op_result in sr.operations.items():
            table.add_row(
                op_name,
                str(op_result.n),
                f"{op_result.avg_time * 1000:.3f}",
                f"{op_result.p50 * 1000:.3f}",
                f"{op_result.p95 * 1000:.3f}",
                f"{op_result.p99 * 1000:.3f}",
                f"{op_result.min_time * 1000:.3f}",
                f"{op_result.max_time * 1000:.3f}",
                f"{op_result.throughput:.0f} ops/s",
            )

        console.print(table)


# ---------------------------------------------------------------------------
# 2. JSON file
# ---------------------------------------------------------------------------


def save_json(report: BenchmarkReport, output_dir: str | Path) -> Path:
    """Write the full report to a JSON file.

    Args:
        report: The benchmark report.
        output_dir: Directory to write the JSON file into.

    Returns:
        Path to the written file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    data: dict[str, Any] = report.as_dict()
    data["system"] = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "processor": platform.processor(),
        "machine": platform.machine(),
    }

    ts = report.timestamp.replace(":", "-").replace("+", "p")[:19]
    filepath = output_dir / f"benchmark-{ts}.json"
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)

    console.print(f"[dim]JSON saved → {filepath}[/dim]")
    return filepath


# ---------------------------------------------------------------------------
# 3. Matplotlib charts
# ---------------------------------------------------------------------------


def save_charts(report: BenchmarkReport, output_dir: str | Path) -> list[Path]:
    """Generate and save benchmark charts.

    Args:
        report: The benchmark report.
        output_dir: Directory to write PNG files into.

    Returns:
        List of paths to generated chart files.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        console.print(
            "[yellow]matplotlib not installed — skipping chart generation.[/yellow]"
        )
        return []

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []

    active = [s for s in report.scenarios if not s.skipped]
    if not active:
        return saved

    # --- Chart 1: Throughput by scenario × operation (grouped bar) ---
    saved.extend(_chart_throughput_grouped(active, output_dir, plt))

    # --- Chart 2: Avg latency comparison ---
    saved.extend(_chart_latency_comparison(active, output_dir, plt))

    # --- Chart 3: Throughput heatmap ---
    saved.extend(_chart_throughput_heatmap(active, output_dir, plt))

    return saved


def _chart_throughput_grouped(scenarios, output_dir: Path, plt) -> list[Path]:
    """Grouped bar chart: throughput for each scenario × operation."""
    saved: list[Path] = []

    # Collect all unique operations
    all_ops: list[str] = []
    for s in scenarios:
        for op in s.operations:
            if op not in all_ops:
                all_ops.append(op)

    if not all_ops:
        return saved

    import numpy as np

    fig, ax = plt.subplots(figsize=(max(10, len(scenarios) * 2), 6))

    x = np.arange(len(all_ops))
    width = 0.8 / max(len(scenarios), 1)

    for i, s in enumerate(scenarios):
        throughputs = []
        for op in all_ops:
            if op in s.operations:
                throughputs.append(s.operations[op].throughput)
            else:
                throughputs.append(0)
        offset = (i - len(scenarios) / 2 + 0.5) * width
        ax.bar(x + offset, throughputs, width, label=s.name)

    ax.set_xlabel("Operation")
    ax.set_ylabel("Throughput (ops/s)")
    ax.set_yscale("log")
    ax.set_title("Throughput by Scenario and Operation")
    ax.set_xticks(x)
    ax.set_xticklabels(all_ops, rotation=30, ha="right")
    ax.legend(fontsize="small", loc="upper right")
    fig.tight_layout()

    path = output_dir / "throughput_grouped.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    saved.append(path)
    console.print(f"[dim]Chart saved → {path}[/dim]")
    return saved


def _chart_latency_comparison(scenarios, output_dir: Path, plt) -> list[Path]:
    """Bar chart: avg latency per operation across scenarios."""
    saved: list[Path] = []

    all_ops: list[str] = []
    for s in scenarios:
        for op in s.operations:
            if op not in all_ops:
                all_ops.append(op)

    if not all_ops:
        return saved

    import numpy as np

    fig, ax = plt.subplots(figsize=(max(10, len(scenarios) * 2), 6))

    x = np.arange(len(all_ops))
    width = 0.8 / max(len(scenarios), 1)

    for i, s in enumerate(scenarios):
        latencies = []
        for op in all_ops:
            if op in s.operations:
                latencies.append(s.operations[op].avg_time * 1000)  # ms
            else:
                latencies.append(0)
        offset = (i - len(scenarios) / 2 + 0.5) * width
        ax.bar(x + offset, latencies, width, label=s.name)

    ax.set_xlabel("Operation")
    ax.set_ylabel("Avg Latency (ms)")
    ax.set_yscale("log")
    ax.set_title("Average Latency by Scenario and Operation")
    ax.set_xticks(x)
    ax.set_xticklabels(all_ops, rotation=30, ha="right")
    ax.legend(fontsize="small", loc="upper right")
    fig.tight_layout()

    path = output_dir / "latency_comparison.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    saved.append(path)
    console.print(f"[dim]Chart saved → {path}[/dim]")
    return saved


def _chart_throughput_heatmap(scenarios, output_dir: Path, plt) -> list[Path]:
    """Heatmap: scenario (y) × operation (x) → throughput."""
    saved: list[Path] = []

    all_ops: list[str] = []
    for s in scenarios:
        for op in s.operations:
            if op not in all_ops:
                all_ops.append(op)

    if not all_ops or len(scenarios) < 2:
        return saved

    import numpy as np
    from matplotlib.colors import LogNorm

    data = np.zeros((len(scenarios), len(all_ops)))
    for i, s in enumerate(scenarios):
        for j, op in enumerate(all_ops):
            if op in s.operations:
                data[i, j] = s.operations[op].throughput

    # Replace zeros with NaN so LogNorm doesn't choke on log(0)
    plot_data = data.copy()
    plot_data[plot_data == 0] = np.nan
    vmin = np.nanmin(plot_data) if np.any(~np.isnan(plot_data)) else 1
    vmax = np.nanmax(plot_data) if np.any(~np.isnan(plot_data)) else 1

    fig, ax = plt.subplots(
        figsize=(max(8, len(all_ops) * 1.2), max(4, len(scenarios) * 0.6))
    )
    im = ax.imshow(
        plot_data, aspect="auto", cmap="YlOrRd", norm=LogNorm(vmin=vmin, vmax=vmax)
    )

    ax.set_xticks(np.arange(len(all_ops)))
    ax.set_yticks(np.arange(len(scenarios)))
    ax.set_xticklabels(all_ops, rotation=30, ha="right")
    ax.set_yticklabels([s.name for s in scenarios])

    # Annotate cells
    log_mid = np.exp((np.log(vmin) + np.log(vmax)) / 2) if vmin > 0 else vmax * 0.5
    for i in range(len(scenarios)):
        for j in range(len(all_ops)):
            val = data[i, j]
            if val > 0:
                ax.text(
                    j,
                    i,
                    f"{val:.0f}",
                    ha="center",
                    va="center",
                    fontsize=7,
                    color="white" if val > log_mid else "black",
                )

    ax.set_title("Throughput Heatmap (ops/s, log scale)")
    fig.colorbar(im, ax=ax, label="ops/s")
    fig.tight_layout()

    path = output_dir / "throughput_heatmap.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    saved.append(path)
    console.print(f"[dim]Chart saved → {path}[/dim]")
    return saved
