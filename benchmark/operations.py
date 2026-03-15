"""Individual CRUD operation benchmarks.

Each public function accepts a :class:`~autocrud.types.IResourceManager`,
pre-generated data, and timing parameters, then returns an
:class:`OperationResult` with statistical summaries.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any

from autocrud.query import QB
from autocrud.types import RevisionStatus

# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class OperationResult:
    """Statistical summary of a single benchmark operation."""

    operation: str
    n: int
    total_time: float = 0.0
    avg_time: float = 0.0
    min_time: float = 0.0
    max_time: float = 0.0
    p50: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    throughput: float = 0.0  # ops/sec
    timings: list[float] = field(default_factory=list, repr=False)

    def as_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict (for JSON output)."""
        return {
            "operation": self.operation,
            "n": self.n,
            "total_time_s": round(self.total_time, 6),
            "avg_time_s": round(self.avg_time, 9),
            "min_time_s": round(self.min_time, 9),
            "max_time_s": round(self.max_time, 9),
            "p50_s": round(self.p50, 9),
            "p95_s": round(self.p95, 9),
            "p99_s": round(self.p99, 9),
            "throughput_ops_s": round(self.throughput, 2),
        }


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Return the *pct*-th percentile from a **sorted** list."""
    if not sorted_values:
        return 0.0
    idx = (len(sorted_values) - 1) * pct / 100.0
    lo = int(idx)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = idx - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def _build_result(operation: str, timings: list[float]) -> OperationResult:
    """Create an :class:`OperationResult` from a list of per-op durations."""
    n = len(timings)
    if n == 0:
        return OperationResult(operation=operation, n=0)
    s = sorted(timings)
    total = sum(s)
    return OperationResult(
        operation=operation,
        n=n,
        total_time=total,
        avg_time=total / n,
        min_time=s[0],
        max_time=s[-1],
        p50=_percentile(s, 50),
        p95=_percentile(s, 95),
        p99=_percentile(s, 99),
        throughput=n / total if total > 0 else 0.0,
        timings=s,
    )


# ---------------------------------------------------------------------------
# Benchmark helpers
# ---------------------------------------------------------------------------


def _time_call(fn, *args, **kwargs) -> tuple[Any, float]:
    """Call *fn* and return ``(result, elapsed_seconds)``."""
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed = time.perf_counter() - t0
    return result, elapsed


# ---------------------------------------------------------------------------
# Operation benchmarks
# ---------------------------------------------------------------------------


def bench_create(rm, data_list: list[dict]) -> OperationResult:
    """Benchmark ``rm.create(data)`` for each item in *data_list*.

    Returns:
        OperationResult with per-create timings.
        Also stores created resource_ids in ``result.timings`` attribute's
        companion — access ``_resource_ids`` on the returned object.
    """
    timings: list[float] = []
    resource_ids: list[str] = []
    for data in data_list:
        info, elapsed = _time_call(rm.create, data)
        timings.append(elapsed)
        resource_ids.append(info.resource_id)
    result = _build_result("create", timings)
    result._resource_ids = resource_ids  # type: ignore[attr-defined]
    return result


def bench_get(rm, resource_ids: list[str]) -> OperationResult:
    """Benchmark ``rm.get(resource_id)`` for each ID."""
    timings: list[float] = []
    ids = list(resource_ids)
    random.shuffle(ids)
    for rid in ids:
        _, elapsed = _time_call(rm.get, rid)
        timings.append(elapsed)
    return _build_result("get", timings)


def bench_update(rm, resource_ids: list[str], data_list: list[dict]) -> OperationResult:
    """Benchmark ``rm.update(resource_id, data)``."""
    timings: list[float] = []
    for rid, data in zip(resource_ids, data_list):
        _, elapsed = _time_call(rm.update, rid, data)
        timings.append(elapsed)
    return _build_result("update", timings)


def bench_delete(rm, resource_ids: list[str]) -> OperationResult:
    """Benchmark ``rm.delete(resource_id)``."""
    timings: list[float] = []
    for rid in resource_ids:
        _, elapsed = _time_call(rm.delete, rid)
        timings.append(elapsed)
    return _build_result("delete", timings)


def bench_search(rm, n: int) -> OperationResult:
    """Benchmark ``rm.search_resources(query)`` with a simple query.

    Runs *n* individual search queries, each looking up a random limit.
    """
    timings: list[float] = []
    for _ in range(n):
        query = QB["name"].is_truthy().limit(random.randint(1, 50))
        _, elapsed = _time_call(rm.search_resources, query)
        timings.append(elapsed)
    return _build_result("search", timings)


def bench_patch(rm, resource_ids: list[str]) -> OperationResult:
    """Benchmark ``rm.patch(resource_id, patch_data)`` (RFC 6902)."""
    from jsonpatch import JsonPatch

    timings: list[float] = []
    for rid in resource_ids:
        patch = JsonPatch(
            [{"op": "replace", "path": "/name", "value": f"patched-{rid[:8]}"}]
        )
        _, elapsed = _time_call(rm.patch, rid, patch)
        timings.append(elapsed)
    return _build_result("patch", timings)


def bench_modify(rm, resource_ids: list[str], data_list: list[dict]) -> OperationResult:
    """Benchmark ``rm.modify(resource_id, data)`` (draft resources only).

    Creates draft resources first, then measures modify timing.
    """
    # First ensure resources are in draft status
    draft_ids: list[str] = []
    draft_data: list[dict] = []
    for data in data_list[: len(resource_ids)]:
        info = rm.create(data, status=RevisionStatus.draft)
        draft_ids.append(info.resource_id)
        draft_data.append(data)

    timings: list[float] = []
    for rid, data in zip(draft_ids, draft_data):
        data_copy = dict(data)
        data_copy["name"] = f"modified-{rid[:8]}"
        _, elapsed = _time_call(rm.modify, rid, data_copy)
        timings.append(elapsed)

    # Cleanup draft resources
    for rid in draft_ids:
        try:
            rm.delete(rid)
            rm.permanently_delete(rid)
        except Exception:
            pass

    return _build_result("modify", timings)


def bench_switch(rm, resource_ids: list[str], data_list: list[dict]) -> OperationResult:
    """Benchmark ``rm.switch(resource_id, revision_id)``.

    Creates a second revision via update, then switches back to the first.
    """
    # Create resources with two revisions each
    switch_targets: list[tuple[str, str]] = []
    for data in data_list[: len(resource_ids)]:
        info1 = rm.create(data)
        data_copy = dict(data)
        data_copy["name"] = f"v2-{info1.resource_id[:8]}"
        rm.update(info1.resource_id, data_copy)
        switch_targets.append((info1.resource_id, info1.revision_id))

    timings: list[float] = []
    for rid, rev_id in switch_targets:
        _, elapsed = _time_call(rm.switch, rid, rev_id)
        timings.append(elapsed)

    # Cleanup
    for rid, _ in switch_targets:
        try:
            rm.delete(rid)
            rm.permanently_delete(rid)
        except Exception:
            pass

    return _build_result("switch", timings)


def bench_restore(rm, resource_ids: list[str]) -> OperationResult:
    """Benchmark ``rm.restore(resource_id)`` by soft-deleting then restoring."""
    # Create and delete resources
    restore_ids: list[str] = []
    for rid in resource_ids:
        # These should already exist — soft-delete them
        try:
            rm.delete(rid)
            restore_ids.append(rid)
        except Exception:
            pass

    timings: list[float] = []
    for rid in restore_ids:
        _, elapsed = _time_call(rm.restore, rid)
        timings.append(elapsed)
    return _build_result("restore", timings)


def bench_list_resources(rm, n: int) -> OperationResult:
    """Benchmark ``rm.list_resources(query)``."""
    timings: list[float] = []
    for _ in range(n):
        query = QB["name"].is_truthy().limit(random.randint(1, 50))
        _, elapsed = _time_call(rm.list_resources, query, returns=["data", "meta"])
        timings.append(elapsed)
    return _build_result("list_resources", timings)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

OPERATION_MAP: dict[str, str] = {
    "create": "bench_create",
    "get": "bench_get",
    "update": "bench_update",
    "delete": "bench_delete",
    "search": "bench_search",
    "patch": "bench_patch",
    "modify": "bench_modify",
    "switch": "bench_switch",
    "restore": "bench_restore",
    "list_resources": "bench_list_resources",
}
