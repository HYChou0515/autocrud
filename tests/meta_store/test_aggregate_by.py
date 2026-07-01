"""Cross-backend behaviour parity for ``ResourceManager.exp_aggregate_by``.

Every metastore implementation MUST return identical results from
``exp_aggregate_by`` — whether it pushes the group-by down to its engine
(SQLite) or falls back to the core Python reduction (memory / disk / …).
This file is the contract: the SAME parametrized tests run over
``ALL_META_STORE_TYPES`` and assert the SAME results, so a pushed-down path
can never silently disagree with the reference Python path.

Scope (v1): ``Count`` group-by. Sum/Min/Max/Avg + ForeignAggregate stay
covered by ``tests/test_exp_aggregate_by.py`` (memory) until they push down too.
"""

import msgspec
import pytest

from specstar.aggregates import Count
from specstar.errors import SpecStarWarning
from specstar.query import QB
from specstar.resource_manager.core import ResourceManager, SimpleStorage
from specstar.resource_manager.resource_store.simple import MemoryResourceStore
from specstar.types import IndexableField

from .common import ALL_META_STORE_TYPES, get_meta_store


class Chunk(msgspec.Struct):
    text: str
    source_doc_id: str


@pytest.mark.parametrize("meta_store_type", ALL_META_STORE_TYPES)
class TestAggregateByCountParity:
    """Each test builds a ResourceManager over the parametrized metastore and
    asserts the exp_aggregate_by(Count()) result — identical across backends."""

    @pytest.fixture(autouse=True)
    def _setup(self, meta_store_type, my_tmpdir):
        self._meta_store_type = meta_store_type
        self._tmpdir = my_tmpdir
        yield

    def _mgr(self, *, indexed: bool = True):
        meta_store = get_meta_store(self._meta_store_type, tmpdir=self._tmpdir)
        storage = SimpleStorage(
            meta_store=meta_store,
            resource_store=MemoryResourceStore(encoding="msgpack"),  # ty:ignore[invalid-argument-type]
        )
        return ResourceManager(
            Chunk,
            storage=storage,
            name="chunk",
            default_user="t",
            indexed_fields=(
                [IndexableField(field_path="source_doc_id", field_type=str)]
                if indexed
                else None
            ),
        )

    def _seed(self, mgr, plan: dict[str, int]):
        """plan = {source_doc_id: n_chunks}."""
        for sid, n in plan.items():
            for _ in range(n):
                mgr.create(Chunk(text="x", source_doc_id=sid))

    # -- core result-consistency cases ------------------------------------

    def test_counts_grouped_by_indexed_field(self):
        mgr = self._mgr()
        self._seed(mgr, {"d1": 3, "d2": 5})
        rows = mgr.exp_aggregate_by(QB["source_doc_id"], {"count": Count()})
        assert {r.key: r.count for r in rows} == {"d1": 3, "d2": 5}

    def test_in_filter_is_the_page_pattern(self):
        # The real document-list case: count chunks for just THIS page's docs.
        mgr = self._mgr()
        self._seed(mgr, {"d1": 3, "d2": 5, "d3": 2})
        rows = mgr.exp_aggregate_by(
            QB["source_doc_id"],
            {"count": Count()},
            query=QB["source_doc_id"].in_(["d1", "d2"]).build(),
        )
        assert {r.key: r.count for r in rows} == {"d1": 3, "d2": 5}

    def test_equality_filter(self):
        mgr = self._mgr()
        self._seed(mgr, {"d1": 3, "d2": 5})
        rows = mgr.exp_aggregate_by(
            QB["source_doc_id"],
            {"count": Count()},
            query=(QB["source_doc_id"] == "d1").build(),
        )
        assert {r.key: r.count for r in rows} == {"d1": 3}

    def test_empty_returns_empty_list(self):
        mgr = self._mgr()
        rows = mgr.exp_aggregate_by(QB["source_doc_id"], {"count": Count()})
        assert rows == []

    def test_caller_named_aggregate_via_attr_and_item(self):
        mgr = self._mgr()
        self._seed(mgr, {"d1": 2, "d2": 4})
        rows = mgr.exp_aggregate_by(QB["source_doc_id"], {"chunk_total": Count()})
        assert {r.key: r.chunk_total for r in rows} == {"d1": 2, "d2": 4}
        assert {r.key: r["chunk_total"] for r in rows} == {"d1": 2, "d2": 4}

    def test_group_by_resource_meta_attribute(self):
        # created_by is a ResourceMeta attribute — queryable without indexing.
        mgr = self._mgr(indexed=False)
        with mgr.using("alice"):
            mgr.create(Chunk(text="a", source_doc_id="d1"))
            mgr.create(Chunk(text="b", source_doc_id="d1"))
        with mgr.using("bob"):
            mgr.create(Chunk(text="c", source_doc_id="d2"))
        rows = mgr.exp_aggregate_by(QB.created_by(), {"count": Count()})
        assert {r.key: r.count for r in rows} == {"alice": 2, "bob": 1}

    def test_non_indexed_field_collapses_to_none_group(self):
        # Without indexing source_doc_id, every row's key is None — and the
        # None group must be the SAME None on every backend (SQLite NULL too).
        mgr = self._mgr(indexed=False)
        self._seed(mgr, {"d1": 2, "d2": 1})
        with pytest.warns(SpecStarWarning, match="source_doc_id"):
            rows = mgr.exp_aggregate_by(QB["source_doc_id"], {"count": Count()})
        assert [(r.key, r.count) for r in rows] == [(None, 3)]


class Rec(msgspec.Struct):
    bucket: str
    size: int
    score: float


@pytest.mark.parametrize("meta_store_type", ALL_META_STORE_TYPES)
class TestAggregateByReducerParity:
    """#406 — Sum/Min/Max/Avg (+ datetime Min/Max) must return IDENTICAL
    results and Python types on every backend, whether the reducer pushes down
    (SQLite / Postgres) or falls back to the core Python reduction."""

    @pytest.fixture(autouse=True)
    def _setup(self, meta_store_type, my_tmpdir):
        self._meta_store_type = meta_store_type
        self._tmpdir = my_tmpdir
        yield

    def _mgr(self):
        from specstar.types import IndexableField

        meta_store = get_meta_store(self._meta_store_type, tmpdir=self._tmpdir)
        storage = SimpleStorage(
            meta_store=meta_store,
            resource_store=MemoryResourceStore(encoding="msgpack"),  # ty:ignore[invalid-argument-type]
        )
        return ResourceManager(
            Rec,
            storage=storage,
            name="rec",
            default_user="t",
            indexed_fields=[
                IndexableField(field_path="bucket", field_type=str),
                IndexableField(field_path="size", field_type=int),
                IndexableField(field_path="score", field_type=float),
            ],
        )

    def _seed(self, mgr, rows):
        for bucket, size, score in rows:
            mgr.create(Rec(bucket=bucket, size=size, score=score))

    def test_sum_int_field_parity_and_type(self):
        from specstar.aggregates import Sum

        mgr = self._mgr()
        self._seed(mgr, [("a", 10, 1.5), ("a", 5, 2.5), ("b", 2, 4.0)])
        rows = mgr.exp_aggregate_by(QB["bucket"], {"total": Sum(QB["size"])})
        result = {r.key: r.total for r in rows}
        assert result == {"a": 15, "b": 2}
        assert all(type(v) is int for v in result.values())

    def test_sum_float_field_parity_and_type(self):
        from specstar.aggregates import Sum

        mgr = self._mgr()
        self._seed(mgr, [("a", 10, 1.5), ("a", 5, 2.5), ("b", 2, 4.0)])
        rows = mgr.exp_aggregate_by(QB["bucket"], {"total": Sum(QB["score"])})
        result = {r.key: r.total for r in rows}
        assert result == {"a": 4.0, "b": 4.0}
        assert all(type(v) is float for v in result.values())

    def test_min_max_parity_and_type(self):
        from specstar.aggregates import Max, Min

        mgr = self._mgr()
        self._seed(mgr, [("a", 10, 2.5), ("a", 5, 9.0), ("b", 2, 4.0)])
        rows = mgr.exp_aggregate_by(
            QB["bucket"], {"lo": Min(QB["size"]), "hi": Max(QB["score"])}
        )
        got = {r.key: (r.lo, r.hi) for r in rows}
        assert got == {"a": (5, 9.0), "b": (2, 4.0)}
        assert type(got["a"][0]) is int and type(got["a"][1]) is float

    def test_avg_parity_is_float(self):
        from specstar.aggregates import Avg

        mgr = self._mgr()
        self._seed(mgr, [("a", 10, 1.0), ("a", 5, 1.0), ("b", 2, 1.0)])
        rows = mgr.exp_aggregate_by(QB["bucket"], {"mean": Avg(QB["size"])})
        result = {r.key: r.mean for r in rows}
        assert result == {"a": 7.5, "b": 2.0}
        assert all(type(v) is float for v in result.values())

    def test_mixed_count_sum_avg_in_one_call(self):
        from specstar.aggregates import Avg, Count, Sum

        mgr = self._mgr()
        self._seed(mgr, [("a", 10, 1.0), ("a", 6, 1.0), ("b", 2, 1.0)])
        rows = mgr.exp_aggregate_by(
            QB["bucket"],
            {"n": Count(), "total": Sum(QB["size"]), "mean": Avg(QB["size"])},
        )
        got = {r.key: (r.n, r.total, r.mean) for r in rows}
        assert got == {"a": (2, 16, 8.0), "b": (1, 2, 2.0)}

    def test_datetime_max_over_meta_column_parity(self):
        from specstar.aggregates import Max

        mgr = self._mgr()
        created = []
        for bucket, size in [("a", 1), ("a", 2), ("b", 3)]:
            rev = mgr.create(Rec(bucket=bucket, size=size, score=0.0))
            created.append((bucket, rev.resource_id))
        expected: dict[str, object] = {}
        for bucket, rid in created:
            ut = mgr.get_meta(rid).updated_time
            expected[bucket] = (
                ut if bucket not in expected else max(expected[bucket], ut)
            )
        rows = mgr.exp_aggregate_by(QB["bucket"], {"latest": Max(QB.updated_time())})
        got = {r.key: r.latest for r in rows}
        assert got == expected
        assert all(v.tzinfo is not None for v in got.values()), "tz-aware UTC"


@pytest.mark.parametrize("meta_store_type", ["sql3-mem", "postgres"])
def test_count_groupby_is_pushed_down_not_iterated(meta_store_type):
    """On a push-down backend (``IMetaWithAgg``) the Count group-by must reach
    ``aggregate_by``, NOT walk ``iter_all`` (that IS the push-down). Spying on
    ``iter_all`` proves the fast path is taken, not a silent fallback."""
    meta_store = get_meta_store(meta_store_type)
    storage = SimpleStorage(
        meta_store=meta_store,
        resource_store=MemoryResourceStore(encoding="msgpack"),  # ty:ignore[invalid-argument-type]
    )
    mgr = ResourceManager(
        Chunk,
        storage=storage,
        name="chunk",
        default_user="t",
        indexed_fields=[IndexableField(field_path="source_doc_id", field_type=str)],
    )
    for sid, n in {"d1": 3, "d2": 2}.items():
        for _ in range(n):
            mgr.create(Chunk(text="x", source_doc_id=sid))

    called = False
    orig_iter_all = mgr.iter_all

    def spy(*a, **k):
        nonlocal called
        called = True
        return orig_iter_all(*a, **k)

    mgr.iter_all = spy
    rows = mgr.exp_aggregate_by(QB["source_doc_id"], {"count": Count()})

    assert {r.key: r.count for r in rows} == {"d1": 3, "d2": 2}
    assert called is False, (
        f"exp_aggregate_by walked iter_all on {meta_store_type} — push-down not taken"
    )


@pytest.mark.parametrize("meta_store_type", ["sql3-mem", "postgres"])
def test_reducers_are_pushed_down_not_iterated(meta_store_type):
    """#406 — Sum, Avg (Sum+Count) and datetime Max(updated_time) reach
    ``aggregate_by`` on a push-down backend rather than walking ``iter_all``
    (proves Postgres/SQLite take the fast path, not a correct-but-slow
    fallback)."""
    from specstar.aggregates import Avg, Max, Sum

    meta_store = get_meta_store(meta_store_type)
    storage = SimpleStorage(
        meta_store=meta_store,
        resource_store=MemoryResourceStore(encoding="msgpack"),  # ty:ignore[invalid-argument-type]
    )
    mgr = ResourceManager(
        Rec,
        storage=storage,
        name="rec",
        default_user="t",
        indexed_fields=[
            IndexableField(field_path="bucket", field_type=str),
            IndexableField(field_path="size", field_type=int),
        ],
    )
    for bucket, size in [("a", 1), ("a", 3), ("b", 5)]:
        mgr.create(Rec(bucket=bucket, size=size, score=0.0))

    called = False
    orig_iter_all = mgr.iter_all

    def spy(*a, **k):
        nonlocal called
        called = True
        return orig_iter_all(*a, **k)

    mgr.iter_all = spy
    rows = mgr.exp_aggregate_by(
        QB["bucket"],
        {
            "total": Sum(QB["size"]),
            "mean": Avg(QB["size"]),
            "latest": Max(QB.updated_time()),
        },
    )

    assert {r.key: (r.total, r.mean) for r in rows} == {"a": (4, 2.0), "b": (5, 5.0)}
    assert called is False, (
        f"exp_aggregate_by walked iter_all on {meta_store_type} — reducers not pushed"
    )


@pytest.fixture
def my_tmpdir():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory(dir="./") as d:
        yield Path(d)
