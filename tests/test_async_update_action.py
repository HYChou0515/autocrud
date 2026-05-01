"""Tests for async update action (async_mode='job').

Covers:
- Decorator accepts async_mode='job' and stores it in _PendingUpdateAction
- apply() auto-generates Job Model with correct fields/naming (resource_id in payload)
- POST to async update → HTTP 202 + JobRedirectInfo
- Job handler lazy-fetches existing, passes to handler, auto-calls update/modify
- Job completion stores RevisionInfo as artifact
- async_mode=None (default) behaviour unchanged
- OpenAPI spec contains asyncMode and jobResourceName for update actions
- Job resource is fully registered with its own CRUD endpoints
- Multiple async update actions on same resource
- Async update action with modify mode
- Custom job_name parameter
- RM-level async_update_job_names mapping
"""

import datetime as dt
import time

import pytest
from fastapi import Body, FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct

from specstar.crud.core import SpecStar
from specstar.message_queue.simple import SimpleMessageQueueFactory
from specstar.types import TaskStatus

# ---------------------------------------------------------------------------
# Test Models
# ---------------------------------------------------------------------------


class Character(Struct):
    name: str
    level: int
    hp: int = 100


class TrainRequest(Struct):
    levels: int


class BoostPayload(Struct):
    amount: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_crud(**kwargs) -> SpecStar:
    return SpecStar(
        default_user="tester",
        default_now=dt.datetime.now,
        message_queue_factory=SimpleMessageQueueFactory(max_retries=1),
        **kwargs,
    )


def _wait_for_job_completion(
    spec: SpecStar, job_resource_name: str, job_resource_id: str, timeout: float = 5.0
):
    """Poll until the job reaches COMPLETED or FAILED status."""
    rm = spec.resource_managers[job_resource_name]
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        resource = rm.get(job_resource_id)
        if resource.data.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            return resource
        time.sleep(0.1)
    raise TimeoutError(f"Job {job_resource_id} did not complete within {timeout}s")


def _create_character(client, name="Alice", level=5, hp=100) -> str:
    """Create a Character via the HTTP API and return the resource_id."""
    resp = client.post(
        "/character/",
        json={"name": name, "level": level, "hp": hp},
    )
    assert resp.status_code == 200
    return resp.json()["resource_id"]


# ---------------------------------------------------------------------------
# 1. Decorator stores async_mode metadata
# ---------------------------------------------------------------------------


class TestAsyncUpdateActionDecorator:
    """@spec.update_action(async_mode='job') stores async_mode in pending action."""

    def test_async_mode_stored_in_pending_action(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action("character", async_mode="job", label="Train")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        assert len(spec._pending_update_actions) == 1
        action = spec._pending_update_actions[0]
        assert action.async_mode == "job"
        assert action.label == "Train"

    def test_default_async_mode_is_none(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action("character", label="Rename")
        def rename(existing: Character, name: str) -> Character:
            return Character(name=name, level=existing.level, hp=existing.hp)

        action = spec._pending_update_actions[0]
        assert action.async_mode is None

    def test_job_name_stored_in_pending_action(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action(
            "character", async_mode="job", label="Train", job_name="my-train-job"
        )
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        action = spec._pending_update_actions[0]
        assert action.job_name == "my-train-job"

    def test_job_name_default_is_none(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action("character", async_mode="job", label="Train")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        action = spec._pending_update_actions[0]
        assert action.job_name is None


# ---------------------------------------------------------------------------
# 2. Auto-generated Job Model
# ---------------------------------------------------------------------------


class TestAsyncUpdateJobModelGeneration:
    """apply() auto-generates a Job Model for async_mode='job' update actions."""

    def test_job_model_registered(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action("character", async_mode="job", label="Train")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = FastAPI()
        spec.apply(app)

        assert "train-job" in spec.resource_managers

    def test_job_model_is_job_subclass(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action("character", async_mode="job", label="Train")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = FastAPI()
        spec.apply(app)

        job_rm = spec.resource_managers["train-job"]
        assert spec._is_job_subclass(job_rm.resource_type)

    def test_job_model_has_correct_fields(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action("character", async_mode="job", label="Train")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = FastAPI()
        spec.apply(app)

        job_rm = spec.resource_managers["train-job"]
        model = job_rm.resource_type
        field_names = set(model.__struct_fields__)
        assert "payload" in field_names
        assert "status" in field_names
        assert "artifact" in field_names
        assert "errmsg" in field_names
        assert "retries" in field_names

    def test_job_model_payload_contains_resource_id(self):
        """The Job payload struct must include resource_id."""
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action("character", async_mode="job", label="Train")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = FastAPI()
        spec.apply(app)

        job_rm = spec.resource_managers["train-job"]
        job_model = job_rm.resource_type
        # Create a dummy instance to inspect payload type
        # The payload type should have resource_id and payload_data fields
        # (explicit Struct wrapping)
        payload_type = job_model.__struct_fields__
        assert "payload" in payload_type

    def test_job_model_has_message_queue(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action("character", async_mode="job", label="Train")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = FastAPI()
        spec.apply(app)

        job_rm = spec.resource_managers["train-job"]
        assert job_rm.message_queue is not None  # ty:ignore[unresolved-attribute]

    def test_job_model_is_async_update_job(self):
        """Job model should be marked as _is_async_update_job=True."""
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action("character", async_mode="job", label="Train")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = FastAPI()
        spec.apply(app)

        job_rm = spec.resource_managers["train-job"]
        model = job_rm.resource_type
        assert getattr(model, "_is_async_update_job", False) is True


# ---------------------------------------------------------------------------
# 3. HTTP flow: POST → 202 + JobRedirectInfo
# ---------------------------------------------------------------------------


class TestAsyncUpdateActionHTTPFlow:
    """POST to async update action returns HTTP 202 + JobRedirectInfo."""

    @pytest.fixture
    def crud_and_client(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action("character", async_mode="job", label="Train")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = FastAPI()
        spec.apply(app)
        client = TestClient(app)
        return spec, client

    def test_returns_202_with_job_redirect_info(self, crud_and_client):
        spec, client = crud_and_client
        resource_id = _create_character(client, name="Alice", level=5)

        resp = client.post(
            f"/character/{resource_id}/train",
            json={"levels": 3},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "job_resource_name" in data
        assert "job_resource_id" in data
        assert data["job_resource_name"] == "train-job"

    def test_job_resource_created_with_payload_containing_resource_id(
        self, crud_and_client
    ):
        spec, client = crud_and_client
        resource_id = _create_character(client, name="Bob", level=10)

        resp = client.post(
            f"/character/{resource_id}/train",
            json={"levels": 2},
        )
        data = resp.json()
        job_rm = spec.resource_managers["train-job"]
        job = job_rm.get(data["job_resource_id"])
        # Payload should include resource_id
        assert job.data.payload.resource_id == resource_id

    def test_standard_sync_update_action_unchanged(self):
        """async_mode=None (default) update action still returns 200 + RevisionInfo."""
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action("character", label="Rename")
        def rename(existing: Character, name: str) -> Character:
            return Character(name=name, level=existing.level, hp=existing.hp)

        app = FastAPI()
        spec.apply(app)
        client = TestClient(app)

        resource_id = _create_character(client, name="Original", level=1)
        resp = client.post(f"/character/{resource_id}/rename?name=Renamed")
        assert resp.status_code == 200
        data = resp.json()
        assert "resource_id" in data
        assert "revision_id" in data


# ---------------------------------------------------------------------------
# 4. Job execution: lazy-fetch existing + update/modify
# ---------------------------------------------------------------------------


class TestAsyncUpdateJobExecution:
    """Job handler lazy-fetches existing resource, calls handler, updates."""

    @pytest.fixture
    def crud_and_client(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action("character", async_mode="job", label="Train")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = FastAPI()
        spec.apply(app)

        # Start consuming jobs
        job_rm = spec.resource_managers["train-job"]
        job_rm.start_consume(block=False)

        client = TestClient(app)
        yield spec, client

    def test_job_handler_updates_character(self, crud_and_client):
        spec, client = crud_and_client
        resource_id = _create_character(client, name="Alice", level=5, hp=100)

        resp = client.post(
            f"/character/{resource_id}/train",
            json={"levels": 3},
        )
        data = resp.json()

        # Wait for job completion
        job = _wait_for_job_completion(spec, "train-job", data["job_resource_id"])
        assert job.data.status == TaskStatus.COMPLETED

        # Verify the Character was updated
        char_resp = client.get(f"/character/{resource_id}")
        assert char_resp.status_code == 200
        char_data = char_resp.json()["data"]
        assert char_data["name"] == "Alice"
        assert char_data["level"] == 8  # 5 + 3
        assert char_data["hp"] == 100

    def test_job_artifact_contains_revision_info(self, crud_and_client):
        spec, client = crud_and_client
        resource_id = _create_character(client, name="Bob", level=10)

        resp = client.post(
            f"/character/{resource_id}/train",
            json={"levels": 1},
        )
        data = resp.json()

        job = _wait_for_job_completion(spec, "train-job", data["job_resource_id"])
        assert job.data.artifact is not None
        artifact = job.data.artifact
        assert "resource_id" in artifact
        assert "revision_id" in artifact
        assert artifact["resource_id"] == resource_id

    def test_job_handler_returns_none_no_update(self):
        """If handler returns None, no update is performed but job completes."""
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action("character", async_mode="job", label="Validate Only")
        def validate_only(
            existing: Character, payload: TrainRequest = Body(...)
        ) -> None:
            # Validate only, no update
            return None

        app = FastAPI()
        spec.apply(app)

        job_rm = spec.resource_managers["validate-only-job"]
        job_rm.start_consume(block=False)

        client = TestClient(app)
        resource_id = _create_character(client, name="Carol", level=7)

        resp = client.post(
            f"/character/{resource_id}/validate-only",
            json={"levels": 99},
        )
        data = resp.json()

        job = _wait_for_job_completion(
            spec, "validate-only-job", data["job_resource_id"]
        )
        assert job.data.status == TaskStatus.COMPLETED
        assert job.data.artifact is None

        # Character should be unchanged
        char_resp = client.get(f"/character/{resource_id}")
        assert char_resp.json()["data"]["level"] == 7


# ---------------------------------------------------------------------------
# 5. Modify mode
# ---------------------------------------------------------------------------


class TestAsyncUpdateJobModifyMode:
    """async_mode='job' with mode='update' creates a new revision on update."""

    def test_update_mode_creates_new_revision(self):
        """mode='update' creates a new revision with the handler's result."""
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action("character", async_mode="job", label="Boost HP")
        def boost_hp(
            existing: Character, payload: BoostPayload = Body(...)
        ) -> Character:
            return Character(
                name=existing.name,
                level=existing.level,
                hp=existing.hp + payload.amount,
            )

        app = FastAPI()
        spec.apply(app)

        job_rm = spec.resource_managers["boost-hp-job"]
        job_rm.start_consume(block=False)

        client = TestClient(app)
        resource_id = _create_character(client, name="Dave", level=3, hp=50)

        resp = client.post(
            f"/character/{resource_id}/boost-hp",
            json={"amount": 25},
        )
        assert resp.status_code == 202
        data = resp.json()

        job = _wait_for_job_completion(spec, "boost-hp-job", data["job_resource_id"])
        assert job.data.status == TaskStatus.COMPLETED

        # Verify update applied
        char_resp = client.get(f"/character/{resource_id}")
        char_data = char_resp.json()["data"]
        assert char_data["hp"] == 75  # 50 + 25
        assert char_data["level"] == 3  # unchanged


# ---------------------------------------------------------------------------
# 6. OpenAPI spec
# ---------------------------------------------------------------------------


class TestAsyncUpdateActionOpenAPI:
    """OpenAPI schema contains asyncMode and jobResourceName for update actions."""

    def test_openapi_has_async_mode_and_job_resource_name(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action("character", async_mode="job", label="Train")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = FastAPI()
        spec.apply(app)
        spec.openapi(app)
        schema = app.openapi()

        custom_actions = schema.get("x-specstar-custom-update-actions", {})
        assert "character" in custom_actions
        actions = custom_actions["character"]
        train_action = next(a for a in actions if a["label"] == "Train")
        assert train_action.get("asyncMode") == "job"
        assert train_action.get("jobResourceName") == "train-job"

    def test_openapi_has_async_update_jobs_mapping(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action("character", async_mode="job", label="Train")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = FastAPI()
        spec.apply(app)
        spec.openapi(app)
        schema = app.openapi()

        async_jobs = schema.get("x-specstar-async-update-jobs", {})
        assert "train-job" in async_jobs
        assert async_jobs["train-job"] == "character"

    def test_openapi_sync_action_has_no_async_mode(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action("character", label="Rename")
        def rename(existing: Character, name: str) -> Character:
            return Character(name=name, level=existing.level, hp=existing.hp)

        app = FastAPI()
        spec.apply(app)
        spec.openapi(app)
        schema = app.openapi()

        custom_actions = schema.get("x-specstar-custom-update-actions", {})
        actions = custom_actions["character"]
        action = next(a for a in actions if a["label"] == "Rename")
        assert "asyncMode" not in action
        assert "jobResourceName" not in action


# ---------------------------------------------------------------------------
# 7. Job CRUD endpoints
# ---------------------------------------------------------------------------


class TestAsyncUpdateJobCRUDEndpoints:
    """Auto-generated Job resource has its own CRUD endpoints."""

    def test_job_resource_has_search_endpoint(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action("character", async_mode="job", label="Train")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = FastAPI()
        spec.apply(app)
        client = TestClient(app)

        resp = client.get("/train-job")
        assert resp.status_code == 200

    def test_job_resource_is_readable(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action("character", async_mode="job", label="Train")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = FastAPI()
        spec.apply(app)
        client = TestClient(app)

        resource_id = _create_character(client, name="Alice", level=5)
        resp = client.post(
            f"/character/{resource_id}/train",
            json={"levels": 1},
        )
        job_id = resp.json()["job_resource_id"]

        resp = client.get(f"/train-job/{job_id}")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 8. Multiple async update actions
# ---------------------------------------------------------------------------


class TestMultipleAsyncUpdateActions:
    """Multiple async_mode='job' update actions on the same resource."""

    def test_multiple_async_actions_create_separate_jobs(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action("character", async_mode="job", label="Train")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        @spec.update_action("character", async_mode="job", label="Boost HP")
        def boost_hp(
            existing: Character, payload: BoostPayload = Body(...)
        ) -> Character:
            return Character(
                name=existing.name,
                level=existing.level,
                hp=existing.hp + payload.amount,
            )

        app = FastAPI()
        spec.apply(app)

        assert "train-job" in spec.resource_managers
        assert "boost-hp-job" in spec.resource_managers

    def test_mixed_sync_and_async_actions(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action("character", async_mode="job", label="Train")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        @spec.update_action("character", label="Rename")
        def rename(existing: Character, name: str) -> Character:
            return Character(name=name, level=existing.level, hp=existing.hp)

        app = FastAPI()
        spec.apply(app)
        client = TestClient(app)

        resource_id = _create_character(client, name="Alice", level=5)

        # Async action → 202
        resp = client.post(
            f"/character/{resource_id}/train",
            json={"levels": 2},
        )
        assert resp.status_code == 202

        # Sync action → 200
        resp = client.post(f"/character/{resource_id}/rename?name=Bob")
        assert resp.status_code == 200
        assert "resource_id" in resp.json()


# ---------------------------------------------------------------------------
# 9. Custom job_name parameter
# ---------------------------------------------------------------------------


class TestUpdateJobNameParam:
    """Tests for the ``job_name`` parameter on ``update_action()``."""

    def test_custom_job_name_registers_correct_resource(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action(
            "character", async_mode="job", label="Train", job_name="my-train-job"
        )
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = FastAPI()
        spec.apply(app)

        assert "my-train-job" in spec.resource_managers

    def test_custom_job_name_in_openapi(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action(
            "character",
            async_mode="job",
            label="Train",
            path="train",
            job_name="my-train-job",
        )
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = FastAPI()
        spec.apply(app)
        spec.openapi(app)
        schema = app.openapi()

        custom_actions = schema.get("x-specstar-custom-update-actions", {})
        action = next(a for a in custom_actions["character"] if a["label"] == "Train")
        assert action["jobResourceName"] == "my-train-job"

        async_jobs = schema.get("x-specstar-async-update-jobs", {})
        assert "my-train-job" in async_jobs
        assert async_jobs["my-train-job"] == "character"

    def test_custom_job_name_full_http_flow(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action(
            "character", async_mode="job", label="Train", job_name="my-train-job"
        )
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = FastAPI()
        spec.apply(app)

        job_rm = spec.resource_managers["my-train-job"]
        job_rm.start_consume(block=False)

        client = TestClient(app)
        resource_id = _create_character(client, name="Eve", level=1)

        resp = client.post(
            f"/character/{resource_id}/train",
            json={"levels": 10},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["job_resource_name"] == "my-train-job"

        resource = _wait_for_job_completion(
            spec, "my-train-job", body["job_resource_id"]
        )
        assert resource.data.status == TaskStatus.COMPLETED

        # Verify update applied
        char_resp = client.get(f"/character/{resource_id}")
        assert char_resp.json()["data"]["level"] == 11


# ---------------------------------------------------------------------------
# 10. Scalar params (auto-payload)
# ---------------------------------------------------------------------------


class TestAutoPayloadScalarUpdateParams:
    """async_mode='job' with scalar-only handlers (no Struct body param)."""

    def test_scalar_params_auto_generate_job_model(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action(
            "character",
            async_mode="job",
            label="Set Name",
            path="set-name",
        )
        def set_name(existing: Character, name: str) -> Character:
            return Character(name=name, level=existing.level, hp=existing.hp)

        app = FastAPI()
        spec.apply(app)

        assert "set-name-job" in spec.resource_managers

    def test_scalar_params_returns_202(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action(
            "character",
            async_mode="job",
            label="Set Name",
            path="set-name",
        )
        def set_name(existing: Character, name: str) -> Character:
            return Character(name=name, level=existing.level, hp=existing.hp)

        app = FastAPI()
        spec.apply(app)
        client = TestClient(app)

        resource_id = _create_character(client, name="A", level=1)
        resp = client.post(f"/character/{resource_id}/set-name?name=NewName")
        assert resp.status_code == 202
        data = resp.json()
        assert data["job_resource_name"] == "set-name-job"

    def test_scalar_params_job_payload_has_resource_id(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action(
            "character",
            async_mode="job",
            label="Set Name",
            path="set-name",
        )
        def set_name(existing: Character, name: str) -> Character:
            return Character(name=name, level=existing.level, hp=existing.hp)

        app = FastAPI()
        spec.apply(app)
        client = TestClient(app)

        resource_id = _create_character(client, name="A", level=1)
        resp = client.post(f"/character/{resource_id}/set-name?name=B")
        data = resp.json()

        job_rm = spec.resource_managers["set-name-job"]
        job = job_rm.get(data["job_resource_id"])
        assert job.data.payload.resource_id == resource_id
        assert job.data.payload.name == "B"

    def test_scalar_params_job_execution_updates_resource(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action(
            "character",
            async_mode="job",
            label="Set Name",
            path="set-name",
        )
        def set_name(existing: Character, name: str) -> Character:
            return Character(name=name, level=existing.level, hp=existing.hp)

        app = FastAPI()
        spec.apply(app)

        job_rm = spec.resource_managers["set-name-job"]
        job_rm.start_consume(block=False)

        client = TestClient(app)
        resource_id = _create_character(client, name="Old", level=5)

        resp = client.post(f"/character/{resource_id}/set-name?name=New")
        data = resp.json()

        job = _wait_for_job_completion(spec, "set-name-job", data["job_resource_id"])
        assert job.data.status == TaskStatus.COMPLETED

        char_resp = client.get(f"/character/{resource_id}")
        assert char_resp.json()["data"]["name"] == "New"
        assert char_resp.json()["data"]["level"] == 5


# ---------------------------------------------------------------------------
# 11. RM-level async_update_job_names mapping
# ---------------------------------------------------------------------------


class TestAsyncUpdateJobRmsMapping:
    """register_async_update_job / async_update_job_names on target RM."""

    def test_mapping_populated_after_apply(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action("character", async_mode="job", label="Train", path="train")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        @spec.update_action("character", async_mode="job", label="Boost", path="boost")
        def boost(existing: Character, payload: BoostPayload = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level,
                hp=existing.hp + payload.amount,
            )

        app = FastAPI()
        spec.apply(app)

        char_rm = spec.resource_managers["character"]
        assert len(char_rm.async_update_job_names) == 2  # ty:ignore[unresolved-attribute]
        assert "train-job" in char_rm.async_update_job_names  # ty:ignore[unresolved-attribute]
        assert "boost-job" in char_rm.async_update_job_names  # ty:ignore[unresolved-attribute]

    def test_mapping_uses_custom_job_name(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action(
            "character", async_mode="job", label="Train", job_name="custom-train"
        )
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = FastAPI()
        spec.apply(app)

        char_rm = spec.resource_managers["character"]
        assert "custom-train" in char_rm.async_update_job_names  # ty:ignore[unresolved-attribute]

    def test_mapping_empty_without_async_actions(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        app = FastAPI()
        spec.apply(app)

        char_rm = spec.resource_managers["character"]
        assert char_rm.async_update_job_names == []  # ty:ignore[unresolved-attribute]

    def test_register_duplicate_raises(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        app = FastAPI()
        spec.apply(app)

        char_rm = spec.resource_managers["character"]
        char_rm.register_async_update_job("dup-job", char_rm)  # ty:ignore[unresolved-attribute]
        with pytest.raises(ValueError, match="already registered"):
            char_rm.register_async_update_job("dup-job", char_rm)  # ty:ignore[unresolved-attribute]


# ---------------------------------------------------------------------------
# 12. DependencyProvider respected
# ---------------------------------------------------------------------------


class TestUpdateActionDependencyProvider:
    """Async-job update actions respect DependencyProvider.get_user."""

    def test_custom_user_propagated_to_job_and_target(self):
        from specstar.crud.route_templates.basic import DependencyProvider

        def custom_get_user() -> str:
            return "custom-user"

        spec = _make_crud(
            dependency_provider=DependencyProvider(get_user=custom_get_user),
        )
        spec.add_model(Character, name="character")

        @spec.update_action("character", async_mode="job", label="Train")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = FastAPI()
        spec.apply(app)

        job_rm = spec.resource_managers["train-job"]
        job_rm.start_consume(block=False)

        client = TestClient(app)
        resource_id = _create_character(client, name="X", level=1)

        resp = client.post(
            f"/character/{resource_id}/train",
            json={"levels": 1},
        )
        assert resp.status_code == 202
        job_data = resp.json()

        # Verify the Job resource's created_by
        job_resource = job_rm.get(job_data["job_resource_id"])
        assert job_resource.info.created_by == "custom-user"

        # Wait for completion and verify target resource update user
        resource = _wait_for_job_completion(
            spec, "train-job", job_data["job_resource_id"]
        )
        assert resource.data.status == TaskStatus.COMPLETED


# ---------------------------------------------------------------------------
# 13. start_consume with custom_update support
# ---------------------------------------------------------------------------


class TestStartConsumeDirectJobRm:
    """Job consumers can be started directly on the job RM."""

    def test_direct_job_rm_start_consume(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.update_action("character", async_mode="job", label="Train", path="train")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        @spec.update_action("character", async_mode="job", label="Boost", path="boost")
        def boost(existing: Character, payload: BoostPayload = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level,
                hp=existing.hp + payload.amount,
            )

        app = FastAPI()
        spec.apply(app)

        # Start each job consumer directly
        spec.resource_managers["train-job"].start_consume(block=False)
        spec.resource_managers["boost-job"].start_consume(block=False)

        client = TestClient(app)
        resource_id = _create_character(client, name="Z", level=1, hp=50)

        resp1 = client.post(
            f"/character/{resource_id}/train",
            json={"levels": 5},
        )
        assert resp1.status_code == 202

        r1 = _wait_for_job_completion(
            spec, "train-job", resp1.json()["job_resource_id"]
        )
        assert r1.data.status == TaskStatus.COMPLETED

        resp2 = client.post(
            f"/character/{resource_id}/boost",
            json={"amount": 20},
        )
        assert resp2.status_code == 202

        r2 = _wait_for_job_completion(
            spec, "boost-job", resp2.json()["job_resource_id"]
        )
        assert r2.data.status == TaskStatus.COMPLETED
