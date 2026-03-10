"""Tests for async create action (async_mode='job').

Covers:
- Decorator accepts async_mode='job' and stores it in _PendingCreateAction
- apply() auto-generates Job Model with correct fields/naming
- POST to async action → HTTP 202 + JobRedirectInfo
- Background Job handler auto-executes: payload passed correctly, resource auto-created
- Job completion stores RevisionInfo as artifact
- async_mode=None (default) behaviour unchanged
- OpenAPI spec contains asyncMode and jobResourceName
- Job resource is fully registered with its own CRUD endpoints
- Multiple async create actions on same resource
- Async create action with sync handler
"""

import datetime as dt
import time

import msgspec
import pytest
from fastapi import Body, FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct

from autocrud.crud.core import AutoCRUD
from autocrud.message_queue.simple import SimpleMessageQueueFactory
from autocrud.types import TaskStatus

# ---------------------------------------------------------------------------
# Test Models
# ---------------------------------------------------------------------------


class Article(Struct):
    title: str
    content: str


class ArticleRequest(Struct):
    prompt: str
    title: str


class ImportPayload(Struct):
    url: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_crud(**kwargs) -> AutoCRUD:
    return AutoCRUD(
        default_user="tester",
        default_now=dt.datetime.now,
        message_queue_factory=SimpleMessageQueueFactory(max_retries=1),
        **kwargs,
    )


def _wait_for_job_completion(
    crud: AutoCRUD, job_resource_name: str, job_resource_id: str, timeout: float = 5.0
):
    """Poll until the job reaches COMPLETED or FAILED status."""
    rm = crud.resource_managers[job_resource_name]
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        resource = rm.get(job_resource_id)
        if resource.data.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            return resource
        time.sleep(0.1)
    raise TimeoutError(f"Job {job_resource_id} did not complete within {timeout}s")


# ---------------------------------------------------------------------------
# 1. Decorator stores async_mode metadata
# ---------------------------------------------------------------------------


class TestAsyncCreateActionDecorator:
    """@crud.create_action(async_mode='job') stores async_mode in pending action."""

    def test_async_mode_stored_in_pending_action(self):
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action("article", async_mode="job", label="Generate Article")
        def generate_article(payload: ArticleRequest = Body(...)) -> Article:
            return Article(title=payload.title, content="generated")

        assert len(crud._pending_create_actions) == 1
        action = crud._pending_create_actions[0]
        assert action.async_mode == "job"
        assert action.label == "Generate Article"

    def test_default_async_mode_is_none(self):
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action("article", label="Sync Import")
        async def sync_import(body: ImportPayload = Body(...)):
            return Article(title="imported", content=body.url)

        action = crud._pending_create_actions[0]
        assert action.async_mode is None


# ---------------------------------------------------------------------------
# 2. Auto-generated Job Model
# ---------------------------------------------------------------------------


class TestAsyncJobModelGeneration:
    """apply() auto-generates a Job Model for async_mode='job' actions."""

    def test_job_model_registered(self):
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action("article", async_mode="job", label="Generate")
        def generate_article(payload: ArticleRequest = Body(...)) -> Article:
            return Article(title=payload.title, content="ok")

        app = FastAPI()
        crud.apply(app)

        # The auto-generated Job model should be registered as a resource manager
        job_resource_name = "generate-article-job"
        assert job_resource_name in crud.resource_managers

    def test_job_model_is_job_subclass(self):
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action("article", async_mode="job", label="Generate")
        def generate_article(payload: ArticleRequest = Body(...)) -> Article:
            return Article(title=payload.title, content="ok")

        app = FastAPI()
        crud.apply(app)

        job_rm = crud.resource_managers["generate-article-job"]
        # The model should be recognized as a Job subclass
        assert crud._is_job_subclass(job_rm.resource_type)

    def test_job_model_has_correct_fields(self):
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action("article", async_mode="job", label="Generate")
        def generate_article(payload: ArticleRequest = Body(...)) -> Article:
            return Article(title=payload.title, content="ok")

        app = FastAPI()
        crud.apply(app)

        job_rm = crud.resource_managers["generate-article-job"]
        model = job_rm.resource_type
        # Should have Job-like fields
        field_names = {f for f in model.__struct_fields__}
        assert "payload" in field_names
        assert "status" in field_names
        assert "artifact" in field_names
        assert "errmsg" in field_names
        assert "retries" in field_names

    def test_job_model_has_message_queue(self):
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action("article", async_mode="job", label="Generate")
        def generate_article(payload: ArticleRequest = Body(...)) -> Article:
            return Article(title=payload.title, content="ok")

        app = FastAPI()
        crud.apply(app)

        job_rm = crud.resource_managers["generate-article-job"]
        assert job_rm.message_queue is not None


# ---------------------------------------------------------------------------
# 3. HTTP flow: POST → 202 + JobRedirectInfo
# ---------------------------------------------------------------------------


class TestAsyncCreateActionHTTPFlow:
    """POST to async create action returns HTTP 202 + JobRedirectInfo."""

    @pytest.fixture
    def crud_and_client(self):
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action("article", async_mode="job", label="Generate")
        def generate_article(payload: ArticleRequest = Body(...)) -> Article:
            return Article(title=payload.title, content=f"generated:{payload.prompt}")

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)
        return crud, client

    def test_returns_202_with_job_redirect_info(self, crud_and_client):
        crud, client = crud_and_client
        resp = client.post(
            "/article/generate-article",
            json={"prompt": "hello", "title": "My Title"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "job_resource_name" in data
        assert "job_resource_id" in data
        assert data["job_resource_name"] == "generate-article-job"

    def test_job_resource_created_with_pending_status(self, crud_and_client):
        crud, client = crud_and_client
        resp = client.post(
            "/article/generate-article",
            json={"prompt": "hello", "title": "My Title"},
        )
        data = resp.json()
        job_rm = crud.resource_managers["generate-article-job"]
        job = job_rm.get(data["job_resource_id"])
        assert job.data.payload.prompt == "hello"
        assert job.data.payload.title == "My Title"

    def test_standard_sync_create_action_unchanged(self):
        """async_mode=None (default) create action still returns 200 + RevisionInfo."""
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action("article", label="Quick Import")
        async def quick_import(body: ImportPayload = Body(...)):
            return Article(title="imported", content=body.url)

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post("/article/quick-import", json={"url": "https://example.com"})
        assert resp.status_code == 200
        data = resp.json()
        assert "resource_id" in data
        assert "revision_id" in data


# ---------------------------------------------------------------------------
# 4. Background job execution
# ---------------------------------------------------------------------------


class TestAsyncJobExecution:
    """Job handler executes in background: resource auto-created, artifact set."""

    @pytest.fixture
    def crud_and_client(self):
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action("article", async_mode="job", label="Generate")
        def generate_article(payload: ArticleRequest = Body(...)) -> Article:
            return Article(title=payload.title, content=f"generated:{payload.prompt}")

        app = FastAPI()
        crud.apply(app)

        # Start consuming jobs
        job_rm = crud.resource_managers["generate-article-job"]
        job_rm.start_consume(block=False)

        client = TestClient(app)
        yield crud, client

        # Cleanup: daemon thread dies with process, no explicit stop needed

    def test_job_handler_creates_article(self, crud_and_client):
        crud, client = crud_and_client
        resp = client.post(
            "/article/generate-article",
            json={"prompt": "write about AI", "title": "AI Article"},
        )
        data = resp.json()

        # Wait for job completion
        job = _wait_for_job_completion(
            crud, "generate-article-job", data["job_resource_id"]
        )
        assert job.data.status == TaskStatus.COMPLETED

        # Verify the Article was created via the HTTP search API
        search_resp = client.get("/article/?limit=50")
        assert search_resp.status_code == 200
        results = search_resp.json()
        if isinstance(results, dict):
            results = results.get("results", [])
        articles = [
            r
            for r in results
            if (r.get("data") or {}).get("content") == "generated:write about AI"
        ]
        assert len(articles) >= 1
        assert articles[0]["data"]["title"] == "AI Article"

    def test_job_artifact_contains_revision_info(self, crud_and_client):
        crud, client = crud_and_client
        resp = client.post(
            "/article/generate-article",
            json={"prompt": "test", "title": "Test Article"},
        )
        data = resp.json()

        job = _wait_for_job_completion(
            crud, "generate-article-job", data["job_resource_id"]
        )
        assert job.data.artifact is not None
        # Artifact should have resource_id and revision_id (RevisionInfo-like)
        artifact = job.data.artifact
        assert "resource_id" in artifact
        assert "revision_id" in artifact

    def test_job_handler_returns_none_no_create(self):
        """If handler returns None, no target resource is created but job completes."""
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action("article", async_mode="job", label="Validate Only")
        def validate_only(payload: ArticleRequest = Body(...)):
            # Validate but don't create
            return None

        app = FastAPI()
        crud.apply(app)

        job_rm = crud.resource_managers["validate-only-job"]
        job_rm.start_consume(block=False)

        client = TestClient(app)
        resp = client.post(
            "/article/validate-only",
            json={"prompt": "test", "title": "T"},
        )
        data = resp.json()

        job = _wait_for_job_completion(
            crud, "validate-only-job", data["job_resource_id"]
        )
        assert job.data.status == TaskStatus.COMPLETED
        assert job.data.artifact is None


# ---------------------------------------------------------------------------
# 5. OpenAPI spec
# ---------------------------------------------------------------------------


class TestAsyncCreateActionOpenAPI:
    """OpenAPI schema contains asyncMode and jobResourceName."""

    def test_openapi_has_async_mode_and_job_resource_name(self):
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action("article", async_mode="job", label="Generate")
        def generate_article(payload: ArticleRequest = Body(...)) -> Article:
            return Article(title=payload.title, content="ok")

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)
        schema = app.openapi()

        custom_actions = schema.get("x-autocrud-custom-create-actions", {})
        assert "article" in custom_actions
        actions = custom_actions["article"]
        gen_action = next(a for a in actions if a["label"] == "Generate")
        assert gen_action.get("asyncMode") == "job"
        assert gen_action.get("jobResourceName") == "generate-article-job"

    def test_openapi_has_async_create_jobs_mapping(self):
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action("article", async_mode="job", label="Generate")
        def generate_article(payload: ArticleRequest = Body(...)) -> Article:
            return Article(title=payload.title, content="ok")

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)
        schema = app.openapi()

        # x-autocrud-async-create-jobs maps job resource → parent resource
        async_jobs = schema.get("x-autocrud-async-create-jobs", {})
        assert "generate-article-job" in async_jobs
        assert async_jobs["generate-article-job"] == "article"

    def test_openapi_sync_action_has_no_async_mode(self):
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action("article", label="Quick Import")
        async def quick_import(body: ImportPayload = Body(...)):
            return Article(title="imported", content=body.url)

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)
        schema = app.openapi()

        custom_actions = schema.get("x-autocrud-custom-create-actions", {})
        actions = custom_actions["article"]
        action = next(a for a in actions if a["label"] == "Quick Import")
        assert "asyncMode" not in action
        assert "jobResourceName" not in action


# ---------------------------------------------------------------------------
# 6. Job CRUD endpoints
# ---------------------------------------------------------------------------


class TestAsyncJobCRUDEndpoints:
    """The auto-generated Job resource has its own CRUD endpoints."""

    def test_job_resource_has_endpoints(self):
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action("article", async_mode="job", label="Generate")
        def generate_article(payload: ArticleRequest = Body(...)) -> Article:
            return Article(title=payload.title, content="ok")

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        # GET /generate-article-job (search endpoint) should exist
        resp = client.get("/generate-article-job")
        assert resp.status_code == 200

    def test_job_resource_is_readable(self):
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action("article", async_mode="job", label="Generate")
        def generate_article(payload: ArticleRequest = Body(...)) -> Article:
            return Article(title=payload.title, content="ok")

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        # Create a job via the async create action
        resp = client.post(
            "/article/generate-article",
            json={"prompt": "hello", "title": "Test"},
        )
        job_id = resp.json()["job_resource_id"]

        # GET /generate-article-job/{id} should return the job
        resp = client.get(f"/generate-article-job/{job_id}")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 7. Multiple async create actions
# ---------------------------------------------------------------------------


class TestMultipleAsyncCreateActions:
    """Multiple async_mode='job' actions on the same resource."""

    def test_multiple_async_actions_create_separate_jobs(self):
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action("article", async_mode="job", label="Generate")
        def generate_article(payload: ArticleRequest = Body(...)) -> Article:
            return Article(title=payload.title, content="generated")

        @crud.create_action("article", async_mode="job", label="Import Async")
        def import_async(payload: ImportPayload = Body(...)) -> Article:
            return Article(title="imported", content=payload.url)

        app = FastAPI()
        crud.apply(app)

        assert "generate-article-job" in crud.resource_managers
        assert "import-async-job" in crud.resource_managers

    def test_mixed_sync_and_async_actions(self):
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action("article", async_mode="job", label="Generate")
        def generate_article(payload: ArticleRequest = Body(...)) -> Article:
            return Article(title=payload.title, content="generated")

        @crud.create_action("article", label="Quick Import")
        async def quick_import(body: ImportPayload = Body(...)):
            return Article(title="imported", content=body.url)

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        # Async action → 202
        resp = client.post(
            "/article/generate-article",
            json={"prompt": "hello", "title": "Test"},
        )
        assert resp.status_code == 202

        # Sync action → 200
        resp = client.post(
            "/article/quick-import",
            json={"url": "https://example.com"},
        )
        assert resp.status_code == 200
        assert "resource_id" in resp.json()


# ---------------------------------------------------------------------------
# 8. JobRedirectInfo type
# ---------------------------------------------------------------------------


class TestJobRedirectInfoType:
    """JobRedirectInfo is importable and has correct fields."""

    def test_importable_from_autocrud(self):
        from autocrud.types import JobRedirectInfo

        info = JobRedirectInfo(
            job_resource_name="test-job",
            job_resource_id="abc123",
            redirect_url="/test-job/abc123",
        )
        assert info.job_resource_name == "test-job"
        assert info.job_resource_id == "abc123"
        assert info.redirect_url == "/test-job/abc123"

    def test_serializable_with_msgspec(self):
        from autocrud.types import JobRedirectInfo

        info = JobRedirectInfo(
            job_resource_name="test-job",
            job_resource_id="abc123",
            redirect_url="/test-job/abc123",
        )
        data = msgspec.json.decode(msgspec.json.encode(info))
        assert data["job_resource_name"] == "test-job"


# ---------------------------------------------------------------------------
# 9. Auto-payload: handlers with scalar (non-Struct) parameters
# ---------------------------------------------------------------------------


class TestAutoPayloadScalarParams:
    """async_mode='job' with scalar-only handlers (no Struct body param)."""

    def test_scalar_params_auto_generate_job_model(self):
        """Handler with only str param auto-generates a payload Struct."""
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action(
            "article", async_mode="job", label="Create by Name", path="by-name"
        )
        async def create_by_name(name: str):
            return Article(title=name, content="auto")

        app = FastAPI()
        crud.apply(app)

        # Job resource should be registered
        assert "by-name-job" in crud.resource_managers
        job_rm = crud.resource_managers["by-name-job"]
        assert crud._is_job_subclass(job_rm.resource_type)

    def test_scalar_params_returns_202(self):
        """POST to scalar-param async action returns 202 + JobRedirectInfo."""
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action(
            "article", async_mode="job", label="Create by Name", path="by-name"
        )
        async def create_by_name(name: str):
            return Article(title=name, content="auto")

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post("/article/by-name?name=hello")
        assert resp.status_code == 202
        data = resp.json()
        assert data["job_resource_name"] == "by-name-job"
        assert "job_resource_id" in data

    def test_scalar_params_job_payload_correct(self):
        """The auto-generated payload Struct captures the scalar value."""
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action(
            "article", async_mode="job", label="Create by Name", path="by-name"
        )
        async def create_by_name(name: str):
            return Article(title=name, content="auto")

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post("/article/by-name?name=hello")
        data = resp.json()

        job_rm = crud.resource_managers["by-name-job"]
        job = job_rm.get(data["job_resource_id"])
        assert job.data.payload.name == "hello"

    def test_scalar_params_job_execution_creates_resource(self):
        """Background job unpacks auto-payload, calls handler, creates resource."""
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action(
            "article", async_mode="job", label="Create by Name", path="by-name"
        )
        async def create_by_name(name: str):
            return Article(title=name, content="auto-generated")

        app = FastAPI()
        crud.apply(app)

        job_rm = crud.resource_managers["by-name-job"]
        job_rm.start_consume(block=False)

        client = TestClient(app)
        resp = client.post("/article/by-name?name=TestArticle")
        data = resp.json()

        job = _wait_for_job_completion(crud, "by-name-job", data["job_resource_id"])
        assert job.data.status == TaskStatus.COMPLETED

        # Verify the Article was created
        search_resp = client.get("/article/?limit=50")
        results = search_resp.json()
        if isinstance(results, dict):
            results = results.get("results", [])
        articles = [
            r
            for r in results
            if (r.get("data") or {}).get("content") == "auto-generated"
        ]
        assert len(articles) >= 1
        assert articles[0]["data"]["title"] == "TestArticle"

    def test_multiple_scalar_params(self):
        """Handler with multiple scalar params all captured in auto-payload."""
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action(
            "article", async_mode="job", label="Create from parts", path="from-parts"
        )
        def create_from_parts(title: str, body: str, count: int):
            return Article(title=f"{title} #{count}", content=body)

        app = FastAPI()
        crud.apply(app)

        job_rm = crud.resource_managers["from-parts-job"]
        job_rm.start_consume(block=False)

        client = TestClient(app)
        resp = client.post("/article/from-parts?title=Hi&body=World&count=42")
        assert resp.status_code == 202
        data = resp.json()

        job = _wait_for_job_completion(crud, "from-parts-job", data["job_resource_id"])
        assert job.data.status == TaskStatus.COMPLETED
        assert job.data.payload.title == "Hi"
        assert job.data.payload.body == "World"
        assert job.data.payload.count == 42

    def test_path_template_params(self):
        """Handler with path template variables works with auto-payload."""
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action(
            "article",
            async_mode="job",
            label="Create by slug",
            path="/{slug}/create",
        )
        def create_by_slug(slug: str):
            return Article(title=slug, content="from-slug")

        app = FastAPI()
        crud.apply(app)

        # Job resource name should be cleaned of path templates
        assert "create-job" in crud.resource_managers

        client = TestClient(app)
        resp = client.post("/article/my-slug/create")
        assert resp.status_code == 202
        data = resp.json()
        assert data["job_resource_name"] == "create-job"

        job_rm = crud.resource_managers["create-job"]
        job = job_rm.get(data["job_resource_id"])
        assert job.data.payload.slug == "my-slug"

    def test_sync_scalar_handler_works(self):
        """Non-async (sync) scalar handler also works with auto-payload."""
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action(
            "article", async_mode="job", label="Sync Create", path="sync-create"
        )
        def sync_create(name: str):
            return Article(title=name, content="sync")

        app = FastAPI()
        crud.apply(app)

        job_rm = crud.resource_managers["sync-create-job"]
        job_rm.start_consume(block=False)

        client = TestClient(app)
        resp = client.post("/article/sync-create?name=SyncTest")
        assert resp.status_code == 202
        data = resp.json()

        job = _wait_for_job_completion(crud, "sync-create-job", data["job_resource_id"])
        assert job.data.status == TaskStatus.COMPLETED

        # Verify the Article was created
        search_resp = client.get("/article/?limit=50")
        results = search_resp.json()
        if isinstance(results, dict):
            results = results.get("results", [])
        articles = [
            r for r in results if (r.get("data") or {}).get("content") == "sync"
        ]
        assert len(articles) >= 1


# ---------------------------------------------------------------------------
# 10. Type conversion: UploadFile, Pydantic, non-msgspec types → async ok
# ---------------------------------------------------------------------------


class TestAutoPayloadTypeConversion:
    """Handlers with UploadFile / Pydantic / non-msgspec params are auto-converted."""

    def test_upload_file_payload_struct(self):
        """UploadFilePayload wraps Binary + filename and round-trips."""
        from autocrud.crud.async_job_builder import UploadFilePayload
        from autocrud.types import Binary

        payload = UploadFilePayload(
            binary=Binary(data=b"hello", content_type="text/plain", size=5),
            filename="test.txt",
        )
        assert payload.filename == "test.txt"
        assert payload.binary.data == b"hello"
        assert payload.binary.content_type == "text/plain"
        assert payload.binary.size == 5

        # Round-trip via msgspec
        encoded = msgspec.json.encode(payload)
        decoded = msgspec.json.decode(encoded, type=UploadFilePayload)
        assert decoded.filename == "test.txt"
        assert decoded.binary.data == b"hello"

    def test_resolve_payload_field_type_upload_file(self):
        """UploadFile maps to UploadFilePayload."""
        from fastapi import UploadFile

        from autocrud.crud.async_job_builder import (
            UploadFilePayload,
            resolve_payload_field_type,
        )

        ser_type, conv_kind = resolve_payload_field_type(UploadFile)
        assert ser_type is UploadFilePayload
        assert conv_kind == "upload_file"

    def test_resolve_payload_field_type_pydantic(self):
        """Pydantic BaseModel maps to a msgspec Struct."""
        from pydantic import BaseModel

        from autocrud.crud.async_job_builder import resolve_payload_field_type

        class MyModel(BaseModel):
            name: str

        ser_type, conv_kind = resolve_payload_field_type(MyModel)
        assert conv_kind == "pydantic"
        assert issubclass(ser_type, Struct)

    def test_resolve_payload_field_type_scalars(self):
        """Scalars and unions pass through unchanged."""
        from autocrud.crud.async_job_builder import resolve_payload_field_type

        for t in (str, int, float, bool, bytes):
            ser_type, conv_kind = resolve_payload_field_type(t)
            assert ser_type is t
            assert conv_kind is None

    def test_resolve_payload_field_type_non_msgspec_class(self):
        """Non-msgspec class (e.g. pydantic_core.Url) → str."""
        from pydantic_core import Url

        from autocrud.crud.async_job_builder import resolve_payload_field_type

        ser_type, conv_kind = resolve_payload_field_type(Url)
        assert ser_type is str
        assert conv_kind == "to_str"

    def test_upload_file_param_works_async(self):
        """UploadFile param is auto-converted → async job succeeds."""
        from fastapi import UploadFile

        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action(
            "article", async_mode="job", label="Upload", path="upload-create"
        )
        async def upload_create(name: str, file: UploadFile):
            content = await file.read()
            return Article(title=name, content=content.decode())

        app = FastAPI()
        crud.apply(app)

        # Job resource should exist (NOT fallen back to sync)
        assert "upload-create-job" in crud.resource_managers

        job_rm = crud.resource_managers["upload-create-job"]
        job_rm.start_consume(block=False)

        client = TestClient(app)
        resp = client.post(
            "/article/upload-create?name=TestFile",
            files={"file": ("test.txt", b"file-content", "text/plain")},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "job_resource_id" in data

        job = _wait_for_job_completion(
            crud, "upload-create-job", data["job_resource_id"]
        )
        assert job.data.status == TaskStatus.COMPLETED

        # Verify the article was created with file content
        search_resp = client.get("/article/?limit=50")
        results = search_resp.json()
        if isinstance(results, dict):
            results = results.get("results", [])
        articles = [
            r for r in results if (r.get("data") or {}).get("content") == "file-content"
        ]
        assert len(articles) >= 1

    def test_pydantic_model_param_works_async(self):
        """Pydantic BaseModel param is auto-converted → async job succeeds."""
        from pydantic import BaseModel

        class PydanticInput(BaseModel):
            name: str

        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action(
            "article", async_mode="job", label="Pydantic", path="pydantic-create"
        )
        def pydantic_create(data: PydanticInput):
            return Article(title=data.name, content="from-pydantic")

        app = FastAPI()
        crud.apply(app)

        # Job resource should exist
        assert "pydantic-create-job" in crud.resource_managers

        job_rm = crud.resource_managers["pydantic-create-job"]
        job_rm.start_consume(block=False)

        client = TestClient(app)
        resp = client.post("/article/pydantic-create", json={"name": "PydTest"})
        assert resp.status_code == 202
        data = resp.json()

        job = _wait_for_job_completion(
            crud, "pydantic-create-job", data["job_resource_id"]
        )
        assert job.data.status == TaskStatus.COMPLETED

        search_resp = client.get("/article/?limit=50")
        results = search_resp.json()
        if isinstance(results, dict):
            results = results.get("results", [])
        articles = [
            r
            for r in results
            if (r.get("data") or {}).get("content") == "from-pydantic"
        ]
        assert len(articles) >= 1

    def test_to_str_conversion_param(self):
        """Non-msgspec type param (Url) is converted to str → async ok."""
        from pydantic_core import Url

        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action(
            "article", async_mode="job", label="UrlCreate", path="url-create"
        )
        def url_create(name: str, url: Url):
            return Article(title=name, content=str(url))

        app = FastAPI()
        crud.apply(app)

        assert "url-create-job" in crud.resource_managers

        job_rm = crud.resource_managers["url-create-job"]
        job_rm.start_consume(block=False)

        client = TestClient(app)
        resp = client.post("/article/url-create?name=UrlTest&url=https://example.com")
        assert resp.status_code == 202
        data = resp.json()

        job = _wait_for_job_completion(crud, "url-create-job", data["job_resource_id"])
        assert job.data.status == TaskStatus.COMPLETED

        search_resp = client.get("/article/?limit=50")
        results = search_resp.json()
        if isinstance(results, dict):
            results = results.get("results", [])
        articles = [
            r for r in results if (r.get("data") or {}).get("title") == "UrlTest"
        ]
        assert len(articles) >= 1

    def test_mixed_params_all_conversions(self):
        """Multiple converted params (UploadFile + Url + scalar) work together."""
        from fastapi import UploadFile
        from pydantic_core import Url

        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action(
            "article", async_mode="job", label="Mixed", path="mixed-create"
        )
        async def mixed_create(
            name: str,
            url: Url,
            file: UploadFile,
        ):
            content = await file.read()
            return Article(
                title=name,
                content=f"{url}|{content.decode()}",
            )

        app = FastAPI()
        crud.apply(app)

        assert "mixed-create-job" in crud.resource_managers

        job_rm = crud.resource_managers["mixed-create-job"]
        job_rm.start_consume(block=False)

        client = TestClient(app)
        resp = client.post(
            "/article/mixed-create?name=MixedTest&url=https://example.com",
            files={"file": ("f.txt", b"mixed-bytes", "text/plain")},
        )
        assert resp.status_code == 202
        data = resp.json()

        job = _wait_for_job_completion(
            crud, "mixed-create-job", data["job_resource_id"]
        )
        assert job.data.status == TaskStatus.COMPLETED


# ---------------------------------------------------------------------------
# 11. Path template cleaning in async_job_builder
# ---------------------------------------------------------------------------


class TestAsyncJobBuilderPathTemplates:
    """Path templates are cleaned for Job model/resource naming."""

    def test_clean_action_name(self):
        from autocrud.crud.async_job_builder import _clean_action_name

        assert _clean_action_name("generate-article") == "generate-article"
        assert _clean_action_name("/{name}/new") == "new"
        assert _clean_action_name("/{id}") == ""
        assert _clean_action_name("/{a}/{b}/create") == "create"
        assert _clean_action_name("simple") == "simple"

    def test_derive_job_resource_name_with_path_template(self):
        from autocrud.crud.async_job_builder import derive_job_resource_name

        assert derive_job_resource_name("generate-article") == "generate-article-job"
        assert derive_job_resource_name("/{name}/new", "character") == "new-job"
        # When cleaned name is empty, fallback to resource_name
        assert derive_job_resource_name("/{id}", "character") == "character-job"

    def test_build_auto_payload_struct(self):
        from autocrud.crud.async_job_builder import build_auto_payload_struct

        PayloadType = build_auto_payload_struct(
            "by-name", "article", [("name", str), ("count", int)]
        )
        assert issubclass(PayloadType, Struct)
        instance = PayloadType(name="hello", count=5)
        assert instance.name == "hello"
        assert instance.count == 5


# ---------------------------------------------------------------------------
# 12. OpenAPI spec for auto-payload actions
# ---------------------------------------------------------------------------


class TestAutoPayloadOpenAPI:
    """OpenAPI schema correctly reports async metadata for auto-payload actions."""

    def test_openapi_has_async_mode_for_scalar_action(self):
        crud = _make_crud()
        crud.add_model(Article, name="article")

        @crud.create_action(
            "article", async_mode="job", label="Create by Name", path="by-name"
        )
        async def create_by_name(name: str):
            return Article(title=name, content="auto")

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)
        schema = app.openapi()

        custom_actions = schema.get("x-autocrud-custom-create-actions", {})
        assert "article" in custom_actions
        actions = custom_actions["article"]
        action = next(a for a in actions if a["label"] == "Create by Name")
        assert action.get("asyncMode") == "job"
        assert action.get("jobResourceName") == "by-name-job"

        # Also in x-autocrud-async-create-jobs
        async_jobs = schema.get("x-autocrud-async-create-jobs", {})
        assert "by-name-job" in async_jobs
        assert async_jobs["by-name-job"] == "article"
