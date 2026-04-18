"""Public exception facade for AutoCRUD."""

from autocrud.types import (
    DuplicateResourceError,
    MissingOperationContextError,
    PermissionDeniedError,
    ResourceConflictError,
    ResourceIDNotFoundError,
    ResourceIsDeletedError,
    ResourceNotFoundError,
    RevisionIDNotFoundError,
    RevisionNotFoundError,
    RevisionNotMigratedError,
    SchemaConflictError,
    UniqueConstraintError,
    ValidationError,
)

__all__ = [
    "DuplicateResourceError",
    "MissingOperationContextError",
    "PermissionDeniedError",
    "ResourceConflictError",
    "ResourceIDNotFoundError",
    "ResourceIsDeletedError",
    "ResourceNotFoundError",
    "RevisionIDNotFoundError",
    "RevisionNotFoundError",
    "RevisionNotMigratedError",
    "SchemaConflictError",
    "UniqueConstraintError",
    "ValidationError",
]
