"""Tests for ``specstar.string_ref`` — lazy dotted-path callable."""

from __future__ import annotations

import sys
import types

import specstar


def test_returns_callable_that_resolves_on_first_invoke(monkeypatch) -> None:
    # Tracer: register a fake module with a callable, build a string_ref,
    # and verify the first call resolves and dispatches.
    fake = types.ModuleType("fake_ref_module")

    def fn(*args, **kwargs):
        return ("ok", args, kwargs)

    fake.fn = fn
    monkeypatch.setitem(sys.modules, "fake_ref_module", fake)

    bound = specstar.string_ref("fake_ref_module.fn")
    result = bound("a", k="v")
    assert result == ("ok", ("a",), {"k": "v"})
