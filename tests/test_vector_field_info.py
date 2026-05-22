"""Tests for ``extract_vector_field_infos`` — richer extractor returning
(name, marker, is_embedding, nullable) for each Vector-annotated field.

Used downstream by EmbeddingProcessor and the dim validator.
"""

from __future__ import annotations

from typing import Annotated

from msgspec import Struct

from specstar.types import Embedding, Vector, extract_vector_field_infos


# VF1: tracer — raw list[float] field
def test_vf_raw_vector_field() -> None:
    class Doc(Struct):
        embedding: Annotated[list[float], Vector(dim=1536)]

    infos = extract_vector_field_infos(Doc)
    assert len(infos) == 1
    info = infos[0]
    assert info.name == "embedding"
    assert info.marker.dim == 1536
    assert info.is_embedding is False
    assert info.nullable is False


# VF2: Embedding-typed field reports is_embedding=True
def test_vf_embedding_field() -> None:
    class Doc(Struct):
        summary: Annotated[Embedding, Vector(dim=1536, encoder="openai_small")]

    infos = extract_vector_field_infos(Doc)
    assert len(infos) == 1
    info = infos[0]
    assert info.name == "summary"
    assert info.is_embedding is True
    assert info.nullable is False


# VF3: Annotated[list[float] | None, Vector(...)] → nullable=True
def test_vf_nullable_raw_vector() -> None:
    class Doc(Struct):
        embedding: Annotated[list[float] | None, Vector(dim=1536)] = None

    infos = extract_vector_field_infos(Doc)
    assert len(infos) == 1
    info = infos[0]
    assert info.name == "embedding"
    assert info.is_embedding is False
    assert info.nullable is True


# VF4: Annotated[Embedding | None, Vector(...)] → nullable=True, is_embedding=True
def test_vf_nullable_embedding() -> None:
    class Doc(Struct):
        body: Annotated[Embedding | None, Vector(dim=3072, encoder="openai_large")] = (
            None
        )

    infos = extract_vector_field_infos(Doc)
    assert len(infos) == 1
    info = infos[0]
    assert info.name == "body"
    assert info.is_embedding is True
    assert info.nullable is True
    assert info.marker.encoder == "openai_large"
