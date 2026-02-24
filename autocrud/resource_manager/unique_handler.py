"""
UniqueConstraintChecker — unique-field enforcement as an :class:`IConstraintChecker`.

This module provides:

* :class:`UniqueConstraintChecker` — implements the ``IConstraintChecker``
  interface.  It checks that every ``Unique``-annotated field value is not
  already used by another non-deleted resource.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, get_args, get_origin, get_type_hints

from msgspec import UNSET

from autocrud.types import (
    DataSearchCondition,
    DataSearchOperator,
    IConstraintChecker,
    IndexableField,
    ResourceMeta,
    ResourceMetaSearchQuery,
    ResourceMetaSearchSort,
    ResourceMetaSortDirection,
    ResourceMetaSortKey,
    UniqueConstraintError,
    extract_unique_fields,
)

if TYPE_CHECKING:
    from autocrud.resource_manager.core import ResourceManager


def _infer_raw_type(model: type, field_name: str) -> Any:
    """Infer the raw (non-Annotated) type of *field_name* on *model*.

    Returns the unwrapped type for ``Annotated[T, ...]`` or the raw hint.
    Falls back to :data:`msgspec.UNSET` when resolution fails.
    """
    try:
        hints = get_type_hints(model, include_extras=True)
        hint = hints.get(field_name)
        if hint is not None and get_origin(hint) is Annotated:
            return get_args(hint)[0]
        if hint is not None:
            return hint
    except Exception:
        pass
    return UNSET


class UniqueConstraintChecker(IConstraintChecker):
    """Checks that unique-annotated fields are not duplicated.

    The checker **owns** the list of unique fields.  When *unique_fields* is
    not given explicitly it is auto-detected from the model's ``Unique``
    annotations.  It also ensures every unique field is present in the
    :class:`ResourceManager`'s indexed fields (auto-adding if missing).

    Args:
        rm: The owning :class:`ResourceManager` (needed to query storage).
        unique_fields: Explicit list of field names to enforce uniqueness on.
            When ``None`` (the default) the fields are auto-detected from
            ``Unique`` annotations on the model.
    """

    def __init__(
        self,
        rm: ResourceManager,
        unique_fields: list[str] | None = None,
    ) -> None:
        self.rm: ResourceManager = rm
        self._unique_fields: list[str] = (
            list(unique_fields)
            if unique_fields is not None
            else extract_unique_fields(rm.resource_type)
        )
        # Auto-ensure every unique field is indexed.
        self._ensure_indexed()

    @property
    def unique_fields(self) -> list[str]:
        """The list of field names enforced by this checker."""
        return self._unique_fields

    # -- internal helpers ----------------------------------------------------

    def _ensure_indexed(self) -> None:
        """Add unique fields to RM's indexed fields if not already present."""
        for field_name in self._unique_fields:
            raw_type = _infer_raw_type(self.rm.resource_type, field_name)
            self.rm.add_indexed_field(
                IndexableField(field_path=field_name, field_type=raw_type)
            )

    # -- IConstraintChecker --------------------------------------------------

    def check(
        self,
        data: Any,
        *,
        exclude_resource_id: str | None = None,
    ) -> None:
        """Raise :class:`UniqueConstraintError` if any unique-annotated field
        value is already used by another (non-deleted) resource.
        """
        if not self._unique_fields:
            return
        for field_path in self._unique_fields:
            value = getattr(data, field_path, None)
            if value is None:
                continue
            query = ResourceMetaSearchQuery(
                conditions=[
                    DataSearchCondition(
                        field_path=field_path,
                        operator=DataSearchOperator.equals,
                        value=value,
                    )
                ],
                is_deleted=False,
                limit=1,
                sorts=[
                    ResourceMetaSearchSort(
                        key=ResourceMetaSortKey.updated_time,
                        direction=ResourceMetaSortDirection.ascending,
                    )
                ],
            )
            matches: list[ResourceMeta] = self.rm.storage.search(query)
            if not matches:
                continue
            first: ResourceMeta = matches[0]
            if (
                exclude_resource_id is not None
                and first.resource_id == exclude_resource_id
            ):
                continue  # this resource is the earliest owner — no conflict
            raise UniqueConstraintError(field_path, value, first.resource_id)

    def data_relevant_changed(self, current_data: Any, new_data: Any) -> bool:
        """Return ``True`` if any unique-constrained field value differs."""
        if not self._unique_fields:
            return False
        return any(
            getattr(new_data, f, None) != getattr(current_data, f, None)
            for f in self._unique_fields
        )
