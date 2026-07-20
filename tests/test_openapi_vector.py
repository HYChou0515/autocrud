"""Tests for OpenAPI x-vector-* extension injection."""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI
from msgspec import Struct

from specstar import Embedding, SpecStar, Vector


# OA1: x-vector-dim appears on the OpenAPI property for a Vector field
def test_oa_x_vector_dim_injected() -> None:
    class Doc(Struct):
        title: str
        embedding: Annotated[list[float], Vector(dim=1536)]

    app = FastAPI(title="oa-vector")
    spec = SpecStar()
    spec.add_model(Doc)
    spec.apply(app)
    spec.openapi(app)

    schema = app.openapi_schema
    components = schema["components"]["schemas"]
    # Find the Doc component (name may be prefixed)
    doc_comp = next(c for n, c in components.items() if n.endswith("Doc") or n == "Doc")
    prop = doc_comp["properties"]["embedding"]
    assert prop.get("x-vector-dim") == 1536


# OA2: distance and encoder also injected when present on annotation
def test_oa_x_vector_distance_and_encoder() -> None:
    class Doc(Struct):
        summary: Annotated[
            Embedding,
            Vector(dim=1536, distance="cosine", encoder="openai_small"),
        ]

    app = FastAPI(title="oa-vector-full")
    spec = SpecStar()
    spec.add_model(Doc)
    spec.apply(app)
    spec.openapi(app)

    schema = app.openapi_schema
    components = schema["components"]["schemas"]
    doc_comp = next(c for n, c in components.items() if n.endswith("Doc") or n == "Doc")
    prop = doc_comp["properties"]["summary"]
    assert prop.get("x-vector-dim") == 1536
    assert prop.get("x-vector-distance") == "cosine"
    assert prop.get("x-vector-encoder-id") == "openai_small"


# OA2 cont: omitted annotation fields → omitted from OpenAPI
def test_oa_no_x_vector_distance_when_unset() -> None:
    class Doc(Struct):
        embedding: Annotated[list[float], Vector(dim=512)]

    app = FastAPI(title="oa-vector-min")
    spec = SpecStar()
    spec.add_model(Doc)
    spec.apply(app)
    spec.openapi(app)

    schema = app.openapi_schema
    components = schema["components"]["schemas"]
    doc_comp = next(c for n, c in components.items() if n.endswith("Doc") or n == "Doc")
    prop = doc_comp["properties"]["embedding"]
    assert prop.get("x-vector-dim") == 512
    assert "x-vector-distance" not in prop
    assert "x-vector-encoder-id" not in prop
