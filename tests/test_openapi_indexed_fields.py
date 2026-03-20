"""Tests for x-autocrud-indexed-fields OpenAPI extension injection."""

import pytest
from fastapi import FastAPI
from msgspec import Struct

from autocrud import AutoCRUD, Schema

# ---------------------------------------------------------------------------
# Test models
# ---------------------------------------------------------------------------


class Hero(Struct):
    name: str
    level: int
    hp: float
    description: str | None = None


class Weapon(Struct):
    name: str
    damage: int


class NoIndexModel(Struct):
    title: str
    content: str


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app_with_indexed_fields():
    """Create an app with models that have indexed_fields configured."""
    app = FastAPI(title="Test Indexed Fields")
    crud = AutoCRUD()
    crud.add_model(
        Schema(Hero, "v1"),
        indexed_fields=[("name", str), ("level", int)],
    )
    crud.add_model(
        Schema(Weapon, "v1"),
        indexed_fields=[("name", str)],
    )
    crud.add_model(Schema(NoIndexModel, "v1"))
    crud.apply(app)
    crud.openapi(app)
    return app


@pytest.fixture()
def app_no_indexed_fields():
    """Create an app where no models have indexed_fields."""
    app = FastAPI(title="Test No Indexed")
    crud = AutoCRUD()
    crud.add_model(Schema(Hero, "v1"))
    crud.add_model(Schema(Weapon, "v1"))
    crud.apply(app)
    crud.openapi(app)
    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestInjectIndexedFields:
    """Tests for _inject_indexed_fields OpenAPI extension."""

    def test_indexed_fields_present_in_schema(self, app_with_indexed_fields):
        """Extension key is present when at least one model has indexed_fields."""
        schema = app_with_indexed_fields.openapi_schema
        assert "x-autocrud-indexed-fields" in schema

    def test_indexed_fields_mapping_content(self, app_with_indexed_fields):
        """Mapping contains correct field paths for each resource."""
        schema = app_with_indexed_fields.openapi_schema
        mapping = schema["x-autocrud-indexed-fields"]

        assert "hero" in mapping
        assert sorted(mapping["hero"]) == ["level", "name"]

        assert "weapon" in mapping
        assert mapping["weapon"] == ["name"]

    def test_resource_without_indexed_fields_excluded(self, app_with_indexed_fields):
        """Resources with no indexed_fields are NOT in the mapping."""
        schema = app_with_indexed_fields.openapi_schema
        mapping = schema["x-autocrud-indexed-fields"]
        assert "no_index_model" not in mapping

    def test_no_extension_when_no_indexed_fields(self, app_no_indexed_fields):
        """Extension key is absent when no models have indexed_fields."""
        schema = app_no_indexed_fields.openapi_schema
        assert "x-autocrud-indexed-fields" not in schema

    def test_mapping_values_are_string_lists(self, app_with_indexed_fields):
        """Each value in the mapping is a list of strings (field paths)."""
        schema = app_with_indexed_fields.openapi_schema
        mapping = schema["x-autocrud-indexed-fields"]
        for resource_name, fields in mapping.items():
            assert isinstance(fields, list), f"{resource_name} value is not a list"
            for f in fields:
                assert isinstance(f, str), f"{resource_name} contains non-string: {f}"
