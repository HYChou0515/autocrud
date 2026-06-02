"""Aggregate specs for :meth:`ResourceManager.exp_aggregate_by`.

v1 ships :class:`Count` only. v2 will add ``Sum(field)`` / ``Min(field)`` /
``Max(field)`` / ``Avg(field)`` — same call site, just more keys in the
``aggregates=`` dict; the return shape (``list[GroupRow]``) stays put.
"""

from __future__ import annotations

from typing import Any

import msgspec


class Aggregate(msgspec.Struct, frozen=True):
    """Marker base for aggregate specs (extend in v2: Sum, Min, Max, Avg)."""


class Count(Aggregate, frozen=True):
    """Count rows in the group."""


class GroupRow:
    """One row of an :meth:`exp_aggregate_by` result.

    ``.key`` is the group-by value (or ``None`` when missing); each aggregate
    you named is exposed both as an attribute (``row.count``) and as an item
    (``row["count"]``), so a dict comp like ``{r.key: r.count for r in rows}``
    matches how callers typically reduce single-aggregate results.
    """

    __slots__ = ("key", "_aggregates")

    def __init__(self, key: Any, **aggregates: Any) -> None:
        self.key = key
        self._aggregates = aggregates

    def __getattr__(self, name: str) -> Any:
        try:
            return self._aggregates[name]
        except KeyError as e:
            raise AttributeError(name) from e

    def __getitem__(self, name: str) -> Any:
        return self._aggregates[name]

    def __repr__(self) -> str:
        body = ", ".join(f"{k}={v!r}" for k, v in self._aggregates.items())
        return f"GroupRow(key={self.key!r}, {body})"


__all__ = ["Aggregate", "Count", "GroupRow"]
