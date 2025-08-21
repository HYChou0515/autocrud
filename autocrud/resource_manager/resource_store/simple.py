from collections.abc import Generator
from pathlib import Path
from typing import TypeVar

from autocrud.resource_manager.basic import (
    Encoding,
    IMigration,
    IResourceStore,
    MsgspecSerializer,
    Resource,
    RevisionInfo,
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
        migration: IMigration|None=None
    ):
        self._data_serializer = MsgspecSerializer(
            encoding=encoding, resource_type=resource_type
        )
        self._info_serializer = MsgspecSerializer(
            encoding=encoding, resource_type=RevisionInfo
        )
        self._rootdir = Path(rootdir)
        self._rootdir.mkdir(parents=True, exist_ok=True)
        self.migration = migration

    def _get_data_path(self, resource_id: str, revision_id: str) -> Path:
        return self._rootdir / resource_id / f"{revision_id}.data"

    def _get_info_path(self, resource_id: str, revision_id: str) -> Path:
        return self._rootdir / resource_id / f"{revision_id}.info"

    def list_resources(self) -> Generator[str]:
        for resource_dir in self._rootdir.iterdir():
            if resource_dir.is_dir():
                yield resource_dir.name

    def list_revisions(self, resource_id: str) -> Generator[str]:
        resource_path = self._rootdir / resource_id
        for file in resource_path.glob("*.info"):
            yield file.stem

    def exists(self, resource_id: str, revision_id: str) -> bool:
        path = self._get_info_path(resource_id, revision_id)
        return path.exists()

    def get(self, resource_id: str, revision_id: str) -> Resource[T]:
        info_path = self._get_info_path(resource_id, revision_id)
        with info_path.open("rb") as f:
            info = self._info_serializer.decode(f.read())
        data_path = self._get_data_path(resource_id, revision_id)
        with data_path.open("rb") as f:
            try:
                data = self._data_serializer.decode(f.read())
            except Exception:
                if self.migration is None:
                    raise
                f.seek(0)
                data = self.migration.migrate(f, info.schema_version)
                info.schema_version = self.migration.schema_version
        return Resource(
            info=info,
            data=data,
        )

    def save(self, data: Resource[T]) -> None:
        resource_id = data.info.resource_id
        revision_id = data.info.revision_id
        resource_path = self._rootdir / resource_id
        resource_path.mkdir(parents=True, exist_ok=True)
        path = self._get_data_path(resource_id, revision_id)
        with path.open("wb") as f:
            f.write(self._data_serializer.encode(data.data))
        path = self._get_info_path(resource_id, revision_id)
        with path.open("wb") as f:
            f.write(self._info_serializer.encode(data.info))
