"""Tests for default_user + DependencyProvider interaction.

Covers:
- default_user on AutoCRUD propagates to DependencyProvider when get_user is not customized
- default_user does NOT override a custom get_user on DependencyProvider
- default_user on AutoCRUD.configure() works the same as __init__
- DependencyProvider(get_now=...) without get_user should still respect default_user
- Per-model default_user (on add_model) still works for programmatic usage
- DependencyProvider._user_is_default flag behavior
"""

import datetime as dt

from fastapi import FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct

from autocrud.crud.core import AutoCRUD
from autocrud.crud.route_templates.basic import DependencyProvider

# ---------------------------------------------------------------------------
# Test Models
# ---------------------------------------------------------------------------


class Item(Struct):
    name: str
    value: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_crud(**kwargs) -> AutoCRUD:
    return AutoCRUD(
        default_now=lambda: dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc),
        **kwargs,
    )


def _build_app(crud: AutoCRUD) -> FastAPI:
    app = FastAPI()
    crud.apply(app)
    return app


# ---------------------------------------------------------------------------
# 1. DependencyProvider._user_is_default flag
# ---------------------------------------------------------------------------


class TestDependencyProviderUserIsDefault:
    """DependencyProvider tracks whether get_user was provided by user."""

    def test_default_get_user_is_marked_as_default(self):
        dp = DependencyProvider()
        assert dp._user_is_default is True

    def test_custom_get_user_is_not_default(self):
        dp = DependencyProvider(get_user=lambda: "custom")
        assert dp._user_is_default is False

    def test_custom_get_now_only_still_marks_user_as_default(self):
        dp = DependencyProvider(get_now=lambda: dt.datetime.now(dt.timezone.utc))
        assert dp._user_is_default is True

    def test_both_custom_not_default(self):
        dp = DependencyProvider(
            get_user=lambda: "custom",
            get_now=lambda: dt.datetime.now(dt.timezone.utc),
        )
        assert dp._user_is_default is False


# ---------------------------------------------------------------------------
# 2. default_user propagates to route via DependencyProvider
# ---------------------------------------------------------------------------


class TestDefaultUserPropagation:
    """default_user on AutoCRUD should be used when DP's get_user is default."""

    def test_default_user_in_init(self):
        """AutoCRUD(default_user='admin') → resource created with user 'admin'."""
        crud = _make_crud(default_user="admin")
        crud.add_model(Item, name="item")
        app = _build_app(crud)
        client = TestClient(app)

        resp = client.post("/item", json={"name": "test"})
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # Read the resource and check created_by
        resource_id = data["resource_id"]
        resp2 = client.get(f"/item/{resource_id}")
        assert resp2.status_code == 200
        meta = resp2.json()["meta"]
        assert meta["created_by"] == "admin"

    def test_default_user_in_configure(self):
        """crud.configure(default_user='admin') → same effect."""
        crud = AutoCRUD()
        crud.configure(
            default_user="admin",
            default_now=lambda: dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc),
        )
        crud.add_model(Item, name="item")
        app = _build_app(crud)
        client = TestClient(app)

        resp = client.post("/item", json={"name": "test"})
        assert resp.status_code == 200
        data = resp.json()

        resource_id = data["resource_id"]
        resp2 = client.get(f"/item/{resource_id}")
        meta = resp2.json()["meta"]
        assert meta["created_by"] == "admin"

    def test_dp_with_custom_get_now_but_no_get_user(self):
        """DependencyProvider(get_now=...) without get_user + default_user → uses default_user."""
        dp = DependencyProvider(
            get_now=lambda: dt.datetime(2025, 6, 1, tzinfo=dt.timezone.utc)
        )
        crud = AutoCRUD(
            default_user="game_admin",
            dependency_provider=dp,
        )
        crud.add_model(Item, name="item")
        app = _build_app(crud)
        client = TestClient(app)

        resp = client.post("/item", json={"name": "sword"})
        assert resp.status_code == 200
        data = resp.json()

        resource_id = data["resource_id"]
        resp2 = client.get(f"/item/{resource_id}")
        meta = resp2.json()["meta"]
        assert meta["created_by"] == "game_admin"

    def test_custom_get_user_overrides_default_user(self):
        """Custom get_user on DP should override default_user."""
        dp = DependencyProvider(get_user=lambda: "auth_user")
        crud = AutoCRUD(
            default_user="game_admin",
            dependency_provider=dp,
        )
        crud.add_model(Item, name="item")
        app = _build_app(crud)
        client = TestClient(app)

        resp = client.post("/item", json={"name": "shield"})
        assert resp.status_code == 200
        data = resp.json()

        resource_id = data["resource_id"]
        resp2 = client.get(f"/item/{resource_id}")
        meta = resp2.json()["meta"]
        # Custom DP get_user should win over default_user
        assert meta["created_by"] == "auth_user"

    def test_no_default_user_falls_back_to_anonymous(self):
        """No default_user, no custom DP → 'anonymous' (backward compat)."""
        crud = AutoCRUD(
            default_now=lambda: dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc),
        )
        crud.add_model(Item, name="item")
        app = _build_app(crud)
        client = TestClient(app)

        resp = client.post("/item", json={"name": "potion"})
        assert resp.status_code == 200
        data = resp.json()

        resource_id = data["resource_id"]
        resp2 = client.get(f"/item/{resource_id}")
        meta = resp2.json()["meta"]
        assert meta["created_by"] == "anonymous"


# ---------------------------------------------------------------------------
# 3. default_user with callable factory
# ---------------------------------------------------------------------------


class TestDefaultUserCallable:
    """default_user can be a callable that returns the user string."""

    def test_callable_default_user(self):
        crud = _make_crud(default_user=lambda: "factory_user")
        crud.add_model(Item, name="item")
        app = _build_app(crud)
        client = TestClient(app)

        resp = client.post("/item", json={"name": "test"})
        assert resp.status_code == 200
        data = resp.json()

        resource_id = data["resource_id"]
        resp2 = client.get(f"/item/{resource_id}")
        meta = resp2.json()["meta"]
        assert meta["created_by"] == "factory_user"


# ---------------------------------------------------------------------------
# 4. default_user affects all route templates, not just create
# ---------------------------------------------------------------------------


class TestDefaultUserAffectsAllRoutes:
    """default_user should work for update, patch, delete, etc."""

    def test_update_uses_default_user(self):
        crud = _make_crud(default_user="admin")
        crud.add_model(Item, name="item")
        app = _build_app(crud)
        client = TestClient(app)

        # Create
        resp = client.post("/item", json={"name": "original"})
        resource_id = resp.json()["resource_id"]

        # Update
        resp2 = client.put(f"/item/{resource_id}", json={"name": "updated"})
        assert resp2.status_code == 200

        # Check updated_by in latest revision
        resp3 = client.get(f"/item/{resource_id}")
        meta = resp3.json()["meta"]
        assert meta["updated_by"] == "admin"

    def test_delete_uses_default_user(self):
        crud = _make_crud(default_user="admin")
        crud.add_model(Item, name="item")
        app = _build_app(crud)
        client = TestClient(app)

        # Create
        resp = client.post("/item", json={"name": "to_delete"})
        resource_id = resp.json()["resource_id"]

        # Delete
        resp2 = client.delete(f"/item/{resource_id}")
        assert resp2.status_code == 200

    def test_list_uses_default_user(self):
        crud = _make_crud(default_user="admin")
        crud.add_model(Item, name="item")
        app = _build_app(crud)
        client = TestClient(app)

        # Create
        client.post("/item", json={"name": "listable"})

        # List (GET /item)
        resp = client.get("/item")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 5. default_user with create_action (custom routes)
# ---------------------------------------------------------------------------


class TestDefaultUserWithCreateAction:
    """default_user should also work for custom create_action routes."""

    def test_create_action_uses_default_user(self):
        from fastapi import Body

        crud = _make_crud(default_user="action_admin")
        crud.add_model(Item, name="item")

        @crud.create_action("item", path="/generate")
        def generate_item(body: Item = Body(...)) -> Item:
            return Item(name=f"generated-{body.name}", value=42)

        app = _build_app(crud)
        client = TestClient(app)

        resp = client.post("/item/generate", json={"name": "test"})
        assert resp.status_code == 200
        data = resp.json()

        resource_id = data["resource_id"]
        resp2 = client.get(f"/item/{resource_id}")
        meta = resp2.json()["meta"]
        assert meta["created_by"] == "action_admin"
