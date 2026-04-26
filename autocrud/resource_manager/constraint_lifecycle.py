"""Constraint lifecycle helpers for :class:`ResourceManager`.

Exposes :func:`build_constraint_handler`, which resolves the
``constraint_checkers`` parameter accepted by :class:`ResourceManager`
and auto-detects ``Unique``-annotated fields on the resource type into
a single :class:`ConstraintEventHandler`.

The function takes the :class:`ResourceManager` it operates on as a plain
argument; it does not import from :mod:`autocrud.resource_manager.core`
so it is safe to import from anywhere.

The function is **pure**: it never mutates ``rm.event_handlers``.  The
caller is responsible for installing the returned handler so that
ordering decisions (constraint handlers run after permission handlers)
stay at the call site.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from autocrud.types import IConstraintChecker

if TYPE_CHECKING:
    from autocrud.resource_manager.constraint_handler import (
        ConstraintEventHandler,
    )
    from autocrud.resource_manager.core import ResourceManager


def build_constraint_handler(
    rm: ResourceManager,
    constraint_checkers: Sequence[
        IConstraintChecker | Callable[[ResourceManager], IConstraintChecker]
    ]
    | None,
) -> ConstraintEventHandler | None:
    """Build the single :class:`ConstraintEventHandler` for ``rm``.

    Resolves user-supplied ``constraint_checkers`` (each item may be an
    :class:`IConstraintChecker` instance or a callable accepting the owning
    :class:`ResourceManager` and returning one) and auto-attaches a
    :class:`UniqueConstraintChecker` whenever the resource type carries
    ``Unique``-annotated fields.

    Returns ``None`` only when the resource has no user checkers and no
    ``Unique`` fields; otherwise returns a single handler that wraps every
    checker.  The caller is responsible for appending it to
    ``rm.event_handlers``.
    """
    from autocrud.resource_manager.constraint_handler import (
        ConstraintEventHandler,
    )
    from autocrud.resource_manager.unique_handler import UniqueConstraintChecker
    from autocrud.types import extract_unique_fields

    checkers: list[IConstraintChecker] = []
    for spec in constraint_checkers or []:
        if isinstance(spec, IConstraintChecker):
            checkers.append(spec)
        elif callable(spec):
            checkers.append(spec(rm))
        else:
            raise TypeError(
                f"constraint_checkers items must be IConstraintChecker instances "
                f"or callable(rm) factories, got {type(spec).__name__}"
            )

    if extract_unique_fields(rm.resource_type):
        checkers.append(UniqueConstraintChecker(rm))

    if not checkers:
        return None
    return ConstraintEventHandler(rm, checkers)
