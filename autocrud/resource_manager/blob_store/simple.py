from pathlib import Path
import msgspec
from autocrud.resource_manager.basic import IBlobStore
from autocrud.types import Binary
from xxhash import xxh3_128_hexdigest


class MemoryBlobStore(IBlobStore):
    def __init__(self):
        self._store = {}

    def put(self, data: bytes) -> str:
        file_id = xxh3_128_hexdigest(data)

        # Create Binary object with metadata
        stored_binary = Binary(file_id=file_id, size=len(data), data=data)

        self._store[file_id] = stored_binary
        return file_id

    def get(self, file_id: str) -> Binary:
        if file_id not in self._store:
            raise FileNotFoundError(f"Blob {file_id} not found")
        return self._store[file_id]

    def exists(self, file_id: str) -> bool:
        return file_id in self._store


class DiskBlobStore(IBlobStore):
    def __init__(self, root_path: str | Path):
        self.root_path = Path(root_path)
        self.root_path.mkdir(parents=True, exist_ok=True)
        self.encoder = msgspec.msgpack.Encoder()
        self.decoder = msgspec.msgpack.Decoder(Binary)

    def put(self, data: bytes) -> str:
        file_id = xxh3_128_hexdigest(data)

        file_path = self.root_path / file_id
        if not file_path.exists():
            stored_binary = Binary(file_id=file_id, size=len(data), data=data)
            encoded = self.encoder.encode(stored_binary)
            with open(file_path, "wb") as f:
                f.write(encoded)
        return file_id

    def get(self, file_id: str) -> Binary:
        file_path = self.root_path / file_id
        if not file_path.exists():
            raise FileNotFoundError(f"Blob {file_id} not found")
        with open(file_path, "rb") as f:
            encoded = f.read()
            return self.decoder.decode(encoded)

    def exists(self, file_id: str) -> bool:
        return (self.root_path / file_id).exists()
