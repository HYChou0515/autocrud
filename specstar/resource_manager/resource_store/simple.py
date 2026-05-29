import io
import os
from collections.abc import Generator, Iterable
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import IO
from uuid import UUID

from specstar.resource_manager.basic import (
    Encoding,
    IResourceStore,
    MsgspecSerializer,
)
from specstar.types import RevisionInfo

UID = UUID
UIDStr = str
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

    def save_many(self, items: Iterable[tuple[RevisionInfo, bytes | DataIO]]) -> None:
        """Bulk save multiple revisions.

        Each *item* is ``(info, data)`` where *data* is raw bytes **or** an
        ``IO[bytes]`` file-like object (only ``read()`` is called).
        """
        for info, data in items:
            raw = bytes(data) if isinstance(data, (bytes, bytearray)) else data.read()
            self._store.setdefault(info.resource_id, {}).setdefault(
                info.revision_id, {}
            )[info.schema_version] = info.uid
            self._raw_data_store[info.uid] = raw
            self._raw_info_store[info.uid] = self._info_serializer.encode(info)

    def purge_resource(self, resource_id: str) -> None:
        """Hard-delete all revision data for a resource."""
        if resource_id not in self._store:
            return
        for revision_dict in self._store[resource_id].values():
            for uid in revision_dict.values():
                self._raw_data_store.pop(uid, None)
                self._raw_info_store.pop(uid, None)
        del self._store[resource_id]


def relative_walk_up(path: Path, start: Path) -> Path:
    """Compute a relative path from *start* to *path*, walking up if needed.

    Uses ``Path.relative_to(walk_up=True)`` when available (Python 3.12+)
    and falls back to ``os.path.relpath`` on older runtimes or when the
    keyword is removed (Python 3.14+).
    """
    try:
        # ``walk_up`` is a Python 3.12+ kwarg; the except below catches
        # the TypeError on older stdlibs.
        return path.relative_to(start, walk_up=True)  # ty: ignore[unknown-argument]
    except TypeError:
        if path.drive != start.drive:
            # fallback: return absolute instead of crash
            return path
        return Path(os.path.relpath(path, start))


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

    def _get_uid_store_realdir(self, uid: UIDStr) -> Path:
        return self._rootdir / "store" / uid

    def _get_raw_data_path(self, uid: UIDStr) -> Path:
        return self._get_uid_store_realdir(uid) / "data"

    def _get_raw_info_path(self, uid: UIDStr) -> Path:
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
        symd.symlink_to(relative_walk_up(reald, symd.parent), target_is_directory=True)

        # Write data and info
        with self._get_raw_data_path(str(info.uid)).open("wb") as f:
            f.write(data.read())
        with self._get_raw_info_path(str(info.uid)).open("wb") as f:
            f.write(self._info_serializer.encode(info))

    def collect_orphans(self, live_resource_ids: "set[str]") -> int:
        """Remove resource/store dirs not referenced by a finalised meta.

        An interrupted ``create()`` writes ``resource/<id>/`` and
        ``store/<uid>/`` before the meta commit marker lands, leaving durable
        garbage on disk. Given the set of resource ids that *do* have a
        finalised meta (the source of truth), this reclaims:

        * ``resource/<id>/`` trees whose id is not in *live_resource_ids*, and
        * ``store/<uid>/`` blobs no longer referenced by any live resource.

        Returns the number of directories removed (resource trees + blobs).
        """
        import shutil

        removed = 0
        resource_root = self._rootdir / "resource"
        store_root = self._rootdir / "store"

        live_uids: set[str] = set()
        if resource_root.exists():
            for rid_dir in resource_root.iterdir():
                if not rid_dir.is_dir():
                    continue
                if rid_dir.name in live_resource_ids:
                    # Record the store blobs this live resource points at so we
                    # don't reclaim them in the store sweep below.
                    for rev_dir in rid_dir.iterdir():
                        if not rev_dir.is_dir():
                            continue
                        for ver_link in rev_dir.iterdir():
                            with suppress(OSError):
                                live_uids.add(ver_link.resolve().name)
                else:
                    shutil.rmtree(rid_dir)
                    removed += 1

        if store_root.exists():
            for uid_dir in store_root.iterdir():
                if uid_dir.is_dir() and uid_dir.name not in live_uids:
                    shutil.rmtree(uid_dir)
                    removed += 1

        return removed

    def purge_resource(self, resource_id: str) -> None:
        """Hard-delete all revision data for a resource from disk."""
        import shutil

        resource_dir = self._rootdir / resource_id
        if resource_dir.exists():
            # Collect UIDs to remove from store/ as well
            uids_to_remove: list[str] = []
            for revision_dir in resource_dir.iterdir():
                if not revision_dir.is_dir():
                    continue
                for schema_dir in revision_dir.iterdir():
                    if not schema_dir.is_dir():
                        continue
                    # Resolve symlink to get the real directory
                    real = schema_dir.resolve()
                    uid = real.name
                    uids_to_remove.append(uid)
            # Remove resource symlink tree
            shutil.rmtree(resource_dir)
            # Remove real store data
            for uid in uids_to_remove:
                real_dir = self._get_uid_store_realdir(uid)
                if real_dir.exists():
                    shutil.rmtree(real_dir)
