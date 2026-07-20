"""Tests for resolving str query_vector → list[float] via encoder at search time."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

import pytest
from msgspec import Struct

from specstar import SpecStar, Vector
from specstar.query_types import (
    DataSearchOperator,
    ResourceMetaSearchQuery,
    VectorDistanceCondition,
    VectorDistanceSort,
)


def _stub_encoder(text: str) -> list[float]:
    # Two text inputs map to opposite-direction vectors so we can assert ordering
    if text == "near_query":
        return [1.0, 0.0]
    if text == "far_query":
        return [0.0, 1.0]
    return [0.5, 0.5]


# Q1: str query_vector in a condition resolved before backend dispatch
def test_q_str_condition_resolved_via_encoder() -> None:
    class Doc(Struct):
        title: str
        embedding: Annotated[list[float], Vector(dim=2, encoder="stub")]

    spec = SpecStar(
        default_user="t",
        default_now=lambda: dt.datetime(2026, 5, 22),
    )
    spec.configure(vector_encoders={"stub": _stub_encoder})
    spec.add_model(Doc)
    mgr = spec.get_resource_manager(Doc)

    mgr.create(Doc(title="aligned", embedding=[1.0, 0.0]))
    mgr.create(Doc(title="opposed", embedding=[0.0, 1.0]))
    mgr.create(Doc(title="close", embedding=[0.9, 0.1]))

    q = ResourceMetaSearchQuery(
        conditions=[
            VectorDistanceCondition(
                field_path="embedding",
                query_vector="near_query",  # str — encoder must resolve
                operator=DataSearchOperator.less_than,
                threshold=0.3,
                distance="cosine",
            ),
        ],
    )
    metas = mgr.search_resources(q)
    titles = sorted(mgr.get(m.resource_id).data.title for m in metas)
    assert "aligned" in titles
    assert "close" in titles
    assert "opposed" not in titles


# Q2: str query_vector in a sort is also resolved
def test_q_str_sort_resolved_via_encoder() -> None:
    class Doc(Struct):
        title: str
        embedding: Annotated[list[float], Vector(dim=2, encoder="stub")]

    spec = SpecStar(
        default_user="t",
        default_now=lambda: dt.datetime(2026, 5, 22),
    )
    spec.configure(vector_encoders={"stub": _stub_encoder})
    spec.add_model(Doc)
    mgr = spec.get_resource_manager(Doc)

    mgr.create(Doc(title="aligned", embedding=[1.0, 0.0]))
    mgr.create(Doc(title="opposed", embedding=[0.0, 1.0]))
    mgr.create(Doc(title="close", embedding=[0.9, 0.1]))

    q = ResourceMetaSearchQuery(
        sorts=[
            VectorDistanceSort(
                field_path="embedding",
                query_vector="near_query",
                distance="cosine",
            ),
        ],
    )
    metas = mgr.search_resources(q)
    titles = [mgr.get(m.resource_id).data.title for m in metas]
    assert titles == ["aligned", "close", "opposed"]


# Q3: async encoder + sync search → raises with clear message
def test_q_async_encoder_in_sync_search_raises() -> None:
    class Doc(Struct):
        title: str
        embedding: Annotated[list[float], Vector(dim=2, encoder="async_stub")]

    async def async_encoder(text: str) -> list[float]:
        return [1.0, 0.0]

    spec = SpecStar(
        default_user="t",
        default_now=lambda: dt.datetime(2026, 5, 22),
    )
    spec.configure(vector_encoders={"async_stub": async_encoder})
    spec.add_model(Doc)
    mgr = spec.get_resource_manager(Doc)
    mgr.create(Doc(title="x", embedding=[1.0, 0.0]))

    q = ResourceMetaSearchQuery(
        conditions=[
            VectorDistanceCondition(
                field_path="embedding",
                query_vector="hello",
                operator=DataSearchOperator.less_than,
                threshold=0.5,
            ),
        ],
    )
    with pytest.raises(RuntimeError, match="async"):
        mgr.search_resources(q)


# Q4: str query_vector + no encoder configured → clear ValueError
def test_q_str_query_without_encoder_raises() -> None:
    class Doc(Struct):
        title: str
        embedding: Annotated[list[float], Vector(dim=2)]  # no encoder

    spec = SpecStar(
        default_user="t",
        default_now=lambda: dt.datetime(2026, 5, 22),
    )
    spec.add_model(Doc)
    mgr = spec.get_resource_manager(Doc)
    mgr.create(Doc(title="x", embedding=[1.0, 0.0]))

    q = ResourceMetaSearchQuery(
        conditions=[
            VectorDistanceCondition(
                field_path="embedding",
                query_vector="hello",
                operator=DataSearchOperator.less_than,
                threshold=0.5,
            ),
        ],
    )
    with pytest.raises(ValueError, match="No encoder"):
        mgr.search_resources(q)
