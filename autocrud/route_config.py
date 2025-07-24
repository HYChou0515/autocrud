"""
Route configuration system for controlling which CRUD routes to enable.
"""

from typing import Dict
from dataclasses import dataclass


@dataclass
class RouteConfig:
    """Configuration for CRUD route generation"""

    # Basic CRUD operations
    create: bool = True
    get: bool = True
    update: bool = True
    delete: bool = True
    list: bool = True

    # Additional operations
    count: bool = True

    # Future extensions can be added here
    # bulk_create: bool = False
    # bulk_update: bool = False
    # bulk_delete: bool = False

    @classmethod
    def all_enabled(cls) -> "RouteConfig":
        """Create config with all routes enabled"""
        return cls(
            create=True, get=True, update=True, delete=True, list=True, count=True
        )

    @classmethod
    def all_disabled(cls) -> "RouteConfig":
        """Create config with all routes disabled"""
        return cls(
            create=False, get=False, update=False, delete=False, list=False, count=False
        )

    @classmethod
    def read_only(cls) -> "RouteConfig":
        """Create config with only read operations enabled"""
        return cls(
            create=False, update=False, delete=False, get=True, list=True, count=True
        )

    @classmethod
    def write_only(cls) -> "RouteConfig":
        """Create config with only write operations enabled"""
        return cls(
            create=True, update=True, delete=True, get=False, list=False, count=False
        )

    @classmethod
    def basic_crud(cls) -> "RouteConfig":
        """Create config with basic CRUD operations only (no count)"""
        return cls(count=False)

    def to_dict(self) -> Dict[str, bool]:
        """Convert to dictionary"""
        return {
            "create": self.create,
            "get": self.get,
            "update": self.update,
            "delete": self.delete,
            "list": self.list,
            "count": self.count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, bool]) -> "RouteConfig":
        """Create from dictionary"""
        return cls(**data)

    def __str__(self) -> str:
        """String representation"""
        enabled_routes = [name for name, enabled in self.to_dict().items() if enabled]
        return f"RouteConfig(enabled: {enabled_routes})"
