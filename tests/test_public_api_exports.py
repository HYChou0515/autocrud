"""Tests for the curated public import surface."""

import pytest

from specstar.query_types import ResourceMetaSearchQuery


def test_root_exports_qb_for_everyday_usage():
    """QB should be importable from the package root."""
    from specstar import QB, Schema, spec

    query = QB["name"].eq("Alice").build()

    assert QB is not None
    assert Schema is not None
    assert spec is not None
    assert isinstance(query, ResourceMetaSearchQuery)


def test_permission_namespace_exposes_common_symbols():
    """Permission helpers should be available from a curated namespace."""
    from specstar.permission import ACLPermissionChecker, AllowAll, ResourceAction

    assert AllowAll is not None
    assert ACLPermissionChecker is not None
    assert ResourceAction.create in ResourceAction.full


def test_events_namespace_exposes_builder_api():
    """Event helpers should be importable without deep internal paths."""
    from specstar.events import (
        IEventHandler,
        ResourceAction,
        do,
    )

    handlers = do(lambda context: None).before(ResourceAction.create)

    assert len(handlers) == 1
    assert isinstance(handlers[0], IEventHandler)


def test_errors_namespace_exposes_public_exception_families():
    """Public exception types should be grouped in a dedicated namespace."""
    from specstar.errors import (
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
    from specstar.resource_manager import (
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
    from specstar import pydantic_to_struct, struct_to_pydantic

    assert callable(pydantic_to_struct)
    assert callable(struct_to_pydantic)


def test_root_does_not_export_resource_ops():
    """ResourceOps should stay in the resource-manager namespace."""
    with pytest.raises(ImportError):
        from specstar import ResourceOps  # noqa: F401  # ty:ignore[unresolved-import]


def test_root_exports_job_for_async_workflows():
    """Job should be importable from the root package."""
    from specstar import Job

    assert Job is not None


def test_root_exports_task_status_for_async_workflows():
    """TaskStatus should be importable from the root package."""
    from specstar import TaskStatus

    assert TaskStatus.PENDING.value == "pending"
    assert TaskStatus.COMPLETED.value == "completed"


def test_events_namespace_exposes_event_context_structs():
    """Every event-context struct lives in specstar.events."""
    from specstar.events import (
        AfterCreate,
        AfterUpdate,
        BeforeCreate,
        BeforeDelete,
        EventContext,
        EventContextProto,
        HasData,
        HasResourceId,
        HasRevisionId,
        OnFailureCreate,
        OnSuccessCreate,
        OnSuccessUpdate,
        SimpleEventHandler,
    )

    assert BeforeCreate is not None
    assert AfterCreate is not None
    assert OnSuccessCreate is not None
    assert OnFailureCreate is not None
    assert BeforeDelete is not None
    assert AfterUpdate is not None
    assert OnSuccessUpdate is not None
    assert EventContextProto is not None
    assert HasData is not None
    assert HasResourceId is not None
    assert HasRevisionId is not None
    assert EventContext is not None
    assert SimpleEventHandler is not None


def test_query_types_namespace_exposes_search_symbols():
    """Search/query types live in specstar.query_types."""
    from specstar.query_types import (
        DEFAULT_QUERY_LIMIT,
        DataSearchCondition,
        DataSearchOperator,
        FieldTransform,
        ResourceMetaSearchQuery,
        ResourceMetaSortKey,
    )

    assert isinstance(DEFAULT_QUERY_LIMIT, int)
    assert DataSearchOperator.equals.value == "eq"
    assert FieldTransform.length.value == "len"
    assert DataSearchCondition is not None
    assert ResourceMetaSearchQuery is not None
    assert ResourceMetaSortKey is not None


def test_types_namespace_no_longer_re_exports_event_context_structs():
    """Event-context structs must be imported from specstar.events, not types."""
    import specstar.types as types_mod

    for name in (
        "BeforeCreate",
        "AfterCreate",
        "OnSuccessCreate",
        "OnFailureCreate",
        "EventContext",
        "EventContextProto",
        "HasData",
        "HasResourceId",
        "IEventHandler",
        "do",
        "SimpleEventHandler",
    ):
        assert name not in vars(types_mod), (
            f"specstar.types should not expose {name!r}; import it from specstar.events"
        )


def test_types_namespace_no_longer_re_exports_query_types():
    """Search/query types must be imported from specstar.query_types, not types."""
    import specstar.types as types_mod

    for name in (
        "FieldTransform",
        "DEFAULT_QUERY_LIMIT",
        "DataSearchCondition",
        "DataSearchOperator",
        "ResourceMetaSortKey",
    ):
        assert name not in vars(types_mod), (
            f"specstar.types should not expose {name!r}; "
            "import it from specstar.query_types"
        )


def test_types_namespace_no_longer_re_exports_permission_checker():
    """Permission interface must come from specstar.permission, not types."""
    import specstar.types as types_mod

    for name in ("IPermissionChecker", "PermissionContext", "PermissionResult"):
        assert name not in vars(types_mod), (
            f"specstar.types should not expose {name!r}; "
            "import it from specstar.permission"
        )


def test_resource_manager_events_module_is_gone():
    """The legacy specstar.resource_manager.events module is removed."""
    with pytest.raises(ImportError):
        import specstar.resource_manager.events  # noqa: F401  # ty:ignore[unresolved-import]


def test_events_module_has_no_getattr_shim():
    """specstar.events must not rely on a __getattr__ compatibility shim."""
    import specstar.events as events_mod

    assert "__getattr__" not in vars(events_mod), (
        "specstar.events should expose symbols directly, not through __getattr__"
    )


def test_events_namespace_declares_all():
    """specstar.events should publish an explicit __all__."""
    import specstar.events as events_mod

    assert hasattr(events_mod, "__all__")
    for name in (
        "BeforeCreate",
        "EventContext",
        "IEventHandler",
        "SimpleEventHandler",
        "do",
        "ResourceAction",
    ):
        assert name in events_mod.__all__
