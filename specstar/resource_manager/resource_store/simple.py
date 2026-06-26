import io
import os
import uuid as uuid_module
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
from specstar.util.fanout import (
    SHARD_ROOT,
    iter_legacy_children,
    sharded_dir,
)
from specstar.util.fs_retry import retry_on_estale

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

    # -- Path helpers -----------------------------------------------------
    #
    # Real data lives under ``store/`` keyed by uid; the revision->uid symlink
    # tree lives under ``resource/`` keyed by resource_id. Both top levels are
    # sharded (``_sh/<ab>/<cd>/``) so neither accumulates an unbounded number
    # of entries — NAS per-directory inode/dirent limits. Reads fall back to
    # the pre-#387 flat layout so existing data keeps working. See #387.

    def _store_root(self) -> Path:
        return self._rootdir / "store"

    def _resource_root(self) -> Path:
        return self._rootdir / "resource"

    def _get_uid_store_realdir(self, uid: UIDStr) -> Path:
        """Sharded directory new real data for *uid* is written to (#387)."""
        return sharded_dir(self._store_root(), uid) / uid

    def _realdir_candidates(self, uid: UIDStr) -> Generator[Path]:
        """Yield real dirs to try: sharded first, then legacy flat (#387)."""
        yield sharded_dir(self._store_root(), uid) / uid
        yield self._store_root() / uid

    def _resolve_realdir(self, uid: UIDStr) -> Path:
        for candidate in self._realdir_candidates(uid):
            if candidate.exists():
                return candidate
        return self._get_uid_store_realdir(uid)

    def _get_raw_data_path(self, uid: UIDStr) -> Path:
        return self._get_uid_store_realdir(uid) / "data"

    def _get_raw_info_path(self, uid: UIDStr) -> Path:
        return self._get_uid_store_realdir(uid) / "info"

    @staticmethod
    def _p_schema(schema_version: SchemaVersion | None) -> str:
        return "no_ver" if schema_version is None else f"v_{schema_version}"

    def _get_uid_store_symdir(
        self,
        resource_id: ResourceID,
        revision_id: RevisionID,
        schema_version: SchemaVersion | None,
    ) -> Path:
        """Sharded symlink path new revisions are written to (#387)."""
        return (
            sharded_dir(self._resource_root(), resource_id)
            / resource_id
            / revision_id
            / self._p_schema(schema_version)
        )

    def _symdir_candidates(
        self,
        resource_id: ResourceID,
        revision_id: RevisionID,
        schema_version: SchemaVersion | None,
    ) -> Generator[Path]:
        """Yield symlink dirs to try: sharded first, then legacy flat (#387)."""
        p = self._p_schema(schema_version)
        yield (
            sharded_dir(self._resource_root(), resource_id)
            / resource_id
            / revision_id
            / p
        )
        yield self._resource_root() / resource_id / revision_id / p

    def _rid_dir_candidates(self, resource_id: ResourceID) -> Generator[Path]:
        """Yield a resource_id's revision-tree dirs across both layouts (#387)."""
        yield sharded_dir(self._resource_root(), resource_id) / resource_id
        yield self._resource_root() / resource_id

    def list_resources(self) -> Generator[ResourceID]:
        resource_root = self._resource_root()
        seen: set[str] = set()
        # Sharded entries first, then legacy flat children (excluding ``_sh``).
        for d in resource_root.glob(f"{SHARD_ROOT}/*/*/*"):
            if d.is_dir() and d.name not in seen:
                seen.add(d.name)
                yield d.name
        for d in iter_legacy_children(resource_root):
            if d.is_dir() and d.name not in seen:
                seen.add(d.name)
                yield d.name

    def list_revisions(self, resource_id: ResourceID) -> Generator[RevisionID]:
        # A resource_id's revisions may be split across layouts after a partial
        # migration, so union both candidate trees. See #387.
        seen: set[str] = set()
        for rid_dir in self._rid_dir_candidates(resource_id):
            if not rid_dir.exists():
                continue
            for d in rid_dir.iterdir():
                if d.is_dir() and d.name not in seen:
                    seen.add(d.name)
                    yield d.name

    def list_schema_versions(
        self, resource_id: ResourceID, revision_id: RevisionID
    ) -> Generator[SchemaVersion | None]:
        seen: set[str] = set()
        for rid_dir in self._rid_dir_candidates(resource_id):
            schema_dir = rid_dir / revision_id
            if not schema_dir.exists():
                continue
            for d in schema_dir.iterdir():
                if d.is_dir() and d.name not in seen:
                    seen.add(d.name)
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
        return any(
            c.exists()
            for c in self._symdir_candidates(
                resource_id, revision_id, schema_version
            )
        )

    def _resolve_symdir(
        self,
        resource_id: ResourceID,
        revision_id: RevisionID,
        schema_version: SchemaVersion | None,
    ) -> Path:
        for candidate in self._symdir_candidates(
            resource_id, revision_id, schema_version
        ):
            if candidate.exists():
                return candidate
        # Default to the sharded path; a subsequent open() raises the same
        # FileNotFoundError the flat layout would have. See #352, #387.
        return self._get_uid_store_symdir(resource_id, revision_id, schema_version)

    @contextmanager
    def get_data_bytes(
        self,
        resource_id: ResourceID,
        revision_id: RevisionID,
        schema_version: SchemaVersion | None,
    ) -> Generator[DataIO]:
        data_path = (
            self._resolve_symdir(resource_id, revision_id, schema_version) / "data"
        )
        # ESTALE on NFS — a concurrent rename invalidated our inode cache.
        # Bounded retry resolves it without surfacing OSError to the caller.
        # See #352.
        f = retry_on_estale(data_path.open, "rb")
        try:
            yield f
        finally:
            f.close()

    def get_revision_info(
        self,
        resource_id: ResourceID,
        revision_id: RevisionID,
        schema_version: SchemaVersion | None,
    ) -> RevisionInfo:
        info_path = (
            self._resolve_symdir(resource_id, revision_id, schema_version) / "info"
        )

        def _read() -> bytes:
            with info_path.open("rb") as f:
                return f.read()

        return self._info_serializer.decode(retry_on_estale(_read))

    def save(self, info: RevisionInfo, data: DataIO) -> None:
        symd = self._get_uid_store_symdir(
            info.resource_id, info.revision_id, info.schema_version
        )
        reald = self._get_uid_store_realdir(str(info.uid))

        # mkdir(exist_ok=True) is already race-tolerant.
        reald.mkdir(parents=True, exist_ok=True)
        symd.parent.mkdir(parents=True, exist_ok=True)

        # Atomic symlink swap: the previous code did exists()→unlink()→symlink_to(),
        # which TOCTOU-races concurrent writers and crashes with either
        # FileExistsError or FileNotFoundError on local FS (see #352). Create a
        # uniquely-named tmp symlink, then ``os.replace`` it onto ``symd`` —
        # POSIX guarantees rename of a symlink onto an existing symlink is atomic.
        # ``relative_walk_up`` recomputes the relative target for the deeper
        # sharded nesting, keeping the symlink portable across PVC remounts.
        target = relative_walk_up(reald, symd.parent)
        tmp_link = symd.with_name(f"{symd.name}.tmp.{uuid_module.uuid4().hex}")
        try:
            tmp_link.symlink_to(target, target_is_directory=True)
            os.replace(tmp_link, symd)
        except BaseException:
            with suppress(FileNotFoundError):
                tmp_link.unlink()
            raise

        # Write data and info
        with self._get_raw_data_path(str(info.uid)).open("wb") as f:
            f.write(data.read())
        with self._get_raw_info_path(str(info.uid)).open("wb") as f:
            f.write(self._info_serializer.encode(info))

    def _iter_rid_dirs(self) -> Generator[Path]:
        """Yield every resource-id revision-tree dir across both layouts."""
        resource_root = self._resource_root()
        for d in resource_root.glob(f"{SHARD_ROOT}/*/*/*"):
            if d.is_dir():
                yield d
        for d in iter_legacy_children(resource_root):
            if d.is_dir():
                yield d

    def _iter_uid_dirs(self) -> Generator[Path]:
        """Yield every store uid dir across both layouts."""
        store_root = self._store_root()
        for d in store_root.glob(f"{SHARD_ROOT}/*/*/*"):
            if d.is_dir():
                yield d
        for d in iter_legacy_children(store_root):
            if d.is_dir():
                yield d

    def collect_orphans(self, live_resource_ids: "set[str]") -> int:
        """Remove resource/store dirs not referenced by a finalised meta.

        An interrupted ``create()`` writes ``resource/<id>/`` and
        ``store/<uid>/`` before the meta commit marker lands, leaving durable
        garbage on disk. Given the set of resource ids that *do* have a
        finalised meta (the source of truth), this reclaims:

        * ``resource/<id>/`` trees whose id is not in *live_resource_ids*, and
        * ``store/<uid>/`` blobs no longer referenced by any live resource.

        Walks both the sharded (#387) and legacy flat layouts. Returns the
        number of directories removed (resource trees + blobs).
        """
        import shutil

        removed = 0
        live_uids: set[str] = set()
        for rid_dir in self._iter_rid_dirs():
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

        for uid_dir in self._iter_uid_dirs():
            if uid_dir.name not in live_uids:
                shutil.rmtree(uid_dir)
                removed += 1

        return removed

    def purge_resource(self, resource_id: str) -> None:
        """Hard-delete all revision data for a resource from disk.

        Handles both the sharded (#387) and legacy flat layouts. (The previous
        implementation looked under ``rootdir/<id>`` instead of
        ``rootdir/resource/<id>`` and silently purged nothing.)
        """
        import shutil

        rid_dirs = [d for d in self._rid_dir_candidates(resource_id) if d.exists()]
        if not rid_dirs:
            return
        # Collect the uids the symlink tree points at before removing it.
        uids_to_remove: list[str] = []
        for resource_dir in rid_dirs:
            for revision_dir in resource_dir.iterdir():
                if not revision_dir.is_dir():
                    continue
                for schema_dir in revision_dir.iterdir():
                    if not schema_dir.is_dir():
                        continue
                    with suppress(OSError):
                        uids_to_remove.append(schema_dir.resolve().name)
        for resource_dir in rid_dirs:
            shutil.rmtree(resource_dir)
        for uid in uids_to_remove:
            for real_dir in self._realdir_candidates(uid):
                if real_dir.exists():
                    shutil.rmtree(real_dir)

    def migrate_layout(self, *, dry_run: bool = False) -> int:
        """Relocate pre-#387 flat resource/store data into the sharded trees.

        Moves ``store/<uid>/`` directories into ``store/_sh/<ab>/<cd>/`` and
        recreates each ``resource/<rid>/<rev>/<ver>`` symlink under
        ``resource/_sh/<ab>/<cd>/`` with its relative target recomputed for the
        new depth. Store dirs are moved first so the recomputed symlink targets
        point at the already-relocated real data. Idempotent and re-runnable;
        reads fall back to the flat layout until each move lands.

        Returns the number of entries relocated (store dirs + symlinks), or —
        when *dry_run* — that would be relocated.
        """
        moved = 0
        store_root = self._store_root()
        resource_root = self._resource_root()

        # 1. store/<uid> -> store/_sh/<ab>/<cd>/<uid>
        for child in iter_legacy_children(store_root):
            if not child.is_dir():
                continue
            target = sharded_dir(store_root, child.name) / child.name
            if target.exists():
                continue
            moved += 1
            if dry_run:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(child, target)

        # 2. resource/<rid>/<rev>/<ver> symlink -> sharded, target recomputed.
        for rid_dir in list(iter_legacy_children(resource_root)):
            if not rid_dir.is_dir():
                continue
            rid = rid_dir.name
            for rev_dir in list(rid_dir.iterdir()):
                if not rev_dir.is_dir():
                    continue
                rev = rev_dir.name
                for ver_link in list(rev_dir.iterdir()):
                    ver = ver_link.name
                    new_symdir = (
                        sharded_dir(resource_root, rid) / rid / rev / ver
                    )
                    if new_symdir.exists():
                        continue
                    # ``resolve().name`` yields the uid even if the legacy
                    # relative target is now dangling (store dir already moved).
                    try:
                        uid = ver_link.resolve().name
                    except OSError:
                        continue
                    moved += 1
                    if dry_run:
                        continue
                    realdir = self._resolve_realdir(uid)
                    new_symdir.parent.mkdir(parents=True, exist_ok=True)
                    target = relative_walk_up(realdir, new_symdir.parent)
                    tmp_link = new_symdir.with_name(
                        f"{ver}.tmp.{uuid_module.uuid4().hex}"
                    )
                    try:
                        tmp_link.symlink_to(target, target_is_directory=True)
                        os.replace(tmp_link, new_symdir)
                    except BaseException:
                        with suppress(FileNotFoundError):
                            tmp_link.unlink()
                        raise
                    ver_link.unlink()
            if not dry_run:
                # Prune the now-empty legacy revision dirs and rid dir.
                for rev_dir in list(rid_dir.iterdir()):
                    with suppress(OSError):
                        rev_dir.rmdir()
                with suppress(OSError):
                    rid_dir.rmdir()
        return moved
