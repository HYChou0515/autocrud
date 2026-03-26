import uuid
from dataclasses import dataclass
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
    """In-memory state for an upload session."""

    upload_id: str
    status: str = "pending"  # pending | uploaded | finalized | aborted
    content_type: str | UnsetType = UNSET
    size: int | None = None
    key: str | None = None
    data: bytes | None = None  # buffered bytes (None until upload_to_session)


class MemoryBlobStore(BasicBlobStore):
    """In-memory blob store — data is lost when the process exits."""

    def __init__(self):
        self._store: dict[str, Binary] = {}
        self._sessions: dict[str, _UploadSessionState] = {}

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

    # -- Upload session methods -------------------------------------------

    def create_upload_session(
        self,
        *,
        key: str | None = None,
        content_type: str | UnsetType = UNSET,
        size: int | None = None,
    ) -> BlobUploadSession:
        upload_id = uuid.uuid4().hex
        state = _UploadSessionState(
            upload_id=upload_id,
            content_type=content_type,
            size=size,
            key=key,
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
        )

    def upload_to_session(self, upload_id: str, data: bytes) -> None:
        state = self._sessions.get(upload_id)
        if state is None:
            raise FileNotFoundError(f"Upload session {upload_id} not found")
        if state.status != "pending":
            raise ValueError(f"Session status is '{state.status}', expected 'pending'")
        state.data = data
        state.size = len(data)
        state.status = "uploaded"

    def finalize_upload_session(self, upload_id: str) -> Binary:
        state = self._sessions.get(upload_id)
        if state is None:
            raise FileNotFoundError(f"Upload session {upload_id} not found")
        if state.status != "uploaded":
            raise ValueError(f"Session status is '{state.status}', expected 'uploaded'")
        stored = self.put(
            state.data,  # type: ignore[arg-type]
            key=state.key,
            content_type=state.content_type,
        )
        state.status = "finalized"
        state.data = None  # free memory
        return Binary(
            file_id=stored.file_id,
            size=stored.size,
            content_type=stored.content_type,
        )

    def abort_upload_session(self, upload_id: str) -> None:
        state = self._sessions.get(upload_id)
        if state is None:
            raise FileNotFoundError(f"Upload session {upload_id} not found")
        if state.status == "finalized":
            raise ValueError("Cannot abort a finalized session")
        state.data = None
        state.status = "aborted"


class _DiskSessionMeta(Struct, kw_only=True):
    """Serializable session metadata persisted alongside uploaded data.

    Unlike ``_UploadSessionState`` (which is in-memory only), this struct
    is msgpack-encoded to disk so that **any** ``DiskBlobStore`` instance
    sharing the same ``root_path`` (e.g. via a Kubernetes PVC) can read
    and mutate the session state — essential for HPA / multi-pod setups.
    """

    upload_id: str
    status: str = "pending"  # pending | uploaded | finalized | aborted
    content_type: str | UnsetType = UNSET
    size: int | None = None
    key: str | None = None


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
        """Path for the raw uploaded bytes."""
        return self._sessions_dir / f"{upload_id}.data"

    def _save_session_meta(self, meta: _DiskSessionMeta) -> None:
        """Persist session metadata to disk."""
        encoded = self._session_meta_encoder.encode(meta)
        self._session_meta_path(meta.upload_id).write_bytes(encoded)

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
    ) -> BlobUploadSession:
        upload_id = uuid.uuid4().hex
        meta = _DiskSessionMeta(
            upload_id=upload_id,
            content_type=content_type,
            size=size,
            key=key,
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
        )

    def upload_to_session(self, upload_id: str, data: bytes) -> None:
        meta = self._load_session_meta(upload_id)
        if meta.status != "pending":
            raise ValueError(f"Session status is '{meta.status}', expected 'pending'")
        # Write data to disk first, then update metadata atomically
        self._session_data_path(upload_id).write_bytes(data)
        meta.size = len(data)
        meta.status = "uploaded"
        self._save_session_meta(meta)

    def finalize_upload_session(self, upload_id: str) -> Binary:
        meta = self._load_session_meta(upload_id)
        if meta.status != "uploaded":
            raise ValueError(f"Session status is '{meta.status}', expected 'uploaded'")
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
        meta = self._load_session_meta(upload_id)
        if meta.status == "finalized":
            raise ValueError("Cannot abort a finalized session")
        meta.status = "aborted"
        self._save_session_meta(meta)
        # Clean up any uploaded data
        self._session_data_path(upload_id).unlink(missing_ok=True)
