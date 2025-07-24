"""AutoCRUD - 自動化 CRUD 系統"""

from .core import SingleModelCRUD
from .multi_model import AutoCRUD
from .storage import MemoryStorage, DiskStorage, Storage
from .converter import ModelConverter
from .serializer import SerializerFactory
from .fastapi_generator import FastAPIGenerator
from .storage_factory import StorageFactory, DefaultStorageFactory

__version__ = "0.1.0"
__all__ = [
    "AutoCRUD",
    "SingleModelCRUD",
    "MemoryStorage",
    "DiskStorage",
    "Storage",
    "ModelConverter",
    "SerializerFactory",
    "FastAPIGenerator",
    "StorageFactory",
    "DefaultStorageFactory",
]
