from pathlib import Path
from autocrud.resource_manager.basic import IBlobStore
from xxhash import xxh3_128_hexdigest


class MemoryBlobStore(IBlobStore):
    def __init__(self):
        self._store = {}

    def put(self, data: bytes) -> str:
        file_id = xxh3_128_hexdigest(data)
        self._store[file_id] = data
        return file_id

    def get(self, file_id: str) -> bytes:
        if file_id not in self._store:
            raise FileNotFoundError(f"Blob {file_id} not found")
        return self._store[file_id]

    def exists(self, file_id: str) -> bool:
        return file_id in self._store


class DiskBlobStore(IBlobStore):
    def __init__(self, root_path: str | Path):
        self.root_path = Path(root_path)
        self.root_path.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes) -> str:
        file_id = xxh3_128_hexdigest(data)
        file_path = self.root_path / file_id
        if not file_path.exists():
            with open(file_path, "wb") as f:
                f.write(data)
        return file_id

    def get(self, file_id: str) -> bytes:
        file_path = self.root_path / file_id
        if not file_path.exists():
            raise FileNotFoundError(f"Blob {file_id} not found")
        with open(file_path, "rb") as f:
            return f.read()

    def exists(self, file_id: str) -> bool:
        return (self.root_path / file_id).exists()
