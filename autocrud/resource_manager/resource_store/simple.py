from contextlib import contextmanager
import io
from collections.abc import Generator
from pathlib import Path
from typing import IO, TypeVar

from autocrud.resource_manager.basic import (
    Encoding,
    IResourceStore,
    MsgspecSerializer,
)
from autocrud.types import RevisionInfo

T = TypeVar("T")


class MemoryResourceStore(IResourceStore[T]):
    def __init__(
        self,
        encoding: Encoding = Encoding.json,
    ):
        self._data_store: dict[str, dict[str, bytes]] = {}
        self._info_store: dict[str, dict[str, bytes]] = {}
        self._info_serializer = MsgspecSerializer(
            encoding=encoding,
            resource_type=RevisionInfo,
        )

    def list_resources(self) -> Generator[str]:
        yield from self._info_store.keys()

    def list_revisions(self, resource_id: str) -> Generator[str]:
        yield from self._info_store[resource_id].keys()

    def exists(self, resource_id: str, revision_id: str) -> bool:
        return (
            resource_id in self._info_store
            and revision_id in self._info_store[resource_id]
        )

    @contextmanager
    def get_data_bytes(
        self, resource_id: str, revision_id: str
    ) -> Generator[IO[bytes]]:
        yield io.BytesIO(self._data_store[resource_id][revision_id])

    def get_revision_info(self, resource_id: str, revision_id: str) -> RevisionInfo:
        return self._info_serializer.decode(self._info_store[resource_id][revision_id])

    def save_data_bytes(
        self, resource_id: str, revision_id: str, data: IO[bytes]
    ) -> None:
        if resource_id not in self._data_store:
            self._data_store[resource_id] = {}
        self._data_store[resource_id][revision_id] = data.read()
        if resource_id not in self._info_store:
            self._info_store[resource_id] = {}

    def save_revision_info(self, info: RevisionInfo) -> None:
        self._info_store[info.resource_id][info.revision_id] = (
            self._info_serializer.encode(info)
        )


class DiskResourceStore(IResourceStore[T]):
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

    @contextmanager
    def get_data_bytes(
        self, resource_id: str, revision_id: str
    ) -> Generator[IO[bytes]]:
        path = self._get_data_path(resource_id, revision_id)
        with path.open("rb") as f:
            yield f

    def get_revision_info(self, resource_id: str, revision_id: str) -> RevisionInfo:
        info_path = self._get_info_path(resource_id, revision_id)
        with info_path.open("rb") as f:
            return self._info_serializer.decode(f.read())

    def save_data_bytes(
        self, resource_id: str, revision_id: str, data: IO[bytes]
    ) -> None:
        resource_path = self._rootdir / resource_id
        resource_path.mkdir(parents=True, exist_ok=True)
        path = self._get_data_path(resource_id, revision_id)
        with path.open("wb") as out_f:
            out_f.write(data.read())

    def save_revision_info(self, info: RevisionInfo) -> None:
        resource_path = self._rootdir / info.resource_id
        resource_path.mkdir(parents=True, exist_ok=True)
        path = self._get_info_path(info.resource_id, info.revision_id)
        with path.open("wb") as f:
            f.write(self._info_serializer.encode(info))
