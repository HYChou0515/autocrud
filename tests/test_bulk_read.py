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


def test_read_many_without_a_size_probe_still_makes_progress():
    store = _UnsizeableStore()
    keys = _seed(store, {"huge": 5_000})

    data, consumed = store.read_many(keys, max_bytes=1)

    assert consumed == 1
    assert data == {"huge": b"x" * 5_000}
