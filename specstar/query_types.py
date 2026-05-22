from __future__ import annotations

import datetime as dt
import os
import warnings
from enum import StrEnum
from typing import Any, Literal

from msgspec import UNSET, Struct, UnsetType


class DataSearchOperator(StrEnum):
    equals = "eq"
    not_equals = "ne"
    greater_than = "gt"
    greater_than_or_equal = "gte"
    less_than = "lt"
    less_than_or_equal = "lte"
    contains = "contains"  # For string fields
    starts_with = "starts_with"  # For string fields
    ends_with = "ends_with"  # For string fields
    in_list = "in"
    not_in_list = "not_in"
    is_null = "is_null"
    exists = "exists"
    isna = "isna"
    regex = "regex"


class FieldTransform(StrEnum):
    """Field transformation functions that can be applied before comparison."""

    length = "len"  # Get length of string, list, dict, etc.


class DataSearchCondition(Struct, kw_only=True, tag=True):
    field_path: str
    operator: DataSearchOperator
    value: Any
    transform: FieldTransform | None = None  # Optional field transformation


class DataSearchLogicOperator(StrEnum):
    and_op = "and"
    or_op = "or"
    not_op = "not"


class DataSearchGroup(Struct, kw_only=True, tag=True):
    operator: DataSearchLogicOperator
    conditions: list["DataSearchCondition | DataSearchGroup"]


class VectorDistanceCondition(Struct, kw_only=True, tag=True):
    """Filter rows by the distance between a Vector field and a query vector.

    Belongs in :attr:`ResourceMetaSearchQuery.conditions` alongside
    :class:`DataSearchCondition` and :class:`DataSearchGroup`.
    """

    field_path: str
    query_vector: list[float] | str
    operator: DataSearchOperator
    threshold: float
    distance: "Literal['cosine', 'l2', 'ip'] | None" = None


DataSearchFilter = DataSearchCondition | DataSearchGroup | VectorDistanceCondition


class ResourceMetaSortDirection(StrEnum):
    ascending = "+"
    descending = "-"


class ResourceDataSearchSort(Struct, kw_only=True, tag=True):
    direction: ResourceMetaSortDirection = ResourceMetaSortDirection.ascending
    field_path: str


class ResourceMetaSortKey(StrEnum):
    """Built-in metadata sort keys supported by QB and search APIs."""

    created_time = "created_time"
    updated_time = "updated_time"
    resource_id = "resource_id"
    current_revision_id = "current_revision_id"
    created_by = "created_by"
    updated_by = "updated_by"
    is_deleted = "is_deleted"
    schema_version = "schema_version"
    total_revision_count = "total_revision_count"
    rev_created_time = "rev_created_time"
    rev_updated_time = "rev_updated_time"


class ResourceMetaSearchSort(Struct, kw_only=True, tag=True):
    direction: ResourceMetaSortDirection = ResourceMetaSortDirection.ascending
    key: ResourceMetaSortKey


class VectorDistanceSort(Struct, kw_only=True, tag=True):
    """Sort rows by the distance between a Vector field and a query vector.

    Belongs in :attr:`ResourceMetaSearchQuery.sorts` alongside
    :class:`ResourceMetaSearchSort` and :class:`ResourceDataSearchSort`.
    """

    field_path: str
    query_vector: list[float] | str
    direction: ResourceMetaSortDirection = ResourceMetaSortDirection.ascending
    distance: "Literal['cosine', 'l2', 'ip'] | None" = None


DEFAULT_QUERY_LIMIT_ENV_VAR = "SPECSTAR_DEFAULT_QUERY_LIMIT"
DEFAULT_QUERY_LIMIT_LEGACY_ENV_VAR = "AUTOCRUD_DEFAULT_QUERY_LIMIT"
DEFAULT_QUERY_LIMIT_FALLBACK = 2**32 - 1


def _read_default_query_limit() -> int:
    """Read the startup default query limit from the environment.

    Prefers ``SPECSTAR_DEFAULT_QUERY_LIMIT``; falls back to the legacy
    ``AUTOCRUD_DEFAULT_QUERY_LIMIT`` (with a one-shot DeprecationWarning) for
    deployments that have not yet migrated their environment.

    The value is intentionally configurable so operators can decide whether
    list endpoints should behave more like a small page or an effectively
    unbounded first page in their deployment.
    """

    raw = os.getenv(DEFAULT_QUERY_LIMIT_ENV_VAR)
    source = DEFAULT_QUERY_LIMIT_ENV_VAR
    if raw is None or raw.strip() == "":
        legacy = os.getenv(DEFAULT_QUERY_LIMIT_LEGACY_ENV_VAR)
        if legacy is not None and legacy.strip() != "":
            warnings.warn(
                (
                    f"{DEFAULT_QUERY_LIMIT_LEGACY_ENV_VAR} is deprecated; "
                    f"set {DEFAULT_QUERY_LIMIT_ENV_VAR} instead."
                ),
                DeprecationWarning,
                stacklevel=2,
            )
            raw = legacy
            source = DEFAULT_QUERY_LIMIT_LEGACY_ENV_VAR
        else:
            return DEFAULT_QUERY_LIMIT_FALLBACK

    try:
        value = int(raw)
    except ValueError:
        warnings.warn(
            (
                f"Invalid {source}={raw!r}; "
                f"falling back to {DEFAULT_QUERY_LIMIT_FALLBACK}."
            ),
            RuntimeWarning,
            stacklevel=2,
        )
        return DEFAULT_QUERY_LIMIT_FALLBACK

    if value < 1:
        warnings.warn(
            (
                f"{source} must be >= 1, got {value}; "
                f"falling back to {DEFAULT_QUERY_LIMIT_FALLBACK}."
            ),
            RuntimeWarning,
            stacklevel=2,
        )
        return DEFAULT_QUERY_LIMIT_FALLBACK

    return value


DEFAULT_QUERY_LIMIT = _read_default_query_limit()
"""Default page size for list-style search endpoints.

Configurable at process startup through the ``SPECSTAR_DEFAULT_QUERY_LIMIT``
environment variable (legacy ``AUTOCRUD_DEFAULT_QUERY_LIMIT`` is still read
with a DeprecationWarning during the migration window). Falls back to a very
large first-page limit so users do not easily mistake pagination for missing
data.
"""


class ResourceMetaSearchQuery(Struct, kw_only=True):
    is_deleted: bool | UnsetType = UNSET
    """Filter by deletion status of the resource."""

    created_time_start: dt.datetime | UnsetType = UNSET
    """Filter resources created >= this time."""
    created_time_end: dt.datetime | UnsetType = UNSET
    """Filter resources created <= this time."""
    updated_time_start: dt.datetime | UnsetType = UNSET
    """Filter resources updated >= this time."""
    updated_time_end: dt.datetime | UnsetType = UNSET
    """Filter resources updated <= this time."""

    created_bys: list[str] | UnsetType = UNSET
    """Filter resources created by these users."""
    updated_bys: list[str] | UnsetType = UNSET
    """Filter resources updated by these users."""

    rev_statuses: list[str] | UnsetType = UNSET
    """Filter by ``ResourceMeta.rev_status`` (current-revision status)."""

    rev_created_bys: list[str] | UnsetType = UNSET
    """Filter by users who created the current revision."""
    rev_updated_bys: list[str] | UnsetType = UNSET
    """Filter by users who last updated the current revision."""

    rev_created_time_start: dt.datetime | UnsetType = UNSET
    """Filter resources whose current revision was created >= this time."""
    rev_created_time_end: dt.datetime | UnsetType = UNSET
    """Filter resources whose current revision was created <= this time."""
    rev_updated_time_start: dt.datetime | UnsetType = UNSET
    """Filter resources whose current revision was last updated >= this time."""
    rev_updated_time_end: dt.datetime | UnsetType = UNSET
    """Filter resources whose current revision was last updated <= this time."""

    data_conditions: list[DataSearchFilter] | UnsetType = UNSET
    """Deprecated. Use `conditions` instead. Conditions to filter resources based on their indexed data fields."""

    conditions: list[DataSearchFilter] | UnsetType = UNSET
    """Conditions to filter resources based on their metadata or indexed data fields."""

    limit: int = DEFAULT_QUERY_LIMIT
    """Maximum number of results to return."""
    offset: int = 0
    """Number of results to skip before starting to collect the result set."""

    sorts: (
        list[ResourceMetaSearchSort | ResourceDataSearchSort | VectorDistanceSort]
        | UnsetType
    ) = UNSET
    """Sorting criteria for the search results."""


__all__ = [
    "DEFAULT_QUERY_LIMIT",
    "DEFAULT_QUERY_LIMIT_ENV_VAR",
    "DEFAULT_QUERY_LIMIT_FALLBACK",
    "DataSearchCondition",
    "DataSearchFilter",
    "DataSearchGroup",
    "DataSearchLogicOperator",
    "DataSearchOperator",
    "FieldTransform",
    "ResourceDataSearchSort",
    "ResourceMetaSearchQuery",
    "ResourceMetaSearchSort",
    "ResourceMetaSortDirection",
    "ResourceMetaSortKey",
]
