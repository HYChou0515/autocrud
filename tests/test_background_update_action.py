"""Tests for background update action (async_mode='background').

Covers:
- Decorator accepts async_mode='background' and stores it in _PendingUpdateAction
- apply() does NOT generate a Job model for background actions
- POST to background update → HTTP 202 + BackgroundTaskAccepted
- Background task lazy-fetches existing, calls handler, auto-updates resource
- Handler returns None → no update performed
- OpenAPI spec contains asyncMode='background' but no jobResourceName
- async handler (async def) and sync handler (def) both supported
- Errors in background task are logged, not raised
- Modify mode supported in background update actions
"""

import asyncio
import datetime as dt

import msgspec
from fastapi import Body, FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct

from autocrud.crud.core import AutoCRUD
from autocrud.types import BackgroundTaskAccepted

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


def _make_crud(**kwargs) -> AutoCRUD:
    return AutoCRUD(
        default_user="tester",
        default_now=dt.datetime.now,
        **kwargs,
    )


def _build_app(crud: AutoCRUD) -> FastAPI:
    app = FastAPI()
    crud.apply(app)
    return app


def _create_character(client, name="Alice", level=5, hp=100) -> str:
    """Create a Character via the HTTP API and return the resource_id."""
    resp = client.post(
        "/character/",
        json={"name": name, "level": level, "hp": hp},
    )
    assert resp.status_code == 200
    return resp.json()["resource_id"]


# ---------------------------------------------------------------------------
# 1. Decorator stores async_mode='background' metadata
# ---------------------------------------------------------------------------


class TestBackgroundUpdateActionDecorator:
    """@crud.update_action(async_mode='background') stores metadata."""

    def test_async_mode_stored_in_pending_action(self):
        crud = _make_crud()
        crud.add_model(Character, name="character")

        @crud.update_action("character", async_mode="background", label="Train BG")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        assert len(crud._pending_update_actions) == 1
        action = crud._pending_update_actions[0]
        assert action.async_mode == "background"
        assert action.label == "Train BG"

    def test_default_async_mode_is_none(self):
        crud = _make_crud()
        crud.add_model(Character, name="character")

        @crud.update_action("character", label="Rename")
        def rename(existing: Character, name: str) -> Character:
            return Character(name=name, level=existing.level, hp=existing.hp)

        action = crud._pending_update_actions[0]
        assert action.async_mode is None


# ---------------------------------------------------------------------------
# 2. No Job model registered for background mode
# ---------------------------------------------------------------------------


class TestBackgroundUpdateNoJobModel:
    """async_mode='background' does NOT generate a Job model."""

    def test_no_job_model_registered(self):
        crud = _make_crud()
        crud.add_model(Character, name="character")

        @crud.update_action("character", async_mode="background", label="Train BG")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = _build_app(crud)

        job_rms = [name for name in crud.resource_managers if "job" in name.lower()]
        assert job_rms == [], f"Unexpected Job resources: {job_rms}"


# ---------------------------------------------------------------------------
# 3. POST → HTTP 202 + BackgroundTaskAccepted
# ---------------------------------------------------------------------------


class TestBackgroundUpdateActionEndpoint:
    """POST to a background update action returns 202 immediately."""

    def test_sync_handler_returns_202(self):
        crud = _make_crud()
        crud.add_model(Character, name="character")

        @crud.update_action("character", async_mode="background", label="Train BG")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = _build_app(crud)
        client = TestClient(app)

        resource_id = _create_character(client, name="Alice", level=5)
        resp = client.post(
            f"/character/{resource_id}/train",
            json={"levels": 3},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["message"] == "Task accepted"

    def test_async_handler_returns_202(self):
        crud = _make_crud()
        crud.add_model(Character, name="character")

        @crud.update_action("character", async_mode="background", label="Async Train")
        async def async_train(
            existing: Character, payload: TrainRequest = Body(...)
        ) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = _build_app(crud)
        client = TestClient(app)

        resource_id = _create_character(client, name="Bob", level=10)
        resp = client.post(
            f"/character/{resource_id}/async-train",
            json={"levels": 1},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["message"] == "Task accepted"


# ---------------------------------------------------------------------------
# 4. Background task updates resource
# ---------------------------------------------------------------------------


class TestBackgroundAutoUpdate:
    """Background handler updates target resource after completion."""

    def test_sync_handler_updates_resource(self):
        crud = _make_crud()
        crud.add_model(Character, name="character")

        @crud.update_action("character", async_mode="background", label="Train BG")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = _build_app(crud)
        # TestClient runs background tasks synchronously before returning
        client = TestClient(app)

        resource_id = _create_character(client, name="Alice", level=5, hp=100)
        resp = client.post(
            f"/character/{resource_id}/train",
            json={"levels": 3},
        )
        assert resp.status_code == 202

        # Verify update applied
        char_resp = client.get(f"/character/{resource_id}")
        assert char_resp.status_code == 200
        char_data = char_resp.json()["data"]
        assert char_data["level"] == 8  # 5 + 3
        assert char_data["name"] == "Alice"

    def test_async_handler_updates_resource(self):
        crud = _make_crud()
        crud.add_model(Character, name="character")

        @crud.update_action("character", async_mode="background", label="Async Train")
        async def async_train(
            existing: Character, payload: TrainRequest = Body(...)
        ) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = _build_app(crud)
        client = TestClient(app)

        resource_id = _create_character(client, name="Bob", level=10, hp=50)
        resp = client.post(
            f"/character/{resource_id}/async-train",
            json={"levels": 5},
        )
        assert resp.status_code == 202

        char_resp = client.get(f"/character/{resource_id}")
        char_data = char_resp.json()["data"]
        assert char_data["level"] == 15
        assert char_data["name"] == "Bob"


# ---------------------------------------------------------------------------
# 5. Handler returns None → no update
# ---------------------------------------------------------------------------


class TestBackgroundUpdateReturnsNone:
    """When the handler returns None, no update is performed."""

    def test_sync_handler_returns_none_no_update(self):
        crud = _make_crud()
        crud.add_model(Character, name="character")

        @crud.update_action("character", async_mode="background", label="Maybe Update")
        def maybe_update(
            existing: Character, payload: TrainRequest = Body(...)
        ) -> None:
            return None

        app = _build_app(crud)
        client = TestClient(app)

        resource_id = _create_character(client, name="Carol", level=7)
        resp = client.post(
            f"/character/{resource_id}/maybe-update",
            json={"levels": 99},
        )
        assert resp.status_code == 202

        # Character should be unchanged
        char_resp = client.get(f"/character/{resource_id}")
        assert char_resp.json()["data"]["level"] == 7

    def test_async_handler_returns_none_no_update(self):
        crud = _make_crud()
        crud.add_model(Character, name="character")

        @crud.update_action("character", async_mode="background", label="Async Maybe")
        async def async_maybe(
            existing: Character, payload: TrainRequest = Body(...)
        ) -> None:
            return None

        app = _build_app(crud)
        client = TestClient(app)

        resource_id = _create_character(client, name="Dave", level=3)
        resp = client.post(
            f"/character/{resource_id}/async-maybe",
            json={"levels": 50},
        )
        assert resp.status_code == 202

        char_resp = client.get(f"/character/{resource_id}")
        assert char_resp.json()["data"]["level"] == 3


# ---------------------------------------------------------------------------
# 6. OpenAPI spec: asyncMode='background', no jobResourceName
# ---------------------------------------------------------------------------


class TestBackgroundUpdateOpenAPI:
    """OpenAPI extension metadata for background update actions."""

    def test_openapi_has_async_mode_background(self):
        crud = _make_crud()
        crud.add_model(Character, name="character")

        @crud.update_action("character", async_mode="background", label="Train BG")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = _build_app(crud)
        crud.openapi(app)
        schema = app.openapi()

        actions = schema.get("x-autocrud-custom-update-actions", {})
        assert "character" in actions
        article_actions = actions["character"]
        assert len(article_actions) == 1
        action_info = article_actions[0]
        assert action_info["asyncMode"] == "background"
        assert "jobResourceName" not in action_info

    def test_openapi_no_async_update_jobs_for_background(self):
        """x-autocrud-async-update-jobs should NOT contain background actions."""
        crud = _make_crud()
        crud.add_model(Character, name="character")

        @crud.update_action("character", async_mode="background", label="Train BG")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = _build_app(crud)
        crud.openapi(app)
        schema = app.openapi()

        async_jobs = schema.get("x-autocrud-async-update-jobs", {})
        assert async_jobs == {}


# ---------------------------------------------------------------------------
# 7. Error handling — background task logs errors
# ---------------------------------------------------------------------------


class TestBackgroundUpdateErrorHandling:
    """Errors in background tasks are logged, not propagated."""

    def test_sync_handler_error_does_not_crash(self):
        crud = _make_crud()
        crud.add_model(Character, name="character")

        @crud.update_action("character", async_mode="background", label="Failing")
        def failing(
            existing: Character, payload: TrainRequest = Body(...)
        ) -> Character:
            raise ValueError("Something went wrong")

        app = _build_app(crud)
        client = TestClient(app, raise_server_exceptions=False)

        resource_id = _create_character(client, name="Err", level=1)
        resp = client.post(
            f"/character/{resource_id}/failing",
            json={"levels": 1},
        )
        assert resp.status_code == 202

        # Character should be unchanged
        char_resp = client.get(f"/character/{resource_id}")
        assert char_resp.json()["data"]["level"] == 1

    def test_async_handler_error_does_not_crash(self):
        crud = _make_crud()
        crud.add_model(Character, name="character")

        @crud.update_action("character", async_mode="background", label="Async Failing")
        async def async_failing(
            existing: Character, payload: TrainRequest = Body(...)
        ) -> Character:
            raise RuntimeError("Async failure")

        app = _build_app(crud)
        client = TestClient(app, raise_server_exceptions=False)

        resource_id = _create_character(client, name="ErrA", level=2)
        resp = client.post(
            f"/character/{resource_id}/async-failing",
            json={"levels": 1},
        )
        assert resp.status_code == 202

        char_resp = client.get(f"/character/{resource_id}")
        assert char_resp.json()["data"]["level"] == 2


# ---------------------------------------------------------------------------
# 8. Modify mode in background
# ---------------------------------------------------------------------------


class TestBackgroundUpdateMode:
    """Background update with mode='update' creates a new revision."""

    def test_update_mode_creates_new_revision(self):
        crud = _make_crud()
        crud.add_model(Character, name="character")

        @crud.update_action(
            "character",
            async_mode="background",
            label="Boost HP BG",
        )
        def boost_hp(
            existing: Character, payload: BoostPayload = Body(...)
        ) -> Character:
            return Character(
                name=existing.name,
                level=existing.level,
                hp=existing.hp + payload.amount,
            )

        app = _build_app(crud)
        client = TestClient(app)

        resource_id = _create_character(client, name="Mod", level=3, hp=50)
        resp = client.post(
            f"/character/{resource_id}/boost-hp",
            json={"amount": 25},
        )
        assert resp.status_code == 202

        char_resp = client.get(f"/character/{resource_id}")
        char_data = char_resp.json()["data"]
        assert char_data["hp"] == 75
        assert char_data["level"] == 3


# ---------------------------------------------------------------------------
# 9. Mixed: background + sync update actions on same resource
# ---------------------------------------------------------------------------


class TestBackgroundUpdateMixedActions:
    """Background and sync update actions coexist on the same resource."""

    def test_background_and_sync_both_work(self):
        crud = _make_crud()
        crud.add_model(Character, name="character")

        @crud.update_action("character", label="Sync Rename")
        def sync_rename(existing: Character, name: str) -> Character:
            return Character(name=name, level=existing.level, hp=existing.hp)

        @crud.update_action("character", async_mode="background", label="BG Train")
        def bg_train(
            existing: Character, payload: TrainRequest = Body(...)
        ) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = _build_app(crud)
        client = TestClient(app)

        resource_id = _create_character(client, name="Mix", level=5)

        # Sync action returns 200 with RevisionInfo
        resp1 = client.post(f"/character/{resource_id}/sync-rename?name=NewName")
        assert resp1.status_code == 200

        # Background action returns 202
        resp2 = client.post(
            f"/character/{resource_id}/bg-train",
            json={"levels": 2},
        )
        assert resp2.status_code == 202
        assert resp2.json()["message"] == "Task accepted"

        # Verify both changes applied
        char_resp = client.get(f"/character/{resource_id}")
        char_data = char_resp.json()["data"]
        assert char_data["name"] == "NewName"
        assert char_data["level"] == 7


# ---------------------------------------------------------------------------
# 10. Background task _run_bg is always sync
# ---------------------------------------------------------------------------


class TestBackgroundUpdateTaskIsSync:
    """_run_bg must always be a plain sync function."""

    def test_async_handler_bg_task_is_not_coroutine(self):
        crud = _make_crud()
        crud.add_model(Character, name="character")

        @crud.update_action("character", async_mode="background", label="Async Train")
        async def async_train(
            existing: Character, payload: TrainRequest = Body(...)
        ) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = _build_app(crud)

        captured_tasks: list = []
        from starlette.background import BackgroundTasks

        original_add_task = BackgroundTasks.add_task

        def spy_add_task(self, func, *args, **kwargs):
            captured_tasks.append(func)
            return original_add_task(self, func, *args, **kwargs)

        BackgroundTasks.add_task = spy_add_task  # ty:ignore[invalid-assignment]
        try:
            client = TestClient(app)
            resource_id = _create_character(client, name="A", level=1)
            resp = client.post(
                f"/character/{resource_id}/async-train",
                json={"levels": 1},
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
        crud = _make_crud()
        crud.add_model(Character, name="character")

        @crud.update_action("character", async_mode="background", label="Train BG")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = _build_app(crud)

        captured_tasks: list = []
        from starlette.background import BackgroundTasks

        original_add_task = BackgroundTasks.add_task

        def spy_add_task(self, func, *args, **kwargs):
            captured_tasks.append(func)
            return original_add_task(self, func, *args, **kwargs)

        BackgroundTasks.add_task = spy_add_task  # ty:ignore[invalid-assignment]
        try:
            client = TestClient(app)
            resource_id = _create_character(client, name="B", level=2)
            resp = client.post(
                f"/character/{resource_id}/train",
                json={"levels": 1},
            )
            assert resp.status_code == 202
        finally:
            BackgroundTasks.add_task = original_add_task

        assert len(captured_tasks) == 1
        task_fn = captured_tasks[0]
        assert not asyncio.iscoroutinefunction(task_fn)


# ---------------------------------------------------------------------------
# 11. BackgroundTaskAccepted type
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
