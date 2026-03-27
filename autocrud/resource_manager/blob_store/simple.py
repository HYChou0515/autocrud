import fcntl
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import msgspec
from msgspec import UNSET, Struct, UnsetType
from xxhash import xxh3_128_hexdigest

from autocrud.resource_manager.basic import IBlobStore
from autocrud.types import Binary, BlobUploadSession


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
        return stored_binary

    def get(self, file_id: str) -> Binary:
        if file_id not in self._store:
            raise FileNotFoundError(f"Blob {file_id} not found")
        return self._store[file_id]

    def exists(self, file_id: str) -> bool:
        return file_id in self._store

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
            status=state.status,
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
        if not path.exists():
            raise FileNotFoundError(f"Upload session {upload_id} not found")
        return self._session_meta_decoder.decode(path.read_bytes())

    # -- Blob put / get / exists ------------------------------------------

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
            stored_binary = Binary(
                file_id=file_id,
                size=len(data),
                data=data,
                content_type=final_content_type,
            )
            encoded = self.encoder.encode(stored_binary)
            with open(file_path, "wb") as f:
                f.write(encoded)
        return Binary(
            file_id=file_id,
            size=len(data),
            data=data,
            content_type=final_content_type,
        )

    def get(self, file_id: str) -> Binary:
        file_path = self.root_path / file_id
        if not file_path.exists():
            raise FileNotFoundError(f"Blob {file_id} not found")
        with open(file_path, "rb") as f:
            encoded = f.read()
            return self.decoder.decode(encoded)

    def exists(self, file_id: str) -> bool:
        return (self.root_path / file_id).exists()

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
            status=meta.status,
            upload_method="proxy",
            content_type=meta.content_type,
            size=meta.size,
            uploaded_size=meta.uploaded_size,
            total_parts=meta.total_parts,
            parts_received=list(meta.parts_received),
        )

    def upload_to_session(
        self, upload_id: str, data: bytes, *, part_number: int
    ) -> None:
        if part_number < 1:
            raise ValueError("part_number must be >= 1")
        with self._lock_session(upload_id):
            meta = self._load_session_meta(upload_id)
            if meta.status not in ("pending", "uploading"):
                raise ValueError(
                    f"Session status is '{meta.status}', expected 'pending' or 'uploading'"
                )

            # Idempotent: if already merged (part_number < next_expected), ignore
            if part_number < meta.next_expected:
                return

            data_path = self._session_data_path(upload_id)

            if part_number == meta.next_expected:
                # In-order: append directly to .data file
                with open(data_path, "ab") as f:
                    f.write(data)
                meta.uploaded_size += len(data)
                if part_number not in meta.parts_received:
                    meta.parts_received.append(part_number)
                    meta.parts_received.sort()
                meta.next_expected += 1

                # Flush consecutive buffered parts
                while True:
                    part_path = self._session_part_path(upload_id, meta.next_expected)
                    if not part_path.exists():
                        break
                    buffered_data = part_path.read_bytes()
                    with open(data_path, "ab") as f:
                        f.write(buffered_data)
                    part_path.unlink()
                    meta.next_expected += 1
            else:
                # Out-of-order: write to part file
                part_path = self._session_part_path(upload_id, part_number)
                if part_path.exists():
                    # Retry: adjust uploaded_size
                    meta.uploaded_size -= part_path.stat().st_size
                part_path.write_bytes(data)
                meta.uploaded_size += len(data)
                if part_number not in meta.parts_received:
                    meta.parts_received.append(part_number)
                    meta.parts_received.sort()

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

            # Read the uploaded data from disk
            data_path = self._session_data_path(upload_id)
            if not data_path.exists():
                raise FileNotFoundError(
                    f"Uploaded data for session {upload_id} not found on disk"
                )
            data = data_path.read_bytes()
            stored = self.put(data, key=meta.key, content_type=meta.content_type)
            # Update session status and clean up data file
            meta.status = "finalized"
            self._save_session_meta(meta)
            data_path.unlink(missing_ok=True)
            return Binary(
                file_id=stored.file_id,
                size=stored.size,
                content_type=stored.content_type,
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
