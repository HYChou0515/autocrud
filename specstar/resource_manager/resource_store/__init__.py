"""
Resource Store implementations for SpecStar
"""

from specstar.resource_manager.resource_store.cached_s3 import CachedS3ResourceStore
from specstar.resource_manager.resource_store.etag_cached_s3 import (
    ETagCachedS3ResourceStore,
)
from specstar.resource_manager.resource_store.mq_cached_s3 import (
    MQCachedS3ResourceStore,
)
from specstar.resource_manager.resource_store.postgres import PostgresResourceStore
from specstar.resource_manager.resource_store.s3 import S3ResourceStore
from specstar.resource_manager.resource_store.simple import (
    DiskResourceStore,
    MemoryResourceStore,
)

__all__ = [
    "MemoryResourceStore",
    "DiskResourceStore",
    "S3ResourceStore",
    "CachedS3ResourceStore",
    "MQCachedS3ResourceStore",
    "ETagCachedS3ResourceStore",
    "PostgresResourceStore",
]
