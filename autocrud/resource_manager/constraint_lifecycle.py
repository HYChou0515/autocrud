"""Constraint lifecycle helpers for :class:`ResourceManager`.

Two responsibilities live here:

1. ``build_constraint_handler`` — turn the ``constraint_checkers`` parameter
   accepted by :class:`ResourceManager` into a
   :class:`ConstraintEventHandler`, resolving callable factories along the
   way.

2. ``register_unique_fields`` — auto-detect ``Unique``-annotated fields on
   the resource type and append a :class:`UniqueConstraintChecker` to the
   constraint event handler (creating one on demand if absent).

Both functions take the :class:`ResourceManager` they operate on as a plain
argument; they do not import from :mod:`autocrud.resource_manager.core` so
they are safe to import from anywhere.
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
    """Resolve ``constraint_checkers`` specs into a ConstraintEventHandler.

    Each item may be an :class:`IConstraintChecker` instance or a callable
    accepting the owning :class:`ResourceManager` and returning one.  A
    :class:`ConstraintEventHandler` is returned only when the list resolves
    to at least one checker; otherwise ``None``.

    The caller is responsible for appending the returned handler to
    ``rm.event_handlers`` — this keeps ordering decisions (constraint
    handlers run after permission handlers) at the call site.
    """
    _checkers: list[IConstraintChecker] = []
    for spec in constraint_checkers or []:
        if isinstance(spec, IConstraintChecker):
            _checkers.append(spec)
        elif callable(spec):
            _checkers.append(spec(rm))
        else:
            raise TypeError(
                f"constraint_checkers items must be IConstraintChecker instances "
                f"or callable(rm) factories, got {type(spec).__name__}"
            )
    if not _checkers:
        return None

    from autocrud.resource_manager.constraint_handler import (
        ConstraintEventHandler,
    )

    return ConstraintEventHandler(rm, _checkers)


def register_unique_fields(rm: ResourceManager) -> ConstraintEventHandler | None:
    """Auto-detect ``Unique``-annotated fields and ensure a checker covers them.

    If the resource type has no fields annotated with ``Unique``, returns
    ``None`` and leaves the manager untouched.  Otherwise, ensures a
    :class:`ConstraintEventHandler` exists on ``rm.event_handlers`` (reusing
    one if present, creating one if not) and appends a freshly-built
    :class:`UniqueConstraintChecker`.

    Returns the (existing or newly-attached) handler so the caller can keep
    a reference on the manager.
    """
    from autocrud.resource_manager.constraint_handler import (
        ConstraintEventHandler,
    )
    from autocrud.resource_manager.unique_handler import UniqueConstraintChecker
    from autocrud.types import extract_unique_fields

    if not extract_unique_fields(rm.resource_type):
        return None

    existing_handler = next(
        (h for h in rm.event_handlers if isinstance(h, ConstraintEventHandler)),
        None,
    )
    if existing_handler is not None:
        # User's checkers and auto-detected ones may protect different
        # fields; both should run.
        existing_handler.checkers.append(UniqueConstraintChecker(rm))
        return existing_handler

    handler = ConstraintEventHandler(rm, [UniqueConstraintChecker(rm)])
    rm.event_handlers.append(handler)
    return handler
