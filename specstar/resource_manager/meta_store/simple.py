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
)
from specstar.types import ResourceMeta
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

    def _get_path(self, pk: str) -> Path:
        return self._rootdir / f"{pk}{self._suffix}"

    def __contains__(self, pk: str):  # ty:ignore[invalid-method-override]
        path = self._get_path(pk)
        return path.exists()

    def __getitem__(self, pk: str) -> ResourceMeta:
        path = self._get_path(pk)

        def _read() -> bytes:
            with path.open("rb") as f:
                return f.read()

        try:
            # ESTALE retried inside; ENOENT still maps to KeyError so the
            # "resource does not exist" contract matches every other meta
            # store. See #352.
            raw = retry_on_estale(_read)
        except FileNotFoundError:
            raise KeyError(pk) from None
        return self._serializer.decode(raw)

    def __setitem__(self, pk: str, b: ResourceMeta) -> None:
        path = self._get_path(pk)
        data = self._serializer.encode(b)
        # Write to a temp file in the same directory, then atomically rename it
        # into place. A finalised ``<pk>.data`` therefore always holds a
        # complete record and acts as the "commit marker": an interrupted write
        # leaves only the temp file (excluded by the ``*.data`` glob and never
        # decoded), so it is invisible to the loader instead of crashing boot.
        fd, tmp = tempfile.mkstemp(
            dir=self._rootdir, prefix=f"{pk}.", suffix=".data.tmp"
        )
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

    def __delitem__(self, pk: str) -> None:
        path = self._get_path(pk)
        try:
            path.unlink()
        except FileNotFoundError:
            raise KeyError(pk) from None

    def __iter__(self) -> Generator[str]:
        for file in self._rootdir.glob(f"*{self._suffix}"):
            yield file.stem

    def __len__(self) -> int:
        return len(list(self._rootdir.glob(f"*{self._suffix}")))

    def iter_search(self, query: ResourceMetaSearchQuery) -> Generator[ResourceMeta]:
        results: list[ResourceMeta] = []
        for file in self._rootdir.glob(f"*{self._suffix}"):

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
