"""Tests for ``_VectorDimValidator`` — write-time dim validation."""

from __future__ import annotations

from typing import Annotated

import pytest
from msgspec import Struct

from specstar.resource_manager.vector_validator import VectorDimValidator
from specstar.types import Embedding, ValidationError, Vector


# DV1: tracer — raw list[float] dim mismatch raises
def test_dv_raw_vector_dim_mismatch_raises() -> None:
    class Doc(Struct):
        embedding: Annotated[list[float], Vector(dim=4)]

    validator = VectorDimValidator(Doc)
    bad = Doc(embedding=[0.1, 0.2])  # len=2, expected=4
    with pytest.raises(ValidationError):
        validator.validate(bad)


# DV2: matching dim passes
def test_dv_matching_dim_passes() -> None:
    class Doc(Struct):
        embedding: Annotated[list[float], Vector(dim=4)]

    validator = VectorDimValidator(Doc)
    ok = Doc(embedding=[0.1, 0.2, 0.3, 0.4])
    validator.validate(ok)  # no exception


# DV3: nullable raw vector with None passes
def test_dv_nullable_raw_vector_none_passes() -> None:
    class Doc(Struct):
        embedding: Annotated[list[float] | None, Vector(dim=4)] = None

    validator = VectorDimValidator(Doc)
    validator.validate(Doc(embedding=None))  # no exception


# DV4: Embedding(vector=wrong_len) raises
def test_dv_embedding_vector_dim_mismatch_raises() -> None:
    class Doc(Struct):
        summary: Annotated[Embedding, Vector(dim=4)]

    validator = VectorDimValidator(Doc)
    bad = Doc(summary=Embedding(content="hi", vector=[0.1, 0.2]))  # len=2
    with pytest.raises(ValidationError):
        validator.validate(bad)


# DV5: Embedding without vector (UNSET) passes — processor will fill it
def test_dv_embedding_unset_vector_passes() -> None:
    class Doc(Struct):
        summary: Annotated[Embedding, Vector(dim=4)]

    validator = VectorDimValidator(Doc)
    # vector defaults to UNSET when user just provides content
    validator.validate(Doc(summary=Embedding(content="hi")))  # no exception


# DV6: error message contains field name, expected dim, actual dim
def test_dv_error_message_includes_expected_and_actual() -> None:
    class Doc(Struct):
        embedding: Annotated[list[float], Vector(dim=1536)]

    validator = VectorDimValidator(Doc)
    bad = Doc(embedding=[0.1, 0.2, 0.3])  # len=3, expected=1536
    with pytest.raises(ValidationError) as exc_info:
        validator.validate(bad)
    msg = str(exc_info.value)
    assert "embedding" in msg
    assert "1536" in msg
    assert "3" in msg


# DV7: model without vector fields → validator is a noop
def test_dv_noop_when_no_vector_fields() -> None:
    class Plain(Struct):
        title: str
        age: int

    validator = VectorDimValidator(Plain)
    validator.validate(Plain(title="hi", age=20))  # no exception
