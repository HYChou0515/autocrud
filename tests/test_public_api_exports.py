"""Tests for the curated public import surface."""

import pytest

from autocrud.types import ResourceMetaSearchQuery


def test_root_exports_qb_for_everyday_usage():
    """QB should be importable from the package root."""
    from autocrud import QB, Schema, crud

    query = QB["name"].eq("Alice").build()

    assert QB is not None
    assert Schema is not None
    assert crud is not None
    assert isinstance(query, ResourceMetaSearchQuery)


def test_permission_namespace_exposes_common_symbols():
    """Permission helpers should be available from a curated namespace."""
    from autocrud.permission import ACLPermissionChecker, AllowAll, ResourceAction

    assert AllowAll is not None
    assert ACLPermissionChecker is not None
    assert ResourceAction.create in ResourceAction.full


def test_events_namespace_exposes_builder_api():
    """Event helpers should be importable without deep internal paths."""
    from autocrud.events import IEventHandler, ResourceAction, do

    handlers = do(lambda context: None).before(ResourceAction.create)

    assert len(handlers) == 1
    assert isinstance(handlers[0], IEventHandler)


def test_errors_namespace_exposes_public_exception_families():
    """Public exception types should be grouped in a dedicated namespace."""
    from autocrud.errors import (
        CannotModifyResourceError,
        ResourceNotFoundError,
        UniqueConstraintError,
        ValidationError,
    )

    assert issubclass(ResourceNotFoundError, Exception)
    assert issubclass(CannotModifyResourceError, Exception)
    assert issubclass(UniqueConstraintError, Exception)
    assert issubclass(ValidationError, Exception)


def test_resource_manager_namespace_exposes_core_symbols():
    """Resource-manager setup should be available from a higher-level facade."""
    from autocrud.resource_manager import (
        Encoding,
        IStorageFactory,
        MemoryStorageFactory,
        ResourceManager,
        ResourceOps,
        SimpleStorage,
        pydantic_to_struct,
    )

    assert ResourceManager is not None
    assert ResourceOps is not None
    assert SimpleStorage is not None
    assert Encoding.json.value == "json"
    assert issubclass(MemoryStorageFactory, IStorageFactory)
    assert callable(pydantic_to_struct)


def test_root_exports_both_pydantic_conversion_directions():
    """The package root should expose the main pydantic conversion helpers."""
    from autocrud import pydantic_to_struct, struct_to_pydantic

    assert callable(pydantic_to_struct)
    assert callable(struct_to_pydantic)


def test_root_does_not_export_resource_ops():
    """ResourceOps should stay in the resource-manager namespace."""
    with pytest.raises(ImportError):
        from autocrud import ResourceOps  # noqa: F401


def test_root_exports_job_for_async_workflows():
    """Job should be importable from the root package."""
    from autocrud import Job

    assert Job is not None


def test_root_exports_task_status_for_async_workflows():
    """TaskStatus should be importable from the root package."""
    from autocrud import TaskStatus

    assert TaskStatus.PENDING.value == "pending"
    assert TaskStatus.COMPLETED.value == "completed"
