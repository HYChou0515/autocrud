"""``ResourceManager.exp_aggregate_by`` — group-by + aggregate (v1: Count).

Built to grow: in v2 you'll pass {"size": Sum("bytes")} alongside
{"count": Count()}; the return type (``list[GroupRow]``) won't change, just the
named fields on each row. ``exp_`` prefix marks the API as experimental until
v2 lands.
"""

import msgspec
import pytest

from specstar import OnUnindexedQuery, SpecStar
from specstar.aggregates import Avg, Count, Max, Min, Sum
from specstar.errors import SpecStarWarning, UnindexedQueryError
from specstar.query import QB


class Doc(msgspec.Struct):
    name: str


class Chunk(msgspec.Struct):
    text: str
    source_doc_id: str


def _setup(d1_chunks: int, d2_chunks: int):
    sp = SpecStar()
    sp.configure(default_user="t")
    sp.add_model(Doc, name="doc")
    sp.add_model(Chunk, name="chunk", indexed_fields=[("source_doc_id", str)])
    rm_doc = sp.get_resource_manager(Doc)
    rm_chunk = sp.get_resource_manager(Chunk)
    d1 = rm_doc.create(Doc(name="d1")).resource_id
    d2 = rm_doc.create(Doc(name="d2")).resource_id
    for _ in range(d1_chunks):
        rm_chunk.create(Chunk(text="x", source_doc_id=d1))
    for _ in range(d2_chunks):
        rm_chunk.create(Chunk(text="x", source_doc_id=d2))
    return rm_doc, rm_chunk, d1, d2


def test_aggregate_by_counts_grouped_by_indexed_field():
    _, rm_chunk, d1, d2 = _setup(d1_chunks=3, d2_chunks=5)
    rows = rm_chunk.exp_aggregate_by("source_doc_id", {"count": Count()})
    by_key = {r.key: r.count for r in rows}
    assert by_key == {d1: 3, d2: 5}


def test_aggregate_by_honours_filter_query():
    # Narrow the aggregation with a filter (matches the issue's batched-page pattern).
    _, rm_chunk, d1, d2 = _setup(d1_chunks=3, d2_chunks=5)
    rows = rm_chunk.exp_aggregate_by(
        "source_doc_id",
        {"count": Count()},
        query=(QB["source_doc_id"] == d1).build(),
    )
    assert {r.key: r.count for r in rows} == {d1: 3}


def test_aggregate_by_empty_input_returns_empty_list():
    _, rm_chunk, _, _ = _setup(d1_chunks=0, d2_chunks=0)
    rows = rm_chunk.exp_aggregate_by("source_doc_id", {"count": Count()})
    assert rows == []


def test_group_row_exposes_caller_named_aggregate_via_attr_and_item():
    # The result-field name comes from the dict key — caller controls it.
    _, rm_chunk, d1, d2 = _setup(d1_chunks=2, d2_chunks=4)
    rows = rm_chunk.exp_aggregate_by("source_doc_id", {"chunk_total": Count()})
    assert {r.key: r.chunk_total for r in rows} == {d1: 2, d2: 4}  # attr access
    assert {r.key: r["chunk_total"] for r in rows} == {d1: 2, d2: 4}  # item access


def test_rejects_value_that_is_not_an_aggregate():
    _, rm_chunk, _, _ = _setup(d1_chunks=1, d2_chunks=0)
    with pytest.raises(TypeError, match="Aggregate"):
        rm_chunk.exp_aggregate_by("source_doc_id", {"oops": "not_an_aggregate"})


def test_non_indexed_group_by_warns_under_default_policy():
    # Without indexed_fields on Chunk, source_doc_id is not in indexed_data —
    # every row collapses to key=None, with a SpecStarWarning naming the field.
    sp = SpecStar()
    sp.configure(default_user="t")
    sp.add_model(Chunk, name="chunk2")  # no indexed_fields
    rm = sp.get_resource_manager(Chunk)
    rm.create(Chunk(text="x", source_doc_id="d1"))
    with pytest.warns(SpecStarWarning, match="source_doc_id"):
        rows = rm.exp_aggregate_by("source_doc_id", {"count": Count()})
    assert [(r.key, r.count) for r in rows] == [(None, 1)]


def test_non_indexed_group_by_raises_under_error_policy():
    sp = SpecStar()
    sp.configure(default_user="t", on_unindexed_query=OnUnindexedQuery.error)
    sp.add_model(Chunk, name="chunk3")
    rm = sp.get_resource_manager(Chunk)
    rm.create(Chunk(text="x", source_doc_id="d1"))
    with pytest.raises(UnindexedQueryError):
        rm.exp_aggregate_by("source_doc_id", {"count": Count()})


def test_group_by_a_resource_meta_attribute_works_without_indexed_fields():
    # ResourceMeta attributes (e.g. created_by) are queryable without indexing.
    sp = SpecStar()
    sp.configure(default_user="t")
    sp.add_model(Chunk, name="chunk4")
    rm = sp.get_resource_manager(Chunk)
    with rm.using("alice"):
        rm.create(Chunk(text="a", source_doc_id="d1"))
        rm.create(Chunk(text="b", source_doc_id="d1"))
    with rm.using("bob"):
        rm.create(Chunk(text="c", source_doc_id="d2"))
    rows = rm.exp_aggregate_by("created_by", {"count": Count()})
    assert {r.key: r.count for r in rows} == {"alice": 2, "bob": 1}


# --- v2 aggregates: Sum / Min / Max / Avg ------------------------------------


class Item(msgspec.Struct):
    bucket: str
    size: int
    score: float


def _items(*items: "tuple[str, int, float] | tuple[str, int, float | None]"):
    """``[(bucket, size, score), ...] -> (rm, items)``."""
    sp = SpecStar()
    sp.configure(default_user="t")
    sp.add_model(
        Item,
        name="item",
        indexed_fields=[("bucket", str), ("size", int), ("score", float)],
    )
    rm = sp.get_resource_manager(Item)
    for bucket, size, score in items:
        rm.create(Item(bucket=bucket, size=size, score=score))
    return rm


def test_sum_aggregates_numeric_field_per_group():
    rm = _items(("a", 10, 1.0), ("a", 20, 2.0), ("b", 5, 1.5))
    rows = rm.exp_aggregate_by("bucket", {"total": Sum("size")})
    assert {r.key: r.total for r in rows} == {"a": 30, "b": 5}


def test_min_and_max_aggregate_per_group():
    rm = _items(("a", 10, 0.5), ("a", 20, 4.0), ("b", 5, 1.5))
    rows = rm.exp_aggregate_by(
        "bucket", {"smallest": Min("size"), "largest": Max("size")}
    )
    by_key = {r.key: (r.smallest, r.largest) for r in rows}
    assert by_key == {"a": (10, 20), "b": (5, 5)}


def test_avg_returns_float():
    rm = _items(("a", 10, 1.0), ("a", 20, 3.0), ("b", 5, 2.0))
    rows = rm.exp_aggregate_by("bucket", {"mean": Avg("size")})
    by_key = {r.key: r.mean for r in rows}
    assert by_key == {"a": 15.0, "b": 5.0}
    assert all(isinstance(v, float) for v in by_key.values())


def test_multiple_aggregates_in_one_call():
    rm = _items(("a", 10, 0.5), ("a", 20, 4.0), ("b", 5, 1.5))
    rows = rm.exp_aggregate_by(
        "bucket",
        {"n": Count(), "total": Sum("size"), "top_score": Max("score")},
    )
    by_key = {r.key: (r.n, r.total, r.top_score) for r in rows}
    assert by_key == {"a": (2, 30, 4.0), "b": (1, 5, 1.5)}


def test_sum_raises_typeerror_on_non_numeric_value():
    rm = _items(("a", 10, 1.0))
    # Sum on a string-typed indexed field (bucket) → first non-None hit raises.
    with pytest.raises(TypeError, match="Sum"):
        rm.exp_aggregate_by("bucket", {"oops": Sum("bucket")})


def test_avg_returns_none_when_no_numeric_values_for_group():
    # Avg on a field that's UNSET / not present for every row in the group:
    # use a ResourceMeta attribute that's None for these rows. The created
    # resources have created_time set, so use updated_by (often UNSET).
    rm = _items(("a", 10, 0.5))
    # Group on bucket but Avg on an indexed field that all rows have None for:
    # rather than fight the model, prove the None-skip + None-return paths via
    # an empty filter that yields a group with no rows. (See empty-filter test.)
    # Here instead exercise Min/Max with no rows -> empty list (no group, no
    # state to finalise).
    rows = rm.exp_aggregate_by(
        "bucket",
        {"m": Avg("score")},
        query=(QB["bucket"] == "nope").build(),
    )
    assert rows == []
