"""Tests for ``StringRefConstraintChecker`` — lazy dotted-path
constraint checker used by spec-driven codegen.

Lets ``_generated.py`` write ``constraint_checkers=[
StringRefConstraintChecker("my_app.logic.X")]`` without importing
the user package at module-top time (which the AST validator blocks
and which would also break ``specstar lock``).
"""

from __future__ import annotations

from specstar.resource_manager import StringRefConstraintChecker
from specstar.types import IConstraintChecker


def test_is_a_constraint_checker() -> None:
    # Tracer: the wrapper must implement IConstraintChecker so it can
    # sit directly in ``constraint_checkers=[...]`` (which iterates
    # entries and dispatches IConstraintChecker.check, not factory).
    c = StringRefConstraintChecker("any.module.fn")
    assert isinstance(c, IConstraintChecker)


def test_check_lazy_resolves_user_function(monkeypatch) -> None:
    # check() must dispatch to the dotted reference, passing through
    # the keyword-only ``exclude_resource_id`` arg.
    import sys
    import types

    calls: list[tuple[object, str | None]] = []

    def my_check(data, *, exclude_resource_id=None):
        calls.append((data, exclude_resource_id))

    fake = types.ModuleType("fake_constraint_module")
    fake.my_check = my_check
    monkeypatch.setitem(sys.modules, "fake_constraint_module", fake)

    c = StringRefConstraintChecker("fake_constraint_module.my_check")
    c.check("payload", exclude_resource_id="r-7")
    assert calls == [("payload", "r-7")]
