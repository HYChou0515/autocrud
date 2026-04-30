"""Generate ``autocrud/events.pyi`` from the live runtime defstruct results.

Why this exists
---------------
``autocrud/events.py`` builds 64 event-context Struct classes via
``msgspec.defstruct(...)`` from a handful of composable atom lists
(``_base_context``, ``_before_context``, ``_create_context``, ...).
This is great for runtime DRY, but ``defstruct`` returns a bare
``type[Struct]`` to static type checkers — the per-class fields are
invisible, and the ``EventContext`` union ends up as ``type[Struct]``
that ty rejects in type expressions.

The fix: keep ``events.py`` as-is and ship a ``.pyi`` stub alongside
it that spells out every class explicitly. Type checkers prefer the
``.pyi`` over the ``.py`` (PEP 484), runtime ignores the stub.

Run with:
    uv run python scripts/gen_events_stub.py > autocrud/events.pyi
or:
    make stubs
"""

from __future__ import annotations

import datetime as dt
import enum
import sys
import types
import typing
from typing import Any, get_args, get_origin

import msgspec

import autocrud.events as ev

SENTINEL_DEFAULT = msgspec.NODEFAULT


def _qualname(t: Any) -> str:
    """Render a type as the short name we already import in the stub."""
    # NoneType
    if t is type(None):
        return "None"
    # bare classes
    if isinstance(t, type):
        # Module-aware short names matching what the stub imports
        if t.__module__ == "builtins":
            return t.__name__
        if t is dt.datetime:
            return "dt.datetime"
        if t.__module__ == "msgspec":
            # UnsetType, etc.
            return t.__name__
        if t.__module__ == "jsonpatch":
            # We re-import as ``from jsonpatch import JsonPatch``
            return t.__name__
        if t.__module__ in ("typing", "collections.abc"):
            # IO, Generator, Sequence, Callable — all imported flat
            return t.__name__
        if t.__module__.startswith("autocrud."):
            return t.__name__
        # Fallback: fully qualified
        return f"{t.__module__}.{t.__name__}"
    # TypeVar
    if isinstance(t, typing.TypeVar):
        return t.__name__
    # repr fallback
    return repr(t)


def _render_type(t: Any) -> str:
    """Render a runtime type back to a stub-source string.

    Handles the type forms we actually encounter in event contexts:
    plain classes, TypeVar, Literal, Union (``X | Y`` and ``Optional``),
    ``Resource[T]`` / generic aliases, and ``None``.
    """
    if t is None or t is type(None):
        return "None"
    if t is Any:
        return "Any"
    if isinstance(t, typing.TypeVar):
        return t.__name__

    origin = get_origin(t)

    # Literal[...]
    if origin is typing.Literal:
        parts = []
        for arg in get_args(t):
            if isinstance(arg, enum.Enum):
                parts.append(f"{type(arg).__name__}.{arg.name}")
            elif isinstance(arg, str):
                parts.append(f'"{arg}"')
            else:
                parts.append(repr(arg))
        return f"Literal[{', '.join(parts)}]"

    # Union (PEP 604 ``X | Y`` shows origin as types.UnionType; legacy Union as typing.Union)
    if origin is typing.Union or origin is types.UnionType:
        return " | ".join(_render_type(a) for a in get_args(t))

    # Generic alias like Resource[T], list[X], etc.
    if origin is not None:
        args = get_args(t)
        rendered_args = ", ".join(_render_type(a) for a in args)
        if isinstance(origin, type):
            return f"{_qualname(origin)}[{rendered_args}]"
        return f"{origin!s}[{rendered_args}]"

    # Plain class / module global
    return _qualname(t)


def _render_default(value: Any) -> str | None:
    """Render a field default. Returns ``None`` if the field has no default."""
    if value is SENTINEL_DEFAULT:
        return None
    if value is msgspec.UNSET:
        return "UNSET"
    if isinstance(value, enum.Enum):
        return f"{type(value).__name__}.{value.name}"
    if isinstance(value, str):
        return f'"{value}"'
    if value is None:
        return "None"
    return repr(value)


def _is_event_context_class(name: str, obj: Any) -> bool:
    if not isinstance(obj, type):
        return False
    if not issubclass(obj, msgspec.Struct):
        return False
    return name.startswith(("Before", "After", "OnSuccess", "OnFailure"))


def _uses_typevar(cls: type) -> bool:
    for f in msgspec.structs.fields(cls):  # ty:ignore[invalid-argument-type]
        if isinstance(f.type, typing.TypeVar):
            return True
        # Handle Generic aliases like Resource[T] containing a TypeVar
        for inner in get_args(f.type):
            if isinstance(inner, typing.TypeVar):
                return True
    return False


def _emit_class(name: str, cls: type, *, generic: bool) -> str:
    fields = msgspec.structs.fields(cls)  # ty:ignore[invalid-argument-type]
    bases = "Struct, Generic[T]" if generic else "Struct"
    lines = [
        f'class {name}({bases}, kw_only=True, tag=True, tag_field="context_type"):'
    ]
    if not fields:
        lines.append("    pass")
        return "\n".join(lines)

    # msgspec orders required fields before defaulted fields automatically.
    for f in fields:
        rendered_type = _render_type(f.type)
        default = _render_default(f.default)
        if default is None:
            lines.append(f"    {f.name}: {rendered_type}")
        else:
            lines.append(f"    {f.name}: {rendered_type} = {default}")
    return "\n".join(lines)


def main() -> None:
    context_classes: list[tuple[str, type]] = []
    for attr in dir(ev):
        obj = getattr(ev, attr)
        if _is_event_context_class(attr, obj):
            context_classes.append((attr, obj))

    # Order: actions in declaration order, phases in fixed cycle.
    # The runtime ``EventContext`` union literal in events.py is
    # incomplete (missing Modify/Migrate at time of writing) — we
    # don't follow it. Instead we order by (action, phase) so the
    # stub is stable regardless of source-file edits.
    phase_order = {"Before": 0, "After": 1, "OnSuccess": 2, "OnFailure": 3}

    def _split(name: str) -> tuple[str, str]:
        for phase in ("OnSuccess", "OnFailure", "Before", "After"):
            if name.startswith(phase):
                return phase, name[len(phase) :]
        raise ValueError(name)

    # Action declaration order = order of first appearance in dir(ev) sorted
    # by source line. Approximate via the runtime class' qualname index.
    action_first_seen: dict[str, int] = {}
    for i, (name, _) in enumerate(context_classes):
        _, action = _split(name)
        action_first_seen.setdefault(action, i)

    ordered = sorted(
        context_classes,
        key=lambda nc: (
            action_first_seen[_split(nc[0])[1]],
            phase_order[_split(nc[0])[0]],
        ),
    )

    out: list[str] = []
    out.append('"""Auto-generated stub for autocrud.events."""')
    out.append("# THIS FILE IS GENERATED — do not edit by hand.")
    out.append("# Regenerate with: make stubs")
    out.append("")
    out.append("from __future__ import annotations")
    out.append("")
    out.append("import datetime as dt")
    out.append("from abc import ABC, abstractmethod")
    out.append("from collections.abc import Callable, Generator, Sequence")
    out.append("from typing import IO, Any, Generic, Protocol, Self, runtime_checkable")
    out.append("")
    out.append("from jsonpatch import JsonPatch")
    out.append("from msgspec import UNSET, Struct, UnsetType")
    out.append("from typing_extensions import Literal")
    out.append("from typing_extensions import TypeVar as TypeVarExt")
    out.append("")
    # Use explicit ``as`` re-exports so ty/pyright honour PEP 484 stub
    # re-export rules: bare ``from X import Y`` in a .pyi is private.
    out.append(
        "from autocrud.query_types import ResourceMetaSearchQuery as ResourceMetaSearchQuery"
    )
    out.append("from autocrud.types import Resource as Resource")
    out.append("from autocrud.types import ResourceAction as ResourceAction")
    out.append("from autocrud.types import ResourceMeta as ResourceMeta")
    out.append("from autocrud.types import RevisionInfo as RevisionInfo")
    out.append("from autocrud.types import RevisionStatus as RevisionStatus")
    out.append("")
    out.append('T = TypeVarExt("T", default=None)')
    out.append("")
    out.append("# ── Structural protocols (re-exported from runtime) ──────")
    out.append("@runtime_checkable")
    out.append("class EventContextProto(Protocol):")
    out.append("    action: ResourceAction")
    out.append("    phase: str")
    out.append("    resource_name: str")
    out.append("")
    out.append("@runtime_checkable")
    out.append("class HasData(EventContextProto, Protocol):")
    out.append("    data: Any")
    out.append("")
    out.append("@runtime_checkable")
    out.append("class HasResourceId(EventContextProto, Protocol):")
    out.append("    resource_id: str")
    out.append("")
    out.append("@runtime_checkable")
    out.append("class HasDataAndResourceId(EventContextProto, Protocol):")
    out.append("    data: Any")
    out.append("    resource_id: str")
    out.append("")
    out.append("@runtime_checkable")
    out.append("class HasRevisionId(HasResourceId, Protocol):")
    out.append("    revision_id: str")
    out.append("")
    out.append("@runtime_checkable")
    out.append("class HasInfo(EventContextProto, Protocol):")
    out.append("    info: RevisionInfo")
    out.append("")
    out.append("# ── Generated event-context classes ──────────────────────")
    out.append("")

    for name, cls in ordered:
        out.append(_emit_class(name, cls, generic=_uses_typevar(cls)))
        out.append("")

    out.append("# ── Union of every event-context class ───────────────────")
    union_names = " | ".join(name for name, _ in ordered)
    out.append(f"EventContext = {union_names}")
    out.append("")
    out.append("ContextFunc = Callable[[EventContext], None]")
    out.append("")
    out.append("# ── Handler interface (mirrors runtime) ──────────────────")
    out.append("class IEventHandler(ABC):")
    out.append("    @abstractmethod")
    out.append("    def is_supported(self, context: EventContext) -> bool: ...")
    out.append("    @abstractmethod")
    out.append("    def handle_event(self, context: EventContext) -> None: ...")
    out.append("")
    out.append("class SimpleEventHandler(IEventHandler):")
    out.append("    func: ContextFunc")
    out.append("    phase: str")
    out.append("    action: ResourceAction")
    out.append("    def __init__(")
    out.append("        self,")
    out.append("        func: ContextFunc,")
    out.append("        phase: str,")
    out.append("        action: ResourceAction,")
    out.append("    ) -> None: ...")
    out.append("    def is_supported(self, context: EventContext) -> bool: ...")
    out.append("    def handle_event(self, context: EventContext) -> None: ...")
    out.append("")
    out.append("class SimpleEventHandlerBuilder(Sequence[SimpleEventHandler]):")
    out.append("    func: list[ContextFunc] | None")
    out.append(
        "    def __init__(self, func: ContextFunc | list[ContextFunc]) -> None: ..."
    )
    out.append("    def __len__(self) -> int: ...")
    # __getitem__ here is a narrower stub than Sequence[T].__getitem__
    # (which also accepts slices); we suppress the override warning.
    out.append(
        "    def __getitem__(self, index: int) -> SimpleEventHandler: ...  # ty: ignore[invalid-method-override]"
    )
    out.append("    def do(self, func: ContextFunc | list[ContextFunc]) -> Self: ...")
    out.append("    def before(self, action: ResourceAction) -> Self: ...")
    out.append("    def after(self, action: ResourceAction) -> Self: ...")
    out.append("    def on_success(self, action: ResourceAction) -> Self: ...")
    out.append("    def on_failure(self, action: ResourceAction) -> Self: ...")
    out.append("")
    out.append(
        "def do(func: ContextFunc | list[ContextFunc]) -> SimpleEventHandlerBuilder: ..."
    )

    sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
