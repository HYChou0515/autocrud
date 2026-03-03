from autocrud.crud.core import AutoCRUD
from autocrud.resource_manager.pydantic_converter import struct_to_pydantic
from autocrud.schema import Schema
from autocrud.types import (
    DisplayName,
    IConstraintChecker,
    IValidator,
    OnDelete,
    Ref,
    RefRevision,
    RefType,
    SearchedResource,
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
    "DisplayName",
    "IConstraintChecker",
    "IValidator",
    "OnDelete",
    "Ref",
    "RefRevision",
    "RefType",
    "Schema",
    "SearchedResource",
    "Unique",
    "UniqueConstraintError",
    "ValidationError",
    "crud",
    "struct_to_pydantic",
]
__version__ = "0.8.3a7"
