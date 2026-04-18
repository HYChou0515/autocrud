from autocrud.crud.core import AutoCRUD, LoadStats
from autocrud.query import QB
from autocrud.resource_manager.core import ResourceOps
from autocrud.resource_manager.pydantic_converter import (
    pydantic_to_struct,
    struct_to_pydantic,
)
from autocrud.schema import Schema
from autocrud.types import (
    BackgroundTaskAccepted,
    BlobUploadSession,
    DisplayName,
    DuplicateResourceError,
    IConstraintChecker,
    IValidator,
    Job,
    JobRedirectInfo,
    MissingOperationContextError,
    OnDelete,
    OnDuplicate,
    Ref,
    RefRevision,
    RefType,
    RevisionNotMigratedError,
    SearchedResource,
    TaskStatus,
    Unique,
    UniqueConstraintError,
    ValidationError,
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
    "DuplicateResourceError",
    "IConstraintChecker",
    "IValidator",
    "Job",
    "JobRedirectInfo",
    "LoadStats",
    "MissingOperationContextError",
    "OnDelete",
    "OnDuplicate",
    "QB",
    "Ref",
    "RefRevision",
    "ResourceOps",
    "RefType",
    "RevisionNotMigratedError",
    "Schema",
    "SearchedResource",
    "TaskStatus",
    "Unique",
    "UniqueConstraintError",
    "ValidationError",
    "crud",
    "pydantic_to_struct",
    "struct_to_pydantic",
]
__version__ = "0.8.3a13"
