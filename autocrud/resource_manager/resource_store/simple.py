from contextlib import contextmanager
import io
from collections.abc import Generator
from pathlib import Path
from typing import IO

from autocrud.resource_manager.basic import (
    Encoding,
    IResourceStore,
    MsgspecSerializer,
)
from autocrud.types import RevisionInfo

UID = str
SchemaVersion = str
ResourceID = str
RevisionID = str
DataBytes = bytes
InfoBytes = bytes
DataIO = IO[bytes]

class MemoryResourceStore(IResourceStore):
    def __init__(
        self,
        encoding: Encoding = Encoding.json,
    ):
        self._raw_data_store: dict[UID, DataBytes] = {}
        self._raw_info_store: dict[UID, InfoBytes] = {}
        self._store: dict[ResourceID, dict[RevisionID, dict[SchemaVersion | None, UID]]] = {}
        self._info_serializer = MsgspecSerializer(
            encoding=encoding,
            resource_type=RevisionInfo,
        )

    def list_resources(self) -> Generator[ResourceID]:
        yield from self._store.keys()

    def list_revisions(self, resource_id: ResourceID) -> Generator[RevisionID]:
        yield from self._store[resource_id].keys()

    def exists(self, resource_id: ResourceID, revision_id: RevisionID, schema_version: str | None) -> bool:
        return (
            resource_id in self._store
            and revision_id in self._store[resource_id]
            and schema_version in self._store[resource_id][revision_id]
        )

    @contextmanager
    def get_data_bytes(
        self, resource_id: ResourceID, revision_id: RevisionID, schema_version: str | None
    ) -> Generator[DataIO]:
        uid = self._store[resource_id][revision_id][schema_version]
        yield io.BytesIO(self._raw_data_store[uid])

    def get_revision_info(self, resource_id: ResourceID, revision_id: RevisionID, schema_version: str | None) -> RevisionInfo:
        uid = self._store[resource_id][revision_id][schema_version]
        return self._info_serializer.decode(self._raw_info_store[uid])

    def save(self, info: RevisionInfo, data: DataIO) -> None:
        self._store.setdefault(info.resource_id, {}).setdefault(info.revision_id, {})[info.schema_version] = info.uid
        self._raw_data_store[info.uid] = data.read()
        self._raw_info_store[info.uid] = self._info_serializer.encode(info)


class DiskResourceStore(IResourceStore):
    def __init__(
        self,
        *,
        encoding: Encoding = Encoding.json,
        rootdir: Path | str,
    ):
        self._info_serializer = MsgspecSerializer(
            encoding=encoding,
            resource_type=RevisionInfo,
        )
        self._rootdir = Path(rootdir)
        self._rootdir.mkdir(parents=True, exist_ok=True)

    def _get_data_path(self, resource_id: ResourceID, revision_id: RevisionID) -> Path:
        return self._rootdir / resource_id / f"{revision_id}.data"

    def _get_info_path(self, resource_id: ResourceID, revision_id: RevisionID) -> Path:
        return self._rootdir / resource_id / f"{revision_id}.info"

    def list_resources(self) -> Generator[ResourceID]:
        for resource_dir in self._rootdir.iterdir():
            if resource_dir.is_dir():
                yield resource_dir.name

    def list_revisions(self, resource_id: ResourceID) -> Generator[RevisionID]:
        resource_path = self._rootdir / resource_id
        for file in resource_path.glob("*.info"):
            yield file.stem

    def exists(self, resource_id: ResourceID, revision_id: RevisionID) -> bool:
        path = self._get_info_path(resource_id, revision_id)
        return path.exists()

    @contextmanager
    def get_data_bytes(
        self, resource_id: ResourceID, revision_id: RevisionID
    ) -> Generator[DataIO]:
        path = self._get_data_path(resource_id, revision_id)
        with path.open("rb") as f:
            yield f

    def get_revision_info(self, resource_id: ResourceID, revision_id: RevisionID) -> RevisionInfo:
        info_path = self._get_info_path(resource_id, revision_id)
        with info_path.open("rb") as f:
            return self._info_serializer.decode(f.read())

    def save(self, info: RevisionInfo, data: DataIO) -> None:
        self._save_data_bytes(info.resource_id, info.revision_id, data)
        self._save_revision_info(info)

    def _save_data_bytes(
        self, resource_id: ResourceID, revision_id: RevisionID, data: DataIO
    ) -> None:
        resource_path = self._rootdir / resource_id
        resource_path.mkdir(parents=True, exist_ok=True)
        path = self._get_data_path(resource_id, revision_id)
        with path.open("wb") as out_f:
            out_f.write(data.read())

    def _save_revision_info(self, info: RevisionInfo) -> None:
        resource_path = self._rootdir / info.resource_id
        resource_path.mkdir(parents=True, exist_ok=True)
        path = self._get_info_path(info.resource_id, info.revision_id)
        with path.open("wb") as f:
            f.write(self._info_serializer.encode(info))
