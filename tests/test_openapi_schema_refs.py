"""Tests for OpenAPI schema $ref consistency.

Covers:
- ``_sanitize_schema_names`` rewrites discriminator mapping values that
  contain dotted schema names.
- ``_resolve_missing_schema_refs`` adds aliases for $ref targets that point
  to simple names when only module-qualified versions exist in components.
- End-to-end: all $ref pointers resolve after openapi() post-processing.
"""

import datetime as dt
import json
import re

import pytest
from fastapi import FastAPI
from msgspec import Struct

from autocrud import struct_to_pydantic
from autocrud.crud.core import AutoCRUD
from autocrud.crud.route_templates.basic import _sanitize_schema_names
from autocrud.message_queue.simple import SimpleMessageQueueFactory

# ---------------------------------------------------------------------------
# Test Models — Skill with tagged-union detail field
# ---------------------------------------------------------------------------


class ActiveDetail(Struct, tag="active", tag_field="kind"):
    mp_cost: int = 0
    damage: int = 0


class PassiveDetail(Struct, tag="passive", tag_field="kind"):
    buff_pct: int = 0


class UltimateDetail(Struct, tag="ultimate", tag_field="kind"):
    mp_cost: int = 0
    damage: int = 0
    aoe: bool = False


class Skill(Struct):
    """Skill with a union field to trigger sub-schema generation."""

    name: str
    detail: ActiveDetail | PassiveDetail | UltimateDetail
    description: str = ""


class Article(Struct):
    """Simple resource used as parent for the create action."""

    title: str
    content: str


# Module-level Pydantic model created from Skill — must be at module level so
# Pydantic can resolve type annotations in function signatures.
SkillPydantic = struct_to_pydantic(Skill)


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


def _collect_all_refs(obj: dict | list | str) -> list[str]:
    """Extract all $ref target names from a JSON-like structure."""
    text = json.dumps(obj)
    return re.findall(r'"\$ref":\s*"#/components/schemas/([^"]+)"', text)


def _assert_all_refs_resolve(openapi_schema: dict) -> None:
    """Assert every $ref in the spec resolves to an existing component."""
    components = openapi_schema["components"]["schemas"]
    refs = _collect_all_refs(openapi_schema)
    missing = [r for r in set(refs) if r not in components]
    assert missing == [], (
        f"Dangling $ref pointers found: {missing}. "
        f"Available schemas: {sorted(components.keys())}"
    )


# ===================================================================
# Test: _sanitize_schema_names rewrites discriminator mapping values
# ===================================================================


class TestSanitizeSchemaDiscriminatorMapping:
    """``_sanitize_schema_names`` must also rewrite ``discriminator.mapping``
    values that contain dotted ``$ref`` paths."""

    def test_discriminator_mapping_values_rewritten(self):
        """Mapping values like ``#/components/schemas/mod.Type`` must be
        sanitised to ``#/components/schemas/mod_Type``."""
        schemas = [
            {
                "anyOf": [
                    {"$ref": "#/components/schemas/__main__.Cat"},
                    {"$ref": "#/components/schemas/__main__.Dog"},
                ],
                "discriminator": {
                    "propertyName": "type",
                    "mapping": {
                        "Cat": "#/components/schemas/__main__.Cat",
                        "Dog": "#/components/schemas/__main__.Dog",
                    },
                },
            }
        ]
        components = {
            "__main__.Cat": {
                "title": "Cat",
                "type": "object",
                "properties": {
                    "type": {"enum": ["Cat"]},
                    "name": {"type": "string"},
                },
            },
            "__main__.Dog": {
                "title": "Dog",
                "type": "object",
                "properties": {
                    "type": {"enum": ["Dog"]},
                    "breed": {"type": "string"},
                },
            },
        }

        new_schemas, new_components = _sanitize_schema_names(schemas, components)

        # Component keys should be sanitised
        assert "__main___Cat" in new_components
        assert "__main___Dog" in new_components
        assert "__main__.Cat" not in new_components
        assert "__main__.Dog" not in new_components

        # $ref values should be sanitised
        schema = new_schemas[0]
        for item in schema["anyOf"]:
            assert "." not in item["$ref"], f"$ref not sanitised: {item['$ref']}"

        # discriminator.mapping values should also be sanitised
        mapping = schema["discriminator"]["mapping"]
        for key, value in mapping.items():
            assert "." not in value, (
                f"Discriminator mapping value not sanitised: {key}={value}"
            )

    def test_discriminator_mapping_absent_is_harmless(self):
        """No crash when discriminator has no mapping key."""
        schemas = [{"$ref": "#/components/schemas/X"}]
        components = {"X": {"title": "X", "type": "object"}}
        new_schemas, new_components = _sanitize_schema_names(schemas, components)
        assert "X" in new_components


# ===================================================================
# Test: _resolve_missing_schema_refs adds aliases for dangling $refs
# ===================================================================


class TestResolveMissingSchemaRefs:
    """``_resolve_missing_schema_refs`` (new utility) scans the full OpenAPI
    schema, identifies ``$ref`` targets that are missing from components, and
    creates alias entries by finding module-prefixed matches."""

    @pytest.fixture()
    def schema_with_missing_ref(self) -> dict:
        """Simulates the real bug:

        * Route requestBody ``$ref`` points to ``Skill`` (simple name,
          generated by per-route ``jsonschema_to_json_schema_extra``).
        * ``components.schemas`` only has ``__main___Skill`` and
          ``autocrud_resource_manager_pydantic_converter_Skill`` (produced
          when ``msgspec`` disambiguates two types with the same ``__name__``
          but different ``__module__``).
        """
        return {
            "openapi": "3.1.0",
            "info": {"title": "Test", "version": "0.1.0"},
            "paths": {
                "/v1/autocrud/skill": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/Skill"
                                    }
                                }
                            }
                        },
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
            "components": {
                "schemas": {
                    "__main___Skill": {
                        "title": "Skill",
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "detail": {
                                "anyOf": [
                                    {
                                        "$ref": "#/components/schemas/__main___ActiveDetail"
                                    },
                                    {
                                        "$ref": "#/components/schemas/__main___PassiveDetail"
                                    },
                                ]
                            },
                        },
                        "required": ["name", "detail"],
                    },
                    "autocrud_resource_manager_pydantic_converter_Skill": {
                        "title": "Skill",
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "detail": {"type": "object"},
                        },
                        "required": ["name", "detail"],
                    },
                    "__main___ActiveDetail": {
                        "title": "ActiveDetail",
                        "type": "object",
                        "properties": {"mp_cost": {"type": "integer"}},
                    },
                    "__main___PassiveDetail": {
                        "title": "PassiveDetail",
                        "type": "object",
                        "properties": {"buff_pct": {"type": "integer"}},
                    },
                }
            },
        }

    def test_missing_skill_ref_resolved(self, schema_with_missing_ref):
        """After resolution, ``Skill`` must exist in components."""
        from autocrud.crud.core import AutoCRUD

        AutoCRUD._resolve_missing_schema_refs(schema_with_missing_ref)
        components = schema_with_missing_ref["components"]["schemas"]
        assert "Skill" in components, (
            f"'Skill' not added. Available: {sorted(components.keys())}"
        )

    def test_prefers_main_module_variant(self, schema_with_missing_ref):
        """When multiple module-prefixed candidates exist, prefer the one
        from ``__main__`` (the user's original type)."""
        from autocrud.crud.core import AutoCRUD

        AutoCRUD._resolve_missing_schema_refs(schema_with_missing_ref)
        components = schema_with_missing_ref["components"]["schemas"]
        # The alias should point to the __main__ variant's content
        assert components["Skill"]["properties"]["detail"].get("anyOf") is not None, (
            "Should use __main___Skill which has anyOf, not the pydantic_converter variant"
        )

    def test_no_change_when_all_refs_present(self):
        """If all $refs already resolve, no changes are made."""
        from autocrud.crud.core import AutoCRUD

        schema = {
            "paths": {
                "/test": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "$ref": "#/components/schemas/Foo"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "components": {
                "schemas": {
                    "Foo": {"type": "object", "properties": {"x": {"type": "string"}}}
                }
            },
        }
        original_keys = set(schema["components"]["schemas"].keys())
        AutoCRUD._resolve_missing_schema_refs(schema)
        assert set(schema["components"]["schemas"].keys()) == original_keys

    def test_nested_refs_in_responses_also_resolved(self):
        """$ref pointers in response schemas should also be resolved."""
        from autocrud.crud.core import AutoCRUD

        schema = {
            "paths": {
                "/items": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "array",
                                            "items": {
                                                "$ref": "#/components/schemas/Item"
                                            },
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "components": {
                "schemas": {
                    "mymodule_Item": {
                        "title": "Item",
                        "type": "object",
                        "properties": {"id": {"type": "integer"}},
                    }
                }
            },
        }
        AutoCRUD._resolve_missing_schema_refs(schema)
        assert "Item" in schema["components"]["schemas"]

    def test_ref_inside_components_also_resolved(self):
        """$ref pointers within component schemas themselves (e.g. nested
        types) should also be resolved."""
        from autocrud.crud.core import AutoCRUD

        schema = {
            "paths": {},
            "components": {
                "schemas": {
                    "Wrapper": {
                        "type": "object",
                        "properties": {
                            "child": {"$ref": "#/components/schemas/Child"}
                        },
                    },
                    "some_module_Child": {
                        "type": "object",
                        "properties": {"value": {"type": "string"}},
                    },
                }
            },
        }
        AutoCRUD._resolve_missing_schema_refs(schema)
        assert "Child" in schema["components"]["schemas"]


# ===================================================================
# Test: end-to-end async create action with struct_to_pydantic
# ===================================================================


class TestAsyncCreateActionPydanticSchemaRefs:
    """When Skill is registered as a resource AND an async create action on
    another resource uses struct_to_pydantic(Skill) as a param, the
    pydantic_to_struct round-trip creates a second Skill type from the
    ``pydantic_converter`` module.  All refs must resolve after openapi()."""

    def _build_app(self) -> tuple[AutoCRUD, FastAPI]:
        crud = _make_crud()
        crud.configure(model_naming="kebab")
        crud.add_model(Skill)
        crud.add_model(Article)

        @crud.create_action("article", async_mode="job")
        def generate_article(skill: SkillPydantic):  # type: ignore[valid-type]
            return Article(title=skill.name, content="generated")

        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)
        return crud, app

    def test_all_refs_resolve(self):
        """Every $ref pointer in the spec must point to an existing component."""
        _, app = self._build_app()
        _assert_all_refs_resolve(app.openapi_schema)

    def test_no_dots_in_schema_names(self):
        """Schema names must not contain dots (breaks code generators)."""
        _, app = self._build_app()
        schema_names = list(app.openapi_schema["components"]["schemas"].keys())
        dotted = [n for n in schema_names if "." in n]
        assert dotted == [], f"Schema names with dots: {dotted}"


# ===================================================================
# Test: struct with union field — no name conflict
# ===================================================================


class TestNoConflictWithoutPydanticRoundTrip:
    """When there's no pydantic round-trip, Skill directly registered should
    produce a clean spec with all refs resolvable."""

    def test_direct_skill_registration_refs_resolve(self):
        crud = _make_crud()
        crud.configure(model_naming="kebab")
        crud.add_model(Skill)
        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)
        _assert_all_refs_resolve(app.openapi_schema)


# ===================================================================
# Test: _promote_defs_to_components hoists inline $defs
# ===================================================================


class TestPromoteDefsToComponents:
    """Pydantic models embedded in Body schemas may carry `$defs` at the
    property level with `$ref: "#/$defs/X"` pointing to the document root.
    ``_promote_defs_to_components`` must hoist these into
    ``#/components/schemas`` and rewrite refs."""

    def test_defs_promoted_to_components(self):
        """$defs entries should be moved to components/schemas."""
        from autocrud.crud.core import AutoCRUD

        schema = {
            "components": {
                "schemas": {
                    "Body_action": {
                        "properties": {
                            "f": {
                                "$defs": {
                                    "ActiveSkillData": {
                                        "type": "object",
                                        "properties": {
                                            "damage": {"type": "integer"}
                                        },
                                    }
                                },
                                "properties": {
                                    "detail": {
                                        "$ref": "#/$defs/ActiveSkillData"
                                    }
                                },
                                "type": "object",
                            }
                        },
                        "type": "object",
                    }
                }
            }
        }
        AutoCRUD._promote_defs_to_components(schema)
        components = schema["components"]["schemas"]
        assert "ActiveSkillData" in components
        assert components["ActiveSkillData"]["type"] == "object"

    def test_refs_rewritten_to_components_path(self):
        """$ref: '#/$defs/X' should become '#/components/schemas/X'."""
        from autocrud.crud.core import AutoCRUD

        schema = {
            "components": {
                "schemas": {
                    "Body_action": {
                        "properties": {
                            "f": {
                                "$defs": {
                                    "Foo": {"type": "object", "properties": {}},
                                },
                                "properties": {
                                    "x": {"$ref": "#/$defs/Foo"}
                                },
                                "type": "object",
                            }
                        },
                        "type": "object",
                    }
                }
            }
        }
        AutoCRUD._promote_defs_to_components(schema)
        ref_val = schema["components"]["schemas"]["Body_action"]["properties"]["f"][
            "properties"
        ]["x"]["$ref"]
        assert ref_val == "#/components/schemas/Foo"

    def test_defs_key_removed_after_promotion(self):
        """The inline $defs key should be removed after promotion."""
        from autocrud.crud.core import AutoCRUD

        schema = {
            "components": {
                "schemas": {
                    "Body_action": {
                        "properties": {
                            "f": {
                                "$defs": {
                                    "Bar": {"type": "object", "properties": {}},
                                },
                                "properties": {
                                    "y": {"$ref": "#/$defs/Bar"}
                                },
                                "type": "object",
                            }
                        },
                        "type": "object",
                    }
                }
            }
        }
        AutoCRUD._promote_defs_to_components(schema)
        assert "$defs" not in schema["components"]["schemas"]["Body_action"][
            "properties"
        ]["f"]

    def test_discriminator_mapping_also_rewritten(self):
        """discriminator.mapping values using #/$defs/X are also rewritten."""
        from autocrud.crud.core import AutoCRUD

        schema = {
            "components": {
                "schemas": {
                    "Body_action": {
                        "properties": {
                            "f": {
                                "$defs": {
                                    "Cat": {"type": "object", "properties": {}},
                                    "Dog": {"type": "object", "properties": {}},
                                },
                                "properties": {
                                    "pet": {
                                        "oneOf": [
                                            {"$ref": "#/$defs/Cat"},
                                            {"$ref": "#/$defs/Dog"},
                                        ],
                                        "discriminator": {
                                            "propertyName": "type",
                                            "mapping": {
                                                "cat": "#/$defs/Cat",
                                                "dog": "#/$defs/Dog",
                                            },
                                        },
                                    }
                                },
                                "type": "object",
                            }
                        },
                        "type": "object",
                    }
                }
            }
        }
        AutoCRUD._promote_defs_to_components(schema)
        mapping = schema["components"]["schemas"]["Body_action"]["properties"][
            "f"
        ]["properties"]["pet"]["discriminator"]["mapping"]
        for key, val in mapping.items():
            assert val.startswith("#/components/schemas/"), f"mapping {key}={val}"

    def test_no_change_when_no_defs(self):
        """No crash when there are no $defs."""
        from autocrud.crud.core import AutoCRUD

        schema = {
            "components": {
                "schemas": {
                    "Simple": {
                        "type": "object",
                        "properties": {"x": {"type": "string"}},
                    }
                }
            }
        }
        original = json.dumps(schema)
        AutoCRUD._promote_defs_to_components(schema)
        assert json.dumps(schema) == original

    def test_collision_avoidance(self):
        """If a promoted name already exists in components, it should not be
        overwritten."""
        from autocrud.crud.core import AutoCRUD

        schema = {
            "components": {
                "schemas": {
                    "Existing": {
                        "type": "object",
                        "properties": {"original": {"type": "string"}},
                    },
                    "Body_action": {
                        "properties": {
                            "f": {
                                "$defs": {
                                    "Existing": {
                                        "type": "object",
                                        "properties": {
                                            "duplicate": {"type": "integer"}
                                        },
                                    },
                                },
                                "properties": {
                                    "x": {"$ref": "#/$defs/Existing"}
                                },
                                "type": "object",
                            }
                        },
                        "type": "object",
                    },
                }
            }
        }
        AutoCRUD._promote_defs_to_components(schema)
        # Original should not be overwritten
        assert "original" in schema["components"]["schemas"]["Existing"]["properties"]
