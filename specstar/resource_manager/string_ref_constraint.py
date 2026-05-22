"""Lazy dotted-path constraint checker.

Lets ``_generated.py`` declare ``constraint_checkers=[
StringRefConstraintChecker("my_app.logic.check_isbn")]`` without
forcing an early import of the user package. The user-side function
is resolved on first ``check()`` call.

The user function signature must mirror ``IConstraintChecker.check``::

    def check_isbn(data, *, exclude_resource_id=None) -> None: ...
"""

from __future__ import annotations

from typing import Any

from specstar.refs import resolve
from specstar.types import IConstraintChecker


class StringRefConstraintChecker(IConstraintChecker):
    """An ``IConstraintChecker`` that lazy-resolves a dotted reference."""

    def __init__(self, target: str):
        self.target = target
        self._resolved = None

    def check(self, data: Any, *, exclude_resource_id: str | None = None) -> None:
        if self._resolved is None:
            self._resolved = resolve(self.target)
        self._resolved(data, exclude_resource_id=exclude_resource_id)
