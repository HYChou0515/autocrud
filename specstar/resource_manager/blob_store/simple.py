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

    Upload sessions are persisted to disk under ``root_path/_sessions/``
    so that multiple processes (or Kubernetes pods sharing a PVC) can
    cooperate on the same upload lifecycle.
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

    def _session_meta_path(self, upload_id: str) -> Path:
        """Path for the msgpack-encoded session metadata file."""
        return self._sessions_dir / f"{upload_id}.meta"

    def _session_data_path(self, upload_id: str) -> Path:
        """Path for the raw uploaded bytes (merged/final data)."""
        return self._sessions_dir / f"{upload_id}.data"

    def _session_part_path(self, upload_id: str, part_number: int) -> Path:
        """Path for an out-of-order part file."""
        return self._sessions_dir / f"{upload_id}.part.{part_number}"

    def _session_lock_path(self, upload_id: str) -> Path:
        """Path for the per-session POSIX lock file."""
        return self._sessions_dir / f"{upload_id}.lock"

    @contextmanager
    def _lock_session(self, upload_id: str):
        """Acquire an exclusive POSIX ``flock`` for the given session.

        Serialises all read-modify-write cycles on the session metadata
        and data files so that concurrent workers / pods do not corrupt
        them.  The lock is automatically released when the context exits
        (including on exceptions or process crashes).
        """
        lock_path = self._session_lock_path(upload_id)
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
        tmp = path.with_suffix(".meta.tmp")
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

    def _blob_meta_path(self, safe_name: str) -> Path:
        """Path for the ``.blobmeta`` sidecar of a stored blob."""
        return self.root_path / f"{safe_name}.blobmeta"

    def put(
        self,
        data: bytes,
        *,
        key: str | None = None,
        content_type: str | UnsetType = UNSET,
    ) -> Binary:
        file_id = key if key is not None else xxh3_128_hexdigest(data)
        # Make filename safe for filesystem
        safe_name = file_id.replace("/", "_").replace("..", "_")

        file_path = self.root_path / safe_name
        final_content_type = self.guess_content_type(data, content_type)
        # When key is caller-specified, always overwrite; for hash keys skip if exists
        if key is not None or not file_path.exists():
            # Atomic write: dump bytes into a uniquely-named tmp file in the
            # same directory, then ``os.replace`` it onto the final path. A
            # concurrent reader either sees the previous complete file or the
            # new complete file — never a truncated mid-write prefix.
            # See #352 (local-FS half).
            blob_meta = _DiskBlobMeta(
                file_id=file_id,
                size=len(data),
                content_type=final_content_type,
            )
            meta_path = self._blob_meta_path(safe_name)
            _atomic_write_bytes(file_path, data)
            _atomic_write_bytes(meta_path, self.encoder.encode(blob_meta))
        return Binary(
            file_id=file_id,
            size=len(data),
            data=data,
            content_type=final_content_type,
        )

    @property
    def _quarantine_dir(self) -> Path:
        return self.root_path / "_quarantine"

    def _read_binary_from(self, base: Path, safe_name: str) -> Binary | None:
        """Read a blob (data + sidecar) from *base*, or ``None`` if absent.

        Skips the ``exists()`` guard: it would race a concurrent purge and
        leak a raw "[Errno 2] ..." path. Translate ENOENT to ``None``. See #352.
        """
        file_path = base / safe_name
        try:
            data = retry_on_estale(file_path.read_bytes)
        except FileNotFoundError:
            return None
        meta_path = base / f"{safe_name}.blobmeta"
        try:
            meta_bytes = retry_on_estale(meta_path.read_bytes)
        except FileNotFoundError:
            # Legacy fallback: pre-sidecar format had the Binary msgpack-encoded
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
        safe_name = file_id.replace("/", "_").replace("..", "_")
        # Active first (zero overhead on hit); on miss fall through to the
        # quarantine area so a transiently-quarantined blob is never lost (#370).
        for base in (self.root_path, self._quarantine_dir):
            result = self._read_binary_from(base, safe_name)
            if result is not None:
                return result
        raise FileNotFoundError(f"Blob {file_id} not found")

    def exists(self, file_id: str) -> bool:
        safe_name = file_id.replace("/", "_").replace("..", "_")
        return (self.root_path / safe_name).exists() or (
            self._quarantine_dir / safe_name
        ).exists()

    def delete(self, file_id: str) -> None:
        """Idempotently remove a blob (active or quarantined) and its sidecars."""
        safe_name = file_id.replace("/", "_").replace("..", "_")
        for base in (self.root_path, self._quarantine_dir):
            (base / safe_name).unlink(missing_ok=True)
            (base / f"{safe_name}.blobmeta").unlink(missing_ok=True)
        self._refcount_path(safe_name).unlink(missing_ok=True)
        self._clear_candidate(file_id)

    def quarantine(self, file_id: str, *, now: dt.datetime) -> None:
        """Move an active blob into quarantine, stamping ``now`` as its entry
        time (recorded as the quarantined file's mtime). No-op if not active."""
        safe_name = file_id.replace("/", "_").replace("..", "_")
        src = self.root_path / safe_name
        if not src.exists():
            return
        self._quarantine_dir.mkdir(exist_ok=True)
        dst = self._quarantine_dir / safe_name
        os.replace(src, dst)
        src_meta = self._blob_meta_path(safe_name)
        if src_meta.exists():
            os.replace(src_meta, self._quarantine_dir / f"{safe_name}.blobmeta")
        ts = now.timestamp()
        os.utime(dst, (ts, ts))
        self._clear_candidate(file_id)

    def restore_from_quarantine(self, file_id: str) -> None:
        """Move a blob back from quarantine to the active area. No-op if absent."""
        safe_name = file_id.replace("/", "_").replace("..", "_")
        src = self._quarantine_dir / safe_name
        if not src.exists():
            return
        os.replace(src, self.root_path / safe_name)
        src_meta = self._quarantine_dir / f"{safe_name}.blobmeta"
        if src_meta.exists():
            os.replace(src_meta, self._blob_meta_path(safe_name))

    def _refcount_path(self, safe_name: str) -> Path:
        return self.root_path / f"{safe_name}.refcount"

    def _read_refcount(self, safe_name: str) -> int:
        try:
            return int(self._refcount_path(safe_name).read_text())
        except (FileNotFoundError, ValueError):
            return 0

    def incref(self, file_id: str) -> int:
        safe_name = file_id.replace("/", "_").replace("..", "_")
        n = self._read_refcount(safe_name) + 1
        self._refcount_path(safe_name).write_text(str(n))
        self._note_count(file_id, n)
        return n

    def decref(self, file_id: str) -> int:
        safe_name = file_id.replace("/", "_").replace("..", "_")
        n = max(0, self._read_refcount(safe_name) - 1)
        self._refcount_path(safe_name).write_text(str(n))
        self._note_count(file_id, n)
        return n

    def get_mtime(self, file_id: str) -> dt.datetime | None:
        safe_name = file_id.replace("/", "_").replace("..", "_")
        try:
            ts = (self.root_path / safe_name).stat().st_mtime
        except FileNotFoundError:
            return None
        return dt.datetime.fromtimestamp(ts, dt.timezone.utc)

    def touch(self, file_id: str, *, now: dt.datetime | None = None) -> None:
        safe_name = file_id.replace("/", "_").replace("..", "_")
        path = self.root_path / safe_name
        if not path.exists():
            return
        ts = (now or dt.datetime.now(dt.timezone.utc)).timestamp()
        os.utime(path, (ts, ts))

    def iter_active(self):
        for entry in self.root_path.iterdir():
            if not entry.is_file():
                continue  # skips _sessions/ and _quarantine/ subdirs
            name = entry.name
            if (
                name.endswith(".blobmeta")
                or name.endswith(".refcount")
                or ".tmp." in name
            ):
                continue
            meta_file = self._blob_meta_path(name)
            if meta_file.exists():
                meta = self._blob_meta_decoder.decode(meta_file.read_bytes())
                yield meta.file_id
            else:
                yield name

    def iter_quarantined(self, *, entered_before: dt.datetime):
        """Yield file_ids quarantined strictly before ``entered_before``."""
        qdir = self._quarantine_dir
        if not qdir.exists():
            return
        cutoff = entered_before.timestamp()
        for data_file in qdir.iterdir():
            if data_file.name.endswith(".blobmeta") or not data_file.is_file():
                continue
            try:
                mtime = data_file.stat().st_mtime
            except FileNotFoundError:
                continue
            if mtime >= cutoff:
                continue
            meta_file = qdir / f"{data_file.name}.blobmeta"
            if meta_file.exists():
                meta = self._blob_meta_decoder.decode(meta_file.read_bytes())
                yield meta.file_id
            else:
                yield data_file.name

    def get_stream(self, file_id: str):
        """Stream blob content in 8 MB chunks without loading into memory."""
        from specstar.types import BlobStreamInfo

        safe_name = file_id.replace("/", "_").replace("..", "_")
        file_path = self.root_path / safe_name
        # Race-tolerant stat: an ``exists()`` guard here would TOCTOU against
        # a concurrent purge and leak a raw "[Errno 2] ..." path to the
        # caller. Catch ENOENT from stat() and translate to the controlled
        # surface. See #352.
        try:
            size = retry_on_estale(file_path.stat).st_size
        except FileNotFoundError:
            raise FileNotFoundError(f"Blob {file_id} not found") from None
        content_type = UNSET
        meta_path = self._blob_meta_path(safe_name)
        try:
            meta_bytes = retry_on_estale(meta_path.read_bytes)
        except FileNotFoundError:
            meta_bytes = None
        if meta_bytes is not None:
            blob_meta = self._blob_meta_decoder.decode(meta_bytes)
            content_type = blob_meta.content_type

        def _iterate():
            # The open itself can ESTALE on NFS even when the parent dir
            # listing said the file is present. See #352.
            f = retry_on_estale(open, file_path, "rb")
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
        for part_file in self._sessions_dir.glob(f"{upload_id}.part.*"):
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
                for p in self._sessions_dir.glob(f"{upload_id}.part.*")
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

            safe_name = file_id.replace("/", "_").replace("..", "_")
            final_path = self.root_path / safe_name

            # Move data to final blob location (zero-copy on same filesystem)
            if meta.key is not None or not final_path.exists():
                data_path.rename(final_path)
            else:
                # Content-addressed blob already exists — discard duplicate
                data_path.unlink()

            # Write metadata sidecar
            blob_meta = _DiskBlobMeta(
                file_id=file_id,
                size=size,
                content_type=final_content_type,
            )
            self._blob_meta_path(safe_name).write_bytes(self.encoder.encode(blob_meta))

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
            # Clean up data file and all part files
            self._session_data_path(upload_id).unlink(missing_ok=True)
            for part_file in self._sessions_dir.glob(f"{upload_id}.part.*"):
                part_file.unlink(missing_ok=True)
