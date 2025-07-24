"""
Metadata field configuration system for AutoCRUD
"""

from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
import datetime


@dataclass
class MetadataConfig:
    """Configuration for metadata fields in CRUD operations"""

    # Primary key configuration
    id_field: str = "id"

    # Timestamp fields
    enable_timestamps: bool = False
    created_time_field: Optional[str] = "created_time"
    updated_time_field: Optional[str] = "updated_time"

    # User tracking fields
    enable_user_tracking: bool = False
    created_by_field: Optional[str] = "created_by"
    updated_by_field: Optional[str] = "updated_by"

    # Functions to get current user/time
    get_current_time: Optional[Callable[[], Any]] = None
    get_current_user: Optional[Callable[[], Any]] = None

    def __post_init__(self):
        """Set default functions if not provided"""
        if self.get_current_time is None:
            self.get_current_time = lambda: datetime.datetime.now(
                datetime.UTC
            ).isoformat()

        if self.get_current_user is None:
            self.get_current_user = lambda: None  # Default to None, can be overridden

    @classmethod
    def with_timestamps(
        cls,
        created_time_field: str = "created_time",
        updated_time_field: str = "updated_time",
        get_current_time: Optional[Callable[[], Any]] = None,
        **kwargs,
    ) -> "MetadataConfig":
        """Create config with timestamp tracking enabled"""
        return cls(
            enable_timestamps=True,
            created_time_field=created_time_field,
            updated_time_field=updated_time_field,
            get_current_time=get_current_time,
            **kwargs,
        )

    @classmethod
    def with_user_tracking(
        cls,
        created_by_field: str = "created_by",
        updated_by_field: str = "updated_by",
        get_current_user: Optional[Callable[[], Any]] = None,
        **kwargs,
    ) -> "MetadataConfig":
        """Create config with user tracking enabled"""
        return cls(
            enable_user_tracking=True,
            created_by_field=created_by_field,
            updated_by_field=updated_by_field,
            get_current_user=get_current_user,
            **kwargs,
        )

    @classmethod
    def with_full_tracking(
        cls,
        created_time_field: str = "created_time",
        updated_time_field: str = "updated_time",
        created_by_field: str = "created_by",
        updated_by_field: str = "updated_by",
        get_current_time: Optional[Callable[[], Any]] = None,
        get_current_user: Optional[Callable[[], Any]] = None,
        **kwargs,
    ) -> "MetadataConfig":
        """Create config with both timestamp and user tracking enabled"""
        return cls(
            enable_timestamps=True,
            enable_user_tracking=True,
            created_time_field=created_time_field,
            updated_time_field=updated_time_field,
            created_by_field=created_by_field,
            updated_by_field=updated_by_field,
            get_current_time=get_current_time,
            get_current_user=get_current_user,
            **kwargs,
        )

    def get_metadata_fields(self) -> Dict[str, bool]:
        """Get all metadata field names and their enabled status"""
        fields = {self.id_field: True}  # ID is always present

        if self.enable_timestamps:
            if self.created_time_field:
                fields[self.created_time_field] = True
            if self.updated_time_field:
                fields[self.updated_time_field] = True

        if self.enable_user_tracking:
            if self.created_by_field:
                fields[self.created_by_field] = True
            if self.updated_by_field:
                fields[self.updated_by_field] = True

        return fields

    def get_create_excluded_fields(self) -> set[str]:
        """Get fields that should be excluded from create request body"""
        excluded = {self.id_field}  # ID is auto-generated

        if self.enable_timestamps:
            if self.created_time_field:
                excluded.add(self.created_time_field)
            if self.updated_time_field:
                excluded.add(self.updated_time_field)

        # created_by might be optional in create body if get_current_user is provided
        if self.enable_user_tracking and self.updated_by_field:
            excluded.add(self.updated_by_field)  # updated_by not needed in create

        return excluded

    def get_update_excluded_fields(self) -> set[str]:
        """Get fields that should be excluded from update request body"""
        excluded = {self.id_field}  # ID cannot be updated

        if self.enable_timestamps:
            if self.created_time_field:
                excluded.add(self.created_time_field)  # created_time cannot be updated
            if self.updated_time_field:
                excluded.add(self.updated_time_field)  # updated_time is auto-set

        if self.enable_user_tracking:
            if self.created_by_field:
                excluded.add(self.created_by_field)  # created_by cannot be updated
            # updated_by might be optional in update body if get_current_user is provided

        return excluded

    def apply_create_metadata(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply metadata to create data"""
        result = data.copy()

        if self.enable_timestamps:
            current_time = self.get_current_time()
            if self.created_time_field:
                result[self.created_time_field] = current_time
            if self.updated_time_field:
                result[self.updated_time_field] = current_time

        if self.enable_user_tracking:
            current_user = self.get_current_user()
            if current_user is not None:
                if self.created_by_field:
                    result[self.created_by_field] = current_user
                if self.updated_by_field:
                    result[self.updated_by_field] = current_user

        return result

    def apply_update_metadata(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply metadata to update data"""
        result = data.copy()

        if self.enable_timestamps and self.updated_time_field:
            result[self.updated_time_field] = self.get_current_time()

        if self.enable_user_tracking and self.updated_by_field:
            current_user = self.get_current_user()
            if current_user is not None:
                result[self.updated_by_field] = current_user

        return result
