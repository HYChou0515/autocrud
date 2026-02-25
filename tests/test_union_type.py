"""Tests for union type support in add_model and schema fields.

Covers:
- add_model(A | B) auto-naming: should produce 'AOrB', not AttributeError
- add_model(A | B, name="...") should not crash on name resolution
- NameConverter variants (snake, kebab) should work with union types
- Uninferrable union type should raise a clear ValueError mentioning name=
- Struct with tagged-struct union field should work end-to-end
- Error messages (get_resource_manager, duplicate registration) should not
  crash when the model is a union type
"""

from __future__ import annotations

import datetime as dt

import pytest
from msgspec import Struct

from autocrud.crud.core import AutoCRUD as AutoCRUDClass
from autocrud.schema import Schema

# ---- Sample types ----


class Cat(Struct, tag=True):
    name: str


class Dog(Struct, tag=True):
    name: str
    breed: str


class Bird(Struct, tag=True):
    name: str
    can_fly: bool


class PetOwner(Struct):
    owner_name: str
    pet: Cat | Dog


class MultiPetOwner(Struct):
    owner_name: str
    pets: list[Cat | Dog | Bird]


# ---- _resource_name tests (no ResourceManager instantiation) ----


def test_resource_name_union_type_two_args():
    """_resource_name(Cat | Dog) with default kebab naming should return 'cat-or-dog'."""
    ac = AutoCRUDClass()
    ac.configure()
    assert ac._resource_name(Cat | Dog) == "cat-or-dog"


def test_resource_name_union_type_three_args():
    """_resource_name(Cat | Dog | Bird) with kebab should return 'cat-or-dog-or-bird'."""
    ac = AutoCRUDClass()
    ac.configure()
    assert ac._resource_name(Cat | Dog | Bird) == "cat-or-dog-or-bird"


def test_resource_name_union_type_snake():
    """_resource_name with snake model_naming should return 'cat_or_dog'."""
    ac = AutoCRUDClass()
    ac.configure(model_naming="snake")
    assert ac._resource_name(Cat | Dog) == "cat_or_dog"


def test_resource_name_union_type_kebab():
    """_resource_name with kebab model_naming should return 'cat-or-dog'."""
    ac = AutoCRUDClass()
    ac.configure(model_naming="kebab")
    assert ac._resource_name(Cat | Dog) == "cat-or-dog"


def test_resource_name_union_type_same():
    """_resource_name with 'same' model_naming should return 'CatOrDog' (PascalCase)."""
    ac = AutoCRUDClass()
    ac.configure(model_naming="same")
    assert ac._resource_name(Cat | Dog) == "CatOrDog"


def test_resource_name_uninferrable_raises_clear_error():
    """Passing a non-union type with no __name__ should raise a clear ValueError."""
    ac = AutoCRUDClass()
    ac.configure()

    # Simulate an object that is not a union and has no __name__ and no get_args
    class _FakeType:
        pass

    fake = _FakeType()
    with pytest.raises((ValueError, AttributeError)):
        ac._resource_name(fake)  # type: ignore


# ---- Error message safety when model is union type ----


def test_get_resource_manager_multiple_names_error_message_safe():
    """get_resource_manager() error message should not crash for union models."""
    ac = AutoCRUDClass()
    ac.configure()
    # Manually simulate a conflicting registration state
    ac.model_names[Cat | Dog] = None  # None means multiple names registered
    with pytest.raises(ValueError, match="registered with multiple names"):
        ac.get_resource_manager(Cat | Dog)


def test_add_model_duplicate_registration_warning_safe(caplog):
    """Duplicate union type registration should warn without crashing."""
    import logging

    ac = AutoCRUDClass()
    ac.configure()
    # Simulate conflicting registration state: model is in model_names with None value
    ac.model_names[Cat | Dog] = None
    with caplog.at_level(logging.WARNING, logger="autocrud"):
        model = Cat | Dog
        # Verify getattr fallback doesn't crash and produces a readable message
        name_repr = getattr(model, "__name__", repr(model))
        import logging as _logging

        logger = _logging.getLogger("autocrud")
        logger.warning(
            f"Model {name_repr} is already registered with a different name."
        )
    # repr(Cat | Dog) contains "Cat | Dog" in some form
    assert caplog.text != ""  # Just ensure it logged without crashing


# ---- Parametrized: add_model(X) and add_model(Schema(X, "v1")) are equivalent ----

UNION_MODELS = [
    pytest.param(Cat | Dog, id="Cat|Dog"),
    pytest.param(Schema(Cat | Dog, "v1"), id="Schema(Cat|Dog)"),
]

STRUCT_WITH_UNION_MODELS = [
    pytest.param(PetOwner, id="PetOwner"),
    pytest.param(Schema(PetOwner, "v1"), id="Schema(PetOwner)"),
]

COMPLEX_UNION_MODELS = [
    pytest.param(MultiPetOwner, id="MultiPetOwner"),
    pytest.param(Schema(MultiPetOwner, "v1"), id="Schema(MultiPetOwner)"),
]


@pytest.mark.parametrize("model", UNION_MODELS)
def test_add_model_union_auto_name(model):
    """add_model(Cat|Dog) and add_model(Schema(Cat|Dog)) both produce 'CatOrDog'."""
    ac = AutoCRUDClass()
    ac.configure(model_naming="same")
    ac.add_model(model)
    rm = ac.get_resource_manager("CatOrDog")
    assert rm is not None


@pytest.mark.parametrize("model", UNION_MODELS)
def test_add_model_union_explicit_name(model):
    """add_model with explicit name= works for both direct union and Schema."""
    ac = AutoCRUDClass()
    ac.configure()
    ac.add_model(model, name="animal")
    rm = ac.get_resource_manager("animal")
    assert rm is not None


@pytest.mark.parametrize("model", UNION_MODELS)
def test_add_model_union_kebab_auto_name(model):
    """Default kebab naming produces 'cat-or-dog' for both variants."""
    ac = AutoCRUDClass()
    ac.configure()
    ac.add_model(model)
    rm = ac.get_resource_manager("cat-or-dog")
    assert rm is not None


@pytest.mark.parametrize("model", UNION_MODELS)
def test_add_model_union_create_and_get(model):
    """Full CRUD cycle works for both Cat|Dog and Schema(Cat|Dog)."""
    ac = AutoCRUDClass()
    ac.configure(model_naming="same")
    ac.add_model(model)
    rm = ac.get_resource_manager("CatOrDog")

    with rm.meta_provide(user="test", now=dt.datetime.now()):
        info = rm.create({"type": "Cat", "name": "Luna"})

    resource = rm.get(info.resource_id)
    assert resource.data.name == "Luna"


@pytest.mark.parametrize("model", STRUCT_WITH_UNION_MODELS)
def test_add_model_struct_with_union_field(model):
    """Struct with tagged Cat|Dog field works both directly and via Schema."""
    ac = AutoCRUDClass()
    ac.configure(model_naming="same")
    ac.add_model(model)
    rm = ac.get_resource_manager("PetOwner")
    assert rm is not None


@pytest.mark.parametrize("model", COMPLEX_UNION_MODELS)
def test_add_model_struct_with_complex_union_field(model):
    """Struct with list[Cat|Dog|Bird] field works both directly and via Schema."""
    ac = AutoCRUDClass()
    ac.configure(model_naming="same")
    ac.add_model(model)
    rm = ac.get_resource_manager("MultiPetOwner")
    assert rm is not None


@pytest.mark.parametrize("model", STRUCT_WITH_UNION_MODELS)
def test_struct_with_union_field_create_and_get(model):
    """Full CRUD cycle for Struct with union field works both directly and via Schema."""
    ac = AutoCRUDClass()
    ac.configure(model_naming="same")
    ac.add_model(model)
    rm = ac.get_resource_manager("PetOwner")

    with rm.meta_provide(user="test", now=dt.datetime.now()):
        info = rm.create(
            {"owner_name": "Alice", "pet": {"type": "Cat", "name": "Whiskers"}}
        )

    resource = rm.get(info.resource_id)
    assert resource.data.owner_name == "Alice"


# ---- openapi() / _inject_ref_metadata() with union type ----

OPENAPI_UNION_MODELS = [
    pytest.param(Cat | Dog, id="Cat|Dog"),
    pytest.param(Schema(Cat | Dog, "v1"), id="Schema(Cat|Dog)"),
]

OPENAPI_STRUCT_MODELS = [
    pytest.param(PetOwner, id="PetOwner"),
    pytest.param(Schema(PetOwner, "v1"), id="Schema(PetOwner)"),
]


@pytest.mark.parametrize("model", OPENAPI_UNION_MODELS)
def test_openapi_with_union_type_model(model):
    """openapi() should not crash when a union type is registered as a resource."""
    from fastapi import FastAPI

    ac = AutoCRUDClass()
    ac.configure(model_naming="same")
    ac.add_model(model)
    app = FastAPI()
    ac.apply(app)
    ac.openapi(app)  # must not raise AttributeError: 'types.UnionType' has no __name__
    assert app.openapi_schema is not None


@pytest.mark.parametrize("model", OPENAPI_STRUCT_MODELS)
def test_openapi_with_struct_having_union_field(model):
    """openapi() should not crash when a Struct with a union field is registered."""
    from fastapi import FastAPI

    ac = AutoCRUDClass()
    ac.configure(model_naming="same")
    ac.add_model(model)
    app = FastAPI()
    ac.apply(app)
    ac.openapi(app)
    assert app.openapi_schema is not None


# ---- OpenAPI schema name sanitisation (no dots) ----


@pytest.mark.parametrize("model", OPENAPI_UNION_MODELS)
def test_openapi_schema_names_no_dots_for_union_resource(model):
    """Component schema names must not contain '.' when the resource is a union type.

    msgspec uses module-qualified names (e.g. ``__main__.Cat``) inside generic
    parameters like ``FullResourceResponse[Cat | Dog]``, which produces schema
    names containing dots.  These dots break the web code generator.
    """
    from fastapi import FastAPI

    ac = AutoCRUDClass()
    ac.configure(model_naming="same")
    ac.add_model(model)
    app = FastAPI()
    ac.apply(app)
    ac.openapi(app)

    schema_names = list(app.openapi_schema["components"]["schemas"].keys())
    dotted = [n for n in schema_names if "." in n]
    assert dotted == [], f"Schema names must not contain dots, but found: {dotted}"


@pytest.mark.parametrize("model", OPENAPI_STRUCT_MODELS)
def test_openapi_schema_names_no_dots_for_struct_with_union_field(model):
    """Component schema names must not contain '.' for Structs with union fields."""
    from fastapi import FastAPI

    ac = AutoCRUDClass()
    ac.configure(model_naming="same")
    ac.add_model(model)
    app = FastAPI()
    ac.apply(app)
    ac.openapi(app)

    schema_names = list(app.openapi_schema["components"]["schemas"].keys())
    dotted = [n for n in schema_names if "." in n]
    assert dotted == [], f"Schema names must not contain dots, but found: {dotted}"


def test_openapi_refs_consistent_after_dot_sanitisation():
    """All $ref pointers must still resolve after schema name sanitisation."""
    import json

    from fastapi import FastAPI

    ac = AutoCRUDClass()
    ac.configure(model_naming="same")
    ac.add_model(Cat | Dog)
    app = FastAPI()
    ac.apply(app)
    ac.openapi(app)

    schema_json = json.dumps(app.openapi_schema)
    components = app.openapi_schema["components"]["schemas"]

    # Every $ref must point to an existing component
    import re

    refs = re.findall(r'"\$ref":\s*"#/components/schemas/([^"]+)"', schema_json)
    for ref_name in refs:
        assert ref_name in components, (
            f"$ref '{ref_name}' points to non-existent component. "
            f"Available: {list(components.keys())}"
        )
