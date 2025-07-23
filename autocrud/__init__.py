"""AutoCRUD - 自動化 CRUD 系統"""

from .core import AutoCRUD
from .multi_model import MultiModelAutoCRUD
from .storage import MemoryStorage, DiskStorage, Storage
from .converter import ModelConverter
from .serializer import SerializerFactory
from .fastapi_generator import FastAPIGenerator

__version__ = "0.1.0"
__all__ = [
    "AutoCRUD",
    "MultiModelAutoCRUD",
    "MemoryStorage",
    "DiskStorage",
    "Storage",
    "ModelConverter",
    "SerializerFactory",
    "FastAPIGenerator",
]
