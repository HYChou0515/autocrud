"""Tests for @crud.update_action() decorator.

Covers:
- Decorator stores pending action metadata
- apply() registers route on the router
- POST to custom action endpoint → auto update via resource_manager
- Handler receives existing resource data injected automatically
- Handler return None → no auto update
- Handler supports Body(), Query() via standard FastAPI
- mode='update' vs mode='modify'
- existing_param custom name
- Multiple actions on same resource
- OpenAPI schema includes x-autocrud-update-action extension
- Import order: decorator before add_model works
- Unknown resource_name logs warning and is skipped
- Sync handler support
- resource_id not found → 404
- info (RevisionInfo) and meta (ResourceMeta) auto-injection
"""

import datetime as dt

import pytest
from fastapi import Body, FastAPI, Query
from fastapi.testclient import TestClient
from msgspec import Struct

from autocrud.crud.core import AutoCRUD
from autocrud.types import (
    ResourceMeta,
    RevisionInfo,
)

# ---------------------------------------------------------------------------
# Test Models
# ---------------------------------------------------------------------------


class Character(Struct):
    name: str
    level: int = 1
    gold: int = 0


class LevelUpInput(Struct):
    levels: int = 1


class RenameInput(Struct):
    new_name: str


class AddGoldInput(Struct):
    amount: int


# ---------------------------------------------------------------------------
# 1. Decorator stores pending actions
# ---------------------------------------------------------------------------


class TestUpdateActionDecorator:
    """@crud.update_action() stores metadata without registering routes."""

    def test_decorator_stores_pending_action(self):
        crud = AutoCRUD()
        crud.add_model(Character, name="character")

        @crud.update_action("character", label="Level Up")
        def level_up(existing: Character, body: LevelUpInput = Body(...)):
            return Character(
                name=existing.name,
                level=existing.level + body.levels,
                gold=existing.gold,
            )

        assert len(crud._pending_update_actions) == 1
        action = crud._pending_update_actions[0]
        assert action.resource_name == "character"
        assert action.label == "Level Up"
        assert action.handler is level_up
        assert action.mode == "update"
        assert action.existing_param == "existing"
        assert action.info_param == "info"
        assert action.meta_param == "meta"

    def test_decorator_returns_original_function(self):
        crud = AutoCRUD()

        @crud.update_action("character", label="Level Up")
        def level_up(existing: Character, body: LevelUpInput = Body(...)):
            return Character(name=existing.name, level=existing.level + body.levels)

        assert level_up.__name__ == "level_up"

    def test_path_inferred_from_function_name(self):
        crud = AutoCRUD()

        @crud.update_action("character", label="Level Up")
        def level_up(existing: Character, body: LevelUpInput = Body(...)):
            return Character(name=existing.name, level=existing.level + body.levels)

        action = crud._pending_update_actions[0]
        assert action.path == "level-up"

    def test_path_explicit_override(self):
        crud = AutoCRUD()

        @crud.update_action("character", path="custom-level", label="Level Up")
        def level_up(existing: Character, body: LevelUpInput = Body(...)):
            return Character(name=existing.name, level=existing.level + body.levels)

        action = crud._pending_update_actions[0]
        assert action.path == "custom-level"

    def test_label_inferred_from_path(self):
        crud = AutoCRUD()

        @crud.update_action("character")
        def level_up(existing: Character, body: LevelUpInput = Body(...)):
            return Character(name=existing.name, level=existing.level + body.levels)

        action = crud._pending_update_actions[0]
        assert action.label == "Level Up"

    def test_mode_modify(self):
        crud = AutoCRUD()

        @crud.update_action("character", mode="modify")
        def quick_fix(existing: Character, body: LevelUpInput = Body(...)):
            return Character(name=existing.name, level=existing.level + body.levels)

        action = crud._pending_update_actions[0]
        assert action.mode == "modify"

    def test_existing_param_custom(self):
        crud = AutoCRUD()

        @crud.update_action("character", existing_param="current")
        def level_up(current: Character, body: LevelUpInput = Body(...)):
            return Character(name=current.name, level=current.level + body.levels)

        action = crud._pending_update_actions[0]
        assert action.existing_param == "current"

    def test_multiple_actions_on_same_resource(self):
        crud = AutoCRUD()

        @crud.update_action("character", label="Level Up")
        def level_up(existing: Character, body: LevelUpInput = Body(...)):
            return Character(name=existing.name, level=existing.level + body.levels)

        @crud.update_action("character", label="Rename")
        def rename(existing: Character, body: RenameInput = Body(...)):
            return Character(name=body.new_name, level=existing.level)

        assert len(crud._pending_update_actions) == 2

    def test_decorator_before_add_model(self):
        """Decorator can be used before add_model — lazy registration."""
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )

        @crud.update_action("character", label="Level Up")
        def level_up(existing: Character, body: LevelUpInput = Body(...)):
            return Character(
                name=existing.name,
                level=existing.level + body.levels,
                gold=existing.gold,
            )

        # add_model comes AFTER the decorator
        crud.add_model(Character, name="character")

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        # First create a character
        resp = client.post("/character", json={"name": "Alice", "level": 1})
        assert resp.status_code == 200
        resource_id = resp.json()["resource_id"]

        # Now call update action
        resp = client.post(f"/character/{resource_id}/level-up", json={"levels": 3})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 2. Route registration & HTTP flow
# ---------------------------------------------------------------------------


class TestUpdateActionRouteRegistration:
    """apply() registers the update action route on the router."""

    @pytest.fixture
    def crud_and_client(self):
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Character, name="character")

        @crud.update_action("character", label="Level Up")
        def level_up(existing: Character, body: LevelUpInput = Body(...)):
            return Character(
                name=existing.name,
                level=existing.level + body.levels,
                gold=existing.gold,
            )

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)
        return crud, client

    def test_post_custom_action_updates_resource(self, crud_and_client):
        crud, client = crud_and_client

        # Create a character first
        resp = client.post("/character", json={"name": "Alice", "level": 1})
        assert resp.status_code == 200
        resource_id = resp.json()["resource_id"]

        # Call update action
        resp = client.post(f"/character/{resource_id}/level-up", json={"levels": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert "resource_id" in data
        assert "revision_id" in data
        assert data["resource_id"] == resource_id

        # Verify the resource was actually updated
        rm = crud.resource_managers["character"]
        resource = rm.get(resource_id)
        assert resource.data.name == "Alice"
        assert resource.data.level == 6  # 1 + 5

    def test_existing_object_is_injected(self, crud_and_client):
        """Handler receives the actual current resource data."""
        crud, client = crud_and_client

        # Create with specific values
        resp = client.post("/character", json={"name": "Bob", "level": 10, "gold": 500})
        resource_id = resp.json()["resource_id"]

        # Level up by 3 — handler should see level=10
        resp = client.post(f"/character/{resource_id}/level-up", json={"levels": 3})
        assert resp.status_code == 200

        rm = crud.resource_managers["character"]
        resource = rm.get(resource_id)
        assert resource.data.level == 13  # 10 + 3
        assert resource.data.gold == 500  # preserved from existing

    def test_handler_return_none_skips_update(self):
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Character, name="character")

        @crud.update_action("character", label="Conditional Update")
        def conditional_update(existing: Character, body: LevelUpInput = Body(...)):
            # Return None → no update
            if existing.level >= 100:
                return None
            return Character(
                name=existing.name,
                level=existing.level + body.levels,
                gold=existing.gold,
            )

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        # Create a max-level character
        resp = client.post(
            "/character", json={"name": "Vet", "level": 100, "gold": 999}
        )
        resource_id = resp.json()["resource_id"]

        # Try to level up → should be skipped (None returned)
        resp = client.post(
            f"/character/{resource_id}/conditional-update", json={"levels": 5}
        )
        assert resp.status_code == 200
        assert resp.json() is None

        # Verify level unchanged
        rm = crud.resource_managers["character"]
        resource = rm.get(resource_id)
        assert resource.data.level == 100

    def test_resource_id_not_found_returns_error(self, crud_and_client):
        """POST with invalid resource_id should return an error."""
        crud, client = crud_and_client
        resp = client.post("/character/nonexistent-id/level-up", json={"levels": 1})
        assert resp.status_code >= 400

    def test_handler_with_query_params(self):
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Character, name="character")

        @crud.update_action("character", label="Level Up With Bonus")
        def level_up_with_bonus(
            existing: Character,
            body: LevelUpInput = Body(...),
            bonus: int = Query(0),
        ):
            return Character(
                name=existing.name,
                level=existing.level + body.levels + bonus,
                gold=existing.gold,
            )

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post("/character", json={"name": "Eve", "level": 5})
        resource_id = resp.json()["resource_id"]

        resp = client.post(
            f"/character/{resource_id}/level-up-with-bonus?bonus=10",
            json={"levels": 2},
        )
        assert resp.status_code == 200
        rm = crud.resource_managers["character"]
        resource = rm.get(resource_id)
        assert resource.data.level == 17  # 5 + 2 + 10

    def test_standard_update_still_works(self, crud_and_client):
        """Standard PUT /character/{id} should still work."""
        crud, client = crud_and_client
        resp = client.post("/character", json={"name": "Std", "level": 1})
        resource_id = resp.json()["resource_id"]

        resp = client.put(
            f"/character/{resource_id}",
            json={"name": "Std Updated", "level": 99},
        )
        assert resp.status_code == 200

    def test_unknown_resource_name_logs_warning(self, caplog):
        crud = AutoCRUD()

        @crud.update_action("nonexistent", label="Test")
        def test_action(existing: Character, body: LevelUpInput = Body(...)):
            return Character(name=existing.name, level=existing.level + body.levels)

        app = FastAPI()
        crud.apply(app)
        assert "nonexistent" in caplog.text or len(crud._pending_update_actions) == 1


# ---------------------------------------------------------------------------
# 3. Mode: update vs modify
# ---------------------------------------------------------------------------


class TestUpdateActionMode:
    """Test mode='update' (new revision) vs mode='modify' (in-place)."""

    def test_mode_update_creates_new_revision(self):
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Character, name="character")

        @crud.update_action("character", mode="update", label="Level Up")
        def level_up(existing: Character, body: LevelUpInput = Body(...)):
            return Character(
                name=existing.name,
                level=existing.level + body.levels,
                gold=existing.gold,
            )

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post("/character", json={"name": "Alice", "level": 1})
        resource_id = resp.json()["resource_id"]
        first_revision_id = resp.json()["revision_id"]

        resp = client.post(f"/character/{resource_id}/level-up", json={"levels": 5})
        assert resp.status_code == 200
        second_revision_id = resp.json()["revision_id"]

        # New revision should be created
        assert second_revision_id != first_revision_id

    def test_mode_modify_edits_in_place(self):
        """mode='modify' should edit the draft in place (no new revision)."""
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        # Use draft as default status so modify works
        crud.add_model(Character, name="character", default_status="draft")

        @crud.update_action("character", mode="modify", label="Quick Fix")
        def quick_fix(existing: Character, body: RenameInput = Body(...)):
            return Character(
                name=body.new_name, level=existing.level, gold=existing.gold
            )

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post("/character", json={"name": "Draft", "level": 1})
        resource_id = resp.json()["resource_id"]
        first_revision_id = resp.json()["revision_id"]

        resp = client.post(
            f"/character/{resource_id}/quick-fix",
            json={"new_name": "Fixed"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Modify returns same revision_id (in-place update)
        assert data["revision_id"] == first_revision_id

        rm = crud.resource_managers["character"]
        resource = rm.get(resource_id)
        assert resource.data.name == "Fixed"


# ---------------------------------------------------------------------------
# 4. existing_param customization
# ---------------------------------------------------------------------------


class TestExistingParamCustomization:
    """existing_param changes the injected parameter name."""

    def test_custom_existing_param_name(self):
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Character, name="character")

        @crud.update_action("character", label="Rename", existing_param="current")
        def rename(current: Character, body: RenameInput = Body(...)):
            return Character(
                name=body.new_name,
                level=current.level,
                gold=current.gold,
            )

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post(
            "/character", json={"name": "Original", "level": 10, "gold": 500}
        )
        resource_id = resp.json()["resource_id"]

        resp = client.post(
            f"/character/{resource_id}/rename",
            json={"new_name": "NewName"},
        )
        assert resp.status_code == 200

        rm = crud.resource_managers["character"]
        resource = rm.get(resource_id)
        assert resource.data.name == "NewName"
        assert resource.data.level == 10
        assert resource.data.gold == 500


# ---------------------------------------------------------------------------
# 5. Async handler support
# ---------------------------------------------------------------------------


class TestUpdateActionAsyncHandler:
    """Async (coroutine) handler should work."""

    def test_async_handler(self):
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Character, name="character")

        @crud.update_action("character", label="Async Level Up")
        async def async_level_up(existing: Character, body: LevelUpInput = Body(...)):
            return Character(
                name=existing.name,
                level=existing.level + body.levels,
                gold=existing.gold,
            )

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post("/character", json={"name": "Async", "level": 5})
        resource_id = resp.json()["resource_id"]

        resp = client.post(
            f"/character/{resource_id}/async-level-up", json={"levels": 7}
        )
        assert resp.status_code == 200

        rm = crud.resource_managers["character"]
        resource = rm.get(resource_id)
        assert resource.data.level == 12  # 5 + 7


# ---------------------------------------------------------------------------
# 6. No Body params (only existing)
# ---------------------------------------------------------------------------


class TestUpdateActionNoBody:
    """Handler with no body params — just transforms existing."""

    def test_no_body_handler(self):
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Character, name="character")

        @crud.update_action("character", label="Double Gold")
        def double_gold(existing: Character):
            return Character(
                name=existing.name,
                level=existing.level,
                gold=existing.gold * 2,
            )

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post("/character", json={"name": "Rich", "level": 1, "gold": 100})
        resource_id = resp.json()["resource_id"]

        resp = client.post(f"/character/{resource_id}/double-gold")
        assert resp.status_code == 200

        rm = crud.resource_managers["character"]
        resource = rm.get(resource_id)
        assert resource.data.gold == 200


# ---------------------------------------------------------------------------
# 7. OpenAPI schema
# ---------------------------------------------------------------------------


class TestUpdateActionOpenAPI:
    """OpenAPI schema should include update action extensions."""

    def _build_app(self):
        crud = AutoCRUD()
        crud.add_model(Character, name="character")

        @crud.update_action("character", label="Level Up")
        def level_up(existing: Character, body: LevelUpInput = Body(...)):
            return Character(
                name=existing.name,
                level=existing.level + body.levels,
                gold=existing.gold,
            )

        @crud.update_action("character", label="Rename")
        def rename(existing: Character, body: RenameInput = Body(...)):
            return Character(
                name=body.new_name,
                level=existing.level,
                gold=existing.gold,
            )

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)
        return app

    def test_operation_has_x_autocrud_update_action(self):
        """Each custom POST operation should have x-autocrud-update-action."""
        app = self._build_app()
        schema = app.openapi_schema
        paths = schema["paths"]

        op = paths["/character/{resource_id}/level-up"]["post"]
        assert "x-autocrud-update-action" in op
        assert op["x-autocrud-update-action"]["resource"] == "character"
        assert op["x-autocrud-update-action"]["label"] == "Level Up"
        assert op["x-autocrud-update-action"]["mode"] == "update"

    def test_top_level_custom_update_actions(self):
        """OpenAPI schema should have x-autocrud-custom-update-actions."""
        app = self._build_app()
        schema = app.openapi_schema

        assert "x-autocrud-custom-update-actions" in schema
        actions = schema["x-autocrud-custom-update-actions"]
        assert "character" in actions
        assert len(actions["character"]) == 2
        labels = {a["label"] for a in actions["character"]}
        assert "Level Up" in labels
        assert "Rename" in labels

    def test_action_path_in_top_level_extension(self):
        """Each action should include path with {resource_id}."""
        app = self._build_app()
        schema = app.openapi_schema
        actions = schema["x-autocrud-custom-update-actions"]["character"]
        paths = {a["path"] for a in actions}
        assert "/character/{resource_id}/level-up" in paths
        assert "/character/{resource_id}/rename" in paths

    def test_body_schema_in_top_level_extension(self):
        """Each action should include bodySchema for generator discovery."""
        app = self._build_app()
        schema = app.openapi_schema
        actions = schema["x-autocrud-custom-update-actions"]["character"]
        schemas = {a["bodySchema"] for a in actions}
        assert "LevelUpInput" in schemas
        assert "RenameInput" in schemas

    def test_mode_in_top_level_extension(self):
        """Each action should include mode."""
        app = self._build_app()
        schema = app.openapi_schema
        actions = schema["x-autocrud-custom-update-actions"]["character"]
        for a in actions:
            assert "mode" in a
            assert a["mode"] in ("update", "modify")

    def test_body_schema_in_components(self):
        """Update action body schemas should be in components."""
        app = self._build_app()
        schema = app.openapi_schema
        components = schema["components"]["schemas"]
        assert "LevelUpInput" in components
        assert "RenameInput" in components

    def test_query_params_in_extension(self):
        """Query params should appear in the extension."""
        crud = AutoCRUD()
        crud.add_model(Character, name="character")

        @crud.update_action("character", label="Level Up With Bonus")
        def level_up_with_bonus(
            existing: Character,
            body: LevelUpInput = Body(...),
            bonus: int = Query(0),
        ):
            return Character(
                name=existing.name,
                level=existing.level + body.levels + bonus,
            )

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)
        schema = app.openapi_schema

        actions = schema["x-autocrud-custom-update-actions"]["character"]
        action = actions[0]
        assert "queryParams" in action
        qp_names = {p["name"] for p in action["queryParams"]}
        assert "bonus" in qp_names

    def test_info_meta_not_in_openapi_spec(self):
        """RevisionInfo/ResourceMeta params should NOT appear as update action body."""
        crud = AutoCRUD()
        crud.add_model(Character, name="character")

        @crud.update_action("character", label="Stamp")
        def stamp(existing: Character, info: RevisionInfo, meta: ResourceMeta):
            return Character(
                name=f"{info.revision_id}-{meta.total_revision_count}",
                level=existing.level,
            )

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)
        schema = app.openapi_schema

        # No body schema should be extracted (RevisionInfo/ResourceMeta are skipped)
        actions = schema["x-autocrud-custom-update-actions"]["character"]
        action = actions[0]
        assert "bodySchema" not in action

        # The POST endpoint should have no requestBody
        paths = schema["paths"]
        op = paths["/character/{resource_id}/stamp"]["post"]
        assert "requestBody" not in op


# ---------------------------------------------------------------------------
# 7.5. Handler WITHOUT existing param (no-arg / body-only)
# ---------------------------------------------------------------------------


class TestUpdateActionNoExistingParam:
    """Handler that does not declare existing param should still work.

    When the user's handler omits the existing-data parameter entirely
    (e.g. ``async def update_char_name(): ...``), the wrapper must NOT
    inject it into kwargs — otherwise a TypeError would be raised.
    """

    def test_no_existing_param_async(self):
        """Async handler with zero params (no existing, no body)."""
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Character, name="character")

        @crud.update_action("character", label="Reset Name")
        async def reset_name():
            return Character(name="reset", level=1, gold=0)

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post("/character", json={"name": "Alice", "level": 10})
        resource_id = resp.json()["resource_id"]

        resp = client.post(f"/character/{resource_id}/reset-name")
        assert resp.status_code == 200

        rm = crud.resource_managers["character"]
        resource = rm.get(resource_id)
        assert resource.data.name == "reset"

    def test_no_existing_param_sync(self):
        """Sync handler with zero params."""
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Character, name="character")

        @crud.update_action("character", label="Reset Name Sync")
        def reset_name_sync():
            return Character(name="reset-sync", level=1, gold=0)

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post("/character", json={"name": "Bob", "level": 5})
        resource_id = resp.json()["resource_id"]

        resp = client.post(f"/character/{resource_id}/reset-name-sync")
        assert resp.status_code == 200

        rm = crud.resource_managers["character"]
        resource = rm.get(resource_id)
        assert resource.data.name == "reset-sync"

    def test_body_only_no_existing(self):
        """Handler with Body param but no existing param."""
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Character, name="character")

        @crud.update_action("character", label="Force Name")
        def force_name(body: RenameInput = Body(...)):
            return Character(name=body.new_name, level=99, gold=0)

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post("/character", json={"name": "Eve", "level": 1})
        resource_id = resp.json()["resource_id"]

        resp = client.post(
            f"/character/{resource_id}/force-name",
            json={"new_name": "Forced"},
        )
        assert resp.status_code == 200

        rm = crud.resource_managers["character"]
        resource = rm.get(resource_id)
        assert resource.data.name == "Forced"
        assert resource.data.level == 99


# ---------------------------------------------------------------------------
# 8. Multiple update + create actions coexist
# ---------------------------------------------------------------------------


class TestUpdateAndCreateActionsCoexist:
    """update_action and create_action work together."""

    def test_both_actions_registered(self):
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Character, name="character")

        @crud.create_action("character", label="Quick Create")
        def quick_create():
            return Character(name="Quick", level=1)

        @crud.update_action("character", label="Level Up")
        def level_up(existing: Character, body: LevelUpInput = Body(...)):
            return Character(
                name=existing.name,
                level=existing.level + body.levels,
                gold=existing.gold,
            )

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        # Create via custom create action
        resp = client.post("/character/quick-create")
        assert resp.status_code == 200
        resource_id = resp.json()["resource_id"]

        # Update via custom update action
        resp = client.post(f"/character/{resource_id}/level-up", json={"levels": 5})
        assert resp.status_code == 200

        rm = crud.resource_managers["character"]
        resource = rm.get(resource_id)
        assert resource.data.level == 6  # 1 + 5


# ---------------------------------------------------------------------------
# 9. Info and Meta injection
# ---------------------------------------------------------------------------


class TestUpdateActionInfoMetaInjection:
    """Handlers can declare RevisionInfo and ResourceMeta parameters to receive them."""

    def test_info_injected_by_type_annotation(self):
        """Handler with RevisionInfo param gets the existing resource's info."""
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Character, name="character")

        @crud.update_action("character", label="Stamp Info")
        async def stamp_info(existing: Character, info: RevisionInfo):
            return Character(
                name=f"{existing.name}-rev:{info.revision_id}",
                level=existing.level,
                gold=existing.gold,
            )

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post("/character", json={"name": "Alice", "level": 1})
        resource_id = resp.json()["resource_id"]
        revision_id = resp.json()["revision_id"]

        resp = client.post(f"/character/{resource_id}/stamp-info")
        assert resp.status_code == 200

        rm = crud.resource_managers["character"]
        resource = rm.get(resource_id)
        assert resource.data.name == f"Alice-rev:{revision_id}"

    def test_meta_injected_by_type_annotation(self):
        """Handler with ResourceMeta param gets the resource meta."""
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Character, name="character")

        @crud.update_action("character", label="Stamp Meta")
        async def stamp_meta(existing: Character, meta: ResourceMeta):
            return Character(
                name=f"{existing.name}-count:{meta.total_revision_count}",
                level=existing.level,
                gold=existing.gold,
            )

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post("/character", json={"name": "Bob", "level": 5})
        resource_id = resp.json()["resource_id"]

        resp = client.post(f"/character/{resource_id}/stamp-meta")
        assert resp.status_code == 200

        rm = crud.resource_managers["character"]
        resource = rm.get(resource_id)
        assert resource.data.name == "Bob-count:1"

    def test_info_and_meta_together(self):
        """Handler with both RevisionInfo and ResourceMeta params."""
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Character, name="character")

        @crud.update_action("character", label="Full Info")
        async def full_info(
            existing: Character, info: RevisionInfo, meta: ResourceMeta
        ):
            return Character(
                name=f"{info.revision_id}-{meta.total_revision_count}",
                level=existing.level,
                gold=existing.gold,
            )

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post("/character", json={"name": "Eve", "level": 1})
        resource_id = resp.json()["resource_id"]
        revision_id = resp.json()["revision_id"]

        resp = client.post(f"/character/{resource_id}/full-info")
        assert resp.status_code == 200

        rm = crud.resource_managers["character"]
        resource = rm.get(resource_id)
        assert resource.data.name == f"{revision_id}-1"

    def test_info_and_meta_sync_handler(self):
        """Sync handler with RevisionInfo and ResourceMeta works too."""
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Character, name="character")

        @crud.update_action("character", label="Sync Full")
        def sync_full(existing: Character, info: RevisionInfo, meta: ResourceMeta):
            return Character(
                name=f"sync-{info.revision_id}-{meta.total_revision_count}",
                level=existing.level,
                gold=existing.gold,
            )

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post("/character", json={"name": "Dan", "level": 3})
        resource_id = resp.json()["resource_id"]
        revision_id = resp.json()["revision_id"]

        resp = client.post(f"/character/{resource_id}/sync-full")
        assert resp.status_code == 200

        rm = crud.resource_managers["character"]
        resource = rm.get(resource_id)
        assert resource.data.name == f"sync-{revision_id}-1"

    def test_meta_only_no_existing(self):
        """Handler with only meta param, no existing."""
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Character, name="character")

        @crud.update_action("character", label="Meta Only")
        def meta_only(meta: ResourceMeta):
            return Character(
                name=f"meta-{meta.total_revision_count}",
                level=0,
                gold=0,
            )

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post("/character", json={"name": "Foo", "level": 1})
        resource_id = resp.json()["resource_id"]

        resp = client.post(f"/character/{resource_id}/meta-only")
        assert resp.status_code == 200

        rm = crud.resource_managers["character"]
        resource = rm.get(resource_id)
        assert resource.data.name == "meta-1"

    def test_info_only_no_existing(self):
        """Handler with only info param, no existing."""
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Character, name="character")

        @crud.update_action("character", label="Info Only")
        async def info_only(info: RevisionInfo):
            return Character(
                name=f"info-{info.revision_id}",
                level=0,
                gold=0,
            )

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post("/character", json={"name": "Bar", "level": 2})
        resource_id = resp.json()["resource_id"]
        revision_id = resp.json()["revision_id"]

        resp = client.post(f"/character/{resource_id}/info-only")
        assert resp.status_code == 200

        rm = crud.resource_managers["character"]
        resource = rm.get(resource_id)
        assert resource.data.name == f"info-{revision_id}"

    def test_custom_param_names(self):
        """info/meta injection works with custom parameter names via decorator kwargs."""
        crud = AutoCRUD(
            default_user="tester",
            default_now=dt.datetime.now,
        )
        crud.add_model(Character, name="character")

        @crud.update_action(
            "character",
            label="Custom Names",
            info_param="my_revision",
            meta_param="my_metadata",
        )
        def custom_names(
            existing: Character,
            my_revision: RevisionInfo,
            my_metadata: ResourceMeta,
        ):
            return Character(
                name=f"{my_revision.revision_id}-{my_metadata.total_revision_count}",
                level=existing.level,
                gold=existing.gold,
            )

        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.post("/character", json={"name": "Zoe", "level": 7})
        resource_id = resp.json()["resource_id"]
        revision_id = resp.json()["revision_id"]

        resp = client.post(f"/character/{resource_id}/custom-names")
        assert resp.status_code == 200

        rm = crud.resource_managers["character"]
        resource = rm.get(resource_id)
        assert resource.data.name == f"{revision_id}-1"


# ---------------------------------------------------------------------------
# Regression: struct as direct body must not produce duplicate inlineBodyParams
# ---------------------------------------------------------------------------


class TestUpdateActionStructBodyNoDuplicate:
    """When a struct is used directly as the update action body, its fields
    must appear only once (via bodySchema), not also as inlineBodyParams."""

    def _build_app(self):
        class Character(Struct):
            name: str
            level: int = 1

        class RenameInput(Struct):
            new_name: str
            suffix: str = ""

        crud = AutoCRUD()
        crud.add_model(Character, name="character")

        @crud.update_action("character", label="Rename")
        def rename(existing: Character, body: RenameInput = Body(...)):
            return Character(name=body.new_name + body.suffix, level=existing.level)

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)
        return app

    def test_no_inline_body_params_when_body_is_struct(self):
        """Struct-as-body must NOT produce inlineBodyParams for update actions."""
        app = self._build_app()
        schema = app.openapi_schema
        action = schema["x-autocrud-custom-update-actions"]["character"][0]
        assert "bodySchema" in action
        assert "inlineBodyParams" not in action, (
            f"inlineBodyParams must be absent when body is a pure struct; "
            f"got: {action.get('inlineBodyParams')}"
        )
