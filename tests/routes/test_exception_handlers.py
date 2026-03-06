"""Tests for the shared exception→HTTP mapping helper and route template consistency.

Covers:
- Unit tests for :func:`to_http_exception` with every mapped exception type.
- Integration tests verifying that each route template returns the correct
  HTTP status for common domain exceptions (PermissionDeniedError,
  ResourceNotFoundError, ValidationError, ResourceConflictError).
"""

import msgspec
import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient

from autocrud.crud.core import AutoCRUD
from autocrud.crud.route_templates.create import CreateRouteTemplate
from autocrud.crud.route_templates.delete import (
    DeleteRouteTemplate,
    PermanentlyDeleteRouteTemplate,
    RestoreRouteTemplate,
)
from autocrud.crud.route_templates.exception_handlers import to_http_exception
from autocrud.crud.route_templates.get import ReadRouteTemplate
from autocrud.crud.route_templates.patch import PatchRouteTemplate
from autocrud.crud.route_templates.search import ListRouteTemplate
from autocrud.crud.route_templates.switch import SwitchRevisionRouteTemplate
from autocrud.crud.route_templates.update import UpdateRouteTemplate
from autocrud.types import (
    CannotModifyResourceError,
    DuplicateResourceError,
    PermissionDeniedError,
    ResourceConflictError,
    ResourceIDNotFoundError,
    ResourceIsDeletedError,
    ResourceNotFoundError,
    RevisionIDNotFoundError,
    RevisionNotFoundError,
    SchemaConflictError,
    UniqueConstraintError,
    ValidationError,
)

# ======================================================================
# Unit tests for to_http_exception
# ======================================================================


class TestToHttpException:
    """Unit tests for :func:`to_http_exception`."""

    # -- ValidationError family → 422 ----------------------------------

    def test_msgspec_validation_error(self):
        exc = to_http_exception(msgspec.ValidationError("bad type"))
        assert exc.status_code == 422
        assert "bad type" in exc.detail

    def test_autocrud_validation_error(self):
        exc = to_http_exception(ValidationError("custom validation failed"))
        assert exc.status_code == 422
        assert "custom validation failed" in exc.detail

    # -- PermissionDeniedError → 403 -----------------------------------

    def test_permission_denied_error(self):
        exc = to_http_exception(PermissionDeniedError("not allowed"))
        assert exc.status_code == 403
        assert "not allowed" in exc.detail

    # -- ResourceNotFoundError family → 404 ----------------------------

    def test_resource_not_found_error(self):
        exc = to_http_exception(ResourceNotFoundError("gone"))
        assert exc.status_code == 404

    def test_resource_id_not_found_error(self):
        exc = to_http_exception(ResourceIDNotFoundError("abc"))
        assert exc.status_code == 404
        assert "abc" in exc.detail

    def test_revision_not_found_error(self):
        exc = to_http_exception(RevisionNotFoundError("rev gone"))
        assert exc.status_code == 404

    def test_revision_id_not_found_error(self):
        exc = to_http_exception(RevisionIDNotFoundError("res1", "rev1"))
        assert exc.status_code == 404
        assert "rev1" in exc.detail

    def test_resource_is_deleted_error(self):
        exc = to_http_exception(ResourceIsDeletedError("del1"))
        assert exc.status_code == 404
        assert "del1" in exc.detail

    # -- ResourceConflictError family → 409 ----------------------------

    def test_resource_conflict_error(self):
        exc = to_http_exception(ResourceConflictError("conflict"))
        assert exc.status_code == 409

    def test_unique_constraint_error_structured_detail(self):
        exc = to_http_exception(UniqueConstraintError("email", "a@b.com", "res-42"))
        assert exc.status_code == 409
        assert isinstance(exc.detail, dict)
        assert exc.detail["field"] == "email"
        assert exc.detail["conflicting_resource_id"] == "res-42"

    def test_duplicate_resource_error(self):
        exc = to_http_exception(DuplicateResourceError("dup1"))
        assert exc.status_code == 409
        assert "dup1" in exc.detail

    def test_schema_conflict_error(self):
        exc = to_http_exception(SchemaConflictError("schema mismatch"))
        assert exc.status_code == 409

    def test_cannot_modify_resource_error(self):
        exc = to_http_exception(CannotModifyResourceError("locked1"))
        assert exc.status_code == 409

    # -- Fallback → 400 -----------------------------------------------

    def test_generic_exception_fallback(self):
        exc = to_http_exception(Exception("something went wrong"))
        assert exc.status_code == 400
        assert "something went wrong" in exc.detail

    def test_value_error_fallback(self):
        exc = to_http_exception(ValueError("bad value"))
        assert exc.status_code == 400

    def test_runtime_error_fallback(self):
        exc = to_http_exception(RuntimeError("runtime issue"))
        assert exc.status_code == 400

    # -- HTTPException → pass through unchanged ------------------------

    def test_http_exception_passthrough(self):
        original = HTTPException(status_code=418, detail="I'm a teapot")
        result = to_http_exception(original)
        assert result is original

    def test_http_exception_preserves_status_and_detail(self):
        original = HTTPException(status_code=503, detail="service unavailable")
        result = to_http_exception(original)
        assert result.status_code == 503
        assert result.detail == "service unavailable"

    # -- FileNotFoundError → 404 ---------------------------------------

    def test_file_not_found_error(self):
        exc = to_http_exception(FileNotFoundError("blob_123"))
        assert exc.status_code == 404
        assert "blob_123" in exc.detail

    def test_file_not_found_error_empty_message(self):
        exc = to_http_exception(FileNotFoundError())
        assert exc.status_code == 404
        assert exc.detail  # must not be empty

    # -- NotImplementedError → 501 -------------------------------------

    def test_not_implemented_error(self):
        exc = to_http_exception(NotImplementedError("blob store not configured"))
        assert exc.status_code == 501
        assert "blob store not configured" in exc.detail

    def test_not_implemented_error_empty_message(self):
        exc = to_http_exception(NotImplementedError())
        assert exc.status_code == 501
        assert exc.detail  # must not be empty

    # -- Return type is always HTTPException ---------------------------

    def test_return_type_is_http_exception(self):
        for e in [
            msgspec.ValidationError("x"),
            ValidationError("x"),
            PermissionDeniedError("x"),
            ResourceIDNotFoundError("x"),
            DuplicateResourceError("x"),
            FileNotFoundError("x"),
            NotImplementedError("x"),
            HTTPException(status_code=400, detail="x"),
            Exception("x"),
        ]:
            result = to_http_exception(e)
            assert isinstance(result, HTTPException)

    # -- Priority: UniqueConstraintError before generic Conflict -------

    def test_unique_constraint_checked_before_generic_conflict(self):
        """UniqueConstraintError IS-A ResourceConflictError;
        but it should get structured detail, not plain str."""
        exc = to_http_exception(UniqueConstraintError("name", "Alice", "r1"))
        assert isinstance(exc.detail, dict)
        assert exc.detail["field"] == "name"


# ======================================================================
# Integration tests — route templates return correct HTTP codes
# ======================================================================


class Item(msgspec.Struct):
    name: str
    price: float


@pytest.fixture
def app_and_client():
    """Build a full CRUD app for *Item* and return (app, client)."""
    crud = AutoCRUD(model_naming="kebab")
    crud.add_route_template(CreateRouteTemplate())
    crud.add_route_template(ReadRouteTemplate())
    crud.add_route_template(UpdateRouteTemplate())
    crud.add_route_template(DeleteRouteTemplate())
    crud.add_route_template(PermanentlyDeleteRouteTemplate())
    crud.add_route_template(RestoreRouteTemplate())
    crud.add_route_template(ListRouteTemplate())
    crud.add_route_template(SwitchRevisionRouteTemplate())
    crud.add_route_template(PatchRouteTemplate())

    crud.add_model(Item)

    app = FastAPI()
    router = APIRouter()
    crud.apply(router)
    app.include_router(router)

    return app, TestClient(app)


class TestRouteExceptionConsistency:
    """Verify that routes return consistent HTTP codes for domain errors."""

    # -- GET (read) routes → 404 for not-found -------------------------

    def test_get_resource_returns_404_for_not_found(self, app_and_client):
        _, client = app_and_client
        resp = client.get("/item/nonexistent")
        assert resp.status_code == 404

    def test_get_resource_meta_returns_404_for_not_found(self, app_and_client):
        _, client = app_and_client
        resp = client.get("/item/nonexistent/meta")
        assert resp.status_code == 404

    def test_get_resource_data_returns_404_for_not_found(self, app_and_client):
        _, client = app_and_client
        resp = client.get("/item/nonexistent/data")
        assert resp.status_code == 404

    def test_get_revision_list_returns_404_for_not_found(self, app_and_client):
        _, client = app_and_client
        resp = client.get("/item/nonexistent/revision-list")
        assert resp.status_code == 404

    def test_get_revision_info_returns_404_for_not_found(self, app_and_client):
        _, client = app_and_client
        resp = client.get("/item/nonexistent/revision-info")
        assert resp.status_code == 404

    # -- CREATE → 422 for validation errors ----------------------------

    def test_create_returns_422_for_invalid_data(self, app_and_client):
        _, client = app_and_client
        resp = client.post("/item", json={"name": "x"})  # missing price
        assert resp.status_code == 422

    def test_create_returns_422_for_wrong_type(self, app_and_client):
        _, client = app_and_client
        resp = client.post("/item", json={"name": 123, "price": "not-a-number"})
        assert resp.status_code == 422

    # -- UPDATE → 422 for validation, appropriate codes for not-found --

    def test_update_returns_422_for_invalid_data(self, app_and_client):
        _, client = app_and_client
        # create first
        resp = client.post("/item", json={"name": "Widget", "price": 9.99})
        resource_id = resp.json()["resource_id"]
        # update with wrong type
        resp = client.put(
            f"/item/{resource_id}", json={"name": "Widget", "price": "bad"}
        )
        assert resp.status_code == 422

    def test_update_nonexistent_returns_not_found_or_bad_request(self, app_and_client):
        """Update a resource that doesn't exist → should be 404."""
        _, client = app_and_client
        resp = client.put("/item/does-not-exist", json={"name": "Widget", "price": 1.0})
        # After our fix, ResourceIDNotFoundError → 404
        assert resp.status_code == 404

    # -- PATCH → 422 for validation, 404 for not-found ----------------

    def test_patch_nonexistent_returns_not_found(self, app_and_client):
        _, client = app_and_client
        resp = client.patch(
            "/item/does-not-exist",
            json=[{"op": "replace", "path": "/name", "value": "X"}],
        )
        # After fix: ResourceIDNotFoundError → 404
        assert resp.status_code == 404

    # -- DELETE → 404 for not-found ------------------------------------

    def test_delete_nonexistent_returns_not_found(self, app_and_client):
        _, client = app_and_client
        resp = client.delete("/item/does-not-exist")
        # After fix: ResourceIDNotFoundError → 404
        assert resp.status_code == 404

    def test_permanently_delete_nonexistent_returns_not_found(self, app_and_client):
        _, client = app_and_client
        resp = client.delete("/item/does-not-exist/permanently")
        assert resp.status_code == 404

    # -- RESTORE → 404 for not-found ----------------------------------

    def test_restore_nonexistent_returns_not_found(self, app_and_client):
        _, client = app_and_client
        resp = client.post("/item/does-not-exist/restore")
        assert resp.status_code == 404

    # -- SWITCH → 404 for not-found ------------------------------------

    def test_switch_nonexistent_returns_not_found(self, app_and_client):
        _, client = app_and_client
        resp = client.post("/item/does-not-exist/switch/rev1")
        assert resp.status_code == 404

    # -- SEARCH / LIST → 400 for bad query params ----------------------

    def test_list_returns_400_for_bad_query(self, app_and_client):
        _, client = app_and_client
        resp = client.get("/item?data_conditions=INVALID_JSON")
        assert resp.status_code == 400

    # -- Happy path still works ----------------------------------------

    def test_full_crud_lifecycle(self, app_and_client):
        """Sanity check: CRUD still works end-to-end."""
        _, client = app_and_client

        # Create
        resp = client.post("/item", json={"name": "Gadget", "price": 19.99})
        assert resp.status_code == 200
        resource_id = resp.json()["resource_id"]

        # Read
        resp = client.get(f"/item/{resource_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Gadget"

        # Update
        resp = client.put(
            f"/item/{resource_id}", json={"name": "Gadget v2", "price": 24.99}
        )
        assert resp.status_code == 200

        # Patch
        resp = client.patch(
            f"/item/{resource_id}",
            json=[{"op": "replace", "path": "/price", "value": 29.99}],
        )
        assert resp.status_code == 200

        # Delete
        resp = client.delete(f"/item/{resource_id}")
        assert resp.status_code == 200

        # Restore
        resp = client.post(f"/item/{resource_id}/restore")
        assert resp.status_code == 200

        # List
        resp = client.get("/item")
        assert resp.status_code == 200
