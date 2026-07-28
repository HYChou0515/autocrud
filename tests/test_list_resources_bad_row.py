"""A listing prefetches its page in one read. Decoding must stay per-row.

The bulk read exists to stop a listing costing one query per row, and it
deliberately fetches BYTES only: the moment decoding moves into that step, one
unreadable row stops being one skipped item and becomes a failed page.

These tests corrupt the stored payload itself rather than patching a method, so
they describe the behaviour and not the mechanism — they hold whether the page
arrives in one read or in twenty.
"""

import datetime as dt

import pytest
from msgspec import Struct

from specstar.query_types import ResourceMetaSearchQuery
from specstar.resource_manager.core import ResourceManager, SimpleStorage
from specstar.resource_manager.meta_store.simple import MemoryMetaStore
from specstar.resource_manager.resource_store.simple import MemoryResourceStore
from specstar.types import OnDecodeError


class Data(Struct):
    name: str


_NOW = dt.datetime(2026, 7, 28, 12, 0, 0)


def _manager(policy: OnDecodeError) -> ResourceManager[Data]:
    storage = SimpleStorage(
        meta_store=MemoryMetaStore(),
        resource_store=MemoryResourceStore(encoding="msgpack"),  # ty:ignore[invalid-argument-type]
    )
    return ResourceManager(Data, storage=storage, on_decode_error=policy)


def _create(mgr: ResourceManager[Data], name: str) -> str:
    with mgr.using(user="someone", now=_NOW):
        info = mgr.create(Data(name=name))
    return info.resource_id


def _corrupt(mgr: ResourceManager[Data], resource_id: str) -> None:
    """Replace one row's stored payload with bytes msgpack cannot decode.

    Reaching into the store rather than stubbing a read is the point: every
    path that serves this row — bulk or per-row — now yields the same garbage,
    so the test cannot be satisfied by a read path that merely happens to skip
    the bulk step.
    """
    store = mgr.storage._resource_store
    assert isinstance(store, MemoryResourceStore)
    revisions = store._store[resource_id]
    revision_id = next(iter(revisions))
    uid = next(iter(revisions[revision_id].values()))
    store._raw_data_store[uid] = b"\xc1 not msgpack"


def _list(mgr: ResourceManager[Data]):
    with mgr.using(user="someone", now=_NOW):
        return mgr.list_resources(ResourceMetaSearchQuery())


def test_one_unreadable_row_is_skipped_not_the_whole_page():
    mgr = _manager(OnDecodeError.skip)
    bad = _create(mgr, "bad")
    good = _create(mgr, "good")
    _corrupt(mgr, bad)

    results = _list(mgr)

    assert [r.meta.resource_id for r in results] == [good]  # ty:ignore[unresolved-attribute]


def test_an_unreadable_row_still_raises_under_the_error_policy():
    mgr = _manager(OnDecodeError.error)
    bad = _create(mgr, "bad")
    _create(mgr, "good")
    _corrupt(mgr, bad)

    with pytest.raises(Exception, match=bad):
        _list(mgr)


def test_the_raw_policy_still_hands_back_the_undecodable_row():
    mgr = _manager(OnDecodeError.raw)
    bad = _create(mgr, "bad")
    good = _create(mgr, "good")
    _corrupt(mgr, bad)

    results = _list(mgr)

    by_id = {r.meta.resource_id: r for r in results}  # ty:ignore[unresolved-attribute]
    assert set(by_id) == {bad, good}
    assert by_id[good].data == Data(name="good")
    # The point of `raw` is that the caller still learns the row exists.
    assert by_id[bad].data != Data(name="good")
