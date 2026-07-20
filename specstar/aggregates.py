"""Aggregate specs for :meth:`ResourceManager.exp_aggregate_by`.

Shipped: :class:`Count`, :class:`Sum`, :class:`Min`, :class:`Max`, :class:`Avg`
+ :class:`ForeignAggregate` for cross-RM. Aggregate fields and the foreign
``link`` are typed as :class:`~specstar.query.Field` (i.e. you pass them as
``QB["..."]`` for indexed data or ``QB.<name>()`` for ResourceMeta attributes)
so the data/meta routing is unambiguous — no name-collision footgun.

The ``exp_`` prefix on the method advertises that this API may still adjust
before stabilising as ``aggregate_by``.
"""

from __future__ import annotations

from typing import Any

from specstar.query import Field


class Aggregate:
    """Marker base for aggregate specs."""

    __slots__ = ()


class Count(Aggregate):
    """Count rows in the group."""

    __slots__ = ()


class _FieldAggregate(Aggregate):
    """Internal base for aggregates that reduce a single field."""

    __slots__ = ("field",)

    def __init__(self, field: Field) -> None:
        if not isinstance(field, Field):
            raise TypeError(
                f"{type(self).__name__} requires a QB Field "
                f'(e.g. QB["size"] or QB.created_time()); '
                f"got {type(field).__name__}."
            )
        self.field = field

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}({self.field.name!r}, source={self.field.source!r})"
        )


class Sum(_FieldAggregate):
    """Sum a numeric field across the group; ``None`` values are skipped.

    Returns ``None`` if the group has no non-``None`` value (SQL semantics).
    Raises ``TypeError`` if a non-numeric value is encountered.
    """

    __slots__ = ()


class Min(_FieldAggregate):
    """Min of a field across the group (``None``-skipping). Returns ``None``
    if the group has no non-``None`` value. Uses Python ``<`` ordering, so the
    field's values must be mutually comparable (numbers, datetimes, strings).
    """

    __slots__ = ()


class Max(_FieldAggregate):
    """Max of a field across the group (``None``-skipping). Returns ``None``
    if the group has no non-``None`` value."""

    __slots__ = ()


class Avg(_FieldAggregate):
    """Average a numeric field across the group (``None``-skipping).

    Returns a ``float``, or ``None`` if the group has no non-``None`` value.
    Raises ``TypeError`` if a non-numeric value is encountered.
    """

    __slots__ = ()


class CountDistinct(_FieldAggregate):
    """Count the DISTINCT non-``None`` values of a field across the group —
    SQL ``COUNT(DISTINCT f)``. Unlike ``Sum``/``Min``/``Max``/``Avg`` the field
    need not be numeric (distinctness is defined for any type).

    Returns an ``int`` (``0`` for a group whose values are all ``None``). This is
    the natural primitive for disagreement detection: group a fact table by a key
    and a group with ``CountDistinct(value) > 1`` holds conflicting values.
    """

    __slots__ = ()


class ForeignAggregate:
    """Aggregate over another resource's rows, linked back to this resource.

    Use inside :meth:`ResourceManager.exp_aggregate_by` to annotate each parent
    row with a reduction over its children — e.g. *"this doc's chunk count"*
    or *"this customer's order total"*. ``rm`` is the **child** manager,
    ``link`` is a :class:`~specstar.query.Field` on the child that holds the
    parent ``resource_id`` (almost always ``QB["..."]``), and ``aggregate`` is
    what to compute over the children of each parent.
    """

    __slots__ = ("rm", "link", "aggregate")

    def __init__(self, rm: object, link: Field, aggregate: Aggregate) -> None:
        if not isinstance(link, Field):
            raise TypeError(
                f"ForeignAggregate.link must be a QB Field "
                f'(e.g. QB["source_doc_id"]); got {type(link).__name__}.'
            )
        if not isinstance(aggregate, Aggregate):
            raise TypeError(
                f"ForeignAggregate.aggregate must be an Aggregate; "
                f"got {type(aggregate).__name__}."
            )
        self.rm = rm
        self.link = link
        self.aggregate = aggregate


class GroupRow:
    """One row of an :meth:`exp_aggregate_by` result.

    ``.key`` is the group-by value (or ``None`` when missing). When the call
    grouped by ``QB.resource_id()`` (each group is exactly one row of *this*
    RM), ``.resource`` carries that row's
    :class:`~specstar.types.SearchedResource` — that's the cross-RM case
    (e.g. *"list each doc and its chunk count"*). For any other ``by``,
    ``.resource`` is ``None`` because a group could span many rows.

    Each named aggregate is exposed both as an attribute (``row.count``) and
    as an item (``row["count"]``), so a dict comp like
    ``{r.key: r.count for r in rows}`` works for single-aggregate results.
    """

    __slots__ = ("key", "resource", "_aggregates")

    def __init__(self, key: Any, *, resource: Any = None, **aggregates: Any) -> None:
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
    "CountDistinct",
    "ForeignAggregate",
    "GroupRow",
    "Max",
    "Min",
    "Sum",
]
