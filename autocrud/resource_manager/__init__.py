"""Curated public ResourceManager and storage API.

Use this namespace for programmatic resource-manager access and storage
configuration without importing from deeper implementation modules.
"""

from autocrud.resource_manager.basic import (
    Encoding,
    IBlobStore,
    IMetaStore,
    IResourceStore,
    IStorage,
)
from autocrud.resource_manager.core import ResourceManager, ResourceOps, SimpleStorage
from autocrud.resource_manager.pydantic_converter import (
    pydantic_to_struct,
    pydantic_to_validator,
    struct_to_pydantic,
)
from autocrud.resource_manager.storage_factory import (
    DiskStorageFactory,
    IStorageFactory,
    MemoryStorageFactory,
    PostgresDiskStorageFactory,
    PostgreSQLS3StorageFactory,
    PostgreSQLStorageFactory,
    PostgresStorageFactory,
    S3StorageFactory,
)

__all__ = [
    "DiskStorageFactory",
    "Encoding",
    "IBlobStore",
    "IMetaStore",
    "IResourceStore",
    "IStorage",
    "IStorageFactory",
    "MemoryStorageFactory",
    "PostgresDiskStorageFactory",
    "PostgresStorageFactory",
    "PostgreSQLS3StorageFactory",
    "PostgreSQLStorageFactory",
    "ResourceManager",
    "ResourceOps",
    "S3StorageFactory",
    "SimpleStorage",
    "pydantic_to_struct",
    "pydantic_to_validator",
    "struct_to_pydantic",
]
