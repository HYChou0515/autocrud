"""Tests for the ``Embedding`` struct type."""

from __future__ import annotations

from msgspec import UNSET

from specstar.types import Embedding


# E1: tracer
def test_embedding_content_only_defaults_unset() -> None:
    e = Embedding(content="hello world")
    assert e.content == "hello world"
    assert e.vector is UNSET
    assert e.content_hash is UNSET
    assert e.encoder_id is UNSET


# E2: full ctor carries all four fields
def test_embedding_full_ctor() -> None:
    e = Embedding(
        content="hello",
        vector=[0.1, 0.2, 0.3],
        content_hash="abc123",
        encoder_id="openai_small",
    )
    assert e.content == "hello"
    assert e.vector == [0.1, 0.2, 0.3]
    assert e.content_hash == "abc123"
    assert e.encoder_id == "openai_small"


# E3: Embedding (and Vector) are part of the public API
def test_embedding_and_vector_in_public_api() -> None:
    import specstar

    assert specstar.Embedding is Embedding
    from specstar import Vector

    assert hasattr(Vector(dim=1), "dim")
    assert "Embedding" in specstar.__all__
    assert "Vector" in specstar.__all__
