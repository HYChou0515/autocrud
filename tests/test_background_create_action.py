"""Tests for background create action (async_mode='background').

Covers:
- Decorator accepts async_mode='background' and stores it in _PendingCreateAction
- apply() does NOT generate a Job model for background actions
- POST to background action → HTTP 202 + BackgroundTaskAccepted
- Background task auto-creates resource after handler returns non-None
- Background task does NOT create resource when handler returns None
- OpenAPI spec contains asyncMode='background' but no jobResourceName
- async handler (async def) is supported
- sync handler (def) is supported
- Errors in background task are logged, not raised
"""

import asyncio
import datetime as dt

import msgspec
from fastapi import Body, FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct

from specstar.crud.core import SpecStar
from specstar.types import BackgroundTaskAccepted

# ---------------------------------------------------------------------------
# Test Models
# ---------------------------------------------------------------------------


class Article(Struct):
    title: str
    content: str


class GenerateRequest(Struct):
    prompt: str
    title: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_crud(**kwargs) -> SpecStar:
    return SpecStar(
        default_user="tester",
        default_now=dt.datetime.now,
        **kwargs,
    )


def _build_app(spec: SpecStar) -> FastAPI:
    app = FastAPI()
    spec.apply(app)
    return app


# ---------------------------------------------------------------------------
# 1. Decorator stores async_mode='background' metadata
# ---------------------------------------------------------------------------


class TestBackgroundCreateActionDecorator:
    """@spec.create_action(async_mode='background') stores metadata."""

    def test_async_mode_stored_in_pending_action(self):
        spec = _make_crud()
        spec.add_model(Article, name="article")

        @spec.create_action(
            "article", async_mode="background", label="Generate Article"
        )
        def generate_article(body: GenerateRequest = Body(...)) -> Article:
            return Article(title=body.title, content="generated")

        assert len(spec._pending_create_actions) == 1
        action = spec._pending_create_actions[0]
        assert action.async_mode == "background"
        assert action.label == "Generate Article"

    def test_default_async_mode_is_none(self):
        spec = _make_crud()
        spec.add_model(Article, name="article")

        @spec.create_action("article")
        def create_article(body: Article = Body(...)) -> Article:
            return body

        action = spec._pending_create_actions[0]
        assert action.async_mode is None


# ---------------------------------------------------------------------------
# 2. No Job model registered for background mode
# ---------------------------------------------------------------------------


class TestBackgroundNoJobModel:
    """async_mode='background' does NOT generate a Job model."""

    def test_no_job_model_registered(self):
        spec = _make_crud()
        spec.add_model(Article, name="article")

        @spec.create_action("article", async_mode="background", label="Generate")
        def generate(body: GenerateRequest = Body(...)) -> Article:
            return Article(title=body.title, content="bg")

        app = _build_app(spec)

        # No resource manager with "job" in the name should exist
        job_rms = [name for name in spec.resource_managers if "job" in name.lower()]
        assert job_rms == [], f"Unexpected Job resources: {job_rms}"


# ---------------------------------------------------------------------------
# 3. POST → HTTP 202 + BackgroundTaskAccepted
# ---------------------------------------------------------------------------


class TestBackgroundCreateActionEndpoint:
    """POST to a background action returns 202 immediately."""

    def test_sync_handler_returns_202(self):
        spec = _make_crud()
        spec.add_model(Article, name="article")

        @spec.create_action("article", async_mode="background", label="Generate")
        def generate(body: GenerateRequest = Body(...)) -> Article:
            return Article(title=body.title, content="bg-sync")

        app = _build_app(spec)
        client = TestClient(app)

        resp = client.post(
            "/article/generate",
            json={"prompt": "hello", "title": "Test"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["message"] == "Task accepted"

    def test_async_handler_returns_202(self):
        spec = _make_crud()
        spec.add_model(Article, name="article")

        @spec.create_action("article", async_mode="background", label="Async Generate")
        async def async_generate(body: GenerateRequest = Body(...)) -> Article:
            return Article(title=body.title, content="bg-async")

        app = _build_app(spec)
        client = TestClient(app)

        resp = client.post(
            "/article/async-generate",
            json={"prompt": "hello", "title": "Test"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["message"] == "Task accepted"


# ---------------------------------------------------------------------------
# 4. Background task auto-creates resource
# ---------------------------------------------------------------------------


class TestBackgroundAutoCreate:
    """Background handler creates target resource after completion."""

    def test_sync_handler_creates_resource(self):
        spec = _make_crud()
        spec.add_model(Article, name="article")

        @spec.create_action("article", async_mode="background", label="Generate")
        def generate(body: GenerateRequest = Body(...)) -> Article:
            return Article(title=body.title, content="bg-created")

        app = _build_app(spec)
        # TestClient runs background tasks synchronously before returning
        client = TestClient(app)

        resp = client.post(
            "/article/generate",
            json={"prompt": "test", "title": "BG Article"},
        )
        assert resp.status_code == 202

        # Verify via HTTP search API
        search_resp = client.get("/article/?limit=50")
        assert search_resp.status_code == 200
        results = search_resp.json()
        assert len(results) >= 1
        found = any(r["data"]["title"] == "BG Article" for r in results)
        assert found, "Background task did not create the article"

    def test_async_handler_creates_resource(self):
        spec = _make_crud()
        spec.add_model(Article, name="article")

        @spec.create_action("article", async_mode="background", label="Async Generate")
        async def async_generate(body: GenerateRequest = Body(...)) -> Article:
            return Article(title=body.title, content="async-bg-created")

        app = _build_app(spec)
        client = TestClient(app)

        resp = client.post(
            "/article/async-generate",
            json={"prompt": "test", "title": "Async BG Article"},
        )
        assert resp.status_code == 202

        search_resp = client.get("/article/?limit=50")
        assert search_resp.status_code == 200
        results = search_resp.json()
        found = any(r["data"]["title"] == "Async BG Article" for r in results)
        assert found, "Async background task did not create the article"


# ---------------------------------------------------------------------------
# 5. Handler returns None → no resource created
# ---------------------------------------------------------------------------


class TestBackgroundReturnsNone:
    """When the handler returns None, no resource is created."""

    def test_sync_handler_returns_none_no_create(self):
        spec = _make_crud()
        spec.add_model(Article, name="article")

        @spec.create_action("article", async_mode="background", label="Maybe Create")
        def maybe_create(body: GenerateRequest = Body(...)):
            # Explicitly return None → no auto-create
            return None

        app = _build_app(spec)
        client = TestClient(app)

        resp = client.post(
            "/article/maybe-create",
            json={"prompt": "skip", "title": "Skip"},
        )
        assert resp.status_code == 202

        search_resp = client.get("/article/?limit=50")
        results = search_resp.json()
        assert results == []

    def test_async_handler_returns_none_no_create(self):
        spec = _make_crud()
        spec.add_model(Article, name="article")

        @spec.create_action("article", async_mode="background", label="Async Maybe")
        async def async_maybe(body: GenerateRequest = Body(...)):
            return None

        app = _build_app(spec)
        client = TestClient(app)

        resp = client.post(
            "/article/async-maybe",
            json={"prompt": "skip", "title": "Skip"},
        )
        assert resp.status_code == 202

        search_resp = client.get("/article/?limit=50")
        results = search_resp.json()
        assert results == []


# ---------------------------------------------------------------------------
# 6. OpenAPI spec: asyncMode='background', no jobResourceName
# ---------------------------------------------------------------------------


class TestBackgroundOpenAPI:
    """OpenAPI extension metadata for background create actions."""

    def test_openapi_has_async_mode_background(self):
        spec = _make_crud()
        spec.add_model(Article, name="article")

        @spec.create_action("article", async_mode="background", label="Generate")
        def generate(body: GenerateRequest = Body(...)) -> Article:
            return Article(title=body.title, content="bg")

        app = _build_app(spec)
        spec.openapi(app)
        schema = app.openapi()

        actions = schema.get("x-specstar-custom-create-actions", {})
        assert "article" in actions
        article_actions = actions["article"]
        assert len(article_actions) == 1
        action_info = article_actions[0]
        assert action_info["asyncMode"] == "background"
        # No jobResourceName for background mode
        assert "jobResourceName" not in action_info

    def test_openapi_no_async_create_jobs_for_background(self):
        """x-specstar-async-create-jobs should NOT contain background actions."""
        spec = _make_crud()
        spec.add_model(Article, name="article")

        @spec.create_action("article", async_mode="background", label="Generate")
        def generate(body: GenerateRequest = Body(...)) -> Article:
            return Article(title=body.title, content="bg")

        app = _build_app(spec)
        spec.openapi(app)
        schema = app.openapi()

        # x-specstar-async-create-jobs should be absent or empty
        async_jobs = schema.get("x-specstar-async-create-jobs", {})
        assert async_jobs == {}


# ---------------------------------------------------------------------------
# 7. Error handling — background task logs errors
# ---------------------------------------------------------------------------


class TestBackgroundErrorHandling:
    """Errors in background tasks are logged, not propagated."""

    def test_sync_handler_error_does_not_crash(self):
        spec = _make_crud()
        spec.add_model(Article, name="article")

        @spec.create_action("article", async_mode="background", label="Failing")
        def failing(body: GenerateRequest = Body(...)) -> Article:
            raise ValueError("Something went wrong")

        app = _build_app(spec)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/article/failing",
            json={"prompt": "fail", "title": "Fail"},
        )
        # The endpoint itself returns 202 even though the bg task will fail
        assert resp.status_code == 202

        # No resource created
        search_resp = client.get("/article/?limit=50")
        results = search_resp.json()
        assert results == []

    def test_async_handler_error_does_not_crash(self):
        spec = _make_crud()
        spec.add_model(Article, name="article")

        @spec.create_action("article", async_mode="background", label="Async Failing")
        async def async_failing(body: GenerateRequest = Body(...)) -> Article:
            raise RuntimeError("Async failure")

        app = _build_app(spec)
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post(
            "/article/async-failing",
            json={"prompt": "fail", "title": "Fail"},
        )
        assert resp.status_code == 202

        search_resp = client.get("/article/?limit=50")
        results = search_resp.json()
        assert results == []


# ---------------------------------------------------------------------------
# 8. Mixed: background + sync actions on same resource
# ---------------------------------------------------------------------------


class TestBackgroundMixedActions:
    """Background and sync actions coexist on the same resource."""

    def test_background_and_sync_both_work(self):
        spec = _make_crud()
        spec.add_model(Article, name="article")

        @spec.create_action("article", label="Sync Import")
        def sync_import(body: Article = Body(...)) -> Article:
            return body

        @spec.create_action("article", async_mode="background", label="BG Generate")
        def bg_generate(body: GenerateRequest = Body(...)) -> Article:
            return Article(title=body.title, content="bg")

        app = _build_app(spec)
        client = TestClient(app)

        # Sync action returns 200 with RevisionInfo
        resp1 = client.post(
            "/article/sync-import",
            json={"title": "Sync", "content": "sync content"},
        )
        assert resp1.status_code == 200

        # Background action returns 202
        resp2 = client.post(
            "/article/bg-generate",
            json={"prompt": "test", "title": "BG"},
        )
        assert resp2.status_code == 202
        assert resp2.json()["message"] == "Task accepted"

        # Both resources should exist
        search_resp = client.get("/article/?limit=50")
        results = search_resp.json()
        assert len(results) == 2


# ---------------------------------------------------------------------------
# 9. BackgroundTaskAccepted type
# ---------------------------------------------------------------------------


class TestBackgroundTaskAcceptedType:
    """BackgroundTaskAccepted struct is correct."""

    def test_struct_fields(self):
        info = BackgroundTaskAccepted(message="Task accepted")
        assert info.message == "Task accepted"

    def test_serialization(self):
        info = BackgroundTaskAccepted(message="OK")
        data = msgspec.json.decode(msgspec.json.encode(info))
        assert data == {"message": "OK"}


# ---------------------------------------------------------------------------
# 10. Background task is always sync (non-blocking event loop)
# ---------------------------------------------------------------------------


class TestBackgroundTaskIsSync:
    """_run_bg must always be a plain sync function so Starlette dispatches
    it via ``run_in_threadpool`` and the 202 response is flushed before the
    background work starts.  If _run_bg is ``async def``, Starlette awaits
    it directly on the event loop, which blocks response delivery.
    """

    def test_async_handler_bg_task_is_not_coroutine(self):
        """Even when the handler is async def, the task added to
        BackgroundTasks must be a plain (sync) callable."""
        spec = _make_crud()
        spec.add_model(Article, name="article")

        @spec.create_action("article", async_mode="background", label="Generate")
        async def generate(body: GenerateRequest = Body(...)) -> Article:
            return Article(title=body.title, content="bg")

        app = _build_app(spec)

        # Patch BackgroundTasks.add_task to capture the function
        captured_tasks: list = []
        original_add_task = None

        from starlette.background import BackgroundTasks

        original_add_task = BackgroundTasks.add_task

        def spy_add_task(self, func, *args, **kwargs):
            captured_tasks.append(func)
            return original_add_task(self, func, *args, **kwargs)

        BackgroundTasks.add_task = spy_add_task  # ty:ignore[invalid-assignment]
        try:
            client = TestClient(app)
            resp = client.post(
                "/article/generate",
                json={"prompt": "p", "title": "T"},
            )
            assert resp.status_code == 202
        finally:
            BackgroundTasks.add_task = original_add_task

        assert len(captured_tasks) == 1
        task_fn = captured_tasks[0]
        assert not asyncio.iscoroutinefunction(task_fn), (
            "_run_bg must be a sync function, not async, "
            "to avoid blocking the event loop"
        )

    def test_sync_handler_bg_task_is_not_coroutine(self):
        spec = _make_crud()
        spec.add_model(Article, name="article")

        @spec.create_action("article", async_mode="background", label="Generate")
        def generate(body: GenerateRequest = Body(...)) -> Article:
            return Article(title=body.title, content="bg")

        app = _build_app(spec)

        captured_tasks: list = []
        from starlette.background import BackgroundTasks

        original_add_task = BackgroundTasks.add_task

        def spy_add_task(self, func, *args, **kwargs):
            captured_tasks.append(func)
            return original_add_task(self, func, *args, **kwargs)

        BackgroundTasks.add_task = spy_add_task  # ty:ignore[invalid-assignment]
        try:
            client = TestClient(app)
            resp = client.post(
                "/article/generate",
                json={"prompt": "p", "title": "T"},
            )
            assert resp.status_code == 202
        finally:
            BackgroundTasks.add_task = original_add_task

        assert len(captured_tasks) == 1
        task_fn = captured_tasks[0]
        assert not asyncio.iscoroutinefunction(task_fn)
