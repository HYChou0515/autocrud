"""Executable tests for every code example in docs/en/howto/vector-search.md.

If any of these fail, either the docs are wrong or there's a real bug.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated

import pytest
from msgspec import Struct

from specstar import Embedding, SpecStar, ValidationError, Vector
from specstar.query import QB


# A tiny deterministic 2-D encoder for tests.
# Maps a few well-known strings to specific vectors so we can assert ordering.
def _embed(text: str) -> list[float]:
    if "near" in text or "aligned" in text or "hello" in text:
        return [1.0, 0.0]
    if "far" in text or "orthogonal" in text or "goodbye" in text:
        return [0.0, 1.0]
    return [0.7, 0.7]


def _new_spec() -> SpecStar:
    s = SpecStar(
        default_user="tester",
        default_now=lambda: dt.datetime(2026, 5, 22),
    )
    return s


# D1: TL;DR — Embedding field + QB.cosine on string query, with scalar filter
def test_docs_tldr_runs_end_to_end() -> None:
    class Doc(Struct):
        title: str
        doctype: str
        summary: Annotated[Embedding, Vector(dim=2, encoder="my_embed")]

    spec = _new_spec()
    spec.configure(vector_encoders={"my_embed": _embed})
    spec.add_model(Doc, indexed_fields=["doctype"])
    mgr = spec.get_resource_manager(Doc)

    mgr.create(
        Doc(title="a-near", doctype="article", summary=Embedding(content="hello world"))
    )
    mgr.create(
        Doc(
            title="b-far",
            doctype="article",
            summary=Embedding(content="orthogonal text"),
        )
    )
    mgr.create(
        Doc(title="c-wrong-type", doctype="memo", summary=Embedding(content="hello"))
    )

    query = (
        ((QB["doctype"] == "article") & (QB["summary"].cosine("near_query") < 0.3))
        .sort(QB["summary"].cosine("near_query"))
        .limit(3)
        .build()
    )

    results = mgr.list_resources(query, returns=["data"])
    titles = [r.data.title for r in results]
    # only "article" doctype docs near "hello"-style vector should appear
    assert "a-near" in titles
    assert "b-far" not in titles
    assert "c-wrong-type" not in titles


# D2: Level 1 — raw list[float] vector field, user supplies the vector
def test_docs_level1_raw_vector() -> None:
    class Doc(Struct):
        title: str
        embedding: Annotated[list[float], Vector(dim=2, distance="cosine")]

    spec = _new_spec()
    spec.add_model(Doc)
    mgr = spec.get_resource_manager(Doc)

    my_vector = [1.0, 0.0]
    info = mgr.create(Doc(title="t", embedding=my_vector))
    assert mgr.get(info.resource_id).data.embedding == my_vector

    # Query by raw vector
    q = (QB["embedding"].cosine([1.0, 0.0]) < 0.1).build()
    results = mgr.list_resources(q, returns=["data"])
    assert [r.data.title for r in results] == ["t"]


# D3: Level 2 — Embedding(content=...) is enough; framework fills vector
def test_docs_level2_embedding_auto_fill() -> None:
    call_count = 0

    def counting_embed(text: str) -> list[float]:
        nonlocal call_count
        call_count += 1
        return _embed(text)

    class Doc(Struct):
        title: str
        summary: Annotated[
            Embedding,
            Vector(dim=2, distance="cosine", encoder="openai_small"),
        ]

    spec = _new_spec()
    spec.configure(vector_encoders={"openai_small": counting_embed})
    spec.add_model(Doc)
    mgr = spec.get_resource_manager(Doc)

    info = mgr.create(Doc(title="t", summary=Embedding(content="hello")))
    stored = mgr.get(info.resource_id).data
    assert stored.summary.vector == [1.0, 0.0]
    assert stored.summary.content_hash  # filled
    assert stored.summary.encoder_id == "openai_small"
    assert call_count == 1

    # Cache reuse: same content → encoder NOT called again
    mgr.update(
        info.resource_id,
        Doc(title="t2", summary=Embedding(content="hello")),
    )
    assert call_count == 1


# D4: encoder override hierarchy (field > model > global)
def test_docs_encoder_override_hierarchy() -> None:
    def embed_small(text: str) -> list[float]:
        return [0.1, 0.2]

    def embed_large(text: str) -> list[float]:
        return [0.9, 0.9]

    class Doc(Struct):
        title: str
        summary: Annotated[
            Embedding,
            Vector(dim=2, encoder="openai_small"),  # field-level wins
        ]

    spec = _new_spec()
    # global registry
    spec.configure(
        vector_encoders={
            "openai_small": embed_small,
            "openai_large": embed_large,
        }
    )
    # per-model override → ignored because annotation pins openai_small
    spec.add_model(Doc, vector_encoders={"summary": "openai_large"})
    mgr = spec.get_resource_manager(Doc)

    info = mgr.create(Doc(title="t", summary=Embedding(content="x")))
    stored = mgr.get(info.resource_id).data
    assert stored.summary.vector == [0.1, 0.2]  # field-level encoder won
    assert stored.summary.encoder_id == "openai_small"


# D5: QB compose — scalar AND vector filter + vector sort + limit
def test_docs_qb_compose() -> None:
    class Doc(Struct):
        title: str
        doctype: str
        embedding: Annotated[list[float], Vector(dim=2)]

    spec = _new_spec()
    spec.add_model(Doc, indexed_fields=["doctype"])
    mgr = spec.get_resource_manager(Doc)

    mgr.create(Doc(title="x1", doctype="article", embedding=[1.0, 0.0]))  # near
    mgr.create(Doc(title="x2", doctype="article", embedding=[0.9, 0.1]))  # near
    mgr.create(Doc(title="y1", doctype="article", embedding=[0.0, 1.0]))  # far
    mgr.create(Doc(title="z1", doctype="memo", embedding=[1.0, 0.0]))  # wrong type

    q = [1.0, 0.0]
    query = (
        ((QB["doctype"] == "article") & (QB["embedding"].cosine(q) < 0.3))
        .sort(QB["embedding"].cosine(q))
        .limit(10)
        .build()
    )
    results = mgr.list_resources(query, returns=["data"])
    titles = [r.data.title for r in results]
    # x1 (exactly aligned) first, then x2 (close); y1 too far, z1 wrong type
    assert titles == ["x1", "x2"]


# D6: §8 Validation — error message format matches what the docs promise
def test_docs_validation_error_format() -> None:
    class Doc(Struct):
        title: str
        embedding: Annotated[list[float], Vector(dim=1536)]

    spec = _new_spec()
    spec.add_model(Doc)
    mgr = spec.get_resource_manager(Doc)

    with pytest.raises(ValidationError) as exc_info:
        mgr.create(Doc(title="t", embedding=[0.1, 0.2]))
    msg = str(exc_info.value)
    # docs say: "Vector field 'embedding': expected dim=1536, got 512"
    assert "embedding" in msg
    assert "expected dim=1536" in msg
    assert "got 2" in msg


# D7: §9 cache reuse — updating an unrelated field doesn't re-encode
def test_docs_cache_reuse_unrelated_field() -> None:
    class Doc(Struct):
        title: str
        summary: Annotated[Embedding, Vector(dim=2, encoder="stub")]

    call_count = 0

    def counting(text: str) -> list[float]:
        nonlocal call_count
        call_count += 1
        return [1.0, 0.0]

    spec = _new_spec()
    spec.configure(vector_encoders={"stub": counting})
    spec.add_model(Doc)
    mgr = spec.get_resource_manager(Doc)

    info = mgr.create(Doc(title="t1", summary=Embedding(content="same")))
    assert call_count == 1
    mgr.update(info.resource_id, Doc(title="t2", summary=Embedding(content="same")))
    assert call_count == 1  # no re-encoding


# D8: §4 distance metrics — l2 / ip both work end-to-end
def test_docs_distance_metric_alternatives() -> None:
    class Doc(Struct):
        title: str
        e: Annotated[list[float], Vector(dim=2, distance="l2")]

    spec = _new_spec()
    spec.add_model(Doc)
    mgr = spec.get_resource_manager(Doc)
    mgr.create(Doc(title="near", e=[1.0, 1.0]))
    mgr.create(Doc(title="far", e=[10.0, 10.0]))

    # default sort by distance ascending; l2 distance
    r_sort = (QB["e"].l2([0.0, 0.0]) < 100.0).sort(QB["e"].l2([0.0, 0.0])).build()
    titles = [r.data.title for r in mgr.list_resources(r_sort, returns=["data"])]
    assert titles == ["near", "far"]

    # ip metric
    r_ip = (QB["e"].ip([1.0, 1.0]) <= -1.0).sort(QB["e"].ip([1.0, 1.0])).build()
    titles_ip = [r.data.title for r in mgr.list_resources(r_ip, returns=["data"])]
    # far has dot=20 → ip dist=-20; near has dot=2 → ip dist=-2. Both ≤ -1.
    # ascending → most-similar (most-negative) first
    assert titles_ip == ["far", "near"]
