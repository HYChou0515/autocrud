"""Test global crud instance and configure() method."""

import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct

from autocrud import AutoCRUD
from autocrud.permission.simple import AllowAll
from autocrud.resource_manager.basic import Encoding
from autocrud.resource_manager.storage_factory import (
    DiskStorageFactory,
    MemoryStorageFactory,
)


class User(Struct):
    """Test user model."""

    name: str
    age: int


class Product(Struct):
    """Test product model."""

    title: str
    price: float


def test_global_crud_instance_exists():
    """Test that global crud instance is available."""
    from autocrud import crud

    assert crud is not None
    assert isinstance(crud, AutoCRUD)


def test_global_crud_can_add_models():
    """Test that global crud instance can register models."""
    # Create a fresh instance for this test
    test_crud = AutoCRUD()
    test_crud.add_model(User)

    # Verify model was registered
    assert User in test_crud.model_names
    manager = test_crud.get_resource_manager(User)
    assert manager is not None


def test_configure_storage_factory():
    """Test configuring storage_factory via configure()."""
    test_crud = AutoCRUD()

    # Initial storage should be MemoryStorageFactory
    assert isinstance(test_crud.storage_factory, MemoryStorageFactory)

    # Configure with DiskStorageFactory
    with tempfile.TemporaryDirectory() as tmpdir:
        disk_factory = DiskStorageFactory(Path(tmpdir))
        test_crud.configure(storage_factory=disk_factory)

        # Verify storage was updated
        assert isinstance(test_crud.storage_factory, DiskStorageFactory)
        assert test_crud.storage_factory.rootdir == Path(tmpdir)


def test_configure_storage_factory_none():
    """Test that configure(storage_factory=None) uses default MemoryStorageFactory."""
    import datetime as dt

    test_crud = AutoCRUD()

    # Configure with None should use MemoryStorageFactory
    test_crud.configure(storage_factory=None)
    assert isinstance(test_crud.storage_factory, MemoryStorageFactory)

    # Should be able to add models and use them without errors
    test_crud.add_model(User)
    manager = test_crud.get_resource_manager(User)
    assert manager is not None

    # Should be able to create resources
    with manager.meta_provide(user="test", now=dt.datetime.now()):
        info = manager.create(User(name="Alice", age=30))
        assert info.resource_id is not None


def test_configure_model_naming():
    """Test configuring model_naming via configure()."""
    test_crud = AutoCRUD()

    # Default is "kebab"
    assert test_crud.model_naming == "kebab"

    # Configure to "snake"
    test_crud.configure(model_naming="snake")
    assert test_crud.model_naming == "snake"


def test_configure_encoding():
    """Test configuring encoding via configure()."""
    test_crud = AutoCRUD()

    # Default is json
    assert test_crud.default_encoding == Encoding.json

    # Configure to msgpack
    test_crud.configure(encoding=Encoding.msgpack)
    assert test_crud.default_encoding == Encoding.msgpack


def test_configure_admin_permission():
    """Test configuring admin with RBAC permission checker."""
    test_crud = AutoCRUD()

    # Default should be AllowAll
    assert isinstance(test_crud.permission_checker, AllowAll)

    # Configure with admin
    test_crud.configure(admin="admin@example.com")

    # Should now have RBAC checker
    from autocrud.permission.rbac import RBACPermissionChecker

    assert isinstance(test_crud.permission_checker, RBACPermissionChecker)


def test_configure_warns_after_models_registered(caplog):
    """Test that configure() warns if called after models are registered."""
    import logging

    test_crud = AutoCRUD()
    test_crud.add_model(User)

    # Should log warning when configuring after registration
    with caplog.at_level(logging.WARNING):
        test_crud.configure(model_naming="snake")

    assert "configure() called after models have been registered" in caplog.text


def test_global_pattern_workflow():
    """Test the complete global instance workflow."""
    # Create a fresh instance to simulate global usage
    test_crud = AutoCRUD()

    # Configure at startup (before registering models)
    with tempfile.TemporaryDirectory() as tmpdir:
        test_crud.configure(
            storage_factory=DiskStorageFactory(Path(tmpdir)),
            model_naming="snake",
        )

        # Register models (from different modules in real app)
        test_crud.add_model(User)
        test_crud.add_model(Product)

        # Apply to FastAPI
        app = FastAPI()
        test_crud.apply(app)

        # Test the API
        client = TestClient(app)

        # Create a user
        response = client.post("/user", json={"name": "Alice", "age": 30})
        assert response.status_code == 200
        resource_id = response.json()["resource_id"]

        # Read the user
        response = client.get(f"/user/{resource_id}/data")
        assert response.status_code == 200
        assert response.json()["name"] == "Alice"
        assert response.json()["age"] == 30


def test_configure_custom_naming_function():
    """Test configuring with custom naming function."""
    test_crud = AutoCRUD()

    def custom_naming(model_type: type) -> str:
        return f"custom_{model_type.__name__.lower()}"

    test_crud.configure(model_naming=custom_naming)

    # Register model and check the name
    test_crud.add_model(User)
    assert "custom_user" in test_crud.resource_managers


def test_configure_event_handlers():
    """Test configuring event handlers."""
    from unittest.mock import Mock

    from autocrud.resource_manager.events import do
    from autocrud.types import ResourceAction

    test_crud = AutoCRUD()
    mock_handler = Mock()

    # Configure with event handler using do() function
    event_handlers = do(mock_handler).after(ResourceAction.create)
    test_crud.configure(event_handlers=event_handlers)

    # Add model and create resource
    test_crud.add_model(User)
    app = FastAPI()
    test_crud.apply(app)

    client = TestClient(app)
    # Default model_naming is "kebab", so "User" becomes "user"
    response = client.post("/user", json={"name": "Bob", "age": 25})
    assert response.status_code == 200

    # Verify handler was called
    mock_handler.assert_called_once()


def test_configure_partial_update():
    """Test that configure() only updates provided parameters."""
    test_crud = AutoCRUD()

    # Set initial state
    initial_naming = test_crud.model_naming
    initial_encoding = test_crud.default_encoding

    # Configure only storage_factory
    with tempfile.TemporaryDirectory() as tmpdir:
        test_crud.configure(storage_factory=DiskStorageFactory(Path(tmpdir)))

        # Other settings should remain unchanged
        assert test_crud.model_naming == initial_naming
        assert test_crud.default_encoding == initial_encoding


def test_configure_multiple_times():
    """Test that configure() can be called multiple times."""
    test_crud = AutoCRUD()

    # First configuration
    test_crud.configure(model_naming="snake")
    assert test_crud.model_naming == "snake"

    # Second configuration
    test_crud.configure(model_naming="kebab")
    assert test_crud.model_naming == "kebab"

    # Third configuration with different parameter
    test_crud.configure(encoding=Encoding.msgpack)
    assert test_crud.default_encoding == Encoding.msgpack
    # model_naming should be unchanged
    assert test_crud.model_naming == "kebab"


def test_documentation_example():
    """Test the example from the feature request documentation."""
    # Simulate the global instance
    test_crud = AutoCRUD()

    # This simulates: from autocrud import crud
    # (in real usage, this would be the global instance)

    # Configure once at startup (from main.py)
    with tempfile.TemporaryDirectory() as tmpdir:
        test_crud.configure(
            storage_factory=DiskStorageFactory(Path(tmpdir)),
            model_naming="snake",
        )

        # Now register models (from various modules)
        # This simulates: from app.models.user import User
        test_crud.add_model(User)

        # Apply to FastAPI
        app = FastAPI()
        test_crud.apply(app)

        # Verify it works
        client = TestClient(app)
        response = client.post("/user", json={"name": "Test", "age": 42})
        assert response.status_code == 200


def test_configure_dependency_provider():
    """Test configuring dependency provider."""
    from autocrud.crud.route_templates.basic import DependencyProvider

    test_crud = AutoCRUD()

    async def custom_get_user():
        return "custom_user"

    provider = DependencyProvider(get_user=custom_get_user)
    test_crud.configure(dependency_provider=provider)

    # Verify route templates were recreated with new dependency provider
    assert len(test_crud.route_templates) > 0
    # Verify the dependency provider is used
    assert test_crud.route_templates[0].deps.get_user == custom_get_user


def test_configure_route_templates_dict():
    """Test configuring route templates with dict."""
    from autocrud.crud.route_templates.create import CreateRouteTemplate

    test_crud = AutoCRUD()

    # Configure with dict to customize templates - use valid parameters
    test_crud.configure(
        route_templates={
            CreateRouteTemplate: {"order": 50},
        }
    )

    # Verify templates were updated
    assert len(test_crud.route_templates) > 0
    # Find the CreateRouteTemplate
    create_template = next(
        (t for t in test_crud.route_templates if isinstance(t, CreateRouteTemplate)),
        None,
    )
    assert create_template is not None
    assert create_template.order == 50


def test_global_instance_isolation():
    """Test that the global instance is separate from new instances."""
    from autocrud import crud as global_crud

    # Create a new instance
    local_crud = AutoCRUD()

    # Configure local instance
    local_crud.configure(model_naming="snake")

    # Global instance should still have default naming
    # (assuming it hasn't been configured)
    # We can't test this perfectly since global instance is shared,
    # but we can verify they are different objects
    assert global_crud is not local_crud


# ============================================================================
# Configuration Consistency Tests (__init__ vs configure)
# ============================================================================
# These tests verify that the refactored _apply_configuration method
# ensures __init__ and configure use the same logic, preventing inconsistencies.


def test_init_and_configure_consistency():
    """Test that __init__ and configure use the same logic via _apply_configuration.

    This demonstrates the DRY principle: configuration logic is shared between
    __init__ and configure, making it easier to maintain and add new options.
    """
    # Test 1: Create instance with __init__
    with tempfile.TemporaryDirectory() as tmpdir1:
        crud1 = AutoCRUD(
            model_naming="snake",
            storage_factory=DiskStorageFactory(Path(tmpdir1)),
            encoding=Encoding.msgpack,
            admin="admin@example.com",
        )

        assert crud1.model_naming == "snake"
        assert isinstance(crud1.storage_factory, DiskStorageFactory)
        assert crud1.default_encoding == Encoding.msgpack

    # Test 2: Create instance then configure - should have identical results
    with tempfile.TemporaryDirectory() as tmpdir2:
        crud2 = AutoCRUD()
        crud2.configure(
            model_naming="snake",
            storage_factory=DiskStorageFactory(Path(tmpdir2)),
            encoding=Encoding.msgpack,
            admin="admin@example.com",
        )

        assert crud2.model_naming == "snake"
        assert isinstance(crud2.storage_factory, DiskStorageFactory)
        assert crud2.default_encoding == Encoding.msgpack


def test_shared_configuration_handles_all_parameters():
    """Test that _apply_configuration correctly handles all configuration parameters."""
    import datetime as dt

    crud = AutoCRUD()

    # Test that we can configure all parameters via configure()
    with tempfile.TemporaryDirectory() as tmpdir:

        def custom_naming(model):
            return f"custom_{model.__name__}"

        def custom_user():
            return "custom_user"

        def custom_now():
            return dt.datetime(2024, 1, 1)

        crud.configure(
            model_naming=custom_naming,
            storage_factory=DiskStorageFactory(Path(tmpdir)),
            encoding=Encoding.msgpack,
            admin="root@example.com",
            default_user=custom_user,
            default_now=custom_now,
        )

        # Verify all configurations are applied
        assert callable(crud.model_naming)
        assert crud.model_naming(User) == "custom_User"
        assert isinstance(crud.storage_factory, DiskStorageFactory)
        assert crud.default_encoding == Encoding.msgpack
        assert callable(crud.default_user)
        assert crud.default_user() == "custom_user"
        assert callable(crud.default_now)
        assert crud.default_now() == dt.datetime(2024, 1, 1)


def test_init_configure_consistency_validates_dry_principle():
    """Verify that __init__ and configure produce identical configurations.

    This test demonstrates the benefit of the refactored _apply_configuration:
    - Configuration logic is defined only once (DRY principle)
    - Adding new options requires updating _apply_configuration only once
    - No risk of __init__ and configure diverging over time
    """
    # Create two instances with identical parameters
    crud1 = AutoCRUD(model_naming="snake", encoding=Encoding.msgpack)

    crud2 = AutoCRUD()
    crud2.configure(model_naming="snake", encoding=Encoding.msgpack)

    # Both should have identical configuration
    assert crud1.model_naming == crud2.model_naming
    assert crud1.default_encoding == crud2.default_encoding
    assert isinstance(crud1.storage_factory, type(crud2.storage_factory))
    assert isinstance(crud1.permission_checker, type(crud2.permission_checker))
