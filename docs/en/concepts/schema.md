
> **TL;DR**
>
> - Define resources with `msgspec.Struct`
> - Use `Schema` only when you need migrations or validation

# Schema & model types

SpecStar separates two concepts:

1. **Resource model** – the Python type representing stored data
2. **Schema** – the descriptor defining versioning, migrations, and validation

In most cases you will define your resource using **`msgspec.Struct`**.

---

## Resource models (`msgspec.Struct`)

SpecStar primarily uses **`msgspec.Struct`** to define resource models.

```python
from msgspec import Struct

class User(Struct):
    name: str
    age: int
```

These models define the **payload stored in the resource system**.

---

### Why `msgspec.Struct`

#### 1. `msgspec.Struct` keeps the schema explicit

`msgspec.Struct` represents data as-is, without adding hidden behavior to the schema itself.
This encourages developers to focus on what is actually stored when modeling resources.

Some modeling libraries support embedding validation logic, computed fields, or other behaviors directly in the schema class. While this can feel convenient at first, it can also encourage coupling persisted data with application logic. Over time, that coupling can make schema evolution and data migration harder as business requirements change.

With `msgspec.Struct`, the persisted model stays explicit and predictable. We recommend keeping resource schemas focused on stored data, while placing validation and business logic in separate layers.

This approach also helps avoid the need to create multiple near-duplicate models for the same concept, such as separate input and output models for every resource.

In SpecStar, we encourage a clean architecture style: the resource schema is the durable domain model, while input/output layers can be adapted separately when needed.

#### 2. Union types are ergonomic

`msgspec` provides strong support for union types, which is especially useful when schemas evolve over time.

```python
class Payment(Struct):
    method: Card | Cash
```

This makes it straightforward to model variant payloads without introducing large amounts of custom validation code.

---

#### 3. High performance

`msgspec` is designed for **fast serialization and deserialization**, which is useful for:

* high-throughput CRUD workloads
* large resource payloads
* heavy read/write operations

This makes it a strong fit for systems that need predictable performance at scale.

---

#### 4. Partial decoding

`msgspec` supports efficient **partial decoding**, so only the required fields need to be decoded.

This can reduce CPU and memory overhead in metadata-heavy or projection-based workflows.

---

## Other supported model types

SpecStar can also accept other model types.

### Pydantic `BaseModel`

Pydantic models are supported and converted into SpecStar's internal struct-based representation.

```python
from pydantic import BaseModel

class User(BaseModel):
    name: str
    age: int
```

Behavior:

* SpecStar converts the model into its internal struct-based representation for storage
* the Pydantic model can still be used for **validation** at integration boundaries

---

### `dataclass` / `TypedDict`

SpecStar is designed primarily around `msgspec.Struct`. Other model styles may work in limited integrations, but they are not part of the recommended default workflow.

---

## What to use when

Use **`msgspec.Struct` only** when:

* your stored resource shape is already stable
* you do not need versioned migrations
* validation can live at the application boundary

Add **`Schema`** when:

* stored resource versions need to evolve over time
* you need migration steps between versions
* you want schema-level validation hooks during loading or migration

---

## Schema (migration & validation)

SpecStar also provides the **`Schema` descriptor**, which defines:

* the **target schema version**
* **migration steps**
* optional **validation logic**

Example:

```python
from specstar import Schema

schema = (
    Schema(User, "v2")
    .step("v1", migrate_v1_to_v2)
)
```

When SpecStar loads stored resources:

* it reads the stored version
* finds the **shortest migration path**
* executes migration steps automatically

See also the migration guide for end-to-end examples.

---

## Practical guidance

Start with plain **`msgspec.Struct`**. Introduce **`Schema`** only when you need versioned migrations or validation hooks.

Recommended workflow:

1. Define your model using `msgspec.Struct`
2. Register it with SpecStar

```python
spec.add_model(User)
```

If schema evolution is needed:

```python
# Legacy style (IO[bytes])
spec.add_model(
    Schema(User, "v2").step("v1", migrate_v1_to_v2)
)

# Typed style (recommended) — source_type auto-decodes for you
def migrate_v1_to_v2(data: UserV1) -> UserV2:
    return UserV2(name=data.name, age=data.age, role="user")

spec.add_model(
    Schema(UserV2, "v2").step("v1", migrate_v1_to_v2, source_type=UserV1)
)
```

---

## Summary

| Concept          | Purpose                                       |
| ---------------- | --------------------------------------------- |
| `msgspec.Struct` | use it to define stored resource data         |
| `Schema`         | add it for versioning, migration, validation  |
