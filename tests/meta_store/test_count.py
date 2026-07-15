"""Cross-backend behaviour parity for ``ResourceManager.count_resources`` (#414).

Every metastore MUST return the same count — whether it pushes ``COUNT(*)``
down to its engine (``IMetaWithCount``: SQLite / Postgres) or falls back to the
core's ``ilen(iter_search(...))`` Python reduction (memory / disk / redis).
This file is the contract: the SAME parametrized tests run over
``ALL_META_STORE_TYPES``, and each asserts the count against the **reference**
``len(search_resources(query))`` — the rows the same query actually returns — so
a pushed-down count can never silently disagree with the path it replaced.

The ``limit`` / ``offset`` cases are the sharp edge: ``ilen(iter_search(q))``
counts the *paged window*, not the whole match set, so a naive
``SELECT COUNT(*) ... WHERE`` pushdown would be wrong. See
``IMetaWithCount``'s contract.
"""

import msgspec
import pytest

from specstar.query import QB
from specstar.resource_manager.basic import IMetaWithCount
from specstar.resource_manager.core import ResourceManager, SimpleStorage
from specstar.resource_manager.resource_store.simple import MemoryResourceStore
from specstar.types import IndexableField

from .common import ALL_META_STORE_TYPES, get_meta_store


class Chunk(msgspec.Struct):
    text: str
    source_doc_id: str


@pytest.mark.parametrize("meta_store_type", ALL_META_STORE_TYPES)
class TestCountParity:
    """count_resources(q) MUST equal len(search_resources(q)) on every backend."""

    @pytest.fixture(autouse=True)
    def _setup(self, meta_store_type, my_tmpdir):
        self._meta_store_type = meta_store_type
        self._tmpdir = my_tmpdir
        yield

    def _mgr(self):
        self._meta_store = get_meta_store(self._meta_store_type, tmpdir=self._tmpdir)
        storage = SimpleStorage(
            meta_store=self._meta_store,
            resource_store=MemoryResourceStore(encoding="msgpack"),  # ty:ignore[invalid-argument-type]
        )
        return ResourceManager(
            Chunk,
            storage=storage,
            name="chunk",
            default_user="t",
            indexed_fields=[IndexableField(field_path="source_doc_id", field_type=str)],
        )

    def _seed(self, mgr, plan: dict[str, int]):
        """plan = {source_doc_id: n_chunks}."""
        for sid, n in plan.items():
            for _ in range(n):
                mgr.create(Chunk(text="x", source_doc_id=sid))

    def _parity(self, mgr, query=None) -> int:
        """Assert the count matches the rows the SAME query returns, and return it."""
        counted = mgr.count_resources(query)
        reference = len(mgr.search_resources(query))
        assert counted == reference
        return counted

    # -- filter parity -----------------------------------------------------

    def test_unfiltered_counts_everything(self):
        mgr = self._mgr()
        self._seed(mgr, {"d1": 3, "d2": 5})
        assert self._parity(mgr) == 8

    def test_equality_filter(self):
        mgr = self._mgr()
        self._seed(mgr, {"d1": 3, "d2": 5})
        assert self._parity(mgr, (QB["source_doc_id"] == "d1").build()) == 3

    def test_in_filter_is_the_page_pattern(self):
        mgr = self._mgr()
        self._seed(mgr, {"d1": 3, "d2": 5, "d3": 2})
        q = QB["source_doc_id"].in_(["d1", "d2"]).build()
        assert self._parity(mgr, q) == 8

    def test_no_match_is_zero(self):
        mgr = self._mgr()
        self._seed(mgr, {"d1": 3})
        assert self._parity(mgr, (QB["source_doc_id"] == "nope").build()) == 0

    def test_empty_store_is_zero(self):
        mgr = self._mgr()
        assert self._parity(mgr) == 0

    # -- the sharp edge: the count is of the LIMIT/OFFSET window -----------

    def test_limit_caps_the_count(self):
        mgr = self._mgr()
        self._seed(mgr, {"d1": 10})
        assert self._parity(mgr, QB.all().limit(4).build()) == 4

    def test_limit_larger_than_matches_is_not_padded(self):
        mgr = self._mgr()
        self._seed(mgr, {"d1": 3})
        assert self._parity(mgr, QB.all().limit(99).build()) == 3

    def test_offset_shrinks_the_window(self):
        mgr = self._mgr()
        self._seed(mgr, {"d1": 10})
        assert self._parity(mgr, QB.all().offset(6).build()) == 4

    def test_offset_past_the_end_is_zero(self):
        mgr = self._mgr()
        self._seed(mgr, {"d1": 3})
        assert self._parity(mgr, QB.all().offset(99).build()) == 0

    def test_limit_and_offset_together(self):
        mgr = self._mgr()
        self._seed(mgr, {"d1": 10})
        # window = rows 6..10 capped at 3
        assert self._parity(mgr, QB.all().offset(6).limit(3).build()) == 3

    def test_limit_offset_with_filter(self):
        mgr = self._mgr()
        self._seed(mgr, {"d1": 10, "d2": 5})
        q = (QB["source_doc_id"] == "d1").limit(4).offset(8).build()
        assert self._parity(mgr, q) == 2

    # -- ordering must not change a count ---------------------------------

    def test_sort_does_not_change_the_count(self):
        mgr = self._mgr()
        self._seed(mgr, {"d1": 4, "d2": 6})
        unsorted = mgr.count_resources(QB.all().build())
        sorted_ = mgr.count_resources(QB.all().sort("source_doc_id").build())
        assert unsorted == sorted_ == 10

    def test_sort_with_limit_counts_the_same_window(self):
        mgr = self._mgr()
        self._seed(mgr, {"d1": 4, "d2": 6})
        q = QB.all().sort("-source_doc_id").limit(7).build()
        assert self._parity(mgr, q) == 7


@pytest.mark.parametrize("meta_store_type", ALL_META_STORE_TYPES)
def test_capable_stores_never_decode_rows_to_count(meta_store_type, my_tmpdir):
    """#414 regression: a store that declares IMetaWithCount must answer a count
    WITHOUT going through iter_search (which decodes every matching row).

    Positive assertion — a store that lacks the capability is expected to use
    the iter_search fallback, so this only pins the pushdown backends.
    """
    meta_store = get_meta_store(meta_store_type, tmpdir=my_tmpdir)
    mgr = ResourceManager(
        Chunk,
        storage=SimpleStorage(
            meta_store=meta_store,
            resource_store=MemoryResourceStore(encoding="msgpack"),  # ty:ignore[invalid-argument-type]
        ),
        name="chunk",
        default_user="t",
        indexed_fields=[IndexableField(field_path="source_doc_id", field_type=str)],
    )
    for _ in range(5):
        mgr.create(Chunk(text="x", source_doc_id="d1"))

    calls: list[object] = []
    real_iter_search = meta_store.iter_search

    def spy(query):
        calls.append(query)
        return real_iter_search(query)

    meta_store.iter_search = spy  # type: ignore[method-assign]
    try:
        assert mgr.count_resources() == 5
    finally:
        meta_store.iter_search = real_iter_search  # type: ignore[method-assign]

    if isinstance(meta_store, IMetaWithCount):
        assert calls == [], (
            f"{type(meta_store).__name__} declares IMetaWithCount but still counted "
            f"via iter_search ({len(calls)} call(s)) — the O(n) decode is back"
        )
    else:
        assert calls, "non-capable store should use the iter_search fallback"


@pytest.fixture
def my_tmpdir():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory(dir="./") as d:
        yield Path(d)
