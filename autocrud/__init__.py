from autocrud.crud.core import AutoCRUD
from autocrud.types import (
    DisplayName,
    IValidator,
    OnDelete,
    Ref,
    RefRevision,
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
    "ValidationError",
    "crud",
]
__version__ = "0.8.0"
