from collections.abc import Generator
from pathlib import Path
from typing import TypeVar

from autocrud.v03.resource_manager.basic import (
    Encoding,
    IResourceStore,
    MsgspecSerializer,
    Resource,
)

T = TypeVar("T")


class MemoryResourceStore(IResourceStore[T]):
    def __init__(self, resource_type: type[T], encoding: Encoding = Encoding.json):
        self._store: dict[str, dict[str, bytes]] = {}
        self._serializer = MsgspecSerializer(
            encoding=encoding, resource_type=Resource[resource_type]
        )

    def list_resources(self) -> Generator[str]:
        yield from self._store.keys()

    def list_revisions(self, resource_id: str) -> Generator[str]:
        yield from self._store[resource_id].keys()

    def exists(self, resource_id: str, revision_id: str) -> bool:
        return resource_id in self._store and revision_id in self._store[resource_id]

    def get(self, resource_id: str, revision_id: str) -> Resource[T]:
        return self._serializer.decode(self._store[resource_id][revision_id])

    def save(self, data: Resource[T]) -> None:
        resource_id = data.info.resource_id
        revision_id = data.info.revision_id
        if resource_id not in self._store:
            self._store[resource_id] = {}
        self._store[resource_id][revision_id] = self._serializer.encode(data)


class DiskResourceStore(IResourceStore[T]):
    def __init__(
        self,
        resource_type: type[T],
        *,
        encoding: Encoding = Encoding.json,
        rootdir: Path | str,
    ):
        self._serializer = MsgspecSerializer(
            encoding=encoding, resource_type=Resource[resource_type]
        )
        self._rootdir = Path(rootdir)
        self._rootdir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, resource_id: str, revision_id: str) -> Path:
        return self._rootdir / resource_id / f"{revision_id}.data"

    def list_resources(self) -> Generator[str]:
        for resource_dir in self._rootdir.iterdir():
            if resource_dir.is_dir():
                yield resource_dir.name

    def list_revisions(self, resource_id: str) -> Generator[str]:
        resource_path = self._rootdir / resource_id
        for file in resource_path.glob("*.data"):
            yield file.stem

    def exists(self, resource_id: str, revision_id: str) -> bool:
        path = self._get_path(resource_id, revision_id)
        return path.exists()

    def get(self, resource_id: str, revision_id: str) -> Resource[T]:
        path = self._get_path(resource_id, revision_id)
        with path.open("rb") as f:
            return self._serializer.decode(f.read())

    def save(self, data: Resource[T]) -> None:
        resource_id = data.info.resource_id
        revision_id = data.info.revision_id
        resource_path = self._rootdir / resource_id
        resource_path.mkdir(parents=True, exist_ok=True)
        path = self._get_path(resource_id, revision_id)
        with path.open("wb") as f:
            f.write(self._serializer.encode(data))
