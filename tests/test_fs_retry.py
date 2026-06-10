"""ESTALE / FS-race tolerance for the disk-backed stores (issue #352).

Two classes of race are covered:

* **NFS ESTALE** — a concurrent rename/unlink on another client invalidates
  the inode the kernel handed us, and the next syscall raises
  ``OSError(errno=116, "Stale file handle")``. Bounded retry resolves it.
* **Local-FS TOCTOU** — even on a single-host POSIX filesystem, the
  ``exists() → unlink()/open()`` patterns inside ``DiskResourceStore.save``
  and ``DiskBlobStore`` race against concurrent writers/deleters and can
  raise ``FileExistsError`` or ``FileNotFoundError``. The fix uses atomic
  ``os.replace`` (tmp + rename) so concurrent operations never observe a
  half-written file or fail to swap a symlink.
"""

from __future__ import annotations

import errno
import io
import pathlib
import sys
import tempfile
import threading
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


# ---------------------------------------------------------------------------
# Local-FS race: DiskResourceStore.save() symlink swap
# ---------------------------------------------------------------------------


def test_concurrent_save_does_not_crash(tmpdir_path: Path):
    """Two threads racing save() on the same logical key must not crash.

    Regression for #352 (local-FS half). The original symlink swap was
    ``exists() → unlink() → symlink_to()`` — a classic TOCTOU. Concurrent
    saves of the same ``(resource_id, revision_id, schema_version)`` raced
    on the symlink and surfaced as either:

    * ``FileExistsError`` — both threads passed ``exists()=False`` and one
      symlinked first;
    * ``FileNotFoundError`` — both passed ``exists()=True`` and one
      unlinked first.

    The atomic-replace fix swaps via a tmp symlink + ``os.replace``, so a
    racing save always sees a complete symlink atomically.
    """
    store = DiskResourceStore(encoding="msgpack", rootdir=tmpdir_path)  # ty:ignore[invalid-argument-type]
    errors: list[BaseException] = []
    iterations = 200

    def saver(thread_idx: int) -> None:
        try:
            for i in range(iterations):
                info = RevisionInfo(
                    uid=f"uid-{thread_idx}-{i}",  # ty:ignore[invalid-argument-type]
                    resource_id="shared:1",
                    revision_id="shared:1:1",
                    schema_version=None,
                    data_hash="h",
                    status=RevisionStatus.stable,
                    created_time=faker.date_time(),
                    updated_time=faker.date_time(),
                    created_by="u",
                    updated_by="u",
                )
                store.save(info, io.BytesIO(f"data-{thread_idx}-{i}".encode()))
        except BaseException as exc:
            errors.append(exc)

    old_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        threads = [threading.Thread(target=saver, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        sys.setswitchinterval(old_interval)

    assert not errors, f"concurrent save() crashed: {errors[0]!r}"


def test_concurrent_save_leaves_consistent_winner(tmpdir_path: Path):
    """After racing saves, the symlink resolves to exactly one valid uid.

    Reader-side consistency: under the atomic-replace fix the symlink is
    always either the old target or the new one — never a dangling link, a
    half-written link, or absent. A subsequent ``get_data_bytes`` must
    return one of the writers' payloads intact, byte-for-byte.
    """
    store = DiskResourceStore(encoding="msgpack", rootdir=tmpdir_path)  # ty:ignore[invalid-argument-type]
    saves_per_thread = 200
    payloads_written: set[bytes] = set()
    lock = threading.Lock()

    def saver(thread_idx: int) -> None:
        for i in range(saves_per_thread):
            payload = f"data-{thread_idx}-{i}".encode()
            with lock:
                payloads_written.add(payload)
            info = RevisionInfo(
                uid=f"uid-{thread_idx}-{i}",  # ty:ignore[invalid-argument-type]
                resource_id="shared:2",
                revision_id="shared:2:1",
                schema_version=None,
                data_hash="h",
                status=RevisionStatus.stable,
                created_time=faker.date_time(),
                updated_time=faker.date_time(),
                created_by="u",
                updated_by="u",
            )
            store.save(info, io.BytesIO(payload))

    old_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        threads = [threading.Thread(target=saver, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        sys.setswitchinterval(old_interval)

    # The final symlink must resolve to a complete payload that one of the
    # writers actually wrote — never garbage, never an empty file.
    with store.get_data_bytes("shared:2", "shared:2:1", None) as f:
        observed = f.read()
    assert observed in payloads_written, (
        f"reader observed payload not written by any thread: {observed!r}"
    )


# ---------------------------------------------------------------------------
# Local-FS race: DiskBlobStore.put() must be atomic w.r.t. readers
# ---------------------------------------------------------------------------


def test_concurrent_blob_put_readers_never_see_partial_bytes(tmpdir_path: Path):
    """A reader's get() must see the full payload or nothing — never a prefix.

    Two writers ``put`` the same content-addressed blob (key=None, same
    payload → same hash). The original code did ``file_path.write_bytes``
    directly, so a reader hitting the file mid-write would see a truncated
    payload. The atomic fix writes to a tmp file and ``os.replace``-s it
    into place, so readers always see the complete prior bytes or the
    complete new bytes.
    """
    store = DiskBlobStore(tmpdir_path)
    # Use a large-enough payload that a mid-write read would catch a prefix.
    payload = b"x" * (256 * 1024)  # 256 KB
    file_id = "shared-hash"

    # Pre-seed so reader's get() always finds *something*.
    store.put(payload, key=file_id)

    errors: list[BaseException] = []
    stop = threading.Event()
    iterations = 100

    def writer() -> None:
        for _ in range(iterations):
            if stop.is_set():
                return
            try:
                store.put(payload, key=file_id)
            except BaseException as exc:
                errors.append(exc)
                return

    def reader() -> None:
        for _ in range(iterations):
            try:
                got = store.get(file_id)
                if got.data != payload:
                    errors.append(
                        AssertionError(
                            f"reader saw partial bytes: len={len(got.data)} "
                            f"expected={len(payload)}"
                        )
                    )
                    return
            except BaseException as exc:
                errors.append(exc)
                return

    old_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        stop.set()
        sys.setswitchinterval(old_interval)

    assert not errors, f"concurrent put/get failed: {errors[0]!r}"


# ---------------------------------------------------------------------------
# Local-FS race: DiskBlobStore.get() TOCTOU translation
# ---------------------------------------------------------------------------


def test_blob_get_translates_toctou_race_to_controlled_error(
    tmpdir_path: Path, monkeypatch
):
    """A blob unlinked between exists() and read() raises the typed message.

    Race: ``DiskBlobStore.get`` calls ``file_path.exists()`` then
    ``file_path.read_bytes()``. A concurrent purge in the window leaves
    ``read_bytes`` to raise a raw ``FileNotFoundError`` with the kernel's
    "[Errno 2] No such file or directory: '/abs/path'" message — leaking
    a filesystem path to the API caller. The fix removes the TOCTOU guard
    and translates ENOENT from the read into the same controlled
    "Blob {file_id} not found" surface as the non-race path.
    """
    store = DiskBlobStore(tmpdir_path)
    stored = store.put(b"payload", key="race-key")

    # Force the exists() check to lie, then make the file truly absent.
    monkeypatch.setattr(pathlib.Path, "exists", lambda self: True)
    (tmpdir_path / "race-key").unlink()

    with pytest.raises(FileNotFoundError) as exc_info:
        store.get(stored.file_id)
    assert "Blob race-key not found" in str(exc_info.value)


def test_blob_get_stream_translates_toctou_race_to_controlled_error(
    tmpdir_path: Path, monkeypatch
):
    """``get_stream`` matches ``get`` — controlled "Blob not found" on race.

    Same window: ``exists()`` says yes, the file is purged before ``stat``
    or ``open``. Without the fix the caller gets a raw pathlib ENOENT with
    an absolute path; with the fix it gets the same controlled message as
    the missing-file path.
    """
    store = DiskBlobStore(tmpdir_path)
    stored = store.put(b"payload", key="race-stream-key")

    monkeypatch.setattr(pathlib.Path, "exists", lambda self: True)
    (tmpdir_path / "race-stream-key").unlink()

    with pytest.raises(FileNotFoundError) as exc_info:
        store.get_stream(stored.file_id)
    assert "Blob race-stream-key not found" in str(exc_info.value)


def test_load_session_meta_translates_toctou_race_to_controlled_error(
    tmpdir_path: Path, monkeypatch
):
    """Session metadata read raises the typed "Upload session not found" surface.

    Race: ``_load_session_meta`` does ``path.exists()`` then
    ``path.read_bytes()``. A concurrent ``abort_upload_session`` or cleanup
    in the window leaves the read to surface a raw ``FileNotFoundError``
    with an absolute filesystem path. The fix translates ENOENT from the
    read into the same controlled "Upload session {upload_id} not found"
    surface as the missing-session path.
    """
    store = DiskBlobStore(tmpdir_path)
    session = store.create_upload_session(key="any")
    upload_id = session.upload_id

    monkeypatch.setattr(pathlib.Path, "exists", lambda self: True)
    (tmpdir_path / "_sessions" / f"{upload_id}.meta").unlink()

    with pytest.raises(FileNotFoundError) as exc_info:
        store._load_session_meta(upload_id)
    assert f"Upload session {upload_id} not found" in str(exc_info.value)
