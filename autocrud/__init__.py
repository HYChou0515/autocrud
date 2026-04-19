from autocrud.crud.core import AutoCRUD, LoadStats
from autocrud.query import QB
from autocrud.resource_manager.pydantic_converter import (
    pydantic_to_struct,
    struct_to_pydantic,
)
from autocrud.schema import Schema
from autocrud.types import (
    BackgroundTaskAccepted,
    BlobUploadSession,
    DisplayName,
    IConstraintChecker,
    IValidator,
    Job,
    JobRedirectInfo,
    OnDelete,
    OnDuplicate,
    Ref,
    RefRevision,
    RefType,
    SearchedResource,
    TaskStatus,
    Unique,
)

# Global instance for simplified usage pattern
# Users can import and use this directly: `from autocrud import crud`
# Configure it at application startup: `crud.configure(storage_factory=...)`
crud = AutoCRUD()

__all__ = [
    "AutoCRUD",
    "BackgroundTaskAccepted",
    "BlobUploadSession",
    "DisplayName",
    "IConstraintChecker",
    "IValidator",
    "Job",
    "JobRedirectInfo",
    "LoadStats",
    "OnDelete",
    "OnDuplicate",
    "QB",
    "Ref",
    "RefRevision",
    "RefType",
    "Schema",
    "SearchedResource",
    "TaskStatus",
    "Unique",
    "crud",
    "pydantic_to_struct",
    "struct_to_pydantic",
]
__version__ = "0.8.3a13"
