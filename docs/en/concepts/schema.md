
> **TL;DR**
>
> - Define resources with `msgspec.Struct`
> - Use `Schema` only when you need migrations or validation

# Schema & model types

AutoCRUD separates two concepts:

1. **Resource model** – the Python type representing stored data
2. **Schema** – the descriptor defining versioning, migrations, and validation

In most cases you will define your resource using **`msgspec.Struct`**.

---

# Resource models (msgspec.Struct)

AutoCRUD primarily uses **`msgspec.Struct`** to define resource models.

```python
from msgspec import Struct

class User(Struct):
    name: str
    age: int
```

These models define the **payload stored in the resource system**.

---

## Why msgspec.Struct

### 1. Union types are ergonomic

`msgspec` provides strong support for union types, which are common when schemas evolve.

```python
class Payment(Struct):
    method: "Card | Cash"
```

This makes it easy to represent variant payloads without complex validation logic.

---

### 2. High performance

`msgspec` is designed for **fast serialization and deserialization**, which is important for:

* high-throughput CRUD workloads
* large resource payloads
* heavy query operations

---

### 3. Partial decoding

`msgspec` allows efficient **partial decoding**, meaning only the required fields need to be decoded.

This helps reduce CPU and memory overhead in metadata-heavy workflows.

---

# Other supported model types

AutoCRUD can also accept other model types.

### Pydantic BaseModel

Pydantic models are supported and automatically converted to structs internally.

```python
from pydantic import BaseModel

class User(BaseModel):
    name: str
    age: int
```

Behavior:

* AutoCRUD converts the model into a struct for storage
* the Pydantic model can be used as a **validator**

---

### dataclass / TypedDict

These may work depending on configuration, but they are **not the recommended primary schema type**.

`msgspec.Struct` is the most predictable and performant option.

---

# Schema (migration & validation)

AutoCRUD also provides the **`Schema` descriptor**, which defines:

* the **target schema version**
* **migration steps**
* optional **validation logic**

Example:

```python
from autocrud import Schema

schema = (
    Schema(User, "v2")
    .step("v1", migrate_v1_to_v2)
)
```

When AutoCRUD loads stored resources:

* it reads the stored version
* finds the **shortest migration path**
* executes migration steps automatically

See:

* **How-to → Migrations**

---

# Practical guidance

Recommended workflow:

1. Define your model using `msgspec.Struct`
2. Register it with AutoCRUD

```python
crud.add_model(User)
```

If schema evolution is needed:

```python
crud.add_model(
    Schema(User, "v2").step("v1", migrate_v1_to_v2)
)
```

---

# Summary

| Concept          | Purpose                                       |
| ---------------- | --------------------------------------------- |
| `msgspec.Struct` | defines the resource payload                  |
| `Schema`         | defines versioning, migration, and validation |
