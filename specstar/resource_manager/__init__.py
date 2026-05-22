"""Curated public ResourceManager and storage API.

Use this namespace for programmatic resource-manager access and storage
configuration without importing from deeper implementation modules.
"""

from specstar.resource_manager.basic import (
    Encoding,
    IBlobStore,
    IMetaStore,
    IResourceStore,
    IStorage,
)
from specstar.resource_manager.core import ResourceManager, ResourceOps, SimpleStorage
from specstar.resource_manager.pydantic_converter import (
    pydantic_to_struct,
    pydantic_to_validator,
    struct_to_pydantic,
)
from specstar.resource_manager.storage_factory import (
    DiskStorageFactory,
    IStorageFactory,
    MemoryStorageFactory,
    PostgresDiskS3StorageFactory,
    PostgresDiskStorageFactory,
    PostgreSQLS3StorageFactory,
    PostgresStorageFactory,
    S3StorageFactory,
)
from specstar.resource_manager.string_ref_constraint import (
    StringRefConstraintChecker,
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
    "PostgresDiskS3StorageFactory",
    "PostgresDiskStorageFactory",
    "PostgresStorageFactory",
    "PostgreSQLS3StorageFactory",
    "ResourceManager",
    "ResourceOps",
    "S3StorageFactory",
    "SimpleStorage",
    "StringRefConstraintChecker",
    "pydantic_to_struct",
    "pydantic_to_validator",
    "struct_to_pydantic",
]
