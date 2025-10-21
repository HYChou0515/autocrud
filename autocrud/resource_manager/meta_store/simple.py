from abc import abstractmethod
from collections.abc import Generator, Iterable
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import TypeVar

from msgspec import UNSET

from autocrud.resource_manager.basic import (
    AbstractFastMetaStore,
    Encoding,
    MsgspecSerializer,
    get_sort_fn,
    get_sort_fn_content_meta,
    is_match_query,
)
from autocrud.types import (
    ContentMeta,
    ContentMetaSearchQuery,
    ResourceMeta,
    ResourceMetaSearchQuery,
)

T = TypeVar("T")

M = TypeVar("M")
Q = TypeVar("Q")


class AbstractMemoryMetaStore(AbstractFastMetaStore[M, Q]):
    @property
    @abstractmethod
    def serializer(self) -> MsgspecSerializer[M]:
        pass

    @abstractmethod
    def iter_search(self, query: Q) -> Generator[M]:
        pass

    def __init__(self):
        self._store: dict[str, bytes] = {}

    def __getitem__(self, pk: str) -> M:
        return self.serializer.decode(self._store[pk])

    def __setitem__(self, pk: str, b: M) -> None:
        self._store[pk] = self.serializer.encode(b)

    def __delitem__(self, pk: str) -> None:
        del self._store[pk]

    def __iter__(self) -> Generator[str]:
        yield from self._store.keys()

    def __len__(self) -> int:
        return len(self._store)

    @contextmanager
    def get_then_delete(self) -> Generator[Iterable[M]]:
        """获取所有元数据然后删除，用于快速存储的批量同步"""
        yield (self.serializer.decode(v) for v in self._store.values())
        self._store.clear()


class MemoryContentMetaStore(
    AbstractMemoryMetaStore[ContentMeta, ContentMetaSearchQuery]
):
    def __init__(self, encoding: Encoding = Encoding.json):
        self._serializer = MsgspecSerializer(
            encoding=encoding,
            resource_type=ContentMeta,
        )
        super().__init__()

    @property
    def serializer(self) -> MsgspecSerializer[M]:
        return self._serializer

    def iter_search(self, query: ContentMetaSearchQuery) -> Generator[ContentMeta]:
        results: list[ContentMeta] = []
        for meta_b in self._store.values():
            meta = self._serializer.decode(meta_b)
            if is_match_query(meta, query):
                results.append(meta)
        results.sort(
            key=get_sort_fn_content_meta([] if query.sorts is UNSET else query.sorts)
        )
        yield from results[query.offset : query.offset + query.limit]


class MemoryMetaStore(AbstractMemoryMetaStore[ResourceMeta, ResourceMetaSearchQuery]):
    def __init__(self, encoding: Encoding = Encoding.json):
        self._serializer = MsgspecSerializer(
            encoding=encoding,
            resource_type=ResourceMeta,
        )
        super().__init__()

    @property
    def serializer(self) -> MsgspecSerializer[M]:
        return self._serializer

    def iter_search(self, query: ResourceMetaSearchQuery) -> Generator[ResourceMeta]:
        results: list[ResourceMeta] = []
        for meta_b in self._store.values():
            meta = self._serializer.decode(meta_b)
            if is_match_query(meta, query):
                results.append(meta)
        results.sort(key=get_sort_fn([] if query.sorts is UNSET else query.sorts))
        yield from results[query.offset : query.offset + query.limit]


class AbstractDiskMetaStore(AbstractFastMetaStore[M, Q]):
    @property
    @abstractmethod
    def serializer(self) -> MsgspecSerializer[M]:
        pass

    def __init__(self, *, rootdir: Path | str):
        self._rootdir = Path(rootdir)
        self._rootdir.mkdir(parents=True, exist_ok=True)
        self._suffix = ".data"

    def _get_path(self, pk: str) -> Path:
        return self._rootdir / f"{pk}{self._suffix}"

    def __contains__(self, pk: str):
        path = self._get_path(pk)
        return path.exists()

    def __getitem__(self, pk: str) -> M:
        path = self._get_path(pk)
        with path.open("rb") as f:
            return self.serializer.decode(f.read())

    def __setitem__(self, pk: str, b: M) -> None:
        path = self._get_path(pk)
        with path.open("wb") as f:
            f.write(self.serializer.encode(b))

    def __delitem__(self, pk: str) -> None:
        path = self._get_path(pk)
        path.unlink()

    def __iter__(self) -> Generator[str]:
        for file in self._rootdir.glob(f"*{self._suffix}"):
            yield file.stem

    def __len__(self) -> int:
        return len(list(self._rootdir.glob(f"*{self._suffix}")))

    @abstractmethod
    def iter_search(self, query: Q) -> Generator[M]:
        pass

    @contextmanager
    def get_then_delete(self) -> Generator[Iterable[M]]:
        """获取所有元数据然后删除，用于快速存储的批量同步"""
        pks = list(self)
        yield (self[pk] for pk in pks)
        for pk in pks:
            with suppress(FileNotFoundError):
                del self[pk]


class DiskMetaStore(AbstractDiskMetaStore[ResourceMeta, ResourceMetaSearchQuery]):
    def __init__(self, *, encoding: Encoding = Encoding.json, rootdir: Path | str):
        self._serializer = MsgspecSerializer(
            encoding=encoding,
            resource_type=ResourceMeta,
        )
        super().__init__(rootdir=rootdir)

    @property
    def serializer(self) -> MsgspecSerializer[ResourceMeta]:
        return self._serializer

    def iter_search(self, query: ResourceMetaSearchQuery) -> Generator[ResourceMeta]:
        results: list[ResourceMeta] = []
        for file in self._rootdir.glob(f"*{self._suffix}"):
            with file.open("rb") as f:
                meta = self._serializer.decode(f.read())
                if is_match_query(meta, query):
                    results.append(meta)
        results.sort(key=get_sort_fn([] if query.sorts is UNSET else query.sorts))
        yield from results[query.offset : query.offset + query.limit]
