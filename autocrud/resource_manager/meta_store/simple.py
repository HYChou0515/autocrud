from collections.abc import Generator, Iterable
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import TypeVar

from msgspec import UNSET

from autocrud.resource_manager.basic import (
    Encoding,
    IFastMetaStore,
    MsgspecSerializer,
    get_sort_fn,
    is_match_query,
)
from autocrud.types import ResourceMeta, ResourceMetaSearchQuery

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
        yield from self._store.keys()

    def __len__(self) -> int:
        return len(self._store)

    def iter_search(self, query: ResourceMetaSearchQuery) -> Generator[ResourceMeta]:
        results: list[ResourceMeta] = []
        for meta_b in self._store.values():
            meta = self._serializer.decode(meta_b)
            if is_match_query(meta, query):
                results.append(meta)
        results.sort(key=get_sort_fn([] if query.sorts is UNSET else query.sorts))
        yield from results[query.offset : query.offset + query.limit]

    @contextmanager
    def get_then_delete(self) -> Generator[Iterable[ResourceMeta]]:
        """获取所有元数据然后删除，用于快速存储的批量同步"""
        yield (self._serializer.decode(v) for v in self._store.values())
        self._store.clear()


class DiskMetaStore(IFastMetaStore):
    def __init__(self, *, encoding: Encoding = Encoding.json, rootdir: Path | str):
        self._serializer = MsgspecSerializer(
            encoding=encoding,
            resource_type=ResourceMeta,
        )
        self._rootdir = Path(rootdir)
        self._rootdir.mkdir(parents=True, exist_ok=True)
        self._suffix = ".data"

    def _get_path(self, pk: str) -> Path:
        return self._rootdir / f"{pk}{self._suffix}"

    def __contains__(self, pk: str):
        path = self._get_path(pk)
        return path.exists()

    def __getitem__(self, pk: str) -> ResourceMeta:
        path = self._get_path(pk)
        with path.open("rb") as f:
            return self._serializer.decode(f.read())

    def __setitem__(self, pk: str, b: ResourceMeta) -> None:
        path = self._get_path(pk)
        with path.open("wb") as f:
            f.write(self._serializer.encode(b))

    def __delitem__(self, pk: str) -> None:
        path = self._get_path(pk)
        path.unlink()

    def __iter__(self) -> Generator[str]:
        for file in self._rootdir.glob(f"*{self._suffix}"):
            yield file.stem

    def __len__(self) -> int:
        return len(list(self._rootdir.glob(f"*{self._suffix}")))

    def iter_search(self, query: ResourceMetaSearchQuery) -> Generator[ResourceMeta]:
        results: list[ResourceMeta] = []
        for file in self._rootdir.glob(f"*{self._suffix}"):
            with file.open("rb") as f:
                meta = self._serializer.decode(f.read())
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
