"""Tests for OpenAPI schema $ref consistency.

Covers:
- ``_sanitize_schema_names`` rewrites discriminator mapping values that
  contain dotted schema names.
- ``_resolve_missing_schema_refs`` adds aliases for $ref targets that point
  to simple names when only module-qualified versions exist in components.
- End-to-end: all $ref pointers resolve after openapi() post-processing.
- ``x-display-name-field`` survives module-qualified name dedup.
"""

import datetime as dt
import json
import re
from typing import Annotated

import pytest
from fastapi import FastAPI, UploadFile
from msgspec import Struct

from specstar import struct_to_pydantic
from specstar.crud.core import SpecStar
from specstar.message_queue.simple import SimpleMessageQueueFactory
from specstar.types import DisplayName

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


class SkillWithDN(Struct):
    """Skill with a DisplayName annotation + union field.

    Used to test that x-display-name-field survives module-qualified
    name dedup caused by struct_to_pydantic round-trip.
    """

    skname: Annotated[str, DisplayName()]
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


def _make_crud(**kwargs) -> SpecStar:
    return SpecStar(
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
# Test: schema-name sanitisation surfaces in the published OpenAPI spec
# ===================================================================


def _walk(obj):
    """Yield every nested dict/list/scalar so callers can scan a JSON tree."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


class TestPublishedSpecHasNoDottedSchemaNames:
    """Build a real SpecStar app whose models include a tagged-union (which
    forces FastAPI to emit ``discriminator.mapping``) and assert the
    post-processed OpenAPI spec contains no dotted schema names anywhere —
    component keys, ``$ref`` values, or ``discriminator.mapping`` values."""

    def _build_spec(self) -> dict:
        spec = _make_crud()
        spec.configure(model_naming="kebab")
        spec.add_model(Skill)
        app = FastAPI()
        spec.apply(app)
        spec.openapi(app)
        return app.openapi_schema  # ty:ignore[invalid-return-type]

    def test_no_dots_in_component_keys(self):
        spec = self._build_spec()
        keys = list(spec["components"]["schemas"].keys())
        dotted = [k for k in keys if "." in k]
        assert dotted == [], f"dotted component keys: {dotted}"

    def test_no_dots_in_any_ref(self):
        spec = self._build_spec()
        refs = _collect_all_refs(spec)
        dotted = [r for r in refs if "." in r]
        assert dotted == [], f"dotted $ref targets: {dotted}"

    def test_no_dots_in_discriminator_mapping_values(self):
        spec = self._build_spec()
        bad: list[str] = []
        for node in _walk(spec):
            if not isinstance(node, dict):
                continue
            mapping = (
                node.get("discriminator", {}).get("mapping")
                if "discriminator" in node
                else None
            )
            if not mapping:
                continue
            for key, value in mapping.items():
                if isinstance(value, str) and "." in value:
                    bad.append(f"{key}={value}")
        assert bad == [], f"dotted discriminator.mapping values: {bad}"


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
          ``specstar_resource_manager_pydantic_converter_Skill`` (produced
          when ``msgspec`` disambiguates two types with the same ``__name__``
          but different ``__module__``).
        """
        return {
            "openapi": "3.1.0",
            "info": {"title": "Test", "version": "0.1.0"},
            "paths": {
                "/v1/specstar/skill": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Skill"}
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
                    "specstar_resource_manager_pydantic_converter_Skill": {
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
        from specstar.crud.core import SpecStar

        SpecStar._resolve_missing_schema_refs(schema_with_missing_ref)
        components = schema_with_missing_ref["components"]["schemas"]
        assert "Skill" in components, (
            f"'Skill' not added. Available: {sorted(components.keys())}"
        )

    def test_prefers_main_module_variant(self, schema_with_missing_ref):
        """When multiple module-prefixed candidates exist, prefer the one
        from ``__main__`` (the user's original type)."""
        from specstar.crud.core import SpecStar

        SpecStar._resolve_missing_schema_refs(schema_with_missing_ref)
        components = schema_with_missing_ref["components"]["schemas"]
        # The alias should point to the __main__ variant's content
        assert components["Skill"]["properties"]["detail"].get("anyOf") is not None, (
            "Should use __main___Skill which has anyOf, not the pydantic_converter variant"
        )

    def test_no_change_when_all_refs_present(self):
        """If all $refs already resolve, no changes are made."""
        from specstar.crud.core import SpecStar

        schema = {
            "paths": {
                "/test": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Foo"}
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
        SpecStar._resolve_missing_schema_refs(schema)
        assert set(schema["components"]["schemas"].keys()) == original_keys

    def test_nested_refs_in_responses_also_resolved(self):
        """$ref pointers in response schemas should also be resolved."""
        from specstar.crud.core import SpecStar

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
        SpecStar._resolve_missing_schema_refs(schema)
        assert "Item" in schema["components"]["schemas"]

    def test_ref_inside_components_also_resolved(self):
        """$ref pointers within component schemas themselves (e.g. nested
        types) should also be resolved."""
        from specstar.crud.core import SpecStar

        schema = {
            "paths": {},
            "components": {
                "schemas": {
                    "Wrapper": {
                        "type": "object",
                        "properties": {"child": {"$ref": "#/components/schemas/Child"}},
                    },
                    "some_module_Child": {
                        "type": "object",
                        "properties": {"value": {"type": "string"}},
                    },
                }
            },
        }
        SpecStar._resolve_missing_schema_refs(schema)
        assert "Child" in schema["components"]["schemas"]


# ===================================================================
# Test: end-to-end async create action with struct_to_pydantic
# ===================================================================


class TestAsyncCreateActionPydanticSchemaRefs:
    """When Skill is registered as a resource AND an async create action on
    another resource uses struct_to_pydantic(Skill) as a param, the
    pydantic_to_struct round-trip creates a second Skill type from the
    ``pydantic_converter`` module.  All refs must resolve after openapi()."""

    def _build_app(self) -> tuple[SpecStar, FastAPI]:
        spec = _make_crud()
        spec.configure(model_naming="kebab")
        spec.add_model(Skill)
        spec.add_model(Article)

        @spec.create_action("article", async_mode="job")
        def generate_article(skill: SkillPydantic):  # type: ignore[valid-type]  # ty:ignore[invalid-type-form]
            return Article(title=skill.name, content="generated")

        app = FastAPI()
        spec.apply(app)
        spec.openapi(app)
        return spec, app

    def test_all_refs_resolve(self):
        """Every $ref pointer in the spec must point to an existing component."""
        _, app = self._build_app()
        _assert_all_refs_resolve(app.openapi_schema)  # ty:ignore[invalid-argument-type]

    def test_no_dots_in_schema_names(self):
        """Schema names must not contain dots (breaks code generators)."""
        _, app = self._build_app()
        schema_names = list(app.openapi_schema["components"]["schemas"].keys())  # ty:ignore[not-subscriptable]
        dotted = [n for n in schema_names if "." in n]
        assert dotted == [], f"Schema names with dots: {dotted}"


# ===================================================================
# Test: struct with union field — no name conflict
# ===================================================================


class TestNoConflictWithoutPydanticRoundTrip:
    """When there's no pydantic round-trip, Skill directly registered should
    produce a clean spec with all refs resolvable."""

    def test_direct_skill_registration_refs_resolve(self):
        spec = _make_crud()
        spec.configure(model_naming="kebab")
        spec.add_model(Skill)
        app = FastAPI()
        spec.apply(app)
        spec.openapi(app)
        _assert_all_refs_resolve(app.openapi_schema)  # ty:ignore[invalid-argument-type]


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
        from specstar.crud.core import SpecStar

        schema = {
            "components": {
                "schemas": {
                    "Body_action": {
                        "properties": {
                            "f": {
                                "$defs": {
                                    "ActiveSkillData": {
                                        "type": "object",
                                        "properties": {"damage": {"type": "integer"}},
                                    }
                                },
                                "properties": {
                                    "detail": {"$ref": "#/$defs/ActiveSkillData"}
                                },
                                "type": "object",
                            }
                        },
                        "type": "object",
                    }
                }
            }
        }
        SpecStar._promote_defs_to_components(schema)
        components = schema["components"]["schemas"]
        assert "ActiveSkillData" in components
        assert components["ActiveSkillData"]["type"] == "object"

    def test_refs_rewritten_to_components_path(self):
        """$ref: '#/$defs/X' should become '#/components/schemas/X'."""
        from specstar.crud.core import SpecStar

        schema = {
            "components": {
                "schemas": {
                    "Body_action": {
                        "properties": {
                            "f": {
                                "$defs": {
                                    "Foo": {"type": "object", "properties": {}},
                                },
                                "properties": {"x": {"$ref": "#/$defs/Foo"}},
                                "type": "object",
                            }
                        },
                        "type": "object",
                    }
                }
            }
        }
        SpecStar._promote_defs_to_components(schema)
        ref_val = schema["components"]["schemas"]["Body_action"]["properties"]["f"][
            "properties"
        ]["x"]["$ref"]
        assert ref_val == "#/components/schemas/Foo"

    def test_defs_key_removed_after_promotion(self):
        """The inline $defs key should be removed after promotion."""
        from specstar.crud.core import SpecStar

        schema = {
            "components": {
                "schemas": {
                    "Body_action": {
                        "properties": {
                            "f": {
                                "$defs": {
                                    "Bar": {"type": "object", "properties": {}},
                                },
                                "properties": {"y": {"$ref": "#/$defs/Bar"}},
                                "type": "object",
                            }
                        },
                        "type": "object",
                    }
                }
            }
        }
        SpecStar._promote_defs_to_components(schema)
        assert (
            "$defs"
            not in schema["components"]["schemas"]["Body_action"]["properties"]["f"]
        )

    def test_discriminator_mapping_also_rewritten(self):
        """discriminator.mapping values using #/$defs/X are also rewritten."""
        from specstar.crud.core import SpecStar

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
        SpecStar._promote_defs_to_components(schema)
        mapping = schema["components"]["schemas"]["Body_action"]["properties"]["f"][
            "properties"
        ]["pet"]["discriminator"]["mapping"]
        for key, val in mapping.items():
            assert val.startswith("#/components/schemas/"), f"mapping {key}={val}"

    def test_no_change_when_no_defs(self):
        """No crash when there are no $defs."""
        from specstar.crud.core import SpecStar

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
        SpecStar._promote_defs_to_components(schema)
        assert json.dumps(schema) == original

    def test_collision_avoidance(self):
        """If a promoted name already exists in components, it should not be
        overwritten."""
        from specstar.crud.core import SpecStar

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
                                "properties": {"x": {"$ref": "#/$defs/Existing"}},
                                "type": "object",
                            }
                        },
                        "type": "object",
                    },
                }
            }
        }
        SpecStar._promote_defs_to_components(schema)
        # Original should not be overwritten
        assert "original" in schema["components"]["schemas"]["Existing"]["properties"]


# ===================================================================
# Test: x-display-name-field survives module-qualified name dedup
# ===================================================================

# Module-level Pydantic model from SkillWithDN — triggers module-qualified
# name conflict just like struct_to_pydantic(Skill) in the real-world case.
SkillWithDNPydantic = struct_to_pydantic(SkillWithDN)


class TestDisplayNameFieldSurvivesDedup:
    """When a Struct has ``DisplayName()`` AND a ``struct_to_pydantic()``
    round-trip creates a second type with the same ``__name__`` but different
    ``__module__``, ``_inject_ref_metadata`` fails to inject
    ``x-display-name-field`` because the simple name doesn't exist in
    components yet — only the module-qualified variant does.

    ``_resolve_missing_schema_refs`` later creates the simple-name alias via
    ``.copy()``, but the copy has no metadata because the source never
    received it either (``get_type_name()`` returns the simple name which
    didn't exist in components at injection time).

    This is an end-to-end regression test ensuring the generated OpenAPI spec
    includes ``x-display-name-field`` even when name collisions are present.
    """

    def _build_app(self) -> tuple[SpecStar, FastAPI]:
        spec = _make_crud()
        spec.configure(model_naming="kebab")
        spec.add_model(SkillWithDN, name="skill-dn")
        spec.add_model(Article)

        @spec.create_action("article", async_mode="job")
        def gen_article(
            attachment: UploadFile,
            skill: SkillWithDNPydantic,  # type: ignore[valid-type]  # ty:ignore[invalid-type-form]
        ):
            return Article(title=skill.skname, content="generated")

        app = FastAPI()
        spec.apply(app)
        spec.openapi(app)
        return spec, app

    def test_display_name_field_present(self):
        """``x-display-name-field`` must be set on the SkillWithDN
        component even when a struct_to_pydantic duplicate exists."""
        _, app = self._build_app()
        components = app.openapi_schema["components"]["schemas"]  # ty:ignore[not-subscriptable]
        comp = components.get("SkillWithDN")
        assert comp is not None, (
            f"SkillWithDN not in components. Available: {sorted(components.keys())}"
        )
        assert comp.get("x-display-name-field") == "skname", (
            f"Expected x-display-name-field='skname', got {comp.get('x-display-name-field')!r}"
        )

    def test_all_refs_still_resolve(self):
        """Ensure the fix doesn't break $ref resolution."""
        _, app = self._build_app()
        _assert_all_refs_resolve(app.openapi_schema)  # ty:ignore[invalid-argument-type]
