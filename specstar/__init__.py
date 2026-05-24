from specstar import defaults, id_generators
from specstar.backend import (
    BackendBinding,
    BackendConfig,
    BackendDefaults,
    ConnectionProfile,
    register_backend_provider,
)
from specstar.crud.core import LoadStats, SpecStar
from specstar.env import env
from specstar.query import QB
from specstar.refs import string_ref
from specstar.resource_manager.pydantic_converter import (
    pydantic_to_struct,
    struct_to_pydantic,
)
from specstar.schema import Schema
from specstar.types import (
    BackgroundTaskAccepted,
    BlobUploadSession,
    DisplayName,
    Embedding,
    IConstraintChecker,
    IValidator,
    Job,
    JobRedirectInfo,
    MergePatch,
    OnDecodeError,
    OnDelete,
    OnDuplicate,
    OnUnindexedQuery,
    Ref,
    RefRevision,
    RefType,
    SearchedResource,
    TaskStatus,
    UndecodableData,
    Unique,
    ValidationError,
    Vector,
)

# Global instance for simplified usage pattern
# Users can import and use this directly: from specstar import spec
# Configure it at application startup via spec.configure(backend=...) or
# the legacy split parameters during the transition window.
spec = SpecStar()

__all__ = [
    "BackendBinding",
    "BackendConfig",
    "BackendDefaults",
    "BackgroundTaskAccepted",
    "BlobUploadSession",
    "ConnectionProfile",
    "DisplayName",
    "Embedding",
    "IConstraintChecker",
    "IValidator",
    "Job",
    "JobRedirectInfo",
    "LoadStats",
    "MergePatch",
    "OnDecodeError",
    "OnDelete",
    "OnDuplicate",
    "OnUnindexedQuery",
    "QB",
    "Ref",
    "RefRevision",
    "RefType",
    "Schema",
    "SearchedResource",
    "SpecStar",
    "TaskStatus",
    "UndecodableData",
    "Unique",
    "ValidationError",
    "Vector",
    "spec",
    "env",
    "string_ref",
    "defaults",
    "id_generators",
    "register_backend_provider",
    "pydantic_to_struct",
    "struct_to_pydantic",
]
__version__ = "0.11.3"
