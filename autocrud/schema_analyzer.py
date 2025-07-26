"""
Schema analyzer for generating request/response models from full user schema
"""

from typing import (
    Type,
    Dict,
    Any,
    Optional,
    Union,
    get_type_hints,
    get_origin,
    get_args,
)
from dataclasses import fields, is_dataclass, MISSING
from pydantic import BaseModel, create_model

from .metadata import MetadataConfig


class SchemaAnalyzer:
    """Analyzes user-provided schemas and generates appropriate request/response models"""

    def __init__(
        self,
        model: Type,
        metadata_config: Optional[MetadataConfig] = None,
        default_values: Optional[Dict[str, Any]] = None,
    ):
        self.model = model
        self.metadata_config = metadata_config or MetadataConfig()
        self.default_values = default_values or {}
        self._analyze_model()
        self._validate_schema()

    def _analyze_model(self):
        """Analyze the user model to understand its structure"""
        if is_dataclass(self.model):
            self._analyze_dataclass()
        elif issubclass(self.model, BaseModel):
            self._analyze_pydantic()
        elif hasattr(self.model, "__annotations__") and hasattr(
            self.model, "__total__"
        ):
            # This is likely a TypedDict
            self._analyze_typeddict()
        else:
            raise ValueError(f"Unsupported model type: {type(self.model)}")

    def _analyze_typeddict(self):
        """Analyze TypedDict model"""
        self.model_fields = {}
        self.field_types = {}

        # TypedDict stores annotations in __annotations__
        for field_name, field_type in self.model.__annotations__.items():
            self.model_fields[field_name] = None  # No default values in TypedDict
            self.field_types[field_name] = field_type

        self.model_type = "typeddict"

    def _analyze_dataclass(self):
        """Analyze dataclass model"""
        self.model_fields = {}
        self.field_types = {}

        for field in fields(self.model):
            self.model_fields[field.name] = field
            self.field_types[field.name] = field.type

    def _analyze_pydantic(self):
        """Analyze Pydantic model"""
        # Use model_fields for Pydantic v2
        if hasattr(self.model, "model_fields"):
            self.model_fields = self.model.model_fields
        else:
            # Fallback for Pydantic v1
            self.model_fields = self.model.__fields__  # pragma: no cover
        self.field_types = get_type_hints(self.model)

    def _validate_schema(self):
        """Validate that the user model has all required fields"""
        # Check if ID field exists
        id_field = self.metadata_config.id_field
        if id_field not in self.field_types:
            raise ValueError(
                f"Model '{self.model.__name__}' must have an '{id_field}' field. "
                f"Please add '{id_field}' field to your model or configure a different id_field in MetadataConfig."
            )

        # Check metadata fields if enabled
        if self.metadata_config.enable_timestamps:
            if self.metadata_config.created_time_field not in self.field_types:
                raise ValueError(
                    f"Model '{self.model.__name__}' must have a '{self.metadata_config.created_time_field}' field "
                    f"when timestamps are enabled. Please add this field or disable timestamps."
                )
            if self.metadata_config.updated_time_field not in self.field_types:
                raise ValueError(
                    f"Model '{self.model.__name__}' must have a '{self.metadata_config.updated_time_field}' field "
                    f"when timestamps are enabled. Please add this field or disable timestamps."
                )

        if self.metadata_config.enable_user_tracking:
            if self.metadata_config.created_by_field not in self.field_types:
                raise ValueError(
                    f"Model '{self.model.__name__}' must have a '{self.metadata_config.created_by_field}' field "
                    f"when user tracking is enabled. Please add this field or disable user tracking."
                )
            if self.metadata_config.updated_by_field not in self.field_types:
                raise ValueError(
                    f"Model '{self.model.__name__}' must have a '{self.metadata_config.updated_by_field}' field "
                    f"when user tracking is enabled. Please add this field or disable user tracking."
                )

    def get_full_model(self) -> Type:
        """Get the full user model (includes all fields)"""
        return self.model

    def get_create_model(self) -> Type[BaseModel]:
        """Generate Pydantic model for create requests"""
        excluded_fields = self.metadata_config.get_create_excluded_fields()

        # Build field definitions for create model
        field_definitions = {}

        for field_name, field_type in self.field_types.items():
            if field_name in excluded_fields:
                continue

            # Handle optional created_by field
            if (
                field_name == self.metadata_config.created_by_field
                and self.metadata_config.enable_user_tracking
                and self.metadata_config.get_current_user() is not None
            ):
                # Make created_by optional if we can get it from context
                field_definitions[field_name] = (Optional[field_type], None)
            else:
                # Check if field is optional in original model
                if self._is_optional_field(field_name):
                    field_definitions[field_name] = (Optional[field_type], None)
                else:
                    field_definitions[field_name] = (field_type, ...)

        # Create the Pydantic model
        model_name = f"{self.model.__name__}CreateRequest"
        return create_model(model_name, **field_definitions)

    def get_update_model(self) -> Type[BaseModel]:
        """Generate Pydantic model for update requests"""
        excluded_fields = self.metadata_config.get_update_excluded_fields()

        # Build field definitions for update model
        field_definitions = {}

        for field_name, field_type in self.field_types.items():
            if field_name in excluded_fields:
                continue

            # Handle optional updated_by field
            if (
                field_name == self.metadata_config.updated_by_field
                and self.metadata_config.enable_user_tracking
                and self.metadata_config.get_current_user() is not None
            ):
                # Make updated_by optional if we can get it from context
                field_definitions[field_name] = (Optional[field_type], None)
            else:
                # All fields in update are optional (partial update)
                field_definitions[field_name] = (Optional[field_type], None)

        # Create the Pydantic model
        model_name = f"{self.model.__name__}UpdateRequest"
        return create_model(model_name, **field_definitions)

    def get_response_model(self) -> Type[BaseModel]:
        """Generate Pydantic model for responses (same as full model)"""
        # Build field definitions from full model
        field_definitions = {}

        for field_name, field_type in self.field_types.items():
            if self._is_optional_field(field_name):
                field_definitions[field_name] = (Optional[field_type], None)
            else:
                field_definitions[field_name] = (field_type, ...)

        # Create the Pydantic model
        model_name = f"{self.model.__name__}Response"
        return create_model(model_name, **field_definitions)

    def _is_optional_field(self, field_name: str) -> bool:
        """Check if a field is optional in the original model"""
        # Check if field has default value provided at registration time
        if field_name in self.default_values:
            return True

        if is_dataclass(self.model):
            for field in fields(self.model):
                if field.name == field_name:
                    # Check if field has default value or is Optional
                    if (
                        field.default is not MISSING
                        or field.default_factory is not MISSING
                    ):
                        return True
                    # Check if type is Optional
                    return self._is_optional_type(field.type)
        elif issubclass(self.model, BaseModel):
            # Use model_fields for Pydantic v2
            if hasattr(self.model, "model_fields"):
                field_info = self.model.model_fields.get(field_name)
                if field_info:
                    return not field_info.is_required()
            else:  # pragma: no cover
                # Fallback for Pydantic v1
                field_info = self.model.__fields__.get(field_name)
                if field_info:
                    return not field_info.required
        elif hasattr(self.model, "__annotations__") and hasattr(
            self.model, "__total__"
        ):
            # TypedDict: check if type is Optional or field has default value
            if field_name in self.model.__annotations__:
                field_type = self.model.__annotations__[field_name]
                return self._is_optional_type(field_type)

        return False

    def _is_optional_type(self, type_hint) -> bool:
        """Check if a type hint represents an Optional type"""
        origin = get_origin(type_hint)
        if origin is not None:
            args = get_args(type_hint)
            # Check for Union[X, None] or Optional[X] (which is Union[X, None])
            # Also handles X | None syntax in Python 3.10+
            if origin in (Union, type(Union)) and len(args) == 2 and type(None) in args:
                return True
            # Handle types.UnionType for X | None syntax (Python 3.10+)
            try:
                import types

                if hasattr(types, "UnionType") and origin is types.UnionType:
                    if len(args) == 2 and type(None) in args:
                        return True
            except ImportError:
                pass
        return False

    def prepare_create_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare data for creation by applying metadata"""
        return self.metadata_config.apply_create_metadata(data)

    def prepare_update_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare data for update by applying metadata"""
        return self.metadata_config.apply_update_metadata(data)

    def get_id_field_name(self) -> str:
        """Get the name of the ID field"""
        return self.metadata_config.id_field

    def extract_id_from_data(self, data: Dict[str, Any]) -> Any:
        """Extract ID value from data"""
        return data.get(self.metadata_config.id_field)

    def get_metadata_fields(self) -> Dict[str, bool]:
        """Get all metadata fields"""
        return self.metadata_config.get_metadata_fields()
