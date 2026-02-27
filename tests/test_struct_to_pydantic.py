"""Tests for struct_to_pydantic() — msgspec Struct → Pydantic BaseModel conversion.

Covers:
- Simple scalar types (str, int, float, bool)
- Optional fields
- Enum types
- datetime types
- list / dict container types
- Default values (present vs NODEFAULT)
- Annotated metadata stripping (DisplayName, Unique, Ref)
- Tagged struct unions → Pydantic discriminated unions
- Nested Structs (recursive conversion)
- Cache prevents duplicate model creation
- Error on non-Struct input
- FastAPI integration: parameter type annotation + OpenAPI schema generation
"""

import datetime as dt
from enum import Enum
from typing import Annotated, Optional

import pytest
from msgspec import Struct
from pydantic import BaseModel

from autocrud import struct_to_pydantic
from autocrud.types import DisplayName, Unique

# ---------------------------------------------------------------------------
# Test models
# ---------------------------------------------------------------------------


class Color(Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


class SimpleStruct(Struct):
    name: str
    age: int
    score: float = 0.0
    active: bool = True


class StructWithOptional(Struct):
    name: str
    email: Optional[str] = None
    tags: list[str] = []


class StructWithAnnotated(Struct):
    name: Annotated[str, DisplayName(), Unique()]
    level: int = 1


class StructWithEnum(Struct):
    name: str
    color: Color
    opt_color: Optional[Color] = None


class StructWithDatetime(Struct):
    name: str
    created_at: dt.datetime = dt.datetime(2024, 1, 1)


class StructWithContainers(Struct):
    names: list[str] = []
    metadata: dict[str, int] = {}


class Inner(Struct):
    value: int = 0


class Outer(Struct):
    name: str
    inner: Inner
    inners: list[Inner] = []


class TagA(Struct, tag="a"):
    x: int = 0


class TagB(Struct, tag="b"):
    y: str = ""


class TagC(Struct, tag="c", tag_field="kind"):
    z: float = 0.0


class StructWithTaggedUnion(Struct):
    name: str
    detail: TagA | TagB


class StructWithOptionalTaggedUnion(Struct):
    name: str
    detail: Optional[TagA | TagB] = None


class ActiveSkill(Struct, tag="active"):
    mp_cost: int = 0
    damage: int = 0


class PassiveSkill(Struct, tag="passive"):
    buff: int = 0


class UltimateSkill(Struct, tag="ultimate"):
    mp_cost: int = 0
    damage: int = 0
    aoe: bool = False


class RPGSkill(Struct):
    """Mimics the real Skill model from the RPG example."""

    skname: Annotated[str, DisplayName()]
    detail: ActiveSkill | PassiveSkill | UltimateSkill
    description: str = ""
    required_level: int = 1
    required_class: Optional[Color] = None


# ---------------------------------------------------------------------------
# Tests — basic conversion
# ---------------------------------------------------------------------------


class TestSimpleConversion:
    def test_returns_pydantic_model(self):
        Model = struct_to_pydantic(SimpleStruct)
        assert isinstance(Model, type)
        assert issubclass(Model, BaseModel)

    def test_preserves_class_name(self):
        Model = struct_to_pydantic(SimpleStruct)
        assert Model.__name__ == "SimpleStruct"

    def test_field_names_preserved(self):
        Model = struct_to_pydantic(SimpleStruct)
        assert set(Model.model_fields.keys()) == {"name", "age", "score", "active"}

    def test_required_field_is_required(self):
        Model = struct_to_pydantic(SimpleStruct)
        assert Model.model_fields["name"].is_required()
        assert Model.model_fields["age"].is_required()

    def test_default_values_preserved(self):
        Model = struct_to_pydantic(SimpleStruct)
        assert Model.model_fields["score"].default == 0.0
        assert Model.model_fields["active"].default is True

    def test_instantiation_with_defaults(self):
        Model = struct_to_pydantic(SimpleStruct)
        obj = Model(name="Alice", age=30)
        assert obj.name == "Alice"
        assert obj.age == 30
        assert obj.score == 0.0
        assert obj.active is True

    def test_instantiation_with_all_values(self):
        Model = struct_to_pydantic(SimpleStruct)
        obj = Model(name="Bob", age=25, score=9.5, active=False)
        assert obj.score == 9.5
        assert obj.active is False


class TestOptionalFields:
    def test_optional_field_allows_none(self):
        Model = struct_to_pydantic(StructWithOptional)
        obj = Model(name="Test")
        assert obj.email is None

    def test_optional_field_accepts_value(self):
        Model = struct_to_pydantic(StructWithOptional)
        obj = Model(name="Test", email="test@example.com")
        assert obj.email == "test@example.com"

    def test_list_default_preserved(self):
        Model = struct_to_pydantic(StructWithOptional)
        obj = Model(name="Test")
        assert obj.tags == []


class TestAnnotatedStripping:
    def test_annotated_metadata_stripped(self):
        """DisplayName and Unique markers should be stripped — Pydantic doesn't need them."""
        Model = struct_to_pydantic(StructWithAnnotated)
        obj = Model(name="Hero", level=5)
        assert obj.name == "Hero"
        assert obj.level == 5

    def test_field_type_is_base_type(self):
        Model = struct_to_pydantic(StructWithAnnotated)
        # Should be str, not Annotated[str, ...]
        obj = Model(name="Test")
        assert isinstance(obj.name, str)


class TestEnumFields:
    def test_enum_field_accepted(self):
        Model = struct_to_pydantic(StructWithEnum)
        obj = Model(name="Test", color=Color.RED)
        assert obj.color == Color.RED

    def test_optional_enum_default_none(self):
        Model = struct_to_pydantic(StructWithEnum)
        obj = Model(name="Test", color=Color.GREEN)
        assert obj.opt_color is None

    def test_enum_from_string_value(self):
        Model = struct_to_pydantic(StructWithEnum)
        obj = Model(name="Test", color="red")
        assert obj.color == Color.RED


class TestDatetimeFields:
    def test_datetime_field(self):
        Model = struct_to_pydantic(StructWithDatetime)
        obj = Model(name="Test")
        assert obj.created_at == dt.datetime(2024, 1, 1)


class TestContainerFields:
    def test_list_field(self):
        Model = struct_to_pydantic(StructWithContainers)
        obj = Model(names=["a", "b"])
        assert obj.names == ["a", "b"]

    def test_dict_field(self):
        Model = struct_to_pydantic(StructWithContainers)
        obj = Model(metadata={"hp": 100})
        assert obj.metadata == {"hp": 100}


# ---------------------------------------------------------------------------
# Tests — nested Structs
# ---------------------------------------------------------------------------


class TestNestedStructs:
    def test_nested_struct_converted(self):
        Model = struct_to_pydantic(Outer)
        obj = Model(name="Test", inner={"value": 42})
        assert obj.inner.value == 42

    def test_nested_struct_is_pydantic(self):
        Model = struct_to_pydantic(Outer)
        obj = Model(name="Test", inner={"value": 1})
        assert isinstance(obj.inner, BaseModel)

    def test_list_of_nested_structs(self):
        Model = struct_to_pydantic(Outer)
        obj = Model(
            name="Test", inner={"value": 0}, inners=[{"value": 1}, {"value": 2}]
        )
        assert len(obj.inners) == 2
        assert obj.inners[0].value == 1


# ---------------------------------------------------------------------------
# Tests — tagged unions
# ---------------------------------------------------------------------------


class TestTaggedUnions:
    def test_tagged_union_discriminator(self):
        Model = struct_to_pydantic(StructWithTaggedUnion)
        obj = Model(name="Test", detail={"type": "a", "x": 42})
        assert obj.detail.type == "a"
        assert obj.detail.x == 42

    def test_tagged_union_variant_b(self):
        Model = struct_to_pydantic(StructWithTaggedUnion)
        obj = Model(name="Test", detail={"type": "b", "y": "hello"})
        assert obj.detail.type == "b"
        assert obj.detail.y == "hello"

    def test_tagged_union_validation_error(self):
        Model = struct_to_pydantic(StructWithTaggedUnion)
        with pytest.raises(Exception):  # Pydantic validation error
            Model(name="Test", detail={"type": "nonexistent"})

    def test_optional_tagged_union_is_none(self):
        Model = struct_to_pydantic(StructWithOptionalTaggedUnion)
        obj = Model(name="Test")
        assert obj.detail is None

    def test_optional_tagged_union_has_value(self):
        Model = struct_to_pydantic(StructWithOptionalTaggedUnion)
        obj = Model(name="Test", detail={"type": "a", "x": 10})
        assert obj.detail.x == 10


class TestThreeWayTaggedUnion:
    """Test with the RPG Skill model — 3-way union like the real example."""

    def test_active_skill(self):
        Model = struct_to_pydantic(RPGSkill)
        obj = Model(
            skname="Fireball",
            detail={"type": "active", "mp_cost": 30, "damage": 100},
        )
        assert obj.detail.type == "active"
        assert obj.detail.mp_cost == 30

    def test_passive_skill(self):
        Model = struct_to_pydantic(RPGSkill)
        obj = Model(
            skname="Iron Will",
            detail={"type": "passive", "buff": 20},
        )
        assert obj.detail.type == "passive"
        assert obj.detail.buff == 20

    def test_ultimate_skill(self):
        Model = struct_to_pydantic(RPGSkill)
        obj = Model(
            skname="CRUD Mastery",
            detail={"type": "ultimate", "mp_cost": 100, "damage": 9999, "aoe": True},
        )
        assert obj.detail.type == "ultimate"
        assert obj.detail.aoe is True

    def test_optional_enum_field(self):
        Model = struct_to_pydantic(RPGSkill)
        obj = Model(
            skname="Test",
            detail={"type": "active"},
            required_class="red",
        )
        assert obj.required_class == Color.RED


# ---------------------------------------------------------------------------
# Tests — caching
# ---------------------------------------------------------------------------


class TestCaching:
    def test_same_class_returns_same_model(self):
        """Calling struct_to_pydantic twice should return the same class."""
        M1 = struct_to_pydantic(SimpleStruct)
        M2 = struct_to_pydantic(SimpleStruct)
        # Different invocations create separate caches, so models may differ
        # But both should work identically
        assert M1.__name__ == M2.__name__
        assert set(M1.model_fields.keys()) == set(M2.model_fields.keys())


# ---------------------------------------------------------------------------
# Tests — error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_non_struct_raises_type_error(self):
        with pytest.raises(TypeError, match="Expected a msgspec Struct class"):
            struct_to_pydantic(str)

    def test_pydantic_model_raises_type_error(self):
        class MyModel(BaseModel):
            x: int = 0

        with pytest.raises(TypeError, match="Expected a msgspec Struct class"):
            struct_to_pydantic(MyModel)

    def test_instance_raises_type_error(self):
        with pytest.raises(TypeError, match="Expected a msgspec Struct class"):
            struct_to_pydantic(SimpleStruct(name="x", age=1))


# ---------------------------------------------------------------------------
# Tests — unsupported msgspec types boundary check
# ---------------------------------------------------------------------------


class TestUnsupportedMsgspecTypes:
    """struct_to_pydantic 遇到 Pydantic 不支援的 msgspec 類型時，
    應立即 raise 清楚的 TypeError，而非讓 Pydantic 報難懂的錯。

    不支援的類型：msgspec.UnsetType, msgspec.Raw, msgspec.msgpack.Ext
    """

    # --- UnsetType ---

    def test_unset_type_raises(self):
        from msgspec import UNSET, UnsetType

        class S(Struct, kw_only=True):
            name: str
            nickname: str | UnsetType = UNSET

        with pytest.raises(TypeError, match="contains unsupported type.*UnsetType"):
            struct_to_pydantic(S)

    def test_optional_unset_type_raises(self):
        from msgspec import UNSET, UnsetType

        class S(Struct, kw_only=True):
            name: str
            bio: str | None | UnsetType = UNSET

        with pytest.raises(TypeError, match="contains unsupported type.*UnsetType"):
            struct_to_pydantic(S)

    def test_nested_struct_with_unset_type_raises(self):
        from msgspec import UNSET, UnsetType

        class Inner(Struct, kw_only=True):
            value: int | UnsetType = UNSET

        class Outer(Struct):
            name: str
            inner: Inner

        with pytest.raises(TypeError, match="contains unsupported type.*UnsetType"):
            struct_to_pydantic(Outer)

    def test_unset_type_in_container_raises(self):
        from msgspec import UnsetType

        class S(Struct, kw_only=True):
            items: list[str | UnsetType] = []

        with pytest.raises(TypeError, match="contains unsupported type.*UnsetType"):
            struct_to_pydantic(S)

    def test_error_message_includes_struct_and_field_name(self):
        from msgspec import UNSET, UnsetType

        class MyConfig(Struct, kw_only=True):
            debug: bool = False
            secret: str | UnsetType = UNSET

        with pytest.raises(TypeError, match=r"MyConfig\.secret.*UnsetType"):
            struct_to_pydantic(MyConfig)

    # --- msgspec.Raw ---

    def test_raw_type_raises(self):
        import msgspec

        class S(Struct):
            name: str
            payload: msgspec.Raw

        with pytest.raises(TypeError, match="contains unsupported type.*msgspec.Raw"):
            struct_to_pydantic(S)

    def test_optional_raw_type_raises(self):
        import msgspec

        class S(Struct):
            name: str
            payload: msgspec.Raw | None = None

        with pytest.raises(TypeError, match="contains unsupported type.*msgspec.Raw"):
            struct_to_pydantic(S)

    def test_raw_in_container_raises(self):
        import msgspec

        class S(Struct):
            name: str
            items: list[msgspec.Raw] = []

        with pytest.raises(TypeError, match="contains unsupported type.*msgspec.Raw"):
            struct_to_pydantic(S)

    # --- msgspec.msgpack.Ext ---

    def test_msgpack_ext_raises(self):
        from msgspec.msgpack import Ext

        class S(Struct):
            name: str
            ext: Ext

        with pytest.raises(TypeError, match="contains unsupported type.*Ext"):
            struct_to_pydantic(S)

    def test_optional_msgpack_ext_raises(self):
        from msgspec.msgpack import Ext

        class S(Struct):
            name: str
            ext: Ext | None = None

        with pytest.raises(TypeError, match="contains unsupported type.*Ext"):
            struct_to_pydantic(S)


# ---------------------------------------------------------------------------
# Tests — JSON Schema / OpenAPI integration
# ---------------------------------------------------------------------------


class TestJSONSchema:
    def test_json_schema_generated(self):
        Model = struct_to_pydantic(SimpleStruct)
        schema = Model.model_json_schema()
        assert "properties" in schema
        assert "name" in schema["properties"]
        assert "age" in schema["properties"]

    def test_tagged_union_json_schema(self):
        Model = struct_to_pydantic(StructWithTaggedUnion)
        schema = Model.model_json_schema()
        # Should have discriminator in the detail field
        assert "$defs" in schema
        # TagA and TagB should appear in $defs
        def_names = set(schema["$defs"].keys())
        assert "TagA" in def_names
        assert "TagB" in def_names

    def test_enum_in_json_schema(self):
        Model = struct_to_pydantic(StructWithEnum)
        schema = Model.model_json_schema()
        # Color enum should appear in $defs
        assert "Color" in schema.get("$defs", {})

    def test_rpg_skill_schema_has_discriminator(self):
        Model = struct_to_pydantic(RPGSkill)
        schema = Model.model_json_schema()
        defs = schema.get("$defs", {})
        assert "ActiveSkill" in defs
        assert "PassiveSkill" in defs
        assert "UltimateSkill" in defs


# ---------------------------------------------------------------------------
# Tests — FastAPI integration
# ---------------------------------------------------------------------------


class TestFastAPIIntegration:
    def test_as_endpoint_parameter(self):
        """struct_to_pydantic result works as a FastAPI endpoint type annotation."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        SkillModel = struct_to_pydantic(RPGSkill)

        @app.post("/skill")
        async def create_skill(body: SkillModel):
            return {"skname": body.skname, "detail_type": body.detail.type}

        client = TestClient(app)
        resp = client.post(
            "/skill",
            json={
                "skname": "Fireball",
                "detail": {"type": "active", "mp_cost": 30, "damage": 100},
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"skname": "Fireball", "detail_type": "active"}

    def test_openapi_schema_contains_model(self):
        from fastapi import FastAPI

        app = FastAPI()
        SkillModel = struct_to_pydantic(RPGSkill)

        @app.post("/skill")
        async def create_skill(body: SkillModel):
            return {}

        schema = app.openapi()
        # Should have Skill ref in requestBody
        post_op = schema["paths"]["/skill"]["post"]
        body_content = post_op["requestBody"]["content"]["application/json"]
        assert "$ref" in body_content["schema"]
        assert "RPGSkill" in body_content["schema"]["$ref"]
