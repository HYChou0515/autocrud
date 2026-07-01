"""Push-down of Sum/Min/Max/Avg (and datetime Min/Max) to an ``IMetaWithAgg``
metastore — the #406 continuation of the Count-only push-down (#361).

Service-free: uses an in-memory SQLite metastore (``MemorySqliteMetaStore``),
which implements ``IMetaWithAgg``, so these run in the fast CI job (the
``tests/meta_store/`` folder is integration-only and excluded there). The
cross-backend parity contract — including real Postgres — lives in
``tests/meta_store/test_aggregate_by.py``; here we assert (a) the reducer
push-down is actually TAKEN (spying on ``iter_all``), (b) results + Python
types match the reference path, and (c) ineligible aggregates fall BACK to the
Python path instead of pushing an incorrect result.
"""

import msgspec

from specstar.aggregates import Avg, Max, Min, Sum
from specstar.query import QB
from specstar.resource_manager.core import ResourceManager, SimpleStorage
from specstar.resource_manager.meta_store.sqlite3 import MemorySqliteMetaStore
from specstar.resource_manager.resource_store.simple import MemoryResourceStore
from specstar.types import IndexableField


class Item(msgspec.Struct):
    bucket: str
    size: int
    score: float


def _mgr(meta_store, *, indexed):
    storage = SimpleStorage(
        meta_store=meta_store,
        resource_store=MemoryResourceStore(encoding="msgpack"),  # ty:ignore[invalid-argument-type]
    )
    return ResourceManager(
        Item,
        storage=storage,
        name="item",
        default_user="t",
        indexed_fields=indexed,
    )


def _sqlite_mgr(*, indexed=None):
    if indexed is None:
        indexed = [
            IndexableField(field_path="bucket", field_type=str),
            IndexableField(field_path="size", field_type=int),
            IndexableField(field_path="score", field_type=float),
        ]
    return _mgr(MemorySqliteMetaStore(encoding="msgpack"), indexed=indexed)


def _seed(mgr, rows):
    for bucket, size, score in rows:
        mgr.create(Item(bucket=bucket, size=size, score=score))


class _IterSpy:
    """Wrap a manager's ``iter_all`` to record whether the Python reduction
    path was walked (i.e. the push-down was NOT taken)."""

    def __init__(self, mgr):
        self.mgr = mgr
        self.walked = False
        self._orig = mgr.iter_all

    def __enter__(self):
        def spy(*a, **k):
            self.walked = True
            return self._orig(*a, **k)

        self.mgr.iter_all = spy
        return self

    def __exit__(self, *exc):
        self.mgr.iter_all = self._orig


def test_sum_pushes_down_and_keeps_int_type():
    mgr = _sqlite_mgr()
    _seed(mgr, [("a", 10, 1.0), ("a", 5, 1.0), ("b", 2, 1.0)])
    with _IterSpy(mgr) as spy:
        rows = mgr.exp_aggregate_by(QB["bucket"], {"total": Sum(QB["size"])})
    result = {r.key: r.total for r in rows}
    assert result == {"a": 15, "b": 2}
    # Sum over an int field stays int (not Decimal/float) — parity with the
    # Python reduction path.
    assert all(type(v) is int for v in result.values())
    assert spy.walked is False, "Sum did not push down — walked iter_all"


def test_min_max_push_down_numeric_and_keep_type():
    mgr = _sqlite_mgr()
    _seed(mgr, [("a", 10, 2.5), ("a", 5, 9.0), ("b", 2, 4.0)])
    with _IterSpy(mgr) as spy:
        rows = mgr.exp_aggregate_by(
            QB["bucket"],
            {"lo": Min(QB["size"]), "hi": Max(QB["score"])},
        )
    by_key = {r.key: (r.lo, r.hi) for r in rows}
    assert by_key == {"a": (5, 9.0), "b": (2, 4.0)}
    # Min over int stays int, Max over float stays float.
    assert type(by_key["a"][0]) is int and type(by_key["a"][1]) is float
    assert spy.walked is False, "Min/Max did not push down — walked iter_all"


def test_avg_push_down_returns_float_via_sum_over_count():
    mgr = _sqlite_mgr()
    _seed(mgr, [("a", 10, 1.0), ("a", 5, 1.0), ("b", 2, 1.0)])
    with _IterSpy(mgr) as spy:
        rows = mgr.exp_aggregate_by(QB["bucket"], {"mean": Avg(QB["size"])})
    result = {r.key: r.mean for r in rows}
    assert result == {"a": 7.5, "b": 2.0}
    assert all(type(v) is float for v in result.values())
    assert spy.walked is False, "Avg did not push down — walked iter_all"


def test_datetime_max_over_meta_column_pushes_down_as_aware_utc():
    mgr = _sqlite_mgr()
    created = []
    for bucket, size in [("a", 1), ("a", 2), ("b", 3)]:
        rev = mgr.create(Item(bucket=bucket, size=size, score=0.0))
        created.append((bucket, rev.resource_id))
    expected: dict[str, object] = {}
    for bucket, rid in created:
        ut = mgr.get_meta(rid).updated_time
        expected[bucket] = ut if bucket not in expected else max(expected[bucket], ut)
    with _IterSpy(mgr) as spy:
        rows = mgr.exp_aggregate_by(QB["bucket"], {"latest": Max(QB.updated_time())})
    got = {r.key: r.latest for r in rows}
    assert got == expected
    assert all(v.tzinfo is not None for v in got.values()), "must be tz-aware UTC"
    assert spy.walked is False, "Max(updated_time) did not push down — walked iter_all"
