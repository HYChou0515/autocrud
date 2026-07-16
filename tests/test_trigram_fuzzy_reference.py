"""``.fuzzy()`` is Postgres-native — the other backends reject it.

Trigram similarity (pg_trgm ``word_similarity``) is an algorithm with no faithful,
portable definition — unlike vector cosine distance, an exact formula the
reference backends reproduce. Rather than silently return DIFFERENT rows than
production Postgres, the memory / disk / sqlite backends raise. This runs in CI
(it needs no external services); the Postgres behaviour is in
``tests/meta_store/test_trigram_index.py``.
"""

import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from specstar.query import QB
from specstar.resource_manager.meta_store.simple import DiskMetaStore, MemoryMetaStore
from specstar.resource_manager.meta_store.sqlite3 import MemorySqliteMetaStore
from specstar.types import ResourceMeta


@pytest.fixture
def tmp():
    with tempfile.TemporaryDirectory(dir="./") as d:
        yield Path(d)


def _stores(tmp: Path):
    return [
        MemoryMetaStore(encoding="msgpack"),
        DiskMetaStore(encoding="msgpack", rootdir=tmp),
        MemorySqliteMetaStore(encoding="msgpack"),
    ]


def _meta(rid: str, title: str) -> ResourceMeta:
    base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    return ResourceMeta(
        current_revision_id=f"rev_{rid}",
        resource_id=str(uuid.uuid4()),
        total_revision_count=1,
        created_time=base,
        updated_time=base,
        created_by="t",
        updated_by="t",
        is_deleted=False,
        indexed_data={"id": rid, "title": title},
    )


def test_fuzzy_raises_on_every_non_postgres_backend_when_empty(tmp):
    """The rejection is about the backend, not the data — an empty store still
    raises, so a developer learns immediately rather than seeing zero rows."""
    for store in _stores(tmp):
        with pytest.raises(NotImplementedError, match="pg_trgm"):
            list(store.iter_search(QB["title"].fuzzy("mol").build()))


def test_fuzzy_raises_on_every_non_postgres_backend_with_rows(tmp):
    for store in _stores(tmp):
        m = _meta("1", "molecular biology")
        store[m.resource_id] = m
        with pytest.raises(NotImplementedError, match="pg_trgm"):
            list(store.iter_search(QB["title"].fuzzy("mol").build()))


def test_similarity_sort_also_raises_on_every_non_postgres_backend(tmp):
    """The ranking sort is Postgres-native too — no faithful word_similarity to
    order by on the reference backends."""
    from specstar.query_types import ResourceMetaSearchQuery

    for store in _stores(tmp):
        m = _meta("1", "molecular biology")
        store[m.resource_id] = m
        q = ResourceMetaSearchQuery(
            sorts=[QB["title"].similarity("mol").desc()], limit=100
        )
        with pytest.raises(NotImplementedError, match="pg_trgm"):
            list(store.iter_search(q))
