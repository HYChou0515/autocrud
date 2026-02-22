from autocrud.crud.core import AutoCRUD
from autocrud.schema import Schema
from autocrud.types import (
    DisplayName,
    IValidator,
    OnDelete,
    Ref,
    RefRevision,
    SearchedResource,
    ValidationError,
)

# Global instance for simplified usage pattern
# Users can import and use this directly: `from autocrud import crud`
# Configure it at application startup: `crud.configure(storage_factory=...)`
crud = AutoCRUD()

__all__ = [
    "AutoCRUD",
    "DisplayName",
    "IValidator",
    "OnDelete",
    "Ref",
    "RefRevision",
    "Schema",
    "SearchedResource",
    "ValidationError",
    "crud",
]
__version__ = "0.8.2"
