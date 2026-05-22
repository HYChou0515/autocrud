"""Lazy string-reference helpers used by spec-driven codegen.

``string_ref("my_app.logic.fn")`` returns a callable that resolves the
dotted path via importlib on first invocation, caches the target, and
forwards subsequent calls to it. This lets ``_generated.py`` wire up
hooks like ``id_generator=specstar.string_ref("my_app.logic.gen_id")``
without importing the user's package at module-top time (which the AST
validator blocks).
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any


def resolve(target: str) -> Callable[..., Any]:
    """Resolve a dotted ``module.path.attr`` reference. Raises early."""
    if "." not in target:
        raise ValueError(
            f"string reference {target!r} must be a dotted path like "
            "'my_app.logic.fn_name'"
        )
    module_name, _, attr = target.rpartition(".")
    module = importlib.import_module(module_name)
    return getattr(module, attr)


def string_ref(target: str) -> Callable[..., Any]:
    """Return a callable that lazy-resolves ``target`` on first invocation.

    Example::

        spec.add_model(
            Book,
            name="book",
            id_generator=specstar.string_ref("my_app.logic.gen_book_id"),
        )
    """
    cache: list[Callable[..., Any] | None] = [None]

    def _call(*args: Any, **kwargs: Any) -> Any:
        if cache[0] is None:
            cache[0] = resolve(target)
        return cache[0](*args, **kwargs)

    _call.__name__ = f"string_ref({target!r})"
    return _call
