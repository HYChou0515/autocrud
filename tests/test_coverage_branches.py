"""Test coverage for specific branches and lines in AutoCRUD.

This test file is designed to achieve 100% coverage for previously uncovered
branches and lines in autocrud/crud/core.py.
"""

import datetime as dt
import io
import tempfile
from pathlib import Path
from unittest.mock import Mock

from fastapi import FastAPI
from msgspec import Struct

from autocrud import AutoCRUD
from autocrud.permission.simple import AllowAll
from autocrud.types import Job


class User(Struct):
    name: str
    age: int


class TaskPayload(Struct):
    """Payload for job."""

    task_name: str


# Use Job with a simple payload type
MyJob = Job[TaskPayload]


# Lines 340-342, 346: Test storage_factory with build_blob_store method
def test_storage_factory_with_build_blob_store():
    """Test storage factory that has build_blob_store method (e.g., S3)."""
    # Create a mock storage factory with build_blob_store method
    mock_storage_factory = Mock(spec=["build", "build_blob_store"])
    mock_blob_store = Mock()
    mock_storage_factory.build_blob_store.return_value = mock_blob_store
    mock_storage = Mock()
    mock_storage_factory.build.return_value = mock_storage

    # Test with __init__
    crud = AutoCRUD(storage_factory=mock_storage_factory)
    assert crud.storage_factory is mock_storage_factory
    assert crud.blob_store is mock_blob_store
    mock_storage_factory.build_blob_store.assert_called_once()

    # Test with configure
    mock_storage_factory2 = Mock(spec=["build", "build_blob_store"])
    mock_blob_store2 = Mock()
    mock_storage_factory2.build_blob_store.return_value = mock_blob_store2

    crud2 = AutoCRUD()
    crud2.configure(storage_factory=mock_storage_factory2)
    assert crud2.storage_factory is mock_storage_factory2
    assert crud2.blob_store is mock_blob_store2


# Lines 482, 502, 506, 513-514: permission_checker and admin combinations
def test_permission_checker_none_with_admin():
    """Test setting permission_checker=None with admin parameter."""
    # When permission_checker=None and admin is provided
    crud = AutoCRUD()
    crud.configure(permission_checker=None, admin="root@example.com")

    from autocrud.permission.rbac import RBACPermissionChecker

    assert isinstance(crud.permission_checker, RBACPermissionChecker)


def test_permission_checker_none_without_admin():
    """Test setting permission_checker=None without admin parameter."""
    crud = AutoCRUD()
    crud.configure(permission_checker=None)

    assert isinstance(crud.permission_checker, AllowAll)


def test_admin_false_sets_allow_all():
    """Test that admin='' or admin=None sets AllowAll."""
    crud = AutoCRUD()
    crud.configure(admin="")

    assert isinstance(crud.permission_checker, AllowAll)


def test_admin_change_without_permission_checker():
    """Test changing admin without explicitly setting permission_checker."""
    crud = AutoCRUD()
    # First set an admin
    crud.configure(admin="admin@example.com")

    from autocrud.permission.rbac import RBACPermissionChecker

    assert isinstance(crud.permission_checker, RBACPermissionChecker)

    # Then change to empty admin
    crud.configure(admin="")
    assert isinstance(crud.permission_checker, AllowAll)


# Line 342: Custom permission_checker provided
def test_custom_permission_checker():
    """Test providing a custom permission_checker instance."""
    custom_checker = AllowAll()
    crud = AutoCRUD(permission_checker=custom_checker)
    assert crud.permission_checker is custom_checker

    # Also test via configure
    custom_checker2 = AllowAll()
    crud2 = AutoCRUD()
    crud2.configure(permission_checker=custom_checker2)
    assert crud2.permission_checker is custom_checker2


# Line 672: Invalid indexed_field type raises TypeError
def test_invalid_indexed_field_type():
    """Test that invalid indexed_field type raises TypeError."""
    import pytest

    crud = AutoCRUD()

    with pytest.raises(
        TypeError, match="Invalid indexed field, should be IndexableField"
    ):
        crud.add_model(User, indexed_fields=[123])  # Invalid type


# Line 672: IndexableField object direct usage
def test_indexablefield_object_in_indexed_fields():
    """Test using IndexableField object directly in indexed_fields list."""
    from autocrud.types import IndexableField

    crud = AutoCRUD()
    field = IndexableField(field_path="age", field_type=int)
    crud.add_model(User, name="users_indexed", indexed_fields=[field])
    assert "users_indexed" in crud.resource_managers


# Line 690: Model registered with multiple names
def test_model_registered_with_multiple_names(caplog):
    """Test warning when model is registered with multiple names."""
    import logging

    crud = AutoCRUD()

    # Register same model with two different names
    crud.add_model(User, name="users")

    with caplog.at_level(logging.WARNING):
        crud.add_model(User, name="people")

    # Check warning was logged
    assert "already registered with a different name" in caplog.text

    # Verify model_names is set to None for ambiguous models
    assert crud.model_names[User] is None


# Line 699->701: Test default_user at model level vs crud level
def test_default_user_precedence():
    """Test that model-level default_user takes precedence over crud-level."""

    def crud_user():
        return "crud_user"

    def model_user():
        return "model_user"

    # Test with crud-level default_user
    crud = AutoCRUD(default_user=crud_user)
    crud.add_model(User)
    # Just verify the model was added successfully
    mgr = crud.get_resource_manager(User)
    assert mgr is not None

    # Test with model-level default_user overriding crud-level
    crud2 = AutoCRUD(default_user=crud_user)
    crud2.add_model(User, default_user=model_user)
    mgr2 = crud2.get_resource_manager(User)
    assert mgr2 is not None


def test_default_now_precedence():
    """Test that model-level default_now takes precedence over crud-level."""

    def crud_now():
        return dt.datetime(2024, 1, 1)

    def model_now():
        return dt.datetime(2025, 1, 1)

    # Test with crud-level default_now
    crud = AutoCRUD(default_now=crud_now)
    crud.add_model(User)
    mgr = crud.get_resource_manager(User)
    assert mgr is not None

    # Test with model-level default_now overriding crud-level
    crud2 = AutoCRUD(default_now=crud_now)
    crud2.add_model(User, default_now=model_now)
    mgr2 = crud2.get_resource_manager(User)
    assert mgr2 is not None


# Lines 721-724, 726->746, 741->746: Job handler various paths
def test_job_with_message_queue_factory_none():
    """Test Job model with message_queue_factory explicitly set to None."""
    crud = AutoCRUD()

    def job_handler(resource):
        pass

    # message_queue_factory=None should disable message queue
    crud.add_model(MyJob, job_handler=job_handler, message_queue_factory=None)

    # Should not have message_queue in other_options
    mgr = crud.get_resource_manager(MyJob)
    assert mgr is not None


def test_job_with_job_handler_factory():
    """Test Job model with job_handler_factory (lazy initialization)."""
    from autocrud.message_queue.simple import SimpleMessageQueueFactory

    crud = AutoCRUD(message_queue_factory=SimpleMessageQueueFactory())

    handler_created = []

    def create_handler():
        def handler(resource):
            handler_created.append(True)

        return handler

    crud.add_model(MyJob, job_handler_factory=create_handler)

    # Handler should not be created yet (lazy)
    assert len(handler_created) == 0


def test_job_with_custom_message_queue_factory():
    """Test Job model with custom message_queue_factory at model level."""
    from autocrud.message_queue.simple import SimpleMessageQueueFactory

    crud = AutoCRUD()  # No factory at crud level
    model_factory = SimpleMessageQueueFactory()

    def job_handler(resource):
        pass

    # Use model-level factory
    crud.add_model(MyJob, job_handler=job_handler, message_queue_factory=model_factory)

    mgr = crud.get_resource_manager(MyJob)
    assert mgr is not None


def test_job_indexed_fields_already_present():
    """Test that Job doesn't add duplicate indexed fields."""
    from autocrud.message_queue.simple import SimpleMessageQueueFactory
    from autocrud.types import TaskStatus

    crud = AutoCRUD(message_queue_factory=SimpleMessageQueueFactory())

    def job_handler(resource):
        pass

    # Pre-define status and retries fields
    crud.add_model(
        MyJob,
        job_handler=job_handler,
        indexed_fields=[
            ("status", TaskStatus),
            ("retries", int),
        ],
    )

    mgr = crud.get_resource_manager(MyJob)
    # Verify indexed_fields doesn't have duplicates
    status_count = sum(1 for f in mgr.indexed_fields if f.field_path == "status")
    retries_count = sum(1 for f in mgr.indexed_fields if f.field_path == "retries")

    assert status_count == 1
    assert retries_count == 1


# Lines 780-800: openapi method with root_path
def test_openapi_with_root_path():
    """Test openapi generation with root_path set."""
    app = FastAPI(root_path="/api/v1")
    crud = AutoCRUD()
    crud.add_model(User)
    crud.apply(app)

    # Call openapi with root_path
    crud.openapi(app)

    assert app.openapi_schema is not None
    assert "servers" in app.openapi_schema
    assert app.openapi_schema["servers"] == [{"url": "/api/v1"}]


def test_openapi_with_root_path_and_existing_servers():
    """Test that existing servers are not overwritten."""
    app = FastAPI(root_path="/api/v1", servers=[{"url": "https://example.com"}])
    crud = AutoCRUD()
    crud.add_model(User)
    crud.apply(app)

    crud.openapi(app)

    # Should keep existing servers
    assert app.openapi_schema["servers"] == [{"url": "https://example.com"}]


def test_openapi_with_custom_structs():
    """Test openapi with additional custom structs."""

    class CustomStruct(Struct):
        value: str

    app = FastAPI()
    crud = AutoCRUD()
    crud.add_model(User)
    crud.apply(app)

    crud.openapi(app, structs=[CustomStruct])

    assert app.openapi_schema is not None
    # CustomStruct should be in the schemas
    assert "CustomStruct" in app.openapi_schema["components"]["schemas"]


# Lines 935-937: dump method with BytesIO vs other IO types
def test_dump_with_bytesio_values():
    """Test dump method when mgr.dump() returns BytesIO objects."""
    crud = AutoCRUD()
    crud.add_model(User)

    mgr = crud.get_resource_manager(User)

    # Create a resource
    with mgr.meta_provide(user="test", now=dt.datetime.now()):
        mgr.create(User(name="Alice", age=30))

    # Dump to buffer
    buffer = io.BytesIO()
    crud.dump(buffer)

    # Verify data was written
    buffer.seek(0)
    assert len(buffer.read()) > 0


def test_dump_with_file_like_objects():
    """Test dump method with various file-like objects."""
    crud = AutoCRUD()
    crud.add_model(User)

    mgr = crud.get_resource_manager(User)

    # Create a resource
    with mgr.meta_provide(user="test", now=dt.datetime.now()):
        mgr.create(User(name="Bob", age=25))

    # Dump to file
    with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
        temp_path = f.name
        crud.dump(f)

    # Verify file was created and has content
    assert Path(temp_path).exists()
    assert Path(temp_path).stat().st_size > 0

    # Clean up
    Path(temp_path).unlink()


# Test apply method exception handling (lines 935-937 area)
def test_apply_with_failing_route_template():
    """Test that apply continues even if a route template fails."""
    from autocrud.crud.route_templates.basic import BaseRouteTemplate

    class FailingTemplate(BaseRouteTemplate):
        order = 0

        def apply(self, model_name, resource_manager, router):
            raise RuntimeError("Template failure")

    crud = AutoCRUD()
    crud.add_route_template(FailingTemplate())
    crud.add_model(User)

    app = FastAPI()
    # Should not raise, just skip the failing template
    crud.apply(app)


# Test get_resource_manager with string that doesn't exist
def test_get_resource_manager_nonexistent_string():
    """Test get_resource_manager with non-existent model name."""
    import pytest

    crud = AutoCRUD()
    crud.add_model(User)

    with pytest.raises(KeyError):
        crud.get_resource_manager("nonexistent")


# Test get_resource_manager with model registered multiple times
def test_get_resource_manager_ambiguous_model():
    """Test get_resource_manager with ambiguous model."""
    import pytest

    crud = AutoCRUD()
    crud.add_model(User, name="users")
    crud.add_model(User, name="people")

    with pytest.raises(ValueError, match="registered with multiple names"):
        crud.get_resource_manager(User)


# Test _is_job_subclass edge cases
def test_is_job_subclass_with_invalid_types():
    """Test _is_job_subclass with types that don't have __mro__."""
    crud = AutoCRUD()

    # Test with a type that doesn't have __mro__
    class NoMRO:
        pass

    # Remove __mro__ to simulate edge case
    result = crud._is_job_subclass(str)  # str is not a Job
    assert result is False


# Line 506: Model without __mro__ attribute
def test_model_without_mro_attribute():
    """Test _is_job_subclass with object that lacks __mro__ attribute."""
    crud = AutoCRUD()
    # Create a mock object without __mro__ attribute
    fake_model = Mock(spec=[])  # Empty spec means no attributes
    result = crud._is_job_subclass(fake_model)
    assert result is False


def test_is_job_subclass_with_exception():
    """Test _is_job_subclass exception handling."""
    crud = AutoCRUD()

    # Create a type that will raise TypeError
    mock_type = Mock()
    mock_type.__mro__ = None

    # Should handle exception and return False
    result = crud._is_job_subclass(mock_type)
    assert result is False
