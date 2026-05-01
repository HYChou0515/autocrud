# Pydantic Integration

SpecStar works well with Pydantic models when you want declarative validation and a familiar model authoring style.

This is especially useful if your project already uses `BaseModel` or relies on field validators and discriminated unions.

---

## What SpecStar does for you

When you register a Pydantic model, SpecStar can:

- accept Pydantic model instances as input
- accept plain dictionaries and validate them through Pydantic
- convert the validated shape into internal `msgspec.Struct` storage
- keep API and storage behavior efficient while preserving a Pydantic-friendly development flow

A key rule is that the internal resource manager still works with Struct-based storage objects, even when the input side uses Pydantic.

---

## Basic example

```python
from pydantic import BaseModel, field_validator
from fastapi import FastAPI

from specstar import spec


class Character(BaseModel):
    name: str
    level: int = 1

    @field_validator("level")
    @classmethod
    def level_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("level must be at least 1")
        return value


app = FastAPI()
spec.add_model(Character)
spec.apply(app)
```

With this setup, create and update operations can use either:

- a `Character(...)` instance
- a plain dictionary with the same fields

---

## Validation flow

There are two layers to keep in mind:

### 1. Pydantic validation

Pydantic checks:

- field types
- custom validators
- discriminated unions
- model-level rules you define

### 2. SpecStar resource handling

After validation, SpecStar converts the model into its internal representation and continues with:

- indexing
- versioning
- persistence
- route generation
- search and lifecycle behavior

This means you get the ergonomics of Pydantic without giving up the core SpecStar model.

---

## Passing dicts directly

You do not need to instantiate the Pydantic class yourself every time.

This is valid when the registered resource model is Pydantic-based:

```python
manager.create({"name": "Alice", "level": 5})
```

If the payload is invalid, the request is rejected through the validation layer.

---

## Using field validators

Pydantic validators are a good fit for domain rules that belong directly to the model.

```python
from pydantic import BaseModel, field_validator


class Item(BaseModel):
    name: str
    price: int

    @field_validator("price")
    @classmethod
    def price_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("price must be non-negative")
        return value
```

Use this style when the rule belongs naturally to the schema itself.

---

## Discriminated unions

SpecStar also supports Pydantic discriminated unions.

This is useful for data that can take multiple tagged shapes, such as different skill types or event payloads.

```python
from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field


class ActiveSkill(BaseModel):
    skill_type: Literal["active"] = "active"
    damage: int


class PassiveSkill(BaseModel):
    skill_type: Literal["passive"] = "passive"
    buff_percentage: int


SkillDetail = Annotated[
    Union[ActiveSkill, PassiveSkill],
    Field(discriminator="skill_type"),
]
```

This pattern is demonstrated in the Pydantic RPG example in the repository.

---

## When to choose Pydantic vs msgspec

### Choose Pydantic when you want:

- rich validator ergonomics
- a schema style your existing team already uses
- discriminated unions and validation-heavy application models

### Choose msgspec-first models when you want:

- the simplest native SpecStar path
- minimal overhead
- direct alignment with the internal storage representation

Both approaches are valid. Pick the one that matches your team’s workflow.

---

## Related pages

- [Validation](/specstar/concepts/validation)
- [Schema](/specstar/concepts/schema)
- [Examples](/specstar/examples/)
- [Routes generation](/specstar/howto/routes)
