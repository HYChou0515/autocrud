"""Public exception facade for AutoCRUD."""

from autocrud.types import (
    CannotModifyResourceError,
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
    "CannotModifyResourceError",
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
