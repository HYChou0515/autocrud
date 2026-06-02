"""Aggregate specs for :meth:`ResourceManager.exp_aggregate_by`.

Shipped: :class:`Count`, :class:`Sum`, :class:`Min`, :class:`Max`, :class:`Avg`.
Pass several at once in the ``aggregates=`` dict — each becomes a named field
on the returned :class:`GroupRow`. The ``exp_`` prefix on the method advertises
that the API may still adjust before stabilising as ``aggregate_by``.
"""

from __future__ import annotations

from typing import Any

import msgspec


class Aggregate(msgspec.Struct, frozen=True):
    """Marker base for aggregate specs."""


class Count(Aggregate, frozen=True):
    """Count rows in the group."""


class Sum(Aggregate, frozen=True):
    """Sum a numeric field across the group; ``None`` values are skipped.

    Returns ``None`` if the group has no non-``None`` value (SQL semantics).
    Raises ``TypeError`` if a non-numeric value is encountered.
    """

    field: str


class Min(Aggregate, frozen=True):
    """Min of a field across the group (``None``-skipping). Returns ``None``
    if the group has no non-``None`` value. Uses Python ``<`` ordering, so the
    field's values must be mutually comparable (numbers, datetimes, strings).
    """

    field: str


class Max(Aggregate, frozen=True):
    """Max of a field across the group (``None``-skipping). Returns ``None``
    if the group has no non-``None`` value."""

    field: str


class Avg(Aggregate, frozen=True):
    """Average a numeric field across the group (``None``-skipping).

    Returns a ``float``, or ``None`` if the group has no non-``None`` value.
    Raises ``TypeError`` if a non-numeric value is encountered.
    """

    field: str


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


__all__ = ["Aggregate", "Avg", "Count", "GroupRow", "Max", "Min", "Sum"]
