"""Encoder registry for Vector / Embedding fields.

Encoders convert ``str`` to ``list[float]`` (sync or async).  They are
registered by name and resolved at write/query time via the override
hierarchy: ``Vector(encoder=...)`` > ``add_model(vector_encoders=...)``
> ``spec.configure(vector_encoders=...)``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from specstar.types import VectorFieldInfo


class EncoderRegistry:
    """Maps encoder names to callables."""

    def __init__(self) -> None:
        self._encoders: dict[str, Callable] = {}

    def register(self, name: str, fn: Callable) -> None:
        self._encoders[name] = fn

    def resolve(self, name: str) -> Callable:
        return self._encoders[name]


def lookup_encoder(
    registry: "EncoderRegistry",
    *,
    field_info: "VectorFieldInfo",
    model_overrides: "dict[str, str | Callable] | None" = None,
) -> Callable | None:
    """Resolve the encoder for a Vector-annotated field.

    Override hierarchy (inner overrides outer): annotation > model > global.
    Returns ``None`` if no encoder is configured anywhere.
    """
    # Field-level (annotation) wins
    if field_info.marker.encoder is not None:
        try:
            return registry.resolve(field_info.marker.encoder)
        except KeyError:
            return None
    # Model-level fallback
    if model_overrides and field_info.name in model_overrides:
        ref = model_overrides[field_info.name]
        if callable(ref):
            return ref
        try:
            return registry.resolve(ref)
        except KeyError:
            return None
    return None
