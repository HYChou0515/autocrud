from pathlib import Path
import msgspec
from msgspec import UNSET, UnsetType
from autocrud.resource_manager.basic import IBlobStore
from autocrud.types import Binary
from xxhash import xxh3_128_hexdigest


def _fallback_content_type_guesser(data: bytes) -> UnsetType:
    # Fallback: use generic binary type
    return UNSET


def get_content_type_guesser():
    try:
        import magic

        def guess_content_type(data: bytes) -> str:
            return magic.from_buffer(data, mime=True)

        return guess_content_type
    except ImportError:
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


class MemoryBlobStore(BasicBlobStore):
    def __init__(self):
        self._store = {}

    def put(self, data: bytes, *, content_type: str | UnsetType = UNSET) -> Binary:
        file_id = xxh3_128_hexdigest(data)

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


class DiskBlobStore(BasicBlobStore):
    def __init__(self, root_path: str | Path):
        self.root_path = Path(root_path)
        self.root_path.mkdir(parents=True, exist_ok=True)
        self.encoder = msgspec.msgpack.Encoder()
        self.decoder = msgspec.msgpack.Decoder(Binary)

    def put(self, data: bytes, *, content_type: str | UnsetType = UNSET) -> Binary:
        file_id = xxh3_128_hexdigest(data)

        file_path = self.root_path / file_id
        final_content_type = self.guess_content_type(data, content_type)
        if not file_path.exists():
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
