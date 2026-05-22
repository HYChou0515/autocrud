"""Tests for the encoder registry and lookup_encoder helper."""

from __future__ import annotations

import pytest

from specstar.resource_manager.encoder_registry import (
    EncoderRegistry,
    lookup_encoder,
)
from specstar.types import Vector, VectorFieldInfo


def _fake_encoder_a(text: str) -> list[float]:
    return [0.1, 0.2]


def _fake_encoder_b(text: str) -> list[float]:
    return [0.3, 0.4]


# ER1: tracer — register + resolve
def test_registry_register_and_resolve() -> None:
    reg = EncoderRegistry()
    reg.register("openai_small", _fake_encoder_a)
    assert reg.resolve("openai_small") is _fake_encoder_a


# ER2: unknown name raises KeyError
def test_registry_unknown_raises() -> None:
    reg = EncoderRegistry()
    with pytest.raises(KeyError):
        reg.resolve("missing")


# ER3: lookup_encoder uses field-level annotation
def test_lookup_field_level_annotation() -> None:
    reg = EncoderRegistry()
    reg.register("openai_small", _fake_encoder_a)
    info = VectorFieldInfo(
        name="embedding",
        marker=Vector(dim=2, encoder="openai_small"),
        is_embedding=False,
        nullable=False,
    )
    assert lookup_encoder(reg, field_info=info) is _fake_encoder_a


# ER4: field-level annotation overrides model-level
def test_lookup_field_overrides_model() -> None:
    reg = EncoderRegistry()
    reg.register("openai_small", _fake_encoder_a)
    reg.register("openai_large", _fake_encoder_b)
    info = VectorFieldInfo(
        name="embedding",
        marker=Vector(dim=2, encoder="openai_small"),  # field-level
        is_embedding=False,
        nullable=False,
    )
    # model_overrides says "openai_large" but field annotation wins
    fn = lookup_encoder(
        reg,
        field_info=info,
        model_overrides={"embedding": "openai_large"},
    )
    assert fn is _fake_encoder_a


# ER5: model-level used when annotation lacks encoder
def test_lookup_model_level_when_annotation_empty() -> None:
    reg = EncoderRegistry()
    reg.register("openai_large", _fake_encoder_b)
    info = VectorFieldInfo(
        name="embedding",
        marker=Vector(dim=2),  # no encoder on annotation
        is_embedding=False,
        nullable=False,
    )
    fn = lookup_encoder(
        reg,
        field_info=info,
        model_overrides={"embedding": "openai_large"},
    )
    assert fn is _fake_encoder_b


# ER6: model_overrides accepts callable directly (not just name string)
def test_lookup_model_level_accepts_callable() -> None:
    reg = EncoderRegistry()  # nothing registered
    info = VectorFieldInfo(
        name="embedding",
        marker=Vector(dim=2),
        is_embedding=False,
        nullable=False,
    )
    fn = lookup_encoder(
        reg,
        field_info=info,
        model_overrides={"embedding": _fake_encoder_b},
    )
    assert fn is _fake_encoder_b


# ER7: returns None when nothing configured
def test_lookup_returns_none_when_unconfigured() -> None:
    reg = EncoderRegistry()
    info = VectorFieldInfo(
        name="embedding",
        marker=Vector(dim=2),
        is_embedding=False,
        nullable=False,
    )
    assert lookup_encoder(reg, field_info=info) is None
    assert lookup_encoder(reg, field_info=info, model_overrides={}) is None
    assert lookup_encoder(reg, field_info=info, model_overrides={"other": "x"}) is None
