"""Tests for the memory-budgeted bulk read primitive (issue #434).

``IResourceStore.read_many`` is the read-side counterpart of the existing
``save_many``: it fetches the raw payload of many revisions at once so a
read-modify-write fan-out (``ResourceManager.patch_many``) does not pay one
round-trip per row.

The budget is expressed in **bytes**, not rows, because row size varies by
orders of magnitude between models (a flat derived table vs a document
carrying its whole extracted text). A row-count batch size that is right for
one is catastrophically wrong for the other.
"""

from __future__ import annotations

import datetime as dt
import io
import uuid

import pytest

from specstar.resource_manager.resource_store.simple import (
    DiskResourceStore,
    MemoryResourceStore,
)
from specstar.types import RevisionInfo, RevisionStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = dt.datetime(2026, 7, 20, tzinfo=dt.timezone.utc)


def _info(resource_id: str, revision_id: str = "r1") -> RevisionInfo:
    return RevisionInfo(
        uid=uuid.uuid4(),
        resource_id=resource_id,
        revision_id=revision_id,
        schema_version=None,
        status=RevisionStatus.stable,
        created_time=_NOW,
        updated_time=_NOW,
        created_by="tester",
        updated_by="tester",
    )


def _seed(store, sizes: dict[str, int]) -> list[tuple[str, str, None]]:
    """Save one revision per entry of *sizes* and return the read keys."""
    keys: list[tuple[str, str, None]] = []
    for rid, size in sizes.items():
        info = _info(rid)
        store.save(info, io.BytesIO(b"x" * size))
        keys.append((rid, info.revision_id, info.schema_version))
    return keys


@pytest.fixture(params=["memory", "disk"])
def store(request, tmp_path):
    if request.param == "memory":
        return MemoryResourceStore()
    return DiskResourceStore(rootdir=tmp_path)


# ---------------------------------------------------------------------------
# Budget behaviour
# ---------------------------------------------------------------------------


def test_read_many_returns_everything_when_budget_is_ample(store):
    keys = _seed(store, {"a": 10, "b": 20, "c": 30})

    data, consumed = store.read_many(keys, max_bytes=10_000)

    assert consumed == 3
    assert data == {"a": b"x" * 10, "b": b"x" * 20, "c": b"x" * 30}


def test_read_many_stops_at_the_budget(store):
    # 40 bytes of budget fits "a" (10) + "b" (20) but not "c" (30).
    keys = _seed(store, {"a": 10, "b": 20, "c": 30})

    data, consumed = store.read_many(keys, max_bytes=40)

    assert consumed == 2
    assert set(data) == {"a", "b"}


def test_read_many_always_reads_at_least_one_row(store):
    """A row bigger than the whole budget must still make progress.

    Otherwise a single oversized row stalls the caller forever — it would
    ask for the same prefix again and again and never consume it.
    """
    keys = _seed(store, {"huge": 5_000})

    data, consumed = store.read_many(keys, max_bytes=1)

    assert consumed == 1
    assert data == {"huge": b"x" * 5_000}


def test_read_many_resumes_from_the_unconsumed_tail(store):
    """Consuming a prefix at a time must eventually cover every row."""
    keys = _seed(store, {"a": 30, "b": 30, "c": 30})

    seen: dict[str, bytes] = {}
    pending = list(keys)
    rounds = 0
    while pending:
        data, consumed = store.read_many(pending, max_bytes=40)
        assert consumed >= 1
        seen.update(data)
        pending = pending[consumed:]
        rounds += 1

    assert seen.keys() == {"a", "b", "c"}
    assert rounds == 3  # 40 bytes fits exactly one 30-byte row at a time


def test_read_many_with_no_items_reads_nothing(store):
    assert store.read_many([], max_bytes=1_000) == ({}, 0)


# ---------------------------------------------------------------------------
# Meta store bulk read
# ---------------------------------------------------------------------------


def _meta_spec():
    from msgspec import Struct

    from specstar.crud.core import SpecStar

    class Item(Struct):
        name: str

    spec = SpecStar()
    spec.configure(default_user="tester", default_now=lambda: _NOW)
    spec.add_model(Item)
    return spec, Item


def test_meta_store_get_many_returns_what_it_finds():
    spec, Item = _meta_spec()
    rm = spec.get_resource_manager(Item)
    ids = [rm.create(Item(name=f"n{i}")).resource_id for i in range(3)]

    found = rm.storage.meta_store.get_many(ids)

    assert set(found) == set(ids)
    assert {m.resource_id for m in found.values()} == set(ids)


def test_meta_store_get_many_omits_unknown_ids():
    """A bulk caller is reconciling a set — it needs to see which members are
    gone, not to be stopped by the first missing one."""
    spec, Item = _meta_spec()
    rm = spec.get_resource_manager(Item)
    known = rm.create(Item(name="here")).resource_id

    found = rm.storage.meta_store.get_many([known, "does-not-exist"])

    assert set(found) == {known}


def test_meta_store_get_many_with_no_ids():
    spec, Item = _meta_spec()
    rm = spec.get_resource_manager(Item)

    assert rm.storage.meta_store.get_many([]) == {}


# ---------------------------------------------------------------------------
# SimpleStorage passthrough
# ---------------------------------------------------------------------------


def test_storage_exposes_the_budgeted_read(tmp_path):
    """`read_revisions_bulk` is the read-side twin of `save_revisions_bulk`.

    Storage is the seam every ResourceManager talks to, so the budget has to
    survive the trip through it rather than only existing on the store.
    """
    from msgspec import Struct

    from specstar.crud.core import SpecStar

    class Item(Struct):
        name: str

    spec = SpecStar()
    spec.configure(default_user="tester", default_now=lambda: _NOW)
    spec.add_model(Item)
    rm = spec.get_resource_manager(Item)

    ids = [rm.create(Item(name="n" * 50)).resource_id for _ in range(3)]
    keys = [
        (rid, rm.get_meta(rid).current_revision_id, rm.get_meta(rid).schema_version)
        for rid in ids
    ]

    everything, consumed = rm.storage.read_revisions_bulk(keys, max_bytes=1_000_000)
    assert consumed == 3
    assert set(everything) == set(ids)

    # A budget below one row's size still makes progress — exactly one row.
    _, consumed = rm.storage.read_revisions_bulk(keys, max_bytes=1)
    assert consumed == 1

    assert rm.storage.read_revisions_bulk([], max_bytes=1_000) == ({}, 0)


# ---------------------------------------------------------------------------
# Backends that cannot size a payload without transferring it
# ---------------------------------------------------------------------------


class _UnsizeableStore(MemoryResourceStore):
    """A backend with no cheap size probe — exercises the fallback path."""

    def payload_sizes(self, items):
        return None


def test_read_many_without_a_size_probe_overshoots_by_at_most_one_row():
    """The fallback can only measure a payload *after* fetching it.

    So it stops as soon as the running total reaches the budget, which means
    the row that crossed the line has already been read. That is a bounded,
    documented overshoot of one row — not an unbounded one — and it is why
    backends that *can* size cheaply override ``payload_sizes``.
    """
    store = _UnsizeableStore()
    keys = _seed(store, {"a": 10, "b": 20, "c": 30})

    data, consumed = store.read_many(keys, max_bytes=40)

    assert consumed == 3  # exact packing would have stopped at 2
    assert set(data) == {"a", "b", "c"}


def test_read_many_skips_rows_that_vanished_since_selection(store):
    """A fan-out selects rows, then reads them — a row can die in between.

    The read must not take the whole batch down with it: the surviving rows
    are returned, the dead one is simply absent, and the caller (which is
    collecting per-row failures anyway) decides what that means.
    """
    keys = _seed(store, {"a": 10, "gone": 10, "c": 10})
    store.purge_resource("gone")

    data, consumed = store.read_many(keys, max_bytes=10_000)

    assert consumed == 3  # the whole prefix was accounted for
    assert set(data) == {"a", "c"}


def test_read_many_without_a_size_probe_still_makes_progress():
    store = _UnsizeableStore()
    keys = _seed(store, {"huge": 5_000})

    data, consumed = store.read_many(keys, max_bytes=1)

    assert consumed == 1
    assert data == {"huge": b"x" * 5_000}
