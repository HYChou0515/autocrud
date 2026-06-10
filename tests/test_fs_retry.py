"""ESTALE / transient FS-error tolerance for the disk-backed stores.

Issue #352: on NFS, a concurrent rename/unlink on another client invalidates
the inode the kernel handed us, and the next syscall raises
``OSError(errno=116, "Stale file handle")``. The same race on a local
filesystem normally surfaces as ``FileNotFoundError`` (already handled), but
on NFS-mounted root dirs the same code path crashes with a raw ESTALE.

These tests prove the three disk stores treat ESTALE as transient: retry
with bounded backoff, succeed on next attempt, never bubble the raw OSError
out of the public API.
"""

from __future__ import annotations

import errno
import pathlib
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from faker import Faker

from specstar.query_types import ResourceMetaSearchQuery
from specstar.resource_manager.blob_store.simple import DiskBlobStore
from specstar.resource_manager.meta_store.simple import DiskMetaStore
from specstar.resource_manager.resource_store.simple import DiskResourceStore
from specstar.types import ResourceMeta, RevisionInfo, RevisionStatus

faker = Faker()


def _stale_fh() -> OSError:
    err = OSError(errno.ESTALE, "Stale file handle")
    err.errno = errno.ESTALE
    return err


@pytest.fixture
def tmpdir_path() -> Generator[Path]:
    with tempfile.TemporaryDirectory(dir="./") as d:
        yield Path(d)


def _make_meta(pk: str) -> ResourceMeta:
    now = faker.date_time()
    user = faker.user_name()
    return ResourceMeta(
        current_revision_id="rev-1",
        resource_id=pk,
        total_revision_count=1,
        created_time=now,
        updated_time=now,
        created_by=user,
        updated_by=user,
    )


def _make_info(pk: str) -> RevisionInfo:
    now = faker.date_time()
    user = faker.user_name()
    return RevisionInfo(
        uid="uid-1",  # ty:ignore[invalid-argument-type]
        resource_id=pk,
        revision_id=f"{pk}:1",
        schema_version=None,
        data_hash="h",
        status=RevisionStatus.stable,
        created_time=now,
        updated_time=now,
        created_by=user,
        updated_by=user,
    )


def make_flaky_open(target_name_contains: str, fail_times: int):
    """Return ``(flaky_fn, state)``.

    ``flaky_fn`` is suitable for ``monkeypatch.setattr(pathlib.Path, "open", flaky_fn)``
    — a *function* (not an instance) so the descriptor protocol binds ``self``
    correctly. ``state["calls"]`` counts how many times we faked ESTALE.
    """
    orig = pathlib.Path.open
    state = {"calls": 0}

    def flaky(self, *args, **kwargs):
        if target_name_contains in self.name and state["calls"] < fail_times:
            state["calls"] += 1
            raise _stale_fh()
        return orig(self, *args, **kwargs)

    return flaky, state


# ---------------------------------------------------------------------------
# DiskMetaStore
# ---------------------------------------------------------------------------


def test_meta_store_getitem_retries_estale(tmpdir_path: Path, monkeypatch):
    """Reading a meta file retries when the kernel returns ESTALE.

    Simulates an NFS stale-handle race: the meta exists on disk but our
    cached inode was invalidated by another client. The first open syscall
    fails with ESTALE; the retry sees a fresh inode and succeeds.
    """
    store = DiskMetaStore(encoding="msgpack", rootdir=tmpdir_path)  # ty:ignore[invalid-argument-type]
    store["k:1"] = _make_meta("k:1")

    flaky, state = make_flaky_open("k:1", fail_times=2)
    monkeypatch.setattr(pathlib.Path, "open", flaky)

    result = store["k:1"]
    assert result.resource_id == "k:1"
    assert state["calls"] == 2  # proves we actually retried


def test_meta_store_getitem_persistent_estale_still_raises(
    tmpdir_path: Path, monkeypatch
):
    """A truly persistent ESTALE eventually surfaces — we do not loop forever."""
    store = DiskMetaStore(encoding="msgpack", rootdir=tmpdir_path)  # ty:ignore[invalid-argument-type]
    store["k:1"] = _make_meta("k:1")

    def always_estale(self, *a, **k):
        raise _stale_fh()

    monkeypatch.setattr(pathlib.Path, "open", always_estale)

    with pytest.raises(OSError) as exc_info:
        store["k:1"]
    assert exc_info.value.errno == errno.ESTALE


def test_meta_store_iter_search_skips_estale_file(tmpdir_path: Path, monkeypatch):
    """One stale-handle file mid-iteration must not crash the whole search.

    Matches the existing FileNotFoundError-skip behavior: a transient ESTALE
    on a single file is treated as "skip this file" once retries are
    exhausted, never as "fail the entire search".
    """
    store = DiskMetaStore(encoding="msgpack", rootdir=tmpdir_path)  # ty:ignore[invalid-argument-type]
    store["real:1"] = _make_meta("real:1")
    store["ghost:2"] = _make_meta("ghost:2")

    orig_open = pathlib.Path.open

    def fake_open(self, *a, **k):
        if self.name.startswith("ghost:2"):
            raise _stale_fh()
        return orig_open(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "open", fake_open)

    results = list(store.iter_search(ResourceMetaSearchQuery()))
    assert [m.resource_id for m in results] == ["real:1"]


def test_meta_store_setitem_retries_estale_on_replace(tmpdir_path: Path, monkeypatch):
    """An ESTALE on the atomic ``os.replace`` commit step is retried."""
    from specstar.resource_manager.meta_store import simple as simple_mod

    store = DiskMetaStore(encoding="msgpack", rootdir=tmpdir_path)  # ty:ignore[invalid-argument-type]

    orig_replace = simple_mod.os.replace
    state = {"calls": 0}

    def flaky_replace(src, dst):
        if state["calls"] == 0:
            state["calls"] += 1
            raise _stale_fh()
        return orig_replace(src, dst)

    monkeypatch.setattr(simple_mod.os, "replace", flaky_replace, raising=True)

    store["k:1"] = _make_meta("k:1")
    assert store["k:1"].resource_id == "k:1"
    assert state["calls"] == 1


# ---------------------------------------------------------------------------
# DiskResourceStore
# ---------------------------------------------------------------------------


def test_resource_store_get_data_bytes_retries_estale(tmpdir_path: Path, monkeypatch):
    """Opening the data file retries when the first open returns ESTALE."""
    import io

    store = DiskResourceStore(encoding="msgpack", rootdir=tmpdir_path)  # ty:ignore[invalid-argument-type]
    info = _make_info("res:1")
    store.save(info, io.BytesIO(b"hello"))

    flaky, state = make_flaky_open("data", fail_times=1)
    monkeypatch.setattr(pathlib.Path, "open", flaky)

    with store.get_data_bytes(info.resource_id, info.revision_id, None) as f:
        assert f.read() == b"hello"
    assert state["calls"] == 1


# ---------------------------------------------------------------------------
# DiskBlobStore
# ---------------------------------------------------------------------------


def test_blob_store_get_retries_estale(tmpdir_path: Path, monkeypatch):
    """Blob get() retries when the kernel returns ESTALE on the data read."""
    store = DiskBlobStore(tmpdir_path)
    stored = store.put(b"payload", key="hash-1")

    orig_read_bytes = pathlib.Path.read_bytes
    state = {"calls": 0}

    def flaky_read_bytes(self):
        if self.name == "hash-1" and state["calls"] == 0:
            state["calls"] += 1
            raise _stale_fh()
        return orig_read_bytes(self)

    monkeypatch.setattr(pathlib.Path, "read_bytes", flaky_read_bytes)

    result = store.get(stored.file_id)
    assert result.data == b"payload"
    assert state["calls"] == 1
