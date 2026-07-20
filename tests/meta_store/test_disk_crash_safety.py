"""Crash-safety / half-committed-write tests for the disk-backed stores.

Regression tests for issue #340: an interrupted batch ``create()`` leaves a
``data/resource/<id>/`` dir on disk *before* ``meta/<id>.data`` is written.
The loader must treat "no finalised meta" as "resource does not exist"
(typed ``ResourceIDNotFoundError`` / ``KeyError``), never crash with a raw
``FileNotFoundError``.
"""

import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from faker import Faker
from msgspec import Struct

from specstar.resource_manager.core import (
    ResourceManager,
    SimpleStorage,
)
from specstar.resource_manager.meta_store.simple import DiskMetaStore
from specstar.resource_manager.resource_store.simple import DiskResourceStore
from specstar.types import ResourceIDNotFoundError, ResourceMeta
from specstar.util.fanout import sharded_dir

faker = Faker()


class Data(Struct):
    name: str
    age: int


def new_data() -> Data:
    return Data(name=faker.name(), age=faker.pyint(min_value=0, max_value=100))


def _make_meta(resource_id: str, *, current_revision_id: str = "rev-1") -> ResourceMeta:
    now = faker.date_time()
    user = faker.user_name()
    return ResourceMeta(
        current_revision_id=current_revision_id,
        resource_id=resource_id,
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by=user,
        updated_by=user,
    )


def _boom(*_args, **_kwargs):
    raise RuntimeError("simulated crash during commit")


@pytest.fixture
def my_tmpdir() -> Generator[Path]:
    with tempfile.TemporaryDirectory(dir="./") as d:
        yield Path(d)


@contextmanager
def disk_meta_store(tmpdir: Path) -> Generator[DiskMetaStore]:
    d = tmpdir / faker.pystr()
    d.mkdir()
    yield DiskMetaStore(encoding="msgpack", rootdir=d)  # ty:ignore[invalid-argument-type]


@contextmanager
def disk_manager(tmpdir: Path) -> Generator[tuple[ResourceManager, Path, Path]]:
    """A ResourceManager backed by disk meta + resource stores.

    Yields ``(mgr, meta_dir, resource_dir)`` so tests can mutate the on-disk
    layout to simulate an interrupted ``create()``.
    """
    meta_dir = tmpdir / "meta"
    res_dir = tmpdir / "res"
    meta_dir.mkdir()
    res_dir.mkdir()
    meta_store = DiskMetaStore(encoding="msgpack", rootdir=meta_dir)  # ty:ignore[invalid-argument-type]
    resource_store = DiskResourceStore(encoding="msgpack", rootdir=res_dir)  # ty:ignore[invalid-argument-type]
    storage = SimpleStorage(meta_store=meta_store, resource_store=resource_store)
    mgr = ResourceManager(Data, storage=storage)
    yield mgr, meta_dir, res_dir


def _create(mgr: ResourceManager, data: Data | None = None):
    data = data or new_data()
    with mgr.using(user=faker.user_name(), now=faker.date_time()):
        return mgr.create(data)


# ---------------------------------------------------------------------------
# Behavior 1: missing key contract parity with the other meta stores
# ---------------------------------------------------------------------------


def test_disk_meta_store_missing_key_raises_keyerror(my_tmpdir: Path):
    """DiskMetaStore[<missing>] raises KeyError, not raw FileNotFoundError.

    Every other meta store (Memory/Redis/SQL/Postgres) raises KeyError for a
    missing pk; the disk store must match so callers can handle it uniformly.
    """
    with disk_meta_store(my_tmpdir) as store:
        with pytest.raises(KeyError):
            store["does-not-exist:abc"]


# ---------------------------------------------------------------------------
# Behavior 2: interrupted create() / stale ref → typed ResourceIDNotFoundError
# ---------------------------------------------------------------------------


def test_interrupted_create_meta_missing_is_invisible(my_tmpdir: Path):
    """Resource data on disk but no finalised meta == "does not exist".

    Simulates an interrupted batch create() that wrote data/resource/<id>/
    before meta/<id>.data. get()/get_meta() must raise the typed
    ResourceIDNotFoundError, and list_resources() must not see the orphan.
    """
    with disk_manager(my_tmpdir) as (mgr, meta_dir, _res_dir):
        info = _create(mgr)
        rid = info.resource_id

        # Drop only the finalised meta marker, leaving the resource dir behind
        # — exactly the on-disk shape of an aborted create().
        (sharded_dir(meta_dir, rid) / f"{rid}.data").unlink()

        with pytest.raises(ResourceIDNotFoundError):
            mgr.get_meta(rid)
        with pytest.raises(ResourceIDNotFoundError):
            mgr.get(rid)
        assert mgr.list_resources() == []


def test_toctou_meta_vanishes_after_exists_check(my_tmpdir: Path, monkeypatch):
    """exists() races a concurrent purge: meta gone between check and read.

    A held Ref (or list snapshot) reports the resource exists, but the meta
    file is removed before get_meta() reads it. The read must surface
    ResourceIDNotFoundError, never a raw FileNotFoundError.
    """
    with disk_manager(my_tmpdir) as (mgr, meta_dir, _res_dir):
        info = _create(mgr)
        rid = info.resource_id

        # Force the stale "it exists" answer, then make the file truly absent.
        monkeypatch.setattr(mgr.storage, "exists", lambda _rid: True)
        (sharded_dir(meta_dir, rid) / f"{rid}.data").unlink()

        with pytest.raises(ResourceIDNotFoundError):
            mgr.get_meta(rid)


# ---------------------------------------------------------------------------
# Behavior 3: meta write is atomic (the commit marker is all-or-nothing)
# ---------------------------------------------------------------------------


def test_interrupted_meta_write_leaves_nothing_visible(my_tmpdir: Path, monkeypatch):
    """A crash before the meta commit must leave no visible/half-written record.

    A new key is written but the atomic commit step fails partway. The store
    must look exactly as if the write never happened: the key is absent, not
    listed, not counted, and listing/search does not crash on a truncated file.
    """
    from specstar.query_types import ResourceMetaSearchQuery
    from specstar.resource_manager.meta_store import simple as simple_mod

    with disk_meta_store(my_tmpdir) as store:
        store["kept:1"] = _make_meta("kept:1")

        # Blow up at the commit step of writing a brand-new key.
        monkeypatch.setattr(simple_mod.os, "replace", _boom, raising=True)
        with pytest.raises(RuntimeError):
            store["orphan:2"] = _make_meta("orphan:2")

        # The aborted write is completely invisible...
        assert "orphan:2" not in store
        assert "orphan:2" not in list(store)
        assert len(store) == 1
        # ...and the previously-committed value is intact and decodable.
        assert store["kept:1"].resource_id == "kept:1"
        searched = list(store.iter_search(ResourceMetaSearchQuery()))
        assert [m.resource_id for m in searched] == ["kept:1"]


def test_overwrite_interrupted_keeps_previous_value(my_tmpdir: Path, monkeypatch):
    """An interrupted overwrite leaves the previous value uncorrupted."""
    from specstar.resource_manager.meta_store import simple as simple_mod

    with disk_meta_store(my_tmpdir) as store:
        store["k:1"] = _make_meta("k:1", current_revision_id="rev-A")

        monkeypatch.setattr(simple_mod.os, "replace", _boom, raising=True)
        with pytest.raises(RuntimeError):
            store["k:1"] = _make_meta("k:1", current_revision_id="rev-B")

        assert store["k:1"].current_revision_id == "rev-A"


# ---------------------------------------------------------------------------
# Behavior 4: listing/search tolerates a file vanishing mid-iteration
# ---------------------------------------------------------------------------


def test_iter_search_skips_file_vanishing_mid_iteration(my_tmpdir: Path, monkeypatch):
    """A meta file removed (concurrent purge) after glob but before open.

    iter_search enumerates files lazily; a file may disappear between the
    directory listing and the read. That must be skipped, not crash the search.
    """
    import pathlib

    from specstar.query_types import ResourceMetaSearchQuery

    with disk_meta_store(my_tmpdir) as store:
        store["real:1"] = _make_meta("real:1")
        store["ghost:2"] = _make_meta("ghost:2")

        orig_open = pathlib.Path.open

        def fake_open(self, *a, **k):
            if self.name.startswith("ghost:2"):
                raise FileNotFoundError(self)
            return orig_open(self, *a, **k)

        monkeypatch.setattr(pathlib.Path, "open", fake_open)

        results = list(store.iter_search(ResourceMetaSearchQuery()))
        assert [m.resource_id for m in results] == ["real:1"]


# ---------------------------------------------------------------------------
# Issue #340 #4: boot-time GC reclaims orphaned resource/store dirs
# ---------------------------------------------------------------------------


def test_collect_orphans_removes_unreferenced_data(my_tmpdir: Path):
    """GC removes resource + store dirs not pointed at by a finalised meta.

    Simulates an interrupted batch create() (resource/store on disk, no meta).
    collect_orphans() reclaims the orphan and reports it, while the live
    resource remains fully readable.
    """
    with disk_manager(my_tmpdir) as (mgr, meta_dir, res_dir):
        live = _create(mgr, Data(name="keep", age=1))
        orphan = _create(mgr, Data(name="drop", age=2))

        # Make `orphan` an aborted create: drop its meta, keep data/resource.
        rid = orphan.resource_id
        (sharded_dir(meta_dir, rid) / f"{rid}.data").unlink()

        orphan_res = sharded_dir(res_dir / "resource", rid) / rid
        orphan_blob = sharded_dir(res_dir / "store", str(orphan.uid)) / str(orphan.uid)
        assert orphan_res.exists() and orphan_blob.exists()

        removed = mgr.collect_orphans()

        assert removed == 2  # one resource dir + one store blob
        assert not orphan_res.exists()
        assert not orphan_blob.exists()
        # The live resource is untouched and still readable.
        assert mgr.get(live.resource_id).data.name == "keep"
        assert (sharded_dir(res_dir / "store", str(live.uid)) / str(live.uid)).exists()


def test_collect_orphans_noop_when_clean(my_tmpdir: Path):
    """A cleanly-committed store has nothing to collect."""
    with disk_manager(my_tmpdir) as (mgr, _meta_dir, _res_dir):
        _create(mgr)
        _create(mgr)
        assert mgr.collect_orphans() == 0


# ---------------------------------------------------------------------------
# Issue #340 #5: optional fsync for OS-crash durability (default off)
# ---------------------------------------------------------------------------


def test_fsync_flag_defaults_off_and_writes_round_trip(my_tmpdir: Path):
    """The fsync flag is opt-in; default-off keeps batch-ingest throughput.

    Atomic rename (the real fix for process kills) is unconditional, so a
    default store still survives interruption. fsync only adds OS-crash
    durability and must not be forced on the hot path.
    """
    d = my_tmpdir / faker.pystr()
    d.mkdir()
    default = DiskMetaStore(encoding="msgpack", rootdir=d)  # ty:ignore[invalid-argument-type]
    assert default._fsync is False

    d2 = my_tmpdir / faker.pystr()
    d2.mkdir()
    durable = DiskMetaStore(encoding="msgpack", rootdir=d2, fsync=True)  # ty:ignore[invalid-argument-type]
    assert durable._fsync is True
    durable["k:1"] = _make_meta("k:1")
    assert durable["k:1"].resource_id == "k:1"
