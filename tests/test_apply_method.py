"""Tests for AutoCRUD.apply() method — router, structs, auto_include params."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct

from autocrud.crud.core import AutoCRUD
from autocrud.resource_manager.storage_factory import MemoryStorageFactory

# ---------------------------------------------------------------------------
# Test models
# ---------------------------------------------------------------------------


class Item(Struct):
    name: str
    score: int = 0


class ExtraSchema(Struct):
    value: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_crud() -> AutoCRUD:
    return AutoCRUD(storage_factory=MemoryStorageFactory())


# ---------------------------------------------------------------------------
# Tests: apply(app) — FastAPI direct (auto openapi)
# ---------------------------------------------------------------------------


class TestApplyFastAPIAutoOpenapi:
    """When app is a FastAPI instance, openapi() should be called automatically."""

    def test_auto_openapi_sets_schema(self):
        crud = _make_crud()
        crud.add_model(Item, name="item")

        app = FastAPI()
        crud.apply(app)

        # openapi_schema should be set automatically
        assert app.openapi_schema is not None
        assert "components" in app.openapi_schema
        assert "Item" in app.openapi_schema["components"]["schemas"]

    def test_routes_are_functional(self):
        crud = _make_crud()
        crud.add_model(Item, name="item")

        app = FastAPI()
        crud.apply(app)

        client = TestClient(app)
        resp = client.post("/item", json={"name": "apple", "score": 10})
        assert resp.status_code == 200
        assert resp.json()["resource_id"].startswith("item:")

    def test_apply_with_structs(self):
        crud = _make_crud()
        crud.add_model(Item, name="item")

        app = FastAPI()
        crud.apply(app, structs=[ExtraSchema])

        assert app.openapi_schema is not None
        assert "ExtraSchema" in app.openapi_schema["components"]["schemas"]


# ---------------------------------------------------------------------------
# Tests: apply(api_router) — pure APIRouter (no openapi)
# ---------------------------------------------------------------------------


class TestApplyAPIRouterNoOpenapi:
    """When app is a bare APIRouter, openapi is not called."""

    def test_no_openapi_on_apirouter(self):
        crud = _make_crud()
        crud.add_model(Item, name="item")

        router = APIRouter()
        result = crud.apply(router)

        assert result is router
        # APIRouter has no openapi_schema attribute
        assert not hasattr(router, "openapi_schema")

    def test_routes_are_added_to_router(self):
        crud = _make_crud()
        crud.add_model(Item, name="item")

        router = APIRouter()
        crud.apply(router)

        # Include into an app manually to verify routes work
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.post("/item", json={"name": "banana", "score": 5})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Tests: apply(app, router=router) — auto include + auto openapi
# ---------------------------------------------------------------------------


class TestApplyWithRouter:
    """When router is provided, routes go to router; auto include + openapi on FastAPI."""

    def test_auto_include_and_openapi(self):
        crud = _make_crud()
        crud.add_model(Item, name="item")

        app = FastAPI()
        sub_router = APIRouter(prefix="/api")
        result = crud.apply(app, router=sub_router)

        # Routes are generated on sub_router
        assert result is sub_router

        # openapi_schema should be set (auto include happened)
        assert app.openapi_schema is not None

        # Routes should be reachable via the prefix
        client = TestClient(app)
        resp = client.post("/api/item", json={"name": "cherry", "score": 3})
        assert resp.status_code == 200

    def test_auto_include_false_no_include(self):
        crud = _make_crud()
        crud.add_model(Item, name="item")

        app = FastAPI()
        sub_router = APIRouter(prefix="/api")
        crud.apply(app, router=sub_router, auto_include=False)

        # openapi is NOT called (routes are not on app yet)
        assert app.openapi_schema is None

        # Routes under /api are NOT reachable
        client = TestClient(app)
        resp = client.post("/api/item", json={"name": "date", "score": 1})
        assert resp.status_code != 200  # 404 or 405

    def test_auto_include_false_manual_include_then_openapi(self):
        crud = _make_crud()
        crud.add_model(Item, name="item")

        app = FastAPI()
        sub_router = APIRouter(prefix="/api")
        crud.apply(app, router=sub_router, auto_include=False)

        # Manually include and regenerate openapi
        app.include_router(sub_router)
        app.openapi_schema = None  # Reset cached schema
        crud.openapi(app)

        client = TestClient(app)
        resp = client.post("/api/item", json={"name": "elderberry", "score": 7})
        assert resp.status_code == 200

    def test_router_with_structs(self):
        crud = _make_crud()
        crud.add_model(Item, name="item")

        app = FastAPI()
        sub_router = APIRouter(prefix="/api")
        crud.apply(app, router=sub_router, structs=[ExtraSchema])

        assert "ExtraSchema" in app.openapi_schema["components"]["schemas"]


# ---------------------------------------------------------------------------
# Tests: return value
# ---------------------------------------------------------------------------


class TestApplyReturnValue:
    """apply() should return the target router."""

    def test_returns_app_when_no_router(self):
        crud = _make_crud()
        crud.add_model(Item, name="item")

        app = FastAPI()
        result = crud.apply(app)
        assert result is app

    def test_returns_router_when_provided(self):
        crud = _make_crud()
        crud.add_model(Item, name="item")

        app = FastAPI()
        sub_router = APIRouter()
        result = crud.apply(app, router=sub_router)
        assert result is sub_router

    def test_returns_router_for_bare_apirouter(self):
        crud = _make_crud()
        crud.add_model(Item, name="item")

        router = APIRouter()
        result = crud.apply(router)
        assert result is router


# ---------------------------------------------------------------------------
# Tests: backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """Existing usage patterns should continue to work unchanged."""

    def test_apply_app_then_separate_openapi(self):
        """Old pattern: apply(app) + openapi(app) should still work.

        Since apply(app) now auto-calls openapi, calling openapi again
        should simply overwrite the schema (no error).
        """
        crud = _make_crud()
        crud.add_model(Item, name="item")

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)  # Should not raise

        assert app.openapi_schema is not None

    def test_apply_router_then_include_then_openapi(self):
        """Old pattern: apply(router) + include_router + openapi(app)."""
        crud = _make_crud()
        crud.add_model(Item, name="item")

        router = APIRouter(prefix="/v1")
        app = FastAPI()
        crud.apply(router)

        app.include_router(router)
        crud.openapi(app)

        client = TestClient(app)
        resp = client.post("/v1/item", json={"name": "fig", "score": 9})
        assert resp.status_code == 200
        assert app.openapi_schema is not None


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and special scenarios."""

    def test_apply_with_no_models(self):
        """apply() should not fail when no models are registered."""
        crud = _make_crud()
        app = FastAPI()
        crud.apply(app)
        assert app.openapi_schema is not None

    def test_auto_include_ignored_when_no_router(self):
        """auto_include has no effect when router is None."""
        crud = _make_crud()
        crud.add_model(Item, name="item")

        app = FastAPI()
        crud.apply(app, auto_include=False)

        # Routes should still be directly on app
        client = TestClient(app)
        resp = client.post("/item", json={"name": "grape", "score": 4})
        assert resp.status_code == 200

    def test_auto_include_ignored_when_app_is_apirouter(self):
        """When app is APIRouter, auto_include and router param are processed
        but no openapi or include_router is attempted."""
        crud = _make_crud()
        crud.add_model(Item, name="item")

        parent_router = APIRouter()
        child_router = APIRouter(prefix="/sub")
        result = crud.apply(parent_router, router=child_router)

        # Routes should be on child_router
        assert result is child_router
        # No openapi_schema since parent is not FastAPI
        assert not hasattr(parent_router, "openapi_schema")
