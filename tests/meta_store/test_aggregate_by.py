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

from specstar.aggregates import Count, CountDistinct
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


class Opt(msgspec.Struct):
    # a nullable group field — some rows collapse to the key=None group (#412 NULL last).
    # str (not int) on purpose: int group-keys have an orthogonal cross-backend type
    # divergence (Postgres returns them as strings); #511 groups by a str cluster_key.
    val: str | None = None


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


@pytest.mark.parametrize("meta_store_type", ["sql3-mem", "postgres"])
def test_order_and_page_pushed_to_store_not_sliced_in_python(meta_store_type):
    """#412 — on a group-paging backend (SQLite + Postgres) the engine does the
    group-level ``ORDER BY … LIMIT … OFFSET``: the store's ``aggregate_by``
    returns ONLY the requested page, not every group for the ResourceManager to
    slice in Python.
    Spying on the store proves the page (not the full group set) crossed the
    boundary — the same fast-path proof as ``*_is_pushed_down_not_iterated``,
    one level down."""
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
    for b in ("a", "b", "c", "d", "e"):
        mgr.create(Rec(bucket=b, size=1, score=0.0))

    seen: dict[str, int] = {}
    orig = meta_store.aggregate_by

    def spy(*a, **k):
        rows = orig(*a, **k)
        seen["n"] = len(rows)
        return rows

    meta_store.aggregate_by = spy
    page = mgr.exp_aggregate_by(
        QB["bucket"], {"n": Count()}, order_by="key", offset=1, limit=2
    )

    assert [r.key for r in page] == ["b", "c"]
    assert seen.get("n") == 2, (
        f"store returned {seen.get('n')} groups on {meta_store_type} — "
        "ORDER BY / LIMIT / OFFSET not pushed to the engine"
    )


@pytest.mark.parametrize("meta_store_type", ALL_META_STORE_TYPES)
class TestAggregateByOrderAndPaginate:
    """#412 — group-level ``order_by`` + ``limit`` / ``offset`` + ``exp_count_groups``.
    The SAME ordered+paginated groups on every backend, whether the sort/page pushes
    down to the engine or falls back to the in-process reference reduction."""

    @pytest.fixture(autouse=True)
    def _setup(self, meta_store_type, my_tmpdir):
        self._meta_store_type = meta_store_type
        self._tmpdir = my_tmpdir
        yield

    def _mgr(self):
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
            ],
        )

    def _seed(self, mgr, rows):
        """rows = [(bucket, size), ...]."""
        for bucket, size in rows:
            mgr.create(Rec(bucket=bucket, size=size, score=0.0))

    def test_order_by_aggregate_desc_with_limit_pages_the_groups(self):
        from specstar.aggregates import Count

        mgr = self._mgr()
        # group counts: a=3, b=1, c=2 → desc-by-count order is a, c, b
        self._seed(mgr, [("a", 1), ("a", 1), ("a", 1), ("b", 1), ("c", 1), ("c", 1)])
        rows = mgr.exp_aggregate_by(
            QB["bucket"], {"n": Count()}, order_by="-n", limit=2
        )
        assert [(r.key, r.n) for r in rows] == [("a", 3), ("c", 2)]

    def test_order_by_group_key_ascending_and_descending(self):
        from specstar.aggregates import Count

        mgr = self._mgr()
        self._seed(mgr, [("b", 1), ("a", 1), ("c", 1)])
        asc = mgr.exp_aggregate_by(QB["bucket"], {"n": Count()}, order_by="key")
        desc = mgr.exp_aggregate_by(QB["bucket"], {"n": Count()}, order_by="-key")
        assert [r.key for r in asc] == ["a", "b", "c"]
        assert [r.key for r in desc] == ["c", "b", "a"]

    def test_order_by_a_value_reducer_the_511_shape(self):
        # #511 pages concepts by their newest member: order_by a Max reducer, desc.
        from specstar.aggregates import Max

        mgr = self._mgr()
        # per-bucket max size: a=9, b=2, c=5 → desc order a, c, b
        self._seed(mgr, [("a", 1), ("a", 9), ("b", 2), ("c", 5), ("c", 3)])
        rows = mgr.exp_aggregate_by(
            QB["bucket"], {"hi": Max(QB["size"])}, order_by="-hi"
        )
        assert [(r.key, r.hi) for r in rows] == [("a", 9), ("c", 5), ("b", 2)]

    def test_offset_pages_past_the_first_groups(self):
        from specstar.aggregates import Count

        mgr = self._mgr()
        self._seed(mgr, [("a", 1), ("b", 1), ("c", 1), ("d", 1)])
        page = mgr.exp_aggregate_by(
            QB["bucket"], {"n": Count()}, order_by="key", offset=1, limit=2
        )
        assert [r.key for r in page] == ["b", "c"]

    def test_offset_without_limit_returns_the_rest_ordered(self):
        # order_by + offset but NO limit: every group past the offset, ordered.
        # Exercises the push-down "no limit" branch (SQLite LIMIT -1 / Postgres
        # LIMIT NULL) as well as the in-process reference.
        from specstar.aggregates import Count

        mgr = self._mgr()
        self._seed(mgr, [("a", 1), ("b", 1), ("c", 1), ("d", 1)])
        rest = mgr.exp_aggregate_by(
            QB["bucket"], {"n": Count()}, order_by="key", offset=2
        )
        assert [r.key for r in rest] == ["c", "d"]

    def test_ties_break_by_group_key_so_pages_are_stable(self):
        from specstar.aggregates import Count

        mgr = self._mgr()
        # every group has count 1 → the order_by target ties; key asc is the tiebreak
        self._seed(mgr, [("c", 1), ("a", 1), ("b", 1), ("d", 1)])
        p1 = mgr.exp_aggregate_by(QB["bucket"], {"n": Count()}, order_by="-n", limit=2)
        p2 = mgr.exp_aggregate_by(
            QB["bucket"], {"n": Count()}, order_by="-n", offset=2, limit=2
        )
        assert [r.key for r in p1] == ["a", "b"]  # tie → key asc
        assert [r.key for r in p2] == ["c", "d"]  # next page, no overlap/gap

    def test_null_group_key_sorts_last_in_both_directions(self):
        from specstar.aggregates import Count

        meta_store = get_meta_store(self._meta_store_type, tmpdir=self._tmpdir)
        storage = SimpleStorage(
            meta_store=meta_store,
            resource_store=MemoryResourceStore(encoding="msgpack"),  # ty:ignore[invalid-argument-type]
        )
        mgr = ResourceManager(
            Opt,
            storage=storage,
            name="opt",
            default_user="t",
            indexed_fields=[IndexableField(field_path="val", field_type=str)],
        )
        for v in ("a", "a", "b", None, None):
            mgr.create(Opt(val=v))
        asc = mgr.exp_aggregate_by(QB["val"], {"n": Count()}, order_by="key")
        desc = mgr.exp_aggregate_by(QB["val"], {"n": Count()}, order_by="-key")
        assert [r.key for r in asc] == ["a", "b", None]  # NULL last on asc
        assert [r.key for r in desc] == ["b", "a", None]  # NULL still last on desc

    def test_exp_count_groups_is_the_total_independent_of_limit_offset(self):
        from specstar.aggregates import Count

        mgr = self._mgr()
        self._seed(mgr, [("a", 1), ("b", 1), ("c", 1)])
        # a limited page returns fewer rows, but the pager total counts all groups
        page = mgr.exp_aggregate_by(
            QB["bucket"], {"n": Count()}, order_by="key", limit=1
        )
        assert len(page) == 1
        assert mgr.exp_count_groups(QB["bucket"]) == 3

    def test_bad_order_by_target_raises(self):
        from specstar.aggregates import Count

        mgr = self._mgr()
        self._seed(mgr, [("a", 1)])
        with pytest.raises(ValueError, match="order_by target"):
            mgr.exp_aggregate_by(QB["bucket"], {"n": Count()}, order_by="nope")

    def test_negative_offset_or_limit_raises(self):
        from specstar.aggregates import Count

        mgr = self._mgr()
        self._seed(mgr, [("a", 1)])
        with pytest.raises(ValueError, match="non-negative"):
            mgr.exp_aggregate_by(QB["bucket"], {"n": Count()}, offset=-1)
        with pytest.raises(ValueError, match="non-negative"):
            mgr.exp_aggregate_by(QB["bucket"], {"n": Count()}, limit=-1)


class Measurement(msgspec.Struct):
    period: str
    value: int


@pytest.mark.parametrize("meta_store_type", ALL_META_STORE_TYPES)
class TestAggregateByCountDistinctParity:
    """``CountDistinct(field)`` — distinct values per group — identical across
    backends (pushed COUNT(DISTINCT ...) vs the Python reference reduction)."""

    @pytest.fixture(autouse=True)
    def _setup(self, meta_store_type, my_tmpdir):
        self._meta_store_type = meta_store_type
        self._tmpdir = my_tmpdir
        yield

    def _mgr(self):
        meta_store = get_meta_store(self._meta_store_type, tmpdir=self._tmpdir)
        storage = SimpleStorage(
            meta_store=meta_store,
            resource_store=MemoryResourceStore(encoding="msgpack"),  # ty:ignore[invalid-argument-type]
        )
        return ResourceManager(
            Measurement,
            storage=storage,
            name="measurement",
            default_user="t",
            indexed_fields=[
                IndexableField(field_path="period", field_type=str),
                IndexableField(field_path="value", field_type=int),
            ],
        )

    def _seed(self, mgr, rows):
        for period, value in rows:
            mgr.create(Measurement(period=period, value=value))

    def test_counts_distinct_values_per_group(self):
        mgr = self._mgr()
        # Q3: values 1,1,2 → 2 distinct; Q4: 5,5 → 1 distinct
        self._seed(mgr, [("Q3", 1), ("Q3", 1), ("Q3", 2), ("Q4", 5), ("Q4", 5)])
        rows = mgr.exp_aggregate_by(QB["period"], {"n": CountDistinct(QB["value"])})
        assert {r.key: r.n for r in rows} == {"Q3": 2, "Q4": 1}

    def test_count_distinct_is_the_contradiction_primitive(self):
        # The motivating use case: a group with >1 distinct value is a conflict.
        mgr = self._mgr()
        self._seed(mgr, [("Q3", 1), ("Q3", 2), ("Q4", 5), ("Q4", 5)])
        rows = mgr.exp_aggregate_by(QB["period"], {"n": CountDistinct(QB["value"])})
        assert {r.key for r in rows if r.n > 1} == {"Q3"}


class Sale(msgspec.Struct):
    region: str
    period: str
    amount: int


@pytest.mark.parametrize("meta_store_type", ALL_META_STORE_TYPES)
class TestAggregateByCompositeGroupByParity:
    """Composite group-by (``by`` = a list of Fields → tuple key), identical
    across backends."""

    @pytest.fixture(autouse=True)
    def _setup(self, meta_store_type, my_tmpdir):
        self._meta_store_type = meta_store_type
        self._tmpdir = my_tmpdir
        yield

    def _mgr(self):
        meta_store = get_meta_store(self._meta_store_type, tmpdir=self._tmpdir)
        storage = SimpleStorage(
            meta_store=meta_store,
            resource_store=MemoryResourceStore(encoding="msgpack"),  # ty:ignore[invalid-argument-type]
        )
        return ResourceManager(
            Sale,
            storage=storage,
            name="sale",
            default_user="t",
            indexed_fields=[
                IndexableField(field_path="region", field_type=str),
                IndexableField(field_path="period", field_type=str),
                IndexableField(field_path="amount", field_type=int),
            ],
        )

    def _seed(self, mgr, rows):
        for region, period, amount in rows:
            mgr.create(Sale(region=region, period=period, amount=amount))

    def test_composite_key_is_a_tuple_in_field_order(self):
        mgr = self._mgr()
        self._seed(
            mgr,
            [("US", "Q3", 10), ("US", "Q3", 20), ("US", "Q4", 5), ("EU", "Q3", 7)],
        )
        rows = mgr.exp_aggregate_by([QB["region"], QB["period"]], {"n": Count()})
        assert {r.key: r.n for r in rows} == {
            ("US", "Q3"): 2,
            ("US", "Q4"): 1,
            ("EU", "Q3"): 1,
        }

    def test_composite_with_count_distinct(self):
        mgr = self._mgr()
        # (US, Q3): amounts 10,10,20 → 2 distinct
        self._seed(
            mgr,
            [("US", "Q3", 10), ("US", "Q3", 10), ("US", "Q3", 20), ("EU", "Q3", 7)],
        )
        rows = mgr.exp_aggregate_by(
            [QB["region"], QB["period"]], {"n": CountDistinct(QB["amount"])}
        )
        assert {r.key: r.n for r in rows} == {("US", "Q3"): 2, ("EU", "Q3"): 1}


@pytest.fixture
def my_tmpdir():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory(dir="./") as d:
        yield Path(d)
