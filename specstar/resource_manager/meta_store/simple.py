import os
import tempfile
from collections.abc import Generator, Iterable
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import TypeVar

from msgspec import UNSET

from specstar.query_types import ResourceMetaSearchQuery
from specstar.resource_manager.basic import (
    Encoding,
    IFastMetaStore,
    MsgspecSerializer,
    get_sort_fn,
    is_match_query,
    reject_fuzzy,
    reject_unquantified_list_string_ops,
)
from specstar.types import ResourceMeta
from specstar.util.fanout import (
    SHARD_ROOT,
    iter_legacy_children,
    sharded_dir,
)
from specstar.util.fs_retry import is_transient_fs_error, retry_on_estale

T = TypeVar("T")


class MemoryMetaStore(IFastMetaStore):
    def __init__(self, encoding: Encoding = Encoding.json):
        self._serializer = MsgspecSerializer(
            encoding=encoding,
            resource_type=ResourceMeta,
        )
        self._store: dict[str, bytes] = {}

    def __getitem__(self, pk: str) -> ResourceMeta:
        return self._serializer.decode(self._store[pk])

    def __setitem__(self, pk: str, b: ResourceMeta) -> None:
        self._store[pk] = self._serializer.encode(b)

    def __delitem__(self, pk: str) -> None:
        del self._store[pk]

    def __iter__(self) -> Generator[str]:
        # Snapshot: a concurrent create/delete must not raise
        # "dictionary changed size during iteration".
        yield from list(self._store.keys())

    def __len__(self) -> int:
        return len(self._store)

    def iter_search(self, query: ResourceMetaSearchQuery) -> Generator[ResourceMeta]:
        reject_fuzzy(query)
        reject_unquantified_list_string_ops(query, self._registered_list_fields())
        results: list[ResourceMeta] = []
        # Snapshot the values: a concurrent write mid-search must not raise
        # "dictionary changed size during iteration".
        for meta_b in list(self._store.values()):
            meta = self._serializer.decode(meta_b)
            if is_match_query(meta, query):
                results.append(meta)
        results.sort(key=get_sort_fn([] if query.sorts is UNSET else query.sorts))
        yield from results[query.offset : query.offset + query.limit]

    @contextmanager
    def get_then_delete(self) -> Generator[Iterable[ResourceMeta]]:
        """获取所有元数据然后删除，用于快速存储的批量同步"""
        # Materialise a snapshot before yielding so consumption can't race a
        # concurrent write ("dictionary changed size during iteration").
        decoded = [self._serializer.decode(v) for v in list(self._store.values())]
        yield decoded
        self._store.clear()


class DiskMetaStore(IFastMetaStore):
    def __init__(
        self,
        *,
        encoding: Encoding = Encoding.json,
        rootdir: Path | str,
        fsync: bool = False,
    ):
        self._serializer = MsgspecSerializer(
            encoding=encoding,
            resource_type=ResourceMeta,
        )
        self._rootdir = Path(rootdir)
        self._rootdir.mkdir(parents=True, exist_ok=True)
        self._suffix = ".data"
        # When True, fsync the meta file before the atomic rename so a finalised
        # commit marker survives an OS crash / power loss, not just a process
        # kill. Off by default: it adds a sync per write, which would throttle
        # high-volume batch ingest (the workload most likely to be interrupted).
        self._fsync = fsync

    def _leaf(self, pk: str) -> str:
        return f"{pk}{self._suffix}"

    def _write_path(self, pk: str) -> Path:
        """Sharded path new records for *pk* are written to (#387)."""
        return sharded_dir(self._rootdir, pk) / self._leaf(pk)

    def _candidate_paths(self, pk: str):
        """Yield paths to try on read: sharded first, then legacy flat (#387)."""
        leaf = self._leaf(pk)
        yield sharded_dir(self._rootdir, pk) / leaf
        yield self._rootdir / leaf

    def _iter_data_files(self) -> Generator[Path]:
        """Yield every record file across both layouts, deduped by stem.

        Sharded entries (``_sh/<ab>/<cd>/<pk>.data``) take precedence over a
        stale legacy twin (``<pk>.data``) should both momentarily exist. The
        top-level glob matches only legacy files — the ``_sh`` container has no
        ``.data`` suffix and is not recursed into. See #387.
        """
        seen: set[str] = set()
        for file in self._rootdir.glob(f"{SHARD_ROOT}/*/*/*{self._suffix}"):
            seen.add(file.stem)
            yield file
        for file in self._rootdir.glob(f"*{self._suffix}"):
            if file.stem not in seen:
                yield file

    def __contains__(self, pk: str):  # ty:ignore[invalid-method-override]
        return any(p.exists() for p in self._candidate_paths(pk))

    def __getitem__(self, pk: str) -> ResourceMeta:
        for path in self._candidate_paths(pk):

            def _read(p: Path = path) -> bytes:
                with p.open("rb") as f:
                    return f.read()

            try:
                # ESTALE retried inside; ENOENT falls through to the next
                # candidate (sharded -> legacy), and KeyError only if neither
                # layout has it — matching every other meta store. See #352, #387.
                raw = retry_on_estale(_read)
            except FileNotFoundError:
                continue
            return self._serializer.decode(raw)
        raise KeyError(pk)

    def __setitem__(self, pk: str, b: ResourceMeta) -> None:
        path = self._write_path(pk)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = self._serializer.encode(b)
        # Write to a temp file in the same (shard) directory, then atomically
        # rename it into place. A finalised ``<pk>.data`` therefore always holds
        # a complete record and acts as the "commit marker": an interrupted
        # write leaves only the temp file (excluded by the ``*.data`` glob and
        # never decoded), so it is invisible to the loader instead of crashing
        # boot.
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f"{pk}.", suffix=".data.tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                if self._fsync:
                    f.flush()
                    os.fsync(f.fileno())
            # ESTALE here means another NFS client invalidated our dirfd
            # mid-replace; retry sees a fresh inode and the commit lands.
            retry_on_estale(os.replace, tmp, path)
        except BaseException:
            with suppress(FileNotFoundError):
                os.unlink(tmp)
            raise
        # Drop any legacy flat twin so the record exists in exactly one place
        # (write-through migration). See #387.
        with suppress(FileNotFoundError):
            (self._rootdir / self._leaf(pk)).unlink()

    def __delitem__(self, pk: str) -> None:
        removed = False
        for path in self._candidate_paths(pk):
            try:
                path.unlink()
                removed = True
            except FileNotFoundError:
                continue
        if not removed:
            raise KeyError(pk)

    def __iter__(self) -> Generator[str]:
        for file in self._iter_data_files():
            yield file.stem

    def __len__(self) -> int:
        return sum(1 for _ in self._iter_data_files())

    def iter_search(self, query: ResourceMetaSearchQuery) -> Generator[ResourceMeta]:
        reject_fuzzy(query)
        reject_unquantified_list_string_ops(query, self._registered_list_fields())
        results: list[ResourceMeta] = []
        for file in self._iter_data_files():

            def _read(p: Path = file) -> bytes:
                with p.open("rb") as f:
                    return f.read()

            try:
                raw = retry_on_estale(_read)
            except FileNotFoundError:
                # File removed (concurrent purge / aborted write) between the
                # directory listing and the read — skip it, don't crash.
                continue
            except OSError as exc:
                # A persistently-stale handle (after retries) for a single
                # file is treated like a missing file: skip rather than crash
                # the entire search. See #352.
                if is_transient_fs_error(exc):
                    continue
                raise
            meta = self._serializer.decode(raw)
            if is_match_query(meta, query):
                results.append(meta)
        results.sort(key=get_sort_fn([] if query.sorts is UNSET else query.sorts))
        yield from results[query.offset : query.offset + query.limit]

    @contextmanager
    def get_then_delete(self) -> Generator[Iterable[ResourceMeta]]:
        """获取所有元数据然后删除，用于快速存储的批量同步"""
        pks = list(self)
        yield (self[pk] for pk in pks)
        for pk in pks:
            with suppress(FileNotFoundError):
                del self[pk]

    def migrate_layout(self, *, dry_run: bool = False) -> int:
        """Relocate pre-#387 flat ``<pk>.data`` records into the sharded tree.

        Walks the legacy flat layout and moves each record into
        ``_sh/<ab>/<cd>/``. Safe to run on a live store: each move is an
        atomic ``os.replace`` on the same filesystem and reads fall back to
        the flat layout until the move lands. Idempotent and re-runnable.
        Returns the number of records moved (or, when *dry_run*, that would
        be moved).
        """
        moved = 0
        for child in iter_legacy_children(self._rootdir):
            if child.is_dir():
                continue
            if not child.name.endswith(self._suffix):
                continue  # skip in-flight ``*.data.tmp`` temp files
            target = sharded_dir(self._rootdir, child.stem) / child.name
            if target.exists():
                continue
            moved += 1
            if dry_run:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(child, target)
        return moved
