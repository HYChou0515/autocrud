from abc import ABC, abstractmethod
from pathlib import Path
from typing import TypeVar

from autocrud.resource_manager.basic import IStorage
from autocrud.resource_manager.core import SimpleStorage
from autocrud.resource_manager.meta_store.simple import DiskMetaStore, MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import (
    DiskResourceStore,
    MemoryResourceStore,
)
from autocrud.types import IMigration

T = TypeVar("T")


class IStorageFactory(ABC):
    @abstractmethod
    def build(
        self,
        model: type[T],
        model_name: str,
        *,
        migration: IMigration | None = None,
    ) -> IStorage[T]: ...


class MemoryStorageFactory(IStorageFactory):
    def build(
        self,
        model: type[T],
        model_name: str,
        *,
        migration: IMigration | None = None,
    ) -> IStorage[T]:
        meta_store = MemoryMetaStore()

        resource_store = MemoryResourceStore[T](resource_type=model)

        return SimpleStorage(meta_store, resource_store)


class DiskStorageFactory(IStorageFactory):
    def __init__(
        self,
        rootdir: Path | str,
    ):
        self.rootdir = Path(rootdir)

    def build(
        self,
        model: type[T],
        model_name: str,
        *,
        migration: IMigration | None = None,
    ) -> IStorage[T]:
        meta_store = DiskMetaStore(rootdir=self.rootdir / model_name / "meta")

        # 對於其他類型（msgspec.Struct, dataclass, TypedDict），使用原生支持
        resource_store = DiskResourceStore[T](
            resource_type=model,
            rootdir=self.rootdir / model_name / "data",
            migration=migration,
        )

        return SimpleStorage(meta_store, resource_store)
