"""
Resource Store implementations for AutoCRUD
"""

from autocrud.resource_manager.resource_store.simple import (
    MemoryResourceStore,
    DiskResourceStore,
)
from autocrud.resource_manager.resource_store.s3 import S3ResourceStore
from autocrud.resource_manager.resource_store.cached_s3 import CachedS3ResourceStore
from autocrud.resource_manager.resource_store.mq_cached_s3 import (
    MQCachedS3ResourceStore,
)
from autocrud.resource_manager.resource_store.etag_cached_s3 import (
    ETagCachedS3ResourceStore,
)

__all__ = [
    "MemoryResourceStore",
    "DiskResourceStore",
    "S3ResourceStore",
    "CachedS3ResourceStore",
    "MQCachedS3ResourceStore",
    "ETagCachedS3ResourceStore",
]
