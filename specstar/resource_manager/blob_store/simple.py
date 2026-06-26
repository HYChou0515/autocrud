import datetime as dt
import fcntl
import os
import threading
import uuid
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path

import msgspec
from msgspec import UNSET, Struct, UnsetType
from xxhash import xxh3_128, xxh3_128_hexdigest

from specstar.resource_manager.basic import IBlobStore
from specstar.types import (
    Binary,
    BlobResponse,
    BlobStreamInfo,
    BlobUploadSession,
)
from specstar.util.fanout import (
    SHARD_ROOT,
    iter_legacy_children,
    sharded_dir,
    sharded_path,
)
from specstar.util.fs_retry import retry_on_estale


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write *data* to *path* atomically (tmp file in same dir + ``os.replace``).

    Concurrent readers either see the previous complete file or the new
    complete file — never a half-written prefix. See #352.
    """
    tmp = path.with_name(f"{path.name}.tmp.{uuid.uuid4().hex}")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except BaseException:
        with suppress(FileNotFoundError):
            tmp.unlink()
        raise


def _fallback_content_type_guesser(data: bytes) -> UnsetType:
    # Fallback: use generic binary type
    return UNSET


def get_content_type_guesser():
    try:
        import magic

        # Probe once to verify libmagic is actually usable
        magic.from_buffer(b"", mime=True)

        def guess_content_type(data: bytes) -> str:
            return magic.from_buffer(data, mime=True)

        return guess_content_type
    except ImportError:
        return _fallback_content_type_guesser
    except Exception as exc:
        import warnings

        warnings.warn(
            f"python-magic is installed but content-type detection failed ({exc}). "
            "Falling back to no content-type detection. "
            "If this is unexpected, ensure libmagic is installed "
            "(e.g. `apt install libmagic1`).",
            stacklevel=2,
        )
        return _fallback_content_type_guesser


class BasicBlobStore(IBlobStore):
    def guess_content_type(
        self, data: bytes, content_type: str | UnsetType
    ) -> str | UnsetType:
        """Guess content type using the content type guesser."""
        if content_type:
            return content_type
        if not hasattr(self, "content_type_guesser"):
            self.content_type_guesser = get_content_type_guesser()
        return self.content_type_guesser(data)

    def get_url(self, file_id: str) -> str | None:
        """
        Get a direct download URL for the blob if supported.
        Returns None if not supported (e.g. local storage without a public server).
        """
        return None

    def get_stream(self, file_id: str) -> BlobStreamInfo | None:
        """Return a streaming iterator for blob content.

        Returns a :class:`BlobStreamInfo` containing a chunk iterator,
        file size, and content type — suitable for
        :class:`~starlette.responses.StreamingResponse`.

        Returns ``None`` when the implementation does not support
        streaming (e.g. :class:`MemoryBlobStore` where data is already
        in memory).  The caller should fall back to :meth:`get` in that
        case.

        Raises:
            FileNotFoundError: If the blob does not exist.
        """
        return None

    def get_response(self, file_id: str) -> BlobResponse:
        """Return the preferred download response for a blob.

        The blob store decides its own download strategy.  The default
        order is:

        1. **stream** — :meth:`get_stream` (constant memory, works
           through proxies).
        2. **data** — :meth:`get` (full body in memory).
        3. **redirect** — :meth:`get_url` (presigned URL / CDN).

        Subclasses may override this to change the priority (e.g.
        :class:`S3BlobStore` can put ``get_url`` first when
        ``prefer_presigned_url=True``).

        Raises:
            FileNotFoundError: If the blob does not exist.
        """
        stream = self.get_stream(file_id)
        if stream is not None:
            return BlobResponse("stream", stream=stream)

        blob = self.get(file_id)
        if blob is not None:
            return BlobResponse("data", blob=blob)

        url = self.get_url(file_id)
        if url is not None:
            return BlobResponse("redirect", url=url)

        raise FileNotFoundError(f"Blob {file_id} not found")

    # ------------------------------------------------------------------
    # Orphan-candidate tracking (issue #370, incremental GC)
    #
    # A best-effort, in-memory, process-local set of file_ids whose
    # approximate count has dropped to <= 0.  Populated by ``decref`` and
    # cleared by ``incref`` / ``quarantine`` / ``delete``.  Non-persistent on
    # purpose: a restart loses it, and the reconcile pass recovers everything.
    # ------------------------------------------------------------------

    def _candidate_set(self) -> set[str]:
        candidates = getattr(self, "_candidates", None)
        if candidates is None:
            candidates = set()
            self._candidates = candidates
        return candidates

    def _note_count(self, file_id: str, count: int) -> None:
        """Record/clear *file_id* as an orphan candidate from a count update."""
        if count <= 0:
            self._candidate_set().add(file_id)
        else:
            self._candidate_set().discard(file_id)

    def _clear_candidate(self, file_id: str) -> None:
        self._candidate_set().discard(file_id)

    def iter_orphan_candidates(self, *, modified_before: dt.datetime):
        for file_id in list(self._candidate_set()):
            mtime = self.get_mtime(file_id)
            # Skip non-active (already quarantined/deleted) and too-fresh blobs.
            if mtime is None or mtime >= modified_before:
                continue
            yield file_id


# ---------------------------------------------------------------------------
# Shared session state dataclass (used by MemoryBlobStore and DiskBlobStore)
# ---------------------------------------------------------------------------


@dataclass
class _UploadSessionState:
    """In-memory state for an upload session with eager-merge support.

    Parts arriving in order are immediately appended to ``merged``.
    Out-of-order parts are buffered in ``buffered`` and flushed as
    soon as the gap fills.
    """

    upload_id: str
    status: str = "pending"  # pending | uploading | uploaded | finalized | aborted
    content_type: str | UnsetType = UNSET
    size: int | None = None
    key: str | None = None
    total_parts: int | None = None
    # Eager-merge state
    merged: list[bytes] = field(default_factory=list)
    buffered: dict[int, bytes] = field(default_factory=dict)
    next_expected: int = 1
    parts_received: list[int] = field(default_factory=list)
    uploaded_size: int = 0


class MemoryBlobStore(BasicBlobStore):
    """In-memory blob store — data is lost when the process exits."""

    def __init__(self):
        self._store: dict[str, Binary] = {}
        # Quarantined blobs (issue #370): file_id -> (Binary, entered_at).
        self._quarantine: dict[str, tuple[Binary, dt.datetime]] = {}
        # Approximate, non-atomic ref counts (issue #370).
        self._refcount: dict[str, int] = {}
        # Last-write time per active blob (the "age" source for the T1 gate).
        self._mtime: dict[str, dt.datetime] = {}
        self._sessions: dict[str, _UploadSessionState] = {}
        self._session_locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def put(
        self,
        data: bytes,
        *,
        key: str | None = None,
        content_type: str | UnsetType = UNSET,
    ) -> Binary:
        file_id = key if key is not None else xxh3_128_hexdigest(data)

        # Create Binary object with metadata
        stored_binary = Binary(
            file_id=file_id,
            size=len(data),
            data=data,
            content_type=self.guess_content_type(data, content_type),
        )

        self._store[file_id] = stored_binary
        self._mtime[file_id] = dt.datetime.now(dt.timezone.utc)
        return stored_binary

    def get(self, file_id: str) -> Binary:
        if file_id in self._store:
            return self._store[file_id]
        # Active miss: fall through to quarantine so a transiently-quarantined
        # blob is never lost to readers (issue #370).
        if file_id in self._quarantine:
            return self._quarantine[file_id][0]
        raise FileNotFoundError(f"Blob {file_id} not found")

    def exists(self, file_id: str) -> bool:
        return file_id in self._store or file_id in self._quarantine

    def delete(self, file_id: str) -> None:
        """Idempotently remove a blob from active or quarantine (no error if absent)."""
        self._store.pop(file_id, None)
        self._quarantine.pop(file_id, None)
        self._mtime.pop(file_id, None)
        self._refcount.pop(file_id, None)
        self._clear_candidate(file_id)

    def quarantine(self, file_id: str, *, now: dt.datetime) -> None:
        """Move a blob from the active area into quarantine, stamping ``now``
        as its entry time. No-op if the blob is not active."""
        binary = self._store.pop(file_id, None)
        if binary is None:
            return
        self._mtime.pop(file_id, None)
        self._clear_candidate(file_id)
        self._quarantine[file_id] = (binary, now)

    def get_mtime(self, file_id: str) -> dt.datetime | None:
        return self._mtime.get(file_id)

    def touch(self, file_id: str, *, now: dt.datetime | None = None) -> None:
        if file_id not in self._store:
            return
        self._mtime[file_id] = now or dt.datetime.now(dt.timezone.utc)

    def restore_from_quarantine(self, file_id: str) -> None:
        """Move a blob back from quarantine to the active area. No-op if absent."""
        entry = self._quarantine.pop(file_id, None)
        if entry is None:
            return
        binary, entered_at = entry
        self._store[file_id] = binary
        self._mtime[file_id] = entered_at

    def incref(self, file_id: str) -> int:
        n = self._refcount.get(file_id, 0) + 1
        self._refcount[file_id] = n
        self._note_count(file_id, n)
        return n

    def decref(self, file_id: str) -> int:
        n = max(0, self._refcount.get(file_id, 0) - 1)
        self._refcount[file_id] = n
        self._note_count(file_id, n)
        return n

    def iter_active(self):
        yield from list(self._store.keys())

    def iter_quarantined(self, *, entered_before: dt.datetime):
        """Yield file_ids quarantined strictly before ``entered_before``."""
        for fid, (_binary, entered_at) in list(self._quarantine.items()):
            if entered_at < entered_before:
                yield fid

    # -- Session locking ------------------------------------------------

    def _get_session_lock(self, upload_id: str) -> threading.Lock:
        """Return a per-session ``threading.Lock``, creating it on first access."""
        with self._global_lock:
            if upload_id not in self._session_locks:
                self._session_locks[upload_id] = threading.Lock()
            return self._session_locks[upload_id]

    # -- Upload session methods -------------------------------------------

    def create_upload_session(
        self,
        *,
        key: str | None = None,
        content_type: str | UnsetType = UNSET,
        size: int | None = None,
        total_parts: int | None = None,
    ) -> BlobUploadSession:
        upload_id = uuid.uuid4().hex
        state = _UploadSessionState(
            upload_id=upload_id,
            content_type=content_type,
            size=size,
            key=key,
            total_parts=total_parts,
        )
        self._sessions[upload_id] = state
        return BlobUploadSession(
            upload_id=upload_id,
            file_id="",
            status="pending",
            upload_method="proxy",
            upload_url=f"/blobs/upload-sessions/{upload_id}/content",
            content_type=content_type,
            size=size,
            total_parts=total_parts,
        )

    def get_upload_session(self, upload_id: str) -> BlobUploadSession:
        state = self._sessions.get(upload_id)
        if state is None:
            raise FileNotFoundError(f"Upload session {upload_id} not found")
        return BlobUploadSession(
            upload_id=state.upload_id,
            file_id="",
            status=state.status,  # ty:ignore[invalid-argument-type]
            upload_method="proxy",
            content_type=state.content_type,
            size=state.size,
            uploaded_size=state.uploaded_size,
            total_parts=state.total_parts,
            parts_received=list(state.parts_received),
        )

    def upload_to_session(
        self, upload_id: str, data: bytes, *, part_number: int
    ) -> None:
        if part_number < 1:
            raise ValueError("part_number must be >= 1")
        with self._get_session_lock(upload_id):
            state = self._sessions.get(upload_id)
            if state is None:
                raise FileNotFoundError(f"Upload session {upload_id} not found")
            if state.status not in ("pending", "uploading"):
                raise ValueError(
                    f"Session status is '{state.status}', expected 'pending' or 'uploading'"
                )
            # Idempotent: if already merged (part_number < next_expected), ignore
            if part_number < state.next_expected:
                return

            # Eager-merge strategy
            if part_number == state.next_expected:
                # In-order: append to merged and flush consecutive buffered parts
                state.merged.append(data)
                state.uploaded_size += len(data)
                if part_number not in state.parts_received:
                    state.parts_received.append(part_number)
                    state.parts_received.sort()
                state.next_expected += 1
                # Flush buffered consecutive parts
                while state.next_expected in state.buffered:
                    buffered_data = state.buffered.pop(state.next_expected)
                    state.merged.append(buffered_data)
                    state.next_expected += 1
            else:
                # Out-of-order: buffer (overwrite if retry)
                if part_number in state.buffered:
                    # Retry: adjust uploaded_size
                    state.uploaded_size -= len(state.buffered[part_number])
                state.buffered[part_number] = data
                state.uploaded_size += len(data)
                if part_number not in state.parts_received:
                    state.parts_received.append(part_number)
                    state.parts_received.sort()

            state.status = "uploading"

    def finalize_upload_session(self, upload_id: str) -> Binary:
        with self._get_session_lock(upload_id):
            state = self._sessions.get(upload_id)
            if state is None:
                raise FileNotFoundError(f"Upload session {upload_id} not found")
            if state.status not in ("uploaded", "uploading"):
                raise ValueError(
                    f"Session status is '{state.status}', expected 'uploaded' or 'uploading'"
                )
            # Validate total_parts
            num_received = len(state.parts_received)
            if state.total_parts is not None and num_received != state.total_parts:
                raise ValueError(
                    f"Expected {state.total_parts} parts but received {num_received}"
                )
            # Check for gaps (buffered parts that couldn't be merged)
            if state.buffered:
                missing = sorted(state.buffered.keys())
                raise ValueError(
                    f"Cannot finalize: parts still buffered (missing earlier parts). "
                    f"Buffered part numbers: {missing}"
                )
            combined = b"".join(state.merged)
            stored = self.put(
                combined,
                key=state.key,
                content_type=state.content_type,
            )
            state.status = "finalized"
            state.merged.clear()
            state.buffered.clear()
            return Binary(
                file_id=stored.file_id,
                size=stored.size,
                content_type=stored.content_type,
            )

    def abort_upload_session(self, upload_id: str) -> None:
        with self._get_session_lock(upload_id):
            state = self._sessions.get(upload_id)
            if state is None:
                raise FileNotFoundError(f"Upload session {upload_id} not found")
            if state.status == "finalized":
                raise ValueError("Cannot abort a finalized session")
            state.merged.clear()
            state.buffered.clear()
            state.status = "aborted"


class _DiskSessionMeta(Struct, kw_only=True):
    """Serializable session metadata persisted alongside uploaded data.

    Unlike ``_UploadSessionState`` (which is in-memory only), this struct
    is msgpack-encoded to disk so that **any** ``DiskBlobStore`` instance
    sharing the same ``root_path`` (e.g. via a Kubernetes PVC) can read
    and mutate the session state — essential for HPA / multi-pod setups.
    """

    upload_id: str
    status: str = "pending"  # pending | uploading | uploaded | finalized | aborted
    content_type: str | UnsetType = UNSET
    size: int | None = None
    key: str | None = None
    uploaded_size: int = 0
    total_parts: int | None = None
    parts_received: list[int] = []
    next_expected: int = 1


class _DiskBlobMeta(Struct, kw_only=True):
    """Metadata sidecar for a DiskBlobStore blob.

    Stored alongside the raw blob file (as ``<safe_name>.blobmeta``) so
    that the blob data itself is never msgpack-encoded — eliminating the
    4 GB ``msgpack`` binary encoding limit.
    """

    file_id: str
    size: int
    content_type: str | UnsetType = UNSET


class DiskBlobStore(BasicBlobStore):
    """Disk-based blob store — data persisted to local filesystem.

    Blobs are spread across a sharded subdirectory tree
    (``root_path/_sh/<ab>/<cd>/<file_id>`` plus a ``.blobmeta`` sidecar in
    the same directory) so that no single directory accumulates an unbounded
    number of entries — which on NAS / networked filesystems hits
    per-directory inode/dirent limits. Blobs written before this layout
    (flat at ``root_path/<file_id>``) are still read transparently; call
    :meth:`migrate_layout` to relocate them. See #387.

    Upload sessions are persisted under ``root_path/_sessions/`` (each
    session in its own sharded ``_sh/<ab>/<cd>/<upload_id>/`` directory) so
    that multiple processes (or Kubernetes pods sharing a PVC) can cooperate
    on the same upload lifecycle.
    """

    def __init__(self, root_path: str | Path):
        self.root_path = Path(root_path)
        self.root_path.mkdir(parents=True, exist_ok=True)
        self.encoder = msgspec.msgpack.Encoder()
        self.decoder = msgspec.msgpack.Decoder(Binary)
        self._sessions_dir = self.root_path / "_sessions"
        self._sessions_dir.mkdir(exist_ok=True)
        self._session_meta_encoder = msgspec.msgpack.Encoder()
        self._session_meta_decoder = msgspec.msgpack.Decoder(_DiskSessionMeta)
        self._blob_meta_decoder = msgspec.msgpack.Decoder(_DiskBlobMeta)

    # -- Internal helpers for disk-persisted sessions ---------------------

    def _session_dir(self, upload_id: str) -> Path:
        """Per-session directory ``_sessions/_sh/<ab>/<cd>/<upload_id>/``.

        Each upload owns one directory holding all of its files (``meta``,
        ``data``, ``part.N``, ``lock``). Sharding the session directory keeps
        ``_sessions/`` from accumulating an unbounded number of entries, and a
        per-session directory makes transient cleanup (``data``/``part.*``) a
        single bounded operation. See #387.
        """
        return sharded_dir(self._sessions_dir, upload_id) / upload_id

    def _session_meta_path(self, upload_id: str) -> Path:
        """Path for the msgpack-encoded session metadata file."""
        return self._session_dir(upload_id) / "meta"

    def _session_data_path(self, upload_id: str) -> Path:
        """Path for the raw uploaded bytes (merged/final data)."""
        return self._session_dir(upload_id) / "data"

    def _session_part_path(self, upload_id: str, part_number: int) -> Path:
        """Path for an out-of-order part file."""
        return self._session_dir(upload_id) / f"part.{part_number}"

    def _session_lock_path(self, upload_id: str) -> Path:
        """Path for the per-session POSIX lock file."""
        return self._session_dir(upload_id) / "lock"

    @contextmanager
    def _lock_session(self, upload_id: str):
        """Acquire an exclusive POSIX ``flock`` for the given session.

        Serialises all read-modify-write cycles on the session metadata
        and data files so that concurrent workers / pods do not corrupt
        them.  The lock is automatically released when the context exits
        (including on exceptions or process crashes).
        """
        lock_path = self._session_lock_path(upload_id)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = lock_path.open("w")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()

    def _save_session_meta(self, meta: _DiskSessionMeta) -> None:
        """Persist session metadata atomically (write-to-tmp + rename)."""
        encoded = self._session_meta_encoder.encode(meta)
        path = self._session_meta_path(meta.upload_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name("meta.tmp")
        tmp.write_bytes(encoded)
        tmp.rename(path)

    def _load_session_meta(self, upload_id: str) -> _DiskSessionMeta:
        """Load session metadata from disk, raising ``FileNotFoundError``."""
        path = self._session_meta_path(upload_id)
        # No exists() guard — it would TOCTOU against a concurrent abort and
        # leak a raw "[Errno 2] No such file or directory: '/abs/path'"
        # message. Read straight and translate ENOENT to the controlled
        # "Upload session {upload_id} not found" surface. See #352.
        try:
            raw = retry_on_estale(path.read_bytes)
        except FileNotFoundError:
            raise FileNotFoundError(f"Upload session {upload_id} not found") from None
        return self._session_meta_decoder.decode(raw)

    # -- Blob put / get / exists ------------------------------------------

    @staticmethod
    def _safe_name(file_id: str) -> str:
        """Filesystem-safe leaf name for *file_id*."""
        return file_id.replace("/", "_").replace("..", "_")

    def _candidate_data_paths(self, safe_name: str):
        """Yield data-file paths to try on read: sharded first, legacy flat last.

        New writes land in the sharded tree (``_sh/<ab>/<cd>/<name>``); blobs
        written before #387 are still flat at the root. The ``.blobmeta``
        sidecar always lives next to whichever data file is found. See #387.
        """
        yield sharded_path(self.root_path, safe_name)
        yield self.root_path / safe_name

    def _blob_exists(self, safe_name: str) -> bool:
        return any(p.exists() for p in self._candidate_data_paths(safe_name))

    def put(
        self,
        data: bytes,
        *,
        key: str | None = None,
        content_type: str | UnsetType = UNSET,
    ) -> Binary:
        file_id = key if key is not None else xxh3_128_hexdigest(data)
        safe_name = self._safe_name(file_id)

        # New blobs are written into the sharded tree to keep any single
        # directory from accumulating an unbounded number of entries (NAS
        # per-directory inode/dirent limits). See #387.
        blob_dir = sharded_dir(self.root_path, safe_name)
        file_path = blob_dir / safe_name
        final_content_type = self.guess_content_type(data, content_type)
        # Caller-specified key always overwrites; content-addressed (hash) keys
        # are immutable, so skip the write when the blob already exists in
        # *either* layout (sharded or legacy flat). See #387, #352.
        if key is not None or not self._blob_exists(safe_name):
            # Atomic write: dump bytes into a uniquely-named tmp file in the
            # same (shard) directory, then ``os.replace`` it onto the final
            # path. A concurrent reader either sees the previous complete file
            # or the new complete file — never a truncated mid-write prefix.
            # See #352 (local-FS half).
            blob_dir.mkdir(parents=True, exist_ok=True)
            blob_meta = _DiskBlobMeta(
                file_id=file_id,
                size=len(data),
                content_type=final_content_type,
            )
            meta_path = blob_dir / f"{safe_name}.blobmeta"
            _atomic_write_bytes(file_path, data)
            _atomic_write_bytes(meta_path, self.encoder.encode(blob_meta))
        return Binary(
            file_id=file_id,
            size=len(data),
            data=data,
            content_type=final_content_type,
        )

    # -- Blob read / GC-aware get / exists / delete -----------------------

    @property
    def _quarantine_root(self) -> Path:
        """Reserved container for quarantined blobs (issue #370), itself
        sharded. A directory, so :meth:`migrate_layout` skips it."""
        return self.root_path / "_quarantine"

    def _quarantine_data_path(self, safe_name: str) -> Path:
        return sharded_path(self._quarantine_root, safe_name)

    def _find_active(self, safe_name: str) -> Path | None:
        """Return the active blob's data file (sharded or legacy flat), or None."""
        for candidate in self._candidate_data_paths(safe_name):
            if candidate.exists():
                return candidate
        return None

    def _read_blob_at(self, data_path: Path, safe_name: str) -> Binary | None:
        """Read a blob (data + adjacent ``.blobmeta``) at *data_path*, or None.

        Skips an ``exists()`` guard: it would race a concurrent purge/migration
        and leak a raw "[Errno 2] ..." path. Translate ENOENT to None. See #352.
        """
        try:
            data = retry_on_estale(data_path.read_bytes)
        except FileNotFoundError:
            return None
        meta_path = data_path.parent / f"{safe_name}.blobmeta"
        try:
            meta_bytes = retry_on_estale(meta_path.read_bytes)
        except FileNotFoundError:
            # Legacy fallback: pre-sidecar format msgpack-encoded the Binary
            # inside the data file itself.
            return self.decoder.decode(data)
        blob_meta = self._blob_meta_decoder.decode(meta_bytes)
        return Binary(
            file_id=blob_meta.file_id,
            size=blob_meta.size,
            data=data,
            content_type=blob_meta.content_type,
        )

    def get(self, file_id: str) -> Binary:
        safe_name = self._safe_name(file_id)
        # Active first (sharded, then legacy flat); on miss fall through to the
        # quarantine area so a transiently-quarantined blob is never lost (#370).
        for data_path in (
            sharded_path(self.root_path, safe_name),
            self.root_path / safe_name,
            self._quarantine_data_path(safe_name),
        ):
            result = self._read_blob_at(data_path, safe_name)
            if result is not None:
                return result
        raise FileNotFoundError(f"Blob {file_id} not found")

    def exists(self, file_id: str) -> bool:
        safe_name = self._safe_name(file_id)
        return (
            self._blob_exists(safe_name)
            or self._quarantine_data_path(safe_name).exists()
        )

    def delete(self, file_id: str) -> None:
        """Idempotently remove a blob (active or quarantined) and its sidecars."""
        safe_name = self._safe_name(file_id)
        for data_path in (
            sharded_path(self.root_path, safe_name),
            self.root_path / safe_name,
            self._quarantine_data_path(safe_name),
        ):
            data_path.unlink(missing_ok=True)
            (data_path.parent / f"{safe_name}.blobmeta").unlink(missing_ok=True)
        self._refcount_path(safe_name).unlink(missing_ok=True)
        (self.root_path / f"{safe_name}.refcount").unlink(missing_ok=True)
        self._clear_candidate(file_id)

    # -- GC primitives (issue #370) ---------------------------------------

    def quarantine(self, file_id: str, *, now: dt.datetime) -> None:
        """Move an active blob (with its sidecar) into the quarantine tree,
        stamping ``now`` as its entry time (the quarantined file's mtime).
        No-op if the blob is not active."""
        safe_name = self._safe_name(file_id)
        src = self._find_active(safe_name)
        if src is None:
            return
        dst = self._quarantine_data_path(safe_name)
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, dst)
        src_meta = src.parent / f"{safe_name}.blobmeta"
        if src_meta.exists():
            os.replace(src_meta, dst.parent / f"{safe_name}.blobmeta")
        ts = now.timestamp()
        os.utime(dst, (ts, ts))
        self._clear_candidate(file_id)

    def restore_from_quarantine(self, file_id: str) -> None:
        """Move a blob back from quarantine into the active sharded tree.
        No-op if not quarantined."""
        safe_name = self._safe_name(file_id)
        src = self._quarantine_data_path(safe_name)
        if not src.exists():
            return
        dst = sharded_path(self.root_path, safe_name)
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, dst)
        src_meta = src.parent / f"{safe_name}.blobmeta"
        if src_meta.exists():
            os.replace(src_meta, dst.parent / f"{safe_name}.blobmeta")

    def _refcount_path(self, safe_name: str) -> Path:
        """Refcount sidecar, kept in the blob's sharded directory."""
        return sharded_dir(self.root_path, safe_name) / f"{safe_name}.refcount"

    def _read_refcount(self, safe_name: str) -> int:
        for path in (
            self._refcount_path(safe_name),
            self.root_path / f"{safe_name}.refcount",  # legacy flat
        ):
            try:
                return int(path.read_text())
            except FileNotFoundError:
                continue
            except ValueError:
                return 0
        return 0

    def incref(self, file_id: str) -> int:
        safe_name = self._safe_name(file_id)
        n = self._read_refcount(safe_name) + 1
        path = self._refcount_path(safe_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(n))
        self._note_count(file_id, n)
        return n

    def decref(self, file_id: str) -> int:
        safe_name = self._safe_name(file_id)
        n = max(0, self._read_refcount(safe_name) - 1)
        path = self._refcount_path(safe_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(n))
        self._note_count(file_id, n)
        return n

    def get_mtime(self, file_id: str) -> dt.datetime | None:
        safe_name = self._safe_name(file_id)
        src = self._find_active(safe_name)
        if src is None:
            return None
        try:
            ts = src.stat().st_mtime
        except FileNotFoundError:
            return None
        return dt.datetime.fromtimestamp(ts, dt.timezone.utc)

    def touch(self, file_id: str, *, now: dt.datetime | None = None) -> None:
        safe_name = self._safe_name(file_id)
        src = self._find_active(safe_name)
        if src is None:
            return
        ts = (now or dt.datetime.now(dt.timezone.utc)).timestamp()
        os.utime(src, (ts, ts))

    @staticmethod
    def _is_blob_data_file(name: str) -> bool:
        return not (
            name.endswith(".blobmeta")
            or name.endswith(".refcount")
            or ".tmp." in name
            or name.endswith(".tmp")
        )

    def _blob_id_at(self, data_file: Path) -> str:
        meta_file = data_file.parent / f"{data_file.name}.blobmeta"
        if meta_file.exists():
            try:
                return self._blob_meta_decoder.decode(meta_file.read_bytes()).file_id
            except Exception:
                pass
        return data_file.name

    def iter_active(self):
        seen: set[str] = set()
        # Legacy flat blobs (files directly under root, excluding reserved dirs).
        for child in iter_legacy_children(self.root_path):
            if not child.is_file() or not self._is_blob_data_file(child.name):
                continue
            fid = self._blob_id_at(child)
            if fid not in seen:
                seen.add(fid)
                yield fid
        # Sharded active blobs under root/_sh/.
        shard_root = self.root_path / SHARD_ROOT
        if shard_root.exists():
            for data_file in shard_root.rglob("*"):
                if not data_file.is_file() or not self._is_blob_data_file(
                    data_file.name
                ):
                    continue
                fid = self._blob_id_at(data_file)
                if fid not in seen:
                    seen.add(fid)
                    yield fid

    def iter_quarantined(self, *, entered_before: dt.datetime):
        """Yield file_ids quarantined strictly before ``entered_before``."""
        qroot = self._quarantine_root
        if not qroot.exists():
            return
        cutoff = entered_before.timestamp()
        for data_file in qroot.rglob("*"):
            if not data_file.is_file() or not self._is_blob_data_file(data_file.name):
                continue
            try:
                mtime = data_file.stat().st_mtime
            except FileNotFoundError:
                continue
            if mtime >= cutoff:
                continue
            yield self._blob_id_at(data_file)

    def get_stream(self, file_id: str):
        """Stream blob content in 8 MB chunks without loading into memory."""
        from specstar.types import BlobStreamInfo

        safe_name = self._safe_name(file_id)
        # Race-tolerant stat across both layouts (sharded first, legacy flat).
        # An exists() guard would TOCTOU against a concurrent purge/migration
        # and leak a raw "[Errno 2] ..." path. See #352, #387.
        size = None
        found_path: Path | None = None
        for candidate in self._candidate_data_paths(safe_name):
            try:
                size = retry_on_estale(candidate.stat).st_size
                found_path = candidate
                break
            except FileNotFoundError:
                continue
        if found_path is None:
            raise FileNotFoundError(f"Blob {file_id} not found")
        content_type = UNSET
        meta_path = found_path.parent / f"{safe_name}.blobmeta"
        try:
            meta_bytes = retry_on_estale(meta_path.read_bytes)
        except FileNotFoundError:
            meta_bytes = None
        if meta_bytes is not None:
            blob_meta = self._blob_meta_decoder.decode(meta_bytes)
            content_type = blob_meta.content_type

        def _iterate(path: Path = found_path):
            # The open itself can ESTALE on NFS even when the parent dir
            # listing said the file is present. See #352.
            f = retry_on_estale(open, path, "rb")
            try:
                while True:
                    chunk = f.read(8 * 1024 * 1024)  # 8 MB
                    if not chunk:
                        break
                    yield chunk
            finally:
                f.close()

        return BlobStreamInfo(
            _iterate(), size=size, content_type=content_type, file_id=file_id
        )

    def migrate_layout(self, *, dry_run: bool = False) -> int:
        """Relocate pre-#387 flat blobs into the sharded tree.

        Walks the legacy flat layout (blob files written directly under
        ``root_path``) and moves each blob — together with its ``.blobmeta``
        sidecar — into ``_sh/<ab>/<cd>/``. Safe to run on a live store:
        each move is an atomic ``os.replace`` on the same filesystem and
        reads fall back to the flat layout until the move lands. Idempotent
        (a blob already present in the sharded tree is skipped) and
        re-runnable after an interruption.

        Returns the number of legacy entries relocated (or, when *dry_run*,
        that would be relocated): flat blobs plus any leftover flat session
        files. A blob's ``.blobmeta`` sidecar is moved with its blob and not
        counted separately.
        """
        moved = 0
        for child in iter_legacy_children(self.root_path):
            # Sharded data (``_sh/``) is already excluded by iter_legacy_children;
            # ``_sessions/`` and any other directory is not a flat blob.
            if child.is_dir():
                continue
            name = child.name
            if name.endswith(".blobmeta"):
                continue  # moved alongside its blob
            if name.endswith(".tmp") or ".tmp." in name:
                continue  # in-flight atomic write
            target_dir = sharded_dir(self.root_path, name)
            target = target_dir / name
            if target.exists():
                continue  # already migrated
            moved += 1
            if dry_run:
                continue
            target_dir.mkdir(parents=True, exist_ok=True)
            os.replace(child, target)
            legacy_meta = self.root_path / f"{name}.blobmeta"
            if legacy_meta.exists():
                os.replace(legacy_meta, target_dir / f"{name}.blobmeta")
        return moved + self._migrate_sessions(dry_run=dry_run)

    def _migrate_sessions(self, *, dry_run: bool = False) -> int:
        """Relocate pre-#387 flat session files into per-session sharded dirs.

        Legacy sessions stored each file flat under ``_sessions/`` as
        ``<upload_id>.<kind>`` (``.meta`` / ``.data`` / ``.lock`` /
        ``.part.N``). They are regrouped into ``_sessions/_sh/<ab>/<cd>/
        <upload_id>/<kind>`` so ``_sessions/`` stops accumulating entries.
        Returns the number of session files moved.
        """
        moved = 0
        for child in iter_legacy_children(self._sessions_dir):
            if child.is_dir():
                continue
            name = child.name
            if name.endswith(".tmp"):
                continue
            upload_id, _, kind = name.partition(".")
            if not kind:
                continue
            if kind in ("meta", "data", "lock"):
                leaf = kind
            elif kind.startswith("part."):
                leaf = kind  # "part.N"
            else:
                continue
            target_dir = self._session_dir(upload_id)
            target = target_dir / leaf
            if target.exists():
                continue
            moved += 1
            if dry_run:
                continue
            target_dir.mkdir(parents=True, exist_ok=True)
            os.replace(child, target)
        return moved

    # -- Upload session methods (disk-persisted) --------------------------

    def create_upload_session(
        self,
        *,
        key: str | None = None,
        content_type: str | UnsetType = UNSET,
        size: int | None = None,
        total_parts: int | None = None,
    ) -> BlobUploadSession:
        upload_id = uuid.uuid4().hex
        meta = _DiskSessionMeta(
            upload_id=upload_id,
            content_type=content_type,
            size=size,
            key=key,
            total_parts=total_parts,
        )
        self._save_session_meta(meta)
        return BlobUploadSession(
            upload_id=upload_id,
            file_id="",
            status="pending",
            upload_method="proxy",
            upload_url=f"/blobs/upload-sessions/{upload_id}/content",
            content_type=content_type,
            size=size,
            total_parts=total_parts,
        )

    def get_upload_session(self, upload_id: str) -> BlobUploadSession:
        meta = self._load_session_meta(upload_id)
        return BlobUploadSession(
            upload_id=meta.upload_id,
            file_id="",
            status=meta.status,  # ty:ignore[invalid-argument-type]
            upload_method="proxy",
            content_type=meta.content_type,
            size=meta.size,
            uploaded_size=meta.uploaded_size,
            total_parts=meta.total_parts,
            parts_received=list(meta.parts_received),
        )

    # -- Two-phase upload helpers -----------------------------------------

    def _flush_merged_parts(self, upload_id: str, meta: _DiskSessionMeta) -> None:
        """Merge consecutive ``.part.N`` files into ``.data`` from *next_expected*.

        Called inside the lock.  Each part file was fully written during
        the lock-free phase, so reading them here is safe and fast
        (typically already in OS page cache).

        Any flushed part number is also recorded in ``parts_received``
        because it may have been written by a different thread that
        hasn't entered the lock yet.
        """
        data_path = self._session_data_path(upload_id)
        while True:
            part_path = self._session_part_path(upload_id, meta.next_expected)
            if not part_path.exists():
                break
            with open(data_path, "ab") as f:
                f.write(part_path.read_bytes())
            part_path.unlink()
            # Record the part written by another thread's phase-1
            if meta.next_expected not in meta.parts_received:
                meta.parts_received.append(meta.next_expected)
            meta.next_expected += 1
        meta.parts_received.sort()

    def _compute_uploaded_size(self, upload_id: str) -> int:
        """Derive ``uploaded_size`` from actual disk state.

        = size of ``.data`` (merged bytes)
        + sum of remaining ``.part.*`` files (buffered bytes)

        Computing from disk eliminates incremental accounting bugs that
        are nearly impossible to get right under concurrency + retries.
        """
        data_path = self._session_data_path(upload_id)
        size = data_path.stat().st_size if data_path.exists() else 0
        for part_file in self._session_dir(upload_id).glob("part.*"):
            size += part_file.stat().st_size
        return size

    # -- Upload session methods (disk-persisted) --------------------------

    def upload_to_session(
        self, upload_id: str, data: bytes, *, part_number: int
    ) -> None:
        if part_number < 1:
            raise ValueError("part_number must be >= 1")

        # ---- Phase 1 (NO LOCK): write chunk to its own part file ----
        # Each part_number maps to a unique file path, so concurrent
        # uploads of *different* parts never interfere.  A retry of the
        # *same* part_number simply overwrites the file (idempotent).
        part_path = self._session_part_path(upload_id, part_number)
        part_path.parent.mkdir(parents=True, exist_ok=True)
        part_path.write_bytes(data)

        # ---- Phase 2 (SHORT LOCK): update meta + eager-merge --------
        with self._lock_session(upload_id):
            meta = self._load_session_meta(upload_id)
            if meta.status not in ("pending", "uploading"):
                part_path.unlink(missing_ok=True)
                raise ValueError(
                    f"Session status is '{meta.status}', "
                    f"expected 'pending' or 'uploading'"
                )

            # Idempotent: already merged past this part
            if part_number < meta.next_expected:
                part_path.unlink(missing_ok=True)
                return

            # Record the part
            if part_number not in meta.parts_received:
                meta.parts_received.append(part_number)
                meta.parts_received.sort()

            # Eager-merge consecutive parts starting from next_expected
            self._flush_merged_parts(upload_id, meta)

            # Derive uploaded_size from disk state (no incremental bugs)
            meta.uploaded_size = self._compute_uploaded_size(upload_id)

            meta.status = "uploading"
            self._save_session_meta(meta)

    def finalize_upload_session(self, upload_id: str) -> Binary:
        with self._lock_session(upload_id):
            meta = self._load_session_meta(upload_id)
            if meta.status not in ("uploaded", "uploading"):
                raise ValueError(
                    f"Session status is '{meta.status}', expected 'uploaded' or 'uploading'"
                )

            # Validate total_parts
            num_received = len(meta.parts_received)
            if meta.total_parts is not None and num_received != meta.total_parts:
                raise ValueError(
                    f"Expected {meta.total_parts} parts but received {num_received}"
                )

            # Check for remaining buffered part files (gaps)
            remaining_parts = sorted(
                int(p.name.split(".")[-1])
                for p in self._session_dir(upload_id).glob("part.*")
            )
            if remaining_parts:
                raise ValueError(
                    f"Cannot finalize: parts still buffered (missing earlier parts). "
                    f"Buffered part numbers: {remaining_parts}"
                )

            data_path = self._session_data_path(upload_id)
            if not data_path.exists():
                raise FileNotFoundError(
                    f"Uploaded data for session {upload_id} not found on disk"
                )

            # Determine content type from file header (constant memory)
            final_content_type = meta.content_type
            if not final_content_type:
                with open(data_path, "rb") as f:
                    header = f.read(8192)
                final_content_type = self.guess_content_type(header, UNSET)

            size = data_path.stat().st_size

            # Determine file_id
            if meta.key is not None:
                file_id = meta.key
            else:
                # Streaming hash — constant memory regardless of file size
                hasher = xxh3_128()
                with open(data_path, "rb") as f:
                    while True:
                        chunk = f.read(8 * 1024 * 1024)  # 8 MB chunks
                        if not chunk:
                            break
                        hasher.update(chunk)
                file_id = hasher.hexdigest()

            safe_name = self._safe_name(file_id)
            blob_dir = sharded_dir(self.root_path, safe_name)
            final_path = blob_dir / safe_name

            # Move data to its final (sharded) blob location — zero-copy on the
            # same filesystem. See #387.
            if meta.key is not None or not self._blob_exists(safe_name):
                blob_dir.mkdir(parents=True, exist_ok=True)
                data_path.rename(final_path)
                # Write metadata sidecar alongside the blob.
                blob_meta = _DiskBlobMeta(
                    file_id=file_id,
                    size=size,
                    content_type=final_content_type,
                )
                (blob_dir / f"{safe_name}.blobmeta").write_bytes(
                    self.encoder.encode(blob_meta)
                )
            else:
                # Content-addressed blob already exists (either layout) — discard
                # the duplicate; the existing blob + sidecar remain authoritative.
                data_path.unlink()

            meta.status = "finalized"
            self._save_session_meta(meta)
            return Binary(
                file_id=file_id,
                size=size,
                content_type=final_content_type,
            )

    def abort_upload_session(self, upload_id: str) -> None:
        with self._lock_session(upload_id):
            meta = self._load_session_meta(upload_id)
            if meta.status == "finalized":
                raise ValueError("Cannot abort a finalized session")
            meta.status = "aborted"
            self._save_session_meta(meta)
            # Clean up the transient bulk (data + part files). The tiny ``meta``
            # (now ``aborted``) and ``lock`` are retained: ``meta`` is the
            # cross-instance status SSOT and unlinking a live ``flock`` anchor
            # races concurrent lockers. They live in the per-session sharded
            # directory, so no single directory bombs. See #387.
            self._session_data_path(upload_id).unlink(missing_ok=True)
            for part_file in self._session_dir(upload_id).glob("part.*"):
                part_file.unlink(missing_ok=True)
