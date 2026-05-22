"""Distance metrics for brute-force vector search (memory / disk / sqlite)."""

from __future__ import annotations

import math
from typing import Literal

DistanceMetric = Literal["cosine", "l2", "ip"]


def cosine_distance(a: list[float], b: list[float]) -> float:
    """Return ``1 - cos(a, b)`` — matches pgvector's ``<=>`` operator.

    Range: [0, 2].  Zero vectors return ``1.0`` (max distance).
    """
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 1.0
    return 1.0 - dot / (math.sqrt(na) * math.sqrt(nb))


def l2_distance(a: list[float], b: list[float]) -> float:
    """Return Euclidean distance — matches pgvector's ``<->`` operator."""
    s = 0.0
    for x, y in zip(a, b):
        d = x - y
        s += d * d
    return math.sqrt(s)


def ip_distance(a: list[float], b: list[float]) -> float:
    """Return ``-dot(a, b)`` — matches pgvector's ``<#>`` operator.

    Negative inner product so that lower = more similar (consistent with
    cosine / L2 semantics where smaller is closer).
    """
    return -sum(x * y for x, y in zip(a, b))


def distance(
    a: list[float], b: list[float], metric: DistanceMetric = "cosine"
) -> float:
    if metric == "cosine":
        return cosine_distance(a, b)
    if metric == "l2":
        return l2_distance(a, b)
    if metric == "ip":
        return ip_distance(a, b)
    raise ValueError(f"Unknown distance metric: {metric!r}")
