"""End-to-end integration tests for Vector + Embedding features."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

import pytest
from msgspec import Struct

from specstar import Embedding, SpecStar, Vector


def _stub_encoder(text: str) -> list[float]:
    """Deterministic 2-D vector based on text length & first char ordinal."""
    return [float(len(text)), float(ord(text[0]) if text else 0)]


# INT1: spec.configure(vector_encoders=...) registers encoders globally
def test_int_configure_vector_encoders() -> None:
    spec = SpecStar()
    spec.configure(vector_encoders={"stub": _stub_encoder})

    # The registry must contain "stub"
    assert spec.encoder_registry.resolve("stub") is _stub_encoder


# INT2: add_model auto-mounts the VectorDimValidator; create() with wrong-len
# vector raises ValidationError without an explicit validator arg
def test_int_dim_validator_auto_mounted() -> None:
    from specstar import ValidationError

    class Doc(Struct):
        embedding: Annotated[list[float], Vector(dim=4)]

    spec = SpecStar(default_user="tester", default_now=lambda: dt.datetime(2026, 5, 22))
    spec.add_model(Doc)

    mgr = spec.get_resource_manager(Doc)
    with pytest.raises(ValidationError):
        mgr.create(Doc(embedding=[0.1, 0.2]))  # len=2 != dim=4


# INT3: add_model with Embedding field auto-encodes vector via the registry
def test_int_embedding_processor_auto_mounted() -> None:
    class Doc(Struct):
        title: str
        summary: Annotated[Embedding, Vector(dim=2, encoder="stub")]

    spec = SpecStar(
        default_user="tester",
        default_now=lambda: dt.datetime(2026, 5, 22),
    )
    spec.configure(vector_encoders={"stub": _stub_encoder})
    spec.add_model(Doc)
    mgr = spec.get_resource_manager(Doc)

    # User only supplies content; framework computes the vector
    info = mgr.create(Doc(title="t", summary=Embedding(content="hi")))
    stored = mgr.get(info.resource_id)
    assert stored.data.summary.vector == _stub_encoder("hi")
    assert stored.data.summary.encoder_id == "stub"
    assert stored.data.summary.content_hash  # filled in


# INT4: end-to-end QB cosine search returns rows in distance order
def test_int_end_to_end_qb_cosine_search() -> None:
    from specstar.query import QB

    class Doc(Struct):
        title: str
        embedding: Annotated[list[float], Vector(dim=2)]

    spec = SpecStar(
        default_user="tester",
        default_now=lambda: dt.datetime(2026, 5, 22),
    )
    spec.add_model(Doc)
    mgr = spec.get_resource_manager(Doc)

    # Aligned with [1, 0] = near; orthogonal = far
    mgr.create(Doc(title="aligned", embedding=[1.0, 0.0]))
    mgr.create(Doc(title="close", embedding=[0.9, 0.1]))
    mgr.create(Doc(title="orthogonal", embedding=[0.0, 1.0]))

    q = [1.0, 0.0]
    query = (
        (QB["embedding"].cosine(q) < 0.5)
        .sort(QB["embedding"].cosine(q))
        .limit(10)
        .build()
    )
    results = mgr.list_resources(query, returns=["data"])
    titles = [r.data.title for r in results]
    assert titles == ["aligned", "close"]
    assert "orthogonal" not in titles


# UPD1: update() reuses the cached vector when content + encoder are unchanged
def test_int_update_cache_reuse() -> None:
    class Doc(Struct):
        title: str
        summary: Annotated[Embedding, Vector(dim=2, encoder="stub")]

    call_count = 0

    def counting_encoder(text: str) -> list[float]:
        nonlocal call_count
        call_count += 1
        return [float(len(text)), float(ord(text[0]))]

    spec = SpecStar(
        default_user="tester",
        default_now=lambda: dt.datetime(2026, 5, 22),
    )
    spec.configure(vector_encoders={"stub": counting_encoder})
    spec.add_model(Doc)
    mgr = spec.get_resource_manager(Doc)

    info = mgr.create(Doc(title="t1", summary=Embedding(content="hello")))
    assert call_count == 1

    # Update changes title but not summary.content → encoder must not be called again
    mgr.update(
        info.resource_id,
        Doc(title="t2", summary=Embedding(content="hello")),
    )
    assert call_count == 1  # cache reuse worked

    # Changing content triggers re-encoding
    mgr.update(
        info.resource_id,
        Doc(title="t2", summary=Embedding(content="goodbye")),
    )
    assert call_count == 2


# INT5: add_model on a postgres backend auto-creates the pgvector column + index
def test_int_add_model_creates_pgvector_column() -> None:
    import psycopg2

    from specstar import BackendBinding, BackendConfig

    class Doc(Struct):
        title: str
        embedding: Annotated[list[float], Vector(dim=2, distance="cosine")]

    # Unique table prefix per-test
    import uuid as _uuid

    table_prefix = f"int_v_{_uuid.uuid4().hex[:6]}_"

    spec = SpecStar(
        default_user="tester",
        default_now=lambda: dt.datetime(2026, 5, 22),
    )
    spec.configure(
        backend=BackendConfig(
            meta=BackendBinding(
                type="postgres",
                options={
                    "dsn": "postgresql://admin:password@localhost:5432/your_database",
                    "table_prefix": table_prefix,
                },
            ),
            resource=BackendBinding(type="memory"),
            blob=BackendBinding(type="memory"),
        ),
    )
    spec.add_model(Doc)

    try:
        # vec_embedding column + HNSW index must exist
        table_name = f"{table_prefix}doc_meta"
        conn = psycopg2.connect(
            "postgresql://admin:password@localhost:5432/your_database"
        )
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT udt_name FROM information_schema.columns
                WHERE table_name='{table_name}' AND column_name='vec_embedding'
                """
            )
            row = cur.fetchone()
            assert row is not None and row[0] == "vector"
            cur.execute(
                f"""
                SELECT indexname FROM pg_indexes
                WHERE tablename='{table_name}' AND indexname LIKE '%embedding%hnsw'
                """
            )
            assert cur.fetchone() is not None
        conn.close()
    finally:
        # cleanup table
        conn = psycopg2.connect(
            "postgresql://admin:password@localhost:5432/your_database"
        )
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(f'DROP TABLE IF EXISTS "{table_prefix}doc_meta" CASCADE')
        conn.close()


# INT6: e2e on pg — create rows with Embedding, query with QB cosine via str
def test_int_pg_e2e_embedding_with_str_query() -> None:
    import uuid as _uuid

    import psycopg2

    from specstar import BackendBinding, BackendConfig
    from specstar.query import QB

    def stub_embed(text: str) -> list[float]:
        if "near" in text or "hello" in text:
            return [1.0, 0.0]
        if "far" in text or "orthogonal" in text:
            return [0.0, 1.0]
        return [0.7, 0.7]

    class Doc(Struct):
        title: str
        summary: Annotated[Embedding, Vector(dim=2, encoder="stub")]

    table_prefix = f"int_pg_e2e_{_uuid.uuid4().hex[:6]}_"
    spec = SpecStar(
        default_user="t",
        default_now=lambda: dt.datetime(2026, 5, 22),
    )
    spec.configure(
        backend=BackendConfig(
            meta=BackendBinding(
                type="postgres",
                options={
                    "dsn": "postgresql://admin:password@localhost:5432/your_database",
                    "table_prefix": table_prefix,
                },
            ),
            resource=BackendBinding(type="memory"),
            blob=BackendBinding(type="memory"),
        ),
        vector_encoders={"stub": stub_embed},
    )
    spec.add_model(Doc)
    mgr = spec.get_resource_manager(Doc)

    try:
        mgr.create(Doc(title="hello-row", summary=Embedding(content="hello world")))
        mgr.create(
            Doc(title="orthogonal-row", summary=Embedding(content="orthogonal text"))
        )

        # Query via str, runs through encoder, dispatched to pgvector SQL
        q = (QB["summary"].cosine("near_query") < 0.3).build()
        results = mgr.list_resources(q, returns=["data"])
        titles = [r.data.title for r in results]
        assert "hello-row" in titles
        assert "orthogonal-row" not in titles
    finally:
        conn = psycopg2.connect(
            "postgresql://admin:password@localhost:5432/your_database"
        )
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(f'DROP TABLE IF EXISTS "{table_prefix}doc_meta" CASCADE')
        conn.close()
