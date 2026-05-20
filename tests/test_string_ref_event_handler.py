"""Tests for ``StringRefEventHandler`` — a lazy dotted-path event handler
used by spec-driven codegen.

The class lets ``_generated.py`` write
``event_handlers=[StringRefEventHandler("my_app.logic.fn", phase="after",
action=ResourceAction.create)]`` without importing the user's logic
module at module-top time. The dotted target is resolved on first
``handle_event`` call.
"""

from __future__ import annotations

from unittest.mock import Mock

from specstar.events import IEventHandler, StringRefEventHandler
from specstar.types import ResourceAction


def test_is_an_event_handler() -> None:
    # Tracer: the new class plugs into ``event_handlers=[...]`` slot,
    # which requires conformance to the IEventHandler ABC.
    h = StringRefEventHandler(
        "any.module.fn", phase="after", action=ResourceAction.create
    )
    assert isinstance(h, IEventHandler)


def test_is_supported_matches_phase_and_action() -> None:
    h = StringRefEventHandler(
        "any.module.fn", phase="after", action=ResourceAction.create
    )
    ctx = Mock(phase="after", action=ResourceAction.create)
    assert h.is_supported(ctx) is True


def test_is_supported_rejects_wrong_phase() -> None:
    h = StringRefEventHandler(
        "any.module.fn", phase="after", action=ResourceAction.create
    )
    ctx = Mock(phase="before", action=ResourceAction.create)
    assert h.is_supported(ctx) is False


def test_is_supported_rejects_wrong_action() -> None:
    h = StringRefEventHandler(
        "any.module.fn", phase="after", action=ResourceAction.create
    )
    ctx = Mock(phase="after", action=ResourceAction.delete)
    assert h.is_supported(ctx) is False


def test_is_supported_matches_any_action_in_flag_combo() -> None:
    # ResourceAction is a Flag, so ``ResourceAction.write`` (= create |
    # update | modify | patch) matches a context.action of any one of
    # those. StringRefEventHandler must inherit that semantic from the
    # ``in`` operator just like SimpleEventHandler does.
    h = StringRefEventHandler(
        "any.module.fn",
        phase="after",
        action=ResourceAction.write,
    )
    ctx = Mock(phase="after", action=ResourceAction.update)
    assert h.is_supported(ctx) is True


def test_handle_event_lazy_imports_and_calls_target(monkeypatch) -> None:
    # Tracer for lazy resolution: register a fake module in sys.modules
    # with a callable attribute, then verify handle_event imports it
    # and dispatches the context.
    import sys
    import types

    calls: list[object] = []

    def captured_fn(ctx: object) -> None:
        calls.append(ctx)

    fake_module = types.ModuleType("fake_workflow_module")
    fake_module.captured_fn = captured_fn
    monkeypatch.setitem(sys.modules, "fake_workflow_module", fake_module)

    h = StringRefEventHandler(
        "fake_workflow_module.captured_fn",
        phase="after",
        action=ResourceAction.create,
    )
    ctx = Mock(phase="after", action=ResourceAction.create)
    h.handle_event(ctx)
    assert calls == [ctx]


def test_handle_event_caches_resolved_callable(monkeypatch) -> None:
    # Second dispatch must reuse the resolved attribute, not re-import.
    # Otherwise hot-event handlers pay an importlib lookup per fire.
    import importlib
    import sys
    import types

    calls: list[object] = []

    def captured_fn(ctx: object) -> None:
        calls.append(ctx)

    fake_module = types.ModuleType("fake_cache_module")
    fake_module.captured_fn = captured_fn
    monkeypatch.setitem(sys.modules, "fake_cache_module", fake_module)

    import_calls: list[str] = []
    real_import = importlib.import_module

    def counting_import(name: str, package: str | None = None):
        import_calls.append(name)
        return real_import(name, package)

    monkeypatch.setattr(importlib, "import_module", counting_import)

    h = StringRefEventHandler(
        "fake_cache_module.captured_fn",
        phase="after",
        action=ResourceAction.create,
    )
    ctx = Mock(phase="after", action=ResourceAction.create)
    h.handle_event(ctx)
    h.handle_event(ctx)
    h.handle_event(ctx)

    assert calls == [ctx, ctx, ctx]
    assert import_calls.count("fake_cache_module") == 1, (
        "importlib.import_module must run only on the first dispatch; "
        "subsequent dispatches reuse the cached callable"
    )


def test_malformed_target_raises_value_error() -> None:
    # No dot in target → no module/attr split possible. Fail loudly so
    # the spec-driven authoring loop catches the typo and can self-
    # correct via the feedback-retry loop.
    h = StringRefEventHandler(
        "no_dot_here", phase="after", action=ResourceAction.create
    )
    ctx = Mock(phase="after", action=ResourceAction.create)
    import pytest

    with pytest.raises(ValueError, match="dotted path"):
        h.handle_event(ctx)


def test_unknown_module_raises_import_error() -> None:
    h = StringRefEventHandler(
        "definitely.not.a.real.module.fn",
        phase="after",
        action=ResourceAction.create,
    )
    ctx = Mock(phase="after", action=ResourceAction.create)
    import pytest

    with pytest.raises(ImportError):
        h.handle_event(ctx)


def test_unknown_attribute_raises_attribute_error(monkeypatch) -> None:
    import sys
    import types

    fake_module = types.ModuleType("fake_missing_attr_module")
    monkeypatch.setitem(sys.modules, "fake_missing_attr_module", fake_module)

    h = StringRefEventHandler(
        "fake_missing_attr_module.missing_fn",
        phase="after",
        action=ResourceAction.create,
    )
    ctx = Mock(phase="after", action=ResourceAction.create)
    import pytest

    with pytest.raises(AttributeError):
        h.handle_event(ctx)


def test_is_in_public_events_all() -> None:
    # Public API: the spec-driven STEP 2 prompt will instruct the LLM
    # to write ``from specstar.events import StringRefEventHandler``.
    # The name must be in ``specstar.events.__all__`` so static-export
    # checks and ``from specstar.events import *`` style usage discover
    # it.
    import specstar.events as ev

    assert "StringRefEventHandler" in ev.__all__
