"""Tests for the ``Vector`` annotation marker and ``extract_vectors`` helper."""

from __future__ import annotations

from typing import Annotated

import pytest
from msgspec import Struct

from specstar.types import Vector, extract_vectors


class _FakeEmbedding(Struct):
    """Placeholder representing the future Embedding type, used by B7."""

    content: str


# B1: tracer
def test_vector_dim_only_defaults() -> None:
    v = Vector(dim=1536)
    assert v.dim == 1536
    assert v.distance is None
    assert v.encoder is None


# B2: full params carried
def test_vector_full_params() -> None:
    v = Vector(dim=1536, distance="cosine", encoder="openai_small")
    assert v.dim == 1536
    assert v.distance == "cosine"
    assert v.encoder == "openai_small"


# B3: extract_vectors single field
def test_extract_vectors_single_field() -> None:
    class Doc(Struct):
        title: str
        embedding: Annotated[list[float], Vector(dim=1536, distance="cosine")]

    pairs = extract_vectors(Doc)
    assert len(pairs) == 1
    name, marker = pairs[0]
    assert name == "embedding"
    assert marker.dim == 1536
    assert marker.distance == "cosine"


# B4: extract_vectors preserves definition order
def test_extract_vectors_preserves_order() -> None:
    class Doc(Struct):
        title: str
        body_vec: Annotated[list[float], Vector(dim=3072)]
        author: str
        title_vec: Annotated[list[float], Vector(dim=512)]

    pairs = extract_vectors(Doc)
    assert [name for name, _ in pairs] == ["body_vec", "title_vec"]
    assert pairs[0][1].dim == 3072
    assert pairs[1][1].dim == 512


# B5: extract_vectors empty when no annotations
def test_extract_vectors_empty() -> None:
    class Plain(Struct):
        title: str
        age: int

    assert extract_vectors(Plain) == []


# B6: extract_vectors handles nullable list[float] | None
def test_extract_vectors_nullable() -> None:
    class Doc(Struct):
        title: str
        embedding: Annotated[list[float] | None, Vector(dim=1536)] = None

    pairs = extract_vectors(Doc)
    assert len(pairs) == 1
    name, marker = pairs[0]
    assert name == "embedding"
    assert marker.dim == 1536


# B7: extract_vectors works on any inner type (Embedding placeholder)
def test_extract_vectors_arbitrary_inner_type() -> None:
    class Doc(Struct):
        summary: Annotated[_FakeEmbedding, Vector(dim=1536, encoder="openai_small")]

    pairs = extract_vectors(Doc)
    assert len(pairs) == 1
    name, marker = pairs[0]
    assert name == "summary"
    assert marker.encoder == "openai_small"


# B8: Vector(dim<=0) raises
@pytest.mark.parametrize("bad_dim", [0, -1, -1536])
def test_vector_rejects_non_positive_dim(bad_dim: int) -> None:
    with pytest.raises(ValueError):
        Vector(dim=bad_dim)


# B9: Vector(distance=invalid) raises; valid values stay accepted
def test_vector_rejects_invalid_distance() -> None:
    with pytest.raises(ValueError):
        Vector(dim=1536, distance="bogus")  # type: ignore[arg-type]


@pytest.mark.parametrize("good_distance", ["cosine", "l2", "ip", None])
def test_vector_accepts_known_distances(good_distance) -> None:
    v = Vector(dim=1536, distance=good_distance)
    assert v.distance == good_distance


# B10: __eq__ and __hash__ consistency — usable as dict / set keys
def test_vector_equality_and_hash() -> None:
    a = Vector(dim=1536, distance="cosine", encoder="openai_small")
    b = Vector(dim=1536, distance="cosine", encoder="openai_small")
    c = Vector(dim=1536, distance="cosine", encoder="openai_large")  # different encoder
    d = Vector(dim=512, distance="cosine", encoder="openai_small")  # different dim

    # equal Vectors compare equal and hash the same
    assert a == b
    assert hash(a) == hash(b)

    # different Vectors are not equal
    assert a != c
    assert a != d

    # usable in a set: duplicates collapse
    assert len({a, b, c, d}) == 3

    # non-Vector comparison returns NotImplemented → False
    assert a != "not a vector"
