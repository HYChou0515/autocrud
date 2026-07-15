"""#414 count push-down — the service-free half, so the FAST CI job guards it.

``tests/meta_store/test_count.py`` is the full cross-backend contract, but the
whole ``meta_store/`` folder is auto-marked ``integration`` (root conftest), so
none of it runs in the fast, service-free CI job. In-memory SQLite implements
``IMetaWithCount`` and needs no external service, so the push-down itself CAN be
guarded there — that is what this file is for. Memory is included as the
fallback side of the branch.

Keep this in sync with the cross-backend contract file; the assertions here are
a service-free subset of the same rules.
"""

import more_itertools as mit
import msgspec
import pytest

from specstar.query import QB
from specstar.resource_manager.basic import IMetaWithCount
from specstar.resource_manager.core import ResourceManager, SimpleStorage
from specstar.resource_manager.meta_store.simple import MemoryMetaStore
from specstar.resource_manager.meta_store.sqlite3 import MemorySqliteMetaStore
from specstar.resource_manager.resource_store.simple import MemoryResourceStore
from specstar.types import IndexableField


class Doc(msgspec.Struct):
    text: str
    collection_id: str


def _mgr(meta_store):
    return ResourceManager(
        Doc,
        storage=SimpleStorage(
            meta_store=meta_store,
            resource_store=MemoryResourceStore(encoding="msgpack"),  # ty:ignore[invalid-argument-type]
        ),
        name="doc",
        default_user="t",
        indexed_fields=[IndexableField(field_path="collection_id", field_type=str)],
    )


def _seed(mgr, plan: dict[str, int]):
    for cid, n in plan.items():
        for _ in range(n):
            mgr.create(Doc(text="x", collection_id=cid))


# sql3-mem pushes the count down; memory takes the ilen fallback. Both are
# service-free, so the fast CI job exercises BOTH sides of the branch.
STORES = [
    pytest.param(
        lambda: MemorySqliteMetaStore(encoding="msgpack"), id="sql3-mem-pushdown"
    ),
    pytest.param(MemoryMetaStore, id="memory-fallback"),
]


@pytest.mark.parametrize("make_store", STORES)
class TestCountPushdownServiceFree:
    def _parity(self, mgr, query=None) -> int:
        """The contract: the count must equal the rows the same query returns."""
        counted = mgr.count_resources(query)
        assert counted == len(mgr.search_resources(query))
        return counted

    def test_unfiltered(self, make_store):
        mgr = _mgr(make_store())
        _seed(mgr, {"c1": 3, "c2": 5})
        assert self._parity(mgr) == 8

    def test_filtered(self, make_store):
        mgr = _mgr(make_store())
        _seed(mgr, {"c1": 3, "c2": 5})
        assert self._parity(mgr, (QB["collection_id"] == "c1").build()) == 3

    def test_no_match_is_zero(self, make_store):
        mgr = _mgr(make_store())
        _seed(mgr, {"c1": 3})
        assert self._parity(mgr, (QB["collection_id"] == "nope").build()) == 0

    def test_counts_the_limit_offset_window_not_the_whole_match(self, make_store):
        """The sharp edge: ilen(iter_search(q)) counts the PAGED window, so a
        naive `SELECT COUNT(*) ... WHERE` push-down would over-count."""
        mgr = _mgr(make_store())
        _seed(mgr, {"c1": 10})
        assert self._parity(mgr, QB.all().limit(4).build()) == 4
        assert self._parity(mgr, QB.all().offset(6).build()) == 4
        assert self._parity(mgr, QB.all().offset(6).limit(3).build()) == 3
        assert self._parity(mgr, QB.all().offset(99).build()) == 0
        assert self._parity(mgr, QB.all().limit(99).build()) == 10

    def test_ordering_does_not_change_the_count(self, make_store):
        mgr = _mgr(make_store())
        _seed(mgr, {"c1": 4, "c2": 6})
        plain = mgr.count_resources(QB.all().build())
        ordered = mgr.count_resources(QB.all().sort("collection_id").build())
        assert plain == ordered == 10


def test_sqlite_counts_without_decoding_any_row():
    """#414 regression: the whole point — a capable store must NOT reach
    iter_search (which decodes every matching row) to answer a count."""
    meta_store = MemorySqliteMetaStore(encoding="msgpack")
    assert isinstance(meta_store, IMetaWithCount)
    mgr = _mgr(meta_store)
    _seed(mgr, {"c1": 5})

    calls: list[object] = []
    real = meta_store.iter_search

    def spy(query):
        calls.append(query)
        return real(query)

    meta_store.iter_search = spy  # type: ignore[method-assign]
    try:
        assert mgr.count_resources() == 5
    finally:
        meta_store.iter_search = real  # type: ignore[method-assign]

    assert calls == [], "count fell back to iter_search — the O(n) row decode is back"


def test_memory_store_keeps_the_ilen_fallback():
    """The other side of the branch: a store without the capability must still
    work, via the untouched reference path."""
    meta_store = MemoryMetaStore()
    assert not isinstance(meta_store, IMetaWithCount)
    mgr = _mgr(meta_store)
    _seed(mgr, {"c1": 7})
    q = (QB["collection_id"] == "c1").build()
    assert mgr.count_resources(q) == mit.ilen(meta_store.iter_search(q)) == 7
