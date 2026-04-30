from autocrud.backend import (
    BackendBinding,
    BackendConfig,
    BackendDefaults,
    ConnectionProfile,
    register_backend_provider,
)
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
# Users can import and use this directly: from autocrud import crud
# Configure it at application startup via crud.configure(backend=...) or
# the legacy split parameters during the transition window.
crud = AutoCRUD()

__all__ = [
    "AutoCRUD",
    "BackendBinding",
    "BackendConfig",
    "BackendDefaults",
    "BackgroundTaskAccepted",
    "BlobUploadSession",
    "ConnectionProfile",
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
    "register_backend_provider",
    "pydantic_to_struct",
    "struct_to_pydantic",
]
__version__ = "0.9.0"
