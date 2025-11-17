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
        self._store: dict[
            ResourceID, dict[RevisionID, dict[SchemaVersion | None, UID]]
        ] = {}
        self._info_serializer = MsgspecSerializer(
            encoding=encoding,
            resource_type=RevisionInfo,
        )

    def list_resources(self) -> Generator[ResourceID]:
        yield from self._store.keys()

    def list_revisions(self, resource_id: ResourceID) -> Generator[RevisionID]:
        yield from self._store[resource_id].keys()

    def list_schema_versions(
        self, resource_id: ResourceID, revision_id: RevisionID
    ) -> Generator[SchemaVersion | None]:
        yield from self._store[resource_id][revision_id].keys()

    def exists(
        self,
        resource_id: ResourceID,
        revision_id: RevisionID,
        schema_version: SchemaVersion | None,
    ) -> bool:
        return (
            resource_id in self._store
            and revision_id in self._store[resource_id]
            and schema_version in self._store[resource_id][revision_id]
        )

    @contextmanager
    def get_data_bytes(
        self,
        resource_id: ResourceID,
        revision_id: RevisionID,
        schema_version: SchemaVersion | None,
    ) -> Generator[DataIO]:
        uid = self._store[resource_id][revision_id][schema_version]
        yield io.BytesIO(self._raw_data_store[uid])

    def get_revision_info(
        self,
        resource_id: ResourceID,
        revision_id: RevisionID,
        schema_version: SchemaVersion | None,
    ) -> RevisionInfo:
        uid = self._store[resource_id][revision_id][schema_version]
        return self._info_serializer.decode(self._raw_info_store[uid])

    def save(self, info: RevisionInfo, data: DataIO) -> None:
        self._store.setdefault(info.resource_id, {}).setdefault(info.revision_id, {})[
            info.schema_version
        ] = info.uid
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

    def _get_uid_store_realdir(self, uid: UID) -> Path:
        return self._rootdir / "store" / uid

    def _get_raw_data_path(self, uid: UID) -> Path:
        return self._get_uid_store_realdir(uid) / "data"

    def _get_raw_info_path(self, uid: UID) -> Path:
        return self._get_uid_store_realdir(uid) / "info"

    def _get_uid_store_symdir(
        self,
        resource_id: ResourceID,
        revision_id: RevisionID,
        schema_version: SchemaVersion | None,
    ) -> Path:
        if schema_version is None:
            p_schema_version = "no_ver"
        else:
            p_schema_version = f"v_{schema_version}"
        return self._rootdir / "resource" / resource_id / revision_id / p_schema_version

    def list_resources(self) -> Generator[ResourceID]:
        resource_dir = self._rootdir / "resource"
        if not resource_dir.exists():
            return
        for d in resource_dir.iterdir():
            if d.is_dir():
                yield d.name

    def list_revisions(self, resource_id: ResourceID) -> Generator[RevisionID]:
        revision_dir = self._rootdir / "resource" / resource_id
        if not revision_dir.exists():
            return
        for d in revision_dir.iterdir():
            if d.is_dir():
                yield d.name

    def list_schema_versions(
        self, resource_id: ResourceID, revision_id: RevisionID
    ) -> Generator[SchemaVersion | None]:
        schema_dir = self._rootdir / "resource" / resource_id / revision_id
        if not schema_dir.exists():
            return
        for d in schema_dir.iterdir():
            if d.is_dir():
                if d.name == "no_ver":
                    yield None
                elif d.name.startswith("v_"):
                    yield d.name[2:]

    def exists(
        self,
        resource_id: ResourceID,
        revision_id: RevisionID,
        schema_version: SchemaVersion | None,
    ) -> bool:
        path = self._get_uid_store_symdir(resource_id, revision_id, schema_version)
        return path.exists()

    @contextmanager
    def get_data_bytes(
        self,
        resource_id: ResourceID,
        revision_id: RevisionID,
        schema_version: SchemaVersion | None,
    ) -> Generator[DataIO]:
        data_path = (
            self._get_uid_store_symdir(resource_id, revision_id, schema_version)
            / "data"
        )
        with data_path.open("rb") as f:
            yield f

    def get_revision_info(
        self,
        resource_id: ResourceID,
        revision_id: RevisionID,
        schema_version: SchemaVersion | None,
    ) -> RevisionInfo:
        info_path = (
            self._get_uid_store_symdir(resource_id, revision_id, schema_version)
            / "info"
        )
        with info_path.open("rb") as f:
            return self._info_serializer.decode(f.read())

    def save(self, info: RevisionInfo, data: DataIO) -> None:
        symd = self._get_uid_store_symdir(
            info.resource_id, info.revision_id, info.schema_version
        )
        reald = self._get_uid_store_realdir(str(info.uid))

        # Create real directory if it doesn't exist
        if not reald.exists():
            reald.mkdir(parents=True, exist_ok=True)

        # Create symlink directory structure
        symd.parent.mkdir(parents=True, exist_ok=True)

        # Remove existing symlink if it exists and create new one
        if symd.exists():
            symd.unlink()
        symd.symlink_to(
            reald.relative_to(symd.parent, walk_up=True), target_is_directory=True
        )

        # Write data and info
        with self._get_raw_data_path(str(info.uid)).open("wb") as f:
            f.write(data.read())
        with self._get_raw_info_path(str(info.uid)).open("wb") as f:
            f.write(self._info_serializer.encode(info))
