"""Pydantic BaseModel → msgspec Struct conversion utilities.

This module handles converting Pydantic BaseModel types to msgspec Struct types,
including:
- Simple field mapping (str, int, float, bool, datetime, Optional, list, dict)
- Nested Pydantic BaseModel → recursive Struct conversion
- Pydantic discriminated unions → msgspec tagged unions
- Validator normalization (callable / IValidator / Pydantic model)

Supports both Pydantic v1 (1.x) and v2 (2.x).
"""

from collections.abc import Callable
from typing import Annotated, Any, Union, get_args, get_origin

import msgspec

from autocrud.types import IValidator

# ---------------------------------------------------------------------------
# Pydantic version detection
# ---------------------------------------------------------------------------

try:
    from pydantic import VERSION as _PYDANTIC_VERSION

    _PYDANTIC_V2 = int(_PYDANTIC_VERSION.split(".")[0]) >= 2
except Exception:  # pragma: no cover
    _PYDANTIC_V2 = False


def is_pydantic_model(obj: type) -> bool:
    """Check if a type is a Pydantic BaseModel subclass."""
    try:
        from pydantic import BaseModel

        return isinstance(obj, type) and issubclass(obj, BaseModel)
    except ImportError:
        return False


def pydantic_to_validator(pydantic_model: type) -> Callable:
    """Create a validator function from a Pydantic model class.

    Converts the data (a msgspec Struct) to a dict, then validates
    via Pydantic's ``model_validate`` (v2) or ``parse_obj`` (v1).
    """
    if _PYDANTIC_V2:

        def validate(data):
            d = msgspec.to_builtins(data)
            pydantic_model.model_validate(d)
    else:

        def validate(data):
            d = msgspec.to_builtins(data)
            pydantic_model.parse_obj(d)

    return validate


def pydantic_to_struct(pydantic_model: type) -> type:
    """Auto-generate a msgspec Struct from a Pydantic BaseModel.

    This allows users to pass a Pydantic model to ``add_model()``
    and have the system auto-generate the internal Struct type while
    using Pydantic only for validation.

    Handles common types: str, int, float, bool, datetime, Optional, list, dict.
    Nested Pydantic BaseModel fields are recursively converted to Structs.
    Pydantic discriminated unions are converted to msgspec tagged unions.
    """
    from pydantic import BaseModel

    if not (isinstance(pydantic_model, type) and issubclass(pydantic_model, BaseModel)):
        raise TypeError(f"Expected a Pydantic BaseModel, got {pydantic_model}")

    # Reject RootModel — it's not a standard field-based model
    try:
        from pydantic import RootModel

        if issubclass(pydantic_model, RootModel):
            raise TypeError(
                f"RootModel is not supported by pydantic_to_struct. "
                f"Got: {pydantic_model}"
            )
    except ImportError:
        pass

    # Cache to avoid converting the same model twice (handles shared/circular refs)
    cache: dict[type, type] = {}
    return _pydantic_to_struct_recursive(pydantic_model, cache)


def build_validator(
    validator: "Callable | IValidator | type | None",
) -> "Callable | None":
    """Normalize the validator argument into a callable or None.

    Supports:
    - None → no validation
    - Callable → used directly
    - IValidator instance → calls .validate()
    - Pydantic BaseModel class → wraps model_validate
    """
    if validator is None:
        return None

    if isinstance(validator, IValidator):
        return validator.validate

    if is_pydantic_model(validator):
        return pydantic_to_validator(validator)

    if callable(validator):
        return validator

    raise TypeError(
        f"validator must be a callable, IValidator instance, or Pydantic BaseModel class. "
        f"Got: {type(validator)}"
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _iter_model_fields(
    pydantic_model: type,
) -> list[tuple[str, Any, bool, Any, "str | None"]]:
    """Iterate model fields with a unified interface for Pydantic v1 and v2.

    Returns a list of ``(field_name, annotation, is_required, default, discriminator)``.

    - **v2**: Uses ``model.model_fields`` → ``FieldInfo``.
    - **v1**: Uses ``model.__fields__`` → ``ModelField``.
    """
    result: list[tuple[str, Any, bool, Any, str | None]] = []
    if _PYDANTIC_V2:
        for name, fi in pydantic_model.model_fields.items():
            annotation = fi.annotation
            # Pydantic v2 strips top-level Annotated metadata (e.g. Ref,
            # DisplayName, RefRevision) into fi.metadata while fi.annotation
            # only contains the bare type.  Reconstruct Annotated[] so that
            # downstream code (extract_refs, extract_display_name) can
            # discover the metadata on the resulting Struct type hints.
            if fi.metadata:
                annotation = Annotated[tuple([annotation, *fi.metadata])]
            result.append(
                (name, annotation, fi.is_required(), fi.default, fi.discriminator)
            )
    else:
        for name, mf in pydantic_model.__fields__.items():
            # v1 ModelField: outer_type_ preserves generics but strips Optional;
            # annotation preserves the raw annotation including Optional.
            annotation = mf.outer_type_
            # Reconstruct Optional if the field allows None but outer_type_
            # already stripped it.
            if mf.allow_none and get_origin(annotation) is not Union:
                annotation = Union[annotation, type(None)]
            result.append(
                (
                    name,
                    annotation,
                    mf.required,
                    mf.default,
                    getattr(mf, "discriminator_key", None),
                )
            )
    return result


def _get_field_annotation(
    pydantic_model: type, field_name: str
) -> "tuple[Any, Any] | None":
    """Get (annotation, default) for a single field — v1/v2 compatible.

    Returns ``None`` if the field does not exist on the model.
    """
    if _PYDANTIC_V2:
        fi = pydantic_model.model_fields.get(field_name)
        if fi is None:
            return None
        return fi.annotation, fi.default
    else:
        mf = pydantic_model.__fields__.get(field_name)
        if mf is None:
            return None
        return mf.outer_type_, mf.default


def _convert_annotation(annotation: Any, cache: dict) -> Any:
    """Recursively convert type annotations, replacing Pydantic models with Structs.

    Handles: direct BaseModel, Optional[BaseModel], list[BaseModel],
    dict[str, BaseModel], Union types containing BaseModel, and
    Pydantic discriminated unions (converted to msgspec tagged unions).
    """

    from pydantic import BaseModel

    # Direct Pydantic model reference
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _pydantic_to_struct_recursive(annotation, cache)

    # Handle Annotated types first (get_origin is needed; __origin__ is unreliable)
    real_origin = get_origin(annotation)
    if real_origin is Annotated:
        args = get_args(annotation)
        if len(args) >= 2:
            inner_type = args[0]
            metadata = args[1:]
            # Check if any metadata is a Pydantic FieldInfo with discriminator
            discriminator = _extract_discriminator(metadata)
            if discriminator is not None:
                return _convert_discriminated_union(inner_type, discriminator, cache)
            # No discriminator — just convert the inner type
            converted_inner = _convert_annotation(inner_type, cache)
            if converted_inner is inner_type:
                return annotation
            return Annotated[tuple([converted_inner, *metadata])]
        return annotation  # pragma: no cover

    # Handle generic types: list[X], dict[K, V], Optional[X], Union[X, Y]
    origin = real_origin or getattr(annotation, "__origin__", None)
    if origin is not None:
        args = getattr(annotation, "__args__", ())
        if not args:
            return annotation

        converted_args = tuple(_convert_annotation(a, cache) for a in args)
        if converted_args == args:
            return annotation  # No change needed

        # Reconstruct the generic type with converted args
        # For Union types (including Optional), use typing.Union
        if origin is Union:
            return Union[converted_args]
        return origin[converted_args]

    return annotation


def _extract_discriminator(metadata: tuple) -> "str | None":
    """Extract discriminator field name from Pydantic FieldInfo metadata."""
    try:
        from pydantic.fields import FieldInfo

        for item in metadata:
            if isinstance(item, FieldInfo) and item.discriminator is not None:
                return item.discriminator
    except ImportError:
        pass
    return None


def _convert_discriminated_union(
    union_type: Any, discriminator: str, cache: dict
) -> Any:
    """Convert a Pydantic discriminated union to a msgspec tagged union.

    Each union member must have a ``Literal[value]`` field matching the
    discriminator name. The Literal value becomes the ``tag`` and the
    discriminator field name becomes the ``tag_field`` for each generated
    msgspec Struct.
    """
    from pydantic import BaseModel

    args = get_args(union_type)
    if not args:
        return _convert_annotation(union_type, cache)

    # Separate None from real union members (for Optional discriminated unions)
    none_included = type(None) in args
    model_args = [a for a in args if a is not type(None)]

    converted_members = []
    for member in model_args:
        if isinstance(member, type) and issubclass(member, BaseModel):
            converted = _pydantic_to_struct_tagged(member, discriminator, cache)
            converted_members.append(converted)
        else:
            converted_members.append(_convert_annotation(member, cache))

    if none_included:
        return Union[tuple([*converted_members, type(None)])]
    return Union[tuple(converted_members)]


def _pydantic_to_struct_tagged(
    pydantic_model: type, tag_field: str, cache: dict
) -> type:
    """Convert a Pydantic BaseModel to a tagged msgspec Struct for discriminated unions.

    The ``tag_field`` is the discriminator field name. The ``tag`` value is
    extracted from the model's ``Literal[value]`` annotation on that field.
    The discriminator field itself is excluded from struct fields since msgspec
    handles it via the tag mechanism.
    """
    if pydantic_model in cache:
        return cache[pydantic_model]

    # Extract the tag value from the Literal annotation on the discriminator field
    info = _get_field_annotation(pydantic_model, tag_field)
    if info is None:
        raise TypeError(
            f"Discriminator field '{tag_field}' not found in {pydantic_model.__name__}"
        )

    tag_annotation, _tag_default = info
    literal_args = get_args(tag_annotation)
    if not literal_args:
        raise TypeError(
            f"Discriminator field '{tag_field}' in {pydantic_model.__name__} "
            f"must be a Literal type, got {tag_annotation}"
        )
    tag_value = literal_args[0]  # e.g. "cat" from Literal["cat"]

    # Build fields, excluding the discriminator field (handled by tag mechanism)
    fields: list[tuple[str, type, Any]] = []
    for field_name, annotation, is_required, default, _disc in _iter_model_fields(
        pydantic_model
    ):
        if field_name == tag_field:
            continue  # Skip discriminator field
        annotation = _convert_annotation(annotation, cache)
        if is_required:
            fields.append((field_name, annotation, msgspec.NODEFAULT))
        elif default is not None:
            fields.append((field_name, annotation, default))
        else:
            fields.append((field_name, annotation, None))

    struct_fields = []
    for name, ann, default in fields:
        if default is msgspec.NODEFAULT:
            struct_fields.append((name, ann))
        else:
            struct_fields.append((name, ann, default))

    result = msgspec.defstruct(
        pydantic_model.__name__,
        struct_fields,
        kw_only=True,
        tag_field=tag_field,
        tag=tag_value,
    )
    cache[pydantic_model] = result
    return result


def _pydantic_to_struct_recursive(pydantic_model: type, cache: dict) -> type:
    """Internal recursive implementation of pydantic_to_struct."""
    if pydantic_model in cache:
        return cache[pydantic_model]

    fields: list[tuple[str, type, Any]] = []
    for (
        field_name,
        annotation,
        is_required,
        default,
        discriminator,
    ) in _iter_model_fields(pydantic_model):
        # Check if this field has a discriminator (discriminated union)
        if discriminator is not None:
            annotation = _convert_discriminated_union(annotation, discriminator, cache)
        else:
            annotation = _convert_annotation(annotation, cache)
        if is_required:
            # Required field, no default
            fields.append((field_name, annotation, msgspec.NODEFAULT))
        elif default is not None:
            fields.append((field_name, annotation, default))
        else:
            # Optional field with default=None (e.g. Optional[str] = None)
            fields.append((field_name, annotation, None))

    # Build struct dynamically
    struct_fields = []
    for name, ann, default in fields:
        if default is msgspec.NODEFAULT:
            struct_fields.append((name, ann))
        else:
            struct_fields.append((name, ann, default))

    result = msgspec.defstruct(pydantic_model.__name__, struct_fields, kw_only=True)
    cache[pydantic_model] = result
    return result
