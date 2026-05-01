"""Public exception facade for SpecStar."""

from specstar.types import (
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
