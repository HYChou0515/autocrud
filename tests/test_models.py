"""
Common test models with proper ID fields for all tests.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    id: str
    name: str
    email: Optional[str] = None
    age: Optional[int] = None


@dataclass
class Product:
    id: str
    name: str
    price: float
    description: Optional[str] = None
    category: Optional[str] = None


@dataclass
class Item:
    id: str
    name: str
    value: int


@dataclass
class Book:
    id: str
    title: str
    author: str
    isbn: Optional[str] = None
    price: Optional[float] = None
    published_year: Optional[int] = None


@dataclass
class Cat:
    id: str
    name: str
    breed: str


@dataclass
class UserProfile:
    id: str
    name: str
    bio: str


@dataclass
class ProductCategory:
    id: str
    name: str
    description: str


@dataclass
class Company:
    id: str
    name: str
    industry: str


@dataclass
class ComplexUser:
    id: str
    name: str
    tags: list = None
    metadata: dict = None
    email: Optional[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.metadata is None:
            self.metadata = {}


# Pydantic models for specific tests
try:
    from pydantic import BaseModel

    class PydanticUser(BaseModel):
        id: str
        name: str
        email: str
        age: Optional[int] = None

    class PydanticProduct(BaseModel):
        id: str
        name: str
        price: float
        description: Optional[str] = None

except ImportError:
    # Pydantic not available
    PydanticUser = None
    PydanticProduct = None


# Dataclass versions for converter tests
@dataclass
class DataclassUser:
    id: str
    name: str
    email: str
    age: Optional[int] = None
