"""A Vector field has its own pgvector column, so it must not also sit in the
``indexed_data`` JSONB (#416 follow-up).

``add_model`` appends every Vector field to ``indexed_fields`` — deliberately:
brute-force backends have no vector column and answer similarity from
``indexed_data``, and the pgvector backend reads that same copy on the write path
to populate its column. But on Postgres, once the column is populated the JSON
copy has no reader: ``_build_vector_order`` searches the ``vec_*`` column, and
``iter_search`` returns metas by decoding the ``data`` BYTEA. The JSONB copy is
dead weight — and not the cheap kind:

* the GIN on ``indexed_data`` indexes EVERY ELEMENT of the array, so one 4096-dim
  embedding contributes 4096 index entries per row;
* every ``@>`` probe must recheck against the whole fat jsonb.

Measured on 5000 rows with a 4096-dim embedding, vs the same rows without it:

    GIN size          43 MB   ->   312 kB     (138x)
    total relation   280 MB   ->   840 kB     (333x)
    @> probe        490.8 ms  ->   1.2 ms     (400x)

That is what made a real deployment's document list take 15 seconds: three
``in_``-list aggregates per request, each probing a GIN poisoned by 60k rows'
worth of 4096-float arrays. The bloat predates #416 — but nothing USED the GIN
until #416 stopped forcing a Seq Scan, so #416 is what woke it up.

Scope: this strips the JSONB column only. The ``data`` BYTEA still encodes the
whole ResourceMeta (vector included), which is exactly why reads are unaffected —
and why this does not reclaim the storage. Reclaiming it means changing what
readers see, which is a separate decision.
"""

from datetime import UTC, datetime

from specstar.types import ResourceMeta

from .common import get_meta_store


def _meta(rid: str, vec: list[float], **extra) -> ResourceMeta:
    base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    return ResourceMeta(
        current_revision_id=f"rev_{rid}",
        resource_id=rid,
        total_revision_count=1,
        created_time=base,
        updated_time=base,
        created_by="t",
        updated_by="t",
        is_deleted=False,
        indexed_data={"id": rid, "embedding": vec, **extra},
    )


def _raw_indexed_data(store, rid: str) -> dict:
    """The JSONB column as Postgres actually stores it (NOT the BYTEA copy)."""
    with store.transaction() as cur:
        cur.execute(
            f'SELECT indexed_data FROM "{store.table_name}" WHERE resource_id = %s',
            [rid],
        )
        return cur.fetchone()[0]


def test_the_vector_is_not_written_into_the_indexed_data_column():
    store = get_meta_store("postgres")
    store.ensure_vector_column("embedding", dim=4, distance="cosine")
    store["r1"] = _meta("r1", [0.1, 0.2, 0.3, 0.4], kind="doc")

    raw = _raw_indexed_data(store, "r1")
    assert "embedding" not in raw, f"vector still in the JSONB column: {list(raw)}"


def test_the_other_indexed_fields_are_untouched():
    # Only the vector keys go; everything the GIN is actually FOR must stay.
    store = get_meta_store("postgres")
    store.ensure_vector_column("embedding", dim=4, distance="cosine")
    store["r1"] = _meta("r1", [0.1, 0.2, 0.3, 0.4], kind="doc", n=7)

    raw = _raw_indexed_data(store, "r1")
    assert raw["id"] == "r1"
    assert raw["kind"] == "doc"
    assert raw["n"] == 7


def test_reading_the_meta_back_still_returns_the_vector():
    # The BYTEA still encodes the whole ResourceMeta, so no reader can tell.
    # This is what makes the change safe.
    store = get_meta_store("postgres")
    store.ensure_vector_column("embedding", dim=4, distance="cosine")
    vec = [0.1, 0.2, 0.3, 0.4]
    store["r1"] = _meta("r1", vec, kind="doc")

    got = store["r1"]
    assert got.indexed_data["embedding"] == vec


def test_the_pgvector_column_is_still_populated():
    # The column is fed from the in-memory meta BEFORE the strip, so it must be
    # unaffected — otherwise stripping would break vector search outright.
    store = get_meta_store("postgres")
    store.ensure_vector_column("embedding", dim=4, distance="cosine")
    store["r1"] = _meta("r1", [0.1, 0.2, 0.3, 0.4])

    col = store._vec_col_name("embedding")
    with store.transaction() as cur:
        cur.execute(
            f'SELECT "{col}" IS NOT NULL FROM "{store.table_name}" '
            "WHERE resource_id = %s",
            ["r1"],
        )
        assert cur.fetchone()[0] is True


def test_vector_search_still_works_end_to_end():
    # The point of the whole change: the column is the search surface, so removing
    # the JSON copy must leave similarity search untouched. Both the ORDER BY and
    # the WHERE form are exercised — each reads `_vec_col_name`, never indexed_data.
    from specstar.query_types import (
        DataSearchOperator,
        ResourceMetaSearchQuery,
        VectorDistanceCondition,
        VectorDistanceSort,
    )

    store = get_meta_store("postgres")
    store.ensure_vector_column("embedding", dim=4, distance="cosine")
    store["near"] = _meta("near", [1.0, 0.0, 0.0, 0.0])
    store["far"] = _meta("far", [0.0, 0.0, 0.0, 1.0])

    ordered = ResourceMetaSearchQuery(
        sorts=[
            VectorDistanceSort(
                field_path="embedding", query_vector=[1.0, 0.0, 0.0, 0.0]
            )
        ]
    )
    assert [m.resource_id for m in store.iter_search(ordered)][0] == "near"

    filtered = ResourceMetaSearchQuery(
        conditions=[
            VectorDistanceCondition(
                field_path="embedding",
                query_vector=[1.0, 0.0, 0.0, 0.0],
                operator=DataSearchOperator.less_than,
                threshold=0.3,
                distance="cosine",
            )
        ]
    )
    ids = [m.resource_id for m in store.iter_search(filtered)]
    assert ids == ["near"], ids


def test_a_field_without_a_vector_column_keeps_its_indexed_data_copy():
    # No column means no other queryable surface — brute-force backends read this
    # copy. Only a REGISTERED vector column licenses the strip.
    store = get_meta_store("postgres")
    store["r1"] = _meta("r1", [0.1, 0.2, 0.3, 0.4])

    raw = _raw_indexed_data(store, "r1")
    assert raw["embedding"] == [0.1, 0.2, 0.3, 0.4]
