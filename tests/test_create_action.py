"""Tests for @crud.create_action() decorator.

Covers:
- Decorator stores pending action metadata
- apply() registers route on the router
- POST to custom action endpoint → auto create via resource_manager
- Handler return None → no auto create
- Handler supports Body(), Path(), Query(), Depends() via standard FastAPI
- Multiple actions on same resource
- OpenAPI schema includes x-autocrud-create-action extension
- Import order: decorator before add_model works
- Unknown resource_name logs warning and is skipped
- Pydantic model as Body type
- UploadFile parameter (single and mixed with other param types)
"""

import datetime as dt
from typing import Annotated, Literal

import pytest
from fastapi import Body, FastAPI, Query, UploadFile
from fastapi.testclient import TestClient
from msgspec import Struct

from autocrud import struct_to_pydantic
from autocrud.crud.core import AutoCRUD
from autocrud.types import OnDelete, Ref, RefType

# ---------------------------------------------------------------------------
# Test Models
# ---------------------------------------------------------------------------


class Article(Struct):
    content: str


class ImportFromUrl(Struct):
    url: str


class ImportFromMultiple(Struct):
    urls: list[str]
    separator: str = "\n"


# ---------------------------------------------------------------------------
# 1. Decorator stores pending actions
# ---------------------------------------------------------------------------


class TestCreateActionDecorator:
    """@crud.create_action() stores metadata without registering routes."""

    def test_decorator_stores_pending_action(self):
        crud = AutoCRUD()
        crud.add_model(Article, name="article")

        @crud.create_action("article", label="Import from URL")
        async def import_from_url(body: ImportFromUrl = Body(...)):
            return Article(content=body.url)

        assert len(crud._pending_create_actions) == 1
        action = crud._pending_create_actions[0]
        assert action.resource_name == "article"
        assert action.label == "Import from URL"
        assert action.handler is import_from_url

    def test_decorator_returns_original_function(self):
        crud = AutoCRUD()

        @crud.create_action("article", label="Import")
        async def import_from_url(body: ImportFromUrl = Body(...)):
            return Article(content=body.url)

        # Decorator should return the original function unchanged
        assert import_from_url.__name__ == "import_from_url"

    def test_path_inferred_from_function_name(self):
        crud = AutoCRUD()

        @crud.create_action("article", label="Import from URL")
        async def import_from_url(body: ImportFromUrl = Body(...)):
            return Article(content=body.url)

        action = crud._pending_create_actions[0]
        assert action.path == "import-from-url"

    def test_path_explicit_override(self):
        crud = AutoCRUD()

        @crud.create_action("article", path="custom-import", label="Import")
        async def import_from_url(body: ImportFromUrl = Body(...)):
            return Article(content=body.url)

        action = crud._pending_create_actions[0]
        assert action.path == "custom-import"

    def test_label_inferred_from_path(self):
        crud = AutoCRUD()

        @crud.create_action("article")
        async def import_from_url(body: ImportFromUrl = Body(...)):
            return Article(content=body.url)

        action = crud._pending_create_actions[0]
        # Should have some sensible label derived from function name or path
        assert action.label is not None
        assert len(action.label) > 0

    def test_multiple_actions_on_same_resource(self):
        crud = AutoCRUD()

        @crud.create_action("article", label="Import from URL")
        async def import_from_url(body: ImportFromUrl = Body(...)):
            return Article(content=body.url)

        @crud.create_action("article", label="Import from Multiple URLs")
        async def import_from_multiple(body: ImportFromMultiple = Body(...)):
            return Article(content=body.separator.join(body.urls))

        assert len(crud._pending_create_actions) == 2

    def test_decorator_before_add_model(self):
        """Decorator can be used before add_model — lazy registration."""
        crud = AutoCRUD()

        @crud.create_action("article", label="Import from URL")
        async def import_from_url(body: ImportFromUrl = Body(...)):
            return Article(content=body.url)

        # add_model comes AFTER the decorator
        crud.add_model(Article, name="article")

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post(
            "/article/import-from-url", json={"url": "https://example.com"}
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 2. Route registration & HTTP flow
# ---------------------------------------------------------------------------


class TestCreateActionRouteRegistration:
    """apply() registers the create action route on the router."""

    @pytest.fixture
    def crud_and_client(self):
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Article, name="article")

        @crud.create_action("article", label="Import from URL")
        async def import_from_url(body: ImportFromUrl = Body(...)):
            return Article(content=f"imported:{body.url}")

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)
        return crud, client

    def test_post_custom_action_creates_resource(self, crud_and_client):
        crud, client = crud_and_client
        resp = client.post(
            "/article/import-from-url", json={"url": "https://example.com"}
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should return RevisionInfo with resource_id and revision_id
        assert "resource_id" in data
        assert "revision_id" in data

        # Verify the resource was actually created
        rm = crud.resource_managers["article"]
        resource = rm.get(data["resource_id"])
        assert resource.data.content == "imported:https://example.com"

    def test_handler_return_none_skips_create(self):
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Article, name="article")

        @crud.create_action("article", label="Dry run import")
        async def dry_run_import(body: ImportFromUrl = Body(...)):
            # Return None → no auto create
            return None

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post(
            "/article/dry-run-import", json={"url": "https://example.com"}
        )
        # Should still succeed but return null (no RevisionInfo)
        assert resp.status_code == 200
        assert resp.json() is None

    def test_handler_with_query_params(self):
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Article, name="article")

        @crud.create_action("article", label="Import with prefix")
        async def import_with_prefix(
            body: ImportFromUrl = Body(...),
            prefix: str = Query("default"),
        ):
            return Article(content=f"{prefix}:{body.url}")

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post(
            "/article/import-with-prefix?prefix=custom",
            json={"url": "https://example.com"},
        )
        assert resp.status_code == 200
        data = resp.json()
        rm = crud.resource_managers["article"]
        resource = rm.get(data["resource_id"])
        assert resource.data.content == "custom:https://example.com"

    def test_standard_create_still_works(self, crud_and_client):
        """Standard POST /article (autocrud create) should still work."""
        crud, client = crud_and_client
        resp = client.post("/article", json={"content": "hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert "resource_id" in data

    def test_unknown_resource_name_logs_warning(self, caplog):
        crud = AutoCRUD()

        @crud.create_action("nonexistent", label="Test")
        async def test_action(body: ImportFromUrl = Body(...)):
            return Article(content=body.url)

        crud.add_model(Article, name="article")
        app = FastAPI()

        import logging

        with caplog.at_level(logging.WARNING):
            crud.apply(app)

        assert any("nonexistent" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# 3. OpenAPI extension
# ---------------------------------------------------------------------------


class TestCreateActionOpenAPI:
    """OpenAPI schema includes x-autocrud-create-action extension."""

    def _build_app(self):
        crud = AutoCRUD()
        crud.add_model(Article, name="article")

        @crud.create_action("article", label="Import from URL")
        async def import_from_url(body: ImportFromUrl = Body(...)):
            return Article(content=body.url)

        @crud.create_action("article", label="Import from Multiple")
        async def import_from_multiple(body: ImportFromMultiple = Body(...)):
            return Article(content=",".join(body.urls))

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)
        return app

    def test_operation_has_x_autocrud_create_action(self):
        """Each custom POST operation should have x-autocrud-create-action."""
        app = self._build_app()
        schema = app.openapi_schema
        paths = schema["paths"]

        op = paths["/article/import-from-url"]["post"]
        assert "x-autocrud-create-action" in op
        assert op["x-autocrud-create-action"]["resource"] == "article"
        assert op["x-autocrud-create-action"]["label"] == "Import from URL"

    def test_top_level_custom_create_actions(self):
        """OpenAPI schema should have x-autocrud-custom-create-actions."""
        app = self._build_app()
        schema = app.openapi_schema

        assert "x-autocrud-custom-create-actions" in schema
        actions = schema["x-autocrud-custom-create-actions"]
        assert "article" in actions
        assert len(actions["article"]) == 2
        labels = {a["label"] for a in actions["article"]}
        assert "Import from URL" in labels
        assert "Import from Multiple" in labels

    def test_custom_action_request_body_schema_in_components(self):
        """Request body schemas for custom actions should be in components."""
        app = self._build_app()
        schema = app.openapi_schema
        components = schema["components"]["schemas"]
        assert "ImportFromUrl" in components
        assert "ImportFromMultiple" in components

    def test_action_path_in_top_level_extension(self):
        """Each action in x-autocrud-custom-create-actions should include path."""
        app = self._build_app()
        schema = app.openapi_schema
        actions = schema["x-autocrud-custom-create-actions"]["article"]
        paths = {a["path"] for a in actions}
        assert "/article/import-from-url" in paths
        assert "/article/import-from-multiple" in paths

    def test_body_schema_in_top_level_extension(self):
        """Each action should include bodySchema for generator discovery."""
        app = self._build_app()
        schema = app.openapi_schema
        actions = schema["x-autocrud-custom-create-actions"]["article"]
        schemas = {a["bodySchema"] for a in actions}
        assert "ImportFromUrl" in schemas
        assert "ImportFromMultiple" in schemas


# ---------------------------------------------------------------------------
# 4. Pydantic model support
# ---------------------------------------------------------------------------


class TestCreateActionPydantic:
    """Custom create action handler with Pydantic Body type."""

    def test_pydantic_body_type(self):
        try:
            from pydantic import BaseModel
        except ImportError:
            pytest.skip("pydantic not installed")

        class PydanticImport(BaseModel):
            url: str
            timeout: int = 30

        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Article, name="article")

        @crud.create_action("article", label="Pydantic Import")
        async def pydantic_import(body: PydanticImport = Body(...)):
            return Article(content=f"{body.url}:{body.timeout}")

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post(
            "/article/pydantic-import",
            json={"url": "https://example.com", "timeout": 60},
        )
        assert resp.status_code == 200
        data = resp.json()
        rm = crud.resource_managers["article"]
        resource = rm.get(data["resource_id"])
        assert resource.data.content == "https://example.com:60"


# ---------------------------------------------------------------------------
# 5. Sync handler support
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 9. Scalar-param handler (no explicit Body Struct)
# ---------------------------------------------------------------------------


class TestCreateActionScalarParams:
    """Handler with simple scalar params (str, int...) should work as query params."""

    def test_scalar_params_sent_as_query_params(self):
        """POST with query params should work when handler uses simple scalar params."""

        class Character(Struct):
            name: str
            level: int = 1

        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Character, name="character")

        @crud.create_action("character", label="New Character")
        async def create_new_character(
            name: str,
        ):
            return Character(name=name, level=1)

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        # name is a query parameter — send via URL query string
        resp = client.post(
            "/character/create-new-character",
            params={"name": "Hero"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "resource_id" in data

        rm = crud.resource_managers["character"]
        resource = rm.get(data["resource_id"])
        assert resource.data.name == "Hero"

    def test_scalar_params_openapi_extension_has_query_params(self):
        """OpenAPI extension should expose queryParams for scalar-param handlers."""

        class Character(Struct):
            name: str
            level: int = 1

        crud = AutoCRUD()
        crud.add_model(Character, name="character")

        @crud.create_action("character", label="New Character")
        async def create_new_character(
            name: str,
        ):
            return Character(name=name, level=1)

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)

        schema = app.openapi_schema
        custom_actions = schema.get("x-autocrud-custom-create-actions", {})
        assert "character" in custom_actions
        actions = custom_actions["character"]
        assert len(actions) == 1
        action = actions[0]
        # Should expose queryParams (NOT bodySchema) for scalar params
        assert "queryParams" in action, (
            "queryParams is required for frontend form generation when the "
            "handler uses plain scalar parameters"
        )
        assert "bodySchema" not in action
        qp = action["queryParams"]
        assert len(qp) == 1
        assert qp[0]["name"] == "name"
        assert qp[0]["required"] is True

    def test_scalar_params_with_default_optional_query_param(self):
        """Optional scalar params (with default) should be non-required query params."""

        class Character(Struct):
            name: str
            level: int = 1

        crud = AutoCRUD()
        crud.add_model(Character, name="character")

        @crud.create_action("character", label="New Character")
        async def create_new_character(name: str, level: int = 1):
            return Character(name=name, level=level)

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)

        schema = app.openapi_schema
        custom_actions = schema.get("x-autocrud-custom-create-actions", {})
        qp = custom_actions["character"][0]["queryParams"]
        qp_by_name = {p["name"]: p for p in qp}
        assert qp_by_name["name"]["required"] is True
        assert qp_by_name["level"]["required"] is False


class TestCreateActionPathParams:
    """Custom create action where params are path parameters (e.g. path='/{name}/new')."""

    def test_path_params_sent_as_path_params(self):
        """Handler using path like /{name}/new — name should be a path param."""

        class Character(Struct):
            name: str
            level: int = 1

        crud = AutoCRUD()
        crud.add_model(Character, name="character")

        @crud.create_action("character", label="New Character", path="/{name}/new")
        async def create_new_character(name: str):
            return Character(name=name, level=1)

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        # name is a path param — pass it in the URL
        resp = client.post("/character/Hero/new")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        rm = crud.resource_managers["character"]
        resource = rm.get(data["resource_id"])
        assert resource.data.name == "Hero"

    def test_path_params_openapi_extension_has_path_params(self):
        """pathParams should be injected into x-autocrud-custom-create-actions."""

        class Character(Struct):
            name: str
            level: int = 1

        crud = AutoCRUD()
        crud.add_model(Character, name="character")

        @crud.create_action("character", label="New Character", path="/{name}/new")
        async def create_new_character(name: str):
            return Character(name=name, level=1)

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)

        schema = app.openapi_schema
        custom_actions = schema.get("x-autocrud-custom-create-actions", {})
        assert "character" in custom_actions
        action = custom_actions["character"][0]
        assert "pathParams" in action, (
            "pathParams must be injected for path-based params"
        )
        assert "bodySchema" not in action
        pp = action["pathParams"]
        assert len(pp) == 1
        assert pp[0]["name"] == "name"
        assert pp[0]["required"] is True

    def test_path_and_query_params_combined(self):
        """Handler with both path and query params — both should be injected."""

        class Character(Struct):
            name: str
            level: int = 1

        crud = AutoCRUD()
        crud.add_model(Character, name="character")

        @crud.create_action("character", label="New Character", path="/{name}/new")
        async def create_new_character(name: str, level: int = 1):
            return Character(name=name, level=level)

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)
        client = TestClient(app)

        # name in path, level as query param
        resp = client.post("/character/Hero/new", params={"level": 5})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        rm = crud.resource_managers["character"]
        resource = rm.get(data["resource_id"])
        assert resource.data.name == "Hero"
        assert resource.data.level == 5

        schema = app.openapi_schema
        action = schema["x-autocrud-custom-create-actions"]["character"][0]
        assert "pathParams" in action
        assert action["pathParams"][0]["name"] == "name"
        assert "queryParams" in action
        assert action["queryParams"][0]["name"] == "level"


class TestCreateActionInlineBodyParams:
    """Custom create action with Annotated[T, Body(embed=True)] scalar params."""

    def test_inline_body_params_endpoint_works(self):
        """Handler with Body(embed=True) params should receive values from JSON body."""

        class Character(Struct):
            name: str
            level: int = 1

        crud = AutoCRUD()
        crud.add_model(Character, name="character")

        @crud.create_action("character", label="New Character3")
        async def create_new_character3(
            name: Annotated[str, Body(embed=True)],
            name1: Annotated[str, Body(embed=True)],
            name2: Annotated[str, Body(embed=True)],
        ):
            return Character(name=name + name1 + name2)

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post(
            "/character/create-new-character3",
            json={"name": "A", "name1": "B", "name2": "C"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        rm = crud.resource_managers["character"]
        resource = rm.get(data["resource_id"])
        assert resource.data.name == "ABC"

    def test_inline_body_params_openapi_extension(self):
        """inlineBodyParams should be injected into x-autocrud-custom-create-actions."""

        class Character(Struct):
            name: str
            level: int = 1

        crud = AutoCRUD()
        crud.add_model(Character, name="character")

        @crud.create_action("character", label="New Character3")
        async def create_new_character3(
            name: Annotated[str, Body(embed=True)],
            name1: Annotated[str, Body(embed=True)],
            name2: Annotated[str, Body(embed=True)],
        ):
            return Character(name=name + name1 + name2)

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)

        schema = app.openapi_schema
        action = schema["x-autocrud-custom-create-actions"]["character"][0]
        assert "inlineBodyParams" in action, (
            "inlineBodyParams must be injected for Body(embed=True) params"
        )
        assert "bodySchema" not in action
        assert "queryParams" not in action
        ibp = action["inlineBodyParams"]
        ibp_by_name = {p["name"]: p for p in ibp}
        assert "name" in ibp_by_name
        assert "name1" in ibp_by_name
        assert "name2" in ibp_by_name
        assert ibp_by_name["name"]["required"] is True

    def test_inline_body_params_optional(self):
        """Body(embed=True) params with defaults should be non-required."""

        class Character(Struct):
            name: str
            level: int = 1

        crud = AutoCRUD()
        crud.add_model(Character, name="character")

        @crud.create_action("character", label="Test")
        async def test_action(
            name: Annotated[str, Body(embed=True)],
            level: Annotated[int, Body(embed=True)] = 1,
        ):
            return Character(name=name, level=level)

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)

        schema = app.openapi_schema
        action = schema["x-autocrud-custom-create-actions"]["character"][0]
        ibp_by_name = {p["name"]: p for p in action["inlineBodyParams"]}
        assert ibp_by_name["name"]["required"] is True
        assert ibp_by_name["level"]["required"] is False


class TestCreateActionDuplicateLabel:
    """Two create_actions with the same label on the same resource."""

    def _make_app(self):
        crud = AutoCRUD(default_user="tester", default_now=dt.datetime.now)
        crud.add_model(Article, name="article")

        @crud.create_action("article", label="Import")
        async def import_a(body: ImportFromUrl = Body(...)):
            return Article(content=f"a:{body.url}")

        @crud.create_action("article", label="Import")  # duplicate label
        async def import_b(body: ImportFromUrl = Body(...)):
            return Article(content=f"b:{body.url}")

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)
        return app, crud

    def test_duplicate_label_warns(self):
        with pytest.warns(UserWarning, match="already has a create action with label"):
            app, _ = self._make_app()
        actions = app.openapi_schema["x-autocrud-custom-create-actions"]["article"]
        assert len(actions) == 2

    def test_both_actions_still_registered(self):
        app, _ = self._make_app()
        actions = app.openapi_schema["x-autocrud-custom-create-actions"]["article"]
        op_ids = {a["operationId"] for a in actions}
        assert "import_a" in op_ids
        assert "import_b" in op_ids

    def test_both_endpoints_callable(self):
        from fastapi.testclient import TestClient

        app, _ = self._make_app()
        client = TestClient(app)

        resp_a = client.post("/article/import-a", json={"url": "http://a.example"})
        assert resp_a.status_code == 200

        resp_b = client.post("/article/import-b", json={"url": "http://b.example"})
        assert resp_b.status_code == 200


class TestCreateActionSyncHandler:
    """Custom create action handler that is synchronous (not async)."""

    def test_sync_handler(self):
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Article, name="article")

        @crud.create_action("article", label="Sync Import")
        def sync_import(body: ImportFromUrl = Body(...)):
            return Article(content=f"sync:{body.url}")

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post(
            "/article/sync-import",
            json={"url": "https://example.com"},
        )
        assert resp.status_code == 200
        data = resp.json()
        rm = crud.resource_managers["article"]
        resource = rm.get(data["resource_id"])
        assert resource.data.content == "sync:https://example.com"


# ---------------------------------------------------------------------------
# UploadFile parameter tests
# ---------------------------------------------------------------------------


class TestCreateActionFileParams:
    """UploadFile params are extracted as fileParams in the OpenAPI extension."""

    def _make_crud_with_file_only(self):
        crud = AutoCRUD(default_user="tester", default_now=dt.datetime.now)
        crud.add_model(Article, name="article")

        @crud.create_action("article", label="Upload File")
        async def upload_file(z: UploadFile):
            content = await z.read()
            return Article(content=f"file:{z.filename}:{len(content)}")

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)
        return app, crud

    def test_file_param_openapi_extension(self):
        """UploadFile param produces fileParams in x-autocrud-custom-create-actions."""
        app, _ = self._make_crud_with_file_only()
        actions = app.openapi_schema["x-autocrud-custom-create-actions"]["article"]
        assert len(actions) == 1
        action = actions[0]
        assert "fileParams" in action
        assert len(action["fileParams"]) == 1
        fp = action["fileParams"][0]
        assert fp["name"] == "z"
        assert fp["schema"]["type"] == "string"
        assert fp["schema"]["format"] == "binary"
        # Should NOT have inlineBodyParams or bodySchema
        assert "inlineBodyParams" not in action
        assert "bodySchema" not in action

    def test_file_param_endpoint_works(self):
        """Multipart file upload via custom create action endpoint works."""
        app, crud = self._make_crud_with_file_only()
        client = TestClient(app)
        resp = client.post(
            "/article/upload-file",
            files={"z": ("hello.txt", b"hello world", "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()
        rm = crud.resource_managers["article"]
        resource = rm.get(data["resource_id"])
        assert resource.data.content == "file:hello.txt:11"


class TestCreateActionMixedFileParams:
    """Mixed query + inline body + UploadFile params all coexist."""

    def _make_crud_mixed(self):
        crud = AutoCRUD(default_user="tester", default_now=dt.datetime.now)
        crud.add_model(Article, name="article")

        @crud.create_action("article", label="Mixed Upload")
        async def mixed_upload(
            x: int,
            name: Annotated[str, Body(embed=True)],
            z: UploadFile,
        ):
            content_bytes = await z.read()
            return Article(
                content=f"{name} x={x} file={z.filename}:{len(content_bytes)}"
            )

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)
        return app, crud

    def test_mixed_openapi_extension(self):
        """Mixed params are categorised into queryParams, inlineBodyParams, fileParams."""
        app, _ = self._make_crud_mixed()
        actions = app.openapi_schema["x-autocrud-custom-create-actions"]["article"]
        assert len(actions) == 1
        action = actions[0]

        # queryParams: x
        assert "queryParams" in action
        qp_names = {p["name"] for p in action["queryParams"]}
        assert qp_names == {"x"}

        # inlineBodyParams: name  (NOT file — only non-file body fields)
        assert "inlineBodyParams" in action
        ibp_names = {p["name"] for p in action["inlineBodyParams"]}
        assert ibp_names == {"name"}

        # fileParams: z
        assert "fileParams" in action
        fp_names = {p["name"] for p in action["fileParams"]}
        assert fp_names == {"z"}

    def test_mixed_endpoint_works(self):
        """Mixed query + body + file endpoint returns the expected resource."""
        app, crud = self._make_crud_mixed()
        client = TestClient(app)
        resp = client.post(
            "/article/mixed-upload",
            params={"x": 42},
            data={"name": "Alice"},
            files={"z": ("doc.pdf", b"pdf-content", "application/pdf")},
        )
        assert resp.status_code == 200
        data = resp.json()
        rm = crud.resource_managers["article"]
        resource = rm.get(data["resource_id"])
        assert resource.data.content == "Alice x=42 file=doc.pdf:11"


# ---------------------------------------------------------------------------
# Enum parameter tests
# ---------------------------------------------------------------------------


class TestCreateActionEnumParams:
    """Literal/enum params should preserve enum values in the OpenAPI extension."""

    def test_query_param_enum_preserved(self):
        """Literal query param should include enum values in queryParams schema."""

        class Character(Struct):
            name: str
            role: str = "warrior"

        crud = AutoCRUD()
        crud.add_model(Character, name="character")

        @crud.create_action("character", label="New Character")
        async def create_character(
            name: str,
            role: Literal["warrior", "mage", "archer"] = "warrior",
        ):
            return Character(name=name, role=role)

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)

        schema = app.openapi_schema
        action = schema["x-autocrud-custom-create-actions"]["character"][0]
        assert "queryParams" in action
        qp_by_name = {p["name"]: p for p in action["queryParams"]}
        assert "role" in qp_by_name
        role_schema = qp_by_name["role"]["schema"]
        assert "enum" in role_schema, "Literal type should produce enum in the schema"
        assert set(role_schema["enum"]) == {"warrior", "mage", "archer"}

    def test_inline_body_param_enum_preserved(self):
        """Literal inline body param should include enum values in inlineBodyParams."""

        class Character(Struct):
            name: str
            role: str = "warrior"

        crud = AutoCRUD()
        crud.add_model(Character, name="character")

        @crud.create_action("character", label="New Character")
        async def create_character(
            name: Annotated[str, Body(embed=True)],
            role: Annotated[
                Literal["warrior", "mage", "archer"], Body(embed=True)
            ] = "warrior",
        ):
            return Character(name=name, role=role)

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)

        schema = app.openapi_schema
        action = schema["x-autocrud-custom-create-actions"]["character"][0]
        assert "inlineBodyParams" in action
        ibp_by_name = {p["name"]: p for p in action["inlineBodyParams"]}
        assert "role" in ibp_by_name
        role_schema = ibp_by_name["role"]["schema"]
        assert "enum" in role_schema, (
            "Literal type in Body(embed=True) should produce enum in schema"
        )
        assert set(role_schema["enum"]) == {"warrior", "mage", "archer"}

    def test_enum_query_param_endpoint_works(self):
        """Enum query param should actually work at runtime."""

        class Character(Struct):
            name: str
            role: str = "warrior"

        crud = AutoCRUD(default_user="tester", default_now=dt.datetime.now)
        crud.add_model(Character, name="character")

        @crud.create_action("character", label="New Character")
        async def create_character(
            name: str,
            role: Literal["warrior", "mage", "archer"] = "warrior",
        ):
            return Character(name=name, role=role)

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post(
            "/character/create-character",
            params={"name": "Hero", "role": "mage"},
        )
        assert resp.status_code == 200
        data = resp.json()
        rm = crud.resource_managers["character"]
        resource = rm.get(data["resource_id"])
        assert resource.data.role == "mage"


# ---------------------------------------------------------------------------
# 9. Ref metadata injection for custom create action body schemas
# ---------------------------------------------------------------------------


class _RefZone(Struct):
    name: str


class _RefGuild(Struct):
    name: str


class _RefMonster(Struct):
    name: str
    zone_id: Annotated[str, Ref("zone")]
    guild_id: Annotated[str | None, Ref("guild", on_delete=OnDelete.set_null)]


class _RefImportMonster(Struct):
    """Action body schema with Ref annotations."""

    url: str
    zone_id: Annotated[str, Ref("zone")]
    guild_id: Annotated[str | None, Ref("guild", on_delete=OnDelete.set_null)]
    zone_revision_id: Annotated[str, Ref("zone", ref_type=RefType.revision_id)]


class TestCreateActionRefMetadata:
    """x-ref-* metadata should be injected into custom action body schemas."""

    def _build_app(self):
        crud = AutoCRUD()
        crud.add_model(_RefZone, name="zone")
        crud.add_model(_RefGuild, name="guild")
        crud.add_model(_RefMonster, name="monster")

        @crud.create_action("monster", label="Import Monster")
        async def import_monster(body: _RefImportMonster = Body(...)):
            return _RefMonster(
                name="imported",
                zone_id=body.zone_id,
                guild_id=body.guild_id,
            )

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)
        return app

    def test_action_body_schema_has_x_ref_resource(self):
        """Action body schema properties should have x-ref-resource."""
        app = self._build_app()
        schema = app.openapi_schema
        body_schema = schema["components"]["schemas"]["_RefImportMonster"]
        props = body_schema["properties"]

        assert props["zone_id"]["x-ref-resource"] == "zone"
        assert props["zone_id"]["x-ref-type"] == "resource_id"
        assert props["zone_id"]["x-ref-on-delete"] == "dangling"

    def test_action_body_schema_nullable_ref(self):
        """Nullable Ref in action body should still get x-ref-* extensions."""
        app = self._build_app()
        schema = app.openapi_schema
        body_schema = schema["components"]["schemas"]["_RefImportMonster"]
        props = body_schema["properties"]

        assert props["guild_id"]["x-ref-resource"] == "guild"
        assert props["guild_id"]["x-ref-type"] == "resource_id"
        assert props["guild_id"]["x-ref-on-delete"] == "set_null"

    def test_action_body_schema_revision_ref(self):
        """Revision ref in action body should get correct x-ref-type."""
        app = self._build_app()
        schema = app.openapi_schema
        body_schema = schema["components"]["schemas"]["_RefImportMonster"]
        props = body_schema["properties"]

        assert props["zone_revision_id"]["x-ref-resource"] == "zone"
        assert props["zone_revision_id"]["x-ref-type"] == "revision_id"
        assert "x-ref-on-delete" not in props["zone_revision_id"]

    def test_action_body_refs_included_in_relationships(self):
        """Refs from action body schemas should appear in x-autocrud-relationships."""
        app = self._build_app()
        schema = app.openapi_schema
        rels = schema.get("x-autocrud-relationships", [])

        # Find refs from action body (source = "monster" since action belongs to monster)
        action_ref_fields = {r["sourceField"] for r in rels if r["source"] == "monster"}
        # Should include refs from both the resource model AND the action body
        assert "zone_id" in action_ref_fields
        assert "guild_id" in action_ref_fields
        assert "zone_revision_id" in action_ref_fields


# ---------------------------------------------------------------------------
# 10. Ref metadata injection for path / query / inline-body params
# ---------------------------------------------------------------------------


class _PEquipment(Struct):
    name: str


class _PCharacter(Struct):
    name: str
    equipment_id: Annotated[
        str | None, Ref("pequipment", on_delete=OnDelete.set_null)
    ] = None


class TestCreateActionParamRefMetadata:
    """x-ref-* should be injected into path/query/inline-body param schemas."""

    def _build_app_path_param(self):
        crud = AutoCRUD()
        crud.add_model(_PEquipment, name="pequipment")
        crud.add_model(_PCharacter, name="pcharacter")

        @crud.create_action("pcharacter", label="Quick Create", path="/{eq_id}/quick")
        async def quick_create(
            eq_id: Annotated[str, Ref("pequipment")],
        ):
            return _PCharacter(name="test", equipment_id=eq_id)

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)
        return app

    def test_path_param_has_x_ref(self):
        """Path param with Ref annotation should have x-ref-* in its schema."""
        app = self._build_app_path_param()
        schema = app.openapi_schema
        actions = schema["x-autocrud-custom-create-actions"]["pcharacter"]
        action = actions[0]
        pp = action["pathParams"]
        eq_param = next(p for p in pp if p["name"] == "eq_id")
        assert eq_param["schema"]["x-ref-resource"] == "pequipment"
        assert eq_param["schema"]["x-ref-type"] == "resource_id"
        assert eq_param["schema"]["x-ref-on-delete"] == "dangling"

    def _build_app_query_param(self):
        crud = AutoCRUD()
        crud.add_model(_PEquipment, name="pequipment")
        crud.add_model(_PCharacter, name="pcharacter")

        @crud.create_action("pcharacter", label="Query Create")
        async def query_create(
            name: str,
            eq_id: Annotated[str, Ref("pequipment", ref_type=RefType.revision_id)],
        ):
            return _PCharacter(name=name, equipment_id=eq_id)

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)
        return app

    def test_query_param_has_x_ref(self):
        """Query param with Ref annotation should have x-ref-* in its schema."""
        app = self._build_app_query_param()
        schema = app.openapi_schema
        actions = schema["x-autocrud-custom-create-actions"]["pcharacter"]
        action = actions[0]
        qp = action["queryParams"]
        eq_param = next(p for p in qp if p["name"] == "eq_id")
        assert eq_param["schema"]["x-ref-resource"] == "pequipment"
        assert eq_param["schema"]["x-ref-type"] == "revision_id"
        # revision_id refs should not have x-ref-on-delete
        assert "x-ref-on-delete" not in eq_param["schema"]

    def _build_app_inline_body_param(self):
        crud = AutoCRUD()
        crud.add_model(_PEquipment, name="pequipment")
        crud.add_model(_PCharacter, name="pcharacter")

        @crud.create_action("pcharacter", label="Inline Create")
        async def inline_create(
            name: Annotated[str, Body(embed=True)],
            eq_id: Annotated[str, Ref("pequipment"), Body(embed=True)],
        ):
            return _PCharacter(name=name, equipment_id=eq_id)

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)
        return app

    def test_inline_body_param_has_x_ref(self):
        """Inline body param with Ref annotation should have x-ref-* in its schema."""
        app = self._build_app_inline_body_param()
        schema = app.openapi_schema
        actions = schema["x-autocrud-custom-create-actions"]["pcharacter"]
        action = actions[0]
        ibp = action["inlineBodyParams"]
        eq_param = next(p for p in ibp if p["name"] == "eq_id")
        assert eq_param["schema"]["x-ref-resource"] == "pequipment"
        assert eq_param["schema"]["x-ref-type"] == "resource_id"
        assert eq_param["schema"]["x-ref-on-delete"] == "dangling"


# ---------------------------------------------------------------------------
# 11. Mixed body schema + inline/file params: coexistence
# ---------------------------------------------------------------------------


class _MixedItem(Struct):
    label: str
    value: int = 0


class _MixedResource(Struct):
    name: str


class TestCreateActionMixedParams:
    """When action has BOTH a Struct/Pydantic body AND inline body/file params,
    all param types should be extracted into the action extension."""

    def _build_app(self):
        crud = AutoCRUD()
        crud.add_model(_PEquipment, name="pequipment")
        crud.add_model(_MixedResource, name="mresource")

        _MixedItemPydantic = struct_to_pydantic(_MixedItem)

        @crud.create_action("mresource", label="Mixed Action")
        async def mixed_action(
            q: str,
            name: Annotated[str, Body(embed=True), Ref("pequipment")],
            pic: UploadFile,
            item: _MixedItemPydantic,  # type: ignore[reportInvalidTypeForm]
        ):
            return _MixedResource(name=name)

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)
        return app

    def test_body_schema_present(self):
        """bodySchema should be detected for the Pydantic model param."""
        app = self._build_app()
        schema = app.openapi_schema
        actions = schema["x-autocrud-custom-create-actions"]["mresource"]
        action = actions[0]
        assert "bodySchema" in action

    def test_inline_body_params_extracted_with_body_schema(self):
        """Inline body params should still be extracted even when bodySchema exists."""
        app = self._build_app()
        schema = app.openapi_schema
        actions = schema["x-autocrud-custom-create-actions"]["mresource"]
        action = actions[0]
        assert "inlineBodyParams" in action
        ibp_names = {p["name"] for p in action["inlineBodyParams"]}
        assert "name" in ibp_names

    def test_file_params_extracted_with_body_schema(self):
        """File params should still be extracted even when bodySchema exists."""
        app = self._build_app()
        schema = app.openapi_schema
        actions = schema["x-autocrud-custom-create-actions"]["mresource"]
        action = actions[0]
        assert "fileParams" in action
        fp_names = {p["name"] for p in action["fileParams"]}
        assert "pic" in fp_names

    def test_inline_body_param_ref_with_body_schema(self):
        """Inline body param Ref should work even when bodySchema coexists."""
        app = self._build_app()
        schema = app.openapi_schema
        actions = schema["x-autocrud-custom-create-actions"]["mresource"]
        action = actions[0]
        name_param = next(p for p in action["inlineBodyParams"] if p["name"] == "name")
        assert name_param["schema"]["x-ref-resource"] == "pequipment"
        assert name_param["schema"]["x-ref-type"] == "resource_id"

    def test_query_params_still_present(self):
        """Query params should still work alongside bodySchema."""
        app = self._build_app()
        schema = app.openapi_schema
        actions = schema["x-autocrud-custom-create-actions"]["mresource"]
        action = actions[0]
        assert "queryParams" in action
        qp_names = {p["name"] for p in action["queryParams"]}
        assert "q" in qp_names

    def test_body_schema_field_not_in_inline_params(self):
        """The Pydantic model field should NOT appear in inlineBodyParams (avoid duplication)."""
        app = self._build_app()
        schema = app.openapi_schema
        actions = schema["x-autocrud-custom-create-actions"]["mresource"]
        action = actions[0]
        ibp_names = {p["name"] for p in action.get("inlineBodyParams", [])}
        assert "item" not in ibp_names

    def test_body_schema_param_name(self):
        """bodySchemaParamName should record the handler parameter name (not schema name)."""
        app = self._build_app()
        schema = app.openapi_schema
        actions = schema["x-autocrud-custom-create-actions"]["mresource"]
        action = actions[0]
        # The handler parameter for the Pydantic model is called 'item'
        assert action.get("bodySchemaParamName") == "item"
