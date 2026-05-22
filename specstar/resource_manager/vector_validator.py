"""Write-time dimension validation for Vector / Embedding fields."""

from __future__ import annotations

from typing import Any, Callable

from msgspec import UNSET

from specstar.types import IValidator, ValidationError, extract_vector_field_infos


class CompositeValidator(IValidator):
    """Chain multiple validators; runs each in order, stops on first raise."""

    def __init__(self, validators: list[IValidator | Callable]) -> None:
        self._validators = validators

    def validate(self, data: Any) -> None:
        for v in self._validators:
            if isinstance(v, IValidator):
                v.validate(data)
            else:
                v(data)


class VectorDimValidator(IValidator):
    """Validate that vector-typed fields match their annotated dim."""

    def __init__(self, struct_type: type) -> None:
        self._infos = extract_vector_field_infos(struct_type)

    def validate(self, data: Any) -> None:
        for info in self._infos:
            value = getattr(data, info.name, None)
            if value is None and info.nullable:
                continue
            if info.is_embedding:
                vector = getattr(value, "vector", UNSET)
                if vector is UNSET:
                    # processor will fill in
                    continue
                actual_len = len(vector)
            else:
                actual_len = len(value)
            if actual_len != info.marker.dim:
                raise ValidationError(
                    f"Vector field {info.name!r}: expected dim={info.marker.dim}, "
                    f"got {actual_len}"
                )
