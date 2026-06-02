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


class ForeignAggregate:
    """Aggregate over another resource's rows, linked back to this resource.

    Use inside :meth:`ResourceManager.exp_list_with_aggregates` to annotate each
    parent row with a reduction over its children — e.g. *"this doc's chunk
    count"* or *"this customer's order total"*. ``rm`` is the **child** manager,
    ``link`` is the child field that holds the parent ``resource_id``, and
    ``aggregate`` is what to compute over the children of each parent.
    """

    __slots__ = ("rm", "link", "aggregate")

    def __init__(self, rm: object, link: str, aggregate: Aggregate) -> None:
        if not isinstance(aggregate, Aggregate):
            raise TypeError(
                f"aggregate must be an Aggregate; got {type(aggregate).__name__}."
            )
        self.rm = rm
        self.link = link
        self.aggregate = aggregate


class GroupRow:
    """One row of an :meth:`exp_aggregate_by` result.

    ``.key`` is the group-by value (or ``None`` when missing). When the call
    grouped by ``"resource_id"`` (each group is exactly one row of *this* RM),
    ``.resource`` carries that row's :class:`~specstar.types.SearchedResource`
    — that's the cross-RM case (e.g. *"list each doc and its chunk count"*).
    For any other ``by``, ``.resource`` is ``None`` because a group could span
    many rows.

    Each named aggregate is exposed both as an attribute (``row.count``) and
    as an item (``row["count"]``), so a dict comp like
    ``{r.key: r.count for r in rows}`` works for single-aggregate results.
    """

    __slots__ = ("key", "resource", "_aggregates")

    def __init__(
        self, key: Any, *, resource: Any = None, **aggregates: Any
    ) -> None:
        self.key = key
        self.resource = resource
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
        extras = f", resource={self.resource!r}" if self.resource is not None else ""
        return f"GroupRow(key={self.key!r}{extras}, {body})"


__all__ = [
    "Aggregate",
    "Avg",
    "Count",
    "ForeignAggregate",
    "GroupRow",
    "Max",
    "Min",
    "Sum",
]
